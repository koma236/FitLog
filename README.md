# FitLog

筋トレの記録と、日々のトレーニングの共有ができる個人開発のWebアプリです。

## デモ動画

約3分で、新規登録からプロフィール編集、トレーニング記録・編集、ユーザー検索・フォロー、タイムライン、いいね・コメント、ログアウトまでを紹介します。カーソル付き・撮影用データで収録しています。

https://github.com/user-attachments/assets/ab8f2915-3b8a-4c3f-be9f-5c6cd9c9f765

## 主な機能

| 機能 | 内容 | 状態 |
|---|---|---|
| アカウント | メールアドレスとパスワードで新規登録・ログイン・ログアウト | 実装済み |
| プロフィール | 表示名・自己紹介・アバター、身体情報と項目別の公開設定 | 実装済み |
| トレーニング記録 | 種目・重量・回数・セット・運動時間・メモ・画像を記録し、自分の記録を編集・削除 | 実装済み |
| カロリー推定 | プロフィールと運動内容に応じた消費カロリーの推定表示 | 実装済み（参考値） |
| タイムライン | 「フォロー中」（自分とフォロー先）・「すべて」の切り替え、カーソルによる追加取得 | 実装済み |
| ユーザー検索・交流 | ユーザー検索、フォロー、投稿へのいいね・コメント、自分のコメントの編集・削除 | 実装済み |

新規登録後はそのままログインします。確認メールの送信・メールアドレスの所有確認は未実装です。カロリーは参考値として表示します。

投稿はログインした利用者間で共有します。投稿全体を非公開・フォロワー限定にする機能はありません。身体情報などの項目別の公開設定と、記録の運動時間・運動種別の公開設定は、投稿全体の公開範囲とは別です。

## 技術スタック

| 領域 | 技術 |
|---|---|
| フロントエンド | React / React DOM 19.3.1、TypeScript 5.9.3、Vite 7.3.7、Node.js 24.22.1 |
| バックエンド | Python 3.13.18、Django 5.2.18、Django REST framework 3.18.3、Django ORM、uv 0.13.6 |
| 認証 | DB保存のDjangoセッション / CSRF対策（Django同梱） |
| データベース | PostgreSQL 17.11（ローカル）/ Django migrations（Django同梱） |
| 画像 | Pillow 13.0.0で検証・変換、ローカルは非公開Docker volume、AWS向けは非公開S3 |
| 開発環境 | Docker / Docker Compose（リポジトリではバージョン未固定） |
| テスト・静的検査 | pytest 8.4.2 / pytest-django 4.14.0 / Vitest 3.2.7 / Testing Library（React 16.3.3、jest-dom 6.9.1）/ Ruff 0.17.3 / mypy 1.19.1 / ESLint 9.39.5 / TypeScript 5.9.3 |
| ブラウザ・性能検証 | Playwright 1.65.0 / k6（リポジトリではバージョン未固定） |
| AWS向け構成 | Terraform 1.15.1 / AWS provider 6.71.0 / CloudFront / S3 / ALB / ECS Fargate（Gunicorn 25.3.0）/ RDS PostgreSQL 17系（適用時に版を指定） |

ライブラリの版は [frontend/package-lock.json](frontend/package-lock.json)・[backend/uv.lock](backend/uv.lock)・[e2e/package-lock.json](e2e/package-lock.json) の解決済みバージョンです。TypeScriptはフロントエンドが5.9.3、E2Eが5.9.2です。Django ORM・セッション・migrationsはDjango同梱の機能です。

Node.js・Python・uv・ローカルPostgreSQLの版は [compose.yaml](compose.yaml) と [frontend/Dockerfile](frontend/Dockerfile)・[backend/Dockerfile](backend/Dockerfile) の固定イメージに基づきます。開発用ポートもComposeで固定しています。

Terraformの版は [versions.tf](terraform/versions.tf)、AWS providerの解決済み版は [provider lock](terraform/.terraform.lock.hcl) が根拠です。RDSのPostgreSQLは [postgres_engine_version](terraform/variables.tf) で17系の具体的なマイナーバージョンを適用時に指定し、ローカルの17.11と同一とは限りません。AWS構成の定義と実環境で確認した範囲は、後述の「AWS構成」で区別しています。

## ディレクトリ構成

```text
FitLog/
├── backend/          # Django：accounts / workouts / social / media_assets / operations
│   ├── config/       # 設定・APIルーティング
│   └── common/       # エラー・health・ログなどの共通処理
├── frontend/src/     # React：画面・認証・API呼び出し・表示部品
├── docs/             # 要件・機能設計・API契約・検証結果
├── documents/        # 開発・品質・セットアップの手順
├── terraform/        # AWS向けの構成定義とmock検証
├── scripts/          # ローカルchecks・配置・検証の補助
├── e2e/              # Playwrightとブラウザ検証の制御
├── perf/             # k6の負荷試験
├── .github/workflows/ # GitHub Actions
└── compose.yaml      # PostgreSQL / backend / frontend
```

## ローカル開発環境のセットアップ

Git、Docker、Docker Composeが必要です。アプリと依存はコンテナ内で動くため、起動にホスト側のPython・Node.jsやAWS資格情報は不要です。

```bash
git clone https://github.com/koma236/FitLog.git
cd FitLog
```

以降はリポジトリのルートで実行します。ローカル用の環境変数は `compose.yaml` に定義済みです。この設定値はローカル専用です。

```bash
docker compose build
docker compose up -d postgres
docker compose run --rm backend uv run --frozen --no-sync python manage.py migrate
docker compose up -d backend frontend
```

ブラウザで [http://localhost:15173](http://localhost:15173) を開き、新規登録してください。APIは `http://localhost:18080` で起動します。いずれもローカルからの接続に限定しています。

停止するときは次を実行します。DBと画像のDocker volumeは保持されます。

```bash
docker compose down
```

複数のworktreeで作業する場合は、固定ポートとDB・imageの競合を避けるため、[並列開発運用](documents/development/personal-parallel-workflow.md)を先に確認してください。

### 品質チェックとCI

ローカルのbuild・lint・型検査・テスト・migrationは、[11チェックのコマンド台帳](.ai-dev/project.toml)に登録しています。[実行手順](documents/development/run-checks.md)の共通Git領域・共有runtimeの事前確認を済ませ、Python 3.11以降のホスト環境で実行します。チェック用スクリプトは専用の作業ブランチで使用します。

```bash
python3 -B scripts/run-checks.py
```

この入口は共有runtimeの排他、DB状態とmigration履歴の確認、全11件の順次実行、結果保存、今回起動したDBの停止を担当します。既存DBの初期化やvolume削除は行いません。

[GitHub Actions](.github/workflows/ci.yml)はPRとmainへのpushで次を検査し、`ci-required` に集約します。

| ジョブ | 主な検査 |
|---|---|
| backend | イメージbuild、Ruff、mypy、Django check、空DBへのmigration、migration差分、pytest |
| frontend | イメージbuild、CI配線の検査、ESLint、TypeScript、Vitest、フロントエンドbuild |
| terraform | AWS資格情報を使わない構成検査・mockテスト・CloudFront Functionテスト |

CIやmockの成功は、実AWSの権限・公開経路・負荷性能の実証とは別です。

## 主要API

実装済みAPIの概要です。パス末尾の `/` は付けません。詳細な入出力・エラー・ヘッダーは [API契約](docs/api/README.md)と [OpenAPI](docs/api/openapi.json) を参照してください。ルーティングの実装は [backend/config/urls.py](backend/config/urls.py) です。

| メソッド | パス | 内容 |
|---|---|---|
| GET | `/api/auth/csrf` | CSRFトークン取得 |
| POST | `/api/auth/signup`、`/api/auth/login`、`/api/auth/logout` | 新規登録・ログイン・ログアウト |
| GET | `/api/auth/me` | ログイン中のアカウント |
| GET / PUT | `/api/users/me` | 自分のプロフィール取得・更新 |
| GET | `/api/users/{username}`、`/api/users/{username}/posts` | プロフィール・記録一覧 |
| GET | `/api/users/search` | ユーザー検索 |
| POST / DELETE | `/api/users/{userId}/follow` | フォロー・解除 |
| GET | `/api/timeline/following`、`/api/timeline/all` | タイムライン |
| POST | `/api/posts` | 記録作成 |
| GET / PUT / DELETE | `/api/posts/{id}` | 記録取得・編集・削除 |
| PUT / DELETE | `/api/posts/{id}/image`、`/api/users/me/avatar` | 投稿画像・アバターの添付／差し替え・削除 |
| GET | `/api/media/content/{token}` | 短命な署名トークンによる画像配信 |
| GET / POST | `/api/posts/{postId}/comments` | コメント一覧・作成 |
| GET / PUT / DELETE | `/api/comments/{id}` | コメント取得・編集・削除 |
| POST / DELETE | `/api/posts/{postId}/like` | いいね・取り消し |
| GET | `/api/health/live`、`/api/health/ready` | プロセス・DBとmigrationの状態確認 |

利用者向けの記録・プロフィール・交流APIはログインが必要です。更新系ではCSRF検査を行い、編集・削除は本人のデータに限定します。セッションCookieとCSRFトークンを使う方式で、JWTやrefresh APIは使いません。投稿保存と画像添付は別リクエストです。

## データモデル

Djangoのモデルと各アプリの `migrations/` が現行スキーマの根拠です。主な関係は `User → Post → WorkoutExercise → WorkoutSet` で、1つの記録に複数の種目・セットを持ちます。

| 領域 | 主なモデル | 役割 |
|---|---|---|
| [accounts](backend/accounts/models.py) | `User` / `ProfileHealth` / `AuthRateLimit` | アカウント、身体情報と項目別公開設定、認証試行の制限 |
| [workouts](backend/workouts/models.py) | `PostIdentity` / `Post` / `WorkoutExercise` / `WorkoutSet` | 記録ID、実施日・メモ・カロリー推定、種目、重量・回数・順序 |
| [social](backend/social/models.py) | `CommentIdentity` / `Comment` / `Like` / `Follow` | コメント、いいね、フォロー関係 |
| [media_assets](backend/media_assets/models.py) | `ImageObject` / `PostImage` / `UserAvatar` / `ImageCleanupJob` / `ImageScan` | 画像の状態・添付先、退役画像の清掃と再照合 |

記録・コメントのIDは削除後も再利用を防ぎます。いいねは投稿と利用者の組、フォローは送信元と送信先の組で一意です。自分自身のフォローは禁止しています。画像の実体はDBへ格納せず、保存先キーと状態・検証済みの属性を管理します。

## AWS構成

公開デモ向けに次の構成をTerraformで定義しています。ローカルComposeの構成とは別です。

```text
Browser ── HTTPS ── CloudFront ┬─ 静的ファイル ── 非公開S3（React、OAC）
                              └─ /api/* ── HTTP ── ALB ── ECS Fargate（Django）
                                                            ├─ RDS PostgreSQL（非公開）
                                                            └─ 非公開S3（画像）
```

画像は短命な署名付きアプリURLを通じて、Djangoが非公開ストレージから読み出して配信します。APIの共有キャッシュは無効です。CloudFrontからALBの区間はHTTPで、全区間TLSの構成ではありません。ALBへの入口はCloudFrontの送信元制限と専用ヘッダーで制限します。

構成定義があることと、実環境の検証完了は区別しています。実RDSでは限定的なrollback診断と初期化処理の検査が行われていますが、これだけでアプリ全経路の動作確認完了とはしていません。常設サービスとしての稼働・公開URLは、このREADMEでは案内していません。

## 運用（ログ・監視・障害対応）

API応答の `X-Request-Id` とログを照合して調査します。バックエンドは許可した項目だけのログを出力し、`FITLOG_LOG_FORMAT=text`（既定）または `json` を選択できます。パスワード・Cookie・健康値・投稿本文・画像URLなどはログへ出しません。

`/api/health/live` はプロセス、`/api/health/ready` はDB疎通と必要なmigrationを確認します。readyは画像ストレージの状態までは検査しません。画像の退役・孤立データは `cleanup_images` 管理コマンドで再照合・清掃する仕組みです。実行時は共有runtimeの排他手順に従います。

常時の通知・24時間対応を約束する運用ではありません。ログの形式・監視項目・障害時の切り分けは次の資料にまとめています。

- [ログ設計](docs/10_logging_design.md)
- [ヘルスチェックと運用監視](docs/11_monitoring_design.md)
- [障害対応手順](docs/12_incident_response.md)

## 関連ドキュメント

- [API共通契約・エラー一覧](docs/api/README.md)・[OpenAPI](docs/api/openapi.json)
- [記録の機能仕様・実装契約](docs/features/F03_post.md)・[タイムラインの実装設計](docs/fl-07-timeline-design.md)
- [ブラウザ検証の設計](docs/fl-10a-design.md)・[実行結果](docs/fl-10a-results.md)
- [ローカル性能検証の結果](docs/fl-10b-local-results.md)
- [受け入れ条件と検証範囲](docs/acceptance.md)
- [実行可能な11チェック](.ai-dev/project.toml)・[実行手順](documents/development/run-checks.md)・[GitHub ActionsのCI](.github/workflows/ci.yml)
- [個人開発運用・マージ条件](documents/development/personal-workflow.md)・[相互レビュー手順](documents/development/cross-review.md)

検証結果は各資料に記載した対象・時点の範囲です。デモ動画の収録は、受け入れ条件の全項目の合格を意味しません。`docs/` には初期草案も残しており、草案の構成案・予定を実装済みの機能や検証結果として扱わないでください。
