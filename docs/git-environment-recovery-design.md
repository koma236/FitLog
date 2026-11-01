# WF-GIT-RECOVERY: Git設定の編集用メタデータ追加後の明示的な復旧

本書は固定の設計契約を記す。作成済みの本書・spec・planは、最終設計承認時のbytesを変更せず、新規ファイルの追加としてcommitする。plan.pathsへの包含はcommit対象であることを示し、実装中の編集許可ではない。承認後の補足・差異・採用結果は別の運用文書かsource外reportへ保存する。quality-checkでは承認済みmanifestの3sourceが要求するsha256と本書のraw bytesを比較し、commit後も同じ期待hashでblobを照合する。期待hashを本書内へ埋め込み循環させず、承認済みspec/receiptの束縛を起点にする。承認・レビュー消費・実装・送信の進行状況は、正規stateとsource外の実行記録に保存する。

## 目的と範囲

FL-07の承認済みcommit `0d234332d51f078f68137a421d442ff7abed1400` はGit設定全体のfingerprint変更で送信準備に失敗する。共有configのmain節へ `vscode-merge-base = origin/main` が1行追加されたことが唯一の差分である。旧hashは `6bd06089bbf149e6b9886a2ca23d81570d99d254c8515dade6877b75ef29860d`、現在は `42fa0496c05567620998cb9e9de6134408050f83f8a767b56ccc53dbd8800b3b`。メモリ上で当該1行を除いたバイト列のhashが旧hashに一致することを確認した。設定ファイルは変更していない。

repoはkoma236/FitLog、個人accountはkoma236のみ。同一cloneの現在のfeature worktreeを対象とし、main/master・force・merge・履歴書換えを扱わない。FL-07/WF-PARALLELのソース、既存のspec/plan、private workflow・四段階receipt・Git proposal/resultは上書きしない。認証情報の複製や表示、会社環境の探索、共有Git configの書換えも行わない。

## 後続taskの成立条件と追加変更の扱い

WF-PARALLELの正規commit job `commit-a5a0405291bf3d82deab8f1d4c31ef3be1e677261a6aca0adb6885144c85e878.json` を読取り確認した。workflow_revisionは62、共有config hashは現在の `42fa0496c05567620998cb9e9de6134408050f83f8a767b56ccc53dbd8800b3b` と一致している。従って、このhashが維持されればWFの通常v9送信は今回のFL-07と同じ理由では止まらない。FL-07の元job revisionは52、元hashは6bd060…であり、両taskの証拠を混同しない。新task自身のcommit proposalも42fa0496…を束縛することを作成時に検証する。

今回の承認対象config hashは42fa0496…に固定し、prepare、承認待機後、execute直前、WF通常v9送信直前、新taskのcommit準備直前・送信直前で再確認する。作業中はCLIのみを使用し、当該cloneのVS Code Git UIでbranch作成・checkout等を行わない。さらに共有configへ書き込むCLIも禁止する。具体的にはgit configの書込み、push -u/--set-upstream、branch --set-upstream-to、追跡設定を作るremote refからのcheckout/branch、worktree add --track、gh repo set-default等を行わない。新task branch fix/v9-git-env-recoveryはlocal commit2a2fd3cから追跡設定なしで作成済みであり、for-each-refのupstreamが空であることを読取り確認する。元Rのexecute_actionの通常feature送信は固定URLとHEAD:feature refだけを指定しており、-uやupstream設定処理がないことを同コードで確認する。実コードで追跡設定を書き込む経路が見つかった場合はX4で停止する。branch作成や既存branchの追跡設定を繰り返さない。AIはVS Codeや個人設定を変更しない。人や他セッションによる追加書込みでhashが変わった場合は、復旧規則を自動拡張せず停止して所有者へ差分を提示する。追加branch節のvscode-merge-base行も拒否する。設定を往復させて既存承認へ合わせない。

## 選択した方法

元runtime `169642d0c8040e24e048ee5f04777345e5242016` は読み取り専用で保持する。runtimeを差し替えると既存四段階承認のruntime digestが変わるため、今回の復旧には使わない。

FitLogの別branch/worktreeに、明示的な公開復旧controller `bin/ai-dev-git-env-recovery` と限定hook入口を追加する。新controller自身のコード、launcher、設定は独立レビュー後にcommitし、実行時はそのcommitとraw byte一致を要求する。既存のv9 commit結果を新環境下で「通常commitを再実行した」と見せる標準resultは生成しない。別schema/namespaceのticket/intent/resultを作り、旧承認済みcommit＋新しい環境確認＋実送信の連鎖として区別する。

これは通常v9の検査を無効にするrunnerではなく、今回の設定差分を正規TTYで再確認する追加の承認操作である。通常v9の2形式と既存の拒否契約は維持する。WF-PARALLELの先行公開条件は、FL-07の元の正規commit結果にこの復旧の成功連鎖とremote SHA確認が追加される場合に限り満たしたと扱う。この代替条件は今回の追加設計の明示的変更点である。

他案: configを一時的に旧hashへ戻す方法、標準commit resultの複製/編集、legacy検証のmonkey patch、runtime digestを据え置いたコード差替えは採用しない。全config fingerprint検査の除外も行わない。

## 公開インターフェース

Sはこの復旧taskのcommit済みworktree root、Pは同一cloneの対象worktree、Jは元の成功commit proposal、Kは新ticket。全パスは絶対・正規化済みで、末端symlinkを拒否する。

1. `S/bin/ai-dev-git-env-recovery prepare --commit-job J --project P --remote origin`
2. `S/bin/ai-dev-git-env-recovery execute K --project P`
3. `S/bin/ai-dev-git-env-recovery prepare-pr --delivery-result D --project P --base main --title TITLE --body-file BODY`
4. `S/bin/ai-dev-git-env-recovery status --delivery-result D --project P`（元承認/復旧全連鎖/remote SHAの読取り照合のみ）

prepareは確認用ticketだけを作る。executeは正規TTYでaction、repo/account、旧commit/tree/parent、旧/新fingerprint、許可差分、immutable SHA refspec、remote観測を表示し、`APPROVE ENV-RECOVERY <ticket-prefix>` を1回求める。ticket-prefixはticket_digestの先頭16文字の小文字hexとし、input()で読んだ1行を期待文字列と完全一致で照合する（行末newlineを除き、前後空白のstripや大文字小文字変換はしない）。余分な文字・空白・別prefix・control文字・EOFは拒否する。PR ticketは別途の最終承認を受けた内容に限り `APPROVE ENV-RECOVERY-PR <ticket-prefix>` を同じ16hex/1行/完全一致の規則で求める。パイプ入力は拒否する。今回の自動実行範囲はfeature送信までで、PR作成やmergeの包括許可にはしない。

launcherの形式は、shebangを `#!/bin/bash -p` に固定し、profile/ENV/BASH_ENV/環境からの関数/SHELLOPTSを取り込まずに開始する。処理は、(1)builtin compgen -eでexport済み変数名だけを列挙、(2)下記の危険な変数名をbuiltin caseで検出したら値を読まず固定診断で終了、(3)危険名がなければbuiltin execから `/usr/bin/env -i` で次の固定Pythonと閉じたenvを起動する、に限定する。eval/source/任意commandの実行や外部shell startup fileを許可しない。新hookは、agent sessionのprocess.envに実際に存在する危険名をlauncher起動前に拒否する。agent開始前にOSが除去した名前をhookが検知できるとは主張しない。

launcherは絶対path `/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12` のisolated/no-site/no-bytecode起動で当該scriptのみを呼び、PATH探索をしない。env -iへ渡す値は固定PATH/個人HOME/CODEX_HOME/TMPDIR/localeと固定Python -I -S -B、当該S内script path、元のquoted引数だけである。HOMEはこの個人環境の `/Users/saki` とし、controllerがOS user recordと一致することを検証する。hookまたはlauncherが観測できる危険名はenv -iで消す前に固定診断で拒否する。観測して停止したセッションを自動unsetして再実行しない。一方、OSが除去するDYLD_*等、または-pが無効化して列挙に現れない関数名/optionは、固定診断の対象にはできない。これらはstartup/関数/loaderコードの不実行と子envへの非継承を別オラクルで検証する。safeな親環境の余分な値は継承しない。このホストの実体はregular file、UID0/GID0（root/wheel）、mode0775、SHA256 `80ee2dd97bc26259d4e30853336f72ad38aa4aa0531bb196cc444d899422689d` であり、このleafのpath/metadata/hashをhookとcontrollerが照合する。OSのroot/wheel管理下のgroup-write bitはこの一致する実体に限って許可し、別owner/group/mode、world-write、symlink leaf、path/hash不一致は拒否する。一般runtimeのcurrent-user-owned/no-group-write規則をOS Pythonへ誤適用しない。

Pythonのleaf hashは起動先の取り違え・偶発変更を検出するためのもので、実行されるframework dylibやstdlib全体のコード同一性、改変コードからの安全境界を保証しない。OSとPythonインストールは既存v9と同様にホスト側の信頼前提とする。framework本体とstdlib moduleの完全なhash固定を今回の追加機能として実装しない。この限界を採用reportにも明記する。読取り実測では、leaf、bin、Versions/3.12、VersionsはUID0/GID0/mode0775、Python.framework・Frameworks・Library・/はUID0/GID0/mode0755、framework dylib Pythonとstdlibディレクトリlib/python3.12はUID0/GID0/mode0775であった。採用時にこのowner/gid/modeを再確認し、gid80(admin)やworld-write、symlink ancestry、その他の観測差があれば停止する。root/wheel管理下のgroup-writeとホスト管理者が変更できるリスクは明示的に信頼前提として受け入れる。これを、repo内controller/runtimeのraw-byte固定と混同しない。任意command、env、runtime、module、home、task/state pathの指定は受けない。Rは既存のclosed registry `.ai-dev/v9-git-entrypoints.json` から選ぶ。新しいclosed config `.ai-dev/v9-env-recovery.json` はschema1/repo/account/許可metadata規則のみ。hookとcontrollerの両方で未知field、duplicate key、不正型を拒否する。

## 元の承認連鎖の読み取り専用検証

元Jをcanonical HOMEの既存private Git ledgerから読み、正規path（project/task hashとproposal digest）、所有者・regular file・0600・private parents・閉じたschema10・result_digest・proposal_digestを確認する。成功commit resultのaction/evidence/schema/status/filenameも元runtimeの契約に一致させる。任意JSONをcommit証拠として受け付けない。

fresh isolated subprocessで、元Rのsourceをimport前に固定Git tree/index/実バイトで検証する。runtime_digestとpolicy_digest、対象Pが選ぶreview-budget hookのdigestを元workflowに照合する。source-only loaderでfingerprint対象の旧v9/harnessのみを読み、pycache/別moduleを採用しない。既存検証APIの読み取り専用部分だけを使用し、`_workflow`、`_sync`、state save、approval生成を呼ばない。

四receiptはhuman_approvedであり、現在のbindingと整合し、元jobのbinding_digest/revisionと現在stateが完全一致すること。直近の保存handoffに基づくfresh `_inputs` とstate.bindingを比較し、実在のchecks/execution_readyも検証する。元仕様・計画・design判定・runtime/policy/route/checks・branch/task/snapshotが変われば拒否する。

元commitのSHAは現在HEADと一致、branchは現在の名前付きfeature、単一parentとtreeは元結果およびreplace無効の `git cat-file commit <SHA>` のraw commit objectに一致（tree行とparent行が厳密に1つずつあることを検証）、indexはplain、Git-visible変更なし、missing_pathsを含むsnapshotは元proposalに一致すること。元Jのpersonal_environmentと現在の差は後述の1箇所以外は一致が必要。

## 許可するGit設定差分（狭い復旧条件）

現在の個人profile/account/gh_config_dir/git_config_file、configファイル一覧と順序、各パス、共有config以外の全hashは元Jと一致させる。共有configはsame Git common directoryの実ファイルだけを対象にする。gitdir/worktree configを共有configに取り違えない。

許可規則は、唯一の完全なheader bytes `[branch "main"]\n` 以降、次のsection headerまたはEOFより前の範囲に、元は存在しなかった完全なraw line bytes `\tvscode-merge-base = origin/main\n`（先頭tab1個、指定の空白、LF終端を含む）が1回追加されている場合のみ。行の位置は当該節内でよいが、別の空白形式・CRLF・BOM・改行なしは許可しない。section/keyの重複、不正UTF-8、改行形式変更、他節に新しく追加/変更された同key（追加branch節のvscode-merge-baseも含む）、include/remote/URL rewrite/credential/sshCommand/hooksPath等を含むその他の変更は拒否する。現在のraw bytesから当該1行だけをメモリ上で除去したraw bytesのSHA256が元Jの共有config hashに一致することを必須とする。元configの全内容が保存されていなくても、この逆変換hashで「その他の変更なし」を確認できる。元と現在が同一ならこの復旧入口は不要として拒否する。元から他のbranch節に存在するvscode-merge-base行は削除も禁止もせず、そのままのraw bytesを逆変換hashへ含める。拒否するのは復旧規則外の新しい差分である。

Gitは必ず既存PersonalGitEnvironmentから個人profileを選択し、現在のorigin fetch/push設定値・実効URL・repo・accountを元commit proposalの唯一のGitHub remoteと照合する。実効URLの変更は上記hash条件に加えて拒否する。raw-byte確認に加え、現在bytesとメモリ上の逆変換後bytesを、空scratch/固定envの `git config --no-includes --file - --null --list` でそれぞれ解析する。追加keyがbranch.main.vscode-merge-base=origin/mainとして意味的に1回だけ増え、その他のkey/value集合が同じであることを確認する。旧subsection表記・headerと同じ行のkey・section名のcase違い等がraw規則やこの意味的対応に合わなければ拒否する。REC-AC1でこれらの境界を検証する。全段階の子process環境は下記の許可リスト契約から新規に構成し、Git repository-selection/設定注入/SSH/認証上書きを継承しない。replace refsを無効にし、任意の環境一覧やtokenは記録しない。`GIT_GRAFT_FILE` は拒否・非継承とし、PとRのGit common directory下 `info/grafts` が存在する場合（空file/symlinkを含む）も拒否する。

## 子process環境の閉じた契約

既存 `PersonalGitEnvironment.load` の `_base`（元Rのgit_environment.pyの_base）はすでに許可リストからenvを構成し、runnerは渡されたenvを個人profile由来のdictで置き換える。したがって、このAPIを通る通信が親のGH_TOKENやGIT_SSH_COMMANDをそのまま継承するという説明は実コードには当たらない。ただし、新controller自身の全段階も同じ原則に統一することを、独立した契約として明記する。

すべての新controller子process（ローカルmetadata・固定Pythonのisolated verifier・個人config構文検証・account/remote読取り・実送信・PR作成）は、`dict(os.environ)` を使わず新規dictでenvを組み立てる。固定PATHは `/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin`、HOMEはOS user recordと一致するcanonical personal HOME、CODEX_HOMEはその`.codex-personal`、TMPDIRは固定`/private/tmp`（scratchはowned0700/O_EXCL）、LANG/LC_ALLは`en_US.UTF-8`とする。Git/ghの起動先はこのホストで読取り確認した `/usr/bin/git` と `/usr/local/bin/gh` を使用する。legacy API内部の`git`起動もsanitized child PATHの先頭/usr/binへ解決される。PATH/command本体はOSの信頼前提であり、ホスト上の全binaryのimmutabilityは保証しない。

local verifierでは `GIT_CONFIG_GLOBAL=/dev/null`、通信段階では元RのPersonalGitEnvironmentが確認した個人`git_config_file`と`gh_config_dir`だけを `GIT_CONFIG_GLOBAL`/`GH_CONFIG_DIR`として使う。どちらも `GIT_CONFIG_NOSYSTEM=1`、`GIT_NO_REPLACE_OBJECTS=1`、`GIT_OPTIONAL_LOCKS=0`、`GIT_TERMINAL_PROMPT=0`、`GIT_NO_LAZY_FETCH=1`を固定する。legacy `_inputs`内部のenv構成も上記sanitized workerの環境から始まり、元APIがOS環境を再利用する場合の値も閉じている。legacy実装をpatchして検証を通すことはしない。

prepare/execute/status/prepare-prの公開入口では、hookがagent sessionのprocess.envで観測する次の名前、またはlauncherがcompgen -eで観測する次の名前を、値を表示せず固定診断で拒否する: `GIT_CONFIG_PARAMETERS`、`GIT_CONFIG_COUNT`、`GIT_CONFIG_KEY_*`、`GIT_CONFIG_VALUE_*`、`GIT_CONFIG`、`GIT_CONFIG_GLOBAL`、`GIT_CONFIG_SYSTEM`、`GIT_SSH`、`GIT_SSH_COMMAND`、`GIT_ASKPASS`、`SSH_ASKPASS`、`GIT_EXEC_PATH`、`GIT_GRAFT_FILE`、`GH_TOKEN`、`GITHUB_TOKEN`、`GH_HOST`、`GH_CONFIG_DIR`、`BASH_ENV`、`ENV`、`SHELLOPTS`、`BASH_FUNC_*`、`DYLD_*`、`LD_*`、`PYTHON*`、`VSCODE_GIT_ASKPASS_*`。拒否対象の変数は子envへ渡さず、選択profileの設定値だけを後段で構成する。OS metadata用の固定flags以外の任意GIT_*、GH_*、SSH_*、Python module/search-path上書き等も子envへ渡さない。CODEX_HOME/HOMEも別環境へ付け替えず、不一致は停止する。

REC-AC2の起動オラクルは次の段階に分ける。

- hookのprocess.envに危険名を注入したfixtureは、公開入口を起動する前に固定診断で拒否する。これはagent sessionに存在する名前の検証で、OSによる除去前の環境を観測できるとの主張ではない。
- 実際のlauncherでcompgen -eに現れる危険名（通常のGIT_*/GH_*/PYTHON*/LD_*/ENV/BASH_ENV等）は、Python/controller/送信の開始前に固定診断で拒否する。SHELLOPTS/BASH_FUNC_*もそのホストで見える場合は同様に拒否する。
- OSに除去されるDYLD_*や、-pで無効化されて列挙されない形式の関数/optionには、固定診断や終了codeによる拒否を要求しない。startup script、環境関数、loader constructorにowned scratch markerを作る独立したprobeを使い、コードが実行されないことと、env -i後の子argv/envへ当該名が渡らないことを検証する。これらの条件で子observerが開始すること自体は失敗ではない。実通信は閉じたenvからしか開始しない。

SHELLOPTSとBASH_FUNC_*を常に不可視と決め付けず、観測可能性と実行無効化を別に確認する。実際の子argv/envを採取し、全段階でallowlist以外の継承がないことをassertする。テストはfake値/fake HOME/temporary repoだけを用い、実credential値を読み出さない。source-only検証用の内部workerも、公開入口から作った閉じたenv以外を受け取らず、任意command/envを入力JSONやCLIで指定できない。

## 新しい記録・競合・中断

元ledgerのtaskディレクトリ下の新namespace `environment-recoveries/<original-commit-proposal-digest>/` を使用する。既存proposal/result/stateは読取りのみ。新記録はprivate0700/0600、owned/non-symlink/size-bound/duplicate-key拒否、atomic no-overwriteで公開する。ticketには元job/result/state/receipt束縛hash、旧/新personal_environment、許可差分の名前とhash、SのHEADとtool/config hash、P/task/branch/commit/parent/tree、repo/account/remote/refspec、remote観測を含める。credentials、config本文、provider/source本文は含めない。

元commit proposal単位のOS lockをprepareとexecuteで取る。元task内の通常push intent/resultや同commitに関連する既存復旧intentも確認し、running/unknown/未解決は拒否する。新executeのintentは送信開始前にdurableに記録する。新ticketは一度限り。created_atとexpires_atをdigestに束縛し、有効期限は作成から15分、期限切れ・未来の作成時刻・不正な期間はexecuteで拒否する。準備・承認待機・直前確認のいずれかでsource/config/HEAD/state/remoteが変われば実行しない。制御workerはPID/PGIDを追跡し、timeout/interruptでは所有するprocess groupを停止・確認する。

起動失敗が確定した場合だけfailed。起動後の非zero・timeout・中断・結果保存失敗・post-readback失敗はunknown/未解決とし、成功を捏造しない。自動retryやintentの自動解決は実装しない。unknown時はX7として停止して本人判断を求める。本設計にはunknownを解決する操作は含めない。結果保存だけが失敗してremoteが同SHAであってもstatus/後続公開ゲートは閉じたままとし、必要なら別途承認された追加設計で、新namespaceにTTY付きresolution recordを追記する経路を検討する。既存intent/resultの編集や、未実装の解決経路が使えるとの主張はしない。過去の失敗/消費枠は保持する。

## 実送信とPR

prepare時点で対象refを読み、未存在なら送信ticket、すでに正確な承認SHAならobservation-only reconciliation ticketとして明示する。異なるSHAなら拒否する。準備とexecute直前で観測が変わった場合も拒否する。最後のls-remoteと送信の間は原子的ではない。非force送信は第三者がその間に作った祖先refをfast-forwardできるため、refの不在が送信の瞬間まで保証されるとは主張しない。force/force-with-leaseは使用しない。Gitの通常の非force更新規則と送信後の最終SHA照合を保証範囲とし、観測できた不一致はunknownで停止する。一時的なref変更が最終的に同じSHAへ収束した場合まで検出できるとは主張しない。送信は元commit SHAを固定した `<approved-SHA>:refs/heads/<feature>` の非forceのみ。可変HEADを送信元にしない。送信後、originの該当refが当該SHAであることと元承認束縛の不変を再確認して新resultを記録する。観測だけの完了を送信成功と表記しない。

PRはこの新ticket/intent/resultの完全連鎖が成功し、元commit＋四receipt＋現在の束縛も一致する場合だけ別ticketを作る。通常v9の成功push resultを偽装しない。PRのbaseはmain、headは対象featureに固定、body hashとtitleも承認束縛し、実行前にremote SHA確認。既存PRは同repo/head/SHA/baseなら観測のみ、異なる/曖昧なPRは拒否。作成後はrepo/head ref/SHA/base/URLを照合し、不一致はunknownとして自動closeしない。GitHubのbranch-based PR作成にSHAを原子的に固定できるとは主張しない。

## WF先行公開条件の判定者と証拠

元Rの `scripts/v9/gitops.py` の `prepare_action`（action == "push" 分岐）と `execute_action`（action == "push" 分岐）を実読取り確認した。Rはその対象P/taskの成功commit結果、現在のworkflow/四receipt・branch/HEAD・personal_environment、remote/accountを検証する。別taskであるFL-07のpush result、remote ancestry、先行公開順は照会しない。従ってWFの通常v9送信が、FL-07に標準push resultがないことを技術条件として拒否する構造ではない。Rを変更したり標準push resultを生成して通す必要はない。誤解を避けるため「Rがremote ancestryだけを見る」とも記さない。Rはcross-task先行公開を判定していない。

先行公開は元WF設計の運用上の追加条件であり、親coordinatorがこの追加承認された復旧契約に基づいて判定する。復旧branch内の `documents/development/personal-parallel-workflow.md` へ、(a)元FL-07成功commit job/resultと四receipt、(b)今回のreview済みcontrollerによるticket/intent/success result全連鎖、(c)個人profileのorigin/feat/fl-07-timelineのremote SHA=0d23433、の3証拠を確認する手順を明記する。mutableな実path/hash/確認時刻はsource外reportとPR本文に記録する。

判定用の読取り専用collectorは新controllerの内側に置き、公開 `status --delivery-result D --project P` でこの連鎖とremote SHAを再検証する（ticketや新承認は作らず、送信もしない）。WFの通常v9 git-actionの直前にcoordinatorがこのstatusを呼び、不一致/欠落/unknownなら送信しない。native実行sessionも同じ手順を守る。このcross-task条件は旧Rやhookで技術的に強制されるものではなく、coordinatorが守る運用上のゲートである。WF送信直前のstatus出力からdelivery-result digest・remote SHA・観測時刻をsource外reportへ記録し、PR本文で照合する。これは機械強制された依存関係だとは報告しない。仮に実コード/fixtureでRがFL-07標準push resultを要求することが見つかった場合は、正常送信を約束せずX4として停止する。forceや標準結果の偽装で補わない。

元WF worktreeの固定source、manifest/plan、private approval/state、commit2a2fd3cは変更しない。本branchに追加する運用文書とsource外実行記録だけが、今回承認する先行条件の代替を示す。旧helper `/private/tmp/wf-verify-app-publication.py` は標準push resultだけを要求するため、復旧後の証拠として呼び続けない。新status collectorへ置き換えることを明示し、既存helperの失敗を無視しない。

## hook受付と採用

旧v9のA/B入口と旧classifier本体は変更しない。新入口のcandidate検出は汎用early-passより前に置く。line continuation/escapeを既存v9Potentialと同じ規則で折り畳み、既存lexerの語とcommand区切りを用いて実行位置を識別する。candidateは、commandの実行語のbasenameがlauncher名 `ai-dev-git-env-recovery` またはscript名 `v9_git_environment_recovery.py` と完全一致する場合、あるいはPython等のinterpreter・shell・env/command/nohup/timeout等の既知wrapperが実行対象としてその語を渡す場合に限る。Pythonの-mで当該moduleを実行する既知形式と、shell -c内の当該tool起動も対象にする。単なる部分文字列検索にはしない。相対path・同名symlink・別worktreeの起動も実行位置で検出し、正規入口以外は拒否する。candidateを検出したら、S内の正規絶対launcherによる公開4形式（prepare/execute/prepare-pr/status）のBash/POSIXだけを閉じた文法で解析し、その他はconfig不在を含めて拒否してlegacyへfallbackしない。candidateに該当する任意wrapper/追加env/option/command、trunk/force・別repo・別clone・不明形式を拒否し、拒否時にlegacyへfallbackしない。prepare-prのtitle/bodyもtokenとして一意に解釈できる形式に限り、shell展開・substitution等を通さない。

Sはロードされたhookのworktree、payload.cwdはS内。Pは同common Gitとし、採用前にS/FL-07/WFの実git-common-dir一致をsource外collectorで確認してevidence.jsonへ記録する。不一致ならX4で停止する。P=Sは新復旧laneでは拒否する（新task自身の送信は旧Rの通常v9経路だけで行う）。両hook、旧registry、新registry、launcher/scriptはS.HEADのraw blobとdiskを比較する。新controllerのdata/code以外をcommit状態確認の対象から漏らさない。旧Rのpurityは既存のv9Runtimeと同等の固定tree/index/raw-byte/mode確認を再利用する。hookでのR確認は、実行開始前に入口の登録先を確認するためであり、controllerがimport直前に再確認することとの二重化は意図したものである。controllerが任意Rを選択できるという意味ではない。新入口のhookも最大8 Git calls/各2秒/全体12秒の既存時間枠を維持する。計画する呼出しは、(1)Sのrev-parse metadata、(2)Pのrev-parse metadata、(3)Pのsymbolic-ref、(4)Rのrev-parse identity、(5)Rのls-tree、(6)Rのls-files --stage -v、(7)S.HEADの6ファイルを1回のbinary cat-file --batchで読む、の7回。P=Sは拒否なので正常受付ケースの呼出しは常に7回。Sの6ファイルは両hook・旧registry・新registry・launcher・script。hookではlauncherのowned regular disk file・owner実行bit・group/world-writeなし、scriptのowned regular・owner実行bitなし・group/world-writeなしをFS metadataで確認する。Git modeはquality-checkとcontrollerの自己検証でS.HEADのls-treeを読み、launcher100755/script100644を確認する。hookへの追加Git callは不要で、7回の枠を保つ。branch/HEADは既取得metadataを再使用し、追加Git statusを呼ばない。新hook回帰で呼出しargv/count/各timeout/global deadlineを検証する。

hookとcontrollerのpath責任を分ける。hookはJ/K/D/BODYすべてについて絶対・正規化済みのpathと末端non-symlink regular fileを確認する。Jは既存private Git ledgerの正規commit proposal path、Kは同taskの `environment-recoveries/<original-commit-proposal-digest>/ticket-<ticket_digest>.json`、Dは同namespaceの `ticket-<ticket_digest>.result.json` に限定し、canonical HOME配下のowned0700 parentsとowned0600 file、最大1MiB、duplicate key/閉じたschemaを検証する。K/Dのproject/task/元commit-jobのcanonical identityとPの一致もhookで照合する。BODYは最大64KiBのowned regular UTF-8 fileとし、canonical絶対path・symlink leaf拒否を検証する（private ledger内である必要はない）。

controllerはこのpath条件を再確認したうえで、proposal/result/ticketの全digest、元state/四receipt/runtime/policy/route/checksの一致、TTL/一度限り実行/lock/未解決intent、remote/account/実効URLとBODY hashを検証する。hookだけで承認連鎖全体を検証したとは主張しない。新hook回帰はK/Dのnamespace外・相対/非正規・symlink・unsafe parents・不正size/schemaと、BODYの不正path/size/ownerを拒否する。bytecode/cacheを作らない。

trust/registrationは変更せず、commit後の実Codex Bash hook実行でSのcwd/gitdir/script/config/commit raw bytesの一致を採取する。fixture payloadやstatusだけをnative採用成功とは扱わない。Claude native clientは未実施ならnot_runとする。

実行位置でないファイル参照はcandidateにしない。具体的に `git diff -- scripts/v9_git_environment_recovery.py`、`git add -- scripts/v9_git_environment_recovery.py`、cat/rgでの読取り、`python3 -I scripts/test_v9_git_environment_recovery.py` および当該testのunittest起動は新laneでは非対象とし、既存classifierの判定を保つ。新回帰はこれらを正例にし、直接Python/相対launcher/同名symlink/bash wrapper/別root launcherを負例にする。git addや読取りを一般allowlistで無条件許可せず、今回の検出との境界だけを検証する。

意図的にlauncher/scriptを別名コピーし、変数・stdin・別マシン等で隠して起動する攻撃は既存hookと同じ静的分類の対象外であり、検出可能とは主張しない。自己検証だけを改変コードからの安全境界とせず、既知の公開入口/直接起動はhook側がcommit済みbytesと照合して拒否する。statusもread-onlyであることをcontrollerテストで検証し、未知actionは拒否する。

## 変更予定の範囲

- 新規: `bin/ai-dev-git-env-recovery`、`scripts/v9_git_environment_recovery.py`、`scripts/test_v9_git_environment_recovery.py`、`.ai-dev/v9-env-recovery.json`。
- 既存: `.claude/hooks/quality-gate.cjs` と `.codex/hooks/quality-gate.cjs` の限定入口。新回帰は別ファイル `scripts/test-quality-gate-env-recovery.cjs` に追加し、旧 `scripts/test-quality-gate-v9.cjs` は変更しない。
- 文書: 本設計、`documents/development/personal-workflow.md` の正規復旧例外、`documents/development/personal-parallel-workflow.md` の復旧記録・公開順、`skills/project/quality-check/SKILL.md` の入口契約。
- task: `.ai-dev/wf-git-recovery.spec.json`、`.ai-dev/wf-git-recovery.plan.json`。

製品コード、DB、CI、Compose、依存、登録11checks、hook登録、旧R、旧2worktreeのtracked fileとprivate承認は変更しない。追加unit/hook検証は既存11checksとは別の実結果として記録する。

## 受入条件とテストオラクル

REC-AC1: 手書きの旧/新config raw bytesを使い、唯一のmain節の完全bytes `\tvscode-merge-base = origin/main\n` 追加だけが成立する。先頭空白/tab数/`=`前後空白/LF/節位置の各境界を固定し、元から他節に存在する未変更metadataは保持できる。remote/credential/includeの追加、同key重複、他section、CRLF/BOM/末尾変化、別config/owner/mode/symlink、未知schema・duplicate keyは拒否する。旧hashを自動計算し直して改ざんを通す期待値は作らない。

REC-AC2: 子process envのallowlist・固定argv、観測可能な危険名の固定診断による拒否、不可視/無効化名のstartup・関数・loader不実行と子env非継承、graft file/環境上書きの拒否とraw commit parent/tree解析を検証する。元commit/job/result/state/receipt/source/runtime/parent/tree/snapshotの各改ざん、stale revision、plain-index違反、pyc/別module、replace refs、Git環境上書き、account/origin/実効URL変更、trunk/別cloneは拒否する。実Rと同commitの使い捨てcheckoutでsource-only検証とno-pycacheを確認し、実private状態はfixtureに流用しない。

REC-AC3: 正常prepare→TTY確認→execute→remote SHA、既存同SHAの観測専用、異なるSHA/承認中の変化は拒否。immutable SHA送信で、prepare後のHEAD差替えは送信前拒否し、送信中のHEAD差替えでも別commitは送らない。fake transportと実一時bare repoで独立期待値を持つ。元record bytesが全て不変であることをbefore/after比較する。

REC-AC4: 期限切れ・未来時刻・非TTY・16hex以外/余分な前後空白/別prefix/control/EOF等の間違った確認・ticket再利用・parallel lock・timeout・child group残存・結果保存失敗・post-readback失敗では成功を作らず、実行後不明は自動retryしない。PRは別承認、完全成功連鎖、既存一致/不一致、作成後raceを確認する。

REC-AC5: 旧回帰ファイルはbaseline2a2fd3cのraw SHA256 `f584bb41e5d84b94fe1601279a7970f3e7d85658ebf29985f88c29a1f06434aa` とbyte一致を保ち、元fixtureは `scripts/fixtures/v9-push-proposal.json`（raw SHA256 `d0ba9c5c3f8f3c572b0ba5d643ca6a281416581003ffe01463c87a0edff53344`）と `scripts/fixtures/v9-push-provenance.json`（raw SHA256 `8a99bd80c32608bf2aaa3741f0cd00db5343d75fc56461a6eff23369ebf708e4`）で、いずれもbaseline2a2fd3cのraw blobと一致させる。件数だけで置換を検知したとは主張しない。新hook入口の正規/不正期待値と旧回帰全件を維持し、main/master/force/未知runnerを許可しない。両コピーのBuffer.equals、commit blob一致、実native採用を確認する。直接Python実行、相対launcher、symlink launcher、bash wrapper、別worktree launcher、改変済み/未commit controllerの既知起動形式は拒否する。固定Pythonのpath/owner/group/mode/hash不一致も拒否する。受付の新規コードhash不一致や未commitは拒否する。

REC-AC6: 登録11checks（変更後1回、共有runtime lockの下）・追加Python unittest/Node回帰・構文/byte parity/diff/scope検査を通し、独立品質レビューを行う。新taskの正規v9四receipt/Issue/commit後、native採用→FL-07復旧送信/remote0d23433→WF通常v9送信/remote2a2fd3c→新復旧taskの通常v9送信、の順とする。新taskのancestor先行公開は実proofで検証する。PR作成は最終個別承認、GitHubのmergeは本人のみ。

## 実行とレビュー予算

親が直接実装する。設計レビューはpublic v9のdesign_review 1回を基本とし、同じ設計を別のdesign reviewへ重複提出しない。追加が必要なら理由・残存指摘をまとめて確認する。実装中のper-taskレビューは行わない。

機械検査後のquality-checkは統合・反証QA・Securityの1巡を基本とし、必要時だけ単独検証reviewer（条件付きQA）へ進む。別providerのv9 reviewは必須の承認段階として1回を予定する。既存FL-07/WFのレビューを再実行せず、過去の消費枠を新branchへ移してリセットしない。新branch予算は今回の新機能差分のためだけに使用する。総当たりのレビュー追加は行わない。

初回の設計・計画承認以後の実装/検証/Issue/commit/feature送信と、それに必要な正規TTY入力はcodex-owner-delegatedの限定委任を求める。新taskのdesign承認前は四receiptを生成しない。PRは最後に具体的内容を示して個別承認、mergeは人間のみ。mutationは未導入、製品UI変更なしのためブラウザE2Eは提案せず、CLIの実採用・実結果を完了条件とする。


## 読み取り検証APIの具体的契約

登録checksの実行可否を設定から確認することと、checksを実行することを区別する。復旧controllerは `run_declared_checks`、provider adapter、v9 handoff/execute_reserved、Docker、build/test runnerを呼ばない。既存結果は `workflow.latest_evidence(state, "implementation")` が選ぶ、元四receiptに束縛された最新成功attemptのevidenceと保存job/resultを検証する。古い成功結果を失敗済みの後続attemptの代わりに選ばない。今回FL-07はverify-5、WFはverify-3の既存証拠であり、復旧中にそのchecksを再実行しない。新task自身の登録11checks実行は別工程・共有runtime lock下で1回行う。

元runtimeの呼出し範囲:

| API | 実際に起こる処理 | 永続書込み/外部副作用 |
| --- | --- | --- |
| `controller.runtime_digest`, `_tree_digest`, `selected_review_hook` | runtime/policy/hookのowned source bytes読取りとhash | なし |
| `WorkflowStore.load`, `workflow.latest_evidence`, `is_ready_for_git`, `gitops._require_workflow` | 既存state/schema/receipt/最新保存evidenceの検証 | なし。create/save/update/approveは呼ばない |
| `gitops._load_job`, `handoff._validate_job`, `workflow_job_path` | private JSONと固定path/schema/digestの検証 | なし |
| `controller._inputs` | config/spec/plan/sourceの読取り、routesと各digestの再計算、branch/HEAD/parent/treeとsnapshotのGit metadata読取り | 永続書込みなし。下記の読取りGit subprocessはある。checks/providerは起動しない |
| `config.resolve_project_config`, `spec.validate_plan`, `execution.execution_digests`, `harness.load_model_routes`, `load_design_route` | 上記_inputsの内部でTOML/JSON/sourceを読んで検証/hash | なし。execution_readyは設定に実コマンド登録があるという値であって成功結果ではない |
| `PersonalGitEnvironment.load` | 個人profile/config読取り、configのGit構文検証、private ghファイルのmetadata検査 | HOME/ledgerを書かない。TMPDIR内に空の一時ディレクトリを作成し、下記git config stdin検証後に削除する |

`_inputs`はread-onlyだがsubprocess-freeではない。設計レビューの「子processを1つも起動しない」という提案はそのまま採用せず、許可する読み取りGitとchecks/provider起動を明確に分ける。内部のGitは、branch --show-current、rev-parse（toplevel/HEAD/tree）、rev-list --parents -n 1、ls-files --stage -z --cached、ls-files -z --cached --others --exclude-standard、である。PersonalGitEnvironmentの構文検証は空scratch内の `git config --no-includes --file - --null --name-only --list` のみ。旧snapshotの_git_environmentはGIT_OPTIONAL_LOCKS=0、global/system configを無効化している。controller自身のmetadata readはGIT_NO_REPLACE_OBJECTS=1とGIT_OPTIONAL_LOCKS=0で実行する。_inputsが参照するcommit tree/parentはcontrollerが同じSHAをreplace無効のplumbingでも別照合する。

Git-visible変更の確認に `gitops._changes` のstatusは使わない。normal stage-zero indexをHEAD treeと比較し、raw-file snapshotと未追跡ファイル列挙を照合する。これによりstatusのfilterやindex更新を読み取り検証へ持ち込まない。`gitops._matching_result` はこの意図的なenvironment差分で拒否する元APIなので呼出し/patch/偽runnerで通過させず、明記した各元commit不変条件を新controllerで検証する。

account照合とremote観測は上記のローカルlegacy検証から分離し、現在のPersonalGitEnvironmentを用いた固定argvのremote get-url/config読取り、ghの認証account確認、git ls-remoteだけを許可する。ネットワークがあるのはこの明示したidentity/readback段階と、executeの承認後の実送信/PR作成だけ。controllerの子processは段階別の許可argv以外を拒否し、任意commandを実行できるpublic引数やcallbackを提供しない。

追加テストではfake HOME/ledger/stateと使い捨てrepoについてbytes/mtime/ファイル集合（index含む）のbefore/after一致を検証する。ローカルlegacy検証の全subprocess argvを採取し、上のGit readとisolated verifier process以外が0件、特にchecks・Docker・provider・networkが0件であることをassertする。scratchは作成/削除先をTMPDIR下に限定し、HOME/ledger/stateへ書かないことをassertする。純粋なschema/digest/evidence検証単体ではsubprocessそのものが0件であることも別にassertする。実credential/private承認に対してはテスト用patchや偽装を適用しない。

## 設計上の根拠

WFの成功commitは現在の共有config hashに束縛されているので通常v9経路を保持する。FL-07だけは旧hashからの限定復旧を必要とする。追加の設定driftは自動許可せず停止する。元runtimeの検証APIは既存結果の読取りを行い、checksやproviderを再実行しない。期限付きticket・mainだけのPR base・固定したhook Git call予算・変更しない旧回帰suiteを採用し、実行時の異なる責任を混同しない。

レビュー結果・時刻・消費枠・承認は本書へ追記せず、正規stateとsource外の実行記録へ保存する。設計合格と実送信成功は別の証拠として示す。


## レビュー用の読取り根拠と採用前確認

レビューproviderがプロジェクト外の元runtimeやprivate stateを読めない場合、権限を広げたり会社/認証領域を探索せず、このworktreeのignored `docs/superpowers/plans/wf-git-recovery-evidence/README.md` を入口にする。`evidence.json` は元commit jobと現在stateのrevision/binding/runtime/policy/四receiptの照合、branch trackingなし、共有config hash、環境変数名の診断を記す。`runtime/*.py.txt` は登録Rの実bytesを固定169642dのGit blobと比較した読取り参照コピーで、hashを同JSONに記録する。`prior-findings.json` は過去の正式な全指摘と不合格判定を保持する。これは承認や実装成功を示す記録ではなく、元private state/job/resultの編集を含まない。参照copyを実行用runtimeとして使わない。

FL-07の現在state revision52、元commit job revision52、binding_digest一致、現在HEAD0d23433、WFのstate/job revision62と共有config42fa0496…の一致を、この読取りcollectorで実装前に確認する。いずれかが変わればX4/X7で停止する。mutableな観測時刻やファイルhashはsource外evidence.jsonに置き、固定sourceに追記しない。

採用前には実際に用いる正規TTYとnative Codex sessionの両方で、launcher/親環境の拒否対象の変数名だけを列挙して確認する。値や認証情報は読まない。VS Code統合ターミナルに通常あるGIT_ASKPASS/VSCODE_GIT_ASKPASS_*が含まれる場合でも許可扱いにせず、変数名だけを報告して停止する。既存セッションのenvをAIが自動unsetして続行しない。必要なら本人が会社設定を含まない専用個人ターミナル/iTerm2から開始する正規の起動方法を選ぶ。その起動がAIに不可能ならX8として一括確認する。採用時に再確認し、過去の「該当名なし」という観測を将来の保証にはしない。


起動オラクルの実機根拠は、ignored evidence packの `launcher-oracle-probe-result.json` に保存する。これは使い捨てscratchだけを使うOS/Bashの観測で、製品controllerのテスト成功や独立レビュー合格ではない。startup scriptとloader constructorのpositive controlを確認し、-p/env -iを通した各ケースのmarker非生成と子envの空集合を比べる。観測結果を元に固定診断で拒否できないものを成功扱いへ書き換えず、保証する振る舞いを上の2種類に分ける。
