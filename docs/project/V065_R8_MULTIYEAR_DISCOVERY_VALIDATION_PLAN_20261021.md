# R8 — Multiyear Strategy Discovery, Rolling Selection, and Locked Validation

> **HISTORICAL PLAN — superseded by R8-8 completion (2026-10-22):** This plan's coverage-map → multiyear price-family sequence is retained as provenance, not the active task queue. R8-7 is closed negative and all five R8-8/Argon tasks are complete. The only prepared next task is metadata-only source feasibility, `PREPARED_NOT_DISPATCHED`; see [the current source-feasibility plan](V065_NEXT_GATE_LIQUIDATION_FLOW_SOURCE_FEASIBILITY_PLAN_20261022.md) and [R8-8 results](V065_R8_ARGON_RESEARCH_RESULTS_20261022.md). Do not launch the old Task 1 or multiyear backtest sequence from this historical plan, and do not touch protected validation/holdout outcomes.

**Date:** 2026-10-21

**Purpose:** Reach a reproducible, economically meaningful exploratory BTC strategy result using broad historical data, without restarting completed R1–R5 work or creating another governance-heavy stage.

## 1. Project state at authoring (2026-10-21; historical)

- Executable main after PR #10 merge: \`v0.6.5@40c70c740f352d1b444decb75276196d17a72dd2\` (refresh remote HEAD before executing).
- PR #10 is merged, but \`exploratory_retrospective_v1\` remains a synthetic-only scaffold; it does not calculate real historical PnL.
- R1–R5 feature findings and their existing artifacts are unchanged. Earlier studies have not established actual after-cost Alpha.
- Existing research records report broad 1-minute BTC price history and uneven derivative-feature coverage. The native Binance Top Trader ratio is sparse in 2022 (1,115/8,760 hourly origins usable) and a frozen 2025 X-feature span from February through December is unavailable/excluded. Never infer complete derivative coverage from price-candle coverage.
- The Owner-reported existing \`FINAL_HOLDOUT\` interval is 2026-02-01 through 2026-08-01. Confirm its exact registration/manifest metadata during Task 1 without opening outcome payloads. Do not use this interval for discovery, threshold selection, cost calibration, or repeated inspection.

## 2. Research time split

Use this as the proposed R8 split. Task 1 must reconcile it against existing registration/manifest metadata once. Do not perform broad legacy archaeology.

| Period | Intended role | Rule |
|---|---|---|
| 2021-01-01 through 2023-12-31 | Discovery | Explore and falsify mechanisms. Preserve every candidate and failure; use time-ordered development splits inside this period. |
| 2024-01-01 through 2024-12-31 | Rolling selection | Use expanding/rolling walk-forward windows. At each origin, train only on data earlier than the validation window. Freeze the candidate families, feature definitions, exit rules, and cost model selected by the end of 2024. |
| 2025-01-01 through 2025-12-31 | Locked validation | One predeclared evaluation after candidate/config/cost assumptions are frozen. First check existing metadata for prior outcome-based exposure. If prior selection exposure cannot be ruled out, label it exploratory/selection-contaminated; do not claim a clean independent validation. Never repeatedly retune on 2025. |
| 2026-02-01 through 2026-08-01 | Existing final holdout | Keep sealed during R8 discovery, feature selection, parameter selection and cost calibration. Only run the final predeclared test after the preceding candidate and protocol are frozen. The run is one-shot; a failed result cannot be used for another tuning cycle. |

The period 2026-01 and data after 2026-08-01 are not automatically part of any split above. Do not quietly mix them into training or relabel them as the existing final holdout. Any use requires a separate, clearly named exploratory/forward window.

If Task 1 cannot establish a historical exposure boundary from existing metadata, record it as UNKNOWN and proceed with the safest useful exploratory path. Do not turn unknown historical provenance into a clean-OOS claim or block all price research.

## 3. Historical Task 1 plan — one-pass data coverage and split map (not active)

**Scope:** A concise inventory only. No new backtest, model fit, candidate scoring or outcome evaluation in this task.

1. Inventory the existing local BTC source manifests/indexes and monthly coverage metadata for 2021–2025: 1m price bars, spot/perpetual basis inputs, volume/flow inputs, OI, Top Trader ratios, funding, mark/index/premium. Report only fields and periods that actually exist; distinguish raw files present, parseable rows, and causal feature-ready rows where the existing metadata supports it.
2. Report monthly coverage and gaps separately for the **price baseline** and each **derivative feature family**. Keep native venue/product/source namespaces distinct. Do not fill publisher blanks, infer missing Top Trader values, or assume another venue is the same observable.
3. Read existing registration, split manifests, and receipts to map the recorded boundaries for A-line, \`FINAL_HOLDOUT\`, \`FORWARD\`, \`OOS\`, H39/H40/H41 where present. Metadata only: no protected outcome payloads, PnL panels, or protected samples. Do not search recursively through the entire old archive. If a boundary is not recoverable from the designated metadata, report UNKNOWN and the exact missing metadata pointer.
4. Check whether any 2025 outcome/strategy-evaluation exposure is recorded. Do not infer a clean 2025 validation from the fact that prior notes say zero formal real-return labels were evaluated; report the actual evidence and any unknowns.
5. Return a short table, source/index paths, command(s), exact gaps, and one decision. Do not download new data or start any strategy/backtest during Task 1.

**Acceptance:** One reproducible coverage/split report; price versus derivative coverage separated; explicit 2025 exposure status; the existing final-holdout metadata identified without reading its payload. Stop when these are answered once.

## 4. Historical strategy-search sequence after Task 1 (not active)

### Price families — first wave

Evaluate four materially distinct, interpretable families on the price baseline, using bounded predeclared parameter grids and the same execution/cost accounting:

1. **Trend continuation / momentum:** multi-horizon return and trend persistence; test a small volatility/regime filter.
2. **Breakout and retest:** range breakout, causal confirmation/retest, and explicit failed-breakout exit logic.
3. **Conditional mean reversion:** only under predeclared non-trending/range/extreme-deviation states; do not buy every large down move.
4. **Volatility compression → expansion:** identify compression using only past data and test whether expansion has a directionally useful follow-through.

Register every candidate/config hash, including failures. Avoid combinatorial grid search and post-hoc threshold fishing. All families use a common causal entry convention and explicit 4–24h holding/exit rules.

### Derivative enhancements — at most two

Only test these when the source matrix shows actual causal coverage:

5. **Price versus OI/position-state divergence:** compare price-only X against X+Z on both matched eligible origins and the full X population. Native Top Trader position ratio and aggregate OI must not be treated as equivalent.
6. **Funding / premium / basis crowding:** use funding as both a possible state feature and a real cash-flow cost where settlement applies. Do not assume a high funding rate automatically predicts reversal.

No derivative family is mandatory if source coverage is insufficient. Missing features are not imputed merely to enlarge sample size.

## 5. Astra's one-time role

After the Task 1 coverage map, ask Astra once for a bounded independent strategy plan—not a repository-wide audit. Astra may use the existing R1–R5 failure record and the coverage map, but must not inspect 2025 validation outcomes or 2026 final-holdout results.

Deliver at most two genuinely distinct new mechanism hypotheses, each with:
- causal observables and exact source-family requirements;
- mechanism and directional prediction;
- control X and incremental Z;
- fixed entry/exit and 4–24h horizon;
- small parameter range;
- falsification condition and required coverage;
- why it is not a renamed R1–R5 candidate.

Do not ask Astra to implement code, run backtests, or re-audit the repository. Codex remains the executor; Controller decides which, if any, enter the registered search.

## 6. Evaluation contract

Every candidate report must include, where calculable:
- trade count and non-overlapping event clusters;
- gross and net return, fees, funding cash flows and slippage sensitivity;
- win rate, average winner, average loser, payoff ratio, Profit Factor, net expectancy per trade;
- maximum drawdown, exposure, turnover, holding-time distribution;
- results by year/regime and source-eligible population;
- baseline versus candidate on matched eligible origins, plus full baseline population;
- missingness, independent event-block support, and concentration in a single year/regime.

If actual execution/fill data is unavailable, label the report as modeled economics, not realized PnL. If any cost component is missing, show the incomplete-cost result separately and do not describe it as fully net-of-cost.

Use time-ordered validation, train-only normalization and appropriate purge/embargo for overlapping labels. Keep 2025 locked after its one permitted evaluation; keep the 2026 final holdout sealed until final freeze. Any previously exposed interval must be marked exploratory/selection-contaminated.

## 7. Historical execution sequence and stop rules (not active)

1. **Task 1:** Codex completes the one-pass coverage/split report. No backtest in Task 1.
2. **Task 2:** Controller freezes the split and launches Astra's one-time two-hypothesis plan using only pre-2025 outcomes and Task 1 coverage.
3. **Task 3:** Codex implements/runs a common price-baseline backtester and the four bounded price families on 2021–2023 discovery plus chronological 2024 rolling selection.
4. **Task 4:** Freeze candidate/config/cost assumptions; run the 2025 locked validation once only if exposure metadata supports the intended label. Otherwise label it exploratory and do not make an independent-validation claim.
5. **Task 5:** Preserve the existing 2026-02-01 to 2026-08-01 final holdout until all prior choices are frozen; run one final test only under the registered protocol.
6. **Task 6:** Add up to two derivative mechanisms on their own actual source-eligible samples, then consider ETH/BNB/XRP only after the BTC pipeline works.

Controller B directly dispatches and accepts routine scoped tasks. No broad security/compliance review, repeated scope approvals, exhaustive legacy archaeology, broad CI cleanup, or standing multi-agent audit chain. If a non-core process concern appears, log it briefly and continue. If blocked, state one exact blocker and the nearest useful fallback.

## 8. Status labels

- \`READY\`: task prompt prepared.
- \`DISPATCHED\`: task was actually sent.
- \`RUNNING\`: supported by an execution receipt.
- \`BLOCKED\`: one exact blocker identified.
- \`COMPLETED\`: deliverable and reproducibility receipt exist.

**Immediate next measurable deliverable:** the one-pass R8 data coverage and split map, not another strategy run or governance document.
