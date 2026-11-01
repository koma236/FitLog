# FitLog 個人用並列開発運用

承認・Gitの方針は [個人開発運用](personal-workflow.md) に従う。
これは2026-10-31のユーザー指定に基づく運用規則。Composeやv9を自動で分離する実装ではない。

## 作業の分離

- 1 Issue = 1 branch = 1 worktree = 1書込みセッション。独立した仕様/plan/taskを使用する。
- `git worktree list` と各担当の状態を確認し、既存worktreeを再利用する。Codex管理下のworktreeも有効。
- 初期設計は準備branchでよい。Issue番号を捏造せず、作成後に対応を記録する。
- 各計画にworktree絶対path、branch、baseline、担当、変更対象、先行PR、共有資源を記載する。
- 他worktreeのstash/restore/clean、branch切替、未保存ファイルの移動・削除を行わない。
- worktree削除はmerge済み・未保存変更なし・利用中processなしを確認してから。force削除しない。

## 共有ファイルと依存

CI担当は `.github/`、機能担当は対象backend/frontendを主な所有範囲とする。
Compose、依存lock、checks設定、OpenAPI、migration、運用規則は計画で変更担当を明示する。
同じ共有ファイルを変更する作業は先行PRと後続PRを決める。異なるworktreeで同時編集できても、統合順を省略しない。
独立したmigrationを並列作成した場合も依存グラフと空DB/既存DBへの適用を統合時に再検証する。
前提PRが未mergeなら依存機能の実装・合格を宣言しない。別branchのv9 receiptを流用しない。

## 現在の共有実行環境

同じホストの共有runtimeを使う全FitLogセッションは、単一cloneのworktreeに限定する。
今回の共通Git管理領域は `/Users/saki/project/FitLog/.git`。別cloneやGit worktree外からは共有Compose/DB/image/portを操作しない。
編集・読取りのために別cloneを持つ場合も、そのclone固有のlockでは共有runtimeを保護できない。正しい共通git-dirとlockを確認できないセッションは共有操作を開始しない。

現行Composeはproject `fitlog-dev`、固定image `fitlog-dev-backend` / `fitlog-dev-frontend`、
DB `fitlog`、hostポート18080/15173を使う。DBと画像volumeもこの環境の共有状態になる。
worktreeを分けただけでは分離されない。project名だけ変えても固定imageタグの競合は残る。

編集・仕様確認は並列に進められる。以下は同じ排他枠で行う。

- imageのbuild、Composeのrun/up/stop、migration、DBテスト、画像cleanup、ブラウザ検証。
- v9経由の全11checksを含む実行。他担当のbuildで検証対象imageを途中で上書きしない。
- 開発サーバーを起動したまま使う場合は、その利用終了まで排他枠を保持する。

### 排他枠の取得・返却

1. 共通Git管理領域を `git rev-parse --path-format=absolute --git-common-dir` で確認する。
2. その直下の `fitlog-runtime.lock` ディレクトリを通常の `mkdir`（`-p`なし）で原子的に作成する。既存（EEXIST）なら取得失敗とし、共有環境へ触れず他の編集を進める。権限拒否（EACCES）など既存以外のエラーは競合待ちにせず、原因を報告して共有操作を停止する。
3. 取得者は `owner.json` を排他作成し、task、worktree絶対path、branch、ホスト、保持主体のPID、開始日時、使用資源を記録する。PIDはlockを取得し返却まで生存する調整役または専用保持processを指し、providerや短命なCompose processと区別する。子process/コンテナは使用資源として別記する。秘密を含めない。書込み失敗時は実行を開始せず、自分が作成したと確認できる途中ファイルだけを除去して、空になった自分のlockディレクトリをrmdirする。他のファイルや所有権を確認できないものが残った場合は削除せず報告する。
4. 取得後にCompose/サービス/imageの初期状態を確認し、自分のworktreeからbuildして登録checksを実行する。checksは--no-depsのため、PostgreSQLが未起動なら排他枠内で起動し、今回起動したサービスとして記録して手順5で停止する。既に起動していたDBは停止しない。共有開発DBは未merge branchのmigrationを保持し得る。登録backend-migrateの前後にshowmigrationsで適用状態を採取し、branch/commit・schema差分とともに返却記録へ残す。取得者は前担当の記録と自分のmigration graphを照合し、不一致は無断の逆migration/resetで直さず、先行PRの統合を待つか必要なデータ変更の承認を得る。開始前状態を採取できなかった場合はその不足を明示する。実行中は同じworktreeへの別セッションの書込みも禁止する。
5. 成否と対象snapshotを保存し、今回起動したサービスだけ停止する。開始前から動いていたサービスは停止しない。
6. 残存processがなく、所有者が自分のままであることを確認し、自分のownerファイルと空のlockディレクトリだけを除去する。

PIDや経過時間だけで古いlockを消さない。別ホスト、所有者不明、追跡不能、稼働中のサービスがある場合は調査し、
安全に所有者の終了を確定できなければまとめて人間へ確認する。他担当のlockは奪わない。
このlockは協調運用であり、現行v9/Composeが自動取得するものではない。provider起動前に調整役が取得し、実行終了まで保持する。
全参加セッションがこの規則に従う必要がある。既に稼働中の未対応セッションがあれば担当と調整するまで共有操作を開始しない。

## v9・レビュー・Git

workflowはworktree絶対pathとtaskに対応する既存stateを使い、別taskへコピーしない。
branch・source・plan・checks等の変更は正規controllerで再照合し、失効した結果は使わない。
review-budgetは共通Git領域のbranch別台帳を使う。同じbranchの重複実行、台帳削除、失敗分の予算返却をしない。
予約と開始受付を区別し、各roleの開始受付が台帳へ記録されたことまで確認する。native Agent hookの受付が未記録なら、その結果を正式な通過根拠にせず、既消費枠を保持して正規経路で再確認する。外部CLIのreviewerを使う場合も、起動前にインストール済みhookの公開受付APIを予約済みmarkerで通し、model/effortとroleを明示する。実行後の受付の付替えや、native hookの信頼を捏造する対応はしない。
Git管理領域も共有するため、index/worktree/refsに関わる変更操作は重ねない。Git lockに遭遇したら所有者を確認し、勝手に削除しない。
自分のworktreeのtask差分だけをproposalへ含める。運用改善と製品機能など別taskの差分を混ぜない。
規則更新は他worktreeへ自動反映されない。新しい作業開始時に採用済みの規則版を確認し、既存セッションにも共有する。

## 統合と完全分離への移行

先行PRの人間によるmerge後、後続branchを許可された通常手順で更新し、競合解消と必要な再検証を行う。
baseline変更等はv9 bindingの更新・再承認要件を確認する。既存成功を新snapshotへ付け替えない。
現行v9の固定HEADとIssue chainの制約により、baseline変更には再承認や既存Issueを再利用できない問題が生じ得る。先行commitの元SHAが残らない場合は [変更設計の停止契約](../../docs/personal-workflow-change-design.md#別taskへの送信とprの後続チェックリスト) に従い、統合方法の判断を得るまで自動更新しない。

検証自体も並列化する場合は別taskで、worktree固有のCompose project、imageタグ、DB/volume、
hostポート、登録checksのargv、起動停止手順を一式で分離する。ローカルの一時overrideで承認済みchecksをすり替えない。
受け入れ条件は、2 worktreeの同時build/テストが互いのimage・DB・画像を変えず、片方の停止が他方へ影響しないこと。
現行の排他運用が不要になるのは、この分離の実検証が完了してからとする。

## 今回の環境差分復旧と先行公開条件

WF-PARALLELの元commitと承認記録は変更しない。今回のFL-07の先行公開は、
元の成功commit job/resultと四receipt、独立レビュー済み復旧controllerのticket/intent/success result全連鎖、
個人profile経由で確認したremote feature refのSHA=`0d234332d51f078f68137a421d442ff7abed1400` の3つで照合する。
これは標準push resultの偽装や通常v9の検査除外ではなく、別設計で承認された新しい復旧記録である。

実行順は、復旧taskのlocal commitとnative採用確認 → FL-07復旧送信とremote照合 →
WF-PARALLELの通常v9送信とremote=`2a2fd3c089771f23046a6b4153b06e3796a95689` の照合 → 復旧taskの通常v9送信とする。
WF通常操作の直前に、coordinatorが新controllerの `status --delivery-result D --project P` を呼ぶ。
result digest・remote SHA・観測時刻をsource外reportへ保存し、不一致やunknownなら後続送信を止める。
標準push resultだけを見る旧helperを復旧後の公開証拠として使い続けない。
このcross-task先行条件はcoordinatorの運用ゲートであり、旧runtimeやhookが機械強制する条件ではない。

共有configを書き換えるCLIやVS Code Git UIでのbranch/追跡設定操作は行わない。
新たなconfig driftを認めるよう復旧規則を自動拡張しない。通常feature送信にも追跡設定を追加しない。
PRは個別承認後。FL-07を本人がmerge commitで統合し元SHAを保持したことを確認してから、
WFのmainに対するthree-dot差分が元の15pathsであることを確認する。AI mergeは禁止する。
