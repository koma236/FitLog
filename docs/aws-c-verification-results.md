# C #60 検証範囲と追加テスト判断

最終更新2026-11-07。[設計](aws-c-verification-design.md)・[利用手順](aws-c-verification-runbook.md)。

## 現在の到達点

A/Bと先行PR #65をCへ取込み済み。対象commit `cf21655ddedc0ea4f98ac03b69819c5f92341c8e`で、コメント対応後run `20261107T105550Z-b83a3ce89cfa42ab84229ca64cf607c7`の登録11 checks全終了0（backend643/frontend190）、型・Python35・Node53・配置52・perf39・ゲート64件成功。clean source hash `55e34ee24954bdbbdb7e46eb243ecca8d647ff7390d9d0e63d6c6dddcb25815a`前後一致、自己所有DB停止・lock返却を確認した。B実handoff生成→C検証器の接続もオフライン確認済み。以下の古いrun/待機理由は経過記録であり、現在の依存状態は本節を正とする。

[相互レビュー](https://github.com/koma236/FitLog/pull/63#issuecomment-6705861432)は同head、High0/Medium2/Low3。コード照合と同head再検証後に待ち解除。MediumのC02対照条件の違い・性能枠遅延のテスト不足、Lowの固定lock path・RDS参照根拠表示・C01失敗共有は未修正としてPRに記録した。C02成功をOrigin単独拒否の証明とは扱わない。既存Mediumの性能失敗時JSON未保存・detail oracleの事前GET依存も保持する。

共通[受入れ文書](acceptance.md#aws準備の到達点2026-11-07)・[公開前条件](production-readiness.md#abc統合後のaws準備2026-11-07)・[README](../README.md#aws準備の現在地2026-11-07)を、実装/ローカル検証済み・実AWS未実施として更新した。今回の更新は結果の文書化のみで、実装・テスト内容は変更していない。C04の実観測証跡形式/照合処理、実AWS試験・動画・破棄/再構築・後日請求は後続。設計差異は設計文書の記録を保持し、品質フラグは未作成。mainへのマージ・実AWS接続は行わない。

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

追加のユーザー許可を受け、H4-R2の集約を修正した。処理本体・source一致・停止確認・lock返却を最終成功の必須条件とし、返却前はfailを保存してから、返却完了後にだけpassへ更新する。停止False/停止例外/owner不一致/source不一致/先行失敗の純粋テストを追加し、Falseを成功扱いする旧コードで失敗→修正後成功を確認した。追加確認1巡は規定CLIで記録し、その結果をPRへ反映する。今回の指示に従い、先行PR未完了の間はマージしない。

追加確認3巡目では、両レビュアーが停止False/例外の解消を確認した。一方QAは新規High H7を再現した。所有確認を複数回行い、結果がTrue→False→Trueなら、途中でOWNER_CHANGEDを記録しても最終statusがpass/終了0へ戻る。共有lockのowned()は一時的な読取り例外でもFalseを返すため、検知した不一致を失敗として固定する必要がある。追加1巡を消費したため修正は停止し、品質未完了・フラグなしを維持する。次の方針は所有確認結果を一度捕捉して判定と返却条件に共用し、返却処理自身の再照合失敗も失敗として保持すること。状態遷移と保存/返却例外の集約反証で確認する。

今回の修正時点で登録11 checksは全成功（run `20261107T083814Z-23a03618513646b9bfcd508da697c591`）、Python runtime33件成功。実行時HEAD `0923236ad043bc3672ceb488b48320409d34867e`と3ファイル差分のsource hash `f54f5597d524b39ee2d285bb81bd9410b49f9fec4d2f253bb2cdb8dd93adad59`は前後一致し、自己所有DB停止・lock返却を確認した。以後は結果文書の追記のみ。実AWSは未接続。

ユーザー「追加1順許可します。」に基づく4巡目では、H7を修正した。所有確認結果を一度捕捉し、合否・理由・返却条件で共用する。共有release自身の独立再照合は維持し、その失敗も成功へ戻さない。回帰テスト2件は旧コードで失敗、修正後はPython runtime35件成功。検証レビュアーと反証QAの双方がH7解消・新規Highなしを確認した。独立反証は実際の共有releaseを使用し、検証側2ケース、QA側66ケースが成功した。

最新登録11 checksは全終了0（run `20261107T085420Z-00354946e4284064811c9cb58f3bfe41`）。実行時HEAD `8648aac3451244bd3b7eed332e5786180b39679e`とruntime/test差分のsource hash `10c39b349376823bdaec52c3aa3112f03d003766b652a2034e2e743b3bee32af`は前後一致。自己所有DB停止とlock返却成功。以後の変更はこの結果文書への追記のみ。Medium2件は未修正で保持する。設計差異・B先行統合・C04実観測receipt・共通受入れ文書・手動相互レビューは引き続き保留のため品質フラグは未作成。ユーザー指示に従いマージせず、実AWSにも接続しない。
