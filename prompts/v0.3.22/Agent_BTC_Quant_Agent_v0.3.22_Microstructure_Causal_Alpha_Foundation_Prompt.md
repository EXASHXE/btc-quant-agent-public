# BTC Quant Agent v0.3.22 — Microstructure Causal Alpha Foundation & H39 Falsification

Repository:

```text
EXASHXE/btc-quant-agent
```

Accepted baseline when this prompt was frozen:

```text
main
497842b07c8048fac4ed9b68827156ce6f51fee2
```

Stage branch:

```text
agent/v0.3.22-microstructure-alpha-foundation
```

Before doing anything:

```bash
git fetch --all --prune
git checkout agent/v0.3.22-microstructure-alpha-foundation
git status
git rev-parse HEAD
git log -12 --oneline
```

Read first:

```text
docs/PROJECT_CONTEXT_HANDOFF.md
docs/MULTI_MODEL_RESEARCH_GOVERNANCE.md
reviews/v0.3.21/gemini-3.8-flash/REVIEW.md
deliverables/v0.3.21/POST_START_SUCCESSOR_HEALTH.json
prompts/v0.3.15/Agent_BTC_Quant_Agent_v0.3.15_Microstructure_Forward_Data_Foundation_Prompt.md
prompts/v0.3.16/Agent_BTC_Quant_Agent_v0.3.16_Forward_Evidence_Recovery_Microstructure_Reliability_Prompt.md
src/btc_quant_agent/microstructure.py
```

This stage is the first formal research stage allowed to use the genuinely new true-Forward L2/aggTrade microstructure information family.

It is NOT permission to deploy a direction engine or execute trades.

---

## 0. Frozen project invariants

These remain unchanged:

```text
strategy = EXPERIMENTAL
qualified_direction_engine = NONE
runtime_maximum = OPPORTUNITY_ONLY
execution = DISABLED
auto_execute = false
live trading = NOT AUTHORIZED
final_holdout = SEALED
```

Strict prohibitions:

```text
NO live/paper/testnet execution
NO Final Holdout access
NO runtime LONG/SHORT integration
NO reopening stopped official-derivatives symbolic family
NO neural proposal engine
NO symbolic-expression factory
NO post-hoc sign inversion
NO threshold search after validation results are visible
NO reconstruction of historical L2/OFI from candles
NO use of missing Forward intervals as if observed
NO using receive_time from one host as if it came from another host
NO deleting or rewriting existing Forward evidence
```

The objective is falsification and information-value measurement, not producing a trade candidate at all costs.

---

# 1. Stage objective

Determine whether the existing true-Forward BTCUSDT microstructure capture contains reproducible, causal, incremental signed information about subsequent BTC price direction at low-frequency-relevant horizons.

The research family is:

```text
H39_MICROSTRUCTURE_DIRECTIONAL_INFORMATION
```

Primary question:

> Do mechanically defined order-flow / order-book pressure variables observed strictly before a closed 15m decision boundary predict the sign and magnitude of subsequent BTC movement better than chance and beyond the existing price/context baseline?

This is a new information family because it uses actual observed diff-depth/order-book state plus aggTrade aggressor flow. It must not be treated as equivalent to prior candle-only or historical aggTrade-only work.

---

# 2. Protect the existing background collectors

Do not interrupt or reset:

```text
DERIVATIVES_PIT_EPOCH_V0321_001
OPPORTUNITY_FORWARD_V0321_20260903T180000Z / H38
MICROSTRUCTURE_FORWARD_V0315_20260831T190000Z
```

Before research work begins, record current health using:

```bash
quantctl forward-evidence doctor
quantctl forward-evidence health
```

If any active Forward campaign has naturally breached a frozen terminal gap gate since v0.3.21, record that honestly and do not repair/backfill the historical gap.

The v0.3.22 research workflow must be read-only against existing finalized Forward partitions.

---

# 3. Mandatory protocol-freeze ordering

Before running any outcome/label correlation, candidate ranking, regression, classification, significance test or threshold analysis, create and commit:

```text
configs/research/v0.3.22_microstructure_h39_protocol.json
```

This freeze commit must contain all items in Sections 4-11 below.

Record its SHA as:

```text
H39_PROTOCOL_FREEZE_SHA
```

No labeled result may be inspected before this commit exists.

After the protocol-freeze commit, changes to feature definitions, feature signs, horizons, gates, sample split, hypothesis universe or statistical correction require a new research family/version. Do not alter H39 because results are weak.

---

# 4. Causal data partitioning

The currently captured true-Forward microstructure data may be used, but it must be split by Git/protocol time so that discovery and subsequent validation are not mixed.

## 4.1 Development microstructure archive

Define:

```text
DEVELOPMENT_MICROSTRUCTURE_CUTOFF
```

as the end timestamp of the latest fully finalized immutable microstructure partition whose finalization occurred before `H39_PROTOCOL_FREEZE_SHA`.

All data at or before this cutoff may be used for development diagnostics after protocol freeze.

It is no longer virgin validation data once used in this stage.

## 4.2 Exclusion buffer

Exclude all observations between:

```text
DEVELOPMENT_MICROSTRUCTURE_CUTOFF
and
H39_VALIDATION_START
```

from formal validation.

## 4.3 Fresh H39 validation start

After the protocol freeze commit, choose:

```text
H39_VALIDATION_START = first fully closed UTC 15m boundary
                       at least 30 minutes after H39_PROTOCOL_FREEZE_SHA
```

Commit this exact boundary before it occurs.

All formal H39 validation data must be naturally observed after this boundary.

No backfill or reconstruction is allowed.

---

# 5. Existing raw microstructure fields that may be used

Use only fields already captured causally from the true Forward microstructure pipeline, including where available:

```text
agg_trades:
- event_time_ms
- transaction_time_ms
- receive_time_ms
- price
- quantity
- aggressive_side
- buyer_is_maker

book_samples:
- event_time_ms
- receive_time_ms
- spread_bps
- top1_imbalance
- top5_imbalance
- top20_imbalance
- microprice
- ofi

aggregates:
- trade_count
- buy_quantity
- sell_quantity
- buy_notional
- sell_notional
- book_sample_count
- spread_bps_sum
- top1_imbalance_sum
- top5_imbalance_sum
- top20_imbalance_sum
- ofi_sum
- gap_count
```

Respect event-time vs receive-time semantics.

Do not invent depth states not present in stored evidence.

Do not synthesize microstructure for gaps.

---

# 6. Fixed H39 primitive feature universe

Keep the formal hypothesis family deliberately small.

At each fully closed UTC 15m decision boundary, compute features using only observations available no later than that boundary.

The formal primitive feature universe is exactly:

```text
M1 TRADE_NOTIONAL_IMBALANCE_5M
M2 TRADE_NOTIONAL_IMBALANCE_15M
M3 OFI_5M
M4 TOP5_DEPTH_IMBALANCE_5M
M5 TOP20_DEPTH_IMBALANCE_5M
M6 MICROPRICE_DEVIATION_1M
M7 PRESSURE_AGREEMENT_SCORE
M8 PRESSURE_DIVERGENCE_SCORE
```

Do not add more formal primitives in v0.3.22.

## M1 / M2 — aggressive trade notional imbalance

For window W:

```text
(buy_notional - sell_notional) / (buy_notional + sell_notional)
```

Return unavailable if denominator is zero or data quality for the window fails.

Mechanistic sign is frozen:

```text
positive -> bullish pressure
negative -> bearish pressure
```

## M3 — OFI 5m

Aggregate stored causal best-level OFI over the final 5 minutes before the decision boundary.

Normalize only with a deterministic scale that uses information available at or before the decision boundary.

Permitted normalization examples:
- contemporaneous absolute OFI sum + epsilon;
- trailing-only robust scale;
- trailing-only median absolute deviation.

No full-series normalization.

Freeze the chosen normalization in the protocol before label inspection.

Mechanistic sign:

```text
positive OFI -> bullish pressure
negative OFI -> bearish pressure
```

## M4 / M5 — order-book depth imbalance

Use time/sample-weighted mean imbalance over the final 5 minutes.

Mechanistic sign:

```text
positive bid-heavy imbalance -> bullish pressure
negative ask-heavy imbalance -> bearish pressure
```

## M6 — microprice deviation

Define a causal microprice-vs-mid deviation in basis points over the final 1 minute.

Use book samples only. If mid cannot be reconstructed causally from available stored values, do not silently approximate it; either derive it from an existing stored causal source or mark M6 unsupported and reduce the formal family size before protocol freeze.

No post-freeze substitution.

## M7 — pressure agreement score

A fixed equal-weight sign agreement score constructed from supported M1/M3/M4/M5/M6 components.

Example semantics:

```text
+1 = all supported components bullish
-1 = all supported components bearish
near 0 = disagreement
```

Freeze exact formula before outcomes are viewed.

Do not fit component weights.

## M8 — pressure divergence score

A fixed deterministic contrast between aggressive trade pressure and resting-book pressure.

Purpose: test whether aggressive taker flow contradicting the order book contains different subsequent information.

Freeze the exact formula and sign interpretation before outcome inspection.

Do not optimize weights or flip signs post hoc.

---

# 7. Data-quality eligibility per decision boundary

A 15m research observation is eligible only if the preceding feature window satisfies the frozen microstructure reliability requirements.

At minimum reject observations containing:

```text
known sequence gap
missing required book coverage
missing trade coverage
invalid/out-of-order causal timestamps
partition corruption
unresolved book resync interval overlapping feature window
```

Create explicit reason codes for excluded observations.

Do not impute a directional value for missing microstructure.

Report the percentage of scheduled 15m boundaries that remain eligible.

---

# 8. Fixed outcome definitions

The decision timestamp is the close of the 15m bar.

Reference entry price must be causal and unavailable at decision time:

```text
reference = OPEN of first fully available 1m bar strictly after the 15m decision close
```

Primary signed horizons:

```text
60 minutes
240 minutes
```

For each horizon compute at minimum:

```text
future_return_bps
future_direction = sign(future_return_bps)
max_up_excursion_atr
max_down_excursion_atr
max_abs_excursion_atr
```

ATR must be the frozen 15m ATR known at decision time.

Do not use any horizon outcome to define or normalize features.

Primary formal directional horizon for familywise testing:

```text
60 minutes
```

The 240m horizon is secondary/supporting only and must not rescue a failed 60m primary family.

---

# 9. Baseline and incremental-value requirement

H39 is not interesting merely because a feature correlates with raw future return.

Compare against a fixed price/context baseline available at decision time.

Use the existing deterministic context without introducing a new optimized model. At minimum control/report:

```text
1H regime
15m ATR percentile/state
recent 15m return sign/magnitude
4H macro state where available
```

The central question is incremental information:

```text
microstructure feature
vs
same price/context state without that microstructure feature
```

A valid analysis can use stratified/matched comparisons or a simple preregistered low-capacity model.

Do NOT use a neural model, tree ensemble, large hyperparameter search or AutoML in v0.3.22.

If a model is used, freeze it before outcome inspection. Preferred maximum complexity:

```text
logistic regression / linear probability model
with fixed regularization
```

---

# 10. Formal hypothesis universe and multiple-testing control

The maximum formal primitive universe is 8 features (M1-M8).

The primary test for each supported feature is:

```text
H0: feature has no positive signed association with next-60m direction/return
H1: mechanistically predefined feature sign has positive signed association
```

Use the mechanistically frozen sign only.

No two-sided result may be converted into a directional candidate by choosing the favorable sign afterward.

Correct the formal family using:

```text
Holm-Bonferroni FWER alpha = 0.05
```

or a more conservative preregistered equivalent.

Report:

```text
raw p
adjusted p
sample count
UTC-day count
effect size
confidence interval
sign consistency
```

Development diagnostics must be clearly labeled exploratory and cannot qualify a candidate.

---

# 11. Stability and minimum sample gates

## Development diagnostics

Development data may be analyzed even when small, but no formal claim is allowed unless there are at least:

```text
>= 5 distinct UTC days
>= 250 eligible 15m observations
```

If less, report `DEVELOPMENT_DATA_INSUFFICIENT` and stop labeled statistical inference.

## Fresh Forward H39 validation

Formal validation cannot qualify anything until all are true:

```text
>= 14 distinct UTC days after H39_VALIDATION_START
>= 750 eligible 15m observations
>= 90% eligible-boundary coverage
no terminal capture-quality breach
```

Preferred stronger maturity:

```text
>= 30 UTC days
>= 1500 eligible observations
```

Also report stability by:

```text
UTC day
volatility regime
1H regime
week / rolling time block
```

A single day or regime may not dominate the effect.

---

# 12. Candidate gate

This stage does NOT authorize runtime promotion.

A feature may be labeled only:

```text
PROVISIONAL_MICROSTRUCTURE_CANDIDATE
```

and only if fresh post-freeze validation satisfies all of:

```text
FWER-adjusted primary p < 0.05
predefined sign correct
non-trivial effect size
95% CI excludes zero in correct direction
>= 14 UTC days
>= 750 eligible samples
coverage >= 90%
no single-day dependence
no obvious regime inversion
incremental value remains after price/context baseline
```

Even then:

```text
qualified_direction_engine = NONE
runtime_maximum = OPPORTUNITY_ONLY
execution = DISABLED
```

A provisional candidate requires a separate future stage before any runtime direction qualification.

If no feature passes, the valid conclusion is:

```text
RESEARCH_FAMILY_STOP
```

or

```text
FORWARD_DATA_INSUFFICIENT
```

Do not increase the feature universe or search budget to rescue the family.

---

# 13. No contamination of H38

H38 Opportunity Forward continues independently.

Do not use H38 outcomes to tune H39.

Do not change TP/BR Opportunity definitions in v0.3.22.

You may report future overlap between H38 opportunities and H39 microstructure states descriptively, but do not make it a formal candidate-selection rule in this version.

---

# 14. Required engineering implementation

Build a deterministic research pipeline, preferably under clearly named modules/tools, that can:

```text
read finalized microstructure partitions read-only
validate partition/provenance integrity
construct causal 15m decision-boundary features
construct future labels separately
apply eligibility masks
emit a row-level research dataset with provenance
run frozen development diagnostics
run fresh-validation analysis only for post-start rows
apply FWER correction
emit deterministic reports
```

The row-level dataset must contain at minimum:

```text
decision_timestamp_ms
source_partition(s)
feature_window_start/end
feature values
eligibility flag
exclusion reason
reference timestamp/price
outcome horizon timestamps
labels
protocol hash
feature version
```

Do not write research rows into the raw Forward capture databases.

---

# 15. Determinism and causality tests

Add direct tests proving at minimum:

```text
feature windows never cross decision boundary
next-1m reference occurs strictly after decision close
full-series normalization is absent
receive/event timestamps are not conflated
known microstructure gaps invalidate affected feature windows
sign convention for aggTrade BUY/SELL is correct
OFI sign convention is correct
M7/M8 formulas are fixed and deterministic
formal feature count <= 8
Holm correction covers complete formal universe
post-freeze validation rows are separated from development rows
Final Holdout is never accessed
execution remains disabled
```

Also add one deliberate leakage test that would fail if a future book/trade event enters a feature window.

---

# 16. Required deliverables

Create:

```text
deliverables/v0.3.22/README.md
deliverables/v0.3.22/MICROSTRUCTURE_DATA_PROVENANCE.json
deliverables/v0.3.22/H39_PROTOCOL_FREEZE_MANIFEST.json
deliverables/v0.3.22/H39_FEATURE_DICTIONARY.json
deliverables/v0.3.22/H39_DEVELOPMENT_DIAGNOSTICS.json
deliverables/v0.3.22/H39_VALIDATION_STATUS.json
deliverables/v0.3.22/V0.3.22_MICROSTRUCTURE_ALPHA_REPORT.md
```

If fresh validation is not mature, `H39_VALIDATION_STATUS.json` must explicitly say:

```text
FORWARD_DATA_INSUFFICIENT
```

and report current days/sample counts without fabricating a conclusion.

If development data are also insufficient, say so explicitly.

---

# 17. Preserve live Forward collection during research

Before and after heavy offline jobs, verify collectors remain healthy.

Research processing must not starve the microstructure capture service or lock active SQLite partitions for long periods.

Prefer:

```text
finalized immutable partitions
read-only SQLite connections
bounded memory
streamed/chunked processing
```

If an active partition must be inspected for status, keep queries short and non-blocking.

Do not run destructive VACUUM/rewrite operations on Forward stores.

---

# 18. Quality gates

Run at minimum:

```bash
ruff check .
mypy src
pytest
python -m compileall src tests tools
```

Run configured GitHub Actions CI across:

```text
Python 3.11
Python 3.12
Python 3.13
```

Report exact CI run IDs tied to the reviewable SHA.

---

# 19. Review workflow

After implementation reaches a reviewable exact SHA:

1. Implementation agent stops editing.
2. Gemini-3.8-Flash performs one independent post-implementation audit only.
3. Gemini writes:

```text
reviews/v0.3.22/gemini-3.8-flash/REVIEW.md
```

and optionally `REVIEW.json`.
4. ChatGPT then performs the final consolidated review and owns the next-stage prompt.
5. No second Gemini reconciliation round is required.

---

# 20. Allowed final stage verdicts

Use one of:

```text
PASS_WITH_NONBLOCKING_FOLLOWUPS
FORWARD_DATA_INSUFFICIENT
RESEARCH_FAMILY_STOP
REPAIR_REQUIRED
REJECT_CANDIDATE
```

`PASS_WITH_NONBLOCKING_FOLLOWUPS` is appropriate when the causal feature pipeline/protocol is correct and fresh H39 validation has started but is not yet mature.

Do not call H39 a qualified direction engine in v0.3.22.

---

# 21. Required implementation-agent final response

Report:

```text
1. branch
2. exact HEAD SHA
3. base SHA
4. H39_PROTOCOL_FREEZE_SHA
5. development cutoff
6. H39 validation start UTC/ms
7. feature universe actually supported
8. excluded/unsupported feature(s), if any, with reason
9. development distinct days / eligible sample count
10. validation distinct days / eligible sample count
11. coverage ratios
12. formal tests and full FWER universe
13. development results (explicitly exploratory)
14. fresh-validation status/results if mature
15. any provisional candidate and exact gate evidence
16. derivatives/H38/microstructure background health
17. ruff/mypy/pytest/compileall
18. CI run IDs/status
19. Final Holdout access count
20. execution safety state
21. final verdict
```

End explicitly with:

```text
qualified_direction_engine = NONE
runtime_maximum = OPPORTUNITY_ONLY
execution = DISABLED
auto_execute = false
final_holdout = SEALED
```
