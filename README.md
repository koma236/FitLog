# FitLog

筋トレの記録と、日々のトレーニングの共有ができる個人開発のWebアプリです。

## デモ動画

約3分で、新規登録からプロフィール編集、トレーニング記録・編集、ユーザー検索・フォロー、タイムライン、いいね・コメント、ログアウトまでを紹介します。カーソル付き・撮影用データで収録しています。

https://github.com/user-attachments/assets/ab8f2915-3b8a-4c3f-be9f-5c6cd9c9f765

## 主な機能

| 機能 | 内容 |
|---|---|
| アカウント | メールアドレスとパスワードで新規登録・ログイン・ログアウト |
| プロフィール | 表示名・自己紹介・アバター、身体情報、公開範囲の設定 |
| トレーニング記録 | 種目・重量・回数・セット・運動時間・メモ・画像を記録し、編集・削除 |
| カロリー推定 | プロフィールと運動内容に応じた消費カロリーの推定表示 |
| タイムライン | 「フォロー中」「すべて」の切り替えと、公開範囲に応じた投稿の表示 |
| ユーザー検索・交流 | ユーザー検索、フォロー、投稿へのいいね・コメント |

新規登録後はそのままログインします。確認メールの送信・メールアドレスの所有確認は未実装です。カロリーは参考値として表示します。

## 技術構成

| 領域 | 技術 |
|---|---|
| フロントエンド | React / TypeScript / Vite |
| バックエンド | Python / Django |
| データベース | PostgreSQL |
| 開発環境 | Docker Compose |
| テスト・静的検査 | pytest / Vitest / Ruff / mypy / ESLint / TypeScript |

## ローカルで動かす

DockerとDocker Composeが必要です。リポジトリのルートで実行します。

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

## 検証・開発資料

- [実行可能な11チェック](.ai-dev/project.toml)と[ローカル検証の実行手順](documents/development/run-checks.md)
- [GitHub ActionsのCI](.github/workflows/ci.yml)：build・lint・型・全テスト・migrationを検査し、`ci-required` に集約
- [ブラウザ検証の設計](docs/fl-10a-design.md)・[実行結果](docs/fl-10a-results.md)
- [ローカル性能検証の結果](docs/fl-10b-local-results.md)
- [受け入れ条件と検証範囲](docs/acceptance.md)
- [個人開発運用・マージ条件](documents/development/personal-workflow.md)・[相互レビュー手順](documents/development/cross-review.md)

検証結果は各資料に記載した対象・時点の範囲です。デモ動画の収録は、受け入れ条件の全項目の合格を意味しません。
