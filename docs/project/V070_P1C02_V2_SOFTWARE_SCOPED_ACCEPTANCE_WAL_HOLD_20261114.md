# Quant v0.7.0 — P1C02 Custody v2 L0 Software Acceptance with SQLite WAL Hold

**Date:** 2026-11-14. **Reviewer:** Controller 0-C. **Local decision:** `controller-decisions/V070_P1C02_V2_L0_SOFTWARE_SCOPED_CONTROLLER_REVIEW_20261114.json`.

## Verdict

**`ACCEPT_P1C02_SYNTHETIC_L0_SOFTWARE_SCOPED_WITH_WAL_HOLD`**: F01/F02/F03 synthetic software contract, versioned `CustodyV2Store` T0/PREPARE, T1/PENDING, T2/COMMITTED and final evidence/DB ACK behavior are accepted within a disposable offline L0 engineering scope. **This does NOT constitute production-grade SQLite WAL/multi-process durability qualification, Source qualification or public-live acceptance.** Runtime `SQLITE_WAL_ENGINE_NOT_QUALIFIED` remains a named blocker. The previous status file's `controller_acceptance=PENDING` is an accurate *worker* receipt; this new Controller review is the scoped decision. No worker self-acceptance was used.

## Grounded evidence

- Sol source: `lt-p1c02-sol-controller-fix01/`.
- `win_capture/p1c02_custody_v2.py`: SHA-256 `91362abb0d6d7d49ce2800ba944b142205a6d0e109e6574121587d82c187a5ab`; `win_capture/p1c02_custody_pins.py`: `74630b053e8a2635399a416cf10132038d634f504cd1e4d18aaa61319757d84a`. Compatibility `p1c02_source_state.py`: `6216ffdd4d90a4ac7946113f58965b3b9fdc6d91b82800414ca5fed70460635f`.
- Author actual native Windows Python 3.14 logs: **222/222 pass, 0 skip**, fixed local C: NTFS; actual Windows process was not independently rerun by Controller. Author WSL log: **220 pass, 2 Windows-only skipped**; synthetic E2E both platforms exit 0.
- Controller **independently executed entire WSL suite**: **220 PASS / 2 SKIP / 58 subtests passed**, 33.03s, exit 0. Controller also independently replayed v2 normal commit, diagnostic-only unverified restart, fully verified restart, raw-return, post-ACK out-of-band raw tamper and cold recovery; raw tamper was rejected, and recovery quarantined with no replay.
- Q0A5 historical frozen source files **287/287**, P1-A **308/308**, P1C01 inherited source **162/162** SHA256 match (Controller independently checked).
- Hydrogen A/B/C/D independent matrix all **27 methods PASS** according to worker native/WSL receipts, with Sol F01/F03+F02 tests and the newly added 17 v2 custody tests.
- New disposable v2 SQLite schema, distinct from v1. Legacy v1 has no silent migration or trust promotion. Synthetic-only authority flags all disabled.

## What is not accepted / known limitations

1. **`SQLITE_WAL_ENGINE_NOT_QUALIFIED`:** Windows native loaded SQLite 3.50.4 (`engine_win.json`), WSL loaded SQLite 3.45.1 (`engine_wsl.json`); no verified patched source provenance or fixed portable runtime. [SQLite WAL-reset bug](https://sqlite.org/wal.html#the_wal_reset_bug): affecting affected upstream binaries through 3.51.2, fixed in 3.51.3+ with backports 3.44.6/3.50.7. Binary version alone cannot establish an independent downstream backport. Do not claim qualified production multi-process durability.
2. **Native custody scope:** ordinary unprivileged conflicting writes/unlink/rename were rejected under held NTFS pins in worker tests, not privileged/volume writers, arbitrary native rename/mapping variants or a separately provisioned protected custodian service. WSL POSIX locks are advisory and sampled verification may miss hostile ABA between checks.
3. No instrumented internal SQLite VFS commit cuts or physical power-loss tests; no external independently anchored restore floor. An internally coherent old DB+files image is not independently time-authoritative.
4. v2 deliberately rejects epoch changes without an enrolled transition policy. Recovered synthetic clock and persisted booleans do not prove UTC.
5. No actual Binance/Feishu calls or live market Source qualification, no Alpha or trading authority.

## Progress and next-stage boundaries

The F01/F03 repair and F02 T0/T1/T2 software contract now provide a **closed L0 software implementation milestone**. Retain Sol's original reports, raw logs and `STATUS_SOL_P1C02_CUSTODY_V2.json` without rewriting historical evidence.

- **Separate `V070-SOL-P1C02-SQLITE-RUNTIME-QUALIFICATION-01`**: verify exact loaded SQLite source/patch for Windows and WSL; safely stage a fixed portable runtime without overwriting system Python; rerun same v2 crash/concurrency and WAL backup/checkpoint matrix; do not claim native NTFS/host authority solely because SQLite tests pass. If runtime unavailable, persist `WAL_ENGINE_UNQUALIFIED`.
- **P1C03 is permitted to start separately within synthetic disposable L0 only**: detached raw-retention index, expiry/tombstone and <=24h allowlisted purge simulation. No accepted evidence deletion; explicit UTC limitations; expired raw cannot be replayed even when bar fingerprints survive. The P1C02 WAL hold does not authorize production operation of the retention worker.
- **P1C04 remains later and separately gated**: disabled TLS/loopback mock Source→E1→Shadow. The current decision does NOT start P1C04 or allow real Binance/Feishu.
- Actual read-only L1 requires new scoped Owner envelope and independent UTC/rights/source admission, plus unresolved durability issues. Feishu real human notification is separately authorized.

**Authority flags remain:** `SOURCE_BLOCKED=true; SOURCE_QUALIFIED=false; SHADOW_QUALIFIED=false; ECONOMICALLY_VALIDATED=false; ALPHA_CLAIMED=false; execution_authority=false; REAL_FEISHU_SEND=false`.

**Dispatch status:** prompt-only; no agent or real API operation was started by Controller during this review.
