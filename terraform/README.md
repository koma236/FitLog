# Terraform — FitLogデモ基盤

FL-09B2（Issue #32、2026-11-04）で基盤のroot moduleとmock planテストを実装。AWS資源の作成・疎通・実権限評価は未実施。下段の構築・配置・撮影・破棄手順は、後続作業の設計草案として区別する。

## 実装済みの範囲

Terraform **1.15.1**、公式AWS provider **6.71.0**をexact pinし、`.terraform.lock.hcl`でchecksumを固定する。root moduleをnetwork/storage/IAM/outputsに分割し、外部moduleは使わない。[承認設計](../docs/fl-09b2-aws-foundation-design.md)・[全体のインフラ草案](../docs/09_infrastructure.md)参照。

- 東京2AZの専用VPC（10.42.0.0/16）、public /24×2とprivate DB /24×2。publicだけIGWへdefault route。NAT/EIPなし。subnetのpublic IP自動付与なし。
- ingress/app/databaseの専用SG。ingressの受信は空、ingress→app TCP8000、app→DB TCP5432、appのIPv4 TCP443外向きだけを許可。exclusive rule setsで既定の広いegressを残さず、DBからの外向き通信はなし。inline SG ruleとstandalone ruleの所有を混在させない。
- private static/media S3、owner enforced、public access全block、AES256。非TLSの非AWS-service要求を明示拒否する。AWS service principalの例外はアクセス許可を追加しない。CloudFrontのread grantはまだない。
- immutable/scanned/AES256のbackend ECR、7日保存のlog group。自動image削除はしない。
- task roleはmediaのimages/* Get/Put/Deleteとprefix=images/でのListだけ。execution roleは対象ECR取得・registry token・対象log stream書込みだけ。信頼先は同account/東京のECS task。Secrets Manager/SSM/DB/image書込み等の権限はまだない。

`expected_account_id`（12桁）、`environment_name`（fitlog-demo-から始まる最大24文字）、`availability_zones`（異なる東京AZ2つ）が入力。providerはexpected account以外を拒否する。mockはこの実account照合や実際のAZ提供状況を検証しない。将来実行時には本人の専用account・利用可能AZも確認する。

ALB/CloudFront/ECS/RDS・秘密の注入・公開経路は未定義。outputsは基盤ID・名前・ARNのみで、稼働URLを返さない。前回のIP判定の信頼設定も有効化しない。**TerraformのCI組込みは実AWS構築へ進む前に必要な後続タスク**であり、現行CIの11 checks/ci-requiredは変更していない。

## AWSへ接続しないローカル検証

リポジトリrootで実行する。`init`は公式Registry/配布元からpluginを取得するためネットワークが必要。`validate`/`test`はローカルpluginの起動権限が必要だが、AWS資格情報を渡さない。`TF_CLI_CONFIG_FILE`も空にし、個人・会社のprovider上書き設定を読み込ませない。

```sh
terraform -chdir=terraform fmt -check -recursive
env -i PATH="$PATH" CHECKPOINT_DISABLE=1 TF_CLI_CONFIG_FILE=/dev/null TF_IN_AUTOMATION=1 AWS_EC2_METADATA_DISABLED=true AWS_SHARED_CREDENTIALS_FILE=/dev/null AWS_CONFIG_FILE=/dev/null terraform -chdir=terraform init -backend=false -input=false -lockfile=readonly
env -i PATH="$PATH" CHECKPOINT_DISABLE=1 TF_CLI_CONFIG_FILE=/dev/null TF_IN_AUTOMATION=1 AWS_EC2_METADATA_DISABLED=true AWS_SHARED_CREDENTIALS_FILE=/dev/null AWS_CONFIG_FILE=/dev/null terraform -chdir=terraform validate
env -i PATH="$PATH" CHECKPOINT_DISABLE=1 TF_CLI_CONFIG_FILE=/dev/null TF_IN_AUTOMATION=1 AWS_EC2_METADATA_DISABLED=true AWS_SHARED_CREDENTIALS_FILE=/dev/null AWS_CONFIG_FILE=/dev/null terraform -chdir=terraform test -no-color
```

全test runは`command=plan`、`mock_provider aws`を使う。mockと個別のID/ARN overrideには`override_during=plan`を設定する。実policy JSONは`jsonencode`で生成し、全Statementを独立した期待値と比較する。policy自体をmockへ置換しない。テストfixtureのaccount `123456789012` は架空値。mockを誤って外しても、上の最小環境はprofile/role/OIDC/container資格情報を引き継がず、共有credential/configとmetadataを探索しない。

mock成功はAPI可用性・AWSでのIAM評価・SG疎通・account照合・課金の実証ではない。real providerのplan/apply/destroyはこのタスクで実行しない。

## stateとデータ削除

現時点はlocal backend。実操作前に`umask 077`と保護した専用作業場所を用意し、state/plan/tfvars/crash logを秘密として管理する。標準state保存先は`terraform/terraform.tfstate`、pluginは`terraform/.terraform/`。これらはGit除外、lockだけを追跡する。plan JSONやログも公開しない。実行・バックアップ・保管先は実AWS操作の承認時に具体化する。

S3の`force_destroy=false`、ECRの`force_delete=false`を固定。中身がある場合は削除に失敗して保全する。データを消すときはFitLog専用の対象・影響と保存済み証跡を確認した後、承認した別操作で空にする。stateを捨てたり、force設定へ変えたりして削除失敗を隠さない。

## FL-09B1のFunction部品（Issue #30、2026-11-04）

`functions/client-ip.js` はCloudFront Functions runtime 2.0のviewer-request用。接続元 `event.viewer.ip` を `X-Fitlog-Client-IP` へ設定し、利用者の同名headerをmultiValueごと上書きする。`node --test terraform/functions/client-ip.test.cjs` で変換を検証できる。AWSへのpublish/関連付けは行っていない。

後続Terraformでは自distributionの全API behaviorへ関連付け、このheaderをoriginへ転送する。APIキャッシュ無効とALB/taskへの迂回防止を含む[本番準備の信頼境界](../docs/production-readiness.md)を実AWSで確認してからアプリのcloudfrontモードを有効化する。viewer.ipはCloudFrontが観測した接続元であり、VPN等の手前のIPを復元するものではない。[AWS公式例](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/example_cloudfront_functions_add_true_client_ip_header_section.html)を根拠にする。

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
実AWS用の実コマンド、公開経路の最終構成、総費用、所要時間は未確定。[インフラ設計](../docs/09_infrastructure.md)に過去の主要料金試算を記載しているが、実構築前に現在の条件で再見積もりする。ブラウザ側のCloudFront既定HTTPSは方針確定。実AWS操作は今回含まない。
