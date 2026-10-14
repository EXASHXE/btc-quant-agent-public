# Independent Challenger Review — BTC 4–24h Outcome-Blind Source/Cost Feasibility R2

**ROLE:** ChatGPT-3 — Independent Adversarial Quant Research Challenger, a separately initiated review role, **not** the ChatGPT-2 Researcher, Controller, implementation executor, or audit-signing authority.  
**DATE:** 2026-10-14 (Asia/Shanghai).  
**REVIEW TARGET (immutable):** Researcher document at commit `1bd24ff42a5eedf498cb5ee574207790e2f3c144`, Git blob `4cb86972d3cc41374026a765f8ba8ba85dcd76e8`, `docs/project/V06_P2_BTC_OUTCOME_BLIND_SOURCE_AND_COST_FEASIBILITY_R2.md`.  
**AUTHORITY:** Controller dispatch `efe0dce0773e2ac76771dda7847a4dffbe867ceb`, `prompts/v0.6/b_line/V06_NEXT_P2_BTC_OUTCOME_BLIND_SOURCE_COST_FEASIBILITY_R2.md`, Git blob `2bd452aa1c9e926fd1306afb97ca5f9606152e79`.  
**DOCS BASE:** `2c99c8f64368a02dfeca05ac1886ed2280faf3ba`.  
**ISOLATION:** Own reviewer branch `docs/v06-p2-btc-feasibility-r2-independent-challenger`, forked from exactly `1bd24ff42a5eedf498cb5ee574207790e2f3c144`; add only this allowlisted review file. No edit to the Researcher's work, canonical docs, code, tests, evidence, prompts or CI. The independent reviewer read source/method contracts *before* opening the Researcher's new design; subsequent crosswalk was against the immutable blob above. Both roles may publish through the same GitHub owner's credentials: **a shared commit author is not evidence of independent analysis**. This document asserts a separate reviewing role/session and independent technical assessment, not an independently authenticated human identity.

**DISPOSITION:** `INDEPENDENT_REVIEW_COMPLETE / METHOD_PLAN_READY_WITH_REQUIRED_CORRECTIONS / SOURCE_NOT_READY / NO_SOURCE_PERMIT / NO_G2_TRIAL`. The Researcher's plan is a good **design artifact**, not evidence that the desired cadence, complete source or positive net returns are feasible. Do **not** represent the present review as `SOURCE_ADMITTED`, `COST_CALIBRATED`, independent Alpha verification, or an approval to collect data. The blocking findings below apply to *advancing the method/permit*, not to writing a conceptual research document.

## 1. Source and scope identity — exact SHAs, not interchangeable

| Read-only evidence | Exact commit SHA | File / admissible inference |
|---|---|---|
| Dispatch | `efe0dce0773e2ac76771dda7847a4dffbe867ceb` | `prompts/v0.6/b_line/V06_NEXT_P2_BTC_OUTCOME_BLIND_SOURCE_COST_FEASIBILITY_R2.md`; outcome-blind, two-path write allowlist |
| Researcher document | `1bd24ff42a5eedf498cb5ee574207790e2f3c144` | `docs/project/V06_P2_BTC_OUTCOME_BLIND_SOURCE_AND_COST_FEASIBILITY_R2.md`, blob `4cb86972d3cc41374026a765f8ba8ba85dcd76e8`, 120 lines |
| Controller BTC objective, readiness, cost plan | `198d0a931cfd610e86553c1f427c57ae60608a65` | `docs/project/V06_BTC_INTRADAY_STRATEGY_OBJECTIVE_AND_PORTFOLIO_RESEARCH_PLAN.md`; `V06_BTC_INTRADAY_INDICATOR_VALUE_AND_SOURCE_READINESS_MATRIX_R1.md`; `V06_BTC_EXECUTION_COST_RECALIBRATION_PLAN.md` |
| P1A cost method | `a68eeef973a178a68005f7eca247ec15bc9bf2a2` | `docs/project/V06_BTC_EXECUTION_COST_METHOD_SYNTHETIC_R1_DESIGN.md`; synthetic design, no market calibration |
| P1A Controller ruling | `efa2df62c02d21b20ce07846c7ca30901716e773` | `reviews/v0.6/b_line/V06_BTC_EXECUTION_COST_METHOD_SYNTHETIC_R1_CONTROLLER_L2_DECISION.md`; design accepted only |
| P1A synthetic implementation/CI report | `0540e2c902ef9565cd3719e60174ac01b1c22adf` | `reviews/v0.6/b_line/V06_P1A_R2_SYNTHETIC_COST_CONTRACT_REPORT.md`; 24 synthetic targeted passes, **4 full-CI failures**, terminal CONTRACT_BLOCKED |
| P1D late-funding synthetic report | `81c613c3c8dc3fb22fd4d09b2d0ef4674f09c079` | `reviews/v0.6/b_line/V06_P1D_CONSUMER_C_LATE_FUNDING_R2_IMPLEMENTATION_AND_EVIDENCE.md`; synthetic late-receipt fix not real settlement ingress |
| G2 R4 index | `98c99ae2690c9e771f65e8ef9dc6a2124d8d6c3f` | `evidence/v0.6/b_line/g2_r4_independent_science/SOURCE_AND_AUDIT_EVIDENCE_INDEX.json` — **index/metadata only; no strategy prices, result arrays, score fields or trade ledgers inspected** |

External venue **documentation only**, last reviewed October 14, 2026:
- [Binance USDⓈ-M Websocket Connect](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Connect), documented `/public` depth vs `/market` Mark routes, 24h connection lifetime, ping/pong and inbound rate limits.
- [Binance USDⓈ-M local order book recipe](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/How-to-manage-a-local-order-book-correctly), snapshot `lastUpdateId` synchronization and subsequent `pu == previous.u`.
- [Binance USDⓈ-M REST market-data API catalog](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data), public endpoint **descriptions**, not market responses.

### Three-part scientific acceptance rubric

1. **Logical design consistency:** outcome-blind features and exact source clocks, event identities, non-overlap, cost accounting and bounded permit must be mutually consistent.
2. **Source readiness:** API availability is not proof of locally received, sequence-continuous, legally retainable, decision-known-at data; quote/depth is not a record of this portfolio's executions.
3. **Prospective economics:** fee-only references and synthetic contracts are not realized after-cost expectancy; reserve `UNKNOWN` / `NOT_CALIBRATED` for all omitted denominators and tails.

## 2. Material independent findings

### P2-C01 — the specified 24h/100k/50MiB permit cannot establish full-day high-frequency L2 admission [BLOCKER at SOURCE_ADMISSION gate]

**Researcher location:** lines 37–38, 66–78, especially 72–75.  
**Assertion tested:** A 24h capped public BTC sample can be used as an interim depth/quote feasibility check, but cannot be asserted sufficient for a **continuous 24h** book or for the strategy's final source gate.

**Independent bounded arithmetic witness, NOT observed exchange traffic:** Exactly one retained event per 100ms would be 864,000/day; per 500ms, 172,800/day; per 1,000ms, 86,400/day. A 100,000-message cap allows at most **1.1574 averaged retained messages/s over 24h** across **all** feeds, snapshots, REST, corrections and logs, *before* the stricter 50 MiB cap. If exactly 100,000 messages are written, total space allows **524.288 bytes per message including its proportional metadata and evidence overhead**. A 100ms or 500ms full-day depth stream is arithmetically incompatible with the record ceiling at its nominal cadence. Actual event traffic and raw payload-size distribution are **UNKNOWN**, so no live throughput estimate is asserted.

**Counterevidence / credit:** The Researcher's lines 73–75 **already disclose this incompatibility**, the first-bound-wins rule and the prohibition on pretending downsampled book updates are continuous. The objection is therefore to *downstream interpretations of readiness*, not an accusation of omission.

**Required closure:** Define two mutually exclusive permit outcomes **before collection**: (A) a budget-capped *partial/source-QC pilot* with `FULL_24H_DEPTH_NOT_ESTABLISHED`, actual contiguous accepted minutes, dropped/truncated time and precise first limit; or (B) a newly authorized, explicitly larger 24h continuous-capture budget with pre-proven envelope/abort logic. Never reclassify a partial pilot as a full-day market book or use the pilot to certify 4–24h fill-cause continuity. Clock gaps, route changes, buffer overrun or `pu` discontinuity invalidate affected book epochs.

### P2-C02 — the opportunity deduplication key is not uniquely an economic episode [HIGH; frequency-estimator identifiability]

**Researcher location:** lines 80–88, especially 82–84.  
**Concrete counterexample (invented timestamps, zero market data):** One physical sweep/refill episode is first confirmed by a qualifying 5m bar at 12:05 and reasserted by the 15m bar at 12:15; the document's illustrative key is `(instrument, side, first_qualified_decision_at, causal_structure_id, source_identity_hash)`. Taken literally, the two notifications have **different timestamps/keys**, even with identical cause and structure, and can double-count. A mere assertion that "repeated 5m/15m alerts are one episode" is not an executable deterministic equivalence relation. Choosing the equivalence tolerance after inspecting event counts would optimize observed frequency.

**Required closure:** Predeclare a unique *canonical structure seed* and an immutable episode-start clock from the **first causal structure detection**, independent of bar-confirmation time. Specify temporal and price-zone equivalence, opposite-side conflict handling, maximum cluster span, reopen/re-arm conditions after genuine invalidation, and monotonic IDs across 5m/15m confirmations. Freeze tie-breaking for same-clock candidates from T/R, without looking at future price or count outcomes. Record `raw_alert_id -> canonical_episode_id -> confirmed_id -> quote_screen_id -> portfolio_admission_id`; publish duplicate-suppression audit examples and count-conservation. If causal identity is not separable, report `RATE_UNESTIMABLE`, not 0.5/day.

### P2-C03 — proposed T/R causal mechanism needs transaction evidence that the draft collector does not explicitly admit [HIGH; mechanism/source mismatch]

**Researcher location:** lines 70–75 and 90–101, especially the T/R descriptions in 96–97.  
**Independent criticism:** The pilot allows `@depth`, `@markPrice`, 1m Last `klines`, premium/funding and configuration/clock calls. The **full contemporaneous executed-trade feed is not an allowlisted subscribed stream**. Changes to displayed depth alone do not distinguish a cancelled displayed order from its trade execution, nor prove true replenishing participant identity; 1m taker-buy aggregate is **not a tick-level transaction-attributed event tape**. Therefore claims such as "transaction-confirmed cessation of one-sided aggression", price-corridor migration via *actual executed inventory*, or book-sweep cause **cannot be established by this permit**. The book and 1m aggregates may still describe a prospective structural state as a proxy.

**Required closure:** Either (i) predeclare R/T as *quote-only descriptive* mechanisms and remove all statements requiring trade-level causal attribution, including "transaction-confirmed" language, **or** (ii) ask the Controller for a distinct, versioned, permission-and-cap-checked BTCUSDT `@aggTrade` / trade-tape source in a **new, separately costed permit**, with explicit clock alignment, coverage and quote/trade reconciliation. Adding tape changes the 100k/50MiB feasibility envelope, so it cannot be smuggled into the existing grant. Note: even public trade data + depth cannot identify hidden queue position, specific participant inventory or one's hypothetical maker fill.

### P2-C04 — receiver **connection epoch** is incorrectly offered as a positive signal-confirmation axis [HIGH; causal feature-quality and selection risk]

**Researcher location:** line 96 T mechanism ("across at least two distinct receiver epochs/checkpoints") versus lines 45 and 75 fail-closed WS reconnect rules.  
**Concrete counterexample:** In a healthy, uninterrupted 24h connection, `connection_epoch` remains a single receiver epoch. Requiring at least **two epochs** would select *reconnections* rather than persistent market liquidity, while combining order book states *across* epochs without a new snapshot would violate its own continuity contract. If the intended term is **two timestamps/checkpoints within one valid depth epoch**, that is scientifically different.

**Required closure:** Replace the ambiguous phrase with at least two causally separated, predeclared **checkpoints inside one sequence-valid epoch** and a finite minimum elapsed time. A reconnect invalidates continuity; resynchronize and start a new qualifying window. Any feature bridging disjoint epochs must explicitly carry `SOURCE_GAP / FEATURE_UNKNOWN` rather than silently retaining stale migration state. This is not a claim that any source code implemented an epoch error; it is a conflicting **draft event predicate**.

### P2-C05 — "executable" portfolio candidate and NORMAL/ADVERSE costs remain conditional, not source-admitted [HIGH; false precision / final economics gate]

**Researcher location:** lines 39–41, 49–64, 82–88, 103–109.  
**Claim tested:** Public book-visible ask/bid, size and filters can screen a hypothetical *taker crossing*, but cannot prove displayed depth is still present at order arrival or determine maker queue survival, actual venue ACK, cancellations, partial fills, stop-market gap VWAP, effective account commission, funding exposure of a non-existent trade, or execution-dependent adverse selection. The Researcher mostly recognizes this correctly, yet the Stage-4 category "order-eligible executable candidate" risks being reported as a venue-executable *trade*, and line 105 suggests a "pessimistic hypothetical cost" as a future alternative to actual fill evidence.

**Resolution:** Rename to **`QUOTE_SCREENED_CONDITIONAL_CANDIDATE`**, not actually executable; distinguish true `BROKER_ADMITTED` (unmeasured), `SIMULATED_PORTFOLIO_ADMITTED` and `ACTUAL_FILLED` (no data). Preserve the four P1A regimes explicitly:
- `FEE_ONLY_REFERENCE`: ordinary hypothetical 2/5 bp maker/taker per filled leg; M/M 4, M/T 7, T/T 10 **fee-only**, not achieved rates or maker probability.
- `NORMAL_EXECUTION`: requires jointly admitted actual intended-size, venue-aware *order/fill* distributions; **NOT_CALIBRATED** now.
- `ADVERSE_EXECUTION`: requires admitted conditional tails, nonfill/cancel censoring, latency and gap-risk; **NOT_CALIBRATED** now.
- `EXTREME_STRESS`: invented bounded shocks, no empirically measured probability, no true finite worst-case claim.

If user-account/real execution evidence is deliberately prohibited, return `EXECUTION_COST_NOT_IDENTIFIABLE` and keep the economic G2 scoring gate blocked. A conservative *synthetic envelope* is a conditional sensitivity result only; it **cannot** be called a measured 95th-percentile bound or prove net-positive expectancy. For taker-at-ask/bid prices, do not double-count the crossed spread; signed funding `-side * Q_at_settlement * M_at_settlement * settled_rate` remains incomplete if receiver-known-at or exposure membership is unverified. The old BASE22/STRESS44 costs remain exactly labelled as historical proxies, not NORMAL/ADVERSE truth. P1A full CI was `CONTRACT_BLOCKED`, despite 24 targeted synthetic cases passing — no implementation acceptance can be inherited from the design report.

### P2-C06 — frequency precision, coverage conditioning and outcome-independent occupancy must be gated *jointly* [MEDIUM; acceptance/specification gap]

**Researcher location:** lines 82–88.  
**Counterexample (theoretical, not sampled BTC events):** At target 0.5 qualified opportunity/day, a 24h pilot has idealized mean **0.5 event**. Even assuming a stationary Poisson mechanism, a 90-day period has expected count 45 and estimated Poisson SE `sqrt(45)/90=0.0745 per day`; regime clustering and outages worsen this. The Researcher correctly says 24h cannot validate 1/48h and that Poisson bounds are illustrations. But frequency acceptance also needs a **jointly precommitted** total-calendar coverage floor, consecutive-valid-source coverage definition, multiweek seasonal/regime balance, permissible missing/censored hours and worst uncovered gaps. A small "eligible_hours" denominator can otherwise produce a falsely encouraging conditional event rate, even if a second raw denominator is reported.

A deterministic conservative 24h occupation reservation avoids future-price leakage but is not equal to actual 4–24h stop/TP exit occupancy. With 24h reservation, overlapping 4h-return events may be suppressed that would be admissible in future real execution; with ex-post "stop released" reservation, the reverse is lookahead. Neither schedule is an empirically verified rate.

**Resolution:** Publish both **all-calendar** and **eligible-coverage** rates and label `RATE_NOT_ADMITTED` when coverage/power contracts fail. Choose the hypothetical 24h reservation as a **separate conservative scenario**, with optional shorter fully **predecision-fixed** reservation scenarios not selected based on observed counts. Freeze admission support thresholds (active independent UTC week/month blocks, annual/session mix, event de-clustering, overdispersion), lower confidence *rate* bounds, tolerance around 0.5/day and mandatory source-missingness strata before observing even outcome-blind frequency. A 50-trade sample count (from separate historical research gates) is not 50 independent event blocks. No trade frequency number in this document is a measured result.

## 3. Overall source-capability crosscheck (positive and negative evidence)

| Input / cash dependency | Public observed now? | Future **public** observable, only under new Controller permit? | Not identifiable from public-only receiver |
|---|---|---|---|
| Last 1m OHLCV and closed-bar semantics | Retrospective archives referenced in earlier published plans; actual historical ingest/PIT unverified | Yes: receiver-stamped public 1m, with completeness, full-source hashes, causal bar aggregation | Price within each 1m bar when touches collide; private fills |
| Mark/index and settlement Funding | Old reconstructed records and synthetic ledger are **not** prospective receipt evidence | Mark/index and *first-seen* funding history values; separate settled rate/Mark and forecast channels | Exchange unpublished publication instant, one's precise economic funding charge/inventory |
| Public bid/ask and L2 | API docs, no source-qualified 24h receiver | Yes, for bounded sequential epochs; quote freshness and visible size | Hidden orders, queue position, lost depth, actual realized spread/market impact |
| Order aggression / sweep attribution | Taker aggregates are a retrospective proxy | 1m aggregated taker share if approved; transaction tape **requires separate explicit permit** | Exact causal origin, liquidation vs discretionary flow, counterparty holdings |
| Fee and actual execution | Ordinary fee table *reference*; P1A/P1D **synthetic** only | Public applicable tier rules, hypothetical crossing cost | Actual effective commission, filled role mix, ACK, passive nonfill, stop-market VWAP, adverse-selection fills |
| OI / liquidation | Described interfaces only; currently source-blocked | Potentially after scope-specific admission, not inherited | Complete liquidation census or trader intent from a wick |
| Event rate target | **DESIGN 0.5/day, observation ZERO** | Independently frozen source-qualified episode counting only in another authorization | Positive expectancy, high win rate, live execution feasibility |

## 4. Permitted *future* source/cost/rate design, with closure dependencies

1. **Permit zero:** Controller must issue a *new* exact-SHA/symbol/endpoint/time/bytes/event/rights permit with explicit `STOP_ON_FIRST_LIMIT`. A 24h, `<=100000` total events, `<=52428800` bytes pilot can prove bounded receiver functionality, **not** 24h full-frequency L2 or 1/48h cadence. Do not autonomously enlarge caps or subscribe to trades/bookTicker on an implicit basis.
2. **PIT/sequence:** For each `BTCUSDT` record, bind venue/market type, provider event+transaction time (where supplied), published-at **if provided**, local first-seen monotonic+UTC, connection epoch, `U/u/pu`, depth snapshot identity, schema/version, correction/duplicate policy, batch SHA256 and retained-rights receipt. Provider event time does not imply published-at; *availability* is bounded by receiver time. All cross-stream feature intersections inherit the latest admitted receipt bound; out-of-order or unresolved settlement exposure is `UNKNOWN/COST_INCOMPLETE`. No backdated funding signals.
3. **Signal discovery:** At most two novel primary, mechanistically distinct T/R families, third V only observation; each precommits source feature/clock/episode mapping/null versus price/flow-only matched controls, direction, invalidation and 4/8/12/18/24h cap-selection family before looking at any outcomes. Don't cherry-pick W1/W2, R3 B/C, Goal-B or F3 identities with renamed parameters. Exposed research budget is inherited. P is source-deferred until genuinely synchronized executable spot/perp/Mark/index, funding and hedged-leg costs become available.
4. **Frequency:** Prospectively count raw alerts, canonical source episodes, PIT-qualified confirmations, quote-screened conditionally eligible intents and one-position portfolio-admitted **hypothetical** candidates as *different* metrics. Target 0.5/day is a planning constraint only; no execution mandate. A **24h source QC pilot cannot supply the 90d+ support** needed to test rate stability, nor independent return-based statistical power. Freeze calendar coverage and effective blocks before a separate counting grant.
5. **Execution/cost:** Keep maker fill role, commission tier, realized spread, depth deterioration, order/ACK/cancel timeouts, protective-gap VWAP, late funding and settlement position as separate evidence contracts. Fee-only 4/7/10 bp is an arithmetic abstraction; NORMAL/ADVERSE remain `NOT_CALIBRATED`, EXTREME remains synthetic. Missing position membership or source receipt is not a zero funding payment. Any actual net expectancy study remains blocked until economic sources and independently audited fill/cost assumptions are authorized and defensible.
6. **Gate hierarchy:** `IDENTITY/PERMISSION -> RIGHTS/RECEIVER/SNAPSHOT-QC -> SOURCE PIT ADMISSION -> COST/FILL IDENTIFIABILITY -> EPISODE/RATE ESTIMATOR FREEZE -> INDEPENDENT SCIENCE/POWER/MULTIPLICITY -> NEW G2 OUTCOME DISPATCH`. A design-review signoff **does not** jump any gate.

## 5. Independent reviewer acceptance table

| Component | Challenger adjudication | Mandatory next proof |
|---|---|---|
| Exact-SHA authority, two-path docs allowlist | **PASS (identity/design scope)** | Independent branch + SHA and one-file review diff verification |
| Baseline source categories and PIT caution | **PASS as draft** | Receiver-specific source qualification; new permit |
| Public collector 24h/100k/50MiB | **NOT FULL-DAY-L2-CAPABLE at nominal 100/500ms** | Scope pilot as partial, or obtain new separate budget |
| T/R novel mechanism feasibility | **REVISE / SOURCE_BLOCKED** | Specify transaction feed/clock or downgrade claims; checkpoint semantics |
| Economic episode identity and 0.5/day | **REVISE / RATE_UNESTIMABLE** | Canonical dedupe, independent season support and coverage gates |
| Four P1A regimes and ledger | **PASS concept; NOT_CALIBRATED in reality** | Actual executable order/fill evidence or explicitly hypothetical-only stop |
| Sparse bootstrap/power and earlier F1–F3 claims | **PASS nonpromotion/UNCALIBRATED label** | Independently approved statistical method before any new inference |
| Measured after-cost BTC 4–24h positive expectancy | **NOT TESTED / UNKNOWN** | Distinct G2 development-scoring grant after source and cost admission |
| Controller permission for source acquisition, accounts or trading | **NONE** | New exact-SHA Controller authority; no implied grant |

**Terminal recommendation:** Retain `METHOD_PLAN_READY` as **design-complete subject to documented revisions**, but **do not grant the current collector as proof of complete 24h depth or executable Alpha**. Reviewer finds six bounded objections, with one admission-level BLOCKER and methodological HIGH findings. Researcher should acknowledge/fix P2-C01–C06 in a future *separately authorized* document revision rather than editing this review. Controller alone can adjudicate next permits. No Alpha / DRY_RUN external integration / TESTNET / LIVE promotion.

## 6. Access, writing and unknowns audit

**Operations actually performed:** GitHub read-only file/commit/branch/compare against public documentation and **synthetic reports**; official developer documentation **pages**, no market-data response; one **new review file** on the independent docs branch. No private worktree access. No historical price arrays, strategy result arrays, PnL/rewards/trade ledgers, return labels, MFE/MAE, backtests, parameter search, historical replay or outcome-based optimization. No collector source created or run; no `/fapi` data endpoint queried; no live market/quote/funding values fetched; no private account/user-data access, credentials, orders or funds writes. No benchmark/test execution in this review. No old files modified.

**All unresolved unknowns (NOT implicitly zero):** real future market message rate and size, successful websocket route connectivity, regional/rights acceptance, actual 24h continuous depth capture capacity, sequence-gap probabilities, server/receiver UTC-offset quality, provider publication timestamps, Mark/Funding realized settlement timing and exact inventory membership, incomplete/out-of-order corrections, true maker/taker per-fill fee tier and discounts, hidden/order queue priority and maker nonfill, actual bid/ask at own arrival, latency/ACK/cancel/partial executions, marketable-limit role, stopped/gapped exit price, effective spread/slippage/impact distributions, unconditional p95/p99 cost tails, quote/capacity decay, exact economic episode equivalence and suppression sensitivity, overall calendar coverage, seasonality, rate precision, number of independent blocks, prospective return dispersion/statistical power, novelty of T/R/V, and whether any 4–24h BTC directional model has economically positive, transportable after-cost expectancy at ~one qualified opportunity per 48h. None is resolved by reading an API schema or a synthetic accounting test.

**Review independence boundary:** This is a concrete dissent/acceptance audit by ChatGPT-3, not copied self-review from the Researcher. It does **not** claim a third-party human credential, proprietary risk review, independent trading experiment, or Controller release authority. The Researcher's reported `CHALLENGER_PENDING` was correct **as of its commit**; the new reviewer branch changes the review status only for this separate frozen snapshot, not retroactively inside that immutable researcher file.

**Exact publication SHA:** record the resulting commit externally after the write; a Git commit cannot attest its own SHA inside its preimage.
