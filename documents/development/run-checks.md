# ローカル11 checksの実行

最終更新: 2026-11-05。関連: Issue #38、[個人開発運用](personal-workflow.md)、[並列運用](personal-parallel-workflow.md)。

## 事前確認（呼出し元の責任）

対象worktreeをcwdとするセッションで、親が `git branch --show-current`、`git status --short`、`git rev-parse HEAD`、`git rev-parse --path-format=absolute --git-common-dir` を確認する。共通Git領域の実体pathが並列運用の採用済み `/Users/saki/project/FitLog/.git` と一致しなければ起動しない。別cloneのlockは同じ固定Composeを保護できない。既存の他セッションが共有runtimeを使っていないことも作業記録と照合する。

親はcommitと未commit差分（tracked/index/対象untrackedのpathと内容hash）を実行前後に記録する。実行中に対象が変わったら同一snapshotの検証とは扱わない。任意commandを許可する汎用runnerとして扱わず、script・registry・Compose・Dockerfileの変更を読み、レビュー対象snapshotと照合して起動する。初回実行前にはscriptの全文を表示する。

## 実行と記録

Python 3.11以降、Docker/Compose、通常のbuild用ネットワークと共通Git領域のlock作成権限が必要。

```sh
python3 -B scripts/run-checks.py
```

引数は `--help` のみ。registryは `.ai-dev/project.toml`、projectは `fitlog-dev` に固定。shell評価を使わず、11件の登録argv/cwd/env/timeoutを順番に用いる。共通Git領域にmkdirでlockを取り、DBが未作成/停止中のときだけ起動する。起動要求を出した時点から停止責任を持ち、起動途中失敗でもstopを試みる。既存の稼働DBは停止しない。

自分のbackend imageをbuildして `showmigrations --plan` と適用済みnode/現graphを読み取りで記録する。未知の適用済みmigrationや履歴不整合ではchecksへ進まない。空DBは正常。reset・逆migrationはしない。backend-migrate前後とfinallyにも状態を採取する。

通常checkの非ゼロは後続を続行し全体を失敗とする。compose-build失敗、timeout、SIGINT/SIGTERM、process起動不能では後続全件を中断し、未実行理由を保存する。準備失敗も全11件を未実行として扱う（registry自体が不正で検証できない場合はregistryエラーを報告する）。

出力は `.quality-check-runs/<UTC時刻とUUID>/` の `results.json`、`summary.md`、各check/操作の `.log`。JSONにはid、argv/cwd/env、開始終了UTC、終了code、status、ログpath、script/registryのSHA-256、worktree/branch/common Git領域、migration状態、cleanup結果を記録する。未実行の時刻/code/logはnull。ログはローカルに保ち、共有する要約に秘密が含まれないことを確認する。

終了0は全11件成功・後始末成功・保存成功を意味する。独立品質レビューや品質フラグを代行しない。親がrun-idとsnapshotを品質報告へ対応づけ、PRへ結果を要約する。

## 異常終了と後始末

timeout/割込みでは子process groupにTERMを送り、直属childをreapしながらgroup全体の消滅を待つ。10秒以内に終わらなければKILLを送り、さらに2秒でgroup消滅を確認できなければlockを保持する。leaderが先に終了しても子孫の残存を見落とさない。通常終了時にもgroup残存を確認する。Dockerコンテナの終了とは別なので、`compose ps --all --format json` でrun前後を照合する（[Docker公式仕様](https://docs.docker.com/reference/cli/docker/compose/ps/)）。新規の非DBコンテナの終了を確認できなければlockを残して失敗とする。コンテナの自動削除・volume/image削除はしない。

group終了の待機中に受けたSIGINT/SIGTERMは保留し、終了確認後に元のtimeout/割込みとともに報告する。終了確認前は安全状態にせず、確認不能の例外や停止待機そのものの中断ではlockを保持する。一度確認不能になった安全状態を、後続のcleanupコマンドの成功だけで安全に戻さない。

finallyでは状態採取失敗・保存失敗でも自分が起動したDBのstopと停止確認を試みる。cleanupで操作ログを作成できない場合は小さなstdoutをメモリへ退避してstop/psを実行し、保存障害自体は全体失敗として残す。所有者が変わった場合はDB/lockへ追加操作しない。停止・残存確認に失敗した場合はlockを保持し、ログとownerを報告する。既存lockを古さだけで奪取せず、自動再実行もしない。後始末中の再度のSIGINT/SIGTERMは無視し、cleanupを完了させる。SIGKILL・電源断はfinallyを保証できない。

## 回帰検証

```sh
python3 -B -m unittest discover -s scripts -p test_run_checks.py
node --test scripts/test-quality-gate.cjs scripts/test-check-pr-stop.cjs
```

scriptとregistryは `gate.controlPlane` の対象。実行命令の変更は品質確認とX2のマージ前停止を通す。Git/gh、品質フラグ、権限設定の変更はscriptに含めない。
