# R11-C2 — Local Capacity Calibration and Expansion Specification

**Executor:** local Codex High, one isolated session.  
**State:** READY / BOUNDED.  
**Purpose:** replace C's illustrative storage numbers with measured evidence. This is a data-engineering capacity task, not Alpha research.

## Execute

On one owner-authorized isolated workspace, measure:

1. filesystem total/free/used and mount identity;
2. current data footprint only inside the explicitly authorized workspace;
3. representative compressed archive size, expanded size and Parquet/ZSTD size for each actually available family;
4. staging peak during one bounded transform;
5. duplicate/daily-vs-monthly overlap where applicable;
6. extrapolated 1y/3y/full-history storage by venue/product/family;
7. separate L2 scenario from core 1m/5m/funding/OI data.

Use only small, lawful public samples already authorized by the Controller. Do not scan H39/H40/H41, Final Holdout, Forward, owner-protected roots, Quant-agent/data or Quant-agent-sanitized. Do not download a multi-year dataset.

## Required output

Report actual GiB values, sample byte counts, compression ratios, staging high-water mark, methodology, assumptions, uncertainty and recommended filesystem expansion. Use `MEASURED`, `ESTIMATED`, `UNMEASURED` labels. Do not call an extrapolation measured.

If current space is insufficient, STOP before any bulk intake and give the exact additional GiB target. Do not resize disks yourself.

Publish exactly one report, exact commit/blob/parent/diff/CI. No source code changes, no protected access, no strategy scoring, no trading.

Terminal: `R11_C2_CAPACITY_MEASURED_WITH_LIMITS` or `R11_C2_CAPACITY_STOP_UNMEASURED_SOURCE`.