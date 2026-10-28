# FIRST-PROJECT：ハーネス改修の保存結果

2026-10-28、初回プロジェクトの生成と検証を分離する改修をPR作成まで完了した。FitLogのアプリ機能の実装完了ではない。

- repository：`koma236/ai-dev-harness`
- branch：`fix/v9-first-project`
- Issue：[6](https://github.com/koma236/ai-dev-harness/issues/6)
- PR：[7](https://github.com/koma236/ai-dev-harness/pull/7)、OPEN、main向け、draftではない
- commit：`7d2a6d3d464ed4ab66fc3323cb630469fdf320e3`
- 最終レビューsnapshot：`73308da351aa0c92f58a73ab9663a7122104891eacf71fbb490d735653c6eb29`
- 対象worktree：`/Users/saki/project/ai-dev-harness/.worktrees/first-project`。保存後の変更なし。

## 検証と承認

全体テスト259件成功。親の実行397.978秒、正式provider内の実行405.456秒。Python構文、Node bridge構文、diff whitespaceも成功。

`FIRST-PROJECT-implementation-4`は792秒でsucceeded。`FIRST-PROJECT-review-2`はClaudeで196秒、別Claudeの反証QAは237秒で完了し、両役ともapproved=true。High/Mediumは0。Lowは重複を統合して6件あり、PRに全文を記載した。品質3巡目で終了し、上限延長・台帳返却・hook変更は行っていない。

本人入力はユーザーの明示指示に基づいてCodexが通常terminalの正式入口で代行した。実装・レビュー承認のactorは`codex-owner-delegated`。本人が実際に入力したとは記録しない。state/receiptの直接編集はしていない。commit・push・PRも正規v9 proposalの順に実施した。

検証役は固定runtimeの公開adapter_factoryを使い、継承した実行前後の検査を維持して、正規marker/checkReviewと共通contextを実Claudeへ渡した。review-1限定の例外を流用していない。

品質レポートは[first-project-quality-final.json](first-project-quality-final.json)。commit後の未追跡検査はOK、品質フラグのcommitとPRのheadRefOidが一致することを確認した。保存起動元で成功出力を完全一致比較して一度停止したが、CLI正本の`untracked-check: OK - ...`形式を確認して照合を修正した。commitを重複作成せず、同じ成功receiptから継続した。

## 残る範囲

mergeは従来の指定どおり人間がGitHub上で行う。AI merge・auto-merge・trunk更新はしていない。外側の固定runtimeをこの改修の途中で更新していない。

Low 6件は、大文字小文字違いの登録ファイル保護、選択中hook本体の保護、検証記録のsnapshot明記、同一ユーザーによる追跡記録改ざんの信頼境界、放棄後stateのassertion補強、provider失敗後の予算不変assertion補強。最終レビュー済み内容を維持し、今回のPRでは未対応として明記した。

人間によるmerge後、新runtimeの適用を確認してFitLogの仕様・計画と初回基盤作成へ進む。既存stateを継続する場合は正規migrationと再承認、新規taskは新規workflowを使う。旧receiptをschema 10へコピーしない。
