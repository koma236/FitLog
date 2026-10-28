# Claude設計レビュー第1回：指摘への対応

対象run：`20261027T060204Z-c302e27a`。実モデル：Claude Opus 5.5。ユーザーがターミナルのverdict全文をチャットへ提示した。approved=false、High 1 / Medium 7 / Low 2。以下はCodexによる現行コードとの照合と設計修正であり、独立再レビューの合格結果ではない。

改訂版：[設計v2](v9-first-project-design-v2.md)。初回レビューに渡した`.ai-dev-jobs/v9-first-project-design.md`は履歴としてそのまま保持する。

| ID | 指摘 | コードとの照合・採用した対応 | 設計v2 | 検証条件 |
|---|---|---|---|---|
| H1 | phase・証拠・stateが未定義で承認混入の可能性 | workflowの厳密な集合検証とcontrollerのphase＋snapshot判定を確認。schema 10、5種のphase、型付き証拠、承認対象attemptの照合を定義。bootstrap/designを実装・品質承認から除外 | §1・3 | B03/B07/B19 |
| M1 | runtime変更による全承認失効の説明がない | update_bindingの仕様以降失効を確認。移行で旧履歴を保存し、設計レビューと全承認のやり直しが必要と明記 | §1 | B06/B07/B20 |
| M2 | design bindingと失効が曖昧 | 全体snapshotと設計の固定前提を分離。baseline_commitとsource hash等を列挙。生成後はplanを変えず実checksだけ登録する正常経路を定義 | §4・6 | B05/B06/B09/B18 |
| M3 | 重大度判定・review-budgetの接続がない | typed severityのverdictを定義。controllerが実行直前に正規beginとcheckReviewで予約・座席消費。失敗は起動0、予算返却なし | §5 | B09/B10/B15 |
| M4 | 設計モデルルートの読込み元とdigestがない | 現load_model_routesの3役のみの解析を確認。専用design route読込みを追加する案とし、通常route digestとは分離 | §5 | B06 |
| M5 | 初回生成のstatus・中断処理が曖昧 | phase=bootstrap/status=succeeded/kind=generationを定義。チェック登録待ちは算出表示。unknown等は本人による正規解消でabandonedにし、証拠・予算を保持 | §3・6・7 | B11/B12/B13 |
| M6 | 初回taskの単位・依存・変更ファイルが未定義 | 独立T0を固定。後続にはGit-readyが必要。生成者は実設定を変更せず、configure-checksが実設定を登録し計画だけ再承認 | §2・6 | B05/B16/B18 |
| M7 | HEADのないrepoの扱いがない | _headと_single_parentの前提を確認。既存HEADを初期化条件にし、root commit対応は範囲外。FitLog/ハーネスのHEADを実確認 | §2 | B14 |
| L1 | 無意味なcheckの拒否と人間判断の境界がない | 自明な成功argvの最小拒否規則を列挙。テスト0件は各runnerの非0終了で確認、任意プログラムの有効性は独立品質レビューで確認 | §8 | B04/B11とcheck側の負例 |
| L2 | 移行・失効・混入・復旧等の負例が不足 | 20件の独立した期待値へ展開。既存成功テストだけで新工程を保証しない | §9 | B01–B20 |

## 重要な影響

旧承認の自動引継ぎは行わない。共通ハーネスを更新した既存workflowにも移行・設計レビュー・再承認が必要。移行操作自体は通常terminalで本人が対象を確認する。旧stateと消費予算を捨てず、成功receiptを作り直す操作ではない。

新しいbootstrapは「初回ならチェック不要」という免除ではなく、生成と検証の証拠を分ける工程。実チェック成功まで実装結果を承認できず、Git-readyにならない。

## 次の判定

Highの根拠に関わるstate/証拠/互換性を具体化したため、改訂設計についてClaudeの追加確認1回を提案し、ユーザーの「OKです」で承認された。正規extend後に第2回を予約済み（2/2）。独立再確認の結果は未取得。今回の追加レビュー承認を設計承認や実装承認に読み替えない。
