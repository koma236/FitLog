# WF-INTEGRATION: 未統合の個人用ワークフローと環境復旧を現行mainへ統合

## 目的と現状
対象koma236/FitLog。ユーザー要求は「残っているIssueを全て閉じられるよう進める」。Issue20はPR21/19の本人統合と新組合せCI3件成功を再確認してcompletedで閉じた。残るIssue17/18の実装は各々commit2a2fd3c/f827b9fとして公開・検証済みだが、mainには未統合である。
基点main a42a25f03dc61b832ed0ffc0e69903629e50f3afにはCI・FL07・FL08が統合済み。元FL07 commit0d23433を保持しており、旧タスクの差分スコープは追跡できる。両旧branchはmainとAGENTS.md、CLAUDE.md、README.md、documents/development/personal-workflow.mdの4文書で競合する。読取り専用のテキスト競合分析で確認した。
現行runtime169642dの通常standard workflowは固定baselineからの承認済み1-parent commitとIssue承認連鎖に束縛される。旧branchを更新して旧receiptへ成功を付け替える方法は取らない。旧commit・branch・元private記録・レビュー消費枠を保存し、別の統合作業を記録する。未解消の過去指摘を新taskへ移して予算を戻す目的ではなく、既存合格済みコードと現行mainの新しい統合差分を対象とする。

## 採用案・範囲
完了済みCI修正のcleanなworktree /Users/saki/.codex-personal/worktrees/e2a7/FitLogを再利用し、branch chore/workflow-integration、task WF-INTEGRATION、baseline a42a25fで進める。S=/Users/saki/.codex-personal/worktrees/5313/FitLogはf827b9fのまま保存し、正規feature送信の採用済みnative入口としてだけ使う。親Codexが唯一の書込み担当。新機能やruntime改修は行わない。
旧Sの0d23433..f827b9fに現れる23ファイルを取り込む。競合しない19ファイルはf827b9fのraw blob/modeをそのまま再利用し、公開済みハーネスcode/config/fixturesを変更しない。競合4文書だけは現行mainの内容を土台に、承認済みの並列開発・最初の計画承認後の委任・登録runtime・環境復旧の規則を統合する。旧設計/manifest/planは旧基点の履歴としてbyte不変で保持し、この新taskのmanifest/planを実行対象にする。
4文書ではCIのbuild/lint/型/全テスト/migrationとci-required、同一SHAの無根拠rerun禁止、別project/image/volumeでのCI再現、現在の技術スタック/ポート、FL08の運用・安全な構造化ログ案内を保持する。個人運用節を最優先として初回計画承認後の正規TTY委任・Issue/commit/feature送信を一意にし、PR最終確認と本人によるGitHub mergeを維持する。配布元の一般説明にある矛盾する承認/merge記述を個人運用で適用除外する。READMEは現在のアプリ説明を保持して運用入口を足す。CIや運用規則を旧状態へ戻さない。
追加するのは本設計docs/workflow-integration-design.md、.ai-dev/workflow-integration.spec.json、.ai-dev/workflow-integration.plan.jsonの3ファイル。予定計26パス。製品backend/frontend、.github、Compose、依存/lock、登録11checks、hook登録/信頼、共有Git設定、既存DB・画像volumeに差分を出さない。新エラーコードは追加しない。品質ゲート、deny条件、review-budgetを弱めない。

## 代替案との比較
旧2branchへmainを直接取り込む案は、原本の固定HEAD/baselineとstandard Issue連鎖を壊す。旧branchのまま2PRを出す案は同じ4文書競合を本人に解かせることになり、解決後のsnapshotも旧v9結果で保証できない。未統合のまま完了扱いで閉じる案では現行mainへ運用改善が届かない。新main基点の統合taskを1つ設け、独自の実結果と承認で1PRにする案を採る。

## 独立した受入条件
WFI-AC1: 競合しない19ファイルが固定f827b9f blob/modeと一致し、旧2commit・branch・private approval/job/result・消費枠が維持される。新bindingに旧receiptを流用しない。
WFI-AC2: 4文書が上記の現行CI/運用規則と既存の並列/委任/復旧要件を両立し、矛盾・競合marker・古い技術スタック表示を残さない。CI/製品/依存/checks/登録/共有configはbaselineからbyte不変。
WFI-AC3: Node構文、既存27件の通常v9 gate回帰、11件の環境復旧gate回帰、99件のPython復旧テストを実測し、旧fixtureの固定SHAも比較する。件数は期待値であり実行前の成功ではない。テスト・fixtureの削除や期待値の緩和をしない。機械検査後に統合/反証QA/Securityの独立品質1巡と異なるprovider Claudeの正式v9レビュー1回でHigh/Mediumが残らないことを確認する。
WFI-AC4: 登録11checksを変更せず、同じcloneの共有runtime排他とmigration graph照合の下で実行する。適用予定が空・既知nodeだけの場合に限り既存DBのmigrateを実行し、履歴を前後比較する。不足・未知node・適用操作があれば停止し、reset/逆migrationを行わない。今回起動したサービスだけ停止し、自分のlockだけ返却する。
WFI-AC5: public v9の独自4工程確認、独自Issue、commit、当該featureへの非force送信を正規実TTYで実行する。R=登録runtime169642dを保持し、native Sからliteral A/Bを使う。送信resultと独立remote SHA照合、untracked-checkを確認する。新しい統合Issueを1件作り、1Issue/branch/PRのv9連鎖を守る。Issue案は「個人用ワークフロー・環境復旧の現行mainへの統合」。旧Issue17/18はこの統合PRへの参照として追跡する。
WFI-AC6: PR作成は具体的本文完成後の最終承認とする。本文にCloses #17、Closes #18と実際の新Issue番号を記載し、全チェック/残る制約を報告する。本人がPRをGitHubで統合した後に3Issueのclosedを確認する。AI merge/auto-merge/trunk直接操作/force/履歴書換え/hook迂回は禁止。統合前に旧Issueを未実装扱いで閉じない。

## 実行計画・予算・承認
Phase0: 本具体案と新Issue案を本人へ提示する。旧設計の目的は継続するが、基点・公開方法・新たな統合Issueが必要なので、この変更範囲への条件付き承認と正規TTY代行の明示委任を求める。公開v9独立設計レビューは1回だけ準備し、本人回答まで実行しない。合格(approved=true、High/Medium0)した場合に限って次へ進む。本人が条件付き事前承認を選ばない場合はレビュー結果を提示してDesign Gate回答を待つ。
Phase1: 合格後にactor codex-owner-delegatedで仕様/計画の正規実TTY確認、新Issueの作成、19blobの移植と4文書の競合解消、Highリスクのテスト設計メモを実装前に作成する。旧taskのsourceやprivate状態は変更しない。
Phase2: Node/Python回帰と登録11checksを実行する。全機械検査が通ってからローカル品質1巡(統合・反証QA・Security)、正式v9 review1回(Claude)を行い、実結果に一致する実装/レビュー確認を正規TTYで行う。実装は親Codex、独立レビューは上記の別担当/provider。設計1回・ローカル品質1巡・正式v9品質1回を今回の上限とし、自動追加・旧予算の初期化・未解消指摘の受入れはしない。上限/停滞/重大範囲変更ではまとめて停止報告する。
Phase3: 自分の26パスだけを正規v9でcommit、untracked-check、品質flag、native Sから正規feature送信とremote SHA照合まで進める。PRを準備して最終承認を1回求める。本人統合後のIssue closed確認まで追跡する。新たな製品E2Eは導線変更がなく対象外。gateの局所反証/既存回帰を使い、mutation基盤を追加しない。必要な判断はまとめ、軽微な範囲内の修正では再申請しない。

## 予定パス

- `.ai-dev/v9-env-recovery.json`
- `.ai-dev/v9-git-entrypoints.json`
- `.ai-dev/wf-git-recovery.plan.json`
- `.ai-dev/wf-git-recovery.spec.json`
- `.ai-dev/wf-parallel.plan.json`
- `.ai-dev/wf-parallel.spec.json`
- `.claude/hooks/quality-gate.cjs`
- `.codex/hooks/quality-gate.cjs`
- `AGENTS.md`
- `CLAUDE.md`
- `README.md`
- `bin/ai-dev-git-env-recovery`
- `docs/git-environment-recovery-design.md`
- `docs/personal-workflow-change-design.md`
- `documents/development/personal-parallel-workflow.md`
- `documents/development/personal-workflow.md`
- `scripts/fixtures/v9-push-proposal.json`
- `scripts/fixtures/v9-push-provenance.json`
- `scripts/test-quality-gate-env-recovery.cjs`
- `scripts/test-quality-gate-v9.cjs`
- `scripts/test_v9_git_environment_recovery.py`
- `scripts/v9_git_environment_recovery.py`
- `skills/project/quality-check/SKILL.md`
- `docs/workflow-integration-design.md`
- `.ai-dev/workflow-integration.spec.json`
- `.ai-dev/workflow-integration.plan.json`

## 設計レビュー1への明示的な前提確認

Medium2件への追記であり、取込み26パス・実装内容・禁止事項・レビュー上限を拡大しない。実装開始前に次を必須の停止条件付き事前確認とする。

1. 再利用する19ファイルのそれぞれについて、0d23433とa42a25fの`git ls-tree`結果（存在有無、blob ID、Git mode）が完全一致することを確認する。1件でも異なればraw blobの移植を開始せず、パス集合と設計の見直しを本人に提示する。「テキスト競合がない」だけを根拠にしない。実装後のf827b9f raw blob/mode一致と合わせ、main変更の巻戻しを防ぐ。これはWFI-AC1/2およびPhase1の必須事前条件である。
2. 元系列が0d23433→2a2fd3c→f827b9fの直系親子であることを`rev-list --parents`で確認する。0d23433..2a2fd3cの15パスが0d23433..f827b9fの23パスの部分集合であることも確認する。成立しなければ開始せず範囲を見直す。これはWFI-AC1/6およびPhase1の必須事前条件である。

レビュー後の読取り実測では19件すべてのblob/mode/存在有無が一致し、直系親子と15パスの部分集合も成立した。結果はignored docs/superpowers/plans/2026-11-01-workflow-integration-design-evidence.jsonに記録した。実装直前にも同じ固定SHAで照合し、実結果の要約を新Issue/PRに残す。過去の不合格verdictや消費枠は保持する。

Low3件の扱い: (a) 4文書の優先規則でskills/project/quality-check/SKILL.mdに残る配布元の「CIはビルド確認のみ」も明示的に適用除外し、現在のCI全機械検査方針を正本とする。旧19ファイルは編集しない。(b) 既存DBでのmigrate確認は登録11checksを変更せず実行するためであり、本差分のschema変更を目的としない。適用予定が空の場合だけ実行し前後履歴を照合する条件を維持する。(c) schemaは固定runtime169642dの定義どおりmanifest9/plan10/project1を使用する。first-project-workflowと既存FL07のspec9/plan10を照合し、新taskのinit-workflow/prepare-runが正規validatorを通過した。schemaやruntimeは変更しない。
