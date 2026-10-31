# 個人用の並列開発・承認運用の更新

ユーザー指示: 並列でもスムーズに開発できるよう個人用ワークフローを修正する。致命的でなければ承認申請は最低限とし、最初の計画承認後はpushまで進める。
対象はkoma236/FitLogのみ。会社用設定・会社repoは扱わない。

## 変更範囲と計画

準備branch docs/personal-parallel-workflow、worktree /private/tmp/fitlog-personal-workflow、baseline 0d234332d51f078f68137a421d442ff7abed1400。
このbaselineはFL-07のローカルcommitを含む。WFが追加する差分は以下の15パスだけとし、祖先のFL-07 commitをWFのreceiptだけで先に公開しない。準備・承認・レビュー履歴は正規stateとsource外の実行記録に保持する。
文書差分の対象はAGENTS.md、CLAUDE.md、README.md、documents/development/personal-workflow.md、personal-parallel-workflow.md。
本設計docと.ai-dev/wf-parallel.spec.json/.plan.jsonも本taskの記録としてcommit対象に含める。
文書・記録8ファイル（運用文書5、設計doc 1、spec/plan JSON 2）に加え、.claude/hooks/quality-gate.cjs、.codex/hooks/quality-gate.cjs、scripts/test-quality-gate-v9.cjs、scripts/fixtures/v9-push-proposal.json、scripts/fixtures/v9-push-provenance.json、.ai-dev/v9-git-entrypoints.json、skills/project/quality-check/SKILL.mdを対象範囲とする（合計15ファイル）。実装は独立設計レビューの合格と、この範囲への明示承認を条件にする。承認状態自体を本sourceに書き込まない。
Issue作成後も準備branchを継続し、実Issue URLとtask ID・branchの対応を記録する。番号追加のための改名は行わない。
WF-AC1の「矛盾を除く」は、最優先の個人運用節により適用規則を一意にする意味。配布元一般節は更新互換性のため保持し、PR/merge関連の適用除外を個人運用で条文名まで明記する。
製品機能、Compose、依存lock、登録checks、hook登録、共有main、認証情報は変更しない。hook実体の変更案は後述の限定入口に限る。FL-07製品差分は別branchのまま保持する。

1. 個人運用を承認の正本にし、最初の仕様/設計/独立レビュー/計画の承認から範囲内のIssue/実装/検証/修正/commit/feature pushまで委任する。
2. 正規v9 controller/proposal/TTY確認と実結果の照合は維持し、対応する入口ではactor=codex-owner-delegated。receipt直接生成・編集、本人入力の偽装、失効した承認の流用はしない。
3. PRは完成内容を最後に確認し、mergeは人間。範囲の重大変更・破壊・本番・予算超過・資格情報不足など必要な例外だけ再確認する。
4. 1 Issue/branch/worktree/書込み担当で独立したtask/stateを使う。他タスクの未保存変更を操作しない。
5. 編集は並列、固定Compose/DB/image/portを使うbuild/run/checksは共通git-dirの原子的runtime lockで直列化する。owner metadata・初期状態・残存processを確認し、既存サービスを停止しない。lockを勝手に奪わない。
6. CI/機能の所有範囲・共有fileの先行PRを明示。完全なruntime分離は別taskとして実検証する。
7. 独立設計レビュー→承認済み内容に一致する仕様/計画の正規receipt→Issue→文書/リンク検証と登録checks→独立品質レビュー→commit/feature push。PRは最終確認。

個別の条件付き委任: 人間が、修正済み設計・既存の独立レビュー指摘・対応を確認して「High/Mediumなしで合格した場合に限り、この同じ設計の実装からfeature pushまで進める」と明示した場合だけ適用する。承認記録は正規receiptとsource外の実行記録に保持する。明示承認がなければ追加枠を設定せず、実装しない。実際のpassing verdict前に仕様/計画receiptを発行せず、各receiptも実結果とbindingを確認してcodex-owner-delegatedで正規TTYから取得する。scope変更・未解消High/Medium・上限到達では条件未成立として停止する。PR作成・人間mergeを委任する規則ではない。

## 要件と受け入れ条件

要件本文（仕様JSONと同一）:

- WF-R1: 承認を最初の計画からfeature pushまでまとめ、正規v9とPR/mergeの例外を維持する。
- WF-R2: worktree/task/state/担当を分離し共有runtimeを安全に排他する。
- WF-R3: 品質hook・予算・未実行の正直な扱いと個人設定境界を保持する。
- WF-R4: 文書と限定hook互換修正を製品差分から分離し、製品・CI・Compose・登録checksを変更しない。
- WF-R5: 正規v9 feature送信と既存quality-gateを限定した入口で互換にし、trunk/force/不正入力を拒否する。

受け入れ条件:

- WF-R1 / WF-AC1: 工程ごとの再申請と包括委任の矛盾をAGENTS/CLAUDE/README/個人運用間から除き、PR・merge・重大例外・v9の技術ゲートを明確に区別する。
- WF-R2 / WF-AC2: 複数worktreeの担当・task/state・共有file・固定runtimeの排他と返却手順を文書で追跡できる。lockの自動奪取や他担当の削除を認めない。
- WF-R3 / WF-AC3: hook/品質基準/レビュー予算を弱めず、未実行を成功扱いしない。設定値は現物を正とし、ポートやcheckを推測で追加しない。
- WF-R4 / WF-AC4: 変更が文書・本タスクの仕様/計画JSON・限定したhook互換実装/許可設定/回帰テストに限定され、製品・CI・Compose・登録checksに差分がない。FL-07の製品差分を混在させない。
- WF-R5 / WF-AC5: 正規v9のfeature送信準備とproposal実行だけをhookが判定できる。正規入口・同一cloneの明示worktree・現在のfeature branch/HEAD・固定refspecを検証し、main/master・force・別repo・不明/不正/曖昧な入力を拒否する。既存trunkガードの回帰テストを維持し、実際に読み込まれたhookを確認するまで送信可能と報告しない。

## 独立した検証根拠

ユーザーの原文、現在のv9公開controllerのAPI（approve_phase/prepare_action/execute_action）と実TTY要件、実Compose/project.toml、git worktreeの実際の分離単位を根拠に文章とリンクを照合する。
文書の存在だけで並列検証やprovider成功を主張しない。登録11checksは製品非回帰として実行する。
独立設計/品質レビューは実装Codexと別providerのClaude。各provider実行は通常の上限3600秒、設計1回・品質は通常1巡と既存上限を維持する。上限超過は自動延長しない。
3600秒の根拠は、検証済み共通ハーネスcommit `169642d0c8040e24e048ee5f04777345e5242016` の `scripts/v9/controller.py`、prepare_runのmax_seconds既定値（293行）。project側harness-runtimeのモデル表から推測した数値ではない。
同commitのapprove_phase（controller.py 215〜283行）はactor引数を正規workflow.approveへ渡し、workflow.py 267〜291行がreceipt.actorへ保存する。実receiptの確認結果はsource外の実行記録に保持する。
handoff.run_jobとgitops.execute_actionには独立したactor引数がない。4工程の承認receiptのactorと、provider/Git操作の実行確認を混同しない。後者は同一workflowの承認receipt/bindingとproposalのapproval_digestで委任元を検証する。4工程のactor未対応入口は停止するが、独立actor引数のない実行確認を全て未対応と判定する必要はない。実行確認自体を人間の承認receiptに見せない。
レビュー修正でsource/spec/planが変わった場合はhashを更新し正規再bindingする。現行v9はsource/plan変更で設計結果を失効させるため、追加レビューと再承認が必要。既存結果の付替えや台帳消去はしない。追加枠が尽きたら明示承認を待つ。
Issue案: chore: streamline personal workflow and v9 Git gate compatibility。今回の改訂設計が承認された場合に文書・限定hook互換修正のcommit/feature pushまでを委任範囲とし、PRは別途確認する。

## v9 Gitとquality-gateの互換修正案

### 問題と選択

FL-07は登録11checksと独立レビュー合格、commit 0d234332d51f078f68137a421d442ff7abed1400まで完了した。正規prepare-gitのaction pushを含むコマンドが、quality-gateの環境変数prefix禁止で実行前に拒否された。prefixを除いてもv9 CLIは既存simple commandの閉じた一覧に入っていない。git-actionの正規job名にもactionが含まれる。これはGit送信の失敗ではなく、入口の非互換である。

採用案は、既存simple parserとは別に、正規v9のfeature送信2形式だけを明示的に分類する限定入口を追加すること。v9全体やpython/shell/script一般をrunnerへ登録しない。job名変更・文字列隠蔽・直接Git・hook無効化による代替はしない。共有ハーネスのreceipt/ジョブschema、承認・実行APIは変更しない。

### 対象と入力契約

- .claude/.codexのquality-gate本体を同一内容で修正する。hooks.json/settings.jsonとmatcher/command/timeoutは変更しない。既存契約の正本quality-check skillにも限定入口の説明を追加し、一般のsimple-form契約は保持する。
- .ai-dev/v9-git-entrypoints.jsonを明示許可設定とする。fieldはschema_version（整数1）、repository（koma236/FitLog）、account（koma236）、harness_root（下記絶対path）、harness_commit（下記40桁SHA）の5つに閉じ、unknown/重複field、型違い、別値、symlink/非通常file、過大入力を拒否する。秘密情報・credentialは入れない。設定はhookを動かすsession worktreeのGit rootから読み、明示送信先Pの設定へ切り替えない。設定不在時はv9の新しい許可経路を一切開かず、potential入力を含め既存classifierだけで判定する（A/Bはenv prefixとgate wordがあれば従来どおり拒否、gate wordのない形は従来の通過を維持）。この組合せも回帰テストに含める。設定が存在する場合に限り以下のpotential入力のfail-closed規則を適用し、設定異常や不明版では新入口candidateを拒否する。このJSON変更もgate control-planeとしてquality-checkとSecurityレビューを必須にする。
- runtime root/commitの登録値をhook codeへ二重にハードコードしない。rootは実HOME配下のliteral絶対path、commitは40桁lowercase hexとして型/形を検証し、Sのreview済みHEADと一致する設定を正本に実runtimeのrealpath/HEADを照合する。本taskの登録値は下記の配置先と169642dに固定し、将来の値変更は設定の別レビューを要する。schema/repo/accountは上記の固定値以外を受理しない。
- 使用するcodeは169642d0c8040e24e048ee5f04777345e5242016に固定する。同commitの専用checkoutを/Users/saki/.codex-personal/runtimes/ai-dev-harness-169642dに配置し、ここだけを許可設定に登録する。共有標準checkoutを変更しない。root欠落はV9_GATE_RUNTIME_MISSINGとしてpathと必要な採用作業だけを表示して拒否する。将来の標準runtime採用も実commit確認と許可設定更新の品質レビューを要する。
- このuser固有の絶対pathを設定に持つことは、個人専用・同一hostのFitLog運用に限定した明示的な選択とする。pathは秘密として扱わないが、他user/hostへの可搬性を主張しない。全v9工程の実行版と整備checkoutの区別はpersonal-workflow.mdにも同じ定義を置く。
- shellOf(tool_name)==='posix'の場合のliteral argvだけを対象にする。Codexのexec_commandは公式Hooks文書でcanonical Bashに対応する（https://learn.chatgpt.com/docs/hooks、Tool coverage/Common input/PreToolUse）。実採取のnative payloadでこれを確認する。資料やparser probeからの推定を実payload captureと偽らない。後述のnative probeを最初の実装検証に置き、Bash→posixを実採取するまでv9形式を実利用しない。WF送信を実行するclientのcaptureを完了条件とし、他clientは実施済みかnot runかを明示して区別する。Claudeで送信する場合も事前に別native fixtureを採取する。別名/unknownだった場合はshellOfを黙って拡張せずX4で設計判断へ戻す。
- 許可root/bin/ai-devの絶対pathと、同じrootのAI_DEV_HARNESS_HOMEを1個指定する形式を受け付ける。rootはrealpathで一致し、Git HEADは許可commitである。権限検査はroot、bin/とscripts/の全entry（通常fileとdir）に限定し、各entryは現UID所有、group/world writable不可、symlink不可。bin/ai-devを必須通常fileとする。.git内部、tests/、documents/等の非実行領域は再帰走査しない。rootからHOMEまでの親検査は後述の別条件で行う。bin/scripts合計は4096entryを上限とし、各lstat/readdirの前後で新入口12秒/既存20秒deadlineを確認し、上限・時間超過・読取り失敗は拒否する。走査結果をprocess間でcacheしない。rootから実HOMEまでの親も同条件、HOMEより上はroot所有かつgroup/world writableでないOS管理領域に限る。bin/とscripts/の全域にtracked差分・untracked・ignoredファイルを認めず、Python module/pycache混入も拒否する。キャッシュを作らない実行条件を用いる。runtimeのGit読取りも既存runGit、SAFE_GIT、GIT_ENVと共通deadlineを使う。任意の追加env、shell展開、wrapper/nested shell、複数コマンド、pipe/redirect、余分/重複/不明optionは拒否する。PowerShell/不明shellのv9新形式は今回許可しない。
- import隔離とcache非生成は固定commitのbin/ai-devの実byteに依存する。launcherはPYTHONPATH="$ROOT/scripts"を設定してpython3 -P -B -m v9.cliを実行し、cwdの追加とpycache生成を抑止する。追加envを許可して解決しない。commit/純粋性照合でこのlauncherも対象とし、Aの実行後にBのpreflightが再び純粋性検査を通る回帰caseと、pycacheを置くと拒否するcaseを用意する。
- 形式Aは v9 prepare-git --action push --project <P> --task <T> --remote origin --branch <B>。CLIが行うのはproposal準備であり送信ではない。Pは実在worktreeで、現在hookを動かすworktreeと同じgit-common-dir、BはPの現在branchと完全一致、空/detached/main/master（大小含む）は不可。task/branchはv9の既存制約に適合させる。extra commandや別actionへ一般化しない。
- 形式Bは v9 git-action <J> --project <P>。Jは現在ユーザーの正規private v9/git配下の通常ファイルで、親dirを含めsymlinkを認めず、他ユーザーowner/過剰権限/1MiB超/不正JSONを拒否する。pathはPとtaskのSHA256、actionとproposal_digestからなる既存正規pathに一致する。コピー・別名jobを許可しない。
- 受理するliteral token列は固定する。Rは登録rootの絶対path。Aは `AI_DEV_HARNESS_HOME=R R/bin/ai-dev v9 prepare-git --action push --project P --task T --remote origin --branch B`、Bは `AI_DEV_HARNESS_HOME=R R/bin/ai-dev v9 git-action J --project P`。prefixは必須、1個だけで値はRと完全一致、option順は上記固定とし省略/並替え/重複/別envを許可しない。空白pathは既存POSIX tokenizerでliteralとして一意に読めるquoteのみ、展開や連結quoteは拒否する。通常gitのenv prefix禁止はこの限定入口と分けてそのまま維持する。
- pathの根拠は固定commitのscripts/v9/handoff.py 52〜78行（home/project正規化）とscripts/v9/gitops.py 204〜207行（Git directory）。homeReal=realpath(Path.home())であり、AI_DEV_HARNESS_HOME/CODEX_HOMEから導かない。Pはliteral絶対pathをabspathし、末端symlinkを拒否してstrict realpath、Git root一致を確認したPRealを用いる。Jの正規式はhomeReal/.ai-dev-harness/v9/git/SHA256(UTF8(PReal))/SHA256(UTF8(task))/push-<proposal_digest>.json。hash対象に末尾slashやUnicode正規化を加えない。macOSでは親/tmpのsymlinkが解決されるため/tmp/exampleと/private/tmp/exampleは同じPReal/hashになる。J自体のsymlinkは許可しない。
- Nodeでhashに使うrealpathはnon-native fs.realpathSyncとし、Pythonのcomponent-wise symlink解決に合わせる。A/BのPは物理caseに一致する表記を要求し、fs.realpathSync.native(P)とのcase差があれば明示的な表記エラーで拒否する。case差を黙って別hashへ直さない。/tmp parent symlinkの解決は許可し、case-variant Pは負例で確認する。
- Bではschema10/operation git_action/action pushと既存envelope/proposalの閉じたfield集合を確認する。project=P、task、branch=B、commit=PのHEAD、refspec=HEAD:refs/heads/Bを照合し、repo/accountは明示設定と一致させる。remoteはoriginのみ。未知field/型・trunk・force相当refspec・別repo/worktree cloneを拒否する。proposal_digestの形式を確認し、内容hash・4工程receipt・workflow revision・commit/Issue chain・実効remoteと実アカウントの最終照合は既存v9 execute_actionが引き続き実施する。hookをv9の全validatorの複製にはしない。
- hookは判断のためにprovider/ハーネスcodeを実行せず、Gitのread-only metadata、設定とjobの必要fieldだけを読む。private job本文やcredentialsをログへ出さない。許可は「正規v9が処理してよい」であり、Git成功や承認receiptの発行ではない。
- 従来のgit/ghのtrunk・force・曖昧commandの判定、flag、review-budget、会社環境禁止は維持する。設定が存在する場合、新形式の許可失敗を既存のno-gate-word早期通過へ落とさず、v9新形式として認識した不正入力は拒否する。設定不在時の既存動作とは区別する。

固定runtimeのGit入口はcli.py 50〜58行からgitops.prepare_action/execute_actionへ入り、gitops.py 55〜61行とgit_environment.py 132〜162行でcanonical home由来の個人設定を読む。継承したCODEX_HOMEは選択元に使わず、git_environment.py 67〜73行の_baseが最小環境を作り、子Git/gh用CODEX_HOMEをhome/.codex-personalに設定する。したがって呼出しprefixにCODEX_HOMEの追加指定は不要で、AI_DEV_HARNESS_HOMEだけを明示する文法と整合する。Codex本体は起動時から個人CODEX_HOMEを使うという別条件を維持する。runtime更新でGit入口が継承CODEX_HOMEへ依存するよう変わった場合は、その場でprefixを拡張せず設計判断へ戻す。

残存する信頼境界として、runtime純粋性はRのcode byteを対象とし、継承PATHで解決されるpython3の実体やPython関連のsession環境をhookは検証しない。これらは信頼済み個人sessionの前提とする。送信前に調整役がcommand -v python3と版を採用記録に照合し、不一致は停止する。秘密を含み得る環境一覧は出力しない。repo/accountはhookの固定値koma236/FitLog・koma236が権威であり、設定の二つのfieldは一致確認用である。root/commitだけは設定が正本であり、この役割をquality-check契約にも明記する。

### 新入口の認識predicate

以下は設定が存在する場合の認識・検証規則であり、設定不在時は前節の既存classifierだけを使う。認識と許可を分ける。既存と同じquote/escape折畳みをした入力に、ai-dev（PATH名・相対path・末尾/bin/ai-devを含む）の呼出しと、それに続くv9およびprepare-gitまたはgit-actionがあればpotential v9 Git入力とする。安全にtokenizeできないpotential入力は拒否する。

tokenizeできた場合、従来からあるprepare-gitの既知non-push action（issue/commit/prを1個だけ指定）と、git-actionの既知non-push正規basename（issue/commit/pr-<64hex>.json）は、pushのgate wordが他にない場合だけ既存classifierへ渡す。これらは新しいfeature送信例外による許可ではなく、従来の非送信入口の扱いを保つもの。v9自身によるjob identity/action整合検査も維持する（gitops.py execute_action 709〜719行）。non-pushを一律拒否してIssue作成やWF自身のcommitを壊す案は採用しない。

上記以外のpotential入力を新入口candidateとし、gate wordの有無によらず固定A/B grammarで検証する。不一致は既存の早期allowへ戻さず拒否する。近似入力の負例にはPATH/relative ai-dev、prefix欠落、missing/unknown/different action、非正規job名、重複action、追加commandを含める。既知のissue/commit/prは新例外に該当しないという負の分類と、従来挙動維持の正例を両方テストする。v9 Git以外のcommandは従来classifierを使う。non-pushでもP/task/HOME path等にpush/pull/merge/rebaseのgate wordが含まれると既存経路へ除外されず拒否し得る。これはfail-closedの既知の制限とし、運用上はworktree/task名でgate wordを避ける。Pにgate wordを含むnon-pushの負例も追加する。

### HOMEの解決と使い捨てテストの境界

本番のHOME解決はPOSIXのNode os.homedir()を入口とし、non-native fs.realpathSyncでstrictに解決する。Python Path.home()がPOSIXでHOMEを優先し、固定runtimeのhandoff.py 52〜57行がそれをstrict resolveする契約と一致させる。ただしenvだけで信頼境界を移せないよう、os.userInfo().homedir（OSユーザーDB由来）も同じ方法で解決し、両者が完全一致しなければ拒否する。片方が欠落・非絶対path・解決失敗でも拒否し、異なるHOMEへのfallbackや環境変数の書換えは行わない。この一致済みhomeRealをRの配下検査とJのpath計算の両方へ使う。本ホストの読取り確認ではNode両値とPythonのPath.home().resolve()はいずれも/Users/sakiだった。異なるHOMEで正規v9が動くこと自体を、hookの許可根拠にしない。

使い捨てテストはHOME/CODEX_HOMEや本番configに注入flagを追加しない。scripts/test-quality-gate-v9.cjs内だけでNode vmの独立module contextを作り、require境界のnode:os/os（homedirとuserInfo）およびfsのOS管理ancestor metadataをfixtureへ置き換える。production moduleのexport・環境変数・CLI・設定から切替可能な入口は作らない。test home以下の所有者/mode/symlink判定には実一時filesystemを使い、その上のOS管理ancestorだけをroot所有・非書込みのfixture metadataとして提示する。同じ本番ancestor検査関数を正例でも通し、UID不一致/group・world writable/symlinkを1条件ずつ変える負例、二つのhome不一致の負例も用意する。テスト専用依存の置換はOS情報境界だけであり、allow/deny、config/job検証、Git metadata取得、self byte比較をstubしない。mkdtempの実親を本番で信頼するよう検査を弱めない。native採用確認はこのvmを使わず、実HOME・実ancestorで行う別証拠とする。

### Git読取り・時間・self byteの契約

新入口のGit呼出しはすべて既存runGit/SAFE_GIT/GIT_ENVを通し、GIT_OPTIONAL_LOCKS=0を重ねる。statusのindex refreshを含む任意lockを取らない（https://git-scm.com/docs/git、GIT_OPTIONAL_LOCKS）。metadataの取得にgit fetch/更新系commandは使わず、lazy fetchとpromptも既存設定で無効にする。

Sは現在ロードされたhook実体を含むworktree、Pは明示送信先、Rはruntime。Sはpayload cwdやPから選ばず、非symlinkの__filenameをrealpathし、そのdirnameをcwdとする下記1のrev-parseが返すGit toplevelと定義する。__filenameがS/.claude/hooks/quality-gate.cjsまたはS/.codex/hooks/quality-gate.cjsの実pathでなければ拒否する。許可設定・self byte・common-dirのanchorは一貫してこのSを使う。payload.cwdは別にstrict realpathした実在dirを要求し、S自体またはその配下でなければ拒否する。配下の場合はSまでの祖先をlstatし、S以外に.git file/dirがあればnested repoとして拒否する（追加Git callは行わない）。CLAUDE_PROJECT_DIRが存在する場合もstrict realpathがSと一致することを要求する。process.cwd()をSの選択に使わない。既存classifierのcwd取扱いは変更せず、新入口だけにこのanchor契約を適用する。cross-task操作はcwdをSに保ち--project Pを明示する。テストにはpayload cwdがS内の正例、P内なのにhookがSからロードされた負例、全worktree外・nested repo内の負例を含める。A/B共通の呼出し一覧は以下に閉じる。同一process内だけ取得済み結果を再利用し、P=Sなら重複しない。

1. realpath(__filename)のdirnameで `rev-parse --show-toplevel --absolute-git-dir --path-format=absolute --git-common-dir HEAD` を1回。root/gitdir/common-dir/HEADの4出力を検証する。
2. P!=Sの場合だけPで同じrev-parseを1回。
3. Pで `symbolic-ref --quiet --short HEAD` を1回。detached/失敗は拒否する。
4. Rで `rev-parse --show-toplevel HEAD` を1回。
5. Rで `status --porcelain=v1 -z --untracked-files=all --ignored -- bin scripts` を1回。非空は拒否する。
6. Sで `cat-file blob HEAD:.claude/hooks/quality-gate.cjs`、`cat-file blob HEAD:.codex/hooks/quality-gate.cjs`、`cat-file blob HEAD:.ai-dev/v9-git-entrypoints.json` を各1回。

前提は本ホストで確認したGit 2.50.1と、上記--path-format=absoluteを含むmetadata commandへの対応である。非対応版または不正な出力は「必要なGit metadata形式を取得できない。対応Gitとworktreeを確認」という理由で拒否し、曖昧な相対pathへfallbackしない。新たなversion取得Git callは追加しない。

最大8回。新入口全体のGit予算は12秒、各呼出しは2秒か残り予算の短い方とし、既存20秒DEADLINEにも常にclampする。filesystem/JSON処理の境界でもdeadlineを確認し、Gitの失敗・timeout・予算切れはv9入口をfail closedにする。従来callerの時間契約を変えないようrunGitの新入口用timeout指定はoptional引数とする。

self byte比較はPではなくSのHEADに対して行う。cat-file読取りにはrunGitの新しいoptional binary modeを使い、execFileSyncのencodingをnullにしてBufferを返す。script/configもfs.readFileSyncにencodingを指定せず読み、Buffer.equalsで比較する。既存の文字列callerの既定utf8 modeは変えない。実行中scriptの__filenameはS内の上記2つのどちらかと一致し、判定時に__filenameから読んだscript byte、ディスク上の両copy、設定の全byteがSのcat-file結果と一致することを要求する。invalid UTF-8、BOM、CRLF差分を正規化しない。Nodeのmodule読込みの瞬間と、この判定時読取りとの原子的同一性までは保証しない。稼働hookは後述の検査済み候補の原子的rename手順でのみ置換し、置換中はprovider/Git操作を停止する協調運用でこの時間差を扱う。read errorや未commit設定・hook編集は拒否する。通常git diffがindex flagで差分を隠してもblobとの直接比較を省略しない。native採用記録にも同じSのscript/config hashを記録し、invalid UTF-8 byte/CRLF/BOMだけが異なる負例も作る。

テストではP/R/Sのindex・refs・packed-refsの内容hashとmtimeを取得前後で比較し、不変を確認する。既存index.lockがあるcaseでもそれを削除/書換えず、optional-locksを無効にしたmetadata読取りだけを行う。command一覧・環境・timeout上限をfake runnerでも検証する。

### Native診断の限定契約

診断機能はreview・commitされるhook本体に残すが、通常は無効。別worktreeやruntime更新後にも実際の採用版を確認するため恒久的に保持し、固定path・opt-in・最小metadataの契約を変える場合は別のcontrol-planeレビューを要する。opt-inはenvではなく、調整役がSのworktree固有Git dir（共通dirそのものではない）に作る固定名 `v9-gate-probe.request.json` とする。requestはschema_version=1とrandom nonceのみ、現UID・0600・通常file・1KiB以下を要求し、symlinkを拒否する。任意の出力pathを指定させない。

hookは診断専用の固定raw command `git status --short --untracked-files=no -- .fitlog-native-hook-probe` と完全一致する場合だけ、no-optional-locksのrev-parseでsession固有Git dirとcommon dirを解決する。普通のstatus commandには追加Git読取りをしない。両dirが同一のmain checkout等では診断を無効にし、markerを読まず何も記録しない。この1回はv9 A/Bの8-call予算とは別経路だが、既存DEADLINEと2秒上限にclampしGIT_OPTIONAL_LOCKS=0を使う。他commandのno-gate-word fast pathは維持する。marker不在なら記録しない。正しいrequestがある時だけ同じdirの固定名 `v9-gate-probe.result.json` をO_CREAT|O_EXCL|O_NOFOLLOW、0600で作り、nonce、tool_name、cwd、読込みscript realpath/sha、config sha（採用前はnull可）だけを記録する。raw commandやjob/provider本文は保存しない。診断の成否は通常のpermissionDecisionへ影響させない。失敗時は採用確認を不成立として扱う。

調整役は採取後、nonceとowner・通常file・非symlinkを再確認して自分のresult/requestだけをfinallyで除去する。途中終了で残った場合も同じ所有確認なしで消さず、他worktreeのGit dirへ触れない。削除完了と採取結果の最小metadata/hashを品質reportへ記録する。回帰テストにはdefault off、固定command以外では記録なし、unsafe marker拒否、O_EXCLで既存resultを上書きしないこと、0600、cleanup、permissionDecision不変を含める。

### 独立したテストオラクル

scripts/test-quality-gate-v9.cjsをnode:testで実行する。ネットワーク・共有Docker・実repoへのGit送信は使わず、temp Git repo/worktree、固定HEAD、private test homeを使う。native stdin payloadを通すテストを含め、.claude/.codexのbyte parityと、判定後もrefs/HEAD/job/workflow/外部環境を変更しないことを確かめる。

正例fixtureは手書きschemaから作らない。2026-10-31に固定commitのpublic v9.cli.prepare_gitから実際に生成済みの/private/tmp/wf-v9-producer-fixture/proposal.json（sha256 d0ba9c5c3f8f3c572b0ba5d643ca6a281416581003ffe01463c87a0edff53344）とprovenance.jsonを、承認後に予定fixture pathへ保存する。これは使い捨てrepo/home・fixture専用accountのテストデータ。workflowと承認データは固定commitのupstream test fixtureで合成し、外部commandのうちGH account/Issue応答をモックした。Git metadataとproposal producerは実物、送信はprepareのみでexecuteしていない。実workflowのreceiptには触れず、実承認/品質ゲート成功の証拠として使わない。

materializeは元fixtureのshaとfield集合を先に照合し、envelopeのproject/task、proposalのbranch/commit/repository/account/fetch_url/push_url/refspecと、personal_environmentのaccount/config path/gh_config_dir/git_config_fileを使い捨てidentityへ置き換える。repo/accountはkoma236/FitLogとkoma236へ合わせるが、ネットワークや実個人設定を使わない。proposal_digestは独立した標準JSONのsorted-key・ensure_ascii=false・compact encodingのSHA256で再計算し、Jを新identityから計算する。binding_digest/workflow_revisionはfixture値のままで、実receiptやworkflowを表さない。hookはproposal_digestの形式だけを検証し、改変後の真偽やreceiptはdownstreamの責務のままにする。この書換え一覧・元producer由来とmaterialized単体fixtureの区別をprovenanceとtestコメントに記録し、materialized値をkoma236向けの実producer出力と報告しない。

通常の回帰suiteはcommitしたfixtureとprovenance/上記固定shaを決定的な形式オラクルにし、共有ハーネスやネットワークを必要としない。可変identityのmaterializeはfixtureのfield集合を保持し、独立した標準JSON/SHA256計算を固定fixtureの既知digestに照合してから使う。これはpreflightの単体オラクルであって、実workflow合格ではない。negative variantsはその正例から1条件ずつ改変する。hook側validatorからfixtureや期待値を生成しない。live producerによる再生成比較は明示的な追加検証とし、pinned runtime不在時はnot run/skipを記録する。省略を成功件数に算入しない。実taskの正式v9実行には採用済みruntimeが必要という条件は別に維持する。

導入時に/tmp側のfixtureが欠落または記録shaと不一致なら、固定commitのpublic producerで再生成し、生成日時/新sha/provenanceを記録するか停止する。古いshaへ合わせるための手編集・捏造はしない。再生成は実taskのreceiptとは別の使い捨てテストcontextだけで行う。

正例は許可root/commitのA、正規B、同一cloneの明示別worktree、feature名にmainを部分文字列で含む場合、/tmpと/private/tmp表記の同一project。負例はtrunk/detached、branch/HEAD/project/refspec不一致、別clone、unknown schema/field/action、欠落/不正/過大/unsafe-permission/symlink job、root/commit差異、tracked/untracked/ignored module/pycache混入、root/parent/binおよびscripts/v9深部fileのowner/mode不正、4096entry/時間上限、追加env/options/commands、shell展開、PowerShell/不明shell。

破損hash/失効receiptをhookのstub downstreamが拒否しても、v9検証成功とは数えない。hook単体では「そこはdownstreamの責任」という契約境界だけを確認する。実v9の拒否証拠は固定commitのtests/test_v9_gitops.py等のexecute_actionを実際に呼ぶupstream test（tampered refspec、stale workflow/approval、invalid digest等）を別に実行して得る。runtime不在時はnot runであり、モックprocessの結果で代用しない。

baselineにはhook回帰suiteがないため、既存ガードに対する新規の固定期待値テストを作る。最低限、通常feature送信allow、main/master送信のflag要求、force-to-trunk拒否、trunk rewrite拒否、nested shell拒否、通常gitのenv prefix拒否、no-gate-word通過を含める。テストは本番hookの自前validatorから期待値を生成しない。quality-checkはgate control-plane変更として省略せず、mechanical checks後に統合・反証QA・Securityの体制で実施する。既存11checksに加えてnodeの構文/回帰テストを明示実行し、登録checksやtrustをすり替えない。

upstream testやlive producer比較は、登録runtime Rでは実行しない。Rとは別の同commit169642dの使い捨てcheckoutを一つ作り、その中だけで行う。Python実行はpython3 -Bを使い、子PythonにもPYTHONDONTWRITEBYTECODE=1を指定する。pytestを使う場合はさらに-p no:cacheproviderを指定する。これらは使い捨て検証用processの条件であり、正規A/Bのenv grammarを拡張しない。実行前後にRのHEADとstatus --porcelain=v1 -z --untracked-files=all --ignored -- bin scriptsを読み取り、変化なし・非空差分なしをsource外reportに記録する。Rに汚染が見つかった場合は自動clean/cache削除/再配置せずX7で停止する。使い捨てcheckoutのcleanupは自分の所有と生成物を確認したものだけを対象にし、実workflowや他taskに触れない。既に取得したupstream負例の証拠はRではない/private/tmp/fitlog-v9-review-contractを利用したもので、使い捨てfixture state以外の承認やGit送信を行っていない。

専用runtime採用時にはpython3の実体pathと版を記録し、-Pが使えるPython 3.11以上を要求する。本ホストでは/Library/Frameworks/Python.framework/Versions/3.12/bin/python3、Python 3.12.3を読取り確認済みだが、採用時にも再確認する。native採用reportにこの情報を記録し、hook側に版取得processやGit callを増やさない。条件不成立なら採用を停止し、別launcherや追加envで迂回しない。

### 段階と採用条件

0. 準備ではWF HEADとplan baselineを0d234332d51f078f68137a421d442ff7abed1400へ揃え、ancestor・入ってくるpathと自分の未保存pathの非衝突・byte保全を確認する。main/master/FL-07側のref変更、force/reset/rebase、別branchへの予算移動は行わない。準備の実施記録はsource外に保持する。
1. source/spec/plan hashを再生成して正規controllerで再bindingし、新baselineの改訂設計レビューを受ける。固定baselineが実HEADと違うままのv9操作はしない（固定runtimeのcontroller.py 131〜144行）。同branch/task/既存state/既消費予算を保持する。原則は合格結果を人間へ提示してDesign Gate承認を得る。上記の条件付き委任を人間が明示した場合だけ、その同じ設計で合格条件を満たした後に再申請なしで進める。これらの条件が成立するまではhook/config/testを実装しない。
2. 設計承認後、同じWF branchで実装する。最初に上記限定契約のopt-in marker方式でnative payload計測を行い、tool_name/shellOfと最小metadataだけを保存する。共通Git dir直下や任意pathへの出力は認めず、codeは出荷するhookに含めてレビューする。raw capture未取得またはBash→posixでなければv9互換入口の実利用を止め、X4/X6として相談する。Claudeの実transport未計測時はnative Claude対応確認済みと報告しない。
   稼働hookは直接編集しない。候補はhook登録が参照しない一時ディレクトリで作り、node --check、既存ガードの固定期待値テスト（main/masterへの送信のflag要求・force拒否を含む）を通してから、各hookの同一filesystem上の非登録一時fileへ書き、renameによる原子的置換を行う。両copyの置換中はprovider/Git操作を開始せず、置換後にbyte parity、構文検査、native stdin形式のfake入力による上記既存ガードのdenyを再確認してから作業を再開する。テストは文字列の分類だけであり実際の送信を行わない。検査が失敗した場合はGit/provider操作を停止し、同じ検査済み候補の置換手順で修正する。候補/一時fileは自分のものだけを除去し、commit対象15パスを増やさない。現在のroot sessionがFL-07側hookを使うことをWF側hookの安全性の代替根拠にしない。実装中・採用後ともtrunkへのGit変更操作は行わない。native採取の品質reportには公式URLの確認日と実際のtool_nameを別々の証拠として記録する。
3. 専用runtimeの安全な配置、限定入口・許可設定・producer由来fixture・新規回帰テスト・契約docを実装する。登録11checksは排他枠とmigration graph照合後に新しいWF baselineからbuildして実行する。コードはFL-07のsocial0002を含むので、WFの検証/commitはFL-07のGitHub送信・人間mergeに依存しない。WF公開には別途下記の先行送信条件を要求する。未知schema差分を無断reset/逆migrationで解消しない。
4. WFのquality-checkは明示baseline 0d234332d51f078f68137a421d442ff7abed1400に対する予定15ファイルを対象とする。全mechanical checks後にgate control-planeの統合・反証QA・Securityレビューを行い、WF自身の四receiptを正規手順で得てWFをcommitする。FL-07のreceiptをWFへ流用しない。
5. 読込み規則はClaudeがCLAUDE_PROJECT_DIR優先→git root、Codexがsession cwdのgit rev-parse --show-toplevelである。exec_commandのworkdirだけでhookのsession cwdが変わったと仮定しない。WF commit後、.claude/.codexの両hookと許可設定がHEADのreview済みbyteと完全一致し、git diff --quietでも差分がないこと、native診断のscript/config hashがそのHEADと一致することを確認する。不一致なら実行しない。新しいv9形式もこの一致を毎回の入口条件にする。FL-07/main/他担当worktreeへhookをコピーしない。現在のUIから採用元を切り替えられない場合は、WF worktreeをcwdとするsession開始というAIから行えない操作を人間へ1回まとめて依頼し、それまでは送信しない。
6. WFの公開前条件は、baseline commit0d234332d51f078f68137a421d442ff7abed1400がFL-07自身の正規v9 git-actionでorigin/feat/fl-07-timelineへ送信済みで、そのremote SHAを確認できること。WFを先にpushして未送信のFL-07 ancestorをWF receiptで公開しない。WF自身の完了は、自身の検証・独立レビュー・四receipt・commit・hook採用証拠・正規feature pushとremote SHA確認までとする。FL-07の送信作業や人間merge自体をWFの成果とは数えない。

### 別taskへの送信とPRの後続チェックリスト

A. cross-task送信の順序は、WF品質確認→WF commit→Sのreview済みbyte/native一致→FL-07自身の正規v9 git-actionとremote SHA確認→WF自身の正規v9 pushとremote SHA確認。FL-07の操作ではWF sessionからP=/Users/saki/.codex-personal/worktrees/fbbe/FitLogを明示し、その既存commit・四receipt・proposal・同一cloneを再検証する。設計準備で両worktreeのgit-common-dirが/Users/saki/project/FitLog/.gitと一致することを読取り確認済みで、source外の実行記録にも保持する。送信時に不一致ならX4で経路を再設計し、別cloneを許可する例外を加えない。これは計画されたcross-task経路であり、FL-07のsource/bindingへhookを混在させない。WF push直前にもFL-07の正規resultとremote SHAを再照合し、欠落/不一致ならX4/X7で停止する。

B. runtimeのcode同一性も送信前条件とする。設計準備時にFL-07の既存stateと4工程receiptを読み、runtime_digest=ca1dff910931ae6b2f565d5465c2ea5b1a5f35ad65f53d57c3077d9aa44cca66、policy_digest=e51e3fb9513c1c6456dc80e691a2bb558a42cfd5daaba0bd4538c616d8603c7fが、commit169642dのpublic controller.runtime_digest/_tree_digestによる再計算と全件一致することを確認した（source外記録 /private/tmp/wf-fl07-runtime-proof.json）。実装時には専用配置先Rでも同じ再計算を行い、FL-07のstate/四receiptと一致し、RのHEADが169642dであることを送信前に再確認する。codeは相対pathとbyte hashで束縛され、同一codeの配置移動で内容を変えない。異なるcode版を使ったprepareし直しやreceipt付替えはせず、差異はX4/X7で停止する。
C. PR作成承認は別途、mergeは人間。FL-07 PRは元SHAを保持するGitHubのMerge pull request（merge commit）方式で先に人間mergeすることを、このstacked workflowの採用条件として明示する。2026-10-31の個人アカウントAPI読取りではallow_merge_commit=true、mainの有効ruleはdeletion/non_fast_forward/pull_request/required_status_checksで、required_linear_historyはなかった。実行前に再照合し、設定は変更しない。PR本文と最終確認にも方式を記載する。方式と元commit保持の根拠: https://docs.github.com/en/pull-requests/reference/pull-request-merges 。
D. 人間merge後、元commit0d23433がorigin/mainの祖先であることと、WF PRの三点diffが予定15ファイルだけであることを確認する。planのdepends_onは同plan内v9 task用のため空のままとし、Gitの先行依存はbaseline_commitで固定、cross-task送信順と公開順をplanにも記録する。
E. squash/rebase等で元SHAが残らなかった場合、force/rebase/resetで追いつかせず、WF PR作成前にX4/X7で停止して運用変更の判断を求める。レビュー4の「origin/mainをWFへmergeしてそのまま再検証・再push」は、現行v9では通常の回復手順として採用しない。固定HEAD/baseline条件（controller.py 131〜144行）に加え、standard taskのIssue chainは仕様/計画receiptのapproval_digestに一致する必要があり、baselineを変えて再承認すると既存Issueが自動再利用されない（gitops.py _matching_resultのsame_gate/action issue、_require_workflow、prepare_action）。bootstrap専用のIssue再利用をstandardへ流用しない。別taskのハーネスreconcile設計、または本人の統合方法の判断が必要であり、v9 sourceを別scopeで直す許可まで本計画に含めない。これはmerge commit採用条件からの逸脱時の停止契約で、既知のv9制約を無視した自動回復を約束しない。

完了の証拠は、入口単体の回帰結果、既存ガードの維持、実際のhook読込み、各taskの登録checksと独立レビュー、正規v9 Git結果を別々に記録する。設計合格やhook単体成功だけでFL-07/WFのpush完了とは扱わない。

承認状態、各レビューの消費数/判定/時刻、採用/公開の進行状況は本source外の正規state・実行記録・品質report・PR本文に記録する。source自体に「未承認」「未実装」等の可変ステータスを書き戻してhashを失効させない。
