# 16. E2Eテスト（Playwright）

> FL-10Aのローカル準備設計は2026-11-07に独立レビュー・ユーザー承認済み。実行結果は[結果記録](fl-10a-results.md)を参照する。AWS実証は未実施。

### 16.1 位置づけ
UIからAPI・DB・画像までつながる主要操作を確認する。UIモックの操作成功をアプリE2Eの成功にしない。

### 16.2 ツール・環境
`e2e/`専用package/lockのPlaywright＋TypeScriptとChromiumを使う。現行の共有PostgreSQLとローカル画像volumeをruntime lockで排他利用する。独立DB/S3互換ストレージ案は今回採用しない。接続先はloopback15173、backend18080。run固有の2利用者と上限付き自己所有資源だけを作り、既存データを消さない。詳細は[設計](fl-10a-design.md)。

`e2e/`で`npm ci`、`npx playwright install chromium`、`npm run typecheck`、`npm run test:harness`、`npm run test:runtime`。実アプリ検証は`npm run test:e2e`、明示的な録画予行は`npm run capture:rehearsal`。runnerが排他取得・起動・停止・返却を担う。既存app稼働時は無断停止せず終了する。

### 16.3 シナリオと対応
UC-01〜13を2人のブラウザコンテキストで実行。登録→ログイン→記録作成→画像→検索→フォロー→フォロー中一覧→いいね→コメント→本人編集→リロード→ログアウト。第三者の更新・削除拒否はAPI結合テストでも確認する。

### 16.4 シナリオでは足りない観点
今回のbrowser対象は空一覧、通信遮断/再試行、logout後の旧session/Cookie喪失、CSRF欠落、容量上限/画像偽装。自然期限経過・並行二重送信・削除/送信競合・cursor境界は既存backend層の対応を照合し、browserではnot_runとする。

### 16.5 アクセシビリティ・ブラウザ性能
主要画面のWCAG2A/AA・2.1A/AAタグでaxe serious/criticalなし、375pxの水平overflow1px以下。keyboardだけで記録作成/セット追加/送信/comment/削除確認を操作しfocusを確認する。moderate/minor/incompleteも記録し全WCAG適合とは呼ばない。性能検証は担当Bの結果を参照する。

### 16.6 AWS上の撮影台本
以下は後日のAWS用シナリオであり、今回のAWS実行許可や成功証跡ではない。認証画面/資格入力は撮らず、実際の録画は認証後に開始する。[撮影台本](fl-10a-capture.md)でlocal予行とAWS実証を分ける。
1. デモ環境URLを開き、Aとしてログインする。
2. 日付・種目・セット・メモ・写真を入力して記録する。
3. BとしてAを検索・フォローし、フォロー中一覧から記録を開く。
4. いいね・コメントを付け、A側でも件数と内容を確認する。
5. 本人編集、プロフィール画像変更、リロード後の永続性、ログアウトを確認する。
6. 動画をローカルへ保存・再生確認後、破棄手順へ進む。

### 16.7 結果の記録
結果は環境・commit・dirty snapshotと対応付ける。通常実行のtrace/HAR/video/screenshot・storageState disk保存・DOM dumpは無効。固定判定IDと秘密を除いた結果だけを残す。録画予行も認証画面/メール/Cookieを含めず、想定外表示は隔離する。実施前の台本を成功証跡と表現しない。
