# Gemini Goal E — Independent G1 offline-preview safety and recovery assurance R1

ROLE: independent read-only implementation/safety auditor. You are NOT the original Codex author and do not use any Codex quota. Implement an independent adversarial test harness and publish finite evidence at the exact code SHA; don't modify Codex implementation or wire production. A verified defect is a successful audit finding; stop and label NO-GO rather than hide it.

TASK_ID: V06_G1_GEMINI_OFFLINE_ASSURANCE_R1
CONTROLLER_DISPATCH_SHA: 4a487fcef182edc6c68486ff53d4a64caa10debc
AUTHORITY: https://github.com/EXASHXE/btc-quant-agent-public/blob/4a487fcef182edc6c68486ff53d4a64caa10debc/reviews/v0.6/b_line/V06_G1_G2_GEMINI_ONLY_NEXT_GATE_R1_CONTROLLER_AUTHORITY.md
REPOSITORY: EXASHXE/btc-quant-agent-public
BRANCH: feature/v06-bline-gemini-g1-offline-assurance-r1
EXACT_START_SHA: 861a9d148f72db00e6079e53af78220bdd7e84ce
OWN_WORKTREE: /root/workspace/project/quant-v0.6/gemini-g1-offline-assurance-r1
SCRATCH: /tmp/btc-g1_offline_assurance_r1
OWN_NAMESPACE: g1_offline_assurance_r1
CODEx_RESULT: G1_OFFLINE_PREVIEW_VERIFIED, 145 locally passing tests, 30 native process-kill/restarts at 15 checkpoints, 2 torn WAL cases, final GitHub CI 38200928294 SUCCESS with actual code tests. This is only a synthetic, nontrading sidecar, not G1 integrated release, G3, Testnet, Live or production security certification.

## Goal and strict acceptance scope

Independently review the exact frozen sidecar `scripts/g1_offline_preview_r1/**`, own local JSON fixtures and code tests at START_SHA. Validate material safety invariants and identify missing edge cases rather than repeat the original 145 tests without reasoning. Create **new independent sidecar test code in your own namespace only**, exercising original module imports as a *read-only* dependency. No account, live LLM, Feishu or exchange connection. Correct final outcomes can be ACCEPT_SYNTHETIC_G1_PREVIEW_ONLY, G1_PREVIEW_MATERIAL_SAFETY_DEFECT, or G1_PREVIEW_INCONCLUSIVE. Do not try to turn the current mock into a production pipeline.

Required static identity audit:
- Git worktree HEAD/parent and 4-commit Codex lineage, allowed paths and CI mode from server; enumerate exactly C3 and C4 touched executable symbols (new stop effective clock, safe argparse). Check manifest and historical evidence hashes, no code edit after exact C4.
- Map state machine transitions signal→mock analysis→explicit *fixture* approval→intent→sim fill→signed Funding→TP1/ACK/stop update→STOP/final ACK→outbox, with exact write points for WAL and snapshots. Discover any operation that alters journal before validated approval or sends network traffic.
- Prove via AST/monkeypatch import/socket guards that executable sidecar cannot reach orders, Testnet/Live or external notification by default. A static import denylist is partial; include dynamic outbound socket attempt interception within isolated process. No direct sockets to private or public exchange, no real funds.

Independent adversarial matrix, **minimum 60 distinct actual tests**, no cosmetic duplicated replays:
1. **Approval authority**: malicious/stale/replayed/other-order approval token, future token, wrong qty/side, mutation of synthetic mock analysis, double approval, approval crossing event clock, human token absent; require absolutely no accepted fill before valid approval.
2. **Causality**: incomplete minute Last/Mark bars, stale/future data, Mark-vs-Last confusion, TP1 and STOP same minute precedence, 12/18/24h cap, ACK before vs after stop, stop update cannot backfill previous minute stop hit, late Feishu/outbox receipt may NOT suppress due stop.
3. **Financial ledger**: Decimal independent reference across both directions, lot rounding, maker/taker fee and slippage as configured invented proxy, negative signed Funding and remaining inventory, duplicate funding receipt IDs, duplicated fill IDs, two pending exit ACK cases, min-notional fail-closed, 5% reserve/one-position/cooldown, all exit ACK journal cash conservation. Do not assume the synthetic fixture min-notional is Binance's real production minimum.
4. **Failure/recovery**: kill actual process (os._exit) immediately around entry intent, fill, approval, 3 funding settlements, TP1, second pending ACK, stop-effectiveness, final close and outbox; include 15 original points plus at least 5 novel offsets. WAL partial/torn/duplicate, checksum mismatch, changed genesis fixture, checkpoint fork, stale stored state, missing outbox, unknown schema version. Post-restart final journal deterministic equivalence or explicit quarantine/fail closed.
5. **Output and safety**: argparse fake secret argument not reflected in logs, JSON and trace scrubbing, no clipboard/real Feishu sends, no future private adapter, idempotency and native single-process concurrency assumption.

Before running tests on real sidecar, **freeze** independent audit plan, expected invariants and synthetic tests in first commit. The sidecar is not a 2021–23 research engine; no historical research data or new policy testing required and none authorized. First nonforce push + verify remote freeze SHA/parent. If the independent tester itself needs repair following observed results, keep old receipts immutable and STOP for new Controller authority; do not erase evidence.

Then run at most ONE finite independent negative battery under Python3.12, capture at least 60 tests and core state before/after each malicious input, host-level actual network call count (zero), all ledger effects and diff with 145 case original suite (which can be run once if env supports). Characterize test gaps; new test failures are not automatically flaws in original engine until minimum reducing witness is independent and deterministic.

Deliver a **semantic release-boundary report**:
- What exactly is safe in synthetic offline G1 sidecar.
- What is still not real: authenticated human approval, credential custody, live LLM bounded outputs, real Feishu delivery/permissions, exchange-known-at source, broker ack, L2 queue, production deployment and disk power-loss semantics.
- Whether manual approval truly prevents simulated order intents; whether recovery is deterministic across verified failure points; whether no network/order write authority remains technically enforced.
- Recommended next engineering contract when Codex budget resumes, with a minimal dependency diagram; NO actual integration/deploy commands or TESTNET.
- Full pytest/Ruff/compile and observed GitHub Actions run+skips, machine evidence sha manifest.

Second result commit must be evidence/docs-only, nonforce push and verify SHA/parents/diffs. NO modification of `scripts/g1_offline_preview_r1/**`, `tests/test_v06_g1_offline_preview_r1_*.py`, production code, original results, .github, role docs, other agent worktrees. ONLY WRITE `scripts/strategy_research/g1_offline_assurance_r1/**`, `tests/test_v06_g1_offline_assurance_r1_*.py`, `docs/engineering/g1_offline_assurance_r1/**`, `evidence/v0.6/b_line/g1_offline_assurance_r1/**`. Never list/stat/read `/root/workspace/project/Quant-agent/data`, `Quant-agent-sanitized`, 2024–26, protected H39/H40/H41/Forward, A-line/Performance or accounts. ZERO testnet/live orders/Feishu messages.
