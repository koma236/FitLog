# FL-09B3 公開入口のTerraform定義（承認済み）

2026-11-06、ユーザーが設計・独立レビュー結果・圧縮無効案・短い実装計画を「はい、承認します」と承認。Issue #42、実装branch `feat/fl-09b3-edge-42`。

## 目的と作業境界

FL-09B2の閉じた基盤に、CloudFront・S3 OAC・ALBと空のtarget groupを追加する。成果物はAWSへ接続せず検証できる構成定義とmock planテスト。ECS/RDS・秘密/CA注入・配置・migration/seed・Terraform CI組込み・AWS実検証は後続とする。公開入口はruntimeとは独立に検証でき、CloudFrontのdomainとtarget group ARNを後続へ渡せるため、この単位で分割する（親の提案）。アプリ稼働や公開の完了とは扱わない。

- worktree: `/Users/saki/project/FitLog/.worktrees/fl-09b3-design`
- 準備branch: `prep/fl-09b3-design`、baseline: `1b43bf68268aba33f8bb01f8f1ee57306178a989`
- writerは親セッション1つ。製品コードの委譲なし。既存worktree・共有Compose/DB/imageには設計中触れない。
- 先行FL-09B1/B2は統合済み。2026-11-06のGitHub確認でopen PRなし。旧v9のIssue #25は再開しない。
- 承認後にIssueを作成し、その番号で `feat/fl-09b3-edge-<issue>` へ改名する。

## 選択肢と承認する判断

既存草案に沿い、CloudFront既定ドメイン＋public ALBのHTTP originを提案する。ブラウザ→CloudFrontとCloudFront→S3はHTTPS、CloudFront→ALBとALB→将来taskはHTTPであり、全区間TLSではない。prefix listと秘密headerはアクセス制御であり通信の暗号化を代替しない。実ユーザーのデータを扱う常設運用へ拡張する際はこの前提を見直す。

比較案はinternal ALB＋CloudFront VPC origin（公開originをなくせるが、既存B1の境界とネットワーク設計を変更する）と、public ALBのHTTPS（ALB origin用のドメイン・証明書を追加設計する）。今回は独自ドメイン購入を要求しない既存方針と、短期デモに限定した既存草案を維持する。これらは今回初めて承認を求める具体案であり、過去の実装承認を流用しない。

## 入力と秘密

Terraform 1.15.1 / AWS provider 6.71.0 / 東京 / expected account境界を維持し、新providerを追加しない。

- 新入力 `origin_verify_secret`: nullable=false、sensitive=true、既定値なし。小文字16進数64文字だけを許可する。ALBのheader条件でwildcardになる文字も拒否する。実値の生成・取得は今回行わず、testでは公開fixtureを使う。
- 新入力 `enable_public_distribution`: bool、nullable=false、既定false。閉じたまま定義でき、実公開は後続の実AWS操作承認と検証の対象とする。今回trueでapplyしない。
- 秘密はCloudFront origin custom headerとALB listener ruleへ同じ値を設定する。output、ログ、公開example、通常environment変数へ書かない。Terraform sensitive指定はstate/保存planの暗号化ではなく、実操作時には平文の値を含み得るstate/plan/tfvarsを秘密として保護する必要がある。秘密値を取得するdata sourceは追加しない。

## network・ALB

- `aws_lb` はapplication / internet-facing / IPv4、既存public subnet2つ、既存ingress SGのみを使用。Host保存を有効化、無効headerをdrop、access logを有効化しない。idle timeoutは65秒。ALB名は環境名から32文字以内。
- AWS管理prefix list `com.amazonaws.global.cloudfront.origin-facing` を名前で取得し、そのIPv4リストだけからingress SGのTCP80受信を追加する。0.0.0.0/0、IPv6 CIDR、443やSSHの受信は追加しない。exclusive rule setへそのrule IDを組み込み、所有者を混在させない。prefix list weight55は1ポート分だけ使う（SG受信既定60枠との関係を実操作前にも照合する）。
- listener HTTP80のdefaultは固定403（text/plainの固定文）。1つの転送ruleで `X-Fitlog-Origin-Verify` が秘密に一致した場合だけtarget groupへ転送する。prefix listだけを自distributionの識別とは扱わない。
- target groupは同VPC / target_type=ip / HTTP8000。healthはGET `/api/health/live`、成功200のみ、interval30秒/timeout5秒/healthy2/unhealthy2。DBの未準備による全task再起動を避け、ready検証は配置工程で別に行う。target attachmentは今回ゼロ。後続ECS serviceが所有する。
- ingress→app8000、app→DB5432、appの443外向き、DB外向きなしは維持。taskへのCIDR受信・NAT・EIPは追加しない。

## CloudFrontと転送契約

distributionは独自aliasなし、既定証明書、HTTP/2、viewer IPv6可、default root object=index.html。公開フラグは上記入力に従う。retain_on_delete=false、wait_for_deployment=true。API originはALB DNSのHTTP80のみ（http-only、origin read timeout60秒）。S3 originはstatic bucketのregional REST endpointを使う。

| behavior | origin / methods | 転送・キャッシュ |
|---|---|---|
| default `*` | static S3 / GET, HEAD | 初版は静的もキャッシュ無効。viewerのCookie・query・headerを転送しない。API Functionなし |
| `/api` および `/api/*` | ALB / GET, HEAD, OPTIONS, PUT, POST, PATCH, DELETE | cached_methodsはGET,HEADだがTTLは全て0。viewer-requestに既存client-ip Functionを関連付け。origin request policyはallViewer headers / all cookies / all query strings |

cache policyは自前1つ、min/default/max TTL=0、cache keyにCookie/query/headerを含めず、gzip/brotli key設定false。全behaviorがこれを参照する。最適化より初版の認証・更新の安全性と固定契約を優先する（親の判断）。API origin request policyのallViewerでHost、Origin、Referer、X-CSRFToken、Content-Typeと専用IP headerを落とさない。APIのHostをALB DNSへ置換しない。全behaviorで圧縮を無効（compress=false）とし、viewer protocol policy=https-onlyを設定する。HTTPのPOSTをリダイレクト再送させず拒否する。

API origin custom headersは `X-Fitlog-Origin-Verify=<secret>` と `X-Fitlog-Forwarded-Proto=https`。CloudFrontがviewerの同名値を上書きするAWS契約を使う。client-ip Functionはruntime cloudfront-js-2.0、publish=trueの構成定義を作り、既存ファイルをそのまま参照する。公開・publish・associationのAWS API呼出しは今回行わない。Functionに秘密は含めない。既存のFunction変換testを維持する。

distribution全体のcustom error responseはAWS対応コード400/403/404/405/414/416/500/501/502/503/504でerror_caching_min_ttl=0だけを設定し、response_code/response_page_pathは指定しない。APIの401/403/404/5xxをindex.htmlや200へ変換しない。S3 originのerrorにはAWSの最小キャッシュ例外があるため、すべてのS3エラーが即時更新される保証とはしない。現frontendはhash routingなのでSPA rewrite Functionを追加しない。`/apiary`や欠落static assetはS3側のエラーのまま扱う。

## OAC・bucket policy・依存関係

- OACはs3 / sigv4 / signing_behavior=always。S3 website endpointとOAIは使わない。
- 既存bucket policyを単一所有のまま拡張する。staticだけにservice principal cloudfront.amazonaws.com、s3:GetObject、static bucketの `/*`、StringEquals AWS:SourceArn=今回distribution ARNのAllowを1件追加する。非TLS拒否はstatic/media双方へ維持。mediaのCloudFront grant、s3:ListBucketやwrite、public principal Allowは追加しない。
- Block Public Access4項目・BucketOwnerEnforced・AES256・force_destroy=falseを維持する。
- 依存はbucket/ALB→distribution→static policyとlistener rule。distribution側からstatic policyやlistener ruleへのdepends_onを張り循環させない。構築途中にoriginへアクセスできない時間を隠さず、実配置後の検証を別途必要とする。
- outputsへdistribution ID/ARN/domain、将来用HTTPS URL、target group ARNを追加する。秘密や稼働成功フラグは出力しない。既定は無効でtargetもゼロなので、URL出力が疎通を示さないことをREADMEへ明記する。

## 範囲・受け入れ条件

主な変更は `terraform/{edge,network,storage,variables,outputs}.tf` と `terraform/tests/`、Terraform README、今回設計、本番準備/インフラ/進捗文書。実装上の内部ファイル分割は任せる。backend/frontend/Compose/lock/CI/ハーネス/11 checks登録は変更しない。

mock planで次を固定期待値と比較する。policy JSONをmockの期待policyへ置き換えず、実生成Statement全体を検査する。computed ARN/ID/DNSは必要箇所だけplan時fixtureで確定する。既存testへ新しい必須secretのfixtureを渡し、B2の閉じた受信期待値を今回許可した唯一の受信へ更新する。mediaやIAMの契約は弱めない。

1. ALBのsubnet/SG/Host、唯一の受信prefix list名とport、exclusive rule数、listenerの拒否既定とsecret一致転送、targetの空・health設定。
2. behaviorが正確にdefault＋2 APIだけであること、両APIのFunction/全methods/全viewer転送、全TTL0とHTTPS限定、origin custom headers、staticへCookie転送がないこと。
3. OAC常時署名とbucket policy全Statementの完全一致、mediaへの追加grantなし、全public blockと破棄保全。error responseにstatus/HTML上書きなし。
4. secretの欠落・短い値・不正文字は拒否。公開フラグfalse/true両方のplanで有効状態だけが意図どおり変わること。秘密outputなし、state/plan/tfvars未追跡。

Terraform fmt/init(-backend=false、lockfile readonly)/validate/testはREADMEのenv -i方式でAWS資格情報を持たず実行。全runはmock_provider aws、override_during=plan、command=plan。AWS data sourceもmockし、real providerへfallbackしない。mockは実SG/IAM評価・header上書き・配信・health疎通の実証ではない。実AWSのplan/apply/destroy/import/account探索は禁止する。

後続ではECS/RDS/秘密/CA/CI・費用/期間/対象/削除の承認を整え、ALB/task直接経路・別distributionの偽装拒否、HTTPS/Host/CSRF/Cookie、利用者IPの分離とrate limit、S3非公開を実証してから公開する。今回アプリのFITLOG_TRUST_PROXY/cloudfront IP modeを有効化しない。

## 短い実装計画

1. 承認後Issueと番号付きbranchを整備。High（公開経路・IAM/bucket権限境界）としてtest-designで期待値と反証入力を先に記録する。親が実装する。
2. 上の契約のmockテストを追加し、失敗確認後にedge/network/policy/outputを実装。既存基盤testとFunction testも通す。
3. 文書の実装済み/未実施を更新し、Terraform fmt/init/validate/test、Function test、ゲート回帰を実行。個人用run-checks手順の共有runtime排他で登録11 checksを実行し、日時・終了コード・snapshotを保存。
4. 機械チェック合格後quality-checkで統合・反証QA・Security（目安3体）を実施し、Highを対応。設計レビュー1体、実装委譲0体、品質初回3体が目安。追加巡は規定に従う。短い計画は本書に一体化する。
5. 個人account/repo/SSH照合後commit・feature push・PR作成。公開経路は既存認証の信頼境界を構成するため、高リスクの手動相互レビュー対象として「相互レビュー待ち」で止める。CI/ゲートは変更せず、実AWSへの反映も行わない。

## 原典（2026-11-06照合）

- [CloudFront→ALBのheader・prefix list制限](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/restrict-access-to-load-balancer.html)
- [AWS管理prefix listのweightとquota](https://docs.aws.amazon.com/vpc/latest/userguide/working-with-aws-managed-prefix-lists.html)
- [OACとdistributionを限定するS3 policy](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html)
- [origin custom headerはviewerの同名値を上書き](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/add-origin-custom-headers.html)
- [CloudFrontのbehavior・HTTPS/method/TTL](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/DownloadDistValuesCacheBehavior.html)
- [AWS provider 6.71.0のALB属性](https://github.com/hashicorp/terraform-provider-aws/blob/v6.71.0/website/docs/r/lb.html.markdown)、[distribution属性](https://github.com/hashicorp/terraform-provider-aws/blob/v6.71.0/website/docs/r/cloudfront_distribution.html.markdown)

## 独立設計レビュー

2026-11-06、helm-doc-reviewer（gpt-6.1-sol/high）による読取りレビュー1体を実施。High 0、Medium 1。Terraform依存方向、Host/CSRF/IPの転送契約、OACの限定grant、既存testの更新範囲は整合するとの評価。テスト・AWS操作は未実施。

- Medium：cache policyのgzip/brotli key設定falseに対して全behaviorの圧縮を有効化する指定は整合しない。[AWSの自動圧縮手順](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/ServingCompressedFiles.html)と照合した。未修正の承認判断として、初版はTTL0とkey設定falseを維持し、全behaviorのcompressもfalseに揃える案を提示する。2026-11-06のユーザー承認によりこの案を採用し、実装開始前に本書の該当契約を更新した。再レビューは行っていない。

レビュー台帳はdesign予約2枠を消費。最初の枠 `b0a3cb967e2bae8994df00a36d6ef23f` は公開APIで事前受付したが、bridgeがmessageをhookへ渡さず、native起動はmarker欠落として拒否された。実際のreviewerは起動していない。この枠は返却・改変していない。2枠目 `85f070daec1f81a3a649df10f4affca1` ではharness-runtimeのbridge形式task_nameを使用し、native起動前のused/receiptと起動後のagent記録を確認した。実レビュー起動数は目安どおり1体。追加レビューは予約していない。

上記判断とレビュー結果を併記したユーザー承認を受け、実装へ進む。

## 実装時の差異

なし。圧縮無効への更新は実装前にユーザーが承認した判断を反映したもの。
