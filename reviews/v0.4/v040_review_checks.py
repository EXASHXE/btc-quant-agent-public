"""Synthetic review probes for implementation 0c75cf5; no market files or APIs.

Run: rtk env PYTHONPATH=src python reviews/v0.4/v040_review_checks.py
Assertions document observed defects, NOT desired regression expectations.
Registry writes are confined to an automatically cleaned temporary directory.
"""

import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from btc_quant_agent.domain import Candle
from btc_quant_agent.economic.benchmarks import BenchmarkEngine
from btc_quant_agent.economic.execution_model import ExecutionModel
from btc_quant_agent.economic.fee_model import FeeModel, SlippageMode
from btc_quant_agent.economic.funding import FundingModel, FundingSettlement
from btc_quant_agent.economic.policy import (
    EntryRule,
    ExitRule,
    MarketStateFilter,
    OrderType,
    PositionSizing,
    RiskBudget,
    SizingType,
    TradePolicy,
)
from btc_quant_agent.economic.portfolio import Portfolio
from btc_quant_agent.economic.signal import InformationSignal
from btc_quant_agent.economic.simulator import EconomicSimulationEngine
from btc_quant_agent.economic.trade_event import TradeAction as A
from btc_quant_agent.research_contract.models import (
    DecisionStatus as D,
)
from btc_quant_agent.research_contract.models import (
    EvaluationMethod,
    ExperimentMetadata,
    FeatureDefinition,
    PredictionTarget,
)
from btc_quant_agent.research_contract.registry import ResearchContractRegistry

ZERO = FeeModel(0, 0, SlippageMode.ZERO)
BASE = TradePolicy(
    "review", "Synthetic review", position_sizing=PositionSizing(target_notional=100)
)
rows = []


def record(name, expected, actual):
    rows.append({"case": name, "expected": expected, "actual": actual})


def bar(t=1000, o=100, h=None, l=None, c=100, volume=100, duration=1000):
    return Candle(
        "BTCUSDT",
        "1s",
        t,
        t + duration - 1,
        o,
        max(o, c) if h is None else h,
        min(o, c) if l is None else l,
        c,
        volume,
    )


def sig(t=1000, direction=1, **kw):
    return InformationSignal(f"s{t}_{direction}", "review", t, direction=direction, **kw)


def sim(bars, signals=(), policy=BASE, fees=ZERO, funds=(), initial=100000, execution=None):
    return EconomicSimulationEngine(
        policy, execution_model=execution, fee_model=fees, initial_cash=initial
    ).simulate(bars, signals, funds)


def state(p, mark):
    pos = p.positions.get("BTCUSDT")
    return {
        "cash": p.cash,
        "quantity": p.get_position_quantity(),
        "average_entry": pos.average_entry_price if pos else None,
        "realized": sum(e.realized_pnl_usdt for e in p.trade_history),
        "unrealized": pos.unrealized_pnl(mark) if pos else 0,
        "equity": p.total_equity({"BTCUSDT": mark}),
        "fees": sum(e.fee_usdt for e in p.trade_history),
        "funding": sum(e.funding_usdt for e in p.trade_history),
        "net": p.total_equity({"BTCUSDT": mark}) - p.initial_cash,
    }


def trade(p, act, price, qty=1, fee=0, t=1000):
    return p.apply_trade(t, act, "BTCUSDT", price, qty, fee)


# Ten required accounting paths: explicit opening and terminal states.
for name, opening, closing, end, pnl in [
    ("long_profit", A.OPEN_LONG, A.CLOSE_LONG, 110, 10),
    ("long_loss", A.OPEN_LONG, A.CLOSE_LONG, 90, -10),
    ("short_profit", A.OPEN_SHORT, A.CLOSE_SHORT, 90, 10),
    ("short_loss", A.OPEN_SHORT, A.CLOSE_SHORT, 110, -10),
]:
    p = Portfolio()
    trade(p, opening, 100)
    assert p.cash == 100000 and p.total_equity({"BTCUSDT": end}) == 100000 + pnl
    record(name + "_open", {"cash": 100000, "equity": 100000 + pnl}, state(p, end))
    trade(p, closing, end, t=2000)
    assert p.cash == 100000 + pnl and p.get_position_quantity() == 0
    record(name + "_close", {"realized": pnl, "net": pnl}, state(p, end))

p = Portfolio()
trade(p, A.OPEN_LONG, 100, fee=0.05)
trade(p, A.CLOSE_LONG, 110, fee=0.055, t=2000)
assert abs(p.cash - 100009.895) < 1e-8
record("round_trip_fees", {"cash": 100009.895, "fees": 0.105}, state(p, 110))
for name, direction, cf in [
    ("funding_payment", A.OPEN_LONG, -1),
    ("funding_receipt", A.OPEN_SHORT, 1),
]:
    p = Portfolio()
    trade(p, direction, 100)
    p.apply_funding(2000, "BTCUSDT", cf, 100)
    record(name, {"cash": 100000 + cf, "funding": cf, "net": cf}, state(p, 100))
    assert p.cash == 100000 + cf
p = Portfolio()
for t, act, price in [
    (1000, A.OPEN_LONG, 100),
    (2000, A.CLOSE_LONG, 110),
    (2000, A.OPEN_SHORT, 110),
    (3000, A.CLOSE_SHORT, 100),
]:
    trade(p, act, price, t=t)
assert p.cash == 100020
record("explicit_reversal", {"cash": 100020, "quantity": 0}, state(p, 100))
p = Portfolio()
for t, act, price in [
    (1000, A.OPEN_LONG, 100),
    (2000, A.CLOSE_LONG, 110),
    (3000, A.OPEN_LONG, 100),
    (4000, A.CLOSE_LONG, 90),
]:
    trade(p, act, price, t=t)
assert p.cash == 100000
record("sequential_positions", {"cash": 100000, "quantity": 0}, state(p, 90))
s = sim([bar(), bar(2000), bar(3000)], [sig(), sig(1000), sig(2000, -1)])
assert [e.action for e in s.trade_events] == [A.OPEN_LONG, A.CLOSE_LONG]
record(
    "overlap_and_reversal",
    "same-side ignored; opposite closes only",
    [e.to_dict() for e in s.trade_events],
)

# Capital identity and invalid transition defects.
s = sim([bar()], initial=1000)
assert s.final_equity == 100000 and s.net_pnl_usdt == 99000
record("cash_creation", {"final": 1000, "net": 0}, s.to_dict())
p = Portfolio()
trade(p, A.OPEN_SHORT, 100)
trade(p, A.OPEN_LONG, 110)
assert p.get_position_quantity() == 0 and p.cash == 100000
record("implicit_opposing_open", "reject, or realize -10 on closing short", state(p, 110))
p = Portfolio()
trade(p, A.OPEN_LONG, 100)
trade(p, A.CLOSE_SHORT, 90)
assert p.get_position_quantity() == 2 and p.cash == 100010
record("wrong_side_close", "reject without mutation", state(p, 90))
p = Portfolio()
try:
    trade(p, A.OPEN_LONG, 100, t=0)
except ValueError:
    pass
assert p.get_position_quantity() == 1 and not p.trade_history
record("non_atomic_trade", "rejected event leaves no position", state(p, 100))

# Causal execution, finite order life and intrabar ambiguity.
ex = ExecutionModel(ZERO)
r = ex.simulate_order(1000, 1, 1, OrderType.MARKET, [bar(c=120)])
assert r.fill_timestamp_ms == 1650 and r.fill_price == 120
record("future_close_at_earlier_time", "close price unavailable until 1999", r.__dict__)
r = ex.simulate_order(
    1700, 1, 1, OrderType.LIMIT, [bar(h=105, l=90, duration=2000)], limit_price=95
)
assert r.is_filled and r.fill_timestamp_ms == 2350
record(
    "limit_extreme_may_precede_arrival", "OHLC cannot establish post-2350 trade-through", r.__dict__
)
r = ex.simulate_order(
    1000, 1, 1, OrderType.LIMIT, [bar(l=90)], limit_price=95, time_in_force_ms=100
)
assert r.is_filled and r.fill_timestamp_ms > r.order_timestamp_ms + 100
record("fill_after_expiry", "no fill after 1600", r.__dict__)
r = ex.simulate_order(1000, 1, 1000, OrderType.LIMIT, [bar(l=90, volume=0)], limit_price=95)
assert r.is_filled and r.filled_quantity == 1000 and r.is_maker
record("zero_volume_full_fill", "not testable/reject without liquidity evidence", r.__dict__)
touch = [
    ex.simulate_order(1000, 1, 1, OrderType.LIMIT, [bar(l=95)], limit_price=95).is_filled,
    ExecutionModel(ZERO, limit_fill_prob_on_touch=0.99)
    .simulate_order(1000, 1, 1, OrderType.LIMIT, [bar(l=95)], limit_price=95)
    .is_filled,
]
record("touch_probability", "default and .99 are both deterministic no-fill", touch)
lp = replace(
    BASE,
    entry_rule=EntryRule(order_type=OrderType.LIMIT, time_in_force_ms=10000),
    exit_rule=ExitRule(take_profit_pct=0.01),
)
s = sim([bar(l=100), bar(2000, o=110, l=100, c=110), bar(3000, l=90)], [sig()], lp)
assert s.trade_events[0].timestamp_ms == 3000 and s.trade_events[1].timestamp_ms == 2999
record(
    "future_fill_applied_immediately",
    "cannot exit before entry",
    [e.to_dict() for e in s.trade_events],
)
collision = replace(BASE, exit_rule=ExitRule(stop_loss_pct=0.05, take_profit_pct=0.05))
s = sim([bar(), bar(2000, h=110, l=90), bar(3000, o=120, c=120)], [sig()], collision)
assert s.net_pnl_usdt == 20
record(
    "stop_target_collision",
    "ambiguous or conservative stop scenario; never certify +20",
    s.to_dict(),
)
s = sim(
    [bar(), bar(2000, o=80, c=80)],
    [sig()],
    replace(collision, entry_rule=EntryRule(order_type=OrderType.MARKET)),
)
assert s.trade_events[-1].price == 95 and s.net_pnl_usdt == -5
record(
    "gap_stop_fabricated_fill",
    "no liquidity at 95; observed bar entirely 80",
    [e.to_dict() for e in s.trade_events],
)
s = sim(
    [bar(), bar(2000, h=120, l=99, c=115)],
    [sig()],
    replace(BASE, exit_rule=ExitRule(trailing_stop_pct=0.1)),
)
assert s.net_pnl_usdt == 8
record(
    "trailing_extreme_order",
    "low-before-high path gives no trailing trigger; ambiguous",
    s.to_dict(),
)
s = sim([bar(), bar(2000, h=110, l=90), bar(3000, o=80, c=80)], [sig(direction=-1)], collision)
assert s.net_pnl_usdt == 20
record("short_stop_target_collision", "ambiguous or conservative stop scenario", s.to_dict())
s = sim(
    [bar(h=110, l=90)],
    [sig()],
    collision,
    execution=ExecutionModel(ZERO, decision_latency_ms=0, exchange_latency_ms=0),
)
assert s.total_trades == 0 and len(s.trade_events) == 1
record(
    "entry_bar_stop_target_skipped",
    "entry at open exposes position to both thresholds",
    s.to_dict(),
)

# Risk, state and sizing fields.
risk_policy = replace(
    BASE,
    risk_budget=RiskBudget(max_gross_exposure_usdt=1, max_open_positions=0),
    market_filter=MarketStateFilter(min_volume_usdt_15m=1e20, allowed_regimes=("FORBIDDEN",)),
)
s = sim([bar(volume=0)], [sig()], risk_policy)
assert len(s.trade_events) == 1 and s.trade_events[0].quantity == 1
record("ignored_risk_and_filters", "no position allowed", [e.to_dict() for e in s.trade_events])
vol = replace(
    BASE,
    position_sizing=PositionSizing(sizing_type=SizingType.VOLATILITY_SCALED, risk_fraction=0.01),
)
q = [vol.calculate_quantity(100, 1000, atr) for atr in (None, 0, -1)]
assert q == [10, 10, 10]
record("missing_atr_full_allocation", "missing/nonpositive ATR rejects volatility sizing", q)
record(
    "risk_fraction_without_stop",
    "explicit stop required for stop-risk sizing",
    replace(
        BASE, position_sizing=PositionSizing(sizing_type=SizingType.RISK_FRACTION)
    ).calculate_quantity(100, 1000),
)
dd_policy = replace(BASE, risk_budget=RiskBudget(max_drawdown_stop_pct=0.00001))
s = sim(
    [bar(), bar(2000, o=90, c=90), bar(3000, o=90, c=90)],
    [sig(), sig(2000, -1), sig(3000)],
    dd_policy,
)
assert len(s.trade_events) == 3 and s.max_drawdown_pct >= 0.0001
record(
    "drawdown_halt_ignored",
    "after 10 loss no new position above 1 dollar halt threshold",
    [e.to_dict() for e in s.trade_events],
)
offset_policy = replace(
    BASE, entry_rule=EntryRule(order_type=OrderType.LIMIT, limit_offset_bps=500)
)
s = sim([bar(l=99)], [sig()], offset_policy)
assert s.trade_events[0].price == 100
record(
    "limit_offset_ignored",
    "5% passive buy limit=95, low99 means no fill",
    [e.to_dict() for e in s.trade_events],
)
s = sim([bar()], [sig(asset="ETHUSDT")])
assert s.trade_events[0].metadata["asset"] == "BTCUSDT"
record("signal_asset_not_checked", "reject ETH signal on BTC input", s.trade_events[0].to_dict())

# Fee/slippage arithmetic, both sides, fixed-quantity comparisons.
fees = FeeModel(slippage_mode=SlippageMode.FIXED_BPS, fixed_slippage_bps=10)
buy = fees.effective_fill_price(100, 2, 1)
sell = fees.effective_fill_price(100, 2, -1)
assert abs(buy - 100.1) < 1e-10 and abs(sell - 99.9) < 1e-10
record(
    "fee_bps",
    {
        "buy": 100.1,
        "sell": 99.9,
        "entry_fee": 0.1001,
        "exit_fee": 0.0999,
        "round_trip_long_or_short_net": -0.6,
    },
    {
        "buy": buy,
        "sell": sell,
        "entry_fee": fees.calculate_fee(2 * buy),
        "exit_fee": fees.calculate_fee(2 * sell),
        "maker_fee_200": fees.calculate_fee(200, True),
        "round_trip_net": 2 * (sell - buy)
        - fees.calculate_fee(2 * buy)
        - fees.calculate_fee(2 * sell),
    },
)
impact = FeeModel(slippage_mode=SlippageMode.SPREAD_AND_IMPACT)
assert impact.calculate_slippage_bps(2, 100, 4, 100) == 4
record(
    "spread_impact",
    "half spread 2 + impact 2 = 4 bps",
    impact.calculate_slippage_bps(2, 100, 4, 100),
)
costs = []
for bps in (0, 1, 50):
    f = FeeModel(0, 0, SlippageMode.FIXED_BPS, bps)
    costs.append(2 * (f.effective_fill_price(100, 2, -1) - f.effective_fill_price(100, 2, 1)))
assert costs[0] == 0 and costs[2] < costs[1] < 0
record("fixed_path_cost_monotonicity", [0, -0.04, -2], costs)

# Funding arithmetic and simulator ordering versus explicit settlement times.
fm = FundingModel()
cf = [
    fm.calculate_cashflow(q, 100, r)
    for q, r in [(2, 0.01), (-2, 0.01), (2, -0.01), (-2, -0.01), (0, 0.01)]
]
assert cf == [-2, 2, 2, -2, 0]
record("funding_signs", [-2, 2, 2, -2, 0], cf)
f = FundingSettlement(1800, 0.01, 100)
s = sim([bar(), bar(2000)], [sig()], funds=[f])
assert s.total_funding_usdt == 0
record("entry_bar_funding_missed", "entry 1650 before settlement 1800 => -1", s.total_funding_usdt)
s = sim(
    [bar(), bar(2000), bar(3000)],
    [sig(), sig(2000, -1)],
    funds=[FundingSettlement(2500, 0.01, 100)],
)
assert s.total_funding_usdt == -1
record(
    "post_exit_funding_charged",
    "exit at reported 2000 precedes 2500 => 0",
    [e.to_dict() for e in s.trade_events],
)
settlements = [FundingSettlement(t, 0.01, 100) for t in (1000, 2000, 3000)]
boundary = [
    fm.accumulate_funding_during_window(1, a, b, settlements)[0]
    for a, b in [(1000, 3000), (1001, 2999), (2000, 2000), (1000, 2000), (2000, 3000)]
]
assert boundary == [-3, -1, 0, -2, -2]
record(
    "funding_boundaries",
    "inclusive nonzero windows; shared boundary double-counts when composed",
    boundary,
)
around_entry = [
    sim([bar(), bar(2000)], [sig()], funds=[FundingSettlement(t, 0.01, 100)]).total_funding_usdt
    for t in (1649, 1650, 1651)
]
assert around_entry == [0, 0, 0]
record(
    "funding_at_entry_boundary", "before=0; same-time needs sequence rule; after=-1", around_entry
)
around_exit = [
    sim(
        [bar(), bar(2000)], [sig(), sig(2000, -1)], funds=[FundingSettlement(t, 0.01, 100)]
    ).total_funding_usdt
    for t in (1999, 2000, 2001)
]
assert around_exit == [0, -1, -1]
record(
    "funding_at_exit_boundary",
    "before=-1; same-time needs sequence rule; after=0 at reported exit",
    around_exit,
)

# Summary and benchmark counterexamples.
f = FeeModel(0, 0.0005, SlippageMode.ZERO)
s = sim([bar(), bar(2000, o=100.075, c=100.075)], [sig(), sig(2000, -1)], fees=f)
assert s.net_pnl_usdt < 0 and s.win_rate == 1 and s.profit_factor == float("inf")
record("net_loser_reported_winner", "net=-.0250375, net win rate=0", s.to_dict())
s = sim([bar(), bar(2000, c=110)], [sig()])
assert s.gross_pnl_usdt == 0 and s.net_pnl_usdt == 10 and s.total_trades == 0
record("open_terminal_position", "report realized=0 and unrealized=10 separately", s.to_dict())
bench = BenchmarkEngine(f)
b = bench.simulate_passive_btc(1000, [bar(), bar(2000)])
assert b.equity_curve[-1][1] > b.final_equity
record(
    "passive_terminal_fee_curve",
    "terminal curve equals final equity; DD includes exit fee",
    b.__dict__,
)
rs = bench.simulate_random_entry(
    100000,
    [bar(t, c=p) for t, p in [(1000, 100), (2000, 102), (3000, 99), (4000, 105), (5000, 95)]],
    BASE,
    trade_frequency_pct=1,
    num_trials=5,
)
rs2 = bench.simulate_random_entry(
    100000,
    [bar(t, c=p) for t, p in [(1000, 100), (2000, 102), (3000, 99), (4000, 105), (5000, 95)]],
    BASE,
    trade_frequency_pct=1,
    num_trials=5,
)
assert rs == rs2
record(
    "random_mean_vs_last_curve",
    "mean terminal equity should not label last trial curve",
    rs.__dict__,
)
prices = [100, 110, 105, 120]
fast = sim([bar(1000 + i * 1000, o=p, c=p) for i, p in enumerate(prices)], [sig()])
slow = sim(
    [
        replace(bar(1000 + i * 900000, o=p, c=p, duration=900000), interval="15m")
        for i, p in enumerate(prices)
    ],
    [sig()],
)
assert fast.sharpe_ratio == slow.sharpe_ratio and fast.sharpe_ratio > 0
record(
    "sharpe_cadence_ignored",
    "same returns over 1s and 15m must not share annualized Sharpe",
    [fast.sharpe_ratio, slow.sharpe_ratio],
)
empty = sim([], initial=100000)
fabricated = replace(empty, final_equity=100001, net_pnl_usdt=1, net_return_pct=0.00001)
qual = BenchmarkEngine(ZERO).evaluate_economic_qualification(fabricated, [bar()], BASE)
assert qual["economic_qualification_passed"] is True and fabricated.total_trades == 0
record("unbound_qualification", "unverified/no-trade contradictory summary not qualified", qual)
beta = BenchmarkEngine(ZERO).evaluate_economic_qualification(fabricated, [bar(c=110)], BASE)
assert beta["economic_qualification_passed"] and not beta["comparisons"]["beats_passive_btc"]
record(
    "passive_not_required_for_qualification",
    "contract must state mandatory versus descriptive benchmarks",
    beta["comparisons"],
)


# Registry mutation, state bypass, validation and reproducible lost update.
def exp(eid="e"):
    return ExperimentMetadata(
        eid,
        "input",
        FeatureDefinition("f", "feature", "x", parameters={"k": 1}),
        PredictionTarget("t", "binary", 1000, "1s", continuous=False),
        EvaluationMethod("permutation", "exact"),
        "policy",
        "cost",
        "bench",
    )


reg = ResearchContractRegistry()
reg.register_experiment(exp())
reg.get_experiment("e").feature_definition.parameters["k"] = 999
reg.update_decision_status("e", D.ECONOMICALLY_QUALIFIED)
reg.update_decision_status("e", D.FROZEN_ARCHIVE)
reg.update_decision_status("e", D.PROPOSED)
assert reg.get_experiment("e").feature_definition.parameters["k"] == 999
record(
    "registry_mutation_and_thaw",
    "immutable protocol; evidence-bound legal transitions",
    reg.to_dict(),
)
reg.register_experiment(
    replace(exp(), evaluation_method=EvaluationMethod("posthoc", "new")), allow_update=True
)
record("registry_protocol_overwrite", "new version/hash/history required", reg.to_dict())
invalid = replace(
    exp("invalid"),
    prediction_target=PredictionTarget("", "", -1, ""),
    evaluation_method=EvaluationMethod("", "", significance_threshold=2),
)
reg.register_experiment(invalid)
record("invalid_nested_schema", "reject negative horizon and alpha=2", invalid.to_dict())
with TemporaryDirectory(prefix="v040-review-") as d:
    path = Path(d) / "registry.json"
    r1, r2 = ResearchContractRegistry(path), ResearchContractRegistry(path)
    r1.register_experiment(exp("a"))
    r2.register_experiment(exp("b"))
    assert list(ResearchContractRegistry(path).to_dict()) == ["b"]
    record("registry_lost_update", ["a", "b"], list(ResearchContractRegistry(path).to_dict()))
    with patch.object(Path, "write_text", side_effect=OSError("synthetic disk failure")):
        try:
            r2.register_experiment(exp("c"))
        except OSError:
            pass
    assert "c" in r2.to_dict() and "c" not in ResearchContractRegistry(path).to_dict()
    record(
        "failed_save_memory_disk_divergence",
        "failed commit must not look registered in memory",
        {"memory": list(r2.to_dict()), "disk": list(ResearchContractRegistry(path).to_dict())},
    )
    with patch.object(Path, "read_text", return_value="{"):
        try:
            ResearchContractRegistry(path)
        except json.JSONDecodeError:
            record(
                "corrupt_registry", "fail closed; recovery is not implemented", "JSONDecodeError"
            )

print(json.dumps({"probe_count": len(rows), "results": rows}, indent=2, default=str))
