"""Finite, loopback-only chronological network replay. Fabricated QA, not warmup."""

from __future__ import annotations

import hashlib
import ipaddress
import itertools
import json
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests/native")]

from helpers import LocalVenue, QAClock, authority  # noqa: E402
from btc_quant_agent.platform.native.contract import authorize, source_hash  # noqa: E402
from btc_quant_agent.platform.native.journal import Journal  # noqa: E402
from btc_quant_agent.platform.native.runtime import capture  # noqa: E402
from btc_quant_agent.platform.native.transport import Transport  # noqa: E402
from btc_quant_agent.platform.native.bridge import replay_synthetic_session, render_blocked_native  # noqa: E402
from btc_quant_agent.platform.rc_fixture import mixed_fixture, future_fixture, TRIGGER, DECISION  # noqa: E402
from btc_quant_agent.platform.rc_store import RCStore  # noqa: E402
from btc_quant_agent.platform.rc_dashboard import snapshot, write_snapshot  # noqa: E402
from btc_quant_agent.platform.rc_observe import observe, advance_episode  # noqa: E402
from btc_quant_agent.platform.program_c_export import build_export, write_export  # noqa: E402
from btc_quant_agent.platform.evaluation_adapter import evaluate_export  # noqa: E402


def main(output):
    output = Path(output).absolute()
    if output.exists():
        raise ValueError("FRESH_QA_OUTPUT_REQUIRED")
    output.mkdir(parents=True)
    original_connect = socket.socket.connect

    def loopback(sock, address):
        if sock.family != socket.AF_UNIX and not ipaddress.ip_address(address[0]).is_loopback:
            raise RuntimeError("QA_EXTERNAL_NETWORK_FORBIDDEN")
        return original_connect(sock, address)

    socket.socket.connect = loopback
    journal = Journal(output / "native.sqlite")
    store = RCStore(output / "product/state.sqlite")
    sessions = []

    # One short synthetic session for each chronological close, never time-rebase
    # a historic candle into a post-review event or weaken clock-refresh policy.
    def ingest(rows):
        for end, members in itertools.groupby(rows, key=lambda r: r.bar.end_ms):
            members = list(members)
            clock = QAClock(end + 110)
            messages = []
            for receipt in members:
                c = receipt.bar.candle
                interval = {"1H": "1h", "4H": "4h", "1D": "1d"}[c.interval]
                messages.append(
                    {
                        "stream": f"{c.symbol.lower()}@kline_{interval}",
                        "data": {
                            "e": "kline",
                            "E": end + 100,
                            "s": c.symbol,
                            "k": {
                                "s": c.symbol,
                                "i": interval,
                                "t": c.open_time_ms,
                                "T": c.close_time_ms,
                                "x": True,
                                "o": str(c.open),
                                "h": str(c.high),
                                "l": str(c.low),
                                "c": str(c.close),
                                "v": str(c.volume),
                            },
                        },
                    }
                )
            venue = LocalVenue(output / "tls", clock, messages)
            try:
                g, env, audit, roots = authority(
                    venue.policy,
                    output / f"session_{len(sessions):03d}",
                    clock.wall,
                    retention_seconds=7776000,
                )
                authorize(
                    env,
                    audit,
                    roots,
                    venue.policy,
                    source_hash=source_hash(),
                    executable_hash="a" * 64,
                    now_ms=clock.wall,
                    exposure="SYNTHETIC_NETWORK",
                )
                transport = Transport(venue.policy, g, journal, clock, qa_ca=venue.cert, qa_proxy=True)
                report = capture(g, venue.policy, journal, clock, transport)
                assert report["reason"] == "PEER_CLOSED_NO_RECONNECT", report
                assert report["transport_closed"] and report["unsettled_frames"] == 0
                assert replay_synthetic_session(journal, g.session_id, store) == len(members)
                sessions.append({"session": g.session_id, "candles": len(members), "report": report})
            finally:
                venue.close()

    ingest(mixed_fixture())
    decisions = [store.compile(s, TRIGGER, DECISION) for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT")]
    for d in decisions:
        store.commit(d)
    assert [d.market_state for d in decisions] == ["ARMED", "NO_SETUP", "NO_SETUP"]
    initial = snapshot(store, now_ms=DECISION)
    write_snapshot(output / "initial", initial)
    original_plans = [d.model_dump(mode="json") for d in store.decisions()]
    btc = decisions[0]
    ingest(future_fixture(btc))
    later = TRIGGER + 50 * 3600000 + 1000
    observed = observe(btc, store.receipts(), asof_ms=later)
    store.record_observation(observed.model_dump(mode="json"))
    advance_episode(store, btc.episode_id, now_ms=later)
    write_snapshot(output / "product", snapshot(store, now_ms=later))
    assert [d.model_dump(mode="json") for d in store.decisions()] == original_plans
    frozen = write_export(output / "product", build_export(store))
    evaluate_export(frozen, output / "evaluation")
    restart = RCStore(output / "product/state.sqlite", readonly=True)
    assert [d.model_dump(mode="json") for d in restart.decisions()] == original_plans
    render_blocked_native(journal, sessions[-1]["session"], output / "native_blocked", later)
    receipt = {
        "status": "PASS",
        "exposure": "SYNTHETIC_NETWORK_ONLY",
        "local_sessions": len(sessions),
        "completed_wire_candles": sum(s["candles"] for s in sessions),
        "transport": "Actual loopback HTTP CONNECT + original hostname/SNI TLS + WS",
        "clock": "FABRICATED_VIRTUAL_UTC_AND_MONOTONIC; same production arithmetic",
        "causal_timestamps": "PRESERVED_WITHOUT_RETIMING",
        "original_plan_preserved": True,
        "states": {d.symbol: d.market_state for d in decisions},
        "observed_market_side": observed.outcome,
        "scientific_decision": "INSUFFICIENT_SUPPORT",
        "native_market_requests": 0,
        "source_qualified": False,
        "shadow_qualified": False,
        "economic_validation": False,
        "journal": journal.verify(),
        "sessions": sessions,
        "files": [
            {"path": str(p.relative_to(ROOT)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in (
                output / "product/latest.html",
                output / "evaluation/scientific_report.md",
                output / "native.sqlite",
                output / "product/state.sqlite",
            )
        ],
    }
    (ROOT / "E3_END_TO_END_SYNTHETIC_NETWORK_ACCEPTANCE.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({k: v for k, v in receipt.items() if k not in {"sessions", "files"}}))


if __name__ == "__main__":
    main(sys.argv[1])
