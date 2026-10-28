# FL-01 backend / ローカル運用

このREADMEは起動・検証の手順書です。実施日時・対象snapshot・image ID・テスト件数は、
v9 verifyの保存結果とPRの検証欄を正本とします。手順の記載だけで合格を示しません。

参照する設計は [FL-01](../docs/fl-01-foundation-design.md)、API正本は
[OpenAPI](../docs/api/openapi.json)。仕様原本・manifest・plan・project.toml・承認状態は今回変更しない。
下記は後続作業の手順であり、実行済みの記録ではない。
今回のbootstrap継続では保持済みlockと固定イメージ参照を使用し、check・build・test・migration・
サーバー起動・Git操作を実行していない。生成物は後続verifyへの入力であり、品質合格の証拠ではない。

## 構成

Python 3.13 / Django 5.2 / DRF 3.16 / PostgreSQL 17。
`accounts.User` はAbstractUserを継承し、初回migrationからUUID主キー。
登録・ログイン・email制約などは後続タスク。認証APIは公開しない。

`GET /api/health/live` はDB非依存。`GET /api/health/ready` はDBのSELECT 1と
未適用migrationなしを条件に200を返す。不成立は503の `{"status":"unavailable"}`。
接続timeoutは5秒。readyのatomic内だけstatement timeoutを2秒にし、DB例外はatomicの外で捕捉する。
DB以外の未知障害は共通500。すべてのAPI応答にサーバー生成UUIDのX-Request-Id。
受信した同名ヘッダーは採用しない。

例外分類・文言は `common/errors.py`。既知の400/401/403/404/405/406/415/429を固定JSONへ変換し、
未知例外は500 INTERNAL_ERROR。health POSTは405＋Allow。
CSRF識別済み拒否はCSRF_FAILED。認証/CSRFの製品機能そのものは後続タスク。
DEBUG両モードでもAPIへHTMLエラーを返さない。例外本文・接続文字列・リクエスト本文をログに書かない。
ログには固定イベント、HTTP status、サーバー生成request-idだけを残す。

Django単体起動時にもDJANGO_SECRET_KEYは空・未設定なら失敗。DEBUG既定false。
ALLOWED_HOSTSはlocalhost/127.0.0.1/backendのみ。Compose内のキーとDBパスワードは
公開されたローカル専用サンプルであり、本番用に流用しない。

## 依存lock・イメージ固定

具体版とmanifest digestは[image-pins.json](image-pins.json)に記録し、公式registryへ
`docker buildx imagetools inspect`して対応を照合した。Composeと各Dockerfileに同じ参照値を固定済み。
アプリの起動・verifyにFITLOG_*_IMAGE環境変数の設定は不要。
Python依存はuv.lock、JS依存はfrontend/package-lock.jsonへ固定した。これだけでは品質合格にならない。

依存を更新するときは、公式配布元の互換性を確認してイメージ参照を揃え、次の隔離buildでlockを再生成する。
ビルドcontextは各依存manifestだけに制限し、出力はlockファイルだけ。hostの既存Python/Node環境を変更しない。

```sh
docker build --file backend/Lockfile.Dockerfile --output type=local,dest=backend .
docker build --file frontend/Lockfile.Dockerfile --output type=local,dest=frontend .
```

通常のアプリbuildはuv sync --locked/npm ciを使い、lock欠落・不整合を失敗にする。
lock更新後は両アプリを再buildして全checkを実行する。失敗を隠して別スタックへ変えない。

## 開発起動・migration・停止

以下はlockとイメージ固定を完了してから。Compose project名は常にfitlog-dev。
初回の操作前に `lsof -nP -iTCP:18080 -sTCP:LISTEN` と
`lsof -nP -iTCP:15173 -sTCP:LISTEN` でポートの使用者を調べる。
占有されているときは別プロジェクトを止めず報告する。既存FitLogも稼働状態を把握してから操作する。
同時に複数セッションからComposeを操作しない。

```sh
docker compose --project-name fitlog-dev -f compose.yaml build backend frontend
docker compose --project-name fitlog-dev -f compose.yaml up -d --no-recreate --wait --wait-timeout 60 postgres
docker compose --project-name fitlog-dev -f compose.yaml run --rm --no-deps backend uv run --frozen --no-sync python manage.py migrate --noinput
docker compose --project-name fitlog-dev -f compose.yaml up -d --no-deps backend frontend
```

frontendは `http://127.0.0.1:15173`、backendは `http://127.0.0.1:18080`。
DBのhost公開はない。frontendの/apiはbackendへproxyする。
コード・lockを変更するたびに必ず両イメージを再buildする。
ソース、hostの.venvやnode_modulesはbind mountしない。

通常停止は**そのセッションで起動したサービスだけ**を `stop` の引数へ指定する。
たとえば3サービスすべてを今回起動した場合のみ次のコマンドとなる。

```sh
docker compose --project-name fitlog-dev -f compose.yaml stop frontend backend postgres
```

`down -v` は通常停止に使わない。DB volumeは保持し、削除は個別に判断する別操作。
既存volumeの中身を空DBと扱わない。開発DBの初回migrationか既存DBへの適用かを区別して記録する。

## 後続verifyのDB準備と後片付け

`.ai-dev/checks.proposed.toml` は予定11件の提案のみ。checks登録もplan再承認も別の手順。
仕様・計画・実装・独立レビューの承認やGit操作をこのREADMEで代替しない。

verifyを起動する担当者は、次の順序とfinally相当の後片付けを守る。

1. `docker compose --project-name fitlog-dev -f compose.yaml ps --all --format json postgres`
   を読み、開始前にStateがrunningだったかをメモリ内に保持する。
   結果が複数・不明・restarting等なら調査し、勝手に停止しない。
   既存イメージIDとサービス状態も把握する。
2. `docker compose --project-name fitlog-dev -f compose.yaml up -d --no-recreate --wait --wait-timeout 60 postgres`
   を実行する。終了コードと再度psのState/Healthを確認し、running/healthyでなければverifyを開始しない。
3. 正式なconfigure-checksとplan再承認後、provider-freeのverifyで登録11件を実行する。
   先頭のcompose-buildが現在のsourceとlockから両イメージをbuildする。
   build失敗なら後続checkへ進めず不合格。backend/frontendのdevサーバー起動は不要。
4. check間にsource、lock、イメージtagを変えない。
   `docker image inspect --format '{{.Id}}' fitlog-dev-backend` と同frontendのIDを、
   compose-build結果・対象snapshotとともに検証記録へ残す。
5. 成功・失敗どちらでもfinallyで、開始前が停止/未作成だった場合だけ
   `docker compose --project-name fitlog-dev -f compose.yaml stop postgres`。
   開始前からrunningなら停止しない。別セッションの競合が見つかったら停止処理を控えて報告する。

DB準備の途中で失敗した場合も、停止していたDBを今回起動したことが確かな場合だけ後片付けする。
初期状態が不明なら既存サービスを勝手に止めない。

## checks・独立オラクル

全checkは `.ai-dev/fl-01.plan.json` のargvと順番を提案へ写したもの。
実行結果はv9 verifyの保存結果とPRの検証欄を参照してください。各runは `--rm --no-deps`、host portを追加で確保しない。

| 順番 | check | 検出する対象 |
|---|---|---|
| 1 | compose-build | source/lockから両イメージをbuild、不整合・欠落を失敗にする |
| 2 | backend-lint | Ruff E4/E7/E9/F/I/B/UP |
| 3 | backend-types | mypy strict＋Django/DRF stubs |
| 4 | django-check | Django system check |
| 5 | backend-migrate | 開発PostgreSQLへmigration |
| 6 | migration-drift | makemigrations --check --dry-run |
| 7 | backend-tests | PostgreSQL・UUID・migration再実行・health・契約・例外 |
| 8 | frontend-lint | ESLint |
| 9 | frontend-types | TypeScript strict |
| 10 | frontend-tests | roleと固定文言によるDOM状態・timeout・unmount |
| 11 | frontend-build | TypeScript＋Vite build |

`uv sync --locked --all-groups` はbuild時だけ。checkでは必ず `uv run --frozen --no-sync` を使う。
missing toolをverify中にinstallしない。テストDBはpytest-djangoが新規作成するPostgreSQLのtest_fitlog。
開発用DBと同じ名前、SQLite、--reuse-db、--nomigrationsへ切り替えない。
初回migrationと再適用の未適用ゼロ、UUIDの保存・再取得をassertする。
DB障害と未適用migrationは注入してHTTPを確認し、共有DBを停止しない。

OpenAPI正本はbuild時 `/app/contracts/openapi.json` へCOPYする。テストはそのschemaと
固定の設計期待値を照合する。テスト設計の根拠は [TEST-ORACLES](tests/TEST-ORACLES.md)。
静的チェック、テスト、buildは省略して成功にできず、0件やskipも完了の代用にはならない。
