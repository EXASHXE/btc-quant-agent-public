# BTC Quant Agent v0.3.19 — Official Derivatives Feature Expansion & Candidate Gate Hardening

## 0. Role and objective

You are the implementation/research owner for `EXASHXE/btc-quant-agent`.

v0.3.19 is a **new-data-family qualification + candidate-gate correctness** round. It is NOT permission to keep searching the same v0.3.18 formula space until something looks profitable, and it is NOT an execution/live-trading round.

v0.3.18 successfully built the causal symbolic-alpha foundation but produced no provisional candidate. Its formal result also exposed several correctness gaps that must be fixed before any future candidate can be promoted to a real-time provisional shadow.

Primary goals:

1. Fix all candidate-evaluation / sandbox correctness gaps discovered in v0.3.18.
2. Expand the historical feature family using **fully downloaded, checksum-verified Binance official archives** that v0.3.18 audited but did not fully use in the formal search: mark price, index price, premium index and event-level spot/perpetual aggTrades.
3. Run a new bounded symbolic search in which every formal candidate MUST contain at least one genuinely new v0.3.19 feature; do not simply resample the old v0.3.18 feature space.
4. Keep Final Holdout sealed and all current Forward campaigns running unchanged.
5. If and only if a formula passes every frozen historical gate AND a complete event-driven candidate replay gate, freeze it and start a **future-only PROVISIONAL_CANDIDATE_FORWARD_SHADOW**. No paper/testnet/live trading.
6. Optionally benchmark a tiny local AlphaGPT-style Transformer proposal engine only after P0 correctness and official-data expansion are complete. It may not bypass the same search-budget and validation rules.

---

## 1. Repository / lineage

Repository:

```text
EXASHXE/btc-quant-agent
```

Formal/published v0.3.18 result SHA:

```text
b58908a0330f58eb675c4949dec9168a03773012
```

v0.3.18 preregistration SHA:

```text
9df1ce0e1db3684c9c9ec65efa82a21c296dc13e
```

v0.3.18 formal implementation SHA:

```text
51681874488216a25564d156e87c65c8afa04109
```

The v0.3.18 branch may contain prompt-only commits after the formal result. Always create/start v0.3.19 from the **latest remote HEAD** of:

```text
codex/v0.3.18-historical-proxy-symbolic-alpha-factory
```

Prompt-only commits after the formal result are allowed and do not change the formal v0.3.18 evidence result.

Work branch:

```text
codex/v0.3.19-official-derivatives-feature-expansion-gate-hardening
```

If that branch already exists, verify it is based on / fast-forwarded to the latest remote v0.3.18 HEAD before implementation.

Before changing code, report:

```bash
git status
git branch --show-current
git fetch --all --prune
git log -10 --oneline
git rev-parse HEAD
gh auth status
```

Do not merge to `main` automatically.

---

## 2. Frozen safety state

Must remain:

```text
strategy = EXPERIMENTAL
qualified_direction_engine = NONE
runtime_maximum = OPPORTUNITY_ONLY
execution = DISABLED
auto_execute = false
candidate_freeze = NONE unless a v0.3.19 historical candidate passes EVERY frozen gate
final_holdout = SEALED
```

Even if a provisional candidate passes, Runtime stays `OPPORTUNITY_ONLY` and execution stays `DISABLED`.

A passing historical candidate may only start:

```text
PROVISIONAL_CANDIDATE_FORWARD_SHADOW
```

with:

```text
runtime_actionable=false
execution=DISABLED
NOT_FORWARD_VALIDATED
```

No Binance order submission, no paper/testnet/live authorization, no Final Holdout access.

---

## 3. v0.3.18 accepted result — do not reinterpret

The accepted v0.3.18 result is:

```text
CONTINUE_SYMBOLIC_DISCOVERY_NO_CANDIDATE
```

Key facts:

- fixed Random Grammar Search seed `3182026`;
- 512 valid unique formulas;
- familywise adjusted discovery p-value `0.358209`;
- top Validation net 8h mean `0.00056740`, CI crossing zero, event count 383 < frozen 500;
- top frozen pseudo-forward net 8h mean `-0.00158574`, 95% CI entirely negative;
- top frozen formula LONG fraction `1.0`;
- all 5 frozen candidates failed;
- no provisional candidate and no candidate shadow started;
- Final Holdout rows loaded = 0;
- historical research wrote 0 records into Forward stores.

Do NOT enlarge the old search budget and call that a new hypothesis. v0.3.19 must earn a new search only through a **genuine data/feature-family increment**.

---

# PART A — P0 correctness hardening before any new formal search

## 4. Fix bootstrap block-unit semantics

v0.3.18 protocol froze:

```text
bootstrap_block_hours = 168
sample_step_hours = 8
```

But the generic `evaluate_formula()` default currently treats `168` as a number of sampled events, which is effectively `168 * 8h = 1344h` for the formal 8h-sampled evaluation.

Fix this generically.

Requirements:

- evaluation APIs must distinguish `block_hours` from `block_events`;
- convert hours to event units from the actual sampling interval;
- for 168h / 8h sampling, the formal block length must be 21 sampled events;
- no silent unit ambiguity;
- record both values in artifacts;
- add regression tests proving the v0.3.18 mismatch and the corrected v0.3.19 behavior.

Do NOT retroactively rewrite v0.3.18 published metrics. Preserve them as historical evidence and document the issue.

## 5. Make candidate gate implementation match the preregistered protocol completely

v0.3.18 protocol declared additional candidate constraints including:

```text
maximum_pairwise_candidate_correlation
minimum_net_profit_factor
maximum_drawdown_r
maximum_losing_streak
funding_included
candidate_must_pass_all
```

but the final `passed_all_frozen_gates` path did not enforce all of those fields.

This must be impossible in v0.3.19.

Implement one typed source of truth for candidate gates.

Requirements:

- protocol -> typed gate config -> evaluator -> machine-readable per-gate result;
- every frozen gate key must be consumed exactly once or explicitly marked `NOT_APPLICABLE` with a preregistered reason;
- unknown/unused gate keys => formal run failure;
- `candidate_must_pass_all=true` means every applicable gate must pass;
- include at minimum:
  - discovery/validation/pseudo-forward event counts;
  - LONG/SHORT balance;
  - net-return thresholds;
  - bootstrap CIs;
  - chronological folds;
  - multiple-testing adjustment;
  - pairwise candidate correlation / redundancy;
  - event-driven sandbox PF;
  - event-driven sandbox MDD in R;
  - maximum losing streak;
  - fee/slippage/funding cost treatment;
  - minimum trade count for sandbox metrics.

Add a test that injects a new unknown protocol gate and proves the formal run fails closed.

## 6. Fix research-only sandbox cost and entry semantics

Audit `src/btc_quant_agent/symbolic_alpha/sandbox.py`.

At minimum fix these issues:

### 6.1 Slippage must reduce net R

Current code computes `slippage_r` but does not subtract it in `net_r`.

Correct relation must be explicit and tested:

```text
net_r = gross_r - fees_r - slippage_r - funding_r
```

unless the protocol defines signed funding semantics differently; if so, document the exact sign convention and test LONG/SHORT separately.

### 6.2 Actual execution entry vs planned entry reference

The replay enters at the first eligible 1m open strictly after decision time. Therefore distinguish:

```text
planned_entry_reference
executed_entry_price
```

Do not embed a future next-bar open into a signal object at decision time.

Risk/R denominator must be based on a causally valid rule and consistent with the actual executed entry. If stop is defined from decision-time structure/ATR, compute actual realized risk from executed entry to that frozen stop after the next bar becomes available to the simulator.

Requirements:

- no future price in the decision object;
- first execution event strictly after decision timestamp;
- gap-through-stop handling explicit;
- LONG/SHORT symmetry tests;
- same-bar stop+target remains conservative unless preregistered otherwise;
- fee and slippage charged on actual executed prices;
- funding event application uses settled/as-of semantics and direction-correct cashflow;
- size is recorded and position/account-level PnL can be reconciled, even if candidate gates remain R-based.

## 7. Direct test coverage for symbolic research-critical code

v0.3.18 CI passed 410 tests, but coverage showed major direct gaps in the new symbolic modules, including approximately:

```text
symbolic_alpha/evaluate.py   44%
symbolic_alpha/search.py      0%
symbolic_alpha/registry.py    0%
symbolic_alpha/vm.py         67%
```

v0.3.19 must add direct unit/integration coverage.

Target direct coverage:

```text
symbolic_alpha/search.py      >= 85%
symbolic_alpha/registry.py    >= 85%
symbolic_alpha/evaluate.py    >= 85%
symbolic_alpha/vm.py          >= 85%
symbolic_alpha/sandbox.py     >= 90%
```

If a line is intentionally unreachable/defensive, justify any exclusion; do not game coverage with broad pragmas.

---

# PART B — new official historical data family

## 8. Fully materialize official Binance archives used by the new formal run

v0.3.18 proved the official archive paths/checksums exist for sampled months, but the formal feature set still relied primarily on canonical 1m kline aggregates.

v0.3.19 must build a new feature family from official historical archives over the full formal Development windows needed for the run.

Priority official sources:

```text
USD-M BTCUSDT markPriceKlines 1m
USD-M BTCUSDT indexPriceKlines 1m
USD-M BTCUSDT premiumIndexKlines 1m
USD-M BTCUSDT aggTrades
Spot BTCUSDT aggTrades
settled funding history
```

For every raw file actually used:

- download official `.CHECKSUM`;
- verify local SHA-256;
- preserve raw file immutable outside Git if large;
- create a manifest with month/day, expected checksum, local checksum, row count, timestamp unit, first/last source timestamp, gaps/duplicates/order errors;
- no interpolation/gap fill/synthetic events;
- normalize 2025+ spot microsecond timestamps to derived milliseconds while preserving raw timestamp and unit metadata;
- Final Holdout files/rows must not be loaded by the formal research run.

If a monthly archive is unavailable, record the missing interval and propagate feature unavailability.

## 9. Freeze a limited v0.3.19 official-derivatives feature family BEFORE outcome inspection

Create and preregister a compact new family. Do not create dozens of variants.

Recommended exact family (adjust only for schema impossibility, and freeze final definitions before outcome research):

```text
PREMIUM_INDEX_LEVEL_1H
PREMIUM_INDEX_Z_24H
MARK_INDEX_BASIS_1H
MARK_INDEX_BASIS_CHANGE_4H
PERP_AGG_BUY_IMBALANCE_1H
SPOT_AGG_BUY_IMBALANCE_1H
SPOT_PERP_AGG_FLOW_SPREAD_1H
PERP_AGG_SIGNED_NOTIONAL_Z_24H
```

Definitions must be causal and explicit.

AggTrade aggressor semantics must be derived from the official maker flag correctly. State exactly whether buyer-is-maker means seller aggression and how base/quote notional is signed.

For event-level features:

- aggregate only events whose exchange/source timestamps belong to fully closed source intervals;
- decision at hour T may use only events available through the close of that hour;
- no receive-time fiction for official archive data; formal role is `OFFICIAL_HISTORICAL_TIMESTAMPED`, not true local PIT;
- missing event intervals => unavailable feature, not zero.

For mark/index/premium:

- use closed 1m values only;
- define whether 1h value is close, mean, sum, or other fixed aggregation;
- denominator safety for basis calculations;
- rolling z uses only trailing closed history.

Do not use historical L2/OFI unless a genuine vendor dataset with audited event and receive timestamps is supplied.

---

## 10. Optional vendor pilot — do not block the round

A paid vendor is NOT required to complete v0.3.19 and no purchase is authorized by this prompt.

However, keep the v0.3.18 vendor contract and improve it so a future sample from Tardis.dev / Amberdata / Kaiko can be imported safely.

If a free/sample dataset is already available without purchase, you MAY audit it, but it must remain:

```text
VENDOR_RECORDED_HISTORICAL_PIT_PROXY
```

and must not enter the formal v0.3.19 search unless its inclusion was preregistered before outcome inspection.

No vendor data may backfill true Forward stores.

---

# PART C — independent symbolic research using the new family

## 11. Preregister v0.3.19 before formal implementation/results

Create a protocol, e.g.:

```text
configs/research/v0.3.19_official_derivatives_symbolic_protocol.json
```

Commit it BEFORE formal implementation/result generation and report the preregistration SHA.

The protocol must freeze:

- exact historical source manifests / roles;
- exact new feature definitions;
- Discovery / purge / Validation / embargo / internal pseudo-forward windows;
- label horizons;
- sampling interval;
- formula grammar;
- search engine(s);
- all reward-evaluation budgets;
- random seeds;
- formula complexity / max lookback;
- top-K selection/freeze rules;
- multiple-testing procedure and budget;
- candidate gate, including complete event-driven replay gates;
- stop rules.

Final Holdout remains:

```text
[2026-02-01, 2026-08-01)
SEALED
```

## 12. Formal Random Grammar Search: NEW-FEATURE-CONSTRAINED

Random Grammar Search remains the formal baseline.

The new formal candidate space must obey:

```text
EVERY formula contains >=1 v0.3.19 new official-derivatives feature
```

Old-only formulas are not eligible and do not create a new hypothesis.

Freeze a bounded search budget before results. A budget comparable to v0.3.18 is preferred; if increased, justify computationally and count every evaluated formula in multiple-testing control.

Do not search until profitable.

Record:

```text
attempts
valid_unique_formulas
reward_evaluations
duplicates
invalids
new_feature_usage_distribution
old_only_rejections
search_seed
search_budget
```

## 13. Multiple-testing control applies to the whole new formal search family

Do not report nominal formula p-values as Alpha evidence after automated search.

Use a preregistered familywise procedure. Correct the block-unit bug from Part A.

If multiple proposal engines contribute formulas to formal candidate selection, the multiple-testing universe must include ALL reward-evaluated formulas from ALL engines, not only final top-K.

---

# PART D — AlphaGPT-style tiny Transformer benchmark (P1 / optional formal arm)

## 14. Tiny local Transformer is a proposal engine, not a trading model

Only implement this after Parts A-C are complete and tested.

It must be local PyTorch, small and domain-specific. No OpenAI/Gemini/Claude API calls.

Suggested bounded architecture:

```text
vocab = typed Formula DSL tokens
embedding dimension <= 64
layers <= 2
heads <= 4
max formula length = same formal DSL constraint
```

Role:

```text
Formula tokens -> local Transformer proposal distribution -> formula -> deterministic VM -> Discovery-only reward
```

Rules:

- Validation and pseudo-forward outcomes NEVER enter training reward or model selection;
- exact training/reward-evaluation budget frozen before run;
- all formula reward evaluations count toward the search/multiple-testing budget;
- compare proposal efficiency against Random Grammar Search under a clearly stated equal-budget or otherwise fair protocol;
- no Transformer output can bypass VM, Formula Registry, candidate gates or execution guards;
- Runtime does not need the Transformer after a formula is frozen.

If there is not enough time to implement it correctly, deliver the interface/tests and defer training. Do not ship a weak Transformer merely to claim AI usage.

Recommended comparison metrics:

```text
valid_formula_rate
unique_formula_rate
best Discovery score vs evaluations
median top-K Discovery score
feature/operator diversity
Validation survival rate
wall-clock per reward evaluation
```

A Transformer that does not beat Random Search in discovery efficiency should not be promoted merely because it is a neural model.

---

# PART E — complete candidate-ready replay and immediate future shadow if earned

## 15. Historical candidate promotion requires BOTH formula gates and event-driven trading gates

A formula cannot become `PROVISIONAL_SANDBOX_CANDIDATE` merely because signed 8h returns look positive.

For each frozen top candidate that survives formula-level gates, create a causal research-only strategy using:

```text
Direction formula
+
frozen TP/BR Opportunity layer
+
WAIT state
+
frozen Entry/Stop/Target/Sizing rules
```

Use canonical 1m event replay.

Preregister the exact strategy mapping before pseudo-forward trade results are viewed.

At minimum report:

```text
trades
LONG trades
SHORT trades
win rate
avg win R
avg loss R
expectancy R
profit factor
max drawdown R
max losing streak
holding time
fees R
slippage R
funding R
net R
2x cost stress
chronological folds
```

A candidate must pass all frozen formula + trade gates.

## 16. Immediate PROVISIONAL_CANDIDATE_FORWARD_SHADOW only if all gates pass

If a candidate passes:

1. write a candidate freeze artifact with exact formula hash, feature manifests, strategy/config/version hashes and all historical gate results;
2. commit that freeze artifact to Git BEFORE its real-time shadow starts;
3. start time must be strictly in the future after freeze commit time;
4. use normal real-time data paths only;
5. record LONG/SHORT/WAIT, Entry/SL/TP/sizing hypothetically for shadow evaluation;
6. execution remains disabled and runtime-actionable=false;
7. do not use any future data from before the fixed shadow start;
8. define a frozen shadow data-quality gate and outcome-resolution logic.

If no candidate passes, do NOT start a shadow and do NOT weaken gates.

---

# PART F — existing Forward campaigns remain immutable

## 17. Continue existing campaigns unchanged

Do not reset/restart/move the start of:

```text
OPPORTUNITY_FORWARD_V0317_20260901T160000Z
DERIVATIVES_PIT_EPOCH_V0316_002
MICROSTRUCTURE_FORWARD_V0315_20260831T190000Z
```

Take start/end snapshots during v0.3.19 and report:

- Derivatives expected/full/partial/failed/missing, coverage and max gap;
- H36 expected/success/misses/opportunities/resolved counts;
- Microstructure age, trade/depth/sequence-valid coverage, gaps, heartbeat, partition integrity;
- health timer state.

Historical data processing must write 0 rows to Forward stores.

If a campaign terminally fails under its frozen gate, report it honestly; do not move the start.

---

## 18. Required tests

At minimum add tests for:

1. 168h bootstrap block converts correctly to 21 events under 8h sampling;
2. unknown/unused candidate gate key fails closed;
3. every declared candidate gate is enforced or preregistered N/A;
4. slippage is subtracted from net R;
5. LONG/SHORT fee/slippage/funding symmetry;
6. next-bar execution uses first event strictly after decision;
7. no future next-open stored in decision object;
8. risk denominator uses actual executed entry consistently;
9. gap-through-stop behavior;
10. mark/index/premium archive checksum and timestamp parsing;
11. aggTrade maker/aggressor sign semantics;
12. spot/perp timestamp-unit normalization;
13. missing source interval -> unavailable feature;
14. future-row mutation cannot change earlier feature/formula output;
15. every formal formula includes at least one new v0.3.19 feature;
16. search budget counts every reward evaluation;
17. combined multiple-testing universe if >1 proposal engine;
18. pseudo-forward firewall and top-K freeze;
19. Final Holdout access blocked;
20. provisional candidate remains Runtime-blocked;
21. execution rejects provisional signal;
22. historical run writes 0 rows to Forward stores;
23. existing Forward campaign identities/start times unchanged.

Run:

```bash
ruff check .
mypy
pytest -q
pytest --cov=btc_quant_agent --cov-report=term-missing
python -m compileall -q src skill-template/scripts
```

Include direct symbolic-module coverage table in the final report.

---

## 19. Mandatory formal artifacts

Local large/raw research artifacts may stay outside Git under a run directory such as:

```text
artifacts/research/v0.3.19_official_derivatives_symbolic_<run>
```

Include at least:

```text
protocol.json
raw_data_manifests/
feature_manifest.json
feature_availability_audit.json
symbolic_search_audit.json
multiple_testing.json
validation_results.json
pseudo_forward_top_k_freeze.json
pseudo_forward_results.json
candidate_gate_audit.json
sandbox_trade_results.json (if any survive)
transformer_benchmark.json (if implemented)
forward_status_start.json
forward_status_end.json
artifact_manifest.json
```

Do not commit large raw ZIP/Parquet/SQLite/event files to Git.

---

## 20. GitHub delivery bundle — mandatory

You MUST commit and push a concise delivery bundle to:

```text
deliverables/v0.3.19/
```

Required files:

```text
deliverables/v0.3.19/README.md
deliverables/v0.3.19/V0.3.19_OFFICIAL_DERIVATIVES_SYMBOLIC_REPORT.md
deliverables/v0.3.19/V0.3.19_NUMERIC_ANSWERS.json
deliverables/v0.3.19/V0.3.19_RECOMMENDATION.md
deliverables/v0.3.19/CANDIDATE_GATE_CORRECTNESS_AUDIT.md
deliverables/v0.3.19/OFFICIAL_DERIVATIVES_DATA_AUDIT.json
deliverables/v0.3.19/NEW_FEATURE_FAMILY_AUDIT.json
deliverables/v0.3.19/SYMBOLIC_SEARCH_AUDIT.json
deliverables/v0.3.19/FORMULA_REGISTRY_UPDATE.json
deliverables/v0.3.19/FORWARD_CAMPAIGNS_STATUS.json
```

If Tiny Transformer is implemented, also include:

```text
deliverables/v0.3.19/TRANSFORMER_PROPOSAL_BENCHMARK.md
```

If a provisional candidate passes, also include:

```text
deliverables/v0.3.19/PROVISIONAL_CANDIDATE_FREEZE.json
deliverables/v0.3.19/PROVISIONAL_SHADOW_STATUS.json
```

After finishing:

```bash
git status
git add ...
git commit -m "research: deliver v0.3.19 official derivatives symbolic qualification"
git push -u origin codex/v0.3.19-official-derivatives-feature-expansion-gate-hardening
```

Then verify the files exist on the remote branch, not only locally:

```bash
git fetch origin
git ls-tree -r origin/codex/v0.3.19-official-derivatives-feature-expansion-gate-hardening -- deliverables/v0.3.19 prompts/v0.3.19 configs/research
```

Create/open the latest research PR, but DO NOT merge it.

The task is NOT complete until the formal delivery bundle is pushed and remote existence is verified.

---

## 21. Allowed final recommendations

Use only a result-consistent recommendation from this set:

```text
START_PROVISIONAL_CANDIDATE_FORWARD_SHADOW
CONTINUE_OFFICIAL_DERIVATIVES_SYMBOLIC_NO_CANDIDATE
STOP_OFFICIAL_DERIVATIVES_SYMBOLIC_FAMILY
RECOMMEND_VENDOR_OI_L2_DATA_PILOT
RECOMMEND_TRANSFORMER_PROPOSAL_FOLLOWUP
```

Multiple recommendations may be reported as primary/secondary if they are logically compatible, but only `START_PROVISIONAL_CANDIDATE_FORWARD_SHADOW` permits starting a candidate shadow, and even then:

```text
Runtime maximum = OPPORTUNITY_ONLY
Execution = DISABLED
Final Holdout = SEALED
Live trading = NOT AUTHORIZED
```

---

## 22. Anti-mining stop rules

- If the new official feature family fails familywise/multiple-testing and Validation stability: do not increase the search budget in-place; stop this family or move to genuinely new vendor OI/L2/liquidation data.
- If Discovery passes but Validation fails: no pseudo-forward rescue search.
- If Validation passes but pseudo-forward fails: reject the candidate; do not invert its sign post hoc.
- If a Tiny Transformer does not improve proposal efficiency over Random Search under the frozen comparison, do not promote it merely because it is neural.
- If all historical gates pass but event-driven trade gates fail: no candidate shadow.
- Never use Final Holdout to rescue a Development failure.

The goal is to accelerate discovery while preserving the project's strongest property: the ability to distinguish a real edge from a mined historical coincidence.
