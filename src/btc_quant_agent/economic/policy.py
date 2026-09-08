from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from .signal import InformationSignal


def _finite(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


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

    def __post_init__(self) -> None:
        _finite(self.min_signal_strength, "min_signal_strength")
        if self.min_signal_strength < 0:
            raise ValueError("min_signal_strength must be nonnegative")
        _finite(self.limit_offset_bps, "limit_offset_bps")
        if type(self.time_in_force_ms) is not int or self.time_in_force_ms <= 0:
            raise ValueError("time_in_force_ms must be a positive integer")
        if not self.allowed_directions:
            raise ValueError("allowed_directions cannot be empty")
        for d in self.allowed_directions:
            if d not in (1, -1):
                raise ValueError(f"invalid allowed direction: {d}")

    def calculate_limit_price(self, reference_price: float, side: int) -> float:
        """Calculate limit price applying limit_offset_bps (+ = passive, - = aggressive).

        For BUY (side=+1): passive offset reduces buy price: ref * (1 - offset).
        For SELL (side=-1): passive offset increases sell price: ref * (1 + offset).
        """
        _finite(reference_price, "reference_price")
        if reference_price <= 0:
            raise ValueError("reference_price must be positive")
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

    def __post_init__(self) -> None:
        if self.stop_loss_pct is not None:
            _finite(self.stop_loss_pct, "stop_loss_pct")
            if self.stop_loss_pct <= 0 or self.stop_loss_pct > 1.0:
                raise ValueError("stop_loss_pct must be in (0, 1]")
        if self.take_profit_pct is not None:
            _finite(self.take_profit_pct, "take_profit_pct")
            if self.take_profit_pct <= 0:
                raise ValueError("take_profit_pct must be positive")
        if self.trailing_stop_pct is not None:
            _finite(self.trailing_stop_pct, "trailing_stop_pct")
            if self.trailing_stop_pct <= 0 or self.trailing_stop_pct > 1.0:
                raise ValueError("trailing_stop_pct must be in (0, 1]")
        if type(self.max_holding_ms) is not int or self.max_holding_ms <= 0:
            raise ValueError("max_holding_ms must be a positive integer")
        if self.ambiguous_exit_handling not in ("CONSERVATIVE_STOP_FIRST", "REJECT_AMBIGUOUS"):
            raise ValueError(f"unsupported ambiguous_exit_handling: {self.ambiguous_exit_handling}")


@dataclass(frozen=True)
class PositionSizing:
    sizing_type: SizingType = SizingType.FIXED_NOTIONAL
    target_notional: float = 10_000.0  # USDT notional for FIXED_NOTIONAL
    risk_fraction: float = 0.02  # fraction of equity at risk
    max_leverage: float = 1.0

    def __post_init__(self) -> None:
        _finite(self.target_notional, "target_notional")
        if self.target_notional <= 0:
            raise ValueError("target_notional must be positive")
        _finite(self.risk_fraction, "risk_fraction")
        if self.risk_fraction <= 0 or self.risk_fraction > 1.0:
            raise ValueError("risk_fraction must be in (0, 1]")
        _finite(self.max_leverage, "max_leverage")
        if self.max_leverage <= 0:
            raise ValueError("max_leverage must be positive")


@dataclass(frozen=True)
class RiskBudget:
    max_gross_exposure_usdt: float = 50_000.0
    max_open_positions: int = 1
    max_drawdown_stop_pct: float = 0.20  # halt new trading if drawdown exceeds 20%

    def __post_init__(self) -> None:
        _finite(self.max_gross_exposure_usdt, "max_gross_exposure_usdt")
        if self.max_gross_exposure_usdt <= 0:
            raise ValueError("max_gross_exposure_usdt must be positive")
        if type(self.max_open_positions) is not int or self.max_open_positions < 0:
            raise ValueError("max_open_positions must be a nonnegative integer")
        _finite(self.max_drawdown_stop_pct, "max_drawdown_stop_pct")
        if self.max_drawdown_stop_pct <= 0 or self.max_drawdown_stop_pct > 1.0:
            raise ValueError("max_drawdown_stop_pct must be in (0, 1]")


@dataclass(frozen=True)
class MarketStateFilter:
    min_volume_usdt_15m: float = 0.0
    max_spread_bps: float = 15.0
    allowed_regimes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _finite(self.min_volume_usdt_15m, "min_volume_usdt_15m")
        if self.min_volume_usdt_15m < 0:
            raise ValueError("min_volume_usdt_15m cannot be negative")
        _finite(self.max_spread_bps, "max_spread_bps")
        if self.max_spread_bps < 0:
            raise ValueError("max_spread_bps cannot be negative")


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
        if (
            self.position_sizing.sizing_type == SizingType.RISK_FRACTION
            and (self.exit_rule.stop_loss_pct is None or self.exit_rule.stop_loss_pct <= 0)
        ):
            raise ValueError("RISK_FRACTION sizing requires explicit positive stop_loss_pct in exit_rule")

    def should_enter(
        self,
        signal: InformationSignal,
        current_spread_bps: float = 0.0,
        current_volume_usdt: float = 0.0,
        current_regime: str | None = None,
    ) -> bool:
        if not signal.is_actionable:
            return False
        if signal.direction not in self.entry_rule.allowed_directions:
            return False
        if abs(signal.strength) < self.entry_rule.min_signal_strength:
            return False
        if not math.isfinite(current_spread_bps) or current_spread_bps < 0:
            return False
        if not math.isfinite(current_volume_usdt) or current_volume_usdt < 0:
            return False
        if self.market_filter.max_spread_bps > 0 and current_spread_bps > self.market_filter.max_spread_bps:
            return False
        if self.market_filter.min_volume_usdt_15m > 0 and current_volume_usdt < self.market_filter.min_volume_usdt_15m:
            return False
        return not (
            self.market_filter.allowed_regimes
            and (current_regime is None or current_regime not in self.market_filter.allowed_regimes)
        )

    def calculate_quantity(
        self,
        current_price: float,
        portfolio_equity: float,
        current_atr: float | None = None,
    ) -> float:
        _finite(current_price, "current_price")
        if current_price <= 0:
            return 0.0
        _finite(portfolio_equity, "portfolio_equity")
        if portfolio_equity <= 0:
            return 0.0

        st = self.position_sizing.sizing_type
        if st == SizingType.FIXED_NOTIONAL:
            notional = min(self.position_sizing.target_notional, portfolio_equity * self.position_sizing.max_leverage)
            return notional / current_price
        elif st == SizingType.RISK_FRACTION:
            sl_pct = self.exit_rule.stop_loss_pct
            if sl_pct is None or not math.isfinite(sl_pct) or sl_pct <= 0:
                raise ValueError("RISK_FRACTION sizing requires explicit positive stop_loss_pct")
            risk_dollars = portfolio_equity * self.position_sizing.risk_fraction
            notional = risk_dollars / sl_pct
            capped_notional = min(notional, portfolio_equity * self.position_sizing.max_leverage)
            return capped_notional / current_price
        elif st == SizingType.VOLATILITY_SCALED:
            if current_atr is None or not math.isfinite(current_atr) or current_atr <= 0:
                raise ValueError("VOLATILITY_SCALED sizing requires a finite positive current_atr")
            atr_pct = current_atr / current_price
            risk_dollars = portfolio_equity * self.position_sizing.risk_fraction
            notional = risk_dollars / max(0.005, atr_pct)
            capped_notional = min(notional, portfolio_equity * self.position_sizing.max_leverage)
            return capped_notional / current_price
        raise ValueError(f"unsupported sizing_type: {st}")

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
