# 個人用GitHub CLI環境の設定案

状態: 2026-10-27、ユーザー承認後に個人用ディレクトリと専用コマンドを作成済み。
ブラウザ認証は本人が実施済み。個人用入口からGitHub APIで `koma236` を確認した。
`koma236/FitLog` の `viewerPermission=ADMIN`、認証状態 `success`、保存先 `keyring` を確認した。
既定のgh・会社用認証・グローバルGit設定は変更していない。

配置後にshell構文、gh 2.89.0の起動、両パスの権限0700を確認した。
4種のtoken環境変数へ検証用の非秘密文字列を渡しても、専用コマンドは未認証を返すことを確認した。
作成直後の個人用設定ディレクトリは空だった。その後、本人認証とAPI確認が完了した。

## 分離するもの

| 項目 | 提案 |
| --- | --- |
| 個人用設定 | `~/.config/gh-koma236`（本人のみアクセスできる権限0700） |
| 専用入口 | `~/.local/bin/gh-koma236`（既存の `gh` は置き換えない） |
| 認証 | ブラウザで `koma236` に新規ログイン。既存tokenのコピー・表示なし |
| 保存先 | macOSの資格情報ストア。平文保存へのfallbackがあれば設定完了とせず報告 |
| v9 | private profileを自動読込み。個人gh/Git設定を子processへ適用済み |

既定のghは会社用として扱う。既定設定の読取り・変更、logout、auth switch、
auth setup-git、グローバルGit設定変更は行わない。会社用tokenを参照しない。

## 配置済みの専用入口

`GH_CONFIG_DIR`だけでなく、保存済み認証より優先されるtoken環境変数も子processから除く。
対象host/repositoryの環境変数とdebug出力も継承しない。親shellの環境は変更しない。

```sh
#!/bin/sh
exec env \
  -u GH_TOKEN -u GITHUB_TOKEN \
  -u GH_ENTERPRISE_TOKEN -u GITHUB_ENTERPRISE_TOKEN \
  -u GH_HOST -u GH_REPO -u GH_DEBUG -u DEBUG \
  GH_CONFIG_DIR="$HOME/.config/gh-koma236" \
  /usr/local/bin/gh "$@"
```

`/usr/local/bin/gh` は今回存在を確認した実行ファイル。
配置時に既存ファイルがあれば上書きせず確認する。
shell全体に `GH_CONFIG_DIR` をexportしたり、`gh` のaliasを変更したりしない。

## 承認後の手順

1. 個人用ディレクトリと専用入口だけを作成する（完了）。
2. 本人が通常ターミナルで次を実行する。

   ```sh
   "$HOME/.local/bin/gh-koma236" auth login \
     --hostname github.com --git-protocol ssh --skip-ssh-key --web
   ```

3. ブラウザに表示されるアカウントが `koma236` であることを本人が確認する。
   別アカウントなら承認しない。SSH鍵の生成・アップロードは行わない。
4. 新規認証後、個人用入口から `api --hostname github.com user --jq .login` を実行し、
   出力が `koma236` と完全一致することを確認する。tokenは取得・表示しない。
5. 一致後に `repo view koma236/FitLog --json nameWithOwner,url,viewerPermission` で対象を確認する。
   `auth status --json hosts` は `--show-token` を付けず、必要なアカウント・保存先項目だけを抽出して確認する。
   JSON形式は認証失敗時も終了コード0になり得るため、終了コードだけで成功扱いしない。
6. 不一致・未認証・平文保存fallbackなら停止し、完了扱いしない。

ここで許可されるのは認証と読取り確認まで。Issue・commit・push・PRは各内容の個別承認が別途必要。

## v9とGit接続（実装済み）

承認済みの [詳細設計](v9-personal-git-design.md) に従い、共通ハーネスを変更した。
v9は `~/.ai-dev-harness/personal-git.toml` を自動で読み込み、
`~/.config/gh-koma236` と `~/.config/git-koma236/config` を選択する。
毎回のexportや既定ghの切替は不要。未設定・不正な設定なら `V9_GIT_ENV` で停止する。

既存の `codex-me` は `CODEX_HOME="$HOME/.codex-personal"` でCodexを起動する。
iTerm2で個人プロジェクトへ移動し `codex-me` を実行すれば、v9のGit操作にも個人設定が適用される。

v9と同じ環境の読取り診断で、アカウント `koma236`、repository `koma236/FitLog`、
権限ADMIN、実効origin `https://github.com/koma236/FitLog.git`、HTTPSのmain参照取得を確認した。
既定Gitのrewriteを変更せず、個人設定では保存済みHTTPS originに直接接続する。

これはv9の設定であり、通常の `git` / `gh` 全体の設定変更ではない。
Issue・commit・push・PRの個別承認とworkflow前提条件は残る。mergeは本人がGitHubで行う。

## 根拠

- [GitHub CLI environment](https://cli.github.com/manual/gh_help_environment): 設定ディレクトリとtoken環境変数の優先順位。
- [GitHub CLI auth login](https://cli.github.com/manual/gh_auth_login): ブラウザ認証、資格情報ストア、SSH鍵検出の抑止。
- `~/project/ai-dev-harness/scripts/v9/gitops.py`: v9のアカウント確認とrewrite拒否。
