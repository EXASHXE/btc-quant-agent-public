import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from test_live_v1_decision_case import assessment
from test_live_v1_decision_models import sample_analysis

from btc_quant_agent.approval.callback import create_callback_app
from btc_quant_agent.approval.feishu import FeishuAppClient
from btc_quant_agent.approval.store import LiveState, LiveStore
from btc_quant_agent.decision.backends import ResponsesBackend
from btc_quant_agent.decision.risk import RiskCompilerV1, RiskPolicyV1
from btc_quant_agent.decision.service import TacticalLiveService


def test_mocked_provider_market_watch_to_durable_approval(tmp_path):
    async def run():
        calls = []
        async def parse(**kwargs):
            calls.append(kwargs)
            case = json.loads(kwargs["input"][1]["content"])
            from btc_quant_agent.decision.models import CasePackageV1
            validated = CasePackageV1.model_validate_json(json.dumps(case))
            return SimpleNamespace(status="completed", output=[], model="configured-model",
                id="response-1", output_parsed=sample_analysis(validated))

        cards = []
        def feishu(request):
            payload = json.loads(request.content)
            if request.url.path.endswith("tenant_access_token/internal"):
                return httpx.Response(200, json={"code":0, "tenant_access_token":"test-token"})
            assert request.headers["authorization"] == "Bearer test-token"
            cards.append(json.loads(payload["content"]))
            return httpx.Response(200, json={"code":0,"data":{"message_id":"message-1"}})

        store = LiveStore(str(tmp_path / "live.db"))
        backend = ResponsesBackend("configured-model", 1,
            client=SimpleNamespace(responses=SimpleNamespace(parse=parse)), clock_ms=lambda:4000)
        async with httpx.AsyncClient(transport=httpx.MockTransport(feishu)) as http:
            notifier = FeishuAppClient("test-app", "test-secret", "test-chat", client=http)
            service = TacticalLiveService(store, backend, RiskCompilerV1(RiskPolicyV1()),
                notifier=notifier, clock_ms=lambda:4000)
            item = assessment(tmp_path)
            proposal = await service.run_assessment(item)
            assert proposal is not None and proposal.recommended_notional_usdt > 0
            assert proposal.account_authority == "DRY_RUN"
            assert store.state(proposal.case_id) == LiveState.WAITING_APPROVAL
            assert len(calls) == len(cards) == 1
            duplicate = await service.run_assessment(item)
            assert duplicate == proposal and len(calls) == len(cards) == 1
            serialized = json.dumps(cards[0])
            assert "DRY_RUN" in serialized and proposal.proposal_hash in serialized
            assert "test-secret" not in serialized and "test-token" not in serialized
            callback = create_callback_app(store, "verification", approver_open_ids=("approver",),
                app_id="test-app", clock_ms=lambda:5000)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=callback),
                                         base_url="http://test") as client:
                payload = {"schema":"2.0", "header":{"token":"verification",
                    "app_id":"test-app", "event_type":"card.action.trigger", "event_id":"event-1"},
                    "event":{"operator":{"open_id":"approver"}, "action":{"value":{
                    "action":"APPROVE", "proposal_hash":proposal.proposal_hash,
                    "case_hash":proposal.case_hash}}}}
                response = await client.post("/callback", json=payload)
                assert response.status_code == 200, response.text
                repeat = await client.post("/callback", json=payload)
                assert repeat.status_code == 200
            restarted = LiveStore(str(tmp_path / "live.db"))
            assert restarted.state(proposal.case_id) == LiveState.APPROVED
            assert restarted.get_proposal(proposal.proposal_hash) == proposal
            assert service.exchange_write_count == 0
    asyncio.run(run())


def test_notification_error_persists_manual(tmp_path):
    async def run():
        from test_live_v1_decision_models import sample_case
        case = sample_case()
        store = LiveStore(str(tmp_path / "live.db"))
        primary = AsyncMock()
        primary.analyze.return_value = sample_analysis(case)
        notifier = AsyncMock()
        notifier.send_proposal.side_effect = RuntimeError("private-provider-error")
        service = TacticalLiveService(store, primary, RiskCompilerV1(RiskPolicyV1()),
            notifier=notifier, clock_ms=lambda:2000)
        proposal = await service.analyze_case(case)
        assert proposal is not None
        assert store.state(case.case_id) == LiveState.MANUAL
        assert "private-provider-error" not in (tmp_path / "live.db").read_bytes().decode(errors="ignore")
    asyncio.run(run())


def test_real_openai_sdk_structured_parse_with_mocked_http():
    from openai import AsyncOpenAI
    from test_live_v1_decision_models import sample_case

    from btc_quant_agent.decision.backends import AnalysisMode

    async def run():
        case = sample_case()
        requests = []
        def provider(request):
            payload = json.loads(request.content)
            requests.append(payload)
            assert payload["model"] == "configured-model"
            assert payload["text"]["format"]["strict"] is True
            assert payload["text"]["format"]["schema"]["additionalProperties"] is False
            assert payload["store"] is False
            assert len(payload["input"]) == 2
            return httpx.Response(200, json={
                "id":"resp_mock", "object":"response", "created_at":1,
                "status":"completed", "model":"configured-model", "error":None,
                "incomplete_details":None, "output":[{"id":"msg_mock", "type":"message",
                "role":"assistant", "status":"completed", "content":[{"type":"output_text",
                "text":sample_analysis(case).canonical_json(), "annotations":[]}]}],
                "parallel_tool_calls":False, "tools":[], "tool_choice":"auto",
                "temperature":1.0, "top_p":1.0,
            })
        async with (
            httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http,
            AsyncOpenAI(api_key="test-key", http_client=http, max_retries=0) as client,
        ):
            backend = ResponsesBackend("configured-model", 1, client=client,
                                        clock_ms=lambda:2000)
            result = await backend.analyze(case, AnalysisMode.PRIMARY)
        assert result.action == "OPEN_LONG"
        assert result.provider_request_id == "resp_mock"
        assert len(requests) == 1
    asyncio.run(run())


def test_cancelled_codex_review_remains_retryable(tmp_path):
    from test_live_v1_decision_models import sample_case
    async def run():
        case = sample_case()
        store = LiveStore(str(tmp_path / "live.db"))
        primary = AsyncMock()
        primary.analyze.return_value = sample_analysis(case)
        secondary = AsyncMock()
        secondary.timeout_seconds = 1
        notifier = AsyncMock()
        notifier.send_proposal.return_value = "card"
        service = TacticalLiveService(store, primary, RiskCompilerV1(RiskPolicyV1()),
            secondary=secondary, notifier=notifier, clock_ms=lambda:2000)
        original = await service.analyze_case(case)
        store.record_callback("request-codex", "REQUEST_CODEX_REVIEW", "actor",
                              original.proposal_hash, original.case_hash, 2100)
        secondary.analyze.side_effect = asyncio.CancelledError()
        try:
            await service.process_codex_reviews()
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("cancellation must propagate")
        assert store.queued_codex_reviews(2200) == [case.case_id]
        secondary.analyze.side_effect = None
        secondary.analyze.return_value = sample_analysis(case, backend="codex_exec",
                                                         provider_request_id="secondary")
        finished = await service.process_codex_reviews()
        assert len(finished) == 1
        assert store.state(case.case_id) == LiveState.WAITING_APPROVAL
        assert store.queued_codex_reviews(2200) == []
        assert primary.analyze.await_count == 1
    asyncio.run(run())


def test_delayed_codex_worker_cannot_clear_successor_claim(tmp_path):
    from test_live_v1_decision_models import sample_case

    async def run():
        case = sample_case()
        store = LiveStore(tmp_path / "live.db")
        primary = AsyncMock()
        primary.analyze.return_value = sample_analysis(case)
        secondary = AsyncMock()
        secondary.timeout_seconds = 1
        notifier = AsyncMock()
        notifier.send_proposal.return_value = "card"
        now = [2000]
        service = TacticalLiveService(store, primary, RiskCompilerV1(RiskPolicyV1()),
            secondary=secondary, notifier=notifier, clock_ms=lambda: now[0])
        original = await service.analyze_case(case)
        store.record_callback("request-codex", "REQUEST_CODEX_REVIEW", "actor",
                              original.proposal_hash, original.case_hash, now[0])
        successor = []

        async def delayed_result(case, mode):
            now[0] = 34000
            assert store.queued_codex_reviews(now[0]) == [case.case_id]
            successor.append(store.claim_codex_review(case.case_id, now[0], 31000))
            assert successor[0] is not None
            return sample_analysis(case, backend="codex_exec")

        secondary.analyze.side_effect = delayed_result
        assert await service.process_codex_reviews() == []
        assert store.active_proposal(case.case_id) == original
        assert store.state(case.case_id) == LiveState.MANUAL
        assert store.renew_codex_review(case.case_id, successor[0], now[0], 31000)
        store.release_codex_review(case.case_id, successor[0])
        assert store.queued_codex_reviews(now[0]) == [case.case_id]

    asyncio.run(run())


@pytest.mark.parametrize("state", [LiveState.CASE_TRIGGERED, LiveState.LLM_ANALYZING])
def test_abandoned_primary_expires_after_restart_without_reissue(tmp_path, state):
    from test_live_v1_decision_models import sample_case

    async def run():
        case = sample_case()
        store = LiveStore(tmp_path / "live.db")
        store.save_case(case)
        if state == LiveState.LLM_ANALYZING:
            store.transition(case.case_id, state, 2000)
        primary = AsyncMock()
        restarted = LiveStore(tmp_path / "live.db")
        service = TacticalLiveService(restarted, primary, RiskCompilerV1(RiskPolicyV1()),
                                     clock_ms=lambda: case.expires_at_ms)
        with pytest.raises(ValueError, match="STALE_CASE"):
            await service.analyze_case(case)
        assert restarted.state(case.case_id) == LiveState.EXPIRED
        primary.analyze.assert_not_awaited()

    asyncio.run(run())
