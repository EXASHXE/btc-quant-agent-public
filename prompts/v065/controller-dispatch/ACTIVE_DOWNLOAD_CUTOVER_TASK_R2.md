# V065-CRYPTO-DATA-ACTIVE-CUTOVER-01 — Local Codex Sol Max / Astra High task

**Task status:** READY_FOR_LOCAL_OPERATOR (R2 updates main SHA after operating contract reconciliation; R1 remains frozen). Historical R10/R11 migration COMPLETED. Existing recurring forward stores NOT migrated; source QA live collection remains BLOCKED. This task authorizes safe inventory/validated migration of existing, previously running forward data locations, **not** initiation of a new market collector or strategy.

## Owner-approved paths and immutable checkpoints

- Authoritative single Git checkout: `/root/workspace/project/quant-0.6.5`, branch `v0.6.5`, expected HEAD at dispatch `2fe503cbab6790863f2d7c7c971e4b98b77434e0`. Read `AGENTS.md` and `GEMINI.md` first. No new branch, no new worktree, no concurrent main writers. This task is operational, not a code rewrite.
- Authoritative receiver: `hyz-laptop`.
- Owner-approved data root: `/root/workspace/project/crypto-data` (realpath, owned by root, 0700, ext4 on /dev/sdd; free estimate ~774GB at 2026-10-17 preflight; recalculate before activity). Approved SOURCE_QA subroot: `crypto-data/prospective/source-qa`, currently empty. Never start SOURCE_QA live.
- Historical R10 and R11-D2 have ALREADY been atomically moved and verified:
  - `crypto-data/historical/r10-binance-vision/data`; original `r10-d1-binance-vision-dev/data` is an absolute symlink to it. 42 files, 760185 B, canonical digest c84539bb92b0ef40db8a9655c91462202255cf8cfd1db8a5b6c7ec5d84e5541e.
  - `crypto-data/historical/r11-binance-core-pilot/data`; original `r11-d2-binance-core-pilot/data` is an absolute symlink to it. 430 files, 63837250 B, digest b2ded95279a9b1b38435968bc95d8e85512046bd10cf87a5329a3fd0abc1bad2.
  - Existing migration receipt `crypto-data/_control/HISTORICAL_RELOCATION_RECEIPT_R1.json`, SHA256 e9b79ceb115712d88bcd0b2deeffc8bcd90b28ca174d58833be5e6000e7a8404. Do not rerun or modify historical moves.

## Existing recurring data jobs to reconcile before cutover

Named systemd user units under `/root/.config/systemd/user/` (read-only until a complete cutover plan and rollback are validated):
- `btc-quant-forward-derivatives.timer/.service`; `quantctl derivatives collect-once --store /root/workspace/project/Quant-agent/data/forward/BTCUSDT/derivatives.sqlite3`, every UTC quarter-hour +20s.
- `btc-quant-forward-health.timer/.service`; `quantctl forward-evidence health`. Inspect implicit read locations without reading market rows unnecessarily.
- `btc-quant-opportunity-forward.timer/.service`; `--store /root/workspace/project/Quant-agent/data/forward/BTCUSDT/opportunity_shadow.sqlite3`.
- `btc-quant-opportunity-resolve.timer/.service`; reads same opportunity store.
- `btc-quant-microstructure-forward.service`; `--root /root/workspace/project/Quant-agent/data/forward/BTCUSDT/microstructure`; determine whether timer-enabled or manually triggered; do not assume status.
- Config/registry files under `Quant-agent/configs/forward` are PROTECTED; keep immutable; never change account credentials, endpoint selection, evidence semantics, risk parameters, clock labeling, H40/A-line or original governance.

Protected root `/root/workspace/project/Quant-agent` must remain physically preserved. Do NOT move, delete, symlink, truncate or rewrite its store in place. User requests **new authoritative write target** under `crypto-data/active/forward/BTCUSDT` while preserving old bytes and old path as read-only historical evidence. Avoid moving the whole Quant-agent project or its private directories.

## Bounded execution plan

### Phase A — READ_ONLY_DEPENDENCY_DISCOVERY (mandatory)
1. Verify every unit, timer next run/last run, real `ExecStart`, effective drop-ins, active processes/open SQLite WAL/SHM and exact data paths. Document all producer/consumer/health/dashboard/export dependencies and implicit default paths; include microstructure, resolver, and any newly discovered scoped forward units.
2. Examine only the named forward-store subtree for inventory metadata and hash/size counts, not unrelated protected archives/history/Quant-agent-sanitized or trade credentials. Never display market rows/account material. Query SQLite integrity/version only in a safe read-only way when admissible; logs should show counts/status, not content.
3. Identify whether each producer supports an explicit new `--store`/`--root` and whether all consumers can be redirected using **systemd user drop-ins outside the protected original project**. If any process writes to hard-coded original files or a reader cannot follow the relocated store, **STOP_UNSAFE_CUTOVER**, no speculative symlinks or force-overrides.
4. Freeze actual paths, device IDs, exact unit definitions, config hashes, schedulers, physical source metrics, WAL state, new target free capacity and a distinct backup location. Preserve a rollback point and gap semantics, no downstream data validation falsely claiming uninterrupted collector coverage.

### Phase B — DRY_RUN_AND_SAFE_SNAPSHOT
5. Prepare a strictly bounded dry-run mapping old→new for each individual DB and microstructure store; validate space reserve >=1GiB plus both source sizes and staging. No recursive expansion beyond allowlisted named store subtree.
6. Plan a narrow quiesce window between timer fires: stop **timers first**, await active services and DB handlers, ensure no further writer, checkpoint/validate WAL or use SQLite backup API safely, then use verified copies into `crypto-data/active/forward/BTCUSDT`. Preserve originals byte-for-byte and their original location. Verify SHA256 and SQLite integrity (report only PASS/FAIL) and paired manifest/sidecar file counts. Record exact missed/paused scheduled origins, never backfill silently or claim original receiver timestamps for transfer time.
7. Validate the new drop-in configs/routing to **both** writer and health/resolve readers, plus no inadvertent second collector. Prefer explicit `ExecStart` overrides and keep untouched originals. If in-memory/env implicit paths cannot be overridden safely, return STOP and do not change timers.

### Phase C — CUTOVER ONLY AFTER PROVED CONTROLLED CONDITIONS
8. Owner authorization for migration is present, but **execute the actual quiesce/cutover only if Phase A/B independently establish safe writer exclusivity, complete consumer routing, backups, an exact rollback and service health probes**. Otherwise STOP with evidence and the smallest missing proof. Never sacrifice existing time series integrity just to satisfy a move request.
9. Update only named user-systemd service drop-ins with backed-up reversible originals, verify syntax and reload user manager. Resume the **previously active** timers at former cadence, not new collectors, after detecting no double writers. The original protected data directory is never deleted or rewritten. Count gaps/epoch transitions explicitly. No hidden replay, overwrite or retry of failed market events.
10. Verify at least two scheduled executions and their intended new physical output paths, or STOP_PENDING_SCHEDULE_CONFIRMATION rather than declaring success. On any regression, restore original drop-ins and timers to the exact earlier state and record full cutover/rollback receipt. No live trading/testnet/account actions.
11. Leave previous protected original data as immutable rollback evidence (no clean-up/move/delete). Do not create aliases that make writers mutate original databases through a symlink. Stop and escalate if systemd privilege, WAL recovery, fsync/directory durability, clock control, or any expected command is unavailable.

## Evidence / deliverable

- One root-owned `crypto-data/_control/ACTIVE_DATA_CUTOVER_REPORT_R1.md` with SHA256, exact old/new store path map, unit/service state table, content digests (or before/after DB integrity if snapshot rearranged bytes), verified counts, open-file/busy checks, scheduler gaps, tested rollback and current terminal state.
- Terminal one of `ACTIVE_DATA_CUTOVER_VERIFIED`, `STOP_UNSAFE_CUTOVER`, `STOP_PENDING_SCHEDULE_CONFIRMATION`. No claim of complete archive migration unless *all* known producers/consumers were identified.
- Include crosswalk separating pre-existing forward download/microstructure jobs from new prospective SOURCE_QA: this migration **DOES NOT** authorize the latter. No change to `SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE`.

**Explicit exclusions:** no Git branch, code edit/push/CI change, random protected filesystem scan, rewinding WAL, original data deletion, market endpoint tests, fresh WebSocket SOURCE_QA subscriptions, strategy experiments, hardcoded time stamps, proxy/geofence bypass or account access.

