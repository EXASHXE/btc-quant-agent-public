"""Synthetic-only *claimed* causal-clock checks; not real source admission.

This pure module authenticates NO sender, clock, policy, stream sequence or fsync.
It never opens a file or a network connection. Caller-provided policy and evidence
are untrusted claims until a separate independent attestation pipeline exists.
Only CLAIMED_TIMING_ELIGIBLE is possible; VERIFIED_ELIGIBLE is not implemented.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

NS = 1_000_000_000
MAX_CALIBRATION_AGE_NS = 60 * NS
MAX_RECEIVER_ERROR_NS = 10_000_000
DECISION_GUARD_NS = 1_000_000

Role = Literal["POINT", "COMPLETED_INTERVAL", "FUTURE_SCHEDULE_METADATA"]
Family = Literal["BBO", "OI", "MARK", "FUNDING", "DERIVED"]
FAMILY_RECEIVER_AGE_NS = {"BBO": 2 * NS, "OI": 10 * NS, "MARK": 5 * NS, "FUNDING": 5 * NS}


class EvidenceBlocked(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _integer(value: object, code: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise EvidenceBlocked(code)
    return value


def _identity(value: object, code: str) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise EvidenceBlocked(code)
    return value


@dataclass(frozen=True)
class SourceRequirement:
    """Exogenously named source and native family, not inferred from an observed row."""

    source_id: str
    family: Family


@dataclass(frozen=True)
class PredeclaredSourceSet:
    """Immutable *claimed* fixed-origin R(F); real provenance is external.

    A caller can forge a new contract object. It is not a source signature,
    registry approval or evidence that the set was frozen before outcome access.
    """

    contract_id: str
    origin_utc_ns: int
    required: tuple[SourceRequirement, ...]

    def identities(self, fixed_origin_utc_ns: int) -> dict[str, Family]:
        _identity(self.contract_id, "REQUIRED_CONTRACT_ID_INVALID")
        if _integer(self.origin_utc_ns, "REQUIRED_ORIGIN_INVALID") != fixed_origin_utc_ns:
            raise EvidenceBlocked("REQUIRED_ORIGIN_MISMATCH")
        if type(self.required) is not tuple or not self.required:
            raise EvidenceBlocked("REQUIRED_SOURCE_SET_INVALID")
        result: dict[str, Family] = {}
        for requirement in self.required:
            if type(requirement) is not SourceRequirement:
                raise EvidenceBlocked("REQUIRED_SOURCE_ENTRY_INVALID")
            name = _identity(requirement.source_id, "REQUIRED_SOURCE_ID_INVALID")
            if type(requirement.family) is not str or requirement.family not in (
                "BBO",
                "OI",
                "MARK",
                "FUNDING",
                "DERIVED",
            ):
                raise EvidenceBlocked("REQUIRED_SOURCE_FAMILY_INVALID")
            if name in result:
                raise EvidenceBlocked("REQUIRED_SOURCE_DUPLICATE")
            result[name] = requirement.family
        return result


@dataclass(frozen=True)
class UtcBounds:
    lower_ns: int
    upper_ns: int


@dataclass(frozen=True)
class ClockCalibration:
    boot_id: str
    anchor_mono_ns: int
    anchor_utc_ns: int
    initial_error_ns: int
    drift_ppb: int
    instrumentation_error_ns: int = 0
    max_age_ns: int = MAX_CALIBRATION_AGE_NS

    def bounds(self, mono_ns: int) -> UtcBounds:
        _identity(self.boot_id, "CLOCK_BOOT_INVALID")
        _integer(self.anchor_mono_ns, "CLOCK_ANCHOR_INVALID")
        _integer(self.anchor_utc_ns, "CLOCK_ANCHOR_INVALID")
        _integer(self.initial_error_ns, "CLOCK_ERROR_UNKNOWN")
        _integer(self.instrumentation_error_ns, "CLOCK_ERROR_UNKNOWN")
        _integer(self.drift_ppb, "CLOCK_DRIFT_UNKNOWN")
        _integer(mono_ns, "CLOCK_INSTANT_INVALID")
        age_cap = _integer(self.max_age_ns, "CLOCK_AGE_INVALID", minimum=1)
        if age_cap > MAX_CALIBRATION_AGE_NS:
            raise EvidenceBlocked("CLOCK_AGE_UNQUALIFIED")
        elapsed = mono_ns - self.anchor_mono_ns
        if not 0 <= elapsed <= age_cap:
            raise EvidenceBlocked("CLOCK_CALIBRATION_EXPIRED")
        drift_error = (elapsed * self.drift_ppb + NS - 1) // NS
        error = self.initial_error_ns + self.instrumentation_error_ns + drift_error
        if error > MAX_RECEIVER_ERROR_NS:
            raise EvidenceBlocked("CLOCK_ERROR_EXCESS")
        center = self.anchor_utc_ns + elapsed
        return UtcBounds(center - error, center + error)


@dataclass(frozen=True)
class SourcePolicy:
    """Externally CLAIMED selection at a fixed origin, never trusted by construction."""

    source_id: str
    family: Family
    connection_id: str
    epoch_id: str
    epoch_start_mono_ns: int
    receiver_max_age_ns: int
    continuity: Literal["CONTIGUOUS", "GAPPED", "RECOVERY_REQUIRED"] = "CONTIGUOUS"
    epoch_end_mono_ns: int | None = None
    sample_max_age_ns: int | None = None

    def validate(self, expected_id: str, decision_mono_ns: int) -> None:
        if _identity(self.source_id, "POLICY_SOURCE_ID_INVALID") != expected_id:
            raise EvidenceBlocked("POLICY_SOURCE_MISMATCH")
        _identity(self.connection_id, "POLICY_CONNECTION_UNKNOWN")
        _identity(self.epoch_id, "POLICY_EPOCH_UNKNOWN")
        if type(self.family) is not str or self.family not in (
            "BBO",
            "OI",
            "MARK",
            "FUNDING",
            "DERIVED",
        ):
            raise EvidenceBlocked("POLICY_FAMILY_UNKNOWN")
        start = _integer(self.epoch_start_mono_ns, "POLICY_EPOCH_START_INVALID")
        if self.epoch_end_mono_ns is not None:
            end = _integer(self.epoch_end_mono_ns, "POLICY_EPOCH_END_INVALID")
            if end < start or decision_mono_ns > end:
                raise EvidenceBlocked("POLICY_EPOCH_ENDED")
        if type(self.continuity) is not str or self.continuity != "CONTIGUOUS":
            raise EvidenceBlocked("POLICY_EPOCH_NOT_CONTIGUOUS")
        age = _integer(self.receiver_max_age_ns, "POLICY_RECEIVER_CAP_MISSING", minimum=1)
        limit = FAMILY_RECEIVER_AGE_NS.get(self.family)
        if limit is not None and age > limit:
            raise EvidenceBlocked("POLICY_RECEIVER_CAP_TOO_WEAK")
        if self.family == "OI" and self.sample_max_age_ns is None:
            raise EvidenceBlocked("POLICY_SAMPLE_CAP_MISSING")
        if self.sample_max_age_ns is not None:
            sample_cap = _integer(self.sample_max_age_ns, "POLICY_SAMPLE_CAP_INVALID", minimum=1)
            if self.family == "OI" and sample_cap > FAMILY_RECEIVER_AGE_NS["OI"]:
                raise EvidenceBlocked("POLICY_SAMPLE_CAP_TOO_WEAK")


@dataclass(frozen=True)
class SourceEvidence:
    """Data produced outside this module, not independently authenticated."""

    source_id: str
    boot_id: str
    connection_id: str
    epoch_id: str
    first_byte_mono_ns: int | None
    complete_mono_ns: int | None
    validated_mono_ns: int | None
    raw_ack_mono_ns: int | None
    manifest_ack_mono_ns: int | None
    admission_mono_ns: int | None
    role: Role = "POINT"
    economic_end_upper_utc_ns: int | None = None
    scheduled_future_utc_ns: int | None = None
    sample_lower_utc_ns: int | None = None
    sample_upper_utc_ns: int | None = None

    def latest_claimed_utc_ns(
        self, clock: ClockCalibration, policy: SourcePolicy, decision_mono_ns: int
    ) -> int:
        sid = _identity(self.source_id, "SOURCE_ID_INVALID")
        if _identity(self.boot_id, "SOURCE_BOOT_INVALID") != clock.boot_id:
            raise EvidenceBlocked("SOURCE_BOOT_MISMATCH")
        if (
            _identity(self.connection_id, "SOURCE_CONNECTION_INVALID") != policy.connection_id
            or _identity(self.epoch_id, "SOURCE_EPOCH_INVALID") != policy.epoch_id
        ):
            raise EvidenceBlocked("SOURCE_EPOCH_MISMATCH")
        policy.validate(sid, decision_mono_ns)
        points = (
            self.first_byte_mono_ns,
            self.complete_mono_ns,
            self.validated_mono_ns,
            self.raw_ack_mono_ns,
            self.manifest_ack_mono_ns,
            self.admission_mono_ns,
        )
        if any(v is None for v in points):
            raise EvidenceBlocked("SOURCE_FULL_CLOCK_OR_ACK_MISSING")
        first, complete, valid, raw, manifest, admitted = (
            _integer(p, "SOURCE_BARRIER_INVALID") for p in points
        )
        if (
            not policy.epoch_start_mono_ns
            <= first
            <= complete
            <= valid
            <= raw
            <= manifest
            < admitted
        ):
            raise EvidenceBlocked("SOURCE_BARRIER_OR_EPOCH_ORDER")
        if policy.epoch_end_mono_ns is not None and admitted > policy.epoch_end_mono_ns:
            raise EvidenceBlocked("SOURCE_EPOCH_ENDED")
        if type(self.role) is not str or self.role not in (
            "POINT",
            "COMPLETED_INTERVAL",
            "FUTURE_SCHEDULE_METADATA",
        ):
            raise EvidenceBlocked("SOURCE_TIME_ROLE_UNKNOWN")
        # Validate every source instant, *including first byte*, against one clock epoch.
        bounds = [clock.bounds(t) for t in (first, complete, valid, raw, manifest, admitted)]
        availability = max(v.upper_ns for v in bounds)
        worst_receiver_age = clock.bounds(decision_mono_ns).upper_ns - bounds[1].lower_ns
        if worst_receiver_age > policy.receiver_max_age_ns:
            raise EvidenceBlocked("SOURCE_RECEIVER_STALE")

        if self.role == "COMPLETED_INTERVAL":
            if self.economic_end_upper_utc_ns is None:
                raise EvidenceBlocked("SOURCE_ECONOMIC_END_UNKNOWN")
            availability = max(
                availability,
                _integer(self.economic_end_upper_utc_ns, "SOURCE_ECONOMIC_END_INVALID"),
            )
        elif self.economic_end_upper_utc_ns is not None:
            raise EvidenceBlocked("SOURCE_POINT_INTERVAL_CONFLICT")
        if self.scheduled_future_utc_ns is not None:
            _integer(self.scheduled_future_utc_ns, "SOURCE_FUNDING_SCHEDULE_INVALID")

        need_sample = policy.sample_max_age_ns is not None
        if (
            need_sample
            or self.sample_lower_utc_ns is not None
            or self.sample_upper_utc_ns is not None
        ):
            if self.sample_lower_utc_ns is None or self.sample_upper_utc_ns is None:
                raise EvidenceBlocked("SOURCE_SAMPLE_CLOCK_UNKNOWN")
            lower = _integer(self.sample_lower_utc_ns, "SOURCE_SAMPLE_CLOCK_INVALID")
            upper = _integer(self.sample_upper_utc_ns, "SOURCE_SAMPLE_CLOCK_INVALID")
            if lower > upper or upper > bounds[1].upper_ns:
                raise EvidenceBlocked("SOURCE_SAMPLE_TIME_INCOHERENT")
            if policy.sample_max_age_ns is None:
                raise EvidenceBlocked("POLICY_SAMPLE_CAP_MISSING")
            if clock.bounds(decision_mono_ns).upper_ns - lower > policy.sample_max_age_ns:
                raise EvidenceBlocked("SOURCE_SAMPLE_STALE")
        return availability


@dataclass(frozen=True)
class Decision:
    status: str
    fixed_origin_utc_ns: int
    fixed_decision_mono_ns: int
    required_upper_utc_ns: int | None
    blocked_source: str | None = None

    @property
    def claimed_timing_eligible(self) -> bool:
        return self.status == "CLAIMED_TIMING_ELIGIBLE"


def evaluate_fixed_origin(
    clock: ClockCalibration,
    records: Sequence[SourceEvidence],
    source_policies: Mapping[str, SourcePolicy],
    *,
    predeclared_sources: PredeclaredSourceSet,
    fixed_origin_utc_ns: int,
    fixed_decision_mono_ns: int,
    feature_ready_mono_ns: int | None,
    feature_admission_mono_ns: int | None,
) -> Decision:
    """Check fixed-origin R(F) against claimed records and native family policy.

    Only the caller can bind the predeclared set to a protected registry; this
    function checks its *internal* consistency, not its provenance or signature.
    """

    def stop(code: str, source: str | None = None) -> Decision:
        return Decision(code, fixed_origin_utc_ns, fixed_decision_mono_ns, None, source)

    try:
        _integer(fixed_origin_utc_ns, "ORIGIN_INVALID")
        _integer(fixed_decision_mono_ns, "DECISION_INVALID")
        if type(predeclared_sources) is not PredeclaredSourceSet:
            raise EvidenceBlocked("REQUIRED_CONTRACT_MISSING")
        required_families = predeclared_sources.identities(fixed_origin_utc_ns)
        if not records:
            raise EvidenceBlocked("REQUIRED_SOURCE_MISSING")
        if feature_ready_mono_ns is None or feature_admission_mono_ns is None:
            raise EvidenceBlocked("FEATURE_ADMISSION_UNKNOWN")
        ready = _integer(feature_ready_mono_ns, "FEATURE_READY_INVALID")
        admitted = _integer(feature_admission_mono_ns, "FEATURE_ADMISSION_INVALID")
        if admitted < ready:
            raise EvidenceBlocked("FEATURE_ADMISSION_PRECEDES_READY")
        # A policy map is an *external claim*, not a trust root or a source verifier.
        if not isinstance(source_policies, Mapping):
            raise EvidenceBlocked("POLICY_MAP_INVALID")
        decision_lower = clock.bounds(fixed_decision_mono_ns).lower_ns
        if decision_lower < fixed_origin_utc_ns:
            raise EvidenceBlocked("DECISION_PRECEDES_FIXED_ORIGIN")
        if any(type(r) is not SourceEvidence for r in records):
            raise EvidenceBlocked("SOURCE_RECORD_TYPE_INVALID")
        ids = [_identity(r.source_id, "SOURCE_ID_INVALID") for r in records]
        if len(set(ids)) != len(ids):
            raise EvidenceBlocked("DUPLICATE_SOURCE_ID")
        supplied = set(ids)
        if supplied != set(required_families):
            raise EvidenceBlocked(
                "REQUIRED_SOURCE_MISSING"
                if set(required_families) - supplied
                else "UNDECLARED_SOURCE"
            )
        # Reject an incomplete/extra policy mapping too: it is an input claim,
        # not a way for the caller to silently drop a required data stream.
        policy_ids = set()
        for key in source_policies:
            policy_ids.add(_identity(key, "POLICY_ID_INVALID"))
        if policy_ids != set(required_families):
            raise EvidenceBlocked("REQUIRED_POLICY_COVERAGE_MISMATCH")
        required = max(clock.bounds(ready).upper_ns, clock.bounds(admitted).upper_ns)
        for record in records:
            try:
                policy = source_policies.get(record.source_id)
                if type(policy) is not SourcePolicy:
                    raise EvidenceBlocked("SOURCE_POLICY_MISSING")
                if policy.family != required_families[record.source_id]:
                    raise EvidenceBlocked("SOURCE_FAMILY_CONTRACT_MISMATCH")
                times = (record.validated_mono_ns, record.admission_mono_ns)
                if any(x is None or type(x) is not int for x in times):
                    raise EvidenceBlocked("SOURCE_ADMISSION_INVALID")
                # "feature_ready" means a COMMITTED projection ready for
                # reading; speculative compute may occur earlier, but it must
                # not be passed in as this published/visible feature clock.
                if ready < times[1] or admitted < ready:
                    raise EvidenceBlocked("FEATURE_PRECEDES_SOURCE_ADMISSION")
                required = max(
                    required, record.latest_claimed_utc_ns(clock, policy, fixed_decision_mono_ns)
                )
            except EvidenceBlocked as exc:
                return stop(exc.code, record.source_id)
        required += DECISION_GUARD_NS
        if decision_lower < required:
            return Decision(
                "NO_ACTION_LATE_INFORMATION", fixed_origin_utc_ns, fixed_decision_mono_ns, required
            )
        return Decision(
            "CLAIMED_TIMING_ELIGIBLE", fixed_origin_utc_ns, fixed_decision_mono_ns, required
        )
    except EvidenceBlocked as exc:
        return stop(exc.code)
