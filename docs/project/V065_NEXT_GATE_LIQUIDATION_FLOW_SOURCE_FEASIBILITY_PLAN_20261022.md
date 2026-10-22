# Next Gate — Liquidation-Flow Source Feasibility Plan

**Date:** 2026-10-22
**State:** `PREPARED_NOT_DISPATCHED`
**Workstream:** B-line BTCUSDT 4–24h research
**Evidence baseline:** [R8-8 and Argon Research Results](V065_R8_ARGON_RESEARCH_RESULTS_20261022.md), based on five isolated task worktrees at executable baseline `40c70c740f352d1b444decb75276196d17a72dd2`. This is not a fresh verification of the moving remote `v0.6.5` HEAD.

## 1. Decision and current status

R8-7's frozen 545-event, 8-hour X-only reference is closed as economically negative: gross cash PnL `-3,081.95 USDT`, base ex-funding `-11,802.83 USDT`, stress ex-funding `-20,523.72 USDT`, base PF `0.719`; all three years are base ex-funding negative. Funding-inclusive net remains unknown. Do not rescue the reference through post-hoc side, delay, threshold, regime or exit changes.

R8-8 reconciled the existing ledger and selected exactly one next mechanism to test for **source feasibility**: directly observed forced-liquidation flow exhaustion, contract-count open-interest destruction, and a still-displaced perpetual/spot anchor. This is an untested hypothesis, not an established signal. R8-A/B/C/D are completed engineering/design tasks with synthetic or descriptive evidence only; their worktrees remain isolated and unmerged.

**Next decision:** determine whether a lawful, historically usable, timestamp-compatible source intersection could support the selected mechanism. This is metadata-only and does not authorize market-payload reads, outcome evaluation, a backtest, integration, or publication.

## 2. Immediate task — metadata-only feasibility

**Task ID:** `V065-R8-NEXT-SOURCE-FEASIBILITY-01`
**Status:** `PREPARED_NOT_DISPATCHED`
**Suggested executor:** Codex or Antigravity; Controller B owns acceptance.
**Prepared prompt:** [V065_R8_NEXT_SOURCE_FEASIBILITY_METADATA_ONLY_R1.md](../../prompts/v065/controller-dispatch/V065_R8_NEXT_SOURCE_FEASIBILITY_METADATA_ONLY_R1.md). This prompt is not dispatched until Controller explicitly assigns it.
**Mode:** read-only metadata/source-contract inspection. Do not launch a live collector or download market payloads.

### Required inventory

For one candidate venue and native contract, record each field family separately:

1. **Forced liquidation flow:** side-specific event/report availability; event semantics and aggregation; native quantity units; event timestamp; archive/API historical retention and known completeness limitations.
2. **Contract-count OI destruction:** native contract count and contract multiplier; observation cadence and timestamp; evidence that the series is not merely USD-notional OI whose value changes with price.
3. **Independent spot anchor:** venue/product, native timestamp, available historical interval, and whether the reference can distinguish spot-led repricing from perp-only convergence.
4. **Executable perpetual evidence:** native bid/ask and sufficient depth or trade/quote data; timestamp semantics and plausible decision-to-entry latency; source of spread, slippage and fill/no-fill assumptions.
5. **Time provenance:** event time versus publish time versus receiver/ingestion time; whether actual receiver-first-known timestamps exist, and whether their evidence is immutable and tied to the source bytes. Documentation of an exchange event timestamp alone is not receiver-clock proof.
6. **Costs and funding:** applicable fee tier assumptions, spread/depth evidence, funding settlement timestamps and coverage, and which fields are observed versus modeled.
7. **Rights and historical coverage:** source terms/use permissions, venue/product identity, retention limits, coverage metadata, native time zone/units, schema/version, manifest/checksum where already available, and known missingness.

### Allowed operations

- Read official source documentation and terms, existing schema/specification files, catalog entries, manifests, coverage matrices, receipts and already-materialized metadata.
- Verify existing path/hash references and summarize stated date ranges, field presence, units, timestamp semantics and known missingness.
- Clearly separate provider-documented availability from locally archived metadata, payload-level QC, actual receiver-clock evidence and lawful authorization.

### Prohibited operations

- No market-value row/payload inspection, new market-data downloads, live collection, account/private endpoints, outcome labels, PnL calculation, candidate backtest, parameter search, or use of protected 2024–2026/Forward/Final/OOS outcomes.
- Do not claim payload completeness, authenticated receiver clocks, source admission or historical PIT based solely on documentation, an exchange event timestamp, a schema, or a hash of unrelated bytes.
- Do not substitute price/volume proxies if direct liquidation flow, contract-count OI or time provenance is unavailable.
- Do not merge or cherry-pick the R8-A/B/C/D worktrees as part of this task.

### Required deliverable

Produce one concise source-feasibility matrix with a row per required field family and these separate columns:

- venue/product and native field/units;
- evidence source/path and immutable version/hash where available;
- provider-documented coverage;
- locally available metadata/manifest coverage;
- receiver-clock evidence;
- rights/terms status;
- missingness/completeness limitations;
- status and the smallest next evidence needed.

Use only these terminal labels:

- `FEASIBLE_FOR_AUTHORIZED_SOURCE_QA`: metadata supports proceeding to a separately authorized payload/clock QA; **not** source admission or PIT acceptance.
- `SOURCE_BLOCKED`: at least one indispensable source family, lawful route or timing requirement is unavailable.
- `INCONCLUSIVE_METADATA_ONLY`: current metadata cannot decide feasibility without a separately authorized next step.

Include an explicit statement of zero outcome reads and zero new return calculations, list what was not checked, and give one Controller decision. Do not produce a generic market-data survey.

## 3. Conditional next gate — outcome-blind registration

**Not dispatched.** Only if the metadata gate returns `FEASIBLE_FOR_AUTHORIZED_SOURCE_QA` may Controller consider a bounded registration task. Before any outcome access, the registration must freeze:

- one forced-flow burst rule and one flow-cessation window;
- the definition of contract-count OI destruction;
- independent spot anchor and required still-present perp/spot displacement;
- event/cutoff/decision/entry clock, receiver-time requirements and entry latency;
- a single four-hour hold, overlap and no-action policy;
- paired spot-led/no-OI-destruction control;
- fee, spread, depth, slippage, fill/no-fill and funding assumptions;
- missingness denominator, source exclusions, inference/uncertainty method;
- one primary comparison, acceptance criteria, strongest falsifier and terminal STOP rule.

No threshold grid, exit sweep, exposed-regime filter, or performance-guided revision. A registration is not permission to run it.

## 4. Conditional source/clock QA and outcome authorization

Metadata feasibility does not authorize payload access. Any subsequent payload-level source/clock QA needs its own explicit scope, legal/source check, bounded date range and read allowlist. It must first establish native bytes, field completeness, time alignment and actual receiver-first-known evidence without using outcome labels.

Any historical return evaluation additionally requires a frozen registration and explicit Owner authorization for the exact source, sample dates and outcome scope. The existing protected-sample, P3, Alpha, TESTNET/LIVE and funds boundaries remain unchanged.

## 5. Integration decision

Do not integrate R8-A/B/C/D yet. The immediate source-feasibility result should determine whether integration is worth the cost.

Before any later shared real-data trial, resolve at least:
- R8-A SMA-seeded EMA/MACD versus R8-C existing production EMA/ATR seed semantics;
- common cutoff, decision, entry and delayed-execution clocks;
- field readiness/missingness and the exact source contract for every indicator/exit input.

R8-B E0's hard ATR stop is a new control arm, not R8-7's original no-stop 8-hour reference. R8-C's 60 declared cells require multiplicity control for any family-wide inference. R8-D's joint historical source coverage is unknown; the old funding-z count is not evidence of joint coverage.

## 6. Decision tree

1. **Metadata gate is feasible:** Controller may dispatch a separately scoped source/receiver-clock QA; only after that passes may an outcome-blind registration be frozen for Owner review.
2. **Metadata gate is blocked:** close the mechanism as `SOURCE_BLOCKED`; do not pivot automatically to R8-C/R8-D or use proxies. Controller makes one explicit stop/replan decision.
3. **Metadata is insufficient:** identify the single missing authority or evidence item; do not repeat the same scan or launch broad collection.
4. **Any gate fails:** retain `NO_ALPHA_ESTABLISHED`, `P3_ACCESS_SCOPE_HOLD`, `SOURCE_NOT_ADMITTED`, `PIT_UNKNOWN`, `COST_INCOMPLETE`, `G2_ALPHA_NO_GO`, `G4_TESTNET_NO_GO`, `LIVE_NO_GO`, and `REAL_FUNDS_WRITE_NONE` as applicable.

## 7. Reporting and task-card rule

Owner-facing summaries are in Chinese by default; repository documentation and runnable prompts are in English by default. Every role and executor follows [V06 ChatGPT Output UI and Task Card Standard R1](V06_CHATGPT_OUTPUT_UI_AND_TASK_CARD_STANDARD_R1.md): at most two compact task cards per response, exactly one functional Copy prompt button per card, full prompt body only in the copy payload. If a working copy action is unavailable, state the limitation and ask before displaying the prompt body. Status labels must distinguish prepared/not dispatched, running, delivered, reviewed and blocked.

[Related evidence: R8-8 and Argon Research Results](V065_R8_ARGON_RESEARCH_RESULTS_20261022.md) · [R8-8 dispatch and completion receipts](V065_R8_8_ARGON_FIVE_TASK_DISPATCH_20261022.md) · [Controller B R5 policy](V065_EXECUTION_FIRST_CONTROLLER_POLICY_R5.md).
