# AWS調査・実操作の承認案

最終更新2026-11-08。Issue #67（関連 #58/#60/#66）。**未承認草案・実行不可**。
本書の文書整備は承認済みだが、調査・AWS操作の承認は受けていない。STSを含む実AWS API、送信、公開、破棄、請求照会はすべてnot_run。

## 使い方と正本

調査申請Rと実操作申請Eを独立して承認する。開発承認、Rの承認、scenario成功をEの承認として使わない。各申請は版・対象・期間・数量・費用・実際の承認発言/参照を固定し、一方だけを承認できるようにする。未確定欄・未承認工程は実行しない。

値の状態は「確定済み」「提案」「ユーザー指定待ち」「調査後待ち」。#66のローカル契約は照合済みだが、実資源/実観測は取得後待ち。提案は承認値ではない。空欄や未確定はゼロ・無制限・許可へ読み替えない。本書は具体申請の集約先、[A操作手順](aws-a-operations.md)は実行手順、[B配置手順](aws-b-deployment-runbook.md)・[C試験手順](aws-c-verification-runbook.md)は契約正本。旧[申請様式](fl-09b7-aws-approval-template.md)と重なる場合も、実際に承認された版・値が必要。

## R：調査だけの申請

| 必須項目 | 現在値・状態 |
|---|---|
| 申請ID/版・承認参照 | R-67草案、未承認。実承認発言の対象版/日時を記録する |
| 個人account | ユーザー指定待ち：12桁。会社accountは対象外 |
| 既存operator role | ユーザー指定待ち：pathを含む完全IAM role ARN。assumed-role ARNだけで代用しない |
| 実行担当・個人資格の選択方法 | ユーザー指定待ち：単独operator名と明示profile/既存role利用方法。既定profileへのfallbackなし。資格値は記載しない |
| 配置region | 確定済み：ap-northeast-1。下表のglobal APIは例外を明示 |
| 初回/再構築environment候補 | 提案：fitlog-demo-first / fitlog-demo-second。調査前に実名を指定し、衝突検査へ使用 |
| 調査開始/終了 | ユーザー指定待ち：UTC `YYYY-MM-DDTHH:MM:SSZ` と同じ瞬間のJST。期限外に続きを呼ばない |
| API/ページ/再試行/時間上限 | 提案：下表だけ、全体200 HTTP要求以内（ページ・再試行含む）、30分以内、各要求30秒以内、失敗の自動再試行なし。未完なら停止し残件を記録 |
| 調査費用 | ユーザー指定待ち：USD上限と予備費。read APIでも無課金を推定せず、請求照会はこの申請に含めない |
| 非秘密結果の保管 | ユーザー指定待ち：repo外の正規絶対path、owner、親0700/file0600、保存/削除期限、共有範囲。認証情報・raw policy・全応答をPRへ貼らない |

### Rで許可を求めるactionと取得範囲

これはIAM policyを付与する操作ではない。既存権限で不足すれば停止する。各行の対象を上の実account/環境名へ置換し、引数・ページ上限も承認対象にする。サービスの一覧系でresource単位制限できない場合にだけ`Resource=*`を要し、account/region/取得項目/件数を運用で限定する。未知APIを「Describe全般」として追加しない。

| 目的 | 正確なIAM action | 対象・必要な非秘密項目 |
|---|---|---|
| identity | `sts:GetCallerIdentity`, `iam:GetRole` | 指定account/roleのみ。IAMはglobal。role正本のpathとAssumedRoleの対応を照合。secret値/policy本文は収集しない |
| AZ/DB提供 | `ec2:DescribeAvailabilityZones`, `rds:DescribeDBEngineVersions`, `rds:DescribeOrderableDBInstanceOptions`, `rds:DescribeCertificates` | Tokyo通常AZ2つ、PostgreSQL17の完全minor、db.t4g.micro、Single-AZ/gp3 20GiB、CA ID/期限。提供がないときclass/minorを自動変更しない |
| quota値 | `servicequotas:ListServiceQuotas`, `servicequotas:GetServiceQuota` | Tokyoのvpc/ec2/elasticloadbalancing/ecs/fargate/rds。global quotaは対象service/endpointを別記して承認。必要quota codeは調査記録へ保存 |
| network使用量 | `ec2:DescribeVpcs`, `ec2:DescribeSubnets`, `ec2:DescribeSecurityGroups`, `ec2:DescribeSecurityGroupRules`, `ec2:DescribeNetworkInterfaces`, `ec2:DescribeAddresses`, `ec2:DescribeManagedPrefixLists`, `ec2:GetManagedPrefixListEntries` | 同account/Tokyoのquota使用数とCloudFront origin-facing managed prefix list。SG枠はprefix-list weight込みで余力確認。既存SGを変更しない |
| ALB/ECS使用量 | `elasticloadbalancing:DescribeLoadBalancers`, `elasticloadbalancing:DescribeTargetGroups`, `ecs:ListClusters`, `ecs:ListServices`, `ecs:ListTasks`, `ecs:DescribeTasks`, `ecs:DescribeClusters` | 同account/Tokyo。ALB/TG、cluster/service数、Fargate稼働/pending taskと予約vCPU。DB個数は次行と共用。全accountのデータ内容取得はしない |
| DB/snapshot衝突 | `rds:DescribeDBInstances`, `rds:DescribeDBSnapshots`, `rds:DescribeDBInstanceAutomatedBackups` | 同account/Tokyoの使用数と2環境のDB/最終snapshot名、DbiResourceId/保持backup。snapshot内データは読まない |
| ECR設定/衝突 | `ecr:DescribeRepositories`, `ecr:GetRegistryScanningConfiguration` | 2環境repository名、registryの基本/拡張scan設定。imageやtokenの取得・pushはしない |
| secret衝突 | `secretsmanager:DescribeSecret` | 2環境のapp/master/fixture予定名だけ。削除予約日時/ARNのmetadata。GetSecretValueは禁止 |

quota不足/使用量不明、AccessDenied、期限切れ、API上限、role/account相違、名前衝突はfailまたはnot_runとして止める。quota引上げや権限付与を調査の継続として実行しない。既存roleのpolicy/boundary/SCPの有効権限は担当から得た非秘密の許可範囲と照合し、このRにないIAM調査APIを勝手に呼ばない。IAM simulationだけで実権限成立としない。

Rの結果表は`action / filter・対象 / observed_at / 選択値・数量 / pass|fail|not_run / 非秘密根拠path・hash / 残件`。2AZ、完全minor/class/CA、quota値と使用数/必要数/差引余力、衝突/scanを埋めてからEへ転記する。

## E：初回・再構築・検証・破棄の実操作申請

R終了後に具体化して別承認する。以下は工程を漏らさないための草案であり、対象ARNや金額の確定申請ではない。

| 共通必須項目 | 現在値・状態 |
|---|---|
| E申請ID/版・承認参照 | E-67草案、未承認。R結果の版/path/hashとE対象版を紐づける |
| account/role/operator | Rと同じ実値を転記し実承認へ拘束。現在ユーザー指定待ち |
| AZ/DB/CA/quota/scan | 調査後待ち。Rのpass記録がなければ構築不可 |
| source | 配置するclean checkoutの完全commit OID、依存lock、CA bundle hash。選択待ち。#66の統合と再検証後に固定し、#67のbaselineを配置対象と自動解釈しない |
| image/static | 各回の実ECR digestとfrontend inventory SHA256、build証拠。取得後待ち。同sourceでも同digestを仮定しない |
| 2環境binding | 異なるenvironment/state/TF_DATA_DIR/run UUID/bootstrap UUID/snapshot名、campaign UUID、B/C handoffとreceipt hash。取得後待ち |
| region/実対象 | TokyoとglobalなCloudFront/IAM。ARN/ID、cluster/service/task定義、role4件、bucket/key、repository、distribution/Function/OAC、VPC/subnet/SG/DB/log/secretを列挙。未作成分は保存planとprefix/tagで限定し作成直後に正本IDへ拘束 |
| local秘密保管 | ユーザー指定待ち：repo外path/owner/保存期限。環境別state/TF_DATA_DIR/tfvars/plan/json/log/backupは親0700/file0600（読取り0400可）、非symlink・正規path/hash。raw値をGit/PRへ出さない |
| 費用 | ユーザー指定待ち：2構築/調査/fixture/残存/後日照会/予備費の見積USD・上限USD・早期停止閾値。JPYは為替日/税/余裕を分離。未確定値を0にしない |
| 公開・共有 | 提案：CloudFront既定domainで限定一時公開、public signup、origin区間HTTP。exact HTTPS originとURL共有先を承認時に指定。撮影は隔離保存、秘密検査/視認前に共有しない。動画の外部公開は対象外 |

### 2環境の期間と成果物対応

| 項目 | 初回 | 再構築 |
|---|---|---|
| environment | fitlog-demo-first（提案） | fitlog-demo-second（提案） |
| start_at / close_start_at / public_end_at / destroy_by | 実UTC/JST指定待ち | 実UTC/JST指定待ち |
| 時間配分の提案 | startから2hで閉鎖開始、3hまでに公開終了、4hまでに破棄 | 同じ配分。初回破棄/棚卸し後に開始 |
| state/TF_DATA_DIR/backup/plan path・hash、run/bootstrap、snapshot名 | 指定・作成後待ち | 初回と別値。指定・作成後待ち |
| source/image/static/B・C証跡 | 実取得後照合 | 同sourceから再buildし新規取得、旧証跡の流用不可 |

両環境とも`start_at < close_start_at < public_end_at < destroy_by`、初回destroy_by≦再構築start_at。構築の遅延で試験窓が取れなければ公開せず閉鎖へ進む。閉鎖の実測所要時間は未確認で、1時間の提案猶予を保証としない。公開/試験窓と退避/破棄の許可窓を分け、遅延予測で早期退避する。期限外のAPIには新しい具体許可が必要。

### 工程ごとの対象・許可・証拠

Terraformの必要write action/条件は、実際のHCL・保存planと選択済み資源からaction/ARN表を作ってEの付属資料にする。現時点は調査後待ちであり、下表のサービス名だけを包括CRUD許可として使わない。未作成ARNを理由に既存共有資源まで対象に広げない。公開/破棄の保存planも対象・hash・許可期限に照合する。

| 工程 | 許可を求める対象・操作 | 成功証拠と停止条件 |
|---|---|---|
| ECR限定作成・build/push | 環境別repository create1件、`ecr:GetAuthorizationToken`、対象repoの`BatchCheckLayerAvailability/InitiateLayerUpload/UploadLayerPart/CompleteLayerUpload/PutImage/DescribeImages` | ECR限定plan検査、clean sourceと実digest。架空digestは限定planだけ。送信先/scan/費用未確定なら停止 |
| 非公開基盤構築 | 選択済みEC2 network/ELBv2/CloudFront/Function/OAC/S3/ECR/ECS/RDS/log/secret/専用IAM。planごとのaction/対象表必須 | default workspace・backend/state hash/lineage/serial照合、private/service0・DB保護on。予期しない置換/削除/権限拡大は停止 |
| B配置 | 対象static bucketの`ListBucket/GetObject/PutObject`、cluster/taskの`ecs:RunTask/DescribeTasks/ListTasks/StopTask`、指定streamの`logs:GetLogEvents`、Bで要求するmetadata action（別表へ展開） | inspect→static→bootstrap-inspect→bootstrap→migrate→seed→checkの同run証跡。未知応答時はintent収集、起動確認なしに再RunTaskしない |
| PassRole | Web/bootstrapのtask/execution role完全ARN計4件、`iam:PassRole`かつ`iam:PassedToService=ecs-tasks.amazonaws.com` | 取得した実ARNとtask定義を照合。Web roleの管理権限拡張は不可 |
| backend確認・一時公開 | 対象service/proxy、distributionだけ。private backend verify後にpublic=true | 各B工程とremote event、distribution Deployed、health/DB/seed/static対応。単なるALB liveは合格でない |
| 対照fixture・probe | #66の専用S3 object/別distribution等、およびBの専用metadata/permission fixtureを個数/容量/ARN/key/TTL/actionで列挙 | #66契約照合済み。下の数量/action/時間の提案を実値へ拘束し承認するまで開始不可。無関係のobjectや既存distributionで代用しない |
| C試験・撮影・性能 | 同origin/lease/campaignの既存C上限と#66確定分だけ。下記試験表 | B ready_for_cと証拠hash/実対象照合。403/timeout/成功要約だけをC04合格にしない |
| 閉鎖 | distribution無効化→Deployed、service0→running/pending0、同runの全one-off停止/収集 | API応答だけで停止扱いしない。全client停止・lease返却・実task状態を確認。停止不明は未完了 |
| 初回/再構築の破棄 | 停止確認後DB保護解除plan/apply→実保護off確認→通常destroy。許可済み専用bucket全version/delete marker/multipart、ECR image、fixtureの削除 | exact ID/ownerを照合、共有データ清掃/force_destroy/state手動編集/force-unlockなし。snapshot/backup等を残存台帳へ移す |
| 残存・後日確認 | 下記の対象ID別照会/期限付き削除と限定請求照会 | 確認日/担当/許可窓を必須とし、state空やECS0で課金停止を断定しない |

B manifestの`approval.steps`は既存8工程の許可部分集合だけ。Terraform/送信/公開/破棄の実許可をこの配列で代替しない。Eのaction表にないmetadata APIやfixtureが必要になればその工程を保留し、未承認追加を行わない。

### 試験・データ・操作窓

下表は#66統合commit `aadcf26a1d317f3baca3ac3cf1eb50b4681ccbb4` の[C契約](aws-c-verification-design.md)および[C04観測契約](aws-c-boundary-contract.md)との照合結果。既存C上限とAの追加枠を分ける。

| 区分 | 1環境の数量・上限 | 2環境・残置の扱い |
|---|---|---|
| B seed | usable passwordなしの予約プロフィール2利用者 | 合計4利用者。再seedは同環境でno-op、別run証跡へ流用しない |
| Cデータ | 新規2利用者/投稿6/comment4/保存画像4点・各64KiB以下 | B+C計4利用者/環境、2環境計8利用者。C利用者2名はcleanup後も残る |
| C通信 | 3000要求（通常2800+cleanup200）、送信20MiB、auth24回・rolling60秒8回 | 各環境1attempt、失敗/中断も消費。2環境分台帳を別pathで初期化し直さない |
| C時間/性能 | 5分超45分以内の固定窓、末尾5分cleanup/30秒停止確認。GETはwarmup10秒+90秒180枠 | C要求予算内。追加run/利用者/負荷/自動再loginなし |
| 撮影/原本 | 限定quarantine動画、非秘密reportのみ。Cookie/CSRF/password/trace/HAR/raw DOMを保存しない | 視認・秘密混入検査・破棄後オフライン再生を別判定。保存先/期限/共有担当は指定待ち |
| B one-off/A追加probe | B task数・実起動時間はB実手順から積算。AのC04 HTTP9要求/環境、metadata/fixtureは下記別枠 | 2環境HTTP18要求。既存感度分析の追加task0.5hで全工程を賄えるとは扱わない |

Aは単独operator。lease台帳に`lease_id / environment / 対象 / window / owner / handoff_at / paused_at / returned_at / 停止証拠`を持たせる。C開始後は構成/rotation/task変更をfreezeする。A検証が必要ならC送信停止・全in-flight完了/取消→Aへ一時返却→対象固定の検証/収集・全one-off停止確認→Cへ再引渡し。A/C要求を重ねない。IP観測はA baseline→停止→Cだけ認証1要求→C停止→A after。同窓/共通IP認証枠を照合し、自動再試行しない。停止不明はlease未返却。ローカルruntime lockだけでAWS排他を証明しない。

Cは自己所有投稿/comment/like/follow/avatarを解除して残置/unknownをIDで渡す。利用者削除APIがないためB seedとC利用者、未回収画像・未確定書込みはAの環境破棄対象。cleanup成功を残存ゼロとはしない。

### #66との最終照合（2026-11-08）

PR #69はhead `62b813bdad611726ce3c549bf5f55dbba85b0237`、統合commit `aadcf26a1d317f3baca3ac3cf1eb50b4681ccbb4` で統合済み。[C04観測契約](aws-c-boundary-contract.md)と実検証器 `e2e/aws_boundary.py`、C02 `e2e/support/aws-oracles.mjs` を読み取り照合した。文書/検証器/送信量の受領は完了、実AWSの収集/合格/実操作準備完了とは区別する。契約文書とFunctionのbyte hashは[A結果](aws-a-results.md)の照合記録へ固定する。

| 受領項目 | 確定した契約・申請への反映 |
|---|---|
| C04 receipt/原本 | C契約schema v1のevidence配列を維持、receiptはschema v2。9 identity、全7probe共通inventory、対象実在原本、probe別観測原本をpath/byte SHA256で拘束。各file最大1MiB、owner/非symlink・非hardlink/親0700/file0600または0400。Bのcanonical JSON hashと混同しない |
| 対象/期待結果 | ALB通常/Host差分各1、task1、S3 static/media匿名各1、正規/別distribution同一static object対照各1、viewer通常/spoof各1。合計9要求/環境。HTTP404/一般通信error/未知object/SG根拠なしtimeoutは合格不可 |
| 別distribution | 正規と別のID/DNS、同じstatic bucket/key、origin path空・behavior `*`、両者にS3 OAC always/sigv4を実attachment。正規200+既知hash/lengthと別403/AccessDeniedを対照。既存bucket policyを広げない |
| ALB/task/Function | ALB HTTP80はCloudFront prefix-list1規則のみ、task HTTP8000はALB SG1規則のみ。全SG attachment/全ingressを収集、余分な規則を射影で隠さない。実LIVE Function code hashとAPI association、BのIP baseline/afterとparameters hashを対応 |
| viewer health | `/api/health/live` の本文は空白/末尾改行なし15byte、SHA256 `a29ee2b15c494311c52521766e44af56a3ad2248e7a8ab465e5206463c13d288`。通常/spoof両方200。secret値は保存せず、固定非秘密spoof値を台帳とB条件へ拘束 |
| C02 | CSRF GET1+状態GET4+PUT3=8要求、既存Cの3000要求/20MiB/45分内。Originのみ異なる正負PUT、marker変更→復元→負例403/CSRF_FAILED→復元状態不変。既存投稿を使い追加利用者/画像/投稿なし |
| 失敗/停止 | 原本不正はpreflight拒否、欠落/旧要約はnot_run、明示失敗を優先。終了時にも参照/byte hash集合を再照合し改変/追加/消失はfail。C04全7probeとB permissions/IPが揃った場合だけfinal_evidence_ready、総合acceptanceは別判定 |

### A追加枠の数量・権限・期間（Eの承認候補）

以下の上限は#67の提案であり実承認ではない。C04 HTTP9要求は#66の確定要求数、その他の数量/時間は実資源と承認へ拘束する。R調査にfixture作成や観測APIを自動追加しない。

| 区分 | 1環境 / 2環境の数量・提案上限 | 費用・後始末・許可対象 |
|---|---|---|
| A C04 HTTP | 9 / 18要求。GETのみ、各timeout5秒、redirect/retry0、body各16KiBまで、受信合計144KiB / 288KiBまで。送信header込み上限は64KiB / 128KiBの提案 | ALB2/task1/S3匿名2/CloudFront4。Cの3000要求/20MiBへ暗黙加算しない。認証/製品データ書込みなし。受信上限超過は中断しfail、本文は保存せずbyte数/hash/分類だけ保存 |
| 既知object | static1+media1=2 / 4点、各1〜16KiB、計32KiB / 64KiBまで | 各環境の専用key・本文hash/length・ownerをEへ記入。B/Cの利用者画像数と別枠。AがPut/Head/Getで実在確認し、C全client停止・lease返却後〜destroy_byに削除。既存object流用はexact key/hash/ownerの別承認がある場合だけ |
| 別distribution/OAC | 専用distribution1+専用OAC1 / 各2。既存正規distribution/OAC/Functionは各環境1を参照し新規Functionなし | 同じstatic bucketへOAC署名し、bucket policyのSourceArnを追加しない。作成/Deployed待ちを公開前に行い、閉鎖時disable→Deployed→delete、OACはdetach後delete。resource IDを残存台帳へ記録 |
| metadata/fixture API | 提案200 HTTP API要求/環境（ページ・作成/伝播poll・読取り・削除・再試行すべて込み）、2環境計400。1要求timeout5秒、自動retry0 | 下記actionだけ。9匿名HTTPとは別枠。作成/確認/削除ごとの残枠を記録し、片付け枠を最低50/環境確保。不足予測なら新規工程を開始しない。完了不能なら残存として引渡し、未承認の継続は不可 |
| 時間/lease | C04観測+対象metadata再確認は10分以内の提案、固定C窓内のA一時返却区間に配置。C04単純timeout合計は最大45秒 | inventory/各原本のobserved_atはすべてCの[start,expires)内。C送信停止→A観測→全要求終了→C返却、構成freezeを維持。fixture作成/伝播/削除は各構築4h提案の内数でC45分に足さない。伝播不足で窓を確保できなければ試験を始めず閉鎖 |

A metadata/fixtureのE付属action表は以下を対象実ID/ARN/keyに限定する。作成前だけenvironment prefix/tagと保存planで束縛し、作成後IDを登録してから次工程へ進む。

- 実在/attachment: `elasticloadbalancing:DescribeLoadBalancers`、`ecs:DescribeTasks`、`ec2:DescribeNetworkInterfaces`、`ec2:DescribeSecurityGroups/DescribeSecurityGroupRules/DescribeManagedPrefixLists`。対象ALB/task/ENI/SG/prefix-listに限定し、Resource制限不能は理由を記載。
- CloudFront読取り: `cloudfront:GetDistribution/GetDistributionConfig/GetOriginAccessControl/GetFunction`。正規/対照distributionとそのOAC、正規LIVE Functionだけ。raw設定のorigin secretや全headerは保存せず収集時にallowlist射影。
- object: 対象bucketの専用keyへの `s3:PutObject/GetObject/DeleteObject`（HeadObjectはGetObject権限）、削除確認に必要な `s3:ListBucket`。version/未完了uploadがある場合は許可済みのversion別削除/abort actionとIDをEに追加確定してから実行。bucket policy更新なし。
- 対照作成/閉鎖/破棄: `cloudfront:CreateDistribution/CreateOriginAccessControl/UpdateDistribution/DeleteDistribution/DeleteOriginAccessControl/TagResource`、対象の上記Get系。create時に別actionが必要な配置方式は自動代用せず付属表を確定してから実行。B固有permission fixture/RunTaskはBの既存工程で別計上し、本枠で包括許可しない。

料金は[費用表](fl-10b-aws-costs.md)の追加内訳へ配賦。実数量/実期間/単価/請求有無が未確認のAPI、LCU、Function、転送、保存を0にしない。9要求の低負荷でも全体USD上限や後日確認担当を省略しない。

#69の既知Mediumも実申請へ引継ぐ。C02復元前失敗でmarkerが残る可能性は残置投稿IDと状態をAへ渡し、無断再試行しない。media実在はAのHead/Get射影原本に依存し匿名403単独では証明しない。task入替え後の古いIPを検出する追加正常対照/最大時間差制限は未実装なので、原本時刻/実task identity/構成freezeを突合し、確証がなければ実境界の合格とはしない。原本消失〜runtime停止/lock返却の結合テスト不足とC結果文書の一部旧状態は#69の既知事項であり、#67からC所有文書/実装は変更しない。

## 残存・後日請求の申請欄

| 対象 | 数量・保持・削除/照会・担当（実値指定待ち） |
|---|---|
| DB最終snapshot/保持automated backup | 両環境のsnapshot ARN/DbiResourceId/容量を台帳へ。提案保持7日、実delete_byと担当必須。追加backupは別加算 |
| secret | app/master/fixtureのexact ARN・DeletionDate・回復期限。提案7日回復、非課金でも消滅確認は必要。強制即時削除は許可しない |
| S3/ECR/log/fixture | version/delete marker/upload ID/image digest/log group/対照distributionを棚卸し、保持量/理由/USD・delete_by・owner・証拠を記入 |
| ALB/ENI/IPv4/ECS/CloudFront/IAM/network | state内外双方を実IDで照合。消滅/保持と理由を記録し、共有資源に触れない |
| local state/backup/planと映像/非秘密証跡 | 別々のpath/owner/権限/保持・削除期限/共有範囲を指定。AWS破棄と同時に必要な証拠を失わない |
| 後日read照会 | E対象IDに限定したRと同種のDescribe/List、必要なS3 `ListBucketVersions/ListBucketMultipartUploads`、ECR `DescribeImages`、CloudFront `GetDistribution`、logs `DescribeLogGroups`、secret `DescribeSecret`等をexact action/対象の別表に確定。削除は別途承認されたaction/IDのみ |
| 請求照会 | `ce:GetCostAndUsage`、endpoint `ce.us-east-1.amazonaws.com`。調査Rに含めない。対象account/日付範囲/サービス・利用可能なtag filter/粒度/ページ上限/費用/UTC-JST照会窓・担当を指定。tag未反映ならゼロ費用とせず未確定 |
| 確認日 | ユーザー指定待ち：destroy直後、予約削除予定日後、請求反映後の日付/許可窓。提案は破棄翌日と8日後、さらに翌請求月の確認。各窓外のAPIを自動実行しない |

台帳項目は[A手順](aws-a-operations.md)を使用し、各行の数量不明を0にしない。RDS停止はstorage/backup課金を残し7日で再開し得る。[RDS公式](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_StopInstance.html)。削除予約secretは回復期間中非課金だが、消滅時刻の実確認が必要。[Secrets Manager公式](https://docs.aws.amazon.com/secretsmanager/latest/userguide/manage_delete-secret.html)。Budgetsは反映遅延があり強制上限ではない。[Budgets公式](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html)。CE照会も有料で、page/requestの積算を[公式料金](https://aws.amazon.com/aws-cost-management/aws-cost-explorer/pricing/)と照合する。

## 指定・確認が必要な事項（まとめ）

1. R/Eそれぞれの個人account・既存role完全ARN・単独operator・明示資格選択方法。
2. R調査の開始終了、API/ページ/時間上限・USD上限、候補環境名。
3. Eの2環境実日時、公開/試験/閉鎖/破棄窓、後日照会窓と削除・請求担当。
4. 2構築+調査+fixture+残存+照会+予備費のUSD上限・早期停止閾値、必要ならJPY為替/税。
5. 秘密/証拠/映像のrepo外保管path・owner・権限・保持期限、URL/映像の共有範囲。

これらは文書開発を止める入力ではなく、R/Eの具体申請を確定する入力。Rを承認する際はRの実値/版だけ、Eを承認する際は調査結果・#66/B契約・実対象・action付属表・費用内訳・全窓を含むEの実値/版を明示する。未記入草案への一般的な「進めて」はAWS操作許可として採用しない。

## 検証と現在の到達点

文書の整合、[費用表](fl-10b-aws-costs.md)とscenario v1の式/時系列、既存オフライン検査で確認する。scenarioは過去の架空日時も受理するため、現在の承認有効期限・権限・fixture充足を保証しない。R/E値と実承認の照合はoperatorの責任。

実装/検証の結果は[A結果](aws-a-results.md)の#67欄へ記録する。#66の契約最終照合は完了。ユーザー指定値、R結果、E実承認、実C04原本は未取得。実AWSの成功・費用成立・全体完了は宣言しない。
