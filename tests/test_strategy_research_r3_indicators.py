"""Tests for indicators, bar aggregations, and technical metric calculations."""

from decimal import Decimal

from btc_quant_agent.strategy_research.r3_overnight.indicators import (
    aggregate_1m_to_1h,
    compute_atr20_1h,
    compute_ema_series,
    compute_er12_4h,
)
from btc_quant_agent.strategy_research.r3_overnight.types import Bar1m, Bar4h


def test_aggregate_1m_to_1h():
    start_ms = 1_700_000_000_000
    # Align to whole hour
    start_hour = (start_ms // 3_600_000) * 3_600_000
    bars_1m = []
    for i in range(60):
        t = start_hour + i * 60_000
        bars_1m.append(
            Bar1m(
                timestamp_ms=t,
                open=Decimal(100) + Decimal(str(i)),
                high=Decimal(105) + Decimal(str(i)),
                low=Decimal(95) + Decimal(str(i)),
                close=Decimal(102) + Decimal(str(i)),
                volume=Decimal("1.5"),
                symbol="BTCUSDT",
            )
        )

    bars_1h = aggregate_1m_to_1h(bars_1m)
    assert len(bars_1h) == 1
    h = bars_1h[0]
    assert h.timestamp_ms == start_hour
    assert h.open == Decimal(100)
    assert h.close == Decimal(102) + Decimal(59)
    assert h.volume == Decimal("1.5") * 60
    assert h.bar_count == 60


def test_aggregate_incomplete_hour_rejected():
    start_hour = 1_700_000_000_000 // 3_600_000 * 3_600_000
    # Only 59 bars (missing 1 minute)
    bars_1m = [
        Bar1m(
            timestamp_ms=start_hour + i * 60_000,
            open=Decimal(100),
            high=Decimal(105),
            low=Decimal(95),
            close=Decimal(100),
            volume=Decimal("1.0"),
            symbol="BTCUSDT",
        )
        for i in range(59)
    ]
    bars_1h = aggregate_1m_to_1h(bars_1m)
    assert len(bars_1h) == 0


def test_compute_atr20_1h():
    start_hour = 1_700_000_000_000 // 3_600_000 * 3_600_000
    # Create 22 hourly bars of constant True Range 10.0
    from btc_quant_agent.strategy_research.r3_overnight.types import Bar1h
    bars_1h = []
    for i in range(22):
        t = start_hour + i * 3_600_000
        bars_1h.append(
            Bar1h(
                timestamp_ms=t,
                open=Decimal(100),
                high=Decimal(110),
                low=Decimal(100),
                close=Decimal(105),
                volume=Decimal(100),
                symbol="BTCUSDT",
                bar_count=60,
            )
        )
    atr = compute_atr20_1h(bars_1h)
    assert atr is not None
    assert atr == Decimal(10)


def test_compute_ema_series():
    # Test EMA with length 3
    closes = [Decimal(10), Decimal(20), Decimal(30), Decimal(40), Decimal(50)]
    ema = compute_ema_series(closes, 3)
    assert len(ema) == 5
    assert ema[0] is None
    assert ema[1] is None
    # SMA seed: (10 + 20 + 30) / 3 = 20
    assert ema[2] == Decimal(20)
    # alpha = 2 / (3 + 1) = 0.5
    # ema[3] = 0.5 * 40 + 0.5 * 20 = 30
    assert ema[3] == Decimal(30)
    # ema[4] = 0.5 * 50 + 0.5 * 30 = 40
    assert ema[4] == Decimal(40)


def test_compute_er12():
    start_4h = 1_700_000_000_000 // 14_400_000 * 14_400_000
    bars_4h = []
    # Straight line up: close increases by 10 each bar
    for i in range(15):
        t = start_4h + i * 14_400_000
        c = Decimal(str(100 + i * 10))
        bars_4h.append(
            Bar4h(
                timestamp_ms=t,
                open=c - Decimal(5),
                high=c + Decimal(5),
                low=c - Decimal(5),
                close=c,
                volume=Decimal(50),
                symbol="BTCUSDT",
                bar_count=240,
            )
        )
    er = compute_er12_4h(bars_4h)
    assert er is not None
    # Displacement over 12 bars is 120, sum of 12 increments of 10 is 120 -> ER12 = 1.0
    assert er == Decimal("1.0")
