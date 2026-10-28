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
