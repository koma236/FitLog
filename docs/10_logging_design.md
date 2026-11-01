# ログ設計

FL-08（Issue #16）の実装契約。FL-07（PR #19）の共通middleware修正を取り込み、全APIの結果ログを接続した。最終的な検証・採用状況はIssue/PRの実行証跡で判断する。

## 出力と設定

`FITLOG_LOG_FORMAT=text|json`、既定はtext。不正値は秘密を含まない設定エラーで起動を拒否する。ログは`SafeStreamHandler`からstdoutへ、CLIの処理失敗の固定CommandErrorはstderrへ出す。API/maintenanceはpropagate=False。rootはWARNING以上を安全handlerへ渡し、未知recordは固定`log_record_discarded`になる。Djangoのrequest/server/SQLログはNullHandlerで抑止する。

`FITLOG_APP_VERSION`は7〜40桁の小文字hex commitだけを出す。それ以外/未設定は`unknown`。AWSでのjson指定とapp version注入はFL-09で行う。

## 固定schema

全eventにtimestamp（UTC ISO-8601・ミリ秒・Z末尾）、level、event、request_id、app_versionがある。duration_msはmonotonic clock差分msの切捨てによる非負整数。

| event | logger / level | 追加field |
|---|---|---|
| api_request | fitlog.api / INFO | request_id=サーバー生成UUID、method、route_template、status、duration_ms |
| api_error | fitlog.api / WARNING(4xx)、ERROR(5xx) | api_requestと同じ |
| maintenance_complete | fitlog.maintenance / INFO | request_id=null、command、duration_ms。cleanup_imagesだけcounts |
| maintenance_failed | fitlog.maintenance / ERROR | request_id=null、command、duration_ms。countsなし |
| image_cleanup_retry | fitlog.maintenance / WARNING | request_id=null、command=null、duration_ms=null |
| log_record_discarded | 安全handler / WARNING | request_id=null。任意のmessage/args/extra/例外を出さない |

commandはcleanup_auth_security/cleanup_imagesだけ。countsはretired/deleted/reconciled/temporary/pending_jobsの非負整数のみ。pending_jobsは未完了job総数であり、失敗数や今回の処理数ではない。

methodはGET/HEAD/POST/PUT/PATCH/DELETE/OPTIONS以外をOTHERとする。route_templateはDjangoの宣言pathを使い、実URLやpath引数は含めない。catch-allと解決前の400/DB・session障害等はunmatchedとなる。unmatchedだけで未知URLと判断せずstatusとrequest_idを使う。

JSONは1行1object。textは`LEVEL EVENT`に続けて、schemaにあるfieldだけをstatus/request_id/command/method/route_template/duration_ms/app_version/timestamp/countsの順でkey=valueにする。nullはnull、countsは空白なしJSON object。

## 相関と制限

APIのX-Request-Idはサーバー生成UUIDであり、入力X-Request-Idを採用しない。最終responseを1件記録する。duration_msはresponse object生成までで、画像等のstream転送完了時間ではない。

retry callbackはrequest contextを引き継がず、時刻とeventだけで調べる。APIとの一対一相関が取れるとは主張しない。user_idは記録せず、ログのためのrequest.user評価やDBアクセスを行わない。

stdout書込みが失敗するとログが欠落し得る。handleErrorはraw Message/Arguments/traceをstderrへ出さず、業務responseもログ障害で変更しない。ログが無いことだけを処理成功/失敗の根拠にしない。

## 機密情報

パスワード、Cookie/CSRF/Authorization、メール、名前、健康値、投稿・コメント本文、画像、capability/署名URL、DB接続文字列、例外文字列を渡さない。formatterはlogger名とeventの許可組、項目集合、型を照合し、不正recordを固定eventへ置換する。

この保証はFitLogが構成するlogging/command出力が対象。operatorが不正なCLI引数へ書いた文字列は標準argparseの拒否文でechoされ得る。実秘密を引数へ渡さない。外部ツールの直接printや将来のSDK独自handler/wire traceは別途検証し、FL-09でS3 SDK/本番serverの実出力を確認する。

## 検証の読み方

handlerはdictConfig時のstdout objectを保持するため、capsysだけで捕捉できるとは仮定しない。試験は設定された安全handlerを列挙して重複を除き、streamを専用StringIOへ差し替え、終了時に復元する。正のeventと秘密非出力を両方assertし、空bufferを合格にしない。

CLI境界はCommandへ注入したstdout/stderrとhandlerのbufferを分離して観測する。これはin-process試験でありOS subprocessの出力確認とは区別する。独立レビュー/正式11checks/実GitHub CIは別の証跡として扱う。

CloudWatchの保持期間・ログ資源破棄・health probe頻度とログ量/費用の確認はFL-09。外部有料監視は本工程で追加しない。
