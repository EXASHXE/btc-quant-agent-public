from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from btc_quant_agent.microstructure_research import (
    FORMAL_FEATURE_IDS,
    H39_HYPOTHESIS_ID,
    H39_PROTOCOL_FREEZE_SHA,
    PREDEFINED_FEATURE_SIGNS,
    H39FeatureRow,
    H39Observation,
    H39OutcomeRow,
    MicrostructureResearchLoader,
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
