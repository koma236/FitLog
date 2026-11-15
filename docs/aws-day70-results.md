# Issue #70 実行記録

最終更新2026-11-15 JST。関連: [設計](aws-day70-design.md)、[運用/具体調査案](aws-day70-runbook.md)。

## 状態

- 個人account `800411048502`、profile `default`。本人が限定許可したSTS照合で `arn:aws:iam::800411048502:user/saki` を確認。構築/送信/公開/削除は未実施。AWS URLは未発行。
- ローカルの録画なし単一環境入口と15テストを実装。元のC契約/2環境campaignを変更せず、既存journey・guard・client停止を再利用する。
- 追加AWS調査R-70-v1は本人回答待ち。構築Eも未承認。実AWSの認証認可/画像/storage/C04/稼働・削除・課金対象消滅は全てnot_run。

## ローカル機械検証

2026-11-15実行。登録checksのHEADは `03f0dae3eed00454ec54f76d09f2e79b39f37a6c`、今回6ファイルをstageした未commit snapshot SHA256は `e5e8e7af3c8c5558015e17a87069bb534c8adaab6c2c674c2248d5395230d2f9`。run前後でsnapshot一致を確認。

| 検証 | 結果 |
|---|---|
| 登録11 checks | 全件exit0。backend pytest643、frontend Vitest190が成功 |
| migration | before/pre/post/finalのgraph・適用状態を記録、未知適用なし |
| 共有runtime後始末 | 今回起動DBのみ停止、lock返却・残存lockなし |
| day70単体/統合fixture | 最終15件成功。REDで入口欠落・health証跡の未検査・再照合失敗時の誤lease返却を確認後に実装/修正 |
| 新規Python静的検査 | ruff F/E9成功。未使用import除去・High修正後に静的検査とday70全15件を再実行 |
| 既存deployment/prebilling | Python52件/16件成功 |
| 既存E2E契約/runtime | Python50件、Node59件、TypeScript型検査成功 |
| Terraform | fmt/init/validate、Python4件、mock45件、Function Node3件成功。資格を除いたmock検査 |
| ゲート回帰 | Node64件成功 |
| run-checks自身の回帰 | Python28件成功。fake boundaryによる検証で製品操作なし |
| HTTPS/送信先/Chromium停止fixture | `aws-fixture-090d6778f9b1` passed=true、product_requests=0、aws=not_run |

登録checksの原本はローカル `.quality-check-runs/20261115T042937Z-70500113d19742dfba86c1e7ae875dd7/results.json` と各log。最終品質記録は `.quality-check-report.json`。Gitへ生logは含めない。登録checks終了後はday70テストの未使用import除去、運用文書、次項のday70終了処理High修正を行った。backend/frontend/Compose/lock/migrationの検証対象に追加差分なし。変更したday70は最終snapshotで静的検査と全15件を再検証済み。

## 独立品質レビューの指摘

初回は統合・反証QA・securityの3役で実施。High1件、Medium2件。Highはsource/B原本の再照合失敗時にstatus=failでもlock/leaseを返却する不整合。source一致と原本照合成功を返却条件へ追加し、source hash変更・実B receipt改変の両方で返却0回/lease未返却/全保存結果failになるRED→GREENを確認した。修正確認レビューは別の規定巡で行う。

MediumはPRへ記録する。journey validator呼出しの欠落を新規テストが検出しない点、および終了時C04 validator例外の専用反証テスト不足。後者のB receipt改変側はHigh修正の回帰テストで補完したが、C04 validator直接例外の専用反証は未追加。

## 実行日の公開料金根拠

2026-11-15に資格なしHTTPSでAWS公式公開Price Listを再取得。既存費用文書のSKUのUSD単価は一致したが、一部原本は更新されhashが変わった。raw/抽出値の保護ローカルpathは `/private/tmp/fitlog-70-pricing-20261115/`。単価確認は実accountの提供状況・scan設定・総見積りの成立を意味しない。

| サービス/公式原本 | byte SHA256 |
|---|---|
| [ECS東京](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonECS/current/ap-northeast-1/index.json) | `560e09e496da9950a3160a6380e7ba909a8de1cf1d8c39e8caa653be18bfb28b` |
| [RDS東京](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonRDS/current/ap-northeast-1/index.json) | `6ccf063064259c27a45756f232f5c8c385ab5769d44c870c69ea2d37431c4653` |
| [ELB東京](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AWSELB/current/ap-northeast-1/index.json) | `921083dd201ba4534405b74438cd4eaa474e1d1a499a4a337f7b47c3017be58c` |
| [S3東京](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonS3/current/ap-northeast-1/index.json) | `06c83a4f67547235f84e0141a67050d7d04c95c1e00cd05ad8feb1802d7fc8f6` |
| [CloudWatch東京](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonCloudWatch/current/ap-northeast-1/index.json) | `e9ffc9580200c9790b42b92a9526f31e21dde08bf7d98846cf898ed33deb0551` |
| [Secrets Manager東京](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AWSSecretsManager/current/ap-northeast-1/index.json) | `fe70549de5e76b2fa8fa0cd152e856cc6840fc979f1b6204b52968791d80851a` |
| [CloudFront](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonCloudFront/current/index.json) | `17e3e9aeb5add88d1f6ba78f7fdcfb2405a83a9388228adc46c8ae09da9ca2ce` |

単価とquantity式は[設計の仮計算](aws-day70-design.md#料金と時間の提案承認値ではない)を参照。本人の5USD上限へ拘束する正式E費用は、R結果・撮影窓・閉鎖猶予・残存期間・未積算項目・予備費を含めて構築前に提示する。無料枠/creditを予算成立の根拠にしない。
