"""Finite invented-fixture contract. No I/O, scoring, source adapters, or order submission.

USDT cash events use eight decimal places, ROUND_HALF_EVEN, and FIFO cost basis.
This convention and ordinary 2/5bp fees are synthetic references, not account evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, Context, Decimal, localcontext
from functools import wraps

ZERO = Decimal(0)
CASH = Decimal("0.00000001")
CONTEXT = Context(prec=80, rounding=ROUND_HALF_EVEN)
LABEL = "INVENTED_SYNTHETIC_ONLY_NOT_CALIBRATED"


def financial(function):
    """Keep fixture results independent of the caller's Decimal context."""

    @wraps(function)
    def call(*args, **kwargs):
        with localcontext(CONTEXT):
            return function(*args, **kwargs)

    return call


def decimal(value: str | Decimal) -> Decimal:
    if not isinstance(value, (str, Decimal)):
        raise TypeError("DECIMAL_STRING_REQUIRED")
    try:
        result = Decimal(value)
    except Exception as exc:
        raise ValueError("INVALID_DECIMAL") from exc
    if not result.is_finite():
        raise ValueError("NONFINITE_INPUT")
    if (
        len(result.as_tuple().digits) > 24
        or result.adjusted() > 12
        or result.as_tuple().exponent < -24
    ):
        raise ValueError("DECIMAL_OUTSIDE_FINITE_CONTRACT")
    return result


@financial
def money(value: Decimal) -> Decimal:
    return value.quantize(CASH, rounding=ROUND_HALF_EVEN)


def clock(value: int) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("INVALID_CLOCK")
    return value


@dataclass(frozen=True)
class Filters:
    tick: Decimal
    step: Decimal
    min_notional: Decimal
    valid_from: int = 0
    valid_until: int = 10**12

    @financial
    def __post_init__(self):
        for name in ("tick", "step", "min_notional"):
            object.__setattr__(self, name, decimal(getattr(self, name)))
        if self.tick <= 0 or self.step <= 0 or self.min_notional < 0:
            raise ValueError("INVALID_FILTERS")
        if clock(self.valid_from) >= clock(self.valid_until):
            raise ValueError("INVALID_FILTER_WINDOW")

    @financial
    def round_price(self, price: str | Decimal, buy: bool) -> Decimal:
        value = decimal(price)
        if value <= 0 or type(buy) is not bool:
            raise ValueError("INVALID_PRICE_ROUNDING")
        mode = ROUND_CEILING if buy else ROUND_FLOOR
        return (value / self.tick).to_integral_value(rounding=mode) * self.tick

    @financial
    def round_quantity(self, quantity: str | Decimal) -> Decimal:
        value = decimal(quantity)
        if value < 0:
            raise ValueError("NEGATIVE_QUANTITY")
        return (value / self.step).to_integral_value(rounding=ROUND_FLOOR) * self.step


@dataclass(frozen=True)
class Quote:
    bid: Decimal
    ask: Decimal
    observed_at: int
    known_at: int
    max_age: int = 100
    sequence_valid: bool = True

    @financial
    def __post_init__(self):
        object.__setattr__(self, "bid", decimal(self.bid))
        object.__setattr__(self, "ask", decimal(self.ask))
        if self.bid <= 0 or self.ask < self.bid or self.sequence_valid is not True:
            raise ValueError("INVALID_QUOTE")
        if clock(self.known_at) < clock(self.observed_at) or clock(self.max_age) == 0:
            raise ValueError("INVALID_QUOTE_CLOCK")

    @property
    @financial
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / 2


@dataclass(frozen=True)
class Fees:
    maker: Decimal = Decimal("0.0002")
    taker: Decimal = Decimal("0.0005")
    currency: str = "USDT"

    def __post_init__(self):
        for name in ("maker", "taker"):
            object.__setattr__(self, name, decimal(getattr(self, name)))
            if not ZERO <= getattr(self, name) <= 1:
                raise ValueError("INVALID_FEE_RATE")
        if self.currency != "USDT":
            raise ValueError("FEE_CURRENCY_CONTRACT_MISSING")

    def rate(self, role: str) -> Decimal:
        if role not in ("MAKER", "TAKER"):
            raise ValueError("FILL_LIQUIDITY_ROLE_REQUIRED")
        return self.maker if role == "MAKER" else self.taker


@dataclass(frozen=True)
class Fill:
    event_id: str
    action: str
    quantity: Decimal
    price: Decimal
    role: str
    executed_at: int
    known_at: int
    source_known_at: int
    quote: Quote
    ack_at: int
    order_type: str = "LIMIT"
    extra_spread_cash: Decimal = ZERO
    external_impact_cash: Decimal = ZERO
    impact_basis: str = "IN_FILL"

    @financial
    def __post_init__(self):
        for name in ("quantity", "price", "extra_spread_cash", "external_impact_cash"):
            object.__setattr__(self, name, decimal(getattr(self, name)))
        if (
            not isinstance(self.event_id, str)
            or not self.event_id
            or self.action not in ("ENTRY", "EXIT")
        ):
            raise ValueError("INVALID_FILL_ID_OR_ACTION")
        if self.quantity <= 0 or self.price <= 0 or self.role not in ("MAKER", "TAKER"):
            raise ValueError("INVALID_FILL")
        if not isinstance(self.quote, Quote) or self.order_type not in ("LIMIT", "MARKET"):
            raise ValueError("FILL_PROVENANCE_REQUIRED")
        if self.order_type == "MARKET" and self.role != "TAKER":
            raise ValueError("MARKET_MAKER_CONFLICT")
        for value in (self.executed_at, self.known_at, self.source_known_at, self.ack_at):
            clock(value)
        if not self.quote.known_at <= self.source_known_at < self.executed_at <= self.known_at:
            raise ValueError("FILL_SOURCE_CHRONOLOGY")
        if self.ack_at < self.known_at:
            raise ValueError("ACK_BEFORE_FILL_KNOWN")
        if self.executed_at - self.quote.observed_at > self.quote.max_age:
            raise ValueError("STALE_QUOTE")
        if self.extra_spread_cash != 0:
            raise ValueError("SPREAD_ALREADY_IN_FILL")
        if self.external_impact_cash < 0 or self.impact_basis not in (
            "IN_FILL",
            "DISTINCT_NOT_IN_FILL",
        ):
            raise ValueError("INVALID_IMPACT_BASIS")
        if self.external_impact_cash and self.impact_basis != "DISTINCT_NOT_IN_FILL":
            raise ValueError("IMPACT_ALREADY_IN_FILL")


@dataclass(frozen=True)
class Funding:
    event_id: str
    settled_at: int
    known_at: int
    source_known_at: int | None
    mark: Decimal | None
    rate: Decimal | None
    economic_exposure: Decimal | None
    boundary_verified: bool = False

    def __post_init__(self):
        if not isinstance(self.event_id, str) or not self.event_id:
            raise ValueError("INVALID_FUNDING_ID")
        clock(self.settled_at)
        clock(self.known_at)
        if self.source_known_at is not None:
            clock(self.source_known_at)
        for name in ("mark", "rate", "economic_exposure"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, decimal(value))


@dataclass(frozen=True)
class FundingCoverage:
    """Bounded invented evidence of all settlements, including verified absence.

    A witness is an explicit fixture assertion, not validation of a real provider.
    The window and expected identities are checked at every receiver-as-of view.
    """

    start_at: int
    end_at: int
    known_at: int
    witness_id: str
    expected_settlements: tuple[str, ...]

    def __post_init__(self):
        if not clock(self.start_at) <= clock(self.end_at) <= clock(self.known_at):
            raise ValueError("COVERAGE_CHRONOLOGY")
        if not isinstance(self.witness_id, str) or not self.witness_id.startswith("SYNTHETIC:"):
            raise ValueError("SYNTHETIC_COVERAGE_WITNESS_REQUIRED")
        if not isinstance(self.expected_settlements, tuple):
            raise TypeError("IMMUTABLE_SETTLEMENT_IDENTITIES_REQUIRED")
        if any(not isinstance(x, str) or not x for x in self.expected_settlements):
            raise ValueError("INVALID_COVERAGE_IDENTITIES")
        if len(set(self.expected_settlements)) != len(self.expected_settlements):
            raise ValueError("DUPLICATE_COVERAGE_IDENTITY")


@dataclass(frozen=True)
class Protection:
    source_known_at: int
    prerequisite_ack_at: int
    requested_at: int
    activation_ack_at: int

    def __post_init__(self):
        for value in (
            self.source_known_at,
            self.prerequisite_ack_at,
            self.requested_at,
            self.activation_ack_at,
        ):
            clock(value)
        if not self.source_known_at < self.requested_at <= self.activation_ack_at:
            raise ValueError("PROTECTION_CHRONOLOGY")
        if self.requested_at < self.prerequisite_ack_at:
            raise ValueError("PROTECTION_BEFORE_PREREQUISITE_ACK")

    def active(self, trigger_at: int) -> bool:
        # Equal-clock trigger/activation ordering is deliberately not inferred.
        return clock(trigger_at) > self.activation_ack_at


@financial
def stop_outcome(
    side: int,
    kind: str,
    trigger: str | Decimal,
    observed: str | Decimal,
    quantity: str | Decimal,
    fill_price: str | Decimal,
    filled_quantity: str | Decimal,
    limit: str | Decimal | None = None,
) -> dict:
    if type(side) is not int or side not in (-1, 1) or kind not in ("MARKET", "LIMIT"):
        raise ValueError("INVALID_STOP_CONTRACT")
    trigger, observed, quantity, fill_price, filled_quantity = map(
        decimal, (trigger, observed, quantity, fill_price, filled_quantity)
    )
    if min(trigger, observed, quantity, fill_price) <= 0 or not 0 <= filled_quantity <= quantity:
        raise ValueError("INVALID_STOP_INPUT")
    triggered = side * (observed - trigger) <= 0
    if kind == "LIMIT":
        if limit is None or decimal(limit) <= 0:
            raise ValueError("STOP_LIMIT_PRICE_REQUIRED")
        # Long closing sell cannot sell below limit; short closing buy cannot buy above it.
        eligible = side * (fill_price - decimal(limit)) >= 0
    else:
        eligible = True
    filled = filled_quantity if triggered and eligible else ZERO
    return {
        "triggered": triggered,
        "filled": filled,
        "remaining": quantity - filled,
        "fill_price": fill_price if filled else None,
    }


class SyntheticLedger:
    """One directional episode, multiple entries followed by FIFO partial exits.

    A snapshot is a receiver-as-of view. Funding eligibility also checks economic
    settlement inventory and an explicitly verified synthetic boundary witness.
    """

    def __init__(self, side: int, filters: Filters, fees: Fees | None = None):
        if type(side) is not int or side not in (-1, 1):
            raise ValueError("INVALID_SIDE")
        if not isinstance(filters, Filters):
            raise TypeError("FILTER_CONTRACT_REQUIRED")
        if fees is not None and not isinstance(fees, Fees):
            raise TypeError("FEE_CONTRACT_REQUIRED")
        self.side, self.filters, self.fees = side, filters, fees or Fees()
        self._fills: dict[str, Fill] = {}
        self._funding: dict[str, Funding] = {}

    @financial
    def add_fill(self, fill: Fill) -> bool:
        if not isinstance(fill, Fill):
            raise TypeError("FILL_CONTRACT_REQUIRED")
        existing = self._fills.get(fill.event_id)
        if existing is not None:
            if existing != fill:
                raise ValueError("CONFLICTING_FILL_ID")
            return False
        if fill.event_id in self._funding:
            raise ValueError("CONFLICTING_EVENT_KIND")
        f = self.filters
        if not f.valid_from <= fill.executed_at < f.valid_until:
            raise ValueError("FILTER_NOT_VALID_AT_FILL")
        if fill.quantity % f.step or fill.price % f.tick:
            raise ValueError("OFF_GRID_FILL")
        if fill.quantity * fill.price < f.min_notional:
            raise ValueError("BELOW_MIN_NOTIONAL")
        buy = self.side == 1 if fill.action == "ENTRY" else self.side == -1
        marketable = fill.price >= fill.quote.ask if buy else fill.price <= fill.quote.bid
        if fill.role == "MAKER" and marketable:
            raise ValueError("MARKETABLE_MAKER_CONFLICT")
        self._position([*self._fills.values(), fill])  # Validate before mutation.
        self._fills[fill.event_id] = fill
        return True

    def add_funding(self, event: Funding) -> bool:
        if not isinstance(event, Funding):
            raise TypeError("FUNDING_CONTRACT_REQUIRED")
        existing = self._funding.get(event.event_id)
        if existing is not None:
            if existing != event:
                raise ValueError("CONFLICTING_SETTLEMENT_ID")
            return False
        if event.event_id in self._fills:
            raise ValueError("CONFLICTING_EVENT_KIND")
        self._funding[event.event_id] = event
        return True

    @financial
    def _position(self, fills: list[Fill]) -> dict:
        fills = sorted(fills, key=lambda x: (x.executed_at, x.event_id))
        lots: list[list] = []
        entered = exited = realized = mid_gross = drag = rounding = ZERO
        seen_exit = False
        actions_at: dict[int, set[str]] = {}
        for fill in fills:
            actions_at.setdefault(fill.executed_at, set()).add(fill.action)
            if len(actions_at[fill.executed_at]) > 1:
                raise ValueError("SAME_CLOCK_FILL_AMBIGUITY")
            if fill.action == "ENTRY":
                if seen_exit:
                    raise ValueError("ENTRY_AFTER_EXIT_OUTSIDE_EPISODE")
                entered += fill.quantity
                lots.append([fill.quantity, fill])
                continue
            seen_exit = True
            exited += fill.quantity
            remaining = fill.quantity
            raw_pnl = ZERO
            for lot in lots:
                matched = min(lot[0], remaining)
                entry = lot[1]
                raw_pnl += self.side * matched * (fill.price - entry.price)
                mid_gross += self.side * matched * (fill.quote.mid - entry.quote.mid)
                drag += (
                    self.side
                    * matched
                    * (entry.price - entry.quote.mid + fill.quote.mid - fill.price)
                )
                lot[0] -= matched
                remaining -= matched
            if remaining:
                raise ValueError("EXIT_EXCEEDS_INVENTORY")
            realized += money(raw_pnl)
            rounding += money(raw_pnl) - raw_pnl
        if mid_gross - drag + rounding != realized:
            raise ValueError("SIGNED_PRICE_CONSERVATION_FAILED")
        return {
            "lots": lots,
            "entered": entered,
            "exited": exited,
            "realized": realized,
            "mid_gross": mid_gross,
            "fill_drag": drag,
            "rounding": rounding,
        }

    @financial
    def snapshot(
        self,
        as_of: int,
        mark: str | Decimal | None = None,
        leverage: str | Decimal = "1",
        funding_coverage: FundingCoverage | None = None,
    ) -> dict:
        clock(as_of)
        leverage = decimal(leverage)
        if leverage <= 0:
            raise ValueError("INVALID_SNAPSHOT_CONTRACT")
        if funding_coverage is not None and not isinstance(funding_coverage, FundingCoverage):
            raise TypeError("BOUNDED_FUNDING_COVERAGE_REQUIRED")
        fills = [f for f in self._fills.values() if f.known_at <= as_of]
        state = self._position(fills)
        fees = sum((money(f.quantity * f.price * self.fees.rate(f.role)) for f in fills), ZERO)
        other = sum((money(f.external_impact_cash) for f in fills), ZERO)
        funding_cash = ZERO
        coverage = funding_coverage
        incomplete = coverage is None
        if coverage is not None:
            first_fill = min((f.executed_at for f in fills), default=as_of)
            observed_ids = {
                e.event_id
                for e in self._funding.values()
                if coverage.start_at <= e.settled_at <= coverage.end_at
            }
            incomplete = not (
                coverage.start_at <= first_fill <= as_of <= coverage.end_at
                and coverage.known_at <= as_of
                and set(coverage.expected_settlements) == observed_ids
            )
        for event in self._funding.values():
            if event.known_at > as_of:
                if event.settled_at <= as_of:
                    incomplete = True
                continue
            economic = [f for f in fills if f.executed_at < event.settled_at]
            exposure = self.side * sum(
                (f.quantity if f.action == "ENTRY" else -f.quantity for f in economic), ZERO
            )
            valid = (
                event.source_known_at is not None
                and event.settled_at <= event.source_known_at <= event.known_at
                and event.mark is not None
                and event.mark > 0
                and event.rate is not None
                and abs(event.rate) <= 1
                and event.economic_exposure is not None
                and event.economic_exposure == exposure
                and event.boundary_verified is True
                # A nominal timestamp or caller bool never resolves the venue's
                # +/-15 second membership uncertainty. This finite contract
                # quarantines all such fills instead of inventing ordering.
                and not any(abs(f.executed_at - event.settled_at) <= 15000 for f in fills)
                and coverage is not None
                and coverage.start_at <= event.settled_at <= coverage.end_at
                and event.event_id in coverage.expected_settlements
            )
            if not valid:
                incomplete = True
                continue
            funding_cash += money(-event.economic_exposure * event.mark * event.rate)
        remaining = state["entered"] - state["exited"]
        unrealized = None
        if mark is not None:
            mark = decimal(mark)
            if mark <= 0:
                raise ValueError("INVALID_VALUATION_MARK")
            unrealized = money(
                sum((self.side * q * (mark - entry.price) for q, entry in state["lots"]), ZERO)
            )
        elif not remaining:
            unrealized = ZERO
        notional = sum((f.quantity * f.price for f in fills if f.action == "ENTRY"), ZERO)
        known_cash = state["realized"] - fees + funding_cash - other
        complete = not incomplete
        net = known_cash if complete else None
        status = (
            "COST_INCOMPLETE"
            if incomplete
            else "NO_FILL"
            if not notional
            else "OPEN_INVENTORY"
            if remaining
            else "COMPLETE"
        )
        return {
            "label": LABEL,
            "status": status,
            "entered": state["entered"],
            "exited": state["exited"],
            "remaining": remaining,
            "signed_inventory": self.side * remaining,
            "trading_cash": state["realized"],
            "mid_gross": state["mid_gross"],
            "fill_drag": state["fill_drag"],
            "trading_rounding": state["rounding"],
            "fees": fees,
            "other_cash": other,
            "funding_cash": funding_cash if complete else None,
            "known_funding_cash": funding_cash,
            "known_cash": known_cash,
            "net_cash": net,
            "unrealized": unrealized,
            "entry_notional": notional,
            "net_bps": net * 10000 / notional if status == "COMPLETE" and notional else None,
            "margin_roi": None,
            "leverage": leverage,
        }
