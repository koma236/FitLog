# FL-09B4 ECS/RDS・秘密参照・RDS CA（承認済み）

2026-11-06、ユーザーが設計・独立レビュー結果・source revision修正・実装計画を「はい、承認します。進めてください。」と承認。Issue #44、実装branch `feat/fl-09b4-runtime-44`。

## 目的と作業境界

FL-09B2/B3のVPC・SG・ECR・IAM・CloudFront/ALBへECS FargateとRDS PostgreSQLの構成定義を接続する。秘密はTerraformへ渡さずECS起動時に参照し、production imageへ公開RDS CAを同梱する。成果物はIaC、公開CA、ローカル検証、文書。

実AWSのplan/apply/destroy/import、資格情報探索、image push、秘密の生成/投入、DB初期化/migration/seed、公開/撮影は含めない。Terraform CI組込みは別の後続タスク。今回の合格は稼働や公開完了を示さない。

- worktree `/Users/saki/.codex-personal/worktrees/277b/FitLog`、準備branch `prep/fl-09b4-design`、baseline `a7f912ccf970379994cd416f132d8b29fe27f103`（PR #43統合後）。
- writerは親セッションのみ、独立レビューは読取りのみ。設計中は共有Compose/DB/imageへ触れない。承認後Issueを作成し `feat/fl-09b4-runtime-<issue>` へ改名する。他worktreeの変更はしない。

## 承認を求める判断（親の提案）

1. Fargateはpublic subnet＋public IP＋IGW。既存app SGでALB SGから8000だけ受信する。private subnet＋NAT/endpoint案は資源数・費用が増えるため初版では採らない。public IPへの直接受信拒否は後続の実AWS検証が必要。
2. RDSは非公開Single-AZ、db.t4g.micro、gp3 20GiB、暗号化、PostgreSQL 17系（ローカルとmajorを合わせる）。短期デモ向けで、冗長化/自動scaleは含めない。
3. RDS管理者passwordはRDS管理、アプリは別の非管理者DB roleと専用Secrets Manager secretを使う。Web taskへ管理者資格を渡さない。
4. 公開RDS東京CA bundleを取得・hash固定してimageへ同梱する。起動時downloadやシステムCAへのfallbackは追加しない。
5. serviceは既定0 task、proxy信頼も既定無効、CloudFrontは引き続き既定無効。フラグは経路検証の証拠とは扱わない。
6. RDS削除保護とfinal snapshotを有効にする。後続の破棄承認時に保護解除、snapshot/backup/secretの残存と費用を扱う。

## 入力と互換性

Terraform 1.15.1 / AWS provider 6.71.0 / 東京 / expected account境界を維持。追加providerなし。既存入力を維持し、以下を追加（nullable=false）。

| 入力 | 契約 |
|---|---|
| backend_image_digest | 必須。小文字 `sha256:`＋64桁hexのみ。既存ECR repository URLと連結し、別repo/tag/latestは受け付けない |
| backend_source_revision | 必須。imageのビルド元Git commitの小文字hex40桁。FITLOG_APP_VERSIONへ渡す。digestとは別の値。後続の配置で成果物とcommitの対応を確認する |
| postgres_engine_version | 必須。`17.<minor整数>` の完全版。17単体/他majorを拒否。東京の提供状況・class/CA対応は後続実操作前に公式APIで照合する |
| db_final_snapshot_identifier | 必須。環境名＋`-final-` prefix、RDSの英字始まり/英数字hyphen/最大255/末尾・連続hyphen不可。破棄前に未使用名へ更新する |
| enable_backend_service | bool、既定false。desired_countを0/1に限定 |
| enable_proxy_trust | bool、既定false。trueのときだけproxy/header信頼を有効化 |

`enable_public_distribution=true` はservice/proxyフラグがともにtrueでなければpreconditionで拒否する。これは今回追加する構成条件。既存の公開trueテストへも前提を供給する。閉じたSG、S3/IAMの既存契約は維持する。

## RDSの契約

`database.tf` にDB subnet group（既存DB subnet2つ）、parameter group（postgres17、rds.force_ssl=1、apply_method=pending-reboot）、DB instanceを定義する。

- identifier=環境名、db_name=fitlog、username=fitlog_admin、port5432、engine=postgres、engine_version=入力。auto_minor_version_upgrade=false、allow_major_version_upgrade=false。後続の稼働前に保守版を確認する。
- class=db.t4g.micro、multi_az=false、gp3/20GiB、storage_encrypted=true（既定AWS管理RDS key）、storage autoscalingなし。
- publicly_accessible=false、既存database SGだけ、DB subnet groupだけを使用。AZはそのsubnet group内でAWS選択。public subnet/外向きroute/追加受信なし。
- manage_master_user_password=true、password/password_woなし。管理secretのmetadataだけ参照し値を取得しない。独自KMS key指定なし。
- ca_cert_identifier=rds-ca-rsa2048-g1。RDS address（DNS）をPOSTGRES_HOSTへ渡す。
- backup_retention_period=1、delete_automated_backups=false、deletion_protection=true、skip_final_snapshot=false、final_snapshot_identifier=入力、apply_immediately=false。enhanced monitoring/Performance Insights/SQLログexportは追加しない。
- outputsはDB identifier/address/port/nameと管理secret ARN（値なし）。削除時の管理secretのAWS挙動とsnapshot/backupの残存確認は後続で具体化する。

## 秘密とDB roleの分離

`secrets.tf` は `${environment_name}/application` のsecret本体だけを定義。既定AWS管理Secrets Manager key、recovery_window_in_days=7。secret version/data source、random password、plaintext入力/outputは追加しない。

JSONの必須keyは `DJANGO_SECRET_KEY`、`AUTH_RATE_LIMIT_HMAC_KEY`、`POSTGRES_PASSWORD`。ECS secrets.valueFromは各keyを `:KEY::` suffix（AWSCURRENT既定）で参照。長さ/相違等は既存production設定も検査する。execution roleへこのapplication secret完全ARNのGetSecretValueだけを追加し、RDS管理secret読取りは許可しない。Web task roleは既存media S3権限だけを維持し、Secrets Manager/SSM/KMS/DB管理権限を追加しない。既存ECR/log/media policyを弱めない。

後続配置の必須工程：一時管理経路でRDS管理secretを使い、非管理者LOGIN role `fitlog_app` を作成する。SUPERUSER/CREATEDB/CREATEROLE/BYPASSRLS/REPLICATIONを与えず、fitlog DB内のアプリschemaとmigrationに必要な所有権/作成権に絞る。同じpasswordをapplication secretへ安全に投入し、Django/HMACの別の秘密も投入する。管理経路/SQL/権限実証は後続で設計し、Web taskの管理者化で代用しない。未実施のservice起動/ready失敗を完了扱いしない。

secret更新だけで既存taskの環境変数は更新されないため新taskへ置換する。processから読めるsecretをenv dump/log/debugへ出さない。7日削除待ちのsecretの再作成名衝突/課金は後続destroy/rebuild計画へ記録する。B3のorigin secretは引き続きstate/planへ含まれ得るため保護する。

## ECSとALB接続

`runtime.tf` に専用cluster/task definition/serviceを定義。

- FARGATE/awsvpc/Linux X86_64/platform1.4.0/CPU256/memory1024MiB、Spotなし。backend container1個、essential=true、HTTP8000、既存ECR＋digest。command/entrypoint上書きなし、既存Gunicorn/非rootを維持。privileged/host volume/静的AWS keyなし。ECS Exec無効。既存task/execution roleを分離して使用。
- public subnet2つ＋既存app SGのみ、assign_public_ip=true。target登録はserviceが所有（既存IP target group、backend/8000）。target attachmentは追加しない。
- desired_count=0/1、minimum100%/maximum200%、circuit breaker enable+rollback、health grace60秒。autoscale/ignore_changes(desired_count)なし、wait_for_steady_state=false。applyは配置成功を意味しない。
- healthは既存ALBのDB非依存live/200を使いcontainer healthcheckは追加しない。readiness/未適用migration/S3と負荷・低速upload/worker終了は後続で実証する。
- serviceはlistener/転送rule、public routing、全SG exclusive rule set、task/executionのIAM policyへdepends_onを張る。起動前の完成とservice削除までの存続を確保し、実グラフで循環/欠落を検査する。
- awslogsは既存group/東京/stream prefix backend、create-groupなし、mode=non-blocking/max-buffer-size=4m。既存SafeFormatter/access log無効を維持。buffer枯渇時のログ欠落可能性は残る。

environmentは以下の完全な集合とし、secretの名前と重複しないことを検査する。

| 名前 | 値 |
|---|---|
| DJANGO_SETTINGS_MODULE / FITLOG_ENV / FITLOG_LOG_FORMAT | config.production / production / json |
| FITLOG_APP_VERSION | backend_source_revision（ビルド元Git commitのhex40桁） |
| FITLOG_PUBLIC_HOST | 自distribution.domain_name |
| PRIVATE_MEDIA_BACKEND / PRIVATE_MEDIA_BUCKET / PRIVATE_MEDIA_EXPECTED_OWNER | s3 / 既存media bucket / expected_account_id |
| AWS_REGION | ap-northeast-1 |
| POSTGRES_HOST / POSTGRES_PORT / POSTGRES_DB / POSTGRES_USER | RDS address / 5432 / fitlog / fitlog_app |
| POSTGRES_SSLROOTCERT | /app/certs/rds-ap-northeast-1-bundle.pem |
| FITLOG_TRUST_PROXY / FITLOG_AUTH_CLIENT_IP_SOURCE | proxyフラグfalse: 0/remote_addr、true: 1/cloudfront |

SDK role credential chainを使用しaccess key/profile/endpointを渡さない。後続の制限した配置検証で両API behavior、SG、専用proto/IP header上書き、ALB/task直接・別distribution経由の拒否を確認し、実URL共有前に実証する。B3承認済みのCloudFront→ALB→taskのHTTP区間は維持する。

## CAとローカル実証

実装時にAWS公開HTTPS `https://truststore.pki.rds.amazonaws.com/ap-northeast-1/ap-northeast-1-bundle.pem` から取得し、`backend/certs/rds-ap-northeast-1-bundle.pem` と取得日/URL/SHA256を記録する。公開certificateだけでprivate keyなし。PEM parse/CA属性/期限/東京RSA2048 G1の包含/self-signed rootを確認しhash固定する。これはTLS取得物の固定値であり、事前に既知の公式checksumとは呼ばない。

Dockerfile.productionは同梱物のSHA256を検査し、build/起動時に再downloadしない。既存COPY backend/で収録できる。production_smoke.pyのCA pathを同梱物へ更新し、network=noneでCA読取り/非root/Gunicorn/live/Host/ログ非漏洩/SIGTERMを確認する。

`backend/tests/production_tls_smoke.py` で一時的なテストCA/server証明書を作り、Composeと同じdigest固定PostgreSQL imageの専用container・専用internal network（host portなし）へproduction imageのpsycopgから接続する。verify-fullで正しいCA＋SAN一致DNSは成功、異なるCAとSAN不一致DNSはcertificate原因で失敗する。DB資格は公開fixture。TLS使用を検査し、単なる接続拒否を負例成功にしない。自分のcontainer/network/tempだけfinallyで除去する。これは公開RDS CA/実RDS接続の実証を代替しない。

## 検証と受け入れ条件

Highリスク（認証信頼経路/IAM/秘密/DB保全）。実装前test-designで独立oracle/反証入力を記録しTDDで進める。

1. mock plan（全run aws mock/override_during=plan/command=plan）でRDSの非公開/SG/subnet/暗号化/major/force_ssl/CA/backup/削除保護/管理secretを固定値と比較。password/secret version/secret値取得なしも構成検査する。
2. ECS JSONをdecodeしdigest URL、roles/network/port/全environment/全secret参照/log/0⇔1/rollout/Exec無効を独立期待値と比較。IAM全Statementを検査し、管理secret/secret値のWeb task混入なしを確認する。
3. null/不正digest/タグ/不正source revision/別major/不正snapshot名を拒否。service/proxy/public全8組を検査（public=trueでserviceまたはproxy=falseを拒否、他は構成として許可）。既存B2/B3へ新必須入力と公開前提を追加し境界の期待値を緩めない。
4. 資格情報なしの実terraform graphでservice→routing/SG/IAM/listener依存と循環なしを確認する。
5. CAのhash/PEM/期限/東京root、image同梱/利用、production smoke、ローカル実PostgreSQL TLS正負例を確認。production smokeにはsource revisionのfixtureを渡しログのapp_versionがunknownにならずそのcommitと一致することも確認する。既存Django verify-full testを維持する。
6. Terraform fmt/init(-backend=false、lockfile readonly)/validate/test、Function test、ゲート回帰、登録11 checksを実施。TerraformはREADMEのenv -i方式。image/DBの検証は個人run-checks手順と共有runtime排他に従い、自分の起動資源だけ停止する。

主変更範囲：`terraform/{database,secrets,runtime,iam,variables,outputs,edge}.tf`、同tests/README、`backend/Dockerfile.production`、`backend/certs/`、`backend/tests/production*_smoke.py`、今回設計/本番準備/インフラ/進捗文書。networkは必要な依存表現に限り変更可。API/認証ロジック/schema/Compose/依存lock/CI/ハーネス/11 checks登録は変更しない。

## 短い実装計画と体制

1. 承認後Issue/番号付きbranchを整備。test-designを先に作成し、親が直接実装する。
2. RDS/Secrets/IAMのmock負例/固定期待値を追加し失敗確認後に定義。続いてECS/公開条件/依存グラフを同様に追加。
3. 公開CAを取得/検査/固定しimage同梱。production/TLS smokeを追加し排他下でbuild/正負例を検証。文書を更新。
4. Terraform/ゲート/登録11 checksのsnapshot・日時・終了コードを保存。機械検証後quality-check（統合/反証QA/Security）でHighを対応し追加テストを判断。
5. account/repo/SSH照合後commit・feature push・PR作成。認証信頼設定/DB権限境界を構成するため手動相互レビュー対象として「相互レビュー待ち」で止める。対象PRへの対応指示後、再検証と通常merge条件へ進む。実AWS反映はしない。

設計レビュー1体（Sol/high）、実装委譲0体、品質初回3体（Astra/high）が目安。追加巡は規定内でHighが出た場合だけ。料金/予算承認とは別。計画は本書と一体化する。

## 原典（2026-11-06照合）

- [ECS public subnet/IGW](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/networking-outbound.html)
- [ECS JSON keyによるsecret注入・platform・更新](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/secrets-envvar-secrets-manager.html)
- [RDS管理password](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-secrets-manager.html)、[PostgreSQL SSL](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL.Concepts.General.SSL.html)、[CA/region bundle](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html)
- provider6.71.0 [DB](https://github.com/hashicorp/terraform-provider-aws/blob/v6.71.0/website/docs/r/db_instance.html.markdown)、[serviceとIAM依存](https://github.com/hashicorp/terraform-provider-aws/blob/v6.71.0/website/docs/r/ecs_service.html.markdown)、[task](https://github.com/hashicorp/terraform-provider-aws/blob/v6.71.0/website/docs/r/ecs_task_definition.html.markdown)

## 独立設計レビュー

2026-11-06、helm-doc-reviewer（gpt-6.1-sol/high）の読取りレビュー1体。High 0件、Medium 0件。依存方向、secret/role分離、provider6.71.0のRDS保全、必須production設定とCA/TLS検証、後続実証の境界に具体的な欠落・矛盾なし。テスト/実AWS/GitHub操作は行っていない。

予約marker `HELM_REVIEW:f80fe40b8e6bb10718170cc57bb43c8a:document-reviewer`。design 1/1枠を使用し、起動前後にused/receiptとagent記録を確認した。個人CODEX_HOMEを指定したcodex-trustの結果はok。

レビュー後の親による追加修正（再レビュー未実施）：初稿のFITLOG_APP_VERSIONはdigestのhex64桁だったが、`docs/10_logging_design.md:9` はGit commit、`backend/common/observability.py:94` は7〜40桁のみ許すため、そのままではログがunknownになる。必須入力backend_source_revision（Git commit40桁）を分けて追加し、environment・不正入力検査・production smokeのログ照合へ反映した。imageは引き続きdigestで固定する。この修正を含む設計への承認を求める。

## 実装時の差異

1. 設計のnull拒否の記述を具体化：必須4入力のnull/欠落は拒否する。一方、既定falseのservice/proxy/publicフラグは、承認したnullable=false/default=false指定を維持するとTerraform自身が明示nullをfalseへ置換する。この安全側の既定動作を維持し、nullで起動/信頼/公開が有効にならないことをmockで検査した。入力のnullを一律エラーとする期待からの差異として記録する。[Terraform変数仕様](https://developer.hashicorp.com/terraform/language/block/variable#nullable)と実診断で照合した。必須入力のnullを許可する変更ではない。
