# V065-R8-NEXT-SOURCE-FEASIBILITY-01 — Metadata-Only Task Prompt

**State:** PREPARED_NOT_DISPATCHED
**Executor:** Codex or Antigravity, only after an explicit Controller B dispatch
**Priority:** P0 research gate
**Mode:** read-only source feasibility; no market payload, no outcomes, no code integration

## Objective

Determine whether a lawful, historically plausible, timestamp-compatible source intersection exists for the single R8-8 hypothesis: directly observed side-specific forced-liquidation flow exhaustion, contract-count open-interest destruction, and a still-displaced perpetual/spot anchor. This task only decides whether a separately authorized source/clock QA is worth running. It does not establish source admission, receiver-first-known PIT, economic utility, Alpha, or permission to evaluate returns.

## Read first

- `docs/project/V065_R8_ARGON_RESEARCH_RESULTS_20261022.md`
- `docs/project/V065_R8_8_ARGON_FIVE_TASK_DISPATCH_20261022.md`
- `docs/project/V065_NEXT_GATE_LIQUIDATION_FLOW_SOURCE_FEASIBILITY_PLAN_20261022.md`
- `docs/project/V065_EXECUTION_FIRST_CONTROLLER_POLICY_R5.md`

The five R8 worktrees are complete, isolated and unmerged. Do not relaunch or merge them. The recorded R8 execution baseline was `40c70c740f352d1b444decb75276196d17a72dd2`; refresh the moving remote `v0.6.5` ref only if you need to state its current value. Do not treat that historical task baseline as a fresh remote-main check.

## Scope

Inspect only:
- official static exchange/API documentation and source terms;
- existing repository schemas, catalogs, data manifests, coverage matrices, receipts and metadata-only reports;
- already-existing file/path/hash metadata and explicitly documented timestamp semantics.

Do not read market-value rows or raw price/liquidation/OI payloads. Do not download market data, call live market endpoints, start a collector, access private accounts, read outcome labels, calculate PnL, run a backtest, tune parameters, or access protected 2024–2026/Forward/Final/OOS outcomes. Do not change code, merge worktrees, commit or push. Do not infer a receiver clock from exchange event time, an archive timestamp, a schema or a checksum alone.

## Required source matrix

Report each source family independently:

1. Side-specific forced-liquidation reports: native event semantics, side/quantity units, event time, historical retention, documented completeness and lawful availability.
2. Native contract-count OI: units, contract multiplier, cadence, timestamp semantics, historical coverage and whether it is distinct from USD-notional OI.
3. Independent spot anchor: venue/product, history, timestamps and ability to distinguish spot-led repricing from perp-only convergence.
4. Executable perpetual evidence: quote/depth or trade evidence availability, timing/latency semantics and coverage metadata.
5. Receiver-time provenance: event/publish/receiver/ingestion time fields, source of each clock and whether immutable receiver-first-known evidence already exists.
6. Costs/funding: fee, spread/depth, slippage, fill/no-fill and funding settlement inputs; distinguish observed evidence from assumptions.
7. Rights/coverage: source terms, product identity, native units/timezone, schema/version, existing manifest/hash, documented period and known gaps.

For each row include evidence path/URL and immutable version/hash where available, provider-documented coverage, locally available metadata coverage, receiver-clock evidence, rights/terms status, known missingness, and the smallest next evidence required. Explicitly separate:
- provider documentation;
- local catalog/manifest metadata;
- payload-level QC (not allowed in this task);
- authenticated receiver-clock proof (not to be claimed without evidence);
- source admission/Owner authorization.

## Terminal status

Use exactly one:
- `FEASIBLE_FOR_AUTHORIZED_SOURCE_QA`: metadata justifies proposing a separate, bounded source/clock QA. This is not source admission or PIT acceptance.
- `SOURCE_BLOCKED`: an indispensable field family, lawful route or timing requirement is unavailable.
- `INCONCLUSIVE_METADATA_ONLY`: metadata is insufficient; name the one missing evidence/authority item.

Do not substitute price/volume proxies, do not automatically pivot to R8-C/R8-D, and do not claim any performance estimate. A source-blocked or inconclusive result is a valid completion.

## Deliverable and acceptance

Write one concise evidence-tagged report to `docs/project/V065_R8_NEXT_SOURCE_FEASIBILITY_REPORT_20261022.md` only when this task is explicitly dispatched. Include:
- terminal status and one Controller decision;
- the source matrix above;
- official links and local evidence paths for each claim;
- explicit `market-value payload reads = 0`, `outcome reads = 0`, `new return calculations = 0`, `market-data downloads = 0`;
- what could not be verified and the minimum next step.

No code/tests are expected for this metadata-only task. Run `git diff --check` for the report only. Leave all unrelated changes untouched. Do not commit or push unless Controller separately instructs you to publish the accepted report.

## Unchanged gates

No protected sample access, outcome evaluation, real-return labels, Alpha promotion, TESTNET/LIVE, order, account or funds operation is authorized by this prompt. A later outcome study requires a frozen registration and explicit Owner authorization for the exact source and date range.
