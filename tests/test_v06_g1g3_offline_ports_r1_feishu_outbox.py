"""22 deterministic tests for FeishuOutboxPort (dedup/reorder, loopback HTTP codes, retry/backoff, no stop delay, zero portfolio mutation)."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.g1_offline_preview_r1.model import SafetyViolation, digest  # noqa: E402
from scripts.g1_offline_preview_r1.reducer import transition  # noqa: E402
from scripts.g1g3_offline_ports_r1.crypto_ed25519 import (  # noqa: E402
    SYNTHETIC_TEST_OPERATOR_SEEDS,
)
from scripts.g1g3_offline_ports_r1.feishu_outbox_port import FeishuOutboxPort  # noqa: E402
from scripts.g1g3_offline_ports_r1.loopback_servers import (  # noqa: E402
    FakeLoopbackFeishuServer,
)
from scripts.g1g3_offline_ports_r1.no_order_port import (  # noqa: E402
    LoopbackSocketGuard,
    NoOrderPort,
)
from tests.test_v06_g1_offline_preview_r1_core import (  # noqa: E402
    analyzed,
    ev,
    next_bar,
    open_position,
)


def _make_card(
    port: FeishuOutboxPort,
    *,
    dedup_id: str = "msg-001",
    category: str = "APPROVED_INFO",
    event_kind: str = "APPROVE",
    phase: str = "APPROVED",
    at: int = 60002,
    summary: str = "Operator approved signal s1 (informational only)",
    reject_raw_secrets: bool = False,
) -> dict:
    return port.build_card(
        deduplication_id=dedup_id,
        card_category=category,
        event_kind=event_kind,
        phase=phase,
        at=at,
        trace_id=digest([dedup_id, event_kind])[:24],
        source_hash=digest({"bar": 0}),
        signal_id="s1",
        summary_text=summary,
        reject_raw_secrets=reject_raw_secrets,
    )


def test_01_default_local_wal_delivery_produces_deterministic_sha_receipt(
    tmp_path: Path,
) -> None:
    port = FeishuOutboxPort(tmp_path, temporary=True)
    card = _make_card(port)
    rec = port.deliver_card(card)
    assert rec["delivered"] is True
    assert rec["transport"] == "LOCAL_JSONL_WAL_ONLY"
    assert rec["deduplication_id"] == "msg-001"
    assert rec["payload_sha256"] == card["payload_sha256"]
    assert len(rec["receipt_sha256"]) == 64


def test_02_loopback_http_200_delivery_and_idempotent_dedup(tmp_path: Path) -> None:
    with FakeLoopbackFeishuServer(mode="OK_200") as srv:
        allowed = {(srv.host, srv.port)}
        with LoopbackSocketGuard(allow_loopback=True, allowed_endpoints=allowed):
            port = FeishuOutboxPort(
                tmp_path,
                endpoint_url=srv.endpoint_url,
                allow_loopback=True,
                allowed_endpoints=allowed,
                temporary=True,
            )
            card = _make_card(port, dedup_id="msg-loop-200")
            r1 = port.deliver_card(card)
            assert r1["http_status"] == 200
            assert r1["dedup_status"] == "FIRST_DELIVERY"
            assert srv.request_count == 1

            # Re-delivering identical card is deduplicated locally without extra network hit
            r2 = port.deliver_card(card)
            assert r2["dedup_status"] == "IDEMPOTENT_DUPLICATE"
            assert r2["receipt_sha256"] == r1["receipt_sha256"]
            assert srv.request_count == 1


def test_03_out_of_order_delivery_and_server_side_dedup_on_new_port(
    tmp_path: Path,
) -> None:
    with FakeLoopbackFeishuServer(mode="OK_200") as srv:
        allowed = {(srv.host, srv.port)}
        with LoopbackSocketGuard(allow_loopback=True, allowed_endpoints=allowed):
            p1 = FeishuOutboxPort(
                tmp_path / "p1",
                endpoint_url=srv.endpoint_url,
                allow_loopback=True,
                allowed_endpoints=allowed,
                temporary=True,
            )
            c1 = _make_card(p1, dedup_id="msg-order-1", at=60001)
            c2 = _make_card(p1, dedup_id="msg-order-2", at=60002)
            # Deliver out of chronological order: c2 then c1
            rec2 = p1.deliver_card(c2)
            rec1 = p1.deliver_card(c1)
            assert rec2["delivered"] and rec1["delivered"]
            assert set(srv.delivered_by_dedup_id.keys()) == {"msg-order-1", "msg-order-2"}

            # Second client sending c1 again receives server-side IDEMPOTENT_DEDUP with same receipt_sha256
            p2 = FeishuOutboxPort(
                tmp_path / "p2",
                endpoint_url=srv.endpoint_url,
                allow_loopback=True,
                allowed_endpoints=allowed,
                temporary=True,
            )
            rec1_again = p2.deliver_card(c1)
            assert rec1_again["dedup_status"] == "IDEMPOTENT_DEDUP"
            assert rec1_again["receipt_sha256"] == rec1["receipt_sha256"]


def test_04_dedup_payload_drift_rejected(tmp_path: Path) -> None:
    port = FeishuOutboxPort(tmp_path, temporary=True)
    c1 = _make_card(port, dedup_id="msg-drift", summary="Original summary")
    port.deliver_card(c1)
    c1_mut = _make_card(port, dedup_id="msg-drift", summary="Mutated summary")
    with pytest.raises(SafetyViolation, match="FEISHU_DEDUP_PAYLOAD_DRIFT"):
        port.deliver_card(c1_mut)


@pytest.mark.parametrize(
    ("bad_url", "allow_loopback", "expected_code"),
    [
        (
            "https://open.feishu.cn/open-apis/bot/v2/hook/real",
            True,
            "EXTERNAL_PROVIDER_ENDPOINT_FORBIDDEN",
        ),
        (
            "https://open.larksuite.com/open-apis/im/v1/messages",
            True,
            "EXTERNAL_PROVIDER_ENDPOINT_FORBIDDEN",
        ),
        ("http://127.0.0.1:9999/open-apis/im/v1/messages", False, "NETWORK_DISABLED_BY_DEFAULT"),
        ("http://127.0.0.1:9999/open-apis/im/v1/messages", True, "LOOPBACK_PORT_NOT_ALLOWLISTED"),
    ],
)
def test_05_to_08_real_network_and_unallowlisted_endpoints_blocked(
    tmp_path: Path, bad_url: str, allow_loopback: bool, expected_code: str
) -> None:
    no_order = NoOrderPort()
    port = FeishuOutboxPort(
        tmp_path,
        endpoint_url=bad_url,
        allow_loopback=allow_loopback,
        allowed_endpoints=set(),
        no_order_port=no_order,
        temporary=True,
    )
    card = _make_card(port, dedup_id=f"msg-{expected_code}")
    with pytest.raises(SafetyViolation, match=expected_code):
        port.deliver_card(card)
    assert no_order.actual_private_or_network_calls == 0


@pytest.mark.parametrize(
    ("mode", "expected_code", "expected_attempts"),
    [
        ("HTTP_400", "FEISHU_HTTP_400", 1),
        ("HTTP_401", "FEISHU_HTTP_401", 1),
        ("HTTP_429", "FEISHU_RETRY_CAP_EXHAUSTED_HTTP_429", 3),
        ("HTTP_500", "FEISHU_RETRY_CAP_EXHAUSTED_HTTP_500", 3),
    ],
)
def test_09_to_12_http_error_responses_and_retry_cap(
    tmp_path: Path, mode: str, expected_code: str, expected_attempts: int
) -> None:
    with FakeLoopbackFeishuServer(mode=mode) as srv:
        allowed = {(srv.host, srv.port)}
        with LoopbackSocketGuard(allow_loopback=True, allowed_endpoints=allowed):
            port = FeishuOutboxPort(
                tmp_path,
                endpoint_url=srv.endpoint_url,
                allow_loopback=True,
                allowed_endpoints=allowed,
                max_attempts=3,
                base_backoff_ms=5,
                temporary=True,
            )
            card = _make_card(port, dedup_id=f"msg-{mode}")
            with pytest.raises(SafetyViolation, match=expected_code):
                port.deliver_card(card)
            assert srv.request_count == expected_attempts
            if expected_attempts == 3:
                assert port.backoff_history_ms == [5, 10]


def test_13_http_503_transient_recovery_with_exponential_backoff(tmp_path: Path) -> None:
    with FakeLoopbackFeishuServer(mode="RECOVER_503", fail_count=2) as srv:
        allowed = {(srv.host, srv.port)}
        with LoopbackSocketGuard(allow_loopback=True, allowed_endpoints=allowed):
            port = FeishuOutboxPort(
                tmp_path,
                endpoint_url=srv.endpoint_url,
                allow_loopback=True,
                allowed_endpoints=allowed,
                max_attempts=3,
                base_backoff_ms=5,
                temporary=True,
            )
            card = _make_card(port, dedup_id="msg-recover-503")
            rec = port.deliver_card(card)
            assert rec["delivered"] is True
            assert rec["attempts"] == 3
            assert srv.request_count == 3
            assert port.backoff_history_ms == [5, 10]


def test_14_socket_timeout_exhausts_retry_cap_and_fails_closed(tmp_path: Path) -> None:
    with FakeLoopbackFeishuServer(mode="TIMEOUT") as srv:
        allowed = {(srv.host, srv.port)}
        with LoopbackSocketGuard(allow_loopback=True, allowed_endpoints=allowed):
            port = FeishuOutboxPort(
                tmp_path,
                endpoint_url=srv.endpoint_url,
                allow_loopback=True,
                allowed_endpoints=allowed,
                max_attempts=2,
                base_backoff_ms=5,
                timeout_ms=60,
                temporary=True,
            )
            card = _make_card(port, dedup_id="msg-timeout")
            with pytest.raises(SafetyViolation, match="FEISHU_TIMEOUT_EXHAUSTED"):
                port.deliver_card(card)
            assert srv.request_count == 2


def test_15_force_stop_never_delayed_by_held_outbox_and_no_portfolio_mutation(
    tmp_path: Path,
) -> None:
    # Open position and hit a STOP bar -> state["required_exit"] is set to STOP
    s = next_bar(open_position(), last="94", high="95", low="93")
    assert s["required_exit"]["kind"] == "STOP"
    port = FeishuOutboxPort(tmp_path, temporary=True)

    # Outbox cannot run ahead of a pending mandatory STOP exit
    with pytest.raises(SafetyViolation, match="REQUIRED_EXIT_PRECEDES_OUTBOX_DELIVERY"):
        port.deliver_state_outbox(s)

    # Mandatory STOP executes immediately in reducer without waiting for outbox
    s_stopped = transition(s, ev("STOP", s["last_at"], {"fill_id": "stop-immediate"}))
    assert s_stopped["phase"] == "EXIT_WAIT_ACK"
    assert s_stopped["remaining_qty"] == "0.00"
    assert s_stopped["required_exit"] is None

    # Now outbox delivers all rows without mutating cash, journal, or approvals
    before_state = copy.deepcopy(s_stopped)
    receipts = port.deliver_state_outbox(s_stopped)
    assert len(receipts) == len(s_stopped["outbox"])
    assert s_stopped == before_state


def test_16_outbox_ack_and_retries_never_duplicate_human_approval_or_mutate_cash(
    tmp_path: Path,
) -> None:
    s = analyzed()
    s = transition(s, ev("APPROVE", 60002, {"token_id": "human1"}))
    cash_before = s["cash"]
    used_tokens_before = list(s["used_tokens"])
    approval_before = copy.deepcopy(s["approval"])

    with FakeLoopbackFeishuServer(mode="RECOVER_503", fail_count=2) as srv:
        allowed = {(srv.host, srv.port)}
        with LoopbackSocketGuard(allow_loopback=True, allowed_endpoints=allowed):
            port = FeishuOutboxPort(
                tmp_path,
                endpoint_url=srv.endpoint_url,
                allow_loopback=True,
                allowed_endpoints=allowed,
                max_attempts=3,
                base_backoff_ms=2,
                temporary=True,
            )
            receipts = port.deliver_state_outbox(s)
            assert len(receipts) == 3
            for r in receipts:
                s = transition(
                    s,
                    ev(
                        "OUTBOX_RECEIPT",
                        s["last_at"],
                        {"message_id": r["deduplication_id"]},
                        label=f"rcpt-{r['deduplication_id'][:8]}",
                    ),
                )
    assert s["cash"] == cash_before
    assert s["used_tokens"] == used_tokens_before
    assert s["approval"] == approval_before
    assert s["journal"] == []


def test_17_accidental_credential_patterns_redacted_in_card_summary(
    tmp_path: Path,
) -> None:
    port = FeishuOutboxPort(tmp_path, temporary=True)
    card = _make_card(
        port,
        dedup_id="msg-redact",
        summary="Alert api_key=SECRET123 password=HIDDEN bearer TOK999",
        reject_raw_secrets=False,
    )
    assert "SECRET123" not in card["summary_text"]
    assert "HIDDEN" not in card["summary_text"]
    assert "TOK999" not in card["summary_text"]
    assert "[REDACTED]" in card["summary_text"]


@pytest.mark.parametrize(
    "secret_payload",
    [
        "-----BEGIN PRIVATE KEY----- MIIEvgIBADANBgkqhkiG9w0BAQE",
        f"leaked_seed={SYNTHETIC_TEST_OPERATOR_SEEDS['ed25519-offline-op-alpha-v1'].hex()}",
        "raw credential api_key=UNREDACTED_BLOCK",
    ],
)
def test_18_to_20_private_keys_and_seeds_rejected_fail_closed(
    tmp_path: Path, secret_payload: str
) -> None:
    port = FeishuOutboxPort(tmp_path, temporary=True)
    with pytest.raises(SafetyViolation, match="FEISHU_SECRET_CONTENT_BLOCKED"):
        _make_card(
            port,
            dedup_id="msg-secret-block",
            summary=secret_payload,
            reject_raw_secrets=True,
        )


def test_21_durable_wal_recovery_and_truncated_wal_rejection(tmp_path: Path) -> None:
    p1 = FeishuOutboxPort(tmp_path, temporary=True)
    c1 = _make_card(p1, dedup_id="msg-persist-1")
    r1 = p1.deliver_card(c1)

    # Re-open on same directory and verify receipt recovered
    p2 = FeishuOutboxPort(tmp_path, temporary=True)
    assert "msg-persist-1" in p2.receipts_by_dedup_id
    r2 = p2.deliver_card(c1)
    assert r2["dedup_status"] == "IDEMPOTENT_DUPLICATE"
    assert r2["receipt_sha256"] == r1["receipt_sha256"]

    # Truncate WAL and verify fail-closed
    raw = p2.wal_path.read_bytes()
    p2.wal_path.write_bytes(raw[:-1])
    with pytest.raises(SafetyViolation, match="FEISHU_WAL_TRUNCATED"):
        FeishuOutboxPort(tmp_path, temporary=True)


def test_22_card_tampered_payload_hash_rejected_on_deliver(tmp_path: Path) -> None:
    port = FeishuOutboxPort(tmp_path, temporary=True)
    card = _make_card(port, dedup_id="msg-tamper")
    card["summary_text"] = "Tampered after payload_sha256 calculation"
    with pytest.raises(SafetyViolation, match="FEISHU_CARD_HASH_MISMATCH"):
        port.deliver_card(card)
