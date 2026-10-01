"""Tests for TradeIntentV1, approval -> intent binding, LLM isolation, and IntentStore."""

from __future__ import annotations

import pytest
from test_live_v1_account_watch import sample_snapshot
from test_live_v1_decision_models import sample_analysis, sample_case

from btc_quant_agent.approval.store import LiveState, LiveStore
from btc_quant_agent.decision.risk import RiskCompilerV1, RiskPolicyV1
from btc_quant_agent.execution.guard import ExecutionBlocked
from btc_quant_agent.execution.intents import IntentStore, build_trade_intent

NOW = 1_700_000_000_000


def setup_approved_state(tmp_path):
    store = LiveStore(tmp_path / "live.db")
    case = sample_case(created_at_ms=NOW, observed_at_ms=NOW, expires_at_ms=NOW + 120_000)
    store.save_case(case)

    analysis = sample_analysis(case)
    store.save_analysis(analysis)

    compiler = RiskCompilerV1(RiskPolicyV1())
    proposal = compiler.compile(
        case,
        analysis,
        now_ms=NOW,
        analysis_result_hashes=(analysis.result_hash,),
        requires_manual_review=False,
    )
    store.save_proposal(proposal)

    # Transition to waiting approval
    store.transition(case.case_id, LiveState.LLM_ANALYZING, NOW)
    store.transition(case.case_id, LiveState.PLAN_READY, NOW)
    store.transition(case.case_id, LiveState.NOTIFIED, NOW)
    store.transition(case.case_id, LiveState.WAITING_APPROVAL, NOW)

    # Record valid approval
    event_id = "appr-evt-1"
    actor = "approver-alice"
    store.record_callback(
        event_id=event_id,
        action="APPROVE",
        actor=actor,
        proposal_hash=proposal.proposal_hash,
        case_hash=case.case_hash,
        now_ms=NOW,
    )

    return store, case, proposal, event_id, actor


def test_build_trade_intent_success(tmp_path):
    store, case, proposal, event_id, actor = setup_approved_state(tmp_path)
    snapshot = sample_snapshot(observed_at_ms=NOW, last_rest_at_ms=NOW)

    intent = build_trade_intent(
        live_store=store,
        account_snapshot=snapshot,
        proposal_hash=proposal.proposal_hash,
        approval_event_id=event_id,
        allowed_approvers=frozenset({actor}),
        now_ms=NOW,
    )

    intent.verify()
    assert intent.case_id == case.case_id
    assert intent.case_hash == case.case_hash
    assert intent.proposal_hash == proposal.proposal_hash
    assert intent.approval_actor == actor
    assert intent.quantity > 0
    assert intent.stop_loss == proposal.stop_loss
    assert intent.take_profit_1 == proposal.take_profit_1
    assert intent.environment == "TESTNET"


def test_llm_cannot_override_executable_parameters(tmp_path):
    store, _case, proposal, event_id, _actor = setup_approved_state(tmp_path)
    snapshot = sample_snapshot(observed_at_ms=NOW, last_rest_at_ms=NOW)

    intent = build_trade_intent(
        live_store=store,
        account_snapshot=snapshot,
        proposal_hash=proposal.proposal_hash,
        approval_event_id=event_id,
        now_ms=NOW,
    )

    # LLM or Feishu callback cannot set arbitrary executable order fields
    # Attempting to tamper with price or quantity invalidates the intent hash
    with pytest.raises(ValueError):
        object.__setattr__(intent, "quantity", 999.0)
        intent.verify()


def test_stale_approval_and_expired_proposal_blocked(tmp_path):
    store, _case, proposal, event_id, _actor = setup_approved_state(tmp_path)
    snapshot = sample_snapshot(observed_at_ms=NOW, last_rest_at_ms=NOW)

    # Call after expiry
    with pytest.raises(ExecutionBlocked, match="proposal or case has expired"):
        build_trade_intent(
            live_store=store,
            account_snapshot=snapshot,
            proposal_hash=proposal.proposal_hash,
            approval_event_id=event_id,
            now_ms=NOW + 60_001,
        )


def test_unauthorized_approver_blocked(tmp_path):
    store, _case, proposal, event_id, _actor = setup_approved_state(tmp_path)
    snapshot = sample_snapshot(observed_at_ms=NOW, last_rest_at_ms=NOW)

    with pytest.raises(ExecutionBlocked, match="not authorized"):
        build_trade_intent(
            live_store=store,
            account_snapshot=snapshot,
            proposal_hash=proposal.proposal_hash,
            approval_event_id=event_id,
            allowed_approvers=frozenset({"approver-bob"}),  # Alice is not Bob
            now_ms=NOW,
        )


def test_unreconciled_account_snapshot_blocked(tmp_path):
    store, _case, proposal, event_id, _actor = setup_approved_state(tmp_path)
    unreconciled = sample_snapshot(reconciled=False, quality="STALE")

    with pytest.raises(ExecutionBlocked, match="not reconciled or degraded"):
        build_trade_intent(
            live_store=store,
            account_snapshot=unreconciled,
            proposal_hash=proposal.proposal_hash,
            approval_event_id=event_id,
            now_ms=NOW,
        )


def test_intent_store_persistence_and_transitions(tmp_path):
    store, _case, proposal, event_id, _actor = setup_approved_state(tmp_path)
    snapshot = sample_snapshot(observed_at_ms=NOW, last_rest_at_ms=NOW)

    intent = build_trade_intent(
        live_store=store,
        account_snapshot=snapshot,
        proposal_hash=proposal.proposal_hash,
        approval_event_id=event_id,
        now_ms=NOW,
    )

    intent_store = IntentStore(tmp_path / "live.db")
    intent_store.save_intent(intent, "PENDING_VALIDATION")

    fetched = intent_store.get_intent(intent.intent_id)
    assert fetched is not None
    assert fetched.intent_hash == intent.intent_hash

    # Check query by idempotency key
    by_key = intent_store.get_intent_by_idempotency_key(intent.idempotency_key)
    assert by_key is not None
    assert by_key.intent_id == intent.intent_id

    # Update status
    intent_store.update_status(intent.intent_id, "SUBMITTED", reason="ORDER_PLACED", now_ms=NOW + 500)
    reloaded = intent_store.get_intent(intent.intent_id)
    assert reloaded is not None
