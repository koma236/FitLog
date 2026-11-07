# AWS C: 実経路E2E・撮影・限定性能試験の詳細設計

2026-11-07 / Issue #60 / **独立レビュー後ユーザー承認済み・ローカル実装中・実AWS未接続**。
担当C: `/Users/saki/.codex-personal/worktrees/e865/FitLog`、branch `test/aws-verification-60`。
baseline: `4524ec2965f6ac46815815555942bd4deda87058`。先行PR #56/#57統合済み。
本書は新規設計案であり、旧E2Eの11run/22利用者という承認を継承しない。

## 1. 到達点と承認の分離

今回の到達点は詳細設計・独立レビュー・短い計画の提示のみ。テストコードを含む実装、install/build/server/Compose操作、AWS SDK/CLI/HTTPによる実AWSアクセスは行わない。
次の設計承認はローカルharness実装・検証の承認とする。実AWSへのHTTP要求、公開、構成変更、停止、破棄は含まない。
後日の実AWS申請でaccount/operator/対象environment・origin・操作・USD予算・UTC期限・回数・データ上限を具体化し、別承認を得る。

目的はAC-10/11/12のAWS部分に必要な、CloudFront経由の利用者操作、公開境界、RDS/S3対応証跡、初回/再構築別結果、AWS外で再生できる動画と限定性能結果を準備すること。ローカル成功をAWS成功へ読み替えない。

## 2. 所有・依存と再利用

| 担当 | 所有とCとの契約 |
|---|---|
| A #58 / 784f | `terraform/**`・`scripts/prebilling/**`・基盤/費用/申請文書。実AWS構成の唯一のoperator。環境ID/ARN・非秘密output・公開状態・操作窓・閉鎖/破棄/再構築証跡を提供 |
| B #59 / 5034 | `scripts/deployment/**`・`backend/operations/**`・配置runbook。source/image/static hash・health/seed/verify結果と対象拘束を提供。B仕様の実AWS操作はAが行う |
| C #60 / e865 | `e2e/**`・`perf/**`・`docs/aws-c-*.md`・`docs/fl-10a-capture.md`・`docs/13_performance_test.md`。最終統合後に限り`docs/acceptance.md`・`docs/production-readiness.md`・`README.md`を更新 |

CI・ゲート・Compose・既存lock・OpenAPI・DB migration・製品認証認可は変更しない。他worktreeは編集しない。追加基盤/remote probeはCで実装せずA/Bへの依頼事項とする。
統合はA→B→C。harnessの純粋ローカル設計/実装は並行可、AWS対応成功の判定は先行統合後の同一snapshotのみ。

再利用先:
- `e2e/support/safety.mjs`: CDP Request/Response guard、CDP喪失時close、ResultLedger/Budget/CancellationScope。
- `e2e/support/app.ts` / `recovery.mjs` / `specs/journey.spec.ts`: 登録・本人確認・画像・交流・通信回復・撮影・削除の既存操作とoracle。環境注入可能な共用journeyへ抽出し、ローカル入口と既存上限を維持する。
- `e2e/runtime.py`: 共通Git/runtime所有照合・履歴/証跡の考え方を利用。AWS runnerではbuild/Compose/migration/DB起動の経路を呼ばない。
- `perf/report.py`: nearest-rank集計、欠測/失敗処理。`perf/runner.py`の親監視・worker回収を利用するが、5利用者固定seed/client/runtimeをAWSへ転用しない。
- Bの既存deployment verify: DB role/TLS、S3 probe、IAM拒否、IP観測の正本を参照。CにAWS SDK/SQL/secret読出し/同じcollectorを追加しない。

## 3. 実行契約と排他

新規`e2e/aws-runtime.py`は既定をオフライン契約検査のみとし、明示的な実行指定と完全な承認済み契約が揃うまでブラウザ/HTTP clientを生成しない。単独URL引数、任意endpoint、任意shell/SQL、秘密値のCLI引数は提供しない。
契約はschema版・approval参照/許可工程・account/region/environment・deployment run UUID/bootstrap UUID・test run UUID・clean source完全OID・backend digest・static hash・exact origin・A/B証跡参照とSHA256・開始/終了UTC・上限・Aの操作窓IDを含む。regionは`ap-northeast-1`。
不明key、未決値、期限切れ、開始前、別環境/source/digest、欠けた先行結果、draftの実行指定を接続前に拒否。承認参照は実承認の代用ではない。Cはstate本文/秘密/planを読まず、Aの対象照合結果を参照する。

開始条件と最終受入れを分離する。Bの`ready_for_c` handoff（account/region/environment/run/bootstrap/source/image/frontend/origin、backend/seed/check/database/public-health metadataのpass、証跡参照/hash、操作窓/承認）が揃えば開始可能。Bのpublic-healthはAWS metadataによる稼働確認であり、公開HTTP healthの実証ではない。permissions/IP/公開境界probeはこの時点でnot_runでもよいが、Cの総合合格には後段で同じ対象の実結果が全て必要。C結果を開始条件へ逆流させない。

originはAの選択output・Bの公開health証跡・承認値の三者で完全一致する`https://<distribution>.cloudfront.net`。path/query/fragment/userinfo/明示port/末尾dot/wildcardは入力として拒否。初回と再構築は別environment/deployment run/test run/origin契約、別証跡。URLが偶然同じでも履歴は共有しない。

Aが環境の試験lease（操作窓ID/対象/期限/Cへの引渡し）を発行し、Cの終了・全client停止確認まで構成/rotation/task変更を重ねない。Cも同一窓で1調整process・1実行のみ。開始前に新runのintentと上限消費を原子的に保存、結果不明・中断も1試行を消費し再起動で回数を戻さない。2環境分の親campaign台帳はworktree外の保護folderに置き、削除/別pathでの予算再初期化を禁止する運用記録をAと共有する。
Aのpermissions/IP one-offや公開境界probeが必要なときは、Cを送信停止して全in-flight要求の完了/取消を確認→Aに一時返却→Aが対象固定の検証/収集とtask停止を確認→Cへ再引渡し、の順にする。構成/rotationはfreezeを維持し、Aの検証要求とCの要求も重ねない。IP観測用のC認証1要求は、Aのbaseline収集・停止確認後にCだけが送信し、C停止後にAがafterを収集する。C起因の認証上限へ算入し、同一固定窓を逸した場合はfailとし自動再試行しない。A自身の認証probeも共通のIP認証枠に照合し、別窓に分ける。
共通Gitの`fitlog-runtime.lock`もbrowser/fixture/checks中は取得し、別ホスト/別cloneでは実施しない。実AWS排他をこのlocal lockだけで代替しない。既存資源・lockを奪わない。

## 4. 通信guard

ローカル入口は従来のloopback限定のまま。AWS入口だけが検査済みoriginを不変policyとして共用guardへ注入する。Chromiumのみ、TLS検証は有効、service workerはblock、popup/未初期化pageは初回通信から拒否。
通常の全navigation/fetch/XHR/画像/script/style/formとredirect各段はexact HTTPS originに限定し、外部HTTP(S)・S3・ALB・task・別distribution・IP literal・userinfo・別portを送信前に拒否する。`data:`はローカルpreview、`blob:`は束縛originのものだけ許可し、network送信の抜け道にしない。WebSocketは通常/性能とも不要として送信前拒否、workerからの外部通信もfixtureで禁止先到達0を確認する。未対応経路があれば実行不可にする。
既存CDP FetchのRequest/Response interception、3xx Location検査を維持し、同origin redirectにも予算を適用。CDP切断/初期化不全・証跡書込失敗はcontextを閉じfail。成功mock/route.fulfill/TLS無効化で継続しない。

性能用HTTP clientは検査済みHTTPS originだけを受け、固定API pathのみ、proxy環境の自動利用なし、redirect追跡なし、TLS検証あり、親が全要求5秒を監視。認証情報はactor別メモリのみ。
既存E08の`context.request`はCDPの対象外であるため、AWS経路では専用のAPI送信wrapperへ置換する。wrapper内だけがAPIRequestContextを扱い、検査済みorigin＋固定API path、`maxRedirects=0`、TLS検証有効、retryなし、全要求5秒、UTC期限、共有要求/送信body bytes/auth予算の送信前消費を強制する。旧sessionを含むCookieはメモリ内だけで渡し、例外/全header/bodyは記録しない。timeout時は保有request contextをdisposeし停止確認まで次へ進まない。AWS経路の直接`context.request`利用を禁止し、wrapperの偽送信境界と制御listenerでredirect0追跡・禁止先0送信・予算/期限拒否を検証する。
C02の異Origin負例もこのwrapperから**正規対象の同origin endpoint**へ固定の偽Origin headerを付けて送る。偽Origin先へ接続せず、実CSRF・本人sessionが有効な同一POSTとの対照を取ってOrigin拒否を識別し、前後で対象が不変であることを確認する。
公開境界の負例は通常guardの例外にしない。ALB/task/S3/別distributionへの実要求はA実行/B証跡の別probeとして参照する。C browserが遮断した結果をAWS側の拒否成功とは数えない。

## 5. 試験量・時間・失敗停止（親の提案、新承認対象）

| 項目 | 初回または再構築の1環境あたり上限 |
|---|---|
| 試行 | 主要E2E1回、撮影1回、限定性能1回。全体2環境で2回ずつ。自動retryなし |
| データ | UI登録の新規合成2利用者、記録最大6、comment最大4、保存画像最大4・各64KiB以下。性能は同2利用者/既存投稿を読むだけ |
| 認証 | signup/loginの正負合算8回/rolling60秒、全体24回。auth-burst試験なし |
| 要求 | C起因のHTTP送信全体3000以下（static/API/画像/redirect/cleanup/warmup含む）、送信body合計20MiB以下。負例画像最大5MiB+1を1回、保存画像枠には数えない |
| 性能 | 並列最大2、各1要求/秒、warmup10秒20枠＋測定90秒180枠。枠遅延は取り戻さない |
| 時間 | C操作窓45分以内、実journey15分（撮影/性能含む）、判定case120秒・操作10秒、撮影合計5分/最大2本。終了/cleanupに残り5分を予約 |

合計4利用者まで。B既存demo seed2人/環境は別所有・別内訳としてAの総データ台帳に加算し、Cは変更しない。旧11run台帳・固定5利用者/1000投稿のローカルperf seedを流用しない。
要求/bytes/auth budgetはbrowserと性能clientとcleanupで共有し、送信前に原子的に消費する。cleanup用に全体3000中200要求を予約し、通常処理は2800で停止。予定送信を超える未知長bodyは拒否する。時刻はUTC期限とmonotonic経過の両方で検査する。
上限/期限/対象不一致/CDP喪失/予期しない401/403/429/5xx/内容不一致/timeoutで新規試験と性能を止める。負例の予定拒否は例外。失敗を保存後、残余の承認/期限/予算内で所有確認済みcleanupだけ行う。窓末尾でworker/browserの停止を確認しAに返却、停止不明はfail・lease未返却として通知する。
環境の閉鎖/停止/破棄はAに引き渡す。CはAWS SDK/CLIで退避しない。再試行・利用者追加・負荷増加は新しい具体承認が必要。

## 6. 検証と合否

| ID | 対象・独立oracle・成功条件 |
|---|---|
| C01 | 既存E01〜E10の主要操作をCloudFrontから実行。UC/AC/OpenAPIの固定入出力・本人ID・他者403・削除後404・変更前後不変を照合。画面hash/HTTP200だけで成功とせずDOM readyと実操作後応答を対応づける |
| C02 | HTTPS/TLS、session/CSRF cookieのSecure・HttpOnly・SameSite=Lax・Path=/・host-onlyをメモリで検査しbooleanだけ保存。欠落CSRFのPOST403、異なるOriginのPOST403、正規CSRFの本人操作成功、logout後旧session401。トークン値/Set-Cookieは保存しない |
| C03 | 正規originの`/api/health/live`・`/api/health/ready`のHTTP200と既存API契約のbodyをメモリ照合し、liveとDB readinessを分けて記録。自分の画像upload→表示→reloadと他者の正当参照。秘密の画像URLはメモリのみ。Bの同環境DB TLS/role/S3実probe成功とAのRDS/S3 target bindingを参照し、UI結果だけで実RDS/S3利用を断言しない |
| C04 | ALB直（通常Host/正規CloudFront Host）、task public IP、static/media S3匿名、別distribution、viewer header/proto/IP偽装をA/Bの実証跡で照合。403等の明示拒否/期待probe条件を要求し、NotFound/単なる接続失敗/fixture無しはpassにしない。taskへのSG到達不可はAのSG/対象実測との組合せで評価し、HTTP拒否とは分ける |
| C05 | 撮影は認証後の自分のprofile/投稿/画像/編集、合成相手の完全一致検索/follow/like/comment。認証前は録画せず、検索マスクを維持。撮影結果/全frame decode/視認/破棄後再生を別状態で保存。どれか未実施なら動画受入れ未完了 |
| C06 | 限定性能: E08後に本人session/下記固定投稿/follow関係を再確認し、両actorでall/following/detailの固定3分類を順番にGET。API契約と所有IDの存在・順序・viewerを照合。各分類60標本、p50/p95/p99 nearest-rank、p95<1000ms、失敗/5xx/欠測0。開始からbody全受信まで測りoracle時間は除外。180枠不足・1000ms一致はfail。5人容量/最大境界/本番性能は主張しない |
| C07 | 初回と再構築のC01〜C06/対象source/digestを別runで評価。閉鎖/破棄/残存/後日請求はAの証跡と対応。2回成功でも未実施のAC項目を一括合格にしない |

基本順序は契約照合→A/B先行結果→E01〜E08/E10の操作→C02/03→撮影→限定性能→E09自己所有削除/logout→全client停止→A返却。
性能の固定状態は、E03でUI作成したA投稿`aPost`（画像あり）とB投稿`bPost`（画像なし）を所有台帳から特定する。E10のkeyboard投稿は削除済み、撮影末尾のfollow/like/commentは解除済み、A/B間のfollowは両方向なしとし、性能準備でfollowを追加しない。allは両actorとも`{aPost,bPost}`、followingはA=`{aPost}`・B=`{bPost}`、detailは両actorとも画像なし`bPost`を読む。集合はレスポンスから期待値を逆生成せずUI作成/削除/解除の台帳から導き、順序は投稿の既知日付/IDとAPI契約で照合する。detailでは同じ本文/所有者に加えactor別viewerを照合する。前提の差異はfail、準備用の無断データ追加や再followで補正しない。
既存journeyをこの順序で共用化し、ローカルではAWS追加検査/性能を呼ばない。既存E08の個別結果と撮影状態を維持する。撮影だけの失敗では元failを保持し、前提が健全ならE09だけ続ける（性能はnot_run）。失敗の自動再ログイン/全体再実行はしない。
cleanupはrun記録の本人投稿/comment/like/follow/avatarを正規UI/APIで解除、ID/所有確認不可の削除はしない。利用者削除APIなしのため2利用者は残置し、Aへ環境破棄時の消去対象として引き渡す。未確定書込み・画像物理回収・cleanup失敗は残置/unknownとして記録する。

## 7. A/Bへの必要な引渡し契約（まだ成立・実装済みとは扱わない）

Aへ: 初回/再構築各45分以内のC専用操作窓、別environment/run、対象originと資源対応、対照distribution/匿名S3既知object/task到達probeの承認と費用、構成freeze、終了時閉鎖/破棄/残存/後日請求担当を依頼する。Cの2利用者/6記録/4comment/4画像/要求3000/20MiBと残置を総予算に含める。
Bへ: `environment/deployment_run/source/backend_digest/frontend_hash/exact_origin/phase/started/finished/status/probe_id`と証跡hashの対応を依頼。既存verifyのDB/S3/IAM/IP各項目と、A実行の公開境界probeの個別結果をCが参照可能にする。公開health/seed/実task exitとsource対応、合成専用環境であることを確認する。
公開境界probeは現状の`deployment_verify.py`だけでは全て揃わない。B/Aに既存runbook実施/非秘密証跡の提供を依頼し、Cにcollectorを二重実装しない。未提供・別run・hash不一致・fixture未承認は該当項目not_run、AWS受入れ未完了。先行証跡の改変・成功転記を行わない。
2026-11-07にA/Bの`docs/aws-a-foundation-design.md` / `docs/aws-b-deployment-design.md`を読取り照合。Bの§5は`ready_for_c`、permissions/IPの未実施を許容するhandoffを提案し、公開HTTP healthはC担当とする。本書§3/6はこれに対応する。公開境界の専用probe証跡schemaと操作窓/一時返却の受渡しは依頼案であり、A/Bが承認・実装済みとは扱わない。初回/再構築で同sourceのbuild digestが異なる場合も、各環境の承認digestと実task/証跡の一致を個別照合し、2環境のbyte同一性を合格条件にしない。
RDSへのC直接接続、S3へのC匿名probe、secret取得、既存demo利用者へのpassword付与、製品診断API追加は要求しない。

## 8. 保存物

repo外0700の専用campaign/run folder、記録0600、既存runを上書きしない。runごとにsource/clean snapshot・依存lock hash・tool/browser版・契約hash・A/B参照hash・UTC/経過・ID別pass/fail/not_run・要求/bytes/認証消費・自己所有ID/残置・停止/返却を原子的保存。
raw error/SDK例外・URLのqueryや署名・Cookie/CSRF/password・response body/全headers・DOM・state/plan・storageStateを保存しない。trace/HAR/screenshot/通常videoはoff、copy prompt抑止とsafe reporterを共用。対象originは制限された契約に保持し、判定ログは固定probe ID/status/booleanのみ。
認証情報はメモリだけ、子clientへは非公開IPCで渡しファイル/argv/envへ出さない。動画は最大2本のquarantineへ保存、checksum/decode/視認を記録し、認証画面/他者データが写ったものは成功証跡にしない。AWS外へ保存しAの破棄後にも再生確認する。外部upload/URL共有は別承認。

## 9. ローカルの反証と受入れ

上位リスクは(1)誤origin/期限外/予算超過の要求、(2)秘密漏洩と他担当資源変更、(3)別環境証跡や失敗の成功化。Highとしてテスト設計する。

| 失敗モード | 独立oracleとテスト層 |
|---|---|
| URL/通信の越境 | 本書§3/4の許可表を固定fixture入力とし、Node単体＋実Chromium制御listenerで外部redirect全段/複数Location/userinfo/port/blob/popup/SW/worker/WebSocket/CDP断を注入。禁止listener到達件数0、同origin通常要求は到達する |
| 契約/予算/再実行 | Python/Node固定時計・偽送信境界で時刻の直前/一致/直後、2800+200/3000、24認証/25回目、2利用者/3人目、別run・hash欠損・中断履歴・二重起動を反証。拒否時のclient生成/送信0 |
| 漏洩/停止 | fixtureに秘密canaryを入れ、例外・reporter・失敗/timeout・遅延context/子起動で成果物とstdout/stderrにcanaryがないこと、停止不能はfail/lease未返却になることを確認 |
| 証拠/集計 | B証跡の同一性不一致/欠落/NotFound/timeout/一部fail、撮影fail＋E09pass、未到達not_runをテスト。性能は手計算固定列でnearest-rank/1000ms境界/60未満/missed/5xxを検査 |
| 既存互換 | 既存loopback policyはAWS origin拒否、旧run上限は不変。local harness/復旧/撮影fixtureが維持されることを確認。旧製品E2Eの追加実runは承認回数を増やさない |

独立レビューに対応する追加反証: API送信wrapperの外部redirect/期限境界/予算尽き/旧sessionを含む秘密canaryで送信先・停止・非漏洩を検査する。性能前提は誤detail ID、follow残存、keyboard投稿残存、別viewer、撮影cleanup不完了を注入し、性能要求0でfailになることを確認する。`ready_for_c`でpermissions/IP=not_runなら開始可能・総合pass不可、Aへ一時返却中はC送信0、Bのmetadata成功だけではHTTP health=passにしないことも固定fixtureで検証する。

共有runtimeのfixtureは既定15173/18080と共通lockの既存方式だけを使い、TLSの差はローカル保護CAを一時生成した制御fixtureで検証する。実AWSへ疎通しない。依存lockの変更/新規runtime依存なし。
承認後の主な検証は`npm --prefix e2e run typecheck`、`test:harness`、`test:runtime`、共有lock下の`test:network-guard`/`test:recovery`と新AWS guard制御fixture、`python3 -B -m perf.runtime unit-tests`。登録11 checksは`python3 -B scripts/run-checks.py`、通常ゲート回帰も実行。機械check後にquality-checkと規定の独立品質レビューを行う。
認証/認可の検証を含むためPRは手動相互レビュー待ちで停止する。実AWS試験・撮影・性能は別承認前は常にnot_run。現時点では本書のテストは一切未実行。

## 10. 短い実装計画（承認後）

1. #60/現branch/worktreeを継続し、§9をローカルtest-designメモへ固定。A/Bに§7の契約を引き渡し、未成立を記録する。
2. 契約/履歴/送信予算/通信guardの負例を先に追加。既存local互換を保ちながら共用journeyとAWS専用runner/configを実装する。
3. 既存2利用者を使うread-only AWS性能client、録画/cleanup/証跡照合を接続。制御fixtureで停止・秘密非保存・誤対象0送信を検証する。
4. A→B統合後に通常取込みし、同snapshotで既存回帰/11 checks/追加fixture→quality-check→commit/feature push/PR。共通受入れ文書はCで最後に更新。手動相互レビュー待ちで停止する。
5. 実AWSはAが具体申請を別承認後、構築→B配置仕様をA実行→C専用試験→A閉鎖/破棄を2環境で行い、破棄後動画再生/残存/後日請求を別状態で追記する。

## 11. 設計の選択と参照

親の選択: 任意URLではなく契約拘束、CにSDKを持たせない、2利用者/GET限定性能、試行1回/環境、上記固定上限、新依存なし。AWS予算/実日時/実origin/対照資源は本設計で決めず実AWS申請に残す。
通信根拠: [CDP Fetch](https://chromedevtools.github.io/devtools-protocol/tot/Fetch/)、[Playwright Network](https://playwright.dev/docs/network)、[Python urllib.request](https://docs.python.org/3/library/urllib.request.html)。固定Playwright/Chromiumでの制御fixtureを採否の根拠とし、最新版の文書だけで対応を断言しない。
既存契約: `docs/acceptance.md` AC-10/11/12、`docs/fl-10a-design.md`、`docs/fl-10a-capture.md`、`docs/13_performance_test.md`、`docs/fl-09b7-deployment-runbook.md`、`docs/api/openapi.json`。

## 独立設計レビュー

2026-11-07、`helm-doc-reviewer`（GPT-6.1 Sol / high）の独立設計レビューを1回実施。**High 0件 / Medium 2件**。実装者の推測を要する箇所として次が指摘された。

1. Medium: 性能試験の画像なしdetail対象/follow状態/actor別期待集合が未確定。既存journeyではA投稿は画像あり、B投稿は画像なし、E04/撮影末尾にfollowを解除する。対応: §6に両actorのdetail=`bPost`、両方向followなし、all/followingの期待集合、既存操作台帳によるoracleを固定した。
2. Medium: 既存E08のAPIRequestContext要求はpage CDPを通らず、guard/共有予算の適用経路が未記載。対応: §4にAWS専用API送信wrapperとredirect拒否/TLS/期限/予算/秘密非保存/timeout回収を明記し、§9に直接通信の反証を追加した。

Mediumは設計の明確化として反映し、再レビューは行っていない。A/B契約の照合による`ready_for_c`と最終合格の分離・公開HTTP healthのC担当・probe時の一時返却は親の補足判断として§3/6/7/9へ明記した。残る依存は公開境界probeのschema/資源/実承認/操作窓の成立であり、未成立なら該当AWS項目はnot_runとなる。

レビュー予算の履歴: design round 1は手動事前受付後にnative起動が拒否され未起動のまま消費。ユーザーの「許可します」により追加1巡を正規CLIでextendし、round 2をbridge ticketでnative起動した。台帳の`admittedAt`・receipt・agent aliasと結果を確認済み。最初の消費枠は保持し、実施した独立レビューは今回の1回だけ。今回許可は設計レビュー追加に限り、設計/実装の承認として扱っていない。

ユーザーの「承認します」により設計を明示承認済み。承認前は本設計文書だけを作成し、承認後ローカル実装を開始した。実AWSの承認ではない。

## 実装時の差異

- 性能送信は既存actorのAPIRequestContextを使う2つのpaced async jobとし、別Python HTTP workerへCookieを移送しない。集計は既存`perf.report.summarize`をPython補助から再利用する。actor分離・親の全体監視・要求5秒/最大並列2/無retryは維持。理由は既存session/guard/共有予算の一元化。
- test run識別子は既存E2Eのusername長/設定と互換な12桁hexを採用し、deployment/campaignはcanonical UUIDで拘束する。
- 動画視認・破棄後再生/C07/後日請求の自動合格は追加しない。自動観測の成功と総合受入れを分離し、Aの運用証跡と実確認を必要とする。操作窓の一時返却はA/Cの手動調整を前提とし、自動AWS操作は追加しない。
- Bの実装済みhandoff v1を読取り照合し、C用成功サマリへの転記を要求せず元のB工程証跡のcanonical hashを検査するadapterに具体化した。B branch未統合時は契約fixtureの検証にとどめる。
- A PR #61は通常mergeで取込み済み。B未統合のため、C専用のローカル品質確認・PR作成を先行し、B統合後の契約再確認と共通README/acceptance/production-readiness更新を未完了として残す。相互レビュー待ちに加えてB依存の解消まではマージしない。理由は各担当の待機時間を減らし、C差分を具体的にレビュー可能にするため。
- 品質レビューで公開境界の薄い成功要約では実拒否を検証できないと判明したため、Aの実観測receipt仕様の成立・実装まではC04/final_evidence_readyをnot_run/falseに固定する。証跡参照の受領と合格を区別する。実AWS受入れは未完了のままで、SDKや独自collectorは追加しない。
- 期限内停止を確保するため末尾30秒はclient取消/停止確認に使い、API timeout・親監視はUTC/monotonic残時間で拘束する。ChromiumのPIDをCDPから取得し起動時刻/PGIDと対応づけ、Nodeとは別groupの停止を確認する。追加listenerや新portを使わず既存pipe transportを維持する。

## #66の承認済み補強設計（2026-11-07）

[C04観測契約・C02 Origin対照](aws-c-boundary-contract.md)を後続仕様とする。C04常時not_runの保留実装を、schema v2の対象台帳/実在原本/観測原本の厳格照合へ置き換える。旧要約はnot_runのまま。原本のhash/対象/identity/窓を照合し、開始後の改変・消失はfail。全7probeとB permissions/IPが揃った場合だけfinal_evidence_ready=trueで、総合acceptanceは別状態のまま。

C02はAPIRequestContextとrequestApiを共通化し、同じPUT/body/CSRF/sessionからOriginだけ変更。正例でmarker変更をGET確認、正規PUTで復元・GET確認、同じmarker本文の負例403/CSRF_FAILEDと復元後の状態不変を確認する。追加の製品認証実装やAWS接続経路は作らない。

独立設計レビューHigh1（OACなし別distributionの403で誤合格）を、両OACのalways/sigv4/attachmentと同一static object正常対照で是正し確認済み。Medium2の扱いはユーザー承認済み（初回不足はnot_run、検証後消失はfail。viewer IPはFunction公開code hashとB baseline/IP観測を結合）。実AWS操作を含まない設計・計画をチャットで承認後に実装する。
