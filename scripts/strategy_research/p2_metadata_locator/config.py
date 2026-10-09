"""Configuration, hard execution caps, and domain models for P2 metadata locator."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

# Task & governance constants
TASK_ID = "V06_POST_P1_GEMINI_LONG_P2_METADATA_ROOT_AND_SOURCE_READINESS_R1"
CONTROLLER_DISPATCH_SHA = "858735e0ae81b1ca0ced8cfa4c2e9ee5d01532e2"
CONTROLLER_DISPATCH_BLOB = "c5684b4428321901bb21c087c3fd2d4b344b7fc7"
PROMPT_PINNED_SHA = "fd47ff5c6b534a6f66925e5f984fe630e9ff0702"
PROMPT_PINNED_BLOB = "94cd9f9ac61a79e7fd86bda4805513597907aa75"
CODE_START_SHA = "e0ff8c3473de4bfa3e66fe7928d42992a4d38a32"
REMOTE_BRANCH = "feature/v06-bline-postp1-gemini-p2-metadata-r1"

# Hard execution caps (immutable boundaries)
MAX_DEPTH = 5
MAX_DIR_ENTRIES = 1500
MAX_LSTAT = 2500
MAX_SELECTED_PARTITION_LSTAT = 36
MAX_WALL_CLOCK_SECONDS = 7200
MAX_SYMLINK_FOLLOW = 0
MAX_REAL_DATA_BODY_BYTES = 0
MAX_PROTECTED_BODY_OR_PARTITION_FILE_ACCESSES = 0
MAX_REMOTE_MARKET_CALLS = 0

# Allowed base roots for discovery
DEFAULT_CANDIDATE_ROOTS: list[str] = [
    "/root/workspace/project/quant-v0.6",
    "/root/workspace/project",
    "/root/data",
    "/data",
    "/mnt/data",
]

# Explicit forbidden roots / patterns (security & mount protection)
FORBIDDEN_ROOTS: set[str] = {
    "/",
    "/proc",
    "/sys",
    "/dev",
    "/run",
    "/etc",
    "/root",  # broad scanning of /root forbidden
    "/home",
    "/var",
    "/tmp",
}

# Forbidden directories within workspace/project
FORBIDDEN_PROJECT_SUBDIRS: set[str] = {
    "Quant-agent-sanitized",
    "postp1-sol61-opportunity-science-r1",  # parallel task
    "controller-review",
    "g1-engineering-preview",
    "g2-overnight-discovery-a",
    "g2-overnight-verifier-b",
    "g2-p1-alt-engine-gemini-a-r1",
    "g2-p1-alt-engine-sol-r1",
    "g2-p1-alt-final-independent-b-r1",
    "g2-perp-reconstruction-r2",
    "g2-r3-cost-aware-method-design",
    "g2-r3-data-readiness-sol61-r1",
    "g2-r3-science-sol-r1",
    "g2-r3-sol-science-gate-r1",
    "g2-r3-source-feasibility-r1",
    "g2-strategy-discovery",
    "g3-operational-readiness",
    "rc1-wp-a-operational",
    "rc1-wp-b-decision-quality",
    "rc1-wp-c-llm-approval",
    "rc1-wp-d-release-engineering",
    "rc2-tactical-successor",
    "rc2-tactical-successor-v06-foundation-r1",
    "resume",
    "resume-career-agent",
    "xiaohongshu-agent",
    "fund-agent",
}

# Protected holdout periods: [2026-02-01, 2026-08-01)
PROTECTED_YEAR = "2026"
PROTECTED_MONTHS = {"02", "03", "04", "05", "06", "07"}

# Six selected nonprotected candidate partitions
SELECTED_SAFE_MONTHS: list[str] = [
    "2021-03",
    "2021-04",
    "2023-03",
    "2023-04",
    "2025-03",
    "2025-04",
]

# Declared logical manifest partitions and checksums for BTC (from frozen data_manifest.json)
DECLARED_BTC_MANIFEST_PARTITIONS: dict[str, dict[str, Any]] = {
    "2021-03": {
        "relative_path": "1m/year=2021/month=03/data.parquet",
        "declared_sha256": "ec395168d9a2c4bdb73fc26843e726b92a58a0ffb167802a3e4a4a45d6178c1f",
        "period_role": "WARMUP",
    },
    "2021-04": {
        "relative_path": "1m/year=2021/month=04/data.parquet",
        "declared_sha256": "a94c0afe0a235c33d04abe048e51e0a3e5079922f05bd7c14a30d384db51fff1",
        "period_role": "DEVELOPMENT_PROPOSAL",
    },
    "2023-03": {
        "relative_path": "1m/year=2023/month=03/data.parquet",
        "declared_sha256": "368b1b7bb7cf5e8ae7f894548d08bbb63e93680c7f55f7bdb5f715d16f3b618a",
        "period_role": "WARMUP",
    },
    "2023-04": {
        "relative_path": "1m/year=2023/month=04/data.parquet",
        "declared_sha256": "1dfdf9e4c02c538fc738370f25047594144ff497bbb7e83976bfa1b014e08677",
        "period_role": "DEVELOPMENT_PROPOSAL",
    },
    "2025-03": {
        "relative_path": "1m/year=2025/month=03/data.parquet",
        "declared_sha256": "2d97729d1c4dd9bc644987cb93fdf06eb15f60dcb4a86f5219a84e45617c023c",
        "period_role": "WARMUP",
    },
    "2025-04": {
        "relative_path": "1m/year=2025/month=04/data.parquet",
        "declared_sha256": "5d6776bf5cc053e65bc11809101251c8cc348b886bbcd4b0245e9bfd07670239",
        "period_role": "DEVELOPMENT_PROPOSAL",
    },
}


class CoverageStatus(str, Enum):
    PRESENT_METADATA_ONLY = "PRESENT_METADATA_ONLY"
    MISSING_VERIFIED_SELECTED_PATH = "MISSING_VERIFIED_SELECTED_PATH"
    UNKNOWN_UNPROBED = "UNKNOWN_UNPROBED"
    PROTECTED_EXCLUDED = "PROTECTED_EXCLUDED"
    SCOPE_DENIED = "SCOPE_DENIED"


class RootCertainty(str, Enum):
    ROOT_CONFIRMED_FOR_SELECTED_METADATA = "ROOT_CONFIRMED_FOR_SELECTED_METADATA"
    ROOT_CANDIDATE_UNVERIFIED = "ROOT_CANDIDATE_UNVERIFIED"
    ROOT_UNKNOWN = "ROOT_UNKNOWN"


class TerminalVerdict(str, Enum):
    P2_SELECTED_LOCAL_ROOT_CONFIRMED_METADATA_ONLY = (
        "P2_SELECTED_LOCAL_ROOT_CONFIRMED_METADATA_ONLY"
    )
    P2_LOCAL_ROOT_CANDIDATE_UNVERIFIED = "P2_LOCAL_ROOT_CANDIDATE_UNVERIFIED"
    P2_LOCAL_ROOT_UNKNOWN_WITH_BOUNDED_NEGATIVE_EVIDENCE = (
        "P2_LOCAL_ROOT_UNKNOWN_WITH_BOUNDED_NEGATIVE_EVIDENCE"
    )
    P2_PROTECTION_OR_SCOPE_STOP = "P2_PROTECTION_OR_SCOPE_STOP"
    P2_BUDGET_EXHAUSTED_UNCONFIRMED = "P2_BUDGET_EXHAUSTED_UNCONFIRMED"
    BLOCKED_IDENTITY_OR_SCOPE = "BLOCKED_IDENTITY_OR_SCOPE"
    BLOCKED_NOT_PUSHED = "BLOCKED_NOT_PUSHED"


class SourceRole(str, Enum):
    KLINE_1M = "1m_kline"
    TRUE_MARK_1M = "true_1m_mark"
    FUNDING_RATES = "funding_rates"
    SYMBOL_FILTERS_FEES = "symbol_filters_fees"
    SPREAD_IMPACT_LICENCE = "spread_impact_licence"


@dataclass
class ScanCounters:
    depth_reached: int = 0
    dir_entries_scanned: int = 0
    lstat_calls: int = 0
    selected_partition_lstat_calls: int = 0
    symlinks_encountered: int = 0
    symlinks_followed: int = 0
    real_data_body_bytes_read: int = 0
    protected_body_or_partition_accesses: int = 0
    remote_market_calls: int = 0
    hidden_paths_skipped: int = 0
    forbidden_roots_rejected: int = 0
    protected_paths_excluded: int = 0
    permission_denied_entries: int = 0
    wall_clock_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_path_protected_holdout(path_str: str) -> bool:
    """Detect if path touches the sealed BTC holdout [2026-02-01, 2026-08-01)."""
    norm = os.path.normpath(path_str)
    parts = norm.split(os.sep)
    for part in parts:
        if part == "year=2026" or part == "2026":
            # Check if any protected month is in subsequent parts
            for m in PROTECTED_MONTHS:
                if f"month={m}" in parts or m in parts or f"2026-{m}" in norm:
                    return True
        for m in PROTECTED_MONTHS:
            if f"2026-{m}" in part or f"2026{m}" in part or f"year=2026/month={m}" in norm:
                return True
    return False
