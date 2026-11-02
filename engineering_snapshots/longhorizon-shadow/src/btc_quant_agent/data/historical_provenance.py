from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class HistoricalDataRole(StrEnum):
    CANONICAL_HISTORICAL = "CANONICAL_HISTORICAL"
    OFFICIAL_HISTORICAL_TIMESTAMPED = "OFFICIAL_HISTORICAL_TIMESTAMPED"
    VENDOR_RECORDED_HISTORICAL_PIT_PROXY = "VENDOR_RECORDED_HISTORICAL_PIT_PROXY"
    DEVELOPMENT_PROXY = "DEVELOPMENT_PROXY"
    FORWARD_PIT_ONLY = "FORWARD_PIT_ONLY"
    TRUE_FORWARD_LOCAL_PIT = "TRUE_FORWARD_LOCAL_PIT"
    UNAVAILABLE_OR_UNTRUSTWORTHY = "UNAVAILABLE_OR_UNTRUSTWORTHY"


@dataclass(frozen=True)
class HistoricalDatasetProvenance:
    provider: str
    source_name: str
    symbol: str
    coverage_start: str | None
    coverage_end: str | None
    resolution_or_event_type: str
    exchange_event_timestamp_field: str | None
    source_timestamp_unit: str | None
    local_or_vendor_receive_timestamp_field: str | None
    retrieval_timestamp: str
    checksum_or_manifest: str | None
    lookback_limit_if_rest: str | None
    point_in_time_interpretation: str
    known_biases: tuple[str, ...]
    formal_role: HistoricalDataRole

    def __post_init__(self) -> None:
        if (
            self.formal_role == HistoricalDataRole.TRUE_FORWARD_LOCAL_PIT
            and self.provider != "BTC_QUANT_AGENT_LOCAL_COLLECTOR"
        ):
            raise ValueError("only the local contemporaneous collector can be TRUE_FORWARD_LOCAL_PIT")
        if (
            self.formal_role == HistoricalDataRole.VENDOR_RECORDED_HISTORICAL_PIT_PROXY
            and not self.local_or_vendor_receive_timestamp_field
        ):
            raise ValueError("vendor PIT proxy requires a receive-timestamp field")

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["formal_role"] = self.formal_role.value
        payload["known_biases"] = list(self.known_biases)
        return payload

