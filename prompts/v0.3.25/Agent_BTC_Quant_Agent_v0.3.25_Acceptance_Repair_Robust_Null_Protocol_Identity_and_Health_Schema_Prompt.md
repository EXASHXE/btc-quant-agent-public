# BTC Quant Agent v0.3.25 — Acceptance Repair: Valid Robust Null, Mandatory Protocol Identity & Truthful Health Schema

Repository: `EXASHXE/btc-quant-agent`

Current review branch: `agent/v0.3.25-h39-one-shot-unblind-preregistration`

Accepted main baseline before this repair family:

```text
4e22c657c12f9e4a97b3b47bdfb3e8da598cabb2
```

Current reviewed repair implementation:

```text
clarification 002 = 6e1259409aa4f1cedf86b7a424666ee7c942a929
implementation     = 419f28ad1008d2a365e21b3bb648bb4db1be13b1
CI                 = 34053961633 (green)
```

ChatGPT review confirms the first repair successfully moved the formal 60m family from iid OLS uncertainty to Newey-West HAC, uses HAC p-values as Holm inputs, uses HAC/sandwich uncertainty for the incremental coefficient, and made derivatives health fail closed on missing/empty/schema/corrupt/stale stores.

However, three remaining protocol/observability blockers must be repaired **before v0.3.25 can be accepted and before any real H39 unblind**.

This is a narrow pre-label acceptance repair. Do not reopen H39 feature design or research direction.

---

## 0. Frozen invariants

Keep unchanged:

```text
hypothesis = H39_MICROSTRUCTURE_DIRECTIONAL_INFORMATION
validation_start = 2026-09-04T11:15:00Z
formal family = M1-M8 exactly
predefined signs = +1 exactly
primary horizon = 60m
secondary horizon = 240m supporting only
Holm-Bonferroni family alpha = 0.05
minimum distinct UTC days = 14
minimum eligible observations = 750
minimum eligible-boundary coverage = 90%
baseline covariates = trailing_return_15m, trailing_return_60m, trailing_atr_ratio_15m
L2 logistic lambda = 1.0
primary HAC max lag = 3
secondary HAC max lag = 15
strategy = EXPERIMENTAL
qualified_direction_engine = NONE
runtime_maximum = OPPORTUNITY_ONLY
execution = DISABLED
auto_execute = false
final_holdout = SEALED
```

Do not inspect real H39 post-start outcomes. Do not run real one-shot unblind.

---

# 1. BLOCKER A — Clarification 002 LR bootstrap null is not the conditional null being tested

Clarification 002 currently specifies the incremental LR bootstrap as:

```text
hold (X_base, y) fixed
resample overlapping blocks of raw x_micro
fit full model on (X_base, x_micro*)
compare LR* with observed LR
```

This is not sufficiently valid for the intended null:

```text
H0: x_micro has no incremental predictive information for y conditional on X_base
```

because H0 does **not** imply:

```text
x_micro independent of X_base
```

Microstructure features can be materially correlated with trailing returns / ATR while still having zero incremental directional information. Resampling raw `x_micro` independently of `X_base` destroys that contemporaneous dependence and changes the design/collinearity structure under the bootstrap null. The resulting LR null distribution can therefore be miscalibrated.

This was discovered before legitimate one-shot unblinding. Fix it now; do not wait for outcomes.

## 1.1 Commit Clarification 003 BEFORE implementation changes

Create and commit first:

```text
deliverables/v0.3.25/H39_PROTOCOL_CLARIFICATION_003_ROBUST_NESTED_NULL.json
```

The clarification must explicitly state:

- zero real fresh H39 outcomes were inspected;
- Clarification 003 supersedes **only** the invalid nested-LR bootstrap calibration section of Clarification 002;
- HAC lag 3/15, M1-M8, signs, horizons, Holm, alpha, maturity gates, baseline fields and L2 lambda remain unchanged;
- the change is a pre-label inferential-validity correction, not result-driven retuning.

Do not edit Clarification 002 in place. Preserve immutable lineage.

## 1.2 Replace the invalid raw-x bootstrap with a defensible dependence-robust nested test

Preferred solution: implement a **HAC-robust nested score test under the null baseline model**, with nuisance adjustment, rather than inventing another ad-hoc bootstrap.

The formal incremental model remains:

```text
Null: y ~ X_base
Full: y ~ X_base + x_micro
fixed L2 lambda = 1.0
```

A valid implementation should:

1. Fit the frozen null baseline logistic model.
2. Compute the microstructure score under H0.
3. Account for nuisance baseline coefficients rather than treating the micro score as orthogonal by assumption.
4. Estimate the long-run covariance of the adjusted score with deterministic Bartlett/Newey-West lag 3.
5. Produce a one-sided dependence-robust nested-test statistic / p-value for the frozen +1 alternative.
6. Use that p-value as the **formal incremental nested-model gate**.
7. Keep the full-model HAC/sandwich microstructure coefficient statistic as the second formal incremental requirement.

The observed nested LR statistic may still be reported as a descriptive effect-of-fit diagnostic, but its classical iid chi-square p-value and the invalid raw-x moving-block bootstrap p-value MUST NOT authorize a candidate.

If the implementation team chooses a different dependence-robust nested-model calibration, it must provide a mathematical justification showing that the procedure targets the conditional null while preserving/conditioning on the observed relationship between `x_micro` and `X_base`. Do not simply resample raw `x_micro` independently of baseline covariates.

If this cannot be implemented confidently and deterministically, fail closed:

```text
STATISTICAL_INFERENCE_NOT_READY
```

Do not fall back to iid LR or the Clarification-002 raw-x bootstrap.

## 1.3 Formal candidate gate after repair

A primary feature may pass the statistical parts of the candidate gate only if all remain true:

```text
Holm-adjusted primary 60m HAC p < 0.05
HAC 95% CI excludes zero in the predefined positive direction
formal dependence-robust nested incremental p < 0.05
full-model microstructure HAC/sandwich coefficient statistic > 0
all other frozen maturity/stability/integrity requirements pass
```

The old fields should be labeled clearly, for example:

```text
iid_*                         = DIAGNOSTIC_ONLY
clarification_002_bootstrap_* = SUPERSEDED_DIAGNOSTIC_ONLY
formal_nested_method          = <Clarification 003 method>
formal_nested_p_value         = <robust p>
```

No ambiguity about which fields gate candidate status.

## 1.4 Required statistical tests

Use synthetic data only. Add tests proving at least:

```text
formal Holm input is still HAC lag-3 primary p-values
formal incremental nested gate cannot consume iid LR p-value
formal incremental nested gate cannot consume Clarification-002 raw-x bootstrap p-value
nested robust test handles x_micro strongly correlated with X_base under a null of zero incremental effect
nested robust test detects a controlled synthetic incremental effect in the correct direction
same synthetic input => deterministic result
HAC/sandwich coefficient gate remains dependence robust
no real post-start outcome loader is called by these tests
STATISTICAL_INFERENCE_NOT_READY is fail-closed on singular/non-computable robust inference
```

Do not write a test whose only assertion is that a function returns a p-value in [0,1]. Test the actual null/correlation structure and routing into the candidate gate.

---

# 2. BLOCKER B — Clarification 002/003 protocol identity must be mandatory, not optional

Current verification logic accepts the absence of Clarification 002 by returning:

```text
clarification_002_verified = false
```

and freeze-manifest verification only checks the hash if the field happens to be present.

That is not a strict frozen protocol identity. Once a pre-label clarification changes formal inference, the future one-shot path must not be able to execute with an old or manually constructed manifest that omits it.

## Required repair

After Clarification 003 is committed, the authoritative protocol identity for future freeze/unblind must require all of:

```text
protocol freeze
clarification 001
clarification 002
clarification 003
```

Requirements:

1. Missing Clarification 002 or 003 file => fail closed before readiness/freeze/unblind authorization.
2. Hash mismatch => fail closed.
3. Freeze manifest required keys MUST include both clarification hashes/identities.
4. A manifest omitting either field must be rejected as corrupt/incomplete.
5. Freeze manifest, readiness artifact, execution key, result provenance and receipt must bind both clarifications.
6. Do not use optional `manifest.get(..., "")` semantics for protocol identity.
7. Old pre-clarification freeze manifests are invalid for future formal unblind. There is currently no legitimate live freeze, so no migration exception is needed.

Add direct tests:

```text
missing clarification 002 => refused
missing clarification 003 => refused
hash drift 002 => refused
hash drift 003 => refused
freeze manifest omitting 002 => refused
freeze manifest omitting 003 => refused
execution key changes when any clarification identity changes
no label/candle loader call occurs before these checks pass
```

---

# 3. BLOCKER C — Microstructure health can still label an unusable schema HEALTHY

Current repaired health checks that the latest partition contains table names:

```text
agg_trades
book_samples
```

but does not verify the required columns used by H39. The current synthetic HEALTHY test even constructs tables containing only `event_time_ms`.

The actual collector/research schema requires materially more fields. Resolve them from the canonical collector implementation (`src/btc_quant_agent/microstructure.py`) rather than duplicating an invented schema.

At minimum health must verify the fields needed by H39 feature/eligibility reads, including the canonical equivalents of:

```text
agg_trades:
  event_time_ms
  receive_time_ms
  price
  quantity
  aggressive_side

book_samples:
  event_time_ms
  receive_time_ms
  spread_bps
  top1_imbalance
  top5_imbalance
  top20_imbalance
  microprice
  ofi

gaps:
  start_ms
  end_ms
```

If authoritative source code requires additional keys/tables for the relevant health claim, derive them from that schema.

A partition with only table names but missing required columns must be:

```text
SCHEMA_ERROR
```

never HEALTHY.

## 3.1 Freshness should prefer local receive-time evidence

For microstructure operational freshness, prefer local `receive_time_ms` where available instead of relying only on exchange `event_time_ms`.

Report both when useful:

```text
latest_event_time_ms
latest_receive_time_ms
freshness_basis = LOCAL_RECEIVE_TIME | EXCHANGE_EVENT_TIME_FALLBACK
```

This avoids silently treating exchange clock skew as collector freshness.

## 3.2 Future timestamp / clock anomaly must not become HEALTHY

Current logic uses roughly:

```text
freshness = max(0, now - latest_timestamp)
```

which can turn a future timestamp into `0s fresh` and therefore HEALTHY.

Add a fixed, documented future-skew tolerance appropriate to the collector clock policy. If the relevant timestamp is beyond `now + tolerance`, use an explicit fail-closed/degraded state such as:

```text
TIMESTAMP_ERROR
```

or

```text
CLOCK_SKEW
```

and never HEALTHY.

Do the same for derivatives `observed_at_ms` if a future local timestamp exceeds the frozen tolerance.

No tolerance tuning based on current data.

## 3.3 Heartbeat truthfulness

Continue to report:

```text
collector_heartbeat_status = NOT_VERIFIED
```

when no authoritative heartbeat is checked.

Fresh valid data may be used as evidence that the data stream is current, but do not rename that evidence to an ACTIVE heartbeat.

If you elect to verify an actual heartbeat, use an existing authoritative source such as canonical process-instance/heartbeat state; do not infer it from file existence.

## 3.4 Health tests

Add direct tests for:

```text
microstructure tables exist but required columns missing => SCHEMA_ERROR
missing gaps table when eligibility requires it => SCHEMA_ERROR
valid full canonical schema + fresh receive time => HEALTHY
future receive timestamp beyond tolerance => TIMESTAMP_ERROR/CLOCK_SKEW, never HEALTHY
future derivatives observed_at beyond tolerance => TIMESTAMP_ERROR/CLOCK_SKEW, never HEALTHY
exchange event timestamp slightly skewed but valid local receive timestamp => freshness uses receive timestamp
latest partition integrity failure => INTEGRITY_ERROR
aggregate health cannot be HEALTHY when either active chain is schema/timestamp invalid
```

Update the previous minimal-schema `HEALTHY` fixtures to use the real canonical schema. Do not weaken production checks to preserve old tests.

---

# 4. Preserve already-correct parts of 419f28ad

Do not regress these accepted repair elements:

```text
primary 60m Newey-West HAC lag = 3
supporting 240m HAC lag = 15
Holm input = primary HAC raw p-values
full-model incremental coefficient covariance = HAC/sandwich
missing derivatives DB => MISSING
empty derivatives DB => EMPTY
wrong derivatives schema => SCHEMA_ERROR
corrupt derivatives DB => INTEGRITY_ERROR/READ_ERROR
stale derivatives => STALE
missing microstructure root/partition => non-HEALTHY
H38 => DATA_QUALITY_TERMINAL_ARCHIVE
aggregate health fail-closed
committed freeze boundary
WAL-safe frozen snapshot
exactly-once execution registry
wall-clock maturity denominator
```

Do not perform unrelated refactors.

---

# 5. Live-state safety

During this repair, H39 remains blind.

Required attestations:

```text
real_one_shot_executed = false
real_validation_labels_loaded = false
real_validation_performance_artifacts_created = false
final_holdout_accessed = false
```

The current live H39 state should remain `FORWARD_DATA_INSUFFICIENT` unless ordinary blind accumulation changes only maturity metadata. Even if readiness naturally becomes true during development, DO NOT execute the real one-shot as part of this repair.

---

# 6. Deliverables

Create at minimum:

```text
deliverables/v0.3.25/H39_PROTOCOL_CLARIFICATION_003_ROBUST_NESTED_NULL.json

deliverables/v0.3.25/V0.3.25_ROBUST_NULL_PROTOCOL_IDENTITY_HEALTH_SCHEMA_REPAIR.json
deliverables/v0.3.25/V0.3.25_ROBUST_NULL_PROTOCOL_IDENTITY_HEALTH_SCHEMA_REPAIR.md
```

The repair report must state:

```text
Clarification 003 exact commit SHA + file SHA256
exact implementation SHA
why raw-x bootstrap did not represent conditional H0
new formal nested robust method and equations/justification
which statistics are formal vs diagnostic-only
mandatory protocol identity chain 0.3.22 freeze + clarifications 001/002/003
canonical microstructure schema checks
freshness timestamp basis and future-skew policy
current live health metadata only (no large raw-data analysis)
proof zero real H39 outcome inspection
safety invariants
```

---

# 7. CI

Require exact implementation SHA green on Python 3.11 / 3.12 / 3.13:

```text
ruff check .
mypy
pytest -q
pytest --cov=btc_quant_agent --cov-report=term-missing
python -m compileall -q src skill-template/scripts
```

Use synthetic fixtures only for inferential tests.

---

# 8. Governance / handoff

Workflow is strictly:

1. Commit Clarification 003 alone first.
2. Implement this narrow acceptance repair on top of it.
3. Run CI.
4. Do not run real one-shot validation.
5. No second Gemini audit is required.
6. Report to ChatGPT:

```text
clarification_003_commit_sha
clarification_003_file_sha256
exact_implementation_sha
CI_run_id
```

ChatGPT will perform final acceptance.

Expected engineering verdict after a correct repair: `PASS_WITH_NONBLOCKING_FOLLOWUPS`.
Expected scientific state: still `FORWARD_DATA_INSUFFICIENT` until the frozen maturity gates are naturally satisfied.