# quant v0.6.5 — P1 executable cost-aware BTC 4–24h position-state evaluation

Task ID: V065-P1-COST-AWARE-POSITION-Z-ENGINE-R1
Dispatch: Controller 0 -> local Codex CLI 0.163.0, model gpt-6.1-sol, model_reasoning_effort=max; only if max explicitly fails, xhigh. MANUAL IMMEDIATE EXECUTION — NO SCHEDULER.
Repo: /root/workspace/project/quant-0.6.5, branch v0.6.5, SHA 12b74b4c2fd3a22a9f4b35dbf331cfb1166aae77 as of 2026-10-18 14:02 Asia/Shanghai (refresh before writing).
Mission: runnable cost-aware BTC 4–24h research code, focused tests, real execution outputs — NOT another report/audit.

## Frozen evidence

- Existing D2 QC/manifest v2 and R3 claimed-only clock are merged. Existing working P0 demo: scripts/research/r11_d2/offline_research_pipeline.py with tests at tests/research/r11_d2/test_offline_research_pipeline.py; 61/61 focused combined P0/data tests passed.
- 2026 Q3 historical archives: /root/workspace/project/crypto-data/historical/binance-usdm-expansion (210/210 QC PASS) and .../okx-swap-expansion (463/463 QC PASS). Binance market-day UTC, OKX archives UTC+8; align native timestamps and contract/spot identities rather than filenames. Original receiving clock PIT remains UNKNOWN.
- Q2 2026 only 6 Binance BTC/ETH fundingRate ZIP pilot files exist; no full Q2 bars/OI yet. Binance/OKX tick trades only approx one day, OKX BTC L2 only one day and its reported QC covers only a 2,000-message prefix (not entire expanded 3GB).
- Frozen read-only scientific report: /root/workspace/project-review-output/v065-sol-strategy-readonly-r1/STRATEGY_DIAGNOSTICS.md, SHA256 4359cde590a3ce79d7884623eb9b67e6bd76abe6e43667022893ad8b125fb3ff. READ sections 4–6 and use its 13-test synthetic protocol as an implementation contract, NOT historical profitable-backtest evidence. Enable Candidate A: incremental OI/position-state Z over lagged price/volume controls X. Candidate B liquidity recovery remains blocked by insufficient historical L2.
- OWNER R4 dirty docs/role files + locally modified D2 code and untracked P0/data modules must stay untouched. No stash/reset/checkout/clean/branch/worktree/stage/commit/push. Do not edit scripts/data, tools/data, tests/data (different data-agent ownership).
- The sole Controller task prompt is published in GitHub docs/engineering, not on local filesystem. Never write a duplicate prompt file. Do not create automated tasks.
- Low memory host (~1.9GiB RAM /1GiB swap): bounded streaming ZIP/CSV, no full L2 extraction.

## Allowed code and tests

Own NEW disjoint modules only:
scripts/research/strategy_eval/__init__.py
scripts/research/strategy_eval/pipeline.py
scripts/research/strategy_eval/costs.py
scripts/research/strategy_eval/clocked_dataset.py
tests/research/strategy_eval/test_*.py

Use a smaller factoring if prudent. Import existing D2/P0/R3 where appropriate, but do not edit their files without a precise reproduced defect. Preserve P0 no-action and fixed-origin invariants.

## Implementation deliverables

1. One-command CLI:
python3 -m scripts.research.strategy_eval.pipeline demo --output-dir /tmp/new-empty-dir
Prefer a second strictly read-only mode:
python3 -m scripts.research.strategy_eval.pipeline inspect-historical --binance-root ... --okx-root ... --output-dir /tmp/new-empty-dir
This inspections mode may read a bounded, nonprotected BTC archive for feature coverage but MUST NOT fit on unauthorized historical outcome labels.
2. Hourly origins HH:01 UTC with decision cutoff HH:00; X bars must close strictly before cutoff. Candidate A Z is native 5m historical Binance OI and top-position ratio with source observation sample ≤C-5m and not older than C-10m, and an exact 4h OI predecessor. Distinguish historical exchange sample time from actual receiver/ACK time. Missing, stale, invalid or future Z -> NO_ACTION and stable reason, scheduled origin retained; no future-fill/backfill or cherry-picked origins.
3. Implement frozen X and X+Z from report sections 4–5. Include always-NO_ACTION baseline and X-only model; train X vs XZ on identical eligible training rows. Do not use future labels, funding events not yet known, or favorable missingness filters. Primary horizon 8h, secondary 4/12/24h.
4. After-cost ledger: entry/exit maker-taker assumed fees, spread, slippage and funding in correct settlement chronology and side; baseline 16bp and stressed 32bp roundtrip as explicitly ASSUMED cost scenarios. Fees/slippage scale correctly by trade notional. Maker fill requires a scenario bound and cannot be guaranteed absent queue/ACK. Implement 1/H capital sleeves for overlapping hourly positions, not fictional independent wagers. Metrics: scheduled origins, NO_ACTION, acted-on trades, gross/net R and PnL, net-positive acted-on win-rate with denominator, fee/funding components, unresolved exits, turnover and tail outcomes. No post hoc choice of most favorable cost assumption.
5. Chronological train/validation on allowlisted EXPOSED_DEV only, report's 42/56/70-day fold boundaries, 14-day validation windows, 24h+ purge/embargo and inner seven-day blocks; reproducible seed/config and strict multiplicity limit. If insufficient clean history, return INSUFFICIENT_HISTORY rather than quietly dropping a fold.
6. Real-source separation: Q3 file dates overlap previously governed research holdouts. Do NOT silently treat the new Q3 archive as fresh unseen OOS, nor run historical outcome backtests on a protected/unauthorized date partition. Read archive manifests/QC and compute timestamp+X/Z availability/coverage as read-only descriptive metadata. Real-return exploratory runs require an explicit user-supplied allowlist of EXPOSED_DEV files and dates (new --exposed-dev-allowlist path), otherwise return EXPOSED_DEV_NOT_AUTHORIZED. Never access original Quant-agent/Quant-agent-sanitized/history, A-line/Final/OOS protected panels, prospective live data, account or orders.
7. Outputs: run_config.json, source_inventory.json, origins.jsonl, trades.csv, metrics.json, test_receipt.json (or consistent equivalent); stable deterministic scientific outputs, volatile clock/process metadata separate. Write only to fresh temp/output directory, reject unsafe symlink escape and non-empty destinations. Keep raw archives out of Git.
8. Focused negative and positive tests: malformed/future Z, wrong market/clock/schema, missing data, funding sign and timestamp, per-leg costs, maker fill unknown, origin denominator, embargo/lookahead, deterministic seeds, overlap capital, unsafe path and exposed-dev gate. Synthetic default demo generates actual PnL and NO_ACTION fixtures but is clearly labelled SYNTHETIC / NO_ALPHA_ESTABLISHED. Run targeted pytest only:
PYTHONPATH="$PWD/src:$PWD" PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q -p no:cacheprovider tests/research/strategy_eval tests/research/r11_d2/test_offline_research_pipeline.py
9. Demonstrate actual CLI, test exit codes, output files/action counts and one bounded 2026-07 BTC historical feature-readiness probe if possible. Verify existing Owner changes untouched. No whole-repo CI.

## Acceptance

P1_DEV_READY only for working code + actual CLI + deterministic outputs + focused tests PASS + source coverage inspection (or exact bounded blocker). Do not substitute a memo. Report edited paths, demo/test exit status and counts, cost arithmetic, synthetic vs historical qualification, and next missing data requirements. If blocked, return precise P1_BLOCKED with reproducer. Controller directly accepts ordinary engineering, no 1-A/2-C chain.

Safety labels remain: SOURCE_NOT_ADMITTED, PIT_UNKNOWN, COST_UNVALIDATED_REAL_FILL, NO_ALPHA_ESTABLISHED, G4_TESTNET_NO_GO, LIVE_NO_GO, REAL_FUNDS_WRITE_NONE. Do not change systemd, production Forward migration, run a market endpoint/WebSocket, enable real SOURCE_QA or execute funds/trades.
