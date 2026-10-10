# Gemini P2 — Verifier Security & CI Semantic Repair Report (R1)

- **TASK_ID:** `V06_P2_OWNER_EXACT_ROOT_CI_AND_SYMLINK_FAIL_CLOSED_REPAIR_R1`
- **ROLE:** Gemini Scoped Verifier-Maintainer
- **CONTROLLER_DISPATCH_SHA:** `52830a73adf9e8c318da8efa8f10c6323a6292b8` ([Controller Dispatch Document](https://github.com/EXASHXE/btc-quant-agent-public/blob/52830a73adf9e8c318da8efa8f10c6323a6292b8/reviews/v0.6/b_line/V06_P2_OWNER_EXACT_ROOT_CONTROLLER_L2_METADATA_EVIDENCE_AND_CI_SEMANTIC_REPAIR_R1.md))
- **PROMPT_PINNED_SHA:** `6ef27e3d6a646786da691ad784497211a775fe83` ([Repair Prompt](https://github.com/EXASHXE/btc-quant-agent-public/blob/6ef27e3d6a646786da691ad784497211a775fe83/prompts/v0.6/b_line/V06_P2_GEMINI_OWNER_EXACT_ROOT_CI_AND_SYMLINK_FAIL_CLOSED_REPAIR_R1.md))
- **EXACT_START_SHA:** `c6823dbc46249cac43aa10400aacbbe9f4542410`
- **PARENT_INHERITED_SHA:** `1e12d6a6467d3bc39c0deedd97204604ac623f18`
- **EXECUTION_BRANCH:** `feature/v06-bline-p2-owner-exact-root-metadata-r1`
- **LOCAL_WORKTREE:** `/root/workspace/project/quant-v0.6/p2-owner-exact-root-metadata-r1`
- **TERMINAL_VERDICT:** `P2_VERIFIER_ONE_SHOT_REPAIR_DELIVERED_PENDING_CONTROLLER`

---

## 1. Executive Summary & Root Cause Analysis

Following Controller review `52830a73adf9e8c318da8efa8f10c6323a6292b8` and examination of GitHub Actions run [`38014778959`](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38014778959), Gemini executed a single bounded repair cycle on the verifier package and test harness.

The CI failure was caused by 20 Ruff code-quality violations in the new verifier package that caused the quality step (`Ruff with bounded historical EXE001 debt`) to fail before test execution. Furthermore, source review identified critical semantic and security vulnerabilities in error handling, symlink traversal, and root containment.

This repair delivers:
1. **20 → 0 Ruff Violations:** Complete resolution across all newly authored scripts and tests without any blanket `# noqa` exclusions.
2. **Intermediate Symlink Non-Following Walk:** Component-by-component `os.lstat` verification on every ancestor and child directory segment (`1m`, `year=YYYY`, `month=MM`), failing closed immediately upon encountering any symbolic link.
3. **Fail-Closed Root Containment:** Hardened root containment using `os.path.commonpath` to block root escape tricks (`data-v2`, traversal), and replaced symlink-following `os.path.exists()` with `os.lstat()`.
4. **Exception Specialization & Propagation:** Replaced broad `Exception` catches with specific OS exception handling; `ProbeSecurityError` and `ProbeBudgetExceededError` strictly propagate; `PermissionError` is preserved as `PERMISSION_DENIED` and never conflated with missing targets (`ENOENT`).
5. **Real Focused Test Expansion:** Expanded test suite from 17 to 25 passing unit and adversarial tests covering intermediate symlinks, malicious alternate filenames, permission denial isolation, and budget propagation.
6. **Strict Evidence Preservation:** Original six-month metadata receipt, permissions matrix, and audit report remain strictly untouched and frozen.

---

## 2. Ruff Violations Resolution Table (20 → 0 Delta)

| # | File | Rule | Description | Resolution |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `scripts/.../__init__.py:3` | `I001` | Unsorted import block | Organized imports according to PEP 8 / isort rules |
| 2 | `scripts/.../__init__.py:15` | `RUF022` | Unsorted `__all__` list | Sorted `__all__` alphabetically |
| 3 | `scripts/.../cli.py:30` | `F401` | Unused import `TerminalVerdict` | Removed unused import |
| 4 | `scripts/.../cli.py:52` | `UP017` | `datetime.now(timezone.utc)` deprecated | Converted to `datetime.now(UTC)` |
| 5 | `scripts/.../cli.py:57` | `F541` | f-string without placeholders | Removed extraneous `f` prefix |
| 6 | `scripts/.../cli.py:71` | `ISC004` | Unparenthesized implicit concatenation | Wrapped multi-line string in explicit parentheses |
| 7 | `scripts/.../cli.py:121` | `ISC004` | Unparenthesized implicit concatenation | Wrapped multi-line string in explicit parentheses |
| 8 | `scripts/.../cli.py:208` | `ISC004` | Unparenthesized implicit concatenation | Wrapped multi-line string in explicit parentheses |
| 9 | `scripts/.../cli.py:258` | `UP017` | `datetime.now(timezone.utc)` deprecated | Converted to `datetime.now(UTC)` |
| 10 | `scripts/.../cli.py:301` | `F541` | f-string without placeholders | Removed extraneous `f` prefix |
| 11 | `scripts/.../config.py:5` | `F401` | Unused import `os` | Removed unused import |
| 12 | `scripts/.../config.py:6` | `F401` | Unused import `dataclasses.field` | Removed unused import |
| 13 | `scripts/.../matrix.py:3` | `I001` | Unsorted import block | Organized imports according to PEP 8 / isort rules |
| 14 | `scripts/.../probe.py:8` | `F401` | Unused import `typing.Any` | Removed unused import |
| 15 | `scripts/.../probe.py:102` | `BLE001` | Blind exception catch `except Exception` | Replaced with specific `PermissionError` and `OSError` |
| 16 | `scripts/.../probe.py:221` | `S110` | `try-except-pass` in scandir | Handled `FileNotFoundError` specifically; propagated security/budget |
| 17 | `scripts/.../probe.py:221` | `BLE001` | Blind exception catch `except Exception` | Removed broad catch; security and budget errors propagate |
| 18 | `scripts/.../probe.py:225` | `RUF059` | Unpacked variable `full_p` never used | Replaced with dummy `_full_p` |
| 19 | `scripts/.../probe.py:241` | `BLE001` | Blind exception catch `except Exception` | Replaced with specific `PermissionError` and `OSError` |
| 20 | `tests/..._unit.py:20` | `F401` | Unused import `TerminalVerdict` | Removed unused import |

**Verification Result:** Both scoped `ruff check scripts/... tests/...` and repo-wide `ruff check . --ignore EXE001` pass with **0 errors**.

---

## 3. Semantic & Security Hardening Details

### 3.1 Intermediate Symlink Non-Following Walk
- Added `_verify_path_components_non_symlink(rel_path)` in `probe.py`.
- For any probed target under `data_root` (e.g. `research/BTCUSDT/1m/year=2021/month=03/data.parquet`), every directory component from `data_root` down to the leaf is individually evaluated using non-following `os.lstat`.
- If any component is a symlink (`stat.S_ISLNK`), `counters.symlinks_encountered` is incremented and `ProbeSecurityError` is immediately raised, causing pipeline termination with `P2_PROTECTION_OR_IDENTITY_STOP`.
- Verified components are memoized in `_verified_non_symlink_components: set[str]` so shared parent components are not redundantly statted, preserving the `MAX_LSTAT = 100` budget.

### 3.2 Root Containment & Preflight Checks
- Replaced `os.path.exists()` preflight on `data_root` with non-following `os.lstat()`. If `data_root` is a symlink, execution immediately halts with `P2_PROTECTION_OR_IDENTITY_STOP`.
- Replaced naive string prefix comparisons with `os.path.commonpath([self.data_root, full_target]) == self.data_root`. Relative paths attempting mount escape (e.g. `../` or `/data-v2`) are rejected.
- Introduced `allow_custom_root: bool = False` parameter in `OwnerRootProbe`. Production runs reject any path other than `/root/workspace/project/Quant-agent/data`, while synthetic temporary test fixtures explicitly enable custom root mode.

### 3.3 Precise Exception Handling & Propagation
- Eliminated `except Exception` blocks in `probe.py`:
  - `verify_ancestors()`: specifically catches `FileNotFoundError` (marked `ENOENT`), `PermissionError` (marked `PERMISSION_DENIED`), and `OSError`. `ProbeSecurityError` and `ProbeBudgetExceededError` strictly re-raise.
  - `scan_selected_months()`: `PermissionError` on directory or parquet access sets `status = PERMISSION_DENIED` and is never collapsed into missing (`ENOENT`).
  - `scandir()` fallback: candidate entry names are screened for traversal (`..`) and protected patterns (`2026`, `forward`, `h39`). Malicious entries raise `ProbeSecurityError`. `ProbeBudgetExceededError` propagates out without suppression.

---

## 4. Test Suite Execution & Verification

All tests run in local WSL environment using synthetic temporary directories. Real market data was not accessed, statted, or modified.

- **Unit Tests (`tests/test_v06_p2_owner_root_metadata_unit.py`):** 12 passed
- **Adversarial Tests (`tests/test_v06_p2_owner_root_metadata_adversarial.py`):** 13 passed
  - `test_adv_01_symlink_ancestor_stops_pipeline`: Custom ancestor symlink halts pipeline.
  - `test_adv_02_intermediate_symlink_at_1m_detected`: Symlink at `1m` directory detected and rejected.
  - `test_adv_03_intermediate_symlink_at_year_detected`: Symlink at `year=2021` detected and rejected.
  - `test_adv_04_intermediate_symlink_at_month_detected`: Symlink at `month=03` detected and rejected.
  - `test_adv_05_symlink_leaf_parquet_stops_pipeline`: Symlink leaf `data.parquet` terminates with `P2_PROTECTION_OR_IDENTITY_STOP`.
  - `test_adv_06_malicious_alternate_name_traversal_propagates`: Malicious alternate filename with `../` raises `ProbeSecurityError`.
  - `test_adv_07_malicious_alternate_name_protected_pattern_propagates`: Protected pattern in alternate filename raises `ProbeSecurityError`.
  - `test_adv_08_permission_error_is_never_absent`: `PermissionError` marks `PERMISSION_DENIED`, never `ENOENT`.
  - `test_adv_09_cap_limit_raising_within_alternate_probe`: Budget cap during alternate probe propagates `ProbeBudgetExceededError`.
  - `test_adv_10_fake_root_escaping_rejected`: Relative path escape raises `ProbeSecurityError`.
  - `test_adv_11_production_mode_rejects_unauthorized_root`: Production mode without `allow_custom_root` strictly rejects foreign root.
  - `test_adv_12_non_symlink_preflight_on_data_root`: Symlink data root halts pipeline without using `os.path.exists()`.
  - `test_adv_13_cli_execution_end_to_end`: CLI end-to-end execution generates valid receipt, matrix, and report.
- **Full P2 Suite (`pytest -q tests/test_v06_p2_*.py`):** **46 passed in 0.84s**

---

## 5. Frozen Original Evidence Integrity

The three original 2026-10-10 evidence artifacts remain strictly unmodified:
1. `docs/strategy_research/g2_r3/p2_owner_root_metadata_r1/P2_OWNER_ROOT_EXACT_METADATA_REPORT.md` (UNTOUCHED)
2. `evidence/v0.6/b_line/p2_owner_root_metadata_r1/P2_OWNER_ROOT_EXACT_SCAN_RECEIPT.json` (UNTOUCHED)
3. `evidence/v0.6/b_line/p2_owner_root_metadata_r1/P2_SELECTED_SOURCE_TYPE_AND_PERMISSIONS_MATRIX.json` (UNTOUCHED)

---

## 6. Updated Script Hashes (SHA-256)

| Script Path | SHA-256 Digest |
| :--- | :--- |
| `scripts/strategy_research/p2_owner_root_metadata/__init__.py` | `7306b68fe706fe302c2304fb3a219a2f99b9d8e4e6d57ebd6ca8cf6def4d33b4` |
| `scripts/strategy_research/p2_owner_root_metadata/cli.py` | `58473e728ae7c4611f2fc9080d8889f9162902aa5d3e822ba572d84126a79712` |
| `scripts/strategy_research/p2_owner_root_metadata/config.py` | `0c7aa09e95eb50502e25dae0f94bb31507a1ceab82c7476269afc5b29ad452bc` |
| `scripts/strategy_research/p2_owner_root_metadata/matrix.py` | `4cb19f696334a4bac2c9f670b5230b201f27c0aa0204598501c616af9c26349b` |
| `scripts/strategy_research/p2_owner_root_metadata/probe.py` | `7fb40706228e3884f58297133029c29b431b7e0ff89ab33b32f65c8861f9bdd7` |

---

## 7. Conclusion & Governance Disposition

This single-shot repair successfully rectifies all CI quality issues and semantic fail-closed vulnerabilities identified by Controller dispatch `52830a73adf9e8c318da8efa8f10c6323a6292b8`.
- Terminal Verdict: `P2_VERIFIER_ONE_SHOT_REPAIR_DELIVERED_PENDING_CONTROLLER`
- Empirical source admission, P3 preregistration, P4 market-body reading, and live trading remain strictly blocked pending subsequent Controller authorization.
