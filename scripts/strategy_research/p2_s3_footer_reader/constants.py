"""Immutable constants for the P2 S3A independent single-file Parquet footer reader.

This module is completely standalone and does not import from S1 or S2 packages.
All historical file size references are pinned directly to the verified stat receipt
commit ``c6823dbc46249cac43aa10400aacbbe9f4542410`` (JSON SHA-256
``a3c9169dcbeb31edce492791ef253e42c580411cdb014337e8084229aaaaf3f2``) with both
Controller S2 Joint L2 Finding F01 and Controller S3A Hold R2 Finding F04
errata corrections applied.
"""

from __future__ import annotations

TASK_ID: str = "V06_P2_S3A_GEMINI_INDEPENDENT_ONEFILE_FOOTER_READER_BUILD_SYNTHETIC_R1"
R2_TASK_ID: str = (
    "V06_P2_S3A_GEMINI_ROOT_ALIAS_GRANT_BUDGET_AND_SOURCE_SIZE_BOUNDED_REPAIR_R2"
)
CONTROLLER_DISPATCH_SHA: str = "e150be89bef2540a4aebe7b11e921dd25104fe16"
R2_CONTROLLER_DISPATCH_SHA: str = "89c1caf07eebd3db81dc16314c3238c037e6fac3"
CONTROLLER_S2_JOINT_DECISION_SHA: str = "9782c68e9faa95988959ea8e7592aefe0b176067"
CODE_START_SHA: str = "e0ff8c3473de4bfa3e66fe7928d42992a4d38a32"
R2_EXACT_START_SHA: str = "30833953804bd965c80913ee6a3ecd4ae7457b40"
PROMPT_SHA: str = "559a56cef42e272c144c40876c2ba9e88f3ddeeb"
R2_PROMPT_SHA: str = "4227f46296b8f66fe33aebf8a7bdbacb6873dc2c"
ORIGINAL_STAT_RECEIPT_SHA: str = "c6823dbc46249cac43aa10400aacbbe9f4542410"
ORIGINAL_STAT_RECEIPT_JSON_SHA256: str = (
    "a3c9169dcbeb31edce492791ef253e42c580411cdb014337e8084229aaaaf3f2"
)

# Counterexample reference ONLY — terminated as unsafe; never imported or invoked.
TERMINATED_OLD_LOCATOR_COUNTEREXAMPLE_SHA: str = (
    "4a1fcc2871708f0e9e3a7c40036ecaab39ba99b8"
)
TERMINATED_OLD_LOCATOR_CONTROLLER_SHA: str = (
    "ca0b6ea62613e6981b6f818f37f45be8c1d74901"
)

# Physical owner WSL data root — strictly forbidden to stat/open/read in S3A.
IMMUTABLE_OWNER_DATA_ROOT: str = "/root/workspace/project/Quant-agent/data"

# Forbidden owner root prefixes (including case/mount aliases) blocked in S3A.
FORBIDDEN_OWNER_ROOT_PREFIXES: tuple[str, ...] = (
    "/root/workspace/project/Quant-agent/data",
    "/root/workspace/project/quant-agent/data",
    "//wsl.localhost/Ubuntu/root/workspace/project/Quant-agent/data",
    "z:/root/workspace/project/Quant-agent/data",
    "Z:/root/workspace/project/Quant-agent/data",
)

# Single non-protected pilot target file admitted by the S3A/S3B boundary design.
S3_SINGLE_PILOT_REL_PATH: str = (
    "research/BTCUSDT/1m/year=2021/month=03/data.parquet"
)
S3_SINGLE_PILOT_COMPONENTS: tuple[str, ...] = (
    "research",
    "BTCUSDT",
    "1m",
    "year=2021",
    "month=03",
    "data.parquet",
)
S3_SINGLE_PILOT_EXPECTED_SIZE_BYTES: int = 2_756_024

# Prospective raw 2021-03 alias string ONLY (not a read grant in S3A/R2).
PROSPECTIVE_RAW_2021_03_KLINE_REL_PATH: str = (
    "research/BTCUSDT/raw/klines/BTCUSDT-1m-2021-03.zip"
)

# Hard syscall and byte budgets for the S3 single-file footer reader.
MAX_ATTEMPTED_FS_CALLS: int = 100
MAX_TRAILER_READ_BYTES: int = 8
MAX_FOOTER_READ_BYTES: int = 65_536
MAX_TOTAL_FILE_READ_BYTES: int = MAX_TRAILER_READ_BYTES + MAX_FOOTER_READ_BYTES  # 65,544

# Parquet format constants: 4-byte header magic + >=1-byte footer + 4-byte len + 4-byte trailer magic.
PARQUET_MAGIC_BYTES: bytes = b"PAR1"
PARQUET_TRAILER_SIZE_BYTES: int = 8
PARQUET_HEADER_MAGIC_SIZE_BYTES: int = 4
MIN_VALID_PARQUET_FILE_SIZE_BYTES: int = (
    PARQUET_HEADER_MAGIC_SIZE_BYTES + 1 + PARQUET_TRAILER_SIZE_BYTES
)

# Explicit header verification status required on every output receipt because
# S3A reads ONLY the last <= 65,544 bytes (trailer + footer) and never offset 0..3.
HEADER_STATUS_NOT_VERIFIED: str = "FILE_HEADER_NOT_VERIFIED"

# Honest synthetic grant token label required by R2 Finding F02.
SYNTHETIC_GRANT_TOKEN_SEMANTICS: str = (
    "TEST_ONLY_INTEGRITY_CHECKSUM_NOT_AUTHORIZATION"
)

# Required fail-closed decision codes for R2 Findings F01 and F03.
HARNESS_ROOT_NOT_PROVEN_CODE: str = "S3A_HARNESS_ROOT_IDENTITY_NOT_PROVEN"
BUDGET_INSUFFICIENT_STOP_CODE: str = "BUDGET_INSUFFICIENT_STOP"

# S3A R1 and R2 terminal status strings required by the Controller dispatches.
S3A_TERMINAL_STATUS: str = (
    "S3A_READER_BUILT_SYNTHETIC_VERIFIED_PENDING_INDEPENDENT_AUDIT"
)
S3A_R2_TERMINAL_STATUS: str = (
    "S3A_R2_BOUNDED_SECURITY_REPAIR_DELIVERED_PENDING_CONTROLLER_SOL_AUDIT"
)

# ETH/SOL 1m perpetual status per Controller S2 Finding F02.
ETH_SOL_1M_PERP_STATUS: str = "UNKNOWN_NOT_VERIFIED_NOT_ADMITTED"

# Forbidden CLI / environment override tokens (no production CLI override permitted).
FORBIDDEN_CLI_OVERRIDE_FLAGS: tuple[str, ...] = (
    "--root",
    "--data-root",
    "--owner-root",
    "--allow-owner-root",
    "--bypass-grant",
    "--production",
)
FORBIDDEN_ENV_OVERRIDE_VARS: tuple[str, ...] = (
    "QUANT_AGENT_DATA_ROOT",
    "BTC_QUANT_DATA_ROOT",
    "S3_FOOTER_READER_ROOT_OVERRIDE",
    "S3_ALLOW_REAL_OWNER_DATA",
)

# Protected and out-of-scope path tokens that must always be rejected fail-closed.
PROTECTED_PATH_TOKENS: tuple[str, ...] = (
    "year=2026",
    "2026-02",
    "2026-03",
    "2026-04",
    "2026-05",
    "2026-06",
    "2026-07",
    "2026_02",
    "2026_03",
    "2026_04",
    "2026_05",
    "2026_06",
    "2026_07",
    "forward",
    "h39",
    "H39",
    "h40",
    "H40",
    "h41",
    "H41",
    "heldout",
    "holdout",
    "a_line",
    "credentials",
    ".env",
)

# Exact 6 non-protected BTC 1m monthly file sizes from c6823dbc46249cac43aa10400aacbbe9f4542410
# with R2 Finding F04 corrections applied to the 5 non-pilot months.
VERIFIED_C6823DBC_BTC_CANDIDATE_MONTH_SIZES_BYTES: dict[str, int] = {
    "research/BTCUSDT/1m/year=2021/month=03/data.parquet": 2_756_024,
    "research/BTCUSDT/1m/year=2021/month=04/data.parquet": 2_621_313,
    "research/BTCUSDT/1m/year=2023/month=03/data.parquet": 2_415_597,
    "research/BTCUSDT/1m/year=2023/month=04/data.parquet": 2_201_521,
    "research/BTCUSDT/1m/year=2025/month=03/data.parquet": 2_352_476,
    "research/BTCUSDT/1m/year=2025/month=04/data.parquet": 2_329_220,
}

# R1 -> R2 old-to-new errata mapping for the 5 non-pilot BTC 1m monthly files (R2 F04).
R1_TO_R2_BTC_SIZE_ERRATA_MAP: dict[str, dict[str, int]] = {
    "research/BTCUSDT/1m/year=2021/month=04/data.parquet": {
        "r1_wrong_bytes": 2_492_430,
        "r2_verified_c6823dbc_bytes": 2_621_313,
    },
    "research/BTCUSDT/1m/year=2023/month=03/data.parquet": {
        "r1_wrong_bytes": 2_672_321,
        "r2_verified_c6823dbc_bytes": 2_415_597,
    },
    "research/BTCUSDT/1m/year=2023/month=04/data.parquet": {
        "r1_wrong_bytes": 2_075_555,
        "r2_verified_c6823dbc_bytes": 2_201_521,
    },
    "research/BTCUSDT/1m/year=2025/month=03/data.parquet": {
        "r1_wrong_bytes": 1_970_619,
        "r2_verified_c6823dbc_bytes": 2_352_476,
    },
    "research/BTCUSDT/1m/year=2025/month=04/data.parquet": {
        "r1_wrong_bytes": 1_942_082,
        "r2_verified_c6823dbc_bytes": 2_329_220,
    },
}

# Complete verified file size dictionary from c6823dbc46249cac43aa10400aacbbe9f4542410.
# NOTE: Only S3_SINGLE_PILOT_REL_PATH (2021-03) is admitted by the S3 single-file reader;
# all other entries are recorded strictly for immutable reference auditability.
VERIFIED_C6823DBC_FILE_SIZES_BYTES: dict[str, int] = {
    **VERIFIED_C6823DBC_BTC_CANDIDATE_MONTH_SIZES_BYTES,
    # BTCUSDT & Spot metadata / funding files (NOT admitted in S3 single-file gate):
    "research/BTCUSDT/data_manifest.json": 45_234,
    "research/BTCUSDT/funding_events.csv": 219_066,
    "research/BTCUSDT_SPOT/data_manifest.json": 19_855,
    # Auxiliary files corrected per Controller S2 Joint L2 Finding F01 (NOT admitted in S3):
    "research/cross_asset_1h/ETHUSDT.parquet": 2_907_000,
    "research/cross_asset_1h/basket_manifest.json": 56_012,
    "research/v0.3.19_official_derivatives/hourly_inputs.parquet": 3_101_084,
    "research/v0.3.19_official_derivatives/raw_data_manifest.json": 420_725,
}

__all__ = [
    "BUDGET_INSUFFICIENT_STOP_CODE",
    "CODE_START_SHA",
    "CONTROLLER_DISPATCH_SHA",
    "CONTROLLER_S2_JOINT_DECISION_SHA",
    "ETH_SOL_1M_PERP_STATUS",
    "FORBIDDEN_CLI_OVERRIDE_FLAGS",
    "FORBIDDEN_ENV_OVERRIDE_VARS",
    "FORBIDDEN_OWNER_ROOT_PREFIXES",
    "HARNESS_ROOT_NOT_PROVEN_CODE",
    "HEADER_STATUS_NOT_VERIFIED",
    "IMMUTABLE_OWNER_DATA_ROOT",
    "MAX_ATTEMPTED_FS_CALLS",
    "MAX_FOOTER_READ_BYTES",
    "MAX_TOTAL_FILE_READ_BYTES",
    "MAX_TRAILER_READ_BYTES",
    "MIN_VALID_PARQUET_FILE_SIZE_BYTES",
    "ORIGINAL_STAT_RECEIPT_JSON_SHA256",
    "ORIGINAL_STAT_RECEIPT_SHA",
    "PARQUET_HEADER_MAGIC_SIZE_BYTES",
    "PARQUET_MAGIC_BYTES",
    "PARQUET_TRAILER_SIZE_BYTES",
    "PROMPT_SHA",
    "PROSPECTIVE_RAW_2021_03_KLINE_REL_PATH",
    "PROTECTED_PATH_TOKENS",
    "R1_TO_R2_BTC_SIZE_ERRATA_MAP",
    "R2_CONTROLLER_DISPATCH_SHA",
    "R2_EXACT_START_SHA",
    "R2_PROMPT_SHA",
    "R2_TASK_ID",
    "S3A_R2_TERMINAL_STATUS",
    "S3A_TERMINAL_STATUS",
    "S3_SINGLE_PILOT_COMPONENTS",
    "S3_SINGLE_PILOT_EXPECTED_SIZE_BYTES",
    "S3_SINGLE_PILOT_REL_PATH",
    "SYNTHETIC_GRANT_TOKEN_SEMANTICS",
    "TASK_ID",
    "TERMINATED_OLD_LOCATOR_CONTROLLER_SHA",
    "TERMINATED_OLD_LOCATOR_COUNTEREXAMPLE_SHA",
    "VERIFIED_C6823DBC_BTC_CANDIDATE_MONTH_SIZES_BYTES",
    "VERIFIED_C6823DBC_FILE_SIZES_BYTES",
]
