"""Fabricated-only foundation acceptance. No accounts, market payloads or network."""
from __future__ import annotations

import asyncio
import json
import socket
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from test_market_watch import make_candle_series, make_dummy_tf

from btc_quant_agent.config import DataConfig
from btc_quant_agent.data.binance import BinancePublicClient
from btc_quant_agent.decision.service import TacticalLiveService
from btc_quant_agent.market_watch import scanner as scanner_module
from btc_quant_agent.market_watch.alerting import NotificationNotSent, _format_price
from btc_quant_agent.market_watch.config import MarketWatchConfig, compute_required_closed_bars
from btc_quant_agent.market_watch.domain import (
    AlertSeverity, CandidateStatus, DerivativesMetrics, DirectionalDecision, ExecutableQuote,
    InputClock, MarketSnapshot, PlaybookCandidate, PlaybookType, PriceMetrics,
    PriceSource, QuoteVerification, ScanHealth,
)
from btc_quant_agent.market_watch.foundation import (
    actionable_reasons, increment, normalize_quantity, reference_reasons,
)
from btc_quant_agent.market_watch.scanner import MarketWatchScanner
from btc_quant_agent.market_watch.state import MarketWatchStateStore, compute_decision_fingerprint

NOW = 1_800_000_000_000


@pytest.fixture(autouse=True)
def forbid_transport(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("SYNTHETIC_ONLY_NETWORK_BLOCKED")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)


def snapshot(symbol="BTCUSDT", price=100.2):
    clock = InputClock(NOW - 1000, NOW - 100, NOW - 100)
    quote = ExecutableQuote(symbol, price - price * .0001, price + price * .0001,
        "FABRICATED_TEST_AUTHORITY", clock, PriceSource.EXECUTABLE_BID_ASK,
        QuoteVerification.VERIFIED)
    frames = {name: make_dummy_tf(symbol, name, close=price, ema_fast=100, atr=.8)
              for name in ("15m", "1h", "4h")}
    return MarketSnapshot(symbol, NOW, NOW - 100, NOW, PriceMetrics(price,
        executable_quote=quote), frames["15m"], frames["1h"], frames["4h"],
        DerivativesMetrics(funding_rate=.0001, current_open_interest=1000,
                           oi_1h_change=.01, spread_bps=1), "fabricated-snapshot",
        clock=clock, candle_clocks={name: clock for name in frames},
        candle_counts={name: compute_required_closed_bars(MarketWatchConfig()) for name in frames},
        derivative_clocks={name: clock for name in ("funding_rate", "current_open_interest", "oi_1h_change")},
        symbol_filters={"tick_size": .01, "step_size": .001},
        reference_clocks={"BTCUSDT": clock, "ETHUSDT": clock},
        closed_bar_watermarks={name: NOW - 1000 for name in frames})


def scanner(tmp_path, *, client=None):
    cfg = MarketWatchConfig(feishu_enabled=True, min_action_entry_quality="POOR")
    store = MarketWatchStateStore(tmp_path / "mw.db", clock_ms=lambda: NOW)
    return MarketWatchScanner(cfg, client or SimpleNamespace(), store, clock_ms=lambda: NOW)


def force_candidate(monkeypatch, *, side=DirectionalDecision.LONG, scale=1):
    candidate = PlaybookCandidate(PlaybookType.TREND_PULLBACK, CandidateStatus.ACTIONABLE,
        side, 100.001 * scale, 100.209 * scale,
        (99.101 if side == DirectionalDecision.LONG else 101.101) * scale,
        (105.111 if side == DirectionalDecision.LONG else 95.111) * scale,
        (108.111 if side == DirectionalDecision.LONG else 92.111) * scale,
        "FABRICATED_STRUCTURE", ("FABRICATED_CANDIDATE",), (), NOW - 1000)
    monkeypatch.setattr(scanner_module, "evaluate_all_playbook_candidates", lambda **kw: (candidate,))
    # Source gate must run even when the existing independent strategy gates admit a candidate.
    monkeypatch.setattr(scanner_module, "check_fatal_vetoes", lambda **kw: (False, ()))


def assess(sc, snap):
    return sc.assess_symbol(snap, None, snapshot("BTCUSDT"), snapshot("ETHUSDT"), None)


class FakeClient:
    def __init__(self, mode):
        self.mode = mode
    def klines(self, symbol, interval, limit):
        step = {"15m": 900000, "1h": 3600000, "4h": 14400000}[interval]
        return [replace(c, available_at_ms=NOW - 50) for c in make_candle_series(
            symbol, interval, count=limit, start_ms=NOW - limit * step - 1000, step_ms=step)]
    def collect_derivatives(self, symbol, **kwargs):
        if self.mode == "total":
            raise RuntimeError("FABRICATED_OUTAGE")
        return SimpleNamespace(snapshot=SimpleNamespace(mark_price=100),
                               field_availability={"funding_rate": False},
                               endpoint_errors={"premium": "FABRICATED_MISSING"})
    def _optional_get(self, *args):
        return None
    def server_time_ms(self):
        return NOW


@pytest.mark.parametrize("mode", ["total", "partial"])
def test_derivative_failure_retains_candles_and_unknowns(tmp_path, mode):
    sc = scanner(tmp_path, client=FakeClient(mode))
    snap, health, reasons = sc.collect_symbol_snapshot("BTCUSDT", NOW)
    assert snap is not None and health == ScanHealth.DEGRADED
    assert snap.derivatives.premium_index_time_ms is None
    assert snap.derivatives.next_funding_time_ms is None
    assert snap.derivatives.endpoint_errors
    assert snap.derivatives.funding_rate is None
    assert snap.price.executable_quote is None
    assert snap.price.source == PriceSource.CLOSED_CANDLE
    assert snap.tf_15m.latest_closed_bar is not None
    assert "DERIVATIVES_FAILED" in actionable_reasons(snap)
    assert reasons


def test_klines_receive_clock_is_post_request(monkeypatch):
    now = [1000]
    client = BinancePublicClient(DataConfig(), receive_clock_ms=lambda: now[0])
    row = [1, "1", "2", "1", "1.5", "10", 999, "15", 2, "5"]
    def request(path, params=None):
        if path.endswith("time"):
            return {"serverTime": 1000}
        now[0] = 9000
        return [row]
    monkeypatch.setattr(client, "_request", request)
    candles = client.klines("BTCUSDT", "15m")
    assert candles[0].available_at_ms == 9000
    assert candles[0].close_time_ms == 999
    assert client._parse_klines([row], "BTCUSDT", "15m", 1000)[0].available_at_ms is None


@pytest.mark.parametrize("kind,expected", [
    ("missing", "EXECUTABLE_QUOTE_UNKNOWN"),
    ("unverified", "EXECUTABLE_QUOTE_UNVERIFIED"),
    ("stale", "EXECUTABLE_QUOTE_STALE"),
    ("unknown_time", "EXECUTABLE_QUOTE_TIMING_UNKNOWN"),
    ("mark", "EXECUTABLE_QUOTE_UNVERIFIED"),
    ("future", "EXECUTABLE_QUOTE_CLOCK_ORDER_INVALID"),
])
def test_quote_semantics_fail_closed(tmp_path, monkeypatch, kind, expected):
    force_candidate(monkeypatch)
    snap = snapshot()
    quote = snap.price.executable_quote
    if kind == "missing": quote = None
    elif kind == "unverified": quote = replace(quote, verification=QuoteVerification.UNKNOWN)
    elif kind == "stale": quote = replace(quote, clock=InputClock(NOW - 6000, NOW - 5500, NOW - 5500))
    elif kind == "unknown_time": quote = replace(quote, clock=InputClock())
    elif kind == "mark": quote = replace(quote, source=PriceSource.CLOSED_CANDLE)
    elif kind == "future": quote = replace(quote, clock=InputClock(NOW, NOW + 1, NOW + 1))
    snap = replace(snap, price=replace(snap.price, executable_quote=quote))
    a = assess(scanner(tmp_path), snap)
    assert a.directional.decision == DirectionalDecision.WAIT
    assert expected in a.veto_reasons
    assert not a.actionable_playbooks
    assert a.feature_evidence.decision_trace.final_directional_decision == "WAIT"
    assert a.snapshot.price.last_price == 100.2


def test_valid_quote_is_actionable_without_fill(tmp_path, monkeypatch):
    force_candidate(monkeypatch)
    snap = snapshot()
    assert actionable_reasons(snap) == ()
    a = assess(scanner(tmp_path), snap)
    assert a.directional.decision == DirectionalDecision.LONG
    assert "fill_price" not in a.as_dict()


@pytest.mark.parametrize("change,reason", [
    ({"candle_counts": {}}, "BARS_15m_INSUFFICIENT"),
    ({"candle_clocks": {}}, "BARS_15m_TIMING_UNKNOWN"),
    ({"derivative_clocks": {}}, "DERIVATIVES_funding_rate_TIMING_UNKNOWN"),
    ({"symbol_filters": {}}, "SYMBOL_FILTERS_UNKNOWN"),
    ({"reference_clocks": {}}, "REFERENCE_ETHUSDT_TIMING_UNKNOWN"),
    ({"health": ScanHealth.DEGRADED}, "SOURCE_HEALTH_DEGRADED"),
])
def test_required_inputs_have_deterministic_reasons(change, reason):
    snap = replace(snapshot(), **change)
    assert reason in actionable_reasons(snap)
    assert actionable_reasons(snap) == tuple(sorted(set(actionable_reasons(snap))))


def test_late_candle_does_not_move_decision(tmp_path):
    class LateClient(FakeClient):
        def klines(self, *args):
            return [replace(c, available_at_ms=NOW + 5000) for c in super().klines(*args)]
    snap, _, _ = scanner(tmp_path, client=LateClient("partial")).collect_symbol_snapshot("BTCUSDT", NOW)
    assert snap.decision_time_ms == NOW
    assert "BARS_15m_CLOCK_ORDER_INVALID" in actionable_reasons(snap)


@pytest.mark.parametrize("kind", ["future", "unknown", "skew", "bars", "symbol"])
def test_benchmark_excluded_before_context(tmp_path, monkeypatch, kind):
    force_candidate(monkeypatch)
    ref = snapshot("ETHUSDT")
    if kind == "future": ref = replace(ref, clock=InputClock(NOW - 1000, NOW + 1, NOW + 1))
    if kind == "unknown": ref = replace(ref, clock=InputClock())
    if kind == "skew": ref = replace(ref, clock=InputClock(NOW - 100000, NOW - 90000, NOW - 90000))
    if kind == "bars": ref = replace(ref, closed_bar_watermarks={})
    if kind == "symbol": ref = replace(ref, symbol="WRONG")
    real = scanner_module.evaluate_benchmark_context
    def context(**kw):
        assert kw["eth_snapshot"] is None
        return real(**kw)
    monkeypatch.setattr(scanner_module, "evaluate_benchmark_context", context)
    a = scanner(tmp_path).assess_symbol(snapshot(), None, snapshot(), ref, None)
    assert a.directional.decision == DirectionalDecision.WAIT
    assert any(code.startswith("REFERENCE_ETHUSDT_") for code in a.veto_reasons)
    assert reference_reasons(snapshot(), ref, "ETHUSDT")


@pytest.mark.parametrize("scale,tick,step", [(1, .1, .001), (1e-7, 1e-10, 1e-8)])
@pytest.mark.parametrize("side", [DirectionalDecision.LONG, DirectionalDecision.SHORT])
def test_tick_step_and_conservative_stop(tmp_path, monkeypatch, scale, tick, step, side):
    from decimal import Decimal
    force_candidate(monkeypatch, side=side, scale=scale)
    snap = snapshot(price=100.2 * scale)
    snap = replace(snap, symbol_filters={"tick_size": tick, "step_size": step})
    a = assess(scanner(tmp_path), snap)
    d = a.directional
    for value in (d.entry_low, d.entry_high, d.stop_loss, d.take_profit_1, d.take_profit_2):
        assert value > 0 and Decimal(str(value)) % Decimal(str(tick)) == 0
        assert _format_price(value) != "0"
    stop = (99.101 if side == DirectionalDecision.LONG else 101.101) * scale
    assert d.stop_loss >= stop if side == DirectionalDecision.LONG else d.stop_loss <= stop
    qty = normalize_quantity(.123456789, snap.symbol_filters)
    assert qty <= .123456789 and Decimal(str(qty)) % Decimal(str(step)) == 0
    changed = replace(a, directional=replace(d, stop_loss=d.stop_loss + tick))
    assert compute_decision_fingerprint(a) != compute_decision_fingerprint(changed)


def test_missing_precision_no_claim_and_zero_rejected():
    with pytest.raises(ValueError, match="SYMBOL_FILTERS_UNKNOWN"):
        normalize_quantity(1, {})
    with pytest.raises(ValueError, match="ZERO"):
        increment(.000001, .01)


def configure_scan(tmp_path, monkeypatch):
    force_candidate(monkeypatch)
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://fabricated.invalid/no-network")
    sc = scanner(tmp_path)
    monkeypatch.setattr(sc, "collect_symbol_snapshot", lambda symbol, now: (snapshot(symbol), ScanHealth.OK, ()))
    return sc


def event_rows(sc):
    with sc.store._connect() as conn:
        return conn.execute("SELECT event_id FROM market_watch_notifications").fetchall()


def test_notify_false_then_true_commit_before_sender_and_restart(tmp_path, monkeypatch):
    sc = configure_scan(tmp_path, monkeypatch)
    sent = []
    def send(url, alert, secret, *, payload):
        row = sc.store.get_notification(alert.event_id)
        saved = sc.store.get_latest_assessment("BTCUSDT")
        assert saved is not None and saved["persisted_commit_at_ms"] <= row["attempted_at_ms"]
        assert row["status"] == "SENDING"
        assert row["decision_time_ms"] <= row["persisted_commit_at_ms"] <= row["attempted_at_ms"]
        assert json.loads(row["payload_json"]) == payload
        assert alert.event_id in json.dumps(payload)
        sent.append(alert.event_id)
    monkeypatch.setattr(scanner_module, "send_market_watch_alert", send)
    sc.scan_universe(["BTCUSDT"], notify=False)
    assert not sent and len(event_rows(sc)) == 1
    state = sc.store.get_symbol_state("BTCUSDT")
    assert not state["last_alert_fingerprint"]
    assert sc.store.get_latest_assessment("BTCUSDT")["notification_sent"] == 0
    sc.scan_universe(["BTCUSDT"], notify=True)
    assert len(sent) == 1
    event_id = sent[0]
    assert sc.store.get_notification(event_id)["status"] == "SENDER_ACCEPTED"
    sc.store = MarketWatchStateStore(tmp_path / "mw.db", clock_ms=lambda: NOW)
    sc.scan_universe(["BTCUSDT"], notify=True)
    assert sent == [event_id] and len(event_rows(sc)) == 1


def test_definite_failure_retries_same_id_and_frozen_payload(tmp_path, monkeypatch):
    sc = configure_scan(tmp_path, monkeypatch)
    calls = []
    def send(url, alert, secret, *, payload):
        calls.append((alert.event_id, payload))
        if len(calls) == 1:
            raise NotificationNotSent("FABRICATED_PRE_TRANSPORT_FAILURE")
    monkeypatch.setattr(scanner_module, "send_market_watch_alert", send)
    sc.scan_universe(["BTCUSDT"], notify=True)
    assert sc.store.get_notification(calls[0][0])["status"] == "FAILED"
    sc.store = MarketWatchStateStore(tmp_path / "mw.db", clock_ms=lambda: NOW)
    sc.scan_universe(["BTCUSDT"], notify=True)
    sc.scan_universe(["BTCUSDT"], notify=True)
    assert len(calls) == 2 and calls[0] == calls[1]
    assert len(event_rows(sc)) == 1


@pytest.mark.parametrize("crash", [False, True])
def test_ambiguous_send_or_ack_crash_is_not_retried(tmp_path, monkeypatch, crash):
    sc = configure_scan(tmp_path, monkeypatch)
    calls = []
    def send(url, alert, secret, *, payload):
        calls.append(alert.event_id)
        if not crash:
            raise TimeoutError("REMOTE_ACCEPTANCE_UNKNOWN")
    monkeypatch.setattr(scanner_module, "send_market_watch_alert", send)
    if crash:
        def lost_ack(*args):
            raise RuntimeError("CRASH_AFTER_REMOTE_ACCEPTANCE")
        monkeypatch.setattr(sc.store, "acknowledge_notification", lost_ack)
        with pytest.raises(RuntimeError, match="CRASH_AFTER"):
            sc.scan_universe(["BTCUSDT"], notify=True)
    else:
        sc.scan_universe(["BTCUSDT"], notify=True)
    event_id = calls[0]
    assert sc.store.get_notification(event_id)["status"] == ("SENDING" if crash else "UNKNOWN")
    assert not sc.store.get_symbol_state("BTCUSDT")["last_alert_fingerprint"]
    sc.store = MarketWatchStateStore(tmp_path / "mw.db", clock_ms=lambda: NOW)
    sc.scan_universe(["BTCUSDT"], notify=True)
    assert calls == [event_id]


def test_bounded_retry_and_atomic_claim(tmp_path, monkeypatch):
    sc = configure_scan(tmp_path, monkeypatch)
    sc.scan_universe(["BTCUSDT"], notify=False)
    event_id = event_rows(sc)[0][0]
    another = MarketWatchStateStore(tmp_path / "mw.db", clock_ms=lambda: NOW)
    for _ in range(3):
        assert sc.store.claim_notification(event_id, NOW)
        assert not another.claim_notification(event_id, NOW)
        sc.store.fail_notification(event_id, NOW, "NOT_SENT", definitely_not_sent=True)
    assert not another.claim_notification(event_id, NOW)
    assert sc.store.get_notification(event_id)["attempts"] == 3


def test_gated_data_never_attempts_notification(tmp_path, monkeypatch):
    sc = configure_scan(tmp_path, monkeypatch)
    monkeypatch.setattr(sc, "collect_symbol_snapshot", lambda symbol, now: (
        replace(snapshot(symbol), price=PriceMetrics(100.2)), ScanHealth.OK, ()))
    def send(*args, **kwargs):
        pytest.fail("gated input attempted notification")
    monkeypatch.setattr(scanner_module, "send_market_watch_alert", send)
    assessments, alerts = sc.scan_universe(["BTCUSDT"], notify=True)
    assert assessments[0].directional.decision == DirectionalDecision.WAIT
    assert alerts == [] and event_rows(sc) == []


def test_decision_service_cannot_promote_unknown_quote(tmp_path, monkeypatch):
    force_candidate(monkeypatch)
    a = assess(scanner(tmp_path), replace(snapshot(), price=PriceMetrics(100.2)))
    service = TacticalLiveService(SimpleNamespace(), AsyncMock(), SimpleNamespace(), clock_ms=lambda: NOW)
    service.analyze_case = AsyncMock()
    assert asyncio.run(service.run_assessment(a)) is None
    service.analyze_case.assert_not_called()
