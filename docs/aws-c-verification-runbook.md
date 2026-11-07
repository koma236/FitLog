# AWS C 検証harnessの利用手順

関連: Issue #60、[承認済み設計](aws-c-verification-design.md)。最終更新2026-11-07。
ローカルharness実装の手順。実AWS操作・公開・撮影・性能の許可や合格証拠ではない。

## 入口と再利用

`e2e/aws-runtime.py`は既定がオフライン契約検査。AWS資格やSDKを読み込まず、`--execute-aws`を明示しない限りclientを生成しない。既存`runtime.py`・ローカルE2Eの11run履歴は独立して維持する。
AWS専用Playwright設定は既存journeyを共用し、origin・成果物folder・通信予算を注入する。CはCompose/DB/サービスの起動・migration・AWS構成変更を行わない。A/Bの基盤/配置/remote verifyを再実装しない。

```sh
npm --prefix e2e ci --ignore-scripts --no-audit --no-fund
npm --prefix e2e run typecheck
npm --prefix e2e run test:harness
npm --prefix e2e run test:runtime
python3 -B -m unittest perf.test_aws_report
```

共有runtimeが空いている場合だけ、runnerが共通lockを取得して次の制御fixtureを実行する。15173/18080の既存listenerや他担当のlockを停止/削除しない。

```sh
npm --prefix e2e run test:network-guard
npm --prefix e2e run test:aws-guard
npm --prefix e2e run test:recovery
```

AWS guard fixtureは専用一時CA証明書・ローカルTLS listener・接続先をローカル固定するCONNECT fixtureを使う。Chromiumだけfixture証明書のSPKIを指定し、Nodeは専用CAを信頼する。製品AWSモードはこのproxy/証明書pinを使用せずTLS検証を維持する。fixture成功は実AWSのTLS/IAM/公開境界の証拠ではない。
回復fixtureのfrontend依存準備は既存[FL-10A設計](fl-10a-design.md)の手順を使う。製品利用者や旧E2E試行回数は増やさない。

## C契約 v1（入力は非秘密）

repo外の実行者所有0700 folderに0600（読取り用0400可）のJSONを置く。正規絶対path・非symlink・通常fileを要求し、親を含むpathのsymlink解決差を拒否する。未知/重複key・欠損・期限外を拒否し、エラーに入力本文は出さない。

| key | 内容 |
|---|---|
| schema_version | 整数1 |
| account / region / environment | 12桁account / ap-northeast-1 / 承認済み環境名 |
| run_id / bootstrap_id / campaign_id | canonical UUID。前2つはA/B deployment、campaignは2環境共通 |
| test_run | 新規12桁hex試行ID。既存local台帳と独立 |
| source / image_digest / frontend_sha256 | clean source完全OID / sha256:付きdigest / static inventory hash |
| origin | `https://<distribution>.cloudfront.net`だけ。userinfo/path/明示port/query/fragment不可 |
| starts_at / expires_at | UTC `YYYY-MM-DDTHH:MM:SSZ`。現在を含む5分超〜45分以内の窓。末尾5分は終了用に確保 |
| approval | reference、steps=`[journey,capture,performance,cleanup]`、正のbudget_usd文字列。実承認の照合はoperatorの責任 |
| lease_id | Aから引き渡された操作窓識別子 |
| handoff | Bの`handoff.py`出力のpathとファイル全体SHA256。C用の成功サマリへ転記しない |
| evidence | 下記のA公開境界証跡参照配列。開始時は空でもよい |

B handoffの`ready_for_c`、account/region/environment/run/bootstrap/source_revision/image_digest/frontend_sha256/origin/windowを照合する。Bの`evidence`各pathは元のschema v2工程証跡を読み、Bのcanonical JSON hash・run/source/digest/static・同じdeployment_identity・status/stepを照合する。必須10工程はBの引継ぎ設計と同じ。Bのstate/manifest本文や秘密は読まない。
まだB未統合なら、Cのfixture契約を検証済みとだけ報告し、B統合済み/実配置成功とは扱わない。Bのschemaが変わったらadapterと固定fixtureを照合し、同snapshotで再検証する。

公開境界のC参照`evidence`は`{probe_id,path,sha256}`。probe_idは`alb-normal/alb-host/task/s3-static/s3-media/other-distribution/viewer-headers`だけ。各fileはC契約のaccount/region/environment/run_id/bootstrap_id/source/image_digest/frontend_sha256/originとprobe_id/status=passのみを持つAの非秘密結果。対象・期待拒否・既知fixture・元の実行記録の意味はAの実操作台帳と照合し、CのファイルだけでAWS拒否を証明したとは呼ばない。未提供ならnot_run。
B permissions/IPがnot_runでもCは開始できる。最終集約にはBの両probe成功とAの全公開境界証跡を要求する。

オフライン検査（AWS未接続）:

```sh
python3 -B e2e/aws-runtime.py --contract /protected/c-contract.json
```

## 後日の実操作に必要な準備

本節の実行にはaccount/operator/対象・金額・実日時・初回/再構築・要求/データ/回数/退避を列挙した別承認が必要。上の開発承認では実行しない。
A/Bが基盤/配置を完了し、AがCへ環境と操作窓を引き渡す。CとAの検証要求も重ねない。permissions/IPの一時返却はA/Bの窓調整と同窓認証枠を確認して手動調整し、不明なら停止する。

campaign folderはrepo外で正規path・実行者所有0700とする。初回/再構築の環境名とcampaign UUIDをAの台帳へ固定し、初回のみ`--campaign <folder> --init-campaign <初回名> <再構築名>`をオフライン契約検査へ追加して初期化する。既存campaignを上書きせず、別pathによる回数リセットを禁止する。
実行時だけ同じ入口に`--campaign <folder> --execute-aws`を追加する。clean sourceが契約の完全OIDに一致しない、共通runtime lockが他担当使用中、期限/証跡が不正なら接続前に拒否する。環境ごとのattempt intentを排他作成した後にclientを起動し、中断/失敗でも1回を消費する。rebuildは初回intentが存在する別環境で1回だけ。
1環境で2利用者/6投稿/4comment/保存画像4点・各64KiB以下、要求3000（通常2800＋cleanup200）/送信20MiB/auth24回・rolling60秒8回。正常画像は既存小型fixture、負例は既存5MiB+1のUI拒否であり実送信を強制しない。
cleanup開始後も期限・総要求/送信/auth上限を緩めない。失われたsessionの自動再loginはせず、未回収の自己所有IDと利用者2名を残置としてAへ引き渡す。環境削除はAだけが行う。

## 結果と停止

campaign/run folderに契約参照、予算、resource-budget、journey/cleanup、C01〜C06、performance-requests/集計、safe reporter、runtime、quarantine動画を保存する。Cookie/password/CSRF/storageStateはメモリのみ、trace/HAR/生HTTP/DOM/例外dumpは保存しない。
限定性能は2利用者でGETのみ、10秒warmupを除く90秒180枠・3分類各60。既存`perf.report.summarize`を使い各分類p95<1000ms、失敗/欠測0を要求する。撮影失敗はfailを保持し性能を見送り、前提が健全なら削除検証を続ける。
`runtime.status=pass`は観測したブラウザ操作/限定性能/動画decodeとclient停止の成功である。`acceptance`、視認、破棄後再生、再構築、Aの残存/後日請求は別状態で、現実装では自動passにしない。C04がnot_runなら受入れ未完了。C07の2環境完了はAの記録とともに人間が確認して文書化する。
全child group停止を確認してからlocal lockと試験leaseを返す。停止不明はlock保持・lease未返却。CはCloudFront無効化やECS停止を行わずAに引き渡す。動画は視認・秘密混入検査前に共有せず、破棄後もAWS外で再生確認する。
