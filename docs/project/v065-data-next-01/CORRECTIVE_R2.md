# V065-DATA-FINAL-CORRECTIVE-R2

**ENGINEERING_CORRECTED_PENDING_INDEPENDENT_REVIEW** — one bounded engineering correction, no source/scientific admission.

**Direct parent:** `80bd531c4a70560c800a12326c3fdfb1f2d6a59d`, itself parented to main `275bb5fc71fa21944375d8118945a6074030353e`. Separate local branch `engineering/v065-data-final-corrective-r2`, worktree `/tmp/v065-data-final-corrective-r2`. Original `/tmp/v065-data-next-01` remains clean at its original commit; no reset, push or merge.

**Independent input:** `/root/workspace/project-review-output/v065-data-next-01-1/INDEPENDENT_REVIEW.md`, verified SHA-256 `19f80d1ae69eaab0704415427513ac60a39018fc44e4c2c1e45b63a86bf13b6a`. Read its F1–F4 findings, author report, affected code/tests and T2 operating guardrails. This author does not independently accept its own repair.

## Corrections

**F1 — Trades/AggTrades:** canonical daily period required; every parsed observation must satisfy **UTC `[declared-day 00:00, next-day 00:00)`**; header-only/no-valid-observation input fails. Invalid rows fail even beside a valid observation. Trade ZIP filenames are bound to declared family/symbol/period under the existing official source scope, in addition to member identity and checksum checks. Aggregate raw-trade ID bounds must be nonnegative and ordered; native schemas, strictly increasing trade/aggregate IDs and distinct aggregate-ID versus raw-ID-range semantics remain intact.

Positive tests preserve same-millisecond timestamps, nonuniform arrival and a single sparse in-day observation. **No one-trade-per-minute grid or whole-day completeness is inferred.** For these event families `expected_rows=0` means no fixed row-count model; successful QC still requires positive valid observations. A zero `missing_intervals` does not certify every execution was captured.

**F2 — v2 successful-status consistency:** required errors/missing/invalid diagnostics must have their proper list/dictionary types. PASS requires empty errors/maps and positive total rows with all rows valid. PARTIAL_PASS is supported only for Metrics and requires known numeric metric-field names, strictly positive integer missing counts (booleans/floats/strings/NaN/Inf rejected), each no greater than total rows. With `incomplete=total_rows-valid_rows`, require `max(missing counts) <= incomplete <= sum(missing counts)`; multiple missing cells in one row are allowed. No invalid fields or malformed/grid errors may hide behind either successful status. Nontrade duplicate timestamps contradict successful status; legitimate same-millisecond Trades/AggTrades remain allowed.

The earlier 17-test module's fake QC records now include row accounting and its PARTIAL positive targets a Metrics record. The **10 frozen original tests are byte-for-byte unchanged**. New R2 tests also exercise the actual synthetic ZIP/checksum path and mocked writer receipts; mocked acquisition mode performs no network/acquisition.

**F3 — retained bounded semantics:** 00/08/16 UTC settlements and nonnegative **0..5000 ms** slot tolerance are the frozen **January 2024 BTCUSDT/ETHUSDT USD-M D2 calendar model**. Other-month synthetic controls test calendar arithmetic only. No universal 8h exchange/era/instrument/OKX/live rule, prior announcement clock or matching-engine proof is claimed.

## Explicit manifest-v2 consumer contract

This patch validates the internally generated v2 records; it does not introduce a general external-manifest reader or compatibility framework. Consumers must dispatch on an **explicit integer `manifest_version=2`** before using these meanings. Missing/unknown versions need rejection or an independently specified legacy path; a v1-only reader must refuse v2 until adapted and tested. Do not infer admission from a terminal suffix or console summary. Normal QC records include additional schema, row, timestamp, coverage and provenance fields; validate any fields required by the consumer's claim.

| v2 field(s) | Exact interpretation / conservative use |
|---|---|
| `manifest_version` | Integer **2**; changes interpretation, not merely formatting. |
| `task`, `terminal`, `safety_code`, `gates` | Task identity, engineering terminal/error and unchanged NO_GO labels. An engineering accepted-with-limits terminal is not L1/L2/science authority. |
| `records[]` | Attempted archive records, with exact family/symbol/period/cadence/reuse-class/URI identity; unique and equal to the frozen plan for a complete receipt. Missing/checksum-failed/unfinished records are not successful QC. |
| `records[].qc`, `errors`, `missing_field_counts`, `invalid_field_counts` | Mandatory coherent diagnostics for PASS/PARTIAL as above. No absent/null/empty-reason PARTIAL acceptance. Missing/invalid dictionary entries are nonzero findings, never zero placeholders or imputations. |
| `records[].total_rows`, `valid_rows` | Mandatory positive integer total for successful status; integer `0 <= valid <= total`; PASS has equality, PARTIAL has justified incompleteness. |
| Row/grid/duplicate counters | When present, malformed/missing/unexpected interval counters must be integer zero for successful status; so must nontrade duplicate timestamps. Trade timestamp duplicates are descriptive, not automatic failure. |
| `publisher_checksum`, `sha256` on successful records | Verified checksum status and lowercase 64-hex ZIP digest. They establish current-byte integrity only, not original publication/receiver PIT. |
| `inventory.expected_objects` | **215** for the unchanged full frozen plan: **21 reused-class + 194 calibration/sample-class**. Monthly/daily and raw/aggregated economic overlap is not independent evidence. |
| `inventory.attempted_objects` / `total_objects_attempted` | Number of records actually attempted/entered, including missing or unfinished records. |
| `inventory.evaluated_objects` / `total_objects_evaluated` | Records carrying completed `PASS`, `PARTIAL_PASS` or `FAIL` QC classification; includes evaluated failures. Not evidence that every object passed; MISSING/unfinished are excluded. |
| `inventory.reused_objects` / `reused_objects_from_r10_d1` | Reused-source **plan classification among attempted records**, not proof of actual local possession or no new I/O. |
| `inventory.calibration_sample_objects` / `calibration_sample_objects` | Non-reused plan classification among attempted records, not new-download count. |
| `newly_acquired_objects` | Successful archive fetch metadata with **nonzero attempts** during that run, whether or not later QC passes; checksum requests are not extra archives. Offline verify is **0** even when **215** objects are evaluated. Mocked writer test separately proves **1 newly acquired != 215 evaluated**. Never alias this field to evaluated, attempted or calibration objects. |
| `inventory.errors` | Any coverage, duplicate, integrity, incomplete or contradictory-QC finding forces STOP. Empty errors do not independently validate physical source bytes. |
| `request_attempts`, disk/byte/cap fields, parity results | Run bookkeeping, budget and parsed daily/monthly row comparison. Not a unique physical-storage inventory, original-data receipt or independent historical availability witness. |

No external/downstream consumer compatibility is certified here. Any integration must pin producer/schema SHA, enforce version dispatch and retain per-record diagnostics and exposure labels; a console `total_objects` summary is not a substitute for the versioned receipt. Existing acquisition/evaluated count assignments were not modified.

## Validation and unchanged evidence

Executed only the changed-invariant suite and frozen D2 module:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 -B -m unittest -v tests.research.r11_d2.test_data_final_corrective_r2 tests.research.r11_d2.test_data_next_01 tests.research.r11_d2.test_binance_core_pilot
```

**41 PASS = 14 R2 + 17 prior D-NEXT + 10 frozen D2**. Selected four R2 methods against the exact parent source produced **27 expected negative failures, zero errors**; regression evidence is synthetic only. Scoped Ruff on the script and two changed test modules, plus scoped Git diff/whitespace checks: PASS. No broad suite, CI, original archive or acquisition was run. Test counters with mocked fetches do not assert actual downloaded objects.

AST comparison with the parent confirms unchanged `pilot_tasks`, source URLs/allowlist, native schemas, term blob `87d04e216f62c86a2c797fbb7637404d6d602687`, terms guard, acquisition-count writer and all gates. The original report and 33-row matrix are unchanged. The full 215-object plan remains 21+194, not the author's erroneous 222 family subtotal.

**Unresolved bytes:** author family expanded subtotal **338,479,481 B** versus claimed total **323,945,031 B** leaves **14,534,450 B** unresolved. This remains reported arithmetic, not a measured or corrected physical-byte total. No new manifest/hash of source archives was invented. Rights/version applicability, actual physical L1 admission, original historical receiver-known PIT L2, costs and account utility remain unaccepted.

Changed paths: script; updated prior test fixtures; new `test_data_final_corrective_r2.py`; this report. The exact new author SHA and four changed-path Git blobs are returned externally after commit, avoiding a self-referential report hash.

**STOP at engineering delivery pending ChatGPT-1 / Controller 0 review.** Preserve `SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE`. No protected H39/H40/H41/Forward/Final/OOS, accounts, funds, original-market data, collector, live API, push, self-merge, CI modification or scientific promotion.
