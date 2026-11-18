# Research Registry Policy (v0.3.12)

`configs/research_registry.json` is the sole machine-readable source of research qualification for normal Runtime. Missing files, parse failures, unknown components, invalid schema, or missing evidence fail closed.

## Current state

| Component | Role | Research status | Runtime eligibility | Reuse |
|---|---|---|---|---|
| `legacy_price_direction_v022` | DIRECTION | REJECTED | BLOCKED | stopped |
| `trend_pullback_opportunity` | OPPORTUNITY | SUPPORTED_MOVEMENT | ANALYSIS_ONLY | movement research only |
| `breakout_retest_opportunity` | OPPORTUNITY | SUPPORTED_MOVEMENT | ANALYSIS_ONLY | movement research only |
| `funding_crowding_direction` | DIRECTION | INCONCLUSIVE | BLOCKED | stopped |
| `xab4h_direction` | DIRECTION | REJECTED | BLOCKED | stopped |
| `range_boll20_2z_mean_reversion` | DIAGNOSTIC | INCONCLUSIVE | ANALYSIS_ONLY | NOT_CANDIDATE |
| `active_direction_engine` | DIRECTION | REJECTED / NONE | BLOCKED | no qualified engine |

Registry schema is `1.0.0`, registry version is `v0.3.12`, qualified Direction count is `0`, maximum Runtime stage is `OPPORTUNITY_ONLY`, and Final Holdout is `SEALED`. The v0.3.12 Spot–Perpetual taker-flow component is `INCONCLUSIVE/BLOCKED`; H33 and H34 were falsified.

## Validation and use

```bash
quantctl research-registry validate
quantctl research-registry status
quantctl research-registry show trend_pullback_opportunity
```

The validator enforces unique IDs, exact fields, enum values, existing evidence, a sealed holdout, non-actionability of rejected components, separation of movement and Direction claims, and `VALIDATED_FORWARD` for `LIVE_ELIGIBLE`.

Normal `QuantService` uses `RUNTIME_GATED`. A deterministic TP/BR detection is looked up before the rejected multifactor Direction and risk chain. Its output is an `OpportunityEvidence`, never a `Signal`; `legacy_pattern_side` remains non-actionable metadata. Existing legacy signals are rechecked by Execution before market refresh or risk calculation and are rejected with `RESEARCH_REGISTRY_NOT_ACTIONABLE`.

Historical research may opt into `LEGACY_RESEARCH_V022` only with `configs/frozen/v0.2.2.toml`. There is no automatic fallback.

## Reopening governance

A stopped family has `eligible_for_reuse=false`. Reopening requires a new mechanism ID, a genuinely independent information source, and a written rationale. Changing thresholds, windows, baskets, or signs is not a new mechanism. `INCONCLUSIVE` never grants Runtime eligibility. Final Holdout access remains separately governed and cannot be opened by a Registry edit.

## 2026-10-22 — R8-8 loss diagnosis and Argon engineering

R8-7 is closed as a negative fixed-8h X-only modeled reference (545 events; base ex-funding -11,802.83 USDT; PF 0.719). R8-8 reconciled only the existing ledger and selected forced-liquidation flow exhaustion for future source feasibility; no new outcomes were read. R8-A/B/C/D completed synthetic engineering (48/82/76/43 tests respectively) but remain unmerged and provide no Alpha evidence. Funding-inclusive R8-7 net and R8-D real joint feature coverage remain unknown. The five worktrees are isolated at baseline `40c70c740f352d1b444decb75276196d17a72dd2`. The only prepared next task is metadata-only source feasibility, `PREPARED_NOT_DISPATCHED`, under [the source-feasibility plan](project/V065_NEXT_GATE_LIQUIDATION_FLOW_SOURCE_FEASIBILITY_PLAN_20261022.md) and [prepared task prompt](../prompts/v065/controller-dispatch/V065_R8_NEXT_SOURCE_FEASIBILITY_METADATA_ONLY_R1.md). No market-value payload reads, new outcome evaluation or protected 2024–2026 access are authorized by this status note. See [research results](project/V065_R8_ARGON_RESEARCH_RESULTS_20261022.md) and [dispatch evidence](project/V065_R8_8_ARGON_FIVE_TASK_DISPATCH_20261022.md).
