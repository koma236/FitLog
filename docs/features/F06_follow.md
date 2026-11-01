# 機能定義書 F06: フォロー・ユーザー検索

> FL-07の実装契約。検証結果は品質レポートに記録する。詳細は ../fl-07-timeline-design.md を正とする。

## 1. 概要 / 目的
フォロー・ユーザー検索を通じて筋トレ記録と交流を提供する。MyTimelineの同IDの責務を引き継ぎ、記録データ・Python基盤に合わせる。
## 2. 機能詳細
プロフィールと検索結果からフォロー・解除。username/表示名の部分一致。空検索は新着利用者。フォロー変更をタイムラインへ反映。
## 3. 対象画面
SCR-03, SCR-05, SCR-06
## 4. API エンドポイント
| メソッド | パス |
|---|---|
| GET | `/api/users/search` |
| POST | `/api/users/{userId}/follow` |
| DELETE | `/api/users/{userId}/follow` |
共通エラーは `{"code":"...","message":"...","fieldErrors":{},"requestId":"..."}` 。[エラー一覧と共通契約](../api/README.md)に定義する。Cookie/CSRFを使う。
## 5. データ
follows、users。[ER図](../07_er_diagram.md)参照。
## 6. バリデーション / 制約
組合せ一意、自己フォロー禁止。検索q最大50文字、limit既定20・最大50。前後空白を除去。大文字小文字を無視し%や_は文字として扱う。
## 7. エラーハンドリング / 異常系
自己フォロー400、未認証401、不在404。付与と解除の再送を冪等にし、数だけ先に成功扱いにしない。
request/response・HTTP状態・エラーコードは[OpenAPI](../api/openapi.json)に定義した契約。[受け入れ条件](../acceptance.md)を検証の根拠にする。

## FL-07 詳細契約

検索結果はid/username/display_name/avatar/is_owner/is_following/follower_count/following_countだけ。emailや身体情報を含めない。
qはPython str.strip後に最大50コードポイント。残存Ccとサロゲートを拒否し、CfのFEFFは文字として保持。
空・非空ともdate_joined DESC,id DESC。%/_/backslashはリテラル。limitはASCII整数1〜50、先頭0/空白/符号は禁止。
method→認証→query形状→q→limit/cursor。未知/重複queryはINVALID_CURSOR、q内容不正はVALIDATION_ERROR。
cursorはASCII最大2048文字、24時間有効、閲覧者・用途・正規化qに束縛し終端はnull。

更新はX-Social-OwnerとCSRF必須、全queryと非空bodyを400 INVALID_REQUESTで拒否（20KiBでも400、独自413なし）。
method→認証→対象UUID→owner→自己操作→対象preflight→query/body→transaction再確認。共通CSRF/middlewareはviewより前。
owner不正400、不一致409 SOCIAL_OWNER_CHANGED、POST/DELETEの自己操作とも400 SELF_FOLLOW「自分自身はフォローできません。」。
FollowResult.user_id/follower_countは対象、following_countは操作した本人。対象のfollowing_countへ代入しない。
両Userをpk昇順FOR UPDATEでロックし存在とactiveを再確認。対象の別書込みとの短い競合を受容する。
social_followはUUID主キー、follower/followee CASCADE FK、created_at、一意制約と自己関係禁止CHECK。
件数はactive会員間の関係から導出し、検索は相関集計/ExistsでN+1を避ける。

#searchで初回空検索、検索ボタン/Enterだけで送信。#search?x等の未定義hashはフォロー中ホームへ戻る。
検索語/タブ変更時はcursorを捨て、abort/世代で古い応答を破棄。続き失敗は既読と失敗cursorを保持。
送信前の本人確認失敗は未送信、送信後の通信/5xx/不正応答は結果不明。GET確認まで逆操作を禁止する。
確認中断には明示確認が必要。401/本人変更で古い状態を破棄し、自動再送しない。
