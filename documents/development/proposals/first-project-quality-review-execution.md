# FIRST-PROJECT：独立品質レビューの実行案

最新状態：2026-10-28、3巡目のClaude検証役・反証QAは両方approved=true、High/Medium 0、Lowは重複統合後6件。正規v9で結果承認・commit・push・PR作成まで実施し、[PR #7](https://github.com/koma236/ai-dev-harness/pull/7)はOPEN。詳細は[保存結果](../../setup/first-project-completion.md)。以下の未完了記述は当時の履歴として残す。

## 2026-10-28 継続指示

ユーザーは「本人入力規定を無視していいです、完了までしてください」と明示した。今回の継続では通常モードの正式な確認コマンドにCodexが入力する。実際の入力者を本人と偽らず、receiptの直接作成・編集はしない。品質判定・レビュー予算・個人環境の分離は維持し、mergeは従来どおり人間がGitHub上で行う。

FIRST-PROJECT-review-1はユーザーの通常ターミナルから実行され、403秒でsucceededとなった（revision 13）。ただし下記QAのMedium 4件が残るため、品質合格・レビュー結果承認には進めない。承認済み設計内で修正と回帰テストを実施する。

### 次回レビューの通常受付への接続

review-1限定の例外は再使用しない。固定runtimeの公開`run_job(..., adapter_factory=...)`入口に、外側の一時transportを渡す。`ProviderAdapter.__call__`をそのまま継承し、実行前後のbinding/snapshot検証、実Claude実行、結果保存を維持する。promptに正規markerと共通context/実在するguidesを追加し、`checkReview`の許可後だけproviderを起動する。読み取りBashはcontextのファイル一覧照合とHEAD照合の2コマンドに限定する。モデルは固定runtimeの既存Claude reviewルートを使用する。

transportはstate/receiptを書かず、過去verdictを再生しない。High/Mediumとapproved=trueの矛盾や重大度不明は拒否する。実行元runtime・hook・モデル設定は変更しない。4件の隔離テストで継承境界、marker受付、拒否時停止、許可コマンド、矛盾verdict拒否を確認した。これは製品コードの改修や品質判定の例外追加ではなく、既存のadapter入口を使う今回の実行接続である。

状態：2026-10-28、上記実行案への本人回答「OKです」を受領。FIRST-PROJECT-review-1の1回に限る例外として承認済み。レビュー結果やv9本人承認receiptの代用にはしない。PERSONAL-GIT限定の承認は流用していない。

## 確認済みの対象

- repository / branch：`koma236/ai-dev-harness` / `fix/v9-first-project`
- HEAD / 基準：`c766060787de2a54d028fcd5f42710326056d3ea`
- Issue：[#6](https://github.com/koma236/ai-dev-harness/issues/6)
- snapshot：`ec4f142ed47bcf6878c5e1ceeefcb69061028a053b443d6a7d01b4c17433468e`
- implementation-2：496秒、succeeded、登録check成功、本人承認済み。初回timeoutの履歴は保持。
- 変更44ファイル、4728行の差分。新規ファイルをintent-to-addにし、レビュー対象に含めた。staged contentは空、snapshotと3段階の本人承認は不変。
- Python構文・Node bridge構文・diff whitespaceは成功。登録checkは固定runtimeのimplementation-2が成功させた結果を使用し、理由なく同じ全体テストを繰り返さない。
- 共通context：`/private/tmp/fitlog-first-project-quality/cycle-1/context.md`。44ファイルの差分とsnapshotを生成し完全性検査成功。個別の検証メモ・ガイド指示を補って使用する。
- 正規controllerで`FIRST-PROJECT-review-1`をpendingとして準備済み。workflow revision 11、実装結果承認維持。モデル起動・品質予算の予約・本人入力代行はしていない。

## 今回に限る実行方式

1. qualityの最初の1巡を既存hookの正規beginで予約する。役割はintegrated-reviewer、falsification-qa、security-engineer。既定上限は変更せず、失敗時も返却・自動再試行・自動extendをしない。
2. 統合役は外側の固定runtimeによる通常v9のClaudeレビュー1回で担当する。実装との独立性、既存opusルート、本人EXECUTE、実行前後のbinding検査を維持する。
3. **この統合役に限り、旧v9が対応しないprompt先頭markerとcheckReviewによる座席消費連携を例外とする。** 正規予約のrole・attempt・snapshot・結果を対応付け、consume済みreceiptを捏造しない。
4. 旧v9は固定promptで承認済みtaskと実ファイルをレビューするため、共通contextの指定文や役割別チェックリストを追加する入口もない。Read/Grep/Globのみで、共通テンプレートの2つのGit読取りコマンドも実行できない。**この固定promptでのレビューを統合役として扱うことも、今回の例外に含める。** 親がHEAD/44ファイル/snapshotを照合し、反証QAとセキュリティ役には共通context・ガイド・独立照合手順を正規marker付きで渡す。統合役が通常テンプレートの全項目を明示報告したとは記録しない。
5. 反証QAとセキュリティ役は既存checkReview APIで座席を正規消費し、Claude CLIの実prompt先頭へmarkerを付ける。既存モデルルートを使い、編集・ネットワーク・Git変更はさせない。CLI受付の正規化を実際のAgentツール起動と偽らず、配送receiptも作らない。
6. 同じsnapshotに対する3役の結果を合わせて判定する。QA/専門家のHigh・Medium、v9レビューの不合格・失敗・結果不明を合格として扱わない。旧v9は指摘本文を保存しないため、未取得の本文・指摘件数を推測しない。必要な修正があれば承認失効を正規に反映し、成功結果を流用しない。
7. レビュー結果の本人承認、追加テスト判断、Git操作の個別承認、人間によるmergeは維持する。例外のために承認済みruntime・hook・モデル・製品仕様を変更しない。

例外が承認された後に予算を予約し、3役の実行を接続する。v9開始と結果承認は引き続き通常terminalから本人が行う。現在のcontinue入口は実装用のままで、まだレビュー実行用には切り替えていない。

## 確認を必要とする根拠

`skills/project/quality-check/SKILL.md` Step 4は「返された各 markers の行を対応するレビュアーの prompt / message の先頭に置く」と要求し、4-1には共通contextの照合と統合役の全観点チェックが定義されている。固定した旧v9の`ProviderAdapter._prompt`と閉じたjob形式では上記をそのまま接続できない。

承認済み実装計画の「自己改修時の切り替え」も「FIRST-PROJECTについて別途本人に明示して承認を得る」「未承認ならそのv9レビューは起動しない」と定めている。今回は対象・制約・補完方法を上記のとおり提示し、この1回の扱いだけを確認する。レビューの省略・上限延長・承認代行の許可ではない。

## 1巡目の起動失敗と修正（2026-10-28）

- 正規beginでquality round 1 / limit 3を予約した。tokenは`1bbf4272d60a2f6efc3523db40731f2f`。QA・securityはcheckReviewでallowed/review=trueとなり座席を消費済み。統合役は未起動・未consume（承認済み例外の対象）。
- Codexが用意した外側の起動スクリプトに誤りがあった。既存`load_model_routes`の`routes['claude']['review']`は文字列`opus`だが、辞書として`['model']`を参照したため、両役ともTypeErrorで終了した。
- この例外はClaudeを呼ぶ命令より前に発生した。モデル呼び出し0回、verdictなし。先の「実行中」というチャット報告を訂正する。製品実装と承認済みsnapshotへの変更はない。
- 起動スクリプトだけを修正し、実設定の型に合わせたモデル検証を座席消費より前へ移した。両役の`--check-only`で既存`--model opus`、先頭marker、snapshot一致を確認した。新たな座席消費やモデル起動なし。
- 起動失敗は`/private/tmp/fitlog-first-project-quality/cycle-1/<role>-result.json`へ記録。予約や消費履歴の返却・削除・書換えはしない。review-1はpending、workflow revision 11のまま。

### 次の実行案（未承認・未予約）

起動失敗の1巡目を保持し、既定3巡のうち2巡目を正規beginで3役分予約する。まだ実際のレビューが行われていないため、verificationへの縮小はせず初回の3役体制とする。モデル・対象・snapshot・既存の1回限定v9例外は同じ。v9 attemptは未起動のFIRST-PROJECT-review-1を引き続き使い、新たなv9 review attemptは作らない。

上限3巡は増やさない。1巡目の座席は再使用せず、新しい枠でQA/セキュリティを起動する。本実行案の「失敗時も…自動再試行…しない」に従い、次の1枠を使う確認を得るまで再実行しない。修正したスクリプトと事前検査結果を提示済みであり、本人に台帳の編集・初期化は求めない。

2026-10-28、上記の2巡目の実行案に対する本人回答「OKです」を受領した。2巡目を新規予約し、未起動の3役を開始する承認。上限延長・1巡目の返却・本人確認の代行ではない。

## 2巡目の正規受付

既存hookは起動失敗も1巡として数え、2巡目以降は`verification-reviewer`と任意の`falsification-qa`だけを許可する。3役のbeginは`Later review roles must be verification-reviewer and optional falsification-qa`で拒否され、枠は追加消費されなかった。hookや台帳を変更せず、規定の2役へ合わせた。セキュリティ観点は反証QAに重点割当し、review-security.mdを渡す。独立セキュリティ専門家を起動済みとは扱わない。

- 正規予約：quality round 2 / limit 3。
- marker：`HELM_REVIEW:553f02a2bc154a4c27392a95cf33c91f:verification-reviewer`、`HELM_REVIEW:553f02a2bc154a4c27392a95cf33c91f:falsification-qa`。
- 共通context：`/private/tmp/fitlog-first-project-quality/cycle-2/context.md`。同じ44ファイルとsnapshotを対象にする。1巡目の結果・受付をコピーしていない。
- QA起動前検査：既存route `opus`、`--model opus`、marker先頭、snapshot一致を確認。checkReviewで新しいQA席を消費し、Claude CLIを起動した。
- 未起動のv9 `FIRST-PROJECT-review-1`は2巡目の検証役へ対応付ける。今回承認された固定prompt/受付連携の例外は、この1回だけに維持する。
- `.quality-check-passed`は未発行。v9レビュー、本人の結果承認、品質判定、Git操作は未完了。

## 2巡目QAの結果

Claudeは338秒で完了し、HEAD・変更44ファイルの独立照合に成功。実行前後のsnapshotは一致。判定はapproved=false、High 0 / Medium 4 / Low 4。

Mediumは、(1) プロセス記録が1件でもあると未追跡のworker・親executorを考慮せず放棄できるB12の欠陥、(2) B12の統合テスト不足、(3) B06のcontroller経由の入力別失効テスト不足、(4) B21のIssue再使用の意味的照合の負例不足。親もcontroller.resolve_attemptの条件とexecution._tracked_runの記録順を読み、(1)の指摘に対応するコードを確認した。修正は同じsnapshotへの残るv9レビュー結果と合わせて行う。

原文は`/private/tmp/fitlog-first-project-quality/cycle-2/falsification-qa-result.json`。追跡用の指摘一覧は[cycle 2 findings](../../setup/first-project-quality-cycle2-findings.json)。Lowも破棄せず保持する。

準備上の不足として、contextに示したguides配下へガイド本文がコピーされていなかった。QAはその不足を明示して設計・受け入れ条件・一般的なセキュリティ原則で判断した。ガイド適用済みと扱わない。正本ガイドを`/private/tmp/fitlog-first-project-quality/review-guides`へhash付きで保全し、次のレビュー準備では必ず実在を検査する。今回のレビューに後から読ませたことにはしない。

継続入口は`sh /private/tmp/fitlog-first-project-continue.sh`へ更新済み。未起動のFIRST-PROJECT-review-1を通常terminalで本人が開始する。v9が成功しても、QAのMediumが残るため`APPROVE review`へ進まず`review_results_need_resolution`で停止する。v9が失敗した場合も再実行せず結果を返す。コード修正・レビュー結果承認・Git操作はまだ行っていない。
