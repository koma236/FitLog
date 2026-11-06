# H4対応：操作UUIDの永続予約（承認済みの差異設計）

## なぜ元の順序では足りないか

DB session lockだけでは、その接続喪失とSecrets Managerへの遅延書込みをatomicに制御できない。秘密の書込み直前にDBを再検証しても、その直後に接続が切れた場合の競合窓が残る。別UUIDの実行Bが初期化した後に実行Aの書込みが到着すると、AWSCURRENTとDB passwordが不一致になる。

## 推奨変更

秘密を生成・保存する前に、管理者専用schemaへoperation UUIDと対象metadataの永続予約をcommitする。完了markerは従来どおりrole/ACLと同じtransactionで作成する。

- `_fitlog_bootstrap.operation_claim` を追加。管理者fitlog_admin所有、PUBLIC/appにschema/table/列の権限なし。固定singleton主キーで1行だけ。operation UUID、account、region、environment、DB identifier、application secret完全ARN、VersionIdを保存。秘密値は保存しない。
- 初回はmetadata停止状態・TLS・DB lock・空DB/空secretを確認し、schema/claim table/claim rowを先に1transactionでcommitする。この時点ではapp roleも完了markerも作らない。
- claimは初回に一度だけ作り、自動変更・削除・期限切れ解放しない。既存claimは全対象情報が一致する同UUIDだけが使用できる。別UUIDの処理は、secret保存前に必ず拒否する。
- 秘密の生成・初回Put/readbackを行う。ClientRequestToken/VersionIdは従来どおりoperation UUID、JSON必須3keyも維持する。既存versionは同じUUIDの値だけを再利用する。
- role/ACL/完了markerを同じtransactionでcommitし、appログインを確認する。role作成時は既存claimに加え完了markerがまだないことを要求する。claim tableは継続保持する。
- session lockの生存/所有を、AWS処理の前後と秘密書込み直前にも検査する。接続喪失を検出したら失敗し再接続しない。このチェックは永続予約の代用とはしない。

## 状態と再開

| 状態 | 同UUID | 別UUID |
|---|---|---|
| claimなし・roleなし・secret空 | 初回claimを予約 | まだ初回なので同様に予約を競う。DB lock下で先着1件だけcommit |
| claimあり・roleなし・secret空 | 秘密保存から再開 | 拒否 |
| claimあり・roleなし・同UUID secretあり | 同じ値でrole/完了markerを作成 | 拒否 |
| claim/role/完了markerあり | 変更せず検証 | 拒否 |
| 未知object/不整合/結果不明 | 停止・再読取で照合。自動修復なし | 拒否 |

claim commitの結果が不明な場合は、その実行では秘密を書かず失敗終了する。接続を自動再確立せず、新しい同UUIDの実行で対象・lock・claimを再検証する。claimなしのsecret-onlyは不整合として停止する。先の処理の遅延Putが後から到着しても、予約により新しい処理は同じVersionIdしか使えず、AWSの同VersionId不変性により別passwordへの上書きが拒否される。古い処理が先に保存した場合は、その保存済みの値を同UUIDの再開処理が正本として利用する。

## 影響・代替案

追加は管理schema内の予約tableと状態検証・テスト・文書。CLI入力、秘密JSON、Web IAM、アプリAPI、Django migration、Terraform/CI/本番依存は変更しない。実AWS操作なし。既存B6は未配置のため運用データの移行なし。未知の旧schemaは引き続き拒否し自動変換しない。

代替案は環境ごとに固定のVersionIdを導出する方式だが、ユーザー指定のoperation UUID＝VersionIdという承認済み契約を変えるため採らない。DynamoDB等の新規AWS lock資源も追加しない。

## 追加検証・進め方

- 非SUPERUSERでclaimを作成し、appからのtable/列アクセスと変更が拒否されること。
- claimだけの中断、claim commit結果不明、秘密保存後の中断を同UUIDで再開できること。別UUIDの処理がPutより前に拒否されること。
- 実行Aのlease喪失と遅延Put、実行Bの同UUID再開を組み合わせ、DBとAWSCURRENTのpasswordが一致し、異UUIDの上書きがないことをSDK障害注入＋専用DBで確認する。
- 完了markerをrole/ACLと同じtransactionで作る条件、既定read-only、未知object/ACL拒否を維持する。
- 設計レビュー追加1回を受け、承認内容を変えない指摘修正後に実装へ戻る。その後、全11 checks・production smokeと残りの品質検証レビューを実施する。PRは手動相互レビュー待ちで停止する。

元の設計レビュー1回はprep/parallel-a時点で使用済み。branch改名後に予算が空でも既消費を無かった扱いにせず、追加の設計レビュー1回をユーザーへ明示して承認を求める。


## 承認と独立レビュー

ユーザーが変更案と追加設計レビュー1回を「はい、許可します」と承認。Sol/highの追加読取りレビューはHigh0/Medium1（結果不明時の再読取りの実行単位）。上記の失敗終了→新しい同UUID実行へ具体化し、承認された方式は変えず実装へ戻る。marker `HELM_REVIEW:ebcff94d5bcc78248c697f581c775ce9:document-reviewer`。元の準備branch設計1回と今回許可された追加1回を合わせ計2回、品質予算1/2は維持。
