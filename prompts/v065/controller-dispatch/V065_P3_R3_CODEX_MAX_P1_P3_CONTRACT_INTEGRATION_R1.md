# quant v0.6.5 — P3-R3 Codex Max: executable real-source outcome integration, without unauthorized results

**Task:** V065-P3-R3-REAL-SOURCE-ADAPTER-INTEGRATION-R1  
**Execution:** MANUAL local Codex CLI 0.163.0 with gpt-6.1-sol, model_reasoning_effort=max. Only if Max actually rejected, use xhigh. No timed task.
**Checkout:** /root/workspace/project/quant-0.6.5, branch v0.6.5. Last verified HEAD 12b74b4c2fd3a22a9f4b35dbf331cfb1166aae77 at 2026-10-18 18:50 Asia/Shanghai; reverify on entry, don't reset.
**Operator role:** direct engineering implementer, NOT a new scientific reviewer. Deliver runnable integration code, targeted tests, actual CLI demonstration and acceptance receipt, not another plan.

## Current verified state

P0 base research pipeline DEV_READY. P1 cost-aware OI X-vs-XZ evaluator DEV_READY. P2 cross-venue source time feature bridge DEV_READY. P3 source/EXPOSED_DEV bridge DEV_READY. Gemini Flash P3-R2 contributed:
- scripts/research/exposed_dev_bridge/outcome_adapter.py, updated authorization.py, pipeline.py and test_outcome_adapter.py.
- Owner's 2026-10-18 17:55 synthetic demonstration at /tmp/v065-p3-r2-scope-gemini-flash/demo/ (72 synthetic origin rows, P1 economics call, 40 8h synthetic resolved trades, REAL_HISTORICAL_OUTCOMES_READ=0).
- Controller reran tests at ~18:50: 138/138 PASS (tests/research/exposed_dev_bridge plus P1 clock/cost tests, exit 0).
- **P3_ACCESS_SCOPE_HOLD**: no actual Owner-signed EXPOSED_DEV scope, private A-line/Final/Forward overlap dates unresolved; DO NOT run any historical return/outcome evaluation.
- Genuine engineering gap: P3 outcome_adapter.build_panel_row stores every outcome key even when value is null; P1 strategy_eval.pipeline.authorized_panel loops supplied outcome keys and requires Outcome.from_dict on each supplied value, which rejects null. P1 uses a distinct strategy_eval.exposed-dev.v1 allowlist that pins normalized panel path+SHA+UTC coverage, while P3 authorization has exposed_dev_bridge.owner-scope.v2 with archive hashes and separate archive/origin ranges. No complete verified P3-to-P1 dual-gate adapter currently exists. P3 materialize still calls materialization_hold and explicitly emits SAFE_HOLD_NO_OUTCOME_PANEL_WRITTEN.
- Five-hour tasks should build code rather than endless audits. No mandatory 1-A/2-C routine review.

## Frozen source proposal and constraints

Preflight evidence root (read only):
/tmp/v065-p3-scope-preflight-gemini-flash-r1/
  protected_scope_matrix.json SHA256 c6b0669564df9029749167482f5e58952ebcb0ba614b7618a59b7d8015c7d3f0
  eligible_object_candidate.json SHA256 3209d9f0a817c83d3f75da5b5669967ded44aee94c4b2076aa6d49b137d46e2b
  OWNER_EXPOSED_DEV_DECISION_TEMPLATE.json SHA256 d77063c4f07885f1146dd79f98c481ab65746363e08ad72912f188c660c33b5b
  OWNER_SCOPE_DECISION.md SHA256 fff5427868c0ee978d6f7659309c306d4984796dd9c4e5f999a2d00e0f999a65

P3-R2 unsigned v2 candidate currently under /tmp/v065-p3-r2-scope-gemini-flash/OWNER_EXPOSED_DEV_DECISION_TEMPLATE_V2.json; do not sign/authorize it. Verified 632 PASS compressed archives are only proposed eligibility. Source envelope UTC [2026-03-31T16:00, 2026-09-01T00:00) encompasses their exact whole-file windows, candidate origin window [2026-04-03T00:00, 2026-09-01T00:00). Horizon 24h requires origins strictly before 2026-08-31T00:00 to mature before the H39 boundary. H39 excluded from Sep 1; H40 confirmation holdout 2025-02-01..2026-02-01; private protected dates remain UNKNOWN and block authorization.

Data correctness: Q2 Binance June BTC markPriceKlines is checksum PASS but has 1440 missing 1m rows; 2026-08-26 OKX ALL_SWAPS funding archive reports three aggregate gaps (not automatically BTC); OKX BTC L2 2026-04-01 OBJECT_NOT_FOUND (not a blocker for OI mechanism A). Q2/Q3 source files are historical publisher-native timestamps, NOT native receiver-known PIT. Low RAM host ~1.9GiB, swap 5GiB; stream, never expand 3GB L2, don't load whole quarter in memory.

## Code ownership and target

Only edit owned code:
  scripts/research/exposed_dev_bridge/*.py
  tests/research/exposed_dev_bridge/test_*.py
You may READ P1/P2/D2/data modules, but must not alter them without a precise reproduced interface defect and explicit recorded justification. Preserve existing Owner R4 tracked dirty docs and all untracked P0/P1/P2/R3 data code. No commit/push/stash/reset/checkout/clean, no local prompt file, no extra worktree/branch.

### P3-R3 engineering requirements

1. **Contract compatibility**: inspect actual P1 normalized.v1 panel required fields (row t, 10 X controls, Z, x_end, status, exact 4h predecessor, 4/8/12/24h Outcome schema, funding). Resolve the P3 null-outcome vs P1 Outcome.from_dict incompatibility with explicit MISSING/UNRESOLVED handling that DOES NOT silently convert missing outcomes to zero PnL, fake fills, or profitable no-action. Ensure P1's fixed-origin denominator (and per-horizon denominators) is retained. Unit-test against the actual P1 parser on synthetic data.
2. **Dual authorization proof-of-possibility**: a real historical pipeline may proceed ONLY after separate original Owner EXPOSED_DEV v2 permission and complete private-protected-date verification, and P1 strategy_eval.exposed-dev.v1 allowlist pinning the output panel full path/SHA/date interval. Build an adapter that on a TEST-ONLY SYNTHETIC scope can generate a deterministic normalized panel and a P1-compatible explicitly labelled synthetic allowlist. For real inputs the permit paths must derive from a PREEXISTING, valid Owner authority; never generate or grant owner permission or set holdout_status/complete yourself. No user request in this turn grants authority.
3. **Streaming real archive adapter implementation**, with strict default metadata/feature-only mode. Connect actual Q2/Q3 PASS archive source record parsing to the native features, funding reference and outcomes construction, preserving source path/hash, market (BTCUSDT USD-M vs BTC-USDT-SWAP vs spot), event/sample UTC and first-known receiver clock UNKNOWN. Use a bounded date/day/quarter iterator for real returns and actual source-price/funding labels, but gate BEFORE reading ANY price rows designated as realized future labels; unsigned invocation must never read them or call any historical evaluate. It is fine to run read-only source metadata/feature QC and source hash verification in this session. A real-data outcome-capable code path may be implemented and tested on SYNTHETIC ZIP fixtures only. No calls to exchange endpoints.
4. **Correct causality**: fixed HH:01 origin, C=HH:00; closed bars strictly before cutoff; OI native 5m Z sample must be 5..10min old plus exact 4h predecessor; pricing entry at HH:02 OPEN and exit matching H; funding only for entry < settlement <= exit, correct side/notional and actual missingness; require mark and funding availability in native source, no interpolating 1440 minute mark gap or inventing BTC funding events from aggregate missing rows. Preserve all scheduled origins and NO_ACTION categories.
5. **Frozen research/economics**: reuse P1 cost math and outer split choices (42/56/70 days, 14d validation, inner 7d, purge/embargo, 16bp/32bp cost assumptions and 8h primary). Do not introduce new hypotheses, hyperparameter search or evaluate profitable results to choose dates. All BTC X vs XZ comparisons must share same eligible data population.
6. **Run commands and test receipt**: provide a reproducible one-command dev CLI, e.g. synthetic-contract-demo + protected/scope-negative cases, output stable normalized_panel.json, P1 allowlist fixture and provenance ledger, summary/test_receipt. Test actual P1 authorized_panel() and, if bounded, P1 evaluate() on purely synthetic 84+ days of normalized data; if not feasible with host memory, explicitly report FULL_FOLD_SYNTHETIC_NOT_RUN and demonstrate the parser+funding+cost path at shorter horizon without claiming 84-day full-sample success. No data in repo, outputs only to fresh isolated /tmp dir. Use focused pytest only; collect total count, terminal statuses, codes and changed paths.
7. **Fail-closed cases**: no scope / UNSIGNED v2 / missing private partition attestation => early rejection before labels read; fake hash, wrong contract, mismatched P1 allowlist, symlink alias, changed manifest, unavailable future settlement, partial source coverage, H39 right-boundary, outcome null and post-origin Z, stable no-action denominator. Never use CLI flag --synthetic on real materialize as a hidden authorization bypass; offer clearly separate dev demo instead.
8. **Ready for actual Owner decision**: return the exact remaining external approval step, source-hash/date receipt and how the future Owner-authorized evaluation command will work; do not execute any real historical return. Terminal state P3_R3_E2E_DEV_READY or P3_R3_BLOCKED with exact reason. Neither is ALPHA_PASS.

## Critical live boundaries

No order placement, account/funds write, TESTNET/LIVE, no protected H39/H40/H41/Forward/Final/OOS outcome access, no production systemd or F-R2 cutover, no new historical downloads. Historical QC != source rights or receiver PIT, and cost scenarios != verified maker fills.
Do not downgrade from P3_ACCESS_SCOPE_HOLD unless the Owner explicitly signs a valid exact scope and private partitions are resolved in a future task.
