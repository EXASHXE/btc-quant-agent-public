from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from ..domain import Candle, Regime
from ..indicators import adx, atr, ema
from ..structure import confirmed_pivots, structure_label
from .config import MarketWatchConfig, compute_market_watch_config_hash
from .domain import TACTICAL_POLICY_VERSION, MarketSnapshot

TREND_EVIDENCE_V2_SHADOW_SCHEMA_VERSION = "TREND_EVIDENCE_V2_SHADOW"
TREND_EVIDENCE_V2_SHADOW_AUTHORITY = "SHADOW_ONLY"

REQUIRED_TREND_EVIDENCE_V2_SHADOW_FIELDS: tuple[str, ...] = (
    "trend_age",
    "trend_persistence",
    "adx_slope",
    "ema_slope_acceleration",
    "structure_transition",
    "bars_since_breakout",
    "pullback_depth_atr",
    "oi_acceleration",
    "price_oi_divergence",
    "funding_delta",
    "basis_delta",
    "trend_transition_state",
)


class StructureTransitionState(StrEnum):
    CONTINUATION_UP = "CONTINUATION_UP"
    CONTINUATION_DOWN = "CONTINUATION_DOWN"
    RANGE_TO_TREND_UP = "RANGE_TO_TREND_UP"
    RANGE_TO_TREND_DOWN = "RANGE_TO_TREND_DOWN"
    TREND_TO_RANGE = "TREND_TO_RANGE"
    REVERSAL_UP_TO_DOWN = "REVERSAL_UP_TO_DOWN"
    REVERSAL_DOWN_TO_UP = "REVERSAL_DOWN_TO_UP"
    STABLE_RANGE = "STABLE_RANGE"


class TrendTransitionState(StrEnum):
    EMERGING_TREND = "EMERGING_TREND"
    MATURE_TREND = "MATURE_TREND"
    EXHAUSTING_TREND = "EXHAUSTING_TREND"
    PULLBACK_IN_TREND = "PULLBACK_IN_TREND"
    TRANSITION_TO_RANGE = "TRANSITION_TO_RANGE"
    RANGE_BOUND = "RANGE_BOUND"
    VOLATILITY_SHOCK = "VOLATILITY_SHOCK"


class TrendShadowCausalityError(ValueError):
    """Raised when future or unclosed inputs are passed to TrendEvidenceV2Shadow."""


@dataclass(frozen=True)
class TrendEvidenceV2Shadow:
    """Shadow-only trend transition and persistence evidence (TREND_EVIDENCE_V2_SHADOW).

    Authority is strictly SHADOW_ONLY. Must never alter active policy decisions,
    thresholds, weights, or frozen TacticalFeatureEvidenceV2 hashes.
    """

    schema_version: str
    authority: str
    shadow_evidence_id: str
    symbol: str
    decision_time_ms: int
    snapshot_hash: str
    feature_evidence_id: str
    policy_version: str
    config_hash: str

    # 12 contract-mandated shadow trend fields
    trend_age: int
    trend_persistence: float
    adx_slope: float
    ema_slope_acceleration: float
    structure_transition: str
    bars_since_breakout: int | None
    pullback_depth_atr: float
    oi_acceleration: float | None
    price_oi_divergence: float | None
    funding_delta: float | None
    basis_delta: float | None
    trend_transition_state: str

    # PIT provenance
    max_consumed_candle_close_ms: int
    pit_safe: bool = True

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)

    def canonical_json(self, include_id: bool = True) -> str:
        payload = self.to_dict()
        if not include_id:
            payload.pop("shadow_evidence_id", None)
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)

    def recompute_id(self) -> str:
        raw = self.canonical_json(include_id=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def validate_trend_evidence_v2_shadow(record: TrendEvidenceV2Shadow) -> None:
    """Validate schema, SHADOW_ONLY authority, finite values, PIT safety, and content hash."""
    if record.schema_version != TREND_EVIDENCE_V2_SHADOW_SCHEMA_VERSION:
        raise ValueError(f"Invalid schema_version: {record.schema_version}")
    if record.authority != TREND_EVIDENCE_V2_SHADOW_AUTHORITY:
        raise ValueError(f"TrendEvidenceV2Shadow must have SHADOW_ONLY authority, got {record.authority}")
    if not record.pit_safe or record.max_consumed_candle_close_ms > record.decision_time_ms:
        raise TrendShadowCausalityError(
            f"PIT violation: max_consumed_candle_close_ms={record.max_consumed_candle_close_ms} > decision_time_ms={record.decision_time_ms}"
        )
    if record.trend_age < 0:
        raise ValueError("trend_age must be non-negative")
    if not (0.0 <= record.trend_persistence <= 1.0):
        raise ValueError(f"trend_persistence out of [0, 1]: {record.trend_persistence}")
    for fname in (
        "trend_persistence",
        "adx_slope",
        "ema_slope_acceleration",
        "pullback_depth_atr",
        "oi_acceleration",
        "price_oi_divergence",
        "funding_delta",
        "basis_delta",
    ):
        val = getattr(record, fname)
        if val is not None and (isinstance(val, bool) or not math.isfinite(float(val))):
            raise ValueError(f"Non-finite value in {fname}: {val}")
    if record.structure_transition not in StructureTransitionState._value2member_map_:
        raise ValueError(f"Invalid structure_transition: {record.structure_transition}")
    if record.trend_transition_state not in TrendTransitionState._value2member_map_:
        raise ValueError(f"Invalid trend_transition_state: {record.trend_transition_state}")
    expected_id = record.recompute_id()
    if record.shadow_evidence_id != expected_id:
        raise ValueError(
            f"TrendEvidenceV2Shadow ID mismatch: stored={record.shadow_evidence_id}, expected={expected_id}"
        )


def _enforce_pit_candles(candles: Sequence[Candle], decision_time_ms: int, label: str) -> list[Candle]:
    valid: list[Candle] = []
    for c in candles:
        if not getattr(c, "closed", True):
            raise TrendShadowCausalityError(f"Unclosed candle passed to TrendEvidenceV2Shadow in {label}")
        if c.close_time_ms > decision_time_ms:
            raise TrendShadowCausalityError(
                f"Future candle in {label}: close_time_ms={c.close_time_ms} > decision_time_ms={decision_time_ms}"
            )
        if c.available_at_ms is not None and c.available_at_ms > decision_time_ms:
            raise TrendShadowCausalityError(
                f"Future candle availability in {label}: available_at_ms={c.available_at_ms} > decision_time_ms={decision_time_ms}"
            )
        valid.append(c)
    valid.sort(key=lambda bar: bar.close_time_ms)
    return valid


_1H_TREND_CACHE: dict[
    tuple[str, int, int, int, int, int, float, int, int],
    tuple[list[str], float, float, str],
] = {}


def _compute_1h_trend_features(
    symbol: str,
    c1h: Sequence[Candle],
    tc: Any,
) -> tuple[list[str], float, float, str]:
    key = (
        symbol,
        c1h[-1].close_time_ms,
        len(c1h),
        int(tc.ema_fast),
        int(tc.ema_mid),
        int(tc.adx_period),
        float(tc.adx_trend_min),
        int(tc.pivot_left),
        int(tc.pivot_right),
    )
    cached = _1H_TREND_CACHE.get(key)
    if cached is not None:
        return cached

    closes_1h = [b.close for b in c1h]
    highs_1h = [b.high for b in c1h]
    lows_1h = [b.low for b in c1h]
    ema_fast_1h = ema(closes_1h, tc.ema_fast)
    ema_mid_1h = ema(closes_1h, tc.ema_mid)
    adx_1h = adx(highs_1h, lows_1h, closes_1h, tc.adx_period)

    bar_states: list[str] = []
    adx_floor = tc.adx_trend_min * 0.85
    for idx in range(len(c1h)):
        c_val = closes_1h[idx]
        ef = ema_fast_1h[idx]
        em = ema_mid_1h[idx]
        ax = adx_1h[idx]
        if c_val > ef > em and ax >= adx_floor:
            bar_states.append("UP")
        elif c_val < ef < em and ax >= adx_floor:
            bar_states.append("DOWN")
        else:
            bar_states.append("NEUTRAL")

    persistence_window = min(12, len(c1h))
    recent_indices = range(len(c1h) - persistence_window, len(c1h))
    if ema_fast_1h[-1] >= ema_mid_1h[-1]:
        aligned_count = sum(
            1 for i in recent_indices if closes_1h[i] > ema_fast_1h[i] and ema_fast_1h[i] >= ema_mid_1h[i]
        )
    else:
        aligned_count = sum(
            1 for i in recent_indices if closes_1h[i] < ema_fast_1h[i] and ema_fast_1h[i] <= ema_mid_1h[i]
        )
    trend_persistence = round(aligned_count / float(persistence_window), 6)

    adx_lookback = min(3, len(adx_1h) - 1)
    adx_slope = round((adx_1h[-1] - adx_1h[-1 - adx_lookback]) / float(adx_lookback), 6)

    prior_1h_slice = c1h[:-4] if len(c1h) > 20 else c1h[:-1]
    prior_pivots = confirmed_pivots(prior_1h_slice[-min(160, len(prior_1h_slice)) :], tc.pivot_left, tc.pivot_right)
    prior_struct = structure_label(prior_pivots)

    res = (bar_states, trend_persistence, adx_slope, prior_struct)
    if len(_1H_TREND_CACHE) > 4096:
        _1H_TREND_CACHE.clear()
    _1H_TREND_CACHE[key] = res
    return res


def compute_trend_evidence_v2_shadow(
    *,
    snapshot: MarketSnapshot,
    closed_candles_15m: Sequence[Candle],
    closed_candles_1h: Sequence[Candle],
    closed_candles_4h: Sequence[Candle] = (),
    config: MarketWatchConfig | None = None,
    feature_evidence_id: str = "",
    prior_funding_rate: float | None = None,
    prior_basis_bps: float | None = None,
) -> TrendEvidenceV2Shadow:
    """Compute TREND_EVIDENCE_V2_SHADOW strictly from already-available PIT-safe raw inputs."""
    cfg = config or MarketWatchConfig()
    tc = cfg.thresholds
    decision_time_ms = snapshot.decision_time_ms

    c15 = _enforce_pit_candles(closed_candles_15m, decision_time_ms, "15m")
    c1h = _enforce_pit_candles(closed_candles_1h, decision_time_ms, "1h")
    c4h = _enforce_pit_candles(closed_candles_4h, decision_time_ms, "4h") if closed_candles_4h else []

    if len(c15) < 30 or len(c1h) < 30:
        raise ValueError("Insufficient closed candle history for TrendEvidenceV2Shadow (need >= 30 15m and 1h bars)")

    max_close_ms = max(
        c15[-1].close_time_ms,
        c1h[-1].close_time_ms,
        c4h[-1].close_time_ms if c4h else 0,
    )

    bar_states, trend_persistence, adx_slope, prior_struct = _compute_1h_trend_features(
        snapshot.symbol, c1h, tc
    )

    # 15m indicators from closed 15m bars
    closes_15m = [b.close for b in c15]
    highs_15m = [b.high for b in c15]
    lows_15m = [b.low for b in c15]
    ema_fast_15m = ema(closes_15m, tc.ema_fast)
    atr_15m = atr(highs_15m, lows_15m, closes_15m, tc.atr_period)

    # 1. trend_age & 2. trend_persistence
    current_bar_state = bar_states[-1]
    if snapshot.tf_1h.regime == Regime.TREND_UP:
        active_dir = "UP"
    elif snapshot.tf_1h.regime == Regime.TREND_DOWN:
        active_dir = "DOWN"
    elif current_bar_state in ("UP", "DOWN"):
        active_dir = current_bar_state
    else:
        active_dir = "NEUTRAL"

    trend_age = 0
    if active_dir in ("UP", "DOWN"):
        for st in reversed(bar_states):
            if st == active_dir:
                trend_age += 1
            else:
                break

    # 4. ema_slope_acceleration (15m EMA fast slope change normalized by 15m ATR)
    slope_lb = min(tc.slope_lookback, (len(ema_fast_15m) - 1) // 2)
    if slope_lb >= 1:
        slope_now = (ema_fast_15m[-1] - ema_fast_15m[-1 - slope_lb]) / float(slope_lb)
        slope_prev = (ema_fast_15m[-1 - slope_lb] - ema_fast_15m[-1 - 2 * slope_lb]) / float(slope_lb)
        norm_atr = max(atr_15m[-1], 1e-8)
        ema_slope_acceleration = round((slope_now - slope_prev) / norm_atr, 6)
    else:
        ema_slope_acceleration = 0.0

    # 5. structure_transition (comparing prior 1h structure vs current 1h structure)
    curr_struct = snapshot.tf_1h.structure

    if prior_struct == "HH_HL" and curr_struct == "HH_HL":
        structure_transition = StructureTransitionState.CONTINUATION_UP.value
    elif prior_struct == "LH_LL" and curr_struct == "LH_LL":
        structure_transition = StructureTransitionState.CONTINUATION_DOWN.value
    elif prior_struct == "HH_HL" and curr_struct == "LH_LL":
        structure_transition = StructureTransitionState.REVERSAL_UP_TO_DOWN.value
    elif prior_struct == "LH_LL" and curr_struct == "HH_HL":
        structure_transition = StructureTransitionState.REVERSAL_DOWN_TO_UP.value
    elif prior_struct not in ("HH_HL", "LH_LL") and curr_struct == "HH_HL":
        structure_transition = StructureTransitionState.RANGE_TO_TREND_UP.value
    elif prior_struct not in ("HH_HL", "LH_LL") and curr_struct == "LH_LL":
        structure_transition = StructureTransitionState.RANGE_TO_TREND_DOWN.value
    elif prior_struct in ("HH_HL", "LH_LL") and curr_struct not in ("HH_HL", "LH_LL"):
        structure_transition = StructureTransitionState.TREND_TO_RANGE.value
    else:
        structure_transition = StructureTransitionState.STABLE_RANGE.value

    # 6. bars_since_breakout (15m bars elapsed since confirmed breakout beyond 1h swing high/low or prior 20-bar channel)
    swing_high = snapshot.tf_1h.recent_swing_high
    swing_low = snapshot.tf_1h.recent_swing_low
    bars_since_breakout: int | None = None
    max_scan_bars = min(24, len(c15) - 20)
    for offset in range(max_scan_bars):
        idx = len(c15) - 1 - offset
        bar = c15[idx]
        prev_bar = c15[idx - 1]
        channel_window = c15[max(0, idx - 20) : idx]
        chan_high = max(b.high for b in channel_window) if channel_window else None
        chan_low = min(b.low for b in channel_window) if channel_window else None
        up_ref = swing_high if swing_high is not None else chan_high
        dn_ref = swing_low if swing_low is not None else chan_low
        broke_up = up_ref is not None and bar.close > up_ref and prev_bar.close <= up_ref
        broke_dn = dn_ref is not None and bar.close < dn_ref and prev_bar.close >= dn_ref
        if broke_up or broke_dn:
            bars_since_breakout = offset
            break

    # 7. pullback_depth_atr
    trail_15m = c15[-min(16, len(c15)) :]
    recent_high_15m = max(b.high for b in trail_15m)
    recent_low_15m = min(b.low for b in trail_15m)
    curr_atr_15m = max(snapshot.tf_15m.atr, 1e-8)
    if snapshot.tf_1h.ema_fast >= snapshot.tf_1h.ema_mid:
        pullback_depth_atr = round(max(0.0, (recent_high_15m - snapshot.tf_15m.close) / curr_atr_15m), 6)
    else:
        pullback_depth_atr = round(max(0.0, (snapshot.tf_15m.close - recent_low_15m) / curr_atr_15m), 6)

    # 8. oi_acceleration
    oi_1h = snapshot.derivatives.oi_1h_change
    oi_4h = snapshot.derivatives.oi_4h_change
    if oi_1h is not None and oi_4h is not None:
        oi_acceleration: float | None = round(float(oi_1h) - (float(oi_4h) / 4.0), 6)
    else:
        oi_acceleration = None

    # 9. price_oi_divergence
    ret_1h = snapshot.return_1h
    if ret_1h is not None and oi_1h is not None:
        price_oi_divergence: float | None = round(float(ret_1h) - float(oi_1h), 6)
    else:
        price_oi_divergence = None

    # 10. funding_delta
    curr_funding = snapshot.derivatives.funding_rate
    if curr_funding is not None and prior_funding_rate is not None:
        funding_delta: float | None = round(float(curr_funding) - float(prior_funding_rate), 8)
    else:
        funding_delta = None

    # 11. basis_delta (in bps)
    curr_basis_bps = snapshot.derivatives.basis_bps
    if curr_basis_bps is not None and prior_basis_bps is not None:
        basis_delta: float | None = round(float(curr_basis_bps) - float(prior_basis_bps), 6)
    else:
        basis_delta = None

    # 12. trend_transition_state
    signed_accel = ema_slope_acceleration if snapshot.tf_1h.ema_fast >= snapshot.tf_1h.ema_mid else -ema_slope_acceleration
    if (
        snapshot.tf_1h.regime == Regime.HIGH_VOLATILITY
        or snapshot.tf_15m.atr_percentile >= tc.high_vol_atr_percentile
    ):
        trend_transition_state = TrendTransitionState.VOLATILITY_SHOCK.value
    elif structure_transition in (
        StructureTransitionState.REVERSAL_UP_TO_DOWN.value,
        StructureTransitionState.REVERSAL_DOWN_TO_UP.value,
        StructureTransitionState.RANGE_TO_TREND_UP.value,
        StructureTransitionState.RANGE_TO_TREND_DOWN.value,
    ) or (1 <= trend_age <= 3 and adx_slope > 0.0):
        trend_transition_state = TrendTransitionState.EMERGING_TREND.value
    elif trend_age >= 3 and 0.5 <= pullback_depth_atr <= 2.5:
        trend_transition_state = TrendTransitionState.PULLBACK_IN_TREND.value
    elif trend_age >= 6 and (adx_slope < -0.5 or signed_accel < -0.15):
        trend_transition_state = TrendTransitionState.EXHAUSTING_TREND.value
    elif trend_age >= 4 and trend_persistence >= 0.6:
        trend_transition_state = TrendTransitionState.MATURE_TREND.value
    elif structure_transition == StructureTransitionState.TREND_TO_RANGE.value:
        trend_transition_state = TrendTransitionState.TRANSITION_TO_RANGE.value
    else:
        trend_transition_state = TrendTransitionState.RANGE_BOUND.value

    cfg_hash = compute_market_watch_config_hash(cfg)
    proto = TrendEvidenceV2Shadow(
        schema_version=TREND_EVIDENCE_V2_SHADOW_SCHEMA_VERSION,
        authority=TREND_EVIDENCE_V2_SHADOW_AUTHORITY,
        shadow_evidence_id="",
        symbol=snapshot.symbol,
        decision_time_ms=decision_time_ms,
        snapshot_hash=snapshot.snapshot_hash,
        feature_evidence_id=feature_evidence_id,
        policy_version=TACTICAL_POLICY_VERSION,
        config_hash=cfg_hash,
        trend_age=trend_age,
        trend_persistence=trend_persistence,
        adx_slope=adx_slope,
        ema_slope_acceleration=ema_slope_acceleration,
        structure_transition=structure_transition,
        bars_since_breakout=bars_since_breakout,
        pullback_depth_atr=pullback_depth_atr,
        oi_acceleration=oi_acceleration,
        price_oi_divergence=price_oi_divergence,
        funding_delta=funding_delta,
        basis_delta=basis_delta,
        trend_transition_state=trend_transition_state,
        max_consumed_candle_close_ms=max_close_ms,
        pit_safe=(max_close_ms <= decision_time_ms),
    )
    final_id = proto.recompute_id()
    record = TrendEvidenceV2Shadow(**{**proto.to_dict(), "shadow_evidence_id": final_id})
    validate_trend_evidence_v2_shadow(record)
    return record


def summarize_trend_evidence_v2_shadow(
    records: Sequence[TrendEvidenceV2Shadow],
    net_r_by_feature_id: Mapping[str, float | None] | None = None,
) -> dict[str, Any]:
    """Produce shadow-only diagnostic summary over TrendEvidenceV2Shadow records."""
    total = len(records)
    if total == 0:
        return {
            "schema_version": TREND_EVIDENCE_V2_SHADOW_SCHEMA_VERSION,
            "authority": TREND_EVIDENCE_V2_SHADOW_AUTHORITY,
            "active_policy_influence": "NONE",
            "sample_count": 0,
            "fields_present": list(REQUIRED_TREND_EVIDENCE_V2_SHADOW_FIELDS),
            "pit_safe_all": True,
            "by_trend_transition_state": {},
            "by_structure_transition": {},
            "feature_means": {},
        }

    net_r_map = dict(net_r_by_feature_id or {})
    by_state: dict[str, list[TrendEvidenceV2Shadow]] = {}
    by_struct: dict[str, list[TrendEvidenceV2Shadow]] = {}
    for rec in records:
        validate_trend_evidence_v2_shadow(rec)
        by_state.setdefault(rec.trend_transition_state, []).append(rec)
        by_struct.setdefault(rec.structure_transition, []).append(rec)

    def _group_stats(items: Sequence[TrendEvidenceV2Shadow]) -> dict[str, Any]:
        rs = [
            float(val)
            for r in items
            if (val := net_r_map.get(r.feature_evidence_id)) is not None
        ]
        return {
            "count": len(items),
            "share": round(len(items) / float(total), 6),
            "mean_trend_age": round(statistics.mean(r.trend_age for r in items), 4),
            "mean_trend_persistence": round(statistics.mean(r.trend_persistence for r in items), 6),
            "mean_adx_slope": round(statistics.mean(r.adx_slope for r in items), 6),
            "mean_pullback_depth_atr": round(statistics.mean(r.pullback_depth_atr for r in items), 6),
            "resolved_actionable_count": len(rs),
            "mean_net_R": round(statistics.mean(rs), 6) if rs else None,
            "median_net_R": round(statistics.median(rs), 6) if rs else None,
        }

    def _mean_opt(vals: Sequence[float | int | None]) -> float | None:
        clean = [float(v) for v in vals if v is not None]
        return round(statistics.mean(clean), 6) if clean else None

    return {
        "schema_version": TREND_EVIDENCE_V2_SHADOW_SCHEMA_VERSION,
        "authority": TREND_EVIDENCE_V2_SHADOW_AUTHORITY,
        "active_policy_influence": "NONE",
        "sample_count": total,
        "fields_present": list(REQUIRED_TREND_EVIDENCE_V2_SHADOW_FIELDS),
        "pit_safe_all": all(r.pit_safe and r.max_consumed_candle_close_ms <= r.decision_time_ms for r in records),
        "feature_means": {
            "trend_age": _mean_opt([r.trend_age for r in records]),
            "trend_persistence": _mean_opt([r.trend_persistence for r in records]),
            "adx_slope": _mean_opt([r.adx_slope for r in records]),
            "ema_slope_acceleration": _mean_opt([r.ema_slope_acceleration for r in records]),
            "bars_since_breakout": _mean_opt([r.bars_since_breakout for r in records]),
            "pullback_depth_atr": _mean_opt([r.pullback_depth_atr for r in records]),
            "oi_acceleration": _mean_opt([r.oi_acceleration for r in records]),
            "price_oi_divergence": _mean_opt([r.price_oi_divergence for r in records]),
            "funding_delta": _mean_opt([r.funding_delta for r in records]),
            "basis_delta": _mean_opt([r.basis_delta for r in records]),
        },
        "by_trend_transition_state": {k: _group_stats(v) for k, v in sorted(by_state.items())},
        "by_structure_transition": {k: _group_stats(v) for k, v in sorted(by_struct.items())},
    }
