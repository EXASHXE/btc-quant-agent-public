"""All market bytes and certificates here are explicitly fabricated loopback QA."""

from __future__ import annotations

from pathlib import Path
import json

import pytest

from btc_quant_agent.platform.live.cli import main
from btc_quant_agent.platform.live.models import Blocked, QA, POLICY, POLICY_HASH, sample
from btc_quant_agent.platform.live.product import Product
from btc_quant_agent.platform.live.store import Store
from btc_quant_agent.platform.live.swing_review import (
    VERSION,
    V2_HASH,
    SwingCollector,
    SwingDecision,
    product_for,
    verify_market,
    actionability,
)
from btc_quant_agent.platform.rc_fixture import TRIGGER
from btc_quant_agent.platform.swing import SwingPolicy
from local_swing import SwingVenue


@pytest.fixture
def swing_capture(tmp_path):
    venues = []

    def capture(*, minutes=30, market_fault=None, flat=False, dirname="capture", **kwargs):
        v = SwingVenue(tmp_path / (dirname + "_tls"), minutes=minutes, market_fault=market_fault, flat=flat)
        venues.append(v)
        s = Store(tmp_path / dirname, create=True, exposure=QA)
        p = product_for(s, VERSION, kwargs.pop("window_minutes", 120))
        fault = kwargs.pop("series_fault", None)
        series = v.data[("BTCUSDT", "4H")]
        if fault == "gap":
            series.pop(-5)
        elif fault == "missing_latest":
            series.pop()
        elif fault == "incomplete":
            series[-1][6] += 1
        elif fault == "insufficient":
            v.data[("BTCUSDT", "4H")] = series[-20:]
        snap = SwingCollector(s, _qa=v.qa, **kwargs).run()
        return s, p, snap, v

    yield capture
    for v in venues:
        v.close()


@pytest.mark.parametrize("minutes", [3, 30, 119])
def test_later_actual_manual_reviews_positive_S1_no_backdating(swing_capture, minutes):
    s, p, snap, _ = swing_capture(minutes=minutes)
    d = p.review("BTCUSDT")
    assert d.market_state == "WATCH" and d.opportunity and d.exposure == QA
    assert d.decision_ms >= TRIGGER + minutes * 60000
    assert d.review_local.mono_before_ms >= snap["last_sample"]["mono_before_ms"]
    assert d.opportunity.setup_close_ms == TRIGGER < d.opportunity.available_ms <= d.decision_ms
    assert d.diagnostics["signal_issued_at_close"] is False
    assert d.market_observation["kind"] == "CURRENT_PARTIAL_4H_NOT_A_COMPLETED_SIGNAL_BAR"
    assert all(r["candle"]["closed"] and r["candle"]["close_time_ms"] < TRIGGER for r in d.admitted_prefix)
    assert [p.review(sym).market_state for sym in ("ETHUSDT", "SOLUSDT")] == ["NO_SETUP", "NO_SETUP"]
    assert snap["requests"] in (14, 22) and snap["request_weight"] <= 40
    assert snap["requests"] == len(s.events.values("REQUEST_ADMITTED"))
    assert not d.source_qualified and not d.economically_validated


@pytest.mark.parametrize("minutes", [121, 239])
def test_after_horizon_not_armed(swing_capture, minutes):
    _, p, _, _ = swing_capture(minutes=minutes)
    d = p.review("BTCUSDT")
    assert d["status"] == "SOURCE_BLOCKED" and "HORIZON_EXPIRED" in d["reason"]
    assert not p.decisions()


def test_configured_shorter_horizon_and_no_mode_migration(swing_capture, tmp_path):
    s, p, _, _ = swing_capture(minutes=30, window_minutes=20)
    assert p.review("BTCUSDT")["status"] == "SOURCE_BLOCKED"
    with pytest.raises(Blocked, match="IMMUTABLE"):
        product_for(s, VERSION, 120)
    with pytest.raises(Blocked, match="IMMUTABLE"):
        product_for(s, "J_OPERATIONAL_POLICY_V1")
    old = Store(tmp_path / "old", create=True, exposure=QA)
    old.events.append("SESSION_START", {"session": "prior_attempt"})
    with pytest.raises(Blocked, match="FRESH_OUTPUT"):
        product_for(old, VERSION)


@pytest.mark.parametrize("minutes", [0, 1])
def test_no_confirmation_grace_no_setup(swing_capture, minutes):
    # The current OHLC itself cannot be admitted before the 120s minimum grace.
    with pytest.raises(Blocked, match="NOT_CURRENT"):
        swing_capture(minutes=minutes)


@pytest.mark.parametrize("fault,reason", [("chase", "NO_CHASE"), ("pivot", "PIVOT_INVALIDATED")])
def test_current_price_and_since_close_path_revalidation(swing_capture, fault, reason):
    _, p, _, _ = swing_capture(market_fault=fault)
    d = p.review("BTCUSDT")
    assert d.market_state == "NO_SETUP" and d.opportunity is None and d.episode_id is None
    assert any(reason in r for r in d.reasons)


@pytest.mark.parametrize("fault", ["wrong_interval", "wrong_cycle", "no_current"])
def test_incomplete_current_observation_not_signal_or_eligible(swing_capture, fault):
    with pytest.raises(Blocked, match="OBSERVATION"):
        swing_capture(market_fault=fault)


def test_all_no_setup_and_existing_html(swing_capture):
    _, p, _, _ = swing_capture(flat=True)
    assert [p.review(s).market_state for s in POLICY["symbols"]] == ["NO_SETUP"] * 3
    html = Path(p.dashboard()["dashboard"]).read_text()
    assert VERSION in html and QA in html and "ACCOUNT_VETO" in html


def test_quote_stale_blocks_new_review(swing_capture, monkeypatch):
    _, p, _, _ = swing_capture()
    from btc_quant_agent.platform.live import product as mod

    previous = mod.sample

    def later():
        s = previous()
        return {
            **s,
            "mono_before_ms": s["mono_before_ms"] + 31000,
            "mono_after_ms": s["mono_after_ms"] + 31000,
            "wall_ms": s["wall_ms"] + 31000,
        }

    monkeypatch.setattr(mod, "sample", later)
    d = p.review("BTCUSDT")
    assert d["status"] in ("SOURCE_BLOCKED", "LIVE_CLOCK_DEGRADED_BLOCKED")
    assert not p.decisions()


def test_clock_jump_reacquisition_retains_24_budget(swing_capture, monkeypatch):
    # Force only the initial hold, then exercise the original complete reacquisition.
    from btc_quant_agent.platform.live import source

    monkeypatch.setattr(source, "offset_step", lambda *_: False)
    import platform

    monkeypatch.setattr(platform, "release", lambda: "microsoft-WSL2-QA")
    s, p, snap, _ = swing_capture()
    assert snap["requests"] == 22 and snap["clock"] == "CLOCK_DEGRADED_RECONCILED"
    assert p.review("BTCUSDT").clock_condition == "CLOCK_DEGRADED_RECONCILED"
    assert s.events.values("CLOCK_RECONCILIATION")


def test_jump_during_current_quote_check_fails_closed(swing_capture, monkeypatch):
    from btc_quant_agent.platform.live import swing_review as mod

    monkeypatch.setattr(mod, "offset_step", lambda *_: True)
    with pytest.raises(Blocked, match="CLOCK_JUMP"):
        swing_capture()


def test_review_clock_jump_blocks(swing_capture, monkeypatch):
    _, p, _, _ = swing_capture()
    from btc_quant_agent.platform.live import product as mod

    prev = mod.sample
    monkeypatch.setattr(mod, "sample", lambda: {**prev(), "wall_ms": prev()["wall_ms"] + 1760})
    d = p.review("BTCUSDT")
    assert d["status"] == "LIVE_CLOCK_DEGRADED_BLOCKED" and not p.decisions()


def test_frozen_decision_shadow_restart_and_C_boundary(swing_capture, tmp_path):
    s, p, _, _ = swing_capture()
    d = p.review("BTCUSDT")
    original = d.model_dump(mode="json")
    assert p.observe(d.episode_id)["outcome"] == "INSUFFICIENT_FUTURE_HORIZON"
    restored = product_for(Store(s.directory))
    assert restored.decisions()[0].model_dump(mode="json") == original
    assert restored.review("BTCUSDT").episode_id == d.episode_id
    assert restored.episode(d.episode_id)["anchors"]["decision"] == original
    report = restored.evaluate(tmp_path / "C")
    assert report["actual_C_validator_error"] == "SOURCE_CLASS_INVALID"
    assert report["scientific_decision"] == "INSUFFICIENT_SUPPORT"
    assert not report["C_economic_ledger_executed"]


def test_frozen_market_receipt_tamper_rejected(swing_capture):
    s, p, snap, _ = swing_capture()
    p.review("BTCUSDT")
    snap["swing_market"]["observations"][0]["price"] += 1
    with pytest.raises(Blocked, match="LINEAGE"):
        verify_market(s, snap, sample())


def test_historical_review_and_future_availability_rejected(swing_capture):
    s, p, _, _ = swing_capture()
    d = p.review("BTCUSDT")
    value = d.model_dump(mode="json")
    value["decision_ms"] = TRIGGER + 180000
    value["review_source_bounds_ms"] = [TRIGGER + 180000, TRIGGER + 180001]
    with pytest.raises(ValueError, match="CAUSALITY"):
        SwingDecision.model_validate_json(json.dumps(value))
    assert all(r["candle"]["available_at_ms"] > TRIGGER for r in value["admitted_prefix"])
    assert all(r["candle"]["close_time_ms"] < TRIGGER for r in value["admitted_prefix"])


def test_original_V1_hash_delay_and_research_clock_unchanged(swing_capture):
    assert POLICY_HASH == "340c3c2b0f7788203b8fdcab36b74fdd982a4d3d7e276b03a69fe681511707ba"
    assert POLICY["review_delay_ms_max"] == SwingPolicy().max_availability_delay_ms == 300000
    _, p, snap, _ = swing_capture()
    old = Product(p.store).review("BTCUSDT")
    assert old["status"] == "SOURCE_BLOCKED"
    from btc_quant_agent.platform.native.clock import Clock

    clock = Clock()
    clock.pair = lambda: {"wall_ms": 1000, "mono_before_ms": 100, "mono_after_ms": 100}
    clock.sample()
    clock.pair = lambda: {"wall_ms": 1200, "mono_before_ms": 110, "mono_after_ms": 110}
    with pytest.raises(ValueError, match="50MS"):
        clock.sample()
    assert clock.failed is not None and V2_HASH != POLICY_HASH


def test_missing_access_v2_cli_zero_socket_and_no_store(tmp_path, capsys):
    out = tmp_path / "never_created"
    assert main(["scan", "--review-policy", VERSION, "--output", str(out)]) == 2
    assert not out.exists() and "ACCESS" in capsys.readouterr().out


@pytest.mark.parametrize("minutes", [-1, 0, 4, 121, 240])
def test_unbounded_policy_rejected(tmp_path, minutes):
    s = Store(tmp_path / str(minutes), create=True, exposure=QA)
    with pytest.raises(Blocked, match="5_TO_120"):
        product_for(s, VERSION, minutes)


def test_expired_target_and_stop_geometry_gate(swing_capture):
    _, p, _, _ = swing_capture()
    d = p.review("BTCUSDT")
    plan = d.opportunity
    q = d.market_observation
    assert actionability(plan, q, plan.expires_ms) == "SWING_SETUP_EXPIRED"
    target = {**q, "high": min(plan.target_zones)}
    assert "TARGET_ALREADY" in actionability(plan, target, d.decision_ms)
    assert plan.entry_region[0] <= q["price"] <= plan.entry_region[1]
    assert plan.buffered_stop < plan.entry_region[0] < min(plan.target_zones)


@pytest.mark.parametrize("fault", ["gap", "missing_latest", "incomplete", "insufficient"])
def test_incomplete_or_gapped_completed_history_blocks(swing_capture, fault):
    with pytest.raises(Blocked, match="GAP|ALIGNMENT|ENOUGH"):
        swing_capture(series_fault=fault)


def test_quote_only_not_used_as_hourly_confirmation(swing_capture):
    _, p, snap, _ = swing_capture(minutes=119)
    d = p.review("BTCUSDT")
    assert d.market_state == "WATCH"
    assert d.diagnostics["optional_1H"] == "ABSENT_NO_URGENCY"
    assert not any(r["candle"]["interval"] == "1H" for r in snap["records"])
    assert not d.episode_id.startswith("SYNTHETIC")


def test_uncertainty_straddling_horizon_and_quote_causality_rejected(swing_capture):
    _, p, _, _ = swing_capture(minutes=119)
    d = p.review("BTCUSDT")
    value = d.model_dump(mode="json")
    value["review_source_bounds_ms"][1] = TRIGGER + 120 * 60000 + 1
    with pytest.raises(ValueError, match="REVIEW_WINDOW"):
        SwingDecision.model_validate_json(json.dumps(value))
    value = d.model_dump(mode="json")
    value["market_observation"]["available_bounds_ms"][1] = d.decision_ms + 1
    with pytest.raises(ValueError, match="PRICE_CAUSALITY"):
        SwingDecision.model_validate_json(json.dumps(value))


def test_repeat_review_cannot_reissue_invalidated_frozen_plan(swing_capture):
    s, p, _, venue = swing_capture()
    d = p.review("BTCUSDT")
    original = d.model_dump(mode="json")
    venue.market_fault = "chase"
    SwingCollector(s, _qa=venue.qa).run()
    rejected = p.review("BTCUSDT")
    assert rejected["status"] == "NO_SETUP" and rejected["candidate_disposition"] == "NO_CHASE"
    assert not rejected["new_candidate"]
    venue.market_fault = None
    SwingCollector(s, _qa=venue.qa).run()
    rejected_again = product_for(Store(s.directory)).review("BTCUSDT")
    assert rejected_again["reason"] == "SWING_EPISODE_TERMINAL_NO_REACTIVATION"
    assert p.decisions()[0].model_dump(mode="json") == original
    assert p.episode(d.episode_id)["state"]["status"] == "NO_CHASE"
    assert len(s.events.values("MANUAL_REVALIDATION")) == 2
    assert all(e["new_decision_created"] is False for e in s.events.values("MANUAL_REVALIDATION"))


def test_v2_shadow_observe_retains_hourly_path_without_new_candidate_promotion(swing_capture):
    from btc_quant_agent.platform.live.swing_review import SwingObservationCollector

    s, p, _, venue = swing_capture()
    d = p.review("BTCUSDT")
    original = d.model_dump(mode="json")
    later = SwingObservationCollector(s, _qa=venue.qa).run()
    assert later["requests"] in (12, 23) and later["request_weight"] <= 40
    assert sum(r["candle"]["interval"] == "1H" for r in later["records"]) == 3 * 72
    assert p.review("BTCUSDT")["status"] == "SOURCE_BLOCKED"
    assert p.observe(d.episode_id)["outcome"] == "INSUFFICIENT_FUTURE_HORIZON"
    assert p.decisions()[0].model_dump(mode="json") == original
    assert p.snapshot()["data"]["new_candidate_generation"] == "SOURCE_BLOCKED_SHADOW_OBSERVATION_ONLY"
