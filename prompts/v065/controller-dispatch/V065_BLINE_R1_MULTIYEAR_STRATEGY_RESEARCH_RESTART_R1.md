# quant v0.6.5 — BLINE-R1: multi-year BTC research restart

You are the direct quant research engineering implementer in the CURRENT agent session. Execute actual code, actual data feature construction and focused tests. Do not restart or choose an agent/model, open routine independent audits, or deliver a prose-only plan.

## Mission

Use the finished unified data lake to find a scientifically differentiated BTCUSDT perpetual 4–24h trading mechanism, fee-adjusted, targeting roughly one opportunity per 48h if genuinely viable. Reuse existing tools. At most TWO predeclared candidates. Zero successful mechanisms is an acceptable result; do not optimize to force positive backtest results.

## Baseline / allowed files

Worktree /root/workspace/project/quant-0.6.5, branch v0.6.5, last verified HEAD 12b74b4c2fd3a22a9f4b35dbf331cfb1166aae77. Preserve existing Owner dirty R4 docs, all P0/P1/P2/P3, catalog and tests. No reset/stash/checkout/clean/commit/push; no modifications to original Quant-agent, crypto-data/historical, ongoing Forward database or service. Preferred new code: scripts/research/bline_multiyear/ and tests/research/bline_multiyear/. Outputs only in new /root/workspace/project/crypto-data/lakehouse/research-bline-r1/.

DATA-C0 source catalog: /root/workspace/project/crypto-data/lakehouse/catalog.sqlite (2493 sources, 50 datasets).
DATA-C1 canonical physically complete: /root/workspace/project/crypto-data/lakehouse/c1/canonical_v1 (1881 partitions, 16,205,395 rows): Binance BTC perp+spot since 2021, BTC mark/index/premium/funding to Jan2026, Binance+OKX BTC/ETH Q2/Q3 2026 1m, Binance 5m OI and top-trader ratios, historical Binance ETH 1h. Actual missing spot/mark/price intervals are recorded.
DATA-C2 minute historical aggressor flow: /root/workspace/project/crypto-data/lakehouse/c2/minute_flow, 4/122 full month original BTC Spot/perp aggTrades ZIPs processed, completed months 2023-08 and 2025-09. Do not claim 2021–2026 full minute flow yet.
DATA-C3 clock contract under scripts/data/catalog/forward_clock.py and forward_compat.py, 37/37 focused tests PASS, C3 Forward 98 metadata entries ALL DEFAULT_DENY. Archive event-time is not verified receiver PIT. Never open/read/copy active or even closed Forward SQLite payloads for this task.

P1 frozen evaluator scripts/research/strategy_eval/pipeline.py expects hash-window-bound EXPOSED_DEV allowlist for real historical outcomes. Frozen protocol: hourly HH:01 origin with HH:00 cutoff, 4/8/12/24h, primary 8h, chronological 42/56/70 day development + 14d validation, 7d inner windows, 24h purge+1h embargo, fee scenarios 16bps/32bps plus actual funding, one/H overlapping sleeves and NO_ACTION denominator.
P3 Owner v2 is still P3_ACCESS_SCOPE_HOLD; old private A-line/Final/Forward protected dates not fully resolved. H40 protected [2025-02-01,2026-02-01) UTC; H39 begins 2026-09-01 UTC. Not all older dates are guaranteed unrestricted. Public archive availability does not constitute permission to evaluate protected outcome labels or declare OOS.

## Two research directions max — falsify, do not assume winners

1. LONG HISTORY derivatives state: ask whether lagged mark-index premium, perp-spot basis and funding state add incremental economic value to price/volatility/volume X under predeclared mean-reversion or continuation trigger. Available 2021–2024 broad BTC price / funding / premium. Select at most two fixed variants; account for missing Spot intervals and prior funding/basis/exit failures.
2. SHORT HISTORY actual OI/position state: test added value of Binance BTC 5m OI/top-trader ratios over matched X with optional source-compatible Binance/OKX basis, only 2026 Q2/Q3 where native data exist. Preserve 5–10m OI causal lag and exact 4h predecessor, and native event time versus receiver-known unknown. Do not claim 2021 OI data exist. Reuse P3-R3/P4 two-phase scope rather than rewriting P3.

Previous B-line trends/flow/breakout, funding/basis, PA-B and landmark/exit failure mechanisms must be consulted from actual project research ledger; tag FAIL, INCONCLUSIVE, SOURCE_BLOCKED, ECONOMIC_BLOCKED or UNTESTED with evidence. Avoid registering already falsified mechanisms as novel.

## Required execution

A. Inspect existing source schemas and known B-line findings. Produce machine-readable per-asset/per-venue/per-month feature eligibility and PIT status from C1+C2+C3. Build a real *feature-only* historical panel adapter with UTC HH:01 origin, strictly completed X bars, past-only funding, mark/index/premium, OI exact lag, optional signed flow only for available months. Keep N scheduled origins, N eligible, gap counts, no-action and exact source SHA lineage. No forward returns computed without authorization.
B. Produce preregistered_candidates.json with at most TWO genuinely distinct candidates: mechanism causal story, frozen signal formula, trade direction, time horizon, trigger, X baseline vs incremental Z, missingness handling, approximate opportunity frequency target not tuned, costs and all-scored/no-action denominator, rejection criteria, exact available development window and H39/H40/private exclusions. Provide comparison to previous failure families, ideally one long-history and one OI short-history direction or zero if not scientifically distinct.
C. Build reproducible CLI with actions feature-coverage, preregister, synthetic-p1, evaluate-authorized. For the last, fail closed unless an actual PREEXISTING signed Owner v2 scope + completed private exclusion attestation + derived valid P1 allowlist exist; do not forge these, bypass P3, read protected labels or calculate real historical trades while P3_ACCESS_SCOPE_HOLD. If project contains an independently explicit already-authorized DEV policy for another source, identify exact contract and comply, but do not infer permission just from access to files. Historical status EVAL_BLOCKED_SCOPE_UNRESOLVED is acceptable; complete other engineering work regardless.
D. Run a full synthetic 84d P1 end-to-end on new adapter to verify X/X+Z pairing, 3 outer folds, 16/32bp and funding, without suggesting synthetic profitability is Alpha. Test no-future bar/funding/flow leak, unavailable Z and NO_ACTION counted, H39 maturation edge, protected H40, source clock UNKNOWN, repeatable SHA, unauthorized real-outcome deny, duplicate old vs Q2 new ZIP identities, cost accounting and >2025 date exclusion.
E. Add focused tests only in new B-line and reused P1/C3 clock modules. Output actual code, CLI, real feature examples, coverage matrix, prior-mechanism failure map, two candidate register (or zero), synthetic_p1_summary, receipts with hashes/test counts/RSS and exact NEXT_EXPERIMENT.md listing minimal Owner decision if real outcome gate remains. Do not re-run whole CI or download historical trade archives.
F. At completion, give concise actionable Controller readout, not a serial review process. Check original raw sources immutable and existing dirty files preserved.

## Terminal

BLINE_R1_RESEARCH_PIPELINE_READY if real multi-year features, scientifically differentiated preregistration, synthetic P1 evaluator and focused tests run with reproducible artifacts, while real outcomes either legally permitted or explicitly held. BLINE_R1_NO_NEW_SOURCE_COMPATIBLE_CANDIDATE if investigation falsifies both candidates and no differentiable mechanism survives. BLINE_R1_PARTIAL on exact engineering blocker.
Maintain P3_ACCESS_SCOPE_HOLD, PIT_UNKNOWN, SOURCE_NOT_ADMITTED, NO_ALPHA_ESTABLISHED, G2_ALPHA_NO_GO, G4_TESTNET_NO_GO, LIVE_NO_GO and REAL_FUNDS_WRITE_NONE until specific future evidence and Owner authorization. No orders, TESTNET/LIVE, account or funds writes.