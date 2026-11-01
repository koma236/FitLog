# ヘルスチェックと運用監視

FL-08（Issue #16）の実装契約と検証区分。最終的な採用状況はIssue/PRの証跡を参照する。常設の通知基盤は追加せず、ローカル検証/撮影中の手動確認を基本とする。AWS実監視の成功を先取りしない。

## health契約

| endpoint | 意味 | 応答 |
|---|---|---|
| GET /api/health/live | 認証/セッション/DBに依存しないプロセス確認 | 200、status=ok |
| GET /api/health/ready | 実DB疎通と必要migrationの適用 | 正常200/ok、DB不可・未適用503/unavailable |

応答は内部構成/資格情報/例外を含めない。既存のX-Request-IdとJSON例外境界を保ち、想定外の不具合は500とする。DB接続timeoutは5秒、readiness内のstatement_timeoutはtransaction-localの2秒で、後続SQLへ漏らさない。画像storage/S3はreadinessへ組み込まず、別の低頻度スモークで調べる。

## 証跡の区別

- 実PostgreSQL: 正常→実driverの接続拒否→設定復元後のSELECT 1/ready 200を確認する。テストprocessが所有する非listen loopback socketで接続拒否先を作り、共有DBを停止しない。
- 設定分離: transaction=True試験で接続設定をdeep copyし、finallyで元dict参照/接続を復旧する。statement_timeoutも前後照合する。
- 未適用migration: 既存migration_plan mockの503試験。実migration rollbackをした証跡ではない。
- ログ: handler-streamの固定反証と、CLIの固定stderrを確認する。OS subprocess捕捉やAWSログ配信とは同一視しない。
- 全体: FL-07統合後の登録11checks、独立品質レビュー、実CIを別々に記録する。部分テストの成功で全体完了にしない。

## 手動確認の目安

| 観測 | 初動 |
|---|---|
| readyが連続失敗 | プロセス、DB疎通、migration、環境設定を照合。DB初期化や検査無効化をしない |
| API 5xx | 発生時刻・status・X-Request-Idを保存し、固定eventを照合。本文や秘密を添付しない |
| 画像清掃pending_jobsが残り続ける/増える | backoff待ちかstorage/DB障害かを切り分ける。deleted=0だけでは障害と決めない |
| maintenance_failed/CLI非0 | 部分変更済みの可能性を残し、同じ冪等commandで再照合する |
| 遅延/資源増加 | FL-10の固定負荷計測で調べる。JVM固有閾値や未計測p95を合格判定に使わない |

成功health probeもINFOのAPI結果ログに含む。ALB/ECS等の頻度、対象数、実行時間からFL-09で件数と費用を見積もり、保持期間を決める。ここで通知SaaS、CloudWatch設定、S3/IAM、費用アラートは作成していない。

共有fitlog-devではbuild/DB/checks/清掃を同時実行しない。共通Git管理領域のfitlog-runtime.lockを原子的に取得しownerを記録する。所有者不明のlockや他担当サービスを削除/停止せず、連絡して待機する。清掃試験はtest_fitlogと一時private storageだけを使う。
