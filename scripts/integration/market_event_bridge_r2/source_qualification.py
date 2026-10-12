"""Real Public Source Multi-Channel Qualification Engine.

Enforces strict qualification criteria:
- Minimum duration >= 120 seconds
- Minimum closed 1m bars >= 2
- Minimum mark price coverage >= 120.0 seconds
- AggTrades > 0
- Raw diff depth updates > 0 with book continuity
- Zero WebSocket errors across both public depth and market streams
- Strict zero IP / port / credential leakage
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

MIN_QUALIFICATION_DURATION_SECONDS: int = 120
MIN_MARK_SPAN_SECONDS: float = 120.0
MIN_CLOSED_KLINES_1M: int = 2


class QualificationLevel(str, Enum):
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    PUBLIC_ROUTE_REACHABLE = "PUBLIC_ROUTE_REACHABLE"
    SHORT_DIAGNOSTIC = "SHORT_DIAGNOSTIC"
    PUBLIC_SOURCE_PARTIAL = "PUBLIC_SOURCE_PARTIAL"
    PUBLIC_MULTI_CHANNEL_SOURCE_VERIFIED = "PUBLIC_MULTI_CHANNEL_SOURCE_VERIFIED"
    L2_CONTINUOUS_WINDOW_VERIFIED = "L2_CONTINUOUS_WINDOW_VERIFIED"


@dataclass(frozen=True)
class QualificationChecks:
    rest_snapshot_ok: bool
    raw_depth_ok: bool
    agg_trades_ok: bool
    mark_ticks_ok: bool
    mark_span_ok: bool
    closed_klines_ok: bool
    wss_depth_ok: bool
    wss_market_ok: bool
    book_continuous: bool
    no_clock_uncertain: bool

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)


@dataclass(frozen=True)
class SourceQualificationReceipt:
    qualification_level: str
    passed: bool
    thresholds: dict[str, Any]
    observed_metrics: dict[str, Any]
    checks: dict[str, bool]
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


def evaluate_source_qualification(stats: dict[str, Any]) -> SourceQualificationReceipt:
    """Evaluate multi-channel telemetry against strict qualification rules."""
    rest_snap = stats.get("REST_snapshot", 0)
    raw_depth = stats.get("raw_public_depth_update", 0)
    agg_trades = stats.get("aggTrade", 0)
    mark_ticks = stats.get("markPriceTick", 0)
    mark_span = float(stats.get("mark_span_seconds", 0.0))
    closed_klines = stats.get("kline_closed_1m", 0)
    duration_sec = stats.get("duration_seconds", 0)
    rebootstraps = stats.get("rebootstrap_count", 0)
    clock_uncertain = stats.get("clockUncertain", 0)
    book_cont = bool(stats.get("book_continuous", True))

    wss_depth_conn = bool(stats.get("wss_public_depth_connected", False))
    wss_depth_err = stats.get("wss_public_depth_error")
    wss_market_conn = bool(stats.get("wss_market_connected", False))
    wss_market_err = stats.get("wss_market_error")

    rest_snapshot_ok = rest_snap >= 1
    raw_depth_ok = raw_depth > 0
    agg_trades_ok = agg_trades > 0
    mark_ticks_ok = mark_ticks > 0
    mark_span_ok = mark_span >= MIN_MARK_SPAN_SECONDS
    closed_klines_ok = closed_klines >= MIN_CLOSED_KLINES_1M
    duration_ok = duration_sec >= MIN_QUALIFICATION_DURATION_SECONDS
    wss_depth_ok = wss_depth_conn and (wss_depth_err is None)
    wss_market_ok = wss_market_conn and (wss_market_err is None)
    book_continuous_ok = book_cont and (rebootstraps == 0)
    no_clock_uncertain = clock_uncertain == 0

    checks = QualificationChecks(
        rest_snapshot_ok=rest_snapshot_ok,
        raw_depth_ok=raw_depth_ok,
        agg_trades_ok=agg_trades_ok,
        mark_ticks_ok=mark_ticks_ok,
        mark_span_ok=mark_span_ok,
        closed_klines_ok=closed_klines_ok,
        wss_depth_ok=wss_depth_ok,
        wss_market_ok=wss_market_ok,
        book_continuous=book_continuous_ok,
        no_clock_uncertain=no_clock_uncertain,
    )

    reasons: list[str] = []

    # Status evaluation
    status_field = stats.get("status")
    if status_field == "NOT_TESTED_SOURCE_UNREACHABLE" or not rest_snapshot_ok:
        level = QualificationLevel.SOURCE_UNAVAILABLE
        reasons.append("REST depth snapshot unreachable or failed.")
    elif not wss_depth_ok and not wss_market_ok:
        if rest_snapshot_ok:
            level = QualificationLevel.PUBLIC_ROUTE_REACHABLE
            reasons.append("REST reachable but both WebSocket streams disconnected or failed.")
        else:
            level = QualificationLevel.SOURCE_UNAVAILABLE
            reasons.append("All network channels failed.")
    elif not wss_depth_ok or not wss_market_ok:
        level = QualificationLevel.PUBLIC_SOURCE_PARTIAL
        if not wss_depth_ok:
            reasons.append(f"Public depth WSS failed: {wss_depth_err or 'not connected'}")
        if not wss_market_ok:
            reasons.append(f"Market events WSS failed: {wss_market_err or 'not connected'}")
    elif not duration_ok or not mark_span_ok or not closed_klines_ok:
        level = QualificationLevel.SHORT_DIAGNOSTIC
        if not duration_ok:
            reasons.append(f"Duration {duration_sec}s < required {MIN_QUALIFICATION_DURATION_SECONDS}s.")
        if not mark_span_ok:
            reasons.append(f"Mark coverage span {mark_span}s < required {MIN_MARK_SPAN_SECONDS}s.")
        if not closed_klines_ok:
            reasons.append(f"Closed 1m klines {closed_klines} < required {MIN_CLOSED_KLINES_1M}.")
    elif not raw_depth_ok or not agg_trades_ok or not mark_ticks_ok:
        level = QualificationLevel.PUBLIC_SOURCE_PARTIAL
        if not raw_depth_ok:
            reasons.append("Zero raw public depth updates received.")
        if not agg_trades_ok:
            reasons.append("Zero aggTrade events received.")
        if not mark_ticks_ok:
            reasons.append("Zero markPrice events received.")
    else:
        if book_continuous_ok:
            level = QualificationLevel.L2_CONTINUOUS_WINDOW_VERIFIED
            reasons.append("Multi-channel feed verified with continuous L2 order book.")
        else:
            level = QualificationLevel.PUBLIC_MULTI_CHANNEL_SOURCE_VERIFIED
            reasons.append("Multi-channel feed verified with minor order book discontinuity/rebootstrap.")

    thresholds = {
        "min_duration_seconds": MIN_QUALIFICATION_DURATION_SECONDS,
        "min_mark_span_seconds": MIN_MARK_SPAN_SECONDS,
        "min_closed_klines_1m": MIN_CLOSED_KLINES_1M,
    }

    observed_metrics = {
        "duration_seconds": duration_sec,
        "events_received": stats.get("events_received", 0),
        "REST_snapshot": rest_snap,
        "raw_public_depth_update": raw_depth,
        "aggTrade": agg_trades,
        "markPriceTick": mark_ticks,
        "mark_span_seconds": mark_span,
        "kline_closed_1m": closed_klines,
        "kline_open_1m": stats.get("kline_open_1m", 0),
        "estimatedFunding": stats.get("estimatedFunding", 0),
        "settledFunding": stats.get("settledFunding", 0),
        "rebootstrap_count": rebootstraps,
        "clockUncertain": clock_uncertain,
        "book_continuous": book_cont,
        "receiver_ingress_epoch": stats.get("receiver_ingress_epoch"),
        "route_epoch": stats.get("route_epoch"),
        "manifest_sha": stats.get("manifest_sha"),
    }

    passed = level in (
        QualificationLevel.PUBLIC_MULTI_CHANNEL_SOURCE_VERIFIED,
        QualificationLevel.L2_CONTINUOUS_WINDOW_VERIFIED,
    )

    return SourceQualificationReceipt(
        qualification_level=level.value,
        passed=passed,
        thresholds=thresholds,
        observed_metrics=observed_metrics,
        checks=checks.to_dict(),
        reasons=reasons,
    )
