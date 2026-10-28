# 機能定義書 F05: いいね

> 壁打ち用の草案。未承認・未実装・独立レビュー未実施。数値・方式は提案であり、実行結果ではない。

## 1. 概要 / 目的
いいねを通じて筋トレ記録と交流を提供する。MyTimelineの同IDの責務を引き継ぎ、記録データ・Python基盤に合わせる。
## 2. 機能詳細
いいね・解除・件数・自分の状態を表示。POST/DELETEの再送は冪等。初版は自分の投稿にも許可する案。
## 3. 対象画面
SCR-03, SCR-04, SCR-05
## 4. API エンドポイント案
| メソッド | パス |
|---|---|
| POST | `/api/posts/{postId}/like` |
| DELETE | `/api/posts/{postId}/like` |
共通エラーは `{"code":"...","message":"...","fieldErrors":{},"requestId":"..."}` 案。[エラー一覧と共通契約](../api/README.md)に定義する。Cookie/CSRFを使う。
## 5. データ
likes、posts、users。[ER図](../07_er_diagram.md)参照。
## 6. バリデーション / 制約
(post_id,user_id)一意。並行送信でも2件にならず解除で負数にならない。レスポンスの件数をUIの正とする。
## 7. エラーハンドリング / 異常系
未認証401、不在404、CSRF403。楽観更新を採る場合は失敗時に復元する。
request/response・HTTP状態・エラーコードは[OpenAPI](../api/openapi.json)に定義したレビュー前の契約案。[受け入れ条件](../acceptance.md)を検証の根拠にする。
