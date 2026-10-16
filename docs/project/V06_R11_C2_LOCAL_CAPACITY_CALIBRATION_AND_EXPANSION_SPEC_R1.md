# R11-C2 — Local capacity calibration and expansion specification R1

**Terminal: `R11_C2_CAPACITY_STOP_UNMEASURED_SOURCE`.**  
**Executor:** Codex, one isolated agent session; no delegation.  
**Task authority:** Owner's in-conversation R11-C2 instruction; no separate immutable R11-C2 Git dispatch or prompt blob was supplied.  
**Result:** Local measurement was not started because no exact R11-C2 isolated workspace and read-authorized existing sample paths were designated. A task-specific path question was issued and remains unresolved. Historical R10-D1 path permissions are not silently extended to this task.

This STOP is an authority/source-witness stop. It does not establish that disks are full, files are absent, rights were denied, or expansion is necessary. No local filesystem, current workspace footprint, source ZIP/CSV/Parquet, protected tree, D1 worktree or private account was inspected for R11-C2. No market payload was downloaded or transformed, no bulk intake was started, no filesystem was resized, and no strategy/scoring/trading operation occurred.

## 1. Verified public input and isolated publication lineage

The public Task C author branch resolved to **`5b9d86209fa71ca2f4732f85b85846434c52af3e`**. Its [storage/schema report](https://github.com/EXASHXE/btc-quant-agent-public/blob/5b9d86209fa71ca2f4732f85b85846434c52af3e/docs/project/V06_DATA_C_VENUE_STORAGE_SCHEMA_AND_CAPACITY_MODEL_R1.md) has exact Git blob **`870c34be446962aeb3b2a7a23591ba75d725b35b`**; the author commit's sole parent is **`ade4df19872122686432cd955d8f139f16069449`**. Public Git metadata and the report were read; their local worktree was not accessed.

Task C explicitly leaves empirical byte/CPU fields NULL but later gives illustrative capacity and feasibility conclusions. Those statements cannot serve as R11-C2 physical measurement. The following numbers are retained only to identify assumptions being challenged:

| Prior number in C | R11-C2 evidentiary label | Treatment |
| --- | --- | --- |
| Approximately 1,024 GiB filesystem, 724 GiB historical free | `UNMEASURED` as current state | No restat; neither current usable capacity nor spendable reserve established |
| 256 GiB safety floor / 468 GiB nominal usable / 408 GiB permanent ceiling | `ESTIMATED`, conditional on historical assumptions | Not measured limits or permission to consume storage |
| 60 GiB staging reserve | `ESTIMATED` illustrative input | Not an observed staging high-water mark |
| 18.2 GiB base Tier A across eight products | `ESTIMATED` illustrative scenario | No measured archive/Parquet sample basis in C; not a safe-fit conclusion |
| 320 GiB base Tier B / 4,500 GiB base Tier C | `ESTIMATED` illustrative scenarios | No calibration adopted; L2 remains separate |

**Publication branch:** `docs/v06-r11-c2-capacity-calibration-r1`.  
**Only added path:** `docs/project/V06_R11_C2_LOCAL_CAPACITY_CALIBRATION_AND_EXPANSION_SPEC_R1.md`.  
**Chosen publication direct parent:** Task C author `5b9d86209fa71ca2f4732f85b85846434c52af3e`, for documentary lineage. This is not represented as a new Controller dispatch. No divergent source branch is merged; no source code, CI, existing report or protected content is changed. The report is prepared and published through remote Git operations; no local output directory is guessed or created.

The exact resulting author commit, report blob, one-file diff, ahead/behind, remote head and actual hosted CI are verified after publication and returned separately. A report cannot embed its own future commit hash or invent a later CI result.

## 2. Required measurement ledger

GiB means **bytes / 1,073,741,824**. NULL means unmeasured, not zero. R11-C2 has no completed local calibration witness.

| Requested measurement | Actual GiB / bytes / ratio | Label | Missing prerequisite |
| --- | --- | --- | --- |
| Filesystem total | NULL GiB | `UNMEASURED` | Exact authorized workspace on the intended filesystem |
| Filesystem used / free / user-available | NULL GiB | `UNMEASURED` | Same; distinguish free blocks, reserved blocks and quotas |
| Mount source/type/device identity | NULL | `UNMEASURED` | Authorized mount lookup for that workspace |
| Current data footprint inside allowed workspace | NULL logical/allocated GiB | `UNMEASURED` | Exact scope; no cross-root traversal |
| Representative compressed archives | NULL bytes | `UNMEASURED` | Read-authorized existing approved samples and their provenance |
| Expanded CSV bytes | NULL bytes | `UNMEASURED` | Bounded local validation/expansion authority |
| Parquet/ZSTD bytes | NULL bytes | `UNMEASURED` | Authorized scratch/output path and transform cap |
| CSV/ZIP, CSV/Parquet and Parquet/ZIP ratios | NULL | `UNMEASURED` | Matched measurements using a recorded lossless schema/codec |
| Bounded transform staging high-water | NULL logical/allocated GiB | `UNMEASURED` | Owned scratch directory; measured phase/monitor protocol |
| Byte-identical duplicate files | NULL files/bytes | `UNMEASURED` | Named scope, local digests and inode accounting |
| Daily/monthly logical overlap | NULL partitions/bytes | `UNMEASURED` | Both forms within a permitted scope; exact UTC coverage/vintages |
| 1y/3y/full-history core demand | NULL GiB | `UNMEASURED` | Calibrated family samples and explicit history/retention definitions |
| Current safe incremental capacity | NULL GiB | `UNMEASURED` | Current available space, floor and workspace-specific quota |
| Exact additional filesystem expansion | NULL GiB | `UNMEASURED` | Current filesystem witness plus calibrated target demand |

**No insufficiency is established.** Therefore an exact additional GiB target, including a claimed zero, would be fabricated. The stop occurs before any intake. No disk resize, deletion, compaction, sample discovery or bulk download is authorized by this report.

## 3. Family coverage and lawful sample boundary

The [published R10-D1 receipt](https://github.com/EXASHXE/btc-quant-agent-public/blob/5630b178bf2f497f67a7e2db2d730f0b2aacabfe/docs/project/V06_R10_D1_CODEX_LOCAL_BINANCE_VISION_DEV_QC_R1.md), blob `7e8f126287e428c739d8c65230eb4366cc8c3256`, is prior public metadata. It reports seven EXPOSED_DEV days of Binance BTCUSDT USD-M trade 1m, mark 1m and metrics. Its reported archive sizes do not supply R11-C2 mount, footprint, Parquet or staging measurements. Their physical persistence and read permission for R11-C2 were not reverified; no D1 workspace or raw file was accessed.

| Venue/product/family | R11-C2 sample availability | Capacity inference allowed now |
| --- | --- | --- |
| Binance BTCUSDT USD-M 1m trade bars | `UNMEASURED`; prior D1 documentary witness only | None pending named sample-path authority |
| Binance BTCUSDT USD-M mark 1m | `UNMEASURED`; prior D1 documentary witness only | None pending named sample-path authority |
| Binance BTCUSDT USD-M metrics/OI 5m | `UNMEASURED`; D1 reports missing fields and timing ambiguity | No data-quality admission; nullable/raw-preserving benchmark would still require authorization |
| Binance Spot BTC/ETH and USD-M ETH core | `UNMEASURED` | No BTC-to-ETH or Spot-to-perp extrapolation |
| Funding, index/premium, trades/aggTrades not explicitly supplied | `UNMEASURED` | Public catalog visibility does not authorize a sample download |
| OKX Spot/swap BTC/ETH | `UNMEASURED` | No Binance-to-OKX extrapolation |
| Historical continuous L2 / forward streams | `UNMEASURED`, separate scenario only | No protected/forward access or continuous collection |

No new source payload or legal entitlement is inferred. Existing Controller-approved sample scope must be identified explicitly; source bytes and derived Parquet remain local. Sample dates must be lawful development slices, never protected H39/H40/H41, Final Holdout, Forward or reserved OOS. No existing private/protected source root is a fallback.

## 4. Bounded measurement protocol to resume

This protocol is a specification, **not a claim of execution**:

1. **Authority and isolation.** Owner names one absolute R11-C2 workspace, its permitted scratch/output directory and exact read-only existing sample paths. Confirm exclusive ownership, clean output namespace, safe write permissions, no symlink/path escape, bounded bytes and no protected descendants. Inspect no alternative locations.
2. **Filesystem witness.** Capture timestamp, mount identity/type, device major/minor, total/free/used/user-available bytes and applicable quota. Identify overlay/thin/shared backing limits separately. A container-visible filesystem is not automatically a resizable physical disk. Publish sanitized identity, not private machine paths.
3. **Footprint witness.** Traverse only the approved scope without following symlinks; report logical file bytes, allocated bytes, file counts and errors separately. Deduplicate hard links by device/inode. Workspace contents are not whole-mount usage; unallocated/sparse/compressed filesystem accounting needs its own label.
4. **Representative samples.** Identify each actually present venue/product/instrument/family and verify original URI, date, publisher digest and local file hash. Use a predeclared small calendar selection, up to three already-approved partitions per group when available, independent of strategy outcomes. A seven-day single-instrument slice is not representative of all venues/years/regimes. No market download or unbounded source discovery.
5. **Lossless transform measurement.** Record CPython/PyArrow/Parquet/ZSTD versions, explicit source-to-column schema, null handling, dictionary settings, row-group size and ZSTD level. Preserve decimal values and timestamps exactly; avoid undocumented float coercion or missing-to-zero conversion. Count actual ZIP/member/CSV/Parquet bytes locally, validate ZIP safety/CRC and round-trip row/schema/value equality with no source rows in tool output.
6. **Staging high-water.** On one capped transform, retain known inputs and intermediates long enough to observe phase barriers after flush/fsync; monitor owned scratch only. Record peak logical and allocated disk bytes, retained baseline, incremental scratch peak, sampling interval and any observational limitation. Do not substitute compressed+expanded+Parquet arithmetic or noisy shared-mount free-space deltas for an observed peak. RAM/RSS is separate from disk staging.
7. **Overlap.** Distinguish byte-identical archives, hard links, same logical UTC coverage and revisions. Daily and monthly ZIP hashes can differ while events overlap; compare schema/event IDs or canonical row digests locally if both are authorized. If only daily samples are available, label daily/monthly overlap `UNMEASURED`. Do not count mark/trade bars as duplicate products just because timestamps match.
8. **Bounded finish.** Report timing, bytes, checksums, read/transform failures and reproducible commands using workspace-relative outputs. Keep all source/Parquet files outside Git and LLM context. Stop on cap, quota, safety-floor, integrity, schema or rights failure; preserve owner data. Publish exactly this report path, with no repository source-code changes.

## 5. Projection methodology and uncertainty

Only matched measurements may supply daily rates. For group `g=(venue,product,instrument,family)`, define `a_g=archive bytes/day`, `p_g=Parquet bytes/day`, with both rates measured on explicitly named samples. Report min/max and sample counts; no unsupported P50/P90. Ratios are `CSV/ZIP`, `CSV/Parquet` and `Parquet/ZIP`, with numerator and denominator explicit.

For a declared retention policy, estimated incremental retained bytes are:

`S_g(D) = D × (retain_archive × a_g + retain_parquet × p_g) + justified_metadata_g`.

- **1y:** D=365 days; **3y:** D=1,095 days for a transparent fixed-day scenario, with leap/calendar corrections disclosed separately.
- **Full history:** specify exact inclusive start/end dates per group and actually verified coverage; do not silently call five years “full history.”
- Sum only compatible groups with measured inputs. Keep unsupported groups NULL. Do not scale one BTC week into all eight products.
- Existing retained copies already counted in baseline usage are not an extra incremental archive requirement. Deduplicate daily/monthly logical coverage and preserve revision lineage.
- Expanded CSV is transient unless retention is explicitly chosen. Add observed staging reserve separately from permanent archive+Parquet; avoid retaining both monthly and daily representations without a reason.
- Forecast 12-month growth separately from historical demand. Historical 172.33/79.6/92 GiB figures may overlap and are not additive current measurements.
- Content/activity, schema, timestamp precision, missing columns, row-group/dictionary choices, filesystem compression and concurrent workers all affect size. Nine tiny samples, if later approved, do not determine a multi-year tail distribution.

All numeric projections from this methodology remain **`ESTIMATED`**, even when their inputs are **`MEASURED`**. No new group projection is calculated here without those inputs.

## 6. L2 scenario kept separate from core

L2 retained demand depends on independent event/snapshot rates, depth, encoding, compression, replay/recovery retention and instrument count. Use `S_L2 = events_per_second × retained_bytes_per_event × seconds × instruments + separately_budgeted_snapshots/indexes`; do not borrow 1m/OI ratios.

An arithmetic sensitivity example, **`ESTIMATED / SYNTHETIC_ASSUMPTIONS_ONLY`**: at 100 updates/second and 1,024 retained bytes/update, with snapshot/index overhead excluded, one instrument-year is **3007.51 GiB** and eight instrument-years **24060.06 GiB**. Neither rate nor byte size is observed, neither is a provider commitment, and no capacity-fit/failure conclusion follows for the unknown local filesystem. This separate scenario replaces no empirical L2 evidence and authorizes no L2 intake.

## 7. Expansion rule and exact-target dependency

After measurement, let all inputs be GiB:

- T = current filesystem total; F = current conservative user-available capacity.
- U = T − F, treating reserved/unavailable space conservatively; reconcile quota/backing-store limits.
- D = **additional**, deduplicated planned retained data + observed peak scratch reserve + justified metadata + chosen growth, excluding bytes already in U.
- Preserve free-space floor `max(100, 0.25 × target_filesystem_total)`, as in the data-program plan.

Under the explicit assumption that existing unavailable usage remains U and added filesystem capacity becomes available one-for-one:

`required_total_GiB = max(U + D + 100, (U + D)/0.75)`.

`additional_GiB_target = ceil(max(0, required_total_GiB − T))`.

The 25% floor applies to the **expanded** filesystem, so merely subtracting the old floor understates the target in some cases. Reserved-block/quota/backing-store changes require adjustment and fresh verification. If the calculated bounded intake breaches the current floor, stop before intake and return the numeric target and assumptions. Do not resize disks.

**Current recommendation:** defer a filesystem expansion decision and all bulk intake until T/F/U/D have witnesses. **Exact additional target is `UNMEASURED`**, not a guessed 1/2/4-TiB purchase recommendation.

## 8. Actual validation, CI and finite resume requirements

**Actual actions:** read public Git metadata and Task C's published report; verify its commit, sole parent and blob; prepare this stop/specification report; verify report content, sole parent, one-file ADD-only diff and remote branch on publication. No filesystem command, local inventory, sample transform, source-QC/synthetic test, benchmark, strategy trial, data download or disk action was run for R11-C2. Spend USD 0.

Proportional report validation covers frozen public-input identity, absence of private absolute paths, required MEASURED/ESTIMATED/UNMEASURED distinctions, no invented numeric results, and publication allowlist. No repository source or CI change is needed. Actual hosted CI is observed for the new report commit and returned in the final receipt; no test or green status is fabricated. Existing CI failures are reported without task-external repair.

**Finite resume input:** one exact owner-selected workspace, exact existing approved sample paths and read permission, an explicitly authorized bounded transform/scratch output location and cap, and the desired per-group full-history/retention scope. If the owner intends to reuse D1's existing samples, that extension must be explicit; no D1 raw path is guessed or accessed in this stop. A later authorized execution can update this same single report with actual witnesses; this report starts no background collector or successor task.

**Preserved gates:** `R9_L1_PAUSE_NEW_ALPHA_RESEARCH_PENDING_EXTERNAL_SOURCE_EVIDENCE / SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE`.
