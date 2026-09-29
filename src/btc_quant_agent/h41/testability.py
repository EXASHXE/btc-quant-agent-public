"""Pre-outcome H41 testability receipts and frozen support floors."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .authority import CANDIDATES_BY_ID, EXPECTED_HASHES, EXPECTED_SOURCE_ROOT
from .science import EventBatch, occupied_days


class H41State(StrEnum):
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    BASIC_SUPPORT_UNAVAILABLE = "BASIC_SUPPORT_UNAVAILABLE"
    INFERENCE_ADEQUACY_UNAVAILABLE = "INFERENCE_ADEQUACY_UNAVAILABLE"
    TESTABLE_EXPLORATORY = "TESTABLE_EXPLORATORY"
    INFERENCE_UNAVAILABLE = "INFERENCE_UNAVAILABLE"
    EDGE_FAIL = "EDGE_FAIL"
    EDGE_PASS = "EDGE_PASS"


@dataclass(frozen=True, slots=True)
class H41TestabilityReceipt:
    schema_id: str
    candidate_id: str
    partition: str
    frozen_semantic_root: str
    candidate_ledger_hash: str
    source_authority_root: str
    event_count_N: int
    occupied_calendar_days_D: int
    state: H41State

    def __post_init__(self) -> None:
        if self.schema_id != "H41_TESTABILITY_RECEIPT_V1":
            raise ValueError("invalid H41 receipt schema")
        if (self.candidate_id not in CANDIDATES_BY_ID
                or self.partition not in ("WF1_TRAIN", "WF1_CALIBRATION")
                or self.frozen_semantic_root != EXPECTED_HASHES["frozen_h41_semantic_root_hash"]
                or self.candidate_ledger_hash != EXPECTED_HASHES["candidate_ledger_hash"]
                or self.source_authority_root != EXPECTED_SOURCE_ROOT):
            raise ValueError("H41 testability authority mismatch")
        if self.event_count_N < 0 or self.occupied_calendar_days_D < 0:
            raise ValueError("negative testability support")
        if self.state in (H41State.EDGE_PASS, H41State.EDGE_FAIL):
            raise ValueError("pre-outcome testability cannot assert edge state")
        if self.state == H41State.TESTABLE_EXPLORATORY and (
            self.event_count_N < 60 or self.occupied_calendar_days_D < 30
        ):
            raise ValueError("testability support state mismatch")


def make_testability_receipt(batch: EventBatch) -> H41TestabilityReceipt:
    n, d = len(batch.events), occupied_days(batch)
    state = (H41State.TESTABLE_EXPLORATORY if n >= 60 and d >= 30
             else H41State.BASIC_SUPPORT_UNAVAILABLE)
    return H41TestabilityReceipt(
        "H41_TESTABILITY_RECEIPT_V1", batch.candidate_id, batch.partition,
        EXPECTED_HASHES["frozen_h41_semantic_root_hash"],
        EXPECTED_HASHES["candidate_ledger_hash"], EXPECTED_SOURCE_ROOT,
        n, d, state,
    )
