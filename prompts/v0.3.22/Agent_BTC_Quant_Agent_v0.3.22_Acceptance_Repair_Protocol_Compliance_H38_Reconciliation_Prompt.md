# BTC Quant Agent v0.3.22 — Acceptance Repair: H39 Protocol Compliance & H38 Terminal Reconciliation

Repository:

```text
EXASHXE/btc-quant-agent
```

Work on the existing stage branch only:

```text
agent/v0.3.22-microstructure-alpha-foundation
```

Current review lineage when this repair was issued:

```text
main accepted baseline: 497842b07c8048fac4ed9b68827156ce6f51fee2
H39 original prompt: 8da42f27c73dd5381381d7af0466c4149b344440
Gemini protocol audit ACCEPT_PROTOCOL: 3641fbff67a75762d1757e86f4f565289bb88bf3
implementation-after-audit prompt: 50699f471b483d7eb9bb22bf9d66579c3d4f107f
H39 protocol freeze: 0eecd8833675c664c42f5e62d89663d7a10ed5fa
implementation reviewed by Gemini: 24d30c356903b1821cd13bc1f1b77be4755d73be
Gemini post-implementation audit artifact: 57b7973e6e2de869c8194b206575060a1744ef04
```

ChatGPT final verdict on the reviewed implementation is:

```text
REPAIR_REQUIRED
```

Do NOT start v0.3.23. Do NOT ask Gemini for another audit. After this repair, stop and report the exact repair SHA to ChatGPT for final acceptance.

---

## 0. Frozen invariants

These remain unchanged:

```text
strategy = EXPERIMENTAL
qualified_direction_engine = NONE
runtime_maximum = OPPORTUNITY_ONLY
execution = DISABLED
auto_execute = false
live trading = NOT AUTHORIZED
final_holdout = SEALED
```

Also preserve:

```text
NO H39 feature-universe expansion
NO post-hoc sign flip
NO horizon rescue
NO new threshold search
NO neural/AutoML search
NO Forward backfill/reconstruction
NO deleting or rewriting historical Forward evidence
NO reopening stopped official-derivatives symbolic family
```

H39 remains the same research family. This repair is to make the implementation faithfully execute the already-frozen protocol, not to improve weak results.

---

# 1. Finding P0-A — H39 reference-entry implementation violates frozen protocol

Frozen protocol:

```text
configs/research/v0.3.22_microstructure_h39_protocol.json
causal_execution_and_outcomes.reference_entry_rule
= OPEN of first fully available 1m bar strictly after decision close
  (decision_close_ms + 60_000)
```

Reviewed implementation in `src/btc_quant_agent/microstructure_research.py` currently does the equivalent of:

```text
c_start = curr_slot
ref_price = candles[0].open
reference_time_ms = curr_slot
```

This does not match the frozen protocol.

Required repair:

1. Define one explicit H39 `decision_close_ms` semantic and use it consistently.
2. Reference price must come from the first eligible 1m candle whose OPEN timestamp is exactly/at least:

```text
decision_close_ms + 60_000
```

under the frozen protocol.
3. Persist the actual reference candle open timestamp as `reference_time_ms`.
4. Construct 60m and 240m outcomes from the repaired reference semantics deterministically.
5. Do not silently reuse an Opportunity/H38 reference or outcome unless its timestamps are proven exactly identical to H39 frozen semantics. Otherwise construct H39 labels independently from canonical 1m price data.
6. Add direct boundary tests that would fail if the implementation reverts to `reference_time_ms == decision_close_ms`.

Create tests covering at least:

```text
feature cutoff <= decision_close_ms
reference_time_ms >= decision_close_ms + 60_000
reference candle is never the candle beginning at decision_close_ms
60m/240m target timestamps are deterministic relative to repaired reference
future candles cannot alter features
```

---

# 2. Finding P0-B — frozen baseline / incremental-value test is not actually implemented

Frozen protocol baseline:

```text
features:
- trailing_return_15m
- trailing_return_60m
- trailing_atr_ratio_15m
regularization = fixed L2, C=1.0 equivalent
incremental test = likelihood-ratio test and microstructure coefficient statistic
```

Reviewed implementation currently creates:

```text
trailing_return_15m = None
trailing_return_60m = None
```

and later converts both to `0.0`. It also passes raw ATR rather than a frozen dimensionless ATR ratio. Therefore the current `incremental_p_value` does NOT represent incremental information beyond the frozen baseline.

This must be repaired before H39 formal validation can mature.

## 2.1 Commit a protocol-clarification manifest before inspecting any fresh 60m validation label

The frozen protocol names `trailing_atr_ratio_15m` but did not fully spell out its arithmetic. Because no mature fresh H39 validation result existed when this repair was issued, create a narrow clarification artifact BEFORE running/inspecting post-start 60m H39 validation outcomes:

```text
deliverables/v0.3.22/H39_PROTOCOL_CLARIFICATION_001.json
```

The clarification may ONLY complete implementation semantics already implied by the frozen baseline. It may not alter M1-M8, signs, horizons, validation start, alpha, sample gates, or candidate gate.

Freeze these exact baseline formulas unless repository evidence proves an already-frozen equivalent exists:

```text
trailing_return_15m
= decision_close / close_15m_ago - 1

trailing_return_60m
= decision_close / close_60m_ago - 1

trailing_atr_ratio_15m
= ATR14_15m_known_at_decision / decision_close_price
```

All source candles for these baseline features must have close timestamps <= `decision_close_ms`.

Record:

```text
clarification commit SHA
formula definitions
source fields/timeframes
causality rule
statement that zero fresh 60m validation outcomes were inspected before clarification
```

If that last statement cannot honestly be made, STOP and report `REPAIR_REQUIRED_PROTOCOL_CONTAMINATION_RISK` rather than silently continuing.

## 2.2 Implement the actual incremental model

Use a deterministic fixed low-capacity logistic model for future direction, with no tuning:

Baseline:

```text
intercept
+ trailing_return_15m
+ trailing_return_60m
+ trailing_atr_ratio_15m
```

Full model for each formal feature arm:

```text
baseline + signed microstructure feature Mi
```

Requirements:

```text
binary target = future 60m direction
fixed L2 strength equivalent to C=1.0
intercept unpenalized
no feature selection
no hyperparameter search
same baseline for M1-M8
```

Prefer a small deterministic NumPy implementation rather than adding a large ML dependency.

For the incremental test, implement BOTH frozen diagnostics:

```text
1. nested baseline-vs-full likelihood-ratio statistic
2. microstructure coefficient z/t-style statistic with documented covariance method
```

For a 1-df LR test, a deterministic chi-square(1) p-value may be computed without SciPy using the exact df=1 relation if desired.

Do not use the previous hand-made ridge covariance as if it were ordinary OLS covariance without justification.

Candidate eligibility must require the repaired incremental test in addition to the primary familywise gate.

Add tests proving that changing baseline returns/ATR ratio changes the incremental statistic and that baseline fields are never silently replaced by zero because they were uncomputed.

---

# 3. Preserve the H39 validation boundary

Current frozen validation start remains:

```text
H39_VALIDATION_START = 2026-09-04T11:15:00Z
1788520500000
```

Do NOT move it merely because implementation needed repair.

The raw true-Forward microstructure observations after that boundary remain valid evidence if they were naturally captured and were not used to tune the repair.

After repair, rebuild H39 research rows deterministically from raw immutable evidence using the corrected frozen semantics.

Do NOT carry forward any pre-repair derived label/reference cache whose timestamps violate the corrected protocol.

If formal 60m validation labels are not yet mature, keep:

```text
FORWARD_DATA_INSUFFICIENT
```

No candidate can be promoted from development diagnostics.

---

# 4. H38 HIGH finding — reconcile terminal breach now

Gemini audit found that:

```text
OPPORTUNITY_FORWARD_V0321_20260903T180000Z
H38_OPPORTUNITY_FORWARD_REPLICATION_LOCAL_RECOVERY
```

recorded 10 consecutive `MISSED_DECISION_SLOT` observations from approximately:

```text
2026-09-04T07:45:00Z through 2026-09-04T10:00:00Z
```

Frozen maximum:

```text
maximum_consecutive_missed_decision_slots = 4
```

Therefore the campaign is irreversibly terminal. The first gate breach is the 5th consecutive missed slot; audit the immutable SQLite rows directly and derive the authoritative timestamp. Expected timestamp if the audited sequence is exactly as reported:

```text
2026-09-04T08:45:00Z
1788511500000
```

Do not trust this expected value blindly; verify against stored evidence.

Update canonical registry state so H38 is no longer resolvable as active/pending:

```text
status = DATA_QUALITY_TERMINAL_ARCHIVE
formal_role = DATA_QUALITY_TERMINAL_ARCHIVE
terminal_reason = frozen consecutive missed-decision-slot gate breached
terminal_at_ms = actual first breach timestamp
immutable_history = true
```

Do not delete/rewrite/backfill the 10 missed slots.

Do NOT preregister a new Opportunity successor in this acceptance repair. A future successor, if desired, requires a separately explicit prompt and future fixed boundary. In particular, do not reuse `H39` as an Opportunity hypothesis ID because H39 already names the microstructure research family.

Ensure scheduled Opportunity collection fails closed / remains inactive when no eligible active campaign exists, while:

```text
Derivatives successor continues if healthy
Microstructure capture continues if healthy
H39 research validation accumulation continues independently
```

Add a direct regression test that terminal H38 cannot be resolved by normal Opportunity collection/resolution.

Produce/update:

```text
deliverables/v0.3.22/H38_TERMINAL_RECONCILIATION.json
```

---

# 5. Re-run H39 diagnostics with corrected semantics

After the clarification commit and implementation repair:

1. Rebuild development diagnostics from immutable development data.
2. Do not interpret them as formal validation; development remains insufficient unless frozen gates are actually met.
3. Rebuild `H39_VALIDATION_STATUS.json` using only naturally observed post-start data and matured labels.
4. Do not rescue weak results by changing signs/windows/horizons/model hyperparameters.
5. Report separately:

```text
DEVELOPMENT_DATA_INSUFFICIENT / exploratory metrics
FORWARD_DATA_INSUFFICIENT / fresh validation progress
```

Update all relevant v0.3.22 deliverables so they no longer describe the pre-repair reference/baseline implementation as protocol-compliant.

---

# 6. Required tests / quality gates

At minimum run:

```bash
ruff check .
mypy src
pytest -q
python -m compileall -q src tests tools
```

CI must be green across:

```text
Python 3.11
Python 3.12
Python 3.13
```

Required new regression coverage:

```text
reference entry +60s protocol boundary
60m/240m target timestamp semantics
baseline trailing returns are populated causally
ATR ratio is populated causally and dimensionlessly
baseline-vs-full incremental statistic responds to baseline controls
fixed L2 / no tuning
complete Holm family remains exactly M1-M8
H38 terminal irreversibility and resolver exclusion
Final Holdout zero access
execution DISABLED
```

---

# 7. Final repair deliverable

Create:

```text
deliverables/v0.3.22/V0.3.22_ACCEPTANCE_REPAIR_REPORT.md
```

It must list:

```text
reviewed implementation SHA = 24d30c356903b1821cd13bc1f1b77be4755d73be
Gemini audit SHA = 57b7973e6e2de869c8194b206575060a1744ef04
repair prompt SHA
protocol clarification SHA
final repair SHA
H38 first-breach timestamp
H39 validation start unchanged
pre/post repair reference semantics
pre/post repair baseline semantics
current H39 validation maturity
CI run IDs
safety invariants
```

Do not claim H39 alpha success. The expected acceptable state after this repair is likely:

```text
engineering = PASS
H39 = FORWARD_DATA_INSUFFICIENT
H38 = DATA_QUALITY_TERMINAL_ARCHIVE
qualified_direction_engine = NONE
runtime_maximum = OPPORTUNITY_ONLY
execution = DISABLED
```

---

# 8. Stop condition / review workflow

After completing repair:

```text
commit + push exact repair SHA
stop editing
report SHA to user
```

Do NOT run another Gemini audit. ChatGPT performs the final acceptance review directly.

Do NOT merge to `main` yourself unless explicitly instructed after ChatGPT final review.
