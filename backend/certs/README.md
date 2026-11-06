# RDS東京公開CA

2026-11-06、AWS公式HTTPS配布元から取得。

- URL: https://truststore.pki.rds.amazonaws.com/ap-northeast-1/ap-northeast-1-bundle.pem
- SHA256: `d1df75221341812a657d7c7b070ff61ce78824fbf05acf499f7e394f5ff58d50`
- 対象: PostgreSQL/RDS `rds-ca-rsa2048-g1` を含む東京の公開root bundle。秘密鍵は含まない。

SHA256はTLSで取得した配布物を固定する値であり、AWSが別途公表したchecksumとは扱わない。Docker build時にSHA256SUMSで検査し、起動時にdownloadしない。

`python3 -B backend/tests/production_ca_smoke.py` はhash、CA parse、期限、東京RSA2048 G1、各rootの自己署名を検査する。更新時はAWS原典と変更を照合し、PEMとSHA256SUMSを同じ変更で更新してimageを再buildする。実RDSのCA/engine対応とverify-full接続は配置時に別途確認する。
