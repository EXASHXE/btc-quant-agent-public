# quant v0.6.5 — P3 evidence-gated historical research bridge and first eligible X versus X+Z analysis

Task ID: V065-P3-HISTORICAL-EVAL-BRIDGE-R1
Execution: MANUAL local Codex 0.163.0, gpt-6.1-sol with reasoning MAX, fallback XHIGH only if max is explicitly rejected.
Project: /root/workspace/project/quant-0.6.5, branch v0.6.5, last independently verified HEAD 12b74b4c2fd3a22a9f4b35dbf331cfb1166aae77. Refresh without resetting.
This is a substantial **engineering + bounded research execution task**, not a governance memo, automation, data downloader or production migration.

## First: verify prerequisite receipts, do not presume done

Owner reports **P2 cross-venue feature bridge** and **DATA-R3 Q2 data backfill** are complete. The Controller's remote desktop was OFFLINE at handoff, so these claims are not yet independently accepted. In first 15 minutes do finite read-only validation:
- Enumerate scripts/research/cross_venue/ and tests/research/cross_venue/, run their *targeted* pytest if code exists; invoke its actual demo/inspect commands against fresh scratch outputs. Capture source hashes, output schema, numbers of fixed decision origins, market/UTC semantics, no-action count.
- Check exact DATA-R3 manifests and QC, including historical/binance-usdm-2026q2 and historical/okx-swap-2026q2; identify per-source PASS vs missing/OBJECT_NOT_FOUND, dates, actual usable OI/trades/L2 and consecutive minutes; assess 2025 Q4/Q1 only if those new roots actually exist. Do not treat one missing OKX L2 day as a blanket failure of all Binance/OKX K-lines. Every source family retains distinct provenance.
- Keep P1 engine read-only: scripts/research/strategy_eval/{pipeline.py,clocked_dataset.py,costs.py}, existing tests. P1 last acknowledged DEV_READY with 2,016 synthetic hourly origins, 8,064 origin/horizon rows, 48 cells, 14,859 synthetic scenario trade records and strict EXPOSED_DEV gate. These are NOT real trades or Alpha. Reconfirm existing API surface before adapter design.
- If P2 files are missing, faulty, or R3 lacks even a contiguous month of target base bars+OI, return precise P3_PREREQ_BLOCKED with exact failing evidence. Do not invent PASS.
- Owner R4 dirty docs/roles/prompts must be fully preserved; no stash, reset, clean, checkout, branch/worktree creation, commit/push unless Owner separately instructs. Do not touch scripts/data, tools/data, tests/data or active Agy downloads. Prompt is only on GitHub docs/engineering: no local prompt copy.
- No original Quant-agent active data, protected A-line/OOS/H39/H40/Final data, trading, accounts, source-QA or production systemd actions. P3 historical archives remain HISTORICAL_OFFLINE / PIT_UNKNOWN.

## Research mechanism: one primary candidate, frozen

Only Candidate A — BTCUSDT USD-M OI/position-state Z over predeclared lagged price/volume X control; BTC-USDT-SWAP, ETH and spot are independent cross-venue controls where actually available, not arbitrary new alpha arms. No fishing over many techniques or timeframes.
- Decision origin at HH:01 UTC, cutoff C = HH:00. Last minute close must be strictly earlier than C. Z native 5m sample at most C-5m and no older than C-10m with exact 4h historical predecessor; never use bar closure or future funding after origin as feature. Native publisher timestamps != receiver first-known. Missing/invalid/late Z gives NO_ACTION, retain complete hourly denominator.
- Primary 8h, secondary 4/12/24h; reuse P1 fixed cost scenarios (16/32bp roundtrip as **assumptions**), actual funding debit chronology, 1/H capital sleeves and X vs X+Z matched eligible population. Frozen 42/56/70-day folds with 14-day outer validation and inner seven-day blocks; purge/embargo, no protected original OOS.
- Never upgrade historic source data to PIT_ADMITTED, execution-approved, real maker fill or Alpha because the code runs.

## Engineering task: make actual verified P2 data consumable by P1 without leakage

Own only NEW nonoverlapping files such as:
  scripts/research/exposed_dev_bridge/__init__.py
  scripts/research/exposed_dev_bridge/pipeline.py
  scripts/research/exposed_dev_bridge/authorization.py
  tests/research/exposed_dev_bridge/test_*.py

Implement reproducible, bounded, streaming CLI:
  python3 -m scripts.research.exposed_dev_bridge.pipeline inspect --binance-root <root> --okx-root <root> --output-dir <fresh>
  python3 -m scripts.research.exposed_dev_bridge.pipeline materialize --scope <explicit allowlist> --output-dir <fresh>
Optional evaluate subcommand delegates only to the existing P1 evaluator once authorized and suitable; do not duplicate P1 cost model.
- Inspect always read-only source QC; output immutable-hash mapped instrument/UTC/date/family coverage and every missing/late clock reason, including OKX UTC+8 day labels. Default status INSPECTION_ONLY, real outcome evaluation zero.
- With NO Owner-authorized explicit EXPOSED_DEV allowlist, implement and negative-test authorization contract but DO NOT materialize outcome labels or calculate historical strategy returns; produce a decision-ready **proposed dev-date scope** enumerating conflicts/uncertainty with governed holdouts. Never invent the Owner's authorization or reuse old exposed Q3 as fresh blind OOS. Propose before asking for approval, but task completes with an executable bridge and test outputs even when research-gated.
- For a *pre-existing* authorized allowlist actually present and verifiably applicable, validate exact data hashes, venue, market, symbol, time windows and permission for outcome evaluation, with path confinement and no symlink/alias bypass; then permit one bounded exploratory development run only, labelled EXPOSED_DEV / NOT_OOS. Never run if exact dates intersect protected restrictions or if clock coverage is insufficient. Prefer simple credible INSUFFICIENT_HISTORY over artificial favorable results.
- Inputs are source files existing before start, no downloader; stream archives in date batches under machine resource budget (host approx 1.9GiB RAM, 5GiB swap). Do not decompress full OKX 3GB L2; only inspect approved truncated prefixes for coverage where necessary. Manifest changes mid-run => INPUT_CHANGED not silently verified.
- Outputs: source_coverage.json, lineage_manifest.json, hourly_origin_coverage.jsonl, authorization_gate.json, feature_panel_schema.json, bridge_result.json plus test receipt in scratch new output dir. If allowed, include X vs X+Z matched coverage, costed results and uncertainty *without declaring edge from preliminary development*.
- Tests: Q2/Q3 stitch, UTC+8 day edge, funding sign and future settlement leakage, position ratio sample staleness, missing exact OI predecessor, native PIT unknown, protected date exclusion, explicit authorization denial, incomplete archive, changed hash, origin denominator, deterministic output; at least one bounded read from a real PASS archive. Use only focused tests, no full CI.

## Terminal outcomes and receipts

P3_BRIDGE_DEV_READY: runnable CLI inspection + source-labelled reproducible panel contract + safety-gated actual integration to existing P1 + targeted tests PASS and exact meaningful source coverage, even if outcomes remain explicitly unauthorized.
P3_DEV_EVALUATED_WITH_LIMITS: same plus eligible actual EXPOSED_DEV development returns only if pre-existing explicit Owner authorization and protected-scope checks pass, and sufficient folds are present. Full after-cost ledger required; no Alpha claim.
P3_PREREQ_BLOCKED or P3_ACCESS_SCOPE_HOLD: exact missing prerequisites/corroboration, avoid exploratory unauthorized returns.
List exact changed paths, commands, exit codes, tests, output counts, source hash, time windows, denied trial status, remaining clean-data/ack/queue constraints. No 1-A/2-C paperwork for ordinary code.

Safety: SOURCE_NOT_ADMITTED / PIT_UNKNOWN / NO_ALPHA_ESTABLISHED / COST_UNVALIDATED_REAL_FILL / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE. The existing F-R2 cutover stays separate.