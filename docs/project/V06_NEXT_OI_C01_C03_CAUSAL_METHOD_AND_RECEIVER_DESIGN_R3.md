# OI C01–C03 R3 — Outcome-Blind Causal Method, Policy Timing and Receiver Witness Design

**Author:** ChatGPT-2-R, Independent Research Scientist. **Status:** `OI_CAUSAL_DESIGN_READY_FOR_2C_CHALLENGE` — documentary design only, NOT source admission or scientific/release approval.  
**Authority:** Controller's immutable dispatch commit `6750150ba88be5a036abc712af7657a43797ef4b`, path `prompts/v0.6/b_line/V06_NEXT_2R_OI_C01_C03_CAUSAL_DESIGN_R3.md`, Git blob `04d1a7c44017a786ccf5d95253c2a61a199c2cbf`.  
**Write allowlist / branch / parent:** ADD ONLY `docs/project/V06_NEXT_OI_C01_C03_CAUSAL_METHOD_AND_RECEIVER_DESIGN_R3.md`, branch `docs/v06-next-2r-oi-c01-c03-design-r3`, parent exactly `6750150ba88be5a036abc712af7657a43797ef4b`; no merges, force pushes, edits to frozen artifacts, executable source, tests or CI. The *output* commit and blob are verified after publication outside this text.  
**Scientific scope:** BTCUSDT Binance USDⓈ-M perpetual, 4–24h directional research objective, approximate one qualified opportunity/48h as an **unmeasured target**. No selection of thresholds from strategy outcomes.

## 0. Source lineage, independent review and enduring gates

| Role | Frozen commit | Frozen path and Git blob |
|---|---|---|
| Original 2-R F01–F06 corrected source contract | `1e830a238906771585b49d844d9cb58ad79bba36` | `docs/project/V06_NEXT_OI_PIT_R2_CORRECTIVE_SOURCE_CONTRACT.md` / `06801a1dc7aeae335f148fea826c28fdf668fe4c` |
| **Actually independent 2-C challenge of R2** | `69afad0a6b83e7d842dd1615f4f28c96d2e467a9` | `reviews/v0.6/b_line/V06_NEXT_OI_PIT_R2_INDEPENDENT_CHALLENGE.md` / `5f859cb7011aec8bba90cd73e4ba89869d35c8c4`; `CORRECTION_DESIGN_PASS_WITH_LIMITS` |
| **Consequential independent ChatGPT-1 audit of R2** | `8781a8e5439f6ed92d24ed69e2f9e0422b664745` | `reviews/v0.6/b_line/V06_NEXT_OI_PIT_R2_CONSEQUENTIAL_SOURCE_AUDIT.md` / `ac9dd16283be69292485d5366c3e545966c53aae`; `SOURCE_CONTRACT_DESIGN_PASS_WITH_LIMITS`, C01–C03 HIGH OPEN |
| Controller's R3 intake/adjudication | `6750150ba88be5a036abc712af7657a43797ef4b` | `reviews/v0.6/b_line/V06_CONTROLLER_R3_RESET_EVIDENCE_AND_NEXT_GATES_20261014.md` / `e9670518288d409b0a5268a4bb109e79564d9c82` |
| Historical source original (FAILED) | `5897e31661834272f2a4f2a8828fb987725cb2e0` | `docs/project/V06_RESET_R1_PRICE_SHOCK_OI_SOURCE_PIT_FEASIBILITY.md` / `3d231ab0ec55d62663ff6d5d2a2b0f247e676a94` |
| Independent historical novelty audit | `0c323641e4bcc1dcff43a06b02b931c72c15a24d` | `reviews/v0.6/b_line/V06_RESET_R1_PERP_FAKEOUT_ADVERSARIAL_NOVELTY_AUDIT.md` / `e2c227b7decadb94e721fbef02fa19384489b5df` |

**Review dispositions are not transferable.** Prior 2-C and 1 acceptance addresses **R2**, not this new R3; its independent 2-C challenge is PENDING, then 1 consequential review and 0 Controller decision. Previously exposed H32 is `INCONCLUSIVE`, H33/H34 `FALSIFIED` only under their original frozen identities; R3/Goal-B/F1–F3 price/volume/flow/basis variants retain historical trial-family exposure. New aggregate OI may be distinct information if source-qualified; it does **not** prove long/short crowding, initiator side or forced liquidation.

**Enduring status:** `SOURCE_NOT_ADMITTED / HISTORICAL_2021_2023_OI_SOURCE_NOT_READY / NOVELTY_CANDIDATE_SOURCE_BLOCKED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE`. Official rolling OI statistics are limited to latest ~one month, not a global proof all licensed archives are absent; 2021–23 alternate archival original first-known-at and legal rights are UNKNOWN. No collector approval or historical outcome access.

## 1. C01 — Three nested populations, transport and missingness must be visible

### 1.1 Source-neutral episode universe `E_X`

`E_X` is a deterministic, auditable **price/X-only parent cohort** created from all scheduled, quality-admissible X observation times before asking whether OI exists. Include *all* closed-bar price shock/reclaim events that meet an independently pre-frozen X structure, as well as source-neutral X rejections in a separate funnel. X consists of past-only structure/price, ATR or realized-volatility **as risk/scale**, completed volume, momentum, prior admitted aggressor flow if used, side, UTC predecision regime and instrument identity. ATR multiples are **not z-score sigmas**. No newly optimized thresholds are selected in this document.

Each `e∈E_X` has `episode_id = hash(contract_spec_version, X_formula_version, shock_start, shock_end, side, predeclared_rearm_id)`, stable source-ref hashes, first known X-confirmation instant `t_X_safe(e)`, episode side, source-neutral X stratum and a strict one-episode/one economic shock policy (dedupe 5m/15m alerts; deterministic cooldown). Define `E_X` **without** checking OI, future path, fill result, realized return, quote after a later outcome or subsequent occupancy. For portfolio analysis, chronologically enumerate the exogenous `E_X` candidate stream *before* policy-specific occupation changes. The portfolio can suppress different events under different policies, but it must not delete them from the common exogenous ledger.

**Observation-denominator guard:** Maintain `N_scheduled_UTC_slots`, `N_X_valid_slots`, `N_X_source_missing_slots` and `|E_X|`; neither healthy-source-only sampling nor zero-event slots can disappear from the calendar denominator. If X source itself is missing the event may be unobservable; represent that as **unknown opportunity exposure**, not “no trade signals.” A 72h prospective 15m OI **source-only** pilot cannot establish `|E_X|` or operational strategy frequency without a separate method permission.

### 1.2 Availability states on every E_X record

Define `Z` as two or more consecutive, unit-consistent **venue-native** 15m OI history buckets, all versioned and safely first-received, with provider period ends no later than the allowed X feature cutoff. `Z_value` may be computed only if every required version and receiver/PIT invariant is satisfied. Preserve `Z_status` as one of:

`TIMELY_VERIFIED` (all requirements met by fixed deadline); `ABSENT_NO_RESPONSE`; `LATE_FIRST_RECEIPT`; `GAP_OR_NONCONSECUTIVE_BUCKET`; `REVISION_CONFLICT_OR_ORDER_UNKNOWN`; `CLOCK_UNCERTAIN_OR_ROLLBACK`; `INVALID_CONTRACT_OR_UNITS`; `RIGHTS_UNVERIFIED`; `STALE`; `SOURCE_OUTAGE`; `NOT_EVALUATED`. Explicit precedence: any unverified rights, clock, unit or source identity **fails closed**, even if a plausible quantity string exists. Optional multiple cause flags retained along with a primary status. Distinguish *“record not observed at deadline”* from *“OI was actually zero”*: they are never equivalent. Re-polling the API after deadline cannot rewrite `Z_status_at_deadline` or a past decision. Changes in previously known provider values create later append-only versions, not a revision of the earlier decision state.

Fix **three** audit cohorts:

- `E_X`: full, pre-OI source-neutral event universe, including every OI status; target of operational policy comparisons.
- `C_Z = {e ∈ E_X : Z_status_at_D(e)=TIMELY_VERIFIED}`: source-available subcohort with source validity **before** any discretionary action; target of the pure conditional information comparison only. No late-arrived or later-repaired OI is retro-admitted.
- `C_EXE ⊆ C_Z`: events where a *common* predeclared executable/quote/risk eligibility guard at the delayed clock also passes, before looking at which model would trade. This is a more selected diagnostic cohort, **never the full target**. Maintain `|E_X|, |C_Z|, |C_EXE|` and all attrition reasons separately; the primary A estimand declares which universe it is based on.

A complete-case A effect `E[U_A(X,Z)-U_A(X)|C_Z]` or conditional executable diagnostic `|C_EXE` does **not** identify `E[U_B(policy_OI)-U_B(policy_X)|E_X]` in the presence of source/volatility/transport selection; do not transport A to the full population by assumption.

### 1.3 Outcome-blind attrition, stratification and precision/power freeze

For every `E_X` event, record only pre-decision variables: side (LONG/SHORT), UTC hour/day/week/month, regime from *previously completed* price/volatility, source provider route, receiver epoch, deadline, miss-cause/version and X-only structural flags. Publish counts `n_X`, `n_Z_timely`, `n_eligible_delayed` and `n_miss_status` for **each** stratum, plus `P(C_Z|side, volatility quartile predeclared from past-only reference, UTC month/week, receiver_epoch)` and days of source non-observation. Do not infer “random missingness.” **Regime-conditioned availability** is a possible collider/selection mechanism.

**Fixed proposed source-readiness feasibility criteria (not grants or observed achievements):** before any *separately authorized* source-frequency study, freeze a 95% two-sided coverage interval method that can handle dependent calendar clusters (nonparametric UTC-week or appropriate exact cluster-level alternative reviewed by an independent statistician), with `target half-width ≤ 0.10` for timely `C_Z/E_X` *overall*, plus a minimum **lower 95% bound ≥ 0.80** overall and **≥ 0.60** for each predeclared critical side × volatility regime. Require ≥ **20 distinct UTC calendar weeks** with eligible `E_X` events across multiple UTC months as a **preliminary coverage-support floor only**; this is neither 20 independent trades nor outcome-power certification. Report uncertainty when a stratum has insufficient events; never silently pool away failing stratum gates. Calendar weeks with zero episodes remain reported in frequency/source outage denominators. If cluster CI cannot be meaningfully estimated, or predeclared precision gates fail: `SOURCE_COVERAGE_INCONCLUSIVE` and no population claim. These numbers are **design proposals**, not Controller-approved operational quality limits, calibrated source behavior, or an invitation to force entries. A 72h pilot cannot pass the 20-week rule and is scoped to basic receiver QC only.

**Future outcome-testing requirements, without observing outcomes here:** preregister a single primary A information endpoint and distinct primary B policy/account endpoint; familywise two-sided Type I budget at most 0.05 across prespecified A/B primary families and all candidate directions/horizons/ablations/selection identities, or a more conservative independent protocol. Require ≥80% pre-specified prospective power for an economically meaningful *after-cost* minimum effect δ_net>0 based on independently authorized, uncontaminated clustered variance and feasible exposure, **not** a guessed historical PnL sigma. Freeze independent calendar-block count and minimal cost-effect-size before any outcome scoring. If no legally admissible independent pilot variance/sample or insufficient effective support exists, return `POWER_NOT_ESTABLISHED / NO_TRIAL`; 30/50 simulated events are not an automatic power PASS. The old F1–F3 degenerate studentized max-|T| intervals remain **UNCALIBRATED**, never reused to claim significance.

**Synthetic counterexample, no outcome labels:** Suppose 100 E_X episode identifiers; 60 low-vol events have timely OI and 40 high-vol events have `LATE_FIRST_RECEIPT`. `C_Z=60`, and a paired statistic on those 60 is **by definition conditional**; there is no justified extrapolation to 100. No returns, profitability, occurrence frequency or actual source coverage is asserted by invented counts.

## 2. C02 — Two distinct estimands, clocks and policies

### 2.1 Common clocks, features and market-eligibility conventions

For each e, freeze:
- `t_shock_end`; `t_confirmation_complete`; `t_X_safe`, the earliest time **all X inputs including confirmation** are safe receiver-known and the X-only intent could be decided.
- `t_Z_end(k)` for the historical-statistic periods; only completed periods **ending no later than the frozen X confirmation cutoff** can be eligible Z. `t_Z_first_complete_safe(k)` uses immutable first complete receiver UTC upper bound, not provider period end or a retrospective REST read.
- `D(e)=t_X_safe(e)+W_fixed` rounded forward to a predeclared receiver scheduler tick, where `W_fixed` is an independently precommitted bounded OI wait time from **X-only known information**. **D must not depend on when or whether OI actually arrives or on any later price/return**. Proposed 5-minute wait and 5-second scheduler step below are **invented timing examples, not approved production thresholds**. Deadline, allowed Z period ends and feature stale cutoff are fixed *before* source exposure. If waiting policy uses a shorter/longer wait, that creates an additional registered trial.
- `t_early(e)`: fixed next eligible X decision/quote tick after `t_X_safe`; `t_delayed(e)=D(e)` (common decision for A). Enforce `t_early < t_delayed` only where their predeclared schedule actually permits; equality is a special recorded case.
- X predictions/thresholds use **X snapshot as known at t_X**, held invariant for the information contrast at D. Both A arms get identical X; neither silently incorporates a later price confirmation, reoptimized side, added liquidity-flow statistic or new technical indicator.
- At each actual hypothetical decision time, *operational safety* checks can use only that time's separately admitted quote age, instrument filters, spread/size and deterministic invalidation state, identically for the same-clock A arms; intervening prices **cannot** be used to select D or rewrite the X signal. A quote from t_early is not fresh at D merely because it existed. If t_delayed quote is missing/stale, the delayed intent is ineligible for **both** A arms and counted as a common guard failure; keep it in `C_Z`.

### 2.2 Estimand A — CONDITIONAL information of Z at a **fixed delayed clock**

**Question:** Given the same X episode, same source-qualified timely Z and same precommitted fixed D, does genuinely independent observed OI Z improve the decision when everything else—including temporal entry disadvantage—is identical?

**Target:** `C_Z`, and separately disclosed `C_EXE` sensitivity; never full E_X by implication.

**Counterfactual policies:** `a0(e)=π_X(X_at_tX, common_quote_guard_at_D)`; `a1(e)=π_XZ(X_at_tX, Z_as_known_by_D, same_quote_guard_at_D)`, both **evaluated at D(e)**. A1 can differ only through Z and a pre-frozen causal function, including a decision not to act. Before outcome observation, retain both candidate decisions on every `C_Z` episode; do not condition the estimand on executed trades or winner/loser outcomes. Same side eligibility, risk budget, hypothetical stop/TP, funding, fee model and quote/entry convention apply.

**Formal future estimand:** `θ_A(C_Z) = E_{e∼C_Z}[ U_D(a1,e) − U_D(a0,e) ]` under common D, with per-episode no-action decisions included; companion paired direction-score contrast `E[S_D(a1,e)-S_D(a0,e)|C_Z]` is predictive diagnostic only. Both utilities require **future separately authorized outcomes and execution-cost evidence**; they are symbols here. A `θ_A>0` alone would not establish practical early-versus-wait benefit or any source-rights gate.

**Null and falsifier (future only):** `H0_A: θ_A ≤ 0` after all precommitted, realistic conditional costs, adjusted multiplicity and effective-calendar power. Reject a proposed increment if Z was reconstructed from X, arrival version after D, side/cost/quote logic differs, common cohort differs, improvement occurs only after posthoc source exclusion, or required independent after-cost lower bound is not strictly positive. Underpowered or uncalibrated CI is `INCONCLUSIVE`, not proof that Z has zero information.

### 2.3 Estimand B — FULL-E_X naturally early X policy versus **fixed-wait OI policy**

**Question:** Is a real policy that gives up the earlier X opportunity in exchange for a bounded OI wait operationally better, after lost entry time, quote ageing, unfilled orders, invalidation while waiting, and portfolio occupancy? **This is a different estimand from A.**

**Common exogenous episode population:** all `E_X` in UTC chronological order, including `OI_UNKNOWN`, source-disabled and quote-ineligible episodes. Policy-specific portfolio states evolve separately, but both consume the same raw candidate stream and common calendar/source-outage ledger.

**Policy B0 — natural early baseline:** `π_E(X)`: at `t_early(e)` decide from X and then-current eligible quote; if common source/risk guards fail => NO_ACTION. Do not wait for an OI report. Its hypothetical occupancy may block later events, which must be logged.

**Policy B1 — wait then OI, primary fail-closed design:** `π_W(X,Z)`: do **not** submit any hypothetical order before fixed `D(e)`. At D, if any required OI is absent/late/revised/untrusted, deadline exceeded or quote/risk/confirmation validity fails, branch `NO_ACTION`; otherwise apply predeclared X+Z decision on X frozen at t_X, Z as receiver-known by D. No late OI backfill or discretionary delay after D. An X-only fallback on `OI_UNKNOWN` is **not** silently equated to this primary B1; if desired it is `π_W_FALLBACK`, a distinct, separately budgeted alternative policy trial to preregister before seeing outcomes. Even fallback **cannot** place an order before D.

**Formal future account-level estimand:** `θ_B(E_X) = E[ V_portfolio(π_W; E_X, T0:T1) − V_portfolio(π_E; E_X, T0:T1) ]` with identical starting flat state, common fixed notional/risk/collateral, the same execution-cost/settled-funding methodology and continuous opportunity/occupancy recording. `V` must account for flat/no-action as **zero cash flow from *that action***, never assign a zero market return to the absent trade or drop it from denominator. Mark any open inventory and unresolved exit/funding as `COST_INCOMPLETE`, **not** closed profit. Portfolio interference/occupation means B cannot be inferred from summing independent per-trade θ_A.

**Mandatory pre-outcome B observables:** X eligible timestamp, D, elapsed wait, stale/invalidation reason, recorded best bid/ask/visible size at each policy's *different* decision clock if later authorized, order-intent/simulated nonfill status under a documented conservative fill contract, hypothetical entry/stop protection ACK only if actually witnessed, time at risk, funding-settlement membership, portfolio conflict/occupancy suppression, cooldown, drawdown disable, no-action branch and source gap exposure. Public OI-only QC cannot create actual execution fills or quotes. The same fee/fill/stop/funding model must be applied, but a common *cost model* does NOT imply identical realized costs at different times. Do not claim a maker fill when no real queue/ACK witness exists.

**Null and falsifier (future only):** `H0_B: θ_B ≤ 0` on full E_X, after timing/occupancy, all actual or independently bounded costs, noise/selection adjustment and adequately powered familywise inference. A positive θ_A does **not** falsify H0_B; if B fails due to wait/unknown-OI rate, report `POLICY_NOT_ECONOMICALLY_ADMITTED` without claiming Z has no conditional information. Do not infer executable Alpha from source-only timeliness/coverage success.

### 2.4 Timing-only worked example (invented; no prices or outcomes)

All invented 2026-10-14 UTC values, no actual receiver logs:
- Confirmation bar closes `12:15:00`; X receiver-known safely by `12:15:02`; natural X-only scheduled action at `12:15:05`.
- 15m OI period ends `12:15:00` but is first safely receiver-known only by `12:19:40`. A fixed `W=5m` after `12:15:02` with a 5s tick places `D=12:20:05` for **all** X episodes of that scheduling class whether Z exists or not. Thus B has waited **5m**, independently of the 12:19:40 arrival, compared with 12:15:05. Had Z never arrived, D is **still** 12:20:05, B1 chooses NO_ACTION, and B0 remains eligible at 12:15:05 if its own quote/risk guard passes.
- Estimand A compares delayed-X and delayed-X+OI **at 12:20:05**, not dynamically at `t_Z+5s`. Under invented source proof both use a common fresh quote decision guard at D. Estimand B compares X action at `12:15:05` against the wait policy at `12:20:05`, with no assumed later price or profit. An actual source gap/revision/clock failure would make Z UNKNOWN and B1 NO_ACTION.
- These are synthetic clock strings, NOT observed OI publication lag, quote age, possible fill price, trade count or historical PnL.

### 2.5 Separate reporting and multiplicity

Report (i) A within C_Z/eligibility subset, (ii) full E_X B, (iii) coverage, missingness and no-action/occupancy gaps **separately**. Do not combine them into one “OI uplift.” Future 4/8/12/18/24h endpoints, both sides, fixed-wait alternatives and fallbacks consume one predeclared familywide search budget together with relevant historic exposure, not a new alpha identity after threshold retuning. A and B primary tests require joint control over multiplicity; no F1–F3 invalid max-T inference or fantasy iid-minute effective-N. If source uncertainty or realistic fill bounds remain unknown, economic verdict `NOT_TESTABLE` regardless of signed-return diagnostic.

## 3. C03 — Receiver-first complete observation and independent synthetic witness contract

### 3.1 Native source/time semantics and contractual limits

Read-only **public specification** (not market responses): https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data, USDⓈ-M:
- `GET /fapi/v1/openInterest`: present snapshot, IP Weight 1, `openInterest` numeric string, `time` labelled **Transaction time**, **not** receiver/published time.
- `GET /futures/data/openInterestHist`: history statistics `period=15m`, `sumOpenInterest`, `sumOpenInterestValue` as distinct numeric strings, `timestamp` **period end**, IP Weight **0** but **1000 requests/5min/IP special quota**, public rolling latest one month only. No original publication/first-ingress timestamp field guaranteed.
- `GET /fapi/v1/time`: current `serverTime`, Weight 1, useful in bounded RTT/offset observation but **not sufficient as independent UTC synchronization attestation**. No historic first-known reconstructed by later REST download.
- Raw numeric quantity, native value units, symbol contract multiplier/quote specification, source rights, access jurisdiction and effective quota must be independently admitted before collecting. OI contraction is not evidence of long-only liquidation or forced sellers.

**Rights fail-close:** Public GET and separate Binance Vision dataset terms (https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md) do **not** grant arbitrary REST archiving, redistribution, commercial use or a 2021–23 validated historical OI archive. Require approved legal/terms receipt naming product, legal entity, geography, use/storage/retention, redistributability, effective date and reviewer before any collection grant.

### 3.2 Proposed receiver evidence envelope (no receiver exists by this task)

For every HTTP attempt, including unsuccessful requests, define an immutable signed/hashed **attempt envelope**:
- `collector_commit_sha`, `build_blob_sha`, `config_digest`, `source_rights_receipt_id`, `venue`, `BTCUSDT USDⓈ-M contract_spec_version`, endpoint/method + canonical **public** query (no credentials), response media/schema version, attempt/retry ID, budget-leasing identity, HTTP status/header used-weight and observed retry instructions.
- `receiver_boot_id`, `monotonic_clock_id`, `connection_epoch`, `process_epoch`, `request_start_mono_ns`, `headers_recv_mono_ns`, `body_last_byte_mono_ns`, `body_integrity_complete_mono_ns`, separately sampled UTC wall time at each checkpoint and monotonic-to-UTC attestation **interval**. “First complete” means fully received, validated untruncated body plus a durably retained raw-byte record; a merely sent request, response header or first JSON field is not known-at.
- `clock_attestation` must reference an independent chrony/NTP/PTP or other approved UTC-discipline measurement stream/version, bound offset + uncertainty across the *entire request interval*, document drift/steps/leap behavior and retain calibration raw hashes. A single `serverTime`, a claimed `40ms`, or a wall clock written into JSON is **not** proof. The monotonic-to-UTC mapping interval upper bound `UTC_hi(body_integrity_complete_mono_ns)` is conservatively used as the earliest safe receiver known-at after **durable complete payload**. If durability (append/fsync/ack) occurs later, known-at for reproducible decisions is no earlier than safe upper UTC bound of that durability event. Missing durability/epoch evidence => `SOURCE_WITNESS_INCOMPLETE`.
- `raw_response_bytes_sha256` computed from unchanged bytes; `raw_byte_length`; immutable raw blob/object pointer with storage checksum; `canonical_parser_version`, `normalized_field_digest` and parse result, time-unit and decimal-string handling; `parent_attempt_digest`, append-only receipt stream sequence `seq`, signer/store witness if available, duplicate/revision link. Never fill an actual SHA field from fabricated example data. A hash with no independent stored bytes establishes no auditability.
- `provider_transaction_time_ms?` for snapshot; `provider_period_end_ms` and `period=15m` for aggregate; optional `provider_published_at` remains `UNKNOWN` unless independently evidenced (do not equate period end or HTTP Last-Modified with original publication); `first_seen_version_id`, `first_complete_known_at_UTC_safe_hi`, parser/rights/clock admission state. Historical data first downloaded later gets *later* first-known-at; no backdating.
- `source_version_key=(exchange, contract_spec_version, endpoint, symbol, period, provider_period_end_ms)`; snapshot keys instead include provider transaction clock and request/receipt identity, with no forced 15m equivalence. First observed response for aggregate version is v1; canonical-field changed on repeat => v2 with `corrects(v1)` and separately persisted first-seen, never mutate v1. Bytes differing only in representation but canonical values identical remain separate raw receipts linked to same normalized version; conflicting values on same logical key create immutable new version. Earlier decisions resolve **the latest proven version known at their original decision clock**, never the “latest eventual” file.
- Time-known invariant `K(v)=max(provider_period_end_safe, receiver_durable_first_complete_UTC_hi, authenticated_provider_publish_hi_if_any)`. Require `K(v) < t_decision_tick` (strict if same-boundary ordering uncertain), every prerequisite K qualified, same units and consecutive needed 15m periods. Incomparable epoch time domains, provider end later than deadline, clock rollback, missing prior bucket, corrected version not provably ordered, undecodable payload or unproven rights ⇒ `PIT_UNKNOWN / NO_OI_ACTION`.

**Append-only durability / replay specification:** Every read attempt, raw body/hash and version decision is appended to a write-ahead journal with an explicit stable sync/atomic commit receipt before being made “visible to decision”; crash between receiving body and durable record results `INCOMPLETE_INGRESS`, no retroactive first-known. Replay preserves original `seq` and known-at; re-keyed byte-identical dupes cannot create a new earlier version; conflicting duplicates preserve both observations with audit/quarantine, not silent overwrite; conflicting first-seen epochs fail closed. Hard stop rather than synthesizing provider publish/receiver time. Execution implementation and tests require *different* Controller permit.

**Clock fail-closed:** At source admission time, Controller must freeze a single quantitative bound (R2 draft proposed gross offset+uncertainty ≤5000ms and unexplained step >1000ms; both **unmeasured suggestions**), proof interval coverage, max signal stale age and continuous external synchronization. Step/rollback mid-response, monotonic counter reset, clock attestation gap, signature/hash mismatch, schema/contract unit drift, or an uncertified conversion across connection epochs => `CLOCK_UNKNOWN`. All suspect sources cause NO_ACTION in OI-gated policy, not favorable fill/reconstruction.

### 3.3 Synthetic witness *types* and negative-case expected results (NOT executed)

The following is a **hypothetical contract**, never an actual payload/witness:

`{
  "synthetic_only": true,
  "instrument": "BTCUSDT",
  "venue": "BINANCE_USDM_PERPETUAL",
  "endpoint": "/futures/data/openInterestHist",
  "period": "15m",
  "provider_period_start_ms": 1791979200000,
  "provider_period_end_ms": 1791980100000,
  "provider_end_utc": "2026-10-14T12:15:00Z",
  "receiver_first_complete_utc": "2026-10-14T12:19:40Z",
  "receiver_durable_utc_safe_hi": "2026-10-14T12:19:40.050Z",
  "receiver_epoch": "MOCK_20261014_EPOCH_A",
  "receiver_first_complete_mono_ns": null,
  "external_clock_attestation_id": null,
  "raw_body_sha256": null,
  "raw_blob_ref": null,
  "rights_receipt_id": null,
  "provider_publish_at": null,
  "sumOpenInterest": "20403.637",
  "sumOpenInterestValue": null,
  "quantity_contract_unit": "UNVERIFIED",
  "source_admission": "REJECT_SYNTHETIC_ONLY"
}`

All times above are invented for C02 clock demonstrations. The mock intentionally lacks raw bytes, real monotonic clock, UTC attestation and rights; it MUST fail `AUTHENTIC_SOURCE_ADMISSION`. Its `provider_period_end_ms` is a period label, not known-at. The old R2 arithmetic `20403.637/20850.120−1=−0.02141392951215626` (fraction, **−2.141392951215626%**) is **illustrative** only; exact base/quote units and multiplier remain unverified.

| Synthetic case (future independent negative test, not run now) | Required verdict / invariant |
|---|---|
| S01 Valid complete two-period source, raw bytes, contract version, external UTC intervals, durable receipt before D | `PIT_ELIGIBLE` **only in the test fixture**; production source still `NOT_ADMITTED` |
| S02 Provider period_end 12:15, first complete receiver 12:19:40, candidate at 12:15:05 | `BLOCK_LATE_OI`; no backdating |
| S03 Same fixture with independently attested safe durable time 12:19:40.050, D=12:20:05 | `PIT_TIME_ELIGIBLE` if other fields pass; no price/return claim |
| S04 Late revision at 12:28 to bucket used at 12:20, compare replay-as-known at 12:20 | Original v1 preserved; later v2 never changes 12:20 feature |
| S05 Duplicate identical raw payload under a new request/attempt | Append attempt, preserve original version/first-seen; no duplicate policy event |
| S06 Same key different quantity/source payload, indeterminate ordering | `REVISION_ORDER_UNKNOWN / BLOCK`; append both, no silent replacement |
| S07 Response truncated / raw digest missing / fsync not confirmed | `SOURCE_WITNESS_INCOMPLETE / BLOCK` |
| S08 UTC wall clock steps backward 2s mid-response; monotonic continues, attestation not covering step | `CLOCK_UNKNOWN / BLOCK`; no guessed offset or cross-epoch splice |
| S09 Monotonic epoch reset/reconnect with no witnessed bridge | `CLOCK_UNKNOWN / BLOCK` |
| S10 Missing or nonconsecutive 15m bucket; later REST returns both | `OI_UNKNOWN` at original deadline; later backfill cannot repair earlier decision |
| S11 Rights missing or wrong contract multiplier/base/quote version | `SOURCE_NOT_ADMITTED / BLOCK` |
| S12 Boundary safe upper receiver time == decision tick without ordering witness | `BLOCK_AMBIGUOUS_BOUNDARY`; wait next legal tick |
| S13 OI missing on 40/100 synthetic E_X events | `C_Z=60`, B includes all 100, missing-state stratification; no inference about PnL |
| S14 X-known 12:15:02, early 12:15:05, Z-known 12:19:40, D=12:20:05 | A both delayed at D; B early vs wait; no ex-post selection of D |
| S15 OI never arrives by D, early X policy would have acted | A event not in C_Z; B1 `NO_ACTION`, B0 evaluated; no fictitious zero future market return |
| S16 Same event arrives in 5m and 15m alert channels | One E_X episode ID, with separate raw alert provenance; no double portfolio opportunity |
| S17 Stop-market trigger without fill and no ACK | Position remains unresolved; never declare completed after-cost trade |
| S18 Shared-IP quota lease unknown / 429 / 418 / dynamic schema drift | `COLLECTOR_PERMIT_INELIGIBLE`; no automatic retries or IP rotation |

No tests, assertion runner, CI, market observation or trading was performed. These are executable **future test specifications**, not a claim of test results. Future independent 2-C should attack the counterexamples with adversarial synthetic traces.

## 4. C03 bounded future source-QC permit *proposal* and stop hierarchy

R2 budget remains strictly a **DRAFT**: BTCUSDT USDⓈ-M **72h** fixed UTC window (nominal 288 distinct 15m closures), history `openInterestHist period=15m limit=3` once per 5m (864 nominal), snapshot/time each ≤1/hour (72+72 nominal), one bounded transient history retry per slot only if separately granted; total ≤**2000 HTTP attempts**, ≤**6000 returned response items** and ≤**16 MiB of raw bodies + logs/manifests**, first cap wins. Nominal 1008 requests, worst retry+initial/final bracket ≤1876 (arithmetic only). Count errors/revisions/duplicates, verify current exact provider weights: OI history documented IP Weight 0 but special **1000 calls / rolling 5 min / IP**; snapshot and server/time Weight 1; shared-IP weighted and special quota ledgers must atomically reserve *every rolling window* and consider all co-located workloads. Schedule-slot limits do not prove rolling quota. Rights, geolocation, byte-size feasibility, source clocks and publisher terms remain UNKNOWN. Stop 418/429, drift, illegal entitlement, unbounded retries, gaps or counter failure; no source-gap interpolation, no evasion or rotation.

Even a perfectly completed 72h pilot could only assess **limited prospective public source delivery/QC**, not conditional OI Alpha, 20-week coverage gate, 48h candidate-rate stability, 2021–23 original historical receiver known-at, effective fee/queue/stop fills, long-short participant provenance or source rights retroactively. A Controller **new exact-SHA source/time/resource/legal authorization** is required *before any collector execution*, independently reviewed synthetic witness tests and after 2-C/1 design challenge. Source status stays `SOURCE_NOT_ADMITTED`.

## 5. Falsifiability and 2-C / 1 / 0 handoff

**Reject A information claim if:** X differs between arms, Z is inferred rather than venue-observed, any receipt after fixed D is backdated, D chosen from OI arrival, common quote/staleness rule differs, missingness silently removes parent records, positive estimate depends on retrospective thresholds, calendar-block inference invalid or outcome power unavailable.  
**Reject B deployable policy claim if:** full E_X/no-action count missing, X early counterfactual artificially delayed, fallback/NO_ACTION switched after observing labels, quote/occupancy/fee/stop/funding contracts differ, decision inventory conflicts or censored orders falsely count as realized PnL, 4–24h endpoint/cost family was selected after exposure.  
**Reject C03 source readiness if:** no external attested UTC/monotonic bound and raw durable first-seen proof, conflicting revision not retained, rollback/cross-epoch ambiguity, unsupported contract units/rights, source/cap/API uncertainty, or a purported historical source whose first-known clock comes only from later REST downloads.  
**Kill or mark inconclusive:** attrition/coverage gates fail, power cannot be established, no comparable predecision OI, distinct OI feature absent, historical identity rebranding, source permits nonexistent, or executed cost witnesses remain uncalibrated. Do not interpret null nonrejection as proof Z has no information; report `UNKNOWN/UNDERPOWERED`.

**Open unknown ledger:** legally licensed historical 2021–23 OI archive and true original arrival/version history; REST/source storage permissions, rights and region; real source rates/fees and quote cost; provider OI publication clock; exact venue units/value, revisions and first receipt; external clock calibration/rollback; actual OI source gaps and regime dependence; X exposure and full E_X event rate, C_Z coverage and effective calendar blocks; optimal/feasible wait time; conditional information θ_A, account utility θ_B, execution/fill likelihood, after-cost expectancy, tails, future power and true 48h cadence. **No numeric market conclusion has been computed.**

**Review ordering:** 2-R publishes one exact-SHA new document and verifies parent/ref/diff/blob. Independent **2-C** freezes that *output* SHA and blob, reviews C01/C02/C03 and synthetic negative cases, and publishes its OWN authorized review under a separately dispatched task. Consequential **ChatGPT-1** reviews unresolved high-impact semantics. **ChatGPT-0 Controller** alone can grant any new source collector permit, experiment, G2 change or integration. An author cannot declare independent PASS, and this document is not such a grant.

**Actual access/test log (to be checked after remote publication):** Public GitHub immutable prompt/R2/2-C/1/Controller documentary reads, plus public official provider API **documentation** only. Live or historical exchange/market/OI/quote responses 0; historical outcome/PnL labels/backtests/sweeps 0; account/private paths/credentials/orders 0; protected H39/H40/H41/Forward/Final Holdout or owner data root reads/metadata probes 0; executable code/test/golden edits 0; CI/test runner invocations 0; merges 0. Only new documentary Git branch/file commit allowed.

**Terminal design disposition:** `OI_CAUSAL_DESIGN_READY_FOR_2C_CHALLENGE / SOURCE_NOT_ADMITTED / NOVELTY_CANDIDATE_SOURCE_BLOCKED / G2_ALPHA_NO_GO`.
