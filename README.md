# BTC Quant Agent v0.6.1 — Gemini / External Scientific Review Snapshot

> **REVIEW-ONLY BRANCH — NOT A v0.6.1 SOFTWARE RELEASE, BACKTEST APPROVAL, STRATEGY PASS, OR TRADING PERMISSION.**

**Project:** BTCUSDT USDT-M perpetual quantitative research for 4–24h short-swing/intraday opportunities. Target around **one net-positive qualified BTC portfolio opportunity per 48h on a rolling average**, never a mandatory order. Python source/package, CI, tests, and simulation engine are retained unchanged from v0.6 code commit `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`. Research materials previously scattered across Git SHAs have been copied into **this single branch** preserving exact source Git blobs.

## Start here — branch-local links (no historical commit SHA required)

**Read in order:**
1. [Verified project roadmap](review_bundle/v0.6.1/reports/01-project-status.md)
2. [Complete strategy research register](review_bundle/v0.6.1/reports/02-strategy-validation-register.md)
3. [Intraday objective](review_bundle/v0.6.1/reports/03-btc-intraday-objective.md)
4. [G2 R3 27-cell results](review_bundle/v0.6.1/reports/07-g2-r3-27cell-results.md)
5. [Independent scientific audit R4](review_bundle/v0.6.1/reports/08-g2-r4-independent-audit.md)
6. [Cost model and source requirements](review_bundle/v0.6.1/reports/05-execution-cost-plan.md) and [indicator matrix](review_bundle/v0.6.1/reports/04-indicator-source-readiness.md)
7. [P2 Researcher design](review_bundle/v0.6.1/reports/09-p2-researcher-source-cost.md) and [independent Challenger objections](review_bundle/v0.6.1/reports/10-p2-challenger-review.md)
8. [Latest Controller adjudication](review_bundle/v0.6.1/reports/14-latest-controller-l2.md)

**Read actual historical strategy code snapshots (exact original bytes, named `.py.txt` to prevent accidental import):**
- [G2 R3 entry signals](review_bundle/v0.6.1/code/15-r3-signals.py.txt), [engine](review_bundle/v0.6.1/code/16-r3-engine.py.txt), [metrics](review_bundle/v0.6.1/code/17-r3-metrics.py.txt)
- [Goal-A trend/flow signals](review_bundle/v0.6.1/code/18-goala-trend-flow-signals.py.txt)
- [Goal-B reversal signals](review_bundle/v0.6.1/code/19-goalb-range-reversal-signals.py.txt)
- [F1–F3 original bootstrap code](review_bundle/v0.6.1/code/20-f1-f3-bootstrap-statistics.py.txt)

**Other resources:**
- [All original SHA/blob provenance and mapping](review_bundle/v0.6.1/FILE_MANIFEST.md)
- [Standalone prompt for an external review model](review_bundle/v0.6.1/EXTERNAL_REVIEW_PROMPT.md)
- [Controller Issue #1 scientific debate adjudication](review_bundle/v0.6.1/reports/06-debate-controller-ruling.md)
- [Original historical v0.6 README](review_bundle/v0.6.1/reports/00-original-code-readme.md) — describes an earlier v0.5/R01 facade and is *not* current research status.

## Critical snapshot findings
- **G2 independently verified BTC Alpha: NONE.** R3 27/27 STRESS development cells failed.
- The older W1/W2 positive mean results are sparse, exposed, with weak 2023 results; H18 gain is heavily right-tail concentrated.
- F1–F3 joint max-T inference is **UNCALIBRATED** because degenerate sparse resamples were mishandled.
- Legacy BASE22/STRESS44 are **assumed** total round-trip costs, not a measured Binance fee or measured NORMAL/ADVERSE execution cost.
- P2 historical OI, spot/perp flow, L2 and execution-source feasibility remain research issues, not admitted Alpha data. A 24h recording cap may not preserve a full day's L2 stream.
- Latest Controller L2 accepted bounded P1C documentary citation closure and P1A CI-history fix at its exact code SHA. P1D-R4 remains **INTEGRATION_BLOCKED** for G1 immutable-contract/H40 gates. No production integration/release authorization.

## Repository structure
Core code lives in `src/btc_quant_agent/`; operational/research code in `scripts/`; deterministic tests in `tests/`; tools, CI, configs and evidence retain their v0.6 base state. The newly added `review_bundle/v0.6.1/` is independent source material for reading, **not integrated runnable strategies**.

## What external models should do
Read the specific source material above before judging whether Spot-Led Breakout or Price-Shock/OI-Contraction Reversal offer economically and statistically novel incremental information. Analyze real source availability, event frequency, executable cost, sample power, multiple testing and historical cohort differences. **Do not promise 12–18 trades/month, 14bp NORMAL cost or Sharpe 1.1–1.8 without measured evidence.** Recommend a finite *outcome-blind first* research plan, not an unauthorized backtest.

If the model cannot access the entire public GitHub domain, GitHub branch links will not fix connectivity; have the user supply the branch ZIP/archive.
