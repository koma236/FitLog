# PRの手動相互レビュー手順（レビューAI向け）

最終更新: 2026-11-05。関連: [Issue #40](https://github.com/koma236/FitLog/issues/40)、[個人開発運用](personal-workflow.md#高リスクprの手動相互レビュー)。

根本さんが実装していない側のprovider（Codex / Claude）を対象PRのworktreeで開き、「cross-review.md に従って PR #N をレビューして」と依頼したときの手順です。あなたはレビュー担当です。設計・実装の開発フローを開始せず、以下の読取りと依頼されたPRコメント投稿だけを行ってください。

これは根本さんが定めた手動運用で、helmのreview-budgetの枠は使いません。通常の設計レビュー・quality-checkはそれぞれ従来の予算と手順を維持します。別providerを使うだけで独立性を満たすとはせず、作者から独立した根拠に照らして判断します。

## 1. 操作範囲と開始条件

- リポジトリのファイル変更、commit、push、merge、branch切替、checkout、fetch、既存変更の退避・削除を行いません。サーバー起動、依存導入、状態を書き込むテスト実行も行いません。
- サブエージェント・他provider・外部レビューCLIを起動せず、review-budgetの予約・消費・変更を行いません。
- 外部への書込みは、依頼されたPRに対する `gh pr comment` のみです。PR本文・状態・レビュー承認・Issueなどを変更しません。
- [個人開発運用](personal-workflow.md)を読み、対象は `koma236/FitLog`、会社用設定・会社repoの探索は禁止と確認します。Codexは `CODEX_HOME=$HOME/.codex-personal` を使用します。

対象PRのworktreeをcwdとして、以下の読取りを行います。

```sh
pwd
git branch --show-current
git rev-parse HEAD
git status --porcelain=v1 --untracked-files=all
gh api user --jq .login
gh repo view --json nameWithOwner
```

GitHub操作前には毎回、accountが `koma236`、repoが `koma236/FitLog` と照合します。不一致・確認不能ならGitHubへの操作を進めません。未commitのtracked/index差分または未追跡ファイルがあれば停止し、根本さんに報告します。既存のignoredな依存物・検証ログはレビュー根拠にしません。

対象PRの番号を指定して取得します。以下の `<N>` は依頼された実番号に置き換えます。

```sh
gh pr view <N> --json number,url,state,baseRefName,baseRefOid,headRefName,headRefOid,body
```

PRがOPENで、作業branchがPRのhead branch、ローカルHEADがPRの完全なhead OIDと一致することを確認し、base/head OIDを固定して記録します。PR本文の実装provider・モデルと自分の実行環境を照合し、実装していない側のproviderであることを確認します。両providerが実装に参加して別側を満たせない、実装側の記載がない、モデルの実値を確認できない、headやbranchが違う場合は、推測・自動修復せず停止して根本さんに報告します。

## 2. 独立した根拠で確認する

```sh
gh pr diff <N>
git diff --name-status <base-OID>...<head-OID>
git diff <base-OID>...<head-OID>
git show <head-OID>:<対象ファイル>
```

`<base-OID>` / `<head-OID>` は手順1で固定した値です。必要なcommit objectがローカルになければfetchせず、読めない範囲を報告します。レビュー根拠は固定したheadの追跡ファイルとbase/head間の差分に限定します。`gh pr diff` と固定した差分が食い違えばhead更新等を疑い、投稿前に停止します。

次を実装・テストと照合してください。

- Issue、関連設計・仕様・受入条件。作者の説明をそのまま正しさの証明にしません。
- 変更に該当する `.github/review-*.md`。認証・認可、CI、制御面、文書整合などの関連観点を選びます。
- テストの期待値の根拠、異常系・境界値、変更された契約を検出できるか。作者の実装と同じ仮定をテストが繰り返していないか確認します。
- 実際の設定・既存の契約。外部仕様の確認が必要なら公式一次資料を参照し、確認した根拠を示します。

確認できない根拠や未実行のテストは明記し、完全に検証済みとは扱いません。必要な根拠が欠けてレビューを完了できない場合は、制約を根本さんに報告して止めます。テスト実行はこの依頼の操作範囲に含めません。

## 3. コメントを投稿して終了する

投稿本文の冒頭は次の形式で、実際のprovider・モデル・完全なhead OIDを記載します。例示の値や推測したモデル名を使いません。

```text
相互レビュー（provider: <実値> / モデル: <実値> / 対象 head commit: <完全OID>）

確認範囲・根拠: <仕様、設計、契約、差分等>
未確認事項: <未実行のテスト等>

High
- <対象ファイル・行、問題、影響、独立した根拠、必要な対応>

Medium
- <同上>

Low
- <同上>
```

各区分で指摘がなければ「指摘なし」と書きます。Highは具体的な手順で起きる誤動作、認証・認可や保護条件の破壊、要件未達などです。Mediumは直ちに停止必須ではない懸念、Lowは軽微な改善です。Lowも記録するのはこの手動相互レビューの契約で、通常quality-checkの指摘運用は変更しません。

投稿直前に、手順1の個人account/repo、worktree状態、ローカルHEAD、PRのOPEN状態・head OIDを再取得します。未commit変更・未追跡ファイル・head更新等があれば投稿せず報告します。一致した場合だけ `gh pr comment <N> --body <本文>` で投稿します。`<本文>` は実際の本文を単一引数で渡し、シェル展開による意図しない実行を避けてください。複数行本文も通常のbody引数で渡し、リポジトリ内に投稿用ファイルを作りません。

投稿結果のコメントURLを確認し、投稿後も個人環境照合のうえPRのheadを読み直します。照合と投稿は原子的ではないため、投稿中にheadが更新されていたら旧headに対するコメントである旨を根本さんに報告します。自動で再レビュー・再投稿はしません。コメントURL、対象head、指摘件数と未確認事項を根本さんに報告して終了します。指摘の修正やmergeは実装AIと根本さんの[再開手順](personal-workflow.md#高リスクprの手動相互レビュー)に委ねます。
