# FitLog Issue単位のtask plan草案

> 壁打ち用の草案。未承認・未実装・独立レビュー未実施。数値・方式は提案であり、実行結果ではない。

これは未承認の分割案。FL識別子はローカル計画IDでありGitHub Issue番号ではない。Issue、ブランチ、実行attempt、receiptは未作成。コード・実行コマンドの確定前なので実行用計画ではない。

## 担当と進行
窓口・実装はCodex、独立レビューはClaude。モデルIDをここで上書きせずハーネス既存ルーティングに従う。各Issueは通常モードで仕様→計画→実装結果→独立レビュー結果の人間承認を得る。Issue/commit/push/PRも別のterminal承認。mergeは本人がGitHubで行う。

## Issue候補
| 計画ID | 完了するもの | 前提 |
|---|---|---|
| FL-01 | ローカル基盤・API契約・品質checks | 仕様と設計の確定 |
| FL-02 | 認証とセッション | FL-01 |
| FL-03 | プロフィール | FL-02 |
| FL-04 | 筋トレ記録CRUDとセット | FL-02 |
| FL-05 | 投稿・プロフィール画像 | FL-03, FL-04 |
| FL-06 | コメント・いいね | FL-04 |
| FL-07 | フォロー・検索・タイムライン | FL-03, FL-04, FL-06 |
| FL-08 | ログ・ヘルス・運用観測 | FL-05, FL-07 |
| FL-09 | AWS構築・配置・破棄と再構築 | FL-08 |
| FL-10 | E2E・性能・撮影と最終文書 | FL-09 |

## 検証と依存
各taskの受け入れ条件・対象path・test oracleは `.ai-dev/plan.draft.json` で対応させる。画像はプロフィールと記録の両方に依存、全体タイムラインは交流件数を含めて仕上げる。初期APIは機能Issueごとにも更新し、OpenAPIのドリフトを検査する。
FL-04は筋トレの重量・回数・セットに限定し、有酸素の距離・時間を追加しない。FL-09は独自ドメインの取得を前提にせず、CloudFront提供URLの発行・再構築時のURL変更を含めて検証する。

## 初期化前に解決すること
現在はハーネス導入の未コミットファイルがあり、準備ブランチ上で草案を作っている。既存の変更を移動・破棄・commitしていない。製品Issueの実装ブランチとbaselineを確定してからworkflowを初期化し、別taskの変更を同じGit proposalへ混在させない。
checks未設定から基盤を立ち上げる手順は既存v9 controllerの前提を確認して決める。未実装のcheckコマンド、常に成功するダミーcheck、構文検査だけでアプリ品質合格にするcheckを登録しない。

## 計画の次の具体化
要件の回答を反映し、各Issueのファイル範囲・APIスキーマ・エラーコード・独立テスト根拠・実コマンドを具体化する。草案の参照検査が通っても人間承認・実行準備完了とはしない。

## Issue起票用のスコープ案
共通の流れは、仕様/計画の個別承認→Issue内容提示と個別承認→Issue作成→番号付きbranch→実装・検証→実装結果承認→Claude独立レビューと結果承認→commit/push/PRを各承認→本人merge。実装前の独立設計レビューも必要。初回手順の制約は[v9準備課題](v9-preparation.md)を先に解決する。

| Issue候補 | 対象モジュール案 | 境界・具体的な検証 |
|---|---|---|
| FL-01 基盤 | frontend/, backend/config/, backend/common/, backend/accounts/（UUIDのUserと初回migrationのみ）, Compose, lock, lint設定 | health、空DBへのmigration、lint/型/build/DBテスト。認証・業務APIは後続 |
| FL-02 認証 | backend/accounts/, frontend/auth/ | session/CSRF/期限/失効、登録重複、rate limitの共有状態。架空アカウントでAPIテスト |
| FL-03 プロフィール | accounts/profile, frontend/profile | 本人だけの編集、メール非公開。記録一覧はFL-04後に統合検証、画像はFL-05 |
| FL-04 記録 | backend/workouts/, frontend/workouts | 全セットの原子性、JST日付、他人の変更拒否。プロフィールの本人記録一覧を接続 |
| FL-05 画像 | backend/media/, frontend/upload/ | 偽装画像・サイズ・画素、競合、失敗補償とcleanup記録。S3実確認はFL-09 |
| FL-06 コメント/いいね | backend/social/, frontend/social/ | コメント所有権、同時いいね、一意制約、件数と投稿削除のcascade |
| FL-07 フォロー/一覧 | social/follows, workouts/feed, frontend/timeline/search | A/B/C固定fixture、同時刻カーソル境界、部分一致、自己フォロー禁止 |
| FL-08 運用 | backend/common/health/logging, 運用文書 | DB断でreadiness失敗、機密ログ防止、cleanupと期限切れ清掃 |
| FL-09 AWS | terraform/, 配置スクリプト・コンテナ設定 | apply/deploy/migrate/seed、default URL、撮影、destroy残存確認、再構築。見積り提示後に実操作 |
| FL-10 最終検証 | e2e/, perf/, READMEと仕様 | 全シナリオとAWS実撮影証跡の照合。追加撮影が必要な場合のみ再構築し破棄 |

各Issueは仕様変更・テスト根拠・検証結果も対象範囲に含める。API変更はOpenAPIを同時更新する。FL-03時点の記録一覧、FL-04時点の交流データのcascadeなど、後続機能が存在しない検証は後続Issueへ明示的に割り当てる。実行用manifestのACを分割し、全体ACの完了を早期に宣言しない。

FL-09で撮影と破棄を行い、FL-10で証跡を仕上げる。FL-10待ちでAWSを起動したままにしない。全体planのdepends_onは開発順序の説明であり、異なるbranchのv9 receiptを同一bindingとみなすものではない。
