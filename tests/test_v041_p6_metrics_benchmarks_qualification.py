from __future__ import annotations

import json
import math
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any

import pytest

from btc_quant_agent.domain import Candle
from btc_quant_agent.economic import (
    P6_BENCHMARK_EVIDENCE_TYPE,
    P6_RESULT_EVIDENCE_TYPE,
    P6_RUN_EVIDENCE_TYPE,
    BenchmarkEngine,
    BenchmarkKind,
    BenchmarkMatchingRules,
    ComparisonContract,
    DataIntervalIdentity,
    EconomicHurdle,
    EconomicSimulationEngine,
    EligibleOpportunity,
    EntryRule,
    ExecutionModel,
    ExitRule,
    FeeModel,
    FundingModel,
    GateOperator,
    InformationSignal,
    MetricStatus,
    PositionSizing,
    ProfitFactorStatus,
    QualificationVerdict,
    ResultCompleteness,
    ReturnMetricsContract,
    RiskBudget,
    SimulationSummary,
    SlippageMode,
    TerminalPolicy,
    TradeAction,
    TradePolicy,
    build_formal_benchmark_suite,
    eligible_opportunity_set_sha256,
    evaluate_formal_economic_qualification,
    execute_bound_run,
    execution_model_identity,
    fee_model_identity,
    funding_model_identity,
    make_artifact_evidence,
    policy_identity,
    summarize_ledger,
)
from btc_quant_agent.economic.acceptance_verifier import (
    validate_persisted_qualification_semantics,
)
from btc_quant_agent.economic.portfolio import Portfolio
from btc_quant_agent.research_contract import (
    P6_PENDING,
    DecisionStatus,
    EvaluationMethod,
    EvidenceReference,
    ExperimentMetadata,
    FeatureDefinition,
    PredictionTarget,
    ResearchContractRegistry,
    VersionedIdentity,
)
from btc_quant_agent.research_contract.canonical import FrozenDict, canonical_json
from btc_quant_agent.research_contract.registry import (
    EvidenceValidationError,
    InvalidTransitionError,
    StaleRegistryError,
)

FIXED_TIME = "2026-09-09T04:00:00+00:00"
CADENCE_MS = 15 * 60 * 1000


def _candles(count: int = 8, *, drift: float = 1.0) -> tuple[Candle, ...]:
    start = 1_800_000_000_000
    result: list[Candle] = []
    for index in range(count):
        open_price = 100.0 + index * drift
        close_price = open_price + drift * 0.5
        result.append(
            Candle(
                symbol="BTCUSDT",
                interval="15m",
                open_time_ms=start + index * CADENCE_MS,
                close_time_ms=start + (index + 1) * CADENCE_MS,
                open=open_price,
                high=max(open_price, close_price) + 0.5,
                low=min(open_price, close_price) - 0.5,
                close=close_price,
                volume=10_000.0,
                quote_volume=1_000_000.0,
            )
        )
    return tuple(result)


def _zero_cost_engine() -> EconomicSimulationEngine:
    fee = FeeModel(
        maker_fee_rate=0.0,
        taker_fee_rate=0.0,
        slippage_mode=SlippageMode.ZERO,
        fixed_slippage_bps=0.0,
    )
    execution = ExecutionModel(
        fee_model=fee,
        decision_latency_ms=0,
        exchange_latency_ms=0,
        limit_fill_prob_on_touch=1.0,
    )
    policy = TradePolicy(
        policy_id="P6_FIXED_NOTIONAL",
        name="P6 deterministic one-bar policy",
        entry_rule=EntryRule(min_signal_strength=0.0),
        exit_rule=ExitRule(
            stop_loss_pct=None,
            take_profit_pct=None,
            trailing_stop_pct=None,
            decay_exit_on_signal_reversal=True,
            max_holding_ms=CADENCE_MS,
        ),
        position_sizing=PositionSizing(target_notional=1_000.0),
        risk_budget=RiskBudget(
            max_gross_exposure_usdt=2_000.0,
            max_open_positions=1,
            max_drawdown_stop_pct=0.9,
        ),
    )
    return EconomicSimulationEngine(
        policy=policy,
        fee_model=fee,
        execution_model=execution,
        funding_model=FundingModel(),
        initial_cash=10_000.0,
    )


def _dataset_evidence(tmp_path: Path, candles: tuple[Candle, ...]) -> EvidenceReference:
    path = tmp_path / "candles.json"
    path.write_text(
        canonical_json(
            [
                {
                    "symbol": item.symbol,
                    "interval": item.interval,
                    "open_time_ms": item.open_time_ms,
                    "close_time_ms": item.close_time_ms,
                    "open": item.open,
                    "high": item.high,
                    "low": item.low,
                    "close": item.close,
                    "volume": item.volume,
                    "quote_volume": item.quote_volume,
                }
                for item in candles
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return EvidenceReference.from_file(
        path,
        evidence_type="CANDLE_DATASET",
        logical_id="p6-candle-dataset",
        producing_revision_id="DATASET-PIPELINE@v1",
        producing_code_revision="dataset-code-v1",
        observed_at_utc=FIXED_TIME,
    )


def _opportunities(candles: tuple[Candle, ...]) -> tuple[EligibleOpportunity, ...]:
    return tuple(
        EligibleOpportunity(f"OPP-{index}", candle.open_time_ms)
        for index, candle in enumerate(candles[:-1])
    )


def _protocol(
    comparison: ComparisonContract,
    engine: EconomicSimulationEngine,
) -> ExperimentMetadata:
    return ExperimentMetadata(
        experiment_id="EXP-P6-FORMAL",
        name="Formal synthetic machinery check",
        input_contract=VersionedIdentity.from_payload(
            "P6_CAUSAL_INPUT", "v1", {"bars": "15m", "source": "local"}
        ),
        feature_definition=FeatureDefinition(
            feature_id="P6_SYNTHETIC_SIGNAL",
            name="Synthetic fixed signal",
            formula="fixture_only",
            input_requirements=("closed_btcusdt_15m",),
        ),
        prediction_target=PredictionTarget(
            target_id="P6_ONE_BAR_RETURN",
            name="One bar return",
            horizon_ms=CADENCE_MS,
            horizon_description="next executable one-bar return",
        ),
        evaluation_method=EvaluationMethod(
            method_name="P6_PREQUALIFIED_FIXTURE",
            statistical_test="FIXTURE_ONLY",
        ),
        economic_policy=policy_identity(engine.policy, "v1"),
        cost_model=fee_model_identity(engine.fee_model, "P6_ZERO_COST", "v1"),
        execution_model=execution_model_identity(
            engine.execution_model, "P6_ZERO_LATENCY_EXECUTION", "v1"
        ),
        benchmark=comparison.versioned_identity,
        product_scope=("BTCUSDT",),
        code_revision="p6-test-code-revision",
        terminal_policy=comparison.terminal_policy.value,
        created_at_utc=FIXED_TIME,
    )


def _comparison(
    dataset: EvidenceReference,
    candles: tuple[Candle, ...],
    engine: EconomicSimulationEngine,
    *,
    threshold: float = -1.0,
    required: tuple[BenchmarkKind, ...] = (
        BenchmarkKind.CASH,
        BenchmarkKind.RANDOM_MATCHED,
    ),
    descriptive: tuple[BenchmarkKind, ...] = (BenchmarkKind.PASSIVE_PERPETUAL,),
    matching: BenchmarkMatchingRules | None = None,
    seed: int = 1234,
    trials: int = 4,
    opportunities: tuple[EligibleOpportunity, ...] | None = None,
) -> ComparisonContract:
    metrics = ReturnMetricsContract(
        contract_name="P6_15M_CLOSE_RETURNS",
        sampling_rule="EQUITY_AT_EACH_CLOSED_15M_BAR",
        cadence_ms=CADENCE_MS,
        spacing_tolerance_ms=0,
    )
    return ComparisonContract(
        contract_name="P6_SYNTHETIC_COMPARISON",
        contract_version="v1",
        product_scope=("BTCUSDT",),
        benchmark_vehicle="BTCUSDT_LINEAR_PERPETUAL",
        initial_capital=engine.initial_cash,
        data_interval=DataIntervalIdentity(
            dataset_evidence_id=dataset.evidence_id,
            dataset_content_sha256=dataset.content_sha256,
            start_ms=candles[0].open_time_ms,
            end_ms=candles[-1].close_time_ms,
            observation_count=len(candles),
        ),
        candidate_policy=policy_identity(engine.policy, "v1"),
        cost_model=fee_model_identity(engine.fee_model, "P6_ZERO_COST", "v1"),
        execution_model=execution_model_identity(
            engine.execution_model, "P6_ZERO_LATENCY_EXECUTION", "v1"
        ),
        funding_model=funding_model_identity(engine.funding_model, "P6_FUNDING", "v1"),
        metrics_contract=metrics,
        terminal_policy=TerminalPolicy.REQUIRE_FLAT,
        required_benchmarks=required,
        descriptive_benchmarks=descriptive,
        randomization_unit="ELIGIBLE_CAUSAL_OPPORTUNITY_TIMESTAMP",
        eligible_opportunity_set_sha256=eligible_opportunity_set_sha256(
            opportunities or _opportunities(candles)
        ),
        random_seed=seed,
        random_trials=trials,
        matching_rules=matching
        or BenchmarkMatchingRules(
            match_entry_count=True,
            match_direction_counts=True,
            maximum_mean_holding_error_fraction=0.0,
            maximum_time_exposure_error_fraction=0.0,
            maximum_average_notional_error_fraction=1e-12,
        ),
        hurdles=(
            EconomicHurdle(
                gate_id="MIN_NET_RETURN",
                metric="NET_RETURN_PCT",
                operator=GateOperator.GREATER_THAN_OR_EQUAL,
                threshold=threshold,
            ),
        ),
        evidence_requirements=(
            "CANDLE_DATASET",
            P6_RUN_EVIDENCE_TYPE,
            P6_BENCHMARK_EVIDENCE_TYPE,
        ),
    )


def _formal_artifacts(
    tmp_path: Path,
    *,
    threshold: float = -1.0,
    matching: BenchmarkMatchingRules | None = None,
    incomparable_opportunities: bool = False,
) -> dict[str, Any]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    candles = _candles()
    engine = _zero_cost_engine()
    dataset = _dataset_evidence(tmp_path, candles)
    opportunities = (
        tuple(
            replace(item, metadata=FrozenDict({"spread_bps": -1.0}))
            for item in _opportunities(candles)
        )
        if incomparable_opportunities
        else _opportunities(candles)
    )
    comparison = _comparison(
        dataset,
        candles,
        engine,
        threshold=threshold,
        matching=matching,
        opportunities=opportunities,
    )
    protocol = _protocol(comparison, engine)
    signal = InformationSignal(
        signal_id="P6_CANDIDATE_ENTRY",
        experiment_id=protocol.experiment_revision_id,
        timestamp_ms=candles[0].open_time_ms,
        direction=1,
        strength=1.0,
    )
    run = execute_bound_run(
        protocol=protocol,
        comparison=comparison,
        dataset_evidence=dataset,
        engine=engine,
        candles=candles,
        signals=(signal,),
    )
    run_path = tmp_path / "candidate-run.json"
    run.write(run_path)
    run_evidence = make_artifact_evidence(
        run_path,
        evidence_type=P6_RUN_EVIDENCE_TYPE,
        logical_id="p6-candidate-run",
        protocol=protocol,
        observed_at_utc=FIXED_TIME,
    )
    suite = build_formal_benchmark_suite(
        protocol=protocol,
        comparison=comparison,
        dataset_evidence=dataset,
        candidate_run=run,
        engine=engine,
        candles=candles,
        eligible_opportunities=opportunities,
    )
    suite_path = tmp_path / "benchmark-suite.json"
    suite.write(suite_path)
    suite_evidence = make_artifact_evidence(
        suite_path,
        evidence_type=P6_BENCHMARK_EVIDENCE_TYPE,
        logical_id="p6-benchmark-suite",
        protocol=protocol,
        observed_at_utc=FIXED_TIME,
    )
    qualification = evaluate_formal_economic_qualification(
        protocol=protocol,
        comparison=comparison,
        candidate_run=run,
        benchmarks=suite,
        required_evidence_ids=(
            dataset.evidence_id,
            run_evidence.evidence_id,
            suite_evidence.evidence_id,
        ),
        generated_at_utc=FIXED_TIME,
    )
    result_path = tmp_path / "qualification.json"
    qualification.write(result_path)
    result_evidence = make_artifact_evidence(
        result_path,
        evidence_type=P6_RESULT_EVIDENCE_TYPE,
        logical_id="p6-qualification-result",
        protocol=protocol,
        observed_at_utc=FIXED_TIME,
    )
    return {
        "candles": candles,
        "engine": engine,
        "dataset": dataset,
        "comparison": comparison,
        "protocol": protocol,
        "run": run,
        "run_evidence": run_evidence,
        "suite": suite,
        "suite_evidence": suite_evidence,
        "qualification": qualification,
        "result_evidence": result_evidence,
    }


def _statistically_qualified_registry(
    tmp_path: Path, protocol: ExperimentMetadata
) -> tuple[ResearchContractRegistry, EvidenceReference]:
    registry = ResearchContractRegistry(tmp_path / "registry.json")
    registry.register_experiment(protocol, registered_at_utc=FIXED_TIME)
    path = tmp_path / "statistical-result.json"
    path.write_text('{"passed":true}\n', encoding="utf-8")
    statistical = EvidenceReference.from_file(
        path,
        evidence_type="STATISTICAL_RESULT",
        logical_id="p6-prior-statistical-result",
        producing_revision_id=protocol.experiment_revision_id,
        producing_code_revision=protocol.code_revision,
        observed_at_utc=FIXED_TIME,
    )
    registry.update_decision_status(
        protocol.experiment_revision_id,
        DecisionStatus.STATISTICALLY_QUALIFIED,
        evidence_references=(statistical,),
        reason="predeclared statistical fixture passed",
        actor="pytest",
        source="P6_TEST_SETUP",
        decided_at_utc=FIXED_TIME,
        statistical_result_id=statistical.evidence_id,
    )
    return registry, statistical


def test_formal_pipeline_is_replayable_and_can_qualify(tmp_path: Path) -> None:
    artifacts = _formal_artifacts(tmp_path)
    qualification = artifacts["qualification"]
    suite = artifacts["suite"]
    assert qualification.verdict is QualificationVerdict.QUALIFIED
    assert suite.random is not None
    assert len(suite.random.trials) == artifacts["comparison"].random_trials
    assert suite.random.comparable
    assert qualification.result_hash == replace(
        qualification, generated_at_utc="2030-01-01T00:00:00+00:00"
    ).result_hash

    protocol = artifacts["protocol"]
    registry, _ = _statistically_qualified_registry(tmp_path, protocol)
    event = registry.record_economic_qualification(
        qualification.decision_attestation(artifacts["result_evidence"]),
        evidence_references=(
            artifacts["dataset"],
            artifacts["run_evidence"],
            artifacts["suite_evidence"],
            artifacts["result_evidence"],
        ),
        reason="all preregistered synthetic machinery gates passed",
        actor="pytest",
        decided_at_utc=FIXED_TIME,
    )
    assert event is not None
    assert event.new_status is DecisionStatus.ECONOMICALLY_QUALIFIED
    assert registry.get_status(protocol.experiment_revision_id) is (
        DecisionStatus.ECONOMICALLY_QUALIFIED
    )
    assert ResearchContractRegistry(registry.storage_path).get_status(
        protocol.experiment_revision_id
    ) is DecisionStatus.ECONOMICALLY_QUALIFIED


def test_accounting_identity_partial_long_and_net_loser_classification() -> None:
    portfolio = Portfolio(1_000.0)
    portfolio.apply_trade(100, TradeAction.OPEN_LONG, "BTCUSDT", 100.0, 2.0, 2.0)
    portfolio.apply_funding(150, "BTCUSDT", -1.0, 105.0)
    portfolio.apply_trade(200, TradeAction.CLOSE_LONG, "BTCUSDT", 110.0, 1.0, 1.0)
    portfolio.apply_trade(300, TradeAction.CLOSE_LONG, "BTCUSDT", 90.0, 1.0, 1.0)
    summary = summarize_ledger(
        initial_cash=1_000.0,
        events=portfolio.trade_history,
        equity_curve=((300, portfolio.cash),),
        final_asset="BTCUSDT",
        final_mark_price=90.0,
        interval_start_ms=50,
        interval_end_ms=300,
        notional_curve=((300, 0.0),),
        terminal_policy=TerminalPolicy.REQUIRE_FLAT,
    )
    summary.validate_accounting()
    assert summary.realized_gross_pnl_usdt == pytest.approx(0.0)
    assert summary.final_equity - summary.initial_cash == pytest.approx(-5.0)
    assert [item.net_pnl_usdt for item in summary.round_trips] == pytest.approx(
        [7.5, -12.5]
    )
    assert (summary.winning_trades, summary.losing_trades) == (1, 1)
    assert summary.completed_round_trips == 2


def test_gross_positive_but_net_negative_is_a_losing_round_trip() -> None:
    portfolio = Portfolio(1_000.0)
    portfolio.apply_trade(100, TradeAction.OPEN_LONG, "BTCUSDT", 100.0, 1.0, 1.0)
    portfolio.apply_trade(200, TradeAction.CLOSE_LONG, "BTCUSDT", 101.0, 1.0, 1.0)
    summary = summarize_ledger(
        initial_cash=1_000.0,
        events=portfolio.trade_history,
        equity_curve=((200, portfolio.cash),),
        final_asset="BTCUSDT",
        final_mark_price=101.0,
        interval_start_ms=50,
        interval_end_ms=200,
        notional_curve=((200, 0.0),),
        terminal_policy=TerminalPolicy.REQUIRE_FLAT,
    )
    assert summary.round_trips[0].gross_realized_pnl_usdt == pytest.approx(1.0)
    assert summary.round_trips[0].net_pnl_usdt == pytest.approx(-1.0)
    assert summary.winning_trades == 0
    assert summary.losing_trades == 1


@pytest.mark.parametrize(
    ("action_open", "action_close", "entry", "exit_price", "expected"),
    [
        (TradeAction.OPEN_LONG, TradeAction.CLOSE_LONG, 100.0, 110.0, 10.0),
        (TradeAction.OPEN_LONG, TradeAction.CLOSE_LONG, 100.0, 90.0, -10.0),
        (TradeAction.OPEN_SHORT, TradeAction.CLOSE_SHORT, 100.0, 90.0, 10.0),
        (TradeAction.OPEN_SHORT, TradeAction.CLOSE_SHORT, 100.0, 110.0, -10.0),
    ],
)
def test_long_short_profit_and_loss_reconcile(
    action_open: TradeAction,
    action_close: TradeAction,
    entry: float,
    exit_price: float,
    expected: float,
) -> None:
    portfolio = Portfolio(1_000.0)
    portfolio.apply_trade(100, action_open, "BTCUSDT", entry, 1.0, 0.0)
    portfolio.apply_trade(200, action_close, "BTCUSDT", exit_price, 1.0, 0.0)
    summary = summarize_ledger(
        initial_cash=1_000.0,
        events=portfolio.trade_history,
        equity_curve=((200, portfolio.cash),),
        final_asset="BTCUSDT",
        final_mark_price=exit_price,
        interval_start_ms=50,
        interval_end_ms=200,
        notional_curve=((200, 0.0),),
        terminal_policy=TerminalPolicy.REQUIRE_FLAT,
    )
    assert summary.final_equity - summary.initial_cash == pytest.approx(expected)
    assert summary.round_trips[0].net_pnl_usdt == pytest.approx(expected)


def test_terminal_open_and_flat_policies_are_explicit_and_reconcile() -> None:
    portfolio = Portfolio(1_000.0)
    portfolio.apply_trade(100, TradeAction.OPEN_LONG, "BTCUSDT", 100.0, 1.0, 1.0)
    mark_equity = portfolio.total_equity({"BTCUSDT": 110.0})
    marked = summarize_ledger(
        initial_cash=1_000.0,
        events=portfolio.trade_history,
        equity_curve=((200, mark_equity),),
        final_asset="BTCUSDT",
        final_mark_price=110.0,
        interval_start_ms=50,
        interval_end_ms=200,
        notional_curve=((200, 110.0),),
        terminal_policy=TerminalPolicy.MARK_TO_MARKET_OPEN,
    )
    assert marked.completeness is ResultCompleteness.COMPLETE
    assert marked.terminal_unrealized_pnl_usdt == pytest.approx(10.0)
    assert marked.final_equity == marked.equity_curve[-1][1]
    marked.validate_accounting()

    unsupported = summarize_ledger(
        initial_cash=1_000.0,
        events=portfolio.trade_history,
        equity_curve=((200, mark_equity),),
        final_asset="BTCUSDT",
        final_mark_price=110.0,
        interval_start_ms=50,
        interval_end_ms=200,
        notional_curve=((200, 110.0),),
        terminal_policy=TerminalPolicy.REQUIRE_FLAT,
    )
    assert unsupported.completeness is ResultCompleteness.UNSUPPORTED_TERMINAL_STATE
    assert not unsupported.formal_complete


def test_sharpe_requires_verified_cadence_and_json_safe_undefined_metrics() -> None:
    contract = ReturnMetricsContract(
        "P6_15M", "CLOSED_BAR_EQUITY", CADENCE_MS, spacing_tolerance_ms=0
    )
    regular = (
        (1_000_000, 100.0),
        (1_000_000 + CADENCE_MS, 101.0),
        (1_000_000 + 2 * CADENCE_MS, 100.5),
    )
    sharpe, status = contract.annualized_sharpe(regular)
    assert status is MetricStatus.AVAILABLE
    assert sharpe is not None and math.isfinite(sharpe)

    irregular = (regular[0], (regular[1][0] + 1, regular[1][1]), regular[2])
    assert contract.annualized_sharpe(irregular) == (None, MetricStatus.INVALID_CADENCE)
    flat = tuple((1_000_000 + index * CADENCE_MS, 100.0) for index in range(3))
    assert contract.annualized_sharpe(flat) == (None, MetricStatus.ZERO_VARIANCE)

    summary = summarize_ledger(
        initial_cash=100.0,
        events=(),
        equity_curve=flat,
        final_asset="BTCUSDT",
        final_mark_price=100.0,
        interval_start_ms=100_000,
        interval_end_ms=flat[-1][0],
        notional_curve=tuple((timestamp, 0.0) for timestamp, _ in flat),
        terminal_policy=TerminalPolicy.REQUIRE_FLAT,
        metrics_contract=contract,
    )
    assert summary.profit_factor is None
    assert summary.profit_factor_status is ProfitFactorStatus.UNDEFINED
    assert "NaN" not in canonical_json(summary.to_dict())
    assert "Infinity" not in canonical_json(summary.to_dict())


def test_slippage_is_in_fill_prices_and_never_deducted_twice() -> None:
    fee = FeeModel(
        maker_fee_rate=0.0,
        taker_fee_rate=0.0,
        slippage_mode=SlippageMode.FIXED_BPS,
        fixed_slippage_bps=100.0,
    )
    engine = EconomicSimulationEngine(
        policy=replace(_zero_cost_engine().policy),
        fee_model=fee,
        execution_model=ExecutionModel(
            fee_model=fee, decision_latency_ms=0, exchange_latency_ms=0
        ),
        initial_cash=10_000.0,
    )
    candles = _candles(count=3, drift=10.0)
    signal = InformationSignal(
        "SLIP", "DIAGNOSTIC", candles[0].open_time_ms, direction=1
    )
    summary = engine.simulate(candles, (signal,))
    assert summary.slippage_attribution_usdt is not None
    assert summary.slippage_attribution_usdt > 0.0
    assert summary.net_pnl_usdt == pytest.approx(
        summary.realized_gross_pnl_usdt
        + summary.terminal_unrealized_pnl_usdt
        - summary.total_fees_usdt
        + summary.total_funding_usdt
    )


def test_passive_perpetual_uses_engine_costs_and_terminal_curve_reconciles(
    tmp_path: Path,
) -> None:
    artifacts = _formal_artifacts(tmp_path)
    passive = artifacts["suite"].passive
    assert passive is not None and passive.comparable
    accounting = dict(passive.accounting)
    assert accounting["terminal_position_quantity"] == pytest.approx(0.0)
    assert accounting["final_equity"] == accounting["equity_curve"][-1][1]
    assert passive.vehicle == "BTCUSDT_LINEAR_PERPETUAL"


def test_random_trials_are_preserved_deterministic_and_not_a_mean_curve(
    tmp_path: Path,
) -> None:
    first = _formal_artifacts(tmp_path)
    opportunities = _opportunities(first["candles"])
    second_suite = build_formal_benchmark_suite(
        protocol=first["protocol"],
        comparison=first["comparison"],
        dataset_evidence=first["dataset"],
        candidate_run=first["run"],
        engine=first["engine"],
        candles=first["candles"],
        eligible_opportunities=opportunities,
    )
    first_random = first["suite"].random
    second_random = second_suite.random
    assert first_random is not None and second_random is not None
    assert len(first_random.trials) == 4
    assert first_random.to_dict() == second_random.to_dict()
    assert first["suite"].suite_id == second_suite.suite_id
    assert all(trial.run_result_id is not None for trial in first_random.trials)
    assert all("equity_curve" in trial.accounting for trial in first_random.trials)


def test_contract_changes_change_comparison_and_protocol_revision(tmp_path: Path) -> None:
    candles = _candles()
    engine = _zero_cost_engine()
    dataset = _dataset_evidence(tmp_path, candles)
    baseline = _comparison(dataset, candles, engine)
    variants = (
        replace(baseline, random_seed=baseline.random_seed + 1),
        replace(baseline, random_trials=baseline.random_trials + 1),
        replace(
            baseline,
            hurdles=(replace(baseline.hurdles[0], threshold=-0.5),),
        ),
        replace(
            baseline,
            required_benchmarks=(BenchmarkKind.CASH,),
            descriptive_benchmarks=(
                BenchmarkKind.PASSIVE_PERPETUAL,
                BenchmarkKind.RANDOM_MATCHED,
            ),
        ),
        replace(baseline, terminal_policy=TerminalPolicy.MARK_TO_MARKET_OPEN),
    )
    for variant in variants:
        assert variant.contract_hash != baseline.contract_hash
        assert _protocol(variant, engine).experiment_revision_id != _protocol(
            baseline, engine
        ).experiment_revision_id
    with pytest.raises(FrozenInstanceError):
        baseline.random_seed = 9  # type: ignore[misc]


def test_p6_pending_and_manual_summary_cannot_formally_qualify(tmp_path: Path) -> None:
    artifacts = _formal_artifacts(tmp_path)
    protocol = artifacts["protocol"]
    pending = replace(protocol, benchmark=P6_PENDING)
    with pytest.raises(ValueError, match="P6_PENDING"):
        evaluate_formal_economic_qualification(
            protocol=pending,
            comparison=artifacts["comparison"],
            candidate_run=artifacts["run"],
            benchmarks=artifacts["suite"],
            required_evidence_ids=("manual",),
        )

    manual = SimulationSummary(
        initial_cash=10_000.0,
        final_equity=20_000.0,
        gross_pnl_usdt=10_000.0,
        total_fees_usdt=0.0,
        total_funding_usdt=0.0,
        net_pnl_usdt=10_000.0,
        net_return_pct=1.0,
        max_drawdown_usdt=0.0,
        max_drawdown_pct=0.0,
        total_trades=1,
        winning_trades=1,
        losing_trades=0,
        win_rate=1.0,
        profit_factor=None,
        sharpe_ratio=None,
    )
    diagnostic = BenchmarkEngine().evaluate_economic_qualification(
        manual, artifacts["candles"], artifacts["engine"].policy
    )
    assert diagnostic["diagnostic_only"] is True
    assert diagnostic["qualification_evaluated"] is False
    registry, _ = _statistically_qualified_registry(tmp_path, protocol)
    with pytest.raises(InvalidTransitionError, match="P6 evidence contract"):
        registry.update_decision_status(
            protocol.experiment_revision_id,
            DecisionStatus.ECONOMICALLY_QUALIFIED,
            evidence_references=(artifacts["result_evidence"],),
            reason="manual bypass",
            actor="pytest",
            source="manual",
        )


def test_failed_hurdle_records_rejected(tmp_path: Path) -> None:
    artifacts = _formal_artifacts(tmp_path, threshold=1.0)
    qualification = artifacts["qualification"]
    assert qualification.verdict is QualificationVerdict.REJECTED
    registry, _ = _statistically_qualified_registry(tmp_path, artifacts["protocol"])
    event = registry.record_economic_qualification(
        qualification.decision_attestation(artifacts["result_evidence"]),
        evidence_references=(
            artifacts["dataset"],
            artifacts["run_evidence"],
            artifacts["suite_evidence"],
            artifacts["result_evidence"],
        ),
        reason="preregistered hurdle failed",
        actor="pytest",
        decided_at_utc=FIXED_TIME,
    )
    assert event is not None and event.new_status is DecisionStatus.REJECTED


def test_failed_matching_is_not_testable_and_does_not_change_status(
    tmp_path: Path,
) -> None:
    matching = BenchmarkMatchingRules(
        match_entry_count=True,
        match_direction_counts=True,
        maximum_mean_holding_error_fraction=0.0,
        maximum_time_exposure_error_fraction=0.0,
        maximum_average_notional_error_fraction=0.0,
    )
    artifacts = _formal_artifacts(
        tmp_path,
        matching=matching,
        incomparable_opportunities=True,
    )
    random_suite = artifacts["suite"].random
    assert random_suite is not None
    assert not random_suite.comparable
    assert any(
        trial.matching_diagnostics["entry_count_match"] is False
        for trial in random_suite.trials
    )
    qualification = artifacts["qualification"]
    assert qualification.verdict is QualificationVerdict.NOT_TESTABLE


def test_not_testable_artifact_registers_evidence_without_lifecycle_event(
    tmp_path: Path,
) -> None:
    artifacts = _formal_artifacts(tmp_path, incomparable_opportunities=True)
    qualification = artifacts["qualification"]
    assert qualification.verdict is QualificationVerdict.NOT_TESTABLE
    result_evidence = artifacts["result_evidence"]
    registry, _ = _statistically_qualified_registry(tmp_path, artifacts["protocol"])
    event_count = len(registry.decision_events())
    result = registry.record_economic_qualification(
        qualification.decision_attestation(result_evidence),
        evidence_references=(
            artifacts["dataset"],
            artifacts["run_evidence"],
            artifacts["suite_evidence"],
            result_evidence,
        ),
        reason="evidence was not testable",
        actor="pytest",
    )
    assert result is None
    assert registry.get_status(artifacts["protocol"].experiment_revision_id) is (
        DecisionStatus.STATISTICALLY_QUALIFIED
    )
    assert len(registry.decision_events()) == event_count
    assert registry.get_evidence(result_evidence.evidence_id) == result_evidence


def test_tampered_result_run_and_dataset_are_atomic_failures(tmp_path: Path) -> None:
    artifacts = _formal_artifacts(tmp_path)
    protocol = artifacts["protocol"]

    for key in ("result_evidence", "run_evidence", "dataset"):
        case_path = tmp_path / key
        case_path.mkdir()
        case = _formal_artifacts(case_path)
        registry, _ = _statistically_qualified_registry(case_path, case["protocol"])
        reference = case[key]
        local_path = reference.local_path()
        assert local_path is not None
        local_path.write_text("tampered\n", encoding="utf-8")
        before = registry.storage_path.read_bytes() if registry.storage_path else b""
        generation = registry.generation
        with pytest.raises(EvidenceValidationError, match="hash mismatch"):
            registry.record_economic_qualification(
                case["qualification"].decision_attestation(case["result_evidence"]),
                evidence_references=(
                    case["dataset"],
                    case["run_evidence"],
                    case["suite_evidence"],
                    case["result_evidence"],
                ),
                reason="must fail atomically",
                actor="pytest",
            )
        assert registry.generation == generation
        assert registry.storage_path is not None
        assert registry.storage_path.read_bytes() == before
        assert registry.get_status(case["protocol"].experiment_revision_id) is (
            DecisionStatus.STATISTICALLY_QUALIFIED
        )
    assert protocol.experiment_revision_id == artifacts["protocol"].experiment_revision_id


def test_stale_registry_cannot_partially_commit_economic_decision(tmp_path: Path) -> None:
    artifacts = _formal_artifacts(tmp_path)
    registry, statistical = _statistically_qualified_registry(
        tmp_path, artifacts["protocol"]
    )
    stale = ResearchContractRegistry(registry.storage_path)
    extra_path = tmp_path / "extra.json"
    extra_path.write_text("{}\n", encoding="utf-8")
    extra = EvidenceReference.from_file(
        extra_path,
        evidence_type="DIAGNOSTIC",
        logical_id="stale-writer-advance",
        producing_revision_id=artifacts["protocol"].experiment_revision_id,
        producing_code_revision=artifacts["protocol"].code_revision,
        observed_at_utc=FIXED_TIME,
    )
    registry.register_evidence(extra)
    stale_generation = stale.generation
    with pytest.raises(StaleRegistryError):
        stale.record_economic_qualification(
            artifacts["qualification"].decision_attestation(
                artifacts["result_evidence"]
            ),
            evidence_references=(
                artifacts["dataset"],
                artifacts["run_evidence"],
                artifacts["suite_evidence"],
                artifacts["result_evidence"],
            ),
            reason="stale writer must fail",
            actor="pytest",
        )
    assert stale.generation == stale_generation
    assert stale.get_evidence(statistical.evidence_id) == statistical
    loaded = ResearchContractRegistry(registry.storage_path)
    assert loaded.get_status(artifacts["protocol"].experiment_revision_id) is (
        DecisionStatus.STATISTICALLY_QUALIFIED
    )


def test_semantically_identical_runs_and_results_have_identical_hashes(
    tmp_path: Path,
) -> None:
    artifacts = _formal_artifacts(tmp_path)
    protocol = artifacts["protocol"]
    signal = InformationSignal(
        "P6_CANDIDATE_ENTRY",
        protocol.experiment_revision_id,
        artifacts["candles"][0].open_time_ms,
        direction=1,
    )
    repeated = execute_bound_run(
        protocol=protocol,
        comparison=artifacts["comparison"],
        dataset_evidence=artifacts["dataset"],
        engine=artifacts["engine"],
        candles=artifacts["candles"],
        signals=(signal,),
    )
    assert repeated.result_id == artifacts["run"].result_id
    assert repeated.to_dict() == artifacts["run"].to_dict()
    repeated_result = evaluate_formal_economic_qualification(
        protocol=protocol,
        comparison=artifacts["comparison"],
        candidate_run=repeated,
        benchmarks=artifacts["suite"],
        required_evidence_ids=artifacts["qualification"].required_evidence_ids,
        generated_at_utc="2030-01-01T00:00:00+00:00",
    )
    assert repeated_result.result_hash == artifacts["qualification"].result_hash
    assert json.loads(canonical_json(repeated_result.semantic_payload()))



def test_acceptance_repair_rejects_runtime_dataset_substitution(tmp_path: Path) -> None:
    candles = _candles()
    engine = _zero_cost_engine()
    dataset = _dataset_evidence(tmp_path, candles)
    comparison = _comparison(dataset, candles, engine)
    protocol = _protocol(comparison, engine)
    forged = list(candles)
    forged[3] = replace(
        forged[3],
        close=forged[3].close + 0.25,
        high=forged[3].high + 0.25,
        volume=forged[3].volume + 1.0,
    )
    with pytest.raises(ValueError, match="runtime candle payload"):
        execute_bound_run(
            protocol=protocol,
            comparison=comparison,
            dataset_evidence=dataset,
            engine=engine,
            candles=tuple(forged),
            signals=(),
        )


def test_acceptance_repair_rejects_runtime_instrument_substitution(tmp_path: Path) -> None:
    candles = _candles()
    engine = _zero_cost_engine()
    dataset = _dataset_evidence(tmp_path, candles)
    comparison = _comparison(dataset, candles, engine)
    protocol = _protocol(comparison, engine)
    forged = tuple(replace(item, symbol="ETHUSDT") for item in candles)
    with pytest.raises(ValueError, match="instrument"):
        execute_bound_run(
            protocol=protocol,
            comparison=comparison,
            dataset_evidence=dataset,
            engine=engine,
            candles=forged,
            signals=(),
        )


def test_acceptance_repair_runtime_binding_is_deterministic(tmp_path: Path) -> None:
    artifacts = _formal_artifacts(tmp_path)
    first = artifacts["run"]
    second = execute_bound_run(
        protocol=artifacts["protocol"],
        comparison=artifacts["comparison"],
        dataset_evidence=artifacts["dataset"],
        engine=artifacts["engine"],
        candles=artifacts["candles"],
        signals=(
            InformationSignal(
                signal_id="P6_CANDIDATE_ENTRY",
                experiment_id=artifacts["protocol"].experiment_revision_id,
                timestamp_ms=artifacts["candles"][0].open_time_ms,
                direction=1,
                strength=1.0,
            ),
        ),
    )
    assert first.result_id == second.result_id
    assert first.accounting["formal_runtime_market_data_sha256"] == second.accounting[
        "formal_runtime_market_data_sha256"
    ]


def test_acceptance_repair_rejects_semantically_forged_run_gate_and_random(tmp_path: Path) -> None:
    artifacts = _formal_artifacts(tmp_path)
    semantic = json.loads(canonical_json(artifacts["qualification"].semantic_payload()))
    candidate = semantic["run_result"]["semantic_payload"]["accounting"]

    forged_run = json.loads(canonical_json(semantic))
    forged_run_candidate = forged_run["run_result"]["semantic_payload"]["accounting"]
    forged_run_candidate["turnover_usdt"] += 10_000.0
    with pytest.raises(ValueError, match="replay"):
        validate_persisted_qualification_semantics(forged_run, artifacts["dataset"])

    forged_gate = json.loads(canonical_json(semantic))
    forged_gate["gates"][0]["observed_value"] = candidate["net_return_pct"] + 1.0
    forged_gate["gates"][0]["passed"] = True
    forged_gate["verdict"] = "QUALIFIED"
    with pytest.raises(ValueError, match="qualification gates"):
        validate_persisted_qualification_semantics(forged_gate, artifacts["dataset"])

    forged_random = json.loads(canonical_json(semantic))
    random_record = forged_random["benchmark_suite"]["random"]
    assert random_record is not None
    random_record["trials"][0]["matching_diagnostics"]["trial_entry_count"] += 1
    random_record["trials"][0]["comparable"] = True
    random_record["comparable"] = True
    with pytest.raises(ValueError, match="matching diagnostics"):
        validate_persisted_qualification_semantics(forged_random, artifacts["dataset"])
