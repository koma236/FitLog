# v9 個人Git環境の検証記録

確認日: 2026-10-27。対象は承認済みの個人設定接続と共通ハーネス変更。
共通ハーネスのブランチは `fix/v9-personal-git-environment`、
HEADは `a35f6f8e9b8c862dfafa1dbe9a01c8570d41abe3`。変更は未commit。

## 結果

- Python構文解析: 変更6ファイルをASTで解析、成功。
- `git diff --check`: 成功。
- `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 python3 -B -m unittest discover -s tests -v`: 189件、80.636秒、成功。
- 設定パスの追加5回帰テスト: 修正前は7 subtest failure・1 error、修正後はGit操作42件すべて成功。
- テストfixture修正: ログを一時領域へ配置し、初期ブランチmainを明示。v8/provider本体は変更なし。
- Python用lint/build/mutation commandは未設定。成功扱いしない。画面/E2Eは対象外。

## 独立レビュー

quality-checkに従い、gpt-6-astra / highを使用。
1巡目は統合レビュー・反証QA・securityの3名。

| 統合指摘 | 深刻度 | 対応 |
| --- | --- | --- |
| macOSで大文字小文字違いの共有設定パスを受理 | High（他2名はMedium） | casefoldで禁止パスを比較 |
| gitdir/commondirのsymlinkと親参照が正規化で隠れる | High | lexical componentを順番に検査後、親参照を処理 |
| ghのhosts.yml/config.ymlがsymlinkでも受理 | Medium | 内容を読まずmetadataでsymlink・非通常ファイルを拒否 |
| Git parserがhomeのrepository設定を探索 | Medium | 空の一時ディレクトリと探索上限を使用 |

2巡目は検証レビューと反証QA。両名とも未解消High/Mediumなし。
検証レビューはGit操作42件を独立再実行。QAは合成fixtureの21プローブを独立実行、全成功。
通常のlinked worktree、空白を含むpath、gh設定本文の非読取りも確認した。
全変更11ファイルとreview snapshot、HEAD・diffの一致を確認。
無関係な未追跡48ファイルは変更に含めず、`untracked-check: OK`。
レビュー回数はquality 2/3。これらはv9 provider attemptや人間承認receiptではない。

## 実環境の読取り診断

追加exportなしで実際の `PersonalGitEnvironment.load` とv9のrunnerを使用。

- profile: `~/.ai-dev-harness/personal-git.toml`。
- gh: `~/.config/gh-koma236`、Git: `~/.config/git-koma236/config`。
- GitHub API login: `koma236`。
- repository: `koma236/FitLog`、権限ADMIN。
- 実効fetch/push origin: `https://github.com/koma236/FitLog.git`。
- `git ls-remote` のmain参照取得: 成功。
- 既存codex-me関数は個人CODEX_HOMEを指定。隔離shellで同じ関数のversion実行を確認。
  iTerm2の新規対話セッション自体は未実行。

tokenの表示・コピー、既定ghの認証切替、会社設定の変更は実施していない。
同一ユーザーによる並行改変やOS隔離は保証対象外。

## 残る本人操作と前提

Codex projectはtrustedだが、hook 3件は未信頼。初回に本人が `/hooks` で信頼する。
Claude新規セッションでのskill/hook実行確認は未完了。
FitLogのchecksは空、`V9_CONFIG_NO_CHECKS`、`execution_ready=false`。
技術スタック・仕様・計画・各人間承認の前提は今回のテストでは満たした扱いにしない。
Issue・commit・push・PR・mergeは未実施。合格flagや承認receiptは生成していない。

## 一時検証資料

全体テスト出力は `/private/tmp/fitlog-harness-final-tests.log`。
review contextとsnapshotは `/private/tmp/fitlog-quality-check/cycle-2/`。
一時資料は将来削除され得るため、本書に結果を記録する。
