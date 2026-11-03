# FitLog 個人開発運用

この文書はFitLogのユーザー指定を記録する。配布元の一般ルールと衝突する場合、
本書の承認・並列開発・個人環境・Git操作の規則を優先する。品質基準やhooksを弱めない。

## 対象と環境

- 対象は個人リポジトリ `koma236/FitLog`。
- 共通ハーネスの整備用checkoutは `~/project/ai-dev-harness`。実行runtimeとは区別する。
- 本改訂の採用後は `.ai-dev/v9-git-entrypoints.json` に登録した専用runtimeをv9の実行入口とする。本運用の登録commitは `164e77f1c6d66c13f70cec2925a0f1f7224b5d1f`、配置先は `/Users/saki/.codex-personal/runtimes/ai-dev-harness-164e77f`。`AI_DEV_HARNESS_HOME=<登録root> <登録root>/bin/ai-dev v9 ...` を使い、4工程の確認・provider/checks・Git準備/実行でcode版を混在させない。
- 設計レビュー候補を使う場合は、対象root・commit・用途をsource外の実行記録へ明示する。候補を登録済みruntimeやGit送信対応済みとは扱わない。`prepare-git` / `git-action` は登録runtime限定とし、標準checkoutへ暗黙fallbackしない。
- runtime更新はcommitとcodeの一致確認、許可設定のquality-check/Securityレビュー、v9 bindingと承認の再照合を経て採用する。整備用checkoutが進んだだけでは実行版を変更しない。
- runtimeのbyte検査は、個人sessionのPATH・python3・Python関連環境が信頼済みであることを前提とする。hookはinterpreterと継承環境を検証しないため、送信前にpython3の実体pathと版を採用記録へ照合し、不一致なら停止する。環境変数一覧を出力しない。
- worktree/task名はpush/pull/merge/rebaseのgate wordを避ける。正規non-push操作でもpath等にこれらの語があると安全側で拒否される制限がある。
- v9 Git入口の語句を検索やhelpに記述したcommandも安全側で拒否され得る。調査時はこの既知の制限を記録し、送信commandの隠蔽・job改名・間接実行へ迂回しない。
- iTerm2で個人プロジェクトへ移動し `codex-me` で起動する（`CODEX_HOME="$HOME/.codex-personal"`）。認証情報をコピーしない。
- v9のGit操作は `~/.ai-dev-harness/personal-git.toml` から個人gh/Git設定を自動選択する。設定が不正なら停止し、既定設定へ戻らない。通常のgit/gh全体の設定は変更しない。
- 会社用 `~/.codex`、会社リポジトリ、`manabi-backoffice` を含むパスは探索・読取り・変更しない。
- project内の `.codex/` はこのリポジトリの設定であり、会社用 `~/.codex` とは異なる。
- GitHub操作前に実リポジトリ、originの設定値と実効URL、認証アカウントが `koma236` であることを確認する。不一致・未確認なら実行しない。
- アカウントを探すために会社の設定を探索しない。既定のGitHub認証やグローバルGit設定を無断で変更しない。

## 承認（2026-10-31改訂）

ユーザー指示「最初の計画の承認以降は、プッシュまで最低限の承認申請」を現行方針とする。
従来の工程ごと・Git操作ごとの個別申請は下記に置き換える。この方針変更自体を未提示の製品計画の承認とは扱わない。

### 最初の承認

- 仕様・設計・独立設計レビュー結果・実装計画をまとめて提示し、人間の承認を1回得る。
- 対象repo、task、worktree/branch、baseline、変更範囲、受け入れ条件、checks、実装/独立レビューprovider、予算を明示する。
- Issue案と、commit・当該feature branchへの通常pushまでの委任を計画に含める。PR作成は今回の包括委任の対象外とし、内容を完成させて最終報告で確認する。

### 承認後に追加申請せず進めるもの

承認範囲内の文書・実装・テスト・ローカル検証・独立レビュー・指摘修正、Issue作成、branch/worktree準備、commit、当該feature branchへの通常push。
実装と独立レビューのproviderは分ける。共有資源の待機、軽微な実装判断、範囲内の恒久修正では毎回停止しない。
軽微な差異は記録して最終報告にまとめる。品質基準、レビュー予算、checksは省略しない。

計画承認は、承認範囲内のv9工程確認・provider実行・Git proposal確認の正規TTY入力の委任も含む。
各段階の実結果と計画への適合を確認してから進め、将来の実装・レビュー結果を事前に承認済みと記録しない。
対応する入口ではactorを `codex-owner-delegated` とし、本人が都度入力したように偽らない。
receiptの直接生成・編集、パイプによる一括承認、失効した承認の流用は禁止。
これは `auto` 専用モードの無条件選択や、品質・独立レビュー・予算の省略を許可するものではない。

### 再確認するもの

- 目的・受け入れ条件・対象repo・公開範囲の重大な変更、破壊的変更、承認予算の超過。
- データ削除、本番反映、課金、秘密情報の露出など重大または取り消せない影響。
- 他タスクの変更を失う危険、アカウント/送信先不一致、原因不明で安全に進めない障害。
- レビュー上限、壊れた台帳、未終了processの本人確認など、通常の委任で処理できないもの。
- PR作成。内容を完成させて最後に確認する。mergeは人間がGitHubで行う。

相談は調査済みの事実・具体的対応・必要な判断をまとめて1回で提示する。
OS/sandboxの権限確認は別に扱い、書込み先と理由を説明する。品質hookを回避しない。

### v9の実装上の制約

現行v9通常モードには4工程のreceiptと操作別proposal/TTY確認がある。
技術上の入口と、チャットで人間へ毎回再申請する方針を区別する。対応する正規委任手順では上の委任を使う。
入口が委任を表現できない場合、文書だけで対応済みとせず、不足するハーネス対応をまとめて報告する。
4工程の承認入口が委任actorをreceiptへ記録できない場合、AIはその承認入力を代行せず、その工程を停止して本人による確認またはハーネス対応を相談する。
provider実行とGit proposalのTTY確認は4工程の承認receiptと区別する。現行handoff/git-actionには独立actor引数がないため、初回承認で得たcodex-owner-delegated receiptと、その同一workflow/bindingに束縛されたjob/proposalを委任根拠にする。入力主体を人間と記録・報告しない。必要な委任receiptがない実行では通常の本人確認または操作を限定した明示委任を得る。入口の確認・binding検査を省略する許可にはしない。
必須receiptの捏造や、通常Git/別provider直接実行への迂回は禁止。共有ハーネスの改修は別taskとして設計・検証する。

### 固定新版の採用と旧作業の保全

新規taskでは現在worktreeの固定登録と[採用契約](v9-chat-runtime-adoption.md)を読み、対応する公開approveのactorを使う。採用後の通常4工程は`--actor codex-owner-delegated`とし、実結果と保存actor/bindingを確認する。旧worktreeのruntime/link/state/receiptは自動移行しない。

旧R0 taskの未送信・未PR状態と実際の起点Sを棚卸しする。Root起点が残る、起点が不明、復旧証拠をまだ確認できない場合はRootのCへの切替を保留して報告する。旧worktreeへ新版mainを取り込む場合も、必要な再束縛・再承認を済ませるまで停止する。新規taskは検証済み登録commitを基準とする別worktreeと起点を使う。

切替完了まではRootでtrunk同期やREGISTER commitの取込みをしない。この制限は通常の同期許可より優先する。Rootのbranch/detached、HEADとR0登録をPR判断前・送信前・切替前に実読し、意図しない登録変更は停止して報告する。mainをcheckoutしていた場合も自動でdetached化せず、R0保全方法を本人判断へ含める。切替前には復帰先のR0登録commit、HEAD/branch、登録JSONのbytes/hash、ignored skillのlink先と実体版をsource外へ記録する。起点不明・未保存変更・他writerがあれば切り替えない。

共通skillが未配置なら、そのworktreeの登録runtime内の`skills/ai-dev-chat/SKILL.md`を読む。整備用checkoutを参照する過去のsetup記録より本書の固定版を優先する。Rootのignoredリンク切替は、両PRの本人統合・CI・C到達性・Root cleanと上記棚卸しを確認した後だけに行う。

## Git・GitHub

- 原則は1 Issue = 1作業ブランチ = 1 PR。Issue番号を捏造しない。
- v9では仕様/計画のreceiptがIssue作成に先行するため、初期設計はlocal task IDの準備branchで行える。実Issueとbranchの対応を記録し、branch名変更時も正規binding更新・必要な再検証を行う。
- Issue作成後もそのtaskの準備branchを継続できる。Issue URL・task ID・branchの対応を記録し、番号を付けるだけの改名やworkflowの作り直しはしない。
- 計画に含めたIssue作成、commit、当該feature branchへの通常pushは承認後の委任範囲。対象repo・個人アカウント・実効remote・SHA・送信先を毎回検証する。
- `prepare-git` のproposalと正規 `git-action` を使う。正規委任の範囲でTTY確認を処理し、receiptを直接生成・編集しない。
- Issueには仕様・計画の承認receipt、commit以降には4段階の承認receiptなど、v9が要求する前提を満たす。満たせない場合は未完了として報告し、別経路で迂回しない。
- **mergeは人間がGitHub上で行う。AIによるmerge・auto-merge有効化は禁止。**
- main/masterへの直接変更・push、force push、履歴の書き換え、hook無効化や回避は禁止。
- 別タスクの変更を同じcommit/proposalへ混在させない。上流にあるAI mergeの許可はFitLogには適用しない。
- 配布元のDevelopment Philosophy/Design Confirmation Rulesの「PRとmergeまで包括承認」、Critical Rules Level 0のIssue自動作成やmerge許可、Autonomy PrinciplesのAI mergeに繋がる記述は本書で置換する。配布元本文は更新互換性のため保持するが、PR最終確認・人間merge・正規v9ゲートの規則を優先し、両方を同時適用しない。
- URL rewriteなどでv9の検証が停止した場合、停止理由を解消する。ハーネスの検査を無効化しない。

## 並列開発

詳細は [並列開発運用](personal-parallel-workflow.md) を正とし、配布worktree skillより優先する。
独立したIssueごとにworktree・branch・仕様/計画・v9 task/workflowを分離する。
1 worktreeの書込み担当は1セッション。他タスクのHEAD/index/未保存ファイルを操作しない。
Codex管理の既存worktreeも使用でき、配置を揃えるだけの移動・作り直しはしない。
編集は並列で進め、現在の固定Compose・DB・imageを使う操作は排他で直列実行する。

## 技術スタックと検証

- React/TypeScript/Vite/Vitest、Python/Django/PostgreSQLを既存Docker環境で実行する。ローカルの実コマンドは `.ai-dev/project.toml` の11チェックを正本とする。
- GitHub Actionsでbuild/lint/型/全テスト/migrationを実行する。backend/frontend両jobの成功だけをci-requiredの成功とし、main rulesetによりPR経由・最新main・Actions由来の必須チェックを要求する。
- 独立レビュー・mutation・目視確認などはハーネス側へ残し、CIの合否判定にLLMを使わない。CI方針は2026-10-31ユーザー指示を優先し、古い「CIはビルドのみ」の配布元説明を適用しない。
- CI実装PRの実runが成功してcheck名を登録できた後、main rulesetを適用してreadbackする。未適用の時点で保護済みと報告しない。mergeは人間のみ。
- テスト失敗を同一SHAのrerunでgreenへ寄せない。logで外部インフラ障害と特定できた場合だけ手動1回のrerunと理由/runリンクを記録する。既知flakeが残る場合は必須化を保留し、workflowだけのmergeと次機能の着手もユーザー判断とする。
- CI相当のローカル試験は別Compose project・別image tag・job内volumeを使う。fitlog-devのcontainer/volume metadataとimage IDを前後比較し、共有bindやpruneを使わない。
- 未設定・未実行・失敗を成功扱いしない。ローカル確認・独立レビュー・実GitHubrun・ruleset readback・merge後確認の証跡を区別する。
- hooksの配置、登録、信頼、実行確認を区別し、未確認の信頼を捏造しない。品質ゲートとレビュー予算を維持する。

- 上記のCI方針は `skills/project/quality-check/SKILL.md` の配布元記述「CIはビルド確認のみ」にも優先する。同skillの品質ゲート・独立レビュー・予算等の他要件は維持する。

## 共通skill

`skills/ai-dev-chat/SKILL.md` を必要時に読む。未配置または整備用checkoutを参照するリンクの場合は、現在worktreeの `.ai-dev/v9-git-entrypoints.json` に固定されたruntime内の同pathを読む。
`.claude/skills`、`.codex/skills`、`.agents/skills` は同じ `skills/` を参照する。
新しいセッションでのskill一覧掲載・実読込みを確認する。現セッションに自動反映したとは扱わない。

技術上の入口は採用済みruntimeの `documents/v9/workflow-policy.md` と
`skills/ai-dev-chat/SKILL.md` を参照する。整備用checkoutの文書は更新案の確認用であり、採用版の正本と混同しない。承認のユーザー方針は本書を優先する。
過去ポリシーは現行承認の根拠にしない。

## 正規のGit環境復旧のエラー

`V9_ENV_RECOVERY` は、承認されたGit環境復旧controllerの固定診断コード。設定差分・元承認連鎖・path/権限・起動環境・期限・未解決intent・送信結果等を証明できない場合に拒否する。入力値、config本文、credential値を診断へ含めない。旧v9の成功resultやreceiptを編集して解消せず、詳細は本taskの承認済み設計とsource外reportを参照する。未実装・未実行を成功扱いしない。

## 承認済みcommitの環境差分復旧

本節は旧R0専用の復旧手順であり、C登録の新しいRootからは意図的に拒否される。固定旧Sは`/Users/saki/.codex-personal/worktrees/5313/FitLog`、commit `f827b9fd3629c6550a60c6d37880fee1a58a785f`、登録runtimeは旧R0 `169642d0c8040e24e048ee5f04777345e5242016`。native cwdと読み込むhookもこのSを起点とし、元source/承認連鎖を既存正規入口で確認する。このSの登録・HEAD・link・stateは変更しない。新登録へ対応させるため復旧controllerやhookを拡張しない。

hook preflightの受理だけでは旧復旧controllerで実行可能とは限らない。controllerはR0の固定登録を別に検査する。repo内の送信回帰fixtureのproducerもR0であり、現行Cの適合証拠とは区別する。Cは実producer・CLI parser・hook両形の隔離検査と実rootの読取り検査で照合する。

通常v9のGit設定fingerprintが変わった場合、設定を一時的に戻したり元receipt/resultを編集して通さない。
今回承認する例外は、共有configの唯一のmain節に編集用metadataの完全な1行が追加された場合だけ。
旧hash `6bd06089…` と承認対象の新hash `42fa0496…` の組を固定し、追加の設定変更では停止する。
固定した契約は [復旧設計](../../docs/git-environment-recovery-design.md) を参照する。

復旧taskのcommit済みworktreeをS、同じcloneの対象feature worktreeをPとする。
Sの正規入口 `S/bin/ai-dev-git-env-recovery` のprepare/execute/status/prepare-prだけを使う。
Python直接実行、別runtime、wrapper、任意env指定、別clone、P=Sは使用しない。
通常v9の入口と元runtimeは維持し、復旧task自身の送信には通常v9を使う。

prepareは15分有効のprivate ticketを作り、executeは表示したSHAと環境差分を正規TTYで再確認する。
16桁prefixの完全一致が必要で、承認待ち中にHEAD/config/state/remoteが変われば実行しない。
送信元は元承認commitのSHAに固定する。公開済み同SHAは観測のみと記録し、実送信と区別する。
通常v9の成功resultを代わりに生成せず、元ledger内の別namespaceにticket/intent/worker/resultを追記する。
running/unknown/未解決intentでは自動再試行しない。解決操作は実装範囲外であり、X7として判断を求める。

PR準備は成功した送信連鎖・現在のremote SHA・本文hashを再照合する。PR作成は最後の個別承認、mergeは本人のみ。
HOME/CODEX_HOMEや危険な環境変数名を検知した場合、AIがunsetして続行せず専用個人環境の起動方法を確認する。
OSが既に除去した環境変数名を検知できるとは主張しない。固定Python leafのhashは実体の取り違え検査であり、
framework dylib/stdlib全体の同一性を保証しない。OS/Pythonインストールはホスト側の信頼前提である。

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
