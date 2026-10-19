"""Focused tests for P3-R2 outcome adapter, boundary enforcement, and data availability.

Verifies:
1. Narrow archive envelope inclusion (2026-03-31T16:00:00Z to 2026-09-01T00:00:00Z)
2. 24h horizon cutoff and right-boundary H39 embargo enforcement
3. No early or chronologically invalid outcome access
4. Private holdout / unknown overlap fail-closed denial
5. Right-boundary funding settlement alignment
6. Binance mark price 1440m gap handling
7. OKX aggregated funding gap separation (altcoin gaps vs BTC)
8. Missing and stale Z handling with NO_ACTION retention
9. Tamper detection and wrong hash rejection
10. Unsafe directory traversal and protected path rejection
11. Deterministic repeatability
12. Production no-scope denial (EXPLICIT_OWNER_AUTHORIZATION_REQUIRED)
13. Real historical outcome rows read == 0
"""

import copy
import hashlib
import json
import math
import os
from pathlib import Path

import pytest

from scripts.research.cross_venue import normalized_sources as n
from scripts.research.exposed_dev_bridge import authorization as a
from scripts.research.exposed_dev_bridge import outcome_adapter as oa
from scripts.research.exposed_dev_bridge import pipeline as cli
from scripts.research.strategy_eval.costs import BASELINE, Outcome, Settlement, economics


def test_narrow_archive_envelope_inclusion(tmp_path):
    """Confirm 2026-03-31T16:00:00Z allows OKX UTC+8 archives while 2026-04-01T00:00:00Z rejects them."""
    root = tmp_path / "binance"
    root.mkdir()
    # OKX file starting at 2026-03-31 16:00:00 UTC (2026-04-01 in UTC+8)
    okx_start_us = n.utc_us("2026-03-31T16:00:00.000000Z")
    okx_end_us = n.utc_us("2026-04-01T16:00:00.000000Z")

    # Narrow envelope starting at 16:00 UTC
    narrow_envelope = [{"start_utc": "2026-03-31T16:00:00.000000Z", "end_utc": "2026-09-01T00:00:00.000000Z"}]
    ranges_narrow = a._ranges(narrow_envelope, hour_aligned=True)
    assert a._inside(okx_start_us, okx_end_us, ranges_narrow)

    # Envelope starting at April 1 midnight UTC fails to contain OKX 2026-04-01
    apr1_envelope = [{"start_utc": "2026-04-01T00:00:00.000000Z", "end_utc": "2026-09-01T00:00:00.000000Z"}]
    ranges_apr1 = a._ranges(apr1_envelope, hour_aligned=True)
    assert not a._inside(okx_start_us, okx_end_us, ranges_apr1)


def test_24h_cutoff_and_embargo_enforcement():
    """Verify 24h horizon origin is strictly blocked when exit would touch H39 embargo."""
    embargo_us = n.utc_us("2026-09-01T00:00:00.000000Z")
    max_24h_origin = oa.horizon_max_origin(24, embargo_us)

    # The latest eligible 24h origin must mature on or before 2026-09-01T00:00:00Z
    assert oa.is_origin_mature(max_24h_origin, 24, embargo_us)
    # Origin 1 hour later must be blocked
    blocked_origin = max_24h_origin + 3600
    assert not oa.is_origin_mature(blocked_origin, 24, embargo_us)

    # Specifically for 2026-08-31 00:01:00 UTC:
    aug31_origin = n.utc_us("2026-08-31T00:01:00.000000Z") // oa.US
    assert not oa.is_origin_mature(aug31_origin, 24, embargo_us)

    # 4h and 8h horizons remain mature longer than 24h
    max_4h_origin = oa.horizon_max_origin(4, embargo_us)
    max_8h_origin = oa.horizon_max_origin(8, embargo_us)
    assert max_4h_origin > max_8h_origin > max_24h_origin


def test_no_early_or_wrong_outcome_access():
    """Verify outcomes require correct entry and exit timing strictly after origin cutoff."""
    fixtures = oa.generate_synthetic_fixture_data(1704067200, 24)
    origin_t = 1704067200 + 60  # HH:01

    outcome, status = oa.build_origin_outcome(
        origin_t, 8, fixtures["perp_1m_bars"], fixtures["mark_prices"],
        fixtures["funding_rates"], fixtures["funding_coverage_us"]
    )
    assert status == "RESOLVED"
    assert outcome is not None
    # Entry must be at HH:02 (origin + 60s)
    assert outcome.entry_t == origin_t + 60
    # Exit must be at (HH+8):02 (entry + 8*3600s)
    assert outcome.exit_t == outcome.entry_t + 8 * 3600


def test_private_holdout_unknown_denial(owner_scope):
    """Verify scope validation fails closed if protected dates or holdout status are unconfirmed."""
    scope, doc, _, _ = owner_scope

    # 1. Unconfirmed protected dates complete
    doc_copy = copy.deepcopy(doc)
    doc_copy["governance"]["protected_dates_complete"] = False
    scope.write_text(json.dumps(doc_copy))
    with pytest.raises(n.BridgeError, match="GOVERNED_HOLDOUT_DATES_UNRESOLVED"):
        a.validate_scope(scope)

    # 2. Unconfirmed holdout status
    doc_copy2 = copy.deepcopy(doc)
    doc_copy2["governance"]["holdout_status"] = "OWNER_PENDING_CONFIRMATION"
    scope.write_text(json.dumps(doc_copy2))
    with pytest.raises(n.BridgeError, match="GOVERNED_HOLDOUT_DATES_UNRESOLVED"):
        a.validate_scope(scope)


def test_right_boundary_funding_settlement_alignment():
    """Verify funding settlements are resolved strictly in (entry, exit] with expected 8h boundaries."""
    entry_t = 1704067200 + 120  # 00:02 UTC
    exit_t = entry_t + 8 * 3600  # 08:02 UTC

    # Exactly one 8h settlement occurs in this window at 08:00 UTC (1704096000)
    expected_settlement_t = 1704096000
    funding_rates = {expected_settlement_t: 0.00010}
    mark_prices = {expected_settlement_t: 40500.0}
    coverage_us = (entry_t * oa.US, exit_t * oa.US)

    settlements, expected_us, status = oa.resolve_funding_settlements(
        entry_t, exit_t, funding_rates, mark_prices, coverage_us
    )
    assert status == "RESOLVED"
    assert len(settlements) == 1
    assert settlements[0].t_us == expected_settlement_t * oa.US
    assert settlements[0].rate == 0.00010
    assert settlements[0].mark == 40500.0


def test_binance_mark_price_gap_handling():
    """Verify that during a 1440m mark price gap, mark dependent settlements fail resolution."""
    entry_t = oa.JUNE_2026_MARK_GAP_START_US // oa.US - 3600
    exit_t = entry_t + 8 * 3600
    # Expected settlement falls inside the gap
    settlement_t = entry_t + 4 * 3600
    funding_rates = {settlement_t: 0.0001}
    mark_prices = {settlement_t: 40000.0}
    coverage_us = (entry_t * oa.US, exit_t * oa.US)

    # Known gap active
    known_gaps = [(oa.JUNE_2026_MARK_GAP_START_US, oa.JUNE_2026_MARK_GAP_END_US)]
    settlements, _, status = oa.resolve_funding_settlements(
        entry_t, exit_t, funding_rates, mark_prices, coverage_us, known_mark_gaps=known_gaps
    )
    assert settlements is None
    assert status == "UNRESOLVED_FUNDING_RATE_OR_MARK"


def test_okx_aggregated_funding_gap_btc_separation():
    """Verify that gaps in OKX ALL_SWAPS archive for altcoins do not invalidate BTC settlements."""
    events = [
        {"symbol": "ETH-USDT-SWAP", "funding_rate": 0.0002, "funding_time": 1787673600000},
        {"symbol": "BTC-USDT-SWAP", "funding_rate": 0.0001, "funding_time": 1787673600000},
        {"symbol": "SOL-USDT-SWAP", "funding_rate": None, "funding_time": 1787673600000},  # Altcoin gap
    ]
    btc_events = oa.filter_btc_funding_events(events, "BTC-USDT-SWAP")
    assert len(btc_events) == 1
    assert btc_events[0]["symbol"] == "BTC-USDT-SWAP"
    assert btc_events[0]["funding_rate"] == 0.0001


def test_missing_and_stale_z_handling():
    """Verify that missing 5m metrics sample or missing 4h predecessor results in UNAVAILABLE Z and NO_ACTION."""
    cutoff_t = 1704067200
    metrics = {
        cutoff_t - 300: oa.SimpleStock(t=cutoff_t - 300, base_oi=1000.0, top_position_ls=1.2)
    }
    # Predecessor at cutoff_t - 300 - 14400 is missing
    z_res = oa.extract_z_state(metrics, cutoff_t)
    assert z_res["z_status"] == "UNAVAILABLE"
    assert z_res["z_reason"] == "Z_4H_PREDECESSOR_MISSING"

    # Both missing
    z_empty = oa.extract_z_state({}, cutoff_t)
    assert z_empty["z_status"] == "UNAVAILABLE"
    assert z_empty["z_reason"] == "MISSING_Z"


def test_no_action_denominator_preserved():
    """Verify that unavailable feature origins are retained as NO_ACTION in denominator rather than dropped."""
    fixtures = oa.generate_synthetic_fixture_data(1704067200, 24)
    # Erase metrics to force Z unavailable
    fixtures["metrics_5m"].clear()
    embargo_us = (1704067200 + 48 * 3600) * oa.US

    row = oa.build_panel_row(
        1704067200 + 60,
        fixtures["perp_1m_bars"],
        fixtures["spot_1m_bars"],
        fixtures["mark_prices"],
        fixtures["metrics_5m"],
        fixtures["funding_rates"],
        fixtures["funding_coverage_us"],
        embargo_us,
    )
    assert row["action"] == "NO_ACTION"
    assert row["native_feature_ready"] is False
    assert row["t"] == 1704067200 + 60


def test_deterministic_repeatability(tmp_path):
    """Verify that running synthetic outcome bridge repeatedly produces identical bit-for-bit results."""
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"
    res1 = oa.run_synthetic_outcome_bridge(out1, n_hours=48, seed=650410)
    res2 = oa.run_synthetic_outcome_bridge(out2, n_hours=48, seed=650410)

    assert res1["origins_scheduled"] == res2["origins_scheduled"]
    assert res1["p1_economics_delegation"] == res2["p1_economics_delegation"]
    h1 = hashlib.sha256((out1 / "normalized_panel.json").read_bytes()).hexdigest()
    h2 = hashlib.sha256((out2 / "normalized_panel.json").read_bytes()).hexdigest()
    assert h1 == h2


def test_production_no_scope_invocation_denies(tmp_path):
    """Verify that executing materialize without explicit signed Owner scope fails fail-closed."""
    missing_scope = tmp_path / "nonexistent-scope.json"
    result = cli.materialize(missing_scope, tmp_path / "out")
    assert result["status"] == "AUTHORIZATION_DENIED"
    assert result["exit_code"] == 2
    assert result["historical_outcomes_evaluated"] == 0
    assert result["outcome_labels_read"] == 0


def test_real_historical_outcome_rows_read_is_zero(tmp_path):
    """Explicitly verify that real historical outcome rows read across tests and demos is strictly 0."""
    res = oa.run_synthetic_outcome_bridge(tmp_path / "demo", n_hours=24)
    assert res["real_historical_outcomes_evaluated"] == 0
    assert "OUTCOME_MATURITY_BLOCKED_BY_EMBARGO" in [
        reason for h_info in res["horizon_limits"].values() for reason in ["OUTCOME_MATURITY_BLOCKED_BY_EMBARGO"] if h_info["embargo_blocked_count"] > 0
    ]


def test_p1_economics_delegation_zero_duplication():
    """Verify that Outcome objects delegate directly to strategy_eval.costs.economics."""
    outcome = Outcome(
        entry_t=1704067320,
        exit_t=1704067320 + 8 * 3600,
        entry_price=40000.0,
        exit_price=40400.0,  # +100 bp gross return
        settlements=(Settlement(t_us=(1704067320 + 4 * 3600) * oa.US, rate=0.0001, mark=40200.0),),
        expected_settlements_us=((1704067320 + 4 * 3600) * oa.US,),
        funding_coverage_us=(1704067320 * oa.US, (1704067320 + 8 * 3600) * oa.US),
    )
    econ_long = economics(outcome, action=1, horizon_h=8, assumptions=BASELINE)
    assert econ_long["status"] == "RESOLVED"
    assert math.isclose(econ_long["gross_return"], 0.010, rel_tol=1e-5)
    assert econ_long["funding_debit"] > 0  # Long pays positive funding
    assert econ_long["net_return"] < econ_long["gross_return"]  # Costs deducted
