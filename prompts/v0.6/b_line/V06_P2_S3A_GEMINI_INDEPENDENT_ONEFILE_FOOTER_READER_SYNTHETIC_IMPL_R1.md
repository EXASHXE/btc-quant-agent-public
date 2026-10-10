# Gemini — P2 S3A independent one-file Footer reader: real POSIX FD implementation, synthetic-only execution R1

**TASK_ID:** `V06_P2_S3A_GEMINI_INDEPENDENT_ONEFILE_FOOTER_READER_BUILD_SYNTHETIC_R1`.
**ROLE:** B-line Gemini engineering executor. Build a **real descriptor-based safe footer reader**, **not** a market backtester, signal generator, old P2 locator patch, or synthetic-only mock pretending to be a production reader.
**CONTROLLER_DISPATCH_SHA:** `e150be89bef2540a4aebe7b11e921dd25104fe16`.
**Read FIRST:** [Binding Controller S3A security and no-owner-IO dispatch](https://github.com/EXASHXE/btc-quant-agent-public/blob/e150be89bef2540a4aebe7b11e921dd25104fe16/reviews/v0.6/b_line/V06_P2_S3_SINGLE_NONPROTECTED_PARQUET_FOOTER_READER_PROSPECTIVE_BUILD_DISPATCH_R1.md). That complete document controls on conflict. This Prompt is implementation direction, not a new data access grant.

## Exact identity and isolated worktree
- GitHub `EXASHXE/btc-quant-agent-public`.
- **Branch precreated** `feature/v06-bline-p2-s3-footer-reader-r1`; **required initial remote HEAD/code parent** `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32` (`v0.6` code, NOT docs; DO NOT checkout S1 or S2 implementation branches into this worktree).
- Suggested isolated root `/root/workspace/project/quant-v0.6/p2-s3-footer-reader-r1` if unused and clean. Explicitly check status, linked worktree ownership and exact SHA before edits. Never overwrite/stash/reset/clean another worker's tree or touch `/root/workspace/project/Quant-agent`, `Quant-agent-sanitized`, or other agents' branches.
- Read Controller [joint S2 decision SHA 9782c68e...](https://github.com/EXASHXE/btc-quant-agent-public/blob/9782c68e9faa95988959ea8e7592aefe0b176067/reviews/v0.6/b_line/V06_P2_S2_GEMINI_SOURCE_CONTRACT_AND_SOL_PIT_SCIENCE_CONTROLLER_JOINT_L2_R1.md). It identified **four incorrect source file sizes** in previous Gemini S2 matrix; DO NOT import its erroneous constants nor treat synthetic walker as real FD reader. Reuse safe source **path strings** from original [six-month metadata receipt SHA c6823...](https://github.com/EXASHXE/btc-quant-agent-public/blob/c6823dbc46249cac43aa10400aacbbe9f4542410/evidence/v0.6/b_line/p2_owner_root_metadata_r1/P2_OWNER_ROOT_EXACT_SCAN_RECEIPT.json). Old `p2_owner_root_metadata` locator code last SHA `4a1fcc...` was TERMINATED; do not copy/import/resurrect it.
- **Single prospective file alias**: fixed root `/root/workspace/project/Quant-agent/data`, relative `research/BTCUSDT/1m/year=2021/month=03/data.parquet`. This is a **string in this task**, not a permitted filesystem target. NO actual `os.stat/lstat/open/scandir` of real market data or root, Parquet footer, CSV header/rows, full file hash, historical download/API, protected data, H39/H40/H41/forward. No external public market API substitutes. All real IO in tests must target tempfile synthetic filesystem you create. No live/testnet/real-funds authority.

## Program of work — one finite implementation cycle

**P0 — security authority + interface freeze.** Before editing, verify frozen start/Controller identities and project status, sketch exact public API and safety matrix. No mutable global `allow_custom_root` in production, no CLI/environment override to open owner root. Production library must require a separate not-yet-published Controller-approved grant, unavailable in this task; even imported direct low-level callable must have an explicit impossibility of owner-root execution without externally supplied capability. Test fixtures may inject a separate clearly marked test-only root and synthetic grant, but cannot convert user-supplied CLI argument into a production capability. Ensure all possible paths to read owner root are fail-closed in this task. Do not create a runnable `--read-real` command yet.

**P1 — real descriptor implementation tested on temp files.** New `scripts/strategy_research/p2_s3_footer_reader/**` module using POSIX `os.open(..., dir_fd=<parent_fd>, flags=O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC)` per component anchored at a trusted root; leaf with `O_RDONLY|O_NOFOLLOW|O_CLOEXEC`, `fstat`, `os.pread`, `os.close`. Disallow `..`, empty, mixed absolute, `/` and `\` attacks, symlinks, mount escapes, nonregular target, wrong name/month, EACCES/ENOENT conflation, real-root fallback. Do NOT perform insecure check-then-open by absolute path. Use bound file descriptors and exact fixed 2021-03 filename, no wildcard/directory scans. Document that symlink checks on temp fixtures are **necessary not sufficient** for arbitrary hostile mounted OS; independent audit required.

**P2 — bit-exact budgets and footer parser.** Enforce `max_attempted_FS_calls<=100` inclusive failed invocations, with actual wrapper-level counting of each `openat, fstat, pread, close`. Close all FDs on hard stops; hard cap handling for cleanup must be explicit and not leak FD if budget exhausted. Limit **actual single candidate source reads to <=65,544 bytes**, split as up to 8 terminal bytes + up to 65,536 Footer. Track requested and returned bytes, short reads and attempts, no unmetered third-party file I/O. Verify terminal `PAR1`, little-endian metadata length and footer extent, type/format errors fail. Never read real first header or any data pages/row group, never assume zero market-derived statistics in Footer. Parse strictly from bounded byte-array in RAM, optionally PyArrow from `BufferReader` ONLY on a reconstructed in-memory Footer container if proven by tiny test fixtures; unknown/thrift decoder errors STOP. Output only allowed synthetic schema column/type and declared row-count fields; no raw footer bytes, price/statistic min/max or actual values. If physical header magic not read, report `FILE_HEADER_NOT_VERIFIED`, not full Parquet validity.

**P3 — real adversarial POSIX temp-fixture proofs.** >=30 actual pytest items including >=18 negative cases, >=3 deliberate mutants killed, including:
- missing/invalid/stale grant, owner-root production calls denied before ANY OS operation, CLI/root-option bypass impossible;
- exact selected path versus adjacent month/file/asset, `.. `, absolute, NUL, `\`;
- symlink at parent/year/month/leaf, mount/device escape simulation or guarded fake device stat, TOCTOU replace/link race, FD inode/device mismatch;
- EACCES distinct from ENOENT and wrong regular-file/type;
- corrupted/truncated trailer, absurd `footer_length`, short read and truncated/negative offsets;
- actual 65,544-byte cap and request 65,545 rejection, OS syscall accounting cap 100 including failed attempts and close cleanup;
- no real root stats/reads, no `os.path.exists(real)` fallback, no network, no price rows;
- synthetic genuine Parquet fixture produces expected limited schema if dependency present; hostile footer statistics do not appear in output.

Record OS-observed tempfile FD/scoped `pread` counters, return codes, stable fixture digests, rejected mutants, exact no-real-root accesses in controlled harness, no invented successes. If a dependency cannot be installed, explicitly mark the particular schema case `BLOCKED_DEPENDENCY`, but still test bounded raw Footer bytes. Any unresolved component safety issue => fail terminal; no waivers to get green.

**P4 — immutable deliverables and quality.** New paths only:
- `scripts/strategy_research/p2_s3_footer_reader/**` — independent code, no S1/S2 imports.
- `tests/test_v06_p2_s3_footer_reader_*.py`.
- `docs/strategy_research/g2_r3/p2_s3_footer_reader_r1/S3A_READER_BOUNDARY_IMPLEMENTATION_AND_FALSIFICATION_REPORT.md`.
- `docs/strategy_research/g2_r3/p2_s3_footer_reader_r1/S3B_PROPOSED_ONE_FILE_FOOTER_QA_GRANT_CONTRACT.md` (**proposal only**, no actual grant).
- `evidence/v0.6/b_line/p2_s3_footer_reader_r1/S3A_FS_SYSCALL_SECURITY_ORACLE_RESULTS.json`.
- `evidence/v0.6/b_line/p2_s3_footer_reader_r1/S3A_IMPLEMENTATION_EXECUTION_RECEIPT.json`.

Use `ruff check <new code/test paths>`, `python -m pytest -q tests/test_v06_p2_s3_footer_reader_*.py` with exact passing count, scoped `compileall`, `git diff --check`, check all own JSON and allowlist. One bounded finish cycle. Do not run/rewrite new source on real WSL root. Preserve old evidence/fixture SHAs. Make one non-force push to branch and verify **remote final commit, direct parent=`e0ff8c...`, exact changed paths, actual CI**. If known inherited H40-only golden mismatch occurs again, label it precisely, don't modify H40.

## Completion contract

Send Controller a compact final receipt with exact `CONTROLLER_DISPATCH_SHA`, task and branch IDs, final SHA/parent/files, 30+ real tests and number of hostile negatives/mutants, injected test-grant versus real grant absence, actual per-test oracles/counters, Ruff/CI status and link, limitations and **one of**:
- `S3A_READER_BUILT_SYNTHETIC_VERIFIED_PENDING_INDEPENDENT_AUDIT`;
- `S3A_READER_SECURITY_OR_ACCOUNTING_FAILED_STOP`;
- `BLOCKED_IDENTITY_OR_SCOPE`;
- `BLOCKED_NOT_PUSHED`.

**Do NOT declare source admitted, owner rights granted, real Footer read completed, P3/P4 effective, Alpha or LIVE authorized.** If a real operator grant or owner consent is asked for, STOP and return to Controller; do not self-grant.

## Controller next action after your push (not this task)

Controller independently verifies exact remote SHA, CI and security code (not just self-report), THEN freezes that SHA and sends an independent **GPT-6 Sol High static/negative audit** on its own branch. Only AFTER an independent accepted reader and explicit owner consent may Controller authorize **S3B real one-file <=65,544-byte schema/Footer inspection**. Do not start Sol audit early or assume tests alone suffice.
