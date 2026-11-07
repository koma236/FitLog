# Issue #64: quality-context の限定受理設計

状態: **承認済み・実装中**。2026-11-07、設計・レビュー結果・計画の提示に対しユーザー「はい、進めて良いです。」。以降の「今回」は承認前の設計作成時点を記録したもの。今回の依頼は「別イシューで設計して良いです。」であり、詳細設計・独立設計レビュー・短い実装計画をまとめて承認待ちにする。設計の作成許可を実装許可として扱わない。

## 1. 作業境界と依存

| 項目 | 固定する値・扱い |
|---|---|
| Issue / branch | #64 / `fix/quality-context-guard-64`（作成済み） |
| root / cwd | `/Users/saki/.codex-personal/worktrees/88fb/FitLog` |
| baseline / 調査時HEAD / origin/main | `9bf3b2796d63c08437981e22ea12d99260611d93`、3者一致を読取り確認 |
| writer | 本設計セッションのみ。レビュアーは読取り専任 |
| CODEX_HOME | `/Users/saki/.codex-personal`。会社用設定・repo・秘密は探索しない |
| 先行・関連 | B: Issue #59 / Draft PR #62、停止時HEAD `2e5c5502403f4e565b7efd733bf72c50eb10d118`。A #58 / C #60には書き込まない |
| 原本 | `/private/tmp/fitlog-quality-context-issue.md`（親作成、変更しない） |
| 今回の書込み | 本文書と本Issueのローカル設計・レビュー記録、正式review-budgetによる本branchの予約/受付のみ |
| 今回の禁止 | 実装、常設テスト、ゲート・宣言・登録・trust変更、commit/push/PR/merge/GitHub操作、AWS接続、Docker・DB・共有runtime操作、他worktree/他task台帳・予算の変更 |

Bの成功した11checks/CIや品質レビューは引継ぎ情報であり、本設計セッションの独立再実行結果ではない。本変更をBへコピー・cherry-pickしたり、本セッションからBのフラグを発行したりしない。承認後の#64自身の実装・品質確認・PR・手動相互レビュー・X2承認・統合が先で、Bの再確認はB担当がその時点の基準と証跡で判断する。#64の統合だけでBの品質合格が成立するわけではない。

## 2. 問題と独立確認した根拠

正式carried手順は `skills/project/quality-check/references/carried-recheck.md`。Bで拒否された入力は次のとおり。

```text
npx --no @crearize/ai-dev-helm@3.7.1 quality-context --merge-only --base origin/main --out /private/tmp/fitlog-aws-b-quality-59
```

現行hookを改変せず、公開 `parseSimple` / `classify` を読み込む局所probeで原因を独立確認した。

| 入力 | 現行結果（両コピー・posix / powershell / unknown） | 原因 |
|---|---|---|
| 上記の裸scoped package | block / rule 2 | `checkSegment` の非quoted `@` 開始語拒否（616付近）。shellによらず一律 |
| package全体を単一/二重引用符で囲う形（実測は二重引用符） | block / rule 2 | `RUNNERS` の引数 `GATE_WORD_RE` 拒否（641–645）。`--merge-only`のmergeが該当 |
| 3.7.0、任意node scriptの同フラグ | block / rule 2 | runner拒否を維持すべき対照 |
| quoted package、`--cycle 1`だけ | allow | ゲート語なしは従来の早期allow。新規の広いCLI許可を意味しない |

probe: `/private/tmp/fitlog-gate-64-probes/classify.cjs`、一次結果 `classification.json`。2コピー×3shell×5入力=30分類。hook入力として評価しただけで、helper・Git送信を実行していない。ctx=nullの分類probeであり、宣言/実repo照合や実clientでの受理を証明しない。

両実体のSHA-256は同一: `909c7d46ba02d4e1affeb523464a0173f9a9cb4ee6513555aec4c8d3712cda5d`。

優先順位は `.codex/hooks/quality-gate.cjs:2591` の `productDenied → alwaysDeny → byte budget → gate-word → 既存正規化/宣言 → parseSimple → analyzeLine/staticRules → locateCandidates/contextRules`。宣言エラーを扱う `loadGuard` / `broken` 判定もparser前にある。ここを前置きallowで短絡すると宣言による拒否を破る。

`scripts/test-quality-gate.cjs` は両hookを実processへJSON入力し、隔離Git fixture内でflagのcommit束縛、trunk/force/間接shell、制御面差分、宣言API拒否等を調べる。`scripts/test-check-pr-stop.cjs` はbase/head両宣言・rename元先・不正manifest・OID等からX2停止を確認する。今回は両スイートを実行していない。

`.ai-dev-helm.json` のversionは3.7.1。`gate.controlPlane` は `.claude/**` / `.codex/**` / `skills/**` 等を含む。`gate.denyCommands` は可視のGraphQL `mergePullRequest`、ruleset書込みmethod/payloadを拒否する。本設計は宣言自身・パラメータを変更しない。

## 3. 比較と採用判断

| 案 | 内容 | 判断 |
|---|---|---|
| A: parserで正式helperの狭い構文を識別 | 固定版・固定位置・既知option・単独実行だけをrunner検査の限定例外とする。既存宣言/拒否/分類は再利用 | **採用提案（設計者判断）**。元のCLIを使用でき、独自の判定器・依存・登録変更を増やさない |
| B: 専用node wrapper/別名scriptを新設 | 操作語を含まない別入口からhelperを呼ぶ | 不採用。任意scriptの信頼/保守範囲を増やし、正式入口との重複や間接化を生む。単にpackageをquoteするだけでもrunner拒否は解消しない |

runner一般のゲート語を緩める、raw文字列のprefix/部分一致で通す、任意版/任意パッケージ/任意node scriptを通す案は要件違反のため比較対象としない。

## 4. 受理文法（独立テストoracle）

以下は本変更が新たに受理する**閉じた集合**。文字列は大文字小文字を区別し、省略・別名は認めない。`SP` は1文字以上のASCII space/tab。コマンド外側の空白・空行は既存trim相当で除けるが、trim後に改行を含むhelperは拒否する。

```text
npx SP --no SP PACKAGE SP quality-context SP --merge-only [SP BASE] [SP OUT]
BASE := --base SP REF
OUT  := --out SP PATH
PACKAGE := @crearize/ai-dev-helm@3.7.1 （語全体の引用規則は下表）
REF := origin/main | origin/master | main | master | 小文字16進40桁OID
```

BASEとOUTは逆順も可、各0/1回。両方省略可。必須の`--merge-only`は常にsubcommand直後。最初のnpx、`--no`、subcommand、option名はunquotedの完全一致。PACKAGE、REF、PATHのみ語全体を単一/二重引用符で囲ってよい（既存lexerの安全なliteral規則を全て満たすこと）。quoteとbareの連結は不可。今回のnpx commandはlowercaseの裸`npx`のみ。

| 項目 | 規則 |
|---|---|
| packageの位置 | index 2（0始まり）に完全一致のみ。scope/name/versionの大小違い、欠落、dist-tag、range、他版、URL/file/npm alias、別位置は不可 |
| bare scoped package | `reading === 'posix'`のとき、この完全な文法に合うindex 2のみ許す。powershell/unknownはquoted必須。一般の`@word`拒否は維持 |
| npx | `--no`必須。`-y` / `--yes` / `--no-install`、追加npx option、`--package` / `-p` / `-c` / `--call`、`--`区切り、パス付きnpx、`.cmd` / `.exe`、npm exec/pnpm/yarn/node経路は対象外 |
| REF | 上記4refまたは40桁小文字OIDだけ。空/欠値/option風/任意rev式・range・reflog・特殊文字は不可。ref実在・履歴の妥当性はCLIが判定する。任意refへ拡張する必要は現要件になく、これも設計者判断 |
| PATH | 絶対ローカルパス。Unix `/`またはWindows `X:/`起点、以降はASCII英数字と`_ . - /`のみ、空component・`.`/`..` component・末尾`/`なし。既存`checkPath`を併用しネットワーク/drive-relative/OS不適合パス、`~` / `%` / backslash / 空白 / 展開を許さない。存在/実体の探索・mkdirはhookではしない |
| option | 値の分離形のみ。`--base=…` / `--out=…`、短縮/束ね/重複/未知option、`--merge-only=true/false` / `--no-merge-only` / `--since` / `--cycle` / `--check-untracked` / `--verbose` / `--help`、余剰位置引数は不可。`--since`は前回flagが既定なので今回は必要ない |

互換用の`--out`はB入力を保つため許す。調査した3.7.1 `bin/cli.js:196–211` のmerge-only分岐は `checkMergeOnly({dir,since,baseRef})` を呼ぶだけで、`argv.out`を渡さず書込みもしない。出力context packを生成する一般のquality-contextは今回対象外。PATHの型検査は将来の誤用を増やさないためで、現版の出力先安全性をhookが代行する意味ではない。

推奨するshell非依存の綴り:

```text
npx --no '@crearize/ai-dev-helm@3.7.1' quality-context --merge-only --base origin/main --out /private/tmp/fitlog-aws-b-quality-59
```

carried文書の未固定版の例は配布元一般例として残し、FitLog向けの上記限定例と受理範囲への参照を追記する。全てのnpx正式機能との互換は約束しない。

## 5. 単一コマンド・cwd・拒否の境界

例外を与えたhelperはコマンド全体で1segment・1物理行のみ。`;` / `&&` / `||` / pipe / redirect / 末尾`;` / here文法 / 入れ子shell / 環境代入 / shell呼出し演算子を付けない。複数行への書き分けや`cd … && helper`、helperを前置きした実push/mergeも拒否。通常コマンドの既存の連結許可は変更しない。

`stripTrailingOutput`が従来許す`2>&1` / `/dev/null` / `tail`等も、この例外では通さない。元入力を保存して前処理の有無を検査し、stripped結果だけを見て単独と誤認しない。PowerShellの`readPsIfOk`による書換え経路も例外不可。外側trimとCRLF外側空行の正規化だけは単独性を変えない。

cwdはhook payload（未指定なら従来のprocess cwd）そのもの。helper用の移動解析や他repoへの例外は作らない。対象worktreeをcwdにして起動するのは実行者の責任。Git repo外、ref/flagなし等はCLIが終了2で判定不能にする。未知shellをPOSIXと推測しない。PowerShell 5.1の引用・引数落ち等に影響される空語を新たに許さず、空白なしのliteral語だけを使う。cmd独自構文は対象外。

拒否する代表近似形:

```text
npx --no @crearize/ai-dev-helm@3.7.0 quality-context --merge-only
npx -y '@crearize/ai-dev-helm@3.7.1' quality-context --merge-only
npx --no ai-dev-helm quality-context --merge-only
npx --no '@crearize/ai-dev-helm@3.7.1' quality-context --merge-only --cycle 1
npx --no '@crearize/ai-dev-helm@3.7.1' quality-context --merge-only --out=out
node arbitrary.cjs --merge-only
bash -c "npx --no @crearize/ai-dev-helm@3.7.1 quality-context --merge-only"
```

これらは`--merge-only`が可視で既存判定の対象になるため拒否を保証する。ゲート語が全くない任意runnerまで検査する変更はしない（例えば`quality-context --cycle 1`は従来どおり）。一般の間接実行・alias・意図した難読化を完全に防ぐものでもない。

## 6. 実装経路・precedence・失敗

常設実装は承認後だけ行う。関数名は裁量だが、次の配置/責任は契約。

1. **既存入口と先行拒否を維持**: `main`のpayload上限/読取り、`productDenied`、`alwaysDeny`、command byte budget、既存宣言の`loadGuard`/`broken`判定をそのまま通す。helperらしい文字列でもここから先の早期allowを追加しない。宣言はcommit済みHEAD/trunkの既存取得/合成を使い、未commit宣言を新たな許可の根拠にしない。
2. **既存lexer→segment検証**: `checkSegment`で§4の語・quote・型・optionを完全に検証してdescriptorを作る。これは純粋な識別でallow返却ではない。共通`--%`拒否は維持し、bare `@`拒否だけを有効descriptorのindex 2かつposixに限定して免除。他の語の検査を飛ばさない。
3. **RUNNERS内の限定例外**: descriptorありの場合だけrunner引数のゲート語拒否を免除。`seg.kind = 'run'`のままとし、新しいGit候補や免除宣言を作らない。descriptorなしなら既存の拒否に戻す。
4. **全体形の照合**: `parseLines`のsegment/separator情報からhelperが唯一でbefore/after区切りなしと確認。さらに`classifyText`で元入力と前処理結果を照合し、内側改行・出力plumbing・PowerShell書換えを拒否。局所descriptorだけで複合コマンド全体をallowしない。
5. **既存分類を続行**: `analyzeLine` / `staticRules`等へ通常どおり進む。唯一のrunなのでGit候補なしの既存allowに到達する。helperをGit gate候補の側へ混ぜない。real push/merge/trunk/forceの分類、候補配置、controlPlane/品質flag検査は変更しない。

不正なhelper入力は既存のNotSimple/rule 2で拒否し、固定版・quoted package・単独呼出しの書き直し例を案内する。hookがhelperを試しに実行したり失敗を握って代替CLIを実行したりしない。既存のmalformed payload等のfail-open契約を本Issueで広げたり作り直したりしない。

## 7. 信頼境界と判定責任

同じ文字列のhelperが正規バイナリであることはhookの文字列分類では証明できない。PATH上の偽npx、shell alias/function、ローカル同名bin、改変cache/依存/registry設定は実行者の環境責任。hook内でnpxの解決、ネットワーク照合、hash pin検証、設定/秘密の読取りを足さない。`@3.7.1`は許可構文の固定であって供給物の真正性保証ではない。

[npm公式 npx 文書](https://docs.npmjs.com/cli/v11/commands/npx/)は、package前のoptionとpackage以降の引数の位置、version指定時の一致条件、local/cacheの実行、bin解決を説明する（2026-11-07確認）。このため`--no`はpackage前だけに固定する。`--no`をネットワーク完全遮断や供給物検証の仕組みと称さない。現行npxの実行環境を信用できない場合は実行を止める。helper版を更新するときは本allowlist・実source・oracleの再評価が必要で、自動的にmanifestの任意versionへ追従しない。

CLIの正規契約はcarried手順と調査した個人環境の3.7.1 sourceを正とする。cached package: `/Users/saki/.npm/_npx/66c2b16d94f96162/node_modules/@crearize/ai-dev-helm/`、`bin/cli.js:154–211`、`lib/quality-check-context.js:921–955`。

| 段階 | 責任 |
|---|---|
| hook allow | その文字列を実行してよいだけ。merge-only YESや品質合格を意味しない |
| CLI 0 + `merge-only: YES` | 前回flag commitと取り込んだbaseの自動merge treeがHEAD treeに一致。carried手順に入れる |
| CLI 1 / NO | 通常quality-checkへ戻る |
| CLI 2 / 判定不能、実行エラー、未実行 | 成功と扱わない。正式carried条件を満たさない |
| 品質flag | 調整役がcarried前提・Step 2–3・report等を確認して現HEADに作り直す。hookは発行しない |

CLIは作業treeやrefsを更新せず、AWSやbuildも呼ばないが、`git merge-tree --write-tree`によるローカルGit objectの生成はあり得る。絶対的な無書込み検査とは呼ばない。今回はCLI本体も実行していない。

## 8. 承認後の検証設計・独立oracle

将来実装はゲート制御面なので**Highリスク**。最重要リスクは(1)例外の広がりで実送信が通る、(2)宣言/alwaysDenyの優先順位が逆転する、(3)hook allowを正式CLI/品質flagの成功と取り違えること。実装前にtest-design skill形式のローカルメモへ本節を対応づける（規定の `docs/superpowers/plans/*-test-design.md`、非commit）。今回の常設テスト作成は行わない。

期待値は新実装のmatcherから生成せず、ユーザー要件、§4の有限文法、§5の単独制約、§6の順序、既存hook-contractをoracleに手書き列挙する。主な層は純粋分類と既存process fixture結合、加えて実clientの安全な採用確認。テストの成功で実client採用を代替しない。

| 群 | 独立に固定する入力と期待値 |
|---|---|
| 正例 | 固定版quoted単独（3shell）、bare（posixだけ）、BASE/OUT省略・個別・両方2順、quote付き値、40桁OID、space/tab → allow。flagなし/古いflag/有効flagで変わらない |
| package/npx負例 | bare（powershell/unknown）、他scope/name/版/無版/tag/range/URL/alias、npx別位置、quoted executable、大小違い、`--no`なし/後置、`-y`、`--package`/`--call`/`-c`、別runner/script → block |
| option/型負例 | 未知・重複・欠値・値をoption化・空語・余剰位置・`=`形・since/cycle/check-untracked/help/verbose、REF範囲外、PATH相対/ネットワーク/drive-relative/`..`/空白/展開/OS違い → block |
| 合成負例 | helper前後に`;`/`&&`/改行でstatus・cd・別helper・trunk/force push・実merge、末尾`;`、全種類の既存末尾redirect/pipe、nested bash/pwsh/cmd、PsIfOk、環境代入 → block。送信文字列は入力データだけ |
| 先行拒否 | fixtureのcommit済みdenyCommandsがこのhelper全文/一部に一致すればblock（flag有無どちらも）。HEAD/trunk宣言不正も既存どおりblock。alwaysDenyとhelperを含む入力もblock。uncommitted編集で許可を増やせない |
| 既存回帰 | 通常feature操作、flagのcommit束縛、trunk/force/GraphQL/ruleset拒否、制御面免除不可、別repo/cwd、入力サイズ/既存fail-open、保護branchの既存意味を維持 |
| X2 | `test-check-pr-stop`のbase/head両宣言、rename/delete、.codex/.claude実体、判定不能を維持。必要なら両quality-gateの正確なpathをfixtureで明示 |
| 責任分離 | hook process評価の前後でflag/report/refs/作業ファイルに変更なし。hookはnpxやhelperを起動しない。CLI自体の0/1/2は隔離されたローカル履歴で別途確かめ、flagが自動発行されないことを確認する |

falsification: prefixだけ照合、版比較を削除、未知optionを無視、bare @全体を免除、descriptor発見だけで複合コマンドをallow、strip後だけ単独判定、宣言より前にallow、他scriptに例外継承、のいずれにも負例が失敗することを狙う。これを未実施のmutation成功とは報告しない。

承認後は `node --test scripts/test-quality-gate.cjs scripts/test-check-pr-stop.cjs` を両hook実体で必須実行。通常quality-checkの機械チェック、必要な11checks/CI・ci-required、独立品質レビュー、test-recommendationを既存ルールどおり行い、実際の実行/未実行をsnapshotとともに記録する。共有runtimeが必要な時だけ正式排他を取得する。今回これらは未実行。

実client採用は将来、対象worktree起動のCodex/Claude各clientで読取りhelperの受理と、安全な非送信入力（例えばnested shell内の`git push --dry-run origin HEAD:main`）の事前拒否を確認する。送信操作はしない。拒否が働かなかったclientを合格と扱わず、未確認clientはnot_run。今回のtrust診断は個人設定を明示したCLIのread-only診断でResult okだが、helperの採用確認ではない。登録や外部trustの変更は設計に含めない。

## 9. 承認後の短い実装計画と停止点

1. #64のbranch/root/baseline・唯一writerを再確認し、必要な統合順を確認。test-designメモを作り、§8の正負oracleを先に既存fixtureへ追加する。実装は原則親が直接担当し、実装/探索agentは予定しない。
2. `.codex/hooks/quality-gate.cjs` と `.claude/hooks/quality-gate.cjs` を同じ内容で限定修正。`scripts/test-quality-gate.cjs` を拡張、必要なX2 pathの明示だけ `scripts/test-check-pr-stop.cjs` に追加。§6の順序を自己確認し局所回帰を通す。
3. 必要な限定文書だけ追従: hookヘッダ、`skills/project/quality-check/references/hook-contract.md` のrunner例外、`carried-recheck.md` のFitLog限定例、本設計の実装差異。供給者全体のparser更新・依存追加・CI変更・宣言/登録/trust変更はしない。
4. 既存quality-checkを完了し、両コピー同一性・snapshot・検証・独立品質レビュー・追加テスト判断を記録。承認後の独立品質レビューはquality-checkが体制/予算を決めるもので、今回のdesign 1席を転用しない。通常commit/feature push/PR作成へ進む。
5. ゲート制御面のためPR本文にprovider/実モデル/完全head OID/「相互レビュー待ち」を記し、**手動相互レビュー待ちで停止**。別providerの相互レビューを本セッションが自動起動しない。ユーザーの対象PRへの対応・再開指示後に指摘検証・必要修正と再検証を行う。
6. **X2でmerge前停止**。`check-pr-stop`でbase/headと制御面pathを示し、PR番号を示したユーザーのOKを得てから既存手順でmergeする。相互レビュー再開指示や設計承認はX2のOKを兼ねない。Bへの適用・Bの再チェック/flagはB側の別作業。

承認を求める範囲: §3–8の限定仕様と上記計画（両hook・関連fixture・限定文書の実装/検証/独立品質レビュー/通常commit・feature push・PR作成まで）。今回のセッションは承認提示で終了し、明示的な次の指示なしに実装しない。CI/宣言/登録/trust/依存追加やB/A/Cの書換えは範囲外。将来の手動相互レビューとX2の停止を残す。

## 10. 独立設計レビュー実結果・受付記録

**正式独立設計レビュー完了: High 0件、Medium 1件。設計は未承認。** Highの是正なし。Mediumは規約・今回の指示に従い本文修正や再レビューをせず、下記のとおり承認提示へ持ち越す。

### 予約・開始受付

- 正式予約: `node .codex/hooks/review-budget.cjs begin --phase design --roles document-reviewer --limit 1`。design round 1 / limit 1。
- 予約時刻: `2026-11-07T08:37:52.115Z`。
- marker（依頼文1行目に使用）: `HELM_REVIEW:76490f2c648aacb07e1cd41295a4faec:document-reviewer`。
- native `collaboration.spawn_agent` で `agent_type=helm-doc-reviewer`、`model=gpt-6.1-sol`、`reasoning_effort=high`、`fork_turns=none` を指定。追加の実装/探索agent・外部CLI reviewerは起動していない。
- bridge task_name: `helm_review_76490f2c648aacb07e1cd41295a4faec_document_reviewer`、返されたagent名: `/root/helm_review_76490f2c648aacb07e1cd41295a4faec_document_reviewer`。
- `status`で `used.document-reviewer.admittedAt = 2026-11-07T08:38:18.366Z` と開始受付を確認。receiptId: `8d560ca2ddf45e2ea9600b1404effc2c04b8c715a766e64b1ba39c9d819a0b19`。予約だけを開始の証明にしていない。
- 正式台帳: `/Users/saki/project/FitLog/.git/ai-dev-helm-reviews/7fe953e7c35168665f24df43597dd3b7545bd8b42f94ade90b547be6b2f69f7e.json`（本branch専用、公開コマンドだけを使用）。状態の手編集・初期化・extend・受付の事後付替えなし。
- 予約出力保存: `/private/tmp/fitlog-gate-64-probes/design-reservation.json`。受付status保存: `design-admission.json`（同directory）。
- レビュー対象文書のSHA-256: `88124b612bd06142caa45f086e2ed0ed2d024ea47b4d4b56740382f4e82de0cd`。レビュー後の変更は本§10への結果記録だけ。
- 上位依頼とIssue原本、本設計、既存両hook・fixtures・宣言・hook-contract・carried手順、独立レビューbrief、cached CLI/sourceを渡し、レビュアーが照合した。作者の自己レビューで代替していない。

### 実結果と保留

独立レビュアーは固定文法、先行拒否、前処理前の単独性、CLI/flagの責任分離、手動相互レビュー/X2についてHigh相当の欠落なしと報告。両hookのhash一致、branch/HEADも確認。原回答保存: `/private/tmp/fitlog-gate-64-probes/design-review-result.md`。

| ID | 重要度 | 指摘・根拠 | 扱い |
|---|---|---|---|
| M1 | Medium | §5のcwd説明は「payloadそのもの、未指定ならprocess cwd」。現行 `.codex/hooks/quality-gate.cjs:3221` は `payload.cwd` が文字列かつ存在するときだけ採用し、不存在でもprocess cwdにfallbackする。§6の既存入口維持との間に実装者判断が残る。正常/未指定/不存在cwdの期待値補足を提案 | 保留・承認提示へ記録。本文仕様への修正、追加レビューは実施しない。入口変更を要求する指摘ではなく、既存fallback維持がレビュアー推奨。実装前のtest-designで扱いを明示できる範囲と評価 |

今回の1巡の予算は消費済み。High 0なので再レビューを予約しない。Mediumを隠して無条件合格とは報告しない。設計の承認時にはM1の持ち越しも提示する。

### 今回の検証範囲

実施: branch/HEAD/baseline・dirty状態の読取り、実source/契約確認、局所30分類probe、両hook hash一致、個人環境のread-only trust診断（Result ok）、正式design予約/開始受付/独立レビュー。

未実施: 実装/常設テスト、ゲート変更、回帰スイート/11checks/build/CI、helper本体実行/実clientでのhelper受理、品質flag発行、GitHub操作/commit/push/PR/merge、AWS/Docker/DB/共有runtime、手動相互レビュー。trust診断やfixture分類を実clientでの採用と呼ばない。

## 11. 実装時の差異

承認済み§3–9の範囲で実装。M1は既存のcwd fallback維持をテスト設計へ明記。宣言不正は既存のHEADによる明示修復経路も維持し、trunk不正＋HEADでkey削除の拒否と区別して検証する。設計との差異なし。検証結果・実clientの採用状況は品質報告へ記録する。
