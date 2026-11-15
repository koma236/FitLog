# Issue #70：1回構築・本人撮影・短期削除の設計案

初稿2026-11-09 JST、更新2026-11-15。以下の旧案は最新の本人回答・実装記録が優先。実AWSは許可済みSTS照合のみ、構築/送信/公開/削除は未実行。

## 2026-11-15の本人回答による更新（以下の旧日時・未決欄より優先）

### 個人accountとローカルprofileの確認（本人の追加回答）

- 本人が `800411048502` を個人アカウントと明示。
- 本人の「はい、よいです」により、ローカル個人AWS設定のprofile名/account/roleだけの読取りを許可。これは設計全体・STSその他AWS API・構築の承認ではない。
- `/Users/saki/.aws/config` と `/Users/saki/.aws/credentials` のprofile見出しを照合した結果、定義は `default` のみ。configのregionは `ap-northeast-1`、role_arn/sso_account_id/sso_role_name/source_profile/sso_sessionの設定はなく、credential_processも設定なし。資格値は表示・記録していない。
- `AWS_PROFILE` は未指定。今回のSTS照合は `--profile default` を明示し、暗黙fallbackとは区別した。本人の「許可します」を受け、東京公式endpoint `https://sts.ap-northeast-1.amazonaws.com` の `sts:GetCallerIdentity` を再試行上限1で実行した。
- 2026-11-15 11:42 JST（記録時刻 `2026-11-15T02:42:35Z`）までに照合成功。Account=`800411048502`、Arn=`arn:aws:iam::800411048502:user/saki`。accountは本人指定と一致し、identityはIAMユーザー `saki`（root/AssumedRoleではない）。初回はCLI v1がv2用 `--no-cli-pager` を接続前に拒否したため、同オプションだけを除き実行。成功したAWS要求はこの照合1回だけ。
- 既存設計はoperator role前提なので、IAMユーザーを操作主体に採用するか、既存roleへ移るかは具体調査・操作前に確定する。STS成功を他API権限・構築許可の証拠にしない。IAM policyの取得・変更や追加調査は行っていない。

- 受領account IDは `800411048502`。本人が個人accountと明示し、STSでprofile `default` のaccount一致とIAMユーザー `saki` を確認済み。画像のロール名は省略されており完全role ARNは未確定。画像だけをAWS API許可と解釈しない。
- 本人指定の費用上限は **5 USD**。構築・検証・本人撮影中の稼働・閉鎖・削除・残存処理・予備費を全体上限へ含める。税を含む扱い、数量と残存期間、早期停止閾値は具体Eで明示し、全見込みが上限に収まらなければ構築しない。
- 本人の希望は「夜の撮影」「公開停止・削除完了は一両日中」。11月9日の期限は失効した。具体案は **11月15日夜に撮影、撮影終了連絡後に公開停止、11月16日23:59 JST（2026-11-16T14:59:00Z）までに削除・残存確認**。撮影開始/終了枠と公開停止の最遅時刻は本人確認待ち。この案は確定期限・実行許可ではない。
- 「当日削除」の旧要件は上記の短期削除希望へ変更。ただし撮影終了連絡待ちと公開停止の期限は別々に確定する。DB/ALBを翌日まで保持する可能性も費用に算入し、旧6hモデルをそのまま総額にしない。
- 以下の11月9日料金・0.9607 USDは過去の数量モデルの参考小計であり、11月15日の現行総見積りではない。実行日の公式料金と新しい期間で再計算して、構築前に提示する。
- 13:19 JST以降の本人「続けてください」により、確認済みIAMユーザーsakiを操作主体とするローカル開発を継続。具体AWS操作窓と追加R/E承認は未確定。先の独立設計レビューは11月9日版の結果として保持し、11月15日は規定の計画レビューを実施。AWS設定の限定読取りと許可済みSTS照合のみ実施済み。コードはローカル実装・検証中で、その他AWS API・送信・公開・削除は引き続きnot_run。

## 対象と承認

- Issue: #70。単独writer/operatorはこのCodexセッション。worktreeは `/Users/saki/.codex-personal/worktrees/f422/FitLog`、branchは `ops/aws-demo-day-70`、baselineは `03f0dae3eed00454ec54f76d09f2e79b39f37a6c`。
- 先行PR #61/#62/#63/#68/#69はbaselineに統合済み。既存A/B/Cの実装・契約を利用するが、旧2環境・撮影・性能・後日請求の全体完了を宣言しない。
- 1環境 `fitlog-demo-day70` を東京に一度だけ構築する提案。Terraform/Bの `fitlog-demo-` prefix・24文字以内の契約を満たす。CloudFront/IAMはglobal。本人へCloudFront既定HTTPS URLをこのチャットで渡す。public signupとCloudFront→ALBのHTTP区間は既存設計どおりで、承認対象として明記する。
- AIは録画しない。再構築、比較、Cost Explorer、後日の請求照会、定期実行は行わない。
- account/profile/完全operator role ARN、USD上限、操作開始/公開終了/破棄期限、本人撮影枠はユーザー指定待ち。既定資格へfallbackしない。指定確定までAWS設定・APIを調査しない。
- ローカル文書と検証用最小コードの開発承認と、実AWSの具体承認を区別する。調査R（旧案のread action表、1環境、200 HTTP要求・30分・再試行なしの提案）と構築Eを分ける。R結果でAZ/PG minor/CA/quota/scan/衝突を確定し、費用・対象action/ID・保存planを照合してからEの具体承認を受ける。未記入値への包括承認で実行しない。

## 実装範囲と実行順

1. 本書と当日運用記録を整備する。既存 `scripts/prebilling/readiness.py` の2構築必須scenarioやCのcapture必須契約を偽入力で通さない。今回の1回分の費用は独立した数量表で積算する。
2. Rで個人identity/role、2AZ、PG17完全minor/db.t4g.micro/gp3 20GiB/CA、quotaと使用量、環境名・snapshot・secret衝突、ECR基本/拡張scanを確認する。AccessDenied・不一致・不明は停止。IAM追加やaccount全体の設定変更は行わない。
3. Eで配置source完全OID、全作成/切替/削除action・prefix/tag・実IDへの拘束、期限と費用、秘密保管を確定する。repo外 `/private/tmp/fitlog-day70-<run UUID>/` を提案し親0700/file0600、state/plan/TF_DATA_DIR/manifestを保護する。生state/資格/secretをGitやチャットへ出さない。期間限定ではなく消去まで必要なstateは自動消去のない個人保護領域へ移すか、消去完了まで保持する。
4. 既存B手順に従いclean sourceのgit archiveだけからbuild。ECR限定保存plan→image push・実digest採取→全体非公開plan/apply（service0/public off/DB保護on）→inspect/static/bootstrap-inspect/bootstrap/migrate/seed/check→backend起動・DB verify→境界検査→一時公開→public inspectと実経路検証。
5. 合格した機能・URL・利用方法・撮影終了連絡の方法を通知する。撮影中はoperatorの構成変更/検証送信を止め、本人だけが操作する。試験用passwordは共有せず本人が自分の合成利用者を登録する。実在の個人情報をseedしない。
6. 本人の撮影終了連絡後、client終了を確認して閉鎖・停止・削除を実行する。公開終了期限まで連絡がない場合は事前承認した公開停止/task0だけを実行し、DB/データ破棄は本人連絡または別の明示指示を待つ。沈黙で撮影完了とみなさない。したがって当日削除には期限内の本人連絡が必要。

変更所有は `docs/aws-day70-*.md` と、必要な場合のみ録画なし検証用 `scripts/day70/`。Terraform・B/C契約・製品認証認可・migration・CI・ゲートは初期変更範囲外。既存コードを変更する必要が判明したら影響を説明し、範囲を確定する。単独operatorを維持し、子は読取り専用の規定レビューだけ。

## 録画なしの検証と独立oracle

`e2e/aws-runtime.py` はcaptureを必須とするため起動しない。既存Cの総合acceptanceを名乗らず、今回の観測結果を項目別に記録する。承認後に必要最小限の録画なしPlaywright/APIスモークを準備し、次を契約とする。

- 起動前にexact HTTPS origin、account/environment/run/source/digest、B public-health/DB/seed/static証跡を照合。redirectによるorigin逸脱、非HTTPS、期限切れを拒否する。単一client・retry0、trace/HAR/screenshot/video/storageState/raw DOM/認証値の保存なし。browserはservice workerをblockし、全requestを承認originのみに限定する。
- 独立oracleはOpenAPI、既存auth/profile/workout/media/socialテスト、`docs/aws-c-boundary-contract.md`。正常値を実装の出力から作らない。UIの描画/操作とサーバー状態の両方を確認する。
- HTTPS/static/SPA、APIのJSON404、live/ready・DB identity/TLS、登録/login/logout、Cookie属性、CSRF欠落/異origin拒否、他者更新拒否、投稿CRUD・画像up/read/delete・comment/like/followを2合成利用者で検証する。
- 上限は検証45分（末尾5分cleanup）、3000要求（cleanup200を留保）、送信20MiB、認証24回・rolling60秒8回、利用者2/投稿6/comment4/保存画像4・各64KiB。全clientに共通計数し、超過前に送信停止。性能試験は行わない。本人の撮影用登録は別1利用者・認証8回、投稿6/画像4・各64KiB、撮影窓最大1時間の提案。本人操作の要求数は厳密計測できないため料金は余裕付きで扱い、operator検証と重ねない。
- AのC04は専用object2点（各16KiB以下）と対照distribution/OAC各1を使い既存契約の9 GETを単独operatorが収集する。全SG attachment/ingress、Function LIVE hashと関連付け、正規/別distributionの同一object対照を含む原本を保護保存し既存 `e2e/aws_boundary.py` の検証器に照合する。metadata/fixture作成・伝播・削除をEのaction表/費用へ含める。
- Bのpermissions/IP probeも同じoperatorが既存手順で実施する。失敗・not_runをpassへ変更しない。検証失敗時は利用可能と通知せず、承認した閉鎖手順へ移る。
- 新しいスモークの単体検証は外部通信の境界をfixture化し、禁止origin/redirect、期限・回数超過、秘密非保存、録画off、client終了を反証項目として固定する。実AWS動作をfixtureで代替しない。

## 料金と時間の提案（承認値ではない）

2026-11-09 10:42〜10:43 JST、資格なしでAWS公式公開Price ListのECS/RDS/ELB/S3/CloudWatch/Secrets Manager/CloudFrontを再取得。既存 `docs/fl-10b-aws-costs.md` のSKUと単価は一致。原本と抽出値/hashは `/private/tmp/fitlog-70-pricing/`。IPv4/ECR/Function等の公式料金も確認して正式Eへ根拠を固定する。

数量案は構築〜消滅6時間、通常Web1、追加one-off/更新task合計2 task時、ALB1/LCU1/IPv4通常3（追加task分別）、DB micro/20GiB、static/media計0.2GB、ECR0.5GB、log取込0.1GB、secret2、HTTPS10000要求/viewer1GB/origin upload0.1GB。撮影・検証・削除poll・fixtureはこの数量に含め、超過見込みなら新規作業を止める。6時間内に十分な撮影/削除枠を取れるか実日時で再計算する。

| 費目 | 仮計算 USD |
|---|---:|
| Web vCPU/メモリ、DB/gp3、ALB/LCU、通常IPv4（6h） | 0.565505 |
| one-off/更新taskとIPv4（2 task時） | 0.046340 |
| log取込0.1GB | 0.076000 |
| HTTPS10000要求/viewer1GB/origin0.1GB | 0.132000 |
| S3 PUT等1000/GET等10000 | 0.008400 |
| secret保持/API100、S3/ECR/log保持（6h、730h月按分） | 0.007555 |
| snapshot20GB+retained backup20GBを削除待ち最大24hの感度枠 | 0.124932 |
| 既知小計（丸め表示） | 0.9607 |

**正式総額は未確定**。CPU credit、AZ間/関連転送、CloudFront Function、基本/拡張scan、fixture・metadata/poll等の未積算費用と予備費を足してEへ提示する。小計を総見積りや上限と呼ばない。無料枠/credit控除なし、税別USD。JPYへの換算は本人が必要とした場合に日時付き為替・税と分ける。上限と早期停止閾値は本人指定後に確定する。通知/ローカル計算はhard capではない。調査・実行・閉鎖・残存処理の全許可窓をUTC/JSTで固定し、期限外APIは行わない。

## 閉鎖・破棄・残存確認

1. 本人連絡/事前承認条件を照合、clientを停止。CloudFront disable→Deployed、ECS desired0→running/pending0、同runの全one-off停止を確認する。
2. DB削除保護解除の保存plan/apply→実offを確認。今回専用S3の全version/delete marker/multipart、ECR image/fixtureを実ID・所有と照合して清掃。通常destroyの保存planを確認して実行する。force_destroy追加/state編集/force-unlock/共有清掃は禁止。
3. 現行HCLは `skip_final_snapshot=false`、`delete_automated_backups=false`。destroy後に今回作成した最終snapshot ARNとDbiResourceIdに対応するretained automated backupを照会し、具体Eで承認された削除を実施する。既存snapshot/他runは触らない。撮影用データは捨てる前提を承認対象にする。
4. AWS正本とstateの双方で、RDS/snapshot/backup、S3全version/multipart、ECR/image/scan、logs、secret、ALB/TG/IPv4/ENI、ECS全task、CloudFront/Function/OAC、専用IAM/networkを棚卸しする。非秘密の台帳は `type/exact ID/owner/observed_at/status/quantity/delete_by/根拠/残費用/残件`。
5. secretは7日回復の削除予約を使い、当日物理消滅と称さない。予約中は非課金という公式仕様と実DeletionDateを記録する。翌日以降の自動照会は今回含めない。課金資源の消滅未確認、削除失敗、24hの仮残存枠超過は未完了として対象ID・費用を直ちに報告する。state空だけでは課金停止を宣言しない。

公式根拠: [RDS削除](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_DeleteInstance.html)、[secret削除](https://docs.aws.amazon.com/secretsmanager/latest/userguide/manage_delete-secret.html)、[IPv4](https://aws.amazon.com/vpc/pricing/)、[ECR](https://aws.amazon.com/ecr/pricing/)、[CloudFront](https://aws.amazon.com/cloudfront/pricing/pay-as-you-go/)。

## 短い実装計画・検証・完了

1. 独立設計レビュー→指摘対応/残件を設計と一括提示→設計承認。R/Eの必須値を確定する。
2. 録画なし検証の最小実装と当日runbook/費用根拠/残存台帳を整備する。test-design/TDDを使い、既存B/Cの公開契約を維持する。
3. 共通Git領域とruntime排他を確認し登録11 checks、関連Python/Nodeテスト・Terraform mock、ゲート回帰を実行。snapshotに結び付けた記録と規定quality-checkを残す。
4. R→具体E承認→非公開構築/配置→実経路検証→URL引渡し→本人撮影終了→閉鎖/破棄/棚卸し。既存手順の予算や停止条件を弱めない。
5. 最終品質レビュー・commit/feature push/PR。CI/ゲート等の対象変更が生じた場合はX2/相互レビュー待ちで止める。それ以外も既存merge条件を照合する。

レビュー起動目安は設計1、計画1、品質2〜3、High修正時は規定内の追加。実装は親が担当し同worktreeのwriterを増やさない。実機未実行・失敗を成功扱いしない。今回完了は1環境のURL提供・本人撮影終了連絡・課金対象の消滅確認と非課金残存の明示。旧Issue全体の完了とは別。

## 未決値

個人account/profile/role、予算、撮影枠、公開停止時刻/破棄期限、実source/全action/実ID、Rの実観測、未積算費目、予備費・早期停止閾値。これらは実行前の必須条件であり推測して埋めない。

## 独立設計レビュー

2026-11-09、helm-doc-reviewer（harness-runtime規定）による読取り専用レビュー1巡。review-budgetのdesign/document-reviewer予約と開始受付を正規台帳で確認済み。

- High 1件：初稿の環境名がTerraform/Bの必須prefixに不適合。`terraform/variables.tf:16`、`backend/operations/deployment_contract.py:98` と照合し `fitlog-demo-day70`（17文字）に修正。R衝突調査・E資源prefix・snapshot名もこの環境名から束縛する。
- その他のHigh/Mediumなし。録画なしの境界validator利用、本人連絡と期限、残存確認、小計と総額の区別を確認。
- 親による料金式のDecimal独立検算：既知小計 `0.9607309589041095890410958904 USD`。実AWSの料金成立・動作合格とは別。

上記は11月9日のレビュー時点の状態。11月15日の本人回答・実装状態は冒頭の更新と次の差異を参照。

## 実装時の差異

- 既存operator role前提 → STSで確認したIAMユーザーsakiを実操作候補に採用。既存IAM権限内だけを使い権限追加はしない。Bのaccount guardはIAMユーザーでも成立するが、追加調査・実操作の具体承認と有効権限確認は別途必要。
- 全く新しいPlaywrightスモーク → 既存journeyとguardを専用単一環境入口から録画offで再利用。既存Cのvalidator/2環境campaign/capture契約は変更せず、専用steps=[journey,cleanup]。C01/C02と既存journey全case/回復/cleanupを必須とし、C05/C06/C07をnot_runとして保持する。重複実装を減らし元の試験oracleを維持するため。
- 新CLIの固定エラーコード登録のため `documents/development/error-codes.md` も更新。ゲート制御面には該当しない。

計画レビューのHigh1件（C05が撮影結果なのにpassを要求していた矛盾）は必須条件と反証テストを修正。追加High/Mediumなし。追加R/Eの具体案・CLI・残存台帳は [当日runbook](aws-day70-runbook.md) を参照する。設計差異があるため、品質確認とPR作成後もmerge前で本人判断を待つ。
