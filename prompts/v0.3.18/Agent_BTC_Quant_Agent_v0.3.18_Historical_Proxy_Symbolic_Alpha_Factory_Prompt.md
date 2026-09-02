# BTC Quant Agent v0.3.18 — Historical Data Acceleration & Causal Symbolic Alpha Factory

> Revision: 2026-09-02 — expand official Binance historical data coverage, add vendor-PIT data path, clarify AlphaGPT Transformer semantics, and allow a frozen provisional candidate to start an isolated real-time shadow before the 30-day infrastructure gates mature.

## 0. Objective

This round accelerates strategy construction **without weakening Forward Evidence truthfulness**.

Continue the existing v0.3.16/v0.3.17 Forward campaigns unchanged, but in parallel build a historical-development candidate sandbox and a causal symbolic alpha factory inspired by the useful ideas in `imbue-bit/AlphaGPT`.

The key acceleration principle is:

```text
True Forward evidence keeps accumulating in real calendar time
                +
Official / audited historical data is used now to discover and build candidates
                +
A strong historical candidate may be frozen and placed into a separate real-time shadow immediately
```

This is NOT permission to trade real money. Historical or vendor-reconstructed data does not become true local Forward PIT merely because it is high quality.

Primary goals:

1. Exhaust the free official Binance historical archives before waiting for new Forward data.
2. Build a strict historical provenance matrix that distinguishes official archives, vendor-recorded historical PIT proxies, Development proxies, and true local Forward PIT.
3. Add official Spot and USD-M Perpetual aggregate-trade history where available, plus mark/index/premium/funding history, with checksum and timestamp-unit audits.
4. Evaluate whether vendor historical data such as Tardis / Amberdata / Kaiko / CoinGlass can materially add OI, L2 diff-depth, liquidation, positioning, and receive-timestamp information; do not make a paid vendor a hard blocker.
5. Implement an AlphaGPT-inspired causal Formula DSL, deterministic VM, Formula Registry, and bounded symbolic proposal/evaluation pipeline.
6. Required search baseline is Random Grammar Search. Create a clean interface for Genetic and a **local tiny Transformer formula proposal engine**; a tiny Transformer may be implemented/trained only after the Random baseline is complete and only under an equal/frozen Discovery-only budget. Do not call an external LLM API to generate formal search formulas.
7. Build a full research-only candidate path with hypothetical LONG/SHORT/WAIT, Entry/SL/TP/sizing, fees/slippage/funding, and event-driven PnL.
8. If and only if a candidate passes the frozen historical validation + internal pseudo-forward gate, freeze it and start a separate **PROVISIONAL_CANDIDATE_FORWARD_SHADOW** from a future fixed UTC boundary. It must not authorize orders or alter normal Runtime.
9. Keep Final Holdout sealed and existing H36 / Derivatives / Microstructure campaigns unchanged.

---

## 1. Repository / lineage

Repository:

```text
EXASHXE/btc-quant-agent
```

Formal/published v0.3.17 delivery SHA:

```text
7ffadae819b03fb5d9de57a0c8b85c3ca6acb637
```

The v0.3.17 branch may contain prompt-only commits after the formal result. Always fetch first and identify the actual latest remote HEAD of:

```text
codex/v0.3.17-opportunity-successor-forward-stabilization
```

Work branch:

```text
codex/v0.3.18-historical-proxy-symbolic-alpha-factory
```

The branch may already exist. Ensure it contains the latest v0.3.17 lineage and this revised prompt before implementation. Do not merge to `main` automatically.

Before changing code, report:

```bash
git status
git branch --show-current
git fetch --all --prune
git log -10 --oneline
git rev-parse HEAD
gh auth status
```

---

## 2. Frozen safety state

Must remain:

```text
strategy = EXPERIMENTAL
qualified_direction_engine = NONE
runtime_maximum = OPPORTUNITY_ONLY
execution = DISABLED
auto_execute = false
candidate_freeze = NONE
final_holdout = SEALED
```

No Binance order submission, no paper/testnet/live authorization, and no Final Holdout access.

Historical and provisional objects must be explicitly tagged:

```text
PROVISIONAL_SANDBOX_ONLY
NOT_FORWARD_VALIDATED
NOT_RUNTIME_ACTIONABLE
```

A separate real-time provisional shadow, if started, must remain:

```text
PROVISIONAL_CANDIDATE_FORWARD_SHADOW
execution = DISABLED
runtime_actionable = false
```

---

## 3. Faster sampling does not replace calendar time

Do NOT claim that collecting every 5m or 1m makes 7 calendar days equivalent to 30 days. Higher-frequency samples are strongly autocorrelated and do not reproduce market-regime diversity.

Preserve all existing formal Forward gates unchanged.

You MAY add an isolated auxiliary high-frequency Derivatives PIT capture (recommended 5m only if endpoint limits and semantics permit), but it must be labeled:

```text
AUXILIARY_HIGH_FREQ_PIT
formal_gate_eligible = false
```

It must never count toward the existing v0.3.16 15m evidence epoch.

Record endpoint set, schedule, rate-limit budget, source timestamps, observed timestamps, gaps, duplicates, and formal-role isolation.

---

## 4. Historical data acceleration: use the richest trustworthy data now

### 4.1 Source hierarchy and formal roles

Use the following hierarchy:

```text
Tier 1 — Binance official public archive / official historical endpoint
    => CANONICAL_HISTORICAL or OFFICIAL_HISTORICAL_TIMESTAMPED

Tier 2 — reputable vendor that recorded exchange data historically
    => VENDOR_RECORDED_HISTORICAL_PIT_PROXY

Tier 3 — our own running collectors at the time of observation
    => TRUE_FORWARD_LOCAL_PIT
```

Never collapse these roles into one another.

The provenance audit must support at least:

```text
CANONICAL_HISTORICAL
OFFICIAL_HISTORICAL_TIMESTAMPED
VENDOR_RECORDED_HISTORICAL_PIT_PROXY
DEVELOPMENT_PROXY
FORWARD_PIT_ONLY
UNAVAILABLE_OR_UNTRUSTWORTHY
```

### 4.2 Binance official archive: P0, do this before paid/vendor data

Audit and, where usable, ingest the official Binance public-data / Binance Vision archives for BTCUSDT.

At minimum investigate and verify actual archive coverage/schema/checksums for:

```text
Spot BTCUSDT aggTrades
USD-M Futures BTCUSDT aggTrades
Spot BTCUSDT 1m klines
USD-M BTCUSDT 1m klines
USD-M markPriceKlines
USD-M indexPriceKlines
USD-M premiumIndexKlines / premium data
settled funding history
```

Important correction to older assumptions: current REST lookback limits do NOT imply that historical `aggTrades` are unavailable. Official Binance public archives provide downloadable daily/monthly historical files for Spot and USD-M datasets. Use archive files rather than attempting to reconstruct years of history from a current short-lookback REST endpoint.

Requirements:

- Prefer official monthly files plus official `.CHECKSUM` verification when available.
- Record exact archive path pattern actually used; do not assume a path without testing it.
- Build a manifest of requested/downloaded/missing months.
- Preserve source files or their hashes in the data manifest; large raw data remains gitignored.
- No gap filling or synthetic trades.
- Duplicate IDs/timestamps must be audited.
- Validate price/quantity/trade-id monotonic semantics where applicable.
- Normalize timestamp units explicitly and test them.

### 4.3 Timestamp semantics are a first-class requirement

For every dataset record:

```text
provider
source_name
symbol
coverage_start
coverage_end
resolution_or_event_type
exchange_event_timestamp_field
source_timestamp_unit
local_or_vendor_receive_timestamp_field (if any)
retrieval_timestamp
checksum_or_manifest
lookback_limit_if_rest
point_in_time_interpretation
known_biases
formal_role
```

Special care:

- Binance public Spot archive timestamps changed to microsecond-scale for newer data. Detect/validate unit by documented dataset semantics plus value-range sanity checks; do not silently interpret microseconds as milliseconds.
- Futures datasets may use different timestamp semantics from Spot; test each dataset independently.
- Preserve the original raw timestamp and add normalized milliseconds as a derived field.
- A normalization test must include both millisecond and microsecond examples.

### 4.4 What to derive from official aggTrades

Use `aggTrades` to construct causal historical market-flow features that are richer than candle-level taker totals, subject to verified schema semantics.

Potential registered features include:

```text
SPOT_AGG_BUY_NOTIONAL
SPOT_AGG_SELL_NOTIONAL
SPOT_AGG_NET_TAKER_FLOW
SPOT_AGG_TRADE_COUNT_IMBALANCE
SPOT_AGG_MEAN_TRADE_SIZE
SPOT_AGG_TRADE_SIZE_SKEW_PROXY
SPOT_AGG_BURSTINESS

PERP_AGG_BUY_NOTIONAL
PERP_AGG_SELL_NOTIONAL
PERP_AGG_NET_TAKER_FLOW
PERP_AGG_TRADE_COUNT_IMBALANCE
PERP_AGG_MEAN_TRADE_SIZE
PERP_AGG_TRADE_SIZE_SKEW_PROXY
PERP_AGG_BURSTINESS

SPOT_PERP_NET_FLOW_SPREAD
SPOT_PERP_FLOW_LEAD_LAG_CAUSAL
MARK_INDEX_BASIS
PREMIUM_LEVEL
FUNDING_LEVEL
```

Use the maker/buyer-maker field only after verifying its direction convention. Document how aggressor BUY/SELL is derived.

Do NOT silently create an "iceberg" or "absorption" label from aggTrades alone. Such terms require explicit operational definitions and preferably order-book context.

### 4.5 Historical OI / positioning / L2: vendor path, not fabrication

Current exchange REST retention for OI / long-short / related positioning may be limited. Do not pretend it provides 2021-2026 PIT simply because an endpoint exists today.

Audit vendor options at minimum:

```text
Tardis.dev
Amberdata
Kaiko
CoinGlass
```

Priorities:

- Tardis.dev: tick trades, incremental L2/order-book reconstruction, OI/funding/liquidations/derivative ticker where supported, exchange timestamp and vendor/local receive timestamp.
- Amberdata: institutional historical derivatives/order-book/OI/liquidation coverage where supported.
- Kaiko: institutional L1/L2 historical market data and normalized exchange feeds.
- CoinGlass: OI/funding/positioning history; treat primarily as derivatives-sentiment/positioning, not tick-L2 ground truth.

For each provider record:

```text
dataset
BTCUSDT venue/instrument exact mapping
coverage dates
frequency/event granularity
exchange timestamp available?
receive timestamp available?
L2 sequence reconstructable?
OI semantics
liquidation semantics
cost/access requirement
sample file/API availability
license/redistribution constraints
recommended_formal_role
```

Do NOT purchase anything automatically and do NOT make vendor access a blocker for v0.3.18. First complete the Tier-1 official-data path. If credentials/data are not available, implement a clean vendor import adapter/manifest contract and report what additional feature families would become available.

### 4.6 Historical L2 prohibition

Never synthesize historical L2, OFI, microprice, depth imbalance, or queue dynamics from OHLCV/candle data.

Historical L2 features are allowed only when a genuine historical incremental depth/order-book source is obtained and audited. Otherwise these remain `FORWARD_PIT_ONLY` from the existing Microstructure campaign.

---

## 5. Historical masking / pseudo-forward protocol

Historical masking accelerates development but does not restore global project innocence because earlier research already inspected parts of Development.

All such evaluation must be called:

```text
DEVELOPMENT_INTERNAL_PSEUDO_FORWARD
```

Never call it true Forward or untouched OOS.

Before any formal search result is viewed, preregister and commit a protocol JSON containing:

- exact Discovery/search window;
- validation/selection window;
- internal pseudo-forward window;
- purge interval;
- embargo interval;
- label horizons;
- maximum formula lookback;
- search seed;
- search budget;
- top-K allowed to touch pseudo-forward;
- provisional-candidate gate.

Use strictly chronological splits. Purge/embargo must be at least the maximum of label horizon and formula lookback necessary to prevent boundary leakage.

Final Holdout remains:

```text
[2026-02-01, 2026-08-01)
SEALED
```

Do not access it.

---

## 6. AlphaGPT-inspired architecture: borrow the good parts, not the leakage

Reference:

```text
https://github.com/imbue-bit/AlphaGPT
```

Prefer clean-room implementation. If direct code is copied, preserve Apache-2.0 attribution/license requirements.

### 6.1 Clarify what the AlphaGPT Transformer is

The AlphaGPT Transformer is NOT an OpenAI/Gemini/Claude API call and is NOT a general-purpose LLM.

It is a small local PyTorch Transformer policy over a tiny formula-token vocabulary:

```text
feature tokens + operator tokens -> next formula token
```

The useful architectural concept is:

```text
Proposal model proposes an interpretable formula
        ↓
Deterministic VM executes it
        ↓
External quant evaluator scores it
```

Formal v0.3.18 search must never depend on an external natural-language model API. LLMs may help humans propose research hypotheses in documentation, but their output is not a formal formula-search oracle.

### 6.2 Causal Formula DSL

Implement a deterministic formula vocabulary over registered features.

Recommended operators:

```text
ADD
SUB
MUL
DIV
NEG
ABS
SIGN
MIN
MAX
GATE
DELAY_1
DELAY_N
ROLL_SUM_N
ROLL_MEAN_N
ROLL_STD_N
ROLL_Z_N
EMA_N
DECAY_N
CLIP
```

Rules:

- every operator declares arity and causal lookback;
- no full-series normalization;
- no future-dependent mean/std/median/MAD;
- no `torch.roll` wrap-around contamination;
- startup unavailable rows stay unavailable/masked;
- divide-by-zero handling is explicit;
- NaN/Inf handling is explicit and auditable;
- formula total lookback is computable before execution;
- unavailable input => unavailable output unless zero has an explicit economic meaning frozen in protocol.

Suggested package:

```text
src/btc_quant_agent/symbolic_alpha/dsl.py
src/btc_quant_agent/symbolic_alpha/vm.py
src/btc_quant_agent/symbolic_alpha/registry.py
src/btc_quant_agent/symbolic_alpha/proposal.py
src/btc_quant_agent/symbolic_alpha/search.py
src/btc_quant_agent/symbolic_alpha/evaluate.py
```

### 6.3 Deterministic VM

Inspired by AlphaGPT StackVM, but research-grade:

- typed postfix/AST representation;
- exact serialization and canonical hash;
- deterministic execution;
- structured failure reasons, no blanket `except Exception: return None`;
- operator-level unit tests;
- formula-level causality tests;
- feature provenance and availability checks;
- reproducible output hash where practical.

Critical causality property:

> Mutating all market rows after time `t` must not change formula output at or before `t`.

### 6.4 Formula Registry

Add a machine-readable registry such as:

```text
configs/formula_registry.json
```

Record at minimum:

```text
formula_id
formula_hash
formula_tokens_or_ast
input_feature_ids
input_data_roles
operator_set
max_lookback
proposal_engine
search_run_id
search_seed
search_budget
complexity
Discovery_window
validation_window
pseudo_forward_window
metrics_by_fold
correlation_to_existing_candidates
status
research_eligibility
runtime_eligibility
```

Statuses:

```text
DISCOVERY_ONLY
FAILED_VALIDATION
REJECTED_REDUNDANT
REJECTED_UNSTABLE
PROVISIONAL_SANDBOX_CANDIDATE
PROVISIONAL_FORWARD_SHADOW
```

No v0.3.18 formula may become `VALIDATED_FORWARD`, `LIVE_ELIGIBLE`, or Runtime-authorized.

---

## 7. Proposal engines: benchmark simple search before AI

Define an interface such as:

```text
FormulaProposalEngine
    propose(n, feature_registry, operator_registry, seed, constraints)
```

### P0 — Random Grammar Search (required)

Required formal baseline.

Freeze before results:

- seed;
- valid unique formula budget;
- maximum AST/token length;
- maximum total lookback;
- complexity penalty;
- allowed features/operators;
- duplicate canonicalization rules.

Budget must be finite. Do not continue searching until a profitable formula appears.

### P1 — Genetic Search (optional)

Only after Random pipeline is complete. Freeze population, generations, mutation/crossover probabilities, and total formula-evaluation budget before results.

### P2 — Tiny local Transformer Proposal Engine (optional but architecture should be ready)

You MAY implement a small local PyTorch Transformer proposal engine inspired by AlphaGPT if P0 is complete and time/runtime permit.

It must be explicitly documented as:

```text
LOCAL_FORMULA_POLICY_MODEL
NOT_LLM
NO_EXTERNAL_API
DISCOVERY_PROPOSAL_ONLY
```

Requirements if trained:

- vocabulary contains only formula tokens, not natural language;
- small model only; no need for billion-parameter architecture;
- training reward may use Discovery data only;
- Validation and pseudo-forward outcomes must never flow into gradients, reward tuning, early stopping, or model selection;
- freeze architecture, optimizer, steps, formula-evaluation budget, reward definition, seed, and complexity penalty before training;
- reward must penalize complexity, turnover/cost fragility, and trivial/redundant formulas where appropriate;
- compare against Random Search at equal or clearly normalized formula-evaluation budget;
- generated formulas still pass through the deterministic VM and the exact same external evaluator;
- no model inference is required in production Runtime after a formula is frozen.

Do NOT copy AlphaGPT's full-series normalization, look-ahead semantics, "best in-sample backtest wins", or unused architectural complexity merely because it exists. Do not add LoRD/MTP/critic machinery unless an explicit preregistered ablation justifies it.

---

## 8. Search feature families

### Tier-1 official historical features may include after audit

```text
price / log return
ATR / realized volatility
volume / quote volume / trade count
kline taker-buy participation
funding
mark/index/premium/basis
Spot aggTrade aggressive-flow features
Perp aggTrade aggressive-flow features
Spot-vs-Perp flow spread / causal lead-lag features
```

### Vendor historical features may additionally include only if acquired/audited

```text
Open Interest
incremental L2 depth
OFI
depth imbalance
microprice displacement
book depletion/replenishment
liquidations
positioning / long-short ratios
vendor receive-latency features where economically justified
```

Keep feature availability timestamps causal. A feature computed from a bar/event is available only after all required source events are fully known under its source semantics.

Do not let Formula Search invent a feature whose historical provenance is weaker than the registry says.

---

## 9. Candidate evaluation and multiple-testing governance

Search/reward sees Discovery only.

Validation is separate from proposal/reward.

The internal pseudo-forward segment is touched only once by a frozen top-K set selected without pseudo-forward outcomes.

For each top candidate report at minimum:

- signed return at frozen horizons;
- event/trade counts;
- LONG/SHORT balance;
- Early/Late stability;
- chronological-fold stability;
- bootstrap CI;
- turnover;
- fees/slippage/funding sensitivity where applicable;
- candidate correlation/redundancy;
- complexity;
- agreement/disagreement with simple baselines.

If a frozen sandbox entry/exit rule is defined, also report:

```text
expectancy_R
profit_factor
max_drawdown_R
max_losing_streak
holding_time
fees
slippage
funding
net_R
```

Multiple-testing audit must record:

```text
unique_formulas_evaluated
invalid_formulas
validation_candidates
top_k_frozen_before_pseudo_forward
search_seed
search_budget
proposal_engine
```

Use at least one multiple-testing-aware procedure suitable to the metric, for example:

- empirical-null/permutation distribution of best search score;
- bootstrap Reality-Check-style comparison;
- Deflated Sharpe Ratio where appropriate;
- FDR control for a hypothesis set.

A nominal p-value after thousands of formulas is not sufficient.

---

## 10. Build the full provisional trading sandbox now

Do not wait 30 days to write the tradable architecture.

Research-only conceptual path:

```text
Historical Direction Formula
        +
Frozen TP/BR Opportunity
        ↓
LONG / SHORT / WAIT
        ↓
research Entry / SL / TP / sizing
        ↓
1m causal event-driven replay
        ↓
fees + slippage + funding
        ↓
PROVISIONAL_SANDBOX_CANDIDATE
```

Requirements:

- isolated from normal Runtime authorization;
- `source=HISTORICAL_PROXY` or exact audited role;
- `runtime_actionable=false`;
- execution service rejects these signals;
- reuse project risk/cost semantics where possible;
- no future bars for signal generation;
- fills simulated only from bars/events strictly after the decision timestamp;
- include WAIT/no-trade state;
- deterministic reproduction;
- do not optimize solely on terminal equity.

Preregister a provisional-candidate acceptance gate before search. Prefer reusing the project's robust historical candidate standards unless there is a documented reason to change them.

A candidate failing robustness remains rejected even if its best in-sample equity curve is attractive.

---

## 11. Acceleration step: frozen provisional real-time shadow

If and only if a historical candidate passes the frozen validation + internal pseudo-forward + robustness gate, do NOT wait for the current 30-day data gates before beginning to observe it in real time.

Instead:

1. Freeze exact formula hash, feature definitions, TP/BR combination logic, Entry/SL/TP/sizing, fee assumptions, strategy/config/registry hashes.
2. Commit that freeze before observing any real-time candidate outcomes.
3. Choose a future fixed UTC start boundary.
4. Start an independent campaign:

```text
PROVISIONAL_CANDIDATE_FORWARD_SHADOW_V0318_...
```

5. Compute real-time hypothetical LONG/SHORT/WAIT and hypothetical fills/PnL only; never submit orders.
6. Do not modify formula/parameters after shadow begins. A changed candidate requires a new campaign ID.
7. Record every expected decision slot, missing slot, data-quality state, signal/no-signal, and outcome so selection bias cannot hide failures.
8. This campaign is additional evidence only and does not alter:

```text
qualified_direction_engine = NONE
runtime_maximum = OPPORTUNITY_ONLY
execution = DISABLED
candidate_freeze = NONE
```

If no candidate passes, do not create a fake shadow campaign.

---

## 12. Existing Forward campaigns must continue unchanged

Do not move/reset/restart the formal start of:

```text
OPPORTUNITY_FORWARD_V0317_20260901T160000Z
DERIVATIVES_PIT_EPOCH_V0316_002
MICROSTRUCTURE_FORWARD_V0315_20260831T190000Z
```

Take fresh start/end snapshots during v0.3.18 and report:

- Derivatives expected/full/partial/failed/missing, per-field availability, max bad gap;
- H36 scan ratio, miss streak, opportunity count, 4h/8h resolved counts;
- Microstructure age, trade/depth/sequence-valid coverage, gaps/resyncs, partition checksum integrity;
- systemd health state.

Historical/vendor research must never write/backfill these stores.

---

## 13. Required tests

Add tests covering at least:

1. official archive checksum validation;
2. Spot/Futures historical timestamp-unit normalization including ms and µs cases;
3. aggTrade aggressor-side mapping against documented schema examples;
4. no gaps silently filled;
5. provider/formal-role provenance serialization;
6. vendor rows cannot be mislabeled as TRUE_FORWARD_LOCAL_PIT;
7. future-row mutation cannot change formula output at earlier timestamps;
8. no full-series normalization;
9. no `torch.roll` wrap-around leakage;
10. every rolling operator respects lookback;
11. formula max-lookback calculation;
12. deterministic formula serialization/hash;
13. VM structured error handling;
14. duplicate formula rejection;
15. frozen search seed/budget;
16. Random and optional Transformer evaluation-budget accounting;
17. optional Transformer receives Discovery reward only;
18. validation and pseudo-forward cannot enter proposal training/reward;
19. chronological split + purge/embargo;
20. pseudo-forward untouched during search/selection;
21. Final Holdout access blocked;
22. provisional candidate is Runtime-blocked;
23. execution rejects provisional signals;
24. provisional real-time shadow, if created, cannot place orders;
25. candidate shadow start is future-fixed and formula freeze predates outcomes;
26. existing H36/Derivatives/Microstructure stores are unchanged by historical research;
27. existing normal Runtime remains max OPPORTUNITY_ONLY.

Run:

```bash
ruff check .
mypy
pytest -q
pytest --cov=btc_quant_agent --cov-report=term-missing
python -m compileall -q src skill-template/scripts
```

---

## 14. Formal artifacts

Store formal run artifacts under a timestamped gitignored research directory, for example:

```text
artifacts/research/v0.3.18_historical_symbolic_<run_id>/
```

Include manifests, protocol, source audit, formula candidates, search audit, fold results, pseudo-forward results, sandbox trades, bootstrap/permutation outputs, and candidate-freeze artifact if applicable.

Do not commit large raw Binance/vendor data, SQLite databases, Parquet event files, or model checkpoints to Git unless they are intentionally small test fixtures.

---

## 15. Mandatory GitHub delivery bundle

Create and **commit + push** at least:

```text
deliverables/v0.3.18/README.md
deliverables/v0.3.18/V0.3.18_HISTORICAL_PROXY_SYMBOLIC_ALPHA_REPORT.md
deliverables/v0.3.18/V0.3.18_NUMERIC_ANSWERS.json
deliverables/v0.3.18/V0.3.18_RECOMMENDATION.md
deliverables/v0.3.18/HISTORICAL_DATA_PROVENANCE_AUDIT.json
deliverables/v0.3.18/BINANCE_OFFICIAL_ARCHIVE_AUDIT.json
deliverables/v0.3.18/VENDOR_HISTORICAL_DATA_OPTIONS.md
deliverables/v0.3.18/FORMULA_DSL_AND_VM_AUDIT.md
deliverables/v0.3.18/FORMULA_REGISTRY_SNAPSHOT.json
deliverables/v0.3.18/SYMBOLIC_SEARCH_AUDIT.json
deliverables/v0.3.18/ALPHAGPT_REFERENCE_ADAPTATION.md
deliverables/v0.3.18/FORWARD_CAMPAIGNS_STATUS.json
```

If a candidate exists, also include:

```text
deliverables/v0.3.18/PROVISIONAL_CANDIDATE.json
deliverables/v0.3.18/PROVISIONAL_CANDIDATE_TRADES_SUMMARY.json
```

If a provisional real-time shadow is started, also include:

```text
deliverables/v0.3.18/PROVISIONAL_CANDIDATE_SHADOW_FREEZE.json
deliverables/v0.3.18/PROVISIONAL_CANDIDATE_SHADOW_STATUS.json
```

The report must clearly separate:

```text
Historical discovery result
Historical validation result
Development-internal pseudo-forward result
Vendor-proxy result (if any)
True Forward campaign status
```

Do not blur these evidence classes.

---

## 16. Git / remote completion requirements

Commit implementation and delivery files to:

```text
codex/v0.3.18-historical-proxy-symbolic-alpha-factory
```

Push the branch to GitHub.

Verify remotely, not only locally:

```bash
git fetch origin
git status
git log -8 --oneline
git ls-tree -r origin/codex/v0.3.18-historical-proxy-symbolic-alpha-factory -- deliverables/v0.3.18 prompts/v0.3.18
git rev-parse HEAD
git rev-parse origin/codex/v0.3.18-historical-proxy-symbolic-alpha-factory
```

Create/update the research PR after delivery. Do not merge it automatically.

Final response must provide:

```text
branch
preregistration SHA
formal implementation SHA
formal delivery/report SHA
CI run/conclusion
PR number
remote deliverables verification
raw-data location/manifest hashes
Forward campaign start/end health
```

---

## 17. Allowed final recommendations

Choose exactly one primary recommendation consistent with evidence:

```text
START_PROVISIONAL_CANDIDATE_FORWARD_SHADOW
CONTINUE_SYMBOLIC_DISCOVERY_NO_CANDIDATE
RECOMMEND_VENDOR_PIT_DATA_EXPANSION
STOP_CURRENT_HISTORICAL_FEATURE_SET
```

A vendor recommendation may be a secondary engineering recommendation, but do not claim paid data guarantees Alpha.

Regardless of outcome:

```text
Strategy = EXPERIMENTAL
Qualified Direction Engine = NONE
Normal Runtime maximum = OPPORTUNITY_ONLY
Execution = DISABLED
Final Holdout = SEALED
Live trading = NOT AUTHORIZED
```

The purpose of v0.3.18 is to **compress development latency, not validation standards**: use the best trustworthy historical data now, borrow AlphaGPT's interpretable symbolic search architecture, freeze any promising candidate early, and let true Forward evidence challenge it while the 30-day campaigns continue accumulating.