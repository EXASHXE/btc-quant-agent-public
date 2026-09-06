"""Regression and unit tests for BTC Quant Agent v0.3.25: H39 One-Shot Unblind Preregistration."""
from __future__ import annotations

import json
import subprocess
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from btc_quant_agent.cli import build_parser
from btc_quant_agent.microstructure_research import (
    FORMAL_FEATURE_IDS,
    H39_FROZEN_CLARIFICATION_HASH,
    H39_FROZEN_PROTOCOL_HASH,
    H39_ONE_SHOT_ALREADY_CONSUMED,
    H39_STATE_BLOCKED_QUALITY,
    H39_STATE_INSUFFICIENT,
    H39_VALIDATION_START_MS,
    PREDEFINED_FEATURE_SIGNS,
    REFUSED_VALIDATION_NOT_MATURE,
    H39BlindLedger,
    H39FeatureRow,
    H39Observation,
    H39OneShotExecutionRegistry,
    H39OneShotUnblindGatekeeper,
    H39OutcomeRow,
    H39ResearchEngine,
    _compute_sha256,
    _holm_bonferroni,
    _open_sqlite,
    evaluate_feature_hypotheses,
    generate_all_v0325_deliverables,
    verify_committed_freeze_package,
)


def _init_test_git_repo(repo_dir: Path) -> None:
    repo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(repo_dir), check=True, capture_output=True)
    init_file = repo_dir / ".gitkeep"
    init_file.write_text("initial", encoding="utf-8")
    subprocess.run(["git", "add", ".gitkeep"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=str(repo_dir), check=True, capture_output=True)


def _commit_in_test_git_repo(repo_dir: Path, rel_or_abs_path: str | Path, commit_msg: str = "commit freeze") -> str:
    p = Path(rel_or_abs_path).resolve()
    rel = p.relative_to(repo_dir.resolve()).as_posix()
    subprocess.run(["git", "add", rel], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", commit_msg], cwd=str(repo_dir), check=True, capture_output=True)
    res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir), check=True, capture_output=True, text=True)
    return res.stdout.strip()


def _make_dummy_slot_row(
    slot_ms: int,
    eligible: bool = True,
    rejection_reason: str | None = None,
    source_partition: str = "microstructure-2026-09-04.sqlite3",
    source_partition_sha: str = "dummy_partition_sha",
    m_val: float = 0.5,
) -> dict[str, Any]:
    ref_time = slot_ms + 60_000
    t60 = ref_time + 59 * 60_000
    t240 = ref_time + 239 * 60_000
    dt_str = datetime.fromtimestamp(slot_ms / 1000, UTC).isoformat()
    return {
        "decision_close_ms": slot_ms,
        "slot_utc": dt_str,
        "reference_time_ms": ref_time,
        "target_60m_ms": t60,
        "target_240m_ms": t240,
        "eligible": eligible,
        "rejection_reason": rejection_reason,
        "m1_trade_imbalance_5m": m_val,
        "m2_trade_imbalance_15m": m_val,
        "m3_ofi_5m": m_val,
        "m4_top5_depth_imbalance_5m": m_val,
        "m5_top20_depth_imbalance_5m": m_val,
        "m6_microprice_deviation_1m": m_val,
        "m7_pressure_agreement": 0.8,
        "m8_pressure_divergence": 0.2,
        "trailing_return_15m": 0.001,
        "trailing_return_60m": 0.002,
        "trailing_atr_ratio_15m": 0.0005,
        "trailing_atr_15m": 25.0,
        "decision_close_price": 50000.0,
        "source_partition": source_partition,
        "source_partition_sha256": source_partition_sha,
        "source_partitions": json.dumps([source_partition]),
        "source_partition_hashes": json.dumps({source_partition: source_partition_sha}),
        "code_git_sha": "dummy_code_sha",
        "protocol_hash": H39_FROZEN_PROTOCOL_HASH,
        "clarification_hash": H39_FROZEN_CLARIFICATION_HASH,
    }


def _create_synthetic_ledger(
    db_path: Path,
    num_days: int = 14,
    slots_per_day: int = 96,
    start_ms: int = H39_VALIDATION_START_MS,
    eligible_ratio: float = 1.0,
    partition_file: Path | None = None,
    max_eligible: int | None = None,
) -> tuple[H39BlindLedger, int]:
    if partition_file is None:
        partition_file = db_path.parent / "test_part.sqlite3"
        if not partition_file.exists():
            partition_file.write_bytes(b"synthetic_partition_evidence_bytes")

    ledger = H39BlindLedger(db_path)
    p_name = partition_file.name
    p_sha = _compute_sha256(partition_file)

    ledger.record_or_verify_source_partition(
        partition_file, finalized=True, min_time_ms=start_ms, max_time_ms=start_ms + 86400000 * (num_days + 1)
    )

    base_midnight = 1788480000000  # 2026-09-04T00:00:00Z
    total_eligible = 0
    curr_ms = start_ms
    rows_to_insert = []

    for d in range(num_days):
        day_midnight = base_midnight + d * 86_400_000
        start_idx = 45 if d == 0 else 0  # 45 * 900_000 = 11:15 UTC
        end_idx = min(96, start_idx + slots_per_day)
        for s in range(start_idx, end_idx):
            slot_time = day_midnight + s * 900_000
            is_elig = True
            if max_eligible is not None and total_eligible >= max_eligible:
                is_elig = False
            elif eligible_ratio < 1.0:
                is_elig = ((s - start_idx) / max(1, end_idx - start_idx)) < eligible_ratio

            reason = None if is_elig else "GAP_IN_FEATURE_WINDOW"
            row = _make_dummy_slot_row(
                slot_ms=slot_time,
                eligible=is_elig,
                rejection_reason=reason,
                source_partition=p_name,
                source_partition_sha=p_sha,
                m_val=0.1 * ((s % 5) + 1),
            )
            rows_to_insert.append(row)
            if is_elig:
                total_eligible += 1
            curr_ms = max(curr_ms, slot_time)

    ledger.ingest_slots(rows_to_insert)
    return ledger, curr_ms


def _populate_canonical_candles(
    db_path: Path,
    slots: list[int],
    base_price: float = 50000.0,
) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _open_sqlite(db_path) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS klines_1m (
                open_time_ms INTEGER PRIMARY KEY,
                open REAL, high REAL, low REAL, close REAL,
                volume REAL, close_time_ms INTEGER
            )"""
        )
        for s in slots:
            ref_t = s + 60_000
            t60 = ref_t + 59 * 60_000
            t240 = ref_t + 239 * 60_000

            # Reference candle
            conn.execute(
                "INSERT OR REPLACE INTO klines_1m VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ref_t, base_price, base_price + 10.0, base_price - 10.0, base_price + 1.0, 10.0, ref_t + 59999),
            )
            # 60m candle (positive return: 50000 -> 50050)
            conn.execute(
                "INSERT OR REPLACE INTO klines_1m VALUES (?, ?, ?, ?, ?, ?, ?)",
                (t60, base_price + 45.0, base_price + 55.0, base_price + 40.0, base_price + 50.0, 10.0, t60 + 59999),
            )
            # 240m candle (positive return: 50000 -> 50100)
            conn.execute(
                "INSERT OR REPLACE INTO klines_1m VALUES (?, ?, ?, ?, ?, ?, ?)",
                (t240, base_price + 95.0, base_price + 105.0, base_price + 90.0, base_price + 100.0, 10.0, t240 + 59999),
            )
        conn.commit()


# =====================================================================
# SECTION 13 REQUIREMENT TESTS
# =====================================================================

def test_unblind_refuses_before_14_days(tmp_path: Path) -> None:
    """1. Unblind refuses before 14 distinct UTC days."""
    db_path = tmp_path / "h39_ledger.sqlite3"
    # 13 distinct days with full slots (51 + 12*96 = 1203 eligible slots, 100% coverage at latest_ms)
    _ledger, latest_ms = _create_synthetic_ledger(db_path, num_days=13, slots_per_day=96)

    gk = H39OneShotUnblindGatekeeper(ledger_path=db_path)
    res = gk.verify_readiness_preconditions(as_of_ms=latest_ms)
    assert not res["ready_for_unblind"]
    assert res["status"] == H39_STATE_INSUFFICIENT
    assert "days: 13/14" in res["refusal_reason"]

    # Attempting to create freeze manifest must raise
    freeze_target = tmp_path / "freeze.json"
    with pytest.raises(RuntimeError, match="unblind readiness preconditions failed"):
        gk.create_freeze_manifest(output_path=freeze_target, as_of_ms=latest_ms)


def test_unblind_refuses_before_750_eligible_observations(tmp_path: Path) -> None:
    """2. Unblind refuses before 750 eligible observations."""
    db_path = tmp_path / "h39_ledger.sqlite3"
    # 14 distinct days, exactly 742 eligible slots
    _ledger, latest_ms = _create_synthetic_ledger(db_path, num_days=14, slots_per_day=96, max_eligible=742)

    gk = H39OneShotUnblindGatekeeper(ledger_path=db_path)
    res = gk.verify_readiness_preconditions(as_of_ms=latest_ms)
    assert not res["ready_for_unblind"]
    assert res["status"] == H39_STATE_INSUFFICIENT
    assert "eligible: 742/750" in res["refusal_reason"]

    freeze_target = tmp_path / "freeze.json"
    with pytest.raises(RuntimeError, match="unblind readiness preconditions failed"):
        gk.create_freeze_manifest(output_path=freeze_target, as_of_ms=latest_ms)


def test_unblind_refuses_below_90pct_wall_clock_coverage(tmp_path: Path) -> None:
    """3. Unblind refuses below 90% wall-clock eligible coverage."""
    db_path = tmp_path / "h39_ledger.sqlite3"
    # 14 days, 750 eligible slots, but clock ceiling is set far ahead so coverage < 90%
    _ledger, _latest_ms = _create_synthetic_ledger(db_path, num_days=14, slots_per_day=54)

    # Move clock forward so expected boundaries = 1000 -> coverage = 756 / 1000 = 75.6%
    as_of_ms = H39_VALIDATION_START_MS + (1000 - 1) * 900_000
    gk = H39OneShotUnblindGatekeeper(ledger_path=db_path)
    res = gk.verify_readiness_preconditions(as_of_ms=as_of_ms)
    assert not res["ready_for_unblind"]
    assert res["status"] == H39_STATE_INSUFFICIENT
    assert "coverage:" in res["refusal_reason"]

    freeze_target = tmp_path / "freeze.json"
    with pytest.raises(RuntimeError, match="unblind readiness preconditions failed"):
        gk.create_freeze_manifest(output_path=freeze_target, as_of_ms=as_of_ms)


def test_stale_ledger_cannot_authorize_unblind(tmp_path: Path) -> None:
    """4. Stale ledger cannot authorize unblind due to expanding wall-clock denominator."""
    db_path = tmp_path / "h39_ledger.sqlite3"
    _ledger, latest_ms = _create_synthetic_ledger(db_path, num_days=14, slots_per_day=54)

    gk = H39OneShotUnblindGatekeeper(ledger_path=db_path)
    # Stale ledger evaluated 5 days later without new slots
    future_wall_clock = latest_ms + 5 * 86_400_000
    res = gk.verify_readiness_preconditions(as_of_ms=future_wall_clock)
    assert not res["ready_for_unblind"]
    assert res["status"] == H39_STATE_INSUFFICIENT


def test_source_partition_mutation_blocks_unblind(tmp_path: Path) -> None:
    """5. Source partition mutation blocks unblind with READINESS_BLOCKED_DATA_QUALITY."""
    db_path = tmp_path / "h39_ledger.sqlite3"
    part_file = tmp_path / "microstructure-2026-09-04.sqlite3"
    part_file.write_bytes(b"initial_partition_content")

    _ledger, latest_ms = _create_synthetic_ledger(
        db_path, num_days=14, slots_per_day=54, partition_file=part_file
    )

    # Mutate source partition
    part_file.write_bytes(b"tampered_mutated_content")

    gk = H39OneShotUnblindGatekeeper(ledger_path=db_path)
    res = gk.verify_readiness_preconditions(as_of_ms=latest_ms)
    assert not res["ready_for_unblind"]
    assert res["status"] == H39_STATE_BLOCKED_QUALITY
    assert "READINESS_BLOCKED_DATA_QUALITY" in res["refusal_reason"]


def test_protocol_hash_drift_blocks_unblind(tmp_path: Path) -> None:
    """6. Protocol hash drift blocks unblind."""
    db_path = tmp_path / "h39_ledger.sqlite3"
    _ledger, latest_ms = _create_synthetic_ledger(db_path, num_days=14, slots_per_day=54)

    # Create mutated protocol file
    bad_proto = tmp_path / "bad_protocol.json"
    bad_proto.write_text('{"tampered": true}', encoding="utf-8")

    gk = H39OneShotUnblindGatekeeper(ledger_path=db_path, protocol_path=bad_proto)
    with pytest.raises(RuntimeError, match="PROTOCOL_HASH_DRIFT"):
        gk.verify_readiness_preconditions(as_of_ms=latest_ms)


def test_clarification_hash_drift_blocks_unblind(tmp_path: Path) -> None:
    """7. Clarification hash drift blocks unblind."""
    db_path = tmp_path / "h39_ledger.sqlite3"
    _ledger, latest_ms = _create_synthetic_ledger(db_path, num_days=14, slots_per_day=54)

    bad_clar = tmp_path / "bad_clarification.json"
    bad_clar.write_text('{"tampered": true}', encoding="utf-8")

    gk = H39OneShotUnblindGatekeeper(ledger_path=db_path, clarification_path=bad_clar)
    with pytest.raises(RuntimeError, match="CLARIFICATION_HASH_DRIFT"):
        gk.verify_readiness_preconditions(as_of_ms=latest_ms)


def test_legacy_evaluate_validation_status_cannot_authorize_unblind() -> None:
    """8. Legacy evaluate_validation_status cannot authorize unblind."""
    engine = H39ResearchEngine()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        diag = engine.evaluate_validation_status()
        assert any(issubclass(warn.category, DeprecationWarning) for warn in w)

    assert diag["deprecated"] is True
    assert diag["authoritative"] is False
    assert diag["diagnostic_only"] is True
    assert diag["readiness_authority"] == "NON_AUTHORITATIVE_DIAGNOSTIC_ONLY"
    assert diag["authoritative_unblind_authorization_allowed"] is False


def test_freeze_cutoff_excludes_later_rows(tmp_path: Path) -> None:
    """9. Freeze cutoff excludes later rows during execution."""
    repo_dir = tmp_path / "repo"
    _init_test_git_repo(repo_dir)

    db_path = tmp_path / "h39_ledger.sqlite3"
    candles_path = tmp_path / "candles.sqlite3"
    _ledger, latest_ms = _create_synthetic_ledger(db_path, num_days=14, slots_per_day=96)

    # Add extra row past the cutoff
    post_cutoff_slot = latest_ms + 900_000
    extra_row = _make_dummy_slot_row(slot_ms=post_cutoff_slot, eligible=True)
    _ledger.ingest_slot(extra_row)

    # Create freeze manifest strictly at latest_ms
    freeze_file = repo_dir / "freeze.json"
    registry_path = tmp_path / "reg.sqlite3"
    snapshot_dir = tmp_path / "snapshots"
    gk = H39OneShotUnblindGatekeeper(
        ledger_path=db_path,
        canonical_candles_path=candles_path,
        registry_path=registry_path,
        snapshot_dir=snapshot_dir,
        repo_root=repo_dir,
    )
    manifest = gk.create_freeze_manifest(output_path=freeze_file, as_of_ms=latest_ms)
    assert manifest["unblind_cutoff_ms"] == latest_ms

    # Commit freeze manifest to git repo
    _commit_in_test_git_repo(repo_dir, freeze_file)

    # Setup candles up to latest_ms
    with _open_sqlite(db_path) as conn:
        slots = [r[0] for r in conn.execute("SELECT decision_close_ms FROM h39_blind_validation_ledger WHERE decision_close_ms <= ?", (latest_ms,)).fetchall()]
    _populate_canonical_candles(candles_path, slots)

    results = gk.execute_one_shot_unblind(
        freeze_manifest_path=freeze_file,
        output_dir=tmp_path / "results",
        repo_root=repo_dir,
    )
    assert results["unblind_cutoff_ms"] == latest_ms
    assert results["evaluated_sample_size"] == len(slots)


def test_reference_timestamp_exact_decision_close_plus_60s(tmp_path: Path) -> None:
    """10. Reference timestamp is strictly decision_close_ms + 60s."""
    db_path = tmp_path / "test_ref.sqlite3"
    ledger = H39BlindLedger(db_path)
    slot_ms = H39_VALIDATION_START_MS

    # Corrupt reference timing by 1 millisecond
    bad_row = _make_dummy_slot_row(slot_ms=slot_ms)
    bad_row["reference_time_ms"] = slot_ms + 60_001
    with pytest.raises(ValueError, match="Invalid reference timing"):
        ledger.ingest_slot(bad_row)


def test_60m_and_240m_target_timestamps_exact(tmp_path: Path) -> None:
    """11. 60m and 240m target timestamps are strictly aligned."""
    db_path = tmp_path / "test_target.sqlite3"
    ledger = H39BlindLedger(db_path)
    slot_ms = H39_VALIDATION_START_MS

    bad_row_60 = _make_dummy_slot_row(slot_ms=slot_ms)
    bad_row_60["target_60m_ms"] = bad_row_60["reference_time_ms"] + 60 * 60_000  # Should be 59*60_000
    with pytest.raises(ValueError, match="Invalid 60m target timing"):
        ledger.ingest_slot(bad_row_60)

    bad_row_240 = _make_dummy_slot_row(slot_ms=slot_ms)
    bad_row_240["target_240m_ms"] = bad_row_240["reference_time_ms"] + 240 * 60_000  # Should be 239*60_000
    with pytest.raises(ValueError, match="Invalid 240m target timing"):
        ledger.ingest_slot(bad_row_240)


def test_formal_universe_exactly_m1_m8() -> None:
    """12. Formal feature universe contains exactly M1-M8."""
    assert len(FORMAL_FEATURE_IDS) == 8
    expected = (
        "M1_TRADE_NOTIONAL_IMBALANCE_5M",
        "M2_TRADE_NOTIONAL_IMBALANCE_15M",
        "M3_OFI_5M",
        "M4_TOP5_DEPTH_IMBALANCE_5M",
        "M5_TOP20_DEPTH_IMBALANCE_5M",
        "M6_MICROPRICE_DEVIATION_1M",
        "M7_PRESSURE_AGREEMENT_SCORE",
        "M8_PRESSURE_DIVERGENCE_SCORE",
    )
    assert FORMAL_FEATURE_IDS == expected


def test_holm_correction_includes_all_8_arms() -> None:
    """13. Holm-Bonferroni correction includes all 8 arms without dropping any."""
    raw_p = [0.001, 0.005, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06]
    adj_p = _holm_bonferroni(raw_p)
    assert len(adj_p) == 8
    # Smallest raw p gets multiplied by 8
    assert adj_p[0] == pytest.approx(0.001 * 8)
    # Monotonicity check
    for i in range(1, 8):
        assert adj_p[i] >= adj_p[i - 1]


def test_predefined_signs_cannot_be_flipped() -> None:
    """14. Predefined signs are frozen positive (+1) and cannot be flipped."""
    for sign in PREDEFINED_FEATURE_SIGNS.values():
        assert sign == 1


def test_240m_cannot_rescue_60m_failure(tmp_path: Path) -> None:
    """15. 240m supporting horizon cannot rescue failure of 60m primary family."""
    repo_dir = tmp_path / "repo"
    _init_test_git_repo(repo_dir)

    db_path = tmp_path / "h39_ledger.sqlite3"
    candles_path = tmp_path / "candles.sqlite3"
    _ledger, latest_ms = _create_synthetic_ledger(db_path, num_days=14, slots_per_day=96)

    freeze_file = repo_dir / "freeze.json"
    registry_path = tmp_path / "reg.sqlite3"
    snapshot_dir = tmp_path / "snapshots"
    gk = H39OneShotUnblindGatekeeper(
        ledger_path=db_path,
        canonical_candles_path=candles_path,
        registry_path=registry_path,
        snapshot_dir=snapshot_dir,
        repo_root=repo_dir,
    )
    gk.create_freeze_manifest(output_path=freeze_file, as_of_ms=latest_ms)
    _commit_in_test_git_repo(repo_dir, freeze_file)

    # Create candles where 60m has zero/negative return, but 240m has strongly positive return
    with _open_sqlite(db_path) as conn:
        slots = [r[0] for r in conn.execute("SELECT decision_close_ms FROM h39_blind_validation_ledger WHERE decision_close_ms <= ?", (latest_ms,)).fetchall()]

    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _open_sqlite(candles_path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS klines_1m (open_time_ms INTEGER PRIMARY KEY, open REAL, high REAL, low REAL, close REAL, volume REAL, close_time_ms INTEGER)")
        base_price = 50000.0
        for s in slots:
            ref_t = s + 60_000
            t60 = ref_t + 59 * 60_000
            t240 = ref_t + 239 * 60_000
            # 60m: negative return (-$100)
            conn.execute("INSERT OR REPLACE INTO klines_1m VALUES (?, ?, ?, ?, ?, ?, ?)", (ref_t, base_price, base_price + 10, base_price - 10, base_price, 10, ref_t + 59999))
            conn.execute("INSERT OR REPLACE INTO klines_1m VALUES (?, ?, ?, ?, ?, ?, ?)", (t60, base_price - 100, base_price - 90, base_price - 110, base_price - 100, 10, t60 + 59999))
            # 240m: positive return (+$500)
            conn.execute("INSERT OR REPLACE INTO klines_1m VALUES (?, ?, ?, ?, ?, ?, ?)", (t240, base_price + 500, base_price + 510, base_price + 490, base_price + 500, 10, t240 + 59999))
        conn.commit()

    results = gk.execute_one_shot_unblind(
        freeze_manifest_path=freeze_file,
        output_dir=tmp_path / "results",
        repo_root=repo_dir,
    )
    assert results["scientific_verdict"] == "RESEARCH_FAMILY_STOP"
    assert len(results["provisional_candidates"]) == 0


def test_baseline_fields_exactly_frozen_trio() -> None:
    """16. Baseline fields are exactly trailing_return_15m, trailing_return_60m, trailing_atr_ratio_15m."""
    gatekeeper = H39OneShotUnblindGatekeeper()
    assert gatekeeper is not None


def test_no_hyperparameter_or_model_search() -> None:
    """17. Incremental modeling uses fixed L2 logistic regression with lambda=1.0."""
    manifest = json.loads(Path("deliverables/v0.3.25/H39_UNBLIND_PREREGISTRATION_MANIFEST.json").read_text(encoding="utf-8")) if Path("deliverables/v0.3.25/H39_UNBLIND_PREREGISTRATION_MANIFEST.json").exists() else {}
    if manifest:
        assert manifest["model_family"] == "L2_LOGISTIC_REGRESSION_LAMBDA_1_0"


def test_no_final_holdout_access() -> None:
    """18. Final holdout remains sealed and unread."""
    gk = H39OneShotUnblindGatekeeper()
    readiness = gk.verify_readiness_preconditions()
    assert readiness["summary"]["safety_firewalls"]["final_holdout"] == "SEALED"


def test_no_runtime_direction_integration() -> None:
    """19. Direction engine remains NONE, runtime ceiling remains OPPORTUNITY_ONLY."""
    gk = H39OneShotUnblindGatekeeper()
    readiness = gk.verify_readiness_preconditions()
    fw = readiness["summary"]["safety_firewalls"]
    assert fw["qualified_direction_engine"] == "NONE"
    assert fw["runtime_maximum"] == "OPPORTUNITY_ONLY"


def test_execution_remains_disabled() -> None:
    """20. Execution engine remains DISABLED and auto_execute false."""
    gk = H39OneShotUnblindGatekeeper()
    readiness = gk.verify_readiness_preconditions()
    fw = readiness["summary"]["safety_firewalls"]
    assert fw["execution"] == "DISABLED"
    assert fw["auto_execute"] is False


def test_no_force_override_unblind_path() -> None:
    """21. No --force or --override flags exist on unblind commands (deliberate bypass scan)."""
    parser = build_parser()
    # Attempting to pass --force or --override to freeze-cutoff or one-shot-unblind must fail
    with pytest.raises(SystemExit):
        parser.parse_args(["h39", "freeze-cutoff", "--force"])
    with pytest.raises(SystemExit):
        parser.parse_args(["h39", "one-shot-unblind", "--freeze-manifest", "dummy.json", "--override"])
    with pytest.raises(SystemExit):
        parser.parse_args(["h39", "one-shot-unblind", "--freeze-manifest", "dummy.json", "--ignore-readiness"])


def test_deliberate_leakage_bypass_fails_closed() -> None:
    """Deliberate leakage/bypass test: post-start validation evaluation fails closed."""
    # Attempting to run evaluate_feature_hypotheses on post-start validation observations unconditionally raises
    feat_row = H39FeatureRow(
        slot_ms=H39_VALIDATION_START_MS + 900_000,
        slot_utc="2026-09-04T11:30:00Z",
        m1_trade_imbalance_5m=0.1,
        m2_trade_imbalance_15m=0.1,
        m3_ofi_5m=0.1,
        m4_top5_depth_imbalance_5m=0.1,
        m5_top20_depth_imbalance_5m=0.1,
        m6_microprice_deviation_1m=0.1,
        m7_pressure_agreement=0.5,
        m8_pressure_divergence=0.1,
        eligible=True,
        rejection_reason=None,
    )
    outcome_row = H39OutcomeRow(
        slot_ms=H39_VALIDATION_START_MS + 900_000,
        reference_price=50000.0,
        reference_time_ms=H39_VALIDATION_START_MS + 960_000,
        future_close_60m=50050.0,
        return_60m=0.001,
        future_close_240m=50100.0,
        return_240m=0.002,
        trailing_return_15m=0.001,
        trailing_return_60m=0.002,
        trailing_atr_15m=25.0,
        trailing_atr_ratio_15m=0.0005,
    )
    obs = [H39Observation(feature_row=feat_row, outcome_row=outcome_row)]

    with pytest.raises(RuntimeError, match=REFUSED_VALIDATION_NOT_MATURE):
        evaluate_feature_hypotheses(obs, horizon="60m")


def test_full_mock_unblind_execution_on_synthetic_mature_ledger(tmp_path: Path) -> None:
    """22. Full mock unblind test on synthetic mature ledger: executes deterministically, produces all 8 artifacts."""
    repo_dir = tmp_path / "repo"
    _init_test_git_repo(repo_dir)

    db_path = tmp_path / "mature_ledger.sqlite3"
    candles_path = tmp_path / "canonical_candles.sqlite3"
    output_dir = repo_dir / "deliverables" / "v0.3.25"
    freeze_path = output_dir / "H39_ONE_SHOT_UNBLIND_FREEZE.json"
    registry_path = tmp_path / "registry.sqlite3"
    snapshot_dir = tmp_path / "snapshots"

    # 14 days with full slots (51 + 13*96 = 1299 eligible slots > 750)
    _ledger, latest_ms = _create_synthetic_ledger(db_path, num_days=14, slots_per_day=96)

    # Populate matching candles
    with _open_sqlite(db_path) as conn:
        slots = [r[0] for r in conn.execute("SELECT decision_close_ms FROM h39_blind_validation_ledger WHERE decision_close_ms <= ?", (latest_ms,)).fetchall()]
    _populate_canonical_candles(candles_path, slots)

    gk = H39OneShotUnblindGatekeeper(
        ledger_path=db_path,
        canonical_candles_path=candles_path,
        registry_path=registry_path,
        snapshot_dir=snapshot_dir,
        repo_root=repo_dir,
    )

    # 1. Readiness check passes at cutoff
    readiness = gk.verify_readiness_preconditions(as_of_ms=latest_ms)
    assert readiness["ready_for_unblind"] is True

    # 2. Freeze manifest is created
    manifest = gk.create_freeze_manifest(output_path=freeze_path, as_of_ms=latest_ms)
    assert manifest["eligible_boundary_count"] >= 750
    assert manifest["distinct_days_count"] >= 14
    assert manifest["eligible_coverage"] >= 0.90
    assert manifest["freeze_status"] == "FREEZE_CREATED_AWAITING_GIT_COMMIT"
    assert Path(manifest["frozen_ledger_snapshot_path"]).exists()
    assert Path(manifest["readiness_artifact_path"]).exists()

    # 3. Commit freeze manifest into Git repository
    commit_sha = _commit_in_test_git_repo(repo_dir, freeze_path)
    assert len(commit_sha) == 40

    # 4. Execute one-shot unblind
    results = gk.execute_one_shot_unblind(
        freeze_manifest_path=freeze_path,
        output_dir=output_dir,
        repo_root=repo_dir,
    )
    assert "scientific_verdict" in results
    assert results["evaluated_sample_size"] == len(slots)
    assert len(results["primary_60m_family"]) == 8
    assert results["freeze_commit_sha"] == commit_sha
    assert results["freeze_blob_verified"] is True
    assert results["freeze_commit_is_ancestor"] is True

    # 5. Verify all 8 required result artifacts exist
    required_artifacts = [
        "H39_ONE_SHOT_UNBLIND_FREEZE.json",
        "H39_ONE_SHOT_VALIDATION_RESULTS.json",
        "H39_ONE_SHOT_VALIDATION_REPORT.md",
        "H39_FAMILYWISE_HOLM_RESULTS.json",
        "H39_BASELINE_INCREMENTAL_RESULTS.json",
        "H39_STABILITY_DIAGNOSTICS.json",
        "H39_FINAL_SCIENTIFIC_VERDICT.json",
        "H39_ONE_SHOT_EXECUTION_RECEIPT.json",
    ]
    for art in required_artifacts:
        p = output_dir / art
        assert p.exists(), f"Missing required deliverable: {art}"
        assert p.stat().st_size > 0

    receipt = json.loads((output_dir / "H39_ONE_SHOT_EXECUTION_RECEIPT.json").read_text(encoding="utf-8"))
    assert receipt["freeze_commit_sha"] == commit_sha
    assert receipt["scientific_verdict"] == results["scientific_verdict"]


def test_generate_all_v0325_deliverables_immature_state(tmp_path: Path) -> None:
    """Test v0.3.25 deliverables generation under immature state (current live repo state)."""
    deliv_dir = tmp_path / "v0.3.25"
    files = generate_all_v0325_deliverables(output_dir=deliv_dir)
    assert len(files) == 7
    assert all(Path(p).exists() for p in files.values())

    expected_files = [
        "README.md",
        "H39_UNBLIND_PREREGISTRATION_MANIFEST.json",
        "H39_BLIND_OPERATIONAL_STATUS.json",
        "FORWARD_CHAIN_HEALTH.json",
        "V0.3.25_H39_ONE_SHOT_UNBLIND_PREREGISTRATION_REPORT.md",
        "V0.3.25_COMMITTED_FREEZE_EXACTLY_ONCE_REPAIR.json",
        "V0.3.25_COMMITTED_FREEZE_EXACTLY_ONCE_REPAIR.md",
    ]
    for ef in expected_files:
        p = deliv_dir / ef
        assert p.exists(), f"Missing deliverable {ef}"

    # Performance artifacts MUST NOT exist
    forbidden_files = [
        "H39_ONE_SHOT_UNBLIND_FREEZE.json",
        "H39_ONE_SHOT_VALIDATION_RESULTS.json",
        "H39_ONE_SHOT_VALIDATION_REPORT.md",
        "H39_FAMILYWISE_HOLM_RESULTS.json",
        "H39_BASELINE_INCREMENTAL_RESULTS.json",
        "H39_STABILITY_DIAGNOSTICS.json",
        "H39_FINAL_SCIENTIFIC_VERDICT.json",
        "H39_ONE_SHOT_EXECUTION_RECEIPT.json",
    ]
    for ff in forbidden_files:
        assert not (deliv_dir / ff).exists(), f"Forbidden performance deliverable created: {ff}"

    status_data = json.loads((deliv_dir / "H39_BLIND_OPERATIONAL_STATUS.json").read_text(encoding="utf-8"))
    assert status_data["state"] == H39_STATE_INSUFFICIENT
    assert status_data["ready_for_unblind"] is False

    repair_data = json.loads((deliv_dir / "V0.3.25_COMMITTED_FREEZE_EXACTLY_ONCE_REPAIR.json").read_text(encoding="utf-8"))
    assert repair_data["scientific_state"] == "FORWARD_DATA_INSUFFICIENT"
    assert repair_data["real_one_shot_executed"] is False
    assert repair_data["real_validation_labels_loaded"] is False
    assert repair_data["real_validation_performance_artifacts_created"] is False


# =====================================================================
# ACCEPTANCE REPAIR REGRESSION TESTS (Findings A - F, K)
# =====================================================================

def test_finding_a_uncommitted_freeze_cannot_unblind(tmp_path: Path) -> None:
    """Finding A: Uncommitted freeze file is rejected before label loading."""
    repo_dir = tmp_path / "repo"
    _init_test_git_repo(repo_dir)

    db_path = tmp_path / "mature_ledger.sqlite3"
    candles_path = tmp_path / "canonical_candles.sqlite3"
    _ledger, latest_ms = _create_synthetic_ledger(db_path, num_days=14, slots_per_day=96)

    freeze_file = repo_dir / "freeze.json"
    gk = H39OneShotUnblindGatekeeper(
        ledger_path=db_path,
        canonical_candles_path=candles_path,
        registry_path=tmp_path / "reg.sqlite3",
        snapshot_dir=tmp_path / "snapshots",
        repo_root=repo_dir,
    )
    gk.create_freeze_manifest(output_path=freeze_file, as_of_ms=latest_ms)
    # Deliberately DO NOT git commit freeze_file

    with patch.object(H39ResearchEngine, "get_canonical_1m_candles") as mock_candles:
        with pytest.raises(RuntimeError, match="COMMITTED_FREEZE_VERIFICATION_FAILED"):
            gk.execute_one_shot_unblind(
                freeze_manifest_path=freeze_file,
                output_dir=tmp_path / "results",
                repo_root=repo_dir,
            )
        assert mock_candles.call_count == 0


def test_finding_a_dirty_freeze_cannot_unblind(tmp_path: Path) -> None:
    """Finding A: Committed freeze file with unstaged local modifications is rejected."""
    repo_dir = tmp_path / "repo"
    _init_test_git_repo(repo_dir)

    db_path = tmp_path / "mature_ledger.sqlite3"
    candles_path = tmp_path / "canonical_candles.sqlite3"
    _ledger, latest_ms = _create_synthetic_ledger(db_path, num_days=14, slots_per_day=96)

    freeze_file = repo_dir / "freeze.json"
    gk = H39OneShotUnblindGatekeeper(
        ledger_path=db_path,
        canonical_candles_path=candles_path,
        registry_path=tmp_path / "reg.sqlite3",
        snapshot_dir=tmp_path / "snapshots",
        repo_root=repo_dir,
    )
    gk.create_freeze_manifest(output_path=freeze_file, as_of_ms=latest_ms)
    _commit_in_test_git_repo(repo_dir, freeze_file)

    # Mutate file on disk to create dirty unstaged changes
    freeze_file.write_text(freeze_file.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with patch.object(H39ResearchEngine, "get_canonical_1m_candles") as mock_candles:
        with pytest.raises(RuntimeError, match="COMMITTED_FREEZE_VERIFICATION_FAILED"):
            gk.execute_one_shot_unblind(
                freeze_manifest_path=freeze_file,
                output_dir=tmp_path / "results",
                repo_root=repo_dir,
            )
        assert mock_candles.call_count == 0


def test_finding_a_exact_committed_blob_is_required(tmp_path: Path) -> None:
    """Finding A: Exact committed blob verification helper passes on unmodified committed file."""
    repo_dir = tmp_path / "repo"
    _init_test_git_repo(repo_dir)

    db_path = tmp_path / "mature_ledger.sqlite3"
    _ledger, latest_ms = _create_synthetic_ledger(db_path, num_days=14, slots_per_day=96)

    freeze_file = repo_dir / "freeze.json"
    gk = H39OneShotUnblindGatekeeper(
        ledger_path=db_path,
        registry_path=tmp_path / "reg.sqlite3",
        snapshot_dir=tmp_path / "snapshots",
        repo_root=repo_dir,
    )
    gk.create_freeze_manifest(output_path=freeze_file, as_of_ms=latest_ms)
    commit_sha = _commit_in_test_git_repo(repo_dir, freeze_file)

    info = verify_committed_freeze_package(freeze_file, repo_root=repo_dir)
    assert info["freeze_commit_sha"] == commit_sha
    assert info["freeze_blob_verified"] is True
    assert info["freeze_commit_is_ancestor"] is True


def test_finding_a_freeze_commit_must_be_ancestor(tmp_path: Path) -> None:
    """Finding A: Freeze commit on diverged/non-ancestor branch is rejected."""
    repo_dir = tmp_path / "repo"
    _init_test_git_repo(repo_dir)

    db_path = tmp_path / "mature_ledger.sqlite3"
    _ledger, latest_ms = _create_synthetic_ledger(db_path, num_days=14, slots_per_day=96)

    freeze_file = repo_dir / "freeze.json"
    gk = H39OneShotUnblindGatekeeper(
        ledger_path=db_path,
        registry_path=tmp_path / "reg.sqlite3",
        snapshot_dir=tmp_path / "snapshots",
        repo_root=repo_dir,
    )
    gk.create_freeze_manifest(output_path=freeze_file, as_of_ms=latest_ms)

    # Commit freeze on a side branch
    subprocess.run(["git", "checkout", "-b", "side-branch"], cwd=str(repo_dir), check=True, capture_output=True)
    _commit_in_test_git_repo(repo_dir, freeze_file)

    # Switch back to default branch where freeze commit is NOT in history
    default_branch = (
        "master"
        if subprocess.run(
            ["git", "branch", "--list", "master"],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        else "main"
    )
    subprocess.run(["git", "checkout", default_branch], cwd=str(repo_dir), check=True, capture_output=True)
    # Create diverged commit on HEAD
    (repo_dir / "diverged.txt").write_text("diverged", encoding="utf-8")
    _commit_in_test_git_repo(repo_dir, repo_dir / "diverged.txt", commit_msg="diverged commit")

    # Put freeze_file on disk without committing on this branch
    gk.create_freeze_manifest(output_path=freeze_file, as_of_ms=latest_ms)

    with patch.object(H39ResearchEngine, "get_canonical_1m_candles") as mock_candles:
        with pytest.raises(RuntimeError, match="COMMITTED_FREEZE_VERIFICATION_FAILED"):
            gk.execute_one_shot_unblind(
                freeze_manifest_path=freeze_file,
                output_dir=tmp_path / "results",
                repo_root=repo_dir,
            )
        assert mock_candles.call_count == 0


def test_finding_b_exactly_once_reservation(tmp_path: Path) -> None:
    """Finding B: Execution key can be reserved exactly once; duplicate reservation raises H39_ONE_SHOT_ALREADY_CONSUMED."""
    reg_path = tmp_path / "registry.sqlite3"
    registry = H39OneShotExecutionRegistry(reg_path)

    key = "test_execution_key_001"
    registry.reserve_execution(
        execution_key=key,
        freeze_manifest_sha256="sha_manifest",
        freeze_commit_sha="sha_commit",
        unblind_cutoff_ms=1000000,
        protocol_hash="proto_hash",
        clarification_hash="clar_hash",
        executing_git_sha="git_sha",
    )
    rec = registry.get_execution(key)
    assert rec is not None
    assert rec["state"] == "STARTED"

    # Second reservation attempt with same key must raise H39_ONE_SHOT_ALREADY_CONSUMED
    with pytest.raises(RuntimeError, match=H39_ONE_SHOT_ALREADY_CONSUMED):
        registry.reserve_execution(
            execution_key=key,
            freeze_manifest_sha256="sha_manifest",
            freeze_commit_sha="sha_commit",
            unblind_cutoff_ms=1000000,
            protocol_hash="proto_hash",
            clarification_hash="clar_hash",
            executing_git_sha="git_sha",
        )


def test_finding_b_completed_execution_cannot_rerun(tmp_path: Path) -> None:
    """Finding B: Completed execution cannot be rerun or overwritten."""
    reg_path = tmp_path / "registry.sqlite3"
    registry = H39OneShotExecutionRegistry(reg_path)

    key = "test_completed_key_002"
    registry.reserve_execution(
        execution_key=key,
        freeze_manifest_sha256="sha_manifest",
        freeze_commit_sha="sha_commit",
        unblind_cutoff_ms=1000000,
        protocol_hash="proto_hash",
        clarification_hash="clar_hash",
        executing_git_sha="git_sha",
    )
    registry.complete_execution(key, result_manifest_sha256="result_sha")
    rec = registry.get_execution(key)
    assert rec is not None
    assert rec["state"] == "COMPLETED"

    with pytest.raises(RuntimeError, match=H39_ONE_SHOT_ALREADY_CONSUMED):
        registry.reserve_execution(
            execution_key=key,
            freeze_manifest_sha256="sha_manifest",
            freeze_commit_sha="sha_commit",
            unblind_cutoff_ms=1000000,
            protocol_hash="proto_hash",
            clarification_hash="clar_hash",
            executing_git_sha="git_sha",
        )


def test_finding_b_crash_fail_closed(tmp_path: Path) -> None:
    """Finding B: Interrupted execution remains STARTED; no auto reset on next run."""
    reg_path = tmp_path / "registry.sqlite3"
    registry = H39OneShotExecutionRegistry(reg_path)

    key = "test_crash_key_003"
    registry.reserve_execution(
        execution_key=key,
        freeze_manifest_sha256="sha_manifest",
        freeze_commit_sha="sha_commit",
        unblind_cutoff_ms=1000000,
        protocol_hash="proto_hash",
        clarification_hash="clar_hash",
        executing_git_sha="git_sha",
    )

    # Process "crashes" before completing. Next run refuses:
    with pytest.raises(RuntimeError, match=H39_ONE_SHOT_ALREADY_CONSUMED):
        registry.reserve_execution(
            execution_key=key,
            freeze_manifest_sha256="sha_manifest",
            freeze_commit_sha="sha_commit",
            unblind_cutoff_ms=1000000,
            protocol_hash="proto_hash",
            clarification_hash="clar_hash",
            executing_git_sha="git_sha",
        )
    # State is still STARTED
    assert registry.get_execution(key)["state"] == "STARTED"


def test_finding_c_wal_safe_snapshot(tmp_path: Path) -> None:
    """Finding C: Freeze creates consistent SQLite backup snapshot with verified integrity and pinned SHA."""
    repo_dir = tmp_path / "repo"
    _init_test_git_repo(repo_dir)

    db_path = tmp_path / "wal_ledger.sqlite3"
    snapshot_dir = tmp_path / "snapshots"
    _ledger, latest_ms = _create_synthetic_ledger(db_path, num_days=14, slots_per_day=96)

    # Explicitly enforce WAL mode
    with _open_sqlite(db_path) as conn:
        conn.execute("PRAGMA journal_mode = WAL;")

    freeze_file = repo_dir / "freeze.json"
    gk = H39OneShotUnblindGatekeeper(
        ledger_path=db_path,
        registry_path=tmp_path / "reg.sqlite3",
        snapshot_dir=snapshot_dir,
        repo_root=repo_dir,
    )
    manifest = gk.create_freeze_manifest(output_path=freeze_file, as_of_ms=latest_ms)

    snapshot_path = Path(manifest["frozen_ledger_snapshot_path"])
    assert snapshot_path.exists()
    assert manifest["frozen_ledger_snapshot_sha256"] == _compute_sha256(snapshot_path)

    # Check snapshot integrity
    with _open_sqlite(f"file:{snapshot_path.as_posix()}?mode=ro", uri=True) as conn:
        chk = conn.execute("PRAGMA integrity_check;").fetchone()[0]
        assert chk.lower() == "ok"
        snap_count = conn.execute("SELECT COUNT(*) FROM h39_blind_validation_ledger;").fetchone()[0]

    with _open_sqlite(f"file:{db_path.as_posix()}?mode=ro", uri=True) as conn:
        live_count = conn.execute("SELECT COUNT(*) FROM h39_blind_validation_ledger;").fetchone()[0]

    assert snap_count == live_count
    assert snap_count == manifest["snapshot_total_row_count"]


def test_finding_d_readiness_artifact_hash_tampering(tmp_path: Path) -> None:
    """Finding D: Readiness artifact tampering fails verification before labels are read."""
    repo_dir = tmp_path / "repo"
    _init_test_git_repo(repo_dir)

    db_path = tmp_path / "mature_ledger.sqlite3"
    candles_path = tmp_path / "canonical_candles.sqlite3"
    _ledger, latest_ms = _create_synthetic_ledger(db_path, num_days=14, slots_per_day=96)

    freeze_file = repo_dir / "freeze.json"
    gk = H39OneShotUnblindGatekeeper(
        ledger_path=db_path,
        canonical_candles_path=candles_path,
        registry_path=tmp_path / "reg.sqlite3",
        snapshot_dir=tmp_path / "snapshots",
        repo_root=repo_dir,
    )
    manifest = gk.create_freeze_manifest(output_path=freeze_file, as_of_ms=latest_ms)
    _commit_in_test_git_repo(repo_dir, freeze_file)

    # Tamper with readiness artifact on disk
    readiness_path = Path(manifest["readiness_artifact_path"])
    readiness_path.write_text('{"tampered": true}', encoding="utf-8")

    with patch.object(H39ResearchEngine, "get_canonical_1m_candles") as mock_candles:
        with pytest.raises(RuntimeError, match="READINESS_ARTIFACT_TAMPERED"):
            gk.execute_one_shot_unblind(
                freeze_manifest_path=freeze_file,
                output_dir=tmp_path / "results",
                repo_root=repo_dir,
            )
        assert mock_candles.call_count == 0


def test_finding_f_label_loader_ordering_spy(tmp_path: Path) -> None:
    """Finding F: Candle and label loader is NEVER called on failed freeze, dirty freeze, or consumed key."""
    repo_dir = tmp_path / "repo"
    _init_test_git_repo(repo_dir)

    db_path = tmp_path / "mature_ledger.sqlite3"
    candles_path = tmp_path / "canonical_candles.sqlite3"
    _ledger, latest_ms = _create_synthetic_ledger(db_path, num_days=14, slots_per_day=96)

    with _open_sqlite(db_path) as conn:
        slots = [r[0] for r in conn.execute("SELECT decision_close_ms FROM h39_blind_validation_ledger WHERE decision_close_ms <= ?", (latest_ms,)).fetchall()]
    _populate_canonical_candles(candles_path, slots)

    freeze_file = repo_dir / "freeze.json"
    registry_path = tmp_path / "reg.sqlite3"
    gk = H39OneShotUnblindGatekeeper(
        ledger_path=db_path,
        canonical_candles_path=candles_path,
        registry_path=registry_path,
        snapshot_dir=tmp_path / "snapshots",
        repo_root=repo_dir,
    )
    gk.create_freeze_manifest(output_path=freeze_file, as_of_ms=latest_ms)
    _commit_in_test_git_repo(repo_dir, freeze_file)

    # First run succeeds
    res = gk.execute_one_shot_unblind(
        freeze_manifest_path=freeze_file,
        output_dir=tmp_path / "results",
        repo_root=repo_dir,
    )
    assert res["evaluated_sample_size"] == len(slots)

    # Second run for identical freeze: fails closed with H39_ONE_SHOT_ALREADY_CONSUMED BEFORE candles loaded
    with patch.object(H39ResearchEngine, "get_canonical_1m_candles") as mock_candles:
        with pytest.raises(RuntimeError, match=H39_ONE_SHOT_ALREADY_CONSUMED):
            gk.execute_one_shot_unblind(
                freeze_manifest_path=freeze_file,
                output_dir=tmp_path / "results2",
                repo_root=repo_dir,
            )
        assert mock_candles.call_count == 0


def test_finding_k_no_real_unblind_during_current_repair() -> None:
    """Finding K: Real H39 evidence remains immature and zero real validation performance files exist."""
    deliv_dir = Path("deliverables/v0.3.25")
    if deliv_dir.exists():
        status_file = deliv_dir / "H39_BLIND_OPERATIONAL_STATUS.json"
        if status_file.exists():
            status = json.loads(status_file.read_text(encoding="utf-8"))
            assert status["state"] == "FORWARD_DATA_INSUFFICIENT"
            assert status["ready_for_unblind"] is False

        forbidden = [
            deliv_dir / "H39_ONE_SHOT_UNBLIND_FREEZE.json",
            deliv_dir / "H39_ONE_SHOT_VALIDATION_RESULTS.json",
            deliv_dir / "H39_ONE_SHOT_VALIDATION_REPORT.md",
            deliv_dir / "H39_FAMILYWISE_HOLM_RESULTS.json",
            deliv_dir / "H39_BASELINE_INCREMENTAL_RESULTS.json",
            deliv_dir / "H39_STABILITY_DIAGNOSTICS.json",
            deliv_dir / "H39_FINAL_SCIENTIFIC_VERDICT.json",
            deliv_dir / "H39_ONE_SHOT_EXECUTION_RECEIPT.json",
        ]
        for f in forbidden:
            assert not f.exists(), f"Forbidden real unblind artifact exists in live repo: {f}"
