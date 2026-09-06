# BTC Quant Agent v0.3.24 — H39 Blind Accumulation Operations & Readiness

Repository:

```text
EXASHXE/btc-quant-agent
```

Accepted baseline:

```text
main
5f4a716f566abb7750e41fdd03d08a68526c1921
```

Stage branch:

```text
agent/v0.3.24-h39-blind-accumulation-operations
```

This is an operational evidence-preservation stage. It is NOT an alpha-search stage and it is NOT an H39 unblind stage.

The v0.3.23 blind-validation implementation is accepted. v0.3.24 exists only to make blind accumulation durable, automatic, auditable, low-interference, and readiness-only while H39 naturally approaches its frozen maturity gates.

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
hypothesis = H39_MICROSTRUCTURE_DIRECTIONAL_INFORMATION
validation_start = 2026-09-04T11:15:00Z
primary_horizon = 60m
secondary_horizon = 240m supporting only
formal feature universe = M1-M8 exactly
predefined signs = frozen
Holm-Bonferroni FWER alpha = 0.05
minimum distinct UTC days = 14
minimum eligible observations = 750
minimum eligible-boundary coverage = 90%
```

Accepted protocol lineage must remain pinned:

```text
H39_PROTOCOL_FREEZE_SHA = 0eecd8833675c664c42f5e62d89663d7a10ed5fa
H39_PROTOCOL_CLARIFICATION_SHA = 2d1ccecc11dc231ffa41cdb1b5a9ea693abccc59
v0.3.23 strict-unblind repair SHA = 5f4a716f566abb7750e41fdd03d08a68526c1921
```

H38 remains permanently terminal:

```text
OPPORTUNITY_FORWARD_V0321_20260903T180000Z
DATA_QUALITY_TERMINAL_ARCHIVE
terminal_at_ms = 1788511500000
```

Strict prohibitions:

```text
NO H39 outcome unblind
NO real post-start p-values
NO real post-start feature ranking
NO real post-start effect estimates
NO real post-start LR/z statistics
NO allow_unblind / force-unblind / validation-unblind path
NO new M9+ feature
NO feature deletion because it looks weak
NO sign flip
NO window change
NO horizon change
NO threshold tuning
NO new model family
NO Opportunity successor
NO H38 resurrection
NO synthetic reconstruction of missing L2/aggTrade
NO Final Holdout access
NO runtime LONG/SHORT integration
NO execution enablement
```

`evaluate_feature_hypotheses` must remain unconditionally fail-closed for any observation with `slot_ms >= H39_VALIDATION_START_MS` throughout v0.3.24.

---

# 1. Stage objective

Operationalize the accepted v0.3.23 blind ledger so that H39 evidence accumulates automatically from genuine Forward data without repeated manual commands and without exposing predictive outcomes.

The system should continuously preserve only:

```text
expected boundary count
observed boundary count
eligible boundary count
coverage ratio
distinct UTC days
rejection reason counts
source partition identities
protocol / clarification hashes
code producer SHA
collector health
ledger integrity
maturity booleans
```

The only scientific state transitions allowed in this stage are:

```text
FORWARD_DATA_INSUFFICIENT
H39_READY_FOR_ONE_SHOT_UNBLIND
DATA_QUALITY_TERMINAL / READINESS_BLOCKED if the frozen microstructure evidence chain becomes invalid
```

No H39 formal statistic may be computed automatically when readiness is reached.

---

# 2. Re-audit current live state before changes

Before editing, run and record:

```bash
git fetch --all --prune
git checkout agent/v0.3.24-h39-blind-accumulation-operations
git rev-parse HEAD
quantctl forward-evidence doctor
quantctl forward-evidence health
quantctl h39 validation-status
quantctl h39 validation-readiness
```

Also inspect:

```text
configs/research/v0.3.22_microstructure_h39_protocol.json
deliverables/v0.3.22/H39_PROTOCOL_CLARIFICATION_001.json
deliverables/v0.3.23/H39_BLINDNESS_ATTESTATION.json
deliverables/v0.3.23/H39_BLIND_VALIDATION_LEDGER_MANIFEST.json
deliverables/v0.3.23/H39_BLIND_VALIDATION_STATUS.json
deliverables/v0.3.23/V0.3.23_STRICT_UNBLIND_GATE_REPAIR.json
src/btc_quant_agent/microstructure_research.py
src/btc_quant_agent/cli.py
tools/run_h39_blind_validation.py
```

The latest reviewed v0.3.23 repository snapshot showed only 2 distinct days, 24 eligible slots, and 17.78% coverage. Treat that as historical evidence only. Recompute the current maturity/coverage state from existing true Forward evidence without examining outcomes.

---

# 3. Durable blind accumulation scheduler

Add a production-quality local scheduler for blind evidence accumulation.

Preferred implementation on the current Linux/WSL host:

```text
systemd service + timer
```

Recommended behavior:

```text
- run once per finalized UTC day, or another low-frequency cadence that avoids active-partition contention;
- ingest only true Forward evidence already captured by the microstructure collector;
- prefer finalized immutable partitions;
- if the current active partition is needed only for status, query it briefly/read-only;
- never run formal validation statistics;
- reruns are idempotent;
- missing raw events remain missing;
- the timer must not restart or manage the microstructure collector itself;
- the job must use bounded CPU/memory and a runtime timeout;
- failure of this research ingestion job must not kill the Forward collector.
```

Use an explicit unit name such as:

```text
btc-quant-h39-blind-accumulate.service
btc-quant-h39-blind-accumulate.timer
```

or an equivalently unambiguous name.

Do not modify accepted collector campaign semantics merely to support the research scheduler.

---

# 4. Finalized-partition ingestion semantics

Blind accumulation may process an old validation slot later ONLY when all feature-side evidence for that slot was genuinely observed and stored at the time in immutable Forward partitions.

This is allowed:

```text
slot occurred at T
true L2 / aggTrade evidence was stored causally at T
finalized partition becomes available later
blind ledger extracts the frozen features later
```

This is forbidden:

```text
raw L2 / aggTrade evidence was never captured
later candles / API snapshots / interpolation are used to manufacture the missing microstructure state
```

For every ingested slot, preserve source partition path + stable identity/hash. If a previously ingested source partition changes unexpectedly, fail closed and report `SOURCE_PARTITION_MUTATION` rather than silently rewriting ledger evidence.

---

# 5. Coverage semantics

Coverage denominator stays clock-based from the frozen validation start:

```text
2026-09-04T11:15:00Z
```

Expected boundaries must not be derived from existing rows.

Report separately:

```text
expected_boundary_count
observed_boundary_count
eligible_boundary_count
raw_observation_coverage = observed / expected
eligible_coverage = eligible / expected
```

The frozen formal maturity gate remains:

```text
eligible_boundary_count / expected_boundary_count >= 0.90
```

If the implementation historically used a single `coverage_ratio`, preserve compatibility but explicitly define which numerator it uses and add the second diagnostic ratio where useful. Do not change the frozen qualification criterion through nomenclature.

A rejected observed slot remains an observed but ineligible slot.

---

# 6. Readiness-only state machine

Implement a clear state machine that never computes outcomes:

```text
FORWARD_DATA_INSUFFICIENT
    -> keep accumulating

H39_READY_FOR_ONE_SHOT_UNBLIND
    -> stop at readiness metadata only
    -> do NOT call formal hypothesis evaluation

READINESS_BLOCKED_DATA_QUALITY
    -> if immutable evidence/provenance/capture quality violates a frozen gate
```

`H39_READY_FOR_ONE_SHOT_UNBLIND` requires all of:

```text
>= 14 distinct UTC validation days
>= 750 eligible slots
>= 90% eligible-boundary coverage
no terminal microstructure capture-quality breach
protocol hash pinned
clarification hash pinned
zero source mutation conflict
zero Final Holdout access
zero interim outcome inspection
```

When ready, write an immutable readiness artifact containing metadata only. Do not expose any feature-specific performance.

---

# 7. Readiness artifact

When maturity is reached, emit:

```text
deliverables/v0.3.24/H39_ONE_SHOT_UNBLIND_READINESS.json
```

with at least:

```text
state = H39_READY_FOR_ONE_SHOT_UNBLIND
validation_start
readiness_as_of
maturity_cutoff
expected_boundary_count
observed_boundary_count
eligible_boundary_count
eligible_coverage
distinct_utc_days
source partition identities/hashes
ledger hash / immutable identity
protocol freeze SHA + hash
clarification SHA + hash
producing code SHA
zero protocol drift attestation
zero outcome inspection attestation
zero Final Holdout access attestation
execution disabled attestation
```

If not ready, do not fabricate this success artifact. Emit only the ordinary blind-status deliverable with `FORWARD_DATA_INSUFFICIENT`.

---

# 8. Ledger durability and recovery

Protect the research ledger itself:

```text
- WAL or another safe SQLite journaling mode;
- append-only/idempotent slot semantics;
- deterministic duplicate conflict detection;
- integrity check in the scheduled job;
- no delete/update of accepted historical slot rows except a formally versioned migration that preserves original evidence;
- atomic manifest/status writes;
- explicit failure status when disk space is low or the ledger becomes unreadable.
```

Add a lightweight backup/snapshot mechanism for the blind ledger and machine-readable manifests. This backup is for operational recovery only; it must never be used to change scientific evidence.

Do not copy raw multi-GB microstructure partitions into Git.

---

# 9. Disk and process safety

The microstructure dataset grows continuously and is more important than the derived blind ledger.

Add operational checks for:

```text
free disk space
ledger DB integrity
latest microstructure heartbeat
latest finalized partition
scheduled ingestion last-success timestamp
scheduled ingestion last-error
```

Use warning/error thresholds that fail the research accumulation conservatively without deleting raw data automatically.

No automatic raw Forward-data deletion in this stage.

---

# 10. No hidden unblind paths

Add repository-wide tests/static checks proving there is no user-facing or library bypass such as:

```text
allow_unblind
force_unblind
--allow-unblind
--force-unblind
validation-unblind
validation-evaluate
AUTO_UNBLIND
H39_UNBLIND_TOKEN
```

If a string appears only in historical documentation/review explaining the removed vulnerability, that is acceptable; executable code must contain no bypass.

Directly test that:

```python
evaluate_feature_hypotheses(post_start_real_or_synthetic_obs)
```

always raises `REFUSED_VALIDATION_NOT_MATURE` in v0.3.24 regardless of whether external readiness metadata says mature.

The future one-shot unblind stage must implement its own separately reviewed execution path rather than re-enabling a flag here.

---

# 11. Required deliverables

Create/update:

```text
deliverables/v0.3.24/README.md
deliverables/v0.3.24/H39_BLIND_OPERATIONAL_STATUS.json
deliverables/v0.3.24/H39_BLIND_LEDGER_INTEGRITY.json
deliverables/v0.3.24/H39_ACCUMULATION_SCHEDULER_REPORT.json
deliverables/v0.3.24/FORWARD_CHAIN_HEALTH.json
deliverables/v0.3.24/V0.3.24_H39_BLIND_ACCUMULATION_OPERATIONS_REPORT.md
```

Conditionally create only when the frozen gates are actually satisfied:

```text
deliverables/v0.3.24/H39_ONE_SHOT_UNBLIND_READINESS.json
```

Do not include p-values, feature effects, rankings, hit rates, returns, or feature-conditioned PnL in any v0.3.24 deliverable.

---

# 12. Required tests

Add tests covering at minimum:

```text
scheduler invokes accumulation only, never formal statistics
scheduler rerun is idempotent
active Forward DBs are read-only inputs
finalized historical true evidence can be ingested later
missing raw evidence cannot be synthesized
expected-boundary clock denominator includes missing slots
observed rejected slot remains ineligible
source partition mutation fails closed
protocol/clarification hash drift fails closed
ledger conflict fails closed
readiness state has metadata only
readiness does not execute evaluate_feature_hypotheses
post-start evaluate_feature_hypotheses always refuses
no executable allow/force-unblind path exists
H38 remains terminal
no Opportunity successor is created
Final Holdout is untouched
execution remains disabled
```

---

# 13. Quality gates

Run:

```bash
ruff check .
mypy src
pytest
python -m compileall src tests tools
```

GitHub Actions must be green across:

```text
Python 3.11
Python 3.12
Python 3.13
```

Report exact reviewable SHA and CI run ID(s).

---

# 14. Review workflow

Use the simplified workflow:

```text
1. Implementation Agent implements v0.3.24 and stops at an exact SHA.
2. Gemini-3.8-Flash performs ONE independent post-implementation audit.
3. Gemini writes reviews/v0.3.24/gemini-3.8-flash/REVIEW.md and optional REVIEW.json.
4. ChatGPT performs final acceptance and owns the next prompt.
5. No second Gemini reconciliation pass.
```

Gemini should specifically challenge:

```text
- outcome-blindness bypasses;
- scheduler accidentally executing statistics;
- source-partition mutation handling;
- coverage denominator correctness;
- readiness state correctness;
- disk/ledger operational durability;
- safety invariants.
```

---

# 15. Allowed final verdicts

Use one of:

```text
PASS_WITH_NONBLOCKING_FOLLOWUPS
FORWARD_DATA_INSUFFICIENT
REPAIR_REQUIRED
READINESS_BLOCKED_DATA_QUALITY
H39_READY_FOR_ONE_SHOT_UNBLIND
```

Engineering acceptance does not require H39 maturity.

If the system is correct but maturity is not reached, the expected scientific state remains:

```text
FORWARD_DATA_INSUFFICIENT
```

Do not start formal H39 hypothesis testing in v0.3.24.