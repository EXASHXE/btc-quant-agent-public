# P2 S3B (PROPOSED ONLY) — Single-File Parquet Footer & Schema QA Grant Contract (R1)

- **Document Role:** `PROPOSED_FUTURE_STAGE_GRANT_CONTRACT_NOT_ACTIVE`
- **Authored Under Stage:** `V06_P2_S3A_GEMINI_INDEPENDENT_ONEFILE_FOOTER_READER_BUILD_SYNTHETIC_R1`
- **Controller S3 Dispatch Authority:** `e150be89bef2540a4aebe7b11e921dd25104fe16`
- **Controller S2 Joint L2 Authority:** `9782c68e9faa95988959ea8e7592aefe0b176067`
- **Current Authorization Status:** **NO REAL-DATA EXECUTION AUTHORIZED IN S3A** (`S3A_READER_BUILT_SYNTHETIC_VERIFIED_PENDING_INDEPENDENT_AUDIT`)

> **IMPORTANT BOUNDARY NOTICE:** This document is a **prospective specification and proposal only**. Passing all S3A synthetic POSIX/Parquet tests does **not** authorize running the reader against `/root/workspace/project/Quant-agent/data`. Any future S3B execution requires (1) an independent Controller L2 audit of the S3A code and (2) a fresh, explicit Controller S3B dispatch commit.

---

## 1. Proposed S3B Single-File Scope & Target Identity

Per Controller S2 Joint L2 Finding **F04** (`9782c68e9faa95988959ea8e7592aefe0b176067`) and Controller S3 Dispatch (`e150be89bef2540a4aebe7b11e921dd25104fe16`), a future S3B pilot gate—if and when separately authorized—is restricted to **exactly one file**:

| Parameter | Proposed S3B Value | Enforcement Mechanism |
| :--- | :--- | :--- |
| **Anchored Owner Data Root** | `/root/workspace/project/Quant-agent/data` | Immutable compile-time constant; zero `--root` / `--data-root` CLI or env overrides permitted. |
| **Single Admitted Relative Path** | `research/BTCUSDT/1m/year=2021/month=03/data.parquet` | 6-component tuple `("research", "BTCUSDT", "1m", "year=2021", "month=03", "data.parquet")` walked via `os.open(..., dir_fd=parent_fd)`. |
| **Historical Stat Receipt Size** | `2,756,024` bytes | Pinned to `c6823dbc46249cac43aa10400aacbbe9f4542410`; S3B must verify `fstat(leaf_fd).st_size == 2_756_024` fail-closed. |
| **Other 5 Candidate Months** | `2021-04`, `2023-03`, `2023-04`, `2025-03`, `2025-04` | **DENIED in S3B** (`DENIED_UNAPPROVED_TARGET_FILE`). |
| **Auxiliary / Raw / Manifest Files** | `data_manifest.json`, `funding_events.csv`, `raw/**`, `ETHUSDT.parquet`, `hourly_inputs.parquet` | **DENIED in S3B** (`DENIED_UNAPPROVED_TARGET_FILE`). |
| **ETH / SOL 1m Perpetuals** | `UNKNOWN_NOT_VERIFIED_NOT_ADMITTED` (Finding F02) | **DENIED in S3B**. |
| **Protected / Withheld Domains** | `2026-02..2026-07`, `year=2026`, `forward`, `H39`, `a_line`, heldout | **PERMANENTLY DENIED** (`DENIED_PROTECTED_PATH_DOMAIN`). |

---

## 2. Proposed S3B Syscall, Descriptor, and Byte Budgets

| Budget / Guardrail | Hard Limit | Nominal S3A Observed Value | Fail-Closed Exception |
| :--- | :--- | :--- | :--- |
| `max_attempted_fs_calls` | `<= 100` (inclusive of failed calls & cleanup closes) | `27` (`8` `openat`, `9` `fstat`, `2` `pread`, `8` `close`) | `SyscallBudgetExceededError` |
| `max_trailer_read_bytes` | `<= 8` bytes (`pread` at `file_size - 8`) | `8` bytes | `ByteBudgetExceededError` |
| `max_footer_read_bytes` | `<= 65,536` bytes (`pread` at `file_size - 8 - footer_len`) | `footer_len` (`1..65,536` bytes) | `ByteBudgetExceededError` / `InvalidParquetFooterLengthError` |
| `max_total_file_read_bytes` | `<= 65,544` bytes (`trailer + footer`) | `8 + footer_len` | `ByteBudgetExceededError` |
| `row_data_pages_read` | `== 0` bytes / `0` pages | `0` | `RowGroupDataReadForbiddenError` |
| `open_fds_remaining` | `== 0` on all exit paths (`finally:`) | `0` | Deterministic `close_all_open_fds()` |

### Mandatory POSIX Descriptor Invariants for S3B
1. **Directory Walk:** Every hop (`<root>`, `research`, `BTCUSDT`, `1m`, `year=2021`, `month=03`) must be opened with `O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC` relative to `parent_fd`, followed by `fstat(fd)` verifying `S_ISDIR(st_mode)` and `st_dev == root_dev`.
2. **Leaf Open:** `data.parquet` must be opened relative to `month=03` `dir_fd` with `O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK`, followed by `fstat(leaf_fd)` verifying `S_ISREG(st_mode)`, `st_dev == root_dev`, `st_nlink == 1`, and `st_size == 2_756_024`.
3. **TOCTOU Verification:** After the two `os.pread` calls (`8`-byte trailer and `footer_len`-byte footer), S3B must re-`fstat(leaf_fd)` and re-open `data.parquet` from `month=03` `dir_fd` (`openat` + `fstat` + `close`) to confirm `(st_dev, st_ino, st_size, st_mtime_ns)` remained invariant throughout the read.

---

## 3. Proposed S3B Output Sanitization & Non-Inference Rules

1. **Sanitized Schema Summary Only:** S3B may emit only `format_version`, `created_by`, `num_columns`, `num_row_groups`, `declared_num_rows`, `footer_length_bytes`, `trailer_length_bytes`, and per-column `(column_index, name, path_in_schema, physical_type, logical_type, converted_type, max_definition_level, max_repetition_level, compression_codecs, encodings, had_embedded_statistics, statistics_suppressed)`.
2. **Complete Value & Statistics Suppression:** Column `min`, `max`, `null_count`, `distinct_count`, dictionary pages, data pages, and custom `key_value_metadata` payloads must remain suppressed (`embedded_statistics_suppressed = True`, `key_value_metadata_suppressed = True`).
3. **Unverified File Header Disclosure:** Because S3 reads only the trailing `<= 65,544` bytes and never reads bytes `0..3`, S3B output receipts must carry `header_verification_status = "FILE_HEADER_NOT_VERIFIED"` and enforce `footer_len + 8 <= file_size - 4`.
4. **What S3B Still Cannot Prove:** Even if S3B succeeds on `2021-03`, a single-file Parquet footer schema summary does **not** prove row-timestamp monotonicity, gap-free 1-minute continuity, true 1m Mark Price availability, funding settlement clock alignment (`known_at` / `available_at`), or multi-month schema stability across `2021-04..2025-04`.

---

## 4. Proposed Owner / Controller Authorization Checklist Before S3B Dispatch

- [ ] **Gate 1 (Independent S3A Audit):** Independent auditor/Controller verifies `feature/v06-bline-p2-s3-footer-reader-r1` commit, AST hygiene, 45 pytest items, 30 security oracle scenarios, and 3 killed mutants.
- [ ] **Gate 2 (Explicit S3B Dispatch SHA):** Controller issues a dedicated S3B dispatch commit explicitly authorizing a single-file footer read of `/root/workspace/project/Quant-agent/data/research/BTCUSDT/1m/year=2021/month=03/data.parquet` with `max_total_read_bytes <= 65,544` and `max_attempted_fs_calls <= 100`.
- [ ] **Gate 3 (Owner Rights & Provenance Confirmation):** Owner confirms whether `research/BTCUSDT/1m` is permitted for post-S3B schema/timestamp QA and clarifies the provenance/location of any `raw/mark_price` and `funding_events.csv` sources.
