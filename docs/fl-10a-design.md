# FL-10A ローカルブラウザ検証の設計

関連: Issue #54。2026-11-07に具体設計・テスト設計を独立レビューし、ユーザー承認済み。独立設計レビューはHigh 0/Medium 2（コメント生存期間と認証状態遷移を明文化）、計画レビューはHigh 0/Medium 0。

## 目的と範囲

課金資源を作る前に、実UI→実API→PostgreSQL→ローカル画像volumeを使った2利用者の検証と撮影予行を用意する。製品コード、既存依存lock、Compose、API、migration、Terraform、CI、品質ゲートを変更しない。性能/AWS準備は担当Bの範囲。

`e2e/`は製品frontendから分離したprivate npm package。Node 24、Playwright Test 1.65.0、axe 4.14.0、TypeScript 5.9.2を専用lockで固定する。Chromiumのみを扱い、他browserは未実施と記録する。

## 実行環境と資源

- 接続先は`http://127.0.0.1:15173`、APIも同origin。外部origin、userinfo、別port、redirect先を拒否。AWS接続の有効化スイッチはない。後日の承認済みAWS環境で再利用する際は、exact HTTPS originとguard変更を再設計・承認する。
  Playwrightのrouteはredirect先で再実行されないため、blank pageでChromium CDP FetchのRequest/Response interceptionを遷移前に確定する。各送信先と3xxの全Locationを検査し、禁止応答は追跡前にfailRequest、許可応答は本文を変更せずcontinueする。route.fulfillや成功応答mockは使わない。未初期化page（popupを含む）の初回通信も拒否し、CDP未対応時はfallbackせず失敗する。
  CDP sessionのcloseを検知したら同期的に不健全状態へ遷移し、pageを終了する。page終了に失敗した場合は所有contextを終了する。重複通知は同じ停止Promiseを共有し、初期化中に切断されたpageは返さない。
  通常fetch/navigationの取消でinterceptionが既に消えた固定エラーだけは接続喪失と区別する。切断通知で不健全になった状態を再び有効化することはない。guard診断は固定code/method/時刻だけを記録し、診断保存失敗でもpageを停止する。
- `fitlog-dev`、15173/18080、共有DB `fitlog`と`private-images` volumeを採用。独立DBやS3互換ストレージでの実証とは呼ばない。
- 共通Git領域の`fitlog-runtime.lock`をbuildから停止確認まで保持。既存app/port占有があれば触らず終了。既存稼働DBは止めず、自分が起動した資源だけ停止。既存migrationとの不一致ではreset/逆migrationしない。
- `e2e/runtime.py`は登録check runnerの読取り可能なlock/process/migration照合プリミティブを再利用する。登録11 checksの内容と実行経路は変更しない。
- 1 runあたり合成2利用者、記録6、comment4、保存画像4（各64KiB以下）。当初3runから追加3run・1run・1run・1runの明示承認を得て、同実装作業で合計9run・合成利用者最大18件を上限にする。認証試行は全context合算で8回/rolling60秒、retries=0。既存counterによる429をresetしない。
- E2E全体15分、判定ケース120秒、操作10秒、撮影5分。build10分・readiness合計90秒・自己所有サービスの一括停止command90秒を別枠で記録する。停止後のinventory/port確認も実施し、確認不能ならlockを保持する。
  撮影期限時は取消状態を各操作の前後に伝え、遅れて生成されたcontextも所有して閉じる。context生成/終了を含む撮影本体がsettleするまでE09へ進めない。
- run固有の自己所有資源だけUIで解除/削除。利用者削除APIがないため合成利用者は残る。画像の物理回収・関連DBの全削除は既存backend責務であり、ブラウザ結果だけでは保証しない。

## 検証契約

| ID | 実ブラウザの対象 | 独立した期待値の根拠 |
|---|---|---|
| E01 | 2人登録、重複拒否、誤password拒否、logout/login | UC01/02、AC01、auth-implementationの201/200/204・401/409コード |
| E02 | 表示名/自己紹介/avatar、本人と相手の参照、非公開情報非露出 | UC12/13、AC08、OpenAPI profile schema |
| E03 | 固定日・60kg×10回×3セット、画像、相手参照/reload | UC05、AC03/04、OpenAPI record/image |
| E04 | 空/部分一致/文字通り検索、follow/unfollow、following/all | UC04/10/11、AC02/07、OpenAPI。共有全件数の仮定なし |
| E05 | like +1/解除、comment作成/編集/削除と件数 | UC07/08/09、AC05/06 |
| E06 | 本人編集、他者編集UI/直接遷移/実API拒否、不変確認 | UC06/08、AC03/05、正しいCSRFと本人owner headerで403 FORBIDDEN |
| E07 | 回数0、空白comment、偽装/容量超過画像の拒否 | UC05/07、AC03/04/05。送信前拒否をHTTP拒否と混同しない |
| E08 | offline/retry、CSRF欠落、logout後旧session、Cookie喪失 | AC01、auth契約。Cookie除去は自然期限経過の証明ではない |
| E09 | 本人削除、相手GET404、cleanup/logout/reload | UC03/06、AC03 |
| E10 | 375px/axe/keyboard | Issue54と下記提案基準。明示時の動画予行は独立判定 |

E05の他者comment拒否は、B本人がcommentを削除する前に実施する。E10の後に認証を失うE08を実施し、旧sessionをメモリで複製→別タブlogout→旧me401→UI再login→Cookie除去→ゲスト→残存旧sessionをlogout→再loginの順にする。前提を失った後続はnot_run。撮影はE08後/E09前の独立判定とし、撮影失敗でもE09の本人削除を観測するが、全runはfailにする。

## アクセシビリティ

主要画面を1280×800と375×812で検査し、375pxでも実際に作成・画像・検索・交流を操作する。水平overflowは1px以下。WCAG2A/AA・2.1A/AAタグのaxeでcritical/serious=0を要求し、moderate/minor/incompleteも件数を記録する。ルール除外で既存不具合を隠さない。

keyboardでメニュー→記録入力/セット追加→保存→comment送信→削除cancel/確定まで操作し、focus/順序/trapを確認する。native dialogは[W3C H102](https://www.w3.org/WAI/WCAG22/Techniques/html/H102)に従いbrowser chromeへの移動を許容し、背景の画面要素へのfocusを拒否する。ファイル選択は自動setInputFilesと手動のOS chooser予行を区別する。axeはscreen readerや全WCAG適合の保証ではない。

## 情報保存

通常のtrace/HAR/video/screenshotは失敗時もoff、storageStateはメモリのみ。HTML/生JSON reporterやconsole/network/DOMのdumpはしない。Playwright 1.65が失敗時に作るARIA copy promptも抑止し、テスト本体からframeworkへ渡す例外は固定エラーに置換する。判定結果をfailのまま伝えるもので、失敗を握りつぶして成功にはしない。

`.artifacts/`はgitignore。commit/source snapshot/依存lock/fixture hash・tool版・判定ID・pass/fail/not_run・日時・起動停止・自己所有ID/残置だけを記録。axeからはrule/impact/件数/画面IDだけを出す。メール/password/Cookie/署名URL・DOM値を出力しない。

撮影は[専用台本](fl-10a-capture.md)の明示コマンドのみ。後日AWS成功・環境往復・課金停止/後日請求確認までFL-09/10全体の完了とはしない。

OpenAPI上、空検索は0件ではなく利用者一覧を返す。録画用contextでは検索結果の行を初回paint前からCSSで隠し、完全な合成usernameの実API応答とDOMの1件・表示名・href一致を確認してからマスクを解除する。通常試験や製品のAPI/応答は変えない。マスク使用は撮影メタデータへ記録する。実施結果は[記録](fl-10a-results.md)を参照する。

## 統合と品質

`npm run test:network-guard`は共有lock下で15173/18080に制御HTTP fixtureだけを起動する。既存app/port占有時は触らず終了し、製品/DBには接続せず利用者も作らない。HTTP redirect各段・userinfo/別port拒否・同origin許可・data/blob preview・offline復旧を実Chromiumで確認し、listener/browser停止とlock返却を記録する。製品E2Eの成功数には含めない。CDP APIの根拠は[Fetch protocol](https://chromedevtools.github.io/devtools-protocol/tot/Fetch/)と固定Playwrightの実装/型定義。

Bを先に統合し、Aにmainを通常取込みして最終snapshotで再検証する。11 checks・ゲート回帰・独立品質レビューを維持する。認証/認可の試験を含むため、PR作成後は手動相互レビュー待ちで止める。製品不具合はfailの証拠と範囲調整を残し、製品コードを無断で修正しない。
