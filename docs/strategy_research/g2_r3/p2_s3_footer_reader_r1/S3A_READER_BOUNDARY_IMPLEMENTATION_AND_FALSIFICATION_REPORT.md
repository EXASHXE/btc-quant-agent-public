# P2 S3A — Independent Single-File POSIX `dir_fd` Parquet Footer Reader Implementation & Falsification Report (R1)

- **Task ID:** `V06_P2_S3A_GEMINI_INDEPENDENT_ONEFILE_FOOTER_READER_BUILD_SYNTHETIC_R1`
- **Branch:** `feature/v06-bline-p2-s3-footer-reader-r1`
- **Direct Code Parent (`CODE_START_SHA`):** `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`
- **Controller S3 Prospective Dispatch (`CONTROLLER_DISPATCH_SHA`):** `e150be89bef2540a4aebe7b11e921dd25104fe16`
- **Controller S2 Joint L2 Decision (`CONTROLLER_S2_JOINT_DECISION_SHA`):** `9782c68e9faa95988959ea8e7592aefe0b176067`
- **S3A Prompt Authority (`PROMPT_SHA`):** `559a56cef42e272c144c40876c2ba9e88f3ddeeb`
- **Historical 6-Month Stat Receipt (`ORIGINAL_STAT_RECEIPT_SHA`):** `c6823dbc46249cac43aa10400aacbbe9f4542410`
- **Terminated Old Locator Counterexample:** `4a1fcc2871708f0e9e3a7c40036ecaab39ba99b8` (Terminated at `ca0b6ea62613e6981b6f818f37f45be8c1d74901`)
- **Terminal Stage Status:** `S3A_READER_BUILT_SYNTHETIC_VERIFIED_PENDING_INDEPENDENT_AUDIT`

---

## 1. Executive Summary & Scope Boundary

This deliverable implements and verifies the standalone **P2 S3A** single-file POSIX descriptor-based Parquet footer reader package (`scripts/strategy_research/p2_s3_footer_reader/`) and its 45-test synthetic POSIX/Parquet verification suite (`tests/test_v06_p2_s3_footer_reader_*.py`).

1. **Zero Real Market Data Touch in S3A:** The physical owner WSL data root (`/root/workspace/project/Quant-agent/data`) was **never** touched (`0` `lstat`, `0` `stat`, `0` `open`, `0` `scandir`, `0` `pread` calls). All executable tests run exclusively against ephemeral temporary directory trees (`tempfile.TemporaryDirectory()` / `pytest` `tmp_path`) populated with synthetic Parquet bytes.
2. **Complete Package Independence:** `scripts/strategy_research/p2_s3_footer_reader/` has **zero** imports from S1 or S2 modules (`p2_s2_source_contract`, etc.), verified by AST inspection (`test_u08_zero_imports_from_s1_or_s2_modules`).
3. **Genuine POSIX `dir_fd` & `pread` Implementation:** Unlike S2's string-based policy simulator, S3A executes real OS kernel descriptor calls (`os.open(..., dir_fd=...)`, `os.fstat`, `os.pread`, `os.close`) wrapped inside `MeteredPosixSyscallWrapper`.

---

## 2. Controller S2 Joint L2 Errata Corrections (`F01`–`F04`)

Per Controller Joint L2 Review (`9782c68e9faa95988959ea8e7592aefe0b176067`), all four S2 findings (`F01`–`F04`) are resolved in S3A:

| Finding | S2 Defect Identified by Controller | S3A Resolution & Verification |
| :--- | :--- | :--- |
| **F01** | Four non-BTC-perp auxiliary file sizes in S2 constants mismatched `c6823dbc46249cac43aa10400aacbbe9f4542410`. | Corrected in `VERIFIED_C6823DBC_FILE_SIZES_BYTES` (`constants.py`) and verified in `test_u02_s2_errata_f01_and_f02_exact_c6823dbc_sizes`: `research/cross_asset_1h/ETHUSDT.parquet = 2,907,000` (was `3,391,374`), `research/cross_asset_1h/basket_manifest.json = 56,012` (was `3,674`), `research/v0.3.19_official_derivatives/hourly_inputs.parquet = 3,101,084` (was `2,058,958`), `research/v0.3.19_official_derivatives/raw_data_manifest.json = 420,725` (was `4,402`). Single pilot `2021-03` confirmed at `2,756,024` bytes. |
| **F02** | ETH/SOL 1m perpetual availability was over-claimed as whole-host `ABSENT`. | Corrected to `ETH_SOL_1M_PERP_STATUS = "UNKNOWN_NOT_VERIFIED_NOT_ADMITTED"`. |
| **F03** | S2 walker was a string-based simulator rather than a real POSIX `dir_fd` descriptor reader. | S3A implements `MeteredPosixSyscallWrapper` and `SingleFileParquetFooterReader` using real `os.open(..., dir_fd=...)`, `os.fstat`, `os.pread`, and `os.close` tested on real POSIX symlinks, FIFOs, hardlinks, permissions, and atomic rename swaps. |
| **F04** | S2 proposed a 6-file / 12 MB budget instead of a single-file footer pilot. | S3A enforces a single admitted pilot relative path (`research/BTCUSDT/1m/year=2021/month=03/data.parquet`), `max_attempted_fs_calls <= 100`, `max_trailer_read_bytes <= 8`, `max_footer_read_bytes <= 65,536`, and `max_total_read_bytes <= 65,544`. |

---

## 3. POSIX `dir_fd` Walk, Syscall Accounting, and TOCTOU Architecture

### 3.1 Pre-Syscall Hard Gates (`0` OS Calls on Rejection)
Before opening the anchored root directory FD, `SingleFileParquetFooterReader` enforces:
1. **CLI & Environment Override Gate (`validate_no_cli_or_env_overrides`):** Rejects `--root`, `--data-root`, `--owner-root`, `--allow-owner-root`, `--bypass-grant`, `--production`, and environment variables `QUANT_AGENT_DATA_ROOT`, `BTC_QUANT_DATA_ROOT`, `S3_FOOTER_READER_ROOT_OVERRIDE`, `S3_ALLOW_REAL_OWNER_DATA` with `CliOrEnvRootOverrideForbiddenError` (`DENIED_CLI_OR_ENV_ROOT_OVERRIDE`).
2. **Production / Owner Root Hard Block (`assert_not_owner_data_root`):** Rejects `production_mode=True`, `synthetic_test_mode=False`, or any fixture root matching or inside `/root/workspace/project/Quant-agent/data` (including case and WSL mount aliases) with `ProductionExecutionForbiddenError` (`DENIED_PRODUCTION_OR_OWNER_ROOT_FORBIDDEN`).
3. **Relative Path & Protected Domain Gate (`validate_and_split_single_pilot_rel_path`):** Rejects empty strings, leading/trailing slashes, backslashes, NUL bytes, `.` and `..` segments (`DENIED_PATH_SYNTAX_OR_TRAVERSAL`), protected 2026/forward/H39/heldout tokens (`DENIED_PROTECTED_PATH_DOMAIN`), and any relative path other than `research/BTCUSDT/1m/year=2021/month=03/data.parquet` (`DENIED_UNAPPROVED_TARGET_FILE`).
4. **Cryptographic Grant Gate (`validate_synthetic_grant`):** Verifies SHA-256 HMAC domain signature, issue/expiry epoch window, single-file scope, and `allow_row_group_reads=False` / `allow_real_owner_root=False`.

### 3.2 Component-by-Component `dir_fd` Walk & Linux `ENOTDIR`/`ELOOP` Disambiguation
1. **Anchored Root Open:** Opens `synthetic_fixture_root` with `os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC` and records `root_dev = fstat(root_fd).st_dev`.
2. **Intermediate Directory Hops (`research` -> `BTCUSDT` -> `1m` -> `year=2021` -> `month=03`):** Each component is opened relative to `parent_fd` via `os.open(comp, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC, dir_fd=parent_fd)`.
   - *Linux Kernel Nuance Handled:* On Linux, calling `openat` with both `O_DIRECTORY` and `O_NOFOLLOW` on a symlink to a directory returns `ENOTDIR` rather than `ELOOP`. Whenever `ENOTDIR` occurs on a directory hop, `MeteredPosixSyscallWrapper._disambiguate_enotdir_or_symlink` immediately performs a counted `openat` probe with `O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK` (without `O_DIRECTORY`): symlinks deterministically raise `ELOOP` (`SymlinkDetectedError`), whereas regular files open cleanly, are immediately closed (counted), and raise `NotADirectoryComponentError`.
   - Every directory hop verifies `stat.S_ISDIR(st.st_mode)` and `st.st_dev == root_dev` (`MountBoundaryEscapeError` on mismatch).
3. **Final Leaf Open (`data.parquet`):** Opened relative to `month=03` `dir_fd` with `os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK`. Passing `O_NONBLOCK` prevents an attacker-planted FIFO pipe from hanging `openat` before `fstat` checks `stat.S_ISREG(leaf_st.st_mode)` (`NonRegularFileError`). Also enforces `leaf_st.st_dev == root_dev` and `leaf_st.st_nlink == 1` (`HardlinkOrAliasError`).
4. **Two-Step Bounded `os.pread` & TOCTOU Identity Verification:**
   - Step 1: `os.pread(leaf_fd, 8, file_size - 8)` reads the 8-byte trailer (`footer_len`, `magic`). Validates `magic == b"PAR1"`, `1 <= footer_len <= 65,536`, and `footer_len + 8 <= file_size - 4`.
   - Step 2: `os.pread(leaf_fd, footer_len, file_size - 8 - footer_len)` reads the Thrift `FileMetaData` bytes.
   - Step 3: Re-stats `leaf_fd` AND re-opens `data.parquet` from `month=03` `dir_fd` (`openat` + `fstat` + `close`), verifying `(st_dev, st_ino, st_size, st_mtime_ns)` equality across all three checkpoints (`TOCTOUOrFDIdentityError` on any mutation or atomic rename swap).
5. **Deterministic FD Cleanup & Close-Slot Reservation:** `MeteredPosixSyscallWrapper` reserves 1 syscall budget slot per open FD so that even if `SyscallBudgetExceededError` triggers mid-walk, `finally: wrapper.close_all_open_fds()` closes every open FD within `max_attempted_fs_calls` (`open_fds_remaining == 0`).

### 3.3 In-Memory Footer Parsing & Statistics Suppression
`parse_in_memory_parquet_footer` accepts strictly `type(val) is bytes` in RAM (rejecting `str`, `Path`, `int` FD, or streams with `ParserInputViolationError`). It constructs `pyarrow.BufferReader(b"PAR1" + footer_bytes + trailer_bytes)` in RAM, extracts column names, physical/logical/converted types, codecs, encodings, `num_row_groups`, and `declared_num_rows`, strips all column `min`/`max`/`null_count`/`distinct_count` statistics and `key_value_metadata`, and stamps `header_verification_status = "FILE_HEADER_NOT_VERIFIED"`.

---

## 4. Synthetic Security Oracle & Mutant Falsification Results

All **30** oracle scenarios (4 positive + 26 adversarial negative) and **3** deliberate security mutants were executed against real temporary files and verified in `evidence/v0.6/b_line/p2_s3_footer_reader_r1/S3A_FS_SYSCALL_SECURITY_ORACLE_RESULTS.json`:

| ID | Category | Scenario Description | Expected / Actual Decision Code | Open FDs Left | Passed |
| :--- | :--- | :--- | :--- | :---: | :---: |
| `POS_01` | Positive | Valid synthetic `2021-03` footer read via `dir_fd` + `pread` (27 syscalls) | `ALLOWED_SINGLE_FILE_FOOTER_SCHEMA_PARSED` | `0` | PASS |
| `POS_02` | Positive | 300 KB body reads only 8B trailer + compact footer (`< 4 KB`) | `ALLOWED_SINGLE_FILE_FOOTER_SCHEMA_PARSED` | `0` | PASS |
| `POS_03` | Positive | Uncompressed Parquet without embedded statistics | `ALLOWED_SINGLE_FILE_FOOTER_SCHEMA_PARSED` | `0` | PASS |
| `POS_04` | Positive | Bounded 30-syscall budget completes cleanly in 27 syscalls | `ALLOWED_SINGLE_FILE_FOOTER_SCHEMA_PARSED` | `0` | PASS |
| `NEG_01` | CLI/Env Guard | CLI `--data-root` override flag | `DENIED_CLI_OR_ENV_ROOT_OVERRIDE` | `0` | PASS |
| `NEG_02` | CLI/Env Guard | Env `QUANT_AGENT_DATA_ROOT` override | `DENIED_CLI_OR_ENV_ROOT_OVERRIDE` | `0` | PASS |
| `NEG_03` | Owner Root | Direct reference to `/root/workspace/project/Quant-agent/data` | `DENIED_PRODUCTION_OR_OWNER_ROOT_FORBIDDEN` | `0` | PASS |
| `NEG_04` | Owner Root | `production_mode=True` | `DENIED_PRODUCTION_OR_OWNER_ROOT_FORBIDDEN` | `0` | PASS |
| `NEG_05` | Symlink | Root directory itself is a symlink | `DENIED_SYMLINK_DETECTED` | `0` | PASS |
| `NEG_06` | Symlink | Intermediate symlink at `research` | `DENIED_SYMLINK_DETECTED` | `0` | PASS |
| `NEG_07` | Symlink | Intermediate symlink at `month=03` | `DENIED_SYMLINK_DETECTED` | `0` | PASS |
| `NEG_08` | Symlink | Final leaf `data.parquet` is a symlink | `DENIED_SYMLINK_DETECTED` | `0` | PASS |
| `NEG_09` | Traversal | `..` traversal segment in relative path | `DENIED_PATH_SYNTAX_OR_TRAVERSAL` | `0` | PASS |
| `NEG_10` | Traversal | Leading `/` absolute path | `DENIED_PATH_SYNTAX_OR_TRAVERSAL` | `0` | PASS |
| `NEG_11` | File Type | Intermediate component `1m` is a regular file | `DENIED_NOT_A_DIRECTORY_COMPONENT` | `0` | PASS |
| `NEG_12` | File Type | Final leaf `data.parquet` is a directory | `DENIED_NON_REGULAR_FILE` | `0` | PASS |
| `NEG_13` | File Type | Final leaf `data.parquet` is a named FIFO pipe | `DENIED_NON_REGULAR_FILE` | `0` | PASS |
| `NEG_14` | Mount Escape | Cross-device `st_dev` change at `year=2021` | `DENIED_MOUNT_BOUNDARY_ESCAPE` | `0` | PASS |
| `NEG_15` | Hardlink | Hardlinked target leaf (`st_nlink = 2 > 1`) | `DENIED_HARDLINK_OR_INODE_ALIAS` | `0` | PASS |
| `NEG_16` | TOCTOU | Mid-read atomic `os.replace` swap of `data.parquet` | `DENIED_TOCTOU_OR_FD_IDENTITY_MISMATCH` | `0` | PASS |
| `NEG_17` | Errno | `EACCES` permission denied distinct from `ENOENT` | `DENIED_EACCES_PERMISSION` | `0` | PASS |
| `NEG_18` | Errno | `ENOENT` missing target file | `DENIED_ENOENT_NOT_FOUND` | `0` | PASS |
| `NEG_19` | Scope | Non-pilot month `2021-04` rejected | `DENIED_UNAPPROVED_TARGET_FILE` | `0` | PASS |
| `NEG_20` | Protected | Protected `2026-02` holdout path rejected | `DENIED_PROTECTED_PATH_DOMAIN` | `0` | PASS |
| `NEG_21` | Grant | Expired / unsigned / tampered grant rejected | `DENIED_EXPIRED_GRANT` | `0` | PASS |
| `NEG_22` | Parquet | Invalid trailer magic `!= b"PAR1"` | `DENIED_INVALID_PARQUET_TRAILER_MAGIC` | `0` | PASS |
| `NEG_23` | Parquet | `footer_len = 70,000 > 65,536` cap | `DENIED_INVALID_PARQUET_FOOTER_LENGTH` | `0` | PASS |
| `NEG_24` | Parquet | `footer_len + 8 > file_size - 4` extent overlap | `DENIED_PARQUET_FOOTER_EXCEEDS_FILE_EXTENT` | `0` | PASS |
| `NEG_25` | Byte/Read | Truncated file / short `pread` (`actual < requested`) | `DENIED_SHORT_READ_OR_TRUNCATED_FILE` | `0` | PASS |
| `NEG_26` | Parquet | Corrupted Thrift footer bytes | `DENIED_CORRUPTED_PARQUET_THRIFT_FOOTER` | `0` | PASS |

### Deliberate Mutant Falsification Proofs
- **`MUTANT_M1_OMIT_O_NOFOLLOW_ON_OPENAT`:** Injected omission of `O_NOFOLLOW` on symlinked target leaf; killed by `test_mut01_mutant_omitting_o_nofollow_is_killed` (`DENIED_SYMLINK_DETECTED`).
- **`MUTANT_M2_DIRECT_PATH_OR_UNCOUNTED_IO_TO_PARSER`:** Injected direct path/FD argument into `parse_in_memory_parquet_footer` bypassing `MeteredPosixSyscallWrapper`; killed by `test_mut02_mutant_passing_path_or_fd_to_parser_is_killed` (`DENIED_PARSER_DIRECT_PATH_OR_FD_FORBIDDEN`).
- **`MUTANT_M3_LEAK_EMBEDDED_COLUMN_STATISTICS_OR_KV_METADATA`:** Injected column `min`/`max` statistics and custom `key_value_metadata` into synthetic Parquet fixture; killed by `test_mut03_mutant_leaking_column_min_max_statistics_is_killed` verifying complete suppression.
