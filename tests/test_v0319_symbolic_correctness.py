from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path

import pytest

from btc_quant_agent.data.historical_provenance import HistoricalDataRole
from btc_quant_agent.symbolic_alpha.dsl import Formula, FormulaToken, Operator, TokenKind
from btc_quant_agent.symbolic_alpha.evaluate import (
    EvaluationFirewall,
    block_hours_to_events,
    evaluate_formula,
    forward_returns,
)
from btc_quant_agent.symbolic_alpha.gates import (
    CandidateGateConfig,
    FormulaGateEvidence,
    GateStatus,
    SandboxGateEvidence,
    evaluate_candidate_gates,
)
from btc_quant_agent.symbolic_alpha.proposal import (
    ProposalConstraints,
    RandomGrammarProposalEngine,
)
from btc_quant_agent.symbolic_alpha.registry import (
    FeatureDefinition,
    FormulaRegistryEntry,
    formula_entry,
    write_registry,
)
from btc_quant_agent.symbolic_alpha.sandbox import (
    ProvisionalSignal,
    ReplayBar,
    SandboxDecision,
    SettledFunding,
    replay_signal,
)
from btc_quant_agent.symbolic_alpha.search import run_discovery_search
from btc_quant_agent.symbolic_alpha.vm import FormulaVM

ROOT = Path(__file__).parents[1]
PROTOCOL = ROOT / "configs/research/v0.3.19_official_derivatives_symbolic_protocol.json"


def _feature(name: str) -> FormulaToken:
    return FormulaToken(TokenKind.FEATURE, name)


def _op(name: Operator, parameter: int | None = None) -> FormulaToken:
    return FormulaToken(TokenKind.OPERATOR, name.value, parameter)


def _gate() -> CandidateGateConfig:
    return CandidateGateConfig.from_dict(json.loads(PROTOCOL.read_text())["candidate_gate"])


def _formula_evidence(**changes: object) -> FormulaGateEvidence:
    baseline = FormulaGateEvidence(
        1000, 500, 500, 0.5, 0.001, 0.001, 0.001, 0.0001, 0.0001, 4, 4, True, 0.5
    )
    return replace(baseline, **changes)


def _sandbox_evidence(**changes: object) -> SandboxGateEvidence:
    baseline = SandboxGateEvidence(50, 1.2, 5.0, 5, 4, True, True, True, 1.0)
    return replace(baseline, **changes)


def test_bootstrap_hours_convert_to_events_without_unit_ambiguity() -> None:
    assert block_hours_to_events(168, 8) == 21
    assert block_hours_to_events(169, 8) == 22
    with pytest.raises(ValueError, match="positive"):
        block_hours_to_events(0, 8)
    formula = Formula((_feature("x"),))
    metrics = evaluate_formula(
        formula,
        {"x": [1.0] * 80},
        [0.01] * 80,
        range(80),
        cost_rate=0,
        bootstrap_seed=1,
        bootstrap_resamples=10,
        bootstrap_block_hours=168,
        sample_step_hours=8,
    )
    assert metrics.bootstrap_block_hours == 168
    assert metrics.bootstrap_block_events == 21


def test_unknown_candidate_gate_fails_closed_and_all_known_keys_consumed() -> None:
    raw = json.loads(PROTOCOL.read_text())["candidate_gate"]
    with pytest.raises(ValueError, match="unknown"):
        CandidateGateConfig.from_dict({**raw, "surprise_gate": 1})
    audit = evaluate_candidate_gates(_gate(), _formula_evidence(), _sandbox_evidence())
    assert audit.passed_all
    assert set(audit.consumed_protocol_keys) == set(raw)
    assert len(audit.consumed_protocol_keys) == len(set(audit.consumed_protocol_keys))


def test_upstream_failure_marks_sandbox_gates_na_with_frozen_reason() -> None:
    audit = evaluate_candidate_gates(_gate(), _formula_evidence(validation_events=1), None)
    assert not audit.passed_all
    sandbox = [item for item in audit.results if item.key == "minimum_net_profit_factor"]
    assert sandbox[0].status == GateStatus.NOT_APPLICABLE
    assert sandbox[0].reason == "UPSTREAM_FORMULA_GATE_FAILED"


def test_missing_sandbox_after_formula_pass_fails() -> None:
    audit = evaluate_candidate_gates(_gate(), _formula_evidence(), None)
    assert not audit.passed_all
    assert any(item.reason == "MISSING_REQUIRED_SANDBOX_EVIDENCE" for item in audit.results)


def _signal(direction: SandboxDecision) -> ProvisionalSignal:
    short = direction == SandboxDecision.SHORT
    return ProvisionalSignal(
        signal_id=direction.value,
        decision_timestamp_ms=100,
        decision=direction,
        formula_hash="hash",
        source=HistoricalDataRole.OFFICIAL_HISTORICAL_TIMESTAMPED.value,
        planned_entry_reference=100,
        stop_price=110 if short else 90,
        take_profit_price=90 if short else 110,
        size=2,
    )


def test_sandbox_cost_identity_actual_entry_and_long_short_symmetry() -> None:
    long = replay_signal(
        _signal(SandboxDecision.LONG),
        [ReplayBar(101, 160, 100, 110, 90.1, 105)],
        fee_rate=0.0004,
        slippage_rate=0.0002,
        funding_events=(SettledFunding(150, 0.0001),),
    )
    short = replay_signal(
        _signal(SandboxDecision.SHORT),
        [ReplayBar(101, 160, 100, 109.9, 90, 95)],
        fee_rate=0.0004,
        slippage_rate=0.0002,
        funding_events=(SettledFunding(150, 0.0001),),
    )
    assert long and short
    assert long.entry_time_ms == 101 and short.entry_time_ms == 101
    assert long.planned_entry_reference == 100
    assert long.executed_entry_price > long.raw_entry_price
    assert short.executed_entry_price < short.raw_entry_price
    assert long.net_r == pytest.approx(
        long.gross_r - long.fees_r - long.slippage_r - long.funding_r
    )
    assert short.net_r == pytest.approx(
        short.gross_r - short.fees_r - short.slippage_r - short.funding_r
    )
    assert long.funding_r > 0 and short.funding_r < 0
    assert long.pnl_quote == pytest.approx(long.net_r * abs(long.executed_entry_price - 90) * 2)


@pytest.mark.parametrize(
    ("direction", "open_price"),
    [(SandboxDecision.LONG, 85), (SandboxDecision.SHORT, 115)],
)
def test_gap_through_stop_is_closed_at_first_future_open(
    direction: SandboxDecision, open_price: float
) -> None:
    trade = replay_signal(
        _signal(direction),
        [ReplayBar(100, 100, 999, 999, 1, 999), ReplayBar(101, 160, open_price, 120, 80, 100)],
        fee_rate=0,
        slippage_rate=0.0002,
    )
    assert trade
    assert trade.entry_time_ms == 101
    assert trade.exit_time_ms == 101
    assert trade.exit_reason == "GAP_THROUGH_STOP_AT_FIRST_OPEN"


def test_new_feature_constraint_and_reward_budget_accounting() -> None:
    constraints = ProposalConstraints(
        maximum_tokens=9,
        maximum_lookback=20,
        windows=(4,),
        operators=(Operator.ADD, Operator.SUB, Operator.SIGN),
        required_features=frozenset({"new"}),
    )
    engine = RandomGrammarProposalEngine()
    formulas, accounting = engine.propose(25, {"old": 1, "new": 1}, 319, constraints)
    assert all("new" in formula.input_features for formula in formulas)
    assert accounting["old_only_rejections"] > 0
    search = run_discovery_search(
        engine,
        25,
        {"old": 1, "new": 1},
        319,
        constraints,
        {"old": [1.0, -1.0] * 30, "new": [-1.0, 1.0] * 30},
        [0.01, -0.01] * 30,
        range(60),
        0.0025,
    )
    assert search.accounting["formula_evaluations"] == 25
    assert search.ranked
    assert len(search.audit_dict()["ranked"]) == len(search.ranked)


def test_registry_entry_and_fail_closed_runtime_eligibility(tmp_path: Path) -> None:
    formula = Formula((_feature("new"), _op(Operator.SIGN)))
    definitions = {
        "new": FeatureDefinition("new", "OFFICIAL_HISTORICAL_TIMESTAMPED", 0, "closed hour")
    }
    entry = formula_entry(
        formula,
        definitions,
        formula_id="f1",
        proposal_engine="RANDOM_GRAMMAR_SEARCH",
        search_run_id="run",
        search_seed=1,
        search_budget=1,
        discovery_window="d",
        validation_window="v",
        pseudo_forward_window="p",
        metrics_by_fold={},
        correlation_to_existing_candidates=None,
        status="DISCOVERY_ONLY",
        research_eligibility=False,
    )
    path = tmp_path / "registry.json"
    write_registry(path, [entry])
    assert json.loads(path.read_text())["formulas"][0]["runtime_eligibility"] is False
    with pytest.raises(ValueError, match="cannot be Runtime"):
        FormulaRegistryEntry(**{**entry.as_dict(), "runtime_eligibility": True})


def test_vm_operator_paths_and_firewall_rejection() -> None:
    features = {"x": [1.0, 2.0, 3.0, 4.0], "y": [4.0, 3.0, 2.0, 1.0]}
    formulas = [
        Formula((_feature("x"), _op(Operator.NEG))),
        Formula((_feature("x"), _op(Operator.ABS))),
        Formula((_feature("x"), _feature("y"), _op(Operator.MIN))),
        Formula((_feature("x"), _feature("y"), _op(Operator.MAX))),
        Formula((_feature("x"), _op(Operator.EMA_N, 2))),
        Formula((_feature("x"), _op(Operator.ROLL_STD_N, 2))),
        Formula((_feature("x"), _op(Operator.DECAY_N, 2))),
        Formula(
            (
                _feature("x"),
                FormulaToken(TokenKind.CONSTANT, 1.5),
                FormulaToken(TokenKind.CONSTANT, 2.5),
                _op(Operator.CLIP),
            )
        ),
    ]
    assert all(FormulaVM().execute(formula, features).failure is None for formula in formulas)
    assert forward_returns([1.0, 2.0, 4.0], 1)[:2] == pytest.approx([math.log(2), math.log(2)])
    firewall = EvaluationFirewall()
    firewall.freeze_top_k([formulas[0]])
    with pytest.raises(PermissionError, match="outside"):
        firewall.authorize_pseudo_forward(formulas[1])
