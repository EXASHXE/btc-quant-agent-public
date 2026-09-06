# BTC Quant Agent v0.3.25 — Statistical Dependence & Forward Health Truthfulness Repair

Repository:

```text
EXASHXE/btc-quant-agent
```

Accepted baseline:

```text
main
4e22c657c12f9e4a97b3b47bdfb3e8da598cabb2
```

This is a **narrow scientific-validity and observability repair** to the accepted v0.3.25 H39 preregistration machinery.

Do NOT reopen H39 feature design, signs, horizons, sample gates, candidate rules, execution policy, or Final Holdout.

Current live H39 remains blind and immature. **Zero real H39 validation outcomes may be inspected or materialized during this repair.**

---

## 0. Frozen invariants

Keep unchanged:

```text
hypothesis = H39_MICROSTRUCTURE_DIRECTIONAL_INFORMATION
validation_start = 2026-09-04T11:15:00Z
formal family = M1-M8 exactly
predefined signs = frozen
primary horizon = 60m
secondary horizon = 240m supporting only
Holm-Bonferroni FWER alpha = 0.05
minimum distinct UTC days = 14
minimum eligible observations = 750
minimum eligible-boundary coverage = 90%
strategy = EXPERIMENTAL
qualified_direction_engine = NONE
runtime_maximum = OPPORTUNITY_ONLY
execution = DISABLED
auto_execute = false
final_holdout = SEALED
```

No H38 successor. No runtime direction promotion. No live trading.

---

# 1. Finding A — overlapping forward-return labels invalidate iid standard errors

H39 emits decision observations every 15 minutes.

Primary outcome horizon is 60 minutes, therefore adjacent outcome intervals overlap:

```text
15m sampling interval
60m label horizon
=> lags 1, 2, 3 share future return intervals
=> observations are serially dependent by construction
```

The current implementation uses ordinary iid OLS covariance:

```text
Cov(beta) = s^2 * (X'X)^-1
```

for feature-effect standard errors, t statistics, p-values and confidence intervals.

This is not acceptable for the formal one-shot H39 inference because overlapping returns can materially understate uncertainty.

The same issue applies to the current fixed L2 logistic incremental coefficient covariance and classical LR chi-square calibration: both assume independent observations unless dependence is explicitly handled.

Because no real H39 validation outcomes have been unblinded yet, repair the inferential method **before any formal outcome inspection**. This is a validity correction, not result-driven retuning.

## 1.1 Pre-label protocol clarification MUST be committed first

Before modifying/running the formal one-shot inference implementation, create and commit a new clarification artifact, e.g.:

```text
deliverables/v0.3.25/H39_PROTOCOL_CLARIFICATION_002_DEPENDENCE_ROBUST_INFERENCE.json
```

Commit this clarification in a dedicated commit BEFORE any code path is permitted to read real post-start validation outcomes.

The clarification must state that:

- M1-M8, predefined signs, horizons, Holm family, alpha and candidate thresholds remain unchanged.
- The correction addresses serial dependence caused mechanically by overlapping labels.
- No validation performance was inspected before selecting the estimator.
- Lag/block choices are deterministic functions of the frozen horizon and 15m decision cadence, not data-tuned.

Pin the clarification SHA/hash into the future freeze manifest, readiness/freeze verification and one-shot result provenance in addition to the existing frozen protocol and clarification 001.

## 1.2 Primary 60m feature-effect inference

For the formal 60m linear effect estimate, retain the same coefficient/effect definition but replace iid OLS uncertainty with a deterministic **HAC / Newey-West covariance estimator**.

Use fixed lag:

```text
primary_horizon = 60m
decision_interval = 15m
HAC max lag = ceil(60/15) - 1 = 3
```

No lag search or sensitivity-driven selection is allowed.

For each M1-M8 report at minimum:

```text
effect_estimate
hac_standard_error
hac_t_or_z_statistic
one_sided_raw_p_value
holm_adjusted_p_value
hac_95pct_ci
hac_max_lag = 3
covariance_method = NEWey_WEST_HAC
```

The formal Holm family must use these dependence-robust primary p-values, not the old iid p-values.

Old iid statistics may be retained only as clearly labeled diagnostics and MUST NOT enter candidate gating.

## 1.3 Incremental baseline inference must also be dependence-robust

Keep the frozen baseline covariates and fixed L2 logistic model:

```text
trailing_return_15m
trailing_return_60m
trailing_atr_ratio_15m
lambda = 1.0
```

Do not change model family or tune regularization.

However, do not use naive inverse-Hessian covariance as the formal coefficient uncertainty under overlapping labels.

Implement a serial-dependence-robust sandwich/HAC covariance for the microstructure coefficient using the same fixed primary lag 3.

The formal signed incremental coefficient statistic must use this robust covariance.

### LR test calibration

The classical iid chi-square calibration of the nested likelihood-ratio statistic must NOT remain the formal inferential gate under overlapping labels.

Preserve the frozen requirement that incremental evidence includes an LR comparison, but calibrate the LR statistic using a deterministic dependence-preserving procedure fixed before labels, preferably one of:

```text
A. moving-block/bootstrap calibration with block length = ceil(60/15) = 4 observations
   and a fixed preregistered seed / fixed replication count;

or

B. an equivalently valid dependence-robust nested-model test with a mathematically documented equivalence/justification.
```

Preferred implementation:

```text
block length = 4 observations
bootstrap replications = 5000
seed = 390325
chronological moving-block resampling
```

Do NOT tune block length, replication count or seed based on observed significance.

If a valid dependence-robust LR calibration cannot be implemented confidently, fail closed and mark the formal H39 one-shot evaluator `STATISTICAL_INFERENCE_NOT_READY`; do not silently fall back to iid LR p-values.

Record both:

```text
incremental_lr_statistic
incremental_lr_p_value_dependence_robust
incremental_coefficient_hac_statistic
incremental_coefficient_hac_p_value
```

The candidate gate must consume only dependence-robust incremental evidence.

## 1.4 Supporting 240m horizon

240m remains supporting only and cannot rescue 60m.

Because 240m outcomes sampled every 15m overlap for up to 16 decision intervals, use deterministic:

```text
HAC max lag = ceil(240/15) - 1 = 15
```

for any reported 240m effect uncertainty.

Do not let 240m p-values affect the primary candidate gate.

## 1.5 Dependence tests

Add direct tests proving:

```text
60m formal inference uses HAC lag 3
240m supporting inference uses HAC lag 15
formal Holm input comes from HAC p-values
naive iid p-values cannot authorize candidate status
incremental coefficient uses robust covariance
classical iid LR p-value cannot authorize candidate status
block/bootstrap parameters are frozen constants
same synthetic data + same seed => deterministic output
positive serial correlation inflates/changes SE versus iid in a constructed regression case
no outcome read occurs while live H39 is immature
```

Do not run these tests on real post-start H39 outcomes; use synthetic fixtures only.

---

# 2. Finding B — Forward health report can falsely report HEALTHY

Current v0.3.25 health generation initializes derivatives health optimistically and only changes it if the DB exists. Therefore a missing derivatives DB can be reported as:

```text
status = HEALTHY
db_integrity = OK
rows_recorded = 0
```

This is a fail-open observability bug.

Microstructure health is also too weak if it treats `partition_count > 0` as sufficient health and reuses blind-ledger integrity as if it represented collector/partition health.

## 2.1 Replace optimistic booleans with evidence-based states

Never initialize a chain to healthy before evidence is verified.

Use explicit states such as:

```text
HEALTHY
STALE
MISSING
EMPTY
SCHEMA_ERROR
INTEGRITY_ERROR
READ_ERROR
DATA_QUALITY_TERMINAL_ARCHIVE
UNKNOWN
```

`HEALTHY` is allowed only after all required checks for that chain pass.

## 2.2 Derivatives chain

For the configured canonical derivatives store:

1. Verify expected path exists.
2. Open read-only.
3. `PRAGMA integrity_check` passes.
4. Required table exists.
5. Required columns exist.
6. Row count > 0.
7. Obtain latest event/observed timestamp when schema supports it.
8. Evaluate freshness against an explicitly configured/frozen threshold appropriate to the collection cadence.

If file is absent:

```text
status = MISSING
exists = false
db_integrity = NOT_CHECKED
rows_recorded = 0
```

Never `HEALTHY`.

If file exists but table/schema is wrong, use `SCHEMA_ERROR` rather than generic healthy/investigate.

The implementation must resolve the actual canonical derivatives path/table from existing project configuration/code; do not hard-code a second inconsistent filename merely to make tests pass.

## 2.3 Microstructure chain

Do not define health as merely `len(partitions) > 0`.

At minimum report separately:

```text
root_exists
partition_count
latest_partition
latest_partition_exists
latest_partition_integrity
latest_partition_schema_valid
latest_event_time_ms or latest_receive_time_ms when available
freshness_seconds
collector_heartbeat_status if there is authoritative heartbeat evidence
```

Only report `HEALTHY` when the latest relevant partition is readable, integrity/schema checks pass, and freshness/heartbeat evidence is acceptable.

Do not claim `daemon_heartbeat = ACTIVE` or equivalent unless an actual heartbeat/process/state source was checked.

Do not use H39 blind-ledger integrity as a substitute for microstructure source-partition integrity.

## 2.4 Opportunity/H38 chain

Preserve H38 exactly as:

```text
DATA_QUALITY_TERMINAL_ARCHIVE
```

Do not accidentally normalize it to HEALTHY/STALE/MISSING.

## 2.5 Aggregate health semantics

Add an aggregate status that is fail-closed and derived from component states, e.g.:

```text
HEALTHY
DEGRADED
BLOCKED
```

Missing/empty/corrupt required evidence must never aggregate to HEALTHY.

Keep operational health separate from scientific H39 readiness. A chain health report must not silently alter the frozen H39 sample gates unless explicitly required by existing authoritative readiness rules.

## 2.6 Health tests

Add tests for at least:

```text
missing derivatives DB => MISSING, never HEALTHY
empty derivatives DB => EMPTY
wrong derivatives schema => SCHEMA_ERROR
corrupt/unreadable DB => INTEGRITY_ERROR or READ_ERROR
valid fresh DB => HEALTHY
stale DB => STALE
missing microstructure root => MISSING
zero microstructure partitions => EMPTY/MISSING, never HEALTHY
latest partition corrupt => INTEGRITY_ERROR
latest partition stale => STALE
blind-ledger integrity cannot masquerade as microstructure health
no heartbeat evidence => UNKNOWN/NOT_VERIFIED, never ACTIVE
H38 remains DATA_QUALITY_TERMINAL_ARCHIVE
aggregate health fails closed
```

---

# 3. Documentation and provenance repair

Update the current v0.3.25 preregistration/report artifacts so they no longer claim iid inference or unsupported health.

The preregistration manifest should explicitly include:

```text
primary_covariance_method = NEWey_WEST_HAC
primary_hac_max_lag = 3
secondary_hac_max_lag = 15
incremental_dependence_robust = true
lr_calibration_method
lr_block_length = 4 (if moving-block bootstrap is used)
```

Forward health deliverables must include evidence fields explaining WHY each chain received its status.

Do not regenerate or create any real H39 performance artifacts.

---

# 4. Scope restrictions

Do NOT:

```text
read Final Holdout
inspect real H39 future returns or labels
run real one-shot unblind
change M1-M8
change predefined signs
change 60m/240m horizons
change sample gates
change Holm alpha/family
add a new alpha family
change runtime direction engine
change execution mode
open live trading
```

This is a pre-unblind validity repair only.

---

# 5. Required repair deliverables

Create at minimum:

```text
deliverables/v0.3.25/H39_PROTOCOL_CLARIFICATION_002_DEPENDENCE_ROBUST_INFERENCE.json

deliverables/v0.3.25/V0.3.25_STATISTICAL_DEPENDENCE_HEALTH_REPAIR.json
deliverables/v0.3.25/V0.3.25_STATISTICAL_DEPENDENCE_HEALTH_REPAIR.md
```

The repair report must include:

```text
exact implementation SHA
clarification commit SHA + file SHA256
proof no real H39 outcome was read
old iid method vs new formal robust method
fixed HAC lags
LR dependence calibration method
health state decision table
current live health evidence without reading large raw datasets
safety invariants
```

---

# 6. Validation

Run:

```text
ruff check .
mypy
pytest -q
pytest --cov=btc_quant_agent --cov-report=term-missing
python -m compileall -q src skill-template/scripts
```

CI must pass Python 3.11 / 3.12 / 3.13 on the exact repair SHA.

Use only synthetic fixtures for formal outcome/statistical regression tests.

---

# 7. Governance / handoff

This repair is prompted by a post-acceptance project-wide audit finding before any legitimate H39 one-shot unblind.

Workflow:

1. Commit `H39_PROTOCOL_CLARIFICATION_002_DEPENDENCE_ROBUST_INFERENCE.json` first, with zero real outcome inspection.
2. Implement the dependence-robust inference and health truthfulness repair.
3. Run tests/CI.
4. Do NOT run real H39 one-shot validation.
5. Do NOT request a second Gemini audit unless explicitly instructed; report the exact repair SHA directly to ChatGPT for final acceptance.

Expected scientific state after repair remains:

```text
H39 = FORWARD_DATA_INSUFFICIENT
```

unless authoritative readiness metadata naturally changes from blind accumulation; regardless, this repair itself must not unblind outcomes.
