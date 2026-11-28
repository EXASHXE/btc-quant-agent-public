# TASK-S5-D1-HEAVY-CLOSEOUT-20261128 — Wave D1 Heavy Regression & 4-Wheel Closeout (P0)

> PUBLIC HISTORICAL TASK CONTRACT — private identifiers omitted; not new authorization.

Executor: Codex GPT-6.2 Sol High (reuse thread [private thread ID omitted], Run 4).
Accountable: Sol WEB | Independent QA: Neon WEB.
Status: OWNER_CONFIRMED_T3_DISPATCH (Owner explicitly approved TASK-S5-D1-HEAVY-CLOSEOUT-20261128 on 2026-11-28 UTC+8 for priority Wave D1 heavy regression and 4-wheel closeout).

## 1. Baseline & Strict Write Set
- Worktree: [private isolated worktree]
- Branch: feat/s5-unified-release-20261127-r2
- Exact Required HEAD: 0d539f6cd29681c703a7196209cda770250b84ee (clean worktree pre and post).
- Authorized Repository Write Set: ZERO repository edits. If any regression, wheel, or RECORD check fails, STOP immediately, preserve logs, and return BLOCKED_WITH_EVIDENCE.
- Evidence Root (0700/0600): /tmp/quant-wave-d1-hermes-20261128/ (preserve prior targeted receipts; add wheels, heavy logs/JUnit, updated RELEASE_MANIFEST.json, RESOURCE_GATE.json, REGRESSION_SUMMARY.json, HANDOFF_RECEIPT.md, SHA256SUMS).

## 2. Resource & Offline Safety Contract
- Acquire shared cooperative flock /tmp/quant-wave-d-heavy.lock (verify regular file, trusted owner, stable inode; never unlink/recreate while held). Priority 1 of 3 (run before D2/D3 heavy work).
- Require MemAvailable >= 1200 MiB pre-start, peak RSS target <= 1000 MiB, single worker, monitor RAM/swap; if unsafe, return RESOURCE_HOLD without modifying host swap/memory or killing processes. No OS-enforced memory limit claims.
- Run all builds/installs/tests in loopback-only network namespace (unshare -n), temporary HOME, private scratch mounts, and repository audit hook.
- Prohibited: live market/provider/Feishu calls, credential/private chat/memory/holdout access, deployment/restart/timers, merge/push/tag, or modifying frozen B2/Hermes core.

## 3. Required Steps & Acceptance Tests
1. Verify HEAD == 0d539f6cd29681c703a7196209cda770250b84ee, exact 16-path diff vs 03af5397311641b042daef0b808047fed0fcc18e, and frozen source SHA256s.
2. Under /tmp/quant-wave-d-heavy.lock, build all four 1.0.0rc2 wheels offline, install into a fresh offline venv, and verify ZIP RECORD vs source bytes, installed RECORD vs wheel bytes, pip check == 0, CLI entrypoints, managed Hermes asset hashes, and synthetic local_upgrade plan/apply/rollback.
3. Under /tmp/quant-wave-d-heavy.lock, run full repository pytest + explicit infrastructure/s6-radar/test_run_radar.py (single worker, 0 failures, 0 unexpected skips), recording JUnit XML, full log, and measured peak RSS.
4. Keep production dispatch disabled with all three verified blockers (PROACTIVE_PRINCIPAL_BINDING_UNVERIFIED, PROACTIVE_MEMORY_ISOLATION_UNVERIFIED, UPSTREAM_HARD_BUDGET_UNENFORCEABLE); actual provider/cache/billing/runtime NOT_RUN; Field/recurrence NOT_AUTHORIZED.
5. Seal updated RELEASE_MANIFEST.json, RESOURCE_GATE.json, REGRESSION_SUMMARY.json, HANDOFF_RECEIPT.md, and SHA256SUMS.

## 4. Stop Conditions & Disposition
Return READY_FOR_INDEPENDENT_WEB_QA_WITH_BOUNDED_OPERATIONAL_BLOCKER, RESOURCE_HOLD, or BLOCKED_WITH_EVIDENCE.
