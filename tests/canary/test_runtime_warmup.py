import json
import pytest
from btc_quant_agent.platform.canary.control import CircuitOpen
from btc_quant_agent.platform.canary.fixtures import bbo
from btc_quant_agent.platform.canary.runtime import OfflineSession, demo, normalize_record
from btc_quant_agent.platform.canary.storage import StorageBlocked
from btc_quant_agent.platform.canary.transport import (
    DisabledPublicTransport,
    NetworkDisabled,
    ScriptedTransport,
)
from btc_quant_agent.platform.canary.warmup import assess, contract
from btc_quant_agent.platform.selection.fixtures import BASE, SYMBOLS, history, structural_bars
from btc_quant_agent.platform.selection.selector import Policy as SelectorPolicy
from btc_quant_agent.platform.selection.sources import STRUCTURE


@pytest.mark.parametrize(
    "count,full,reason",
    [
        (65, False, "STRUCTURAL_66"),
        (66, False, "BETA_ALIGNED_RETURNS"),
        (200, False, "BETA_ALIGNED_RETURNS"),
        (201, True, "BETA_ALIGNED_RETURNS"),
    ],
)
def test_actual_causal_warmup_counts(count, full, reason):
    p = SelectorPolicy(symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT"))
    h = history(structural_bars(count=count, symbols=p.symbols), BASE + count * STRUCTURE, p)
    r = assess(h, full_beta_reference_required=full)
    assert any(reason in why for row in r["members"].values() for why in row["reasons"])
    assert not r["strategy_ready"] and not r["source_qualified"]


def test_full_warmup_is_not_a_trigger_or_native_qualification():
    p = SelectorPolicy(symbols=SYMBOLS)
    h = history(structural_bars(count=201), BASE + 201 * STRUCTURE, p)
    r = assess(h)
    assert r["feature_warmup_ready"]
    assert not r["strategy_ready"] and not r["source_qualified"]
    assert (
        contract()["dependencies_completed_5m_bars"]["beta_complete_288_return_reference_if_required"] == 289
    )


@pytest.mark.parametrize("fault", ["429", "timeout", "disconnect"])
def test_session_records_fault_before_stop_or_watch(fault, policy, catalog, binding, tmp_path):
    e = catalog["binance_usdm_bbo_ws"]
    f = bbo(e, "BTCUSDT", policy.synthetic_start_ms + 1000, fault=fault)
    s = OfflineSession(tmp_path, policy, catalog, ScriptedTransport((f,), policy))
    if fault == "429":
        with pytest.raises(CircuitOpen):
            s.step(e.id, "BTCUSDT", f.capture.request_wall_ms, binding[0])
        assert s.transport.closed
    else:
        r = s.step(e.id, "BTCUSDT", f.capture.request_wall_ms, binding[0])
        assert r["status"] == "WATCH" and not r["action_source_ready"]
    assert s.storage.audit()["retained_raw_chunks"] == 1
    assert s.storage.replay_crosscheck(lambda r: normalize_record(r, catalog, policy))["replayed_pairs"] == 1


def test_session_storage_full_closes_without_consuming_next_frame(policy, catalog, binding, tmp_path):
    e = catalog["binance_usdm_bbo_ws"]
    f = bbo(e, "BTCUSDT", policy.synthetic_start_ms + 1000)
    p = policy.model_copy(update={"storage": policy.storage.model_copy(update={"chunk_bytes": 50})})
    s = OfflineSession(tmp_path, p, catalog, ScriptedTransport((f, f), p))
    with pytest.raises(StorageBlocked):
        s.step(e.id, "BTCUSDT", f.capture.request_wall_ms, binding[0])
    assert s.transport.closed and s.transport.receive_calls == 1
    assert not s.store.get_value("last_receipt")


def test_no_alternative_transport_and_utc_stop(policy, catalog, binding, tmp_path):
    with pytest.raises(NetworkDisabled):
        OfflineSession(tmp_path, policy, catalog, DisabledPublicTransport())
    e = catalog["binance_usdm_bbo_ws"]
    s = OfflineSession(tmp_path, policy, catalog, ScriptedTransport((), policy))
    with pytest.raises(NetworkDisabled, match="END_REACHED"):
        s.step(e.id, "BTCUSDT", policy.end_ms, binding[0])
    assert s.transport.receive_calls == 0 and s.transport.closed
    assert s.store.get_value("finalization")["stopped_utc_ms"] == policy.end_ms


def test_native_to_l23_factors_scan_and_replay(policy, catalog, tmp_path):
    r = demo(policy, catalog, tmp_path / "demo")
    assert r["decoded_completed_5m_bars"] == 198
    assert len(r["selector"]["regimes"]) == 3
    assert all(v["metrics"]["usable"] for v in r["selector"]["regimes"].values())
    assert r["selector"]["candidates"] and r["selector"]["rejected"]
    assert not r["readiness"]["feature_warmup_ready"]
    assert all(
        v["status"] == "OFFLINE_STABLE" and not v["native_source_qualified"] for v in r["quotes"].values()
    )
    assert r["finalization"]["replay"]["replayed_pairs"] == 204
    assert r["finalization"]["replay"]["complete_raw_replay"]
    assert not r["source_qualified"] and not r["shadow_advisory_qualified"]
    assert r["local_external_sends"] == 0
    saved = json.loads((tmp_path / "demo/report.json").read_text())
    assert saved["policy_hash"] == policy.hash
    assert "<h1>Fabricated inputs only</h1>" in (tmp_path / "demo/report.html").read_text()
    with pytest.raises(ValueError, match="OUTPUT_EXISTS"):
        demo(policy, catalog, tmp_path / "demo")
