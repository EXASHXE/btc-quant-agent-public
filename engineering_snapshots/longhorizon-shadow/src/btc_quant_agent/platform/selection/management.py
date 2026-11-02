"""One policy kernel for episode replay and user-position supervision."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from math import isfinite

from ..core import ManagementAction, MarketEvent, PositionState, dec, quantize


@dataclass(frozen=True)
class ExitPolicy:
    atr: float | None = None
    target: Decimal | None = None
    trailing_atr: float = 2.5
    partial_at_r: float | None = None  # Off by default; an explicit challenger may enable it.
    partial_fraction: float = 1 / 3
    confirmed_swing: Decimal | None = None
    highest_completed_close: Decimal | None = None
    lowest_completed_close: Decimal | None = None
    thesis_invalid: bool = False
    funding_review_due: bool = False
    funding_source_known: bool = True
    stop_mode: str = "market"

    def __post_init__(self):
        if self.stop_mode != "market":
            raise ValueError("V1_STOP_LIMIT_REQUIRES_SEPARATE_EXECUTION_MODEL")
        if not isfinite(self.trailing_atr) or self.trailing_atr <= 0:
            raise ValueError("INVALID_TRAILING_POLICY")
        if self.atr is not None and (not isfinite(self.atr) or self.atr <= 0):
            raise ValueError("INVALID_ATR_EVIDENCE")
        if not 0 < self.partial_fraction < 1:
            raise ValueError("INVALID_PARTIAL_FRACTION")


def manage(position: PositionState, event: MarketEvent, policy: ExitPolicy) -> ManagementAction:
    def action(kind, reason, stop=None, fraction=None, status="UNCONFIRMED"):
        return ManagementAction(position.id, kind, reason, event.decision_ts, stop, fraction, status)

    if event.decision_ts < position.updated_ts:
        return action("RECONCILE", "POSITION_REPORT_AFTER_OBSERVATION")
    if position.status == "CLOSED":
        return action("RECONCILE", "USER_CONFIRMED_CLOSED")
    if position.status == "STOP_BREACHED":
        return action("EXIT", "REPORTED_FILL_BEYOND_FROZEN_INVALIDATION", status="EXECUTION_UNKNOWN")
    if event.spec.symbol != position.symbol or event.reason(90_000):
        return action("RECONCILE", "SOURCE_OR_IDENTITY_UNAVAILABLE")
    side = 1 if position.direction == "LONG" else -1
    c, q = event.candle, event.quote
    breach = c.low <= float(position.stop) if side == 1 else c.high >= float(position.stop)
    quote_valid = q is not None and q.reason(event.spec, event.decision_ts) is None
    executable_breach = (
        q is not None and quote_valid and side * ((q.bid if side == 1 else q.ask) - position.stop) <= 0
    )
    if breach or executable_breach:
        gap = side * (c.open - float(position.stop)) < 0
        return action("EXIT", "STOP_GAP" if gap else "STOP_BREACHED", status="EXECUTION_UNKNOWN")
    if policy.thesis_invalid:
        return action("EXIT", "FROZEN_THESIS_INVALIDATED", status="EXECUTION_UNKNOWN")
    if not quote_valid or q is None:
        return action("RECONCILE", "EXECUTABLE_QUOTE_UNKNOWN")
    derivative = event.derivatives
    mark_clock = derivative.field_clock("mark_price") if derivative else None
    if (
        event.spec.market == "PERPETUAL"
        and derivative is not None
        and derivative.mark_price is not None
        and mark_clock is not None
        and not derivative.field_reason("mark_price", event.decision_ts, 90_000)
        and mark_clock.provider == event.spec.provider
    ):
        distance = 1 / position.leverage - event.spec.maintenance_margin_rate
        liquidation_proxy = float(position.entry) * (1 - side * distance)
        if side * (derivative.mark_price - liquidation_proxy) / float(position.entry) < 0.03:
            return action("REDUCE", "LIQUIDATION_PROXY_DISTANCE_WARNING", fraction=0.5)
    price = q.bid if side == 1 else q.ask
    if policy.target is not None and side * (price - policy.target) >= 0:
        return action("EXIT", "FROZEN_OBSERVED_MEAN_REACHED", status="EXECUTION_UNKNOWN")
    if policy.funding_review_due and not policy.funding_source_known:
        return action("RECONCILE", "FUNDING_REVIEW_EVIDENCE_UNKNOWN")
    initial_risk = abs(position.entry - position.initial_stop)
    r = float(dec(side) * (price - position.entry) / initial_risk) if initial_risk else 0
    if (
        policy.partial_at_r is not None
        and r >= policy.partial_at_r
        and position.partial_closes == 0
        and 0 < policy.partial_fraction < 1
    ):
        return action("PARTIAL_EXIT", "EXPLICIT_PARTIAL_POLICY", fraction=policy.partial_fraction)
    if policy.target is None and policy.atr is not None and policy.atr > 0:
        extreme = (policy.highest_completed_close if side == 1 else policy.lowest_completed_close) or dec(
            c.close
        )
        suggested = extreme - dec(side * policy.trailing_atr * policy.atr)
        if policy.confirmed_swing is not None:
            buffered = policy.confirmed_swing - dec(side) * max(
                2 * event.spec.tick_size, dec(0.15 * policy.atr)
            )
            suggested = max(suggested, buffered) if side == 1 else min(suggested, buffered)
        if suggested > 0 and side * (suggested - position.stop) > 0:
            suggested = quantize(suggested, event.spec.tick_size, up=side < 0)
            if side * (price - suggested) <= 0:
                return action("EXIT", "PROJECTED_TRAIL_ALREADY_BREACHED", status="EXECUTION_UNKNOWN")
            return action("TIGHTEN_STOP", "NEXT_OBSERVATION_ACTIVATION_AFTER_CONFIRMED_AMENDMENT", suggested)
    return action("HOLD", "STRUCTURE_INTACT")
