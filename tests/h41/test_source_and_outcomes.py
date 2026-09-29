from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import fields, replace
from decimal import Decimal
from pathlib import Path

import pytest

from btc_quant_agent.h41.authority import CANDIDATES, SOURCE_BINDING, canonical_json
from btc_quant_agent.h41.outcomes import EventOutcome, calibration_matrices, materialize_outcomes
from btc_quant_agent.h41.science import HOUR_MS, PARTITIONS, Event, EventBatch
from btc_quant_agent.h41.source import (
    EconomicBar,
    SynchronizedSource,
    canonical_number,
    load_accepted_archive,
    load_synthetic_archive,
    projection_sha256,
)
from btc_quant_agent.h41.testability import H41State, make_testability_receipt

START = 1_609_459_200_000


def _archive(tmp_path: Path, symbol: str, times: list[int], *, close: str = "100.00") -> tuple[Path, str]:
    name = f"{symbol}-1h-2021-01"
    rows = [f"{t},100.00,102,99,{close},1.0,{t + HOUR_MS - 1},100,5,0.5,50,0"
            for t in times]
    path = tmp_path / f"{name}.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{name}.csv", "\n".join(rows) + "\n")
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _bar(symbol: str, t: int, op: str = "100") -> EconomicBar:
    return EconomicBar(symbol, t, t + HOUR_MS - 1, Decimal(op), Decimal(102),
                       Decimal(99), Decimal(100), Decimal(1), Decimal(100),
                       5, Decimal(".5"), Decimal(50))


def test_source_projection_same_buffer_and_numeric_replay(tmp_path: Path) -> None:
    path, digest = _archive(tmp_path, "BTCUSDT", [START, START + HOUR_MS])
    parsed = load_synthetic_archive(path, "BTCUSDT", "2021-01", digest)
    assert parsed.archive_sha256 == digest
    assert parsed.projection_sha256 == projection_sha256((parsed,))
    assert canonical_number(Decimal("100.00")) == "100"
    assert canonical_number(Decimal("-0.000")) == "0"
    assert len(parsed.bars[0].projection()) == 14
    assert parsed.bars[0].projection()["close"] == "100"
    assert "100.00" not in repr(parsed.bars[0])
    assert SOURCE_BINDING["projection_hashes"]["BTC"] != parsed.projection_sha256
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="checksum"):
        load_synthetic_archive(path, "BTCUSDT", "2021-01", digest)


def test_native_product_and_accepted_checksum_binding(tmp_path: Path) -> None:
    path, digest = _archive(tmp_path, "BTCUSDT", [START])
    with pytest.raises(ValueError, match="product"):
        load_synthetic_archive(path, "ETHUSDT", "2021-01", digest)
    with pytest.raises(ValueError, match="checksum"):
        load_accepted_archive(path, "BTCUSDT", "2021-01")
    link = tmp_path / "BTCUSDT-1h-2021-02.zip"
    link.symlink_to(path)
    with pytest.raises(ValueError, match="path"):
        load_synthetic_archive(link, "BTCUSDT", "2021-02", digest)


@pytest.mark.parametrize("field,replacement", [(2, "98"), (5, "-1"), (6, "0"),
                                                   (8, "-1"), (9, "NaN")])
def test_ohlc_volume_and_close_time_fail_closed(
    tmp_path: Path, field: int, replacement: str,
) -> None:
    t = START
    row = [str(t), "100", "102", "99", "100", "1", str(t + HOUR_MS - 1),
           "100", "5", "0.5", "50", "0"]
    row[field] = replacement
    name = "BTCUSDT-1h-2021-01"
    path = tmp_path / f"{name}.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{name}.csv", ",".join(row) + "\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        load_synthetic_archive(path, "BTCUSDT", "2021-01", digest)


@pytest.mark.parametrize("times", [[START, START], [START, START + 2 * HOUR_MS],
                                   [START + 1, START + HOUR_MS + 1]])
def test_source_duplicate_gap_alignment_fail_closed(tmp_path: Path, times: list[int]) -> None:
    path, digest = _archive(tmp_path, "ETHUSDT", times)
    with pytest.raises(ValueError):
        load_synthetic_archive(path, "ETHUSDT", "2021-01", digest)


def test_synchronized_source_and_completed_view(tmp_path: Path) -> None:
    btc_path, btc_digest = _archive(tmp_path, "BTCUSDT", [START + i * HOUR_MS for i in range(75)])
    eth_path, eth_digest = _archive(tmp_path, "ETHUSDT", [START + i * HOUR_MS for i in range(75)])
    btc = load_synthetic_archive(btc_path, "BTCUSDT", "2021-01", btc_digest).bars
    eth = load_synthetic_archive(eth_path, "ETHUSDT", "2021-01", eth_digest).bars
    source = SynchronizedSource(btc, eth)
    view = source.completed_view(START + 75 * HOUR_MS, 73)
    assert view.btc[0].open_time_ms == START + 74 * HOUR_MS
    assert {f.name for f in fields(view.btc[0])} == {"open_time_ms", "high", "low", "close"}
    with pytest.raises(ValueError, match="timestamp membership"):
        SynchronizedSource(btc, (replace(eth[0], open_time_ms=START + HOUR_MS),) + eth[1:])


def test_right_boundary_and_open_endpoint_each_horizon() -> None:
    class Marks:
        def __init__(self, values: dict[int, Decimal]) -> None:
            self.values = values

        def open_at(self, symbol: str, t: int) -> Decimal:
            return self.values[t]

    end = PARTITIONS["WF1_TRAIN"][1]
    for candidate in (CANDIDATES[0], CANDIDATES[9], CANDIDATES[1]):
        h = candidate.horizon_hours
        for offset in (h + 1, h):
            t = end - offset * HOUR_MS
            batch = EventBatch(candidate.candidate_id, "WF1_TRAIN", (Event(t, 1, h),))
            mark = Marks({t: Decimal(100), t + h * HOUR_MS: Decimal(101)})
            result = materialize_outcomes(batch, mark)[0]
            assert result.primary_net == pytest.approx(.0088)
            assert result.stress_net_diagnostic == pytest.approx(.0076)
        with pytest.raises(ValueError, match="outside frozen partition"):
            EventBatch(candidate.candidate_id, "WF1_TRAIN",
                       (Event(end - (h - 1) * HOUR_MS, 1, h),))
        with pytest.raises(KeyError):
            materialize_outcomes(batch, Marks({t: Decimal(100)}))


def test_entry_open_is_distinct_from_previous_close() -> None:
    t = START + HOUR_MS
    btc = tuple(_bar('BTCUSDT', START + i * HOUR_MS,
                     '101' if i == 1 else '102' if i == 5 else '100') for i in range(6))
    eth = tuple(_bar('ETHUSDT', START + i * HOUR_MS) for i in range(6))
    source = SynchronizedSource(btc, eth)
    assert source.btc[0].close == Decimal(100)
    batch = EventBatch(CANDIDATES[0].candidate_id, 'WF1_TRAIN', (Event(t, 1, 4),))
    result = materialize_outcomes(batch, source)[0]
    assert result.primary_net == pytest.approx(102 / 101 - 1 - .0012)
    altered = SynchronizedSource((btc[0], replace(btc[1], open=Decimal(100)),
                                  *btc[2:]), eth)
    assert source.completed_view(t, 0) == altered.completed_view(t, 0)
    assert materialize_outcomes(batch, altered)[0].primary_net != result.primary_net


def test_exact_partition_lengths_and_calibration_matrix_roster() -> None:
    assert {name: (end - start) // HOUR_MS for name, (start, end) in PARTITIONS.items()} == {
        'WF1_TRAIN': 16032, 'WF1_PURGE_1': 24, 'WF1_CALIBRATION': 2184,
        'WF1_PURGE_2': 24, 'WF1_VALIDATION': 2112, 'SOURCE_RESERVE': 24,
    }
    start = PARTITIONS['WF1_CALIBRATION'][0]
    batches = tuple(EventBatch(c.candidate_id, 'WF1_CALIBRATION',
                               (Event(start, 1, c.horizon_hours),)) for c in CANDIDATES)
    results = tuple((EventOutcome(start, .01, .0088),) for _ in CANDIDATES)
    z, a = calibration_matrices(batches, results)
    assert z.shape == a.shape == (20, 2184)
    assert (z[:, 0] == .01).all() and (a[:, 0] == 1).all()
    with pytest.raises(ValueError, match='order'):
        calibration_matrices((batches[1], batches[0], *batches[2:]), results)


def test_testability_floors_and_redaction() -> None:
    candidate = CANDIDATES[0]
    start = PARTITIONS["WF1_TRAIN"][0]
    def batch(n: int, days: int) -> EventBatch:
        times = sorted(start + (i % days) * 24 * HOUR_MS + (i // days) * HOUR_MS
                       for i in range(n))
        return EventBatch(candidate.candidate_id, "WF1_TRAIN",
                          tuple(Event(t, 1, 4) for t in times))
    assert make_testability_receipt(batch(59, 30)).state == H41State.BASIC_SUPPORT_UNAVAILABLE
    assert make_testability_receipt(batch(60, 29)).state == H41State.BASIC_SUPPORT_UNAVAILABLE
    receipt = make_testability_receipt(batch(60, 30))
    assert receipt.state == H41State.TESTABLE_EXPLORATORY
    assert receipt.event_count_N == 60 and receipt.occupied_calendar_days_D == 30
    serialized = json.dumps({f.name: str(getattr(receipt, f.name)) for f in fields(receipt)})
    assert all(name not in serialized for name in ("P_entry", "P_exit", "return", "LCB", "PnL", "rank"))
    assert canonical_json({"state": receipt.state}).decode() == '{"state":"TESTABLE_EXPLORATORY"}'
