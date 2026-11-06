# 2構築分のAWS費用試算

最終更新/公式単価取得日2026-11-07 JST、Issue #55。東京Linux/x86オンデマンド、無料枠/credit控除なし。
実account/role/予算/期限は未決、実AWS未承認。仮定数量の感度分析であり請求額/hard cap保証ではない。
再計算: `python3 -B scripts/prebilling/readiness.py`。

## 単価・数量

Terraform: Web0.25vCPU/1GiB通常1/更新最大2、同容量bootstrap、RDS db.t4g.micro Single-AZ/gp3 20GiB、ALB1/2AZ、S3二bucket、ECR1、log二group/7日、app/master secret。NATなし。

| 項目 | USD単価 | 数量/構築 |
|---|---:|---|
| Fargate vCPU/memory | 0.05056/vCPU時 / 0.00553/GB時 | 0.25vCPU/1GB×h、追加task0.5時間 |
| RDS instance/gp3 | 0.025/時 / 0.138/GB月 | h時間、20GB |
| ALB/LCU | 0.0243/時 / 0.008/LCU時 | 1台/1LCU×h、部分時間切上げ注意 |
| public IPv4 | 0.005/address時 | ALB最低2+Web1×h、追加task0.5address時 |
| S3 Standard | 0.025/GB月 | 二bucket合計0.2GB |
| S3 PUT等/GET等 | 0.0047/1000 / 0.0037/10000 | 1000 / 10000要求 |
| ECR private | 0.10/GB月 | image0.5GB、同region取得 |
| CloudWatch取込/保持 | 0.76/GB / 0.033/GB月 | 合計0.1GB |
| Secrets Manager保持/API | 0.40/secret月 / 0.05/10000 | app+master計2、100要求 |
| CloudFront日本HTTPS/viewer転送 | 0.012/10000 / 0.114/GB | 10000要求、1GB |
| CloudFront→origin転送 | 0.060/GB | upload等0.1GB |
| RDS追加snapshot/backup | 0.095/GB月 | 2構築後20GB×2を7日保持 |

公式公開Price List（実account APIではない）:

- [ECS東京](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonECS/current/ap-northeast-1/index.json): publication2026-10-19、vCPU SKU KBQ3Q6DY9J327G8N、memory JQEE6EF5FAF2AESH。
- [RDS東京](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonRDS/current/ap-northeast-1/index.json): publication2026-10-29、instance YXENKSJFV9BXQF4N、gp3 YM9AR73XYRPUSCN3、backup 8EP35HPTSYF38J3V。
- [ALB東京](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AWSELB/current/ap-northeast-1/index.json): publication2026-11-05、ALB 98ZU8QNDMR4AS8FJ、LCU F2UQT6CZGM7BTWS8。
- [S3東京](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonS3/current/ap-northeast-1/index.json): publication2026-11-04、Standard CCBFTMENTDWZHXHX、PUT XAKHUSC46NWC9PPM、GET 9C7873KU3ZQBD6BJ。
- [CloudWatch東京](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonCloudWatch/current/ap-northeast-1/index.json): publication2026-11-04、取込 CWB2GTZJXNX3TA6H、保持 42CVQU4BPES8AWHC。
- [Secrets Manager東京](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AWSSecretsManager/current/ap-northeast-1/index.json): publication2026-09-11、保持 GVA2ZKT9KD5RYX6P、API JC68V52M47AA94EZ。
- [CloudFront](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonCloudFront/current/index.json): publication2026-10-19、日本HTTPS EJZT492VM8J2VQTQ、viewer CME9BRJSS2F5PBYE、origin 3R2FUPWJ2VYY9GAN。従量課金想定でflat-rateへ変更しない。
- [IPv4公式](https://aws.amazon.com/vpc/pricing/)、[ECR公式](https://aws.amazon.com/ecr/pricing/)、[Fargate課金単位](https://aws.amazon.com/fargate/pricing/)。Linux Fargate/IPv4は秒単位/最低60秒。月額は試算上730時間按分で実月日数と区別。

## 時間別の2構築費用

各構築h時間、初回破棄から再構築まで4時間保持、終了後7日保持と仮定。
中核0.09425082 USD/構築時、追加task等0.011585 USD/構築。容量/要求/転送/log/secretを2回分加算。
中間保持0.01073041、終了後保持0.90135452 USD。

| 各構築h | 2構築中核小計USD | 仮定変動費・中間/終了後保持込みUSD |
|---:|---:|---:|
| 1 | 0.2117 | 1.5599 |
| 4 | 0.7772 | 2.1325 |
| 8 | 1.5312 | 2.8959 |
| 24 | 4.5472 | 5.9495 |

式 `2×(h×時間単価+one-off)+中間保持+終了後保持`。snapshotは実保持容量による。
automated backupを別途40GB・1日残すなら約0.1249 USD追加。停止RDSを残すとgp3 20GBだけで約2.76 USD/月+backup等。
最終snapshot40GBは約3.80 USD/月、未削除secret4個は約1.60 USD/月。削除予約済みsecret回復期間は課金なし（[公式](https://docs.aws.amazon.com/secretsmanager/latest/userguide/manage_delete-secret.html)）。

## 未決・未算入

実LCU/転送先/GB/要求/ALB address数、taskのimage取得/起動時間、対照distribution/metadata fixture追加量、RDS CPU credit/AZ間転送/backup実量、ECR基本/拡張scanのaccount設定、RDS minor/CA/quotaは未確認。
JPY/税/余裕率/予算/実期限も未決。仮定超過で試算超過になる。実行日の数量/単価を再確認し残存期限込みUSD予算を別承認する。
停止/削除/後日請求確認は[readiness](fl-09b8-prebilling-readiness.md)。試算を資源作成許可にしない。
