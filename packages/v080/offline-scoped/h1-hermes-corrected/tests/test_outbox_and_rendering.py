"""Deterministic outbox state machine, concurrency, crash/retry, suppression, and rendering tests."""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from quant_hermes_feishu_h1.contract import (
    CONTRACT_ID,
    SYNTHETIC_WARNING_TOKEN,
    ContractError,
    canonical_json,
    compute_outbox_event_id,
)
from quant_hermes_feishu_h1.facade import (
    QuantFacadeClient,
    QuantFacadeService,
    QuantUdsServer,
)
from quant_hermes_feishu_h1.feishu_outbound import MockFeishuTransport, ScriptedOutcome
from quant_hermes_feishu_h1.journal_reader import (
    ApprovedJournalRegistry,
    ApprovedJournalSource,
)
from quant_hermes_feishu_h1.outbox import DeterministicOutbox
from quant_hermes_feishu_h1.renderer import render_signal_alert

WORKSPACES = Path(__file__).resolve().parents[2]
B2_DEMO = WORKSPACES / "lt-v080-sol62-personal-mvp-market-decision-b2-01/evidence/demo"
B5_JOURNAL = WORKSPACES / "lt-v080-personal-mvp-live-public-b5-01/evidence/replay-input/journal.sqlite"


def _start_facade(tmp_path: Path, sources: list[ApprovedJournalSource]) -> tuple[QuantUdsServer, QuantFacadeClient]:
    sock = tmp_path / "sock/facade.sock"
    reg = ApprovedJournalRegistry(sources)
    svc = QuantFacadeService(reg)
    srv = QuantUdsServer(sock, svc)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, QuantFacadeClient(sock, principal_id="hermes_quant_plugin", recipient_scope="outbox_worker")


def test_deterministic_event_id_rendering_and_synthetic_executable_banner(tmp_path):
    srv, client = _start_facade(tmp_path, [ApprovedJournalSource("b5", B5_JOURNAL)])
    try:
        active = client.call_tool("list_active_signals", {"limit": 10})["data"]["signals"][0]
        detail = client.call_tool("get_signal_detail", {"episode_id": active["episode_id"]})["data"]["snapshot"]
        assert detail["market_status"] == "EXECUTABLE"

        expected_eid = hashlib.sha256(
            canonical_json([
                CONTRACT_ID,
                "feishu",
                "ou_owner_001",
                detail["episode_id"],
                detail["card_id"],
                detail["card_version"],
                detail["market_status"],
            ]).encode("utf-8")
        ).hexdigest()
        computed = compute_outbox_event_id(
            contract_id=CONTRACT_ID,
            channel="feishu",
            recipient="ou_owner_001",
            episode_id=detail["episode_id"],
            card_id=detail["card_id"],
            card_version=detail["card_version"],
            market_status=detail["market_status"],
        )
        assert computed == expected_eid

        rendered = render_signal_alert(detail)
        assert "SYNTHETIC_QA_ONLY" in rendered
        assert SYNTHETIC_WARNING_TOKEN in rendered
        assert detail["plan"]["entry_low"] in rendered
        assert detail["plan"]["hard_stop"] in rendered
        assert detail["plan"]["targets"][0]["net_r"] in rendered
        assert "UNAVAILABLE" in rendered
    finally:
        srv.shutdown()
        srv.server_close()


def test_outbox_dedup_concurrent_workers_and_append_only_transitions(tmp_path):
    srv, client = _start_facade(tmp_path, [ApprovedJournalSource("b5", B5_JOURNAL)])
    try:
        active = client.call_tool("list_active_signals", {"limit": 10})["data"]["signals"][0]
        snap = client.call_tool("get_signal_detail", {"episode_id": active["episode_id"]})["data"]["snapshot"]
        now_ms = snap["evaluated_at_ms"] + 100

        outbox = DeterministicOutbox(tmp_path / "outbox.sqlite", allowed_recipients=frozenset({"ou_owner_001"}))
        # Concurrent idempotent enqueue
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(
                pool.map(
                    lambda _: outbox.enqueue_snapshot(snap, recipient="ou_owner_001", now_ms=now_ms),
                    range(12),
                )
            )
        non_dedup = [r for r in results if not r["deduplicated"]]
        assert len(non_dedup) == 1
        eid = non_dedup[0]["event_id"]

        # Concurrent claim: only 1 worker may claim the single READY row
        with ThreadPoolExecutor(max_workers=4) as pool:
            claims = list(pool.map(lambda i: outbox.claim_next(worker_id=f"w-{i}", now_ms=now_ms + 5), range(4)))
        winners = [c for c in claims if c is not None]
        assert len(winners) == 1

        transport = MockFeishuTransport([ScriptedOutcome("PROVIDER_ACK", message_id="om_ok_1", http_status=200)])
        final = outbox.process_claimed(winners[0], facade_client=client, transport=transport, worker_id="w-0", now_ms=now_ms + 10)
        assert final["state"] == "PROVIDER_ACK"
        assert final["provider_message_id"] == "om_ok_1"
        assert final["user_read_receipt_proven"] == 0

        # Verify outbox_transitions is append-only (UPDATE/DELETE rejected by SQLite trigger)
        transitions = outbox.get_transitions(eid)
        assert [t["to_state"] for t in transitions] == ["CREATED", "READY", "ATTEMPTED", "PROVIDER_ACK"]
        conn = sqlite3.connect(str(tmp_path / "outbox.sqlite"))
        with pytest.raises(sqlite3.DatabaseError, match="H1_OUTBOX_APPEND_ONLY"):
            conn.execute("DELETE FROM outbox_transitions")
        conn.close()
    finally:
        srv.shutdown()
        srv.server_close()


def test_outbox_crash_unknown_delivery_delayed_ack_and_retry_matrix(tmp_path):
    srv, client = _start_facade(
        tmp_path,
        [
            ApprovedJournalSource("b5", B5_JOURNAL),
            ApprovedJournalSource("el", B2_DEMO / "early-long/decision.sqlite"),
        ],
    )
    try:
        active_list = client.call_tool("list_active_signals", {"limit": 10})["data"]["signals"]
        snap1 = client.call_tool("get_signal_detail", {"episode_id": active_list[0]["episode_id"]})["data"]["snapshot"]
        snap2 = client.call_tool("get_signal_detail", {"episode_id": active_list[1]["episode_id"]})["data"]["snapshot"]
        now_ms = max(snap1["evaluated_at_ms"], snap2["evaluated_at_ms"]) + 100

        outbox = DeterministicOutbox(
            tmp_path / "outbox.sqlite",
            allowed_recipients=frozenset({"ou_owner_001"}),
            max_attempts=3,
            base_backoff_ms=500,
            lease_ms=1000,
        )

        # Scenario A: crash during send -> lease expires -> UNKNOWN_DELIVERY -> delayed message_id reconcile
        enq1 = outbox.enqueue_snapshot(snap1, recipient="ou_owner_001", now_ms=now_ms)
        claim1 = outbox.claim_next(worker_id="crash-worker", now_ms=now_ms + 10)
        crash_t = MockFeishuTransport([ScriptedOutcome("PROVIDER_ACK", message_id="om_lost_before_commit")])
        crash_res = outbox.process_claimed(
            claim1,
            facade_client=client,
            transport=crash_t,
            worker_id="crash-worker",
            now_ms=now_ms + 20,
            simulate_crash_after_send=True,
        )
        assert crash_res["simulated_crash"] is True
        assert outbox.get_event(enq1["event_id"])["state"] == "ATTEMPTED"

        reclaimed = outbox.reclaim_expired_leases(now_ms=now_ms + 2000)
        assert reclaimed == [enq1["event_id"]]
        ev_unknown = outbox.get_event(enq1["event_id"])
        assert ev_unknown["state"] == "UNKNOWN_DELIVERY"
        assert ev_unknown["duplicate_risk"] == 1
        assert ev_unknown["reconciliation_required"] == 1

        # Reconcile delayed message_id arrives later
        reconciled = outbox.reconcile_delayed_ack(
            event_id=enq1["event_id"],
            provider_message_id="om_delayed_reconciled_99",
            ack_at_ms=now_ms + 2500,
        )
        assert reconciled["state"] == "PROVIDER_ACK"
        assert reconciled["provider_message_id"] == "om_delayed_reconciled_99"
        assert reconciled["duplicate_risk"] == 1  # Explicitly preserved!
        assert reconciled["user_read_receipt_proven"] == 0

        # Scenario B: 429 retryable -> 503 retryable -> max retry exhausted -> PERMANENT
        outbox.enqueue_snapshot(snap2, recipient="ou_owner_001", now_ms=now_ms)
        t_retry = MockFeishuTransport([
            ScriptedOutcome("RETRYABLE", http_status=429, error_code="429", error_detail="rate limit"),
            ScriptedOutcome("RETRYABLE", http_status=503, error_code="503", error_detail="unavailable"),
            ScriptedOutcome("RETRYABLE", http_status=502, error_code="502", error_detail="bad gateway"),
        ])
        cur_t = now_ms + 100
        for step in range(3):
            c = outbox.claim_next(worker_id="retry-worker", now_ms=cur_t)
            assert c is not None
            res = outbox.process_claimed(c, facade_client=client, transport=t_retry, worker_id="retry-worker", now_ms=cur_t + 5)
            if step < 2:
                assert res["state"] == "RETRYABLE"
                cur_t = res["next_retry_at_ms"] + 1
            else:
                assert res["state"] == "PERMANENT"
                assert res["last_error_code"] == "RETRY_BUDGET_EXHAUSTED"
    finally:
        srv.shutdown()
        srv.server_close()


def test_outbox_suppresses_superseded_expired_and_expiry_before_retry(tmp_path):
    # Use pullback-short: card_0=WATCH, card_1=EXECUTABLE, card_2=INVALID (STRUCTURAL_INVALIDATION)
    srv, client = _start_facade(
        tmp_path,
        [ApprovedJournalSource("ps", B2_DEMO / "pullback-short/decision.sqlite")],
    )
    try:
        hist = client.call_tool("get_signal_history", {"limit": 10})["data"]["history"]
        ordered = sorted(hist, key=lambda h: h["evaluated_at_ms"])
        exec_card = ordered[1]  # card_1 = EXECUTABLE (superseded by card_2 INVALID and card_3 INVALID)
        snap_exec = client.call_tool(
            "get_signal_detail",
            {"episode_id": exec_card["episode_id"], "card_id": exec_card["card_id"]},
        )["data"]["snapshot"]

        outbox = DeterministicOutbox(
            tmp_path / "outbox.sqlite",
            allowed_recipients=frozenset({"ou_owner_001"}),
            base_backoff_ms=60_000,
        )
        t_ok = MockFeishuTransport()

        # 1. Superseded EXECUTABLE card must be SUPPRESSED before send; transport must NOT be called!
        enq = outbox.enqueue_snapshot(snap_exec, recipient="ou_owner_001", now_ms=snap_exec["evaluated_at_ms"] + 10)
        assert enq["state"] == "READY"
        claimed = outbox.claim_next(worker_id="sup-worker", now_ms=snap_exec["evaluated_at_ms"] + 20)
        res = outbox.process_claimed(
            claimed,
            facade_client=client,
            transport=t_ok,
            worker_id="sup-worker",
            now_ms=snap_exec["evaluated_at_ms"] + 25,
        )
        assert res["state"] == "SUPPRESSED"
        assert "SUPERSEDED_BY:" in res["suppression_reason"]
        assert len(t_ok.sent_records) == 0

        # 2. Card expiring between enqueue and send -> EXPIRED before send; transport NOT called!
        srv2, client2 = _start_facade(tmp_path / "exp_srv", [ApprovedJournalSource("b5", B5_JOURNAL)])
        try:
            b5_sig = client2.call_tool("list_active_signals", {"limit": 5})["data"]["signals"][0]
            b5_snap = client2.call_tool("get_signal_detail", {"episode_id": b5_sig["episode_id"]})["data"]["snapshot"]
            abs_exp = b5_snap["absolute_expiry_ms"]
            outbox2 = DeterministicOutbox(
                tmp_path / "outbox2.sqlite",
                allowed_recipients=frozenset({"ou_owner_001"}),
                base_backoff_ms=100_000,
            )
            enq_exp = outbox2.enqueue_snapshot(b5_snap, recipient="ou_owner_001", now_ms=abs_exp - 500)
            assert enq_exp["state"] == "READY"
            # Claim just before expiry, but recheck occurs at or after expiry
            claimed_exp = outbox2.claim_next(worker_id="exp-worker", now_ms=abs_exp - 10)
            res_exp = outbox2.process_claimed(
                claimed_exp,
                facade_client=client2,
                transport=t_ok,
                worker_id="exp-worker",
                now_ms=abs_exp + 1,
            )
            assert res_exp["state"] == "EXPIRED"
            assert len(t_ok.sent_records) == 0

            # 3. Retry scheduled after absolute_expiry_ms -> transitions immediately to EXPIRED
            t_fresh = b5_snap["source_as_of_ms"] + 60_000
            backoff_past_expiry = (abs_exp - t_fresh) + 60_000
            outbox3 = DeterministicOutbox(
                tmp_path / "outbox3.sqlite",
                allowed_recipients=frozenset({"ou_owner_001"}),
                base_backoff_ms=backoff_past_expiry,
                max_backoff_ms=backoff_past_expiry,
            )
            outbox3.enqueue_snapshot(b5_snap, recipient="ou_owner_001", now_ms=t_fresh)
            c_r = outbox3.claim_next(worker_id="exp-retry", now_ms=t_fresh + 1_000)
            t_429 = MockFeishuTransport([ScriptedOutcome("RETRYABLE", http_status=429, error_code="429", error_detail="429")])
            res_r = outbox3.process_claimed(
                c_r,
                facade_client=client2,
                transport=t_429,
                worker_id="exp-retry",
                now_ms=t_fresh + 2_000,
            )
            assert res_r["state"] == "EXPIRED"
            assert res_r["suppression_reason"] == "EXPIRES_BEFORE_NEXT_RETRY"

            # 4. Unauthorized recipient rejected at enqueue
            with pytest.raises(ContractError) as exc_unauth:
                outbox3.enqueue_snapshot(b5_snap, recipient="ou_attacker", now_ms=abs_exp - 60_000)
            assert exc_unauth.value.code == "UNAUTHORIZED"
        finally:
            srv2.shutdown()
            srv2.server_close()
    finally:
        srv.shutdown()
        srv.server_close()
