# Phase 1 Pre-Freeze Protocol Review: Gemini-3.8-Flash
**Repository**: `EXASHXE/btc-quant-agent`  
**Stage Under Review**: `v0.3.22` (Microstructure Causal Alpha Foundation & H39 Falsification)  
**Review Date**: 2026-09-04  
**Review Mode**: Phase 1 Pre-Implementation Protocol Independent Audit & Challenge  

---

## 1. Reviewed Protocol Identity

- **Branch**: `agent/v0.3.22-microstructure-alpha-foundation`
- **Reviewed Preregistration Prompt Commit**: `8da42f27c73dd5381381d7af0466c4149b344440`
- **Preregistration File**: `prompts/v0.3.22/Agent_BTC_Quant_Agent_v0.3.22_Microstructure_Causal_Alpha_Foundation_Prompt.md`
- **Base Commit**: `497842b07c8048fac4ed9b68827156ce6f51fee2` (`main`)
- **Research Family**: `H39_MICROSTRUCTURE_DIRECTIONAL_INFORMATION`

---

## 2. Independent Pre-Freeze Verdict

```text
PRE_FREEZE_VERDICT = ACCEPT_PROTOCOL
```

### Verdict Justification:
1. **Genuinely New Information Family**: The protocol evaluates physical L2 order book depth (top 1/5/20 imbalance, OFI, microprice deviation) and aggressor trade flow causally captured by `MICROSTRUCTURE_CAPTURE_V0315_001` since 2026-08-31. It does NOT synthesize depth from candles, nor does it reopen the stopped official-derivatives symbolic search family ($p \approx 0.4328$).
2. **Strict Causality & Anti-Leakage Architecture**:
   - Decision point anchored strictly at closed 15m boundaries.
   - Reference entry price delayed to the OPEN of the first 1m bar *strictly after* the 15m decision close (incorporating causal execution latency).
   - Normalization strictly trailing or contemporaneous; full-series normalization strictly prohibited.
   - ATR for excursion measurement frozen at decision time.
3. **Rigorous Temporal Split & Holdout Isolation**:
   - Development data cut off at the latest finalized partition prior to `H39_PROTOCOL_FREEZE_SHA`.
   - Exclusion buffer enforced between development cutoff and validation start.
   - `H39_VALIDATION_START` anchored at a future closed UTC 15m boundary committed before occurrence.
   - Final Holdout (`[2026-02-01, 2026-08-01)`) remains strictly SEALED (0 rows).
4. **Multiple-Testing Burden Bounded**:
   - Maximum 8 primitive features (M1–M8) with pre-frozen mechanistic signs (no post-hoc sign flipping).
   - Primary horizon fixed at 60m (240m secondary cannot rescue 60m).
   - Holm-Bonferroni FWER ($\alpha = 0.05$) correction enforced across all 8 hypothesis arms.
5. **Realistic Sample Maturity Expectations**:
   - Development requires $\ge 5$ distinct UTC days and $\ge 250$ eligible 15m observations.
   - Fresh validation requires $\ge 14$ distinct UTC days and $\ge 750$ eligible observations.
   - Because `H39_VALIDATION_START` is in the future, the protocol explicitly anticipates reporting `FORWARD_DATA_INSUFFICIENT` during initial implementation, prohibiting false early candidate promotion.

---

## 3. Protocol Evaluation Matrix

| Dimension | Protocol Specification | Compliance / Challenge Assessment | Status |
| :--- | :--- | :--- | :--- |
| **Data Family Novelty** | True Forward L2 diff-depth & aggTrade streams | Genuinely new physical information; not synthetic, not reopening stopped family | **PASS** |
| **Leakage & Look-Ahead** | Feature window $\le$ 15m close; entry at next 1m OPEN | Strict causal ordering; latency buffer enforced; trailing-only normalization | **PASS** |
| **Data Partitioning** | Git-anchored Dev Cutoff $\rightarrow$ Exclusion Buffer $\rightarrow$ Future Validation Start | Clean physical separation; validation data must be naturally observed post-freeze | **PASS** |
| **Multiple Testing** | 8 features (M1–M8); primary 60m horizon; Holm-Bonferroni FWER | Universe strictly finite; familywise $\alpha = 0.05$; no best-backtest selection | **PASS** |
| **Sign Convention** | Pre-frozen mechanistic signs only | Post-hoc sign reversal explicitly prohibited | **PASS** |
| **Sample Size / Maturity** | Dev $\ge 5\text{d} / 250\text{n}$; Val $\ge 14\text{d} / 750\text{n}$ | Appropriate thresholding; acknowledges validation insufficiency in v0.3.22 | **PASS** |
| **Candidate Gate** | Provisional only; requires FWER $p < 0.05$ & CI excluding 0 | No runtime execution or direction engine promotion authorized in this stage | **PASS** |
| **Collector Protection** | Background systemd collectors protected | Read-only access against Forward SQLite databases mandated | **PASS** |

---

## 4. Mandatory Implementation Guardrails

The implementation agent must adhere strictly to the following 4 engineering and research guardrails:

1. **Strict Two-Commit Lineage**:
   - The protocol JSON (`configs/research/v0.3.22_microstructure_h39_protocol.json`) must be committed first to establish `H39_PROTOCOL_FREEZE_SHA`.
   - No label inspection, correlation, regression, or IC computation may occur prior to this freeze commit.
2. **SQLite Read-Only Concurrency Protection**:
   - The host daemon is actively appending to `microstructure-2026-09-04.sqlite3`.
   - All research loaders must connect using read-only URI semantics (`file:path?mode=ro`, `uri=True`) or `PRAGMA query_only = ON` to prevent lock contention with the live collector.
3. **M6 Mid-Price Derivation Pre-Verification**:
   - Verify whether `book_samples` contains sufficient top-level bid/ask or spread fields to reconstruct mid causally. If mid cannot be reconstructed without ambiguity, M6 must be formally marked unsupported and the universe reduced to 7 features before protocol freeze.
4. **Economic Expectation of Alpha Decay**:
   - Microstructure imbalances typically dissipate within seconds to minutes. Testing at 60m is a high-hurdle falsification test.
   - If adjusted $p$-values exceed 0.05, this negative result must be reported honestly as `RESEARCH_FAMILY_STOP` or `FORWARD_DATA_INSUFFICIENT`. Do not post-hoc shift horizons to 5m.

---

## 5. Safety Invariant Confirmation

```text
strategy: EXPERIMENTAL
qualified_direction_engine: NONE
runtime_maximum: OPPORTUNITY_ONLY
execution: DISABLED
auto_execute: false
final_holdout: SEALED (0 rows read, 0 bytes accessed)
live trading: NOT AUTHORIZED
```

All 6 institutional safety gates remain active and fail-closed.

---

## 6. What Would Falsify My Conclusion

To prevent reviewer overconfidence, this protocol approval (`ACCEPT_PROTOCOL`) would be falsified if:
1. **Underlying Capture Time Conflation**: An audit of raw microstructure databases reveals that `receive_time_ms` and `event_time_ms` are corrupted or reversed during websocket capture, introducing invisible look-ahead into "causal" windows.
2. **Hidden Universe Expansion**: The implementation code performs an unrecorded grid search over feature parameters (e.g. testing 1m, 3m, 5m, 10m, 15m windows) while reporting only the best window as M1–M8, rendering the nominal 8-feature FWER correction invalid.
3. **Database Concurrency Deadlock**: Despite read-only connections, batch processing of large SQLite partitions triggers database locks that disrupt live collection on `MICROSTRUCTURE_CAPTURE_V0315_001`.

---

## 7. Advisory Next Steps

- Implementation agent proceeds with single-writer implementation on `agent/v0.3.22-microstructure-alpha-foundation`.
- Step 1: Commit `configs/research/v0.3.22_microstructure_h39_protocol.json`.
- Step 2: Implement pipeline, unit tests, and development diagnostics.
- Step 3: Emit deliverables and report exact reviewable SHA for Phase 2 blind post-implementation audit.
