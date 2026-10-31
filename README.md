# FitLog

個人アカウント `koma236` のアプリ開発用リポジトリです。
React/TypeScript・Django・PostgreSQLで開発しています。仕様・API契約は `docs/`、検証コマンドは `.ai-dev/project.toml` にあります。

- [個人開発運用](documents/development/personal-workflow.md)
- [セットアップ状況と確認手順](documents/setup/harness-setup.md)
- [セットアップIssue本文案](documents/setup/issue-body.md)

共通ハーネスの整備用checkoutは `~/project/ai-dev-harness`、配布資産は `@crearize/ai-dev-helm@3.4.3` を利用します。v9の実行版は[個人運用](documents/development/personal-workflow.md)の採用済みruntimeを使い、整備用checkoutと混在させません。
iTerm2でこのリポジトリへ移動し、`codex-me` で起動します。
個人Codex環境 `~/.codex-personal` と、v9の個人Git/GitHub設定が自動で選ばれます。
初回はCodexの `/hooks` で登録済みの3件を信頼してください。

仕様・独立設計レビュー・計画を最初にまとめて承認し、範囲内の作業はfeature pushまで委任します。
重大な変更とPR作成は別途確認し、mergeは本人がGitHub上で行います。
並列作業は[並列開発運用](documents/development/personal-parallel-workflow.md)に従います。
導入診断の成功をアプリのテスト成功とは扱いません。
