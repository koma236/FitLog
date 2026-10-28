# MyTimelineとの文書・技術対応

> 壁打ち用の草案。未承認・未実装・独立レビュー未実施。数値・方式は提案であり、実行結果ではない。

参照：`koma236/MyTimeline` mainのコミット `fd9f00b1eb8e7211a577babd72690c7848bbcff7`。GitHubから読み取った原本は変更していない。

## 同じ分類で作る成果物
`requirements.md`、`docs/01_overview.md`〜`14_e2e_test.md`、`docs/features/F01_auth.md`〜`F07_profile.md`、`docs/api/openapi.json`、`mock/`、`terraform/README.md`。
FitLogではv9用に受け入れ条件、task plan、manifestを追加する。

## 内容の置換
| MyTimeline | FitLogの草案 |
|---|---|
| テキスト・写真投稿 | 日付・種目・セット・メモ・写真の筋トレ記録 |
| Java/Spring/MyBatis/Flyway | Python/Django/DRF/ORM/migrations |
| JWT＋refresh_tokens | セッション・CSRF、Django標準セッション |
| JVM・GC監視 | Pythonプロセス・DB・画像処理の計測 |
| CloudFront既定ドメイン・証明書 | 同じ方式を採用。独自ドメインは購入しない |
| ECS/RDS等の構成 | 同じ主要サービスを候補に、NAT省略等の費用低減案を設計中 |
| 実装済みの説明・テスト実績 | FitLogでは未実装として分離 |

参照元のREADMEには投稿画像を未実装とする記載がある一方、ツリーには画像用migration等がある。READMEの状態だけから機能の完成度を推測せず、文書の分類・機能の難易度を参照する。

## 現段階の差
文書分類、機能別仕様、OpenAPIの入出力・エラー、8画面の操作モックを揃えた。MyTimelineの実装証跡をFitLogへ流用していない。依存版・実checks・AWS実測・Claudeの独立レビューは未完了。APIとモックの契約はレビュー前の草案として扱う。
