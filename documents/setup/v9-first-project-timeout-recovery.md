# FIRST-PROJECT 実装タイムアウトからの続行

2026-10-28。対象は`koma236/ai-dev-harness`の`fix/v9-first-project`。

## 確認した状態

- `FIRST-PROJECT-implementation-1`は`provider_timeout`でfailed。1 round、3600秒消費。成功へ書き換えず履歴を保持する。
- 実装途中のコード・テストはworktreeに残っている。固定した外側runtime、仕様source、manifest/plan/configには変更なし。仕様・計画の本人承認は維持されている。
- Issue [#6](https://github.com/koma236/ai-dev-harness/issues/6)の成功receiptあり。作り直さない。
- 診断テスト開始前に対象worktreeのcwdを持つ残存processは検出されなかった。旧実行元のtimeout処理もprocess groupを終了させる実装を確認した。

## 診断と修正

残った実装で全回帰テストを実行し、236件中1件失敗（246.679秒）。追加済みの`test_linux_missing_boot_identity_is_not_mistaken_for_process_termination`が、Linuxのboot ID取得失敗をプロセス終了と誤認する問題を検出した。

`/proc/<pid>/stat`の不存在とboot ID取得失敗を別々に扱い、後者は`V9_PROCESS_IDENTITY`で停止するよう修正した。プロセスそのものが不存在ならNoneになる負例も追加。関連4件のテストは成功。設計B12の範囲内であり、時間制限・本人確認・チェック条件は緩和していない。この不具合が3600秒タイムアウトの原因だったとまでは確認できない。

修正前ファイルは`/private/tmp/fitlog-process-fix-55u03a_s`に保全。Python 30ファイルの構文、Node bridgeの構文、`git diff --check`は成功。修正後の全回帰は237件 / 245.069秒 / OK。診断ログは`/private/tmp/fitlog-first-project-after-timeout-tests.log`。

## 続行方針

途中の成果を別途バックアップし、生成された未追跡pycだけを保存対象から外す。正規controllerで現在のsnapshotへ同期し、別attempt `FIRST-PROJECT-implementation-2`を最大1 round・3600秒で準備する。最初のfailed attemptと消費量は保持する。仕様/計画receiptとIssue照合が変わらないことを確認する。

`sh /private/tmp/fitlog-first-project-continue.sh`を通常ターミナルで本人が実行する。既済の仕様・計画承認とIssue作成は省略し、新attemptのEXECUTEと成功後の実装結果APPROVEは本人が入力する。診断テストの成功をv9実装成功receiptとして代用しない。独立品質レビューと保存操作は後続工程。

## 続行準備の結果

- 変更51ファイルを`/private/tmp/fitlog-first-project-timeout-rf6rre13`へhash照合付きでバックアップした。うち生成pyc 7ファイルはバックアップに残しworktreeから取り除いた。コードを破棄していない。
- `FIRST-PROJECT-implementation-2`を正規controllerでpendingとして予約。revision 7、snapshot `ee0eded437f995003b1f6b9cd8696dea963ca8ea42021f98f545a037b7822d41`。
- 最初のfailed attempt、消費量、仕様・計画の本人承認は完全一致で保持。Issue #6の正規receipt再照合も成功。
- 続行入口の`--check-only`は成功。provider起動、実装結果承認、独立品質レビュー、Git保存操作はまだ実施していない。
