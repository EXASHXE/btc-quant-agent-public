"""H4 installed integration, adversarial state checks and finite single-use S4."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import sqlite3
from contextlib import closing
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from quant_hermes_feishu_h1.contract import ContractError
from quant_hermes_feishu_h1.renderer import render_signal_alert
from quant_hermes_feishu_h2b.activation_gate import H2BRevocationStore
from quant_hermes_feishu_h2b.inbound_boundary import InboundDedupStore
from quant_hermes_feishu_h2b.outbound_sender import (
    ConcurrentSenderError,
    H2BMockLarkRecorder,
    HermesSingleSenderService,
    compute_snapshot_event_id,
)
from quant_hermes_h3.agent import NAMES, LocalSession, configure
from quant_hermes_h3.facade import serving
from quant_hermes_h3.inbound import APP, CHAT, OPEN_ID, TENANT, binding
from quant_hermes_h3.safety import restrict_python_network
from quant_hermes_h3.source import FixtureCase, actionability
from quant_personal_live_public_b5.contract import FUNDING
from quant_personal_public_b1.fixture import fixture_reply
from quant_hermes_h3.telemetry import Measurements, correlate, pi_export

from quant_h4.approval import NATIVE, ROLES, Claim, Permit, State, ns_guard, verify_release
from quant_h4.fence import Denied, FilePin, Witness, canonical
from quant_h4.inbound import FiniteInbound, Frame, authenticate
from quant_h4.market import packet
from quant_h4.provider import FeishuPort
from quant_h4.sender import ProtectedSender, text_sha

WHEEL = Path(os.environ["H4_WHEEL"])
WHEEL_SHA = hashlib.sha256(WHEEL.read_bytes()).hexdigest()
HOME = Path(os.environ["HERMES_HOME"])
BRIDGE_KEY = b"H4-QA-ONLY-EPHEMERAL-BRIDGE-KEY-01"


@pytest.fixture(scope="session", autouse=True)
def setup():
    ns_guard()
    restrict_python_network()
    configure(HOME)
    yield
    import sys

    assert not {"quant_personal_account_b3", "btc_quant_agent", "program_c"}.intersection(
        name.split(".")[0] for name in sys.modules
    )


@pytest.fixture
def core(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    measurement = Measurements(tmp_path / "metrics.sqlite")
    case = FixtureCase(tmp_path / "source", measurement, "trend_pullback-long")
    with case.collecting():
        (watch,) = case.evaluate(0)
        (card,) = case.evaluate(1)
        with serving(case.source, case.journal) as client:
            now = card["evaluated_ms"]
            env = client.call_tool(
                "get_signal_detail",
                {
                    "episode_id": card["episode_id"],
                    "card_id": card["card_id"],
                    "as_of_ms": now,
                },
            )
            assert env["status"] == "OK"
            yield SimpleNamespace(
                root=tmp_path,
                measurement=measurement,
                case=case,
                snapshot=env["data"]["snapshot"],
                card=card,
                watch=watch,
                now=now,
                client=client,
            )


def approvals(claim):
    keys = [Ed25519PrivateKey.from_private_bytes(bytes([x]) * 32) for x in (111, 113)]
    sig = {
        role: key.sign(f"{NATIVE}/{role}\n".encode() + canonical(asdict(claim))).hex()
        for role, key in zip(ROLES, keys, strict=True)
    }
    return tuple(key.public_key().public_bytes_raw() for key in keys), sig


def new_state(core, name, *, responses=None):
    root = core.root / name
    root.mkdir(0o700)
    service = HermesSingleSenderService(
        state_dir=root, binding=binding(), hermes_home=HOME, mock_lark_client=H2BMockLarkRecorder()
    )
    paths = {
        "outbox": service.outbox_db_path,
        "delivery": root / "h2b_delivery_ledger.sqlite",
        "quota": root / "quota.sqlite",
        "dedup": root / "dedup.sqlite",
    }
    H2BRevocationStore(paths["quota"])
    InboundDedupStore(paths["dedup"])
    witness_root = core.root / f"independent-{name}"
    witness_root.mkdir(0o700)
    witness = witness_root / "anchor"
    body = b"H4_WITNESS_V1 offline-test-anchor\n"
    witness.write_bytes(body)
    state = State(
        Witness(FilePin.capture_fixture(witness), hashlib.sha256(body).hexdigest(), True),
        tuple((name_, FilePin.capture_fixture(path)) for name_, path in sorted(paths.items())),
    )
    return state, H2BMockLarkRecorder(responses)


def make_sender(core, capability="outbound", *, responses=None, enrolled=None):
    state, provider = enrolled or new_state(core, capability, responses=responses)
    outbound = capability == "outbound"
    runtime = binding()
    claim = Claim(
        task=NATIVE,
        capability=capability,
        run_id="8" * 32 if outbound else "9" * 32,
        release_sha256=WHEEL_SHA,
        state_sha256=state.identity(),
        runtime_uid=os.geteuid(),
        authority="https://open.feishu.cn",
        app=APP,
        tenant=TENANT,
        owner=OPEN_ID,
        chat=CHAT,
        sender=runtime.sender_id,
        channel="feishu",
        not_before_ms=core.now - 1,
        expires_ms=core.now + 30_000,
        event_id=compute_snapshot_event_id(core.snapshot, recipient=CHAT) if outbound else None,
        message_sha256=text_sha(render_signal_alert(core.snapshot)) if outbound else None,
        evidence_class="SYNTHETIC_QA_ONLY",
        message_limit=int(outbound),
        accepted_turns=int(not outbound),
        reply_limit=int(not outbound),
        auth_bootstrap_limit=0,
        facade_path=str(core.client.socket_path.resolve()),
        facade_uid=os.geteuid(),
        callback_key_sha256=None if outbound else hashlib.sha256(BRIDGE_KEY).hexdigest(),
    )
    keys, signatures = approvals(claim)
    permit = Permit(claim, state, WHEEL, signatures, fixture_keys=keys, clock=lambda: core.now)
    sender = ProtectedSender(permit, hermes_home=HOME, provider=provider)
    return sender, provider


def event(core, *, owner=OPEN_ID, chat=CHAT, chat_type="p2p"):
    payload = {
        "schema": "2.0",
        "header": {
            "event_id": "ev_h4_1",
            "event_type": "im.message.receive_v1",
            "app_id": APP,
            "tenant_key": TENANT,
            "create_time": str(core.now),
        },
        "event": {
            "sender": {
                "sender_id": {"open_id": owner},
                "tenant_key": TENANT,
                "sender_type": "user",
            },
            "message": {
                "message_id": "om_h4_1",
                "chat_id": chat,
                "chat_type": chat_type,
                "create_time": str(core.now),
                "message_type": "text",
                "content": json.dumps({"text": "当前机会"}),
            },
        },
    }
    body = json.dumps(payload, ensure_ascii=False).encode()
    return Frame(body, authenticate(BRIDGE_KEY, "9" * 32, body))


class Session:
    def __init__(self, frame, delay=0):
        self.frame, self.delay = frame, delay
        self.closed = False

    async def receive(self):
        await asyncio.sleep(self.delay)
        return self.frame

    async def disconnect(self):
        self.closed = True


def test_complete_h4_chain(core):
    canary = FixtureCase(core.root / "canary", core.measurement, canary=True)
    with canary.collecting():
        assert canary.evaluate() == []
    assert canary.trace[0]["market_status"] == "NOT_EVALUATED"
    assert canary.trace[0]["request_budget"]["reserved_requests"] == 2
    assert canary.trace[0]["request_budget"]["reserved_weight"] == 2

    staged = FixtureCase(core.root / "combined", core.measurement)
    with staged.collecting():
        cards = staged.evaluate()
    assert len(cards) == 3 and {card["market_status"] for card in cards} == {"NO_SETUP"}
    assert staged.trace[0]["request_budget"]["reserved_requests"] == 39
    assert staged.trace[0]["request_budget"]["reserved_weight"] == 42
    assert all(trace["receipt_replay"]["evidence"] == "SYNTHETIC_QA_ONLY" for trace in staged.trace)
    assert core.watch["market_status"] == "WATCH" and core.card["market_status"] == "EXECUTABLE"

    sender, provider = make_sender(core)
    claim = sender.permit.claim
    direct = sender.send_text(
        channel=claim.channel,
        recipient=claim.chat,
        text=render_signal_alert(core.snapshot),
        event_id=claim.event_id,
        attempt=1,
    )
    assert direct.error_code == "CORE_RECHECK_REQUIRED" and not provider.requests
    queued = sender.enqueue(core.snapshot, core.now)
    assert sender.enqueue(core.snapshot, core.now)["deduplicated"]
    alert_key = core.case.trace[1]["measurement_key"]
    core.measurement.record("OUTBOX_ENQUEUE", alert_key)
    core.measurement.record("SENDER_ATTEMPT", alert_key)
    attempt = sender.dispatch(core.client, core.now + 1)
    core.measurement.record("PROVIDER_ACK", alert_key, code="ACK")
    assert attempt["state"] == "PROVIDER_ACK"
    assert sender.used_hermes_adapter and len(provider.requests) == 1
    assert provider.requests[0]["uuid"] == "qh2b-" + queued["event_id"][:36]
    with pytest.raises(Denied, match="CAPABILITY_SPENT"):
        sender.dispatch(core.client, core.now + 2)

    outbound_attempts = len(provider.requests)
    inbound, replies = make_sender(core, "inbound", enrolled=(sender.permit.state, provider))
    assert inbound.service.outbox_db_path == sender.service.outbox_db_path
    assert inbound.service.lock_path == sender.service.lock_path
    verify = FiniteInbound(inbound, core.client, bridge_secret=BRIDGE_KEY, events=core.measurement)
    frame = Session(event(core))
    outcome = asyncio.run(verify.run(frame, as_of_ms=core.now))
    assert outcome == {"status": "PROVIDER_ACK", "model": "NONE", "human_read": "UNOBSERVED"}
    assert frame.closed and len(replies.requests) == 2
    with closing(LocalSession((APP, TENANT, OPEN_ID, CHAT), core.measurement)) as local:
        assert local.inventory() == NAMES
        result = local.call("list_active_signals", {"limit": 5}, turn=correlate("h4-session"))
        assert result["status"] == "OK"
        with pytest.raises(ContractError, match="outside frozen QUANT session"):
            local.call("send_message", {}, turn=correlate("h4-session"))
    restart = FiniteInbound(inbound, core.client, bridge_secret=BRIDGE_KEY)
    with pytest.raises(Denied, match="CAPABILITY_SPENT"):
        asyncio.run(restart.run(Session(event(core)), as_of_ms=core.now))
    (five,) = core.case.evaluate(2)
    (ten,) = core.case.evaluate(3, quote="chase")
    moves = actionability(core.card, core.snapshot["card_version"], [five, ten])
    assert ten["market_status"] == "INVALID"
    assert moves["real_collection"] == "REPRICE_UNOBSERVED"
    out = Path(os.environ["H4_EVIDENCE"]) / "integrated-trace.json"
    out.write_text(
        json.dumps(
            {
                "lane": "OFFLINE_SYNTHETIC",
                "canary": canary.trace,
                "market": staged.trace,
                "outbound": {"state": attempt["state"], "attempt_count": outbound_attempts},
                "inbound": outcome,
                "total_attempt_count": len(provider.requests),
                "reprice": moves,
                "live_samples": pi_export(),
                "human_read": "UNOBSERVED",
                "fills": "UNOBSERVED",
                "tool_inventory": NAMES,
                "raw_measurement": core.measurement.rows(),
            },
            indent=2,
        )
        + "\n"
    )


@pytest.mark.parametrize("delete", [True, False], ids=["missing", "new-inode"])
def test_quota_replacement_stops_startup_and_attempt(core, delete):
    sender, provider = make_sender(core)
    sender.enqueue(core.snapshot, core.now)
    original = dict(sender.permit.state.pins)["quota"].path
    if delete:
        original.unlink()
    else:
        copy = original.with_suffix(".copy")
        copy.write_bytes(original.read_bytes())
        copy.replace(original)
    with pytest.raises(Denied, match="STATE_UNAVAILABLE|STATE_IDENTITY_MISMATCH"):
        sender.dispatch(core.client, core.now)
    with pytest.raises(Denied, match="STATE_UNAVAILABLE|STATE_IDENTITY_MISMATCH"):
        ProtectedSender(sender.permit, hermes_home=HOME, provider=provider)
    assert len(provider.requests) == 0 and original.exists() is not delete


def test_dual_sqlite_rollback_and_delayed_ack(core):
    sender, provider = make_sender(core)
    queued = sender.enqueue(core.snapshot, core.now)
    key = queued["event_id"]
    backups = []
    for name, pin in sender.permit.state.pins:
        if name == "dedup":
            continue
        clean = sqlite3.connect(":memory:")
        with closing(sqlite3.connect(pin.path)) as db:
            db.backup(clean)
        backups.append((pin, clean))
    try:
        outcome = sender.dispatch(core.client, core.now + 1, crash=True)
        assert outcome["state"] == "ATTEMPTED" and len(provider.requests) == 1
        assert sender.service.reclaim_unknown_deliveries(now_ms=core.now + 1_002) == [key]
        unresolved = sender.service.reconcile_unknown(
            event_id=key,
            provider_message_id=None,
            delivered=False,
            reconciled_at_ms=core.now + 1_003,
        )
        assert unresolved["state"] == "UNKNOWN_DELIVERY"
        accepted = sender.service.reconcile_unknown(
            event_id=key,
            provider_message_id="om_fixture_ack",
            delivered=True,
            reconciled_at_ms=core.now + 1_004,
        )
        assert accepted["state"] == "PROVIDER_ACK"
        for pin, clean in backups:
            with closing(sqlite3.connect(pin.path)) as db:
                clean.backup(db)
            pin.verify_private()
        restarted = ProtectedSender(sender.permit, hermes_home=HOME, provider=provider)
        with pytest.raises(Denied, match="CAPABILITY_SPENT"):
            restarted.dispatch(core.client, core.now + 1_005)
        assert len(provider.requests) == 1
    finally:
        for _, clean in backups:
            clean.close()


def test_uncertain_provider_outcome_has_no_resend(core):
    sender, provider = make_sender(core, responses=[TimeoutError("fixture timeout after write")])
    sender.enqueue(core.snapshot, core.now)
    result = sender.dispatch(core.client, core.now + 1)
    assert result["state"] == "UNKNOWN_DELIVERY"
    with pytest.raises(Denied, match="CAPABILITY_SPENT"):
        sender.dispatch(core.client, core.now + 1_001)
    assert len(provider.requests) == 1


def test_racing_workers_share_one_budget(core):
    sender, provider = make_sender(core)
    sender.enqueue(core.snapshot, core.now)
    other = ProtectedSender(sender.permit, hermes_home=HOME, provider=provider)

    def attempt(worker):
        try:
            return worker.dispatch(core.client, core.now + 1)
        except ConcurrentSenderError:
            return None
        except Denied as exc:
            assert str(exc) in {"CAPABILITY_SPENT", "WITNESS_UNAVAILABLE_OR_BUSY"}
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, (sender, other)))
    assert len(provider.requests) == 1
    assert sum(row is not None and row["state"] == "PROVIDER_ACK" for row in results) == 1


def test_revoked_expired_approval_and_edited_release(core):
    sender, provider = make_sender(core)
    permit = sender.permit
    keys, sig = approvals(permit.claim)
    with pytest.raises(Denied, match="DUAL_APPROVAL_REQUIRED"):
        Permit(permit.claim, permit.state, WHEEL, {"owner": sig["owner"]}, fixture_keys=keys)
    with pytest.raises(Denied, match="APPROVAL_SIGNATURE_INVALID"):
        Permit(replace(permit.claim, chat="oc_wrong"), permit.state, WHEEL, sig, fixture_keys=keys)
    with pytest.raises(Denied, match="APPROVAL_EXPIRED_OR_EARLY"):
        Permit(
            permit.claim,
            permit.state,
            WHEEL,
            sig,
            fixture_keys=keys,
            clock=lambda: permit.claim.expires_ms,
        )
    with pytest.raises(Denied, match="LIVE_FEISHU_NOT_ACTIVATED"):
        Permit(permit.claim, permit.state, WHEEL, sig)
    with pytest.raises(Denied, match="REAL_PROVIDER_NOT_ACTIVATED"):
        FeishuPort(permit, token="fixture", ca_path=core.root / "absent", ca_sha256="1" * 64)
    corrupt = core.root / WHEEL.name
    corrupt.write_bytes(WHEEL.read_bytes() + b"fixture")
    with pytest.raises(Denied, match="RELEASE_DIGEST_MISMATCH"):
        verify_release(corrupt, WHEEL_SHA)
    sender.enqueue(core.snapshot, core.now)
    permit.revoke()
    with pytest.raises(Denied, match="CAPABILITY_REVOKED"):
        sender.dispatch(core.client, core.now + 1)
    assert not provider.requests


def test_inbound_spoof_group_wrong_owner_and_timeout(core):
    sender, provider = make_sender(core, "inbound")
    finite = FiniteInbound(sender, core.client, bridge_secret=BRIDGE_KEY)
    frame = event(core)
    cases = (
        (Session(Frame(frame.body, "0" * 64)), "UNAUTHENTICATED_CALLBACK"),
        (Session(event(core, chat_type="group")), "GROUP|PRIVATE|DM|CHAT"),
        (Session(event(core, owner="ou_impostor")), "OWNER|UNAUTHORIZED|IDENTITY"),
        (Session(frame, delay=0.2), "TURN_TIMEOUT"),
    )
    for session, reason in cases:
        with pytest.raises(Denied, match=reason):
            asyncio.run(finite.run(session, as_of_ms=core.now, timeout_s=0.05))
        assert session.closed
    assert not provider.requests
    assert asyncio.run(finite.run(Session(frame), as_of_ms=core.now))["status"] == "PROVIDER_ACK"
    with pytest.raises(Denied, match="CAPABILITY_SPENT"):
        asyncio.run(finite.run(Session(frame), as_of_ms=core.now))
    assert len(provider.requests) == 1


def test_market_funding_gap_and_unsigned_budget(core):
    proposed = packet()
    assert (
        proposed["combined_requests"],
        proposed["combined_known_weight"],
        proposed["funding_calls"],
    ) == (39, 39, 3)
    assert proposed["funding_general_debit"] is None and proposed["grant"] is None
    assert len(proposed["request_plan"]) == 39
    assert all(
        row["documented_debit"] is None
        for row in proposed["request_plan"]
        if row["path"] == FUNDING
    )

    def gap(request, response):
        return fixture_reply([], status=200) if request.route == FUNDING else response

    partial = FixtureCase(core.root / "funding-gap", core.measurement, mutate=gap)
    with partial.collecting():
        cards = partial.evaluate()
    assert not any(card["market_status"] == "EXECUTABLE" for card in cards)
    assert {trace["market_status"] for trace in partial.trace} == {"SOURCE_BLOCKED"}


@pytest.mark.parametrize(
    "http_status,raw,expected",
    [
        (200, b'{"code":0,"data":{"message_id":"om_fixture"}}', "PROVIDER_ACK"),
        (200, b'{"code":0}', "UNKNOWN_DELIVERY"),
        (503, b"temporary fixture error", "UNKNOWN_DELIVERY"),
        (429, b"rate limited", "PERMANENT"),
    ],
)
def test_provider_wire_shape_and_single_attempt(core, http_status, raw, expected):
    sender, recorder = make_sender(core)
    port = FeishuPort.__new__(FeishuPort)
    port.permit, port.token, port.context = sender.permit, "fixture-token", None
    http = SimpleNamespace(status=http_status, read=lambda limit: raw)
    with patch("quant_h4.provider.http.client.HTTPSConnection") as factory:
        conn = factory.return_value
        conn.getresponse.return_value = http
        sender.native.mock_lark_client.provider = port
        sender.enqueue(core.snapshot, core.now)
        result = sender.dispatch(core.client, core.now + 1)
        assert result["state"] == expected
        factory.assert_called_once_with("open.feishu.cn", 443, context=None, timeout=2)
        conn.request.assert_called_once()
        method, route, body, headers = conn.request.call_args.args
        assert method == "POST" and route == "/open-apis/im/v1/messages?receive_id_type=chat_id"
        assert headers["Authorization"] == "Bearer fixture-token"
        decoded = json.loads(body)
        assert decoded["receive_id"] == CHAT and decoded["msg_type"] == "text"
        assert decoded["uuid"] == "qh2b-" + sender.permit.claim.event_id[:36]
        assert json.loads(decoded["content"]) == {"text": render_signal_alert(core.snapshot)}
        conn.close.assert_called_once()
        with pytest.raises(Denied, match="CAPABILITY_SPENT"):
            sender.dispatch(core.client, core.now + 2)
        assert conn.request.call_count == 1 and not recorder.requests


def test_claim_bound_to_distinct_facade_peer(core):
    sender, provider = make_sender(core)
    permit = sender.permit
    changed = replace(permit.claim, facade_uid=os.geteuid() + 1)
    keys, sig = approvals(changed)
    bound = Permit(changed, permit.state, WHEEL, sig, fixture_keys=keys, clock=lambda: core.now)
    scoped = ProtectedSender(bound, hermes_home=HOME, provider=provider)
    scoped.enqueue(core.snapshot, core.now)
    with pytest.raises(Denied, match="FACADE_PEER_UID_MISMATCH"):
        scoped.dispatch(core.client, core.now)
    assert not provider.requests
