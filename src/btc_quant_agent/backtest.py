"""Legacy R-based diagnostics and compatibility imports, never P5/P6 authority.

New economic consumers must use btc_quant_agent.formal_research.
"""

from __future__ import annotations

import math
import random
from collections import deque
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any

from .config import BacktestConfig
from .data.derivatives import HistoricalDerivativeStore
from .data.funding import FundingEvent
from .data.quality import validate_candles
from .data.resample import INTERVAL_MS, resample
from .domain import Candle, Direction, Signal
from .engine import QuantEngine

__all__ = [
    "INTERVAL_MS", "BacktestEngine", "EventDrivenBacktestEngine", "FundingEvent", "TradeOutcome", "bootstrap",
    "metrics", "monte_carlo", "resample", "resolve_signal",
]


@dataclass(frozen=True)
class TradeOutcome:
    signal_id: str
    outcome: str
    entry_price: float | None
    exit_price: float | None
    r_multiple: float | None
    entered_at_ms: int | None
    exited_at_ms: int | None
    gross_pnl_usdt: float | None = None
    fees_usdt: float = 0.0
    slippage_usdt: float = 0.0
    funding_pnl_usdt: float = 0.0
    net_pnl_usdt: float | None = None
    holding_minutes: float | None = None
    direction: str | None = None
    setup: str | None = None
    regime: str | None = None
    risk_usdt: float | None = None
    entry_low: float | None = None
    entry_high: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    rr_gross: float | None = None
    rr_net: float | None = None

    @property
    def net_r(self) -> float | None:
        return self.r_multiple

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["net_r"] = self.net_r
        return payload


def _funding_cashflow(
    signal: Signal, entry_price: float, events: Sequence[FundingEvent]
) -> float:
    quantity = signal.recommended_notional / entry_price
    side_sign = -1.0 if signal.direction == Direction.LONG else 1.0
    return sum(
        quantity * (event.mark_price or entry_price) * event.funding_rate * side_sign
        for event in events
    )


def _completed_outcome(
    signal: Signal,
    outcome: str,
    entry_price: float,
    exit_price: float,
    entered_at_ms: int,
    exited_at_ms: int,
    funding_pnl_usdt: float,
) -> TradeOutcome:
    signed_move = (
        exit_price - entry_price
        if signal.direction == Direction.LONG
        else entry_price - exit_price
    )
    gross_pnl = signal.recommended_notional * signed_move / entry_price
    fees = signal.estimated_fee_usdt
    slippage = signal.estimated_slippage_usdt
    net_pnl = gross_pnl - fees - slippage + funding_pnl_usdt
    net_r = net_pnl / signal.max_loss_usdt if signal.max_loss_usdt else None
    return TradeOutcome(
        signal.signal_id,
        outcome,
        entry_price,
        exit_price,
        net_r,
        entered_at_ms,
        exited_at_ms,
        gross_pnl,
        fees,
        slippage,
        funding_pnl_usdt,
        net_pnl,
        (exited_at_ms - entered_at_ms + 1) / 60_000,
        signal.direction.value,
        signal.setup.value,
        signal.regime.value,
        signal.max_loss_usdt,
        signal.entry_low,
        signal.entry_high,
        signal.stop_loss,
        signal.take_profit,
        signal.rr_gross,
        signal.rr_net,
    )


def resolve_signal(
    signal: Signal,
    child_bars: Sequence[Candle],
    max_holding_minutes: int | None = None,
    as_of_ms: int | None = None,
    backtest_config: BacktestConfig | None = None,
    funding_events: Sequence[FundingEvent] = (),
) -> TradeOutcome:
    """Resolve only from bars supplied by the caller; it never fetches future data."""

    holding_config = backtest_config or BacktestConfig()
    if max_holding_minutes is None:
        max_holding_minutes = (
            holding_config.trend_pullback_holding_minutes
            if signal.setup.value == "TREND_PULLBACK"
            else holding_config.breakout_retest_holding_minutes
        )
    entry_price: float | None = None
    entered_at: int | None = None
    holding_deadline: int | None = None
    last_bar: Candle | None = None
    for bar in child_bars:
        if bar.open_time_ms <= signal.data_timestamp_ms:
            continue
        if entry_price is None:
            if bar.open_time_ms > signal.expires_at_ms:
                break
            if not (bar.low <= signal.entry_high and bar.high >= signal.entry_low):
                continue
            entry_price = signal.entry_high if signal.direction == Direction.LONG else signal.entry_low
            entered_at = bar.open_time_ms
            holding_deadline = entered_at + max_holding_minutes * 60_000
        if holding_deadline is not None and bar.close_time_ms > holding_deadline:
            break
        last_bar = bar
        if signal.direction == Direction.LONG:
            stop_hit = bar.low <= signal.stop_loss
            target_hit = bar.high >= signal.take_profit
        else:
            stop_hit = bar.high >= signal.stop_loss
            target_hit = bar.low <= signal.take_profit
        if stop_hit or target_hit:
            assert entered_at is not None
            settlements = [
                event
                for event in funding_events
                if entered_at < event.timestamp_ms <= bar.close_time_ms
            ]
            return _completed_outcome(
                signal,
                "LOSS" if stop_hit else "WIN",
                entry_price,
                signal.stop_loss if stop_hit else signal.take_profit,
                entered_at,
                bar.close_time_ms,
                _funding_cashflow(signal, entry_price, settlements),
            )
    if entry_price is None:
        if as_of_ms is not None and as_of_ms <= signal.expires_at_ms:
            return TradeOutcome(signal.signal_id, "PENDING", None, None, None, None, None)
        return TradeOutcome(signal.signal_id, "UNFILLED", None, None, None, None, None)
    assert entered_at is not None
    if as_of_ms is not None and holding_deadline is not None and as_of_ms <= holding_deadline:
        return TradeOutcome(signal.signal_id, "PENDING", entry_price, None, None, entered_at, None)
    if last_bar is None:
        return _completed_outcome(
            signal, "TIMEOUT", entry_price, entry_price, entered_at, entered_at, 0.0
        )
    settlements = [
        event
        for event in funding_events
        if entered_at < event.timestamp_ms <= last_bar.close_time_ms
    ]
    return _completed_outcome(
        signal,
        "TIMEOUT",
        entry_price,
        last_bar.close,
        entered_at,
        last_bar.close_time_ms,
        _funding_cashflow(signal, entry_price, settlements),
    )


def metrics(outcomes: Sequence[TradeOutcome]) -> dict[str, Any]:
    resolved = [item for item in outcomes if item.r_multiple is not None]
    values = [item.r_multiple for item in resolved if item.r_multiple is not None]
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    equity = peak = max_drawdown = 0.0
    max_losing_streak = losing_streak = 0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
        losing_streak = losing_streak + 1 if value < 0 else 0
        max_losing_streak = max(max_losing_streak, losing_streak)
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    holding = sorted(item.holding_minutes for item in resolved if item.holding_minutes is not None)
    outcome_counts = {
        name: sum(item.outcome == name for item in outcomes)
        for name in sorted({item.outcome for item in outcomes})
    }
    return {
        "signals": len(outcomes),
        "filled_trades": sum(item.entered_at_ms is not None for item in outcomes),
        "outcome_counts": outcome_counts,
        "trades": len(values),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(values) if values else None,
        "avg_win_r": sum(wins) / len(wins) if wins else None,
        "avg_loss_r": sum(losses) / len(losses) if losses else None,
        "expectancy_r": sum(values) / len(values) if values else None,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "max_drawdown_r": max_drawdown,
        "max_losing_streak": max_losing_streak,
        "median_holding_minutes": holding[len(holding) // 2] if holding else None,
        "p90_holding_minutes": (
            holding[min(len(holding) - 1, math.ceil(0.9 * len(holding)) - 1)] if holding else None
        ),
        "total_r": sum(values),
        "gross_pnl_usdt": sum(item.gross_pnl_usdt or 0.0 for item in resolved),
        "fees_usdt": sum(item.fees_usdt for item in resolved),
        "slippage_usdt": sum(item.slippage_usdt for item in resolved),
        "funding_pnl_usdt": sum(item.funding_pnl_usdt for item in resolved),
        "net_pnl_usdt": sum(item.net_pnl_usdt or 0.0 for item in resolved),
    }


def _drawdown_and_streak(values: Sequence[float]) -> tuple[float, int, int]:
    equity = peak = max_drawdown = 0.0
    losing = worst_losing = recovery = worst_recovery = 0
    for value in values:
        equity += value
        if equity >= peak:
            peak = equity
            worst_recovery = max(worst_recovery, recovery)
            recovery = 0
        else:
            max_drawdown = max(max_drawdown, peak - equity)
            recovery += 1
        losing = losing + 1 if value < 0 else 0
        worst_losing = max(worst_losing, losing)
    return max_drawdown, worst_losing, max(worst_recovery, recovery)


def bootstrap(
    outcomes: Sequence[TradeOutcome],
    simulations: int = 2_000,
    seed: int = 7,
    block_size: int = 1,
) -> dict[str, float | int | None]:
    values = [item.r_multiple for item in outcomes if item.r_multiple is not None]
    if not values:
        return {
            "p95_max_drawdown_r": None,
            "p99_max_drawdown_r": None,
            "worst_losing_streak": None,
            "p05_expectancy_r": None,
            "p95_recovery_trades": None,
        }
    rng = random.Random(seed)
    drawdowns: list[float] = []
    expectancies: list[float] = []
    streaks: list[int] = []
    recoveries: list[int] = []
    size = max(1, min(block_size, len(values)))
    for _ in range(simulations):
        sample: list[float] = []
        while len(sample) < len(values):
            start = rng.randrange(0, len(values) - size + 1)
            sample.extend(values[start : start + size])
        sample = sample[: len(values)]
        drawdown, streak, recovery = _drawdown_and_streak(sample)
        drawdowns.append(drawdown)
        streaks.append(streak)
        recoveries.append(recovery)
        expectancies.append(sum(sample) / len(sample))
    drawdowns.sort()
    expectancies.sort()
    recoveries.sort()
    return {
        "p95_max_drawdown_r": drawdowns[math.ceil(0.95 * simulations) - 1],
        "p99_max_drawdown_r": drawdowns[math.ceil(0.99 * simulations) - 1],
        "worst_losing_streak": max(streaks),
        "p05_expectancy_r": expectancies[max(0, math.ceil(0.05 * simulations) - 1)],
        "p95_recovery_trades": recoveries[math.ceil(0.95 * simulations) - 1],
    }


def monte_carlo(
    outcomes: Sequence[TradeOutcome], simulations: int = 2_000, seed: int = 7
) -> dict[str, float | None]:
    values = [item.r_multiple for item in outcomes if item.r_multiple is not None]
    if not values:
        return {"p95_max_drawdown_r": None, "p99_max_drawdown_r": None}
    rng = random.Random(seed)
    drawdowns: list[float] = []
    for _ in range(simulations):
        sample = list(values)
        rng.shuffle(sample)
        drawdowns.append(_drawdown_and_streak(sample)[0])
    drawdowns.sort()
    return {
        "p95_max_drawdown_r": drawdowns[math.ceil(0.95 * len(drawdowns)) - 1],
        "p99_max_drawdown_r": drawdowns[math.ceil(0.99 * len(drawdowns)) - 1],
    }


@dataclass
class _OpenTrade:
    signal: Signal
    entry_price: float
    entered_at_ms: int
    holding_deadline_ms: int
    funding_pnl_usdt: float = 0.0
    last_bar: Candle | None = None


class EventDrivenBacktestEngine:
    """Advance pending signals and positions exactly once per arriving 1m bar."""

    def __init__(
        self,
        engine: QuantEngine,
        derivatives: HistoricalDerivativeStore | None = None,
        funding_events: Sequence[FundingEvent] = (),
        *,
        capture_decisions: bool = False,
    ):
        self.engine = engine
        self.derivatives = derivatives
        self.funding_events = tuple(sorted(funding_events, key=lambda event: event.timestamp_ms))
        self.capture_decisions = capture_decisions
        self.decision_log: list[dict[str, Any]] = []

    def _update_open(self, trade: _OpenTrade, bar: Candle) -> TradeOutcome | None:
        if bar.close_time_ms > trade.holding_deadline_ms:
            exit_bar = trade.last_bar
            return _completed_outcome(
                trade.signal,
                "TIMEOUT",
                trade.entry_price,
                exit_bar.close if exit_bar else trade.entry_price,
                trade.entered_at_ms,
                exit_bar.close_time_ms if exit_bar else trade.entered_at_ms,
                trade.funding_pnl_usdt,
            )
        lower = trade.last_bar.close_time_ms if trade.last_bar else trade.entered_at_ms
        for event in self.funding_events:
            if lower < event.timestamp_ms <= bar.close_time_ms:
                trade.funding_pnl_usdt += _funding_cashflow(
                    trade.signal, trade.entry_price, (event,)
                )
        if trade.signal.direction == Direction.LONG:
            stop_hit = bar.low <= trade.signal.stop_loss
            target_hit = bar.high >= trade.signal.take_profit
        else:
            stop_hit = bar.high >= trade.signal.stop_loss
            target_hit = bar.low <= trade.signal.take_profit
        trade.last_bar = bar
        if not (stop_hit or target_hit):
            return None
        return _completed_outcome(
            trade.signal,
            "LOSS" if stop_hit else "WIN",
            trade.entry_price,
            trade.signal.stop_loss if stop_hit else trade.signal.take_profit,
            trade.entered_at_ms,
            bar.close_time_ms,
            trade.funding_pnl_usdt,
        )

    def run(self, one_minute: Sequence[Candle]) -> list[TradeOutcome]:
        quality = validate_candles(one_minute, "1m")
        if not quality.valid:
            raise ValueError("invalid 1m backtest data: " + "; ".join(quality.issues))
        completed = {interval: resample(one_minute, interval) for interval in ("15m", "1h", "4h")}
        by_close = {
            interval: {bar.close_time_ms: bar for bar in bars}
            for interval, bars in completed.items()
        }
        limits = {
            "15m": self.engine.config.data.history_limit_15m,
            "1h": self.engine.config.data.history_limit_1h,
            "4h": self.engine.config.data.history_limit_4h,
        }
        history: dict[str, deque[Candle]] = {
            interval: deque(maxlen=limits[interval]) for interval in ("15m", "1h", "4h")
        }
        outcomes: list[TradeOutcome] = []
        pending: dict[str, Signal] = {}
        last_fingerprint_ms: dict[str, int] = {}
        open_trade: _OpenTrade | None = None
        for bar in one_minute:
            had_open = open_trade is not None
            if open_trade is not None:
                outcome = self._update_open(open_trade, bar)
                if outcome is not None:
                    outcomes.append(outcome)
                    open_trade = None
            if not had_open and open_trade is None:
                for signal_id, signal in list(pending.items()):
                    if bar.open_time_ms > signal.expires_at_ms:
                        outcomes.append(
                            TradeOutcome(signal_id, "UNFILLED", None, None, None, None, None)
                        )
                        del pending[signal_id]
                        continue
                    if bar.open_time_ms <= signal.data_timestamp_ms:
                        continue
                    if bar.low <= signal.entry_high and bar.high >= signal.entry_low:
                        entry = (
                            signal.entry_high
                            if signal.direction == Direction.LONG
                            else signal.entry_low
                        )
                        holding = (
                            self.engine.config.backtest.trend_pullback_holding_minutes
                            if signal.setup.value == "TREND_PULLBACK"
                            else self.engine.config.backtest.breakout_retest_holding_minutes
                        )
                        open_trade = _OpenTrade(
                            signal, entry, bar.open_time_ms, bar.open_time_ms + holding * 60_000
                        )
                        del pending[signal_id]
                        same_bar = self._update_open(open_trade, bar)
                        if same_bar is not None:
                            outcomes.append(same_bar)
                            open_trade = None
                        break
            for interval in ("15m", "1h", "4h"):
                completed_bar = by_close[interval].get(bar.close_time_ms)
                if completed_bar is not None:
                    history[interval].append(completed_bar)
            if bar.close_time_ms not in by_close["15m"]:
                continue
            now_ms = bar.close_time_ms + 1
            for signal_id, signal in list(pending.items()):
                reason = self.engine.invalidation_reason(
                    signal,
                    list(history["4h"]),
                    list(history["1h"]),
                    list(history["15m"]),
                    now_ms,
                )
                if reason is not None:
                    name = "UNFILLED" if reason == "TTL_EXPIRED" else "INVALIDATED"
                    outcomes.append(TradeOutcome(signal_id, name, None, None, None, None, now_ms))
                    del pending[signal_id]
            if open_trade is not None:
                continue
            result = self.engine.scan(
                list(history["4h"]),
                list(history["1h"]),
                list(history["15m"]),
                derivatives=(
                    self.derivatives.snapshot_at(
                        now_ms,
                        self.engine.config.data,
                        include_order_book=self.engine.config.strategy.enable_order_book_factor,
                    )
                    if self.derivatives
                    else None
                ),
                now_ms=now_ms,
                include_order_book=self.engine.config.strategy.enable_order_book_factor,
            )
            if self.capture_decisions:
                self.decision_log.append(
                    {
                        "timestamp_ms": now_ms,
                        "decision": result.action,
                        "reason_code": result.reason_code,
                        "reason": result.reason,
                        "health": result.health,
                        "signal_id": result.signal.signal_id if result.signal else None,
                        "direction": (
                            result.signal.direction.value if result.signal else None
                        ),
                        "setup": result.signal.setup.value if result.signal else None,
                        "factor_score": result.diagnostics.get("factor_score"),
                        "regime": result.diagnostics.get("regime"),
                        "macro_4h": result.diagnostics.get("macro_4h"),
                        "structure_15m": result.diagnostics.get("structure_15m"),
                        "ema_15m": result.diagnostics.get("ema_15m"),
                    }
                )
            candidate_signal = result.signal
            if candidate_signal is None:
                continue
            cutoff = (
                candidate_signal.created_at_ms
                - self.engine.config.runtime.cooldown_minutes * 60_000
            )
            previous_fingerprint_ms = last_fingerprint_ms.get(candidate_signal.fingerprint)
            if previous_fingerprint_ms is not None and previous_fingerprint_ms >= cutoff:
                continue
            last_fingerprint_ms[candidate_signal.fingerprint] = candidate_signal.created_at_ms
            pending[candidate_signal.signal_id] = candidate_signal
        if open_trade is not None:
            outcomes.append(
                TradeOutcome(
                    open_trade.signal.signal_id,
                    "OPEN_AT_END",
                    open_trade.entry_price,
                    None,
                    None,
                    open_trade.entered_at_ms,
                    None,
                )
            )
        outcomes.extend(
            TradeOutcome(signal_id, "PENDING", None, None, None, None, None)
            for signal_id in pending
        )
        return outcomes


class BacktestEngine(EventDrivenBacktestEngine):
    """Backward-compatible name for the event-driven implementation."""
