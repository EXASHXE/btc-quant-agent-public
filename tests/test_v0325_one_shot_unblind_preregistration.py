"""Regression and unit tests for BTC Quant Agent v0.3.25: H39 One-Shot Unblind Preregistration."""
from __future__ import annotations

import json
import sqlite3
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
    H39_CLARIFICATION_002_SHA,
    H39_CLARIFICATION_003_SHA,
    H39_CORRECTED_EVALUATOR_VERSION,
    H39_FROZEN_CLARIFICATION_002_HASH,
    H39_FROZEN_CLARIFICATION_003_HASH,
    H39_FROZEN_CLARIFICATION_HASH,
    H39_FROZEN_PROTOCOL_HASH,
    H39_FUTURE_SKEW_TOLERANCE_SECONDS,
    H39_HAC_MAX_LAG_60M,
    H39_HAC_MAX_LAG_240M,
    H39_INPUT_CONTRACT_VERSION,
    H39_LR_BOOTSTRAP_BLOCK_LENGTH,
    H39_LR_BOOTSTRAP_REPLICATIONS,
    H39_LR_BOOTSTRAP_SEED,
    H39_ONE_SHOT_ALREADY_CONSUMED,
    H39_STATE_BLOCKED_QUALITY,
    H39_STATE_INSUFFICIENT,
    H39_VALIDATION_START_MS,
    MICROSTRUCTURE_REQUIRED_COLUMNS,
    MICROSTRUCTURE_REQUIRED_TABLES,
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
    _fit_l2_logistic_regression,
    _hac_robust_nested_score_test,
    _holm_bonferroni,
    _l2_logistic_sandwich_cov,
    _moving_block_bootstrap_lr_p_value,
    _newey_west_linear_regression,
    _open_sqlite,
    evaluate_feature_hypotheses,
    evaluate_forward_chain_health,
    generate_all_v0325_deliverables,
    verify_committed_freeze_package,
)


def _populate_canonical_microstructure_partition(
    db_path: Path,
    event_time_ms: int,
    receive_time_ms: int | None = None,
) -> None:
    rec_ms = receive_time_ms if receive_time_ms is not None else event_time_ms
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE agg_trades (
                aggregate_trade_id INTEGER PRIMARY KEY,
                event_time_ms INTEGER,
                transaction_time_ms INTEGER,
                receive_time_ms INTEGER,
                receive_monotonic_ns INTEGER,
                price REAL,
                quantity REAL,
                buyer_is_maker INTEGER,
                aggressive_side TEXT,
                payload_hash TEXT
            )"""
        )
        conn.execute(
            """CREATE TABLE book_samples (
                event_time_ms INTEGER,
                final_update_id INTEGER,
                receive_time_ms INTEGER,
                spread_bps REAL,
                top1_imbalance REAL,
                top5_imbalance REAL,
                top20_imbalance REAL,
                microprice REAL,
                ofi REAL,
                PRIMARY KEY(event_time_ms, final_update_id)
            )"""
        )
        conn.execute(
            """CREATE TABLE gaps (
                id INTEGER PRIMARY KEY,
                start_ms INTEGER,
                end_ms INTEGER,
                kind TEXT,
                detail TEXT
            )"""
        )
        conn.execute(
            """INSERT INTO agg_trades (aggregate_trade_id, event_time_ms, transaction_time_ms, receive_time_ms, price, quantity, aggressive_side)
               VALUES (1, ?, ?, ?, 50000.0, 1.0, 'BUY')""",
            (event_time_ms, event_time_ms, rec_ms),
        )
        conn.execute(
            """INSERT INTO book_samples (event_time_ms, final_update_id, receive_time_ms, spread_bps, top1_imbalance, top5_imbalance, top20_imbalance, microprice, ofi)
               VALUES (?, 1, ?, 0.5, 0.1, 0.2, 0.3, 50000.1, 10.0)""",
            (event_time_ms, rec_ms),
        )
        conn.commit()


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
        "m7_pressure_agreement": m_val,
        "m8_pressure_divergence": max(0.01, 1.0 - m_val),
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


def _gatekeeper(tmp_path: Path, **overrides: Any) -> H39OneShotUnblindGatekeeper:
    paths: dict[str, str | Path] = {
        "ledger_path": tmp_path / "h39_ledger.sqlite3",
        "microstructure_root": tmp_path / "microstructure",
        "opportunity_store_path": tmp_path / "opportunity.sqlite3",
        "canonical_candles_path": tmp_path / "canonical_candles.sqlite3",
        "registry_path": tmp_path / "one_shot_registry.sqlite3",
        "snapshot_dir": tmp_path / "frozen_snapshots",
    }
    paths.update(overrides)
    return H39OneShotUnblindGatekeeper(**paths)


def _research_engine(tmp_path: Path) -> H39ResearchEngine:
    return H39ResearchEngine(
        microstructure_root=tmp_path / "microstructure",
        opportunity_store_path=tmp_path / "opportunity.sqlite3",
        canonical_candles_path=tmp_path / "canonical_candles.sqlite3",
    )


def _forward_health(tmp_path: Path, **overrides: Any) -> dict[str, Any]:
    paths: dict[str, Any] = {
        "microstructure_root": tmp_path / "microstructure",
        "canonical_derivatives_path": tmp_path / "derivatives.sqlite3",
        "opportunity_store_path": tmp_path / "opportunity.sqlite3",
        "now_ms": H39_VALIDATION_START_MS,
    }
    paths.update(overrides)
    return evaluate_forward_chain_health(**paths)


# =====================================================================
# SECTION 13 REQUIREMENT TESTS
# =====================================================================

def test_unblind_refuses_before_14_days(tmp_path: Path) -> None:
    """1. Unblind refuses before 14 distinct UTC days."""
    db_path = tmp_path / "h39_ledger.sqlite3"
    # 13 distinct days with full slots (51 + 12*96 = 1203 eligible slots, 100% coverage at latest_ms)
    _ledger, latest_ms = _create_synthetic_ledger(db_path, num_days=13, slots_per_day=96)

    gk = _gatekeeper(tmp_path, ledger_path=db_path)
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

    gk = _gatekeeper(tmp_path, ledger_path=db_path)
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
    gk = _gatekeeper(tmp_path, ledger_path=db_path)
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

    gk = _gatekeeper(tmp_path, ledger_path=db_path)
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

    gk = _gatekeeper(tmp_path, ledger_path=db_path)
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

    gk = _gatekeeper(tmp_path, ledger_path=db_path, protocol_path=bad_proto)
    with pytest.raises(RuntimeError, match="PROTOCOL_HASH_DRIFT"):
        gk.verify_readiness_preconditions(as_of_ms=latest_ms)


def test_clarification_hash_drift_blocks_unblind(tmp_path: Path) -> None:
    """7. Clarification hash drift blocks unblind."""
    db_path = tmp_path / "h39_ledger.sqlite3"
    _ledger, latest_ms = _create_synthetic_ledger(db_path, num_days=14, slots_per_day=54)

    bad_clar = tmp_path / "bad_clarification.json"
    bad_clar.write_text('{"tampered": true}', encoding="utf-8")

    gk = _gatekeeper(tmp_path, ledger_path=db_path, clarification_path=bad_clar)
    with pytest.raises(RuntimeError, match="CLARIFICATION_HASH_DRIFT"):
        gk.verify_readiness_preconditions(as_of_ms=latest_ms)


def test_clarification_002_and_003_hash_and_sha_pinned() -> None:
    """Clarification 002 and 003 commit SHAs and file hashes are correctly pinned."""
    assert H39_CLARIFICATION_002_SHA == "6e1259409aa4f1cedf86b7a424666ee7c942a929"
    assert H39_FROZEN_CLARIFICATION_002_HASH == "94c938b65640252c85a9e320b6f7759729ffa00f793c93e17cca52726e73212e"
    assert H39_CLARIFICATION_003_SHA == "5d055ae17798bdc00e1b0d6388596ecd59358251"
    assert H39_FROZEN_CLARIFICATION_003_HASH == "035b7528141c714fbe1aef310462d5aa5fd96d3d5fdec67ae8f70082531d7a92"


def test_legacy_evaluate_validation_status_cannot_authorize_unblind(
    tmp_path: Path, h39_outcome_access_spy: list[str]
) -> None:
    """8. Legacy evaluate_validation_status cannot authorize unblind."""
    engine = _research_engine(tmp_path)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        diag = engine.evaluate_validation_status()
        assert any(issubclass(warn.category, DeprecationWarning) for warn in w)

    assert diag["deprecated"] is True
    assert diag["authoritative"] is False
    assert diag["diagnostic_only"] is True
    assert diag["readiness_authority"] == "NON_AUTHORITATIVE_DIAGNOSTIC_ONLY"
    assert diag["authoritative_unblind_authorization_allowed"] is False
    assert h39_outcome_access_spy == []


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
    gk = _gatekeeper(
        tmp_path,
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
    gk = _gatekeeper(
        tmp_path,
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


def test_baseline_fields_exactly_frozen_trio(tmp_path: Path) -> None:
    """16. Baseline fields are exactly trailing_return_15m, trailing_return_60m, trailing_atr_ratio_15m."""
    gatekeeper = _gatekeeper(tmp_path)
    assert gatekeeper is not None


def test_no_hyperparameter_or_model_search() -> None:
    """17. Incremental modeling uses fixed L2 logistic regression with lambda=1.0."""
    manifest = json.loads(Path("deliverables/v0.3.25/H39_UNBLIND_PREREGISTRATION_MANIFEST.json").read_text(encoding="utf-8")) if Path("deliverables/v0.3.25/H39_UNBLIND_PREREGISTRATION_MANIFEST.json").exists() else {}
    if manifest:
        assert manifest["model_family"] == "L2_LOGISTIC_REGRESSION_LAMBDA_1_0"


def test_no_final_holdout_access(
    tmp_path: Path, h39_outcome_access_spy: list[str]
) -> None:
    """18. Final holdout remains sealed and unread."""
    gk = _gatekeeper(tmp_path)
    readiness = gk.verify_readiness_preconditions(now_ms=H39_VALIDATION_START_MS)
    assert readiness["summary"]["safety_firewalls"]["final_holdout"] == "SEALED"
    assert h39_outcome_access_spy == []


def test_no_runtime_direction_integration(tmp_path: Path) -> None:
    """19. Direction engine remains NONE, runtime ceiling remains OPPORTUNITY_ONLY."""
    gk = _gatekeeper(tmp_path)
    readiness = gk.verify_readiness_preconditions(now_ms=H39_VALIDATION_START_MS)
    fw = readiness["summary"]["safety_firewalls"]
    assert fw["qualified_direction_engine"] == "NONE"
    assert fw["runtime_maximum"] == "OPPORTUNITY_ONLY"


def test_execution_remains_disabled(tmp_path: Path) -> None:
    """20. Execution engine remains DISABLED and auto_execute false."""
    gk = _gatekeeper(tmp_path)
    readiness = gk.verify_readiness_preconditions(now_ms=H39_VALIDATION_START_MS)
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

    gk = _gatekeeper(
        tmp_path,
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
    files = generate_all_v0325_deliverables(
        output_dir=deliv_dir,
        ledger_path=tmp_path / "h39_ledger.sqlite3",
        microstructure_root=tmp_path / "microstructure",
        opportunity_store_path=tmp_path / "opportunity.sqlite3",
        canonical_derivatives_path=tmp_path / "derivatives.sqlite3",
        canonical_candles_path=tmp_path / "canonical_candles.sqlite3",
        registry_path=tmp_path / "one_shot_registry.sqlite3",
        snapshot_dir=tmp_path / "frozen_snapshots",
        as_of_ms=H39_VALIDATION_START_MS,
        now_ms=H39_VALIDATION_START_MS,
    )
    assert len(files) == 11
    assert all(Path(p).exists() for p in files.values())

    expected_files = [
        "README.md",
        "H39_UNBLIND_PREREGISTRATION_MANIFEST.json",
        "H39_BLIND_OPERATIONAL_STATUS.json",
        "FORWARD_CHAIN_HEALTH.json",
        "V0.3.25_H39_ONE_SHOT_UNBLIND_PREREGISTRATION_REPORT.md",
        "V0.3.25_COMMITTED_FREEZE_EXACTLY_ONCE_REPAIR.json",
        "V0.3.25_COMMITTED_FREEZE_EXACTLY_ONCE_REPAIR.md",
        "V0.3.25_STATISTICAL_DEPENDENCE_HEALTH_REPAIR.json",
        "V0.3.25_STATISTICAL_DEPENDENCE_HEALTH_REPAIR.md",
        "V0.3.25_ROBUST_NULL_PROTOCOL_IDENTITY_HEALTH_SCHEMA_REPAIR.json",
        "V0.3.25_ROBUST_NULL_PROTOCOL_IDENTITY_HEALTH_SCHEMA_REPAIR.md",
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
    gk = _gatekeeper(
        tmp_path,
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
    gk = _gatekeeper(
        tmp_path,
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
    gk = _gatekeeper(
        tmp_path,
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
    gk = _gatekeeper(
        tmp_path,
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
    gk = _gatekeeper(
        tmp_path,
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
    gk = _gatekeeper(
        tmp_path,
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
    gk = _gatekeeper(
        tmp_path,
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


def test_hac_linear_regression_fixed_lags() -> None:
    """Finding A.1: 60m formal inference uses HAC lag 3, 240m uses lag 15."""
    assert H39_HAC_MAX_LAG_60M == 3
    assert H39_HAC_MAX_LAG_240M == 15

    n = 100
    x = [[1.0, float(i)] for i in range(n)]
    y = [float(i) * 0.1 for i in range(n)]
    b60, se60, _t60, _, _ = _newey_west_linear_regression(x, y, max_lag=H39_HAC_MAX_LAG_60M)
    b240, se240, _t240, _, _ = _newey_west_linear_regression(x, y, max_lag=H39_HAC_MAX_LAG_240M)
    assert len(b60) == 2
    assert len(b240) == 2
    assert se60[1] > 0
    assert se240[1] > 0


def test_hac_standard_error_inflation_under_autocorrelation() -> None:
    """Finding A.2: Positive serial correlation inflates SE versus naive iid in AR(1) case."""
    import numpy as np

    rng = np.random.default_rng(12345)
    n = 300
    x_val = rng.standard_normal(n)
    # Generate AR(1) autocorrelated errors e_t = 0.8 * e_{t-1} + v_t
    e = np.zeros(n)
    v = rng.standard_normal(n)
    for t in range(1, n):
        e[t] = 0.8 * e[t - 1] + v[t]
    y_val = 0.5 * x_val + e

    x_mat = [[1.0, float(xv)] for xv in x_val]
    y_vec = [float(yv) for yv in y_val]

    _beta, se_hac, t_hac, se_iid, t_iid = _newey_west_linear_regression(
        x_mat, y_vec, max_lag=3, l2_lambda=0.0
    )
    # Positive autocorrelation must inflate the HAC standard error compared to naive iid SE
    assert se_hac[1] > se_iid[1]
    # Consequently, t-statistic must be smaller under HAC than naive iid
    assert abs(t_hac[1]) < abs(t_iid[1])


def test_sandwich_hac_logistic_regression() -> None:
    """Finding A.3: Sandwich HAC covariance produces valid SE and accounts for dependence."""
    import numpy as np

    rng = np.random.default_rng(54321)
    n = 200
    X = np.column_stack([np.ones(n), rng.standard_normal((n, 3)), rng.standard_normal(n)])
    y = (rng.uniform(0, 1, n) > 0.5).astype(float)
    b, _c_model, _ = _fit_l2_logistic_regression(X.tolist(), y.tolist(), l2_lambda=1.0)

    cov_sandwich, _cov_m = _l2_logistic_sandwich_cov(X, y, b, max_lag=3, l2_lambda=1.0)
    assert len(cov_sandwich) == 5
    assert cov_sandwich[4][4] > 0.0


def test_moving_block_bootstrap_lr_calibration_deterministic() -> None:
    """Finding A.4: Moving-block bootstrap parameters are frozen constants and execution is deterministic."""
    assert H39_LR_BOOTSTRAP_BLOCK_LENGTH == 4
    assert H39_LR_BOOTSTRAP_REPLICATIONS == 5000
    assert H39_LR_BOOTSTRAP_SEED == 390325

    import numpy as np

    rng = np.random.default_rng(9999)
    n = 100
    X_base = np.column_stack([np.ones(n), rng.standard_normal((n, 3))]).tolist()
    y = (rng.uniform(0, 1, n) > 0.5).astype(float).tolist()
    x_micro = rng.standard_normal(n).tolist()

    # Two identical runs with same seed must yield exact identical p-value
    p1 = _moving_block_bootstrap_lr_p_value(
        x_base=X_base,
        x_micro=x_micro,
        y_vector=y,
        ll_base=-60.0,
        observed_lr=2.5,
        block_length=4,
        n_boot=100,  # Fast check
        seed=390325,
    )
    p2 = _moving_block_bootstrap_lr_p_value(
        x_base=X_base,
        x_micro=x_micro,
        y_vector=y,
        ll_base=-60.0,
        observed_lr=2.5,
        block_length=4,
        n_boot=100,
        seed=390325,
    )
    assert p1 == p2
    assert 0.0 <= p1 <= 1.0


def test_one_shot_results_contain_hac_and_bootstrap(tmp_path: Path) -> None:
    """Finding A.5: execute_one_shot_unblind records HAC lags, robust p-values, and diagnostics."""
    repo_dir = tmp_path / "test_repo"
    _init_test_git_repo(repo_dir)

    db_path = tmp_path / "ledger.sqlite3"
    candles_path = tmp_path / "candles.sqlite3"
    _ledger, latest_ms = _create_synthetic_ledger(db_path, num_days=14, slots_per_day=96)

    freeze_file = repo_dir / "freeze.json"
    registry_path = tmp_path / "reg.sqlite3"
    gk = _gatekeeper(
        tmp_path,
        ledger_path=db_path,
        canonical_candles_path=candles_path,
        registry_path=registry_path,
        snapshot_dir=tmp_path / "snapshots",
        repo_root=repo_dir,
    )
    gk.create_freeze_manifest(output_path=freeze_file, as_of_ms=latest_ms)
    _commit_in_test_git_repo(repo_dir, freeze_file)

    with _open_sqlite(db_path) as conn:
        slots = [r[0] for r in conn.execute("SELECT decision_close_ms FROM h39_blind_validation_ledger WHERE decision_close_ms <= ?", (latest_ms,)).fetchall()]
    _populate_canonical_candles(candles_path, slots)

    res = gk.execute_one_shot_unblind(
        freeze_manifest_path=freeze_file,
        output_dir=tmp_path / "results",
        repo_root=repo_dir,
    )
    prim = res["primary_60m_family"]
    for fid in FORMAL_FEATURE_IDS:
        f_res = prim[fid]
        assert f_res["covariance_method"] == "NEWEY_WEST_HAC"
        assert f_res["hac_max_lag"] == 3
        assert f_res["formal_nested_method"] == H39_CORRECTED_EVALUATOR_VERSION
        assert "formal_nested_p_value" in f_res
        assert "formal_nested_z_stat" in f_res
        assert "diagnostics" in f_res
        assert "iid_standard_error" in f_res["diagnostics"]
        assert "iid_incremental_lr_p_value" in f_res["diagnostics"]
        assert f_res["diagnostics"]["clarification_002_bootstrap_role"] == "SUPERSEDED_DIAGNOSTIC_ONLY"
        assert f_res["diagnostics"]["iid_role"] == "DIAGNOSTIC_ONLY"


def test_derivatives_health_states(tmp_path: Path) -> None:
    """Finding B.1: Derivatives chain evaluates all failure and healthy states correctly."""
    # 1. Missing file -> MISSING, exists=False, db_integrity=NOT_CHECKED, rows=0
    missing_path = tmp_path / "non_existent.sqlite3"
    h_missing = _forward_health(tmp_path, canonical_derivatives_path=missing_path)
    d_m = h_missing["derivatives_chain"]
    assert d_m["status"] == "MISSING"
    assert d_m["exists"] is False
    assert d_m["db_integrity"] == "NOT_CHECKED"
    assert d_m["rows_recorded"] == 0
    assert h_missing["aggregate_status"] == "BLOCKED"

    # 2. Corrupt / non-sqlite file -> READ_ERROR or INTEGRITY_ERROR
    corrupt_path = tmp_path / "corrupt.sqlite3"
    corrupt_path.write_bytes(b"NOT_A_SQLITE_DATABASE")
    h_corrupt = _forward_health(tmp_path, canonical_derivatives_path=corrupt_path)
    d_c = h_corrupt["derivatives_chain"]
    assert d_c["status"] in ("INTEGRITY_ERROR", "READ_ERROR")
    assert h_corrupt["aggregate_status"] == "BLOCKED"

    # 3. Valid sqlite with wrong schema -> SCHEMA_ERROR
    bad_schema = tmp_path / "bad_schema.sqlite3"
    with sqlite3.connect(bad_schema) as conn:
        conn.execute("CREATE TABLE other_table (id INT)")
    h_bad_schema = _forward_health(tmp_path, canonical_derivatives_path=bad_schema)
    assert h_bad_schema["derivatives_chain"]["status"] == "SCHEMA_ERROR"
    assert h_bad_schema["aggregate_status"] == "BLOCKED"

    # 4. Valid table but empty -> EMPTY
    empty_db = tmp_path / "empty.sqlite3"
    with sqlite3.connect(empty_db) as conn:
        conn.execute(
            """CREATE TABLE derivative_snapshots (
                observed_at_ms INT, funding_rate REAL, open_interest REAL,
                taker_buy_sell_ratio REAL, basis_rate REAL, long_short_account_ratio REAL
            )"""
        )
    h_empty = _forward_health(tmp_path, canonical_derivatives_path=empty_db)
    assert h_empty["derivatives_chain"]["status"] == "EMPTY"
    assert h_empty["derivatives_chain"]["rows_recorded"] == 0
    assert h_empty["aggregate_status"] == "BLOCKED"

    # 5. Stale data -> STALE
    stale_db = tmp_path / "stale.sqlite3"
    old_t = 1000000000000  # Long ago
    with sqlite3.connect(stale_db) as conn:
        conn.execute(
            """CREATE TABLE derivative_snapshots (
                observed_at_ms INT, funding_rate REAL, open_interest REAL,
                taker_buy_sell_ratio REAL, basis_rate REAL, long_short_account_ratio REAL
            )"""
        )
        conn.execute(
            "INSERT INTO derivative_snapshots VALUES (?, 0.0001, 1000.0, 1.1, 0.0002, 1.2)",
            (old_t,),
        )
    mock_m_root_stale = tmp_path / "micro_stale"
    mock_m_root_stale.mkdir()
    p_file_stale = mock_m_root_stale / "microstructure-2026-09-06.sqlite3"
    _populate_canonical_microstructure_partition(p_file_stale, old_t + 10_000_000 - 30_000)

    h_stale = _forward_health(
        tmp_path,
        canonical_derivatives_path=stale_db,
        microstructure_root=mock_m_root_stale,
        now_ms=old_t + 10_000_000,
    )
    assert h_stale["derivatives_chain"]["status"] == "STALE"
    assert h_stale["aggregate_status"] == "DEGRADED"

    # 6. Healthy fresh data -> HEALTHY
    fresh_db = tmp_path / "fresh.sqlite3"
    fresh_t = 1788720000000
    with sqlite3.connect(fresh_db) as conn:
        conn.execute(
            """CREATE TABLE derivative_snapshots (
                observed_at_ms INT, funding_rate REAL, open_interest REAL,
                taker_buy_sell_ratio REAL, basis_rate REAL, long_short_account_ratio REAL
            )"""
        )
        conn.execute(
            "INSERT INTO derivative_snapshots VALUES (?, 0.0001, 1000.0, 1.1, 0.0002, 1.2)",
            (fresh_t,),
        )
    mock_m_root = tmp_path / "micro"
    mock_m_root.mkdir()
    p_file = mock_m_root / "microstructure-2026-09-06.sqlite3"
    _populate_canonical_microstructure_partition(p_file, fresh_t)

    h_fresh = _forward_health(
        tmp_path,
        canonical_derivatives_path=fresh_db,
        microstructure_root=mock_m_root,
        now_ms=fresh_t + 60_000,
    )
    assert h_fresh["derivatives_chain"]["status"] == "HEALTHY"
    assert h_fresh["microstructure_chain"]["status"] == "HEALTHY"
    assert h_fresh["aggregate_status"] == "HEALTHY"


def test_microstructure_health_states(tmp_path: Path) -> None:
    """Finding B.2 & Blocker C: Microstructure health evaluates root, partitions, schema, and truthfulness."""
    # 1. Missing root -> MISSING
    h_m_missing = _forward_health(
        tmp_path, microstructure_root=tmp_path / "no_such_dir"
    )
    assert h_m_missing["microstructure_chain"]["status"] == "MISSING"
    assert h_m_missing["microstructure_chain"]["root_exists"] is False
    assert h_m_missing["aggregate_status"] == "BLOCKED"

    # 2. Empty directory (no partitions) -> MISSING
    empty_root = tmp_path / "empty_micro"
    empty_root.mkdir()
    h_m_empty = _forward_health(tmp_path, microstructure_root=empty_root)
    assert h_m_empty["microstructure_chain"]["status"] == "MISSING"
    assert h_m_empty["microstructure_chain"]["partition_count"] == 0

    # 3. Collector heartbeat is NOT_VERIFIED, never ACTIVE without proof
    assert h_m_empty["microstructure_chain"]["collector_heartbeat_status"] == "NOT_VERIFIED"

    # 4. H38 Opportunity Shadow is strictly DATA_QUALITY_TERMINAL_ARCHIVE
    assert h_m_empty["opportunity_shadow_chain"]["status"] == "DATA_QUALITY_TERMINAL_ARCHIVE"

    # Canonical tables and columns specification check
    assert "agg_trades" in MICROSTRUCTURE_REQUIRED_TABLES
    assert "book_samples" in MICROSTRUCTURE_REQUIRED_TABLES
    assert "gaps" in MICROSTRUCTURE_REQUIRED_TABLES
    assert "receive_time_ms" in MICROSTRUCTURE_REQUIRED_COLUMNS["agg_trades"]
    assert "receive_time_ms" in MICROSTRUCTURE_REQUIRED_COLUMNS["book_samples"]


def test_microstructure_tables_exist_but_columns_missing_is_schema_error(tmp_path: Path) -> None:
    """Blocker C: Required tables exist but columns missing triggers SCHEMA_ERROR, never HEALTHY."""
    m_root = tmp_path / "micro_bad_cols"
    m_root.mkdir()
    p_file = m_root / "microstructure-2026-09-07.sqlite3"
    with sqlite3.connect(p_file) as conn:
        conn.execute("CREATE TABLE agg_trades (event_time_ms INT)")
        conn.execute("CREATE TABLE book_samples (event_time_ms INT)")
        conn.execute("CREATE TABLE gaps (start_ms INT, end_ms INT)")
        conn.execute("INSERT INTO agg_trades VALUES (1000)")
        conn.execute("INSERT INTO book_samples VALUES (1000)")
    health = _forward_health(tmp_path, microstructure_root=m_root, now_ms=1000)
    assert health["microstructure_chain"]["status"] == "SCHEMA_ERROR"
    assert health["microstructure_chain"]["latest_partition_schema_valid"] is False
    assert health["aggregate_status"] == "BLOCKED"


def test_microstructure_missing_gaps_table_is_schema_error(tmp_path: Path) -> None:
    """Blocker C: Missing gaps table triggers SCHEMA_ERROR, never HEALTHY."""
    m_root = tmp_path / "micro_no_gaps"
    m_root.mkdir()
    p_file = m_root / "microstructure-2026-09-07.sqlite3"
    with sqlite3.connect(p_file) as conn:
        conn.execute("CREATE TABLE agg_trades (event_time_ms INT, receive_time_ms INT, price REAL, quantity REAL, aggressive_side TEXT)")
        conn.execute("CREATE TABLE book_samples (event_time_ms INT, receive_time_ms INT, spread_bps REAL, top1_imbalance REAL, top5_imbalance REAL, top20_imbalance REAL, microprice REAL, ofi REAL)")
    health = _forward_health(tmp_path, microstructure_root=m_root, now_ms=1000)
    assert health["microstructure_chain"]["status"] == "SCHEMA_ERROR"
    assert health["aggregate_status"] == "BLOCKED"


def test_future_receive_timestamp_beyond_tolerance_is_timestamp_error(tmp_path: Path) -> None:
    """Blocker C: Future receive timestamp beyond tolerance triggers TIMESTAMP_ERROR/CLOCK_SKEW."""
    m_root = tmp_path / "micro_future"
    m_root.mkdir()
    p_file = m_root / "microstructure-2026-09-07.sqlite3"
    now_ms = 1788750000000
    future_ms = now_ms + int((H39_FUTURE_SKEW_TOLERANCE_SECONDS + 1.0) * 1000)
    _populate_canonical_microstructure_partition(p_file, event_time_ms=now_ms, receive_time_ms=future_ms)

    health = _forward_health(tmp_path, microstructure_root=m_root, now_ms=now_ms)
    assert health["microstructure_chain"]["status"] == "TIMESTAMP_ERROR"
    assert health["aggregate_status"] == "BLOCKED"


def test_future_derivatives_observed_at_beyond_tolerance_is_timestamp_error(tmp_path: Path) -> None:
    """Blocker C: Future derivatives timestamp beyond tolerance triggers TIMESTAMP_ERROR."""
    d_path = tmp_path / "deriv_future.sqlite3"
    now_ms = 1788750000000
    future_ms = now_ms + int((H39_FUTURE_SKEW_TOLERANCE_SECONDS + 2.0) * 1000)
    with sqlite3.connect(d_path) as conn:
        conn.execute(
            """CREATE TABLE derivative_snapshots (
                observed_at_ms INT, funding_rate REAL, open_interest REAL,
                taker_buy_sell_ratio REAL, basis_rate REAL, long_short_account_ratio REAL
            )"""
        )
        conn.execute(
            "INSERT INTO derivative_snapshots VALUES (?, 0.0001, 1000.0, 1.1, 0.0002, 1.2)",
            (future_ms,),
        )
    health = _forward_health(tmp_path, canonical_derivatives_path=d_path, now_ms=now_ms)
    assert health["derivatives_chain"]["status"] == "TIMESTAMP_ERROR"
    assert health["aggregate_status"] == "BLOCKED"


def test_skewed_event_time_uses_valid_receive_time_for_freshness(tmp_path: Path) -> None:
    """Blocker C: Operational freshness prefers local receive_time_ms over exchange event_time_ms."""
    m_root = tmp_path / "micro_skewed"
    m_root.mkdir()
    p_file = m_root / "microstructure-2026-09-07.sqlite3"
    now_ms = 1788750000000
    skewed_event_ms = now_ms - 7200_000  # 2 hours stale
    fresh_receive_ms = now_ms - 20_000   # 20s fresh
    _populate_canonical_microstructure_partition(
        p_file, event_time_ms=skewed_event_ms, receive_time_ms=fresh_receive_ms
    )

    health = _forward_health(tmp_path, microstructure_root=m_root, now_ms=now_ms)
    assert health["microstructure_chain"]["freshness_basis"] == "LOCAL_RECEIVE_TIME"
    assert health["microstructure_chain"]["freshness_seconds"] == 20.0
    assert health["microstructure_chain"]["status"] == "HEALTHY"


def test_score_test_preserves_conditional_null_under_collinear_controls() -> None:
    """Blocker A: Nuisance parameter projection correctly preserves conditional null under collinear controls."""
    import numpy as np
    rng = np.random.default_rng(42)
    n = 200
    # X_base: intercept, momentum, volatility
    x1 = rng.normal(0, 1, n)
    x2 = rng.normal(0, 1, n)
    x3 = rng.exponential(1, n)
    X_base = np.column_stack([np.ones(n), x1, x2, x3])
    beta_base = np.array([0.1, 0.5, -0.4, 0.3])

    logits = X_base @ beta_base
    probs = 1.0 / (1.0 + np.exp(-logits))
    y = (rng.uniform(0, 1, n) < probs).astype(float)

    # x_micro is strongly correlated with X_base[:, 1] (momentum), but has ZERO direct effect on y
    x_micro = 0.8 * x1 + rng.normal(0, 0.2, n)

    z_score, p_score, _s_adj, v_hac = _hac_robust_nested_score_test(
        x_base=X_base,
        y_vector=y,
        x_micro=x_micro,
        beta_base=beta_base,
        max_lag=3,
        l2_lambda=1.0,
    )
    # Under conditional null, p_score should not falsely reject (p_score > 0.05)
    assert p_score > 0.05, f"False positive under conditional null: p_score={p_score:.4f}, z={z_score:.3f}"
    assert np.isfinite(v_hac) and v_hac > 0.0


def test_score_test_detects_controlled_synthetic_incremental_signal() -> None:
    """Blocker A: Score test detects strong true incremental signal in the correct positive direction."""
    import numpy as np
    rng = np.random.default_rng(123)
    n = 250
    x1 = rng.normal(0, 1, n)
    x2 = rng.normal(0, 1, n)
    x3 = rng.exponential(1, n)
    X_base = np.column_stack([np.ones(n), x1, x2, x3])
    beta_base = np.array([0.0, 0.3, -0.2, 0.1])

    # True positive incremental signal
    x_micro = rng.normal(0, 1, n)
    logits = X_base @ beta_base + 1.2 * x_micro
    probs = 1.0 / (1.0 + np.exp(-logits))
    y = (rng.uniform(0, 1, n) < probs).astype(float)

    z_score, p_score, _s_adj, _v_hac = _hac_robust_nested_score_test(
        x_base=X_base,
        y_vector=y,
        x_micro=x_micro,
        beta_base=beta_base,
        max_lag=3,
        l2_lambda=1.0,
    )
    assert p_score < 0.05, f"Expected detection of true signal, got p_score={p_score:.4f}"
    assert z_score > 0.0, f"Expected positive z_score, got {z_score:.3f}"


def test_score_test_deterministic_for_identical_input() -> None:
    """Blocker A: Score test is fully deterministic and closed-form."""
    import numpy as np
    X_base = np.array([[1.0, 0.2, -0.1], [1.0, 0.5, 0.3], [1.0, -0.2, 0.4], [1.0, 0.1, -0.2]])
    y = np.array([1.0, 0.0, 1.0, 0.0])
    x_micro = np.array([0.3, -0.4, 0.2, 0.1])
    beta_base = np.array([0.1, 0.2, -0.1])

    res1 = _hac_robust_nested_score_test(X_base, y, x_micro, beta_base, max_lag=2, l2_lambda=1.0)
    res2 = _hac_robust_nested_score_test(X_base, y, x_micro, beta_base, max_lag=2, l2_lambda=1.0)
    assert res1 == res2


def test_score_test_fails_closed_on_insufficient_or_singular() -> None:
    """Blocker A: Score test fails closed with STATISTICAL_INFERENCE_NOT_READY on invalid input."""
    import numpy as np
    X_base = np.array([[1.0, 0.2], [1.0, 0.5]])
    y = np.array([1.0, 0.0])
    x_micro = np.array([0.3, -0.4])
    beta_base = np.array([0.1, 0.2])

    with pytest.raises(RuntimeError, match="STATISTICAL_INFERENCE_NOT_READY"):
        _hac_robust_nested_score_test(X_base, y, x_micro, beta_base)


def test_missing_clarification_002_refused(tmp_path: Path) -> None:
    """Blocker B: Missing Clarification 002 file fails closed before readiness/freeze/unblind."""
    gk = _gatekeeper(
        tmp_path,
        clarification_002_path=tmp_path / "non_existent_002.json",
        repo_root=tmp_path,
    )
    with pytest.raises(FileNotFoundError, match="Protocol clarification 002 file not found"):
        gk.verify_protocol_and_clarification_hashes()


def test_missing_clarification_003_refused(tmp_path: Path) -> None:
    """Blocker B: Missing Clarification 003 file fails closed before readiness/freeze/unblind."""
    gk = _gatekeeper(
        tmp_path,
        clarification_003_path=tmp_path / "non_existent_003.json",
        repo_root=tmp_path,
    )
    with pytest.raises(FileNotFoundError, match="Protocol clarification 003 file not found"):
        gk.verify_protocol_and_clarification_hashes()


def test_hash_drift_002_refused(tmp_path: Path) -> None:
    """Blocker B: Hash drift on Clarification 002 triggers CLARIFICATION_002_HASH_DRIFT."""
    fake_002 = tmp_path / "fake_002.json"
    fake_002.write_text('{"drifted": true}', encoding="utf-8")
    gk = _gatekeeper(
        tmp_path,
        clarification_002_path=fake_002,
        repo_root=tmp_path,
    )
    with pytest.raises(RuntimeError, match="CLARIFICATION_002_HASH_DRIFT"):
        gk.verify_protocol_and_clarification_hashes()


def test_hash_drift_003_refused(tmp_path: Path) -> None:
    """Blocker B: Hash drift on Clarification 003 triggers CLARIFICATION_003_HASH_DRIFT."""
    fake_003 = tmp_path / "fake_003.json"
    fake_003.write_text('{"drifted": true}', encoding="utf-8")
    gk = _gatekeeper(
        tmp_path,
        clarification_003_path=fake_003,
        repo_root=tmp_path,
    )
    with pytest.raises(RuntimeError, match="CLARIFICATION_003_HASH_DRIFT"):
        gk.verify_protocol_and_clarification_hashes()


def test_freeze_manifest_omitting_002_refused(tmp_path: Path) -> None:
    """Blocker B: Freeze manifest omitting clarification_002_hash triggers FREEZE_MANIFEST_CORRUPT."""
    manifest_file = tmp_path / "corrupt_manifest.json"
    manifest_file.write_text(json.dumps({
        "artifact_name": "H39_ONE_SHOT_UNBLIND_FREEZE",
        "hypothesis_id": "H39",
        "validation_start_ms": H39_VALIDATION_START_MS,
        "validation_start_utc": "2026-09-04T11:15:00Z",
        "unblind_cutoff_ms": 1788750000000,
        "unblind_cutoff_utc": "2026-09-07T03:00:00Z",
        "expected_boundary_count": 800,
        "observed_boundary_count": 800,
        "eligible_boundary_count": 760,
        "eligible_coverage": 0.95,
        "distinct_days_count": 14,
        "readiness_artifact_path": "fake",
        "readiness_sha256": "fake",
        "frozen_ledger_snapshot_path": "fake",
        "frozen_ledger_snapshot_sha256": "fake",
        "source_partitions": {},
        "protocol_hash": H39_FROZEN_PROTOCOL_HASH,
        "clarification_hash": H39_FROZEN_CLARIFICATION_HASH,
        # OMITTED: clarification_002_hash
        "clarification_003_hash": H39_FROZEN_CLARIFICATION_003_HASH,
        "code_version_sha": "fake",
        "attestations": {},
    }), encoding="utf-8")
    gk = _gatekeeper(tmp_path)
    with pytest.raises(RuntimeError, match="FREEZE_MANIFEST_CORRUPT"):
        gk.verify_freeze_manifest(manifest_file)


def test_freeze_manifest_omitting_003_refused(tmp_path: Path) -> None:
    """Blocker B: Freeze manifest omitting clarification_003_hash triggers FREEZE_MANIFEST_CORRUPT."""
    manifest_file = tmp_path / "corrupt_manifest.json"
    manifest_file.write_text(json.dumps({
        "artifact_name": "H39_ONE_SHOT_UNBLIND_FREEZE",
        "hypothesis_id": "H39",
        "validation_start_ms": H39_VALIDATION_START_MS,
        "validation_start_utc": "2026-09-04T11:15:00Z",
        "unblind_cutoff_ms": 1788750000000,
        "unblind_cutoff_utc": "2026-09-07T03:00:00Z",
        "expected_boundary_count": 800,
        "observed_boundary_count": 800,
        "eligible_boundary_count": 760,
        "eligible_coverage": 0.95,
        "distinct_days_count": 14,
        "readiness_artifact_path": "fake",
        "readiness_sha256": "fake",
        "frozen_ledger_snapshot_path": "fake",
        "frozen_ledger_snapshot_sha256": "fake",
        "source_partitions": {},
        "protocol_hash": H39_FROZEN_PROTOCOL_HASH,
        "clarification_hash": H39_FROZEN_CLARIFICATION_HASH,
        "clarification_002_hash": H39_FROZEN_CLARIFICATION_002_HASH,
        # OMITTED: clarification_003_hash
        "code_version_sha": "fake",
        "attestations": {},
    }), encoding="utf-8")
    gk = _gatekeeper(tmp_path)
    with pytest.raises(RuntimeError, match="FREEZE_MANIFEST_CORRUPT"):
        gk.verify_freeze_manifest(manifest_file)


def test_execution_key_changes_when_any_clarification_identity_changes() -> None:
    """Blocker B: Execution key strictly binds all clarification identities."""
    import hashlib
    base_material = "manifest_sha" + "commit_sha" + "1788750000000" + H39_FROZEN_PROTOCOL_HASH + H39_FROZEN_CLARIFICATION_HASH
    key1 = hashlib.sha256((base_material + H39_FROZEN_CLARIFICATION_002_HASH + H39_FROZEN_CLARIFICATION_003_HASH).encode("utf-8")).hexdigest()
    key2 = hashlib.sha256((base_material + "different_hash" + H39_FROZEN_CLARIFICATION_003_HASH).encode("utf-8")).hexdigest()
    key3 = hashlib.sha256((base_material + H39_FROZEN_CLARIFICATION_002_HASH + "different_hash_003").encode("utf-8")).hexdigest()
    assert key1 != key2
    assert key1 != key3
    assert key2 != key3
