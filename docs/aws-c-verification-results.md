# C #60 検証範囲と追加テスト判断

最終更新2026-11-07。[設計](aws-c-verification-design.md)・[利用手順](aws-c-verification-runbook.md)。

## ローカルで確認した範囲

Python契約/実行境界、NodeのURL/送信予算/性能枠/固定oracle、型、既存回復/撮影/guardの回帰を対象とする。正式な対象snapshot・check別終了コード・最新の品質判定はPRの検証欄と`.quality-check-runs/<run>/results.json` / source対応記録に残す。

| 制御browser実行 | 確認した事実 |
|---|---|
| `aws-fixture-f8f5960163dd` | 最初のHTTPS guard予行、禁止先0、許可先7、body188bytes、listener停止確認 |
| `network-fixture-017b90a07501` | Bが共有runtimeを使用中のため開始不可。operations空、テスト未実行。成功へ転記しない |
| `network-fixture-bb5ac4377b8b` | 既存ローカルguard回帰成功、lock返却 |
| `recovery-fixture-f6cc9f536066` | 既存実App読取りの回復/撮影制御fixture成功、lock返却 |
| `aws-fixture-4844e9e65853` | HTTPS/redirect/worker/WebSocket/API経路・実multipart bytes一致・body未完了の全体5秒timeout、禁止先0、listener停止確認 |

これらは製品への要求・利用者作成・実AWS接続なし。fixtureの自己署名証明書pinを本番TLS検証の実証と呼ばない。
登録11 checksの初回run `20261107T074546Z-f5b7649216aa477aa11e8a9c5b515860`は全11終了0、backend643件、DBの自己所有停止/lock返却成功。実行中source hash `8370290e9acb9a2ecf9191b8ccbca47baa3b8b0b589f2ecea03beabbe5a8d364`は前後一致。その後C03の保留表示・既存noteを保持するCSRF正例を追加したため、初回成功を最新snapshotの成功に読み替えない。

## 追加テストの判断（C所有の記録）

共有運用台帳はA/Bと同時編集せず、本Issueの判断をこのC文書と品質レポートへ記録する。

| 対象 | 推奨度・判断 |
|---|---|
| ミューテーション | Python/Nodeハーネスに適用する既存mutation構成なし。not_configured、未実施。新依存/CI配線は追加しない |
| 通信guard/回復browser fixture | strong。副作用なし・固定port/共通排他内、実行済み。実AWS/製品E2Eとは分離 |
| 旧ローカル製品E2E | 旧11run承認を増やさないため新たな実runは未実施。既存操作を共用し制御fixtureで回帰 |
| 実AWS E2E/撮影/性能 | 別の具体承認が必要なためadded_only/not_run。今回の開発承認を実行許可にしない |

## 未確認

A PR #61はCへ通常取込み済み。B→Cの先行統合、実account/期限/予算/公開fixture、RDS/S3/IAM/CloudFront実経路、実AWS E2E/動画/性能、初回/再構築、閉鎖/破棄/残存/後日請求は未確認。C03/C04や総合受入れを未実施のままpassにしない。共通acceptance/production-readiness/READMEはB先行統合後にCが更新する。CのPRを先行準備するがB依存未解消のままマージしない。

品質1巡目のHighは重複統合後6件（保存名、復旧origin、期限、browser group、先行失敗後撮影、C04成功要約）。正負テストで是正し確認巡へ渡す。C04は実観測receipt仕様が未成立のためnot_runに維持する。Medium 2件は未修正でPRへ記録する（性能閾値失敗時に集計JSONが残らない、性能detail本文oracleが事前GET由来）。
修正後fixture `aws-fixture-c791286be700`ではローカルHTTPSと実ファイル保存、期限取消、停止したChromiumをNode自己SIGKILL後に親が同じPID/PGID/起動時刻で特定・停止する反証が通った。実AWS接続/製品要求/利用者作成なし。

確認巡でHigh 1件が残った。`AwsDriver.stop_owned()`のFalseが`execute()`の最終passed/status/終了コードへ伝播せず、browser停止不明でもruntime.status=pass/終了0になる場合がある。lock/leaseは保持されるが、停止不明はfailという設計を満たしていない。High H4-R2として未対応、品質チェック未完了・フラグなし・マージ禁止とする。2巡上限かつH4再指摘のため追加コード修正/レビューはユーザー判断待ち。
次の修正方針は、exercise・source一致・全client停止確認を最終成功の必須条件へ一元化し、exercise成功＋stop_owned=Falseの集約を実行する純粋テストで、終了非0・status fail・lock保持を固定すること。確認巡追加の許可を得るまでは実施しない。
