# quant v0.6.5 — P2 cross-venue BTC historical feature bridge (execution-first)

Task ID: V065-P2-CROSS-VENUE-FEATURE-BRIDGE-R1
Primary implementer: Codex CLI 0.163.0, model gpt-6.1-sol, reasoning max. If and only if Max runtime rejects request, xhigh (Extra High).
Execution mode: MANUAL, NOT scheduled. Aim to produce real runnable code, positive+negative tests, actual QC/feature coverage results. No reviewer escalation for routine implementation.
Repository: /root/workspace/project/quant-0.6.5 branch v0.6.5 HEAD 12b74b4c2fd3a22a9f4b35dbf331cfb1166aae77 at 2026-10-18 ~14:50 Asia/Shanghai; refresh before writing.
Owner R4 mandates lean, progress-driven engineering. No commit/push/branch/worktree by default.

## State and evidence (verify, don't repeat reviews)

1. Existing P0 D2 QC+manifest v2, R3 claimed-only fixed-origin clock and single-command synthetic demo are present; previous combined P0/data tests 61/61 pass.
2. Existing P1 cost-aware engine has been delivered as DEV ONLY in scripts/research/strategy_eval/{__init__.py,pipeline.py,clocked_dataset.py,costs.py} and tests/research/strategy_eval/*.py. Owner completion receipt: 148/148 P1+P0 tests pass; demo emits six required files, 2,016 scheduled hourly origins, 8,064 origin/horizon rows, 48 evaluation cells, 14,859 **synthetic** model/scenario trades (NOT live trades); July BTC historical inspection read 95 objects and 187,488 native rows, 719/744 eligible features, no outcome evaluation. Without explicit EXPOSED_DEV allowlist, historical evaluation returns EXPOSED_DEV_NOT_AUTHORIZED. You must confirm current actual code and relevant tests but don't rerun huge suites if unchanged.
3. Read-only mechanism report: /root/workspace/project-review-output/v065-sol-strategy-readonly-r1/STRATEGY_DIAGNOSTICS.md, SHA256 4359cde590a3ce79d7884623eb9b67e6bd76abe6e43667022893ad8b125fb3ff. Enabled development candidate A: hour-grid BTC derivatives position state incremental Z over lagged X, not a validated edge. Liquidity recovery B remains conditional on longer L2.
4. Actual data roots, READ-ONLY FOR YOU:
 /root/workspace/project/crypto-data/historical/binance-usdm-expansion (Q3 2026, 210/210 PASS)
 /root/workspace/project/crypto-data/historical/okx-swap-expansion (Q3 2026, 463/463 PASS)
 /root/workspace/project/crypto-data/historical/binance-usdm-2026q2 (Q2 2026, 208/208 PASS as of 14:51)
 /root/workspace/project/crypto-data/historical/okx-swap-2026q2 (Q2 2026, 457/458 PASS; sole absent archive is BTC-USDT-SWAP 400-level L2 on OKX archive label 2026-04-01. NOT FULLY PASS).
 Agy DATA-R3 owns all new/continuing downloads, QC, write receipts, tools/data, scripts/data and tests/data. It may still be active. You may consume only already atomically published, verifiably stable PASS objects, and must not read .part/staging or race changed manifests. Snapshot manifest SHA at beginning+end, stop or label INPUT_CHANGED for moving inputs. Do NOT modify, rename, delete, re-download or rehash a 3GB expanded archive in RAM.
5. Runtime machine WSL ~1.9GiB RAM, 5GiB swap, disk ample. Never full-expand OKX L2 or accumulate a quarter of all 1m rows into a large in-memory dataframe.
6. Preserve all 14 uncommitted Owner R4 docs and prompt changes, the existing modified D2 pilot and untracked P0/P1/data code. Do not stash, reset, checkout, clean, autoformat unrelated files, stage, commit, pull --rebase or push.

## Distinct write set

You own new code exclusively:
 scripts/research/cross_venue/__init__.py
 scripts/research/cross_venue/pipeline.py
 scripts/research/cross_venue/normalized_sources.py
 tests/research/cross_venue/test_*.py
Smaller factoring is encouraged. Read-only imports from P1 (e.g. clocked_dataset feature and config dataclasses) are allowed; do not modify P1/P0 modules that another worker may own. If integration needs new stable API, implement a bridge adapter in YOUR module rather than patching P1. No direct write to data roots. Tests output only to tmp_path.

## Functional scope

A. Implement one demo + one actual historical INSPECTION (no outcome labels / no backtest) in a single module:
  python3 -m scripts.research.cross_venue.pipeline demo --output-dir /tmp/new-empty-path
  python3 -m scripts.research.cross_venue.pipeline inspect-historical --binance-q3 <path> --okx-q3 <path> --output-dir /tmp/new-empty-path
Allow optional explicitly selected Q2 directories only after their manifest/QC stable; never auto-include incomplete sources as if complete.
B. Normalize physically available BTC and ETH perpetual+spot 1m bars (Binance USD-M BTCUSDT / ETHUSDT and OKX BTC-USDT-SWAP / ETH-USDT-SWAP, spot controls), preserving venue, contract type, price unit, raw hash, native sample/close time, UTC event time and archive calendar label. OKX daily filename is UTC+8, while Binance monthly archive UTC. For Q3 their 1m intersection is 91d16h (132,000 aligned minutes), **not** 92 full UTC days. Detect and quantify exactly this; do not insert imaginary trailing OKX bars.
C. Extract bounded, causal-alignment-safe cross-venue features: lagged venue price/basis spread, spot-perp basis, mark-versus-last (where available), funding ACTUAL settlement calendar (not forward funding), and Binance 5m OI / top position ratios as development Z where eligible. Mark OKX historic OI / position fields UNKNOWN if not actually sourced; do not fabricate them. Separate native label clock from receiver first-known PIT. For origin HH:01 UTC with C=HH:00 enforce pre-cutoff features, Z sample ≤C−5m and >=C−10m and exact 4h predecessor; missing/stale → NO_ACTION, denominator retained. A cross-venue signal is NOT permitted to turn historical archive into source-admitted, no outcome-based eligibility.
D. Compute for each scheduled origin an actual feature-coverage row and source-specific blockers, Q2 vs Q3 plus BTC vs ETH and Binance vs OKX; emit source_inventory.json, lineage_manifest.json, origins.jsonl, coverage.json, diagnostics.json with stable deterministic scientific content. If streaming full Q3 is resource-intensive, use bounded month/day chunk iteration; prove exact intersection from archive metadata first, then a complete or explicitly sampled feature coverage scan. Report SKIPPED_SCAN_BUDGET rather than misleading full coverage if budget hit.
E. Test real semantic corner cases: OKX UTC+8 edge, Binance 1m closed-bar rules, 5m OI lookahead, missing 4h predecessor, unknown OKX OI, missing L2 in April, spot/swap family mismatch, duplicate timestamps, stale/future funding, manifest SHA changed, non-PASS archives, fund source PIT UNKNOWN, no-action origin denominator, read-only protected input aliases, symlink/unsafe output paths and byte reproducibility. At least one integration test reads a tiny bounded real Q3 source without writing that source. No online market endpoints, no account or execution client. Use streaming, deterministic fixtures.
F. Optionally provide P1 adapter handoff CONTRACT ready to feed fixed-origin candidate A X/Z with correct type semantics and predeclared feature vector, but DO NOT call P1 historical outcome evaluation or attempt real-return Alpha without Owner-selected EXPOSED_DEV dates/allowlist. Do not peek protected OOS, A-line, H39/H40, historical targets, original Quant-agent, or Forward stores.

## Verification

Run targeted tests only, with:
 PYTHONPATH="$PWD/src:$PWD" PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q -p no:cacheprovider tests/research/cross_venue
Run both commands on fresh temporary output dirs. Record actual exit codes and counts, missingness by source and a strict stdout status CROSS_VENUE_DEV_READY, PARTIAL_SOURCE_COVERAGE, or BLOCKED_EXACT_CAUSE.

Definition: CROSS_VENUE_DEV_READY means real normalized BTC/ETH source-time alignment, correct Q3 intersection, feature readiness and NO_ACTION over a fixed origin grid, source hashes recorded, deterministic machine-readable outputs, focused tests PASS. Q2 is optional while Agy continues to acquire; report Q2 missing April OKX L2 explicitly. Distinguish data QC PASS from receiver PIT admission and executable fills. No claims of positive Alpha based on this descriptive feature readiness task.

Hard project gates: SOURCE_NOT_ADMITTED, PIT_UNKNOWN, COST_UNVALIDATED_REAL_FILL, NO_ALPHA_ESTABLISHED, G2_ALPHA_NO_GO, G4_TESTNET_NO_GO, LIVE_NO_GO, REAL_FUNDS_WRITE_NONE.
