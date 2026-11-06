# Terraform — FitLogデモ基盤

FL-09B2（Issue #32）で基盤、FL-09B3（Issue #42）でCloudFront/ALB/OAC、FL-09B4（Issue #44、2026-11-06）でECS/RDS・秘密参照・公開RDS CAを構成定義。AWS資源の作成・疎通・実権限評価は未実施。下段の構築・配置・撮影・破棄手順は後続の草案。

## 実装済みの範囲

Terraform **1.15.1**、公式AWS provider **6.71.0**をexact pinし、`.terraform.lock.hcl`でchecksumを固定する。root moduleをnetwork/storage/IAM/outputsに分割し、外部moduleは使わない。[承認設計](../docs/fl-09b2-aws-foundation-design.md)・[全体のインフラ草案](../docs/09_infrastructure.md)参照。

- 東京2AZの専用VPC（10.42.0.0/16）、public /24×2とprivate DB /24×2。publicだけIGWへdefault route。NAT/EIPなし。subnetのpublic IP自動付与なし。
- ingress/app/databaseの専用SG。ingress受信はCloudFront origin-facing IPv4 managed prefix listのTCP80だけ、ingress→app TCP8000、app→DB TCP5432、appのIPv4 TCP443外向きだけを許可。exclusive rule setsで既定の広いegressを残さず、DBからの外向き通信はなし。inline SG ruleとstandalone ruleの所有を混在させない。
- private static/media S3、owner enforced、public access全block、AES256。非TLSの非AWS-service要求を明示拒否する。AWS service principalの例外はアクセス許可を追加しない。staticだけに自distribution ARN限定のCloudFront GetObject grantを付与する。mediaへのgrantはない。
- immutable/scanned/AES256のbackend ECR、7日保存のlog group。自動image削除はしない。
- task roleはmediaのimages/* Get/Put/Deleteとprefix=images/でのListだけ。execution roleは対象ECR取得・registry token・対象log stream書込みとapplication secret完全ARNのGetSecretValueだけ。信頼先は同account/東京のECS task。両roleにDB管理secretの読取り・DB管理・SSM・image書込みは許可しない。

`expected_account_id`（12桁）、`environment_name`（fitlog-demo-から始まる最大24文字）、`availability_zones`（異なる東京AZ2つ）が入力。providerはexpected account以外を拒否する。mockはこの実account照合や実際のAZ提供状況を検証しない。将来実行時には本人の専用account・利用可能AZも確認する。

ECS/RDS・秘密の参照とCA同梱はB4で定義。outputsは識別子・将来用URLとDB/secretのmetadataだけ。distribution無効・service0 taskが既定のためURLは稼働を示さない。実配置・秘密の値投入・DB初期化は後続。**TerraformのCI組込みは実AWS構築前に必要な別タスク**で、現行11 checks/ci-requiredは変更していない。

## FL-09B4のruntime

[承認設計](../docs/fl-09b4-runtime-design.md)が契約の正本。

- FargateはLinux/x86_64・platform1.4.0・0.25vCPU/1GiB。既存public subnet＋public IPで外向き443を使いNATなし。受信8000はALB SGだけ。既定0 task、明示起動時1 task、ローリング時最大2 task。CPU/memoryや実経路の十分性は未実証。
- 非公開RDS PostgreSQL 17系/db.t4g.micro/Single-AZ/gp3 20GiB、暗号化、TLS強制とverify-full、rds-ca-rsa2048-g1。削除保護、1日backup、final snapshot、削除後backup保持を指定。保護解除・snapshot/backup削除と課金停止の実証は別途承認する破棄工程で扱う。
- RDS管理secretはWeb task/executionから読めない。application secretの本体だけを作り、3つのJSON keyを起動時注入する。Terraformへ値を渡さずsecret version/data sourceも作らない。別途、非管理者fitlog_appの作成と同じDB password、Django/HMACの異なる秘密を投入する。未投入でもIaC定義の検査はできるが、task起動は成功しない。
- secret更新後は新taskへの置換が必要。secretはprocessの環境変数から読めるためenv dump/debug/logへ出さない。application secretは削除後7日待機となり、同名再作成衝突と残存費用をdestroy/rebuild工程で扱う。
- 公開CAは[公開物と固定hash](../backend/certs/README.md)をimageへ同梱しbuildでhash検査。起動時download/fallbackなし。ローカルTLS正負例は自作テストCAで実PostgreSQLへ接続する検証であり、実RDSのCA/接続実証は後続。
- serviceはrouting/SG exclusive rules/IAM/listenerの完成と存続を待つ。ALB healthはDB非依存live、readiness/未適用migration/S3確認は別。awslogsはnon-blocking/4mで、buffer枯渇時のログ欠落可能性がある。

追加必須入力は `backend_image_digest`（sha256＋小文字hex64桁）、`backend_source_revision`（ビルド元Git commit40桁）、`postgres_engine_version`（17の完全minor）、`db_final_snapshot_identifier`（環境名-final-から始まる未使用名）。例示17.6はmock fixtureであり東京での提供保証ではない。実操作前にengine/class/CA対応とimageのcommit/digest対応を照合する。

`enable_backend_service` と `enable_proxy_trust` は既定false。public=trueは両方true以外を拒否する。proxy=true時だけproductionの専用proto/IP header信頼を有効化する。必須入力のnull/欠落は拒否し、既定falseフラグの明示nullはTerraform仕様によりfalseへ戻る。これらのフラグを実境界検証の証拠にせず、実URL共有前に両API/偽装拒否/CSRF/Cookie/IPを検証する。

## FL-09B3の公開入口

[承認設計](../docs/fl-09b3-edge-design.md)に従う。`enable_public_distribution` は既定falseで、実公開は後続の実AWS操作承認と検証の対象。

- ブラウザ→CloudFrontはHTTPS限定（HTTPは拒否、redirectしない）。CloudFront既定ドメイン/証明書を使用し、独自ドメイン・ACM・DNSは追加しない。
- CloudFront→ALB HTTP80、ALB→将来task HTTP8000。**この2区間は暗号化しない**短期デモ向け構成。prefix list・秘密headerはアクセス制御でありTLSの代替ではない。
- ALBはpublic2AZ/IPv4、Host保存、default403。`X-Fitlog-Origin-Verify` の秘密一致だけ空のIP target groupへ転送。healthはDB非依存の `/api/health/live` / 200。ECSが未定義なので成功応答は期待しない。
- `/api` と `/api/*` は両方ALBへ全methods・viewer headers（Host/CSRF/IP含む）・Cookie・queryを転送。既存client-ip Functionを両方へviewer-request関連付けする定義を追加した。API originの専用proto headerと秘密headerはviewer値を上書きする。
- defaultはstatic S3のregional REST endpointへGET/HEADだけ。OACはsigv4/always。全behaviorはTTL0・圧縮無効。hash routingを維持し、API errorをSPA HTMLやstatus200へ変えない。
- static policyだけにdistribution限定GetObjectを追加。既存非TLS拒否とmedia非公開は維持。policyとSG ruleは既存所有者のまま拡張する。

新たな必須入力 `origin_verify_secret` は小文字hex64桁、nullable=false、sensitive=true、既定なし。ALBのwildcardを含む値は拒否する。今回のtest fixtureは公開の架空値で、実値を生成/取得していない。実操作時に別途生成し、Git除外・権限制限したtfvars等から供給する。**secretはstate/保存planとAWS構成へ入り得る**。sensitive指定は暗号化ではないため、それらの保管・バックアップを保護し、plan JSONやstateを公開しない。secretをoutputしない。

AWS管理prefix listのweightは55で、TCP80の1ポートだけに適用する。実操作前に東京のprefix listとSG quotaを確認する。別distribution・ALB/task直接経路の拒否、実ヘッダ上書き、Cookie/CSRF/利用者IPは、ECS/RDS等を整えた後に実AWSで検証する。

## AWSへ接続しないローカル検証

リポジトリrootで実行する。`init`は公式Registry/配布元からpluginを取得するためネットワークが必要。`validate`/`test`はローカルpluginの起動権限が必要だが、AWS資格情報を渡さない。`TF_CLI_CONFIG_FILE`も空にし、個人・会社のprovider上書き設定を読み込ませない。

```sh
terraform -chdir=terraform fmt -check -recursive
env -i PATH="$PATH" CHECKPOINT_DISABLE=1 TF_CLI_CONFIG_FILE=/dev/null TF_IN_AUTOMATION=1 AWS_EC2_METADATA_DISABLED=true AWS_SHARED_CREDENTIALS_FILE=/dev/null AWS_CONFIG_FILE=/dev/null terraform -chdir=terraform init -backend=false -input=false -lockfile=readonly
python3 -B -m unittest discover -s terraform/tests -p 'test_*.py'
env -i PATH="$PATH" CHECKPOINT_DISABLE=1 TF_CLI_CONFIG_FILE=/dev/null TF_IN_AUTOMATION=1 AWS_EC2_METADATA_DISABLED=true AWS_SHARED_CREDENTIALS_FILE=/dev/null AWS_CONFIG_FILE=/dev/null terraform -chdir=terraform validate
env -i PATH="$PATH" CHECKPOINT_DISABLE=1 TF_CLI_CONFIG_FILE=/dev/null TF_IN_AUTOMATION=1 AWS_EC2_METADATA_DISABLED=true AWS_SHARED_CREDENTIALS_FILE=/dev/null AWS_CONFIG_FILE=/dev/null terraform -chdir=terraform test -no-color
```

全test runは`command=plan`、`mock_provider aws`を使う。共有mockは`tests/mocks/*.tfmock.hcl`にcomputed ID/ARN/DNSだけを置く。mockと個別のID/ARN overrideには`override_during=plan`を設定する。実policy JSONは`jsonencode`で生成し、全Statementを独立した期待値と比較する。policy自体をmockへ置換しない。テストfixtureのaccount `123456789012` は架空値。mockを誤って外しても、上の最小環境はprofile/role/OIDC/container資格情報を引き継がず、共有credential/configとmetadataを探索しない。

mock成功はAPI可用性・AWSでのIAM評価・SG疎通・account照合・課金の実証ではない。real providerのplan/apply/destroyはこのタスクで実行しない。

依存グラフの回帰は資格情報なしで `terraform graph` を実行し、ALBのpublic routing待ちとECSのrouting/SG/IAM/listener待ちを検査する。必須入力のnull/欠落テストは一時test directoryでmockの実診断を検査し、finallyで除去する。初回は先に上記initを実行する。

共有runtime排他下のproduction検証（実AWSなし、host port非公開）：

```sh
python3 -B backend/tests/production_ca_smoke.py
docker build --platform linux/amd64 --file backend/Dockerfile.production --tag fitlog-fl09b4-production-44 .
python3 -B backend/tests/production_smoke.py
PYTHONPATH=backend python3 -B -m tests.production_tls_smoke
```

## stateとデータ削除

現時点はlocal backend。実操作前に`umask 077`と保護した専用作業場所を用意し、state/plan/tfvars/crash logを秘密として管理する。標準state保存先は`terraform/terraform.tfstate`、pluginは`terraform/.terraform/`。これらはGit除外、lockだけを追跡する。plan JSONやログも公開しない。実行・バックアップ・保管先は実AWS操作の承認時に具体化する。

S3の`force_destroy=false`、ECRの`force_delete=false`を固定。中身がある場合は削除に失敗して保全する。データを消すときはFitLog専用の対象・影響と保存済み証跡を確認した後、承認した別操作で空にする。stateを捨てたり、force設定へ変えたりして削除失敗を隠さない。

## FL-09B1のFunction部品（Issue #30、2026-11-04）

`functions/client-ip.js` はCloudFront Functions runtime 2.0のviewer-request用。接続元 `event.viewer.ip` を `X-Fitlog-Client-IP` へ設定し、利用者の同名headerをmultiValueごと上書きする。`node --test terraform/functions/client-ip.test.cjs` で変換を検証できる。AWSへのpublish/関連付けは行っていない。

FL-09B3で自distributionの両API behaviorへの関連付けと、このheaderのorigin転送を構成定義した。APIキャッシュ無効とALB/taskへの迂回防止を含む[本番準備の信頼境界](../docs/production-readiness.md)を実AWSで確認してからアプリのcloudfrontモードを有効化する。viewer.ipはCloudFrontが観測した接続元であり、VPN等の手前のIPを復元するものではない。[AWS公式例](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/example_cloudfront_functions_add_true_client_ip_header_section.html)を根拠にする。

## 前提
個人AWSアカウント・専用環境であることを操作前に確認する。具体的なリージョン、ドメイン、利用リソース、概算料金、稼働時間を示す。認証情報はコピー・表示しない。
公開ドメインはCloudFrontが発行する `*.cloudfront.net` とし、既定証明書でHTTPSを使う。独自ドメインの購入・DNS設定は不要。新たなapply後はoutputに出るURLを使い、以前のURLを固定しない。

## 構築・デプロイ・撮影・破棄（後続の草案）
1. IaCと依存lockを検証し、インフラのplanを確認する。
2. applyでリソースを作成する。
3. フロント・バックの固定した成果物を配置する。
4. migrationと再実行可能なデモseedを実行する。
5. HTTPS・readiness・認証・画像・交流をスモーク検証する。
6. 動作動画をローカルに保存し、再生確認する。
7. destroyの対象とデータ削除を確認し、環境を破棄する。
8. stateとAWS上の対象リソースを照合し、残存があれば理由を記録して削除を完了する。
9. 再applyから基本動作まで再現し、再びdestroyする。

実装時は上記それぞれに実際のコマンド、成功条件、失敗時の再実行、所要時間を追記する。applyだけでアプリの配置成功とはしない。

## 消すもの・残すもの
専用の計算資源、ネットワーク資源、DBとデータ、画像・成果物バケット、イメージ、ログ、作成したsnapshot・固定IPを削除する。動画・ソース・文書・lock・秘密として管理するstateはローカルに残す。ユーザーの既存ドメイン・共有資源は自動削除しない。

## 削除失敗
stateやlockを手で消して成功扱いにしない。エラー対象と依存関係を修正し、同じstateでdestroyを再実行する。課金停止はプロセス停止ではなく対象資源の消滅で確認する。

## 未確定
実AWS用コマンド、秘密値/DB roleの初期化、配置/破棄/再構築、総費用/所要時間は後続。ECS/RDS/CA/秘密参照は定義済みだが実経路は未検証。[インフラ設計](../docs/09_infrastructure.md)の過去料金に加えてsecret/backup/snapshot等も実構築前に再見積もりする。実AWS操作は今回含まない。
