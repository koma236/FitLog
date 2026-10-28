# 3. 技術スタック

> 壁打ち用の草案。未承認・未実装・独立レビュー未実施。数値・方式は提案であり、実行結果ではない。

MyTimelineの参照コミットは `fd9f00b1eb8e7211a577babd72690c7848bbcff7`。以下は採用提案であり、依存関係のインストール・バージョン固定は未実施。

## フロントエンド
React＋TypeScript＋Viteを継続する案。ルーター、CSS、HTTPクライアント、テスト構成は基盤Issueで互換性確認後に固定する。MyTimelineのパッチバージョンを無検証でコピーしない。
選定理由：記録フォームの増分に集中し、バックエンドの違いを比較しやすくする。Vueへの全面変更は追加学習になるが、今回必須ではない。

## バックエンド
| MyTimeline | FitLog案 | 学べる違い |
|---|---|---|
| Java / Spring Boot | Python / Django＋Django REST framework | 言語、HTTP処理、Serializer、サービスの責務 |
| MyBatis | Django ORM | SQL中心とモデル中心のデータ操作、N+1対策 |
| Flyway | Django migrations | スキーマの変更・制約の管理 |
| JWT＋refresh token | DB保存のセッション＋CSRF対策 | 認証方式の比較、失効とCookie管理 |
| Gradle / JUnit | uv / pytest＋pytest-django | 依存管理、単体・DB結合テスト |
| Checkstyle / SpotBugs | Ruff＋型チェック | Pythonの静的検証 |

PythonとDjangoのサポート中の組合せを採用し、DRF・画像処理・DBドライバの互換性を確認してlockする。セッション認証は同一オリジンを前提とする。ログイン自体にもCSRF検査を適用する。JWTを独自実装しない。

## データベース・ローカル実行
PostgreSQLを継続し、ローカルとAWSで同じメジャーを使う。Docker ComposeでDB・API・S3互換ストレージを起動する案。開発ポートと実checksは未設定であり、基盤構築後に実行確認して登録する。

## ストレージ
AWS S3の非公開バケット。Python側で画像を検証してアップロードし、DBにキーを保存する。ローカルはS3互換環境を使う案。具体イメージは配布・保守状況を確認して固定する。

## 本番相当インフラ（AWS）
Terraformで作成・破棄。公開URLはMyTimelineと同じCloudFront提供ドメイン（`https://<distribution>.cloudfront.net`）と既定証明書を使うことで確定。独自ドメイン・Route 53 hosted zone・独自証明書の購入や作成は不要。
主要サービスはCloudFront/S3＋ALB＋ECS Fargate＋RDS PostgreSQL＋画像S3を提案する。低費用化のためFargateの外向き通信でNAT Gatewayを省く案を推奨する。ネットワークの採用判断は独立設計レビューを経て行う。[インフラ設計](09_infrastructure.md)を参照。

## 公式資料
- [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/)
- [DRF SessionAuthentication](https://www.django-rest-framework.org/api-guide/authentication/#sessionauthentication)
- [MyTimelineの技術スタック](https://github.com/koma236/MyTimeline/blob/fd9f00b1eb8e7211a577babd72690c7848bbcff7/docs/02_tech_stack.md)
