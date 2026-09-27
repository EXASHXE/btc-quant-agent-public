from __future__ import annotations

import statistics
from collections.abc import Sequence
from typing import Any

from ..data.binance import BinancePublicClient
from ..domain import Candle
from .config import MarketWatchConfig
from .domain import (
    DirectionalDecision,
    ShadowExecutionPathModel,
    ShadowFillStatus,
    ShadowPathResolution,
    SymbolAssessment,
)
from .state import MarketWatchStateStore


def _safe_fetch_klines(client: Any, symbol: str, interval: str, limit: int = 120) -> list[Candle]:
    if not hasattr(client, "klines"):
        return []
    try:
        res = client.klines(symbol, interval, limit)
        if isinstance(res, (list, tuple)):
            return [c for c in res if isinstance(c, Candle)]
    except Exception:  # noqa: BLE001
        return []
    return []


def _safe_fetch_historical(
    client: Any, symbol: str, interval: str, start_ms: int, end_ms: int
) -> list[Candle]:
    if not hasattr(client, "historical_klines"):
        return []
    try:
        res = client.historical_klines(symbol, interval, start_ms, end_ms)
        if isinstance(res, (list, tuple)):
            return [c for c in res if isinstance(c, Candle)]
    except Exception:  # noqa: BLE001
        return []
    return []


def resolve_shadow_fill(
    direction: DirectionalDecision | str,
    entry_zone_low: float,
    entry_zone_high: float,
    signal_time_ms: int,
    entry_window_end_ms: int,
    candles: Sequence[Candle],
) -> tuple[ShadowFillStatus, float | None, int | None]:
    """Authoritative fill resolution for shadow trades strictly on post-signal candles.

    Returns:
        tuple[ShadowFillStatus, fill_price, fill_time_ms]
    """
    dir_str = str(direction.value if hasattr(direction, "value") else direction).upper()
    if dir_str not in ("LONG", "SHORT") or entry_zone_high <= 0.0:
        return ShadowFillStatus.NO_FILL, None, None

    if entry_zone_low > entry_zone_high:
        entry_zone_low, entry_zone_high = entry_zone_high, entry_zone_low

    valid_candles = [c for c in candles if isinstance(c, Candle)]

    for candle in valid_candles:
        # Invariant: No candle closing before or at signal_time_ms may create a fill
        if candle.close_time_ms <= signal_time_ms:
            continue
        # Invariant: Entry candle must not start after entry window has expired
        if candle.open_time_ms >= entry_window_end_ms:
            break

        if dir_str == "LONG" and candle.low <= entry_zone_high and candle.high >= entry_zone_low:
            # Conservative fill price
            if candle.open >= entry_zone_high:
                fill_price = entry_zone_high
            elif candle.open <= entry_zone_low:
                fill_price = entry_zone_low
            else:
                fill_price = candle.open
            return ShadowFillStatus.FILLED, fill_price, candle.close_time_ms
        elif dir_str == "SHORT" and candle.high >= entry_zone_low and candle.low <= entry_zone_high:
            # Conservative fill price
            if candle.open <= entry_zone_low:
                fill_price = entry_zone_low
            elif candle.open >= entry_zone_high:
                fill_price = entry_zone_high
            else:
                fill_price = candle.open
            return ShadowFillStatus.FILLED, fill_price, candle.close_time_ms

    # If not filled: check if entry window has expired
    latest_time = valid_candles[-1].close_time_ms if valid_candles else signal_time_ms
    if isinstance(latest_time, (int, float)) and latest_time >= entry_window_end_ms:
        return ShadowFillStatus.NO_FILL, None, None
    return ShadowFillStatus.WAITING_FOR_FILL, None, None


def compute_trade_friction_r(
    fill_price: float,
    exit_price: float,
    initial_risk: float,
    config: MarketWatchConfig | None = None,
) -> tuple[float, float]:
    """Compute trade friction in dollars and R-multiple.

    Returns:
        tuple[friction_dollars, friction_r]
    """
    if config is None:
        return 0.0, 0.0

    if initial_risk <= 0.0:
        initial_risk = 1.0

    taker_fee_rate = 0.0005
    slippage_bps = 2.0
    th = getattr(config, "thresholds", None)
    if th is not None:
        taker_fee_rate = getattr(th, "taker_fee_rate", taker_fee_rate)
        slippage_bps = getattr(th, "slippage_bps_per_side", slippage_bps)
    else:
        taker_fee_rate = getattr(config, "taker_fee_rate", taker_fee_rate)
        slippage_bps = getattr(config, "slippage_bps_per_side", slippage_bps)

    per_side_friction = taker_fee_rate + (slippage_bps / 10_000.0)
    entry_friction = fill_price * per_side_friction
    exit_friction = exit_price * per_side_friction
    total_friction_dollars = entry_friction + exit_friction
    friction_r = total_friction_dollars / initial_risk
    return round(total_friction_dollars, 4), round(friction_r, 4)


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
        entry_window_bars: int = 4,
    ) -> int:
        d = assessment.directional
        signal_time_ms = assessment.snapshot.decision_time_ms
        entry_window_end_ms = signal_time_ms + (entry_window_bars * 15 * 60 * 1000)

        entry_low = d.entry_low if d.entry_low > 0.0 else assessment.snapshot.price.last_price
        entry_high = d.entry_high if d.entry_high > 0.0 else assessment.snapshot.price.last_price
        if entry_low > entry_high:
            entry_low, entry_high = entry_high, entry_low

        entry_price = (
            entry_high
            if d.decision == DirectionalDecision.LONG
            else (entry_low if d.decision == DirectionalDecision.SHORT else assessment.snapshot.price.last_price)
        )

        return self.store.record_shadow_observation(
            timestamp_ms=signal_time_ms,
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
            signal_identity=assessment.signal_identity,
            signal_time_ms=signal_time_ms,
            entry_zone_low=entry_low,
            entry_zone_high=entry_high,
            entry_window_bars=entry_window_bars,
            entry_window_end_ms=entry_window_end_ms,
            fill_status=ShadowFillStatus.WAITING_FOR_FILL.value,
        )

    def resolve_pending_observations(
        self,
        client: BinancePublicClient,
        current_time_ms: int,
        config: MarketWatchConfig | None = None,
    ) -> dict[str, Any]:
        """Resolve previous eligible shadow observations using ONLY subsequently available closed candles."""
        pending = self.store.get_pending_shadow_records()
        if not pending:
            return {"resolved_count": 0, "pending_count": 0, "results": []}

        results = []
        for rec in pending:
            symbol = rec["symbol"]
            rec_id = rec["id"]
            dir_str = rec.get("direction", "WAIT")
            obs_type = rec.get("observation_type", "ACTIONABLE_TRIGGERED")

            # Ineligible check
            if dir_str not in ("LONG", "SHORT") or obs_type != "ACTIONABLE_TRIGGERED":
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
                    gross_r=0.0,
                    friction_r=0.0,
                    regime_after="INELIGIBLE",
                    resolved=1,
                )
                results.append({"id": rec_id, "symbol": symbol, "status": "INELIGIBLE"})
                continue

            signal_time_ms = int(rec.get("signal_time_ms") or rec["timestamp_ms"])
            entry_low = float(rec.get("entry_zone_low") or rec.get("entry_price") or 0.0)
            entry_high = float(rec.get("entry_zone_high") or rec.get("entry_price") or 0.0)
            if entry_low <= 0.0 and entry_high <= 0.0:
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
                    gross_r=0.0,
                    friction_r=0.0,
                    regime_after="INELIGIBLE",
                    resolved=1,
                )
                results.append({"id": rec_id, "symbol": symbol, "status": "INELIGIBLE"})
                continue

            entry_bars = int(rec.get("entry_window_bars") or 4)
            entry_window_end_ms = int(
                rec.get("entry_window_end_ms") or (signal_time_ms + (entry_bars * 15 * 60 * 1000))
            )
            eval_bars = int(rec.get("evaluation_horizon_bars") or 16)
            eval_end_ms = int(rec.get("evaluation_end_ms") or (signal_time_ms + (eval_bars * 15 * 60 * 1000)))
            fill_status = rec.get("fill_status") or ShadowFillStatus.WAITING_FOR_FILL.value

            fetch_end_ms = min(current_time_ms, eval_end_ms)
            if fetch_end_ms <= signal_time_ms:
                results.append({"id": rec_id, "symbol": symbol, "status": "PENDING_AWAITING_FUTURE_BARS"})
                continue

            # Fetch primary 15m candles
            raw_candles: Sequence[Candle] = []
            if (current_time_ms - signal_time_ms) >= (100 * 15 * 60 * 1000):
                raw_candles = _safe_fetch_historical(client, symbol, "15m", signal_time_ms, eval_end_ms)
            else:
                raw_candles = _safe_fetch_klines(client, symbol, "15m", 120)
                if raw_candles and raw_candles[0].open_time_ms > signal_time_ms:
                    recovered = _safe_fetch_historical(client, symbol, "15m", signal_time_ms, eval_end_ms)
                    if recovered:
                        raw_candles = recovered

            # Stage 1: Resolve fill if WAITING_FOR_FILL
            if fill_status == ShadowFillStatus.WAITING_FOR_FILL.value:
                # Check candidate candles post-signal within entry window
                cand_for_fill = [
                    c for c in raw_candles
                    if c.close_time_ms > signal_time_ms and c.close_time_ms <= min(current_time_ms, entry_window_end_ms)
                ]

                # If first candidate candle started before signal_time_ms, try 1m refinement to avoid lookahead
                partial_1m: Sequence[Candle] = []
                if cand_for_fill and cand_for_fill[0].open_time_ms < signal_time_ms:
                    first_c = cand_for_fill[0]
                    fetched_1m = _safe_fetch_historical(client, symbol, "1m", signal_time_ms, first_c.close_time_ms)
                    partial_1m = [c for c in fetched_1m if getattr(c, "interval", "") == "1m"]

                fill_res = ShadowFillStatus.WAITING_FOR_FILL
                fill_p: float | None = None
                fill_t: int | None = None
                path_res = ShadowPathResolution.FIFTEEN_MINUTE_STOP_FIRST.value
                exec_model = ShadowExecutionPathModel.PARTIAL_FIRST_BAR_1M_THEN_15M.value

                if partial_1m:
                    fill_res, fill_p, fill_t = resolve_shadow_fill(
                        dir_str, entry_low, entry_high, signal_time_ms, entry_window_end_ms, partial_1m
                    )
                    if fill_res == ShadowFillStatus.FILLED:
                        path_res = ShadowPathResolution.ONE_MINUTE_CHRONOLOGICAL.value

                if fill_res != ShadowFillStatus.FILLED and cand_for_fill:
                    # Filter out partial first candle if 1m already proved it didn't fill after signal
                    start_bound = cand_for_fill[0].close_time_ms if partial_1m else signal_time_ms
                    cand_15m = [c for c in cand_for_fill if c.close_time_ms > start_bound or c.open_time_ms >= signal_time_ms]
                    if cand_15m:
                        fill_res, fill_p, fill_t = resolve_shadow_fill(
                            dir_str, entry_low, entry_high, signal_time_ms, entry_window_end_ms, cand_15m
                        )

                if fill_res == ShadowFillStatus.FILLED and fill_p is not None and fill_t is not None:
                    fill_status = ShadowFillStatus.FILLED.value
                    eval_end_ms = fill_t + (eval_bars * 15 * 60 * 1000)
                    self.store.update_shadow_fill(
                        rec_id,
                        fill_status=fill_status,
                        fill_time_ms=fill_t,
                        fill_price=fill_p,
                        evaluation_end_ms=eval_end_ms,
                        path_resolution=path_res,
                        execution_path_model=exec_model,
                    )
                    rec["fill_status"] = fill_status
                    rec["fill_price"] = fill_p
                    rec["fill_time_ms"] = fill_t
                    rec["entry_price"] = fill_p
                    rec["evaluation_end_ms"] = eval_end_ms
                elif fill_res == ShadowFillStatus.NO_FILL or current_time_ms >= entry_window_end_ms:
                    self.store.update_shadow_outcome(
                        rec_id,
                        future_mfe=None,
                        future_mae=None,
                        tp1_hit=False,
                        tp2_hit=False,
                        sl_hit=False,
                        time_to_target_ms=None,
                        time_to_stop_ms=None,
                        net_r=None,
                        gross_r=None,
                        friction_r=None,
                        regime_after="NO_FILL",
                        fill_status=ShadowFillStatus.NO_FILL.value,
                        resolved=1,
                    )
                    results.append({"id": rec_id, "symbol": symbol, "status": "NO_FILL"})
                    continue
                else:
                    results.append({"id": rec_id, "symbol": symbol, "status": "PENDING_WAITING_FOR_FILL"})
                    continue

            # Stage 2: Evaluate forward outcomes strictly post-fill
            fill_time_ms = int(rec.get("fill_time_ms") or signal_time_ms)
            fill_price = float(rec.get("fill_price") or rec.get("entry_price") or 0.0)
            eval_end_ms = int(rec.get("evaluation_end_ms") or (fill_time_ms + (eval_bars * 15 * 60 * 1000)))
            stop_loss = float(rec.get("stop_loss") or 0.0)
            tp1 = float(rec.get("tp1") or 0.0)
            tp2 = float(rec.get("tp2") or 0.0)

            subsequent_closed = [
                c for c in raw_candles
                if c.close_time_ms > fill_time_ms and c.close_time_ms <= fetch_end_ms
            ]
            if not subsequent_closed:
                results.append({"id": rec_id, "symbol": symbol, "status": "PENDING_AWAITING_FUTURE_BARS"})
                continue

            direction = DirectionalDecision(dir_str)
            outcome = self.evaluate_forward_outcomes(
                shadow_id=rec_id,
                entry_price=fill_price,
                stop_loss=stop_loss,
                tp1=tp1,
                tp2=tp2,
                direction=direction,
                future_candles=subsequent_closed,
                persist=False,
                config=config,
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
                    gross_r=outcome.get("gross_r"),
                    friction_r=outcome.get("friction_r"),
                    net_r=outcome["net_r"],
                    path_resolution=outcome.get("path_resolution"),
                    regime_after=regime_after,
                    resolved=1,
                )
                results.append({"id": rec_id, "symbol": symbol, "status": "RESOLVED", "outcome": outcome})
            else:
                results.append({"id": rec_id, "symbol": symbol, "status": "PENDING_UNMATURED", "outcome": outcome})

        return {
            "resolved_count": sum(1 for r in results if r["status"] in ("RESOLVED", "NO_FILL", "INELIGIBLE")),
            "pending_count": sum(
                1 for r in results
                if r["status"] in ("PENDING_AWAITING_FUTURE_BARS", "PENDING_UNMATURED", "PENDING_WAITING_FOR_FILL")
            ),
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
        config: MarketWatchConfig | None = None,
        intrabar_1m_candles: Sequence[Candle] | None = None,
    ) -> dict[str, Any]:
        """Compute post-facto execution excursions strictly from subsequent candles."""
        if not future_candles or entry_price <= 0.0:
            return {}

        is_long = direction == DirectionalDecision.LONG
        is_short = direction == DirectionalDecision.SHORT
        risk_dist = abs(entry_price - stop_loss) if (stop_loss > 0.0 and entry_price != stop_loss) else 1.0

        tp1_hit = False
        tp2_hit = False
        sl_hit = False
        time_to_target_ms: int | None = None
        time_to_stop_ms: int | None = None
        mfe = 0.0
        mae = 0.0
        path_resolution = ShadowPathResolution.FIFTEEN_MINUTE_STOP_FIRST.value

        for candle in future_candles:
            if is_long:
                favorable = candle.high - entry_price
                adverse = entry_price - candle.low
                bar_sl = candle.low <= stop_loss
                bar_tp1 = candle.high >= tp1
                bar_tp2 = candle.high >= tp2
            elif is_short:
                favorable = entry_price - candle.low
                adverse = candle.high - entry_price
                bar_sl = candle.high >= stop_loss
                bar_tp1 = candle.low <= tp1
                bar_tp2 = candle.low <= tp2
            else:
                favorable = 0.0
                adverse = 0.0
                bar_sl = False
                bar_tp1 = False
                bar_tp2 = False

            mfe = max(mfe, favorable / risk_dist)
            mae = max(mae, adverse / risk_dist)

            # Check same-bar ambiguity (both SL and TP touched on same candle)
            if bar_sl and (bar_tp1 or bar_tp2):
                disambiguated = False
                if intrabar_1m_candles:
                    span_1m = [
                        c for c in intrabar_1m_candles
                        if c.close_time_ms > candle.open_time_ms and c.close_time_ms <= candle.close_time_ms
                    ]
                    if span_1m:
                        for c1 in span_1m:
                            c1_sl = (c1.low <= stop_loss) if is_long else (c1.high >= stop_loss)
                            c1_tp = (c1.high >= tp1) if is_long else (c1.low <= tp1)
                            if c1_tp and not c1_sl:
                                tp1_hit = True
                                time_to_target_ms = c1.close_time_ms
                                path_resolution = ShadowPathResolution.ONE_MINUTE_CHRONOLOGICAL.value
                                disambiguated = True
                                c1_tp2 = (c1.high >= tp2) if is_long else (c1.low <= tp2)
                                if c1_tp2:
                                    tp2_hit = True
                                break
                            elif c1_sl and not c1_tp:
                                sl_hit = True
                                time_to_stop_ms = c1.close_time_ms
                                path_resolution = ShadowPathResolution.ONE_MINUTE_CHRONOLOGICAL.value
                                disambiguated = True
                                break
                if disambiguated:
                    if sl_hit or tp2_hit:
                        break
                    continue

                # Fallback to STOP_FIRST
                sl_hit = True
                time_to_stop_ms = candle.close_time_ms
                path_resolution = ShadowPathResolution.FIFTEEN_MINUTE_STOP_FIRST.value
                break

            if bar_sl:
                sl_hit = True
                time_to_stop_ms = candle.close_time_ms
                break
            elif bar_tp1:
                if not tp1_hit:
                    tp1_hit = True
                    time_to_target_ms = candle.close_time_ms
                if bar_tp2:
                    tp2_hit = True
                    break

        if sl_hit:
            exit_price = stop_loss
        elif tp2_hit:
            exit_price = tp2
        elif tp1_hit:
            exit_price = tp1
        else:
            exit_price = future_candles[-1].close

        if is_long:
            gross_r = (exit_price - entry_price) / risk_dist
        elif is_short:
            gross_r = (entry_price - exit_price) / risk_dist
        else:
            gross_r = 0.0

        _friction_dollars, friction_r = compute_trade_friction_r(entry_price, exit_price, risk_dist, config)
        net_r = gross_r - friction_r
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
                gross_r=round(gross_r, 4),
                friction_r=round(friction_r, 4),
                net_r=round(net_r, 4),
                path_resolution=path_resolution,
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
            "gross_r": round(gross_r, 4),
            "friction_r": round(friction_r, 4),
            "net_r": round(net_r, 4),
            "path_resolution": path_resolution,
            "is_terminal": is_terminal,
        }


def compute_performance_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate forward performance metrics using only RESOLVED + ELIGIBLE actionable observations."""
    total_records = len(records)
    if not records:
        return {
            "total_records": 0,
            "setup_armed_records": 0,
            "actionable_records": 0,
            "filled_actionable_count": 0,
            "no_fill_count": 0,
            "resolved_actionable_count": 0,
            "pending_actionable_count": 0,
            "pending_count": 0,
            "ineligible_count": 0,
            "tp1_hit_rate": 0.0,
            "tp2_hit_rate": 0.0,
            "sl_hit_rate": 0.0,
            "median_mfe": 0.0,
            "median_mae": 0.0,
            "median_gross_r": 0.0,
            "median_friction_r": 0.0,
            "median_net_r": 0.0,
            "signal_count": 0,
            "stratified_by_playbook": {},
            "stratified_by_direction": {},
            "stratified_by_entry_quality": {},
        }

    setup_armed_records = sum(
        1 for r in records
        if r.get("observation_type") == "SETUP_ARMED"
    )

    actionable_records = [
        r for r in records
        if r.get("observation_type", "ACTIONABLE_TRIGGERED") == "ACTIONABLE_TRIGGERED"
    ]
    actionable_count = len(actionable_records)

    pending_count = sum(1 for r in records if not r.get("resolved"))

    no_fill_count = sum(
        1 for r in actionable_records
        if r.get("fill_status") == ShadowFillStatus.NO_FILL.value or r.get("regime_after") == "NO_FILL"
    )

    # Ineligible / Legacy records:
    # Any record with missing R2.2 fields (fill_status is None, signal_time_ms is None),
    # direction not in ('LONG', 'SHORT'), entry_price <= 0, or explicit INELIGIBLE/LEGACY regime
    ineligible_count = sum(
        1 for r in records
        if r.get("regime_after") in ("INELIGIBLE", "LEGACY")
        or r.get("observation_type") == "SETUP_ARMED"
        or r.get("direction") not in ("LONG", "SHORT")
        or (float(r.get("entry_price") or 0.0) <= 0.0)
        or (r.get("fill_status") in ("LEGACY", "INELIGIBLE"))
        or (r.get("is_legacy") is True)
    )

    filled_actionable_count = sum(
        1 for r in actionable_records
        if r.get("fill_status") in (ShadowFillStatus.FILLED.value, ShadowFillStatus.RESOLVED.value, None)
        and r.get("direction") in ("LONG", "SHORT")
        and float(r.get("entry_price") or 0.0) > 0.0
        and r.get("regime_after") not in ("NO_FILL", "INELIGIBLE", "LEGACY")
        and not r.get("is_legacy")
    )

    pending_actionable_count = sum(
        1 for r in actionable_records
        if not r.get("resolved")
        and r.get("fill_status") != ShadowFillStatus.NO_FILL.value
        and r.get("regime_after") not in ("INELIGIBLE", "LEGACY")
        and not r.get("is_legacy")
    )

    # RESOLVED + ELIGIBLE actionable observations (the trading win/loss denominator):
    resolved_actionable = [
        r for r in actionable_records
        if bool(r.get("resolved"))
        and r.get("fill_status") in (ShadowFillStatus.FILLED.value, ShadowFillStatus.RESOLVED.value, None)
        and r.get("regime_after") not in ("NO_FILL", "INELIGIBLE", "LEGACY")
        and r.get("direction") in ("LONG", "SHORT")
        and float(r.get("entry_price") or 0.0) > 0.0
        and not r.get("is_legacy")
    ]
    resolved_actionable_count = len(resolved_actionable)

    denom = resolved_actionable_count
    tp1_hits = sum(1 for r in resolved_actionable if r.get("tp1_hit"))
    tp2_hits = sum(1 for r in resolved_actionable if r.get("tp2_hit"))
    sl_hits = sum(1 for r in resolved_actionable if r.get("sl_hit"))

    tp1_hit_rate = round(tp1_hits / denom, 3) if denom > 0 else 0.0
    tp2_hit_rate = round(tp2_hits / denom, 3) if denom > 0 else 0.0
    sl_hit_rate = round(sl_hits / denom, 3) if denom > 0 else 0.0

    gross_rs = [float(r["gross_r"]) for r in resolved_actionable if r.get("gross_r") is not None]
    friction_rs = [float(r["friction_r"]) for r in resolved_actionable if r.get("friction_r") is not None]
    net_rs = [float(r["net_r"]) for r in resolved_actionable if r.get("net_r") is not None]
    mfes = [float(r["future_mfe"]) for r in resolved_actionable if r.get("future_mfe") is not None]
    maes = [float(r["future_mae"]) for r in resolved_actionable if r.get("future_mae") is not None]

    median_gross_r = round(statistics.median(gross_rs), 2) if gross_rs else 0.0
    median_friction_r = round(statistics.median(friction_rs), 2) if friction_rs else 0.0
    median_net_r = round(statistics.median(net_rs), 2) if net_rs else 0.0
    median_mfe = round(statistics.median(mfes), 2) if mfes else 0.0
    median_mae = round(statistics.median(maes), 2) if maes else 0.0

    stratified_playbook: dict[str, list[dict[str, Any]]] = {}
    stratified_direction: dict[str, list[dict[str, Any]]] = {}
    stratified_quality: dict[str, list[dict[str, Any]]] = {}
    for r in resolved_actionable:
        sb = r.get("agent_setup", "UNKNOWN")
        d_k = r.get("direction", "UNKNOWN")
        q_k = r.get("entry_quality", "UNKNOWN")
        stratified_playbook.setdefault(sb, []).append(r)
        stratified_direction.setdefault(d_k, []).append(r)
        stratified_quality.setdefault(q_k, []).append(r)

    def _summarize_group(items: list[dict[str, Any]]) -> dict[str, Any]:
        n = len(items)
        g_rs = [float(x["gross_r"]) for x in items if x.get("gross_r") is not None]
        n_rs = [float(x["net_r"]) for x in items if x.get("net_r") is not None]
        return {
            "count": n,
            "tp1_hit_rate": round(sum(1 for x in items if x.get("tp1_hit")) / n, 3) if n else 0.0,
            "tp2_hit_rate": round(sum(1 for x in items if x.get("tp2_hit")) / n, 3) if n else 0.0,
            "sl_hit_rate": round(sum(1 for x in items if x.get("sl_hit")) / n, 3) if n else 0.0,
            "median_net_r": round(statistics.median(n_rs), 2) if n_rs else 0.0,
            "median_gross_r": round(statistics.median(g_rs), 2) if g_rs else 0.0,
        }

    stratified_playbook_summary = {k: _summarize_group(v) for k, v in stratified_playbook.items()}
    stratified_direction_summary = {k: _summarize_group(v) for k, v in stratified_direction.items()}
    stratified_quality_summary = {k: _summarize_group(v) for k, v in stratified_quality.items()}

    return {
        "total_records": total_records,
        "setup_armed_records": setup_armed_records,
        "actionable_records": actionable_count,
        "filled_actionable_count": filled_actionable_count,
        "no_fill_count": no_fill_count,
        "resolved_actionable_count": resolved_actionable_count,
        "pending_actionable_count": pending_actionable_count,
        "pending_count": pending_count,
        "ineligible_count": ineligible_count,
        "tp1_hit_rate": tp1_hit_rate,
        "tp2_hit_rate": tp2_hit_rate,
        "sl_hit_rate": sl_hit_rate,
        "median_mfe": median_mfe,
        "median_mae": median_mae,
        "median_gross_r": median_gross_r,
        "median_friction_r": median_friction_r,
        "median_net_r": median_net_r,
        "signal_count": resolved_actionable_count,
        "stratified_by_playbook": stratified_playbook_summary,
        "stratified_by_direction": stratified_direction_summary,
        "stratified_by_entry_quality": stratified_quality_summary,
    }


ShadowDecisionRecorder = ShadowEvaluationManager
