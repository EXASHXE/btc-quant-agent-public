from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from btc_quant_agent.config import ExecutionConfig
from btc_quant_agent.data.binance_market_archive import (
    OFFICIAL_SPECS,
    aggregate_flow,
    aggressor_side,
    normalize_timestamp,
    parse_agg_trades,
)
from btc_quant_agent.data.historical_provenance import (
    HistoricalDataRole,
    HistoricalDatasetProvenance,
)
from btc_quant_agent.data.vendor_contract import VendorDatasetContract
from btc_quant_agent.domain import Direction
from btc_quant_agent.execution.guard import ExecutionBlocked, ExecutionGuard
from btc_quant_agent.execution.models import ExecutionMode, ExecutionPlan
from btc_quant_agent.symbolic_alpha.dsl import Formula, FormulaToken, Operator, TokenKind
from btc_quant_agent.symbolic_alpha.evaluate import EvaluationFirewall
from btc_quant_agent.symbolic_alpha.proposal import (
    LocalTransformerProposalEngine,
    ProposalConstraints,
    RandomGrammarProposalEngine,
)
from btc_quant_agent.symbolic_alpha.sandbox import (
    ProvisionalSignal,
    SandboxDecision,
    assert_shadow_start_is_valid,
)
from btc_quant_agent.symbolic_alpha.vm import FormulaVM

ROOT = Path(__file__).parents[1]
PROTOCOL = ROOT / "configs/research/v0.3.18_historical_symbolic_protocol.json"


def feature(name: str) -> FormulaToken:
    return FormulaToken(TokenKind.FEATURE, name)


def operator(name: Operator, parameter: int | None = None) -> FormulaToken:
    return FormulaToken(TokenKind.OPERATOR, name.value, parameter)


def test_protocol_is_frozen_and_holdout_sealed() -> None:
    raw = json.loads(PROTOCOL.read_text())
    assert raw["frozen_before_results"] is True
    assert raw["scope"]["final_holdout_access"] is False
    assert raw["safety"]["final_holdout"] == "SEALED"
    assert raw["formula_search"]["valid_unique_formula_budget"] == 512
    assert raw["formula_search"]["pseudo_forward_outcomes_visible_to_search_or_selection"] is False


def test_archive_paths_and_timestamp_units() -> None:
    assert OFFICIAL_SPECS["spot_aggTrades"].monthly_url("2024-01").endswith(
        "/spot/monthly/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2024-01.zip"
    )
    assert OFFICIAL_SPECS["markPriceKlines_1m"].monthly_url("2024-01").endswith(
        "/futures/um/monthly/markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2024-01.zip"
    )
    assert normalize_timestamp(1_735_689_600_000) == (1_735_689_600_000, "milliseconds")
    assert normalize_timestamp(1_735_689_600_000_000) == (
        1_735_689_600_000,
        "microseconds",
    )


def test_aggtrade_aggressor_mapping_and_no_gap_fill() -> None:
    rows, audit = parse_agg_trades(
        [
            ["1", "100", "2", "10", "11", "1735689600000", "false"],
            ["3", "101", "1", "13", "13", "1735689601000000", "true"],
        ],
        market="spot",
    )
    assert aggressor_side(False) == "BUY"
    assert aggressor_side(True) == "SELL"
    assert [row["aggressor_side"] for row in rows] == ["BUY", "SELL"]
    assert [row["aggregate_trade_id"] for row in rows] == [1, 3]
    assert audit["synthetic_rows"] == 0
    assert audit["timestamp_units"] == {"milliseconds": 1, "microseconds": 1}
    flow = aggregate_flow(rows)
    assert len(flow) == 1
    assert flow[0]["buy_notional"] == 200
    assert flow[0]["sell_notional"] == 101


def test_historical_provenance_and_vendor_cannot_be_forward() -> None:
    provenance = HistoricalDatasetProvenance(
        provider="BINANCE",
        source_name="public-data aggTrades",
        symbol="BTCUSDT",
        coverage_start="2024-01-01",
        coverage_end="2024-02-01",
        resolution_or_event_type="aggregate trade",
        exchange_event_timestamp_field="T",
        source_timestamp_unit="milliseconds",
        local_or_vendor_receive_timestamp_field=None,
        retrieval_timestamp="2026-09-02T00:00:00Z",
        checksum_or_manifest="sha256:test",
        lookback_limit_if_rest=None,
        point_in_time_interpretation="official historical exchange event time",
        known_biases=("no receive timestamp",),
        formal_role=HistoricalDataRole.OFFICIAL_HISTORICAL_TIMESTAMPED,
    )
    assert provenance.as_dict()["formal_role"] == "OFFICIAL_HISTORICAL_TIMESTAMPED"
    with pytest.raises(ValueError, match="only the local"):
        replace(provenance, formal_role=HistoricalDataRole.TRUE_FORWARD_LOCAL_PIT)
    contract = VendorDatasetContract(
        provider="Tardis.dev",
        dataset="incremental_book_L2",
        venue_instrument="binance-futures BTCUSDT perpetual",
        coverage_dates="contract-dependent",
        granularity="event",
        exchange_timestamp_available=True,
        receive_timestamp_available=True,
        l2_sequence_reconstructable=True,
        oi_semantics=None,
        liquidation_semantics=None,
        access_requirement="paid",
        sample_available="exchange samples",
        license_constraints="no redistribution",
        formal_role=HistoricalDataRole.VENDOR_RECORDED_HISTORICAL_PIT_PROXY,
    )
    with pytest.raises(ValueError, match="cannot be labeled"):
        contract.validate_row(
            {
                "provider": "Tardis.dev",
                "dataset": "incremental_book_L2",
                "exchange_timestamp": 1,
                "receive_timestamp": 2,
                "formal_role": "TRUE_FORWARD_LOCAL_PIT",
            }
        )


def test_formula_hash_lookback_and_duplicate_determinism() -> None:
    formula = Formula((feature("x"), operator(Operator.ROLL_Z_N, 24), operator(Operator.DELAY_1)))
    clone = Formula(tuple(formula.tokens))
    assert formula.formula_hash == clone.formula_hash
    assert formula.max_lookback({"x": 4}) == 28
    assert formula.canonical_json() == clone.canonical_json()


def test_vm_is_causal_and_has_no_wraparound_or_full_series_normalization() -> None:
    formula = Formula((feature("x"), operator(Operator.ROLL_Z_N, 3)))
    before = FormulaVM().execute(formula, {"x": [1.0, 2.0, 4.0, 8.0, 16.0]})
    after = FormulaVM().execute(formula, {"x": [1.0, 2.0, 4.0, 800.0, 1600.0]})
    assert before.failure is None and after.failure is None
    assert before.values is not None and after.values is not None
    assert before.values[:3] == after.values[:3]
    assert before.values[:2] == [None, None]
    delayed = FormulaVM().execute(
        Formula((feature("x"), operator(Operator.DELAY_1))), {"x": [1.0, 2.0, 3.0]}
    )
    assert delayed.values == [None, 1.0, 2.0]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (Operator.ROLL_SUM_N, [None, None, 6.0, 9.0]),
        (Operator.ROLL_MEAN_N, [None, None, 2.0, 3.0]),
        (Operator.ROLL_STD_N, [None, None, pytest.approx(0.81649658), pytest.approx(0.81649658)]),
        (Operator.DECAY_N, [None, None, pytest.approx(14 / 6), pytest.approx(20 / 6)]),
    ],
)
def test_rolling_operators_respect_startup_lookback(name: Operator, expected: list[object]) -> None:
    result = FormulaVM().execute(
        Formula((feature("x"), operator(name, 3))), {"x": [1.0, 2.0, 3.0, 4.0]}
    )
    assert result.failure is None
    assert result.values == expected


def test_vm_structured_errors_and_divide_by_zero() -> None:
    missing = FormulaVM().execute(Formula((feature("missing"),)), {"x": [1.0]})
    assert missing.failure is not None
    assert missing.failure.code == "FEATURE_UNAVAILABLE"
    divided = FormulaVM().execute(
        Formula((feature("x"), feature("z"), operator(Operator.DIV))),
        {"x": [1.0, None], "z": [0.0, 1.0]},
    )
    assert divided.failure is None
    assert divided.values == [None, None]


def test_random_budget_seed_duplicate_accounting_and_transformer_contract() -> None:
    constraints = ProposalConstraints(
        maximum_tokens=13,
        maximum_lookback=96,
        windows=(4, 8),
        operators=(Operator.ADD, Operator.SUB, Operator.ROLL_MEAN_N),
    )
    engine = RandomGrammarProposalEngine()
    first, audit = engine.propose(40, {"x": 1, "y": 2}, 3182026, constraints)
    second, _ = engine.propose(40, {"x": 1, "y": 2}, 3182026, constraints)
    assert [item.formula_hash for item in first] == [item.formula_hash for item in second]
    assert len({item.formula_hash for item in first}) == 40
    assert audit["valid_unique_formulas"] == 40
    transformer = LocalTransformerProposalEngine()
    assert transformer.external_api is False
    assert transformer.discovery_reward_only is True
    with pytest.raises(RuntimeError, match="not preregistered"):
        transformer.propose(1, {"x": 1}, 1, constraints)


def test_pseudo_forward_requires_frozen_top_k() -> None:
    formula = Formula((feature("x"),))
    firewall = EvaluationFirewall()
    with pytest.raises(PermissionError, match="top-K freeze"):
        firewall.authorize_pseudo_forward(formula)
    firewall.freeze_top_k([formula])
    firewall.authorize_pseudo_forward(formula)
    assert firewall.pseudo_forward_touches == 1


def test_provisional_signal_and_execution_are_blocked() -> None:
    signal = ProvisionalSignal(
        signal_id="p1",
        decision_timestamp_ms=1,
        decision=SandboxDecision.WAIT,
        formula_hash="abc",
        source="HISTORICAL_PROXY",
        entry_price=None,
        stop_price=None,
        take_profit_price=None,
        size=0,
    )
    assert signal.runtime_actionable is False
    config = ExecutionConfig(mode="paper")
    plan = ExecutionPlan(
        plan_id="p1",
        signal_id="s1",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        mode=ExecutionMode.PAPER,
        order_type="MARKET",
        quantity=1,
        entry_price=100,
        stop_price=90,
        take_profit_price=120,
        notional_usdt=100,
        leverage=1,
        validation_status="PROVISIONAL_SANDBOX_ONLY",
        created_at_ms=1,
        expires_at_ms=10,
        signal_expires_at_ms=10,
        rounded_rr_net=2,
        estimated_max_loss_usdt=10,
        plan_hash="",
    )
    plan = replace(plan, plan_hash=plan.calculated_hash())
    with pytest.raises(ExecutionBlocked, match="provisional"):
        ExecutionGuard(config).validate_entry(plan, plan.plan_hash, 2)
    with pytest.raises(ValueError, match="future-fixed"):
        assert_shadow_start_is_valid(100, 100)

