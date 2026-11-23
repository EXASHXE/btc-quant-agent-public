"""Offline end-to-end and negative checks against the installed wheels."""

import asyncio
import json
import os
import socket
import sqlite3
import sys
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from quant_hermes_feishu_h1.contract import SYNTHETIC_WARNING_TOKEN, ContractError
from quant_hermes_feishu_h2b.explainer_gate import ScriptedModelResponse
from quant_hermes_feishu_h2b.outbound_sender import deterministic_feishu_uuid
from quant_hermes_h3.agent import NAMES, LocalSession, configure
from quant_hermes_h3.cli import detail, synthetic_permit
from quant_hermes_h3.delivery import Delivery, alert_snapshot
from quant_hermes_h3.facade import SOCKET, serving
from quant_hermes_h3.inbound import APP, CHAT, OPEN_ID, TENANT, PrivateDm, binding, mock_callback
from quant_hermes_h3.safety import (
    Blocked,
    OfflinePermit,
    exclusive,
    isolated,
    restrict_python_network,
)
from quant_hermes_h3.source import FixtureCase, actionability, refresh_interface
from quant_hermes_h3.telemetry import Measurements, correlate, pi_export
from quant_personal_live_public_b5.contract import PublicRequest
from quant_personal_live_public_b5.decision import DecisionJournal

RUN = Path(os.environ["H3_QA_RUN"])
HERMES = RUN / "hermes"
SOURCE = RUN / "pullback-long/source.sqlite"
JOURNAL = RUN / "pullback-long/journal.sqlite"


def artifact(name):
    return json.loads((RUN / f"{name}.json").read_text())


def cards():
    journal = DecisionJournal(JOURNAL)
    with journal.connect() as db:
        rows = list(db.execute("SELECT id FROM cards ORDER BY as_of"))
    return [journal.read(card_id=row[0]) for row in rows]


@pytest.fixture(scope="session", autouse=True)
def local_only():
    isolated()
    restrict_python_network()
    configure(HERMES)
    yield
    disallowed = {"quant_personal_account_b3", "btc_quant_agent", "program_c"}
    assert not disallowed.intersection(name.partition(".")[0] for name in sys.modules)


@pytest.fixture
def room(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    measure = Measurements(tmp_path / "measure.sqlite")
    with serving(SOURCE, JOURNAL) as client:
        now = cards()[-1]["evaluated_ms"]
        permit = synthetic_permit(tmp_path, now)
        delivery = Delivery(tmp_path / "sender", binding(), HERMES, client, permit, measure)
        yield SimpleNamespace(
            root=tmp_path, measure=measure, now=now, client=client, permit=permit, delivery=delivery
        )


def test_source_stages_and_no_setup():
    trace = artifact("source-trace")
    (canary,) = trace["canary"]
    assert canary["market_status"] == "NOT_EVALUATED"
    assert canary["request_budget"]["reserved_requests"] == 2
    assert canary["request_budget"]["reserved_weight"] == 2
    assert canary["available_venue_ms"] is None
    assert len(trace["staged"]) == 3
    for report in trace["staged"]:
        assert report["market_status"] == "NO_SETUP"
        assert report["episode_id"] is None
        assert report["request_budget"]["reserved_requests"] == 39
        assert report["request_budget"]["reserved_weight"] == 42


def test_deterministic_alert_then_mock_and_fallback_replies():
    trace = artifact("transcripts")
    (alert,) = trace["alerts"]
    assert alert["state"] == "PROVIDER_ACK"
    assert alert["human_read"] == "UNOBSERVED"
    assert alert["deduplicated"]
    assert [turn["model_status"] for turn in trace["replies"]] == [
        "NO_MODEL",
        "MOCK_MODEL_VALIDATED",
        "MODEL_QUOTA",
        "MODEL_TIMEOUT",
        "MODEL_OR_TOOL_INTEGRITY_FAILURE",
    ]
    assert all(turn["sent"] for turn in trace["replies"])
    assert trace["mock_provider_requests"][0]["uuid"] == deterministic_feishu_uuid(
        alert["event_id"]
    )
    assert all(SYNTHETIC_WARNING_TOKEN in r["content"] for r in trace["mock_provider_requests"])


def test_replay_recovery_and_measurements():
    replay = artifact("raw-replay")
    assert len(replay) == 9
    assert all(r["unchanged_decision_payload"] and r["raw_receipt_count"] > 0 for r in replay)
    recovery = artifact("recovery")
    assert recovery["reclaimed_to"] == "UNKNOWN_DELIVERY"
    assert recovery["automatic_resends"] == 0
    assert recovery["reconciled_state"] == "PROVIDER_ACK"
    rows = artifact("resume-measurements")
    counts = [row for row in rows if row["event"] == "GET_DISPATCH"]
    assert len(counts) == 110
    assert all(row["lane"] == "OFFLINE_SYNTHETIC" for row in rows)
    assert artifact("resume-latency")["REAL_FEISHU"]["status"] == "UNOBSERVED"
    assert pi_export() == artifact("pi-feedback")


def test_actionability_has_no_future_information_at_t0():
    trajectory = artifact("actionability")
    first, five, ten = trajectory["trajectory"]
    assert [row["label"] for row in (first, five, ten)] == ["T0", "T+5m", "T+10m"]
    assert first["reprice"] is None
    assert five["source_available_venue_ms"] >= first["evaluated_venue_ms"] + 300_000
    assert ten["source_available_venue_ms"] >= first["evaluated_venue_ms"] + 600_000
    assert len({row["original_card_version"] for row in (first, five, ten)}) == 1
    assert first["bid"] and first["ask"] and first["spread_usdt"]
    assert ten["market_status"] == "INVALID" and ten["reasons"] == ["MISSED_NO_CHASE"]
    watch, *rest = cards()
    with pytest.raises(Blocked, match="REPRICE_UNCONFIRMED"):
        actionability(watch, "unused", rest)
    assert refresh_interface()["real_observations"] == "REPRICE_UNOBSERVED"


def test_assembled_hermes_wire_inventory_and_callability(room):
    with closing(LocalSession((APP, TENANT, OPEN_ID, CHAT), room.measure)) as session:
        assert session.inventory() == NAMES
        _watch, original, *_ = cards()
        episode = original["episode_id"]
        args = {
            "list_active_signals": {},
            "get_signal_detail": {"episode_id": episode},
            "get_market_context": {"symbol": original["symbol"]},
            "get_latest_reprice": {"episode_id": episode},
            "get_signal_history": {},
            "get_strategy_summary": {},
        }
        for n, name in enumerate(NAMES):
            result = session.call(name, args[name], turn=correlate("all-tools"), index=n)
            assert result["status"] == "OK", (name, result)


def test_global_builtin_tools_invisible_and_uncallable(room):
    import model_tools
    from tools.registry import registry

    global_names = set(registry.get_all_tool_names())
    assert {"terminal", "read_file", "write_file", "browser_navigate"} <= global_names
    blocked = sorted(
        global_names - set(NAMES)
        | {"request_reprice", "send_message", "arbitrary_http", "mcp_generic", "trade"}
    )
    with closing(LocalSession((APP, TENANT, OPEN_ID, CHAT), room.measure)) as session:
        assert not set(blocked).intersection(session.inventory())
        for name in blocked:
            with pytest.raises(ContractError, match="outside frozen QUANT session"):
                session.call(name, {}, turn=correlate("privileges"))
    result = model_tools.handle_function_call("terminal", {"command": "forbidden"})
    assert "blocked by QUANT H2-B fail-closed boundary" in result


def test_uds_enforces_peer_scopes_and_model_arguments(room):
    assert SOCKET.stat().st_mode & 0o777 == 0o600
    assert SOCKET.parent.stat().st_mode & 0o777 == 0o700
    wrong = room.client.send_raw_envelope(
        {
            "contract_id": "V080_QUANT_AGENT_CONTRACT_V1",
            "request_id": "h3-qa-011",
            "tool": "list_active_signals",
            "args": {},
            "principal_id": "wrong_principal",
            "recipient_scope": "owner_dm",
            "deadline_ms": 1000,
        }
    )
    assert wrong["status"] == "ERROR" and wrong["error"]["code"] == "UNAUTHORIZED"
    with closing(LocalSession((APP, TENANT, OPEN_ID, CHAT), room.measure)) as session:
        reply = session.call(
            "get_signal_history", {"db_path": "/not-authorized"}, turn=correlate("bad-arg")
        )
        assert reply["status"] == "ERROR" and reply["error"]["code"] == "INVALID_ARGUMENT"


@pytest.mark.parametrize(
    ("bad", "code"),
    [
        ({"app": "cli_wrong001"}, "APP_ID_MISMATCH"),
        ({"tenant": "wrong_tenant"}, "TENANT_KEY_MISMATCH"),
        ({"owner": "ou_wrong001"}, "UNAUTHORIZED_OWNER_OPEN_ID"),
        ({"chat": "oc_wrong001"}, "CHAT_IDENTITY_MISMATCH"),
        ({"chat_type": "group"}, "UNAUTHORIZED_GROUP_OR_NON_DM"),
        ({"token": "forged"}, "INVALID_VERIFICATION_TOKEN"),
    ],
)
def test_spoofed_inbound_is_rejected(room, bad, code):
    dm = PrivateDm(room.root, room.client, room.permit, room.delivery, room.measure)
    event = mock_callback(number=10, text="当前机会", ts=room.now, **bad)
    result = asyncio.run(dm.handle(event, now_ms=room.now, as_of_ms=room.now))
    assert result["error_code"] == code
    assert not room.delivery.mock.requests


def test_replayed_event_and_message_blocked_after_restart(room):
    def instance():
        return PrivateDm(room.root, room.client, room.permit, room.delivery, room.measure)

    event = mock_callback(number=1, text="当前机会", ts=room.now)
    duplicate_message = mock_callback(number=2, text="当前机会", ts=room.now, message_number=1)
    assert asyncio.run(instance().handle(event, now_ms=room.now, as_of_ms=room.now))["sent"]
    for message, code in (
        (event, "DUPLICATE_EVENT_ID"),
        (duplicate_message, "DUPLICATE_MESSAGE_ID"),
    ):
        result = asyncio.run(instance().handle(message, now_ms=room.now, as_of_ms=room.now))
        assert result["error_code"] == code and not result["sent"]
    assert len(room.delivery.mock.requests) == 1


def test_forged_hermes_source_and_untrusted_raw_dict(room):
    dm = PrivateDm(room.root, room.client, room.permit, room.delivery, room.measure)
    event = mock_callback(number=1, text="当前机会", ts=room.now)
    event.source.user_id = "ou_forged111"
    assert not asyncio.run(dm.handle(event, now_ms=room.now, as_of_ms=room.now))["sent"]
    event.raw_message = {"payload": "not-verified"}
    assert asyncio.run(dm.handle(event, now_ms=room.now, as_of_ms=room.now))["error_code"] == (
        "UNVERIFIED_MOCK_CALLBACK_ORIGIN"
    )


@pytest.fixture
def active_room(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    measure = Measurements(tmp_path / "measure.sqlite")
    case = FixtureCase(tmp_path / "active", measure, "trend_pullback-long")
    with case.collecting():
        (watch,) = case.evaluate(0)
        (card,) = case.evaluate(1)
        with serving(case.source, case.journal) as client:
            now = card["evaluated_ms"]
            mutable = [now]
            permit = OfflinePermit(
                tmp_path, starts_ms=now - 1, expires_ms=now + 1_000_000, clock=lambda: mutable[0]
            )
            yield SimpleNamespace(
                root=tmp_path,
                measure=measure,
                now=now,
                client=client,
                permit=permit,
                mutable=mutable,
                card=card,
                watch=watch,
                case=case,
            )


def send_setup(room, responses=None):
    delivery = Delivery(
        room.root / "out",
        binding(),
        HERMES,
        room.client,
        room.permit,
        room.measure,
        responses=responses,
    )
    selection = (room.card["episode_id"], room.card["card_id"])
    key = correlate("alert")
    return delivery, selection, key


@pytest.mark.parametrize(
    ("phase", "value", "reason"),
    [
        ("snapshot", {"freshness_state": "STALE"}, "STALE"),
        ("snapshot", {"source_receipt_sha256": None}, "MISSING_PROVENANCE"),
        ("envelope", {"source_evidence_class": "MIXED"}, "EVIDENCE_MISMATCH"),
        ("data", {"is_superseded": True}, "SUPERSEDED"),
        ("snapshot", {"absolute_expiry_ms": None}, "EXPIRED"),
    ],
)
def test_affirmative_alert_rechecks(active_room, phase, value, reason):
    r = active_room
    args = {"episode_id": r.card["episode_id"], "card_id": r.card["card_id"], "as_of_ms": r.now}
    env = r.client.call_tool("get_signal_detail", args)
    selection = {"envelope": env, "data": env["data"], "snapshot": env["data"]["snapshot"]}
    selection[phase].update(value)
    with pytest.raises(ContractError, match=reason):
        alert_snapshot(env, episode=args["episode_id"], card=args["card_id"], now_ms=r.now)


def test_stale_queued_card_suppressed_before_provider(active_room):
    r = active_room
    delivery, selection, key = send_setup(r)
    delivery.enqueue(*selection, now_ms=r.now, correlation=key)
    r.case.evaluate(2)
    answer = delivery.dispatch(now_ms=r.case.cards[-1]["evaluated_ms"], correlation=key)
    assert answer["state"] in {"EXPIRED", "SUPPRESSED"}
    assert not delivery.mock.requests


def test_revocation_and_expiry_before_provider(active_room):
    r = active_room
    delivery, selection, key = send_setup(r)
    delivery.enqueue(*selection, now_ms=r.now, correlation=key)
    (r.root / "REVOKED").touch()
    with pytest.raises(ContractError, match="revoked"):
        delivery.dispatch(now_ms=r.now + 1, correlation=key)
    (r.root / "REVOKED").unlink()
    r.mutable[0] = r.permit.expires_ms
    with pytest.raises(ContractError, match="expired"):
        delivery.dispatch(now_ms=r.now + 1, correlation=key)
    assert not delivery.mock.requests


def test_retry_backoff_transient_and_ambiguous_delivery(active_room):
    r = active_room
    error = SimpleNamespace(success=lambda: False, code=429, msg="synthetic rate limit")
    delivery, selection, key = send_setup(r, [error, TimeoutError("mock timeout")])
    delivery.enqueue(*selection, now_ms=r.now, correlation=key)
    first = delivery.dispatch(now_ms=r.now, correlation=key)
    assert first["state"] == "RETRYABLE"
    assert delivery.dispatch(now_ms=r.now + 999, correlation=key) is None
    second = delivery.dispatch(now_ms=r.now + 1000, correlation=key)
    assert second["state"] == "UNKNOWN_DELIVERY"
    assert delivery.dispatch(now_ms=r.now + 2000, correlation=key) is None
    assert len(delivery.mock.requests) == 2
    assert len({item["uuid"] for item in delivery.mock.requests}) == 1


def test_unconfirmed_watch_cannot_enter_outbox(active_room):
    r = active_room
    delivery, _, key = send_setup(r)
    with pytest.raises(ContractError):
        delivery.enqueue(r.watch["episode_id"], r.watch["card_id"], now_ms=r.now, correlation=key)
    assert not delivery.mock.requests


def test_mock_wrong_price_and_account_assertions_rejected(active_room):
    r = active_room
    delivery, _, _ = send_setup(r)
    dm = PrivateDm(r.root, r.client, r.permit, delivery, r.measure)
    snapshot = detail(r.client, r.card)
    base = {
        "schema_version": "V1",
        "card_id": snapshot["card_id"],
        "card_version": snapshot["card_version"],
        "market_status": snapshot["market_status"],
        "referenced_reason_codes": snapshot["status_reason_codes"],
        "advisory_only": True,
    }
    from quant_hermes_feishu_h1.explainer import EXPLANATION_SCHEMA_VERSION

    base["schema_version"] = EXPLANATION_SCHEMA_VERSION
    targets = snapshot["plan"]["targets"]
    samples = [
        f"SL {targets[0]['price']} TP1 {snapshot['plan']['hard_stop']}",
        "账户上下文可用，已验证仓位安全。",
    ]
    for index, sample in enumerate(samples):
        script = ScriptedModelResponse(explanation_payload={**base, "summary_zh": sample})
        event = mock_callback(number=index + 1, text=f"查看 {r.card['episode_id']}", ts=r.now)
        turn = asyncio.run(dm.handle(event, now_ms=r.now, as_of_ms=r.now, script=script))
        assert turn["model_status"] == "MODEL_OR_TOOL_INTEGRITY_FAILURE" and turn["sent"]
        assert sample not in turn["transcript"]


@pytest.mark.parametrize(
    ("script", "reason"),
    [
        (ScriptedModelResponse(mode="invalid_json"), "MODEL_OR_TOOL_INTEGRITY_FAILURE"),
        (ScriptedModelResponse(tool_args={"principal_id": "forged"}), "TOOL_REJECTED"),
        (
            ScriptedModelResponse(tool_choice="get_strategy_summary", tool_args={}),
            "WRONG_MODEL_CONTEXT",
        ),
    ],
)
def test_mock_malformed_and_multi_turn_context(active_room, script, reason):
    r = active_room
    delivery, _, _ = send_setup(r)
    dm = PrivateDm(r.root, r.client, r.permit, delivery, r.measure)
    assert asyncio.run(
        dm.handle(mock_callback(number=1, text="当前机会", ts=r.now), now_ms=r.now, as_of_ms=r.now)
    )["sent"]
    event = mock_callback(number=2, text=f"查看 {r.card['episode_id']}", ts=r.now)
    result = asyncio.run(dm.handle(event, now_ms=r.now, as_of_ms=r.now, script=script))
    assert result["model_status"] == reason and result["sent"]


def test_model_cancellation_and_expired_card(active_room):
    r = active_room
    delivery, _, _ = send_setup(r)
    dm = PrivateDm(r.root, r.client, r.permit, delivery, r.measure)
    text = f"查看 {r.card['episode_id']}"

    async def interrupted():
        event = mock_callback(number=1, text=text, ts=r.now)
        task = asyncio.create_task(
            dm.handle(
                event,
                now_ms=r.now,
                as_of_ms=r.now,
                script=ScriptedModelResponse(mode="delayed_cancel"),
            )
        )
        while not any(row["event"] == "MODEL_BEGIN" for row in r.measure.rows()):
            assert not task.done()
            await asyncio.sleep(0.001)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(interrupted())
    assert not delivery.mock.requests
    expires = detail(r.client, r.card)["absolute_expiry_ms"]
    result = asyncio.run(
        dm.handle(
            mock_callback(number=2, text=text, ts=expires),
            now_ms=expires,
            as_of_ms=expires,
            script=ScriptedModelResponse(),
        )
    )
    assert result["sent"] and result["model_status"] == "EXPIRED_OR_STALE_CORE_CARD"
    assert "MOCK_MODEL_VALIDATED" not in result["transcript"]


def test_denied_source_and_endpoint(tmp_path):
    measure = Measurements(tmp_path / "ledger.sqlite")
    case = FixtureCase(
        tmp_path / "denied",
        measure,
        canary=True,
        mutate=lambda request, result: replace(result, status=451),
    )
    with case.collecting():
        assert case.evaluate() == []
    assert case.trace[0]["market_status"] == "SOURCE_BLOCKED"
    assert case.wire.number == 1
    with pytest.raises(Exception, match="(ROUTE|METHOD|ALLOW)"):
        PublicRequest("/fapi/v1/order", {}).validate()
    assert case.wire.number == 1


def test_append_only_redacted_no_external_socket_and_exclusive_writer(tmp_path):
    m = Measurements(tmp_path / "m.sqlite")
    m.record("START", correlate("feedback"))
    with sqlite3.connect(m.path) as db, pytest.raises(sqlite3.DatabaseError, match="append only"):
        db.execute("DELETE FROM measurements")
    with pytest.raises(ValueError, match="UNSCHEMATIZED"):
        m.record("OPERATOR_FEEDBACK", "person@example", code="MARKED_FOR_REVIEW")
    assert m.report()["REAL_FEISHU"]["status"] == "UNOBSERVED"
    with pytest.raises(Blocked, match="OFFLINE_IP_SOCKET"):
        socket.socket(socket.AF_INET)
    with pytest.raises(Blocked, match="OFFLINE_IP_SOCKET"):
        socket.getaddrinfo("offline-denied.invalid", 443)
    with (
        exclusive(tmp_path / ".lock"),
        pytest.raises(Blocked, match="COMPETING_WRITER"),
        exclusive(tmp_path / ".lock"),
    ):
        pass


def test_full_inbound_deadline_prevents_late_send(active_room):
    r = active_room
    delivery, _, _ = send_setup(r)
    dm = PrivateDm(r.root, r.client, r.permit, delivery, r.measure)
    event = mock_callback(number=1, text="当前机会", ts=r.now)
    result = asyncio.run(dm.handle(event, now_ms=r.now, as_of_ms=r.now, deadline_s=0))
    assert result["error_code"] == "TURN_TIMEOUT" and not delivery.mock.requests


def test_integrity_checked_again_after_outbox_enqueue(active_room):
    r = active_room
    delivery, selection, key = send_setup(r)
    delivery.enqueue(*selection, now_ms=r.now, correlation=key)
    # The update is against a disposable fixture database and breaks the accepted B5 receipt seal.
    with sqlite3.connect(r.case.source) as db:
        with pytest.raises(sqlite3.IntegrityError, match="B5_APPEND_ONLY"):
            db.execute("UPDATE b5_receipts SET sha256 = 'invalid'")
        db.execute("DROP TRIGGER lock_b5_receipts_UPDATE")
        db.execute("UPDATE b5_receipts SET sha256 = 'invalid'")
    result = delivery.dispatch(now_ms=r.now + 1, correlation=key)
    assert result["state"] == "SUPPRESSED" and not delivery.mock.requests


def test_no_setup_stays_diagnostic_in_frozen_v1(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    staged = RUN / "staged"
    with serving(staged / "source.sqlite", staged / "journal.sqlite") as client:
        result = client.call_tool("list_active_signals")
        assert result["status"] == "OK" and not result["data"]["signals"]
        context = client.call_tool("get_market_context", {"symbol": "BTCUSDT"})
        assert context["status"] == "OK"
        assert "NO_SETUP" in json.dumps(context["data"])
