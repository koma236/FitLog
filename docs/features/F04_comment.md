# 機能定義書 F04: コメント

> 壁打ち用の草案。未承認・未実装・独立レビュー未実施。数値・方式は提案であり、実行結果ではない。

## 1. 概要 / 目的
コメントを通じて筋トレ記録と交流を提供する。MyTimelineの同IDの責務を引き継ぎ、記録データ・Python基盤に合わせる。
## 2. 機能詳細
記録詳細で作成し、古い順にカーソル表示。本人のみ編集削除。件数を記録カードにも反映。
## 3. 対象画面
SCR-04
## 4. API エンドポイント案
| メソッド | パス |
|---|---|
| GET | `/api/posts/{postId}/comments` |
| POST | `/api/posts/{postId}/comments` |
| PUT | `/api/comments/{id}` |
| DELETE | `/api/comments/{id}` |
共通エラーは `{"code":"...","message":"...","fieldErrors":{},"requestId":"..."}` 案。[エラー一覧と共通契約](../api/README.md)に定義する。Cookie/CSRFを使う。
## 5. データ
comments、posts、users。[ER図](../07_er_diagram.md)参照。
## 6. バリデーション / 制約
本文1〜500文字、空白だけは拒否。表示はプレーンテキストとして扱い、HTMLとして実行しない。limit既定20・最大50。
## 7. エラーハンドリング / 異常系
入力400、権限403、不在404。削除済み投稿への送信を拒否。失敗時は入力を維持する。
request/response・HTTP状態・エラーコードは[OpenAPI](../api/openapi.json)に定義したレビュー前の契約案。[受け入れ条件](../acceptance.md)を検証の根拠にする。
