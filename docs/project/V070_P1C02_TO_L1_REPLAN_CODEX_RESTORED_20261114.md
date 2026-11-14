> **CONTROLLER SCOPED GATE — 2026-11-14:** P1C02 Custody v2 Sol software contract is accepted **only in synthetic, disposable L0**: `ACCEPT_P1C02_SYNTHETIC_L0_SOFTWARE_SCOPED_WITH_WAL_HOLD`. Controller WSL 220 PASS/2 Windows-only SKIP/58 subtests; worker Windows native 222 PASS/0 SKIP; F01/F03 and F02 T0/T1/T2/ACK ordinary-writer tests green. Runtime `SQLITE_WAL_ENGINE_NOT_QUALIFIED` continues on Windows SQLite 3.50.4 and WSL 3.45.1 pending independently verified fixed source. Permission to **implement detached P1C03 synthetic disposable retention simulation** is now available as a new prompt-only L0 phase; do not treat this as approval for production retention, live Source, Feishu or P1C04. Separate Sol SQLite WAL runtime proof task also remains pending. See [P1C02 scoped acceptance](V070_P1C02_V2_SOFTWARE_SCOPED_ACCEPTANCE_WAL_HOLD_20261114.md).

# Quant v0.7.0 — Post-P1C01 Recovery Plan With Astra / Sol / Hydrogen (2026-11-14)

**Owner update:** Codex quota is restored. **Routing priority:** Codex GPT Astra = complex architecture and independent architectural challenge; Codex GPT Sol = primary integration and risk-bearing implementation; Gemini 4 Hydrogen = bounded tests, fixtures, documentation, and mechanical isolated tasks; Controller 0-C = independent acceptance, release gates; ChatGPT 1-A = owner-facing project strategy. **All assignments below are PROMPT-ONLY and NOT DISPATCHED.**

## 0. Verified state, not executor self-report

- Q0A5 whole synthetic L0: `ACCEPT_Q0A5_FULL_L0_OFFLINE_SCOPED`.
- P1A Windows localized clock decoding: `ACCEPT_P1A_DECODE_ONLY_OFFLINE_SCOPED`, no real UTC.
- P1B Source/Clock ADR: designed; only offline implementation permitted.
- P1C01 P1C01 FIX02 (five-TF, quotes, UTC/window, requests): `ACCEPT_P1C01_FULL_OFFLINE_SCOPED` after F01–F05.
- **P1C02 Source-state SQLite sidecar: `NEEDS_SPECIFIC_FIX`**, NOT accepted. Independently reproduced:
  - F01: `recover_on_restart(..., verify_bundles=False)` returns replayable even when raw is missing.
  - F02: mutation after sealed-bundle verify but before SQLite COMMIT yields immediate `COMMITTED` (TOCTOU).
  - F03: genuine Q0A4 stage bundle for an unrelated scan can commit a P1C02 candidate and recover as verified (cross-schema identity gap).
- P1C02 author Windows native 161 PASS/0 SKIP; Controller independent WSL 160 PASS/1 Windows-only SKIP; originals Q0A5 287/287, P1A 308/308, P1C01 inherited 162/162 SHA match. Passing regression does **not** close F01–F03.
- Read-only product: Binance USDT-M, intended 2–12h human trades; 1D context, 4H regime, completed 1H setup, completed 15m trigger, 5m and current quote; eventually Feishu human alert, never auto orders. Source/Feishu/Alpha/execution all remain unqualified/disabled.

## 1. Assignment policy (restored capacity)

| Role | Exclusive responsibility | Forbidden claims / duties |
|---|---|---|
| **Astra, architect** | Cross-resource commit/custody semantics, Source UTC/provenance architecture, retention-vs-recovery policy, integration graph, acceptance design and red-team review of Sol patch | Do not silently edit implementation, self-accept or enable real L1 |
| **Sol, primary coder** | F01–F03 P1C02 core repair, SQLite/NTFS recovery, P1C03 custody/retention implementation, P1C04 TLS mock integration, subsequent disabled Source adapter | No independent architecture override, simultaneous frozen code edits or real egress |
| **Gemini 4 Hydrogen, bounded engineer** | Separate tests-only checkout: adversarial fixtures, test harness, scenario matrices, log comparison, exact docs and mechanical code after Sol architectural decomposition | No editing Sol's live workspace; no cross-resource trust decisions, Source/Producer/Outbox live changes or author self-acceptance |
| **Controller 0-C** | Single queue authority, integration review, independent regression/falsification and signed scoped acceptance | No conflation of synthetic test PASS with live Source admission |
| **ChatGPT 1-A** | Progress/roadmap, product economics readiness, schedule and Owner handoff | Does not compete with Controller task queue |

Do not demand per-run SHA-256 or routine test authorization from Owner. Tests, isolated coding and evidence receipts are ordinary delegated implementation work. Still separately scope genuine public-network acquisition, Feishu sends, host time/service changes or private operations.

## 2. Critical path and parallel task DAG

### Wave 0 — CURRENT: close P1C02 findings

**Astra A0 `V070-ASTRA-P1C02-CUSTODY-ADR02-01`** (READ-ONLY design, parallel): inspect actual `p1c02_source_state.py`, F01–F03 Controller findings; give precise fail-closed algorithm for F02:
- Admit that SQLite and filesystem are not a single transaction. Avoid a false guarantee against arbitrary external writers; specify immutable sealed snapshot ownership, durable incident states, exact byte/hash revalidation at bounded checkpoints, post-COMMIT readback before an accepted return, race limits, idempotent replay and verified restart requirements.
- Reject Q0A4 schema as cycle evidence without formally approved mapping, retaining independent standalone Q0A4 audit.
- Verify P1C03 retention with P1C02 restart: after lawful expiration, no replay of expired raw, but immutable identity/digest/tombstone and audit retained; distinguish expiration from tampering and legal scope.
- Deliver design and challenge/decision cases. No live data and no self-sign.

**Sol S0 `V070-SOL-P1C02-F01F03-THEN-F02-FIX01`** (main coder): implement strict F03 schema admission and F01 unverified restore rejection immediately, plus fail-first F02. **Integrate the F02 solution only after reviewing Astra A0 ADR** and resolving any contradiction with Controller, then run Windows fixed-NTFS + WSL test suites and real `os._exit` crash races. Work in one isolated P1C02 branch/worktree. Do not touch frozen Q0A5/P1A/P1C01 or existing q0bc_v2.

**Hydrogen H0 `V070-HYDROGEN-P1C02-NEGATIVE-MATRIX-01`** (strictly tests-only, parallel): in separate checkout only, create executable reproducer scenarios for F01–F03, include genuine unrelated Q0A4 bundle and restart validation, hook-time raw mutation and non-author tests; include malformed/collision/retention-boundary future cases. Hand the tested fixtures to Sol/0-C. Do not patch Source state code or edit Sol's workspace.

**0-C C0:** independent compare, selective fuzz/replay, Windows evidence review and WSL rereun; `ACCEPT_P1C02_OFFLINE_SCOPED` or focused blocker. F02 must not be marked solved merely by tests that only mutate via a cooperative hook.

**Parallel coordination**: Astra reads source while Sol works on F01/F03 and Hydrogen writes separate tests-only directory; Sol alone owns production code. The initial overlap must not include Astra and Sol modifying same files.

### Wave 1 — offline durability and integration (only after P1C02 scoped acceptance)

**Astra A1**: ADR for bounded 24h raw retention, escrow/ledger/tombstone policies, source/Outbox idempotency and no false replay after lawful purge. Account for `recover_on_restart()` historically checking every COMMITTED raw blob, and whether legitimate expiry should be status `EXPIRED_EVIDENCE_NO_REPLAY` vs untrusted corruption; never quietly mark `SOURCE_QUALIFIED`.

**Sol S1 / P1C03:** implement separate synthetic-only raw retention index and purge simulation (max 24h raw under isolated writable test roots only); use manifest allowlist, reject symlink/junction/reparse traversal; preserve accepted evidence; protect SQLite identity/Bar fingerprints and rule out raw resurrection. Offline Windows/WSL tests.

**Hydrogen H1:** generate edge-case fixtures (23h59m, 24h, 24h+1ms, tampered retention anchors, time drift, reboot, read-only ACL, symlink/junction, fixture survival) and audit docs. No destructive operations outside disposable roots.

### Wave 2 — local Source/E1/Shadow integration (after P1C03 acceptance)

**Astra A2:** approve a strictly disabled mock-integration contract, Source clock provenance, quote-vs-reference freshness, 1D/4H/1H/15m/5m completed-bar causality, and read-only identity bridging; assess difference between `PUBLIC_DIAGNOSTIC_L1_RAW_ONLY` and `PUBLIC_QUALIFIED_L1_CURRENT`. No real credentials or Source network claims.

**Sol S2 / P1C04:** make local loopback/TLS stub integration with mock responses, Source→versioned E1→Shadow/Producer (where separately approved). Ensure `WindowsHttpsTransport(qa=None)` still returns BLOCKED, public bridge remains LIVE_DISABLED, Feishu test provider only, 24 requests/40 planned weight and R1.2 disabled. Crash/restart, stale quote, uncertain clock, missing OI/depth, WSL/Windows E2E.

**Hydrogen H2:** synthetic 5TF and V3.8 scenario expansion, regression & documentation-only verification under exact Sol-built seams. Do not infer Alpha or signal executability.

### Wave 3 — Source readiness and bounded public diagnostics (separate L1 Owner envelope)

**Astra A3:** design independent UTC evidence and public REST rights/region/clock/budget gate, safe split of unqualified diagnostic capture vs qualified current Source. Review real-host w32tm Leap=3/Stratum=0/Local CMOS; QPC is elapsed time only. Venue `/fapi/v1/time` is not an independent UTC certificate. Explicitly decide if qualified Source is possible in current Windows/WSL or if new trusted execution host/sync source is required. Do not change host clock without separate grant.

**Sol S3:** offline implement disabled actual Source transport adapter, current-date-only window and validated single-symbol bookTicker + 5TF kline routes, independent clock-proof interface; preserve rights/holdout. Then, only if Owner creates one finite explicit public-read-only L1 envelope, run bounded BTC/ETH/SOL raw-only canary and audit. No Feishu real sends in Source diagnostics, no order access.

**Hydrogen H3:** non-author QA fixtures, fail-closed right/region/rate/HTTP error matrix; no independent real API probes.

### Wave 4 — usable MVP, monitored read-only signals and prospective quality

**Astra A4:** risk/actionability policy, V3.8 policy evaluation, OI/depth data provenance and >3-symbol expansion, criteria for turning an alert from WATCH to EXECUTABLE (if qualified); distinguish strategy research from prospective Alpha.

**Sol S4:** read-only human Feishu canary only after separate Owner scope (provider-specific outbox/ack/dedup and delivery reliability); no trading. Live Shadow and event sampling with evidence; operational CLI, 5–10min human latency fresh-quote check.

**Hydrogen H4:** dashboards, 69 factor / 21 working + 7 research register, data-dictionary, robustness/consistency fixtures, retrospective summaries (not economic validation), acceptance report formatting.

## 3. Evidence and delivery contract

Each worker's handoff must have: exact isolated workspace, changed-file inventory, deterministic fail-first red/good cases, executable tests and raw results, actual native Windows and WSL counts with skips separated, code/evidence SHA receipt, baseline drift check, exact external request and Feishu count (0 in L0), issue/decision blockers. A task is not accepted until Controller independent review. Existing accepted snapshots are immutable. Roles do **not** need a new Owner approval for each ordinary test, isolated file write or SHA computation.

When models have restored quota, prefer a Sol-owned production code path and Astra-owned narrow decision memo; stop using Hydrogen as the default integrator for critical state/security contracts. Small patch batches reduce regressions and help Owner see real program progress.

## 4. Exit-based milestones (not invented deadlines)

1. **Milestone M-A:** P1C02 F01–F03 fixed, independent scoped acceptance, same SQLite/cycle semantics after restart and no replay without raw evidence.
2. **M-B:** P1C03 retention with correct expiry semantics; P1C04 disabled local Source/E1/Shadow pipeline fully green.
3. **M-C:** independent clock proof and rights feasibility resolved; separate finite L1 diagnostic capture with no qualified signal if UTC unqualified.
4. **M-D:** qualified current read-only Source (if achievable), scoped Feishu canary after explicit authorization, human latency and prospective risk evidence.
5. **M-E:** ≥10 qualified high-liquidity symbols and monitored Factor Registry/Strategy Lab only after the 3-symbol pipeline has achieved meaningful reliability and has no hidden alpha claim.

**Do not let model assignments change the safety/authority baseline:** `SOURCE_BLOCKED=true; SOURCE_QUALIFIED=false; SHADOW_QUALIFIED=false; ECONOMICALLY_VALIDATED=false; ALPHA_CLAIMED=false; execution_authority=false; REAL_FEISHU_SEND=false` unless future *separate* proofs and grants specifically change a named layer.

**IMPORTANT:** The P1C02 worker report proposed converting P1C03 into external UTC+L1 and P1C04 into an online canary. That change was not authorized. Correct sequence remains P1C03 offline retention and P1C04 disabled local mock integration.
