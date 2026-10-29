# FL-01 テストの根拠

根拠は docs/fl-01-foundation-design.md 改訂3とdocs/api/openapi.json。
リスクはHigh。DBの誤判定、例外・秘密の露出、UIの偽の成功が主要リスク。

- AC1: PostgreSQLの新規隔離test_fitlog DBへpytest-djangoが初回migrationを適用。
  UUID保存・再取得と再migrate前後の未適用ゼロを実DBで観測する。
- AC2: liveのDB非依存、readyの実DB・未適用migration・接続障害をHTTPで観測。
  DB障害だけ503へ変換し、未知例外は500へ変換する両側を扱う。
  DEBUG両モードの固定JSON、例外分類、応答ヘッダー、受信request-idの不採用、
  OpenAPI schema、ログと応答の秘密非露出を観測する。
- AC3: 文言は設計から直接固定。loading、200、503、通信失敗、不正JSON/HTTP、
  4999ms/5000ms境界、unmount後の遅延解決をDOMとAbortSignalで扱う。
- AC4: check定義は計画の11件。0件・skip・常時成功による代用をしない。
- AC5: READMEへ再build・DB準備・元の稼働状態を考慮する停止を記載。

この文書は期待値の根拠であり、実行済み結果の宣言ではない。
実施日時・対象snapshot・件数はv9 verifyの保存結果とPRの検証欄を正本とする。
ログは実console出力を捕捉し、api_errorとrequest-idが実際に出たという正の対照もassertする。
共有DBの物理停止とAWS・製品全体E2Eは今回対象外。

# FL-02 認証テストの独立根拠

根拠は承認済み認証設計の改訂3、正式レビューのLow判断、認証テスト設計。
HTTP期待値はsignup201/login200/me200/logout204、最小account4項目、固定エラーコードから定める。
入力や時刻の期待値を本番の定数・正規化関数・計算結果から生成しない。

- AC1: enforce_csrf_checks=TrueのHTTP境界で実UserとDBセッションを保存し、
  パスワードの照合・セッションキー変更・ログアウト後の旧cookie失効を観測する。
- AC2: 2026-10-29T12:34:56Zの成功に対し2026-11-05T12:34:56Z固定期限。
  途中のsession更新で延長せず、直前は200・到達時刻は401。CSRF欠落・旧token・unsafe非POSTを拒否する。
- AC3: trim/大小文字、usernameとemailの競合優先順、予約語、未知項目、型、長さ、
  非ASCIIメール、表示名制御文字、弱いpasswordをHTTPで観測。loginには登録強度を再適用しない。
  UserManagerとhistorical modelの移行互換テストを分け、UUID/passwordと旧空メールを保持する。
- AC4: UTC12:34:56の11回目は429/Retry-After=4、次窓は別件数。
  実PostgreSQL別接続の12同時UPSERTで許可10/拒否2、hash待機中にも別接続で加算できること、
  User rollback後にもcounterが見えることを検証する。既知制約競合と未知IntegrityErrorを区別する。
  応答時SessionStore.saveとcounterの故障注入で503/no-store/request-id/cookie削除を検査する。
  ログには実api_errorとrequest-idがある正の対照を置き、marker値の非露出を検査する。
  未知メールのdummy hash実行、inactiveと同じ401、IP正規化、環境設定の安全側分岐、清掃境界を扱う。
- AC5: DOMはサーバー境界のみ代替し、登録フォーム4項目、本人名、入力保持、二重送信、
  400/401/403/409/429/503・通信失敗・非JSONを検査する。403後はcsrf1回/POST1回、
  409後はme結果で遷移。表示名のHTML文字列が要素として実行されないことも確認する。
  FL-01の14件は抽出したReadiness実コンポーネントへ同じ期待値を維持する。

実ブラウザ→Vite→backendのcookie/CSRF往復、登録済み11checks、独立品質レビューは実行結果を別途記録する。
これらのテストの存在や構文検査だけをGREENの証拠にしない。
