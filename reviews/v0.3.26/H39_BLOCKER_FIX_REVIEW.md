# H39 Blocker Fix Review — v0.3.26

## 1. Executive Summary

| Finding | Status | Resolution |
|---|---|---|
| B1 conditional incremental semantics | FIXED | Future formal gate uses unpenalized FWL conditional OLS on continuous 60m return; positive rescaling is invariant and baseline-span candidates are not testable. |
| B2 baseline / maturity / eligibility | FIXED | Maturity counts only `H39_REQUIRED_INPUT_V1` rows; neutral canonical-candle ATR replaces the terminal Opportunity dependency. |
| H1 tail gap | FIXED | Book and trade coverage both check head, internal, and tail gaps; adjacent partitions can jointly supply a continuous window. |
| H2 dual-stream health | FIXED | Book and trade status/age are reported separately and both must be healthy. |
| B3 one-shot precheck ordering | FIXED | Frozen pre-label rows are validated before the atomic execution claim; post-claim crash remains permanently consumed. |

No alpha search, parameter search, backtest, live/testnet execution, formal H39 one-shot, real H39-label read, or Final Holdout access occurred.

## 2. Root Causes

### B1

- Symptom: `candidate = 1000 * baseline` could produce a tiny formal p-value and pass.
- Root cause: the old formal score projection and full-model z statistic inherited a fixed L2 penalty across differently scaled nuisance/candidate variables. It tested improvement of a penalized objective, not uniquely identified conditional information.
- Why tests missed it: tests covered deterministic output and dependence adjustment, but not scaling or baseline-span invariants.

### B2

- Symptom: many `eligible=true` rows with missing baselines could satisfy maturity; ATR stopped arriving when H38 terminated.
- Root cause: eligibility described microstructure only, maturity reused that count, and ATR was read from Opportunity shadow scans.
- Why tests missed it: fixtures supplied baseline ratios without asserting all formal fields, their provenance, or their producer lifecycle.

### H1 / H2 / B3

- H1 checked the head and adjacent gaps but never `decision_ts - last_event_ts`.
- H2 collapsed freshness to `max(book, trade)`, allowing one fresh stream to mask the other.
- B3 persisted `STARTED` before baseline/input validation, conflating retryable precheck failure with post-unblind compute failure.

## 3. Statistical Contract

- Estimand: future continuous 60m return per one standard deviation of the candidate component orthogonal to the frozen controls (`trailing_return_15m`, `trailing_return_60m`, `trailing_atr_ratio_15m`).
- Normalization: each nonconstant baseline and candidate is standardized; the FWL candidate residual is standardized again.
- Estimator: unpenalized SVD least-squares nuisance projection and FWL OLS. Ridge/L2 logistic is retained only as a predictive diagnostic.
- Identification: constant, exact-span, rank-deficient, or near-collinear candidates return `NOT_TESTABLE`, p=1, and cannot pass.
- Dependence: minimum lag is `ceil(60/15)-1 = 3`. Bartlett HAC pairs observations by exact physical timestamp differences, not filtered row index. Missing cadence slots remove unavailable pairs; off-grid and non-monotonic timestamps fail closed.
- Multiplicity: Holm-Bonferroni receives the eight conditional one-sided HAC p-values. Conditional effect, confidence interval, sign, and p-value jointly drive the formal gate.

HAC addresses linear serial covariance through lag three for the specified overlapping horizon. It does not prove power, nonlinear-model adequacy, stationarity, or robustness to arbitrary long-memory/regime shifts.

## 4. Input Contract

`H39_REQUIRED_INPUT_V1` is label-free and requires:

- finite M1-M8;
- finite 15m/60m trailing returns;
- positive ATR14, decision price, and an internally consistent ATR ratio;
- positive book/trade evidence counts;
- exact feature-window, decision, reference, 60m-target, and 240m-target timing;
- valid UTC slot identity;
- source partition names/hashes, base protocol hash, code SHA, and input-contract identity.

Diagnostics separately expose raw, microstructure-eligible, baseline-complete, formal-ready, and exclusion-reason counts. Old rows lacking the corrected contract identity remain preserved but cannot mature the corrected experiment.

ATR is now computed without a strategy dependency: canonical 1m candles → 500 complete causal 15m bars → existing Wilder ATR14 definition. A missing 1m child fails closed; no synthetic or retrospective fill is performed.

## 5. Synthetic Counterexamples

The deterministic suite verifies:

- exact, negative, and 1000x baseline duplicates: `NOT_TESTABLE`, never pass;
- baseline linear combination: `NOT_TESTABLE`;
- near-collinear candidate: conservative `NOT_TESTABLE`;
- correlated conditional null: p-value above 0.05 for the fixed DGP;
- true baseline-orthogonal signal: detected at p<0.01;
- positive scaling from 0.001x to 1000x: effect and p-value equal within 1e-12.

## 6. Test Results

- New blocker suite: **33 passed** (10 statistical invariants, 6 input/maturity, 5 window cases, 5 dual-stream cases, 4 one-shot cases, 2 neutral-ATR cases, and 1 artifact-path compatibility case).
- Relevant v0.3.23/v0.3.24 suites: **37 passed**, one expected deprecation warning.
- Relevant v0.3.25 suite: **59 passed**.
- Full lightweight suite: **580 passed**, with one expected legacy deprecation warning.
- Ruff: **clean** across the repository.
- Focused mypy on all changed source modules: **clean**. Repository-wide mypy reaches one environment/dependency error in unchanged `microstructure.py` because the `websockets` library/stub is not installed; no changed module reports a type error.

## 7. Compatibility

The future formal protocol is explicitly upgraded to v0.3.26 and binds clarification 004, `H39_CONDITIONAL_OLS_HAC_V1`, and `H39_REQUIRED_INPUT_V1` into freeze verification and the execution key. Historical artifacts are not overwritten. Legacy statistical functions remain available only for reproduction/diagnostics; the future one-shot default uses the corrected evaluator.

## 8. Blindness Statement

- No Final Holdout accessed.
- No H39 labels inspected.
- No formal H39 one-shot executed.
- No trading API invoked.
- No real forward raw ledger was read.

## 9. Remaining Risks

- Power is unknown until the predeclared formal-ready sample matures.
- HAC lag three is justified by nominal overlap but does not cover every possible dependence structure.
- Irregular missing slots reduce physical-lag pair counts and effective information.
- Existing pre-v0.3.26 rows are not silently upgraded; production maturity may restart from corrected rows.
- Canonical 1m completeness and 500-bar ATR warmup may be the production bottleneck; legally recoverable PIT history must be assessed without inspecting labels.
- Linear FWL tests conditional linear information, not arbitrary nonlinear conditional predictability.

## 10. Next Recommended Step

Deploy only the corrected label-free accumulator and observe contract diagnostics until enough new v0.3.26 rows exist. Validate operational completeness and ATR availability without loading future-return labels. Do not start another alpha family or formal unblind during that monitoring phase.
