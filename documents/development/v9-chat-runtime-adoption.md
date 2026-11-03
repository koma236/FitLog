# チャット委任対応runtimeの固定登録

## R1 固定する実行版

対象は個人repo `koma236/FitLog`。新規task向けの登録値を次の5項目へ更新する。

| 項目 | 値 |
|---|---|
| schema_version | 1 |
| repository | koma236/FitLog |
| account | koma236 |
| harness_root | /Users/saki/.codex-personal/runtimes/ai-dev-harness-164e77f |
| harness_commit | 164e77f1c6d66c13f70cec2925a0f1f7224b5d1f |

配布元は `koma236/ai-dev-harness` の `fix/v9-chat-runtime`、Issue 14。上記Cは正常v9のcommit・本人の通常TTY送信を経て、remoteの同branchから同一SHAを読み戻した。mainへの統合やFitLogへの採用が済んだという意味ではない。

専用runtimeはCのdetached worktreeとして新設した。Git tree/indexと全248 tracked fileの物理bytes/modeが一致し、bin/scriptsの19ファイルに余分なcacheがなく、固定Python 3.12の実体を確認した。公開approve helpはactorをowner/codex-owner-delegatedの2値に限定する。読取り検査の詳細はowner-only作業記録へ保存し、未実行の採用結果をreceiptへ記録しない。

## R2 承認済み範囲の通常委任

初回に仕様・独立設計レビュー・計画、対象repo/task/worktree/branch/baseline、変更範囲・受入・checks・provider・時間/round上限・Git操作をまとめて本人が承認する。その承認に含まれる実装・検証・独立レビュー・修正・Issue・commit・指定feature branchへの通常送信は再申請せず進める。

Codexは実際の結果、差分、現在binding、残予算を確認して正規TTYの完全一致入力を処理する。4工程のapproveは `--actor codex-owner-delegated` を指定し、保存されたactor/bindingを読み戻す。互換性のあるreceipt kind `human_approved`と実際の入力主体を区別する。actor指定そのものや文書は権限を与えず、委任が確認できない場合と非Codex agentでは本人へ引き渡す。provider/Git確認の入力者が独立保存されない制約は、元承認参照と実際の入力者をowner-only作業記録へ残して区別する。

4工程の順序、実TTY、成功結果、入力後のfresh binding検査、独立provider、予算を維持する。receipt直接編集、未来結果の先行承認、一括パイプ、旧runtimeをowner actorで代行する操作を許可しない。通常委任でautoを選択しない。重大な範囲変更・不可逆操作・予算超過などは個人開発運用に従う。

PR作成は完成したhead/base/title/bodyへの最後の別承認を待つ。mergeは本人がGitHub上で行う。main直接更新、force、auto-merge、hook回避は禁止する。

### 本taskの委任と予算

source外記録の基準directoryは`/Users/saki/.ai-dev-harness/v9/chat-transition/working-records/chat-delegation-20261103/`、sealの正規pathは`/Users/saki/.ai-dev-harness/v9/chat-transition/tool-seal.json`とする。以下の`register-resume-20261103/`参照はこの基準から解決し、欠落・会話参照不一致では権限を推定しない。

Issue案の題名は「FitLogの新規task向け固定runtimeとチャット委任運用を登録」、本文は固定C/pathの登録、R0復旧fixtureの保全、通常委任と新規task向け採用を対象とする。Issue・commit・`fix/v9-chat-runtime-config`への通常送信までを委任範囲とし、PR作成は最後の別判断とする。

設計レビューは従来の4回（4回目は228秒で不合格）を保持する。本人の追加指示「ではレビュー3回まで追加許可します。進めてください」により、同一task/branchで最大3回・各回最大3,600秒を追加し、累計上限を7回とする。承認参照はsource外の`register-resume-20261103/design-extension-three.json`。以後の消費と残枠は正規review-budget台帳と各attempt resultで照合し、合格時点で残枠を使わず終了する。失敗分の返却、別branch/taskでの予算初期化、追加の計画レビューは行わない。再レビューは確認した指摘の修正後だけとし、同じ入力を通るまで繰り返さない。実装開始には正規の有効な設計判定が必要であり、本書の修正を合格結果とみなさない。

実装providerはCodex。正式R0 verifyの実行上限は3,600秒、独立品質は1巡・合計最大3,600秒とし、正式Claude reviewを統合役、反証QAとSecurityを同じ巡の担当に含める。追加の品質巡は未承認。上限到達、失敗または未解決High/Mediumは記録して停止し、通るまで反復しない。本人指示と実入力者の参照はsource外の`register-resume-20261103/authorization.json`、Claudeへの設計情報送信許可は同所の`claude-transfer-authorization.json`へ保存し、元の会話との対応を照合する。これらはreceiptではなく、記録だけを委任権限の代わりにしない。

11 checksの個別timeout合計は3,900秒であり、verify全体の3,600秒を超える。個別checkがtimeout内でも全体上限で終了し得る。全体上限到達と個別check失敗を区別して報告し、timeout値や全体予算を自動延長しない。

## R3 既存作業と採用順序

旧task棚卸しはPR作成判断の前にも実施し、影響を受ける旧PRと起点不明のtaskを両PR本文・最終報告へ記載する。PR本文には作成時点の事実と未確認の統合前確認項目を区別して書く。source統合後にしか得られない方式とC到達性の実確認結果は、その後の本人への報告で伝える。承認済みPR本文の編集やGitHubコメント投稿は今回の委任に含めない。順序違い・C未到達が事後に判明した場合もRoot切替を保留して報告する。AIが本人の統合操作を阻止できるとは扱わない。

Cのproducerと既存hookの不適合が隔離検査で判明した場合は登録PRを止める。Root切替後に不適合が判明した場合は新task開始を止め、Cに束縛されたtaskを保全して報告する。Rootがcleanで他writerとC依存taskがないことを確認できる場合だけ、切替前に記録したR0登録commitとignored skill参照へdetachedで戻す。条件を証明できない場合は状態を変更せず相談する。main ref、旧taskのbinding、receiptを書き換える復旧はしない。

登録対象は `.ai-dev/v9-git-entrypoints.json` と個人開発運用、新規task向け共通skillの参照版。既存worktreeのruntime/link/state/receipt/予算はそのまま残し、自動移行しない。旧R0 `169642d0c8040e24e048ee5f04777345e5242016` とその専用rootは上書きしない。

このREGISTER task自身は最後まで旧R0で仕様・計画・Issue・実checks・独立品質・4receipt・commit・通常送信を処理する。新runtimeで自分自身を承認しない。FitLog root側の既存登録・hookは作業中に変えず、別worktreeに登録変更を置く。作業中にだけ必要な旧R0への確認手段は、別途本人が承認した移行作業の権限に限る。一時入口・旧GATE・失敗記録・診断説明・そのテストを本PRへ持ち込まない。

旧R0の公開approve helpにはactor指定がない。一方、固定R0の`controller.approve_phase`は4 phaseすべてでactorを受け取り、実際に先行RUNTIMEの4 receiptで`codex-owner-delegated`と`human_approved`の保存を読み戻した。REGISTERは別途本人が承認し独立事前検査を終えた移行用確認手順で、同じR0の正規APIへ委任actorを渡す。4工程すべての期待actorは`codex-owner-delegated`、kindは`human_approved`である。入口に対応や委任根拠がなければ代行せず、owner名義へ偽装しない。各工程の実結果・bindingを再照合して次へ進む。この作業権限と期限はsource外の保全済み作業記録で管理し、本書を将来の旧runtime迂回権限にしない。

### 現セッションの送信起点

REGISTER限定の移行例外は、本人承認済みの縮小移行設計に基づき、現行personal-workflowの公開入口限定・未対応時停止の一般規則に優先する。絶対期限は2026-11-04 00:00 UTC（1793750400）。確認入口のSHA256は`e3404c395dbb6d7714c12f27e5bdb31aab9d6cdca2c44b45096a9541ce86549d`、移行controllerは`92724e51f68b7732c7f34f3ac225bfd5de4010d7c8ecd90dacf4f3b65ae17bb9`、固定helperは`e18cc5646f3dcfa7b107376e68acdd8edc38c55a157840f477ccb527542073a6`。owner-onlyの承認参照とsealを実際に照合する。いずれか欠落・期限切れ・bytes不一致なら停止して相談し、actor=ownerへの代替や通常Pythonへの迂回で受入を通さない。

期限切れ時は未完了の工程確認と本移行委任に基づくIssue・commit・送信を停止し、完了済みreceipt/resultは変更せず保全する。完了済みreceiptがあるだけで期限後のcommitや送信を実行せず、再開条件は別途本人判断とする。期限を黙って延長しない。

Sは`/Users/saki/project/FitLog`、HEAD `60582e73771c059840e1b917efbe7f02fca68663`、登録R0のままのrootとする。Pは上記REGISTER worktreeでS≠P。同一cloneである。送信を行うCodex sessionはnative cwd=Sで起動され、読み込まれるhookもSにあることを実確認する。`CLAUDE_PROJECT_DIR`がある場合もSと一致させる。この起点を確認できないsessionでは送信を保留し、shellのworkdir指定やPへのcdだけで条件を満たしたとみなさない。Root切替と旧taskの移行は今回の登録・送信の完了条件に含めない。

Sの両hookと登録JSONがSのHEADのbytesと一致し、登録root/commitがR0であることを送信前に確認する。Sの本task所有の文書草稿は保持できるが、hook/登録を未commit変更した状態では送信しない。Pにある候補C登録をSの登録として使わない。

正常送信はSを起点に次のliteral形を使う。job pathは直前のcontrollerが返したcanonical値だけを使い、改名・手作りをしない。

```sh
AI_DEV_HARNESS_HOME=/Users/saki/.codex-personal/runtimes/ai-dev-harness-169642d /Users/saki/.codex-personal/runtimes/ai-dev-harness-169642d/bin/ai-dev v9 prepare-git --action push --project /Users/saki/project/FitLog/.worktrees/v9-chat-runtime-config --task V9-CHAT-REGISTER --remote origin --branch fix/v9-chat-runtime-config
AI_DEV_HARNESS_HOME=/Users/saki/.codex-personal/runtimes/ai-dev-harness-169642d /Users/saki/.codex-personal/runtimes/ai-dev-harness-169642d/bin/ai-dev v9 git-action CONTROLLER_RETURNED_JOB_PATH --project /Users/saki/project/FitLog/.worktrees/v9-chat-runtime-config
```

4工程の一時確認手順はこの送信runnerではなく、正規送信は既存R0だけで行う。新しいhook例外や送信入口は追加しない。

### 旧復旧laneと残作業の保全

既存の環境差分復旧controllerはR0専用であり、Cを登録した新しいSからは意図的に拒否する。旧復旧作業は、その承認・ticket/resultのsource identityを保つ旧専用S `/Users/saki/.codex-personal/worktrees/5313/FitLog`（commit `f827b9fd3629c6550a60c6d37880fee1a58a785f`、R0登録）から行う。読み込むhookとnative cwdもその旧Sとし、使用前にsource bytes・runtime・元承認連鎖を既存正規入口で照合する。このSのHEAD/登録/link/stateを変えない。Cに対応させるための復旧controller改修や新しい例外は本taskに含めない。

復旧回帰のfixtureが「現在の通常runtime登録」を読む依存を、独立した固定R0実体へ分離する。変更予定は`./scripts/test_v9_git_environment_recovery.py`のCoreFixtureの参照先と、import前の`sys.dont_write_bytecode`有効化によるR0汚染防止だけで、R0のidentity/evidence/拒否条件を弱めず、テストをskip・無効化しない。既存controllerとhook本体は変更しない。hook preflightの通過だけでは旧復旧controllerでの実行可能性を証明しない。repo内の送信回帰fixtureのproducerはR0であり、Cの適合は別の実producer隔離検査を根拠にする。C用の恒久fixture追加は本taskへ拡張しない。

bytecode抑止の負例検査では、-Bを省略する子processだけに`PYTHONPYCACHEPREFIX`を使い捨て領域へ指定し、欠陥があっても実R0へcacheを書かせない。prefix内にR0由来のpycがないことと実R0のcache不在を前後で検査する。実R0にcacheを検出した場合は削除・clean・seal再生成をせず停止し、本人へ報告する。

root切替前に、未送信または未PRの旧v9 taskと、それぞれの実際の起点S、登録版、binding、送信/復旧/PR結果を棚卸しする。workflowは起点session Sを保存しないため、project pathから推定しない。旧Root起点に依存する残作業、起点不明、必要な復旧連鎖の照合不足があれば、登録PRを用意してもrootの切替は保留し、対象を報告する。既に廃案として保存したGATEや統合済みの履歴は、実根拠で区別する。旧taskのworktreeへ新版mainを取り込む場合も、必要な再束縛・再承認を別に満たすまで停止し、旧receiptを新runtimeへ付け替えない。

切替完了まではRootでtrunk同期やREGISTER commitの取込みを行わない。この制限も採用するpersonal-workflowへ明記し、一般的な同期許可より優先させる。Rootのbranch/detached、HEADと登録R0をPR判断前と送信・切替前に読み戻し、意図しない登録変更は停止・報告する。2026-11-03の読取りではRootは`fix/v9-chat-gate`、HEADは上記baselineであり、mainではない。将来mainをcheckoutしていた場合もAIが自動でdetached化せず、R0登録commitの保全が必要な理由と状態を本人へ報告する。

実行対象は V9-CHAT-REGISTER、worktree `/Users/saki/project/FitLog/.worktrees/v9-chat-runtime-config`、branch `fix/v9-chat-runtime-config`、baseline `60582e73771c059840e1b917efbe7f02fca68663`。実装providerはCodex、正式設計・品質providerはClaude。既存project.tomlの11 checksを変更せず、Compose/DB/imageを共通leaseで排他して実行する。review予算を別branchでリセットしない。

2 PRの内容を完成して最後に作成判断を求め、本人がsource→REGISTERの順で統合する。sourceは通常merge commit方式を使う。source統合後はいったん本人への確認結果の報告点とし、`/Users/saki/.local/bin/gh-koma236 pr view <source-PR番号> --repo koma236/ai-dev-harness --json state,headRefOid,mergeCommit`でhead=C・統合済み・統合SHAを読む。同wrapperの`api repos/koma236/ai-dev-harness/git/commits/<統合SHA>`でparentsが2件かつCを含むこと、`api repos/koma236/ai-dev-harness/compare/<統合SHA>...main`でmainへ到達していることを確認する。番号とSHAは実結果だけを使う。この読取りはPR本文の更新ではなく本人への報告に用いる。squash/rebase・C不一致・main未到達ではREGISTER統合を勧めず、Root切替を保留して報告する。Cや登録SHAの変更は黙って行わない。

compareのstatusは`identical`または`ahead`の場合だけ到達確認に合格とする。`behind`・`diverged`・取得失敗は未確認としてRoot切替を保留する。

両PR統合とCI・登録C/pathを実際に読み戻してから、親所有の一時成果物をhash付きで保全し、他の変更を触らず整理する。上記の旧task棚卸しで切替可能と確認し、rootがcleanで他writerがいない場合だけ検証済み登録commitへdetached checkoutし、新規task向けのignored共通skill参照を固定新版へ切り替える。棚卸し未解決ならRootはR0起点として維持する。新規taskは検証済み登録commitを基準に別worktreeとその起点を準備し、当該worktreeのC登録と固定skillを読む。main refを更新しない。実施前に採用完了と記録しない。

切替操作より先に、復帰先となる現在のR0登録commit、Root HEAD/branch/detached、登録JSONのbytes/hash、ignored skillのlink先と実体版をsource外へ記録する。欠落・未commit登録・他writer・未保存変更がある場合は切り替えない。この記録を上記の条件付き復帰で照合する。
