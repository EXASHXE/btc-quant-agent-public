from __future__ import annotations

import math
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
    max_slippage_bps: float | None = None  # hard cap and missing-spread adverse scenario

    def __post_init__(self) -> None:
        object.__setattr__(self, "slippage_mode", SlippageMode(self.slippage_mode))
        for name in (
            "maker_fee_rate",
            "taker_fee_rate",
            "fixed_slippage_bps",
            "impact_coefficient",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if self.max_slippage_bps is not None and (
            not math.isfinite(self.max_slippage_bps) or self.max_slippage_bps < 0
        ):
            raise ValueError("max_slippage_bps must be finite and nonnegative")
        if self.fixed_slippage_bps >= 10_000:
            raise ValueError("fixed_slippage_bps must be less than 10,000")
        if self.max_slippage_bps is not None and self.max_slippage_bps >= 10_000:
            raise ValueError("max_slippage_bps must be less than 10,000")

    def worst_case_price_bound(
        self,
        reference_price: float,
        side: int,  # +1 = BUY, -1 = SELL
        current_spread_bps: float | None = None,
    ) -> float | None:
        """Calculate deterministic ex-ante worst-case bound on execution price.

        For BUY (side=+1): returns maximum possible fill price (upper bound for gross calculation).
        For SELL (side=-1): returns maximum notional evaluation price (upper bound for gross calculation).
        Returns None if slippage model has no finite deterministic ex-ante bound.
        """
        if not math.isfinite(reference_price) or reference_price <= 0:
            raise ValueError(f"reference_price must be positive; got {reference_price}")
        if side not in (-1, 1):
            raise ValueError(f"side must be -1 or 1; got {side}")
        if current_spread_bps is not None and (
            not math.isfinite(current_spread_bps) or current_spread_bps < 0
        ):
            raise ValueError("current_spread_bps must be finite and nonnegative when provided")

        if self.slippage_mode == SlippageMode.ZERO:
            return reference_price
        if self.slippage_mode == SlippageMode.FIXED_BPS:
            slippage_factor = self.fixed_slippage_bps / 10_000.0
            return reference_price * (1.0 + slippage_factor)
        if self.slippage_mode == SlippageMode.SPREAD_AND_IMPACT:
            if self.max_slippage_bps is not None:
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
        current_spread_bps: float | None = None,
        bar_volume_base: float = 0.0,
    ) -> float:
        for name, value in (
            ("quantity", quantity),
            ("price", price),
            ("bar_volume_base", bar_volume_base),
        ):
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if quantity < 0:
            raise ValueError("quantity must be nonnegative")
        if price <= 0:
            raise ValueError("price must be positive")
        if bar_volume_base < 0:
            raise ValueError("bar_volume_base must be nonnegative")

        if self.slippage_mode == SlippageMode.ZERO:
            return 0.0
        if self.slippage_mode == SlippageMode.FIXED_BPS:
            return self.fixed_slippage_bps
        if self.slippage_mode == SlippageMode.SPREAD_AND_IMPACT:
            if current_spread_bps is None:
                if self.max_slippage_bps is None:
                    raise ValueError(
                        "SPREAD_AND_IMPACT requires causal current_spread_bps or "
                        "a declared max_slippage_bps adverse scenario"
                    )
                return self.max_slippage_bps
            if not math.isfinite(current_spread_bps) or current_spread_bps < 0:
                raise ValueError("current_spread_bps must be finite and nonnegative")

            half_spread = current_spread_bps / 2.0
            impact = 0.0
            if bar_volume_base > 0 and quantity > 0:
                participation = quantity / bar_volume_base
                impact = self.impact_coefficient * participation * 10_000.0  # convert fraction to bps
            raw_slippage_bps = half_spread + impact
            if self.max_slippage_bps is not None:
                return min(raw_slippage_bps, self.max_slippage_bps)
            return raw_slippage_bps
        return self.fixed_slippage_bps

    def effective_fill_price(
        self,
        reference_price: float,
        quantity: float,
        side: int,  # +1 = BUY, -1 = SELL
        is_maker: bool = False,
        current_spread_bps: float | None = None,
        bar_volume_base: float = 0.0,
    ) -> float:
        if not math.isfinite(reference_price) or reference_price <= 0:
            raise ValueError(f"reference_price must be positive; got {reference_price}")
        if side not in (-1, 1):
            raise ValueError(f"side must be -1 (SELL) or +1 (BUY); got {side}")
        if not math.isfinite(quantity) or quantity <= 0:
            raise ValueError("quantity must be finite and positive")

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
            result = reference_price * (1.0 + slippage_factor)
        else:  # SELL suffers lower execution price
            result = reference_price * (1.0 - slippage_factor)
        if not math.isfinite(result) or result <= 0:
            raise ValueError("configured slippage produces a nonpositive fill price")
        return result
