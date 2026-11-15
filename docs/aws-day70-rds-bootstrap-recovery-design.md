# Issue #70 RDS bootstrap管理grantの修正

2026-11-15承認。既存B6初期化の補正であり、appの認可・migration・IaC・CI・gateは変更しない。

## 実観測と方針

実RDS PostgreSQL17.11の公開dummy値によるrollback診断で、role作成後の管理者ADMIN OPTION検査が失敗した。予約は正常、実app secretは未読・未更新、DB変更はrollbackしてrole未作成へ戻った。通常PG17の作成者への暗黙grantを、この実行では仮定できなかった。RDS全体の内部仕様を断定するものではない。

初期化のCREATE ROLE直後、同じtransactionで固定の `GRANT fitlog_app TO fitlog_admin WITH ADMIN TRUE, INHERIT FALSE, SET FALSE` を実行する。masterへの管理関係だけを明示し、appへの管理者membershipは与えない。appの5強権限はfalse、上位membership0、DB/schema ACL・管理table拒否・元のverifyを維持する。新grant失敗時はrole/ACL/完了markerをrollbackし、予約と元secretを保持。既存role/ACLの自動修復はしない。

## 検証と復旧

通常の非SUPERUSER経路とself_grant既定/`inherit,set`を維持し、暗黙ADMINなしのローカルモデルを追加する。モデルはSUPERUSER creatorで当該条件を作るもので、RDS自体の再現ではない。管理membershipの全grantor・全行で存在、ADMIN付き行あり、INHERIT/SET=falseを独立SQLで検査し、appでの実拒否・全migration・rollback/同UUID再開を確認する。旧imageのREDは既存ADMIN検査での失敗を確認済み。

登録11checks・専用production image PG17/TLS fixture・独立品質レビューを実施。独立設計レビューはHigh0、Medium2（全membership行のoracleと手動相互レビュー適用）を具体化済み。品質枠はユーザー承認で最大3巡追加し、既存状態を保持する。

本変更はDB権限管理のため手動相互レビュー対象。PR作成後は別providerによる本人のレビュー依頼と、対象PRへの再開指示を待つ。指摘ゼロでも再検証する。必須gate完了後だけ、新source/image/digestを保護台帳へ固定し、同じ専用環境のtaskdefinitionを更新する。実RDSのgrant可否を下記のrollback診断で確認した。必須gate完了後、別run UUID・別証跡folderで元bootstrap UUID/保存secretの既存B6復旧を行う。

one-off計14回、追加task合計3時間、総予算5 USDを維持。公開停止・destroyは本人指示後のみ。許可されていない検査緩和、手動role削除、別環境、追加権限は採用しない。

## 実装時の差異

無条件の明示grant案→作成後のADMINが不足する場合だけ明示grant。通常PG17が既に付与したADMINを自分へ再付与するとInvalidGrantOperationになることを実SQLテストで確認したため。作成前にtransaction-localのcreaterole_self_grantを空にしてINHERIT/SETの暗黙付与を防ぎ、既存ADMINを保持する。設定がtransaction後に元へ戻ることも独立SQLで確認する。appの権限制限・既存verify・rollback境界・同UUID復旧は維持。

## PR #72 相互レビューH1への実測回答

相互レビュー対象は `f5a3e75a5d30eff880d7ca3ad1a3f953fbcce05e`。2026-11-15 21:13 JSTの本人のコメント対応指示により再開した。通常PGの非SUPERUSERの規則からRDSでもgrantできない可能性が指摘されたため、SUモデルの成功とは別に、同じ専用RDS PostgreSQL17.11の実測を取得した。

元の失敗を特定したrollback診断（20:21:37 JST）のsourceは `97296be3cb9375936e219cae8c0f9ab8f4c6edd4`。例外は `BootstrapError`、経路は `database.py:164 initialize → database.py:263 verify → contract.py:21 require`。同sourceの263–266行は `coalesce(bool_or(admin_option),false)` がTrueかを要求する箇所であり、257行のapp属性、258行の上位membership0、260行の他管理member0とは区別できる。

21:19:56 JST、同じRDS管理者の接続で、公開dummy値だけを使用した診断を1回実行した。元imageのinitializeをconnection proxyで観測し、CREATE ROLE前に現在の修正と同じtransaction-local設定を適用し、CREATE ROLE直後に固定GRANTを実行した。全体は強制rollbackし、元の厳格なverifyも通した。観測は次の通り。

| 観測 | 結果 |
|---|---|
| session_user / current_user | ともに `fitlog_admin`。SET ROLEは未使用 |
| 管理者属性 | SUPERUSER=false、CREATEDB=true、CREATEROLE=true、REPLICATION=false、BYPASSRLS=false |
| 管理者の既存membership | `rds_superuser`、grantor=`rdsadmin`、ADMIN=false、INHERIT=true、SET=true |
| CREATE ROLE後、明示GRANT前のapp管理membership | 0行 |
| 明示GRANT後の全行 | member=`fitlog_admin`、grantor=`rdsadmin`、ADMIN=true、INHERIT=false、SET=falseの1行 |
| initialize / 元verify | 成功 |
| rollback後 | app roleなし、既存予約は有効、完了markerなし |
| secret / 永続DB変更 | app secret値未読、secret書込み0、永続DB書込み0 |

従って、この環境では不足ADMINをRDS管理者が直接付与できる。標準PGの非SUPERUSERや他RDS環境へ一般化せず、grantorがrdsadminになった理由の内部実装も推測しない。新sourceのproduction image自体を実RDSへ配置した検証ではないため、実配置後のbootstrap/DB検証は引き続き必須とする。検査・権限制限を緩めるcode変更は不要と判断した。

診断は予定済みの配置前rollback確認枠を置き換え、追加のone-off枠を増やさない（消費済み5、残り9、上限14）。新imageによる別のrollback taskは重ねて実行しない。この順序変更も実装時の差異として報告する。公開停止/destroyの自動実行はしない。

監査用の非秘密JSONと診断payloadは保護台帳に保存し、下記SHA-256で対応づける。生のTerraform state、password、secret値、ログ全文は公開しない。

- 元rollback観測JSON: f4d909b713d96489d9fa7c5b28e6d67ee2455b88c08c1eb3a98fcac74fc68227
- H1実RDS観測JSON（observationのみ）: 56e1d4b4a1d3e61e2e5527ce7c45498790fc11bc288b2cb95fdc25e8d80c26b7
- H1診断payload: 5a1193fe0a090c1d23a6929ced63f414e7415750c06b67181bb9f876c0a083b1

Medium/Low指摘はPRへ記録する。特にSU creatorはB6の「常に非SUPERUSER」というローカルfixture前提の明示的な例外で、検証するのはADMIN欠落分岐のSQL、option、設定復元とapp拒否である。実RDSのgrant許可の根拠には使わない。通常非SUPERUSERの2条件も維持する。明示GRANT自体のSQL失敗から予約/secret保持を経て同UUID復旧する専用flowは未追加である。
