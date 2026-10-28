# 機能定義書 F01: 認証

> 壁打ち用の草案。未承認・未実装・独立レビュー未実施。数値・方式は提案であり、実行結果ではない。

## 1. 概要 / 目的
認証を通じて筋トレ記録と交流を提供する。MyTimelineの同IDの責務を引き継ぎ、記録データ・Python基盤に合わせる。
## 2. 機能詳細
登録後はログイン状態にする。ログインはメール＋パスワード、ログアウトでサーバーセッションを失効。メール認証・パスワード再設定は初版対象外の案。
## 3. 対象画面
SCR-01, SCR-02
## 4. API エンドポイント案
| メソッド | パス |
|---|---|
| GET | `/api/auth/csrf` |
| POST | `/api/auth/signup` |
| POST | `/api/auth/login` |
| POST | `/api/auth/logout` |
| GET | `/api/auth/me` |
共通エラーは `{"code":"...","message":"...","fieldErrors":{},"requestId":"..."}` 案。[エラー一覧と共通契約](../api/README.md)に定義する。Cookie/CSRFを使う。
## 5. データ
users、django_session。[ER図](../07_er_diagram.md)参照。
## 6. バリデーション / 制約
username: 小文字ASCII英数字と_、3〜30文字。予約語me/searchは使用不可。表示名1〜50、メール最大254、パスワード12〜128文字＋Django標準検証。メールの正規化・重複をDB制約で保証。ログイン前のCSRFも必須。
## 7. エラーハンドリング / 異常系
未認証401、CSRF不正403、入力不正400、重複409。ログイン失敗理由を細分化してユーザー存在を漏らさない。未認証は認証境界で401 AUTH_REQUIREDへ統一する。
request/response・HTTP状態・エラーコードは[OpenAPI](../api/openapi.json)に定義したレビュー前の契約案。[受け入れ条件](../acceptance.md)を検証の根拠にする。
