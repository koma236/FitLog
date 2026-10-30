# API共通契約・エラー一覧

> health・FL-02認証・FL-03プロフィール・FL-04記録・FL-05ローカル画像・FL-06コメント/いいねの実装契約。フォロー・全体タイムラインなどは将来の契約案。検証結果は別途記録する。

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
FL-05の現行契約は下記「FL-05 実装契約」とOpenAPIを参照する。投稿保存と画像添付は別APIで、画像失敗時も投稿は保存済みとして画像だけ再試行できる。現在はprivate filesystemへの保存であり、S3保存・補償削除・孤立キーのログ出力は実装していない。S3の整合性・清掃方式はFL-09で別途設計・検証する。

## エラーコード
| HTTP | code | 用途 |
|---|---|---|
| 400 | `VALIDATION_ERROR` | 入力値・未知項目・形式 |
| 400 | `INVALID_REQUEST` | 本人/画像操作ヘッダーの欠落・形式不正、multipart構造不正 |
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
| 409 | `SOCIAL_OWNER_CHANGED` | コメント/いいね開始時と現在の本人が異なる |
| 409 | `COMMENT_ID_CONFLICT` | 使用済み/削除済みのコメントID。POSTを自動再送せず保存状態を確認 |
| 409 | `IMAGE_OPERATION_CONFLICT` | 同じ画像操作IDの内容・対象不一致、または退役済み |
| 409 | `IMAGE_OPERATION_PENDING` | 同じ画像操作が処理中。Retry-After: 2 |
| 413 | `PAYLOAD_TOO_LARGE` | JSONの16/32KiB上限、画像の入出力2/5MiB・20MP上限、またはmultipart全体上限の超過 |
| 415 | `INVALID_IMAGE` | 画像形式・デコード不正 |
| 429 | `RATE_LIMITED` | 認証試行制限 |
| 500 | `INTERNAL_ERROR` | 予期しない失敗。内部例外は公開しない |
| 503 | `IMAGE_PROCESSING_BUSY` | 画像処理枠が使用中、未処理。Retry-After: 2 |
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

## FL-05 実装契約

ローカルのprivate filesystemのみ実装し、S3 adapterと実AWS検証はFL-09に行う。FITLOG_ENV=local以外ではlocal adapterの起動を拒否し、storage操作時にも拒否する。専用Docker volumeを使用し、MEDIA_URL/staticで直接配信しない。S3はFL-09の対象であり、FL-05の実S3確認完了を意味しない。

PUT `/api/posts/{id}/image` と `/api/users/me/avatar` はmultipart field `image`を厳密に1個、owner header（X-Record-Owner/X-Profile-Owner）、X-CSRFToken、X-Image-Operation(UUIDv4)を要求する。DELETEは画像だけを削除し未設定も204。PUT成功はPostまたはProfile DTO、viewer_idとnullable image/avatarを返す。author.avatarも同じ形。画像情報はid/url/expires_at/width/height/content_typeだけでkey/digest/原本filenameは返さない。

JPEG/PNGの入力と再エンコード後の両方にpost5MiB/avatar2MiB上限、全画素20MPまで。16bit PNG/APNG等は415。EXIF向き補正後pixelから新規画像を作って全metadataを除去、JPEG85/PNG6、透過保持、ICC色変換なし。upload原本はbounded memory handlerに限定する。raw multipartはファイル上限+64KiB、複数/未知fieldは400。既存JSONの16/32KiB上限を緩めない。

操作はpending予約を確定→immutable object保存→User/Post/ImageObject順にlockして添付を確定する。pendingは同binding/digestの再要求で再開可能。同IDの現在添付は200、退役済み/内容不一致/別対象は409 IMAGE_OPERATION_CONFLICT。新objectのlockを取得できない場合は409 IMAGE_OPERATION_PENDING/Retry-After2。process単位の処理枠1を取得できない場合は503 IMAGE_PROCESSING_BUSY/Retry-After2（未処理）。保存先障害503 STORAGE_UNAVAILABLEはsession DB障害と区別し、単に保存先失敗だけでsession cookieを消さない。

GET `/api/media/content/{token}` は300秒のcapability URL。tokenにはopaque asset UUIDと発行時刻のみ。署名・未来/期限・attached stateを確認し正規化画像だけを返す。no-store/nosniff/no-referrer、固定filename。URLを持つ者はsessionなしで期限内取得できる。削除後のlocal早期失効は本番S3の保証にしない。失敗時のURL再取得は画面の取得ページ/generation単位にGET1回まで集約する。

`cleanup_images --limit 100` はretired job、1時間以上放棄されたpending、管理prefix内のaged orphan/retired fileを回収する。完了jobもprefix照合から除外せず、遅延writeを次の巡回で回収。attachedは保護する。checkpointで有限ページを巡回、tempもactive flockと1h猶予で保護。FL-05は手動清掃、定期実行はFL-08/09で接続する。

画像PUTはclient45秒/明示中止に対応、server側総受信期限は現行local構成ではLow保留。127.0.0.1限定の開発機能で公開配置せず、FL-09公開前に受信期限・接続数・worker合計memoryを検証する。画像を無限に自動再送しない。

署名URLの取得は認証処理と独立しており、DB障害でもsession cookieを破棄せず固定503/no-storeを返す。署名の安全性はSECRET_KEYの機密性に依存する。composeの公開サンプル鍵はローカル確認専用で、FL-09公開前には本番でサンプルSECRET_KEYを拒否する検査を追加し、秘密鍵を別途設定する。Django multipartのFILES=1/FIELDS=16を明示し、画像経路ではさらにimageだけ1パートに制限する。


## FL-06 コメント・いいね

[F04](../features/F04_comment.md)/[F05](../features/F05_like.md)とOpenAPIが正本。全経路会員向け、全応答no-store/Vary:Cookie/request-id。書込みはCSRFとX-Social-Ownerで本人変更を拒否し、実際の主体はrequest.user。コメントはPOST{id UUIDv4,body}201、GET/PUT200、DELETE204。いいねPOST/DELETEは0bytes bodyで常に200のstate/countを返し、再送は冪等。

Postの全成功DTOにcomment_count/like_count/is_likedを必須追加。コメント/Likeはactive条件を一覧/単体/件数に揃え、無効な本人コメントは他人のPUT/DELETEでも404。parent/user削除はComment/Like CASCADE、本文なしCommentIdentityは保持。User→Post→Comment順で最新値を再検査し、同IDの削除後復活を拒否する。既存の画像・本文・energy・private射影は変えない。

コメントはUTF-8 JSON raw16KiB/深さ4、CRLF→LF、単独CR/control/surrogate拒否、Python strip、1..500 code points。HTMLはテキスト、NFC/NFKCなし。ASCの署名cursorはviewer/postに束縛し24h/2048bytes、limit20既定/50最大、未知/重複queryもINVALID_CURSOR。

新コードSOCIAL_OWNER_CHANGEDは全social書込み、COMMENT_ID_CONFLICTはコメントPOSTだけ。DELETEへ本文検証や画像処理のエラー/Retry-Afterを複写しない。結果不明は固定UUID/snapshotで照合し、新IDで自動POSTしない。再送は同ID/本文を1回、確認できない場合は警告後に明示中断できる。POST成功後は全ページを捨て先頭再取得し、本人の確認枠を一覧と区別する。
