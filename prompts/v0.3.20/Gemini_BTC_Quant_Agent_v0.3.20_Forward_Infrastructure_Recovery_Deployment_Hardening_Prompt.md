# BTC Quant Agent v0.3.20 — Forward Infrastructure Recovery & Deployment Hardening

## Role
You are the implementation/reliability owner for `EXASHXE/btc-quant-agent`. You may use Gemini/Antigravity as the coding agent. Work directly in GitHub/WSL, keep all calculations deterministic, and do not alter strategy conclusions to obtain a preferred result.

## Starting point
Branch: `gemini/v0.3.20-forward-infrastructure-recovery-deployment-hardening`
Base v0.3.19 delivery HEAD: `eaa75330854d54e9967f3c0c0446bd6d4b34a76e`
Formal v0.3.19 implementation SHA: `a26b657379f1b2e0f463c6cd614d4849f1c1b833`

v0.3.19 accepted research result: `STOP_OFFICIAL_DERIVATIVES_SYMBOLIC_FAMILY`; no candidate, no provisional shadow, Final Holdout sealed.

## Why v0.3.20 exists
The v0.3.19 forward-status snapshot shows a genuine operational defect and therefore overrides the normal wait-for-evidence stop rule:
- Derivatives successor: terminal, 162 expected, 126 full, 11 partial, 25 missing, max bad/missing streak 15.
- H36 Opportunity successor: terminal, 136 expected, 49 missed, max miss streak 24, successful scan ratio ~0.6397, zero opportunities.
- Microstructure: stale heartbeat (~31,715 s), although partition integrity was still OK.
- Health state: UNHEALTHY.

These terminal campaigns MUST remain immutable archives. Do not edit, backfill, relabel, delete misses, move starts, or reset their terminal state.

## Primary objectives
1. Root-cause the forward interruptions with evidence from systemd journal, boot/suspend history, process lifetime, WSL lifecycle, network/proxy state and collector logs.
2. Make the collection stack robust to normal process failure and observable across Windows/WSL restarts.
3. Add a deterministic deployment-health contract and a one-command diagnostic/recovery workflow.
4. Pre-register clean successor campaigns/epochs only after the recovery design is committed and verified, using fixed future closed-bar start times.
5. Preserve old terminal campaigns as archives and exclude them from successor formal denominators.
6. Continue to prohibit execution, Final Holdout access and Alpha reinterpretation.
7. Prepare a Linux/VPS deployment profile so the same collectors can run 24x7 outside the laptop, but do not require paid infrastructure or migrate automatically.

## P0 — forensic audit before repair
Create a machine-readable audit that distinguishes at least:
- `WINDOWS_OR_WSL_OFFLINE`
- `SYSTEM_SUSPEND_OR_HIBERNATE`
- `USER_SYSTEMD_NOT_RUNNING`
- `UNIT_DISABLED_OR_NOT_ENABLED`
- `PROCESS_CRASH`
- `NETWORK_OR_PROXY_FAILURE`
- `BINANCE_HTTP_451_OR_REGION_RESTRICTION`
- `TIMER_INVOCATION_MISSED`
- `TIMER_FIRED_BUT_COLLECTION_FAILED`
- `MICROSTRUCTURE_HEARTBEAT_STALE`
- `UNKNOWN`

Evidence sources should include where available:
- `journalctl --user` for all btc-quant units;
- `systemctl --user status/show/list-timers`;
- `journalctl --list-boots`, suspend/resume/reboot logs;
- WSL/systemd state and `/etc/wsl.conf`;
- `loginctl show-user` / linger state;
- network env/proxy configuration without leaking secrets;
- forward SQLite slots and recorded failure classes;
- microstructure heartbeat/lease/session/gap tables.

Do not infer a Windows/WSL shutdown merely from missing data if logs cannot prove it. Assign confidence and evidence references.

## P0 — deployment/restart hardening
### User systemd
Audit all committed units and installers. Ensure installed units are enabled and restart semantics are explicit. Keep service paths configurable rather than silently assuming a different checkout.

Add a command such as:
`quantctl forward-evidence doctor`
that reports, in JSON and readable text:
- WSL/systemd availability;
- all required timer/service enabled/active states;
- next scheduled times;
- latest successful slot/time per chain;
- heartbeat age;
- network/proxy reachability diagnostics;
- disk free space;
- DB/partition writeability;
- current campaign identities and terminal/active state;
- whether execution remains disabled and Holdout sealed.

Add a safe recovery command such as:
`quantctl forward-evidence recover-services`
which may reload/restart/enable required units but MUST NOT rewrite evidence, backfill slots, create campaigns, or change frozen starts.

### Windows/WSL lifecycle
Document and, where safely automatable, support:
- systemd enabled in WSL;
- user-manager/linger behavior where applicable;
- how to verify services return after WSL restart;
- an optional Windows startup mechanism that starts the target WSL distro without interactive login.

Do not silently modify Windows Task Scheduler or OS-wide settings without explicit user action. Provide an idempotent helper/script and exact verification steps instead.

### Resource isolation
Historical research/download jobs must not starve Forward collectors. Add optional controls for research downloader concurrency/bandwidth and document sane defaults. Forward collectors get priority in reliability checks; do not alter market data semantics.

## P0 — immutable archive + successor rules
Archive current terminal chains exactly as-is. Create explicit archived states, e.g.:
- Derivatives v0.3.16 successor => `DATA_QUALITY_TERMINAL_ARCHIVE`
- H36 => `DATA_QUALITY_TERMINAL_ARCHIVE`
- Microstructure v0.3.15 session/campaign => preserve all existing events/gaps; if campaign semantics allow continuation, explain why. If a formal new campaign is required, preregister it; never rewrite prior gaps.

Only after repair tests pass, preregister successors with fixed future UTC starts on valid closed decision boundaries. Config freeze commit MUST precede start.

For derivatives successor keep a comparable quality gate unless a change is justified purely by engineering semantics, never by observed market outcomes:
- minimum_calendar_days = 30
- minimum_fully_available_snapshots = 2500
- minimum_required_field_availability = 0.95
- maximum_consecutive_failed_or_missing_slots = 4
- natural scheduled observations only
- manual/legacy/backfill excluded

For Opportunity successor keep the exact frozen TP/BR detector semantics and movement/control definition. Create a new hypothesis identity such as `H37_OPPORTUNITY_FORWARD_REPLICATION_RECOVERY` only if a clean successor is necessary. Suggested unchanged gate:
- minimum_calendar_days = 30
- minimum_resolved_opportunities = 30
- preferred_resolved_opportunities = 50
- minimum_unique_matched_controls = 100
- minimum_distinct_utc_days = 20
- minimum_successful_scheduled_scan_ratio = 0.95
- maximum_consecutive_missed_decision_slots = 4

Do not reinterpret H35/H36 outcomes.

## P1 — Linux/VPS deployment profile
Add a provider-neutral deployment profile for a normal x86_64 Linux host:
- systemd system or user services;
- Python/venv install/bootstrap;
- network/proxy env file contract;
- persistent data directory;
- log rotation;
- disk-space guard;
- UTC clock/NTP diagnostics;
- immutable daily partition/checksum workflow;
- backup/export hook interface (disabled by default).

Deliver a migration runbook that explains how to start a NEW successor campaign on a new host. Do not copy laptop Forward history and pretend continuity. The old host/campaign remains an archive.

## P1 — monitoring/alert-ready health output
Keep notification backend lightweight and optional. Expose stable structured health JSON suitable for Hermes/Feishu later. Include severity (`HEALTHY/WARN/CRITICAL`) and actionable reason codes. No trading action may be triggered from health alerts.

## Safety invariants
Must remain throughout:
- `strategy = EXPERIMENTAL`
- `qualified_direction_engine = NONE`
- `runtime_maximum = OPPORTUNITY_ONLY`
- `execution = DISABLED`
- `auto_execute = false`
- `final_holdout = SEALED`
- no Binance order submission
- no paper/testnet/live authorization
- no historical writes to Forward stores
- no backfill converted into formal forward success

v0.3.19 result remains stopped: do NOT rerun/increase the official-derivatives symbolic search and do NOT use a Transformer to reopen that stopped family.

## Tests/acceptance
Add tests for:
- terminal archive monotonicity;
- successor fixed-start / pre-start exclusion;
- missed wall-clock slot denominator;
- restart/duplicate invocation idempotency;
- stale heartbeat and lease recovery;
- unknown health failure reason fail-closed;
- service doctor/recover dry-run behavior;
- no evidence mutation by recovery command;
- no Holdout load;
- execution disabled.

Run and report:
- `ruff check .`
- strict `mypy`
- `pytest -q`
- targeted coverage for new reliability modules
- `python -m compileall -q src skill-template/scripts`
- systemd unit verification (`systemd-analyze verify` where available)
- controlled restart test of user services
- if feasible, one WSL restart validation with before/after timestamps; if not feasible from the agent, provide exact user-run verification commands and mark it unverified rather than fabricate evidence.

## Required deliverables
Commit and push all formal deliverables to GitHub under `deliverables/v0.3.20/`:
- `README.md`
- `V0.3.20_FORWARD_INFRASTRUCTURE_RECOVERY_REPORT.md`
- `V0.3.20_NUMERIC_ANSWERS.json`
- `V0.3.20_RECOMMENDATION.md`
- `FORWARD_FAILURE_ROOT_CAUSE_AUDIT.json`
- `TERMINAL_CAMPAIGN_ARCHIVE_AUDIT.json`
- `SUCCESSOR_PREREGISTRATION_STATUS.json`
- `FORWARD_OPERATIONS_HEALTH.json`
- `WSL_RESTART_RECOVERY_AUDIT.json`
- `LINUX_VPS_DEPLOYMENT_READINESS.json`

Large SQLite/raw partitions remain gitignored. Include hashes/provenance for referenced local artifacts.

## Git/PR delivery
- Work only on `gemini/v0.3.20-forward-infrastructure-recovery-deployment-hardening`.
- Preserve history; do not merge to `main`.
- Commit and push code, configs, tests, prompt-preserving history and deliverables.
- Verify remote contents with `git ls-tree -r origin/gemini/v0.3.20-forward-infrastructure-recovery-deployment-hardening deliverables/v0.3.20`.
- Create/update a PR to `main`, leave it open/unmerged.
- Ensure CI passes.

## Final recommendation vocabulary
Use exactly one primary recommendation:
- `FORWARD_INFRASTRUCTURE_RECOVERED_SUCCESSORS_ACCUMULATING`
- `FORWARD_INFRASTRUCTURE_PARTIALLY_RECOVERED_MANUAL_ACTION_REQUIRED`
- `FORWARD_INFRASTRUCTURE_RECOVERY_FAILED`

Do not start v0.3.21 merely for version cadence. After successful recovery, let real Forward time accumulate unless a new operational defect occurs or an independent new-data research family is genuinely ready.