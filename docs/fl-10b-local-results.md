# FL-10B ローカル性能試験結果

最終更新2026-11-07、Issue #55。[仕様](13_performance_test.md)、[実行](../perf/README.md)。
ローカル実アプリの結果。AWS/S3/CloudFront/ALB/RDS/Gunicornの実性能はnot_run。

## load / normal

- 状態: pass / cleanup: pass
- 実行: 2026-11-06T17:59:05.279147+00:00 ～ 2026-11-06T18:05:19.092555+00:00（UTC。JSTは+09:00）
- 一次データ: `docs/superpowers/plans/perf-results/66ef4f0975ab4ea3b009ba2286d3c5c9/results.json` と同folderのrequests.jsonl/ownership.json
- source: `43baf4353acf74eec0170660cfd953d78d0c8a90` + source SHA-256 `48e91a5ce4139d4b213c7fc20c0838354f933e2626fb43dac122ad599f33f1fb`
- 環境: macOS-26.5.2-x86_64-i386-64bit / x86_64、Docker CPU 8 / memory 8321994752 bytes
- backend: `sha256:02256cd305bcd485396e1c94e5e1052e7f4e356d79adda8c786368a166b42b7b`、Django runserver --noreload; DEBUG=false; 1GiB
- PostgreSQL: `postgres:17.11-bookworm@sha256:d2b1a0795f5ecbe49dc07be0b35b62977aff9152870ea332375021c79ea4905b`
- 版: `{"python": "3.13.18", "django": "5.2.18", "psycopg": "3.3.6", "pillow": "13.0.0"}`
- 前件数: `{"users": 5, "posts": 1000, "exercises": 3000, "sets": 9000, "comments": 2000, "likes": 2000, "follows": 10, "posts_per_user": [200, 200, 200, 200, 200]}`
- 後件数: `{"users": 5, "posts": 1000, "exercises": 3000, "sets": 9000, "comments": 2000, "likes": 2005, "follows": 10, "posts_per_user": [200, 200, 200, 200, 200]}`
- 全run時間: 373.84秒（構築/seed/認証/smoke/warmup/cleanupを含む）

測定窓300秒、5人/毎秒5予定要求、warmup30秒除外。1500/1500完了、missed=0。

| API / method | n | p50 ms | p95 ms | p99 ms | 失敗率 | 5xx率 |
|---|---:|---:|---:|---:|---:|---:|
| all GET | 300 | 78.05 | 109.71 | 149.10 | 0.00% | 0.00% |
| detail GET | 300 | 56.80 | 69.81 | 171.58 | 0.00% | 0.00% |
| following GET | 300 | 80.68 | 121.31 | 151.53 | 0.00% | 0.00% |
| like DELETE | 75 | 53.50 | 65.67 | 68.46 | 0.00% | 0.00% |
| like POST | 75 | 50.70 | 62.19 | 67.50 | 0.00% | 0.00% |
| search GET | 150 | 51.11 | 61.80 | 66.16 | 0.00% | 0.00% |
| update PUT | 150 | 76.59 | 87.11 | 124.67 | 0.00% | 0.00% |
| user GET | 150 | 80.25 | 132.74 | 156.00 | 0.00% | 0.00% |

CPU/memory: 56回のdocker stats（backend/専用DB）をresults.jsonに保存。取得失敗 0回。

## load / boundary

- 状態: pass / cleanup: pass
- 実行: 2026-11-06T18:06:44.179533+00:00 ～ 2026-11-06T18:13:02.439108+00:00（UTC。JSTは+09:00）
- 一次データ: `docs/superpowers/plans/perf-results/80c2c805516e403f88397e8dee90d0ca/results.json` と同folderのrequests.jsonl/ownership.json
- source: `43baf4353acf74eec0170660cfd953d78d0c8a90` + source SHA-256 `48e91a5ce4139d4b213c7fc20c0838354f933e2626fb43dac122ad599f33f1fb`
- 環境: macOS-26.5.2-x86_64-i386-64bit / x86_64、Docker CPU 8 / memory 8321994752 bytes
- backend: `sha256:02256cd305bcd485396e1c94e5e1052e7f4e356d79adda8c786368a166b42b7b`、Django runserver --noreload; DEBUG=false; 1GiB
- PostgreSQL: `postgres:17.11-bookworm@sha256:d2b1a0795f5ecbe49dc07be0b35b62977aff9152870ea332375021c79ea4905b`
- 版: `{"python": "3.13.18", "django": "5.2.18", "psycopg": "3.3.6", "pillow": "13.0.0"}`
- 前件数: `{"users": 5, "posts": 1000, "exercises": 10000, "sets": 200000, "comments": 2000, "likes": 2000, "follows": 10, "posts_per_user": [200, 200, 200, 200, 200]}`
- 後件数: `{"users": 5, "posts": 1000, "exercises": 10000, "sets": 200000, "comments": 2000, "likes": 2005, "follows": 10, "posts_per_user": [200, 200, 200, 200, 200]}`
- 全run時間: 378.29秒（構築/seed/認証/smoke/warmup/cleanupを含む）

測定窓300秒、5人/毎秒5予定要求、warmup30秒除外。1500/1500完了、missed=0。

| API / method | n | p50 ms | p95 ms | p99 ms | 失敗率 | 5xx率 |
|---|---:|---:|---:|---:|---:|---:|
| all GET | 300 | 230.55 | 318.42 | 358.91 | 0.00% | 0.00% |
| detail GET | 300 | 63.10 | 92.80 | 114.24 | 0.00% | 0.00% |
| following GET | 300 | 231.38 | 303.15 | 325.58 | 0.00% | 0.00% |
| like DELETE | 75 | 51.67 | 60.50 | 61.68 | 0.00% | 0.00% |
| like POST | 75 | 48.92 | 60.65 | 61.33 | 0.00% | 0.00% |
| search GET | 150 | 45.32 | 57.15 | 58.29 | 0.00% | 0.00% |
| update PUT | 150 | 120.74 | 191.22 | 228.12 | 0.00% | 0.00% |
| user GET | 150 | 226.74 | 477.42 | 560.77 | 0.00% | 0.00% |

CPU/memory: 56回のdocker stats（backend/専用DB）をresults.jsonに保存。取得失敗 0回。

## image / normal

- 状態: pass / cleanup: pass
- 実行: 2026-11-06T18:13:20.253025+00:00 ～ 2026-11-06T18:14:04.563638+00:00（UTC。JSTは+09:00）
- 一次データ: `docs/superpowers/plans/perf-results/8729995d90274706974e4a5711404828/results.json` と同folderのrequests.jsonl/ownership.json
- source: `43baf4353acf74eec0170660cfd953d78d0c8a90` + source SHA-256 `48e91a5ce4139d4b213c7fc20c0838354f933e2626fb43dac122ad599f33f1fb`
- 環境: macOS-26.5.2-x86_64-i386-64bit / x86_64、Docker CPU 8 / memory 8321994752 bytes
- backend: `sha256:02256cd305bcd485396e1c94e5e1052e7f4e356d79adda8c786368a166b42b7b`、Django runserver --noreload; DEBUG=false; 1GiB
- PostgreSQL: `postgres:17.11-bookworm@sha256:d2b1a0795f5ecbe49dc07be0b35b62977aff9152870ea332375021c79ea4905b`
- 版: `{"python": "3.13.18", "django": "5.2.18", "psycopg": "3.3.6", "pillow": "13.0.0"}`
- 前件数: `{"users": 5, "posts": 1000, "exercises": 3000, "sets": 9000, "comments": 2000, "likes": 2000, "follows": 10, "posts_per_user": [200, 200, 200, 200, 200]}`
- 後件数: `{"users": 5, "posts": 1000, "exercises": 3000, "sets": 9000, "comments": 2000, "likes": 2000, "follows": 10, "posts_per_user": [200, 200, 200, 200, 200]}`
- 全run時間: 44.34秒（構築/seed/認証/smoke/warmup/cleanupを含む）

直列60測定要求、入力/出力を分離。1秒閾値の対象外。内容はRGB画素digestで照合。

| 分類 | n | p50 ms | p95 ms | p99 ms |
|---|---:|---:|---:|---:|
| image-1320 GET | 10 | 36.29 | 41.81 | 41.81 |
| image-1320 PUT | 10 | 332.70 | 347.00 | 347.00 |
| image-147 GET | 10 | 7.71 | 9.29 | 9.29 |
| image-147 PUT | 10 | 46.89 | 62.48 | 62.48 |
| image-590 GET | 10 | 10.28 | 20.05 | 20.05 |
| image-590 PUT | 10 | 80.92 | 89.59 | 89.59 |
- 147px: input 65057 bytes、output 65047 bytes、GET平均 8078182 bytes/秒（body全受信まで）。
- 590px: input 1045273 bytes、output 1046348 bytes、GET平均 89104895 bytes/秒（body全受信まで）。
- 1320px: input 5230178 bytes、output 5235898 bytes、GET平均 141269580 bytes/秒（body全受信まで）。

CPU/memory: 4回のdocker stats（backend/専用DB）をresults.jsonに保存。取得失敗 0回。

## auth-burst / normal

- 状態: pass / cleanup: pass
- 実行: 2026-11-06T18:14:32.756084+00:00 ～ 2026-11-06T18:15:18.171639+00:00（UTC。JSTは+09:00）
- 一次データ: `docs/superpowers/plans/perf-results/72f2536f13d54334a068441ff54c8567/results.json` と同folderのrequests.jsonl/ownership.json
- source: `43baf4353acf74eec0170660cfd953d78d0c8a90` + source SHA-256 `48e91a5ce4139d4b213c7fc20c0838354f933e2626fb43dac122ad599f33f1fb`
- 環境: macOS-26.5.2-x86_64-i386-64bit / x86_64、Docker CPU 8 / memory 8321994752 bytes
- backend: `sha256:02256cd305bcd485396e1c94e5e1052e7f4e356d79adda8c786368a166b42b7b`、Django runserver --noreload; DEBUG=false; 1GiB
- PostgreSQL: `postgres:17.11-bookworm@sha256:d2b1a0795f5ecbe49dc07be0b35b62977aff9152870ea332375021c79ea4905b`
- 版: `{"python": "3.13.18", "django": "5.2.18", "psycopg": "3.3.6", "pillow": "13.0.0"}`
- 前件数: `{"users": 5, "posts": 1000, "exercises": 3000, "sets": 9000, "comments": 2000, "likes": 2000, "follows": 10, "posts_per_user": [200, 200, 200, 200, 200]}`
- 後件数: `{"users": 5, "posts": 1000, "exercises": 3000, "sets": 9000, "comments": 2000, "likes": 2000, "follows": 10, "posts_per_user": [200, 200, 200, 200, 200]}`
- 全run時間: 45.44秒（構築/seed/認証/smoke/warmup/cleanupを含む）

- 正規login 10、期待429 1。通常性能分母に含めない。

CPU/memory: 5回のdocker stats（backend/専用DB）をresults.jsonに保存。取得失敗 0回。

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
| smoke/normal | 2026-11-06T17:54:25.255023+00:00 | pass | pass | cd2550ceb3f948a490d0be6a2df373c6 |
| load/normal | 2026-11-06T17:59:05.279147+00:00 | pass | pass | 66ef4f0975ab4ea3b009ba2286d3c5c9 |
| load/boundary | 2026-11-06T18:06:44.179533+00:00 | pass | pass | 80c2c805516e403f88397e8dee90d0ca |
| image/normal | 2026-11-06T18:13:20.253025+00:00 | pass | pass | 8729995d90274706974e4a5711404828 |
| auth-burst/normal | 2026-11-06T18:14:32.756084+00:00 | pass | pass | 72f2536f13d54334a068441ff54c8567 |

最初のsmokeは資源作成前のTIME_WAIT判定で失敗。試験側を修正し、PID終了・空資源台帳・該当containerなしを確認して自分のlockだけ返却した。失敗記録を保持している。
初回通常loadは内容検証時間も含めたため参考扱い。最終loadはbody全受信までで再測定した。
実行時は未commit source。ファイル別hash一覧はdocs/superpowers/plans/perf-snapshots/に保存。後続の文書変更と計測対象コードを区別して照合する。
ローカル結果をAWS実証へ読み替えない。撮影・2構築/破棄・後日請求確認は未完了。

品質レビューのHigh修正後、必須Post/検索形状とPNG stream終端、作成intent/worker/cleanup割込みの保護を43baf4353acf74eec0170660cfd953d78d0c8a90へ固定し、通常・最大境界・画像・認証集中を再実行した。上の各節は最新runを採用している。

追加承認後の修正はworker起動時の割込み保留と、PID未登録時の停止未確認判定に限定する。
上記の負荷値は43baf43での実測として保持し、最終コード全体と同一とは記さない。
要求・計測・固定データ・JSON/画像oracle・集計は変更していない。
追加smoke `docs/superpowers/plans/perf-results/f652ec102d584deca58c0ddd92455e93/results.json` は55/55成功・cleanup成功。
perf全37テストが成功し、OS子生成後の実SIGINT/SIGTERMで子停止、起動結果不明では停止未確認となる負例を確認した。
異常時の開始/中断内訳・実throughputの詳細不足M1は、ユーザーが既知の設計差異として承認した。
