from __future__ import annotations

from btc_quant_agent.domain import (
    Candle,
    Direction,
    Regime,
    Setup,
    Signal,
    SignalStatus,
)


def candles(
    count: int,
    interval: str,
    interval_ms: int,
    start: int = 0,
    base: float = 100.0,
) -> list[Candle]:
    output: list[Candle] = []
    for index in range(count):
        price = base + (index % 3 - 1) * 0.1
        open_time = start + index * interval_ms
        output.append(
            Candle(
                symbol="BTCUSDT",
                interval=interval,
                open_time_ms=open_time,
                close_time_ms=open_time + interval_ms - 1,
                open=price,
                high=price + 0.3,
                low=price - 0.3,
                close=price + 0.05,
                volume=10 + index % 5,
            )
        )
    return output


def signal() -> Signal:
    return Signal(
        signal_id="sig-1",
        fingerprint="fp-1",
        strategy_version="0.2.1",
        feature_version="0.2.1",
        model_version=None,
        config_hash="abc",
        validation_status="EXPERIMENTAL",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        setup=Setup.TREND_PULLBACK,
        regime=Regime.TREND_UP,
        status=SignalStatus.ACTIVE,
        data_timestamp_ms=59_999,
        created_at_ms=60_000,
        expires_at_ms=180_000,
        entry_low=99.0,
        entry_high=100.0,
        stop_loss=98.0,
        invalidation_level=98.5,
        take_profit=104.0,
        rr_gross=2.0,
        rr_net=1.9,
        pattern_score=80,
        factor_score=80.0,
        p_win=None,
        expected_r=None,
        recommended_notional=25.0,
        margin_at_leverage=1.25,
        display_leverage=20.0,
        max_loss_usdt=0.535,
        estimated_fee_usdt=0.025,
        estimated_slippage_usdt=0.01,
        estimated_funding_usdt=0.0,
    )
