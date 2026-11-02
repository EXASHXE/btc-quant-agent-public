import pytest

from btc_quant_agent.platform.canary.control import CanaryStore
from btc_quant_agent.platform.canary.public_data import normalize
from btc_quant_agent.platform.canary.public_journal import PublicJournal
from btc_quant_agent.platform.canary.public_policy import START
from btc_quant_agent.platform.canary.storage import StorageBlocked
from .fixtures import Clock, wire, record, meta_payload, structural_replay


def journal(tmp_path, clock, **kw):
    return PublicJournal(
        tmp_path,
        CanaryStore(tmp_path / "s.sqlite", clock_ms=clock.wall),
        clock,
        exposure="SYNTHETIC",
        reserve=0,
        **kw,
    )


def test_raw_normalized_chunk_replay_detects_tampering(scope, tmp_path):
    clock = Clock()
    j = journal(tmp_path, clock)
    w = wire("binance_usdm_exchange_info", meta_payload(), START + 100)
    r = record(scope, w)
    a, _ = j.write("raw", [r])
    j.write("normalized", [normalize(r)], raw_sha=a)
    result = j.audit_replay(normalize)
    assert result["checked_pairs"] == 1 and result["complete_retained_raw_replay"]
    p = j.root / "raw" / (a + ".json.gz")
    p.write_bytes(b"bad")
    with pytest.raises(StorageBlocked, match="HASH"):
        j.audit_replay(normalize)


@pytest.mark.parametrize("kind", ["raw", "normalized"])
def test_compressed_byte_ceiling_before_write(kind, scope, tmp_path):
    j = journal(
        tmp_path,
        Clock(),
        raw_cap=1 if kind == "raw" else 8 * 1024**3,
        aux_cap=1 if kind == "normalized" else 4 * 1024**3,
    )
    with pytest.raises(StorageBlocked, match="SCOPE"):
        j.write(
            kind, [{"exposure": "SYNTHETIC", "received_wall_ms": START, "symbol": "BTCUSDT", "value": "data"}]
        )
    assert not list((tmp_path / kind).glob("*.json.gz"))


def test_retention_is_not_24h_and_expiry_is_explicit_operator_action(scope, tmp_path):
    clock = Clock()
    j = journal(tmp_path, clock)
    w = wire("binance_usdm_exchange_info", meta_payload(), START + 100)
    r = record(scope, w)
    a, _ = j.write("raw", [r])
    b, _ = j.write("normalized", [normalize(r)], raw_sha=a)
    assert not j.expire(w.receive_wall + 35 * 3600000)["expired"]
    assert j.expire(w.receive_wall + 36 * 3600000)["expired"] == [a]
    assert (tmp_path / "normalized" / (b + ".json.gz")).exists()
    assert j.audit_replay(normalize)["expired_chunks"] == 1


def test_raw_only_crash_state_never_claims_complete_replay(scope, tmp_path):
    j = journal(tmp_path, Clock())
    r = record(scope, wire("binance_usdm_exchange_info", meta_payload(), START + 100))
    j.write("raw", [r])
    result = j.audit_replay(normalize)
    assert result["status"] == "INCOMPLETE" and result["unpaired_raw_chunks"] == 1


def test_native_to_existing_factors_selector_and_local_outbox(scope, tmp_path):
    model, j, store = structural_replay(scope, tmp_path)
    result = model.report()
    assert result["L23_scan_count"] >= 2, result["reasons"]
    assert result["latest_scan"]["candidates"], result["latest_scan"]
    assert any(x["state"] == "TREND_UP" for x in result["latest_scan"]["regimes"].values())
    assert result["candidate_states"] and all(s == "WATCH" for s in result["candidate_states"].values())
    assert result["latest_scan"]["selected"] == []
    with store._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM market_watch_notifications").fetchone()[0] >= 1
        assert not db.execute(
            "SELECT 1 FROM market_watch_notifications WHERE attempted_at_ms IS NOT NULL"
        ).fetchone()
    assert not result["source_qualified"] and not result["shadow_advisory_qualified"]
    assert result["actual_user_actions_or_fills"] == 0 and result["external_sends"] == 0
    replay = j.audit_replay(normalize)
    assert replay["status"] == "PARITY_VERIFIED"
