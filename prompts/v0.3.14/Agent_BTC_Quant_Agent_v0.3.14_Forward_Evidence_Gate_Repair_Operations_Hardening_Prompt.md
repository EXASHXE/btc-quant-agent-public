# BTC Quant Agent v0.3.14 — Forward Evidence Gate Repair & Operations Hardening

Repository: `EXASHXE/btc-quant-agent`

This prompt is model-neutral and may be executed by Codex, Gemini/Antigravity, or another capable coding agent.

## 0. Mission

Implement **v0.3.14 Forward Evidence Gate Repair & Operations Hardening**.

This is **not** a new Alpha research round. Do not open a new historical Direction family. Do not touch Final Holdout. Do not enable paper/testnet/live execution.

v0.3.13 successfully started two real forward evidence streams:

1. `OPPORTUNITY_FORWARD_V0313_20260831T050656Z` — directionless TP/BR Opportunity Forward Shadow.
2. append-only BTCUSDT forward Derivatives PIT collection.

v0.3.14 must make those streams operationally trustworthy and repair one P0 eligibility-gate defect found during review.

---

# 1. Start point / Git workflow

Start from the actual latest accepted v0.3.13 head:

```text
branch: codex/v0.3.13-opportunity-forward-shadow-reliability
reviewed HEAD: b260d6655ab8661b4203da90a6bf53f4372d0aa5
```

First run:

```bash
cd /root/workspace/project/Quant-agent
git status
git remote -v
git branch --show-current
git rev-parse HEAD
git log --oneline --decorate -15
gh auth status
```

Then create/reuse:

```text
codex/v0.3.14-forward-evidence-gate-repair-operations-hardening
```

Do not merge to `main` automatically.

Record exact:

- start SHA;
- implementation SHA;
- final delivery SHA;
- PR number;
- CI run/status.

---

# 2. Frozen safety state

The following remain mandatory throughout v0.3.14:

```text
Strategy = EXPERIMENTAL
Runtime maximum = OPPORTUNITY_ONLY
Qualified Direction Engine = NONE
Execution = DISABLED
Candidate Freeze = NONE
Final Holdout = SEALED
```

Do not produce actionable LONG/SHORT, Entry, SL, TP, position sizing, trade PnL, or an Alpha claim.

The existing v0.3.13 Opportunity Forward campaign must continue. Do **not** silently restart it merely because code changes.

---

# 3. Frozen v0.3.13 facts

Treat these as immutable input evidence:

## Opportunity Forward

```text
campaign_id = OPPORTUNITY_FORWARD_V0313_20260831T050656Z
H35 = FORWARD_CAMPAIGN_ACCUMULATING
successful scans at delivery = 1
missed slots at delivery = 1
TP = 0
BR = 0
resolved opportunities = 0
```

H35 may only become evaluable after the already frozen gate:

```text
resolved 8h opportunities >= 30
calendar age >= 30 days
unique matched controls >= 100
distinct resolved UTC days >= 20
```

Preferred resolved opportunities remains 50.

Do not change this gate.

## Derivatives forward evidence

Frozen research gate remains conceptually:

```text
minimum evidence duration = 30 days
minimum fully available snapshots = 2500
minimum availability for every required field = 95%
maximum persistent scheduled gap = 4 slots
```

Required fields remain:

```text
funding_rate
open_interest
taker_buy_sell_ratio
basis_rate
long_short_account_ratio
```

Do not loosen these gates.

---

# 4. P0 defect: current Derivatives gap gate is logically non-recoverable

The v0.3.13 implementation currently calculates `largest_gap_slots` / longest failure run over the retained all-time collection ledger, including pre-repair legacy failures.

At v0.3.13 delivery:

```text
largest failure run = 54 slots
```

The eligibility check requires:

```text
largest_gap_slots <= 4
```

Because the old 54-slot sequence is immutable, the current implementation can never satisfy the gate, even after months of perfect future collection.

The report text says the gate is recoverable with a clean future window, but the current code does not implement such an evidence-window or epoch policy.

This must be repaired without deleting, relabelling, or hiding historical failures.

---

# 5. P0-A: introduce a preregistered Forward Evidence Epoch

Implement an explicit, immutable **Evidence Epoch** for Derivatives research eligibility.

Purpose:

> Separate archival history from the formally qualified evidence interval without cherry-picking a later rolling window after seeing results.

Suggested identity:

```text
DERIVATIVES_PIT_EPOCH_V0314_001
```

Create a committed machine-readable config before formal post-change eligibility accumulation, for example:

```text
configs/forward/v0.3.14_derivatives_evidence_epoch.json
```

It must include at least:

```text
epoch_id
symbol
created_from_git_sha
epoch_start_ms
epoch_start_rule
cadence_minutes = 15
post_boundary_delay_seconds
required_fields
minimum_days = 30
minimum_fully_available_snapshots = 2500
minimum_required_field_availability = 0.95
maximum_consecutive_failed_or_missing_scheduled_slots = 4
manual_runs_count_for_eligibility = false
legacy_runs_count_for_eligibility = false
backfill_allowed = false
final_holdout_access = false
```

## Ordering requirement

The epoch config must be committed before it is used as the active eligibility epoch.

Record the epoch-freeze commit SHA.

Do not choose the epoch start retrospectively based on which interval looks cleanest. Use a deterministic rule tied to deployment/freeze, such as the first scheduled slot after the epoch-freeze commit and successful unit installation.

---

# 6. Evidence-epoch semantics

All previous collection rows must remain preserved.

Do not delete or rewrite:

```text
legacy failed attempts
partial attempts
manual attempts
pre-v0.3.14 snapshots
```

Instead, explicitly distinguish:

```text
ARCHIVE / PRE_EPOCH
ACTIVE_EVIDENCE_EPOCH
```

Recommended implementation options:

- `evidence_epoch_id` on new `collection_runs` and optionally snapshots;
- or a separate immutable epoch table with timestamp-based membership.

Whichever representation is chosen, it must be auditably deterministic.

## Eligibility denominator

Formal v0.3.14+ eligibility must use **scheduled slots in the active evidence epoch only**.

Manual attempts:

```text
can diagnose endpoints
can be stored
must NOT improve formal eligibility
```

Legacy attempts:

```text
remain visible in archive metrics
must NOT contaminate the active epoch denominator
```

## Gap semantics

`maximum_consecutive_failed_or_missing_scheduled_slots <= 4` must mean:

> Within the frozen active Evidence Epoch, based on expected 15-minute scheduled slots, the largest consecutive sequence that is either missing, failed, or not fully available is at most four slots.

A missing systemd invocation is therefore a gap too; it cannot disappear just because no DB run was written.

Do not compute the formal gap only over rows that happened to exist.

---

# 7. P0-B: collector transient-network reliability

v0.3.13 fixed the primary systemd proxy-environment problem. Remaining observed issue:

```text
intermittent TLS_HANDSHAKE_TIMEOUT on openInterest
```

Add bounded per-endpoint retry for transient public-network failures.

Frozen retry policy for this version:

```text
max total attempts per endpoint = 3
retry count after first failure = 2
bounded backoff = short and deterministic
no retry for clearly non-transient schema/validation failures
```

Classify at least:

```text
CONNECT_TIMEOUT
READ_TIMEOUT
TLS_HANDSHAKE_TIMEOUT
CONNECTION_RESET
DNS_ERROR
HTTP_429
HTTP_5XX
HTTP_4XX_NON_RETRYABLE
SCHEMA_ERROR
VALIDATION_ERROR
UNKNOWN
```

Do not turn repeated failure into a fabricated value.

Record per required endpoint:

```text
attempt_count
success/failure
latency_ms per attempt or total latency
final_error_class
source_timestamp
```

`observed_at_ms` must remain the time after the full snapshot collection/assembly completes, not the start time.

Preserve each exchange/source timestamp independently.

Do not backfill missed PIT values later.

---

# 8. Slot-boundary and retry safety

Retries must not destroy PIT semantics.

If a collection begins for scheduled slot `T` and retries run long:

- keep it associated with the original scheduled slot;
- record actual `collection_started_at_ms` and final `observed_at_ms`;
- do not create a second synthetic observation for the same slot;
- do not use data from a later scheduled slot as if observed at the earlier one.

If the collection exceeds a reasonable bounded execution window, store PARTIAL/FAILED and let the next natural slot proceed.

Add tests around slot identity across retries.

---

# 9. P1-A: automate Opportunity outcome resolution

The v0.3.13 observation timer only runs:

```text
opportunity-forward collect-once
```

Outcome resolution currently requires a separate manual:

```text
opportunity-forward resolve
```

Add a persistent, idempotent outcome-resolution scheduler.

Preferred:

```text
btc-quant-opportunity-resolve.service
btc-quant-opportunity-resolve.timer
```

A 15-minute or hourly cadence is acceptable; choose one deterministic cadence and document it.

The resolver may only:

- find already-mature 4h/8h observations;
- query post-event public 1m candles;
- verify the strict next-open window;
- append missing outcome labels;
- retry unresolved labels after transient network failures.

It must never:

- alter original scan observations;
- create missed scan observations retrospectively;
- infer a TP/BR event after the fact;
- create Direction;
- reconstruct missing PIT features.

Outcome resolution after the horizon is outcome labelling, not feature backfill. Preserve that separation in code and docs.

---

# 10. P1-B: unified forward-evidence status / watchdog

Add a single operational status surface, for example:

```text
quantctl forward-evidence status
quantctl forward-evidence audit
```

or equivalent.

It should report, without Alpha interpretation:

## Derivatives

```text
active epoch id
epoch age
expected scheduled slots
recorded scheduled slots
fully available scheduled slots
partial slots
failed slots
missing slots
active-epoch success rate
required-field coverage per field
max consecutive bad/missing slots
2500 progress
30d progress
eligibility state
scheduler enabled/active
last scheduled status
recent endpoint error classes
```

Also expose archive/pre-epoch counts separately.

## Opportunity Forward

```text
campaign id
campaign age
scheduled slots
successful scans
missed slots
TP count
BR count
resolved 4h
resolved 8h
unique controls
distinct resolved days
H35 state
collection timer status
resolver timer status
unresolved mature labels
```

No green `HEALTHY` label based on one or two successes. Use conservative states such as:

```text
INITIALIZING
COLLECTING
DEGRADED
ELIGIBLE_FOR_PREREGISTERED_RESEARCH
```

---

# 11. Preserve the existing Opportunity campaign

Do not reset `OPPORTUNITY_FORWARD_V0313_20260831T050656Z` merely to obtain a cleaner sample.

The v0.3.13 campaign is genuine forward evidence and should continue under its frozen detector/config semantics.

If a code change would alter the actual detector semantics or frozen config hash, fail closed and explain that a new campaign would be required. Do not silently migrate observations.

Operational fixes that do not change frozen signal semantics may continue the same campaign.

Add a regression test proving normal Runtime remains:

```text
RUNTIME_GATED
maximum OPPORTUNITY_ONLY
signal = null
Direction Engine = NONE
```

---

# 12. No v0.3.14 Alpha experiment

Do not run a new historical Direction search in this version.

Specifically prohibited:

- Funding threshold/window changes;
- XAB reversal/basket/window changes;
- Spot/Perp flow threshold/window/sign reversal;
- EMA/RSI/MACD/ADX Direction revival;
- TP/BR parameter optimization;
- Range/Bollinger optimization;
- new ML/RL model;
- Final Holdout;
- Candidate Freeze;
- Paper/Testnet/Live execution.

The correct v0.3.14 result is improved evidence infrastructure, not a better backtest.

---

# 13. Mandatory tests

Add direct tests for at least:

1. pre-epoch rows are preserved;
2. pre-epoch failures do not enter active-epoch eligibility denominator;
3. manual runs never improve formal eligibility;
4. expected missing scheduled slots count as gaps;
5. active-epoch consecutive gap is computed on wall-clock slots, not only existing DB rows;
6. 30d/2500/95%/max4 gates remain unchanged;
7. epoch start cannot be moved retrospectively by status code;
8. duplicate/conflicting slot remains immutable;
9. retry succeeds after one transient error;
10. retry stops after max 3 attempts;
11. non-retryable schema/validation error is not repeatedly retried;
12. retry telemetry/error classification is persisted;
13. `observed_at_ms >= collection_started_at_ms` and reflects final assembly;
14. source timestamps may not be after observed_at;
15. retries do not create a second scheduled slot;
16. outcome resolver is idempotent;
17. outcome resolver never mutates scan observation rows;
18. immature 4h/8h outcomes are not resolved;
19. mature network-failed outcome remains unresolved/retryable;
20. Opportunity campaign ID/frozen semantics remain unchanged;
21. Runtime cannot emit actionable LONG/SHORT;
22. execution remains disabled;
23. Final Holdout remains sealed.

Keep tests deterministic; no real-network dependency in unit tests.

---

# 14. Real operational validation

After implementation/tests, perform real local operational checks in the actual WSL/systemd environment.

At minimum:

```bash
systemctl --user daemon-reload
systemctl --user status btc-quant-forward-derivatives.timer
systemctl --user status btc-quant-opportunity-forward.timer
systemctl --user status btc-quant-opportunity-resolve.timer
```

Run safe diagnostics and at least one systemd-context collection after deployment.

Then wait for / inspect at least one natural scheduled invocation if practical within the task session.

Never manufacture a scheduled success from a manual invocation.

If natural timer evidence is not available before task completion, report that limitation explicitly.

Do not include proxy secrets in Git, logs, reports, or deliverables.

---

# 15. Quality gates

Run:

```bash
ruff check .
mypy
pytest -q
pytest --cov=btc_quant_agent --cov-report=term-missing
python -m compileall -q src tools tests skill-template/scripts
```

Expected:

```text
all tests pass
Ruff PASS
strict Mypy PASS
compileall PASS
```

Prioritize direct coverage of:

```text
forward_store
network/retry logic
evidence epoch
gap calculation
opportunity_forward
resolver
Runtime gate
```

Do not weaken tests to get green CI.

---

# 16. Required v0.3.14 deliverables

Create and commit at least:

```text
deliverables/v0.3.14/
├── README.md
├── V0.3.14_FORWARD_EVIDENCE_GATE_REPAIR_REPORT.md
├── V0.3.14_NUMERIC_ANSWERS.json
├── V0.3.14_RECOMMENDATION.md
├── DERIVATIVES_EVIDENCE_EPOCH_STATUS.json
├── DERIVATIVES_COLLECTOR_RELIABILITY_STATUS.json
├── OPPORTUNITY_FORWARD_CAMPAIGN_STATUS.json
├── OUTCOME_RESOLVER_STATUS.json
└── FORWARD_EVIDENCE_OPERATIONS.md
```

The report must explicitly answer:

1. What was wrong with the old `largest_gap_slots` eligibility logic?
2. What is the frozen active evidence epoch ID/start rule/start timestamp?
3. Were any historical failed/partial/manual rows deleted or relabelled?
4. Which rows count toward formal eligibility?
5. How are missing scheduled slots detected?
6. Current active-epoch fully available snapshot count?
7. Current per-required-field active-epoch coverage?
8. Current active-epoch largest consecutive bad/missing slot run?
9. Current 30d/2500/95%/max4 progress?
10. Retry policy and actual retry telemetry?
11. Latest natural systemd collection result?
12. Opportunity campaign ID unchanged?
13. Current TP/BR/resolved/controls counts?
14. Is outcome resolver timer enabled/active?
15. Any Direction claim? Must be `NONE`.
16. Any Execution? Must be `DISABLED`.
17. Any Holdout access? Must be `false`.
18. Tests / coverage / Ruff / Mypy / compileall?
19. Exact branch/start SHA/final SHA/CI/PR?
20. Final recommendation?

---

# 17. Recommendation vocabulary

Use only one final recommendation:

```text
CONTINUE_FORWARD_EVIDENCE_ACCUMULATION
```

unless an unrepaired operational correctness blocker remains, in which case:

```text
FORWARD_EVIDENCE_BLOCKED_REQUIRES_REPAIR
```

Do not invent an Alpha recommendation in v0.3.14.

H35 remains `FORWARD_CAMPAIGN_ACCUMULATING` unless its already frozen gates naturally happen to be met during elapsed real time; do not accelerate or backfill it.

Derivatives remains `INSUFFICIENT_FORWARD_HISTORY` until the frozen active-epoch gate naturally passes.

---

# 18. GitHub delivery is mandatory

The task is **not complete** when files merely exist locally.

Before final response run:

```bash
git status
git log --oneline --decorate -15
git diff <start-sha>..HEAD --stat
git ls-tree -r --name-only HEAD deliverables/v0.3.14
git ls-tree -r --name-only HEAD configs/forward
git push -u origin codex/v0.3.14-forward-evidence-gate-repair-operations-hardening
```

Open/update the v0.3.14 PR, but do not merge it.

Verify from GitHub remote that all formal deliverables are readable.

Final agent response must report:

```text
branch
start SHA
epoch freeze commit SHA
implementation SHA
final delivery SHA
PR number
CI status
evidence epoch ID
Derivatives eligibility state
Opportunity H35 state
collector operational state
resolver operational state
Strategy status
Runtime maximum
Direction Engine
Execution
Final Holdout
```

Finish with:

```text
Strategy: EXPERIMENTAL
Runtime maximum: OPPORTUNITY_ONLY
Qualified Direction Engine: NONE
Execution: DISABLED
Candidate Freeze: NONE
Final Holdout: SEALED
```
