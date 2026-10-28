v9のGit/GitHub操作が個人profileを自動選択し、共有の既定設定へ戻らないようにします。また、限定環境からUSERが除かれると既存のClaudeログインを認識できなかったため、USERだけを許可リストに追加します。

Closes __SUCCESSOR_ISSUE__
Refs #3

## 実装レポート

### 設計・計画との対応

| 対象 | 結果 |
|---|---|
| 個人Git環境 | profile、path・権限・include・account、環境変数、proposalへの設定固定を実装 |
| Claude環境 | USERを限定継承。欠落時は捏造せず、token・askpass・設定注入の除外を維持 |
| v9の前提 | 仕様・計画・実装結果・独立レビュー結果の4段階本人承認済み |
| 保存範囲 | `.ai-dev/personal-git.plan.json` の17ファイル。受け入れ条件PG-A01〜PG-A09 |

### 設計・計画との差異

- USERの最小修正は本人承認後に仕様・計画へ反映し、再検証済みです。
- 保存対象外の旧資料・backup・cache 57ファイルは本人承認に基づきローカルに保持し、commit対象外にしました。
- 旧Issue #3は仕様・計画の再承認により現行v9の照合条件を満たさなくなったため、今回限り後継Issueを作成する扱いを本人承認済みです。旧receiptは変更していません。
- FIRST-PROJECTの初回開発工程改修とFitLogアプリ実装は、このPRの範囲外です。

### 品質チェック結果サマリ

- リスク：High（認証・設定・Git/GitHub操作の境界）。引き下げなし。
- Python変更7ファイルのAST解析、`git diff --check`：成功。静的チェックのAI修正パス0回。専用lint/buildコマンドは未設定です。
- `python3 -B -m unittest discover -s tests`：作業環境195件成功。保存対象のみの検証コピーでは191件成功（旧テストbackupを含めません）。
- `PERSONAL-GIT-implementation-3`：登録checks成功、142秒。
- 独立レビュー：Claude反証QA合格（90秒、コード分析）、Claude v9 review-3成功（78秒）。現snapshotで未解消High/Mediumなし。
- レビュー履歴：過去の3役レビューと修正確認を含め予約5巡。review-1の起動失敗を成功に数えていません。本人承認による追加サイクル2回。現在の最終サイクルは5です。
- テスト設計：`docs/superpowers/plans/2026-10-27-personal-git-test-design.md` とPG-A01〜09を照合済み（ローカル作業用メモは非commit）。
- ミューテーション：Python用runner未設定のためnot_configured。未実行です。
- UI E2E：画面変更なし、none/not_proposed、skipped。Git/環境の統合fixtureはunittestに含みます。
- 文書更新：個人Git仕様、受け入れ条件、保存計画、エラーコード、運用policy、README、chat skill。
- Flag commit：`__FLAG_COMMIT__`。commit後に保存対象の照合と`untracked-check: OK`を確認して発行します。

### レビュー指摘への対応

- 過去の共有設定pathのcasefold、gitdir/commondirのsymlink・親参照、gh設定symlink、Git parserのhome探索に関する4件は修正確認済みです。
- 今回のQAではUSER継承と実子processのテストオラクルを確認。禁止環境キーの追加assert、snapshot環境への直接assertはLowの将来拡充候補として保持しています。空行の体裁指摘も内容への影響はありません。
- QAが未確認とした参照source hashと実環境auth statusは親側で確認済みです。認証情報は表示・コピーしていません。
- 現行v9はレビュー本文を保存しないため、検証レビューは保存されたattemptの成功状態と本人承認を根拠にしています。過去の未保存findingsは捏造していません。

### ゲート上書き・承認

- ゲートパラメータ上書き・品質不合格の受容・リスク引き下げ：なし。
- review-budgetは正規extend/beginで登録。台帳の書換え・上限回避なし。
- 現行v9にreview marker受渡しがないため、当該v9レビューだけ正規予約と対応記録で扱う例外を本人承認済みです。反証QAはcheckReview APIで座席を正規消費しました。
- Issue・commit・feature branchへのpush・PR作成はそれぞれ通常terminalで個別に本人確認します。mergeは人間がGitHub上で行います。
