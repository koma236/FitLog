# Issue #36: ゲート拒否規則とマージ停止手順の補完

状態: 独立設計レビュー済み・2026-11-05 ユーザー承認済み（CLI 追加を含む）。対象 branch は `fix/gate-followup-36`。PR 作成後、マージ前で停止する。

## 根拠と現状

Issue #36、PR #35 本文の残件、2026-11-05 の引き継ぎ指示を根拠とする。既存の配布 hook 本体は変更せず、FitLog の宣言・登録・手順・回帰試験で補完する。会社用環境や旧 v9 記録は対象外。

引き継ぎ差分は `.codex/hooks.json` と `scripts/test-quality-gate.cjs`。全回帰試験を実行し 17 件中 15 成功、登録の 2 件が `collaborationlist_agents` の除外期待で失敗した。

## 1. review-budget の登録

親の提案: PreToolUse / PostToolUse とも、現在の `collaboration.*` を維持する。「collaboration で始まるツール名を足す」という依頼を登録の契約とし、テストの肯定例に list / wait / interrupt と未知の接尾辞も含める。非 collaboration の類似名は除外する。既存テストの「承認済み」とするコメントは、今回の承認前の事実と区別して直す。

登録は hook への配送条件であり、レビューの判定は hook 本体の責務。本体の `request()` は既知の spawn / followup / send / resume だけを候補とし、list / wait / interrupt や未知名をレビューとして数えない。この非候補の扱いも一時 Git fixture 内の hook 実行で試験し、登録テストだけで消費制御の証明としない。実リポジトリの review-budget 状態を試験から編集しない。

matcher は変更しないので、本体への再コピーや再信頼は行わない。独立設計レビューは予約済み token `500018f859557c3c97f760d03723c19c` / role `document-reviewer` を使用し、正規 spawn の task_name と message 先頭に印を付ける。起動直後に正規 `status` で used を確認する。記録されなければ追加起動・状態修正はせず、状況を報告して止める。

## 2. gh api の拒否宣言

`.ai-dev-helm.json` の `gate.denyCommands` に、既存エンジンの `{ all: [正規表現], reason }` を使い以下を追加する。

- `gh api graphql` でコマンド本文に `mergePullRequest` が見える呼び出しを拒否する。
- `gh api` の repository ruleset エンドポイント (`repos/<owner>/<repo>/rulesets[/<id>]`) に対する更新・削除の明示 HTTP method（PUT / PATCH / DELETE）を拒否する。作成も書込みとして POST を拒否する。
- rulesets エンドポイントで `-f` / `-F` / `--field` / `--raw-field` / `--input` を指定する暗黙 POST も、明示 GET を伴う場合を含め保守的に拒否する。通常の一覧・個別 GET と無関係の API 読取りは通す。

`gh` と既存個人 wrapper の形、endpoint と option の順序、短縮・長形式と等号形式、引用符、改行継続、大文字小文字を代表例として扱う。正規表現はコマンド文字列を判定する既存契約に従う。別ツール経由やファイル内に隠した GraphQL 本文など、文字列に対象が見えない呼び出しまでの検出は保証しない。既存の REST PR merge の検出・通常 PR 作成・feature push は維持する。auto-merge 禁止・account 照合は既存の運用規則とサーバ設定を維持し、万能な防御と記述しない。

回帰試験は宣言を fixture に commit して実行する（エンジンは HEAD / trunk の commit 済み宣言を読む）。両 hook で、フラグ有無にかかわらず対象が拒否され、読取りは許可されることを確認する。未 commit の宣言だけで有効化したと主張しない。

## 3. CI とゲート制御面の X2 停止判定

`personal-workflow.md`、AGENTS.md / CLAUDE.md の個人運用節、README.md の要約を同期する。停止対象は `.github/workflows/`・`.github/ci/`、および `.ai-dev-helm.json` の `gate.controlPlane` に一致するファイル。宣言自身の変更で検出が弱まらないよう `.ai-dev-helm.json` 自体も常に停止対象にする。

判定を再現可能にする小さい読取り専用 CLI `scripts/check-merge-stop.cjs` と専用試験を追加する。CLI は `--base <完全 commit OID>` と `--head <完全 commit OID>` を必須とする。GitHub へ接続せず、merge / push / フラグ操作を行わない。

- 親が `git fetch origin` と `gh pr view` により PR の baseRefOid / headRefOid を取得し、対象 object がローカルに存在し、ローカル HEAD・フラグ・PR head が一致することを確認する。
- CLI は `git diff --name-only -z --no-renames <base>...<head>` で PR 差分を採取する。削除と追加に分けるのでリネーム元・先の両方を検査でき、空白や非 ASCII のパスも保つ。
- base と head の両方の manifest の controlPlane の和集合を使う。`**/` はゼロ階層も含む、`*` / `?` は `/` を越えない、末尾 `/` は配下全体、大文字小文字は既存ゲートと同じく区別しない。未知の glob 構文を拡張しない。
- manifest が無い旧 commit は空宣言として扱う。存在する manifest の JSON 不正・controlPlane の型不正、Git エラー・不明 object・共通祖先なしは判定失敗として停止する。controlPlane の key が無い場合は空配列相当とし、片側にある宣言で保護する。
- JSON に検出パスと判定を出力する。終了コードは 0=対象なし、2=X2対象あり、1=判定失敗。失敗を対象なしとして扱わない。

制御面には hook や skills なども含むため、この PR 自身も停止対象になる。これは運用の停止判断を補助する CLI であり、ユーザーの X2 の OK を hook が検証する仕組みではない。

## 4. マージ手順の補完と残件

personal-workflow の手順 3 を上記判定に置き換え、対象があれば PR番号と head OID・検出パスを示して止める。対象 PR を指定したユーザーの X2 の OK の後、手順 1〜3 の照合・検出を再実行し、承認対象の head と対象範囲が一致する場合だけ手順 4 へ進む。head が変わったら承認を取り直す。判定エラーは承認で読み飛ばさない。本タスクでは PR 作成時に必ず止め、今回の設計承認をマージの OK と解釈しない。

main が進んでマージを拒否されたら、`--admin` 等で回避せず fetch して差分を確認する。必要なら feature branch に最新 main を通常 merge し、失敗の原因を修正して quality-check・commit・通常 push・CI と手順 1〜3 をやり直す。force / 自動 rebase はしない。head 更新後は X2 の OK も新しい head に対して取り直す。

マージ後は PR が MERGED であることと統合結果を確認し、今回の branch / commit に対応する `.quality-check-passed` だけを削除する。失敗・結果不明では成功として後始末しない。次の確認では常に commit 一致を要求する。

README の停止条件に設計との差異ありを加え、CI と制御面の条件を揃える。personal-workflow の個人環境に「Codex は `codex-me` で起動する（`CODEX_HOME=$HOME/.codex-personal`）」を 1 行追記する。

PR #35 の小さいテスト不足として `.cursorrules` / `.cursor/**` の制御面 fixture、手順と同じ state / base / head の `gh pr view` の形、既存 REST merge 経路を回帰に含める。CHANGELOGのみの免除や古いbranchを含め hook の免除を完全に消したと誤解させる文言を直し、AI の手順は常に quality-check とフラグ照合を要求すると記す。account / チャットだけの停止指示 / 平文フラグ / context-handoff の既存限界を解決したとは扱わない。PR #35 の履歴本文は書き換えず、この PR の対応表に結果を残す。

## 検証と実装計画

リスクは High（ゲート制御面）。期待値の根拠は本設計とユーザー指示を先に置き、承認後、test-design skill に従う非 commit のメモへ状態遷移・反証項目を具体化する。

1. Issue / branch は既存の #36 / fix/gate-followup-36 を使う。独立設計レビューは既存予約 1 体のみ、親が実装を担当する。
2. matcher を維持して登録試験を修正し、fixture 内の非レビュー動作を確認する。拒否宣言の拒否・許可の対を追加し、宣言を追加する。
3. X2 判定 CLI を TDD で作る。通常ファイル / CI / 各 controlPlane パターン / 削除 / 内外へのリネーム / 宣言削除 / 不正宣言 / 読取りエラーを固定オラクルで検証する。両版の glob 実装の出力を期待値にコピーしない。
4. 運用文書を同期し、設計との照合・全ゲート回帰と新しい CLI 試験を実行する。
5. quality-check skill の機械チェックと独立品質レビューを実行する。11 checks は project.toml の argv を共有 runtime の排他枠内で親が直接実行し、snapshot・日時・終了コードを記録する。レビューはその時点で正式に別途予約し、上限を守る。hook-selftest 等の適用可否も同 skill で確認する。
6. 自分の変更だけ commit・feature push し、Closes #36 の PR を作成、CI 結果と残件を報告してマージ前で止める。本体側への一時 hook コピーは変更・削除しない。

外部契約の参照: [GitHub rules API](https://docs.github.com/en/rest/repos/rules)、[GitHub GraphQL pull requests](https://docs.github.com/en/graphql/reference/pull-requests)、[GitHub CLI api](https://cli.github.com/manual/gh_api)。ローカル diff 方式により PR files API の上限に依存しない。

## 設計レビュー結果

予約済み token の席を正規の `helm-doc-reviewer` 起動で 1 回使用した。起動後の `review-budget.cjs status` で `used.document-reviewer`、receipt、agent 名の記録を確認した。直接の状態編集・追加予約・追加レビューは行っていない。

結果は High 0 件・Medium 0 件、設計承認に進めるとの判定。レビュアーは登録と候補判定の分離、commit 済み宣言の fixture、リネーム両側と両版の制御面、X2 の続行、復旧・後始末、文書同期とテスト不足を既存契約に照合した。指摘なしのため設計の修正対応はない。実装・試験の最終品質レビューを代替するものではない。

## 実装時の差異

- CLI 名を `scripts/check-merge-stop.cjs` から `scripts/check-pr-stop.cjs` に変更した（試験も `test-check-pr-stop.cjs`）。既存ゲートは node の引数の `merge` を単語境界で操作語と解釈し、元のファイル名を指定した無害な試験まで拒否した。拒否メッセージの「push/merge しないコマンドはそれらの語を避ける」に従い、読取り専用機能に即した PR 停止判定の名前とした。配布 hook やその防御は変更せず、CLI の契約・機能・検証範囲は同じ。最終報告・PR にもこの命名差異を記載する。
- 11 checks の実行方法は、ユーザーの追加指示により一時スクリプトへ変更した。登録済み argv だけを順番に実行し、同じプロセス内で共有 lock の取得と `try/finally` による解放、id・終了コード・開始/終了時刻の保存を行う。Git の送信・統合、品質フラグ、gh 操作は含まない。前の標準入力待ち保持方式は EOF で終了したため不採用とし、その lock はユーザーが削除済み。新方式の初回実行は DB 停止により 9 成功・2 失敗で、解放済みを `ls` でも確認した。これを成功結果として流用しない。
- その後のユーザー指示で、同じ一時スクリプト内に Compose による DB 稼働状態の確認・必要時の起動・migration 状態の前後記録を追加した。今回起動した DB のみを `finally` で停止し、続いて lock を解放する。volume/image 削除や Git/gh 操作は含まない。再実行は全 11 checks が終了 0、backend 620 / frontend 190 成功、migration 22 件の状態は前後一致。Compose で DB 停止、`ls` で lock 不在を確認した。追加指示による実行方法の変更であり、リポジトリへ一時スクリプトを追加しない。
