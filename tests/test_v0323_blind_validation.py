from __future__ import annotations

import hashlib
import inspect
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from btc_quant_agent.cli import build_parser
from btc_quant_agent.microstructure_research import (
    FORMAL_FEATURE_IDS,
    H38_TERMINAL_FIRST_BREACH_MS,
    H39_CLARIFICATION_SHA,
    H39_FROZEN_CLARIFICATION_HASH,
    H39_FROZEN_PROTOCOL_HASH,
    H39_HYPOTHESIS_ID,
    H39_MINIMUM_COVERAGE_RATIO,
    H39_MINIMUM_ELIGIBLE_OBSERVATIONS,
    H39_MINIMUM_VALIDATION_DAYS,
    H39_PROTOCOL_CLARIFICATION_SHA,
    H39_PROTOCOL_FREEZE_SHA,
    H39_PROTOCOL_PATH,
    H39_VALIDATION_START_MS,
    H39_VALIDATION_START_UTC,
    PREDEFINED_FEATURE_SIGNS,
    REFUSED_VALIDATION_NOT_MATURE,
    H39BlindLedger,
    H39FeatureRow,
    H39Observation,
    H39OutcomeRow,
    H39ResearchEngine,
    MicrostructureResearchLoader,
    evaluate_feature_hypotheses,
)


def _make_dummy_valid_row(
    slot_ms: int = H39_VALIDATION_START_MS,
    eligible: bool = True,
    rejection_reason: str | None = None,
    m1: float = 0.1,
) -> dict[str, Any]:
    ref_time = slot_ms + 60_000
    t60 = ref_time + 59 * 60_000
    t240 = ref_time + 239 * 60_000
    return {
        "decision_close_ms": slot_ms,
        "decision_close_utc": "2026-09-04T11:15:00Z",
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
        "source_partition": "microstructure-2026-09-04.sqlite3",
        "source_partition_sha256": "dummy_partition_sha",
        "code_git_sha": "dummy_code_sha",
        "protocol_hash": H39_FROZEN_PROTOCOL_HASH,
        "clarification_hash": H39_FROZEN_CLARIFICATION_HASH,
    }


def _make_dummy_valid_feature_row(
    slot_ms: int = H39_VALIDATION_START_MS,
    eligible: bool = True,
    rejection_reason: str | None = None,
    m1: float = 0.1,
) -> H39FeatureRow:
    return H39FeatureRow(
        slot_ms=slot_ms,
        slot_utc="2026-09-04T11:15:00Z",
        m1_trade_imbalance_5m=m1,
        m2_trade_imbalance_15m=0.2,
        m3_ofi_5m=0.3,
        m4_top5_depth_imbalance_5m=0.4,
        m5_top20_depth_imbalance_5m=0.5,
        m6_microprice_deviation_1m=0.6,
        m7_pressure_agreement=0.7,
        m8_pressure_divergence=0.8,
        eligible=eligible,
        rejection_reason=rejection_reason,
    )


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


def test_post_start_only_validation_ledger_rows(tmp_path: Path) -> None:
    ledger_path = tmp_path / "test_ledger.sqlite3"
    ledger = H39BlindLedger(ledger_path)

    # Pre-start slot must be rejected
    pre_start_row = _make_dummy_valid_row(slot_ms=H39_VALIDATION_START_MS - 900_000)
    with pytest.raises(ValueError, match="Ledger accepts post-start validation slots only"):
        ledger.append_slot(pre_start_row)

    # Post-start slot at exact validation start must succeed
    post_start_row = _make_dummy_valid_row(slot_ms=H39_VALIDATION_START_MS)
    status = ledger.append_slot(post_start_row)
    assert status == "INSERTED"

    # Future post-start slot must succeed
    future_row = _make_dummy_valid_row(slot_ms=H39_VALIDATION_START_MS + 900_000)
    status2 = ledger.append_slot(future_row)
    assert status2 == "INSERTED"


def test_feature_window_and_receive_time_causality(tmp_path: Path) -> None:
    db_path = tmp_path / "causal_test.sqlite3"
    _create_test_partition(db_path)

    slot_ms = H39_VALIDATION_START_MS
    t_15m = slot_ms - 15 * 60_000

    conn = sqlite3.connect(db_path)
    # 1. Book samples continuity
    cur_t = t_15m + 1000
    uid = 1
    while cur_t <= slot_ms:
        conn.execute(
            """INSERT INTO book_samples VALUES(?,?,?,?,?,?,?,?,?)""",
            (cur_t, uid, cur_t, 1.0, 0.2, 0.3, 0.4, 70000.0, 10.0),
        )
        cur_t += 5000
        uid += 1

    # 2. Trades:
    # In-window valid trade: event_time in 5m, receive_time <= slot_ms
    conn.execute(
        """INSERT INTO agg_trades VALUES(1, ?, ?, ?, 0, 70000.0, 1.0, 0, 'BUY', 'h1')""",
        (slot_ms - 1000, slot_ms - 1000, slot_ms - 500),
    )
    # Late-arriving trade: event_time in 5m, but receive_time_ms > slot_ms (MUST BE EXCLUDED)
    conn.execute(
        """INSERT INTO agg_trades VALUES(2, ?, ?, ?, 0, 70000.0, 10.0, 0, 'BUY', 'h2')""",
        (slot_ms - 2000, slot_ms - 2000, slot_ms + 1000),
    )
    # Future trade: event_time > slot_ms (MUST BE EXCLUDED)
    conn.execute(
        """INSERT INTO agg_trades VALUES(3, ?, ?, ?, 0, 70000.0, 100.0, 0, 'SELL', 'h3')""",
        (slot_ms + 500, slot_ms + 500, slot_ms + 500),
    )
    conn.commit()
    conn.close()

    loader = MicrostructureResearchLoader(db_path)
    feat = loader.compute_features(slot_ms)

    # If late-arriving trade (qty=10) or future trade (qty=100) leaked, m1 would be different.
    # Only valid trade 1 (BUY, qty 1.0) is present -> buy_notional = 70000, sell_notional = 0 -> m1 = 1.0
    assert feat.m1_trade_imbalance_5m == 1.0
    assert feat.trade_count_15m == 1


def test_schedule_metadata_reference_and_targets(tmp_path: Path) -> None:
    ledger_path = tmp_path / "timing_test.sqlite3"
    ledger = H39BlindLedger(ledger_path)

    slot_ms = H39_VALIDATION_START_MS
    row = _make_dummy_valid_row(slot_ms=slot_ms)

    # Correct timing: ref = slot + 60s, 60m = ref + 59m, 240m = ref + 239m
    assert row["reference_time_ms"] == slot_ms + 60_000
    assert row["target_60m_ms"] == slot_ms + 60_000 + 59 * 60_000
    assert row["target_240m_ms"] == slot_ms + 60_000 + 239 * 60_000

    # Bad reference time
    bad_ref = dict(row)
    bad_ref["reference_time_ms"] = slot_ms  # candle starting at decision close is prohibited
    with pytest.raises(ValueError, match="Invalid reference timing"):
        ledger.append_slot(bad_ref)

    # Bad 60m target time
    bad_60 = dict(row)
    bad_60["target_60m_ms"] = row["reference_time_ms"] + 60 * 60_000  # off by 1m
    with pytest.raises(ValueError, match="Invalid 60m target timing"):
        ledger.append_slot(bad_60)

    # Bad 240m target time
    bad_240 = dict(row)
    bad_240["target_240m_ms"] = row["reference_time_ms"] + 240 * 60_000
    with pytest.raises(ValueError, match="Invalid 240m target timing"):
        ledger.append_slot(bad_240)


def test_frozen_m1_to_m8_universe_unchanged() -> None:
    expected_m1_m8 = (
        "M1_TRADE_NOTIONAL_IMBALANCE_5M",
        "M2_TRADE_NOTIONAL_IMBALANCE_15M",
        "M3_OFI_5M",
        "M4_TOP5_DEPTH_IMBALANCE_5M",
        "M5_TOP20_DEPTH_IMBALANCE_5M",
        "M6_MICROPRICE_DEVIATION_1M",
        "M7_PRESSURE_AGREEMENT_SCORE",
        "M8_PRESSURE_DIVERGENCE_SCORE",
    )
    assert FORMAL_FEATURE_IDS == expected_m1_m8
    assert len(FORMAL_FEATURE_IDS) == 8
    for fid in expected_m1_m8:
        assert PREDEFINED_FEATURE_SIGNS[fid] == 1

    assert H39_HYPOTHESIS_ID == "H39_MICROSTRUCTURE_DIRECTIONAL_INFORMATION"


def test_frozen_baseline_and_review_lineage() -> None:
    # Lineage constants
    assert H39_PROTOCOL_FREEZE_SHA == "0eecd8833675c664c42f5e62d89663d7a10ed5fa"
    assert H39_CLARIFICATION_SHA == "2d1ccecc11dc231ffa41cdb1b5a9ea693abccc59"
    assert H39_PROTOCOL_CLARIFICATION_SHA == H39_CLARIFICATION_SHA
    assert H39_VALIDATION_START_MS == 1788520500000
    assert H39_VALIDATION_START_UTC == "2026-09-04T11:15:00Z"


def test_protocol_and_clarification_hash_pinning(tmp_path: Path) -> None:
    # 1. Check actual file hashes
    protocol_path = Path(H39_PROTOCOL_PATH)
    assert protocol_path.exists()
    p_bytes = protocol_path.read_bytes()
    assert hashlib.sha256(p_bytes).hexdigest() == H39_FROZEN_PROTOCOL_HASH

    clarification_path = Path("deliverables/v0.3.22/H39_PROTOCOL_CLARIFICATION_001.json")
    assert clarification_path.exists()
    c_bytes = clarification_path.read_bytes()
    assert hashlib.sha256(c_bytes).hexdigest() == H39_FROZEN_CLARIFICATION_HASH

    # 2. Check ledger rejects wrong protocol or clarification hash
    ledger_path = tmp_path / "hash_test.sqlite3"
    ledger = H39BlindLedger(ledger_path)

    row = _make_dummy_valid_row()
    bad_p = dict(row)
    bad_p["protocol_hash"] = "wrong_hash"
    with pytest.raises(ValueError, match="Protocol hash mismatch"):
        ledger.append_slot(bad_p)

    bad_c = dict(row)
    bad_c["clarification_hash"] = "wrong_hash"
    with pytest.raises(ValueError, match="Clarification hash mismatch"):
        ledger.append_slot(bad_c)


def test_raw_forward_db_read_only_behavior(tmp_path: Path) -> None:
    db_path = tmp_path / "ro_test.sqlite3"
    _create_test_partition(db_path)

    loader = MicrostructureResearchLoader(db_path)
    with loader.connect_readonly() as conn:
        # Read succeeds
        r = conn.execute("SELECT COUNT(*) FROM agg_trades").fetchone()
        assert r[0] == 0

        # Writes fail
        with pytest.raises(sqlite3.OperationalError, match="readonly|read-only"):
            conn.execute("INSERT INTO agg_trades (aggregate_trade_id) VALUES (999)")

        with pytest.raises(sqlite3.OperationalError, match="readonly|read-only"):
            conn.execute("DELETE FROM agg_trades")


def test_idempotent_duplicate_insertion_and_conflicting_failure(tmp_path: Path) -> None:
    ledger_path = tmp_path / "idem_test.sqlite3"
    ledger = H39BlindLedger(ledger_path)

    slot_ms = H39_VALIDATION_START_MS
    row1 = _make_dummy_valid_row(slot_ms=slot_ms, m1=0.25)

    # First insert
    res1 = ledger.append_slot(row1)
    assert res1 == "INSERTED"

    # Idempotent re-insert
    res2 = ledger.append_slot(row1)
    assert res2 == "DUPLICATE_IDEMPOTENT"

    manifest = ledger.get_manifest()
    assert manifest["total_slots_recorded"] == 1

    # Conflicting feature value insertion
    conflicting_row = dict(row1)
    conflicting_row["m1_trade_imbalance_5m"] = 0.99  # materially different
    with pytest.raises(ValueError, match="Conflicting duplicate slot evidence"):
        ledger.append_slot(conflicting_row)

    # Manifest row count still 1
    manifest_after = ledger.get_manifest()
    assert manifest_after["total_slots_recorded"] == 1


def test_missing_expected_slots_remain_in_coverage_denominator(tmp_path: Path) -> None:
    ledger_path = tmp_path / "coverage_test.sqlite3"
    ledger = H39BlindLedger(ledger_path)

    # 10 slots elapsed since validation start (i.e. slots 0 through 9 -> 10 slots total)
    now_ms = H39_VALIDATION_START_MS + 9 * 900_000

    # With empty ledger, expected slots = 10, observed = 0, coverage = 0.0
    status_empty = ledger.get_status(now_ms=now_ms)
    assert status_empty["expected_boundary_count"] == 10
    assert status_empty["observed_boundary_count"] == 0
    assert status_empty["eligible_boundary_count"] == 0
    assert status_empty["coverage_ratio"] == 0.0

    # Insert 2 eligible slots out of 10 expected
    ledger.append_slot(_make_dummy_valid_row(slot_ms=H39_VALIDATION_START_MS))
    ledger.append_slot(_make_dummy_valid_row(slot_ms=H39_VALIDATION_START_MS + 900_000))

    status_2 = ledger.get_status(now_ms=now_ms)
    assert status_2["expected_boundary_count"] == 10
    assert status_2["observed_boundary_count"] == 2
    assert status_2["eligible_boundary_count"] == 2
    # Missing 8 slots remain in denominator!
    assert pytest.approx(status_2["coverage_ratio"], 1e-4) == 2.0 / 10.0


def test_fail_closed_real_validation_outcome_refusal() -> None:
    # Synthetic observation with post-start slot
    f_row = H39FeatureRow(
        slot_ms=H39_VALIDATION_START_MS + 900_000,
        slot_utc="2026-09-04T11:30:00Z",
        m1_trade_imbalance_5m=0.1,
        m2_trade_imbalance_15m=0.1,
        m3_ofi_5m=0.1,
        m4_top5_depth_imbalance_5m=0.1,
        m5_top20_depth_imbalance_5m=0.1,
        m6_microprice_deviation_1m=0.1,
        m7_pressure_agreement=0.1,
        m8_pressure_divergence=0.1,
        eligible=True,
        rejection_reason=None,
    )
    o_row = H39OutcomeRow(
        slot_ms=H39_VALIDATION_START_MS + 900_000,
        reference_price=70000.0,
        reference_time_ms=H39_VALIDATION_START_MS + 960_000,
        future_close_60m=70100.0,
        return_60m=0.0014,
        future_close_240m=70200.0,
        return_240m=0.0028,
        trailing_return_15m=0.0005,
        trailing_return_60m=0.0010,
        trailing_atr_15m=50.0,
        trailing_atr_ratio_15m=0.0007,
        decision_close_price=70000.0,
        decision_close_ms=H39_VALIDATION_START_MS + 900_000,
    )
    obs = [H39Observation(feature_row=f_row, outcome_row=o_row)]

    # Attempting to evaluate post-start validation MUST unconditionally raise RuntimeError
    with pytest.raises(RuntimeError, match=REFUSED_VALIDATION_NOT_MATURE):
        evaluate_feature_hypotheses(obs, horizon="60m")

    # Calling with removed allow_unblind parameter MUST raise TypeError
    with pytest.raises(TypeError, match="unexpected keyword argument 'allow_unblind'"):
        evaluate_feature_hypotheses(obs, horizon="60m", allow_unblind=False)  # type: ignore[call-arg]

    with pytest.raises(TypeError, match="unexpected keyword argument 'allow_unblind'"):
        evaluate_feature_hypotheses(obs, horizon="60m", allow_unblind=True)  # type: ignore[call-arg]


def test_unconditional_post_start_validation_refusal() -> None:
    # Section 6.A: Real/synthetic observation whose slot_ms >= H39_VALIDATION_START_MS
    # must always raise REFUSED_VALIDATION_NOT_MATURE through evaluate_feature_hypotheses
    f_post = _make_dummy_valid_feature_row(slot_ms=H39_VALIDATION_START_MS + 900_000)
    o_post = H39OutcomeRow(
        slot_ms=H39_VALIDATION_START_MS + 900_000,
        reference_price=70000.0,
        reference_time_ms=H39_VALIDATION_START_MS + 960_000,
        future_close_60m=70100.0,
        return_60m=0.0014,
        future_close_240m=70200.0,
        return_240m=0.0028,
        trailing_return_15m=0.0005,
        trailing_return_60m=0.0010,
        trailing_atr_15m=50.0,
        trailing_atr_ratio_15m=0.0007,
        decision_close_price=70000.0,
        decision_close_ms=H39_VALIDATION_START_MS + 1800_000,
    )
    obs_post = [H39Observation(feature_row=f_post, outcome_row=o_post)]

    # 60m horizon refusal
    with pytest.raises(RuntimeError, match=REFUSED_VALIDATION_NOT_MATURE):
        evaluate_feature_hypotheses(obs_post, horizon="60m")

    # 240m horizon refusal
    with pytest.raises(RuntimeError, match=REFUSED_VALIDATION_NOT_MATURE):
        evaluate_feature_hypotheses(obs_post, horizon="240m")

    # Mixed pre-start and post-start rows must also fail closed
    f_pre = _make_dummy_valid_feature_row(slot_ms=H39_VALIDATION_START_MS - 900_000)
    obs_mixed = [
        H39Observation(feature_row=f_pre, outcome_row=o_post),
        H39Observation(feature_row=f_post, outcome_row=o_post),
    ]
    with pytest.raises(RuntimeError, match=REFUSED_VALIDATION_NOT_MATURE):
        evaluate_feature_hypotheses(obs_mixed, horizon="60m")


def test_allow_unblind_parameter_removed_and_rejected() -> None:
    # Section 6.B: Old bypass is completely impossible
    sig = inspect.signature(evaluate_feature_hypotheses)
    assert "allow_unblind" not in sig.parameters

    f_row = _make_dummy_valid_feature_row(slot_ms=H39_VALIDATION_START_MS)
    o_row = H39OutcomeRow(
        slot_ms=H39_VALIDATION_START_MS,
        reference_price=70000.0,
        reference_time_ms=H39_VALIDATION_START_MS + 960_000,
        future_close_60m=70100.0,
        return_60m=0.0014,
        future_close_240m=70200.0,
        return_240m=0.0028,
        trailing_return_15m=0.0005,
        trailing_return_60m=0.0010,
        trailing_atr_15m=50.0,
        trailing_atr_ratio_15m=0.0007,
        decision_close_price=70000.0,
        decision_close_ms=H39_VALIDATION_START_MS + 900_000,
    )
    obs = [H39Observation(feature_row=f_row, outcome_row=o_row)]

    # Attempting to use allow_unblind=True as authorization path raises TypeError
    with pytest.raises(TypeError) as excinfo:
        evaluate_feature_hypotheses(obs, allow_unblind=True)  # type: ignore[call-arg]
    assert "allow_unblind" in str(excinfo.value)


def test_pre_start_development_evaluation_functional() -> None:
    # Section 6.C: Pre-validation/development observations remain analyzable
    pre_f = H39FeatureRow(
        slot_ms=H39_VALIDATION_START_MS - 900_000,
        slot_utc="2026-09-04T11:00:00Z",
        m1_trade_imbalance_5m=0.1,
        m2_trade_imbalance_15m=0.1,
        m3_ofi_5m=0.1,
        m4_top5_depth_imbalance_5m=0.1,
        m5_top20_depth_imbalance_5m=0.1,
        m6_microprice_deviation_1m=0.1,
        m7_pressure_agreement=0.1,
        m8_pressure_divergence=0.1,
        eligible=True,
        rejection_reason=None,
    )
    o_row = H39OutcomeRow(
        slot_ms=H39_VALIDATION_START_MS - 900_000,
        reference_price=70000.0,
        reference_time_ms=H39_VALIDATION_START_MS - 840_000,
        future_close_60m=70100.0,
        return_60m=0.0014,
        future_close_240m=70200.0,
        return_240m=0.0028,
        trailing_return_15m=0.0005,
        trailing_return_60m=0.0010,
        trailing_atr_15m=50.0,
        trailing_atr_ratio_15m=0.0007,
        decision_close_price=70000.0,
        decision_close_ms=H39_VALIDATION_START_MS,
    )
    pre_obs = [H39Observation(feature_row=pre_f, outcome_row=o_row)]

    # 60m evaluation succeeds
    res_60m = evaluate_feature_hypotheses(pre_obs, horizon="60m")
    assert isinstance(res_60m, dict)
    assert len(res_60m) == len(FORMAL_FEATURE_IDS)
    for fid in FORMAL_FEATURE_IDS:
        assert fid in res_60m

    # 240m evaluation succeeds
    res_240m = evaluate_feature_hypotheses(pre_obs, horizon="240m")
    assert isinstance(res_240m, dict)
    assert len(res_240m) == len(FORMAL_FEATURE_IDS)


def test_readiness_does_not_execute_statistics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Section 6.D: Both immature and mature-simulated readiness paths must expose
    # only readiness/maturity metadata and must not call the formal evaluator.
    engine = H39ResearchEngine()
    ledger_path = tmp_path / "readiness_stat_guard.sqlite3"
    ledger = H39BlindLedger(ledger_path)

    # Instrument evaluate_feature_hypotheses to detect any invocation
    call_count = 0

    def fail_if_called(*args: Any, **kwargs: Any) -> Any:
        nonlocal call_count
        call_count += 1
        raise AssertionError("evaluate_feature_hypotheses was called unexpectedly by readiness check!")

    monkeypatch.setattr(
        "btc_quant_agent.microstructure_research.evaluate_feature_hypotheses",
        fail_if_called,
    )

    # 1. Immature ledger check
    r_immature = engine.check_unblind_readiness(ledger_path=ledger_path)
    assert call_count == 0
    assert r_immature["ready_for_unblind"] is False
    assert r_immature["status"] == "FORWARD_DATA_INSUFFICIENT"

    st_immature = engine.get_blind_validation_status(ledger_path=ledger_path)
    assert call_count == 0
    assert st_immature["state"] == "FORWARD_DATA_INSUFFICIENT"

    # 2. Mature-simulated ledger check
    # Populate synthetic ledger to meet all gates (14 days, >= 750 eligible, >= 90% coverage)
    slots_per_day = 54
    for day in range(14):
        day_slot_base = H39_VALIDATION_START_MS + day * 86_400_000
        for s in range(slots_per_day):
            s_ms = day_slot_base + s * 900_000
            ledger.ingest_slot(_make_dummy_valid_row(slot_ms=s_ms))

    clock_mature = H39_VALIDATION_START_MS + 799 * 900_000
    r_mature = engine.check_unblind_readiness(ledger_path=ledger_path, as_of_ms=clock_mature)
    assert call_count == 0
    assert r_mature["ready_for_unblind"] is True
    assert r_mature["status"] == "H39_READY_FOR_ONE_SHOT_UNBLIND"

    # Verify mature payload exposes only metadata and zero performance metrics
    r_mature_str = json.dumps(r_mature).lower()
    for forbidden in ["p_value", "p_val", "t_stat", "sharpe", "effect_size", "return_60m", "return_240m", "ranking"]:
        assert f'"{forbidden}"' not in r_mature_str


def test_cli_has_no_unblind_options() -> None:
    # Section 6.E: Parser/CLI tests must prove no public option/subcommand exists for unblinding
    parser = build_parser()

    # 1. Reject --allow-unblind and --force-unblind
    for invalid_arg in ["--allow-unblind", "--force-unblind"]:
        with pytest.raises(SystemExit):
            parser.parse_args(["h39", "validation-status", invalid_arg])

        with pytest.raises(SystemExit):
            parser.parse_args(["h39", "validation-readiness", invalid_arg])

        with pytest.raises(SystemExit):
            parser.parse_args(["h39", "validation-accumulate", invalid_arg])

    # 2. Reject subcommands validation-unblind and validation-evaluate
    for invalid_sub in ["validation-unblind", "validation-evaluate"]:
        with pytest.raises(SystemExit):
            parser.parse_args(["h39", invalid_sub])

        with pytest.raises(SystemExit):
            parser.parse_args(["microstructure-research", invalid_sub])

    # 3. Exhaustive check of all actions registered on all subparsers
    def walk_actions(p: Any) -> list[str]:
        actions = []
        for act in p._actions:
            actions.extend(act.option_strings)
            if hasattr(act, "choices") and act.choices:
                if isinstance(act.choices, dict):
                    for c, sub_p in act.choices.items():
                        actions.append(str(c))
                        if hasattr(sub_p, "_actions"):
                            actions.extend(walk_actions(sub_p))
                elif isinstance(act.choices, (list, tuple, set)):
                    for c in act.choices:
                        actions.append(str(c))
        return actions

    all_actions = walk_actions(parser)
    for act in all_actions:
        if act == "one-shot-unblind":
            # Permitted in v0.3.25 as preregistered gatekeeper command
            continue
        assert "unblind" not in act.lower(), f"Forbidden unblind option/command found: {act}"
        assert act != "validation-evaluate", f"Forbidden validation-evaluate command found: {act}"


def test_blind_validation_status_contains_no_p_values_or_rankings(tmp_path: Path) -> None:
    ledger_path = tmp_path / "status_test.sqlite3"
    ledger = H39BlindLedger(ledger_path)
    ledger.append_slot(_make_dummy_valid_row(slot_ms=H39_VALIDATION_START_MS))

    status = ledger.get_status(now_ms=H39_VALIDATION_START_MS + 3600_000)
    status_str = json.dumps(status).lower()

    # Forbidden terms check
    forbidden_terms = [
        "p_value",
        "p_val",
        "p_raw",
        "p_holm",
        "t_stat",
        "sharpe",
        "ic",
        "effect_size",
        "rank",
        "ranking",
        "return_60m",
        "return_240m",
    ]
    for term in forbidden_terms:
        assert f'"{term}"' not in status_str, f"Forbidden term {term} leaked in status JSON"


def test_maturity_requires_all_gates_simultaneously(tmp_path: Path) -> None:
    ledger_path = tmp_path / "maturity_test.sqlite3"
    ledger = H39BlindLedger(ledger_path)

    # Minimum thresholds: 14 days, 750 eligible observations, 90% coverage
    assert H39_MINIMUM_VALIDATION_DAYS == 14
    assert H39_MINIMUM_ELIGIBLE_OBSERVATIONS == 750
    assert H39_MINIMUM_COVERAGE_RATIO == 0.90

    # Populate synthetic ledger with known quantities
    # Case A: 14 days and 750 slots, but coverage < 90%
    # 750 eligible slots, but 1000 expected slots (75% coverage) across 14 days
    slots_per_day = 54
    for day in range(14):
        day_slot_base = H39_VALIDATION_START_MS + day * 86_400_000
        for s in range(slots_per_day):
            s_ms = day_slot_base + s * 900_000
            row = _make_dummy_valid_row(slot_ms=s_ms)
            ledger.ingest_slot(row)

    total_inserted = 14 * slots_per_day  # 756 slots
    assert total_inserted >= 750

    # If clock says 1000 slots have elapsed -> coverage is 756 / 1000 = 75.6% < 90%
    clock_low_coverage = H39_VALIDATION_START_MS + 999 * 900_000
    st_low_cov = ledger.get_status(now_ms=clock_low_coverage)
    assert st_low_cov["days_gate_passed"] is True
    assert st_low_cov["observations_gate_passed"] is True
    assert st_low_cov["coverage_gate_passed"] is False
    assert st_low_cov["maturity_achieved"] is False
    assert st_low_cov["state"] == "FORWARD_DATA_INSUFFICIENT"

    # If clock says only 800 slots elapsed -> coverage is 756 / 800 = 94.5% >= 90%
    clock_all_met = H39_VALIDATION_START_MS + 799 * 900_000
    st_mature = ledger.get_status(now_ms=clock_all_met)
    assert st_mature["days_gate_passed"] is True
    assert st_mature["observations_gate_passed"] is True
    assert st_mature["coverage_gate_passed"] is True
    assert st_mature["maturity_achieved"] is True
    assert st_mature["state"] == "FRESH_FORWARD_VALIDATION"


def test_ready_state_schema_and_no_performance_leak(tmp_path: Path) -> None:
    engine = H39ResearchEngine()
    ledger_path = tmp_path / "readiness_test.sqlite3"
    H39BlindLedger(ledger_path)

    # When immature:
    r_immature = engine.check_unblind_readiness(ledger_path=ledger_path)
    assert r_immature["ready_for_unblind"] is False
    assert "summary" in r_immature
    assert r_immature["status"] == "FORWARD_DATA_INSUFFICIENT"

    # Check that readiness payload never contains performance metrics
    r_str = json.dumps(r_immature).lower()
    for forbidden in ["p_value", "sharpe", "return_60m", "return_240m", "ranking"]:
        assert f'"{forbidden}"' not in r_str


def test_final_holdout_sealed_and_execution_disabled() -> None:
    engine = H39ResearchEngine()
    val_status = engine.evaluate_validation_status()

    assert val_status["execution"] == "DISABLED"
    assert val_status["runtime_maximum"] == "OPPORTUNITY_ONLY"
    assert val_status["candidate_promotion_allowed"] is False

    # Check configs/safety
    opp_config_path = Path("configs/forward/opportunity_forward_campaigns.json")
    if opp_config_path.exists():
        c_data = json.loads(opp_config_path.read_text(encoding="utf-8"))
        for c in c_data.get("campaigns", []):
            if c.get("campaign_id") == "OPPORTUNITY_FORWARD_V0321_20260903T180000Z":
                assert c.get("status") == "DATA_QUALITY_TERMINAL_ARCHIVE"
                assert c.get("superseded_by") is None


def test_h38_remains_terminal_and_cannot_be_restarted() -> None:
    opp_config_path = Path("configs/forward/opportunity_forward_campaigns.json")
    assert opp_config_path.exists()
    c_data = json.loads(opp_config_path.read_text(encoding="utf-8"))
    campaigns = c_data.get("campaigns", [])

    # Confirm H38 campaign exists, is terminal archive, and no successor is registered
    h38_list = [c for c in campaigns if c.get("campaign_id") == "OPPORTUNITY_FORWARD_V0321_20260903T180000Z"]
    assert len(h38_list) == 1
    h38 = h38_list[0]
    assert h38["status"] == "DATA_QUALITY_TERMINAL_ARCHIVE"
    assert h38["terminal_at_ms"] == H38_TERMINAL_FIRST_BREACH_MS
    assert h38.get("superseded_by") is None


def test_generated_deliverables_integrity() -> None:
    deliv_dir = Path("deliverables/v0.3.23")
    assert deliv_dir.exists()

    required_files = [
        "README.md",
        "H39_BLIND_VALIDATION_LEDGER_MANIFEST.json",
        "H39_BLIND_VALIDATION_STATUS.json",
        "H39_BLINDNESS_ATTESTATION.json",
        "FORWARD_CHAIN_HEALTH.json",
        "V0.3.23_H39_BLIND_VALIDATION_REPORT.md",
        "V0.3.23_STRICT_UNBLIND_GATE_REPAIR.json",
        "V0.3.23_STRICT_UNBLIND_GATE_REPAIR.md",
    ]
    for fn in required_files:
        fpath = deliv_dir / fn
        assert fpath.exists(), f"Missing required deliverable: {fn}"

    # Forward chain health content
    fch = json.loads((deliv_dir / "FORWARD_CHAIN_HEALTH.json").read_text(encoding="utf-8"))
    assert fch["chains"]["DERIVATIVES_PIT_EPOCH_V0321_001"]["status"] == "HEALTHY"
    assert fch["chains"]["DERIVATIVES_PIT_EPOCH_V0321_001"]["rows_recorded"] > 0
    assert fch["chains"]["MICROSTRUCTURE_CAPTURE_V0315_001"]["status"] == "HEALTHY"
    assert fch["chains"]["H38_OPPORTUNITY_FORWARD_REPLICATION_LOCAL_RECOVERY"]["status"] == "DATA_QUALITY_TERMINAL_ARCHIVE"

    # Blindness attestation content
    att = json.loads((deliv_dir / "H39_BLINDNESS_ATTESTATION.json").read_text(encoding="utf-8"))
    assert att["attestations"]["zero_outcomes_evaluated_in_ledger"] is True
    assert att["attestations"]["zero_p_values_inspected"] is True
    assert att["attestations"]["zero_feature_rankings_computed"] is True
    assert att["attestations"]["zero_final_holdout_access"] is True
    assert att["attestations"]["execution_engine_disabled"] is True

    # Repair deliverable content check
    repair_json = json.loads((deliv_dir / "V0.3.23_STRICT_UNBLIND_GATE_REPAIR.json").read_text(encoding="utf-8"))
    assert repair_json["finding_id"] == "CHATGPT-V0.3.23-HIGH-ALLOW-UNBLIND-BYPASS"
    assert repair_json["new_fail_closed_behavior"]["unconditional_refusal"] is True
    assert repair_json["new_fail_closed_behavior"]["allow_unblind_removed"] is True
    assert repair_json["attestations"]["zero_fresh_outcome_inspection"] is True
    assert repair_json["attestations"]["zero_protocol_drift"] is True
    assert repair_json["attestations"]["zero_final_holdout_access"] is True
    assert repair_json["attestations"]["execution_disabled"] is True
    assert repair_json["attestations"]["h38_permanently_terminal"] is True
    assert repair_json["current_blind_maturity_counts_only"]["state"] == "FORWARD_DATA_INSUFFICIENT"
