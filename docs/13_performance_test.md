# 15. パフォーマンステスト（FL-10B）

最終更新2026-11-07、Issue #55。独立設計レビュー・ユーザー承認済みのローカル試験仕様。
[実行手順](../perf/README.md)、[実測結果](fl-10b-local-results.md)。AWS実証は未実施。

## 15.1 環境・隔離

標準Python runner、既存lock済みbackend/PostgreSQL17 image、Django runserver、DEBUG=false、backend memory1GiB、ローカルprivate storage。
共通Git領域fitlog-runtime.lockで排他。固定18080使用中なら他者serverを停止せず見送る。
UUID別のDB container/volume・network・画像volume・backendを作る。専用settings/seedでDB名/hostを検査し共有DBへ接続しない。
台帳・ラベルが一致した今回の所有資源だけを停止・除去する。共有DB reset/逆migration/包括的volume削除は禁止。
全体30分（作業29分+cleanup最大1分）、migration/seed各5分、HTTP全体5秒、body16MiB。worker終了不明/cleanup失敗はlock保持・fail。
S3/CloudFront/ALB/RDS/Gunicornとの差は未測定。ローカル合格をAWS合格としない。

## AWS限定試験の準備（C #60）

[専用harness](aws-c-verification-runbook.md)ではE2Eの同じ2利用者と既存投稿を使い、各1要求/秒・GETのみ、warmup10秒＋90秒180枠を別測定する。3分類各60標本、既存nearest-rank集計・各p95<1000ms・失敗/欠測0を採用する。ローカル5人/1000投稿のseed・最大境界・画像負荷・auth-burstはAWSへ持ち込まない。実AWS試験は別承認前not_runであり、5人容量や本番性能の証明とは呼ばない。

## 15.2 固定データ

| データ | 通常 | 最大境界 |
|---|---:|---:|
| 利用者/投稿（各人200） | 5 / 1000 | 5 / 1000 |
| 種目/投稿・セット/種目 | 3 / 3 | 10 / 20 |
| 総種目/セット | 3000 / 9000 | 10000 / 200000 |
| コメント/like/follow | 2000 / 2000 / 10 | 2000 / 2000 / 10 |

日時・UUID・本文・重量・関係を固定し通常/境界を別空DBにseed。製品demo seedへ混ぜず前後件数監査。
投稿追加/削除なし。各人は別の本人投稿だけ更新/like操作。smoke後likeなし、warmup/測定後各人likeあり（最終2005）。

## 15.3 負荷・合否

各人独立process/CookieJar/CSRF。正規login→CSRF再取得→me照合。認証枠の変更/消去・再login/retryなし。
smoke55要求の後、warmup30秒を除外し300秒。各人毎秒1要求、合計毎秒5・同時最大5、測定1500予定枠。

| API | 予定標本 |
|---|---:|
| all timeline GET（limit20、先頭/次ページ） | 300 |
| following timeline GET（同上） | 300 |
| 詳細GET | 300 |
| 本人一覧GET / 検索GET / 本人投稿PUT | 各150 |
| like POST / DELETE（空body・本人owner・CSRF） | 各75 |

通常/境界別、全体/API-method別p50/p95/p99（nearest-rank、補間なし）、5xx/全失敗率を報告。
要求開始→body全受信の時間を計測し内容oracle時間は除外。各API-method p95<1000ms・5xx<1%に加え、意図しない応答/通信失敗/内容不一致/missed=0を要求（合格時5xxも0）。各分類50標本以上。
1000ms一致/0件/標本不足/欠測はfail。401/403/429/redirect/5xx/timeout、空items、不正JSON、別viewer、順序・件数・種目/セット欠落を失敗にする。
遅れた枠を取り戻さずmissedへ。親processが要求全体5秒を監視しtimeout時間も記録する。

## 15.4 別測定

画像は別通常DB、直列60要求（5人×3サイズ×2周×upload/download）、120秒上限。
147/590/1320px四方の固定RGB PNG（約64KiB/1MiB/5MiB、実bytesは結果、5MiB以下）。正規化後の形式・寸法・RGB画素digestを照合。
入力/出力bytes、時間・転送速度を別報告しAPI1秒基準から除外。画像同時5人の容量は主張しない。
認証集中は別空DBの同一IP/60秒窓11回。最初10回200、11回目429+Retry-After。窓跨ぎ/20秒超fail、通常分母へ混ぜない。
stress/spike/soak・AWS実負荷は対象外。

## 15.5 証跡

results.json/requests.jsonl/ownership.jsonへ環境・版・snapshot・件数・負荷・失敗・CPU/memory定点観測（欠測明記）・cleanupを対応付ける。
Cookie/CSRF/画像URL/password/response本文を保存しない。起動・seed・smoke/warmupは300秒分布から除外。
未達を閾値変更や担当外の製品修正で隠さず、pass/fail/not_run/未決を区別する。
