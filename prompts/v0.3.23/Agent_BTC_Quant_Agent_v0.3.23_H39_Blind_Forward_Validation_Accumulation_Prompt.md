# BTC Quant Agent v0.3.23 — H39 Blind Forward Validation Accumulation

Repository:

```text
EXASHXE/btc-quant-agent
```

Accepted baseline:

```text
main
f2e3f29dec38f71a2b5d6640d25bc8f2ae8353ba
```

Stage branch:

```text
agent/v0.3.23-h39-blind-forward-validation
```

Before doing anything:

```bash
git fetch --all --prune
git checkout agent/v0.3.23-h39-blind-forward-validation
git status
git rev-parse HEAD
git log -15 --oneline
```

Read first:

```text
docs/PROJECT_CONTEXT_HANDOFF.md
docs/MULTI_MODEL_RESEARCH_GOVERNANCE.md
configs/research/v0.3.22_microstructure_h39_protocol.json
deliverables/v0.3.22/H39_PROTOCOL_FREEZE_MANIFEST.json
deliverables/v0.3.22/H39_PROTOCOL_CLARIFICATION_001.json
deliverables/v0.3.22/H39_VALIDATION_STATUS.json
deliverables/v0.3.22/H38_TERMINAL_RECONCILIATION.json
reviews/v0.3.22/gemini-3.8-flash/REVIEW.md
src/btc_quant_agent/microstructure_research.py
```

This stage is an **evidence-preservation and blind-validation accumulation stage**.

It is NOT a new alpha-search stage.

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

H39 remains exactly:

```text
H39_MICROSTRUCTURE_DIRECTIONAL_INFORMATION
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

Strict prohibitions:

```text
NO new feature
NO feature deletion because it looks weak
NO window change
NO sign flip
NO threshold search
NO new horizon
NO 5m/15m rescue test
NO new model family
NO neural/tree/AutoML search
NO Final Holdout access
NO runtime Direction integration
NO execution enablement
NO H38 resurrection
NO H38 backfill
NO automatic H38 successor in v0.3.23
NO inspection/reporting of fresh-validation alpha results before maturity
```

H38 remains permanently:

```text
OPPORTUNITY_FORWARD_V0321_20260903T180000Z
DATA_QUALITY_TERMINAL_ARCHIVE
terminal_at_ms = 1788511500000
```

Do not create H39/H40-named Opportunity successors. H39 already refers to the microstructure hypothesis family.

---

# 1. Stage objective

Turn the already-frozen H39 fresh validation into a deterministic **blind accumulation pipeline** so that the project can collect evidence for days without repeatedly looking at intermediate performance and contaminating the eventual formal test.

The system should answer only:

```text
Is validation data accumulating correctly?
How many eligible boundaries exist?
How many distinct UTC days exist?
What is the coverage ratio?
Are provenance and capture quality healthy?
Has the frozen maturity gate been reached?
```

Before maturity, it must NOT answer:

```text
Which M1-M8 feature is best?
What is current IC/correlation?
What are current p-values?
What are current coefficient signs/effects?
What is current hit rate by feature?
Would a threshold currently be profitable?
```

---

# 2. Preserve the accepted H39 protocol

Do not modify the scientific meaning of:

```text
configs/research/v0.3.22_microstructure_h39_protocol.json
deliverables/v0.3.22/H39_PROTOCOL_CLARIFICATION_001.json
```

The accepted reference rule remains:

```text
decision_close_ms = closed 15m boundary
reference_time_ms = decision_close_ms + 60_000
reference_price = OPEN at reference_time_ms
```

The accepted baseline remains:

```text
trailing_return_15m
trailing_return_60m
trailing_atr_ratio_15m = ATR14_15m / decision_close_price
```

The accepted incremental model remains fixed L2 logistic regression with no hyperparameter search.

v0.3.23 must not re-estimate/tune any protocol choice.

---

# 3. Blind validation ledger

Create a dedicated research evidence store, separate from raw Forward stores, for example:

```text
data/research/h39_validation/
```

or an equivalently explicit path.

Raw Forward databases remain read-only inputs.

The blind ledger must be append-only/idempotent by validation decision slot.

For each post-start 15m boundary, record only causal feature-side information and provenance needed for the future one-shot validation:

```text
decision_close_ms
slot_utc
M1-M8 values
baseline features
eligibility flag
exclusion/rejection reason
feature_window_start_ms
feature_window_end_ms
source microstructure partition(s)
source partition integrity/hash identity where available
protocol SHA/hash
protocol clarification SHA/hash
feature-code version / producing Git SHA
coverage diagnostics
known gap/resync overlap status
```

It is acceptable to record the predeclared future reference/target timestamps because they are deterministic schedule metadata:

```text
reference_time_ms
60m target timestamp
240m target timestamp
```

Do NOT include fresh-validation return, direction, effect-size or feature-performance fields in the feature ledger.

---

# 4. Real outcome blindness

During v0.3.23 implementation and routine operation, do not run formal H39 association statistics against real post-start validation outcomes.

Allowed before maturity:

```text
feature extraction
eligibility calculation
coverage counting
partition/provenance verification
reference/target timestamp planning
maturity counting
data-health reporting
synthetic/unit-test outcome evaluation
```

Forbidden before maturity:

```text
real validation p-values
real validation Holm results
real validation effect estimates
real validation LR/z statistics
feature ranking
feature hit rates
feature-conditioned PnL/returns
best-feature reporting
regime-specific performance mining
```

If existing tooling can calculate these statistics, add a fail-closed maturity guard for real fresh validation.

Expected behavior before maturity:

```text
formal validation analysis command
-> REFUSED_VALIDATION_NOT_MATURE
```

The command may return only maturity counts and reasons for refusal.

---

# 5. Maturity gate

The frozen gate is unchanged:

```text
>= 14 distinct UTC days after 2026-09-04T11:15:00Z
>= 750 eligible 15m observations
>= 90% eligible-boundary coverage
no terminal microstructure capture-quality breach
```

Do not loosen these thresholds.

Compute coverage denominator from the frozen validation clock, not from rows that happen to exist.

A missing expected boundary remains a missing boundary.

Do not backfill it with synthetic features.

Raw true-Forward evidence that was genuinely captured at the time may be deterministically extracted later from finalized immutable partitions; this does not authorize reconstruction of data that never existed.

---

# 6. Ready-for-unblind state

v0.3.23 itself must NOT automatically unblind H39 when maturity is reached.

When all frozen maturity gates are satisfied, produce only a readiness artifact/state:

```text
H39_READY_FOR_ONE_SHOT_UNBLIND
```

The readiness artifact must include:

```text
validation_start
maturity cutoff
expected boundaries
eligible boundaries
coverage ratio
distinct UTC days
source partition list + immutable identities
protocol SHA/hash
clarification SHA/hash
producing code SHA
zero protocol drift attestation
zero Final Holdout access attestation
zero validation performance inspection attestation
```

Do not include feature outcomes/performance.

Formal H39 hypothesis testing will happen in a separate next stage exactly once.

---

# 7. Operational interface

Provide a deterministic CLI, preferably under `quantctl h39` or equivalent, with clear separation:

```text
validation-accumulate
validation-status
validation-readiness
```

Before maturity, `validation-status` may expose only:

```text
state
validation_start
expected boundary count
observed boundary count
eligible boundary count
coverage ratio
distinct days
capture/provenance health
rejection-reason counts
latest processed slot
maturity booleans
```

It must not expose per-feature outcome statistics.

If there is an existing research command that would expose fresh H39 statistics, make its real-validation path maturity-gated without breaking development diagnostics or synthetic tests.

---

# 8. Scheduling / accumulation

Make accumulation operationally robust and idempotent.

A daily finalized-partition ingestion job is acceptable and preferable to heavy frequent queries against the active SQLite partition.

If systemd automation is added:

```text
- do not interfere with the existing microstructure collector;
- prefer finalized partitions;
- use read-only SQLite;
- use bounded CPU/memory;
- make reruns idempotent;
- do not run formal statistical analysis automatically;
- do not start or revive Opportunity Forward.
```

Do not treat `Persistent=true` as permission to fabricate missed raw evidence.

---

# 9. Evidence integrity

Add deterministic protection against:

```text
duplicate slot with conflicting feature values
protocol hash drift
clarification hash drift
source partition mutation after ingestion
future event entering feature window
late receive_time entering feature window
missing boundary silently disappearing from denominator
rejected slot being converted to eligible on rerun without source/protocol change
```

If an idempotent rerun sees exactly the same evidence, it may no-op.

If the same slot resolves to materially different evidence under the same protocol/source identity, fail closed with an explicit conflict status.

---

# 10. Current Forward chains

Preserve:

```text
DERIVATIVES_PIT_EPOCH_V0321_001
MICROSTRUCTURE_FORWARD_V0315_20260831T190000Z
```

H38 is terminal and stays terminal.

Do not preregister an Opportunity successor in this stage.

Report current derivatives/microstructure health in deliverables, but do not make H39 maturity contingent on unrelated Opportunity availability.

If microstructure itself suffers a frozen terminal data-quality breach, stop blind accumulation from claiming healthy formal coverage and report the real gap.

---

# 11. Tests

Add direct tests for at least:

```text
post-start only validation ledger rows
feature window causality
receive-time causality
reference_time = decision_close + 60s metadata
frozen M1-M8 universe unchanged
frozen baseline unchanged
protocol/clarification hash pinning
raw Forward DB read-only behavior
idempotent duplicate insertion
conflicting duplicate fails closed
missing expected slots remain in coverage denominator
before maturity formal real-validation stats are refused
before maturity status contains no p/effect/ranking fields
maturity requires all 14d/750/90% gates simultaneously
ready state contains no performance results
Final Holdout is never accessed
execution remains disabled
H38 remains terminal and cannot be restarted
```

Use synthetic fixtures for statistical-path tests. Do not inspect real fresh validation performance simply to test the gate.

---

# 12. Required deliverables

Create:

```text
deliverables/v0.3.23/README.md
deliverables/v0.3.23/H39_BLIND_VALIDATION_LEDGER_MANIFEST.json
deliverables/v0.3.23/H39_BLIND_VALIDATION_STATUS.json
deliverables/v0.3.23/H39_BLINDNESS_ATTESTATION.json
deliverables/v0.3.23/FORWARD_CHAIN_HEALTH.json
deliverables/v0.3.23/V0.3.23_H39_BLIND_VALIDATION_REPORT.md
```

If mature during or after deployment, also create/update only:

```text
deliverables/v0.3.23/H39_READY_FOR_ONE_SHOT_UNBLIND.json
```

Before maturity its state should be:

```text
FORWARD_DATA_INSUFFICIENT
```

Do not generate a formal H39 results table in v0.3.23.

---

# 13. Quality gates

Run:

```bash
ruff check .
mypy src
pytest
python -m compileall src tests tools
```

CI must be green across:

```text
Python 3.11
Python 3.12
Python 3.13
```

Record exact CI run IDs tied to the reviewable SHA.

---

# 14. Review workflow

Use the simplified governance workflow:

```text
Implementation Agent completes v0.3.23
        -> exact reviewable SHA
Gemini-3.8-Flash performs ONE post-implementation audit
        -> reviews/v0.3.23/gemini-3.8-flash/REVIEW.md
ChatGPT performs final review
        -> final verdict + next-stage prompt
```

Do NOT perform a Gemini pre-freeze review for v0.3.23.
Do NOT perform a second Gemini reconciliation review.

Allowed review verdicts:

```text
PASS_WITH_NONBLOCKING_FOLLOWUPS
FORWARD_DATA_INSUFFICIENT
REPAIR_REQUIRED
```

Engineering may pass while H39 remains `FORWARD_DATA_INSUFFICIENT`.

---

# 15. Acceptance criteria

v0.3.23 is acceptable when:

```text
blind ledger is deterministic and append-only/idempotent
real fresh H39 performance is maturity-gated
routine status reveals only maturity/data-health information
M1-M8 and baseline protocol are unchanged
validation_start remains 2026-09-04T11:15:00Z
coverage denominator uses expected clock slots
no missing raw evidence is reconstructed
H38 remains terminal
Derivatives/Microstructure are not disrupted
Final Holdout remains sealed
execution remains disabled
all tests and CI pass
```

The expected scientific status at initial completion is likely:

```text
H39 = FORWARD_DATA_INSUFFICIENT
```

That is a valid outcome. Do not accelerate the clock, lower the gate, or inspect interim performance to force progress.
