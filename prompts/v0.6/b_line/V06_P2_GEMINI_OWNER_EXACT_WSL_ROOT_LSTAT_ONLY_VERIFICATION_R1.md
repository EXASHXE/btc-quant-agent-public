# Gemini P2 — exact owner-provided WSL root, selected nonprotected metadata verification R1

**TASK_ID:** `V06_P2_OWNER_EXACT_WSL_ROOT_LSTAT_ONLY_VERIFICATION_R1`.
**Role:** Gemini trusted read-only filesystem metadata verifier, NOT root-wide discovery, not source-admission/Alpha/trading/engine implementation. This is a finite new task after Gemini P2 R1 was accepted as `ROOT_UNKNOWN within the then-allowed roots`. **The user has now supplied the missing exact WSL root**, so do not ask where it is, say it is unknown, or repeat the previous broad scan.
**CONTROLLER_DISPATCH_SHA:** `b6120e2557d26fc822e740b7d889714a8c0124e6`. READ first [Controller owner-root binding/absolute allowed-path and budget authority](https://github.com/EXASHXE/btc-quant-agent-public/blob/b6120e2557d26fc822e740b7d889714a8c0124e6/reviews/v0.6/b_line/V06_P2_OWNER_SUPPLIED_EXACT_WSL_DATA_ROOT_BINDING_AND_METADATA_VERIFICATION_DISPATCH_R1.md).
**Repo:** `EXASHXE/btc-quant-agent-public`.
**PRECREATED REMOTE EXECUTION BRANCH:** `feature/v06-bline-p2-owner-exact-root-metadata-r1`.
**BRANCH START / INHERITED ACCEPTED GEMINI P2 SHA:** `1e12d6a6467d3bc39c0deedd97204604ac623f18`, not v0.6-docs and not original e0ff8 baseline. A new single direct child commit is preferred. Do NOT amend old R1 receipt.
**Owner data ROOT (Ubuntu WSL, exact case):** `/root/workspace/project/Quant-agent/data`.
**BTC perp selected dataset ROOT:** `/root/workspace/project/Quant-agent/data/research/BTCUSDT`.
**Windows aliases OWNER DECLARED:** `Z:\root\workspace\project\Quant-agent\data` OR `\\wsl.localhost\Ubuntu\root\workspace\project\Quant-agent\data`. Execute **in WSL/Ubuntu**, do not pass Windows path strings to Linux `os.lstat`.
**Fresh isolated source worktree:** `/root/workspace/project/quant-v0.6/p2-owner-exact-root-metadata-r1`. Do NOT `cd` the owner `Quant-agent` repo to commit code or modify its data in any manner; only read selected safe metadata through exact stat paths. Never touch `Quant-agent-sanitized`.

## Context and strict source gates

The user explicitly described:
- `data/research/BTCUSDT/1m/year=2021~2026/month=01~12/` and `raw/{klines,mark_price,funding}` plus `funding_events.csv`, `data_manifest.json`; file names of actual selected monthly parquet still UNVERIFIED.
- `data/research/BTCUSDT_SPOT` separately as spot; `data/research/cross_asset_1h/{ETH,BNB,ADA,LTC,XRP}USDT.parquet` as **1h not 1m**; `data/research/v0.3.19_official_derivatives/hourly_inputs.parquet`. ETH/SOL perp 1m + true continuous 1m Mark have NOT been independently established.
- `data/forward/BTCUSDT/**`, `data/research/h39_validation/**`, any BTC market file from `[2026-02-01,2026-08-01)`: **PROTECTED EXCLUDED** and never enter or inspect, including metadata scans.
- P1 old & new engine routes **TERMINATED** SHA `fd3c13645df9ad2506293b109d3891cf57936208`. Sol R4 science `5032259954e001635c97110c9c50e4a35a2c95b5` finished synthetic-only; PRIORITIZATION IS NOT SIGNAL/ALPHA. No P3 prereg/P4 market-body/live/testnet/funds grant.
- Earlier Gemini package on this branch was designed for project-owned roots and specifically blocks foreign repos `Quant-agent`. **Do not invoke it as-is for root discovery and then count an explicit refusal as missing data**. The *new exact owner-bound metadata authority* permits only exact owner-selected lstat paths and at most six named nonprotected month directory listings. Either add a NEW small isolated script with a hardcoded authorized path set or manually execute a tightly audited explicit Python stat script. Keep the old generic locator untouched.

## Step 1 — branch safety, machine/owner root identity

Verify `git fetch --no-tags`, `git rev-parse HEAD` exactly inherited Gemini P2 SHA, remote new branch HEAD identical, parent history, clean owned worktree, prompt/Controller exact objects. If worktree path exists and is not clearly yours, stop; do not reset/stash/force. Check `os.lstat` of every non-symlink ancestor from `/root/workspace/project` to `Quant-agent/data/research/BTCUSDT` **without following symlink**. The approved Quant-agent data path is READ-METADATA-ONLY; `.git` source/other repo files not to be touched. Preserve actual `device/inode` or stat mode for provenance if safe; no user IDs/host secrets need reporting.
If executing agent lacks local WSL access => `P2_OWNER_ROOT_DECLARED_BUT_EXECUTOR_FILESYSTEM_UNAVAILABLE`, report exact condition, do not mark dataset missing.

## Step 2 — selected fixed-path stat-only feasibility

For 2021/2023/2025, each March and April month, check **ONLY**:
`data/research/BTCUSDT/1m/year=YYYY/month=MM`, then exact `data.parquet` if present. If parquet basename differs, `os.scandir` **only these six approved month directories**, at most 16 entries per month, `lstat` regular names ending `.parquet`, no symlinks or opens. Do **not** stat/list other months, in particular `year=2026` or 2026-02..07. Distinguish PRESENT_METATDATA_ONLY for a regular file from DIRECTORY_PRESENT_FILE_NAME_UNKNOWN and ENOENT exact target. Do not open any parquet footer or hash files. Hard MAX_LSTAT=100, SELECTED_DIR_LIST<=6, SELECTED_DIR_ENTRIES<=16 each, no scan of root children by recursion, no directory listing under `raw/mark_price`, max real market data bytes=0.

Additional exact parent/file stat (NO OPEN):
`data/research/BTCUSDT/data_manifest.json`;
`data/research/BTCUSDT/funding_events.csv`;
`data/research/BTCUSDT/raw/{mark_price,funding,klines}` **parent directories only**;
`data/research/BTCUSDT_SPOT/{data_manifest.json,1m}`;
`data/research/cross_asset_1h/{ETHUSDT.parquet,basket_manifest.json}`;
`data/research/v0.3.19_official_derivatives/{hourly_inputs.parquet,raw_data_manifest.json}`.
These metadata-only checks do not prove 1m Mark availability, funding time PIT, 2026-safe raw files, schema, hash, rights, or three-asset Option A. No raw CSV/SQLite/Parquet contents, SELECT, `head`, `cat`, `pandas`, `pyarrow`, downloading or hashing full archive, no market API.

## Step 3 — truth table and falsification tests

Write small safe pure stdlib `lstat` checker with positive whitelist and tests before actual check, including mock synthetic temporary tree. At least 10 focused checks: exact allowed six dirs, deny 2026, deny forward & h39, deny traversal/`..`, deny symlink in root/leaf, capped dir entries & total calls, missing-vs-denied treatment, no-body opens, spot/perp distinction, mark/funding parent cannot be deemed true minute PIT, expected name mismatch handling. Test never actually uses protected genuine source; simulate names and directories only. Run `pytest -q` selected tests, scoped Ruff, `git diff --check`, parse generated JSON; no full 11–14 minute repository CI required (known unrelated H40 science golden mismatch).
Output a **candidate-month × file-existence** matrix for 6 approved BTC months and **source classes** summarized separately. Real source root must be lstat-confirmed, not inferred from user prose. Assert no protected stats/access; no false **KNOWN_ABSENT** claim if WSL unavailable or permission denied.
Formulate next bounded readiness checks **without executing**: (a) owner grants future selected Kline Parquet read/sha, (b) raw Mark 1m schema/timestamp availability & true continuous 1m PIT, (c) Funding true known-at, settlement/index and price sources, (d) rights/fees/filter/protection gates, (e) ETH/SOL minute data decision or prospective BTC-only *diagnostic* route. BTC-only positive screen issue is **100% single asset exposure >60% ceiling**; **NOT "1/3 assets 33% below >=60% positive support"**. A BTC-only separately authorized diagnostic need not claim 3asset positive support and must be new prospective method if selected.

## Step 4 — owned output, exact push and truthful CI

Allowed only NEW:
`scripts/strategy_research/p2_owner_root_metadata/**`;
`tests/test_v06_p2_owner_root_metadata_*.py`;
`docs/strategy_research/g2_r3/p2_owner_root_metadata_r1/**`;
`evidence/v0.6/b_line/p2_owner_root_metadata_r1/**`.
Commit distinct output `P2_OWNER_ROOT_EXACT_METADATA_REPORT.md`, `P2_OWNER_ROOT_EXACT_SCAN_RECEIPT.json`, `P2_SELECTED_SOURCE_TYPE_AND_PERMISSIONS_MATRIX.json`; include root path (user provided), stat-only source and zero market bytes, metadata stat numbers, exact six nonprotected partitions, sibling file roles, blocked unknown, focused QA, static hashes for YOUR SCRIPTS ONLY and precise parent. Never copy/hardlink any real market data.
Non-force push to precreated new branch; actual `git ls-remote` verifies final branch SHA and one direct parent starting `1e12d6a6467d3bc39c0deedd97204604ac623f18`. No use of user's old quant-v0.6 data worktree. Report remote CI actual status, never substitute focused tests for global green.

**ONE terminal exactly:** `P2_BTC_SELECTED_NONPROTECTED_FILES_LOCATED_METADATA_ONLY`, `P2_OWNER_ROOT_PRESENT_BUT_SELECTED_FILES_INCOMPLETE`, `P2_OWNER_ROOT_DECLARED_BUT_EXECUTOR_FILESYSTEM_UNAVAILABLE`, `P2_OWNER_ROOT_NOT_PRESENT_AT_EXACT_PATH`, `P2_PROTECTION_OR_IDENTITY_STOP`, `BLOCKED_NOT_PUSHED`. Even full metadata presence is **NOT P2 SOURCE_ADMITTED**, no P3/P4/TESTNET/LIVE authority. Never create a follow-up downloader or third engine. Stop with bounded evidence and push.

**Final compact report:** Controller SHA, pinned prompt SHA, owner root, executed WSL root existence, exact six-month observation table, source class presence-vs-unknown, protected zero access, physical metadata-only caps, focused QA/actual CI, branch final exact SHA/parent and terminal; next Controller **separate possible selected-source admission** decision.
