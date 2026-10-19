"""Contracts and invariants for B-line R3 2022 native position gap investigation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

TASK = "V065-BLINE-R3-2022-NATIVE-POSITION-GAP-01"
TERMINAL_DECISION = "NATIVE_RATIO_2022_PUBLISHER_GAP"

LABELS = [
    "P3_ACCESS_SCOPE_HOLD",
    "SOURCE_NOT_ADMITTED",
    "PIT_UNKNOWN",
    "COST_INCOMPLETE",
    "UTILITY_NOT_IDENTIFIED",
    "NO_ALPHA_ESTABLISHED",
    "G2_ALPHA_NO_GO",
    "G4_TESTNET_NO_GO",
    "LIVE_NO_GO",
    "REAL_FUNDS_WRITE_NONE",
]

BINANCE_METRICS_SCHEMA = [
    "create_time",
    "symbol",
    "sum_open_interest",
    "sum_open_interest_value",
    "count_toptrader_long_short_ratio",
    "sum_toptrader_long_short_ratio",
    "count_long_short_ratio",
    "sum_taker_long_short_vol_ratio",
]

US = 1_000_000
MINUTE = 60 * US
FIVE_MINUTES = 5 * MINUTE
HOUR = 60 * MINUTE
FOUR_HOURS = 4 * HOUR

EXPECTED_HOURLY_ORIGINS_2022 = 8760
OBSERVED_RATIO_PRESENT_ORIGINS_2022 = 1115
OBSERVED_RATIO_BLANK_ORIGINS_2022 = 7645

SIMULATED_COVERAGE_UPPER_BOUND_LABEL = "SIMULATED_COVERAGE_UPPER_BOUND"

INVARIANTS = {
    "no_account_ratio_substitution": "Never substitute count_toptrader_long_short_ratio (accounts) for sum_toptrader_long_short_ratio (positions).",
    "no_notional_oi_substitution": "Never substitute sum_open_interest_value (notional) for sum_open_interest (base OI).",
    "no_cross_venue_substitution": "Never substitute OKX or Bybit open interest for native Binance open interest.",
    "no_zero_or_fill_inference": "Never infer zeros, forward fill, or interpolate missing position ratios.",
    "simulated_upper_bound_labeling": "Counterfactual denominator must be explicitly labeled SIMULATED_COVERAGE_UPPER_BOUND, never real observed data or trade opportunity.",
}


def canonical_json_bytes(value: dict | list) -> bytes:
    """Deterministic canonical JSON serialization."""
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode("utf-8")


def sha256_digest(path: Path) -> str:
    """Compute hex SHA256 digest of a file."""
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
