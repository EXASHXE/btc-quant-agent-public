"""Frozen mathematical constants, authority SHAs, and Decimal arithmetic rules for G2 R3 Oracle."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, Context, Decimal, localcontext
from enum import IntEnum

TASK_ID = "V06_G2_R3_PARALLEL_P0_OFFLINE_PREPARATION"
ROLE_ID = "GEMINI_B"
ROLE_BRANCH = "feature/v06-bline-g2-overnight-verifier-b"
ROLE_DIR = "g2-overnight-verifier-b"

CONTROLLER_DISPATCH_SHA = "56f8a9faa1a4539124ab006b49bf42b6e7c997e3"
FROZEN_CODE_BASE_SHA = "e0ff8c3473de4bfa3e66fe7928d42992a4d38a32"
METHOD_ADDENDUM_HEAD_SHA = "cf2d5cc33774cdcff7d709636305bba830e977ef"
METHOD_ADDENDUM_COMMIT_SHA = "35d2b8488fd6fbdab0d3d7ff8cf2b84ee5b60b6f"
ORIGINAL_DESIGN_SHA = "e5b2006a89441f7eb2ec900e508aff451106b87a"
SOURCE_AUDIT_SHA = "12793bc04db7414d11a0961684fd14f5df3ce16e"

REAL_FUNDS_WRITE_AUTHORITY = "NONE"
EMPIRICAL_EXECUTION_AUTHORITY = "NONE"
REQUIRED_SOURCE_DATA_GRADE = "ARCHIVAL_EVENT_TIME_RECONSTRUCTED"

ALLOWLISTED_SYMBOLS: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
ALLOWLISTED_MARKET = "BINANCE_USDT_M_PERPETUAL"
ALLOWLISTED_MANIFEST_MARKETS: frozenset[str] = frozenset(
    {"BINANCE_USDT_M_PERPETUAL", "USD-M PERPETUAL"}
)

RC2_PROTECTED_SYMBOLS: frozenset[str] = frozenset(
    {
        "ZECUSDT",
        "HYPEUSDT",
        "ORCAUSDT",
        "PUMPUSDT",
        "NMRUSDT",
        "BRUSDT",
        "RLCUSDT",
        "QNTUSDT",
        "ZEC",
        "HYPE",
        "ORCA",
        "PUMP",
        "NMR",
        "BR",
        "RLC",
        "QNT",
    }
)

CANDIDATE_REGISTRY_IDS: tuple[str, ...] = (
    "STRUCTURAL_CONTINUATION_LONG_04H",
    "STRUCTURAL_CONTINUATION_LONG_12H",
    "STRUCTURAL_CONTINUATION_SHORT_04H",
    "STRUCTURAL_CONTINUATION_SHORT_12H",
    "CLOSED_RETEST_LONG_04H",
    "CLOSED_RETEST_LONG_12H",
    "CLOSED_RETEST_SHORT_04H",
    "CLOSED_RETEST_SHORT_12H",
)

CONTROL_POLICY_IDS: tuple[str, ...] = (
    "PAUSE",
    "MATCHED_LONG",
    "MATCHED_SHORT",
    "BALANCED_MATCHED_DIRECTION",
    "UNCONDITIONAL_LONG_04H",
    "UNCONDITIONAL_LONG_12H",
    "UNCONDITIONAL_SHORT_04H",
    "UNCONDITIONAL_SHORT_12H",
)

# Time constants in integer milliseconds
ONE_MINUTE_MS = 60_000
ONE_HOUR_MS = 3_600_000
FOUR_HOURS_MS = 14_400_000
TWELVE_HOURS_MS = 43_200_000
ARCHIVAL_AVAILABILITY_LAG_MS = 60_000
EARLIEST_ENTRY_LAG_FROM_BAR_END_MS = 120_000
VIRTUAL_ACK_DELAY_MS = 60_000
MAX_MARK_EVENT_AGE_MS = 120_000
FUNDING_OWNERSHIP_HALF_WINDOW_MS = 15_000
COOLDOWN_DURATION_MS = 14_400_000  # 4 hours

# Portfolio and risk constants
INITIAL_EQUITY_USDT = Decimal("1000.000000000000")
PER_ASSET_ALLOCATION_CEILING_USDT = Decimal("333.333333333333")
ADMISSIBLE_EQUITY_FRACTION = Decimal("0.95")
EQUITY_BUFFER_FRACTION = Decimal("0.05")
SCENARIO_RESERVE_MULTIPLIER = Decimal("1.10")
DRAWDOWN_KILL_THRESHOLD_USDT = Decimal("100.000000000000")
MIN_RISK_BPS = Decimal(30)
MAX_RISK_BPS = Decimal(250)
MAX_ENTRY_GAP_ATR_FRACTION = Decimal("0.25")
TARGET_RISK_MULTIPLE = Decimal(2)
BPS_DENOMINATOR = Decimal(10000)
LEDGER_QUANTUM = Decimal("0.000000000001")

# Old v0.3 BTC final holdout window [2026-02-01T00:00:00Z, 2026-08-01T00:00:00Z)
V03_BTC_FINAL_HOLDOUT_START_MS = 1_769_904_000_000  # 2026-02-01T00:00:00Z
V03_BTC_FINAL_HOLDOUT_END_MS = 1_785_542_400_000  # 2026-08-01T00:00:00Z

# Proposed R3 windows from CANDIDATE_REGISTER_PROPOSAL.json
R3_PROPOSED_WARMUP_WINDOW_MS: tuple[int, int] = (
    1_767_225_600_000,  # 2026-01-01T00:00:00Z
    1_769_904_000_000,  # 2026-02-01T00:00:00Z
)
R3_PROPOSED_DEV_WINDOWS_MS: tuple[tuple[int, int], ...] = (
    (1_769_904_000_000, 1_772_323_200_000),  # [2026-02-01, 2026-03-01)
    (1_772_323_200_000, 1_775_001_600_000),  # [2026-03-01, 2026-04-01)
    (1_775_001_600_000, 1_777_593_600_000),  # [2026-04-01, 2026-05-01)
)


class MessageTypePriority(IntEnum):
    """Total ordering priority for simultaneous available_at and event_at."""

    FILL_ACK = 0
    FUNDING_ACK = 1
    TRADE_BAR = 2
    MARK_BAR = 3


class FillAckSubPriority(IntEnum):
    """Within FILL_ACK, exit/reduction acknowledgments precede entry acknowledgments."""

    EXIT_OR_REDUCTION = 0
    ENTRY = 1


class BookSymbolState(IntEnum):
    """Per-symbol state machine states in a virtual book."""

    FLAT = 0
    ENTRY_PENDING = 1
    OPEN = 2
    EXIT_PENDING = 3
    COOLDOWN = 4
    DISABLED = 5


@dataclass(frozen=True)
class CostScenario:
    """Frozen cost scenario parameters per R3 design and R1.1 addendum."""

    name: str
    taker_fee_bps_per_leg: Decimal
    half_spread_bps_per_leg: Decimal
    slippage_bps_per_leg: Decimal
    funding_proxy_bps_per_event: Decimal
    allow_positive_funding_credit: bool = False

    @property
    def execution_friction_bps_per_leg(self) -> Decimal:
        """Embedded quote execution friction per leg (half-spread + slippage)."""
        with decimal_context():
            return self.half_spread_bps_per_leg + self.slippage_bps_per_leg

    @property
    def total_one_way_bps(self) -> Decimal:
        """Total one-way cost in bps (taker fee + half-spread + slippage)."""
        with decimal_context():
            return (
                self.taker_fee_bps_per_leg
                + self.half_spread_bps_per_leg
                + self.slippage_bps_per_leg
            )

    @property
    def round_trip_one_time_bps(self) -> Decimal:
        """Round-trip one-time cost in bps before funding (22bp base, 44bp stress)."""
        with decimal_context():
            return Decimal(2) * self.total_one_way_bps


BASE_COST_SCENARIO = CostScenario(
    name="BASE",
    taker_fee_bps_per_leg=Decimal(6),
    half_spread_bps_per_leg=Decimal(2),
    slippage_bps_per_leg=Decimal(3),
    funding_proxy_bps_per_event=Decimal(4),
    allow_positive_funding_credit=False,
)

STRESS_COST_SCENARIO = CostScenario(
    name="STRESS",
    taker_fee_bps_per_leg=Decimal(12),
    half_spread_bps_per_leg=Decimal(4),
    slippage_bps_per_leg=Decimal(6),
    funding_proxy_bps_per_event=Decimal(8),
    allow_positive_funding_credit=False,
)


@contextmanager
def decimal_context() -> Iterator[Context]:
    """Hermetic Decimal context (prec=50, ROUND_HALF_EVEN) isolated from process defaults."""
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)) as ctx:
        yield ctx


def to_dec(value: Decimal | int | str) -> Decimal:
    """Convert exact numeric representation to Decimal without float binary drift."""
    if isinstance(value, float):
        raise TypeError("Float inputs are forbidden in R3 oracle; use Decimal, int, or str")
    with decimal_context():
        return Decimal(value)


def round_ledger_usdt(value: Decimal) -> Decimal:
    """Round ledger USDT posting or metric to 12 decimal places using ROUND_HALF_EVEN."""
    with decimal_context():
        return value.quantize(LEDGER_QUANTUM, rounding=ROUND_HALF_EVEN)


def floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    """Round value down (toward -infinity / zero for positive values) to exact multiple of step."""
    with decimal_context():
        if step <= Decimal(0):
            raise ValueError(f"Step must be strictly positive, got {step}")
        quotient = (value / step).to_integral_value(rounding=ROUND_FLOOR)
        return (quotient * step).quantize(step, rounding=ROUND_HALF_EVEN)


def ceil_to_tick(value: Decimal, tick: Decimal) -> Decimal:
    """Round price upward to exact multiple of tick."""
    with decimal_context():
        if tick <= Decimal(0):
            raise ValueError(f"Tick must be strictly positive, got {tick}")
        quotient = (value / tick).to_integral_value(rounding=ROUND_CEILING)
        return (quotient * tick).quantize(tick, rounding=ROUND_HALF_EVEN)


def floor_to_tick(value: Decimal, tick: Decimal) -> Decimal:
    """Round price downward to exact multiple of tick."""
    return floor_to_step(value, tick)


def round_execution_price(
    raw_price: Decimal,
    *,
    is_buy: bool,
    cost_scenario: CostScenario,
    tick_size: Decimal,
) -> Decimal:
    """Compute effective execution price embedding spread + slippage + adverse tick rounding once.

    Buy executions shift up by (half_spread + slippage) and ceil to tick.
    Sell executions shift down by (half_spread + slippage) and floor to tick.
    """
    with decimal_context():
        if raw_price <= Decimal(0):
            raise ValueError(f"Raw execution price must be positive, got {raw_price}")
        friction_rate = cost_scenario.execution_friction_bps_per_leg / BPS_DENOMINATOR
        if is_buy:
            shifted = raw_price * (Decimal(1) + friction_rate)
            return ceil_to_tick(shifted, tick_size)
        shifted = raw_price * (Decimal(1) - friction_rate)
        return floor_to_tick(shifted, tick_size)


def round_stop_toward_entry(raw_stop: Decimal, *, direction: int, tick_size: Decimal) -> Decimal:
    """Round stop price toward entry (LONG upward, SHORT downward) per R1.1 specification."""
    if direction == 1:
        return ceil_to_tick(raw_stop, tick_size)
    if direction == -1:
        return floor_to_tick(raw_stop, tick_size)
    raise ValueError(f"Direction must be +1 or -1, got {direction}")


def round_target_toward_entry(
    raw_target: Decimal, *, direction: int, tick_size: Decimal
) -> Decimal:
    """Round target price toward entry (LONG downward, SHORT upward) per R1.1 specification."""
    if direction == 1:
        return floor_to_tick(raw_target, tick_size)
    if direction == -1:
        return ceil_to_tick(raw_target, tick_size)
    raise ValueError(f"Direction must be +1 or -1, got {direction}")
