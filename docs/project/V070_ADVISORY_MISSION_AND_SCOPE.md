# v0.7.0 Product Mission — Real-Time Opportunity & Position Advisory
Status: Owner direction reflected 2026-10-28. Documentation-only planning baseline; not deployed system status.

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
