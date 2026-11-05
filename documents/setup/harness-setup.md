# FitLog ハーネスの利用

現行方針は[個人開発運用](../development/personal-workflow.md)。既存の通常skillで、自然言語の承認から開発を進める。

- 配布資産は.ai-dev-helm.jsonに記録された導入版を使う。更新は`documents/development/harness-upgrade.md`の手順で行う。
- AGENTS.md / CLAUDE.mdから個人運用を最優先で参照する。
- .claude/skills / .codex/skills / .agents/skillsは共通skills/を参照する。新worktreeで不足するリンクは導入版のlink-skillsで整備する。
- 個人CodexはCODEX_HOME=$HOME/.codex-personalを選ぶ既存codex-meから起動する。GitHub操作は`gh`（操作前にaccountとrepoを確認する）、通常Gitの送信は認証確認済みの個人SSH経路を使う。
- Codex /hooksのquality-gate、review-budget（Pre/Post）、context-handoffの信頼を確認する。信頼記録を直接編集したり、信頼を迂回するflagを使ったりしない。
- Claudeも/hooksの登録を確認する。実clientでの起動確認と、模擬stdin試験は区別する。未確認は未確認のまま報告する。
- 仕様・独立設計レビュー・計画の一括承認後、範囲内の実装からPR作成・mergeまで進める。例外は[個人開発運用](../development/personal-workflow.md)の「承認と自律実行」による。
- build/lint/型/テスト/migrationはproject.tomlの実コマンドを[checksスクリプト](../development/run-checks.md)で共有排他枠の中で実行する。親が対象snapshotとrun-id・終了コードをquality-check報告へ対応づける。

既存のlocal専用chat skillリンクはこのPRのGit差分では削除できない。統合と採用確認後、Rootのリンクだけを解除する。通常skillsのリンク、共有source、共通excludeは維持する。旧sessionを終了して新規sessionで現行規則を読む。
