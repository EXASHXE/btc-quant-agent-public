"""Entirely simulated native-shaped observations; no market datasets."""

from dataclasses import replace
from datetime import datetime
import json

from btc_quant_agent.platform.canary import longhorizon as lh
from btc_quant_agent.platform.canary.control import CanaryStore
from btc_quant_agent.platform.canary.public_journal import PublicJournal
from btc_quant_agent.platform.canary.longhorizon_runtime import LongEngine
from btc_quant_agent.platform.core import fingerprint
from canary_public.fixtures import meta_payload
from canary_public.test_clock_domain import frame as native_frame
from canary_public.test_session02 import Clock

START = int(datetime.fromisoformat("2026-10-31T06:00:00+00:00").timestamp() * 1000)


def body(start=START, duration=lh.MAX_DURATION):
    data = {
        "version": "L4_LONGHORIZON_SOURCE_GRANT_V1", "session_id": lh.SESSION,
        "authorization_reference": "OWNER-V070-L4-LONGHORIZON-FABRICATED_TEST_ONLY",
        "provider": "binance", "market": "USD_M_USDT_LINEAR_PERPETUAL",
        "permitted_use": "OWNER_CONFIRMED_PERSONAL_NONCOMMERCIAL_PUBLIC_READONLY",
        "symbols": lh.SYMBOLS, "endpoint_ids": lh.IDS,
        "endpoint_fields": {e["id"]: e["fields"] for e in json.loads(lh.DOCUMENT.read_text())["endpoints"]},
        "output_relative_path": "artifacts/prospective_48h/session_01",
        "issued_utc_ms": start - 1000, "start_utc_ms": start, "end_utc_ms": start + duration,
        "source_sha256_fingerprint": fingerprint(lh.source_hashes()), "canonical_documentation_head": lh.HEAD,
        "documentation_sha256": lh.sha(lh.DOCUMENT), "clock_qualification_receipt_sha256": "0" * 64,
        "egress_route": {"egress_mode": "DIRECT"}, "clock_contract": "L4_CLOCK_DOMAIN_V2",
        "wall_jump_ms": 50, "max_offset_uncertainty_ms": 100, "max_probe_age_ms": 300000,
        "startup_independent_probes": 2, "startup_probe_gap_ms": 10,
        "subsequent_probe_interval_ms": 120000, "rest_weight_per_minute": 60,
        "retry_reserve_weight_per_minute": 10, "time_calls_per_minute": 2, "controls_per_second": 2,
        "connections": 2, "subscriptions": 9, "reconnects_per_hour": 3, "ws_messages_per_second": 200,
        "pending_records": 128, "max_retries": 3, "repair_calls_per_minute": 6, "repair_rows_per_call": 99,
        "raw_retention_hours": 36, "normalized_retention_hours": 168, "raw_bytes": 8 * 1024**3,
        "auxiliary_bytes": 4 * 1024**3, "disk_reserve_bytes": 2 * 1024**3,
        "automatic_restart": False, "external_notifications": False, "account_or_order_operations": False}
    return data


def scope(start=START, duration=lh.MAX_DURATION):
    b = lh.GrantBody.model_validate_json(json.dumps(body(start, duration)))
    e = lh.GrantEnvelope(grant=b, key_id="FABRICATED", signature_algorithm="Ed25519",
                         signature_base64="NOT_AUTHORIZED")
    return lh.make_scope(e, fabricated=True)


def frame(clock, endpoint, payload, symbol="*", stream=None, request=None, params=None):
    return replace(native_frame(clock, endpoint, payload, symbol, stream, request),
                   exposure="SYNTHETIC", params=params or {})


def probes(engine, clock, offset=846):
    for _ in range(2):
        clock.advance(10)
        request = clock.sample()
        native = clock.wall() + offset + 10
        clock.advance(20)
        engine.ingest(frame(clock, "binance_usdm_server_time", {"serverTime": native}, request=request))


def engine_at(root, start=START, offset=846):
    root.mkdir(parents=True, exist_ok=True)
    c = Clock(start + 10)
    s = scope(start)
    store = CanaryStore(root / "state.sqlite", clock_ms=c.wall)
    journal = PublicJournal(root, store, c, exposure="SYNTHETIC", reserve=0)
    engine = LongEngine(s, c, store, journal, "SYNTHETIC")
    engine.ingest(frame(c, "binance_usdm_exchange_info", meta_payload()))
    probes(engine, c, offset)
    return c, s, store, journal, engine


def quote(engine, clock, symbol="BTCUSDT", sequence=1, bid="100.00", offset=846):
    event = clock.wall() + offset - 50
    stream = symbol.lower() + "@bookTicker"
    return engine.ingest(frame(clock, "binance_usdm_bbo_ws", {"stream": stream, "data": {
        "e": "bookTicker", "st": 1, "s": symbol, "u": sequence, "E": event, "T": event - 2,
        "b": bid, "a": str(float(bid) + .02), "B": "100", "A": "100"}}, symbol, stream))


def candle(engine, clock, start, interval=60000, symbol="BTCUSDT", close=100.5, offset=846):
    end = start + interval
    stream = symbol.lower() + ("@kline_1m" if interval == 60000 else "@kline_5m")
    payload = {"stream": stream, "data": {"e": "kline", "s": symbol, "st": 1,
        "E": clock.wall() + offset - 30, "k": {"s": symbol, "i": "1m" if interval == 60000 else "5m",
        "t": start, "T": end - 1, "x": True, "o": str(close - .1), "h": str(close + 1),
        "l": str(close - 1), "c": str(close), "v": "100", "q": str(100 * close)}}}
    return engine.ingest(frame(clock, "binance_usdm_klines_ws", payload, symbol, stream))


def structural_replay(root, count=201):
    from btc_quant_agent.platform.selection.fixtures import structural_bars
    from btc_quant_agent.platform.selection.sources import STRUCTURE
    c, s, store, journal, engine = engine_at(root)
    grouped = {}
    for bar in structural_bars(count=count, symbols=tuple(sorted(lh.SYMBOLS))):
        grouped.setdefault(bar.end, []).append(bar)
    for i, key in enumerate(sorted(grouped)):
        end = START + (i + 1) * STRUCTURE
        c.advance(end - 1000 - 846 - c.wall())
        if i % 6 == 0:
            engine.ingest(frame(c, "binance_usdm_exchange_info", meta_payload()))
        probes(engine, c)
        c.advance(end + 50 - 846 - c.wall())
        for bar in grouped[key]:
            values, _ = bar.values(bar.end + 1000)
            stream = bar.spec.symbol.lower() + "@kline_5m"
            payload = {"stream": stream, "data": {"e": "kline", "s": bar.spec.symbol, "st": 1,
                "E": end + 1, "k": {"s": bar.spec.symbol, "i": "5m", "t": end - STRUCTURE,
                "T": end - 1, "x": True, **{k: str(values[f]) for k, f in (
                    ("o", "open"), ("h", "high"), ("l", "low"), ("c", "close"),
                    ("v", "volume"), ("q", "quote_volume"))}}}}
            result = engine.ingest(frame(c, "binance_usdm_klines_ws", payload, bar.spec.symbol, stream))
            if not result["bars"]:
                raise AssertionError(result["reasons"])
    engine.flush()
    return c, s, store, journal, engine
