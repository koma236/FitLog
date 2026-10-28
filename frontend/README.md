# FL-01 frontend

このREADMEは起動・検証の手順書です。実施日時・対象snapshot・image ID・テスト件数は、
v9 verifyの保存結果とPRの検証欄を正本とします。手順の記載だけで合格を示しません。

React / TypeScript / Vite。実装するのはreadyの状態表示だけ。
認証・記録画面・AWSは後続タスク。

| readyの結果 | role=statusの文言 |
|---|---|
| 初期状態 | 確認中 |
| 200かつstatus=ok | 利用可能 |
| 503かつstatus=unavailable | 準備未完了 |
| 通信失敗・5秒timeout | 接続できません |
| 不正body/status・その他HTTP | 応答を確認できません |

状態要素は単独のrole=status。AbortControllerで5秒・unmount時にabortし、
期限後・unmount後の応答では表示を更新しない。テストはDOMを独立の設計文言と照合する。
5秒timeoutとunmountにはfake timersと遅延応答を使う。実行結果はPRの検証欄を参照してください。

`/api` はViteから `http://backend:8000` へproxyする。同一オリジンで通信し、
秘密・tokenをlocalStorageへ保存しない。

## 再build・起動停止とchecks

共通の詳細手順は [backend README](../backend/README.md) を参照。
具体版/digestを固定し、`Lockfile.Dockerfile` で初回package-lock.jsonを生成した後、
アプリbuildでは必ずnpm ciを使う。hostへnpm installせず、hostのnode_modulesもmountしない。

ポート127.0.0.1:15173と127.0.0.1:18080が使えることを事前に調べる。
他プロジェクトを止めない。rootで両イメージを再buildし、postgresをhealthyまで待ち、
backendのmigrateを実行してからbackend/frontendを起動する。
通常停止は今回起動したサービスだけへstopを指定し、DB volumeは削除しない。

後続verifyは先頭のcompose-buildを含む全11件が対象。frontend単独のchecksはDB不要。
backendを含む全体verifyではpostgresを明示的に準備する。開始前の状態を保持し、
元からrunningなら終了時も停止しない。開始前に停止/未作成だった場合だけfinallyでstopする。
競合操作・不明な状態では勝手に停止せず報告する。

予定されたfrontendコマンドは次の4件。すべてイメージ内で実行する。

```sh
docker compose --project-name fitlog-dev -f compose.yaml run --rm --no-deps frontend npm run lint
docker compose --project-name fitlog-dev -f compose.yaml run --rm --no-deps frontend npm run typecheck
docker compose --project-name fitlog-dev -f compose.yaml run --rm --no-deps frontend npm run test -- --run
docker compose --project-name fitlog-dev -f compose.yaml run --rm --no-deps frontend npm run build
```

コード・lock変更後は再buildが必要。bind mount・依存volumeはなく、各checkでhostの依存を変更しない。
`--service-ports` は指定せず、既存devサーバーがあっても新しいhost portを割り当てない。
実行結果はPRの検証欄を参照してください。この手順や提案ファイルだけでは品質合格になりません。
