from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from .signal import InformationSignal


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class SizingType(StrEnum):
    FIXED_NOTIONAL = "FIXED_NOTIONAL"
    VOLATILITY_SCALED = "VOLATILITY_SCALED"
    RISK_FRACTION = "RISK_FRACTION"


@dataclass(frozen=True)
class EntryRule:
    min_signal_strength: float = 0.0
    order_type: OrderType = OrderType.MARKET
    limit_offset_bps: float = 0.0  # offset from mid price for limit orders (+ = passive, - = aggressive)
    time_in_force_ms: int = 60_000  # maximum time limit order remains active
    allowed_directions: tuple[int, ...] = (1, -1)

    def calculate_limit_price(self, reference_price: float, side: int) -> float:
        """Calculate limit price applying limit_offset_bps (+ = passive, - = aggressive).

        For BUY (side=+1): passive offset reduces buy price: ref * (1 - offset).
        For SELL (side=-1): passive offset increases sell price: ref * (1 + offset).
        """
        offset_fraction = self.limit_offset_bps / 10_000.0
        if side == 1:
            return reference_price * (1.0 - offset_fraction)
        elif side == -1:
            return reference_price * (1.0 + offset_fraction)
        raise ValueError(f"side must be 1 or -1; got {side}")


@dataclass(frozen=True)
class ExitRule:
    stop_loss_pct: float | None = None  # e.g. 0.02 for 2% adverse move
    take_profit_pct: float | None = None  # e.g. 0.04 for 4% favorable move
    trailing_stop_pct: float | None = None  # e.g. 0.015 trailing from peak
    decay_exit_on_signal_reversal: bool = True
    max_holding_ms: int = 3_600_000  # e.g. 60m default
    ambiguous_exit_handling: str = "CONSERVATIVE_STOP_FIRST"  # "CONSERVATIVE_STOP_FIRST" or "REJECT_AMBIGUOUS"


@dataclass(frozen=True)
class PositionSizing:
    sizing_type: SizingType = SizingType.FIXED_NOTIONAL
    target_notional: float = 10_000.0  # USDT notional for FIXED_NOTIONAL
    risk_fraction: float = 0.02  # fraction of equity at risk
    max_leverage: float = 1.0


@dataclass(frozen=True)
class RiskBudget:
    max_gross_exposure_usdt: float = 50_000.0
    max_open_positions: int = 1
    max_drawdown_stop_pct: float = 0.20  # halt new trading if drawdown exceeds 20%


@dataclass(frozen=True)
class MarketStateFilter:
    min_volume_usdt_15m: float = 0.0
    max_spread_bps: float = 15.0
    allowed_regimes: tuple[str, ...] = ()


@dataclass(frozen=True)
class TradePolicy:
    """Explicit trading policy translating pure InformationSignals into economic execution."""

    policy_id: str
    name: str
    entry_rule: EntryRule = field(default_factory=EntryRule)
    exit_rule: ExitRule = field(default_factory=ExitRule)
    position_sizing: PositionSizing = field(default_factory=PositionSizing)
    risk_budget: RiskBudget = field(default_factory=RiskBudget)
    market_filter: MarketStateFilter = field(default_factory=MarketStateFilter)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.policy_id:
            raise ValueError("policy_id cannot be empty")
        if not self.name:
            raise ValueError("name cannot be empty")

    def should_enter(self, signal: InformationSignal, current_spread_bps: float = 0.0) -> bool:
        if not signal.is_actionable:
            return False
        if signal.direction not in self.entry_rule.allowed_directions:
            return False
        if abs(signal.strength) < self.entry_rule.min_signal_strength:
            return False
        return not (self.market_filter.max_spread_bps > 0 and current_spread_bps > self.market_filter.max_spread_bps)

    def calculate_quantity(
        self,
        current_price: float,
        portfolio_equity: float,
        current_atr: float | None = None,
    ) -> float:
        if current_price <= 0:
            return 0.0
        st = self.position_sizing.sizing_type
        if st == SizingType.FIXED_NOTIONAL:
            notional = min(self.position_sizing.target_notional, portfolio_equity * self.position_sizing.max_leverage)
            return notional / current_price
        elif st == SizingType.RISK_FRACTION:
            # risk fraction of equity / stop loss distance
            sl_pct = self.exit_rule.stop_loss_pct or 0.02
            risk_dollars = portfolio_equity * self.position_sizing.risk_fraction
            notional = risk_dollars / sl_pct
            capped_notional = min(notional, portfolio_equity * self.position_sizing.max_leverage)
            return capped_notional / current_price
        elif st == SizingType.VOLATILITY_SCALED:
            # Scale inversely with ATR if provided
            if current_atr and current_atr > 0:
                atr_pct = current_atr / current_price
                risk_dollars = portfolio_equity * self.position_sizing.risk_fraction
                notional = risk_dollars / max(0.005, atr_pct)
                capped_notional = min(notional, portfolio_equity * self.position_sizing.max_leverage)
                return capped_notional / current_price
            return (portfolio_equity * self.position_sizing.max_leverage) / current_price
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "name": self.name,
            "entry_rule": asdict(self.entry_rule),
            "exit_rule": asdict(self.exit_rule),
            "position_sizing": asdict(self.position_sizing),
            "risk_budget": asdict(self.risk_budget),
            "market_filter": asdict(self.market_filter),
            "metadata": self.metadata,
        }
