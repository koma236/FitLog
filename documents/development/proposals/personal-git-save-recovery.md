# PERSONAL-GIT 保存前の復旧案

状態：復旧案を本人承認後、保存範囲の整理・実装再検証・独立レビュー・4段階承認を完了。Issue #4、commit df0cd4f5a920add6748bf30978a2ccf5f8fee15b、PR #5まで正規v9で保存済み。PRはopen、本人によるGitHub上のmerge待ち。以下は実施時の案と履歴。

## 確認した事実

- 対象は `/Users/saki/project/ai-dev-harness`、branch `fix/v9-personal-git-environment`。FitLog本体の実装・AWS操作ではない。
- workflow revision 20。4段階の本人承認と現在のbindingの一致を確認済み。
- Git-visible変更74ファイルのうち、承認済みplanの対象は17ファイル。対象外57ファイルはすべて未追跡。削除・上書き・移動はしていない。
- 内訳の正本：[保存対象の監査](personal-git-save-scope-audit.json)。本件以外の旧設計資料、バックアップ、キャッシュ等を含む。
- 現行commitは全変更を保存し、操作後にGit-visible変更が残ることも拒否する。選択的なstageや手動commitで回避しない。
- Issue #3の成功結果は存在するが、元proposalのapproval_digestは再承認後の仕様・計画receiptと一致しない。現行CLIに既存Issueの再承認・取込み機能はない。
- review-budgetはquality 4/4予約済み。以前の追加1回はreview-2で使用済み。追加実行には本人の新しい上限承認が必要。

## 推奨案：新しいruntime改修を加えず、保存範囲を確定して再検証

1. 対象外57ファイルをその場に残し、ローカルの `.git/info/exclude` に個別の完全な相対pathを登録する。対象17ファイル・仕様・計画・checks・runtimeを変更しない。候補は[除外リスト](personal-git-exclude-proposal.txt)。広範囲なワイルドカードや会社設定の変更は行わない。
2. 変更前に対象pathがすべて未追跡であること、planに含まれないこと、既存exclude内容を再確認する。既存内容を保持して追記し、前後のpathと内容ハッシュを記録する。ファイル削除・移動・stashは不要。
3. snapshot変更を正規controllerで同期し、実装結果・レビュー結果の承認を失効させる。仕様・計画の承認は維持する。純粋関数update_bindingによるメモリ内の検証で、この失効範囲を確認した。stateファイルへの試験結果の保存はしていない。
4. Codexの通常implementationで新snapshotの登録checksを実行し、実装結果を本人が承認する。製品コードの追加変更を目的としない。
5. qualityレビュー枠を1サイクルだけ追加する。Claudeによる検証レビューをv9の新しいreview attemptとして実施し、USER環境修正について未完了の反証QAも同じサイクルで実施する（verification-reviewer / falsification-qa）。新しいreviewerのモデルは既存Claudeルートを使用する。従来のレビュー記録は履歴として保持し、別の結果へ読み替えない。
6. v9レビューは現行のmarker受渡しに制約があるため、先に承認された「正規予約と手動対応記録」の例外を次の1 attemptだけ追加適用することも本人判断の対象とする。QAのmarkerは正規経路で扱う。上限を再度超える場合や未解消の指摘がある場合は、成功扱いせず停止する。
7. 最新snapshotでquality-checkの未完了項目・追加テスト判断・結果記録を整理する。レビュー1件の成功だけでquality-check全体の完了とはしない。記録追加がsnapshotを変える場合は、最終v9検証前に確定する。レビュー結果は本人が承認する。
8. 更新後の仕様・計画に対応する後継Issueを正規proposalで1件作成する。旧Issue #3を参照し、USER修正とPG-A01〜PG-A09を明示する。これは今回だけ同じbranchに2件のIssueを持つ例外。旧Issueのreceiptを書き換えず、旧Issueの編集・終了も無断で行わない。
9. commit → feature branchへのpush → PRの順で個別proposalを提示する。mergeは本人がGitHubで実施する。

除外後の未追跡path列挙は、候補ファイルを `git ls-files --others --exclude-standard --exclude-from=...` に渡す読取り専用の確認で、plan内の5ファイルだけになることを確認済み。tracked変更12ファイルと合わせて17ファイルになる。実際のexclude設定は未変更。

ローカル除外はテスト探索からの除外ではない。旧テストバックアップがローカルのunittest discoverに含まれ得るため、保存するファイルだけから成る検証用コピーでも登録checksを確認する。過去のテスト件数を保存後のテスト件数として流用しない。検証用コピーから承認receiptを移植しない。

## 手動操作への影響

- 今回の復旧だけで仕様・計画の再承認は不要（入力が予定どおり維持された場合）。
- 正常終了時のv9本人確認は計8回の見込み：実装開始、実装結果承認、レビュー開始、レビュー結果承認、Issue作成、commit、push、PR作成。GitHub上のmergeは別。
- 起動案内は共通の進行入口へまとめられるが、各確認文字列を自動入力しない。失敗時は止まり、未実施の操作を続行しない。
- これは現行通常モードを維持する案で、確認回数の上限保証ではない。検証失敗や範囲変更があれば、その原因と影響をまとめて報告する。

## 他の案と選ばない理由

- 既存Issueの再承認・保存path指定機能を新設：今回のPERSONAL-GITの仕様・runtime変更を増やし、4段階の再承認と設計レビューの追加につながる。手動操作を減らす当面の復旧には勧めない。
- 74ファイルをそのままcommit：承認済みplan外の旧資料・バックアップを混在させるため採用しない。
- receiptを書き換える、既存remoteを外す、直接commitする：v9の前提を迂回するため採用しない。

## 本人にまとめて確認する事項

上記の復旧案、今回限りの後継Issue作成の扱い、qualityレビュー追加1サイクル（Claude検証レビュー＋反証QA）、次のv9 review attempt 1回に限るmarker連携例外。Git操作そのものの承認は、具体的proposalを提示した通常terminalで別途行う。

根拠：personal-workflow.mdの「1 Issue = 1作業ブランチ = 1 PR」、ai-dev-chatの「Every action is a separate proposal and a separate terminal approval」、quality-check Step 4のレビュー予約・marker連携・レビュー上限。今回の調査依頼を、例外や上限拡張の承認とは扱わない。

## 承認後の実施記録

- 上記の復旧案、後継Issue、追加レビュー1サイクル、marker連携例外をまとめて本人が承認した。省略可能な確認は省略する。v9必須の本人入力は代行しない。
- `.git/info/exclude` に承認済み57pathを追記した。既存の内容は保持し、対象74ファイルすべての内容ハッシュが前後で一致することを確認した。削除・移動なし。
- Git-visible変更はplan内17ファイルだけになった。新snapshotは `a0318e3282406f09baabb2e80c22dd9d2c04f908d9294950778672de4d2cdcb1`。前後のハッシュ記録は `/private/tmp/fitlog-personal-git-scope-result.json`。
- 正規review-budget extendを1回実行し、qualityの使用済み4 / 上限5になった。追加サイクルのbegin・モデル起動はまだ実施していない。
- 作業フォルダの全体テスト195件成功（85.124秒）。Git-visibleファイル212件だけを取り出した保存内容の検証用コピーでは191件成功（85.426秒）。旧テストバックアップを含めないコピーでも成功した。diff whitespace確認も成功。
- テストログ末尾のCANCELLEDは非対話拒否fixtureの出力であり、テスト失敗ではない。両processの終了コード0とunittestのOKを確認した。
- 正規prepare-runで `PERSONAL-GIT-implementation-3` を予約した。仕様・計画承認を維持し、実装・レビュー結果承認のみ失効した。ローカルテストからv9成功を生成していない。
- 共通入口：`sh /private/tmp/fitlog-personal-git-continue.sh`。準備済みimplementation-3の実行確認から、成功後の実装結果承認まで続けて進む。本人の確認入力は継承されたterminalで行う。承認済み工程は再確認しない。失敗attemptの自動再実行・追加レビュー枠の自動消費・Git操作は行わない。
- 独立レビュー前のQA準備は、implementation-3の成果物確定後に行う。入口はその後も同じパスを使い、次の承認済み工程へ対応させる。

続報：implementation-3は142秒で成功、本人承認済み（revision 25）。保存対象・snapshotは不変。追加枠を正規予約してClaude反証QAを実施し、High/Mediumなし。v9 review-3を準備した（revision 26）。詳細は[追加品質サイクル5](personal-git-quality-cycle5.md)。共通continue入口はレビュー開始→結果承認に更新済み。
