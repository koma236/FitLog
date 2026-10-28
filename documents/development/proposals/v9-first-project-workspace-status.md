# 初回開発順序修正：作業場所と承認待ち

## 最新状況

2026-10-28追記：FIRST-PROJECTの初回実装は3600秒でtimeout。途中成果を保全し、未完了のプロセス識別処理1件を修正した。全回帰237件成功。仕様・計画とIssue #6を維持してimplementation-2を準備済み（revision 7 / pending）。本人の開始確認待ち。詳細は[タイムアウトからの続行記録](../../setup/v9-first-project-timeout-recovery.md)。以下の初期化時点の記述は2026-10-27の準備履歴。

先行PERSONAL-GITは本人によるPR #5のmergeまで完了し、GitHubの結果を確認した。Issueは[#4](https://github.com/koma236/ai-dev-harness/issues/4)、feature commitは`df0cd4f5a920add6748bf30978a2ccf5f8fee15b`、統合commitは`c766060787de2a54d028fcd5f42710326056d3ea`。4段階承認、実装・Claudeレビュー成功、Git操作の正規receipt、品質flagとの一致を確認済み。

FIRST-PROJECTの専用worktree・branchを統合commitへfast-forwardし、設計v3と既存草案を保持した。実装未着手。新基準のbaselineは191 tests / 80.946秒 / OK。実行元は外側の検証済みschema 9版に固定し、worktree内で新schema 10を実装・検証する。

実装計画とテスト設計は対象worktreeの`documents/v9/first-project-implementation-plan.md`、`first-project-test-design.md`へ保存し、manifest sourceへ登録した。実装用JSONは`.ai-dev/first-project.spec.json`と`.ai-dev/first-project.plan.json`。B01〜B23をP1〜P7で扱う。

Claude計画レビューはplan枠1/1の受付済みだが結果未回収。CLIプロセス終了を確認した。合否と終了原因は不明であり、合格扱いも再予約もしない。writing-plansの上限到達時規則に従い、この不足を計画へ記録した。実装後のClaude独立品質レビューは別途必須。旧v9との品質レビュー連携例外はFIRST-PROJECTについて未承認であり、PERSONAL-GIT限定例外を流用しない。

正規controllerでFIRST-PROJECT workflowを初期化済み。revision 0、4承認null、attempt 0件。source・実行元を固定する検査と、通常terminal専用の`sh /private/tmp/fitlog-first-project-continue.sh`を用意した。入口の構文・読み取りpreflight・非TTY拒否を確認し、承認やGit操作を代行していない。次は本人が仕様・計画・Issue・実装開始を順に確認する。

以下は当初準備時の履歴であり、現在のHEADやテスト結果ではない。PERSONAL-GITの保存詳細は[保存完了記録](personal-git-final-save-actions.md#実行完了の確認)を参照。

## 当初の準備記録

2026-10-27。番号なしbranch先行の例外承認を受領し、実行した。

## 今回の改修

- repository：`koma236/ai-dev-harness`
- worktree：`/Users/saki/project/ai-dev-harness/.worktrees/first-project`
- branch：`fix/v9-first-project`
- 現在HEAD：`a35f6f8e9b8c862dfafa1dbe9a01c8570d41abe3`
- task：`FIRST-PROJECT`。workflowはまだ初期化していない。
- `.ai-dev/first-project.spec.json` / `.ai-dev/first-project.plan.json`：現行schema 9で検証成功、受け入れ条件B01〜B23を1 taskに対応付けた。提供する新機能のschema 10と混同しない。
- 設計v3と第2回対応表のコピーは元文書とbyte一致を確認済み。
- configは実在するPython unittestを登録。設定解決成功はテスト成功・実行許可の意味ではない。
- production codeの変更なし。先行personal Git変更の持ち込みなし。

古いHEADに対するbaseline testは167件、failure 3 / error 24、終了コード1。代表原因は、テストが実ユーザーのlog領域へ書こうとしてsandboxに拒否されたことと、旧Git経路がグローバルURL rewriteの影響を受けたこと。これを成功としない。既存personal Git修正側ではログの一時領域への隔離と個人Git環境の選択が実装されている。

## 先行変更の保存

- 作業場所：`/Users/saki/project/ai-dev-harness`
- branch：`fix/v9-personal-git-environment`（既存）
- task：`PERSONAL-GIT`
- `.ai-dev/personal-git.spec.json` / `.ai-dev/personal-git.plan.json`：schema 9検証成功。8条件を既存仕様と保存計画に対応付けた。
- 資料：`documents/v9/personal-git.md`、`personal-git-acceptance.md`、`personal-git-save-plan.md`。
- 登録check：`python3 -B -m unittest discover -s tests`、timeout 600秒。
- 今回の実測：189件、92.966秒、終了コード0。末尾CANCELLEDはlegacy非対話拒否のfixture出力。実providerを起動した記録ではない。
- 正規`init-workflow`でschema 9 / revision 0を作成。4承認はすべてnull、attempt 0件。AIによる承認代行なし。
- 元の11ファイルの既存差分は維持。作業中のcommit、Issue作成、push、PR作成なし。

次はPERSONAL-GITの仕様・計画に対する通常terminalでの本人承認。これは今回の順序修正の設計承認をやり直すものではない。先行変更を保存できる基準にするための別workflowであり、以後のIssue・結果・Gitの個別承認も維持する。
