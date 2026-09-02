from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import fmean, pstdev
from typing import Any

NEW_FEATURE_IDS = frozenset(
    {
        "PREMIUM_INDEX_LEVEL_1H",
        "PREMIUM_INDEX_Z_24H",
        "MARK_INDEX_BASIS_1H",
        "MARK_INDEX_BASIS_CHANGE_4H",
        "PERP_AGG_BUY_IMBALANCE_1H",
        "SPOT_AGG_BUY_IMBALANCE_1H",
        "SPOT_PERP_AGG_FLOW_SPREAD_1H",
        "PERP_AGG_SIGNED_NOTIONAL_Z_24H",
    }
)


@dataclass(frozen=True)
class OfficialHourlyInputs:
    timestamp_ms: int
    premium_close: float | None
    mark_close: float | None
    index_close: float | None
    perp_buy_notional: float | None
    perp_sell_notional: float | None
    spot_buy_notional: float | None
    spot_sell_notional: float | None


def _imbalance(buy: float | None, sell: float | None) -> float | None:
    if buy is None or sell is None or buy < 0 or sell < 0 or buy + sell <= 0:
        return None
    return (buy - sell) / (buy + sell)


def _rolling_z(values: list[float | None], window: int) -> list[float | None]:
    output: list[float | None] = [None] * len(values)
    for index in range(window - 1, len(values)):
        block = values[index - window + 1 : index + 1]
        if any(value is None for value in block):
            continue
        clean = [float(value) for value in block if value is not None]
        deviation = pstdev(clean)
        if deviation > 1e-15:
            output[index] = (clean[-1] - fmean(clean)) / deviation
    return output


def build_official_derivatives_features(
    rows: list[OfficialHourlyInputs],
) -> dict[str, list[float | None]]:
    premium = [row.premium_close for row in rows]
    basis = [
        None
        if row.mark_close is None or row.index_close is None or abs(row.index_close) <= 1e-15
        else (row.mark_close - row.index_close) / row.index_close
        for row in rows
    ]
    basis_change: list[float | None] = [None] * len(rows)
    for index in range(4, len(rows)):
        current_basis = basis[index]
        prior_basis = basis[index - 4]
        if current_basis is not None and prior_basis is not None:
            basis_change[index] = current_basis - prior_basis
    perp = [_imbalance(row.perp_buy_notional, row.perp_sell_notional) for row in rows]
    spot = [_imbalance(row.spot_buy_notional, row.spot_sell_notional) for row in rows]
    spread = [
        None if spot_value is None or perp_value is None else spot_value - perp_value
        for spot_value, perp_value in zip(spot, perp, strict=True)
    ]
    signed_notional = [
        None
        if row.perp_buy_notional is None or row.perp_sell_notional is None
        else row.perp_buy_notional - row.perp_sell_notional
        for row in rows
    ]
    output = {
        "PREMIUM_INDEX_LEVEL_1H": premium,
        "PREMIUM_INDEX_Z_24H": _rolling_z(premium, 24),
        "MARK_INDEX_BASIS_1H": basis,
        "MARK_INDEX_BASIS_CHANGE_4H": basis_change,
        "PERP_AGG_BUY_IMBALANCE_1H": perp,
        "SPOT_AGG_BUY_IMBALANCE_1H": spot,
        "SPOT_PERP_AGG_FLOW_SPREAD_1H": spread,
        "PERP_AGG_SIGNED_NOTIONAL_Z_24H": _rolling_z(signed_notional, 24),
    }
    if set(output) != NEW_FEATURE_IDS:
        raise RuntimeError("official derivatives feature family is incomplete")
    if any(
        value is not None and not math.isfinite(value)
        for values in output.values()
        for value in values
    ):
        raise ValueError("official derivatives feature output contains non-finite values")
    return output


def feature_availability_audit(
    features: dict[str, list[float | None]], rows: list[OfficialHourlyInputs]
) -> dict[str, Any]:
    return {
        "rows": len(rows),
        "feature_available_counts": {
            name: sum(value is not None for value in values)
            for name, values in sorted(features.items())
        },
        "feature_unavailable_counts": {
            name: sum(value is None for value in values)
            for name, values in sorted(features.items())
        },
        "synthetic_rows": 0,
        "missing_intervals_filled": 0,
    }
