"""Family D tests: sole sender, single-attempt transport, retry/backoff, crash/UNKNOWN_DELIVERY, expiry & ledger."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from quant_hermes_feishu_h1.contract import SYNTHETIC_WARNING_TOKEN, ContractError
from quant_hermes_feishu_h1.facade import QuantFacadeClient, QuantFacadeService, QuantUdsServer
from quant_hermes_feishu_h1.journal_reader import ApprovedJournalRegistry, ApprovedJournalSource

from quant_hermes_feishu_h2b.outbound_sender import (
    ConcurrentSenderError,
    H2BMockLarkRecorder,
    HermesSingleSenderService,
    OutboundBinding,
    deterministic_feishu_uuid,
)

H2B_ROOT = Path(__file__).resolve().parents[1]
WORKSPACES = H2B_ROOT.parent
B5_JOURNAL = WORKSPACES / "lt-v080-personal-mvp-live-public-b5-01/evidence/replay-input/journal.sqlite"
B2_ES_JOURNAL = WORKSPACES / "lt-v080-sol62-personal-mvp-market-decision-b2-01/evidence/demo/early-short/decision.sqlite"


def _binding() -> OutboundBinding:
    return OutboundBinding(
        app_id="cli_h2boffline001",
        tenant_key="tenant_h2b_001",
        owner_open_id="ou_owner001",
        authorized_dm_chat_id="oc_dmowner001",
    )


def _start_facade(tmp_path: Path, journal: Path = B5_JOURNAL, *, require_active: bool = True):
    sock = tmp_path / "sock/f.sock"
    reg = ApprovedJournalRegistry([ApprovedJournalSource("src", journal)])
    srv = QuantUdsServer(sock, QuantFacadeService(reg))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    client = QuantFacadeClient(sock, principal_id="hermes_quant_plugin", recipient_scope="outbox_worker")
    snap = None
    if require_active:
        sig = client.call_tool("list_active_signals")["data"]["signals"][0]
        snap = client.call_tool("get_signal_detail", {"episode_id": sig["episode_id"]})["data"]["snapshot"]
    return srv, client, snap


def test_d1_single_sender_dedup_concurrent_fencing_and_ledger_append_only(tmp_path):
    srv, client, snap = _start_facade(tmp_path)
    try:
        recorder = H2BMockLarkRecorder()
        sender = HermesSingleSenderService(
            state_dir=tmp_path / "state",
            binding=_binding(),
            hermes_home=tmp_path / "hhome",
            mock_lark_client=recorder,
            offline_mock_only=True,
        )
        t0 = snap["evaluated_at_ms"]
        e1 = sender.enqueue(snap, recipient="oc_dmowner001", now_ms=t0)
        e2 = sender.enqueue(snap, recipient="oc_dmowner001", now_ms=t0 + 1)
        assert e1["event_id"] == e2["event_id"]
        assert e2["deduplicated"] is True

        # Reject unauthorized recipient
        with pytest.raises(ContractError) as exc_rec:
            sender.enqueue(snap, recipient="ou_rogue999", now_ms=t0)
        assert exc_rec.value.code == "UNAUTHORIZED"

        # Fence second concurrent sender process attempting to acquire lock
        with sender._exclusive_sender_fence():
            sender2 = HermesSingleSenderService(
                state_dir=tmp_path / "state",
                binding=_binding(),
                hermes_home=tmp_path / "hhome",
                mock_lark_client=recorder,
            )
            with pytest.raises(ConcurrentSenderError) as exc_fence:
                sender2.dispatch_next(facade_client=client, now_ms=t0 + 5)
            assert exc_fence.value.code == "CONCURRENT_SENDER_FENCED"

        # Single dispatch succeeds once with deterministic uuid and text payload; user_read_receipt_proven stays 0
        out = sender.dispatch_next(facade_client=client, now_ms=t0 + 10)
        assert out is not None and out["state"] == "PROVIDER_ACK"
        assert len(recorder.requests) == 1
        req = recorder.requests[0]
        assert req["receive_id_type"] == "chat_id"
        assert req["msg_type"] == "text"
        assert req["uuid"] == deterministic_feishu_uuid(e1["event_id"])
        assert SYNTHETIC_WARNING_TOKEN in json.loads(req["content"])["text"]

        entries = sender.ledger.entries_for_event(e1["event_id"])
        assert all(ent["user_read_receipt_proven"] == 0 for ent in entries)
        with pytest.raises(sqlite3.DatabaseError), sqlite3.connect(str(sender.ledger.db_path)) as db:
            db.execute("UPDATE h2b_delivery_ledger SET action = 'FORGED'")
    finally:
        srv.shutdown()
        srv.server_close()


def test_d2_retryable_429_5xx_permanent_and_crash_unknown_delivery_reconcile(tmp_path):
    srv, client, snap = _start_facade(tmp_path)
    try:
        t0 = snap["evaluated_at_ms"]
        # 1. Retryable 429 -> 503 -> PROVIDER_ACK
        recorder_retry = H2BMockLarkRecorder([
            SimpleNamespace(success=lambda: False, code=99991400, msg="429 rate limited cli_secret_tok", data=None),
            SimpleNamespace(success=lambda: False, code=503, msg="service unavailable", data=None),
            SimpleNamespace(success=lambda: True, code=0, msg="ok", data=SimpleNamespace(message_id="om_ack_3")),
        ])
        s_retry = HermesSingleSenderService(
            state_dir=tmp_path / "retry_state",
            binding=_binding(),
            hermes_home=tmp_path / "hhome",
            mock_lark_client=recorder_retry,
            base_backoff_ms=50,
            max_attempts=3,
        )
        s_retry.enqueue(snap, recipient="ou_owner001", now_ms=t0)
        r1 = s_retry.dispatch_next(facade_client=client, now_ms=t0 + 1)
        assert r1["state"] == "RETRYABLE"
        assert len(recorder_retry.requests) == 1  # Strictly 1 SDK call per outbox attempt (no hidden retry loop)
        r2 = s_retry.dispatch_next(facade_client=client, now_ms=r1["next_retry_at_ms"] + 1)
        assert r2["state"] == "RETRYABLE"
        r3 = s_retry.dispatch_next(facade_client=client, now_ms=r2["next_retry_at_ms"] + 1)
        assert r3["state"] == "PROVIDER_ACK" and r3["provider_message_id"] == "om_ack_3"
        # Ensure secret-like prefix redacted in ledger
        all_txt = json.dumps(s_retry.ledger.all_entries())
        assert "cli_secret_tok" not in all_txt

        # 2. Permanent 403 error
        recorder_perm = H2BMockLarkRecorder([
            SimpleNamespace(success=lambda: False, code=403, msg="permission denied by app scope", data=None),
        ])
        s_perm = HermesSingleSenderService(
            state_dir=tmp_path / "perm_state",
            binding=_binding(),
            hermes_home=tmp_path / "hhome",
            mock_lark_client=recorder_perm,
        )
        s_perm.enqueue(snap, recipient="ou_owner001", now_ms=t0)
        rp = s_perm.dispatch_next(facade_client=client, now_ms=t0 + 1)
        assert rp["state"] == "PERMANENT"

        # 3. Crash after send + timeout ambiguity -> UNKNOWN_DELIVERY quarantine; NO automatic resend!
        recorder_crash = H2BMockLarkRecorder([
            SimpleNamespace(success=lambda: True, code=0, msg="ok", data=SimpleNamespace(message_id="om_lost_before_commit")),
        ])
        s_crash = HermesSingleSenderService(
            state_dir=tmp_path / "crash_state",
            binding=_binding(),
            hermes_home=tmp_path / "hhome",
            mock_lark_client=recorder_crash,
            lease_ms=500,
        )
        enq_c = s_crash.enqueue(snap, recipient="oc_dmowner001", now_ms=t0)
        crash_out = s_crash.dispatch_next(facade_client=client, now_ms=t0 + 10, simulate_crash_after_send=True)
        assert crash_out["simulated_crash"] is True
        reclaimed = s_crash.reclaim_unknown_deliveries(now_ms=t0 + 1000)
        assert reclaimed == [enq_c["event_id"]]
        # Claiming again while in UNKNOWN_DELIVERY MUST return None (never blindly resend!)
        assert s_crash.dispatch_next(facade_client=client, now_ms=t0 + 1100) is None
        assert len(recorder_crash.requests) == 1

        # Explicit audited reconciliation
        rec_out = s_crash.reconcile_unknown(
            event_id=enq_c["event_id"],
            provider_message_id="om_reconciled_after_check",
            delivered=True,
            reconciled_at_ms=t0 + 1200,
        )
        assert rec_out["state"] == "PROVIDER_ACK"
        assert rec_out["duplicate_risk"] == 1  # Explicitly preserved duplicate risk history

        # Transport timeout raises TimeoutError -> immediate UNKNOWN_DELIVERY
        recorder_to = H2BMockLarkRecorder([TimeoutError("socket timed out")])
        s_to = HermesSingleSenderService(
            state_dir=tmp_path / "to_state",
            binding=_binding(),
            hermes_home=tmp_path / "hhome",
            mock_lark_client=recorder_to,
        )
        s_to.enqueue(snap, recipient="ou_owner001", now_ms=t0)
        rto = s_to.dispatch_next(facade_client=client, now_ms=t0 + 1)
        assert rto["state"] == "UNKNOWN_DELIVERY"
        assert s_to.dispatch_next(facade_client=client, now_ms=t0 + 5000) is None
    finally:
        srv.shutdown()
        srv.server_close()


def test_d3_expiry_and_superseded_suppression_before_send(tmp_path):
    # Superseded WATCH card in B2 early-short journal
    srv, client, _exec_snap = _start_facade(tmp_path, journal=B2_ES_JOURNAL, require_active=False)
    try:
        hist = client.call_tool("get_signal_history", {"limit": 20})["data"]["history"]
        superseded_row = next(h for h in hist if h.get("market_status") == "WATCH")
        superseded_snap = client.call_tool(
            "get_signal_detail",
            {"episode_id": superseded_row["episode_id"], "card_id": superseded_row["card_id"]},
        )["data"]["snapshot"]
        recorder = H2BMockLarkRecorder()
        sender = HermesSingleSenderService(
            state_dir=tmp_path / "sup_state",
            binding=_binding(),
            hermes_home=tmp_path / "hhome",
            mock_lark_client=recorder,
        )
        t0 = superseded_snap["evaluated_at_ms"]
        enq = sender.enqueue(superseded_snap, recipient="oc_dmowner001", now_ms=t0)
        assert enq["state"] == "READY"
        res = sender.dispatch_next(facade_client=client, now_ms=t0 + 10)
        assert res["state"] == "SUPPRESSED"
        assert len(recorder.requests) == 0  # Zero Feishu API calls sent for stale/superseded card

        # Expiry before retry transition
        srv_b5, client_b5, b5_snap = _start_facade(tmp_path / "b5", journal=B5_JOURNAL)
        try:
            abs_exp = b5_snap["absolute_expiry_ms"]
            t_fresh = b5_snap["source_as_of_ms"] + 60_000
            backoff_past_expiry = (abs_exp - t_fresh) + 60_000
            recorder_exp = H2BMockLarkRecorder([SimpleNamespace(success=lambda: False, code=429, msg="429", data=None)])
            s_exp = HermesSingleSenderService(
                state_dir=tmp_path / "exp_state",
                binding=_binding(),
                hermes_home=tmp_path / "hhome",
                mock_lark_client=recorder_exp,
                base_backoff_ms=backoff_past_expiry,
                max_backoff_ms=backoff_past_expiry,
            )
            s_exp.enqueue(b5_snap, recipient="ou_owner001", now_ms=t_fresh)
            rexp = s_exp.dispatch_next(facade_client=client_b5, now_ms=t_fresh + 1_000)
            assert rexp["state"] == "EXPIRED"
            assert rexp["suppression_reason"] == "EXPIRES_BEFORE_NEXT_RETRY"
        finally:
            srv_b5.shutdown()
            srv_b5.server_close()
    finally:
        srv.shutdown()
        srv.server_close()
