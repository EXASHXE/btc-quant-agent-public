# Gemini Goal E — Independent G1 Offline-Preview Safety and Recovery Assurance R1: Frozen Audit Plan & Invariants

## 1. Authority, Identity, and Strict Scope Boundaries

- **Task ID**: `V06_G1_GEMINI_OFFLINE_ASSURANCE_R1`
- **Role**: Independent read-only implementation/safety auditor (Gemini Goal E). Not the original Codex author; zero Codex quota consumed.
- **Controller Dispatch SHA**: `4a487fcef182edc6c68486ff53d4a64caa10debc`
- **Authority Document**: `reviews/v0.6/b_line/V06_G1_G2_GEMINI_ONLY_NEXT_GATE_R1_CONTROLLER_AUTHORITY.md`
- **Repository**: `EXASHXE/btc-quant-agent-public`
- **Branch**: `feature/v06-bline-gemini-g1-offline-assurance-r1`
- **Exact Start SHA (`C4`)**: `861a9d148f72db00e6079e53af78220bdd7e84ce`
- **Parent SHA (`C3`)**: `84c4764a2f1c46c81f43b144f5daf1f54cccc5d3`
- **Own Worktree**: `/root/workspace/project/quant-v0.6/gemini-g1-offline-assurance-r1`
- **Own Scratch**: `/tmp/btc-g1_offline_assurance_r1`
- **Own Namespace**: `g1_offline_assurance_r1`
- **Permitted Write Paths**:
  - `scripts/strategy_research/g1_offline_assurance_r1/**`
  - `tests/test_v06_g1_offline_assurance_r1_*.py`
  - `docs/engineering/g1_offline_assurance_r1/**`
  - `evidence/v0.6/b_line/g1_offline_assurance_r1/**`
- **Read-Only Audit Target**: `scripts/g1_offline_preview_r1/**` and `tests/test_v06_g1_offline_preview_r1_*.py` at `861a9d148f72db00e6079e53af78220bdd7e84ce`.
- **Forbidden Paths & Operations**: Zero modification of `scripts/g1_offline_preview_r1/**`, `tests/test_v06_g1_offline_preview_r1_*.py`, production code, `.github/**`, role docs, or other worktrees. Zero access (never list/stat/read) to `/root/workspace/project/Quant-agent/data`, `Quant-agent-sanitized`, 2024–2026 partitions, protected H39/H40/H41/Forward, A-line/Performance, or private accounts. Zero live LLM calls, Feishu network sends, Testnet/Live connections, or real funds.

---

## 2. Static Identity Audit Specification

### 2.1 4-Commit Codex Lineage (`C0` → `C1` → `C2` → `C3` → `C4`)

| Stage | Commit SHA | Parent SHA | Summary | Server CI Run |
|---|---|---|---|---|
| `C0` (Base) | `55ac4c631c69f6edbd275462ad23e4486b9782ed` | `de2c1fb222970a93ca797868b91b8544261ebaad` | Clean base before G1 offline preview R1 | — |
| `C1` | `cf76ef99b47dc91b7f062877679172bacf1d6c9f` | `55ac4c631c69f6edbd275462ad23e4486b9782ed` | Implement sealed offline G1 workflow with causal approval and durable WAL | `38195492298` (`SUCCESS`, `mode=full`) |
| `C2` | `b792c613cac70324e66f6fb6958ce269f1a55dd1` | `cf76ef99b47dc91b7f062877679172bacf1d6c9f` | Enforce mandatory causal exits and verify offline crash recovery | `38197778075` (`SUCCESS`, `mode=full`) |
| `C3` | `84c4764a2f1c46c81f43b144f5daf1f54cccc5d3` | `b792c613cac70324e66f6fb6958ce269f1a55dd1` | Prevent retrospective BE-stop fills and correct pinned test evidence | `38199249523` (`FAILURE` in unrelated H40 graph test, `mode=full`) |
| `C4` (`HEAD`) | `861a9d148f72db00e6079e53af78220bdd7e84ce` | `84c4764a2f1c46c81f43b144f5daf1f54cccc5d3` | Finish offline preview with redacted CLI errors and audited recovery evidence | `38200928294` (`SUCCESS`, `mode=full`) |

### 2.2 Exact Executable Symbols Touched in `C3` and `C4`

1. **`C3` (`84c4764a2f1c46c81f43b144f5daf1f54cccc5d3`)**:
   - `scripts/g1_offline_preview_r1/reducer.py`:
     - `transition(state: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]`:
       - Under `kind == "PROPOSE"`: added `s.pop("stop_update_source_hash", None)` to clear any prior stop-update bar hash upon new proposal admission.
       - Under `kind == "UPDATE_STOP"`: added `if at > bar["close_time"] + 1: raise SafetyViolation("STOP_UPDATE_NOT_AT_COMPLETED_BOUNDARY")` and recorded `s["stop_update_source_hash"] = s["last_bar_hash"]`.
       - Under `kind in ("STOP", "TIME_CAP", "TP2")` when `kind == "STOP"`: added `if s.get("stop_update_source_hash") == s["last_bar_hash"]: raise SafetyViolation("STOP_UPDATE_NOT_YET_EFFECTIVE")` so a newly tightened break-even stop cannot retroactively fill against the completed bar on which the stop update occurred.
   - `tests/test_v06_g1_offline_preview_r1_exit_safety.py`:
     - Added helper `residual_before_update(side="LONG")`, test `test_new_be_stop_cannot_retroactively_fill_update_source_bar(side)`, and test `test_stop_update_after_boundary_rejects_without_financial_effect()`.
2. **`C4` (`861a9d148f72db00e6079e53af78220bdd7e84ce`)**:
   - `scripts/g1_offline_preview_r1/__main__.py`:
     - Added class `SafeArgumentParser(argparse.ArgumentParser)` overriding `error(self, message)` to exit with code `3` and static canonical JSON (`CLI_ARGUMENTS_INVALID`) without echoing `message` or caller-supplied argument strings.
     - Updated `main(argv=None)` to instantiate `SafeArgumentParser(description=__doc__)`.
   - `tests/test_v06_g1_offline_preview_r1_decimal_and_ports.py`:
     - Added `test_cli_argument_errors_never_echo_credentials_or_create_state(args, tmp_path, capsys)`.
   - Zero code edits occurred after `C4`; `reducer.py`, `storage.py`, `model.py`, `fixtures.py`, and `fixtures/*.json` are byte-identical between `C3` and `C4`.

### 2.3 State Machine Transitions and WAL / Snapshot Write Points

```text
READY ──(PROPOSE side!=NO_ACTION)──► PROPOSED ──(ANALYZE)──► ANALYZED ──(APPROVE)──► APPROVED
  │                                                                                     │
  └──(PROPOSE side==NO_ACTION)──► NO_ACTION                                          (PLACE)
                                                                                        ▼
  ┌───────────────────────────(FILL_ENTRY: journals ENTRY_FEE)────────────────────── PLACED
  ▼
WAIT_ENTRY_ACK ──(ACK entry_fill_id)──► OPEN ──(TP1: pending_cash[tp1])──► WAIT_TP1_ACK
  │                                       │                                      │
  │                                       │                                (ACK tp1_fill_id)
  │                                       │                                      ▼
  │                                       │                                OPEN_RESIDUAL
  │                                       │                                 │         ▲
  │                                       │                           (UPDATE_STOP)   │
  │                                       │                                 └─────────┘
  └──(STOP/TIME_CAP)──► EXIT_WAIT_ACK ◄───┴──(STOP/TIME_CAP/TP2: pending_cash[final])─┘
                              │
                   (All pending ACKs + entry ACK)
                              ▼
                           CLOSED ──(at >= cooldown_until: PROPOSE)──► PROPOSED / NO_ACTION
```

- **Journal (`state["journal"]`) & Cash (`state["cash"]`) Write Points**:
  1. `FILL_ENTRY` (only reachable from `PLACED`, which requires `APPROVED`): debits `-fee` (`ENTRY_FEE`) and reserves `reserved_notional = qty * entry_price`.
  2. `FUNDING` (only reachable in `WAIT_ENTRY_ACK`, `OPEN`, `WAIT_TP1_ACK`, `OPEN_RESIDUAL`): credits/debits `-side * remaining_qty * mark_close * rate_fraction` (`FUNDING`).
  3. `ACK` for exit fills (`TP1`, `STOP`, `TIME_CAP`, `TP2`): settles `pending_cash[fill_id]` into `state["cash"]` (`{REASON}_NET`) and releases `pending_release[fill_id]` from `reserved_notional`.
  - **Pre-Approval Journal Invariant**: Neither `BAR`, `PROPOSE`, `ANALYZE`, `APPROVE`, `PLACE`, nor `OUTBOX_RECEIPT` can invoke `_journal()` or mutate `state["cash"]`.
- **WAL (`events.wal.jsonl`) & Snapshot (`checkpoints/checkpoint-*.json`) Write Points**:
  - `Engine.__init__`: acquires `fcntl.flock(LOCK_EX | LOCK_NB)` on `writer.lock`; writes genesis line `{"format":"G1_OFFLINE_WAL_V1","genesis_hash":digest(initial)}` + `os.fsync(fd)` + directory `fsync`; calls `_recover()`.
  - `Engine.apply(event)`:
    1. Redacts `ANALYZE` summary via `redact_text`.
    2. Checks `event["id"] in self.seen` (`IDEMPOTENT_DUPLICATE` if identical hash; `EVENT_REUSE_DRIFT` if mutated).
    3. Pure validation & state computation `new = transition(self.state, e)`. Any `SafetyViolation` aborts before WAL write.
    4. Hook `before_append`.
    5. Appends canonical JSON line `{seq, previous, event, event_hash, state_hash, record_hash}` to `events.wal.jsonl`.
    6. Hook `after_append`.
    7. `os.fsync(fd)` on `events.wal.jsonl`.
    8. Hook `after_fsync`.
    9. Commits `self.state = new`, `self.seq += 1`, `self.chain = record["record_hash"]`.
    10. Writes immutable checkpoint `checkpoint-{seq:08d}-{state_hash[:16]}.json` (via temp file + `os.fsync` + `os.link` + `chmod 0400` + directory `fsync`) whenever `e["kind"] != "BAR" or self.seq % 120 == 0`.
    11. Hook `after_snapshot`.
    12. Appends operational trace line to `events.log.jsonl`.
  - `Engine.deliver()`: appends each `state["outbox"]` message to `outbox_delivery.jsonl` with `flush()` + `os.fsync()`, firing hook `after_outbox_delivery`.

---

## 3. Frozen Independent Adversarial Test Matrix (>60 Distinct Actual Tests)

All tests are frozen prior to execution in `tests/test_v06_g1_offline_assurance_r1_*.py`:

1. **Category 1 — Approval Authority (`test_v06_g1_offline_assurance_r1_approval_and_causality.py`)**:
   - Unapproved `PLACE` and `FILL_ENTRY` rejected across `READY`, `NO_ACTION`, `PROPOSED`, `ANALYZED` with zero journal/cash/order effect.
   - Malicious/unknown `token_id`, empty `trusted_approvals` (absent human token), and replayed `token_id` (same proposal and across subsequent post-cooldown proposal).
   - Other-order token (`signal_id` mismatch), `proposal_hash` drift, wrong `quantity` in token, wrong `proposal_version` in token.
   - Future token (`at < token["issued_at"]`), pre-analysis token (`token["issued_at"] < analysis_at`), expired token (`at >= token["expires_at"]`), approval crossing proposal expiry (`at >= proposal["expires_at"]`).
   - Invalid fixture token admission (`approved=False`, untrusted `issuer`, `issued_at >= expires_at`, duplicate `token_id`, non-positive `quantity`).
   - Double approval in `APPROVED` and post-`PLACE` phases.
   - Synthetic mock analysis mutations (`ANALYZE` with wrong `signal_id`, `proposal_hash`, `source_hash`, `risk != "DESCRIPTIVE_ONLY"`, `as_of < decision_at`, `as_of > at`, `at >= proposal["expires_at"]`, invalid `OfflineLLMAnalysisPort` payloads).
   - Wrong side/level ordering in `PROPOSE` for both `LONG` and `SHORT`, plus `NO_ACTION` nonzero quantity rejection.

2. **Category 2 — Causality (`test_v06_g1_offline_assurance_r1_approval_and_causality.py`)**:
   - Incomplete 1m bars (`open_time % 60000 != 0`, `close_time != open_time + 59999`), future `available_at > at`, `available_at < close_time`, non-dense bar gap, stale bar (`at - close_time > 60000`), and invalid OHLC inequalities.
   - Mark-vs-Last strict isolation: extreme `mark_close` excursions never trigger `STOP`/`TP1`/`TP2` or affect execution fill prices; extreme `last_close` excursions never alter `FUNDING` settlements (which use `mark_close`).
   - Same-minute collision precedence: `STOP` vs `TP1` (`STOP_PRECEDES_TP1`), `STOP` vs `TP2` (`STOP_PRECEDES_TP2`), `STOP` vs `TIME_CAP` (`STOP_PRECEDES_TIME_CAP`) for both `LONG` and `SHORT`.
   - 12h, 18h, and 24h time-cap boundaries: early rejection (`TIME_CAP_EARLY`), missed first completed bar rejection (`TIME_CAP_MISSED_FIRST_COMPLETED_BAR`), and exact first-completed-bar execution.
   - ACK before vs after `STOP`:
     - `STOP` before `TP1` ACK (`WAIT_TP1_ACK` → `EXIT_WAIT_ACK`) with both ACK arrival permutations.
     - `STOP` before `FILL_ENTRY` ACK (`WAIT_ENTRY_ACK` → `EXIT_WAIT_ACK`) with both `[entry_ack, stop_ack]` and `[stop_ack, entry_ack]` arrival permutations.
   - C3 stop-update causality: `UPDATE_STOP` rejected before `TP1` ACK, rejected on `TP1` bar, rejected after boundary (`at > close_time + 1`), never loosens an already tighter stop, and blocks same-bar retrospective `STOP` (`STOP_UPDATE_NOT_YET_EFFECTIVE`) while firing on the next completed bar.
   - Late Feishu/outbox receipt (`OUTBOX_RECEIPT`): cannot suppress or bypass a due `STOP` (`REQUIRED_EXIT_UNHANDLED`), and when processed after `STOP`, does not advance `last_at` or block subsequent 1m bars.

3. **Category 3 — Financial Ledger (`test_v06_g1_offline_assurance_r1_ledger_and_recovery.py`)**:
   - Independent Decimal reference oracle across `LONG` and `SHORT` for `STOP`, `TIME_CAP` (12h/18h/24h), and `TP2` without calling reducer internal pricing helpers.
   - Lot rounding (`0.001` increment): odd-lot `TP1` split floors `tier` and leaves larger residual (`0.011` → `0.005` + `0.006`; `0.003` → `0.001` + `0.002`); fractional sub-lot quantities reject (`QUANTITY_INVALID`).
   - Invented proxy fee (`6bp`) and adverse slippage (`5bp` quantized to `0.1` tick via `ROUND_CEILING`/`ROUND_FLOOR`) verified across entry, `TP1`, `TP2`, `STOP` (including adverse opening gap through stop), and `TIME_CAP`.
   - Signed Funding (positive and negative rates) on initial vs post-`TP1` remaining inventory (`remaining_qty`), duplicate `settlement_id` rejection, same-clock alias rejection, `WAIT_ENTRY_ACK`/`WAIT_TP1_ACK` timestamp collision rejection, and rate bound (`|rate| <= 0.1`) enforcement.
   - Persistent `fill_id` deduplication across `FILL_ENTRY`, `TP1`, `STOP`, `TIME_CAP`, `TP2` both before and after ACK.
   - Two pending exit ACK cases (`TP1` + `STOP`, `TP1` + `TP2`, `TP1` + `TIME_CAP`) in both ACK orders, proving exact cash conservation and zero residual `reserved_notional`.
   - Synthetic min-notional (`MIN_NOTIONAL = 1`) fail-closed in `PLACE`, `FILL_ENTRY`, and `TP1` partial split (`qty = 0.001` or low price), explicitly distinguished from Binance production min-notional filters.
   - 5% cash reserve (`notional + fee <= 0.95 * cash`), 1x mark exposure guard (`MARK_EXPOSURE_ABOVE_ONE_X`), nonpositive mark equity guard (`MARK_EQUITY_NONPOSITIVE`), one-position exclusivity, and 6h (`21,600,000 ms`) post-close cooldown boundary (`cooldown_until - 1` vs `cooldown_until`).

4. **Category 4 — Failure and Recovery (`test_v06_g1_offline_assurance_r1_ledger_and_recovery.py`)**:
   - Native OS process-kill (`os._exit(91)`) and restart recovery across **22 checkpoints** (all 15 original checkpoints + 7 novel offsets: `approve_pre`, `place_fsynced`, `entry_snapshotted`, `tp1_pre`, `stop_update_fsynced`, `funding3_fsynced` on the 3rd negative funding settlement, and `stop_appended`).
   - Native OS process-kill (`os._exit(91)`) and restart during simultaneous **two-pending-exit-ACK** state around the second exit ACK (`before_append`, `after_append`, `after_fsync`, `after_snapshot`).
   - WAL and checkpoint tamper/corruption quarantine witnesses (12 modes): torn trailing line (`WAL_TRUNCATED`), duplicate WAL line (`WAL_CHAIN`), record hash mismatch (`WAL_CHAIN`), tampered `event_hash` with recomputed `record_hash` (`WAL_EVENT_IDENTITY`), duplicate `event["id"]` in WAL with valid chain (`WAL_EVENT_IDENTITY`), tampered `state_hash` with recomputed `record_hash` (`WAL_STATE_IDENTITY`), changed genesis fixture (`WAL_GENESIS_MISMATCH`), checkpoint state fork (`CHECKPOINT_IDENTITY`), checkpoint immutable conflict (`CHECKPOINT_IMMUTABLE_CONFLICT`), checkpoint ahead of truncated WAL (`CHECKPOINT_AHEAD_OF_WAL`), missing `outbox_delivery.jsonl` recovery/redelivery, and unknown schema versions (`STATE_SCHEMA`, `WAL_GENESIS_MISMATCH`, `CHECKPOINT_SCHEMA`, `FIXTURE_SCHEMA`).

5. **Category 5 — Output and Safety (`test_v06_g1_offline_assurance_r1_static_and_safety.py`)**:
   - Static AST import & call surface gate + dynamic runtime socket/DNS/HTTP interception trap (`actual_network_calls == 0`).
   - `SafeArgumentParser` CLI secret redaction across invalid flags/values (`exit 3`, static JSON error, zero secret echo, zero directory creation).
   - `redact_text`, `OfflineLLMAnalysisPort`, and `Engine.apply` credential scrubbing (`api_key`, `api-key`, `secret`, `password`, `token`, `bearer`) and reducer `_text` `SECRET_IN_EVENT` rejection.
   - Local JSONL outbox isolation (no clipboard/Feishu network adapter), trace/span linkage, idempotent duplicate event handling (`IDEMPOTENT_DUPLICATE` vs `EVENT_REUSE_DRIFT`), and native single-process `fcntl.flock` concurrency lock (`SINGLE_WRITER_LOCKED`).
