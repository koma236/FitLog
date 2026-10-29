# F07: プロフィール表示・編集

FL-03は表示名・自己紹介・任意の身体情報と項目別公開設定を扱う。画像はFL-05、記録一覧はFL-04、交流件数はFL-06/07で接続する。email/usernameの変更は含まない。

## API

| method | path | 内容 |
|---|---|---|
| GET | `/api/users/me` | 本人の全項目と公開設定 |
| PUT | `/api/users/me` | 本人のプロフィールを完全置換 |
| GET | `/api/users/{username}` | 本人なら全項目、他人なら公開項目だけ |

会員間のみ利用可能。未認証401、不在・無効化User・大文字usernameは認証後404。
Profile.idはUser.pkのUUID文字列。email/password/セッション情報はプロフィール応答に含まれない。

本人にはhealth5項目、energy3項目とvisibility8項目を返す。他人にはpublicとしたhealth/energyキーだけ返し、非公開キーはnullで埋めずに除外する。公開値が未入力/未計算ならnull。全privateならhealthとenergyは{}。visibilityや不足理由は他人へ返さない。
公開の範囲はログイン利用者間。既定は全て非公開。公開した数値から非公開値を推測できない保証はない。

PUTはJSONキーdisplay_name/bio/health/visibilityを全て必須とする。healthはheight/weight/age/formula/activityの5キー、visibilityは同5キーとbmr/tdee/intakeの8キー。未知項目を拒否し、対象Userを本文で指定できない。`X-CSRFToken`と、編集開始時のUser UUIDを示す`X-Profile-Owner`が必須。後者は認証ではなくrequest.userとの照合に使い、不一致なら409 PROFILE_OWNER_CHANGEDで更新しない。

## 入力

- 表示名はFL-02と共通のtrim後1〜50コードポイント/Cc拒否。自己紹介はCRLF/CR→LF後に160コードポイントまで、trimなし。LF/TAB以外のCcは拒否。
- 身長は100〜250cm、体重は20〜350kgで両端を含む。nullか、ASCIIの`^(0|[1-9][0-9]{0,2})(\.[0-9])?$`に完全一致する文字列。小数1桁まで、返却は小数1桁。空文字・前後空白・先頭ゼロ・指数等を拒否。
- 年齢はnullかJSON整数0〜120（bool/float/文字列を拒否）。男性式/女性式、活動量low/medium/highはnullで未選択にできる。
- 公開設定は各キーpublic/privateのみ。欠落や不正値を公開へ補完しない。
- 本文16KiBまで、JSON/UTF-8のみ。重複キー・深いJSON・不正Unicodeは400。未知キーや入力値をエラー・ログに反射しない。

判定順はCSRF→認証→method→413→415→ownerヘッダー400→owner不一致409→JSON/項目400。HEAD/OPTIONSは405。Allowは本人ルートGET, PUT、usernameルートGET。
全応答はno-store/Vary:Cookie/request-id。DB障害は固定JSONの503とsession cookie破棄。Userと身体情報の更新は同じatomicで、Userをロックして直列化し、commit成功後だけ200を返す。

## 計算と画面

サーバーはMifflin–St Jeor簡略式をDecimalで計算し、19〜59歳で必要入力が揃う場合だけ整数kcal/日を返す。プレビューはBigIntの整数比計算。最終結果だけ四捨五入し、丸め後bmrからtdeeを算出しない。活動係数low=1.5、medium=1.75、high=2.1はアプリの参考値。体重維持のintakeはtdeeと同値。過去の運動記録や日次へ運動消費を加算しない。
原著: [Mifflin–St Jeor, 1990](https://pubmed.ncbi.nlm.nih.gov/2305711/)。入力は任意で、対象外・不足は未計算。減量/増量の指示はしない。

本人の非公開項目にだけ「非公開」。公開項目の状態ラベルは出さない。選択肢は公開/非公開。編集画面の公開結果から推測できる旨の案内と、計算方法の折りたたみを維持する。
下書きは取得時の本人UUIDに紐付け、送信前の本人確認とサーバー照合を併用する。403はcsrfを1回更新して明示操作を待ち、PUT自動再送をしない。401/本人変更で機密状態を消去する。
503/通信失敗時は下書きを保持し、保存状態の明示再取得が成功した場合だけ置き換える。古いGET/PUT応答は破棄する。保存中の履歴移動は元のhashへ戻し、それ以外の編集画面離脱では下書きを破棄する。身体情報をWeb StorageやURLに保存しない。

## 検証の根拠

`backend/tests/TEST-ORACLES.md` とOpenAPI、固定手計算の [ベクトルJSON](../api/profile-calorie-vectors.json)。同じJSONを各テスト用コピーへ配置し、固定SHA-256で一致を検証する。256公開設定、A/B/Cの所有者、計算境界、原子的更新・失敗、移行互換、DOMとPC/375pxブラウザを検証対象とする。文書の存在は未実行のテスト成功を意味しない。
