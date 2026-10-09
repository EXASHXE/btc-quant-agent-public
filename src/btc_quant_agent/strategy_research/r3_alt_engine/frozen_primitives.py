"""Pure frozen primitives, constants, candidate definitions, and indicators for r3_alt_engine.

Version provenance:
- Original 8 formula IDs: e5b2006a89441f7eb2ec900e508aff451106b87a
- Method R1.1 accepted PIT/cost: cf2d5cc33774cdcff7d709636305bba830e977ef
- Controller AM01/AM02 prospective method freeze: 821d23427a5f6d0b4635f32f226ddc779358ab72
- Sol architecture and matrix: c0b41d1ce62e0fe852edfc6e162f1bc3dc6dcc01
- Code baseline: e0ff8c3473de4bfa3e66fe7928d42992a4d38a32
"""

from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, Context, Decimal

from btc_quant_agent.strategy_research.r3_alt_engine.model import (
    Bar1h,
    Bar1m,
    Bar4h,
    CandidateDefinition,
    CandidateFamily,
    CostScenario,
    Direction,
    Horizon,
    SymbolFilters,
)

# Local Decimal context (50 decimal places precision, HALF_EVEN rounding)
DECIMAL_CTX = Context(prec=50, rounding=ROUND_HALF_EVEN)
POSTING_QUANT_12DP = Decimal("0.000000000001")


def quantize12dp(value: Decimal) -> Decimal:
    """Quantize decimal value to 12 decimal places using HALF_EVEN."""
    return DECIMAL_CTX.quantize(value, POSTING_QUANT_12DP)


# Frozen constants
INITIAL_EQUITY_USDT = Decimal("1000.000000000000")
ALLOCATION_CEILING_PER_ASSET_USDT = Decimal("333.333333333333")
EQUITY_RESERVE_FRACTION = Decimal("0.05")  # 5% reserve
DRAWDOWN_KILL_THRESHOLD_USDT = Decimal("100.000000000000")  # 100 USDT peak-to-trough
RESERVE_BUFFER_MULTIPLIER = Decimal("1.10")  # 10% adverse pricing buffer

# Risk distance constraints (bps as decimals)
MIN_RISK_BPS = Decimal("0.0030")  # 30 bps
MAX_RISK_BPS = Decimal("0.0250")  # 250 bps
MAX_GAP_ATR_FRACTION = Decimal("0.25")  # 0.25 ATR20 gap limit
TARGET_R_MULTIPLE = Decimal("2.0")  # 2R target

# Cost model parameters: Base scenario (22 bps round trip)
BASE_TAKER_FEE_BPS = Decimal(6)
BASE_HALF_SPREAD_BPS = Decimal(2)
BASE_SLIPPAGE_BPS = Decimal(3)
BASE_TOTAL_LEG_FRICTION_BPS = Decimal(5)  # half_spread + slippage embedded
BASE_TOTAL_LEG_FEE_BPS = Decimal(6)  # fee debited separately
BASE_ROUND_TRIP_BPS = Decimal(22)

# Cost model parameters: Stress scenario (44 bps round trip)
STRESS_TAKER_FEE_BPS = Decimal(12)
STRESS_HALF_SPREAD_BPS = Decimal(4)
STRESS_SLIPPAGE_BPS = Decimal(6)
STRESS_TOTAL_LEG_FRICTION_BPS = Decimal(10)  # half_spread + slippage embedded
STRESS_TOTAL_LEG_FEE_BPS = Decimal(12)  # fee debited separately
STRESS_ROUND_TRIP_BPS = Decimal(44)

# Funding proxy parameters
BASE_FUNDING_RATE_PER_EVENT = Decimal("0.0004")  # 4 bps adverse
STRESS_FUNDING_RATE_PER_EVENT = Decimal("0.0008")  # 8 bps adverse
FUNDING_OWNERSHIP_HALF_WINDOW_MS = 15_000  # +/- 15 seconds around whole hour

# Timing and clocks
MINUTE_MS = 60_000
HOUR_MS = 3_600_000
FOUR_HOUR_MS = 14_400_000
DECISION_AVAILABILITY_LAG_MS = 60_000  # Bar close + 60s
FILL_DELAY_FROM_DECISION_MS = 60_000  # Order due at open O + 60s
FILL_ACK_DELAY_MS = 60_000  # Fill acknowledgment available at fill + 60s
MARK_STALENESS_LIMIT_MS = 120_000  # 120s mark freshness limit
COOLDOWN_DURATION_MS = 14_400_000  # 4 hours

# Diagnostic and ineligibility labels
STRESS_COST_GEOMETRY_INELIGIBLE = "STRESS_COST_GEOMETRY_INELIGIBLE"
SOURCE_OR_PERMISSION_BLOCKED = "SOURCE_OR_PERMISSION_BLOCKED"
NO_EMPIRICAL_RESULTS = "NO_EMPIRICAL_RESULTS"
REAL_FUNDS_WRITE_AUTHORITY = "NONE"

# Candidate registry constants
EXPECTED_CANDIDATE_COUNT = 8
SUPPORTED_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")

CANDIDATE_IDS = (
    "STRUCTURAL_CONTINUATION_LONG_04H",
    "STRUCTURAL_CONTINUATION_LONG_12H",
    "STRUCTURAL_CONTINUATION_SHORT_04H",
    "STRUCTURAL_CONTINUATION_SHORT_12H",
    "CLOSED_RETEST_LONG_04H",
    "CLOSED_RETEST_LONG_12H",
    "CLOSED_RETEST_SHORT_04H",
    "CLOSED_RETEST_SHORT_12H",
)

_RAW_CANDIDATES = [
    CandidateDefinition(
        id="STRUCTURAL_CONTINUATION_LONG_04H",
        family=CandidateFamily.STRUCTURAL_CONTINUATION,
        direction=Direction.LONG,
        horizon=Horizon.H4,
        symbols=SUPPORTED_SYMBOLS,
    ),
    CandidateDefinition(
        id="STRUCTURAL_CONTINUATION_LONG_12H",
        family=CandidateFamily.STRUCTURAL_CONTINUATION,
        direction=Direction.LONG,
        horizon=Horizon.H12,
        symbols=SUPPORTED_SYMBOLS,
    ),
    CandidateDefinition(
        id="STRUCTURAL_CONTINUATION_SHORT_04H",
        family=CandidateFamily.STRUCTURAL_CONTINUATION,
        direction=Direction.SHORT,
        horizon=Horizon.H4,
        symbols=SUPPORTED_SYMBOLS,
    ),
    CandidateDefinition(
        id="STRUCTURAL_CONTINUATION_SHORT_12H",
        family=CandidateFamily.STRUCTURAL_CONTINUATION,
        direction=Direction.SHORT,
        horizon=Horizon.H12,
        symbols=SUPPORTED_SYMBOLS,
    ),
    CandidateDefinition(
        id="CLOSED_RETEST_LONG_04H",
        family=CandidateFamily.CLOSED_RETEST,
        direction=Direction.LONG,
        horizon=Horizon.H4,
        symbols=SUPPORTED_SYMBOLS,
    ),
    CandidateDefinition(
        id="CLOSED_RETEST_LONG_12H",
        family=CandidateFamily.CLOSED_RETEST,
        direction=Direction.LONG,
        horizon=Horizon.H12,
        symbols=SUPPORTED_SYMBOLS,
    ),
    CandidateDefinition(
        id="CLOSED_RETEST_SHORT_04H",
        family=CandidateFamily.CLOSED_RETEST,
        direction=Direction.SHORT,
        horizon=Horizon.H4,
        symbols=SUPPORTED_SYMBOLS,
    ),
    CandidateDefinition(
        id="CLOSED_RETEST_SHORT_12H",
        family=CandidateFamily.CLOSED_RETEST,
        direction=Direction.SHORT,
        horizon=Horizon.H12,
        symbols=SUPPORTED_SYMBOLS,
    ),
]


class CandidateRegistry:
    """Registry maintaining the exact 8 frozen candidate specifications."""

    def __init__(self) -> None:
        self._candidates: dict[str, CandidateDefinition] = {
            c.id: c for c in _RAW_CANDIDATES
        }
        if len(self._candidates) != EXPECTED_CANDIDATE_COUNT:
            raise ValueError(
                f"Candidate registry must contain exactly {EXPECTED_CANDIDATE_COUNT} candidates, "
                f"found {len(self._candidates)}"
            )

    def get_candidate(self, candidate_id: str) -> CandidateDefinition:
        if candidate_id not in self._candidates:
            raise KeyError(f"Candidate ID '{candidate_id}' not registered in frozen 8-candidate set")
        return self._candidates[candidate_id]

    def list_candidates(self) -> list[CandidateDefinition]:
        return [self._candidates[cid] for cid in CANDIDATE_IDS]

    def check_geometry_eligibility(
        self,
        candidate_id: str,
        cost_scenario: CostScenario,
        funding_schedule_is_known_8h: bool = False,
    ) -> tuple[bool, str | None]:
        """
        Check cost geometry eligibility.
        Under stress scenario with default hourly funding:
        12h horizon across 12 hourly funding windows at 8bp stress = 96bp adverse funding.
        Round trip transaction stress = 44bp.
        Total adverse cost hurdle = 140bp.
        With target = 2R, minimum stop distance required for non-negative payoff space is >= 2 * 140bp = 280bp.
        However, maximum initial stop distance is 250bp (2.5%).
        Since 280bp > 250bp, 12h stress variants with hourly funding cannot satisfy the pre-registered geometry.
        This must be reported as STRESS_COST_GEOMETRY_INELIGIBLE.
        Note: If a pre-declared known 8h funding schedule is used (e.g. BASE 12h), hurdle is different.
        """
        candidate = self.get_candidate(candidate_id)
        if cost_scenario == CostScenario.STRESS and candidate.horizon == Horizon.H12:
            return False, STRESS_COST_GEOMETRY_INELIGIBLE
        return True, None


def get_default_registry() -> CandidateRegistry:
    return CandidateRegistry()


# Rounding and tick/lot utilities
def round_to_tick(value: Decimal, tick_size: Decimal, mode: str = "nearest") -> Decimal:
    """Round value to exchange tick size multiple with local context."""
    if tick_size <= Decimal(0):
        return value
    units = value / tick_size
    if mode == "ceil":
        rounded_units = units.to_integral_value(rounding=ROUND_CEILING)
    elif mode == "floor":
        rounded_units = units.to_integral_value(rounding=ROUND_FLOOR)
    else:
        rounded_units = units.to_integral_value(rounding=ROUND_HALF_EVEN)
    return rounded_units * tick_size


def floor_to_lot(quantity: Decimal, step_size: Decimal) -> Decimal:
    """Floor quantity to exchange step size (lot size) multiple."""
    if step_size <= Decimal(0):
        return quantity
    units = quantity / step_size
    floored_units = units.to_integral_value(rounding=ROUND_FLOOR)
    return floored_units * step_size


class CostModel:
    """Deterministic cost model implementing Base (22bp) and Stress (44bp) parameters."""

    def __init__(self, scenario: CostScenario = CostScenario.BASE) -> None:
        self.scenario = scenario
        if scenario == CostScenario.BASE:
            self.fee_bps = BASE_TAKER_FEE_BPS
            self.half_spread_bps = BASE_HALF_SPREAD_BPS
            self.slippage_bps = BASE_SLIPPAGE_BPS
            self.friction_bps = BASE_TOTAL_LEG_FRICTION_BPS
            self.funding_rate = BASE_FUNDING_RATE_PER_EVENT
        else:
            self.fee_bps = STRESS_TAKER_FEE_BPS
            self.half_spread_bps = STRESS_HALF_SPREAD_BPS
            self.slippage_bps = STRESS_SLIPPAGE_BPS
            self.friction_bps = STRESS_TOTAL_LEG_FRICTION_BPS
            self.funding_rate = STRESS_FUNDING_RATE_PER_EVENT

        self.friction_rate = self.friction_bps / Decimal(10000)
        self.fee_rate = self.fee_bps / Decimal(10000)

    def model_execution_price(
        self,
        raw_price: Decimal,
        is_buy: bool,
        filters: SymbolFilters,
    ) -> Decimal:
        """
        Model effective fill price embedding adverse half-spread and slippage.
        Buy orders embed friction upward: ceil_to_tick(raw * (1 + friction))
        Sell orders embed friction downward: floor_to_tick(raw * (1 - friction))
        """
        if is_buy:
            adverse_price = raw_price * (Decimal(1) + self.friction_rate)
            return round_to_tick(adverse_price, filters.tick_size, mode="ceil")
        else:
            adverse_price = raw_price * (Decimal(1) - self.friction_rate)
            return round_to_tick(adverse_price, filters.tick_size, mode="floor")

    def round_stop_level(
        self,
        raw_stop: Decimal,
        direction: Direction,
        filters: SymbolFilters,
    ) -> Decimal:
        """
        Round stop level adversely toward entry:
        LONG stop rounds upward toward entry: ceil_to_tick
        SHORT stop rounds downward toward entry: floor_to_tick
        """
        if direction == Direction.LONG:
            return round_to_tick(raw_stop, filters.tick_size, mode="ceil")
        else:
            return round_to_tick(raw_stop, filters.tick_size, mode="floor")

    def round_target_level(
        self,
        raw_target: Decimal,
        direction: Direction,
        filters: SymbolFilters,
    ) -> Decimal:
        """
        Round target level adversely toward entry:
        LONG target rounds downward toward entry: floor_to_tick
        SHORT target rounds upward toward entry: ceil_to_tick
        """
        if direction == Direction.LONG:
            return round_to_tick(raw_target, filters.tick_size, mode="floor")
        else:
            return round_to_tick(raw_target, filters.tick_size, mode="ceil")

    def compute_taker_fee(self, executed_notional: Decimal) -> Decimal:
        """Compute separate taker fee debited from cash."""
        return executed_notional * self.fee_rate

    def compute_funding_charge(
        self,
        quantity: Decimal,
        settlement_mark: Decimal,
    ) -> Decimal:
        """
        Compute adverse funding debit under diagnostic proxy assumptions.
        Always debits adverse rate * notional.
        """
        notional = abs(quantity) * settlement_mark
        return notional * self.funding_rate


# Aggregators and Indicators
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
            continue

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
        vol_val = sum((b.volume for b in hour_bars), Decimal(0))

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
        vol_val = sum((b.volume for b in period_bars), Decimal(0))

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
    """Compute True Range series for 1h bars."""
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
    """Compute arithmetic mean of 20 hourly True Ranges using prior closes."""
    if len(bars_1h) < 21:
        return None
    trs = compute_true_ranges_1h(bars_1h)
    last_20_trs = trs[-20:]
    return sum(last_20_trs) / Decimal(20)


def compute_atr20_4h(bars_4h: list[Bar4h]) -> Decimal | None:
    """Compute arithmetic mean of 20 4-hourly True Ranges using prior closes."""
    if len(bars_4h) < 21:
        return None
    trs = compute_true_ranges_4h(bars_4h)
    last_20_trs = trs[-20:]
    return sum(last_20_trs) / Decimal(20)


def compute_ema_series(closes: list[Decimal], period: int) -> list[Decimal | None]:
    """Compute EMA series initialized with SMA seed of length N."""
    if len(closes) < period:
        return [None] * len(closes)

    result: list[Decimal | None] = [None] * (period - 1)
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
    Compute 12-bar Efficiency Ratio on 4h bars.
    displacement = abs(close_t - close_{t-12})
    path = sum(abs(close_i - close_{i-1}) for i in t-11..t)
    ER12 = displacement / path. Zero path yields Decimal(0).
    """
    if len(bars_4h) < 13:
        return None

    closes = [b.close for b in bars_4h]
    displacement = abs(closes[-1] - closes[-13])
    path = sum(abs(closes[i] - closes[i - 1]) for i in range(len(closes) - 12, len(closes)))
    if path == Decimal(0):
        return Decimal(0)
    return displacement / path
