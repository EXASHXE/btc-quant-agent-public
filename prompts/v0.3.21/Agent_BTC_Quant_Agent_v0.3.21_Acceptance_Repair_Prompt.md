# BTC Quant Agent v0.3.21 — Acceptance Repair

Repository:

```text
EXASHXE/btc-quant-agent
```

Repair branch:

```text
agent/v0.3.21-forward-recovery-cutover
```

Gemini one-pass audit commit:

```text
5d6bb7b54daee19f17e77dbf4535e155d40546db
```

Gemini reviewed implementation SHA:

```text
31aa2c366a52793b72bb87a53bbe07ce6b43a23c
```

Read first:

```text
docs/PROJECT_CONTEXT_HANDOFF.md
docs/MULTI_MODEL_RESEARCH_GOVERNANCE.md
prompts/v0.3.21/Agent_BTC_Quant_Agent_v0.3.21_Forward_Runtime_State_Reconciliation_Local_Resilience_Prompt.md
reviews/v0.3.21/gemini-3.8-flash/REVIEW.md
reviews/v0.3.21/gemini-3.8-flash/REVIEW.json
```

This is a narrow acceptance-repair pass. Do not start v0.3.22, do not add a new alpha family, and do not broaden scope.

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

Strictly forbidden:

```text
NO live/paper/testnet execution enablement
NO Final Holdout access
NO new alpha search or feature mining
NO reopening the stopped official-derivatives symbolic family
NO post-hoc sign reversal or parameter expansion
NO Forward backfill/reconstruction
NO deletion or timestamp rewriting of historical Forward evidence
NO reset/revival of a terminal campaign under the same ID
NO VPS/cloud migration work in this repair
```

## 1. Final-review findings to repair

### F-01 — HIGH — non-hermetic time-dependent doctor test

Gemini identified and ChatGPT independently confirmed that:

```text
tests/test_v0321_resilience.py::test_forward_doctor_preregistered_successor_recognized
```

asserts:

```text
PREREGISTERED_NOT_STARTED
```

while `check_campaign_states()` uses the real `time.time()` clock. Once the frozen successor start `1788458400000` ms passed, production behavior correctly changed to `HEALTHY_ACCUMULATING`, so the test became deterministically stale. GitHub Actions is therefore RED across Python 3.11/3.12/3.13.

Repair this with deterministic time control.

Required acceptance behavior:

1. A pre-start test uses an explicit deterministic time strictly before `1788458400000` ms and asserts:

```text
status = PREREGISTERED_NOT_STARTED
is_healthy = true
```

2. A post-start test uses an explicit deterministic time at/after `1788458400000` ms and asserts:

```text
status = HEALTHY_ACCUMULATING
is_healthy = true
```

3. Tests must not depend on the wall clock date on which CI happens to run.

Preferred minimal implementation:
- patch `btc_quant_agent.forward_diagnostics.time.time` in the relevant tests; or
- add a small backward-compatible `now_ms` injection path if it materially improves determinism without broad refactoring.

Do not change production state semantics merely to make the old assertion pass.

### F-02 — formal post-start evidence artifact is missing

The frozen v0.3.21 prompt requires:

```text
deliverables/v0.3.21/POST_START_SUCCESSOR_HEALTH.json
```

once natural post-start evidence exists. Gemini observed 42 natural slots, so this artifact is now required before final stage closure.

Create it from the existing immutable Forward stores. Do not synthesize or backfill observations.

Use a deterministic audit cutoff timestamp and record it explicitly.

At minimum include:

#### Derivatives

```text
epoch_id
start_ms
audit_cutoff_ms
expected scheduled slots
recorded slots
COMPLETE count
PARTIAL count
FAILED count
missing count
maximum consecutive failed/missing streak
required-field available count / denominator / ratio
frozen thresholds
current gate status
```

#### Opportunity

```text
campaign_id
hypothesis_id
start_ms
audit_cutoff_ms
expected decision slots
SUCCESSFUL_SCAN count
MISSED_DECISION_SLOT count
missing count
maximum consecutive missed streak
successful scan ratio
frozen thresholds
current gate status
```

#### Microstructure

Where deterministically auditable from local Forward stores, include:

```text
campaign_id
partition count/latest partition
latest heartbeat
heartbeat freshness at audit cutoff
event counts / continuity indicators
known gap status
```

#### Overall

Explicitly distinguish:

```text
HEALTHY_ACCUMULATING
FORWARD_DATA_INSUFFICIENT
TERMINAL_BREACH
```

Do not label H38 statistically qualified. H38 still requires its frozen long-horizon sample/calendar/control requirements.

### F-03 — re-evaluate current Forward state through the repair cutoff

Do not assume Gemini's 42-slot snapshot is still the current truth.

Because the local Windows/WSL host can sleep, reboot, or lose network, re-evaluate all natural elapsed slots from each v0.3.21 successor start through the repair audit cutoff.

If a frozen consecutive gap/miss gate has been breached since Gemini's audit:

```text
1. record the breach honestly;
2. mark the affected campaign/epoch terminal according to frozen semantics;
3. do not backfill or reset counters;
4. do not create another successor merely to force v0.3.21 to PASS;
5. final repair verdict must be FORWARD_DATA_INSUFFICIENT (or REPAIR_REQUIRED if a separate software defect remains).
```

If gates remain satisfied, report `HEALTHY_ACCUMULATING` and continue accumulation.

Gemini's previously observed 4 PARTIAL Derivatives slots and one Opportunity missed activation-boundary slot are not to be erased. Evaluate them under the frozen formal gates, not an invented post-hoc threshold.

## 2. Low-severity findings

### Binance basis HTTP 418 / partial rows

Gemini observed a small number of `PARTIAL` Derivatives snapshots associated with HTTP 418 or empty basis payloads while required-field availability remained above the frozen 95% gate.

For this repair:
- preserve those rows exactly;
- report them in `POST_START_SUCCESSOR_HEALTH.json`;
- do not weaken thresholds;
- do not add a large rate-limit redesign unless current evidence shows an actual frozen-gate risk.

### Microstructure teardown AttributeError

Gemini observed:

```text
AttributeError: 'ClientConnection' object has no attribute 'recv_messages'
```

during connection teardown while the process remained alive and streaming.

This is nonblocking for v0.3.21 unless it is reproducibly causing capture gaps or process death. Prefer documenting it as a deferred maintenance item. If you choose to patch it now, keep the change minimal and add a direct regression test; do not broaden the repair.

## 3. Deliverable accuracy repair

Update v0.3.21 release documentation so it no longer presents pre-start verification as the latest state after natural Forward accumulation has begun.

Audit and update where necessary:

```text
deliverables/v0.3.21/README.md
deliverables/v0.3.21/V0.3.21_FORWARD_LOCAL_RECOVERY_REPORT.md
deliverables/v0.3.21/PR_BODY.md
```

Requirements:
- keep preregistration/preflight history intact;
- add the current post-start state rather than rewriting historical facts;
- report actual current test counts/results;
- do not claim CI green until exact repair SHA CI is green;
- distinguish infrastructure `HEALTHY_ACCUMULATING` from statistical H38 qualification.

## 4. Required test/CI acceptance

Run locally at the exact repair SHA:

```bash
ruff check .
mypy src
pytest -q
python -m compileall -q src tests tools skill-template/scripts
```

If repository CI uses a narrower compileall path, also run that exact CI command.

Then push and require GitHub Actions green on the exact repair SHA for:

```text
Python 3.11
Python 3.12
Python 3.13
```

The two new/updated time-state tests must explicitly cover both sides of the frozen start boundary.

No acceptance based on an older green run.

## 5. Safety and provenance checks

Before reporting completion verify:

```text
execution = DISABLED
auto_execute = false
qualified_direction_engine = NONE
runtime_maximum = OPPORTUNITY_ONLY
final_holdout = SEALED
```

Also report:

```text
Forward rows deleted = 0
Forward rows backfilled/reconstructed = 0
historical start timestamps moved = 0
terminal campaigns revived = 0
```

## 6. Review workflow after repair

Under the simplified governance, do NOT request a second Gemini audit by default.

After the repair is pushed and exact-SHA CI is green:

```text
Implementation Agent -> reports exact repair SHA and evidence
ChatGPT -> performs final acceptance review directly
```

A second Gemini pass is only needed if ChatGPT explicitly requests one because the repair introduces material new research/production logic. A deterministic test repair and evidence-finalization pass should not trigger another review ceremony.

## 7. Allowed final repair verdicts

Choose exactly one:

```text
PASS
PASS_WITH_NONBLOCKING_FOLLOWUPS
REPAIR_REQUIRED
FORWARD_DATA_INSUFFICIENT
```

`PASS` requires all of:

```text
time-dependent test repaired deterministically
pre-start and post-start states both directly tested
local full suite green
GitHub Actions green on exact repair SHA across 3.11/3.12/3.13
POST_START_SUCCESSOR_HEALTH.json created from natural immutable evidence
current Forward gap gates still satisfied
release docs accurately distinguish preregistration vs current accumulation
all safety invariants preserved
Final Holdout remains sealed
```

The microstructure teardown log noise may remain a documented nonblocking follow-up if it has not caused evidence loss or process failure.

## 8. Required final implementation-agent response

Report concisely:

```text
1. branch
2. exact repair HEAD SHA
3. parent/review SHA
4. files changed
5. F-01 test repair details
6. pre-start test result
7. post-start test result
8. current Derivatives post-start metrics through audit cutoff
9. current Opportunity post-start metrics through audit cutoff
10. current Microstructure health
11. POST_START_SUCCESSOR_HEALTH.json path
12. ruff result
13. mypy result
14. pytest result
15. compileall result
16. GitHub Actions run ID and 3.11/3.12/3.13 status
17. execution safety state
18. Final Holdout access count
19. Forward deletion/backfill/rewrite counts
20. remaining nonblocking follow-ups
21. final repair verdict
```

Do not merge to `main` yourself unless explicitly instructed. Stop after reporting the exact repair SHA and evidence for ChatGPT final acceptance review.
