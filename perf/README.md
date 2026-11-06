# 固定ローカル性能試験

Issue #55。方式・合否は [性能試験仕様](../docs/13_performance_test.md)。
Python 3.12以上とDocker/Compose、共通Git領域へのlock作成権限が必要。製品実行は既存lock済みPython 3.13 image。

```sh
python3 -B -m perf.runtime unit-tests
python3 -B -m perf.runtime smoke
python3 -B -m perf.runtime load --scenario normal
python3 -B -m perf.runtime load --scenario boundary
python3 -B -m perf.runtime image
python3 -B -m perf.runtime auth-burst
```

各コマンドが共有runtimeのlockを取得する。lock競合・固定18080使用中は開始せず、他者serverを止めない。
専用network/DB/media volumeとbackend containerを作り、共有DB/画像へ接続しない。
既存Compose定義からimage/environmentを読み、DB名・host・PERF_RUN_ID・PYTHONPATHを指定する。
perf専用settingsで接続先が所有DBと一致することを起動前に検証する。
frontendは使わない。製品認証/制限はそのまま。Django開発serverの結果をAWS/Gunicornの性能と呼ばない。

通常/境界は5人・1000投稿、smoke後30秒warmup+300秒測定・毎秒5要求。
各人のCookie/CSRFは別process内で分離。親が5秒の要求全体期限を監視し、worker終了確認後にcleanupする。
固定件数/時間/並列数の拡大optionや任意URLは提供しない。画像は直列60要求、認証集中は別DBで11回（最後429期待）。

一次結果・所有台帳は `docs/superpowers/plans/perf-results/<UUID>/`（ignored）。
`results.json` に環境・版・snapshot・前後件数・統計・資源観測・cleanup、`requests.jsonl` に秘密を含まない要求単位の結果を保存する。
画像の入力bytesと出力bytesは分け、内容はRGB画素のSHA-256で照合。URL/token/Cookie/response本文は保存しない。
PNGサイズは147/590/1320px四方（約64KiB/1MiB/5MiB、正確なbytesは結果を参照）。

正常終了は今回の所有資源を逆順で停止・除去する。所有不一致、停止不能やcleanup失敗時はfailとしlockを保持する。
Docker作成前にintentを原子的に保存し、応答喪失時は実在とラベルを照合する。作成結果が未確認なら台帳とlockを残す。
worker起動も終了管理の保護範囲に含め、cleanup中の割込みは後始末の確定まで保留する。
中断した場合は所有台帳、lockのowner、実process/container/volumeを照合して担当者が回復する。古さだけでlockを消さず、共有DB resetやvolume一括削除をしない。
明示的な復旧は `python3 -B -m perf.runtime cleanup --record <結果folderのUUID>`。
元の調整process終了、同worktree/branch、台帳の固定資源名と実ラベルを確認する。既存runtime lockは自動で奪わず拒否する。
owner_pidが未記録の旧台帳は復旧CLIでは扱わない。所有確認を省略しない。

AWS準備のオフライン検査:

```sh
python3 -B scripts/prebilling/readiness.py
python3 -B -m unittest discover -s scripts/prebilling -p 'test_*.py'
python3 -B -m unittest discover -s scripts/deployment -p 'test_*.py'
```

draft有効は実AWS未実施・未承認・readiness未決のまま。実AWSへ接続するoptionはない。
