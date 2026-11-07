# FL-10A 結果と非秘密の記録様式

現時点: 承認された実アプリ11/11runを使用。11回目`3f3ee7f365f6`はE01〜10とE08の4項目が全pass、撮影Bのいいね操作でfail。撮影を含む全体は不合格。A/B cleanup・logout、自起動3サービス停止、lock返却はpass。登録確認20件、保守的な合成利用者枠22/22を使用。品質フラグなし・マージ不可。design1/plan1/quality3巡を維持。以下は各時点の履歴。

最新追加承認: 「はい、承認します」により、CDP切断時の停止修正・quality追加1巡（計3巡）・E2E追加1run/2利用者（計9run/最大18利用者）を承認。正規extend済み。切断後/初期化中/重複通知/停止失敗の回帰4件はred→green、型とNode26/Python10がpass。制御Chromium最終fixture `network-fixture-4784116f9b61` は切断page終了・初期化拒否・正常close後の同context継続・禁止先到達0を確認、listener/browser停止/lock返却成功。以下の2巡上限による停止は追加承認前の履歴。

追加fixture `network-fixture-8cc22132a730` はfetch-redirect段階でfail（禁止先到達0、停止/lock返却）。その時点の失敗詳細は固定分類otherのみ。イベント分類を追加した`network-fixture-bda5b33c8b37`は全項目pass。拒否されたdocument navigationが後続caseへ影響しないよう各caseを別pageに分離し、最終4784116f9b61で確認した。失敗を実アプリ成功に数えない。

関連: Issue #54、[設計](fl-10a-design.md)、[撮影台本](fl-10a-capture.md)。結果は対象snapshotに限って記録する。

## 初期検証から第2巡停止までの履歴

専用lockからのnpm ci・型チェック、guard/reporterのNodeテスト12件、runner後始末/結果検証のPythonテスト9件、ゲート回帰54件を実行して成功した。新規依存のnpm install/ci監査は脆弱性0件だった。

ローカル実アプリは8回実行し、1〜7回目はfail、8回目はE01〜10・撮影・後始末pass。受け入れ条件全体の合格ではない。独立品質レビュー第2巡でCDP切断後のguard喪失が高1件として残り、2巡上限で停止。現コードの実アプリ再検証も未実施。品質フラグ・commit・PRは未作成。本体mainは`11736cd`へ同期済み。

| run ID / UTC | 結果 | 起動停止 |
|---|---|---|
| 010c47e4c56c / 2026-11-06 17:12:22〜17:12:59 | E01 fail、後続not_run。A登録確認、B工程で停止。詳細な失敗箇所は未確定、次runでE01は再現せずpass | 自起動frontend/backend/postgres停止確認、lock返却。A UI cleanup pass、B cleanup fail |
| 103377f691b6 / 2026-11-06 17:14:06〜17:14:43 | E01/E02 pass、E03 fail、E04〜10 not_run。写真付き作成後の再読込確認で停止。恒久URLへの遷移は後続3回目で検証 | 自起動3サービス停止確認、lock返却。A/B UI cleanup pass。合成利用者2件は設計どおり残置 |
| ed6c35dee804 / 2026-11-06 17:33:30〜17:34:08 | E01〜03 pass、E04 fail、E05〜10 not_run。空検索を0件とする試験期待値がOpenAPIと不一致だった。訂正は後続4回目で確認 | 自起動3サービスの一括停止/確認、lock返却、A/B UI cleanup pass。合成利用者2件を残置 |
| 75c879313df3 / 2026-11-06 17:46:07〜17:46:49 | E01〜04 pass、E05の編集時textarea指定でfail、後続not_run。隔離DOMでlabel完全一致0件/textbox accessible name一致1件を確認。role指定への訂正は後続5回目で検証 | 自起動資源停止/lock返却、A/B UI cleanup pass |
| 5827bdc8e355 / 2026-11-06 18:05:19〜18:06:02 | E01〜06 pass、E07 fail。空白commentはUIの送信前拒否であり、HTTP400を待つ試験が誤りだった。UIエラー/未送信と、補助実APIの400/件数不変を分離する修正を入れて未再検証 | 自起動3サービス停止/lock返却、A/B UI cleanup pass |
| 9ded0bca6f91 / 2026-11-07 01:31:28〜01:32:22 | B統合後、E01〜07 pass、E10 fail、E08/09と撮影not_run。削除dialogのShift+Tabで必ず最終ボタンへ戻るという期待値がnative dialogと不一致 | 自起動3サービス停止/lock返却、A/B UI cleanup pass |
| 4851ffc49a9b / 2026-11-07 02:14:31〜02:15:33 | E01〜07 pass、E10内のkeyboard削除cancel/確定まで通過、撮影Bのマスク中role locatorでfail。E10全体fail、E08/09 not_run | 自起動3サービス停止/lock返却、A/B UI cleanup pass |
| 6c87437129b6 / 2026-11-07 02:33:39〜02:34:40 | E01〜10 pass、独立撮影判定pass、動画2本decode pass。raw journey/runner/capture判定を保存。runtime詳細の欠落は下記参照 | 自起動3サービス停止/lock返却、A/B UI cleanup pass |
| 75fc423d7af6 / 2026-11-07 03:34:52〜03:35:17 | E01 fail、登録AのHTTP201とID読取り後にUI確認で停止。B登録・E02以降not_run。製品合格とは扱わない | A UI cleanup fail、B登録未確認not_run。自起動3サービス停止/lock返却。投稿/comment/画像作成なし |

両runのcommitは`626c81b2ff00a649b378e370a44402486036f583`と未commit差分。source SHA-256は順に`8b0019feb29a8b6e36f5a66827d1ebf5504f66a7de0b437fb6fa85f6ffdcb220`、`437b503f1509f01f2a8700fb6e56f08fc21777577deac8e63b6f68d184b35365`。一次データは対応する`.artifacts/<run>/runtime.json`と`journey.json`。

3回目も同commitと未commit差分で、source SHA-256は`44f1baba7672b0128d8468eb815c5c56d5ff3f0f21667fd1c5ba9f0b46eeeb16`。前後snapshotは一致した。E03の恒久URLへの修正を実アプリで確認できた。4回目のsource SHA-256は`7321cf5714ba4501ee8a5a206383778664fb7740c7b1800242483c17a1a45169`で前後一致。空検索の期待値修正は確認できたが、録画のprivacy maskと通信回復時の実HTTP200待機は未到達。

5回目のsource SHA-256は`02b3315984cecc4d2a6e3e8c5fc0bf975641dde9b7fc6fd5f655669b373afad5`、前後一致。locator characterizationと実アプリのコメント編集が通り、画像選択のSpaceキー→filechooserイベント→固定PNG保存もE03で確認できた。OSダイアログの手動操作とは区別する。空白commentの試験訂正は6回目でpass。完全性ガード・case timeout時のcontext close・readiness全応答の時間上限は単体検証済み。

6回目はBの統合commit `11736cd267f465705ca69b2c74b9bc38565247b2`と未commit差分、source SHA-256 `b10fc34970cbf496d68233c2e33cd313f0a212f6b3570c651200d882db43ecd7`で前後一致。axeは38画面観測で違反0、incompleteのnode集計30、最大水平overflow 0px。E10はkeyboardによる記録・comment作成、削除dialogの初期cancel focusまで到達したが、境界のShift+Tabで停止した。E10全体はfailのままとする。

隔離HTMLでもcancel→Shift+Tabでdocument.activeElementがBODYとなるnative動作を再現した。[W3C H102](https://www.w3.org/WAI/WCAG22/Techniques/html/H102)はブラウザchromeを含む循環を許容している。試験を「modal内部、またはdocumentがfocusを失ったBODY」に訂正し、前後両方向の境界6回とnonmodal背景focus拒否を隔離HTMLで検証した（`native-dialog-oracle/runtime.json`）。ネットワーク/DB接続・利用者作成ゼロ、専用browser終了・lock返却。訂正後の実アプリは未再検証で、製品コード変更なし。

7回目は同HEADと未commit差分、source SHA-256 `6dd64117a2ba2939890ed948d12aad0c8b9784bf311c0fb36023ad2c5b47987a`で前後一致。訂正したnative focusは実アプリで通過。38画面のaxe違反0/最大overflow 0px。撮影Aは終了し、撮影Bはexact検索の実応答とDOM1行を確認した後、visibility:hiddenの要素を通常role locatorで探して停止した。隔離HTMLでも通常role0件を再現。マスクを維持したままDOM linkの表示名・hrefを検証してから解除する試験へ訂正し、非表示→DOM検証→解除後visibleを隔離HTMLで確認した（`masked-result-oracle/runtime.json`）。実アプリ再実行は未実施。

7回目の動画2本は隔離保存。両方のffmpeg全decodeはexit0、抽出した各1フレームを視認し、Bの結果行マスクを確認した（`partial-video-check.json`）。これは部分動画であり、撮影全体の成功・全編の視認再生・公開承認とは呼ばない。動画のsafe markerは作成されていない。製品コード変更なし。

撮影失敗がE08/09を隠さないよう、撮影の判定をE10から分離してE08後/E09前へ移した。撮影失敗を記録してもE09へ進めるが、全runは必ずfailのままにする。訂正後の順序全体は未検証。7run上限への変更時に旧6run上限を期待するfixtureが1件失敗したため、ユーザー承認に対応する7件履歴/8回目拒否へ更新し、Python全9件passを確認。型/Node全12件もpass。

`7d1d9d45eae2`と`e95ba423d44f`は担当Bのlock競合で共有操作/ブラウザ実行ゼロ。自分が取得していないlockを解除していない。3回上限到達後にユーザーが追加最大3回を明示承認し、既存履歴を維持して合計6回へ拡張した。現在6/6回で追加の実アプリ実行を停止。利用者は11件の登録を確認、初回Bは未確認。保守的に最大12件分の枠を使用済みと扱う。B PR #56を取り込み、README/acceptanceの横断文書を更新した。本体mainは別の生存Codexセッションの利用を確認できず更新保留。A作業branchへのB取り込みとは区別する。

隔離locator probeはアプリ/DBへの接続と利用者作成なし。`locator-probe-corrected/runtime.json`の観測はlabelCount=0/roleCount=1、専用browser終了/lock返却済み。native picker probeはOrcaの`permission_denied`（Accessibility不足）で手動操作未実施。専用Chromeは期限内に終了しlock返却、`native-picker-probe/gui-status.json`にnot_runを記録した。これらを製品E2E成功に数えない。

## 登録11 checks

最終レビュー対象の機械検証はrun `20261107T023807Z-18129fdab33c4099855c61a828092dc7`で全11件exit0、backend643件・frontend190件pass。source SHA-256 `ac6cb02ca84c433aa11a8c4b76a6989f11da155ea1a4d036b5a03ecf6c42b158`、`fl10a-reviewed-before.json`/`fl10a-reviewed-after.json`一致。errors空、自起動DB停止/lock返却成功。工程別の原本JSONとlogを保存しており、8回目E2Eのruntime詳細欠落とは別の証拠。この後の機械検証結果の追記は文書のみ。

run `20261106T172826Z-09be828a0fc94943b83d97b963dac977`の全11件がexit0。backend 643件、frontend 190件、lint/型/build/Django/migration確認を含む。一次結果は`.quality-check-runs/<run>/results.json`、対象対応は`fl10a-before.json`と`fl10a-after.json`で、両snapshotは一致した。自己起動DB停止・lock返却・記録保存成功、errorsは空。これはB統合前・3回目E2E前のsnapshotに対する結果であり、後続のe2e修正まで同じsnapshotで検証済みとは呼ばない。

B統合後のrun `20261107T013550Z-d7c6c9f51f3c444889092bb07317334a`も全11件exit0、backend 643件・frontend 190件pass。HEAD `11736cd267f465705ca69b2c74b9bc38565247b2`と未commit差分、source SHA-256 `c2ed40eb853d39fe742a468e9063da7ae3d5c6b7bed0c2dbac5ed34e8f317c23`。`fl10a-final-before.json`/`fl10a-final-after.json`は一致。errors空、自起動DB停止・lock返却を確認した。この後の変更は検証結果の文書記録だけ。E2Eのfocus訂正後は型check・Node12件・Python9件・ゲート回帰54件もpass。登録11 checksには新規e2e packageの実ブラウザ検証を含まないため、E2E全体成功の証拠にはしない。

## 再開が必要な項目

2026-11-07、ユーザーが追加1run・合成利用者2件を承認し、履歴を維持して合計7run/最大14利用者へ拡張。本体mainも通常fast-forwardで`11736cd267f465705ca69b2c74b9bc38565247b2`へ同期した。以下の6回上限による停止は追加承認前の記録。訂正後の実アプリ再実行と後続検証を再開する。

最新の追加承認で全体8run/最大16利用者へ拡張し8回目を実施した。現在8/8run、利用者15件を確認、初回B未確認を含め保守的に最大16/16枠使用。9回目は拒否する。独立品質レビュー、commit/PRは未完了。既存履歴と失敗判定を保持する。製品の認証・認可テストに関係するため、品質確認後のPRでは別providerの手動相互レビュー待ちで止める。

8回目はHEAD `11736cd267f465705ca69b2c74b9bc38565247b2`と未commit差分、source SHA-256 `5ba49eae6db259d96736e7085b80986e23dba263550324c4b0e37a9179facceb`で前後一致をtool出力で確認。E01〜10/両者UI cleanup/撮影判定passを原本JSONに保持している。axe38画面で違反0/incomplete node30/overflow0px。動画は1.56秒・3.08秒、ffmpeg全decode成功、ネットワーク遮断Chromiumで末尾まで再生し39/77frameを確認。抽出4frameをAIが視認した。人間の全編視認再生とOS chooser手動操作はnot_run。

証跡の制限: 動画再生probeに同じ出力directoryを渡したため、8回目の`runtime.json`を誤って上書きした。工程別時刻/return code・image ID・migration/toolchainのそのrunの原本詳細は失われた。事前に表示・確認したsnapshot/開始終了/停止/lock/decode結果だけを`product-runtime-summary.json`へ観測要約として記録し、原本の復元とは呼ばない。`journey.json`/`runner.json`/`capture-safe.json`/動画等は未変更。再生probeは`runtime-playback-probe.json`/`browser-playback.json`へ分離した。後続11 checksの証跡は別に保存する。

8回目後のコード差分は、撮影分離時にも設計上の5分期限を維持するための`withinDeadline`ラッパー追加のみ。期限時は撮影用contextだけ閉じ、不明な書込みを記録する。期限到達/通常成功/通常失敗の単体試験と型確認はpass、同ラッパー追加後の実アプリは未再実行。撮影の操作本体は8回目と同じ。

## 独立品質レビュー第1巡と修正

GPT-6 Astra/highの統合・反証型QA・securityを正規quality第1巡（上限2巡）で実施。重複統合して高2/中3。高だけを修正し、中はPRに記録する。

- H1: Promise.raceの期限処理が元のcaptureを停止せず、context生成/終了待ちの後にB撮影を開始し得る。実関数の純粋probeで再現。取消scopeを各操作の前後へ伝え、遅れたcontextを閉じ、元captureのsettleを待ってからE09へ進めるよう訂正。生成待ち/終了待ちの回帰試験は修正前fail→修正後pass。
- H2: 固定Playwrightのrouteはredirect先を自動継続するため、最初のURL検査だけでは外部接続を防げない。CDP Fetchをpage遷移前に初期化し、Request/Response各段・3xxのLocationを検査する方式に訂正。応答本文の変更/mock/fulfillなし。未初期化pageとprotocol設定失敗は拒否する。
- 中: `_`検索が誤って空配列でもevery判定が通る検査不足、OS chooser手動not_run、8回目runtime詳細欠落。いずれも独立指摘としてPRへ残し、合格に読み替えない。

通信guardの制御fixture履歴（製品/DB接続・利用者作成・インターネット通信は全て0）:

| fixture run | 結果 | 観測 |
|---|---|---|
| network-fixture-cba658ea3103 | fail | route pause中のNetwork初期化で許可要求がtimeout。listener停止/lock返却 |
| network-fixture-e41305b0ee60 | fail | 固定分類でNetwork.enable待機と切り分け。listener停止/lock返却 |
| network-fixture-3aec1a27b8ef | fail | Network.setBlockedURLsは制御redirect先へ1件到達し不採用。到達先も自己所有dummy listener。停止/lock返却 |
| network-fixture-9045c34db548 | pass | CDP Fetchで禁止先/credential先への到達0、画像preview/offline復旧も確認。停止/lock返却 |
| network-fixture-cb15e0119073 | pass | 同origin redirect許可も含め最終コードで確認。禁止先/credential先到達0、preview/offline復旧pass、停止/lock返却 |

型確認・Node22件・Python10件はpass。登録11 checksは上記ac6cb02 snapshotまでの証拠であり、高修正後の現E2Eコード全体を実アプリで検証した証拠ではない。実アプリは8/8枠のため再実行していない。

### 第2巡（上限2巡）と停止時点

GPT-6 Astra/highの検証担当＋反証QAを正規quality第2巡で実施。H1は両者が解消と判定。H2の通常redirect/Location/send失敗は検証担当が解消と判定した一方、QAがCDP sessionのclose通知という追加の故障経路を発見した。

固定Playwrightはsessionだけのdetach時にもcloseを通知するが、現guardはその通知を監視せずhealthy=trueを残す。QAの純粋probeを親も再実行し、close listener=0/page close=0/切断通知後route continue、追加sendなしを確認した。実ブラウザの切断後に禁止先へ到達する検証は未実施。送信commandの例外処理とは異なる経路であるため、親はguard喪失の高を確認済みと裁定した。現コードを合格にはしない。

2巡上限のため、追加の実装・品質レビューは未実施。次の変更方針は、CDP切断を同期的に不健全状態へ遷移させ、該当page/contextの終了と進行中要求の停止を行い、以降を成功扱いしないこと。切断通知後・初期化中・通常closeの回帰と制御Chromiumのdetach fixtureを追加する。追加品質1巡と、修正後E2E1run/合成2利用者（累計9run/最大18利用者）の承認を求める。承認前に予算を延長・上限値を変更しない。

### 追加承認後の切断修正と9回目

正規extendでquality上限3巡へ拡張済み。CDP closeで同期的にhealthy=false、同一停止Promiseでpage終了・失敗時context終了。初期化中に失ったguardは返さず、通知重複/正常終了も回帰で区別した。fixture `network-fixture-4784116f9b61`で実detach/初期化中拒否/正常close後の同context継続・禁止先0を確認、全停止/lock返却。

9回目のsource SHA-256は`7a1b3ed6b9da1da52331e8e2dac076ce1b287feca0a03f221d16b4027514ef34`（HEAD11736cd＋未commit差分）で前後一致。原本JSONは`e2e/.artifacts/75fc423d7af6/`、退避コピーは`.quality-check-runs/e2e-75fc423d7af6-original/`。201/ID確認はあるが、signup helper内のUI確認後にresourcesへ追加する順序だったため、その利用者IDはjourney原本に保存されていない。Cookie/資格は保持しておらず、Aのlogoutは未確認。登録確認は累計16件、初回B未確認を含め保守的な割当上限18件を維持。10回目は未承認で実行しない。

実アプリの9回目はnative guardイベントの記録がなく、失敗の厳密な原因は未確定。調査用の制御fixtureで通常fetchの取消を応答interceptと競合させると、`Invalid InterceptionId`が発生し、接続中のCDPを故障扱いしてpageを閉じる不具合を決定的に再現した（`network-fixture-a38a1f1611d5`、fail、禁止先0、全停止/lock返却）。この要求は既に消滅しているため、その固定protocolエラーだけを通常取消として区別。session closeとそれ以外のprotocol失敗は引き続き停止する。単体もred→green。9回目と同一原因だったと断定しない。

最終制御fixture `network-fixture-3ed19b37136a`ではCookie付き201/JSONと後続me200、取消済み応答後の通常通信、実CDP切断後のpage終了、初期化切断拒否、通常close後の同context継続、禁止先/credential先到達0、preview/offline復旧が全pass。製品/DB接続・利用者作成・Internet通信0、browser/listener停止/lock返却。今後の実アプリでは`guard-status.json`へ固定code/method/時刻のみ保存して原因識別を補う。URL/生例外/本文/Cookieは保存しない。製品E2Eの代わりにはしない。

### 第3巡の結果

追加承認された正規quality第3巡、GPT-6 Astra/highの検証担当＋反証QAはH2-lifecycleを解消と判定し、新規の高コード指摘なし。独立pure probeは両者各8ケースexit0。型/Node28/Python10/制御Chromiumの既存証拠とは区別する。

新規中M4: page.close/context.closeが双方失敗すると停止Promiseがfalseへ解決し、失敗を記録・伝播しない。後続requestのabortは維持され、外部到達/製品偽passは未実証。中としてPRへ記録し、今作業では修正しない。前巡中の3件も保持。コードレビューの高0を、9回目E2Eの成功・品質全体の完了へ読み替えない。

実アプリ上限9runを維持し、追加実行は承認待ち。現在の失敗修正を実アプリで確かめるまで品質フラグを発行せず、PRをマージしない。必要時の再確認を含む追加最大2run/合成最大4利用者（計11run/最大22枠）を提案するが、承認前に実行しない。

## 非秘密の記録様式

| 分類 | 保存する非秘密情報 |
|---|---|
| 対象 | run ID、commit完全OID、dirty path、source/lock/fixture SHA-256 |
| 環境 | local、Node/Playwright/axe/Chromium/OS版、viewport |
| 時間 | 開始終了UTC、ケース/操作/起動停止の所要時間 |
| 結果 | 固定判定ID、pass/fail/not_run、固定失敗分類、未実施理由 |
| axe | 画面ID、幅、rule ID、impact、件数、incomplete件数、overflow |
| runtime | 初期サービス状態、migration適用状態、自己起動/停止、lock返却 |
| 残置 | 自runのIDと件数、合成利用者残置、cleanup不能/未確認 |
| 撮影 | local動画本数、decode結果、視認再生とOS chooserの実施有無 |

一次結果は`e2e/.artifacts/<run>/runtime.json`、`journey.json`、`runner.json`、`accessibility.json`。Cookie/password/メール/署名URL/フォーム値/DOM/生例外は保存しない。公開するときは自己所有IDも省いて静的判定ID/集計へ縮約し、秘密を含まないことを点検する。

## 10回目と検証方法の見直し

ユーザーの「はい1回承認します」で最大10runへ拡張し、`e01acf6895da`を2026-11-07 04:06:33〜04:07:30 UTCに実行した。HEAD `94c22b12b019fc5273fc272e95d3e1065ac9987d`＋上限・対応テスト・文書だけの差分、source SHA-256 `09145baff1d8a1dc738c4863e8b150b82e08c1dbae48e6b4652eb0e69525307c`は前後一致。直前の型check/Node28件/Python10件はpass。通信ガードと製品コードは9回目後にレビューした版から変更していない。

E01〜07/E10はpass。E08は`journey.spec.ts:366`の「画像と一覧を再読み込み」button clickで停止し、E09/撮影はnot_run。axe38画面の違反0/incomplete node30/最大overflow0px。両者UI cleanupで自己所有post/commentは0、logoutもpass。合成2利用者は承認どおり残置し、登録確認累計18件、未確認分込みの保守的割当20/20枠を使用。自起動postgres/backend/frontendの停止・port解放・lock返却を確認した。

一次記録は`e2e/.artifacts/e01acf6895da/`、退避コピーは`.quality-check-runs/e2e-e01acf6895da-original/`。runtime/runner/journey/HTTP/guard/a11yの原本を保持する。guard診断には通常取消50件とsession close5件があり、`PROTOCOL_FAILURE`は0件。closeの記録だけで異常切断とは判定しない。今回も生例外・DOM・資格は保存しておらず、click待ちの詳細な画面状態は未確定。

コード上は`go()`がlogout表示だけを待つため、E08は一覧の初期読込完了を保証せずofflineへ切り替える。一方、製品の再読み込みbuttonは`WorkoutFeed`の`page`取得後にだけ現れる。このため、初期読込と遮断の競合がテストに存在する。ただし今回の厳密な実行順序は記録不足で断定しない。待機時間の増加や自動retryで隠す修正は行っていない。

今後の検証案は、初期読込成功とbuttonのenabledを確認→意図した再読込要求だけを遮断→エラー表示→オンラインで実200/内容復旧、という前提と判定を分離すること。初期読込を意図的に遅らせた隔離fixtureで競合を先に再現し、条件待ちの根拠を確かめる。固定分類の診断を段階ごとに残し、長い共通シナリオの前工程失敗が後工程を隠す構成も見直す。これは未実装の検討案であり、11回目の承認・実行はしていない。追加回数の申請を繰り返す段階には進めず、PR #57は品質未完了・マージ不可のままにする。

## 未実施・下位層との区別

AWS URLへの接続、S3の実保存障害、自然session期限、再起動永続、3利用者集合/cursor境界、DB停止、競合/二重送信、全WCAG、他browser、環境2往復・課金停止/後日請求確認は今回ブラウザnot_run。既存backendテストの対応と実行結果は別に示す。

登録11 checksとゲート回帰は独立に実施・記録する。新規ブラウザtestの追加だけで製品の受け入れ条件全体をpassにしない。B統合後にREADMEとacceptanceを最終更新する。

## 承認後のE08前提修正（製品追加実行前）

Astraが実App/WorkoutFeedをread-only importした制御fixtureを追加し、実journeyとnetworkRecoveryを共用した。E10削除後の遷移完了、E08四項目の独立台帳、操作開始後requestとの相関、前提確認後だけのoffline、必ずonlineへ戻す処理、後工程の本人/所有資源再確認、非秘密の固定stage観測を実装。製品応答のmockはfixtureだけであり、主要E2Eでは使わない。

TDD根拠:
- Python: 11件履歴でprepare前拒否と既存原本再利用拒否を追加し、修正前2件fail→修正後pass。E08詳細の欠落/fail/未完了を全体passから拒否する3反証もred→green。10履歴を保持した11件目の予約と12件目拒否を別に検証。
- 旧E08の実コードを抽出した`recovery-fixture-8c33be0d3005`は初回GET保留中offline=1・button=0でfail。新共用関数の`bcabe7a0d8bf`はoffline=0・button=0を保ち、release後に通信失敗と回復までpass。これは10回目の厳密な実行順序の復元ではない。
- request相関の反証: mount read取消→同じ操作で開始した後続GET200を、新helperがREQUEST_FAILEDで早期拒否するredを確認し訂正。古い同path応答は引き続き採用せず、時間延長/自動retryなし。

fixture開発中の失敗も保持する。`cbe7fb421b8b`は初期red（数値なし）、`261561e64488`は旧offlineがHTTP到達前になり同期点を待ったため所有runnerへTERMして停止/lock返却。`cd793e2a64c3`/`4ab72602d1b3`はfixtureの保留応答二重送信、`4f17c813cf68`は既に代替表示へ変わったimgの待機、`108af8475625`はfixtureがFetch Response.statusを関数として呼んだ誤り、`21e2bef21e0b`はStrictModeで初回GETが複数回になることを画像fixtureが考慮していなかった失敗。各原因を制御側で修正し、製品run枠は使っていない。`a2865949d728`は13ケースpass、StrictMode/実CSS/401/本人不一致まで含む`377b1112c860`は15ケースpass、全停止/lock返却・source前後一致。

現時点の制御fixture対象は初回GET保留、200後body/DOM遅延、503/不正body/401、本人不一致、別画面の同名button、古い同path応答、画像固有のエラー、DELETE204後の遷移、4段階の観測保存失敗後online復帰、context終了。秘密markerが観測へ出ないことも確認する。製品/DB接続・利用者作成は0。製品11回目・登録11checks・手動相互レビュー等は未実施で、fixture成功を全体合格へ読み替えない。

## 11回目の実アプリ結果

承認「どちらにしても実装と追加しないとダメだと思うので、承認します。」に基づく追加1runだけを実行。`3f3ee7f365f6`、2026-11-07 05:16:53〜05:17:44 UTC。HEAD `9446b99f2af482df5f65b89261a9600fcd97f5dd`と未commit差分、source SHA-256 `a3a12bdf7f001ecc197a93734867bca4e79a2a23b8e6c9b754a33e70d7921575`前後一致。12回目は承認・実行していない。

- E01〜E10すべてpass。E08のnetwork/CSRF/old-session/cookie-lossも全pass。E08の準備・遮断・回復と後工程の前提確認は固定分類の観測原本に残した。
- 撮影はA工程後、Bのfollow→一覧→記録詳細後のいいね操作（`journey.spec.ts:537:153`）でfail。HTTP status不一致0。例外本文・DOMを保存しないため、厳密な失敗分類は記録だけでは未確定。`capture-safe.json`なし。quarantineの2本は撮影成功・共有可とは扱わない。E09は撮影失敗と独立してpassしたが、全体不合格は維持する。
- axe38画面、違反0/incomplete node30/最大overflow0px。A/B UI cleanup・logout pass、post/commentの自己所有台帳残存0。合成利用者2件は承認どおり残置。画像物理回収の保証ではない。
- 自起動postgres/backend/frontend停止、port解放、lock返却を確認。runtime原本の工程/時刻/終了code/source対応は保持。
- 一次記録は`e2e/.artifacts/3f3ee7f365f6/`。`.quality-check-runs/e2e-3f3ee7f365f6-original/`へ10ファイルを複製し、全内容hash一致を確認。既存原本の上書きはしていない。
- 直前の型check/Node34件/Python13件はpass。既存guard fixture `network-fixture-fe0afcc44202`もpass、製品要求・利用者追加0、停止/lock返却pass。ゲート回帰54件pass。登録11checksの最終結果は同PRの品質報告へ対応付ける。

AstraによるE08修正は今回の実アプリで合格した。ただし他runの撮影成功を合成して今回の全体合格とはしない。撮影失敗の調査結果と未確認事項をPRへ記録し、追加回数を自動で増やさず停止する。認証/認可試験を含む手動相互レビュー等の既存条件も未解除。

## 撮影詳細遷移の修正と制御fixture

撮影Bは詳細link直後に全画面のlike buttonを選んでおり、hashchange後のReact描画と詳細GET完了を待っていなかった。11回目の保存動画末尾には2投稿のlikeと一覧再読込buttonが残る。複数一致が最有力だが、当時の例外分類がないため11回目の直接原因とは断定しない。8回目の成功動画は詳細の読込画面から単一card/コメントへ進んでおり、以前の成功は遷移待ちの保証にならない。

撮影と実App fixtureで共用する詳細遷移/like関数を追加した。対象linkを押した後に開始したGET200、対象hash、詳細内の既知card/コメントUI、loading解消、一意enabled/非pressed/0件を確認してからPOSTし、pressed/1件への描画完了を要求する。固定capture stageとLOCATOR_NOT_UNIQUE分類を記録し、生例外・DOM・URLは保存しない。CancellationScopeと動画隔離は維持した。

TDD: 初回fixture `75ebfe015fb3`は別投稿メモにも対象文字列が含まれ詳細linkが複数一致するfixture側の誤りでfail。メモを区別した旧順序の`6d4f4b813a3f`はhashchange保留中like button2・対象/別投稿POST0・LOCATOR_NOT_UNIQUEでred。修正後`0fb5691994a1`は新規1＋従来15＝16ケースpass、runner exit0。hash一致でも旧一覧DOMの間はPOST0、詳細GET200のbody保留中もPOST0、解放後対象POST1/別投稿POST0・pressed/1件を確認した。全fixtureで停止/lock返却、製品要求/利用者追加0。

最終fixtureのHEADは`aeffd2d64b3dc777f79f8e6cc05486513489e0ba`、source SHA-256 `9158aa596becfd8480cd4b596399b74de9b453dde07b222add43ef2804ee33c1`前後一致。以後は文書と固定診断の秘密除去テストだけを追加し、実行コードは同じ。製品runは11/11のまま、12回目は実行していない。11回目のraw結果は全体failを維持し、修正後の製品撮影は未再検証。正式design1/plan1/quality3巡を変更せず、失敗修正の影響範囲だけを検証した。
