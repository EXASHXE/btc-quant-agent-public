# BTC Quant Agent v0.3.23 — Acceptance Repair: Strict One-Shot Unblind Gate

Repository:

```text
EXASHXE/btc-quant-agent
```

Stage branch:

```text
agent/v0.3.23-h39-blind-forward-validation
```

Accepted main baseline before v0.3.23:

```text
f2e3f29dec38f71a2b5d6640d25bc8f2ae8353ba
```

Gemini-reviewed v0.3.23 implementation SHA:

```text
3141be7761ee4492550173b80043b42b0b7194e6
```

Latest Gemini review/report commit present on branch:

```text
7afcd2739d4c8f982c9e96ad7dae65125cf2b084
```

ChatGPT final-review verdict before this repair:

```text
REPAIR_REQUIRED
```

This is a narrow acceptance repair. Do not start v0.3.24, do not run H39 formal validation statistics, and do not change any scientific protocol choice.

---

## 0. Frozen invariants

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

Keep H39 unchanged:

```text
hypothesis = H39_MICROSTRUCTURE_DIRECTIONAL_INFORMATION
validation_start = 2026-09-04T11:15:00Z
primary_horizon = 60m
secondary_horizon = 240m supporting only
formal feature universe = M1-M8 exactly
predefined signs = frozen
Holm-Bonferroni FWER alpha = 0.05
minimum validation days = 14 distinct UTC days
minimum eligible observations = 750
minimum eligible-boundary coverage = 90%
```

Keep H38 permanently terminal:

```text
OPPORTUNITY_FORWARD_V0321_20260903T180000Z
DATA_QUALITY_TERMINAL_ARCHIVE
terminal_at_ms = 1788511500000
```

Strict prohibitions:

```text
NO real post-start H39 outcome inspection
NO p-values/effect sizes/rankings/hit rates from fresh validation
NO new feature/window/sign/horizon/model
NO validation-start movement
NO threshold changes
NO synthetic backfill of missing raw evidence
NO H38 resurrection or successor
NO Final Holdout access
NO runtime Direction integration
NO execution enablement
NO second Gemini audit required for this repair
```

---

# 1. Blocking finding to repair

The current implementation contains this API shape:

```python
evaluate_feature_hypotheses(
    observations,
    horizon="60m",
    allow_unblind=False,
)
```

and the guard behaves approximately as:

```python
if has_post_start and not allow_unblind:
    raise RuntimeError(REFUSED_VALIDATION_NOT_MATURE)
```

Therefore:

```python
allow_unblind=True
```

can bypass the maturity refusal for real post-start H39 validation observations even when the frozen maturity gates are not satisfied.

This violates the v0.3.23 contract:

```text
v0.3.23 itself must NOT unblind H39.
Formal H39 hypothesis testing occurs in a separate future stage exactly once.
```

The fact that the current CLI does not expose `allow_unblind` is not sufficient. The library-level formal evaluator must also be fail-closed.

This finding is HIGH because premature unblinding would irreversibly contaminate the fresh validation set.

---

# 2. Required repair — remove the premature-unblind bypass

Preferred repair:

1. Remove `allow_unblind` from `evaluate_feature_hypotheses` entirely.
2. For any observation set containing real H39 post-start validation rows:

```text
slot_ms >= H39_VALIDATION_START_MS
```

`evaluate_feature_hypotheses` must always raise:

```text
REFUSED_VALIDATION_NOT_MATURE
```

inside v0.3.23.

3. Development/pre-start evaluation must continue to work normally.
4. Synthetic statistical unit tests must not require a real post-start bypass. Use one of:
   - synthetic observations with timestamps before `H39_VALIDATION_START_MS`, or
   - a clearly separate private/test-only synthetic evaluator that cannot accept real Forward validation evidence.

Do NOT introduce another boolean, environment variable, hidden CLI switch, magic token, config flag, or debug path that can expose real post-start validation outcomes in v0.3.23.

Do NOT add the future one-shot unblind implementation now.

The future unblind stage should be a separate version/stage after `H39_READY_FOR_ONE_SHOT_UNBLIND` exists.

---

# 3. Readiness remains metadata-only

Preserve:

```text
quantctl h39 validation-accumulate
quantctl h39 validation-status
quantctl h39 validation-readiness
```

Before maturity, these commands may expose only:

```text
state
validation_start
expected boundary count
observed boundary count
eligible boundary count
coverage ratio
distinct UTC days
capture/provenance health
rejection-reason counts
latest processed slot
maturity booleans
```

When all frozen maturity gates are eventually satisfied, `validation-readiness` may return only:

```text
H39_READY_FOR_ONE_SHOT_UNBLIND
```

plus provenance/maturity metadata.

It still must NOT execute formal statistics or reveal any outcome/performance value in v0.3.23.

---

# 4. Preserve blind-ledger semantics

Do not alter the accepted ledger's scientific contents:

```text
M1-M8
baseline covariates
eligibility/rejection reason
causal timestamps
source partition identities
protocol/clarification hashes
code provenance
```

Continue to prohibit storage of:

```text
future_return_60m
future_return_240m
future_direction
p-values
effect estimates
feature ranking
feature-conditioned PnL/hit rate
```

Existing rows must not be deleted or rewritten merely because this repair changes the evaluator guard.

If scientific feature extraction has not changed, do not mark existing blind rows as invalid solely due to the guard-only repair commit.

---

# 5. Coverage and historical extraction rule

Current audited snapshot was approximately:

```text
expected boundaries = 135
observed boundaries = 42
eligible boundaries = 24
coverage = 17.78%
distinct UTC days = 2
state = FORWARD_DATA_INSUFFICIENT
```

This low interim coverage is NOT itself an engineering acceptance failure.

Continue using the frozen clock denominator.

Permitted:

```text
Deterministically extract a past validation boundary later IF the true raw Forward microstructure evidence was genuinely captured at that time and remains available in finalized immutable partitions.
```

Forbidden:

```text
synthetic reconstruction of raw L2/aggTrade evidence that never existed
inventing data across true capture gaps
removing missing boundaries from the denominator
```

Do not inspect outcomes while filling the blind ledger.

---

# 6. Required regression tests

Add or modify tests proving all of the following:

### A. No real post-start bypass exists

A real/synthetic-shaped `H39Observation` whose slot is:

```text
>= H39_VALIDATION_START_MS
```

must always raise `REFUSED_VALIDATION_NOT_MATURE` through the production formal evaluator.

There must be no supported call equivalent to:

```python
allow_unblind=True
```

that changes this result.

### B. Old bypass is impossible

If the parameter is removed, add a regression test demonstrating that the old invocation cannot be used as an authorization path.

### C. Development inference still works

Pre-validation/development observations remain analyzable using the frozen H39 statistical implementation.

### D. Readiness cannot trigger statistics

Both immature and mature-simulated readiness paths must expose only readiness/maturity metadata and must not call the formal evaluator.

### E. CLI has no unblind control

Parser/CLI tests must prove no public option/subcommand such as the following exists in v0.3.23:

```text
--allow-unblind
--force-unblind
validation-unblind
validation-evaluate
```

### F. Existing blind guarantees remain green

Retain tests for:

```text
protocol/clarification hash pinning
post-start-only ledger rows
raw Forward read-only behavior
feature/event/receive-time causality
idempotent duplicate ingestion
conflicting duplicate refusal
missing expected boundaries in denominator
H38 terminal permanence
Final Holdout sealed
execution disabled
```

---

# 7. Deliverable update

Add:

```text
deliverables/v0.3.23/V0.3.23_STRICT_UNBLIND_GATE_REPAIR.json
deliverables/v0.3.23/V0.3.23_STRICT_UNBLIND_GATE_REPAIR.md
```

At minimum report:

```text
finding_id
pre_repair_review_sha
repair_sha
old bypass shape
new fail-closed behavior
regression tests
current blind maturity counts only
zero fresh outcome inspection attestation
zero protocol drift attestation
zero Final Holdout access attestation
```

Do not put fresh H39 predictive results into these deliverables.

---

# 8. Quality gates

Run:

```bash
ruff check .
mypy src
pytest
python -m compileall -q src tests tools
```

Require GitHub Actions CI green on Python:

```text
3.11
3.12
3.13
```

Report exact repair SHA and CI run IDs.

---

# 9. Acceptance criteria

This repair passes only if all are true:

```text
1. No library/API/CLI path in v0.3.23 can unblind real post-start H39 outcomes.
2. evaluate_feature_hypotheses always refuses post-start real validation rows.
3. Development/pre-start evaluation still functions.
4. Blind ledger remains outcome-free.
5. Readiness remains metadata-only.
6. M1-M8 / baseline / horizons / validation start / maturity gates unchanged.
7. H38 remains permanently terminal.
8. Final Holdout remains SEALED.
9. Execution remains DISABLED.
10. Full tests and CI are green.
```

Expected final scientific state remains one of:

```text
FORWARD_DATA_INSUFFICIENT
```

or, only after natural maturity:

```text
H39_READY_FOR_ONE_SHOT_UNBLIND
```

Neither state authorizes formal H39 result inspection inside v0.3.23.

---

# 10. Review workflow after repair

Do NOT request another Gemini review for this repair.

After implementation:

1. Stop editing.
2. Push exact repair SHA.
3. Report CI run IDs.
4. ChatGPT performs final acceptance review directly.

Do not create v0.3.24 until ChatGPT accepts v0.3.23.
