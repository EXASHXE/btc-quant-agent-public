# v0.6 B-line G2 R3 — Controller alternate event-journal engine IMPLEMENTATION dispatch R1

**REAL TASK GRANT:** `AUTHORIZE_ONE_ALT_ENGINE_SYNTHETIC_ONLY_GEMINI_A_IMPLEMENTATION__NO_HISTORICAL_MARKET_BODIES_OR_LIVE`.

- **Task ID:** `V06_G2_R3_P1_ALT_ENGINE_GEMINI_A_IMPLEMENTATION_R1`
- **Role:** Gemini A implementing a NEW, isolated R3 research micro-engine from one frozen prospective specification. **Not** an R4/R5 modification of rejected mutable VirtualBook.
- **Repo:** `EXASHXE/btc-quant-agent-public`; **implementation branch already created**: `feature/v06-bline-g2-r3-p1-alt-engine-gemini-a-r1`.
- **Remote branch START SHA (v0.6 code baseline):** `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`. Note that the **Controller dispatch SHA is a different later docs commit**: do not checkout implementation from the docs branch! Verify both separately and record in execution receipt.
- **Controller prospective R1.2 method/spec freeze:** `821d23427a5f6d0b4635f32f226ddc779358ab72` at [AM01/AM02 decision](https://github.com/EXASHXE/btc-quant-agent-public/blob/821d23427a5f6d0b4635f32f226ddc779358ab72/reviews/v0.6/b_line/V06_G2_R3_P1_ALT_ENGINE_AM01_AM02_CONTROLLER_SPEC_FREEZE_R1.md).
- **Source Sol architecture design:** `c0b41d1ce62e0fe852edfc6e162f1bc3dc6dcc01`: [design](https://github.com/EXASHXE/btc-quant-agent-public/blob/c0b41d1ce62e0fe852edfc6e162f1bc3dc6dcc01/docs/strategy_research/g2_r3/p1_alt_engine_sol_r1/ENGINE_OPTION_DECISION_AND_EVENT_LEDGER_DESIGN.md), [17 invariants + 34 named synthetic oracles + module plan](https://github.com/EXASHXE/btc-quant-agent-public/blob/c0b41d1ce62e0fe852edfc6e162f1bc3dc6dcc01/evidence/v0.6/b_line/g2_r3_p1_alt_engine_sol_r1/ENGINE_OPTIONS_AND_INVARIANT_ORACLE_MATRIX.json).
- **Original scientific 8 candidates formula IDs:** `e5b2006a89441f7eb2ec900e508aff451106b87a`. **Accepted R1.1 PIT/cost source:** `cf2d5cc33774cdcff7d709636305bba830e977ef`; R1.2 freeze explicitly adds prospective AM01/AM02 and must be named separately.
- **Rejected A target (read-only reference, never implementation base/import mutable money):** `b5d34aacd36dc27454944a22436db555c3f6eeb8`. Independent B terminal blocked `52ee5f1e582defbfb0bb3c8bb29101a1d40d9cd7` (B01,B02,B03,B05,B06,B07; B04 PASS).
- **Worktree:** suggested `/root/workspace/project/quant-v0.6/g2-p1-alt-engine-gemini-a-r1`, only if unoccupied, with clean branch and remote origin verification.
- **Authority limit:** one complete implementation, synthetic-only focused engineering tests, then one independent B/Sol exact-SHA semantic audit; independent blocker means STOP, not another patch loop. Source/strategy/economic performance authority remains ZERO. Prefer GPT-6 Sol if needed for tricky invariants as a reviewer of the Controller contract, but A execution must not substitute unapproved scientific choices.
- **Immutable implementation Prompt:** published as a separate exact-sha docs file AFTER this Controller dispatch. Read that pinned prompt link and this dispatch SHA before making changes. Do not assume floating docs branch contains your branch file.

## Allowed writes

Only:
- `src/btc_quant_agent/strategy_research/r3_alt_engine/**`;
- `tests/test_r3_alt_events_money.py`, `tests/test_r3_alt_clock_execution.py`, `tests/test_r3_alt_retest_replay.py`;
- `scripts/strategy_research/r3_alt_engine/run_synthetic.py`;
- `docs/strategy_research/g2_r3/p1_alt_engine_impl_r1/**`;
- `evidence/v0.6/b_line/g2_r3_p1_alt_engine_impl_r1/**`.

Original candidate registry, existing A/B code/tests, P2 or A-line, H40 golden and CI/workflow untouched. **Read-only** pure value source can be inspected using pinned SHA but no mutable `VirtualBook` import or legacy ledger adapters. No data fetchers/readers, CSV/Parquet/ZIP market bodies, private credentials, external exchange requests, TESTNET or real order execution.

## Implementation acceptance contract

Architecture: 12 event kinds/8 immutable records; deterministic event identity/payload hash; immutable reducer/journal postings and owner subledgers; 7 owner phases plus killed latch; explicit source-proof clock vs economic/event vs model ACK; all original eight candidates and BASE/STRESS cases; as-of mark conflict rejection; closed Retest sequential cursor and same-hour no re-seed; owner-scoped pending exit loss/fee/liability and funding cover+shortfall; 17 per-transition invariants (I01–I17). B04 SL-first, worse stop gap, favorable target cap and protective hold/expiry retained.

**Tests:** instantiate and execute all 34 T01–T34 Sol oracle scenarios on actual implemented code, not only list/static receipts. Require 0 FAIL/0 SKIP/0 XFAIL for the mandatory cases; run a true `ReplayEngine.run_simulation` of synthetic-only nonempty winning AND losing 4h cases plus BASE 12h, original 240h indicator warmup, funding+fees and exact end-of-book reconciliation. 12h STRESS remains `STRESS_COST_GEOMETRY_INELIGIBLE`, no fake trade. Include deterministic input permutation/Decimal context/Python-version tests. Logs must distinguish developer-authored positives from later independent behavioral checks. If cannot finish an authorized case with frozen R1.2 semantics, **return INCOMPLETE**; never invent PASS to protect schedule.

**One initial package, one independent audit, one STOP rule**. No promotion solely on green CI. Do not bypass license/source Mark ambiguity or 2026 protected old Final Holdout. Work exclusively with synthetic in-memory bars and marks and declared conservative proxy fees. All scientific R3 results are unobserved.

**Terminal states:** `ALT_ENGINE_IMPLEMENTED_SYNTHETIC_READY_FOR_INDEPENDENT_AUDIT`, `ALT_ENGINE_IMPLEMENTATION_INCOMPLETE`, `ALT_ENGINE_CONTRACT_CONFLICT_STOP`, `BLOCKED_IDENTITY_OR_SCOPE`, `BLOCKED_NOT_PUSHED`. Production P1 acceptance remains `NO` until independent Controller L2 validates B/Sol outcome. P2 `LOCAL_ROOT_UNKNOWN`; P3 prereg `NONE`; P4 market body `NONE`; TESTNET and real funds `NONE`.

**Delivery mandate:** commit one cohesive branch result and non-force PUSH independently; remote exact HEAD SHA/parent+allowed paths/CI receipt must be verified. If there is any material discrepancy between Sol design and new Controller R1.2 freeze, the Controller R1.2 freeze prevails, STOP on unresolved stronger source conflict; do not ad hoc rewrite candidate rules.
