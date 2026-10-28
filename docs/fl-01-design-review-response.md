# FL-01 設計レビュー対応（改訂2）

2026-10-28。FL-01-design_review-2のClaude判定は不承認。High 1、Medium 5、Low 6。以下は修正内容であり、修正版の独立レビュー合格を意味しない。

| ID | 重要度 | 指摘 | 修正 |
|---|---|---|---|
| FL01-D2-01 | High | Userの主キー型がUUID契約と未整合 | 初回migrationでUUIDFieldを明示。保存・再取得とUUID型をAC1に追加。後続のemail制約はFL-02へ割当 |
| FL01-D2-02 | Medium | readyがmigration未適用を見ない | 実DB照会＋MigrationExecutorの未適用なしを200の条件にし、未適用503を追加 |
| FL01-D2-03 | Medium | request-idとJSON404/500が不明 | サーバー生成UUIDのヘッダー・body一致、固定メッセージ、APIエラーハンドラーを定義 |
| FL01-D2-04 | Medium | migrationの再実行を検証しない | PostgreSQLテストDBで適用後にmigrate再実行と未適用0をassert。開発DB用migrate checkも追加 |
| FL01-D2-05 | Medium | compose runが依存サービスを起動 | 全10 checksに--no-deps。postgresのみ明示起動、元の稼働状態に応じた停止を定義 |
| FL01-D2-06 | Medium | bind mountと古い依存で誤検証 | bind mountなし、/opt/venvとイメージ内node_modules、lock照合、Dockerfile別ignore、検証前buildを定義 |
| FL01-D2-07 | Low | DB切断注入が共有DBへ影響 | unit/結合テストは照会箇所のOperationalError注入。実DB停止はFL-08の専用環境 |
| FL01-D2-08 | Low | frontendの状態オラクルが曖昧 | readyを対象とし、loading/ok/503/通信失敗/不正応答のroleと固定文言を定義 |
| FL01-D2-09 | Low | lint/型の厳しさが不明 | mypy strictとDjango plugin、Ruff E4/E7/E9/F/I/B/UPを指定 |
| FL01-D2-10 | Low | accountsの作業割当が不一致 | task-planのFL-01にUUID Userと初回migrationのみを追加 |
| FL01-D2-11 | Low | ready 503のヘッダー宣言不足 | OpenAPIへX-Request-Idを追加。bootstrap前の契約変更として固定 |
| FL01-D2-12 | Low | 古いv9制約説明との不整合 | v9-preparationと設計へmain 308a7f0/PR #7の新経路導入を追記 |

参照sourceのSHA-256と実行planを更新。manifestのquestionsは製品上の未解決事項に限定する。採用承認自体はv9仕様・計画gateで別途取得し、spec_readyと人間承認を混同しない。

## 返答形式とレビュー枠

初回design_review-1はinvalid_result。元の返答本文が残らないため原因は断定しない。JSON schemaが文字列内改行を許す一方で既存validatorが拒否する不整合をローカルで再現した。正式run_jobのadapter_factoryを使う外側transportに、既存validatorと同じ文字列制約と出力指示を追加した。返答内容の書換え・合否閾値の変更・receiptの直接編集は行っていない。

ユーザーの「よいです」を根拠にdesign枠を1巡だけ正式extend。接続コードの引数誤りはadapter構築時に発生し、attempt開始・Claude起動・追加席消費の前に停止した。正式入口の同一引数で検査して修正し、同じpendingのdesign_review-2を実行。99秒で判定を正常取得し、review_rejectedとして保存された。第1巡の失敗、拡張記録、第2巡の不承認を保持する。

修正版の独立確認には新たなレビュー枠が必要。既存2巡の結果を再使用・書換えせず、無断のextendや別providerの未計上レビューは行わない。

## 第3巡の結果と改訂3

ユーザー承認「yes」により追加1巡を正式extendし、FL-01-design_review-3を実行した。98秒で不承認。前回のUUID主キー等の反映は確認され、High 0、Medium 2、Low 8となった。修正版の合格や仕様承認はまだない。

| ID | 重要度 | 指摘 | 改訂3の対応 |
|---|---|---|---|
| FL01-D3-01 | Medium | 事前buildとDB起動・待機・停止が文章だけ | compose-buildを先頭の必須checkに追加し全11本へ。CodexをDB準備担当とし、psの状態取得、up --no-recreate --wait --wait-timeout 60、finallyでの条件付きstop、image inspectによるID記録を具体化 |
| FL01-D3-02 | Medium | 405/406/415等の共通codeが未決 | 例外→HTTP/code表とOpenAPI enum/response定義を追加。health POSTの405・Allow・request-idをAC2に追加 |
| FL01-D3-03 | Low | DEBUG=Trueでは標準handlerがHTMLになる | API末尾catch-all、process_exception、既存HTMLエラーの境界正規化を明記。DEBUG両モードで確認 |
| FL01-D3-04 | Low | readinessのtimeoutがmigration等へ影響 | connect_timeoutは5秒、statement_timeoutはreadyのatomic内SET LOCALで2000msだけ適用 |
| FL01-D3-05 | Low | uv runが検証中に依存を同期する | build時dev groupを含むuv sync --locked、全backend checkを--frozen --no-syncへ |
| FL01-D3-06 | Low | fetchが終わらない | AbortControllerの5秒timeout、unmountでabort、fake timersによるDOM確認 |
| FL01-D3-07 | Low | check定義ファイルの参照不足 | Dockerfile/個別ignore、初回migrationの具体ファイル、conftest、frontend設定をdefinition_pathsへ追加。ディレクトリではなく実ファイルを宣言 |
| FL01-D3-08 | Low | SECRET_KEY等の設定方針が不明 | 環境変数必須・未設定失敗、DEBUG=false既定、localhost/127.0.0.1/backend、開発用キーと本番の分離を明記 |
| FL01-D3-09 | Low | RDSのDBメジャーと未整合 | FL-09も17系前提とし、変更時はローカルも同時に追従・再検証する方針を追加 |
| FL01-D3-10 | Low | manifest 9とplan 10の形式差 | 意図した契約であり不具合ではない。正本と実validatorにより確認し、説明を設計へ追加 |

第3巡後のコード生成・checks登録・承認receipt生成は行っていない。改訂3を独立に確認する枠はまだ承認・予約していない。過去の3巡を保持する。
