# 運用改善の設計（Issue #38・承認済み）

2026-11-05にユーザーが設計・Medium 2件への対応と実装計画を承認。worktreeをcwdとするセッションでの作業ルール追加も対象。承認範囲は実装・検証・品質レビュー・commit・push・PR作成まで。マージ前で停止する。

品質レビュー2巡後、停止待機中の再割込みでlockを返すHighへの対応として、ユーザーが追加1巡だけを承認した。停止待機中のSIGINT/SIGTERMを保留し、終了確認不能なら必ずlockを保持する方針で修正する。延長巡で新しいHighが出ても追加修正せず、既知の制限としてPR本文と運用文書へ記録してcommit・push・PR作成まで進む。マージは行わず、残存指摘があれば品質合格と区別して報告する。追加の延長はしない。

## 目的・範囲

設計の承認後は、機械チェック、独立品質レビュー、通常のcommit/push、PR作成までAIが進める。本PRは制御面変更のためマージ前で停止する。製品コード、CI、既存の別task、古いworktree/branchには変更を加えない。

baseline: `583fe51`。worktree: `/Users/saki/project/FitLog/.worktrees/chore-operations-38`。branch: `chore/operations-38`。Issue: #38。書込み担当: 親セッションのみ。レビュアーは読取りと隔離fixtureでの検証のみ。

## 1. checksスクリプト

- Python 3.11以降の標準ライブラリだけで `scripts/run-checks.py` を作る（親の判断）。PR #37 の `/private/tmp/fitlog-36-checks-with-db.py` を原型とし、固定task/pathを除去する。
- 通常起動は `python3 -B scripts/run-checks.py`。引数は `--help` 以外受け付けない。任意command、registry、Compose project、lock、出力先の上書き機能を持たせない。
- worktreeはスクリプト自身の位置から決める。`.git` ファイル/ディレクトリと `commondir` を標準ライブラリで読み、共通Git管理領域を確定する。branchはHEADから読む。git subprocessは起動しない。
- 呼出し前の必須手順として、親は `git rev-parse --path-format=absolute --git-common-dir` の実体pathがpersonal-parallel-workflow.mdの採用済み共通Git管理領域と一致することを確認する。不一致・未確認なら起動しない。別cloneの独立lockでは固定Composeを保護できないためであり、この制限と確認責任を実行手順にも明記する。スクリプトへ環境固有の絶対pathは埋め込まない（親の判断）。
- registryの11 idと順序、argv（文字列配列）、cwd（当該worktree内）、env、正のtimeoutを明示的に検証する。登録argv/cwd/env/timeoutを順にそのまま用いる。shellは使わない。11件以外や不正値は実行前に失敗する。
- 外部起動はregistryのargvと、固定 `docker compose --project-name fitlog-dev -f compose.yaml` の `ps / up / stop / run --rm` だけ。git/gh、品質フラグ、volume/image削除、権限設定は操作しない。
- 共通 `.git/fitlog-runtime.lock` をmkdirで原子的に取得し、排他作成のowner.jsonへtask/branch/worktree/host/生存PID/開始時刻/資源を記録。既存lock・所有者不明・権限エラーでは共有runtimeを操作しない。他人のlockを削除しない。
- lock内でComposeの初期状態を採取し、DBが稼働中ならそのまま使い、停止中/未作成の場合だけ `up -d --wait postgres`。未知の状態や複数DBは停止する。起動要求直前から自分の起動責任を記録し、upの途中失敗でもfinallyでstopを試みる。
- migration前状態は、自分のbackend imageを `run --rm --build --no-deps backend ...` で準備して記録する（親の判断。古いbranchの既存imageを根拠にしないため）。`showmigrations --plan` とDBの適用済みnode/現在のmigration graphの比較を読み取りだけで取得する。未知の適用済みmigrationや不整合は、migrationを実行せず停止して記録。DBが空の場合は正常とする。自動reset/逆migrationはしない。
- 続いて11 checksを実行する。compose-build以外の通常の非ゼロ終了は保存し、後続checkも実行。compose-build失敗・任意checkのtimeout・SIGINT/SIGTERM・process起動不能では後続check全件を中断し、各未実行理由を明示して後始末へ進む（frontendも続行しない、親の判断）。checks開始前の準備失敗では全11件を未実行とする。backend-migrateの直前/直後にもmigration状態を採取する。最後のmigration採取もfinallyで試みる。
- SIGINT/SIGTERMとtimeoutでは子processを終了・待機してから後始末する。Docker側のone-off残存は `ps --all` で確認し、終了が確認できない場合は成功や安全なlock返却を宣言しない。SIGKILL/電源断にはfinallyの保証がないことを文書化する。
- 後半を入れ子のfinallyとし、migration記録失敗・結果保存失敗でも、自分で起動したDBだけのstop、所有権確認とlock返却を必ず試みる。他人に所有権が変わったlockは残す。DB停止失敗や残存processで安全な返却不能ならlockを保持して失敗を報告する（自動的な奪取・再実行はしない）。
- `.quality-check-runs/<一意run-id>/` にJSONと各ログ、短いMarkdown要約を保存しignoreする。各checkにはid/argv/cwd/開始終了UTC/終了code/status/log pathを記録し、未実行も全11件に明示する。操作ログとcleanup結果も保存する。全check成功とcleanup成功を満たす場合だけ終了0。
- registryとスクリプトのSHA-256、worktree、branchを記録する。commitと未commit差分snapshotの採取・同一性確認は従来どおり親のquality-check側で行い、run結果へ対応づける。スクリプトは品質合格の判定やフラグ生成を代行しない。
- `gate.controlPlane` にスクリプトと実行命令台帳 `.ai-dev/project.toml` を追加する（台帳も実行権限を決めるため、親の判断）。gate hookの実装自体は変更しない。

## 2. マージ後の後片付け

personal-workflow.mdの「作業の分離」に、作業は対象worktreeを作業場所（cwd）にしたセッションで行うことを追加する。本体側のセッションの担当はworktreeの作成と引継ぎまでとし、引継ぎ後の設計レビュー・実装・検証・GitHub操作は対象worktreeのセッションで行う。本体側のセッションから別worktreeへのpath指定だけで作業を継続しない（ユーザー追加要件）。マージ後の本体main更新・今回作成した資源の後片付けは、以下の専用手順で扱う。

personal-workflow.mdのマージ手順5を拡充する。MERGEDと統合結果の確認後、対応する品質フラグだけを除去し、本体がmain・未コミット変更なし・他セッションの使用なしの場合に通常fetchとfast-forwardだけで更新する。

今回自分が作ったbranch/worktreeのみ対象にする。mainの変更、他セッション使用中、所有権不明、worktree内の未保存/未追跡ファイル、稼働process、統合を確認できないbranchがあれば触らず報告する。stash/restore/clean/forceを使わない。必要な証跡を削除対象の外へ保存し、本体のパスからworktree削除を最後のworktree操作として行い、その後merge済みの自分のローカルbranchを通常削除する。remote branchも今回作成分だけ、他セッション使用がなく統合確認できる場合に通常削除し、確認不能なら残す。古い資源を掃除しない。本PR自体はマージ前停止なので後片付けは実行しない。

## 3. 許可設定は提案まで

`documents/development/command-permissions-proposal.md` に、Codex/Claude Codeの設定例、配置先、対象・除外、公式参照、検証方法を保存する。repository内設定例もこのPRに含めるが、activeなallow設定もリポジトリ外設定も適用しない（「案の作成まで」に従う、親の判断）。

- codex-trust、hook-selftest、既知CLIの--help、review-budget status、gh api user --jq .login、git status/diff/logの安全な定型形、checksスクリプトを候補にする。
- Claude Codeはワイルドカードなしの完全一致で列挙。Codexのprefix_ruleは後続引数を制限できないため、`gh api user ... -X PATCH`、`git diff ... --output`等に伸長できるものをallowしない。安全に表せない候補は制約を明示し承認を維持する。任意引数を受けないchecksスクリプトのprefixだけは候補化できる。Python全般、git/gh全般、npx全般は許可しない。
- checksスクリプトはDB/migration/imageへの限定書込みを持つ例外として記載する。他の書込み、push、gh書込み、review-budget begin/extendは常時許可しない。
- `.git`全体を書込み可にしない。runtime lockと `ai-dev-helm-reviews` の限定書込みを、インストール済みCodex 0.166.0と公式permission profile仕様に照らして調べる。保護されたmetadataへの深いpathの明示許可と従来writable_rootsの違い、親directory作成、worktree共通git-dir、managed設定の優先を区別する。実環境の外部設定は変更せず、未検証は明記する。git index/refs/hooks/config、会社用設定を許可対象に広げない。
- 公式根拠: https://learn.chatgpt.com/docs/agent-configuration/rules 、https://learn.chatgpt.com/docs/config-file/config-reference 、https://code.claude.com/docs/en/permissions （2026-11-05確認）。

## 短い実装計画・検証

1. 承認後、独立した期待値メモを作り、lock競合/所有者変更、DB既存/停止/up途中失敗、check失敗/timeout/signal、保存失敗、cleanup失敗、migration不一致、argv許可範囲を固定fixtureで先にテストする。通常非ゼロ時の続行とbuild失敗/timeout/signal/起動不能時の後続全件中断をそれぞれ検証する。Python unittestとprocess境界のfakeを使い実DBを壊さない。共通Git管理領域の呼出し前照合も手順の検証対象とする。
2. スクリプトを実装し、personal-workflow/personal-parallel-workflowと関連checks手順を更新。後片付け、権限提案、制御面宣言、必要なignore/運用説明/回帰テストを追加する。共通helm配布skillの整理はしない。
3. 登録11 checksを新スクリプトで実行し、スクリプト用テスト・既存ゲート回帰・stop判定のスクリプト/台帳検知も確認。各失敗を成功扱いしない。新スクリプト実行前に全文を提示する。
4. quality-checkの機械チェック後に規定の独立レビュー（integrated-reviewer、falsification-qa、必要な専門家最大1体）を行いHighを修正・検証。証跡と設計との差異を報告へ記録し、自分の変更だけcommit、feature通常push、PR作成、CI結果とX2対象パスを確認する。PR番号/headを示しマージ前で停止する。

## 主な権限申請の記録

- GitHub読取り: account/repo照合（sandbox内のnetwork失敗後、昇格実行で成功）。
- GitHub書込み: Issue #38作成。
- Git書込み: .worktrees/chore-operations-38 と chore/operations-38作成（.gitのEPERM後、昇格実行で成功）。
- レビュー台帳: design/document-reviewer第1巡の予約（.gitのEPERM後、昇格実行で成功）。

## 独立設計レビュー（2026-11-05）

- `helm-doc-reviewer` によるdesign第1巡（上限1）。token: `8ee22f53c42bc4201248de1a53d799fe`。collaboration起動成功後、`review-budget.cjs status` のusedとreceiptsでreceiptId `052e4c0067633a0d2e27838781cb554a8e25ea029c46873c9cdf96fed42583a8` を確認した。
- 結果: High 0件、Medium 2件。再レビューは行わない。
- Medium 1: 別cloneのlockでは共有runtimeを保護できず、採用済み共通Git領域の確認担当が曖昧。呼出し前に親が採用済みpathとの一致を確認し、不一致・未確認なら起動しない必須手順を追加した。
- Medium 2: 異常終了時の「依存する後続」の範囲が曖昧。build失敗/timeout/signal/起動不能は後続全件中断、その他の通常非ゼロは続行と明記し、fixtureの期待値にも含めた。
- 指摘への対応は親の判断による設計の明確化であり、再レビューによる確認はしていない。その後、ユーザーがMedium 2件への対応を含めて設計を承認した。
