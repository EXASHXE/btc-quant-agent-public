"""Frozen long-only signal and accounting kernel, gated from empirical use."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from itertools import pairwise

from .source import HOUR, MINUTE, Bar, SourceError, complete_window, digest, require_available

D = Decimal
FAMILIES = ("BREAKOUT", "TREND_PULLBACK", "RANGE_REVERSION")
HORIZONS = (4, 8, 16, 24)


@dataclass(frozen=True)
class Candidate:
    family: str
    hours: int

    def __post_init__(self) -> None:
        if self.family not in FAMILIES or type(self.hours) is not int or self.hours not in HORIZONS:
            raise ValueError("UNREGISTERED_CANDIDATE")

    @property
    def identity(self) -> str:
        return f"{self.family}_{self.hours:02d}H"


@dataclass(frozen=True)
class Decision:
    candidate: str
    symbol: str
    decision_ms: int
    entry_ms: int
    action: str
    risk: Decimal
    regime: str
    input_identity: str


def signal(candidate: Candidate, hours: Sequence[Bar], *, synthetic_test: bool = False) -> Decision:
    if len(hours) != 25:
        raise SourceError("EXACT_25_HOUR_CONTEXT_REQUIRED")
    if len({b.symbol for b in hours}) != 1 or any(
        b.end_ms - b.event_ms != HOUR
        or b.event_ms % HOUR
        or (i and hours[i - 1].end_ms != b.event_ms)
        for i, b in enumerate(hours)
    ):
        raise SourceError("INVALID_HOURLY_FEATURE_CALENDAR")
    latest = hours[-1]
    decision_ms = latest.end_ms + MINUTE
    require_available(hours, decision_ms, synthetic_test=synthetic_test)
    with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)) as context:
        context.prec = 28
        atr = sum(
            (
                max(b.high - b.low, abs(b.high - p.close), abs(b.low - p.close))
                for p, b in pairwise(hours)
            ),
            D(0),
        ) / D(24)
        sma = sum((b.close for b in hours[1:]), D(0)) / D(24)
        ret = latest.close / hours[0].close - 1
        conditions = {
            "BREAKOUT": latest.close > max(b.high for b in hours[:-1]) and latest.close > sma,
            "TREND_PULLBACK": ret > 0
            and latest.low <= sma < latest.close
            and latest.close > latest.open,
            "RANGE_REVERSION": abs(ret) <= D("0.01")
            and latest.close < sma - atr
            and latest.close > latest.open,
        }
        risk = D("1.5") * atr
    return Decision(
        candidate.identity,
        latest.symbol,
        decision_ms,
        decision_ms + MINUTE,
        "LONG" if conditions[candidate.family] else "WAIT",
        risk,
        "UP" if ret > D("0.01") else "DOWN" if ret < D("-0.01") else "RANGE",
        digest([asdict(b) for b in hours]),
    )


@dataclass(frozen=True)
class Friction:
    fee: Decimal
    spread: Decimal
    slippage: Decimal

    def __post_init__(self) -> None:
        if any(not v.is_finite() or v < 0 for v in (self.fee, self.spread, self.slippage)):
            raise ValueError("INVALID_FRICTION")


BASE = Friction(D("0.001"), D("0.0002"), D("0.0003"))
STRESS = Friction(D("0.0015"), D("0.0004"), D("0.0006"))
PARTICIPATION = D("0.001")
NOTIONAL = D(1000)


@dataclass(frozen=True)
class Trade:
    identity: str
    candidate: str
    symbol: str
    entry_ms: int
    exit_ms: int
    reason: str
    gross_R: Decimal
    net_R: Decimal
    taker_fee_R: Decimal
    spread_R: Decimal
    slippage_R: Decimal
    funding_R: Decimal
    mfe_R: Decimal
    mae_R: Decimal
    pnl_usdt: Decimal
    notional_usdt: Decimal
    synthetic_test_only: bool


def execute(
    candidate: Candidate,
    decision: Decision,
    minutes: Sequence[Bar],
    *,
    partition_start: int,
    partition_end: int,
    previous_exit_ms: int | None = None,
    friction: Friction = BASE,
    participation: Decimal = PARTICIPATION,
    notional: Decimal = NOTIONAL,
    synthetic_test: bool = False,
) -> Trade | None:
    with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)) as arithmetic:
        arithmetic.prec = 28
        if decision.candidate != candidate.identity or decision.action not in {"LONG", "WAIT"}:
            raise SourceError("UNREGISTERED_DECISION")
        if not (
            notional.is_finite() and notional > 0 and participation in {D("0.001"), D("0.0001")}
        ):
            raise SourceError("INVALID_CAPITAL_OR_PARTICIPATION")
        if decision.entry_ms != decision.decision_ms + MINUTE:
            raise SourceError("SAME_BAR_OR_INVALID_ENTRY")
        end = decision.entry_ms + candidate.hours * HOUR
        if decision.entry_ms < partition_start + 24 * HOUR or end >= partition_end:
            raise SourceError("PURGED_OR_EMBARGOED_BOUNDARY")
        if previous_exit_ms is not None and decision.entry_ms < previous_exit_ms:
            raise SourceError("OVERLAPPING_POSITION")
        if decision.action == "WAIT":
            return None
        if not decision.risk.is_finite() or decision.risk <= 0:
            raise SourceError("INVALID_RISK")
        # Full window checked before outcome resolution, even if a stop would hit early.
        rows = complete_window(minutes, decision.symbol, decision.entry_ms - MINUTE, end)
        # Participation is a fill-time gate; this minute completes at execution.
        require_available(rows[:1], decision.entry_ms, synthetic_test=synthetic_test)
        if not synthetic_test or any(b.availability_basis != "SYNTHETIC_TEST" for b in rows):
            raise SourceError("EMPIRICAL_REPLAY_SOURCE_GATE_BLOCKED")
        if notional > participation * rows[0].quote_volume:
            return None  # market participation gate, not an invented maker fill
        entry = rows[1].open
        risk = decision.risk
        if not D("0.001") <= risk / entry <= D("0.10"):
            return None
        stop, target = entry - risk, entry + 2 * risk
        mfe = mae = D(0)
        exit_price, exit_ms, reason = rows[-1].close, rows[-1].end_ms, "TIMEOUT"
        for b in rows[1:]:
            if b.low <= stop:
                exit_price, exit_ms, reason = min(stop, b.open), b.end_ms, "SL_FIRST"
                # No attribution of unknown pre-stop extremes from this minute.
                mae = max(mae, (entry - exit_price) / risk)
                mfe = max(mfe, max(D(0), (min(b.open, entry) - entry) / risk))
                break
            mae = max(mae, (entry - b.low) / risk)
            if b.high >= target:
                exit_price, exit_ms, reason = target, b.end_ms, "TP1"
                mfe = max(mfe, D(2))
                break
            mfe = max(mfe, (b.high - entry) / risk)
        with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)) as context:
            context.prec = 28
            turnover = entry + exit_price
            fee_R = turnover * friction.fee / risk
            spread_R = turnover * friction.spread / risk
            slippage_R = turnover * friction.slippage / risk
            gross_R = (exit_price - entry) / risk
            net_R = gross_R - fee_R - spread_R - slippage_R
            pnl = net_R * risk * notional / entry
        identity = digest(
            {
                "candidate": candidate.identity,
                "symbol": decision.symbol,
                "entry_ms": decision.entry_ms,
                "input": decision.input_identity,
            }
        )
        return Trade(
            identity,
            candidate.identity,
            decision.symbol,
            decision.entry_ms,
            exit_ms,
            reason,
            gross_R,
            net_R,
            fee_R,
            spread_R,
            slippage_R,
            D(0),
            max(D(0), mfe),
            max(D(0), mae),
            pnl,
            notional,
            True,
        )


def derived_trade(trade: Trade) -> dict[str, object]:
    """Canonical derived output; synthetic provenance cannot become historic metrics."""
    with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)) as arithmetic:
        arithmetic.prec = 28
        return {
            k: str(v.quantize(D("0.000000000001"))) if isinstance(v, Decimal) else v
            for k, v in asdict(trade).items()
        }
