# v9 初回開発の順序修正：改訂設計 v3

状態：Claude第2回は初回Highの解消を確認し、Medium 2 / Low 3で不承認。本書はその5件を反映した設計承認用の改訂案であり、独立レビュー合格済みとは扱わない。実装・第3回レビューは未実施。本書は承認receiptではない。第1・2回に渡したコピーは履歴として保持する。

## 1. 対象と互換性の決定

CLI名は`ai-dev v9`のまま、workflow state・新しい実行job・Git proposal/result・planは**schema_version=10**にする。manifestは9、project.tomlは1を維持する。schema番号は各データ形式の版であり、製品名の変更ではない。

旧stateは専用のschema 9 validatorで読み取り・表示できる。新工程の実行はschema 10だけが受け付ける。旧jobは新実行入口で明示的に拒否し、再準備を案内する。旧runtimeはschema 10を拒否する。schema 1の既存review経路は変更しない。

**既存承認の維持は保証しない。** runtime/policy変更により仕様承認以降は失効する。既存利用者にも設計レビュー、仕様・計画の再承認、現在のsnapshotに対する実チェックと品質レビュー、結果の再承認が必要になる。旧レビューを新しい設計レビューに転用しない。維持する互換性は、旧データの参照・履歴保全と、移行後に通常開発を実施できることである。

`migrate-workflow`は対象task、旧stateのdigest、失効する承認、未解決attemptを表示し、通常terminalで本人が確認する。確認後に旧JSONをprivate領域へ変更不能なバックアップとして保存し、新stateをrevision比較付きで原子的に置換する。失敗時は旧stateを残す。既存proposalは再利用しない。AIが移行確認を代行しない。

旧attemptは消さず、id/phase/status/消費時間/ラウンドを保存する。新しい入力bindingや検証証拠を推定で埋めない。移行済み旧attemptは`origin_schema=9`、新しいbinding/evidenceはnullとし、どの承認の根拠にもならない。旧receiptはバックアップで保持し、新stateの4承認はnull。review-budgetの台帳は移行・初期化しない。既存の実行中processがあれば移行しない。停止確認後に残っていたrunningをunknownとして移し、§7の本人確認による解消を要求する。

## 2. リポジトリとtaskの前提

Git root、存在するHEAD、main/master以外の名前付きbranchを要求する。HEADがない場合は、初期化・bootstrap・Git proposalの前に`V9_BASELINE_REQUIRED`で停止する。root commit対応は今回の範囲外。基準commitの作成は既存のGit個別承認手順で別途行い、AIが自動生成しない。

FitLogにはHEAD `03f1b69ffcbacdaf6eab69722e6c473d09a99ad0`、ハーネスにはHEAD `a35f6f8e9b8c862dfafa1dbe9a01c8570d41abe3`が存在することを確認済み。これらは今後の実行時にも再確認する。

初回基盤は独立task T0とし、planの`kind=bootstrap`をworkflow作成時に固定する。他taskを途中でbootstrapへ変えられない。後続機能taskはT0の実チェック・品質レビュー・4承認の完了後に始める。同じbranch/planでのdepends_onは従来どおりGit-readyを要求。別Issue/branchではT0のPRを本人が統合した基準commitから、別manifest/planを承認する。異なるbranchの依存検査を緩めない。

## 3. state・attempt・承認の形式

schema 10 stateのキーは`schema_version, revision, binding, approvals, attempts, resolutions, legacy_archive`。未知キーを拒否する。bindingは従来の12項目に`task_kind, design_binding_digest`を追加し、project/branch/task/task_kindは不変。design_binding_digestは§4の正規化済みdesign_bindingから毎回再計算する。approvalsは従来のspecification/plan/implementation/reviewの4種類だけ。

新attemptの共通キーは従来のid/phase/input_snapshot/status/max_rounds/max_seconds/rounds_used/seconds_used/output_snapshot/error_categoryに、`origin_schema, input_binding, result_binding, evidence, admission`を追加する。origin_schema=10の入力bindingは予約時に固定。結果がない間はresult_binding/evidence=null。成功時はphase固有の証拠を必須とする。移行されたorigin_schema=9は前節の制限付きで保持する。

statusは`pending/running/succeeded/paused_quota/failed/unknown/abandoned`。最後のabandonedは§7の正規解消だけが設定できる。`awaiting_checks`というattempt statusは追加しない。「チェック登録待ち」は成功bootstrapはあるが実チェック成功はない、という状態から算出する表示名。

| phase | 予約に必要な条件 | 成功時のsnapshot更新 | 承認に使える証拠 |
|---|---|---|---|
| design_review | 構造・source hashが有効。checks空とblocking questionありの草案は可。独立reviewer | 更新しない。開始前後の全体snapshot一致必須 | specificationの前提となるdesign verdictだけ |
| bootstrap | task_kind=bootstrap、仕様・計画の人間承認、有効なdesign結果 | 範囲検査済み出力へ更新 | generation証拠のみ。implementation承認不可 |
| verify | 仕様・計画の人間承認、実checksあり、独立design有効 | 変更なし。入力と検証後の一致必須 | checks証拠。implementation承認可 |
| implementation | task_kind=standard、仕様・計画の人間承認、実checksあり | provider出力を実checksで検証後に更新 | checks証拠。implementation承認可 |
| review | 現在のimplementation承認、別provider、実checks設定が承認時と一致 | 変更なし | quality証拠。review承認可 |

verifyはproviderを起動せず、同じ実行予算の下で承認済みcheck runnerを使う。通常taskも修正後の同じsnapshotを再検証するためverifyを使えるが、設計・計画承認は省けない。bootstrap taskは通常implementation/autoへ進めず、bootstrap→verifyを使う。

成功時のresult_bindingは予約時input_bindingを元に、bootstrap/implementationだけsnapshot_hashを検証済み出力へ置き換えたもの。verify/reviewはinput_bindingと同一とする。phaseと無関係なconfig/route/runtime変更を結果へ吸収しない。check開始前・完了後に実設定をディスクから再解決して照合し、providerが変更した未承認のcheckを実行・成功扱いしない。

phase別evidenceは以下の完全一致スキーマで検証する。

- design_review：`kind=design, design_binding, verdict`。verdictは§5。
- bootstrap：`kind=generation, allowed_paths_digest, changed_paths_digest, proposed_checks_digest`。checks_passedという項目を持たない。
- verify/implementation：`kind=checks, checks_digest, results, verified_snapshot`。resultsはcheck idごとのexit_code・elapsed_ms・判定を持つ非空配列。設定中のcheck全件と一対一に対応し、全件成功だけを承認候補とする。本文・環境値は保存しない。
- review：`kind=quality, quality_status, verified_snapshot, implementation_attempt_id`。対象の実装検証attemptを明示する。

implementation承認の判定は、現在のbindingに合う**最新の検証候補attempt**（phaseがverifyまたはimplementation）のstatus=succeeded、origin_schema=10、kind=checks、全checkの成功、verified_snapshot一致を必要とする。後発の失敗・未知・未完了の検証を飛ばして過去の成功を拾わない。生成・修正・設定変更の後はそれより後の検証が必要。bootstrap/design_review/legacyは常に除外する。

review承認は現在の実装承認が指すattemptと現在のsnapshotに対する最新quality attemptだけを受け付ける。`_has_success`のphase名＋snapshotだけの判定を廃止し、controllerと低水準approve、Git-ready判定で同じ証拠検証関数を使う。固定のchecks_passed=Trueを成功根拠として生成しない。receiptのevidenceに検証済みattempt idを記録する。

## 4. 設計レビューのbindingと失効

design_bindingのキーを`project, branch, task, task_kind, spec_hash, plan_hash, source_hashes, baseline_commit, policy_digest, runtime_digest, design_route_digest`とする。source_hashesはvalidate_spec済みmanifest sourceのid/path/sha256をソートした配列。全体snapshot、config_digest、checks_digest、通常のroute_digestは含めない。

controllerの入力解決は毎回、ディスク上のmanifest/source/plan・モデル表・runtimeを検証し、design_bindingをcanonical JSONにしてSHA256を計算し、candidate binding.design_binding_digestへ設定する。保存済みreceiptの値を現在値として流用しない。全操作の入口と本人確認後の再検査で同じ処理を使う。Git prepare/executeもこの共通syncを呼び、古いstateを読むだけでGit-readyと判断しない。sourceとmanifestのhashが不一致なら入力エラーで停止し、承認を有効と報告しない。

schema 10のupdate_bindingは次の順で最初の変更group以降を失効させる。active attempt中の更新拒否を維持し、変更された入力を持つ実行は失敗・解消後にsyncする。

| group | 対象項目 | 失効 |
|---|---|---|
| identity | project, branch, task, task_kind | 変更不可 |
| specification | spec_hash, **plan_hash**, policy_digest, runtime_digest, **design_binding_digest** | 仕様・計画・実装結果・review結果 |
| plan | config_digest, scope_digest, route_digest, checks_digest | 計画・実装結果・review結果 |
| implementation | snapshot_hash | 実装結果・review結果 |

仕様receiptのbinding項目は`project, branch, task, task_kind, spec_hash, plan_hash, policy_digest, runtime_digest, design_binding_digest`。計画receiptはこれにconfig/scope/route/checksの各digestを追加し、実装・review receiptはbinding全項目を使う。validate_stateは純粋な保存値の整合性検査として、receiptのbindingとstate bindingの一致、およびevidenceのdesign_binding_digestとの一致を確認する。現在のディスクとの差は必ずcontroller共通syncで検出する。plan_hashを計画groupへ残さない。

既存コードの設計上の前提はplanのbaseline_commitのツリーを参照する。初期化時にHEADとの一致を確認して固定する。未コミットのコードを前提にする場合は、必要な契約を設計sourceへ明記・固定する。レビュー開始時に対象sourceと現在の全体snapshotを検査し、前後にsource/plan/spec/branch/runtime変更があれば失敗。設計レビューが承認するのは固定した設計と基準コードであり、生成後コードの正しさは実チェックと品質レビューで判断する。

仕様承認時は現在のdesign_bindingが成功レビューの値と一致することを要求する。仕様承認receiptのevidenceを`spec_ready, design_attempt_id, design_binding_digest`とし、その参照先を検証する。plan_hash/source/spec/baseline/runtime/policy/design routeが変われば設計結果と仕様以降が失効する。baseline_commitはこのworkflow中に暗黙更新しない。HEADの外部更新は拒否して新しい基準への計画改訂を要求するが、同じworkflowで別途承認・記録したcommitは既存Git receiptの連鎖で認識する。working treeの生成や当該commitでbaselineを変更しない。

初回のplanには予定checksをあらかじめ固定する。生成後に変えるのはproject.tomlの実checks登録だけで、planファイルは変更しない。この場合config/checks/scope digestにより**計画以降だけ失効**し、仕様承認と設計結果は維持される。コマンド自体を変える場合はplan改訂なので再レビュー・仕様再承認が必要。checks部分だけのplan改訂を特別扱いしない。

「レビュー未実施」「コマンド未作成」など工程の状態をmanifestのblocking questionに置かない。工程の前提はstateの条件で管理する。製品要件の未解決だけをquestionに置く。レビュー完了をquestionへ書き戻してspec_hashを変え、同じレビューを無効にする循環を避ける。

## 5. verdict・モデル・review-budget

設計verdictは`approved: boolean, summary: string, findings: [{severity: High|Medium|Low, location: string, problem: string, recommendation: string}]`。未知キー・不正型・重要度不明を拒否する。approved=falseまたはHigh/Mediumが1件以上なら不合格。Lowのみの場合はapprovedの値を尊重する。矛盾したapproved=trueも合格に補正しない。制御文字・極端な長さは拒否し、UTF-8全体サイズを64KiB以下にする。

構造化verdictは同じprivate stateに保存し、人間向け`show-review`で再取得可能にする。providerの生レスポンス、prompt、source本文、環境値は保存しない。verdictに秘密を書かないよう依頼し、private保存を非機密性の保証とは扱わない。これにより今回のように件数だけ残って指摘本文を失う問題も防ぐ。

モデルの選択元は、Claudeがharness-runtimeの「設計・計画の文書レビュー」行、Codexが`.codex/agents/helm-doc-reviewer.toml`と同文書の「設計・計画の文書レビュー」行の一致検査。専用`load_design_route`を追加する。既存load_model_routesのimplement/review/standardと通常route_digestは変えない。設計routeのdigestはdesign_bindingにだけ追加するが、変更時は§4により仕様以降の承認が失効する。providerは実装担当とは異なるものを必須とする。

実行主体はcontroller。prepare-run design_reviewは予算を消費せずpendingを作る。本人がhandoffを確認し、再検証を終えた直後、provider起動前に `node .claude/hooks/review-budget.cjs begin --phase design --roles document-reviewer`（Codexのみなら既存の選択規則に従う）を実行する。自動extendは禁止。

新v9のdesign_reviewは、そのtask設計に対するbrainstormingのDesign Gateの独立レビューを**兼ねる**。chat側は別のbegin・別reviewerを先に起動しない。同一branchの既存design予算をそのまま利用し、移行前や手動のレビューが枠を消費済みなら通常の上限確認に従う。別台帳を作ったり予算を初期化したりしない。同じ設計をv9とskillで二重レビューしないことをai-dev-chatと運用文書へ明記する。人間による設計・仕様承認は引き続き必要。

予約のmarkerを実際のreview promptの**1行目**に置く。専用Node bridgeから既存exportのcheckReviewを呼び、実際の委譲id・document-reviewer名・同じpromptを渡して座席を消費する。beginだけで許可済みとみなさない。台帳を直接編集せず既存APIを使う。bridgeの返却はreview=trueかつallowed=trueを必須とし、未知ロール・再使用・別branch・不明な台帳は拒否する。この連携は新v9のみの追加であり、今回使った旧review wrapperの挙動を変えない。

attemptは本人確認後runningを保存してから予約する。予約失敗はfailed/budget_denied、座席拒否はfailed/admission_denied、provider起動回数0。予約後の起動失敗でも予算は返却しない。途中で止まればunknownとし、同じmarkerを再使用しない。本人確認前の取消はpendingのまま、予算未消費。reserve/consume成功からprovider開始までのprocess停止も§7で解消し、次のレビューには新しい正規予約が必要。

## 6. 初回生成から実チェックまで

plan schema 10のトップレベルは`schema_version, baseline_commit, tasks`。既存task項目に`kind`と、bootstrapだけ必須の`planned_checks`を加える。standardにはplanned_checksを許可しない。各planned_checkは`id, argv, cwd, timeout_seconds, env, purpose, definition_paths`を持つ。cwdはproject相対で、生成前には未存在でもよい。実行時には存在するproject内ディレクトリであることを再検査する。環境変数・パスは既存の許可規則に従う。

bootstrapは承認済みtask.pathsに限って基盤ファイルと`.ai-dev/checks.proposed.toml`を作る。manifest/source/plan、project.toml、Git管理情報、hooks、承認stateは生成者が変更できない。pathsにこれらを含めた計画は拒否する（提案checksファイルだけは明示許可）。前後のGit-visible path/hash一覧を比較し、範囲外の追加・削除・変更はfailed/scope_violation。外部変更の完全なOS隔離を保証する仕様にはしない。禁止変更を検出したら成果物は自動破棄せず停止する。

provider終了コード0、範囲内変更、提案checksの実行項目がplanと一致、definition_pathsが実ファイルとして存在、manifest等が不変の場合のみbootstrap succeeded。run_declared_checksはまだ呼ばずkind=generationを保存する。現行implementation adapterからの流用で自動的にchecks付き成功にしない。表示は「生成済み・実チェック未実施」。

次に`configure-checks`を本人の通常terminalで実行する。planの予定値、生成された定義、実設定への差分、対象task・snapshotを表示して確認する。本人確認前後で入力を再検査する。設定対象はproject.tomlのroot checksだけ（project id、scopesと他の制約は保持）。シェル評価せずargvとして扱い、予定値と異なる任意コマンドを実行しない。登録後にconfigを再解決し、binding更新による計画・実装・reviewの失効を記録する。

初回T0の設定対象を曖昧にしないため、初期configはchecks=[]/scopes=[]を要件とする。予定チェックはrootのchecksとして登録し、各cwdでbackend/frontend等を指定する。configure-checksはroot checksだけを更新し、scopes=[]と他の設定を保持する。scopeを追加する運用は初回T0の範囲外で、後続の設定変更計画で扱う。

再実行時は、同一の登録済み内容なら何も再承認扱いにせず現在状態を表示する。設定保存後・state更新前に中断した場合も、次の通常syncが新digestを検出して計画以降を失効させる。旧計画が有効なままverifyを起動できない。

本人によるplan再承認の後にverifyをprepare/handoffする。bootstrap由来なら最新のgeneration evidenceと生成後の変更範囲を確認する。bootstrap出力以降に許す変更はconfigure-checksによるproject.tomlだけ。別の修正があれば、新snapshotで計画を再承認してbootstrapを修正実行し、新generation evidenceを得る。初回後の修正bootstrapはchecksが登録済みでも許可するが、結果の実装承認には必ず新verifyが必要。

```text
草案 → design_review → 仕様承認 → 計画承認（checks未登録）
    → Issue内容の個別承認・Issue作成 → bootstrap
    → configure-checks → 計画失効
    → 計画再承認（実checks） → verify → 実装結果承認
    → quality review → review結果承認 → commit/push/PRを各個別承認
```

この通常経路ではspec_hash/plan_hashを変更せず、設計レビュー・仕様承認へ戻る循環はない。autoはbootstrapを拒否。standardのautoは人間の仕様/計画承認と実checks必須を維持する。

### 6.1 計画再承認と作成済みIssueの照合

Issueは最初の仕様・計画承認の後、bootstrap実装の前に1件だけ作成する。本人がIssue内容を承認する順序を変えず、2件目を作る回避策は使わない。reviewer提案(a)を採り、**schema 10のbootstrap taskに限って**作成済みIssueの照合に安定したスコープ識別子を加える。

Issue proposalのapproval_digest（仕様・計画receipt全体）は保持する。未実行proposalには現在のworkflow revision・binding・approval_digestの完全一致を引き続き要求し、計画再承認前のproposalをそのまま実行することはできない。

追加のissue_scope_digestは`project, branch, task, task_kind, spec_hash, plan_hash, design_binding_digest, policy_digest, runtime_digest, route_digest`のcanonical JSONのSHA256とする。初回planned_checksはplan_hashに含まれる。config/checks/scope digestとsnapshotは含めない。proposal作成時に記録し、成功結果も同じproposal_digestに結び付ける。resultから元proposalを読み、値を再計算して一致を検証する。旧schema 9の結果に後からこの値を付け足さない。

bootstrapのIssue proposalにはissue_scope_digestに加え、解決済み設定の`schema_version, project, constraints, scopes`だけから作るconfig_base_digestを保存する。checksに依存するdiagnostics/execution_ready/config_digestはこのbase計算から除く。commit準備時は現在値から同じbaseを再計算して照合する。これらの追加項目はschema 10のbootstrap Issue用validatorで必須にし、通常Issueには暗黙補完しない。

commitが作成済みIssue結果を採用できる条件は、schema 10の成功結果と元proposalが整合し、project/task/branch、現在のissue_scope_digest、repository/account、remote設定、personal environmentが一致し、現在の仕様・計画の人間承認が有効であること。bootstrapではさらに現在の実checksの正規化済みid/argv/cwd/timeout/envが承認済みplanned_checksと全件一致し、scopes=[]、生成証拠とconfigure後の実verifyが有効であることを要求する。proposal作成時のconfigのうちchecks以外が変わっていれば拒否する。

ここだけで旧Issueのapproval_digestと現在receiptの一致を必須にしないため、予定どおりのchecks登録に伴う計画再承認後も同じIssueを使える。**Issueを作った事実だけを維持する変更**であり、古い計画receipt・実装検証・品質承認の再利用ではない。commitの4段階承認・snapshot一致・個別確認はそのまま要求する。standard taskのIssue照合、未実行Issue proposalの失効、commit/push/PR結果の照合規則は緩めない。

仕様/plan/design route/通常route/runtime/policy・remote・個人アカウントの変更、予定と違うcheck、改ざん・未成功・別task・旧schemaのIssue結果は照合不可。意図的なIssue scope変更は別の承認・計画整理を要し、今回の例外で受け入れない。Git入口の共通sync後に現在の値で判定する。

## 7. 中断・失敗と再試行

失敗時のファイルを自動restore/stash/deleteしない。failedは証拠として保存し、出力成功snapshotを持たない。部分的変更があれば未検証の現在snapshotとして表示する。runningの実行が終了したか不明ならunknownとし、新attemptを開始しない。

`resolve-attempt --attempt <id> --disposition abandon`を追加する。通常terminalで元status、消費予算、現在snapshot、範囲差分、残存processを表示し、本人が確認する。process終了が検証できなければ解消を拒否する。本人確認とstateのrevision・snapshot再確認後、status=abandonedにしてresolutionsへ元status・観測snapshot・理由・時刻を追記する。成功や合格へ変換しない。消費予算・レビュー台帳は維持する。

起動adapterはworkerのpidと開始識別子をprivateな実行管理情報に保存し、PID再利用を区別する。保存前に停止したなど、processが追跡できない場合は自動で「終了済み」と判定しない。明示したprocess確認手順が完了するまで解消不可。AIからの本人確認代行は禁止。

pendingの取消、paused_quota、unknownの解消は同じ入口で扱う。設計レビューとbootstrapには自動resumeを追加しない。通常autoの既存RESUME規則は維持する。解消後は新snapshotで計画を再承認し、新attemptを準備する。仕様・計画・design sourceが変わった場合は§4の失効を適用する。scope_violationの差分は人間が内容を確認して解消するまでbootstrap再実行不可。

## 8. 無意味なチェックを除く範囲

新規configure-checksで、argv[0]のbasenameが`true`または`:`、および`sh/bash/zsh -c`の文字列が空・`true`・`:`・`exit 0`だけ（前後空白を除去）なら拒否する。`python -c pass`のような全ての等価表現を検出できるとはしない。既存プロジェクト全体へ新しいcheck言語制限を遡及導入しない。

purposeとdefinition_pathsは人間と独立品質レビューの確認項目とする。テスト0件の検出はrunnerごとの実check側で非0終了になる設定・ラッパーを作り、その負例をテストする。汎用runnerが全出力形式からテスト数を推測して合格判定する方式は採らない。countだけでlint等を拒否しない。独立品質レビューでは、テスト収集実績・検証対象・必須領域・自明に成功するスクリプトでないことを確認する。

## 9. 受け入れ条件とテスト対応

| ID | 独立した期待値 | 主なテスト対象 |
|---|---|---|
| B01 | checks空でもinitと草案レビュー準備可。未解決要件の仕様承認は不可 | controller/spec |
| B02 | checks空の通常implementation/review/auto/verify・実装承認・commit proposalは不可 | controller/auto/gitops |
| B03 | bootstrap成功やdesign_review成功からimplementation/reviewを承認しようとしても拒否 | workflow/controller/gitops |
| B04 | 実際の失敗check・timeout・check中のsource変更・検証後の変更は成功証拠にならない | execution/workflow |
| B05 | checks登録で計画以降だけ失効。空のまま計画再承認してもverify不可 | config/controller |
| B06 | plan改訂・source内容と宣言hashの更新・baseline/design route/runtime/policy変更で設計digestが変わり仕様以降失効。sourceだけ変更しmanifest不変なら検証拒否。通常routeだけの変更は計画以降失効 | workflow/controller/spec |
| B07 | 旧state移行で旧履歴と予算を保存し承認はnull。新stateを旧validatorへ渡すと拒否 | migration/workflow |
| B08 | 同一provider、非TTY、EOF、確認不一致、確認中の入力変更はprovider起動0 | handoff/execution |
| B09 | review中のsource/plan/spec/全体snapshot変更、重要度矛盾、不正verdictを拒否 | design adapter |
| B10 | review-budget超過・座席再使用・別branch・台帳エラーで起動0。失敗後に予算を返さない | admission bridge |
| B11 | bootstrapの範囲外変更・禁止path・提案check不一致・定義ファイルなしを拒否 | spec/bootstrap |
| B12 | bootstrap中断→unknownでは後続不可。本人による解消後も生成物は未検証、新verifyが必要 | recovery/workflow |
| B13 | 登録後の中断・並行変更・revision競合で古い計画が使えず、同一configure再実行で承認を偽造しない | config/controller |
| B14 | HEADなしではbaseline-required、既存HEADなら一親の新commitのみ。root commitを暗黙作成しない | controller/gitops |
| B15 | High/Mediumあり又はapproved=falseなら不合格。Lowのみ＋approved=trueだけ合格 | verdict |
| B16 | T0生成済みだけでは依存task不可。4承認と品質合格後のみ同一binding依存が成立 | handoff |
| B17 | 不正path/symlink/会社環境、旧jobへ新phaseを混入、unknown keyを拒否 | validators |
| B18 | 初回計画承認→Issue作成1回→bootstrap→予定checks登録→計画再承認→verify→品質レビューと4承認→同じIssueでcommit proposalまで到達。Issue作成回数は1のまま | end-to-end fixture/gitops |
| B19 | 検証後の設定変更・後発の検証失敗・旧版attemptで過去成功を再利用できない | evidence eligibility |
| B20 | 既存通常開発は正規移行・再承認後に動く。旧v8経路と個人Gitの回帰を維持 | full regression |
| B21 | 作成済みIssueでもspec/plan/design/route/runtime/remote/account変更・予定外check・改ざん結果なら照合拒否。未実行proposalは計画再承認で失効し、scope digest一致だけでは実行不可 | gitops |
| B22 | brainstormingとv9で同じ設計レビューを二重予約しない。v9が1回だけbegin/consumeし、枠不足なら既存台帳を保持して起動拒否 | admission/skill flow |
| B23 | 新bridge・migration・design adapter・harness.py・実際に選ばれたhookの変更ごとにruntime digestが変わり、仕様以降が失効。必須ファイルの欠落も拒否 | runtime digest/controller |

fake providerと一時Git fixtureで状態遷移・副作用回数を検証する。実Claudeの認証・実行成功は別の実行証跡で確認する。実チェックの中には故意に非0終了するfixtureを含め、成功フラグの固定値だけのテストにしない。

## 10. 変更ファイルと作業順

controller/cli：準備・移行・設定登録・検証・解消・show-reviewとdesign digestの再計算。workflow：schema 10、型付き証拠、receipt bindingと失効groupの更新。spec/config：plan 10・予定checks検証。execution/handoff：各phaseと独立provider、端末境界。新しいadmission bridge：既存hook APIとの接続。auto/gitops：証拠混入・旧state/job拒否と§6.1の成功済みIssue照合。harness.py：既存ルートと独立したdesign route読込み。対応するtestsとdocuments/v9、error-codes、ai-dev-chat skillを更新する。hook本体・既存モデル選択を変更しない。

runtime_digestの対象は現在の8ファイル固定列挙から、以下の相対pathと内容hashのソート済み集合へ更新する。集合自体をhashするため追加・削除も検知する。symlinkや対象外へ解決されるpathは拒否する。

- `scripts/v9/`配下の全`.py`と`.cjs`。既存8モジュールのほかgitops.py、git_environment.py、新規migration.py、design_review.py、bootstrap.py、review_admission.cjsを含める。これらは必須ファイルとして欠落を拒否する。新モジュールも同じディレクトリに配置する。
- `scripts/harness.py`、`scripts/ai_dev_handoff.py`、`bin/ai-dev`。
- 対象projectで実際に選択したreview-budget.cjsのpathと内容hash（project起点の別namespaceで記録）。controllerが使用するhookと同じ解決結果を用い、ダイジェスト用だけ別copyを読まない。

runtime一覧の生成関数をcontrollerだけでなく全実行入口とGit共通syncで使用し、未対応ファイル欠落時は失敗させる。モデル設定の役割別変更はdesign_route/route digestでも検出する。policy_digestには現行workflow-policy、acceptance、ai-dev-chat SKILLを含める。実装時に新たな制御モジュールを別pathへ置く必要が生じた場合は、この対象表とB23を同時更新する。

今回のハーネス改修は、設計レビューの指摘対応→人間の設計承認→実装計画の確定・個別承認→Issue内容の個別承認と作業branch分離→型・移行・負例→準備とdesign review→bootstrap/configure/verify/recovery→回帰テスト→独立品質レビュー→結果承認→Git個別承認の順。改修後のT0がIssueを作る時点は§6のとおり、初回の仕様・計画承認後かつbootstrap前。既存personal Git対応の未コミット変更を移動・破棄・混在commitしない。

第2回の結果はHigh 0 / Medium 2 / Low 3で、5件を本書へ反映した。正規のレビュー枠2/2を消費済み。新しいHighはないため自動で第3回を追加せず、残存リスクと修正内容を人間の設計判断へ提示する。指摘対応はCodexの照合であり、Claudeが改訂版を合格としたものではない。設計承認・実装・Git操作はまだ行っていない。改修後のFitLogはv9通常モードを使い、今回の既存review経路の例外を恒久化しない。
