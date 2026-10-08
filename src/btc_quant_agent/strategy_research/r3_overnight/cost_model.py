"""Cost models, execution frictions, tick/lot rounding, and funding calculations."""

from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, Decimal

from btc_quant_agent.strategy_research.r3_overnight.constants import (
    BASE_FUNDING_RATE_PER_EVENT,
    BASE_HALF_SPREAD_BPS,
    BASE_SLIPPAGE_BPS,
    BASE_TAKER_FEE_BPS,
    BASE_TOTAL_LEG_FRICTION_BPS,
    STRESS_FUNDING_RATE_PER_EVENT,
    STRESS_HALF_SPREAD_BPS,
    STRESS_SLIPPAGE_BPS,
    STRESS_TAKER_FEE_BPS,
    STRESS_TOTAL_LEG_FRICTION_BPS,
)
from btc_quant_agent.strategy_research.r3_overnight.types import (
    CostScenario,
    Direction,
    SymbolFilters,
)


def round_to_tick(value: Decimal, tick_size: Decimal, mode: str = "nearest") -> Decimal:
    """Round value to exchange tick size multiple."""
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
        Always debits adverse rate * notional regardless of direction.
        """
        notional = abs(quantity) * settlement_mark
        return notional * self.funding_rate
