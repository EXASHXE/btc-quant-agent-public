# V070 Research Priorities After Owner Manual Latency Disclosure
Status: ADVISORY_RECOMMENDATION; not experiment authorization.
Date: 2026-10-28.
Canonical document: GitHub `docs/engineering`.
Owner-supplied operational constraint: **manual response after notification to order submission normally takes 1–5 minutes**.

## Decision and rationale
M1 forced-deleveraging / liquidation-shock reversion remains the **first bounded research feasibility candidate**, NOT a validated strategy, sole viable mechanism, or an authorized backtest.

The end-to-end actionable timeline includes event occurrence, required data publication/receipt, evidence maturation, decision commitment, delivery, 1–5 minute manual action, and exchange execution. The relevant estimand is **residual capture after the notification plus the selected manual response delay**, not full shock-to-peak reversal and not return from a hindsight-labeled low.

A 5-minute human delay **does not automatically mean** 5-minute total latency. A coarse 5m historical OI series, end-of-bar wait, and cessation confirmation can consume the opportunity before the message reaches the Owner. Preserve both clocks:
- `event_time` (origin of shock);
- `first_causally_eligible_decision_time` (all required evidence actually available);
- `notification_commit_time`, `delivery_time` (measured; if unknown, mark UNKNOWN);
- `user_order_submit_time` (assumed scenarios + future actual reports);
- `realistic_execution_time` (modeled and ultimately observed).

Do not infer liquidation from OI declines alone. An OI decline can reflect voluntary closures and both sides of open contracts; distinguish information-led selloffs versus temporary forced-flow pressure. A historical Binance `!forceOrder@arr` feed samples at most the latest force order per symbol per 1000 ms, so it cannot be treated as full liquidation turnover.
Official Binance docs: https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Liquidation-Order-Streams
The OI history REST interface offers 5m+ periods but only about the most recent month; 2021–2023 source availability must be proven with already-accepted archived data or a legitimate vendor and PIT semantics:
https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics

## Revised scientific priority order
| Priority | Decision | Scope and terminal deliverable |
|---|---|---|
| R0 / P0 | M1 causal-source and human-delay FEASIBILITY preflight | Existing archival data source coverage and publication clocks (not value/outcome reads), liquidation proxy semantics, spot/perp matching, clustering and independent support. Return FEASIBLE_FOR_BOUNDED_EXPLORATION / SOURCE_OR_LATENCY_BLOCKED / INSUFFICIENT_SUPPORT. |
| R1 / Conditional | M1 exploratory residual-move/execution analysis | Only after explicit data-use authorization and R0 source pass: freeze decision-time algorithm BEFORE reading outcome labels; calculate remaining feasible move and net R for **1, 3, 5 minute human response**, with 10–15 minute end-to-end sensitivity. Include actual confirmation lag and STRESS fees/spread/slippage, gaps and NO_FILL. |
| R2 / Parallel low-cost | Existing structural playbook placebo & baseline audit | Separate exploratory analysis if authorized: causal pivot confirmation, matched random/no-signal entry, no-fill, price-regime/beta control and honest event-driven stop/exit; not a new primary Alpha claim. |
| R3 / Independent alternative | Medium/slow trend + structure (M3) | Retain as fallback more compatible with 1–5m response; do not infer a 5-day optimum from friction/volatility ratio. Test after source/performance case is specified. |
| R4 / Owner scope decision | Low-turnover hedged funding/basis carry (M2) | Research separately if two-leg, margin-capital, venue/counterparty and settlement risk fit the Owner's intended product. Not a direct substitute for the manual directional-opportunity assistant. |

These are **research priority labels** not dispatch permission, date commitments or rankings of expected profitability.

## R0 preflight questions and stop conditions
1. Can a historical 2021–2023 non-leaking symbol universe be reconstructed, including delisted instruments, from documented admitted sources?
2. What exact timestamp and granularity are known-at for 5m OI statistics, perp/spot prices, taker trade information, bid/ask/spread, and premium? What is missing?
3. How many *independent market shock clusters* and opposite-direction controls are potentially supported? Count event candidates before reading returns; do not optimize a family of outcome-conditioned thresholds.
4. Does a causal early WATCH using price/trades/perp-spot dislocation, followed by delayed OI evidence for ACTION, make sense? Test both distinctly; never backdate the OI confirmation. A rapid entry based only on early evidence is a DIFFERENT hypothesis and must be explicitly identified.
5. If source availability or clock provenance cannot demonstrate an actionable decision while the reversion window is still plausible, STOP the historical M1 economic campaign. A limited prospective timing/monitoring pilot may be proposed under separate authorization.

## Conditional R1 evaluation contract
- Human delays: primary **3 min**, favorable **1 min**, conservative **5 min** measured from *notification actually received*; missing delivery timestamps => unavailable, never 0.
- Record total `event→eligible→commit→delivered→order→fill` age. Independently show **10–15 minute total-delay** stress scenarios.
- Measure residual move to an originally frozen anchor *after the executable entry*; report completion fraction **before** entry and residual distribution (median, tails and cluster bootstrap), not just eventual maximal reversal.
- Verify usable market opportunity at the **5-minute human scenario**, not only 1-minute ideal execution. Profit proxy must exceed instrument-specific STRESS round-trip costs, funding, price impact and tail-risk allowance. Underlying signal must also withstand same-episode spot-leading/information-shock controls.
- If most expected economic edge disappears before the realistic executable entry, discard manual M1 opportunity alerts even if post-shock reversal is statistically present.
- Preserve independent event clustering and honest missing/partial fills. Future real event-to-send timing distributions are needed to calibrate historic conservative lag assumptions.
- No claims of positive Alpha without independent, predeclared and sufficiently powered confirmation.

## Parallel product engineering (separate from Alpha research)
Finish the already-existing Foundation contract reconciliation; prior receipt on 2026-10-28 recorded 33/34 original Foundation, 140/141 original affected, 35/35 new continuation, 6/7 original E2E: still **PARTIAL**. Check for fresher receipts before acting.
Then prioritize user-reported position risk copilot + immutable TradePlan/claim ledger + transactional notification outbox. Separate opportunity tiers:
- RESEARCH: internal ledger, no discretionary executable recommendations.
- CANDIDATE: clearly experimental, explicitly opt-in observation and no promise of edge.
- VALIDATED: externally and prospectively supported under a stated protocol; this status is currently EMPTY.
Product utility and strategy Alpha remain independently evaluated.

## Protected experiment and document boundaries
This decision note creates no authorization for historical outcome/market payload reads, protected 2024–2025 exposure, 2026 FINAL_HOLDOUT, PRIMARY registration, new data collection, real alerts, worker dispatch, account access or trades.
Existing frozen PRIMARY experiment classifications and funding NULLs remain unchanged. Funding sensitivity analyses can be proposed but must not rewrite an accepted terminal.
All subsequent authoritative docs, role definitions, task cards and new-chat prompts are to be read/edited **only on GitHub docs/engineering**. This note does not alter the review-only Opus branch or executable v0.7.0 branch.
