# FitLog

筋トレ記録・プロフィール・画像・コメント・いいねを扱う個人開発プロジェクトです。React/TypeScript、Python/Django、PostgreSQLをDockerで実行します。

## AWS準備の現在地（2026-11-07）

A（基盤・費用/操作管理）、B（成果物照合・配置/初期化・稼働証跡）、C（E2E・撮影・限定性能の検証harness）の実装とローカル検証を行っています。A/Bはmainへ統合済み、Cは[PR #63](https://github.com/koma236/FitLog/pull/63)で相互レビューコメント対応済みです。実AWSの構築・配置・公開・試験・破棄は未実施です。

現在の到達点と後続条件は[受入れ状況](docs/acceptance.md#aws準備の到達点2026-11-07)・[公開前の残作業](docs/production-readiness.md#abc統合後のaws準備2026-11-07)を参照してください。[Cの検証結果](docs/aws-c-verification-results.md)には対象commit・ローカル試験・既知の制限を記録しています。Issue #66で[C04の観測契約・照合処理とC02 Origin対照](docs/aws-c-boundary-contract.md)を補強しました。実AWSの検証はaccount/role・予算・期間・対象操作を具体化して別承認した後に実施します。

## CIとマージ条件

GitHub Actionsの [CI workflow](.github/workflows/ci.yml) はmain向けPRとmainへのpushで実行します。

| Job | 確認するもの |
|---|---|
| backend | image build、Ruff、mypy、Django check、PostgreSQLへのmigration、migration差分、全pytest |
| frontend | image build、workflow配線/集約の負例、ESLint、TypeScript、全Vitest、本番build |
| ci-required | backend/frontendが両方successの場合だけ成功 |

PRのChecksで結果と失敗stepのlogを確認してください。失敗・中断・skipは集約の成功にはしません。依存解決は既存lockfile、base imageはdigest、checkoutは完全commit SHAで固定しています。hosted runner image・Docker/Compose版・BuildKitのsyntax frontendは固定しておらず、実runの環境と結果も確認します。

mainの保護は、CI導入PRで初回runと発行元を確認した後にRepository rulesetを設定します。PR必須、最新main、GitHub Actions由来のci-required、bypassなし、削除/force push禁止を対象とします。実設定の適用結果は導入PRへ記録し、workflowがあるだけで保護済みとは扱いません。mergeの担当は下の「個人開発環境」の節に従います。

workflowと検査scriptもPR側で変更できるため、CIのgreenは差分レビューの代わりにはなりません。CI（`.github/workflows/`・`.github/ci/`）、ゲート制御面（`.ai-dev-helm.json`の`gate.controlPlane`に当たるファイル）、または宣言自身を変えるPRは、常にmerge前で止めます。検出・X2のOK後の続行は[個人運用のマージ手順](documents/development/personal-workflow.md#承認と自律実行)に従います。CIの判定は `compose.yaml` や `package.json` のscriptsなどからも変えられるため、この例外ですべての変更が止まるわけではありません。設定検査器は誤編集を検出する回帰ガードであり、悪意ある同時改変を防ぐ境界ではありません。

CIは機械チェックによるmerge条件です。独立AIレビュー・mutation・目視検証はハーネス側に残し、CIへLLM判定を組み込みません。テスト失敗は原因を調査して修正し、rerunを繰り返してgreenへ寄せません。明確なインフラ障害だけ、理由とrunへのリンクを記録して同一SHAを手動で1回再実行できます。

## ローカル検証

主要操作のブラウザ検証は[FL-10A設計](docs/fl-10a-design.md)と[実行結果](docs/fl-10a-results.md)、固定負荷の実測は[FL-10B結果](docs/fl-10b-local-results.md)を参照してください。ローカルでの検証とAWS上の実証・撮影・環境破棄は別に扱います。[受け入れ条件](docs/acceptance.md)の全項目が合格したことは意味しません。

[.ai-dev/project.toml](.ai-dev/project.toml) に実行可能な11チェックを登録しています。Composeのbackend/frontend build、lint/型、Django check、migrate/差分確認、backend/frontend全テスト、本番buildです。CIでも同じコマンドと基準を使います（image buildのみ各jobに分割）。

[集約script](.github/ci/required-status.sh)の固定16組と不正入力は `bash .github/ci/test-required-status.sh` で確認できます。workflowのneeds/always/result入力と既存11チェックの対応も、固定frontend依存の検証imageで確認します。YAMLの読取りには現在のESLint依存に含まれるjs-yamlを使います。依存更新で解決できなくなれば検査は失敗し、CIを成功扱いしません。検査器自身を呼ぶstepの削除は検査器だけでは防げないため、workflow差分のレビュー対象です。

CI相当をローカルで再現するときは、既存fitlog-devと別のCompose project・image tagを使い、既存DB/画像volumeやimage IDを保護してください。詳細は[個人開発運用](documents/development/personal-workflow.md)を参照してください。

## 個人開発環境

- [個人開発運用](documents/development/personal-workflow.md)
- [手動相互レビュー（レビューAI向け手順）](documents/development/cross-review.md)
- [並列開発運用](documents/development/personal-parallel-workflow.md)
- [task plan](docs/task-plan.md)
- [初期セットアップ記録](documents/setup/harness-setup.md)

個人アカウントは `koma236`。個人Codex環境 `~/.codex-personal` と個人Git/GitHub接続を使います。[個人運用](documents/development/personal-workflow.md)を正とします。

仕様・独立設計レビュー・短い計画を最初に一括承認し、範囲内のIssue作成・実装・検証・修正・commit・feature push・PR作成・mergeまで委任します。工程ごとの承認は不要です。mergeは原則AIが行い、ユーザーが作業ごとに明示した場合、設計との差異がある場合、およびCI・ゲート制御面・宣言自身を変えるPRはmerge前で止めます。高リスクPRは実装していない側のproviderによる手動相互レビューを待って停止します。対象と再開条件は[個人運用](documents/development/personal-workflow.md#高リスクprの手動相互レビュー)に従います。
11 checksは[実行手順](documents/development/run-checks.md)に従い `python3 -B scripts/run-checks.py` で実行します。排他・必要時のDB起動・migration記録・後始末を含み、対象commit・run-id・check id・終了コードを親が品質報告とPRへ残します。
