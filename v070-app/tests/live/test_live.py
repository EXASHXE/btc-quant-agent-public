from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from btc_quant_agent.platform.live.cli import main
from btc_quant_agent.platform.live.models import (
    POLICY,
    QA,
    Blocked,
    sample,
    offset_step,
)
from btc_quant_agent.platform.live.product import Product
from btc_quant_agent.platform.live.rest import Transport, wire_request
from btc_quant_agent.platform.live.source import Collector, metadata, parse_rows, reference, project
from btc_quant_agent.platform.live.store import Store
from btc_quant_agent.platform.rc_fixture import TRIGGER
from btc_quant_agent.platform.swing import INTERVALS
from local_rest import RestVenue, exchange_info, candle_row


@pytest.fixture(scope="module")
def venue(tmp_path_factory):
    v = RestVenue(tmp_path_factory.mktemp("J_local_tls"))
    try:
        yield v
    finally:
        v.close()


@pytest.fixture(scope="module")
def captured(tmp_path_factory, venue):
    # Module fixture setup precedes function autouse fixtures. Keep its QA clock
    # in the same explicit synthetic domain as the local HTTP worker.
    with pytest.MonkeyPatch.context() as patch:

        def qa_sample():
            value = sample()
            value["wall_ms"] = value["mono_before_ms"] + 1000000000000
            return value

        for module in ("source", "store", "product"):
            patch.setattr("btc_quant_agent.platform.live." + module + ".sample", qa_sample)
        folder = tmp_path_factory.mktemp("J_store") / "data"
        s = Store(folder, create=True, exposure=QA)
        snapshot = Collector(s, _qa=venue.qa).run()
        yield s, snapshot


def parse_context():
    end = TRIGGER
    opening = end - 61 * INTERVALS["4H"]
    now = sample()
    ref = {"offset_upper_ms": end + 125000 - now["mono_after_ms"]}
    wire = {
        "receive_sample": now,
        "durable_sample": now,
        "body_sha256": "a" * 64,
        "session": "LOCAL_QA",
        "ordinal": 1,
        "route": "/fapi/v1/klines",
    }
    rows = [candle_row(i, INTERVALS["4H"]) for i in range(opening, end, INTERVALS["4H"])]
    kwargs = dict(
        symbol="BTCUSDT",
        interval="4H",
        start=opening,
        end=end,
        source_lower=end + 125000,
        grace_ms=120000,
        wire=wire,
        ref=ref,
        exposure=QA,
    )
    return rows, kwargs


def test_real_local_CONNECT_TLS_and_all_required_series(captured, venue):
    store, snapshot = captured
    assert snapshot["exposure"] == QA and snapshot["requests"] in (12, 23)
    assert len(snapshot["records"]) == 3 * (80 + 100 + 72)
    assert snapshot["request_weight"] <= 40 and snapshot["response_bytes"] < 16777216
    assert set(venue.sni) == {"fapi.binance.com"}
    assert all(v.startswith("CONNECT fapi.binance.com:443 ") for v in venue.targets)
    assert all(
        r["source_event_ms"] is None and r["source_publication_ms"] is None for r in snapshot["records"]
    )
    responses = store.events.values("HTTP_RESPONSE")
    assert all(r["tls"]["hostname_verified"] and r["tls"]["chain"] == "CERT_REQUIRED" for r in responses)
    store.verify_raw()


def test_actual_S1_Html_Shadow_restart_and_C_schema_gate(captured, tmp_path):
    store, _ = captured
    p = Product(store)
    values = [p.review(s) for s in POLICY["symbols"]]
    assert [d.market_state for d in values] == ["ARMED", "NO_SETUP", "NO_SETUP"]
    original = [d.model_dump(mode="json") for d in values]
    assert all(d.exposure == QA and not d.source_qualified for d in values)
    page = Path(p.dashboard()["dashboard"]).read_text()
    assert QA in page and "Planned gross R" in page and "Hypothetical cost assumptions bps" in page
    result = p.observe(values[0].episode_id)
    assert result["outcome"] == "INSUFFICIENT_FUTURE_HORIZON" and not result["actual_fill"]
    restored = Product(Store(store.directory))
    assert [d.model_dump(mode="json") for d in restored.decisions()] == original
    assert p.review("BTCUSDT") == values[0]
    r = p.evaluate(tmp_path / "J_C_gate")
    assert r["actual_C_validator_error"] == "SOURCE_CLASS_INVALID" and not r["source_relabeling"]
    assert r["scientific_decision"] == "INSUFFICIENT_SUPPORT" and not r["C_economic_ledger_executed"]


def test_flat_market_all_NO_SETUP(tmp_path):
    v = RestVenue(tmp_path / "tls", flat=True)
    try:
        s = Store(tmp_path / "flat", create=True, exposure=QA)
        Collector(s, _qa=v.qa).run()
        p = Product(s)
        assert [p.review(name).market_state for name in POLICY["symbols"]] == ["NO_SETUP"] * 3
        assert Path(p.dashboard()["dashboard"]).is_file()
    finally:
        v.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("contractType", "CURRENT_QUARTER"),
        ("marginAsset", "BTC"),
        ("quoteAsset", "USD"),
        ("status", "BREAK"),
        ("baseAsset", "ETH"),
        ("pair", "BTCUSD"),
    ],
)
def test_exact_instrument_identity(field, value):
    info = exchange_info()
    info["symbols"][0][field] = value
    with pytest.raises(Blocked, match="INSTRUMENT"):
        metadata(info)


@pytest.mark.parametrize(
    "fault,reason",
    [
        ("duplicate", "DUPLICATE"),
        ("gap", "GAP"),
        ("short", "ENOUGH"),
        ("stale", "GAP"),
        ("unaligned", "ALIGNMENT"),
        ("invalid_ohlc", "OHLCV"),
        ("nan", "NONFINITE"),
        ("boolean", "NUMERIC"),
        ("future_range", "OPERATIONAL_SCOPE"),
    ],
)
def test_completed_parser_rejects_faults(fault, reason):
    rows, kw = parse_context()
    if fault == "duplicate":
        rows.append(rows[-1])
    elif fault == "gap":
        rows.pop(20)
    elif fault == "short":
        rows = rows[-20:]
    elif fault == "stale":
        rows = rows[:-1]
    elif fault == "unaligned":
        rows[-1][6] += 1
    elif fault == "invalid_ohlc":
        rows[-1][2] = "1"
    elif fault == "nan":
        rows[-1][4] = "NaN"
    elif fault == "boolean":
        rows[-1][5] = True
    elif fault == "future_range":
        kw["start"] += INTERVALS["4H"]
    with pytest.raises(Blocked, match=reason):
        parse_rows(rows, **kw)


def test_current_partial_candle_never_admitted():
    rows, kw = parse_context()
    rows.append(candle_row(TRIGGER, INTERVALS["4H"]))
    result, skipped = parse_rows(rows, **kw)
    assert skipped == 1 and len(result) == 61
    assert all(r["candle"]["close_time_ms"] < TRIGGER for r in result)


def test_server_time_brackets_and_reference_staleness():
    s = sample()
    a = ({"serverTime": 1000000}, {"request_sample": s, "receive_sample": s, "body_sha256": "a" * 64})
    later = {**s, "mono_before_ms": s["mono_before_ms"] + 100, "mono_after_ms": s["mono_after_ms"] + 100}
    b = ({"serverTime": 1000100}, {"request_sample": later, "receive_sample": later, "body_sha256": "b" * 64})
    ref = reference(a, b)
    assert project(ref, later)[0] <= 1000100 <= project(ref, later)[1]
    with pytest.raises(Blocked, match="STALE"):
        project(ref, {**later, "mono_before_ms": later["mono_before_ms"] + 400000})
    with pytest.raises(Blocked, match="REGRESSION"):
        reference(a, ({"serverTime": 1}, b[1]))


def test_1760ms_clock_hold_reacquires_complete_prefix(captured, venue, monkeypatch):
    store, _ = captured
    monkeypatch.setattr("btc_quant_agent.platform.live.source.offset_step", lambda *_: False)
    store.events.append("CLOCK_STATE", {"session": "INJECTED_1760MS_PRIOR_STOP", "held": True})
    before = len(store.events.values("HTTP_RESPONSE"))
    s = Collector(store, _qa=venue.qa).run()
    assert s["clock"] == "CLOCK_DEGRADED_RECONCILED" and s["requests"] == 23
    assert len(store.events.values("HTTP_RESPONSE")) - before == 23
    assert store.events.values("CLOCK_RECONCILIATION")
    assert store.events.values("CLOCK_STATE")[-1]["held"] is False
    a = sample()
    assert offset_step(a, {**a, "wall_ms": a["wall_ms"] + 1760})


@pytest.mark.parametrize("status", [301, 403, 418, 429, 451])
def test_no_redirect_retry_or_denial_bypass(tmp_path, venue, status):
    old = venue.status
    venue.status = status
    try:
        s = Store(tmp_path / str(status), create=True, exposure=QA)
        with pytest.raises(Blocked, match="NO_RETRY"):
            Collector(s, _qa=venue.qa).run()
        assert len(s.events.values("REQUEST_ADMITTED")) == 1 and not s.snapshots()
        assert s.events.values("SESSION_TERMINAL")[-1]["status"] == "FAILED"
    finally:
        venue.status = old


@pytest.mark.parametrize("option", ["deny", "wrong_cert"])
def test_actual_proxy_denial_and_certificate_rejection(tmp_path, option):
    v = RestVenue(tmp_path / "tls", **{option: True})
    try:
        s = Store(tmp_path / "rejected", create=True, exposure=QA)
        with pytest.raises(Blocked, match="TLS_PROXY_OR_NETWORK"):
            Collector(s, _qa=v.qa).run()
        assert len(s.events.values("REQUEST_ADMITTED")) == 1 and not s.snapshots()
    finally:
        v.close()


def test_request_worker_timeout_is_killed_and_not_retried(monkeypatch):
    calls = []

    def timeout(*args, **kwargs):
        calls.append(args)
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(Blocked, match="DEADLINE_NO_RETRY"):
        Transport(None, {"host": "127.0.0.1", "port": 1, "cafile": "QA"}).request("/fapi/v1/time", {}, 0.1)
    assert len(calls) == 1


def test_missing_access_refuses_before_store_creation_or_socket(tmp_path, capsys):
    assert main(["scan", "--output", str(tmp_path / "absent")]) == 2
    assert not (tmp_path / "absent").exists()
    assert "ACCESS_REGION" in capsys.readouterr().out


@pytest.mark.parametrize(
    "route", ["/fapi/v1/order", "/api/v3/klines", "https://evil.invalid/", "/fapi/v1/markPriceKlines"]
)
def test_only_three_public_routes(route):
    with pytest.raises(Blocked, match="ALLOWLISTED"):
        wire_request({"route": route, "params": {}})


def test_raw_hash_tampering_rejected_on_restart(tmp_path, captured):
    import shutil

    source, _ = captured
    shutil.copytree(source.directory, tmp_path / "tampered")
    p = next((tmp_path / "tampered/raw").rglob("*.bin"))
    p.write_bytes(p.read_bytes() + b" ")
    with pytest.raises(Blocked, match="LINEAGE_TAMPER"):
        Store(tmp_path / "tampered")


def test_crash_after_prepared_snapshot_never_admits(tmp_path):
    s = Store(tmp_path / "crash", create=True, exposure=QA)
    s.events.append("SESSION_START", {"session": "CRASH_TEST"})
    s.events.append("SNAPSHOT", {"session": "CRASH_TEST", "records": []})
    assert s.snapshots() == []
    assert s.recover() == ["CRASH_TEST"]
    assert s.snapshots() == []


def test_disk_full_before_request_is_charged_or_connected(tmp_path, venue, monkeypatch):
    s = Store(tmp_path / "disk", create=True, exposure=QA)

    def fail(*args):
        raise Blocked("LIVE_DISK_FULL")

    monkeypatch.setattr(s, "capacity", fail)
    with pytest.raises(Blocked, match="DISK_FULL"):
        Collector(s, _qa=venue.qa).run()
    assert not s.events.values("REQUEST_ADMITTED")


def test_strict_and_H_code_bytes_preserved():
    root = Path(__file__).resolve().parents[2]
    rows = json.loads((root / "audit/H_accepted/audit/code_manifest.json").read_text())["files"]
    for r in rows:
        if r["path"] == "src/btc_quant_agent/platform/rc_strategy.py":
            from approved_compiler_delta import assert_original_s1_ast

            assert_original_s1_ast(root)
        elif r["path"].startswith(("src/", "contracts/")) and not r["path"].endswith("unified_cli.py"):
            assert hashlib.sha256((root / r["path"]).read_bytes()).hexdigest() == r["sha256"]


@pytest.mark.parametrize("budget", ["requests", "bytes", "duration"])
def test_finite_budgets_fail_before_a_new_socket(tmp_path, venue, budget):
    s = Store(tmp_path / budget, create=True, exposure=QA)
    c = Collector(s, _qa=venue.qa)
    if budget == "requests":
        c.requests = POLICY["request_count_max"]
    elif budget == "bytes":
        c.size = POLICY["session_bytes_max"]
    else:
        c.deadline = 1
    with pytest.raises(Blocked, match="FINITE_REQUEST_BUDGET"):
        c.get("/fapi/v1/time", {})
    assert not s.events.values("REQUEST_ADMITTED")


def test_revision_is_sticky_and_original_decisions_are_not_rewritten(captured, venue, tmp_path):
    import shutil

    original, _ = captured
    shutil.copytree(original.directory, tmp_path / "revision")
    s = Store(tmp_path / "revision")
    prior = s.events.values("DECISION")
    venue.fault = "revision"
    try:
        with pytest.raises(Blocked, match="REVISION"):
            Collector(s, _qa=venue.qa).run()
    finally:
        venue.fault = None
    assert s.events.values("SOURCE_STOP") and s.events.values("DECISION") == prior
    count = len(s.events.values("REQUEST_ADMITTED"))
    with pytest.raises(Blocked, match="REVISION_REQUIRES_NEW_REVIEWED_VERSION"):
        Collector(s, _qa=venue.qa).run()
    assert len(s.events.values("REQUEST_ADMITTED")) == count


def test_interrupted_raw_fsync_has_no_eligible_snapshot(tmp_path, venue, monkeypatch):
    import os

    s = Store(tmp_path / "torn", create=True, exposure=QA)

    def broken(*args):
        raise OSError("INJECTED_INTERRUPTED_FSYNC")

    monkeypatch.setattr(os, "fsync", broken)
    with pytest.raises(OSError, match="INTERRUPTED_FSYNC"):
        Collector(s, _qa=venue.qa).run()
    assert not s.snapshots() and not s.events.values("HTTP_RESPONSE")
    assert s.events.values("SESSION_TERMINAL")[-1]["status"] == "FAILED"


def test_sealed_date_exclusion_prevents_even_a_kline_request(tmp_path, venue):
    s = Store(tmp_path / "excluded", create=True, exposure=QA)
    c = Collector(s, _qa=venue.qa)
    c.exclusions = {"excluded_UTC_ms_ranges": [[TRIGGER - INTERVALS["1D"], TRIGGER]]}
    with pytest.raises(Blocked, match="HOLDOUT_DATE_OVERLAP"):
        c.run()
    assert [r["route"] for r in s.events.values("REQUEST_ADMITTED")] == [
        "/fapi/v1/exchangeInfo",
        "/fapi/v1/time",
    ]
    assert not s.snapshots()


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "REVOKED"),
        ("region", "UNKNOWN"),
        ("policy_sha256", "f" * 64),
        ("retention_days", 31),
        ("api_key", "FORBIDDEN"),
    ],
)
def test_reviewed_operational_access_requires_no_signer_but_rejects_invalid_scope(tmp_path, field, value):
    from btc_quant_agent.platform.live.models import Access, POLICY_HASH

    config = {
        "schema_version": "J_OPERATIONAL_ACCESS_V1",
        "status": "VERIFIED",
        "policy_sha256": POLICY_HASH,
        "region": "FABRICATED_QA_REGION_NOT_VENUE_AUTHORITY",
        "reviewer_reference": "OFFLINE_STRUCTURE_TEST_ONLY",
        "retention_days": 1,
        "operational_rolling_lookback_only": True,
        "proxy": None,
    }
    for name in ("eligibility", "advisory_use_and_cache", "holdout_exclusions"):
        f = tmp_path / ("excluded_dates.json" if name == "holdout_exclusions" else name + ".json")
        f.write_text(
            json.dumps(
                {
                    "metadata_complete": True,
                    "excluded_UTC_ms_ranges": [],
                    "evidence_class": "FABRICATED_QA_NOT_AUTHORITY",
                }
            )
        )
        config[name] = {"path": f.name, "sha256": hashlib.sha256(f.read_bytes()).hexdigest()}
    p = tmp_path / "access.json"
    p.write_text(json.dumps(config))
    access, _ = Access.load(p)
    assert access.status == "VERIFIED"  # Structural verification only; never used for network.
    config[field] = value
    p.write_text(json.dumps(config))
    with pytest.raises(Blocked):
        Access.load(p)


def test_real_local_stalled_socket_deadline_terminates_worker(tmp_path):
    import time

    v = RestVenue(tmp_path / "tls")
    v.fault = "hang"
    try:
        before = time.monotonic()
        with pytest.raises(Blocked, match="DEADLINE_NO_RETRY|NETWORK_FAILURE_NO_RETRY"):
            Transport(None, v.qa).request("/fapi/v1/time", {}, 1.5)
        assert time.monotonic() - before < 3 and len(v.calls) == 1
    finally:
        v.close()


def test_oversize_response_prefix_is_durable_but_never_admitted(tmp_path):
    v = RestVenue(tmp_path / "tls")
    v.fault = "oversize"
    try:
        s = Store(tmp_path / "oversize", create=True, exposure=QA)
        with pytest.raises(Blocked, match="SIZE_LIMIT_TRUNCATED"):
            Collector(s, _qa=v.qa).run()
        r = s.events.values("HTTP_RESPONSE")[-1]
        assert not r["response_complete"] and not s.snapshots()
        assert (s.directory / r["raw_path"]).stat().st_size == 2097152
    finally:
        v.close()


def test_normalized_snapshot_must_rederive_from_raw_HTTP_bytes(captured, tmp_path):
    import shutil
    from btc_quant_agent.platform.native.contract import digest

    original, _ = captured
    shutil.copytree(original.directory, tmp_path / "normalized_tamper")
    s = Store(tmp_path / "normalized_tamper")
    modified = s.snapshots()[0]
    modified["session"] = "FABRICATED_LINEAGE_TAMPER_TEST"
    modified["records"][0]["candle"]["close"] += 1
    s.events.append("SESSION_START", {"session": modified["session"]})
    s.events.append("SNAPSHOT", modified)
    s.events.append(
        "SESSION_TERMINAL",
        {"session": modified["session"], "status": "COMPLETE", "snapshot_sha256": digest(modified)},
    )
    with pytest.raises(Blocked, match="NORMALIZED_RAW_LINEAGE_TAMPER"):
        s.snapshots()
