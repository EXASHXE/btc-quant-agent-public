"""Versioned exploratory contract; freeze before reading trigger features."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

TASK = "V065-BLINE-R2-EXPANDED-OI-SAMPLE-JOIN-01"
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
PERIODS = {
    "A_R1_2026_REPRODUCTION": ["2026-04-01T00:00:00Z", "2026-09-01T00:00:00Z"],
    "B_EXISTING_R2_2026_EXTENSION": ["2026-04-01T00:00:00Z", "2026-10-01T00:00:00Z"],
    "C_EXPLORATORY_2021_2025": ["2021-01-01T00:00:00Z", "2026-01-01T00:00:00Z"],
}


def canonical(value) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def registration(input_binding: dict) -> dict:
    return {
        "schema": "bline-r2-expanded-oi.exploratory-registration.v1",
        "task": TASK,
        "version": 1,
        "labels": LABELS,
        "state": "EXPLORATORY_EVENT_TIME_ONLY_FROZEN_BEFORE_NEW_TRIGGER_COUNTS",
        "input_binding": input_binding,
        "instrument": ["binance", "BTCUSDT", "USD_M_PERPETUAL", "metrics", "5m"],
        "periods_half_open_utc": PERIODS,
        "period_roles": {
            "A": "Reproduce frozen R1 X/Z, then compare new native Z on identical frozen X.",
            "B": "Published existing R2 report only; September X absent from frozen R1. No reconstruction.",
            "C": "New exploratory extension; all hourly origins retained, missing/protected X never rebuilt.",
        },
        "frozen_formula": {
            "direction": "SHORT",
            "X": "log_return_4h <= -0.01",
            "Z": "log(sum_open_interest(t)/sum_open_interest(t-4h)) <= -0.02 AND sum_toptrader_long_short_ratio(t) >= 1.5",
            "thresholds": {"x_max": -0.01, "log_oi_max": -0.02, "position_ratio_min": 1.5},
            "joint": "X AND Z; paired baseline action masked on identical X/Z eligibility",
        },
        "native_fields": {
            "sum_open_interest": "base_open_interest; native underlying quantity, never sum_open_interest_value",
            "sum_toptrader_long_short_ratio": "top_position_long_short_ratio; aggregate top-trader long/short POSITION ratio, never count_toptrader_long_short_ratio (accounts)",
            "evidence": "Raw 8-column archive header and R2 quality.scan_archive positional mapping are checked locally. No provider publication/receiver timing inferred.",
        },
        "clock": {
            "origin": "UTC HH:01",
            "cutoff": "UTC HH:00",
            "content": "[native_label,native_label+5m] contained in [cutoff-10m,cutoff-5m]",
            "selection": "Latest label <= cutoff-10m; guard requires exactly cutoff-10m; no fallback from conflicting label",
            "predecessor": "Exact native label minus 4h; predecessor content uses cutoff minus 4h with identical guard",
            "duplicates": "Identical complete native values deduplicated; conflicting values at either label reject",
            "missing": "No fill, imputation, ratio substitution, timestamp shifting or source-family substitution",
            "vintage": "HTTP Last-Modified/ETag are archive vintage, never receiver first-known",
        },
        "eligibility": {
            "X": "Only frozen R1 HISTORICAL_FEATURE_ONLY binance/BTC X; x_complete, correct x_names, finite values, x_end_us < cutoff",
            "known_exclusion": ["2025-02-01T00:00:00Z", "2026-02-01T00:00:00Z"],
            "warmup": "Preserve R2 protected_feature_window 24h+120s boundary guard; no protected outcome payload access",
            "denominator": "All scheduled hourly origins; separate OI-only, native Z, X and paired X/Z masks",
        },
        "episodes": {
            "implementation": "Existing EventClusterer; first trigger anchors half-open [T0,T0+H), no sliding extension",
            "primary_horizon_hours": 8,
            "diagnostic_horizons_hours": [4, 8, 12, 24],
            "effective_weekly_blocks": "Distinct ISO weeks containing episode starts; count only, not IID or power proof",
            "feasibility_floor": {"paired_acted_origin_hours": 30, "weekly_blocks": 12},
            "additional_conservative_floor": "Also disclose >=30 non-overlapping episodes AND >=12 episode-start weeks, as in existing EventClusterer",
            "regime_proxies": {
                "2021": "2021_calendar",
                "2022": "2022_calendar",
                "2023": "2023_2024_calendar",
                "2024": "2023_2024_calendar",
                "2025": "2025_calendar",
            },
            "regime_interpretation": "Fixed calendar strata; no price/outcome-derived or fitted regime labels",
        },
        "no_outcome_scope": {
            "outcome_access": False,
            "forward_returns": False,
            "strategy_returns": False,
            "private_endpoints": False,
            "network_downloads": False,
            "protected_sqlite": False,
            "threshold_search_budget": 0,
            "horizon_search_budget": 0,
            "exit_search_budget": 0,
            "source_admitted": False,
            "executable": False,
            "receiver_first_known_pit": "UNKNOWN",
        },
    }


def freeze(output: Path, value: dict) -> str:
    """Immutable registration; an existing conflicting registration is an error."""
    path = output / "exploratory_registration.v1.json"
    data = canonical(value)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("REGISTRATION_ALREADY_FROZEN_DIFFERENT_INPUT_OR_CONTRACT")
    else:
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
    return digest(path)
