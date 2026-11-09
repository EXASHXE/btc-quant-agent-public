"""Separate MVP schemas; never aliases for qualified native research evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Any, Final, cast

from pydantic import Field, model_validator

from ..core import fingerprint
from ..native.contract import Strict, digest, strict, require
from ..rc_models import RCPlan, STRATEGY_VERSION
from ..swing import Contract, ClosedBar, SwingPolicy

POLICY = strict((Path(__file__).parent / "contract.json").read_bytes())
CONTRACT_HASH = digest(POLICY)
PRODUCT = POLICY["product"]
SYNTHETIC: Final = "H_DETERMINISTIC_SYNTHETIC"
IMPORTED: Final = "H_AUTHORIZED_IMPORT_UNQUALIFIED"


class Sample(Strict):
    wall_ms: int = Field(gt=0)
    mono_before_ms: int = Field(gt=0)
    mono_after_ms: int = Field(gt=0)
    boot_id: str

    @model_validator(mode="after")
    def bracket(self):
        require(0 <= self.mono_after_ms - self.mono_before_ms <= 5, "MVP_CLOCK_SAMPLE_UNCERTAIN")
        return self


class Reference(Strict):
    lower_ms: int = Field(gt=0)
    upper_ms: int = Field(gt=0)
    received_mono_ms: int = Field(gt=0)
    boot_id: str
    provenance: str

    @model_validator(mode="after")
    def bounds(self):
        require(
            0 <= self.upper_ms - self.lower_ms <= POLICY["source_reference_width_ms_max"],
            "MVP_SOURCE_TIME_UNCERTAINTY",
        )
        return self

    def project(self, sample):
        require(sample.boot_id == self.boot_id, "MVP_REFERENCE_BOOT_MISMATCH")
        age = sample.mono_before_ms - self.received_mono_ms
        require(0 <= age <= POLICY["source_reference_age_ms_max"], "MVP_SOURCE_REFERENCE_STALE_OR_FUTURE")
        return self.lower_ms + age, self.upper_ms + sample.mono_after_ms - self.received_mono_ms


class CaptureClocks(Strict):
    receive_wall_ms: int = Field(gt=0)
    available_wall_ms: int = Field(gt=0)
    durable_wall_ms: int = Field(gt=0)
    receive_mono_ms: int = Field(gt=0)
    available_mono_ms: int = Field(gt=0)
    durable_mono_ms: int = Field(gt=0)
    boot_id: str

    @model_validator(mode="after")
    def order(self):
        require(
            self.receive_mono_ms <= self.available_mono_ms <= self.durable_mono_ms,
            "MVP_CAPTURE_MONOTONIC_ORDER",
        )
        return self

    def jumped(self):
        offsets = [
            self.receive_wall_ms - self.receive_mono_ms,
            self.available_wall_ms - self.available_mono_ms,
            self.durable_wall_ms - self.durable_mono_ms,
        ]
        return max(offsets) - min(offsets) > 50


class Row(Strict):
    kind: Literal["COMPLETED_DATASET", "COMBINED_KLINE"]
    symbol: Literal["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    interval: Literal["1H", "4H", "1D"]
    candle: dict
    raw_kline: dict | None = None
    original_source_event_ms: int | None = None
    clocks: CaptureClocks
    revision: int = Field(default=0, ge=0)


class Dataset(Strict):
    schema_version: Literal["H_COMPLETED_DATASET_V1"] = "H_COMPLETED_DATASET_V1"
    mode: Literal["EXPLORATORY_MVP"] = "EXPLORATORY_MVP"
    evidence_class: Literal["H_DETERMINISTIC_SYNTHETIC", "H_AUTHORIZED_IMPORT_UNQUALIFIED"]
    source_id: str
    capture_origin: str
    fixture_id: str | None = None
    reference: Reference
    transport_provenance: str
    rows: list[Row]


class ImportPermit(Strict):
    schema_version: Literal["H_IMPORT_PERMISSION_V1"] = "H_IMPORT_PERMISSION_V1"
    mode: Literal["EXPLORATORY_MVP"] = "EXPLORATORY_MVP"
    dataset_sha256: str
    rights_sha256: str
    source_id: str
    contract_sha256: str
    prospective_or_historical_permission: str
    caching_retention_reference: str
    region_venue_reference: str
    source_transport_reference: str
    chronology_reference: str


class PermitEnvelope(Strict):
    grant: ImportPermit
    key_id: str
    signature_algorithm: Literal["Ed25519"] = "Ed25519"
    signature_base64: str


class MVPBar(Contract):
    candle: Any
    source_id: str
    source_event_ms: int
    received_ms: int
    available_ms: int
    durable_ms: int
    revision: int = Field(default=0, ge=0)

    @property
    def end_ms(self):
        return self.candle.close_time_ms + 1

    exposure: Literal["EXPLORATORY_MVP_ONLY"] = "EXPLORATORY_MVP_ONLY"

    def reason(self, cutoff_ms, policy):
        reason = ClosedBar.reason(cast(Any, self), cutoff_ms, policy)
        # Imported completed history was observed at the declared source snapshot,
        # not fabricated as available at its historical close. Mandatory latest
        # closes, continuity, reference freshness and actual local import commit
        # are checked separately before the unchanged S1 compiler is called.
        return None if reason == "AVAILABILITY_SLA_MISSED" else reason


class Decision(Contract):
    schema_version: Literal["H_MVP_DECISION_V1"] = "H_MVP_DECISION_V1"
    mode: Literal["EXPLORATORY_MVP"] = "EXPLORATORY_MVP"
    product_version: Literal["H_EXPLORATORY_S1_V1"] = "H_EXPLORATORY_S1_V1"
    contract_sha256: str = CONTRACT_HASH
    exposure: Literal["H_DETERMINISTIC_SYNTHETIC", "H_AUTHORIZED_IMPORT_UNQUALIFIED"]
    strategy: Literal["trend_pullback"] = "trend_pullback"
    strategy_version: Literal["PROGRAM_A_S1_CAUSAL_V1"] = "PROGRAM_A_S1_CAUSAL_V1"
    symbol: Literal["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    market_state: Literal["WATCH", "ARMED", "NO_SETUP", "DATA_UNAVAILABLE", "SOURCE_BLOCKED"]
    source_qualified: Literal[False] = False
    shadow_advisory_qualified: Literal[False] = False
    economically_validated: Literal[False] = False
    account: Literal["ACCOUNT_UNKNOWN/ACCOUNT_VETO"] = "ACCOUNT_UNKNOWN/ACCOUNT_VETO"
    actionability: Literal["HYPOTHETICAL_MARKET_SIDE_ONLY_ACCOUNT_VETO"] = (
        "HYPOTHETICAL_MARKET_SIDE_ONLY_ACCOUNT_VETO"
    )
    trigger_close_ms: int
    decision_ms: int
    scheduled_review_ms: int
    review_source_bounds_ms: tuple[int, int]
    review_local: Sample
    clock_condition: str
    data_status: str
    import_watermark: int
    admitted_prefix: tuple[dict, ...]
    prefix_sha256: str
    receipt_ids: tuple[str, ...]
    reasons: tuple[str, ...]
    diagnostics: dict[str, Any]
    opportunity: RCPlan | None = None
    episode_id: str | None = None
    eligible_planned_r: tuple[int, ...] = ()

    @model_validator(mode="after")
    def integrity(self):
        require(self.contract_sha256 == CONTRACT_HASH, "MVP_MODE_CONTRACT_CHANGED")
        require(
            self.decision_ms == self.review_source_bounds_ms[0] <= self.review_source_bounds_ms[1],
            "MVP_SOURCE_REVIEW_BOUNDS",
        )
        require(
            self.scheduled_review_ms == SwingPolicy().next_review(self.decision_ms), "MVP_SCHEDULED_REVIEW"
        )
        require(
            fingerprint(list(self.admitted_prefix)) == self.prefix_sha256, "MVP_FROZEN_SOURCE_PREFIX_TAMPER"
        )
        positive = self.market_state in ("WATCH", "ARMED")
        require(positive == (self.opportunity is not None) == (self.episode_id is not None), "MVP_PLAN_STATE")
        if positive:
            p = self.opportunity
            assert p is not None
            require(4 <= p.holding_hours <= 48 and p.account_status == "UNKNOWN", "MVP_HORIZON_OR_ACCOUNT")
            require(
                p.symbol == self.symbol
                and p.planned_after_cost_r >= 2
                and self.eligible_planned_r == tuple(r for r in (2, 3, 4) if r <= p.planned_after_cost_r),
                "MVP_STRUCTURAL_R_GEOMETRY",
            )
            require(self.clock_condition != "CLOCK_DEGRADED_HOLD", "MVP_HELD_CLOCK_CANNOT_GENERATE_PLAN")
            require(
                self.episode_id
                == fingerprint(
                    [PRODUCT, STRATEGY_VERSION, self.symbol, self.trigger_close_ms, self.prefix_sha256]
                ),
                "MVP_EPISODE_ID",
            )
            require(
                p.available_ms <= self.decision_ms < self.scheduled_review_ms < p.expires_ms
                and p.setup_close_ms == self.trigger_close_ms,
                "MVP_CAUSAL_PLAN_CLOCK",
            )
        return self
