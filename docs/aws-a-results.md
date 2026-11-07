# AWS A 実装・品質記録

最終更新2026-11-07。Issue #58。branch `feat/aws-foundation-58`、baseline `4524ec2965f6ac46815815555942bd4deda87058`。
設計レビュー反映版はユーザーの「承認します」で承認済み。[設計](aws-a-foundation-design.md)・[運用手順](aws-a-operations.md)。

実装: local backend宣言、providerなしのstate分離fixture、readinessの任意scenario検査、A所有文書。B/C所有・CI・ゲート・Compose・lock・migration・製品認証認可は変更しない。
実AWS API/送信/公開/破棄・実AWS E2E/撮影/性能・請求確認はnot_run。開発承認は実操作承認ではない。

## 機械検証

登録11 checks run: `20261107T073005Z-2de5a2b846d24eb1abf8c6b5ea7e9f87`。UTC 2026-11-07 07:30:05〜07:33:11。実行HEADは上記baseline、対象snapshotのpath/SHA256を同runの`snapshot-before.json`に保存。実行前後で対象内容が不変であることを確認した。

| check ID | exit |
|---|---:|
| compose-build | 0 |
| backend-lint | 0 |
| backend-types | 0 |
| django-check | 0 |
| backend-migrate | 0 |
| migration-drift | 0 |
| backend-tests | 0 |
| frontend-lint | 0 |
| frontend-types | 0 |
| frontend-tests | 0 |
| frontend-build | 0 |

backend 643件、frontend 190件。migration前/直前/直後/finalのgraph・適用記録を採取し未知node/不整合なし。今回起動DBの停止・残存container確認・runtime lock返却成功。実ログ/登録argv/cwd/env/終了時刻はローカル`.quality-check-runs/<run>/results.json`と各logへ保存。

同run後の差分は、prebillingの追加負例/新規backend隔離graphテスト・import整形・文書/記録だけ。製品コード・Compose・依存・checks登録の差分なし。影響するprebilling/Terraform Python/ruffを再実行し、製品11 checksを別snapshotの実行結果へ付け替えていない。

| 検証 | 結果 |
|---|---|
| prebilling unittest | 16件pass（初回RED: scenario API/引数未実装、TZ回帰RED→GREENを確認） |
| deployment既存標準unittest | 30件pass |
| Terraform既存共通入口 | fmt/init lock readonly/validate、Python4件、mock45件、Function3件pass |
| gate回帰 | Node54件pass |
| 追加Python静的検査 | backend lock同版ruff0.17.3を一時folderに取得、変更4ファイルのE4/E7/E9/F/I/B/UP pass。本番依存/lock変更なし |
| diff空白検査 | pass |
| hook信頼診断 | 個人CODEX_HOMEのcodex-trust Result ok。設計時の診断未完了とは別の実行 |

Terraform初回は明示backendに対する既存graph試験の初期化要求で失敗。資源定義をそのまま隔離コピーし、backend宣言とbackend metadataを除いてschema/依存グラフだけを検査するよう修正。backendの保存先は別のproviderなしfixtureで検証し、共通入口を再実行してpassを確認した。CI script/ゲートは変更していない。

## 独立品質レビュー・追加テスト

通常quality-check第1巡は統合・反証QA・Security（全員gpt-6-astra/high）で実施。統合/QAが同一のHigh 1件を検出、Medium 0件、Security追加指摘なし。`datetime.fromisoformat`が不正offset `+00:60/+00:99`等を正規化して通す問題に対し、変換前のoffset形式/範囲検査と負例・Z正例を追加した。回帰REDで5失敗を確認後に修正し、関連静的/単体検証を再実行。第2巡の検証担当・反証QA（gpt-6-astra/high）が解消確認、新規High/Mediumなし。製品認証認可やIAM policyの実装変更はない。

第1巡marker `5a6a82956cbadca48747de75b0bd51f8`、第2巡marker `e913745e4e0b2193548ea28364c45433`。全roleのused/receipt/agent登録を確認。品質予算2/2巡を使用し、追加レビューなし。
第1巡QAはFraction独立oracle1,000件、Securityは正常+4負例を確認。第2巡は検証担当がoffset20,000通り・各期限への136負例、QAが20,220件の独立probeで不正offset、Unicode/末尾改行/二重offset、±23:59/Z、期限±1μsとoverflow無害化を確認した。これはAWS試験や製品E2Eの実施を意味しない。
mutationは設定ツール未導入のためnot_configured。E2EはUI/製品導線/AI処理の差分なしでnone・not_proposed。実AWS試験は別承認とB/Cの工程に残す。既存台帳の状態変更はない。

## 設計との差異

なし。

## Issue #67：調査・実操作の承認案整備

2026-11-07。branch `docs/aws-execution-approval-67`、baseline `08fc88361143b4dd7915e69474d3b055b597b104`。ユーザー「進めて良いです。」による文書整備の設計承認。独立設計レビューはSol/high 1体、High0/Medium2。A/C leaseのfreeze・一時返却と、B seed/C利用者の総数量・利用者残置を明記して承認へ提示した。

[調査・実操作承認案](aws-execution-approval-draft.md)を新設し、調査action/数量・期間、2環境の成果物対応/公開/閉鎖/破棄、PassRole、fixture、残存/後日請求、指定待ち一覧を集約した。既存A手順/申請様式/readinessから参照し、費用表に公開単価の再取得hashと未算入項目の配賦表を追加。実行コード/manifest schema/CI/ゲート/製品設定は変更していない。

| 検証 | #67の実施結果 |
|---|---|
| prebilling既定 / 架空scenario | exit0 / exit0。scenario計算値1.90 USD、AWS not_run/未承認/未決を維持 |
| prebilling unittest | 16件pass |
| gate回帰 | Node64件pass、fail/skip0。既存Node54件の記録は過去runのまま保持 |
| 公開Price List | 7サービスの既存SKU/region/単位/USDを再取得し一致。TLS検証付きcurl、資格/API不使用 |
| 文書差分/リンク | diff空白検査とローカル参照先存在検査。品質対象の最終snapshotはPRの検証記録へ保存 |
| 登録11checks | not_run / docs領域のため対象外。DB/Compose/image/portを使用しない |
| mutation / E2E | out_of_scope / none・not_proposed。実AWS試験はnot_run |

ローカル検証記録は `/private/tmp/fitlog-67-quality/`、料金原本と抽出hashは `/private/tmp/fitlog-67-pricing/`。初回batchは全5コマンドexit0だが、実行中の文書リンク訂正1件でsnapshot不一致となりbatch終了1。成功snapshotへ付け替えず記録を保持し、最終文書の差分/リンク検査と前後snapshot照合を別途行う。既存テスト・ゲートの実行コードは変更していない。

独立品質レビュー・指摘・最終対象commitとsnapshotはPR本文とローカル品質レポートに記録する。#66の正式契約が未取得のため最終照合は未完で、依存未解決のままmerge/Issue完了とはしない。account/role/USD上限/実日時/保管・削除・請求担当は指定待ち。実AWS読取り/構築/送信/公開/破棄/請求照会は未承認・not_run。


## #66統合後の契約最終照合（2026-11-08）

ユーザー「66終わりました。照合してください。」により再開。PR #69はhead `62b813bdad611726ce3c549bf5f55dbba85b0237`、統合commit `aadcf26a1d317f3baca3ac3cf1eb50b4681ccbb4` でMERGED、Issue #66 CLOSEDを確認し、#67 featureへ通常取込みした。上の「#66未取得/最終照合未完」は初回PR作成時点の履歴とする。

| 照合元 | byte SHA256 |
|---|---|
| `docs/aws-c-boundary-contract.md` | `28c3a5541ad2ba13e10534a371d834bc7a4f5883dc22430376f23a7db6b9d468` |
| `e2e/aws_boundary.py` | `66f9042b02e16f4b8eac97b38654a9555093f6c949720160e01492e813867db2` |
| `e2e/support/aws-oracles.mjs` | `2c78ddb6cbdd2f8734fded68657b8e43766fd5b4e59c5b48b013fa518fbe8073` |
| `terraform/functions/client-ip.js` | `d0422a69e40ff3a474ed62c04fedb7cd3bb45c393668e8ade20a0c5771418709` |

C04は1環境9要求（ALB2/task1/S3匿名2/CloudFront4）、各response16KiB以下、timeout5秒、redirect/retryなし。C02は8要求を既存C予算で消費し追加user/post/imageなし。receipt v2/9 identity/inventory/全SG/OAC/既知object原本、health実15byte/hash、Function公開code、BのIP baseline/after・parameters hash、原本の前後再照合を確認した。C04のAPI/fixture/時間/費用はA追加枠へ切り出し、環境あたりobject2点・対照distribution/OAC各1・API200要求以内（片付け50確保）・観測10分以内の提案と許可action/残存担当欄を追記。未承認のまま実行できる値にはしない。

契約/実装の受領と申請案への反映は完了。実account/role/予算/日時/実資源/実AWS原本/R/E承認は未確定で実行不可。#69のC02復元失敗時marker残置、media実在のA原本依存、古いtask IP正常対照不足、原本消失〜停止/lock返却の結合テスト不足、C結果文書の一部旧状態は既知事項として引継ぐ。#67の既知Medium（RDS管理masterと通常secretの生命周期混在）は未修正でPRへ保持する。C所有実装/共通受入れ文書は編集していない。

照合後の再検証・独立品質結果・対象snapshot/commitとCIはPR #68とローカル品質報告を正とする。実AWSはread APIを含めnot_run、実受入れの成功は主張しない。設計との差異なし。

再検証: prebilling既定/scenario各exit0、prebilling16件、AWS Python34件、Origin/Oracle Node8件、ゲートNode64件pass。実行前後snapshot一致、登録11checksはdocs差分のため対象外/not_run。以後の変更はfixture削除をC全client停止・lease返却後とする文書明確化と本結果追記だけで、最終文書diff/link/前後hashを別途検査する。
