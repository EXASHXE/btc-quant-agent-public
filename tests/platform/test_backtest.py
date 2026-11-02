import json
from dataclasses import replace
from decimal import Decimal

import pytest

from btc_quant_agent.platform import backtest
from btc_quant_agent.platform.advisory import gate
from btc_quant_agent.platform.config import PlatformConfig, StrategyConfig
from btc_quant_agent.platform.core import Lifecycle, StrategyCandidate
from btc_quant_agent.platform.demos import market
from btc_quant_agent.platform.execution_model import entry_fill
from btc_quant_agent.platform.reporting import compare, save_run


def simple_candidate(event):
    return StrategyCandidate(
        "synthetic-candidate",
        "BTCUSDT",
        "LONG",
        "trend_breakout",
        "1",
        event.decision_ts,
        Lifecycle.WATCH,
        1,
        json.dumps({"close": 100, "stop_reference": "observed prior low"}),
        ("next close up",),
        Decimal("99"),
        Decimal("102"),
        Decimal("102"),
        event.decision_ts + 600000,
        Decimal("98"),
        Decimal("98"),
        None,
        "OPEN_ENDED_TRAIL",
        "TREND_UP",
        event.provenance,
    )


def injected(monkeypatch, prices):
    e = market(100, 1, low=98)
    candidate = simple_candidate(e)
    monkeypatch.setattr(
        backtest,
        "scan",
        lambda pipeline, batch, indices, config: [candidate] if batch[0].decision_ts == e.decision_ts else [],
    )
    return [e] + prices


def test_gap_through_stop_and_cost_identity(monkeypatch):
    events = injected(monkeypatch, [market(100.2, 2), market(95, 3, low=94)])
    c = PlatformConfig(universe=["BTCUSDT"])
    r = backtest.run(c, events)
    trade = r["trades"][0]
    assert trade["reason"] == "STOP_GAP" and trade["exit"] < 98
    assert trade["modeled_net"] == pytest.approx(
        trade["gross"] - trade["fees"] - trade["spread"] - trade["slippage"] + trade["funding"]
    )
    assert r["run"]["metrics"]["total_marked_modeled_net_pnl"] == pytest.approx(trade["modeled_net"])


def test_touching_limit_is_not_a_fill():
    c = PlatformConfig(universe=["BTCUSDT"])
    c = c.model_copy(update={"execution": c.execution.model_copy(update={"entry_mode": "limit"})})
    e = market(100, 1, low=98)
    candidate = simple_candidate(e)
    later = market(100.2, 2, low=98.5)
    plan = gate(candidate, later, c)
    assert plan.action == "ENTRY_ELIGIBLE"
    assert entry_fill(plan, later, c) is None


def test_ambiguous_stop_and_target_uses_stop_first(monkeypatch):
    events = injected(monkeypatch, [market(100.2, 2), market(103, 3, low=97)])
    original = backtest.scan

    def scan(*args):
        return [replace(c, target=Decimal("102")) for c in original(*args)]

    monkeypatch.setattr(backtest, "scan", scan)
    result = backtest.run(PlatformConfig(universe=["BTCUSDT"]), events)
    assert result["trades"][0]["reason"] == "STOP"


def test_partial_fills_cutoff_and_stop_limit_unknown(monkeypatch):
    events = injected(monkeypatch, [market(100.2, 2), market(95, 3, low=94)])
    c = PlatformConfig(universe=["BTCUSDT"])
    c = c.model_copy(
        update={
            "execution": c.execution.model_copy(update={"fill_fraction": 0.3}),
            "exits": c.exits.model_copy(update={"stop_order": "limit"}),
        }
    )
    result = backtest.run(c, events)
    assert result["fills"] and result["open_positions"]
    assert any(d.get("reason") == "STOP_LIMIT_UNFILLED_EXECUTION_UNKNOWN" for d in result["decisions"])
    assert result["run"]["metrics"]["open_at_cutoff"] == 1


def test_full_replay_determinism_and_duplicate_event_rejection(config, events, tmp_path):
    first = backtest.run(config, events, source_hash="test-source")
    second = backtest.run(config, events, source_hash="test-source")
    assert first == second
    path = save_run(first, tmp_path)
    assert (path / "report.html").is_file() and (path / "trades.csv").is_file()
    with pytest.raises(ValueError, match="DUPLICATE"):
        backtest.run(config, [events[0], events[0]])


def test_comparison_rejects_inconsistent_costs(tmp_path):
    c = PlatformConfig(bars=80)
    other = c.model_copy(update={"execution": c.execution.model_copy(update={"slippage_bps": 10})})
    with pytest.raises(ValueError, match="cost assumptions"):
        compare([c, other], tmp_path)


def test_no_single_leg_funding_carry():
    with pytest.raises(ValueError, match="Research-only"):
        backtest.run(PlatformConfig(strategies=[StrategyConfig(id="funding_carry")]))
