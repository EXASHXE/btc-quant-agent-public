# BTC Quant Agent v0.3.18 — Historical Proxy Acceleration & Causal Symbolic Alpha Factory

## 0. Objective

This round accelerates strategy construction **without weakening Forward Evidence truthfulness**.

The project must continue the existing v0.3.16/v0.3.17 Forward campaigns unchanged, but in parallel build a **historical-development candidate sandbox** and a **causal symbolic alpha factory** inspired by the useful architectural ideas in `imbue-bit/AlphaGPT`.

This is NOT permission to trade real money. It is also NOT permission to reinterpret historical proxy results as Forward validation.

Primary goals:

1. Use historical Development data and strictly chronological masked/purged evaluation to build the end-to-end candidate framework now instead of waiting 30 days before writing strategy code.
2. Audit which historical derivatives / trade-flow datasets can be reconstructed with trustworthy timestamp provenance, and clearly separate them from true Forward PIT data.
3. Implement a causal Formula DSL + deterministic VM + Formula Registry, inspired by AlphaGPT but without importing its look-ahead / full-series normalization / simplistic best-backtest-wins semantics.
4. Implement a bounded symbolic search baseline (Random Grammar Search first; Genetic optional only if time remains). Do not train a Transformer policy generator yet.
5. Allow historical results to create only `PROVISIONAL_SANDBOX_CANDIDATE`, never `VALIDATED_FORWARD`, `LIVE_ELIGIBLE`, or execution authorization.
6. Continue H36 Opportunity, Derivatives successor, and Microstructure Forward collection with no gate reset or start-time movement.

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

The v0.3.17 branch may contain prompt-only commits after the formal delivery. Always start from the **latest remote HEAD** of:

```text
codex/v0.3.17-opportunity-successor-forward-stabilization
```

Work branch:

```text
codex/v0.3.18-historical-proxy-symbolic-alpha-factory
```

A branch with this name may already exist. Before implementation, fetch and fast-forward/rebase it to the latest remote v0.3.17 HEAD if necessary.

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
candidate_freeze = NONE
final_holdout = SEALED
```

No Binance order submission, no paper/testnet/live authorization, no Final Holdout access.

A historical sandbox may compute hypothetical LONG/SHORT labels and hypothetical PnL **inside research only**, but those objects must be explicitly tagged:

```text
PROVISIONAL_SANDBOX_ONLY
NOT_FORWARD_VALIDATED
NOT_RUNTIME_ACTIONABLE
```

---

## 3. Important statistical principle: faster collection does not replace calendar time

Do NOT claim that collecting 5m or 1m snapshots makes 7 calendar days equivalent to 30 calendar days.

Higher-frequency sampling may improve feature resolution, but effective independent sample size remains constrained by market autocorrelation and regime diversity.

Therefore preserve the existing formal Forward gates unchanged.

You MAY add an isolated auxiliary high-frequency derivatives capture campaign (recommended 5m, only if endpoint rate limits and semantics permit), but:

```text
AUXILIARY_HIGH_FREQ_PIT
```

must never count toward the existing formal v0.3.16 15m evidence gate.

If implemented, record:
- exact endpoint set;
- schedule;
- rate-limit budget;
- source timestamps;
- observed timestamps;
- duplicate/gap semantics;
- explicit `formal_gate_eligible=false`.

Microstructure is already stream-based; do not attempt to create fake additional independent samples by re-bucketing the same events.

---

## 4. Historical data acceleration track

### 4.1 Historical data provenance audit

Before any alpha search, create a machine-readable audit of historical sources available to the repository.

At minimum classify each dataset as one of:

```text
CANONICAL_HISTORICAL
OFFICIAL_HISTORICAL_TIMESTAMPED
DEVELOPMENT_PROXY
FORWARD_PIT_ONLY
UNAVAILABLE_OR_UNTRUSTWORTHY
```

Audit at least:
- BTCUSDT canonical 1m OHLCV;
- taker-buy volume / quote volume / trade count already present in canonical candles;
- official funding history;
- spot aggregate trades if available from official archive/history;
- perpetual aggregate trades if available from official archive/history;
- historical OI series if an official endpoint/archive can provide timestamped historical values;
- historical basis / premium / mark-price series;
- global long-short account ratio historical series;
- taker buy/sell ratio historical series;
- L2 diff-depth history;
- order-book snapshots.

Do not assume an endpoint supports 2021-2026 history merely because the current REST endpoint exposes a current value.

For every historical source record:

```text
source_name
provider
endpoint_or_archive
symbol
coverage_start
coverage_end
time_resolution
source_timestamp_semantics
retrieval_timestamp
checksum_or_manifest
lookback_limit
point_in_time_interpretation
known_biases
formal_role
```

If only recent history is available, use it only as a recent Development proxy and say so.

Do NOT backfill any historical row into Forward Evidence stores.

### 4.2 Strict historical masking semantics

Historical masking is allowed to accelerate framework construction, but masking alone does not restore global project innocence because earlier versions have already inspected parts of Development.

Therefore all such evaluation must be named:

```text
DEVELOPMENT_INTERNAL_PSEUDO_FORWARD
```

Never call it true OOS or Forward.

Implement a frozen chronological split protocol before any search results are inspected.

Recommended architecture:

- Discovery/search window: earlier Development only.
- Selection/validation window: later Development, never used for formula generation reward.
- Internal pseudo-forward window: final Development segment before `DEV_END`, touched only once per frozen top-K candidate set.
- Purge/embargo at boundaries >= maximum label horizon and maximum formula lookback.

You may choose exact dates based on existing Development coverage, but they MUST be frozen in a protocol JSON before running the formula search.

Final Holdout `[2026-02-01, 2026-08-01)` remains sealed and untouched.

---

## 5. AlphaGPT-inspired architecture to implement

Reference project:

```text
https://github.com/imbue-bit/AlphaGPT
```

Borrow the architecture ideas, not its research shortcuts.

Prefer clean-room reimplementation. If any code is copied directly, preserve required Apache-2.0 attribution/license notices.

### 5.1 Causal Formula DSL

Create a deterministic formula vocabulary over registered features.

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
ROLL_MEAN_N
ROLL_STD_N
ROLL_Z_N
EMA_N
DECAY_N
CLIP
```

Rules:
- every operator must declare arity;
- every operator must declare causal lookback;
- no full-series normalization;
- no future-dependent mean/std/median/MAD;
- no `torch.roll` wrap-around contamination;
- startup unavailable rows must remain unavailable/masked, not wrap from the end;
- divide-by-zero handling must be explicit;
- NaN/Inf handling must be explicit and auditable;
- a formula's total lookback must be computable before execution;
- unavailable input feature -> unavailable formula output, not silently zero unless the protocol explicitly defines a zero value.

Suggested files:

```text
src/btc_quant_agent/symbolic_alpha/dsl.py
src/btc_quant_agent/symbolic_alpha/vm.py
src/btc_quant_agent/symbolic_alpha/registry.py
src/btc_quant_agent/symbolic_alpha/search.py
```

### 5.2 Deterministic Stack/Expression VM

Inspired by AlphaGPT's StackVM, but production-research-grade:

- deterministic;
- typed formula tokens / AST or postfix representation;
- exact serialization;
- exact formula hash;
- no blanket `except Exception: return None`;
- return structured failure reason;
- unit tests for every operator;
- causality tests proving output at time `t` is unchanged when future rows `>t` are modified.

### 5.3 Formula Registry

Add a machine-readable registry, e.g.:

```text
configs/formula_registry.json
```

Each candidate records:

```text
formula_id
formula_hash
formula_tokens_or_ast
input_feature_ids
operator_set
max_lookback
search_run_id
search_budget
complexity
training_window
validation_window
pseudo_forward_window
metrics_by_fold
correlation_to_existing_candidates
status
research_eligibility
runtime_eligibility
```

Allowed statuses should distinguish at least:

```text
DISCOVERY_ONLY
FAILED_VALIDATION
PROVISIONAL_SANDBOX_CANDIDATE
REJECTED_REDUNDANT
REJECTED_UNSTABLE
```

No v0.3.18 formula may become `VALIDATED_FORWARD` or `LIVE_ELIGIBLE`.

---

## 6. Search engine: start simple before Transformer

Do NOT implement or train the AlphaGPT Transformer policy generator in this round.

First establish a transparent baseline:

### P0: Random Grammar Search

Use a fixed random seed and frozen search budget.

The search budget MUST be pre-registered before results.

For example, choose a bounded budget such as 2,000-10,000 valid unique formulas depending runtime; record the exact final number in the protocol.

Formula generation constraints:
- maximum token/AST depth;
- maximum lookback;
- reject algebraically trivial formulas where feasible;
- deduplicate by canonical formula hash;
- complexity penalty;
- avoid repeated evaluation of identical formulas.

### Optional P1: Genetic search

Only if Random Search + evaluation pipeline is complete and tested.

If implemented, freeze mutation/crossover/population/generation budget before formal run.

### Explicitly prohibited in v0.3.18

- Transformer/RL training;
- reward tuning after observing validation/pseudo-forward;
- unlimited search until a profitable formula appears;
- reversing a failed formula post hoc;
- scanning many thresholds on validation/test;
- using Final Holdout for search or selection.

---

## 7. Feature families allowed in symbolic search

Only features with defensible historical provenance may enter historical search.

Potential allowed inputs include, subject to the provenance audit:

- price/return/ATR/volatility features;
- canonical taker participation / volume features;
- funding history;
- spot/perpetual aggregate-trade flow features if historical coverage is valid;
- historical mark/premium/basis features if officially timestamped;
- any derivatives historical series proven by the audit to be timestamped and causally usable.

Do NOT synthesize historical L2 OFI from candles.

Do NOT pretend current-forward OI/basis/long-short snapshots existed historically if they cannot be reconstructed with trustworthy timestamped history.

Microstructure L2 features remain Forward-only unless a genuine historical L2 source with adequate provenance is found and audited.

---

## 8. Evaluation protocol for symbolic candidates

The formula generator/search objective may only use the Discovery window.

Validation must be separate from search reward.

For each top candidate evaluate at minimum:
- signed forward return at frozen horizons;
- hit rate / calibration if converted to directional score;
- trade count or event count;
- expectancy in R only if a frozen sandbox entry/exit rule is defined in protocol;
- PF / MDD only if actual sandbox trades are generated causally;
- turnover;
- fees/slippage stress where applicable;
- Early/Late stability;
- LONG/SHORT side stability;
- chronological fold stability;
- bootstrap confidence interval;
- candidate correlation/redundancy.

### Multiple-testing governance

Because formula search evaluates many candidates, explicitly record:

```text
number_of_unique_formulas_evaluated
number_reaching_validation
top_k_frozen_before_pseudo_forward
search_seed
search_budget
```

The internal pseudo-forward segment may be evaluated only for the frozen top-K selected without seeing pseudo-forward outcomes.

At minimum report a multiple-testing-aware caution metric or procedure. Preferred options include one or more of:
- Deflated Sharpe Ratio where appropriate;
- empirical null/permutation distribution of best-search score;
- bootstrap Reality-Check-style comparison;
- FDR control across candidate hypotheses.

Do not make a strong Alpha claim from nominal p-values after thousands of searches.

---

## 9. Build a candidate-ready sandbox framework now

The user's goal is to avoid waiting 30 days before building the trading framework.

Therefore implement a **research-only candidate sandbox** that can take a frozen provisional formula and combine it with the existing directionless TP/BR Opportunity layer.

Conceptual path:

```text
Historical/proxy Direction Score
        +
TP/BR Opportunity
        ↓
PROVISIONAL_SANDBOX_SIGNAL
        ↓
Frozen research Entry / SL / TP / sizing simulation
        ↓
Historical event-driven evaluation
```

Requirements:
- completely isolated from Runtime signal authorization;
- execution service must reject these objects;
- `source=HISTORICAL_PROXY`;
- `runtime_actionable=false`;
- realistic fee/slippage configuration reused from project research framework;
- no optimized final equity curve as sole objective;
- include WAIT/no-trade state;
- preserve deterministic reproducibility.

This builds the future tradable architecture now, while Forward Evidence keeps accumulating in parallel.

---

## 10. Forward campaigns must continue unchanged

Do not reset/restart/move the starts of:

```text
OPPORTUNITY_FORWARD_V0317_20260901T160000Z
DERIVATIVES_PIT_EPOCH_V0316_002
MICROSTRUCTURE_FORWARD_V0315_20260831T190000Z
```

Take a fresh status snapshot during the task and report:
- current expected/full/missing/partial Derivatives counts;
- H36 scan ratio / miss streak / opportunity count / resolved count;
- Microstructure age / trade coverage / depth coverage / sequence-valid coverage / partition integrity.

If a Forward campaign has terminally failed under its frozen gate, report it; do not repair by moving the start.

---

## 11. Tests

Add strong tests covering at minimum:

1. future-row mutation cannot change formula output at earlier timestamps;
2. no full-series normalization;
3. no `torch.roll` wrap-around leakage;
4. every rolling operator respects lookback;
5. formula max-lookback calculation;
6. deterministic formula hash / serialization;
7. VM structured error handling;
8. duplicate formula rejection;
9. frozen search seed and budget;
10. chronological split boundaries + purge/embargo;
11. pseudo-forward not touched during search/selection;
12. Final Holdout access blocked;
13. historical-proxy candidates are Runtime-blocked;
14. execution rejects provisional sandbox signals;
15. Forward stores are not mutated/backfilled by historical research;
16. existing H36/Derivatives/Microstructure safety states unchanged.

Run:

```bash
ruff check .
mypy
pytest -q
pytest --cov=btc_quant_agent --cov-report=term-missing
python -m compileall -q src skill-template/scripts
```

---

## 12. Deliverables — MUST be committed and pushed to GitHub

Create:

```text
deliverables/v0.3.18/
├── README.md
├── V0.3.18_HISTORICAL_PROXY_SYMBOLIC_ALPHA_REPORT.md
├── V0.3.18_NUMERIC_ANSWERS.json
├── V0.3.18_RECOMMENDATION.md
├── HISTORICAL_DATA_PROVENANCE_AUDIT.json
├── SYMBOLIC_DSL_SPEC.md
├── FORMULA_SEARCH_AUDIT.json
├── PROVISIONAL_CANDIDATE_REGISTRY.json
├── PSEUDO_FORWARD_EVALUATION.json
└── FORWARD_EVIDENCE_STATUS_SNAPSHOT.json
```

Also include the frozen research protocol under:

```text
configs/research/v0.3.18_historical_proxy_symbolic_alpha_protocol.json
```

The protocol MUST be committed before the formal search implementation/run or, if implementation scaffolding already exists, at minimum before any formal result-generating search is executed. Clearly document commit chronology.

At task completion:

```bash
git status
git log --oneline --decorate -12
git ls-tree -r --name-only HEAD deliverables/v0.3.18
git push -u origin codex/v0.3.18-historical-proxy-symbolic-alpha-factory
```

Create/update a PR after implementation and deliverables exist.

The task is NOT complete until all required deliverables are readable from GitHub remote.

---

## 13. Recommendation tree

Final recommendation must choose exactly one primary state:

```text
A. PROVISIONAL_SYMBOLIC_DIRECTION_CANDIDATE_FOUND
B. SYMBOLIC_PIPELINE_VALID_NO_ROBUST_CANDIDATE
C. HISTORICAL_PROXY_DATA_INSUFFICIENT_FOR_DIRECTION_RESEARCH
D. STOP_SYMBOLIC_SEARCH_PENDING_NEW_DATA
```

Even under A:

```text
qualified_direction_engine = NONE
runtime_maximum = OPPORTUNITY_ONLY
execution = DISABLED
final_holdout = SEALED
```

A only means the framework has found a **historical-development provisional candidate worth validating later**.

It is not a Forward-validated trading signal.

---

## 14. Forward-looking architecture after v0.3.18

If A:
- freeze the provisional formula;
- do NOT continue tuning it on pseudo-forward;
- wait for eligible Derivatives/Microstructure Forward data;
- compare the frozen formula against future Forward observations;
- only after true OOS/Forward support consider Candidate Strategy / Holdout / Paper/Testnet.

If B/C/D:
- keep the Symbolic DSL/VM/Registry infrastructure;
- do not increase search budget post hoc just to find a winner;
- revisit once new independent data families mature.

A later Transformer/AlphaGPT-style generator is allowed only after Random/Genetic baselines exist and sufficient data supports nested chronological validation.
