# F03: 筋トレ記録（FL-04実装）

会員が記録を作成・閲覧し、本人だけが編集・削除する。実施日、1〜10種目、各1〜20セット、重量0〜999.99kg（小数文字列2桁まで）・回数1〜999、任意メモ500コードポイント。実施日はJST当日以下。画像はFL-05、交流はFL-06、全体/フォロー中一覧はFL-07。

POST /api/posts（201）、GET/PUT/DELETE /api/posts/{id}（200/200/204）、GET /api/users/{username}/posts（200）。全ルート認証必須、書込みはCSRFとX-Record-Ownerの本人一致ガード必須。authorはrequest.userだけで決める。他人の変更403、削除済み404、本人切替409 RECORD_OWNER_CHANGED。

新規フォームで生成したUUID v4をPOSTのidとして固定する。PostIdentityに使用済みidを保持するので、同時投稿の重複や、削除後に同じURLで別の会員の内容へすり替わることを防ぐ。既存/削除済みidの作成は409 POST_ID_CONFLICT。DELETEでPostと子を消し、Identityは残す。User削除は製品機能の対象外だが、DBではPost.user CASCADE、Identity.author SET_NULL。

書込みはUser→最新Postの行ロック順。不在・所有権をロック後にも再検査し、最新行で再計算の要否を判定する。親子を全置換し、失敗すれば全旧値を保持。PUTで不在Postを作り直さない。created_atは作成時のUserロック後に決め、編集で変更しない。

GETの親・子・limit+1の取得はPostgreSQL17の短いREPEATABLE READ READ ONLY transaction。リクエスト内は同じsnapshotであり、更新/削除により新旧の子が混在しない。ページ間の全件snapshotは保証せず、遅延commitや新着は先頭から再読込みで確認する。

## 消費カロリーと公開設定

MET×体重kg×分÷60をDecimalで計算し、最終値だけROUND_HALF_UP。general3.5（02054）、squat5.0（02052）、vigorous6.0（02050）。[2024 Compendium](https://pacompendium.com/conditioning-exercise/)の推定値。対象は保存済み年齢19〜59歳。体重・年齢・時間・種類不足は未計算でも保存できる。身長・計算式区分・普段の活動量は運動計算に使わない。

初回は保存時点で計算。PUTで時間/種類が変わるかrecalculate=trueの場合だけ現在の身体情報で再計算する。メモ・種目・日付・公開設定だけなら過去結果を保持する。過去の体重/年齢はコピー保存しない。日次消費へ加算しない。ブラウザは体重の小数文字列からBigIntの整数比でプレビューし、サーバーの保存結果を正とする。

時間と種類は独立にpublic/private（初期private）。本人はenergy_inputの両キーとPostトップレベルvisibilityを見る。他人は公開かつ値ありの項目だけを受け、どちらもなければenergy_input:{}、visibilityキーはない。カロリー結果は会員間に公開。非公開の体重・年齢・emailをDTOへ含めないが、公開結果や時間・種類から体重・対象年齢帯等を推測できる場合があることを入力時に案内する。

カードは「消費カロリー」、本人の非公開の値だけ「（非公開）」、公開時はラベルなし。未計算は本人/他人とも「未計算」で、他人に不足理由を出さない。計算方法の説明は初期閉の折りたたみ。カード内の安静時注記は置かない。

## 異常時・一覧

32KiB・深さ8・UTF-8・重複キー/未知キー/非有限数/不正Unicodeを制限。fieldErrorsは既知のパスだけで最大32項目。body上限413、形式415。全応答no-store/Vary:Cookie/request-id、401にWWW-Authenticate。DB/session失敗503でsession cookieを消し、SQL/本文等をログに出さない。

通信断は入力を固定して元idの保存状態をGET確認し、勝手に再送しない。503後の401は下書きを破棄し再ログイン後の一覧確認を案内。CSRF失敗は本人再確認後に1回だけtoken更新し、明示再送を待つ。本人が変われば古い下書きを捨てる。削除は確認ダイアログを使用する。

一覧はcreated_at DESC,id DESC、limit既定20・最大50、24時間期限の署名cursorを対象/閲覧者UUIDへ束縛する。古い記録を下に追加し、追加取得失敗で既読を消さない。INVALID_CURSORは同じcursorを再試行せず、明示操作で先頭から読む。

## 検証根拠

[OpenAPI](../api/openapi.json)と[固定手計算表](../api/workout-calorie-vectors.json)を正本とする。固定値10件、16状態×本人/他人のDTO、JST・入力境界、原子的置換、並行POST/PUT/DELETEと読取りsnapshot、DOMの本人変更・CSRF・通信断を検証する。実行結果は品質レポートへ記録し、設計レビューを実装/画面の検証済み証拠として扱わない。

## FL-05 記録の写真

任意のJPEG/PNGを1枚添付・差し替え・画像だけ削除できる。5MiB以下・2000万画素以下、16bit PNG/APNG/GIF/SVGは非対応。写真は会員間で表示し、運動時間・種類と身体情報の公開設定を変更しない。表示は画像の縦横比を維持し、読込み失敗時は代替表示。

新規投稿は本文のPOST成功後、画像を別のPUTで保存する。画像だけ失敗した場合も本文/セット/カロリーは保存済みであり再POSTしない。画像だけを同じFile/操作UUIDで明示再試行できる。結果不明時は親GETのimage.idが送信操作と一致する場合だけ保存成功。画像削除は本文を消さず、投稿削除は画像を退役し清掃対象へ残す。

画像変更はsession/CSRF/X-Record-Ownerで本人確認し、X-Image-Operationは論理操作ごとのUUIDv4。原本のファイル名・EXIF/GPS等は保存/出力しない。JPEG/PNGを実デコードして向きを補正し再エンコード。ICCの色域変換は行わず色味変化を許容する。署名URLは300秒、URLを知る者は期限内に取得できる。

FL-05はlocal専用private filesystemと期限付き配信を実装する。S3 adapter/実接続はFL-09。ローカル処理枠1、画像PUTのclient期限45秒、混雑時は2秒後に明示再試行する。server側の受信総期限は未実装で、遅い送信が画像処理枠を占有するLow制約をFL-09公開前に検証・対処する。
