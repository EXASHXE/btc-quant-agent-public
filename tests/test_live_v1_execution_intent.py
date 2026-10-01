"""Tests for TradeIntentV1, approval -> intent binding, LLM isolation, and IntentStore."""

from __future__ import annotations

import pytest
from test_live_v1_account_watch import sample_snapshot
from test_live_v1_decision_models import sample_analysis, sample_case

from btc_quant_agent.approval.store import LiveState, LiveStore
from btc_quant_agent.decision.risk import RiskCompilerV1, RiskPolicyV1
from btc_quant_agent.execution.guard import ExecutionBlocked
from btc_quant_agent.execution.intents import IntentStore, TradeIntentV1, build_trade_intent
from btc_quant_agent.live_db import connection

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


def test_r1_01_same_approval_materialized_twice_same_identity_and_client_order_id(tmp_path):
    store, _case, proposal, event_id, _actor = setup_approved_state(tmp_path)
    snapshot = sample_snapshot(observed_at_ms=NOW, last_rest_at_ms=NOW)

    intent1 = build_trade_intent(
        live_store=store,
        account_snapshot=snapshot,
        proposal_hash=proposal.proposal_hash,
        approval_event_id=event_id,
        now_ms=NOW,
    )
    intent2 = build_trade_intent(
        live_store=store,
        account_snapshot=snapshot,
        proposal_hash=proposal.proposal_hash,
        approval_event_id=event_id,
        now_ms=NOW,
    )

    assert intent1.intent_id == intent2.intent_id
    assert intent1.client_order_id == intent2.client_order_id
    assert intent1.idempotency_key == intent2.idempotency_key
    assert intent1.intent_hash == intent2.intent_hash


def test_r1_01_same_approval_with_changed_account_snapshot_no_second_executable_intent(tmp_path):
    store, _case, proposal, event_id, _actor = setup_approved_state(tmp_path)
    snapshot1 = sample_snapshot(observed_at_ms=NOW, last_rest_at_ms=NOW, equity_usdt=1000.0)
    intent_store = IntentStore(tmp_path / "live.db")

    intent1 = build_trade_intent(
        live_store=store,
        account_snapshot=snapshot1,
        proposal_hash=proposal.proposal_hash,
        approval_event_id=event_id,
        now_ms=NOW,
        intent_store=intent_store,
    )
    intent_store.save_intent(intent1)

    # Newer account snapshot arrives with different equity and timestamp
    snapshot2 = sample_snapshot(observed_at_ms=NOW + 10_000, last_rest_at_ms=NOW + 10_000, equity_usdt=1050.0)
    intent2 = build_trade_intent(
        live_store=store,
        account_snapshot=snapshot2,
        proposal_hash=proposal.proposal_hash,
        approval_event_id=event_id,
        now_ms=NOW + 10_000,
        intent_store=intent_store,
    )

    # Replay of the same approval must return existing intent and not create second executable identity
    assert intent2.intent_id == intent1.intent_id
    assert intent2.client_order_id == intent1.client_order_id
    assert intent2.account_snapshot_hash == intent1.account_snapshot_hash


def test_r1_01_concurrent_materialization_produces_one_row(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    store, _case, proposal, event_id, _actor = setup_approved_state(tmp_path)
    snapshot = sample_snapshot(observed_at_ms=NOW, last_rest_at_ms=NOW)
    intent_store = IntentStore(tmp_path / "live.db")

    def materialize_and_save():
        intent = build_trade_intent(
            live_store=store,
            account_snapshot=snapshot,
            proposal_hash=proposal.proposal_hash,
            approval_event_id=event_id,
            now_ms=NOW,
            intent_store=intent_store,
        )
        intent_store.save_intent(intent)
        return intent.intent_id

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(materialize_and_save) for _ in range(8)]
        results = [f.result() for f in futures]

    assert len(set(results)) == 1

    with connection(tmp_path / "live.db") as db:
        count = db.execute("SELECT COUNT(*) FROM live_trade_intents").fetchone()[0]
    assert count == 1


def test_r1_01_divergent_payload_under_same_approval_fails_closed(tmp_path):
    store, _case, proposal, event_id, _actor = setup_approved_state(tmp_path)
    snapshot = sample_snapshot(observed_at_ms=NOW, last_rest_at_ms=NOW)
    intent_store = IntentStore(tmp_path / "live.db")

    intent1 = build_trade_intent(
        live_store=store,
        account_snapshot=snapshot,
        proposal_hash=proposal.proposal_hash,
        approval_event_id=event_id,
        now_ms=NOW,
    )
    intent_store.save_intent(intent1)

    # Construct divergent intent with tampered price under the same approval_event_id
    divergent = intent1.model_copy(update={"price": 99999.0, "intent_hash": ""})
    divergent_built = TradeIntentV1.build(**divergent.model_dump(exclude={"intent_hash"}))

    with pytest.raises(ExecutionBlocked, match="divergent intent for approval event"):
        intent_store.save_intent(divergent_built)
