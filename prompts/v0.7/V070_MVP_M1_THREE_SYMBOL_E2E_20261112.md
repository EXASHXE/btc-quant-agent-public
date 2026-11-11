# V070-MVP-M2-E2E-OFFLINE-INTEGRATION-01 | M1 Three-Symbol Synthetic Vertical Slice
Executor: Codex Sol (single implementation owner); Controller 0-C accepts. State: READY — NOT DISPATCHED.
Language: engineering English; Owner update Chinese.

Mission
Deliver one runnable, reproducible 2030 synthetic three-symbol product vertical slice on the now Controller-accepted Q0BC offline contract. Scope BTCUSDT, ETHUSDT, SOLUSDT; LONG/SHORT where the fixture supports. One native Q0BC Producer and its sole canonical transactional Outbox; no parallel Q0C Dispatcher or second notification ledger.

Authoritative evidence / read first
Root: /root/workspace/project/quant-0.7.0
- controller-decisions/V070_M0_Q0R_OFFLINE_SCOPED_ACCEPTANCE_20261112.json (new M0 decision)
- lt-q0bc-positive-semantic-proof-01/continuation-01/reports/POSITIVE_SEMANTIC_ACCEPTANCE_REPORT.md
- lt-q0bc-positive-semantic-proof-01/continuation-01/reports/{TEST_INVENTORY,NATIVE_READY_TO_OUTBOX_EVIDENCE,CURRENT_GATE_AND_ATTEMPT_EVIDENCE,CRASH_RECOVERY_MATRIX,QUEUED_PLAN_CONFLICT_EVIDENCE,ERRATUM_COMPATIBILITY_EVIDENCE}.json
- lt-q0bc-positive-semantic-proof-01/q0bc_v2/
- lt-q0b-b01-stable-identity-01/ and lt-q0c-feishu-outbox-offline-01/
- docs/engineering docs/project/V070_GEMINI_PREFLIGHT_REVIEW_AND_FAST_MVP_PLAN_20261111.md and V070_EXECUTION_DELEGATION_POLICY_20261111.md (canonical GitHub branch).
- Original three Gemini preflight maps are optional architecture references, not execution evidence.

Execution boundary
L0 delegated offline synthetic engineering only: no external network, Binance requests, real Feishu messages, accounts, protected 2024/2025/2026 data or holdout, deployment, time/service changes, secrets or orders. Do not alter, delete, rehash or overwrite sealed Q0BC original evidence or baseline. Work in one isolated implementation workspace; inspect current locks/worktrees first. Ordinary L0 tests, files, commits and internal receipts do not need repeated Owner authorization.

Flow and ownership
Synthetic 2030 Source Mock -> native Q0B Engine with 1D regime / 4H / completed 1H setup / completed causal 15m confirmation / 5m and quote -> native Q0BC eligibility/cost -> one durable Q0BC Outbox -> Q0F FEISHU_MOCK_ONLY card/transport -> separate append-only Shadow store -> existing read-only HTML rendering.
The canonical Q0BC Producer owns episode, immutable Plan, cause consumption, eligibility, queue and dispatch gate. Reuse Q0C card serialization/mock/HMAC utilities only; never instantiate Q0C V1 Dispatcher or a second Outbox DB. Transport I/O stays outside the SQLite transaction. Never represent provider accepted as human read.

Narrow fixes and contract gates
1. Reproduce the 30s/60s boundary: native Q0B observation can be <=60s (snapshot asof), but all actionable Q0BC eligibility/gate/claim and mock pre-send require a same-venue causally ordered book quote <=30s (current now anchor), snapshot-to-now <=1s; no 5m-close quote substitute. Review the known false negative: 15m confirmation consumed when quote age 30001..60000ms before Producer rejection. Implement the smallest versioned compatible fix that preserves 15m cause for later fresh-quote requalification within its existing expiry, without weakening 30s gate or changing numeric economics/plan identity; only if reproduced. Include tests at 29999/30000/30001/60000/60001ms, quote missing/future and gate expiry.
2. Correct R1.1 economics event schema overlay as a versioned E1 event+adapter bundle, requiring economics.evaluation_policy_status == OWNER_APPROVED. Keep old sealed schema unchanged and all historical proof byte-identical. Update $ref and validation pins explicitly in the new integration package; no silent URN alias, no Plan/episode rekey, no ledger migration. Run six actual positive payloads against both validators and six negative POLICY_UNAPPROVED specimens against corrected one. Do not claim schema-only bypass has occurred in Producer runtime.
3. Preserve atomic READY+Outbox; attempt_evidence INSERT and ATTEMPTED UPDATE in same outer durable commit before possible transport. Gate fresh evidence/generation check, duplicate suppression, cold restart UNKNOWN_DELIVERY retryable=0 with no blind resend. On provider timeout/ambiguous result, preserve UNKNOWN fail-closed. Check source/account/symbol veto, stale 4H, no chase and latest 1H supersession.

Acceptance
One command reproduces the 3-symbol synthetic E2E from a clean isolated workspace. Cover at least the planned 24 positive/negative scenarios including truthful NO_SETUP denominator, WATCH vs READY, stale/missing quote, false 15m, plan drift/refetch, duplicate, crash-before/after-commit, queue/gate/claim, provider success/error/timeout/UNKNOWN, isolated Shadow append-only observations and HTML, plus H5/H10 conditional response. Output concise runbook, machine-readable cases/outcomes, event/outbox/transport trace, single HTML report, diff, tests, and exact remaining blockers; only claim metrics actually observed.
Preserve: SOURCE_BLOCKED=true, SOURCE_QUALIFIED=false, SHADOW_QUALIFIED=false, ECONOMICALLY_VALIDATED=false, no Alpha, no real delivery or trading.
STOP and report if a concrete defect requires rewriting sealed proof inputs, access beyond L0, external sending, dual-authority queue, undeclared schema rekey or protected data. Return concise Chinese Owner handoff with exact paths. The worker does not self-accept M1.
