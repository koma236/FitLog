# AWS B 配置・初期化・引継ぎ設計（承認済み）

2026-11-07。Issue #59、branch `feat/aws-deployment-59`。
唯一のwriterはB親セッション。worktree `/Users/saki/.codex-personal/worktrees/5034/FitLog`。
baseline `4524ec2965f6ac46815815555942bd4deda87058`（PR #56/#57統合済み）。
2026-11-07、ユーザーの「承認します」により本設計・独立レビュー結果・短い計画を承認。ローカル実装・検証へ進む。実AWS接続は別承認であり禁止を維持する。

## 1. 目的・所有範囲

既存CLIを使い、同じsourceのimage/staticからbootstrap→migration→seed→稼働確認までを追跡し、Cへ試験可能な状態を引き渡す。実配置成功は後日の実AWS証跡だけで判断する。

| 担当 | 所有・責任 | Bとの契約 |
|---|---|---|
| A #58 / 784f | terraform/**、scripts/prebilling/**、費用・実AWS申請。AWS変更operatorはAのみ | account/role、region、environment、選択した非秘密outputs、state参照/hash、操作期限・予算・排他枠を供給。B手順のpush/static/task実行・停止もAが行う |
| B #59 / 5034 | scripts/deployment/**、backend/operations/**、関連deployment/bootstrap/demo_seedテスト、docs/aws-b-*.md、既存B6/B7 runbook | 成果物記録、配置CLI、工程証跡、Aへの操作手順、Cへの引継ぎ |
| C #60 / e865 | e2e/**、perf/**、撮影・受入文書 | exact HTTPS originとB証跡を受領。公開health API・ブラウザ/API境界・性能・撮影を実証し、Bのremote verifyを再実装しない |

Terraform/IAM変更はAへ要求しBは編集しない。CI/制御面/Compose/既存lock/OpenAPI/製品認証認可/DB migration/共通README等は対象外。A/Cや旧worktreeの編集・操作・片付けを行わない。
ローカル実装の統合はA→B→C。準備・fake検証は並行可能、A統合後にBで通常取込みと契約回帰を行う。未統合Aの成果をBの合格根拠にしない。

## 2. 既存実装と追加が必要な部分

再利用する正本:

- `deployment_contract.py`: strict manifest v1、draft専用検査、期限/工程承認、保護state照合、原子的な証跡v2。
- `deployment_cli.py`: run identity/binding、先行工程、固定command、RunTask前intent、collect-only、失敗task停止・STOPPED確認。
- `deployment_aws.py`: account/tags/DB/task/role/secret/公開段階照合、実task digest/exit0/同stream完了event収集。
- `deployment_assets.py` / `bundle.py`: 全static inventory、送信直前hash検証、対象bucket限定・削除なし。
- `bootstrap.py` / `aws.py` / `database.py`: 初期化UUID、永続claim/advisory lock、TLS、非管理者role、秘密の安全な再開。
- `deployment_step.py` / `demo_seed.py` / `deployment_verify.py`: 固定工程、DB identity/TLS、seed衝突rollback、権限/IP観測。

不足は (1) clean sourceとimage/staticの対応がrunbook依存、(2) service台数だけでは旧task/rollback/ALB不健全を除外できない、(3) static・health・C引継ぎ証跡の共通対応づけが不足している点。bootstrap SQLや製品機能を再実装しない。

## 3. 成果物の作成と拘束

親の設計判断: 新依存を追加せずPython標準ライブラリ・既存boto3・既存Docker/npmを使う。汎用パイプラインは作らず、既存buildコマンドをAの手順として残し、Bは照合器を加える。

1. Aは最終統合後の承認sourceをclean checkoutで確認。tracked/index/untracked差分なし、HEAD=40桁sourceを必須とする。ビルド元は同commitの`git archive`をrepo外の専用0700作業directoryに展開したものとする。Git管理ファイルだけを含み、.git・ローカル資格/state/.envをDocker contextへ入れない。submodule/LFSがあれば本手順の対象外として停止する。export後のsourceを編集しない。
2. 同exportでlock済みfrontend buildと既存production Dockerfileのlinux/amd64 buildを行う。revision labelを必須とし、push前はローカル専用tag/image IDとplatform/labelを記録。Dockerfile/lockを変更しない。ビルドログや環境変数全体を証跡へ転記しない。
3. 既存bundle関数でstatic inventoryを生成。Aの実操作承認後、対象ECRへimmutable tag `<source>-<run UUID>` で送信しDescribeImagesのdigestを確認する。local image IDとregistry image digestは別項目とし同一視しない。buildxのindex/attestationによるdigest混同を避け、送信手順はsingle-platform・provenance無効で固定し、ECSで実際に観測したdigestも照合する。
4. 新しい `scripts/deployment/artifacts.py` と `backend/operations/deployment_artifacts.py` にオフライン照合器を置く。入力はローカルbuild記録・manifest・assets inventory。既定は読取り/照合だけでbuild/push/AWS接続なし。任意shell/endpoint/秘密を引数にしない。
5. artifact record v1は厳密なallowlist: schema_version/run_id/source_revision/source_tree、backendのrepository/tag/local_image_id/registry_digest/platform/revision_label、frontend_sha256、開始終了UTC、build command種別と終了コード。source_treeはGit tree OID。recordは保護directory内0600・排他的作成。未知key、実行失敗、label/source/tag/account/environment/digest/inventoryの不一致を拒否する。
6. `deploy.py --artifacts <record>`をAWSモードの必須入力にする（draft/既存offline manifest検査は互換維持）。recordとmanifestのrun/source/image/frontendを照合してからGatewayへ接続する。inspectで対象ECRのregistryId/repositoryName/tag/digestをAWS正本と照合する。staticはローカル全inventoryも再照合する。recordは人間の承認や改ざん耐性のある署名を代替しない。source tree/build結果の真正性はAの同一排他枠での実作成と照合記録が根拠。

成果物recordにstateやsecretを追加しない。manifest schema v1と既存identityの計算は維持する。既存AWSモードの呼出しは新flagが必要になるため、所有runbook/全fixtureを同時更新しA/Cへ引継ぐ。draftのA側readinessを壊さない。

## 4. 工程・稼働確認

private: inspect→static→bootstrap-inspect→bootstrap→migrate→seed→check。
bootstrap→checkの先行証跡・固定command・UUID・claim/lock・DB role/TLS・seed完全一致no-op/衝突rollbackは既存を維持する。新規schema migrationなし。

- static成功記録を現状のmanifest hash/statusだけからrun/source/image/frontend/identity/UTCを含む専用version付きrecordへ変更し、全put成功時だけ原子的保存。失敗はpartialの可能性を残して後段へ進めない。同じ閉鎖環境・同一inventoryの再送だけAが照合して行える。削除/sync --deleteは追加しない。
- bootstrap-inspectの前に同runのinspect/static成功を要求する。staticにもinspect成功を要求する。private inspectの再照合は既存同一証跡を上書きせずattempt記録を分ける。
- Aがservice/proxy=true、public=falseを適用し新task revision/state hashを反映後、`inspect --phase backend`を実行する。先行check成功、既存preflightに加えて下記healthを要求。成功は既存STEPSの`backend`として記録し、private inspectの記録と衝突させない。
- `verify --phase backend --mode database`相当の既存verify-inputでDB/TLS/migration検査。backend phase verifyにbackend成功を要求。Aが公開試験を許可してdistributionを有効にした後は、`inspect --phase public`を再実施し`public-health` recordを別保存。public phase verifyにはこの成功を要求する。
- inspectは既存approval.steps=`inspect`で許可する。public-healthは新しい証跡stepだけで、新しいAWS操作許可stepは増やさない。公開をCLIから切替しない。manifest/schema/phase/期限/state/必要recordを接続前に検査する。

healthはoperator側read-only処理として既存adapterに追加する。900秒上限、3秒間隔、毎回期限照合。既存preflightの検査を「対象・認可の即時拒否」と「稼働状態の待機」に分ける。backend/public inspectの待機前に現行preflightの1/1/0要求をそのまま呼ばない。account/ARN/tags/network/role/secret/成果物とserviceの設定task revisionの不一致、期限切れ、rollout FAILED、SDK例外は即失敗とする。期待service設定への更新後、台数不足・新旧deployment併存・旧taskの終了待ち・target未登録/initial/draining/unhealthyは進行中として期限まで再観測し、成功条件を緩めない。private工程の0/0/0即時拒否は維持する。成功条件は次の全件。

1. service ACTIVE、desired/running/pending=1/1/0、deploymentが期待task revisionのPRIMARY 1件だけ、rolloutState=COMPLETED。
2. 対象serviceのListTasks/DescribeTasksがRUNNING 1件、期待task revision・backend container・manifest digestと一致。全paginationを処理し循環token/欠落/余分taskを拒否。task ENIのprivate IPv4を照合に使用する。
3. service.loadBalancersの唯一のtarget groupがbackend container:8000。DescribeTargetGroupsで同じALB/VPC/IP target/HTTP8000、既存health path `/api/health/live` を照合。DescribeTargetHealthで登録targetがそのtask private IPv4:8000 1件かつhealthy。
4. distributionは期待ID/ARN/tags/API originでDeployed、backendはdisabled、publicはenabled。domainをAWS metadataから取得し`https://<domain>`だけをCのexact originにする。任意URL、userinfo/port/path/query/fragment、redirect許容はしない。

ALB live合格はDB readinessを証明しない。既存database verifyを併用し、公開HTTP `/api/health/ready` とbody/version等の実証はCが行う。BはCloudFrontへHTTP送信せず、公開経路全体をB単独で合格としない。

## 5. A/Cの入出力と失敗時の契約

Aへ要求する追加権限はoperatorの既存権限との差だけ: ECR DescribeImages、ECS ListTasks/DescribeTasks、ELB DescribeTargetGroups/DescribeTargetHealth（既存DescribeServices等は再利用）。task/Web/bootstrap roleへ新権限を付けない。target group ARNとdistribution.urlは既存Terraform outputに存在するため新outputは原則不要。IAM定義/権限根拠はAの所有。

`scripts/deployment/handoff.py`はオフライン専用の集約器。manifest/artifact/static/工程/health/verify証跡を読み同一run/source/digest/frontend/identityを照合し、C向けの非秘密handoff v1を生成する。保存先0700/0600・原子的排他作成。success=実AWS完了ではなく、明記した証跡の集約結果。

必須欄はaccount/region/environment、run/bootstrap UUID、source/image/frontend hash、record参照とhash、exact origin、backend/seed/check/database/公開healthのpass、A指定の試験開始・終了UTC/承認参照。試験窓はapproval期限以内。state本文/plan/秘密/ログ全文/生IP/credentialは出力しない。handoffにはstate pathを含めず、保護manifest参照hashだけを置く。

公開permissions/IP probeはA operatorの制御下でCと時刻を合わせる。handoffの初期状態は`ready_for_c`であり`verified`ではない。permissions/IP未実施はnot_runとして明示しCの総合合格を禁止する。Cのブラウザ試験・撮影結果や承認回数をB側で生成しない。

入力ファイルは正規path・非symlink通常file・実行者所有・0600/0400、親0700を検証する。hashは混在/変更検出用であり実承認の証明ではない。不足/失敗/別run/古いtask/source違いはfailとし、passへ補完しない。

応答不明時は既存intentを保持し新RunTaskを禁止。Aが対象taskを正本から特定し既存collect-onlyを使う。成功recordを別runへコピーしない。bootstrap UUIDは同環境の復旧で維持、新環境再構築では新run/state/environment/bootstrapを使う。migrationのfake/reverse/resetとseed自動修復は禁止。先行工程からやり直せない既存環境の復旧は別途状態に合う計画が必要で、自動的な新run開始で回避しない。

失敗時のCloudFront閉鎖・service停止・残存task確認はAだけが承認済み退避を実行。Bは失敗結果/対象/停止要求を返す。未知原因・期限切れ・停止未確認は先へ進めない。実AWSの費用/期間/2構築/削除の申請はAの別承認、今回の開発承認では実行しない。

## 6. 独立oracleと検証計画

Highリスクとして扱う。既存AWS認可・bootstrap契約を変えず、誤配置/偽合格/秘密漏洩を反証する。実装前にtest-design/TDDを適用する。

| 不変条件 / oracle | 正例と独立負例 |
|---|---|
| clean source・固定成果物（本書§3、Git tree、既存Dockerfile/lock） | 正しいrecord、dirty/untracked、別commit/tree/label、local IDとregistry digest取り違え、改変static、追加key、build非0。AWS未呼出し |
| 工程順（本書§4、既存B6/B7契約） | 全工程、inspect/static欠落、別run、前段fail、task revision更新後の同identity、public-health欠落、collect-onlyの再起動0 |
| 稼働判定（ECS/ELB公式API、live/ready実装） | 完了service＋同digest task＋同ENI target。fake時系列で起動中0/0→1/0/1→1/1/0、ローリング中の新旧併存→新taskのみを確認。rollback FAILED/異ALB/VPCは即失敗、旧task/余分task/不健全・空targetが解消しなければ期限失敗。fake clockで待機上限と変更API0 |
| secret非漏洩（既存固定event境界） | SDK/SQL/CLI失敗fixtureへ秘密sentinelを入れstdout/stderr/全証跡に存在しない。raw API内容をhandoffしない |
| 引継ぎ（本書§5） | 同一証跡一式、別environment/source/digest/frontend、origin差異/欠落、窓の期限超過、symlink/所有権/権限不正、失敗recordを拒否。permissions/IP未実施はnot_run |

承認後のコマンド: `python3 -B -m unittest discover -s scripts/deployment -p 'test_*.py'`、関連backend pytest（deployment/bootstrap/demo_seed）、通常11 checksは `python3 -B scripts/run-checks.py`、通常ゲート回帰2本。全checks/DB/buildは共通git-dir照合とfitlog-runtime.lockの排他運用、固定15173/18080、独自DB/port新設なし。全結果を対象commit/未commit snapshotと対応づける。
機械チェック後にquality-checkの統合/反証QA/必要securityを実施。追加テストはtest-recommendationで判断するが実AWS/E2Eは今回の開発承認で実行しない。高リスク相互レビューの対象判断は実差分で行い、対象ならPRを作って相互レビュー待ち停止。CI/制御面に拡張が必要ならA/Cの所有に無断侵入せず設計変更として相談する。

## 7. 短い実装計画（承認後）

1. 既存Issue/branchを継続し、成果物record・工程順・health・handoffの固定期待値と負例を先に作る。A/C契約は本書の入出力で固定し、新しいクラウド値は推測しない。
2. bundle/manifest/event collector/bootstrapを再利用しartifact照合→工程証跡→health→offline handoffをB所有パスだけで実装。B6/B7 runbookを実コマンド/失敗再開/唯一operator=Aに更新。
3. A統合後に通常取込み、output/task/IAMとの契約を回帰。共有runtime排他で11 checksと関連検証、quality-check・追加テスト判定・独立品質レビュー。A未統合ならfake検証済み/統合未確認を分ける。
4. 自担当差分だけcommit/feature push/PR、CI確認。相互レビュー等の停止条件を守り統合、Cへ証跡schema/試験前提を渡す。実AWS操作は別申請後Aが実施。

想定agent使用: 設計レビューSol/high 1体、実装委譲0体、品質初回は規定Astra/high最大3体。設計・短い計画は個人運用に従いまとめて一度承認を受ける。

## 8. 根拠・未実施

Issue #58/#59/#60、ローカル引継ぎ票、既存B6/B7設計/runbook・上記実装を確認。2026-11-07、公開公式文書の閲覧のみ実施（AWS APIではない）。
- https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_DescribeServices.html
- https://docs.aws.amazon.com/elasticloadbalancing/latest/APIReference/API_DescribeTargetHealth.html
- https://docs.aws.amazon.com/AmazonECR/latest/APIReference/API_DescribeImages.html

実装・build・テスト・実AWS・公開・撮影・性能・破棄はnot_run。金額/時刻/account/roleは未確定。CとAの独自設計が未統合のため、本契約案との差は統合前に調整し重大差異は再確認する。

## 9. 独立設計レビュー

2026-11-07、helm-doc-reviewer（gpt-6.1-sol / high）1体・design第1巡。review-budgetの予約とdocument-reviewer開始受付を確認した。設計と短い計画を上位担当契約・既存実装・Terraform・health実装から独立に照合。High 0件、Medium 1件、設計ゲート通過可。

- Medium: 起動中を900秒待つ設計と、現行preflightの台数不一致即失敗の呼出し順が曖昧。§4を対象/認可と稼働状態に分離する設計へ明確化し、§6に正常起動・ローリングのfake時系列を追加した（親の判断）。privateの停止要求と最終成功条件は維持する。
- Mediumへの明確化後の再レビューは行っていない。High指摘なしのため追加巡を消費しない。承認提示時に指摘とこの対応を報告する。
- このレビュー時点では実装・テスト・実AWSはnot_run。以後の実装・検証結果は実装レポートに記録する。ユーザーの設計承認は本文冒頭に記載。
