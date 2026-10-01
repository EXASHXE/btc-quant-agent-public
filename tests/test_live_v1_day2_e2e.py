"""Day-2 full deterministic E2E integration and adversarial safety test suite.

Validates operational path:
AccountSnapshot
  -> approved TradeIntent
  -> PreExecutionValidator
  -> DRY_RUN / TESTNET ExecutionBackend
  -> order state / fill / protective order
  -> PositionSupervisor
  -> material position event
  -> PositionCase
  -> existing AnalysisBackend
  -> Feishu review
"""

from __future__ import annotations

import asyncio

from test_live_v1_decision_models import sample_analysis, sample_case

from btc_quant_agent.account_watch import AccountStore, AccountWatch
from btc_quant_agent.approval.store import LiveState, LiveStore
from btc_quant_agent.config import ExecutionConfig
from btc_quant_agent.decision.models import CasePackageV1
from btc_quant_agent.decision.risk import RiskCompilerV1, RiskPolicyV1
from btc_quant_agent.execution.backend import DryRunExecutionBackend
from btc_quant_agent.execution.executor import LiveExecutionService
from btc_quant_agent.execution.intents import IntentStore, build_trade_intent
from btc_quant_agent.execution.validator import PreExecutionValidator
from btc_quant_agent.live_market.service import MarketStreamService
from btc_quant_agent.position_supervisor.kill_switch import KillSwitch
from btc_quant_agent.position_supervisor.supervisor import (
    PositionSupervisor,
)

NOW = 1_700_000_000_000


def test_day2_full_operational_e2e_cycle(tmp_path):
    db_path = tmp_path / "live.db"

    # 1. Setup shared durable stores
    live_store = LiveStore(db_path)
    intent_store = IntentStore(db_path)
    account_store = AccountStore(db_path)
    kill_switch = KillSwitch(db_path)

    # 2. Case generation and analysis
    case = sample_case(
        case_id="case-day2-1",
        created_at_ms=NOW,
        observed_at_ms=NOW,
        expires_at_ms=NOW + 300_000,
        price=100.0,
        entry_low=99.0,
        entry_high=101.0,
        stop_loss=90.0,
        take_profit_1=110.0,
    )
    assert live_store.save_case(case)

    analysis = sample_analysis(case)
    live_store.save_analysis(analysis)

    risk_policy = RiskPolicyV1(proposal_ttl_ms=300_000)
    compiler = RiskCompilerV1(risk_policy)
    proposal = compiler.compile(
        case,
        analysis,
        now_ms=NOW,
        analysis_result_hashes=(analysis.result_hash,),
        requires_manual_review=False,
    )
    live_store.save_proposal(proposal)

    # 3. Transitions and Approval
    live_store.transition(case.case_id, LiveState.LLM_ANALYZING, NOW)
    live_store.transition(case.case_id, LiveState.PLAN_READY, NOW)
    live_store.transition(case.case_id, LiveState.NOTIFIED, NOW)
    live_store.transition(case.case_id, LiveState.WAITING_APPROVAL, NOW)

    approval_event_id = "appr-day2-001"
    approver = "approver-alice"
    cb_result = live_store.record_callback(
        event_id=approval_event_id,
        action="APPROVE",
        actor=approver,
        proposal_hash=proposal.proposal_hash,
        case_hash=case.case_hash,
        now_ms=NOW,
    )
    assert cb_result["state"] == "APPROVED"
    assert not cb_result["replay"]

    # 4. AccountWatch generates fresh AccountSnapshotV1
    exec_cfg = ExecutionConfig(mode="paper")
    account_watch = AccountWatch(exec_cfg, account_store, clock_ms=lambda: NOW)
    account_snap = account_watch.reconcile_rest()
    assert account_snap.reconciled
    assert account_snap.quality == "OK"

    # 5. Build immutable TradeIntentV1
    intent = build_trade_intent(
        live_store=live_store,
        account_snapshot=account_snap,
        proposal_hash=proposal.proposal_hash,
        approval_event_id=approval_event_id,
        allowed_approvers=frozenset({approver}),
        now_ms=NOW,
    )
    intent.verify()
    intent_store.save_intent(intent)

    # 6. Live Market Stream observation
    market_stream = MarketStreamService(symbol="BTCUSDT", clock_ms=lambda: NOW)
    market_stream.update_simulated(
        mark_price=intent.price,
        best_bid=intent.price - 0.02,
        best_ask=intent.price + 0.02,
        kline_close=intent.price,
        now_ms=NOW,
    )

    # 7. Position Supervisor with analysis spy
    analyzed_position_cases: list[CasePackageV1] = []

    class MockAnalysisService:
        async def analyze_case(self, pos_case: CasePackageV1) -> None:
            analyzed_position_cases.append(pos_case)

    supervisor = PositionSupervisor(
        db_path,
        analysis_service=MockAnalysisService(),
        fresh_market_case=lambda _: case,
    )

    # 8. Execution Coordinator
    validator = PreExecutionValidator(
        live_store=live_store,
        intent_store=intent_store,
        kill_switch=kill_switch,
        risk_policy=risk_policy,
    )
    dry_run_backend = DryRunExecutionBackend(db_path)

    exec_service = LiveExecutionService(
        intent_store=intent_store,
        live_store=live_store,
        account_watch=account_watch,
        market_stream=market_stream,
        validator=validator,
        kill_switch=kill_switch,
        dry_run_backend=dry_run_backend,
        supervisor=supervisor,
        clock_ms=lambda: NOW,
    )

    # 9. Execute approved intent
    report = asyncio.run(exec_service.execute_approved_intent(intent.intent_id, NOW))
    assert report.status == "FILLED"
    assert report.filled_qty == intent.quantity
    assert report.protective_stop_id is not None

    # Check updated intent status in DB
    updated_intent = intent_store.get_intent(intent.intent_id)
    assert updated_intent is not None

    # 10. Position supervisor generated material event (POSITION_OPENED) during execution
    from btc_quant_agent.live_db import connection
    from btc_quant_agent.position_supervisor.models import PositionEventV1
    with connection(db_path) as db:
        row = db.execute("SELECT payload FROM live_position_events WHERE trigger='POSITION_OPENED'").fetchone()
    assert row is not None
    opened_event = PositionEventV1.model_validate_json(row["payload"])
    assert opened_event.trigger == "POSITION_OPENED"

    # 11. Coordinator fill automatically orchestrated PositionCase to AnalysisService end-to-end!
    assert len(analyzed_position_cases) == 1
    pos_case = analyzed_position_cases[0]
    pos_case.verify()
    assert pos_case.trigger == "POSITION_OPENED"
    assert pos_case.source == "POSITION_SUPERVISOR"
    assert pos_case.base_case_hash == case.case_hash
    assert pos_case.position_event_hash == opened_event.event_hash
    assert pos_case.evidence_id == case.evidence_id
    assert pos_case.signal_identity == case.signal_identity
    assert pos_case.case_hash != case.case_hash

    # 12. Replay does not duplicate PositionCase analysis
    report_replay = asyncio.run(exec_service.execute_approved_intent(intent.intent_id, NOW + 1000))
    assert report_replay.status == "FILLED"
    assert len(analyzed_position_cases) == 1


def report_to_observation(report, intent, account_snap, market_obs, now_ms):
    from btc_quant_agent.position_supervisor.models import PositionObservationV1
    return PositionObservationV1.build(
        account_snapshot_hash=account_snap.snapshot_hash,
        market_source_hash=market_obs.observation_hash,
        symbol=intent.symbol,
        observed_at_ms=now_ms,
        quantity=report.filled_qty if intent.side == "BUY" else -report.filled_qty,
        previous_quantity=0.0,
        entry_price=report.avg_price,
        mark_price=market_obs.mark_price,
        unrealized_pnl_usdt=0.0,
        realized_pnl_usdt=0.0,
        margin_usdt=(report.filled_qty * report.avg_price) / intent.leverage,
        stop_price=intent.stop_loss,
        take_profit_price=intent.take_profit_1,
        funding_rate=0.0,
        oi_change_pct=0.0,
        volatility_percentile=0.2,
        spread_bps=market_obs.spread_bps,
        tactical_regime="BULLISH" if intent.side == "BUY" else "BEARISH",
        grid_boundary_breached=False,
        order_status=report.status,
        order_filled_quantity=report.filled_qty,
        order_observed_at_ms=now_ms,
        evidence_id="0" * 64,
        signal_identity="signal-e2e",
        add_opportunity=False,
    )


def test_adversarial_restart_does_not_resubmit_or_duplicate(tmp_path):
    db_path = tmp_path / "live.db"
    live_store = LiveStore(db_path)
    intent_store = IntentStore(db_path)
    account_store = AccountStore(db_path)
    kill_switch = KillSwitch(db_path)

    case = sample_case(created_at_ms=NOW, observed_at_ms=NOW, expires_at_ms=NOW + 300_000)
    live_store.save_case(case)
    analysis = sample_analysis(case)
    live_store.save_analysis(analysis)

    risk_policy = RiskPolicyV1(proposal_ttl_ms=300_000)
    compiler = RiskCompilerV1(risk_policy)
    proposal = compiler.compile(case, analysis, now_ms=NOW, requires_manual_review=False)
    live_store.save_proposal(proposal)

    live_store.transition(case.case_id, LiveState.LLM_ANALYZING, NOW)
    live_store.transition(case.case_id, LiveState.PLAN_READY, NOW)
    live_store.transition(case.case_id, LiveState.NOTIFIED, NOW)
    live_store.transition(case.case_id, LiveState.WAITING_APPROVAL, NOW)

    live_store.record_callback("appr-1", "APPROVE", "alice", proposal.proposal_hash, case.case_hash, NOW)

    account_watch = AccountWatch(ExecutionConfig(mode="paper"), account_store, clock_ms=lambda: NOW)
    snap = account_watch.reconcile_rest()

    intent = build_trade_intent(live_store, snap, proposal.proposal_hash, "appr-1", now_ms=NOW)
    intent_store.save_intent(intent)

    market_stream = MarketStreamService(clock_ms=lambda: NOW)
    market_stream.update_simulated(intent.price, intent.price - 0.01, intent.price + 0.01, intent.price, NOW)

    validator = PreExecutionValidator(live_store, intent_store, kill_switch, risk_policy=risk_policy)
    backend = DryRunExecutionBackend(db_path)
    service = LiveExecutionService(intent_store, live_store, account_watch, market_stream, validator, kill_switch, backend)

    # First execution succeeds
    rep1 = asyncio.run(service.execute_approved_intent(intent.intent_id, NOW))
    assert rep1.status == "FILLED"

    # Simulate process restart by instantiating new service instances on the same SQLite database
    restarted_intent_store = IntentStore(db_path)
    restarted_backend = DryRunExecutionBackend(db_path)
    restarted_service = LiveExecutionService(
        restarted_intent_store, live_store, account_watch, market_stream, validator, kill_switch, restarted_backend
    )

    # Resubmitting the same intent ID recovers existing state without creating duplicate orders
    rep2 = asyncio.run(restarted_service.execute_approved_intent(intent.intent_id, NOW + 1000))
    assert rep2.order_id == rep1.order_id
    assert rep2.reason == "IDEMPOTENT_REPLAY"


def test_r1_05_coordinator_fill_source_bound_and_no_neutral_masquerade(tmp_path):
    db_path = tmp_path / "live.db"
    live_store = LiveStore(db_path)
    intent_store = IntentStore(db_path)
    account_store = AccountStore(db_path)
    kill_switch = KillSwitch(db_path)

    case = sample_case(
        case_id="case-r1-05",
        created_at_ms=NOW,
        observed_at_ms=NOW,
        expires_at_ms=NOW + 300_000,
        evidence_id="a" * 64,
        signal_identity="sig-real-source-456",
    )
    live_store.save_case(case)
    analysis = sample_analysis(case)
    live_store.save_analysis(analysis)

    risk_policy = RiskPolicyV1(proposal_ttl_ms=300_000)
    compiler = RiskCompilerV1(risk_policy)
    proposal = compiler.compile(case, analysis, now_ms=NOW, requires_manual_review=False)
    live_store.save_proposal(proposal)

    live_store.transition(case.case_id, LiveState.LLM_ANALYZING, NOW)
    live_store.transition(case.case_id, LiveState.PLAN_READY, NOW)
    live_store.transition(case.case_id, LiveState.NOTIFIED, NOW)
    live_store.transition(case.case_id, LiveState.WAITING_APPROVAL, NOW)
    live_store.record_callback("appr-r1-05", "APPROVE", "alice", proposal.proposal_hash, case.case_hash, NOW)

    account_watch = AccountWatch(ExecutionConfig(mode="paper"), account_store, clock_ms=lambda: NOW)
    snap = account_watch.reconcile_rest()

    intent = build_trade_intent(live_store, snap, proposal.proposal_hash, "appr-r1-05", now_ms=NOW)
    intent_store.save_intent(intent)

    market_stream = MarketStreamService(clock_ms=lambda: NOW)
    market_stream.update_simulated(intent.price, intent.price - 0.01, intent.price + 0.01, intent.price, NOW)

    analyzed_cases: list[CasePackageV1] = []

    class MockAnalysisService:
        async def analyze_case(self, pos_case: CasePackageV1) -> None:
            analyzed_cases.append(pos_case)

    supervisor = PositionSupervisor(
        db_path,
        analysis_service=MockAnalysisService(),
        fresh_market_case=lambda _: case,
    )
    validator = PreExecutionValidator(live_store, intent_store, kill_switch, risk_policy=risk_policy)
    backend = DryRunExecutionBackend(db_path)

    # Supply explicit verified source providers for tactical and market feeds
    service = LiveExecutionService(
        intent_store,
        live_store,
        account_watch,
        market_stream,
        validator,
        kill_switch,
        backend,
        supervisor=supervisor,
        tactical_regime_provider=lambda _sym: "BULLISH",
        funding_rate_provider=lambda _sym: 0.0001,
        oi_change_provider=lambda _sym: 0.05,
        volatility_provider=lambda _sym: 0.40,
    )

    report = asyncio.run(service.execute_approved_intent(intent.intent_id, NOW))
    assert report.status == "FILLED"

    # Verify that the coordinator built PositionObservationV1 bound to actual sources
    assert len(analyzed_cases) == 1
    analyzed = analyzed_cases[0]
    assert analyzed.trigger == "POSITION_OPENED"
    # Evidence ID and signal identity are strictly from the real case, NOT "0"*64 or "live-signal"
    assert analyzed.evidence_id == "a" * 64
    assert analyzed.signal_identity == "sig-real-source-456"
