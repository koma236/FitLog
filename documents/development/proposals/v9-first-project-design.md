# v9 初回開発の順序修正・設計案

> 初回レビュー後の改訂案は[設計v2](v9-first-project-design-v2.md)。本書は初稿として保持する。

状態：改修への着手はユーザー承認済み。具体設計の独立レビューは未実施。本書は承認receiptではない。
作成日：2026-10-27。対象：個人用 ai-dev-harness。窓口・実装Codex、独立レビューClaude、既存モデルルーティングを使用。

## 目的と確認済みの不具合

新規アプリでも、仕様整理→独立設計レビュー→人間による仕様・計画承認→初期構成作成→実チェック→実装結果承認→独立品質レビュー→結果承認の順で進められるようにする。

現行controller._inputsは、入力検証とexecution_readyの要求を共通化しているため、checks=[]ではinit-workflowも失敗する。2026-10-27、既存test_v9_controllerの一時fixtureを使い、spec_ready=true／execution_ready=falseの条件で `V9_CONTROLLER_INPUT: specification or project checks are not ready` を再現した。実ユーザーのworkflowを作成・変更していない。既存config/controller/workflowの34テストは成功。

さらに現行prepare-runはimplementation/reviewのみであり、後者は実装結果の承認を要求する。独立設計レビューを実装後レビューに偽装してはならない。

追加の基準確認：`python3 -B -m unittest discover -s tests -p 'test_v9_*.py'` は163テスト、81.163秒、終了コード0で成功。これは改修前の回帰基準であり、不具合修正完了の証拠ではない。出力のproposal・workflow・provider表示はテスト用fixture/mockであり、実ユーザーの承認やGit操作を実行したものではない。

## 不変条件

- 空checks・未実行・失敗は合格にしない。通常implementation/autoの実行条件を緩めない。
- 仕様・計画・実装結果・品質レビュー結果の人間承認を維持する。チャット応答でreceiptを作らない。
- provider実行は通常terminalで本人が確認。EOF・非TTY・内容変更では起動しない。
- Issue/commit/push/PRは個別承認、mergeは本人のみ。設計レビューや初期ファイル生成だけでGit-readyにしない。
- 個人用Codex環境、providerの独立性、既存ルーティング、review-budgetを維持する。
- 設計レビューはコードや仕様を変更しない。読み取り前後のsnapshot不一致は失敗。
- 過去のreceipt・実行attemptを新しい状態に見せかけて書き換えない。

## 変更方針

### 1. 準備と実行の判定を分ける

構造・ハッシュ・パスの検証と実行条件を分離する。init-workflowでは有効な仕様/計画構造を要求するが、checksの存在は要求しない。未解決の仕様は準備状態として保持できるが仕様承認はできない。仕様承認はspec_readyと独立設計レビュー結果、計画承認は仕様承認と計画の完全性を要求する。コマンド表示で「準備可能」「実装可能」「チェック合格」を区別する。

通常のprepare-run implementation/reviewとautoは引き続き実checksを要求する。単に_inputsのready検査を削除する修正にはしない。

### 2. 独立設計レビューを実装結果レビューから分離する

設計レビュー専用のprepare/handoffを追加する。対象はmanifest、plan、検証済みsourceと既存コード。未解決事項を含む草案も読めるが、結果は未解決の承認条件を消さない。

実装providerと異なるreviewerを選び、役割はdocument-reviewer、モデルはharness-runtimeの設計レビュー欄に従う。設計レビューは実装後quality_statusに流用しない。結果は対象spec/plan/参照source/branch/runtime/モデルルートに結び付ける。対象変更で失効し、同じレビュー結果の再利用可否を判定する。実装による無関係なsnapshot変更と設計source変更を区別し、同じ設計のレビューを無意味に繰り返させない。

既存の4段階承認の前にある準備工程として管理する。人間の仕様承認時に設計レビュー結果と残存事項を表示する。重大・中程度の指摘や未解決のblocking questionがあれば承認に進めない。

### 3. 初回基盤作成を明示的に扱う

planに初回基盤taskを明示し、予定するファイル範囲・実装するチェックの目的とコマンド案を記載する。予定コマンドは実行済みchecksとしてproject.tomlへ登録しない。通常taskの初回扱いへの暗黙切替は禁止。初回基盤は通常モードだけを対象としauto対象外。

人間が仕様・計画を承認した後、bootstrapのhandoffを作成する。初期ファイルと実チェックの定義を生成できるが、provider終了コード0だけでは実装成功にならない。終了時は「チェック登録待ち」とし、出力snapshot・範囲差分・提案チェックを表示する。

生成されたコマンドと実在する定義を確認してから、通常terminalで新しい計画・checksへの承認を得る。設定変更時は既存のbinding失効規則を適用する。旧計画receiptを移し替えない。新しいbindingに対してproviderを再実装目的で起動せず、生成物を検証する工程を用意する。

検証工程は空checks、存在しないcwd、失敗、タイムアウト、実行中・実行後のsource変更を拒否する。通過したsnapshotだけを実装結果承認の対象とする。bootstrapの生成結果と検証結果は別のattempt/evidenceとして追跡し、生成だけのattemptで実装承認が成立しないことをテストする。

`true`だけのコマンド等をチェックとして採用しない。汎用ハーネスが任意プログラムの有効性を完全判定できるとはしない。チェックの目的・対象・テスト収集の証跡と独立品質レビューを使って、テスト0件や必要な領域の未検証を成功扱いしない。

### 4. 既存運用との互換性

旧workflowを破壊せず読み取る。新しい初回taskの状態は明示したversion/拡張スキーマで判別し、古い実行入口が新phaseを通常実装として実行できないようにする。旧receiptのない設計レビューを捏造しない。既存の正常な通常開発は回帰試験で維持する。

Issueをまたぐ依存は今回のruntime機能拡張に含めない。FitLogの全体planは索引として保持し、個別Issueのmanifest/planと、前提PR・基準commitの確認へ分ける。同一branch依存の検証を緩めない。

## 影響範囲

| 対象 | 変更内容 |
|---|---|
| scripts/v9/controller.py, cli.py | 準備・設計レビュー・初回基盤・検証入口と表示 |
| scripts/v9/spec.py, config.py | 初回taskと予定checkの構造検証、実設定との区別 |
| scripts/v9/workflow.py | 初回生成と検証の証拠、失効・承認条件、互換性 |
| scripts/v9/handoff.py, execution.py | 端末確認、別providerの設計レビュー、生成後検証 |
| scripts/v9/auto.py, gitops.py | 新しい準備状態を実行済み・Git-readyとして受け入れない |
| tests/test_v9_*.py | 下記の独立した期待値による回帰・負例 |
| documents/v9/, error-codes, ai-dev-chat skill | 正式手順、状態、エラー、導入先の案内 |

## 受け入れ条件と検証根拠

1. 空checksの新規fixtureでも初期化と草案レビュー準備ができる。spec_ready=falseの仕様承認は拒否。
2. 空checksの通常implementation/review/auto、実装承認、commit用proposalは拒否。
3. 同一providerの設計レビュー、非TTY/EOF/確認文字列不一致、確認中のsource変更はprovider起動回数0。
4. 設計レビューによるファイル変更、期限切れsource/hash、review-budget超過は合格にしない。
5. 初回生成が成功しても実checks未登録なら実装承認不可。生成失敗・quota・unknownから自動で後続へ進まない。
6. checks変更で計画以降の承認が失効し、旧receiptのまま検証を起動できない。
7. 実際に失敗する小さいcheck fixture、timeout、snapshotを書き換えるcheckで検証失敗。正常fixtureだけが検証証拠を得る。
8. 実装結果・品質レビュー結果の個別承認とGit操作ごとの承認は維持。
9. 不正パス・symlink・会社環境への参照、新phaseを旧jobへ紛れ込ませる入力は拒否。
10. 既存v9全テストとv8互換テストを実行する。fake providerの通過を実Claudeの認証・実行成功の代用にしない。

## 作業順と既存変更の保護

1. 本設計を独立レビューし、指摘と対応をユーザーへ提示する。
2. ハーネス側の既存未コミット変更（personal Git対応）を保護する。実装前に今回のIssue内容・作業branchを分離し、承認なしに既存変更をcommit/stash/移動しない。
3. まず準備/実行判定の分離、次に設計レビュー、次に初回生成・実チェック検証を実装し、各状態の負例を確認する。
4. 既存回帰テスト、独立品質レビュー、ドキュメント整合性を確認する。
5. FitLog側には正式な新手順を反映し、草案をClaude設計レビューへ渡す。承認の代行やAWS構築はしない。

## 今回のレビュー経路

新しい設計レビュー入口自体を、存在しない入口からレビューすることはできない。ユーザーが「はい、今回に限りよいです。」と回答し、今回のハーネス改修の独立設計レビューに限り既存review経路の利用を許可した。そこで得るレビューはv9のreceiptとして代用しない。既存schema 1 jobと通常terminalの確認は維持する。実装・Git操作・追加レビューへの包括承認とは解釈しない。
