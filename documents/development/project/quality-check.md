# FitLog: quality-check の当てはめ

スキルの規則は変えない。FitLog のコマンドと検証の当てはめだけを書く。

- 通常ゲートと X2 停止判定の回帰試験は `node --test scripts/test-quality-gate.cjs scripts/test-check-pr-stop.cjs` で、両方の hook と読取り専用 CLI を実プロセスで実行する。
- 11 checks は親が `documents/development/run-checks.md` の事前確認後、`python3 -B scripts/run-checks.py` で実行する。登録argv/cwd/env/timeoutは `.ai-dev/project.toml` を正とし、scriptは排他とDBの後始末も担当する。親が実行前後のcommit・未commit snapshotとrun-idを対応づけ、全checkのid/終了コード/日時/ログ・cleanup結果を品質報告へ添付する。scriptの終了0は独立レビュー完了や品質フラグの代わりにならない。
- script回帰は `python3 -B -m unittest discover -s scripts -p test_run_checks.py`。実DBを使わずprocess境界のfakeと一時Git metadataで検証する。
