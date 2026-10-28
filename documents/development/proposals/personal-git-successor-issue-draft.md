# fix(v9): 個人Git設定とClaude認証環境の改修を保存する

既存Issue https://github.com/koma236/ai-dev-harness/issues/3 の後継。
USER環境の最小修正を追加して仕様・計画を再承認したため、現行v9のIssue照合用に今回限り後継Issueを作成する。旧Issueと承認receiptは履歴として保持する。

対象はtask PERSONAL-GIT、branch fix/v9-personal-git-environment。
初回開発の工程分離（FIRST-PROJECT）とFitLogアプリ本体の開発は別task。

- 個人profileからGit/GitHub設定を自動選択し、既定の共有設定へ戻らない。
- token・askpass・設定注入などの環境継承を除外する。
- path、所有者、権限、include、accountを検証し、秘密を診断に出さない。
- 個人・local・worktree設定の識別をproposalへ固定し、変更時は失効させる。
- Claude認証が認識されるよう、限定環境へ非秘密のUSERを継承する。USERがない場合は捏造しない。
- テストログの一時領域分離、Git fixtureの初期branch固定、環境継承の回帰テストを含む。

仕様：documents/v9/personal-git.md
受け入れ条件：documents/v9/personal-git-acceptance.md のPG-A01〜PG-A09
保存計画：documents/v9/personal-git-save-plan.md

保存対象は承認済みplanの17ファイル。旧資料・backup・キャッシュはローカルに保持し、今回のcommitには含めない。
実装担当はCodex、独立レビューはClaude、モデルは既存ルートを使用する。
v9の本人承認と各Git操作の個別確認を維持し、mergeは本人がGitHub上で行う。
