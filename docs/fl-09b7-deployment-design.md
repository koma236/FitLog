# FL-09B7 AWS配置・実経路検証の準備

## 1. 承認・範囲

2026-11-06承認、Issue #52。独立設計レビュー2巡、最終High0/Medium0。
担当A、branch feat/fl-09b7-deployment-52、worktree /Users/saki/.codex-personal/worktrees/24d7/FitLog。
基準2b80ae9cdf8f07e290a20181e8a208347b2aeea5から担当BのPR #51（b33c9f4d92b155e6935481567860bee6545c0102、ci-required成功）を取り込み済み。
ローカル実装・検証・文書・PRを対象とし、高リスク相互レビュー待ちで停止する。
実AWS API・資源作成・公開・課金・データ消去は別途具体的承認を必要とする。
CI/Compose/依存lock/checks台帳/OpenAPI/Django migration/製品認証認可の挙動は変更しない。

入口: [runbook](fl-09b7-deployment-runbook.md)、[実AWS申請](fl-09b7-aws-approval-template.md)。
実行用CLIは scripts/deployment/deploy.py、remote処理は backend/operations/deployment_*.py と demo_seed.py。

## 2. 仕様・インターフェース

親が直接実装。Python標準ライブラリ＋既存backendのboto3を利用し新runtime依存なし（親の選択）。CLIは工程別で、既定はローカルmanifest検査だけ。AWSモードは明示し、固定東京/商用公式endpoint/期待accountを照合する。任意command/endpoint/SQL/秘密値を入力にしない。

成果は(1)対象・順序照合、(2)image/static配置と固定種類のone-off task補助、(3)実経路試験と証跡collector、(4)撮影/破棄/再構築runbook。汎用破壊操作や一括削除ツールは作らない。

manifestはschema version、実行UUID、期待account/region/environment、承認記録参照、費用/期限、source commit、frontend成果物sha256、backend ECR digest、保護stateのローカル参照、resource ID/ARN、bootstrap UUIDを持つ。local draftは未決値を許す。AWSモードは空欄/期限切れ/他account/region/environment/未承認工程を拒否する。承認参照は監査補助で、人間の実承認を代替しない。

`--draft`はローカル専用で、未決値は項目省略またはnullで表す。入力済み値・未知項目・既知account/environmentとARNの不一致は完全manifestと同じ規則で拒否する。draftとAWS指定の併用は拒否し、draftオブジェクトは全項目が揃っても実行権限を持たない。

`state={path,sha256}`はstateファイルの正規絶対pathと実内容SHA256。AWS接続前に非symlinkの通常file、実行者所有、親0700・file0600または0400、hash一致を確認し、state本文を出力/証跡へ保存しない。これは参照artifactの拘束であり、state内容のTerraform上の意味的正当性は保存planとAWS metadata照合で確認する。各apply後はhashを更新し、同runでstate pathを変更しない。run identityからは変更可能なstate hash・承認情報・task revisionを除き、各呼出しのmanifest hashには全値を含める。

`approval.steps`は実装済みCLI工程inspect/static/bootstrap-inspect/bootstrap/migrate/seed/check/verifyから選ぶ重複なしの非空一覧。現在工程がなければGateway接続前に拒否し、collect-onlyも現在の承認へ同工程を必要とする。verifyのphase/modeは別途既存guardで照合する。人間の承認内容をこの一覧へ転記する責任と、その真正性の確認はoperatorが担う。

同じrun UUIDの全AWS工程は、専用証跡folderのlock内で不変identityのbindingを保存・照合してから接続する。先行工程のないinspect/bootstrap-inspectやstaticも対象で、同じ内容のstateを別pathへ移しても拒否する。bindingの不完全/不一致を上書きして通さず、新しい対象で開始する場合は新run UUIDを使う。保存前の失敗ではAWSへ接続しない。

証跡はsnapshot/commit、開始終了UTC、工程、manifest hash、task ARN/digest、exit code、観測点、pass/fail/not_runをrunごとに保存。失敗/timeout/判定不能を成功にしない。再実行前にAWS正本を照合。SDK例外本文、秘密、SCRAM verifier、state/plan JSON、origin header、Cookie/token/password、HTTP全header/bodyを記録しない。保存先0700・記録0600。映像は合成デモデータのUIのみ。

manifestだけを正本にせずTerraform管理対象の非秘密metadataとSTS/Describe/tagsを相互照合。output全体のdumpをしない。raw state/保存planは秘密扱い。環境名一致だけで削除対象を決めない。

## 3. 配置とone-off実行

### 3.1 image/staticと初回ECR

cleanな統合済みcommitからLinux/amd64 production imageをbuild。revision label・build記録・immutable tag（commit/run対応）を保存し、ECR送信後DescribeImagesのdigestとtask定義を照合。既存tagと異なるdigestの上書きは拒否。frontendは同commit/lockからbuildしファイル名/MIME/hash manifestを作る。対象static bucketだけに配置しmediaへ同期しない。削除付きsyncは使わない。

ECR未作成と必須image digestの循環は、初回だけ `aws_ecr_repository.backend` のtarget plan/applyで解消する（親の選択）。変更が同resourceのcreateだけであることを確認し、他資源/既存repo変更が混ざれば停止。root必須入力用の架空digestはこの限定planのみで使用。送信後の実digestで必ず通常full plan/applyを行う。日常配置/復旧はtargetを既定にしない。今回実行せずmockで範囲を検査する。

### 3.2 bootstrap runner

専用one-off Fargate taskをTerraformへ追加。既存production image、別family、amd64/platform1.4.0・0.25vCPU/1GiB、public subnet/public IP、既存app SGを使いALB登録なし。DB5432/外向き443のSGを広げず、Exec/SSH/SSM/NAT/踏み台は追加しない。Web service0・CloudFront disabledを維持。

- commandはB6の `python -m operations.bootstrap`。region/CA等の非秘密envだけを持ち、application secretの起動時注入を持たない。未投入secretで起動できない循環を防ぐ。管理者secretはB6がSDKでメモリ内取得する。
- 専用task roleはSTS GetCallerIdentity、RDS DescribeDBInstances、ECS DescribeServices/DescribeTaskDefinition、ELB DescribeLoadBalancers/DescribeTags、CloudFront GetDistribution/ListTagsForResource、対象application secret DescribeSecret/ListSecretVersionIds/GetSecretValue/PutSecretValue、対象RDS管理secret GetSecretValueのみ。Resource制限不可のDescribe系だけ `*` としAWS公式認可表の根拠を残す。管理secret ARNはresource metadata参照、既存AWS管理keyを維持。
- 専用execution roleはECR取得と専用7日log group書込みのみ。Web task/executionには管理秘密/secret書込みを追加しない。bootstrapにS3データ操作/IAM変更/RunTask/PassRole/破壊権限なし。
- operatorの必要権限を対象task定義RunTask/DescribeTasks/StopTask・cluster条件・必要なrole完全ARNへのPassRole（ecs-tasks.amazonaws.com条件）までrunbookに列挙。既存個人operatorの権限を勝手に変更しない。実操作申請時にroleを指定。
- collectorを動かすoperatorには、対象Web/bootstrap log groupの対象streamへの `logs:GetLogEvents` を追加する。task定義のawslogs group/prefix/containerとtask ARN末尾IDからstreamを特定し、任意streamや全ログ取得は許さない。STOPPED後の到着待ちは180秒を上限とし、event欠落/不正/食違いは判定不能。raw log本文を転記せず、許可した完了eventの項目だけを証跡にする。非blocking awslogsによる欠落も成功扱いしない。
- inspect→initializeは別工程。B6の固定非秘密引数と記録した同UUID、永続claim/lock/TLS/再開規則を再利用。B6ロジックは改変しない。

### 3.3 migration/seed/verify

bootstrap_verified後、Webと同じtask定義/非管理者DB role/secret/media IAMのone-offで `python -m operations.deployment_step --step <工程> --run-id <UUID>` を工程ごとに実行する。固定allowlistはmigrate/seed/check/verify。公開前はmigrate=`manage.py migrate --noinput`相当のDjango call_command、seed=demo_seed、check=`migrate --check`相当の順で、service0/distribution disabledのまま実行する。verifyは§4の段階別guardで実行。任意command/SQLは受け付けない。

wrapperは子処理の正常終了後だけ `deployment_step_completed` とrun UUID/stepをJSON一行で出す。子の通常出力・例外詳細は外へ流さず、失敗は固定eventと非0終了。ログや例外に秘密が混ざる負例をテストする。collectorは**同じtaskのstreamから**UUID/step一致のeventを取得し、exitCode/digestと合わせて照合する。collectorがexitCodeからeventを捏造しない。bootstrapはB6既存event/operation UUIDを同様に照合する。

seedは架空プロフィール2件のみ（予約username/決定的UUID、`.invalid` email、非staff/非superuser、usable passwordなし、健康値なし）。単一transactionで作り完全一致はno-op。username/email/UUID衝突・値不一致は変更前停止し更新/削除/password再設定しない。schema/migration追加なし。

AWS対象/停止状態は**operator側のpreflight**が照合する。bootstrap/migrate/seedではservice desired/running/pending=0かつdistribution disabledを要求し、他の変更実行主体がいない排他を保持する。seed/wrapper内はproduction設定・期待DB host/name・session_user=fitlog_app・TLS実接続を検査する。Web taskにECS/RDS Describe権限を追加せずB6 Aws.inspectも再利用しない。公開後verifyはoperatorがservice稼働と正しいdistributionの公開試験状態を確認する別guardを使い、停止専用guardを流用しない。任意操作を可能にするoverrideはdeploy補助が拒否する。

認証/投稿/画像/交流の試験データは公開試験中に既存API/UIから作る。run UUID別の利用者2名、passwordは試験runner/ブラウザのメモリ内だけ。資格を失ったrunは再利用せず、新runで試験し前runを改変/削除しない。まとめた消去は承認済み環境破棄のみ。固定seedの冪等性と可変E2Eデータを分ける。

起動clientToken/task ARNを記録。応答不明時に無条件で別taskを起動しない。DescribeTasksでSTOPPED、必須container exitCode=0、固定完了event、imageDigest一致を確認。失敗/応答不明/timeout/競合は後段へ進まない。停止要求後もSTOPPEDを確認。migration中断は台帳を調べ、reverse/fake/resetで自動修復しない。

## 4. 公開切替と受け入れ条件

状態: local_prepared→approved_aws→private_applied→bootstrapped→migrated_seeded→backend_ready→public_testing→verified→captured→destroyed→rebuilt→destroyed_again。同じ対象の証跡が揃った時だけ進む。公開試験中の失敗はdistribution無効化/service0へ退避し、原因不明なら停止（退避も実AWS申請に含める）。

1. image/static/secret/migration完了後service/proxy=true、distribution=falseでfull apply。service stable/target health、one-offでDB/migration確認。liveをreadinessと呼ばず、S3実操作も別試験する。
2. header上書き/両API Function関連付け/origin/SG/IAMの定義照合後、distribution=trueで公開試験、Deployedを待つ。一時公開は実試験に必要。URL対外共有は全試験成功後。public signupとALB/task区間HTTPの境界を実AWS申請へ含める。
3. HTTPSのSPA、`/api`（JSON404）、`/api/*`、live/ready、未知APIのJSON404、HTTP拒否。2利用者のCSRFなし/異origin拒否と正常操作、Secure/HttpOnly/SameSite Cookie、login/logout、本人/他者更新、profile、投稿CRUD、画像up/read/delete、匿名media拒否、コメント/like/follow。status/bodyのoracleはOpenAPI/既存テスト/guard順序に対応づける。
4. 直ALB（通常Host/正しいCloudFront Hostの両方）、task public IP、S3 static/media匿名直読、別CloudFront distribution経由を拒否。別distributionは対照用短命資源として別途費用/削除承認に含め、なければnot_run＝受け入れ未完了。
5. `/api` と `/api/*` へviewerのorigin verifier/proto/client-IP偽装（大小文字/複数値）を送る。秘密verifierを取得/記録せず偽値だけ使用。IPは認証試行の前後におけるDB固定窓HMACのcount差分をVPC内verify taskで照合しbooleanだけ出す。IPv4は/32、IPv6は/64という既存仕様に従い、試験元公開IP/VPN/proxyとUTC窓を対応づける。鍵/生digestは出さない。同窓の他試行との競合や10回上限を避け、観測不明は再試験とする。`/api` 自体はIPを消費する機能がないため、IP上書きの動作実証は `/api/auth/*` で行う。`/api` はFunction実関連付け/同一Function内容をAWS metadataで照合し、404だけでIP上書きを実証したと主張しない。製品診断APIは追加しない。
6. Web roleで実保護対象への権限拒否を以下の表のとおり確認する。fixtureの拒否だけを実対象の証明とせず、NotFound/通信障害/想定外応答は失敗とする。

| action / 主体 | 実保護対象・対照 | 合格条件と安全策 |
|---|---|---|
| GetSecretValue / Web task role | operatorが存在を確認した実RDS管理secret ARN | AccessDeniedのみ。想定外に取得できても本文を保持/出力せず直ちに破棄し失敗 |
| PutSecretValue / Web task role | 実application secret、B6の既存version UUID | operatorが同UUIDの現存と唯一のAWSCURRENTを直前照合。ClientRequestTokenを**そのUUIDに固定**し、実値と異なる公開の試験文字列をSDK内部から送り、新UUID/VersionStages変更は不可。AccessDeniedのみ合格。既存versionは変更不能というAWS契約を利用し、許可されても新versionを作らない。想定外応答は失敗、前後version metadataもoperatorが照合。独立した正常権限fixtureで同token/異値が不変になることを先に検証し、未検証なら実対象試験をnot_runとして止める |
| S3 Get/Put/Delete / Web task role | 存在確認済みの対象media bucket内、images/外の専用fixture key | AccessDeniedのみ。fixture作成/意図せぬ変更時の除去はoperatorが承認範囲で扱う。images/内の専用keyには正常操作も確認 |
| SQL / fitlog_app | 実管理role・bootstrap marker table | SET ROLE/marker SELECTのpermission denied。CREATE DATABASEのようにtransaction内で権限と無関係に失敗するSQLを拒否証明に使わず、危険なrole作成/変更の実試行はしない。属性/catalog不許可を併用 |

operatorは実保護ARNと非秘密version UUIDをAWS正本から導出し、照合済み固定引数としてverifyへ渡す。任意対象の探索/選択機能は作らない。freeze中は別経路secret rotation/削除を禁止し、metadata変化時は試験を中止する。実対象への試験に安全な条件が揃わなければ、定義検査済み/実評価not_runを分け、verifiedへ進めない。

`backend/operations/deployment_verify.py` は固定catalog/TLS接続・非秘密boolean出力・専用fixtureのS3操作・上記拒否検査に限定。任意SQL/自由なsecret ARN選択は不可。公開後のverifyもdeployment_stepの固定stepとして実行し、結果の全項目が合格した時だけ完了eventを出す。Web強化の製品変更が必要なら設計差異として相談する。

## 5. 撮影・破棄・再構築

- 2利用者の認証→profile→投稿→画像→交流→logoutをローカル動画保存、再生/必要UIの写り確認。source/digest/runに対応づける。AWS console/terminal/認証情報は撮影しない。外部公開は別承認。
- データ削除の対象一覧を示し実承認後、distribution disabled/Deployed・service0・one-off STOPPEDを確認。S3/ECRの完全な対象一覧（version/delete marker/multipart含む）と証跡保全を照合して内容を削除。force_destroy/force_deleteなし。
- `allow_database_teardown`（default false）を追加。trueはpublic=false/service=falseを必須とする。停止後、既存RDS保護属性だけを変更するplanを確認しapply、実属性falseを待って通常destroy。snapshot保持/秘密非管理方針は維持。
- final snapshot/retained backupは通常destroy後も残る。事前採取DbiResourceId/final snapshot ID/account/environmentに照合し承認済み別工程で削除。RDS/ALB/Fargate/ENI/CloudFront/S3/ECR/logs/IAM/VPCの残存をAPIで確認。stateだけで課金停止を断言せず削除不能対象と見込み費用を記録。
- application secretは7日削除待機を維持しforce-deleteしない。名前再利用制約、削除予約日/予定日、期限後消滅確認を記録。AWS公式では削除予約中secret自体は非課金、snapshot/backup費用とは区別。
- 再構築は新environment suffix・新state・新bootstrap UUID・新snapshot名。同じソース/成果物を新ECRへ送信しdigest再照合、基本動作/境界試験から再破棄まで再現。旧stateも秘密保管し残存を追跡。既存データrestoreは対象外。
- 環境破棄/非課金secret削除待ち/後日の請求照合を別状態で報告。請求反映遅延があるため即時請求ゼロを成功条件にしない。

## 6. ローカル検証・反証

Highリスク。承認後、実装前に `docs/superpowers/plans/2026-11-06-fl-09b7-test-design.md` を作る。

| 上位リスク/不変条件 | 独立oracleと検証 |
|---|---|
| 誤account/対象/順序の変更・公開・削除 | 本書§1/3/4/5とAWS公式仕様。SDK Stubber/偽CLIで誤ARN・タグ不一致・期限切れ・順序飛越・偽endpoint・pagination循環・応答欠落を注入し変更API未呼出しと停止を確認 |
| 管理権限のWeb流入・秘密漏洩 | B6契約とIAM action/resource完全期待値。Terraform mock/Python独立検査でrole分離・未投入secretなしの起動・Web管理権限なしを確認。秘密入りSDK例外fixtureがstdout/stderr/証跡に漏れないこと |
| 再実行の重複/データ破壊・偽完了 | seed初回/一致/衝突/rollbackを専用PG17で確認。RunTask応答喪失・STOPPED非0・exit欠落・timeout・digest不一致・migration失敗で後段未実行と状態不変を確認 |

通常11 checksは共通git-dir照合後 `python3 -B scripts/run-checks.py`。共有runtime/production image検証はfitlog-runtime.lock内。専用container/network/label、host portなしで追加検証し他担当資源を変更しない。seed/verifyは既存pytest/型/lintへ乗せる。Terraform fmt/init readonly/validate/mock/Python/FunctionはB統合済み共通入口。ゲート回帰も行いsnapshot/実結果を保存。

ローカル成功は実IAM/RDS/経路/課金を証明しない。今回実AWS/E2Eはnot_run。品質レビューは機械チェック成功後に規定の統合・反証QA・security最大1席。追加試験はtest-recommendationで判断する。

## 7. 短い実装計画

0. 設計承認後にIssue/番号付きbranch、担当依存記録、test-design。
1. manifest/工程/証跡のpure処理をTDD。既定local-only・非漏洩・失敗停止を固める。
2. Terraformへbootstrap task/専用IAM/logs/outputs/DB保護解除入力。Web権限・service0/distribution無効の独立期待値で回帰検証。
3. deploy補助、deployment_step/demo_seed/deployment_verifyを実装。SDK境界と専用PG17/production imageで再実行・権限・非漏洩を検証。migration正常終了のevent、子失敗時のevent禁止、他run/task event拒否、ログ未着/期限切れ、operatorとWebのguard分離、既存secret version固定token試験の無変更を反証テストへ含める。
4. `docs/fl-09b7-deployment-design.md` / `docs/fl-09b7-deployment-runbook.md` / `docs/fl-09b7-aws-approval-template.md` とterraform README。実コマンド/成功条件/失敗再開を対応づける。
5. B統合後にmain取込み/共通進捗文書更新。同snapshotで11 checks＋Terraform/追加検証→quality-check→commit/通常push/PR。相互レビュー待ち停止、対象PR対応指示後に再検証し通常統合条件へ。
6. 実AWSは§8の具体的な別申請。今回の承認だけでは実行しない。

設計Sol/high 1体（通常1巡）、実装委譲0体、品質初回最大3体Astra/highを想定。仕様/設計/短い計画をまとめて独立レビューし一度承認する（個人運用優先）。

## 8. 実AWS承認時に具体化する必須値

未確定account/資格を推測せず会社設定を探索しない。次の値を実行前に一括提示する。

- 本人専用12桁account/実行role ARN、東京、利用可能2AZ、PG17 minor/class/CA、SG quota/prefix list。
- 2構築分のenvironment/state保存・backup先（秘密0700/0600）、source/digest、UUID、resource inventory、対照distribution/権限fixture。
- 最新単価×数量/稼働時間/転送量。ローリング最大2task・one-off・IPv4・ALB/LCU・RDS・S3/ECR/log/secret/API・snapshot/backup・税/為替/余裕を含む2構築分総額上限。free tierは保証しない。
- 開始/停止期限・最大公開時間・予算超過前停止判断・通知はhard capでない点・退避/連絡先。金額/日時未入力では実行不可。
- 一時公開/signup・HTTP origin区間・対照資源・migration/seed・データ消去・RDS保護解除/snapshot/backup削除・2構築/破棄を明示。
- 残すローカル映像/証跡/秘密state、削除待ちsecretの後日確認担当/日時、残存費用の上限/期限。

数値見積りは未作成。期間/上限未指定のためローカル実装承認を課金許可と解釈しない。

## 9. 根拠（2026-11-06確認）

- B6設計/runbook、B4 runtime設計、terraform/runtime.tf・iam.tf・database.tf・secrets.tf・outputs.tf、backend/operations/*、OpenAPI/既存APIテスト。
- [ECS RunTask](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_RunTask.html)
- [Task IAM](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html)
- [ECS認可表](https://docs.aws.amazon.com/service-authorization/latest/reference/list_ecs.html)
- [Terraform targetの例外用途](https://developer.hashicorp.com/terraform/tutorials/state/resource-targeting)
- [RDS保持backup](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_WorkingWithAutomatedBackups.Retaining.html)
- [Secrets Manager削除待機/料金](https://docs.aws.amazon.com/secretsmanager/latest/userguide/manage_delete-secret.html)
- [PutSecretValueの既存version不変契約](https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_PutSecretValue.html)
- [CloudWatch Logs読取り権限](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/permissions-reference-cwl.html)

## manifestの運用境界

下書き検査・保護stateの参照とhash照合・工程別承認一覧の強制を提供する。承認referenceやstepsは人間の実承認を暗号的に証明するものではない。operatorは実承認を正しく転記し、state/planの意味とAWS正本の対象を照合する。実AWSモードの明示opt-inと実AWSの別承認を必要とする。

