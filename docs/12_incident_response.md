# 障害対応手順

FL-08（Issue #16）の運用手順。検証・採用状況はIssue/PRの証跡を参照する。個人デモのため24時間対応は約束しない。AWS上の故障注入とdestroy訓練はFL-09で費用/対象を確認して実施する。

## 初動

撮影/更新を止める→対象の個人repo/環境/版を確認→発生時刻・status・request-id・固定eventを保全→原因を切り分け→同じhealth/認証/記録/画像操作で回復を確認する。資格情報、本文、健康値、画像URL、Terraform stateを証跡へ貼らない。

情報漏えい疑い・意図しない公開・課金資源の制御不能を最優先に扱う。認証/記録停止、一部表示・性能問題とは分け、停止予定を障害と混同しない。

## ローカルの切り分け

| 症状 | 調査と復旧 |
|---|---|
| 起動不可 | 固定image/環境設定/依存疎通/migrationを確認。不正なログ形式設定は固定エラーで拒否される |
| live不可 | process/起動を調べる。DB障害と即断しない |
| live正常・ready不可 | DB疎通/接続数/資格情報/migrationを確認。データを初期化せず復旧後にreadyを再確認 |
| API 5xx | responseのrequest-idと時刻/statusを照合。unmatchedは解決前の障害でも起きる。本文をログへ足して回避しない |
| ログ欠落 | stdoutの接続/回収先を確認。書込み失敗時のraw traceback fallbackは抑止されるため、ログ不在を処理未実施と決めない |
| 認証拒否 | HTTPS/Cookie/CSRF/時刻/session失効を確認。認証やCSRFを無効化しない |
| private画像失敗 | local storageの権限/空き容量/設定とoperation状態を確認。公開ディレクトリや公開バケットへ切替えない |

## 清掃command

通常の同一Compose設定で、排他枠を保持してから実行する。実秘密をCLI引数へ渡さない。稼働中の他担当環境に対する清掃試験はしない。

```sh
docker compose --project-name fitlog-dev -f compose.yaml run --rm --no-deps backend uv run --frozen --no-sync python manage.py cleanup_auth_security
docker compose --project-name fitlog-dev -f compose.yaml run --rm --no-deps backend uv run --frozen --no-sync python manage.py cleanup_images --limit 100
```

認証清掃は期限切れsessionと既存2分以前のrate windowだけ。画像清掃は既存の有限batch/保持期間/backoffを使う。今回のログ追加は削除対象を広げない。

| 結果 | 意味と行動 |
|---|---|
| maintenance_complete / exit 0 | commandのbatchが完了。画像全削除完了を意味しない。countsとpending_jobsを確認 |
| clean_one内の個別delete失敗 | jobがbackoffへ延期され、batchは完了し得る。pending_jobs/次回の推移を確認 |
| listing/sweep/reconcileの直接delete/DB障害 | maintenance_failed、固定CommandError、非0。途中変更済みの可能性を保ち、原因解消後に冪等再実行 |
| 最後のpending_jobs集計失敗 | 清掃完了済みの可能性もあるがmaintenance_failed/非0、countsなし。再実行で照合 |
| limit範囲外 | 開始前の固定CommandError、非0、maintenance eventなし |
| 型不正/未知引数 | 標準argparseの非0、eventなし。operator入力をechoし得る。保存済みデータの値を返すものではない |
| image_cleanup_retry | callbackのDB失敗。時刻/eventで調査しAPIの相関IDがあるとは仮定しない |

変換するCommandErrorはfrom Noneで元例外chainを抑止する。運用で自由なtracebackをログへ追加しない。バケット全削除、DB再作成、force、検査無効化で回避しない。

## AWSの後続確認

S3障害はIAM/キー/バケット/署名期限を確認し、バケット公開で回避しない。destroy失敗はstate/エラーを保持し、専用資源/バケット内容/依存関係/snapshotを照合する。実操作、残存資源確認、ログ資源破棄、再apply/再destroyはFL-09の本人採用・費用確認後に行う。本工程のlocal storage試験からAWS成功を推定しない。

## 復旧記録

発生時刻、対象commit/環境、症状、影響範囲、request-idまたは固定event、原因、実施操作、復旧時の観測、残存問題を記録する。互換な前版へ戻す場合もDB互換性を先に確認し、破壊的migrationの逆実行を安易に行わない。
