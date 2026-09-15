from __future__ import annotations

import json
import math
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any

import pytest

from btc_quant_agent.domain import Candle
from btc_quant_agent.economic import (
    FORMAL_FUNDING_EVIDENCE_SCHEMA_VERSION,
    FORMAL_FUNDING_EVIDENCE_TYPE,
    P6_BENCHMARK_EVIDENCE_TYPE,
    P6_RESULT_EVIDENCE_TYPE,
    P6_RUN_EVIDENCE_TYPE,
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
    FundingIntervalIdentity,
    FundingModel,
    FundingSettlement,
    GateOperator,
    InformationSignal,
    MetricStatus,
    PositionSizing,
    ProfitFactorStatus,
    QualificationVerdict,
    ResultCompleteness,
    ReturnMetricsContract,
    RiskBudget,
    SignalProducerRegistry,
    SlippageMode,
    TerminalPolicy,
    TradeAction,
    TradePolicy,
    build_formal_benchmark_suite,
    build_formal_replay_input_bundle,
    eligible_opportunity_set_sha256,
    evaluate_formal_economic_qualification,
    execute_bound_run,
    execution_model_identity,
    fee_model_identity,
    funding_event_set_sha256,
    funding_model_identity,
    make_artifact_evidence,
    policy_identity,
    summarize_ledger,
)
from btc_quant_agent.economic.acceptance_verifier import (
    build_formal_decision_input_binding,
    build_passive_benchmark_accounting,
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
from btc_quant_agent.research_contract.canonical import (
    FrozenDict,
    canonical_json,
    canonical_sha256,
)
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
                available_at_ms=start + (index + 1) * CADENCE_MS,
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
                    "closed": item.closed,
                    "available_at_ms": item.available_at_ms,
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


def _funding_evidence(
    parent: Path,
    candles: tuple[Candle, ...],
    events: tuple[FundingSettlement, ...] = (),
) -> EvidenceReference:
    """Deterministic preregistered funding evidence artifact (AG-01 repair).

    Same parent, candles and events rebuild the identical evidence reference:
    content hash, fixed logical id and FIXED_TIME make evidence_id stable.
    """
    path = Path(parent) / "funding.json"
    path.write_text(
        canonical_json(
            {
                "schema_version": FORMAL_FUNDING_EVIDENCE_SCHEMA_VERSION,
                "product": "BTCUSDT",
                "coverage_start_ms": candles[0].open_time_ms,
                "coverage_end_ms": candles[-1].close_time_ms,
                "events": [
                    {
                        "timestamp_ms": item.timestamp_ms,
                        "funding_rate": item.funding_rate,
                        "mark_price": item.mark_price,
                    }
                    for item in sorted(events, key=lambda item: item.timestamp_ms)
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return EvidenceReference.from_file(
        path,
        evidence_type=FORMAL_FUNDING_EVIDENCE_TYPE,
        logical_id="p6-funding-dataset",
        producing_revision_id="DATASET-PIPELINE@v1",
        producing_code_revision="dataset-code-v1",
        observed_at_utc=FIXED_TIME,
    )


def _funding_interval(
    evidence: EvidenceReference,
    candles: tuple[Candle, ...],
    events: tuple[FundingSettlement, ...] = (),
) -> FundingIntervalIdentity:
    return FundingIntervalIdentity(
        evidence_id=evidence.evidence_id,
        content_sha256=evidence.content_sha256,
        coverage_start_ms=candles[0].open_time_ms,
        coverage_end_ms=candles[-1].close_time_ms,
        event_count=len(events),
        event_set_sha256=funding_event_set_sha256(events),
    )


def _default_funding_evidence(
    dataset: EvidenceReference,
    candles: tuple[Candle, ...],
    events: tuple[FundingSettlement, ...] = (),
) -> EvidenceReference:
    """Rebuild the funding evidence a _comparison call derives internally (AG-01)."""
    base = dataset.local_path()
    return _funding_evidence(base.parent if base is not None else Path("."), candles, events)


def _opportunities(candles: tuple[Candle, ...]) -> tuple[EligibleOpportunity, ...]:
    return tuple(
        EligibleOpportunity(
            f"OPP-{index}",
            candle.open_time_ms,
            FrozenDict(
                {
                    "decision_input_open_times_ms": (
                        candles[index - 1].open_time_ms,
                    )
                }
            ),
        )
        for index, candle in enumerate(candles[1:-1], start=1)
    )


def _decision_input_binding(
    signal: InformationSignal,
    dataset: EvidenceReference,
    candles: tuple[Candle, ...],
    protocol: ExperimentMetadata,
) -> FrozenDict:
    # R05B: the authoritative required window is the latest eligible row by
    # the decision timestamp; assert exactly that instead of a fixed row.
    eligible = [
        candle
        for candle in candles
        if candle.closed
        and candle.available_at_ms is not None
        and candle.available_at_ms <= signal.timestamp_ms
        and candle.close_time_ms <= signal.timestamp_ms
    ]
    latest = max(eligible, key=lambda item: item.open_time_ms)
    return build_formal_decision_input_binding(
        signal,
        dataset_evidence=dataset,
        input_contract=protocol.input_contract.to_dict(),
        candles=candles,
        material_input_open_times_ms=(latest.open_time_ms,),
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
        signal_producer_contract=SignalProducerRegistry.get_contract(
            "SYNTHETIC_FIXED_DIRECTION_V1"
        ),
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
    funding_events: tuple[FundingSettlement, ...] = (),
    funding_interval: FundingIntervalIdentity | None = None,
) -> ComparisonContract:
    metrics = ReturnMetricsContract(
        contract_name="P6_15M_CLOSE_RETURNS",
        sampling_rule="EQUITY_AT_EACH_CLOSED_15M_BAR",
        cadence_ms=CADENCE_MS,
        spacing_tolerance_ms=0,
    )
    if funding_interval is None:
        # AG-01: funding evidence becomes part of the preregistered comparison
        # identity; the default zero-event artifact lives next to the candles.
        base = dataset.local_path()
        funding_parent = base.parent if base is not None else Path(".")
        funding_interval = _funding_interval(
            _funding_evidence(funding_parent, candles, funding_events),
            candles,
            funding_events,
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
        funding_interval=funding_interval,
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
    funding_events: tuple[FundingSettlement, ...] = (),
) -> dict[str, Any]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    candles = _candles()
    engine = _zero_cost_engine()
    dataset = _dataset_evidence(tmp_path, candles)
    funding_evidence = _funding_evidence(tmp_path, candles, funding_events)
    opportunities = (
        tuple(
            replace(
                item,
                metadata=FrozenDict({**dict(item.metadata), "spread_bps": -1.0}),
            )
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
        funding_events=funding_events,
    )
    protocol = _protocol(comparison, engine)
    signal = InformationSignal(
        signal_id="P6_CANDIDATE_ENTRY",
        experiment_id=protocol.experiment_revision_id,
        timestamp_ms=candles[1].open_time_ms,
        direction=1,
        strength=1.0,
    )
    bundle = build_formal_replay_input_bundle(
        protocol=protocol,
        dataset_evidence=dataset,
        candles=candles,
        signals=(signal,),
        decision_inputs=(
            _decision_input_binding(signal, dataset, candles, protocol),
        ),
        funding_events=funding_events,
    )
    run = execute_bound_run(
        protocol=protocol,
        comparison=comparison,
        dataset_evidence=dataset,
        engine=engine,
        candles=candles,
        signals=(signal,),
        replay_input_bundle=bundle,
        funding_evidence=funding_evidence,
        funding_events=funding_events,
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
        funding_evidence=funding_evidence,
        funding_events=funding_events,
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
            funding_evidence.evidence_id,
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
        "funding_evidence": funding_evidence,
        "comparison": comparison,
        "protocol": protocol,
        "run": run,
        "run_evidence": run_evidence,
        "suite": suite,
        "suite_evidence": suite_evidence,
        "qualification": qualification,
        "result_evidence": result_evidence,
        "funding_events": funding_events,
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
    assert (
        qualification.result_hash
        == replace(qualification, generated_at_utc="2030-01-01T00:00:00+00:00").result_hash
    )

    protocol = artifacts["protocol"]
    registry, _ = _statistically_qualified_registry(tmp_path, protocol)
    event = registry.record_economic_qualification(
        qualification.decision_attestation(artifacts["result_evidence"]),
        evidence_references=(
            artifacts["dataset"],
            artifacts["funding_evidence"],
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
    assert (
        ResearchContractRegistry(registry.storage_path).get_status(protocol.experiment_revision_id)
        is DecisionStatus.ECONOMICALLY_QUALIFIED
    )


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
    assert [item.net_pnl_usdt for item in summary.round_trips] == pytest.approx([7.5, -12.5])
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
        execution_model=ExecutionModel(fee_model=fee, decision_latency_ms=0, exchange_latency_ms=0),
        initial_cash=10_000.0,
    )
    candles = _candles(count=3, drift=10.0)
    signal = InformationSignal("SLIP", "DIAGNOSTIC", candles[0].open_time_ms, direction=1)
    summary = engine.simulate(candles, (signal,))
    assert summary.slippage_attribution_usdt is not None
    assert summary.slippage_attribution_usdt > 0.0
    assert summary.realized_gross_pnl_usdt is not None
    assert summary.terminal_unrealized_pnl_usdt is not None
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
        funding_evidence=first["funding_evidence"],
        funding_events=first["funding_events"],
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
        assert (
            _protocol(variant, engine).experiment_revision_id
            != _protocol(baseline, engine).experiment_revision_id
        )
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
            artifacts["funding_evidence"],
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
        trial.matching_diagnostics["entry_count_match"] is False for trial in random_suite.trials
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
            artifacts["funding_evidence"],
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
                    case["funding_evidence"],
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
    registry, statistical = _statistically_qualified_registry(tmp_path, artifacts["protocol"])
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
            artifacts["qualification"].decision_attestation(artifacts["result_evidence"]),
            evidence_references=(
                artifacts["dataset"],
                artifacts["funding_evidence"],
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
        artifacts["candles"][1].open_time_ms,
        direction=1,
    )
    repeated_bundle = build_formal_replay_input_bundle(
        protocol=protocol,
        dataset_evidence=artifacts["dataset"],
        candles=artifacts["candles"],
        signals=(signal,),
        decision_inputs=(
            _decision_input_binding(
                signal,
                artifacts["dataset"],
                artifacts["candles"],
                protocol,
            ),
        ),
    )
    repeated = execute_bound_run(
        protocol=protocol,
        comparison=artifacts["comparison"],
        dataset_evidence=artifacts["dataset"],
        engine=artifacts["engine"],
        candles=artifacts["candles"],
        signals=(signal,),
        replay_input_bundle=repeated_bundle,
        funding_evidence=artifacts["funding_evidence"],
        funding_events=artifacts["funding_events"],
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
    signal = InformationSignal(
        signal_id="P6_CANDIDATE_ENTRY",
        experiment_id=artifacts["protocol"].experiment_revision_id,
        timestamp_ms=artifacts["candles"][1].open_time_ms,
        direction=1,
        strength=1.0,
    )
    second_bundle = build_formal_replay_input_bundle(
        protocol=artifacts["protocol"],
        dataset_evidence=artifacts["dataset"],
        candles=artifacts["candles"],
        signals=(signal,),
        decision_inputs=(
            _decision_input_binding(
                signal,
                artifacts["dataset"],
                artifacts["candles"],
                artifacts["protocol"],
            ),
        ),
    )
    second = execute_bound_run(
        protocol=artifacts["protocol"],
        comparison=artifacts["comparison"],
        dataset_evidence=artifacts["dataset"],
        engine=artifacts["engine"],
        candles=artifacts["candles"],
        signals=(signal,),
        replay_input_bundle=second_bundle,
        funding_evidence=artifacts["funding_evidence"],
        funding_events=artifacts["funding_events"],
    )
    assert first.result_id == second.result_id
    assert (
        first.accounting["formal_runtime_market_data_sha256"]
        == second.accounting["formal_runtime_market_data_sha256"]
    )


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


_BENCHMARK_RESULT_PAYLOAD_KEYS = (
    "benchmark_kind",
    "vehicle",
    "accounting",
    "comparable",
    "matching_diagnostics",
    "trial_id",
    "seed",
    "run_result_id",
)


def _refresh_benchmark_record_id(record: dict[str, Any]) -> None:
    payload = {key: record.get(key) for key in _BENCHMARK_RESULT_PAYLOAD_KEYS}
    record["result_id"] = f"benchmark-result@{canonical_sha256(payload)}"


def _refresh_suite_identity(suite: dict[str, Any]) -> None:
    for key in ("cash", "passive"):
        record = suite.get(key)
        if isinstance(record, dict):
            _refresh_benchmark_record_id(record)
    random_record = suite.get("random")
    if isinstance(random_record, dict):
        trials = random_record["trials"]
        for trial in trials:
            _refresh_benchmark_record_id(trial)
        random_record["distribution_id"] = "random-distribution@" + canonical_sha256(
            {"seed": random_record["seed"], "provenance": random_record["provenance"], "trials": trials}
        )
    suite_payload = {
        key: suite.get(key)
        for key in (
            "comparison_contract_id",
            "candidate_run_result_id",
            "eligible_opportunity_set_sha256",
            "cash",
            "passive",
            "random",
        )
    }
    suite["suite_id"] = f"benchmark-suite@{canonical_sha256(suite_payload)}"


def _suite_result_ids(suite: dict[str, Any]) -> list[str]:
    result: list[str] = []
    if suite.get("cash") is not None:
        result.append(suite["cash"]["result_id"])
    if suite.get("passive") is not None:
        result.append(suite["passive"]["result_id"])
    random_record = suite.get("random")
    if random_record is not None:
        result.append(random_record["distribution_id"])
        result.extend(trial["result_id"] for trial in random_record["trials"])
    return result


def _write_forged_registry_artifacts(
    tmp_path: Path,
    artifacts: dict[str, Any],
    artifact: dict[str, Any],
    *,
    run_changed: bool,
    suite_changed: bool,
) -> tuple[Any, tuple[EvidenceReference, ...]]:
    semantic = artifact["semantic_payload"]
    protocol = artifacts["protocol"]
    run_evidence = artifacts["run_evidence"]
    suite_evidence = artifacts["suite_evidence"]

    if run_changed:
        run_path = tmp_path / "forged-run.json"
        run_path.write_text(canonical_json(semantic["run_result"]) + "\n", encoding="utf-8")
        run_evidence = make_artifact_evidence(
            run_path,
            evidence_type=P6_RUN_EVIDENCE_TYPE,
            logical_id="p6-forged-candidate-run",
            protocol=protocol,
            observed_at_utc=FIXED_TIME,
        )
    if suite_changed:
        suite_path = tmp_path / "forged-suite.json"
        suite_path.write_text(canonical_json(semantic["benchmark_suite"]) + "\n", encoding="utf-8")
        suite_evidence = make_artifact_evidence(
            suite_path,
            evidence_type=P6_BENCHMARK_EVIDENCE_TYPE,
            logical_id="p6-forged-benchmark-suite",
            protocol=protocol,
            observed_at_utc=FIXED_TIME,
        )

    semantic["required_evidence_ids"] = [
        artifacts["dataset"].evidence_id,
        artifacts["funding_evidence"].evidence_id,
        run_evidence.evidence_id,
        suite_evidence.evidence_id,
    ]
    result_hash = canonical_sha256(semantic)
    artifact["result_id"] = f"economic-qualification@{result_hash}"
    result_path = tmp_path / "forged-qualification.json"
    result_path.write_text(canonical_json(artifact) + "\n", encoding="utf-8")
    result_evidence = make_artifact_evidence(
        result_path,
        evidence_type=P6_RESULT_EVIDENCE_TYPE,
        logical_id="p6-forged-qualification-result",
        protocol=protocol,
        observed_at_utc=FIXED_TIME,
    )
    original_attestation = artifacts["qualification"].decision_attestation(
        artifacts["result_evidence"]
    )
    attestation = replace(
        original_attestation,
        result_evidence_id=result_evidence.evidence_id,
        result_artifact_sha256=result_evidence.content_sha256,
        result_id=artifact["result_id"],
        result_hash=result_hash,
        verdict=semantic["verdict"],
        run_result_id=semantic["run_result_id"],
        benchmark_suite_id=semantic["benchmark_suite_id"],
        benchmark_result_ids=tuple(semantic["benchmark_result_ids"]),
        required_evidence_ids=tuple(semantic["required_evidence_ids"]),
    )
    return attestation, (
        artifacts["dataset"],
        artifacts["funding_evidence"],
        run_evidence,
        suite_evidence,
        result_evidence,
    )


def _replay_passive_with(
    artifacts: dict[str, Any],
    *,
    fee_model: FeeModel | None = None,
    execution_model: ExecutionModel | None = None,
    funding_events: tuple[FundingSettlement, ...] | None = None,
    terminal_policy: TerminalPolicy | None = None,
) -> dict[str, Any]:
    engine = artifacts["engine"]
    comparison = artifacts["comparison"]
    selected_fee = fee_model or engine.fee_model
    selected_execution = execution_model or ExecutionModel(
        fee_model=selected_fee,
        decision_latency_ms=engine.execution_model.decision_latency_ms,
        exchange_latency_ms=engine.execution_model.exchange_latency_ms,
        limit_fill_prob_on_touch=engine.execution_model.limit_fill_prob_on_touch,
    )
    return build_passive_benchmark_accounting(
        candidate_identity=artifacts["run"].identity.to_dict(),
        product=comparison.product_scope[0],
        initial_cash=comparison.initial_capital,
        candles=artifacts["candles"],
        fee_model=selected_fee,
        execution_model=selected_execution,
        funding_model=engine.funding_model,
        funding_events=(artifacts["funding_events"] if funding_events is None else funding_events),
        interval_start_ms=comparison.data_interval.start_ms,
        interval_end_ms=comparison.data_interval.end_ms,
        terminal_policy=terminal_policy or comparison.terminal_policy,
        metrics_contract=comparison.metrics_contract,
    )


def _assert_rehashed_passive_forgery_rejected(
    tmp_path: Path,
    artifacts: dict[str, Any],
    *,
    forged_accounting: dict[str, Any] | None = None,
    mutation: Any = None,
) -> None:
    artifact = json.loads(canonical_json(artifacts["qualification"].to_dict()))
    semantic = artifact["semantic_payload"]
    suite = semantic["benchmark_suite"]
    passive = suite["passive"]
    assert passive is not None
    if forged_accounting is not None:
        passive["accounting"] = forged_accounting
    if mutation is not None:
        mutation(passive)
    _refresh_suite_identity(suite)
    semantic["benchmark_suite_id"] = suite["suite_id"]
    semantic["benchmark_result_ids"] = _suite_result_ids(suite)

    forged_dir = tmp_path / "forged"
    forged_dir.mkdir()
    attestation, evidence = _write_forged_registry_artifacts(
        forged_dir,
        artifacts,
        artifact,
        run_changed=False,
        suite_changed=True,
    )
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    registry, _ = _statistically_qualified_registry(registry_dir, artifacts["protocol"])
    with pytest.raises(EvidenceValidationError, match="semantic replay"):
        registry.record_economic_qualification(
            attestation,
            evidence_references=evidence,
            reason="rehashed passive benchmark forgery must fail closed",
            actor="pytest",
            decided_at_utc=FIXED_TIME,
        )


def test_registry_rejects_rehashed_passive_fee_replay(tmp_path: Path) -> None:
    artifacts = _formal_artifacts(tmp_path / "base")
    wrong_fee = replace(artifacts["engine"].fee_model, taker_fee_rate=0.000001)
    forged = _replay_passive_with(artifacts, fee_model=wrong_fee)
    original = artifacts["suite"].passive
    assert original is not None
    original_events = original.accounting["trade_events"]
    forged_events = forged["trade_events"]
    assert forged_events[0]["fee_usdt"] == pytest.approx(original_events[0]["fee_usdt"] + 0.01)
    _assert_rehashed_passive_forgery_rejected(tmp_path, artifacts, forged_accounting=forged)


def test_registry_rejects_rehashed_passive_fill_price_replay(tmp_path: Path) -> None:
    artifacts = _formal_artifacts(tmp_path / "base")
    wrong_fee = replace(
        artifacts["engine"].fee_model,
        slippage_mode=SlippageMode.FIXED_BPS,
        fixed_slippage_bps=1.0,
    )
    forged = _replay_passive_with(artifacts, fee_model=wrong_fee)
    original = artifacts["suite"].passive
    assert original is not None
    assert forged["trade_events"][0]["price"] != original.accounting["trade_events"][0]["price"]
    _assert_rehashed_passive_forgery_rejected(tmp_path, artifacts, forged_accounting=forged)


def test_registry_rejects_rehashed_passive_entry_timestamp_replay(
    tmp_path: Path,
) -> None:
    artifacts = _formal_artifacts(tmp_path / "base")
    engine = artifacts["engine"]
    wrong_execution = ExecutionModel(
        fee_model=engine.fee_model,
        decision_latency_ms=1,
        exchange_latency_ms=0,
        limit_fill_prob_on_touch=engine.execution_model.limit_fill_prob_on_touch,
    )
    forged = _replay_passive_with(artifacts, execution_model=wrong_execution)
    original = artifacts["suite"].passive
    assert original is not None
    assert (
        forged["trade_events"][0]["timestamp_ms"]
        != original.accounting["trade_events"][0]["timestamp_ms"]
    )
    _assert_rehashed_passive_forgery_rejected(tmp_path, artifacts, forged_accounting=forged)


def test_registry_rejects_rehashed_passive_missing_funding_event(
    tmp_path: Path,
) -> None:
    candles = _candles()
    funding = (
        FundingSettlement(
            timestamp_ms=candles[2].open_time_ms,
            funding_rate=0.001,
            mark_price=candles[2].open,
        ),
    )
    artifacts = _formal_artifacts(tmp_path / "base", funding_events=funding)
    forged = _replay_passive_with(artifacts, funding_events=())
    original = artifacts["suite"].passive
    assert original is not None
    assert any(
        event["action"] == TradeAction.FUNDING_SETTLEMENT.value
        for event in original.accounting["trade_events"]
    )
    assert all(
        event["action"] != TradeAction.FUNDING_SETTLEMENT.value for event in forged["trade_events"]
    )
    _assert_rehashed_passive_forgery_rejected(tmp_path, artifacts, forged_accounting=forged)


def test_registry_rejects_rehashed_passive_execution_identity(tmp_path: Path) -> None:
    artifacts = _formal_artifacts(tmp_path / "base")

    def mutate(passive: dict[str, Any]) -> None:
        identity = passive["accounting"]["formal_run_identity"]
        identity["execution_model"]["content_sha256"] = "0" * 64

    _assert_rehashed_passive_forgery_rejected(tmp_path, artifacts, mutation=mutate)


def test_registry_rejects_rehashed_passive_terminal_policy(tmp_path: Path) -> None:
    artifacts = _formal_artifacts(tmp_path / "base")
    forged = _replay_passive_with(artifacts, terminal_policy=TerminalPolicy.MARK_TO_MARKET_OPEN)
    assert forged["terminal_policy"] == TerminalPolicy.MARK_TO_MARKET_OPEN.value
    _assert_rehashed_passive_forgery_rejected(tmp_path, artifacts, forged_accounting=forged)


def test_registry_rejects_rehashed_forged_run_accounting(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    artifacts = _formal_artifacts(base)
    artifact = json.loads(canonical_json(artifacts["qualification"].to_dict()))
    semantic = artifact["semantic_payload"]
    run_artifact = semantic["run_result"]
    accounting = run_artifact["semantic_payload"]["accounting"]
    delta = 100.0
    accounting["final_equity"] += delta
    accounting["final_cash"] += delta
    accounting["gross_pnl_usdt"] += delta
    accounting["realized_gross_pnl_usdt"] += delta
    accounting["net_pnl_usdt"] += delta
    accounting["net_return_pct"] = accounting["net_pnl_usdt"] / accounting["initial_cash"]
    accounting["equity_curve"][-1][1] += delta
    semantic["metric_values"]["net_return_pct"] = accounting["net_return_pct"]
    semantic["gates"][0]["observed_value"] = accounting["net_return_pct"]

    run_semantic = run_artifact["semantic_payload"]
    run_artifact["result_id"] = "economic-run-result@" + canonical_sha256(run_semantic)
    semantic["run_result_id"] = run_artifact["result_id"]
    suite = semantic["benchmark_suite"]
    suite["candidate_run_result_id"] = run_artifact["result_id"]
    _refresh_suite_identity(suite)
    semantic["benchmark_suite_id"] = suite["suite_id"]
    semantic["benchmark_result_ids"] = _suite_result_ids(suite)

    forged_dir = tmp_path / "forged"
    forged_dir.mkdir()
    attestation, evidence = _write_forged_registry_artifacts(
        forged_dir,
        artifacts,
        artifact,
        run_changed=True,
        suite_changed=True,
    )
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    registry, _ = _statistically_qualified_registry(registry_dir, artifacts["protocol"])
    with pytest.raises(EvidenceValidationError, match="semantic replay"):
        registry.record_economic_qualification(
            attestation,
            evidence_references=evidence,
            reason="forged run accounting must fail closed",
            actor="pytest",
            decided_at_utc=FIXED_TIME,
        )


def test_registry_rejects_rehashed_forged_gate_and_verdict(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    artifacts = _formal_artifacts(base, threshold=1.0)
    assert artifacts["qualification"].verdict is QualificationVerdict.REJECTED
    artifact = json.loads(canonical_json(artifacts["qualification"].to_dict()))
    semantic = artifact["semantic_payload"]
    gate = semantic["gates"][0]
    gate["observed_value"] = 2.0
    gate["testable"] = True
    gate["passed"] = True
    gate["reason_code"] = "GATE_PASSED"
    semantic["verdict"] = "QUALIFIED"
    semantic["reason_codes"] = ["ALL_PREREGISTERED_HURDLES_PASSED"]

    forged_dir = tmp_path / "forged"
    forged_dir.mkdir()
    attestation, evidence = _write_forged_registry_artifacts(
        forged_dir,
        artifacts,
        artifact,
        run_changed=False,
        suite_changed=False,
    )
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    registry, _ = _statistically_qualified_registry(registry_dir, artifacts["protocol"])
    with pytest.raises(EvidenceValidationError, match="semantic replay"):
        registry.record_economic_qualification(
            attestation,
            evidence_references=evidence,
            reason="forged qualification gate must fail closed",
            actor="pytest",
            decided_at_utc=FIXED_TIME,
        )


def test_registry_rejects_rehashed_forged_random_matching_diagnostics(
    tmp_path: Path,
) -> None:
    base = tmp_path / "base"
    base.mkdir()
    artifacts = _formal_artifacts(base)
    artifact = json.loads(canonical_json(artifacts["qualification"].to_dict()))
    semantic = artifact["semantic_payload"]
    suite = semantic["benchmark_suite"]
    random_record = suite["random"]
    assert random_record is not None
    trial = random_record["trials"][0]
    trial["matching_diagnostics"]["trial_entry_count"] += 1
    _refresh_suite_identity(suite)
    semantic["benchmark_suite_id"] = suite["suite_id"]
    semantic["benchmark_result_ids"] = _suite_result_ids(suite)

    forged_dir = tmp_path / "forged"
    forged_dir.mkdir()
    attestation, evidence = _write_forged_registry_artifacts(
        forged_dir,
        artifacts,
        artifact,
        run_changed=False,
        suite_changed=True,
    )
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    registry, _ = _statistically_qualified_registry(registry_dir, artifacts["protocol"])
    with pytest.raises(EvidenceValidationError, match="matching diagnostics"):
        registry.record_economic_qualification(
            attestation,
            evidence_references=evidence,
            reason="forged random comparability must fail closed",
            actor="pytest",
            decided_at_utc=FIXED_TIME,
        )


def test_registry_rejects_rehashed_forged_random_trial_dataset(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    artifacts = _formal_artifacts(base)
    artifact = json.loads(canonical_json(artifacts["qualification"].to_dict()))
    semantic = artifact["semantic_payload"]
    suite = semantic["benchmark_suite"]
    random_record = suite["random"]
    assert random_record is not None
    trial = random_record["trials"][0]
    accounting = trial["accounting"]
    # Mutate one candle within valid OHLC bounds
    bar = accounting["formal_runtime_market_data"][0]
    bar["high"] = max(bar["high"], bar["close"] + 0.5)
    bar["close"] = bar["close"] + 0.5
    accounting["formal_runtime_market_data_sha256"] = canonical_sha256(
        {
            "schema_version": accounting["formal_runtime_market_data_schema_version"],
            "candles": accounting["formal_runtime_market_data"],
        }
    )
    identity = accounting["formal_run_identity"]
    trial["run_result_id"] = "economic-run-result@" + canonical_sha256(
        {"run_identity": identity, "accounting": accounting}
    )
    _refresh_suite_identity(suite)
    semantic["benchmark_suite_id"] = suite["suite_id"]
    semantic["benchmark_result_ids"] = _suite_result_ids(suite)

    forged_dir = tmp_path / "forged"
    forged_dir.mkdir()
    attestation, evidence = _write_forged_registry_artifacts(
        forged_dir,
        artifacts,
        artifact,
        run_changed=False,
        suite_changed=True,
    )
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    registry, _ = _statistically_qualified_registry(registry_dir, artifacts["protocol"])
    with pytest.raises(
        EvidenceValidationError, match="dataset evidence|candle payload|market data"
    ):
        registry.record_economic_qualification(
            attestation,
            evidence_references=evidence,
            reason="forged random trial dataset must fail closed",
            actor="pytest",
            decided_at_utc=FIXED_TIME,
        )


def test_registry_rejects_rehashed_forged_random_cost_identity(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    artifacts = _formal_artifacts(base)
    artifact = json.loads(canonical_json(artifacts["qualification"].to_dict()))
    semantic = artifact["semantic_payload"]
    suite = semantic["benchmark_suite"]
    random_record = suite["random"]
    assert random_record is not None
    trial = random_record["trials"][0]
    accounting = trial["accounting"]
    # Modify cost_model identity in random trial
    identity = dict(accounting["formal_run_identity"])
    cost_model = dict(identity["cost_model"])
    cost_model["name"] = "FORGED_COST_MODEL"
    identity["cost_model"] = cost_model
    accounting["formal_run_identity"] = identity
    trial["run_result_id"] = "economic-run-result@" + canonical_sha256(
        {"run_identity": identity, "accounting": accounting}
    )
    _refresh_suite_identity(suite)
    semantic["benchmark_suite_id"] = suite["suite_id"]
    semantic["benchmark_result_ids"] = _suite_result_ids(suite)

    forged_dir = tmp_path / "forged"
    forged_dir.mkdir()
    attestation, evidence = _write_forged_registry_artifacts(
        forged_dir,
        artifacts,
        artifact,
        run_changed=False,
        suite_changed=True,
    )
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    registry, _ = _statistically_qualified_registry(registry_dir, artifacts["protocol"])
    with pytest.raises(EvidenceValidationError, match="cost_model|matching diagnostics|identity"):
        registry.record_economic_qualification(
            attestation,
            evidence_references=evidence,
            reason="forged random cost identity must fail closed",
            actor="pytest",
            decided_at_utc=FIXED_TIME,
        )


def test_registry_rejects_rehashed_forged_random_execution_identity(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    artifacts = _formal_artifacts(base)
    artifact = json.loads(canonical_json(artifacts["qualification"].to_dict()))
    semantic = artifact["semantic_payload"]
    suite = semantic["benchmark_suite"]
    random_record = suite["random"]
    assert random_record is not None
    trial = random_record["trials"][0]
    accounting = trial["accounting"]
    # Modify execution_model identity in random trial
    identity = dict(accounting["formal_run_identity"])
    exec_model = dict(identity["execution_model"])
    exec_model["name"] = "FORGED_EXECUTION_MODEL"
    identity["execution_model"] = exec_model
    accounting["formal_run_identity"] = identity
    trial["run_result_id"] = "economic-run-result@" + canonical_sha256(
        {"run_identity": identity, "accounting": accounting}
    )
    _refresh_suite_identity(suite)
    semantic["benchmark_suite_id"] = suite["suite_id"]
    semantic["benchmark_result_ids"] = _suite_result_ids(suite)

    forged_dir = tmp_path / "forged"
    forged_dir.mkdir()
    attestation, evidence = _write_forged_registry_artifacts(
        forged_dir,
        artifacts,
        artifact,
        run_changed=False,
        suite_changed=True,
    )
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    registry, _ = _statistically_qualified_registry(registry_dir, artifacts["protocol"])
    with pytest.raises(
        EvidenceValidationError, match="execution_model|matching diagnostics|identity"
    ):
        registry.record_economic_qualification(
            attestation,
            evidence_references=evidence,
            reason="forged random execution identity must fail closed",
            actor="pytest",
            decided_at_utc=FIXED_TIME,
        )


def test_registry_rejects_rehashed_forged_random_terminal_or_comparison_identity(
    tmp_path: Path,
) -> None:
    base = tmp_path / "base"
    base.mkdir()
    artifacts = _formal_artifacts(base)
    artifact = json.loads(canonical_json(artifacts["qualification"].to_dict()))
    semantic = artifact["semantic_payload"]
    suite = semantic["benchmark_suite"]
    random_record = suite["random"]
    assert random_record is not None
    trial = random_record["trials"][0]
    accounting = trial["accounting"]
    # Modify comparison_contract_hash in random trial
    identity = dict(accounting["formal_run_identity"])
    identity["comparison_contract_hash"] = "0" * 64
    accounting["formal_run_identity"] = identity
    trial["run_result_id"] = "economic-run-result@" + canonical_sha256(
        {"run_identity": identity, "accounting": accounting}
    )
    _refresh_suite_identity(suite)
    semantic["benchmark_suite_id"] = suite["suite_id"]
    semantic["benchmark_result_ids"] = _suite_result_ids(suite)

    forged_dir = tmp_path / "forged"
    forged_dir.mkdir()
    attestation, evidence = _write_forged_registry_artifacts(
        forged_dir,
        artifacts,
        artifact,
        run_changed=False,
        suite_changed=True,
    )
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    registry, _ = _statistically_qualified_registry(registry_dir, artifacts["protocol"])
    with pytest.raises(EvidenceValidationError, match="comparison_contract_hash|identity"):
        registry.record_economic_qualification(
            attestation,
            evidence_references=evidence,
            reason="forged comparison identity must fail closed",
            actor="pytest",
            decided_at_utc=FIXED_TIME,
        )


def test_registry_rejects_rehashed_forged_same_diagnostics(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    artifacts = _formal_artifacts(base)
    artifact = json.loads(canonical_json(artifacts["qualification"].to_dict()))
    semantic = artifact["semantic_payload"]
    suite = semantic["benchmark_suite"]
    random_record = suite["random"]
    assert random_record is not None
    trial = random_record["trials"][0]
    accounting = trial["accounting"]
    # Change underlying identity
    identity = dict(accounting["formal_run_identity"])
    cost_model = dict(identity["cost_model"])
    cost_model["name"] = "FORGED_COST_MODEL"
    identity["cost_model"] = cost_model
    accounting["formal_run_identity"] = identity
    trial["run_result_id"] = "economic-run-result@" + canonical_sha256(
        {"run_identity": identity, "accounting": accounting}
    )
    # But forge matching diagnostics to claim True
    trial["matching_diagnostics"]["same_policy_cost_execution_funding"] = True
    _refresh_suite_identity(suite)
    semantic["benchmark_suite_id"] = suite["suite_id"]
    semantic["benchmark_result_ids"] = _suite_result_ids(suite)

    forged_dir = tmp_path / "forged"
    forged_dir.mkdir()
    attestation, evidence = _write_forged_registry_artifacts(
        forged_dir,
        artifacts,
        artifact,
        run_changed=False,
        suite_changed=True,
    )
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    registry, _ = _statistically_qualified_registry(registry_dir, artifacts["protocol"])
    with pytest.raises(EvidenceValidationError, match="matching diagnostics|cost_model|identity"):
        registry.record_economic_qualification(
            attestation,
            evidence_references=evidence,
            reason="forged same_* diagnostics must fail closed",
            actor="pytest",
            decided_at_utc=FIXED_TIME,
        )


def test_validate_formal_run_identity_binding_checks_all_critical_fields(tmp_path: Path) -> None:
    from btc_quant_agent.economic.acceptance_verifier import (
        _CRITICAL_IDENTITY_FIELDS,
        validate_formal_run_identity_binding,
    )

    base = tmp_path / "base"
    base.mkdir()
    artifacts = _formal_artifacts(base)
    candidate_id = json.loads(canonical_json(artifacts["run"].identity.to_dict()))
    trial_id = dict(candidate_id)

    # Positive control: identical identities pass
    validate_formal_run_identity_binding(candidate_id, trial_id)

    # Negative controls: each critical field discrepancy fails closed
    for field in _CRITICAL_IDENTITY_FIELDS:
        corrupted = dict(candidate_id)
        if field == "initial_capital":
            corrupted[field] = corrupted[field] + 100.0
        elif field == "product_scope":
            corrupted[field] = ("ETHUSDT",)
        elif field in ("interval_start_ms", "interval_end_ms", "observation_count"):
            corrupted[field] = corrupted[field] + 1
        elif isinstance(corrupted[field], dict):
            corrupted_dict = dict(corrupted[field])
            corrupted_dict["name"] = "MUTATED"
            corrupted[field] = corrupted_dict
        else:
            corrupted[field] = "MUTATED_FIELD_VALUE"
        with pytest.raises(ValueError, match=f"random trial identity {field} mismatch"):
            validate_formal_run_identity_binding(candidate_id, corrupted)

    # Completeness check
    corrupted_completeness = dict(candidate_id)
    corrupted_completeness["completeness"] = "PARTIAL"
    with pytest.raises(ValueError, match="COMPLETE"):
        validate_formal_run_identity_binding(candidate_id, corrupted_completeness)

    # Funding event set check
    corrupted_funding = dict(candidate_id)
    corrupted_funding["funding_event_set_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="funding event set"):
        validate_formal_run_identity_binding(candidate_id, corrupted_funding)
