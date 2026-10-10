"""Configuration, hard execution caps, and domain models for P2 owner exact root metadata verification."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

# Task & governance constants
TASK_ID = "V06_P2_OWNER_EXACT_WSL_ROOT_LSTAT_ONLY_VERIFICATION_R1"
CONTROLLER_DISPATCH_SHA = "b6120e2557d26fc822e740b7d889714a8c0124e6"
CONTROLLER_DISPATCH_DOC = (
    "reviews/v0.6/b_line/"
    "V06_P2_OWNER_SUPPLIED_EXACT_WSL_DATA_ROOT_BINDING_AND_METADATA_VERIFICATION_DISPATCH_R1.md"
)
PROMPT_PINNED_SHA = "7becda2c752e1f557e72a9a8e735a698ab1a680f"
PROMPT_PINNED_DOC = "prompts/v0.6/b_line/V06_P2_GEMINI_OWNER_EXACT_WSL_ROOT_LSTAT_ONLY_VERIFICATION_R1.md"
CODE_START_SHA = "1e12d6a6467d3bc39c0deedd97204604ac623f18"
REMOTE_BRANCH = "feature/v06-bline-p2-owner-exact-root-metadata-r1"

# Owner WSL Data Root and Derived Paths
DEFAULT_OWNER_WSL_DATA_ROOT = "/root/workspace/project/Quant-agent/data"
DEFAULT_BTC_PERP_SELECTED_ROOT = "/root/workspace/project/Quant-agent/data/research/BTCUSDT"

# Hard execution caps (immutable safety fences)
MAX_LSTAT = 100
MAX_SELECTED_DIR_LIST = 6
MAX_SELECTED_DIR_ENTRIES = 16
MAX_REAL_DATA_BODY_BYTES = 0
MAX_SYMLINK_FOLLOW = 0
MAX_PROTECTED_BODY_OR_PARTITION_FILE_ACCESSES = 0
MAX_REMOTE_MARKET_CALLS = 0

# Approved 6 Non-Protected Month Partitions (strictly 2021, 2023, 2025 - March and April)
APPROVED_MONTH_PARTITIONS: list[dict[str, str]] = [
    {"year": "2021", "month": "03", "label": "2021-03", "rel_dir": "research/BTCUSDT/1m/year=2021/month=03"},
    {"year": "2021", "month": "04", "label": "2021-04", "rel_dir": "research/BTCUSDT/1m/year=2021/month=04"},
    {"year": "2023", "month": "03", "label": "2023-03", "rel_dir": "research/BTCUSDT/1m/year=2023/month=03"},
    {"year": "2023", "month": "04", "label": "2023-04", "rel_dir": "research/BTCUSDT/1m/year=2023/month=04"},
    {"year": "2025", "month": "03", "label": "2025-03", "rel_dir": "research/BTCUSDT/1m/year=2025/month=03"},
    {"year": "2025", "month": "04", "label": "2025-04", "rel_dir": "research/BTCUSDT/1m/year=2025/month=04"},
]

# Additional Exact Parent / File Targets (Relative to Owner Data Root)
ADDITIONAL_TARGETS: list[dict[str, Any]] = [
    {
        "target_id": "btc_perp_data_manifest",
        "rel_path": "research/BTCUSDT/data_manifest.json",
        "expected_type": "file",
        "role": "btc_perp_manifest",
        "proves_minute_pit": False,
        "is_spot": False,
    },
    {
        "target_id": "btc_perp_funding_events",
        "rel_path": "research/BTCUSDT/funding_events.csv",
        "expected_type": "file",
        "role": "btc_perp_funding_events_csv",
        "proves_minute_pit": False,
        "is_spot": False,
    },
    {
        "target_id": "btc_perp_raw_mark_price_parent",
        "rel_path": "research/BTCUSDT/raw/mark_price",
        "expected_type": "dir",
        "role": "btc_perp_raw_mark_price_parent_only",
        "proves_minute_pit": False,
        "is_spot": False,
    },
    {
        "target_id": "btc_perp_raw_funding_parent",
        "rel_path": "research/BTCUSDT/raw/funding",
        "expected_type": "dir",
        "role": "btc_perp_raw_funding_parent_only",
        "proves_minute_pit": False,
        "is_spot": False,
    },
    {
        "target_id": "btc_perp_raw_klines_parent",
        "rel_path": "research/BTCUSDT/raw/klines",
        "expected_type": "dir",
        "role": "btc_perp_raw_klines_parent_only",
        "proves_minute_pit": False,
        "is_spot": False,
    },
    {
        "target_id": "btc_spot_data_manifest",
        "rel_path": "research/BTCUSDT_SPOT/data_manifest.json",
        "expected_type": "file",
        "role": "btc_spot_manifest",
        "proves_minute_pit": False,
        "is_spot": True,
    },
    {
        "target_id": "btc_spot_1m_parent",
        "rel_path": "research/BTCUSDT_SPOT/1m",
        "expected_type": "dir",
        "role": "btc_spot_1m_parent_only",
        "proves_minute_pit": False,
        "is_spot": True,
    },
    {
        "target_id": "cross_asset_ethusdt_1h",
        "rel_path": "research/cross_asset_1h/ETHUSDT.parquet",
        "expected_type": "file",
        "role": "cross_asset_hourly_eth",
        "proves_minute_pit": False,
        "is_spot": False,
    },
    {
        "target_id": "cross_asset_basket_manifest",
        "rel_path": "research/cross_asset_1h/basket_manifest.json",
        "expected_type": "file",
        "role": "cross_asset_hourly_basket_manifest",
        "proves_minute_pit": False,
        "is_spot": False,
    },
    {
        "target_id": "v0319_derivatives_hourly_inputs",
        "rel_path": "research/v0.3.19_official_derivatives/hourly_inputs.parquet",
        "expected_type": "file",
        "role": "legacy_v0319_hourly_inputs",
        "proves_minute_pit": False,
        "is_spot": False,
    },
    {
        "target_id": "v0319_derivatives_raw_manifest",
        "rel_path": "research/v0.3.19_official_derivatives/raw_data_manifest.json",
        "expected_type": "file",
        "role": "legacy_v0319_manifest",
        "proves_minute_pit": False,
        "is_spot": False,
    },
]

# Ancestor Chain Definition from /root to Quant-agent/data/research/BTCUSDT
ANCESTOR_CHAIN: list[str] = [
    "/root",
    "/root/workspace",
    "/root/workspace/project",
    "/root/workspace/project/Quant-agent",
    "/root/workspace/project/Quant-agent/data",
    "/root/workspace/project/Quant-agent/data/research",
    "/root/workspace/project/Quant-agent/data/research/BTCUSDT",
]

# Protected / Excluded Patterns
PROTECTED_PATTERNS: tuple[str, ...] = (
    "forward",
    "h39",
    "h39_validation",
    "year=2026",
    "2026-",
    "Quant-agent-sanitized",
)


class TerminalVerdict(str, Enum):
    P2_BTC_SELECTED_NONPROTECTED_FILES_LOCATED_METADATA_ONLY = (
        "P2_BTC_SELECTED_NONPROTECTED_FILES_LOCATED_METADATA_ONLY"
    )
    P2_OWNER_ROOT_PRESENT_BUT_SELECTED_FILES_INCOMPLETE = (
        "P2_OWNER_ROOT_PRESENT_BUT_SELECTED_FILES_INCOMPLETE"
    )
    P2_OWNER_ROOT_DECLARED_BUT_EXECUTOR_FILESYSTEM_UNAVAILABLE = (
        "P2_OWNER_ROOT_DECLARED_BUT_EXECUTOR_FILESYSTEM_UNAVAILABLE"
    )
    P2_OWNER_ROOT_NOT_PRESENT_AT_EXACT_PATH = "P2_OWNER_ROOT_NOT_PRESENT_AT_EXACT_PATH"
    P2_PROTECTION_OR_IDENTITY_STOP = "P2_PROTECTION_OR_IDENTITY_STOP"
    BLOCKED_NOT_PUSHED = "BLOCKED_NOT_PUSHED"


class FilePresenceStatus(str, Enum):
    PRESENT_METADATA_ONLY = "PRESENT_METADATA_ONLY"
    DIRECTORY_PRESENT_FILE_NAME_UNKNOWN = "DIRECTORY_PRESENT_FILE_NAME_UNKNOWN"
    ENOENT = "ENOENT"
    PROTECTED_EXCLUDED = "PROTECTED_EXCLUDED"
    SYMLINK_REJECTED = "SYMLINK_REJECTED"


def is_path_protected(path: str) -> bool:
    """Check if path falls under protected/excluded criteria."""
    normalized = path.replace("\\", "/").lower()
    for token in PROTECTED_PATTERNS:
        if token.lower() in normalized:
            return True
    return False


def is_path_traversal(path: str) -> bool:
    """Check if path contains directory traversal sequences."""
    parts = path.replace("\\", "/").split("/")
    return ".." in parts


@dataclass
class AncestorStat:
    path: str
    exists: bool = False
    is_symlink: bool = False
    is_dir: bool = False
    mode_octal: str | None = None
    dev: int | None = None
    ino: int | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MonthPartitionObservation:
    label: str
    year: str
    month: str
    rel_dir: str
    dir_exists: bool = False
    dir_is_symlink: bool = False
    file_name: str | None = None
    file_rel_path: str | None = None
    file_exists: bool = False
    file_is_symlink: bool = False
    file_is_regular: bool = False
    file_size_bytes: int | None = None
    file_mode_octal: str | None = None
    file_mtime: float | None = None
    status: str = FilePresenceStatus.ENOENT.value
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AdditionalTargetObservation:
    target_id: str
    rel_path: str
    expected_type: str
    role: str
    proves_minute_pit: bool
    is_spot: bool
    exists: bool = False
    is_symlink: bool = False
    is_regular: bool = False
    is_dir: bool = False
    size_bytes: int | None = None
    mode_octal: str | None = None
    status: str = FilePresenceStatus.ENOENT.value
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResourceCounters:
    lstat_calls: int = 0
    dir_list_calls: int = 0
    dir_entries_scanned: int = 0
    symlinks_encountered: int = 0
    symlinks_followed: int = 0
    real_data_body_bytes_read: int = 0
    protected_body_or_partition_accesses: int = 0
    remote_market_calls: int = 0
    parquet_opens: int = 0
    csv_opens: int = 0
    wall_clock_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
