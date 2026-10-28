# PERSONAL-GIT 保存操作の具体案

対象はprivate repo `koma236/ai-dev-harness`、本人アカウント `koma236`。v9個人環境経由でGitHub APIと実効URLを読取り確認済み。
送受信URLは `https://github.com/koma236/ai-dev-harness.git`。branchは `fix/v9-personal-git-environment`、PR baseは `main`。

## 正常時の操作順

1. 後継Issue作成：タイトル「fix(v9): 個人Git設定とClaude認証環境の改修を保存する」。[本文](personal-git-successor-issue-draft.md)。旧Issue #3は参照だけで、編集・終了しない。
2. commit：`fix(v9): apply personal Git environment and retain Claude login user`。承認済みplanの17ファイル全件のみ。親HEADは`a35f6f8e9b8c862dfafa1dbe9a01c8570d41abe3`。
3. push：現在のfeature branchだけ。v9固定refspec `HEAD:refs/heads/fix/v9-personal-git-environment`。forceなし。
4. PR作成：タイトル「fix(v9): 個人Git設定とClaude認証環境を適用する」。headは上記branch、baseはmain。実装・品質・例外を本文へ記載する。作成された後継IssueをClosesで参照し、旧Issue #3はRefsにとどめる。mergeは行わない。

## 本人確認と自動確認

- 共通入口：`sh /private/tmp/fitlog-personal-git-continue.sh`。
- 4操作を順に正規v9 proposal/git-actionで処理する。具体的proposalを表示し、各操作の本人確認文字列を通常terminalで入力する。AIやscriptは確認入力を代行しない。
- 最初のIssue確認文字列は `APPROVE ISSUE 8c6a57eee1e2`。後続操作のdigestは先行操作の実際の結果から決まるため、予測せず各表示を使用する。
- 失敗・取消・state/binding/対象変更があれば停止する。続きから再実行した場合は、正規receiptの照合に成功した操作だけ重複実行を省略する。
- `save-jobs.json`はjob pathだけの進行メモであり、承認receiptではない。結果はv9の実際のresultと元proposalを照合する。
- commit後に保存内容・clean worktree・未追跡混入検査を確認し、成功したcommitに`.quality-check-passed`を結び付ける。検査が通らなければpushへ進まない。
- PR本文のFlag commitと後継Issue番号は、それぞれ実際のcommit/Issue成功結果から設定する。架空のSHAやIssue番号を使わない。

準備時点のworkflowはrevision 29、snapshot `a0318e3282406f09baabb2e80c22dd9d2c04f908d9294950778672de4d2cdcb1`、4承認済み。外部変更は未実行。

## 実行完了の確認

本人が共通入口で各操作を個別承認し、Issue・commit・push・PRの正規成功resultを取得した。親が元proposalと現在のworkflowを使って全4件のreceiptを再照合し、成功を確認した。

- 後継Issue：[ai-dev-harness #4](https://github.com/koma236/ai-dev-harness/issues/4)
- commit：`df0cd4f5a920add6748bf30978a2ccf5f8fee15b`
- PR：[ai-dev-harness #5](https://github.com/koma236/ai-dev-harness/pull/5)
- GitHubのPRはopen、merged=false、head SHAは上記commit、baseはmain。
- 現在のbindingと4段階承認は一致。Git-visible作業ツリーはclean。対象外57ファイルはローカルに保持されている。
- `.quality-check-passed` のbranch/commitは実commitと一致する。
- 旧Issue #3の変更・終了、AIによるmerge、main直接更新は行っていない。

PERSONAL-GITの保存とPR作成は完了。mainへの統合は本人がGitHub上で行う。FIRST-PROJECTの工程改修およびFitLogアプリ本体の実装は未完了で、このPRの完了と区別する。
