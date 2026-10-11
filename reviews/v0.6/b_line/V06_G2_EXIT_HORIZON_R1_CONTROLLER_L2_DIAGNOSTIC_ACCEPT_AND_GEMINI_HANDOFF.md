# v0.6 B-line Controller — Exit/Horizon R1 L2 diagnostic acceptance and temporary Gemini executor route

**Decision date:** 2026-10-12 (Asia/Shanghai)
**Controller:** ChatGPT-0, B-line only
**Decision:** EXIT_R1_DIAGNOSTIC_ACCEPTED_INSUFFICIENT_SUPPORT__NO_POLICY_PROMOTION__GEMINI_EXECUTOR_TEMPORARY
**Authority level:** Controller interpretation/next planning; *not* protected data access or live execution authority.

## 1. Verified exact identities and scientific work unit

Repository EXASHXE/btc-quant-agent-public. Branch feature/v06-bline-exit-horizon-r1 verified remote HEAD **55ac4c631c69f6edbd275462ad23e4486b9782ed**, direct parent frozen implementation **de2c1fb222970a93ca797868b91b8544261ebaad**, direct parent original R3.1 baseline **990c02b5479b3b14996f90fdbf677cb672ada81e**. Exactly two commits beyond start, no unrelated changed paths; 13 frozen implementation/test/method/contract files at first commit, result-only report/evidence/ledgers at second. Original Controller Dispatch **7293d3f97f2d81167fd6ea17e69e424065e19e41**; frozen design **9a3ba717e0c8eea062d74a038f743f87d7ae1b94**; prompt **974d32c5cae75be7ef228826e33fd4edcb446be0**.

The evidence's first remote freeze receipt records parent/HEAD verified prior to new exit outcome computations. This is supported by remote ancestry and pre-result freeze files, not by an independent time-stamped surveillance of each memory read. Frozen code and 66 inherited files were reported byte-identical by final handoff, preserving original E0 Last/Mark/Funding receipt and no 2024–26 or protected outcomes.

GitHub CI on frozen method commit **38151818546** completed SUCCESS; **3060 passed, 2 skipped, 9 warnings** in risk-selected full pytest, Ruff/compile/type/JSON steps SUCCESS, manual full compatibility lane SKIPPED. Final result-artifact commit CI **38155507891** SUCCESS, tests/Ruff/type skipped as risk-planner mode=none, compile/JSON PASS. The executor's separate scoped 54 tests PASS. Do not conflated final artifact-only green with rerunning scientific methods on final commit.

E0 exact identities for W1/W2 × BASE/STRESS are committed in E0_EXACT_IDENTITY_RECEIPT.json: original R2 event/trade digest, R3.1 funded trade digest, three minute equity curve digests per cell = EXACT_MATCH; static source inheritance and method path reviewed by Controller. Independently scoped Python stdlib CSV/ZIP/Decimal test method reconstructs partial quantity, fees, post-TP1 remaining-funded quantity, as-of Mark, cash journal and Mark curve for 24 real episodes (STRESS12/BASE12), including both directions and positive/negative funding, with 14 residual-Q funding cases. Source body itself was not freshly downloaded or rerun in Controller session. No actual TP1 within 60 s of settlement (closest 119,999 ms), explicitly reported; no fabricated historical boundary case.

**Terminal reported** EXIT_R1_DIAGNOSTIC_INSUFFICIENT_SUPPORT. L2 review accepts it as a useful bounded **DEVELOPMENT_ONLY diagnostic**, not an independent alpha-validation or order-fill certification.

## 2. Empirical findings and limits

Only original BTCUSDT public USD-M 2021–2023 data; two fixed candidate IDs and four new exit schemes per ID, no D1/D2 trials, 35 scored months, 3,285 real signed settlement rates with **completed 1m Mark settlement-notional approximation** and BASE22/STRESS44 friction proxies, rather than exact historical maker queues/fee tiers/exchange settlement marks.

STRESS44 full funded account means, in bp/trade, E0/H1(18h)/H2(24h)/E1(50%1R partial)/E2(E1 residual BE):
- W1 n34: **11.2047 / 48.5499 / 44.0744 / 11.6909 / 10.5317**
- W2 n55: **19.0135 / 41.4477 / 33.0215 / 20.5324 / 18.1324**.

H1 has a coherent exploratory 12h→18h time-cap mechanism in both leads, including year-2023 improvement, but both candidates' 7d and 14d simultaneous eight-contrast confidence intervals cross zero. H2 has lower point means than H1 despite more exposure/Funding. E1 increments are small in STRESS and negative versus E0 in BASE; E2-E1 is negative in both candidates. All original 89 STRESS paired events had complete 24h prices; 20/34 and 36/55 E0 trades reached original 12h time cap. No sample-size improvement (same 34/55) or prospective independent test. Historical original 48-trial selection was already exposed and no confirmatory joint56-family inference can be claimed.

**Separation:** fixed-event paired contrasts do not model all account availability; complete account replay separately regenerates signal event fates, partial tiers, ACK/cooldown, 5% reserve, ≤1x capital, cash/funding and minute Mark MTM. This is a research execution proxy, not actual order book/maker queue/real liquidations. Source checksum authenticity does not prove historical known-at or commercial rights.

## 3. Scientific disposition and stop

- SOURCE_IDENTITY: ACCEPTED within previously authorized frozen public-data manifests and receipts.
- BASELINE_E0_IDENTITY: ACCEPTED on exact published digests and static implementation review.
- PARTIAL_LEDGER_DIAGNOSTIC: ACCEPTED within scoped simulation / independent documented Decimal reconstruction; does NOT demonstrate real maker fills or prove every unseen path.
- EXPLORATORY_RESEARCH: ACCEPTED as one bounded completed family.
- POLICY_VALIDATED: **NO**; ALPHA: **NO**; HOLDOUT_2024_2025_ACCESS: **NONE**; TESTNET/LIVE/REAL_FUNDS_WRITE: **NONE**.
- Future **D1/D2**: DESIGN_ONLY; no automatic R2, no outcome-guided change to 18h candidate or held-out consumption. Retire this exact R1 experiment family from adaptive exploration. Do not equate better development H1 average with new trading strategy.

## 4. Temporary executor re-routing

**User instruction (2026-10-12):** GPT-6.1 Sol quota constrained; use **Gemini** for future B-line executor work until explicitly changed. Controller and independent Auditor roles unchanged. Existing R1 complete, so DO NOT re-run R1, create a third P1 engine, auto-open 2024–25, or dispatch another "never stop until profit" search.

Next actionable work, only after Controller explicitly dispatches a newly bounded task if needed: *outcome-blind scientific readiness/strategy evidence prioritization,* e.g., review whether 18h mechanism merits a **future prospectively frozen** test or whether better independent entry hypotheses/source microstructure are needed. Gemini may handle scoped document/implementation/economic evidence tasks, with exact new Controller authority, independently verified repository branch/parent/changed paths, frozen trial budget, auto non-force push and remote verification. For semantic cash/funding/event sequencing or protected gates, Controller must apply tighter independent test/audit scrutiny rather than assuming Gemini/Codex naming guarantees correctness. Quota restriction is not an authorization to relax gates.

**A-line** independent; **Performance** independent; P1 ended/P2 owner source parked; H39/H40/H41/Forward/protected outcomes remain closed.
