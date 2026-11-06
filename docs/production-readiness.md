# FL-09A 本番起動・S3保存の契約

Issue #28。アプリ側の本番用部品を用意する段階。AWS資源、実RDS/S3、IAM、公開経路を検証した状態ではない。通常の開発Compose・API・画像token・DB schemaは維持する。

## 起動と必須設定

`backend/Dockerfile.production` は固定digestのPython/uv、lock済みruntime依存のみ、非rootで起動する。`DJANGO_SETTINGS_MODULE=config.production` と `FITLOG_ENV=production` をimageに設定し、Gunicornを8000番で起動する。起動時のmigration・seed・AWS操作はしない。秘密はimage/build引数へ入れず、配置側から注入する。

| 設定 | 条件 |
|---|---|
| DJANGO_SECRET_KEY | 50文字以上、公開sample不可 |
| AUTH_RATE_LIMIT_HMAC_KEY | 32文字以上、公開sample不可、SECRETと別の値 |
| FITLOG_PUBLIC_HOST | 単一CloudFront DNS名。scheme/path/wildcard不可 |
| PRIVATE_MEDIA_BUCKET | general-purpose非公開bucket、英小文字/数字/ハイフン3–63字 |
| PRIVATE_MEDIA_EXPECTED_OWNER | 12桁の期待AWS account ID |
| AWS_REGION | ap-northeast-1固定 |
| POSTGRES_HOST / DB / USER / PASSWORD | すべて必須。DB/USERはそれぞれPOSTGRES_DB/POSTGRES_USER |
| POSTGRES_SSLROOTCERT | container内の読取り可能な有効CA bundle。配置時にRDS用CAを検証する |
| FITLOG_TRUST_PROXY | 0が既定。1のみ下記専用headerを信頼 |
| FITLOG_AUTH_CLIENT_IP_SOURCE | remote_addrが既定。cloudfrontはproductionかつFITLOG_TRUST_PROXY=1の場合だけ許可 |

productionはDEBUG=False、DBは`sslmode=verify-full`・connect timeout5秒。設定の不備は値を表示せず拒否する。base moduleを使うローカル開発は従来どおり。storage factory/apps.ready/system checkは(local,local)/(production,s3)だけを許す。production moduleのbackend既定はs3で、明示した別backendも拒否する。

Secure/HttpOnly/SameSite cookieとHTTPSのCSRF originを使う。Gunicornのforwarded header信頼は無効。Djangoのproxy信頼も既定offで、opt-in時だけ`X-Fitlog-Forwarded-Proto: https`を使う。SSL redirectはFalse、HSTSはopt-in時だけ3600秒。公開時にはproxy側でHTTPSを強制し、このheaderを必ず上書きする。proxy以外から到達できない物理境界の実証が必要。

productionのGET/HEAD `/api/health/live`完全一致だけはIP形式のHostでもDBなしで応答する。ready、他API、類似prefix、他methodは通常のHost検査を行う。ready成功はDB到達と未適用migrationなしを条件とし、S3の疎通を示さない。

## 不変画像と障害

`PrivateStorage`の5操作をfactoryで選び、upload/content/cleanupのすべてが同じ入口を使う。localではSDK clientも資格情報探索も開始しない。S3はIAM roleのSDK credential chainを想定し、アプリ専用の静的access key設定を追加しない。独自endpoint環境変数はSDK設定で無効化する。

S3 objectは`images/<32桁hex>.(jpg|png)`だけ。全requestへExpectedBucketOwner、PutへSSE-S3/AES256とIfNoneMatch=*を指定する。送信前に5MiB上限とSHA256を検査。412は既存objectの実bytesが同digestの場合だけ成功。409は条件付きPutを1回だけ再試行。timeout/5xx等で結果不明ならGetで同digestを確認できた場合だけ成功し、確認不能・異digestは503にする。ETagだけで成功扱いしない。

Getは64KiB以下のchunk、MAX+1上限、ContentLength・SDK checksumをEOFまで検証し、成功/失敗ともstreamをcloseする。NoSuchKeyのみ404、認証/権限/SDK障害は503。Deleteは欠落再送を成功とする。SDKはconnect2秒/read4秒/total attempts1、streamはmonotonic経過4秒を監視する。409再試行・照合・on_commit清掃を含む設定上の待機予算32秒はGunicorn timeout60秒より小さい。ただしDB lock、client upload、各socket全区間を含む厳密な壁時計上限ではない。worker強制終了時も常に503を返せる保証はなく、既存pending operation・rollback・orphan清掃で回復する。同じoperationを再開し、新IDで無制限再送しない。

ListはMaxKeys<=1000、images/のPrefixとexclusive StartAfterでkey順に走査し、truncated時の最後のkeyをcursorへ保存する。prefix外/不正key/順序/時刻/空truncated pageは503で停止し、cursorを進めない。multipartやversioningは使わず、temporary sweepは外部呼出しなしで0件。既存DBのattached判定・所有権・1時間猶予は保持する。

`maintenance_failed`が継続するときは所有者が設定・IAM・bucketとprefix内のobjectを確認する。不正keyの自動削除やscan checkpointの手編集はしない。必要な退避/除去は対象と影響を確認する別操作とし、修復後に通常のcleanup_imagesを再実行する。

## ログとローカル検証

Gunicornのaccess logは無効。error logも既存SafeFormatterへ通し、固定`server_info`/`server_warning`/`server_error`/`server_critical`とseverity、timestamp、request_id=null、検証済みapp_versionだけを記録する。元message/URI/args/tracebackは捨てる。既存api/maintenance eventは維持する。原因調査にはseverityと発生時刻・health/maintenanceの固定eventを使い、rawログを有効化してtokenを残さない。

共通runtime leaseを取得してから、登録11 checksを`.ai-dev/project.toml`のargvで実行する。backend/testsは実PostgreSQLとSDKの署名/parse/HTTP境界を使い、dummy資格情報と外部送信前の応答注入でAWSアクセスを防ぐ。

```sh
docker build --platform linux/amd64 --file backend/Dockerfile.production --tag fitlog-fl09b4-production-44 .
python3 backend/tests/production_smoke.py
```

smokeはnetwork=none・host port非公開の専用containerで、実アプリの起動/非root/check/cleanup help/live/Host/SIGTERMを確認する。別のtest-only WSGI fixtureでGunicorn自身の例外と不正requestを起こし、stdout/stderrの非漏洩を確認する。fixtureはproduction imageから除外し、試験時だけread-only mountする。今回作成したcontainerだけをfinallyで停止・削除する。system CAによる構文検査はRDS用CA/実接続の検証を代替しない。

## FL-09B1：認証の利用者IP（Issue #30、2026-11-04）

signup/loginのIP選択は既定の直接接続元を維持する。`FITLOG_AUTH_CLIENT_IP_SOURCE=cloudfront` の明示設定時だけ `X-Fitlog-Client-IP` を使用する。不正・欠落ヘッダは503で拒否し、接続元やX-Forwarded-Forへのfallbackはしない。10回/60秒の固定窓、IPv4 /32・IPv6 /64・mapped IPv6の正規化とHMAC保存は既存どおり。[認証契約](api/auth-implementation.md)参照。

`terraform/functions/client-ip.js` はviewer-requestで `event.viewer.ip` から専用headerのフィールド全体を上書きし、利用者のvalue/multiValueを残さない。ローカルtestは `node --test terraform/functions/client-ip.test.cjs`。Functionのpublish/関連付けや実AWS経路は未実施。

有効化には後続IaCと実AWSで、自distributionのAPI behavior全体へのFunction関連付け、専用headerのorigin転送、APIキャッシュ無効、CloudFront origin-facing prefix list＋秘密origin headerのALB制限、ALBのみを許すtask SG、HTTPS強制と専用proto header上書きを検証する。別distribution・ALB/task直接経由での偽装拒否も確認する。単にヘッダが存在することを信頼境界の実証にしない。

## FL-09B：公開前に必要な実証

FL-09B2（Issue #32）で専用VPC・閉じたSG・非公開S3/ECR・task/execution IAM・logsのTerraform定義を追加した。[検証と制限](../terraform/README.md)参照。ローカルmock planの構成検証であり、実資源・IAM評価・疎通は未実施。FL-09B3（Issue #42）でCloudFront/ALB/OACの公開入口定義を追加した（公開既定false、target group空）。APIは両behaviorのFunction/全viewer転送/TTL0、staticはdistribution限定OAC読取り。CloudFront→ALB/taskはHTTPという短期デモ向けの境界であり全区間TLSではない。ECS/RDS、CA/秘密の注入、配置/seed、TerraformのCI組込みと費用・対象・期間の承認を済ませてから実AWS操作へ進む。[承認設計](fl-09b3-edge-design.md)参照。

FL-09B4（Issue #44）で[ECS/RDS・秘密参照・公開CAの構成定義](fl-09b4-runtime-design.md)を追加した。Fargateは既定0 task、非公開RDSは削除保護/final snapshot、アプリ用secretは本体だけで値未投入。管理secretをWeb task/executionへ許可しない。専用CAをimageへ同梱し、ローカル実PostgreSQLでverify-fullのCA/SAN正負例を検証する。実RDSのCA/接続、非管理者DB roleの初期化、秘密投入、実配置/seed/公開境界、Terraform CI組込み、費用/期限は後続。publicフラグはservice/proxyの明示有効化を要求するが、フラグやmock合格だけを経路実証としない。RDS snapshot/保持backupと7日削除待ちsecretの残存費用・再構築時の名前衝突も破棄手順へ含める。

- AWS/IaC/課金・対象・期限の具体化と承認、IAM role、ListBucketを含む最小権限、bucket policy/期待owner、実S3障害・RDS CAとverify-full接続。
- CloudFrontのHost転送、HTTPS強制、専用headerの上書き、origin認証、proxyのみから到達するSG/経路。実ALBのhealthを確認。
- 利用者IPの信頼経路とsignup/loginの実機レート制限。FL-09B1のFunction/アプリ契約だけでは実証未完了。既定REMOTE_ADDRのままALB配下で枠を共有する状態では公開しない。
- sync worker2での低速upload・画像配信・同時利用時の受信期限/接続数/memory/livenessと、worker終了・結果不明からの回復。

SDK設定の原典: [botocore Config](https://docs.aws.amazon.com/botocore/latest/reference/config.html)。実AWSを使う検証は今回の成功へ含めない。


## 依存のセキュリティ更新

本番依存の照合で、既存DRF 3.16.1の公開High（GHSA-33wh-fxxf-88vvなど）を検出したため、DRFだけを3.18.3へ更新した。他の既存packageの一括更新は行わない。healthのAccept処理も到達するため、FL-09Bへ修正を先送りしない。12KBの過大Accept tokenは406、上限内のJSON指定は200になることと既存API全件を検査する。型stubは既存版のままstrict検査する。
原典: [DRF 3.18.3 security release](https://github.com/encode/django-rest-framework/releases/tag/3.18.3)、[Accept処理のadvisory](https://github.com/encode/django-rest-framework/security/advisories/GHSA-33wh-fxxf-88vv)。

## Terraform CI（FL-09B5 / Issue #46）

PR/mainのTerraform jobは資格情報を渡さず、既存mock/plan・依存グラフ・入力負例・Function testを検証する。backend/frontend/terraformすべてのsuccessをci-requiredで必須化する。[共通入口と実行契約](../terraform/README.md#ciと共通入口fl-09b5)参照。mock/CI成功は実RDS/S3/IAM/公開経路や課金停止の実証を代替しない。実AWSの操作・秘密投入・DB初期化は後続の承認範囲。
