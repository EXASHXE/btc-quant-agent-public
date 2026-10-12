# v0.6 B-line Controller L2 — Gemini R3 + Codex R3, Fast-CI and controlled simplification

Review date 2026-10-13 Asia/Shanghai. ChatGPT-0 B-line Primary Controller. Repository EXASHXE/btc-quant-agent-public.

## Identity and verified status

**Gemini R3** branch feature/v06-bline-gemini-r3-portable-ci-funding-pit-source-qualification at exact remote SHA 97f4040b9380f2069575a989c066d1daeef15194, seven commits from 632d2e37f28b8c3efbd2b818ecdb74783f0df238. [Final GitHub Actions run 38270967488](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38270967488) true FULL pytest execution: **3454 passed, 2 skipped, 9 warnings in 904.17 seconds**; Ruff and compile steps succeed. Executor independently reports locally 394 scoped feed/bridge tests pass; 394 is a distinct subset, not the complete 3454 suite.

[Public market diagnostic](https://github.com/EXASHXE/btc-quant-agent-public/blob/97f4040b9380f2069575a989c066d1daeef15194/evidence/v0.6/b_line/market_event_bridge_r3/PUBLIC_SOURCE_CHANNEL_QUALITY.json) reports 180 sec public Binance data via explicit locally configured Clash route: 4730 messages, 1733 depth diff, 2405 aggTrade, 178 Mark ticks spanning 177 sec, three closed 1m Last bars, two REST depth snapshots, one rebootstrap. It also says book_continuous=false. Accordingly *public multi-channel short forward input observed* but **L2 continuous-window NOT accepted**. No 24h feed proof, fill-capacity proof or Alpha.

**Codex R3 independent review** branch feature/v06-bline-codex-r3-independent-causal-audit-r1 at exact remote SHA a64a33caf3323447daa09b4e15214894007b8dfe. [Codex review](https://github.com/EXASHXE/btc-quant-agent-public/blob/a64a33caf3323447daa09b4e15214894007b8dfe/docs/audits/r3_codex_causal_audit_r1/FOCUSED_DATA_ACCOUNTING_REVIEW.md) claims 20 local deterministic probes, 13 bug reproductions and 7 correct invariants at **original frozen R2** SHA 632d2e37f28b8c3efbd2b818ecdb74783f0df238, not newer R3. [Codex GitHub Actions 38276598851](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38276598851) failed Ruff on two I001 import ordering issues; pytest skipped. No independent final Codex CI PASS.

## New source-level concerns after Gemini R3 (do not infer that 13 original R2 findings persist)

1. **Late Funding mark settlement witness**: scripts/integration/market_event_bridge_r2/funding_adapter.py near line 244 passes reference_time_ms=observed_wall_utc_ms (funding record's receipt), NOT the independently verified historical funding settlement price at funding_time_ms. Being fresh upon receipt does not certify historical settlement cash basis, especially delayed REST records. Requires new R3-specific deterministic proofs.
2. **Duplicate settlement normalization**: same funding_adapter.py near line 228 builds settlement identity from raw rate_str. Numerically equivalent strings e.g. 0.0001 and 0.00010000 can produce two entries; independently reproduced on R2, needs repeat against R3.
3. **Untrusted scalar Mark path**: same file near lines 253–269 converts a bare float/Decimal to source_sha=manual_scalar_witness and quality VERIFIED, potentially permitting incomplete provenance in direct consumer calls; must reject or keep explicitly nonauthoritative.
4. **Nonfinite numerical input**: ensure rate and Mark are is_finite() before journal entry or serialization.
5. **Source qualification**: R3 correctly distinguishes PUBLIC_MULTI_CHANNEL_SOURCE_VERIFIED from stronger L2_CONTINUOUS_WINDOW_VERIFIED; actual public witness has book_continuous=false and one rebootstrap. Do not promote to sustained L2 or market-liquidity confidence.
6. **Receipt lineage**: final branch HEAD 97f4040b, some executor evidence cites docs-stage code 4881b789. Actual full CI at 97f4040b passed; receipt must not misattribute exact identity.

**L2 decision:** R3 engineering CI and short multi-channel source bounded ACCEPT; financial settlement-price provenance and L2 continuity remain BLOCKED, G2 validated Alpha NO-GO, G3 true external LLM/Feishu not accepted, G4 TESTNET/LIVE/real funds NO GRANT. Frozen B/C/G1 policy source untouched.

## Root cause of ~15 minute CI

The true planner scripts/ci/test_plan.py line 191–193 sets full=True for unmapped executable paths. Explicit maps for new scripts/integration/market_event_bridge_r2 and scripts/market_data/forward_public_feed_r1 are missing. GH run 38270967488 used PROFILE full, 3454 pytest cases in 904.17s; measured bridge/source suite reported 394 tests in 15.28 sec locally. Raw test runtime ratio is ~59x, not an assured ratio for overall CI time. CI workflow already schedules full weekly/manual and cancels superseded in-flight jobs. This is a test ownership mapping problem, NOT evidence that H40/H41 scientific tests should be removed.

**NORMAL Gemini task**: minimal fail-closed planner ownership mapping and explicit dependency suites; retain unknown-change full, tests deleted/renamed full, CI-only plan tests and weekly/manual full. First fast CI focused plus one final exact-SHA full gate. Never just add blanket scripts/** exemptions.

**BOOST Gemini task**: full architecture and test inventory, proof-preserving low-risk A + R2/R3 local-only consolidation, performance profiling, fixture deduplication based on independent invariants; no deletion/relaxation of scientific H40/H41/holdout, PIT, G1/C, operator, portfolio or testnet guards. Benchmark focused and full once at final candidate. Separately record any science behavior change as NEEDS_SEPARATE_AUTHORITY, not implicit acceptance. Avoid merging either branch before exact-SHA Controller review.

A-line, performance and protected legacy/holdout data untouched. Two independent worktrees from Gemini R3 SHA, non-overlapping scope, no force-push.
