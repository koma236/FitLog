# v9 個人用Git/GitHub環境の接続設計

状態: 設計・実装はユーザー承認済み。共通ハーネスと個人用設定へ配置済み。
実装結果と最終検証は [導入状況](harness-setup.md) を参照。

## 問題と到達点

`~/project/ai-dev-harness/scripts/v9/gitops.py` の `_safe_environment()` は
`GH_CONFIG_DIR` を除去する一方、既定のGit設定とtoken環境変数を使用し得る。
FitLogでは既定ghは会社用であり、この経路を実行してはいけない。
originの保存値はHTTPSだが、既定Git設定のURL rewriteでSSH aliasへ変換される。
現行v9のrewrite拒否は維持し、専用の個人用設定を使うことで原因を除く。

読取り診断で `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1` のprocessから
fetch/pushのoriginを取得すると、両方とも `https://github.com/koma236/FitLog.git` だった。
これは設定選択の診断のみであり、この環境を使ってGit操作や承認を迂回したものではない。

成功条件は、同じ個人用環境をproposal作成・本人承認後の実行・子processで使用し、
アカウントや設定が変われば再承認を必要とすること。
未設定なら会社用へ戻らず、Git/GitHub操作の前に明示エラーで止まること。

## 設定契約

共通ハーネスのprivate領域に `~/.ai-dev-harness/personal-git.toml` を新設する。
許可する項目はschema_version=1と以下の3項目のみ。tokenや認証本文は保存しない。

```toml
schema_version = 1
account = "koma236"
gh_config_dir = ".config/gh-koma236"
git_config_file = ".config/git-koma236/config"
```

パスはhome相対。絶対パス、`..`、symlink、既定gh/Git設定、会社用 `.codex`、
`manabi-backoffice` は拒否する。設定ファイルは本人所有、他ユーザーから読めないことを確認する。
Git設定・gh設定ディレクトリの存在を確認し、欠落なら停止する。
GH_CONFIG_DIRの中身（tokenを含み得るhosts.yml）はアプリから読み出し・複製・ログ記録しない。

v9 Git操作はこの設定を必須とする。status/dry-run、仕様作成、provider実行、v8は変更しない。
既存ユーザーはGit操作前に明示的な設定が必要になる。暗黙の既定認証を残す互換モードは設けない。

## 子process環境

Git/GitHub操作の共通runnerで、許可済みの基本環境に以下を設定する。

- `GH_CONFIG_DIR`: 検証済みの個人用ディレクトリ。
- `GIT_CONFIG_GLOBAL`: 検証済みの個人用Git設定ファイル。
- `GIT_CONFIG_NOSYSTEM=1`: システムGit設定を読み込まない。
- `GIT_TERMINAL_PROMPT=0`: Gitの認証未設定を対話で補わず停止する。
- 親のGH/GITHUB token、host/repo override、Git config注入、askpass、trace/debugを引き継がない。

同じ環境を内部のghとcredential helperにも渡す。HOMEは変更しない。
`snapshot_project()` は例外として、既存の認証不要・global/system設定を使わない
検査用環境を維持する。providerやchecks実行用の環境は変更しない。
Gitのinclude/includeIfで会社設定へ移動しないよう、個人Git設定と対象リポジトリの
ローカル/worktree設定をinclude展開なしで確認し、include指定があれば読込み前に停止する。
Gitコマンドの引数、remote検証、feature branch制限、実行順序、本人承認、hooksは維持する。
core.hooksPathを無効化する指定や `--no-verify` は追加しない。

## FitLogで配置する個人Git設定

`~/.config/git-koma236/config`（0600、親は0700）に次を設定する。
authorはFitLogの既存commitに記録された個人名義を用いる。

```gitconfig
[user]
    name = koma
    email = 88425419+koma236@users.noreply.github.com
[credential "https://github.com"]
    helper =
    helper = !/Users/saki/.local/bin/gh-koma236 auth git-credential
```

既定のグローバル設定、会社用認証、SSH鍵、originの保存値は変更しない。
Gitは保存済みの `https://github.com/koma236/FitLog.git` へ直接接続し、
HTTPSの認証は作成済みの個人用gh入口へ委ねる。
設定を既定shell全体へexportしない。v9を使わない通常のgitにまで適用したとは説明しない。

## Proposalと実行の結び付け

proposalに個人環境情報（account、設定先、Git設定のfingerprint）を追加してdigestへ含める。
Git設定のfingerprintは個人Git設定に加え、対象リポジトリのローカル/worktree設定も対象とする。
ファイルの有無・対象pathと内容のSHA-256を照合し、本文や設定値はproposalへ保存・表示しない。
これにより承認後のuser.emailやcore.hooksPath変更、worktree設定の追加・削除もstaleにする。
GitHub認証ファイルやtoken自体はhash化・記録しない。
実行時には同じ設定を再解決し、proposalと照合する。変更時はstaleとして停止する。
GitHub APIが返すloginは設定accountと一致することを要求し、既存のproposal account照合も維持する。
既存の環境情報を含まない未実行proposalは、再準備・本人承認を要求する。
既存receiptは書き換えず、環境の対応を証明できないreceiptを新操作の根拠に使わない。
ローカルcommitでも同じGit設定とhooksを使用する。remoteなしをGitHub成功とは記録しない。

## 変更範囲と実施順

1. 共通ハーネスの作業ブランチ `fix/v9-personal-git-environment` を作成する。
   既存の未追跡ファイルには触れない。Issueは別途内容提示・個別承認が必要。
2. `scripts/v9/gitops.py` と小さな環境設定モジュールを変更し、上記境界を実装する。
3. `tests/test_v9_gitops.py` と必要な環境テスト・fixtureを更新する。
4. README、v9 Git運用・エラーコード・ai-dev-chatの必要な説明を更新する。
5. ハーネス回帰テストを実行し、必要な品質レビュー・人間承認を経る。
6. 個人設定を配置し、FitLogでは読取り診断・APIのaccount/repo照合・git ls-remoteまで確認する。
   Issue、commit、push、PRは各proposalの個別承認後。mergeは人間のみ。

## 検証

一時home・一時Gitリポジトリを使用し、実認証・会社設定には触れない。

- 既定gh/global/system configに検出用設定があっても個人環境のコマンドへ混入しない。
- token環境変数を渡しても子processへ渡らず、明示したGH_CONFIG_DIRが残る。
- 設定未作成、symlink、不正path/include、アカウント不一致、設定変更後の実行を拒否する。
- proposal作成後にローカル/worktree設定のuser.email、core.hooksPath、ファイル有無が変われば、Git変更操作の前にstaleで拒否する。
- 正常な個人設定でrepository/remote/accountを同定できる。
- 有効な個人/ローカル設定にURL rewriteがある場合は従来どおり拒否する。
- ローカルpre-commit hookが実行され、その失敗でcommitが停止する。
- 非TTY、誤った確認文字列、mainへのpush、force、merge、snapshot変更、receipt順序の既存テストを維持する。
- ハーネスの既存コマンド `python3 -B -m unittest discover -s tests -v` を実行する。

FitLogの `.ai-dev/project.toml` はchecks未設定のままにし、ハーネスのテスト成功を
FitLogアプリのchecks成功やv9 workflow承認として扱わない。

## 範囲外・限界

アプリ実装、スタック選定、会社設定の探索、tokenコピー、hook信頼の代行、Git操作の承認代行は対象外。
OSによる完全な隔離を追加する変更ではない。PATH上の実行ファイルや同一ユーザーの任意改変まで防ぐものではない。
FitLogの未設定checks・manifest/plan不足によるv9 workflow未準備はこの変更では解消しない。

根拠: [Git環境変数](https://git-scm.com/docs/git)、
[Git credential helper](https://git-scm.com/docs/gitcredentials)、
共通ハーネス `scripts/v9/gitops.py` と `scripts/v9/execution.py`。

## 設計レビュー結果

2026-10-27、FitLog導入設計としてdocument-reviewer（gpt-6.1-sol / high）による1回のレビューを実施。
これはv9の実装結果レビューや人間承認receiptではない。

- High: 0件。
- Medium: 1件。ローカル/worktree Git設定の変更がproposalに結び付かない点。
  対応: fingerprintの対象を拡張し、名義・hooks設定・設定ファイル有無の変更を拒否する契約とテストを追加。
- Low: 1件。snapshot用Git環境との関係が不明確な点。
  対応: snapshotは従来の認証不要の検査用環境を維持する例外と明記。

指摘を設計へ反映して実装済み。実装レビューではパスの大文字小文字、symlinkと親参照、
gh設定ファイルのsymlink、Git parserのrepository探索を追加検証し修正した。
テストfixtureのログ保存先と初期ブランチを明示した点が実装時の追加変更。
既存のv8/provider実装とFitLogのchecksは変更していない。
