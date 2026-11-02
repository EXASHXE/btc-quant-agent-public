"""Existing runtime/renderer integration; every positive fixture is SYNTHETIC."""

import copy
import json
import threading

import pytest

from btc_quant_agent.platform.canary.longhorizon_runtime import write_snapshot, save_dashboard
from btc_quant_agent.platform.canary.longhorizon_view import adapt, producer_identity
from .fixtures import engine_at, quote


@pytest.fixture
def produced(tmp_path):
    c, s, store, journal, engine = engine_at(tmp_path / "engine")
    c.advance(100)
    for i in range(1, 5):
        quote(engine, c, sequence=i)
        c.advance(5)
    engine.flush()
    return engine.report(), engine


def test_actual_producer_schema_clock_fields_and_independent_tiers(produced):
    model, _ = produced
    view = adapt(model)
    q = view["symbols"][0]["quote"]["value"]
    assert q["native_T"] == q["native_E"] - 2
    assert q["native_E"] > q["local_receipt_utc_ms"]  # Valid native-ahead clock, no raw-wall shortcut.
    assert view["evidence_kind"] == "SYNTHETIC"
    assert all(f["state"] == "FALSE" for f in view["qualifications"].values())
    assert view["ranking"]["required"] == 10 and view["ranking"]["members"] == 3
    assert view["account_side"]["state"] == "ACCOUNT_VETO" and view["actual_fills"] is None
    assert view["symbols"][0]["quote"]["input_sha256"] == view["input_sha256"]


def test_missing_partial_fields_never_become_zero_or_synthetic_quote(produced):
    model, _ = produced
    model.pop("clock_readiness")
    model.pop("clock_estimate")
    model["per_symbol"]["BTCUSDT"]["quote"] = None
    model["per_symbol"]["BTCUSDT"]["bars"] = None
    model["per_symbol"].pop("ETHUSDT")
    view = adapt(model)
    assert view["symbols"][0]["quote"]["value"] is None
    assert view["symbols"][0]["bars"]["value"] is None
    assert view["symbols"][1]["regime"]["state"] == "UNKNOWN"
    assert view["clock"]["state"] == "UNKNOWN"


@pytest.mark.parametrize("elapsed,state", [(5000, "AS_OF_SNAPSHOT_NOT_LIVE_BROWSER"), (5001, "STALE")])
def test_snapshot_lease_equality_and_stale_readiness(produced, elapsed, state):
    model, _ = produced
    view = adapt(model, now_ms=model["as_of_utc_ms"] + elapsed)
    assert view["snapshot_state"] == state
    if elapsed > 5000:
        assert view["symbols"][0]["quote"]["state"] == "STALE_SNAPSHOT"


@pytest.mark.parametrize(
    "field,value", [("probe_age_ms", 300001), ("uncertainty_ms", 101), ("independent_probes", 1)]
)
def test_expired_or_unqualified_clock_never_preserves_quote_readiness(produced, field, value):
    model, _ = produced
    model["clock_readiness"][field] = value
    view = adapt(model)
    assert view["clock"]["state"] == view["symbols"][0]["quote"]["state"] == "SOURCE_VETO"


@pytest.mark.parametrize(
    "fault", ["schema", "identity", "unknown", "nested", "symbol", "quote_status", "count", "nan", "future"]
)
def test_changed_or_malformed_schema_fails_closed(produced, fault):
    model, _ = produced
    if fault == "schema":
        model["snapshot_schema_id"] = "NEXT_UNREVIEWED"
    if fault == "identity":
        model["producer_identity"]["source_sha256"] = {}
    if fault == "unknown":
        model["unreviewed"] = True
    if fault == "nested":
        model["per_symbol"]["BTCUSDT"]["quote"]["unknown"] = 1
    if fault == "symbol":
        model["per_symbol"]["FAKEUSDT"] = {}
    if fault == "quote_status":
        model["per_symbol"]["BTCUSDT"]["quote"]["status"] = "TRUST_ME"
    if fault == "count":
        model["per_symbol"]["BTCUSDT"]["bars"]["60000"]["missing_count"] = True
    if fault == "nan":
        model["per_symbol"]["BTCUSDT"]["quote"]["bid"] = "NaN"
    with pytest.raises(ValueError):
        adapt(model, now_ms=model["as_of_utc_ms"] - 1 if fault == "future" else None)


@pytest.mark.parametrize("claim", ["native_json", "native_fake_producer", "synthetic_qualified", "economic"])
def test_no_declared_flag_or_fabricated_authority_confers_native_origin(produced, claim):
    model, engine = produced
    if claim.startswith("native"):
        model["exposure"] = "PUBLIC_CANARY"
        engine.exposure = "PUBLIC_CANARY"
    if claim == "synthetic_qualified":
        model["source_qualified"] = True
    if claim == "economic":
        model["economically_validated"] = True
    with pytest.raises(ValueError):
        adapt(model, producer=engine if claim == "native_fake_producer" else None)


def episode(model):
    now = model["as_of_utc_ms"]
    return {
        "episode_id": "fixture-watch",
        "status": "ARMED",
        "known_at_utc_ms": now - 60000,
        "anchors": {
            "symbol": "BTCUSDT",
            "side": "LONG",
            "strategy": "trend_pullback",
            "zone_low": "99",
            "zone_high": "101",
            "stop": "98",
            "chase_cap": "101",
            "target": None,
            "expiry": now + 60000,
            "regime": "TREND_UP",
            "evidence_tier": "SYNTHETIC_VALIDATED",
        },
        "state": None,
        "ranking": None,
    }


def test_frozen_episode_and_xss_safe_existing_renderer(produced, tmp_path):
    model, _ = produced
    item = episode(model)
    item["episode_id"] = "<script>alert(1)</script>"
    model["advisory_episodes"] = [item]
    model["per_symbol"]["BTCUSDT"]["quote"]["reason"] = "<img src=x onerror=alert(1)>"
    before = copy.deepcopy(model)
    target = save_dashboard(tmp_path, {"model": model, "exposure": "SYNTHETIC"}, live=True)
    text = target.read_text()
    assert "&lt;script&gt;" in text and "<script>" not in text and "<img src=x" not in text
    assert "Rank (not probability)" in text and "ACCOUNT_VETO" in text and "ENTRY BLOCKED" in text
    assert "UNKNOWN" in text and model == before
    assert "fetch(" not in text and "<script src=" not in text and "<iframe" not in text


def test_only_matching_user_reported_unconfirmed_position_risk_is_displayed(produced):
    model, _ = produced
    t = model["as_of_utc_ms"]
    model["risk_recommendations"] = [
        {
            "position_id": "p",
            "action": "TIGHTEN_STOP",
            "decision_ts": t,
            "execution_status": "UNCONFIRMED",
            "suggested_stop": "99",
        }
    ]
    assert adapt(model)["position_risk"]["state"] == "UNKNOWN"
    model["user_reported_positions"] = {
        "p": {"source": "USER_REPORTED", "status": "OPEN", "version": 1, "updated_ts": t}
    }
    assert adapt(model)["position_risk"]["state"] == "USER_REPORTED_RISK_ONLY"
    assert adapt(model)["account_side"]["state"] == "ACCOUNT_VETO"
    model["user_reported_positions"]["p"]["status"] = "CLOSED"
    assert adapt(model)["position_risk"]["state"] == "UNKNOWN"


def test_response_causality_and_unknown_are_not_user_actions(produced):
    model, _ = produced
    t = model["as_of_utc_ms"]
    model["advisory_episodes"] = [episode(model)]
    row = {
        "episode": "fixture-watch",
        "response_minutes": 1,
        "modeled_ack_ts": t - 10,
        "subsequently_received_quote_ts": t - 5,
        "revalidated_ts": t,
        "conditional_market_survival": "SURVIVED_CONDITIONALLY",
        "quote_chronology": "POST_MODELED_ACK_NATIVE_AND_RECEIPT_VERIFIED",
        "actual_delivery_or_ack": False,
        "modeled_fill": False,
    }
    model["response_sensitivity"] = [row]
    v = adapt(model)
    assert v["responses"][0]["evidence_kind"] == "SYNTHETIC"
    row["subsequently_received_quote_ts"] = row["modeled_ack_ts"]
    with pytest.raises(ValueError, match="NOT_SUBSEQUENT"):
        adapt(model)
    row.pop("subsequently_received_quote_ts")
    row.pop("revalidated_ts")
    row["conditional_market_survival"] = "UNKNOWN"
    assert adapt(model)["responses"][0]["state"] == "UNKNOWN"
    row["actual_delivery_or_ack"] = True
    with pytest.raises(ValueError, match="ASSUMPTION"):
        adapt(model)


def test_atomic_snapshot_failure_preserves_previous_and_cleans_temp(produced, tmp_path, monkeypatch):
    model, _ = produced
    write_snapshot(tmp_path, model)
    before = (tmp_path / "latest.json").read_bytes()

    def fail(*a):
        raise OSError("FABRICATED_REPLACE_FAILURE")

    monkeypatch.setattr("btc_quant_agent.platform.canary.longhorizon_runtime.os.replace", fail)
    with pytest.raises(OSError):
        write_snapshot(tmp_path, model)
    assert (tmp_path / "latest.json").read_bytes() == before
    assert not list(tmp_path.glob(".*.part"))


def test_live_publication_atomic_under_two_local_writers_and_final_immutable(produced, tmp_path):
    model, _ = produced
    errors = []

    def publish():
        try:
            write_snapshot(tmp_path, copy.deepcopy(model))
        except Exception as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=publish) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert (
        not errors
        and json.loads((tmp_path / "latest.json").read_text())["producer_identity"] == producer_identity()
    )
    final = save_dashboard(tmp_path, {"model": model, "exposure": "SYNTHETIC"})
    before = final.read_bytes()
    with pytest.raises(ValueError, match="IMMUTABLE"):
        save_dashboard(tmp_path, {"model": model, "exposure": "SYNTHETIC"})
    assert final.read_bytes() == before


def test_symlink_output_and_exposure_mismatch_are_rejected(produced, tmp_path):
    model, _ = produced
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "linked"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="SYMLINK"):
        write_snapshot(link, model)
    with pytest.raises(ValueError, match="EXPOSURE"):
        save_dashboard(tmp_path, {"model": model, "exposure": "PUBLIC_CANARY"})


def test_unknown_historical_receipt_cannot_be_relabelled_native(tmp_path):
    from btc_quant_agent.platform.canary.longhorizon_view import historical_source

    (tmp_path / "receipt_seal.json").write_text("{}")
    with pytest.raises(ValueError, match="NOT_ACCEPTED_SEAL"):
        historical_source(tmp_path)


def test_local_review_manifest_is_independent_of_input_claims(produced, tmp_path, monkeypatch):
    from btc_quant_agent.platform.canary import longhorizon_view as module

    model, _ = produced
    manifest = json.loads(module.MANIFEST.read_text())
    name = next(iter(manifest["source_sha256"]))
    manifest["source_sha256"][name] = "0" * 64
    changed = tmp_path / "producer.json"
    changed.write_text(json.dumps(manifest))
    monkeypatch.setattr(module, "MANIFEST", changed)
    with pytest.raises(ValueError, match="REVISION_MISMATCH"):
        adapt(model)
