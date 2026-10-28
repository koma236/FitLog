# 機能定義書 F07: プロフィール表示・編集

> 壁打ち用の草案。未承認・未実装・独立レビュー未実施。数値・方式は提案であり、実行結果ではない。

## 1. 概要 / 目的
プロフィール表示・編集を通じて筋トレ記録と交流を提供する。MyTimelineの同IDの責務を引き継ぎ、記録データ・Python基盤に合わせる。
## 2. 機能詳細
表示名・自己紹介・画像・件数・本人の投稿一覧。本人のみ表示名・自己紹介・画像を更新。username/emailの変更は初版対象外。
## 3. 対象画面
SCR-05, SCR-07
## 4. API エンドポイント案
| メソッド | パス |
|---|---|
| GET | `/api/users/{username}` |
| GET | `/api/users/{username}/posts` |
| PUT | `/api/users/me` |
| PUT | `/api/users/me/avatar` |
| DELETE | `/api/users/me/avatar` |
共通エラーは `{"code":"...","message":"...","fieldErrors":{},"requestId":"..."}` 案。[エラー一覧と共通契約](../api/README.md)に定義する。Cookie/CSRFを使う。
## 5. データ
users、posts、follows。[ER図](../07_er_diagram.md)参照。
## 6. バリデーション / 制約
表示名1〜50文字、自己紹介160文字以内。画像JPEG/PNG・2MiB以下・最大2000万画素。画像検証はF03と同じ共通処理。emailは公開しない。
## 7. エラーハンドリング / 異常系
入力400、権限403、不在404、容量413、形式415、S3失敗503。新画像保存に失敗したら従来の画像を維持。
request/response・HTTP状態・エラーコードは[OpenAPI](../api/openapi.json)に定義したレビュー前の契約案。[受け入れ条件](../acceptance.md)を検証の根拠にする。
