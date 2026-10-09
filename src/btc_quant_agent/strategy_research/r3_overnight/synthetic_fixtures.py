"""Hermetic synthetic nonmarket fixtures for deterministic testing of the R3 execution ledger."""

from decimal import Decimal

from btc_quant_agent.strategy_research.r3_overnight.types import (
    Bar1m,
    Direction,
    MarkBar1m,
)


def make_1m_bar(
    timestamp_ms: int,
    open_p: Decimal,
    high_p: Decimal,
    low_p: Decimal,
    close_p: Decimal,
    volume: Decimal = Decimal("10.0"),
    symbol: str = "BTCUSDT",
) -> Bar1m:
    """Helper to construct a single 1m trade candle."""
    return Bar1m(
        timestamp_ms=timestamp_ms,
        open=open_p,
        high=high_p,
        low=low_p,
        close=close_p,
        volume=volume,
        symbol=symbol,
    )


def make_mark_bar(
    timestamp_ms: int,
    price: Decimal,
    symbol: str = "BTCUSDT",
    available_lag_ms: int = 0,
) -> MarkBar1m:
    """Helper to construct a 1m mark price bar."""
    return MarkBar1m(
        timestamp_ms=timestamp_ms - 60_000,
        open=price,
        high=price,
        low=price,
        close=price,
        symbol=symbol,
        available_at_ms=timestamp_ms + available_lag_ms,
    )


def generate_flat_1m_series(
    start_ms: int,
    count_minutes: int,
    price: Decimal,
    symbol: str = "BTCUSDT",
) -> list[Bar1m]:
    """Generate a series of flat 1m bars."""
    bars: list[Bar1m] = []
    current_ms = start_ms
    for _ in range(count_minutes):
        bars.append(
            make_1m_bar(
                timestamp_ms=current_ms,
                open_p=price,
                high_p=price + Decimal("1.0"),
                low_p=price - Decimal("1.0"),
                close_p=price,
                symbol=symbol,
            )
        )
        current_ms += 60_000
    return bars


def generate_flat_mark_series(
    start_ms: int,
    count_minutes: int,
    price: Decimal,
    symbol: str = "BTCUSDT",
) -> list[MarkBar1m]:
    """Generate a series of 1m mark bars."""
    marks: list[MarkBar1m] = []
    current_ms = start_ms
    for _ in range(count_minutes):
        marks.append(
            make_mark_bar(
                timestamp_ms=current_ms,
                price=price,
                symbol=symbol,
            )
        )
        current_ms += 60_000
    return marks


def create_constructed_win_fixture(direction: Direction = Direction.LONG) -> tuple[list[Bar1m], list[MarkBar1m]]:
    """
    Constructed WIN fixture:
    Order entered at 50,000 USDT.
    For LONG: Stop at 49,500, Target at 51,000. Price moves up to 51,200 and hits TP.
    For SHORT: Stop at 50,500, Target at 49,000. Price moves down to 48,800 and hits TP.
    """
    start_ms = 1_700_000_000_000
    bars: list[Bar1m] = []
    marks: list[MarkBar1m] = []

    base_p = Decimal("50000.00")
    if direction == Direction.LONG:
        prices = [
            (base_p, base_p + 10, base_p - 10, base_p),  # Entry bar
            (base_p + 100, base_p + 300, base_p + 50, base_p + 250),
            (base_p + 300, base_p + 600, base_p + 250, base_p + 550),
            (base_p + 600, base_p + 1200, base_p + 580, base_p + 1100),  # TP triggered at 51000
        ]
    else:
        prices = [
            (base_p, base_p + 10, base_p - 10, base_p),
            (base_p - 100, base_p - 50, base_p - 300, base_p - 250),
            (base_p - 300, base_p - 250, base_p - 600, base_p - 550),
            (base_p - 600, base_p - 580, base_p - 1200, base_p - 1100),  # TP triggered at 49000
        ]

    for i, (op, hp, lp, cp) in enumerate(prices):
        t = start_ms + i * 60_000
        bars.append(make_1m_bar(t, Decimal(str(op)), Decimal(str(hp)), Decimal(str(lp)), Decimal(str(cp))))
        marks.append(make_mark_bar(t, Decimal(str(cp))))

    return bars, marks


def create_constructed_loss_fixture(direction: Direction = Direction.LONG) -> tuple[list[Bar1m], list[MarkBar1m]]:
    """
    Constructed LOSS fixture:
    Hits stop loss level cleanly.
    """
    start_ms = 1_700_000_000_000
    bars: list[Bar1m] = []
    marks: list[MarkBar1m] = []

    base_p = Decimal("50000.00")
    if direction == Direction.LONG:
        prices = [
            (base_p, base_p + 10, base_p - 10, base_p),
            (base_p - 100, base_p - 50, base_p - 300, base_p - 250),
            (base_p - 300, base_p - 250, base_p - 600, base_p - 550),  # SL triggered at 49500
        ]
    else:
        prices = [
            (base_p, base_p + 10, base_p - 10, base_p),
            (base_p + 100, base_p + 300, base_p + 50, base_p + 250),
            (base_p + 300, base_p + 600, base_p + 250, base_p + 550),  # SL triggered at 50500
        ]

    for i, (op, hp, lp, cp) in enumerate(prices):
        t = start_ms + i * 60_000
        bars.append(make_1m_bar(t, Decimal(str(op)), Decimal(str(hp)), Decimal(str(lp)), Decimal(str(cp))))
        marks.append(make_mark_bar(t, Decimal(str(cp))))

    return bars, marks


def create_collision_fixture() -> tuple[list[Bar1m], list[MarkBar1m]]:
    """
    STOP-BEFORE-TARGET COLLISION FIXTURE:
    A single 1m bar touches BOTH Stop Loss and Take Profit levels:
    Open: 50,000, High: 51,500 (touches TP 51,000), Low: 49,000 (touches SL 49,500).
    The deterministic requirement demands: SL RESOLVES FIRST!
    """
    start_ms = 1_700_000_000_000
    bars = [
        make_1m_bar(start_ms, Decimal(50000), Decimal(50010), Decimal(49990), Decimal(50000)),
        make_1m_bar(start_ms + 60_000, Decimal(50000), Decimal(51500), Decimal(49000), Decimal(50200)),
    ]
    marks = [
        make_mark_bar(start_ms, Decimal(50000)),
        make_mark_bar(start_ms + 60_000, Decimal(50200)),
    ]
    return bars, marks


def create_gap_stop_fixture() -> tuple[list[Bar1m], list[MarkBar1m]]:
    """
    ADVERSE GAP STOP FIXTURE:
    Bar opens below the stop level (LONG position):
    Entry at 50,000, Stop at 49,500.
    Next bar opens at 49,000 (gapped below stop).
    Adverse stop gap must execute at the worse open (49,000), not the stop level (49,500).
    """
    start_ms = 1_700_000_000_000
    bars = [
        make_1m_bar(start_ms, Decimal(50000), Decimal(50010), Decimal(49990), Decimal(50000)),
        make_1m_bar(start_ms + 60_000, Decimal(49000), Decimal(49100), Decimal(48900), Decimal(49050)),
    ]
    marks = [
        make_mark_bar(start_ms, Decimal(50000)),
        make_mark_bar(start_ms + 60_000, Decimal(49050)),
    ]
    return bars, marks


def create_target_gap_fixture() -> tuple[list[Bar1m], list[MarkBar1m]]:
    """
    FAVORABLE TARGET GAP FIXTURE:
    Bar opens favorably beyond target (LONG position):
    Entry at 50,000, Target at 51,000.
    Next bar opens at 51,500.
    Rule mandates: Favorable TP gap is capped at fixed target (51,000) with zero overcredit.
    """
    start_ms = 1_700_000_000_000
    bars = [
        make_1m_bar(start_ms, Decimal(50000), Decimal(50010), Decimal(49990), Decimal(50000)),
        make_1m_bar(start_ms + 60_000, Decimal(51500), Decimal(51600), Decimal(51400), Decimal(51550)),
    ]
    marks = [
        make_mark_bar(start_ms, Decimal(50000)),
        make_mark_bar(start_ms + 60_000, Decimal(51550)),
    ]
    return bars, marks


def create_negative_collateral_fixture() -> tuple[list[Bar1m], list[MarkBar1m]]:
    """
    NEGATIVE COLLATERAL / INSOLVENCY FIXTURE:
    Catastrophic gap loss that pushes equity below zero.
    Must preserve negative equity, latch kill, flag insolvency, and never clip loss at zero.
    """
    start_ms = 1_700_000_000_000
    # Position with 0.05 BTC at 50,000 = 2,500 USDT notional
    # Flash crash to 20,000 USDT -> loss = 0.05 * 30,000 = 1,500 USDT.
    # Starting cash 1,000 USDT -> ending equity -500 USDT!
    bars = [
        make_1m_bar(start_ms, Decimal(50000), Decimal(50010), Decimal(49990), Decimal(50000)),
        make_1m_bar(start_ms + 60_000, Decimal(20000), Decimal(20500), Decimal(19500), Decimal(20000)),
    ]
    marks = [
        make_mark_bar(start_ms, Decimal(50000)),
        make_mark_bar(start_ms + 60_000, Decimal(20000)),
    ]
    return bars, marks


def create_mark_staleness_fixture() -> tuple[list[Bar1m], list[MarkBar1m]]:
    """
    MARK STALENESS FIXTURE:
    Trade bars continue, but mark price is stale (>120 seconds old).
    Rule mandates: Veto entries, do not guess MTM, queue liquidation of open positions.
    """
    start_ms = 1_700_000_000_000
    bars: list[Bar1m] = []
    # 5 minutes of trade bars
    for i in range(5):
        t = start_ms + i * 60_000
        bars.append(make_1m_bar(t, Decimal(50000), Decimal(50050), Decimal(49950), Decimal(50000)))

    # Mark bars only for the first minute, then stops!
    marks = [
        make_mark_bar(start_ms, Decimal(50000)),
    ]
    return bars, marks
