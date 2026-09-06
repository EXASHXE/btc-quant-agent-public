# BTC Quant Agent v0.3.25 — H39 One-Shot Unblind Preregistration

Repository:

```text
EXASHXE/btc-quant-agent
```

Accepted baseline:

```text
main
e99964a3ced0c40424a4ace6dd59cc2376a2dea6
```

Stage branch:

```text
agent/v0.3.25-h39-one-shot-unblind-preregistration
```

This stage is a **pre-registration and gatekeeper stage** for the future one-shot H39 fresh-forward unblind.

It is NOT permission to run H39 formal validation now.

The implementation agent must fail closed and stop without computing any validation performance unless the accepted v0.3.24 authoritative readiness path returns exactly:

```text
H39_READY_FOR_ONE_SHOT_UNBLIND
ready_for_unblind = true
```

using current wall-clock coverage semantics and successful integrity verification.

---

## 0. Frozen safety invariants

Keep unchanged:

```text
strategy = EXPERIMENTAL
qualified_direction_engine = NONE
runtime_maximum = OPPORTUNITY_ONLY
execution = DISABLED
auto_execute = false
live trading = NOT AUTHORIZED
final_holdout = SEALED
```

H38 remains permanently:

```text
OPPORTUNITY_FORWARD_V0321_20260903T180000Z
DATA_QUALITY_TERMINAL_ARCHIVE
terminal_at_ms = 1788511500000
```

Do not create or revive any H38 successor.

---

# 1. Scientific protocol remains frozen

Do not modify:

```text
configs/research/v0.3.22_microstructure_h39_protocol.json
deliverables/v0.3.22/H39_PROTOCOL_CLARIFICATION_001.json
```

Keep exactly:

```text
hypothesis = H39_MICROSTRUCTURE_DIRECTIONAL_INFORMATION
validation_start = 2026-09-04T11:15:00Z
primary horizon = 60m
secondary horizon = 240m supporting only
formal feature universe = M1-M8 exactly
predefined signs = frozen
Holm-Bonferroni FWER alpha = 0.05
minimum distinct UTC days = 14
minimum eligible observations = 750
minimum eligible-boundary coverage = 90%
```

No new feature, no feature deletion, no sign change, no window change, no threshold search, no model-family search, no hyperparameter search, no 5m/15m rescue horizon, no post-hoc inversion.

---

# 2. Authoritative readiness source

The ONLY authorization source for future unblind is the accepted v0.3.24 blind-ledger readiness path:

```text
H39ResearchEngine.check_unblind_readiness(...)
```

which must use:

```text
H39BlindLedger.get_summary(...)
```

with default production denominator:

```text
clock_ceiling = current UTC wall clock
```

or explicit `as_of_ms` only for deterministic audit/replay.

Legacy or historical diagnostic methods such as:

```text
evaluate_validation_status()
```

MUST NOT authorize unblind, candidate promotion, or formal H39 validation. If retained, label/deprecate them explicitly as non-authoritative diagnostics and ensure no CLI, scheduler, readiness artifact, or formal validation path consumes their maturity result.

---

# 3. Precondition: fail closed before maturity

Before any real fresh-validation label is loaded, joined, correlated, ranked, summarized, or passed to statistical code:

1. Verify blind ledger SQLite integrity.
2. Verify all finalized source partition hashes.
3. Verify protocol hash and clarification hash.
4. Compute readiness using wall-clock denominator.
5. Require all frozen gates:

```text
>= 14 distinct UTC days
>= 750 eligible observations
>= 90% eligible coverage
no terminal microstructure capture-quality breach
zero source mutation
zero protocol drift
zero Final Holdout access
zero prior validation performance inspection
```

If any gate fails, emit only:

```text
FORWARD_DATA_INSUFFICIENT
```

or:

```text
READINESS_BLOCKED_DATA_QUALITY
```

and stop.

Before readiness, the code must not read or materialize fresh-validation outcome fields.

---

# 4. Immutable one-shot cutoff

When readiness is first legitimately achieved, freeze a one-shot validation cutoff BEFORE reading labels.

Create an immutable machine-readable artifact, for example:

```text
deliverables/v0.3.25/H39_ONE_SHOT_UNBLIND_FREEZE.json
```

It must include:

```text
validation_start_ms
unblind_cutoff_ms
unblind_cutoff_utc
clock_source
expected_boundary_count
observed_boundary_count
eligible_boundary_count
eligible_coverage
distinct_days_count
ledger SHA-256
source partition names + SHA-256
protocol SHA/hash
clarification SHA/hash
exact producing Git SHA
readiness artifact/hash
zero protocol drift attestation
zero prior performance inspection attestation
zero Final Holdout access attestation
```

The cutoff is immutable after the freeze commit.

No rows after `unblind_cutoff_ms` may enter the one-shot test.

---

# 5. Exact one-shot outcome construction

Only after the freeze artifact is committed may the one-shot process construct real validation outcomes.

Keep frozen timing semantics:

```text
decision_close_ms = closed 15m boundary
reference_time_ms = decision_close_ms + 60_000
reference_price = OPEN at reference_time_ms
primary 60m target = reference_time_ms + 59*60_000
secondary 240m target = reference_time_ms + 239*60_000
```

Do not substitute a different entry candle or endpoint.

Only use rows:

```text
validation_start_ms <= decision_close_ms <= unblind_cutoff_ms
eligible = true
```

No backfilled synthetic L2/OFI/depth evidence.

---

# 6. Formal hypothesis universe

Test exactly M1-M8 and no more.

For each feature, use the frozen predefined direction/sign.

Primary family:

```text
8 one-sided H39 hypotheses at 60m
```

Apply complete Holm-Bonferroni FWER correction over all 8 formal hypotheses.

Report for every M1-M8 arm regardless of result:

```text
n
raw p-value
Holm adjusted p-value
effect estimate
95% CI
predefined sign
observed sign
sign correctness
primary gate pass/fail
```

No dropping a weak arm after seeing results.

The 240m horizon is supporting evidence only and cannot rescue failure of the 60m family.

---

# 7. Frozen baseline incremental test

Use the accepted baseline exactly:

```text
trailing_return_15m
trailing_return_60m
trailing_atr_ratio_15m = ATR14_15m / decision_close_price
```

Use the already accepted fixed low-capacity L2 logistic formulation with no hyperparameter search.

For each formal feature, report incremental evidence beyond baseline using the accepted LR/z diagnostics.

Do not refit a more favorable model family if incremental evidence is weak.

---

# 8. Stability checks

Without changing the primary familywise test, report prespecified stability diagnostics across:

```text
UTC day
week / rolling block
volatility regime
1H regime
```

These are diagnostics only.

Do not mine subgroups to rescue an otherwise failed primary result.

Flag:

```text
single-day dependence
single-regime dependence
material sign inversion by major regime
```

---

# 9. Candidate decision rule

A formal feature may receive only:

```text
PROVISIONAL_MICROSTRUCTURE_CANDIDATE
```

if ALL are true on the fresh one-shot validation:

```text
Holm-adjusted p < 0.05 on primary 60m family
observed effect follows predefined sign
95% CI is on the correct side of zero
nontrivial effect size
incremental evidence beyond frozen baseline
>=14 days
>=750 eligible observations
>=90% eligible coverage
no source/integrity breach
no single-day dependence
no material regime inversion
```

Even if this gate passes:

```text
qualified_direction_engine = NONE
runtime_maximum = OPPORTUNITY_ONLY
execution = DISABLED
auto_execute = false
```

No runtime promotion occurs in v0.3.25.

---

# 10. Allowed scientific verdicts

Use one of:

```text
FORWARD_DATA_INSUFFICIENT
READINESS_BLOCKED_DATA_QUALITY
RESEARCH_FAMILY_STOP
REJECT_CANDIDATE
PASS_WITH_NONBLOCKING_FOLLOWUPS
```

If no M1-M8 feature passes the frozen primary gate after the legitimate one-shot unblind:

```text
H39 = RESEARCH_FAMILY_STOP
```

Do not expand M1-M8, change signs, add search budget, add neural proposal engines, or reopen the family to rescue it.

If one or more pass, record only provisional research candidate status and defer any independent replication/runtime qualification to a future stage.

---

# 11. One-shot execution semantics

The formal unblind must be auditable as a single bounded execution.

Create a command such as:

```text
quantctl h39 one-shot-unblind --freeze-manifest <path>
```

but it must fail closed unless the manifest proves readiness and its hashes match current immutable evidence.

The command must:

1. verify freeze manifest;
2. verify readiness and hashes;
3. load labels only after verification;
4. execute the fixed formal analysis exactly once for that cutoff;
5. write immutable result artifacts;
6. never execute trading actions.

Do not add `--force`, `--ignore-readiness`, `--override`, or equivalent bypasses.

---

# 12. Required result artifacts

When NOT ready, create no performance artifacts. Only readiness refusal metadata is allowed.

When legitimately ready and one-shot unblind is executed, create at minimum:

```text
deliverables/v0.3.25/H39_ONE_SHOT_UNBLIND_FREEZE.json
deliverables/v0.3.25/H39_ONE_SHOT_VALIDATION_RESULTS.json
deliverables/v0.3.25/H39_ONE_SHOT_VALIDATION_REPORT.md
deliverables/v0.3.25/H39_FAMILYWISE_HOLM_RESULTS.json
deliverables/v0.3.25/H39_BASELINE_INCREMENTAL_RESULTS.json
deliverables/v0.3.25/H39_STABILITY_DIAGNOSTICS.json
deliverables/v0.3.25/H39_FINAL_SCIENTIFIC_VERDICT.json
```

Every artifact must identify the exact implementation SHA and frozen evidence identities.

---

# 13. Tests

Add direct tests for at least:

```text
unblind refuses before 14 days
unblind refuses before 750 eligible observations
unblind refuses below 90% wall-clock eligible coverage
stale ledger cannot authorize unblind
source partition mutation blocks unblind
protocol hash drift blocks unblind
clarification hash drift blocks unblind
legacy evaluate_validation_status cannot authorize unblind
freeze cutoff excludes later rows
reference timestamp = decision close + 60s
60m and 240m target timestamps exact
formal universe exactly M1-M8
Holm correction includes all 8 arms
predefined signs cannot be flipped
240m cannot rescue 60m failure
baseline fields are exactly frozen trio
no hyperparameter/model search
no Final Holdout access
no runtime direction integration
execution remains disabled
no force/override unblind path
```

Add a deliberate leakage/bypass test that must fail closed.

---

# 14. CI and quality

Require:

```text
ruff check .
mypy
pytest -q
pytest --cov=btc_quant_agent --cov-report=term-missing
python -m compileall -q src skill-template/scripts
```

GitHub Actions must be green for Python 3.11 / 3.12 / 3.13 on the exact reviewed SHA.

---

# 15. Governance

Gemini already completed the v0.3.24 single audit at:

```text
ed02feced4f946093934a026fa5fb7eb34811151
```

ChatGPT accepted the v0.3.24 repair at:

```text
e99964a3ced0c40424a4ace6dd59cc2376a2dea6
```

For v0.3.25:

1. Implementation agent may implement the gatekeeper/preregistration machinery now.
2. It MUST NOT execute real one-shot validation until authoritative readiness is achieved.
3. When implementation is complete, report exact SHA.
4. Gemini performs one independent post-implementation audit.
5. ChatGPT performs final review.
6. If readiness is still false, engineering may pass while scientific state remains `FORWARD_DATA_INSUFFICIENT`; do not execute formal H39 validation.
7. Once readiness later becomes true, the actual one-shot execution must use the already frozen v0.3.25 procedure and immutable cutoff manifest; do not redesign the analysis after seeing results.

---

# 16. Current expected state

At stage creation, H39 is expected to remain:

```text
FORWARD_DATA_INSUFFICIENT
```

The implementation agent must treat that as normal and must not manufacture or expose performance results.

The purpose of v0.3.25 is to pre-register the final unblind machinery before the evidence matures, not to accelerate or bypass maturity.
