# Research Registry Policy (v0.3.11)

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

Registry schema is `1.0.0`, registry version is `v0.3.11`, qualified Direction count is `0`, maximum Runtime stage is `OPPORTUNITY_ONLY`, and Final Holdout is `SEALED`.

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

