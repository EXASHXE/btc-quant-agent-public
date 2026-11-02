import json

import pytest

from btc_quant_agent.platform.canary import clock_domain as d
from btc_quant_agent.platform.canary.control import BudgetGuard, CanaryStore
from btc_quant_agent.platform.canary.longhorizon_runtime import save_dashboard
from btc_quant_agent.platform.canary.public_data import normalize
from btc_quant_agent.platform.canary.storage import StorageBlocked
from btc_quant_agent.platform.selection.sources import MINUTE, FrozenUniverse, SourceHistory
from .fixtures import START, engine_at, frame, probes, quote


def test_quote_freshness_preserves_native_and_local_clocks(tmp_path):
    c, _, _, journal, e = engine_at(tmp_path)
    c.advance(100)
    for i in range(1, 5):
        result = quote(e, c, sequence=i)
        c.advance(5)
    e.flush()
    assert result["quote"] and "BTCUSDT" in e.quote
    report = e.report()
    assert report["per_symbol"]["BTCUSDT"]["quote"]["status"] == "QUALIFIED_PRICE_ONLY"
    assert report["per_symbol"]["ETHUSDT"]["quote"]["status"] == "MISSING"
    raw = [r for r in journal.rows() if r[3] == "raw"][-1]
    record = journal.read(raw)["records"][-1]
    native = json.loads(record["wire"]["payload_text"])["data"]
    assert native["E"] > record["received_wall_ms"] and native["T"] == native["E"] - 2
    assert record["source_contract_version"] == "L4_LONGHORIZON_V1"
    c.advance(5001)
    assert e.report()["per_symbol"]["BTCUSDT"]["quote"]["status"] == "STALE"
    assert journal.audit_replay(normalize)["complete_retained_raw_replay"]


def test_silent_candle_gaps_queue_only_bounded_prospective_repair(tmp_path):
    c, s, _, _, e = engine_at(tmp_path)
    c.advance(10 * MINUTE)
    probes(e, c)
    e.queue_gaps()
    assert e.repairs and len(e.repairs) <= 32
    for symbol, size, lo, hi in e.repairs:
        assert lo >= s.start_ms and hi < c.wall() + 846
        assert hi - lo + 1 <= 99 * size
    missing = e.report()["per_symbol"]["BTCUSDT"]["bars"][str(MINUTE)]
    assert missing["missing_count"] >= 9
    assert e.repair_ready() and not e.repair_ready()


def repair(e, c, *, bad_row=False):
    params = {"symbol": "BTCUSDT", "interval": "1m", "startTime": START,
              "endTime": START + 2 * MINUTE - 1, "limit": 2}
    request = c.sample()
    c.advance(20)
    rows = [[START + i * MINUTE, "100", "101", "99", "100.5", "100",
             START + (i + 1) * MINUTE - 1, "10050", 1, 0, 0, 0] for i in range(2)]
    if bad_row:
        rows[0][0] -= MINUTE
    return e.ingest(frame(c, "binance_usdm_klines_rest", rows, "BTCUSDT", request=request, params=params))


def test_late_repair_enters_future_history_never_replays_past_decisions(tmp_path):
    c, _, _, journal, e = engine_at(tmp_path)
    c.advance(5 * MINUTE)
    probes(e, c)
    result = repair(e, c)
    assert len(result["bars"]) == 2, result["reasons"]
    e.flush()
    assert len(e.bars[("BTCUSDT", MINUTE)]) == 2
    assert e.scans == 0 and not e.management
    with d.decision_clock(c.sample(), e.scope.hash):
        b = e.bars[("BTCUSDT", MINUTE)][START]
        assert b.values(b.end + 1000)[0]["close"] == 100.5
        h = SourceHistory((b,), FrozenUniverse(("BTCUSDT",), "BTCUSDT", b.end,
                                             interval_ms=MINUTE, decision_ts=c.wall()))
        assert len(h.frames["BTCUSDT"]) == 1
    p = b.fields[0].provenance
    original = p.clock_evidence["decision"]
    prior = {**original, "wall_ms": original["wall_ms"] - 100,
             "mono_before_ms": original["mono_before_ms"] - 100,
             "mono_after_ms": original["mono_after_ms"] - 100}
    with d.decision_clock(prior, e.scope.hash):
        assert not b.values(b.end + 1000)[0]
    assert journal.audit_replay(normalize)["complete_retained_raw_replay"]


def test_repair_cannot_accept_extra_native_history(tmp_path):
    c, _, _, _, e = engine_at(tmp_path)
    c.advance(5 * MINUTE)
    probes(e, c)
    result = repair(e, c, bad_row=True)
    assert not result["bars"] and "BOUNDED_REPAIR_ROWS_OUTSIDE_REQUEST" in result["reasons"]


def test_source_fields_keep_unknown_units_clocks_and_missing_cadence(tmp_path):
    c, _, _, _, e = engine_at(tmp_path)
    c.advance(100)
    for endpoint, value in (
        ("binance_usdm_oi", {"symbol": "BTCUSDT", "openInterest": "123", "time": c.wall() + 796}),
        ("binance_usdm_premium", {"symbol": "BTCUSDT", "markPrice": "100", "indexPrice": "99.99",
         "lastFundingRate": "0.001", "nextFundingTime": c.wall() + 3600000, "time": c.wall() + 796}),
        ("binance_usdm_turnover", {"symbol": "BTCUSDT", "quoteVolume": "5000", "volume": "50",
         "openTime": c.wall() - 86400000, "closeTime": c.wall() + 796})):
        e.ingest(frame(c, endpoint, value, "BTCUSDT", request=c.sample()))
    e.ingest(frame(c, "binance_usdm_funding_info", [], request=c.sample()))
    e.flush()
    fields = e.report()["per_symbol"]["BTCUSDT"]["fields"]
    assert fields["open_interest"]["status"] == fields["mark_price"]["status"] == "UNKNOWN"
    assert fields["funding_cadence"]["status"] == "MISSING"
    assert fields["turnover"]["status"] == "CONTEXT_ONLY"
    assert not any(v["action_qualified"] for v in fields.values())


@pytest.mark.parametrize("elapsed,expected_raw,expected_normal", [
    (36 * 3600000 - 1, False, False), (36 * 3600000, True, False),
    (48 * 3600000, True, False), (168 * 3600000 - 1, True, False), (168 * 3600000, True, True)])
def test_raw_36h_normalized_168h_minimum_and_explicit_replay_loss(tmp_path, elapsed, expected_raw, expected_normal):
    c, _, _, journal, e = engine_at(tmp_path)
    e.flush()
    rows = journal.rows()
    # Test exact chunk expiry using the last receipt, not process-start time.
    when = max(r[6] for r in rows) + elapsed
    journal.expire(when)
    expired = {r[1] for r in rows if not journal._path(r[3], r[1]).exists()}
    last_raw = [r for r in rows if r[3] == "raw"][-1]
    last_normal = [r for r in rows if r[3] == "normalized"][-1]
    assert (last_raw[1] in expired) == expected_raw
    assert (last_normal[1] in expired) == expected_normal
    result = journal.audit_replay(normalize)
    if expected_raw:
        assert not result["complete_retained_raw_replay"]
        assert result["full_session_raw_replay_status"] == "INCOMPLETE_EARLY_RAW_EXPIRED"


def test_clock_fault_is_durable_and_restart_does_not_restore_readiness(tmp_path):
    c, _, store, _, e = engine_at(tmp_path)
    c.advance(10, step=900)
    e.tick(c.wall())
    assert not e.advisory_enabled and e.clock_fault
    reloaded = CanaryStore(tmp_path / "state.sqlite")
    assert reloaded.get_value("clock_epoch_invalidation")["reason"] == "LOCAL_WALL_CLOCK_JUMP"


def test_stale_clock_refresh_and_storage_headroom_stop_durably(tmp_path):
    c, _, store, _, e = engine_at(tmp_path / "clock")
    c.advance(300001)
    with pytest.raises(ValueError, match="CLOCK_REFRESH_UNQUALIFIED"):
        e.maintenance()
    assert store.get_value("longhorizon_clock_fault")
    c, _, store, journal, e = engine_at(tmp_path / "disk")
    journal.raw_cap = journal.used()["raw"] + 100
    with pytest.raises(StorageBlocked, match="HEADROOM"):
        e.maintenance()
    assert store.get_value("longhorizon_storage_fault")


def test_integrity_corruption_is_detected(tmp_path):
    _, _, _, journal, e = engine_at(tmp_path)
    e.flush()
    row = journal.rows()[0]
    path = journal._path(row[3], row[1])
    path.write_bytes(path.read_bytes() + b"corrupt")
    with pytest.raises(StorageBlocked):
        journal.audit_replay(normalize)


def test_rest_retry_and_repair_share_60_weight_ceiling(tmp_path):
    _, s, store, _, _ = engine_at(tmp_path)
    guard = BudgetGuard(store, s.budget_policy())
    endpoint = s.endpoint("binance_usdm_server_time")
    # Other endpoints consume the primary budget. Two time probes remain hard-capped.
    guard.request(endpoint, {}, 1000)
    guard.request(endpoint, {}, 1001, retry=True)
    with pytest.raises(ValueError, match="BUDGET"):
        guard.request(endpoint, {}, 1002, retry=True)
    assert store.get_value("circuit")


def test_dashboard_reports_missing_sources_and_entry_vetoes(tmp_path):
    _, _, _, _, e = engine_at(tmp_path)
    value = e.report()
    path = save_dashboard(tmp_path, {"model": value, "exposure": "SYNTHETIC"})
    text = path.read_text()
    assert "SYNTHETIC" in text and "ENTRY BLOCKED" in text and "MISSING" in text
    assert "ten-symbol" in text and not value["source_qualified"]
    assert value["coverage"]["opportunities_per_observed_hour"] is None
    assert value["coverage"]["prevalence_support"] == "UNKNOWN_NO_L23_SCAN_SUPPORT"


def test_maintenance_expiry_preserves_receiver_uncertainty_margin(tmp_path):
    c, _, _, journal, e = engine_at(tmp_path)
    e.flush()
    first = journal.rows()[0]
    c.advance(first[7] - c.wall())
    probes(e, c)
    e.maintenance()
    assert journal._path(first[3], first[1]).exists()
    c.advance(60000)
    e.maintenance()
    assert not journal._path(first[3], first[1]).exists()
    assert e.retention["raw_to_normalized_full_session_replay"] == "INCOMPLETE_EARLY_RAW_EXPIRED"
