"""Pre-outcome H41 testability receipts and frozen support floors."""

from __future__ import annotations

from dataclasses import InitVar, dataclass, fields
from enum import StrEnum
from weakref import WeakKeyDictionary

from .authority import CANDIDATES_BY_ID, EXPECTED_HASHES, EXPECTED_SOURCE_ROOT, canonical_sha256
from .provenance import SYNTHETIC_SOURCE_ROOT, H41ProvenanceEventBatch
from .science import EventBatch, occupied_days

_RECEIPT_ISSUER = object()


class H41State(StrEnum):
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    BASIC_SUPPORT_UNAVAILABLE = "BASIC_SUPPORT_UNAVAILABLE"
    INFERENCE_ADEQUACY_UNAVAILABLE = "INFERENCE_ADEQUACY_UNAVAILABLE"
    TESTABLE_EXPLORATORY = "TESTABLE_EXPLORATORY"
    INFERENCE_UNAVAILABLE = "INFERENCE_UNAVAILABLE"
    EDGE_FAIL = "EDGE_FAIL"
    EDGE_PASS = "EDGE_PASS"


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
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
    authority_kind: str
    source_context_id: str
    train_fit_seal_id: str | None
    event_population_hash: str
    _issuer: InitVar[object | None] = None
    _issuer_batch: InitVar[H41ProvenanceEventBatch | None] = None

    def __post_init__(self, _issuer: object | None,
                      _issuer_batch: H41ProvenanceEventBatch | None) -> None:
        if self.schema_id != "H41_TESTABILITY_RECEIPT_V1":
            raise ValueError("invalid H41 receipt schema")
        if (self.candidate_id not in CANDIDATES_BY_ID
                or self.partition not in ("WF1_TRAIN", "WF1_CALIBRATION")
                or self.frozen_semantic_root != EXPECTED_HASHES["frozen_h41_semantic_root_hash"]
                or self.candidate_ledger_hash != EXPECTED_HASHES["candidate_ledger_hash"]):
            raise ValueError("H41 testability authority mismatch")
        if self.authority_kind == "ACCEPTED_CANONICAL_SOURCE":
            if (self.source_authority_root != EXPECTED_SOURCE_ROOT
                    or not self.source_context_id or _issuer is not _RECEIPT_ISSUER
                    or _issuer_batch is None):
                raise ValueError("accepted H41 receipt authority mismatch")
            H41ProvenanceEventBatch.assert_intact(_issuer_batch)
            if (_issuer_batch.authority_kind != self.authority_kind
                    or _issuer_batch.candidate_id != self.candidate_id
                    or _issuer_batch.partition != self.partition
                    or _issuer_batch.source_context_id != self.source_context_id
                    or _issuer_batch.train_fit_seal_id != self.train_fit_seal_id
                    or _issuer_batch.event_population_hash != self.event_population_hash
                    or len(_issuer_batch.events) != self.event_count_N
                    or occupied_days(_issuer_batch.batch) != self.occupied_calendar_days_D):
                raise ValueError("accepted H41 receipt event lineage mismatch")
            expected_state = (H41State.TESTABLE_EXPLORATORY
                              if self.event_count_N >= 60 and self.occupied_calendar_days_D >= 30
                              else H41State.BASIC_SUPPORT_UNAVAILABLE)
            if self.state != expected_state:
                raise ValueError("accepted H41 receipt support state mismatch")
        elif self.authority_kind == "SYNTHETIC_NON_AUTHORITATIVE":
            if self.source_authority_root != SYNTHETIC_SOURCE_ROOT:
                raise ValueError("synthetic H41 receipt authority mismatch")
        else:
            raise ValueError("unknown H41 receipt authority kind")
        if not self.event_population_hash:
            raise ValueError("missing H41 event population hash")
        if self.event_count_N < 0 or self.occupied_calendar_days_D < 0:
            raise ValueError("negative testability support")
        if self.state in (H41State.EDGE_PASS, H41State.EDGE_FAIL):
            raise ValueError("pre-outcome testability cannot assert edge state")
        if self.state == H41State.TESTABLE_EXPLORATORY and (
            self.event_count_N < 60 or self.occupied_calendar_days_D < 30
        ):
            raise ValueError("testability support state mismatch")

    def assert_intact(self) -> None:
        if type(self) is not H41TestabilityReceipt:
            raise TypeError("exact H41 testability receipt required")
        recorded = _RECEIPT_REGISTRY.get(self)
        if recorded is None or _receipt_fields(self) != recorded[0]:
            raise ValueError("H41 receipt lineage and runtime integrity mismatch")
        if recorded[1] is not None:
            H41ProvenanceEventBatch.assert_intact(recorded[1])


def _receipt_fields(receipt: H41TestabilityReceipt) -> tuple[object, ...]:
    return tuple(getattr(receipt, item.name) for item in fields(H41TestabilityReceipt))


_RECEIPT_REGISTRY: WeakKeyDictionary[
    H41TestabilityReceipt, tuple[tuple[object, ...], H41ProvenanceEventBatch | None]
] = WeakKeyDictionary()


def make_testability_receipt(
    batch: EventBatch | H41ProvenanceEventBatch,
) -> H41TestabilityReceipt:
    if type(batch) is H41ProvenanceEventBatch:
        H41ProvenanceEventBatch.assert_intact(batch)
        raw = batch.batch
        kind = batch.authority_kind
        root = batch._context.source_authority_root
        context_id = batch.source_context_id
        fit_id = batch.train_fit_seal_id
        population_hash = batch.event_population_hash
    elif type(batch) is EventBatch:
        raw = batch
        kind = "SYNTHETIC_NON_AUTHORITATIVE"
        root = SYNTHETIC_SOURCE_ROOT
        context_id = "SYNTHETIC_UNBOUND"
        fit_id = None
        population_hash = canonical_sha256({
            "candidate_id": raw.candidate_id, "partition": raw.partition,
            "events": [(e.decision_time_ms, e.side, e.horizon_hours) for e in raw.events],
        })
    else:
        raise TypeError("H41 event batch required")
    n, d = len(raw.events), occupied_days(raw)
    state = (H41State.TESTABLE_EXPLORATORY if n >= 60 and d >= 30
             else H41State.BASIC_SUPPORT_UNAVAILABLE)
    receipt = H41TestabilityReceipt(
        "H41_TESTABILITY_RECEIPT_V1", raw.candidate_id, raw.partition,
        EXPECTED_HASHES["frozen_h41_semantic_root_hash"],
        EXPECTED_HASHES["candidate_ledger_hash"], root,
        n, d, state, kind, context_id, fit_id, population_hash,
        _issuer=_RECEIPT_ISSUER if kind == "ACCEPTED_CANONICAL_SOURCE" else None,
        _issuer_batch=batch if type(batch) is H41ProvenanceEventBatch
        and kind == "ACCEPTED_CANONICAL_SOURCE" else None,
    )
    _RECEIPT_REGISTRY[receipt] = (
        _receipt_fields(receipt),
        batch if type(batch) is H41ProvenanceEventBatch else None,
    )
    H41TestabilityReceipt.assert_intact(receipt)
    return receipt
