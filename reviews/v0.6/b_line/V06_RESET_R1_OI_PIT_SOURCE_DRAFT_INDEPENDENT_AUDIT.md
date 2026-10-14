# RESET R1/R2 — Independent BTC OI/PIT Source Draft Audit

**Terminal verdict: `SOURCE_DRAFT_FAIL`.** This is a narrowly scoped **documentary/source-design failure**, not evidence that authentic prospective BTC OI cannot exist, that a hypothetical trading strategy is unprofitable, or that the official short-window REST sources are wholly unusable. The existing draft contains several material provider, permissions, PIT and causal-method defects that must be corrected before even a **separate** public-only micro-QC collection permit could be considered.

**Binding effective gate: `SOURCE_NOT_ADMITTED`.** Retain `SOURCE_NOT_READY` for the unsubstantiated 2021–2023 historical OI horizon; the official REST one-month statistics window does **not** cover that target. At most, *a corrected future* prospectively received source could become `PARTIAL_SOURCE_QC_ONLY` after independently authorized QC. **No market collection, retrospective OI import, trial, price/return label analysis, historical rerun, strategy scoring, TESTNET, LIVE or real-money action is permitted by this review.**

**Independent reviewer:** ChatGPT-1, independent source/PIT scientific auditor, session conducted 2026-10-14 (UTC+08:00). NOT the target author (Gemini BOOST Architecture / Codex read-only analyst). Separate branch and independently fetched immutable Git blobs establish the review workflow, not cryptographic authentication of model or human authorship. No source author-provided reviewer PASS was accepted or invented.

## 1. Immutable dispatch/target and independent read receipts

| Role | Full exact commit SHA | Path and Git blob |
|---|---|---|
| **Independent audit Controller dispatch** | **`70fde472d83c3ed9ba24d130ba8d7ec36c4e1fa5`** | `prompts/v0.6/b_line/V06_RESET_R2_OI_PIT_SOURCE_DRAFT_INDEPENDENT_AUDIT.md` / **`e0e87d3fee3dbe696ce43d8b672cb0800512fcf7`** |
| Baseline author dispatch | `ceb851765b84e8e83b78caa6ceecbc665e57c02f` | `prompts/v0.6/b_line/V06_RESET_R1_PRICE_SHOCK_OI_SOURCE_PIT.md` / `e7ee11eaee342f7b849ce7626a0c987d27ab5167` |
| **Frozen target, OI source/PIT design** | **`5897e31661834272f2a4f2a8828fb987725cb2e0`** | **`docs/project/V06_RESET_R1_PRICE_SHOCK_OI_SOURCE_PIT_FEASIBILITY.md` / `3d231ab0ec55d62663ff6d5d2a2b0f247e676a94`** |
| Historical novelty Crosswalk (separate author's work, not independent PASS) | `194cbac1d6846dd6ea4fa11b3dd6567b01969bd9` | `docs/project/V06_RESET_R1_HISTORICAL_MECHANISM_AND_NOVELTY_CROSSWALK.md` / `9df803ce8147724e91be98f960bc0588bdf0837f` |
| Independent fakeout novelty challenge | `0c323641e4bcc1dcff43a06b02b931c72c15a24d` | `reviews/v0.6/b_line/V06_RESET_R1_PERP_FAKEOUT_ADVERSARIAL_NOVELTY_AUDIT.md` / `e2c227b7decadb94e721fbef02fa19384489b5df` |
| Read-only existing public connector code | `13e3a710b137efeec2e21e3002f748834ec0cc22` | `src/btc_quant_agent/data/binance.py` / `bf4de7511ee1bac0e48bf7a5fac2f49da6d70cbc` |

**Target freeze independently confirmed:** the exact target branch `docs/v06-reset-r1-price-shock-oi-source-pit` resolves to `5897e316...`. Full commit parent `ceb851765...`. Independent Git comparison returns one commit ahead/zero behind and **only one newly added target document** (+378/-0 lines). Fetch by fixed commit/path and separate Git blob `3d231ab...` yielded **byte-identical** 31,959-character source (378 populated lines plus trailing newline). The prior authorization and target path exist and match; therefore this is a substantive audit, **not** `INCOMPLETE_TARGET_UNFROZEN`.

**Primary provider documentation examined directly, without market-data requests:**
- Binance official USDⓈ-M REST Market Data catalog: `https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data`, specifically sections **Open Interest**, **Open Interest Statistics**, and **Check Server Time**; observed 2026-10-14.
- Source documentation confirms `GET /fapi/v1/openInterest` returns a **present snapshot**, weight **1**, `symbol`, `openInterest`, and `time` documented as **“Transaction time”**; it gives no historic `startTime/endTime` parameters.
- `GET /futures/data/openInterestHist` supports `symbol`, `period` 5m/15m/30m/1h/2h/4h/6h/12h/1d, `limit <= 500` (default 30), and optional `startTime/endTime`. Official restrictions: **latest one month** and **1000 requests/5min per IP**, with endpoint **IP Weight 0**. Response includes `sumOpenInterest`, `sumOpenInterestValue`, `timestamp` explicitly labelled **“End time of the period, in milliseconds”**, and an additional documented `CMCCirculatingSupply` field. Nothing here proves publication/first-known-at latency or absence of future corrections.
- `GET /fapi/v1/time` has IP Weight 1 and response `serverTime`. It is an endpoint for observing server time, **not** proof that application wall-clock and monotonic-to-UTC mapping have been continuously disciplined.
- Binance official Vision dataset terms (distinct from REST API rights): `https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md`, version dated 2026-08-26, impose express non-commercial/redistribution restrictions on **Vision datasets**. Do **not** treat the archive's license as blanket consent for REST ingestion or later monetized automated trading.

## 2. Independent source verification matrix

| Audit question | Independent check / evidentiary boundary | Decision |
|---|---|---|
| Correct BTC instrument and REST family | `BTCUSDT` USDⓈ-M `/fapi` vs `/futures/data` distinguished; no COIN-M `/dapi` source substituted. | **PASS** |
| Snapshot vs historical aggregated OI | Snapshot is present-only; statistics support 5m and 15m+ and bounded one-month history. | **PASS with qualification** |
| Exact public weights and throttles | Draft lines **68** and **317–333** attribute OI-statistics weight 1 / 2400 per minute and ignore official special `1000/5min`; official OI-statistics **IP Weight 0**, separate **1000/5min**, while snapshot weight **1** and time weight **1**. | **FAIL — F02** |
| Schema, units and symbols | Official response names, `timestamp` period-end and value fields verified; however docs call them “total open interest” and “total open interest value”, **not** an explicit audited BTC contract multiplier or a publication latency. `quote=USDT` is plausible for BTCUSDT but requires venue contract/quote specification validation before a general units assertion. | **QUALIFIED** |
| Historic horizon and absence claims | Latest-one-month REST history is documented and historical price klines do not supply independent authentic OI; **not** proof that no archival 2021–2023 OI dataset exists at any licensed vendor or independently archived prospective receiver. | **FAIL — F01** |
| UTC, first receipt, PIT and revisions | Positive rule `decision >= max(complete_period_end, actual local receipt)` is right in spirit; draft does not fully freeze reliable first-seen observation, response-version lineage, UTC wall/monotonic bridging or fail-closed clock-change policies. | **FAIL — F03** |
| Episode identification and OI contribution | Descriptive price shock + OI contraction is **possible as a hypothesis**; cannot infer which side liquidated. However draft's same-t confirmation and conditional null do not freeze a causal, matched `X` vs `X+OI` comparison. | **FAIL — F04** |
| Proposed public pilot, rights and QC | Endpoint scoping and prohibitions are a useful start, but declared legal entitlement is unverified; runtime/cadence/caps and revision/gap/age/QC evidence cannot deliver the promised continuity validation. | **FAIL — F05** |
| Crosswalk and novelty | Independently challenged crosswalk documents overlapping price/volume/flow/reclaim; fakeout review `0c323641...` assigns `NOVELTY_CANDIDATE_SOURCE_BLOCKED`, not novel alpha. A truly independent observed OI delta is `DISTINCT_REQUIRES_NEW_SOURCE` *conditional on verified PIT* only. | **ACCEPT STOP** |

## 3. Material independent findings

### F01 — HIGH: rolling REST unavailability overclaimed as global / permanent historical source absence

**Frozen draft lines 30, 36, 91, 143–146, 356–370:** source says “Public authentic source data does not exist”, “Historical Non-Existence” and “Permanently missing from public Binance REST infrastructure”. The official Binance USDⓈ-M OI statistics endpoint documents **“Only the data of the latest 1 month is available”**. This establishes the endpoint's retrospective service horizon, **not** a universal proof that authentic 2021–2023 records were never collected or cannot exist under any vendor/legacy archive/license. Official price-only klines cannot synthetically recreate OI; that independent negative constraint remains valid.

**Correct disposition:** `OFFICIAL_ROLLING_REST_2021_2023_UNAVAILABLE` / `HISTORICAL_AUTHENTIC_OI_2021_2023_NOT_ESTABLISHED`, with alternative licensed archival source, matching instrument continuity, timestamps, rights and period first-known-at all **UNKNOWN**. Historical multi-year trial `SOURCE_NOT_READY` remains blocked. Do not declare an unsearched vendor universe permanently empty.

### F02 — HIGH: official per-endpoint weight/rate limits misreported; permit arithmetic demonstrably false

**Draft lines 68, 316–333.** The OI-statistics endpoint's official IP Weight is **0** (not 1); special IP limit is **1000 requests per 5 minutes**. Snapshot weight=1; /time weight=1. A paper policy of **5 requests/second** permits **300/min**, which is **12.5%** of a quoted **2400/min** generic capacity, NOT “less than 5%”. If sustained specifically against OI-statistics, five requests/second would produce **1500 requests/5min**, exceeding its published **1000/5min** limit despite zero generic IP weight. Such a cap is an *upper bound*, not assurance of safe use; a stricter combined collector envelope with endpoint-specific quota and other same-IP traffic accounting is required. The actual proposed one-query-per-15m would be vastly lower *if applied to all requests*, but is not reconciled with simultaneous snapshot, statistics and time-check calls.

**Correct disposition:** draft permit is **NOT AUTHORIZED** and cannot be issued verbatim. Reconcile per-endpoint budgets including retries/429/418, a period-sequenced 15m data fetch and separate clock checks, and conservative aggregate account/IP accounting in a subsequent Controller-approved design.

### F03 — HIGH: insufficient first-known-at proof and internally inconsistent skew/revision gates

**Draft lines 31–33, 61, 89–93, 136–144, 152–185, 203–223, 335–350.**

- Official `openInterestHist.timestamp` is a **period-end** label; official snapshot `time` is a **“Transaction time”** field, not documented as proof of a matching-engine replay clock, gateway publication time or local arrival. `T_pub` is **unobserved**, so a later historical REST response cannot be backdated to a period-end or retrospectively asserted to be accessible for a past decision.
- The necessary invariant `available_at >= max(complete_window_end, first_payload_received_at)` holds only for an actually recorded, authenticated receiver event on a trusted UTC clock; the draft example equates availability to a single response receipt while lacking durable first-seen identifiers/response version retention, multi-poll payload chronology, publication uncertainty and epoch/clock-discontinuity safeguards. Pair wall-clock with request/response **monotonic** readings and preserve raw payload + stable hash and first-receipt UTC, with explicit uncertainty/clock-skew bound; if unprovable, `UNKNOWN` and no PIT use.
- The draft's provider matrix **line 138** permits **30,000 ms** skew, whereas collector QC **line 341** aborts above **5,000 ms**: inconsistent binding contract. A one-off `/fapi/v1/time` query alone does not establish local NTP synchronization under latency or clock steps.
- Treat duplicate `(symbol,period,timestamp)` with distinct payloads as **separate observed revisions** in an append-only audit trail; fail closed for any decision until revision and originally known version are resolved. Do **not** rewrite or silently replace a historical record, assume the snapshot provider event value is irrevisable, or infer first availability from later polls.

**Required freeze:** UTC timestamp mapping + monotonic connection epoch + request/first-complete-response timings + provider server offset bounds/round-trip uncertainty + raw-byte payload hash/version + append-only revision history + period-end closed-bar check + explicit jointly known `t_decision`. Future records cannot be admitted based on period-end alone.

### F04 — HIGH: insufficient causal episode/ablation contract; illustrative thresholds improperly posed as settled methods

**Draft lines 236–301, 369–373.** The draft supplies a price-shock/reversal control A and a price/vol/volume-momentum control B, but `X+OI` is not explicitly defined as the *same eligible episode cohort with the only difference being OI Z*. `Alert_B` imposes `VolSpike` and `MomExhaust` gates absent from the OI arm, introducing substantial **selection and event-composition confounding**. A meaningful direct ablation needs fixed eligible `X = [price, realized-vol, volume, momentum, formerly tested flow/basis if used]`, identical event anchors/candidate sides, identical PIT and occupancy/cost contracts, with nested `X` versus `X+OI` and a matched OI-present event cohort. Predefine the no-OI missingness arm; missing OI must not silently create a different population.

**Timing fault:** the shock is indexed at `t`, while confirmation is described as `t+1` or `t+2` but `R_conf(t)` appears in `Alert(t)` without freezing separate shock_end, OI first-known, confirmation_close, entry_earliest, invalidation and episode merge/rearm clocks. Require all required features first received *before* the alert decision, not merely assigned to bar `t`. Bind horizon `4–24h` to the first executable post-confirmation timestamp and prohibit post-shock selection across an unknown period.

**Scale fault:** draft's `Z_price=|\Delta P|/ATR_{14}` uses an ATR price-unit denominator; it is **not** a standard deviation or independently calibrated “2.5 sigma” statistic. Both shock `2.5` and `OI decline 1.5%/2.0%` are **ILLUSTRATIVE_ONLY, NOT PREREGISTERED, NOT APPROVED**, cannot become authorized entry thresholds simply by publication. Specify whether OI `-0.015` is a fraction or `-1.5%` in percent and respect symbol units. `MomExhaust` is not fully defined in B; the one-sided null on *unsigned subsequent price returns* must be replaced with a direction- and event-matched, friction-aware incremental estimand in any later independently authorized preregistration. Absence of rejection with sparse data **does not prove computational redundancy or falsify all OI mechanisms**. Episode frequency (one opportunity/48h) and conditional power remain UNKNOWN.

**Mechanism boundary accepted:** OI reduction means fewer jointly outstanding long/short matched contracts, not which participant was forcibly liquidated; NO inference of one-sided liquidation/long-unwind or position stress from OI alone.

### F05 — HIGH: draft pilot permit cannot substantiate proposed QC claims; legal/entitlement not established

**Draft lines 143–146, 305–352.** A future pilot limited to **120 seconds total ingress** with at most one poll per **15 minutes** cannot by itself observe even two consecutive newly published 15m windows, let alone estimate live **15m gap frequency**, missingness, first publication delay distribution, revisions or robust epoch continuity. A `limit=30` REST back-query can sample 7.5h of *existing* 15m rows but **does not establish historical receiver-known-at for those bars**. A 500-record cap and a 5 MB payload cap can bound resource usage; they cannot substitute for temporal coverage/first-receipt proof. The draft's stale rule `now - end > 30min` is a policy, **not** a validated performance cap; if availability delay is substantial, the source may be infeasible at 15m decision cadence. A period-continuity check must not “repair” actual gaps by forward-filling.

The provider matrix line 144 and permit lines 311–318 simply declare “Binance Public REST API Terms; non-commercial research use” as entitlement. An unauthenticated GET and a public documentation page do NOT independently establish archival storage, redistribution, commercial/non-commercial deployment, jurisdictional rights or trading-data licensing. **Vision archives have separate explicit 2026-08-26 terms**, including non-commercial constraints; do not misapply those terms to REST or assume free reuse. Verify current applicable exchange terms/licensing and use limitation with a qualified reviewer/rights holder **before any future permit**; current answer: `SOURCE_RIGHTS_UNKNOWN`.

**Correct disposition:** A *separately scoped, Controller-authorized* prospective QC design may later propose collection with an observation window and explicit per-endpoint quotas sufficient to measure first-seen delay/gaps without crossing legal or protected boundaries. Such a permit is not created here. Real prospective continuous OI archival absence remains UNKNOWN.

### F06 — MEDIUM: field/source semantics and illustrative mock need provenance tightening

**Draft lines 59–62, 85–90, 134–139, 203–226.** The official API supports `openInterest`, `sumOpenInterest`, `sumOpenInterestValue`, `timestamp` but the published docs do not by themselves certify the draft's generalized “BTC contracts”/“USDT notional” mapping, price-conversion basis or whether future symbol specs change. Separate native base-quantity and provider “open interest value” fields and validate instrument multiplier/quote unit using venue contract specs; **never** mix a Last or Spot price sampled at different times. A snapshot `time` is documented as **Transaction time**, not guaranteed “matching-engine server snapshot instant”.

The mock JSON uses `period_start_ms=1776168000000` (2026-04-14 12:00 UTC), `period_end_ms=1776168900000` (2026-04-14 12:15 UTC), while `connection_epoch_id=`epoch_20261014_01`` suggests 2026-10-14. As a synthetic illustration it is not evidence of a real ingestion/clock record; explicitly mark **synthetic** and correct inconsistent date labelling in any next draft. Its OI change `20403.637/20850.120-1\approx -0.02141393` is a dimensionless fraction (−2.141393%), not “−0.0214%”. No live record, verified payload SHA or duration was obtained.

## 4. Independent novelty challenge / falsification and governance boundaries

- Frozen historical Crosswalk `194cbac...` classifies price/volatility/volume/momentum, 5m/15m reclaim/fakeout structures, funding/Mark and taker-flow as **overlapping older mechanisms** (R3, Goal-A/B, F1–F3, v0.3.12 H32–H34). It grants only `NOVELTY_POSSIBLE_SOURCE_BLOCKED` for a truly separately observed `OI_DELTA`; its author terminal is a draft `CROSSWALK_READY_FOR_INDEPENDENT_CHALLENGE`, **not independently admitted**.
- Independent adversarial fakeout audit `0c323641...` gives `NOVELTY_CANDIDATE_SOURCE_BLOCKED`; no liquidated counterparty identity, verified OI causality, or free-standing fresh family exists. It explicitly requires an incremental OI effect over old X plus all relevant old signals/cost/occupancy/multiplicity. Renaming an old price/reclaim/flow strategy is not novelty.
- Only a prospective non-admitted source-design hypothesis and **future** `X` vs `X+OI` protocol are eligible for additional Controller deliberation. Unknown event frequency, true fees/slippage, horizon, opportunity/48h rate, and net alpha cannot be inferred now.
- The draft's `SOURCE_NOT_READY` retrospective stop is **kept**. Historical 2021–2023 OI is not certified admissible. There is no `SOURCE_ADMITTED` status, no market collection authority and no trial registration.

## 5. Recommended finite corrections (not authorized execution)

1. Replace global “permanently no authentic OI” claims with **official one-month REST unavailability + other independently authenticated historical sources UNKNOWN**; retain the multi-year historical `SOURCE_NOT_READY` gate.
2. Correct OI-statistics **weight 0 and separate 1000/5min limit**, snapshot/time weights 1; fix the 5 req/s arithmetic and specify requests/period, retry and shared-IP policy.
3. Freeze source/period/receipt UTC and monotonic lineage, first-seen/version/revision history, defensible server skew thresholds and fail-closed PIT; keep all original raw payloads if a permit is later authorized.
4. Define exactly comparable `X` and `X+OI` matched cohorts, fixed episode and confirmation timestamps, non-overlapping eligible decision windows, cost/occupancy/null semantics; forbid treating ATR ratios as a sigma Z-score or threshold examples as approved parameters.
5. Resolve REST and Vision legal rights separately and rewrite a bounded first-publication-delay pilot consistent with 15m periodicity, duration, record/byte/rate caps and measurable QC, under a **separate fresh Controller authorization** only.

**Final independently attributable terminal: `SOURCE_DRAFT_FAIL`**. Accept only the broad public endpoint distinction, limited rolling REST source, first-receipt PIT principle, and rejection of one-sided liquidation inference as useful **design subcomponents**. The submitted document is **not** a verified source contract; `SOURCE_NOT_ADMITTED`, `G2_ALPHA_NO_GO`, `G4_TESTNET_NO_GO`, `LIVE_NO_GO`, `REAL_FUNDS_WRITE_NONE`.

## 6. Execution and publication receipt

**Actual operations:** connected GitHub exact-SHA fetch for dispatch/target/crosswalk/fakeout/source-code; exact source Git blob checksum identity via GitHub; branch HEAD and target commit-parent/diff checks; static reading of the public repository client (`collect_derivatives` uses **1h OI `limit=2`** and does not expose independent 15m first-seen ledger); *documentation-only* direct review of official Binance developer REST docs and official Vision licensing text; static numerical unit/cap arithmetic. This report contains independently reached conclusions and source quotes, not self-certification by the target author.

**Prohibited activities performed: ZERO:** market API/REST calls, WebSocket connections, downloads of actual OI records, trade data or price-history, source runner/backtest, outcome/PnL or alpha scoring, private/protected/holdout inspection, account/credential access, testnet/live/trades, source code or frozen report modifications, GitHub CI invocation, bypass or merge.

**Write allowlist:** ONLY add `reviews/v0.6/b_line/V06_RESET_R1_OI_PIT_SOURCE_DRAFT_INDEPENDENT_AUDIT.md` to new isolated branch `docs/v06-reset-r1-oi-pit-source-independent-audit` created from immutable Controller dispatch `70fde472d83c3ed9ba24d130ba8d7ec36c4e1fa5`. No changes to Stage A author branch or frozen files; review commit SHA / Git blob are objectively verifiable after GitHub publication.
