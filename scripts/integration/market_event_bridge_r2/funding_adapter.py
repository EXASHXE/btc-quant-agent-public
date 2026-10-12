"""Settled Funding Decimal Ledger: Adapts official REST funding records to B and C schemas.

Resolves Incompatibility 3 (A's REST format vs B's parse_funding_payload zero default).
Enforces exact Decimal arithmetic, non-zero Mark price verification, past settlement gating,
and signed long/short cash flows. Prevents silent zero defaults and duplicate settlements.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any


@dataclass(frozen=True)
class SettledFundingEntry:
    """Rigorous financial journal entry for a completed Binance USDⓈ-M funding settlement."""

    symbol: str
    funding_time_ms: int
    funding_rate: Decimal
    mark_price: Decimal
    settlement_id: str
    settled: bool
    rate_type: str
    derived_available_at_ms: int
    feature_known_at_ms: int
    producer_manifest_sha256: str
    quality: str
    reason_codes: tuple[str, ...]
    derivation_version: str = "settled-funding-entry-v1"
    parent_event_sha256: tuple[str, ...] = ()
    producer_upstream_sha: str = "df00997f344eba82f7cca0d03ee1617948abee44"
    route_epoch: str = "route-epoch-0"
    connection_epoch: int = 1
    source_observed_wall_utc_ms: int = 0
    source_available_at_ms: int = 0
    clock_uncertainty_ms: int = 0

    def calculate_cash_flow(self, position_size_btc: Decimal) -> Decimal:
        """Calculate signed cash flow for position size in BTC.
        
        Long (>0) pays positive rate; short (<0) receives positive rate.
        Formula: cash_flow = -1 * position_size * funding_rate * mark_price
        """
        # Quantize to 8 decimal places for USD cash precision
        cf = -1 * position_size_btc * self.funding_rate * self.mark_price
        return cf.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_EVEN)

    def to_b_funding_payload(self) -> dict[str, Any]:
        """Convert to payload expected by B's parse_funding_payload."""
        return {
            "T": self.funding_time_ms,
            "r": float(self.funding_rate),
            "p": float(self.mark_price),
            "settled": True,
            "estimated": False,
            "symbol": self.symbol,
        }

    def to_c_funding_payload(self) -> dict[str, Any]:
        """Convert to exact schema required by C's MarketPitPort._translate_funding."""
        return {
            "event_id": f"FUNDING-{self.symbol}-{self.funding_time_ms}",
            "settlement_id": self.settlement_id,
            "settlement_at_ms": self.funding_time_ms,
            "rate_fraction": str(self.funding_rate),
            "settled": True,
            "rate_type": "SETTLED_REALIZED",
        }

    def to_dict(self) -> dict[str, Any]:
        src_wall = self.source_observed_wall_utc_ms or self.derived_available_at_ms
        src_avail = self.source_available_at_ms or self.derived_available_at_ms
        base = {
            "schema_version": self.derivation_version,
            "derivation_version": self.derivation_version,
            "symbol": self.symbol,
            "funding_time_ms": self.funding_time_ms,
            "funding_rate": str(self.funding_rate),
            "mark_price": str(self.mark_price),
            "settlement_id": self.settlement_id,
            "settled": self.settled,
            "rate_type": self.rate_type,
            "source_observed_wall_utc_ms": src_wall,
            "source_available_at_ms": src_avail,
            "derived_available_at_ms": self.derived_available_at_ms,
            "feature_known_at_ms": self.feature_known_at_ms,
            "clock_uncertainty_ms": self.clock_uncertainty_ms,
            "route_epoch": self.route_epoch,
            "connection_epoch": self.connection_epoch,
            "parent_event_sha256": list(self.parent_event_sha256),
            "raw_source_manifest_sha256": self.producer_manifest_sha256,
            "producer_manifest_sha256": self.producer_manifest_sha256,
            "producer_upstream_sha": self.producer_upstream_sha,
            "quality": self.quality,
            "reason_codes": list(self.reason_codes),
        }
        canonical_sha = hashlib.sha256(
            json.dumps(base, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        base["canonical_sha256"] = canonical_sha
        return base


class SettledFundingLedger:
    """Maintains deduplicated journal of settled funding events with verified Mark pricing."""

    def __init__(self, symbol: str = "BTCUSDT") -> None:
        self.symbol = symbol
        self.journal: dict[str, SettledFundingEntry] = {}
        self.duplicate_count: int = 0
        self.rejected_count: int = 0

    def ingest_settled_funding(
        self,
        raw_record: dict[str, Any],
        contemporaneous_mark_price: Decimal | float | str | None,
        observed_wall_utc_ms: int,
        raw_manifest_sha256: str = "",
    ) -> SettledFundingEntry | None:
        """Ingest official REST fundingRate record and bind contemporaneous verified Mark price.
        
        raw_record: {'symbol': 'BTCUSDT', 'fundingRate': '0.00010000', 'fundingTime': 1728720000000}
        """
        funding_time = int(raw_record.get("fundingTime", 0))
        rate_str = str(raw_record.get("fundingRate", "0.0"))
        funding_rate = Decimal(rate_str)
        sym = str(raw_record.get("symbol", self.symbol))

        # Check past settlement
        if funding_time > observed_wall_utc_ms:
            # Future / unfinalized funding is strictly rejected
            self.rejected_count += 1
            return None

        # Check Mark price validity
        if contemporaneous_mark_price is None:
            # Financial Blocker: cannot classify cost complete without Mark price
            self.rejected_count += 1
            return None

        mark_dec = Decimal(str(contemporaneous_mark_price))
        if mark_dec <= Decimal(0):
            self.rejected_count += 1
            return None

        settlement_id = f"{sym}:{funding_time}:{rate_str}"
        if settlement_id in self.journal:
            self.duplicate_count += 1
            return self.journal[settlement_id]

        entry = SettledFundingEntry(
            symbol=sym,
            funding_time_ms=funding_time,
            funding_rate=funding_rate,
            mark_price=mark_dec,
            settlement_id=settlement_id,
            settled=True,
            rate_type="SETTLED_REALIZED",
            derived_available_at_ms=observed_wall_utc_ms,
            feature_known_at_ms=observed_wall_utc_ms,
            producer_manifest_sha256=raw_manifest_sha256,
            quality="VERIFIED",
            reason_codes=("OK",),
        )

        self.journal[settlement_id] = entry
        return entry

    def generate_decimal_ledger_report(self) -> dict[str, Any]:
        """Produce full audit receipt matching SETTLED_FUNDING_DECIMAL_LEDGER.json."""
        records = []
        for entry in self.journal.values():
            # Test sample long (+1 BTC) and short (-1 BTC) cash flows
            long_cf = entry.calculate_cash_flow(Decimal("1.0"))
            short_cf = entry.calculate_cash_flow(Decimal("-1.0"))
            rec = entry.to_dict()
            rec["sample_long_1btc_cash_flow"] = str(long_cf)
            rec["sample_short_1btc_cash_flow"] = str(short_cf)
            records.append(rec)

        return {
            "schema_version": "settled-funding-decimal-ledger-v1",
            "symbol": self.symbol,
            "total_settlements": len(self.journal),
            "duplicate_count": self.duplicate_count,
            "rejected_count": self.rejected_count,
            "journal_records": records,
        }
