# Issue #70 RDS bootstrap管理grantの修正

2026-11-15承認。既存B6初期化の補正であり、appの認可・migration・IaC・CI・gateは変更しない。

## 実観測と方針

実RDS PostgreSQL17.11の公開dummy値によるrollback診断で、role作成後の管理者ADMIN OPTION検査が失敗した。予約は正常、実app secretは未読・未更新、DB変更はrollbackしてrole未作成へ戻った。通常PG17の作成者への暗黙grantを、この実行では仮定できなかった。RDS全体の内部仕様を断定するものではない。

初期化のCREATE ROLE直後、同じtransactionで固定の `GRANT fitlog_app TO fitlog_admin WITH ADMIN TRUE, INHERIT FALSE, SET FALSE` を実行する。masterへの管理関係だけを明示し、appへの管理者membershipは与えない。appの5強権限はfalse、上位membership0、DB/schema ACL・管理table拒否・元のverifyを維持する。新grant失敗時はrole/ACL/完了markerをrollbackし、予約と元secretを保持。既存role/ACLの自動修復はしない。

## 検証と復旧

通常の非SUPERUSER経路とself_grant既定/`inherit,set`を維持し、暗黙ADMINなしのローカルモデルを追加する。モデルはSUPERUSER creatorで当該条件を作るもので、RDS自体の再現ではない。管理membershipの全grantor・全行で存在、ADMIN付き行あり、INHERIT/SET=falseを独立SQLで検査し、appでの実拒否・全migration・rollback/同UUID再開を確認する。旧imageのREDは既存ADMIN検査での失敗を確認済み。

登録11checks・専用production image PG17/TLS fixture・独立品質レビューを実施。独立設計レビューはHigh0、Medium2（全membership行のoracleと手動相互レビュー適用）を具体化済み。品質枠はユーザー承認で最大3巡追加し、既存状態を保持する。

本変更はDB権限管理のため手動相互レビュー対象。PR作成後は別providerによる本人のレビュー依頼と、対象PRへの再開指示を待つ。指摘ゼロでも再検証する。必須gate完了後だけ、新source/image/digestを保護台帳へ固定し、同じ専用環境のtaskdefinitionを更新する。実RDSの新image rollback診断が成功してから、別run UUID・別証跡folderで元bootstrap UUID/保存secretの既存B6復旧を行う。

one-off計14回、追加task合計3時間、総予算5 USDを維持。公開停止・destroyは本人指示後のみ。許可されていない検査緩和、手動role削除、別環境、追加権限は採用しない。

## 実装時の差異

無条件の明示grant案→作成後のADMINが不足する場合だけ明示grant。通常PG17が既に付与したADMINを自分へ再付与するとInvalidGrantOperationになることを実SQLテストで確認したため。作成前にtransaction-localのcreaterole_self_grantを空にしてINHERIT/SETの暗黙付与を防ぎ、既存ADMINを保持する。設定がtransaction後に元へ戻ることも独立SQLで確認する。appの権限制限・既存verify・rollback境界・同UUID復旧は維持。

実RDS確認は新image配置のgate完了後に実施し、ローカル成功を実RDS成功とは報告しない。
