# Controller Research Dispatch — P2 BTC 4–24h Source/Cost Feasibility R2 (Outcome-Blind Design Only)

Controller: ChatGPT-0 B-line Primary Controller.
Executor: Independent Researcher (ChatGPT-2) or Gemini NORMAL, method/design only; Adversarial Challenger (ChatGPT-3) for independent review.
Task authority: the immutable Git commit containing this prompt. This is NOT market-data acquisition, historical return-label access, backtest or exchange trading permission.
Docs base: 2c99c8f64368a02dfeca05ac1886ed2280faf3ba; create a separate docs worktree/branch docs/v06-p2-btc-outcome-blind-source-cost-feasibility-r2; never modify live canonical docs files.

## Objective, not a performance claim

Design an admissible next-stage data/method contract for BTCUSDT Binance USDT-M perp long/short with typical holding 4–24h and a strategic average of ~one qualified *candidate opportunity* every 48h, without forced execution. A measured after-cost positive expectancy is required BEFORE actual Alpha; no fixed win-rate, maker-fill assumption or ex-post signal selection is allowed.

Primary independent references:
- Controller BTC portfolio objective and source-readiness plan at 198d0a931cfd610e86553c1f427c57ae60608a65.
- P1A cost design at a68eeef973a178a68005f7eca247ec15bc9bf2a2 and accepted design-only Controller ruling efa2df62c02d21b20ce07846c7ca30901716e773.
- P1A synthetic cost R2 at 0540e2c902ef9565cd3719e60174ac01b1c22adf (not measured market calibration).
- P1D synthetic late-Funding design at 81c613c3c8dc3fb22fd4d09b2d0ef4674f09c079 (not source-qualified fills).
- G2 science R4 read-only audit at 98c99ae2690c9e771f65e8ef9dc6a2124d8d6c3f.
- F1–F3 max-T synthetic METHOD_BLOCKED; original simultaneous CI remains uncalibrated.
Read only public code/doc/source interface contracts and synthetic receipts; do not inspect protected H39/H40/H41, owner Quant-agent/data, private account/fill archives, reserved holdout or past strategy price/result arrays.

## Deliverables (design-only)

1. Source capability matrix: BTC Last OHLC 1m, settlement Mark and time, recorded funding publication/receiver known-at, bid/ask/depth snapshot+deltas with sequence/clock continuity, intended size vs depth, fill-role/VWAP/ACK/cancel/partial stop execution (UNKNOWN without our own measured fills), maker nonfill queue risk, outages/clock uncertainty. Separate public observed/proxy/inferable/impossible-from-public.
2. P1A four regimes: FEE_ONLY_REFERENCE as abstract basis, NORMAL and ADVERSE measured only when actual admissible observations exist, EXTREME synthetic bounded stress. Explicitly distinguish maker/taker fee schedule reference (ordinary 2/5 bp per leg, not personalized) from actual achieved fees and filled-role mix. Avoid BASE22/STRESS44 relabelling as live costs.
3. A future prospective public BTC source collector acquisition permit DRAFT (not authorization) with symbol/endpoints, time window, max records/bytes, receiver clocks, data rights, QC/fail-closed, contract-admission fields, source checksum, no account calls, no market/label scoring. Use conservative example caps 24h, <=100,000 public quote/depth events, <=50MiB, first bound wins, but quantify infeasibility or endpoint issues rather than treating caps as data collection approval.
4. Outcome-blind rate/power design: operational opportunity counting before profitability, regimes and 4–24h expected duration, deterministic non-overlap, stable portfolio admission, support/independent-event counts, season coverage, false discovery control and joint-family selection. The "0.5 opportunity/day" is a design target, not forced orders, not guaranteed positive expectancy or proof of tradability.
5. New *preregisterable* causal mechanisms only, not parameter-optimized combinations selected from past W1/W2 PnL. Document pretrade feature PIT, invalidation, execution path, order toxicity, null hypothesis, falsifier, leakage and multiplicity. A shortlist is a scientific design artifact only.
6. Map exactly which data/CI/PIT evidence must exist before a separate Controller grant authorizes measured source collection or new G2 development scoring. Be frank about unknown account effective maker fills, actual slippage, funding/Mark and settlement tails. Estimate effort and prioritize highest-impact blockers without inventing market magnitudes.

## Write allowlist and review

Two new docs paths only:
- docs/project/V06_P2_BTC_OUTCOME_BLIND_SOURCE_AND_COST_FEASIBILITY_R2.md
- reviews/v0.6/b_line/V06_P2_BTC_FEASIBILITY_R2_INDEPENDENT_CHALLENGE.md

The second file must be authored by a genuinely separate challenger, if available; otherwise leave it absent and report CHALLENGER_PENDING. Do not claim a review by copying the researcher's own arguments. No code, collector, historical re-run, strategy score, tests/goldens, prompt edits, protected source access or exchange requests. Do not promote Alpha, DRY_RUN external integration, TESTNET or LIVE.

Publish exact isolated docs commit, branch and diff, source/authority SHA receipts, empirical-access log affirming NONE, dissenting review if actually performed, and terminal METHOD_PLAN_READY / SOURCE_NOT_READY / REVIEW_PENDING. Any real data acquisition requires NEW exact-SHA and source/time/budget specific Controller authorization.
