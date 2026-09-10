"""Regression and unit tests for v0.3.24 H39 Blind Accumulation Operations & Readiness."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from btc_quant_agent.microstructure_research import (
    H39_FROZEN_CLARIFICATION_HASH,
    H39_FROZEN_PROTOCOL_HASH,
    H39_INPUT_CONTRACT_VERSION,
    H39_STATE_BLOCKED_QUALITY,
    H39_STATE_INSUFFICIENT,
    H39_VALIDATION_START_MS,
    H39_VALIDATION_START_UTC,
    REFUSED_VALIDATION_NOT_MATURE,
    H39BlindLedger,
    H39FeatureRow,
    H39Observation,
    H39OutcomeRow,
    H39ResearchEngine,
    evaluate_feature_hypotheses,
)


def _make_dummy_valid_row(
    slot_ms: int = H39_VALIDATION_START_MS,
    eligible: bool = True,
    rejection_reason: str | None = None,
    m1: float = 0.1,
    source_partition: str = "microstructure-2026-09-04.sqlite3",
    source_partition_sha: str = "dummy_partition_sha",
) -> dict[str, Any]:
    ref_time = slot_ms + 60_000
    t60 = ref_time + 59 * 60_000
    t240 = ref_time + 239 * 60_000
    return {
        "decision_close_ms": slot_ms,
        "decision_close_utc": datetime.fromtimestamp(slot_ms / 1000, UTC).isoformat(),
        "reference_time_ms": ref_time,
        "target_60m_ms": t60,
        "target_240m_ms": t240,
        "eligible": eligible,
        "rejection_reason": rejection_reason,
        "m1_trade_imbalance_5m": m1,
        "m2_trade_imbalance_15m": 0.2,
        "m3_ofi_5m": 0.3,
        "m4_top5_depth_imbalance_5m": 0.4,
        "m5_top20_depth_imbalance_5m": 0.5,
        "m6_microprice_deviation_1m": 0.6,
        "m7_pressure_agreement": 0.7,
        "m8_pressure_divergence": 0.8,
        "trailing_return_15m": 0.001,
        "trailing_return_60m": 0.002,
        "trailing_atr_ratio_15m": 0.0005,
        "trailing_atr_15m": 25.0,
        "decision_close_price": 50000.0,
        "book_sample_count_15m": 180,
        "trade_count_15m": 30,
        "input_contract_version": H39_INPUT_CONTRACT_VERSION,
        "source_partition": source_partition,
        "source_partition_sha256": source_partition_sha,
        "source_partitions": json.dumps([source_partition]),
        "source_partition_hashes": json.dumps({source_partition: source_partition_sha}),
        "code_git_sha": "dummy_code_sha",
        "protocol_hash": H39_FROZEN_PROTOCOL_HASH,
        "clarification_hash": H39_FROZEN_CLARIFICATION_HASH,
    }


def _create_test_partition(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE depth_events(event_time_ms INTEGER, final_update_id INTEGER,
          receive_time_ms INTEGER, receive_monotonic_ns INTEGER, payload_json TEXT, payload_hash TEXT,
          PRIMARY KEY(event_time_ms, final_update_id));
        CREATE TABLE agg_trades(aggregate_trade_id INTEGER PRIMARY KEY,
          event_time_ms INTEGER, transaction_time_ms INTEGER, receive_time_ms INTEGER,
          receive_monotonic_ns INTEGER, price REAL, quantity REAL, buyer_is_maker INTEGER,
          aggressive_side TEXT, payload_hash TEXT);
        CREATE TABLE gaps(id INTEGER PRIMARY KEY, start_ms INTEGER, end_ms INTEGER,
          kind TEXT, detail TEXT);
        CREATE TABLE book_samples(event_time_ms INTEGER, final_update_id INTEGER,
          receive_time_ms INTEGER, spread_bps REAL, top1_imbalance REAL, top5_imbalance REAL,
          top20_imbalance REAL, microprice REAL, ofi REAL,
          PRIMARY KEY(event_time_ms, final_update_id));
        CREATE TABLE aggregates(interval_ms INTEGER, bucket_start_ms INTEGER,
          trade_count INTEGER DEFAULT 0, buy_quantity REAL DEFAULT 0,
          sell_quantity REAL DEFAULT 0, buy_notional REAL DEFAULT 0,
          sell_notional REAL DEFAULT 0, book_sample_count INTEGER DEFAULT 0,
          spread_bps_sum REAL DEFAULT 0, top1_imbalance_sum REAL DEFAULT 0,
          top5_imbalance_sum REAL DEFAULT 0, top20_imbalance_sum REAL DEFAULT 0,
          ofi_sum REAL DEFAULT 0, gap_count INTEGER DEFAULT 0,
          PRIMARY KEY(interval_ms, bucket_start_ms));
        """
    )
    conn.commit()
    conn.close()


def _populate_test_partition(path: Path, min_t: int, max_t: int) -> None:
    _create_test_partition(path)
    conn = sqlite3.connect(path)
    t = min_t
    step = 5000
    while t <= max_t:
        conn.execute(
            "INSERT OR IGNORE INTO book_samples (event_time_ms, final_update_id, receive_time_ms, spread_bps, top1_imbalance, top5_imbalance, top20_imbalance, microprice, ofi) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (t, t, t, 1.0, 0.1, 0.1, 0.1, 60000.5, 0.5),
        )
        conn.execute(
            "INSERT OR IGNORE INTO agg_trades (aggregate_trade_id, event_time_ms, transaction_time_ms, receive_time_ms, receive_monotonic_ns, price, quantity, buyer_is_maker, aggressive_side, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (t, t, t, t, t, 60000.5, 1.0, 0, "BUY", "hash"),
        )
        t += step
    conn.commit()
    conn.close()


def test_scheduler_invocation_and_outcome_blindness(tmp_path: Path) -> None:
    """1. Scheduler invokes accumulation only; never calls formal statistics or unblinds outcomes."""
    ledger_path = tmp_path / "ledger.sqlite3"
    backup_dir = tmp_path / "backups"
    micro_dir = tmp_path / "micro"
    micro_dir.mkdir(parents=True)
    p_file = micro_dir / "microstructure-2026-09-04.sqlite3"
    _populate_test_partition(p_file, H39_VALIDATION_START_MS - 30 * 60_000, H39_VALIDATION_START_MS + 60 * 60_000)

    opp_file = tmp_path / "opp.sqlite3"
    with sqlite3.connect(opp_file) as conn:
        conn.execute("CREATE TABLE scan_observations (scheduled_slot_ms INTEGER, decision_close_ms INTEGER, atr_15m REAL, status TEXT)")
        conn.execute("INSERT INTO scan_observations VALUES (?, ?, ?, ?)", (H39_VALIDATION_START_MS, H39_VALIDATION_START_MS, 150.0, "SUCCESSFUL_SCAN"))

    engine = H39ResearchEngine(
        microstructure_root=micro_dir,
        opportunity_store_path=opp_file,
        canonical_candles_path=tmp_path / "canonical_candles.sqlite3",
    )

    sched_res = engine.run_scheduled_accumulation(
        output_ledger_path=ledger_path,
        backup_dir=backup_dir,
        only_finalized=False,
    )

    assert sched_res["status"] == "SUCCESS"
    assert Path(sched_res["backup_file"]).exists()

    with sqlite3.connect(ledger_path) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(h39_blind_validation_ledger)").fetchall()]
        for forbidden in ["target_return_60m", "target_return_240m", "direction_label", "p_value", "t_stat", "sharpe"]:
            assert forbidden not in cols


def test_accumulation_idempotency(tmp_path: Path) -> None:
    """2. Successive runs on the same partitions result in zero duplicate rows and zero drift."""
    ledger_path = tmp_path / "idemp_ledger.sqlite3"
    ledger = H39BlindLedger(ledger_path)

    row1 = _make_dummy_valid_row(slot_ms=H39_VALIDATION_START_MS)
    inserted1 = ledger.ingest_slot(row1)
    assert inserted1 is True

    inserted2 = ledger.ingest_slot(row1)
    assert inserted2 is False
    assert ledger.append_slot(row1) == "DUPLICATE_IDEMPOTENT"

    with sqlite3.connect(ledger_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM h39_blind_validation_ledger").fetchone()[0]
        assert count == 1


def test_read_only_input_firewalls(tmp_path: Path) -> None:
    """3. Forward databases are opened read-only and never modified."""
    micro_dir = tmp_path / "micro"
    micro_dir.mkdir(parents=True)
    p_file = micro_dir / "microstructure-2026-09-04.sqlite3"
    _populate_test_partition(p_file, H39_VALIDATION_START_MS - 30 * 60_000, H39_VALIDATION_START_MS + 60 * 60_000)

    h_before = hashlib.sha256(p_file.read_bytes()).hexdigest()
    engine = H39ResearchEngine(
        microstructure_root=micro_dir,
        opportunity_store_path=tmp_path / "none.sqlite3",
        canonical_candles_path=tmp_path / "canonical_candles.sqlite3",
    )
    engine.accumulate_blind_validation(output_ledger_path=tmp_path / "ledger.sqlite3", only_finalized=False)

    h_after = hashlib.sha256(p_file.read_bytes()).hexdigest()
    assert h_before == h_after


def test_finalized_historical_ingestion(tmp_path: Path) -> None:
    """4. Past true evidence from closed partitions can be ingested later without error."""
    micro_dir = tmp_path / "micro"
    micro_dir.mkdir(parents=True)
    p_file = micro_dir / "microstructure-2026-09-04.sqlite3"
    _populate_test_partition(p_file, H39_VALIDATION_START_MS - 30 * 60_000, H39_VALIDATION_START_MS + 60 * 60_000)

    engine = H39ResearchEngine(
        microstructure_root=micro_dir,
        opportunity_store_path=tmp_path / "none.sqlite3",
        canonical_candles_path=tmp_path / "canonical_candles.sqlite3",
    )
    res = engine.accumulate_blind_validation(output_ledger_path=tmp_path / "ledger.sqlite3", only_finalized=True)
    assert "microstructure-2026-09-04.sqlite3" in res["partitions_processed"]
    assert res["new_slots_ingested"] > 0


def test_missing_evidence_invariant(tmp_path: Path) -> None:
    """5. Missing raw evidence cannot be manufactured or interpolated; gaps remain documented."""
    ledger_path = tmp_path / "gap_ledger.sqlite3"
    ledger = H39BlindLedger(ledger_path)

    gap_row = _make_dummy_valid_row(
        slot_ms=H39_VALIDATION_START_MS,
        eligible=False,
        rejection_reason="GAP_IN_FEATURE_WINDOW",
        m1=0.0,
    )
    ledger.ingest_slot(gap_row)
    summary = ledger.get_summary(now_ms=H39_VALIDATION_START_MS)

    assert summary["observed_boundary_count"] == 1
    assert summary["eligible_boundary_count"] == 0
    assert summary["rejection_reason_counts"]["GAP_IN_FEATURE_WINDOW"] == 1


def test_clock_denominator_calculation(tmp_path: Path) -> None:
    """6. Coverage denominator derives strictly from validation start and elapsed time."""
    ledger_path = tmp_path / "clock_ledger.sqlite3"
    ledger = H39BlindLedger(ledger_path)

    for i in range(4):
        s = H39_VALIDATION_START_MS + i * 900_000
        ledger.ingest_slot(_make_dummy_valid_row(slot_ms=s, eligible=(i == 0)))

    # Explicit as-of cutoff produces exact deterministic expected count
    cutoff = H39_VALIDATION_START_MS + 3 * 900_000
    summary_explicit = ledger.get_summary(as_of_ms=cutoff)
    assert summary_explicit["clock_source"] == "EXPLICIT_AS_OF"
    assert summary_explicit["clock_ceiling_ms"] == cutoff
    assert summary_explicit["expected_boundary_count"] == 4
    assert summary_explicit["observed_boundary_count"] == 4
    assert summary_explicit["eligible_boundary_count"] == 1
    assert summary_explicit["coverage_ratio"] == 0.25
    assert summary_explicit["eligible_coverage"] == 0.25
    assert summary_explicit["raw_observation_coverage"] == 1.0

    # A later injected wall-clock snapshot expands the denominator independently
    # of the latest ledger slot.
    later_clock = cutoff + 10 * 900_000
    summary_wall = ledger.get_summary(now_ms=later_clock)
    assert summary_wall["clock_source"] == "EXPLICIT_AS_OF"
    assert summary_wall["expected_boundary_count"] > 4
    assert summary_wall["observed_boundary_count"] == 4
    assert summary_wall["eligible_boundary_count"] == 1
    assert summary_wall["raw_observation_coverage"] == 4 / summary_wall["expected_boundary_count"]


def test_rejected_slot_classification(tmp_path: Path) -> None:
    """7. Observed rejected slots are recorded as observed but ineligible."""
    ledger_path = tmp_path / "rej_ledger.sqlite3"
    ledger = H39BlindLedger(ledger_path)

    r1 = _make_dummy_valid_row(slot_ms=H39_VALIDATION_START_MS, eligible=True)
    r2 = _make_dummy_valid_row(slot_ms=H39_VALIDATION_START_MS + 900_000, eligible=False, rejection_reason="ZERO_TRADE_VOLUME")

    ledger.ingest_slot(r1)
    ledger.ingest_slot(r2)

    cutoff = H39_VALIDATION_START_MS + 900_000
    summary = ledger.get_summary(as_of_ms=cutoff)
    assert summary["clock_source"] == "EXPLICIT_AS_OF"
    assert summary["observed_boundary_count"] == 2
    assert summary["eligible_boundary_count"] == 1
    assert summary["raw_observation_coverage"] == 1.0
    assert summary["eligible_coverage"] == 0.5


def test_source_partition_mutation_guard(tmp_path: Path) -> None:
    """8. Altering a previously ingested source partition raises SOURCE_PARTITION_MUTATION and blocks quality."""
    p_file = tmp_path / "microstructure-2026-09-04.sqlite3"
    _populate_test_partition(p_file, H39_VALIDATION_START_MS - 30 * 60_000, H39_VALIDATION_START_MS + 60 * 60_000)

    ledger_path = tmp_path / "mut_ledger.sqlite3"
    ledger = H39BlindLedger(ledger_path)

    rec = ledger.record_or_verify_source_partition(p_file, finalized=True)
    assert rec["status"] == "RECORDED"

    with open(p_file, "ab") as f:
        f.write(b"corrupt")

    with pytest.raises(RuntimeError, match="SOURCE_PARTITION_MUTATION"):
        ledger.record_or_verify_source_partition(p_file, finalized=True)

    integ = ledger.verify_integrity()
    assert integ["status"] == "DATA_QUALITY_BREACH"
    assert len(integ["mutations_detected"]) > 0

    engine = H39ResearchEngine(
        microstructure_root=tmp_path,
        opportunity_store_path=tmp_path / "none.sqlite3",
        canonical_candles_path=tmp_path / "canonical_candles.sqlite3",
    )
    readiness = engine.check_unblind_readiness(ledger_path=ledger_path)
    assert readiness["status"] == H39_STATE_BLOCKED_QUALITY
    assert readiness["ready_for_unblind"] is False


def test_hash_pinning_and_conflict_refusal(tmp_path: Path) -> None:
    """9. Modified protocol/clarification hash or conflicting feature values fail closed with ValueError."""
    ledger_path = tmp_path / "hash_ledger.sqlite3"
    ledger = H39BlindLedger(ledger_path)

    bad_p = _make_dummy_valid_row(slot_ms=H39_VALIDATION_START_MS)
    bad_p["protocol_hash"] = "tampered_protocol_hash"
    with pytest.raises(ValueError, match="Protocol hash mismatch"):
        ledger.ingest_slot(bad_p)

    bad_c = _make_dummy_valid_row(slot_ms=H39_VALIDATION_START_MS)
    bad_c["clarification_hash"] = "tampered_clarification_hash"
    with pytest.raises(ValueError, match="Clarification hash mismatch"):
        ledger.ingest_slot(bad_c)

    good = _make_dummy_valid_row(slot_ms=H39_VALIDATION_START_MS, m1=0.1)
    ledger.ingest_slot(good)

    conflict = _make_dummy_valid_row(slot_ms=H39_VALIDATION_START_MS, m1=0.999)
    with pytest.raises(ValueError, match="Conflicting duplicate slot evidence"):
        ledger.ingest_slot(conflict)


def test_readiness_state_machine_and_metadata_isolation(tmp_path: Path) -> None:
    """10. Readiness state machine adheres to FORWARD_DATA_INSUFFICIENT, READY, BLOCKED_QUALITY; metadata only."""
    ledger_path = tmp_path / "ready_ledger.sqlite3"
    ledger = H39BlindLedger(ledger_path)
    engine = H39ResearchEngine(
        microstructure_root=tmp_path,
        opportunity_store_path=tmp_path / "none.sqlite3",
        canonical_candles_path=tmp_path / "canonical_candles.sqlite3",
    )

    r1 = engine.check_unblind_readiness(ledger_path=ledger_path)
    assert r1["status"] == H39_STATE_INSUFFICIENT
    assert r1["ready_for_unblind"] is False

    p_file = tmp_path / "microstructure-2026-09-04.sqlite3"
    _populate_test_partition(p_file, H39_VALIDATION_START_MS - 30 * 60_000, H39_VALIDATION_START_MS + 60 * 60_000)
    ledger.record_or_verify_source_partition(p_file, finalized=True)
    with open(p_file, "ab") as f:
        f.write(b"mutated")
    r2 = engine.check_unblind_readiness(ledger_path=ledger_path)
    assert r2["status"] == H39_STATE_BLOCKED_QUALITY


def test_fail_closed_formal_evaluator() -> None:
    """11. evaluate_feature_hypotheses unconditionally raises on any post-start observation."""
    feat = H39FeatureRow(
        slot_ms=H39_VALIDATION_START_MS,
        slot_utc=H39_VALIDATION_START_UTC,
        m1_trade_imbalance_5m=0.1,
        m2_trade_imbalance_15m=0.2,
        m3_ofi_5m=0.3,
        m4_top5_depth_imbalance_5m=0.4,
        m5_top20_depth_imbalance_5m=0.5,
        m6_microprice_deviation_1m=0.6,
        m7_pressure_agreement=0.7,
        m8_pressure_divergence=0.8,
        eligible=True,
        rejection_reason=None,
    )
    outcome = H39OutcomeRow(
        slot_ms=H39_VALIDATION_START_MS,
        reference_price=60001.0,
        reference_time_ms=H39_VALIDATION_START_MS + 60_000,
        future_close_60m=60010.0,
        return_60m=0.00015,
        future_close_240m=60020.0,
        return_240m=0.0003,
        trailing_return_15m=0.0001,
        trailing_return_60m=0.0002,
        trailing_atr_15m=150.0,
    )
    obs = H39Observation(feature_row=feat, outcome_row=outcome)

    with pytest.raises(RuntimeError, match=REFUSED_VALIDATION_NOT_MATURE):
        evaluate_feature_hypotheses([obs])


def test_static_code_anti_bypass_audit() -> None:
    """12. Programmatic scan of the entire codebase verifies zero occurrences of forbidden bypass terms."""
    forbidden_tokens = [
        "allow" + "_unblind",
        "force" + "_unblind",
        "--allow" + "-unblind",
        "--force" + "-unblind",
        "validation" + "-unblind",
        "validation" + "-evaluate",
        "AUTO" + "_UNBLIND",
        "H39" + "_UNBLIND_TOKEN",
    ]
    repo_root = Path(__file__).resolve().parent.parent
    scanned_count = 0

    for ext in ("*.py", "*.sh", "*.service", "*.timer"):
        for path in repo_root.glob(f"src/**/{ext}"):
            text = path.read_text(encoding="utf-8")
            for tok in forbidden_tokens:
                assert tok not in text, f"Forbidden bypass token '{tok}' found in {path}"
            scanned_count += 1

        for path in repo_root.glob(f"tools/**/{ext}"):
            text = path.read_text(encoding="utf-8")
            for tok in forbidden_tokens:
                assert tok not in text, f"Forbidden bypass token '{tok}' found in {path}"
            scanned_count += 1

        for path in repo_root.glob(f"deploy/**/{ext}"):
            text = path.read_text(encoding="utf-8")
            for tok in forbidden_tokens:
                assert tok not in text, f"Forbidden bypass token '{tok}' found in {path}"
            scanned_count += 1

    assert scanned_count > 0, "Static anti-bypass scan found no executable files"


def test_durability_and_online_backup(tmp_path: Path) -> None:
    """13. PRAGMA integrity_check passes and SQLite online backup produces a valid, readable replica."""
    ledger_path = tmp_path / "backup_src.sqlite3"
    ledger = H39BlindLedger(ledger_path)

    for i in range(5):
        ledger.ingest_slot(_make_dummy_valid_row(slot_ms=H39_VALIDATION_START_MS + i * 900_000))

    bak_dir = tmp_path / "backups"
    bak_path = ledger.backup_ledger(bak_dir)
    assert bak_path.exists()

    with sqlite3.connect(bak_path) as conn:
        res = conn.execute("PRAGMA integrity_check").fetchone()[0]
        assert res.lower() == "ok"
        cnt = conn.execute("SELECT COUNT(*) FROM h39_blind_validation_ledger").fetchone()[0]
        assert cnt == 5

    manifests = list(bak_dir.glob("*_manifest.json"))
    assert len(manifests) == 1
    m_data = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert m_data["total_slots"] == 5
    assert m_data["integrity_check"] == "OK"


def test_operational_safety_firewalls_and_disk_check(tmp_path: Path) -> None:
    """14. Low disk space triggers refusal without deletion; H38 terminal; execution disabled."""
    engine = H39ResearchEngine(
        microstructure_root=tmp_path,
        opportunity_store_path=tmp_path / "none.sqlite3",
        canonical_candles_path=tmp_path / "canonical_candles.sqlite3",
    )

    safe, _free = engine.check_disk_safety(min_free_gb=1e9)
    assert safe is False
    with pytest.raises(RuntimeError, match="REFUSED_INSUFFICIENT_DISK_SPACE"):
        engine.run_scheduled_accumulation(
            output_ledger_path=tmp_path / "l.sqlite3",
            backup_dir=tmp_path / "b",
            min_free_gb=1e9,
        )

    status = engine.get_blind_validation_status(
        ledger_path=tmp_path / "missing_safety_ledger.sqlite3",
        now_ms=H39_VALIDATION_START_MS,
    )
    firewalls = status["safety_firewalls"]
    assert firewalls["strategy"] == "EXPERIMENTAL"
    assert firewalls["qualified_direction_engine"] == "NONE"
    assert firewalls["runtime_maximum"] == "OPPORTUNITY_ONLY"
    assert firewalls["execution"] == "DISABLED"
    assert firewalls["auto_execute"] is False
    assert firewalls["final_holdout"] == "SEALED"


def test_stale_ledger_fail_closed_regression(tmp_path: Path) -> None:
    """15. Stale ledger regression: halting ingestion while wall clock advances causes coverage to fall and readiness to fail closed."""
    ledger_path = tmp_path / "stale_ledger.sqlite3"
    ledger = H39BlindLedger(ledger_path)

    # Ingest 15 distinct days of eligible slots through T1 (1440 slots)
    # T0 = validation start (2026-09-04T11:15:00Z)
    t0 = H39_VALIDATION_START_MS
    num_slots = 1440
    for i in range(num_slots):
        s = t0 + i * 900_000
        ledger.ingest_slot(_make_dummy_valid_row(slot_ms=s, eligible=True))

    t1 = t0 + (num_slots - 1) * 900_000

    # If evaluated strictly through T1, all gates would pass (100% coverage, 1440 observations, >=14 days)
    summary_t1 = ledger.get_summary(as_of_ms=t1)
    assert summary_t1["clock_source"] == "EXPLICIT_AS_OF"
    assert summary_t1["expected_boundary_count"] == num_slots
    assert summary_t1["observed_boundary_count"] == num_slots
    assert summary_t1["eligible_boundary_count"] == num_slots
    assert summary_t1["coverage_ratio"] == 1.0
    assert summary_t1["days_gate_passed"] is True
    assert summary_t1["observations_gate_passed"] is True
    assert summary_t1["coverage_gate_passed"] is True
    assert summary_t1["maturity_achieved"] is True

    # Now evaluate under simulated future wall clock T2 = T1 + 20 days (materially later, ingestion halted at T1)
    t2 = t1 + 20 * 86_400_000
    summary_t2 = ledger.get_summary(now_ms=t2)
    assert summary_t2["clock_source"] == "EXPLICIT_AS_OF"
    expected_t2 = ((t2 - t0) // 900_000) + 1
    assert summary_t2["expected_boundary_count"] == expected_t2
    assert expected_t2 > num_slots + 1800
    assert summary_t2["observed_boundary_count"] == num_slots
    assert summary_t2["eligible_boundary_count"] == num_slots
    # Coverage has fallen drastically because the 20 days of missing boundaries remain in denominator!
    assert summary_t2["eligible_coverage"] < 0.50
    assert summary_t2["coverage_gate_passed"] is False
    assert summary_t2["maturity_achieved"] is False
    assert summary_t2["state"] == H39_STATE_INSUFFICIENT

    # Verify check_unblind_readiness fails closed under T2
    engine = H39ResearchEngine(
        microstructure_root=tmp_path,
        opportunity_store_path=tmp_path / "none.sqlite3",
        canonical_candles_path=tmp_path / "canonical_candles.sqlite3",
    )
    readiness_t2 = engine.check_unblind_readiness(ledger_path=ledger_path, now_ms=t2)
    assert readiness_t2["ready_for_unblind"] is False
    assert readiness_t2["status"] == H39_STATE_INSUFFICIENT
    assert "Minimum gates not met" in str(readiness_t2.get("refusal_reason"))


def test_empty_and_missing_ledger_explicit_clock_denominator(tmp_path: Path) -> None:
    """16. Empty and missing ledgers use the injected deterministic clock ceiling."""
    empty_ledger_path = tmp_path / "empty.sqlite3"
    ledger = H39BlindLedger(empty_ledger_path)
    clock_ms = H39_VALIDATION_START_MS + 9 * 900_000

    summary_empty = ledger.get_summary(now_ms=clock_ms)
    assert summary_empty["clock_source"] == "EXPLICIT_AS_OF"
    assert summary_empty["expected_boundary_count"] == 10
    assert summary_empty["observed_boundary_count"] == 0
    assert summary_empty["eligible_boundary_count"] == 0
    assert summary_empty["raw_observation_coverage"] == 0.0
    assert summary_empty["eligible_coverage"] == 0.0

    # Non-existent ledger via engine also accumulates expected boundaries
    missing_path = tmp_path / "does_not_exist.sqlite3"
    engine = H39ResearchEngine(
        microstructure_root=tmp_path,
        opportunity_store_path=tmp_path / "none.sqlite3",
        canonical_candles_path=tmp_path / "canonical_candles.sqlite3",
    )
    status_missing = engine.get_blind_validation_status(
        ledger_path=missing_path, now_ms=clock_ms
    )
    assert status_missing["clock_source"] == "EXPLICIT_AS_OF"
    assert status_missing["expected_boundary_count"] == 10
    assert status_missing["observed_boundary_count"] == 0
    assert status_missing["state"] == H39_STATE_INSUFFICIENT
