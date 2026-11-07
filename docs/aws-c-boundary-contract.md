# C04 公開境界の観測契約

最終更新: 2026-11-07。関連: Issue #66、[C利用手順](aws-c-verification-runbook.md)。実装は `e2e/aws_boundary.py`。本書の形式を受理するローカル検証器を用意した段階であり、実AWS結果は未取得。

## 目的と信頼の境界

対象不明の403、存在しないobject、SG根拠のないtimeout、成功要約から公開境界の合格を作らない。A operatorが別承認の対象環境で収集した非秘密原本を、Cがオフラインで照合する。CはAWS SDK・オンラインcollectorを持たず、Bのpermissions/IP収集も再実装しない。

hashは原本の改変検知であり、AWSが発行した署名ではない。実環境で採取したことの確認にはAの承認・操作台帳・資源ID・UTC・原本の突合が必要。テスト用の `e2e/harness/boundary_fixtures.py` は架空データであり、実行許可やAWS成功証跡に使わない。

## 入力と保存

C契約schema v1の `evidence` は `{probe_id,path,sha256}` の配列を維持する。各pathは絶対正規path、実行者所有の通常file、mode0600または0400、親directory0700、symlink/hardlink不可、各1MiB以下。sha256はファイルの**byte列**のhex64桁。B handoff工程原本のcanonical JSON hashとは区別する。

新receiptは次のキーだけを持つ。9 identityはC契約と全一致させる。

| キー | 値 |
|---|---|
| schema_version | 整数2 |
| account/region/environment/run_id/bootstrap_id/source/image_digest/frontend_sha256/origin | C契約の9 identityをトップレベルへ配置 |
| probe_id | alb-normal/alb-host/task/s3-static/s3-media/other-distribution/viewer-headers |
| inventory | `{path,sha256}`、全7probeで同じ参照 |
| observation | `{path,sha256}`、probe固有の非秘密観測原本 |

status=passを入力しない。旧identity/probe_id/status=passだけの要約は互換読取りできるが `not_run` になる。未知キー/schemaは拒否する。

### 対象台帳inventory

トップレベルは `schema_version:1, identity, observed_at, approval_reference, starts_at, expires_at, targets`。identityは9項目のobject。承認referenceはCと一致、windowはCのwindowを内包する。observed_atはCの `[starts_at,expires_at)` 内のUTC（秒精度Z）。targetsには以下の7対象をすべて含め、各対象に実在確認原本への `original:{path,sha256}` を付ける。

| 対象 | originalを除く完全な属性 |
|---|---|
| alb | arn, dns, port=80, security_groups（1件）, ingress, prefix_list |
| task | arn, eni, public_ip（IPv4）, port=8000, security_groups（1件）, ingress |
| static/media | arn, key, sha256（既知object本文）, size（1〜16384bytes）, region, owner |
| distribution | id, dns, bucket_arn（static）, origin_path="", path_pattern="*", oac, api |
| other | id, dns, bucket_arn（static）, origin_path="", path_pattern="*", oac |
| function | arn, stage="LIVE", sha256（実配信Function公開codeのbyte hash） |

ALB/task/Function ARNのaccount・regionとCを照合。task ARNのcluster名はenvironment。bucket ARNは `arn:aws:s3:::<environment>-<staticまたはmedia>-<account>-ap-northeast-1`。正規distribution DNSはC originと一致し、otherのID/DNSは正規と異なる。keyは1〜200文字の英数・underscore・dot・slash・hyphen（先頭slashと `..` は不可）。原本は対象の存在とattachment/属性をまとめて保持する。

- ingress: `[{protocol:"tcp",from_port,to_port,source_type,source}]`。ALBは80/80/prefix-list/実prefix list ID、taskは8000/8000/security-group/ALB SG IDの1規則だけ。全attachmentと全ingressを収集し、余分なSG/広い許可を省いて射影しない。
- prefix_list: `{id,name:"com.amazonaws.global.cloudfront.origin-facing",owner:"AWS"}`。
- oac: `{id,origin_type:"s3",signing_behavior:"always",signing_protocol:"sigv4"}`。両distributionの実attachment・対象behavior・origin pathを収集する。OACなしの匿名拒否はSourceArn制限の実証にならない。
- api: `{alb_arn,origin_verify:"configured",forwarded_proto:"https",function_arn}`。秘密custom headerの値は含めない。
- function公開codeのhashはリポジトリの `terraform/functions/client-ip.js` と一致させる。正規distributionのAPIへのFunction関連付けも一致させる。IP観測にはB handoffの `verify-public-ip-baseline` と `verify-public-ip` が必要で、両方のparameters_sha256も一致させる。

対象ごとのoriginalは `schema_version:1,identity,observed_at,kind,facts` だけを持つ。kindは上表の対象名、factsは台帳からoriginalを除いた全属性と一致させる。AはDescribe/Get/Head結果から、実在・SG attachment・全規則・OAC・objectのlength/hash等の事実を収集時にallowlist射影してこの原本を保存する。secretを含むCloudFront全設定・Terraform state・生ログをCへ渡さない。

### 要求・応答の観測原本

`schema_version:1,identity,probe_id,observed_at,attempts` を持つ。attemptsは `{request,result}` の配列で、最後の2probeだけ2件、他は1件。

requestの完全なキーは `target,host,port,scheme,method,path,host_header,headers`。methodはGET。host/port/scheme/pathは対象台帳から検証器が導出する。任意URL・署名query・redirectは使わない。host_headerはHostの条件名で、実際のsecret値を格納する欄ではない。headersは固定profileのnone/spoofedのみ。

resultの完全なキーは `transport,status,response_class,body_bytes,body_sha256`。HTTPではtransport=http、statusは整数、body_bytesは1〜16384。本文は保存せず、受信時のbyte数/hashと固定分類を残す。S3エラーは実XMLのCode=AccessDeniedを確認してaccess-deniedへ分類する。timeoutでは `transport:"timeout",status:null,response_class:"none",body_bytes:0,body_sha256:null`。一般通信エラーや404は合格にしない。

| probe | attemptsの順序・要求条件 | 合格する実観測 |
|---|---|---|
| alb-normal | alb DNS/HTTP80、health、host_header=alb、headers=none | SG根拠付きtimeout、または403/alb-denied/本文Forbiddenのhash |
| alb-host | 接続先は同じalb、host_header=canonical（正規CloudFront DNS） | 上と同じ。偽Hostへ接続しない |
| task | 実ENI public IP/HTTP8000、health、host_header=task | SG原本とattachmentが一致しtimeout。HTTP拒否と区別してsg-restrictedと記録 |
| s3-static/media | `<bucket>.s3.ap-northeast-1.amazonaws.com`/HTTPS443/既知key、host_header=target | 匿名・非署名GET403/access-denied。既知objectの実在原本が必須 |
| other-distribution | 正規→別DNSの順でHTTPS443/同じstatic既知key、host_header=target | 正規200/objectと既知hash/size一致、別403/access-denied。両方でOAC署名必須 |
| viewer-headers | 正規DNS/HTTPS443/health/host_header=canonical、headers=none→spoofed | 両方200/health、本文 `{"status":"ok"}` のbyte hash一致、配信Function/設定原本とB IP観測一致 |

healthの期待byteは[FL-01仕様](fl-01-foundation-design.md)に従う空白・末尾改行なしの15byteで、SHA256は `a29ee2b15c494311c52521766e44af56a3ad2248e7a8ab465e5206463c13d288`。`e2e/harness/health_response_contract.py` を実backendの `manage.py shell` で実行し、Django Client→LiveView→DRF rendererの実応答 `response.content` と照合する。共通runtime lock内でこのworktreeのimageをbuildしてから実施する。validatorの定数から期待値を生成せず、同じ意味の空白入りJSONもbyte不一致として拒否する。

health pathは `/api/health/live`。noneでは秘密origin headerを送らない。spoofedは固定の無効なorigin-verify、httpのforwarded-proto、試験用IPを用いてorigin-verify/proto/client-IPの偽装を試みる条件名。実値は秘密でない専用値をAの操作台帳へ固定し、B IP試験のspoof条件とも照合する。受信header全体やsecretは原本に保存しない。

## 判定と原本のライフサイクル

欠落・未収集・旧要約はnot_run。不一致（hash/identity/対象/条件/期限）・未知field・期待外応答はfail。failをnot_runより優先する。全7probeがpassの場合だけC04がpassとなり、B permissions/IPもpassの場合だけfinal_evidence_ready=true。C03、総合acceptance、動画視認、破棄/再構築、請求は別判定を維持する。

原本は射影してから確定し、その後byte hashを計算する。hash計算後にredactしたファイルへ同じhashを付けない。秘密の生ログをAが別途保管する場合はCへ渡す原本から分離する。Cの出力には固定のstatus/classification/fingerprintだけを残し、未知値/例外本文を反射しない。

提供された不正原本はpreflightで拒否しclientを作らない。not_runなら既存journeyは実行可能。終了時は原本を再読込みし、開始時の参照・byte hash集合のfingerprintと比較する。一度読んだ原本の消失・追加・改変はfailにして古いpassを残さず、client停止・lock返却を続ける。最終C04は親のruntime.jsonの `c04/boundary` を正とし、browserのaws-results.jsonのC04はnot_runのままにする。

## A/#67へ引き渡す試験量

新規HTTPはALB2/task1/S3匿名2/別distribution対照2/viewer対照2の **9要求/環境**。各応答16KiB、timeout5秒、redirect/retryなし。既知static/media fixtureは16KiB以下。資源確認のDescribe/Get/Head等API、fixture/別distributionの作成・伝播・削除、CloudFront/ALB/ECS/S3/API/転送/保存の費用と時間は別申請で列挙する。Cの3000要求/20MiB/45分へ暗黙加算しない。

C02は同一APIRequestContextでCSRF GET1・状態GET4・PUT3の8要求。正例と負例のmethod/endpoint/body/session/CSRF等は同じでOriginのみを変更。正例でmarkerへ変更→元の状態へ復元→同じmarker本文の負例403/CSRF_FAILED→復元状態が不変の順で確認する。正例と負例の間の復元PUTは対照ペアに数えない。recalculate=falseで既存投稿を使い、新規user/post/imageを作らない。これらはCの既存送信予算と停止/期限に従う。
