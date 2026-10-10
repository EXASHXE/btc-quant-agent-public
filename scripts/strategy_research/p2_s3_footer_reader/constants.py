"""Immutable constants for the P2 S3A independent single-file Parquet footer reader.

This module is completely standalone and does not import from S1 or S2 packages.
All historical file size references are pinned directly to the verified stat receipt
commit ``c6823dbc46249cac43aa10400aacbbe9f4542410`` with Controller S2 Joint L2
Finding F01 errata corrections applied.
"""

from __future__ import annotations

TASK_ID: str = "V06_P2_S3A_GEMINI_INDEPENDENT_ONEFILE_FOOTER_READER_BUILD_SYNTHETIC_R1"
CONTROLLER_DISPATCH_SHA: str = "e150be89bef2540a4aebe7b11e921dd25104fe16"
CONTROLLER_S2_JOINT_DECISION_SHA: str = "9782c68e9faa95988959ea8e7592aefe0b176067"
CODE_START_SHA: str = "e0ff8c3473de4bfa3e66fe7928d42992a4d38a32"
PROMPT_SHA: str = "559a56cef42e272c144c40876c2ba9e88f3ddeeb"
ORIGINAL_STAT_RECEIPT_SHA: str = "c6823dbc46249cac43aa10400aacbbe9f4542410"

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

# S3A terminal status string required by the Controller dispatch.
S3A_TERMINAL_STATUS: str = (
    "S3A_READER_BUILT_SYNTHETIC_VERIFIED_PENDING_INDEPENDENT_AUDIT"
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
    "heldout",
    "holdout",
    "a_line",
    "credentials",
    ".env",
)

# Verified historical metadata file sizes from c6823dbc46249cac43aa10400aacbbe9f4542410
# with Controller S2 Joint L2 Finding F01 errata corrections applied.
# NOTE: Only S3_SINGLE_PILOT_REL_PATH is admitted by the S3 single-file reader;
# the remaining entries are recorded strictly for immutable reference auditability.
VERIFIED_C6823DBC_FILE_SIZES_BYTES: dict[str, int] = {
    # Single admitted S3 pilot month:
    "research/BTCUSDT/1m/year=2021/month=03/data.parquet": 2_756_024,
    # Other 5 non-protected BTC 1m candidate months (NOT admitted in S3 single-file gate):
    "research/BTCUSDT/1m/year=2021/month=04/data.parquet": 2_492_430,
    "research/BTCUSDT/1m/year=2023/month=03/data.parquet": 2_672_321,
    "research/BTCUSDT/1m/year=2023/month=04/data.parquet": 2_075_555,
    "research/BTCUSDT/1m/year=2025/month=03/data.parquet": 1_970_619,
    "research/BTCUSDT/1m/year=2025/month=04/data.parquet": 1_942_082,
    # BTCUSDT metadata / funding files (NOT admitted in S3 single-file gate):
    "research/BTCUSDT/data_manifest.json": 45_234,
    "research/BTCUSDT/funding_events.csv": 219_066,
    # Auxiliary files corrected per Controller S2 Joint L2 Finding F01 (NOT admitted in S3):
    "research/cross_asset_1h/ETHUSDT.parquet": 2_907_000,
    "research/cross_asset_1h/basket_manifest.json": 56_012,
    "research/v0.3.19_official_derivatives/hourly_inputs.parquet": 3_101_084,
    "research/v0.3.19_official_derivatives/raw_data_manifest.json": 420_725,
}

__all__ = [
    "CODE_START_SHA",
    "CONTROLLER_DISPATCH_SHA",
    "CONTROLLER_S2_JOINT_DECISION_SHA",
    "ETH_SOL_1M_PERP_STATUS",
    "FORBIDDEN_CLI_OVERRIDE_FLAGS",
    "FORBIDDEN_ENV_OVERRIDE_VARS",
    "FORBIDDEN_OWNER_ROOT_PREFIXES",
    "HEADER_STATUS_NOT_VERIFIED",
    "IMMUTABLE_OWNER_DATA_ROOT",
    "MAX_ATTEMPTED_FS_CALLS",
    "MAX_FOOTER_READ_BYTES",
    "MAX_TOTAL_FILE_READ_BYTES",
    "MAX_TRAILER_READ_BYTES",
    "MIN_VALID_PARQUET_FILE_SIZE_BYTES",
    "ORIGINAL_STAT_RECEIPT_SHA",
    "PARQUET_HEADER_MAGIC_SIZE_BYTES",
    "PARQUET_MAGIC_BYTES",
    "PARQUET_TRAILER_SIZE_BYTES",
    "PROMPT_SHA",
    "PROTECTED_PATH_TOKENS",
    "S3A_TERMINAL_STATUS",
    "S3_SINGLE_PILOT_COMPONENTS",
    "S3_SINGLE_PILOT_EXPECTED_SIZE_BYTES",
    "S3_SINGLE_PILOT_REL_PATH",
    "TASK_ID",
    "TERMINATED_OLD_LOCATOR_CONTROLLER_SHA",
    "TERMINATED_OLD_LOCATOR_COUNTEREXAMPLE_SHA",
    "VERIFIED_C6823DBC_FILE_SIZES_BYTES",
]
