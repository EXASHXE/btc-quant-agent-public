# Research Data Concurrency & Resource Isolation Policy (v0.3.20)

## 1. Objective & Threat Model

Forward PIT collection operates in real-time under tight SLA bounds:
- 15m derivatives snapshot must be collected within 60 seconds of boundary close.
- 15m opportunity shadow scan must complete within 60 seconds of decision boundary.
- Microstructure feed processes hundreds of depth and trade events per second and writes to SQLite continuously.

**Threat**: Running heavy ad-hoc research jobs (historical data downloads, multi-year ZIP uncompressions, backtest sweeps, resampling audits) can consume 100% of available CPU cores and disk I/O, starving real-time collectors and causing SQLite write lock timeouts (`database is locked`).

---

## 2. Process Scheduling & Nice Prioritization

### Rules:
1. **Real-time Forward Services**: All forward daemons and timers run at default or elevated scheduling priority.
2. **Heavy Research / Dataset Builds**:
   - Long-running batch commands (e.g. `quantctl build-official-dataset`, `quantctl audit-official-timeframes`) must lower their execution priority using `os.nice(10)` or `nice -n 10`.
   - On Linux systems supporting `ionice`, research downloads should run under the idle I/O scheduling class:
     ```bash
     ionice -c 3 quantctl build-official-dataset ...
     ```

---

## 3. Database Access & Concurrency Segregation

1. **Forward Databases are Write-Exclusive to Collectors**:
   - `data/forward/BTCUSDT/derivatives.sqlite3`
   - `data/forward/BTCUSDT/opportunity_shadow.sqlite3`
   - `data/forward/BTCUSDT/microstructure/microstructure-*.sqlite3`
   Ad-hoc analysis or backtests must NEVER execute long-running analytical queries directly against active write partitions without read-only mode (`sqlite3 ... mode=ro` or copying to temporary workspace).
2. **Microstructure Status Caching**:
   - `MicrostructureStore.status()` caches finalized and immutable partition metadata in `.partition_stats_cache.json`.
   - Status checks must not execute full `PRAGMA integrity_check` on multi-gigabyte databases; use cached metadata and `PRAGMA quick_check`.

---

## 4. Disk Space Budgeting & Garbage Collection

- **Alerting Threshold**: Forward storage directory must maintain at least 15 GB of free NVMe SSD space.
- If disk space falls below 10 GB, `quantctl forward-evidence doctor` flags storage status as degraded.
- Archive raw ZIP downloads under `data/research/BTCUSDT/raw/` only as necessary; avoid duplicate unpacked CSV directories.
