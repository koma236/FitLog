# 機能定義書 F02: タイムライン

> 壁打ち用の草案。未承認・未実装・独立レビュー未実施。数値・方式は提案であり、実行結果ではない。

## 1. 概要 / 目的
タイムラインを通じて筋トレ記録と交流を提供する。MyTimelineの同IDの責務を引き継ぎ、記録データ・Python基盤に合わせる。
## 2. 機能詳細
フォロー中は自分＋フォロー先、すべては全会員。created_at DESC,id DESC。実施日の遡及入力でも投稿日時順を変えない。初期タブはフォロー中。
## 3. 対象画面
SCR-03
## 4. API エンドポイント案
| メソッド | パス |
|---|---|
| GET | `/api/timeline/following` |
| GET | `/api/timeline/all` |
共通エラーは `{"code":"...","message":"...","fieldErrors":{},"requestId":"..."}` 案。[エラー一覧と共通契約](../api/README.md)に定義する。Cookie/CSRFを使う。
## 5. データ
posts、users、follows、likes、comments、workout_exercises、workout_sets。[ER図](../07_er_diagram.md)参照。
## 6. バリデーション / 制約
limit既定20・最大50。次カーソルはnullで終端。編集で順序を変更しない。件数・自分のいいね状態を含む。
## 7. エラーハンドリング / 異常系
不正カーソル400、未認証401。通信失敗と0件を分け、既読一覧を消さず再試行できる。
request/response・HTTP状態・エラーコードは[OpenAPI](../api/openapi.json)に定義したレビュー前の契約案。[受け入れ条件](../acceptance.md)を検証の根拠にする。
