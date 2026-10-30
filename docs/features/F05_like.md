# F05: いいね（FL-06実装契約）

会員がカード・詳細でいいねを付け解除する。自分の記録にも可能。ハートとaria-pressed、件数で示す。通知・付与会員一覧は追加しない。実行結果は品質レポートへ記録する。

## API

POST/DELETE `/api/posts/{postId}/like`、いずれも200。viewer_id/post_id/is_liked/like_countを返す。セッション認証・global CSRF・X-Social-Owner必須。headerは本人変更guardであり主体はrequest.user。

bodyは0bytes、Content-Type不要。非空body/不正owner400 INVALID_REQUEST、本人不一致409 SOCIAL_OWNER_CHANGED、不在/無効Post作者404、未認証401、CSRF失敗403、予期しない障害500、DB/session障害503 SERVICE_UNAVAILABLE/cookie破棄。Retry-Afterや画像処理中コードは返さない。全応答no-store/Vary:Cookie/X-Request-Id、405にAllow、401にWWW-Authenticate。正本は[OpenAPI](../api/openapi.json)。

## 整合性

LikeはPost/User CASCADE、(post,user) UNIQUE。User→Postロックで有効な本人/親を再検査する。二重POSTは1行、二重DELETEは0行。付与/解除の競合はロック順に確定。件数を加減算保存せず、有効な会員のLike行を数える。無効会員分は除外し、再有効化で復帰。Post DTOも同じ集計/自分の状態を返す。コメントとのJOIN積やN+1を避ける。本文・画像・更新日時・energy・公開設定は不変。

## UI・失敗

成功前に状態や件数を反転しない。意図とactorを固定し、本人確認→CSRF→送信。二重押下を防ぎshared busy tokenでnavigation/logout保護、10秒timeout、unmount abort、古い応答破棄。

結果不明なら記録DTOを明示取得して確認する。未確定のまま逆操作を自動送信せず通常toggleを無効にする。成功でlike_count/is_likedだけを更新し、comment draftや画像を上書きしない。本人変更/401は全操作state破棄。CSRF更新後も再操作は明示操作だけ。

公開前のrate limit・台帳保持方針とCSRFによるPOST先行解析の制約はF04「公開前の残存課題」を参照。

状態確認が失敗し続ける場合は「確認を中断」で警告dialogを表示する。明示確認した場合だけアプリ内の遷移/操作guardを解除する。付与/解除を成功と断定せず、表示中の通常toggleは結果不明のまま無効を保つ。状態確認GETは継続でき、逆操作や自動再送はしない。記録を開き直した場合は最新DTOから開始する。
