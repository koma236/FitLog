# 本番秘密値・DBロールの初回初期化

Issue #48、[承認設計](fl-09b6-bootstrap-design.md)。コマンドとローカル検証を実装する工程であり、実AWS構築・投入・公開・実RDSの権限実証は未実施。

[承認済みの永続予約方式](fl-09b6-durable-claim-proposal.md)を適用する。秘密保存前に操作UUIDを予約し、別UUIDへの引継ぎを拒否する。

## 実行前条件

実AWS実行は対象account、資源、費用、期限、実行用IAM/VPC内runnerを具体化し承認してから行う。Webのtask/execution roleに管理者秘密の読取りや秘密書込みを追加しない。実行用roleはSTS本人確認、対象RDS/ECS/ELBv2/CloudFrontとtagsの読取り、対象application secretのDescribe/ListSecretVersionIds/GetSecretValue/PutSecretValue、RDS管理secretのGetSecretValueを必要とする。実行用role/IAMの作成は今回含めない。

runnerは非公開RDSへ到達でき、同梱CAを使ったverify-fullが成立する必要がある。SQL/監査ログがpassword/verifierを漏らさないことを実行前に確認する。CloudFrontの読取り応答にはorigin認証headerも含まれるため、実行者はこの値も読める。コマンドは応答を保存・出力しない。実行中の配置、service起動、秘密の別経路更新は禁止する。DB advisory lockは協調コマンドだけの排他であり外部操作を阻止しない。

## コマンド契約

backendをcwdにして `python -m operations.bootstrap --help` で確認できる。必須引数は以下の非秘密metadataだけ。

| 引数 | 値 |
|---|---|
| --expected-account-id | 期待する12桁account ID |
| --environment | Terraform environment_name |
| --db-instance-identifier | environmentと同じRDS identifier |
| --application-secret-arn | Terraform application_secret_arnの完全ARN |
| --distribution-id | Terraform distribution.id |
| --operation-id | 初回作業ごとに決めて記録するcanonical UUID。同じ作業の再開時は同じ値 |

既定はmetadata確認のみ（成功event `bootstrap_inspected`）。`--initialize` を明示した場合だけ管理secretを読み、DBとapplication secretを初期化する。初期化・再実行検証の成功eventは `bootstrap_verified`。失敗は固定 `bootstrap_failed` / exit 2。失敗内容、SQL、例外本文や秘密は出力しない。非秘密のoperation ID、終了code、実行時刻を作業記録へ残す。

regionは東京固定。cluster/service/container/ALB名は既存Terraform規則で導出し、別環境混在・稼働タスク・有効な公開distributionを拒否する。SDK endpointは公式commercial AWS endpointへ固定し、環境変数からの独自endpointへ転送しない。password/DSN/profile/任意SQLはCLI入力にしない。SDK標準credential chainの実行用roleを使う。秘密値をCLI、環境dump、build引数、Terraform、ファイル、チャットへ転記しない。

CloudFrontのglobal APIだけは署名scopeをus-east-1/cloudfrontとする。他の5clientはap-northeast-1で署名する。これはglobal APIの署名設定であり、配置先を東京以外へ変える設定ではない。

## 処理と復旧

1. 対象metadataと停止状態を照合。管理資格をメモリ内で読み、RDS正本の接続先へTLS接続する。
2. 同じ接続でsession advisory lockを取得。競合は変更なしで停止。接続切断後の自動再接続は行わない。
3. 初回だけsecret全versionなし、app roleなし、許可リスト以外のDB objectなしを確認。管理schemaのoperation_claimへ操作UUIDと対象metadataを先にcommitし、予約を保持する。
4. 独立した3値を生成し、UUID固定の初回AWSCURRENT versionとして保存・読み戻す。同UUIDの再開は保存値を再利用する。
5. role・ACL・完了markerを単一transactionで作成。別のapp接続でログインと権限を確認する。

| 状態 | 対応 |
|---|---|
| claim予約前に失敗 | 外部状態を調査し再実行。変更成否を推測しない |
| claimのみ残存/claim commit結果不明 | 現在の実行で秘密を書かず終了。新しい同UUID実行で対象・lock・予約を再検証する。別UUIDへ切り替えない |
| claimなし・secretだけ存在 | 不整合として停止。既存秘密を勝手に採用しない |
| secret保存後、DB未commit/rollback | 同UUIDで保存済みの同passwordを再利用してDB処理を再開 |
| secretまたはDB commitの成否が不明 | 固定エラーで停止。同UUIDで再読取りして照合。secret/roleを手作業で削除・上書きしない |
| 同UUID・marker/roleあり | 全権限・marker・秘密versionとapp実ログインを検証。変更なしで成功 |
| 異UUID/未知version/未知role/marker不一致/権限差異 | 停止して対象を調査。自動修復・rotation・dropは行わない |
| RDSに未知の初期object | 変更前停止。所有者/拡張依存を調べ、許可リストの設計変更へ回す。skipで進めない |

初回AWSCURRENT保存とDB作成は分散transactionにできない。secretだけの状態を完了扱いしない。Webの停止状態を変更直前にも照合する。元の作業UUIDを失った場合も、別UUIDで既存秘密を上書きせず作業記録とversion metadataから調査する。

## DBとimageの境界

fitlog DBはfitlog_admin所有。fitlog_appはCONNECT、publicのUSAGE/CREATEと自分がmigrationで作るobjectの所有権を持ち、SUPERUSER/CREATEDB/CREATEROLE/BYPASSRLS/REPLICATIONおよび管理role membershipを持たない。WebとmigrationはB4契約どおり同じapp role。PUBLICのfitlog DB/public schema権限は初回に剥奪。他DBのACLは変更しないためcluster全体の隔離とは呼ばない。

管理者所有 `_fitlog_bootstrap.operation_claim` は操作UUIDを永続予約し、`initialization` はrole/ACLと同じtransactionの完了markerとしてoperation・対象metadataだけを保存する。両table/列ともappからの読取り/変更を拒否する。Django migrationには追加しない。再実行はGRANT OPTION増加やmarker tableの追加grantも拒否する。

既存Dockerfileのbackend全体COPYで管理ツールもproduction imageへ同梱される。Webから実行せず、WebのIAM権限を増やさない。開発用SDK型スタブはTYPE_CHECKING内からのみ参照しproduction runtimeへ依存させない。

## ローカル検証

通常の登録11 checksに加え、共有runtime排他内で `backend/Dockerfile.production` から専用image `fitlog-fl09b6-production-48` をbuildし、`PYTHONPATH=backend python3 backend/tests/bootstrap_smoke.py` を実行する。固定PG17 image、専用internal network、host portなし、tmpfs DB、公開fixtureだけを使い、自分のlabel付きcontainer/networkをfinallyで除去する。共有開発DBへbootstrapしない。

非SUPERUSER fitlog_adminから初期化し、createrole_self_grantの既定とinherit,setの両方、TLSのCA/SAN正負例、rollback/再開、lock競合、危険操作拒否、ACL/marker差異拒否、appとして全Django migrationを確認する。RDS固有のrds_superuserや実IAM/経路/ログ方針はこの検証では実証できない。

実run経路でも、claimのみ、秘密保存後timeout、claim/完了commit後の応答喪失、最終ログイン失敗、lease喪失、遅延旧Putの両到着順、claimなしsecretの拒否をSDK境界応答注入＋専用DBで確認する。TLS fixture内のDB破棄/再作成は公開fixtureの専用DBだけを対象とする。

## B #59との接続（2026-11-07）

新しい配置入口では [B配置手順](aws-b-deployment-runbook.md) のartifact recordと同runのinspect/static成功を確認してから、既存bootstrap-inspect→bootstrapを実行する。初期化SQL・claim/lock/TLS・同一bootstrap UUIDでの再開契約は本書を維持する。実AWSの起動/収集/停止operatorはAのみ。B/Cが別経路で実行しない。実AWS未実施。
