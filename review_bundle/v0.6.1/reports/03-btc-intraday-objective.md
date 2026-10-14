# BTC 4–24h Intraday Portfolio — Revised B-line Research Objective (R1)

**Controller:** ChatGPT-0; **date:** 2026-10-13; **status:** OBJECTIVE_APPROVED / RESEARCH-ONLY; **source:** Controller planning request 2026-10-13 and verified G2 R3/R4, Goal-B and Issue #1; **release:** G2_ALPHA_NO_GO.

## Binding strategy objective

Discover and independently validate a BTCUSDT USDT-M perpetual multi-mechanism directional trading portfolio targeting approximately **one high-quality executable portfolio opportunity every 48 hours on a rolling average**, primarily managed within a **4–24h maximum holding horizon**, with positive net expectancy after realistic fill, financing and operational costs, favorable realized payoff distribution, bounded drawdowns and feasible entry/exit execution. This is an optimization objective and feasibility gate, **not** an order schedule or a claim that an opportunity always exists.

The target is about **0.5 portfolio executions/day**, 15/30 calendar days and 180–183/year under uninterrupted admissible source coverage. Track rate per actual eligible calendar-time exposure; publish uncertainty and missing-data exclusions. The primary scope is **BTCUSDT only**, long/short, one aggregate directional BTC exposure by default. Early invalidation, protective stops, take profits or risk closure may shorten the actual hold. No loss-making filler trades or forced entries to hit cadence.

Practical superiority over uninformed/undisciplined trading is a research motivation, NOT an empirically verified percentile versus retail traders. Outperformance claims require a valid external population comparator.

## Existing trade-frequency versus economics evidence

All observations below are historical **exposed development** results, not validation and not independent cost truth.

| Tested approach | Reported executions and calendar | Mean STRESS proxy net | Interpretation |
| --- | --- | --- | --- |
| W1 ATR expansion trend 12h | 34 fills / 35 scored months | +11.2047bp | Sparse and previously selected; 2023 negative; not an Alpha |
| W2 asymmetric volatility breakout 12h | 55 / 35 months | +19.0135bp | Sparse and 2023 negative; not Alpha |
| W1/W2 18h extensions | 34/55 same originally selected episodes | +48.55/+41.45bp | Positive descriptive means; paired confidence bounds include zero; H18 gains driven by few target winners |
| Goal-B wide 72h failed-breakout reclaim | 167 / 35 months | -33.10bp | Gross+10.97bp; positive gross insufficient for legacy cost |
| Goal-B Keltner false-expansion reversal | 669 / 35 months | -36.93bp | Approx one fill/1.6 days, inadequate price advantage |
| Goal-B low-vol shock fade | 941 / 35 months | -43.07bp | Approx one fill/1.1 days, unfavorable economics |
| Goal-B 15m failed-acceptance | 1,100 / 35 months | -45.54bp | Approx daily frequency, not positive after fees |
| Codex G2 R3 A/B/C × exit × cap | 27 cells / selected 12 score months | All negative, 5/34/35 per cell | No Alpha, distinct source/timing/funding estimator from older W1/W2 |

Sources: Goal-B exact SHA b51a0019c68c8539895ac1b48379f0045e5bfdae; W1/W2 Exit R1 SHA 55ac4c631c69f6edbd275462ad23e4486b9782ed; H18 SHA 397a62c1a0fbd6ad14a569a5be0058b1f684f08e; R3 a69ccfdfd578bd0b7d3aa43d75959a659f969782; R4 98c99ae2690c9e771f65e8ef9dc6a2124d8d6c3f.

The bottleneck is **after-cost directional payoff**, not signal generation alone. Legacy STRESS44 is an assumed cost scenario, so these negatives are genuine for THAT frozen proxy, not proofs against lower-cost execution. Repricing any historical PnL needs its own authorization and leakage safeguards.

## Mechanism architecture and falsifiable novelty

Plan at most **two active primary mechanisms plus one optional observation mechanism**. No automatic code/search runs.

**Track T — structural continuation:** 1h/4h regime, distinct 15m setup, limited 5m causal order confirmation; new feature must explain value migration, replenishment or first-pullback positioning *beyond* frozen R3 B breakout–retest–reacceptance. Do not merely change EMA/ATR thresholds. Benchmark its incremental signed post-entry return and cost against matched contemporaneous controls.

**Track R — failed auction/reacceptance reversal:** requires observable failure of accepted prices / trades and, when asserted, book depletion/replenishment; 15m wick or signed taker ratio alone is NOT forced liquidation or absorption. Must be distinct from prior Goal-B failed acceptance and R3 C next-bar reclaim negatives.

**Track V — compression to directional release:** ex-ante volatility transition is a regime **condition**, not directional prediction; signed direction needs independent mechanism and ablation versus matched volatility-only baseline. Must distinguish previous Keltner false-expansion and compression failures.

**Optional Track P — perpetual dislocation:** only after contemporaneous spot/perp/index quotes, OI/Mark/settled Funding and causal receipt identities are admissible. Distinguish unhedged perpetual direction from equal-BTC hedged spot/perp basis; price spread cost, carry/borrow and both legs are part of the hypothesis. Consumer C delayed Funding remains blocked.

Decision rule: at the P3 preregistration gate select at most T/R or T/V as distinct primary mechanisms and retain P as observation ONLY if distinct data readiness becomes credible. Do not assume combining two negative strategies yields positive portfolio returns.

## Portfolio event funnel and acceptance measures

Record five separate counts for every candidate: (1) raw setup, (2) deduplicated economic episode, (3) closed-bar/known-at confirmed candidate, (4) order-eligible executable candidate after quote freshness/tick/lot/min-notional/spread/latency/risk, (5) portfolio-admitted hypothetical execution after occupancy/overlap/conflict/cooldown. A signal is not an executable trade; overlapping same-direction 5m and 15m alerts are ONE episode absent a separate new inventory event.

Portfolio conflict resolution predeclare direction priority by verified state quality and net payoff estimate; no new opposite exposure while existing exposure remains except an independently frozen hedge. Limit aggregate notional, one active risk budget and drawdown disable. Count opportunities relative to timestamped admitted exposure, not only scored months with good signals.

Dashboard: rolling 30/60/90d counts and daily/weekly inter-event gaps; gap proportions >48h, >72h, >7d; opportunity rate after broker-like admission, long/short mix, 4/8/12/18/24h occupancy, overlap suppression, source outage exclusions, realized/hypothetical net per trade by full funding + fill, PF, drawdown, top-k profit concentration, calendar stability and uncertainty. For any missing value state UNKNOWN rather than zero.

## Outcome-blind Phase-2 feasibility boundary

A separately approved task MAY count frozen source-qualified signal timestamps and ex-ante feature availability from permitted public observations without loading future returns or trading outcomes. Feature-rule identity, source/time contract and dedup/cooldown must be frozen before counts. Reusing an already exposed developmental method does NOT create unexposed OOS, and counting returns in a candidate funnel is forbidden. If source/path rights are absent, limit to published event-count aggregates and invented examples.

New historical return labeling, MFE/MAE scoring, parameter sweeps, outlier-based selector search, order-book capture and all account/release actions require a NEW exact-SHA authorization. Frequency alone is not scientific Alpha.

**Gate:** current R4 NO_ADMISSIBLE_NEXT_STRATEGY_TRIAL remains in force for existing proposed 21-endpoint design. Allow only design, fee-cost, synthetic-statistics and source/frequency readiness work until adequate provenance, novelty, attainable power and independently reviewed preregistration are proven.
