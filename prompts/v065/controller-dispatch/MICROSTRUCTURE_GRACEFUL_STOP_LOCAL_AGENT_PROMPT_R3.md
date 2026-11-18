You are LOCAL Codex Sol Max / Astra High, an independent host-systemd/SQLite operational verifier for quant v0.6.5.

TASK: V065-MICROSTRUCTURE-GRACEFUL-STOP-QUALIFICATION-R3.

Read exact Controller decision at:
/root/workspace/project/crypto-data/_control/MICROSTRUCTURE_GRACEFUL_STOP_CONTROLLER_DECISION_R3.md

Read actual R2 STOP and verify its SHA256:
/root/workspace/project/crypto-data/_control/ACTIVE_DATA_CUTOVER_REPORT_R2.md
SHA256 8da2395ec5efd92f1db2c929c6d48c2b7928eff0708410eb7f09e22ae4e61fd9

Canonical code checkout: /root/workspace/project/quant-0.6.5 on v0.6.5, observed HEAD 12b74b4c2fd3a22a9f4b35dbf331cfb1166aae77. Default no new branch/worktree required. No AGENTS.md/GEMINI.md. No Git code modification.

HARD SCOPE: fix ONLY the R2 microstructure systemd 20-second unsafe SIGKILL escalation. Do NOT repeat R1 or R2 broad inventory, API-health, HEAD review, source authorization or strategy research. SOURCE_QA is still blocked.

1. Fresh readonly verification of exact target unit file SHA256 eaabde7fdfd9074835c5beb655cadefa4e3bc1262718f1e6bcb1bd2bef74980b, effective properties (SIGINT, 20s, SendSIGKILL=yes, PrivateTmp=true, Restart=on-failure), running MainPID and no unexpected drop-ins. Verify source microstructure.py SHA256 e4201e10f10ee8038d1245adca5ec03644ac1b79a9bfdebbfa01a4cc114f88c6 and bounded finally/instance_end/finalize_partitions behavior without reading market rows or mutating original data.
2. Run isolated **synthetic** transient-systemd fixture that matches production PrivateTmp=true and uses a script located outside /tmp in an isolated new scratch directory. Verify SIGINT and a deliberately slow (e.g. 5-second) fake finalize. Test TimeoutStopSec=infinity, SendSIGKILL=no, and nonblocking stop: at 2s observe deactivating+PID alive; at exit observe inactive/dead+result success+exit=0 with no SIGKILL. If safe, verify a second finite watchdog-failure fixture: at a shorter supervisor deadline, STOP_PENDING without sending any extra signal or killing the test process; allow its own clean exit. Remove all synthetic units/scratch only after they fully exit; no daemon left behind.
3. Produce an exact, reversible, scoped proposed drop-in for real btc-quant-microstructure-forward.service. DO NOT INSTALL IT in this qualification task. Preserve the current actual ExecStart/WorkingDirectory/Environment/PrivateTmp/restart/signal, change only TimeoutStopSec=infinity and SendSIGKILL=no. Validate drop-in grammar and static expected effective settings using nonproduction systemd fixture. The original unit file must be byte-identical throughout; don't change production timers/drop-ins/services/reload.
4. Specify supervisor's 30-minute **decision** deadline, with exact UTC start, poll interval <=15s, monotonic time checks, unit state/PID, journal progress, safe success criteria and exact STOP_PENDING_GRACEFUL_EXIT. State plainly that this does NOT bound the real finalization duration. There must be NO SIGKILL, no repeated stop/restart/kill, no automatic resumption if still stopping, no data copy/snapshot/cutover during incomplete shutdown.
5. Define outcome cases: clean exit (service inactive, MainPID=0, Result=success, no children/FDs, no finalization error) → only then eligible for later quiesced snapshot and migration; pending after deadline → preserve original unit in stopping state, timers remain paused, preserve every original byte and report gaps; unexpected failure/Signal/OOM/restart → fail closed with an independently reviewed recovery and no data mutation.
6. Review systemd's exact real semantics and limitations for TimeoutStopSec=infinity, SendSIGKILL=no, Restart=on-failure, PrivateTmp=true. Include a matrix showing which synthetic evidence can and cannot establish safety of 60GB live production finalization and which next step is needed. An unbounded finalizer cannot be declared guaranteed to exit.
7. Save a SINGLE readonly report under
/root/workspace/project/crypto-data/_control/MICROSTRUCTURE_GRACEFUL_STOP_QUALIFICATION_R3.md
with content SHA256, exact test unit names, observed elapsed/status values, hashes, case verdict and reproducible commands. Allowed terminal verdicts:
PASS_NONKILL_STOP_POLICY_SYNTHETIC_ONLY
STOP_NONKILL_STOP_POLICY_UNVERIFIED
STOP_NO_SAFE_NONKILL_RECOVERY

ABSOLUTE NONACTIONS: Do NOT signal/stop/restart/reload/edit the real btc-quant-microstructure-forward service, four legacy timers, legacy Quant-agent source/stores, protected A-line/history, Git repository, credentials, market REST/WS, source-QA collection, account or trading. Do not alter other unrelated systemd units or use a service/fixture that reads live market data.

Expected workflow AFTER an independent R3 PASS (NOT IN THIS TASK): Controller may authorize a separate reversible production drop-in preflight and then a controlled supervised stop, followed only on clean exit by legacy data migration. If 30-minute decision deadline arrives and service still stops, preserve the pending stop and return STOP rather than forcing the exit.

Preserve SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE.

