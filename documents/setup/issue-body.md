## 目的

FitLogを個人アカウント koma236 の新規アプリ開発用リポジトリとして準備し、
Claude Code・Codex共通の個人開発ハーネスを導入する。

## 対象

- リポジトリ: koma236/FitLog
- 作業ブランチ: chore/setup-ai-dev-harness
- 共通ハーネス: ~/project/ai-dev-harness
- 共通資産の基準版: @crearize/ai-dev-helm 3.4.3

## 作業内容

- AGENTS.md、CLAUDE.md、共通ルール、skills、quality-gate / review-budget hooksを配置する。
- ai-dev-chatをClaude・Codex双方から参照できるようにする。
- v9の4段階承認とIssue・commit・push・PRごとの個別承認を明文化する。
- mergeは人間がGitHub上で行い、AIは実行しない。
- Codexに ~/.codex-personal を使用し、会社環境にはアクセスしない。
- CLI、skill探索先・読込み、hooks登録・信頼状態を確認して記録する。

## 受け入れ条件

- [ ] 対象リポジトリ、origin、GitHub認証先が個人用 koma236 である。
- [ ] 両AIの入口から個人用v9運用ルールを参照できる。
- [ ] 両AIで共通ai-dev-chat skillの読込みを確認している。
- [ ] hooksの構文・登録・信頼状態と実行確認の結果が記録されている。
- [ ] 技術スタック・checks未設定を明示し、execution_ready=false としている。
- [ ] 未設定・未実行のchecksやレビューを成功扱いしていない。
- [ ] 必要なGit操作は内容提示と個別承認を経て実行する。

## 今回の対象外

アプリ機能の実装、技術スタック決定、推測によるテストコマンド登録、AIによるmerge。

この文書はIssue本文案であり、Issue作成済み・承認済みを意味しない。
