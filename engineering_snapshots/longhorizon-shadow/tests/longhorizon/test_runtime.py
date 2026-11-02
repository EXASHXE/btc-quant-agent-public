import json
import time

import pytest

from btc_quant_agent.platform.canary.public_policy import PublicStop
from btc_quant_agent.platform.canary.public_runtime import run_public
from btc_quant_agent.platform.canary.longhorizon import SYMBOLS, FiniteWindow, MAX_DURATION
from btc_quant_agent.platform.canary.control import BudgetGuard, CanaryStore
from btc_quant_agent.platform.selection.sources import MINUTE
from canary_public.fixtures import meta_payload
from canary_public.test_session02 import Clock
from .fixtures import START, scope, engine_at, probes, quote


class Connection:
    def __init__(self, backend, market):
        self.backend, self.market = backend, market
        self.closed = False
        self.sequence = 0

    def recv(self, timeout):
        if self.closed:
            raise OSError("closed")
        time.sleep(.02)
        b = self.backend
        b.clock.advance(30)
        self.sequence += 1
        if b.step and not self.market and self.sequence == 10:
            b.clock.advance(0, step=900)
        if b.disconnect and not self.market and self.sequence == 10:
            raise OSError("simulated outage")
        symbol = SYMBOLS[(self.sequence - 1) % 3]
        event = b.clock.wall() + b.offset - 50
        if self.market:
            stream = symbol.lower() + "@kline_1m"
            payload = {"e": "kline", "s": symbol, "st": 1, "E": event,
                       "k": {"s": symbol, "i": "1m", "x": False}}
        else:
            stream = symbol.lower() + "@bookTicker"
            payload = {"e": "bookTicker", "s": symbol, "st": 1, "u": self.sequence,
                       "E": event, "T": event - 2, "b": "100", "a": "100.02", "B": "10", "A": "10"}
        return json.dumps({"stream": stream, "data": payload})

    def close(self):
        self.closed = True


class Backend:
    exposure = "SYNTHETIC"

    def __init__(self, clock, status=200, offset=846, step=False, disconnect=False):
        self.clock, self.status, self.offset = clock, status, offset
        self.step, self.disconnect = step, disconnect
        self.calls, self.connections, self.urls = [], [], []
        self.closed = False

    def get(self, url, params, timeout, clock):
        self.calls.append((url, params))
        clock.advance(10)
        first = clock.pair()
        if url.endswith("exchangeInfo"):
            value = meta_payload()
        elif url.endswith("/time"):
            value = {"serverTime": clock.wall() + self.offset}
        elif url.endswith("fundingInfo") or url.endswith("klines"):
            value = []
        else:
            value = {"symbol": params.get("symbol"), "time": clock.wall() + self.offset - 30,
                "openInterest": "1000", "markPrice": "100", "indexPrice": "100", "lastFundingRate": "0.001",
                "nextFundingTime": clock.wall() + 3600000, "closeTime": clock.wall() + self.offset - 30,
                "openTime": clock.wall() - 86400000, "quoteVolume": "10000", "volume": "100"}
        clock.advance(10)
        return self.status, json.dumps(value), first

    def connect(self, url, timeout, on_control):
        self.urls.append(url)
        conn = Connection(self, "/market/" in url)
        self.connections.append(conn)
        return conn

    def close(self):
        self.closed = True
        for conn in self.connections:
            conn.close()


@pytest.mark.parametrize("offset", [0, 846, -846])
def test_finite_foreground_source_shadow_closes_and_seals(tmp_path, offset):
    c = Clock(START + 10)
    s = scope(duration=8000)
    backend = Backend(c, offset=offset)
    result = run_public(s, enabled=True, clock=c, backend=backend, output=tmp_path / "session")
    assert result["sockets_closed"] and result["receiver_threads_stopped"]
    assert result["stop_reason"] in ("AUTHORIZED_UTC_END", "GRANT_WINDOW_EXPIRED"), result["stop_reason"]
    assert result["replay"]["checked_pairs"] > 2 and result["replay"]["status"] == "PARITY_VERIFIED"
    assert len(backend.urls) == 2 and len(backend.calls) >= 10
    assert result["external_notifications"] == result["account_or_order_operations"] == 0
    assert result["native_market_requests"] == 0
    assert not result["source_qualified"] and not result["shadow_advisory_qualified"]
    assert result["model"]["risk"]["entry_eligible_blocked"]
    assert result["session_id"] == "L4-LONGHORIZON-SOURCE-SHADOW-01"
    assert result["run_profile"] == "L4_LONGHORIZON_V1"
    started = json.loads((tmp_path / "session/started.json").read_text())
    assert started["session_id"] == result["session_id"]
    assert (tmp_path / "session/dashboard_final.html").exists()
    seal = json.loads((tmp_path / "session/receipt_seal.json").read_text())
    assert "owner_signed_grant.json" in seal and "dashboard_final.html" in seal
    with pytest.raises(PublicStop, match="ALREADY_CLAIMED"):
        run_public(s, enabled=True, clock=Clock(START + 10), backend=Backend(c), output=tmp_path / "session")


@pytest.mark.parametrize("status", [403, 451, 418, 429])
def test_actual_venue_denial_or_rate_response_stops_without_retry(tmp_path, status):
    c = Clock(START + 10)
    backend = Backend(c, status=status)
    r = run_public(scope(duration=8000), enabled=True, clock=c, backend=backend, output=tmp_path / "denied")
    assert len(backend.calls) == 1 and not backend.urls and r["sockets_closed"]
    assert r["stop_reason"] in ("VENUE_ACCESS_DENIED", "RATE_LIMIT_CIRCUIT_OPEN")


def test_epoch_step_stops_transport_and_writes_durable_fault(tmp_path):
    c = Clock(START + 10)
    r = run_public(scope(duration=8000), enabled=True, clock=c, backend=Backend(c, step=True),
                   output=tmp_path / "stepped")
    assert "CLOCK" in r["stop_reason"]
    assert r["sockets_closed"] and r["model"]["clock_epoch_failure"]
    store = CanaryStore(tmp_path / "stepped/state.sqlite")
    assert store.get_value("clock_epoch_invalidation")


def test_reconnects_have_global_three_per_hour_ceiling(tmp_path):
    _, s, store, _, e = engine_at(tmp_path)
    guard = BudgetGuard(store, s.budget_policy())
    endpoint = s.endpoint("binance_usdm_bbo_ws")
    for i in range(3):
        guard.connection_open("public", endpoint, 1000 + i * 2000)
        guard.connection_close("public")
    with pytest.raises(ValueError, match="BUDGET"):
        guard.connection_open("public", endpoint, 8000)


def test_48h_schedule_budgets_with_clock_refresh_and_two_native_bar_intervals(tmp_path):
    """Accelerated 48h control-plane soak, no strategy backtest or market history."""
    c = Clock(START + 10)
    s = scope()
    window = FiniteWindow(c, START, START + MAX_DURATION)
    store = CanaryStore(tmp_path / "budgets.sqlite")
    guard = BudgetGuard(store, s.budget_policy())
    time_endpoint = s.endpoint("binance_usdm_server_time")
    guard.request(time_endpoint, {}, c.mono())
    c.advance(20)
    guard.request(time_endpoint, {}, c.mono())
    counts = {"time": 2, "oi": 0, "premium": 0, "turnover": 0, "funding": 0, "metadata": 0}
    last = START
    for minute in range(1, 48 * 60):
        target = START + minute * MINUTE + 100
        c.advance(target - c.wall())
        window.check()
        due = ["oi", "premium"]
        if minute % 2 == 0:
            due += ["time"]
        if minute % 5 == 0:
            due += ["funding_info", "turnover"]
        if minute % 58 == 0:
            due += ["exchange_info"]
        for kind in due:
            endpoint = s.endpoint("binance_usdm_" + ("server_time" if kind == "time" else kind))
            for symbol in SYMBOLS if kind in ("oi", "premium") else ("BTCUSDT",):
                guard.request(endpoint, {"symbol": symbol} if kind in ("oi", "premium", "turnover") else {}, c.mono())
                counts[{"funding_info": "funding", "exchange_info": "metadata"}.get(kind, kind)] += 1
        last = target
    assert last > START + 47 * 3600000 and counts["time"] == 1441
    assert not store.get_value("circuit")
    c.advance(START + MAX_DURATION - c.wall())
    with pytest.raises(PublicStop, match="WINDOW_EXPIRED"):
        window.check()


@pytest.mark.parametrize("delay", [1, 3, 5])
def test_response_requires_actual_post_ack_quote_and_never_claims_entry(tmp_path, delay):
    c, _, _, _, e = engine_at(tmp_path)
    known = c.sample()
    anchor = {"id": "component", "symbol": "BTCUSDT", "side": "LONG", "strategy": "trend_pullback",
              "contract": {"symbol": "BTCUSDT", "provider": "binance", "market": "PERPETUAL"},
              "expiry": c.wall() + 3600000, "expiry_mono_ms": c.mono() + 3600000,
              "clock_epoch_id": known["epoch_id"], "chase_cap": "101", "zone_low": "99", "zone_high": "101",
              "entry_mode": "market"}
    # Use the actual metadata contract; no account positions or capital fabricated.
    from btc_quant_agent.platform.canary.public_data import instrument
    from btc_quant_agent.platform.canary.public_io import Wire
    from btc_quant_agent.platform.core import primitive
    anchor["contract"] = primitive(instrument(Wire(**e.metadata["wire"]).payload, "BTCUSDT", Wire(**e.metadata["wire"])).spec)
    e.episodes["component"] = {"anchors": anchor, "known_at": c.wall(), "known_mono": c.mono(),
                               "responses": {}, "last_status": "ARMED"}
    c.advance(delay * MINUTE)
    probes(e, c)
    e.tick(c.wall())
    assert str(delay) not in e.episodes["component"]["responses"]
    c.advance(100)
    for i in range(1, 5):
        quote(e, c, sequence=i)
        c.advance(10)
    e.flush()
    result = e.episodes["component"]["responses"][str(delay)]
    assert result["quote_chronology"] == "POST_MODELED_ACK_NATIVE_AND_RECEIPT_VERIFIED"
    assert result["conditional_market_survival"] == "SURVIVED_CONDITIONALLY"
    assert not result["entry_eligible"] and not result["modeled_fill"]
    assert "CURRENT_CAPITAL_AND_MARGIN_NOT_VERIFIED" in result["vetoes"]
