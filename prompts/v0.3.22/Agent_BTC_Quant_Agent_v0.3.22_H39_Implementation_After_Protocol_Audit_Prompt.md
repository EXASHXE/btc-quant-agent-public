# BTC Quant Agent v0.3.22 — H39 Implementation After Protocol Audit

Repository:

```text
EXASHXE/btc-quant-agent
```

Stage branch:

```text
agent/v0.3.22-microstructure-alpha-foundation
```

Accepted baseline:

```text
main
497842b07c8048fac4ed9b68827156ce6f51fee2
```

Original v0.3.22 protocol prompt:

```text
prompts/v0.3.22/Agent_BTC_Quant_Agent_v0.3.22_Microstructure_Causal_Alpha_Foundation_Prompt.md
```

Original protocol prompt commit:

```text
8da42f27c73dd5381381d7af0466c4149b344440
```

Gemini protocol audit:

```text
reviews/v0.3.22/gemini-3.8-flash/PROTOCOL_REVIEW.md
reviews/v0.3.22/gemini-3.8-flash/PROTOCOL_REVIEW.json
```

Gemini protocol-audit commit:

```text
3641fbff67a75762d1757e86f4f565289bb88bf3
```

Gemini verdict:

```text
PRE_FREEZE_VERDICT = ACCEPT_PROTOCOL
```

This prompt does NOT replace the original H39 hypothesis/protocol. It is the authoritative implementation addendum after the independent protocol audit. Where this addendum conflicts with the original prompt only on implementation/review workflow, this addendum wins. All research definitions, safety invariants, hypothesis-family limits, temporal split rules, candidate gates and prohibitions from the original v0.3.22 prompt remain frozen.

---

## 0. Workflow correction for this stage

The project governance has been simplified by user decision to one Gemini audit per stage.

For v0.3.22 specifically, Gemini has already used that one audit on the pre-freeze protocol at commit `3641fbff...`.

Therefore:

```text
NO second Gemini post-implementation audit for v0.3.22
NO reconciliation round
NO second Gemini review artifact required
```

After implementation reaches an exact reviewable SHA:

```text
Implementation Agent stops editing
        -> ChatGPT directly reviews exact implementation SHA + Gemini protocol audit
        -> ChatGPT issues final stage verdict
        -> ChatGPT owns the next-stage prompt
```

Do not create a second `reviews/v0.3.22/gemini-3.8-flash/REVIEW.md` merely to satisfy the older Section 19 of the original prompt. For this stage only, the existing `PROTOCOL_REVIEW.md` is the sole Gemini audit artifact.

---

## 1. Frozen safety invariants

Remain unchanged:

```text
strategy = EXPERIMENTAL
qualified_direction_engine = NONE
runtime_maximum = OPPORTUNITY_ONLY
execution = DISABLED
auto_execute = false
live trading = NOT AUTHORIZED
final_holdout = SEALED
```

Strict prohibitions remain:

```text
NO live/paper/testnet execution
NO Final Holdout access
NO runtime LONG/SHORT integration
NO reopening stopped official-derivatives symbolic family
NO neural proposal engine
NO symbolic-expression factory
NO post-hoc sign inversion
NO hidden feature/window search
NO threshold rescue after results are visible
NO synthetic historical L2/OFI/depth
NO reconstruction/backfill of missing Forward intervals
NO destructive writes to raw Forward evidence
```

---

## 2. Mandatory implementation ordering

Before any label, future return, IC, correlation, regression, classification, p-value or effect-size inspection:

1. Audit the stored microstructure schema needed by M1-M8.
2. Resolve M6 support status using only schema/field semantics, not labels.
3. Create:

```text
configs/research/v0.3.22_microstructure_h39_protocol.json
```

4. Freeze all supported feature definitions, signs, windows, normalization, eligibility rules, baseline model, statistical tests, multiple-testing universe, development cutoff and future validation-start rule.
5. Commit that protocol JSON in a dedicated commit.
6. Record that exact commit as:

```text
H39_PROTOCOL_FREEZE_SHA
```

Only after that commit exists may any outcome-bearing analysis run.

The lineage must therefore be visibly:

```text
497842b... accepted main
 -> 8da42f... original H39 protocol prompt
 -> 3641fbf... Gemini ACCEPT_PROTOCOL audit
 -> this implementation addendum
 -> H39_PROTOCOL_FREEZE_SHA
 -> implementation/tests
 -> development diagnostics
 -> fresh Forward validation accumulation/status
 -> exact reviewable implementation SHA
 -> ChatGPT final review
```

Do not squash away the protocol-freeze boundary before review.

---

## 3. Guardrail G1 — strict protocol freeze before labels

Gemini explicitly required a two-step evidence ordering. Implement it literally.

Before `H39_PROTOCOL_FREEZE_SHA`:

Permitted:

```text
schema inspection
column/type inspection
partition inventory
checksums/manifests
row counts
coverage metadata
capture timestamps/provenance
feature computability checks without outcomes
M6 support determination
```

Forbidden:

```text
future_return inspection
direction labels
feature/label correlation
IC
regression coefficients
classification accuracy
p-values
candidate ranking
feature sign changes based on outcomes
window comparison based on outcomes
```

Add an audit manifest proving the ordering.

---

## 4. Guardrail G2 — SQLite must be read-only and collector-safe

The research pipeline must never interfere with the active Forward collector.

For microstructure SQLite inputs:

Preferred connection contract:

```python
sqlite3.connect(f"file:{path}?mode=ro", uri=True)
```

or equivalently enforce:

```sql
PRAGMA query_only = ON;
```

Requirements:

```text
no INSERT/UPDATE/DELETE
no VACUUM
no schema migration
no WAL checkpoint forcing
no long-lived write transaction
no research table creation in Forward DB
```

Prefer finalized immutable partitions for heavy analysis.

If active partition metadata is inspected, use short bounded read-only queries.

Before and after heavy jobs record collector heartbeat/health and verify no collection degradation was caused by research.

Add direct tests proving the loader refuses/does not perform writes.

---

## 5. Guardrail G3 — M6 support must be decided before protocol freeze

Original M6:

```text
MICROPRICE_DEVIATION_1M
```

requires an unambiguous causal mid price.

Before `H39_PROTOCOL_FREEZE_SHA`, audit whether stored evidence contains enough causal information to derive:

```text
mid = (best_bid + best_ask) / 2
```

or an exactly equivalent already-stored causal mid source.

Do NOT infer mid from future candles or approximate it from fields whose semantics are insufficient.

Valid outcomes are only:

### M6_SUPPORTED

Freeze exact derivation, source fields, timestamp semantics and formula in protocol JSON.

### M6_UNSUPPORTED

Remove M6 from the formal hypothesis family BEFORE protocol freeze and reduce the Holm family denominator accordingly.

If M6 is removed, M7/M8 definitions must be frozen using only the remaining supported primitive components. Do not substitute a new primitive for M6.

Formal primitive universe therefore becomes exactly either:

```text
8 supported features
```

or, if M6 cannot be causally reconstructed:

```text
7 supported features
```

No replacement ninth idea is permitted.

---

## 6. Guardrail G4 — 60m is a deliberate high-hurdle falsification

Primary horizon remains exactly:

```text
60m
```

Secondary horizon remains:

```text
240m supporting only
```

The mechanistic expectation may be that microstructure alpha decays faster than 60m. That is NOT permission to change the test after results are visible.

If H39 fails at 60m:

```text
DO NOT post-hoc move to 5m/10m/15m/30m
DO NOT claim the family succeeded because a shorter exploratory horizon looks good
DO NOT increase the feature universe
DO NOT invert signs
```

The valid outcome is the frozen H39 result:

```text
RESEARCH_FAMILY_STOP
```

or, if fresh validation has not matured:

```text
FORWARD_DATA_INSUFFICIENT
```

A future short-horizon microstructure hypothesis would require a NEW separately preregistered research family/version, not an H39 repair.

---

## 7. Protocol JSON must freeze the complete testing universe

At minimum encode:

```text
hypothesis_id = H39_MICROSTRUCTURE_DIRECTIONAL_INFORMATION
protocol_version
protocol_freeze_sha placeholder/manifest linkage
development_microstructure_cutoff
H39 validation-start rule
formal feature IDs
feature formulas
feature windows
predefined sign of every feature
M6 support status and reason
M7/M8 exact formulas
normalization rules
eligibility/rejection reason codes
reference-entry semantics
primary horizon = 60m
secondary horizon = 240m
baseline/context specification
statistical test specification
Holm-Bonferroni FWER alpha = 0.05
complete formal family size
minimum development sample/day gates
minimum fresh validation sample/day/coverage gates
candidate gate
stop rules
holdout prohibition
execution prohibition
```

No hidden grids or alternative windows outside this JSON may influence formal H39 inference.

---

## 8. Fixed causal feature pipeline

Implement the original M1-M8 definitions exactly, subject only to pre-freeze M6 support determination.

All feature windows must satisfy:

```text
feature_event_time <= decision_timestamp
feature_receive_time <= decision_timestamp where receive-time availability matters
```

Any event strictly after the decision boundary must be excluded even if it belongs to a delayed/late-arriving source row.

A known gap/resync/invalid-sequence interval overlapping the required feature window makes the observation ineligible.

Do not impute directional values into missing windows.

Add deliberate adversarial tests that inject future events and prove they cannot enter feature calculations.

---

## 9. Outcome and baseline rules

Keep the original causal outcome definition:

```text
decision = closed UTC 15m boundary
reference = OPEN of first fully available 1m bar strictly after decision close
primary future horizon = 60m
secondary = 240m only
```

ATR/excursion context must use ATR known at decision time.

Incremental-information analysis must compare microstructure against the preregistered low-complexity price/context baseline.

Do not optimize the baseline after seeing H39 results.

No neural model, tree ensemble, AutoML or hyperparameter search.

---

## 10. Development versus fresh validation

Development data:

```text
latest fully finalized immutable microstructure partition finalized before H39_PROTOCOL_FREEZE_SHA
```

Fresh validation start:

```text
first fully closed UTC 15m boundary
at least 30 minutes after H39_PROTOCOL_FREEZE_SHA
```

Commit the exact validation boundary before it occurs.

Development diagnostics are exploratory only.

Formal candidate qualification requires fresh post-freeze validation and all original gates:

```text
>= 14 distinct UTC days
>= 750 eligible samples
>= 90% eligible-boundary coverage
no terminal capture-quality breach
Holm-adjusted primary p < 0.05
predefined sign correct
95% CI excludes zero in correct direction
incremental value beyond baseline
no single-day dependence
no obvious regime inversion
```

If the wall-clock validation window is not mature at implementation completion, report:

```text
FORWARD_DATA_INSUFFICIENT
```

This is an expected valid outcome and does not block engineering acceptance.

---

## 11. Required deliverables

Produce at minimum:

```text
deliverables/v0.3.22/README.md
deliverables/v0.3.22/MICROSTRUCTURE_DATA_PROVENANCE.json
deliverables/v0.3.22/H39_PROTOCOL_FREEZE_MANIFEST.json
deliverables/v0.3.22/H39_FEATURE_DICTIONARY.json
deliverables/v0.3.22/H39_DEVELOPMENT_DIAGNOSTICS.json
deliverables/v0.3.22/H39_VALIDATION_STATUS.json
deliverables/v0.3.22/V0.3.22_MICROSTRUCTURE_ALPHA_REPORT.md
```

Additionally include protocol-audit compliance explicitly in the report:

```text
G1 protocol-before-label compliance
G2 read-only SQLite compliance
G3 M6 support determination
G4 no horizon rescue compliance
```

Every result must distinguish:

```text
DEVELOPMENT_EXPLORATORY
FRESH_FORWARD_VALIDATION
FORWARD_DATA_INSUFFICIENT
PROVISIONAL_MICROSTRUCTURE_CANDIDATE
RESEARCH_FAMILY_STOP
```

Do not blur these states.

---

## 12. Required tests / CI

At minimum test:

```text
read-only SQLite research loading
no research writes to Forward stores
feature windows never cross decision boundary
receive/event timestamps not conflated
known gap/resync window invalidation
aggTrade aggressive BUY/SELL sign convention
OFI sign convention
M6 deterministic support/unsupported behavior
M7/M8 deterministic formulas
formal family size exactly matches supported frozen universe
Holm correction covers complete family
next-1m reference strictly after decision close
development/fresh-validation separation
validation boundary committed before occurrence
no Final Holdout access
execution remains disabled
```

Also run:

```bash
ruff check .
mypy src
pytest
python -m compileall src tests tools
```

and GitHub Actions across Python 3.11/3.12/3.13.

---

## 13. Final review handoff

When implementation is complete:

1. Stop editing the implementation branch.
2. Report exact implementation SHA.
3. Report `H39_PROTOCOL_FREEZE_SHA` separately.
4. Report CI run IDs/status.
5. Ensure all deliverables are committed.
6. Do NOT ask Gemini for another review in v0.3.22.
7. Hand the exact SHA directly to ChatGPT for the final review.

ChatGPT will verify:

```text
protocol ordering
causality/leakage
formal family completeness
statistics/multiple testing
Forward validation maturity
collector non-interference
safety invariants
CI
```

Final stage verdict will be one of:

```text
PASS_WITH_NONBLOCKING_FOLLOWUPS
FORWARD_DATA_INSUFFICIENT
RESEARCH_FAMILY_STOP
REPAIR_REQUIRED
REJECT_CANDIDATE
```

No runtime direction engine or execution authorization can be granted in v0.3.22.
