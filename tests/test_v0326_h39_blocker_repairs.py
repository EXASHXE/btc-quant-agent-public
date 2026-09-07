"""Deterministic scientific regression tests for the v0.3.26 H39 blocker repair."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from btc_quant_agent.cli import build_parser
from btc_quant_agent.h39_baseline import causal_wilder_atr_15m
from btc_quant_agent.h39_input import (
    H39_INPUT_CONTRACT_VERSION,
    check_h39_required_input,
)
from btc_quant_agent.h39_statistics import conditional_incremental_ols_hac
from btc_quant_agent.indicators import atr
from btc_quant_agent.microstructure_research import (
    H39_FROZEN_CLARIFICATION_002_HASH,
    H39_FROZEN_CLARIFICATION_003_HASH,
    H39_FROZEN_CLARIFICATION_004_HASH,
    H39_FROZEN_CLARIFICATION_HASH,
    H39_FROZEN_PROTOCOL_HASH,
    H39_PROTOCOL_VERSION_CORRECTED,
    H39_VALIDATION_START_MS,
    H39BlindLedger,
    H39OneShotExecutionRegistry,
    H39OneShotUnblindGatekeeper,
    H39ResearchEngine,
    MicrostructureResearchLoader,
    evaluate_forward_chain_health,
)


def _dgp(n: int = 320, seed: int = 7) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    b1 = rng.normal(size=n)
    b2 = rng.normal(size=n)
    residual = rng.normal(size=n)
    candidate = 0.8 * b1 - 0.3 * b2 + residual
    noise = rng.normal(scale=0.35, size=n)
    for i in range(1, n):
        noise[i] += 0.45 * noise[i - 1]
    baseline = np.column_stack((b1, b2))
    return baseline, candidate, residual, noise


def _test(baseline: np.ndarray, candidate: np.ndarray, y: np.ndarray, ts: np.ndarray):
    return conditional_incremental_ols_hac(
        future_returns=y,
        baseline_controls=baseline,
        candidate=candidate,
        timestamps_ms=ts,
    )


# 1-10: formal conditional-incremental statistical invariants.
def test_01_exact_duplicate_baseline_not_testable() -> None:
    b, _, _, noise = _dgp()
    result = _test(
        b, b[:, 0], b[:, 0] + noise, H39_VALIDATION_START_MS + np.arange(len(b)) * 900_000
    )
    assert result.status == "NOT_TESTABLE" and result.p_value_one_sided == 1.0


def test_02_negative_duplicate_not_testable() -> None:
    b, _, _, noise = _dgp()
    result = _test(
        b, -b[:, 0], b[:, 0] + noise, H39_VALIDATION_START_MS + np.arange(len(b)) * 900_000
    )
    assert result.status == "NOT_TESTABLE"


def test_03_thousand_x_duplicate_not_testable() -> None:
    b, _, _, noise = _dgp()
    result = _test(
        b, 1000.0 * b[:, 0], b[:, 0] + noise, H39_VALIDATION_START_MS + np.arange(len(b)) * 900_000
    )
    assert result.status == "NOT_TESTABLE" and not result.sign_correct


def test_04_baseline_linear_combination_not_testable() -> None:
    b, _, _, noise = _dgp()
    result = _test(
        b,
        2.0 * b[:, 0] - 0.5 * b[:, 1],
        b[:, 0] + noise,
        H39_VALIDATION_START_MS + np.arange(len(b)) * 900_000,
    )
    assert result.status == "NOT_TESTABLE"


def test_05_near_collinear_candidate_fails_closed() -> None:
    b, _, residual, noise = _dgp()
    result = _test(
        b,
        b[:, 0] + 1e-10 * residual,
        b[:, 0] + noise,
        H39_VALIDATION_START_MS + np.arange(len(b)) * 900_000,
    )
    assert result.status == "NOT_TESTABLE"


def test_06_conditional_null_correlated_candidate_does_not_pass() -> None:
    false_positives = 0
    for seed in (11, 19, 31, 43, 59):
        b, candidate, _, noise = _dgp(seed=seed)
        y = 0.002 * b[:, 0] - 0.001 * b[:, 1] + 0.001 * noise
        result = _test(
            b,
            candidate,
            y,
            H39_VALIDATION_START_MS + np.arange(len(b)) * 900_000,
        )
        false_positives += result.p_value_one_sided < 0.05
    assert false_positives <= 1


def test_07_true_incremental_candidate_detected() -> None:
    b, candidate, residual, noise = _dgp(seed=23)
    y = 0.001 * b[:, 0] + 0.004 * residual + 0.0007 * noise
    result = _test(b, candidate, y, H39_VALIDATION_START_MS + np.arange(len(b)) * 900_000)
    assert result.testable and result.p_value_one_sided < 0.01 and result.effect_estimate > 0


def test_08_positive_scaling_invariance() -> None:
    b, candidate, residual, noise = _dgp(seed=29)
    y = 0.001 * b[:, 0] + 0.003 * residual + 0.0007 * noise
    ts = H39_VALIDATION_START_MS + np.arange(len(b)) * 900_000
    results = [_test(b, scale * candidate, y, ts) for scale in (0.001, 1.0, 10.0, 1000.0)]
    results.extend(
        _test(b * np.array([scale, 1.0 / scale]), candidate, y, ts) for scale in (0.001, 1000.0)
    )
    assert all(item.testable for item in results)
    assert (
        max(item.p_value_one_sided for item in results)
        - min(item.p_value_one_sided for item in results)
        < 1e-12
    )
    assert (
        max(item.effect_estimate for item in results)
        - min(item.effect_estimate for item in results)
        < 1e-12
    )


def test_09_constant_candidate_not_testable() -> None:
    b, _, _, noise = _dgp()
    result = _test(b, np.ones(len(b)), noise, H39_VALIDATION_START_MS + np.arange(len(b)) * 900_000)
    assert result.reason == "CONSTANT_CANDIDATE"


def test_10_zero_variance_residual_not_testable() -> None:
    b, _, _, noise = _dgp()
    result = _test(
        b, b[:, 0] + 0.0 * noise, noise, H39_VALIDATION_START_MS + np.arange(len(b)) * 900_000
    )
    assert result.status == "NOT_TESTABLE"


def _row(slot: int = H39_VALIDATION_START_MS) -> dict[str, object]:
    partition = "microstructure-2026-09-04.sqlite3"
    return {
        "decision_close_ms": slot,
        "slot_utc": datetime.fromtimestamp(slot / 1000, UTC).isoformat(),
        "eligible": 1,
        "rejection_reason": None,
        "m1_trade_imbalance_5m": 0.1,
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
        "decision_close_price": 50_000.0,
        "book_sample_count_15m": 180,
        "trade_count_15m": 30,
        "feature_window_start_ms": slot - 900_000,
        "feature_window_end_ms": slot,
        "reference_time_ms": slot + 60_000,
        "target_60m_ms": slot + 3_600_000,
        "target_240m_ms": slot + 14_400_000,
        "source_partitions": json.dumps([partition]),
        "source_partition_hashes": json.dumps({partition: "abc"}),
        "protocol_hash": H39_FROZEN_PROTOCOL_HASH,
        "clarification_hash": H39_FROZEN_CLARIFICATION_HASH,
        "code_version_sha": "synthetic",
        "input_contract_version": H39_INPUT_CONTRACT_VERSION,
    }


# 11-16: label-free input and maturity contract.
def test_11_missing_atr_excluded() -> None:
    row = _row()
    row["trailing_atr_15m"] = None
    assert not check_h39_required_input(row).formal_test_ready


def test_12_missing_baseline_return_excluded() -> None:
    row = _row()
    row["trailing_return_60m"] = None
    assert not check_h39_required_input(row).formal_test_ready


def test_13_missing_required_baseline_field_excluded() -> None:
    row = _row()
    row["decision_close_price"] = None
    assert not check_h39_required_input(row).baseline_complete


def test_14_many_rows_all_baseline_missing_not_mature(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import btc_quant_agent.microstructure_research as module

    monkeypatch.setattr(module, "H39_MINIMUM_ELIGIBLE_OBSERVATIONS", 2)
    monkeypatch.setattr(module, "H39_MINIMUM_VALIDATION_DAYS", 1)
    monkeypatch.setattr(module, "H39_MINIMUM_COVERAGE_RATIO", 0.0)
    ledger = H39BlindLedger(tmp_path / "ledger.sqlite3")
    rows = [_row(H39_VALIDATION_START_MS + i * 900_000) for i in range(3)]
    for row in rows:
        row["trailing_atr_15m"] = None
    ledger.ingest_slots(rows)
    summary = ledger.get_summary(as_of_ms=H39_VALIDATION_START_MS + 2 * 900_000)
    assert summary["microstructure_eligible_boundary_count"] == 3
    assert summary["formal_test_ready_boundary_count"] == 0
    assert summary["maturity_achieved"] is False


def test_15_valid_full_input_is_ready() -> None:
    assert check_h39_required_input(_row()).formal_test_ready


def test_16_malformed_timestamp_is_excluded() -> None:
    row = _row()
    row["reference_time_ms"] = int(row["reference_time_ms"]) + 1
    assert "TIMING_CONTRACT_INVALID" in check_h39_required_input(row).reasons


def _partition(
    path: Path, start: int, end: int, *, book_step: int = 5_000, trade_step: int = 30_000
) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript("""
        CREATE TABLE agg_trades(aggregate_trade_id INTEGER PRIMARY KEY,event_time_ms INTEGER,transaction_time_ms INTEGER,receive_time_ms INTEGER,receive_monotonic_ns INTEGER,price REAL,quantity REAL,buyer_is_maker INTEGER,aggressive_side TEXT,payload_hash TEXT);
        CREATE TABLE book_samples(event_time_ms INTEGER,final_update_id INTEGER,receive_time_ms INTEGER,spread_bps REAL,top1_imbalance REAL,top5_imbalance REAL,top20_imbalance REAL,microprice REAL,ofi REAL,PRIMARY KEY(event_time_ms,final_update_id));
        CREATE TABLE gaps(id INTEGER PRIMARY KEY,start_ms INTEGER,end_ms INTEGER,kind TEXT,detail TEXT);
        """)
        for stamp in range(start + book_step, end + 1, book_step):
            conn.execute(
                "INSERT INTO book_samples VALUES(?,?,?,?,?,?,?,?,?)",
                (stamp, stamp, stamp, 1.0, 0.1, 0.2, 0.3, 50000.0, 1.0),
            )
        for stamp in range(start + trade_step, end + 1, trade_step):
            conn.execute(
                "INSERT INTO agg_trades VALUES(?,?,?,?,?,?,?,?,?,?)",
                (stamp, stamp, stamp, stamp, 0, 50000.0, 1.0, 0, "BUY", "h"),
            )


# 17-21: complete window, including physical tail and partition boundaries.
def test_17_head_gap_rejected(tmp_path: Path) -> None:
    slot = H39_VALIDATION_START_MS
    path = tmp_path / "p.sqlite3"
    _partition(path, slot - 800_000, slot)
    assert not MicrostructureResearchLoader(path).check_slot_eligibility(slot)[0]


def test_18_internal_gap_rejected(tmp_path: Path) -> None:
    slot = H39_VALIDATION_START_MS
    path = tmp_path / "p.sqlite3"
    _partition(path, slot - 900_000, slot)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "DELETE FROM book_samples WHERE event_time_ms BETWEEN ? AND ?",
            (slot - 500_000, slot - 450_000),
        )
    assert not MicrostructureResearchLoader(path).check_slot_eligibility(slot)[0]


def test_19_tail_gap_rejected(tmp_path: Path) -> None:
    slot = H39_VALIDATION_START_MS
    path = tmp_path / "p.sqlite3"
    _partition(path, slot - 900_000, slot - 300_000)
    assert not MicrostructureResearchLoader(path).check_slot_eligibility(slot)[0]


def test_20_complete_window_accepted(tmp_path: Path) -> None:
    slot = H39_VALIDATION_START_MS
    path = tmp_path / "p.sqlite3"
    _partition(path, slot - 900_000, slot)
    assert MicrostructureResearchLoader(path).check_slot_eligibility(slot) == (True, None)


def test_21_partition_boundary_requires_both_partitions(tmp_path: Path) -> None:
    slot = H39_VALIDATION_START_MS
    prior = tmp_path / "prior.sqlite3"
    current = tmp_path / "current.sqlite3"
    _partition(prior, slot - 900_000, slot - 450_000)
    _partition(current, slot - 450_000, slot)
    assert MicrostructureResearchLoader(current, [prior]).check_slot_eligibility(slot) == (
        True,
        None,
    )
    assert not MicrostructureResearchLoader(current).check_slot_eligibility(slot)[0]


def _health_root(tmp_path: Path, book_ms: int | None, trade_ms: int | None) -> Path:
    root = tmp_path / "micro"
    root.mkdir()
    path = root / "microstructure-2026-09-07.sqlite3"
    _partition(path, 0, 0)
    with sqlite3.connect(path) as conn:
        if book_ms is not None:
            conn.execute(
                "INSERT INTO book_samples VALUES(?,?,?,?,?,?,?,?,?)",
                (book_ms, 1, book_ms, 1.0, 0.1, 0.2, 0.3, 1.0, 1.0),
            )
        if trade_ms is not None:
            conn.execute(
                "INSERT INTO agg_trades VALUES(?,?,?,?,?,?,?,?,?,?)",
                (1, trade_ms, trade_ms, trade_ms, 0, 1.0, 1.0, 0, "BUY", "h"),
            )
    return root


# 22-26: book and trade health are independent and jointly required.
@pytest.mark.parametrize(
    ("case", "book_delta", "trade_delta", "expected"),
    [
        (22, 100, 100, "HEALTHY"),
        (23, 5_000_000, 100, "STALE"),
        (24, 100, 5_000_000, "STALE"),
        (25, None, 100, "MISSING"),
        (26, 100, None, "MISSING"),
    ],
)
def test_22_to_26_dual_stream_health(
    tmp_path: Path, case: int, book_delta: int | None, trade_delta: int | None, expected: str
) -> None:
    del case
    now = 10_000_000
    root = _health_root(
        tmp_path,
        None if book_delta is None else now - book_delta,
        None if trade_delta is None else now - trade_delta,
    )
    health = evaluate_forward_chain_health(
        microstructure_root=root, now_ms=now, microstructure_stale_threshold_seconds=3600
    )
    assert health["microstructure_chain"]["status"] == expected
    if expected != "HEALTHY":
        assert health["microstructure_chain"]["overall_research_health"] != "HEALTHY"


def _snapshot(tmp_path: Path, *, valid: bool) -> tuple[Path, dict[str, object]]:
    ledger = H39BlindLedger(tmp_path / "snapshot.sqlite3")
    row = _row()
    if not valid:
        row["trailing_atr_15m"] = None
    ledger.ingest_slot(row)
    manifest = {
        "unblind_cutoff_ms": H39_VALIDATION_START_MS,
        "unblind_cutoff_utc": datetime.fromtimestamp(
            H39_VALIDATION_START_MS / 1000, UTC
        ).isoformat(),
        "frozen_ledger_snapshot_path": str(ledger.db_path),
        "frozen_ledger_snapshot_sha256": "synthetic",
        "snapshot_eligible_row_count": 1,
        "protocol_hash": H39_FROZEN_PROTOCOL_HASH,
        "clarification_hash": H39_FROZEN_CLARIFICATION_HASH,
        "clarification_002_hash": H39_FROZEN_CLARIFICATION_002_HASH,
        "clarification_003_hash": H39_FROZEN_CLARIFICATION_003_HASH,
        "clarification_004_hash": H39_FROZEN_CLARIFICATION_004_HASH,
        "corrected_protocol_version": H39_PROTOCOL_VERSION_CORRECTED,
        "corrected_evaluator_version": "H39_CONDITIONAL_OLS_HAC_V1",
        "input_contract_version": H39_INPUT_CONTRACT_VERSION,
        "readiness_sha256": "synthetic",
    }
    freeze = tmp_path / "freeze.json"
    freeze.write_text("{}", encoding="utf-8")
    return freeze, manifest


# 27-30: precheck is retryable; post-claim state remains one-shot.
def test_27_precheck_failure_does_not_consume_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import btc_quant_agent.microstructure_research as module

    monkeypatch.setattr(module, "H39_MINIMUM_ELIGIBLE_OBSERVATIONS", 1)
    freeze, manifest = _snapshot(tmp_path, valid=False)
    gate = H39OneShotUnblindGatekeeper(registry_path=tmp_path / "registry.sqlite3")
    with (
        patch.object(gate, "verify_freeze_manifest", return_value=manifest),
        patch.object(
            module, "verify_committed_freeze_package", return_value={"freeze_commit_sha": "a" * 40}
        ),pytest.raises(RuntimeError, match="BLIND_PRECHECK_FAILED")
    ):
        gate.execute_one_shot_unblind(freeze, output_dir=tmp_path / "out")
    with sqlite3.connect(gate.registry.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM h39_one_shot_executions").fetchone()[0] == 0

    # Repair only the synthetic pre-label input. The same invocation can now
    # reach the label stage, proving that the first refusal did not burn the key.
    with sqlite3.connect(manifest["frozen_ledger_snapshot_path"]) as conn:
        conn.execute(
            "UPDATE h39_blind_validation_ledger SET trailing_atr_15m = 25.0 "
            "WHERE decision_close_ms = ?",
            (H39_VALIDATION_START_MS,),
        )
    with (
        patch.object(gate, "verify_freeze_manifest", return_value=manifest),
        patch.object(
            module,
            "verify_committed_freeze_package",
            return_value={"freeze_commit_sha": "a" * 40},
        ),
        patch.object(
            H39ResearchEngine,
            "get_canonical_1m_candles",
            side_effect=RuntimeError("LABEL_STAGE_REACHED"),
        ),pytest.raises(RuntimeError, match="LABEL_STAGE_REACHED")
    ):
        gate.execute_one_shot_unblind(freeze, output_dir=tmp_path / "retry")
    with sqlite3.connect(gate.registry.db_path) as conn:
        assert conn.execute("SELECT state FROM h39_one_shot_executions").fetchone()[0] == "STARTED"


def test_28_completed_execution_key_cannot_rerun(tmp_path: Path) -> None:
    registry = H39OneShotExecutionRegistry(tmp_path / "registry.sqlite3")
    kwargs = {
        "execution_key": "k",
        "freeze_manifest_sha256": "f",
        "freeze_commit_sha": "c",
        "unblind_cutoff_ms": 1,
        "protocol_hash": "p",
        "clarification_hash": "q",
        "executing_git_sha": "g",
    }
    registry.reserve_execution(**kwargs)
    registry.complete_execution("k", "r")
    with pytest.raises(RuntimeError, match="H39_ONE_SHOT_ALREADY_CONSUMED"):
        registry.reserve_execution(**kwargs)


def test_29_started_crash_state_remains_consumed(tmp_path: Path) -> None:
    registry = H39OneShotExecutionRegistry(tmp_path / "registry.sqlite3")
    kwargs = {
        "execution_key": "k",
        "freeze_manifest_sha256": "f",
        "freeze_commit_sha": "c",
        "unblind_cutoff_ms": 1,
        "protocol_hash": "p",
        "clarification_hash": "q",
        "executing_git_sha": "g",
    }
    registry.reserve_execution(**kwargs)
    assert registry.get_execution("k")["state"] == "STARTED"
    with pytest.raises(RuntimeError, match="H39_ONE_SHOT_ALREADY_CONSUMED"):
        registry.reserve_execution(**kwargs)


def test_30_label_loader_never_runs_before_blind_precheck(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import btc_quant_agent.microstructure_research as module

    monkeypatch.setattr(module, "H39_MINIMUM_ELIGIBLE_OBSERVATIONS", 1)
    freeze, manifest = _snapshot(tmp_path, valid=False)
    gate = H39OneShotUnblindGatekeeper(registry_path=tmp_path / "registry.sqlite3")
    with (
        patch.object(gate, "verify_freeze_manifest", return_value=manifest),
        patch.object(
            module, "verify_committed_freeze_package", return_value={"freeze_commit_sha": "a" * 40}
        ),
        patch.object(H39ResearchEngine, "get_canonical_1m_candles") as labels,
        pytest.raises(RuntimeError, match="BLIND_PRECHECK_FAILED"),
    ):
        gate.execute_one_shot_unblind(freeze, output_dir=tmp_path / "out")
    labels.assert_not_called()


def test_31_neutral_atr_matches_wilder_definition() -> None:
    slot = H39_VALIDATION_START_MS
    first = slot - 500 * 900_000
    candles: dict[int, dict[str, float]] = {}
    bar_highs: list[float] = []
    bar_lows: list[float] = []
    bar_closes: list[float] = []
    for bar_index in range(500):
        bar_open = first + bar_index * 900_000
        children = []
        for minute in range(15):
            close = 50_000.0 + bar_index * 2.0 + minute * 0.1
            child = {"open": close - 0.1, "high": close + 2.0, "low": close - 1.5, "close": close}
            candles[bar_open + minute * 60_000] = child
            children.append(child)
        bar_highs.append(max(item["high"] for item in children))
        bar_lows.append(min(item["low"] for item in children))
        bar_closes.append(children[-1]["close"])
    expected = atr(bar_highs, bar_lows, bar_closes, 14)[-1]
    assert causal_wilder_atr_15m(candles, slot) == pytest.approx(expected)


def test_32_neutral_atr_fails_closed_on_missing_child() -> None:
    slot = H39_VALIDATION_START_MS
    first = slot - 500 * 900_000
    candles = {first + i * 60_000: {"high": 2.0, "low": 1.0, "close": 1.5} for i in range(500 * 15)}
    candles.pop(first + 123 * 60_000)
    assert causal_wilder_atr_15m(candles, slot) is None


def test_33_corrected_cli_defaults_do_not_overwrite_v0325_artifacts() -> None:
    parser = build_parser()
    freeze_args = parser.parse_args(["h39", "freeze-cutoff"])
    unblind_args = parser.parse_args(
        ["h39", "one-shot-unblind", "--freeze-manifest", "synthetic.json"]
    )
    assert freeze_args.output_path.startswith("deliverables/v0.3.26/")
    assert unblind_args.output_dir == "deliverables/v0.3.26"
