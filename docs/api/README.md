# API共通契約・エラー一覧

> healthとFL-02認証の実装契約。他の業務APIは将来の契約案。検証結果は別途記録する。

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
| 409 | `ALREADY_AUTHENTICATED` | すでにログイン中。meを確認 |
| 413 | `PAYLOAD_TOO_LARGE` | 認証JSONが16KiB超 |
| 413 | `IMAGE_TOO_LARGE` | ファイルサイズまたは画素数超過 |
| 415 | `INVALID_IMAGE` | 画像形式・デコード不正 |
| 429 | `RATE_LIMITED` | 認証試行制限 |
| 500 | `INTERNAL_ERROR` | 予期しない失敗。内部例外は公開しない |
| 503 | `STORAGE_UNAVAILABLE` | 画像保存失敗 |
| 503 | `SERVICE_UNAVAILABLE` | 依存サービス停止 |

fieldErrorsはフィールドパス→文字列配列。例：`exercises.0.sets.1.reps`。機密値をmessageに埋め込まない。OpenAPIのエラー一覧と同時に変更する。

## 設計レビューの重点
CSRFを含む認証境界、DBとS3の障害境界、画像競合、ページングの更新境界、UTC/JST、同時いいねとフォロー、OpenAPIと画面の整合性。モックはこれらのサーバー側保証の証拠ではない。
