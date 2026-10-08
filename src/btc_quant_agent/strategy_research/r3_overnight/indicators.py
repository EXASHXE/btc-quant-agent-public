"""Deterministic technical indicators for G2 R3 overnight discovery."""

from decimal import Decimal

from btc_quant_agent.strategy_research.r3_overnight.types import Bar1h, Bar1m, Bar4h


def aggregate_1m_to_1h(bars_1m: list[Bar1m]) -> list[Bar1h]:
    """
    Aggregate completed 1m bars into 1h bars aligned to UTC epoch hour boundaries.
    Each 1h bar must contain exactly 60 contiguous 1m bars; gaps invalidate the hour.
    """
    bars_by_hour: dict[int, list[Bar1m]] = {}
    for bar in bars_1m:
        hour_open = (bar.timestamp_ms // 3_600_000) * 3_600_000
        bars_by_hour.setdefault(hour_open, []).append(bar)

    result_1h: list[Bar1h] = []
    for hour_open in sorted(bars_by_hour.keys()):
        hour_bars = sorted(bars_by_hour[hour_open], key=lambda b: b.timestamp_ms)
        if len(hour_bars) != 60:
            # Incomplete hour; missing minutes invalidate the bar
            continue
        
        # Verify contiguous 1m timestamps
        expected_ts = hour_open
        is_contiguous = True
        for b in hour_bars:
            if b.timestamp_ms != expected_ts:
                is_contiguous = False
                break
            expected_ts += 60_000
        if not is_contiguous:
            continue

        symbol = hour_bars[0].symbol
        open_val = hour_bars[0].open
        high_val = max(b.high for b in hour_bars)
        low_val = min(b.low for b in hour_bars)
        close_val = hour_bars[-1].close
        vol_val = sum(b.volume for b in hour_bars)

        result_1h.append(
            Bar1h(
                timestamp_ms=hour_open,
                open=open_val,
                high=high_val,
                low=low_val,
                close=close_val,
                volume=vol_val,
                symbol=symbol,
                bar_count=len(hour_bars),
            )
        )
    return result_1h


def aggregate_1m_to_4h(bars_1m: list[Bar1m]) -> list[Bar4h]:
    """
    Aggregate completed 1m bars into 4h bars aligned to UTC epoch 4h boundaries.
    Each 4h bar must contain exactly 240 contiguous 1m bars.
    """
    bars_by_4h: dict[int, list[Bar1m]] = {}
    for bar in bars_1m:
        four_h_open = (bar.timestamp_ms // 14_400_000) * 14_400_000
        bars_by_4h.setdefault(four_h_open, []).append(bar)

    result_4h: list[Bar4h] = []
    for four_h_open in sorted(bars_by_4h.keys()):
        period_bars = sorted(bars_by_4h[four_h_open], key=lambda b: b.timestamp_ms)
        if len(period_bars) != 240:
            continue
        
        expected_ts = four_h_open
        is_contiguous = True
        for b in period_bars:
            if b.timestamp_ms != expected_ts:
                is_contiguous = False
                break
            expected_ts += 60_000
        if not is_contiguous:
            continue

        symbol = period_bars[0].symbol
        open_val = period_bars[0].open
        high_val = max(b.high for b in period_bars)
        low_val = min(b.low for b in period_bars)
        close_val = period_bars[-1].close
        vol_val = sum(b.volume for b in period_bars)

        result_4h.append(
            Bar4h(
                timestamp_ms=four_h_open,
                open=open_val,
                high=high_val,
                low=low_val,
                close=close_val,
                volume=vol_val,
                symbol=symbol,
                bar_count=len(period_bars),
            )
        )
    return result_4h


def compute_true_ranges_1h(bars_1h: list[Bar1h]) -> list[Decimal]:
    """
    Compute True Range series for 1h bars:
    TR_t = max(H_t - L_t, abs(H_t - C_{t-1}), abs(L_t - C_{t-1}))
    First bar True Range is H_0 - L_0.
    """
    if not bars_1h:
        return []
    trs: list[Decimal] = []
    for i in range(len(bars_1h)):
        bar = bars_1h[i]
        hl = bar.high - bar.low
        if i == 0:
            trs.append(hl)
        else:
            prev_close = bars_1h[i - 1].close
            hc = abs(bar.high - prev_close)
            lc = abs(bar.low - prev_close)
            trs.append(max(hl, hc, lc))
    return trs


def compute_true_ranges_4h(bars_4h: list[Bar4h]) -> list[Decimal]:
    """Compute True Range series for 4h bars."""
    if not bars_4h:
        return []
    trs: list[Decimal] = []
    for i in range(len(bars_4h)):
        bar = bars_4h[i]
        hl = bar.high - bar.low
        if i == 0:
            trs.append(hl)
        else:
            prev_close = bars_4h[i - 1].close
            hc = abs(bar.high - prev_close)
            lc = abs(bar.low - prev_close)
            trs.append(max(hl, hc, lc))
    return trs


def compute_atr20_1h(bars_1h: list[Bar1h]) -> Decimal | None:
    """
    Compute arithmetic mean of 20 hourly True Ranges using prior closes.
    Requires at least 21 completed 1h bars so that 20 True Ranges with prior close exist.
    """
    if len(bars_1h) < 21:
        return None
    trs = compute_true_ranges_1h(bars_1h)
    # Take the last 20 TRs (which all have prior closes)
    last_20_trs = trs[-20:]
    return sum(last_20_trs) / Decimal(20)


def compute_atr20_4h(bars_4h: list[Bar4h]) -> Decimal | None:
    """
    Compute arithmetic mean of 20 4-hourly True Ranges using prior closes.
    Requires at least 21 completed 4h bars.
    """
    if len(bars_4h) < 21:
        return None
    trs = compute_true_ranges_4h(bars_4h)
    last_20_trs = trs[-20:]
    return sum(last_20_trs) / Decimal(20)


def compute_ema_series(closes: list[Decimal], period: int) -> list[Decimal | None]:
    """
    Compute EMA series initialized with SMA seed of length N.
    alpha = 2 / (period + 1)
    Values before index (period - 1) are None.
    """
    if len(closes) < period:
        return [None] * len(closes)
    
    result: list[Decimal | None] = [None] * (period - 1)
    # SMA seed
    sma_seed = sum(closes[:period]) / Decimal(period)
    result.append(sma_seed)

    alpha = Decimal(2) / Decimal(period + 1)
    one_minus_alpha = Decimal(1) - alpha

    current_ema = sma_seed
    for close in closes[period:]:
        current_ema = (alpha * close) + (one_minus_alpha * current_ema)
        result.append(current_ema)
    return result


def compute_er12_4h(bars_4h: list[Bar4h]) -> Decimal | None:
    """
    Compute 12-bar Efficiency Ratio on 4h bars:
    displacement = abs(close_t - close_{t-12})
    path = sum(abs(close_i - close_{i-1}) for i in t-11..t)
    ER12 = displacement / path
    Zero denominator yields Decimal('0').
    Requires at least 13 completed 4h bars.
    """
    if len(bars_4h) < 13:
        return None
    
    closes = [b.close for b in bars_4h]
    displacement = abs(closes[-1] - closes[-13])
    path = sum(abs(closes[i] - closes[i - 1]) for i in range(len(closes) - 12, len(closes)))
    if path == Decimal(0):
        return Decimal(0)
    return displacement / path
