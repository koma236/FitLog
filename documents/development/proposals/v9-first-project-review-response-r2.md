# Claude設計レビュー第2回：指摘への対応

実行記録：`20261027T063928Z-29f34f5b`。実モデルClaude Opus 5.5、worker未起動。テスト189件成功、review_exit_code=0、approved=false、findings=5。ユーザー提示の全文でMedium 2 / Low 3を確認。初回High等の解消はClaudeが確認したが、第2回の設計判定は不承認。

設計承認用の修正版：[改訂設計v3](v9-first-project-design-v3.md)。以下はCodexによるコード照合と修正であり、修正版の独立レビュー合格を意味しない。

| ID | 第2回指摘 | 採用した修正 | 設計・検証 |
|---|---|---|---|
| R2-M1 | design bindingと実際の失効処理がつながっていない | state bindingへdesign_binding_digestを追加。毎回ディスクから再計算し、specification groupに配置。plan_hashも仕様groupへ移動。仕様receiptのbinding項目を列挙し、Git操作でも共通syncを使用 | §3・4、B06 |
| R2-M2 | checks登録後の計画再承認で作成済みIssueを照合できない | 最初の計画承認後・生成前にIssueを1件作る。schema 10 bootstrapの成功済みIssueに限り、安定したissue_scope_digestとconfig_base_digest、現在の承認・予定check一致で照合。未実行proposalと他Git操作の検査は緩めない | §6.1、B18・B21 |
| R2-L1 | コピー先の対応表リンクが不正 | 修正版資料は同じbasenameを保って設計書と対応表を同じディレクトリへコピーする。コピー先でMarkdown参照先の実在を検査。以前のレビュー入力は上書きしない | 本書と修正版の配布資料 |
| R2-L2 | brainstormingとv9が同じbranchのdesign枠を二重消費する | v9 design_reviewがDesign Gateの独立レビューを兼ねると明記。chat側で別予約・別レビューを起動しない。既存台帳を共有し、消費済み枠を消去しない | §5、B22 |
| R2-L3 | runtime digestに新しい制御コードが含まれるか不明 | scripts/v9の全py/cjs＋必須モジュール、harness.py、handoff入口、bin/ai-dev、実際に選択したhookのpath/hashを集合として固定。追加・削除・欠落も検出し全入口で使用 | §10、B23 |

## R2-M1の具体例についての訂正

現行spec.pyのvalidate_specは`spec_hash = _digest(raw)`でmanifest全体をhashしている。manifest内sourceのsha256を更新すればspec_hashも変わり、source本文だけ変えればsource検証が失敗する。したがって「sourceのsha256だけ変えてもspec_hash不変」という例は現行コードの正常経路では成立しない。

ただし、plan_hashのgroupが設計の要求と異なること、design_route等の変化を現在のsyncへ渡す具体的なfieldがなかったことは事実なので、指摘の主要部を採用した。B06には、source変更時の2経路（宣言hash更新あり／なし）と、design digest自体の変化を扱う単体条件を分けて記載した。

## 確認できたことと限界

文書のリンク・受け入れ条件の対応は機械確認する。変更したのは設計書であり、実装された状態遷移やGit操作の成功証跡はまだない。Medium 2件への修正を特にB06/B18/B21で検証する計画。既存テストの成功を今回の修正実装の成功として扱わない。

第2回に新しいHighはなく、レビュー予算2/2を消費済み。brainstormingの通常手順に従い、第3回を自動追加せず、修正内容と未実装・未再確認の限界を提示して人間の設計承認を受ける。これは品質不合格の実装を受容するものではなく、実装後の実チェック・独立品質レビュー・各承認を省略しない。
