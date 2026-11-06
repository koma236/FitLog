# FL-09B7 配置・実経路検証・撮影・破棄・再構築

Issue #52、[設計](fl-09b7-deployment-design.md)、[実AWS申請書](fl-09b7-aws-approval-template.md)。最終更新2026-11-06。
実AWS工程は未実施。以下は**申請書を具体化して別途承認後**に使う。ローカルCLIの`--aws-approved`は実承認を代替しない。

## ローカルの検査と環境

repo rootから、backendのlock済みPython3.13/runtime依存を使う。ローカルmanifest検査は標準Pythonだけで実行でき、AWS資格を読まない。

```sh
python3 -B -m unittest discover -s scripts/deployment -p 'test_*.py'
python3 -B scripts/deployment/deploy.py --manifest /protected/manifest.json
```

manifestの完全schema/公開fixtureは `scripts/deployment/test_contract.py::fixture`。実用時は架空accountを実accountへ置換し、`resources`をTerraformの**非秘密outputを選択して**転記する。bootstrap task ARNはbootstrap_runner、Web task ARNはbackend_service、master secret ARN/hostはdatabase、SG/subnets/distributionも照合する。secret値を入力しない。approval.referenceはチャットの対象操作承認記録を指し、budget_usd/expires_atを埋める。

証跡pathはrepo外の専用0700フォルダ、ファイル0600。失敗runも残す。同時操作禁止。CLIはそのフォルダのdeployment.lockをmkdirで取得し終了時返却する。このlockは別path/別端末の操作を防がないため、operatorを1主体に限定する。lockは古さで除去しない。中断時はprocess/taskの残存を調べ、本人承認後に自分の空lockだけ除去する。

## 1. 成果物と初回ECR

所要時間はローカルbuild/転送速度次第。実測開始終了を記録し、ここに未実測の分数を置かない。

1. 承認済みsource commitをclean checkoutし、`git status --porcelain`が空、`git rev-parse HEAD`が記録と一致することを確認。source変更中のbuildをしない。
2. frontendのlock済みbuildを実行。例: `npm --prefix frontend ci`、`npm --prefix frontend run build`。共有runtimeを使う場合は個人並列運用の排他を取得する。
3. `python3 scripts/deployment/bundle.py --root frontend/dist --output /protected/assets.json`。sha256をmanifest.frontend_sha256へ設定。staticのファイル名/MIME/hashを確認する。
4. 初回ECR未存在時だけ、必要tfvarsを保護してECR限定保存planを作る。架空backend digestはこの限定planにだけ使用する。plan/state/tfvarsにはorigin verifierが入るため表示/共有しない。

```sh
umask 077
terraform -chdir=terraform plan -input=false -target=aws_ecr_repository.backend -var-file=/protected/bootstrap.tfvars -out=/protected/ecr.plan
python3 scripts/deployment/check_plan.py --plan /protected/ecr.plan
terraform -chdir=terraform apply -input=false /protected/ecr.plan
```

`ecr_plan_verified`以外はapplyしない。plan内容がECR create1件以外なら停止。初回限定targetは通常の全体planの代替ではない。

5. 対象accountのECRへログインし、専用一時DOCKER_CONFIGを使う。`aws ecr get-login-password --region ap-northeast-1`は必ず`docker login --username AWS --password-stdin <対象registry>`へ直接pipeし、passwordを表示/保存しない。終了後専用の認証cacheだけを除去する。
6. `docker buildx build --platform linux/amd64 --file backend/Dockerfile.production --label org.opencontainers.image.revision=<40桁commit> --tag <対象ECR>:<commit>-<runUUID> --push .`。送信対象/費用承認を先に照合。immutable tagの衝突を上書きしない。
7. `aws ecr describe-images --repository-name <environment>/backend --image-ids imageTag=<同tag> --region ap-northeast-1 --query 'imageDetails[0].imageDigest' --output text`でdigestを記録し、source/build記録・revision labelと対応づける。tfvarsへ実digest/sourceを設定し、service/public/proxyは既定falseの全体保存plan→確認→apply。taskは起動しない。

## 2. private環境で初期化・migration・seed

RDS available、CloudFront Deployedかつdisabled、service desired/running/pending=0、metadata一致を確認。RDS SQL/監査ログの非漏洩条件もB6 runbookに従い確認。初期化用roleとrunnerが使えることを申請と照合する。

以下の各コマンドは前段成功後だけ実行する。`M`は保護manifest、`E`は専用0700証跡folderの絶対pathへ置換。shell変数へ秘密は入れない。

```sh
python3 scripts/deployment/deploy.py --manifest M --evidence E --aws-approved --step inspect
python3 scripts/deployment/deploy.py --manifest M --evidence E --aws-approved --step static --static-root frontend/dist --assets /protected/assets.json
python3 scripts/deployment/deploy.py --manifest M --evidence E --aws-approved --step bootstrap-inspect
python3 scripts/deployment/deploy.py --manifest M --evidence E --aws-approved --step bootstrap
python3 scripts/deployment/deploy.py --manifest M --evidence E --aws-approved --step migrate
python3 scripts/deployment/deploy.py --manifest M --evidence E --aws-approved --step seed
python3 scripts/deployment/deploy.py --manifest M --evidence E --aws-approved --step check
```

成功は実task STOPPED/exit0/実imageDigest一致と**同task streamのremote event**で判定。ログ待ちはSTOPPED後180秒、task待ちは900秒。待ち期限で成功を推測しない。bootstrap再開は同bootstrap UUIDを維持し、[B6復旧規則](fl-09b6-bootstrap-runbook.md)へ従う。migrationのfake/reverse/reset、seed既存値の修復を行わない。

seedは予約IDの`fitlog_demo_athlete`/`fitlog_demo_trainer`、`.invalid` email、usable passwordなしの公開プロフィールだけ。UUID/username/email衝突は全件rollback、既存値変更なし。同じseedの繰返しはno-op。撮影/実動作試験は後段の新利用者で行う。

### 失敗・応答不明の再開

intentはRunTaskより前に0600で保存、既存intentがあると再起動しない。通信失敗直後に新tokenでRunTaskしない。固定event `deployment_failed`だけを共有し、SDK/SQL例外を表示しない。

operatorが対象clusterの`startedBy=<runUUID>`をListTasksで調べ（停止済みも照合）、task定義/command/override/runUUIDとintentを確認。結果不明/複数候補なら停止して調査する。確定したtaskだけ、同じmanifest/step/phase/verify-inputに `--collect-task <完全taskARN>` を追加して収集する。このモードは新taskを起動しない。停止/cleanup不明は未完了として残す。失敗taskの再実行は原因とB6状態を調べた後に新しいrun UUIDのmanifest/証跡へ移るが、同環境のbootstrap UUIDは変更しない。前段証跡を別runへコピーして通さない。既存環境の再開計画を作り、不明なDB状態を新規初期化として扱わない。

復旧までに承認期限が切れた場合は、対象の期限延長承認を得てapproval metadataだけを更新する。起動時intentのtoken/hashは書き換えない。collectorは現在の承認期限と、保存済みintentのdeployment identity/task定義/override/元tokenを別々に照合する。成功証跡はidentity/IP parameters hashも含む単一の原子的JSONで、明示したcollect-taskによる再収集時だけ既存同一recordを検証して採用する。taskや判定が異なるrecordを上書きしない。private phaseのverifyはtask起動前に拒否するため、backend/publicを明示する。

## 3. backend起動・公開試験

service/proxy=true、public=falseで通常plan→apply。proxy変更でWeb task revisionが変わるのでmanifest.resources.backend_taskを新しいTerraform outputへ更新する。同run/environment/source/digestは維持。CLIはtask revision/承認期限の更新を許し、先行証跡のdeployment identityを照合する。service stable/target healthyを待つ。

`/protected/database.json`は`{"mode":"database","parameters":{}}`。次でmigration未適用なしとTLS/app DB identityを検査する。

```sh
python3 scripts/deployment/deploy.py --manifest M --evidence E --aws-approved --step verify --phase backend --verify-input /protected/database.json
```

static/secret/readinessだけで境界実証済みとしない。設計§4のFunction両behavior関連付け、originヘッダ上書き、ALB/SG/Host/IAMを確認後、public=trueの通常plan→apply。Deployedを待ち一時公開試験へ入る。対外URL共有は全試験成功後。失敗時は承認済み退避（distribution無効化→Deployed、service0→全task停止）を行い、原因不明なら停止。

### 試験表とoracle

既存OpenAPIと `backend/tests/test_auth*.py` / `test_image_api.py` / `test_social_api.py` / `test_follow_timeline.py` をoracleにする。JSONのrequestIdはサーバー生成値、既知のHTTP guard順でstatusを判定。各項目にUTC/URLの分類/期待/実結果/pass・fail・not_runを記録。raw Cookie/body/SDK応答や秘密を保存しない。

| 観測 | 受け入れ条件 |
|---|---|
| HTTPS/HTTP/SPA | HTTPS正常、HTTP拒否、static OAC経由だけ取得 |
| `/api` と `/api/*` | APIのJSON404をHTML/200へ変えず、両behaviorでFunction/forward/cache設定一致 |
| auth/CSRF/Cookie | 2利用者登録/login/logout、CSRF欠落/異origin拒否、Secure/HttpOnly/SameSite、他者更新拒否 |
| profile/posts/media/social | CRUD、画像up/read/delete、匿名media直読拒否、comment/like/follow |
| 迂回 | ALB直（普通Hostと正しいCF Host）、task public IP:8000、S3匿名直読、別distribution経由を拒否 |
| header偽装 | origin verifier/proto/IPの偽値・大小文字・複数値を送って上書き/拒否。真のverifierは取得/記録しない |

API/UIでrun固有の合成利用者2名を作り、passwordは試験runner/ブラウザのメモリだけ。失ったrunのデータを削除/変更しない。別distribution/専用対照object・secretは費用/作成/後始末を別途承認済み資源として用意し、未実行を合格にしない。

### 権限・IPのone-off検査

permissions.jsonは`mode=permissions`、parametersはmanifestと同じaccount/application_secret/master_secret、`version=<bootstrap UUID>`、`fixture_verified=true`の5項目だけ。operatorが秘密正本を触る前に、専用secret fixtureで**既存version tokenへの異値Putがversion/値/stage不変になること**を確認し、結果を保護記録へ保存する。未検証でtrueにしない。実application secretは同UUIDの唯一のAWSCURRENTを直前/直後に照合し、rotation/削除/別更新をfreezeする。

operatorがmedia bucketの `deployment-probes/<runUUID>.txt` に公開fixtureを事前作成する。Web taskはそのkeyへのGet/Put/DeleteがAccessDeniedになることと、`images/deployment-probes/<runUUID>.txt`への正常操作を確認。後者は自分の作成成功時だけfinallyで削除。誤って権限が広ければ失敗とし、対照keyの変更はoperatorが照合/片付ける。

IP試験のinputは`mode=ip`、parametersは`expected_ip`、異なるnetworkの`spoof_ip`、`window`（offset付きUTC分境界）、`before`、`spoof_before`。同じparametersでmodeだけ`ip-baseline`にしたファイルを先にverify実行し、VPC内の固定ORM照合で事前count一致を確認する。Fargate起動時間を考慮して未来のUTC分窓を選び、通常はbefore/spoof_before=0。baselineの完了後、指定したUTC窓でsignup/loginを1回だけ試し、その後mode=ipでcount差分を検証する。後段taskの起動が次の分へ遅れても、記録した元窓を照合する。CLIはbaselineの成功と同parameters hashを要求する。IPv4/32・IPv6/64、VPN有無を記録。認証の既存10回上限/他試行と競合すれば合格にせず新窓で再試験。HMAC/鍵は出力しない。`/api`はIPを消費しないためFunction関連付けの照合と動作実証を混同しない。

```sh
python3 scripts/deployment/deploy.py --manifest M --evidence E --aws-approved --step verify --phase public --verify-input /protected/permissions.json
python3 scripts/deployment/deploy.py --manifest M --evidence E --aws-approved --step verify --phase public --verify-input /protected/ip.json
```

各modeは別intent/証跡として保存。既存runの同modeを安易に再実行せず、ログ収集の再開はcollect-taskを使う。実試験に安全条件が欠ければnot_runでverifiedへ進めない。

## 4. 撮影・破棄・再構築

1. 全試験後、合成利用者2名でauth→profile→記録→画像→交流→logoutをローカル動画へ撮影。再生して必要UIが写ることを確認。terminal/AWS console/認証情報を撮らない。source/digest/runと映像hashを記録し、外部公開しない。
2. 承認済み対象inventoryと保存済み映像/証跡/state backupを照合。distribution=false/Deployed、service=false・全one-off STOPPEDを確認。停止だけで課金停止とはしない。
3. S3のversion/delete marker/multipartとECR imageを対象ID単位で列挙し承認範囲だけ空にする。汎用一括削除/force_destroy/force_deleteを使わない。失敗・他者資源は残して報告。
4. `allow_database_teardown=true`の保存planを作成。差分が既存RDS deletion_protectionのtrue→falseだけであることを確認してapplyし、実属性falseを待つ。snapshot/backup保持設定を緩めない。必要なら停止と保護解除を別planにする。
5. 同じstateで通常 `terraform destroy -var-file=/protected/runtime.tfvars`。失敗してもstateを捨てない。final snapshot/保持backupは別の承認済み工程で事前記録のsnapshot ID/DbiResourceIdに対応づけて削除する。
6. stateとサービス別API inventoryを照合し、RDS/ALB/task/ENI/CF/S3/ECR/logs/IAM/VPC/対照資源の消滅を確認。application secretは7日削除待ち・予定日を記録しforce-deleteしない。削除予約中secret自体は非課金だがbackup等の残存費用を別に記録。
7. 新environment suffix・新state・新bootstrap UUID・新snapshot名で同sourceを再構築し、image対応と基本動作/境界試験を再確認、同手順で再破棄。旧secret名を再利用せず旧state/残存を追跡する。
8. 後日、削除待ちsecret消滅と請求反映を担当者が確認。削除完了・非課金残存・請求確認待ちを分けて報告。即時請求ゼロを合格条件にしない。

実AWSの所要時間・費用は未計測。各工程の開始/終了/失敗再開を実施時に記録し、申請の稼働期限・費用上限を超える前に停止判断する。
