# FL-09B1 認証レート制限のプロキシ境界

2026-11-04、独立設計レビュー結果・本計画を提示し、ユーザーが「はい、よいです。お願いします。」と承認。Issue #30、実装branch `feat/fl-09b-client-ip-30`。

## 現状と目的

baseline `1b32d4d`。FL-01〜08、CI-01、FL-09A（#28 / PR #29）はmainへ統合済み。TerraformはREADMEだけで、AWS実配置・撮影・再構築は未実施。`docs/task-plan.md`の実装順と受け入れ条件の完了表示は古いため、今回確認できた製品進捗を追記する。旧v9履歴は変更しない。

現在signup/loginはREMOTE_ADDRを固定窓のキーにする。ALB配下では利用者が同じ枠を共有し得る。公開前条件のうち、信頼済み経路から受け取る利用者IPの選択・検証と送信側Functionを今回整備する。AWS実経路を検証したとは扱わない。

## 契約

- 新設定 `FITLOG_AUTH_CLIENT_IP_SOURCE` は `remote_addr`（既定）または `cloudfront` のみ。不明値は起動拒否。localではremote_addrだけを許可する。cloudfrontはproductionかつ既存 `FITLOG_TRUST_PROXY=1` の場合だけ許可する。HTTPS判定の既存設定は維持する。
- remote_addrは従来どおりREMOTE_ADDRのみ使用し、すべての転送ヘッダを無視する。
- cloudfrontは `X-Fitlog-Client-IP` の単一IPリテラルのみ使用する。欠落・空・過長（45文字超）・空白・カンマ・port・zone ID・不正IPを503で拒否し、REMOTE_ADDRやX-Forwarded-Forへfallbackしない。既存の共通エラーを使い、新しい公開エラーコードは追加しない。
- 選択したIPは既存 `ip_network` でIPv4 /32、IPv4-mapped IPv6はIPv4、IPv6 /64に正規化しHMAC化する。signup/loginで同じキーを共有し、60秒内10回、11回目429とRetry-After、DB UPSERT/autocommitの契約を維持する。
- CSRF・method検査の既存順序を維持する。有効なCSRFを持つ認証POSTでIP不正なら、カウンタ更新・password hash・ユーザー作成より前に拒否する。生IP・ヘッダ・秘密をログやエラー本文へ出さない。
- `terraform/functions/client-ip.js` にCloudFront Functions runtime 2.0のviewer-request用コードを置く。`event.viewer.ip`から専用ヘッダのオブジェクト全体を置換し、利用者が入れたvalue/multiValueを引き継がない。URI/body/cookies等は維持し、ログ出力しない。Functionのpublish/associationは今回行わない。

## 信頼境界と範囲

ヘッダだけでは送信元の真正性を検証できない。cloudfront設定の有効化は、後続IaCで以下を満たし、実AWSで検証した後に限る：自分のdistributionのAPI behavior全体へのFunction関連付け、専用ヘッダのoriginへの転送、APIキャッシュ無効、CloudFront origin-facing prefix listと秘密origin headerによるALB制限、ALBからだけ到達できるtask SG、HTTPS強制・専用protoヘッダ上書き。別distribution・ALB/task直接経由の偽装も拒否されることを確認する。現在の既定設定では専用ヘッダを信頼しない。

Terraformのネットワーク/IAM/RDS/S3定義、apply、公開、課金、IPのraw記録、多IP攻撃対策、窓方式の変更、UI変更、DB migrationは範囲外。VPN等を経由した場合はCloudFrontが観測した接続元が単位になる。

## 実装と検証計画

1. 承認後にIssueを作成し、準備branchを番号付きfeature branchへ改名する。writerは親セッションのみ。worktree `/Users/saki/.codex-personal/worktrees/5db0/FitLog`、準備branch `prep/fl-09b-client-ip`。先行PR #29はmerge済み。
2. 認証・セキュリティ設定変更のためHighリスクとしてtest-designを記録し、設定検証・IP選択・認証POSTの失敗/分離テストを先に追加する。変更対象はbackend/configの設定、accountsのIP選択と呼出し、対応tests。DB/APIスキーマ・lockfileは変更しない。
3. FunctionとNode標準testを追加する。固定viewer IPv4/IPv6、偽装専用ヘッダとmultiValueの上書き、その他requestフィールドの維持を独立期待値で確認する。
4. APIテストでは同じREMOTE_ADDRの異なるIPv4利用者を別枠、同じIPv6 /64を同枠、mapped IPv6とIPv4を同枠と確認する。両endpointの枠共有、転送ヘッダ変更による既定動作の不変、不正IPの無更新・非漏洩も検証する。設定テストは実production moduleを別processで読み込む既存方式を使う。
5. 共通git-dirのruntime leaseを取得し、既存migration状態を照合してから `.ai-dev/project.toml` の11 checksを親が登録argvで直接実行する。Function test、`node --test scripts/test-quality-gate.cjs`、本番image smokeも実行。開始前から動いているサービスを停止せず、今回のprocessだけを終了する。
6. ドキュメント（認証契約・production-readiness・terraform README・task-plan進捗）を更新し、機械チェック合格後にquality-checkの独立レビューと必要な修正を実施。証跡を保存してcommit・feature pushする。PR本文を完成させ、作成は最終報告で確認する。mergeは本人が行う。

## 原典

- [AWSの利用者IPヘッダ追加例](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/example_cloudfront_functions_add_true_client_ip_header_section.html)
- [CloudFront Functions event構造](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/functions-event-structure.html)：viewer.ip、header名の小文字、multiValueの仕様。今回ローカルで検証するのはFunctionの変換とアプリ側契約であり、AWS実関連付けではない。

## 独立設計レビュー

2026-11-04、helm-doc-reviewerによる独立レビュー1回。High/Mediumなし、Low 1件（リスク分類）。品質ポリシーに従いMediumからHighへ修正済み。既定互換性・fallback禁止・無更新での拒否・IP正規化・FunctionのmultiValue置換・実AWS検証との区別は既存契約およびAWS原典と整合するとの評価。レビュー時点では実装コードとテストは未変更・未実行。

起動受付の監査では、設計レビュー予約の `used` が空のままであることを確認した。独立レビュー結果とユーザー承認は存在するが、ハーネスの正式な起動受付の証跡とは扱わない。予約や結果への事後の付替えはしない。最終品質レビューでは起動前に公開受付APIで正規受付を行い、承認済み設計との一致も独立確認する。実AWSの未実施範囲は維持する。
