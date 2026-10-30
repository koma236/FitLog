# F04: コメント（FL-06実装契約）

会員が記録詳細でコメントを追加し、コメント本人だけが編集・削除する。記録の作者も他人のコメントは変更できない。本文は1〜500 Unicode code points、プレーンテキストとして表示しHTMLを実行しない。返信階層・通知・管理者削除は対象外。実行結果は品質レポートへ記録する。

## API・データ

正本は[OpenAPI](../api/openapi.json)。GET/POST `/api/posts/{postId}/comments`、GET/PUT/DELETE `/api/comments/{id}`。POST201、GET/PUT200、DELETE204。認証必須、書込みはglobal CSRFとX-Social-Owner（開始時の会員UUID）が必須。headerは本人変更guardであり、操作主体はrequest.user。

POSTは固定client UUIDv4のidとbody、PUTはbodyだけ。CommentIdentityにUUID・author（削除時SET_NULL）・post UUIDを残し、削除済みIDも再利用させない。本文はIdentity OneToOne/PROTECT、Post/User CASCADE。台帳に本文は保存しない。

Commentはid/post_id/author/is_owner/body/created_at/updated_at。authorはid/username/display_name/avatarだけ。単体GET/POST/PUTはviewer_id/post_id/comment/comment_count、一覧はviewer_id/post_id/comment_count/items/next_cursor。Post作者とコメント本人がactiveな行だけを一覧・単体GET・件数へ同じ条件で含める。無効な本人のコメントはGET/他人PUT/DELETEも404。再有効化で復帰する。

## 入力・HTTP

UTF-8 application/json、raw16KiB・深さ4、未知/重複キー・不正JSON/型を拒否。CRLF→LF、残る単独CR・LF/TAB以外のC0・DEL・孤立surrogate拒否、Python strip、1〜500 code pointsの順。NFC/NFKCは行わない。前後NELはstrip、FEFFは非strip。クライアントも固定例で検証する。

unsafe CSRF失敗403はviewの前。method405→auth401→path404→owner形式400→本人不一致409→非表示/不在404→他人403→body413/415/400→最新DB再検査の順。新コードは409 SOCIAL_OWNER_CHANGED/COMMENT_ID_CONFLICT（後者はPOSTだけ）。実PK重複以外のIntegrityErrorを重複扱いしない。全応答no-store/Vary:Cookie/X-Request-Id、401にWWW-Authenticate、405にAllow。DB/session障害503でcookieを破棄。DELETEへPOST用エラーを複写しない。

## 並行操作・ページ

User→Post→Commentでロックし、active/親/所有権を再確認。JOINで別のPost作者Userを追加ロックしない。親削除で本文をCASCADE、台帳は保持。通常の同じ本人による並行PUTはロック順の後勝ちで作成順は不変。

created_at ASC,id ASC、既定20・最大50。limit不正・未知/重複queryも400 INVALID_CURSOR。署名cursorはviewer/post/末尾UTC日時+UUIDへ束縛し24h、2048bytesまで。境界行削除に依存しないtuple比較。各ページのcount/itemsは同一snapshot、ページ間は現在集合で固定全件snapshotではない。再有効化した過去行は先頭再読込で確認する。

## UI・結果不明

POST成功後は全取得ページ/cursorを捨て先頭再取得。送信本人コメントが先頭ページにないときは一覧と別の確認枠へ表示し、後続ページで同IDを取得したら枠を消す。未取得部分を連続取得済みと見せず、server cursorを使う。DELETE204後も全ページを破棄して先頭取得・見出しfocus。未送信の別draftは保持。取得だけ失敗しても既知の送信/削除成功をunknownへ戻さない。

送信前失敗は未送信として入力維持。送信後はactor/UUID/action/正規化本文を固定しreadonlyにしてGET同UUIDで照合する。一致だけ成功、本文相違は中立表示と旧snapshot保持。POST照合404なら同ID/同本文を1回だけ明示再送。再送201は通常POST成功と同じ処理。409→404や再送後404は現在非表示の終端とし、新UUIDで自動作成しない。

PUT/DELETEも照合中snapshotを固定。照合GET失敗や再操作の送信前失敗で旧unknown/actionを失わない。DELETE照合404は「現在は表示されていません」とし、guard解除・先頭再取得。照合が失敗し続けても警告dialogで明示中断できる。401/本人変更は全state破棄・再ログイン後確認。読取り/書込みcontrollerを分け古い世代の応答を破棄する。

INVALID_CURSORは本人確認1回後、同一本人なら明示先頭再読込。beforeunload警告は使うが強制終了によるmemory内UUID/draft喪失と手動再入力の重複は防げない。自動再送やdraft永続化は行わない。

## 公開前の残存課題

本文は承認済みのC0/DEL/surrogate拒否に従い、BIDI・C1（空白としてstripされるもの以外）・ゼロ幅文字は保存する。DOMの作者表示とは別のテキストとして描画しHTML実行はしないが、本文内の見た目の偽装は防げない。拒否する文字集合の拡張は今回行わず、FL-09公開前に身体情報・記録本文も含め表示/Unicode方針を揃える。

会員単位のコメント作成・いいね操作のrate limitは未導入。CommentIdentityは削除後も残るため、認証済み会員による連続作成で台帳は増える。FL-09公開前にrate limit、迷惑投稿対策、台帳保持方針を決める。現在はloopbackのlocal専用で、公開運用の準備完了を意味しない。

Django CSRFのPOST解析はviewの入力検証より先に行われる。multipartの先行解析・一時ファイルや受信総期限は既存POST/画像経路と併せFL-09公開前の課題。view内の16KiB制限をCSRF解析前の受信制限と見なさない。
