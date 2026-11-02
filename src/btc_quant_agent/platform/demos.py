"""Deterministic required demonstrations with assertions and reproducible artifacts."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from btc_quant_agent.market_watch.alerting import NotificationNotSent

from .advisory import gate
from .backtest import build_pipeline, run
from .config import PlatformConfig, StrategyConfig
from .core import (
    Candle,
    DataProvenance,
    DerivativeSnapshot,
    ExecutableQuote,
    InstrumentSpec,
    Lifecycle,
    MarketEvent,
    UserReportedFill,
    primitive,
)
from .data import START, SyntheticProvider, histories
from .position_management import AdvisoryStore, supervise
from .reporting import compare, save_run, source_identity, write_json
from .strategies import evaluate


def market(price: float, minute: int, *, low: float | None = None, quote: bool = True) -> MarketEvent:
    spec = InstrumentSpec("BTCUSDT")
    ts = START + minute * 60000
    p = DataProvenance("synthetic", f"position-demo:{minute}", ts - 110, ts - 10, ts)
    price = Decimal(str(price))
    q = (
        ExecutableQuote(
            spec.symbol, price - Decimal(".01"), price + Decimal(".01"), p, Decimal("1000"), Decimal("1000")
        )
        if quote
        else None
    )
    candle = Candle(
        spec.symbol,
        "1m",
        ts - 60110,
        ts - 110,
        float(price),
        float(price) + 0.1,
        low if low is not None else float(price) - 0.1,
        float(price),
        1000,
        1000 * float(price),
        500,
        10,
        True,
        ts,
    )
    return MarketEvent(
        spec, candle, p, ts, q, DerivativeSnapshot(p, 1000, "BASE", 0.0001, False, mark_price=float(price))
    )


def shock_delays(config=None):
    c = config or PlatformConfig(scenario="shock", strategies=[StrategyConfig(id="shock_reversal")])
    c = c.model_copy(update={"entry": c.entry.model_copy(update={"region_bps": 150})})
    events = SyntheticProvider().events(c)
    pipeline, indices = build_pipeline(events, c)
    group = histories(events)[c.universe[0]]
    candidate = None
    for i, event in enumerate(group):
        candidate = evaluate(pipeline, event, i, c.strategies[0], c)
        if candidate:
            break
    if candidate is None:
        raise AssertionError("shock fixture did not generate a setup")
    output = []
    for delay in (1, 5, 15):
        trial = c.model_copy(update={"execution": c.execution.model_copy(update={"delay_minutes": delay})})
        future = group[i + delay]
        plan = gate(replace(candidate, state=Lifecycle.ARMED), future, trial)
        output.append({"delay_minutes": delay, "plan": primitive(plan)})
    assert output[0]["plan"]["action"] == "ENTRY_ELIGIBLE"
    assert output[-1]["plan"]["state"] == "EXPIRED"
    return output


def position_demo(output):
    path = Path(output) / "positions.sqlite"
    store = AdvisoryStore(path)
    event = market(100, 1)
    fill = UserReportedFill(
        "demo-user-fill-1",
        "demo-position",
        "BTCUSDT",
        "LONG",
        Decimal("100"),
        Decimal("1"),
        event.decision_ts - 1,
        event.decision_ts,
    )
    p = store.report(fill, event.spec, stop=Decimal("98"))
    actions = [
        supervise(p, market(100.1, 2)),
        supervise(p, market(101.2, 3), atr=0.2),
        supervise(p, market(103.2, 4)),
        supervise(p, market(97, 5, low=96)),
    ]
    assert [a.action for a in actions] == ["HOLD", "TIGHTEN_STOP", "PARTIAL_EXIT", "EXIT"]
    assert store.position(p.id).status == "OPEN"
    close = replace(
        fill,
        report_id="demo-user-close-1",
        price=Decimal("97"),
        operation="CLOSE",
        user_action_ts=event.decision_ts + 5 * 60000,
        received_ts=event.decision_ts + 5 * 60000,
    )
    closed = store.report(close, event.spec)
    assert closed.status == "CLOSED"
    return {
        "fixture": "synthetic user-reported inputs; not an Owner execution report",
        "initial": primitive(p),
        "recommendations": primitive(actions),
        "confirmed_close": primitive(closed),
    }


def notification_demo(output):
    path = Path(output) / "notifications.sqlite"
    store = AdvisoryStore(path)
    ts = START + 1000000
    identity = store.commit_decision({"action": "WATCH", "fixture": "synthetic"}, ts, ts)
    event_id = store.prepare(identity, "BTCUSDT", ts)
    assert store.dispatch(event_id, lambda payload: None, ts, notify=False) == "PENDING"

    def failed(payload):
        raise NotificationNotSent("fabricated definite no-send")

    first = store.dispatch(event_id, failed, ts)
    assert first == "FAILED"
    calls = []
    restarted = AdvisoryStore(path)
    status = restarted.dispatch(event_id, lambda payload: calls.append(payload), ts + 1)
    again = AdvisoryStore(path).dispatch(event_id, lambda payload: calls.append(payload), ts + 2)
    assert status == again == "SENDER_ACCEPTED" and len(calls) == 1
    unknown_id = store.commit_decision({"action": "EXIT", "fixture": "ambiguous send"}, ts + 3, ts + 3)
    unknown = store.prepare(unknown_id, "BTCUSDT", ts + 3)

    def ambiguous(payload):
        raise TimeoutError("fabricated unknown remote delivery")

    assert store.dispatch(unknown, ambiguous, ts + 3) == "UNKNOWN"
    assert AdvisoryStore(path).dispatch(unknown, lambda p: calls.append(p), ts + 4) == "UNKNOWN"
    crash_id = store.commit_decision({"action": "EXIT", "fixture": "crashed claim"}, ts + 5, ts + 5)
    crash = store.prepare(crash_id, "BTCUSDT", ts + 5)
    assert store.claim_notification(crash, ts + 5)
    assert AdvisoryStore(path).dispatch(crash, lambda p: calls.append(p), ts + 6) == "SENDING"
    return {
        "event_id": event_id,
        "first_attempt": first,
        "after_restart": status,
        "fake_sender_calls": len(calls),
        "ambiguous_delivery": "UNKNOWN; no automatic retry",
        "crashed_claim": "SENDING; remote acceptance UNKNOWN",
        "user_delivery_status": "UNKNOWN",
        "external_notifications_sent": 0,
    }


def demonstrate(output, scenario="all"):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[3]
    from .config import load_config

    selected = {str(x) for x in range(1, 10)} if scenario == "all" else {str(scenario)}
    if not selected <= set(map(str, range(1, 10))):
        raise ValueError("scenario must be all or a number from 1 to 9")
    results = {}
    configs = {
        name: load_config(root / "configs" / (name + ".yaml"))
        for name in ("trend_breakout", "bollinger_reversion", "multi_strategy_regime")
    }
    for number, name in (
        ("1", "trend_breakout"),
        ("2", "bollinger_reversion"),
        ("3", "multi_strategy_regime"),
    ):
        if number not in selected:
            continue
        result = run(configs[name], source_hash=source_identity())
        assert result["run"]["metrics"]["filled_plans"] > 0
        assert result["run"]["metrics"]["closed_trades"] > 0
        path = save_run(result, output / "runs")
        results[number] = {"path": str(path), "metrics": result["run"]["metrics"]}
    if "4" in selected:
        results["4"] = shock_delays()
    if "5" in selected:
        results["5"] = position_demo(output)
    if "6" in selected or "7" in selected:
        from .ml import train

        for number, family in (("6", "logistic"), ("7", "transformer")):
            if number not in selected:
                continue
            config = PlatformConfig(bars=140)
            config = config.model_copy(update={"ml": config.ml.model_copy(update={"family": family})})
            results[number] = train(config, output / "models")
    if "8" in selected:
        results["8"] = compare(list(configs.values()), output / "comparison")
    if "9" in selected:
        c = configs["trend_breakout"]
        events = SyntheticProvider().events(c)
        pipeline, indices = build_pipeline(events, c)
        group = histories(events)[c.universe[0]]
        candidate = None
        for index, event in enumerate(group):
            candidate = evaluate(pipeline, event, index, c.strategies[0], c)
            if candidate:
                break
        assert candidate is not None
        event = group[index + 1]
        missing_quote = gate(candidate, replace(event, quote=None), c)
        missing_derivatives = gate(candidate, replace(event, derivatives=None), c)
        stale = gate(candidate, replace(event, decision_ts=event.decision_ts + 120000), c)
        bad_quote = replace(event.quote, bid=event.quote.bid + Decimal(".001"))
        bad_tick = gate(candidate, replace(event, quote=bad_quote), c)
        assert "EXECUTABLE_QUOTE_MISSING" in missing_quote.veto_reasons
        assert missing_derivatives.action != "ENTRY_ELIGIBLE"
        assert "SOURCE_STALE_OR_INADMISSIBLE" in stale.veto_reasons
        assert "QUOTE_TICK_INVALID" in bad_tick.veto_reasons
        from .strategies import resolve

        assert len(resolve([candidate, candidate], c)) == 1
        failure_store = AdvisoryStore(output / "failure_positions.sqlite")
        failure_event = market(100, 1)
        failure_position = failure_store.report(
            UserReportedFill(
                "failure-fill",
                "failure-position",
                "BTCUSDT",
                "LONG",
                Decimal("100"),
                Decimal("1"),
                failure_event.decision_ts - 1,
                failure_event.decision_ts,
            ),
            failure_event.spec,
            stop=Decimal("98"),
        )
        stop_gap = supervise(failure_position, market(90, 20))
        assert stop_gap.action == "EXIT" and stop_gap.execution_status == "EXECUTION_UNKNOWN"
        results["9"] = {
            "missing_quote": primitive(missing_quote),
            "missing_derivatives": primitive(missing_derivatives),
            "stale": primitive(stale),
            "invalid_tick": primitive(bad_tick),
            "notifications": notification_demo(output),
            "duplicate_candidate_count": 1,
            "stop_gap": primitive(stop_gap),
        }
    write_json(output / ("demonstrations_" + scenario + ".json"), results)
    return {
        "scenarios_completed": sorted(results),
        "exposure": "SYNTHETIC",
        "artifact": str(output / ("demonstrations_" + scenario + ".json")),
    }
