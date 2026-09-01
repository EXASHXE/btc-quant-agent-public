# BTC Quant Agent v0.3.17 — Opportunity Successor Campaign & Forward Evidence Stabilization

## 0. Role and objective

You are the implementation owner for `EXASHXE/btc-quant-agent`.

v0.3.17 is a **forward-evidence stabilization round**, not an Alpha research round and not an execution round.

Primary goals:

1. Preserve the compromised v0.3.13 H35 campaign exactly as historical evidence with `H35_DATA_QUALITY_AT_RISK`.
2. Pre-register and start a clean successor Opportunity Forward campaign using the exact same frozen TP/BR Opportunity semantics, but with an explicit data-quality gate.
3. Verify the v0.3.16 Derivatives successor epoch after its scheduled start without moving/resetting its start.
4. Continue the v0.3.15 Microstructure campaign unchanged and add only reliability/coverage reporting needed for long-run accumulation.
5. End the current sequence of infrastructure versions after this round unless a new operational defect is discovered. The next **strategy research** version should be triggered by evidence eligibility, not by version cadence.

Do not test OFI, depth imbalance, microprice, aggressive flow, OI, basis, taker ratio, long/short ratio, or any other feature against future returns in v0.3.17.

---

## 1. Repository / lineage

Repository:

```text
EXASHXE/btc-quant-agent
```

Formal/published v0.3.16 delivery result SHA:

```text
8ed774f294d272537377d5361adbd448627d6fd6
```

The v0.3.16 branch may contain documentation-only prompt commits after the formal result. Always start from the **latest remote HEAD** of:

```text
codex/v0.3.16-forward-evidence-recovery-microstructure-reliability
```

A v0.3.17 branch may already exist. Ensure it is fast-forwarded/rebased to the latest v0.3.16 remote HEAD before implementation:

```text
codex/v0.3.17-opportunity-successor-forward-stabilization
```

Before changing code, report:

```bash
git status
git branch --show-current
git fetch --all --prune
git log -8 --oneline
git rev-parse HEAD
gh auth status
```

Do not merge to `main` automatically.

---

## 2. Frozen safety state

Must remain:

```text
strategy = EXPERIMENTAL
qualified_direction_engine = NONE
runtime_maximum = OPPORTUNITY_ONLY
execution = DISABLED
auto_execute = false
candidate_freeze = NONE
final_holdout = SEALED
```

No LONG/SHORT authorization, Entry/SL/TP/size generation, paper/testnet/live execution, or Final Holdout access.

---

## 3. Frozen prior evidence

### 3.1 v0.3.14 Derivatives epoch

`DERIVATIVES_PIT_EPOCH_V0314_001` is permanently:

```text
FAILED_GAP_GATE_TERMINAL
```

Never recover, reset, delete, or reinterpret it.

### 3.2 v0.3.16 Derivatives successor

Operative successor:

```text
DERIVATIVES_PIT_EPOCH_V0316_002
start = 2026-09-01T09:30:00Z
```

Frozen gates remain:

```text
minimum_days = 30
minimum_fully_available_snapshots = 2500
minimum_required_field_availability = 0.95
maximum_consecutive_failed_or_missing_slots = 4
manual/legacy/backfill do not count
```

Do not move the start because of observed quality.

### 3.3 v0.3.13 Opportunity/H35

Preserve campaign:

```text
OPPORTUNITY_FORWARD_V0313_20260831T050656Z
```

Its 28 immutable misses remain in place. v0.3.16 classified:

```text
H35_DATA_QUALITY_AT_RISK
```

Do not delete, backfill, relabel, or use it as validated evidence.

### 3.4 v0.3.15 Microstructure

Preserve:

```text
MICROSTRUCTURE_FORWARD_V0315_20260831T190000Z
```

It remains `FUTURE_RESEARCH_DATA`, no Alpha claim.

---

# 4. P0 — Pre-register a clean Opportunity successor campaign

Create and commit the successor campaign config **before activation** and before any successor observation is accepted.

Suggested ID format:

```text
OPPORTUNITY_FORWARD_V0317_<UTC_START>
```

Select a fixed future fully closed 15m boundary with sufficient deployment lead time. Record:

- freeze commit SHA;
- fixed start UTC/ms;
- immutable campaign ID;
- source v0.3.13 campaign ID;
- exact registry/config/feature/strategy identities;
- start rule;
- no-backfill rule.

The successor MUST use the exact same frozen Opportunity definition:

```text
trend_pullback_opportunity
breakout_retest_opportunity
```

No detector threshold changes, no TP/BR side/direction resurrection, no feature reconstruction.

Frozen movement labels remain:

```text
4h
8h
future_range_atr
max_up_excursion_atr
max_down_excursion_atr
max_abs_excursion_atr
```

Reference and ATR rules remain identical to the old campaign.

Control matching remains identical unless there is a demonstrated implementation bug; any correctness fix must be isolated, justified, and must not use outcomes.

---

# 5. P0 — Add an explicit Opportunity data-quality gate

The old campaign lacked a sufficiently strict scan-coverage gate. The successor must pre-register data-quality requirements before activation.

Freeze:

```text
minimum_calendar_days = 30
minimum_resolved_opportunities = 30
preferred_resolved_opportunities = 50
minimum_unique_matched_controls = 100
minimum_distinct_utc_days = 20
minimum_successful_scheduled_scan_ratio = 0.95
maximum_consecutive_missed_decision_slots = 4
```

A scheduled slot is successful only if:

```text
RUNTIME_GATED scan completed
market_data_health == OK
valid closed decision bar exists
observation was durably stored for the frozen slot
```

Missed slot categories must be explicit, e.g.:

```text
NETWORK_HTTP_451
NETWORK_TLS
NETWORK_TIMEOUT
MARKET_DATA_INSUFFICIENT
RUNTIME_CONTRACT
PROCESS_OR_HOST_GAP
OTHER
```

Do not turn a later retry into a retrospective successful historical slot.

If the successor breaches the frozen max-consecutive-miss gate, mark campaign data quality terminal for formal H36 evaluation; do not silently restart it based on market outcomes.

---

# 6. H36 identity

The successor is a **clean replication** of H35, not a new optimized hypothesis.

Name:

```text
H36_OPPORTUNITY_FORWARD_REPLICATION
```

Question:

> Do the exact frozen TP/BR OPPORTUNITY_ONLY events produce larger future movement than matched non-opportunity market states in clean forward data?

Do not evaluate H36 until all frozen sample and data-quality gates are satisfied.

When not eligible, status must be only:

```text
FORWARD_CAMPAIGN_ACCUMULATING
```

or a data-quality terminal state.

No interim p-value hunting or repeated Alpha interpretation while accumulating.

---

# 7. P0 — Verify Derivatives successor status after real activation

At the time v0.3.17 runs, `DERIVATIVES_PIT_EPOCH_V0316_002` should already be past its fixed start.

Audit only natural `SCHEDULED` rows.

Report:

- expected slots since start;
- recorded slots;
- full/partial/failed/missing;
- per-field availability;
- current max consecutive bad/missing;
- endpoint failure classes;
- scheduler active/enabled;
- whether terminal gap gate has already been breached.

Rules:

- never move epoch start;
- never replace failed/missing slots;
- manual collect cannot improve eligibility;
- old v0.3.14 rows cannot count;
- backfill cannot count.

If v0.3.16 successor is already terminal, report it honestly and stop creating endless epochs in this version. Diagnose the environment first; do not create another successor automatically.

---

# 8. P1 — Microstructure long-run accumulation status

Do not change feature definitions or test returns.

Continue the existing campaign and report rolling reliability mechanically:

```text
campaign age
service uptime/heartbeat coverage
depth coverage
trade coverage
sequence-valid coverage
aggregate completeness
gap taxonomy
resync counts
orphan instances
clock offset/RTT
partition integrity
duplicate/conflict counts
```

Add 24h and 7d rolling summaries only if they can be computed causally and without rewriting prior raw data.

Do not call microstructure `RESEARCH_READY` based on a few minutes/hours of good uptime.

Recommended minimum before a future preregistered Alpha qualification:

```text
>= 30 calendar days
>= 95% trade coverage
>= 95% depth coverage
>= 95% sequence-valid coverage
no unresolved partition checksum drift
```

This is a future-readiness guideline, not an Alpha result.

---

# 9. Unified forward evidence state machine

`quantctl forward-evidence status` should clearly distinguish:

```text
DERIVATIVES:
  old v0.3.14 = TERMINAL_ARCHIVE
  v0.3.16 successor = ACTIVE_ACCUMULATING / TERMINAL

OPPORTUNITY:
  v0.3.13 H35 = DATA_QUALITY_AT_RISK_ARCHIVE
  v0.3.17 H36 = ACTIVE_ACCUMULATING / DATA_QUALITY_TERMINAL / EVALUABLE

MICROSTRUCTURE:
  v0.3.15 = ACTIVE_ACCUMULATING
```

No chain can grant Direction or Execution eligibility.

---

# 10. Operations / alerting

Add or harden a lightweight operational health check suitable for a timer/cron/systemd invocation.

It should return non-zero or a clear unhealthy state for:

- derivatives successor scheduler inactive;
- consecutive derivatives bad slots approaching terminal gate;
- Opportunity successor scheduler inactive;
- Opportunity successor missed-slot streak approaching terminal gate;
- microstructure daemon inactive;
- stale heartbeat/coverage;
- checksum conflict/drift;
- unresolved mature Opportunity outcomes beyond a reasonable resolver delay.

Do not send orders or modify strategies.

If Feishu/Hermes integration is not already appropriate for this data-only health state, produce structured JSON first; do not create a large new notification backend.

---

# 11. Explicit prohibitions

v0.3.17 must NOT:

- test Direction Alpha;
- test OFI/depth/microprice against returns;
- test derivatives features against returns;
- modify TP/BR detector rules;
- change H35/H36 movement definitions;
- reopen Funding/XAB/Spot-Perp Flow;
- reverse failed historical directions;
- access Final Holdout;
- create Candidate Strategy;
- enable paper/testnet/live execution;
- implement Maker-First execution;
- create repeated successor campaigns because early results look bad.

---

# 12. Mandatory tests

At minimum cover:

1. H35 archive remains immutable and `DATA_QUALITY_AT_RISK`;
2. successor start is future-fixed and cannot move;
3. pre-start observations cannot enter successor;
4. missed slot cannot later be replaced by success;
5. successful scan ratio denominator is wall-clock scheduled slots;
6. missing wall-clock slots count as misses;
7. max consecutive missed slots logic;
8. terminal Opportunity quality state cannot recover from later successes;
9. H36 cannot become evaluable before 30d/sample/control/day/coverage gates;
10. no Direction/action columns are introduced;
11. derivatives v0.3.14 stays terminal;
12. derivatives v0.3.16 successor start cannot move;
13. manual/legacy/backfill do not improve derivatives gate;
14. microstructure status cannot modify H36/derivatives eligibility;
15. Execution remains disabled;
16. Final Holdout remains sealed.

Run:

```bash
ruff check .
mypy --strict <current CI source scope>
pytest -q
python -m compileall src tools tests
```

---

# 13. Required GitHub deliverables

All formal text/JSON deliverables MUST be committed and pushed to GitHub under:

```text
deliverables/v0.3.17/
```

At minimum:

```text
README.md
V0.3.17_OPPORTUNITY_SUCCESSOR_FORWARD_STABILIZATION_REPORT.md
V0.3.17_NUMERIC_ANSWERS.json
V0.3.17_RECOMMENDATION.md
OPPORTUNITY_H35_ARCHIVE_AUDIT.json
OPPORTUNITY_H36_SUCCESSOR_STATUS.json
DERIVATIVES_V0316_SUCCESSOR_STATUS.json
MICROSTRUCTURE_LONG_RUN_STATUS.json
FORWARD_EVIDENCE_COMBINED_STATUS.json
FORWARD_OPERATIONS_HEALTH.json
```

Raw SQLite/WAL/high-volume event data remains ignored by Git.

Before declaring completion verify from Git:

```bash
git status
git log --oneline --decorate -12
git ls-tree -r --name-only HEAD deliverables/v0.3.17
git push -u origin codex/v0.3.17-opportunity-successor-forward-stabilization
```

The task is not complete until the remote GitHub branch contains the deliverables.

Create/update a PR to `main`, but do not merge automatically.

---

# 14. Final recommendation vocabulary

Use one primary recommendation only:

```text
FORWARD_EVIDENCE_CHAINS_STABLE_CONTINUE_ACCUMULATION
```

if successor chains are mechanically healthy but not sample-eligible.

```text
FORWARD_EVIDENCE_OPERATIONAL_REPAIR_REQUIRED
```

if a new terminal infrastructure/data-quality problem exists.

```text
H36_EVALUABLE_START_PREREGISTERED_ANALYSIS
```

only if all H36 sample + quality gates are actually met.

This does NOT authorize Direction, Holdout, Paper, Testnet, or Live.

---

# 15. Post-v0.3.17 stop rule

After v0.3.17, do **not** create v0.3.18 merely to keep coding.

If all chains are stable:

> Let real time pass and accumulate forward evidence.

The next strategy/research round should be triggered by one of:

1. Derivatives successor reaches formal 30d/2500/95%/max-gap eligibility;
2. H36 reaches its frozen forward evaluation gate;
3. Microstructure reaches sufficient long-run data health for a separately preregistered feature-family qualification;
4. A genuine operational defect is detected.

Until then:

```text
Strategy: EXPERIMENTAL
Direction Engine: NONE
Runtime maximum: OPPORTUNITY_ONLY
Execution: DISABLED
Final Holdout: SEALED
```
