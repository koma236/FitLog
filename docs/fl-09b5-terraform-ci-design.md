# FL-09B5 Terraform検証のCI組込み（承認済み）

2026-11-06、ユーザーが設計・独立レビュー結果・実装計画を「はい、承認します。進めてください。」と承認。承認範囲内でIssue作成からPR作成まで進め、CI変更の手動相互レビューとX2のマージ前停止を維持する。

## 目的と境界

FL-09B4までのTerraform検証をPR/mainの既存CIへ追加し、Terraformの失敗でも必須status `ci-required` が失敗するようにする。次の作業範囲として親が提案する。実AWSへのplan/apply/destroy、認証情報の探索・投入、image配置、DB初期化、課金を伴う構築は対象外。

worktreeは `/Users/saki/.codex-personal/worktrees/c189/FitLog`、準備branch `prep/parallel-b`、baseline `9d9979561fb10573019481208eb1d254da4e6768`（PR #45統合済み）。writerは親のみ、独立レビューは読取りのみ。共有Compose/DB/imageは設計では操作せず、承認後の11 checks等は既定のruntime排他を使う。他worktreeへ書き込まない。

## 設計上の判断（親の提案）

- 既存 `.github/workflows/ci.yml` に独立した `terraform` jobを追加する。ubuntu-24.04、timeout20分、PR/mainで毎回実行しpaths条件を付けない。backend/frontendと並列、追加サービス/Composeは不要。
- Terraform **1.15.1**、AWS provider **6.71.0**、既存lockを維持する。公式 `hashicorp/setup-terraform` を検証済みの完全commit SHAで固定し、terraform_wrapper=false。checkoutも既存SHA/persist-credentials=falseを維持する。setup actionのexact SHAは実装時に公式repositoryと照合して記録する。更新や新しい依存packageは加えない。
- `.github/ci/terraform-checks.sh` をローカル/CI共通入口にする。rootへcwdを確定し、最小環境（env -i、PATHと専用一時HOME、CHECKPOINT_DISABLE=1、TF_CLI_CONFIG_FILE=/dev/null、TF_IN_AUTOMATION=1、AWS_EC2_METADATA_DISABLED=true、AWS_SHARED_CREDENTIALS_FILE=/dev/null、AWS_CONFIG_FILE=/dev/null）で実行する。TF_VAR/TF_CLI_ARGS/各種AWS・OIDC・container credential・個人設定を継承しない。作成した一時HOMEだけをtrapで片付ける。
- 順に fmt -check -recursive、init -backend=false -input=false -lockfile=readonly、validate、既存Python unittest全件（dependency graphと必須/null入力）、terraform test -no-color、client-ipのnode --testを実行する。Python testsのsubprocessも既存の最小環境を維持する。mock_provider aws / command=planを維持し、real providerのplan/apply/destroyは呼ばない。initの公式provider取得にはネットワークを使う。
- ci-requiredのneedsをbackend/frontend/terraformの3つにし、always()を維持する。required-status.shは結果を3つだけ受け取り、success/failure/cancelled/skipped以外と引数不足/過剰を拒否する。3つともsuccessのときだけ終了0、他の有効組合せは1、不正入力は2。
- 権限はcontents:readのみ、AWS資格設定/OIDC/id-token/secret参照/artifact upload/cacheを追加しない。rulesetの必須status名ci-requiredは変えず、rulesetは操作しない。backend/frontendの既存11 checksの網羅性を維持する。
- workflow検査の既存exact allowlistを新job/setup action/共通scriptの契約に合わせて更新する。許容shell/steps/条件を広く緩めない。検査imageは新scriptの検査に必要な範囲だけCOPYを追加可。

## 検証と受け入れ条件

Highリスク（CI）。実装前にtest-designのoracle/反証項目を記録する。

1. required-statusの固定oracle：4状態の3乗=64通りのうちsuccess×3だけ0。他は1。不正な状態、0/1/2/4引数、空文字、shell文字列は2。
2. workflowの正例と既存負例を維持し、新job削除、needs/resultの欠落・偽装、terraform失敗無視、条件skip、mutable action/version、wrapper有効、credential/write権限の混入を拒否する負例を追加する。
3. 共通scriptはスタブexecutablesによる副作用のないテストで実行順・argv・cwd・継承環境の遮断、各段の非0の伝播・後続未実行・一時HOME削除を検証する。テスト専用分岐を製品scriptへ入れない。
4. 実Terraformで全検証を実行し、既存mock/graph/null入力/Function testを成功させる。scriptテストもCIに組み込む。mock成功は実AWSでの可用性/権限評価の証拠とはしない。
5. 既存workflow検査・ゲート回帰・登録11 checksを既定手順で実施し、対象snapshot・日時・exit codeを記録する。quality-checkの機械検証後に独立品質レビューと追加テスト判定を行う。
6. PRでbackend/frontend/terraform/ci-requiredの実run成功を確認する。ローカル成功をCI実run成功と呼ばない。

## 短い実装計画

1. 設計承認後Issueを作成し、準備branchを `ci/fl-09b5-terraform-<issue>` へ改名。test-designと失敗するpredicate/script/workflowテストを先に作る。
2. 共通script、terraform job、3結果の集約、厳密なworkflow検査を実装。実検証と文書（Terraform README、本番準備、task-plan）を更新する。
3. 機械checksとquality-check、必要なHigh修正、commit/通常feature push/PR作成、CI実runを確認する。
4. CI変更なので手動相互レビュー待ちで停止する。レビューへの対応指示後に再検証し、X2により対象PR番号とheadを示したユーザーのマージOKを受けてから統合する。

主変更対象は `.github/workflows/ci.yml`、`.github/ci/`、上記文書。Terraform資源定義/backend/frontend/依存lock/ハーネス/11 checks台帳は変更しない。

設計レビューはhelm-doc-reviewer 1体（Sol/high）、実装は親、品質レビューは規定の体制（初回は統合/反証QA/必要な専門家最大1体、Astra/high）。追加巡はHighの確認が必要な場合だけ予算内で行う。

原典：[setup-terraformの公式仕様](https://github.com/hashicorp/setup-terraform)、[Terraform testの公式仕様](https://developer.hashicorp.com/terraform/cli/commands/test)。testは既定で実資源を扱い得るため、既存mock/plan指定と資格情報を渡さない境界を維持する。

## 独立設計レビュー

2026-11-06、helm-doc-reviewer（gpt-6.1-sol/high）による読取りレビュー1体を実施。High 0件、Medium 0件。3結果集約と固定64状態oracle、厳密なworkflow検査と既存11 checks、mock/plan限定と環境遮断、CI変更の手動相互レビュー/X2停止が既存契約と整合していると確認。公式setup-terraform/test仕様も照合した。追加修正事項なし。

予約markerは `HELM_REVIEW:526e0cd9046b324b45774ae1ebd84497:document-reviewer`。準備branchのdesign 1/1枠を使用。台帳のused/receipt/agent受付を確認した。個人CODEX_HOMEを指定した公式CLIのcodex-trustはok。実装・Terraform/Dockerの実行はまだ行っていない。

## 実装記録

Issue #46、branch `ci/fl-09b5-terraform-46`。一時的なDNS障害が回復した後、gh account=koma236/repo=koma236/FitLogを再照合してIssueを作成した。設計承認は上記のとおり有効。

setup-terraformの公式v3参照をGitHub APIで照合し、commit `b9cd54a3c349d3f38e8881555d616ced269862dd` に固定した。テスト設計メモは非コミットの `docs/superpowers/plans/2026-11-06-fl-09b5-terraform-ci-test-design.md`。

## 実装時の差異

製品・CIの振る舞いに設計との差異なし。工程順序のみ、ローカル11 checksの準備がDocker credential helperの応答待ちで進まないため、品質レビュー前にdraft PRを作成して実装を保存する。quality-check通過・通常PR準備完了とは扱わず、後続のローカル全checks→独立品質レビュー→必要な修正→CI確認→手動相互レビュー→X2を維持する。

## 検証状態（実装保存時）

- status集約64状態＋不正入力8件、script契約7件、workflow正例＋負例45件、ゲート回帰54件が成功。
- 共通入口を実Terraform 1.15.1/provider6.71.0で実行し終了0。fmt/init/validate、Python tests3件、Terraform mock42 run、Function tests3件が成功。実AWS操作なし。
- 正規11 checks runnerのrun-idは `20261106T032638Z-f7437dd9733f43e1bbbdd5f53d2fd7f1`。HEAD `9d9979561fb10573019481208eb1d254da4e6768` とstage済み11ファイルのhashを実行前後で照合し一致。最初のmigration状態採取用buildが `docker-credential-desktop get` の待機で停止したため、親が所有照合後runnerへSIGTERMを送った。終了1、登録11件はすべてnot_run（exit null）。既存imageでの最終migration状態は採取できたが、開始前状態の採取は未完了。
- runner自身のfinallyで今回起動したDBを停止し、残存container/process確認後に自分のlockを返却した（lock_released=true）。共有設定・認証設定を変更せず、credential helperの回避はしていない。
- GUI確認用の `orca skills get computer-use --json` はcommand not found（127）。可視ダイアログの有無は未確認。
- 依存lockの変更なし。既存lockのローカル復元時にnpmが脆弱性10件（moderate8/critical2）を表示。追加の `npm audit --omit=dev --json` は依存metadataの外部送信を理由に自動承認レビューで拒否されたため未実行。対象package/runtime到達性は未確認、監査成功とは扱わない。`audit:prod` は未配線。
- quality-checkの独立レビュー/Step5完了/品質flagは未実施。Docker認証待機が解消した後、正規11 checksから再開する。設計の再承認は不要。
