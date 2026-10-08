# B-Line Live V1 RC1 Operational & Persistence Runbook

- **Release ID**: `B_LINE_INITIAL_USABLE_RELEASE_V1_RC1`
- **Work Package**: `WP_D` (`B_LINE_RELEASE_ENGINEERING_R1_REPAIR_IDENTITY_BINDING`)
- **Work Package Base SHA**: `08e81bec003d645a0a0582db183a1b6916887eff` (WP-D worktree base only; **not** final RC1 release `source_sha`)
- **Release Source Identity**: `UNBOUND_PENDING_RC_INTEGRATION` in WP-D template; bound to exact 40-hex integration `source_sha` at RC closure
- **Startup Contract**: `SERIALIZED_SINGLE_RUNTIME_INITIALIZER` (`startup_mechanical_certification = PENDING_WP_A` until accepted WP-A evidence is bound)
- **Python Runtime Separation**:
  - `requires_python`: `>=3.11` (package metadata)
  - `container_build_python`: `3.12` (`Dockerfile` base image)
  - `rc1_certified_python`: `PENDING_WP_A` until supplied from accepted WP-A evidence (Python `3.13` is not RC1-certified unless independently certified by WP-A)
- **Supported Execution Modes**: `DRY_RUN` (default), `TESTNET` (explicit opt-in required)
- **Unavailable Mode**: `LIVE` (hard-rejected at configuration and runtime boundaries)
- **Safety Authority**:
  - `REAL_FUNDS_WRITE_AUTHORITY = NONE`
  - `LIVE_APPROVAL_ONLY = NOT_AUTHORIZED`
  - `AUTONOMOUS_LIVE = FORBIDDEN`

---

## 1. Canonical Service Startup Path (`SERIALIZED_SINGLE_RUNTIME_INITIALIZER`)

RC1 enforces a single canonical startup path. Legacy multi-process daemon patterns (`quantctl daemon`) are removed from container and compose configurations.

### 1.1 Canonical Host Startup Command

```bash
uvicorn btc_quant_agent.api:app --host 127.0.0.1 --port 8787 --workers 1
```

- **Single Worker Requirement (`--workers 1`)**: `SERIALIZED_SINGLE_RUNTIME_INITIALIZER` requires a single serialized process to own the SQLite WAL schema initialization, crash-recovery intent reconciliation, position supervisor outbox drain, and background async loops (`live-v1-market`, `live-v1-rest`, `live-v1-outbox`, `live-v1-position`, and in `TESTNET` mode `live-v1-account`).
- **Pre-Start Configuration & Readiness Smoke Command (No Network / No Server Loop)**:
  ```bash
  python -m btc_quant_agent.api --check-config
  python -m btc_quant_agent.api --print-readiness
  python -m btc_quant_agent.api --verify-manifest evidence/v0.6/b_line/engineering_preview_r1/RELEASE_MANIFEST_TEMPLATE_UNBOUND.json
  ```

### 1.2 Container & Compose Startup

`Dockerfile` and `docker-compose.yml` use the same single-process ASGI entrypoint bound to localhost on the host:

```bash
docker compose up -d api
```

---

## 2. Non-Secret Configuration Reference (`.env.example`)

Copy `.env.example` to a local untracked `.env` file (or export variables in your service environment). Never commit real API keys, secrets, or tokens.

| Variable | Default | Required When | Validation / Fail-Early Rule |
|---|---|---|---|
| `BTC_QUANT_CONFIG` | `./configs/default.toml` | Always | Must point to an existing valid TOML config file |
| `BTC_QUANT_DB_PATH` | `./var/quant.db` | Always | Non-empty filesystem path for host repository |
| `BTC_QUANT_LIVE_V1_DB_PATH` | `./var/live_v1.db` | Live V1 enabled | Non-empty durable path (`:memory:` rejected) |
| `BTC_QUANT_API_TOKEN` | *(empty)* | Calling protected GET routes | Bearer token required by `/health`, `/execution/status`, `/signals/*`, `/live-v1/*` |
| `BTC_QUANT_LIVE_V1_RUNTIME_ENABLED` | `false` (`true` in `.env.example`) | Canonical RC1 service | Must be `true` or `false`; enables `B4_RUNTIME` |
| `BTC_QUANT_LIVE_V1_ENABLED` | `false` | Legacy B3 control | Must be `true` or `false`; superseded when `B4_RUNTIME` is enabled |
| `BTC_QUANT_LIVE_V1_EXECUTION_MODE` | `DRY_RUN` | Live V1 enabled | `DRY_RUN` or `TESTNET` (`PAPER`/`SHADOW` normalize to `DRY_RUN`; `LIVE` rejected) |
| `BTC_QUANT_LIVE_V1_TESTNET_EXECUTION_ENABLED` | `false` | `EXECUTION_MODE=TESTNET` | Must be `true` when `EXECUTION_MODE=TESTNET` |
| `BTC_QUANT_LIVE_V1_SYMBOL` | `BTCUSDT` | Live V1 enabled | Non-empty symbol (`BTCUSDT`) |
| `BTC_QUANT_LIVE_V1_ACCOUNT_ID` | `DEFAULT_ACCOUNT` | Live V1 enabled | Non-empty account authority identifier |
| `BTC_QUANT_LIVE_V1_WS_URL` | `wss://fstream.binance.com` | Live V1 enabled | Must start with `ws://` or `wss://` |
| `BTC_QUANT_LIVE_V1_REST_RECONCILE_SECONDS` | `30` | Live V1 enabled | Finite float in `[30, 60]` |
| `BTC_QUANT_LIVE_V1_POSITION_POLL_SECONDS` | `5` | Optional | Positive finite float |
| `BTC_QUANT_LIVE_V1_OUTBOX_POLL_SECONDS` | `5` | Optional | Positive finite float |
| `BTC_QUANT_LIVE_RESPONSES_MODEL` | `gpt-5.4` | Primary LLM analysis | Non-empty model identifier if set |
| `OPENAI_API_KEY` | *(empty)* | Primary LLM analysis | Secret key in env only; if absent, primary backend fails closed |
| `BTC_QUANT_LIVE_CODEX_ENABLED` | `false` | Secondary review | Must be `true` or `false` |
| `BTC_QUANT_LIVE_CODEX_MODEL` | `gpt-5.3-codex-spark` | `CODEX_ENABLED=true` | Required non-empty model string when `CODEX_ENABLED=true` |
| `BTC_QUANT_LIVE_ANALYSIS_TIMEOUT` | `60` | Live V1 enabled | Positive finite float (seconds) |
| `BTC_QUANT_LIVE_CASE_TTL_MS` | `120000` | Live V1 enabled | Positive integer (milliseconds) |
| `BTC_QUANT_LIVE_RISK_POLICY_JSON` | *(unset)* | Optional override | Must validate against `RiskPolicyV1` JSON schema |
| `FEISHU_APP_ID` | *(empty)* | Outbound Feishu cards | Must be set together with `FEISHU_APP_SECRET` and `FEISHU_RECEIVE_ID` |
| `FEISHU_APP_SECRET` | *(empty)* | Outbound Feishu cards | Must be set together with `FEISHU_APP_ID` and `FEISHU_RECEIVE_ID` |
| `FEISHU_RECEIVE_ID` | *(empty)* | Outbound Feishu cards | Must be set together with `FEISHU_APP_ID` and `FEISHU_APP_SECRET` |
| `FEISHU_RECEIVE_ID_TYPE` | `chat_id` | Optional | One of `chat_id`, `open_id`, `user_id`, `email` |
| `FEISHU_VERIFICATION_TOKEN` | *(empty)* | Feishu callbacks | Required for `/live-v1/feishu/callback` verification |
| `FEISHU_ENCRYPT_KEY` | *(empty)* | Signed Feishu callbacks | Used to verify callback timestamp/signature headers |
| `FEISHU_APPROVER_OPEN_IDS` | *(empty)* | Feishu approvals | Comma-separated allowlist of authorized approver `open_id`s |
| `BINANCE_TESTNET_API_KEY` | *(empty)* | `EXECUTION_MODE=TESTNET` | Required in `TESTNET` runtime mode |
| `BINANCE_TESTNET_API_SECRET` | *(empty)* | `EXECUTION_MODE=TESTNET` | Required in `TESTNET` runtime mode |
| `BINANCE_TESTNET_FAPI_BASE_URL` | `https://testnet.binancefuture.com` | `EXECUTION_MODE=TESTNET` | Must equal `https://testnet.binancefuture.com` |
| `BINANCE_TESTNET_WS_BASE_URL` | `wss://stream.binancefuture.com/ws` | `EXECUTION_MODE=TESTNET` | Must be a valid Binance Futures Testnet `ws(s)://` URL |
| `REAL_FUNDS_WRITE_AUTHORITY` | `NONE` | Always | Must be `NONE`; any other value aborts startup |
| `LIVE_APPROVAL_ONLY` | `NOT_AUTHORIZED` | Always | Must be `NOT_AUTHORIZED`; any other value aborts startup |
| `AUTONOMOUS_LIVE` | `FORBIDDEN` | Always | Must be `FORBIDDEN`; any other value aborts startup |

> **Forbidden Mainnet Variables**: Setting any of `BINANCE_API_KEY`, `BINANCE_API_SECRET`, `BINANCE_LIVE_API_KEY`, `BINANCE_LIVE_API_SECRET`, `BINANCE_MAINNET_API_KEY`, `BINANCE_MAINNET_API_SECRET`, or `BINANCE_PRIVATE_KEY` when Live V1 is enabled causes immediate startup rejection.

---

## 3. Machine-Readable Readiness & Health Inspection

Readiness is exposed via three machine-readable channels:
1. **HTTP `GET /health`** under the `live_v1_readiness` key (read-only inspection; never mutates or creates SQLite files).
2. **HTTP `GET /execution/status`** under the `live_v1_readiness` key alongside `live_v1_runtime`.
3. **Structured JSON Startup/Shutdown Logs** on logger `btc_quant_agent.live_v1.readiness` (`event="LIVE_V1_STARTUP_READINESS"`, `event="LIVE_V1_STARTUP_READINESS_FAILED"`, `event="LIVE_V1_SHUTDOWN_COMPLETE"`).

### 3.1 Required Readiness Field Matrix

| Field | Type | Values | Meaning |
|---|---|---|---|
| `service_started` | `bool` | `true` / `false` | `true` once FastAPI lifespan has completed `await live_runtime.start()` |
| `database_ready` | `bool` | `true` / `false` | `true` when `live_v1.db` exists on disk, opens read-only, and is in `wal` journal mode |
| `migration_ready` | `bool` | `true` / `false` | `true` when all 16 B4 tables, migrated columns, and R8 immutable triggers are present |
| `market_source_ready` | `bool` | `true` / `false` | `true` when public market stream (`MarketStreamService`) is connected |
| `analysis_backend_ready` | `bool` | `true` / `false` | `true` when primary `ResponsesBackend` (and optional `CodexExecBackend`) is configured |
| `approval_backend_state` | `str` | `READY`, `CALLBACK_READY_NO_OUTBOUND_NOTIFIER`, `CALLBACK_TOKEN_ONLY`, `MANUAL_FALLBACK_ONLY`, `DISABLED` | Current Feishu notification and callback authentication readiness |
| `account_stream_state` | `str` | `CONNECTED`, `DISCONNECTED`, `NOT_REQUIRED_DRY_RUN`, `NOT_APPLICABLE_B3_CONTROL`, `DISABLED` | User-data stream state (`TESTNET` requires `CONNECTED` before new risk is accepted) |
| `execution_mode` | `str` | `DRY_RUN`, `TESTNET`, `DISABLED` | Active execution mode |
| `kill_switch_state` | `str` | `ARMED`, `TRIPPED`, `UNAVAILABLE`, `DISABLED` | `ARMED` when `is_killed=0` (normal), `TRIPPED` when latched (`is_killed=1`) |

### 3.2 Inspecting Readiness via CLI / HTTP

```bash
# HTTP inspection (requires BTC_QUANT_API_TOKEN)
curl -sS -H "Authorization: Bearer ${BTC_QUANT_API_TOKEN}" http://127.0.0.1:8787/health | python -m json.tool
curl -sS -H "Authorization: Bearer ${BTC_QUANT_API_TOKEN}" http://127.0.0.1:8787/execution/status | python -m json.tool
```

---

## 4. Persistence Architecture, Migrations & Backup Expectations

### 4.1 Persistence Database Paths

1. **Live V1 Durable Store (`BTC_QUANT_LIVE_V1_DB_PATH`, default `./var/live_v1.db`)**:
   - Connection invariants enforced by `src/btc_quant_agent/live_db.py`:
     - `PRAGMA journal_mode=WAL`
     - `PRAGMA synchronous=FULL`
     - `PRAGMA foreign_keys=ON`
     - `PRAGMA recursive_triggers=ON`
     - `PRAGMA busy_timeout=10000`
   - **B3 Decision & Approval Tables**:
     - `live_cases`, `analysis_results`, `trade_proposals`, `approval_records` (migrated columns: `review_processed`, `review_claim_until_ms`, `review_claim_token`), `live_state_events`
   - **B4 Runtime, Account, Execution & Supervisor Tables**:
     - `live_account_snapshots`, `live_account_events`
     - `live_trade_intents`, `live_intent_transitions`
     - `live_execution_market_observations`, `live_pre_execution_authorizations`, `live_execution_claims`, `live_execution_orders`
     - `live_protection_owners` (migrated column: `confirmed_at_ms`)
     - `live_kill_switch_state`
     - `live_position_events` (migrated authority columns: `environment`, `credential_namespace`, `account_id`, `position_side`, `position_authority_key`)
     - `live_position_active`, `live_position_lifecycle`, `live_position_lifecycle_v2`, `live_position_observed_sources`
     - `live_position_case_dispatches` (migrated columns: `position_case_id`, `position_case_hash`, `position_case_json`, `case_hash`, `dispatch_authority_json`, `dispatch_authority_hash`, `analysis_admission_hash`, `analysis_completed`)
   - **Immutable SQLite Triggers**:
     - `trg_live_position_events_immutable_update`, `trg_live_position_events_immutable_delete`
     - `trg_live_position_dispatches_immutable_authority`, `trg_live_position_dispatch_blank_insert`, `trg_live_position_dispatch_admission_immutable`, `trg_live_position_dispatch_done_requires_completion`, `trg_live_position_analysis_completion_guard`, `trg_live_position_dispatches_immutable_delete`
2. **Host Operational Store (`BTC_QUANT_DB_PATH`, default `./var/quant.db`)**:
   - Retains legacy/host `signals`, `runtime_events`, and diagnostic tables.
3. **MarketWatch Store (`./var/market_watch.db`)**:
   - Stores `market_watch_symbol_state`, `market_watch_assessments`, `market_watch_shadow_records`, `tactical_feature_evidence_v2`, `tactical_shadow_evaluations_v2`, and `tactical_grid_shadow_evaluations_v1`.

### 4.2 Schema Migration Policy

Under `SERIALIZED_SINGLE_RUNTIME_INITIALIZER`, `create_app()` runs `_initialize_live_v1_persistence()` before any async worker task is spawned. All `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN`, and `CREATE TRIGGER` statements execute in serialized order on `./var/live_v1.db`.

### 4.3 Backup Expectations

- **Online Hot Backup (Service Running)**:
  Always use SQLite's online backup API so WAL frames are consistently checkpointed into the backup file:
  ```bash
  sqlite3 ./var/live_v1.db ".backup './var/backups/live_v1_$(date -u +%Y%m%dT%H%M%SZ).db'"
  ```
- **Cold Backup (Service Stopped)**:
  Stop the service cleanly first so SQLite checkpoints `./var/live_v1.db-wal` and removes `./var/live_v1.db-shm`. If copying after an unclean crash, copy `./var/live_v1.db`, `./var/live_v1.db-wal`, and `./var/live_v1.db-shm` together as an atomic set.
- **Audit Immutability Rule**:
  Never manually `DELETE` or `UPDATE` rows in `live_cases`, `trade_proposals`, `approval_records`, `live_trade_intents`, `live_execution_orders`, `live_position_events`, or `live_position_case_dispatches`.

---

## 5. Standard Operational Procedures & Failure Runbook

### 5.1 First Start

1. Prepare `.env` from `.env.example`. Set a strong `BTC_QUANT_API_TOKEN` and keep `BTC_QUANT_LIVE_V1_EXECUTION_MODE=DRY_RUN` for initial verification.
2. Validate configuration and print initial readiness without starting background loops:
   ```bash
   python -m btc_quant_agent.api --check-config
   ```
3. Start the service using the single canonical command:
   ```bash
   uvicorn btc_quant_agent.api:app --host 127.0.0.1 --port 8787 --workers 1
   ```
4. Verify `LIVE_V1_STARTUP_READINESS` is logged and query `/execution/status`:
   - `service_started: true`
   - `database_ready: true`
   - `migration_ready: true`
   - `kill_switch_state: "ARMED"`

### 5.2 Normal Start

1. Confirm no other `uvicorn` or `LiveV1Runtime` process is attached to `./var/live_v1.db`.
2. Start with `uvicorn btc_quant_agent.api:app --host 127.0.0.1 --port 8787 --workers 1`.
3. Startup automatically executes:
   - `reconcile_unfinished_intents()`
   - `account_watch.reconcile_rest_async()` and snapshot authority verification
   - `_refresh_case(symbol)`
   - `supervisor.drain_pending_dispatches()`
   - Worker task launch (`live-v1-market`, `live-v1-rest`, `live-v1-outbox`, `live-v1-position`, plus `live-v1-account` in `TESTNET`)

### 5.3 Stop

1. Send `SIGTERM` or `SIGINT` (`Ctrl+C` or `docker compose stop api`).
2. `LiveV1Runtime.stop()` immediately sets `accepting_risk=False` and `blocked_reason="RUNTIME_STOPPED"`, signals `_stop_event`, shields in-flight position reconciliation so no signed REST read is orphaned, closes the user stream (`close_user_stream()`), and logs `LIVE_V1_SHUTDOWN_COMPLETE`.

### 5.4 Restart & Crash Recovery

1. If the process crashed or was killed (`SIGKILL`), restart using the canonical startup command.
2. On startup, before `accepting_risk` can become `True`:
   - Every non-terminal trade intent in `live_trade_intents` is reconciled against the execution backend (`reconcile_intent(intent_id)`) before any new entry is considered.
   - Any claimed/expired lease in `live_position_case_dispatches` or `approval_records` (Codex review queue) recovers after lease expiry without duplicating primary provider calls or fabricating completion receipts.
   - Account state is reconciled via REST (`reconcile_rest_async()`).

### 5.5 Stale State (`STALE_CASE` / Stale Account / Stale Market Observation)

- **Symptom**: `blocked_reason` reports `ACCOUNT_RECONCILIATION_REQUIRED` or `FRESH_MARKET_CASE_UNAVAILABLE`, or case analysis raises `STALE_CASE`.
- **System Behavior**: Fail-closed (`accepting_risk=False`). Pre-execution validation (`PreExecutionValidator`) rejects any intent whose market observation, account snapshot, or tactical case exceeds `max_staleness_ms` or `expires_at_ms`.
- **Operator Action**: Check network clock sync (`ntp` / `chrony`), verify Binance public WebSocket (`BTC_QUANT_LIVE_V1_WS_URL`) and REST connectivity, and wait for the next 30-second REST reconciliation cycle.

### 5.6 Provider Outage (OpenAI Responses API / Codex CLI Outage)

- **Symptom**: `OPENAI_API_KEY` missing, OpenAI HTTP timeout/5xx/refusal, or Codex CLI subprocess timeout/non-zero exit.
- **System Behavior**:
  - `ResponsesBackend.analyze()` and `CodexExecBackend.analyze()` catch all provider/timeout errors and return `AnalysisResultV1.fail_closed(..., reason="BACKEND_TIMEOUT" | "BACKEND_RESPONSE_INVALID" | "BACKEND_CONFIG")` with `action="WAIT"` (`NO_ACTION`).
  - `TacticalLiveService` persists the fail-closed analysis and transitions the case to `MANUAL` (or `EXPIRED` if past TTL). Zero executable authority is created.
- **Operator Action**: Inspect `analysis_backend_ready` in `/execution/status`, verify `OPENAI_API_KEY` and model identifiers (`BTC_QUANT_LIVE_RESPONSES_MODEL`, `BTC_QUANT_LIVE_CODEX_MODEL`), and check provider status. No restart is required once provider connectivity recovers.

### 5.7 Binance Outage (Public Market Stream / REST Outage)

- **Symptom**: `market_source_ready: false` or `blocked_reason: "MARKET_STREAM_DISCONNECTED"`.
- **System Behavior**:
  - `MarketStreamService.run_stream()` marks `_connected = False` and reconnects with bounded exponential backoff (1.0s to 10.0s).
  - While disconnected, `assert_current_new_risk_authority()` blocks all new risk (`ExecutionBlocked("MARKET_STREAM_DISCONNECTED")`).
- **Operator Action**: Check egress network/firewall (ensure non-US egress IP to avoid HTTP 451; see `docs/LINUX_VPS_MIGRATION_RUNBOOK.md`). When the stream reconnects and a fresh REST cycle succeeds, `market_source_ready` returns to `true`.

### 5.8 Feishu Outage (Outbound Card Delivery / Inbound Callback Outage)

- **Symptom**: Feishu Open API `send_proposal` fails or callback webhook does not reach `/live-v1/feishu/callback`.
- **System Behavior**:
  - Outbound failure: `TacticalLiveService._finish()` catches the notification error and transitions the case to `LiveState.MANUAL`. It never transitions to `WAITING_APPROVAL` without confirmed delivery.
  - Inbound callback delay/outage: Proposals awaiting approval automatically expire when `clock_ms >= expires_at_ms` (`LiveState.EXPIRED`). Late callbacks after TTL are rejected.
- **Operator Action**: Verify `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, `FEISHU_RECEIVE_ID`, `FEISHU_VERIFICATION_TOKEN`, and reverse-proxy/tunnel reachability to `/live-v1/feishu/callback`.

### 5.9 TESTNET Transport Uncertainty (`UNKNOWN_EXECUTION`)

- **Symptom**: During `TESTNET` order submission, network timeout or HTTP 5xx leaves order creation outcome uncertain.
- **System Behavior**:
  - The pre-execution claim is persisted in `live_execution_claims` *before* the signed POST.
  - Transport uncertainty transitions the intent to `UNKNOWN_EXECUTION` (`has_existing_side_effect=True`).
  - Blind retry is forbidden. `LiveV1Runtime.execute_intent()` routes any intent with an existing side effect strictly to `execution_service.reconcile_intent(intent_id)`, querying Binance Testnet by deterministic `origClientOrderId` (`client_order_id`).
- **Operator Action**: Do not manually delete `live_execution_claims` or `live_trade_intents`. Allow `reconcile_unfinished_intents()` (run automatically every 5s and on startup) to query `/fapi/v1/order` by `origClientOrderId` and resolve the true exchange state.

### 5.10 Partial Fill Handling (`PARTIAL_FILL` / `PARTIAL_FILL_STALE`)

- **Symptom**: Entry order on `TESTNET` is `PARTIALLY_FILLED`.
- **System Behavior**:
  - `TestnetExecutionBackend` installs or updates protective stop-loss (`STOP_MARKET` `reduceOnly`) sized to the actual `filled_qty`.
  - If a partial fill remains open beyond the supervisor staleness threshold, `PositionSupervisor` emits a `PARTIAL_FILL_STALE` event and dispatches a frozen position review case via `live_position_case_dispatches`.
- **Operator Action**: Review the position supervision alert in Feishu / `/live-v1/cases/{case_id}`. Verify on Binance Testnet that the remainder is canceled or filled and that protective stop quantity matches the open position.

### 5.11 Protection Uncertainty (`PENDING_CONFIRMATION` / `PROTECTIVE_ORDER_MISSING`)

- **Symptom**: Entry order fills, but protective stop-loss placement or confirmation on `/fapi/v1/openAlgoOrders` / `/fapi/v1/openOrders` fails or remains `PENDING_CONFIRMATION`.
- **System Behavior**:
  - `ProtectionStore` reserves protection ownership (`RESERVED` -> `PENDING_CONFIRMATION`) before confirmed `ACTIVE` status.
  - If protection fails during entry submission, `TestnetExecutionBackend` immediately attempts an emergency `MARKET` `reduceOnly` flatten order and latches the `KillSwitch` (`PROTECTIVE_ORDER_MISSING`).
  - If an open position lacks confirmed protection beyond `protective_missing_grace_ms`, `KillSwitch.evaluate()` latches `PROTECTIVE_ORDER_MISSING`.
- **Operator Action**: Immediately inspect open positions and open algo/conditional orders on Binance Futures Testnet. Manually close any unprotected Testnet position before investigating logs.

### 5.12 Kill Switch (`TRIPPED` State & Latch Reasons)

- **Symptom**: `kill_switch_state: "TRIPPED"` in `/health` or `/execution/status`, `blocked_reason: "KILL_SWITCH_ACTIVE"`.
- **Trigger Conditions (`KillSwitch.evaluate`)**:
  - `DAILY_LOSS_CAP`: `daily_loss_usdt >= daily_loss_cap_usdt`
  - `DRAWDOWN_CAP`: `drawdown_pct >= drawdown_cap_pct`
  - `ACCOUNT_UNRECONCILED`: account unreconciled longer than `unreconciled_timeout_ms`
  - `ORDER_STATE_CONFLICT`: `order_conflicts >= order_conflicts_max`
  - `WRONG_ENVIRONMENT`: environment/credential namespace/URL mismatch
  - `PROTECTIVE_ORDER_MISSING`: open position missing confirmed stop-loss beyond grace period
- **System Behavior**:
  - Latches `is_killed = 1` with JSON `reasons` and `tripped_at_ms` in `live_kill_switch_state` (`./var/live_v1.db`).
  - Blocks all new risk (`allows_new_risk() == False`) across restarts.
  - Risk-reducing actions remain permitted in non-`LIVE` environments (`allows_risk_reducing("TESTNET") == True`, `allows_risk_reducing("LIVE") == False`).

### 5.13 Operator Recovery Procedure (From Blocked or Tripped State)

1. **Inspect State**:
   ```bash
   curl -sS -H "Authorization: Bearer ${BTC_QUANT_API_TOKEN}" http://127.0.0.1:8787/execution/status | python -m json.tool
   ```
   Check `live_v1_readiness.kill_switch_state`, `live_v1_readiness.kill_switch_reasons`, and `live_v1_readiness.blocked_reason`.
2. **Stop the Service**:
   Stop `uvicorn` cleanly (`SIGTERM`).
3. **Back Up Database**:
   ```bash
   sqlite3 ./var/live_v1.db ".backup './var/backups/live_v1_pre_recovery_$(date -u +%Y%m%dT%H%M%SZ).db'"
   ```
4. **Verify Exchange Account State (If `TESTNET`)**:
   Confirm on Binance Futures Testnet (`https://testnet.binancefuture.com`) that:
   - All open positions on `BTCUSDT` (and any foreign symbols) are flat (`quantity == 0`) or have verified protective orders.
   - No orphaned open orders remain.
5. **Clear Kill Switch Only After Root Cause Resolution**:
   Once the underlying cause is resolved and positions are verified flat/safe, reset the kill switch row in `./var/live_v1.db`:
   ```bash
   sqlite3 ./var/live_v1.db "UPDATE live_kill_switch_state SET is_killed=0, reasons='[]', tripped_at_ms=0 WHERE id=1;"
   ```
6. **Restart and Verify Readiness**:
   Start with `uvicorn btc_quant_agent.api:app --host 127.0.0.1 --port 8787 --workers 1` and confirm `kill_switch_state == "ARMED"` and `accepting_risk == true`.

---

## 6. Evidence, Manifest & Log Locations

- **WP-D Release Manifest**: `evidence/v0.6/b_line/engineering_preview_r1/RELEASE_MANIFEST_TEMPLATE_UNBOUND.json`
- **WP-D Release Engineering Evidence**: `evidence/v0.5.5/live_v1/RC1/WP_D/EVIDENCE.json`
- **Prior B-Line Validation Evidence**:
  - `evidence/v0.5.5/live_v1/B3_DAY1_VALIDATION.json`
  - `evidence/v0.5.5/live_v1/B3_DAY1_PUBLIC_DATA_DRY_RUN.json`
  - `evidence/v0.5.5/live_v1/B4_DAY2_VALIDATION.json`
- **Runtime SQLite Databases**:
  - `./var/live_v1.db` (Live V1 durable state, audit trail, intents, supervisor outbox, kill switch)
  - `./var/quant.db` (host repository)
  - `./var/market_watch.db` (MarketWatch assessments and shadow records)
- **Structured Readiness Logs**:
  - Emitted to standard output / container logs under logger `btc_quant_agent.live_v1.readiness` (`LIVE_V1_STARTUP_READINESS`, `LIVE_V1_STARTUP_READINESS_FAILED`, `LIVE_V1_SHUTDOWN_COMPLETE`).
