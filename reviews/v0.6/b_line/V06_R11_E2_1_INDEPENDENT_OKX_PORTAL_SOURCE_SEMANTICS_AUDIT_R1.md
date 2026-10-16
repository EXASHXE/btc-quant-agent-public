# V06 R11-E2 — ChatGPT-1 Independent OKX Portal Source-Semantics Audit R1

**Review target:** EXACTLY ONE consequential claim: whether the author-delivered OKX historical-portal pilot establishes sufficiently verified source/rights/native-clock/contract integrity to support the next R11-Q3 source admission.  
**Independent reviewer:** ChatGPT-1 Supervisory Auditor (separate from E2 author and Controller).  
**Terminal:** `BLOCK_PENDING_EVIDENCE` **for R11-Q3 scientific/causal source admission and blanket E2 integrity acceptance**.  
**Retained limited positive:** `PERSONAL_OFFLINE_PORTAL_RESEARCH_RIGHTS_SUPPORTED`; the bounded offline DEV pilot may be retained under its actual license and original frozen limits. No reversal of the Controller's narrower R11-Q2 permission.

## Frozen authority and identity

- Main integration snapshot inspected: `v0.6.5@275bb5fc71fa21944375d8118945a6074030353e` (moving main; only an observed starting SHA).
- Author E2 commit: `7f8c6acadead47dccdeba80b2ae27c2497ee8cdf`; direct parent and dispatch-authority commit `c07c60385479f0d595352ad751c1c49150b4cbbc`. Parent-to-author compare: **ahead 1 / behind 0; exactly 3 added paths**, no existing path altered.
- Author report: `docs/project/V06_R11_E2_OKX_HISTORICAL_PORTAL_ONE_FILE_PILOT_R1.md`, blob `6a6b172ea734d8c62f0c581faaca0d4e86dc48c1`.
- Author QC implementation: `scripts/research/r11_e2/okx_portal_pilot_qc.py`, blob `d82a81a8546ad0b3b549b427260153c39370fc0c`.
- Author unit tests: `tests/research/r11_e2/test_okx_portal_pilot_qc.py`, blob `5706ff4af38231b9b825f7b444807b0adb7d0e2f`.
- Original Controller task prompt: `prompts/v0.6/b_line/data_program/V06_R11_E2_OKX_HISTORICAL_PORTAL_ONE_FILE_PILOT_R1.md`, at `c07c6038...`, blob `b5e7509db49046cfb76b14baf6d73859b1207e7f`.
- Exact author commit: https://github.com/EXASHXE/btc-quant-agent-public/commit/7f8c6acadead47dccdeba80b2ae27c2497ee8cdf
- Controller Q2 authority: https://github.com/EXASHXE/btc-quant-agent-public/blob/c07c60385479f0d595352ad751c1c49150b4cbbc/reviews/v0.6/b_line/V06_R11_Q2_CONTROLLER_CAPACITY_EXPANSION_AND_NEXT_STAGE_DECISION_R1.md

## Independently established positive: narrow channel rights

The official historical-data page identifies trades, candles, funding and L2 as available portal families (not an historical-OI family): https://www.okx.com/historical-data . The dedicated **OKX Historical Data Terms**, published 2023-10-26, §2 explicitly license **personal** possession/retention/use of portal historical data for the user's own strategy development, non-exclusive and revocable; commercial redistribution/sublicensing is outside the grant, and revocation/expiry requires deletion of held copies: https://www.okx.com/en-sg/help/historicaldata-terms-and-conditions . This is **not** a license for the generic market API, redistribution, permanent unconditional retention, LIVE orders or historical first-known causality. A pilot report's assertion of no private/market calls is author-attested; it was not independently reproduced.

## Findings, ranked by consequence

**F1 — HIGH — Unresolved native completed-candle semantics (decision-driving).**  
E2 §4.2 states `confirm='0'` on all 1,440 historical bars and interprets this as completed historical snapshot records. OKX's official v5 candlestick documentation explicitly defines `confirm=0` as **uncompleted** and `1` as **completed**: https://tr.okx.com/docs-v5/en/ (Market Data → Candlesticks history, `confirm`). The portal **might** encode the exported field differently; its file-specific semantics are not established by the author. The exact QC source reads that field into `_conf` and does not validate or report it. This is a source-contract conflict; do not automatically reinterpret archived zeros as completed or discard all bars without a portal-specific clarification. **Minimum evidence:** official portal CSV `confirm` specification or bounded independently checked publisher clarification, plus an explicit acceptance/rejection policy and negative test for unknown/uncompleted values.

**F2 — HIGH — The executable QC does not enforce the asserted one-day continuity/contract identity.**  
`qc_candlesticks_rows` checks successive timestamp deltas of 60,000 ms, but returns `missing_bars=1440-row_count` **without requiring zero**, does not assert the exact day start/end, and ignores `confirm`. Its own purported successful test feeds only **two** candles, proving a short series is a valid input to this QC function; consequently a partial 2/1439-bar day is not a fatal source error. The code additionally hard-codes `0.01 BTC/contract` as the acceptance constant; agreement with `vol_ccy/vol` is valuable sample arithmetic but not independent proof of the 2024-01-15 instrument contract specification. OKX v5 documents `ctVal`, `ctMult`, `ctValCcy`, `ctType` as the native derivatives contract fields: https://tr.okx.com/docs-v5/en/ (Public Data → Get instruments). **Minimum evidence:** exact partition-boundary and row-count rejection tests; native historical contract-spec identity (or a clearly limited reconstructed specification), and a negative test of mismatched volume units.

**F3 — MEDIUM — L2 integrity/market-execution meaning is substantially narrower than reported.**  
The implementation reads **only the first 2 MiB compressed bytes**, decompresses an initial slice, checks one 400×400 snapshot and at most the first 49 update lines. It does **not** hash or decompress/validate the complete ~495 MB compressed daily object, verify end-to-end sequence continuity/recovery, or establish maker queue, order ACK, fills, fees, funding cost or receiver-first-known timestamps. The L2 sample is suitable for schema reconnaissance only. **Minimum evidence for a full-day L2 quality claim:** independently reproducible whole-object checksum, full replay with monotonic and gap/recovery negative cases. Those are **not prerequisites** to retaining a deliberately slice-only offline DEV exploratory result.

## Tests, evidence provenance and CI

- **Author-reported local**: `pytest: 9 passed`, `unittest: 9 passed`, Ruff passed; pilot counts, SHA-256 values and network assertions are **author-reported**. The first two test runners cover the same 9 authored fixture tests, not 18 independent tests.
- **Independent review this turn**: exact GitHub author commit/parent/three blobs, code control flow, negative-case gap and frozen Controller authorization inspected; official OKX terms, historical family list and v5 contract/candle semantics cross-checked. A minimal negative case is deducible from source: the existing two-row positive test passes despite `missing_bars=1438`, and `_conf` has no reject condition. No protected data or actual third-party market/archive endpoints requested.
- **Independently executed author unit suite:** `NOT_RUN` — network-isolated review environment could not fetch original frozen source into a runnable workspace. Do not claim local test reproduction.
- **Hosted GitHub CI:** `NO_WORKFLOW_RUNS_OR_COMBINED_STATUSES_FOUND_FOR_EXACT_AUTHOR_SHA` through the connected GitHub checks; this is **not** equivalent to CI PASS or proof that no other checks exist.
- **Raw historical ZIP/L2 bytes:** `NOT_INSPECTED`; original local author-provided archive checksums and counts were not independently rehashed.

## Single supervisory decision

**`BLOCK_PENDING_EVIDENCE`** for accepting E2 as a scientifically/PIT-admitted source or a fully proven one-day integrity/contract baseline. Retain author E2 as an **unaccepted but useful bounded offline DEV report** and retain the narrow portal personal-use terms; no general source/PIT, cost, fill, Alpha or release promotion. **Fastest decision-changing evidence:** resolve the portal `confirm=0` contract, assert and negative-test exact 1,440-minute day/UTC+8 boundary, and bind contract-size fields for the historical instrument. Do not require a full L2 download or unrelated CI merely to close the offline pilot. R11-Q3 belongs to Controller 0 after independent evidence.

**Unchanged:** `SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE`.

**Review isolation:** this review adds one report only, does not edit E2 author artifacts or the main branch, merge anything, dispatch successors, touch protected/holdout data, call exchange market endpoints, or trade.
