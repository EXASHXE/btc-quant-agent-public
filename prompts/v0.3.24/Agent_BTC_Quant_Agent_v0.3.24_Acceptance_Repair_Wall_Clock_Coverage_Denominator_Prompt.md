# BTC Quant Agent v0.3.24 — Acceptance Repair: Wall-Clock Coverage Denominator

Repository:

```text
EXASHXE/btc-quant-agent
```

Stage branch:

```text
agent/v0.3.24-h39-blind-accumulation-operations
```

Accepted main baseline before v0.3.24:

```text
5f4a716f566abb7750e41fdd03d08a68526c1921
```

Gemini-reviewed v0.3.24 implementation SHA:

```text
bc898c5b1d22c328e5a0a16e0340fc528161fc3a
```

Gemini review artifact commit present on branch:

```text
ed02feced4f946093934a026fa5fb7eb34811151
```

ChatGPT final-review verdict before this repair:

```text
REPAIR_REQUIRED
```

This is a narrow acceptance repair. Do not start a new research family, do not unblind H39, and do not modify any frozen scientific protocol choice.

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

Keep H38 permanently terminal.

Strict prohibitions:

```text
NO H39 unblind
NO outcome statistics
NO new features/windows/signs/horizons/models
NO Final Holdout access
NO synthetic/backfilled L2 or aggTrade evidence
NO H38 resurrection/successor
NO execution enablement
NO weakening 14d / 750 / 90% gates
```

---

# 1. Blocking finding

The v0.3.24 implementation claims a clock-based coverage denominator, but the default code path currently does this in `H39BlindLedger.get_summary()`:

```python
effective_cutoff = as_of_ms if as_of_ms is not None else now_ms
clock_ceiling_ms = effective_cutoff if effective_cutoff is not None else latest_slot_ms
```

Therefore when callers omit `as_of_ms` / `now_ms`, the denominator stops at the latest ledger row rather than the current wall clock.

This affects normal production paths including:

```text
check_unblind_readiness()
run_scheduled_accumulation() -> check_unblind_readiness()
validation-status with no --as-of-ms
validation-readiness with no --as-of-ms
normal deliverable generation unless it explicitly supplies a current cutoff
```

This violates the frozen v0.3.24 requirement:

```text
Coverage denominator stays clock-based from validation_start = 2026-09-04T11:15:00Z.
Expected boundaries must not be derived from existing rows.
A missing expected boundary remains missing.
```

Failure mode:

```text
collector/ingestion stops
latest ledger slot stops advancing
wall clock continues advancing
current implementation denominator also stops advancing
new missing boundaries disappear from denominator
stale ledger can retain/inflate apparent coverage and may become or remain READY incorrectly
```

This is a HIGH acceptance blocker.

---

# 2. Required denominator semantics

Production default must use actual current UTC wall clock.

Canonical rule:

```text
clock_ceiling_ms = explicit as_of_ms when supplied
otherwise = current UTC wall-clock time
```

Never default to:

```text
latest ledger slot
latest observed partition timestamp
latest collector heartbeat
latest ingested boundary
```

Expected boundaries remain:

```text
if clock_ceiling_ms < validation_start_ms:
    expected_boundary_count = 0
else:
    expected_boundary_count = floor((clock_ceiling_ms - validation_start_ms) / 900000) + 1
```

Preserve:

```text
raw_observation_coverage = observed_boundary_count / expected_boundary_count
eligible_coverage = eligible_boundary_count / expected_boundary_count
coverage_ratio = eligible_coverage
```

The 90% maturity gate must use `eligible_coverage` against the wall-clock denominator.

---

# 3. Deterministic audit/test override

Keep an explicit deterministic cutoff for tests and historical audits.

Preferred public API shape:

```python
get_summary(as_of_ms: int | None = None)
```

where:

```text
as_of_ms is not None -> use exactly as_of_ms
as_of_ms is None     -> use current UTC wall clock
```

If an internal `now_ms` injection is retained for tests, it must be unambiguously test/internal plumbing and production default still must resolve to real current UTC time.

Add output metadata:

```text
clock_ceiling_ms
clock_ceiling_utc
clock_source = WALL_CLOCK | EXPLICIT_AS_OF
```

This makes denominator provenance auditable.

---

# 4. Readiness must use the same wall-clock denominator

Fix all normal readiness paths so they cannot freeze the denominator at the newest ledger row.

Specifically verify:

```text
H39ResearchEngine.check_unblind_readiness()
H39ResearchEngine.get_blind_validation_status()
H39ResearchEngine.run_scheduled_accumulation()
quantctl h39 validation-status
quantctl h39 validation-readiness
quantctl h39 scheduled-accumulate
v0.3.24 deliverable generation
```

When no explicit audit cutoff is provided, all must reflect current wall-clock expected boundaries.

`H39_READY_FOR_ONE_SHOT_UNBLIND` remains metadata-only and requires the real current-clock gates.

No path in this repair may call `evaluate_feature_hypotheses` on post-start validation data.

---

# 5. Stale-ledger fail-closed scenario

Add a direct regression scenario proving the original bug is impossible.

Example:

```text
validation start = T0
ledger contains many rows only through T1
coverage through T1 would be >= 90%
current wall clock = T2, materially later than T1
many boundaries T1..T2 are missing
```

Required result:

```text
expected_boundary_count includes T1..T2
coverage falls accordingly
ready_for_unblind = false unless all frozen gates still pass using T2
```

It must be impossible for readiness to remain true merely because ingestion stopped and the denominator froze.

---

# 6. Tests

Add/update direct tests for at least:

```text
A. explicit as_of_ms produces deterministic denominator
B. default production path uses wall clock, not latest ledger slot
C. empty/stale ledger still accumulates expected boundaries as wall clock advances
D. stale ledger cannot remain READY because latest slot froze
E. get_blind_validation_status default uses wall clock
F. check_unblind_readiness default uses wall clock
G. scheduled accumulation readiness uses wall clock
H. CLI --as-of-ms remains deterministic for audit/status
I. no regression in dual coverage semantics
J. no unblind bypass/statistical execution reintroduced
K. source mutation, backup, finalized-only scheduler and disk-safety tests remain green
```

For tests, freeze/patch time or pass an explicit injected current time. Do not make tests depend on the real current date.

The previous test pattern:

```python
summary = ledger.get_summary()
assert raw_observation_coverage == observed / boundaries_through_latest_row
```

must be removed or changed. Default `get_summary()` must no longer infer the denominator from the latest row.

---

# 7. Deliverables

Update/add:

```text
deliverables/v0.3.24/V0.3.24_WALL_CLOCK_DENOMINATOR_REPAIR.json
deliverables/v0.3.24/V0.3.24_WALL_CLOCK_DENOMINATOR_REPAIR.md
deliverables/v0.3.24/H39_BLIND_OPERATIONAL_STATUS.json
deliverables/v0.3.24/H39_BLIND_LEDGER_INTEGRITY.json
deliverables/v0.3.24/H39_ACCUMULATION_SCHEDULER_REPORT.json
```

The operational status must expose:

```text
clock_ceiling_ms
clock_ceiling_utc
clock_source
expected_boundary_count
observed_boundary_count
eligible_boundary_count
raw_observation_coverage
eligible_coverage
```

Do not include any H39 performance statistic.

---

# 8. Acceptance commands

Run at minimum:

```bash
pytest -q
ruff check .
mypy src
python -m compileall -q src tests tools
```

CI must be green on Python 3.11 / 3.12 / 3.13.

Also run deterministic targeted tests demonstrating the stale-ledger denominator behavior.

---

# 9. Required report

Return exact:

```text
repair implementation SHA
CI run ID / status
full test counts
changed files
wall-clock denominator evidence
stale-ledger regression evidence
current blind maturity counts only
protocol/clarification hashes unchanged
H38 terminal unchanged
execution disabled
Final Holdout sealed
zero H39 outcome inspection
```

Do NOT report any p-value, effect, coefficient, ranking, hit rate, feature performance, return, or PnL from fresh H39 validation.

---

# 10. Review governance

Gemini has already completed the single v0.3.24 independent audit.

After this repair:

```text
NO second Gemini review is required.
```

ChatGPT performs direct final acceptance on the exact repair SHA.

Allowed final stage decisions:

```text
PASS
PASS_WITH_NONBLOCKING_FOLLOWUPS
REPAIR_REQUIRED
FORWARD_DATA_INSUFFICIENT
```

The scientific state may remain `FORWARD_DATA_INSUFFICIENT`; that does not block engineering acceptance if the operational pipeline is correct.
