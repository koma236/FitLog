# Issue作成案（未作成）

対象：`koma236/ai-dev-harness`

タイトル：`fix(v9): 初回生成・実検証・設計レビューの工程を分離する`

以下がIssue本文案。個人アカウントkoma236と対象repositoryを2026-10-27に読み取り確認した。確認時点で既存Issueは終了済みの#1のみ。この案にIssue番号は割り当てていない。

---

新規プロジェクトではcheckコマンドがまだなく、現行v9の準備処理が停止する。初回生成を通常implementationとして扱うと、生成と検証の証拠が混ざるため、工程と承認条件を分離する。

## 変更内容

- checksが空でも草案準備と独立設計レビューを可能にする。実チェックなしの実装承認やGit-readyは認めない。
- schema 10にdesign_review/bootstrap/verifyを追加し、通常implementation/reviewと合わせてphase別証拠を定義する。
- bootstrap→予定checks登録→計画再承認→verify→独立品質レビューを接続する。
- design binding、入力変更時の失効、旧state移行、中断解消、review-budget連携を実装する。
- 初回の計画再承認後も同一Issueを使える限定照合を追加する。未実行proposalの失効条件は維持する。
- CLI・運用説明・エラー一覧・ai-dev-chatを更新する。

## 受け入れ条件

設計v3 §9のB01〜B23を満たす。特に、生成だけで実装承認が成立しないこと、入力変更で正しい承認が失効すること、Issue作成1回のまま初回生成からcommit proposalまで進むことを結合テストで確認する。

通常開発・v8・個人Git設定の回帰を維持する。モデルとhook本体は変更しない。CLI名はv9のまま、state/job/Gitデータ/planのschemaを10へ更新し、既存承認は再取得が必要と案内する。

## 検証・運用

Codexが実装し、Claudeが既存モデルルートに従って独立レビューする。Python unittestと一時Git/fake provider fixture、Node admission bridge検証を行い、quality-checkで判定する。仕様・計画・実装結果・レビュー結果、各Git操作の本人承認を維持し、mergeは人間が行う。

先行するpersonal Git対応の未コミット変更を本Issueへ混在させない。作業開始前に基準commitと専用branchを確定する。
