"""Synthetic inputs and fully rehashed adversarial artifacts (never production replay)."""

from dataclasses import replace
from pathlib import Path

import test_v041_p6_metrics_benchmarks_qualification as p6

from btc_quant_agent.economic import (
    BenchmarkKind,
    EconomicSimulationEngine,
    ExecutionModel,
    FeeModel,
    FundingSettlement,
    InformationSignal,
    SlippageMode,
    build_formal_benchmark_suite,
    build_formal_replay_input_bundle,
    evaluate_formal_economic_qualification,
    execute_bound_run,
    make_artifact_evidence,
)
from btc_quant_agent.economic.acceptance_verifier import (
    _curve_and_notional_from_ledger,
    verify_formal_accounting,
)
from btc_quant_agent.economic.metrics import summarize_ledger
from btc_quant_agent.economic.portfolio import Portfolio
from btc_quant_agent.economic.replay_bundle import ReplayInputBundle
from btc_quant_agent.economic.trade_event import TradeAction
from btc_quant_agent.research_contract.canonical import FrozenDict, canonical_sha256, thaw_json


def context(tmp_path: Path, *, count=8, trials=4, nonzero=True, opportunities=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    candles = p6._candles(count)
    base = p6._zero_cost_engine()
    fee = FeeModel(
        taker_fee_rate=0.0005 if nonzero else 0.0, maker_fee_rate=0.0,
        slippage_mode=SlippageMode.SPREAD_AND_IMPACT if nonzero else SlippageMode.ZERO,
        max_slippage_bps=20.0,
    )
    engine = EconomicSimulationEngine(
        policy=base.policy, fee_model=fee, initial_cash=base.initial_cash,
        execution_model=ExecutionModel(fee_model=fee, decision_latency_ms=0, exchange_latency_ms=0),
    )
    dataset = p6._dataset_evidence(tmp_path, candles)
    opportunities = opportunities if opportunities is not None else p6._opportunities(candles)
    funding = (FundingSettlement(candles[1].open_time_ms + 1000, 0.001, 101.0),) if nonzero else ()
    funding_evidence = p6._funding_evidence(tmp_path, candles, funding)
    comparison = p6._comparison(
        dataset, candles, engine, required=(BenchmarkKind.CASH, BenchmarkKind.RANDOM_MATCHED),
        descriptive=(), trials=trials, opportunities=opportunities, funding_events=funding,
    )
    protocol = p6._protocol(comparison, engine)
    signals = tuple(InformationSignal(
        f"REPLAY-{index}", protocol.experiment_revision_id, candles[index].open_time_ms,
        direction=direction,
        metadata={
            "spread_bps": 2.0, "liquidity_volume_base": 1000.0,
            "liquidity_available_at_ms": candles[index - 1].close_time_ms,
        } if nonzero else {},
    ) for index, direction in ((1, 1), (4, -1)))
    bundle = build_formal_replay_input_bundle(
        protocol=protocol, dataset_evidence=dataset, candles=candles, signals=signals,
        decision_inputs=tuple(p6._decision_input_binding(signal, dataset, candles, protocol) for signal in signals),
        funding_events=funding,
    )
    run = execute_bound_run(
        protocol=protocol, comparison=comparison, dataset_evidence=dataset, candles=candles,
        engine=engine, signals=signals, replay_input_bundle=bundle,
        funding_evidence=funding_evidence, funding_events=funding,
    )
    suite = build_formal_benchmark_suite(
        protocol=protocol, comparison=comparison, dataset_evidence=dataset, candidate_run=run,
        engine=engine, candles=candles, eligible_opportunities=opportunities,
        funding_evidence=funding_evidence, funding_events=funding,
    )
    return {"protocol": protocol, "comparison": comparison, "dataset": dataset, "candles": candles,
            "engine": engine, "run": run, "suite": suite, "funding": funding,
            "funding_evidence": funding_evidence, "signals": signals}


def assert_accounting(ctx, accounting):
    comp = ctx["comparison"]
    verify_formal_accounting(
        accounting, product="BTCUSDT", initial_cash=comp.initial_capital,
        interval_start_ms=comp.data_interval.start_ms, interval_end_ms=comp.data_interval.end_ms,
        terminal_policy=comp.terminal_policy, metrics_contract=comp.metrics_contract,
    )


def persisted_qualification(ctx, directory):
    evidence = []
    for name, artifact, kind in (
        ("candidate-run", ctx["run"], p6.P6_RUN_EVIDENCE_TYPE),
        ("benchmark-suite", ctx["suite"], p6.P6_BENCHMARK_EVIDENCE_TYPE),
    ):
        path = directory / f"{name}.json"
        artifact.write(path)
        evidence.append(make_artifact_evidence(
            path, evidence_type=kind, logical_id=name, protocol=ctx["protocol"],
            observed_at_utc=p6.FIXED_TIME,
        ))
    qualification = evaluate_formal_economic_qualification(
        protocol=ctx["protocol"], comparison=ctx["comparison"], candidate_run=ctx["run"],
        benchmarks=ctx["suite"], required_evidence_ids=tuple(
            item.evidence_id for item in (ctx["dataset"], *evidence)
        ), generated_at_utc=p6.FIXED_TIME,
    )
    path = directory / "qualification.json"
    qualification.write(path)
    result_evidence = make_artifact_evidence(
        path, evidence_type=p6.P6_RESULT_EVIDENCE_TYPE, logical_id="qualification",
        protocol=ctx["protocol"], observed_at_utc=p6.FIXED_TIME,
    )
    return {**ctx, "qualification": qualification, "run_evidence": evidence[0],
            "suite_evidence": evidence[1], "result_evidence": result_evidence}


def assert_registry_rejects_atomic(tmp_path, artifacts, artifact, match):
    semantic = artifact["semantic_payload"]
    suite = semantic["benchmark_suite"]
    p6._refresh_suite_identity(suite)
    semantic["benchmark_suite_id"] = suite["suite_id"]
    semantic["benchmark_result_ids"] = p6._suite_result_ids(suite)
    forged_dir = tmp_path / "forged"
    forged_dir.mkdir()
    attestation, evidence = p6._write_forged_registry_artifacts(
        forged_dir, artifacts, artifact, run_changed=False, suite_changed=True,
    )
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    registry, _ = p6._statistically_qualified_registry(registry_dir, artifacts["protocol"])
    before, generation = registry.storage_path.read_bytes(), registry.generation
    import pytest

    from btc_quant_agent.research_contract.registry import EvidenceValidationError
    with pytest.raises(EvidenceValidationError, match=match):
        registry.record_economic_qualification(
            attestation, evidence_references=evidence, reason="rehashed semantic attack", actor="pytest",
        )
    assert registry.generation == generation
    assert registry.storage_path.read_bytes() == before


def coherent_forgery(ctx, *, price=None, fee_delta=0.0, funding_delta=0.0, quantity_scale=1.0):
    """Recompute all ledger-derived state/metrics and all affected candidate-owned hashes."""
    run = ctx["run"]
    portfolio = Portfolio(ctx["comparison"].initial_capital)
    first = True
    for event in run.accounting["trade_events"]:
        item = thaw_json(event)
        action = TradeAction(item["action"])
        if action == TradeAction.FUNDING_SETTLEMENT:
            portfolio.apply_funding(item["timestamp_ms"], "BTCUSDT",
                                    item["funding_usdt"] + funding_delta, item["price"])
        else:
            portfolio.apply_trade(
                item["timestamp_ms"], action, "BTCUSDT",
                price if first and price is not None else item["price"],
                item["quantity"] * quantity_scale, item["fee_usdt"] + fee_delta,
                item["signal_id"], item["trade_id"],
                observation_timestamp_ms=item["observation_timestamp_ms"],
                decision_timestamp_ms=item["decision_timestamp_ms"],
                order_timestamp_ms=item["order_timestamp_ms"],
                settlement_timestamp_ms=item["settlement_timestamp_ms"], metadata=item["metadata"],
            )
            first = False
    initial = ctx["comparison"].initial_capital
    candles = ctx["candles"]
    curve = [(c.close_time_ms, Portfolio.from_events(
        initial, [event for event in portfolio.trade_history if event.timestamp_ms <= c.close_time_ms]
    ).total_equity({"BTCUSDT": c.close})) for c in candles]
    curve, notional, drawdown = _curve_and_notional_from_ledger(
        initial_cash=initial, events=portfolio.trade_history, candles=candles,
        observed_curve=[list(point) for point in curve], product="BTCUSDT",
    )
    comp = ctx["comparison"]
    summary = summarize_ledger(
        initial_cash=initial, events=portfolio.trade_history, equity_curve=curve,
        final_asset="BTCUSDT", final_mark_price=candles[-1].close,
        interval_start_ms=comp.data_interval.start_ms, interval_end_ms=comp.data_interval.end_ms,
        notional_curve=notional, terminal_policy=comp.terminal_policy,
        metrics_contract=comp.metrics_contract, max_drawdown_override=drawdown,
    )
    accounting = thaw_json(run.accounting)
    accounting.update(summary.to_dict())
    identity = run.identity
    bundle = accounting.get("formal_replay_input_bundle")
    if bundle is not None:
        by_id = {item.trade_id: item for item in portfolio.trade_history}
        for entry in bundle["causal_execution_inputs"]:
            event = by_id[entry["trade_id"]]
            entry.update(quantity=event.quantity, price=event.price)
        bundle["bundle_sha256"] = canonical_sha256({key: value for key, value in bundle.items() if key != "bundle_sha256"})
        assert ReplayInputBundle(**bundle).bundle_sha256 == bundle["bundle_sha256"]
        accounting["formal_replay_input_bundle_sha256"] = bundle["bundle_sha256"]
        identity = replace(identity, replay_input_bundle_sha256=bundle["bundle_sha256"])
    accounting["formal_run_identity"] = identity.to_dict()
    forged = replace(run, identity=identity, accounting=FrozenDict(accounting))
    assert_accounting(ctx, thaw_json(forged.accounting))
    return forged
