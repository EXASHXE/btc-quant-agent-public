# S3A R2 — Bounded Security Repair & Errata Report (`F01`–`F04`)

- **TASK_ID:** `V06_P2_S3A_GEMINI_ROOT_ALIAS_GRANT_BUDGET_AND_SOURCE_SIZE_BOUNDED_REPAIR_R2`
- **CONTROLLER_DISPATCH_SHA:** `89c1caf07eebd3db81dc16314c3238c037e6fac3` (`reviews/v0.6/b_line/V06_P2_S3A_GEMINI_EXACT_SHA_SECURITY_HOLD_AND_BOUNDED_REPAIR_R1.md`)
- **PROMPT_SHA:** `4227f46296b8f66fe33aebf8a7bdbacb6873dc2c` (`prompts/v0.6/b_line/V06_P2_S3A_GEMINI_ROOT_ALIAS_GRANT_BUDGET_AND_SOURCE_SIZE_BOUNDED_REPAIR_R2.md`)
- **EXACT_START_SHA (R1 Commit Parent):** `30833953804bd965c80913ee6a3ecd4ae7457b40`
- **CODE_START_SHA (v0.6 Baseline):** `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`
- **ORIGINAL_STAT_RECEIPT_SHA:** `c6823dbc46249cac43aa10400aacbbe9f4542410` (`evidence/v0.6/b_line/p2_owner_root_metadata_r1/P2_OWNER_ROOT_EXACT_SCAN_RECEIPT.json`, JSON SHA-256 `a3c9169dcbeb31edce492791ef253e42c580411cdb014337e8084229aaaaf3f2`)
- **BRANCH:** `feature/v06-bline-p2-s3-footer-reader-r1`
- **TERMINAL_STATUS:** `S3A_R2_BOUNDED_SECURITY_REPAIR_DELIVERED_PENDING_CONTROLLER_SOL_AUDIT`

---

## 0. Immutable R1 Evidence Preservation & Supersession Banner

Per Controller R2 dispatch `89c1caf07eebd3db81dc16314c3238c037e6fac3` and R2 prompt `4227f46296b8f66fe33aebf8a7bdbacb6873dc2c`, the four original R1 documentation and machine-evidence files committed in `30833953804bd965c80913ee6a3ecd4ae7457b40` are preserved **byte-for-byte unchanged** at their original R1 SHA-256 hashes as an immutable audit trail:

| Frozen R1 Artifact Path | Immutable R1 SHA-256 | R2 Status |
|---|---|---|
| `docs/strategy_research/g2_r3/p2_s3_footer_reader_r1/S3A_READER_BOUNDARY_IMPLEMENTATION_AND_FALSIFICATION_REPORT.md` | `cc9a9f8685c37218fa18162eb1ca81f38427645e962d5beeeed960081c4565dc` | Frozen audit record; superseded on `F01`–`F04` by this R2 report |
| `docs/strategy_research/g2_r3/p2_s3_footer_reader_r1/S3B_PROPOSED_ONE_FILE_FOOTER_QA_GRANT_CONTRACT.md` | `f667a855c92b0c6ab86c7ebdf614e3a903dc9176961e80b4f26b3949c01325b4` | Frozen audit record; superseded on `F01`–`F04` by this R2 report |
| `evidence/v0.6/b_line/p2_s3_footer_reader_r1/S3A_FS_SYSCALL_SECURITY_ORACLE_RESULTS.json` | `5eb83e49fa32d53184b82524c0c2015a7496926ab4c39747871e307d50ec14d9` | Frozen audit record; superseded by `S3A_R2_FS_SYSCALL_SECURITY_ORACLE_RESULTS.json` |
| `evidence/v0.6/b_line/p2_s3_footer_reader_r1/S3A_IMPLEMENTATION_EXECUTION_RECEIPT.json` | `2040a2011fbba18e58d232da7f25c6acfb22f8341bf22567376fdca08e497156` | Frozen audit record; superseded by `S3A_R2_BOUNDED_REPAIR_EXECUTION_RECEIPT.json` |

### Specific R1 Sections Superseded by R2

1. **Root directory open & custody verification (`F01`):** Supersedes R1 Section 2.1 of `S3A_READER_BOUNDARY_IMPLEMENTATION_AND_FALSIFICATION_REPORT.md`, which previously opened the synthetic fixture root path in one call via `os.open(root_path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)` without walking ancestor components (`parts[:-1]`) or verifying harness custody `(st_dev, st_ino)`.
2. **Grant token semantics (`F02`):** Supersedes R1 Section 2.2 of `S3A_READER_BOUNDARY_IMPLEMENTATION_AND_FALSIFICATION_REPORT.md` and Section 2 of `S3B_PROPOSED_ONE_FILE_FOOTER_QA_GRANT_CONTRACT.md`, replacing any "signed capability token" phrasing for `SyntheticTestGrant` with explicit `TEST_ONLY_INTEGRITY_CHECKSUM_NOT_AUTHORIZATION` semantics.
3. **Syscall budget reservation on first FD & close failure accounting (`F03`):** Supersedes R1 Section 2.3 of `S3A_READER_BOUNDARY_IMPLEMENTATION_AND_FALSIFICATION_REPORT.md` regarding syscall cap enforcement at `max_attempted_fs_calls < 27` and `close_all_open_fds()` error propagation.
4. **S1 BTC 1m candidate monthly file sizes (`F04`):** Supersedes R1 Section 1.2 of `S3A_READER_BOUNDARY_IMPLEMENTATION_AND_FALSIFICATION_REPORT.md` and Section 1.2 of `S3B_PROPOSED_ONE_FILE_FOOTER_QA_GRANT_CONTRACT.md` for the five non-pilot BTC 1m candidate months (`2021-04`, `2023-03`, `2023-04`, `2025-03`, `2025-04`), restoring exact byte-for-byte equality with `c6823dbc46249cac43aa10400aacbbe9f4542410:evidence/v0.6/b_line/p2_owner_root_metadata_r1/P2_OWNER_ROOT_EXACT_SCAN_RECEIPT.json`.

---

## 1. Gate `F01` — Trusted Fixture Root Custody & Ancestor Symlink Escape Repair

### 1.1 Root Cause in R1 (`30833953804bd965c80913ee6a3ecd4ae7457b40`)
In R1, `MeteredPosixSyscallWrapper.open_anchored_root_dir(root_path)` validated that `root_path` started with `/tmp/` or `/var/tmp/` and had no `..` segments, and then called:
```python
os.open(root_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
```
On POSIX/Linux kernels, `O_NOFOLLOW` only prevents following a symlink at the **final path component** (`parts[-1]`). If an intermediate ancestor directory under `/tmp/...` (for example `/tmp/s3a_test/allowed_tree/ancestor_alias/data_root`, where `ancestor_alias` is a symlink pointing to a forbidden directory tree) is a symlink, the kernel follows `ancestor_alias` during pathname resolution before applying `O_NOFOLLOW` to `data_root`.

### 1.2 R2 Structural Fix
1. **Component-by-Component Ancestor Walk from `/` (`fd_syscall_wrapper.py`):**
   - `validate_and_split_temp_root_path(root_path)` splits the validated `/tmp/...` or `/var/tmp/...` path into individual path components `parts = ("tmp", ..., root_leaf_name)` and rejects empty segments, `.` or `..` segments, backslashes, NUL bytes, or forbidden tokens (`Quant-agent`, `forward`, `h39`, `2026`, etc.).
   - `open_anchored_root_dir` opens `"/"` with `O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC` and steps one component at a time across every ancestor component `parts[:-1]` using `os.open(ancestor_comp, dir_flags, dir_fd=cur_fd)`.
   - Every ancestor component is checked with `O_NOFOLLOW` (so any ancestor symlink at any depth fails immediately with `ELOOP` / `ENOTDIR` and is disambiguated via `os.stat(ancestor_comp, dir_fd=cur_fd, follow_symlinks=False)` into `SymlinkDetectedError` -> `DENIED_SYMLINK_DETECTED`).
   - Every opened ancestor FD is verified via `os.fstat(cur_fd)` to be a directory (`stat.S_ISDIR`), to reside on the same filesystem device (`st_dev == tmp_base_dev`, catching bind-mounts / cross-device mounts), and to not match any registered forbidden owner-surrogate inode (`is_forbidden_surrogate_inode(st_dev, st_ino)`).
   - Once the parent directory `parts[-2]` is verified, the final root component `parts[-1]` is opened via `self._raw_open(root_leaf_name, dir_flags, dir_fd=cur_fd, label="<root>")` — a single relative component with no `/` separators.
2. **Trusted Temp Root Custody (`TrustedTempRootCustody` in `types.py` & `reader.py`):**
   - `attest_temp_root_custody(root_path)` verifies that no component of `root_path` is a symlink or forbidden surrogate inode, and records `TrustedTempRootCustody(canonical_temp_root, expected_root_dev, expected_root_ino, expected_parent_dev, expected_parent_ino)`.
   - `SingleFileParquetFooterReader` requires `grant.trusted_root_custody` (`require_trusted_custody=True` by default) and verifies both before and after opening `<root>` that:
     - `trusted_custody` is present (`UntrustedRootCustodyError` -> `S3A_HARNESS_ROOT_IDENTITY_NOT_PROVEN` if `None`),
     - `parent_st.(st_dev, st_ino)` matches `(expected_parent_dev, expected_parent_ino)`,
     - `root_st.(st_dev, st_ino)` matches `(expected_root_dev, expected_root_ino)`, and
     - neither parent nor root inode belongs to `_FORBIDDEN_SURROGATE_TREES`.

### 1.3 Executable Adversarial Proof (`F01`)

| Scenario / Test ID | Adversarial Vector | Old R1 `os.open(root, O_NOFOLLOW)` Behavior | Repaired R2 Decision Code | Actual Bytes Read | Open FDs Remaining |
|---|---|---|---|---:|---:|
| `R2_F01_01` / `test_adv27` | Two temp trees (`allowed_tree` + `forbidden_owner_surrogate`) with ancestor symlink `allowed_tree/ancestor_alias -> forbidden_owner_surrogate`, target `.../ancestor_alias/data_root` | Reached `forbidden_owner_surrogate/data_root` (`old_r1_unguarded_reached_forbidden_surrogate = True`) | `DENIED_SYMLINK_DETECTED` | `0` | `0` |
| `R2_F01_02` / `test_adv28` | Multi-hop parent symlink chain `hop1_sym -> hop2_sym -> forbidden_surrogate/data_root` | Followed multi-hop ancestor symlinks | `DENIED_SYMLINK_DETECTED` | `0` | `0` |
| `R2_F01_03` / `test_adv29` | Fixture root path containing `..` (`allowed/../forbidden`) | Rejected by path syntax validator | `DENIED_PATH_SYNTAX_OR_TRAVERSAL` | `0` | `0` |
| `R2_F01_04` / `test_adv29` | Relative path alias (`relative_temp_alias/fixture_root`) | Rejected by path syntax validator | `DENIED_PATH_SYNTAX_OR_TRAVERSAL` | `0` | `0` |
| `R2_F01_05` / `test_adv29` | Direct forbidden owner-surrogate temp tree registered in `_FORBIDDEN_SURROGATE_TREES` | Not checked against surrogate inode registry | `S3A_HARNESS_ROOT_IDENTITY_NOT_PROVEN` | `0` | `0` |
| `R2_F01_06` / `test_adv29` | Parent/root directory renamed and replaced after custody attestation | Not checked against attested `(st_dev, st_ino)` | `S3A_HARNESS_ROOT_IDENTITY_NOT_PROVEN` | `0` | `0` |
| `R2_F01_07` / `test_adv29` | Simulated bind-mount (`st_dev` change on `<root>` or ancestor) | Only checked child `st_dev` against `<root>` | `DENIED_MOUNT_BOUNDARY_ESCAPE` | `0` | `0` |

---

## 2. Gate `F02` — Honest Synthetic Token Semantics (`TEST_ONLY_INTEGRITY_CHECKSUM_NOT_AUTHORIZATION`)

### 2.1 Root Cause in R1
In R1, `SyntheticTestGrant` used a deterministic SHA-256 hash over public in-repo constants (`_SYNTHETIC_GRANT_SECRET`), while docstrings and report prose referred to `signature_hex` as a "signed synthetic test capability token". Because the salt lives in public source code, any caller can compute `compute_grant_signature_hex(...)`. Calling it a cryptographic capability signature overstated its security role.

### 2.2 R2 Structural Fix
1. **Explicit Constant & Field Labeling (`constants.py`, `types.py`):**
   - Defined `SYNTHETIC_GRANT_TOKEN_SEMANTICS = "TEST_ONLY_INTEGRITY_CHECKSUM_NOT_AUTHORIZATION"`.
   - Renamed the internal constant to `_SYNTHETIC_GRANT_PUBLIC_SALT = b"S3A_SYNTHETIC_TEST_INTEGRITY_CHECKSUM_PUBLIC_SALT_V1_NOT_AUTH"`.
   - Added `token_semantics: str = SYNTHETIC_GRANT_TOKEN_SEMANTICS` and property `integrity_checksum_hex` on `SyntheticTestGrant`.
   - `validate_grant_for_target` verifies that `grant.token_semantics == "TEST_ONLY_INTEGRITY_CHECKSUM_NOT_AUTHORIZATION"`.
2. **Separation of Checksum Tamper Detection from Root Custody Isolation (`reader.py`):**
   - The public SHA-256 checksum only detects accidental test-struct field mutation (`DENIED_UNSIGNED_OR_FORGED_GRANT` if corrupted/empty).
   - Actual root isolation is enforced structurally by `validate_and_split_temp_root_path`, the `O_DIRECTORY | O_NOFOLLOW` ancestor walk from `/`, and `TrustedTempRootCustody` `(st_dev, st_ino)` attestation.
   - As proven in `R2_F02_01` and `test_adv30_r2_f02_public_checksum_self_mint_and_honest_semantics`, a caller who recomputes a valid public SHA-256 checksum for an unattested directory (`attest_root_custody=False`) or for the owner root `/root/workspace/project/Quant-agent/data` is rejected fail-closed (`S3A_HARNESS_ROOT_IDENTITY_NOT_PROVEN` and `DENIED_FORBIDDEN_OWNER_DATA_ROOT`, respectively) with `0` bytes read.

---

## 3. Gate `F03` — Syscall Cap & FD Cleanup Invariant (`BUDGET_INSUFFICIENT_STOP` & `DENIED_FD_CLEANUP_CLOSE_FAILED`)

### 3.1 Root Cause in R1
1. **First-FD Close Reservation Defect:** In R1 `MeteredPosixSyscallWrapper._check_syscall_budget(reserve_for_new_fd=True)`:
   ```python
   reserved_closes = len(self._open_fds) + (1 if reserve_for_new_fd and self._open_fds else 0)
   ```
   When `self._open_fds` was empty (`len == 0`), opening the initial `<root>` directory FD did **not** reserve 1 future syscall for closing `<root>`. Consequently, under `max_attempted_fs_calls = 1`, `open("<root>")` succeeded as call #1, and `close_all_open_fds()` then executed `os.close(root_fd)` as call #2 (`attempted_fs_calls_total = 2 > 1`), violating the hard cap `attempted_fs_calls_total <= max_attempted_fs_calls`.
2. **Close Failure Handling in `close_all_open_fds()`:** In R1, if an `os.close(fd)` call raised `OSError`, `_raw_close` caught the error and removed the FD, allowing `read_single_parquet_footer()` to return `ALLOWED_SINGLE_FILE_FOOTER_SCHEMA_PARSED` even when an FD close failed.

### 3.2 R2 Structural Fix
1. **Unconditional Close Reservation for Every New FD (`fd_syscall_wrapper.py`):**
   ```python
   reserved_closes = len(self._open_fds) + (1 if reserve_for_new_fd else 0)
   if self._attempted_fs_calls_total + 1 + reserved_closes > self._max_attempted_fs_calls:
       raise SyscallBudgetExceededError(...)
   ```
   Every `open` (including the very first `<root>` FD when `len(self._open_fds) == 0`) requires at least 2 available calls in the budget (`1` for `open` + `1` reserved for its future `close`), and every non-open syscall (`fstat`, `pread`) requires `1 + len(self._open_fds)` available calls so all currently open FDs can always be closed within `max_attempted_fs_calls`.
   - `SyscallBudgetExceededError` now carries `decision_code = "BUDGET_INSUFFICIENT_STOP"`.
2. **Non-Aborting Cleanup Loop & Fail-Closed Close Failure (`FDCloseFailureError`):**
   - `close_all_open_fds(raise_on_failure=True)` iterates over all remaining open FDs in reverse order inside a per-FD `try ... except OSError` block so a failure on one FD never aborts closing the remaining FDs.
   - `_close_failed` is incremented on any failed `os.close(fd)`, and after all open FDs have been attempted, `close_all_open_fds` raises `FDCloseFailureError` (`DENIED_FD_CLEANUP_CLOSE_FAILED`).
   - In `reader.py`, `finally: wrapper.close_all_open_fds(raise_on_failure=False)` guarantees cleanup on any exception path, and `wrapper.assert_no_close_failures()` on the normal path ensures a close failure always raises `FDCloseFailureError` and never returns a `PASS` receipt.

### 3.3 Executable Syscall Cap & Close-Failure Matrix (`F03`)

| Scenario / Test ID | `max_attempted_fs_calls` | Injected Close Error | Decision Code | `attempted_fs_calls_total` | Cap Respected (`<= cap`) | `open_fds_remaining` | `close_failed` |
|---|---:|---|---|---:|---|---:|---:|
| `R2_F03_SYSCALL_CAP_1` (`test_adv31`) | `1` | None | `BUDGET_INSUFFICIENT_STOP` | `0` | `True` (`0 <= 1`) | `0` | `0` |
| `R2_F03_SYSCALL_CAP_2` (`test_adv32`) | `2` | None | `BUDGET_INSUFFICIENT_STOP` | `2` | `True` (`2 <= 2`) | `0` | `0` |
| `R2_F03_SYSCALL_CAP_3` (`test_adv33`) | `3` | None | `BUDGET_INSUFFICIENT_STOP` | `3` | `True` (`3 <= 3`) | `0` | `0` |
| `R2_F03_SYSCALL_CAP_25` (`test_adv34`) | `25` | None | `BUDGET_INSUFFICIENT_STOP` | `25` | `True` (`25 <= 25`) | `0` | `0` |
| `R2_F03_SYSCALL_CAP_27` (`test_adv35`) | `27` | None | `ALLOWED_SINGLE_FILE_FOOTER_SCHEMA_PARSED` | `27` | `True` (`27 <= 27`) | `0` | `0` |
| `R2_F03_SYSCALL_CAP_100` (`test_adv36`) | `100` | None | `ALLOWED_SINGLE_FILE_FOOTER_SCHEMA_PARSED` | `27` | `True` (`27 <= 100`) | `0` | `0` |
| `R2_F03_CLOSE_FAILURE` (`test_adv37`) | `32` | `EIO` on `month=03` | `DENIED_FD_CLEANUP_CLOSE_FAILED` | `27` | `True` (`27 <= 32`) | `0` | `1` (7 succeeded) |

---

## 4. Gate `F04` — Exact Immutable S1 BTC Six-File Metadata Truth (`c6823dbc46249cac43aa10400aacbbe9f4542410`)

### 4.1 Root Cause in R1
In R1 (`constants.py`, `S3A_READER_BOUNDARY_IMPLEMENTATION_AND_FALSIFICATION_REPORT.md`, and `S3B_PROPOSED_ONE_FILE_FOOTER_QA_GRANT_CONTRACT.md`), the pilot month `2021-03` had the exact `c6823dbc46249cac43aa10400aacbbe9f4542410` byte size (`2,756,024`), and the three S2 errata files (`BTCUSDT_funding_rate_2020_202601.csv = 679,115`, `ETHUSDT_1h_klines.parquet = 2,522,069`, `SOLUSDT_1h_klines.parquet = 2,000,906`) had the exact `c6823dbc46249cac43aa10400aacbbe9f4542410` byte sizes, **but the five non-pilot BTC 1m candidate months (`2021-04`, `2023-03`, `2023-04`, `2025-03`, `2025-04`) carried stale S2 transcription numbers** instead of the exact byte sizes recorded in `c6823dbc46249cac43aa10400aacbbe9f4542410:evidence/v0.6/b_line/p2_owner_root_metadata_r1/P2_OWNER_ROOT_EXACT_SCAN_RECEIPT.json`.

### 4.2 Complete R1 → R2 Errata Table for the 6 BTC 1m Candidate Monthly Files

| Candidate Month | Relative Path under Owner Root | R1 Stale Value (Bytes) | R2 Verified Exact `c6823dbc...` Size (Bytes) | R1 vs R2 Delta | S3 Scope Role |
|---|---|---:|---:|---|---|
| `2021-03` | `research/BTCUSDT/1m/year=2021/month=03/data.parquet` | `2,756,024` | **`2,756,024`** | Unchanged (`0`) | Single Pilot Target (S3B) |
| `2021-04` | `research/BTCUSDT/1m/year=2021/month=04/data.parquet` | `2,492,430` | **`2,621,313`** | Corrected (`+128,883`) | Non-pilot (Denied in S3) |
| `2023-03` | `research/BTCUSDT/1m/year=2023/month=03/data.parquet` | `2,672,321` | **`2,415,597`** | Corrected (`-256,724`) | Non-pilot (Denied in S3) |
| `2023-04` | `research/BTCUSDT/1m/year=2023/month=04/data.parquet` | `2,075,555` | **`2,201,521`** | Corrected (`+125,966`) | Non-pilot (Denied in S3) |
| `2025-03` | `research/BTCUSDT/1m/year=2025/month=03/data.parquet` | `1,970,619` | **`2,352,476`** | Corrected (`+381,857`) | Non-pilot (Denied in S3) |
| `2025-04` | `research/BTCUSDT/1m/year=2025/month=04/data.parquet` | `1,942,082` | **`2,329,220`** | Corrected (`+387,138`) | Non-pilot (Denied in S3) |

### 4.3 Complete 13-File Verification Against Pinned `c6823dbc46249cac43aa10400aacbbe9f4542410` JSON Receipt
`load_pinned_c6823dbc_scan_receipt_json()` (`oracle_runner.py`, tested in `test_u17_r2_f04_pinned_c6823dbc_json_parse_row_wise_equality`) loads `c6823dbc46249cac43aa10400aacbbe9f4542410:evidence/v0.6/b_line/p2_owner_root_metadata_r1/P2_OWNER_ROOT_EXACT_SCAN_RECEIPT.json`, verifies its exact SHA-256 digest (`a3c9169dcbeb31edce492791ef253e42c580411cdb014337e8084229aaaaf3f2`), parses the JSON `target_Checks` array, and verifies row-wise equality across all 13 regular files recorded in `c6823dbc46249cac43aa10400aacbbe9f4542410`:

| # | Relative Path in `c6823dbc46249cac43aa10400aacbbe9f4542410` | `st_size` (Bytes) | `mtime_utc` |
|---:|---|---:|---|
| 1 | `research/BTCUSDT/data_manifest.json` | `475` | `2026-03-23T06:24:09Z` |
| 2 | `research/BTCUSDT/funding_events.csv` | `424,781` | `2026-03-23T06:23:39Z` |
| 3 | `research/BTCUSDT/1m/year=2021/month=03/data.parquet` | `2,756,024` | `2026-03-23T06:23:54Z` |
| 4 | `research/BTCUSDT/1m/year=2021/month=04/data.parquet` | `2,621,313` | `2026-03-23T06:23:54Z` |
| 5 | `research/BTCUSDT/1m/year=2023/month=03/data.parquet` | `2,415,597` | `2026-03-23T06:23:59Z` |
| 6 | `research/BTCUSDT/1m/year=2023/month=04/data.parquet` | `2,201,521` | `2026-03-23T06:23:59Z` |
| 7 | `research/BTCUSDT/1m/year=2025/month=03/data.parquet` | `2,352,476` | `2026-03-23T06:24:04Z` |
| 8 | `research/BTCUSDT/1m/year=2025/month=04/data.parquet` | `2,329,220` | `2026-03-23T06:24:04Z` |
| 9 | `raw/funding/BTCUSDT_funding_rate_2020_202601.csv` | `679,115` | `2026-02-23T06:58:02Z` |
| 10 | `ETHUSDT_1h_klines.parquet` | `2,522,069` | `2026-03-11T09:57:40Z` |
| 11 | `SOLUSDT_1h_klines.parquet` | `2,000,906` | `2026-03-11T09:57:53Z` |
| 12 | `BTCUSDT_perp_1h.parquet` | `2,616,951` | `2026-03-04T15:39:11Z` |
| 13 | `BTCUSDT_spot_1h.parquet` | `2,913,841` | `2026-03-04T15:38:51Z` |

- **ETH/SOL 1m Perp Status (`S2 F02`):** `ETH_SOL_1M_PERP_ABSENT_UNPROVEN` (`ETHUSDT_1h_klines.parquet` and `SOLUSDT_1h_klines.parquet` are 1-hour files at root level; no ETH or SOL 1m perp directories exist in `c6823dbc46249cac43aa10400aacbbe9f4542410`).

---

## 5. Source vs. Test Proof & Terminal Governance Boundary

1. **Zero Real Owner Data Root Access:** Throughout S3A R1 and R2 implementation and testing, `/root/workspace/project/Quant-agent/data` was **never** `stat`ed, `lstat`ed, `open`ed, `scandir`ed, or `read`. `owner_data_root_syscalls == 0` across all 58 pytest items and all 45 oracle scenarios.
2. **All Tests Use Ephemeral Synthetic Temp Fixtures Only:** Every POSIX `os.open`, `os.fstat`, `os.pread`, and `os.close` call in the test suite and oracle runner operated exclusively on ephemeral `/tmp/s3a_*` directories created via `tempfile.TemporaryDirectory` and deleted immediately upon test exit.
3. **No Self-Authorization of S3B:** Passing the S3A R2 synthetic security oracle and 58-test suite **does NOT authorize S3B** or any access to `/root/workspace/project/Quant-agent/data`. Any future single-file footer inspection on the real pilot file (`research/BTCUSDT/1m/year=2021/month=03/data.parquet`, `2,756,024` bytes) requires a separate Controller + Sol audit sign-off and an explicit owner S3B execution dispatch.
