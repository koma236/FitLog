# FL-10A 撮影台本

関連: [設計](fl-10a-design.md)、[結果](fl-10a-results.md)。この台本の存在は撮影成功の証拠ではない。

## ローカル予行

`e2e/`で`npm run capture:rehearsal`。共有runtime lockの取得・自worktreeからの起動・実UI検証・停止までrunnerが担当する。通常の`npm run test:e2e`では録画しない。

1. 非録画contextでrun固有のA/BをUI登録・認証し、記録/画像を用意する。
2. 認証後のstorageStateをメモリで撮影用contextに渡し、viewportだけ録画する。認証画面と資格入力は録画しない。DevTools、address bar、OS全画面を含めない。
3. A: 自分のprofile/avatar→自己所有記録/画像→本人編集→reload。
4. B: 自分のprofile→完全なAの合成username検索→Aのprofile/follow→following→A記録→like/comment→reload。公開all一覧や広い検索は撮影しない。
   空検索は利用者一覧を返すため、条件入力中の結果行は録画用CSSでマスクする。実APIとDOMが合成Aだけの1件で一致してから解除する。マスクの使用も記録し、通常試験の表示やAPI応答は変更しない。
   followingから詳細へ進む際は、link操作後に開始した対象GET200と対象hash、詳細領域の既知投稿/コメントUI、loading解消、一意かつenabledのlike（非pressed・0件）を確認する。詳細領域内からPOSTし、pressed・1件への描画完了まで待つ。hash変更やHTTP200だけでは画面完了としない。固定stage/件数/一致boolean/HTTP status/例外分類を記録し、DOMや生例外は保存しない。
5. comment/like/followを解除。動画contextをcloseして録画停止、その後非録画contextでlogoutする。
6. ffmpegによる全frame decodeを確認する。これは人間による再生/視認確認とは区別し、視認未実施ならnot_runとする。OS file chooserのkeyboard確認も別欄に記録する。
7. ローカル動画は`.artifacts/<run>/videos-quarantine/`に保持。想定外遷移/認証画面が一度でも現れたら成功証跡にしない。安全確認前の共有/外部uploadは禁止。

撮影上限5分、2本以内。別のrunで予行する場合も追加承認後の全体11run上限（追加承認は1回のみ）に数える。資格情報は動画を含む成果物へ転記しない。撮影はE08後/E09前に独立判定する。E08の成否と別にonline・A/B本人session・対象自己所有投稿を確認できた場合だけ開始し、前提不成立ならnot_runとする。撮影/再生probeは既存runのdirectoryを再利用しない。撮影失敗でも削除検証は続けるが、全runをfailとする。

OSファイル選択の隔離手動probeはOrcaのAccessibility権限不足で未実施。専用Chromeは終了し、lock返却済み。アプリ内でSpaceキーからfilechooserイベントを開く自動確認と、OSダイアログ自体の手動確認は分けて記録する。

## 後日のAWS実証欄（今回not_run）

承認されたAWS対象とexact HTTPS originを設計/guardへ反映した後に使用する。今回のコマンドはAWSへ接続できない。

| 項目 | 記入する事実 |
|---|---|
| 承認/対象commit | 承認メッセージと完全OID |
| 実環境 | 許可されたURL、秘密なしの環境識別子 |
| 開始/停止 | 実操作・録画の開始/停止UTC |
| 内容 | A/Bの認証後操作、画像/検索/follow/交流/本人編集/reload |
| 未収録範囲 | 認証画面・資格入力・未実施の操作 |
| 再生/保管 | AWS外ローカルpath、checksum、再生結果 |
| 残置/破棄 | 自己所有データ・破棄担当への引継ぎ、環境往復結果の参照 |

AWS動画の実操作、破棄後の再生、2回の構築/破棄、課金停止/後日請求確認は別の証拠が必要。
