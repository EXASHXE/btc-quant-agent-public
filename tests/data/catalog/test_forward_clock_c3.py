"""Focused DATA-C3 negative and positive clock/metadata checks."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest

from scripts.data.catalog import forward_compat as fc
from scripts.data.catalog.forward_clock import ClockRecord, archive_label_window, evaluate_asof

ORIGIN = datetime(2026, 10, 18, 12, 1, tzinfo=UTC)
CUTOFF = ORIGIN - timedelta(minutes=1)


def record(kind="bar", **changes):
    start = CUTOFF - timedelta(minutes=2)
    default = {"exchange": "binance", "instrument": "BTCUSDT", "product": "USD_M_PERPETUAL",
               "stream": "bars_1m" if kind == "bar" else kind,
               "kind": kind, "event_ts_utc": start + timedelta(minutes=1),
               "source_native_ts": int((start + timedelta(minutes=1)).timestamp() * 1000),
               "source_time_unit": "ms", "source_id": "synthetic", "raw_sha256": "a" * 64,
               "interval_open": start, "interval_close": start + timedelta(minutes=1),
               "receiver_first_known_at": CUTOFF + timedelta(seconds=20),
               "local_ingested_at": CUTOFF + timedelta(seconds=30),
               "durable_committed_at": CUTOFF + timedelta(seconds=40),
               "evidence": "TEST_ONLY_SYNTHETIC", "receiver_proof": "TEST_ONLY_SYNTHETIC"}
    default.update(changes)
    return ClockRecord(**default)


def check(records, kind="bar", mode="RECEIVER_PIT_REQUIRED", **kwargs):
    origin = kwargs.pop("origin", ORIGIN)
    return evaluate_asof(records, origin=origin, exchange="binance", instrument="BTCUSDT",
                         product="USD_M_PERPETUAL", stream="bars_1m" if kind == "bar" else kind,
                         kind=kind, mode=mode, **kwargs)


def test_event_time_is_not_receiver_first_known():
    good = record()
    assert good.event_ts_utc != good.receiver_first_known_at
    assert good.availability_gate == CUTOFF + timedelta(seconds=40)
    assert check([good])["action"] == "FEATURE_READY_NOT_TRADE"
    late = dataclasses.replace(good, receiver_first_known_at=ORIGIN + timedelta(seconds=1))
    assert "AVAILABLE_AFTER_ORIGIN" in check([late])["blockers"]
    late_ingest = dataclasses.replace(good, local_ingested_at=ORIGIN + timedelta(seconds=1))
    assert "AVAILABLE_AFTER_ORIGIN" in check([late_ingest])["blockers"]


def test_archive_only_never_claims_receiver_pit():
    archive = dataclasses.replace(record(), receiver_first_known_at=None,
                                  local_ingested_at=None, durable_committed_at=None,
                                  evidence="HISTORY_ARCHIVE", receiver_proof="NONE")
    assert check([archive], mode="DESCRIPTIVE_EVENT_TIME")["action"] == "FEATURE_READY_NOT_TRADE"
    result = check([archive])
    assert result["action"] == "NO_ACTION"
    assert result["qualities"] == ["ARCHIVE_EVENT_ONLY"]
    assert "RECEIVER_FIRST_KNOWN_UNKNOWN" in result["blockers"]
    assert result["real_outcome_labels_read"] == 0
    with pytest.raises(ValueError, match="RECEIVER_PROOF_MISSING_OR_CONTRADICTORY"):
        dataclasses.replace(archive, receiver_first_known_at=CUTOFF)


def test_bar_strict_pre_cutoff_flow_closed_at_cutoff():
    at_cutoff = record(interval_open=CUTOFF - timedelta(minutes=1), interval_close=CUTOFF,
                       event_ts_utc=CUTOFF, source_native_ts=int(CUTOFF.timestamp() * 1000))
    assert check([at_cutoff])["action"] == "NO_ACTION"
    flow = dataclasses.replace(at_cutoff, kind="flow", stream="flow")
    assert check([flow], kind="flow")["action"] == "FEATURE_READY_NOT_TRADE"
    assert "INCOMPLETE_CLOSED_WINDOW" in check([flow], kind="flow", flow_minutes=5)["blockers"]


def test_oi_exact_four_hour_predecessor_and_grid():
    sample = CUTOFF - timedelta(minutes=5)
    z = record(kind="oi", event_ts_utc=sample, source_native_ts=int(sample.timestamp() * 1000),
               interval_open=None, interval_close=None)
    pred_time = sample - timedelta(hours=4)
    pred = dataclasses.replace(z, source_id="pred", event_ts_utc=pred_time,
                               source_native_ts=int(pred_time.timestamp() * 1000))
    assert "OI_4H_PREDECESSOR_MISSING" in check([z], kind="oi")["blockers"]
    assert check([z, pred], kind="oi")["action"] == "FEATURE_READY_NOT_TRADE"
    off_time = CUTOFF - timedelta(minutes=6) + timedelta(seconds=1)
    off = dataclasses.replace(z, event_ts_utc=off_time,
                              source_native_ts=int(off_time.timestamp() * 1000))
    off_pred_time = off_time - timedelta(hours=4)
    off_pred = dataclasses.replace(pred, event_ts_utc=off_pred_time,
                                   source_native_ts=int(off_pred_time.timestamp() * 1000))
    assert "OI_OFF_5M_GRID" in check([off, off_pred], kind="oi")["blockers"]


def test_previous_funding_only():
    future = record(kind="funding", event_ts_utc=CUTOFF + timedelta(hours=7),
                    source_native_ts=int((CUTOFF + timedelta(hours=7)).timestamp() * 1000),
                    interval_open=None, interval_close=None)
    assert "PREVIOUS_FUNDING_SETTLEMENT_MISSING" in check([future], kind="funding")["blockers"]
    past = dataclasses.replace(future, event_ts_utc=CUTOFF - timedelta(hours=1),
                               source_native_ts=int((CUTOFF - timedelta(hours=1)).timestamp() * 1000))
    assert check([past, future], kind="funding")["selected_source_ids"] == ["synthetic"]


def test_units_duplicates_gaps_stale_hash_and_identity():
    a = record()
    b = dataclasses.replace(a, source_id="other", source_time_unit="us",
                            source_native_ts=int(a.event_ts_utc.timestamp() * 1000000))
    assert "MIXED_NATIVE_TIMESTAMP_UNITS" in check([a, b])["blockers"]
    assert "DUPLICATE_SOURCE_CLOCK" in check([a, a])["blockers"]
    assert "SOURCE_GAP_OVERLAP" in check([dataclasses.replace(a, gap=True)])["blockers"]
    assert "SOURCE_HASH_MUTATED" in check([a], expected_sha256="b" * 64)["blockers"]
    assert "SOURCE_FAMILY_OR_INSTRUMENT_MISMATCH" in check([dataclasses.replace(a, product="SPOT")])["blockers"]
    assert "RECEIVER_WATERMARK_STALE" in check([a], max_receiver_age=timedelta(seconds=10))["blockers"]
    with pytest.raises(ValueError, match="RECORD_BUDGET_EXCEEDED"):
        check([a] * 10001)
    with pytest.raises(ValueError, match="NATIVE_CLOCK_UNIT_MISMATCH"):
        dataclasses.replace(a, source_time_unit="s")


def test_utc_day_offset_and_filename_misparse():
    start, end = archive_label_window("BTC-USDT-SWAP-trades-2024-01-15.zip", "UTC+8")
    assert start == datetime(2024, 1, 14, 16, tzinfo=UTC)
    assert end == datetime(2024, 1, 15, 16, tzinfo=UTC)
    assert archive_label_window("BTC-USDT-SWAP-L2orderbook-2024-01-15.tar.gz", "UTC")[0] == \
        datetime(2024, 1, 15, tzinfo=UTC)
    with pytest.raises(ValueError, match="ARCHIVE_FILENAME_OR_TIMEZONE_INVALID"):
        archive_label_window("BTC-USDT-SWAP-trades-2024-01-15.zip.backup", "UTC+8")
    with pytest.raises(ValueError, match="UTC_CLOCK_REQUIRED"):
        check([record()], mode="DESCRIPTIVE_EVENT_TIME", origin=datetime.fromisoformat("2026-10-18T12:01"))


def test_manifest_mismatch_and_ambiguous_close_state():
    name = "microstructure-2026-08-31.sqlite3"
    day = datetime(2026, 9, 1, tzinfo=UTC)
    row = {"path": str(fc.FORWARD_METADATA_ROOT / name), "period": "2026-08-31", "raw_sha256": None,
           "source_id": "c0", "forward_state": "PAST_DATED_CLOSED_UNVERIFIED"}
    claim = {"sha256": "a" * 64, "immutable": True,
             "eligible_at_ms": int(day.timestamp() * 1000),
             "finalized_at_ms": int((day + timedelta(hours=1)).timestamp() * 1000)}
    final = {"protocol_id": "MICROSTRUCTURE_RELIABILITY_V0316_001", "partitions": {name: claim}}
    matrix = fc.metadata_matrix([row], final, {}, [], [])
    assert matrix[0]["closed_state"] == "FINALIZATION_CLAIM_UNCORROBORATED"
    assert matrix[0]["later_read_access"] == "DEFAULT_DENY"
    assert fc.metadata_matrix([row], final, {name: "b" * 64}, [], [])[0]["closed_state"] == \
        "MANIFEST_MISMATCH_DEFAULT_DENY"
    assert fc.metadata_matrix([row], final, {name: "a" * 64}, [], [])[0]["closed_state"] == \
        "CLOSE_VERIFIED_METADATA_LINKED"


def test_bounded_manifest_rejects_symlink_and_oversize(tmp_path):
    target = tmp_path / "source.json"
    target.write_text('{"safe": true}')
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="MANIFEST_SYMLINK_FORBIDDEN"):
        fc.bounded_json(link)
    with pytest.raises(ValueError, match="MANIFEST_NOT_BOUNDED_REGULAR_JSON"):
        fc.bounded_json(target, maximum=2)


def test_actual_metadata_build_never_opens_forward_db_or_outcomes(tmp_path, monkeypatch):
    inputs = [fc.FORWARD_METADATA_ROOT / name for name in fc.MANIFEST_NAMES]
    inputs += [fc.LAKEHOUSE / "catalog.sqlite", fc.LAKEHOUSE / "c1/actual_full_coverage_matrix.json",
               ]
    before = [(p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest()) for p in inputs]
    original_connect = fc.sqlite3.connect
    calls = []

    def guarded_connect(database, *args, **kwargs):
        calls.append(str(database))
        assert "Quant-agent/data/forward" not in str(database)
        return original_connect(database, *args, **kwargs)

    monkeypatch.setattr(fc.sqlite3, "connect", guarded_connect)
    receipt = fc.build(tmp_path / "c3")
    assert calls and all("catalog.sqlite" in call for call in calls)
    assert receipt["forward_db_connections"] == 0
    assert receipt["historical_real_outcome_labels_read"] == 0
    demo = json.loads((tmp_path / "c3/demo_asof_report.json").read_text())
    assert demo["real_outcome_labels_read"] == 0
    assert demo["synthetic_forward_fixture_TEST_ONLY_SYNTHETIC"]["arrived_after_origin"]["action"] == "NO_ACTION"
    after = [(p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest()) for p in inputs]
    assert before == after
