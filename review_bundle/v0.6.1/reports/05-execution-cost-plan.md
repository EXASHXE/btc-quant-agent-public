# BTCUSDT USDT-M Perpetual — Execution Cost Recalibration Plan R1

**Status:** METHOD_DESIGN_ONLY / NO HISTORICAL REPRICING / NO PRIVATE ACCOUNT ACCESS.
**Controller:** ChatGPT-0, 2026-10-13.
**Official reference, accessed 2026-10-13:** https://www.binance.com/en/fee/futureFee ; official explanatory FAQ (updated 2026-05-01) https://www.binance.com/en/support/faq/detail/360033544231 . The fee table is dynamic/localized, so record retrieved page, time, product USDT-M, USDT maker/taker column, account assumptions and any effective promotions before operational use. Do not apply TradFi, COIN-M, USDC or VIP columns to USDT BTC perpetuals.

## 1. Do not confuse legacy proxy with fee

| Per executed leg (entry or exit) | Frozen BASE | Frozen STRESS | Actual ordinary USDT-M reference |
| --- | ---: | ---: | --- |
| Fee | 6 bp | 12 bp | Maker 2bp; Taker 5bp |
| Assumed spread drag | 2 bp | 4 bp | Must be measured at arrival/filled executable price |
| Assumed additional slippage | 3 bp | 6 bp | Must be conditioned on latency, size and volatility |
| Simplified roundtrip | **22 bp** | **44 bp** | Fee only M/M 4bp, M/T 7bp, T/T 10bp |

The 22/44bp figures are historical **research conventions**, not observed venue costs. STRESS44 includes **24bp fees** alone, whereas ordinary all-taker two-leg fee-only reference is 10bp. A marketable LIMIT at counterparty level 1 generally REMOVES liquidity and may incur taker fees; LIMIT wording does not prove Maker status. Account VIP, BNB fee discount, promotions, realized maker ratio, fee tier changes and liquidations are UNKNOWN. Never presume ordinary published reference equals a specific user's realized rate.

## 2. Signed cash and decomposition

Use signed position side s=+1 LONG, -1 SHORT; positive fill quantity q>0 BTC, signed economic funding rate r (longs pay when r>0), actual filled price P_i USDT/BTC, filled fee f_i, valid settlement Mark M_T, remaining position Q_T after unambiguous same-clock fill ordering.

Define entry cost from arrival-mid m_e to actual fill P_e by s×(P_e−m_e)×q; for exit s×(m_x−P_x)×q, with arrival/executable mid m_x and fill P_x. These mid-to-fill terms jointly include spread, impact, latency/adverse selection and slippage, decomposed only when mutually exclusive evidence exists. If executable ask/bid price is used for a fill, **do not deduct that same half-spread again**. For taker buy, ask-mid crossing is half-spread, not full-spread PER LEG; one buy and one sell can consume approximately a full spread over a roundtrip even with unchanged mid. Maker fill probability, rebates and queue position cannot be assumed 1.

For a flat, unhedged directional episode:
- Signed trading cash: s×sum_exit(q_j P_exit_j) − s×sum_entry(q_k P_entry_k), with sum exited quantity = sum entered quantity after rounding and any flat-at-end contract.
- Fee cash: minus sum_i(abs(q_i×P_i) × verified maker/taker fee rate_i).
- Settled funding cash: sum_T[-s_T × abs(Q_T) × valid settlement Mark_T × signed rate_T]. Positive cash credit is kept signed; absence of source is COST_INCOMPLETE, **not** funding=0.
- Net USDT = trading cash − fees + funding cash − explicit other carry/borrow/impact costs not already included in actual fills. Net basis points = 10,000×Net USDT / predeclared reference entry gross notional. For partial open inventory distinguish realized cash from Mark-based unrealized exposure and fees to liquidate.
- Derive return on margin only after actual leverage/margin/collateral and risk are separately defined. Do not multiply notional bp edge by leverage and call the result attainable economic alpha.

### Invented synthetic ledger — LONG (not a historical fill)

One taker entry, one taker exit; 0.010 BTC; arrival mid at entry 100,000; ask 100,002 plus 1 USD additional adverse slippage -> buy fill 100,003. Exit arrival mid 101,000; bid 100,998 less 1 USD extra adverse slippage -> sell fill 100,997. Ordinary illustrative taker fee 5bp each side. One invented settlement r=+0.0001 and verified synthetic Mark=100,400 with full 0.010 exposure.

- Gross executed price PnL=(100,997−100,003)×.010=+9.940000 USDT.
- Entry fee = 100,003×.010×0.0005=0.500015 USDT; exit fee =100,997×.010×0.0005=0.504985 USDT; fees =1.005000 USDT.
- Long funding cash=−.010×100,400×.0001=−0.100400 USDT.
- Net = **+8.834600 USDT**; raw mid-to-mid move would have been 10.000000; price execution drag 0.060000, fees1.005000, funding0.100400. No second spread deduction.
- Net initial executed-notional bp=10,000×8.8346/1,000.03≈88.3434bp (not account return).

### Invented synthetic ledger — SHORT

Sell 0.010 BTC from entry mid100,000, bid99,998 minus1 slippage -> entry99,997; buy to cover from exit mid99,000, ask99,002 plus1 slippage -> exit99,003. Fee 5bp per leg; one invented positive settlement r=+0.0001, Mark99,600 while short.

- Trading PnL=(99,997−99,003)×.010=+9.940000 USDT.
- Fees 99,997×.010×0.0005=0.499985, plus99,003×.010×0.0005=0.495015; total0.995000 USDT.
- Signed funding credit to short=+.010×99,600×.0001=+0.099600 USDT.
- Net = **+9.044600 USDT**; opposite funding sign relative to LONG; no double spread/impact charge.

For partial legs, the entry fee applies once to each actually bought/sold quantity, and exit fees apply only to that filled exit leg. Enforce identity by fill-id, exact Decimal quantity conservation, execution timestamp > source-known-at, signed cash and no retroactive BE/protective activation.

## 3. Scenario hierarchy (not retrospective result relabeling)

**FEE_ONLY_REFERENCE:** maker/maker4bp, maker/taker7bp, taker/taker10bp fee identities plus receipt/precision tests; NOT an executable performance claim.

**NORMAL_EXECUTION:** frozen applicable user-independent verified fee tier reference and empirically admissible bid/ask at order decision/arrival, realistic conditional partial/fill probability, marketable taker entry/exit and measured latency-dependent slippage; source and distributions must be accepted before economic trial. Missing distributions = NOT_CALIBRATED, do not invent numerical Normal price drag.

**ADVERSE_EXECUTION:** conditionally high but plausible spread, greater size-vs-visible-depth and adverse selection, market impact, stop-market gap, partial completion and cancellation/timeout/reprice tails; calibrate empirical p75/p95 and outage regime.

**EXTREME_STRESS:** independently frozen extreme volatility/liquidity/latency/funding/stop gaps and order-rejection cases. Preserve a side-by-side LEGACY_BASE22 / LEGACY_STRESS44 comparator as a *sensitivity*, never conflate it with Normal or assume 44bp worst possible.

Report p50/p75/p95 and worst observable tail for venue spread, adverse fill-mid, queue nonfill, canceled remainder, latency and signed funding by UTC hour/session, volatility, notional size and order type. Data grade and sample support for each conditional bucket must accompany the estimate. Unknown marketable quote conditions are not zero.

## 4. Source, known-at and funding admission

Need public timestamped BTCUSDT perp bid/ask, sequence-valid book snapshots/deltas, tick/step/min-notional and instrument filters valid at use time, provider and receiver event clocks, actual decision/ACK, full or partial executed leg, order-type fee reference, signed historical settled funding rate and correctly contemporaneous settlement Mark. Historical Last minute open is a **trade-price proxy**, not executable arrival bid/ask. Mark is valuation/settlement source, not itself an executable fill. OI, basis or future published funding cannot be backdated to settlement as a feature.

Consumer C currently rejects late REST funding because settlement economic time != receiver available time. Fix only under separate contract authority; neither stamping available_at=settlement nor ignoring a missing cash event is admissible.

Data acquisition must be public-only, locally/legally authorized, minimal and finite, with no protected/reserved/owner data and no private account. Collecting fresh quote/book evidence is NOT authorized by this planning document; a later source permit is required.

## 5. Required separate implementation/test grant

Before a cost-engine implementation, issue a fresh SHA-frozen branch and path allowlist. Invented synthetic tests must cover: buy/sell fee rates, maker vs taker classification including marketable LIMIT, half-spread versus fill price no double count, partial exits, rounding/tick/lot conservation, duplicate fill/settlement idempotence, stop gap vs stop-limit nonfill, ACK-to-BE, late funding receiver clock vs settlement clock, source-missing fail closed, identical order cost decomposition under synthetic Last/mid/quotes, and 10x/15x leverage not altering notional-bp fee. Independent financial PIT reviewer required.

No frozen historical R3/R3.1/Goal-B outcome modification, data fetching, outcome repricing or order submission granted. **Terminal here: COST_RECALIBRATION_METHOD_DESIGNED_PENDING_MEASURED_SOURCE.**
