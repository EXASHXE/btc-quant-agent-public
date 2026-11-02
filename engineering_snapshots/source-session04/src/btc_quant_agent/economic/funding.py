from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class FundingSettlement:
    """An exchange funding settlement event at a point-in-time."""

    timestamp_ms: int
    funding_rate: float
    mark_price: float


@dataclass(frozen=True)
class FundingModel:
    """Perpetual funding rate cashflow modeling and settlement proration."""

    settlement_interval_hours: int = 8

    def calculate_cashflow(
        self,
        position_quantity: float,
        mark_price: float,
        funding_rate: float,
    ) -> float:
        """Calculate the cashflow received (+) or paid (-) upon funding settlement.

        Standard Crypto Perpetual Convention:
        - Longs pay shorts when funding_rate > 0: cashflow < 0
        - Shorts receive when funding_rate > 0: cashflow > 0
        - Longs receive when funding_rate < 0: cashflow > 0
        - Shorts pay when funding_rate < 0: cashflow < 0
        Formula: cashflow = -1 * position_quantity * mark_price * funding_rate
        """
        if abs(position_quantity) < 1e-12:
            return 0.0
        return -1.0 * position_quantity * mark_price * funding_rate

    def accumulate_funding_during_window(
        self,
        position_quantity: float,
        entry_ms: int,
        exit_ms: int,
        funding_events: Sequence[FundingSettlement],
    ) -> tuple[float, list[FundingSettlement]]:
        """Accumulate all settled funding cashflows strictly falling within [entry_ms, exit_ms]."""
        if abs(position_quantity) < 1e-12 or entry_ms >= exit_ms:
            return 0.0, []

        total_cashflow = 0.0
        settled_events: list[FundingSettlement] = []

        for event in funding_events:
            # Settlement occurs if event timestamp is between entry and exit
            if entry_ms <= event.timestamp_ms <= exit_ms:
                cf = self.calculate_cashflow(
                    position_quantity=position_quantity,
                    mark_price=event.mark_price,
                    funding_rate=event.funding_rate,
                )
                total_cashflow += cf
                settled_events.append(event)

        return total_cashflow, settled_events
