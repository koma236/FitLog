# FL-09B6 秘密値・DBロールの初期化（承認済み）

## 目的・境界

ユーザーは2026-11-06に次の開発対象として「本番用の秘密値・DBロール初期化」を選択した。2026-11-06、Claudeレビュー反映版をユーザーが「はい、承認します。実装を進めてください。」と承認。Issue #48、branch `feat/fl-09b6-bootstrap-48`。既存B4のapplication secret（値なし）と非管理者 `fitlog_app` の契約を満たす初回専用コマンドを用意する。実AWSの構築・秘密投入・DB変更・公開は実行しない。

親の提案：Django起動前の独立Python module `backend/operations/bootstrap.py`（`python -m operations.bootstrap`）とする。既存psycopg/boto3を利用し、本番依存は増やさない。開発用boto3-stubsは既存s3にsts/rds/ecs/secretsmanager/cloudfront/elbv2のextrasを追加し、backend/pyproject.tomlとuv.lockを更新する。elbv2は既存ALB originの対応照合に必要。既存runtime packageを意図せず更新せず、lock差分と本番依存集合を確認する。strict mypyを維持し、Any/cast/ignoreによる検査回避は行わない。Web起動から呼ばず、Web用task/execution roleへ管理権限を追加しない。実行者用IAM・VPC内runnerの作成/起動は後続のAWS配置設計で扱う。初期化コマンドの存在だけで実AWS初期化完了とはしない。

- cwd/worktree: `/Users/saki/.codex-personal/worktrees/d91e/FitLog`、writerは本セッションのみ。
- branch: `prep/parallel-a`、baseline: `9d9979561fb10573019481208eb1d254da4e6768`。承認後Issueを作成し `feat/fl-09b6-bootstrap-<Issue>` へ改名。
- 並行担当: #46 / PR #47（Terraform CI）。本作業はCI/Terraform/Compose/11 checks登録/ハーネスを変更しない。backendの開発用型スタブとuv.lockは本担当が所有し、他担当との同時変更があれば先行統合後に更新する。共通文書 `docs/task-plan.md` は先行PR統合後に更新するか、本専用文書から参照する。CIの未統合分の成功を流用しない。
- 共有runtime: 既存run-checks/排他運用に従う。設計中はDB/Compose/image操作なし。

## 入力・対象照合

CLIで受け取るのは非秘密metadataだけ：`--expected-account-id`、`--environment`、`--db-instance-identifier`、`--application-secret-arn`、`--distribution-id`、`--operation-id`（UUID）。regionはap-northeast-1固定で入力させない。cluster/service/container名とALB名はenvironmentから既存命名規則で導出し、CLI入力にしない。distribution IDとapplication secret ARNはTerraform outputsから取得する。任意DSN・password・SQL・SDK endpoint/profile指定は受け付けない。確認用read-onlyモードを既定とし、明示 `--initialize` でのみ変更する。read-onlyはSTS/RDS/ECS/Secrets/CloudFront/ELBv2の対象metadata照合だけで、GetSecretValue/秘密値生成/DB接続/変更API呼出しなし。ただしCloudFront応答には既存origin認証headerが含まれる（後述）。

SDK標準role credential chainでSTS accountを照合する。独自endpoint環境変数を無効化し、region東京固定・短いtimeout/有限retryを設定。RDS Describeからaddress/port/DB名/管理username/管理secret ARNを得る（期待identifier/非公開/PostgreSQL17/DB fitlog/管理者fitlog_adminを検査）。application secretは同account/regionの完全ARN・名前 `${environment}/application`・削除待ちでないことを照合。管理secretとは別ARNを要求する。

対応付けは固定する：RDS identifier＝environment名、cluster名＝environment名、service名＝`${environment}-backend`。全リソースの既存Project/Environment tagをTerraform定義と照合する。serviceのtask definitionを取得し、backend containerのPOSTGRES_HOST/PORT/DB/USERが当該RDS/5432/fitlog/fitlog_appと一致し、必須3secret参照が当該application ARNの既存key suffixと完全一致することを要求する。CloudFrontは明示distribution IDのaccount/tagと既存ALB originを照合する。ELBv2で名前 `${environment}-api` のALBを取得しaccount/tagを検査し、そのDNS名とdistributionのapi originドメインが一致することを要求する。別環境との混在を拒否する。API応答にはorigin認証headerも含まれるため応答全体をログやファイルへ出さない。

ECSの `${environment}` cluster内 `${environment}-backend` service、container `backend` を照合し、desired/running/pendingすべて0であること、distributionの公開が無効であることをAPIで確認する。distribution IDはCLIで明示し、serviceは固定命名から導出する。account/environmentとの対応もAPIで検査する。未検証の状態で初期化しない。実行中の配置・秘密変更は運用上禁止し、変更直前にも停止状態を再照合する。これは外部操作を阻止する分散lockではない。CloudFront照合は停止タスクの確認に加え公開入口も閉じていることを確認する目的で維持する。応答から照合に必要なenabled/originドメイン等だけを取り出し、origin認証headerを保持・出力せず応答への参照を速やかに破棄する（Pythonメモリの完全消去は保証しない）。実行者にはこのheaderも読める権限が必要になることを後続IAM設計の明示事項とする。

## 初回処理と再開

1. 対象metadata/停止状態を照合し、管理secretをメモリ内で読む。RDS正本host/5432/fitlog/fitlog_admin、同梱CA/verify-fullで接続し、接続先とTLSを検査する。CLIはPG環境上書きを除去する。
2. session advisory lockをtry取得。競合は変更せず終了し、接続喪失後は再接続しない。未知role/schema/secret状態は拒否する。
3. 初回は空DB・空secretを確認し、管理者専用schemaとoperation_claimを先にcommitする。singleton=trueの1行にoperation UUIDと対象metadataを予約する。claimのみの再開は同UUIDだけ許可。claimなしのsecret-onlyは拒否する。
4. Django/HMAC/DB passwordを独立にsecrets.token_urlsafe(48)で生成。各64字のURL-safe ASCII、3値の相違とproductionの長さ/公開sample拒否を検査する。JSON必須3keyをoperation UUID固定VersionId/AWSCURRENTで保存・読み戻す。未知versionは拒否。同UUIDは保存値を再利用する。
5. role/ACL/完了marker initializationを同じtransactionで作成し、別app接続で実ログインを確認する。claimは保持する。claim/secret/DB commitの結果不明時は現在の実行を失敗終了し、新しい同UUIDの実行で対象・lock・予約を再検証する。
6. 完了済みの同UUIDは変更せずclaim/marker/role/ACL/実ログインを検証する。別UUIDや権限差異は拒否し自動修復しない。全外部処理の前後・秘密書込み直前に予約とlockを検証する。検査直後にleaseを失っても永続予約が別UUIDを拒否し、AWS固定VersionIdの不変性が遅延Putによるpassword上書きを防ぐ。

詳細状態表は[承認済み差異設計](fl-09b6-durable-claim-proposal.md)を正とする。完了markerとrole/ACLのatomicityは維持する。
operation UUIDは非秘密の復旧識別子として出力・記録可。自動rotation/既存秘密の更新、secret削除、既存roleのpassword変更、drop/REASSIGN OWNEDは実装しない。失敗後の秘密残存を完了と扱わず、状態別の再開手順を文書化する。

管理schema `_fitlog_bootstrap` のclaim table `operation_claim` と完了table `initialization` はfitlog_admin所有で、PUBLIC/appのschema/table/列権限を許可しない。claimはsingleton boolean PRIMARY KEY CHECK(singleton)と、operation/account/region/environment/database/secret_arn/versionの7つのtext列。完了tableはoperation text PRIMARY KEYと残り6列。全列NOT NULL、秘密値なし。両行でUUID・対象metadata・VersionIdの完全一致を検査する。

初回はschema不存在、予約後はclaimだけ、完了後は両tableだけを許可する。各PK index・暗黙composite/array type以外のschema内object、table種別/型/制約/行/所有者/列ACL/追加grantの差異も拒否する。claim commitはrole作成前だが、完了markerはrole/ACLと同じtransactionでcommitする。

## 初回の空DB判定

schemaは `pg_catalog`、`information_schema`、`pg_toast`、既定 `public` のみを許可する。PostgreSQL生成の一時schemaは正規形 `pg_temp_[0-9]+` / `pg_toast_temp_[0-9]+` に限定してシステム領域として扱い、任意の `pg_` prefixを一括許可しない。publicの所有者はpg_database_ownerであることを確認する。拡張は既定plpgsqlだけを許可し、未知の拡張・schemaは拒否する。

システムschemaの標準objectおよびplpgsqlの既定objectは空判定から除外する。publicはschemaの存在だけを許可し、中のrelation（table/view/materialized view/sequence/foreign table等）、routine、利用者定義type/domain等のユーザーobjectを許可しない。relationだけの検査で空とせず、pg_class/pg_proc/pg_type等のcatalogと拡張依存を照合する。large object、event trigger、publication/subscription、foreign server/user mapping等のDB単位のユーザー定義物も初回には許可しない。_fitlog_bootstrapは初回は不存在、再開時は上記の状態ごとの既知claim/marker構造だけを許可する。判定SQLと許可リストを明示したテストを作り、publicの関数/typeだけが存在する負例も含める。

これはローカルPG17を起点とした保守的な許可リストであり、実RDSの初期状態と一致するとは断定しない。実RDSで未知objectを検出した場合は変更前に停止する。対象と所有者・拡張依存を調査して許可リストの設計変更と確認へ回し、実行時のskipフラグや自動学習で受け入れない。

## DB権限

既存Djangoの既定public schemaを維持。fitlog DBは管理者所有のまま、fitlog_appはLOGIN/NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NOREPLICATION/NOBYPASSRLS/NOINHERIT、他role membershipなし（RDS/PGによる作成者側の管理membershipとは区別）。DB CONNECTとpublic schema USAGE/CREATEだけを明示許可。初期化transaction内で専用fitlog DBおよびpublic schemaのPUBLIC権限を剥奪する。他DBやtemplate/postgresのACLは変更しない。public schemaの所有者は既定pg_database_ownerのまま。アプリが作成するmigration/table/sequenceはアプリ自身が所有する。

アプリは自分のschema内objectに対してmigration可能だが、DB作成/role作成/管理roleへのSET ROLE/他者所有tableの読取り・変更は拒否する。DB owner権限、schema作成のためのDB CREATE、TEMP、他DBへの明示権限は与えない。PostgreSQL既定PUBLICが他DBへのCONNECTを許す可能性は残り、cluster全体の隔離を主張しない。WebとmigrationのDB roleを分ける追加設計は今回含めない（B4契約）。

SQLは識別子/値をpsycopgの安全なcompositionで渡す。passwordはクライアントでSCRAM verifier化してからDDLへ渡し平文SQLを避ける。verifierも秘密と扱う。SQL/parameter/SDK wire/debug/例外本文/tracebackをログへ出さず固定event・終了code・非秘密operation UUIDだけを出す。repr/dataclassにも秘密を含めない。ログ設定を勝手に弱めず、実RDSのSQL/監査ログ方針確認は実行前条件とする。

## 実装対象・テスト根拠

主対象は `backend/pyproject.toml`（開発用extrasのみ）と `backend/uv.lock`、`backend/operations/`、`backend/tests/test_bootstrap*.py`、専用ローカルsmoke、今回設計と運用手順文書。アプリの認証/API/schema/migration、Terraform/IAM設定、CIは変更しない。新エラーcodeは既存error一覧の規約に沿って記載し、並行担当が同文書を変更する場合は統合後に追記する。

既存Dockerfile.productionのCOPY backend/により管理ツールもWeb用imageへ意図して同梱する。Web起動から実行せず、Webのtask/execution roleに管理資格の取得・秘密書込み権限は与えない。専用imageの新設は今回含めない。

Highリスク。実装前test-designを記録しTDDで以下を確認する。

- boto境界の固定応答/SDK Stubber：account/region/ARN/name/RDS/service/distribution照合、pagination、外部endpoint遮断、read-onlyで値取得/変更なし、停止していない環境の拒否。
- 状態遷移：初回、同UUID再開/検証、異UUID拒否、secret書込み/DB transaction/commit不明/ログイン失敗、同時実行。失敗で別passwordを生成・上書き・削除しない。
- 実PostgreSQL17の独立catalog照合：role属性/membership/ACL、PUBLIC剥奪、appのDDL/DML成功、CREATE DATABASE/ROLE・管理SET ROLE・他者table拒否。実Django migrateをappとして空DBへ適用し全migration成功を確認。独立の専用DB/containerで検証し共有開発DBへbootstrapしない。fixture準備だけをpostgres SUPERUSERで行い、NOSUPERUSER/LOGIN/CREATEROLE/CREATEDB/INHERIT/NOREPLICATION/NOBYPASSRLSのfitlog_adminを作ってfitlog DBを所有させる。bootstrap自体は必ずこの非SUPERUSERで実行する。管理者のCREATEDBは実RDSの属性へ合わせるが、appには付けない。pg_auth_membersで「appが管理roleのmemberでないこと」と「管理者が作成appのADMIN権を持つこと」を方向別に検査する。createrole_self_grantはADMINの自動付与とは別にINHERIT/SETを制御するため、既定空文字とinherit,set指定の両fixtureでappから管理者へ権限が逆流しないことを確認する。rds_superuser固有の挙動はローカルで再現できず、実RDSでの権限実証は後続へ残す。
- TLS正例/CA誤り/SAN不一致は既存TLS smoke方式を再利用。平文passwordとSCRAM verifier・管理secret・Django/HMAC値を故意の例外/SDKエラー/SQLエラーに含めてもstdout/stderrに残らないことを確認する。
- 登録11 checks、ゲート回帰、production image内CLI起動/helpと既存production smokeを排他下で実施。実AWS APIは呼ばずローカル成功と実RDS権限実証を区別する。

## 短い実装計画・承認後の進め方

1. Issue/番号付きbranchを整備しtest-designを作成。親が実装（委譲なし）。
2. 開発用型スタブextrasとlockを更新・差分確認。metadata照合/秘密の初回固定versionと復旧状態遷移をテストして実装。
3. DB transaction/権限/非漏洩と専用PostgreSQL/Django migration/TLS smokeを実装・検証。手順文書を追加。
4. 登録checksと追加検証を保存後quality-check（統合・反証QA・Security、Highを規定内で対応）。commit/通常feature push/PR作成。
5. DB権限/秘密の高リスク変更としてPRを「相互レビュー待ち」にしてマージ前停止。ユーザーの対象PRコメント対応指示後に再検証し通常条件へ進む。実AWS実行は今回承認に含めない。

設計レビュー1体Sol/high、実装委譲0体、品質初回3体Astra/highを想定。設計・レビュー結果・本計画をまとめて承認後に実装する。

## 原典（2026-11-06確認）

- PostgreSQL17 CREATE ROLE: https://www.postgresql.org/docs/17/sql-createrole.html
- PostgreSQL17 schema/既定権限: https://www.postgresql.org/docs/17/ddl-schemas.html
- Secrets Manager初回versionとClientRequestToken: https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_PutSecretValue.html
- 既存契約: docs/fl-09b4-runtime-design.md、terraform/{database,secrets,runtime,outputs}.tf

## 独立設計レビューと解決

2026-11-06、helm-doc-reviewer（gpt-6.1-sol/high）の独立読取りレビュー：High 0件、Medium 2件。

1. 対象リソースの対応付けが未具体化：上記のidentifier/environment一致、tags、ECS task definitionの接続先/secret完全参照、CloudFront origin照合を親の判断で追記した。
2. operation markerの保存契約が未定義：上記の管理者専用schema/table・保存項目・同一transaction・一致条件・appからのアクセス拒否を親の判断で追記した。

再レビューは実施していない。これらの具体化を含む設計と計画をユーザー承認へ提示する。marker `HELM_REVIEW:0c8a48f544ad3489dfb00930be67b0fc:document-reviewer`、design 1/1。最初の起動はbridgeがmessage markerを認識せず拒否し、usedなしを確認後、実装済みbridge ticket形式で起動した。used/receipt/agentの正規記録を確認済み。個人CODEX_HOMEを明示したcodex-trustはResult ok。実装・テスト・実AWS操作は未着手。


## ユーザー提示のClaudeレビューへの対応（承認前追記）

提示結果はHigh 0 / Medium 4 / Low 4。親がコードと公式仕様を照合し、M1〜M4およびL1〜L4を上記へ反映した。追加reviewerは起動していない。

- M1：bootstrapを非SUPERUSERのDB所有者で実行するfixtureとmembershipの方向別検査を明記。ADMINの自動付与とcreaterole_self_grantのINHERIT/SET設定を区別した。実RDS固有の限界は維持。
- M2：schema/拡張/各種ユーザーobjectの許可条件を定義し、未知のRDS初期objectは停止して設計変更へ回す。
- M3：dev extrasとlockを本担当の変更範囲へ追加。本番依存を増やさない方針は維持。既存ALB照合のためelbv2も対象に含める。型スタブ追加は唯一の手段とは限らないが、SDKの公開型を直接使う本設計では採用が適切と判断した。
- M4：CLI入力を列挙し、region/cluster/service/container/ALB名は固定・導出へ統一。
- L1〜L4：CloudFront読取り権限の影響と応答の破棄、生成文字種/相違検査、lock接続切断時の停止、管理ツールのimage同梱を明記。

この追記で実装範囲に開発用依存/lock更新を追加した。まだ設計承認・実装・依存更新・テスト・実AWS操作は行っていない。

追加照合原典：
- RDS管理者の非SUPERUSER属性：https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Appendix.PostgreSQL.CommonDBATasks.Roles.rds_superuser.html
- ADMINとcreaterole_self_grantの区別：https://www.postgresql.org/docs/17/runtime-config-client.html#GUC-CREATEROLE-SELF-GRANT
- boto3-stubsのservice extras：https://youtype.github.io/boto3_stubs_docs/


## 実装時の差異（X4承認済み）

品質初回レビューはHigh4/Medium1。marker列ACL/未知objectの検出漏れ2件、credential chain内部STSへのendpoint上書き1件は修正し、単体・型・専用PG17/production smokeで検証した（独立検証レビューはまだ実施していない）。

H4はDB session lock喪失後の別UUID遅延書込み競合。ユーザーが[永続予約方式](fl-09b6-durable-claim-proposal.md)と追加設計レビュー1回を「はい、許可します」と承認。追加レビューはHigh0/Medium1（結果不明なら現在の実行で秘密を書かず終了し、新しい同UUID実行で再検証する単位へ具体化）。予約tableと状態遷移を実装し、実run経路の応答喪失・lease喪失・遅延Putの両到着順を専用DBで検証した。

元設計との差異は、秘密保存より前にoperation claimをcommitする点と、管理schema内の予約table追加。CLI/秘密JSON/Web IAM/アプリAPI/本番依存/実AWS対象範囲は維持する。品質初回レビュー前の全11 checks結果を変更後の合格として流用せず、再実行と残り品質レビューを行う。
