# FL-09B7 実AWS操作の申請書

関連: Issue #52、[設計](fl-09b7-deployment-design.md)、[手順](fl-09b7-deployment-runbook.md)。
本書は申請様式。**未記入のまま実行不可**。実装の承認をAWS操作の承認へ読み替えない。

| 項目 | 実行前に記入する内容 |
|---|---|
| account / operator | 個人専用12桁account、STSで照合するrole完全ARN。既存の共有/会社資格を使わない |
| 配置先 | ap-northeast-1、実利用可能な2AZ、PG17完全minor/db.t4g.micro/CAの提供確認、prefix-list/SG quota |
| 対象 | 初回/再構築の異なるenvironment名、各resource ID/ARN、snapshot ID/DbiResourceId、bootstrap UUID、source commit、ECR digest |
| 秘密の保管 | state/tfvars/保存plan/バックアップの絶対pathと0700/0600保護、保持期限、アクセス担当。秘密値を申請へ貼らない |
| 期間 | UTC/JSTの開始、最大公開時間、停止期限、再構築の期限、残存確認日と担当 |
| 上限 | 2構築分のUSD見積りと上限、JPY参考額の為替/税/余裕、残存費用の上限・許容期限 |
| 単価根拠 | 実行日にAWS公式料金表/Calculatorで確認。free tierを前提にしない |
| 数量 | Fargate通常1/更新最大2/one-off、public IPv4、ALB+LCU、RDS+20GiB+backup/snapshot、S3/ECR/log/secret/API/転送量、対照distribution/fixture |
| 公開 | CloudFront既定ドメインの一時公開、public signup、origin区間HTTP、試験成功後のURL共有範囲。動画外部公開は含めない |
| 変更 | ECR限定初回作成、image/static送信、専用IAM/runner、初期化/migration/seed、service/proxy/public切替、障害時distribution無効化/service0 |
| 破棄 | デモDB/画像/static/ECR/対照fixture削除、RDS保護解除、通常destroy、final snapshot/保持backup削除、2回目構築と再破棄 |
| 残すもの | ローカル映像/非秘密証跡/秘密state。7日削除待ちsecretの消滅予定日と後日確認。既存共有資源は対象外 |
| 停止判断 | 期限/見込み費用上限に達する前の停止担当・退避・連絡先。Budget通知はhard capではない |

費用の数値が現時点未定なのは、実行期間・account・上限が未指定のため。ローカルmock/CI成功で費用・経路・権限の成立を推定しない。

operator権限は本環境のTerraform構築/配置権限とは別に、対象cluster/task定義へのRunTask/DescribeTasks/StopTask、必要role完全ARNへのiam:PassRole（iam:PassedToService=ecs-tasks.amazonaws.com）、対象Web/bootstrap streamのlogs:GetLogEvents、対象サービスmetadataのDescribe、対象S3/ECR配置、前後secret version metadata照合を要する。metadata fixture作成権限/後始末も列挙する。Web task roleを広げて代用しない。
