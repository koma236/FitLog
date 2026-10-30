# FitLog 個人開発運用

この文書はFitLogのユーザー指定を記録する。配布元の一般ルールと衝突する場合、
本書の個別承認・個人環境・Git操作の制限を優先する。品質基準やhooksを弱めない。

## 対象と環境

- 対象は個人リポジトリ `koma236/FitLog`。
- 共通ハーネスは `~/project/ai-dev-harness`。実行入口は `bin/ai-dev`。
- iTerm2で個人プロジェクトへ移動し `codex-me` で起動する（`CODEX_HOME="$HOME/.codex-personal"`）。認証情報をコピーしない。
- v9のGit操作は `~/.ai-dev-harness/personal-git.toml` から個人gh/Git設定を自動選択する。設定が不正なら停止し、既定設定へ戻らない。通常のgit/gh全体の設定は変更しない。
- 会社用 `~/.codex`、会社リポジトリ、`manabi-backoffice` を含むパスは探索・読取り・変更しない。
- project内の `.codex/` はこのリポジトリの設定であり、会社用 `~/.codex` とは異なる。
- GitHub操作前に実リポジトリ、originの設定値と実効URL、認証アカウントが `koma236` であることを確認する。不一致・未確認なら実行しない。
- アカウントを探すために会社の設定を探索しない。既定のGitHub認証やグローバルGit設定を無断で変更しない。

## 承認

- v9通常モードは、仕様、計画、実装結果、独立レビュー結果の4段階で個別に人間承認を得る。
- 実装と独立レビューのproviderは分ける。仕様・plan・taskが揃うまではv9実行準備完了としない。
- チャット上の承認をv9のreceiptとして生成・編集・代用しない。
- 原則として `ai-dev v9 approve` の内容を本人が通常ターミナルで確認し、要求された文字列を入力する。例外は、会話で具体的内容を個別承認したうえで通常TTY入力の代行を明示委任した範囲だけ。その場合は既存の `codex-owner-delegated` 手順で正規の対話入力を行える。未承認の内容への代行、パイプによる一括承認、receiptの生成・編集は認めない。
- provider実行も、返されたhandoffを通常ターミナルで実行し `EXECUTE <attempt-id>` を入力する。本人確認を原則とし、前項の明示委任がある対象に限って正規TTY入力を代行できる。
- `auto` / 完全自動はユーザーが明示した場合のみ。結果の `auto_delegated` は人間承認済みでもGit操作可能でもない。
- 承認済み範囲の編集・ローカル確認・指摘修正は進める。Git操作への包括承認には解釈しない。

## Git・GitHub

- 原則は1 Issue = 1作業ブランチ = 1 PR。Issue番号を捏造しない。
- Issue作成、commit、PR作成は毎回、対象と具体的内容を示して個別承認を得る。
- featureブランチのpushは、2026-10-30のユーザー指示「これ以降pushには個別承認不要です」により個別確認を省く。対象repo・個人アカウント・送信先・commitの検証と正規v9操作は維持する。main/masterへの直接push、force、mergeの許可にはしない。
- v9では `prepare-git` のproposalを使い、正規の `git-action` を実行する。feature pushは上記の委任範囲で進め、それ以外は個別承認を得る。承認節の例外条件（具体的内容の個別承認と通常TTY入力の明示委任）を満たす範囲に限り、同節の正規対話手順で要求文字列を入力できる。receiptを直接生成・編集しない。
- Issueには仕様・計画の承認receipt、commit以降には4段階の承認receiptなど、v9が要求する前提を満たす。満たせない場合は未完了として報告し、別経路で迂回しない。
- **mergeは人間がGitHub上で行う。AIによるmerge・auto-merge有効化は禁止。**
- main/masterへの直接変更・push、force push、履歴の書き換え、hook無効化や回避は禁止。
- 上流にある自動Issue作成、設計承認によるGit操作の包括許可、自由なfeature push、AIによるmergeの記述はFitLogには適用しない。
- URL rewriteなどでv9の検証が停止した場合、停止理由を解消する。ハーネスの検査を無効化しない。

## 技術スタックと検証

- 今回はハーネス導入のみ。アプリの技術スタック、開発ポート、build/lint/testコマンドは未設定。
- `.ai-dev/project.toml` のchecksは、技術スタック相談後に実在するコマンドを確認してargv配列で登録する。
- 未設定・未実行・失敗を成功扱いしない。checksが空なら `execution_ready=false` のままにする。
- CLI help、status、dry-run、ファイル構文やリンク確認は導入診断であり、アプリのchecks成功、provider認証、独立レビュー、workflow完了の証明ではない。
- hooksの配置、登録、信頼、実行確認を区別する。信頼をAIが捏造せず、Codexの `/hooks` で本人が確認する。
- 配布元のquality-gate / review-budgetを保持する。導入だけを根拠に `.quality-check-passed` を作成しない。

## 共通skill

`skills/ai-dev-chat/SKILL.md` を必要時に読む。
`.claude/skills`、`.codex/skills`、`.agents/skills` は同じ `skills/` を参照する。
新しいセッションでのskill一覧掲載・実読込みを確認する。現セッションに自動反映したとは扱わない。

正本は `~/project/ai-dev-harness/documents/v9/workflow-policy.md` の現行節と
`~/project/ai-dev-harness/skills/ai-dev-chat/SKILL.md`。過去ポリシーは現行承認の根拠にしない。
