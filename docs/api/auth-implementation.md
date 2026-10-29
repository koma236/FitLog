# FL-02 最小認証

メール/パスワードによる登録・ログイン、本人情報とログアウトを提供する。
画面は確認済みモックの登録/ログインフォームを基準とし、ホームには表示名とログアウトを置く。
メール確認、追加認証、SNSログイン、パスワード再設定、プロフィール編集、記録機能は含まない。

## HTTP契約

| メソッド・パス | 成功 | 本文 |
|---|---|---|
| GET /api/auth/csrf | 200 | csrf_token（masked token） |
| POST /api/auth/signup | 201 | AuthAccount |
| POST /api/auth/login | 200 | AuthAccount |
| POST /api/auth/logout | 204 | なし。匿名でもCSRFが正しければ成功 |
| GET /api/auth/me | 200 | AuthAccount。匿名/期限切れは401 AUTH_REQUIRED |

AuthAccountはid（UUID文字列）/username/display_name/emailの4項目。
すべての認証応答にCache-Control: no-storeとサーバー生成X-Request-Idを付ける。
エラーはcode/message/requestId、項目別案内がある場合だけfieldErrors（文字列配列）。
401にはWWW-Authenticate: Session、405にはAllow、429にはRetry-After（整数1〜60秒）を付ける。
ログイン失敗は未知メール・不一致・inactiveを同じ401 INVALID_CREDENTIALSにまとめる。
未知メールでも標準hasherを1回実行する。完全な時間同一性は保証しない。

| HTTP/code | message |
|---|---|
| 400 VALIDATION_ERROR | リクエストを確認してください。 |
| 401 AUTH_REQUIRED | ログインが必要です。 |
| 401 INVALID_CREDENTIALS | 認証情報を確認してください。 |
| 403 CSRF_FAILED | リクエストを再送してください。 |
| 405 METHOD_NOT_ALLOWED | このメソッドは利用できません。 |
| 409 DUPLICATE_USERNAME / DUPLICATE_EMAIL | すでに使われています。 |
| 409 ALREADY_AUTHENTICATED | すでにログインしています。 |
| 413 PAYLOAD_TOO_LARGE | リクエストが大きすぎます。 |
| 415 UNSUPPORTED_MEDIA_TYPE | 指定された入力形式は利用できません。 |
| 429 RATE_LIMITED | 時間をおいて再試行してください。 |
| 500 INTERNAL_ERROR | 処理中にエラーが発生しました。 |
| 503 SERVICE_UNAVAILABLE | 処理結果を確認できません。時間をおいてログインしてください。 |

登録409は利用可能性を示すためアカウントの存在を推測できる。試行制限で緩和するが、列挙防止を保証しない。

## 入力・保存

signupのキーはusername/display_name/email/password、loginはemail/passwordのみ。
欠落・型不正・未知項目・不正JSONを400、JSON本文16KiB超を413、非JSON形式を415とする。
emailはtrim・小文字化後、ASCIIの有効メールで最大254文字。
usernameはtrim・小文字化後、小文字英数字と_の3〜30文字、me/searchを拒否する。
display_nameはtrim後1〜50 Unicodeコードポイントで制御文字（Cc）を拒否する。
passwordはtrimせず、signupは12〜128文字とDjangoの類似/最小長/一般的/Numeric validatorを適用する。
loginは長さ1〜128のみを照合し、登録時の強度規則を再適用しない。
APIとcreate_user/create_superuserは同じ検証を使う。createsuperuserはemail/display_nameも必須。
標準hasherで保存し、password、セッションキー、staffなどを応答に含めない。

0001は保持し、0002でdisplay_name、Lowerの一意制約、試行窓を追加する。
旧UserのUUID/password/emailは変更せず、display_nameを既存usernameから引き継ぐ。
不正username、大小文字衝突、非ASCII/前後空白の旧メールはIDと違反種別のみでmigrationを停止する。
旧空メールは保持するがメールログインできない。架空メールの補完や自動renameをしない。
既知のusername unique/Lower(username)/Lower(email)違反のみ409へ変換し、usernameを優先する。
標準username制約はPostgreSQL introspectionで識別する。その他DBエラーは503にする。

## セッション・CSRF・UI

DjangoのDBセッションとlogin/logoutを使う。成功時にキーとCSRFをローテートし、
aware datetimeによる成功時刻+7日の固定期限を設定する。通常アクセスや途中保存で延長しない。
全POSTに匿名時もCSRF必須。global CSRF検査がメソッド判定より先に動くため、
safe非POSTは405、CSRF不正unsafeは403、正しいCSRF付き非POSTは405。これらは試行数に含めない。

session/CSRF cookieはSecure/HttpOnly/SameSite=Lax/Path=/、Domainなしが既定。
FITLOG_ENV=localとFITLOG_LOCAL_HTTP=1を両方指定するComposeだけHTTPを許可する。
不明環境値やproductionのlocal HTTP指定は起動エラー。ViteはHostを維持するproxyを使う。
CSRF_TRUSTED_ORIGINSは空、転送ヘッダやTLS終端を推測して信用しない。

フロントはmeで復元し、GET csrfのtokenをメモリだけに保持する。
成功後はCSRFを再取得。CSRF403でも1回取得し直すがPOSTは再送せず入力を保持する。
409 ALREADY_AUTHENTICATEDはme200でホーム、401ならフォームに留まる。
通信失敗・503・不正応答では結果不明を示し、自動再送せず本人の操作を待つ。
送信中は二重送信と画面切替を防ぐ。再読込/ウィンドウfocusで本人状態を確認し期限切れはログインへ戻す。
ユーザー値はJSXで表示し、localStorageの疑似認証や固定パスワードを使わない。

API境界はSessionMiddlewareより外側。派生SessionMiddlewareは標準の保存処理へ委譲し、
auth応答時のDatabaseError/SessionInterruptedだけを503に変換してcookieを削除する。
ビュー内のDB障害も503。障害処理でDBを再読込・再保存しない。
登録のUser保存後にsession保存が失敗した場合、Userが存在する可能性があるためログイン操作を案内する。

## 試行窓と運用

UTC UNIX時刻の60秒固定窓でsignup/loginの合計1〜10回を許可、11回以降429。
CSRF→メソッド→UPSERT単独autocommit→認証済み409→入力検証→password処理→User保存の順。
400/401/409/413/成功も数え、hash中やUser保存中にcounterの行ロックを持たない。
ATOMIC_REQUESTS=Falseとnon_atomic_requestsで外側transactionを排除し、保証できなければ503とする。
User保存のみ短いatomicに入れ、rollbackで確定済みcounterを消さない。

直接接続元だけをIPv4 /32、IPv4-mapped IPv6はIPv4、IPv6 /64へ正規化しHMAC-SHA256で保存する。
欠落/不正IPは503。X-Forwarded-Forを変更しても制限キーは変わらない。
生IP・メール・password・cookie・request body・DB例外本文をログへ出さない。
AUTH_RATE_LIMIT_HMAC_KEYは32文字以上必須、productionでは既知の公開ローカルサンプルを拒否する。
鍵変更は認証受付停止→最後の受付から120秒以上待機→全worker同時更新→再開とし、稼働中変更を行わない。

開発開始/終了時には、既存DBが稼働している状態で次を実行する（依存サービスの起動/停止は管理側が行う）。

```sh
docker compose --project-name fitlog-dev -f compose.yaml run --rm --no-deps backend uv run --frozen --no-sync python manage.py cleanup_auth_security
```

継続稼働では毎時実行が必要。clearsessionsで失効済みDBセッションを、独自清掃で現在窓より2分以上前の窓を削除する。
schedulerの配置はFL-08/09で扱う。固定窓の境界を跨ぐ集中、共有IPv6 prefix、多IP攻撃の限界を保持する。
trusted proxy・TLS終端・実接続元/Originの検証と多IP対策評価はFL-09の公開前条件で、今回設定を推測しない。

検証根拠はbackend/tests/TEST-ORACLES.md。本文書はテスト実行・独立品質レビュー・v9承認済みを意味しない。
