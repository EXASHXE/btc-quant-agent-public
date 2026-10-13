# P1D-R3 Independent Causal Funding/PIT and Ledger Audit — R1

**Independent reviewer:** ChatGPT-1, Independent Supervisory Auditor (not the P1D Gemini BOOST implementer or the B-line Controller).  
**Review date:** 2026-10-13 (Asia/Singapore).  
**TERMINAL VERDICT: `INTEGRATION_BLOCKED`.** This is an independently authored static code-path and immutable-CI evidence review. It is **not** a successful integrated Funding/cash-ledger test, a full CI pass, source certification, G2 Alpha, or release approval.

## 1. Immutable identity and publication boundary

| Item | Exact identity |
| --- | --- |
| Repository | `EXASHXE/btc-quant-agent-public` |
| Controller P1D-R3 audit dispatch / verified docs HEAD at review start | `efe0dce0773e2ac76771dda7847a4dffbe867ceb` |
| Auditor sidecar authorized parent | `2c99c8f64368a02dfeca05ac1886ed2280faf3ba` |
| Frozen reviewed implementation | `81c613c3c8dc3fb22fd4d09b2d0ef4674f09c079` |
| Read-only implementation baseline | `91495e5b8c178e60f3cf2f56eab3ad4deeb7c86b` |
| Port blob, reviewed SHA | `scripts/g1g3_offline_ports_r1/market_pit_port.py`: `3c2198325649ea3a64986218ec60953cbb889403` |
| Changed core tests blob | `tests/test_v06_g1g3_offline_ports_r1_core_integration.py`: `92261a755f8ad94cbb0d5d1e8332537cf6e6c40c` |
| Changed recovery tests blob | `tests/test_v06_g1g3_offline_ports_r1_recovery_and_guards.py`: `398a48c5463a171da22185a43405f9dce10018b7` |
| Unchanged downstream reducer blob at reviewed SHA | `scripts/g1_offline_preview_r1/reducer.py`: `df6a68f4797950f1b9bdbdebc6591745cdea76d5` |
| Downstream G1 WAL/engine blob at reviewed SHA | `scripts/g1_offline_preview_r1/storage.py`: `4d250f5123d57d4df7430b9dc911b5b5208ba81e` |
| Sidecar supervisor blob at reviewed SHA | `scripts/g1g3_offline_ports_r1/durable_supervisor.py`: `9c0fec44287911fad6a64d274f44b9a8c90388d4` |
| P1D implementation author report blob | `84a4448df7c85db1d0caf04cc16351fa65e248a1` |
| Actual full GitHub CI | [Run 38390261764](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38390261764), job `115272035493`, checked-out HEAD `81c613c3c8dc3fb22fd4d09b2d0ef4674f09c079` |

The implementation ancestor comparison `91495e5...81c613c` contains exactly five paths: the port, two P1D tests, a synthetic receipt, and the author report. The report's claim of an “INDEPENDENT AUDITOR: Codex Sol High” is **not** a separate attributable reviewer artifact. Before this review, the requested docs review branch did not exist; GitHub code search and an independent-audit commit/issue search did not identify a verifiable earlier standalone report. This new report is the independently attributable review; it does not claim an unseen Sol execution.

**Methods:** independently inspected the exact remote GitHub blobs, G1 interfaces, sidecar recovery and final CI job log. No local test execution or local checkout was performed. The examples below are **static falsifying witnesses** derived from explicit branch conditions, **not** falsely claimed executed tests. No datasets or exchange APIs were accessed.

## 2. Positive, scope-limited observations (ACCEPTED only at the synthetic port level)

- **OBSERVED:** `MarketPitPort.ingest_envelope` checks receiver `available_at_ms >= observed_wall_utc_ms`, provider event bounds and optional decision-reference future/staleness bounds (port lines 181–208); `_translate_funding` permits `available_at_ms > settlement_at_ms` but rejects receipt before settlement (lines 390–392).
- **OBSERVED:** funding economic identity is checked against in-memory `seen_funding_settlements` and `seen_funding_clocks`; conflicting rate/event_id/Mark or economic timestamp raises, while identical replay is suppressed (port lines 403–436). This is **in-process** duplicate handling, not a durable cash-accounting proof.
- **OBSERVED:** pure synthetic helpers implement `cash = -signed_exposure * mark * rate`, with separate long/short signs, and compute before-settlement partial exits (port lines 599–735). Missing Mark/rate and explicitly incomplete coverage return `COST_INCOMPLETE`. Existing synthetic cases exercise ordinary signs, zero and partial fills. They do not prove venue Mark identity, actual fills, receipt ACK or wallet cash reconciliation.
- **OBSERVED:** `validate_decision_pit` compares decisions against `max_feature_known_at_ms` (lines 438–442). This is port state only; no end-to-end time-indexed decision snapshot/recovery contract was established.

## 3. Consequential findings (maximum three)

### F1 — BLOCKER: receiver-known-at is lost at the translated G1 boundary; chronological application fails or leaks future information

**Exact evidence:**
- Port `market_pit_port.py:294–306` returns `available_at_ms` and `feature_known_at_ms` in the **ingest receipt**, but `_translate_funding:427–436` emits `g1_event = {"id", "kind":"FUNDING", "at":settlement_at, "payload":{"settlement_id", "settlement_at", "rate_fraction"}}`. The G1 event has no `available_at`/receiver-known-at.
- `reducer.py:210–225` requires `at >= state["last_at"]` and rejects backward time with `EVENT_REORDERED`. `reducer.py:508–517` requires Funding payload settlement time to equal G1 `event.at`. `storage.py:263–280` invokes this reducer before committing to its WAL. `durable_supervisor.py:330–355, 513–538` translates synthetic events and applies each to G1; it does not persist the distinct late-Funding receiver clock in the G1 event.

**Minimal static counterexample:** settle at `480000 ms`; a subsequent bar is received and applied at `539999 ms`; the settlement record arrives at receiver time `540000 ms`. The port accepts a late settlement and emits `FUNDING.at = 480000`. Applying it after the later bar makes `480000 < last_at=539999`, hence G1 raises `EVENT_REORDERED`. Alternatively sorting it before the bar by economic time introduces information that was not received until `540000` into an earlier decision-time state unless a different as-of mechanism is introduced and proved. Simply rewriting `g1_event.at` to arrival time is **not** a legal fix: current Funding reducer requires equality with settlement time, and financial exposure must remain at economic settlement.

**Consequence:** the explicit requirement “a late settlement is recognized causally without retroactive market feature visibility” is **not shown compatible with the actual G1 event contract**. No production integration acceptance is possible.

**Lowest-scope follow-up, only under new Controller code authority:** introduce a separately verified receipt-time ordering contract and immutable economic settlement fields, or an explicit retroactive cash adjustment mechanism with non-retroactive decision state. Test the counterexample end-to-end through Engine WAL, restart and earlier decision snapshots. Do not change historical strategy outcomes or protected data.

### F2 — BLOCKER: settlement Mark and position are not causally reconciled by the downstream ledger

**Exact evidence:**
- The port parses optional positive `mark_price` or `mark_close` into the in-memory settlement fingerprint (`market_pit_port.py:397–425`), but `g1_event.payload` **drops Mark** (`427–436`).
- Actual G1 Funding reducer uses `bar = _bar(s, at)`, then `bar["mark_close"]` and **current** `s["remaining_qty"]` (`reducer.py:508–529`). `_bar` only establishes a synthetic recent-bar availability/staleness bound (`reducer.py:37–43`); it is not an authenticated Mark-at-economic-settlement or fill-history witness.
- `compute_settlement_exposure` correctly asks for pre-settlement fills as a standalone helper (`market_pit_port.py:691–735`), but no observed `durable_supervisor.py`/G1 reducer invocation connects that exposure result to an actual Funding WAL journal row. The existing reducer still computes with its own `remaining_qty`.

**Minimal static counterexample:** a LONG position is `0.010 BTC` at settlement `T` with Mark `60000` and funding rate `+0.0001`; a `0.004 BTC` exit executes after `T` but before delayed Funding receipt. Correct economic settlement charge is `-0.010*60000*0.0001 = -0.0600 USDT`. A receiver-time state with `remaining_qty=0.006` produces only `-0.0360 USDT` if erroneously used. Port pure-helper tests recognize this distinction, but no end-to-end G1 account-state proof eliminates it. Similarly, a valid settlement Mark witness ingested at the port is not carried to the G1 ledger.

**Consequence:** exactly-once **economic** cash, partial-exit valuation and Mark source completeness are not integration-proved; a port-level `COST_COMPLETE` is not a posted financial ledger entry. This is an integration blocker independent of the chronological rejection in F1.

**Lowest-scope follow-up:** require settlement-keyed, witnessed Mark/rate/source and pre-settlement executed-position snapshot (or equivalent immutable fill ledger); journal a signed cash delta exactly once with replay/recovery invariants. Test long, short, flat, before/after partial exits, missing Mark, ±15 s settlement-window uncertainty (where relevant), and crash boundaries. Unknown settlement economic coverage must remain `COST_INCOMPLETE`, never zero cash by default.

### F3 — HIGH: in-memory settlement dedupe and unqualified helper defaults cannot establish durable financial completeness

**Exact evidence:**
- `MarketPitPort.__init__:103–114` initializes `seen_dedupe_keys`, `seen_funding_settlements`, `seen_funding_clocks` and max known-at in memory. `durable_supervisor.py:330–335` constructs a new port per scenario; `durable_supervisor.py:209–260` recovers sidecar WAL kinds `LLM_ANALYSIS_RECORDED` and `SIMULATED_INTENT_SETTLED`, not port funding state. The G1 engine **does** journal `used_settlements` in its own state (`reducer.py:508–531`, `storage.py:252–301`); however, there is no demonstrated atomic port-accept → G1-cash-post → ACK/restart transaction for delayed Funding.
- `calculate_settled_funding_cash_flow(..., funding_coverage_complete=True)` defaults to **true** without consuming any Mark source witness, rate receipt identity, completeness interval or wallet posting evidence (`market_pit_port.py:599–687`). `quantity` is normalized with `abs(raw_qty)` before combining with `side` (`645–677`): e.g. `side="LONG", quantity="-0.010"` is silently treated as positive long. For the supported signed-SHORT helper convention this normalization is intentional, but a contradictory LONG/negative input is not rejected. This is a concrete unchecked interface invariant, not a claim that the existing tested SHORT case is wrong.
- Recovery tests at `tests/test_v06_g1g3_offline_ports_r1_recovery_and_guards.py` cover general synthetic crash/restart and Funding clock regression, not a late-Funding exactly-once end-to-end economic posting across a crash. An unqualified helper “complete” status cannot substitute for independent source completeness.

**Minimal static witness:** reconstruct a new `MarketPitPort()` after accepting a settlement; its in-memory `seen_funding_settlements` is empty, so the same settlement can be accepted at the port again under a new transport sequence. The separate G1 `used_settlements` guard may prevent a second cash post **if and only if** G1 already committed and rebuilt its WAL state. Atomicity and delivery/retry behavior are **UNKNOWN**, not proven double-posting.

**Consequence:** classify the calculation as a synthetic helper, not a receiver-to-wallet exactly-once settlement implementation. Demand a fail-closed provenance and side/quantity contract before economic certification.

**Lowest-scope follow-up:** in the separately authorized G1 boundary work, replay one settlement under same/different transport keys before/after crash at each journal edge, inject conflicting Mark/event_id/rate, verify reconstructed economic settlement identity and exactly one signed cash journal effect, and reject contradictory side/quantity forms. No external market data is necessary for this synthetic witness.

## 4. Executed CI and evidence limits

**OBSERVED remote GitHub Actions:** [Run `38390261764`](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38390261764), exact `head_sha=81c613c3c8dc3fb22fd4d09b2d0ef4674f09c079`, status `completed`, conclusion **failure**. Python 3.12 risk-based quality job `115272035493` executed Ruff, type/compile/JSON checks and real tests; pytest log records **3357 passed, 3 failed, 2 skipped**. The three failures are:
- `test_catalog_reports_actual_paths_and_parser_without_service`
- `test_catalog_default_stdout_never_recreates_reviews`
- `test_catalog_refuses_agent_documents_on_code_branch`

All three fail because a review Markdown on the code branch makes `ROOT/"reviews"` exist. This is **not** evidence that scientific finance tests failed, and **not** a full CI PASS. A docs-only successful workflow with executable pytest skipped cannot repair this. Compatibility full job was skipped. A separate Controller dispatch `efe0dce...` authorizes only carefully segregated report-archive/code-docs work by another executor, not this auditor changing code/tests.

**Existing claimed local tests:** P1D author receipt states `155 passed` and 13 targeted funding cases. This reviewer inspected test source but did **not** re-execute those commands. Therefore local test count is labelled **AUTHOR-REPORTED**, not `REPRODUCED_BY_AUDITOR`.

**New reviewer-executed tests:** NONE. No local fixture, remote desktop, historical PnL data, protected H39/H40/H41/Forward/holdout path, personal market root, private account, credentials, exchange endpoints, Feishu send or real funds were inspected or modified.

**Independent result:** this read-only audit independently establishes the **F1 event-clock boundary conflict** directly from exact implementation/G1 code, the **F2 Mark/exposure integration gap**, and **F3 unresolved durability/completeness invariants**. It does not assert that a test suite has empirically reproduced failures, nor that double charges occurred in observed trading.

## 5. Finite next action and stop condition

**Auditor recommendation to ChatGPT-0:** issue **one bounded synthetic-only G1/P1D integration-contract review/repair authorization**, only after reviewing this report. Keep the separate existing code/docs CI relocation job isolated; do not repeatedly re-run the full 3,362-case suite until the exact repair SHA warrants a final run.

Acceptance must include:
1. A late-settlement event delivered **after** a newer BAR yields no `EVENT_REORDERED`, no earlier-decision information leak, and correct persisted receiver-known-at plus economic settlement-at through G1 Engine WAL and recovery.
2. Funding cash uses a demonstrably settlement-time Mark source and fill-position exposure, supports partial exit/short/flat and funding sign, and is charged once even across at least one injected crash before and after WAL commit; missing/uncertain witnesses fail closed.
3. A separate full GitHub CI on the exact new implementation commit actually executes pytest and passes required compatibility/policy gates; the already-authorized docs segregation must be completed without weakening catalog/H40 golden tests. Reviewer verifies SHA/test receipt; Controller alone decides merge/release authorization.

**Stop:** if the immutable G1 event contract cannot express both receiver-known-at and economic settlement without violating chronological replay, stop patching Consumer C in isolation. Escalate a versioned G1 event/WAL contract redesign, preserving existing protected science and branch ownership.

**Terminal decision:** `INTEGRATION_BLOCKED`. **Auditor strategic route recommendation:** `BOUNDED_REPAIR`, solely an advisory recommendation. `G2_ALPHA=NO_GO`, `TESTNET=NOT_AUTHORIZED`, `LIVE=NOT_AUTHORIZED`, `REAL_FUNDS_WRITE=NONE`. No source admission, historical outcome re-scoring, code edits, autonomous trading, branch merge or release authority granted.

## 6. Publication receipt boundary

Authorized branch: `docs/v06-p1d-independent-causal-review-r1`, rooted at `2c99c8f64368a02dfeca05ac1886ed2280faf3ba`. This report is the **only new file**. Its Git commit SHA is reported in the separate delivery message after GitHub creates the commit, rather than creating a self-referential unhashable commit assertion within this file.
