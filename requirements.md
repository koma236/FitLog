# 要件定義書サマリ - FitLog

> 壁打ち用の草案。未承認・未実装・独立レビュー未実施。数値・方式は提案であり、実行結果ではない。

学習・ポートフォリオ用の筋トレ記録・交流アプリ。認証、RDBの関連、画像保存、AWSへのデプロイを説明・実演できることを目的とする。

## 確定している依頼
- AWSとフロントエンドのTypeScriptを継続し、MyTimelineから技術の一部を変える。
- 認証、いいね、コメント、フォロー、画像アップロードを扱う。
- AWSは低費用を優先し、構築→デプロイ→動作動画の撮影→destroy→再構築を可能にする。
- 初版の運動範囲は筋トレ中心。ランニング等の距離・時間の記録は含めない（ユーザー回答で確定）。
- 独自ドメインは購入せず、MyTimelineと同じCloudFront提供ドメインと既定証明書を利用する（ユーザー回答で確定）。
- MyTimelineと同じ分類・ファイル構成の仕様書、機能定義書、UIモック、運用文書を作る。
- Codexが窓口・実装、Claudeが独立レビュー。モデルは共通ハーネスの既存ルーティング。v9通常モード。

## 提案中の初版
筋トレの種目・重量・回数・セットを1回のトレーニングとして記録し、その記録が投稿になる。全記録はログイン利用者全員に公開する（ユーザー回答で確定）。自己用の非公開記録と公開投稿を分ける機能はまだ採用しない。
例：2026-10-27、ベンチプレス、60kg×10回を3セット、メモ、写真。
有酸素の時間・距離は初版対象外として確定。体重管理、食事、AI、通知、DM、動画投稿も初版の候補から外す。

## 機能一覧
| ID | 機能 | 定義書 |
|---|---|---|
| F01 | 登録・ログイン・ログアウト | [認証](docs/features/F01_auth.md) |
| F02 | 全体・フォロー中タイムライン | [タイムライン](docs/features/F02_timeline.md) |
| F03 | 筋トレ記録・画像・本人による編集削除 | [記録](docs/features/F03_post.md) |
| F04 | コメント・本人による編集削除 | [コメント](docs/features/F04_comment.md) |
| F05 | いいね・解除 | [いいね](docs/features/F05_like.md) |
| F06 | フォロー・解除・ユーザー検索 | [フォロー](docs/features/F06_follow.md) |
| F07 | プロフィール表示・編集 | [プロフィール](docs/features/F07_profile.md) |

## ドキュメント構成
| ファイル | 内容 |
|---|---|
| [01_overview](docs/01_overview.md) | 概要・スコープ・用語 |
| [02_tech_stack](docs/02_tech_stack.md) | 技術比較と候補 |
| [03_usecases](docs/03_usecases.md) | 利用者と操作フロー |
| [04_features](docs/04_features.md) | 機能要件とREQ識別子 |
| [05_nonfunctional](docs/05_nonfunctional.md) | 品質・権限・性能 |
| [06_ui_design](docs/06_ui_design.md) | 画面・状態・遷移 |
| [07_er_diagram](docs/07_er_diagram.md) | ER図・テーブル・制約 |
| [08_constraints](docs/08_constraints.md) | 前提・未決事項 |
| [09_infrastructure](docs/09_infrastructure.md) | AWS・デプロイ・破棄 |
| [10_logging_design](docs/10_logging_design.md) | ログ |
| [11_monitoring_design](docs/11_monitoring_design.md) | 監視 |
| [12_incident_response](docs/12_incident_response.md) | 障害対応 |
| [13_performance_test](docs/13_performance_test.md) | 性能検証 |
| [14_e2e_test](docs/14_e2e_test.md) | E2E・撮影シナリオ |
| [API](docs/api/openapi.json) | OpenAPI草案 |
| [UIモック](mock/README.md) | ブラウザで開く画面草案 |
| [Terraform運用](terraform/README.md) | 構築・配置・破棄の契約草案 |
| [受け入れ条件](docs/acceptance.md) | 観察可能な合否条件 |
| [task plan](docs/task-plan.md) | Issue候補の分割・依存・検証 |
| [MyTimeline対応表](docs/mytimeline-parity.md) | 参照元と差分 |

v9入力は `.ai-dev/spec.draft.json` と `.ai-dev/plan.draft.json`。未決事項を解決してレビューするまで草案として扱う。SHA-256は原本の整合性検査用で、人間の承認receiptではない。
## 準備状況へのリンク

[API共通契約](docs/api/README.md)、[操作モック](mock/README.md)、[Issue計画](docs/task-plan.md)、[v9初回準備の課題と対応案](docs/v9-preparation.md)。製品実装・AWS構築・独立レビュー・Git操作は未実施。

