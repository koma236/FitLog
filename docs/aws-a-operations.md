# AWS A: 操作管理・引渡し・残存確認

種別: 前提条件・運用手順。最終更新2026-11-07。Issue #58。
[承認設計](aws-a-foundation-design.md)、[申請書](fl-09b7-aws-approval-template.md)、[Bの配置手順](fl-09b7-deployment-runbook.md)を併用する。
Issue #67: 個別の調査/実操作の対象・期限・数量・費用・後日照会は[承認案](aws-execution-approval-draft.md)へ集約する。同案は未承認草案であり、未確定/#66待ちが残る間は実行不可。

以下の実AWS工程は未実行。この文書やローカル検査成功は接続許可ではない。

## 責任と開始条件

AWS構成変更はA一人だけが実行する。Bは配置手順・成果物、Cは試験harness/試験結果を所有する。Cの通信窓以外では試験を開始しない。B/Cの要望を取り込み、操作対象・上限・期限を実申請へ記載する。新しい資源や権限が必要なら自動で広げない。

1. 読取り調査だけの申請に個人12桁account、既存IAM operator role完全ARN、Tokyo、read API、開始/終了時刻を記入し、対象への明示承認を得る。
2. 承認後にだけ`sts:GetCallerIdentity`。account一致、AssumedRole ARNのrole対応をIAM正本と照合し、別role/rootなら停止。会社資格・既定profileへのfallbackをしない。roleのpathを省略比較しない。
3. 下表を調査し、非秘密の選択項目・日時・対象・pass/fail/not_runを保護folderへ記録する。AccessDenied/不明/提供なしは停止し、権限・class・minorを自動変更しない。
4. Bの所要時間・各one-off task数、Cの要求数/利用者/画像/負荷/撮影/fixture上限とcleanupを取得する。未取得なら実操作申請を完成扱いにしない。
5. 調査結果・2環境の実名/成果物対応・費用・閉鎖猶予・破棄/残存期限を申請へ記入し、構築/送信/公開/破棄/再構築の個別対象と工程の承認を得る。

## 調査APIとoperator権限

これは権限を自動付与するpolicyではない。実行前に既存roleのpolicy・boundary/SCPと照合し、対象の正確なARN/IDに束縛した実操作申請を作る。List/Describeで資源単位制限のないAPIは`Resource=*`の理由・region・読取り限定を明記する。管理者policyを追加して代用しない。

| 工程 | API/action群 | 対象・確認 |
|---|---|---|
| identity | `sts:GetCallerIdentity`、必要な`iam:GetRole` | 指定account/role。IAM操作は調査承認に含めたものだけ |
| 提供確認 | `ec2:DescribeAvailabilityZones`、`rds:DescribeDBEngineVersions`、`rds:DescribeOrderableDBInstanceOptions`、`rds:DescribeCertificates` | Tokyo通常AZ2つ、PG17完全minor/db.t4g.micro/Single-AZ/gp3 20GiB/指定CA、期限。CA bundleは既存固定hashと照合 |
| quota | `servicequotas:ListServiceQuotas`/`GetServiceQuota`、`ec2:DescribeManagedPrefixLists`/`DescribeSecurityGroups`、各サービスのList/Describe | CloudFront prefix list weight55のSG枠、Fargate vCPU、ALB/target group、VPC/SG/RDS/IPv4。上限だけでなく使用量を差引く |
| 衝突・設定 | `ecr:DescribeRepositories`/`GetRegistryScanningConfiguration`、`secretsmanager:DescribeSecret`、`rds:DescribeDBInstances`/`DescribeDBSnapshots`/`DescribeDBInstanceAutomatedBackups` | 2環境名・snapshot・削除予約secret衝突、scan費用、保持backup。secret値は読まない |
| Terraform構築/切替/破棄 | planに含まれるEC2 VPC/subnet/route/SG、ELBv2、CloudFront/Function/OAC、S3、ECR、ECS、RDS、Secrets Manager、logs、IAM専用role/policyのCRUDとtag操作 | `terraform/*.tf`と保存planからAPI・対象一覧を作成する。作成前でARN限定不能な操作は環境prefix/tagとregionで限定し、対象外の変更がplanにあれば停止。未具体化のまま実行しない |
| B配置 | `ecr:GetAuthorizationToken`、対象repositoryのupload/PutImage/DescribeImages、static bucketのList/Get/Put、`ecs:RunTask`/`DescribeTasks`/`ListTasks`/`StopTask`、B既存metadata Describe、`logs:GetLogEvents` | 指定ECR/static bucket/cluster/task定義/Web・bootstrap stream。応答不明はBのintent/collect規則で収集。RunTask起動済みの確認なく再起動しない |
| PassRole | `iam:PassRole` | 今回Web/bootstrapのtask/execution role完全ARN4つだけ。`iam:PassedToService=ecs-tasks.amazonaws.com`。Webに管理権限を足さない |
| 対照fixture | B/Cが指定する専用secret/S3 key/別distributionの作成・metadata検査・削除 | 対象と費用/後始末を別途列挙。秘密の値をA→B/Cの共有記録へ出さない |
| 残存/請求 | 対象サービスのList/Describe/Get、承認対象のsnapshot/retained backup/S3/ECR/log/secret削除、`ce:GetCostAndUsage`等の許可した請求照会 | RDS DbiResourceId、snapshot ARN、削除予約日時、bucket version/upload ID等へ限定。account全体清掃は不可。請求反映遅延を記録 |

API一覧の不足は権限不足を握り潰して補わず、保存planと実際の要求を照合して申請に戻す。IAM simulationだけで実権限の成立を証明しない。

## 保護local backendと保存plan

実操作許可後に使う雛形。`/protected/...`は実在するユーザー所有のrepo外0700 directoryへ置換し、state/tfvars/plan/backup/TF_DATA_DIR内ファイルを秘密として管理する。個々の値はチャットへ貼らない。

```sh
umask 077
export TF_DATA_DIR=/protected/first/terraform-data
terraform -chdir=terraform init -input=false -lockfile=readonly -backend-config=path=/protected/first/terraform.tfstate
terraform -chdir=terraform workspace show
```

workspaceはdefaultのみ。初回は新規folder/state不在を確認し、既存stateを発見したら移行・上書きしない。初期化後`TF_DATA_DIR/terraform.tfstate`のbackend種別/pathと申請を保護folder内で照合する。shell履歴に秘密を入れず、`TF_CLI_ARGS*`等の暗黙引数を排除する。B手順のTerraform呼出しにもこのTF_DATA_DIRを維持する。再構築は別TF_DATA_DIR・別state。

全体planの前にECR限定create1件だけをBの`check_plan.py`で検査して適用し、B手順でimageを送信する。架空digestはECR限定planだけ。実digest/sourceを得てから全体planへ進む。

```sh
terraform -chdir=terraform plan -input=false -var-file=/protected/first/runtime.tfvars -out=/protected/first/runtime.plan > /protected/first/plan.log 2>&1
terraform -chdir=terraform show -json /protected/first/runtime.plan > /protected/first/plan.json
```

plan/json/logは全て秘密として保護し、端末/PRへ中継しない。source/vars/planのhash、既存stateのhash/lineage/serial、default workspace、backend path、予算/期限・許可操作を照合。別環境、予期しない置換/削除/公開/権限拡大ならapplyしない。初回state不存在はその旨を記録する。

```sh
terraform -chdir=terraform apply -input=false /protected/first/runtime.plan > /protected/first/apply.log 2>&1
```

毎apply後にstateのowner/正規path/非symlink・親0700/file0600（読取り専用0400可）とhashを確認し、manifestへ新hashを反映する。raw stateではなく既存の名前指定非秘密outputだけを選択して転記する。広い`terraform output -json`は共有しない。stateの手動編集/削除、force-unlock、refresh=falseでの回避は禁止。

## B/Cへ渡す契約

既存manifest正本は`backend/operations/deployment_contract.py`。schemaを増やさず、[設計§4](aws-a-foundation-design.md#4-stateplanと担当間契約)の対応表を使う。

- A→B: account/environment/run/bootstrap UUID、outputからのresource IDs、保護state path/hash、source/image/static対応、承認reference/許可steps/予算/有効期限。secretの値は渡さない。
- B→A: clean build/source/digest/static hash、前段成功・intent/task/remote event証拠、所要時間、応答不明の収集方法。
- A/B→C: exact HTTPS origin、environment/run/source/digest、B health/seed/verify成功証拠、窓/要求数/データ/負荷上限、停止条件。
- C→A: 試験開始/終了、実使用量と残存fixture、自分のcleanup結果、失敗・不明事項。Cの上限や必要fixtureが未決なら公開へ進めない。

run単位の台帳は`environment/run/source/image_digest/frontend_sha256/state_path/state_sha256/approval_reference/operator/start/close_start/public_end/destroy_by/B_evidence/C_evidence/status`を記録。操作直前に現在値と期限を再照合する。Bの同run bindingを破壊するために証跡を編集/コピーしない。

## 退避・破棄・再構築

公開既定off・task0・削除保護onから開始。B private工程→backend検証→許可済み一時公開→C試験の順。Terraform apply成功やALB liveだけでは実経路成功としない。

閉鎖開始時刻には新しい試験/配置を止め、Aがdistribution無効化→Deployed、service0→running/pending0を実測し、one-off taskもB intent/runと照合して停止・収集する。失敗証拠を残し、退避不明なら未完了。期限超過予測で早期退避し、権限拡張/未承認削除へfallbackしない。退避・破棄の有効期間を公開終了より長く別指定し、期限切れ後は新しい許可が必要。

停止確認後だけDB保護解除plan/apply→実保護off確認→通常destroyの保存planを作成して対象を確認する。force_destroyを足さず、申請で許可された専用bucketの全version/delete marker/未完了multipart、ECR image、B/C fixtureをID照合して片付ける。共有/他runのデータを消さない。DB final snapshot・保持backupは削除成功に含めず残存台帳へ移す。

初回破棄・棚卸し後、別環境/別state/別run/bootstrap UUID/snapshot名で再構築する。Bの既存手順で同sourceから再buildし、実digest/static hashを新環境の申請/manifest/tfvarsへ拘束して再試験。同sourceから同一digestを保証しない。新digestが許可対象に含まれなければ承認まで停止。初回成功証拠の流用は禁止。

## 残存・請求台帳

各項目に`environment/run/resource_type/exact_id_or_arn/DbiResourceId/observed_at/status/quantity/retention_reason/delete_by/owner/estimated_residual_usd/approval_reference/evidence/next_check_at`を記録。情報不明をゼロとして計算しない。

棚卸しはALB/ENI/public IPv4、ECS全task/cluster、RDS instance/final snapshot/manual snapshot/retained automated backups、S3 versions/delete markers/multipart、ECR image/scan、logs、app/master/fixture secret、CloudFront/Function、IAM/networkを対象にする。AWS正本とstate双方を確認し、state外に残るsnapshot等も追う。
RDS停止だけではstorage/backup課金が残り7日後に再開し得る。削除予約secretは回復期間中の残存と課金なしを区別し、予定日後に消滅を確認する。削除/請求確認担当と具体日時は実申請で必須。2回の構築・再検証・破棄、承認した残存の消滅/保持確認と遅延請求確認まで、AWS全体完了とはしない。

## ローカル検証

`readiness.py --scenario`は[費用文書](fl-10b-aws-costs.md#ローカルscenario検査issue-58)を参照。Terraformは既存`bash -p .github/ci/terraform-checks.sh`でmock検証し、資格を除いたproviderなしfixtureでstate分離も確認する。実AWSの成立証拠とは区別する。
