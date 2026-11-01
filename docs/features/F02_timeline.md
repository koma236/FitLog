# 機能定義書 F02: タイムライン

> FL-07の実装契約。検証結果は品質レポートに記録する。詳細は ../fl-07-timeline-design.md を正とする。

## 1. 概要 / 目的
タイムラインを通じて筋トレ記録と交流を提供する。MyTimelineの同IDの責務を引き継ぎ、記録データ・Python基盤に合わせる。
## 2. 機能詳細
フォロー中は自分＋フォロー先、すべては全会員。created_at DESC,id DESC。実施日の遡及入力でも投稿日時順を変えない。初期タブはフォロー中。
## 3. 対象画面
SCR-03
## 4. API エンドポイント
| メソッド | パス |
|---|---|
| GET | `/api/timeline/following` |
| GET | `/api/timeline/all` |
共通エラーは `{"code":"...","message":"...","fieldErrors":{},"requestId":"..."}` 。[エラー一覧と共通契約](../api/README.md)に定義する。Cookie/CSRFを使う。
## 5. データ
posts、users、follows、likes、comments、workout_exercises、workout_sets。[ER図](../07_er_diagram.md)参照。
## 6. バリデーション / 制約
limit既定20・最大50。次カーソルはnullで終端。編集で順序を変更しない。件数・自分のいいね状態を含む。
## 7. エラーハンドリング / 異常系
不正カーソル400、未認証401。通信失敗と0件を分け、既読一覧を消さず再試行できる。
request/response・HTTP状態・エラーコードは[OpenAPI](../api/openapi.json)に定義した契約。[受け入れ条件](../acceptance.md)を検証の根拠にする。

## FL-07 詳細契約

ホーム#は初期タブ「フォロー中」、#timeline/allは「すべて」。会員限定で前者は自分と現在のフォロー先、後者は全有効会員の記録。
created_at DESC,identity_id DESCのkeyset。編集日時/実施日で順序を変えず既存Post DTO・画像・公開設定・交流状態を維持。
各ページはread-only REPEATABLE READ。固定集合で欠落/重複なくnullへ到達。ページ間の削除/投稿/関係変更では全件固定を保証しない。
cursorはASCII最大2048文字、24時間有効、閲覧者と用途に束縛。limitはASCII整数1〜50、既定20、先頭0/空白/符号を拒否。
method→認証→query形状→limit/cursor。未知/重複queryは400 INVALID_CURSOR。
フォロー後ホームへ戻る時とタブ切替時は先頭取得。検索画面に記録Feedは表示せず、プロフィールは対象会員の記録のみ。
両タブに記録作成導線。続き失敗では既読を保持し同じcursorを再試行。先頭失敗を続き成功で置き換えない。
画像の期限切れは同じ取得元ページAPIを1回再取得しID列を照合、変化時は先頭再読込みを案内する。
