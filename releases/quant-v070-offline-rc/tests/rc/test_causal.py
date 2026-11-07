from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from btc_quant_agent.platform.core import fingerprint
from btc_quant_agent.platform.rc_fixture import DECISION, TRIGGER, future_fixture, wire
from btc_quant_agent.platform.rc_models import CONTRACT_SHA256, RCDecision, frozen_contract
from btc_quant_agent.platform.rc_source import Receipt, canonical, normalize
from btc_quant_agent.platform.rc_strategy import decide_s1
from btc_quant_agent.platform.swing import INTERVALS


def decide(rows, **kwargs):
    return decide_s1(symbol="BTCUSDT", trigger_ms=TRIGGER, decision_ms=DECISION, receipts=rows, **kwargs)


def test_frozen_interface_and_original_b_digest():
    root = Path(__file__).resolve().parents[2]
    data = (root / "contracts/rc_v1.json").read_bytes()
    assert hashlib.sha256(data).hexdigest() == CONTRACT_SHA256
    spec = frozen_contract()
    assert spec["program_b"]["sha256"] == hashlib.sha256((root / "contracts/lt_b_frozen_handoff_v1.json").read_bytes()).hexdigest()
    assert spec["safety"]["market_requests"] == 0
    assert spec["workload_predeclaration"]["seed"] == 7061106


@pytest.mark.parametrize("symbol", ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
def test_real_callable_s1_positive_has_frozen_structural_risk_and_account_veto(symbol, positive_rows):
    d = decide_s1(symbol=symbol, trigger_ms=TRIGGER, decision_ms=DECISION, receipts=positive_rows)
    assert d.market_state == "ARMED" and d.episode_id
    o = d.opportunity
    assert o.direction == "LONG" and o.buffered_stop < o.entry_region[0] <= o.entry_region[1] < min(o.target_zones)
    assert o.planned_after_cost_r >= 2 and d.eligible_planned_r == (2, 3)
    assert d.diagnostics["pivot_confirmation_index"] > d.diagnostics["structural_pivot_index"]
    assert d.diagnostics["structural_confirmation_available_ms"] <= DECISION
    assert max(d.diagnostics["fixed_target_confirmation_ends"]) <= TRIGGER
    assert d.account == "ACCOUNT_UNKNOWN/ACCOUNT_VETO" and o.account_status == "UNKNOWN"
    assert d.actionability == "NOT_ACTIONABLE_ACCOUNT_VETO"
    assert not any((d.source_qualified, d.shadow_advisory_qualified, d.economically_validated))


def test_flat_source_is_independent_genuine_no_setup(flat_rows):
    d = decide(flat_rows)
    assert d.market_state == "NO_SETUP" and d.opportunity is None and d.episode_id is None
    assert d.reasons == ("DAILY_4H_TREND_NOT_ALIGNED",)


@pytest.mark.parametrize("hours", [4, 24, 72, 120])
def test_intraday_and_multi_day_ex_ante_holding_geometry(hours, btc_rows):
    d = decide(btc_rows, holding_hours=hours)
    assert d.opportunity.holding_hours == hours
    assert d.opportunity.planned_after_cost_r >= 2
    assert d.scheduled_review_ms < d.opportunity.expires_ms


def test_optional_hour_absence_is_watch_without_urgency(btc_rows):
    d = decide([r for r in btc_rows if r.bar.candle.interval != "1H"])
    assert d.market_state == "WATCH"
    assert d.diagnostics["optional_1H"] == "ABSENT_NO_URGENCY"


@pytest.mark.parametrize("fault", ["no_source", "missing_daily", "gap", "out_of_order", "stale", "late_review"])
def test_bad_or_insufficient_conditions_fail_closed(fault, btc_rows):
    rows = list(btc_rows)
    trigger, now = TRIGGER, DECISION
    if fault == "no_source":
        rows = []
    elif fault == "missing_daily":
        rows = [r for r in rows if r.bar.candle.interval != "1D"]
    elif fault == "gap":
        del rows[next(i for i, r in enumerate(rows) if r.bar.candle.interval == "4H") + 4]
    elif fault == "out_of_order":
        indices = [i for i, r in enumerate(rows) if r.bar.candle.interval == "4H"]
        rows[indices[3]], rows[indices[4]] = rows[indices[4]], rows[indices[3]]
    elif fault == "stale":
        trigger += INTERVALS["4H"]
        now += INTERVALS["4H"]
    elif fault == "late_review":
        now = TRIGGER + 300001
    d = decide_s1(symbol="BTCUSDT", trigger_ms=trigger, decision_ms=now, receipts=rows)
    assert d.market_state == "DATA_UNAVAILABLE" and d.opportunity is None


def test_raw_and_normalized_roundtrip_and_duplicate_digest_parity(btc_rows, positive):
    normalized = [Receipt.model_validate_json(r.model_dump_json()) for r in btc_rows]
    assert decide(normalized) == positive
    assert decide([*btc_rows, btc_rows[-1]]) == positive
    assert all(normalize(r.raw) == r for r in normalized)


@pytest.mark.parametrize("fault", ["open", "misaligned", "bool_clock", "wrong_authority", "wrong_symbol", "nonfinite", "duplicate_json_key"])
def test_raw_source_boundary_rejects_unsafe_inputs(fault, btc_rows):
    r = btc_rows[-1]
    value = json.loads(r.raw)
    if fault == "open":
        value["candle"]["closed"] = False
    elif fault == "misaligned":
        value["candle"]["open_time_ms"] += 1
    elif fault == "bool_clock":
        value["received_ms"] = True
    elif fault == "wrong_authority":
        value["venue"] = "NATIVE"
    elif fault == "wrong_symbol":
        value["candle"]["symbol"] = "XRPUSDT"
    elif fault == "nonfinite":
        value["candle"]["volume"] = float("nan")
        with pytest.raises(ValueError):
            normalize(json.dumps(value))
        return
    else:
        with pytest.raises(ValueError, match="DUPLICATE_JSON_KEY"):
            normalize(r.raw[:-1] + ',"revision":0}')
        return
    with pytest.raises((ValueError, TypeError)):
        normalize(canonical(value))


def test_binding_hashes_cannot_be_substituted(btc_rows):
    raw = btc_rows[0].model_dump(mode="json")
    raw["raw_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="HASH_BINDING"):
        Receipt.model_validate_json(canonical(raw))


def test_future_candle_and_future_revision_cannot_change_past(positive, btc_rows):
    future = future_fixture(positive)
    original = btc_rows[-1].bar
    revised_candle = replace(original.candle, high=original.candle.high * 2)
    revision = normalize(wire(revised_candle, revision=1, at_ms=DECISION + INTERVALS["1H"]))
    for multiple in (1.0, 2.0, 10.0):
        changed = []
        for r in future:
            c = r.bar.candle
            changed.append(normalize(wire(replace(c, open=c.open * multiple, high=c.high * multiple,
                                                  low=c.low * multiple, close=c.close * multiple))))
        assert decide([*btc_rows, *changed, revision]) == positive
    later = decide_s1(symbol="BTCUSDT", trigger_ms=TRIGGER + INTERVALS["4H"],
                     decision_ms=DECISION + INTERVALS["4H"], receipts=[*btc_rows, revision])
    assert later.market_state == "DATA_UNAVAILABLE"
    assert "VISIBLE_REVISION_UNRESOLVED" in later.reasons


def test_explicit_rc_version_and_geometry_cannot_inflate_labels(positive):
    raw = positive.model_dump(mode="json")
    raw["eligible_planned_r"] = [2, 3, 4]
    with pytest.raises(ValueError, match="R_LABEL"):
        RCDecision.model_validate_json(canonical(raw))
    raw = positive.model_dump(mode="json")
    raw["source_qualified"] = True
    with pytest.raises(ValueError):
        RCDecision.model_validate_json(canonical(raw))
    raw = positive.model_dump(mode="json")
    raw["opportunity"]["account_status"] = "NOT_REQUESTED"
    with pytest.raises(ValueError, match="ACCOUNT_VETO"):
        RCDecision.model_validate_json(canonical(raw))
    raw = positive.model_dump(mode="json")
    raw["opportunity"]["expires_ms"] = raw["scheduled_review_ms"]
    raw["opportunity"]["review_deadline_ms"] = raw["scheduled_review_ms"]
    with pytest.raises(ValueError, match="ACCOUNT_VETO"):
        RCDecision.model_validate_json(canonical(raw))
    assert fingerprint(positive.model_dump(mode="json")) == fingerprint(json.loads(positive.model_dump_json()))


def test_frozen_raw_fixture_bytes_match_reproducible_generator_and_real_pipeline(positive_rows, flat_rows):
    root = Path(__file__).resolve().parents[2] / "fixtures"
    manifest = json.loads((root / "SYNTHETIC_FIXTURE_MANIFEST.json").read_text())
    assert manifest["exposure"] == "SYNTHETIC" and manifest["seed"] == 7061106
    for item in manifest["files"]:
        data = (root / item["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == item["sha256"]
        rows = tuple(normalize(line) for line in data.decode().splitlines())
        assert len(rows) == item["rows"]
        assert fingerprint([r.model_dump(mode="json") for r in rows]) == item["normalized_digest"]
        if "positive" in item["path"]:
            assert rows == positive_rows and decide(rows).market_state == "ARMED"
        elif "all_no_setup" in item["path"]:
            assert rows == flat_rows and decide(rows).market_state == "NO_SETUP"
