# FL-10B ローカル性能試験結果

最終更新2026-11-07、Issue #55。[仕様](13_performance_test.md)、[実行](../perf/README.md)。
ローカル実アプリの結果。AWS/S3/CloudFront/ALB/RDS/Gunicornの実性能はnot_run。

## load / normal

- 状態: pass / cleanup: pass
- 実行: 2026-11-06T17:15:40.731278+00:00 ～ 2026-11-06T17:21:54.047299+00:00（UTC。JSTは+09:00）
- 一次データ: `docs/superpowers/plans/perf-results/938a7d05bf2a456eb7d4dea4cb302fba/results.json` と同folderのrequests.jsonl/ownership.json
- source: `626c81b2ff00a649b378e370a44402486036f583` + source SHA-256 `e27694f6e60ca7a8175f43e5e549954535141eed38117d6d117650d185344bf5`
- 環境: macOS-26.5.2-x86_64-i386-64bit / x86_64、Docker CPU 8 / memory 8321994752 bytes
- backend: `sha256:02256cd305bcd485396e1c94e5e1052e7f4e356d79adda8c786368a166b42b7b`、Django runserver --noreload; DEBUG=false; 1GiB
- PostgreSQL: `postgres:17.11-bookworm@sha256:d2b1a0795f5ecbe49dc07be0b35b62977aff9152870ea332375021c79ea4905b`
- 版: `{"python": "3.13.18", "django": "5.2.18", "psycopg": "3.3.6", "pillow": "13.0.0"}`
- 前件数: `{"users": 5, "posts": 1000, "exercises": 3000, "sets": 9000, "comments": 2000, "likes": 2000, "follows": 10, "posts_per_user": [200, 200, 200, 200, 200]}`
- 後件数: `{"users": 5, "posts": 1000, "exercises": 3000, "sets": 9000, "comments": 2000, "likes": 2005, "follows": 10, "posts_per_user": [200, 200, 200, 200, 200]}`
- 全run時間: 373.34秒（構築/seed/認証/smoke/warmup/cleanupを含む）

測定窓300秒、5人/毎秒5予定要求、warmup30秒除外。1500/1500完了、missed=0。

| API / method | n | p50 ms | p95 ms | p99 ms | 失敗率 | 5xx率 |
|---|---:|---:|---:|---:|---:|---:|
| all GET | 300 | 77.54 | 111.89 | 125.63 | 0.00% | 0.00% |
| detail GET | 300 | 53.90 | 76.54 | 82.85 | 0.00% | 0.00% |
| following GET | 300 | 80.59 | 134.29 | 202.96 | 0.00% | 0.00% |
| like DELETE | 75 | 50.48 | 58.29 | 65.22 | 0.00% | 0.00% |
| like POST | 75 | 52.10 | 98.23 | 105.95 | 0.00% | 0.00% |
| search GET | 150 | 50.26 | 64.36 | 66.21 | 0.00% | 0.00% |
| update PUT | 150 | 70.93 | 103.05 | 145.42 | 0.00% | 0.00% |
| user GET | 150 | 76.54 | 91.77 | 138.33 | 0.00% | 0.00% |

CPU/memory: 56回のdocker stats（backend/専用DB）をresults.jsonに保存。取得失敗 0回。

## load / boundary

- 状態: pass / cleanup: pass
- 実行: 2026-11-06T17:22:04.875947+00:00 ～ 2026-11-06T17:28:26.130142+00:00（UTC。JSTは+09:00）
- 一次データ: `docs/superpowers/plans/perf-results/c24d65651e0a49b78588ac7a45f38a88/results.json` と同folderのrequests.jsonl/ownership.json
- source: `626c81b2ff00a649b378e370a44402486036f583` + source SHA-256 `e27694f6e60ca7a8175f43e5e549954535141eed38117d6d117650d185344bf5`
- 環境: macOS-26.5.2-x86_64-i386-64bit / x86_64、Docker CPU 8 / memory 8321994752 bytes
- backend: `sha256:02256cd305bcd485396e1c94e5e1052e7f4e356d79adda8c786368a166b42b7b`、Django runserver --noreload; DEBUG=false; 1GiB
- PostgreSQL: `postgres:17.11-bookworm@sha256:d2b1a0795f5ecbe49dc07be0b35b62977aff9152870ea332375021c79ea4905b`
- 版: `{"python": "3.13.18", "django": "5.2.18", "psycopg": "3.3.6", "pillow": "13.0.0"}`
- 前件数: `{"users": 5, "posts": 1000, "exercises": 10000, "sets": 200000, "comments": 2000, "likes": 2000, "follows": 10, "posts_per_user": [200, 200, 200, 200, 200]}`
- 後件数: `{"users": 5, "posts": 1000, "exercises": 10000, "sets": 200000, "comments": 2000, "likes": 2005, "follows": 10, "posts_per_user": [200, 200, 200, 200, 200]}`
- 全run時間: 381.28秒（構築/seed/認証/smoke/warmup/cleanupを含む）

測定窓300秒、5人/毎秒5予定要求、warmup30秒除外。1500/1500完了、missed=0。

| API / method | n | p50 ms | p95 ms | p99 ms | 失敗率 | 5xx率 |
|---|---:|---:|---:|---:|---:|---:|
| all GET | 300 | 243.38 | 390.38 | 588.80 | 0.00% | 0.00% |
| detail GET | 300 | 66.93 | 124.51 | 187.28 | 0.00% | 0.00% |
| following GET | 300 | 261.40 | 479.27 | 833.93 | 0.00% | 0.00% |
| like DELETE | 75 | 56.67 | 232.03 | 234.59 | 0.00% | 0.00% |
| like POST | 75 | 57.88 | 342.85 | 359.28 | 0.00% | 0.00% |
| search GET | 150 | 56.21 | 180.47 | 239.61 | 0.00% | 0.00% |
| update PUT | 150 | 131.30 | 296.83 | 334.21 | 0.00% | 0.00% |
| user GET | 150 | 268.65 | 352.18 | 402.16 | 0.00% | 0.00% |

CPU/memory: 56回のdocker stats（backend/専用DB）をresults.jsonに保存。取得失敗 0回。

## image / normal

- 状態: pass / cleanup: pass
- 実行: 2026-11-06T17:32:43.590805+00:00 ～ 2026-11-06T17:33:29.539529+00:00（UTC。JSTは+09:00）
- 一次データ: `docs/superpowers/plans/perf-results/b0a36a1a877b4c309fde09a7af962b79/results.json` と同folderのrequests.jsonl/ownership.json
- source: `626c81b2ff00a649b378e370a44402486036f583` + source SHA-256 `04f3a799d5f3e30c59d996e2caceec31359c69d2ab05b64f6d4e105dc7aab505`
- 環境: macOS-26.5.2-x86_64-i386-64bit / x86_64、Docker CPU 8 / memory 8321994752 bytes
- backend: `sha256:02256cd305bcd485396e1c94e5e1052e7f4e356d79adda8c786368a166b42b7b`、Django runserver --noreload; DEBUG=false; 1GiB
- PostgreSQL: `postgres:17.11-bookworm@sha256:d2b1a0795f5ecbe49dc07be0b35b62977aff9152870ea332375021c79ea4905b`
- 版: `{"python": "3.13.18", "django": "5.2.18", "psycopg": "3.3.6", "pillow": "13.0.0"}`
- 前件数: `{"users": 5, "posts": 1000, "exercises": 3000, "sets": 9000, "comments": 2000, "likes": 2000, "follows": 10, "posts_per_user": [200, 200, 200, 200, 200]}`
- 後件数: `{"users": 5, "posts": 1000, "exercises": 3000, "sets": 9000, "comments": 2000, "likes": 2000, "follows": 10, "posts_per_user": [200, 200, 200, 200, 200]}`
- 全run時間: 45.98秒（構築/seed/認証/smoke/warmup/cleanupを含む）

直列60測定要求、入力/出力を分離。1秒閾値の対象外。内容はRGB画素digestで照合。

| 分類 | n | p50 ms | p95 ms | p99 ms |
|---|---:|---:|---:|---:|
| image-1320 GET | 10 | 34.40 | 103.40 | 103.40 |
| image-1320 PUT | 10 | 336.93 | 726.54 | 726.54 |
| image-147 GET | 10 | 8.37 | 14.15 | 14.15 |
| image-147 PUT | 10 | 47.56 | 64.99 | 64.99 |
| image-590 GET | 10 | 10.98 | 29.36 | 29.36 |
| image-590 PUT | 10 | 80.67 | 140.45 | 140.45 |
- 147px: input 65057 bytes、output 65047 bytes、GET平均 6999934 bytes/秒（body全受信まで）。
- 590px: input 1045273 bytes、output 1046348 bytes、GET平均 78332776 bytes/秒（body全受信まで）。
- 1320px: input 5230178 bytes、output 5235898 bytes、GET平均 104987910 bytes/秒（body全受信まで）。

CPU/memory: 4回のdocker stats（backend/専用DB）をresults.jsonに保存。取得失敗 0回。

## auth-burst / normal

- 状態: pass / cleanup: pass
- 実行: 2026-11-06T17:31:52.578356+00:00 ～ 2026-11-06T17:32:15.554558+00:00（UTC。JSTは+09:00）
- 一次データ: `docs/superpowers/plans/perf-results/245980def7ed43e4a61c3cbaf9f633ea/results.json` と同folderのrequests.jsonl/ownership.json
- source: `626c81b2ff00a649b378e370a44402486036f583` + source SHA-256 `04f3a799d5f3e30c59d996e2caceec31359c69d2ab05b64f6d4e105dc7aab505`
- 環境: macOS-26.5.2-x86_64-i386-64bit / x86_64、Docker CPU 8 / memory 8321994752 bytes
- backend: `sha256:02256cd305bcd485396e1c94e5e1052e7f4e356d79adda8c786368a166b42b7b`、Django runserver --noreload; DEBUG=false; 1GiB
- PostgreSQL: `postgres:17.11-bookworm@sha256:d2b1a0795f5ecbe49dc07be0b35b62977aff9152870ea332375021c79ea4905b`
- 版: `{"python": "3.13.18", "django": "5.2.18", "psycopg": "3.3.6", "pillow": "13.0.0"}`
- 前件数: `{"users": 5, "posts": 1000, "exercises": 3000, "sets": 9000, "comments": 2000, "likes": 2000, "follows": 10, "posts_per_user": [200, 200, 200, 200, 200]}`
- 後件数: `{"users": 5, "posts": 1000, "exercises": 3000, "sets": 9000, "comments": 2000, "likes": 2000, "follows": 10, "posts_per_user": [200, 200, 200, 200, 200]}`
- 全run時間: 23.00秒（構築/seed/認証/smoke/warmup/cleanupを含む）

- 正規login 10、期待429 1。通常性能分母に含めない。

CPU/memory: 1回のdocker stats（backend/専用DB）をresults.jsonに保存。取得失敗 0回。

## 実行履歴と制限

| mode/scenario | started UTC | status | cleanup | local evidence folder |
|---|---|---|---|---|
| smoke/normal | 2026-11-06T16:53:34.997939+00:00 | fail | OSError | 1797dc3525f745dbb6d8e7cb2011fbb4 |
| smoke/normal | 2026-11-06T16:56:09.448936+00:00 | pass | pass | 28cb0e104a784a959a253a865d1cd693 |
| load/normal | 2026-11-06T16:59:59.793328+00:00 | pass | pass | 00ad495d502b49fd96af81c73f421fd6 |
| image/normal | 2026-11-06T17:08:10.951172+00:00 | pass | pass | 05f92f46a6b94e618e95e2ed100e692c |
| load/normal | 2026-11-06T17:15:40.731278+00:00 | pass | pass | 938a7d05bf2a456eb7d4dea4cb302fba |
| load/boundary | 2026-11-06T17:22:04.875947+00:00 | pass | pass | c24d65651e0a49b78588ac7a45f38a88 |
| auth-burst/normal | 2026-11-06T17:31:52.578356+00:00 | pass | pass | 245980def7ed43e4a61c3cbaf9f633ea |
| image/normal | 2026-11-06T17:32:43.590805+00:00 | pass | pass | b0a36a1a877b4c309fde09a7af962b79 |

最初のsmokeは資源作成前のTIME_WAIT判定で失敗。試験側を修正し、PID終了・空資源台帳・該当containerなしを確認して自分のlockだけ返却した。失敗記録を保持している。
初回通常loadは内容検証時間も含めたため参考扱い。最終loadはbody全受信までで再測定した。
実行時は未commit source。ファイル別hash一覧はdocs/superpowers/plans/perf-snapshots/に保存。後続の文書変更と計測対象コードを区別して照合する。
ローカル結果をAWS実証へ読み替えない。撮影・2構築/破棄・後日請求確認は未完了。
