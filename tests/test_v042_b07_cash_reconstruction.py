"""CASH has an independently reconstructed, exact no-activity economic payload."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import test_v041_p6_metrics_benchmarks_qualification as p6
from helpers_v042_economic_replay import assert_registry_rejects_atomic, context

from btc_quant_agent.economic.acceptance_verifier import validate_persisted_qualification_semantics
from btc_quant_agent.economic.execution_replay import verify_benchmark_replay
from btc_quant_agent.research_contract.canonical import canonical_json, thaw_json


@pytest.mark.parametrize("attack", ["traded", "funding", "fee", "position", "grid", "equity", "kind", "vehicle", "seed", "terminal"])
def test_b07_t1_through_t7_fully_rehashed_cash_substitution_rejected(tmp_path: Path, attack: str) -> None:
    ctx = context(tmp_path)
    suite = ctx["suite"].to_dict()
    cash = suite["cash"]
    accounting = cash["accounting"]
    if attack == "traded":
        cash["accounting"] = thaw_json(ctx["run"].accounting)
    elif attack == "funding":
        accounting["total_funding_usdt"] = 1.0
    elif attack == "fee":
        accounting["total_fees_usdt"] = 1.0
    elif attack == "position":
        accounting["turnover_usdt"] = 1.0
        accounting["notional_curve"] = [[ctx["candles"][0].close_time_ms, 1.0]]
    elif attack == "grid":
        accounting["equity_curve"] = list(reversed(accounting["equity_curve"]))
    elif attack == "equity":
        accounting["equity_curve"][0][1] += 1.0
    elif attack == "terminal":
        accounting["terminal_policy"] = "MARK_TO_MARKET_OPEN"
    else:
        cash[{"kind": "benchmark_kind", "vehicle": "vehicle", "seed": "seed"}[attack]] = {
            "kind": "RANDOM_MATCHED", "vehicle": "BTCUSDT_LINEAR_PERPETUAL", "seed": 1234,
        }[attack]
    p6._refresh_suite_identity(suite)
    with pytest.raises(ValueError, match="CASH canonical replay mismatch"):
        verify_benchmark_replay(ctx["run"].semantic_payload(), suite,
                                protocol=ctx["protocol"], comparison=ctx["comparison"])


def test_b07_t8_positive_constant_equity_no_activity(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    suite = ctx["suite"].to_dict()
    cash = suite["cash"]["accounting"]
    assert cash["trade_events"] == []
    assert cash["total_fees_usdt"] == cash["total_funding_usdt"] == cash["turnover_usdt"] == 0
    assert cash["equity_curve"] == [[c.close_time_ms, ctx["comparison"].initial_capital] for c in ctx["candles"]]
    verify_benchmark_replay(ctx["run"].semantic_payload(), suite,
                            protocol=ctx["protocol"], comparison=ctx["comparison"])


def test_traded_cash_passes_old_ledger_arithmetic_but_not_persisted_promotion(tmp_path: Path) -> None:
    artifacts = p6._formal_artifacts(tmp_path)
    semantic = json.loads(canonical_json(artifacts["qualification"].semantic_payload()))
    suite = semantic["benchmark_suite"]
    suite["cash"]["accounting"] = thaw_json(artifacts["run"].accounting)
    p6._refresh_suite_identity(suite)
    with pytest.raises(ValueError, match="CASH canonical replay mismatch"):
        validate_persisted_qualification_semantics(semantic, artifacts["dataset"], protocol=artifacts["protocol"])


def test_fully_rehashed_traded_cash_cannot_mutate_registry(tmp_path: Path) -> None:
    artifacts = p6._formal_artifacts(tmp_path / "base")
    artifact = json.loads(canonical_json(artifacts["qualification"].to_dict()))
    artifact["semantic_payload"]["benchmark_suite"]["cash"]["accounting"] = thaw_json(artifacts["run"].accounting)
    assert_registry_rejects_atomic(tmp_path, artifacts, artifact, "CASH canonical replay mismatch")
