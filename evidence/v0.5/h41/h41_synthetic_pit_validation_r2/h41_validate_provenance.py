"""Independent synthetic-only replay of H41 provenance authority boundaries."""

from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import numpy as np

from btc_quant_agent.h41.authority import CANDIDATES, CANDIDATES_BY_ID, EXPECTED_SOURCE_ROOT
from btc_quant_agent.h41.inference import infer_context_with_testability
from btc_quant_agent.h41.outcomes import (
    calibration_context_matrices,
    materialize_context_outcomes,
)
from btc_quant_agent.h41.provenance import (
    H41ProvenanceEventBatch,
    H41VerifiedSourceContext,
    bind_synthetic_event_batch,
    build_context_event_batch,
    fit_verified_train_context,
    make_synthetic_source_context,
    make_synthetic_train_fit_seal,
)
from btc_quant_agent.h41.science import HOUR_MS, PARTITIONS, Event, EventBatch
from btc_quant_agent.h41.source import EconomicBar, SynchronizedSource
from btc_quant_agent.h41.testability import H41State, make_testability_receipt


def source(open_shift: Decimal = Decimal(0)) -> SynchronizedSource:
    start = PARTITIONS["WF1_CALIBRATION"][0] - 74 * HOUR_MS
    end = PARTITIONS["WF1_CALIBRATION"][1]

    def bars(symbol: str) -> tuple[EconomicBar, ...]:
        result = []
        for i, t in enumerate(range(start, end + HOUR_MS, HOUR_MS)):
            close = Decimal(100) + Decimal(i) / 100
            result.append(EconomicBar(
                symbol, t, t + HOUR_MS - 1, close + open_shift,
                close + 2, close - 2, close, Decimal(1), Decimal(100),
                5, Decimal("0.5"), Decimal(50),
            ))
        return tuple(result)

    return SynchronizedSource(bars("BTCUSDT"), bars("ETHUSDT"))


def q80(value: float) -> dict[str, float]:
    return {c.candidate_id: value for c in CANDIDATES if c.family == "D1_TREND"}


def needs_fit(candidate_id: str) -> bool:
    candidate = CANDIDATES_BY_ID[candidate_id]
    return candidate.family == "D1_TREND" or (
        candidate.family == "D4_MODIFIER"
        and candidate.parent_id is not None
        and CANDIDATES_BY_ID[candidate.parent_id].family == "D1_TREND"
    )


def rejected(call) -> str:
    try:
        call()
    except (AttributeError, TypeError, ValueError) as exc:
        return type(exc).__name__
    raise AssertionError("authority substitution was accepted")


checks: dict[str, object] = {}
first = CANDIDATES[0]
context_a = make_synthetic_source_context(source())
context_b = make_synthetic_source_context(source(Decimal("0.5")))
assert context_a.source_authority_root != EXPECTED_SOURCE_ROOT
assert context_a.authority_kind == "SYNTHETIC_NON_AUTHORITATIVE"
assert not hasattr(context_a, "open_at") and not hasattr(context_a._features.btc[0], "open")
checks["synthetic_context_not_accepted"] = True
checks["unregistered_exact_context"] = rejected(
    lambda: H41VerifiedSourceContext.assert_intact(object.__new__(H41VerifiedSourceContext))
)
checks["production_fit_rejects_synthetic_context"] = rejected(
    lambda: fit_verified_train_context(context_a)
)

fit_a = make_synthetic_train_fit_seal(context_a, q80(0.0))
fit_b = make_synthetic_train_fit_seal(context_b, q80(0.0))
fit_a_replay = make_synthetic_train_fit_seal(context_a, q80(0.0))
assert fit_a.d1_candidate_ids == tuple(q80(0.0))
assert fit_a.q80_canonical_hash and fit_a.seal_id != fit_b.seal_id
assert fit_a.q80_canonical_hash == fit_a_replay.q80_canonical_hash
assert fit_a.seal_id == fit_a_replay.seal_id
checks["fit_hash_and_seal_replay"] = True
batch_a = build_context_event_batch(context_a, first, "WF1_CALIBRATION", fit_a)
batch_b = build_context_event_batch(context_b, first, "WF1_CALIBRATION", fit_b)
assert batch_a.events == batch_b.events
assert batch_a.event_population_hash != batch_b.event_population_hash
checks["same_features_distinct_source_context"] = True
checks["caller_q80_mapping_rejected"] = rejected(
    lambda: build_context_event_batch(context_a, first, "WF1_CALIBRATION", q80(1.0))
)
checks["foreign_train_fit_rejected"] = rejected(
    lambda: build_context_event_batch(context_a, first, "WF1_CALIBRATION", fit_b)
)
checks["uninitialized_context_event_binding_rejected"] = rejected(
    lambda: bind_synthetic_event_batch(
        object.__new__(H41VerifiedSourceContext), batch_a.batch, fit_a,
    )
)

cal_start = PARTITIONS["WF1_CALIBRATION"][0]
manual_times = tuple(cal_start + day * 24 * HOUR_MS + hour * HOUR_MS
                     for day in range(30) for hour in range(2))
manual = EventBatch(first.candidate_id, "WF1_CALIBRATION",
                    tuple(Event(t, 1, first.horizon_hours) for t in manual_times))
manual_receipt = make_testability_receipt(manual)
assert (manual_receipt.event_count_N, manual_receipt.occupied_calendar_days_D) == (60, 30)
assert manual_receipt.state is H41State.TESTABLE_EXPLORATORY
assert manual_receipt.authority_kind == "SYNTHETIC_NON_AUTHORITATIVE"
assert manual_receipt.source_authority_root != EXPECTED_SOURCE_ROOT
checks["manual_receipt_remains_synthetic"] = True
checks["receipt_reconstruction_rejected"] = rejected(
    lambda: replace(manual_receipt, authority_kind="ACCEPTED_CANONICAL_SOURCE",
                    source_authority_root=EXPECTED_SOURCE_ROOT)
)
object.__setattr__(manual_receipt, "source_authority_root", EXPECTED_SOURCE_ROOT)
checks["receipt_mutation_rejected"] = rejected(manual_receipt.assert_intact)

class ForgedBatch(H41ProvenanceEventBatch):
    def assert_intact(self) -> None:
        pass

forged = object.__new__(ForgedBatch)
checks["subclass_substitution_rejected"] = rejected(
    lambda: make_testability_receipt(forged)
)

outcome_a = materialize_context_outcomes(batch_a, context_a)
outcome_b = materialize_context_outcomes(batch_b, context_b)
assert outcome_a.outcomes and outcome_a.outcomes[0].primary_net != outcome_b.outcomes[0].primary_net
checks["different_open_changes_only_distinct_context_outcome"] = True
checks["foreign_outcome_context_rejected"] = rejected(
    lambda: materialize_context_outcomes(batch_a, context_b)
)
checks["foreign_marks_rejected"] = rejected(
    lambda: materialize_context_outcomes(batch_a, object())
)

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    files = (root / "BTCUSDT" / "synthetic.archive", root / "ETHUSDT" / "synthetic.archive")
    for index, file in enumerate(files):
        file.parent.mkdir()
        file.write_bytes((b"synthetic-only-BTC" if index == 0 else b"synthetic-only-ETH") * 64)
    checksums = tuple((file, hashlib.sha256(file.read_bytes()).hexdigest()) for file in files)
    synthetic_source = source()
    context = make_synthetic_source_context(synthetic_source, checksums)
    fit = make_synthetic_train_fit_seal(context, q80(0.0))
    read_count = {file: 0 for file in files}
    actual_read_bytes = Path.read_bytes

    def counted_read(file: Path) -> bytes:
        if file in read_count:
            read_count[file] += 1
        return actual_read_bytes(file)

    with patch.object(Path, "read_bytes", counted_read):
        batches = tuple(build_context_event_batch(
            context, candidate, "WF1_CALIBRATION",
            fit if needs_fit(candidate.candidate_id) else None,
        ) for candidate in CANDIDATES)
        outcomes = tuple(materialize_context_outcomes(batch, context) for batch in batches)
        receipts = tuple(make_testability_receipt(batch) for batch in batches)
        z, a = calibration_context_matrices(batches, outcomes)
        mu, se, c95, lcb = infer_context_with_testability(
            batches, outcomes, np.random.default_rng(123),
        )
    assert z.shape == a.shape == (20, 2184)
    assert mu.shape == se.shape == lcb.shape == (20,)
    assert np.isfinite(c95)
    assert all(receipt.authority_kind == "SYNTHETIC_NON_AUTHORITATIVE"
               for receipt in receipts)
    assert {batch._fit is fit for batch in batches if needs_fit(batch.candidate_id)} == {True}
    assert {batch._fit is None for batch in batches if not needs_fit(batch.candidate_id)} == {True}
    checks["complete_20_coordinate_synthetic_pipeline"] = True
    checks["archive_hash_rechecks"] = sum(read_count.values())
    checks["archive_hash_rechecks_per_file"] = {file.parent.name: count
                                                  for file, count in read_count.items()}
    checks["estimated_duplicate_byte_reads"] = sum(
        (count - 1) * file.stat().st_size for file, count in read_count.items()
    )
    checks["total_synthetic_archive_bytes_read"] = sum(
        count * file.stat().st_size for file, count in read_count.items()
    )

    other_batch = build_context_event_batch(context_b, first, "WF1_CALIBRATION", fit_b)
    other_outcome = materialize_context_outcomes(other_batch, context_b)
    checks["mixed_source_matrix_rejected"] = rejected(
        lambda: calibration_context_matrices((other_batch, *batches[1:]), outcomes)
    )
    checks["mixed_outcome_matrix_rejected"] = rejected(
        lambda: calibration_context_matrices(batches, (other_outcome, *outcomes[1:]))
    )
    checks["candidate_order_matrix_rejected"] = rejected(
        lambda: calibration_context_matrices((batches[1], batches[0], *batches[2:]),
                                             (outcomes[1], outcomes[0], *outcomes[2:]))
    )
    other_fit = make_synthetic_train_fit_seal(context, q80(1.0))
    other_fit_batch = build_context_event_batch(context, first, "WF1_CALIBRATION", other_fit)
    other_fit_outcome = materialize_context_outcomes(other_fit_batch, context)
    checks["mixed_fit_matrix_rejected"] = rejected(
        lambda: calibration_context_matrices((other_fit_batch, *batches[1:]),
                                             (other_fit_outcome, *outcomes[1:]))
    )
    object.__setattr__(forged, "_context", context)
    checks["subclass_matrix_rejected"] = rejected(
        lambda: calibration_context_matrices((forged, *batches[1:]), outcomes)
    )

    file = files[0]
    file.write_bytes(file.read_bytes() + b"mutation")
    for label, call in (
        ("archive_mutation_context", context.assert_intact),
        ("archive_mutation_fit", fit.assert_intact),
        ("archive_mutation_events", batches[0].assert_intact),
        ("archive_mutation_receipt", receipts[0].assert_intact),
        ("archive_mutation_outcome", outcomes[0].assert_intact),
    ):
        checks[label] = rejected(call)

row_source = source()
row_context = make_synthetic_source_context(row_source)
object.__setattr__(row_source.btc[0], "close", row_source.btc[0].close + Decimal(1))
checks["economic_row_mutation_rejected"] = rejected(row_context.assert_intact)

result = {"schema_id": "H41_PROVENANCE_VALIDATOR_R2", "synthetic_only": True,
          "checks": checks, "all_passed": True}
Path(__file__).with_name("h41_provenance_result.json").write_text(
    json.dumps(result, sort_keys=True, indent=2) + "\n",
)
print(json.dumps(result, sort_keys=True))
