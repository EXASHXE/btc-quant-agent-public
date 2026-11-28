# TASK-S5-D1-HEAVY-CLOSEOUT-20261128 (Run 5 — Owner-Approved Threshold Override)

> PUBLIC HISTORICAL TASK CONTRACT — private identifiers omitted; not new authorization.

Executor: Codex GPT-6.2 Sol High (reuse thread [private thread ID omitted], Run 5).
Accountable: Sol WEB | Independent QA: Neon WEB.
Status: OWNER_CONFIRMED_T3_DISPATCH (Owner explicitly approved on 2026-11-28 UTC+8 lowering the D1 pre-start MemAvailable floor to 1,000 MiB and raising the heavy-job peak RSS target ceiling by +500 MiB to 1,500 MiB, then launching Run 5 immediately).

## 1. Exact Baseline & Zero-Edit Source Scope
- Worktree: [private isolated worktree]
- Branch: feat/s5-unified-release-20261127-r2
- Exact Required HEAD: 0d539f6cd29681c703a7196209cda770250b84ee (verify clean working tree before and after).
- Authorized Repository Write Set: ZERO repository edits. If any regression, wheel, or RECORD check fails, STOP immediately, preserve logs, and return BLOCKED_WITH_EVIDENCE.
- Evidence Root (0700/0600): /tmp/quant-wave-d1-hermes-20261128/ (preserve prior targeted receipts; write new wheels, heavy logs/JUnit, updated RELEASE_MANIFEST.json, RESOURCE_GATE.json, REGRESSION_SUMMARY.json, HANDOFF_RECEIPT.md, SHA256SUMS).

## 2. Owner-Approved Resource Contract (Run 5 Override)
- Acquire shared cooperative flock /tmp/quant-wave-d-heavy.lock (verify regular file, trusted owner, stable inode; never unlink/recreate while held).
- Owner-approved pre-start floor: **MemAvailable >= 1,000 MiB (1,024,000 KiB)** (overriding the prior 1,200 MiB floor that caused Run 4 RESOURCE_HOLD at 1,122.1 MiB; update your launch-gate check accordingly and record `threshold_kib: 1024000` plus `owner_override: true` in RESOURCE_GATE.json).
- Owner-approved cooperative peak RSS target ceiling: **<= 1,500 MiB** (raised +500 MiB from 1,000 MiB; single worker, monitor actual RAM/swap/RSS; do NOT claim OS-enforced memory limits).
- Do NOT modify host swap/memory/WSL config or kill any processes. If MemAvailable < 1,000 MiB or lock is unsafe, return RESOURCE_HOLD.
- Run all builds, installs, and tests inside isolated loopback-only network namespace (unshare -n), temporary HOME, private scratch mounts, and repository audit hook.
- Strictly prohibited: live market/provider/Feishu calls, credential/private chat/memory/holdout access, deployment/restart/timers, merge/push/tag, or modifying frozen B2/Hermes core.

## 3. Required Execution Steps
1. Verify HEAD == 0d539f6cd29681c703a7196209cda770250b84ee, exact 16-path diff vs 03af5397311641b042daef0b808047fed0fcc18e, and frozen source SHA256s.
2. Acquire /tmp/quant-wave-d-heavy.lock (with MemAvailable >= 1,000 MiB), build all four 1.0.0rc2 wheels offline (quant-transport, quant-core, quant-research, quant-agent-bridge), install into a fresh offline venv, and verify:
   - ZIP RECORD vs source bytes, installed RECORD vs wheel bytes, pip check == 0, CLI entrypoints, managed Hermes asset hashes, and synthetic local_upgrade plan/apply/rollback.
   - Compare quant-core, quant-transport, quant-research wheels against 03af5397 closeout pins (recording exact SHA256s).
3. Under /tmp/quant-wave-d-heavy.lock, run full repository pytest + explicit infrastructure/s6-radar/test_run_radar.py (single worker, 0 failures, 0 unexpected skips), recording JUnit XML, full log, and measured peak RSS.
4. Keep production dispatch disabled with all three verified blockers (PROACTIVE_PRINCIPAL_BINDING_UNVERIFIED, PROACTIVE_MEMORY_ISOLATION_UNVERIFIED, UPSTREAM_HARD_BUDGET_UNENFORCEABLE); actual provider/cache/billing/runtime NOT_RUN; Field/recurrence NOT_AUTHORIZED.
5. Seal updated RELEASE_MANIFEST.json (with exact 4-wheel, RECORD, asset, and source SHA256s), RESOURCE_GATE.json, REGRESSION_SUMMARY.json, HANDOFF_RECEIPT.md, and verified SHA256SUMS.

## 4. Stop Conditions & Disposition
Return READY_FOR_INDEPENDENT_WEB_QA_WITH_BOUNDED_OPERATIONAL_BLOCKER, RESOURCE_HOLD, or BLOCKED_WITH_EVIDENCE.
