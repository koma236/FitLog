# 2構築分のAWS費用試算

最終更新2026-11-08 JST、Issue #55/#58/#67。下記単価の取得記録は従来#55の2026-11-07時点のもの。#58では再取得していない。#67で同じ公開Price ListのSKU/課金単位/USD値を再取得し一致を確認した（末尾参照）。東京Linux/x86オンデマンド、無料枠/credit控除なし。
実account/role/予算/期限は未決、実AWS未承認。仮定数量の感度分析であり請求額/hard cap保証ではない。
再計算: `python3 -B scripts/prebilling/readiness.py`。

実申請は[調査・実操作承認案](aws-execution-approval-draft.md)に集約する。本表の感度分析は#66のprobe/fixture費用、実one-off数、調査・請求照会、予備費が未確定のため総予算ではない。

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

## ローカルscenario検査（Issue #58）

```sh
python3 -B scripts/prebilling/readiness.py --scenario scripts/prebilling/scenario.example.json
python3 -B -m unittest discover -s scripts/prebilling -p 'test_*.py'
```

接続optionはない。既存draft検査とcost_sensitivityを維持し、scenario指定時だけ`scenario`結果を追加する。draft失敗、不正scenario、予算超過はexit1。成功時も`aws=not_run/approval=未承認/readiness=未決`。エラー時に入力本文を出さない。

schema v1の全項目は[架空サンプル](../scripts/prebilling/scenario.example.json)。deployment manifestとは別形式で、未知key/重複keyを拒否する。`builds`は異なるFitLog環境名2件。各`hours`はstart〜destroyまでの見積り時間以上、`start_at < close_start_at < public_end_at < destroy_by`、初回destroy_by≤再構築startを満たす。時刻は`Z`または`±HH:MM`（時00〜23・分00〜59）のoffset必須でUTC換算して比較。`+00:99`等をdatetimeが正規化する前に拒否する。過去の架空日時も計算例として受け入れるため、実承認期限の有効性検査には使わない。

USD/時間は整数9桁・小数6桁以内の非負固定小数字符列。hours/budgetは正値。数値型/bool/null/指数/NaN/Infinity/符号/空白は拒否。精度50で中間丸めを拒否し、予算は表示丸め前に比較する。`estimate_exact_usd`は計算値、`estimate_usd`はUSD小数2桁切上げ。1.900001は予算1.900000を超える。

式は`Σ(hours_i×hourly_usd+one_off_usd_i+variable_usd_i)+residual_usd+contingency_usd`。サンプルは手計算`2×(4×0.10+0.02+0.03)+0.90+0.10=1.90 USD`の検算専用。実料金の見積りではない。

根拠台帳は各金額に`service/region/unit_price/source_url/checked_at/quantity/duration/subtotal/included_in`を付け、上の既存数量表から追跡する。`hourly_usd`はALB/RDS/storage/通常Web/public IPv4等、`one_off_usd`は更新追加task・bootstrap/migrate/seed/check/verify等の全taskの実見積り時間、`variable_usd`は各回の要求/転送/取込、`residual_usd`は中間・終了後のsnapshot/backup/S3/ECR/log/未削除secret等の総額、`contingency_usd`は明示した余裕とする。欠落/二重計上を照合し、残存7日や各構築4時間は仮定として扱う。
Cの別distribution/対照fixture/試験要求/負荷上限とBのtask時間は受領後に加算する。未受領なら見積り未完。再build/送信も2回計上する。JPY/税/為替は参考額でUSDと混ぜない。実行日の単価・数量・閉鎖猶予を再確認し、残存上限/消滅確認日を含む予算を別承認する。Budget通知とこのローカル検査はhard capではない。


## #67：公開料金の再確認と実申請用内訳

2026-11-07、資格なしのHTTPSで上記7サービスの公開Price Listを再取得し、列挙済みSKUのOnDemand USD/単位/対象regionを照合した。publicationは上の記録と同じで、単価変更なし。原本JSONと抽出値・SHA256はローカル `/private/tmp/fitlog-67-pricing/` に保存。これはaccountの提供状況・請求単価の実調査ではない。実操作日に再確認する。

| 公開Price List | 原本SHA256 |
|---|---|
| AmazonECS | `00047d52a0649ef2b12956eeba00d7a0ad26730ae2e554c2e289b2f722a00115` |
| AmazonRDS | `7a77dc0c23c25332f4ceffd818924e99ab6c60db82feb1073ad59530c238aed5` |
| AWSELB | `a3086880e503b007184f4b1988d17d13b72841e5458dca74ca3246183d32200c` |
| AmazonS3 | `420ad567690506adf50142d6ac44a62760095fab4a3d5964768b55fa02c0eae2` |
| AmazonCloudWatch | `e9ffc9580200c9790b42b92a9526f31e21dde08bf7d98846cf898ed33deb0551` |
| AWSSecretsManager | `e8f9173a1d39593f4038f3065dc5083b8a6204c4c905d05746cf3b20c42d403b` |
| AmazonCloudFront | `17e3e9aeb5add88d1f6ba78f7fdcfb2405a83a9388228adc46c8ae09da9ca2ce` |

[IPv4公式](https://aws.amazon.com/vpc/pricing/)の0.005 USD/address時と秒単位/最低60秒、[ECR公式](https://aws.amazon.com/ecr/pricing/)のprivate storage 0.10 USD/GB月・同region転送、[Fargate公式](https://aws.amazon.com/fargate/pricing/)のLinux秒単位/最低60秒を再確認。Fargate課金時間にはimage取得開始からtask終了までを含め、アプリ処理時間だけにしない。RDS gp3/backupと保存容量は月額730時間按分の試算であり実請求の丸めではない。

実申請は以下の**初回/再構築別の数量表**を埋める。単価確認済みでも数量未確定なら総額を確定しない。既存4h×2の2.1325 USDは比較用基礎値で、追加項目込みの上限として採用しない。

| 費目 | 初回と再構築それぞれの基礎仮定 | 正式申請で置換/追加する数量 |
|---|---|---|
| Web通常/task更新/one-off | 通常1×h、追加task合計0.5 task時の感度分析 | 通常0.25vCPU/1GiB、更新最大2の重複task時、bootstrap/migrate/seed/check/verify/permission/IPごとの件数・起動含む時間。fixture分も別計上 |
| ALB/LCU/IPv4 | ALB1・LCU1・IPv4最低3×h | 初回/再構築のstart〜実消滅、LCU枠、ALB増設address数、更新/one-off address時。部分時間切上げの余裕 |
| RDS/storage/backup | micro1×h、gp3 20GiB | 取得minor/classの単価、CPU credit、保持backup容量/期間。DB停止後もstorage課金 |
| S3 | 2bucket合計0.2GB、PUT/LIST1000、GET10000 | static/media/fixtureの実GB、全version/delete marker/upload残存、各request数と保持時間 |
| ECR/scan | 0.5GB/環境、基本料金の仮定 | 各回の実image容量・保持期間、基本/拡張scan設定/数量。拡張scan不明を0としない |
| log/secret/API | log取込0.1GB・保持0.1GB、app/master2・API100 | fixture secret、実取込/保持GB/期間/API、未予約secretの保持期間。予約削除中の非課金と区別 |
| CloudFront/転送 | 日本HTTPS10000、viewer1GB、origin0.1GB | 主/対照distributionの要求・GB、Function実行、無効化等の有料条件、uploadとリージョン/AZ間の課金経路 |
| 中間/終了後残存 | 間隔4h、snapshot20GB×2とS3/ECR/logを7日保持 | 実棚卸し量/実保持期限に置換。automated backup40GB×1日なら約0.1249 USDを追加（比較例） |
| 調査/後日照会 | 基礎感度分析に未算入 | R read APIの課金有無確認、EのCE request/page数、照会有効窓。担当指定 |
| 予備費/為替/税 | 未算入 | USD予備費、停止判断閾値、USD全体上限、JPY為替日・税・余裕は別欄 |

`総見積USD = 初回の時間費+one-off+変動費 + 再構築の時間費+one-off+変動費 + 中間残存 + 終了後残存 + 調査 + 後日照会 + #66追加分 + 予備費`。既存項目に含めたfixture/残存は再加算せず対応欄を示す。未知値は未確定であり総額計算を保留する。scenario v1には共通hourlyを使えるときだけ落とし込み、各回の差額はone_off/variable、全期間の調査/照会はvariableまたはcontingencyへ根拠付きで配賦し二重計上しない。schemaは増やさない。

[Cost Explorer公式料金](https://aws.amazon.com/aws-cost-management/aws-cost-explorer/pricing/)を2026-11-07確認。primary billing viewは1 requestにつき0.01 USD、custom viewはsourceごとの加算があるため今回採用せず、primary viewのページ/再試行を含む件数を承認する。例：primaryの3回×各1ページなら0.03 USDであり、これは実照会の許可や件数確定ではない。Cost Explorer設定/粒度/課金tagを変更する操作は含めない。

#66契約の要求/最大応答量は下記で照合済み。fixture数量/時間はEへ提案し、実数量/保持期間/metadata費用、Bのone-off時間、R調査費/期間、USD上限は未確定。上限到達後に止めるのでなく、見込総額と閉鎖/破棄の必要費用を監視して承認された早期停止閾値で新規作業を止める。Budgets通知は補助でありhard capではない。申請の指定待ち一覧と停止条件は[承認案](aws-execution-approval-draft.md)を正とする。

## #66統合後の追加数量・配賦（2026-11-08照合）

PR #69、統合commit `aadcf26a1d317f3baca3ac3cf1eb50b4681ccbb4` の[C04観測契約](aws-c-boundary-contract.md)を受領した。C02の8要求は既存C予算内。C04の9要求/環境、API・fixture作成/伝播/削除はA追加枠であり、既存Cの3000要求/20MiB/45分へ暗黙加算しない。

| 費目 | 1環境 / 2環境 | 費用への対応 |
|---|---|---|
| C04 HTTP | ALB2・task1・S3匿名2・CloudFront4 = 9 / 18要求 | CloudFront HTTPS4×0.012/10000、S3匿名GET2×0.0037/10000を変動費へ。ALB分は既存LCU予算に収まるか再評価し、超過分のみ追加。送受信・task/ALB pathの課金経路も確認 |
| 応答/送信 | 応答144KiB / 288KiB以内。送信64KiB / 128KiBの提案 | CloudFront viewer応答だけなら64KiB / 128KiB以内を日本viewer単価へ。全9要求のbytesを全部CloudFront転送へ二重配賦しない。エラー応答/headers/関連APIの量も別途確認 |
| fixture storage/PUT | static/media各1点・各16KiB以内 = 32KiB / 64KiB以内の提案 | S3 PUT2/環境とHead/Get metadata・保持GB時を追加。known objectは新規利用者画像と別枠。承認済み既存object流用時は容量を重複加算しない |
| 別distribution/OAC | 各1 / 各2の専用資源を提案。新規Function0 | 対照distributionの実HTTPS要求/転送、API/伝播poll/閉鎖/削除を配賦。API/resourceを未確認のまま一括0 USDとしない。正規LIVE Function参照とviewer追加2回/環境のFunction実行費も確認 |
| metadata/fixture API | 作成/確認/poll/削除/再試行込み200 / 400 HTTP要求以内の提案 | APIごとの件数・課金有無/単位をE付属表で確定。S3 Get/Head等を上記と二重計上しない。B one-offは別枠、追加task0.5hで代替しない |
| 時間/残存 | 観測/metadata再確認10分以内、fixtureは構築開始〜destroy_byの4h内数の提案 | 作成・伝播待ちを含む実寿命で試算。C窓内のA一時返却、残枠と片付け猶予を確保。削除未確認のobject/distribution/OACは残存費/確認窓へ移す |

2026-11-07に確認した既存単価を使う検算では、C04のCloudFront/S3匿名要求分は `4×0.0000012 + 2×0.00000037 = 0.00000554 USD/環境`、2環境0.00001108 USD。CloudFront viewer応答64KiBなら `65536/1073741824×0.114 = 0.0000069580078125 USD/環境`。いずれも費目の一部だけであり**追加枠の総額でも承認上限でもない**。新しい単価取得の主張ではなく、7日の原本による数量検算。実操作日に単価を再照合する。

実配分はEの200要求上限を各APIへ割当て、最低50要求/環境の片付け枠を確保する提案とする。上限で足りない場合に無断拡張せず、実行前に申請へ戻す。任意のUSD値を作らず、既知費目+未確定費目+予備費+残存/請求を区別して全体上限を具体承認する。#66依存の契約照合は完了したが、R/E値・実資源・実AWS費用の成立は未確認。
