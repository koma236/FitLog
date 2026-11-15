# Error Code List

Error codes used in this project. When implementing new error codes, always add them to this file.

## Error Code Naming Convention

### Format

```
[FEATURE]_[TYPE]_[DETAIL]
```

### Examples

```
USER_NOT_FOUND
AUTH_TOKEN_EXPIRED
PAYMENT_VALIDATION_ERROR
```

## HTTP Status Code Mapping

| HTTP Status | Usage | Error Code Example |
|-------------|-------|-------------------|
| 400 Bad Request | Validation error | `VALIDATION_ERROR` |
| 401 Unauthorized | Authentication error | `AUTH_TOKEN_EXPIRED`, `AUTH_INVALID_TOKEN` |
| 403 Forbidden | Authorization error | `AUTH_INSUFFICIENT_PERMISSION` |
| 404 Not Found | Resource not found | `USER_NOT_FOUND`, `RESOURCE_NOT_FOUND` |
| 409 Conflict | Conflict (duplicate, etc.) | `DUPLICATE_EMAIL` |
| 500 Internal Server Error | System error | `SYSTEM_INTERNAL_ERROR` |

## Error Codes

### Authentication / Authorization (AUTH)

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `AUTH_TOKEN_EXPIRED` | 401 | ID token expired |
| `AUTH_INVALID_TOKEN` | 401 | Invalid ID token |
| `AUTH_INSUFFICIENT_PERMISSION` | 403 | Insufficient permissions |

### General (GENERAL)

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `DATA_NOT_FOUND` | 404 | Generic data not found |
| `DUPLICATE_DATA` | 409 | Data duplication |

### Validation (VALIDATION)

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `VALIDATION_ERROR` | 400 | Invalid input |
| `INVALID_REQUEST` | 400 | Invalid request parameters |

### System (SYSTEM)

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `SYSTEM_INTERNAL_ERROR` | 500 | Unexpected system error |

---

**Note**: When adding new error codes, place them in the appropriate category.
If no suitable category exists, create a new section.

### Bootstrap operator command (CLI)

| Event | Exit | Description |
|---|---|---|
| `bootstrap_failed` | 2 | 初期化コマンドの入力・対象・状態・権限・外部処理の失敗。秘密や上流例外を表示せず停止。同じoperation UUIDで状態を再検証する。詳細は `docs/fl-09b6-bootstrap-runbook.md` |

### Deployment operator command (CLI)

HTTPの製品エラーとは別の運用CLI event。詳細は `docs/fl-09b7-deployment-runbook.md`。

| event | exit | 意味 |
|---|---|---|
| `deployment_failed` | 2 | 入力/対象/期限/工程/外部処理/証跡照合の失敗。秘密・例外本文を出さず停止。RunTask応答不明時はintentを調べ、新taskを安易に起動しない |
| `deployment_step_failed` | 2 | remote固定工程の失敗。子処理出力・SQL/SDK例外を出さず成功eventを発行しない |
| `deployment_evidence_failed` | 2 | 失敗証跡の保存自体に失敗。後続のdeployment_failedとともに未完了扱い |
| `ecr_plan_rejected` | 2 | ECR create1件以外、または保存plan判定不能。apply不可 |

### Day70 recording-free verification (CLI)

HTTPの製品エラーとは別の運用CLI。詳細は `docs/aws-day70-runbook.md`。

| event | exit | 意味 |
|---|---|---|
| `DAY70_RUN_REFUSED` | 1 | 入力/承認/期限/実行の拒否。生例外を表示せず停止 |
| `DAY70_RUN_FAILED` | 1 | 録画なしjourneyの実行失敗。attemptは消費済み |
| `DAY70_OBSERVATIONS_INVALID` | 1 | 必須観測の欠落、録画/性能/再構築の誤実行、禁止artifactを検出 |
| `DAY70_EVIDENCE_INVALID` | 1 | 停止後のB/C04原本再照合が失敗。成功へ昇格しない |
