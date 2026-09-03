# BTC Quant Agent — Canonical Project Context Handoff

Last updated: 2026-09-03

This document is the canonical compact context for starting a new ChatGPT/Gemini conversation without replaying the full historical chat. When this file conflicts with older prompts or prose, prefer the latest committed protocol/deliverable for the relevant version and preserve immutable historical evidence.

## 1. Project purpose

Build a deterministic, auditable BTCUSDT USDⓈ-M perpetual quantitative research and decision-support system for low-frequency personal trading research. The project is explicitly NOT a profit guarantee and is NOT authorized for live trading.

The intended long-run architecture is:

```text
Market data -> deterministic QuantCore -> Signal/Opportunity -> Agent orchestration/explanation -> user
```

The LLM/Agent is never the calculation brain. Deterministic Python owns features, structure, RR, sizing, replay, costs, probability calibration and all frozen gates. An Agent may orchestrate tools, explain results and surface alerts, but may not override WAIT, invent prices/probabilities, or rewrite research evidence.

## 2. Frozen safety state

Unless a later accepted release explicitly changes these values, assume:

```text
strategy = EXPERIMENTAL
qualified_direction_engine = NONE
runtime_maximum = OPPORTUNITY_ONLY
execution = DISABLED
auto_execute = false
live trading = NOT AUTHORIZED
final_holdout = SEALED
```

Historical research may create only explicitly tagged provisional research candidates. No model may silently promote a historical result into runtime/live eligibility.

## 3. Core strategy / research frame

Primary structural frame:
- 4H Macro
- 1H Regime
- 15m Setup
- formal decisions only on closed 15m bars
- 1m data may be used for causal replay/execution simulation, never to create a future-informed 15m signal
- Structure > EMA; EMA7/25 responsive, EMA25/60/99 broad context
- stop = structural invalidation + ATR buffer
- desired RR generally >= 1.5-2.0; frozen research baseline uses rr_min=1.8
- position sizing = desired account risk / stop-distance%, capped by max notional
- leverage changes margin/liquidation, not fixed-notional PnL%
- never fabricate live p_win or expected_r; keep null until calibrated OOS

## 4. Canonical data / split policy

Development window:
```text
[2021-01-01, 2026-02-01)
```

Final Holdout:
```text
[2026-02-01, 2026-08-01)
SEALED
```

Canonical BTCUSDT USD-M 1m development/holdout source was frozen with checksum/provenance controls. Historical masks inside Development are DEVELOPMENT_INTERNAL_PSEUDO_FORWARD, not virgin OOS.

Data provenance roles used by the project:
- CANONICAL_HISTORICAL / OFFICIAL_HISTORICAL_TIMESTAMPED
- VENDOR_RECORDED_HISTORICAL_PIT_PROXY
- DEVELOPMENT_PROXY
- TRUE_FORWARD_LOCAL_PIT / FORWARD_PIT_ONLY

Never synthesize L2/OFI/microprice/depth from candles. Historical vendor receive timestamps are not equivalent to this machine's true Forward observed_at.

## 5. Research governance

Rules:
1. Preregister protocol, split, seed, hypothesis, budget and gates before outcome inspection.
2. Discovery may search only inside its frozen budget.
3. Validation is separate from Discovery.
4. Internal pseudo-forward is touched once by frozen top-K/candidate logic.
5. Final Holdout stays sealed until an explicitly authorized final validation stage.
6. Multiple testing must include all reward-evaluated formulas/arms in the formal family.
7. No post-hoc direction reversal, parameter expansion or search-until-profitable behavior.
8. Failed/falsified feature families are stopped unless a genuinely new audited data family creates a new preregistered hypothesis.
9. Forward missed slots are evidence; never backfill them as if observed live.
10. Same market input + config/version must reproduce the same deterministic output.

Typical qualification target used as guidance, not an automatic promise:
- OOS expectancy > 0
- PF >= 1.2
- positive folds >= 70%
- sufficient trade/sample count
- cost-stress robustness
- parameter/local stability
- acceptable drawdown/losing streak bootstrap behavior

## 6. Research history and conclusions

### v0.3.0-v0.3.5: baseline and geometry/direction diagnostics
- v0.3.0 baseline: only 13 trades, negative expectancy; no candidate.
- v0.3.1 confirmed severe funnel scarcity.
- v0.3.2 showed bottleneck was geometry, not merely fees/min-notional.
- v0.3.3 found historical movement/reachability but exposed non-causal entry/target issues.
- v0.3.4 causal TP retrace produced 2 fills, both losses; TP direction research suspended.
- v0.3.5 breakout-retest direction/gates failed; architecture reset.

### v0.3.6: architecture reset
- direction hypotheses H14-H17 falsified.
- H18 Opportunity Layer supported: TP/BR states predict elevated movement magnitude, not direction.
- important rule: failed direction signals are not reversed post hoc.

### v0.3.7-v0.3.12: new feature-family tests
- funding crowding/stability: weak or unstable, family stopped.
- cross-asset breadth: falsified, family stopped.
- range mean reversion: descriptive movement/center-hit effects but no qualified profitable strategy.
- spot/perp taker flow: inconclusive/falsified incrementally; no direction candidate.

Conclusion at this point: price-only and several simple derivative/context direction primitives were exhausted. The strongest durable result was directionless Opportunity/movement magnitude.

### v0.3.13-v0.3.17: Forward evidence infrastructure
Built true forward chains:
- directionless Opportunity shadow
- derivatives PIT snapshots
- microstructure diff-depth + aggTrade capture
- outcome resolver
- health watchdog

Key campaign history:
- H35 Opportunity: archived DATA_QUALITY_AT_RISK.
- DERIVATIVES_PIT_EPOCH_V0314_001: terminal due data-quality gap gate.
- MICROSTRUCTURE_CAPTURE_V0315_001: long-running capture campaign.
- DERIVATIVES_PIT_EPOCH_V0316_002: successor; later became terminal after host/proxy failure.
- H36 OPPORTUNITY_FORWARD_V0317_20260901T160000Z: successor; later became terminal after host/proxy failure.

### v0.3.18: causal Symbolic Alpha Factory
Built:
- typed Formula DSL
- deterministic VM
- Formula Registry
- bounded Random Grammar Search
- pseudo-forward firewall
- research-only event-driven sandbox
- AlphaGPT reference adaptation

Formal result:
- 512 unique formulas under frozen budget
- familywise adjusted discovery p-value ~0.3582
- no candidate
- no provisional shadow

Important AlphaGPT lesson: retain symbolic DSL/VM and model-guided proposal ideas, but reject full-series normalization/look-ahead, repeated best-backtest selection, weak OOS control and simplistic execution assumptions.

### v0.3.19: official derivatives feature expansion + gate hardening
Formal delivery lineage:
- formal implementation SHA: a26b657379f1b2e0f463c6cd614d4849f1c1b833
- formal/published result SHA: eaa75330854d54e9967f3c0c0446bd6d4b34a76e

Key work:
- fixed bootstrap block unit semantics: 168h / 8h = 21 events
- made candidate gates typed/fail-closed
- fixed sandbox slippage and executed-entry semantics
- raised direct symbolic-module coverage
- downloaded/checksum-verified 366 official Binance archives (~85.65 GB raw)
- built 8 genuinely new official-derivatives/aggTrade features
- reran bounded new-feature-constrained symbolic search

Formal result:
- 512 valid unique formulas
- 20 validation candidates, frozen top-5
- empirical familywise adjusted p-value = 0.4328358209
- candidate_exists = false
- provisional_shadow_started = false
- Final Holdout rows loaded = 0
- historical Forward-store writes = 0
- recommendation = STOP_OFFICIAL_DERIVATIVES_SYMBOLIC_FAMILY

Do not reopen this family by merely increasing search budget or adding a Transformer proposal engine.

### v0.3.20: Forward infrastructure recovery and deployment hardening
Current accepted implementation/review branch:
```text
gemini/v0.3.20-forward-infrastructure-recovery-deployment-hardening
```

Latest checked branch head at handoff creation:
```text
b8bcef04106d7eedf7ea928d9de26810f9bd1ecc
```

Latest GitHub Actions CI on that head: SUCCESS across Python 3.11/3.12/3.13.

Forensic root causes found:
- Windows Modern Standby suspended WSL for ~5.5h.
- proxy egress used a US exit and Binance Futures endpoints returned HTTP 451.
- clock-alignment code crashed when all source timestamps were absent.
- microstructure heartbeat thread could die on sqlite database locks.
- status checks were too expensive (~65s) and caused contention.
- WSL user linger was disabled.

Repairs:
- Forward Doctor and recovery diagnostics
- clock max() fix
- heartbeat lock tolerance + supervisor
- microstructure partition/status caching (~65s -> ~2.6s reported)
- systemd hardening / linger setup
- Windows lifecycle tooling
- Linux VPS deployment package
- research-data concurrency policy
- terminal chain archiving and clean successor preregistration

Acceptance-repair results:
- HTTP451 test made deterministic across Python 3.11/3.12/3.13
- local full suite reported 429 passed
- CI green on repaired head
- microstructure restarted healthy with fresh heartbeat and low memory
- linger verified enabled

However, the preregistered v0.3.20 Derivatives/H37 successors were empirically compromised before network eligibility was fixed:
- 5 expected slots after 06:30 UTC
- Derivatives: 5/5 HTTP451 failures, consecutive streak 5 > max 4
- H37 Opportunity: 5/5 missed decision slots, streak 5 > max 4
- therefore those two successors are terminal/compromised and must NOT be reset or backfilled
- microstructure was healthy collecting in the last committed post-start snapshot

The next valid forward successor must be preregistered only after network access is compliant and operationally verified. Do not use proxies to bypass jurisdiction/account restrictions; use a legally eligible environment/provider or alternate compliant data source.

## 7. Current runtime / operations

Local project path:
```text
/root/workspace/project/Quant-agent
```

Forward tasks historically run in local WSL Ubuntu via systemd:
- derivatives PIT timer every UTC quarter hour +20s
- Opportunity scanner every UTC quarter hour +50s
- resolver hourly around :07
- microstructure daemon continuously
- health watchdog around :08/:23/:38/:53

Windows/WSL shutdown, sleep, network loss or proxy errors create real Forward gaps. Persistent timers cannot recreate historical true-PIT snapshots after downtime.

Recommended production data-collection topology:
```text
24x7 Linux VPS / compliant region
  -> Forward collectors
  -> immutable local stores + off-host backup

Local workstation
  -> development
  -> historical research
  -> symbolic search
  -> review
```

## 8. Repository workflow

Repository:
```text
EXASHXE/btc-quant-agent
```

New policy after repository cleanup:
- `main` is the canonical accepted lineage and must be kept current.
- implementation work uses one short-lived stage branch.
- review artifacts are committed against the exact stage SHA.
- once accepted, fast-forward/merge to main and close/delete the stage branch.
- old version branches are unnecessary after their commits are ancestors of main.
- preserve versioned protocols/prompts/deliverables in Git as research evidence; do not delete them just because a branch is old.
- large raw market data/SQLite/Parquet stays gitignored/local or in external storage.

## 9. Multi-model workflow

From the next stage onward use independent multi-model checks:
1. ChatGPT and Gemini-3.8-Flash independently critique the proposed hypothesis/protocol before freeze.
2. One implementation agent edits the repository; reviewers do not concurrently modify the same code branch.
3. After push, Gemini-3.8-Flash performs a blind independent review of the exact SHA.
4. ChatGPT independently reviews the same exact SHA.
5. Compare verdicts and create a disagreement matrix.
6. Any unresolved high-severity research-integrity, data-causality, execution-safety or Forward-evidence objection blocks promotion.
7. Only after resolution does the stage advance.

See `docs/MULTI_MODEL_RESEARCH_GOVERNANCE.md` and `prompts/review/Gemini_3.8_Flash_Independent_CoReview_Prompt.md`.

## 10. Immediate next plan

P0 — repository/operations hygiene:
- make `main` current
- close superseded PRs
- delete temporary/old remote branches once verified ancestors of main
- keep only main + the currently active short-lived implementation/review branch
- preserve research deliverables/protocols/prompts as audit history

P1 — Forward recovery:
- verify market-data access is legally/operationally available without HTTP451
- verify Forward Doctor HEALTHY before preregistering any new successor
- preregister fresh Derivatives and Opportunity successors on a future UTC boundary
- prove several natural post-start successful slots before calling recovery complete
- prefer migration of primary collectors to a 24x7 Linux VPS

P2 — new research only after Forward operations are stable:
- do not reopen stopped official-derivatives symbolic family
- next direction family should require genuinely different auditable information, likely vendor PIT OI/L2/liquidations or other microstructure/derivatives data
- vendor history remains VENDOR_RECORDED_HISTORICAL_PIT_PROXY, never true local Forward
- keep Final Holdout sealed until a truly qualified candidate exists

P3 — candidate lifecycle if one is ever earned:
```text
Development discovery
 -> Validation
 -> Development internal pseudo-forward
 -> frozen historical candidate
 -> future-only provisional candidate Forward Shadow
 -> 30-60d / sufficient-sample real Forward challenge
 -> execution parity / paper-testnet only if authorized
 -> tiny live only after explicit separate authorization
```

## 11. Stop rules that must survive context migration

- No live execution.
- No fabricated p_win/expected_r.
- No Final Holdout peeking to rescue a weak family.
- No random masking presented as OOS.
- No search-until-profitable.
- No post-hoc reverse-the-signal logic.
- No rebuilding true Forward gaps from later historical data.
- No synthetic historical L2/OFI from candles.
- No vendor/local/archive timestamp role confusion.
- No single-model approval for a new research/strategy promotion once multi-model governance is active.
