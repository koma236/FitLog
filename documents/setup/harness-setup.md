# FitLog ハーネス導入状況

確認日: 2026-10-27（Asia/Tokyo）。今回の範囲は個人開発ハーネスの導入のみ。

## 配置

- ブランチ: `chore/setup-ai-dev-harness`。
- 配布資産: `@crearize/ai-dev-helm@3.4.3`。toolsはclaude-code / codex、stacksは空、skillsはall。
- `AGENTS.md` / `CLAUDE.md`、共通skills、開発ルール、レビューガイド、lint資産、両AIのhooksを配置。
- `lint/` は配布資産のみ。アプリ用lintコマンド・依存関係・実行環境は未設定。
- [個人運用ルール](../development/personal-workflow.md)を両AIの入口から最優先で参照。
- `skills/ai-dev-chat` は `../../ai-dev-harness/skills/ai-dev-chat` へのsymlink。
- `.claude/skills` / `.codex/skills` / `.agents/skills` は `../skills` へのsymlink。
- このリンクはFitLogとai-dev-harnessが同じ親ディレクトリにある配置を前提とする。
  clone先を変える場合はリンク先を確認し、既存ファイルを上書きしない。
- インストーラー生成のbackupはローカルに保持し、Git対象外とする。

## 診断結果

| 項目 | 結果 |
| --- | --- |
| CLI | ai-dev v9 help、Codex 0.162.1、Claude 2.1.299、Python 3.12.3、Node 24.10.0、npm 11.8.0、gh 2.89.0の表示を確認。既存codex-meと同じ関数を隔離shellで再現しversion表示を確認（iTerm2の対話起動自体は未実施） |
| CODEX_HOME | `/Users/saki/.codex-personal` |
| project config | status / dry-runで読込み成功 |
| 設定ファイル | TOML / JSONを解析して構文確認済み。stacksは空 |
| skillのリンク | 共通入口と両AI・`.agents` の4経路が同じSKILL.mdへ解決し、読取り可能 |
| hooksの配布元との一致 | quality-gate / review-budgetの計4ファイルが3.4.3配布物と一致。Node構文確認済み |
| quality-gateの単体呼出し | 両AIの登録コマンドに読取り専用コマンドのイベントを渡し、終了コード0。AIセッションによる自動発火の確認ではない |
| checks | 空。`V9_CONFIG_NO_CHECKS`、`execution_ready=false` |
| アプリbuild/lint/test | 未設定・未実行 |
| Codex project trust | 個人用環境で `trusted` |
| Codex hook trust | 3件未信頼。診断終了コード1 |
| skillの掲載・実読込み | 現在のCodexセッションのskillカタログにai-dev-chatと共通skillsが掲載済み。Claude新規セッションの確認は未完了 |
| Claudeでのhook実行 | 新規セッションでは未確認 |
| GitHub認証 | 個人用入口からAPIで `koma236` を確認。`state=success`、`tokenSource=keyring` |
| 対象GitHubリポジトリ | `koma236/FitLog`、`viewerPermission=ADMIN` を確認 |
| 個人用GitHub CLI | `~/.local/bin/gh-koma236` と `~/.config/gh-koma236` を承認後に作成。権限0700、token環境変数の除外を確認 |
| v9のGitHub設定引継ぎ | 個人profile自動読込みを実装。v9のrunnerでkoma236 / koma236/FitLog / ADMIN / HTTPS main参照取得を確認 |
| 共通ハーネス回帰テスト | 189件成功（80.636秒）。設定パスの追加5テストは修正前の失敗と修正後の成功を確認 |
| v9 manifest / plan / workflow / 承認receipt | 未作成。アプリ仕様を捏造しない |
| 独立レビュー・quality-check合格 | 共通ハーネス実装の独立レビューで4件を修正。2巡目の検証・QAでHigh/Medium残存なし。commit未実施のため合格フラグなし |
| Issue / commit / push / PR | 未実施。Issueは本文案のみ |

`git diff --check` は追跡済み変更について終了コード0。新規配布ファイル全体の品質合格を意味しない。

## 読取り診断

```sh
"$HOME/project/ai-dev-harness/bin/ai-dev" v9 status --project "$PWD"
"$HOME/project/ai-dev-harness/bin/ai-dev" v9 dry-run --project "$PWD"
npx -y @crearize/ai-dev-helm@3.4.3 codex-trust \
  --dir . --codex-home "$HOME/.codex-personal"
```

status / dry-runの `status=ok` は設定読込みの成功のみ。
checks成功、provider認証、実行可能なworkflowを証明しない。

## 本人による信頼・読込み確認

通常ターミナルでFitLogへ移動し、個人用環境で起動する。

```sh
cd "$HOME/project/FitLog"
codex-me
```

Codexの `/hooks` で以下を確認して信頼し、上のcodex-trust診断を再実行する。
信頼記録をAIが直接編集したり、hook-trustを迂回する起動オプションを使ったりしない。

- PreToolUse: quality-gate.cjs（Bash）
- PreToolUse: review-budget.cjs（agent操作）
- PostToolUse: review-budget.cjs（agent操作）

CodexとClaudeの新規セッションで `ai-dev-chat` の掲載と
`skills/ai-dev-chat/SKILL.md` の読込みを確認する。
確認用の依頼は「ai-dev-chatを読み、個人環境・承認・mergeの制約だけ説明してください。実行はしないでください。」とする。
Claudeでは `/hooks` でも登録を確認する。実行確認前にhooksが動作済みとは報告しない。

Codexの探索先と信頼の仕様は[公式skill文書](https://learn.chatgpt.com/docs/build-skills)と
[公式hooks文書](https://learn.chatgpt.com/docs/hooks)を参照。

## 普段の起動

```sh
cd "$HOME/project/FitLog"
codex-me
```

既存の `codex-me` が個人Codex環境を選び、v9のGit操作は
`~/.ai-dev-harness/personal-git.toml` を自動読込みする。追加のexportは不要。
profileは `~/.config/gh-koma236` と `~/.config/git-koma236/config` を指定する。
初回のhooks信頼と、操作ごとのv9人間承認は必要。
通常の `git` / `gh` 全体に個人設定を適用するものではない。

## 残る作業

1. Codex `/hooks` の3件を本人が信頼する。Claudeの新規セッションでもskill・hooksを確認する。
2. 技術スタック相談後、実在するchecksと仕様・計画を整備する。
3. [Issue本文案](issue-body.md)の個別承認。v9が要求する前提を満たしてから作成する。
4. commit・push・PRをそれぞれ内容提示・個別承認の上で進める。mergeは人間が行う。

承認済みのローカル導入はv9承認receiptではない。
checksや仕様が未設定のためv9の前提を満たさない操作は、未完了のまま報告する。

共通ハーネス変更の対象追加はユーザー承認済み。
具体設計は [v9個人用Git/GitHub環境](v9-personal-git-design.md) を参照。

詳しい検証結果: [個人Git環境の検証記録](v9-personal-git-validation.md)。
