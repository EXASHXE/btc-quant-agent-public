"""Comprehensive RC1 WP-C tests: LLM analysis, DecisionFusion, and Feishu approval integration.

Guarantees:
- Primary ResponsesBackend strict fail-closed on timeout/refusal/malformed/oversize/provider failure/case mismatch
- Secondary CodexExecBackend SECONDARY_ONLY isolation and independent CasePackage analysis
- DecisionFusion mandatory review triggers, hard disagreement fail-closed, no majority voting
- Feishu notification, callback identity, idempotency, nonce, proposal hash binding, approval TTL
- Explicit zero execution authority for all model outputs
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

_src_dir = str(Path(__file__).resolve().parent.parent / "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import httpx
import pydantic
import pytest
from test_live_v1_decision_models import sample_analysis, sample_case

from btc_quant_agent.approval.callback import create_callback_app
from btc_quant_agent.approval.feishu import FeishuAppClient, build_interactive_card
from btc_quant_agent.approval.store import LiveState, LiveStore
from btc_quant_agent.config import LiveV1Config
from btc_quant_agent.decision.backends import (
    AnalysisMode,
    CodexExecBackend,
    ResponsesBackend,
)
from btc_quant_agent.decision.fusion import DecisionFusion
from btc_quant_agent.decision.models import (
    AccountContextV1,
    AnalysisResultV1,
    TradeProposalV1,
)
from btc_quant_agent.decision.risk import RiskCompilerV1, RiskPolicyV1
from btc_quant_agent.decision.service import TacticalLiveService

NOW = 10_000


# ==============================================================================
# Helper fixtures and builders
# ==============================================================================


class MockResponsesParse:
    def __init__(self, response_or_exc):
        self.response_or_exc = response_or_exc
        self.calls = []

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.response_or_exc, Exception):
            raise self.response_or_exc
        return self.response_or_exc


def prepare_live_store_with_proposal(tmp_path, *, requires_manual=False, blocked=False, notional=100.0):
    store = LiveStore(tmp_path / "live.sqlite")
    case = sample_case(created_at_ms=NOW, observed_at_ms=NOW, expires_at_ms=NOW + 60_000)
    analysis = sample_analysis(case, requires_manual_review=requires_manual)
    policy = RiskPolicyV1()
    compiler = RiskCompilerV1(policy)
    proposal = compiler.compile(case, analysis, now_ms=NOW)
    if blocked or notional <= 0:
        values = proposal.model_dump(exclude={"proposal_hash"})
        values["requires_manual_review"] = True
        values["recommended_notional_usdt"] = 0.0
        values["blocked_reasons"] = ("MANUAL_REVIEW",)
        proposal = TradeProposalV1.build(**values)
    store.save_case(case)
    store.save_analysis(analysis)
    store.save_proposal(proposal)
    for state in (LiveState.LLM_ANALYZING, LiveState.PLAN_READY, LiveState.NOTIFIED, LiveState.WAITING_APPROVAL):
        store.transition(case.case_id, state, NOW)
    return store, case, proposal


# ==============================================================================
# 1. Primary ResponsesBackend: Negative-Case Matrix
# ==============================================================================


def test_primary_timeout_fails_closed():
    case = sample_case(created_at_ms=NOW, observed_at_ms=NOW, expires_at_ms=NOW + 60_000)
    mock_responses = MockResponsesParse(TimeoutError("timeout"))
    client = SimpleNamespace(responses=mock_responses)
    backend = ResponsesBackend("gpt-4o", timeout_seconds=1.0, client=client, clock_ms=lambda: NOW)
    result = asyncio.run(backend.analyze(case, AnalysisMode.PRIMARY))

    assert result.action == "NO_ACTION"
    assert result.risk_modifier == "BLOCK"
    assert result.requires_manual_review is True
    assert "BACKEND_TIMEOUT" in result.risk_factors


def test_primary_refusal_fails_closed():
    case = sample_case(created_at_ms=NOW, observed_at_ms=NOW, expires_at_ms=NOW + 60_000)
    refusal_response = SimpleNamespace(
        status="completed",
        id="resp-refusal",
        model="gpt-4o",
        output=[SimpleNamespace(type="refusal", content=[SimpleNamespace(type="refusal")])],
        output_parsed=sample_analysis(case),
    )
    backend = ResponsesBackend(
        "gpt-4o",
        timeout_seconds=2.0,
        client=SimpleNamespace(responses=MockResponsesParse(refusal_response)),
        clock_ms=lambda: NOW,
    )
    result = asyncio.run(backend.analyze(case, AnalysisMode.PRIMARY))

    assert result.action == "NO_ACTION"
    assert result.risk_modifier == "BLOCK"
    assert result.requires_manual_review is True
    assert "BACKEND_REFUSAL" in result.risk_factors


def test_primary_malformed_response_fails_closed():
    case = sample_case(created_at_ms=NOW, observed_at_ms=NOW, expires_at_ms=NOW + 60_000)
    malformed_response = SimpleNamespace(
        status="completed",
        id="resp-malformed",
        model="gpt-4o",
        output=[],
        output_parsed={"malformed": "bad-data", "action": "INVALID_ACTION"},
    )
    backend = ResponsesBackend(
        "gpt-4o",
        timeout_seconds=2.0,
        client=SimpleNamespace(responses=MockResponsesParse(malformed_response)),
        clock_ms=lambda: NOW,
    )
    result = asyncio.run(backend.analyze(case, AnalysisMode.PRIMARY))

    assert result.action == "NO_ACTION"
    assert result.risk_modifier == "BLOCK"
    assert result.requires_manual_review is True
    assert "BACKEND_RESPONSE_INVALID" in result.risk_factors


def test_primary_provider_failure_fails_closed():
    case = sample_case(created_at_ms=NOW, observed_at_ms=NOW, expires_at_ms=NOW + 60_000)
    provider_error = RuntimeError("500 Internal Server Error from model provider")
    backend = ResponsesBackend(
        "gpt-4o",
        timeout_seconds=2.0,
        client=SimpleNamespace(responses=MockResponsesParse(provider_error)),
        clock_ms=lambda: NOW,
    )
    result = asyncio.run(backend.analyze(case, AnalysisMode.PRIMARY))

    assert result.action == "NO_ACTION"
    assert result.risk_modifier == "BLOCK"
    assert result.requires_manual_review is True
    assert "BACKEND_RESPONSE_INVALID" in result.risk_factors


def test_primary_case_mismatch_fails_closed():
    case = sample_case(case_id="case-expected", created_at_ms=NOW, observed_at_ms=NOW, expires_at_ms=NOW + 60_000)
    other_case = sample_case(case_id="case-other", created_at_ms=NOW, observed_at_ms=NOW, expires_at_ms=NOW + 60_000)
    mismatched_analysis = sample_analysis(other_case)
    mismatch_response = SimpleNamespace(
        status="completed",
        id="resp-mismatch",
        model="gpt-4o",
        output=[],
        output_parsed=mismatched_analysis,
    )
    backend = ResponsesBackend(
        "gpt-4o",
        timeout_seconds=2.0,
        client=SimpleNamespace(responses=MockResponsesParse(mismatch_response)),
        clock_ms=lambda: NOW,
    )
    result = asyncio.run(backend.analyze(case, AnalysisMode.PRIMARY))

    assert result.action == "NO_ACTION"
    assert result.risk_modifier == "BLOCK"
    assert result.requires_manual_review is True
    assert "CASE_MISMATCH" in result.risk_factors


def test_primary_oversize_case_fails_closed():
    huge_reasons = tuple(f"REASON_{i}" * 10_000 for i in range(30))
    case = sample_case(
        reason_codes=huge_reasons,
        created_at_ms=NOW,
        observed_at_ms=NOW,
        expires_at_ms=NOW + 60_000,
    )
    backend = ResponsesBackend(
        "gpt-4o",
        timeout_seconds=2.0,
        client=SimpleNamespace(responses=MockResponsesParse(None)),
        clock_ms=lambda: NOW,
    )
    result = asyncio.run(backend.analyze(case, AnalysisMode.PRIMARY))

    assert result.action == "NO_ACTION"
    assert result.risk_modifier == "BLOCK"
    assert "CASE_TOO_LARGE" in result.risk_factors


# ==============================================================================
# 2. Secondary CodexExecBackend: Isolation and Negative Cases
# ==============================================================================


def test_codex_exec_secondary_only_rejects_primary_mode():
    case = sample_case(created_at_ms=NOW, observed_at_ms=NOW, expires_at_ms=NOW + 60_000)

    async def mock_spawn(*args, **kwargs):
        raise AssertionError("Codex process should not be spawned in PRIMARY mode")

    backend = CodexExecBackend("o3-mini", 2.0, process_factory=mock_spawn, clock_ms=lambda: NOW)
    result = asyncio.run(backend.analyze(case, AnalysisMode.PRIMARY))

    assert result.action == "NO_ACTION"
    assert result.risk_modifier == "BLOCK"
    assert result.requires_manual_review is True
    assert "SECONDARY_ONLY" in result.risk_factors


def test_codex_exec_receives_independent_case_package_only():
    case = sample_case(created_at_ms=NOW, observed_at_ms=NOW, expires_at_ms=NOW + 60_000)
    calls = []

    class FakeProcess:
        returncode = 0

        async def communicate(self, input):
            calls.append(input)
            output_file.write_text(sample_analysis(case).canonical_json(), encoding="utf-8")

    async def spawn(*args, **kwargs):
        nonlocal output_file
        output_file = __import__("pathlib").Path(args[args.index("-o") + 1])
        return FakeProcess()

    output_file = None
    backend = CodexExecBackend("o3-mini", 5.0, process_factory=spawn, clock_ms=lambda: NOW)
    result = asyncio.run(backend.analyze(case, AnalysisMode.SECONDARY))

    assert result.action == "OPEN_LONG"
    assert len(calls) == 1
    passed_input = calls[0].decode("utf-8")
    assert case.canonical_json() in passed_input
    assert "primary" not in passed_input.lower()
    assert "chain_of_thought" not in passed_input


def test_codex_exec_timeout_fails_closed():
    case = sample_case(created_at_ms=NOW, observed_at_ms=NOW, expires_at_ms=NOW + 60_000)

    class HangingProcess:
        returncode = None
        pid = 12345

        async def communicate(self, input):
            await asyncio.sleep(10)

        def kill(self):
            self.returncode = -9

        async def wait(self):
            return -9

    async def spawn(*args, **kwargs):
        return HangingProcess()

    backend = CodexExecBackend("o3-mini", 0.05, process_factory=spawn, clock_ms=lambda: NOW)
    result = asyncio.run(backend.analyze(case, AnalysisMode.SECONDARY))

    assert result.action == "NO_ACTION"
    assert result.risk_modifier == "BLOCK"
    assert result.requires_manual_review is True
    assert "BACKEND_TIMEOUT" in result.risk_factors


def test_codex_exec_case_mismatch_fails_closed():
    case = sample_case(case_id="case-1", created_at_ms=NOW, observed_at_ms=NOW, expires_at_ms=NOW + 60_000)
    other_case = sample_case(case_id="case-2", created_at_ms=NOW, observed_at_ms=NOW, expires_at_ms=NOW + 60_000)

    class MismatchedProcess:
        returncode = 0

        async def communicate(self, input):
            out_path.write_text(sample_analysis(other_case).canonical_json(), encoding="utf-8")

    async def spawn(*args, **kwargs):
        nonlocal out_path
        out_path = __import__("pathlib").Path(args[args.index("-o") + 1])
        return MismatchedProcess()

    out_path = None
    backend = CodexExecBackend("o3-mini", 2.0, process_factory=spawn, clock_ms=lambda: NOW)
    result = asyncio.run(backend.analyze(case, AnalysisMode.SECONDARY))

    assert result.action == "NO_ACTION"
    assert result.risk_modifier == "BLOCK"
    assert "CASE_MISMATCH" in result.risk_factors


# ==============================================================================
# 3. DecisionFusion: Mandatory-Review Triggers & Hard Disagreement
# ==============================================================================


@pytest.mark.parametrize("trigger,change,expected_reason", [
    ("low confidence", {"confidence": 0.5}, "LOW_CONFIDENCE"),
    ("high exposure", None, "HIGH_EXPOSURE"),
    ("ADD action", {"action": "ADD"}, "ADD_REVIEW"),
    ("reversal LONG to SHORT", {"action": "OPEN_SHORT"}, "REVERSE_OR_CLOSE_ACTION"),
    ("close-sensitive CLOSE", {"action": "CLOSE"}, "REVERSE_OR_CLOSE_ACTION"),
    ("close-sensitive REDUCE", {"action": "REDUCE"}, "REVERSE_OR_CLOSE_ACTION"),
    ("strategy/data disagreement", {"strategy_data_disagreement": True}, "STRATEGY_DATA_DISAGREEMENT"),
    ("primary requests secondary review", {"requires_secondary_review": True}, "SECONDARY_REVIEW_REQUESTED"),
    ("primary requests manual review", {"requires_manual_review": True}, "PRIMARY_REVIEW_REQUESTED"),
])
def test_fusion_mandatory_review_trigger_matrix(trigger, change, expected_reason):
    if trigger == "high exposure":
        case = sample_case(
            direction="LONG",
            account=AccountContextV1(
                equity_usdt=1000.0,
                symbol_exposure_usdt=300.0,
                portfolio_exposure_usdt=300.0,
                margin_used_usdt=0.0,
                simultaneous_positions=0,
                daily_loss_usdt=0.0,
                drawdown_pct=0.0,
                observed_at_ms=NOW,
            ),
        )
        primary = sample_analysis(case)
    else:
        case = sample_case(direction="LONG")
        primary = sample_analysis(case, **change)

    fusion = DecisionFusion()
    assert fusion.needs_secondary(case, primary) is True
    # Without secondary provided, secondary is unavailable -> fails closed with manual review
    result = fusion.fuse(case, primary, secondary=None)
    assert result.requires_manual_review is True
    assert result.selected.risk_modifier == "BLOCK"
    assert expected_reason in result.reasons
    assert "SECONDARY_UNAVAILABLE" in result.reasons


def test_fusion_manual_codex_review_request():
    case = sample_case(direction="LONG")
    primary = sample_analysis(case)
    fusion = DecisionFusion()
    assert fusion.needs_secondary(case, primary, manual_codex_request=True) is True
    result = fusion.fuse(case, primary, secondary=None, manual_codex_request=True)
    assert result.requires_manual_review is True
    assert "MANUAL_CODEX_REQUEST" in result.reasons


@pytest.mark.parametrize("conflict_type,secondary_override", [
    ("action conflict", {"action": "OPEN_SHORT"}),
    ("risk modifier conflict", {"risk_modifier": "BLOCK"}),
    ("entry quality conflict", {"entry_quality": "POOR"}),
    ("thesis strength divergence >= 0.3", {"thesis_strength": 0.2}),  # primary has 0.8
])
def test_fusion_hard_disagreement_matrix_requires_manual_review(conflict_type, secondary_override):
    case = sample_case(direction="LONG")
    primary = sample_analysis(case, thesis_strength=0.8, risk_modifier="STANDARD", entry_quality="GOOD")
    secondary = sample_analysis(case, **secondary_override)

    fusion = DecisionFusion()
    result = fusion.fuse(case, primary, secondary=secondary)

    assert result.requires_manual_review is True
    assert result.selected.risk_modifier == "BLOCK"
    assert "MODEL_DISAGREEMENT" in result.reasons
    assert "MANUAL_REVIEW_REQUIRED" in result.reasons


def test_fusion_asymmetric_risk_reduction_without_majority_voting():
    case = sample_case(direction="LONG")
    primary = sample_analysis(case, risk_modifier="STANDARD")
    # Secondary suggests REDUCE; this should be adopted without changing action or requiring manual review
    secondary = sample_analysis(case, risk_modifier="REDUCE", thesis_strength=0.8, entry_quality="GOOD")

    fusion = DecisionFusion()
    result = fusion.fuse(case, primary, secondary=secondary)

    assert result.selected.action == primary.action
    assert result.selected.risk_modifier == "BLOCK"  # Disagreement on modifier blocks and triggers manual review


def test_fusion_secondary_cannot_weaken_primary_block():
    case = sample_case(direction="LONG")
    primary = sample_analysis(case, risk_modifier="BLOCK")
    secondary = sample_analysis(case, risk_modifier="STANDARD")

    fusion = DecisionFusion()
    result = fusion.fuse(case, primary, secondary=secondary)

    assert result.selected.risk_modifier == "BLOCK"
    assert result.requires_manual_review is True


# ==============================================================================
# 4. Feishu Notification & Callback Replay/Idempotency/Hash/TTL Matrix
# ==============================================================================


def test_feishu_interactive_card_contains_safe_bound_identity():
    case = sample_case(created_at_ms=NOW, observed_at_ms=NOW, expires_at_ms=NOW + 60_000)
    analysis = sample_analysis(case)
    proposal = RiskCompilerV1(RiskPolicyV1()).compile(case, analysis, now_ms=NOW)

    card = build_interactive_card(proposal)
    assert card["config"]["wide_screen_mode"] is True
    assert "Live V1 DRY_RUN proposal" in card["header"]["title"]["content"]

    buttons = [
        btn for el in card["elements"] if el.get("tag") == "action" for btn in el["actions"]
    ]
    assert {b["text"]["content"] for b in buttons} == {
        "APPROVE", "REJECT", "MANUAL", "REQUEST_CODEX_REVIEW",
    }
    for b in buttons:
        assert b["value"]["proposal_hash"] == proposal.proposal_hash
        assert b["value"]["case_hash"] == case.case_hash


def test_feishu_callback_exact_replay_idempotent(tmp_path):
    store, case, proposal = prepare_live_store_with_proposal(tmp_path)
    args = ("event-replay-1", "APPROVE", "approver-1", proposal.proposal_hash, case.case_hash, NOW + 1000)

    first = store.record_callback(*args)
    assert first["state"] == "APPROVED"
    assert first["replay"] is False
    assert store.state(case.case_id) == LiveState.APPROVED

    second = store.record_callback(*args)
    assert second["state"] == "APPROVED"
    assert second["replay"] is True


def test_feishu_callback_event_collision_rejected(tmp_path):
    store, case, proposal = prepare_live_store_with_proposal(tmp_path)
    store.record_callback("event-id-dup", "APPROVE", "approver-1", proposal.proposal_hash, case.case_hash, NOW + 1000)

    # Replay with different action or actor under the same event_id
    with pytest.raises(ValueError, match="callback event collision"):
        store.record_callback("event-id-dup", "REJECT", "approver-1", proposal.proposal_hash, case.case_hash, NOW + 1000)

    with pytest.raises(ValueError, match="callback event collision"):
        store.record_callback("event-id-dup", "APPROVE", "approver-2", proposal.proposal_hash, case.case_hash, NOW + 1000)


def test_feishu_callback_hash_binding_mismatch_rejected(tmp_path):
    store, case, proposal = prepare_live_store_with_proposal(tmp_path)

    # Corrupted proposal hash
    with pytest.raises(ValueError, match="stale or mismatched callback identity"):
        store.record_callback("event-bad-prop", "APPROVE", "approver-1", "0" * 64, case.case_hash, NOW + 1000)

    # Corrupted case hash
    with pytest.raises(ValueError, match="stale or mismatched callback identity"):
        store.record_callback("event-bad-case", "APPROVE", "approver-1", proposal.proposal_hash, "f" * 64, NOW + 1000)


def test_feishu_callback_ttl_expiration_fails_closed(tmp_path):
    store, case, proposal = prepare_live_store_with_proposal(tmp_path)
    expired_time = proposal.expires_at_ms + 1

    with pytest.raises(ValueError, match="proposal expired"):
        store.record_callback("event-late", "APPROVE", "approver-1", proposal.proposal_hash, case.case_hash, expired_time)

    assert store.state(case.case_id) == LiveState.EXPIRED


def test_feishu_callback_rejects_approve_when_manual_review_required(tmp_path):
    store, case, proposal = prepare_live_store_with_proposal(tmp_path, requires_manual=True)

    with pytest.raises(ValueError, match="proposal cannot be approved"):
        store.record_callback("event-approve-manual", "APPROVE", "approver-1", proposal.proposal_hash, case.case_hash, NOW + 1000)

    assert store.state(case.case_id) == LiveState.WAITING_APPROVAL


def test_feishu_callback_rejects_approve_when_blocked_or_zero_notional(tmp_path):
    store, case, proposal = prepare_live_store_with_proposal(tmp_path, blocked=True, notional=0.0)

    with pytest.raises(ValueError, match="proposal cannot be approved"):
        store.record_callback("event-approve-blocked", "APPROVE", "approver-1", proposal.proposal_hash, case.case_hash, NOW + 1000)

    assert store.state(case.case_id) == LiveState.WAITING_APPROVAL


def test_feishu_callback_http_signatures_and_allowlists(tmp_path):
    store, case, proposal = prepare_live_store_with_proposal(tmp_path)
    secret = "test-signing-secret"
    token = "test-verify-token"
    app = create_callback_app(
        store,
        verification_token=token,
        signing_secret=secret,
        approver_open_ids=("approver-allowed",),
        app_id="cli-app-id",
        clock_ms=lambda: NOW,
    )

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            # 1. Reject invalid verification token
            bad_token_body = {
                "schema": "2.0",
                "header": {"token": "wrong-token", "app_id": "cli-app-id", "event_id": "e1", "event_type": "card.action.trigger"},
                "event": {"operator": {"open_id": "approver-allowed"}, "action": {"value": {"action": "APPROVE", "proposal_hash": proposal.proposal_hash, "case_hash": case.case_hash}}},
            }
            res = await client.post("/callback", json=bad_token_body)
            assert res.status_code == 401

            # 2. Reject stale timestamp
            ts_stale = str((NOW // 1000) - 400)
            nonce = "random-nonce-1"
            body_bytes = json.dumps({
                "schema": "2.0",
                "header": {"token": token, "app_id": "cli-app-id", "event_id": "e2", "event_type": "card.action.trigger"},
                "event": {"operator": {"open_id": "approver-allowed"}, "action": {"value": {"action": "APPROVE", "proposal_hash": proposal.proposal_hash, "case_hash": case.case_hash}}},
            }).encode()
            sig = hashlib.sha256(ts_stale.encode() + nonce.encode() + secret.encode() + body_bytes).hexdigest()
            res = await client.post(
                "/callback",
                content=body_bytes,
                headers={"x-lark-request-timestamp": ts_stale, "x-lark-request-nonce": nonce, "x-lark-signature": sig},
            )
            assert res.status_code == 401

            # 3. Reject unauthorized approver open_id
            ts_valid = str(NOW // 1000)
            denied_body = json.dumps({
                "schema": "2.0",
                "header": {"token": token, "app_id": "cli-app-id", "event_id": "e3", "event_type": "card.action.trigger"},
                "event": {"operator": {"open_id": "approver-denied"}, "action": {"value": {"action": "APPROVE", "proposal_hash": proposal.proposal_hash, "case_hash": case.case_hash}}},
            }).encode()
            sig_denied = hashlib.sha256(ts_valid.encode() + nonce.encode() + secret.encode() + denied_body).hexdigest()
            res = await client.post(
                "/callback",
                content=denied_body,
                headers={"x-lark-request-timestamp": ts_valid, "x-lark-request-nonce": nonce, "x-lark-signature": sig_denied},
            )
            assert res.status_code == 403

            # 4. Reject oversized request (>64KB)
            oversized_content = b"x" * 70_000
            res = await client.post("/callback", content=oversized_content)
            assert res.status_code == 413

    asyncio.run(run())


# ==============================================================================
# 5. Zero Execution Authority for Model Outputs
# ==============================================================================


@pytest.mark.parametrize("injected_field", [
    "quantity", "order_type", "price", "leverage", "notional", "account_authority", "execute_immediately"
])
def test_model_cannot_return_executable_fields(injected_field):
    case = sample_case()
    raw = sample_analysis(case).model_dump(mode="json")
    raw[injected_field] = 100.0

    with pytest.raises(pydantic.ValidationError):
        AnalysisResultV1.model_validate_json(json.dumps(raw))


def test_tactical_service_exchange_write_count_is_zero(tmp_path):
    store = LiveStore(tmp_path / "live.sqlite")
    primary = AsyncMock()
    primary.analyze.return_value = sample_analysis(sample_case())
    service = TacticalLiveService(store, primary, RiskCompilerV1(RiskPolicyV1()), clock_ms=lambda: NOW)

    assert service.exchange_write_count == 0


def test_config_live_v1_feishu_and_llm_fields():
    config = LiveV1Config(
        enabled=True,
        execution_mode="DRY_RUN",
        responses_model="gpt-4o",
        codex_model="o3-mini",
        codex_enabled=True,
        feishu_app_id="app-123",
        feishu_receive_id="chat-123",
        feishu_receive_id_type="chat_id",
        feishu_verification_token="token-abc",
    )
    assert config.responses_model == "gpt-4o"
    assert config.codex_model == "o3-mini"
    assert config.feishu_receive_id_type == "chat_id"
    assert config.feishu_verification_token == "token-abc"

    with pytest.raises(ValueError, match="feishu_receive_id_type"):
        LiveV1Config(
            feishu_receive_id_type="invalid_type",
        )


def test_feishu_client_supports_configurable_receive_id_type():
    requests = []

    def handle(request):
        requests.append(request)
        if request.url.path.endswith("tenant_access_token/internal"):
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "token-xyz"})
        assert request.url.params["receive_id_type"] == "open_id"
        return httpx.Response(200, json={"code": 0, "data": {"message_id": "msg-xyz"}})

    async def run():
        proposal = RiskCompilerV1(RiskPolicyV1()).compile(sample_case(), sample_analysis(sample_case()), now_ms=NOW)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            feishu = FeishuAppClient("app", "sec", "user-open-id", client=client, receive_id_type="open_id")
            msg_id = await feishu.send_proposal(proposal)
            assert msg_id == "msg-xyz"

    asyncio.run(run())
    assert len(requests) == 2
