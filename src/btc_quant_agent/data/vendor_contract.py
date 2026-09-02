from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .historical_provenance import HistoricalDataRole


@dataclass(frozen=True)
class VendorDatasetContract:
    provider: str
    dataset: str
    venue_instrument: str
    coverage_dates: str
    granularity: str
    exchange_timestamp_available: bool
    receive_timestamp_available: bool
    l2_sequence_reconstructable: bool
    oi_semantics: str | None
    liquidation_semantics: str | None
    access_requirement: str
    sample_available: str
    license_constraints: str
    formal_role: HistoricalDataRole

    def __post_init__(self) -> None:
        if self.formal_role != HistoricalDataRole.VENDOR_RECORDED_HISTORICAL_PIT_PROXY:
            raise ValueError("vendor imports must remain vendor historical PIT proxies")
        if not self.exchange_timestamp_available:
            raise ValueError("vendor import requires an exchange timestamp")
        if not self.receive_timestamp_available:
            raise ValueError("vendor PIT proxy requires a vendor receive timestamp")

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["formal_role"] = self.formal_role.value
        return payload

    def validate_row(self, row: dict[str, Any]) -> None:
        required = {"exchange_timestamp", "receive_timestamp", "provider", "dataset"}
        missing = sorted(required - row.keys())
        if missing:
            raise ValueError(f"vendor row missing fields: {', '.join(missing)}")
        if row["provider"] != self.provider or row["dataset"] != self.dataset:
            raise ValueError("vendor row does not match frozen contract")
        if row.get("formal_role") == HistoricalDataRole.TRUE_FORWARD_LOCAL_PIT.value:
            raise ValueError("vendor row cannot be labeled TRUE_FORWARD_LOCAL_PIT")

