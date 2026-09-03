# BTC Quant Agent v0.3.21 — Forward Runtime State Reconciliation, Compliant Cutover & Fresh Successor Recovery

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

If `main` has advanced, inspect the new commits and use the latest accepted `main` as the base. Do not silently discard newer accepted work.

Read first:

```text
docs/PROJECT_CONTEXT_HANDOFF.md
docs/MULTI_MODEL_RESEARCH_GOVERNANCE.md

reviews/v0.3.20/gemini-3.8-flash/REVIEW.md

deliverables/v0.3.20/README.md
deliverables/v0.3.20/ACCEPTANCE_REPAIR_REPORT.md
deliverables/v0.3.20/POST_START_SUCCESSOR_HEALTH.json
deliverables/v0.3.20/FORWARD_DOCTOR_REPORT.json

docs/LINUX_VPS_MIGRATION_RUNBOOK.md
docs/FORWARD_DERIVATIVES_OPERATIONS.md
```

This is primarily an **operations / Forward-evidence integrity stage**.

It is NOT a new alpha-search stage.

## 0. Frozen project invariants

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
NO post-hoc signal reversal
NO synthetic historical L2 / OFI / microprice from candles
NO reconstruction of missed true Forward slots
NO deleting failed Forward records
NO moving historical campaign start timestamps
NO resetting terminal campaigns
NO proxy/VPN technique intended to bypass jurisdictional or provider restrictions
```

Historical Forward gaps and failures are evidence and must remain immutable.

## 1. v0.3.20 facts that are now frozen

### Derivatives

`DERIVATIVES_PIT_EPOCH_V0320_001` observed 5 expected slots, 0 fully available, 5 failed, maximum consecutive failure streak 5 versus frozen maximum 4. Therefore it is permanently `TERMINAL_BREACH / COMPROMISED_AT_RISK` and is ineligible for continued formal accumulation.

### Opportunity

`OPPORTUNITY_FORWARD_V0320_20260903T063000Z` / `H37_OPPORTUNITY_FORWARD_REPLICATION_RECOVERY` observed 5 expected scans, 0 successful scans, 5 `MISSED_DECISION_SLOT`, maximum consecutive miss streak 5 versus frozen maximum 4. Therefore it is permanently `TERMINAL_BREACH / COMPROMISED_AT_RISK` and must never be restarted under the same campaign ID.

### Microstructure

Last accepted v0.3.20 evidence showed `MICROSTRUCTURE_CAPTURE_V0315_001 = HEALTHY_COLLECTING`. Do not retroactively mark it failed merely because Derivatives/H37 failed. Any host migration must nevertheless have an explicit provenance boundary.

## 2. Primary objective

v0.3.21 has four objectives, in this order:

```text
A. Reconcile canonical runtime state with the known terminal evidence
B. Make systemd/deployment fail closed against terminal/stale campaign configs
C. Establish a legally and operationally eligible 24x7 Forward collection host
D. Only after C is proven, preregister fresh Derivatives + Opportunity successors
```

Do not start objective D before A-C pass. Do not start a new alpha hypothesis in this version.

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

Reconcile the canonical registries so `DERIVATIVES_PIT_EPOCH_V0320_001` and `OPPORTUNITY_FORWARD_V0320_20260903T063000Z` are represented as immutable terminal chains. Use the actual first gate-breach timestamp derived from existing immutable evidence where available. Do not fabricate a timestamp.

Required semantics must clearly encode terminal/ineligible state, immutable history, and the HTTP451-induced maximum consecutive gap/miss breach. Do not set `superseded_by` to a future successor until that successor has actually been preregistered.

Add direct tests proving:
1. terminal v0.3.20 chains cannot resolve as active;
2. terminal chains cannot be selected by normal scheduled collection;
3. terminal state is irreversible;
4. no terminal history is deleted or rewritten.

Produce:

```text
deliverables/v0.3.21/TERMINAL_STATE_RECONCILIATION.json
```

## 4. Phase B — Remove stale/unsafe runtime campaign wiring

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

### B1. Terminal campaign restart risk

The unified installer must not blindly activate a collector whose canonical active campaign/epoch is terminal. Make installation/activation fail closed. A valid implementation may use registry-driven active resolution or another deterministic mechanism, but version-specific stale static paths must not make a terminal chain silently resume.

At minimum:

```text
terminal campaign -> collector activation refused
no eligible active/preregistered campaign -> collector remains stopped
health/doctor may still run
```

Microstructure behavior should be handled independently from terminal Derivatives/H37 state.

### B2. Opportunity collector/resolver mismatch

Audit for the possibility that `collect-once -> campaign A` while `resolve -> campaign B`. Resolve this structurally. Collector and resolver for a given active Opportunity campaign must resolve the exact same campaign config/ID. Add a direct automated test that fails if collector and resolver are wired to different formal campaigns. Do not merely replace one hard-coded filename with another while leaving the architectural mismatch possible.

## 5. Phase C — Forward Doctor becomes the deployment gate

`quantctl forward-evidence doctor` must be the authoritative preflight before a new successor is registered or activated.

Audit and harden it so that it verifies at minimum:

```text
Git / deployment identity
systemd state
user linger
host clock sanity
storage writability
SQLite integrity
microstructure partition health
network configuration
required REST reachability
required WebSocket reachability where practical
HTTP451 / legal-restriction failure
active/terminal registry consistency
stale campaign wiring
```

A doctor result must fail closed when the source is legally or operationally unavailable, HTTP451 is observed, required endpoints are unavailable, registry says active but empirical terminal gate is breached, collector/resolver campaign IDs disagree, required storage is not writable, or microstructure daemon is stale when expected to be running.

Do not equate `non-US IP == legally eligible`. Geography alone is not sufficient. Update documentation so the environment/data source must be both legally/provider eligible and operationally reachable. Do not introduce VPN/proxy bypass instructions.

## 6. Phase D — 24x7 Linux host cutover

Preferred production topology remains:

```text
24x7 Linux host
    -> Forward collectors
    -> immutable Forward stores
    -> off-host backup

local workstation
    -> development
    -> historical research
    -> review
```

Use `deploy/linux-vps/` and `docs/LINUX_VPS_MIGRATION_RUNBOOK.md` as a starting point, correcting any assumptions contradicted by this prompt.

Two valid outcomes exist:
- Real eligible host available: perform deployment and capture evidence.
- No eligible host available: complete repository hardening but stop before successor preregistration and report `CUTOVER_BLOCKED_NO_VERIFIED_ELIGIBLE_HOST`.

Do not create fake healthy reports and do not preregister a successor merely to complete the version.

## 7. Preserve old Forward evidence during migration

Never merge or normalize old records in a way that erases provenance. Before migration record source/destination host identity, old campaign IDs, last source-host observation timestamp, first destination-host observation timestamp, database checksums/partition manifests where practical, network/egress diagnostic result, deployed Git SHA, Python version, and service/config hashes.

Create:

```text
deliverables/v0.3.21/HOST_MIGRATION_MANIFEST.json
```

Existing `derivatives.sqlite3`, `opportunity_shadow.sqlite3`, and `microstructure/` may be copied as immutable evidence. No historical rows may be altered to hide downtime.

## 8. Microstructure host migration boundary

Because `receive_time_ms` and true local Forward provenance are host-dependent, do not silently make a new host appear identical to the old WSL capture environment. Audit the frozen microstructure protocol.

If the existing protocol does not explicitly establish that migration to a materially different host/network environment can remain one provenance campaign, create a clean successor capture campaign such as:

```text
MICROSTRUCTURE_CAPTURE_V0321_001
```

with a fixed preregistered future start boundary. The old `MICROSTRUCTURE_CAPTURE_V0315_001` must remain immutable. Use an explicit migration/supersession state rather than falsely marking a healthy campaign failed.

## 9. Pre-successor operational proof

Before preregistering any v0.3.21 Derivatives or Opportunity successor, obtain a real preflight result from the intended production collector host.

Required state:

```text
forward-evidence doctor = HEALTHY
required network endpoints = reachable
HTTP451 = absent
registry consistency = valid
storage = healthy
systemd = healthy
linger = enabled
microstructure path = healthy/ready
```

Record:

```text
deliverables/v0.3.21/FORWARD_CUTOVER_PREFLIGHT.json
```

If it does not pass, stop.

## 10. Fresh successor preregistration

Only after the real production host passes preflight may new successors be created.

### Derivatives

Use a fresh immutable ID:

```text
DERIVATIVES_PIT_EPOCH_V0321_001
```

Do not weaken `maximum_consecutive_failed_or_missing_scheduled_slots = 4`.

### Opportunity

Use a fresh successor, e.g.:

```text
H38_OPPORTUNITY_FORWARD_REPLICATION_POST_CUTOVER
OPPORTUNITY_FORWARD_V0321_<FIXED_START_UTC>
```

H38 is an operationally clean replication successor to H37, not a new directional hypothesis. Keep `direction_claim = NONE` and runtime `OPPORTUNITY_ONLY`. Keep TP/BR detector semantics and movement-outcome hypothesis unchanged unless independently reviewed preregistration explicitly justifies a modification.

## 11. Successor start-time rule

Do not hard-code a start timestamp in this prompt.

After code is complete, tests pass, deployment host is healthy, and preflight evidence is captured, select deterministically:

```text
start = first fully closed UTC 15m boundary
        at least 30 minutes after the preregistration commit
```

Commit successor config and manifest before the start timestamp. Record preregistration SHA, commit timestamp, campaign start UTC, config hashes and parent/terminal IDs in:

```text
deliverables/v0.3.21/SUCCESSOR_PREREGISTRATION_MANIFEST.json
```

No moving the boundary after commit.

## 12. Natural post-start acceptance evidence

Do not simulate or backfill this evidence. For initial operational recovery qualification, require at least 8 consecutive natural 15-minute slots after the new start boundary.

### Derivatives initial recovery gate

```text
expected = 8+
recorded = expected
fully available required snapshots = expected
failed = 0
missing = 0
required-field coverage = 100%
maximum consecutive bad/missing = 0
```

### Opportunity initial recovery gate

```text
expected scans = 8+
successful scans = expected
MISSED_DECISION_SLOT = 0
market_data_health = OK
observations durably stored
collector campaign ID = resolver campaign ID
```

This only establishes `HEALTHY_ACCUMULATING`; it does not statistically qualify H38.

### Microstructure initial recovery gate

Verify service active, heartbeat fresh, aggTrade/depth counts increasing, timestamps sane, sequence continuity healthy, partition integrity healthy, no silent heartbeat-thread death, and no unresolved SQLite-lock failure.

If the natural window has not elapsed, report `FORWARD_DATA_INSUFFICIENT`. Do not fabricate completion.

## 13. Resolver verification

Verify Opportunity outcome resolution separately. Collector and resolver must share exactly one active campaign; outcomes use only data after the original Forward decision; reference price semantics remain causal; ATR remains the frozen ATR observed at scan time; 240m/480m outcomes are resolved only after maturity; missed observations are never reconstructed.

Add deterministic tests for immature vs mature observations.

## 14. Runtime health semantics

Update `quantctl forward-evidence health` and `quantctl forward-evidence doctor` so operational states clearly distinguish, or equivalently type:

```text
HEALTHY
HEALTHY_ACCUMULATING
PREREGISTERED_NOT_STARTED
FORWARD_DATA_INSUFFICIENT
TERMINAL_BREACH
NETWORK_INELIGIBLE
CONFIGURATION_INCONSISTENT
SERVICE_UNHEALTHY
```

Historical terminal chains must remain visible without contaminating the status of a fresh successor.

## 15. Deployment installer requirements

Harden `deploy/systemd/install-all-forward-services.sh` so a fresh machine cannot accidentally run stale terminal campaigns.

Expected behavior:

```text
install unit definitions
    -> run/require preflight
    -> resolve eligible active/preregistered campaign
    -> only then enable corresponding collectors
```

Microstructure and health may have separate lifecycle handling.

## 16. Tests and engineering acceptance

Run at minimum:

```bash
ruff check .
mypy src
pytest
python -m compileall src tests tools
```

Run configured CI across Python 3.11, 3.12 and 3.13.

Add direct tests for terminal registry resolution, terminal restart refusal, active successor resolution, collector/resolver campaign parity, doctor fail-closed behavior, HTTP451 classification, installer stale-campaign protection, migration provenance, future-start preregistration validation, no Forward backfill, execution disabled, and Final Holdout sealed.

Do not declare PASS based only on unit tests if real Forward network recovery has not been demonstrated.

## 17. Required deliverables

Create:

```text
deliverables/v0.3.21/README.md
deliverables/v0.3.21/TERMINAL_STATE_RECONCILIATION.json
deliverables/v0.3.21/HOST_MIGRATION_MANIFEST.json
deliverables/v0.3.21/FORWARD_CUTOVER_PREFLIGHT.json
```

If successor preregistration becomes eligible:

```text
deliverables/v0.3.21/SUCCESSOR_PREREGISTRATION_MANIFEST.json
```

After natural post-start slots exist:

```text
deliverables/v0.3.21/POST_START_SUCCESSOR_HEALTH.json
```

Also produce:

```text
deliverables/v0.3.21/V0.3.21_FORWARD_RECOVERY_REPORT.md
```

Every report must distinguish `CODE_VERIFIED`, `DEPLOYMENT_VERIFIED`, `NETWORK_VERIFIED`, `FORWARD_EMPIRICALLY_VERIFIED`, and `NOT_YET_VERIFIED`.

## 18. Git lineage

Use the short-lived implementation branch:

```text
agent/v0.3.21-forward-recovery-cutover
```

Preserve evidence-significant ordering:

```text
main
 -> v0.3.21 protocol / acceptance freeze
 -> runtime-state reconciliation + engineering implementation
 -> tests / CI
 -> real host preflight evidence
 -> fresh successor preregistration commit
 -> future fixed start boundary
 -> natural Forward evidence
 -> formal v0.3.21 result commit
```

The successor preregistration commit must precede its future start boundary. Do not squash away evidence-significant ordering before review.

## 19. Multi-model review

After implementation reaches an exact reviewable SHA:
1. Gemini-3.8-Flash performs blind independent review.
2. ChatGPT independently reviews the same SHA.
3. Neither reviewer edits implementation before its initial verdict.
4. Create review artifacts under `reviews/v0.3.21/` for Gemini, ChatGPT and reconciliation.
5. Any unresolved BLOCKER/HIGH prevents promotion.

## 20. v0.3.21 allowed final verdicts

Use one of:

```text
PASS
PASS_WITH_NONBLOCKING_FOLLOWUPS
REPAIR_REQUIRED
FORWARD_DATA_INSUFFICIENT
```

`PASS` requires terminal v0.3.20 states canonically reconciled; no terminal campaign can silently restart; collector/resolver parity fixed; eligible 24x7 host verified; Forward Doctor healthy before preregistration; fresh successors preregistered before future start; minimum natural post-start recovery evidence passes; CI passes; execution remains disabled; Final Holdout remains sealed; and no unresolved multi-model BLOCKER/HIGH.

If code is correct but no verified eligible collection environment exists, `FORWARD_DATA_INSUFFICIENT` is the correct result.

## 21. Explicit non-goals

Do not in v0.3.21 search for new alpha, train Transformer signal models, increase symbolic formula search budget, reopen the official derivatives symbolic family, touch Final Holdout, optimize H38 after seeing results, introduce directional LONG/SHORT runtime, implement automated orders, enable Binance trading credentials, or optimize for a positive strategy result.

The objective is:

```text
make Forward evidence trustworthy again
```

not:

```text
find a trade
```

## 22. Required final response from implementation agent

Report branch, exact HEAD SHA, base SHA, protocol/preregistration SHAs, files changed, terminal-state reconciliation, runtime/systemd fixes, collector/resolver parity, deployment host status, Forward Doctor result, network eligibility/reachability result, successor IDs/start boundary if legitimately preregistered, natural Forward slot counts if elapsed, microstructure status, ruff/mypy/pytest/compileall results, CI run IDs/status, execution safety state, Final Holdout access count, remaining blockers and final verdict.

End explicitly with:

```text
execution = DISABLED
auto_execute = false
qualified_direction_engine = NONE
runtime_maximum = OPPORTUNITY_ONLY
final_holdout = SEALED
```
