from __future__ import annotations

import statistics
from collections.abc import Sequence
from typing import Any

from ..domain import Candle
from .domain import DirectionalDecision, SymbolAssessment
from .state import MarketWatchStateStore


class ShadowEvaluationManager:
    """Manager for recording policy decisions and evaluating forward outcomes without lookahead."""

    def __init__(self, store: MarketWatchStateStore) -> None:
        self.store = store

    def record_decision(
        self,
        assessment: SymbolAssessment,
        reference_decision: str | None = None,
        reference_notes: str | None = None,
    ) -> int:
        return self.store.record_shadow_observation(
            timestamp_ms=assessment.snapshot.decision_time_ms,
            symbol=assessment.symbol,
            snapshot_hash=assessment.snapshot.snapshot_hash,
            agent_decision=str(assessment.directional.decision),
            agent_setup=str(assessment.directional.setup),
            entry_quality=str(assessment.directional.entry_quality),
            reason_codes=list(assessment.directional.reason_codes),
            reference_decision=reference_decision,
            reference_notes=reference_notes,
        )

    def evaluate_forward_outcomes(
        self,
        shadow_id: int,
        entry_price: float,
        stop_loss: float,
        tp1: float,
        tp2: float,
        direction: DirectionalDecision,
        future_candles: Sequence[Candle],
        regime_after: str = "UNKNOWN",
    ) -> dict[str, Any]:
        """Compute post-facto execution excursions strictly from subsequent candles."""
        if not future_candles or entry_price <= 0:
            return {}

        is_long = direction == DirectionalDecision.LONG
        is_short = direction == DirectionalDecision.SHORT

        tp1_hit = False
        tp2_hit = False
        sl_hit = False
        time_to_target_ms: int | None = None
        time_to_stop_ms: int | None = None

        mfe = 0.0
        mae = 0.0
        risk_dist = abs(entry_price - stop_loss) if stop_loss > 0 else 1.0

        for candle in future_candles:
            if is_long:
                favorable = candle.high - entry_price
                adverse = entry_price - candle.low
                mfe = max(mfe, favorable / risk_dist)
                mae = max(mae, adverse / risk_dist)

                if not sl_hit and candle.low <= stop_loss:
                    sl_hit = True
                    time_to_stop_ms = candle.close_time_ms
                if not tp1_hit and candle.high >= tp1:
                    tp1_hit = True
                    time_to_target_ms = candle.close_time_ms
                if not tp2_hit and candle.high >= tp2:
                    tp2_hit = True
            elif is_short:
                favorable = entry_price - candle.low
                adverse = candle.high - entry_price
                mfe = max(mfe, favorable / risk_dist)
                mae = max(mae, adverse / risk_dist)

                if not sl_hit and candle.high >= stop_loss:
                    sl_hit = True
                    time_to_stop_ms = candle.close_time_ms
                if not tp1_hit and candle.low <= tp1:
                    tp1_hit = True
                    time_to_target_ms = candle.close_time_ms
                if not tp2_hit and candle.low <= tp2:
                    tp2_hit = True

        net_r = 0.0
        if sl_hit and not tp1_hit:
            net_r = -1.0
        elif tp1_hit and not sl_hit:
            net_r = 1.0 + (1.0 if tp2_hit else 0.0)

        self.store.update_shadow_outcome(
            shadow_id,
            future_mfe=round(mfe, 2),
            future_mae=round(mae, 2),
            tp1_hit=tp1_hit,
            tp2_hit=tp2_hit,
            sl_hit=sl_hit,
            time_to_target_ms=time_to_target_ms,
            time_to_stop_ms=time_to_stop_ms,
            net_r=round(net_r, 2),
            regime_after=regime_after,
        )

        return {
            "future_mfe": round(mfe, 2),
            "future_mae": round(mae, 2),
            "tp1_hit": tp1_hit,
            "tp2_hit": tp2_hit,
            "sl_hit": sl_hit,
            "net_r": round(net_r, 2),
        }


def compute_performance_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate forward performance metrics stratified by playbook and setup."""
    if not records:
        return {
            "signal_count": 0,
            "tp1_hit_rate": 0.0,
            "sl_hit_rate": 0.0,
            "median_net_r": 0.0,
            "stratified": {},
        }

    total = len(records)
    tp1_hits = sum(1 for r in records if r.get("tp1_hit"))
    sl_hits = sum(1 for r in records if r.get("sl_hit"))
    mfes = [r["future_mfe"] for r in records if r.get("future_mfe") is not None]
    maes = [r["future_mae"] for r in records if r.get("future_mae") is not None]
    net_rs = [r["net_r"] for r in records if r.get("net_r") is not None]

    stratified_playbook: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        sb = r.get("agent_setup", "UNKNOWN")
        stratified_playbook.setdefault(sb, []).append(r)

    stratified_summary: dict[str, Any] = {}
    for playbook, items in stratified_playbook.items():
        n = len(items)
        stratified_summary[playbook] = {
            "count": n,
            "tp1_hit_rate": round(sum(1 for x in items if x.get("tp1_hit")) / n, 3) if n else 0.0,
            "sl_hit_rate": round(sum(1 for x in items if x.get("sl_hit")) / n, 3) if n else 0.0,
            "median_net_r": round(statistics.median([x["net_r"] for x in items if x.get("net_r") is not None]), 2) if items else 0.0,
        }

    return {
        "signal_count": total,
        "tp1_hit_rate": round(tp1_hits / total, 3) if total else 0.0,
        "sl_hit_rate": round(sl_hits / total, 3) if total else 0.0,
        "median_mfe": round(statistics.median(mfes), 2) if mfes else 0.0,
        "median_mae": round(statistics.median(maes), 2) if maes else 0.0,
        "median_net_r": round(statistics.median(net_rs), 2) if net_rs else 0.0,
        "stratified_by_playbook": stratified_summary,
    }
