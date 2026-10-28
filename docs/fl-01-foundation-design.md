# FL-01 ローカル開発基盤の設計案

2026-10-28 改訂3。未承認。第2巡の12件と第3巡のMedium 2件・Low 8件を反映した。改訂3の独立レビューは未実施。

## 目的と範囲

MyTimelineと異なるPython/Djangoの構成で、ローカル起動、DB migration、実際に失敗を検出する品質checksを成立させる。認証・筋トレCRUD・画像・交流の実装はFL-02以降。AWSリソースを作成しない。

既存の全体仕様は文脈であり、FL-01で全機能の受け入れを宣言しない。今回公開するのは既存契約のhealth 2本だけ。未実装APIの成功応答を作らない。設計段階でOpenAPIのready 503にもX-Request-Idの宣言を補い、既存共通契約と整合させる。bootstrapでは契約原本を変更しない。

## 採用提案

- React / TypeScript / Vite。Node 24系、npm、ESLint、TypeScript、Vitest、Testing Library。
- Python 3.13系、Django 5.2 LTS、Django REST framework 3.16系、Django ORMとmigrations。uv、Ruff、mypy＋django-stubs、pytest＋pytest-django。
- PostgreSQL 17系。FL-09のRDSも17系を採用する前提とし、提供状況はFL-09で公式情報を再確認する。メジャー変更が必要ならローカル側も同時に変更し、migration・互換性を再検証する。SQLiteへ代替してDB検証を成功扱いしない。
- アプリとDBはDocker Composeで起動する。ローカル限定のCompose project名はfitlog-dev。DBはホストへ公開しない。API 127.0.0.1:18080、frontend 127.0.0.1:15173を提案し、使用前に占有確認する。他プロジェクトを停止しない。
- Python/Nodeのベースイメージ、PostgreSQLイメージ、uvは生成時に取得できるサポート中の具体版とdigestへ固定する。Python依存はuv.lock、JS依存はpackage-lock.jsonへ固定。現時点では未インストールで、パッチ版の解決・互換性確認は生成後のverifyで行う。
- 画像ストレージのローカル実装はFL-05で決定する。FL-01に不要なS3互換コンテナを導入しない。AWSの構成・予算はFL-09の前に別途確定する。

DjangoとPythonの対応根拠：[Django公式](https://docs.djangoproject.com/en/5.2/faq/install/)。DRFとの対応根拠：[DRF公式](https://www.django-rest-framework.org/community/3.16-announcement/)。依存解決が不成立なら別構成へ黙って変えず、失敗として報告する。

## 構成と将来の認証への境界

backend/config/に設定・URL・WSGI、backend/common/にhealthと共通API応答、backend/accounts/にカスタムUserモデルと初回migrationを配置する。Djangoの最初のmigrationより前にAUTH_USER_MODELを設定する。UserはAbstractUserを基礎とし、idをUUIDField(primary_key=True, default=uuid.uuid4, editable=False)で明示する。UUIDを文字列形式のAPIとDB保存・再取得の両方で検証し、整数主キーから後で切り替えない。usernameはAbstractUser由来の一意制約を保つ。emailの正規化・一意制約、表示名・bio等の属性、認証APIはFL-02で追加migrationとテストを用意する。FL-01はユーザー登録APIを公開せず、email非一意のまま登録を許可しない。

frontend/src/は基盤の状態表示だけを実装する。Viteの/apiをbackendへproxyし、ブラウザから同一オリジンでアクセスする。将来のDBセッション認証とCSRFを前提にし、トークンをlocalStorageへ保存しない。モックの既存画面は参照資料として保持し、本物の機能と混同しない。

GET /api/health/liveはDBを問い合わせず200、bodyは{"status":"ok"}。GET /api/health/readyは実DBへのSELECT 1成功かつMigrationExecutor.migration_planの未適用一覧が空の場合だけ200で同bodyを返す。DB接続失敗または未適用migrationありは503、bodyは{"status":"unavailable"}。DB確認は設定した接続・statement timeoutで有界とし、内部の失敗理由を応答へ含めない。テストではDB照会箇所へOperationalErrorを注入し、共有DBを停止しない。migration未適用の注入も独立に検証する。実際にDBを停止する確認はFL-08の専用環境で扱う。

connect_timeoutは全DB接続に5秒を指定する。statement_timeoutは全体設定にせず、readyのtransaction.atomic内でSET LOCAL statement_timeout='2000ms'を設定し、SELECT 1とmigration照会だけへ適用する。失敗はatomicの外で捕捉して503へ変換し、通常クエリ・migrateへ短いtimeoutを残さない。liveからDBへアクセスしないこともテストする。

全API応答にX-Request-Idを付与する。今回は外部からの同名ヘッダーを一切採用せず、各リクエストでサーバーが新しいUUIDを生成する。/api/配下の未実装ルートを含む404はJSON Error(code=NOT_FOUND, message, requestId)、想定外500は同形式のINTERNAL_ERRORを返す。requestIdは応答ヘッダーと一致させる。DEBUGの有無にかかわらずAPIをHTMLへ戻さない。メッセージは固定の非機密文言とし、例外本文、接続情報、秘密を応答・ログに出さない。DRF例外とURL未解決の両方を共通契約へ揃え、500のテストではクライアントの例外再送出を無効にして実応答を検査する。

DRFのカスタムexception handlerは下表の既知例外を共通Errorへ変換する。JSONRendererだけを有効にし、406でもレンダラー未選択に依存せずJSONを返せるよう境界でJsonResponseを使う。Allow・WWW-Authenticate・Retry-After等の該当ヘッダーは失わない。未解決の/api/ルートは末尾のcatch-allでJSON404、未知例外はmiddlewareのprocess_exceptionでJSON500とする。Djangoが先に変換したHTMLの400/403/404/500もAPI境界のresponse処理で対応する固定codeへ正規化し、既に共通形式のJSONを返した場合は内容を上書きしない。DEBUG=True/Falseの両方で確認する。

| 例外・入力 | HTTP | code |
|---|---|---|
| ParseError / ValidationError / Djangoの不正リクエスト | 400 | VALIDATION_ERROR |
| NotAuthenticated | 401 | AUTH_REQUIRED |
| AuthenticationFailed | 401 | INVALID_CREDENTIALS |
| PermissionDenied / Django PermissionDenied | 403 | FORBIDDEN |
| 識別済みCSRF拒否 | 403 | CSRF_FAILED |
| NotFound / Http404 / 未実装API | 404 | NOT_FOUND |
| MethodNotAllowed（例：healthへPOST） | 405 | METHOD_NOT_ALLOWED |
| NotAcceptable | 406 | NOT_ACCEPTABLE |
| UnsupportedMediaType | 415 | UNSUPPORTED_MEDIA_TYPE |
| Throttled | 429 | RATE_LIMITED |
| 上記で処理しない未知例外・500 | 500 | INTERNAL_ERROR |

healthの正常なreadiness拒否503は既存Health形式を保つ。画像固有のINVALID_IMAGEとは別に、405/406/汎用415のcodeをOpenAPIへ設計段階で追加する。認証API・CSRF検査本体はFL-02とし、FL-01では共通handlerの例外変換をunitで確認する。許可しないメソッドのテストではPOST /api/health/liveが405・共通Error・X-Request-Id・Allowを返すことを照合する。[DRF例外仕様](https://www.django-rest-framework.org/api-guide/exceptions/)をHTTP分類の根拠とする。

compose.yamlはpostgresのhealthcheck、依存の起動待ち、backend/frontendのbuildと起動を定義。開発用パスワードはローカル専用と明記し、実認証情報を保存しない。env.exampleは変数名と非秘密のサンプルだけ。volumeの削除は通常の停止から分離し、既存データを黙って破棄しない。

DjangoはDJANGO_SECRET_KEYを必須環境変数とし、空・未設定なら起動失敗。DEBUGの既定値はfalse、DJANGO_DEBUGで明示する。ALLOWED_HOSTSのローカル値はlocalhost、127.0.0.1、backendとし、任意ホストを許す*は使わない。Composeの開発設定には「ローカル専用・秘密ではない」と明示したキーを環境変数として渡し、本番利用を禁止する。env.exampleは非秘密のプレースホルダーだけとする。未設定での失敗とDEBUG両モードは設定テストで検証する。

初版ではソース・venv・node_modulesをhostからbind mountしない。buildでコードとlockをイメージへCOPYし、Python環境はUV_PROJECT_ENVIRONMENT=/opt/venv、Node依存はコンテナ内/app/node_modulesに置く。uv sync --lockedとnpm ciでlockとの不整合を失敗にする。各.dockerignoreで.venv、node_modules、cache、.env等を除外する。コード・lock変更後は必ず再buildして検証し、host上の依存を書き換えない。

この開発用backendイメージのbuildではdev groupを含めてuv sync --lockedする。checkのuv runには--frozen --no-syncを指定し、起動時の依存取得・環境同期をしない。開発ツール不足はcheck失敗となり、verify中にインストールして補わない。

build contextはリポジトリroot、Dockerfileはbackend/Dockerfileとfrontend/Dockerfileを使う。対応するDockerfile.dockerignoreを各ディレクトリに作成し、必要なコードとlockだけを含め、backendには正本docs/api/openapi.jsonを/app/contracts/openapi.jsonへ読み取り用にCOPYする。これにより、コンテナからhostのdocsをmountせず正本との照合を行う。Gitや個人設定・envファイルはbuild contextの送信対象から除外する。

checksはすべてcompose run --rm --no-depsを使う。verify前にfitlog-devのpostgresだけを明示的に起動してhealthyを確認し、backend/frontendのdevサーバーはchecksのためには起動しない。runに--service-portsを渡さないため、devサーバー稼働中でも新たなhost portを確保しない。終了時は今回起動したpostgresだけをstopし、もともと稼働中なら停止しない。通常停止にdown -vは使わず、DBを保持する。フロントcheckはDBなしでも動く。

frontendはready APIを表示対象とする。初期表示「確認中」、200かつstatus=okで「利用可能」、503かつstatus=unavailableで「準備未完了」、ネットワーク失敗で「接続できません」、不正なstatus/bodyやその他のHTTPで「応答を確認できません」。状態表示はrole=statusの単独要素とし、DOMの文言を独立オラクルにする。loading中やエラーを成功表示しない。

fetchはAbortControllerで5秒を上限にし、timeoutも「接続できません」とする。unmount時もabortし、終了後の表示更新を行わない。fake timersによるtimeoutとunmountのテストを追加する。

RuffはE4/E7/E9/F/I/B/UPを選択する。mypyはstrict=true、mypy_django_plugin.mainとDjango settings moduleを設定し、migrationの必要最小限の例外だけを個別に理由付きで扱う。製品コード全体の除外は禁止する。

## 生成とチェックの順序

1. ハーネスのmain 308a7f0（PR #7）で導入されたschema 10のFL-01 workflowでClaudeのdesign_reviewを実行。これはDesign Gateの独立レビューを兼ね、別の設計レビュー席は予約しない。docs/v9-preparation.mdの旧制約は改修前の調査記録である。
2. レビュー結果を添えて本設計と予定checksを提示し、仕様・計画の正式な承認へ進む。Issue作成は具体的な内容の承認後。
3. bootstrapはbackend/、frontend/、compose.yaml、env.example、.ai-dev/checks.proposed.tomlだけを生成。source、manifest、plan、project.toml、Git、hookは変更しない。checksを実行せず生成成功を品質合格にしない。
4. 実在する定義と予定内容をconfigure-checksで照合して登録し、計画を再承認。verifyの先頭に登録したcompose-build checkでdocker compose --project-name fitlog-dev -f compose.yaml build backend frontendを必ず実行する。build失敗なら後続checkを実行せず不合格。下記のDB準備を行った上で、providerを起動しないverifyで全11 checksを実行する。
5. 実装結果承認、Claude品質レビュー、レビュー結果承認を経てcommit・push・PR。mergeはユーザーが行う。

DB起動・待機・後片付けはverifyを起動するCodexが担当し、backend/README.mdにも同じ手順を記載する。開始前にdocker compose --project-name fitlog-dev -f compose.yaml ps --all --format json postgresを読み、Stateがrunningだったかをメモリ内に保持する。不明・複数・restarting等の状態なら勝手に止めず調査する。次にdocker compose --project-name fitlog-dev -f compose.yaml up -d --no-recreate --wait --wait-timeout 60 postgresを実行し、終了コードとpsのState/Healthを確認する。待機失敗ならverifyを開始しない。開始前が停止または未作成だった場合だけ、成功・失敗にかかわらずfinallyでdocker compose --project-name fitlog-dev -f compose.yaml stop postgresを実行する。開始前にrunningなら停止しない。検証中の別セッションによるCompose操作を禁止し、競合が見つかったら停止処理を控えて報告する。

compose.yamlのbackend/frontendはFitLog専用の固定image名を使う。verifyの後にdocker image inspect --format '{{.Id}}' fitlog-dev-backendと同frontendで使用イメージIDを取得し、compose-buildの成功結果・実行対象snapshotとともに検証記録へ残す。check間にコード・lock・イメージタグを変更しない。build自体は登録checkなので、省略して古いイメージのままverifyを成功させる経路にはしない。

## 受け入れ条件と独立したオラクル

- FL01-AC1：pytest-djangoが初回作成する新しいPostgreSQLテストDBへmigrationを適用。test_foundation.pyでcall_command('migrate', interactive=False)を再実行し、前後ともMigrationExecutorが未適用migrationなしと判定することをassertする。UserのidがUUIDであることと保存・再取得の一致を確認する。makemigrations --check --dry-runが変更なしで成功。開発用DBへのmigrateも登録checkで実行し、初回の空DB確認と既存データがある場合の適用を区別して証跡に残す。既存volumeを空DBと偽らず、冪等性の必須オラクルは隔離テストDBとする。
- FL01-AC2：liveのDB非依存、readyの実DB照会とmigration確認、接続失敗・未適用時の503を検証。全health応答のbodyとX-Request-Id、未知APIのJSON404、想定外のJSON500と機密非露出、healthへのPOSTの405を確認。DEBUG両モードのJSON404/500と例外分類表のunitも検証。全体の未実装APIが成功しない。API契約はbootstrapの前に固定し、pytestから読み取り可能な形でイメージへ含める。
- FL01-AC3：frontendのready APIの読み込み・成功・503・通信失敗・不正応答・5秒timeoutを上記のroleと文言で区別し、DOMをassertする。unmount後の更新を防ぐ。fetchモックの呼出しだけをassertionにしない。
- FL01-AC4：Ruff、mypy、Django system check、migration drift、PostgreSQL上のpytest、frontend lint・typecheck・Vitest・buildが全て成功。対象コードの包括ignore、常に成功するcheck、テスト0件、skipによる代用を禁止。
- FL01-AC5：lockを固定してComposeを再build・起動できる。hostの既存Python環境の書換えを要しない。devの起動停止、チェック前のbuild、DBへのmigration、隔離テストDB、今回起動したサービスだけの停止をbackend/README.md・frontend/README.mdに記載する。

予定checksの正本は.ai-dev/fl-01.plan.json。実check定義はbootstrapで初めて作成する。生成前にはexecution_ready=falseが正しい。通常のunitテストにDB migration・healthの結合テストを含める。製品全体のE2EとAWS上の検証はFL-10/FL-09であり、今回の完了根拠にしない。

入力形式は仕様manifestがschema 9、実行plan/workflow/jobがschema 10、project.tomlがschema 1で正しい。名称がv9でもmanifestまで10へ変更しない。ハーネスのdocuments/v9/first-project-workflow.mdと実入力validatorで確認済みである。

## 保存対象の注意

既存のハーネス導入物・仕様草案・モックは未コミットのまま存在する。bootstrapはこれらを変更しない。Git proposalを作る前に、既存ファイルと今回生成したファイルを区別した全対象一覧を提示する。別タスクの変更を黙って巻き込まない。今回の仕様承認は既存の全ファイルをcommitする包括承認ではない。
