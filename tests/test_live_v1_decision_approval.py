import asyncio
import hashlib
import json
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from test_live_v1_decision_models import sample_analysis, sample_case

from btc_quant_agent.approval.callback import create_callback_app
from btc_quant_agent.approval.feishu import FeishuAppClient, build_interactive_card
from btc_quant_agent.approval.store import LiveStore
from btc_quant_agent.decision.models import TradeProposalV1
from btc_quant_agent.decision.risk import RiskCompilerV1, RiskPolicyV1


def prepared(tmp_path, *, manual=False):
    store = LiveStore(tmp_path / "live.sqlite")
    case = sample_case()
    analysis = sample_analysis(case, requires_manual_review=manual)
    proposal = RiskCompilerV1(RiskPolicyV1()).compile(case, analysis, now_ms=2000)
    assert store.save_case(case)
    assert not store.save_case(case)
    store.save_analysis(analysis)
    store.save_proposal(proposal)
    for state in ("LLM_ANALYZING", "PLAN_READY", "NOTIFIED", "WAITING_APPROVAL"):
        store.transition(case.case_id, state, 2000)
    return store, case, analysis, proposal


def test_store_persists_verified_payloads_and_rejects_stale_proposal(tmp_path):
    store, case, analysis, proposal = prepared(tmp_path)
    assert LiveStore(tmp_path / "live.sqlite").get_case(case.case_id) == case
    assert store.get_analysis(case.case_id, "PRIMARY") == analysis
    assert store.active_proposal(case.case_id) == proposal
    assert store.get_proposal(proposal.proposal_hash) == proposal
    assert store.state(case.case_id) == "WAITING_APPROVAL"
    bad = proposal.model_copy(update={"proposal_hash": "a" * 64})
    with pytest.raises(ValueError):
        store.save_proposal(bad)
    with sqlite3.connect(tmp_path / "live.sqlite") as db:
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_store_creates_nested_database_directory(tmp_path):
    path = tmp_path / "var" / "live" / "live.sqlite"
    store = LiveStore(path)
    case = sample_case()
    assert store.save_case(case)
    assert LiveStore(path).get_case(case.case_id) == case


def test_same_analysis_can_be_selected_for_fused_role(tmp_path):
    store, case, analysis, _ = prepared(tmp_path)
    store.save_analysis(analysis, "FUSED")
    assert store.get_analysis(case.case_id, "FUSED") == analysis


def test_case_source_identity_cannot_be_reused_under_new_case_id(tmp_path):
    store = LiveStore(tmp_path / "live.sqlite")
    assert store.save_case(sample_case())
    with pytest.raises(ValueError):
        store.save_case(sample_case(case_id="case-2"))


def test_proposal_id_collision_rejected_without_replacing_active_pointer(tmp_path):
    store, case, _, proposal = prepared(tmp_path)
    values = proposal.model_dump(exclude={"proposal_hash"})
    values["allowed_price_drift_bps"] = 25.0
    collision = TradeProposalV1.build(**values)
    with pytest.raises(ValueError):
        store.save_proposal(collision)
    assert store.active_proposal(case.case_id) == proposal


def test_approval_replay_and_terminal_collision(tmp_path):
    store, case, _, proposal = prepared(tmp_path)
    args = ("event-1", "APPROVE", "actor-1", proposal.proposal_hash, case.case_hash, 3000)
    first = store.record_callback(*args)
    assert first["state"] == "APPROVED" and not first["replay"]
    assert store.record_callback(*args)["replay"]
    assert LiveStore(tmp_path / "live.sqlite").state(case.case_id) == "APPROVED"
    with pytest.raises(ValueError):
        store.record_callback("event-2", "REJECT", "actor-1", proposal.proposal_hash, case.case_hash, 3001)
    with pytest.raises(ValueError):
        store.record_callback("event-1", "APPROVE", "actor-2", proposal.proposal_hash, case.case_hash, 3000)


def test_concurrent_final_callbacks_allow_only_one_decision(tmp_path):
    store, case, _, proposal = prepared(tmp_path)
    path = tmp_path / "live.sqlite"
    def decide(item):
        event_id, action = item
        try:
            return LiveStore(path).record_callback(event_id, action, "actor",
                                                   proposal.proposal_hash, case.case_hash, 3000)["state"]
        except ValueError:
            return "REJECTED_CALLBACK"
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(decide, (("a", "APPROVE"), ("b", "REJECT"))))
    assert outcomes.count("REJECTED_CALLBACK") == 1
    assert store.state(case.case_id) in {"APPROVED", "REJECTED"}
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM approval_records").fetchone()[0] == 1


def test_expiry_is_persisted_even_when_callback_fails(tmp_path):
    store, case, _, proposal = prepared(tmp_path)
    with pytest.raises(ValueError):
        store.record_callback("late", "APPROVE", "actor", proposal.proposal_hash, case.case_hash,
                              proposal.expires_at_ms)
    assert LiveStore(tmp_path / "live.sqlite").state(case.case_id) == "EXPIRED"


def test_manual_review_queue_survives_restart(tmp_path):
    store, case, _, proposal = prepared(tmp_path)
    result = store.record_callback("review", "REQUEST_CODEX_REVIEW", "actor", proposal.proposal_hash,
                                   case.case_hash, 3000)
    assert result["state"] == "MANUAL"
    assert LiveStore(tmp_path / "live.sqlite").queued_codex_reviews() == [case.case_id]
    token = store.claim_codex_review(case.case_id, 3000, 100)
    assert token
    store.mark_codex_review_processed(case.case_id, token)
    assert store.queued_codex_reviews() == []
    store.transition(case.case_id, "PLAN_READY", 3001)
    assert store.queued_codex_reviews() == []


def test_codex_review_claim_is_exclusive_and_expires(tmp_path):
    store, case, _, proposal = prepared(tmp_path)
    store.record_callback("review", "REQUEST_CODEX_REVIEW", "actor", proposal.proposal_hash,
                          case.case_hash, 3000)
    assert store.claim_codex_review(case.case_id, 3000, 100)
    assert not LiveStore(tmp_path / "live.sqlite").claim_codex_review(case.case_id, 3000, 100)
    assert store.queued_codex_reviews(3099) == []
    assert store.queued_codex_reviews(3100) == [case.case_id]
    assert LiveStore(tmp_path / "live.sqlite").claim_codex_review(case.case_id, 3100, 100)


def test_codex_review_release_requeues_before_lease_expiry(tmp_path):
    store, case, _, proposal = prepared(tmp_path)
    store.record_callback("review", "REQUEST_CODEX_REVIEW", "actor", proposal.proposal_hash,
                          case.case_hash, 3000)
    token = store.claim_codex_review(case.case_id, 3000, 100)
    assert token
    store.release_codex_review(case.case_id, token)
    assert store.queued_codex_reviews(3001) == [case.case_id]


def test_pending_review_survives_active_proposal_change_in_manual_state(tmp_path):
    store, case, _, proposal = prepared(tmp_path)
    store.record_callback("review", "REQUEST_CODEX_REVIEW", "actor", proposal.proposal_hash,
                          case.case_hash, 3000)
    values = proposal.model_dump(exclude={"proposal_hash"})
    values["proposal_id"] = "reviewed-id"
    reviewed = TradeProposalV1.build(**values)
    store.save_proposal(reviewed)
    assert store.queued_codex_reviews(3000) == [case.case_id]
    token = store.claim_codex_review(case.case_id, 3000, 100)
    assert token
    store.mark_codex_review_processed(case.case_id, token)
    assert store.queued_codex_reviews(3200) == []


@pytest.mark.parametrize("final_state", ["WAITING_APPROVAL", "APPROVED", "REJECTED"])
def test_queue_reconciles_reviewed_proposal_after_finish_crash(tmp_path, final_state):
    store, case, _, proposal = prepared(tmp_path)
    store.record_callback("review", "REQUEST_CODEX_REVIEW", "actor", proposal.proposal_hash,
                          case.case_hash, 3000)
    values = proposal.model_dump(exclude={"proposal_hash"})
    values["proposal_id"] = "reviewed-id"
    reviewed = TradeProposalV1.build(**values)
    store.save_proposal(reviewed)
    for state in ("PLAN_READY", "NOTIFIED", "WAITING_APPROVAL"):
        store.transition(case.case_id, state, 3001)
    if final_state != "WAITING_APPROVAL":
        store.transition(case.case_id, final_state, 3002)
    assert store.queued_codex_reviews(3003) == []
    with sqlite3.connect(tmp_path / "live.sqlite") as db:
        assert db.execute("SELECT review_processed FROM approval_records WHERE event_id='review'").fetchone()[0] == 1


@pytest.mark.parametrize("interrupted_state", ["PLAN_READY", "NOTIFIED"])
def test_expired_lease_recovers_interrupted_review_finish(tmp_path, interrupted_state):
    store, case, _, proposal = prepared(tmp_path)
    store.record_callback("review", "REQUEST_CODEX_REVIEW", "actor", proposal.proposal_hash,
                          case.case_hash, 3000)
    assert store.claim_codex_review(case.case_id, 3000, 100)
    store.transition(case.case_id, "PLAN_READY", 3001)
    if interrupted_state == "NOTIFIED":
        store.transition(case.case_id, "NOTIFIED", 3002)
    assert store.queued_codex_reviews(3099) == []
    assert store.queued_codex_reviews(3100) == [case.case_id]
    assert LiveStore(tmp_path / "live.sqlite").state(case.case_id) == "MANUAL"


def test_stale_review_owner_cannot_release_mark_or_mutate_successor(tmp_path):
    store, case, _, proposal = prepared(tmp_path)
    store.record_callback("review", "REQUEST_CODEX_REVIEW", "actor", proposal.proposal_hash,
                          case.case_hash, 3000)
    old = store.claim_codex_review(case.case_id, 3000, 100)
    assert old
    current = LiveStore(tmp_path / "live.sqlite").claim_codex_review(case.case_id, 3100, 100)
    assert current and current != old
    store.release_codex_review(case.case_id, old)
    store.mark_codex_review_processed(case.case_id, old)
    assert store.queued_codex_reviews(3101) == []
    with sqlite3.connect(tmp_path / "live.sqlite") as db:
        assert db.execute("SELECT review_claim_token, review_processed FROM approval_records "
                          "WHERE event_id='review'").fetchone() == (current, 0)
    values = proposal.model_dump(exclude={"proposal_hash"})
    values["proposal_id"] = "reviewed-id"
    reviewed = TradeProposalV1.build(**values)
    with pytest.raises(ValueError):
        store.save_proposal(reviewed, review_claim_token=old, now_ms=3101)
    with pytest.raises(ValueError):
        store.transition(case.case_id, "PLAN_READY", 3101, review_claim_token=old)
    assert store.active_proposal(case.case_id) == proposal
    assert store.state(case.case_id) == "MANUAL"
    store.save_proposal(reviewed, review_claim_token=current, now_ms=3101)
    store.transition(case.case_id, "PLAN_READY", 3101, review_claim_token=current)
    assert store.active_proposal(case.case_id) == reviewed


def test_review_lease_renewal_requires_current_unexpired_token(tmp_path):
    store, case, _, proposal = prepared(tmp_path)
    store.record_callback("review", "REQUEST_CODEX_REVIEW", "actor", proposal.proposal_hash,
                          case.case_hash, 3000)
    old = store.claim_codex_review(case.case_id, 3000, 100)
    assert old
    assert store.renew_codex_review(case.case_id, old, 3050, 100)
    assert not store.renew_codex_review(case.case_id, old, 3150, 100)
    current = store.claim_codex_review(case.case_id, 3150, 100)
    assert current and current != old
    assert not store.renew_codex_review(case.case_id, old, 3151, 100)
    assert store.renew_codex_review(case.case_id, current, 3151, 100)


def test_expired_older_review_cannot_reset_newer_live_review(tmp_path):
    store, case, _, proposal = prepared(tmp_path)
    store.record_callback("first", "REQUEST_CODEX_REVIEW", "actor", proposal.proposal_hash,
                          case.case_hash, 3000)
    first = store.claim_codex_review(case.case_id, 3000, 100)
    assert first
    for state in ("PLAN_READY", "NOTIFIED", "WAITING_APPROVAL"):
        store.transition(case.case_id, state, 3001, review_claim_token=first)
    store.record_callback("second", "REQUEST_CODEX_REVIEW", "actor", proposal.proposal_hash,
                          case.case_hash, 2999)
    second = store.claim_codex_review(case.case_id, 3100, 100)
    assert second and second != first
    store.transition(case.case_id, "PLAN_READY", 3101, review_claim_token=second)
    assert store.queued_codex_reviews(3102) == []
    assert store.state(case.case_id) == "PLAN_READY"


def test_new_request_on_reviewed_proposal_reconciles_superseded_request(tmp_path):
    store, case, _, proposal = prepared(tmp_path)
    store.record_callback("first", "REQUEST_CODEX_REVIEW", "actor", proposal.proposal_hash,
                          case.case_hash, 3000)
    first = store.claim_codex_review(case.case_id, 3000, 100)
    assert first
    values = proposal.model_dump(exclude={"proposal_hash"})
    values["proposal_id"] = "reviewed-id"
    reviewed = TradeProposalV1.build(**values)
    store.save_proposal(reviewed, review_claim_token=first, now_ms=3001)
    for state in ("PLAN_READY", "NOTIFIED", "WAITING_APPROVAL"):
        store.transition(case.case_id, state, 3001, review_claim_token=first)
    store.record_callback("second", "REQUEST_CODEX_REVIEW", "actor", reviewed.proposal_hash,
                          case.case_hash, 3002)
    assert store.queued_codex_reviews(3002) == [case.case_id]
    with sqlite3.connect(tmp_path / "live.sqlite") as db:
        assert db.execute("SELECT event_id, review_processed FROM approval_records "
                          "ORDER BY event_id").fetchall() == [("first", 1), ("second", 0)]
    assert store.claim_codex_review(case.case_id, 3002, 100)


def test_manual_proposal_cannot_be_approved(tmp_path):
    store, case, _, proposal = prepared(tmp_path, manual=True)
    with pytest.raises(ValueError):
        store.record_callback("approve", "APPROVE", "actor", proposal.proposal_hash, case.case_hash, 3000)
    assert store.state(case.case_id) == "WAITING_APPROVAL"


def callback_body(case, proposal, event_id="event", action="APPROVE", value_extra=None):
    value = {"action": action, "proposal_hash": proposal.proposal_hash, "case_hash": case.case_hash}
    value.update(value_extra or {})
    return {"schema": "2.0", "header": {"event_type": "card.action.trigger", "event_id": event_id,
            "token": "verify", "app_id": "app"}, "event": {"operator": {"open_id": "allowed"},
            "action": {"value": value}}}


def test_callback_rejects_executable_values_and_bad_identity(tmp_path):
    store, case, _, proposal = prepared(tmp_path)
    app = create_callback_app(store, "verify", approver_open_ids=("allowed",), app_id="app",
                              clock_ms=lambda: 3000)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            bad = callback_body(case, proposal, value_extra={"leverage": 100})
            assert (await client.post("/callback", json=bad)).status_code == 400
            bad = callback_body(case, proposal)
            bad["event"]["action"]["value"]["case_hash"] = "a" * 64
            assert (await client.post("/callback", json=bad)).status_code == 400
            assert store.state(case.case_id) == "WAITING_APPROVAL"
            assert (await client.post("/callback", json=callback_body(case, proposal))).status_code == 200
    asyncio.run(run())


def test_callback_token_challenge_allowlist_and_signature(tmp_path):
    store, case, _, proposal = prepared(tmp_path)
    app = create_callback_app(store, "verify", "secret", ("allowed",), "app", clock_ms=lambda: 3000)
    body = json.dumps({"type": "url_verification", "token": "verify", "challenge": "x"}).encode()
    timestamp, nonce = "3", "n"
    signature = hashlib.sha256(timestamp.encode() + nonce.encode() + b"secret" + body).hexdigest()
    headers = {"x-lark-request-timestamp": timestamp, "x-lark-request-nonce": nonce,
               "x-lark-signature": signature}
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.post("/callback", json={"type": "url_verification", "token": "bad",
                                                         "challenge": "x"})).status_code == 401
            assert (await client.post("/callback", content=body, headers=headers)).json() == {"challenge": "x"}
            assert (await client.post("/callback", json=callback_body(case, proposal))).status_code == 401
            action = callback_body(case, proposal)
            action["event"]["operator"]["open_id"] = "denied"
            denied_body = json.dumps(action).encode()
            denied_signature = hashlib.sha256(timestamp.encode() + nonce.encode() + b"secret" + denied_body).hexdigest()
            headers["x-lark-signature"] = denied_signature
            assert (await client.post("/callback", content=denied_body, headers=headers)).status_code == 403
            approved_body = json.dumps(callback_body(case, proposal)).encode()
            headers["x-lark-signature"] = hashlib.sha256(
                timestamp.encode() + nonce.encode() + b"secret" + approved_body).hexdigest()
            assert (await client.post("/callback", content=approved_body, headers=headers)).json()["state"] == "APPROVED"
    asyncio.run(run())


def test_card_values_contain_only_identity_and_action(tmp_path):
    _, case, _, proposal = prepared(tmp_path)
    card = build_interactive_card(proposal)
    values = [button["value"] for element in card["elements"] if element.get("tag") == "action"
              for button in element["actions"]]
    assert {v["action"] for v in values} == {"APPROVE", "REJECT", "MANUAL", "REQUEST_CODEX_REVIEW"}
    assert all(set(v) == {"action", "case_hash", "proposal_hash"} for v in values)
    assert all(v["case_hash"] == case.case_hash for v in values)


def test_feishu_client_uses_custom_app_token_and_provider_idempotency(tmp_path):
    _, _, _, proposal = prepared(tmp_path)
    requests = []
    def handle(request):
        requests.append(request)
        assert request.extensions["timeout"]["read"] == 10.0
        if request.url.path.endswith("tenant_access_token/internal"):
            assert json.loads(request.content) == {"app_id": "app", "app_secret": "secret"}
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "token"})
        assert request.url.path.endswith("/im/v1/messages")
        assert request.url.params["receive_id_type"] == "chat_id"
        assert request.headers["authorization"] == "Bearer token"
        body = json.loads(request.content)
        assert body["receive_id"] == "chat"
        assert body["msg_type"] == "interactive"
        assert body["uuid"] == str(uuid.UUID(proposal.proposal_hash[:32]))
        assert len(body["uuid"]) <= 50
        assert json.loads(body["content"])["header"]["title"]["content"].endswith("DRY_RUN proposal")
        return httpx.Response(200, json={"code": 0, "data": {"message_id": "message"}})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            assert await FeishuAppClient("app", "secret", "chat", client).send_proposal(proposal) == "message"
    asyncio.run(run())
    assert len(requests) == 2


def test_feishu_delivery_error_does_not_expose_response_or_token(tmp_path):
    _, _, _, proposal = prepared(tmp_path)
    def handle(request):
        return httpx.Response(200, json={"code": 1, "msg": "private-token"})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            with pytest.raises(RuntimeError, match="Feishu proposal delivery failed") as error:
                await FeishuAppClient("app", "secret", "chat", client).send_proposal(proposal)
            assert "private-token" not in str(error.value)
    asyncio.run(run())


def test_feishu_malformed_success_response_is_sanitized(tmp_path):
    _, _, _, proposal = prepared(tmp_path)
    calls = 0
    def handle(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "token"})
        return httpx.Response(200, json={"code": 0, "data": "unexpected"})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            with pytest.raises(RuntimeError, match="Feishu proposal delivery failed"):
                await FeishuAppClient("app", "secret", "chat", client).send_proposal(proposal)
    asyncio.run(run())
