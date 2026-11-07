# AWS B 成果物・稼働確認・C引継ぎ

2026-11-07、Issue #59。[承認設計](aws-b-deployment-design.md)、[既存配置手順](fl-09b7-deployment-runbook.md)。
実AWSは未実施。以下の実操作はaccount/role・対象・費用・期限・工程を別途承認した後、Aが単独で行う。Bはコード/手順の提供、Cは試験担当。

## 入力と成果物

manifest v1は既存schemaを維持。AWSモードは全工程（collect-onlyを含む）に `--artifacts /protected/artifacts.json` が必要。未指定/混在/未知key/秘密らしい値を含む不正入力はGateway接続前に固定eventで拒否する。draft/通常offline manifest検査は従来どおり。

manifest/artifact/assets/verify-input/window/証跡は実行者所有・非symlink通常file、0600（読取りは0400も可）、正規絶対path、親0700で保管する。state本文を共有せず、apply後は同じstate pathのhashだけを更新する。manifest内のapprovalは承認そのものを証明しない。

artifact record v1の完全な公開fixtureは `scripts/deployment/test_artifacts.py::artifact_fixture`。項目はrun/source/tree、backend repository/tag/local image ID/registry digest/platform/revision label、frontend inventory hash、build開始終了UTC、frontend/backend各固定種別・終了コード0。local image IDとregistry digestを混同しない。

### Aが行うbuildと確認

1. 最終統合済みのclean checkout（HEAD=承認source、tracked/index/untracked差分なし）を用意する。source tree OIDを採取する。submodule/LFSは未対応なので停止する。
2. 同sourceの `git archive` を専用0700 directoryへ展開し、そこを唯一のbuild元にする。.git、ローカルstate/.env/資格をcontextへ入れない。exportを編集しない。通常ローカルcheckoutをそのまま `docker build ... .` に渡さない。
3. exportで `npm --prefix frontend ci` → `npm --prefix frontend run build`、既存bundle.pyでassets inventoryを専用保護pathへ作る。既存production Dockerfileで `docker buildx build --platform linux/amd64 --provenance=false --load --file backend/Dockerfile.production --label org.opencontainers.image.revision=<source> --tag <専用local tag> .`。shared runtimeを触るbuildはruntime lock内で行う。
4. `docker image inspect`からlocal image ID/platform/revision labelの必要項目だけを採取。秘密を含み得るimage inspect全体やログ全文を保存しない。build失敗はrecordを成功にしない。
5. 対象ECR/送信承認を照合し、同local image IDをimmutable tag `<source>-<run UUID>` へtag付けしてpush。専用一時DOCKER_CONFIGのpassword-stdin手順は既存runbookを使う。DescribeImagesから対象registry/repository/tagのdigestを採取する。初回ECR限定plan/full applyはA所有の既存手順に従う。
6. 上記実測値でbuild recordを作成し、manifest source/image/frontendと同じ値を使う。次のoffline照合後の出力をdeployへ渡す（コマンド自身はbuild/push/AWS接続をしない）。sourceは同commitのclean checkout、assetsはbundle結果。

```sh
python3 -B scripts/deployment/artifacts.py --manifest /protected/manifest.json --record /protected/build-record.json --assets /protected/assets.json --source /absolute/clean-checkout --output /protected/artifacts.json
```

recordは署名ではなくoperatorの実作業証跡。改ざん耐性/承認の真正性を保証しない。Aが同一排他枠で採取・照合した根拠を保持する。

## 工程と停止条件

既存runbookの全AWSコマンドにartifact flagを付ける。private inspectはECR正本のtag/digestも照合。inspect→static→bootstrap-inspect→bootstrap→migrate→seed→checkの順。欠落/別run/source/hashや前段failは後段へ進めない。staticは削除せず全put成功時だけbound recordを保存。途中失敗ならpartialの可能性を残し、Aが閉鎖状態と同inventoryを照合して再送する。

Aがservice/proxy=true、public=falseを適用してmanifestのtask revision/state hashを更新後:

```sh
python3 -B scripts/deployment/deploy.py --manifest M --artifacts A --evidence E --aws-approved --step inspect --phase backend
python3 -B scripts/deployment/deploy.py --manifest M --artifacts A --evidence E --aws-approved --step verify --phase backend --verify-input /protected/database.json
```

healthは最大900秒・3秒間隔、進行中だけ待機。全read/paginationの前後と成功確定前に承認期限・単調時計期限を照合し、期限後の追加API呼出しや成功確定を禁止する。account/対象/role/network/成果物不一致、FAILED、SDK例外、期限切れは停止する。同serviceの旧taskが一時的に観測される場合はpendingとして再観測し、期待PRIMARY完了1件＋同digest RUNNING task1件＋そのprivate IP:8000のALB target healthyを待つ。ALBのliveはDB readinessの証明にしない。

Aが承認済み公開切替を行った後、public inspectを実行する。backend/public inspectはそれぞれbackend/public-health記録でprivate inspectと分離。成功済みrecordは上書きせず同一内容を照合し、inspectの観測attemptは別保存。APIのlive/readyや公開境界はCが実証する。URLは対象distribution metadataから導出したexact HTTPS originだけ。

```sh
python3 -B scripts/deployment/deploy.py --manifest M --artifacts A --evidence E --aws-approved --step inspect --phase public
```

RunTask応答不明時はintentを残し再起動禁止。Aが対象taskを確定して同manifest/step/phase/inputと `--collect-task <ARN>` で収集。bootstrap UUIDの復旧と新環境でのUUID更新を混同しない。停止・再開・秘密fixture/IP試験は既存B6/B7規則を維持する。

## C向けoffline引継ぎ

window JSONは `starts_at`/`ends_at`（offset付きUTC）とmanifestと一致する `approval_reference`。public-health完了後から承認期限内の試験窓とし、AがCの回数・時間・データ上限を別申請へ取りまとめる。CLIの値だけでは試験承認にならない。

```sh
python3 -B scripts/deployment/handoff.py --manifest M --artifacts A --evidence E --window /protected/window.json --output /protected/c-handoff.json
```

handoff v1はrun/source/image/frontend、account/region/environment、exact origin、window、artifact/manifest hash、必須工程のrecord参照/hashを持つ。証跡v2にはbackend_taskを保存し、backend/public-health/DB・公開verifyは現manifestのtask definitionと一致させる。private工程の履歴はproxy有効化前のrevisionを許容するが、旧revisionの最終health/DB証跡は流用しない。既存成功recordを新revisionで上書きして復旧せず、停止して状態に合う再開計画を作る。statusは `ready_for_c`。permissions/IPの未実施は `not_run`、総合 `verified` は生成しない。Cはこの結果と自分の実試験を分け、Bのremote collectorを再実装しない。state本文/plan/raw SDK/Cookie/passwordは共有しない。

失敗時はB/CからAへ対象と停止要求を渡し、Aだけが承認済み閉鎖/停止を実行する。AWS構成変更とCの要求送信を重ねない。再構築は新environment/state/run/bootstrap UUIDで新証跡を作る。初回のpassを流用しない。

## ローカル検証

`python3 -B -m unittest discover -s scripts/deployment -p 'test_*.py'` はAWS資格不要。通常11 checksとDB関連pytestは共通Git領域確認後の `python3 -B scripts/run-checks.py` でruntime排他を取得する。AWS/IAM/公開経路/費用の実証は別承認後に行う。
