from __future__ import annotations

import json
import sqlite3

import pytest

from btc_quant_agent.platform.native.contract import authorize, source_hash
from btc_quant_agent.platform.native.journal import Journal
from btc_quant_agent.platform.native.runtime import capture, consume
from btc_quant_agent.platform.native.transport import Transport
from btc_quant_agent.platform.rc_fixture import TRIGGER
from helpers import LocalVenue, QAClock, authority


def message(**changes):
    result = {
        "stream": "btcusdt@kline_4h",
        "data": {
            "e": "kline",
            "E": TRIGGER + 100,
            "s": "BTCUSDT",
            "k": {
                "s": "BTCUSDT",
                "i": "4h",
                "t": TRIGGER - 14400000,
                "T": TRIGGER - 1,
                "x": True,
                "o": "100",
                "h": "110",
                "l": "90",
                "c": "105",
                "v": "1000",
            },
        },
    }
    result["data"]["k"].update(changes)
    return result


def run(tmp_path, messages, **options):
    clock = QAClock(TRIGGER + 110)
    venue = LocalVenue(tmp_path / "tls", clock, messages, **options)
    policy = venue.policy
    grant, envelope, audit, roots = authority(policy, tmp_path / "capture", clock.wall)
    authorize(
        envelope,
        audit,
        roots,
        policy,
        source_hash=source_hash(),
        executable_hash="a" * 64,
        now_ms=clock.wall,
        exposure="SYNTHETIC_NETWORK",
    )
    journal = Journal(tmp_path / "registry.sqlite")
    transport = Transport(policy, grant, journal, clock, qa_ca=venue.cert, qa_proxy=True)
    try:
        report = capture(grant, policy, journal, clock, transport)
        return report, journal, grant, transport, venue
    finally:
        venue.close()


def test_actual_connect_tls_websocket_journal(tmp_path):
    partial = message(x=False)
    report, journal, g, transport, venue = run(tmp_path, [partial, message(), message()])
    assert report["reason"] == "PEER_CLOSED_NO_RECONNECT"
    assert report["transport_closed"] and report["unsettled_frames"] == 0
    assert len(transport.tls) == 3
    assert all(t["hostname_verified"] for t in transport.tls)
    assert len(venue.targets) == 3
    assert journal.usage(g.session_id)["incoming"] == 5  # ping, partial, final, duplicate, close
    records = journal.records(g.session_id)
    assert len(records) == 1 and records[0]["record"]["durable_ms"] >= records[0]["record"]["received_ms"]
    assert records[0]["source_qualified"] is False
    with pytest.raises((ValueError, sqlite3.IntegrityError)):
        journal.reserve(g)


@pytest.mark.parametrize(
    "changes",
    [
        {"s": "ETHUSDT"},
        {"i": "1d"},
        {"T": TRIGGER},
        {"x": "true"},
        {"h": "NaN"},
        {"l": "106"},
        {"v": "-1"},
        {"t": TRIGGER - 14400001},
    ],
)
def test_wire_rejection_preserves_raw(tmp_path, changes):
    report, journal, g, _, _ = run(tmp_path, [message(**changes)])
    assert report["reason"] != "PEER_CLOSED_NO_RECONNECT"
    assert journal.records(g.session_id) == []
    assert journal.verify()["frames"] >= 1


def test_correction_and_duplicate_lineage(tmp_path):
    report, journal, g, _, _ = run(tmp_path, [message(), message(c="106")])
    assert report["reason"].startswith("CORRECTION_REQUIRES_REQUALIFICATION")
    assert len(journal.records(g.session_id)) == 1


@pytest.mark.parametrize(
    "options,reason",
    [
        ({"deny": True}, "PROXY_DENIED"),
        ({"wrong_cert": True}, "CERTIFICATE_VERIFY_FAILED"),
        ({"disconnect": True}, "RECEIVER_INTERRUPTED_OR_PEER_CLOSED"),
    ],
)
def test_transport_fail_closed_no_retry(tmp_path, options, reason):
    report, journal, g, transport, _ = run(tmp_path, [message()], **options)
    assert reason in report["reason"]
    assert transport.connection_attempts <= 3
    assert journal.usage(g.session_id)["status"] in {"CLOSED", "FAILED_CLOSURE"}


def test_clock_step_sticky():
    clock = QAClock(TRIGGER)
    clock.sample()
    clock.step = 51
    with pytest.raises(ValueError, match="50MS"):
        clock.sample()
    clock.step = 0
    with pytest.raises(ValueError, match="50MS"):
        clock.sample()


def test_parse_wrong_wrapper_or_stream():
    class ReadyClock:
        def event(self, *_):
            pass

        estimate = {}

    sample = {"wall_ms": TRIGGER + 200}

    class G:
        streams = ["btcusdt@kline_4h"]

    for value in ({"data": message()["data"]}, {**message(), "stream": "ethusdt@kline_4h"}):
        with pytest.raises(ValueError, match="COMBINED"):
            consume(json.dumps(value).encode(), sample, G(), ReadyClock(), {})


def test_raw_hash_tamper_detected(tmp_path):
    _, journal, _, _, _ = run(tmp_path, [message()])
    with journal.db() as db:
        db.execute("DROP TRIGGER immutable_frames_u")
        db.execute("UPDATE frames SET raw=x'00'")
    with pytest.raises(ValueError, match="TAMPER"):
        journal.verify()


def test_real_monotonic_clock_and_sni_local_tls(tmp_path):
    from btc_quant_agent.platform.native.clock import Clock

    clock = Clock()
    now = clock.sample()["wall_ms"]
    end = now // 14400000 * 14400000
    value = message(t=end - 14400000, T=end - 1)
    value["data"]["E"] = now
    venue = LocalVenue(tmp_path / "tls", clock, [value])
    try:
        policy = venue.policy
        g, envelope, audit, roots = authority(policy, tmp_path / "capture", now)
        authorize(
            envelope,
            audit,
            roots,
            policy,
            source_hash=source_hash(),
            executable_hash="a" * 64,
            now_ms=now,
            exposure="SYNTHETIC_NETWORK",
        )
        j = Journal(tmp_path / "registry.sqlite")
        transport = Transport(policy, g, j, clock, qa_ca=venue.cert, qa_proxy=True)
        report = capture(g, policy, j, clock, transport)
        assert report["transport_closed"]
        assert len(clock.probes) == 2 and clock.estimate["uncertainty_ms"] <= 100
        assert venue.sni == ["fapi.binance.com", "fapi.binance.com", "fstream.binance.com"]
    finally:
        venue.close()


def test_actual_120_second_refresh_same_ws_no_reconnect(tmp_path):
    clock = QAClock(TRIGGER + 110)
    venue = LocalVenue(tmp_path / "tls", clock, [message()])

    class AdvanceOnce(Transport):
        def open(self):
            super().open()
            clock.wall += 120001
            clock.mono += 120001

    try:
        policy = venue.policy
        g, envelope, audit, roots = authority(
            policy, tmp_path / "capture", clock.wall, end_ms=clock.wall + 400000
        )
        authorize(
            envelope,
            audit,
            roots,
            policy,
            source_hash=source_hash(),
            executable_hash="a" * 64,
            now_ms=clock.wall,
            exposure="SYNTHETIC_NETWORK",
        )
        j = Journal(tmp_path / "registry.sqlite")
        transport = AdvanceOnce(policy, g, j, clock, qa_ca=venue.cert, qa_proxy=True)
        report = capture(g, policy, j, clock, transport)
        assert len(clock.probes) == 4 and transport.connection_attempts == 5
        assert report["transport_closed"]
    finally:
        venue.close()
