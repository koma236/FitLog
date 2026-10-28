# FL-01 初回基盤の準備状況

2026-10-28。製品コード未実装、仕様・計画の承認は未取得。

- ハーネス本体はmainへ戻し、`git pull --ff-only origin main`でPR #7のmerge commit `308a7f0`を取得済み。mainとorigin/mainの差分なし。
- FitLogは既存の未コミット資料を保持して`feat/fl-01-foundation`へ移動。baselineは既存のinitial commit。既存資料をcommit・削除していない。
- 設計：`docs/fl-01-foundation-design.md`。
- manifest：`.ai-dev/fl-01.spec.json`（schema 9）。plan：`.ai-dev/fl-01.plan.json`（schema 10、bootstrap）。予定checkは改訂2で10本。実checkは未設定。
- 参照source 34件のSHA-256照合に成功。workflowは正規init-workflowで初期化済み。
- Codex実装／Claude独立レビュー。既存ルーティングと通常モードを使用。
- `FL-01-design_review-1`を正式handoffで開始。確認文字列は前のユーザー指示に基づきCodexが入力。101秒で`failed / invalid_result`。判定・指摘本文は回収できず、合格・指摘0件と扱わない。失敗と消費済みレビュー枠を保持する。
- 設計レビュー枠は既定limit 1、使用済み1。新しいbeginやextendを無断実行していない。次は返答形式の原因調査と、本人承認を得た追加1巡が必要。
- `show-review` CLIには`_inputs`のhome/routes/harness_root引数不足によるTypeErrorも確認。CLIエラーをレビュー結果と混同しない。
- Docker Compose CLIあり。Docker engine socketなし。提案ポート18080/15173にLISTENは検出されなかった。コンテナ・AWSリソース・依存lockはまだ作成していない。

新設計の採用は独立レビュー結果を取得してから提示する。仕様・計画receipt、Issue、bootstrap、checks登録、製品実装の検証は未完了。

## 追加1巡の結果と改訂2

ユーザー承認「よいです」によりdesign枠を1巡extendし、FL-01-design_review-2を実行。99秒で判定取得に成功し、不承認（High 1 / Medium 5 / Low 6）。UUID主キー・readiness・request-id/JSON error・migration再検証・Compose実行と依存配置等の全12件を設計とplanへ反映した。対応表はdocs/fl-01-design-review-response.md。入力schema・source照合は成功。修正版のレビューは未実施であり、追加枠はまだ承認・予約していない。製品コード、仕様/計画の承認receipt、Issueは未作成。

## 第3巡と改訂3

本人回答「yes」に基づき1巡追加。design_review-3は98秒でreview_rejected、High 0 / Medium 2 / Low 8。前回の主要指摘の反映は確認された。新しい指摘を改訂3へ反映し、先頭compose-buildを含む11 checks、API例外分類とHTTP/code、DBの具体手順等を定義。実入力validator・source照合・予定argvの検査は成功。改訂3の独立レビューは未実施。詳細はdocs/fl-01-design-review-response.md。追加枠の無断予約や承認receiptの直接編集は行っていない。
