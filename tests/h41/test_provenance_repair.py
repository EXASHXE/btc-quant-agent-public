"""Synthetic adversarial coverage for H41 scientific provenance binding."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest

from btc_quant_agent.h41.authority import CANDIDATES, EXPECTED_SOURCE_ROOT
from btc_quant_agent.h41.inference import infer_context_with_testability, infer_with_testability
from btc_quant_agent.h41.outcomes import (
    calibration_context_matrices,
    calibration_matrices,
    materialize_context_outcomes,
    materialize_outcomes,
)
from btc_quant_agent.h41.provenance import (
    H41ProvenanceEventBatch,
    H41VerifiedSourceContext,
    bind_synthetic_event_batch,
    build_context_event_batch,
    fit_verified_train_context,
    load_verified_accepted_source_context,
    make_synthetic_source_context,
    make_synthetic_train_fit_seal,
)
from btc_quant_agent.h41.science import HOUR_MS, PARTITIONS, Event, EventBatch
from btc_quant_agent.h41.source import EconomicBar, SynchronizedSource
from btc_quant_agent.h41.testability import make_testability_receipt


def _source(*, changed_open: bool = False) -> SynchronizedSource:
    start = PARTITIONS["WF1_CALIBRATION"][0] - 74 * HOUR_MS
    end = PARTITIONS["WF1_CALIBRATION"][1]

    def bars(symbol: str) -> tuple[EconomicBar, ...]:
        result = []
        for i, t in enumerate(range(start, end + HOUR_MS, HOUR_MS)):
            close = Decimal(100) + Decimal(i) / 100
            opened = close + (Decimal("0.5") if changed_open else Decimal(0))
            result.append(EconomicBar(symbol, t, t + HOUR_MS - 1, opened,
                                      close + 2, close - 2, close, Decimal(1),
                                      Decimal(100), 5, Decimal("0.5"), Decimal(50)))
        return tuple(result)

    return SynchronizedSource(bars("BTCUSDT"), bars("ETHUSDT"))


def _fit(context: H41VerifiedSourceContext):
    return make_synthetic_train_fit_seal(
        context, {c.candidate_id: 0.0 for c in CANDIDATES if c.family == "D1_TREND"},
    )


def test_synthetic_context_cannot_claim_accepted_root_or_be_forged() -> None:
    context = make_synthetic_source_context(_source())
    assert context.authority_kind == "SYNTHETIC_NON_AUTHORITATIVE"
    assert context.source_authority_root != EXPECTED_SOURCE_ROOT
    assert not hasattr(context, "open_at")
    assert not hasattr(context, "_source")
    assert not hasattr(context._features.btc[0], "open")
    context.assert_intact()
    with pytest.raises(ValueError, match="unregistered|integrity"):
        object.__new__(H41VerifiedSourceContext).assert_intact()
    with pytest.raises(ValueError, match="accepted source context"):
        fit_verified_train_context(context)
    object.__setattr__(context, "source_authority_root", EXPECTED_SOURCE_ROOT)
    with pytest.raises(ValueError, match="integrity"):
        context.assert_intact()


def test_archive_byte_mutation_invalidates_context(tmp_path: Path) -> None:
    path = tmp_path / "BTCUSDT" / "synthetic.zip"
    path.parent.mkdir()
    path.write_bytes(b"synthetic archive A")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    context = make_synthetic_source_context(_source(), ((path, digest),))
    context.assert_intact()
    path.write_bytes(b"synthetic archive B")
    with pytest.raises(ValueError, match="archive integrity"):
        context.assert_intact()
    with pytest.raises(ValueError):
        load_verified_accepted_source_context(tmp_path)


def test_same_views_foreign_q80_and_fit_context_rejected() -> None:
    context_a = make_synthetic_source_context(_source())
    context_b = make_synthetic_source_context(_source(changed_open=True))
    fit_a, fit_b = _fit(context_a), _fit(context_b)
    candidate = CANDIDATES[0]
    batch = build_context_event_batch(context_a, candidate, "WF1_CALIBRATION", fit_a)
    same_completed_different_opens = build_context_event_batch(
        context_b, candidate, "WF1_CALIBRATION", fit_b,
    )
    assert batch.events and batch.source_context_id == context_a.source_context_id
    assert batch.events == same_completed_different_opens.events
    assert (materialize_context_outcomes(batch, context_a).outcomes[0].primary_net
            != materialize_context_outcomes(same_completed_different_opens,
                                            context_b).outcomes[0].primary_net)
    assert batch.train_fit_seal_id == fit_a.seal_id
    with pytest.raises((TypeError, ValueError)):
        build_context_event_batch(context_a, candidate, "WF1_CALIBRATION",  # type: ignore[arg-type]
                                  {candidate.candidate_id: 1.0})
    with pytest.raises(ValueError, match="fit|context"):
        build_context_event_batch(context_a, candidate, "WF1_CALIBRATION", fit_b)
    assert fit_a.seal_id != fit_b.seal_id


def test_manual_events_and_synthetic_batches_cannot_mint_accepted_receipt() -> None:
    t = PARTITIONS["WF1_CALIBRATION"][0]
    raw = EventBatch(CANDIDATES[0].candidate_id, "WF1_CALIBRATION", (Event(t, 1, 4),))
    raw_receipt = make_testability_receipt(raw)
    assert raw_receipt.source_authority_root != EXPECTED_SOURCE_ROOT
    assert raw_receipt.authority_kind == "SYNTHETIC_NON_AUTHORITATIVE"

    context = make_synthetic_source_context(_source())
    bound = bind_synthetic_event_batch(context, raw, _fit(context))
    receipt = make_testability_receipt(bound)
    assert receipt.source_authority_root != EXPECTED_SOURCE_ROOT
    assert receipt.event_population_hash == bound.event_population_hash
    assert receipt.source_context_id == context.source_context_id
    with pytest.raises(ValueError, match="authority"):
        replace(receipt, source_authority_root=EXPECTED_SOURCE_ROOT)
    with pytest.raises(ValueError, match="authority"):
        replace(receipt, authority_kind="ACCEPTED_CANONICAL_SOURCE",
                source_authority_root=EXPECTED_SOURCE_ROOT)


def test_foreign_marks_and_contexts_rejected_after_event_commit() -> None:
    context_a = make_synthetic_source_context(_source())
    context_b = make_synthetic_source_context(_source(changed_open=True))
    t = PARTITIONS["WF1_CALIBRATION"][0]
    raw = EventBatch(CANDIDATES[0].candidate_id, "WF1_CALIBRATION", (Event(t, 1, 4),))
    batch = bind_synthetic_event_batch(context_a, raw, _fit(context_a))

    class ForeignMarks:
        def open_at(self, symbol: str, open_time_ms: int) -> Decimal:
            return Decimal(100)

    with pytest.raises((TypeError, ValueError)):
        materialize_context_outcomes(batch, ForeignMarks())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="synthetic"):
        materialize_outcomes(batch, ForeignMarks())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="context"):
        materialize_context_outcomes(batch, context_b)
    result = materialize_context_outcomes(batch, context_a)
    assert result.source_context_id == batch.source_context_id
    assert result.event_population_hash == batch.event_population_hash


def test_underlying_source_mutation_invalidates_context_and_events() -> None:
    source = _source()
    context = make_synthetic_source_context(source)
    fit = _fit(context)
    batch = build_context_event_batch(context, CANDIDATES[0], "WF1_CALIBRATION", fit)
    object.__setattr__(source.btc[0], "close", source.btc[0].close + Decimal(1))
    with pytest.raises(ValueError, match="source|integrity"):
        context.assert_intact()
    with pytest.raises(ValueError, match="source|integrity"):
        make_testability_receipt(batch)


def test_context_matrix_rejects_mixed_sources_and_fits() -> None:
    context_a = make_synthetic_source_context(_source())
    context_b = make_synthetic_source_context(_source(changed_open=True))
    fit_a, fit_b = _fit(context_a), _fit(context_b)
    t = PARTITIONS["WF1_CALIBRATION"][0]
    batches = tuple(
        bind_synthetic_event_batch(
            context_a,
            EventBatch(candidate.candidate_id, "WF1_CALIBRATION",
                       (Event(t, 1, candidate.horizon_hours),)),
            fit_a if candidate.family == "D1_TREND" or (
                candidate.family == "D4_MODIFIER" and candidate.parent_id in {
                    c.candidate_id for c in CANDIDATES if c.family == "D1_TREND"
                }
            ) else None,
        )
        for candidate in CANDIDATES
    )
    results = tuple(materialize_context_outcomes(batch, context_a) for batch in batches)
    z, a = calibration_context_matrices(batches, results)
    assert z.shape == a.shape == (20, 2184)
    assert int(a.sum()) == 20
    class ForgedBatch(H41ProvenanceEventBatch):
        def assert_intact(self) -> None:
            pass

    forged = object.__new__(ForgedBatch)
    object.__setattr__(forged, "_context", context_a)
    with pytest.raises(TypeError, match="source-bound"):
        calibration_context_matrices((forged, *batches[1:]), results)
    receipts = tuple(make_testability_receipt(batch) for batch in batches)
    with pytest.raises(TypeError, match="synthetic"):
        calibration_matrices(batches, tuple(result.outcomes for result in results))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="synthetic"):
        infer_with_testability(z, a, receipts, batches, np.random.default_rng(2))  # type: ignore[arg-type]
    _, _, c95, lcb = infer_context_with_testability(batches, results,
                                                     np.random.default_rng(2))
    assert np.isnan(c95) and np.all(np.isneginf(lcb))

    foreign_batch = bind_synthetic_event_batch(
        context_b, batches[0].batch, fit_b,
    )
    with pytest.raises(ValueError, match="context"):
        calibration_context_matrices((foreign_batch, *batches[1:]), results)
    alternate_fit = make_synthetic_train_fit_seal(
        context_a, {c.candidate_id: 1.0 for c in CANDIDATES if c.family == "D1_TREND"},
    )
    mixed_fit_batch = bind_synthetic_event_batch(context_a, batches[0].batch, alternate_fit)
    mixed_result = materialize_context_outcomes(mixed_fit_batch, context_a)
    with pytest.raises(ValueError, match="fit"):
        calibration_context_matrices((mixed_fit_batch, *batches[1:]),
                                     (mixed_result, *results[1:]))


def test_subclass_integrity_override_cannot_mint_accepted_receipt() -> None:
    class ForgedContext(H41VerifiedSourceContext):
        def assert_intact(self) -> None:
            pass

    class ForgedBatch(H41ProvenanceEventBatch):
        def assert_intact(self) -> None:
            pass

    t = PARTITIONS["WF1_CALIBRATION"][0]
    context = object.__new__(ForgedContext)
    object.__setattr__(context, "source_authority_root", EXPECTED_SOURCE_ROOT)
    batch = object.__new__(ForgedBatch)
    object.__setattr__(batch, "batch", EventBatch(CANDIDATES[0].candidate_id,
                                                  "WF1_CALIBRATION", (Event(t, 1, 4),)))
    object.__setattr__(batch, "authority_kind", "ACCEPTED_CANONICAL_SOURCE")
    object.__setattr__(batch, "source_context_id", "forged-context")
    object.__setattr__(batch, "train_fit_seal_id", "forged-fit")
    object.__setattr__(batch, "event_population_hash", "forged-population")
    object.__setattr__(batch, "_context", context)
    with pytest.raises((TypeError, ValueError)):
        make_testability_receipt(batch)


def test_receipt_mutation_invalidates_runtime_integrity() -> None:
    t = PARTITIONS["WF1_CALIBRATION"][0]
    raw = EventBatch(CANDIDATES[0].candidate_id, "WF1_CALIBRATION", (Event(t, 1, 4),))
    receipt = make_testability_receipt(raw)
    receipt.assert_intact()
    object.__setattr__(receipt, "event_count_N", 60)
    with pytest.raises(ValueError, match="receipt.*integrity"):
        receipt.assert_intact()
