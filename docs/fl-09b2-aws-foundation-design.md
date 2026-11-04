# FL-09B2 AWS基盤のTerraform定義

2026-11-04、ユーザーが独立設計レビュー結果と短い計画を「はい、よいです。お願いします。」と承認。Issue #32、実装branch `feat/fl-09b2-aws-foundation-32`。Terraform 1.15.1、公式Registryで確認したAWS provider 6.71.0を固定する。

## 目的・現状

baseline `c90ae50`。FL-09AとFL-09B1はmainへ統合済み。次は専用VPC・非公開storage・image repository・最小権限をTerraformで定義し、AWS APIや資格情報を使わず構成の契約を検証できる状態にする。今回の成功はAWS構築・アプリ配置・公開の成功を意味しない。

worktree `/Users/saki/.codex-personal/worktrees/5db0/FitLog`、準備branch `prep/fl-09b2-aws-foundation`。writerは親セッション1つ。先行PR #31はmerge済み。Issueは設計承認後に作成し、番号付きfeature branchへ改名する。他worktree・共有環境は変更しない。

## 対象と契約

`terraform/` を単一環境のroot moduleとして、設定・network・storage・IAM・outputs・testsに分割する。外部moduleは導入しない。

| 対象 | 定義するもの |
|---|---|
| 固定と入力 | Terraform 1.15.1（手元で確認済み）、導入時に公式Registryで確認したstable AWS providerをexact pinしlockをcommit。東京 `ap-northeast-1` 固定。入力は12桁のexpected account、`fitlog-demo-`から始まる短い環境名、東京の異なるAZ2つ。account/name/AZの不正はvalidationで拒否 |
| account境界 | providerのallowed_account_idsにexpected accountを設定。実操作ではAWS標準credential chainで本人の専用accountを確認する。資格情報検証やaccount照合を無効化する設定を製品providerへ追加しない。mockはtest providerだけ |
| network | 専用VPC `10.42.0.0/16`、DNS support/hostnames有効、2AZのpublic subnet各/24とprivate DB subnet各/24。publicのみIGWへのdefault route、privateはlocal routeのみ。subnetのpublic IP自動付与は無効。将来Fargate配置時にtask側で明示する。NAT/EIP/peering/共有VPC参照なし |
| SG | ingress用・app用・DB用を専用作成。ingress SGの受信は空（公開経路を後続で設計・接続するまで閉じる）。ingress→app TCP8000、app→DB TCP5432のみ相互方向に必要なルールを作成。appは外部AWS API用TCP443のみIPv4 egress許可。DBは受信元app SGだけ、egressなし。SSH/DBのpublic CIDR受信なし。default SGは未使用 |
| S3 | 静的成果物用・画像用の2bucket。environment/account/regionから命名、bucket owner enforced、4項目のBlock Public Access、SSE-S3 AES256、非TLS拒否policyを設定。versioningなし。静的bucketのCloudFront read grantはdistribution作成時に追加。ACL/website endpoint/公開grantを作らない |
| ECR / logs | backend用private ECR repository、immutable tag、AES256、scan-on-push。専用CloudWatch log group、retention7日。自動image lifecycle削除は追加しない |
| IAM | ecs-tasks.amazonaws.comだけを信頼するtask roleとexecution role。SourceAccountと東京・同accountのECS SourceArn条件を付ける。task roleは画像bucketのimages/*にGet/Put/DeleteObject、bucket ListBucketはs3:prefix=images/だけ。static bucket・他prefix・管理操作は許可しない。execution roleは対象ECRのimage取得と対象log groupへのstream作成/書込み。GetAuthorizationTokenだけResource=*（API仕様による）。Secrets Manager・SSM・DB・iam:PassRole・image push権限は今回付与しない |
| 破棄境界 | S3 bucketのforce_destroy=false、ECRのforce_delete=falseを固定。中身がある場合は失敗して保全し、無条件削除scriptを追加しない。state/plan/tfvars/.terraform/crash logをGit除外し、.terraform.lock.hclは追跡。local stateは秘密として扱い、将来実行時のファイル権限・保存場所をREADMEに明記 |
| outputs | VPC/subnet/SG IDs、bucket名/ARN、ECR URL/ARN、log group名、role ARNを後続へ渡す。秘密値は入力も生成も出力もしない。CloudFront URL・稼働serviceが存在するような出力は作らない |

appのTCP443外向き許可はAWS APIの可変IPに対応するための範囲であり、endpoint制限とは扱わない。private DB subnetは現時点で外向き経路が不要なためNATを設けない。公開SGを先に開ける案は採用せず、未接続の基盤を閉じた状態で渡す。

## 今回含めないもの

ALB/CloudFront/OAC/ECS service・task definition/RDS instance/DB subnet group/Secrets Manager、CA bundle注入、migration/seed/deploy/destroyの実行script、公開・撮影は後続。前回Functionも未関連付けのまま。アプリのcloudfront IP信頼設定を変更しない。ALB経路のHTTP/TLSやVPC originの最終選択はこの土台で決めず、公開経路の設計で承認する。

AWS accountの探索・AWS API呼出し・real providerのplan/apply/destroy・resource importは今回実行しない。registry/provider配布元への依存取得だけは必要。AWS価格の古い試算を今回の総額見積りとして使用しない。実AWS操作の前に対象・料金・期間・データ削除を別途具体化して承認する。

現行CIの11 checksとci-requiredは変更しない。Terraform用CI組込みは、実AWS構築へ進む前の後続必須作業としてREADME/task-planに明記する。今回追加のTerraformチェックはローカルで全件実行し、CIで検証済みとは表現しない。

## 検証の根拠と短い実装計画

1. 承認後Issue・番号付きbranchを整える。High（IAM・network・provider依存）のtest-designを実装前に記録。既存アプリ/Compose/lock/11 checks設定は変更しない。主な所有範囲はterraform/、.gitignore、インフラ/進捗/本番準備の関連docs。
2. 仕様の固定期待値を `terraform/tests/*.tftest.hcl` に先に記述。すべて `mock_provider "aws" { override_during = plan }` を使い、実providerへのfallbackなし。runはcommand=planとし、computed IDs/ARNは必要な箇所だけ固定fixtureを使う。これによりSG参照やARNをplan中に確定させる。テストが失敗することを確認して定義を実装する。
3. networkのsubnet数/AZ/routeとSGのprotocol/port/source/destination、S3の非公開・所有権・暗号化・TLS拒否・force_destroy=false、ECRのimmutability・force_delete=false、roleのtrust/action/resource/conditionを固定期待値でassertする。IAM/bucket policyはjsonencode等で実設定から生成し、計画されたJSONをdecodeして全statementを検査する。policy JSONそのものをmock期待値で置き換えるテストは作らず、禁止したgrantの追加も検出する。account/name/AZの負例はexpect_failuresで確認する。mockはAWSの実権限評価ではないことを明記する。
4. `terraform -chdir=terraform fmt -check -recursive`、`init -backend=false`（provider取得）、`validate`、`test`（mock planのみ）を実行。testはAWS資格情報を渡さず、metadata/共有credential file探索を無効にしたtest processで実行する。mockの誤編集で実AWSにfallbackしても資格情報を得られない環境にする。AWS accountや秘密をtest fixtureに入れない。
5. 関連文書を更新。共有runtime lease内で既存11 checksとゲート回帰、既存Function testを実行。機械チェック合格後にquality-check（統合・反証QA・Security、目安3体）で独立確認・修正する。設計レビューは1体。親が実装し、task単位レビューは追加しない。
6. check id/終了コード/snapshot/日時を保存し、commit・feature push。完成したPR本文を最終報告で提示してPR作成を確認する。mergeは本人。

受け入れ条件は、mock下で上記固定契約・負例がすべて通ること、state/秘密の追跡なし、未実施AWS/CIを完了と呼ばないこと。Terraform fmtやvalidateだけでIAM・ネットワークの合格とはせず、計画値のassertionと独立レビューを併用する。

## 原典（2026-11-04確認）

- [Terraform provider mocking](https://developer.hashicorp.com/terraform/language/tests/mocking)：実resource/資格情報なしでprovider schemaを使うテスト。実IAMや疎通は実証しない。
- [Provider requirementsとlock](https://developer.hashicorp.com/terraform/language/providers/requirements)、[AWS provider公式設定](https://raw.githubusercontent.com/hashicorp/terraform-provider-aws/main/website/docs/index.html.markdown)：exact version、allowed_account_ids。
- [ECS execution role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html)、[ECR action/resource](https://docs.aws.amazon.com/service-authorization/latest/reference/list_ecr.html)：image取得とauthorization tokenの権限境界。
- [ECS task roleのtrust条件](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html)、[ECR repository provider仕様](https://raw.githubusercontent.com/hashicorp/terraform-provider-aws/main/website/docs/r/ecr_repository.html.markdown)。
- [S3 policy条件](https://docs.aws.amazon.com/AmazonS3/latest/userguide/amazon-s3-policy-keys.html)：s3:prefix、非TLS拒否とAWS service principal条件の注意。
- [VPC DNS属性](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-dns-updating.html)。公開経路は後続で[CloudFront/ALB原典](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/restrict-access-to-load-balancer.html)も照合する。

## 独立設計レビュー

2026-11-04、helm-doc-reviewer（gpt-6.1-sol/high）1回。予約marker `d757bf8a9c25a44232e0ef78527fe690:document-reviewer` は起動前に既存公開checkReview APIで受付し、台帳のused/receiptを確認済み。

- High 0、Medium 1：mock値をplan中に確定させる条件不足。override_during=planとcomputed ID/ARN fixtureを明記し、policy JSONは実設定から生成して検査する方針へ修正。
- Low 1：ECRの削除属性名。S3 force_destroyとECR force_deleteを分け、両方falseのassert対象へ修正。
- ほかに具体的な重大矛盾なし。修正は指摘内容・公式仕様と照合済み。追加設計レビューは行っていない。レビュー後の本設計・短い計画はユーザー承認済み。
