# Issue #49 setup-terraform v4対応：仕様・設計・実装計画

状態: 2026-11-06、独立設計レビューと仕様・設計・短い実装計画を提示し、ユーザーが「はい、進めてください」と承認。承認範囲内の実装・検証・PR作成を進め、手動相互レビュー待ちで停止する。

## 担当と前提

- 担当B、Issue: https://github.com/koma236/FitLog/issues/49
- worktree: `/Users/saki/.codex-personal/worktrees/7f90/FitLog`
- branch: `ci/setup-terraform-v4-49`
- baseline: `2b80ae9cdf8f07e290a20181e8a208347b2aeea5`（PR #50統合後）。Issue/branch作成済みで追加作成不要。
- `CODEX_HOME=/Users/saki/.codex-personal`、対象 `koma236/FitLog`。GitHubのaccount/repoを読取り確認済み。
- writerは親セッション1つ。独立設計レビュアーは読取りのみ。Aの共通進捗文書は編集しない。
- 統合順はB→A。AがB統合後のmainを取り込み再検証する。Bは他worktreeの変更を取り込まない。

## 1. 目的と受け入れ条件

現行setup-terraform v3はNode.js20を使用する。Issue記載の既存CI run `42163045621` では旧Node.js20警告が出た。v4.0.1へ完全SHA固定で移行し、同actionに対する警告が新しいPRの実CI runで消えることを確認する。

1. v4.0.1の公式tagがcommit `dfe3c3f87815947d99a8997f908cb6525fc44e9e` を指し、そのcommitのaction.ymlが `runs.using: node24` であることを照合する。
2. workflowと検査器が同じ完全SHAを要求する。v3、可変tag、別SHAを受理しない。
3. workflow正例/負例、安全入口14ケース、集約64状態と不正入力、Terraformの実mockテスト、Functionテストが成功する。
4. 正規11 checksとquality-checkを完了し、PRのbackend/frontend/terraform/ci-requiredが同じ対象headで全成功する。
5. 手動相互レビュー待ちで停止し、CI変更に対するX2承認を維持する。レビュー待ちからの自動再開・自動mergeは行わない。

## 2. 公式根拠と設計判断

2026-11-06、GitHub APIで公式 `git/ref/tags/v4.0.1` を照合し、object.type=commitと上記完全SHAを確認。同commitのaction.ymlでnode24、terraform_version入力、terraform_wrapper入力を確認した。

- [公式v4.0.1リリース](https://github.com/hashicorp/setup-terraform/releases/tag/v4.0.1): Node24のDEP0169警告を依存更新で修正。
- [固定commitのaction.yml](https://github.com/hashicorp/setup-terraform/blob/dfe3c3f87815947d99a8997f908cb6525fc44e9e/action.yml): `runs.using: node24`。
- [公式v4.0.0リリース](https://github.com/hashicorp/setup-terraform/releases/tag/v4.0.0): Node.js24への移行。

Issueで指定されたv4.0.1を採用する。可変v4や別パッチへの自動追従はしない。実装開始時にも公式参照を再照合し、不一致なら無断で別SHAへ変更せず報告する。runnerは既存のGitHub hosted `ubuntu-24.04` を維持する。実行互換性の最終根拠は実CI成功とする。

## 3. 変更範囲と維持する契約

| ファイル | 変更 |
|---|---|
| `.github/workflows/ci.yml` | setup-terraformの完全SHAと説明コメントをv4.0.1へ更新 |
| `.github/ci/check-workflow.cjs` | setupの厳密な期待SHAだけを同期更新。完全一致の制約を維持 |
| `.github/ci/test-workflow.cjs` | v3固定SHAへの後退、可変v4/v4.0.1、別の40桁SHAを拒否する負例を追加。既存負例を維持し件数表示を整合 |
| `docs/issue-49-setup-terraform-v4-design.md` | 本設計・承認・レビュー・検証結果の記録 |

以下は変更しない: Terraform **1.15.1**、AWS provider **6.71.0**、Terraform定義・lock、`terraform_wrapper: false`、checkoutの完全SHAとpersist-credentials=false、contents:read、トリガー、実行順・timeout・concurrency、登録11 checks、3結果集約、Compose・配置・秘密・DB初期化・共通運用規則。

安全入口 `bash -p .github/ci/terraform-checks.sh` とクリーン子環境、backend=false/input=false/lockfile=readonly、資格情報なし・既存mock/plan限定を維持する。AWS認証/OIDC/実applyを追加しない。provider配布物のdownload等は既存経路を使う。

旧設計 `docs/fl-09b5-terraform-ci-design.md` のv3記録は当時の履歴として保持する。今回の新しい設計とPR本文に更新先を記録する。既存ファイルの削除・移動や検査の許可範囲の拡張はしない。

## 4. 検証設計と期待値の根拠

主な故障は、更新漏れでworkflow検査が失敗すること、SHA制約の緩和で別actionを受理すること、新runtimeで実CIが失敗すること。期待SHAとnode24の根拠は公式tag/固定action.ymlとIssue #49であり、検査器の出力から期待値を生成しない。

- **正例**: 更新後の実workflowを既存検査器へ渡し、完全SHAと既存11 checksを含む全契約を通過する。
- **負例**: v3旧SHA `b9cd54a3c349d3f38e8881555d616ced269862dd`、`@v4`、`@v4.0.1`、別の完全SHAをそれぞれ拒否する。既存のwrapper=true、version=latest、資格情報/OIDC、bash -p除去、結果偽装・欠落等の負例も維持する。
- **安全入口**: `node --test .github/ci/test-terraform-checks.cjs`。既存14ケースでstartup汚染防止、6段階の失敗伝播、後始末を確認する。
- **集約**: `bash .github/ci/test-required-status.sh`。4³=64状態でsuccess/success/successだけが0、不正入力も非0という独立oracleを維持する。
- **workflow検査**: frontendの既存lock由来js-yamlを使い、CIと同じ検査imageで `/ci/test-workflow.cjs` を実行する。新しい依存は加えない。
- **実Terraform**: 共通入口をTerraform 1.15.1/provider6.71.0で実行。fmt/init/validate、Python unittest、実Terraform mock/plan、FunctionのNodeテストを確認する。lock差分なしを確認する。
- **全体**: `documents/development/run-checks.md` に従い `python3 -B scripts/run-checks.py` で11 checksを実行。gate回帰 `node --test scripts/test-quality-gate.cjs scripts/test-check-pr-stop.cjs`、quality-checkの必須確認・独立品質レビューも実施する。
- **実CI**: PR head OID/run ID/attemptを紐づけ、全job成功とrunのannotations・terraform jobのセットアップを含む実ログを読む。setup-terraformに対するNode.js20廃止/Node24強制実行警告がないことを確認しPRへ証跡を記載する。最終CIの証跡はPR本文に記録し、その確認後にtracked文書を更新しない。tracked文書や実装を追加変更する場合は、対象snapshotを更新し、必要なchecks/quality-check・通常commit/push・新headの実CI確認までやり直す。静的検査だけで警告解消と判定しない。取得不能・失敗時は未確認として停止理由を記録する。

共有runtime操作は共通Git領域 `/Users/saki/project/FitLog/.git` の `fitlog-runtime.lock` の排他下で順次実施する。11 checksはrun-checks.py自身がlockを管理し、二重取得しない。他担当のDB/image/processを変更しない。登録checks後の追加共有runtime操作も同じ運用で排他を取得する。製品動線に変更がないため、ブラウザE2E追加は予定せず、追加テスト要否はquality-check Step 5に記録する。

## 5. 承認後の短い実装計画

1. 既存Issue/branch/baselineと公式SHA/action.ymlを再確認する。安全契約の負例を追加し、旧workflowの拒否と新SHA候補の受理を検証できるようにする。新SHA候補が旧検査器に拒否されるredを確認する。
2. workflowと検査器の固定値を最小変更で同期更新し、正例/負例をgreenにする。Terraformや共有ファイルに差分がないことを確認する。
3. 排他を取得しCI回帰・実Terraform mock・11 checks・gate回帰を実行する。対象snapshotと終了コードを記録し、quality-checkの機械確認後に独立品質レビューを行う。実装は親が担当する。
4. 新規文書へローカル検証結果を記録してから検証対象snapshotを確定し、quality-checkの証跡を整える。検証済み変更だけをcommit・feature pushし、Issue #49を参照するPRを作成する。実CIの全job・警告解消を確認し、最終head OID/run ID/attemptと証跡をPR本文へ記録する。以降tracked文書を変更する場合は第4節の再検証手順を適用する。
5. PR本文へ実装provider/実際のモデル・完全head OID・「相互レビュー待ち」を記載して停止する。ユーザーが別providerで手動レビューし、対象PRのコメント対応を指示した後に再開する。必要な修正・再検証後も、CI変更のmergeはPR番号・対象headを示したX2のOKまで停止する。

承認対象は本仕様・設計・短い計画と、その範囲内の実装・文書・検証・通常commit/push・PR作成。追加の相互レビュー起動を自動化せず、merge承認もこの設計承認には含めない。

## 6. 独立設計レビュー

2026-11-06、`helm-doc-reviewer`（gpt-6.1-sol/high）による読取りレビュー1体を実施。review-budgetのdesign第1巡（上限1巡）を予約して実施した。

- High 0件。
- Medium 1件: 実CI確認後にtracked設計文書へ結果を追記するとheadが変わるが、その後の証跡更新が曖昧。
- 対応: 親の判断で第4・5節を明確化。最終CI証跡はPR本文へ記録し、以降tracked文書を更新しない。追加変更する場合はsnapshot・checks/quality-check・commit/push・新headの実CI確認をやり直す。追加レビューは実施せず、承認時に所見と対応を提示する。

レビューでは完全SHA/node24/入力互換性、変更範囲・安全契約・検証範囲とIssue #49/既存実装との整合を確認。実装・テスト・build・Compose操作は未実施。

## 実装時の差異

なし。

## 7. 実装・ローカル検証記録

2026-11-06、workflowと検査器を公式v4.0.1の完全SHAへ同期更新。正例に独立した固定SHAの確認を加え、旧v3完全SHA・可変v4・可変v4.0.1・別の完全SHA（v4.0.0）を拒否する4負例を追加した。

- red: 旧workflowが新SHAの正例確認で失敗。workflowだけ更新した状態も旧検査器の完全一致検査で失敗したことを確認。その後、検査器の更新で正例と50負例が成功。
- 正規runner `20261106T081130Z-3af3951754bb410785742aa544bbcbd2`: 11 checksすべて終了0。backend 638件、frontend 190件成功。runnerの `results.json` と `summary.md` を確認。今回起動したDBの停止、migration前後の状態採取と排他返却を確認。
- 追加runtime検証 `20261106T081452Z-1f2e913620bc4b31b2458cb2f74f5e88`: CI検査imageの正例/50負例、Terraform 1.15.1での共通入口が終了0。Terraform mock 42 run、Python unittest 3件、Function 3件成功。排他返却済み。実AWS操作なし。
- ローカル安全入口14ケース、集約64状態+不正入力8ケース、gate回帰54ケースがすべて成功。Terraform定義/lock・Compose・依存lock・checks台帳に変更なし。
- 検証ログはこのworktreeの `.quality-check-runs/` とローカル品質報告で保持する。正規runner開始後の準備中にsnapshotを採取し、実行後に内容hash不変を確認した（実行前採取とは扱わない）。この記録追加後も実行コードのhashは同一。文書の記録更新は独立品質レビュー対象とする。
- 実CIの最終head/run/警告確認結果と独立品質レビューの最終結果はPR本文に記録する。現時点で実CIの警告解消は未確認。
