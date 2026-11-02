"""OFFLINE: fabricated native-shaped clock proofs through existing L23 engines."""

import json
import os
from pathlib import Path
import subprocess
import sys
import pytest


from btc_quant_agent.platform.canary import clock_domain as d
from btc_quant_agent.platform.canary.control import CanaryStore, BudgetGuard
from btc_quant_agent.platform.canary.public_data import normalize
from btc_quant_agent.platform.canary.public_journal import PublicJournal
from btc_quant_agent.platform.canary.public_policy import START, SYMBOLS, preflight, PublicStop
from btc_quant_agent.platform.canary.public_io import PublicTransport
from btc_quant_agent.platform.canary.public_runtime import PublicEngine
from btc_quant_agent.platform.selection.fixtures import structural_bars
from btc_quant_agent.platform.selection.sources import STRUCTURE
from .test_clock_domain import EpochClock, frame
from .fixtures import meta_payload


def probe_engine(engine, clock, offset=846):
    for _ in range(2):
        clock.advance(5)
        request = clock.sample()
        native = clock.wall() + offset + 10
        clock.advance(20)
        engine.ingest(frame(clock, "binance_usdm_server_time", {"serverTime": native}, request=request))


def quote_engine(engine, clock, *, sequence=1, offset=846, symbol="BTCUSDT"):
    event = clock.wall() + offset - 50
    w = frame(
        clock,
        "binance_usdm_bbo_ws",
        {
            "stream": symbol.lower() + "@bookTicker",
            "data": {
                "e": "bookTicker",
                "st": 1,
                "s": symbol,
                "u": sequence,
                "E": event,
                "T": event - 2,
                "b": "100.00",
                "a": "100.02",
                "B": "100",
                "A": "100",
            },
        },
        symbol,
        symbol.lower() + "@bookTicker",
    )
    result = engine.ingest(w)
    engine.flush()
    return w, result


def make_engine(scope, root, clock=None):
    clock = clock or EpochClock(START + 1000)
    store = CanaryStore(root / "state.sqlite", clock_ms=clock.wall)
    journal = PublicJournal(root, store, clock, exposure="PUBLIC_CANARY", reserve=0)
    engine = PublicEngine(scope, clock, store, journal, "PUBLIC_CANARY")
    return clock, store, journal, engine


def test_multiple_probes_and_duplicate_ordering_then_epoch_fault(scope, tmp_path):
    clock, store, journal, engine = make_engine(scope, tmp_path)
    engine.ingest(frame(clock, "binance_usdm_exchange_info", meta_payload()))
    probe_engine(engine, clock)
    assert engine.estimate["version"] == d.VERSION
    assert len(engine.native_probes) == 2
    clock.advance(100)
    for seq in (10, 11, 12):
        clock.advance(5)
        w, result = quote_engine(engine, clock, sequence=seq)
    assert result["quote"] and engine.quote["BTCUSDT"]
    count = engine.counts["distinct_qualified_quotes"]
    engine.ingest(w)
    engine.flush()
    assert engine.counts["distinct_qualified_quotes"] == count
    clock.advance(5)
    _, result = quote_engine(engine, clock, sequence=9)
    assert result["quote"]  # Clock proof is separate from source-sequence admission.
    assert engine.counts["distinct_qualified_quotes"] == count
    assert any("DUPLICATE" in x or "OUT_OF_ORDER" in x for x in engine.reasons)
    clock.advance(5, wall_step=900)
    engine.tick(clock.wall())
    assert engine.clock_fault == "LOCAL_WALL_CLOCK_JUMP"
    assert not engine.quote and not engine.advisory_enabled
    assert store.get_value("clock_epoch_invalidation")["sample"]["wall_ms"] == clock.wall()
    engine.flush()
    assert journal.audit_replay(normalize)["complete_retained_raw_replay"]


def test_offline_scope_cannot_enable_new_native_session(scope, tmp_path):
    assert scope.raw["activation_status"] == "OFFLINE_ONLY_PENDING_SECOND_SESSION_AUTH"
    check = preflight(scope, EpochClock(START + 1000))
    assert "SECOND_NATIVE_SESSION_REQUIRES_DISTINCT_OWNER_AUTHORIZATION" in check["reasons"]
    assert check["native_market_calls"] == 0

    class NeverCalledBackend:
        exposure = "PUBLIC_CANARY"
        calls = 0

        def get(self, *args):
            self.calls += 1
            raise AssertionError("OFFLINE_NATIVE_TRANSPORT_REACHED")

    backend = NeverCalledBackend()
    clock = EpochClock(START + 1000)
    transport = PublicTransport(
        scope,
        clock,
        BudgetGuard(CanaryStore(tmp_path / "s.sqlite"), scope.budget_policy()),
        enabled=True,
        backend=backend,
    )
    with pytest.raises(PublicStop, match="SECOND_NATIVE_SESSION_REQUIRES_DISTINCT_OWNER_AUTHORIZATION"):
        transport.request("binance_usdm_server_time", {})
    assert backend.calls == 0


@pytest.mark.parametrize("minutes", [1, 3, 5])
def test_response_component_without_new_quote_stays_unknown(scope, tmp_path, minutes):
    """Component-only episode fixture; not a discovered setup or observed action."""
    clock, _, _, engine = make_engine(scope, tmp_path)
    known = clock.sample()
    engine.episodes["component-fixture"] = {
        "anchors": {
            "id": "component-fixture",
            "symbol": "BTCUSDT",
            "expiry": clock.wall() + 3600000,
            "expiry_mono_ms": clock.mono() + 3600000,
            "clock_epoch_id": known["epoch_id"],
        },
        "known_at": clock.wall(),
        "known_mono": clock.mono(),
        "responses": {},
        "last_status": "WATCH",
    }
    clock.advance(minutes * 60000 + 6000)
    engine.tick(clock.wall())
    result = engine.episodes["component-fixture"]["responses"][str(minutes)]
    assert result["state"] == "NO_VALID_QUOTE/UNKNOWN"
    assert not result["actual_delivery_or_ack"] and not result["modeled_fill"]


def structural_clock_replay(scope, root):
    clock, store, journal, engine = make_engine(scope, root)
    grouped = {}
    for b in structural_bars(count=66, symbols=tuple(sorted(SYMBOLS))):
        grouped.setdefault(b.end, []).append(b)
    offset = 846
    for i, oldend in enumerate(sorted(grouped)):
        end = START + (i + 1) * STRUCTURE
        clock.advance(end - 1000 - offset - clock.wall())
        if i % 6 == 0:
            engine.ingest(frame(clock, "binance_usdm_exchange_info", meta_payload()))
        probe_engine(engine, clock, offset)
        clock.advance(end + 50 - offset - clock.wall())
        for b in grouped[oldend]:
            values, _ = b.values(b.end + 1000)
            k = {
                "s": b.spec.symbol,
                "i": "5m",
                "t": end - STRUCTURE,
                "T": end - 1,
                "x": True,
                **{
                    key: str(values[field])
                    for key, field in (
                        ("o", "open"),
                        ("h", "high"),
                        ("l", "low"),
                        ("c", "close"),
                        ("v", "volume"),
                        ("q", "quote_volume"),
                    )
                },
            }
            stream = b.spec.symbol.lower() + "@kline_5m"
            payload = {
                "stream": stream,
                "data": {"e": "kline", "s": b.spec.symbol, "st": 1, "E": end + 1, "k": k},
            }
            normalized = engine.ingest(frame(clock, "binance_usdm_klines_ws", payload, b.spec.symbol, stream))
            assert normalized["bars"], normalized
    engine.flush()
    return clock, store, journal, engine


def test_exchange_ahead_full_factor_regime_setup_funnel_and_persistent_fault(scope, tmp_path):
    clock, store, journal, engine = structural_clock_replay(scope, tmp_path)
    report = engine.report()
    assert report["L23_scan_count"] >= 2, report["reasons"]
    assert report["candidate_states"] and set(report["candidate_states"].values()) == {"WATCH"}
    assert report["latest_scan"]["selected"] == []
    assert any(s["state"] == "TREND_UP" for s in report["latest_scan"]["regimes"].values())
    anchors = [store.episode(id)["anchors"] for id in engine.episodes]
    assert all(a["known_at_ts"] < a["setup_ts"] and a["known_clock_sample"] for a in anchors)
    assert all(
        a["expiry"] > a["setup_ts"]
        and a["expiry_mono_ms"] == d.native_bounds(d.from_record(a["setup_provenance"]), a["expiry"])[0]
        for a in anchors
    )
    assert journal.audit_replay(normalize)["complete_retained_raw_replay"]
    with store._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM market_watch_notifications").fetchone()[0] > 0
        assert not db.execute(
            "SELECT 1 FROM market_watch_notifications WHERE attempted_at_ms IS NOT NULL"
        ).fetchone()
    # Use newly received, causally post-ack quotes at each modeled reaction delay.
    chosen = next(iter(engine.episodes.values()))
    for minute in (1, 3, 5):
        ack_mono = chosen["known_mono"] + minute * 60000
        clock.advance(ack_mono - 500 - clock.mono())
        probe_engine(engine, clock)
        clock.advance(ack_mono + 100 - clock.mono())
        for extra in (1, 2):
            clock.advance(2)
            quote_engine(engine, clock, sequence=minute * 10 + extra, symbol=chosen["anchors"]["symbol"])
        response = chosen["responses"][str(minute)]
        assert response["modeled_ack_mono_ms"] == ack_mono
        assert response["subsequently_received_quote_ts"] > response["modeled_ack_ts"]
        assert response["state"] != "ENTRY_ELIGIBLE" and not response["actual_delivery_or_ack"]
        clock.advance(ack_mono + 6000 - clock.mono())
        engine.tick(clock.wall())
    # A backwards step is recorded as observed, never max(previous wall, raw wall).
    clock.advance(10, wall_step=-900)
    engine.tick(clock.wall())
    assert not engine.quote and not engine.advisory_enabled
    for id in engine.episodes:
        episode = store.episode(id)
        assert episode["state"]["status"] == "CANCELLED"
        assert episode["updated_ts"] == clock.wall()
        assert episode["anchors"] in anchors
    assert all(store.regime(s)["state"] == "UNKNOWN" for s in SYMBOLS)
    # Genuine new process reads only the fabricated SQLite evidence. No fresh epoch
    # or old proof is allowed to erase the durable fault or restore entry readiness.
    script = """
import json,sys
from btc_quant_agent.platform.canary.control import CanaryStore
s=CanaryStore(sys.argv[1])
with s._connect() as db:
    states=[json.loads(v[0])['status'] for v in db.execute('SELECT state FROM selector_episodes')]
assert states and set(states)=={'CANCELLED'}
assert s.get_value('clock_epoch_invalidation')['reason']=='LOCAL_WALL_CLOCK_JUMP'
print(json.dumps({'states':states,'fault_persisted':True}))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "state.sqlite")],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src")},
        timeout=30,
    )
    assert json.loads(result.stdout)["fault_persisted"]
    fresh_clock = EpochClock(clock.wall(), epoch="fabricated-second-process")
    restarted = PublicEngine(scope, fresh_clock, store, journal, "PUBLIC_CANARY")
    assert restarted.clock_fault == "LOCAL_WALL_CLOCK_JUMP" and not restarted.advisory_enabled


def test_quote_capacity_and_user_execution_are_not_inferred_from_clock_proof(scope, tmp_path):
    clock, store, _, engine = make_engine(scope, tmp_path)
    engine.ingest(frame(clock, "binance_usdm_exchange_info", meta_payload()))
    probe_engine(engine, clock)
    clock.advance(100)
    _, r = quote_engine(engine, clock)
    assert r["quote"] and r["quote"]["bid_quantity"] is None and r["quote"]["ask_quantity"] is None
    with store._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM platform_position_versions").fetchone()[0] == 0
    assert engine.report()["actual_user_actions_or_fills"] == 0
