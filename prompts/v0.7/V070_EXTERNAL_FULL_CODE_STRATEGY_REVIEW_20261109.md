# External Independent Review Prompt — Quant v0.7.0
## Architecture / Strategy / Refactor / Fast MVP

You are an independent principal quant researcher, systematic trading engineer, and senior Python architect. Perform a **code-grounded adversarial review** of Quant v0.7.0. Do not assume the architecture is correct or that extensive tests imply trading edge.

Repositories:
- Canonical planning (read first): https://github.com/EXASHXE/btc-quant-agent-public/tree/docs/engineering
- Dated verified state: docs/project/V070_STATUS_AND_HANDOFF_20261109.md
- Intraday MVP plan: docs/project/V070_INTRADAY_MVP_ACCELERATION_PLAN_20261109.md
- Full isolated *review snapshot* of accepted offline application code: https://github.com/EXASHXE/btc-quant-agent-public/tree/review/v070-full-code-review-20261109/v070-app
- GitHub code branch is for static independent review; do not claim it was merged, deployed, or native/economically qualified.

Review the actual Python packages, CLI, Source/live adapters, 1H/4H/1D candle handling, S1 trend-pullback, regime/feature logic, opportunity compiler, persistent Shadow, local HTML dashboard, research evaluator, tests, fixture duplication, native authority and clock guards, and build/deployment scripts. Cite concrete file paths, functions/classes and lines or symbols. If you cannot access code, explicitly mark the finding UNVERIFIED; do not invent inspection.

Owner's product goal:
- Read-only crypto decision support, primarily **2–12h** holds; overnight up to 24h only when preplanned.
- Primary setup on completed **1H**, market regime/structure on **4H**; **1D** as macro-risk context, optional subordinate **15m** confirmation.
- Review once/twice daily with explicit entry zone, structural stop, realistic targets, after-cost R, expiry, no-chase, reasons and NO_SETUP.
- Expand BTC/ETH/SOL to a dynamic liquidity-qualified universe (initial 10–20, then ~20–50 if verified sustainable), including large liquid altcoins.
- Deterministic regime router: trend up/down/range/unknown × volatility normal/high/low/dislocated; initially only S1 active, others research-only.
- Keep actual auto-execution, accounts, key handling, orders and trade automation as TODO only.
- Accelerate **first real market-to-S1-or-NO_SETUP-to-Shadow-to-dashboard operational MVP**, not more framework scaffolding.

Verified facts / constraints:
- Programs A/B/C, H/J/L/O achieved scoped offline acceptance; source and Shadow strict qualification false; economics insufficient; account UNKNOWN/VETO.
- Program N genuinely received 22 public Binance REST HTTP 200 responses (240 completed 1D, 300 completed 4H bars), but two ~0.8–0.9s host clock steps failed closed before Source admission. No genuine trading setup or dashboard followed.
- Program P attempted one Owner-authorized guest timesyncd stop; after ~3.29s an independent clock guard stopped the trial, rollback succeeded. 600s/120s validation incomplete; current WSL host remains unqualified.
- The N raw payload was scoped-purged under Owner approval; retained audit metadata does not authorize reconstruction.
- Existing FIFO, 128 queue hard stop, 50ms sticky clock stop, durable accounting, protected historical date and 2026-02-01 to 2026-08-01 FINAL_HOLDOUT restrictions, source-specific rights/grants, no PRIMARY trial registration, no account/order access all remain binding.
- Any alternative Source or host requires independent eligibility, accuracy and evidence; don't suggest bypassing region controls or relaxing the strict guard as a shortcut.
- Historical BTC directional ideas did not establish after-cost alpha. R11 fixed 14-day carry deprioritized; L2 feature episodes are not independent wins.

Please deliver, in Chinese, the following **eight sections**:

1. **Evidence inventory:** What code and test evidence was actually read? Confirm exact commit/branch, source root, acceptance level, known missing provenance, limitations. Separate implemented/offline/native/economic/product readiness.
2. **Architecture diagnosis:** Critical path diagram and module dependency map; identify accidental complexity, duplicated code/config/fixtures, overlapping CLI or Source paths, dead code and legacy compatibility layers with path/line evidence. Explicit KEEP / MERGE / DELETE / DEFER judgments. Do not recommend deleting original sealed evidence.
3. **Fastest MVP route:** A specific, dependency-ordered P0/P1/P2 plan that gets a genuine authorized low-frequency market scan, valid completed candle warmup, 1H setup/4H regime, real card or NO_SETUP, durable Shadow, local HTML and replay under a qualified clock/host. Specify acceptance tests, failure exits and the smallest viable deployment/host alternative. State which existing modules avoid a rewrite.
4. **Intraday research design:** Evaluate 1D as context vs hard decision; 4H regime and 1H entry; optional 15m; 2/4/8/12/24h horizons; trade opportunity expiry at scheduled reviews. Identify leakage, candle-close ambiguity, human response delay, high funding, jumps and false 3R/4R expectancy. Compare S1 trend pullback, S2 breakout/retest, S3 range mean-reversion / failed-breakout; require genuine after-cost evidence and regime-conditioned no-edge controls.
5. **Regime and universe design:** Deterministic, versioned market state machine with hysteresis, uncertainty and NO_SETUP, plus bounded two-stage liquidity-universe discovery. Include Binance 24h ticker weighting implications, request budget, rate limits, snapshots/caches, data gaps, spread/depth/cost filters and cross-symbol ranking support; call out exact implementation changes.
6. **Simplification/refactor plan:** Rank <=10 high-value proposed PRs by impact, effort, dependencies, risk and test changes. Distinguish safe dead-code removal from unverified research behavior. Propose a minimal target tree and migration/rollback; name high-risk coupling and avoid speculative framework rewrites.
7. **Independent challenge:** At least five concrete weaknesses or places where current project design may be overengineered or scientifically unproductive. Estimate the time/effort tradeoff **as a scenario, not a fact**, and compare decision quality to a simple periodically scheduled ChatGPT/V3.0 market monitor.
8. **Final verdict:** State whether to ship a narrow read-only MVP now, conditionally after host/data gate, or re-scope. Provide one prioritized Controller 0-C work package and an acceptance checklist. Explicitly list unresolved assumptions and which data the Owner must supply; ask at most three critical questions.

Reviewer rules:
- Analysis ONLY, do not mutate branches/code or dispatch other agents.
- Use actual code, not project-document prose alone. Give file/function references for factual claims.
- No claims of live profitability, OOS alpha, exchange eligibility or passing native Source without proof.
- Distinguish hard blockers from nice-to-haves and prefer a narrow working product over breadth.
- Do not read protected local/private data, credentials, account state, sealed economic/holdout payloads or attempt unauthorized API calls.
- Keep Owner's 2–12h horizon, dynamic liquid universe, deterministic risk, and delayed human review central.

End with **one-page actionable summary addressed to 0-C**.
