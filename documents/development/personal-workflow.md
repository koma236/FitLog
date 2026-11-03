# FitLog 個人開発運用

本書はユーザー指定の運用を定め、配布元の一般ルールと共通skillに優先する。
2026-11-03の承認により、通常skillと自然言語の承認で開発する。

## 承認と自律実行

- 仕様・独立設計レビュー結果・短い実装計画をまとめて提示し、チャットで一度承認する。
- 承認には範囲内のIssue作成、隔離branch/worktree、実装、文書、検証、独立品質レビュー、指摘修正、commit、feature branchへの通常pushを含める。
- 工程ごとの再承認や専用のTTY入力を要求しない。実行結果を確認し、未実行・失敗を成功扱いしない。
- 重大な範囲変更、不可逆操作、本番反映、予算超過、原因不明で安全に進めない障害はまとめて相談する。既存development-policyの例外を適用する。
- PR作成は内容を完成させて最後に確認する。mergeは本人がGitHubで行う。AI merge、auto-merge、trunk直接更新、force、hook回避は禁止。
- OS/sandbox権限申請は工程承認とは別に扱う。拒否時に制御を迂回しない。

## 個人環境とGitHub

- 対象はkoma236/FitLog。CodexはCODEX_HOME=$HOME/.codex-personalを使う。会社用~/.codex、会社repo、manabi-backofficeを含むpathを探索・変更しない。
- GitHubには既存の~/.local/bin/gh-koma236を使う。既定ghやtoken環境変数へfallbackしない。wrapperはGH token上書きを除去し、個人gh configを選択する。
- commitには~/.config/git-koma236/configの個人name/emailを使用する。共有Git設定や既定global設定は変更しない。
- 通常Gitの送信には既存SSH接続先github-koma236を使う。操作直前にoriginの実効URLがgit@github-koma236:koma236/FitLog.gitであり、SSH認証応答のaccountがkoma236であることを確認する。別のpush URLが設定されている場合も同じ照合を行う。不一致・未確認なら送信しない。
- SSH認証を確認できないとき、HTTPSや別accountへ自動切替しない。credential helperを使うHTTP操作が必要なら、個人wrapperを指す既存個人Git設定を明示し、選択を確認してから実行する。
- Issue/PR/API操作の前にgh api userのaccountとrepoを確認する。Gitの通常commandをhookへ直接提示し、送信を別scriptへ隠さない。
- 1 Issue = 1 branchを原則とし、自分の変更だけをcommitする。PR本文は通常のbody-file入力で渡す。

## 品質と実行記録

- 通常の設計・実装・test-design・quality-check skillを使う。レビュー予算と独立レビューを維持する。別モデルだけを独立性の証明にしない。
- .ai-dev/project.tomlは11 checksのコマンド台帳として残す。親が登録argv/cwdを順番に直接実行し、新しいrunnerを作らない。
- 各checkのid、終了コード、実行時のcommitと未commit差分の対象snapshot、日時をquality-check報告へ保存し、PR本文の検証欄へ要約する。
- checksは[並列開発運用](personal-parallel-workflow.md)の共有runtime排他枠内で実施する。スタック・port・checksは実設定を読み、他担当のDB/image/processを変更しない。
- GitHub Actionsはbuild/lint/型/全テスト/migrationとci-requiredを維持する。AIレビューはCIの判定に使わない。配布元skillの古い「CIはビルドのみ」は適用しない。
- CI相当の独立再現では別Compose projectだけでなく別image/volumeも必要。共有dev imageを上書きしない。実行済みE2Eの失敗を隠さない。
- hook登録・信頼・実clientでの実行確認を区別する。fixture結果を実clientでの採用確認と呼ばない。新運用採用後、実clientで安全なdry-run拒否を確認し、未確認clientはnot_runと報告する。
- 通常ゲート回帰はnode --test scripts/test-quality-gate.cjs。CIへの追加は今回行わないため、ローカル品質チェックで必ず実行する。

## 作業の分離

- [並列開発運用](personal-parallel-workflow.md)を正とする。1 worktreeのwriterは1セッション。他taskのrestore/stash/cleanやbranch切替を行わない。
- skillの入口は.claude/skills・.codex/skills・.agents/skillsから共通skills/を参照する。リンク不足は導入済み版のlink-skillsで整備する。
- 共有ai-dev-chatへのlocalリンクは新規導入しない。既存Rootのリンク解除は本人の統合と採用確認後にリンクだけを対象として行い、共有sourceや共通excludeを変更しない。旧sessionへの自動反映は保証しない。

## 旧運用の履歴

2026-11-03以前のv9専用spec/plan・設計原本・提案・receipt・実行結果は履歴として保持し、1byteも書き換えない。requirements.mdとdocs/task-plan.mdのv9手順も旧運用の記録であり、製品要件を除く運用判断は本書を正とする。
旧v9対応branchの採用や2件のPR作成は新運用の前提にしない。旧taskを再開したり消費予算を初期化したりしない。
共有runtime自体は削除しないが、新規作業でv9を実行しない。hookは旧経路全体の遮断を保証せず、この禁止は運用規則が担う。review-budget内のreceiptsは別の機構であり維持する。
