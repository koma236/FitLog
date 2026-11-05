# FitLog 個人開発運用

本書はユーザー指定の運用を定め、配布元の一般ルールと共通skillに優先する。
2026-11-03の承認により、通常skillと自然言語の承認で開発する。

## 承認と自律実行

- 仕様・独立設計レビュー結果・短い実装計画をまとめて提示し、チャットで一度承認する。
- 承認には範囲内のIssue作成、隔離branch/worktree、実装、文書、検証、独立品質レビュー、指摘修正、commit、feature branchへの通常push、PR作成、mergeを含める。
- 工程ごとの再承認や専用のTTY入力を要求しない。実行結果を確認し、未実行・失敗を成功扱いしない。
- 重大な範囲変更、不可逆操作、本番反映、予算超過、原因不明で安全に進めない障害はまとめて相談する。既存development-policyの例外を適用する。
- mergeは原則AIが行う（quality-check 完了・設計との差異なしのとき。helm の development-policy『承認後の進め方』に従う）。ユーザーが作業ごとにマージしないと明示した場合はマージ前で止める。GitHub の auto-merge、trunk への直接更新、force、hook の回避は禁止。
- CI（`.github/workflows/`・`.github/ci/`）、ゲート制御面（`.ai-dev-helm.json`の`gate.controlPlane`に当たるファイル）、または宣言自身（`.ai-dev-helm.json`）を変えるPRは、常にマージ前で止める（例外X2。PR番号を示したユーザーのOKの後にAIがマージするか、ユーザーがGitHubでマージする）。
- AIがmergeするときは、ハーネスのみの差分でも運用上の免除を使わず、常にquality-checkを通して`.quality-check-passed`を作る。`gate.controlPlane`に当たる差分はhookでも免除されない。ただしCHANGELOGだけの差分や宣言前に切ったbranchなど、hookの免除を完全には消していないため、必ず次の照合を行う。
  1. `gh api user`がkoma236、`gh repo view --json nameWithOwner`がkoma236/FitLogであることを確認する。違えばmergeしない。
  2. `gh pr view <n> --json state,baseRefName,baseRefOid,headRefName,headRefOid`で、`state`がOPEN、`baseRefName`がmain、`headRefName`が`.quality-check-passed`の`branch`、`headRefOid`が同じファイルの`commit`と完全に一致することを確認する。ローカルHEADもこのcommitと一致させる。違えばmergeしない。
  3. `git fetch origin`の後、手順2を再取得し、`baseRefOid`と`headRefOid`のcommit objectがローカルにあることを確認する。`node scripts/check-pr-stop.cjs --base <baseRefOid> --head <headRefOid>`でCI・制御面・宣言自身の変更を検出する。CLIはリネーム元と先の両方、base/head両方の`gate.controlPlane`を調べる。終了0は対象なし、2はX2対象あり、1は判定失敗。対象があればPR番号・head OID・検出パスを示して止める。PR番号を示したユーザーのX2のOKの後、手順1〜3を再実行し、承認対象のheadと対象範囲が同じ場合だけ手順4へ進む。headが変わったら新しいheadへのOKを取り直す。判定失敗・object不足は原因を直すまで止め、OKで読み飛ばさない。
  4. 直前に手順2を再取得し、判定したbase/headが変わっていないことを確認する。変わっていれば手順2〜3に戻る。CIの`ci-required`成功とquality-checkの証跡を確認し、`gh pr merge <n> --merge --match-head-commit <.quality-check-passedのcommit>`で実行する。`--auto`と`--admin`は使わない。
  5. PRがMERGEDであることと統合結果を確認した後、今回のbranch/commitに対応する`.quality-check-passed`だけを削除する。失敗・結果不明を成功扱いして後始末しない。
  6. 統合後のmain更新と今回作成したworktree/branchの削除は、下記「マージ後の後片付け」に従ってAIが行う。X2でマージ前停止中は実行しない。
- mainが進んでmergeを拒否されたら、fetchして差分と失敗理由を確認する。必要ならfeature branchへ最新mainを通常mergeし、競合・失敗原因を修正して、quality-check・commit・通常push・CI成功確認・手順1〜3をやり直す。forceや`--admin`で回避しない。headが変わればX2のOKも取り直す。
- OS/sandbox権限申請は工程承認とは別に扱う。拒否時に制御を迂回しない。

## 個人環境とGitHub

- Codex は `codex-me` で起動する（`CODEX_HOME=$HOME/.codex-personal`）。
- 対象はkoma236/FitLog。CodexはCODEX_HOME=$HOME/.codex-personalを使う。会社用~/.codex、会社repo、manabi-backofficeを含むpathを探索・変更しない。
- GitHubには`gh`を使う。Issue・PR・マージなどの操作の前に`gh api user`がkoma236、対象のrepoがkoma236/FitLogであることを確認し、違えば操作しない。
- commitには~/.config/git-koma236/configの個人name/emailを使用する。共有Git設定や既定global設定は変更しない。
- 通常Gitの送信には既存SSH接続先github-koma236を使う。操作直前にoriginの実効URLがgit@github-koma236:koma236/FitLog.gitであり、SSH認証応答のaccountがkoma236であることを確認する。別のpush URLが設定されている場合も同じ照合を行う。不一致・未確認なら送信しない。
- SSH認証を確認できないとき、HTTPSや別accountへ自動切替しない。credential helperを使うHTTP操作が必要なら、個人wrapperを指す既存個人Git設定を明示し、選択を確認してから実行する。
- Issue/PR/API操作の前にgh api userのaccountとrepoを確認する。Gitの通常commandをhookへ直接提示し、送信を別scriptへ隠さない。
- 1 Issue = 1 branchを原則とし、自分の変更だけをcommitする。PR本文は通常のbody-file入力で渡す。

## 品質と実行記録

- 通常の設計・実装・test-design・quality-check skillを使う。レビュー予算と独立レビューを維持する。別モデルだけを独立性の証明にしない。
- .ai-dev/project.tomlは11 checksのコマンド台帳として残す。親は[checks実行手順](run-checks.md)に従い、採用済み共通Git管理領域を確認して `python3 -B scripts/run-checks.py` を実行する。スクリプトが排他・DB状態・migration記録・登録argv/cwd/env/timeoutの順次実行・後始末を担当する。Git/gh・snapshot対応づけ・品質合否・フラグ操作は親の担当とする。
- 各checkのid、終了コード、実行時のcommitと未commit差分の対象snapshot、日時をquality-check報告へ保存し、PR本文の検証欄へ要約する。
- checksは[並列開発運用](personal-parallel-workflow.md)の共有runtime排他枠内で実施する。スタック・port・checksは実設定を読み、他担当のDB/image/processを変更しない。
- GitHub Actionsはbuild/lint/型/全テスト/migrationとci-requiredを維持する。AIレビューはCIの判定に使わない。配布元skillの古い「CIはビルドのみ」は適用しない。
- CI相当の独立再現では別Compose projectだけでなく別image/volumeも必要。共有dev imageを上書きしない。実行済みE2Eの失敗を隠さない。
- hook登録・信頼・実clientでの実行確認を区別する。fixture結果を実clientでの採用確認と呼ばない。新運用採用後、実clientで安全なdry-run拒否を確認し、未確認clientはnot_runと報告する。
- 通常ゲート回帰は `node --test scripts/test-quality-gate.cjs scripts/test-check-pr-stop.cjs`。CIへの追加は今回行わないため、ローカル品質チェックで必ず実行する。
- `gate.denyCommands`は、見えるGraphQL `mergePullRequest`とrepository rulesetへの書込みmethod・payload指定を拒否する。宣言はcommit済みHEAD/trunkから読むため、未commitの編集だけでは有効化されない。別ツールやファイル内に隠れたGraphQL本文までの検出は保証しない。account照合やX2のOKは運用手順で確認する。

## 作業の分離

- 作業は対象worktreeを作業場所（cwd）にしたセッションで行う。本体側のセッションはworktreeの作成と引継ぎまでを担当する。引継ぎ後の設計レビュー・実装・検証・GitHub操作を、本体側のセッションから別worktreeへのpath指定だけで続行しない。マージ後の本体main更新・資源削除は下記の専用手順で扱う。
- [並列開発運用](personal-parallel-workflow.md)を正とする。1 worktreeのwriterは1セッション。他taskのrestore/stash/cleanやbranch切替を行わない。
- skillの入口は.claude/skills・.codex/skills・.agents/skillsから共通skills/を参照する。リンク不足は導入済み版のlink-skillsで整備する。
- 共有ai-dev-chatへのlocalリンクは新規導入しない。既存Rootのリンク解除は統合と採用確認後にリンクだけを対象として行い、共有sourceや共通excludeを変更しない。旧sessionへの自動反映は保証しない。

## マージ後の後片付け

AIは次の条件を順に照合する。判断できないもの・使用中のものは残して報告する。古い資源の棚卸しや一括削除はしない。stash/restore/clean、force、hookの回避は使わない。

1. マージ手順でPRのMERGED、統合commit、今回のheadが統合commitの祖先であることを確認する。対象のPR番号・head・作成したbranch/worktreeの絶対pathを作業記録と照合する。今回作成したことが確認できない資源は対象外。
2. 今回のbranch/commitに対応する品質フラグだけを除去する。checksの結果・ログ、品質報告、必要なローカル計画は削除するworktreeの外へ保存し、保存先と内容を確認する。元の証跡を失敗扱いのまま消さない。
3. 本体のpathは `git worktree list --porcelain` と共通Git管理領域から確認する。本体がmain、index/worktreeに変更がなく、未追跡ファイルがなく、他セッションの書込み・Git操作がないことを確認できる場合だけ、本体を通常fetchして `git merge --ff-only origin/main` で更新する。最新origin/mainのOIDと一致したことを確認する。branch切替・既存変更の退避・履歴の書換えはしない。条件不成立やgate拒否なら更新せず報告する。
4. 削除対象worktreeは今回作成したものに限る。tracked/index/未追跡の変更、必要なignoredファイルや未保存成果物、実行中process・container・runtime lock・他セッション利用がないことを確認する。ignoredな証跡を退避したことも確認する。使用なしを確認できなければ残す。
5. 実行するシェルのcwdを本体pathへ移してから `git worktree remove <今回の絶対path>` を通常実行する。これは対象worktreeに対する最後の操作とし、削除後にそのcwdへ戻ってコマンドを実行しない。本体側の別セッションに作業を再開させる必要はない。失敗時にforceで再試行しない。
6. 対象branchが他worktreeでcheckoutされていないこと、記録したheadから進んでいないこと、更新後mainに統合済みであることを再照合して、今回のローカルbranchだけを `git branch -d <branch>` で削除する。
7. remote branchも今回作成分だけを対象とし、account/repo/SSH照合後にremote OIDが記録headと同じでmainに統合済み、他セッションが利用していないと確認できる場合だけ通常削除する。他者による更新との競合を避ける排他を確認できない場合は残す。force・leaseによる強制更新を使わない。削除後はremote refの不存在を確認する。

セッションの利用状況はGitの一覧だけでは証明できない。引継ぎ・作業記録と生存processを照合し、確認不能なら推測で削除しない。常時許可設定は[設定案](command-permissions-proposal.md)を参照する。このPRで外部設定は変更しない。

## 旧運用の履歴

2026-11-03以前のv9専用spec/plan・設計原本・提案・receipt・実行結果は履歴として保持し、1byteも書き換えない。requirements.mdとdocs/task-plan.mdのv9手順も旧運用の記録であり、製品要件を除く運用判断は本書を正とする。
旧v9対応branchの採用や2件のPR作成は新運用の前提にしない。旧taskを再開したり消費予算を初期化したりしない。
共有runtime自体は削除しないが、新規作業でv9を実行しない。hookは旧経路全体の遮断を保証せず、この禁止は運用規則が担う。review-budget内のreceiptsは別の機構であり維持する。
