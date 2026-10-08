"""Frozen eight-candidate historical reconstruction and adverse accounting."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import asdict, dataclass, field
from decimal import Decimal, localcontext
from itertools import pairwise

from .perp_source import (
    CONTEXT,
    DAY,
    HOUR,
    MINUTE,
    Bar,
    Funding,
    SourceError,
    canonical,
    digest,
    funding_complete,
    resample,
)

D = Decimal
NOTIONAL = D("333.333333333333")


@dataclass(frozen=True)
class Candidate:
    family: str
    direction: str
    hours: int

    def __post_init__(self) -> None:
        if self.family not in {"BREAKOUT", "TREND_PULLBACK", "NAIVE"} or (
            self.direction not in {"LONG", "SHORT"}
            or type(self.hours) is not int
            or self.hours not in {4, 12}
        ):
            raise SourceError("UNREGISTERED_STRATEGY_NO_GRID")

    @property
    def identity(self) -> str:
        return f"{self.family}_{self.direction}_{self.hours:02d}H"

    @property
    def side(self) -> int:
        return 1 if self.direction == "LONG" else -1


CANDIDATES = tuple(
    Candidate(f, d, h)
    for f in ("BREAKOUT", "TREND_PULLBACK")
    for d in ("LONG", "SHORT")
    for h in (4, 12)
)
CONTROLS = tuple(Candidate("NAIVE", d, h) for d in ("LONG", "SHORT") for h in (4, 12))


@dataclass(frozen=True)
class Feature:
    symbol: str
    decision: int
    entry: int
    risk: Decimal
    ret24: Decimal
    regime: str
    breakout_long: bool
    breakout_short: bool
    pullback_long: bool
    pullback_short: bool
    identity: str
    grade: str

    def action(self, candidate: Candidate) -> bool:
        if candidate.family == "NAIVE":
            return True
        return (
            getattr(
                self,
                ("breakout" if candidate.family == "BREAKOUT" else "pullback")
                + ("_long" if candidate.direction == "LONG" else "_short"),
            )
            is True
        )


def feature(rows: tuple[Bar, ...]) -> Feature:
    if (
        len(rows) != 25
        or len({b.symbol for b in rows}) != 1
        or any(
            b.end - b.t != HOUR or b.t % HOUR or (i and rows[i - 1].end != b.t)
            for i, b in enumerate(rows)
        )
    ):
        raise SourceError("INVALID_COMPLETED_FEATURE_WINDOW")
    last = rows[-1]
    decision = last.end + MINUTE
    if any(b.available > decision for b in rows) or len({b.grade for b in rows}) != 1:
        raise SourceError("LOOKAHEAD_OR_UNKNOWN_AVAILABLE_AT")
    with localcontext(CONTEXT):
        atr = sum(
            (max(b.h - b.l, abs(b.h - p.c), abs(b.l - p.c)) for p, b in pairwise(rows)),
            D(0),
        ) / D(24)
        sma = sum((b.c for b in rows[1:]), D(0)) / D(24)
        ret = last.c / rows[0].c - 1
        values = (
            last.c > max(b.h for b in rows[:-1]),
            last.c < min(b.l for b in rows[:-1]),
            ret > D("0.01") and last.l <= sma < last.c and last.c > last.o,
            ret < D("-0.01") and last.h >= sma > last.c and last.c < last.o,
        )
        identity = digest(
            [
                (
                    b.t,
                    b.end,
                    b.available,
                    str(b.o),
                    str(b.h),
                    str(b.l),
                    str(b.c),
                    str(b.qv),
                    b.source,
                    b.grade,
                )
                for b in rows
            ]
        )
        return Feature(
            last.symbol,
            decision,
            decision + MINUTE,
            D("1.5") * atr,
            ret,
            "UP" if ret > D("0.01") else "DOWN" if ret < D("-0.01") else "RANGE",
            *values,
            identity,
            last.grade,
        )


@dataclass(frozen=True)
class Series:
    bars: tuple[Bar, ...]
    features: tuple[Feature, ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "bars", canonical(self.bars))
        if len({b.grade for b in self.bars}) != 1:
            raise SourceError("MIXED_DATA_GRADE")
        hours = resample(self.bars, 60)
        object.__setattr__(
            self, "features", tuple(feature(hours[i - 24 : i + 1]) for i in range(24, len(hours)))
        )

    def at(self, t: int) -> Bar:
        i, remainder = divmod(t - self.bars[0].t, MINUTE)
        if remainder or not 0 <= i < len(self.bars):
            raise SourceError("MISSING_REQUESTED_1M")
        return self.bars[i]


@dataclass(frozen=True)
class Trade:
    identity: str
    candidate: str
    symbol: str
    direction: str
    partition: int
    regime: str
    feature_identity: str
    decision_ms: int
    entry_ms: int
    exit_ms: int
    entry_price: Decimal
    exit_price: Decimal
    risk_price: Decimal
    holding_hours: Decimal
    reason: str
    gross_R: Decimal
    net_R: Decimal
    stress_net_R: Decimal
    gross_pnl: Decimal
    net_pnl: Decimal
    stress_net_pnl: Decimal
    fee: Decimal
    spread: Decimal
    slippage: Decimal
    funding: Decimal
    stress_fee: Decimal
    stress_spread: Decimal
    stress_slippage: Decimal
    stress_funding: Decimal
    funding_signed_proxy: Decimal
    funding_events: int
    funding_grade: str
    mfe_R: Decimal
    mae_R: Decimal
    capital: Decimal
    grade: str
    liquidity_stress_filled: bool


@dataclass(frozen=True)
class FillResult:
    status: str
    trade: Trade | None


def execute(
    series: Series,
    f: Feature,
    candidate: Candidate,
    partition: int,
    start: int,
    end: int,
    funding: tuple[Funding, ...],
    *,
    proxy: bool,
    previous_exit: int = 0,
    delay: int = 0,
) -> FillResult:
    with localcontext(CONTEXT):
        if f.symbol != series.bars[0].symbol or f.grade != series.bars[0].grade:
            raise SourceError("FEATURE_SOURCE_MISMATCH")
        if f.entry != f.decision + MINUTE or delay not in {0, MINUTE}:
            raise SourceError("SAME_BAR_OR_UNREGISTERED_LATENCY")
        offset, remainder = (
            divmod(f.decision - series.features[0].decision, HOUR) if series.features else (-1, 1)
        )
        if remainder or not 0 <= offset < len(series.features) or series.features[offset] != f:
            raise SourceError("FEATURE_LINEAGE_OR_CLOCK_NOT_BOUND")
        entry = f.entry + delay
        deadline = entry + candidate.hours * HOUR
        if entry < start + 12 * HOUR or deadline > end - 12 * HOUR:
            return FillResult("EMBARGO", None)
        if not f.action(candidate):
            return FillResult("WAIT", None)
        if entry < previous_exit:
            return FillResult("POSITION_OPEN_WAIT", None)
        if not f.risk.is_finite() or f.risk <= 0:
            return FillResult("RISK_WAIT", None)
        first = series.at(entry)
        liquidity = series.at(entry - 2 * MINUTE)  # latest completed minute available after 60s lag
        if liquidity.available > entry:
            raise SourceError("LATE_LIQUIDITY")
        risk, raw_entry = f.risk, first.o
        if not D("0.002") <= risk / raw_entry <= D("0.05"):
            return FillResult("RISK_WAIT", None)
        if first.qv <= 0 or NOTIONAL > liquidity.qv * D("0.001"):
            return FillResult("NO_FILL", None)
        side = candidate.side
        stop, target = raw_entry - side * risk, raw_entry + side * 2 * risk
        raw_exit, exit_ms, reason = series.at(deadline - MINUTE).c, deadline, "TIMEOUT"
        mfe = mae = D(0)
        for t in range(entry, deadline, MINUTE):
            b = series.at(t)
            if b.qv <= 0:
                raise SourceError("STALE_ZERO_VOLUME_OUTCOME_NO_ASSUMED_FILL")
            stopped = b.l <= stop if side == 1 else b.h >= stop
            targeted = b.h >= target if side == 1 else b.l <= target
            if stopped:
                raw_exit = min(stop, b.o) if side == 1 else max(stop, b.o)
                exit_ms, reason = b.end, "SL_FIRST"
                mae = max(mae, -side * (raw_exit - raw_entry) / risk)
                mfe = max(mfe, side * (b.o - raw_entry) / risk)
                break
            mae = max(mae, side * (raw_entry - (b.l if side == 1 else b.h)) / risk)
            if targeted:
                raw_exit, exit_ms, reason = target, b.end, "TP1"
                mfe = max(mfe, D(2))
                break
            mfe = max(mfe, side * ((b.h if side == 1 else b.l) - raw_entry) / risk)
        quantity = NOTIONAL / raw_entry
        gross_pnl = quantity * side * (raw_exit - raw_entry)
        base_funding = stress_funding = signed_funding = D(0)
        if proxy:
            applicable = tuple(
                Funding(t, D(8), D("0.0004"))
                for t in range((entry // (8 * HOUR) + 1) * 8 * HOUR, exit_ms + 1, 8 * HOUR)
            )
        else:
            partition_funding = tuple(x for x in funding if start <= x.t < end)
            if not funding_complete(partition_funding, start, end):
                raise SourceError("INCOMPLETE_FUNDING_MUST_USE_PROXY")
            times = tuple(x.t for x in funding)
            applicable = funding[bisect_right(times, entry) : bisect_right(times, exit_ms)]
        for event in applicable:
            # Settlement-minute high is explicitly a conservative price proxy, not mark data.
            funding_notional = quantity * max(raw_entry, series.at((event.t // MINUTE) * MINUTE).h)
            adverse = D("0.0004") if proxy else max(D(0), side * event.rate)
            base_funding += funding_notional * adverse
            stress_funding += funding_notional * 2 * max(adverse, D("0.0004"))
            signed_funding += funding_notional * (adverse if proxy else side * event.rate)

        def costs(multiplier: int) -> tuple[Decimal, Decimal, Decimal]:
            half_spread = D("0.0002") * multiplier
            slip = D("0.0003") * multiplier
            modeled_entry = raw_entry * (1 + side * (half_spread + slip))
            modeled_exit = raw_exit * (1 - side * (half_spread + slip))
            return (
                quantity * (modeled_entry + modeled_exit) * D("0.0006") * multiplier,
                quantity * (raw_entry + raw_exit) * half_spread,
                quantity * (raw_entry + raw_exit) * slip,
            )

        fee, spread, slip = costs(1)
        stress_fee, stress_spread, stress_slip = costs(2)
        net = gross_pnl - fee - spread - slip - base_funding
        stress_net = gross_pnl - stress_fee - stress_spread - stress_slip - stress_funding
        dollar_risk = quantity * risk
        identity = digest(
            {
                "candidate": candidate.identity,
                "feature": f.identity,
                "entry": entry,
                "symbol": f.symbol,
                "delay": delay,
            }
        )
        return FillResult(
            "FILLED",
            Trade(
                identity,
                candidate.identity,
                f.symbol,
                candidate.direction,
                partition,
                f.regime,
                f.identity,
                f.decision,
                entry,
                exit_ms,
                raw_entry,
                raw_exit,
                risk,
                D(exit_ms - entry) / HOUR,
                reason,
                gross_pnl / dollar_risk,
                net / dollar_risk,
                stress_net / dollar_risk,
                gross_pnl,
                net,
                stress_net,
                fee,
                spread,
                slip,
                base_funding,
                stress_fee,
                stress_spread,
                stress_slip,
                stress_funding,
                signed_funding,
                len(applicable),
                "PROXY_STRESS_ONLY" if proxy else "ACTUAL_RATE_ADVERSE_PRICE_PROXY",
                max(D(0), mfe),
                max(D(0), mae),
                NOTIONAL,
                f.grade,
                NOTIONAL <= liquidity.qv * D("0.0001"),
            ),
        )


def derived(trade: Trade) -> dict[str, object]:
    with localcontext(CONTEXT):
        return {
            k: format(v.quantize(D("0.000000000001")), "f") if isinstance(v, Decimal) else v
            for k, v in asdict(trade).items()
        }


def bootstrap(values: list[tuple[int, Decimal]], start: int) -> dict[str, object]:
    # Fixed SHA-based block draws avoid Python RNG/version-dependent digests.
    with localcontext(CONTEXT):
        blocks: dict[int, tuple[Decimal, int]] = {}
        for t, v in values:
            block = (t - start) // (7 * DAY)
            total, n = blocks.get(block, (D(0), 0))
            blocks[block] = total + v, n + 1
        ordered = [blocks[b] for b in sorted(blocks)]
        if not ordered:
            return {"blocks": 0, "lower_95": None, "upper_95": None, "lower_bonferroni": None}
        draws = []
        for replicate in range(2000):
            total, n = D(0), 0
            for draw in range(len(ordered)):
                raw = hashlib_bytes(f"G2R2:620262:{replicate}:{draw}")
                value, count = ordered[int.from_bytes(raw[:8], "big") % len(ordered)]
                total += value
                n += count
            draws.append(total / n)
        draws.sort()

        def q(fraction: Decimal) -> str:
            return format(
                draws[int((len(draws) - 1) * fraction)].quantize(D("0.000000000001")), "f"
            )

        return {
            "blocks": len(ordered),
            "replicates": 2000,
            "lower_95": q(D("0.025")),
            "upper_95": q(D("0.975")),
            "lower_bonferroni": q(D("0.003125")),
            "common_shock_cluster": "UTC seven-day entry-time blocks jointly across assets",
        }


def hashlib_bytes(value: str) -> bytes:
    import hashlib

    return hashlib.sha256(value.encode("ascii")).digest()
