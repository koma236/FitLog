# コマンド常時許可・Git領域書込みの設定案

最終更新: 2026-11-05。Issue #38。**提案のみ。active設定・外部設定は変更していない。**

## 判断と適用先

自然言語の工程承認とOS/sandboxの許可は別。読み取りはsandbox内で実行し、外へ出る許可を広く追加しない。checksだけは共有DB/migration/imageとlockへの限定書込みを含む例外候補とする。script・registry・Compose・Dockerfileは実行コードなので、変更内容を確認したsnapshotでだけ使う。scriptの変更に自動追従する許可を不変な安全境界とは扱わない。

Codexは `CODEX_HOME=/Users/saki/.codex-personal` を使う。配置候補は個人 `rules/fitlog.rules` または信頼済みrepoの `.codex/rules/`。本PRの例はこのMarkdown内だけで、読み込まれる場所へ置かない。公式の[Rules](https://learn.chatgpt.com/docs/agent-configuration/rules)はprefix照合と、最も厳しい判定の優先を定める。

## Codexのコマンド案

安全な固定引数として表せるかを優先する。`git status/diff/log`、`gh api user --jq .login`、`review-budget status`、既知CLIのhelp、codex-trust、hook-selftestは読取り候補だが、prefixだけでは後続引数を禁止できない。例えば `gh api user --jq .login -X PATCH` や `git diff --output=/tmp/file` まで拡張可能なprefixはallowしない。statusからbegin/extendへ切り替わらなくても別script/pathを許す一般的なnode/python/npxのprefixを作らない。

唯一のallow例は、レビューしたscriptの**絶対path**までを含むもの。下記pathは対象worktreeごとに置き換える。相対pathだと別cwdの同名scriptを実行できるため採用しない。

```python
prefix_rule(
    pattern = ["python3", "-B", "/Users/saki/project/FitLog/.worktrees/chore-operations-38/scripts/run-checks.py"],
    decision = "allow",
)
```

追加引数はscript自身が拒否する。許可するとsandbox外でDocker/build/登録checksが実行され得るため、任意Python・git/gh・npx全般の許可とは分けて、採用時に対象pathとコードを確認する。push・gh書込み・review-budget begin/extendは都度のOS許可を維持する。

Codex 0.166.0の `codex execpolicy check --help` で構文を確認し、例を一時ファイルへ保存して `--rules <例のpath> -- <argv>` で照合できる。checksの正しいpathはallow、別pathは非一致、同pathへの追加引数はprefixには一致するがCLIが拒否、と分けて検証する。ルール照合は実行許可の本番採用やhook動作の証明ではない。

## Claude Codeの案

`.claude/settings.local.json` が個人向け候補、共有する場合は `.claude/settings.json`。既存hooks・deny/ask・managed設定を残してallow配列だけ統合する。以下はコピー元の例であり、本PRでは配置しない。公式[Permissions](https://code.claude.com/docs/en/permissions)に基づきワイルドカードなしの完全一致で列挙する。

```json
{
  "permissions": {
    "allow": [
      "Bash(git status --short)",
      "Bash(git diff --stat)",
      "Bash(git diff --check)",
      "Bash(git log -5 --oneline)",
      "Bash(gh api user --jq .login)",
      "Bash(node .codex/hooks/review-budget.cjs status)",
      "Bash(codex --help)",
      "Bash(claude --help)",
      "Bash(npx -y @crearize/ai-dev-helm@3.7.1 codex-trust --dir . --codex-home /Users/saki/.codex-personal)",
      "Bash(python3 -B /Users/saki/project/FitLog/.worktrees/chore-operations-38/scripts/run-checks.py)"
    ]
  }
}
```

hook-selftestは安全なdry-runのCLI/argvを導入版で確認できた場合だけ完全一致で追加する。未知のサブコマンドを推測して許可しない。Claude Codeは実clientで未採用・未検証。採用する際は余分な引数、別cwd、複合command、書込み先追加が自動許可されないことを確認し、network/OS sandboxは別に扱う。

## `.git`限定書込みの案

公式[Permissions](https://learn.chatgpt.com/docs/permissions)では `:workspace` の保護を継承し、必要な深いpathだけを明示するprofileを定義できる。従来の `sandbox_workspace_write.writable_roots` にclone全体を足す方法とは別であり、`.git`全体を書込み可能にしない。実環境のCodex 0.166.0ではCLIのprofile指定が存在することまで確認した。管理側がprofilesを許可していない場合や上位設定のdenyがある場合は採用できないため、設定例だけで動作保証しない（[Config Reference](https://learn.chatgpt.com/docs/config-file/config-reference)）。

```toml
# $CODEX_HOME/config.toml に統合する場合の案。現状へは未適用。
default_permissions = "fitlog-local"

[permissions.fitlog-local]
extends = ":workspace"

[permissions.fitlog-local.filesystem]
"/Users/saki/project/FitLog/.git/fitlog-runtime.lock" = "write"
"/Users/saki/project/FitLog/.git/ai-dev-helm-reviews" = "write"
```

worktreeの `.git` はpointerであり、本体共通Git領域の絶対pathを対象とする。index/refs/hooks/config、会社用設定、本体worktree全体への許可を追加しない。runtime lockは作成・削除が必要で、レビュー台帳は `.json` と `.json.lock` の作成/更新を含む。未知のbranch hashまで個別許可する案より対象directory全体の案が簡単だが、**台帳の改変を許可する工程承認ではない**。

未存在のpathや親directory作成、protected metadataに対する深いpathの明示許可は、OS・profileの実効設定を含めた実機検証が必要。本PRでは外部設定を変えず、実Git領域への書込み試験もしない。導入時は一時fixtureの `.git` で対象2か所の作成/削除だけが可能で、兄弟index/refs/configは拒否されることを比較する。その後、個人環境の管理設定・実効profileを確認し、対象worktreeのセッションで採用を検証する。確認できない間は既存の昇格申請を維持する。

Claude CodeのBash allowはファイル書込み範囲のsandbox設定を代替しない。`.git`全体をadditionalDirectoriesや書込み許可へ加える案は採用しない。
