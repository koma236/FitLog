# ai-dev-helm 3.7.1 への更新とマージ規則の変更

状態: 2026-11-05、ユーザーが独立設計レビュー結果を確認し、判断事項1を案Dへ変更して承認（2巡目のレビュー。1巡目は結果が出る前に停止。案Dへの変更後の再レビューはしていない）。branch `chore/harness-3.7.1`。baseline `269483a`。worktreeはmain checkout `/Users/saki/project/FitLog`、writerは親セッション1つ。

## 目的

1. helmを3.4.3から3.7.1へ更新する（初回の移行を含む）。
2. マージの方針を「原則AI、ユーザーが作業ごとに明示したときだけマージ前で止める」へ変える。

範囲外: Codex/Claude相互レビューの追加、v9のbranch・worktree・stashの片付け、製品コードの変更。

この PR 自身は旧ルールで扱い、PR作成で止める。マージはユーザーがGitHubで行う。

## 調査で確認した事実

| 項目 | 結果 | 確認方法 |
|---|---|---|
| Node | v24.10.0（20.19以上） | `node -v` |
| `upgrade --plan` | 91件。置換・三者マージ2件・新規・削除4件。警告なし | 実行 |
| 保留 | 5件: quality-gate.cjs 2コピー、quality-check/SKILL.md、CLAUDE.md#harness、AGENTS.md#harness | `--plan`と使い捨てclone |
| 三者マージ | development-policy.md、quality-policy.md | 同上 |
| settings/hooks | `.claude/settings.json`と`.codex/hooks.json`が変わる。Codexは`PreCompact`・`SessionStart`・`Stop`に3件追加 | 同上 |
| quality-gateの独自差分 | 3.4.3との差は`runGit`のoptions引数と`toolName`変数だけ。呼出し元がなく未使用（v9撤去の残り） | 3.4.3配布物とのdiff、grep |
| 回帰テスト | 3.7.1のhook本体で`scripts/test-quality-gate.cjs`が9件すべて合格 | 使い捨てclone |
| CLAUDE.md/AGENTS.mdの独自差分 | 先頭の個人運用節、CI方針の1行、Project Overview、Common Commands | 3.4.3テンプレートとのdiff |
| デプロイ | workflowは`ci.yml`のみでデプロイなし。マージは例外X2に当たらない | `.github/workflows` |
| GitHub設定 | ruleset有効: PR必須（承認数0）、`ci-required`、最新main必須、bypassなし。auto-mergeは無効 | `gh api`読取り |
| 現行hookのdeny | `gh pr merge`を拒否するdenyやCodex ruleはない | settings、`.codex/rules` |

## 問題: 新ルールを今の環境では実行できない

quality-gateの判定（3.7.1、有効なフラグあり、一時リポジトリで確認）:

| コマンド | 判定 | 理由 |
|---|---|---|
| `gh pr merge 5 --merge` | allow | ゲートが判定できる形 |
| `~/.local/bin/gh-koma236 pr merge 5 --merge` | block | コマンド名が`git`/`gh`以外 |
| `GH_CONFIG_DIR=… gh pr merge 5 --merge` | block | 環境変数の代入つき |

旧personal-workflow.mdは`gh-koma236`を必須とし、既定`gh`へのfallbackを禁じていた。そのままではAIのマージは常にhookで止まる。hookの回避は禁止なので、対処は環境と規則の側で行う（下記「ユーザーの決定」1）。

## 変更1: helmの更新

手順は3.7.1の`harness-upgrade.md`に従う。

1. `upgrade --record <repo外のファイル>`を実行する。`projectName: "FitLog"`がマニフェストに入る。`stacks`は空、`tools`はclaude-code・codexのまま。
2. 保留を次のとおり解消し、`upgrade --resolve`の後に`upgrade`を再実行する。

| 保留 | 解消の方針 |
|---|---|
| quality-gate.cjs 2コピー | 配布物と同一にする。未使用の独自差分は残さない。selftestがコピーの一致を確認する |
| quality-check/SKILL.md | 本体は配布物と同一にする。補足ファイルはスキルの規則を緩められないので、独自の節のうちコマンドと検証の当てはめ（hook回帰、11 checksの実行）だけを`documents/development/project/quality-check.md`へ移す。優先順位の文と「PR作成は最後に確認し、mergeは人間がGitHubで行う」は移さない。優先順位は CLAUDE.md 先頭の節が担う |
| CLAUDE.md#harness、AGENTS.md#harness | `harness`の目印は自動で入らないので手で囲む。管理ブロックの中は配布物と同一にする。独自の内容はブロックの外に置く |

解消後、`<file>.ai-dev-helm-new`（ignore対象で見えない）をすべて削除する。

3. CI方針の1行は管理ブロックの中にあるため、配布物の文に戻す。同じ趣旨は先頭の個人運用節（「CIはbuild/lint/型/全テスト/migrationとci-requiredを使う。配布元skillsの古い『CIはビルド確認のみ』は適用しない」）にあり、これが優先する。独自の文をブロックに残すと毎回の更新で衝突する。
4. Project OverviewとCommon Commandsはブロックの外にあるので変えない。
5. `documents/development/development-policy.md`の先頭の注記は三者マージで残るが、古い内容で新方針と矛盾する（下記「変更2」）。`<!-- ai-dev-helm:local:start -->`〜`end`で囲み、書き換える。
6. 移行手順4（版ごとの記録、`init`を禁じる規則の削除）: FitLogの運用文書に該当なし。
7. 検証で確かめること: `upgrade --verify`の終了コード0（未導入0・保留0）、`hook-selftest`全件OK、`claude doctor`の出力に`Invalid settings`がない、`node --test scripts/test-quality-gate.cjs`合格。

## 変更2: マージ規則

### 指定された箇所

CLAUDE.mdとAGENTS.mdの同じ行を同じ内容に変える。

- 10行目: 「…Issue作成・commit・feature push・PR作成・mergeまで追加申請せず進める。」（追記。「PRの作成とマージも承認の範囲に含める」を実現するために必要）
- 11行目: 「重大な範囲変更・不可逆操作・予算超過等だけ再確認する。」（PR作成の文を削除）
- 12行目: 「mergeは原則AIが行う（quality-check 完了・設計との差異なしのとき。helm の development-policy『承認後の進め方』に従う）。ユーザーが作業ごとにマージしないと明示した場合はマージ前で止める。GitHub の auto-merge、trunk への直接更新、force、hook の回避は禁止。」

personal-workflow.mdの「承認と自律実行」の節:

- 9行目: 承認の範囲に「PR作成、merge」を足す。
- 12行目: 上記12行目と同じ文に置き換える。

CLAUDE.md、AGENTS.md、personal-workflow.mdの3つとも、12行目の直後に次の行を足す（指定の文は変えず、決定2の例外を別の行にする）。

- 「`.github/workflows/` または `.github/ci/` を変えるPRは、常にマージ前で止める（例外X2。PR番号を示したユーザーのOKの後にAIがマージするか、ユーザーがGitHubでマージする）。」

personal-workflow.md「個人環境とGitHub」の節の18行目を、決定1の文に置き換える。「承認と自律実行」の節に、次のマージ手順を足す。

1. `gh api user`がkoma236、`gh repo view --json nameWithOwner`がkoma236/FitLogであることを確認する。違えばマージしない。
2. `gh pr view <n> --json state,baseRefName,headRefName,headRefOid`で、`state`がOPEN、`baseRefName`がmain、`headRefName`がフラグの`branch`、`headRefOid`がフラグの`commit`と完全に一致することを確認する。違えばマージしない。
3. `gh pr diff <n> --name-only`で`.github/workflows/`と`.github/ci/`の変更がないことを確認する。あれば止める。
4. `gh pr merge <n> --merge --match-head-commit <フラグのcommit>`で実行する。`--auto`と`--admin`は使わない。

### 指定の外で、新ルールと矛盾するため変更する箇所

| 箇所 | 現在 | 変更 |
|---|---|---|
| `skills/project/quality-check/SKILL.md:24` | 「PR作成は最後に確認し、mergeは人間がGitHubで行う。」 | ユーザーの指示で範囲に追加。本体は配布物と同一にし、この文は移行先の`documents/development/project/quality-check.md`へ移さない |
| `documents/development/development-policy.md:1` | 「各Git操作は個別承認。mergeは人間のみ。本書の包括承認・自動Git操作の記述は適用しない。」 | 「`personal-workflow.md` を先に読む。」だけにする。新ルールが参照する「承認後の進め方」を、この注記が無効にしているため |
| `README.md:17` | 「mergeは本人がGitHubで行います。」 | 新方針（原則AI、例外あり）を指す文へ置き換える |
| `README.md:19` | 「`.github/workflows/`・`.github/ci/`・テストを変えるPRは、merge前に本人が差分を確認します」 | 決定2に合わせて対象を`.github/workflows/`と`.github/ci/`にする。テストだけを変えるPRは例外の対象外。CIの判定は`compose.yaml`や`package.json`のscriptsからも変えられるので、「CIの改変がすべて止まる」とは書かない |
| `documents/setup/harness-setup.md:11` | 「PR作成は最後に確認し、統合は本人が行う。」 | 新方針へ置き換える。Common Commandsから参照される現行文書のため。同じファイルの5行目（版の記述）、8行目（`gh`の例外）、9行目（context-handoffの信頼）も合わせる |
| `README.md:40` | 「…feature pushまで委任します。…PR内容を最後に確認し、mergeは本人がGitHubで行います。」 | 新方針の説明へ置き換える |
| `documents/development/personal-parallel-workflow.md:65` | 「先行PRの人間によるmerge後」 | 「先行PRのmerge後」 |

### 書き換えないもの

過去の記録: personal-workflow.mdの「旧運用の履歴」節、`docs/`の既存の設計書と`docs/task-plan.md`、`docs/v9-preparation.md`、`documents/development/proposals/`、`documents/setup/`（`harness-setup.md`を除く）、`.ai-dev/*.plan.json`。

## ユーザーの決定

### 1. `gh-koma236`とquality-gateの不整合: 案D

ユーザーがMacの環境で、既定の`gh`を個人用（koma236）に、会社用を別のコマンドに切り替え済み。`gh auth status`はkoma236だけ（2026-11-05に確認。`gh repo view`はkoma236/FitLog、`GH_*`/`GITHUB_*`の環境変数なし）。

- `.claude/settings.local.json`は作らない。worktreeに同じファイルを置く規則も設けない。
- personal-workflow.md 18行目を次に置き換える。「GitHubには`gh`を使う。Issue・PR・マージなどの操作の前に`gh api user`がkoma236、対象のrepoがkoma236/FitLogであることを確認し、違えば操作しない。」
- Claude CodeもCodexも同じ`gh`を使う。worktreeでも同じ。
- quality-gateはこの`gh pr merge`を判定する。ただしhookはローカルのHEADとフラグだけを照合し、PR番号を見ない（フラグが有効なら`gh pr merge 99`も通る）。rulesetの承認数は0なので、対象PRの取り違えは上のマージ手順で防ぐ。
- 限界: 既定の`gh`の切り替えは端末の状態で、リポジトリでは保証できない。別accountになった場合は操作前の確認が止める。

### 2. `.github/workflows/`・`.github/ci/`を変えるPR: 案b

常にマージ前で止める。CIの変更はCI自身の判定を変えられるため。これは新方針の唯一の常設の例外で、規則とマージ手順3で守る（hookは強制しない）。

### 3. `quality-check/SKILL.md:24`

変更の範囲に含める（上の表）。

### 4. 決定2で止めた後の扱い: X2

PR番号を示したユーザーのOKの後にAIがマージするか、ユーザーがGitHubでマージする。

## 独立設計レビューへの対応

| 指摘 | 重要度 | 対応 |
|---|---|---|
| M1 hookはPR番号を見ない | Medium | マージ手順を追加（`--match-head-commit`。フラグなしblock・ありallowを再現済み） |
| M2 linked worktreeで決定1が効かない | Medium | 案Dでは対象のファイルがなくなり解消 |
| M3 `harness-setup.md:11`の旧ルール | Medium | 変更対象へ移動、検索語を拡大 |
| M4 例外の判定方法とOK後の扱いが未定義 | Medium | 判定はマージ手順3。OK後はX2 |
| M5 レビュー範囲から変更2の文書が漏れる | Medium | 実装計画4を分割 |
| M6 Codexの扱いが未定義 | Medium | 同じ`gh`を使えるので、`codex-trust`の確認だけ |
| L1 wrapperより環境変数が狭い | Low | 確認にrepoを追加 |
| L2 トークン上書きの未確認 | Low | 案Dでは設定しないので対象外。環境変数があれば操作前の確認が止める |
| L3 過去の決定との関係 | Low | 案Dは`GH_CONFIG_DIR`をexportしないので対象外 |
| L4 `--auto`・`--admin`がhookを通る | Low | マージ手順で禁止（再現済み）。`gate.denyCommands`による強制はしない |
| L5 目印と`.ai-dev-helm-new`の手順 | Low | 変更1と受け入れ条件に追加 |
| L6 補足ファイルの優先順位 | Low | 当てはめだけを移す |
| L7 決定2の根拠の限界 | Low | README.mdの文に反映 |
| L8 `settings.local.json`の判定が厳しい | Low | 案Dではファイルを作らないので対象外 |
| L9 「5 declared out」の内訳が不明 | Low | 実装時に特定し、差分の有無とともにPR本文へ書く |

## 設計との差異（実装中に記録）

品質レビューの高の指摘への対応で、承認済みの設計にないものを足した。

1. AIがマージするときは、ハーネスのみの差分でも免除を使わず、常にquality-checkを通してフラグを作る規則（personal-workflow.md）。配布の規則ではハーネスのみの差分はquality-check不要で、`quality-check 完了`を条件とする新ルールと矛盾し、マージ手順2も実行できなかったため。
2. `.ai-dev-helm.json`に`gate.controlPlane`を宣言し、hookでも免除しない。CLAUDE.md・AGENTS.mdだけのPRがフラグなしでAIにマージできたため。
3. 回帰テストの追加（`scripts/test-quality-gate.cjs`。マージ手順と上記の宣言）。

細部: personal-workflow.mdとharness-setup.mdの「本人の統合」「本人統合」から「本人」を除いた（受け入れ条件の検索に当たる、過去の作業を指す文）。

## 実装計画

1. `gh`でaccountとrepoを確認してIssueを1件作る。branch名は指定どおり`chore/harness-3.7.1`。
2. 変更1の更新と保留の解消、変更2の文書変更を行う。
3. 11 checksを共有runtimeの排他枠内で実行し、hook回帰、`--verify`、`hook-selftest`、`claude doctor`を実行する。
4. quality-checkを行う。upgradeの部分のレビュー範囲は3.7.1のharness-upgrade.mdに従い、三者マージ・衝突を直したファイル・マニフェスト・補足ファイル・ルート規則とする。変更2の文書（personal-workflow.md、personal-parallel-workflow.md、README.md、harness-setup.md）はすべて対象にする。ゲート制御面を変えるのでSecurityの専門レビューが入る。
5. `~/.config/git-koma236/config`の個人identityでcommitし、originとSSH accountを確認してfeature pushする。
6. `gh pr create --body-file`でPRを作成し、「5 declared out」の内訳、宣言で外した部品の配布元の差分、検証結果を本文に載せる。マージはしない。
7. `codex-trust --dir <repo> --codex-home ~/.codex-personal`（読み取りのみ）を実行し、結果を報告する。
8. 最終報告に次を書く: PRのURL、差異、`.codex/hooks.json`が変わったので`CODEX_HOME=$HOME/.codex-personal`のCodexで`/hooks`の信頼をやり直す必要があること、実client未確認の項目。

## 受け入れ条件

- `upgrade --verify`の終了コード0、`hook-selftest`全件OK、`claude doctor`に`Invalid settings`なし。
- `.ai-dev-helm.json`が3.7.1、`stacks`は空、`pending`なし。`*.ai-dev-helm-new`が残っていない。
- CLAUDE.md/AGENTS.mdの先頭の個人運用節が管理ブロックの外にあり、指定の文になっている。
- 現行規則の中に「mergeは人間」の趣旨が、決定2の例外を除いて残らない（履歴を除く）。`README.md`・`documents/development/`（`proposals/`を除く）・`documents/setup/harness-setup.md`・`skills/`・`.claude/`・`.codex/`・`.github/`を、`merge`または`統合`と`人間`または`本人`を含む行で`git grep`して確認する。`quality-check/SKILL.md`と`documents/development/project/quality-check.md`も対象に含まれる。
- CLAUDE.md、AGENTS.md、personal-workflow.mdに決定2の例外の行がある。
- 履歴の文書と製品コード（`backend/`・`frontend/`・`terraform/`）に差分がない。
- 11 checks、`scripts/test-quality-gate.cjs`、CIの`ci-required`が成功する。失敗や未実行は成功として扱わない。
- 決定1: `.claude/settings.local.json`を作っていない。`gh api user`がkoma236を返す。personal-workflow.md 18行目が指定の文になっている。一時リポジトリで`gh pr merge --match-head-commit`がフラグなしで拒否、フラグありで許可される。実際のマージでの確認が次のPRになることを報告する。
