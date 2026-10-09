# Alternative Event-Journal Engine Implementation and Handoff Report

**TASK_ID:** `V06_G2_R3_P1_ALT_ENGINE_GEMINI_A_IMPLEMENTATION_R1`
**Author / Worker:** Gemini A Implementation Worker
**Repository:** `EXASHXE/btc-quant-agent-public`
**Branch:** `feature/v06-bline-g2-r3-p1-alt-engine-gemini-a-r1`
**Target Package:** `src/btc_quant_agent/strategy_research/r3_alt_engine`
**Status:** IMPLEMENTATION COMPLETE, FULL SYNTHETIC AUDIT VERIFIED

---

## 1. Provenance and Authoritative References

| Reference | SHA / URI | Description |
| :--- | :--- | :--- |
| `CONTROLLER_DISPATCH_SHA` | `70236530a0bc1927772493c80ea1f00495088034` | Real Controller implementation authorization |
| `AM01_AM02_FREEZE_SHA` | `821d23427a5f6d0b4635f32f226ddc779358ab72` | Controller AM01/AM02 normative specification freeze (Method R1.2) |
| `SOL_DESIGN_SHA` | `c0b41d1ce62e0fe852edfc6e162f1bc3dc6dcc01` | Sol event-ledger architecture, 17 invariants, T01–T34 oracle cases |
| `CODE_START_SHA` | `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32` | Starting parent commit on `v0.6` |
| `PINNED_PROMPT_SHA` | `ed180ebd7966007f5f3e2398cf7d438c9e73aa06` | Pinned implementation instruction prompt |
| `ORIGINAL_CANDIDATE_SHA` | `e5b2006a89441f7eb2ec900e508aff451106b87a` | Original 8 candidate IDs and indicator definitions |
| `ACCEPTED_R11_SHA` | `cf2d5cc33774cdcff7d709636305bba830e977ef` | Accepted limited PIT and cost baseline R1.1 |

---

## 2. Module Architecture and Responsibilities

The package is strictly organized into 10 decoupled, deterministic, functional modules:

```
src/btc_quant_agent/strategy_research/r3_alt_engine/
├── __init__.py               # Public API exports
├── model.py                  # 8 frozen records, enums, pure data structures
├── frozen_primitives.py      # Frozen indicators (ATR, EMA, ER), candidate registry, cost geometry
├── journal.py                # Cryptographic payload hashing, conflict detection, balanced batch journal
├── money.py                  # Double-entry subledgers, AM02 capital/risk formulas, I01–I17 invariants
├── clock.py                  # Minute-aligned clock progression, tie-breaking, causality gates
├── execution.py              # Pure B04 execution semantics, SL-first, open gap, favorable exit capping
├── signals.py                # Pure 8 formula predicates, Retest cursor, AM01 dual-role normative gate
├── reducer.py                # Pure transactional state transition reducer reduce(state, event, config)
└── replay.py                 # In-memory ReplayEngine for BASE/STRESS multi-policy synthetic replay
```

### Module Breakdown

1. **`model.py`**:
   - Declares 8 frozen immutable dataclasses: [`Event`](file:///root/workspace/project/quant-v0.6/g2-p1-alt-engine-gemini-a-r1/src/btc_quant_agent/strategy_research/r3_alt_engine/model.py), [`Posting`](file:///root/workspace/project/quant-v0.6/g2-p1-alt-engine-gemini-a-r1/src/btc_quant_agent/strategy_research/r3_alt_engine/model.py), [`OwnerLedger`](file:///root/workspace/project/quant-v0.6/g2-p1-alt-engine-gemini-a-r1/src/btc_quant_agent/strategy_research/r3_alt_engine/model.py), [`RetestState`](file:///root/workspace/project/quant-v0.6/g2-p1-alt-engine-gemini-a-r1/src/btc_quant_agent/strategy_research/r3_alt_engine/model.py), [`Projection`](file:///root/workspace/project/quant-v0.6/g2-p1-alt-engine-gemini-a-r1/src/btc_quant_agent/strategy_research/r3_alt_engine/model.py), [`EngineState`](file:///root/workspace/project/quant-v0.6/g2-p1-alt-engine-gemini-a-r1/src/btc_quant_agent/strategy_research/r3_alt_engine/model.py), [`ReplayConfig`](file:///root/workspace/project/quant-v0.6/g2-p1-alt-engine-gemini-a-r1/src/btc_quant_agent/strategy_research/r3_alt_engine/model.py), [`ReplayReport`](file:///root/workspace/project/quant-v0.6/g2-p1-alt-engine-gemini-a-r1/src/btc_quant_agent/strategy_research/r3_alt_engine/model.py).
   - Enums: 12 [`EventKind`](file:///root/workspace/project/quant-v0.6/g2-p1-alt-engine-gemini-a-r1/src/btc_quant_agent/strategy_research/r3_alt_engine/model.py) types, 6 [`AccountType`](file:///root/workspace/project/quant-v0.6/g2-p1-alt-engine-gemini-a-r1/src/btc_quant_agent/strategy_research/r3_alt_engine/model.py) accounts, 7 [`OwnerPhase`](file:///root/workspace/project/quant-v0.6/g2-p1-alt-engine-gemini-a-r1/src/btc_quant_agent/strategy_research/r3_alt_engine/model.py) states, [`Direction`](file:///root/workspace/project/quant-v0.6/g2-p1-alt-engine-gemini-a-r1/src/btc_quant_agent/strategy_research/r3_alt_engine/model.py), [`CostScenario`](file:///root/workspace/project/quant-v0.6/g2-p1-alt-engine-gemini-a-r1/src/btc_quant_agent/strategy_research/r3_alt_engine/model.py).
   - Validates exact `Decimal` precision and strictly typed IDs.

2. **`frozen_primitives.py`**:
   - Preserves original 8 candidate definitions: 4 Structural Continuation variants + 4 Retest Breakout variants across 4h and 12h holding horizons.
   - Exact mathematical indicator calculations: ATR20 (`high - low`), EMA (`alpha = 2/(N+1)`), Efficiency Ratio (`ER12 = |C_t - C_{t-12}| / \sum |C_i - C_{i-1}|`).
   - Standardized cost geometry: BASE (22bp roundtrip + 4bp funding proxy), STRESS (44bp roundtrip + 8bp funding proxy).

3. **`journal.py`**:
   - Implements deterministic SHA-256 payload digests via `compute_payload_digest(event)`.
   - Rejection of conflicting duplicate events with different payloads (`ConflictFailClosedError`).
   - Causal graph verification and owner verification (`CauseOrOwnerFailClosedError`).
   - Ensures each appended event produces balanced double-entry batches ($\sum \text{debits} == \sum \text{credits}$).

4. **`money.py`**:
   - Owner-scoped subledgers indexed by `(book_id, position_id, settlement_id)`.
   - Immutable double-entry bookkeeping with 12 decimal places quantization (`ROUND_HALF_EVEN`).
   - Normative AM02 capital & risk formulas: $E_d, E_c, P_f, C_o, R_f, L_f, A_{\text{raw}}, A, B$.
   - Comprehensive invariant validator checking all 17 invariants (`I01` through `I17`) on every state transition.

5. **`clock.py`**:
   - Strict minute-aligned progression (`advance_to(aligned_open_ms)`).
   - Immediate fail-closed rejection of non-minute timestamps (`InvalidMinuteClockError`).
   - Strict separation of economic time, knowledge availability time, and ACK visibility time.
   - Deterministic tie-breaking across events arriving at the same timestamp.

6. **`execution.py`**:
   - B04 execution engine with stop-loss prioritization within the same bar.
   - Open gap handling ensuring adverse fills take the worse price.
   - Favorable exit capping across TP, TIME, KILL, and REDUCTION orders.
   - 4h / 12h hold expiry adjudicated on the exact first due open minute.

7. **`signals.py`**:
   - Frozen signal predicates for continuation and retest breakout candidates.
   - Sequential chronological cursor advancing 1h bars without lookahead.
   - AM01 normative dual-role gate: terminal breakout bars cannot seed new breakout candidates in the same hour.

8. **`reducer.py`**:
   - Pure state transition function `reduce(old_state, event, config) -> (new_state, postings, scheduled_events)`.
   - Guarantees zero side-effects and atomic updates.

9. **`replay.py`**:
   - In-memory synthetic simulation runner `ReplayEngine.run_simulation`.
   - Produces comprehensive `ReplayReport` with event sequence hash, candidate performance, book cash balances, and terminal liability verification.

---

## 3. Normative AM01 / AM02 Specification (Method R1.2)

### 3.1 AM01 Normative Dual-Role Gate
Under prior ambiguous interpretations, an hour $H$ that triggered a cancellation or confirmation of an existing breakout was sometimes simultaneously treated as an entry signal for a new candidate.
**Method R1.2 Specification:**
- Hour $H$ cannot simultaneously serve as a terminal transition (cancel, confirm, or expire) and seed a new breakout.
- Only a subsequent distinct hour $H+1$ or later can seed a new breakout, provided all qualification conditions hold.

### 3.2 AM02 Conservative Capital and Risk Accounting
Under Method R1.2, capital safety is maintained through conservative risk projections:
1. **Decision Equity ($E_d$):**
   $$E_d = C - P_f$$
   Where $C$ is settled cash and $P_f$ is visible funding payables.
2. **Conservative Equity ($E_c$):**
   $$E_c = E_d - L_{\text{pending\_exit}} - \text{unpaid\_fees}$$
   Visible exit losses reduce conservative equity immediately upon exit execution, but positive unacknowledged receivables cannot inflate equity ($I17$).
3. **Funding Union Encumbrance ($R_f + L_f$):**
   - $R_f$: Funding reserve on unsettled funding intervals.
   - $L_f$: Estimated funding liability on active positions.
   The total funding encumbrance is $R_f + L_f$. $P_f$ is not subtracted a second time from available capital $A$.
4. **Operating Cash & Fee Cover ($C_o$):**
   $$C_o = \text{cash\_encumbered} + \text{fee\_cover}$$
   Fee cover in $C_o$ is atomically converted to fee expense when fee payables become visible ($T34$).
5. **Available Capital ($A$):**
   $$A_{\text{raw}} = E_c - C_o - (R_f + L_f)$$
   $$A = \max(0, A_{\text{raw}})$$
6. **Risk Kill Threshold:**
   When $E_c \le 100$ USDT, the risk kill latch activates permanently ($T19$). Once latched, no new orders can be accepted.

---

## 4. Verification and Invariant Auditing

### 4.1 Oracle Cases (T01–T34) Summary
All 34 required oracle test cases have been implemented across three test modules and verified with 100% pass rates:

- **Events & Money (`tests/test_r3_alt_events_money.py`):**
  - `T01`: Same close Mark conflict detection.
  - `T02`: Delayed future Mark rejection.
  - `T03`: Late same close Mark conflict fail-closed.
  - `T04`: Report decision isolation.
  - `T05`: Mark staleness boundary check.
  - `T06`: ACK duplicate idempotent handling.
  - `T07`: ACK payload conflict detection.
  - `T08`: Older ACK does not rewind cooldown.
  - `T09`: ACK owner and cause validation.
  - `T10`: Funding shortfall and owner isolation witness.
  - `T11`: Funding ACK delayed / out-of-order handling.
  - `T12`: Exit before $S$ remains in funding window.
  - `T13`: Rejection of non-minute clock calls.
  - `T14`: Exact position ID matching (no prefix/substring collision).
  - `T15`: Pre-funding window cannot know future ownership.
  - `T16`: Standardized pending loss witness ($-169.336545$ USDT).
  - `T17`: Unacknowledged gains cannot inflate capital.
  - `T18`: Small pending loss reduces available capital.
  - `T19`: Permanent risk kill latch at $\le 100$ USDT.
  - `T32`: Different pending slices non-netting ($I17$).
  - `T33`: Capital deficit and negative equity bounds.
  - `T34`: Atomic fee cover conversion on fee payable notice.

- **Clock & Execution (`tests/test_r3_alt_clock_execution.py`):**
  - `T20`: Same-bar stop-loss prioritization.
  - `T21`: Adverse open gap fill at worse price.
  - `T22`: Favorable exit capping across TP, TIME, KILL, REDUCTION.
  - `T23`: Hold duration exact expiry at first due open.
  - `Comprehensive I01–I17`: Machine verification of all 17 invariants.

- **Retest & Replay (`tests/test_r3_alt_retest_replay.py`):**
  - `T24`: Skipped intermediate hour cancels prior boundary.
  - `T25`: Three-hour extrema stop calculation.
  - `T26`: AM01 dual-role normative gate verification.
  - `T27`: Candidate cost geometry and stress hurdle evaluation.
  - `T28`: Full 4h BASE and STRESS non-empty simulation replays.
  - `T29`: Full 12h BASE known schedule replay and STRESS infeasibility diagnostic.
  - `T30`: Decimal permutation partial exit preservation.
  - `T31`: Boundary safety and fail-closed missingness.

### 4.2 Machine Invariants (I01–I17)
Every transaction satisfies the complete set of 17 Sol machine invariants:
- **I01:** Double-entry postings balance ($\sum \text{Dr} == \sum \text{Cr}$).
- **I02:** Cash balance non-negative unless terminal loss exceeds equity.
- **I03:** Trade receivables $\ge 0$.
- **I04:** Unpaid payables $\ge 0$.
- **I05:** Fee expense $\ge 0$.
- **I06:** Funding expense matches cumulative accruals.
- **I07:** Encumbered cash $\le$ settled cash.
- **I08:** Available capital $A \le E_c$.
- **I09:** Decision equity $E_d == C - P_f$.
- **I10:** Conservative equity $E_c \le E_d$.
- **I11:** Capital deficit $B == \max(0, 100 - E_c)$.
- **I12:** Risk kill latch is monotonically non-decreasing.
- **I13:** Owner phase transitions are valid DAG edges.
- **I14:** Closed positions have zero open position exposure.
- **I15:** No lookahead beyond knowledge availability horizon.
- **I16:** Exact position identity matching.
- **I17:** Non-netting of unacknowledged receivables against pending exit losses.

---

## 5. Test Execution Evidence and Environment

The test suite was run and verified under both Python environments:
- **Python 3.13.13**: 35 passed in 27.05s
- **Python 3.12.3**: 35 passed in 25.98s
- **Lint & Types**: `ruff check` passed (0 errors), `mypy` passed (0 errors in 10 source files).
- **Compilation**: `python -m compileall src/ tests/ scripts/` passed (0 errors).

---

## 6. Audit & Handoff Readiness

The package `btc_quant_agent.strategy_research.r3_alt_engine` is complete, fully hermetic, and adheres strictly to all frozen specifications. It is ready for independent review by the Controller and verifiers.
