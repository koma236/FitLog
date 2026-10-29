# API共通契約・エラー一覧

> health・FL-02認証・FL-03プロフィール・FL-04記録の実装契約。画像・交流・全体タイムラインなどは将来の契約案。検証結果は別途記録する。

正本は [OpenAPI](openapi.json)。JSONのデータ項目はsnake_case、既存の共通エラー項目のみfieldErrors/requestIdという名前を使う。すべてのAPI応答にX-Request-Idを付ける。

## 認証・CSRF
認証の採用仕様と運用は [FL-02認証](auth-implementation.md) を参照する。
認証APIはDjango JSON views、DBセッション、global CSRF検査を使用する。
signup201/login200/me200の本文はid/username/display_name/emailのみ。logout204は本文なし。
セッション期限は成功時刻から7日固定。Secure/HttpOnly/SameSite=Lax/Path=/・host-onlyが既定。
全auth応答はno-store。IPあたりsignup/login合算10回/60秒固定窓で、直接接続元のHMACのみをPostgreSQLへ保存する。

## 入力とページング
未知フィールドは400。usernameは予約語me/searchを除く小文字ASCII英数字と_、emailは前後空白除去・小文字化して一意とする。文字数はUnicodeコードポイントで数える。表示名・種目名・コメントの前後空白を除去し空白だけの値を拒否する。パスワードは入力をそのまま扱い、勝手にtrimしない。
idはUUID。重量は10進文字列、DBはdecimal(5,2)。実施日はAsia/Tokyoの今日以前、日時はUTCのRFC3339。種目・セットの配列順をpositionとして保存する。入力上限はOpenAPIとF03で一致させる。
limitは1〜50、既定20。不正値・不透明カーソルの改ざん・一覧種別や検索条件の不一致は400 INVALID_CURSOR。新着順はcreated_at DESC,id DESC、コメントだけASC。ページ取得の間に削除やフォロー変更がある場合は現在の対象集合を返し、厳密な全件スナップショットは保証しない。
PUTは対象データの全置換。記録PUTは画像・コメント・いいねを変更しない。同時編集は後勝ちとし履歴・競合解決UIは初版外。POSTの記録・コメント作成は自動再試行せず、結果不明時は再取得して確認する。いいね・フォローは冪等。

## 画像
記録保存と画像添付は別API。画像失敗時は「記録は保存済み、画像は未保存」として再試行できる。multipartのimageは1個のみ。JPEG/PNGを実デコード、画素数と入力サイズを検査し、EXIFを除去して再エンコードする。入力5MiB（avatar2MiB）以下、2000万画素以下。再エンコード後も同じサイズ上限を適用する。SVG/GIFや偽装画像は拒否する。
画像は非公開S3へサーバー生成キーで保存し、DBはキーだけ保持。署名付き取得URLは300秒。URLを知る者は期限内に取得できるため、URL失効前の即時アクセス取消は保証しない。投稿APIを再取得して期限切れURLを更新する。
新画像保存→DB切替→旧画像削除の順。DB切替前に失敗すれば旧画像は残す。新画像のDB登録に失敗した場合は新オブジェクトの補償削除を試みる。削除失敗は専用のcleanup記録にキーと操作IDを残し、運用コマンドで再試行する。DBも利用不能で記録できない場合は孤立キーをマスク不要の内部運用ログに残し、S3とDBの照合で再回収する。本文・URL・画像内容はログに残さない。
同じ投稿／avatarの画像変更はDB行ロック等で直列化し、操作ごとに別キーを使う。他の更新が採用したキーを補償削除しない。S3 DeleteObjectの再実行は許容する。処理中のアップロードを消さないよう孤立照合では最低1時間の猶予を置く。

## エラーコード
| HTTP | code | 用途 |
|---|---|---|
| 400 | `VALIDATION_ERROR` | 入力値・未知項目・形式 |
| 400 | `INVALID_REQUEST` | 本人ヘッダーの欠落／形式不正 |
| 400 | `INVALID_CURSOR` | カーソル不正／他条件の流用 |
| 400 | `SELF_FOLLOW` | 自己フォロー |
| 401 | `AUTH_REQUIRED` | ログインが必要 |
| 401 | `INVALID_CREDENTIALS` | 認証失敗 |
| 403 | `FORBIDDEN` | 本人以外の更新削除 |
| 403 | `CSRF_FAILED` | CSRF検証不一致 |
| 404 | `NOT_FOUND` | 対象不在 |
| 405 | `METHOD_NOT_ALLOWED` | 許可されないHTTPメソッド。Allowを返す |
| 406 | `NOT_ACCEPTABLE` | 応答形式を提供できない |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | リクエストのContent-Type非対応 |
| 409 | `DUPLICATE_USERNAME` | ユーザー名重複 |
| 409 | `DUPLICATE_EMAIL` | メール重複 |
| 409 | `RECORD_OWNER_CHANGED` | 記録入力開始時と現在の本人が異なる。更新しない |
| 409 | `POST_ID_CONFLICT` | 使用済み／削除済みの記録ID。保存状態を確認する |
| 409 | `PROFILE_OWNER_CHANGED` | 編集開始時と現在の本人が異なる。更新しない |
| 409 | `ALREADY_AUTHENTICATED` | すでにログイン中。meを確認 |
| 413 | `PAYLOAD_TOO_LARGE` | 認証・プロフィールJSONが16KiB超、または記録JSONが32KiB超 |
| 413 | `IMAGE_TOO_LARGE` | ファイルサイズまたは画素数超過 |
| 415 | `INVALID_IMAGE` | 画像形式・デコード不正 |
| 429 | `RATE_LIMITED` | 認証試行制限 |
| 500 | `INTERNAL_ERROR` | 予期しない失敗。内部例外は公開しない |
| 503 | `STORAGE_UNAVAILABLE` | 画像保存失敗 |
| 503 | `SERVICE_UNAVAILABLE` | 依存サービス停止 |

fieldErrorsはフィールドパス→文字列配列。例：`exercises.0.sets.1.reps`。機密値をmessageに埋め込まない。OpenAPIのエラー一覧と同時に変更する。

## 設計レビューの重点
CSRFを含む認証境界、DBとS3の障害境界、画像競合、ページングの更新境界、UTC/JST、同時いいねとフォロー、OpenAPIと画面の整合性。モックはこれらのサーバー側保証の証拠ではない。

## FL-03 プロフィール

`GET /api/users/me`、`PUT /api/users/me`、`GET /api/users/{username}`。
詳細は[F07](../features/F07_profile.md)。会員間のみ、全応答no-store/Vary:Cookie。
PUTにはX-CSRFTokenと編集開始時のUser UUIDを送るX-Profile-Ownerが必須。不一致は409 `PROFILE_OWNER_CHANGED`。本文から対象Userや計算結果を指定できない。成功/エラーのschemaはOpenAPIを参照。
本人だけvisibility8項目を取得可能。他人向けは非公開値をhealth/energyからキーごと除外し、emailも返さない。公開結果からの数学的な推測を防ぐ保証はない。

## FL-04 筋トレ記録（実装）

POST /api/posts、GET/PUT/DELETE /api/posts/{id}、GET /api/users/{username}/posts。詳細は[F03](../features/F03_post.md)とOpenAPI。新規POSTはclient生成UUID v4を固定し、削除後もPostIdentityに保持。RECORD_OWNER_CHANGED（409）は下書きの本人が変化、POST_ID_CONFLICT（409）は使用済みidで、いずれも自動再送しない。INVALID_CURSOR（400）は先頭からの明示再取得が必要。

記録JSON上限32KiB・深さ8、UTF-8、厳密な数値/文字列と既知キーだけを受理。413 PAYLOAD_TOO_LARGEは記録のbody上限にも適用。全応答no-store/Vary:Cookie/request-id。本人向けPostだけトップレベルvisibilityを持ち、他人向けenergy_inputは公開かつ非nullのキーだけ（なければ{}）。viewer_idは実際の閲覧会員を示し、クライアントは期待する本人と照合する。

固定METのカロリーと保持/再計算規則、同一snapshotの読取り、削除済みid保護はF03参照。GitHub Actions CIは未実装で、品質checksはローカルDockerで実行する。
