# FL-07 フォロー・検索・タイムライン設計案

本書は独立設計レビューの指摘を反映した仕様案。最新の判定・承認状態はv9 workflowを正とし、本書だけで実装・検証の成功を主張しない。

## 前提と範囲

基準commitは `947139032e84df6bb6b470c451b0d04424180aba`（FL-06、PR #12のmerge commit）。
FL-03プロフィール、FL-04記録、FL-05画像、FL-06コメント/いいねを利用する。
準備ブランチは `feat/fl-07-timeline`。FL-07は計画IDでありIssue番号ではない。
CI導入は別ブランチ `ci/github-actions` の作業。今回 `.github/`、Compose、依存lock、checks設定を変更しない。
既存の草案 F02/F06、AC-02/AC-07 を今回の範囲に具体化する。差異は本書に明記し、実装時にOpenAPIと機能文書を同期する。
通知、フォロー一覧専用画面、ブロック、非公開アカウント、AWS配置は含めない。

## 要件

- FL07-R1: 会員が他の有効な会員をフォロー・解除できる。重複・自己フォローをDBでも禁止する。
- FL07-R2: username/表示名の部分一致で会員を検索し、プロフィールへ移動できる。
- FL07-R3: ホームに「フォロー中」「すべて」を設け、記録・画像・交流状態を投稿日時の新着順に表示する。
- FL07-R4: 本人判定、非公開情報、セッション変更、通信失敗の既存の保護を維持する。

## データと整合性

`social.Follow`: UUID主キー、follower/followee（UserへのCASCADE FK、別々のrelated_name）、created_at。
`(follower_id, followee_id)` のUniqueConstraint、両者の不一致CheckConstraintをmigrationで追加する。
件数は保存せず有効な会員間の関係から導出する。検索・プロフィールでは相関集計とExistsで件数と状態を付け、joinによる件数増幅やユーザーごとの追加queryを避ける。

更新はtransaction内で操作側・対象側のUserをUUID昇順でロックし、両方の存在とis_activeを再確認する。
重複POSTは既存行を維持、DELETEは未作成でも成功。同じ2者間の反対方向の操作も同じ順序でロックする。
関係・対象のフォロワー数・操作側のフォロー数を同じtransactionで返す。未知のDBエラーを成功扱いにしない。
ユーザー削除はFK cascade、有効でない会員は検索、対象API、タイムライン、件数から除く。

## API契約

既存Cookie認証、CSRF、JSON共通エラーを使う。全APIは会員限定。

| API | 成功時の契約 |
|---|---|
| GET `/api/users/search` | `{viewer_id, items: SearchUser[], next_cursor}` |
| POST/DELETE `/api/users/{userId}/follow` | `{viewer_id, user_id, is_following, follower_count, following_count}`、200 |
| GET `/api/timeline/following` | 既存PostPage（viewer_id/items/next_cursor） |
| GET `/api/timeline/all` | 既存PostPage |
| GET/PUT `/api/users/me`、GET `/api/users/{username}` | 既存Profileにis_following/follower_count/following_countを追加 |

FollowResultの `user_id` は対象、`follower_count` は対象の数、`following_count` は操作側の数。
Profileの2つのcountはどちらも表示対象の数。更新結果のfollowing_countを他人のProfileへ代入しない。
SearchUserはid/username/display_name/avatar/is_owner/is_following/follower_count/following_countのみ。
自分も検索対象だがis_following=falseでフォローボタンを出さない。メール・身体情報・カロリー・権限情報を検索結果に含めない。
既存UserSummary（投稿/コメントのauthor）は拡張せず、検索専用schemaを設ける。
既存Profileの公開可否と厳格な型検査を保ち、GET/PUT両方のschema・client validator・fixtureを更新する。

フォロー更新は `X-Social-Owner`（正規UUID）と `X-CSRFToken` を要求しbodyを受け付けない。
viewのbody判定は既存likeと同じとする。declared_length > 0 または request.read(1) で1 byteでも読めたら、大きさに関係なく400 INVALID_REQUEST。20KiBでも400で、フォローview独自の413や閾値を設けない。
CSRFや共通middlewareのview到達前のエラー処理は既存どおり。view到達後はmethod→認証→対象UUID（不正404）→owner（不正400/不一致409）→自己操作（SELF_FOLLOW）→対象preflight（不在/無効404）→query/body検証（400）→transaction内再確認の順で固定する。
transaction内ではactor無効/不在を401、対象無効/不在を404として拒否する。owner不一致と自己操作が同時なら409、自己操作と非空bodyならSELF_FOLLOWを優先する。
owner欠落/不正は400 INVALID_REQUEST、ログイン中の本人と不一致は409 SOCIAL_OWNER_CHANGED。
CSRF失敗403 CSRF_FAILED、未認証401 AUTH_REQUIRED、自己操作400 SELF_FOLLOW、不正UUID/不在/無効な対象404 NOT_FOUND。
SELF_FOLLOWの固定文言は「自分自身はフォローできません。」とし、backend/common/errors.pyとAPI契約・テストに反映する。
不許可methodは405とAllow。フォロー更新では全queryを禁止し、未知/重複queryは400 INVALID_REQUEST。更新の非空bodyも400 INVALID_REQUEST。
409を含む応答とheaderをOpenAPIへ追加する。フォローviewの413は追加しない。新エラーが必要なら一覧を同時更新する。
`users/search` は `users/<username>` より前にルーティングする。
SOCIAL_OWNER_CHANGEDはフォローにも適用する。backend/common/errors.pyの固定文言を「ログインしているユーザーが変わりました。交流の状態を確認してください。」へ汎用化し、既存コメント/いいねの回帰テストも同期する。
docs/api/README.mdとOpenAPIのFL-06限定の説明をコメント・いいね・フォローへ更新する。

## 検索とカーソル

qは省略可（空文字）。サーバーのPython str.strip()を正本として前後空白を除去し、その後のUnicodeコードポイントで最大50文字。
クライアントは独自のtrimを行わず入力を送る。U+3000は除去し、U+FEFFは除去しない。
NUL・サロゲート・残存制御文字は400 VALIDATION_ERROR。パラメーターはURLSearchParamsで送る。
username/display_nameの大文字小文字を無視した部分一致。SQL wildcard `%` `_` とbackslashは文字として検索する。
空検索は新着会員。並びは既存Userの `date_joined DESC, id DESC` を使う（草案のcreated_atを実モデルへ対応させる）。
limitは省略20、ASCIIの `[1-9][0-9]?` に一致する整数1〜50。空・符号・小数・指数・範囲外・前後空白・先頭0（01/050）・全角など非ASCII数字を拒否する。
検索の判定順は、未知キーまたは任意キーの重複→400 INVALID_CURSOR、q内容不正→400 VALIDATION_ERROR、limit/cursor不正→400 INVALID_CURSORとする。
q重複もINVALID_CURSOR。q内容不正と未知キーが同時ならINVALID_CURSORを優先する。

新しい検索/タイムラインのカーソルはASCIIの署名値で24時間有効、最大2048文字（Unicodeコードポイント数。ASCIIなのでUTF-8バイト数と同じ）。非ASCIIはINVALID_CURSORで拒否する。
OpenAPIの検索・両タイムラインのcursor maxLengthを2048に揃える。既存の別一覧の制限は今回変更しない。
バージョン・用途・閲覧者UUID・検索では正規化後q（前後空白除去、大小は保持）・最後の日時/UUIDに束縛する。
検索/プロフィール投稿/全体/フォロー中でsaltまたは用途を区別し、他用途・他閲覧者・他検索語の流用を400 INVALID_CURSORにする。
空文字cursor、不正型、改ざん、期限切れ、timezoneなしを拒否。limit変更は許容する。
limit+1件から次カーソルを判断し、終端はnull。日時同値はUUID降順のkeyset条件で処理する。

## タイムライン

view到達後はmethod→認証→query形状→limit/cursor内容の順。許可queryはlimit/cursorだけで、未知キー・任意キーの重複は内容検証に先立って400 INVALID_CURSOR。
初期タブは「フォロー中」。自分と現在フォロー中の有効な会員の投稿を返す。「すべて」は全有効会員。
`created_at DESC, identity_id DESC`。実施日・編集日時で順番を変えない。
既存 `workouts.service.posts/dto/snapshot` を再利用し、セット、画像、公開設定、like/comment件数、is_likedを維持する。
1リクエストは既存のread-only REPEATABLE READ snapshotで一貫させる。
ページ間全体の固定snapshotは設けない。新規投稿は先頭再読込みで取得し、削除・フォロー変更は次の取得時の状態を反映する。
フォロー変更後ホームへ戻る際、タブを切り替えた際は先頭から取得する。既取得の一覧へ異なる検索/タブの応答を連結しない。
固定データでページ間の欠落・重複ゼロを保証する。ページ間に集合が変わる場合の全件固定は保証しない。

## UIと失敗時の動作

既存hash routingを維持。ホーム（#）はフォロー中、#timeline/allは全体、#searchはユーザー検索。
ルートごとの一覧の有無を以下で固定し、DOMで重複した一覧が出ないことを検証する。

| hash | 表示 |
|---|---|
| 空、# | フォロー中タイムラインのみ |
| #timeline/all | 全体タイムラインのみ |
| #search | ユーザー検索のみ。記録Feedは表示しない |
| #profile、#profile/&lt;username&gt; | プロフィールと対象会員の記録一覧 |
| #profile-edit | プロフィール編集のみ |
| #record-new、#record/&lt;id&gt;、#record-edit/&lt;id&gt; | 既存の入力/詳細/編集だけ。Feedは表示しない |
| その他（#timeline/foo、#search?x等） | ホームと同じフォロー中タイムラインへフォールバック。自身の記録Feedを別途表示しない |

プロフィール画面は従来のユーザー投稿一覧を維持する。ホームの自身の投稿一覧をタイムラインへ差し替える。
投稿作成の導線は両タブに表示する。検索は入力＋検索ボタン（Enter対応）、初回は空検索。
検索結果からプロフィールへ移動でき、検索結果と他人のプロフィールにフォロー/解除ボタン、プロフィールに両件数を表示する。
検索結果にも両件数を表示する。成功後は該当対象を更新し、一覧中の自分のfollowing_countも更新する。
送信中は二重操作を防ぎ、サーバー確認前に状態・件数を成功表示しない。

新しい読み取り・書き込み応答はviewer_idを照合する。フォロー応答はuser_idと期待した状態も照合する。
401/owner変更は古いデータと処理を破棄し既存onIdentity経路で本人を再確認、自動再送しない。
送信前の本人確認失敗は「未送信」、送信後のtimeout/5xx/不正応答は「結果不明」として区別する。
結果不明のまま逆操作を許可せず、プロフィールGETで現在の関係を確認できる。確認を中断して画面を離れる場合は既存like同様に明示確認する。
確認後の次操作直前にも本人確認を行う。後着の古い検索/タブ/別ユーザーの応答は世代番号とabortで破棄する。
既存の画像期限切れ再読込みは対象の一覧APIを再取得し、同じページID群か照合する。変わっていれば先頭再読込みを案内する。
取得中/0件/取得失敗を分離し、続きの失敗時は既読一覧を保持して同じカーソルを再試行する。
最初からの再読込み失敗を次ページ成功で置き換えない。再試行対象の操作/カーソルを記録する。
検索語変更・タブ変更時はcursorを破棄。変更前の一覧を変更後の結果と表示しない。
ボタンは操作名を明示し、キーボード操作可能。タブは選択状態を伝え、状態/エラーはstatus/alertで通知する。

## 受け入れ条件と独立テスト根拠

| ID | 観測する結果 |
|---|---|
| FL07-AC1 | A→Bの繰り返し/同時POST後は1行、DELETE後は0行。A→AはAPIとDB直書きの両方で拒否。相互A→B/B→A同時操作がdeadlockしない。件数は実関係と一致する。 |
| FL07-AC2 | Alice/ali_name/別名を固定し、大小・前後空白・空q・日本語・%・_・backslashで手書きの該当ID集合に一致する。50/51文字、limit境界、重複query、不正cursorを検証する。メール/非公開情報は含まない。 |
| FL07-AC3 | AはBだけフォロー、Cは非フォロー。followingはA/Bのみ、allはA/B/C。日時同値の固定UUIDをlimit=1で巡回し重複/欠落なくnullへ到達。編集・実施日変更で順序不変。 |
| FL07-AC4 | 他ユーザー/他用途/他qカーソル、改ざん/期限切れを拒否。未認証、CSRF、owner不一致、無効会員、削除済み投稿を検証。公開設定と交流件数は既存契約を維持する。 |
| FL07-AC5 | UIで検索→プロフィール→フォロー→ホームの表示が連動。フォロー応答の操作側following_countを対象のcountへ誤適用しない。自分に操作ボタンなし。記録作成・詳細・画像・いいねの回帰なし。 |
| FL07-AC6 | 遅延/逆順/401/409/5xx/timeout/不正bodyで古いユーザー・検索結果を表示せず、自動再送なし。続き取得失敗で既読保持、結果不明では再確認するまで逆操作なし。 |
| FL07-AC7 | PostgreSQL migration/制約、OpenAPIとのschema照合、全登録11checksが成功。件数1件/20件でquery数が件数比例しないことを検証する。未実行を成功扱いにしない。 |

## 実装計画案

v9設計レビュー→仕様/計画/Issue案をまとめた初回人間承認→正規の委任手順によるIssue作成→実装の順。
初回承認後は個人開発運用に従い、範囲内の実装・検証・レビュー・修正・commit・feature pushを追加申請せず進める。
Issue作成前のブランチは準備用。Issue番号を捏造せず、branch bindingの変更が必要なら正規controllerで再照合する。

1. DB制約とAPI境界・検索・カーソルの独立テストを先に用意し、Follow migration/service/presentation/viewsを追加する。
2. プロフィールの関係/件数を追加し、タイムラインを既存Post表現へ接続。OpenAPIとAPI契約、機能文書・ER図を同期する。
3. frontendの厳格なresponse validator、フォロー操作、検索、タイムラインと既存profile/画像/いいねの接続を実装しDOM・通信テストを追加する。
4. 登録済み11checksを実行。CI作業と共有する `fitlog-dev` のCompose/DBを同時操作しない。使用状況を確認し、そのセッションが起動したサービスだけ終了する。
5. 正規の委任手順で実装結果確認→Claude独立品質レビュー→結果確認→commit/feature push。PRは完成した内容を最終報告で確認し、mergeは人間。

担当providerは実装Codex、独立設計/品質レビューClaude。モデルはハーネス既定routeに従う。
承認前にアプリコードを変更しない。今回は仕様と計画の準備であり、CIの動作・アプリchecksの成功を主張しない。

## API草案からの具体化

- UserPage.itemsをProfile全体からSearchUserへ限定し、viewer_idを追加する。
- FollowResultにviewer_id/user_id、更新にX-Social-Ownerを追加する。
- Profileに関係と件数を追加するが、author用UserSummaryは変更しない。
- Userの日時はdate_joinedを使う。新カーソル長は既存実装に合わせ2048文字とする。
- 既存仕様の初期タブ、自己フォロー禁止、空検索、件数の意味は維持する。

## mockからの差異

- mockの入力ごとの即時検索に対し、製品は検索ボタン/Enterで実行する。入力だけでは検索リクエストを送らない。
- mockの#timelineに対し、製品は既存ホームの#をフォロー中、#timeline/allを全体に使う。
- メニューはホーム・ユーザー検索・プロフィール。mockの「仲間を探す」は製品では「ユーザー検索」と表記する。
- UIのACは本書を正とし、mockとの上記差異を不具合として扱わない。

## 初回レビュー対応と次の承認範囲

FL-07-design_review-2はMedium 3件/Low 4件により不合格。その指摘を追記後、design_review-3は形式エラーで有効な判定を取得できなかった。
出力契約修正版によるdesign_review-4では、有効なverdictを取得したがMedium 1件/Low 5件により不合格。
親がbody契約を既存likeと同じ非空400へ統一し、queryエラーコード、limit形式、SELF_FOLLOW文言、ルート表、文書状態を明確化した。この追記後の再レビューは未実施。
実装はCodex、独立レビューはClaude。各provider実行はv9既定の最大3600秒、品質レビューは通常1巡と既存上限を維持する。
修正計画と合格後の実装からfeature pushまではユーザーが条件付き承認済み。次は修正後の設計レビュー追加枠だけを確認する。
追加レビューが正規に合格した場合に限り、正規の委任手順で仕様/計画receiptを取得し、Issue作成から実装・検証・レビュー・修正・commit・feature pushまで進める。
再レビューでMedium以上が残る場合や予算超過時は追加実行せずまとめて報告する。PRは最終確認、mergeは人間。
Issue案は「feat: add follows, user search and timelines (FL-07)」。対象は本書のFL07-R1〜R4/AC1〜AC7、CIやAWSは含めない。
