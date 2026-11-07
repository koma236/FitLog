# AWS A: 基盤・費用・操作管理 詳細設計（承認済み）

2026-11-07。Issue #58。writerはA親セッションのみ。
worktree `/Users/saki/.codex-personal/worktrees/784f/FitLog`、branch `feat/aws-foundation-58`、baseline `4524ec2965f6ac46815815555942bd4deda87058`。
先行PR #56/#57は統合済み。2026-11-07、レビュー反映版をユーザーが「承認します」と承認。範囲内のローカル実装・検証・文書・Git/PR作業へ進む。実AWS API（読取り含む）、AWSへの送信、公開、破棄は別承認まで行わない。

## 1. 目的と選択

既存FL-09B2/B3/B4/B6/B7/B8を再利用し、初回と再構築の2環境について「誰が・どの対象を・どの承認・費用・期限で操作し、何を証拠に止めるか」を具体化する。
新しい配置エンジン、AWS接続CLI、remote backend、operator IAM自動作成は追加しない（Aの設計判断）。ローカル計算と運用文書に絞る。
現状のTerraformにはVPC/閉じたSG/S3/ECR/CloudFront/ALB/ECS/RDS/秘密コンテナ/専用bootstrap runner/非秘密outputsが揃っており、新規HCL資源やoutputの追加は現時点で不要。
不足は実提供/権限確認、保護stateの明示指定、費用仮定の入力化、2構築の期限・残存台帳、担当間の引渡し。Terraform 1.15.1/provider 6.71.0・既存lock・CA同梱を維持する。例外としてlocal backendの空の明示宣言だけを`terraform/backend.tf`に追加し、環境別pathを初期化時に渡せるようにする。AWS資源/権限/outputの変更はしない。

## 2. 所有・依存

| 担当 | 所有・契約 |
|---|---|
| A #58 | `terraform/**`、`scripts/prebilling/**`、`docs/aws-a-*.md`、`docs/fl-09b8-prebilling-readiness.md`、`docs/fl-10b-aws-costs.md`、`docs/fl-09b7-aws-approval-template.md`。本計画の実編集はbackend宣言・関連ローカルテスト/README、prebillingと列挙文書。terraformの既存検証も実施する |
| B #59 | `scripts/deployment/**`、`backend/operations/**`、関連backend tests、B専用文書と既存配置/bootstrap runbook。Aは変更しない。配置CLIのschema/工程証跡/応答不明収集の正本 |
| C #60 | `e2e/**`、`perf/**`、C専用文書・撮影/性能手順、最終統合時の横断README/acceptance/production-readiness。Aは変更しない |

CI/ゲート/Compose/依存lock/OpenAPI/製品認証認可/DB migrationは変更しない。共有文書の重複編集を避け、A専用runbookからB/C正本を参照する。
実装準備は並行可能。実操作はAの構築→Bの配置手順をAが実行→Cの試験→Aの退避/破棄→新環境で反復。AWS構成変更operatorはAだけ。CはAが割り当てた窓内で試験通信のみ行う。
B/Cで必要資源・権限・上限が増える場合は自動拡張せず契約を照合し、範囲変更なら設計承認を取り直す。先行PR未mergeの実装/成功を採用済みと呼ばない。

## 3. 実AWS承認を分離する

開発設計の承認と実操作の承認は別。未決値を架空値で埋めない。

1. **調査許可**: 個人account/既存operator role完全ARN・対象region・許可read API・時間窓を埋め、読取り接続だけを別承認。STS identity一致を最初に確認し、不一致なら以後のAPIを呼ばない。AssumedRole ARNは想定IAM roleと対応照合し、別account/root/別roleは拒否。role作成/権限変更は含めない。
2. **実操作許可**: 調査結果とB/Cの必要時間・fixture・要求/利用者/負荷上限を集め、2構築のUSD上限、公開/閉鎖/破棄期限、残存上限/期限、対象資源、各操作、障害退避、再構築、削除対象を申請書へ記入して別承認。許可されない工程は実行しない。

調査項目: EC2の通常Tokyo AZ2つと利用可能状態、RDS PostgreSQL17完全minor・db.t4g.micro・20GiB gp3・指定CAのorderable対応と証明書期限、Fargate/ALB/SG/VPC/RDS/IPv4のquotaと使用量、CloudFront origin-facing prefix listとSG rule枠、同名資源・snapshot/削除予約secretの衝突、ECR scan設定、実行roleの必要権限。
CA公開bundleの固定hash/期限は既存`backend/certs/README.md`へ照合し、更新が必要ならBの担当変更として調整する。
公開公式資料の閲覧と資格不要なローカルmockだけではaccount固有の提供/権限を確認済みとしない。AccessDenied/不明quota/対応なしは停止。quota引上げ・class/minor/CA変更へ自動fallbackしない。

operator権限表はA専用runbookにAPI/対象/目的/限定不能箇所を列挙する。Terraformの対象資源CRUD、ECR push、static配置、既存BのRunTask/Describe/List/StopTask/log読取り、限定PassRole、承認済みfixture、破棄/残存読取り・削除を別工程に整理。PassRoleは既存Web/bootstrap task/executionの完全ARNと`iam:PassedToService=ecs-tasks.amazonaws.com`へ限定。Web roleを拡張しない。広い管理者権限や権限シミュレーションだけを成立証拠にしない。

## 4. state・planと担当間契約

環境ごとにrepo外の正規絶対pathの0700 directoryを使い、state/tfvars/saved plan/backup/生のplan JSONは秘密資料として0600（読取り専用stateは0400も許容）。owner一致・非symlinkを確認。保護されない同期folderやGit/CI artifactへ保存しない。
`terraform/backend.tf`に`terraform { backend "local" {} }`を明示し、実操作手順では`init -backend-config=path=<保護state絶対path>`を必須にする。環境ごとのTF_DATA_DIRも保護folder内へ置き、plan/apply/destroy前に記録されたbackend pathとdefault workspaceを照合する。既定`terraform/terraform.tfstate`を認めない。初回/再構築のstateは混ぜずworkspace切替に依存しない。既存stateが発見されたら移行せず停止する。CI/mockは従来どおり`init -backend=false`を維持。
保存planを使い、apply前にsource/vars/plan hash・state lineage/serial/hash・承認・対象を照合。通常全体planで意図しない置換/削除/公開/別環境を認めない。ECR初回だけBの既存`check_plan.py`でcreate1件限定を確認し、架空digestを全体applyへ持ち込まない。stateを手で編集/削除、force-unlock、refresh=falseによる回避はしない。
plan/showのraw出力・origin secret・tfvarsを共有せず、保護folder内で確認する。毎apply後にstate hashと変更履歴を更新し、Bの既存同run bindingを壊さずmanifestの更新許容項目だけを更新する。

**Bへの引渡し**（既存`Manifest` schema v1を再実装/変更しない）:

- `account/region/environment/run_id/bootstrap_id/source_revision/image_digest/frontend_sha256`。source/digest/static hashはBのclean build証拠をAが照合。bootstrap UUIDは同環境再開では維持。
- `resources`: `distribution`←distribution.id、`database_host/master_secret`←database、`application_secret`←application_secret_arn、`backend_task`←backend_service.task_definition、`bootstrap_task`←bootstrap_runner.task_definition、`subnets`←public_subnet_idsの値2つ、`security_group`←security_group_ids.app。
- `state.path/sha256`、`approval.reference/budget_usd/expires_at/steps`。stepsは既存8工程の許可部分集合。Terraform公開・破棄は別の実操作承認で管理する。
- manifest外のA運用台帳でrole ARNs、cluster/service、bucket/ECR、exact HTTPS origin、公開/閉鎖/破棄期限、操作窓、A/B/C証跡参照を記録。秘密値とraw stateは渡さない。

CにはBのhealth/seed/verify証拠、同一environment/run/source/digest、exact HTTPS origin、試験窓と上限を渡す。CがBのverifyを重複実装しない。B/Cの契約案が未確定の間は実行準備完了とはしない。

## 5. 工程と失敗時動作（将来の別承認後だけ）

| 工程 | 開始条件・成功証拠・停止条件 |
|---|---|
| 初回ECR→非公開構築 | 保存plan承認、ECR限定作成後Bのimage送信手順、実digest/source照合。通常全体planでservice/proxy/public=false、DB削除保護true。apply成功だけを稼働成功にしない |
| 配置/初期化 | B CLIのinspect→static→bootstrap-inspect→bootstrap→migrate→seed→check。Aが操作、B既存のintent/remote event/task exit/digestで判断。応答不明は新taskを起動せず収集手順へ |
| backend→一時公開 | service/proxy=true、public=falseでbackend verify。次に公開対象の別許可を照合してpublic=true、Deployed後Cの限定試験。ALB liveとDB/S3 readinessを区別。成功前にURLを対外共有しない |
| 失敗/期限前退避 | 新規配置/試験を停止。distribution無効→Deployed、service0→running/pending0、B intent/runのone-off taskも停止・結果収集。Terraform applyだけでは実停止としない。失敗/不明は保持し報告。退避不能は未完了、権限拡張や勝手な削除はしない |
| 破棄 | 実測停止確認後だけallow_database_teardown=trueの保存plan/apply→削除保護off確認→通常destroyの保存plan。承認済み専用S3の全version/delete marker/未完了multipart、ECR/fixtureの片付けを先に行う。force_destroyや一括account清掃は使わない。final snapshotと保持backupは残存台帳に記録 |
| 再構築 | 初回閉鎖・破棄と残存棚卸し後、異なるenvironment/state/run/bootstrap UUID/final snapshot名で同じ承認sourceからBの既存手順で再build・配置し再検証。各回の実image digest/static hashを新規取得し、新環境のmanifest・tfvars・実操作承認対象へ拘束する。同sourceだけで同一digest/同一byteを保証しない。旧環境成功証跡をコピーしない |
| 後日確認 | 各回の残存台帳とAWS対象IDを再照合。snapshot/backup/S3/ECR/log/secret/ALB/ENI/IPv4等の消滅または保持理由と期限を記録。遅延請求を確認し、stateが空やECS0だけで課金停止とはしない |

実AWSはA単独operator・同時実行なし。ローカルの共有runtimeは既存共通Git領域のruntime lockを使う。実AWSの単独操作はローカルruntime lockで保証できないため、実操作申請にoperator/開始終了/休止/再開記録を置き、B/Cの窓を重ねない。
CloudFront停止/DB削除には時間がかかるため、閉鎖開始の締切を公開期限より前に確保し、締切時刻そのものを申請へ記入。超過予測で新規作業を打切り退避する。承認切れのcleanupが必要にならないよう退避・破棄の有効期間を別途確保し、切れた場合は新しい許可なくAPIを続けない。

## 6. オフライン費用・readiness補強

`scripts/prebilling/readiness.py`の既存draft呼出し・`sensitivity()/two_builds()`を再利用。既存引数と出力の意味を維持し、AWS接続/資格取得opt-inは作らない。
追加`--scenario <JSON>`は仮定費用・期限・B/C調整の**ローカル検査**用。既存deployment manifestとは別。既存schemaに未知keyを足さない。

scenario v1: `schema_version`、`builds`（正確に2件）、`hourly_usd`、`residual_usd`、`contingency_usd`、`budget_usd`。各buildは`environment`、`hours`、`one_off_usd`、`variable_usd`、`start_at`、`close_start_at`、`public_end_at`、`destroy_by`。USD/数量は有限非負Decimal文字列、hours>0、budget>0。環境名は既存Terraform制約・2件で相違、時刻はoffset必須。start<close_start<public_end<destroy_by、初回destroy_by<=再構築start。仮定hoursはstart〜destroy_by以上とする。未知key/重複JSON key/bool数値/NaN/Infinity/負数/不正TZ/欠損を拒否し、入力本文はログへ出さない。
数値文字列は`[0-9]{1,9}(\.[0-9]{1,6})?`に限定（指数/符号/空白を拒否）。USD・hoursとも整数9桁/小数6桁以内、入力長16文字以内。演算はlocalcontext精度50で行い、Inexact/Rounded/InvalidOperation/Overflowを例外として拒否する。2項の積和はこの範囲で中間丸めを生じない。式は`Σ(hours_i × hourly_usd + one_off_i + variable_i) + residual_usd + contingency_usd`。既存同一仮定2構築ならtwo_buildsと整合する。比較は表示丸め前、表示USDは別contextで小数2桁に切上げ。超過はexit非0。`budget=1.900000/estimate=1.900001`の境界と最大桁/指数拒否も検査する。既存readiness成功も`aws=not_run/approval=未承認/readiness=未決`を維持する。scenario合格を実行許可にしない。
hourly/one_off/variable/residualの根拠は費用文書の数量表で人が追跡可能にする。開始〜destroyまでのALB/RDS/IPv4、更新最大2taskとbootstrap/verify task時間、2回の転送/要求/画像/log、final snapshot・backup・削除待ち以外のsecret等を計上。Cの対照distribution/fixture/負荷は未決として追加見積り必須。税/為替は参考欄へ分離。既存単価は過去試算として保持し、今回新単価の正確性を主張しない。
提案は各構築4時間以内、残存7日を比較の出発点にするが、実時間・USD上限・残存削除日と担当は実操作前の別承認で決める。Budget通知をhard capにしない。

## 7. 受入条件と検証オラクル

- 新規prebilling負例: 型/未知・重複key/不正金額/時刻順序/環境重複/予算超過/丸め境界を拒否。独立した手計算例（2×(4×0.10+0.02+0.03)+0.90+0.10=1.90 USD）と既存同一条件の結果で正例を確認する。入力欠損は未決と拒否を混同しない（既存draftは未決を許容、scenario指定時は全項目必須）。
- 既存draft検査の失敗を保持、CLI出力に入力本文/秘密を中継しない。AWS SDK/credential解決/接続経路を追加しないことを差分とsubprocess呼出しで確認。
- Terraform既存入力負例/依存グラフ/mock/Functionは`.github/ci/terraform-checks.sh`の資格を除いた既存入口で再実行。実AWS plan/apply/destroyやprovider実問い合わせへfallbackしない。
- prebilling unittest、deployment既存標準unittest（read-only再利用）、登録11 checksとゲート回帰は承認後に実施。共有runtimeのchecksは`run-checks.py`の既存排他内。snapshotに対応する結果を保存する。
- 最終quality-checkとtest-recommendationを通常実施。「スピード感」は品質省略の指定とは扱わない。実AWS/E2E/配置/撮影/性能/破棄/請求確認は別承認までnot_run。

## 8. 短い実装計画（承認後）

1. 既存Issue/branch/baseline/所有を再照合。B/C契約に差分があれば影響を記録し、A専用運用runbookへ工程別権限・保護backend・引渡し・停止/残存台帳の具体例を作る。local backend宣言と、AWS providerを含まない隔離fixtureによる2環境state分離/保存plan適用先の検査を追加する。fixtureでは実AWSへ接続しない。
2. prebillingのscenario正負例を先に追加し、既存計算を再利用してローカル入力/予算・期限検査を実装。公開サンプルは架空値で実承認とは区別。
3. A所有のreadiness/費用/申請書とTerraform READMEを更新。B/C文書はリンク参照し、要望と未決値をA契約へ集約する。backend宣言以外のHCL変更が必要と判明したら自動で範囲を広げない。
4. 上記検証→通常quality-check/独立品質レビュー→記録・commit・feature push・PR。高リスク対象が生じれば既存の相互レビュー待ちを守る。実AWS操作は開発承認に含めない。

## 9. 公式根拠（公開文書のみ確認）

- [Terraform plan](https://developer.hashicorp.com/terraform/cli/commands/plan): 保存planは秘密入力を含み得るため保護する。
- [CloudFront managed prefix list](https://docs.aws.amazon.com/vpc/latest/userguide/working-with-aws-managed-prefix-lists.html): weight55。実quotaと使用量は将来確認。
- [RDS停止](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_StopInstance.html): 最長7日、storage/backup課金は残る。
- [RDS削除](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_DeleteInstance.html): 削除保護解除・final snapshot/保持backupを別管理。
- [Secrets Manager削除](https://docs.aws.amazon.com/secretsmanager/latest/userguide/manage_delete-secret.html): 最低7日回復期間、削除予約中は課金なし。即時消滅とは区別。

## 独立設計レビュー

2026-11-07、`helm-doc-reviewer`（gpt-6.1-sol/high）1体による独立読取りレビューを実施。design 1/1。marker `HELM_REVIEW:6521eeb28ef6277d3d8ec732d0dddc32:document-reviewer`。台帳のused/receipt/agent登録を確認済み。

- **High 1件**: 初回ECR削除後、同sourceの再buildで同一image digestを保証できない。対処: 同一digestを2環境で要求する条件を削除し、各環境でBの既存clean build→digest/static hash取得→承認対象/manifest/tfvars照合を行う設計へ修正した。目的は同sourceからの構築・基本動作再現であり、byte同一性ではない（Aの判断・今回の承認対象）。新しいimage保存/転送処理やBの変更は増やさない。実操作許可が初回digestだけに限定されていれば再構築分を別途承認するまで停止する。
- **Medium 1件**: Decimal入力桁数/指数/演算精度が未定義。対処案を明記: 固定小数・整数9桁/小数6桁以内、指数拒否、精度50・中間丸め例外、表示のみ切上げ、微小予算超過の負例を追加する。追加レビューは行わず、扱いを含めてユーザー承認へ提示する。

Manifest/outputs対応・state保護・担当境界について追加High/Mediumなしとの結果。修正後の再レビューは未実施。レビュー上限の追加予約や自己通過判定はしていない。今回は設計文書1件だけを作成し、実装/テスト/実AWS/共有runtime操作は未実施。公開公式文書の閲覧は実AWS操作に含めていない。codex-trust診断はnpxが完了せず中断したため未確認（レビュー正式受付の台帳確認と区別）。

## 実装時の差異

差異なし。検証結果は[実装・品質記録](aws-a-results.md)、実操作準備は[A runbook](aws-a-operations.md)を参照。
