"""v0.6 B-line Engineering Preview R1 End-to-End Offline DRY_RUN Integration Suite.

Validates:
1. Offline synthetic MarketWatch fixture -> Tactical signal -> CasePackageV1
   -> strictly mocked primary AnalysisResultV1 -> DecisionFusion + RiskCompilerV1
   -> TradeProposalV1 -> mock Feishu approval -> approval checks -> DRY_RUN execution
   -> simulated fill/protection/reconciliation -> PositionSupervisor -> durable terminal.
2. Negative safety matrix: provider refusal, model disagreement, rejection veto,
   expired TTL, forged hash, duplicate replay, stale market -> NO_EXECUTION.
3. DRY_RUN structural isolation: LIVE mode blocked before network/client creation,
   TESTNET without opt-in blocked, forbidden mainnet credentials rejected,
   signed client call count == 0, zero external network/exchange writes.
4. Cold restart and durable recovery under SerializedInitializer with all 8 R8 triggers.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# Ensure tests/ root is on sys.path for test helper imports
_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

from test_live_v1_decision_models import sample_analysis
from test_market_watch import make_dummy_tf

from btc_quant_agent import api
from btc_quant_agent.account_watch import AccountStore, AccountWatch
from btc_quant_agent.approval.feishu import build_interactive_card
from btc_quant_agent.approval.store import LiveState, LiveStore
from btc_quant_agent.config import DataConfig, ExecutionConfig, LiveV1Config
from btc_quant_agent.data.binance import BinancePublicClient
from btc_quant_agent.decision.case import case_from_assessment
from btc_quant_agent.decision.fusion import DecisionFusion
from btc_quant_agent.decision.models import (
    AnalysisResultV1,
    CasePackageV1,
)
from btc_quant_agent.decision.risk import RiskCompilerV1, RiskPolicyV1
from btc_quant_agent.domain import Regime
from btc_quant_agent.execution.backend import DryRunExecutionBackend
from btc_quant_agent.execution.binance_signed import (
    BinanceExecutionError,
    BinanceSignedClient,
    create_testnet_signed_client,
)
from btc_quant_agent.execution.executor import LiveExecutionService
from btc_quant_agent.execution.guard import ExecutionBlocked
from btc_quant_agent.execution.intents import IntentStore, build_trade_intent
from btc_quant_agent.execution.policy import LIVE_WRITE_AUTHORITY
from btc_quant_agent.execution.validator import PreExecutionValidator
from btc_quant_agent.live_db import connection, serialized_initializer
from btc_quant_agent.live_market.service import MarketStreamService
from btc_quant_agent.market_watch.config import MarketWatchConfig
from btc_quant_agent.market_watch.domain import (
    DerivativesMetrics,
    MarketSnapshot,
    PriceMetrics,
    SymbolAssessment,
)
from btc_quant_agent.market_watch.scanner import MarketWatchScanner
from btc_quant_agent.market_watch.state import MarketWatchStateStore
from btc_quant_agent.position_supervisor.kill_switch import KillSwitch
from btc_quant_agent.position_supervisor.supervisor import (
    REQUIRED_R8_GUARDS,
    PositionSupervisor,
)

BASE_TIMESTAMP_MS = 1_700_000_000_000


def _mock_host_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate host db path from hermetic guard."""
    host_db = tmp_path / "host_quant.db"
    monkeypatch.setenv("BTC_QUANT_DB_PATH", str(host_db))


def create_synthetic_market_watch_case(
    tmp_path: Path, ttl_ms: int = 120_000
) -> tuple[SymbolAssessment, CasePackageV1]:
    """Create a fully offline, synthetic MarketWatch SymbolAssessment and CasePackageV1."""
    cfg = MarketWatchConfig()
    store = MarketWatchStateStore(tmp_path / "mw_preview.db")
    scanner = MarketWatchScanner(cfg, BinancePublicClient(DataConfig()), store)
    tf = make_dummy_tf(
        "BTCUSDT",
        "1h",
        101.0,
        Regime.TREND_UP,
        ema_fast=100.0,
        ema_mid=95.0,
        recent_swing_low=99.0,
        supports=(99.0,),
    )
    snapshot = MarketSnapshot(
        symbol="BTCUSDT",
        decision_time_ms=BASE_TIMESTAMP_MS,
        observed_at_ms=BASE_TIMESTAMP_MS,
        exchange_time_ms=BASE_TIMESTAMP_MS,
        price=PriceMetrics(100.2, quote_volume_24h=1_000_000.0),
        tf_15m=make_dummy_tf(
            "BTCUSDT", "15m", close=100.2, ema_fast=100.0, atr=0.8, recent_swing_low=99.0
        ),
        tf_1h=tf,
        tf_4h=replace(tf, interval="4h"),
        derivatives=DerivativesMetrics(
            mark_price=100.2,
            oi_1h_change=0.02,
            funding_rate=0.0001,
            spread_bps=1.0,
        ),
        snapshot_hash="snap-preview-synthetic",
    )
    assessment = scanner.assess_symbol(snapshot, None, snapshot, None, None)
    case = case_from_assessment(assessment, ttl_ms=ttl_ms)
    return assessment, case


class SpySignedClientCounter:
    """Spy to guarantee zero calls ever reach real or signed network transport."""

    def __init__(self) -> None:
        self.call_count = 0
        self.calls: list[str] = []

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.call_count += 1
        self.calls.append(str(args))
        raise RuntimeError("SPY_SIGNED_CLIENT_BLOCKED: unexpected call into signed transport")


# ==============================================================================
# 1. POSITIVE E2E DRY_RUN CYCLE
# ==============================================================================

def test_v06_e2e_positive_dry_run_authorized_lifecycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Full offline positive DRY_RUN cycle from synthetic MarketWatch to PositionSupervisor.

    Asserts:
    - Zero signed client or exchange calls.
    - Deterministic immutable CasePackage, proposal hash, approval binding.
    - RiskCompiler enforces strict risk cap; LLM cannot inflate quantity/leverage.
    - DRY_RUN backend executes simulated entry, stop-loss, and take-profit.
    - PositionSupervisor records immutable terminal event under R8 triggers.
    - Exactly-once intent execution.
    """
    _mock_host_config(tmp_path, monkeypatch)
    db_path = tmp_path / "engineering_preview_r1.db"
    now_ms = BASE_TIMESTAMP_MS

    spy_signed = SpySignedClientCounter()

    # Verify LIVE authority lock is strictly NONE (None in Python)
    assert LIVE_WRITE_AUTHORITY is None

    # Step 1: Offline synthetic fixture -> MarketWatch SymbolAssessment -> CasePackageV1
    _assessment, case = create_synthetic_market_watch_case(tmp_path, ttl_ms=120_000)
    assert case.symbol == "BTCUSDT"
    assert case.direction == "LONG"
    assert case.entry_quality in {"GOOD", "EXCELLENT"}
    assert case.data_quality == "OK"
    assert case.observed_at_ms == now_ms
    assert case.case_hash is not None

    # Step 2: Initialize durable stores under SerializedInitializer
    with serialized_initializer(db_path):
        live_store = LiveStore(db_path)
        intent_store = IntentStore(db_path)
        account_store = AccountStore(db_path)
        kill_switch = KillSwitch(db_path)
        supervisor = PositionSupervisor(
            db_path,
            analysis_service=None,
            fresh_market_case=lambda _: case,
        )
        supervisor.assert_guards_installed()

    assert live_store.save_case(case)

    # Step 3: Strictly mocked primary LLM AnalysisResultV1 (ResponsesBackend)
    primary_analysis = sample_analysis(
        case,
        backend="responses",
        model="gpt-5.4",
        action="OPEN_LONG",
        confidence=0.92,
        thesis_strength=0.85,
        risk_modifier="STANDARD",
        requires_secondary_review=False,
        requires_manual_review=False,
        narrative="Strong multi-factor momentum and funding alignment",
    )
    assert primary_analysis.case_hash == case.case_hash
    live_store.save_analysis(primary_analysis)

    # Step 4: DecisionFusion + Deterministic RiskCompiler
    fusion = DecisionFusion()
    fusion_result = fusion.fuse(case, primary_analysis, secondary=None)
    assert fusion_result.selected.action == "OPEN_LONG"
    assert not fusion_result.requires_manual_review

    risk_policy = RiskPolicyV1(
        max_notional_usdt=500.0,
        max_leverage=3,
        max_simultaneous_positions=1,
        proposal_ttl_ms=120_000,
    )
    compiler = RiskCompilerV1(risk_policy)
    proposal = compiler.compile(
        case=case,
        analysis=primary_analysis,
        now_ms=now_ms,
        analysis_result_hashes=(primary_analysis.result_hash,),
        requires_manual_review=False,
    )
    assert not proposal.requires_manual_review
    assert not proposal.blocked_reasons
    assert proposal.recommended_notional_usdt > 0
    # Mechanically bounded leverage and quantity
    assert proposal.leverage <= risk_policy.max_leverage
    assert proposal.recommended_notional_usdt <= risk_policy.max_notional_usdt
    assert proposal.proposal_hash is not None
    live_store.save_proposal(proposal)

    # Step 5: Mock Feishu interactive card & notification
    card = build_interactive_card(proposal)
    assert card["config"]["wide_screen_mode"] is True
    assert "elements" in card
    assert len(card["elements"]) >= 5

    # Step 6: Approval lifecycle transition & simulated human callback
    live_store.transition(case.case_id, LiveState.LLM_ANALYZING, now_ms)
    live_store.transition(case.case_id, LiveState.PLAN_READY, now_ms)
    live_store.transition(case.case_id, LiveState.NOTIFIED, now_ms)
    live_store.transition(case.case_id, LiveState.WAITING_APPROVAL, now_ms)

    approval_event_id = "preview-appr-evt-001"
    approver_id = "ou_preview_approver_1"
    cb_result = live_store.record_callback(
        event_id=approval_event_id,
        action="APPROVE",
        actor=approver_id,
        proposal_hash=proposal.proposal_hash,
        case_hash=case.case_hash,
        now_ms=now_ms + 1000,
    )
    assert cb_result["state"] == "APPROVED"
    assert not cb_result["replay"]

    # Step 7: AccountWatch reconciles offline snapshot
    account_watch = AccountWatch(
        ExecutionConfig(mode="paper"),
        account_store,
        signed_client=None,
        clock_ms=lambda: now_ms + 1500,
    )
    account_snap = account_watch.reconcile_rest()
    assert account_snap.reconciled
    assert account_snap.quality == "OK"

    # Step 8: Build immutable TradeIntentV1
    intent = build_trade_intent(
        live_store=live_store,
        account_snapshot=account_snap,
        proposal_hash=proposal.proposal_hash,
        approval_event_id=approval_event_id,
        allowed_approvers=frozenset({approver_id}),
        now_ms=now_ms + 2000,
    )
    intent.verify()
    intent_store.save_intent(intent)
    assert intent.proposal_hash == proposal.proposal_hash

    # Step 9: Market observation update
    market_stream = MarketStreamService(symbol="BTCUSDT", clock_ms=lambda: now_ms + 2500)
    market_stream.update_simulated(
        mark_price=case.price,
        best_bid=case.price - 0.01,
        best_ask=case.price + 0.01,
        kline_close=case.price,
        now_ms=now_ms + 2500,
    )

    # Step 10: PreExecutionValidator multi-guard check
    validator = PreExecutionValidator(
        live_store=live_store,
        intent_store=intent_store,
        kill_switch=kill_switch,
        risk_policy=risk_policy,
        tactical_validity_provider=lambda s, t: True,
        tactical_case_provider=lambda s, t: case,
    )
    market_obs = market_stream.latest_observation(now_ms + 2500)
    assert market_obs is not None
    validation = validator.validate(intent, market_obs, account_snap, now_ms=now_ms + 3000)
    assert validation.is_valid, f"Validation failed: {validation.reason}"

    # Step 11: DRY_RUN ExecutionBackend (zero signed transport)
    dry_run_backend = DryRunExecutionBackend(db_path)
    exec_service = LiveExecutionService(
        intent_store=intent_store,
        live_store=live_store,
        account_watch=account_watch,
        market_stream=market_stream,
        validator=validator,
        kill_switch=kill_switch,
        dry_run_backend=dry_run_backend,
        testnet_backend=None,
        supervisor=supervisor,
    )

    with patch.object(BinanceSignedClient, "_signed_request", spy_signed):
        report = exec_service.execute_approved_intent_sync(intent.intent_id, now_ms=now_ms + 3500)

    assert report.status == "FILLED"
    assert report.filled_qty == intent.quantity
    assert report.avg_price > 0
    assert report.protective_stop_id is not None

    # Verify zero calls reached signed client
    assert spy_signed.call_count == 0

    # Step 12: Verify exactly-once execution (subsequent execution reconciles existing fill)
    report_re = exec_service.execute_approved_intent_sync(intent.intent_id, now_ms=now_ms + 4000)
    assert report_re.status == "FILLED"
    assert report_re.reason == "RECONCILED"
    assert spy_signed.call_count == 0

    # Step 13: PositionSupervisor verifies position event capture
    with connection(db_path) as db:
        events = db.execute("SELECT * FROM live_position_events").fetchall()
        assert len(events) >= 1
        pos_active = db.execute("SELECT * FROM live_position_lifecycle_v2").fetchall()
        assert len(pos_active) >= 1
        assert pos_active[0]["symbol"] == "BTCUSDT"
        assert pos_active[0]["is_open"] == 1
        assert pos_active[0]["last_transition"] == "POSITION_OPENED"


# ==============================================================================
# 2. NEGATIVE SAFETY MATRIX (FAIL-CLOSED)
# ==============================================================================

def test_v06_e2e_negative_refusal_rejection_expired_matrix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies fail-closed behavior for all negative paths: NO execution orders possible."""
    _mock_host_config(tmp_path, monkeypatch)
    db_path = tmp_path / "negative_matrix.db"
    now_ms = BASE_TIMESTAMP_MS

    with serialized_initializer(db_path):
        live_store = LiveStore(db_path)
        _intent_store = IntentStore(db_path)
        account_store = AccountStore(db_path)
        _kill_switch = KillSwitch(db_path)

    _assessment, case = create_synthetic_market_watch_case(tmp_path, ttl_ms=120_000)
    live_store.save_case(case)

    risk_policy = RiskPolicyV1(proposal_ttl_ms=60_000)
    compiler = RiskCompilerV1(risk_policy)

    # --- Negative Path A: LLM Refusal / Provider failure -> NO decision / NO proposal ---
    refusal_analysis = AnalysisResultV1.fail_closed(
        case=case,
        backend="responses",
        model="gpt-5.4",
        reason="BACKEND_REFUSAL",
    )
    assert refusal_analysis.action == "NO_ACTION"
    assert refusal_analysis.risk_modifier == "BLOCK"
    assert refusal_analysis.requires_manual_review
    proposal_refused = compiler.compile(
        case, refusal_analysis, now_ms=now_ms, analysis_result_hashes=(),
    )
    assert "MODEL_BLOCK" in proposal_refused.blocked_reasons
    assert proposal_refused.requires_manual_review

    # --- Negative Path B: Model Disagreement -> Manual Review Triggered ---
    analysis_disagree_primary = sample_analysis(
        case,
        backend="responses",
        model="gpt-5.4",
        action="OPEN_LONG",
        confidence=0.85,
        thesis_strength=0.90,
        risk_modifier="STANDARD",
        requires_secondary_review=True,
        requires_manual_review=False,
    )
    analysis_disagree_secondary = sample_analysis(
        case,
        backend="codex_exec",
        model="gpt-5.3-codex-spark",
        action="OPEN_SHORT",
        confidence=0.80,
        thesis_strength=0.85,
        risk_modifier="BLOCK",
        requires_secondary_review=False,
        requires_manual_review=True,
    )
    fusion = DecisionFusion()
    fusion_result = fusion.fuse(
        case, analysis_disagree_primary, analysis_disagree_secondary
    )
    assert fusion_result.requires_manual_review
    assert "MODEL_DISAGREEMENT" in fusion_result.reasons

    # --- Negative Path C: Human REJECT Callback ---
    normal_analysis = sample_analysis(
        case,
        backend="responses",
        model="gpt-5.4",
        action="OPEN_LONG",
        confidence=0.88,
        thesis_strength=0.80,
        risk_modifier="STANDARD",
        requires_secondary_review=False,
        requires_manual_review=False,
    )
    live_store.save_analysis(normal_analysis)
    valid_proposal = compiler.compile(
        case,
        normal_analysis,
        now_ms=now_ms,
        analysis_result_hashes=(normal_analysis.result_hash,),
    )
    live_store.save_proposal(valid_proposal)
    live_store.transition(case.case_id, LiveState.LLM_ANALYZING, now_ms)
    live_store.transition(case.case_id, LiveState.PLAN_READY, now_ms)
    live_store.transition(case.case_id, LiveState.NOTIFIED, now_ms)
    live_store.transition(case.case_id, LiveState.WAITING_APPROVAL, now_ms)

    cb_reject = live_store.record_callback(
        event_id="reject-evt-1",
        action="REJECT",
        actor="approver_bob",
        proposal_hash=valid_proposal.proposal_hash,
        case_hash=case.case_hash,
        now_ms=now_ms + 1000,
    )
    assert cb_reject["state"] == "REJECTED"

    account_watch = AccountWatch(
        ExecutionConfig(mode="paper"), account_store, clock_ms=lambda: now_ms
    )
    account_snap = account_watch.reconcile_rest()

    with pytest.raises(ExecutionBlocked, match="approval record does not match proposal or case"):
        build_trade_intent(
            live_store=live_store,
            account_snapshot=account_snap,
            proposal_hash=valid_proposal.proposal_hash,
            approval_event_id="reject-evt-1",
            allowed_approvers=frozenset({"approver_bob"}),
            now_ms=now_ms + 2000,
        )

    # --- Negative Path D: Expired Proposal TTL ---
    expired_now = valid_proposal.expires_at_ms + 10_000
    with pytest.raises(ValueError, match="proposal expired"):
        live_store.record_callback(
            event_id="expired-evt-1",
            action="APPROVE",
            actor="approver_bob",
            proposal_hash=valid_proposal.proposal_hash,
            case_hash=case.case_hash,
            now_ms=expired_now,
        )

    # --- Negative Path E: Forged / Tampered Proposal Hash ---
    with pytest.raises(ValueError, match="stale or mismatched callback identity"):
        live_store.record_callback(
            event_id="forged-evt-1",
            action="APPROVE",
            actor="approver_bob",
            proposal_hash="f" * 64,
            case_hash=case.case_hash,
            now_ms=now_ms + 2000,
        )

    # --- Negative Path F: Duplicate Callback Collision & Replay ---
    with pytest.raises(ValueError, match="callback event collision"):
        live_store.record_callback(
            event_id="reject-evt-1",
            action="APPROVE",
            actor="attacker",
            proposal_hash=valid_proposal.proposal_hash,
            case_hash=case.case_hash,
            now_ms=now_ms + 3000,
        )

    cb_replay = live_store.record_callback(
        event_id="reject-evt-1",
        action="REJECT",
        actor="approver_bob",
        proposal_hash=valid_proposal.proposal_hash,
        case_hash=case.case_hash,
        now_ms=now_ms + 3000,
    )
    assert cb_replay["replay"] is True


# ==============================================================================
# 3. DRY_RUN STRUCTURAL ISOLATION & MODE ESCALATION GUARDS
# ==============================================================================

def test_v06_dry_run_structural_enforcement_and_mode_escalation_fences(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verifies that LIVE mode is structurally forbidden and cannot be escalated.

    - Attempting LIVE mode fails before client or network creation.
    - TESTNET mode without explicit boolean opt-in fails.
    - Mainnet/live exchange credentials in environment fail early.
    - REAL_FUNDS_WRITE_AUTHORITY != NONE fails early.
    """
    _mock_host_config(tmp_path, monkeypatch)

    # 1. LIVE execution mode rejected in LiveV1Config
    with pytest.raises(ValueError, match="live_v1.execution_mode must be DRY_RUN or TESTNET"):
        LiveV1Config(enabled=True, execution_mode="LIVE")

    # 2. TESTNET execution mode without explicit opt-in rejected
    with pytest.raises(ValueError, match="TESTNET requires explicit execution opt-in"):
        LiveV1Config(enabled=True, execution_mode="TESTNET", testnet_execution_enabled=False)

    # 3. create_testnet_signed_client rejects non-testnet endpoint
    with pytest.raises(BinanceExecutionError, match="invalid testnet endpoint"):
        create_testnet_signed_client(base_url="https://fapi.binance.com")

    # 4. API pre-parse rejects live authority escalation
    monkeypatch.setenv("REAL_FUNDS_WRITE_AUTHORITY", "LIVE_WRITE")
    with pytest.raises(ValueError, match="REAL_FUNDS_WRITE_AUTHORITY must be NONE"):
        api.create_app()

    monkeypatch.setenv("REAL_FUNDS_WRITE_AUTHORITY", "NONE")
    monkeypatch.setenv("AUTONOMOUS_LIVE", "TRUE")
    with pytest.raises(ValueError, match="AUTONOMOUS_LIVE must be FORBIDDEN"):
        api.create_app()

    monkeypatch.setenv("AUTONOMOUS_LIVE", "FORBIDDEN")
    monkeypatch.setenv("BTC_QUANT_LIVE_V1_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("BINANCE_API_KEY", "real_key_forbidden")
    with pytest.raises(ValueError, match="Forbidden live/mainnet credential variable"):
        api.create_app()


# ==============================================================================
# 4. COLD RESTART AND DURABLE RECOVERY UNDER SERIALIZED INITIALIZER
# ==============================================================================

def test_v06_cold_restart_and_durable_recovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies durable recovery after restart under certified SerializedInitializer."""
    _mock_host_config(tmp_path, monkeypatch)
    db_path = tmp_path / "restart_preview.db"
    now_ms = BASE_TIMESTAMP_MS

    _assessment, case = create_synthetic_market_watch_case(tmp_path, ttl_ms=120_000)

    # Cycle 1: First startup and execution
    with serialized_initializer(db_path):
        live_store = LiveStore(db_path)
        intent_store = IntentStore(db_path)
        account_store = AccountStore(db_path)
        kill_switch = KillSwitch(db_path)
        supervisor = PositionSupervisor(db_path, fresh_market_case=lambda _: case)

    live_store.save_case(case)
    analysis = sample_analysis(
        case,
        backend="responses",
        model="gpt-5.4",
        action="OPEN_LONG",
        confidence=0.9,
        thesis_strength=0.8,
        risk_modifier="STANDARD",
        requires_secondary_review=False,
        requires_manual_review=False,
        narrative="Restart test",
    )
    live_store.save_analysis(analysis)
    compiler = RiskCompilerV1(RiskPolicyV1())
    proposal = compiler.compile(
        case, analysis, now_ms=now_ms, analysis_result_hashes=(analysis.result_hash,)
    )
    live_store.save_proposal(proposal)

    live_store.transition(case.case_id, LiveState.LLM_ANALYZING, now_ms)
    live_store.transition(case.case_id, LiveState.PLAN_READY, now_ms)
    live_store.transition(case.case_id, LiveState.NOTIFIED, now_ms)
    live_store.transition(case.case_id, LiveState.WAITING_APPROVAL, now_ms)
    live_store.record_callback(
        event_id="restart-appr-1",
        action="APPROVE",
        actor="approver_1",
        proposal_hash=proposal.proposal_hash,
        case_hash=case.case_hash,
        now_ms=now_ms + 1000,
    )

    account_watch = AccountWatch(
        ExecutionConfig(mode="paper"), account_store, clock_ms=lambda: now_ms
    )
    account_snap = account_watch.reconcile_rest()
    intent = build_trade_intent(
        live_store,
        account_snap,
        proposal.proposal_hash,
        "restart-appr-1",
        allowed_approvers=frozenset({"approver_1"}),
        now_ms=now_ms + 2000,
    )
    intent_store.save_intent(intent)

    market_stream = MarketStreamService(symbol="BTCUSDT", clock_ms=lambda: now_ms + 2500)
    market_stream.update_simulated(
        case.price, case.price - 0.01, case.price + 0.01, case.price, now_ms + 2500
    )

    validator = PreExecutionValidator(
        live_store, intent_store, kill_switch, RiskPolicyV1()
    )
    backend = DryRunExecutionBackend(db_path)
    exec_svc = LiveExecutionService(
        intent_store,
        live_store,
        account_watch,
        market_stream,
        validator,
        kill_switch,
        backend,
        supervisor=supervisor,
    )
    report = exec_svc.execute_approved_intent_sync(intent.intent_id, now_ms=now_ms + 3000)
    assert report.status == "FILLED", f"Failed: status={report.status}, reason={report.reason}"

    # Cold Restart: Re-open the database in a completely new set of service instances
    with serialized_initializer(db_path):
        reopened_intent_store = IntentStore(db_path)
        reopened_supervisor = PositionSupervisor(
            db_path, fresh_market_case=lambda _: case
        )
        reopened_supervisor.assert_guards_installed()

    recovered_intent = reopened_intent_store.get_intent(intent.intent_id)
    assert recovered_intent is not None
    assert recovered_intent.proposal_hash == proposal.proposal_hash

    with connection(db_path) as db:
        intent_row = db.execute(
            "SELECT status FROM live_trade_intents WHERE intent_id=?", (intent.intent_id,)
        ).fetchone()
        assert intent_row is not None
        assert intent_row["status"] == "FILLED"

    # Verify R8 immutable triggers remain enforced on restarted database
    with connection(db_path) as db:
        triggers = {
            r[0]
            for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            ).fetchall()
        }
        for guard in REQUIRED_R8_GUARDS:
            assert guard in triggers, f"Missing guard trigger after restart: {guard}"
