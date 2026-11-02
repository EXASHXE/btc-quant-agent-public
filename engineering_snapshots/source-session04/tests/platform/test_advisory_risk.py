from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from btc_quant_agent.platform.advisory import gate
from btc_quant_agent.platform.backtest import build_pipeline
from btc_quant_agent.platform.config import PlatformConfig, StrategyConfig, load_config
from btc_quant_agent.platform.core import Lifecycle, quantize
from btc_quant_agent.platform.data import SyntheticProvider, histories
from btc_quant_agent.platform.demos import shock_delays
from btc_quant_agent.platform.portfolio import Exposure, size
from btc_quant_agent.platform.strategies import REGISTRY, evaluate, resolve


def setup_candidate(config=None):
    c = config or PlatformConfig(bars=140, scenario="trend")
    events = SyntheticProvider().events(c)
    p, indices = build_pipeline(events, c)
    group = histories(events)[c.universe[0]]
    for i, e in enumerate(group):
        candidate = evaluate(p, e, i, c.strategies[0], c)
        if candidate:
            return c, p, group, i, candidate
    raise AssertionError("no candidate in deterministic trend fixture")


def test_missing_quote_retains_watch_and_blocks_action():
    c, p, group, i, candidate = setup_candidate()
    plan = gate(candidate, replace(group[i + 1], quote=None), c)
    assert candidate.state == Lifecycle.DISCOVERED
    assert "EXECUTABLE_QUOTE_MISSING" in plan.veto_reasons
    assert plan.risk is None and plan.action == "WAIT"
    assert plan.lifecycle_transitions == (Lifecycle.DISCOVERED, Lifecycle.WATCH, Lifecycle.ARMED)


def test_candle_availability_and_intrabar_invalidation_are_enforced():
    c, p, group, i, candidate = setup_candidate()
    e = group[i + 1]
    candle = replace(e.candle, available_at_ms=e.decision_ts + 1)
    assert (
        "CANDLE_AVAILABILITY_UNKNOWN_OR_FUTURE" in gate(candidate, replace(e, candle=candle), c).veto_reasons
    )
    swept = replace(e.candle, low=float(candidate.stop) - 1)
    result = gate(candidate, replace(e, candle=swept), c)
    assert "STRUCTURE_INVALIDATED" in result.veto_reasons and result.state == Lifecycle.CANCELLED


def test_missing_funding_and_bad_quote_tick_fail_closed():
    c, p, group, i, candidate = setup_candidate()
    event = group[i + 1]
    assert "FUNDING_UNKNOWN" in gate(candidate, replace(event, derivatives=None), c).veto_reasons
    q = replace(event.quote, bid=event.quote.bid + Decimal(".001"))
    assert "QUOTE_TICK_INVALID" in gate(candidate, replace(event, quote=q), c).veto_reasons
    assert gate(candidate, replace(event, decision_ts=candidate.expires_ts), c).state == Lifecycle.EXPIRED


def test_sizing_uses_stop_costs_steps_and_exposure():
    c, p, group, i, candidate = setup_candidate()
    entry = float(candidate.entry_high)
    plan, veto = size(candidate, group[i].spec, entry, c, [], funding_rate=0.0001, beta=1)
    assert not veto and plan.quantity % group[i].spec.quantity_step == 0
    assert plan.modeled_loss <= plan.budget + 1e-8
    exposure = [Exposure("OTHER", "LONG", c.risk.equity)]
    blocked, veto = size(candidate, group[i].spec, entry, c, exposure, funding_rate=0.0001, beta=1)
    assert blocked is None and "PORTFOLIO_CORRELATION_UNKNOWN" in veto
    assert "CAPITAL_OCCUPANCY" in veto
    with pytest.raises(ValueError):
        quantize(0.00000001, 0.01)
    assert quantize(".000012345", ".00000001") == Decimal(".00001234")


def test_liquidation_buffer_veto():
    c, p, group, i, candidate = setup_candidate()
    c = c.model_copy(update={"risk": c.risk.model_copy(update={"leverage": 5})})
    candidate = replace(candidate, stop=Decimal("50"))
    _, veto = size(candidate, group[i].spec, 100, c, [], funding_rate=0.0001, beta=1)
    assert "LIQUIDATION_BUFFER" in veto


def test_manual_delay_and_lost_opportunity():
    result = shock_delays()
    assert result[0]["plan"]["action"] == "ENTRY_ELIGIBLE"
    assert result[1]["plan"]["action"] == "CANCEL"
    assert result[2]["plan"]["state"] == "EXPIRED"


@pytest.mark.parametrize("id", [k for k, v in REGISTRY.items() if v.status != "RESEARCH_ONLY"])
def test_every_directional_strategy_has_a_causal_executable_evaluator(id):
    c = PlatformConfig(bars=100, strategies=[StrategyConfig(id=id)])
    events = SyntheticProvider().events(c)
    p, _ = build_pipeline(events, c)
    for symbol, group in histories(events).items():
        for i in (40, 60, 76, 82, 99):
            value = evaluate(p, group[i], i, c.strategies[0], c)
            if value:
                assert value.stop > 0 and value.entry_low < value.entry_high
                assert value.provenance.available_ts <= value.decision_ts
                if value.direction == "LONG":
                    assert value.stop < value.entry_high


def test_deterministic_conflict_and_vote_resolution():
    c, p, group, i, a = setup_candidate()
    b = replace(a, id="different", strategy_id="rsi_reversion", direction="SHORT")
    c = c.model_copy(
        update={
            "strategies": [
                StrategyConfig(id=a.strategy_id, priority=2),
                StrategyConfig(id=b.strategy_id, priority=1),
            ]
        }
    )
    assert resolve([b, a, a], c) == [replace(a, state=Lifecycle.WATCH)]
    c = c.model_copy(update={"entry": c.entry.model_copy(update={"aggregation": "vote"})})
    assert resolve([a, b], c) == []


def test_all_example_yaml_and_unknown_keys(tmp_path):
    root = Path(__file__).resolve().parents[2]
    for path in (root / "configs").glob("*.yaml"):
        if path.name not in ("comparison.yaml", "search_space.yaml"):
            assert load_config(path).hash
    bad = tmp_path / "bad.yaml"
    bad.write_text("strategies:\n  - id: imaginary\n")
    with pytest.raises(ValueError, match="unknown strategy"):
        load_config(bad)
    bad.write_text("execution:\n  allow_live: true\n")
    with pytest.raises(ValueError, match="Extra inputs"):
        load_config(bad)
