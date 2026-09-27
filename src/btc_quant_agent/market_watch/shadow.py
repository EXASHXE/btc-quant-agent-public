from __future__ import annotations

import logging
import statistics
from collections.abc import Sequence
from typing import Any

from ..data.binance import BinancePublicClient
from ..domain import Candle
from .config import MarketWatchConfig
from .domain import (
    MARKET_WATCH_EVIDENCE_VERSION,
    DirectionalDecision,
    ShadowExecutionPathModel,
    ShadowFillResult,
    ShadowFillStatus,
    ShadowPathResolution,
    SymbolAssessment,
    validate_time_coverage,
)
from .state import MarketWatchStateStore, is_legacy_shadow_record

logger = logging.getLogger(__name__)


def _to_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _to_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


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
) -> ShadowFillResult:
    """Authoritative fill resolution for shadow trades strictly on post-signal candles.

    Returns:
        ShadowFillResult (tuple-unpackable as (status, fill_price, fill_time_ms))
    """
    dir_str = str(direction.value if hasattr(direction, "value") else direction).upper()
    if dir_str not in ("LONG", "SHORT") or entry_zone_high <= 0.0:
        return ShadowFillResult(status=ShadowFillStatus.NO_FILL)

    if entry_zone_low > entry_zone_high:
        entry_zone_low, entry_zone_high = entry_zone_high, entry_zone_low

    valid_candles = [c for c in candles if isinstance(c, Candle)]

    for candle in valid_candles:
        # Invariant: No candle closing before or at signal_time_ms may create a fill (Test 14)
        if candle.close_time_ms <= signal_time_ms:
            continue
        # Invariant: Entry candle must not start after entry window has expired
        if candle.open_time_ms >= entry_window_end_ms:
            break

        src_interval = getattr(candle, "interval", "") or "15m"

        if dir_str == "LONG" and candle.low <= entry_zone_high and candle.high >= entry_zone_low:
            # Conservative fill price
            if candle.open >= entry_zone_high:
                fill_price = entry_zone_high
            elif candle.open <= entry_zone_low:
                fill_price = entry_zone_low
            else:
                fill_price = candle.open
            return ShadowFillResult(
                status=ShadowFillStatus.FILLED,
                fill_price=fill_price,
                fill_time_ms=candle.close_time_ms,
                fill_candle_open_ms=candle.open_time_ms,
                fill_candle_close_ms=candle.close_time_ms,
                source_interval=src_interval,
            )
        elif dir_str == "SHORT" and candle.high >= entry_zone_low and candle.low <= entry_zone_high:
            # Conservative fill price
            if candle.open <= entry_zone_low:
                fill_price = entry_zone_low
            elif candle.open >= entry_zone_high:
                fill_price = entry_zone_high
            else:
                fill_price = candle.open
            return ShadowFillResult(
                status=ShadowFillStatus.FILLED,
                fill_price=fill_price,
                fill_time_ms=candle.close_time_ms,
                fill_candle_open_ms=candle.open_time_ms,
                fill_candle_close_ms=candle.close_time_ms,
                source_interval=src_interval,
            )

    # If not filled: check if candles covered through entry_window_end_ms
    latest_time = valid_candles[-1].close_time_ms if valid_candles else signal_time_ms
    if isinstance(latest_time, (int, float)) and latest_time >= entry_window_end_ms:
        return ShadowFillResult(status=ShadowFillStatus.NO_FILL)
    return ShadowFillResult(status=ShadowFillStatus.WAITING_FOR_FILL)


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
    if config is not None:
        taker_fee_rate = getattr(config, "taker_fee_rate", taker_fee_rate)
        slippage_bps = getattr(config, "slippage_bps_per_side", slippage_bps)
        th = getattr(config, "thresholds", None)
        if th is not None:
            if hasattr(th, "taker_fee_rate"):
                taker_fee_rate = th.taker_fee_rate
            if hasattr(th, "slippage_bps_per_side"):
                slippage_bps = th.slippage_bps_per_side

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
            setup_key=getattr(assessment, "setup_key", ""),
            evidence_version=MARKET_WATCH_EVIDENCE_VERSION,
            entry_window_start_ms=signal_time_ms,
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
            dir_str = str(rec.get("direction") or "WAIT").upper()
            obs_type = rec.get("observation_type", "ACTIONABLE_TRIGGERED")

            # Invariant: Legacy shadow rows fail closed (Test 30, 31)
            if is_legacy_shadow_record(rec):
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
                    terminal_reason="LEGACY_INELIGIBLE",
                    regime_after="LEGACY_INELIGIBLE",
                    fill_status="LEGACY",
                    resolved=1,
                )
                results.append({"id": rec_id, "symbol": symbol, "status": "LEGACY_INELIGIBLE"})
                continue

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
                    terminal_reason="INELIGIBLE",
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
                    terminal_reason="INELIGIBLE",
                    regime_after="INELIGIBLE",
                    resolved=1,
                )
                results.append({"id": rec_id, "symbol": symbol, "status": "INELIGIBLE"})
                continue

            if entry_low > entry_high:
                entry_low, entry_high = entry_high, entry_low

            entry_bars = int(rec.get("entry_window_bars") or 4)
            entry_window_end_ms = int(
                rec.get("entry_window_end_ms") or (signal_time_ms + (entry_bars * 15 * 60 * 1000))
            )
            eval_bars = int(rec.get("evaluation_horizon_bars") or 16)
            fill_status = rec.get("fill_status") or ShadowFillStatus.WAITING_FOR_FILL.value

            # Determine initial fetch target
            if fill_status == ShadowFillStatus.FILLED.value:
                rec_fill_t = int(rec["fill_time_ms"])
                eval_end_ms = int(rec.get("evaluation_end_ms") or (rec_fill_t + (eval_bars * 15 * 60 * 1000)))
                needed_fetch_end = min(current_time_ms, eval_end_ms)
            else:
                eval_end_ms = int(rec.get("evaluation_end_ms") or (signal_time_ms + (eval_bars * 15 * 60 * 1000)))
                needed_fetch_end = eval_end_ms

            # Fetch primary 15m candles
            raw_candles: Sequence[Candle] = []
            if (current_time_ms - signal_time_ms) >= (100 * 15 * 60 * 1000):
                raw_candles = _safe_fetch_historical(client, symbol, "15m", signal_time_ms, needed_fetch_end)
            else:
                raw_candles = _safe_fetch_klines(client, symbol, "15m", 120)
                if not raw_candles or raw_candles[0].open_time_ms > signal_time_ms:
                    recovered = _safe_fetch_historical(client, symbol, "15m", signal_time_ms, needed_fetch_end)
                    if recovered:
                        raw_candles = recovered

            fill_bar_remaining_1m: list[Candle] = []
            touch_cand: Candle | None = None

            # Stage 1: Resolve fill if WAITING_FOR_FILL
            if fill_status == ShadowFillStatus.WAITING_FOR_FILL.value:
                cand_for_fill = [
                    c for c in raw_candles
                    if c.close_time_ms > signal_time_ms and c.open_time_ms < entry_window_end_ms
                ]

                # Check candidate candles post-signal within entry window
                for c in cand_for_fill:
                    touches = (c.low <= entry_high and c.high >= entry_low) if dir_str == "LONG" else (c.high >= entry_low and c.low <= entry_high)
                    if touches:
                        touch_cand = c
                        break

                fill_res = ShadowFillStatus.WAITING_FOR_FILL
                fill_p: float | None = None
                fill_t: int | None = None
                path_res = ShadowPathResolution.FIFTEEN_MINUTE_STOP_FIRST.value
                exec_model = ShadowExecutionPathModel.PARTIAL_FIRST_BAR_1M_THEN_15M.value

                if touch_cand is not None:
                    # Attempt 1m refinement inside touch candle only if touch candle reaches SL/TP or starts before signal_time_ms
                    stop_loss_val = float(rec.get("stop_loss") or 0.0)
                    tp1_val = float(rec.get("tp1") or 0.0)
                    touches_stop = (touch_cand.low <= stop_loss_val) if dir_str == "LONG" else (touch_cand.high >= stop_loss_val)
                    touches_tp1 = (touch_cand.high >= tp1_val) if dir_str == "LONG" else (touch_cand.low <= tp1_val)
                    partial_start = touch_cand.open_time_ms < signal_time_ms

                    if (touches_stop or touches_tp1 or partial_start):
                        fetched_1m = _safe_fetch_historical(client, symbol, "1m", touch_cand.open_time_ms, touch_cand.close_time_ms)
                        valid_1m = [c for c in fetched_1m if getattr(c, "interval", "") == "1m"]
                        if valid_1m:
                            for idx, c1 in enumerate(valid_1m):
                                if c1.close_time_ms <= signal_time_ms:
                                    continue
                                c1_touches = (c1.low <= entry_high and c1.high >= entry_low) if dir_str == "LONG" else (c1.high >= entry_low and c1.low <= entry_high)
                                if c1_touches:
                                    fill_res = ShadowFillStatus.FILLED
                                    if dir_str == "LONG":
                                        fill_p = entry_high if c1.open >= entry_high else (max(entry_low, c1.open))
                                    else:
                                        fill_p = entry_low if c1.open <= entry_low else (min(entry_high, c1.open))
                                    fill_t = c1.close_time_ms
                                    path_res = ShadowPathResolution.ONE_MINUTE_CHRONOLOGICAL.value
                                    fill_bar_remaining_1m = [c for c in valid_1m[idx+1:] if c.close_time_ms > c1.close_time_ms]
                                    break

                    if fill_res != ShadowFillStatus.FILLED:
                        # 15m fill without 1m
                        fill_res = ShadowFillStatus.FILLED
                        fill_t = touch_cand.close_time_ms
                        if dir_str == "LONG":
                            fill_p = entry_high if touch_cand.open >= entry_high else (max(entry_low, touch_cand.open))
                        else:
                            fill_p = entry_low if touch_cand.open <= entry_low else (min(entry_high, touch_cand.open))
                        path_res = ShadowPathResolution.FIFTEEN_MINUTE_STOP_FIRST.value

                if fill_res == ShadowFillStatus.FILLED and fill_p is not None and fill_t is not None:
                    # FREEZE BOUNDARIES ONCE FILLED (Test 6, 7, 8)
                    fill_status = ShadowFillStatus.FILLED.value
                    eval_start_ms = fill_t
                    eval_end_ms = fill_t + (eval_bars * 15 * 60 * 1000)
                    self.store.update_shadow_fill(
                        rec_id,
                        fill_status=fill_status,
                        fill_time_ms=fill_t,
                        fill_price=fill_p,
                        evaluation_start_ms=eval_start_ms,
                        evaluation_end_ms=eval_end_ms,
                        path_resolution=path_res,
                        execution_path_model=exec_model,
                    )
                    rec["fill_status"] = fill_status
                    rec["fill_price"] = fill_p
                    rec["fill_time_ms"] = fill_t
                    rec["entry_price"] = fill_p
                    rec["evaluation_start_ms"] = eval_start_ms
                    rec["evaluation_end_ms"] = eval_end_ms
                    rec["path_resolution"] = path_res
                    rec["execution_path_model"] = exec_model
                elif current_time_ms < entry_window_end_ms:
                    results.append({"id": rec_id, "symbol": symbol, "status": "PENDING_WAITING_FOR_FILL"})
                    continue
                else:
                    # Entry window expired: MUST VALIDATE COVERAGE (Test 1, 2, 3)
                    coverage = validate_time_coverage(
                        cand_for_fill,
                        signal_time_ms,
                        entry_window_end_ms,
                        interval_ms=15 * 60 * 1000,
                    )
                    if not coverage.complete:
                        # DATA GAP! Must not infer NO_FILL!
                        self.store.update_shadow_outcome(
                            rec_id,
                            coverage_status="INCOMPLETE",
                            coverage_reason="ENTRY_WINDOW_DATA_GAP",
                            regime_after="PENDING_DATA_GAP",
                            resolved=0,
                        )
                        results.append({
                            "id": rec_id,
                            "symbol": symbol,
                            "status": "PENDING_DATA_GAP",
                            "reason": "ENTRY_WINDOW_DATA_GAP",
                        })
                        continue
                    else:
                        # Complete coverage and no fill -> NO_FILL
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
                            terminal_reason="NO_FILL",
                            fill_status=ShadowFillStatus.NO_FILL.value,
                            coverage_status="COMPLETE",
                            resolved=1,
                        )
                        results.append({"id": rec_id, "symbol": symbol, "status": "NO_FILL"})
                        continue

            # Stage 2: Evaluate forward outcomes strictly post-fill
            fill_time_ms = int(rec["fill_time_ms"])
            fill_price = float(rec["fill_price"])
            eval_start_ms = int(rec.get("evaluation_start_ms") or fill_time_ms)
            eval_end_ms = int(rec.get("evaluation_end_ms") or (fill_time_ms + (eval_bars * 15 * 60 * 1000)))
            stop_loss = float(rec.get("stop_loss") or 0.0)
            tp1 = float(rec.get("tp1") or 0.0)
            tp2 = float(rec.get("tp2") or 0.0)
            direction = DirectionalDecision(dir_str)
            risk_dist = abs(fill_price - stop_loss) if (stop_loss > 0.0 and fill_price != stop_loss) else 1.0

            # Evaluate remaining 1m candles in fill bar if any (Test 15, 16, 17, 18)
            fill_bar_terminal = False
            if fill_bar_remaining_1m:
                is_long = dir_str == "LONG"
                for c1 in fill_bar_remaining_1m:
                    c1_sl = (c1.low <= stop_loss) if is_long else (c1.high >= stop_loss)
                    c1_tp1 = (c1.high >= tp1) if is_long else (c1.low <= tp1)
                    c1_tp2 = (c1.high >= tp2) if is_long else (c1.low <= tp2)
                    if c1_sl and (c1_tp1 or c1_tp2):
                        sl_hit = True
                        tp1_hit = False
                        tp2_hit = False
                        exit_price = stop_loss
                        exit_time_ms = c1.close_time_ms
                        term_reason = "STOP"
                        fill_bar_terminal = True
                        break
                    elif c1_tp1 and not c1_sl:
                        tp1_hit = True
                        sl_hit = False
                        tp2_hit = c1_tp2
                        exit_price = tp1
                        exit_time_ms = c1.close_time_ms
                        term_reason = "TP1"
                        fill_bar_terminal = True
                        break
                    elif c1_sl and not c1_tp1:
                        sl_hit = True
                        tp1_hit = False
                        tp2_hit = False
                        exit_price = stop_loss
                        exit_time_ms = c1.close_time_ms
                        term_reason = "STOP"
                        fill_bar_terminal = True
                        break

                if fill_bar_terminal:
                    gross_r = (exit_price - fill_price) / risk_dist if is_long else (fill_price - exit_price) / risk_dist
                    _f_dol, friction_r = compute_trade_friction_r(fill_price, exit_price, risk_dist, config)
                    net_r = gross_r - friction_r
                    mfe = max(0.0, (c1.high - fill_price) / risk_dist if is_long else (fill_price - c1.low) / risk_dist)
                    mae = max(0.0, (fill_price - c1.low) / risk_dist if is_long else (c1.high - fill_price) / risk_dist)
                    fill_bar_outcome = {
                        "future_mfe": round(mfe, 2),
                        "future_mae": round(mae, 2),
                        "tp1_hit": tp1_hit,
                        "tp2_hit": tp2_hit,
                        "sl_hit": sl_hit,
                        "time_to_target_ms": exit_time_ms if tp1_hit else None,
                        "time_to_stop_ms": exit_time_ms if sl_hit else None,
                        "gross_r": round(gross_r, 4),
                        "friction_r": round(friction_r, 4),
                        "net_r": round(net_r, 4),
                        "path_resolution": ShadowPathResolution.ONE_MINUTE_CHRONOLOGICAL.value,
                        "terminal_reason": term_reason,
                        "exit_price": exit_price,
                        "exit_time_ms": exit_time_ms,
                        "is_terminal": True,
                    }
                    self.store.update_shadow_outcome(
                        rec_id,
                        future_mfe=_to_float(fill_bar_outcome.get("future_mfe")),
                        future_mae=_to_float(fill_bar_outcome.get("future_mae")),
                        tp1_hit=bool(fill_bar_outcome.get("tp1_hit")),
                        tp2_hit=bool(fill_bar_outcome.get("tp2_hit")),
                        sl_hit=bool(fill_bar_outcome.get("sl_hit")),
                        time_to_target_ms=_to_int(fill_bar_outcome.get("time_to_target_ms")),
                        time_to_stop_ms=_to_int(fill_bar_outcome.get("time_to_stop_ms")),
                        gross_r=_to_float(fill_bar_outcome.get("gross_r")),
                        friction_r=_to_float(fill_bar_outcome.get("friction_r")),
                        net_r=_to_float(fill_bar_outcome.get("net_r")),
                        path_resolution=str(fill_bar_outcome["path_resolution"]) if fill_bar_outcome.get("path_resolution") is not None else None,
                        regime_after="RESOLVED_TERMINAL",
                        terminal_reason=term_reason,
                        exit_price=exit_price,
                        exit_time_ms=exit_time_ms,
                        coverage_status="COMPLETE",
                        resolved=1,
                    )
                    results.append({"id": rec_id, "symbol": symbol, "status": "RESOLVED", "outcome": fill_bar_outcome})
                    continue

            # Recompute required fetch range through new eval_end_ms (Test 6, 7)
            target_fetch_end = min(current_time_ms, eval_end_ms)
            if touch_cand is not None:
                fill_bar_close_ms = touch_cand.close_time_ms
            else:
                fill_bar_cand = next((c for c in raw_candles if c.open_time_ms < fill_time_ms <= c.close_time_ms), None)
                if fill_bar_cand is not None:
                    fill_bar_close_ms = fill_bar_cand.close_time_ms
                else:
                    fill_bar_close_ms = fill_time_ms

            subsequent_closed = [
                c for c in raw_candles
                if c.close_time_ms > fill_bar_close_ms and c.close_time_ms <= target_fetch_end
            ]

            outcome: dict[str, Any] = {}
            if subsequent_closed:
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
                    client=client,
                    symbol=symbol,
                )

            is_terminal = bool(outcome.get("is_terminal", False))

            # Only fetch more candles if not already terminal and candles do not reach target_fetch_end
            if not is_terminal and (not subsequent_closed or subsequent_closed[-1].close_time_ms < target_fetch_end) and target_fetch_end > fill_bar_close_ms:
                more_cand = _safe_fetch_historical(client, symbol, "15m", fill_bar_close_ms, target_fetch_end)
                if more_cand:
                    subsequent_closed = [
                        c for c in more_cand
                        if c.close_time_ms > fill_bar_close_ms and c.close_time_ms <= target_fetch_end
                    ]
                    if subsequent_closed:
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
                            client=client,
                            symbol=symbol,
                        )
                        is_terminal = bool(outcome.get("is_terminal", False))

            if not subsequent_closed:
                results.append({"id": rec_id, "symbol": symbol, "status": "PENDING_AWAITING_FUTURE_BARS"})
                continue
            if is_terminal:
                self.store.update_shadow_outcome(
                    rec_id,
                    future_mfe=_to_float(outcome.get("future_mfe")),
                    future_mae=_to_float(outcome.get("future_mae")),
                    tp1_hit=bool(outcome.get("tp1_hit")),
                    tp2_hit=bool(outcome.get("tp2_hit")),
                    sl_hit=bool(outcome.get("sl_hit")),
                    time_to_target_ms=_to_int(outcome.get("time_to_target_ms")),
                    time_to_stop_ms=_to_int(outcome.get("time_to_stop_ms")),
                    gross_r=_to_float(outcome.get("gross_r")),
                    friction_r=_to_float(outcome.get("friction_r")),
                    net_r=_to_float(outcome.get("net_r")),
                    path_resolution=str(outcome["path_resolution"]) if outcome.get("path_resolution") is not None else None,
                    regime_after="RESOLVED_TERMINAL",
                    terminal_reason=str(outcome["terminal_reason"]) if outcome.get("terminal_reason") is not None else None,
                    exit_price=_to_float(outcome.get("exit_price")),
                    exit_time_ms=_to_int(outcome.get("exit_time_ms")),
                    coverage_status="COMPLETE",
                    resolved=1,
                )
                results.append({"id": rec_id, "symbol": symbol, "status": "RESOLVED", "outcome": outcome})
                continue

            if current_time_ms < eval_end_ms:
                results.append({"id": rec_id, "symbol": symbol, "status": "PENDING_UNMATURED", "outcome": outcome})
                continue
            else:
                # Outcome maturity reached: MUST VALIDATE COVERAGE (Test 4, 5)
                coverage = validate_time_coverage(
                    subsequent_closed,
                    fill_bar_close_ms,
                    eval_end_ms,
                    interval_ms=15 * 60 * 1000,
                )
                if not coverage.complete:
                    # DATA GAP! Must not become TIMEOUT!
                    self.store.update_shadow_outcome(
                        rec_id,
                        coverage_status="INCOMPLETE",
                        coverage_reason="OUTCOME_WINDOW_DATA_GAP",
                        regime_after="PENDING_DATA_GAP",
                        resolved=0,
                    )
                    results.append({
                        "id": rec_id,
                        "symbol": symbol,
                        "status": "PENDING_DATA_GAP",
                        "reason": "OUTCOME_WINDOW_DATA_GAP",
                    })
                    continue
                else:
                    self.store.update_shadow_outcome(
                        rec_id,
                        future_mfe=_to_float(outcome.get("future_mfe")),
                        future_mae=_to_float(outcome.get("future_mae")),
                        tp1_hit=False,
                        tp2_hit=bool(outcome.get("tp2_hit", False)),
                        sl_hit=False,
                        time_to_target_ms=None,
                        time_to_stop_ms=None,
                        gross_r=_to_float(outcome.get("gross_r")),
                        friction_r=_to_float(outcome.get("friction_r")),
                        net_r=_to_float(outcome.get("net_r")),
                        path_resolution=str(outcome["path_resolution"]) if outcome.get("path_resolution") is not None else None,
                        regime_after="RESOLVED_MATURED",
                        terminal_reason="TIMEOUT",
                        exit_price=_to_float(outcome.get("exit_price")),
                        exit_time_ms=_to_int(outcome.get("exit_time_ms")),
                        coverage_status="COMPLETE",
                        resolved=1,
                    )
                    results.append({"id": rec_id, "symbol": symbol, "status": "RESOLVED", "outcome": outcome})
                    continue

        return {
            "resolved_count": sum(1 for r in results if r["status"] in ("RESOLVED", "NO_FILL", "INELIGIBLE", "LEGACY_INELIGIBLE")),
            "pending_count": sum(
                1 for r in results
                if r["status"] in ("PENDING_AWAITING_FUTURE_BARS", "PENDING_UNMATURED", "PENDING_WAITING_FOR_FILL", "PENDING_DATA_GAP")
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
        client: Any = None,
        symbol: str = "",
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
        terminal_reason: str = "TIMEOUT"
        exit_price: float = future_candles[-1].close if future_candles else entry_price
        exit_time_ms: int = future_candles[-1].close_time_ms if future_candles else 0
        is_terminal = False

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
                bar_sl = bar_tp1 = bar_tp2 = False

            mfe = max(mfe, favorable / risk_dist)
            mae = max(mae, adverse / risk_dist)

            # Check same-bar ambiguity (both SL and TP touched on same candle)
            if bar_sl and (bar_tp1 or bar_tp2):
                span_1m = [
                    c for c in (intrabar_1m_candles or [])
                    if c.close_time_ms > candle.open_time_ms and c.close_time_ms <= candle.close_time_ms
                ]
                if not span_1m and client is not None and symbol:
                    fetched = _safe_fetch_historical(client, symbol, "1m", candle.open_time_ms, candle.close_time_ms)
                    span_1m = [c for c in fetched if getattr(c, "interval", "") == "1m"]

                if span_1m:
                    disambiguated = False
                    for c1 in span_1m:
                        c1_sl = (c1.low <= stop_loss) if is_long else (c1.high >= stop_loss)
                        c1_tp1 = (c1.high >= tp1) if is_long else (c1.low <= tp1)
                        c1_tp2 = (c1.high >= tp2) if is_long else (c1.low <= tp2)

                        # Test 21: 1m candle itself touches both -> conservative STOP_FIRST
                        if c1_sl and (c1_tp1 or c1_tp2):
                            sl_hit = True
                            time_to_stop_ms = c1.close_time_ms
                            exit_price = stop_loss
                            exit_time_ms = c1.close_time_ms
                            terminal_reason = "STOP"
                            path_resolution = ShadowPathResolution.FIFTEEN_MINUTE_STOP_FIRST.value
                            disambiguated = True
                            is_terminal = True
                            break
                        elif c1_tp1 and not c1_sl:
                            # Test 19: 1m path proves TP first -> TP1
                            tp1_hit = True
                            time_to_target_ms = c1.close_time_ms
                            exit_price = tp1
                            exit_time_ms = c1.close_time_ms
                            terminal_reason = "TP1"
                            path_resolution = ShadowPathResolution.ONE_MINUTE_CHRONOLOGICAL.value
                            disambiguated = True
                            is_terminal = True
                            if c1_tp2:
                                tp2_hit = True
                            break
                        elif c1_sl and not c1_tp1:
                            # Test 20: 1m proves SL first -> STOP
                            sl_hit = True
                            time_to_stop_ms = c1.close_time_ms
                            exit_price = stop_loss
                            exit_time_ms = c1.close_time_ms
                            terminal_reason = "STOP"
                            path_resolution = ShadowPathResolution.ONE_MINUTE_CHRONOLOGICAL.value
                            disambiguated = True
                            is_terminal = True
                            break
                    if disambiguated:
                        break

                # 1m unavailable or could not disambiguate -> 15m STOP_FIRST fallback (Test 22)
                sl_hit = True
                time_to_stop_ms = candle.close_time_ms
                exit_price = stop_loss
                exit_time_ms = candle.close_time_ms
                terminal_reason = "STOP"
                path_resolution = ShadowPathResolution.FIFTEEN_MINUTE_STOP_FIRST.value
                is_terminal = True
                break

            elif bar_sl:
                # Test 27: STOP
                sl_hit = True
                time_to_stop_ms = candle.close_time_ms
                exit_price = stop_loss
                exit_time_ms = candle.close_time_ms
                terminal_reason = "STOP"
                is_terminal = True
                break
            elif bar_tp1:
                # Test 26 & 29: TP1 terminal exit
                tp1_hit = True
                time_to_target_ms = candle.close_time_ms
                exit_price = tp1
                exit_time_ms = candle.close_time_ms
                terminal_reason = "TP1"
                is_terminal = True
                if bar_tp2:
                    tp2_hit = True
                break

        if not is_terminal:
            # Test 28: TIMEOUT uses final covered candle close
            exit_price = future_candles[-1].close
            exit_time_ms = future_candles[-1].close_time_ms
            terminal_reason = "TIMEOUT"

        if is_long:
            gross_r = (exit_price - entry_price) / risk_dist
        elif is_short:
            gross_r = (entry_price - exit_price) / risk_dist
        else:
            gross_r = 0.0

        _friction_dollars, friction_r = compute_trade_friction_r(entry_price, exit_price, risk_dist, config)
        net_r = gross_r - friction_r

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
                terminal_reason=terminal_reason,
                exit_price=exit_price,
                exit_time_ms=exit_time_ms,
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
            "terminal_reason": terminal_reason,
            "exit_price": exit_price,
            "exit_time_ms": exit_time_ms,
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
            "waiting_for_fill_count": 0,
            "no_fill_count": 0,
            "filled_count": 0,
            "resolved_trade_count": 0,
            "pending_data_gap_count": 0,
            "legacy_ineligible_count": 0,
            "data_gap_ineligible_count": 0,
            "tp1_rate": 0.0,
            "stop_rate": 0.0,
            "timeout_rate": 0.0,
            "no_fill_rate": 0.0,
            "tp1_hit_rate": 0.0,
            "tp2_hit_rate": 0.0,
            "sl_hit_rate": 0.0,
            "median_mfe": 0.0,
            "median_mae": 0.0,
            "median_gross_r": 0.0,
            "median_friction_r": 0.0,
            "median_net_r": 0.0,
            "signal_count": 0,
            "filled_actionable_count": 0,
            "resolved_actionable_count": 0,
            "pending_actionable_count": 0,
            "pending_count": 0,
            "ineligible_count": 0,
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
        and not is_legacy_shadow_record(r)
    ]
    actionable_count = len(actionable_records)

    legacy_ineligible_count = sum(
        1 for r in records
        if is_legacy_shadow_record(r)
        or r.get("regime_after") in ("LEGACY", "LEGACY_INELIGIBLE")
        or r.get("terminal_reason") == "LEGACY_INELIGIBLE"
    )

    data_gap_ineligible_count = sum(
        1 for r in records
        if r.get("regime_after") == "INELIGIBLE_DATA_GAP"
        or r.get("terminal_reason") == "INELIGIBLE_DATA_GAP"
    )

    pending_data_gap_count = sum(
        1 for r in records
        if r.get("regime_after") == "PENDING_DATA_GAP"
        or r.get("coverage_reason") in ("ENTRY_WINDOW_DATA_GAP", "OUTCOME_WINDOW_DATA_GAP")
    )

    pending_count = sum(1 for r in records if not r.get("resolved"))

    waiting_for_fill_count = sum(
        1 for r in actionable_records
        if r.get("fill_status") == ShadowFillStatus.WAITING_FOR_FILL.value
        and not r.get("resolved")
        and r.get("regime_after") != "PENDING_DATA_GAP"
    )

    no_fill_count = sum(
        1 for r in actionable_records
        if r.get("fill_status") == ShadowFillStatus.NO_FILL.value
        or r.get("regime_after") == "NO_FILL"
        or r.get("terminal_reason") == "NO_FILL"
    )

    filled_count = sum(
        1 for r in actionable_records
        if r.get("fill_status") in (ShadowFillStatus.FILLED.value, ShadowFillStatus.RESOLVED.value)
        and r.get("direction") in ("LONG", "SHORT")
        and float(r.get("entry_price") or 0.0) > 0.0
        and r.get("regime_after") not in ("NO_FILL", "INELIGIBLE", "LEGACY_INELIGIBLE", "INELIGIBLE_DATA_GAP")
    )

    # Eligible resolved trades (trade hit-rate denominator - Section 28)
    resolved_actionable = [
        r for r in actionable_records
        if bool(r.get("resolved"))
        and r.get("fill_status") in (ShadowFillStatus.FILLED.value, ShadowFillStatus.RESOLVED.value, None)
        and (
            r.get("terminal_reason") in ("STOP", "TP1", "TIMEOUT")
            or (
                r.get("terminal_reason") is None
                and (
                    bool(r.get("tp1_hit"))
                    or bool(r.get("sl_hit"))
                    or r.get("regime_after") in ("RESOLVED", "RESOLVED_MATURED", "RESOLVED_TERMINAL", "TIMEOUT", "BALANCED")
                    or r.get("net_r") is not None
                )
            )
        )
        and r.get("regime_after") not in ("NO_FILL", "INELIGIBLE", "LEGACY_INELIGIBLE", "PENDING_DATA_GAP", "INELIGIBLE_DATA_GAP")
        and r.get("direction") in ("LONG", "SHORT")
        and float(r.get("entry_price") or 0.0) > 0.0
    ]
    resolved_trade_count = len(resolved_actionable)
    denom = resolved_trade_count

    tp1_hits = sum(1 for r in resolved_actionable if r.get("terminal_reason") == "TP1" or r.get("tp1_hit"))
    stop_hits = sum(1 for r in resolved_actionable if r.get("terminal_reason") == "STOP" or r.get("sl_hit"))
    timeout_hits = sum(
        1 for r in resolved_actionable
        if r.get("terminal_reason") == "TIMEOUT"
        or (r.get("terminal_reason") is None and not r.get("tp1_hit") and not r.get("sl_hit"))
    )
    tp2_hits = sum(1 for r in resolved_actionable if r.get("tp2_hit"))

    tp1_rate = round(tp1_hits / denom, 3) if denom > 0 else 0.0
    stop_rate = round(stop_hits / denom, 3) if denom > 0 else 0.0
    timeout_rate = round(timeout_hits / denom, 3) if denom > 0 else 0.0
    no_fill_rate = round(no_fill_count / actionable_count, 3) if actionable_count > 0 else 0.0

    tp1_hit_rate = tp1_rate
    sl_hit_rate = stop_rate
    tp2_hit_rate = round(tp2_hits / denom, 3) if denom > 0 else 0.0

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
            "tp1_hit_rate": round(sum(1 for x in items if x.get("terminal_reason") == "TP1" or x.get("tp1_hit")) / n, 3) if n else 0.0,
            "tp2_hit_rate": round(sum(1 for x in items if x.get("tp2_hit")) / n, 3) if n else 0.0,
            "sl_hit_rate": round(sum(1 for x in items if x.get("terminal_reason") == "STOP" or x.get("sl_hit")) / n, 3) if n else 0.0,
            "median_net_r": round(statistics.median(n_rs), 2) if n_rs else 0.0,
            "median_gross_r": round(statistics.median(g_rs), 2) if g_rs else 0.0,
        }

    stratified_playbook_summary = {k: _summarize_group(v) for k, v in stratified_playbook.items()}
    stratified_direction_summary = {k: _summarize_group(v) for k, v in stratified_direction.items()}
    stratified_quality_summary = {k: _summarize_group(v) for k, v in stratified_quality.items()}

    ineligible_count = sum(
        1 for r in records
        if r.get("observation_type") != "ACTIONABLE_TRIGGERED"
        or is_legacy_shadow_record(r)
        or r.get("regime_after") in ("INELIGIBLE", "INELIGIBLE_DATA_GAP", "LEGACY", "LEGACY_INELIGIBLE")
        or r.get("terminal_reason") in ("INELIGIBLE", "INELIGIBLE_DATA_GAP", "LEGACY_INELIGIBLE")
        or r.get("fill_status") in ("LEGACY", "INELIGIBLE")
        or r.get("direction") not in ("LONG", "SHORT")
        or float(r.get("entry_price") or 0.0) <= 0.0
    )

    pending_actionable_count = sum(
        1 for r in actionable_records
        if not r.get("resolved")
    )

    return {
        "total_records": total_records,
        "setup_armed_records": setup_armed_records,
        "actionable_records": actionable_count,
        "waiting_for_fill_count": waiting_for_fill_count,
        "no_fill_count": no_fill_count,
        "filled_count": filled_count,
        "resolved_trade_count": resolved_trade_count,
        "pending_data_gap_count": pending_data_gap_count,
        "legacy_ineligible_count": legacy_ineligible_count,
        "data_gap_ineligible_count": data_gap_ineligible_count,
        "tp1_rate": tp1_rate,
        "stop_rate": stop_rate,
        "timeout_rate": timeout_rate,
        "no_fill_rate": no_fill_rate,
        "tp1_hit_rate": tp1_hit_rate,
        "tp2_hit_rate": tp2_hit_rate,
        "sl_hit_rate": sl_hit_rate,
        "median_mfe": median_mfe,
        "median_mae": median_mae,
        "median_gross_r": median_gross_r,
        "median_friction_r": median_friction_r,
        "median_net_r": median_net_r,
        "signal_count": resolved_trade_count,
        "filled_actionable_count": filled_count,
        "resolved_actionable_count": resolved_trade_count,
        "pending_actionable_count": pending_actionable_count,
        "pending_count": pending_count,
        "ineligible_count": ineligible_count,
        "stratified_by_playbook": stratified_playbook_summary,
        "stratified_by_direction": stratified_direction_summary,
        "stratified_by_entry_quality": stratified_quality_summary,
    }


ShadowDecisionRecorder = ShadowEvaluationManager
