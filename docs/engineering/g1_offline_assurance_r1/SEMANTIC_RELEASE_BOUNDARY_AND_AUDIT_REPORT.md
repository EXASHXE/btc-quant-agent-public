# Gemini Goal E — Independent G1 Offline-Preview Safety and Recovery Assurance R1: Semantic Release-Boundary & Audit Report

- **Task ID**: `V06_G1_GEMINI_OFFLINE_ASSURANCE_R1`
- **Role**: Independent Read-Only Implementation & Safety Auditor (Gemini Goal E)
- **Controller Dispatch SHA**: `4a487fcef182edc6c68486ff53d4a64caa10debc`
- **Exact Start SHA (`C4`)**: `861a9d148f72db00e6079e53af78220bdd7e84ce`
- **Parent SHA (`C3`)**: `84c4764a2f1c46c81f43b144f5daf1f54cccc5d3`
- **First Freeze Commit SHA**: `7a8b49adff94b5cc9fe2e3e2787acc3ffd7dda65` (remote-verified prior to test execution)
- **Branch**: `feature/v06-bline-gemini-g1-offline-assurance-r1`
- **Worktree**: `/root/workspace/project/quant-v0.6/gemini-g1-offline-assurance-r1`
- **Scratch**: `/tmp/btc-g1_offline_assurance_r1`
- **Audit Outcome**: **`ACCEPT_SYNTHETIC_G1_PREVIEW_ONLY`** *(strictly bounded to the standalone, non-trading synthetic sidecar; zero production, G3, Testnet, Live, or Alpha authority)*

---

## 1. Static Identity and Lineage Audit

### 1.1 4-Commit Codex Lineage and Server CI Mode

| Stage | Commit SHA | Parent SHA | Touched Scope | Server CI Run & Mode |
|---|---|---|---|---|
| `C0` (Base) | `55ac4c631c69f6edbd275462ad23e4486b9782ed` | `de2c1fb222970a93ca797868b91b8544261ebaad` | Clean base prior to G1 offline preview R1 | — |
| `C1` | `cf76ef99b47dc91b7f062877679172bacf1d6c9f` | `55ac4c631c69f6edbd275462ad23e4486b9782ed` | Initial offline workflow (`scripts/g1_offline_preview_r1/**`, `tests/**`, `docs/**`, `evidence/**`) | Run `38195492298`: `SUCCESS` (`mode=full`, compatibility manual suite `skipped`) |
| `C2` | `b792c613cac70324e66f6fb6958ce269f1a55dd1` | `cf76ef99b47dc91b7f062877679172bacf1d6c9f` | Mandatory causal exits, per-fill pending ACK accounting, OS crash recovery | Run `38197778075`: `SUCCESS` (`mode=full`, compatibility manual suite `skipped`) |
| `C3` | `84c4764a2f1c46c81f43b144f5daf1f54cccc5d3` | `b792c613cac70324e66f6fb6958ce269f1a55dd1` | Stop effective clock guard in `reducer.py` + 3 exit safety tests | Run `38199249523`: `FAILURE` (`mode=full`; failed solely on unrelated `tests/test_v051_h40_m3a_production_discovery_producer.py::test_p09_through_p18_exact_scientific_graph`) |
| `C4` (`HEAD`) | `861a9d148f72db00e6079e53af78220bdd7e84ce` | `84c4764a2f1c46c81f43b144f5daf1f54cccc5d3` | `SafeArgumentParser` in `__main__.py`, 2 CLI redaction tests, final manifests/receipts | Run `38200928294`: `SUCCESS` (`mode=full`, job `114653955103` `SUCCESS`, compatibility job `114653955998` `skipped`) |

- **Path Scope Verification**: All 31 changed paths across `55ac4c631c69f6edbd275462ad23e4486b9782ed..861a9d148f72db00e6079e53af78220bdd7e84ce` fall within `{scripts/g1_offline_preview_r1/, tests/test_v06_g1_offline_preview_r1_, docs/engineering/g1_offline_preview_r1/, evidence/v0.6/b_line/g1_offline_preview_r1/}`. Zero production files (`src/btc_quant_agent/**`) or CI workflow files (`.github/**`) were modified.
- **Manifest & Historical Hash Verification**: All 13 source and test file SHA256 digests at `861a9d148f72db00e6079e53af78220bdd7e84ce` match `C4_FINAL_SOURCE_MANIFEST.json` (`source_manifest_sha256 = 2de618e4aebc43aacd3ef45071a1714099b47d59bc4e2d06973b0a74ce412460`) and `C3_STOP_EFFECTIVE_CLOCK_VALIDATION.json` (for `reducer.py`, `storage.py`, `model.py`, `fixtures.py`, `fixtures/*.json`). Zero code edits occurred after `C4`.

### 1.2 Exact Executable Symbols Touched in `C3` and `C4`

- **`C3` (`84c4764a2f1c46c81f43b144f5daf1f54cccc5d3`)**:
  - [`transition`](file:///z:/root/workspace/project/quant-v0.6/gemini-g1-offline-assurance-r1/scripts/g1_offline_preview_r1/reducer.py#L210-L703) in [reducer.py](file:///z:/root/workspace/project/quant-v0.6/gemini-g1-offline-assurance-r1/scripts/g1_offline_preview_r1/reducer.py):
    - Line 353 (`kind == "PROPOSE"`): `s.pop("stop_update_source_hash", None)` clears any stale stop-update bar hash when a new proposal is admitted.
    - Lines 570–571 (`kind == "UPDATE_STOP"`): `if at > bar["close_time"] + 1: raise SafetyViolation("STOP_UPDATE_NOT_AT_COMPLETED_BOUNDARY")` restricts stop updates to the completed bar boundary (`close_time` or `close_time + 1`).
    - Line 596 (`kind == "UPDATE_STOP"`): `s["stop_update_source_hash"] = s["last_bar_hash"]` binds the stop update to the current bar's digest.
    - Lines 604–605 (`kind == "STOP"`): `if s.get("stop_update_source_hash") == s["last_bar_hash"]: raise SafetyViolation("STOP_UPDATE_NOT_YET_EFFECTIVE")` prevents the newly tightened break-even stop from retroactively filling against the same completed bar's OHLC.
- **`C4` (`861a9d148f72db00e6079e53af78220bdd7e84ce`)**:
  - [`SafeArgumentParser`](file:///z:/root/workspace/project/quant-v0.6/gemini-g1-offline-assurance-r1/scripts/g1_offline_preview_r1/__main__.py#L17-L33), [`SafeArgumentParser.error`](file:///z:/root/workspace/project/quant-v0.6/gemini-g1-offline-assurance-r1/scripts/g1_offline_preview_r1/__main__.py#L20-L33), and [`main`](file:///z:/root/workspace/project/quant-v0.6/gemini-g1-offline-assurance-r1/scripts/g1_offline_preview_r1/__main__.py#L104-L172) in [__main__.py](file:///z:/root/workspace/project/quant-v0.6/gemini-g1-offline-assurance-r1/scripts/g1_offline_preview_r1/__main__.py):
    - Overrides `argparse.ArgumentParser.error(self, message)` to exit with code `3` and emit static canonical JSON (`CLI_ARGUMENTS_INVALID`) without echoing `message` or any caller-supplied CLI string.

### 1.3 State Machine Transitions and WAL / Checkpoint Write Map

| Event Kind | Allowed Input Phases | Output Phase | Journal (`_journal`) Write? | Outbox Append? | WAL & Checkpoint Write Behavior (`Engine.apply`) |
|---|---|---|---|---|---|
| `BAR` | Any valid state (`required_exit == None`) | Unchanged (`required_exit` updated) | **No** | **No** | Appends + `fsync` to `events.wal.jsonl`; writes `checkpoint-*.json` only if `seq % 120 == 0` |
| `PROPOSE` | `READY`, `CLOSED` (`at >= cooldown_until`), `NO_ACTION` | `PROPOSED` or `NO_ACTION` | **No** | Yes (`APPROVAL_NEEDED` / `NO_ACTION`) | Appends + `fsync` to `events.wal.jsonl`; writes immutable `checkpoint-*.json` |
| `ANALYZE` | `PROPOSED` | `ANALYZED` | **No** | Yes (`EXECUTION_STATE`) | Scrubs `summary` via `redact_text`; appends + `fsync` to WAL; writes `checkpoint-*.json` |
| `APPROVE` | `ANALYZED` | `APPROVED` | **No** | Yes (`EXECUTION_STATE`) | Appends + `fsync` to WAL; writes `checkpoint-*.json` |
| `PLACE` | `APPROVED` | `PLACED` (`order_id` assigned) | **No** | Yes (`EXECUTION_STATE`) | Appends + `fsync` to WAL; writes `checkpoint-*.json` |
| `FILL_ENTRY` | `PLACED` | `WAIT_ENTRY_ACK` | **Yes (`ENTRY_FEE`, `-fee`, reserves notional)** | Yes (`EXECUTION_STATE`) | Appends + `fsync` to WAL; writes `checkpoint-*.json` |
| `FUNDING` | `WAIT_ENTRY_ACK`, `OPEN`, `WAIT_TP1_ACK`, `OPEN_RESIDUAL` | Unchanged | **Yes (`FUNDING`, `-side * rem_qty * mark * rate`)** | Yes (`EXECUTION_STATE`) | Appends + `fsync` to WAL; writes `checkpoint-*.json` |
| `TP1` | `OPEN` (`not tp1_filled`) | `WAIT_TP1_ACK` | **No (`pending_cash[fill_id]` held)** | Yes (`EXECUTION_STATE`) | Appends + `fsync` to WAL; writes `checkpoint-*.json` |
| `UPDATE_STOP` | `OPEN_RESIDUAL` | `OPEN_RESIDUAL` | **No** | Yes (`EXECUTION_STATE`) | Appends + `fsync` to WAL; writes `checkpoint-*.json` |
| `STOP` / `TIME_CAP` / `TP2` | `OPEN`, `OPEN_RESIDUAL`, `WAIT_TP1_ACK`, `WAIT_ENTRY_ACK` | `EXIT_WAIT_ACK` | **No (`pending_cash[fill_id]` held)** | Yes (`EXECUTION_STATE`) | Appends + `fsync` to WAL; writes `checkpoint-*.json` |
| `ACK` | `WAIT_ENTRY_ACK`, `WAIT_TP1_ACK`, `EXIT_WAIT_ACK` | `OPEN`, `WAIT_TP1_ACK`, `OPEN_RESIDUAL`, `EXIT_WAIT_ACK`, or `CLOSED` | **Yes for exit fills (`{KIND}_NET`); No for entry ACK** | Yes (`EXECUTION_STATE`) | Appends + `fsync` to WAL; writes `checkpoint-*.json` |
| `OUTBOX_RECEIPT` | Any valid state (`required_exit == None`) | Unchanged (`last_at` unchanged) | **No** | **No** | Appends + `fsync` to WAL; writes `checkpoint-*.json` |

- **Pre-Approval Journal Invariant Proof**: `_journal()` is invoked exclusively at lines 452 (`FILL_ENTRY`), 480 (`ACK` for exit fills), and 529 (`FUNDING`) of [reducer.py](file:///z:/root/workspace/project/quant-v0.6/gemini-g1-offline-assurance-r1/scripts/g1_offline_preview_r1/reducer.py). Every one of those phases is strictly downstream of `APPROVED → PLACED → FILL_ENTRY`. No operation prior to validated human token approval can alter `state["journal"]`, `state["cash"]`, or `state["order_id"]`.
- **Static & Dynamic No-Network Proof**: AST analysis of all 5 Python modules in `scripts/g1_offline_preview_r1/` confirms imports are restricted to `{__future__, argparse, collections.abc, copy, decimal, fcntl, hashlib, json, os, pathlib, re, typing}` plus relative `.model`, `.reducer`, `.storage`. Dynamic runtime interception of `socket.socket.connect`, `socket.socket.connect_ex`, `socket.create_connection`, `socket.getaddrinfo`, and `urllib.request.urlopen` across all 65 negative transitions and all 10 full 24h workflows recorded **`0` outbound network/DNS/socket calls**.

---

## 2. Independent Adversarial Battery & Test Gap Characterization

### 2.1 Execution Summary

1. **Single-Shot Negative & Ledger Audit ([STATIC_IDENTITY_AND_SURFACE_AUDIT.json](file:///z:/root/workspace/project/quant-v0.6/gemini-g1-offline-assurance-r1/evidence/v0.6/b_line/g1_offline_assurance_r1/STATIC_IDENTITY_AND_SURFACE_AUDIT.json), [NEGATIVE_BATTERY_STATE_TRANSITIONS.json](file:///z:/root/workspace/project/quant-v0.6/gemini-g1-offline-assurance-r1/evidence/v0.6/b_line/g1_offline_assurance_r1/NEGATIVE_BATTERY_STATE_TRANSITIONS.json), [INDEPENDENT_DECIMAL_LEDGER_AUDIT.json](file:///z:/root/workspace/project/quant-v0.6/gemini-g1-offline-assurance-r1/evidence/v0.6/b_line/g1_offline_assurance_r1/INDEPENDENT_DECIMAL_LEDGER_AUDIT.json))**:
   - **65 distinct negative/adversarial reducer inputs (`N01`–`N65`)**: `65/65` rejected with exact expected `SafetyViolation` code, `any_state_mutated_on_rejection = false`, `outbound_network_calls_observed = 0`.
   - **10 full-workflow independent Decimal ledger scenarios (`LONG` & `SHORT` × `STOP` 24h, `TP2` 24h, `TIME_CAP` 12h/18h/24h = 60 journal effects)**: `10/10` exact Decimal match (`1000.33834810` for `LONG` 24h `STOP`, `1000.34054750` for `SHORT` 24h `STOP`).
2. **Frozen Commit 1 Pytest Suite (`tests/test_v06_g1_offline_assurance_r1_*.py`, [ASSURANCE_PYTEST_RECEIPT.txt](file:///z:/root/workspace/project/quant-v0.6/gemini-g1-offline-assurance-r1/evidence/v0.6/b_line/g1_offline_assurance_r1/ASSURANCE_PYTEST_RECEIPT.txt), [ASSURANCE_PYTEST_JUNIT.xml](file:///z:/root/workspace/project/quant-v0.6/gemini-g1-offline-assurance-r1/evidence/v0.6/b_line/g1_offline_assurance_r1/ASSURANCE_PYTEST_JUNIT.xml))**:
   - **149 collected test items**: **145 passed, 4 failed** in `267.20s`.
   - All **22 native OS process-kill (`os._exit(91)`) and restart checkpoints** (15 original + 7 novel offsets including the 3rd negative funding settlement `funding3_fsynced_novel`) **PASSED**.
   - All **4 dual-pending-exit-ACK native OS process-kill and restart tests** (`before_append`, `after_append`, `after_fsync`, `after_snapshot` on `ACK-SECOND-PENDING`) **PASSED**.
   - All **12 WAL and checkpoint corruption/tamper quarantine tests** **PASSED**.
   - **Characterization of the 4 Frozen Tester Failures ([ORIGINAL_VS_ASSURANCE_SUITE_DIFF.json](file:///z:/root/workspace/project/quant-v0.6/gemini-g1-offline-assurance-r1/evidence/v0.6/b_line/g1_offline_assurance_r1/ORIGINAL_VS_ASSURANCE_SUITE_DIFF.json))**:
     - None of the 4 failures is a defect in `scripts/g1_offline_preview_r1/**`. Three failures (`test_lot_rounding_floors_tp1_half_and_preserves_residual[0.011-...]`, `[0.003-...]`, and `test_min_notional_and_five_percent_reserve_fail_closed`) occurred because our frozen helper `build_state_at_phase` defaulted to `last_close = "100"`, where `0.001 * 100 = 0.1 < MIN_NOTIONAL (1.0)` and `0.003 * 100 = 0.3 < MIN_NOTIONAL (1.0)` rightly triggered `SafetyViolation("ONE_X_OR_MIN_NOTIONAL")` at `PLACE`, and `0.005 * 106 = 0.53 < MIN_NOTIONAL (1.0)` rightly triggered `SafetyViolation("PARTIAL_LOT_OR_MIN_NOTIONAL")` at `TP1`. The fourth failure (`test_initial_state_rejects_malformed_trusted_approval_fixtures[zero_quantity-override4]`) occurred because `initial_state` raised `SafetyViolation("DECIMAL_BOUNDS")` on `quantity="0"` whereas the test regex matched `"APPROVAL_FIXTURE_INVALID"`. Per the strict no-post-freeze-edit rule, the frozen test files and receipts are kept 100% immutable.

### 2.2 Concrete Test-Coverage Gaps Identified in the Original 145-Case Codex Suite

1. **`GAP_01` — `WAL_EVENT_IDENTITY` and `WAL_STATE_IDENTITY` Masked by `WAL_CHAIN`**:
   - In [test_v06_g1_offline_preview_r1_wal.py](file:///z:/root/workspace/project/quant-v0.6/gemini-g1-offline-assurance-r1/tests/test_v06_g1_offline_preview_r1_wal.py#L78-L81), the `"state"` damage case mutated `record["state_hash"] = "bad"` without recomputing `record["record_hash"] = digest(body)`. Because `Engine._recover()` in [storage.py](file:///z:/root/workspace/project/quant-v0.6/gemini-g1-offline-assurance-r1/scripts/g1_offline_preview_r1/storage.py#L179-L190) checks `digest(body) != rec["record_hash"]` (`WAL_CHAIN`, line 182) before checking `event_hash` (`WAL_EVENT_IDENTITY`, line 187) or `state_hash` (`WAL_STATE_IDENTITY`, line 190), the original suite never reached lines 187 or 190. Our independent suite recomputes `record_hash` after tampering with `event_hash`, duplicate `event["id"]`, and `state_hash`, directly verifying `WAL_EVENT_IDENTITY` and `WAL_STATE_IDENTITY`.
2. **`GAP_02` — Process Crash Recovery Omitted 3rd (Negative) Funding Settlement & Intermediate Hook Offsets**:
   - The original 15 process-kill cases in [test_v06_g1_offline_preview_r1_process_recovery.py](file:///z:/root/workspace/project/quant-v0.6/gemini-g1-offline-assurance-r1/tests/test_v06_g1_offline_preview_r1_process_recovery.py#L28-L44) only killed `FUNDING` at occurrences `0` and `1` (both `+0.0001`), omitting occurrence `2` (`-0.0002` at `t=36000000`), and tested only a single hook edge per event kind. Our 7 novel checkpoints verify `funding3_fsynced_novel` (`FUNDING` occurrence `2`, `after_fsync`), `approve_pre_novel`, `place_fsynced_novel`, `entry_snapshotted_novel`, `tp1_pre_novel`, `stop_update_fsynced_novel`, and `stop_appended_novel`.
3. **`GAP_03` — Process Crash Recovery During Simultaneous Dual-Pending-Exit-ACK State**:
   - Because `long_24h.json` and `short_24h.json` ACK `TP1` before `STOP` triggers, `len(pending_cash)` is never `2` during any OS process crash in the original 30 process-recovery tests. Our `dual_pending_ack` crash worker kills the process via `os._exit(91)` across all 4 hook edges (`before_append`, `after_append`, `after_fsync`, `after_snapshot`) on `ACK-SECOND-PENDING` while both `TP1` and `STOP` proceeds are pending, verifying deterministic recovery and cash conservation.
4. **`GAP_04` — `STOP` Triggered in `WAIT_ENTRY_ACK` Across Both ACK Arrival Orders**:
   - The original suite tested `STOP` before `TP1` ACK, but did not test `STOP` occurring while still in `WAIT_ENTRY_ACK` (before the entry fill itself is acknowledged) followed by both `[entry_ack, stop_ack]` and `[stop_ack, entry_ack]` arrival orders. Verified in `test_stop_before_entry_ack_all_ack_arrival_orders_conserve`.
5. **`GAP_05` — `CHECKPOINT_IMMUTABLE_CONFLICT` and `CHECKPOINT_SCHEMA`**:
   - The original suite did not exercise `CHECKPOINT_IMMUTABLE_CONFLICT` ([storage.py](file:///z:/root/workspace/project/quant-v0.6/gemini-g1-offline-assurance-r1/scripts/g1_offline_preview_r1/storage.py#L235)) or `CHECKPOINT_SCHEMA` ([storage.py](file:///z:/root/workspace/project/quant-v0.6/gemini-g1-offline-assurance-r1/scripts/g1_offline_preview_r1/storage.py#L207)). Both are verified in our assurance suite.

---

## 3. Semantic Release-Boundary Assessment

### 3.1 What Exactly Is Safe in the Synthetic Offline G1 Sidecar

1. **Manual Approval Gating of Simulated Intents & Fills**:
   - `PLACE` and `FILL_ENTRY` are unreachable without a prior `APPROVE` transition in `ANALYZED` phase backed by an explicit, un-replayed `TRUSTED_HUMAN_FIXTURE` token matching `signal_id`, `proposal_hash`, `proposal_version == 1`, `quantity`, and causal clock window `analysis_at <= issued_at <= approve_at < min(token_expires_at, proposal_expires_at)`.
2. **Deterministic Single-Process Crash Recovery**:
   - Across all 22 single-pending-ACK checkpoints and all 4 dual-pending-ACK checkpoints killed via `os._exit(91)`, restarting the engine replays `events.wal.jsonl` from genesis, verifies all immutable `checkpoint-*.json` prefixes, treats already-committed events as `IDEMPOTENT_DUPLICATE`, and converges to the exact reference `state_hash`, `wal_chain`, `journal_hash`, `cash`, and terminal checkpoint SHA256. Torn lines, hash mismatches, genesis drift, and checkpoint forks fail closed and quarantine with `unsafe_effects_replayed = false`.
3. **Technical Enforcement of Zero Network and Zero Order Write Authority**:
   - The sidecar imports only Python 3.12 standard library modules, contains no socket, HTTP, websocket, exchange, or notification client code, and makes zero outbound network or DNS calls at runtime.

### 3.2 What Is Still NOT Real (Production / Live / Testnet Release Blockers)

| Domain | Synthetic Preview Implementation (`g1_offline_preview_r1`) | Missing Production / Real-World Capability |
|---|---|---|
| **Human Approval Authentication** | Static JSON dictionary in `fixture["trusted_approvals"]` with string `"issuer": "TRUSTED_HUMAN_FIXTURE"` | Cryptographic or IdP-authenticated human identity (e.g., signed callback, WebAuthn/MFA, tamper-evident operator audit log, RBAC). Any process that can edit the fixture JSON can forge `"TRUSTED_HUMAN_FIXTURE"`. |
| **Credential Custody** | Regex scrubber `redact_text()` and `SafeArgumentParser` suppressing accidental `api_key=`/`secret=`/`password=`/`token=`/`bearer ` strings | Hardware/cloud secret custody (KMS/HSM/Vault), Least-Privilege read-only vs execution key separation, memory pinning, and structured secret-free logging pipelines. |
| **Live LLM Bounded Outputs** | `OfflineLLMAnalysisPort.analyze()` parses a static in-memory dict/JSON string | Bounded live LLM transport: strict request timeouts, token/cost caps, prompt-injection sanitization, schema-constrained decoding, circuit-breaker fallback to `NO_ACTION` on API timeout/5xx. |
| **Real Feishu Delivery & Permissions** | Appends JSON lines to local `/tmp/.../outbox_delivery.jsonl` | Authenticated Feishu webhook/bot transport, HMAC signature verification, rate-limit backoff, idempotent remote message deduplication, and authenticated operator callback routing. |
| **Exchange-Known-At Source & L2 Queue** | Pre-generated `SYNTHETIC_V1` 1m OHLC strings (`open_time + 59999`) | Real-time exchange WebSocket/REST ingestion, server-vs-local monotonic clock drift guards, missing/late bar heartbeat watchdogs, and L2 order-book depth / queue-position fill modeling. |
| **Broker ACK & Exchange Filters** | Scripted `ACK` events at `fill_at + 60000`; synthetic constants `MIN_NOTIONAL = 1`, `LOT = 0.001`, `TICK = 0.1`, `FEE = 6bp`, `ADVERSE_FILL = 5bp` | Real exchange `executionReport` reconciliation (partial fills, cancel/replace races, rejected orders, rate limits) and actual Binance USD-M symbol filters (where `MIN_NOTIONAL` is typically 5–100 USDT, not 1 USDT). |
| **Deployment & Disk Power-Loss Semantics** | Single-process `fcntl.flock` and `os.fsync` tested via `os._exit(91)` (page cache survives process death) | Hardware power-loss / disk-controller write-reordering fault tolerance, filesystem corruption recovery outside `/tmp` volatile tmpfs, supervisor/container lifecycle management, and distributed split-brain fencing. |

### 3.3 Recommended Next Engineering Contract (When Codex Budget Resumes)

No production integration, deployment, or Testnet/Live connection is authorized in this task. When engineering budget resumes, the recommended next bounded contract (`G1_BOUNDED_ADAPTER_CONTRACT_R2`, strictly offline/loopback-verified before any external G3/G4 gate) should enforce hexagonal port interfaces around the pure reducer:

```text
+-----------------------------------------------------------------------------------+
|                        G1 Pure Deterministic Core (Read-Only)                     |
|  model.py + reducer.py (Pure Transition, Mandatory Causal Exits, Decimal Ledger)  |
+-----------------------------------------+-----------------------------------------+
                                          |
                     Immutable Port Contracts (Strict Schemas)
                                          |
       +----------------------+-----------+-----------+----------------------+
       |                      |                       |                      |
       v                      v                       v                      v
+--------------+      +---------------+       +---------------+      +---------------+
| MarketPitPort|      | BoundedLLMPort|       | AuthHumanPort |      | DurableWalPort|
| - Monotonic  |      | - Timeout/Cap |       | - Ed25519/HMAC|      | - Non-tmpfs   |
|   clock drift|      | - Schema gate |       |   signed token|      |   storage root|
|   guard      |      | - Fail-closed |       | - Operator ID |      | - Power-loss  |
| - Gap/stale  |      |   to NO_ACTION|       |   & expiry    |      |   checksum    |
|   heartbeat  |      | - Zero order  |       |   verification|      |   verification|
|   watchdog   |      |   authority   |       |   before PLACE|      | - Outbox ACK  |
+--------------+      +---------------+       +---------------+      +---------------+
```

1. **Cryptographically Verified Approval Port (`AuthHumanPort`)**: Replace unauthenticated fixture dict lookup with an Ed25519/HMAC-verified approval token binding `(signal_id, proposal_hash, proposal_version, quantity, issued_at, expires_at, operator_key_id)` verified against a pinned operator public-key keyring.
2. **Loopback-Tested Bounded LLM & Outbox Ports (`BoundedLLMPort`, `OutboxPort`)**: Enforce strict wall-clock timeouts, byte-size bounds, and fail-closed fallback using local loopback mock servers before any external API wiring.
3. **Exchange Filter & Execution Reconciliation Contract**: Parameterize `ExchangeSymbolFilter` (`min_notional`, `step_size`, `tick_size`, `maker_fee`, `taker_fee`) in genesis state rather than hardcoding `MIN_NOTIONAL = Decimal(1)`, and model asynchronous broker reject/cancel-replace states before any G3/G4 consideration.
