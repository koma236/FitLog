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
- Issue/PR作成は毎回、対象と具体的内容を示して個別承認を得る。commitは2026-10-30のユーザー指示「これ以降コミットの個別承認も不要です」により個別確認を省く。commit/pushとも正規v9 proposal・個人環境検証・対話操作の記録は維持する。
- featureブランチのpushは、2026-10-30のユーザー指示「これ以降pushには個別承認不要です」により個別確認を省く。対象repo・個人アカウント・送信先・commitの検証と正規v9操作は維持する。main/masterへの直接push、force、mergeの許可にはしない。
- v9では `prepare-git` のproposalを使い、正規の `git-action` を実行する。commitとfeature pushは上記の委任範囲で進め、Issue/PRは個別承認を得る。承認節の例外条件（具体的内容の個別承認と通常TTY入力の明示委任）を満たす範囲に限り、同節の正規対話手順で要求文字列を入力できる。receiptを直接生成・編集しない。
- Issueには仕様・計画の承認receipt、commit以降には4段階の承認receiptなど、v9が要求する前提を満たす。満たせない場合は未完了として報告し、別経路で迂回しない。
- **mergeは人間がGitHub上で行う。AIによるmerge・auto-merge有効化は禁止。**
- main/masterへの直接変更・push、force push、履歴の書き換え、hook無効化や回避は禁止。
- 上流にある自動Issue作成、設計承認によるGit操作の包括許可、検証や正規v9操作を省くfeature push、AIによるmergeの記述はFitLogには適用しない。
- URL rewriteなどでv9の検証が停止した場合、停止理由を解消する。ハーネスの検査を無効化しない。

## 技術スタックと検証

- React/TypeScript/Vite/Vitest、Python/Django/PostgreSQLを既存Docker環境で実行する。ローカルの実コマンドは `.ai-dev/project.toml` の11チェックを正本とする。
- GitHub Actionsでbuild/lint/型/全テスト/migrationを実行する。backend/frontend両jobの成功だけをci-requiredの成功とし、main rulesetによりPR経由・最新main・Actions由来の必須チェックを要求する。
- 独立レビュー・mutation・目視確認などはハーネス側へ残し、CIの合否判定にLLMを使わない。CI方針は2026-10-31ユーザー指示を優先し、古い「CIはビルドのみ」の配布元説明を適用しない。
- CI実装PRの実runが成功してcheck名を登録できた後、main rulesetを適用してreadbackする。未適用の時点で保護済みと報告しない。mergeは人間のみ。
- テスト失敗を同一SHAのrerunでgreenへ寄せない。logで外部インフラ障害と特定できた場合だけ手動1回のrerunと理由/runリンクを記録する。既知flakeが残る場合は必須化を保留し、workflowだけのmergeと次機能の着手もユーザー判断とする。
- CI相当のローカル試験は別Compose project・別image tag・job内volumeを使う。fitlog-devのcontainer/volume metadataとimage IDを前後比較し、共有bindやpruneを使わない。
- 未設定・未実行・失敗を成功扱いしない。ローカル確認・独立レビュー・実GitHubrun・ruleset readback・merge後確認の証跡を区別する。
- hooksの配置、登録、信頼、実行確認を区別し、未確認の信頼を捏造しない。品質ゲートとレビュー予算を維持する。

## 共通skill

`skills/ai-dev-chat/SKILL.md` を必要時に読む。
`.claude/skills`、`.codex/skills`、`.agents/skills` は同じ `skills/` を参照する。
新しいセッションでのskill一覧掲載・実読込みを確認する。現セッションに自動反映したとは扱わない。

正本は `~/project/ai-dev-harness/documents/v9/workflow-policy.md` の現行節と
`~/project/ai-dev-harness/skills/ai-dev-chat/SKILL.md`。過去ポリシーは現行承認の根拠にしない。

## CI相当のローカル再現

workflowのbuildコマンドをそのままローカルへコピーすると、Compose project名を変えてもfitlog-devのimage tagを上書きする。必ず別image tagのoverrideを使う。以下はrepoルートの個人用ターミナルで使う例。Dockerが利用可能な環境で実行する。

```sh
export FITLOG_CI_LOCAL_PROJECT="fitlog-ci-$(date +%Y%m%d%H%M%S)-$$"
FITLOG_CI_LOCAL_DIR=$(mktemp -d)
cat > "$FITLOG_CI_LOCAL_DIR/compose.yaml" <<'YAML'
services:
  backend:
    image: ${FITLOG_CI_LOCAL_PROJECT:?}-backend
  frontend:
    image: ${FITLOG_CI_LOCAL_PROJECT:?}-frontend
YAML
ci_compose() {
  docker compose --project-name "$FITLOG_CI_LOCAL_PROJECT" -f compose.yaml -f "$FITLOG_CI_LOCAL_DIR/compose.yaml" "$@"
}
ci_compose config
# 解決結果が下記の分離条件を満たすことを確認してから続行する。
ci_compose build backend frontend
ci_compose up --detach --wait postgres
ci_compose run --rm --no-deps backend uv run --frozen --no-sync python manage.py migrate --noinput
ci_compose run --rm --no-deps backend uv run --frozen --no-sync pytest -q
docker build --file .github/ci/Dockerfile --build-arg "FRONTEND_IMAGE=$FITLOG_CI_LOCAL_PROJECT-frontend" --tag "$FITLOG_CI_LOCAL_PROJECT-tools" .
docker run --rm "$FITLOG_CI_LOCAL_PROJECT-tools" node /ci/test-workflow.cjs
# 残りのlint/型/build等もproject.tomlのコマンド本体をci_compose経由で実行する。
# 全試験の終了後、自分のprojectだけを停止・削除する。
ci_compose down --volumes --remove-orphans
```

事前にcontainer_name、external resource、共有host bind、他projectのvolume名が無いことを実際の解決結果で確認する。backend/frontendはrun --no-depsを使い、upや--service-portsで開発ポートを公開しない。既存fitlog-devのcontainer/volume metadataとimage IDを実行前後で比較する。分離できない定義へ変わっていた場合は実行・cleanupを止め、既存resourceを変更しない。

CI設定/検査script/テストを変えるPRは、ci-requiredのgreenだけでmergeせず本人が差分を確認する。設定検査器は回帰ガードであり、PR側でworkflowと同時改変される場合のセキュリティ境界ではない。導入時はfork workflow承認設定とwrite権限者も読み取り、意図しない設定変更はしない。
