# Codex Sol High — P1D R4 Causal Late-Funding G1 Ledger Integration (Synthetic-Only)

## Exact-SHA dispatch

Owner: ChatGPT-0 B-line Controller, quant v0.6.
Task ID: V06_CODEX_P1D_R4_CAUSAL_LEDGER_SYNTHETIC_INTEGRATION.
Authority: this prompt at the exact immutable Git commit in which it is published; verify the full SHA and Git blob, not moving HEAD.
Executor: Codex Sol High; independent reviewer: other Codex/ChatGPT-1, not the implementer.
**Implementation base (exact, not latest branch):** \`04cbc46497ed26b0c4e889f30fa10eb8d666a79e\` from \`repair/v06-p1d-r2-doc-surface-ci-r1\`. This base has the report moved off the code branch. Original port code digest at this base \`scripts/g1g3_offline_ports_r1/market_pit_port.py\`: \`3c2198325649ea3a64986218ec60953cbb889403\`. Original G1 reducer blob \`df6a68f4797950f1b9bdbdebc6591745cdea76d5\`.
**Independent audit** \`e11f84963adddc29b1dc106c1e0d2a984dd6add2\`, path \`reviews/v0.6/b_line/V06_P1D_FINAL_SHA_INDEPENDENT_CAUSAL_REVIEW_R1.md\`; independent terminal \`INTEGRATION_BLOCKED\`, with F1 and F2 BLOCKER, F3 HIGH.
**Existing true manual full CI:** \`38426601134\` on exact base code SHA. Python 3.12 = \`3359 passed / 1 failed / 2 skipped\` (protected H40 synthetic graph digest). Python 3.11/3.13 failed on Git/CI history and H40; do not attribute those failures to this task. A separate Codex CI workstream owns compatibility debugging.

## Bounded engineering authorization

Create a **new isolated code branch** \`feature/v06-p1d-r4-synthetic-g1-funding-causal-integration\` at precisely the base code SHA above. No push to v0.6, main, existing repair branch, or another worker's branch. No force push. This dispatch authorizes bounded synthetic contract and regression code work, **not external integration**, fund movements, protected science, market data ingestion, TESTNET or LIVE.

Allowed **MODIFY** only:
- \`scripts/g1g3_offline_ports_r1/market_pit_port.py\`
- \`scripts/g1g3_offline_ports_r1/durable_supervisor.py\`
- \`scripts/g1_offline_preview_r1/model.py\`
- \`scripts/g1_offline_preview_r1/reducer.py\`
- \`scripts/g1_offline_preview_r1/storage.py\`
- \`tests/test_v06_g1g3_offline_ports_r1_core_integration.py\`
- \`tests/test_v06_g1g3_offline_ports_r1_recovery_and_guards.py\`
- \`tests/test_v06_g1_offline_preview_r1_process_recovery.py\`

Allowed **ADD only**:
- \`tests/test_v06_p1d_r4_late_funding_g1_economic_recovery.py\`
- \`docs/engineering/v0.6/V06_P1D_R4_SYNTHETIC_CAUSAL_INTEGRATION_EVIDENCE.md\` only if \`docs/\` allowed by existing code-branch catalog checks; otherwise omit report and publish it separately on a docs branch after asking Controller; never create \`reviews/\` on a code branch.

No other changes, no new/altered H40/H41 source/tests/golden, no CI policy/test-plan modification, no historical event data or reusable private source.

## Objective: close independent reviewer F1/F2/F3 without time-travel

F1: At current code SHA the port translates a late funding envelope into \`g1_event.at=settlement_at\`, while reducer.transition rejects \`at < last_at\` as EVENT_REORDERED. Never "repair" this by backdating receiver visibility, decreasing last_at, replaying earlier decisions with later-known funding, or disabling reordered-event assertions. Define and implement a causally ordered **receipt-time** integration path while retaining immutable economic settlement_at, with explicit historical versus new event-kind compatibility. If preserving existing G1 event schema makes this impossible within allowlist, STOP with \`CONTRACT_REDESIGN_REQUIRED\` and a minimal, exact-SHA proposal; do not do an architectural rewrite.

F2: Funding debit must depend on **settlement-time** witnessed Mark, settled rate, and actual position exposure from fills executed strictly before the economic settlement; it may NOT use current receiver-time remaining_qty or a nearby last bar as proof of settlement Mark. Build deterministic synthetic witnesses for a 0.010 BTC long at 60000 and +0.0001 funding at T, partial 0.004 exit after T but before receipt: charge -0.0600 USDT, not -0.0360. Check equivalent signed short, zero exposure, pre-T partial, ± uncertain edge. Missing Mark/rate/fill-membership => COST_INCOMPLETE / reject; never silently zero cost.

F3: The port keeps dedupe state in memory, whereas the G1 WAL owns a separate used_settlements set. Prove or implement settlement-keyed exactly-once **cash journal** semantics over crash boundaries: accept before/after receipt, after WAL append, before snapshot, after restart, conflicting same settlement on new transport key, duplicate rate/Mark/event_id. Preserve ordered decision state. Reject contradiction between side and signed quantity instead of unqualified abs() normalization if it permits an economically wrong long/short interpretation. Avoid changing existing general G1 ledger invariants.

## Tests and scientific boundaries

First construct minimal RED synthetic tests on the frozen original base: late funding after newer BAR (no EVENT_REORDERED and no earlier decision leak), correctly witnessed settlement exposure/Mark, crash and replay exact-once, conflicting fingerprint, signed SHORT/LONG/flat, zero-rate completeness, missing fields, chronological ACK/WAL recovery. Mark RED as a real failing test, not presumed. Then minimal implementation and GREEN targeted tests. Verify legacy G1 fixture/old funding compatibility. Test source code only; no historical strategy runner, no historical economic outcome-scoring, no archived protected source, no testnet/order APIs.

Run focused impacted test suites; optional comprehensive Python3.12 only after real fix, but **do not call full gate PASS** while H40 digest still fails or compatibility tests unresolved. Record test commands, exact pytest totals and source/test blob diffs, cite independent F1/F2/F3 disposition. Do not rewrite protected goldens. If any feature requires external source receipt/fills to prove economic truth, label \`SYNTHETIC_INTEGRATION_ONLY\`, not source-admitted.

## Receipt and STOP conditions

Report base SHA, branch SHA, diff whitelist, negative/positive tests, immutable ledger invariant checks, actual CI results, and \`SYNTHETIC_G1_LATE_FUNDING_INTEGRATED_PENDING_INDEPENDENT_REVIEW\` / \`CONTRACT_REDESIGN_REQUIRED\` / \`FAIL\`.
Independent reviewer must separately validate exact final commit; no self-attested PASS, no merge or auto-release. G2 Alpha/TESTNET/LIVE remain NO_GO.
