# FL-09B8 課金前の実行準備

最終更新2026-11-07、Issue #55。実AWSの申請・承認記録ではない。
[既存runbook](fl-09b7-deployment-runbook.md)と[申請様式](fl-09b7-aws-approval-template.md)を正とし処理・権限は変更しない。

## オフライン予行

scripts/prebilling/draft.jsonはregion以外のaccount/環境/資源/state/approvalをnullにした非秘密下書き。
`python3 -B scripts/prebilling/readiness.py`は既存CLIの`--draft`だけを実行しAWS資格を読まない。接続optionなし。
成功でもdraft_validation=pass / aws=not_run / approval=未承認 / readiness=未決。未知key・不正regionはfail。
正負テストと既存deploymentテストの成功を実IAM/疎通/配置の証明と呼ばない。

## 実AWS前の未決値

| 項目 | 必要根拠 |
|---|---|
| 個人account/operator role完全ARN | ユーザー指定と別承認後のidentity照合 |
| AZ/PG17完全minor/CA/quota | 別承認後の実提供確認 |
| 初回/再構築environment名・全ID/ARN | 保存planと選択した非秘密output |
| source commit/image digest | clean checkoutとの対応 |
| state/plan/tfvars/秘密保管path・期限 | repo外0700/0600、正規path/hash。内容を貼らない |
| USD予算/JPY換算/残存上限 | [費用試算](fl-10b-aws-costs.md)と実行日の数量/単価 |
| UTC/JST開始・閉鎖/破棄期限・担当 | 実日時はユーザー指定。案は各構築4時間以内 |
| 後日請求/残存確認日・担当 | snapshot/backup/secret等の保管判断 |
| approval reference/steps | 対象操作の別承認。今回の開発承認で代用しない |

## 工程・証跡・停止点

| 工程 | 事前条件と証跡 |
|---|---|
| inspect | 実申請承認、state保護/hash、identity/資源正本。不一致なら以後接続しない |
| static | inspect対応、許可step、固定配置と同run証跡 |
| bootstrap-inspect/bootstrap | 専用task/role、各許可step。master secretをWebへ渡さない |
| migrate/seed/check | 非管理者role、先行成功、同run/source/image |
| verify | TLS/公開境界/API/画像/CSRF/本人境界/IP制限の実結果。mock代用不可 |
| 撮影 | verify成功、Aの台本、映像/経路/時刻/source対応。今回はnot_run |
| 閉鎖・停止 | 対象/期限承認、公開無効、one-off含むtask終了確認。課金ゼロとはしない |
| 破棄 | 保護解除/対象削除の別承認。snapshot/backup/S3/ECR/log/secret棚卸し。共有資源対象外 |
| 再構築 | 別environment/新run、新規証跡。初回結果流用不可 |
| 後日確認 | 保管期限/担当、請求の遅延反映と残存確認 |

失敗run証跡を残す。CLIのAWS opt-inは承認を代替しない。2構築・撮影・課金停止/後日請求確認までFL-09/10全体未完了。

## 停止・残存

今回は停止/削除も実行しない。実行時はrunbookの閉鎖→task停止→保護解除/DB破棄→残存確認を対象承認内で行う。
ECS0でもALB/IPv4、DB storage、snapshot/backup、S3/ECR/log、未削除secret等は別管理。
[RDS公式](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_StopInstance.html): 停止中もstorage/backupが残り7日後に自動再開。停止を恒久的課金停止にしない。
[Secrets Manager公式](https://docs.aws.amazon.com/secretsmanager/latest/userguide/manage_delete-secret.html): 削除予約済みsecretは課金なし。7日回復期間の残存/名前衝突/復元可能性を管理し、未削除/復元済みの課金と区別する。
