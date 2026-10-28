# PERSONAL-GIT：Claudeレビューの実行案

現在の状態：implementation-2とreview-2は成功し、4段階の本人承認済み。workflow revision 20、現在のbindingと一致し、state上のready_for_gitはtrue。ただし下記のGit準備の障害は未解決。review-1の失敗と下記の過去の予約・診断は履歴として保持する。

## 確認済みの結果

- v9 stateは実装結果承認済みで、現在の入力bindingと一致する。
- implementation-1は成功、287秒、登録済みcheck成功。Python変更6ファイルの構文解析とdiff whitespace確認も成功。
- 先行変更の3役レビューと再確認は[既存記録](../../setup/v9-personal-git-validation.md)にある。過去のreviewerはGPTであり、Claudeのレビューと読み替えない。
- `/private/tmp/fitlog-quality-check/cycle-2/snapshot/`と現在の既存変更11ファイルを比較。10ファイルはbyte一致、`tests/test_v9_gitops.py`だけ追加・強化あり。
- 新しい仕様manifest・plan・project設定と保存用文書は過去のレビューに含まれていない。現在のClaudeレビューではこれらも対象とする。
- 既存の`.quality-check-report.json`は別件READMEの記録なので、今回の合格証拠にしない。上記個人Gitの記録と区別する。
- review-budgetのqualityは2/3回を予約済み。台帳を消さず、過去のusedが空でも消費枠を戻さない。

## 今回限りの実行案

1. qualityの残る1枠を、既存hookの正規beginでverification-reviewerとして予約する。上限は増やさない。
2. 予約番号・対象attempt・実行前snapshot・結果を作業記録で対応付ける。
3. 既存v9の通常handoffを本人が起動し、既存ルートのClaude opus（runtimeはOpus 5.5を指定）で`PERSONAL-GIT-review-1`を1回実行する。本人のEXECUTE確認は省略しない。
4. 現行ProviderAdapter._promptは固定文を先頭へ付け、jobスキーマにreview markerの受渡し項目がない。そのため、**今回のv9レビューに限り、prompt先頭markerとcheckReviewによる座席消費の自動連携を適用できない例外**を認める。正規予約による回数制限は維持し、座席消費receiptや成功記録を捏造しない。
5. 結果が不合格なら合格扱いにしない。3/3回を使い切った後の追加レビューは本人判断とし、自動extend・別branchへの移動・別名での追加起動をしない。
6. レビュー結果の本人承認、Git操作の個別承認、人間によるmergeはそのまま維持する。既存の成果物と承認済みruntimeをこの例外のために変更しない。

この例外は既存v9とquality-check受付の接続に限定する。Claudeレビューの省略、旧レビューのv9 receipt化、最終quality-checkの未実施項目を合格とすることは含まない。恒久対応は承認済みの初回開発順序修正の設計へ既に含まれるadmission連携で扱う。

根拠：quality-check SKILL Step 4は「返された各 markers の行を対応するレビュアーの prompt / message の先頭に置く」と要求する。現在のv9実装ではこれを満たせないため、例外の採用は本人に確認する。通常v9レビューの依頼をこの例外への包括承認とはみなさない。

## 予約とhandoffの対応

- branch：`fix/v9-personal-git-environment`
- task / attempt：`PERSONAL-GIT` / `PERSONAL-GIT-review-1`
- phase / round / limit：`quality` / `3` / `3`
- role：`verification-reviewer`
- 正規beginのmarker：`HELM_REVIEW:716716b8ed80f0977055942d007179a9:verification-reviewer`
- 実行前snapshot：`a7c4028ba9cce5b003640a9c5e6803aaf19d4d9b9adeee6bb578b1a037be5bf1`
- workflow revision：7、review attemptはpending、仕様・計画・実装結果は本人承認済み。
- job basename：`3d4ed14400fbaee340cbb83c73084363b890506cd827a1c00a682f7d60e4a4e1.json`
- provider：Claude、既存review route `opus`。jobへモデル指定を追加しない。
- attempt上限：1 round / 3600秒。予約枠の追加・再予約・自動再試行なし。
- 短い起動入口：`sh /private/tmp/fitlog-personal-git-review.sh`。既存v9 handoffを呼ぶだけで、確認入力・承認receiptを作成しない。

markerはここで対応を記録するだけで、実際のpromptへ挿入済み・checkReviewによる座席消費済みとは記録しない。実行結果は本人による起動後にstateから確認する。

## 実行結果と認証環境の診断

本人起動後、review-1は5秒、failed/provider_failed。state revision 9、review承認なし。現在のbindingは実装結果の承認時と一致。レビュー合格/不合格verdictを受領したとは扱わない。quality予約は3/3のまま保持し、返却・追加予約・再実行なし。

Claude CLIは2.1.299。必要なdontAsk/json-schema/no-session-persistenceオプションはhelpに存在する。モデルを起動しない`claude auth status`を、通常ターミナル相当の権限で比較した。

| 環境 | exit code | loggedIn |
|---|---|---|
| 通常環境 | 0 | true |
| 現行v9の限定環境 | 1 | false |
| 限定環境＋USERだけ | 0 | true |
| 限定環境＋LOGNAME/SHELL/SECURITYSESSIONID/XPC_SERVICE_NAME/__CF_USER_TEXT_ENCODINGの各1項目 | 1 | false |

認証情報は取得・コピー・表示していない。モデル呼出しなし。現行v9はprovider失敗時のstderrを保存しないため、当時の原文までは復元できないが、USERの除外による認証認識の失敗を再現した。

最小修正案は`execution.py`の既存環境allowlistへ非秘密の`USER`を1項目加えること。候補は`/private/tmp/fitlog-v9-user-env.patch`、未適用。`/private/tmp/fitlog-v9-user-regression.py`でClaude adapterへのUSER伝達とtoken/askpass非継承を検証し、現行コードでは1 failure、候補では1 success。これはfake providerの回帰検証であり、実Claudeレビューの成功ではない。

execution.pyはruntime digestの対象で、今回のPERSONAL-GIT planの編集許可pathには含まれていない。適用には作業範囲を反映した仕様・計画とv9再承認が必要。旧承認・Issue proposal/resultの結び付きを現在値へ書き換えない。Git操作の内容変更・再準備も各正規手順で扱う。追加レビューは本人が1回追加を承認した場合だけ正規extendし、失敗attemptを再開・成功化しない。

## USER修正の承認・実施

修正範囲追加とClaudeレビュー1回追加へのユーザー回答「はい」を受領した。

- 仕様・受け入れ条件にPG-R09/PG-A09、planのpathsにexecution.pyを追加。既存の矛盾する互換性説明も更新し、source hashを再計算した。
- 親Codexが明示承認された最小変更として、実行環境allowlistへUSERを1項目追加した。モデル・hook・token除外は変更していない。
- 回帰テストは実際の子processをClaude adapterから起動するオフラインfixture。USERを要求し、token/askpassの非継承も検査。追加テストは修正前に終了コード3で失敗、修正後に成功。
- 全体テスト194件、78.659秒、終了コード0。Python構文・diff whitespace確認も成功。末尾CANCELLEDは非対話拒否fixtureの出力であり、実レビュー取消ではない。
- 修正済みの実v9環境でauth statusはexit 0 / loggedIn=true。モデル呼出し・再ログイン・token表示なし。
- 正規extendを1回実行し、qualityはused 3 / limit 4。追加枠の予約・Claude再起動は未実施。
- 失敗attemptを保持する。ローカル修正・テスト結果からv9の成功attemptや本人承認receiptを作らない。更新後の仕様・計画を本人が承認した後、改めて通常implementationで検証し、結果承認後に新review attemptへ進む。

再承認入口：`sh /private/tmp/fitlog-personal-git-reapprove.sh`。仕様と計画を順に個別確認する。旧Issue #3と旧承認の連鎖は当時の履歴として保持し、Git操作を無断で追加・編集していない。

## 追加レビューの準備

- 更新後の仕様・計画は本人承認済み。implementation-2は309秒でsucceeded、登録済みcheck成功。その実装結果も本人承認済み。
- 正規beginによる追加予約：quality round 4 / effective limit 4、verification-reviewer。既に承認された1回の延長を使用し、追加延長・再予約は行っていない。
- marker対応：`HELM_REVIEW:f0db5ac88b026bce927642700b3f5a8a:verification-reviewer`。
- attempt：`PERSONAL-GIT-review-2`、pending、workflow revision 17。
- snapshot：`2cf5222c57f3a0252d95825a431c91d77d4face760be1c79960d12ccc4525d3a`。
- job basename：`538d394aacb9bf920fd8508fe931f098861d453004a20694e6df63bb7bcb7ed5.json`。
- providerはClaude、モデルは既存ルート。通常handoffの読込み検証で入力binding・実装結果承認・pending attemptを確認した。
- 起動入口：`sh /private/tmp/fitlog-personal-git-review2.sh`。本人のEXECUTE入力が必要で、AIは実行・確認入力を代行しない。
- 前述の今回限りのmarker連携例外を、この承認済み追加レビューにも適用する。markerをpromptに挿入した、座席消費receiptが発行されたとは扱わない。
- レビュー結果・レビュー結果の本人承認は未取得。旧Issue #3と再承認後のreceipt照合は、Git準備前に解決する必要があり、旧receiptは変更しない。

## 追加レビューの結果

- 本人の通常ターミナル実行後、review-2はsucceeded、error_categoryはnull、1 round / 119秒。WorkflowStoreで検証したstate revisionは19。
- input/output snapshotはいずれも`2cf5222c57f3a0252d95825a431c91d77d4face760be1c79960d12ccc4525d3a`。controllerの現在入力から再計算したbindingとstateのbindingは一致する。
- 仕様・計画・実装結果の本人承認は保持され、レビュー結果の本人承認はまだない。レビュー本文は現行runtimeで保存されないため、指摘件数や本文を推測して記録しない。
- 本人承認入口：`sh /private/tmp/fitlog-personal-git-approve-review.sh`。AIは承認文字列を入力せず、receiptを作成しない。
- この成功のみでGit操作や最終quality-check全項目の完了とは扱わない。旧Issue receiptの照合問題は引き続きGit準備前の未解決事項。

## レビュー結果承認後のGit準備確認

- WorkflowStoreでrevision 20と4段階の人間承認を確認。controllerで再計算した入力bindingも一致する。
- Issue #3の成功結果は存在するが、そのproposalのapproval_digestと現在の仕様・計画receiptのdigestは不一致。現行gitopsのsame_gate条件を満たさず、このIssue結果を現在のcommit前提に使えない。
- 現行commitはGit-visible変更全件を対象とする。作業ツリーにはplanの許可path以外の旧資料・backup・pycache等があり、そのままでは今回の保存範囲を超える。除外・移動もsnapshotを変えるため、承認済みsnapshotを保持したまま済む整理とは扱えない。
- 追加Issue作成、receipt編集、無関係ファイルの削除・移動、承認の無効化を伴う変更は行っていない。必要な対処と承認への影響をまとめる前に、追加の手動操作を順次依頼しない。
