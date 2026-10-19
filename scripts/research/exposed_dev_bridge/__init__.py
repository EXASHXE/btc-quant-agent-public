"""Manual, offline P3 inspection and explicit Owner development-scope gate."""

from pathlib import Path

from scripts.research.cross_venue import normalized_sources as _sources

TASK = "V065-P3-R3-REAL-SOURCE-ADAPTER-INTEGRATION-R1"
LABELS = (
    "SOURCE_NOT_ADMITTED", "PIT_UNKNOWN", "NO_ALPHA_ESTABLISHED",
    "COST_UNVALIDATED_REAL_FILL", "G2_ALPHA_NO_GO", "G4_TESTNET_NO_GO",
    "LIVE_NO_GO", "REAL_FUNDS_WRITE_NONE",
)


def checked_path(path: Path) -> Path:
    path = _sources.safe_path(path)
    for part in path.parts:
        lower = part.casefold()
        _sources.require(not any(lower == name or any(lower.startswith(name + sep) for sep in ("-", "_", "."))
                                 for name in ("account", "trade", "trades")), "PROTECTED_PATH", component=part)
    return path
