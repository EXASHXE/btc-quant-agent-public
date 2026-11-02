"""Fabricated continuation cases; original 175 cases are left byte-identical."""
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from test_advisory_foundation import (
    NOW,
    assess,
    configure_scan,
    event_rows,
    force_candidate,
    scanner,
    snapshot,
)

from btc_quant_agent.market_watch import scanner as scanner_module
from btc_quant_agent.market_watch.alerting import _format_price
from btc_quant_agent.market_watch.domain import (
    AlertSeverity,
    DirectionalDecision,
    GridDecision,
    GridPlan,
    InputClock,
    PriceMetrics,
)
from btc_quant_agent.market_watch.evidence import (
    TacticalEvidenceConflictError,
    compute_evidence_id,
)
from btc_quant_agent.market_watch.foundation import (
    actionable_reasons,
    clock_reason,
    increment,
    normalize_quantity,
    reference_reasons,
)
from btc_quant_agent.market_watch.state import MarketWatchStateStore


def test_replacement_missing_quote_preserves_watch_without_action(tmp_path, monkeypatch):
    """New Owner contract supersedes the old gated-data 'no WATCH' assertion."""
    sc = configure_scan(tmp_path, monkeypatch)
    monkeypatch.setattr(sc, "collect_symbol_snapshot", lambda symbol, now: (
        replace(snapshot(symbol), price=PriceMetrics(100.2)), None, ()))
    sent = []

    def send(url, alert, secret, *, payload):
        event = sc.store.get_notification(alert.event_id)
        assert event["status"] == "SENDING" and event["persisted_commit_at_ms"] <= event["attempted_at_ms"]
        saved = sc.store.get_latest_assessment(alert.symbol)
        assert sc.store.get_tactical_feature_evidence(saved["feature_evidence_id"]) is not None
        sent.append((alert.severity, alert.event_id))

    monkeypatch.setattr(scanner_module, "send_market_watch_alert", send)
    assessments, alerts = sc.scan_universe(["BTCUSDT"], notify=True)
    assert assessments[0].directional.decision == DirectionalDecision.WAIT
    assert assessments[0].grid.decision == GridDecision.PAUSE
    assert [a.severity for a in alerts] == [AlertSeverity.WATCH]
    assert sent == [(AlertSeverity.WATCH, alerts[0].event_id)]
    assert "EXECUTABLE_QUOTE_UNKNOWN" in alerts[0].risks


def test_replacement_analytical_candidate_needs_source_authority(tmp_path, monkeypatch):
    """An analytical candidate does not gain LONG authority from its retest alone."""
    force_candidate(monkeypatch)
    sc = scanner(tmp_path)
    unverified = assess(sc, replace(snapshot(), price=PriceMetrics(100.2)))
    verified = assess(sc, snapshot())
    assert unverified.directional.decision == DirectionalDecision.WAIT
    assert "EXECUTABLE_QUOTE_UNKNOWN" in unverified.veto_reasons
    assert verified.directional.decision == DirectionalDecision.LONG


def test_risk_priority_survives_missing_quote(tmp_path, monkeypatch):
    sc = configure_scan(tmp_path, monkeypatch)
    monkeypatch.setattr(sc, "collect_symbol_snapshot", lambda symbol, now: (
        replace(snapshot(symbol), price=PriceMetrics(100.2)), None, ()))
    monkeypatch.setattr(scanner_module, "evaluate_alert_emission", lambda *args: (
        True, AlertSeverity.RISK, ("FABRICATED_CRITICAL_RISK",)))
    _, alerts = sc.scan_universe(["BTCUSDT", "ETHUSDT", "LINKUSDT", "SOLUSDT"], notify=False)
    assert len(alerts) == 4
    assert all(a.severity == AlertSeverity.RISK and a.event_id for a in alerts)


@pytest.mark.parametrize("field,value", [
    ("clock", MagicMock()), ("candle_clocks", None),
    ("candle_counts", {"15m": MagicMock()}), ("symbol_filters", MagicMock()),
    ("symbol_filters", {"tick_size": MagicMock(), "step_size": .001}),
    ("derivative_clocks", {"funding_rate": MagicMock()}),
    ("closed_bar_watermarks", None), ("source_receipt_timestamps", MagicMock()),
    ("price", PriceMetrics(100.2, executable_quote=MagicMock())),
])
def test_invalid_metadata_declines_action_without_mock_numbers(tmp_path, monkeypatch, field, value):
    force_candidate(monkeypatch)
    sc = scanner(tmp_path)
    item = assess(sc, replace(snapshot(), **{field: value}))
    assert item.directional.decision == DirectionalDecision.WAIT
    assert item.grid.decision == GridDecision.PAUSE
    encoded = json.dumps(item.as_dict(), allow_nan=False)
    assert "MagicMock" not in encoded
    assert item.veto_reasons


@pytest.mark.parametrize("value", [MagicMock(), True, None, "1800000000000", 1.5])
def test_unknown_clock_types_are_not_numeric(value):
    assert clock_reason(InputClock(value, value, value), NOW, 1000) == "TIMING_UNKNOWN"
    assert clock_reason(InputClock(NOW, NOW, NOW), value, 1000) == "TIMING_UNKNOWN"
    assert actionable_reasons(MagicMock()) == ("SOURCE_METADATA_UNKNOWN",)


def test_unknown_reference_fields_are_rejected():
    assert reference_reasons(snapshot(), MagicMock(symbol="ETHUSDT"), "ETHUSDT")
    ref = replace(snapshot("ETHUSDT"), clock=InputClock(MagicMock(), None, None))
    assert "REFERENCE_ETHUSDT_TIMING_UNKNOWN" in reference_reasons(snapshot(), ref, "ETHUSDT")


def test_future_reference_mutation_has_no_effect_on_replay(tmp_path, monkeypatch):
    force_candidate(monkeypatch)
    sc = scanner(tmp_path)
    future = replace(snapshot("ETHUSDT"), clock=InputClock(NOW - 1, NOW + 1, NOW + 1))
    first = sc.assess_symbol(snapshot(), None, snapshot(), future, None)
    sc.store.save_symbol_state(first.symbol, first, NOW)
    changed = replace(future, price=PriceMetrics(999999))
    again = sc.assess_symbol(snapshot(), sc.store.get_symbol_state(first.symbol), snapshot(), changed, None)
    assert first.feature_evidence_id == again.feature_evidence_id
    assert first.frozen_inputs_json == again.frozen_inputs_json


def test_changed_frozen_input_under_same_key_conflicts(tmp_path, monkeypatch):
    sc = configure_scan(tmp_path, monkeypatch)
    items, _ = sc.scan_universe(["BTCUSDT"], notify=False)
    first = items[0]
    changed = replace(first.snapshot, price=replace(first.snapshot.price, last_price=101))
    with pytest.raises(TacticalEvidenceConflictError, match="FROZEN_DECISION_INPUT_CONFLICT"):
        sc.assess_symbol(changed, None, snapshot(), snapshot("ETHUSDT"), None)


def test_different_evidence_is_never_overwritten(tmp_path, monkeypatch):
    sc = configure_scan(tmp_path, monkeypatch)
    items, _ = sc.scan_universe(["BTCUSDT"], notify=False)
    first = items[0]
    ev = first.feature_evidence
    with sc.store._connect() as conn:
        before = conn.execute("SELECT evidence_json FROM tactical_feature_evidence_v2 WHERE evidence_id=?", (ev.evidence_id,)).fetchone()[0]
    changed = replace(ev, policy_state_before=replace(ev.policy_state_before, previous_age_bars=9))
    changed = replace(changed, evidence_id=compute_evidence_id(changed))
    with pytest.raises(TacticalEvidenceConflictError):
        sc.store.save_symbol_state(first.symbol, replace(first, feature_evidence=changed), NOW)
    with sc.store._connect() as conn:
        after = conn.execute("SELECT evidence_json FROM tactical_feature_evidence_v2 WHERE evidence_id=?", (ev.evidence_id,)).fetchone()[0]
    assert before == after
    assert sc.store.get_tactical_feature_evidence(ev.evidence_id).evidence_id == ev.evidence_id


def test_multiple_origins_keep_exact_prestate_after_restart(tmp_path, monkeypatch):
    sc = configure_scan(tmp_path, monkeypatch)
    first, _ = sc.scan_universe(["BTCUSDT", "ETHUSDT"], notify=False)
    sc.store = MarketWatchStateStore(tmp_path / "mw.db", clock_ms=lambda: NOW)
    again, _ = sc.scan_universe(["BTCUSDT", "ETHUSDT"], notify=False)
    assert [(a.feature_evidence_id, a.alert_fingerprint) for a in first] == [
        (a.feature_evidence_id, a.alert_fingerprint) for a in again]
    assert all(a.policy_state_before_json == "null" for a in again)
    assert len(event_rows(sc)) == 2


def test_event_creation_crash_after_evidence_commit_restarts_safely(tmp_path, monkeypatch):
    sc = configure_scan(tmp_path, monkeypatch)
    prepare = sc.store.prepare_notification

    def crash(*args):
        raise RuntimeError("FABRICATED_BEFORE_EVENT")

    monkeypatch.setattr(sc.store, "prepare_notification", crash)
    with pytest.raises(RuntimeError, match="BEFORE_EVENT"):
        sc.scan_universe(["BTCUSDT"], notify=False)
    saved = sc.store.get_latest_assessment("BTCUSDT")
    assert saved["feature_evidence_id"] and saved["persisted_commit_at_ms"] == NOW
    assert event_rows(sc) == []
    monkeypatch.setattr(sc.store, "prepare_notification", prepare)
    again, _ = sc.scan_universe(["BTCUSDT"], notify=False)
    assert again[0].feature_evidence_id == saved["feature_evidence_id"]
    assert len(event_rows(sc)) == 1


def test_commit_cannot_precede_decision(tmp_path, monkeypatch):
    force_candidate(monkeypatch)
    sc = scanner(tmp_path)
    item = assess(sc, snapshot())
    with pytest.raises(ValueError, match="COMMIT_BEFORE_DECISION"):
        sc.store.save_symbol_state(item.symbol, item, NOW - 1)
    assert sc.store.get_latest_assessment(item.symbol) is None


def test_regressed_commit_clock_is_unacknowledged(tmp_path, monkeypatch):
    force_candidate(monkeypatch)
    sc = scanner(tmp_path)
    item = assess(sc, snapshot())
    sc.store.clock_ms = lambda: NOW - 1
    with pytest.raises(ValueError, match="COMMIT_CLOCK_ORDER_INVALID"):
        sc.store.save_symbol_state(item.symbol, item, NOW)
    assert sc.store.get_latest_assessment(item.symbol)["persisted_commit_at_ms"] is None
    assert event_rows(sc) == []


@pytest.mark.parametrize("price,tick,step", [(64000.17, .1, .001), (.00001001239, 1e-10, 1e-8)])
def test_price_quantity_formatting_keeps_scale(price, tick, step):
    normalized = increment(price, tick)
    qty = normalize_quantity(.123456789, {"step_size": step})
    assert Decimal(str(normalized)) % Decimal(str(tick)) == 0
    assert Decimal(str(qty)) % Decimal(str(step)) == 0
    text = _format_price(normalized)
    assert Decimal(text.replace(",", "")) == Decimal(str(normalized))
    assert "," in text if price > 1000 else text.startswith("0.00001")


def test_non_tick_grid_is_paused_without_reinventing_levels(tmp_path, monkeypatch):
    force_candidate(monkeypatch)
    monkeypatch.setattr(scanner_module, "evaluate_grid_policy", lambda **kw: GridPlan(
        symbol=kw["symbol"], decision=GridDecision.NEUTRAL, lower_bound=99.005,
        upper_bound=101, stop_loss=98, take_profit=102))
    item = assess(scanner(tmp_path), snapshot())
    assert item.grid.decision == GridDecision.PAUSE
    assert item.grid.lower_bound is None
    assert "GRID_PRECISION_INVALID" in item.grid.reason_codes


def test_action_is_rechecked_at_send_time(tmp_path, monkeypatch):
    sc = configure_scan(tmp_path, monkeypatch)
    ticks = iter([NOW, NOW, NOW, NOW + 6000])
    sc.clock_ms = lambda: next(ticks, NOW + 6000)
    sender = MagicMock()
    monkeypatch.setattr(scanner_module, "send_market_watch_alert", sender)
    sc.scan_universe(["BTCUSDT"], notify=True)
    sender.assert_not_called()
    event = sc.store.get_notification(event_rows(sc)[0][0])
    assert event["status"] == "PENDING" and event["attempts"] == 0
    assert not sc.store.get_symbol_state("BTCUSDT")["last_alert_fingerprint"]


def test_crashed_claim_is_unknown_on_restart_and_never_reclaimed(tmp_path, monkeypatch):
    sc = configure_scan(tmp_path, monkeypatch)
    sc.scan_universe(["BTCUSDT"], notify=False)
    event_id = event_rows(sc)[0][0]
    assert sc.store.claim_notification(event_id, NOW)
    restarted = MarketWatchStateStore(tmp_path / "mw.db", clock_ms=lambda: NOW)
    row = restarted.get_notification(event_id)
    assert row["remote_acceptance_status"] == row["user_delivery_status"] == "UNKNOWN"
    assert not restarted.claim_notification(event_id, NOW + 1)


def test_two_concurrent_claimants_cannot_both_send(tmp_path, monkeypatch):
    sc = configure_scan(tmp_path, monkeypatch)
    sc.scan_universe(["BTCUSDT"], notify=False)
    event_id = event_rows(sc)[0][0]
    other = MarketWatchStateStore(tmp_path / "mw.db", clock_ms=lambda: NOW)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda store: store.claim_notification(event_id, NOW), [sc.store, other]))
    assert sorted(claims) == [False, True]
    assert sc.store.get_notification(event_id)["attempts"] == 1


@pytest.mark.parametrize("field,value,reason", [
    ("decision_time_ms", MagicMock(), "SOURCE_DECISION_TIMING_UNKNOWN"),
    ("snapshot_hash", MagicMock(), "SOURCE_IDENTITY_UNKNOWN"),
    ("symbol", None, "SOURCE_IDENTITY_UNKNOWN"),
])
def test_invalid_decision_identity_has_typed_decline(tmp_path, field, value, reason):
    with pytest.raises(ValueError, match=reason):
        assess(scanner(tmp_path), replace(snapshot(), **{field: value}))


def test_verified_source_to_durable_case_with_fake_sender(tmp_path, monkeypatch):
    from test_live_v1_decision_models import sample_analysis

    from btc_quant_agent.approval.store import LiveState, LiveStore
    from btc_quant_agent.decision.risk import RiskCompilerV1, RiskPolicyV1
    from btc_quant_agent.decision.service import TacticalLiveService

    force_candidate(monkeypatch)
    sc = scanner(tmp_path)
    snap = snapshot()
    snap = replace(snap, price=replace(snap.price, quote_volume_24h=1000000))
    item = assess(sc, snap)
    sc.store.save_symbol_state(item.symbol, item, NOW)
    primary = AsyncMock()
    primary.analyze.side_effect = lambda case, mode: sample_analysis(case)
    notifier = AsyncMock()
    notifier.send_proposal.return_value = "FABRICATED_SENDER_ACCEPTANCE"
    store = LiveStore(str(tmp_path / "advisory.db"))
    service = TacticalLiveService(store, primary, RiskCompilerV1(RiskPolicyV1()),
        notifier=notifier, market_watch=SimpleNamespace(config=sc.config), clock_ms=lambda: NOW + 1)
    proposal = asyncio.run(service.run_assessment(item))
    assert proposal is not None and proposal.recommended_notional_usdt > 0
    assert store.state(proposal.case_id) == LiveState.WAITING_APPROVAL
    assert service.exchange_write_count == 0
    assert sc.store.get_tactical_feature_evidence(item.feature_evidence_id) is not None
    notifier.send_proposal.assert_awaited_once()
