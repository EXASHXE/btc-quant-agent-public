"""Immutable constants and authorities for v0.6 P2 S2 Source Contract."""


# Task and Lineage Authorities
TASK_ID: str = "V06_P2_S2_GEMINI_LONG_SOURCE_CONTRACT_AND_SYNTHETIC_CAPABILITY_GATE_R1"
CONTROLLER_DISPATCH_SHA: str = "b176f4361cd97d1d89c3e25173b2c72a6af93ec4"
CODE_START_SHA: str = "e0ff8c3473de4bfa3e66fe7928d42992a4d38a32"
ORIGINAL_STAT_RECEIPT_SHA: str = "c6823dbc46249cac43aa10400aacbbe9f4542410"
TERMINATED_LOCATOR_COUNTEREXAMPLE_SHA: str = "4a1fcc2871708f0e9e3a7c40036ecaab39ba99b8"
CONTROLLER_TERMINATION_SHA: str = "ca0b6ea62613e6981b6f818f37f45be8c1d74901"
CONTROLLER_ADMISSION_DESIGN_SHA: str = "519b2e9ba2ca847e76ad9c0a7fbafcec5fcda158"
SOL_R4_SCIENCE_SHA: str = "5032259954e001635c97110c9c50e4a35a2c95b5"

# Owner Data Root (Fixed & Immutable in production)
IMMUTABLE_OWNER_WSL_DATA_ROOT: str = "/root/workspace/project/Quant-agent/data"
BTC_PERP_SUBROOT: str = "research/BTCUSDT"

# Exact six non-protected monthly candidate Parquet paths
# Proven as physical regular files by receipt c6823dbc46249cac43aa10400aacbbe9f4542410
SIX_NONPROTECTED_CANDIDATE_PATHS: tuple[str, ...] = (
    "research/BTCUSDT/1m/year=2021/month=03/data.parquet",
    "research/BTCUSDT/1m/year=2021/month=04/data.parquet",
    "research/BTCUSDT/1m/year=2023/month=03/data.parquet",
    "research/BTCUSDT/1m/year=2023/month=04/data.parquet",
    "research/BTCUSDT/1m/year=2025/month=03/data.parquet",
    "research/BTCUSDT/1m/year=2025/month=04/data.parquet",
)

# Immutable file sizes recorded in stat receipt c6823dbc46249cac43aa10400aacbbe9f4542410
RECORDED_METADATA_FILE_SIZES: dict[str, int] = {
    "research/BTCUSDT/1m/year=2021/month=03/data.parquet": 2756024,
    "research/BTCUSDT/1m/year=2021/month=04/data.parquet": 2621313,
    "research/BTCUSDT/1m/year=2023/month=03/data.parquet": 2415597,
    "research/BTCUSDT/1m/year=2023/month=04/data.parquet": 2201521,
    "research/BTCUSDT/1m/year=2025/month=03/data.parquet": 2352476,
    "research/BTCUSDT/1m/year=2025/month=04/data.parquet": 2329220,
    "research/BTCUSDT/data_manifest.json": 45234,
    "research/BTCUSDT/funding_events.csv": 219066,
    "research/BTCUSDT_SPOT/data_manifest.json": 19855,
    "research/cross_asset_1h/ETHUSDT.parquet": 3391374,
    "research/cross_asset_1h/basket_manifest.json": 3674,
    "research/v0.3.19_official_derivatives/hourly_inputs.parquet": 2058958,
    "research/v0.3.19_official_derivatives/raw_data_manifest.json": 4402,
}

# Companion metadata directories observed via lstat (mode 0o40755, size 4096)
METADATA_PARENT_DIRECTORIES: tuple[str, ...] = (
    "research/BTCUSDT/raw/klines",
    "research/BTCUSDT/raw/mark_price",
    "research/BTCUSDT/raw/funding",
    "research/BTCUSDT_SPOT/1m",
)

# Protected partition patterns (Strict Fail-Closed Deny)
# Any path matching these substrings or prefixes is strictly forbidden from any metadata/data access.
PROTECTED_PARTITION_PATTERNS: tuple[str, ...] = (
    "research/BTCUSDT/1m/year=2026",
    "year=2026",
    "2026-02",
    "2026-03",
    "2026-04",
    "2026-05",
    "2026-06",
    "2026-07",
    "data/forward",
    "forward/",
    "h39_validation",
    "h39",
    "Quant-agent-sanitized",
    "rc1-",
    "rc2-",
    ".env",
    ".git/config",
    "id_rsa",
    "credentials",
)

# Hard Policy Limits
DEFAULT_MAX_BYTES: int = 0  # Under THIS task, max_bytes MUST be 0
DEFAULT_MAX_SYSCALLS: int = 50
MAX_COMPONENT_DEPTH: int = 16

# Proposed Future Budgets (FOR SPECIFICATION / PROPOSAL ONLY, NOT ACTIVE GRANTS)
PROPOSED_FUTURE_L2_SCHEMA_MAX_BYTES: int = 65536      # 64 KB for footer metadata
PROPOSED_FUTURE_L3_QUALITY_MAX_BYTES: int = 10485760   # 10 MB bounded quality sample
PROPOSED_FUTURE_L4_MARKET_MAX_BYTES: int = 209715200  # 200 MB maximum bounded run
