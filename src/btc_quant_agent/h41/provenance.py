"""Source-bound H41 scientific inputs; synthetic inputs never gain source authority."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Literal
from weakref import WeakKeyDictionary

from .authority import (
    CANDIDATES,
    CANDIDATES_BY_ID,
    EXPECTED_HASHES,
    EXPECTED_SOURCE_ROOT,
    SOURCE_BINDING,
    Candidate,
    canonical_json,
    canonical_sha256,
    verify_frozen_bindings,
)
from .science import (
    HOUR_MS,
    PARTITIONS,
    CompletedBar,
    CompletedPairView,
    Event,
    EventBatch,
    build_event_batch,
    train_q80,
)
from .source import SynchronizedSource, load_accepted_pair

AuthorityKind = Literal["ACCEPTED_CANONICAL_SOURCE", "SYNTHETIC_NON_AUTHORITATIVE"]
SYNTHETIC_SOURCE_ROOT = "SYNTHETIC_NON_AUTHORITATIVE"
_ACCEPTED: AuthorityKind = "ACCEPTED_CANONICAL_SOURCE"
_SYNTHETIC: AuthorityKind = "SYNTHETIC_NON_AUTHORITATIVE"


def _fingerprints(source: SynchronizedSource) -> tuple[str, str, str]:
    projections: list[str] = []
    for bars in (source.btc, source.eth):
        digest = hashlib.sha256()
        for bar in bars:
            digest.update(canonical_json(bar.projection()) + b"\n")
        projections.append(digest.hexdigest())
    membership = hashlib.sha256(canonical_json(
        [bar.open_time_ms for bar in source.btc],
    )).hexdigest()
    return projections[0], projections[1], membership


@dataclass(frozen=True, slots=True)
class H41CompletedSource:
    """Only finalized timestamp/High/Low/Close values reach event generation."""

    btc: tuple[CompletedBar, ...]
    eth: tuple[CompletedBar, ...]

    def completed_view(self, decision_time_ms: int, lookback: int) -> CompletedPairView:
        first = self.btc[0].open_time_ms
        offset = (decision_time_ms - first) // HOUR_MS
        if decision_time_ms % HOUR_MS or offset < lookback + 1 or offset > len(self.btc):
            raise ValueError("incomplete completed-bar history")
        return CompletedPairView(
            decision_time_ms,
            tuple(reversed(self.btc[offset - lookback - 1:offset])),
            tuple(reversed(self.eth[offset - lookback - 1:offset])),
        )


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True, init=False)
class H41VerifiedSourceContext:
    authority_kind: AuthorityKind
    source_authority_root: str
    btc_projection_hash: str
    eth_projection_hash: str
    timestamp_membership_hash: str
    candidate_ledger_hash: str
    frozen_semantic_root: str
    source_context_id: str
    _features: H41CompletedSource = field(repr=False)
    _archive_checks: tuple[tuple[Path, str], ...] = field(repr=False)

    def assert_intact(self) -> None:
        if type(self) is not H41VerifiedSourceContext:
            raise TypeError("exact H41 source context required")
        recorded = _CONTEXT_REGISTRY.get(self)
        if recorded is None:
            raise ValueError("unregistered H41 source context")
        source, features, fields = recorded
        if self._features is not features or _context_fields(self) != fields:
            raise ValueError("H41 source context integrity mismatch")
        if _fingerprints(source) != fields[2:5]:
            raise ValueError("H41 source economic row integrity mismatch")
        if (features.btc != tuple(bar.completed() for bar in source.btc)
                or features.eth != tuple(bar.completed() for bar in source.eth)):
            raise ValueError("H41 completed source integrity mismatch")
        for path, expected in self._archive_checks:
            if (path.is_symlink() or path.parent.is_symlink()
                    or path.parent.parent.is_symlink() or not path.is_file()
                    or hashlib.sha256(path.read_bytes()).hexdigest() != expected):
                raise ValueError("H41 source archive integrity mismatch")

    def completed_view(self, decision_time_ms: int, lookback: int) -> CompletedPairView:
        H41VerifiedSourceContext.assert_intact(self)
        return self._features.completed_view(decision_time_ms, lookback)


def _context_fields(context: H41VerifiedSourceContext) -> tuple[object, ...]:
    return (context.authority_kind, context.source_authority_root,
            context.btc_projection_hash, context.eth_projection_hash,
            context.timestamp_membership_hash, context.candidate_ledger_hash,
            context.frozen_semantic_root, context.source_context_id,
            context._features, context._archive_checks)


_CONTEXT_REGISTRY: WeakKeyDictionary[
    H41VerifiedSourceContext,
    tuple[SynchronizedSource, H41CompletedSource, tuple[object, ...]],
] = WeakKeyDictionary()


def _outcome_source(context: H41VerifiedSourceContext) -> SynchronizedSource:
    """Post-event only: retrieve the sealed Open-mark source from the registry."""
    H41VerifiedSourceContext.assert_intact(context)
    recorded = _CONTEXT_REGISTRY.get(context)
    if recorded is None:
        raise ValueError("unregistered H41 outcome source context")
    return recorded[0]


def _new_context(source: SynchronizedSource, kind: AuthorityKind,
                 checks: tuple[tuple[Path, str], ...]) -> H41VerifiedSourceContext:
    if type(source) is not SynchronizedSource:
        raise TypeError("exact synchronized H41 source required")
    btc, eth, membership = _fingerprints(source)
    if kind == _ACCEPTED:
        verify_frozen_bindings()
        expected_records = tuple(
            (asset, row) for asset in ("BTC", "ETH")
            for row in SOURCE_BINDING["archive_records"][asset]
        )
        if ((btc, eth) != (SOURCE_BINDING["projection_hashes"]["BTC"],
                           SOURCE_BINDING["projection_hashes"]["ETH"])
                or membership != SOURCE_BINDING["membership_hashes"]["joint"]
                or len(checks) != len(expected_records)
                or any(path.name != row["archive_name"]
                       or path.parent.name != f"{asset}USDT"
                       or digest != row["official_archive_checksum"]
                       for (path, digest), (asset, row) in zip(
                           checks, expected_records, strict=True))):
            raise ValueError("accepted H41 source context mismatch")
        root = EXPECTED_SOURCE_ROOT
    else:
        root = SYNTHETIC_SOURCE_ROOT
    ledger = EXPECTED_HASHES["candidate_ledger_hash"]
    semantic = EXPECTED_HASHES["frozen_h41_semantic_root_hash"]
    identity = canonical_sha256({
        "schema_id": "H41_SOURCE_CONTEXT_V1", "authority_kind": kind,
        "source_authority_root": root, "btc_projection_hash": btc,
        "eth_projection_hash": eth, "timestamp_membership_hash": membership,
        "candidate_ledger_hash": ledger, "frozen_semantic_root": semantic,
    })
    features = H41CompletedSource(
        tuple(bar.completed() for bar in source.btc),
        tuple(bar.completed() for bar in source.eth),
    )
    context = object.__new__(H41VerifiedSourceContext)
    for name, value in (
        ("authority_kind", kind), ("source_authority_root", root),
        ("btc_projection_hash", btc), ("eth_projection_hash", eth),
        ("timestamp_membership_hash", membership),
        ("candidate_ledger_hash", ledger), ("frozen_semantic_root", semantic),
        ("source_context_id", identity), ("_features", features),
        ("_archive_checks", checks),
    ):
        object.__setattr__(context, name, value)
    _CONTEXT_REGISTRY[context] = (source, features, _context_fields(context))
    H41VerifiedSourceContext.assert_intact(context)
    return context


def load_verified_accepted_source_context(archive_root: Path) -> H41VerifiedSourceContext:
    """The only accepted-context factory; parses every accepted archive first."""
    source = load_accepted_pair(archive_root)
    checks = tuple(
        (archive_root / f"{asset}USDT" / row["archive_name"],
         row["official_archive_checksum"])
        for asset in ("BTC", "ETH")
        for row in SOURCE_BINDING["archive_records"][asset]
    )
    return _new_context(source, _ACCEPTED, checks)


def make_synthetic_source_context(
    source: SynchronizedSource,
    archive_checks: tuple[tuple[Path, str], ...] = (),
) -> H41VerifiedSourceContext:
    """Explicit non-authoritative fixture context with optional file-change checks."""
    return _new_context(source, _SYNTHETIC, archive_checks)


_D1_IDS = tuple(c.candidate_id for c in CANDIDATES if c.family == "D1_TREND")


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True, init=False)
class H41TrainFitSeal:
    authority_kind: AuthorityKind
    source_context_id: str
    frozen_semantic_root: str
    candidate_ledger_hash: str
    partition: str
    d1_candidate_ids: tuple[str, ...]
    q80_values: tuple[tuple[str, float], ...]
    q80_canonical_hash: str
    fit_status: str
    seal_id: str
    _context: H41VerifiedSourceContext = field(repr=False)

    @property
    def q80_by_id(self) -> MappingProxyType[str, float]:
        return MappingProxyType(dict(self.q80_values))

    def assert_intact(self) -> None:
        if type(self) is not H41TrainFitSeal:
            raise TypeError("exact H41 TRAIN fit seal required")
        recorded = _FIT_REGISTRY.get(self)
        if recorded is None or self._context is not recorded[0] or _fit_fields(self) != recorded[1]:
            raise ValueError("unregistered or altered H41 TRAIN fit seal")
        H41VerifiedSourceContext.assert_intact(self._context)
        if self.source_context_id != self._context.source_context_id:
            raise ValueError("TRAIN fit source context mismatch")


def _fit_fields(fit: H41TrainFitSeal) -> tuple[object, ...]:
    return (fit.authority_kind, fit.source_context_id, fit.frozen_semantic_root,
            fit.candidate_ledger_hash, fit.partition, fit.d1_candidate_ids,
            fit.q80_values, fit.q80_canonical_hash, fit.fit_status, fit.seal_id)


_FIT_REGISTRY: WeakKeyDictionary[
    H41TrainFitSeal, tuple[H41VerifiedSourceContext, tuple[object, ...]]
] = WeakKeyDictionary()


def _accepted_train_values(context: H41VerifiedSourceContext) -> dict[str, float]:
    start, end = PARTITIONS["WF1_TRAIN"]
    values: dict[str, float] = {}
    for candidate in CANDIDATES:
        if candidate.family != "D1_TREND":
            continue
        first = start + (candidate.lookback_window_hours + 1) * HOUR_MS
        views = (context._features.completed_view(t, candidate.lookback_window_hours)
                 for t in range(first, end, HOUR_MS))
        values[candidate.candidate_id] = train_q80(candidate, views)
    H41VerifiedSourceContext.assert_intact(context)
    return values


def _new_fit(context: H41VerifiedSourceContext,
             values: dict[str, float] | None) -> H41TrainFitSeal:
    H41VerifiedSourceContext.assert_intact(context)
    if context.authority_kind == _ACCEPTED:
        if values is not None:
            raise ValueError("caller Q80 cannot create accepted TRAIN fit")
        values = _accepted_train_values(context)
    elif values is None:
        raise ValueError("synthetic TRAIN fit requires explicit synthetic values")
    if (set(values) != set(_D1_IDS)
            or any(not math.isfinite(value) or value < 0 for value in values.values())):
        raise ValueError("incomplete or invalid frozen D1 Q80 fit")
    ordered = tuple((candidate_id, float(values[candidate_id])) for candidate_id in _D1_IDS)
    q80_hash = canonical_sha256([(candidate_id, value.hex())
                                 for candidate_id, value in ordered])
    identity = canonical_sha256({
        "schema_id": "H41_TRAIN_FIT_SEAL_V1",
        "authority_kind": context.authority_kind,
        "source_context_id": context.source_context_id,
        "frozen_semantic_root": context.frozen_semantic_root,
        "candidate_ledger_hash": context.candidate_ledger_hash,
        "partition": "WF1_TRAIN", "d1_candidate_ids": _D1_IDS,
        "q80_canonical_hash": q80_hash, "fit_status": "PASS",
    })
    fit = object.__new__(H41TrainFitSeal)
    for name, value in (
        ("authority_kind", context.authority_kind),
        ("source_context_id", context.source_context_id),
        ("frozen_semantic_root", context.frozen_semantic_root),
        ("candidate_ledger_hash", context.candidate_ledger_hash),
        ("partition", "WF1_TRAIN"), ("d1_candidate_ids", _D1_IDS),
        ("q80_values", ordered), ("q80_canonical_hash", q80_hash),
        ("fit_status", "PASS"), ("seal_id", identity), ("_context", context),
    ):
        object.__setattr__(fit, name, value)
    _FIT_REGISTRY[fit] = (context, _fit_fields(fit))
    H41TrainFitSeal.assert_intact(fit)
    return fit


def fit_verified_train_context(context: H41VerifiedSourceContext) -> H41TrainFitSeal:
    """Compute every frozen D1 Q80 from this context's complete TRAIN clock."""
    if type(context) is not H41VerifiedSourceContext or context.authority_kind != _ACCEPTED:
        raise ValueError("accepted source context required for production TRAIN fit")
    return _new_fit(context, None)


def make_synthetic_train_fit_seal(
    context: H41VerifiedSourceContext, values: dict[str, float],
) -> H41TrainFitSeal:
    if type(context) is not H41VerifiedSourceContext or context.authority_kind != _SYNTHETIC:
        raise ValueError("synthetic context required for synthetic TRAIN fit")
    return _new_fit(context, values)


def _needs_fit(candidate: Candidate) -> bool:
    return candidate.family == "D1_TREND" or (
        candidate.family == "D4_MODIFIER"
        and candidate.parent_id is not None
        and CANDIDATES_BY_ID[candidate.parent_id].family == "D1_TREND"
    )


def _population_hash(batch: EventBatch, context_id: str, fit_id: str | None) -> str:
    return canonical_sha256({
        "schema_id": "H41_EVENT_POPULATION_V1", "candidate_id": batch.candidate_id,
        "partition": batch.partition, "source_context_id": context_id,
        "train_fit_seal_id": fit_id,
        "frozen_semantic_root": EXPECTED_HASHES["frozen_h41_semantic_root_hash"],
        "candidate_ledger_hash": EXPECTED_HASHES["candidate_ledger_hash"],
        "events": [(e.decision_time_ms, e.side, e.horizon_hours) for e in batch.events],
    })


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True, init=False)
class H41ProvenanceEventBatch:
    batch: EventBatch
    authority_kind: AuthorityKind
    source_context_id: str
    train_fit_seal_id: str | None
    event_population_hash: str
    frozen_semantic_root: str
    candidate_ledger_hash: str
    _context: H41VerifiedSourceContext = field(repr=False)
    _fit: H41TrainFitSeal | None = field(repr=False)

    @property
    def candidate_id(self) -> str:
        return self.batch.candidate_id

    @property
    def partition(self) -> str:
        return self.batch.partition

    @property
    def events(self) -> tuple[Event, ...]:
        return self.batch.events

    def assert_intact(self) -> None:
        if type(self) is not H41ProvenanceEventBatch:
            raise TypeError("exact H41 event population required")
        recorded = _BATCH_REGISTRY.get(self)
        if recorded is None or _batch_fields(self) != recorded:
            raise ValueError("unregistered or altered H41 event population")
        H41VerifiedSourceContext.assert_intact(self._context)
        if self._fit is not None:
            H41TrainFitSeal.assert_intact(self._fit)
        if (self.source_context_id != self._context.source_context_id
                or self.event_population_hash != _population_hash(
                    self.batch, self.source_context_id, self.train_fit_seal_id)):
            raise ValueError("H41 event source or population integrity mismatch")


def _batch_fields(batch: H41ProvenanceEventBatch) -> tuple[object, ...]:
    return (batch.batch, batch.authority_kind, batch.source_context_id,
            batch.train_fit_seal_id, batch.event_population_hash,
            batch.frozen_semantic_root, batch.candidate_ledger_hash,
            batch._context, batch._fit)


_BATCH_REGISTRY: WeakKeyDictionary[
    H41ProvenanceEventBatch, tuple[object, ...]
] = WeakKeyDictionary()


def _bind_batch(context: H41VerifiedSourceContext, batch: EventBatch,
                fit: H41TrainFitSeal | None, *, production_built: bool) -> H41ProvenanceEventBatch:
    H41VerifiedSourceContext.assert_intact(context)
    if type(batch) is not EventBatch:
        raise TypeError("exact H41 event batch required")
    if context.authority_kind == _ACCEPTED and not production_built:
        raise ValueError("caller events cannot acquire accepted source authority")
    candidate = CANDIDATES_BY_ID[batch.candidate_id]
    if _needs_fit(candidate):
        if type(fit) is not H41TrainFitSeal:
            raise ValueError("source-bound TRAIN fit required")
        H41TrainFitSeal.assert_intact(fit)
        if (fit.source_context_id != context.source_context_id
                or fit.authority_kind != context.authority_kind):
            raise ValueError("TRAIN fit and event source context mismatch")
        fit_id: str | None = fit.seal_id
    else:
        if fit is not None:
            raise ValueError("unneeded TRAIN fit on non-D1 candidate")
        fit_id = None
    if context.authority_kind == _ACCEPTED and batch != _derive_batch(
        context, candidate, batch.partition, fit,
    ):
        raise ValueError("accepted event population differs from source-derived events")
    bound = object.__new__(H41ProvenanceEventBatch)
    for name, value in (
        ("batch", batch), ("authority_kind", context.authority_kind),
        ("source_context_id", context.source_context_id),
        ("train_fit_seal_id", fit_id),
        ("event_population_hash", _population_hash(batch, context.source_context_id, fit_id)),
        ("frozen_semantic_root", context.frozen_semantic_root),
        ("candidate_ledger_hash", context.candidate_ledger_hash),
        ("_context", context), ("_fit", fit),
    ):
        object.__setattr__(bound, name, value)
    _BATCH_REGISTRY[bound] = _batch_fields(bound)
    H41ProvenanceEventBatch.assert_intact(bound)
    return bound


def bind_synthetic_event_batch(
    context: H41VerifiedSourceContext, batch: EventBatch,
    fit: H41TrainFitSeal | None = None,
) -> H41ProvenanceEventBatch:
    """Permit arbitrary event fixtures only under a synthetic identity."""
    if type(context) is not H41VerifiedSourceContext or context.authority_kind != _SYNTHETIC:
        raise ValueError("synthetic source context required")
    return _bind_batch(context, batch, fit, production_built=False)


def _derive_batch(context: H41VerifiedSourceContext, candidate: Candidate,
                  partition: str, fit: H41TrainFitSeal | None) -> EventBatch:
    q80 = fit.q80_by_id if fit is not None else MappingProxyType({})
    oldest = candidate.lookback_window_hours + (candidate.family == "D3_FAILED_BREAK")
    start, end = PARTITIONS[partition]
    first = start + (oldest + 1) * HOUR_MS if partition == "WF1_TRAIN" else start
    views = (context._features.completed_view(t, oldest)
             for t in range(first, end, HOUR_MS))
    return build_event_batch(candidate, views, q80, partition)


def build_context_event_batch(
    context: H41VerifiedSourceContext, candidate: Candidate, partition: str,
    fit: H41TrainFitSeal | None = None,
) -> H41ProvenanceEventBatch:
    """Build a complete event clock from bound completed bars and bound TRAIN fit."""
    if type(context) is not H41VerifiedSourceContext:
        raise TypeError("verified source context required")
    H41VerifiedSourceContext.assert_intact(context)
    if CANDIDATES_BY_ID.get(candidate.candidate_id) != candidate:
        raise ValueError("candidate differs from frozen ledger")
    if partition not in ("WF1_TRAIN", "WF1_CALIBRATION"):
        raise ValueError("protected or source-only partition")
    if _needs_fit(candidate):
        if type(fit) is not H41TrainFitSeal:
            raise ValueError("source-bound TRAIN fit required")
        H41TrainFitSeal.assert_intact(fit)
        if fit.source_context_id != context.source_context_id:
            raise ValueError("TRAIN fit source context mismatch")
    else:
        if fit is not None:
            raise ValueError("unneeded TRAIN fit on non-D1 candidate")
    batch = _derive_batch(context, candidate, partition, fit)
    H41VerifiedSourceContext.assert_intact(context)
    return _bind_batch(context, batch, fit, production_built=True)
