# 初回開発の順序修正：独立設計レビュー第1回の記録

ユーザーは今回のハーネス改修に限り既存review経路の利用を許可済み。通常terminalの確認は維持する。v9の承認receiptは作成しない。

- 対象：`/Users/saki/project/ai-dev-harness`
- 読み取り対象branch：`fix/v9-personal-git-environment`。既存の未コミット変更は保持。今回の実装branch作成は未実施。
- 依頼：`.ai-dev-jobs/v9-first-project-document-reviewer.md`
- 設計書の固定コピー：`.ai-dev-jobs/v9-first-project-design.md`
- schema 1 job：`.ai-dev-jobs/v9-first-project-design-review.json`
- reviewer：Claude、既存ルート `opus`。worker起動なし。
- review-budget：design / document-reviewer、round 1 / limit 1 を予約済み。再予約・重複起動しない。
- job形式、taskのサイズ上限、branch条件、端末確認を省略しないコマンド構築を検査済み。下記runでproviderの実行を確認した。
- 改修前の全テスト：`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests`、189件、105.346秒、終了コード0で成功。末尾のCANCELLEDは非対話拒否を確認するテストfixtureの出力であり、実レビューの取消ではない。

通常terminalで実行するコマンド：

```sh
cd /Users/saki/project/ai-dev-harness
CODEX_HOME="$HOME/.codex-personal" PYTHONDONTWRITEBYTECODE=1 python3 scripts/ai_dev_handoff.py .ai-dev-jobs/v9-first-project-design-review.json
```

最初にテスト開始確認、その後Claudeレビュー開始確認がある。本人が表示内容を確認して入力する。AIは入力・パイプ送信を代行しない。

設計書SHA256：`1ff6fe3fbfdb94e635a0119dc3adf826f9f2df73e3dfb4c6e3c0582c7b390fe2`
依頼SHA256：`befc0c99d18af74589530f4e37eeccf270bbe7912e66d0ce533814a083d5faf6`

結果取得後は指摘を現行コードと照合し、設計修正とユーザーへの説明を行う。設計レビュー結果を実装合格・Git操作許可と読み替えない。追加レビューが必要なら既存の上限手順を守る。

## 実行確認

個人用実行ログ `~/.local/state/ai-dev-harness/runs/20261027T060204Z-c302e27a.json` を確認。

- dry_run=false、worker未起動、reviewer_actual_models=[claude-opus-5-5]。
- テスト189件成功、test_exit_code=0。
- review_exit_code=0、review_approved=false、finding_count=10。
- status=human_review_required。レビュー正常終了と設計の合格を区別する。

現行harness.pyはverdict本文を標準出力に表示し、実行ログには承認可否・件数のみ保存する。指摘本文・重要度は未取得。ユーザーのターミナルに表示されたReview JSONの提示を依頼する。未取得の指摘を推測で修正したり、同じjobを再実行して再レビューを増やしたりしない。

その後、ユーザーからverdict全文を受領。High 1 / Medium 7 / Low 2を確認し、[対応表](v9-first-project-review-response.md)と[改訂設計](v9-first-project-design-v2.md)へ反映した。初回jobを再実行していない。追加レビュー・コード実装は未実施。

## 第2回：追加承認と準備

ユーザーの「OKです」に基づき、正規extendでdesign上限を1から2へ拡張し、round 2 / limit 2を予約した。追加providerは未起動。ハーネス本体・初回jobは変更していない。

- job：`.ai-dev-jobs/v9-first-project-design-review-r2.json`
- task：`.ai-dev-jobs/v9-first-project-document-reviewer-r2.md`
- 固定設計：`.ai-dev-jobs/v9-first-project-design-v2-r2.md`
- 対応表：`.ai-dev-jobs/v9-first-project-review-response-r2.md`
- 設計SHA256：`610f02a2e9f0e7d30fa0ea7da3ae2e756099a1b915f3e047bb6284569156fd5d`
- task SHA256：`6dde8f717f252e936ea8d44fba2a5d6a87ed89d31d14fe4af0e6214635cae99f`

schema 1 validator、taskサイズ上限、marker、review-only、端末確認を省略しないコマンド構築、既存ルートClaude opusを確認済み。今回変えたのはレビュー資料だけなので、別途の回帰テスト再実行はしていない。本人が起動する既存handoffが全テストを実行する。

```sh
cd /Users/saki/project/ai-dev-harness
CODEX_HOME="$HOME/.codex-personal" PYTHONDONTWRITEBYTECODE=1 python3 scripts/ai_dev_handoff.py .ai-dev-jobs/v9-first-project-design-review-r2.json
```

本人が2回の開始確認へ応答する。終了後は`Review: { ... }`のsummary/findingsを提示してもらう。既存ログは本文を保存しないため、終了報告だけから指摘内容を取得できるとは案内しない。

## 第2回の結果と指摘対応

実行ログ`20261027T063928Z-29f34f5b`を確認。実モデルClaude Opus 5.5、worker未起動、テスト189件成功、review_exit_code=0、review_approved=false、finding_count=5。ユーザー提示のverdict全文でHigh 0 / Medium 2 / Low 3と初回Highの解消を確認した。

残る5件を[設計v3](v9-first-project-design-v3.md)へ反映し、[第2回対応表](v9-first-project-review-response-r2.md)を作成。修正版資料はハーネス内`.ai-dev-jobs/v9-first-project-corrected/`へ同じbasenameでコピーし、コピー先のリンクと元文書とのbyte一致を検証済み。新job・第3回予約・provider実行は行っていない。旧入力資料は保持した。

設計v3 SHA256：`c0c8d7403f300cfaf5dcd1172b4831e708b07705a4afb47df46bfa2a9d6b8873`
第2回対応表 SHA256：`ddc5a70e57cd297e21677b6773478672bf1ae59a1fd1a4baf12eaa43a4a0474a`

現在は修正設計に対する人間の承認待ち。Claudeの第2回判定を合格へ書き換えず、実装コード・実行state・Git操作への移行はまだ行わない。
