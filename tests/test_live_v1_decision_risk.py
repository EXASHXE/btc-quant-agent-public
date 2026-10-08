import pytest
from test_live_v1_decision_models import sample_analysis, sample_case

from btc_quant_agent.decision.models import AccountContextV1
from btc_quant_agent.decision.risk import RiskCompilerV1, RiskPolicyV1


def compile_proposal(case=None, policy=None, **analysis):
    case = case or sample_case()
    return RiskCompilerV1(policy or RiskPolicyV1()).compile(
        case, sample_analysis(case, **analysis), now_ms=2000,
    )


def test_risk_modifier_cannot_increase_risk():
    standard = compile_proposal()
    reduced = compile_proposal(risk_modifier="REDUCE")
    blocked = compile_proposal(risk_modifier="BLOCK")
    assert 0 < reduced.risk_budget_usdt < standard.risk_budget_usdt
    assert reduced.recommended_notional_usdt <= standard.recommended_notional_usdt
    assert blocked.recommended_notional_usdt == 0
    assert standard.max_loss_usdt <= standard.risk_budget_usdt
    assert standard.account_authority == "DRY_RUN"


def test_caps_notional_and_margin():
    policy = RiskPolicyV1(max_symbol_exposure_pct=0.01, max_portfolio_exposure_pct=0.02,
                          max_margin_utilization=0.01)
    proposal = compile_proposal(policy=policy)
    assert proposal.recommended_notional_usdt <= 10
    assert proposal.margin_usdt <= 10
    assert proposal.leverage == policy.configured_leverage


def test_stale_case_rejected():
    case = sample_case(expires_at_ms=1500)
    with pytest.raises(ValueError, match="STALE"):
        compile_proposal(case)


def test_add_requires_distinct_evidence_and_signal():
    proposal = compile_proposal(action="ADD")
    assert "ADD_FRESH_EVIDENCE_REQUIRED" in proposal.blocked_reasons
    account = AccountContextV1(equity_usdt=1000.0, symbol_exposure_usdt=0.0,
        portfolio_exposure_usdt=0.0, margin_used_usdt=0.0, simultaneous_positions=1,
        daily_loss_usdt=0.0, drawdown_pct=0.0, observed_at_ms=1000,
        prior_signal_identities=("signal-1",), prior_evidence_ids=("a" * 64,))
    same = compile_proposal(sample_case(account=account), action="ADD")
    assert same.recommended_notional_usdt == 0
    fresh = compile_proposal(sample_case(account=account, signal_identity="signal-2",
                                        evidence_id="b" * 64), action="ADD")
    assert fresh.recommended_notional_usdt > 0
    assert fresh.requires_manual_review


@pytest.mark.parametrize("case_args,reason", [
    ({"spread_bps":20.0}, "SPREAD_CAP"),
    ({"liquidity_usdt":None}, "LIQUIDITY_MISSING"),
    ({"data_quality":"DEGRADED"}, "DATA_QUALITY"),
    ({"stop_loss":102.0}, "INVALID_GEOMETRY"),
    ({"direction":"SHORT"}, "STRATEGY_DATA_DISAGREEMENT"),
])
def test_risk_guards(case_args, reason):
    proposal = compile_proposal(sample_case(**case_args))
    assert proposal.recommended_notional_usdt == 0
    assert reason in proposal.blocked_reasons


@pytest.mark.parametrize("loss,drawdown,ceiling", [
    (29.9, 0.0, 0.1), (0.0, 0.0999, 0.112), (30.0, 0.0, 0.0), (0.0, 0.1, 0.0),
])
def test_remaining_loss_limits_cap_new_trade(loss, drawdown, ceiling):
    account = AccountContextV1(equity_usdt=1000.0, symbol_exposure_usdt=0.0,
        portfolio_exposure_usdt=0.0, margin_used_usdt=0.0, simultaneous_positions=0,
        daily_loss_usdt=loss, drawdown_pct=drawdown, observed_at_ms=1000)
    proposal = compile_proposal(sample_case(account=account))
    assert proposal.max_loss_usdt <= ceiling + 1e-9
    assert proposal.risk_budget_usdt <= ceiling + 1e-9
