from __future__ import annotations

import statistics
from collections.abc import Sequence
from typing import Any

from ..data.binance import BinancePublicClient
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
        evaluation_horizon_bars: int = 16,
        observation_type: str = "ACTIONABLE_TRIGGERED",
    ) -> int:
        d = assessment.directional
        entry_price = (
            d.entry_high
            if d.decision == DirectionalDecision.LONG
            else (d.entry_low if d.decision == DirectionalDecision.SHORT else assessment.snapshot.price.last_price)
        )
        return self.store.record_shadow_observation(
            timestamp_ms=assessment.snapshot.decision_time_ms,
            symbol=assessment.symbol,
            snapshot_hash=assessment.snapshot.snapshot_hash,
            agent_decision=str(d.decision),
            agent_setup=str(d.setup),
            entry_quality=str(d.entry_quality),
            reason_codes=list(d.reason_codes),
            reference_decision=reference_decision,
            reference_notes=reference_notes,
            policy_version=assessment.policy_version,
            config_hash=assessment.config_hash,
            entry_price=entry_price,
            stop_loss=d.stop_loss,
            tp1=d.take_profit_1,
            tp2=d.take_profit_2,
            direction=str(d.decision),
            evaluation_horizon_bars=evaluation_horizon_bars,
            observation_type=observation_type,
        )

    def resolve_pending_observations(
        self,
        client: BinancePublicClient,
        current_time_ms: int,
    ) -> dict[str, Any]:
        """Resolve previous eligible shadow observations using ONLY subsequently available closed candles."""
        pending = self.store.get_pending_shadow_records()
        if not pending:
            return {"resolved_count": 0, "pending_count": 0, "results": []}

        results = []
        for rec in pending:
            symbol = rec["symbol"]
            rec_id = rec["id"]
            timestamp_ms = rec["timestamp_ms"]
            entry_price = float(rec.get("entry_price") or 0.0)
            stop_loss = float(rec.get("stop_loss") or 0.0)
            tp1 = float(rec.get("tp1") or 0.0)
            tp2 = float(rec.get("tp2") or 0.0)
            dir_str = rec.get("direction", "WAIT")
            eval_bars = int(rec.get("evaluation_horizon_bars") or 16)
            eval_end_ms = rec.get("evaluation_end_ms")
            if not eval_end_ms:
                eval_end_ms = timestamp_ms + (eval_bars * 15 * 60 * 1000)

            if dir_str not in ("LONG", "SHORT") or entry_price <= 0:
                self.store.update_shadow_outcome(
                    rec_id,
                    future_mfe=0.0,
                    future_mae=0.0,
                    tp1_hit=False,
                    tp2_hit=False,
                    sl_hit=False,
                    time_to_target_ms=None,
                    time_to_stop_ms=None,
                    net_r=0.0,
                    regime_after="INELIGIBLE",
                )
                results.append({"id": rec_id, "symbol": symbol, "status": "INELIGIBLE"})
                continue

            fetch_end_ms = min(current_time_ms, eval_end_ms)
            if fetch_end_ms <= timestamp_ms:
                results.append({"id": rec_id, "symbol": symbol, "status": "PENDING_AWAITING_FUTURE_BARS"})
                continue

            # Historical Recovery (R2.1-06):
            # Resolve frozen evaluation windows using historical_klines when interval is not safely covered by 120 bars
            raw_candles: Sequence[Candle] = []
            if (current_time_ms - timestamp_ms) >= (100 * 15 * 60 * 1000) and hasattr(client, "historical_klines"):
                try:
                    raw_candles = client.historical_klines(symbol, "15m", timestamp_ms, fetch_end_ms)
                except Exception as exc:  # noqa: BLE001
                    results.append({"id": rec_id, "symbol": symbol, "status": f"HISTORICAL_FETCH_FAILED: {exc}"})
                    continue
            else:
                try:
                    raw_candles = client.klines(symbol, "15m", 120)
                except Exception as exc:  # noqa: BLE001
                    results.append({"id": rec_id, "symbol": symbol, "status": f"FETCH_FAILED: {exc}"})
                    continue

                # If raw_candles doesn't reach back to timestamp_ms, recover using historical_klines
                if raw_candles and raw_candles[0].open_time_ms > timestamp_ms and hasattr(client, "historical_klines"):
                    try:
                        raw_candles = client.historical_klines(symbol, "15m", timestamp_ms, fetch_end_ms)
                    except Exception as exc:  # noqa: BLE001
                        results.append({"id": rec_id, "symbol": symbol, "status": f"HISTORICAL_FETCH_FAILED: {exc}"})
                        continue

            # Only complete candles up to the frozen evaluation horizon
            subsequent_closed = [
                c for c in raw_candles
                if c.open_time_ms >= timestamp_ms and c.close_time_ms <= fetch_end_ms
            ]
            if not subsequent_closed:
                results.append({"id": rec_id, "symbol": symbol, "status": "PENDING_AWAITING_FUTURE_BARS"})
                continue

            direction = DirectionalDecision(dir_str)
            outcome = self.evaluate_forward_outcomes(
                shadow_id=rec_id,
                entry_price=entry_price,
                stop_loss=stop_loss,
                tp1=tp1,
                tp2=tp2,
                direction=direction,
                future_candles=subsequent_closed,
                persist=False,
            )

            is_terminal = outcome.get("is_terminal", False)
            is_matured = current_time_ms >= eval_end_ms

            if is_terminal or is_matured:
                regime_after = "RESOLVED_TERMINAL" if is_terminal else "RESOLVED_MATURED"
                self.store.update_shadow_outcome(
                    rec_id,
                    future_mfe=outcome["future_mfe"],
                    future_mae=outcome["future_mae"],
                    tp1_hit=outcome["tp1_hit"],
                    tp2_hit=outcome["tp2_hit"],
                    sl_hit=outcome["sl_hit"],
                    time_to_target_ms=outcome["time_to_target_ms"],
                    time_to_stop_ms=outcome["time_to_stop_ms"],
                    net_r=outcome["net_r"],
                    regime_after=regime_after,
                )
                results.append({"id": rec_id, "symbol": symbol, "status": "RESOLVED", "outcome": outcome})
            else:
                results.append({"id": rec_id, "symbol": symbol, "status": "PENDING_UNMATURED", "outcome": outcome})

        return {
            "resolved_count": sum(1 for r in results if r["status"] in ("RESOLVED", "INELIGIBLE")),
            "pending_count": sum(1 for r in results if r["status"] in ("PENDING_AWAITING_FUTURE_BARS", "PENDING_UNMATURED")),
            "results": results,
        }

    def get_status(self) -> dict[str, Any]:
        all_records = self.store.get_all_shadow_records()
        return compute_performance_metrics(all_records)

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
        persist: bool = True,
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

                bar_sl = candle.low <= stop_loss
                bar_tp1 = candle.high >= tp1
                bar_tp2 = candle.high >= tp2

                # Conservative STOP_FIRST policy for same-bar ambiguity:
                # Checking bar_sl first guarantees that if both bar_sl and bar_tp occurred on the same bar,
                # the trade stops out before target is credited.
                if not sl_hit and not tp1_hit:
                    if bar_sl:
                        sl_hit = True
                        time_to_stop_ms = candle.close_time_ms
                        break
                    elif bar_tp1:
                        tp1_hit = True
                        time_to_target_ms = candle.close_time_ms
                        if bar_tp2:
                            tp2_hit = True
                            break
                elif tp1_hit and not sl_hit:
                    if bar_sl:
                        sl_hit = True
                        time_to_stop_ms = candle.close_time_ms
                        break
                    elif bar_tp2:
                        tp2_hit = True
                        break
            elif is_short:
                favorable = entry_price - candle.low
                adverse = candle.high - entry_price
                mfe = max(mfe, favorable / risk_dist)
                mae = max(mae, adverse / risk_dist)

                bar_sl = candle.high >= stop_loss
                bar_tp1 = candle.low <= tp1
                bar_tp2 = candle.low <= tp2

                # Conservative STOP_FIRST policy for same-bar ambiguity:
                # Checking bar_sl first guarantees that if both bar_sl and bar_tp occurred on the same bar,
                # the trade stops out before target is credited.
                if not sl_hit and not tp1_hit:
                    if bar_sl:
                        sl_hit = True
                        time_to_stop_ms = candle.close_time_ms
                        break
                    elif bar_tp1:
                        tp1_hit = True
                        time_to_target_ms = candle.close_time_ms
                        if bar_tp2:
                            tp2_hit = True
                            break
                elif tp1_hit and not sl_hit:
                    if bar_sl:
                        sl_hit = True
                        time_to_stop_ms = candle.close_time_ms
                        break
                    elif bar_tp2:
                        tp2_hit = True
                        break

        net_r = 0.0
        if sl_hit and not tp1_hit:
            net_r = -1.0
        elif tp1_hit and not sl_hit:
            net_r = 1.0 + (1.0 if tp2_hit else 0.0)
        elif sl_hit and tp1_hit:
            net_r = 0.0

        is_terminal = sl_hit or tp2_hit

        if persist:
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
            "time_to_target_ms": time_to_target_ms,
            "time_to_stop_ms": time_to_stop_ms,
            "net_r": round(net_r, 2),
            "is_terminal": is_terminal,
        }


def compute_performance_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate forward performance metrics using only RESOLVED + ELIGIBLE actionable observations."""
    total_records = len(records)
    if not records:
        return {
            "total_records": 0,
            "actionable_records": 0,
            "resolved_actionable_count": 0,
            "pending_count": 0,
            "ineligible_count": 0,
            "tp1_hit_rate": 0.0,
            "tp2_hit_rate": 0.0,
            "sl_hit_rate": 0.0,
            "median_mfe": 0.0,
            "median_mae": 0.0,
            "median_net_r": 0.0,
            "signal_count": 0,
            "stratified_by_playbook": {},
        }

    # Actionable records: observation_type == ACTIONABLE_TRIGGERED
    actionable_records = [
        r for r in records
        if r.get("observation_type", "ACTIONABLE_TRIGGERED") == "ACTIONABLE_TRIGGERED"
    ]
    actionable_count = len(actionable_records)

    # Pending records: unresolved
    pending_count = sum(1 for r in records if not r.get("resolved"))

    # Ineligible records:
    # Any record that cannot be evaluated as an actionable trade:
    # regime_after == 'INELIGIBLE', observation_type == 'SETUP_ARMED',
    # direction not in ('LONG', 'SHORT'), or entry_price <= 0
    ineligible_count = sum(
        1 for r in records
        if r.get("regime_after") == "INELIGIBLE"
        or r.get("observation_type") == "SETUP_ARMED"
        or r.get("direction") not in ("LONG", "SHORT")
        or (float(r.get("entry_price") or 0.0) <= 0.0)
    )

    # RESOLVED + ELIGIBLE actionable observations:
    resolved_actionable = [
        r for r in actionable_records
        if bool(r.get("resolved"))
        and r.get("regime_after") != "INELIGIBLE"
        and r.get("direction") in ("LONG", "SHORT")
        and float(r.get("entry_price") or 0.0) > 0.0
    ]
    resolved_actionable_count = len(resolved_actionable)

    # Pending records MUST NOT enter hit-rate denominator.
    denom = resolved_actionable_count
    tp1_hits = sum(1 for r in resolved_actionable if r.get("tp1_hit"))
    tp2_hits = sum(1 for r in resolved_actionable if r.get("tp2_hit"))
    sl_hits = sum(1 for r in resolved_actionable if r.get("sl_hit"))

    tp1_hit_rate = round(tp1_hits / denom, 3) if denom > 0 else 0.0
    tp2_hit_rate = round(tp2_hits / denom, 3) if denom > 0 else 0.0
    sl_hit_rate = round(sl_hits / denom, 3) if denom > 0 else 0.0

    mfes = [float(r["future_mfe"]) for r in resolved_actionable if r.get("future_mfe") is not None]
    maes = [float(r["future_mae"]) for r in resolved_actionable if r.get("future_mae") is not None]
    net_rs = [float(r["net_r"]) for r in resolved_actionable if r.get("net_r") is not None]

    median_mfe = round(statistics.median(mfes), 2) if mfes else 0.0
    median_mae = round(statistics.median(maes), 2) if maes else 0.0
    median_net_r = round(statistics.median(net_rs), 2) if net_rs else 0.0

    stratified_playbook: dict[str, list[dict[str, Any]]] = {}
    for r in resolved_actionable:
        sb = r.get("agent_setup", "UNKNOWN")
        stratified_playbook.setdefault(sb, []).append(r)

    stratified_summary: dict[str, Any] = {}
    for playbook, items in stratified_playbook.items():
        n = len(items)
        stratified_summary[playbook] = {
            "count": n,
            "tp1_hit_rate": round(sum(1 for x in items if x.get("tp1_hit")) / n, 3) if n else 0.0,
            "tp2_hit_rate": round(sum(1 for x in items if x.get("tp2_hit")) / n, 3) if n else 0.0,
            "sl_hit_rate": round(sum(1 for x in items if x.get("sl_hit")) / n, 3) if n else 0.0,
            "median_net_r": round(statistics.median([float(x["net_r"]) for x in items if x.get("net_r") is not None]), 2) if items else 0.0,
        }

    return {
        "total_records": total_records,
        "actionable_records": actionable_count,
        "resolved_actionable_count": resolved_actionable_count,
        "pending_count": pending_count,
        "ineligible_count": ineligible_count,
        "tp1_hit_rate": tp1_hit_rate,
        "tp2_hit_rate": tp2_hit_rate,
        "sl_hit_rate": sl_hit_rate,
        "median_mfe": median_mfe,
        "median_mae": median_mae,
        "median_net_r": median_net_r,
        "signal_count": resolved_actionable_count,
        "stratified_by_playbook": stratified_summary,
    }


ShadowDecisionRecorder = ShadowEvaluationManager
