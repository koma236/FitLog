# v9初回開発の準備課題と対応案

> 調査・提案のみ。共通ハーネス、承認receipt、workflow、checksを変更していない。

## 確認した制約
2026-10-27時点の`~/project/ai-dev-harness`を読み取り確認した。

1. `scripts/v9/controller.py`の`_inputs`（63行付近）はexecution_readyとspec_readyが両方trueでないと初期化・承認へ進めない。FitLogは実アプリがなくchecks=[]なのでfalse。初回基盤でchecksを作る前に、その仕様・計画を承認する入口がない。
2. `scripts/v9/cli.py`のprepare-run（117行付近）のphaseはimplementation/reviewのみ。`skills/ai-dev-chat/SKILL.md`は「implementation result approval precedes review」と定める。実装前のClaude設計レビュー専用phaseは現行入口にない。実装後reviewを設計レビューと偽装しない。
3. `scripts/v9/handoff.py`の`_validate_dependencies`（316行付近）は依存taskのbranch/spec_hash/plan_hash等の一致とready_for_gitを要求する。全体計画FL-01〜10を別Issue・別branchでそのまま実行することはできない。

## 共通ハーネスへの変更提案（別作業として要承認）
- 仕様/計画の準備・承認と実装可能性の判定を分離する。checks未設定を実装結果の合格条件にはしない。
- 読み取り専用の独立設計レビューを通常ターミナルhandoffで実施できる入口を追加する。Codex実装／Claudeレビューと既存ルーティングを保持する。設計レビューだけで実装結果のreceiptやready_for_gitを生成しない。
- 初回bootstrapの狭い実行範囲を設ける。人間が仕様・計画・実行を承認し、実checksの作成・実行を確認するまで後続機能・Gitへ進めない。設定変更に伴うbinding更新・承認失効を正規手順で扱う。
- 通常モードの4段階承認、Git操作ごとの承認、本人merge、個人環境の分離は維持する。

受け入れ試験案：空checksの通常実装は拒否／仕様準備は可能／設計レビューから実装やGitへ昇格しない／bootstrap失敗・ダミーcheck・receipt代行では進めない／実checks登録によるbinding変更を隠せない／既存v9テストが通る。具体設計と独立レビューはハーネス側の変更着手時に必要。

## Issueと依存の扱い
`.ai-dev/plan.draft.json`は全体の計画索引であり実行用に登録しない。Issue開始時にそのIssueの仕様・ACへ限定したmanifest/planを作って承認する。前提Issueは本人によるmerge済みPRと基準commitを確認し、計画に記録する。branch間の依存を同一workflowのdepends_onへ付け替えない。未mergeの前提を削除して通過させない。

正式な既存経路で解決できる場合はそれを優先する。別providerの直接起動、v8への無断変更、空checksの成功扱いによる迂回は行わない。仕様の参照検査は人間承認やアプリchecksとは別であり、未解決事項がある間はspec_ready=falseを維持する。

## 2026-10-28 改修後の経路

上の制約1・2は改修前の調査記録。ハーネスmainの308a7f0（PR #7）でschema 10のdesign_review・bootstrap・configure-checks・verifyが導入された。FitLogのFL-01は新経路で初期化済み。設計レビューは実行前の独立Design Gateを兼ね、checks空の合格扱いはしない。workflowの別branch依存の制約3は継続し、Issueごとのmanifest/planを使う。手順の正本はハーネスのdocuments/v9/first-project-workflow.md、FL-01設計はfl-01-foundation-design.md。
