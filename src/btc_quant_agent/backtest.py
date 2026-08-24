from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import asdict, dataclass

from .config import BacktestConfig
from .data.derivatives import HistoricalDerivativeStore
from .data.quality import validate_candles
from .domain import Candle, Direction, Signal
from .engine import QuantEngine

INTERVAL_MS = {"1m": 60_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}


@dataclass(frozen=True)
class TradeOutcome:
    signal_id: str
    outcome: str
    entry_price: float | None
    exit_price: float | None
    r_multiple: float | None
    entered_at_ms: int | None
    exited_at_ms: int | None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def resample(candles: Sequence[Candle], interval: str) -> list[Candle]:
    bucket_ms = INTERVAL_MS[interval]
    buckets: dict[int, list[Candle]] = {}
    for bar in candles:
        bucket = (bar.open_time_ms // bucket_ms) * bucket_ms
        buckets.setdefault(bucket, []).append(bar)
    output: list[Candle] = []
    expected_children = bucket_ms // INTERVAL_MS[candles[0].interval] if candles else 0
    for bucket, children in sorted(buckets.items()):
        if len(children) != expected_children:
            continue
        children = sorted(children, key=lambda item: item.open_time_ms)
        output.append(
            Candle(
                symbol=children[0].symbol,
                interval=interval,
                open_time_ms=bucket,
                close_time_ms=bucket + bucket_ms - 1,
                open=children[0].open,
                high=max(item.high for item in children),
                low=min(item.low for item in children),
                close=children[-1].close,
                volume=sum(item.volume for item in children),
                quote_volume=sum(item.quote_volume for item in children),
                taker_buy_base_volume=sum(item.taker_buy_base_volume for item in children),
                trades=sum(item.trades for item in children),
                closed=True,
            )
        )
    return output


def resolve_signal(
    signal: Signal,
    child_bars: Sequence[Candle],
    max_holding_minutes: int | None = None,
    as_of_ms: int | None = None,
    backtest_config: BacktestConfig | None = None,
) -> TradeOutcome:
    holding_config = backtest_config or BacktestConfig()
    if max_holding_minutes is None:
        max_holding_minutes = (
            holding_config.trend_pullback_holding_minutes
            if signal.setup.value == "TREND_PULLBACK"
            else holding_config.breakout_retest_holding_minutes
        )
    entry_price: float | None = None
    entered_at: int | None = None
    deadline = signal.expires_at_ms
    holding_deadline: int | None = None
    last_bar: Candle | None = None

    for bar in child_bars:
        if bar.open_time_ms <= signal.data_timestamp_ms:
            continue
        if entry_price is None:
            if bar.open_time_ms > deadline:
                break
            touched = bar.low <= signal.entry_high and bar.high >= signal.entry_low
            if not touched:
                continue
            entry_price = (
                signal.entry_high if signal.direction == Direction.LONG else signal.entry_low
            )
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
        # Conservative ambiguity rule: stop wins when both occur inside one child bar.
        if stop_hit:
            gross_loss_usdt = (
                signal.recommended_notional * abs(entry_price - signal.stop_loss) / entry_price
            )
            friction = (
                signal.estimated_fee_usdt
                + signal.estimated_slippage_usdt
                + signal.estimated_funding_usdt
            )
            loss_r = -(gross_loss_usdt + friction) / signal.max_loss_usdt
            return TradeOutcome(
                signal.signal_id,
                "LOSS",
                entry_price,
                signal.stop_loss,
                loss_r,
                entered_at,
                bar.close_time_ms,
            )
        if target_hit:
            reward = abs(signal.take_profit - entry_price)
            gross_reward_usdt = signal.recommended_notional * reward / entry_price
            friction = (
                signal.estimated_fee_usdt
                + signal.estimated_slippage_usdt
                + signal.estimated_funding_usdt
            )
            return TradeOutcome(
                signal.signal_id,
                "WIN",
                entry_price,
                signal.take_profit,
                (gross_reward_usdt - friction) / signal.max_loss_usdt
                if signal.max_loss_usdt
                else None,
                entered_at,
                bar.close_time_ms,
            )

    if entry_price is None:
        if as_of_ms is not None and as_of_ms <= deadline:
            return TradeOutcome(signal.signal_id, "PENDING", None, None, None, None, None)
        return TradeOutcome(signal.signal_id, "UNFILLED", None, None, None, None, None)
    if as_of_ms is not None and holding_deadline is not None and as_of_ms <= holding_deadline:
        return TradeOutcome(signal.signal_id, "PENDING", entry_price, None, None, entered_at, None)
    if last_bar is None:
        return TradeOutcome(
            signal.signal_id, "TIMEOUT", entry_price, entry_price, 0.0, entered_at, entered_at
        )
    signed_move = (
        last_bar.close - entry_price
        if signal.direction == Direction.LONG
        else entry_price - last_bar.close
    )
    gross_pnl_usdt = signal.recommended_notional * signed_move / entry_price
    friction = (
        signal.estimated_fee_usdt + signal.estimated_slippage_usdt + signal.estimated_funding_usdt
    )
    return TradeOutcome(
        signal.signal_id,
        "TIMEOUT",
        entry_price,
        last_bar.close,
        (gross_pnl_usdt - friction) / signal.max_loss_usdt if signal.max_loss_usdt else None,
        entered_at,
        last_bar.close_time_ms,
    )


def metrics(outcomes: Sequence[TradeOutcome]) -> dict[str, float | int | None]:
    values = [item.r_multiple for item in outcomes if item.r_multiple is not None]
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "trades": len(values),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(values) if values else None,
        "expectancy_r": sum(values) / len(values) if values else None,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "max_drawdown_r": max_drawdown,
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
        equity = peak = max_drawdown = 0.0
        for value in sample:
            equity += value
            peak = max(peak, equity)
            max_drawdown = max(max_drawdown, peak - equity)
        drawdowns.append(max_drawdown)
    drawdowns.sort()
    return {
        "p95_max_drawdown_r": drawdowns[math.ceil(0.95 * len(drawdowns)) - 1],
        "p99_max_drawdown_r": drawdowns[math.ceil(0.99 * len(drawdowns)) - 1],
    }


class BacktestEngine:
    def __init__(
        self,
        engine: QuantEngine,
        derivatives: HistoricalDerivativeStore | None = None,
    ):
        self.engine = engine
        self.derivatives = derivatives

    def run(self, one_minute: Sequence[Candle]) -> list[TradeOutcome]:
        quality = validate_candles(one_minute, "1m")
        if not quality.valid:
            raise ValueError("invalid 1m backtest data: " + "; ".join(quality.issues))
        candles_15m = resample(one_minute, "15m")
        candles_1h = resample(one_minute, "1h")
        candles_4h = resample(one_minute, "4h")
        outcomes: list[TradeOutcome] = []
        busy_until = 0
        for index, decision_bar in enumerate(candles_15m):
            if decision_bar.close_time_ms <= busy_until:
                continue
            history_15m = candles_15m[: index + 1]
            history_1h = [
                bar for bar in candles_1h if bar.close_time_ms <= decision_bar.close_time_ms
            ]
            history_4h = [
                bar for bar in candles_4h if bar.close_time_ms <= decision_bar.close_time_ms
            ]
            result = self.engine.scan(
                history_4h,
                history_1h,
                history_15m,
                derivatives=(
                    self.derivatives.snapshot_at(
                        decision_bar.close_time_ms + 1, self.engine.config.data
                    )
                    if self.derivatives
                    else None
                ),
                now_ms=decision_bar.close_time_ms + 1,
                include_order_book=False,
            )
            if result.signal is None:
                continue
            future = [bar for bar in one_minute if bar.open_time_ms > decision_bar.close_time_ms]
            outcome = resolve_signal(
                result.signal,
                future,
                backtest_config=self.engine.config.backtest,
            )
            outcomes.append(outcome)
            if outcome.exited_at_ms:
                busy_until = outcome.exited_at_ms
        return outcomes
