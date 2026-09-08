from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SlippageMode(StrEnum):
    ZERO = "ZERO"
    FIXED_BPS = "FIXED_BPS"
    SPREAD_AND_IMPACT = "SPREAD_AND_IMPACT"


@dataclass(frozen=True)
class FeeModel:
    """Configurable transaction cost model supporting maker/taker fees and multi-regime slippage."""

    maker_fee_rate: float = 0.0002  # 2 bps maker
    taker_fee_rate: float = 0.0005  # 5 bps taker
    slippage_mode: SlippageMode = SlippageMode.FIXED_BPS
    fixed_slippage_bps: float = 1.0  # 1 bp default slippage
    impact_coefficient: float = 0.01  # price impact scale factor per fraction of bar volume
    max_slippage_bps: float | None = None  # optional upper bound cap on worst-case slippage

    def worst_case_price_bound(
        self,
        reference_price: float,
        side: int,  # +1 = BUY, -1 = SELL
        current_spread_bps: float = 0.0,
    ) -> float | None:
        """Calculate deterministic ex-ante worst-case bound on execution price.

        For BUY (side=+1): returns maximum possible fill price (upper bound for gross calculation).
        For SELL (side=-1): returns maximum notional evaluation price (upper bound for gross calculation).
        Returns None if slippage model has no finite deterministic ex-ante bound.
        """
        if reference_price <= 0:
            raise ValueError(f"reference_price must be positive; got {reference_price}")
        if side not in (-1, 1):
            raise ValueError(f"side must be -1 or 1; got {side}")

        if self.slippage_mode == SlippageMode.ZERO:
            return reference_price
        elif self.slippage_mode == SlippageMode.FIXED_BPS:
            slippage_factor = self.fixed_slippage_bps / 10_000.0
            return reference_price * (1.0 + slippage_factor)
        elif self.slippage_mode == SlippageMode.SPREAD_AND_IMPACT:
            if self.max_slippage_bps is not None and self.max_slippage_bps >= 0:
                slippage_factor = self.max_slippage_bps / 10_000.0
                return reference_price * (1.0 + slippage_factor)
            return None
        return None

    def calculate_fee(self, notional: float, is_maker: bool = False) -> float:
        rate = self.maker_fee_rate if is_maker else self.taker_fee_rate
        return abs(notional) * rate

    def calculate_slippage_bps(
        self,
        quantity: float,
        price: float,
        current_spread_bps: float = 0.0,
        bar_volume_base: float = 0.0,
    ) -> float:
        if self.slippage_mode == SlippageMode.ZERO:
            return 0.0
        elif self.slippage_mode == SlippageMode.FIXED_BPS:
            return self.fixed_slippage_bps
        elif self.slippage_mode == SlippageMode.SPREAD_AND_IMPACT:
            half_spread = max(0.0, current_spread_bps / 2.0)
            impact = 0.0
            if bar_volume_base > 0 and quantity > 0:
                participation = quantity / bar_volume_base
                impact = self.impact_coefficient * participation * 10_000.0  # convert fraction to bps
            return half_spread + impact
        return self.fixed_slippage_bps

    def effective_fill_price(
        self,
        reference_price: float,
        quantity: float,
        side: int,  # +1 = BUY, -1 = SELL
        is_maker: bool = False,
        current_spread_bps: float = 0.0,
        bar_volume_base: float = 0.0,
    ) -> float:
        if reference_price <= 0:
            raise ValueError(f"reference_price must be positive; got {reference_price}")
        if side not in (-1, 1):
            raise ValueError(f"side must be -1 (SELL) or +1 (BUY); got {side}")

        if is_maker:
            # Maker orders do not suffer crossing-the-spread slippage
            return reference_price

        bps = self.calculate_slippage_bps(
            quantity=quantity,
            price=reference_price,
            current_spread_bps=current_spread_bps,
            bar_volume_base=bar_volume_base,
        )
        slippage_factor = bps / 10_000.0

        if side == 1:  # BUY suffers higher execution price
            return reference_price * (1.0 + slippage_factor)
        else:  # SELL suffers lower execution price
            return reference_price * (1.0 - slippage_factor)
