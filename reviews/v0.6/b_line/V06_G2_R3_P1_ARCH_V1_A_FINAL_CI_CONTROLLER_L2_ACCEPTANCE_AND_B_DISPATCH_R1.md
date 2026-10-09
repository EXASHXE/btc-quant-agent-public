# v0.6 B-line G2 R3 P1 — Gemini A architecture final CI acceptance and independent Gemini B dispatch

## L2 Controller decision

**`ACCEPT_P1_A_DELIVERY_AND_REAL_NONEMPTY_SYNTHETIC_EVIDENCE__AUTHORIZE_ONE_FINAL_INDEPENDENT_B_ARCH_V1_AUDIT__P1_ENGINE_NOT_YET_ACCEPTED`**.

This document is a **real Controller-owned immutable dispatch** for the NEXT, one-shot independent Gemini B audit. It is NOT engineering, method, data or real-money acceptance.

### Verified A identity and changed-file scope

- Repository: `EXASHXE/btc-quant-agent-public`
- Existing A branch: `feature/v06-bline-g2-overnight-discovery-a`
- Prior A exact start: `398e6bab0cdedf07a93827019ca4bf1bf913c7f9`
- **Final A exact target:** `b5d34aacd36dc27454944a22436db555c3f6eeb8`, one direct child of `398e6bab...`. Original implementation commit `89d0c211cff96286203e4fb7459a51042c1257f1`.
- Five changed files **all within prior final closure allowlist:** design handoff; architecture synthetic receipt; B01–B07 matrix; `src/btc_quant_agent/strategy_research/r3_overnight/ledger.py`; `tests/test_strategy_research_r3_architecture_invariants.py`. Candidate registry, frozen design, other unrelated source, independent B branch, H40, old Holdout and P2 unchanged in A maintenance diff.
- Candidate receipt now correctly identifies the eight original `STRUCTURAL_CONTINUATION/CLOSED_RETEST × LONG/SHORT × 04H/12H` and original design `e5b2006a89441f7eb2ec900e508aff451106b87a`. This resolves the prior false-ID metadata, **not** independent semantic acceptance.

### Verified full CI

[A exact-head CI 37918930513](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37918930513): `SUCCESS`, Risk-based quality Python 3.12, `mode=full`; Ruff lint pass, mypy `Success: no issues found in 170 source files`, compileall pass, **2844 passed / 2 skipped / 9 warnings in 885.37s**. Compatibility/manual job skipped because no explicit manual full-suite request, but standard job executed `pytest -q --durations=20` full suite; do not misreport as zero tests or as independent B scientific PASS. Prior repeatable H40 golden mismatch **not observed in this run**, while historical failure remains a separately trackable reproducibility concern rather than reason to suppress current green.

### Synthetic execution evidence: meaningful progress

[Current pinned architecture receipt](https://github.com/EXASHXE/btc-quant-agent-public/blob/b5d34aacd36dc27454944a22436db555c3f6eeb8/evidence/v0.6/b_line/g2_overnight_p0_a/architecture_v1/ARCHITECTURE_SYNTHETIC_EXECUTION_RECEIPT.json) includes BOTH an empty-book control and a nonzero-trade actual `ReplayEngine.run_simulation` fixture after 240h synthetic warmup. `CLOSED_RETEST_LONG_04H` executed 1 trade, quantity0.006, modeled fees0.360036 USDT, funding0.480048 USDT, net−1.141284 USDT, 1000→998.858716 cash, zero final outstanding reserves. `CLOSED_RETEST_LONG_12H` BASE executed 1 trade, funding1.440144 USDT, net−2.10138 USDT, 1000→997.89862 cash, zero final reserves. These are **synthetic** checks, not real historical realized strategy observations or actual-fee proof. A reports 59 focused local passes on each Python3.12 and3.13; 13 declared test functions include one alias wrapper that re-invokes a prior scenario, so test counts are not independent scientific observations. B must validate real source and event trace itself.

### Decision boundary and authority

- **Next exact B start/parent:** `feature/v06-bline-g2-overnight-verifier-b@068a4005f68b5ee4a970063cb1f3bc524a08784a`. Reuse existing separately owned B worktree `/root/workspace/project/quant-v0.6/g2-overnight-verifier-b`, inspect local/remote branch/clean state and do not reset/clean/stash.
- **Independent audited immutable A target:** `b5d34aacd36dc27454944a22436db555c3f6eeb8`. B R2 original oracle/findings `068a4005...` and baseline A R2 `2c60b0653d3619eedf457753511a9ecc84c1cd5b` must remain unchanged. Fresh B behavior exercises exact A candidate/ledger/replay code in an independent isolated temp execution, not imported from B's stale local A sources or its own mocks.
- The next pinned B Prompt is published in a subsequent commit, NOT part of this authority object. The real `CONTROLLER_DISPATCH_SHA` is the Git SHA publishing THIS file; executor MUST independently verify and bind both it and the separately issued immutable B prompt. Do not treat a guessed SHA or floating branch name as authority.
- One final independent, adversarial, architecture-level semantic audit: identity+scope+CI+real per-position Funding, owner reserve shortfall/exact sum, mark PIT, pre-ACK economic risk, retest time/prospective original method, B02/B04 regressions and executed 4h/12h end-to-end. Negative/positive oracle must be independent, not a replay of A's PASS labels. Examine economic/equity and pre-S-stage ordering races, duplicate/same-close marks, event reorder and same-symbol close/reopen.
- B may add B-owned tests and audit artifacts only in `scripts/strategy_research/r3_verification/**`, `tests/test_v06_g2_r3_verifier_architecture_*.py`, `docs/strategy_research/g2_r3/prep_b/architecture_v1/**`, `evidence/v0.6/b_line/g2_overnight_p0_b/architecture_v1/**`. Must not modify any A code/tests/evidence or B R2 original artifacts.
- Exit exactly one `ARCH_V1_B_INDEPENDENT_SEMANTIC_ACCEPTABLE_FOR_CONTROLLER`, `ARCH_V1_B_SEMANTIC_BLOCKED_REPLAN_ALTERNATIVE_ENGINE`, `ARCH_V1_B_EVIDENCE_INCOMPLETE`, `BLOCKED_IDENTITY_OR_SCOPE`, `BLOCKED_NOT_PUSHED`. A material independent design/ledger failure triggers **alternative engine feasibility/replan, not another A R4/R5 patch loop**.
- B must auto-commit and non-force push only its original B branch, verify remote exact final SHA/parent/scoped diff and actual CI. No additional historical price/Mark/funding/OI bodies, H41/H42 sealed results, Final Holdout, TESTNET or real-funds authority; NO empirical policy-quality or strategy alpha claim.

**Project gating:** Sol `SCIENCE_READY` for one restricted descriptive/proxy-development diagnostic, Astra not currently needed; P2 `LOCAL_ROOT_UNKNOWN`; P3 first-pushed prereg `NONE`; P4 empirical-market-body authority `NONE`; real funds `NONE`.
