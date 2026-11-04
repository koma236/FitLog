# FitLog: quality-check の当てはめ

スキルの規則は変えない。FitLog のコマンドと検証の当てはめだけを書く。

- 通常ゲートの回帰試験は `node --test scripts/test-quality-gate.cjs` で、両方の hook を実プロセスで実行する。
- 11 checks は親が `.ai-dev/project.toml` の argv を共有排他枠の中で直接実行し、id・終了コード・対象 snapshot を報告する（`documents/development/personal-parallel-workflow.md`）。
