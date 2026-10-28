# FitLog

個人アカウント `koma236` のアプリ開発用リポジトリです。
現在は共通ハーネスの導入段階です。アプリの要件・技術スタック・検証コマンドは今後決めます。

- [個人開発運用](documents/development/personal-workflow.md)
- [セットアップ状況と確認手順](documents/setup/harness-setup.md)
- [セットアップIssue本文案](documents/setup/issue-body.md)

共通ハーネスは `~/project/ai-dev-harness`、配布資産は `@crearize/ai-dev-helm@3.4.3` を利用します。
iTerm2でこのリポジトリへ移動し、`codex-me` で起動します。
個人Codex環境 `~/.codex-personal` と、v9の個人Git/GitHub設定が自動で選ばれます。
初回はCodexの `/hooks` で登録済みの3件を信頼してください。

Issue・commit・push・PRは内容ごとに個別承認し、mergeは本人がGitHub上で行います。
checksは未設定です。導入診断の成功をアプリのテスト成功とは扱いません。
