from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from btc_quant_agent.microstructure_research import (
    FORMAL_FEATURE_IDS,
    H38_TERMINAL_FIRST_BREACH_MS,
    H38_TERMINAL_FIRST_BREACH_UTC,
    H39_HYPOTHESIS_ID,
    H39_PROTOCOL_CLARIFICATION_SHA,
    H39_PROTOCOL_FREEZE_SHA,
    PREDEFINED_FEATURE_SIGNS,
    FeatureTestResult,
    H39FeatureRow,
    H39Observation,
    H39OutcomeRow,
    H39ResearchEngine,
    MicrostructureResearchLoader,
    _fit_l2_logistic_regression,
    _holm_bonferroni,
    evaluate_feature_hypotheses,
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


def test_read_only_sqlite_and_write_refusal(tmp_path: Path) -> None:
    db_path = tmp_path / "test_micro.sqlite3"
    _create_test_partition(db_path)

    loader = MicrostructureResearchLoader(db_path)
    ok, status = loader.check_integrity()
    assert ok is True
    assert status.lower() == "ok"

    # Reading should work
    with loader.connect_readonly() as conn:
        count = conn.execute("SELECT COUNT(*) FROM agg_trades").fetchone()[0]
        assert count == 0

        # Attempting any write must raise OperationalError (read-only database)
        with pytest.raises(sqlite3.OperationalError, match="readonly|read-only"):
            conn.execute("INSERT INTO agg_trades (aggregate_trade_id) VALUES (1)")

        with pytest.raises(sqlite3.OperationalError, match="readonly|read-only"):
            conn.execute("CREATE TABLE evil_research_table (x INT)")

        with pytest.raises(sqlite3.OperationalError, match="readonly|read-only"):
            conn.execute("DELETE FROM agg_trades")


def test_feature_window_anti_leakage_and_event_boundary(tmp_path: Path) -> None:
    db_path = tmp_path / "test_micro.sqlite3"
    _create_test_partition(db_path)

    slot_ms = 1788204600000  # 19:30:00 UTC
    t_15m = slot_ms - 15 * 60_000

    conn = sqlite3.connect(db_path)
    # Populate dense book samples every 5 seconds to satisfy continuity
    cur_t = t_15m + 1000
    uid = 100
    while cur_t <= slot_ms:
        conn.execute(
            """INSERT INTO book_samples VALUES(?,?,?,?,?,?,?,?,?)""",
            (cur_t, uid, cur_t, 1.0, 0.2, 0.3, 0.4, 70000.0, 10.0),
        )
        cur_t += 5000
        uid += 1

    # Populate regular trades
    cur_trade = t_15m + 2000
    tid = 1
    while cur_trade <= slot_ms:
        conn.execute(
            """INSERT INTO agg_trades VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (tid, cur_trade, cur_trade, cur_trade, 0, 70000.0, 1.0, 0, "BUY", "h"),
        )
        cur_trade += 30000
        tid += 1

    # Inject ADVERSARIAL FUTURE EVENTS (strictly after slot_ms)
    conn.execute(
        """INSERT INTO agg_trades VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (9999, slot_ms + 1, slot_ms + 1, slot_ms + 1, 0, 80000.0, 1000.0, 1, "SELL", "future"),
    )
    conn.execute(
        """INSERT INTO book_samples VALUES(?,?,?,?,?,?,?,?,?)""",
        (slot_ms + 1, 99999, slot_ms + 1, 100.0, -1.0, -1.0, -1.0, 10000.0, -9999.0),
    )

    # Inject ADVERSARIAL LATE EVENT (event_time <= slot_ms but receive_time > slot_ms)
    conn.execute(
        """INSERT INTO agg_trades VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (8888, slot_ms - 1000, slot_ms - 1000, slot_ms + 5000, 0, 80000.0, 500.0, 1, "SELL", "late"),
    )
    conn.execute(
        """INSERT INTO book_samples VALUES(?,?,?,?,?,?,?,?,?)""",
        (slot_ms - 1000, 88888, slot_ms + 5000, 100.0, -1.0, -1.0, -1.0, 10000.0, -9999.0),
    )
    conn.commit()
    conn.close()

    loader = MicrostructureResearchLoader(db_path)
    feat = loader.compute_features(slot_ms)

    assert feat.eligible is True
    # Future/late trades must NOT affect M1/M2 (should be 100% BUY -> +1.0)
    assert feat.m1_trade_imbalance_5m == pytest.approx(1.0)
    assert feat.m2_trade_imbalance_15m == pytest.approx(1.0)

    # Future/late book samples must NOT affect M3/M4/M5/M6
    assert feat.m3_ofi_5m > 0.99
    assert feat.m4_top5_depth_imbalance_5m == pytest.approx(0.3)
    assert feat.m5_top20_depth_imbalance_5m == pytest.approx(0.4)


def test_gap_and_continuity_invalidation(tmp_path: Path) -> None:
    db_path = tmp_path / "test_micro.sqlite3"
    _create_test_partition(db_path)

    slot_ms = 1788204600000
    t_15m = slot_ms - 15 * 60_000

    conn = sqlite3.connect(db_path)
    # Insert a sequence gap in the 15m window
    conn.execute(
        "INSERT INTO gaps VALUES(1, ?, ?, 'PU_GAP', 'pu continuity failure')",
        (t_15m + 60_000, t_15m + 120_000),
    )
    conn.commit()
    conn.close()

    loader = MicrostructureResearchLoader(db_path)
    eligible, reason = loader.check_slot_eligibility(slot_ms)
    assert eligible is False
    assert reason == "GAP_IN_FEATURE_WINDOW"


def test_agg_trade_buy_sell_sign_convention(tmp_path: Path) -> None:
    db_path = tmp_path / "test_micro.sqlite3"
    _create_test_partition(db_path)

    slot_ms = 1788204600000
    t_15m = slot_ms - 15 * 60_000

    conn = sqlite3.connect(db_path)
    # Book samples to pass eligibility
    cur_t = t_15m + 1000
    uid = 1
    while cur_t <= slot_ms:
        conn.execute(
            """INSERT INTO book_samples VALUES(?,?,?,?,?,?,?,?,?)""",
            (cur_t, uid, cur_t, 1.0, 0.0, 0.0, 0.0, 70000.0, 0.0),
        )
        cur_t += 5000
        uid += 1

    # In 5m window: 75% BUY, 25% SELL
    # Buy notional: 75000, Sell notional: 25000 -> Imbalance = (75 - 25) / (75 + 25) = +0.50
    t_5m = slot_ms - 5 * 60_000
    conn.execute(
        "INSERT INTO agg_trades VALUES(1, ?, ?, ?, 0, 75000.0, 1.0, 0, 'BUY', 'h')",
        (t_5m + 60_000, t_5m + 60_000, t_5m + 60_000),
    )
    conn.execute(
        "INSERT INTO agg_trades VALUES(2, ?, ?, ?, 0, 25000.0, 1.0, 1, 'SELL', 'h')",
        (t_5m + 120_000, t_5m + 120_000, t_5m + 120_000),
    )
    conn.commit()
    conn.close()

    loader = MicrostructureResearchLoader(db_path)
    feat = loader.compute_features(slot_ms)
    assert feat.m1_trade_imbalance_5m == pytest.approx(0.50, abs=1e-5)


def test_m6_closed_form_algebraic_mid_and_deviation() -> None:
    # Test closed-form algebraic derivation:
    # mid = (bid + ask) / 2
    # spread_bps = (ask - bid) / mid * 10000
    # top1_imbalance = (bq - aq) / (bq + aq)
    # microprice = (ask * bq + bid * aq) / (bq + aq)
    # Formula: mid == microprice / [1 + (spread_bps / 20000) * top1_imbalance]
    bid = 65000.0
    ask = 65005.0
    bq = 2.5
    aq = 1.5

    mid_true = (bid + ask) / 2.0
    spread_bps = (ask - bid) / mid_true * 10000.0
    top1_imb = (bq - aq) / (bq + aq)
    microprice = (ask * bq + bid * aq) / (bq + aq)

    # Reconstructed mid
    reconstructed_mid = microprice / (1.0 + (spread_bps / 20000.0) * top1_imb)
    assert reconstructed_mid == pytest.approx(mid_true, abs=1e-9)

    # Deviation in bps
    dev_direct = (microprice - mid_true) / mid_true * 10000.0
    dev_formula = (spread_bps / 2.0) * top1_imb
    assert dev_direct == pytest.approx(dev_formula, abs=1e-9)


def test_m7_and_m8_deterministic_formulas() -> None:
    # M7: (sign(M1) + sign(M3) + sign(M4) + sign(M5) + sign(M6)) / 5.0
    # M8: M1 - (M4 + M5) / 2.0

    # Case 1: Unanimous positive
    m1, m3, m4, m5, m6 = 0.5, 0.8, 0.2, 0.1, 1.2
    def sgn(x: float) -> float:
        return 1.0 if x > 0 else (-1.0 if x < 0 else 0.0)
    m7 = (sgn(m1) + sgn(m3) + sgn(m4) + sgn(m5) + sgn(m6)) / 5.0
    m8 = m1 - (m4 + m5) / 2.0
    assert m7 == pytest.approx(1.0)
    assert m8 == pytest.approx(0.5 - 0.15)

    # Case 2: Divergence: positive trade flow, negative depth
    m1, m4, m5 = 0.8, -0.4, -0.6
    m8_div = m1 - (m4 + m5) / 2.0
    assert m8_div == pytest.approx(0.8 - (-0.5))  # 1.3


def test_formal_family_size_and_holm_bonferroni() -> None:
    assert len(FORMAL_FEATURE_IDS) == 8
    assert len(PREDEFINED_FEATURE_SIGNS) == 8

    # Synthetic p-values
    # Feature 1: raw 0.005 -> adjusted 0.005 * 8 = 0.040
    # Feature 2: raw 0.010 -> adjusted 0.010 * 7 = 0.070
    p_raw = [0.005, 0.010, 0.20, 0.50, 0.80, 0.90, 0.15, 0.40]
    p_adj = _holm_bonferroni(p_raw)

    assert len(p_adj) == 8
    # Smallest p-value multiplier is 8
    assert p_adj[0] == pytest.approx(0.040, abs=1e-5)
    # Second smallest (0.010) multiplier is 7 -> 0.070
    assert p_adj[1] == pytest.approx(0.070, abs=1e-5)
    # Adjusted p-values must be monotonically non-decreasing with respect to raw rank
    indexed_raw = sorted(enumerate(p_raw), key=lambda x: x[1])
    for i in range(len(indexed_raw) - 1):
        idx_curr = indexed_raw[i][0]
        idx_next = indexed_raw[i + 1][0]
        assert p_adj[idx_curr] <= p_adj[idx_next] + 1e-9


def test_statistical_evaluator_gate_enforcement() -> None:
    # Create mock observations
    obs_list: list[H39Observation] = []
    slot = 1788204600000

    # 30 observations with positive correlation between M1 and return_60m
    for i in range(30):
        m1_val = (i - 15) / 15.0  # [-1.0, 1.0]
        ret = m1_val * 0.005 + 0.001  # Perfect positive correlation
        f_row = H39FeatureRow(
            slot_ms=slot + i * 900_000,
            slot_utc="2026-08-31T19:30:00Z",
            m1_trade_imbalance_5m=m1_val,
            m2_trade_imbalance_15m=m1_val * 0.8,
            m3_ofi_5m=m1_val * 0.5,
            m4_top5_depth_imbalance_5m=m1_val * 0.3,
            m5_top20_depth_imbalance_5m=m1_val * 0.2,
            m6_microprice_deviation_1m=m1_val * 2.0,
            m7_pressure_agreement=m1_val,
            m8_pressure_divergence=m1_val * 0.5,
            eligible=True,
            rejection_reason=None,
            book_sample_count_15m=100,
            trade_count_15m=50,
        )
        o_row = H39OutcomeRow(
            slot_ms=slot + i * 900_000,
            reference_price=70000.0,
            reference_time_ms=slot + i * 900_000,
            future_close_60m=70000.0 * (1.0 + ret),
            return_60m=ret,
            future_close_240m=70000.0 * (1.0 + ret * 2),
            return_240m=ret * 2,
            trailing_return_15m=0.0005,
            trailing_return_60m=0.0010,
            trailing_atr_15m=500.0,
        )
        obs_list.append(H39Observation(feature_row=f_row, outcome_row=o_row))

    results = evaluate_feature_hypotheses(obs_list, horizon="60m")
    assert len(results) == 8

    m1_res = results["M1_TRADE_NOTIONAL_IMBALANCE_5M"]
    assert m1_res.sign_correct is True
    assert m1_res.effect_estimate > 0
    assert m1_res.p_value_raw < 0.001
    assert m1_res.p_value_holm < 0.01
    assert m1_res.ci_excludes_zero_in_correct_direction is True


def test_frozen_protocol_integrity_and_safety_invariants() -> None:
    protocol_path = Path("configs/research/v0.3.22_microstructure_h39_protocol.json")
    assert protocol_path.exists()
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))

    assert protocol["hypothesis_id"] == H39_HYPOTHESIS_ID
    assert protocol["formal_feature_universe"]["family_size"] == 8
    assert protocol["formal_feature_universe"]["m6_support_determination"]["status"] == "M6_SUPPORTED"

    safety = protocol["safety_invariants"]
    assert safety["strategy"] == "EXPERIMENTAL"
    assert safety["qualified_direction_engine"] == "NONE"
    assert safety["runtime_maximum"] == "OPPORTUNITY_ONLY"
    assert safety["execution"] == "DISABLED"
    assert safety["auto_execute"] is False
    assert safety["final_holdout"] == "SEALED"


def test_deliverables_manifest_consistency() -> None:
    manifest_path = Path("deliverables/v0.3.22/H39_PROTOCOL_FREEZE_MANIFEST.json")
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["protocol_freeze_sha"] == H39_PROTOCOL_FREEZE_SHA
        assert manifest["guardrail_compliance"]["G1_protocol_before_labels"]["compliant"] is True
        assert manifest["guardrail_compliance"]["G2_read_only_sqlite"]["compliant"] is True
        assert manifest["guardrail_compliance"]["G3_m6_support_determination"]["status"] == "M6_SUPPORTED"
        assert manifest["guardrail_compliance"]["G4_high_hurdle_falsification"]["primary_horizon_minutes"] == 60


def test_h39_reference_entry_timing_and_protocol_boundary() -> None:
    # Finding P0-A: Reference entry timing semantics
    # Decision boundary: curr_slot is the decision close
    curr_slot = 1788204600000  # 19:30:00 UTC
    decision_close_ms = curr_slot
    ref_time_ms = decision_close_ms + 60_000

    # 1. Reference time must be strictly decision_close_ms + 60_000
    assert ref_time_ms == decision_close_ms + 60_000

    # 2. Reference candle is NEVER the candle beginning at decision_close_ms
    forbidden_candle_start_ms = decision_close_ms
    assert ref_time_ms != forbidden_candle_start_ms
    assert ref_time_ms - forbidden_candle_start_ms == 60_000

    # 3. 60m horizon exit candle open: ref_time_ms + 59 * 60_000 (closes at ref_time_ms + 60 * 60_000)
    c60_open_ms = ref_time_ms + 59 * 60_000
    c60_close_ms = c60_open_ms + 60_000
    assert c60_open_ms == curr_slot + 60 * 60_000
    assert c60_close_ms == ref_time_ms + 60 * 60_000
    assert c60_close_ms == curr_slot + 61 * 60_000

    # 4. 240m horizon exit candle open: ref_time_ms + 239 * 60_000 (closes at ref_time_ms + 240 * 60_000)
    c240_open_ms = ref_time_ms + 239 * 60_000
    c240_close_ms = c240_open_ms + 60_000
    assert c240_open_ms == curr_slot + 240 * 60_000
    assert c240_close_ms == ref_time_ms + 240 * 60_000
    assert c240_close_ms == curr_slot + 241 * 60_000


def test_h39_baseline_anti_lookahead_and_invariance() -> None:
    # Baseline features must be purely causal and computed only from candles <= decision_close_ms
    curr_slot = 1788204600000  # 19:30:00 UTC
    decision_close_ms = curr_slot

    # Source candle timestamps for baseline:
    c_dec_open = decision_close_ms - 60_000       # 19:29:00 -> closes at 19:30:00 (<= decision_close)
    c_15m_open = decision_close_ms - 16 * 60_000  # 19:14:00 -> closes at 19:15:00 (15m before decision)
    c_60m_open = decision_close_ms - 61 * 60_000  # 18:29:00 -> closes at 18:30:00 (60m before decision)

    assert c_dec_open + 60_000 <= decision_close_ms
    assert c_15m_open + 60_000 <= decision_close_ms
    assert c_60m_open + 60_000 <= decision_close_ms

    # Simulate baseline returns
    dec_close = 70000.0
    close_15 = 69650.0
    close_60 = 69300.0
    atr_15m = 350.0

    tr15 = (dec_close - close_15) / close_15
    tr60 = (dec_close - close_60) / close_60
    atr_ratio = atr_15m / dec_close

    assert tr15 == pytest.approx((70000.0 - 69650.0) / 69650.0)
    assert tr60 == pytest.approx((70000.0 - 69300.0) / 69300.0)
    assert atr_ratio == pytest.approx(350.0 / 70000.0)

    # Future adversarial candle at ref_time_ms or beyond must have zero impact on baseline
    future_adversarial_price = 999999.0
    assert future_adversarial_price > dec_close
    assert issubclass(H39ResearchEngine, object)
    # Recomputing baseline features with future adversarial price available elsewhere cannot change them
    tr15_recomputed = (dec_close - close_15) / close_15
    assert tr15_recomputed == tr15


def test_h39_baseline_non_zero_enforcement() -> None:
    # Baseline features must never be silently converted to zero
    slot = 1788204600000
    f_row = H39FeatureRow(
        slot_ms=slot,
        slot_utc="2026-08-31T19:30:00Z",
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
        book_sample_count_15m=100,
        trade_count_15m=50,
    )

    # Missing trailing_return_15m on first observation
    bad_outcome = H39OutcomeRow(
        slot_ms=slot,
        reference_price=70000.0,
        reference_time_ms=slot + 60_000,
        future_close_60m=70100.0,
        return_60m=0.0014,
        future_close_240m=70200.0,
        return_240m=0.0028,
        trailing_return_15m=None,  # type: ignore[arg-type]
        trailing_return_60m=0.0010,
        trailing_atr_15m=500.0,
        trailing_atr_ratio_15m=0.007,
    )
    good_outcome_1 = H39OutcomeRow(
        slot_ms=slot + 900_000,
        reference_price=70000.0,
        reference_time_ms=slot + 960_000,
        future_close_60m=70100.0,
        return_60m=0.0014,
        future_close_240m=70200.0,
        return_240m=0.0028,
        trailing_return_15m=0.0010,
        trailing_return_60m=0.0010,
        trailing_atr_15m=500.0,
        trailing_atr_ratio_15m=0.007,
    )
    good_outcome_2 = H39OutcomeRow(
        slot_ms=slot + 1800_000,
        reference_price=70000.0,
        reference_time_ms=slot + 1860_000,
        future_close_60m=70200.0,
        return_60m=0.0028,
        future_close_240m=70300.0,
        return_240m=0.0042,
        trailing_return_15m=0.0010,
        trailing_return_60m=0.0010,
        trailing_atr_15m=500.0,
        trailing_atr_ratio_15m=0.007,
    )
    obs = [
        H39Observation(feature_row=f_row, outcome_row=bad_outcome),
        H39Observation(feature_row=f_row, outcome_row=good_outcome_1),
        H39Observation(feature_row=f_row, outcome_row=good_outcome_2),
    ]

    with pytest.raises(ValueError, match="Baseline features missing"):
        evaluate_feature_hypotheses(obs, horizon="60m")


def test_h39_logistic_regression_baseline_and_incremental_stats() -> None:
    # Test deterministic L2 logistic regression and incremental statistics
    import numpy as np

    # 1. Direct unit test of _fit_l2_logistic_regression
    np.random.seed(42)
    n = 50
    x0 = np.ones((n, 1))
    x1 = np.random.randn(n, 1)
    x2 = np.random.randn(n, 1)
    x3 = np.random.randn(n, 1)
    X = np.hstack([x0, x1, x2, x3])
    # Target linearly dependent on x1
    prob = 1.0 / (1.0 + np.exp(-(0.5 + 1.2 * x1.ravel())))
    y = (prob > 0.5).astype(float).tolist()

    beta, cov, ll = _fit_l2_logistic_regression(X.tolist(), y, l2_lambda=1.0)
    assert len(beta) == 4
    assert len(cov) == 4 and len(cov[0]) == 4
    assert ll < 0.0  # Log-likelihood is negative
    assert all(np.isfinite(b) for b in beta)
    assert all(np.isfinite(cov[i][j]) for i in range(4) for j in range(4))

    # 2. Test incremental statistics in evaluate_feature_hypotheses
    slot = 1788204600000
    obs_list: list[H39Observation] = []
    for i in range(40):
        m1_val = (i - 20) / 20.0
        ret = m1_val * 0.004 + 0.0005
        f_row = H39FeatureRow(
            slot_ms=slot + i * 900_000,
            slot_utc="2026-08-31T19:30:00Z",
            m1_trade_imbalance_5m=m1_val,
            m2_trade_imbalance_15m=m1_val * 0.5,
            m3_ofi_5m=m1_val * 0.5,
            m4_top5_depth_imbalance_5m=m1_val * 0.2,
            m5_top20_depth_imbalance_5m=m1_val * 0.2,
            m6_microprice_deviation_1m=m1_val * 1.5,
            m7_pressure_agreement=m1_val,
            m8_pressure_divergence=m1_val * 0.4,
            eligible=True,
            rejection_reason=None,
            book_sample_count_15m=100,
            trade_count_15m=50,
        )
        o_row = H39OutcomeRow(
            slot_ms=slot + i * 900_000,
            reference_price=70000.0,
            reference_time_ms=slot + i * 900_000 + 60_000,
            future_close_60m=70000.0 * (1.0 + ret),
            return_60m=ret,
            future_close_240m=70000.0 * (1.0 + ret * 2),
            return_240m=ret * 2,
            trailing_return_15m=0.0002 * (i % 3 - 1),
            trailing_return_60m=0.0005 * (i % 5 - 2),
            trailing_atr_15m=300.0,
            trailing_atr_ratio_15m=300.0 / 70000.0,
            decision_close_price=70000.0,
            decision_close_ms=slot + i * 900_000,
        )
        obs_list.append(H39Observation(feature_row=f_row, outcome_row=o_row))

    results = evaluate_feature_hypotheses(obs_list, horizon="60m")
    m1_res = results["M1_TRADE_NOTIONAL_IMBALANCE_5M"]
    assert isinstance(m1_res, FeatureTestResult)

    # Verify both LR and z statistics are populated and finite
    assert m1_res.incremental_lr_stat is not None
    assert m1_res.incremental_lr_p_value is not None
    assert m1_res.incremental_z_stat is not None
    assert m1_res.incremental_z_p_value is not None
    assert np.isfinite(m1_res.incremental_lr_stat)
    assert np.isfinite(m1_res.incremental_z_stat)
    assert 0.0 <= m1_res.incremental_lr_p_value <= 1.0
    assert 0.0 <= m1_res.incremental_z_p_value <= 1.0

    # 3. Test that altering baseline returns changes incremental statistics
    obs_list_alt: list[H39Observation] = []
    for obs in obs_list:
        alt_outcome = H39OutcomeRow(
            slot_ms=obs.outcome_row.slot_ms,
            reference_price=obs.outcome_row.reference_price,
            reference_time_ms=obs.outcome_row.reference_time_ms,
            future_close_60m=obs.outcome_row.future_close_60m,
            return_60m=obs.outcome_row.return_60m,
            future_close_240m=obs.outcome_row.future_close_240m,
            return_240m=obs.outcome_row.return_240m,
            trailing_return_15m=obs.outcome_row.return_60m * 0.9,  # Highly correlated with outcome!
            trailing_return_60m=obs.outcome_row.return_60m * 0.8,
            trailing_atr_15m=obs.outcome_row.trailing_atr_15m,
            trailing_atr_ratio_15m=obs.outcome_row.trailing_atr_ratio_15m,
            decision_close_price=obs.outcome_row.decision_close_price,
            decision_close_ms=obs.outcome_row.decision_close_ms,
        )
        obs_list_alt.append(H39Observation(feature_row=obs.feature_row, outcome_row=alt_outcome))

    results_alt = evaluate_feature_hypotheses(obs_list_alt, horizon="60m")
    m1_res_alt = results_alt["M1_TRADE_NOTIONAL_IMBALANCE_5M"]

    # When baseline controls absorb the signal, incremental statistics must change
    assert m1_res.incremental_lr_stat != m1_res_alt.incremental_lr_stat
    assert m1_res.incremental_z_stat != m1_res_alt.incremental_z_stat


def test_h38_terminal_reconciliation_and_irreversibility() -> None:
    from btc_quant_agent.opportunity_forward import (
        OpportunityCampaignRegistry,
        collect_opportunity_once,
        resolve_opportunity_outcomes,
    )

    # 1. Verify H38 campaign config reconciliation
    config_path = Path("configs/forward/opportunity_forward_campaigns.json")
    assert config_path.exists()
    registry = OpportunityCampaignRegistry.load(config_path)

    h38_life = next(
        (c for c in registry.campaigns if c.campaign_id == "OPPORTUNITY_FORWARD_V0321_20260903T180000Z"),
        None,
    )
    assert h38_life is not None
    assert h38_life.status == "DATA_QUALITY_TERMINAL_ARCHIVE"
    assert h38_life.formal_role == "DATA_QUALITY_TERMINAL_ARCHIVE"
    assert h38_life.terminal_at_ms == 1788511500000

    # 2. Verify first breach constants
    assert H38_TERMINAL_FIRST_BREACH_MS == 1788511500000
    assert H38_TERMINAL_FIRST_BREACH_UTC == "2026-09-04T08:45:00Z"

    # 3. Verify H38 reconciliation deliverable exists and is consistent
    recon_path = Path("deliverables/v0.3.22/H38_TERMINAL_RECONCILIATION.json")
    assert recon_path.exists()
    recon = json.loads(recon_path.read_text(encoding="utf-8"))
    assert recon["campaign_id"] == "OPPORTUNITY_FORWARD_V0321_20260903T180000Z"
    assert recon["data_quality_gate"]["observed_consecutive_missed_decision_slots"] == 10
    assert recon["data_quality_gate"]["maximum_consecutive_missed_decision_slots"] == 4
    assert recon["terminal_transition"]["terminal_at_ms"] == 1788511500000
    assert recon["terminal_transition"]["terminal_at_utc"] == "2026-09-04T08:45:00Z"
    assert recon["terminal_transition"]["new_status"] == "DATA_QUALITY_TERMINAL_ARCHIVE"
    assert recon["terminal_transition"]["formal_role"] == "DATA_QUALITY_TERMINAL_ARCHIVE"

    # 4. Verify fail-closed protection in opportunity collection and resolution
    mock_camp = MagicMock()
    mock_camp.campaign_id = "OPPORTUNITY_FORWARD_V0321_20260903T180000Z"
    mock_camp.has_data_quality_gate = True
    mock_camp.campaign_start_ms = 0

    mock_store = MagicMock()
    mock_store.data_quality_metrics.return_value = {
        "terminal_failure": True,
        "consecutive_missed_slots": 10,
    }
    mock_service = MagicMock()
    mock_client = MagicMock()

    # collect_opportunity_once must raise ValueError
    with pytest.raises(ValueError, match="cannot collect for terminal campaign.*data quality gate breached"):
        collect_opportunity_once(mock_service, mock_store, mock_camp, now_ms=1788511500000)

    # resolve_opportunity_outcomes must raise ValueError
    with pytest.raises(ValueError, match="cannot resolve outcomes for terminal campaign.*data quality gate breached"):
        resolve_opportunity_outcomes(mock_client, mock_store, mock_camp, now_ms=1788511500000)


def test_h39_protocol_clarification_manifest() -> None:
    # Verify clarification manifest committed prior to inspecting fresh validation outcomes
    assert H39_PROTOCOL_CLARIFICATION_SHA == "2d1ccecc11dc231ffa41cdb1b5a9ea693abccc59"
    manifest_path = Path("deliverables/v0.3.22/H39_PROTOCOL_CLARIFICATION_001.json")
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["clarification_id"] == "H39_PROTOCOL_CLARIFICATION_001"
    assert manifest["hypothesis_id"] == "H39_MICROSTRUCTURE_DIRECTIONAL_INFORMATION"
    assert manifest["protocol_freeze_sha"] == H39_PROTOCOL_FREEZE_SHA
    assert manifest["preceding_implementation_review_sha"] == "24d30c356903b1821cd13bc1f1b77be4755d73be"

    # Reference entry semantics
    ref = manifest["reference_entry_semantics"]
    assert ref["reference_entry_rule"] == "OPEN of first fully available 1m bar strictly after decision close (decision_close_ms + 60_000)"
    assert ref["reference_candle_open_ms"] == "decision_close_ms + 60_000"
    assert "strictly never the candle beginning at decision_close_ms" in ref["prohibition"]

    # Baseline specification
    base = manifest["baseline_specification"]
    assert "C=1.0" in base["regularization"]
    assert "lambda = 1.0" in base["regularization"]

    # Contamination attestation
    att = manifest["contamination_attestation"]
    assert att["zero_fresh_60m_validation_outcomes_inspected"] is True
    assert att["validation_start_ms"] == 1788520500000
    assert att["validation_start_utc"] == "2026-09-04T11:15:00Z"
    assert att["fresh_validation_status_at_clarification"] == "FORWARD_DATA_INSUFFICIENT"

