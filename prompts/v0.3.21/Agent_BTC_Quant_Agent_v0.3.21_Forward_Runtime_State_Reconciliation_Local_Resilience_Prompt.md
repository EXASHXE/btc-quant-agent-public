# BTC Quant Agent v0.3.21 — Forward Runtime State Reconciliation & Local Resilience

Repository:

```text
EXASHXE/btc-quant-agent
```

Expected accepted baseline when this prompt was drafted:

```text
main
ec08024588e6a766e061ed25ceb62ec24751fa61
```

Before doing anything:

```bash
git fetch --all --prune
git checkout main
git pull --ff-only
git status
git rev-parse HEAD
git log -10 --oneline
```

If `main` has advanced, inspect the newer accepted commits and use the latest accepted `main` as the base. Do not silently discard newer work.

Read first:

```text
docs/PROJECT_CONTEXT_HANDOFF.md
docs/MULTI_MODEL_RESEARCH_GOVERNANCE.md
reviews/v0.3.20/gemini-3.8-flash/REVIEW.md
deliverables/v0.3.20/README.md
deliverables/v0.3.20/ACCEPTANCE_REPAIR_REPORT.md
deliverables/v0.3.20/POST_START_SUCCESSOR_HEALTH.json
deliverables/v0.3.20/FORWARD_DOCTOR_REPORT.json
docs/FORWARD_DERIVATIVES_OPERATIONS.md
```

This is an operations / Forward-evidence integrity stage. It is NOT a new alpha-search stage and does NOT require VPS/cloud migration.

## 0. Frozen invariants

These remain unchanged:

```text
strategy = EXPERIMENTAL
qualified_direction_engine = NONE
runtime_maximum = OPPORTUNITY_ONLY
execution = DISABLED
auto_execute = false
live trading = NOT AUTHORIZED
final_holdout = SEALED
```

Strict prohibitions:

```text
NO live execution
NO paper/testnet execution enablement
NO Final Holdout access
NO new direction model
NO symbolic-search budget expansion
NO reopening the stopped official-derivatives symbolic family
NO post-hoc sign reversal
NO synthetic historical L2 / OFI / microprice from candles
NO reconstruction of missed true Forward slots
NO deleting failed Forward records
NO moving historical campaign start timestamps
NO resetting terminal campaigns
NO proxy/VPN technique intended to bypass jurisdictional or provider restrictions
NO VPS/cloud-provider provisioning or migration work in v0.3.21
```

Historical Forward gaps and failures are immutable evidence.

## 1. Frozen v0.3.20 facts

### Derivatives

`DERIVATIVES_PIT_EPOCH_V0320_001` recorded:

```text
expected slots = 5
fully available = 0
failed = 5
maximum consecutive failure streak = 5
frozen maximum = 4
```

Therefore it is permanently:

```text
TERMINAL_BREACH
COMPROMISED_AT_RISK
```

It is ineligible for continued formal accumulation.

### Opportunity

`OPPORTUNITY_FORWARD_V0320_20260903T063000Z` / `H37_OPPORTUNITY_FORWARD_REPLICATION_RECOVERY` recorded:

```text
expected scans = 5
successful scans = 0
MISSED_DECISION_SLOT = 5
maximum consecutive miss streak = 5
frozen maximum = 4
```

Therefore it is permanently terminal and must never be restarted under the same campaign ID.

### Microstructure

Last accepted v0.3.20 evidence showed:

```text
MICROSTRUCTURE_CAPTURE_V0315_001 = HEALTHY_COLLECTING
```

Do not retroactively mark this campaign failed merely because Derivatives/H37 failed.

## 2. v0.3.21 objectives

Complete these in order:

```text
A. Reconcile canonical runtime state with known terminal evidence
B. Make systemd/runtime fail closed against stale or terminal campaigns
C. Fix Opportunity collector/resolver campaign parity structurally
D. Harden local WSL lifecycle/network recovery and observability
E. Make Forward Doctor the authoritative local preflight
F. Only if the local machine is genuinely healthy, preregister fresh successors
G. Verify natural post-start Forward slots without backfill
```

Do not start a new alpha hypothesis in this version.

## 3. Phase A — Canonical terminal-state reconciliation

Audit at minimum:

```text
configs/forward/derivatives_evidence_epochs.json
configs/forward/opportunity_forward_campaigns.json
configs/forward/v0.3.20_derivatives_evidence_epoch.json
configs/forward/v0.3.20_opportunity_successor_campaign.json
src/btc_quant_agent/forward_evidence.py
src/btc_quant_agent/forward_diagnostics.py
```

The current repository may still represent v0.3.20 Derivatives/H37 as active even though immutable empirical evidence shows their gap gates were breached.

Reconcile canonical registries so both are represented as terminal/ineligible. Use the actual first gate-breach timestamp derived from immutable evidence where available. Do not fabricate timestamps.

Required semantics:

```text
terminal = true
formal eligibility = terminal/ineligible
immutable_history = true
terminal reason = frozen consecutive gap/miss gate breached
```

Do not assign `superseded_by` until a real fresh successor has been preregistered.

Add direct tests proving:

1. terminal chains cannot resolve as active;
2. terminal chains cannot be selected by normal scheduled collection;
3. terminal state is irreversible;
4. no terminal history is deleted or rewritten.

Produce:

```text
deliverables/v0.3.21/TERMINAL_STATE_RECONCILIATION.json
```

## 4. Phase B — Fail-closed runtime/service activation

Audit:

```text
deploy/systemd/btc-quant-forward-derivatives.service
deploy/systemd/btc-quant-forward-derivatives.timer
deploy/systemd/btc-quant-opportunity-forward.service
deploy/systemd/btc-quant-opportunity-forward.timer
deploy/systemd/btc-quant-opportunity-resolve.service
deploy/systemd/btc-quant-opportunity-resolve.timer
deploy/systemd/btc-quant-microstructure-forward.service
deploy/systemd/btc-quant-forward-health.service
deploy/systemd/btc-quant-forward-health.timer
deploy/systemd/install-all-forward-services.sh
```

The installer/runtime must not blindly restart terminal campaigns because stale `.service` files still reference them.

Expected behavior:

```text
terminal campaign -> collector activation refused
no eligible active/preregistered campaign -> corresponding collector remains stopped
health/doctor may still run
microstructure lifecycle remains independent
```

Prefer deterministic registry-driven active campaign resolution over hard-coded version filenames.

Add tests that prove a fresh installation cannot silently restart a terminal Derivatives or Opportunity campaign.

## 5. Phase C — Opportunity collector/resolver parity

Current wiring must be audited for this invalid state:

```text
collector -> campaign A
resolver  -> campaign B
```

Fix this structurally, not by merely replacing one hard-coded filename with another.

Collector and resolver for one formal Opportunity campaign must resolve exactly the same campaign ID/config through one deterministic active-campaign resolution path.

Add direct tests that fail if collector and resolver resolve different formal campaigns.

Also verify:

```text
outcomes use only data after original Forward decision
reference-price semantics remain causal
ATR is the frozen ATR observed at scan time
240m/480m outcomes resolve only after maturity
missed observations are never reconstructed
```

## 6. Phase D — Local Windows/WSL resilience

The formal collection host for this version remains the current local Windows + WSL environment.

Do not pretend this can guarantee uninterrupted 24x7 operation. Windows shutdown, sleep, WSL teardown, network loss and source/API outages create real Forward gaps that cannot be backfilled.

The objective is to reduce avoidable outages and recover correctly, not to hide gaps.

Audit existing Windows/WSL lifecycle tooling and harden where needed.

Required capabilities:

### D1. WSL/systemd lifecycle checks

Verify and report:

```text
systemd enabled
user systemd available
loginctl linger enabled
required timers enabled
microstructure daemon active
service restart policies correct
```

Provide idempotent setup/repair commands or scripts where missing.

### D2. Windows restart/login recovery tooling

Where practical, provide an optional Windows-side script/task definition that can start the intended WSL distro and invoke a safe Forward recovery/preflight after Windows boot/login.

Requirements:

```text
idempotent
no credentials embedded
no execution/trading path
no historical backfill
no silent reset of terminal campaigns
```

Do NOT automatically alter user sleep/power policy without explicit user approval. Instead diagnose and document whether sleep/Modern Standby remains an active Forward risk.

### D3. Resume/network-change recovery

Add or harden a safe recovery path that, after WSL/service interruption or network restoration:

```text
runs doctor
checks registry state
checks network/source reachability
checks storage/SQLite
checks microstructure heartbeat/partition state
restarts only eligible services
records actual missed slots/gaps
never backfills them
```

A recovery command must not convert a terminal campaign back to active.

### D4. Resource protection

Check at minimum:

```text
disk free space
microstructure partition growth
SQLite lock/health state
memory use
heartbeat freshness
log growth
```

Add warning/fail-closed thresholds where appropriate and deterministic tests for the critical logic.

Produce:

```text
deliverables/v0.3.21/LOCAL_RUNTIME_RESILIENCE_REPORT.json
```

## 7. Phase E — Forward Doctor as authoritative local preflight

`quantctl forward-evidence doctor` must become the authoritative gate before fresh successors can be preregistered or activated.

It must verify at minimum:

```text
Git/deployment identity
canonical registry consistency
systemd/timer state
user linger
host clock sanity
storage writability
SQLite integrity
microstructure partition health
microstructure heartbeat freshness
network configuration
required REST reachability
required WebSocket reachability where practical
HTTP451 / provider restriction failure
collector/resolver campaign parity
terminal/stale campaign wiring
```

Doctor must fail closed if:

```text
HTTP451 is observed
required endpoints are unavailable
registry says active while empirical terminal gate is breached
collector/resolver campaigns disagree
storage is unwritable
SQLite integrity is bad
microstructure is stale when expected active
required systemd state is invalid
```

Do not equate a particular IP geography with eligibility. Actual provider/jurisdiction eligibility and real endpoint reachability are distinct requirements.

Do not add instructions intended to bypass regional/provider restrictions.

Produce:

```text
deliverables/v0.3.21/LOCAL_FORWARD_PREFLIGHT.json
```

If preflight is not genuinely healthy, do not preregister a fresh successor merely to finish the version.

## 8. Runtime health state model

Update `quantctl forward-evidence health` / doctor so they can distinguish, or equivalently type:

```text
HEALTHY
HEALTHY_ACCUMULATING
PREREGISTERED_NOT_STARTED
FORWARD_DATA_INSUFFICIENT
TERMINAL_BREACH
NETWORK_INELIGIBLE
CONFIGURATION_INCONSISTENT
SERVICE_UNHEALTHY
HOST_LIFECYCLE_AT_RISK
STORAGE_AT_RISK
```

Avoid one generic boolean when remediation differs materially.

Historical terminal chains must remain visible without contaminating the status of a fresh successor.

## 9. Fresh successor preregistration — only after healthy local preflight

If and only if the real local environment passes the frozen preflight, create clean successors.

### Derivatives

Use:

```text
DERIVATIVES_PIT_EPOCH_V0321_001
```

Carry forward the existing research semantics and data-quality gate. Do NOT weaken:

```text
maximum_consecutive_failed_or_missing_scheduled_slots = 4
```

### Opportunity

Use a fresh operational replication successor, for example:

```text
H38_OPPORTUNITY_FORWARD_REPLICATION_LOCAL_RECOVERY
OPPORTUNITY_FORWARD_V0321_<FIXED_START_UTC>
```

H38 is NOT a new directional hypothesis.

Keep:

```text
direction_claim = NONE
runtime = OPPORTUNITY_ONLY
```

Keep the frozen TP/BR detector semantics and movement-outcome hypothesis unless a separately reviewed preregistration explicitly justifies a change.

## 10. Successor start-time rule

Do not hard-code a start timestamp in this prompt.

Only after:

```text
code complete
tests pass
local doctor/preflight HEALTHY
canonical terminal states reconciled
```

select deterministically:

```text
start = first fully closed UTC 15m boundary
        at least 30 minutes after preregistration commit
```

Commit successor configs/manifest before the start timestamp.

Record:

```text
preregistration SHA
commit timestamp
campaign/epoch start UTC
config hashes
previous terminal IDs
```

in:

```text
deliverables/v0.3.21/SUCCESSOR_PREREGISTRATION_MANIFEST.json
```

Never move the boundary after commit.

## 11. Natural post-start recovery evidence

Do not simulate or backfill acceptance evidence.

For initial operational recovery require at least 8 consecutive natural 15-minute slots after the fresh start boundary.

### Derivatives

Target recovery evidence:

```text
expected = 8+
recorded = expected
fully available required snapshots = expected
failed = 0
missing = 0
required-field coverage = 100%
maximum consecutive bad/missing = 0
```

If a natural failure occurs, record the real result. Do not reset counters.

### Opportunity

Target:

```text
expected scans = 8+
successful scans = expected
MISSED_DECISION_SLOT = 0
market_data_health = OK
observations durably stored
collector campaign ID = resolver campaign ID
```

This establishes only `HEALTHY_ACCUMULATING`; it does not statistically qualify H38.

### Microstructure

During the same natural window verify:

```text
service active
heartbeat fresh
aggTrade events increasing
depth events increasing
event/receive timestamps sane
sequence continuity healthy
partition integrity healthy
no silent heartbeat-thread death
no unresolved SQLite-lock failure
```

If the natural observation window has not elapsed, report `FORWARD_DATA_INSUFFICIENT`. Never fabricate completion.

Produce when evidence exists:

```text
deliverables/v0.3.21/POST_START_SUCCESSOR_HEALTH.json
```

## 12. Explicit handling of local shutdown/sleep/network gaps

This version must preserve the following rule:

```text
shutdown/sleep/network outage
        -> real missing Forward interval
        -> gap recorded honestly
        -> no reconstruction/backfill
        -> frozen gap gate evaluated
        -> terminal campaign if gate is breached
        -> only a fresh preregistered successor may continue formal accumulation
```

`Persistent=true` may resume timers after startup but must never be described as recreating true-PIT observations missed while the machine was unavailable.

Add documentation/tests preventing this semantic confusion.

## 13. Tests and engineering acceptance

Run at minimum:

```bash
ruff check .
mypy src
pytest
python -m compileall src tests tools
```

Run configured CI across:

```text
Python 3.11
Python 3.12
Python 3.13
```

Add direct tests for at least:

```text
terminal registry resolution
terminal restart refusal
active successor resolution
collector/resolver parity
doctor fail-closed behavior
HTTP451 classification
installer stale-campaign protection
WSL/systemd state diagnostics
safe recovery after service interruption
future-start preregistration validation
no Forward backfill
execution remains disabled
Final Holdout remains sealed
```

Do not declare empirical Forward recovery from unit tests alone.

## 14. Required deliverables

Create:

```text
deliverables/v0.3.21/README.md
deliverables/v0.3.21/TERMINAL_STATE_RECONCILIATION.json
deliverables/v0.3.21/LOCAL_RUNTIME_RESILIENCE_REPORT.json
deliverables/v0.3.21/LOCAL_FORWARD_PREFLIGHT.json
deliverables/v0.3.21/V0.3.21_FORWARD_LOCAL_RECOVERY_REPORT.md
```

If fresh successor preregistration becomes legitimately eligible:

```text
deliverables/v0.3.21/SUCCESSOR_PREREGISTRATION_MANIFEST.json
```

After natural post-start evidence exists:

```text
deliverables/v0.3.21/POST_START_SUCCESSOR_HEALTH.json
```

Every report must distinguish:

```text
CODE_VERIFIED
LOCAL_RUNTIME_VERIFIED
NETWORK_VERIFIED
FORWARD_EMPIRICALLY_VERIFIED
NOT_YET_VERIFIED
```

Do not call something verified when only simulated/unit-test evidence exists.

## 15. Git lineage

Use one short-lived implementation branch. The existing stage branch may be used if it remains the only active v0.3.21 writer branch.

Preserve evidence-significant ordering:

```text
accepted main
 -> revised v0.3.21 protocol freeze
 -> state reconciliation + local resilience implementation
 -> tests / CI
 -> real local preflight evidence
 -> fresh successor preregistration commit (only if eligible)
 -> future fixed start boundary
 -> natural Forward evidence
 -> formal v0.3.21 result commit
```

The successor preregistration commit must precede its future start boundary.

Do not squash away evidence-significant ordering before review.

## 16. Multi-model review

After implementation reaches an exact reviewable SHA:

1. Gemini-3.8-Flash performs blind independent review.
2. ChatGPT independently reviews the same exact SHA.
3. Neither reviewer edits implementation before its initial verdict.
4. Create:

```text
reviews/v0.3.21/gemini-3.8-flash/REVIEW.md
reviews/v0.3.21/gemini-3.8-flash/REVIEW.json
reviews/v0.3.21/chatgpt/REVIEW.md
reviews/v0.3.21/chatgpt/REVIEW.json
reviews/v0.3.21/RECONCILIATION.md
```

5. Reconciliation table:

```text
Issue | Gemini view | ChatGPT view | Evidence | Severity | Resolution
```

Any unresolved `BLOCKER` or `HIGH` prevents promotion.

## 17. Allowed final verdicts

Use one of:

```text
PASS
PASS_WITH_NONBLOCKING_FOLLOWUPS
REPAIR_REQUIRED
FORWARD_DATA_INSUFFICIENT
```

`PASS` for this stage requires at minimum:

```text
v0.3.20 terminal states canonically reconciled
terminal campaigns cannot silently restart
collector/resolver parity fixed
local WSL/systemd recovery hardening verified
Forward Doctor/preflight healthy
fresh successors preregistered before future start, if preregistration occurred
minimum natural recovery evidence passes, if enough wall-clock time elapsed
CI passes
execution remains DISABLED
Final Holdout remains SEALED
no unresolved multi-model BLOCKER/HIGH
```

If engineering is correct but the local network/host cannot currently produce trustworthy Forward data, `FORWARD_DATA_INSUFFICIENT` is the correct result.

## 18. Explicit non-goals

Do NOT in v0.3.21:

```text
provision or migrate to VPS/cloud infrastructure
buy or configure paid cloud services
search for new alpha
train Transformer signal models
increase symbolic-search budget
reopen official-derivatives symbolic family
touch Final Holdout
optimize H38 after seeing outcomes
introduce directional LONG/SHORT runtime
implement automated orders
enable exchange trading credentials
weaken gap gates to make local hosting look healthier
```

The objective is:

```text
make the current local Forward pipeline internally consistent,
fail closed,
recover safely,
and accumulate trustworthy Forward evidence whenever the host is actually available
```

not:

```text
pretend the local machine is 24x7 infrastructure
```

## 19. Required final implementation-agent response

Report:

```text
1. branch
2. exact HEAD SHA
3. base SHA
4. revised protocol/preregistration SHA(s)
5. files changed
6. terminal state reconciliation
7. systemd/runtime fail-closed changes
8. collector/resolver parity result
9. Windows/WSL lifecycle/resilience result
10. Forward Doctor result
11. network/source reachability result
12. successor IDs/start boundary, if legitimately preregistered
13. natural Forward slot counts, if elapsed
14. microstructure status
15. ruff result
16. mypy result
17. pytest result
18. compileall result
19. CI run IDs/status
20. execution safety state
21. Final Holdout access count
22. remaining blockers
23. final verdict
```

End explicitly with:

```text
execution = DISABLED
auto_execute = false
qualified_direction_engine = NONE
runtime_maximum = OPPORTUNITY_ONLY
final_holdout = SEALED
```
