"""All prices and 2030 dates below are invented fixtures, never historical samples."""
from dataclasses import replace

from .planner import plan_collection
from .schema import Bar, Batch, ClockProof, HOUR, INTERVALS, MINUTE, Quote, Snapshot
from .source import utc_ms
from .strategy import Engine, PairedComparison

SETUP_END = utc_ms("2030-01-03")


def bar(symbol, interval, end, o, h, low, c):
    return Bar(symbol, interval, end - INTERVALS[interval], end, end - 1,
               o, h, low, c, 1_000.0, end + 200, end + 100, end + 50)


def batch(symbol, interval, bars):
    return Batch(symbol, interval, tuple(bars), bars[0].open_ms, bars[-1].end_ms)


def snapshot(minutes=0, *, symbol="BTCUSDT", include_15m=True, quote=True,
             daily_down=False, four_down=False, false_15m=False, five_lag_minutes=0):
    asof = SETUP_END + minutes * MINUTE + 5_000
    groups = []
    for interval in ("1D", "4H"):
        down = daily_down if interval == "1D" else four_down
        rows = []
        for i in range(32):
            price = (108 - i * 0.25) if down else (92 + i * 0.25)
            end = SETUP_END - (31 - i) * INTERVALS[interval]
            rows.append(bar(symbol, interval, end, price, price + 1, price - 1, price))
        groups.append(batch(symbol, interval, rows))
    prices = [101, 104, 100, 107, 101, 110, 102, 103] * 4
    rows = [bar(symbol, "1H", SETUP_END - (31 - i) * HOUR,
                p, p + 0.8, p - 0.8, p) for i, p in enumerate(prices)]
    rows[-2] = bar(symbol, "1H", SETUP_END - HOUR, 99.5, 100, 98.5, 99)
    rows[-1] = bar(symbol, "1H", SETUP_END, 99, 101, 98.8, 100.5)
    groups.append(batch(symbol, "1H", rows))
    for interval in ("15m", "5m"):
        if interval == "15m" and not include_15m:
            continue
        step = INTERVALS[interval]
        lag = five_lag_minutes * MINUTE if interval == "5m" else 0
        end = (asof - lag) // step * step
        rows = []
        for i in range(32):
            row_end = end - (31 - i) * step
            o, c = (100.8, 100.2) if interval == "15m" and false_15m and row_end > SETUP_END else (100, 100.6)
            rows.append(bar(symbol, interval, row_end, o, 100.9, 99.8, c))
        groups.append(batch(symbol, interval, rows))
    q = Quote(symbol, 100.5, 100.6, 100, 100, asof - 500, asof - 100, asof - 200) if quote else None
    return Snapshot(symbol, asof, ClockProof(asof - 50, asof + 50, asof - 100), tuple(groups), q)


def modify_bar(s, target_interval, index=-1, **changes):
    groups = []
    for group in s.batches:
        if group.interval == target_interval:
            rows = list(group.bars)
            rows[index] = replace(rows[index], **changes)
            group = replace(group, bars=tuple(rows))
        groups.append(group)
    return replace(s, batches=tuple(groups))


def artifacts():
    pairs = []
    cards = []
    for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
        comparison = PairedComparison()
        for minute in (0, 15):
            pair = comparison.review(snapshot(minute, symbol=symbol, include_15m=minute > 0))
            pairs.append(pair)
            cards.append(pair["mtf"])
    for name, kwargs in (("false_trigger", {"false_15m": True}),
                         ("daily_countertrend", {"daily_down": True}),
                         ("four_hour_conflict", {"four_down": True}),
                         ("stale_5m", {"quote": False, "five_lag_minutes": 10})):
        engine = Engine()
        engine.review(snapshot(0, include_15m=False, **kwargs))
        card = engine.review(snapshot(15, **kwargs)).to_dict()
        cards.append({"example": name, "card": card})
    engine = Engine()
    watch = engine.review(snapshot(0, include_15m=False))
    stopped = modify_bar(snapshot(15), "15m", low=watch.plan["hard_stop"])
    cards.append({"example": "stopped_before_entry", "card": engine.review(stopped).to_dict()})
    engine = Engine()
    engine.review(snapshot(0, include_15m=False))
    cards.append({"example": "entry_expired_hold_not_started", "card": engine.review(snapshot(45)).to_dict()})
    for name, value in (("overall_source_veto", replace(snapshot(), source_veto=True)),
                        ("incomplete_bar", modify_bar(snapshot(), "1H", closed=False)),
                        ("no_primary_setup", modify_bar(snapshot(), "1H", close=99.5)),
                        ("unknown_envelope", None)):
        cards.append({"example": name, "card": Engine().review(value).to_dict()})
    plans = [plan_collection(SETUP_END + 5_000).to_dict(),
             plan_collection(SETUP_END + 5_000, [f"COIN{i:02}USDT" for i in range(10)]).to_dict()]
    return {"synthetic_cards.json": {"synthetic_only": True, "cards": cards},
            "paired_comparison.json": {"synthetic_only": True, "pairs": pairs,
                                       "forward_results": None},
            "collector_plans.json": {"offline_only": True, "plans": plans}}
