# Issue #70：録画なし配置検証・撮影引渡し・短期削除

種別: 運用CLI/実操作申請案。最終更新2026-11-15。関連: #70、[設計](aws-day70-design.md)、[実行記録・料金原本hash](aws-day70-results.md)、[B配置](aws-b-deployment-runbook.md)、[C04正本](aws-c-boundary-contract.md)。

## 現在の状態と目的

個人account `800411048502`、profile `default`、STSで確認したIAMユーザー `arn:aws:iam::800411048502:user/saki`。予算は本人指定 **5 USD**。実AWSの実施は許可済みSTS照合1回だけ。追加調査R、構築E、公開・データ削除は未承認。夜に1回利用して本人が撮影し、終了連絡後に閉鎖・削除する。旧2環境・AI撮影・性能・後日請求比較の完了とは分ける。

## 構成と設計判断

新しい `scripts/day70/contract.py` / `runtime.py` は既存Cと別の単一環境入口。元のCが撮影を必須とするため、元のvalidatorに偽の撮影許可や2環境名を渡す方法は採用しない。B handoff・保護file・C04原本validator、既存journey、送信先guard・通信/データ上限、Node/Chromium停止処理は再利用する。製品認証認可/既存C契約/Terraform/CI/依存lockは変更しない。

## 録画なしCLI

rootから実行。Python 3.11以降、Node 24、既存lockどおりのe2e依存とChromiumが必要。

```sh
python3 -B scripts/day70/runtime.py --contract /protected/day70/contract.json
python3 -B scripts/day70/runtime.py --contract /protected/day70/contract.json --ledger /protected/day70/ledger --initialize-ledger
```

上記はoffline。`/protected/...` は実在するrepo外の正規絶対pathに置換する。親0700/file0600（原本読取り0400可）、所有者・非symlink・非hardlinkを照合。ledger directoryは事前に0700で作り、`binding.json` と `attempt.json` は排他作成。上書き/削除/別pathによる試行回数リセットは禁止。

実環境の対象origin・source・時間・費用・2合成利用者/データ/要求上限の具体E承認後だけ:

```sh
python3 -B scripts/day70/runtime.py --contract /protected/day70/contract.json --ledger /protected/day70/ledger --execute-aws
```

contract v1は `e2e/aws_contract.py` のFIELDSから `campaign_id` を除いた項目を使う。`approval.steps` は厳密に `["journey","cleanup"]`。budget_usdは正の固定小数字符列、最大5.00。environmentは `fitlog-demo-` prefix・24文字以内。他のidentity/B handoff/evidence形式は既存契約を維持する。実行窓は現在を含む5分超〜45分、末尾5分cleanup・30秒停止確認。完全な架空・保護file fixtureは `scripts/day70/test_day70.py::fixture`（実承認や配置証拠ではない）。

既存runtime lockを取得し、clean sourceのHEAD/内容hash・承認source完全OIDを照合してからintentを消費し、単独clientで既存journeyを実行する。`FITLOG_E2E_CAPTURE=0`、video/trace/screenshot off、性能を起動しない。失敗・中断でもattemptを消費。起動不明を同環境で自動再実行しない。Node起動/停止とCDPで確認したChromiumのPID/PGID/起動時刻を照合し、停止不明ではlockを保持する。

## 結果の意味

- `status=pass` はjourney E01〜E10、回復4件、自己所有データcleanup2件、C01/C02、client停止・source/所有・原本再照合・lock返却の成功。C05（録画）/C06（性能）/C07（再構築）とcapture_statusは必ずnot_run。動画/HAR/traceの生成は拒否。
- C03/画像storageの実証とC04全7probe、B permissions/IPが全て揃うまでは実AWS全体の受入れ成功としない。旧Cのacceptanceは引き続きnot_run。本人へのURL通知はCLI終了0だけで決めず、BのDB/static/health、C04原本、storage/permissions/IPの実結果も照合する。
- runtimeの`final_evidence_ready`はC04/B証跡の充足であり、撮影終了・destroy・課金停止の証明ではない。原本が消失/変更したらfail。
- パス/時刻/固定code/非秘密の観測のみ保存し、生例外・Cookie/password/CSRF/DOM/動画は保存しない。実データ/証跡の保護とURL共有先はEで固定する。

## R-70-v1：追加の読取り調査申請案（未承認）

対象は上記account・IAMユーザー、`--profile default`明示。Tokyoのみ、STS東京endpoint、IAM/CloudFrontはglobal。環境候補 `fitlog-demo-day70`、snapshot候補 `fitlog-demo-day70-final`。account内の使用数確認は内容取得でなくquota余力/衝突の判定だけ。

許可窓の提案: **具体承認の受領後30分以内、かつ2026-11-15 18:00 JST（09:00 UTC）まで**。全200 HTTP要求以内（ページ/必要なpollを含む）、各要求30秒以内、retry1=自動再送なし。SDK/CLIの暗黙再試行を無効にする。調査・全工程を含む5 USD上限のうちR枠は最大0.10 USDを提案し、read課金不明はゼロと推測しない。200件で完了しなければ未調査を明記して止める。API/対象の追加・権限変更は別扱い。

| 目的 | 正確なIAM action | 取得・対象 |
|---|---|---|
| identity照合 | `sts:GetCallerIdentity` | accountと完全IAM user ARN一致だけ。root/role/他accountなら停止 |
| IAM実行権限の読取り | `iam:GetUser`, `iam:ListAttachedUserPolicies`, `iam:ListUserPolicies`, `iam:ListGroupsForUser`, `iam:ListAttachedGroupPolicies`, `iam:ListGroupPolicies`, `iam:GetUserPolicy`, `iam:GetGroupPolicy`, `iam:GetPolicy`, `iam:GetPolicyVersion` | saki本人と所属group・関連policy/boundaryだけ。policy本文はメモリ内で必要action/制約を照合し、raw全文/秘密をGit・ログへ出さない。SCP等により有効権限未確定なら未確認と報告し、権限成立を断定しない |
| AZ/DB提供 | `ec2:DescribeAvailabilityZones`, `rds:DescribeDBEngineVersions`, `rds:DescribeOrderableDBInstanceOptions`, `rds:DescribeCertificates` | Tokyo通常2AZ、PG17完全minor/db.t4g.micro/Single-AZ/gp3 20GiB、CA。自動class変更なし |
| quota | `servicequotas:ListServiceQuotas`, `servicequotas:GetServiceQuota` | vpc/ec2/elasticloadbalancing/ecs/fargate/rdsの必要枠とcodeだけ |
| network使用数・prefix list | `ec2:DescribeVpcs`, `ec2:DescribeSubnets`, `ec2:DescribeSecurityGroups`, `ec2:DescribeSecurityGroupRules`, `ec2:DescribeNetworkInterfaces`, `ec2:DescribeAddresses`, `ec2:DescribeManagedPrefixLists`, `ec2:GetManagedPrefixListEntries` | 同account/Tokyoの必要数・prefix-list weight込み余力。既存規則を変更しない |
| ALB/ECS使用数 | `elasticloadbalancing:DescribeLoadBalancers`, `elasticloadbalancing:DescribeTargetGroups`, `ecs:ListClusters`, `ecs:ListServices`, `ecs:ListTasks`, `ecs:DescribeTasks`, `ecs:DescribeClusters` | 同account/Tokyo、running/pendingとvCPU予約・資源名衝突 |
| DB/backup衝突 | `rds:DescribeDBInstances`, `rds:DescribeDBSnapshots`, `rds:DescribeDBInstanceAutomatedBackups` | Tokyoの使用数、環境/snapshot候補との衝突、DbiResourceId。DBデータ取得なし |
| ECR/scan設定 | `ecr:DescribeRepositories`, `ecr:GetRegistryScanningConfiguration` | 対象repository衝突と基本/拡張scan・費用条件。token取得/送信なし |
| secret衝突 | `secretsmanager:DescribeSecret` | 今回application/master/fixture予定名だけ。ARN/DeletionDate metadata。GetSecretValueなし |

Resource限定不能なList/Describeは取得account/region/項目/要求枠を限定する。非秘密結果をrepo外のowner0700/file0600へ保存し、`action/filter/observed_at/選択値・数量/pass|fail|not_run/根拠path・hash/残件`で記録する。既存AWS資源の変更・CE請求照会・upload・公開・削除はRに含まない。

## Eの前に固定する費用・操作窓

EはRのpass結果を受けて別の具体承認へまとめる。未確定値をゼロ扱いせず、実行日の公式公開料金・数量・削除待ち・予備費を含め5USD以内か判断する。11月9日の0.9607USDは過去の仮定小計。今夜の撮影開始時刻と公開停止最遅時刻が未確定のため、現時点の正式総額は未算出。

- 試算項目: Fargate通常/更新/全one-off・public IPv4、ALB/LCU、RDS時間/gp3/CPU credit、snapshot/retained backup、S3容量/全version/multipart/要求、ECR storage/scan、logs/API/secret、CloudFront HTTPS/viewer/origin/Function、AZ間転送、fixture作成/伝播/削除poll、予備費・税。
- source完全OID、実ECR digest/static hash、実AZ/minor/CA、保存plan/action対象表、全ID/prefix/tag・PassRole対象4 ARN、secret/state保護pathを固定する。5USDを超える予測なら構築しない。早期停止時も閉鎖/破棄の予備費を確保する。金額通知をhard capとしない。
- 日程案は11/15夜撮影、終了連絡後に公開停止、11/16 23:59 JSTまで削除・残存確認。本人連絡なしでデータを削除しない。公開停止の最遅時刻を別に承認し、その時刻に連絡がなければ公開停止/task0だけを実行。継続課金のDB等を無言で翌日まで保持せず、予測が上限/削除猶予に達する前に報告する。

## 閉鎖・残存台帳

本人撮影終了→client停止→distribution disable/Deployed→service0/running・pending0/one-off全停止→DB保護offの保存plan/applyと実値確認→専用S3全version/delete marker/multipart・ECR image/fixture清掃→通常destroy。現行HCLが作る最終snapshot/retained backupも、今回の実ARN/DbiResourceIdを照合して承認範囲で削除する。state空だけを課金停止の根拠にしない。

対象はDB/snapshot/backup、S3、ECR/scan、logs、secret、ALB/TG/IPv4/ENI、ECS全task、CloudFront/Function/OAC、専用IAM/network。台帳の各行に `environment/run/type/exact ID/owner/observed_at/status/quantity/消滅または残存理由/残費用/delete_by/根拠/残件` を記録する。削除予約secretは7日回復期間の非課金残存とし物理消滅と区別する。課金資源の削除未確認は未完了として報告。force/共有データ清掃/未知task再起動/自動権限追加はしない。

## ローカル検証

```sh
python3 -B -m unittest discover -s scripts/day70 -p 'test_*.py'
python3 -B -m unittest discover -s e2e/harness -p 'test_*.py'
npm --prefix e2e run typecheck
npm --prefix e2e run test:harness
```

登録11 checksは `python3 -B scripts/run-checks.py`、既存HTTPS/停止guard fixtureは `python3 -B e2e/harness/aws-browser.py`。共通Git領域とruntime排他・固定portを守る。fixture成功は実AWS成功ではない。実行記録は別途snapshot/commitと対応付ける。

## エラーと回復

`DAY70_RUN_REFUSED`はcontract/承認/期限/実行の固定拒否（exit1）。runtime内の`DAY70_RUN_FAILED`、`DAY70_OBSERVATIONS_INVALID`、`DAY70_EVIDENCE_INVALID`は原因分類。上流例外を表示せず、失敗intent/証跡を保持する。停止不明・所有変更ではlockを残し、他taskのprocessやlockを削除しない。再実行には原因と残存client/データを確認した再開計画が必要。
