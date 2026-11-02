# v0.7.0 Product Mission — Real-Time Opportunity & Position Advisory

## 2026-11-02 product decision update

The near-term product is a deterministic **market-side opportunity survival and risk advisory** for a human responding in roughly 1–5 minutes. A single trustworthy WATCH/ARMED candidate with price zone, no-chase cap, structural stop, expiry, current source health, and genuinely subsequently received quote checks is a more meaningful first objective than a larger indicator library or hypothetical net PnL. If no event qualifies, `NO_SETUP` and exact veto/funnel accounting are valid outputs.

Owner-reported Session04 completion remains unverified against the most recent local `READY_FOR_OWNER_SIGNING / native NOT_RUN` acceptance; do not silently claim a live pass. Use [current evidence check](V070_SESSION04_EVIDENCE_RECONCILIATION_20261102.md).

Keep market-side eligibility separate from >=10-universe cross-sectional rank and account capital/margin/order controls. Do not weaken actual account hard veto or invent ten-member ranks. Funding/basis carry and user-reported position risk are worthwhile **research/product backlog hypotheses**, not deployed strategies or alpha. Keep automated trading, account access, live notifications and economic claims separately unauthorized.

---


> **Canonical:** GitHub `docs/engineering`. [Documentation Branch Policy](V070_DOCUMENTATION_BRANCH_POLICY.md). Matching `v0.7.0` documents are historical copies.
Status: Owner direction reflected 2026-10-28. Documentation-only planning baseline; not deployed system status.

## Current practical closure criterion (2026-11-02)

The first useful product milestone is a **genuine** qualified public-source-to-local-Shadow loop: admitted market fields and immutable replay, deterministic strategy/position state and source vetoes, WATCH/ARMED/market-side readiness, quote expiry/cancellation, and real subsequently received prices for 1/3/5-minute response scenarios. Publish local-only snapshots before economic validation where authorized. A synthetic dashboard, a valid short clock/BBO sample, or a modeled fill does not establish a continuous online product.

The latest Session03 run is `PARTIAL/BACKPRESSURE_BLOCKED`, Source instrumentation remains `PARTIAL`, while Session04/LONG handoff and Dashboard reuse are **offline ready only**. See [current closure status](V070_SOURCE_TO_ADVISORY_CLOSURE_STATUS_20261102.md). Native Session04 requires its own explicit diagnostic amendment and signer/window; LONG <=48h source + Shadow requires another independent grant and fresh <=300s native clock. Keep 50ms clock jump and queue-128 failsafes; do not restart legacy microstructure collection or spend time expanding unproven strategy counts. Genuine source quality, market-side strategy qualification, account readiness and economic value are distinct acceptance tiers.

## What we optimize
Deliver timely, trustworthy and actionable crypto trading-opportunity advice. The system detects market conditions, proposes a **symbol / direction / entry zone / confirmation / structural invalidation / initial stop / target or trailing policy**, tracks an unfilled plan, then tracks a real position only after user-reported or separately authorized verified fills. Alerts explain evidence changes and recommend HOLD, TIGHTEN_STOP, TAKE_PARTIAL_PROFIT, REDUCE, EXIT, CANCEL or RECONCILE.

No automatic order submission, account mutation or real-money control is part of the current mandate. News monitoring is planned, not implemented as an admitted input.

## The decision path
1. **Observe:** liquid USDT-M candidate universe with benchmark state, completed candles, available derivatives, current executable quote when available, explicit data freshness/health.
2. **Select:** a small, falsifiable family of playbooks (initially TREND_PULLBACK and BREAKOUT_RETEST); distinguish WATCH, ARMED, ENTRY_ELIGIBLE and NO_TRADE.
3. **Plan:** frozen plan identity/version, instrument and tick-size semantics, causal evidence, actual entry zone, confirmation, maximum acceptable price, structure-based invalidation and hard stop, risk budget, target mode and management rules.
4. **Commit/notify:** persist plan and decision before notification; record delivery attempts independently. Notify risk escalation ahead of routine opportunities.
5. **Manage:** confirmed user-reported fill opens a separate position lifecycle. Mark simulated and exchange-verified fills differently. Deterministic management uses latest valid inputs, risk priority and immutable revisions.
6. **Evaluate:** separate policy simulation, published recommendations and actual user behavior. Record NO_FILL, canceled plans, stale data, unconfirmed execution, unresolved outcomes and funding uncertainty.

## Trading policy principles
- Economic/derivatives signals are market context and possible incremental predictors, not guaranteed LONG/SHORT evidence. Price structure defines entry, invalidation and reachable profit reference.
- No mandatory fixed 2R target and no 4h/8h/12h/24h exit for profit simply because a deadline expires. Fixed time may bound risk, research evaluation, source validity or an explicit strategy thesis.
- Target modes: STRUCTURAL_ZONES (verified known-at levels), OPEN_ENDED_TRAIL (complete risk/trailing rule without invented TP), NO_TRADE (insufficient credible and safe plan). ATR projections are not structural support/resistance.
- Protective stops are mandatory for proposed positions, but simulated stops may gap and are not guaranteed fills. Structural/trend exit and trailing updates only activate after their evidence is confirmed and a new plan version committed.
- Compute feasible worst-entry risk and exposure across open correlated positions; reward/risk ratios screen plans, never generate arbitrary target prices.
- NEWS_RISK is an unimplemented future source and may only alter advice after source, publication/receive-time, reliability and asset relevance checks.

## Separate success criteria
**Product correctness:** valid scans; price/tick-size/time fidelity; actionable notification latency; plan and user-position state consistency; outage recovery; risk-alert coverage; no duplicate/conflicting/fabricated actions.

**Scientific/economic correctness:** transparent cost and funding assumptions; policy-level gross and modeled/full-net results; capital occupancy; drawdown and tail risk; prospective evidence; calibrated predictions only when supported. Useful advice does not itself prove positive after-cost Alpha.

## Minimal architecture
One compact deterministic advisory modular monolith using existing market_watch, structure/features, decision persistence, position_supervisor, notify and economic components. Research replay is operationally separate but shares versioned signal and management policies. LLMs can explain verifiable inputs and later classify news; they cannot invent fills, prices, stops or probability.

## Data and permission boundary
No new economic experiment, protected dataset inspection, forward market-payload access, collector deployment, credentials or exchange action is authorized by this document. Preserve historical frozen studies and 3/6 PRIMARY usage.
