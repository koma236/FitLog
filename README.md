# FitLog

筋トレ記録・プロフィール・画像・コメント・いいねを扱う個人開発プロジェクトです。React/TypeScript、Python/Django、PostgreSQLをDockerで実行します。

## CIとマージ条件

GitHub Actionsの [CI workflow](.github/workflows/ci.yml) はmain向けPRとmainへのpushで実行します。

| Job | 確認するもの |
|---|---|
| backend | image build、Ruff、mypy、Django check、PostgreSQLへのmigration、migration差分、全pytest |
| frontend | image build、workflow配線/集約の負例、ESLint、TypeScript、全Vitest、本番build |
| ci-required | backend/frontendが両方successの場合だけ成功 |

PRのChecksで結果と失敗stepのlogを確認してください。失敗・中断・skipは集約の成功にはしません。依存解決は既存lockfile、base imageはdigest、checkoutは完全commit SHAで固定しています。hosted runner image・Docker/Compose版・BuildKitのsyntax frontendは固定しておらず、実runの環境と結果も確認します。

mainの保護は、CI導入PRで初回runと発行元を確認した後にRepository rulesetを設定します。PR必須、最新main、GitHub Actions由来のci-required、bypassなし、削除/force push禁止を対象とします。実設定の適用結果は導入PRへ記録し、workflowがあるだけで保護済みとは扱いません。mergeは本人がGitHubで行います。

workflowと検査scriptもPR側で変更できるため、CIのgreenは差分レビューの代わりにはなりません。とくに `.github/workflows/`・`.github/ci/`・テストを変えるPRは、merge前に本人が差分を確認します。設定検査器は誤編集を検出する回帰ガードであり、悪意ある同時改変を防ぐ境界ではありません。

CIは機械チェックによるmerge条件です。独立AIレビュー・mutation・目視検証はハーネス側に残し、CIへLLM判定を組み込みません。テスト失敗は原因を調査して修正し、rerunを繰り返してgreenへ寄せません。明確なインフラ障害だけ、理由とrunへのリンクを記録して同一SHAを手動で1回再実行できます。

## ローカル検証

[.ai-dev/project.toml](.ai-dev/project.toml) に実行可能な11チェックを登録しています。Composeのbackend/frontend build、lint/型、Django check、migrate/差分確認、backend/frontend全テスト、本番buildです。CIでも同じコマンドと基準を使います（image buildのみ各jobに分割）。

[集約script](.github/ci/required-status.sh)の固定16組と不正入力は `bash .github/ci/test-required-status.sh` で確認できます。workflowのneeds/always/result入力と既存11チェックの対応も、固定frontend依存の検証imageで確認します。YAMLの読取りには現在のESLint依存に含まれるjs-yamlを使います。依存更新で解決できなくなれば検査は失敗し、CIを成功扱いしません。検査器自身を呼ぶstepの削除は検査器だけでは防げないため、workflow差分のレビュー対象です。

CI相当をローカルで再現するときは、既存fitlog-devと別のCompose project・image tagを使い、既存DB/画像volumeやimage IDを保護してください。詳細は[個人開発運用](documents/development/personal-workflow.md)を参照してください。

## 個人開発環境

- [個人開発運用](documents/development/personal-workflow.md)
- [task plan](docs/task-plan.md)
- [初期セットアップ記録](documents/setup/harness-setup.md)

個人アカウントは `koma236`、共通ハーネスは `~/project/ai-dev-harness`。iTerm2でこのrepoへ移動し`codex-me`を起動します。個人Codex環境`~/.codex-personal`と個人Git/GitHub設定を使い、既定の会社環境へ切り替えません。

仕様・計画・実装結果・独立レビュー結果は正規v9の4段階承認を維持します。Issue/PRは内容ごとの個別承認、commit/pushはユーザーの明示委任で個別確認不要です。正規v9のproposal・検証・操作記録は省きません。
