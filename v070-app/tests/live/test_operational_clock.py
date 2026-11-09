"""Synthetic clock domains and real loopback TLS only; never N market payloads."""

from __future__ import annotations
import json
from pathlib import Path

import pytest

from btc_quant_agent.platform.live import operational_clock as oc
from btc_quant_agent.platform.live import store as store_module
from btc_quant_agent.platform.live.models import Blocked, QA, POLICY, sample
from btc_quant_agent.platform.live.store import Store
from btc_quant_agent.platform.live.swing_review import VERSION as L_VERSION, product_for as l_product
from local_swing import SwingVenue


class Venue(SwingVenue):
    time_fault = None

    def body(self, path):
        value = super().body(path)
        if "/fapi/v1/time" in path and self.time_fault == "regress" and len(self.calls) > 5:
            value["serverTime"] -= 100000
        if "/fapi/v1/klines" in path and "limit=1&" in path:
            pass
        if (
            self.market_fault == "target"
            and "/fapi/v1/klines" in path
            and "limit=1" in path
            and len(value) == 1
        ):
            value[0][2] = "1000000"
        return value


class Script:
    def __init__(self):
        self.offset = 0

    def sample(self):
        s = sample()
        s["wall_ms"] = s["mono_before_ms"] + 1000000000000 + self.offset
        return s

    def control(self):
        s = self.sample()
        # Explicit fabricated stable auxiliary clock domains, not host telemetry.
        s.update(
            raw_ms=s["mono_before_ms"] + 1000,
            boottime_ms=s["mono_before_ms"] + 2000,
            control_end_ms=s["mono_after_ms"],
        )
        return s


class FaultTransport:
    def __init__(self, base, script, collector, jumps):
        self.base, self.script, self.collector, self.jumps = base, script, collector, jumps

    def request(self, route, params, timeout):
        offset = self.script.offset
        result = self.base.request(route, params, timeout)
        delta = self.jumps.get(self.collector.requests, 0)
        result["request_sample"]["wall_ms"] = (
            result["request_sample"]["mono_before_ms"] + 1000000000000 + offset
        )
        self.script.offset += delta
        result["receive_sample"]["wall_ms"] = (
            result["receive_sample"]["mono_before_ms"] + 1000000000000 + self.script.offset
        )
        return result


@pytest.fixture
def capture(tmp_path, monkeypatch):
    script = Script()
    monkeypatch.setattr(oc, "sample", script.sample)
    monkeypatch.setattr(oc, "control_sample", script.control)
    monkeypatch.setattr(store_module, "sample", script.sample)
    venues = []

    def make(*, jumps=None, flat=False, fault=None, minutes=30, source_fault=None, shadow=False):
        v = Venue(tmp_path / "tls", minutes=minutes, flat=flat, market_fault=fault)
        venues.append(v)
        v.time_fault = source_fault
        s = Store(tmp_path / "store", create=True, exposure=QA)
        p = oc.product_for(s, oc.VERSION, 120)
        cls = oc.OperationalObserver if shadow else oc.OperationalCollector
        c = cls(s, _qa=v.qa)
        c.transport = FaultTransport(c.transport, script, c, jumps or {})
        return s, p, c, v, script

    yield make
    for v in venues:
        v.close()


@pytest.mark.parametrize(
    "jumps,requests",
    [({}, 12), ({2: -799}, 23), ({9: 918}, 23), ({2: -799, 9: 918}, 23), ({2: -799, 5: 100, 9: 918}, 23)],
)
def test_complete_post_anomaly_witness_positive(capture, jumps, requests):
    s, p, c, _, _ = capture(jumps=jumps)
    snap = c.run()
    assert snap["requests"] == requests and snap["request_weight"] in (15, 29)
    d = p.review("BTCUSDT")
    assert d.market_state == "WATCH" and d.exposure == QA
    assert d.contract_sha256 == oc.HASH and d.review_local.wall_ms != d.decision_ms
    assert d.clock_evidence["witness_used"] == bool(jumps)
    assert d.opportunity.available_ms <= d.decision_ms
    assert [p.review(x).market_state for x in ("ETHUSDT", "SOLUSDT")] == ["NO_SETUP", "NO_SETUP"]
    if jumps:
        assert [e["wall_minus_mono_change_ms"] for e in s.events.values("O_WALL_CLOCK_DEGRADED")] == list(
            jumps.values()
        )
        assert snap["clock"] == "CLOCK_DEGRADED_RECONCILED"
        first = snap["o_clock"]["accepted_pass"][0]
        assert first == 13 and all(e["ordinal"] < first for e in snap["o_clock"]["wall_steps"])
    assert not d.source_qualified and not d.economically_validated


@pytest.mark.parametrize(
    "jumps", [{2: -799, 19: 918}, {2: -799, 13: 918}, {2: -799, 23: 100}, {2: -799, 9: 918, 20: -250}]
)
def test_second_epoch_step_in_witness_cannot_be_ignored(capture, jumps):
    s, p, c, _, _ = capture(jumps=jumps)
    with pytest.raises(Blocked, match="WITNESS_CLOCK"):
        c.run()
    assert not s.snapshots() and not p.decisions()
    assert len(s.events.values("REQUEST_ADMITTED")) == 23
    assert s.events.values("SESSION_TERMINAL")[-1]["status"] == "FAILED"


def test_normal_all_NO_SETUP_existing_html_shadow_C_and_restart(capture, tmp_path):
    s, p, c, _, _ = capture(flat=True)
    c.run()
    decisions = [p.review(x) for x in POLICY["symbols"]]
    assert [d.market_state for d in decisions] == ["NO_SETUP"] * 3
    html = Path(p.dashboard()["dashboard"]).read_text()
    assert oc.VERSION in html and QA in html
    restored = oc.product_for(Store(s.directory))
    assert restored.decisions() == decisions
    report = restored.evaluate(tmp_path / "C_gate")
    assert (
        report["scientific_decision"] == "INSUFFICIENT_SUPPORT"
        and report["actual_C_validator_error"] == "SOURCE_CLASS_INVALID"
    )


def test_positive_frozen_Shadow_and_replay(capture, tmp_path):
    s, p, c, _, _ = capture(jumps={2: -799, 9: 918})
    c.run()
    d = p.review("BTCUSDT")
    original = d.model_dump(mode="json")
    identity = d.episode_id
    assert p.observe(identity)["outcome"] == "INSUFFICIENT_FUTURE_HORIZON"
    restored = oc.product_for(Store(s.directory))
    assert restored.review("BTCUSDT").model_dump(mode="json") == original
    assert restored.episode(identity)["anchors"]["decision"] == original
    assert Path(restored.dashboard()["dashboard"]).exists()
    report = p.evaluate(tmp_path / "C")
    assert report["actual_C_validator_error"] == "SOURCE_CLASS_INVALID"


@pytest.mark.parametrize(
    "fault,reason", [("chase", "NO_CHASE"), ("pivot", "PIVOT_INVALIDATED"), ("target", "TARGET_ALREADY")]
)
def test_invalid_current_path_never_arms(capture, fault, reason):
    _, p, c, _, _ = capture(fault=fault)
    c.run()
    d = p.review("BTCUSDT")
    assert d.market_state == "NO_SETUP" and d.opportunity is None and any(reason in r for r in d.reasons)


@pytest.mark.parametrize("fault", ["wrong_interval", "wrong_cycle", "no_current"])
def test_current_partial_identity_fault(capture, fault):
    s, _, c, _, _ = capture(fault=fault)
    with pytest.raises(Blocked, match="OBSERVATION"):
        c.run()
    assert not s.snapshots()


def test_completed_gap_or_revision_blocks(capture):
    s, _, c, v, _ = capture()
    v.data[("BTCUSDT", "4H")].pop(-3)
    with pytest.raises(Blocked, match="GAP"):
        c.run()
    assert not s.snapshots()


def test_venue_time_regression_is_fatal_not_wall_warning(capture):
    s, _, c, _, _ = capture(jumps={2: -799}, source_fault="regress")
    with pytest.raises(Blocked, match="REGRESSION|BRACKETS"):
        c.run()
    assert not s.snapshots() and len(s.events.values("REQUEST_ADMITTED")) == 12


def test_reference_width_5s_not_relaxed():
    def stamp(t):
        return {"mono_before_ms": t, "mono_after_ms": t, "wall_ms": t + 1000000, "boot_id": "SYNTHETIC"}

    a = (
        {"serverTime": 1000000},
        {"request_sample": stamp(100), "receive_sample": stamp(6100), "body_sha256": "a" * 64},
    )
    b = (
        {"serverTime": 1010000},
        {"request_sample": stamp(10100), "receive_sample": stamp(16100), "body_sha256": "b" * 64},
    )
    with pytest.raises(Blocked, match="BRACKETS"):
        oc.reference(a, b)


@pytest.mark.parametrize("fault", ["rollback", "boot", "raw_step", "suspend"])
def test_monotonic_or_epoch_uncertainty_hard_stop(fault):
    a = {
        "wall_ms": 100000,
        "mono_before_ms": 1000,
        "mono_after_ms": 1000,
        "boot_id": "SYNTHETIC",
        "raw_ms": 2000,
        "boottime_ms": 3000,
        "control_end_ms": 1000,
    }
    b = {
        **a,
        "wall_ms": 100100,
        "mono_before_ms": 1100,
        "mono_after_ms": 1100,
        "raw_ms": 2100,
        "boottime_ms": 3100,
        "control_end_ms": 1100,
    }
    if fault == "rollback":
        b.update(mono_before_ms=900, mono_after_ms=900, control_end_ms=900)
    if fault == "boot":
        b["boot_id"] = "OTHER"
    if fault == "raw_step":
        b["raw_ms"] += 1000
    if fault == "suspend":
        b["boottime_ms"] += 1000
    with pytest.raises(Blocked, match="MONOTONIC|BOOT"):
        oc.control_check(a, b)


def test_late_review_stale_price_and_new_wall_step_block(capture, monkeypatch):
    s, p, c, _, script = capture()
    snap = c.run()
    original = script.control

    def stale():
        q = original()
        for k in ("mono_before_ms", "mono_after_ms", "raw_ms", "boottime_ms", "control_end_ms", "wall_ms"):
            q[k] += 31000
        return q

    monkeypatch.setattr(oc, "control_sample", stale)
    assert p.review("BTCUSDT")["status"] in (
        "SOURCE_BLOCKED",
        "LIVE_CLOCK_DEGRADED_BLOCKED",
        "LIVE_SOURCE_UNAVAILABLE",
    )
    monkeypatch.setattr(oc, "control_sample", original)
    script.offset += 918
    result = p.review("BTCUSDT")
    assert "WALL_STEP_AFTER_PROOF" in result["reason"]
    assert not p.decisions() and s.events.values("REVIEW_BLOCKED")
    assert snap["o_clock"]["strict_UTC_qualified"] is False


@pytest.mark.parametrize("minutes", [1, 121, 239])
def test_grace_and_review_expiry_remain(capture, minutes):
    s, p, c, _, _ = capture(minutes=minutes)
    if minutes == 1:
        with pytest.raises(Blocked, match="NOT_CURRENT"):
            c.run()
    else:
        c.run()
        assert p.review("BTCUSDT")["status"] == "SOURCE_BLOCKED"
    assert not p.decisions()


def test_clock_proof_tamper_and_no_legacy_promotion(capture, tmp_path):
    s, _, c, _, _ = capture(jumps={2: -799, 9: 918})
    snap = c.run()
    altered = json.loads(json.dumps(snap))
    altered["o_clock"]["wall_steps"] = []
    with pytest.raises(Blocked, match="EVIDENCE_TAMPER"):
        oc.verify_snapshot(s, altered)
    with pytest.raises(Blocked, match="IMMUTABLE"):
        oc.product_for(s, L_VERSION)
    old = Store(tmp_path / "old", create=True, exposure=QA)
    l_product(old, L_VERSION)
    with pytest.raises(Blocked, match="FRESH_OUTPUT"):
        oc.product_for(old, oc.VERSION)


def test_budget_before_socket_and_single_witness_only(capture):
    s, _, c, _, _ = capture()
    c.requests = 24
    with pytest.raises(Blocked, match="BUDGET"):
        c.get("/fapi/v1/time", {})
    assert not s.events.values("REQUEST_ADMITTED")


def test_old_source_and_strict_clock_bytes_untouched():
    root = Path(__file__).resolve().parents[2]
    import hashlib

    original = json.loads((root / "contracts/O_FROZEN_L_CODE.json").read_text())["files"]
    names = [
        "models.py",
        "source.py",
        "swing_review.py",
        "rest.py",
        "product.py",
        "policy.json",
        "swing_review_v2.json",
    ]
    for row in original:
        if row["path"].startswith("src/btc_quant_agent/platform/live/") and Path(row["path"]).name in names:
            assert hashlib.sha256((root / row["path"]).read_bytes()).hexdigest() == row["sha256"]
    assert oc.CONTRACT["wall_step_ms"] == 50 and oc.POLICY["clock_jump_ms"] == 50


def test_unknown_intrabar_order_preserved(capture):
    from btc_quant_agent.platform.rc_fixture import future_fixture
    from btc_quant_agent.platform.rc_observe import observe_path
    from btc_quant_agent.platform.live.product import JObservation

    _, p, c, _, _ = capture()
    c.run()
    d = p.review("BTCUSDT")
    rows = future_fixture(d, scenario="ambiguous")
    outcome = observe_path(
        d,
        rows,
        asof_ms=d.decision_ms + 60 * oc.INTERVALS["1H"],
        decision_parser=oc.OperationalDecision.model_validate_json,
        observation_factory=lambda **kw: JObservation(**kw, exposure=QA),
    )
    assert outcome.outcome == "AMBIGUOUS_OHLC_ORDER_UNKNOWN"
    assert not outcome.actual_fill and not outcome.economic_evidence


def test_completed_revision_in_witness_fails_closed(capture):
    s, _, c, v, _ = capture(jumps={2: -799})
    body = v.body

    def revised(path):
        result = body(path)
        if c.requests >= 14 and "/klines" in path and len(result) > 1:
            result[-1][5] = str(float(result[-1][5]) + 1)
        return result

    v.body = revised
    with pytest.raises(Blocked, match="REVISED_OR_CHANGED"):
        c.run()
    assert s.events.values("SOURCE_STOP") and not s.snapshots()


def test_reference_age_and_mismatched_venue_evidence_rejected():
    r = {"offset_lower_ms": 1000, "offset_upper_ms": 1002, "at_mono_ms": 100, "boot_id": "QA"}
    with pytest.raises(Blocked, match="STALE"):
        oc.project(r, {"mono_before_ms": 120101, "mono_after_ms": 120101, "boot_id": "QA"}, 120000)
    with pytest.raises(Blocked, match="MISMATCH"):
        oc.reconcile_reference(r, {**r, "offset_lower_ms": 7000, "offset_upper_ms": 7002})


def test_weight_and_elapsed_budget_no_request(capture):
    s, _, c, _, _ = capture()
    c.weight = 40
    with pytest.raises(Blocked, match="BUDGET"):
        c.get("/fapi/v1/time", {})
    c.weight = 0
    c.deadline = c.start["mono_before_ms"] - 1
    with pytest.raises(Blocked, match="DURATION"):
        c.get("/fapi/v1/time", {})
    assert not s.events.values("REQUEST_ADMITTED")


def test_rejected_control_counters_are_durable_not_only_an_error_string(capture, monkeypatch):
    s, _, c, v, script = capture()

    def broken():
        stamp = script.control()
        stamp["raw_ms"] += 918
        stamp["wall_ms"] -= 799
        return stamp

    monkeypatch.setattr(oc, "control_sample", broken)
    with pytest.raises(Blocked, match="RAW_OR_BOOTTIME"):
        c.run()
    event = s.events.values("O_CONTROL_CLOCK_REJECTED")[-1]
    assert event["quality"] == "CLOCK_DEGRADED" and event["admission"] == "HARD_STOP"
    assert event["observed"]["raw_ms"] - event["observed"]["mono_before_ms"] == 1918
    assert event["previous"] == event["anchor"]
    assert Store(s.directory).events.values("O_CONTROL_CLOCK_REJECTED")[-1] == event
    assert not v.calls and not s.snapshots() and s.events.values("O_FATAL_STOP")
