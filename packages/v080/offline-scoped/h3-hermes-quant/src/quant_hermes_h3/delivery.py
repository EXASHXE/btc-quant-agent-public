"""H3 policy around the accepted deterministic outbox and Hermes sender."""

from quant_hermes_feishu_h1.contract import SYNTHETIC_WARNING_TOKEN, ContractError
from quant_hermes_feishu_h1.renderer import render_signal_alert
from quant_hermes_feishu_h2b.outbound_sender import (
    H2BMockLarkRecorder,
    HermesSingleSenderService,
    compute_snapshot_event_id,
)
from quant_personal_live_public_b5.contract import QA

from .telemetry import correlate


def alert_snapshot(envelope, *, episode, card, now_ms):
    if envelope.get("status") != "OK":
        raise ContractError("SOURCE_BLOCKED", "Verified current card unavailable")
    data = envelope["data"]
    snapshot = data["snapshot"]
    reasons = (
        (snapshot["episode_id"] != episode or snapshot["card_id"] != card, "IDENTITY_MISMATCH"),
        (
            not snapshot["card_version"]
            or data["latest_card_version"] != snapshot["card_version"]
            or data["is_superseded"],
            "SUPERSEDED",
        ),
        (
            snapshot["market_status"] != "EXECUTABLE" or snapshot.get("reasons") is None,
            "NON_AFFIRMATIVE",
        ),
        (
            envelope["source_evidence_class"] != QA
            or snapshot["source_evidence_class"] != QA
            or snapshot.get("source_origin") != QA
            or not snapshot["not_a_real_trade_signal"],
            "EVIDENCE_MISMATCH",
        ),
        (
            not snapshot["source_receipt_sha256"] or not snapshot["source_publication_sha256"],
            "MISSING_PROVENANCE",
        ),
        (
            snapshot["freshness_state"] != "CURRENT"
            or type(snapshot["source_as_of_ms"]) is not int
            or snapshot["source_as_of_ms"] > now_ms,
            "STALE",
        ),
        (
            not snapshot["absolute_expiry_ms"]
            or snapshot["is_expired"]
            or now_ms >= snapshot["absolute_expiry_ms"],
            "EXPIRED",
        ),
        (
            snapshot["account_context_status"] != "UNAVAILABLE"
            or snapshot["safe_position_size"] != "UNKNOWN",
            "ACCOUNT_BOUNDARY",
        ),
    )
    for failed, reason in reasons:
        if failed:
            raise ContractError("SOURCE_BLOCKED", reason)
    return snapshot


class MockProvider(H2BMockLarkRecorder):
    """Observe each actual attempted Lark create at the mock provider edge."""

    def __init__(self, measurements, responses=None):
        super().__init__(responses)
        self.measurements = measurements
        self.correlation = None

    def _handle(self, op, request):
        self.measurements.record("SENDER_ATTEMPT", self.correlation, code="MOCK")
        result = super()._handle(op, request)
        if result.success():
            self.measurements.record("PROVIDER_ACK", self.correlation, code="ACK")
        return result


class Delivery:
    def __init__(self, home, binding, hermes_home, client, permit, measurements, *, responses=None):
        self.client, self.permit, self.measurements = client, permit, measurements
        self.mock = MockProvider(measurements, responses)
        self.sender = HermesSingleSenderService(
            state_dir=home,
            binding=binding,
            hermes_home=hermes_home,
            mock_lark_client=self.mock,
            offline_mock_only=True,
            lease_ms=1_000,
        )
        self.recipient = binding.authorized_dm_chat_id

    def _detail(self, episode, card, now_ms):
        return self.client.call_tool(
            "get_signal_detail",
            {"episode_id": episode, "card_id": card, "as_of_ms": now_ms},
            recipient_scope="outbox_worker",
        )

    def enqueue(self, episode, card, *, now_ms, correlation):
        self.permit.check()
        snapshot = alert_snapshot(
            self._detail(episode, card, now_ms), episode=episode, card=card, now_ms=now_ms
        )
        canonical = compute_snapshot_event_id(snapshot, recipient=self.recipient)
        outcome = self.sender.enqueue(snapshot, recipient=self.recipient, now_ms=now_ms)
        if outcome["event_id"] != canonical:
            raise ContractError("INTEGRITY_FAILURE", "Outbox event identity mismatch")
        event = "DUPLICATE" if outcome["deduplicated"] else "OUTBOX_ENQUEUE"
        self.measurements.record(
            event, correlation, code="DUPLICATE" if outcome["deduplicated"] else "OK"
        )
        return outcome

    def dispatch(self, *, now_ms, correlation, crash=False):
        """Before every attempt, H1 rechecks the facade and H3 fences the wire edge."""
        owner = self
        transport = self.sender.transport

        class RecheckedTransport:
            offline_mock_only = True

            @property
            def used_hermes_adapter(self):
                return transport.used_hermes_adapter

            def send_text(self, *, channel, recipient, text, event_id, attempt):
                owner.permit.check()
                row = owner.sender.outbox.get_event(event_id)
                snapshot = alert_snapshot(
                    owner._detail(row["episode_id"], row["card_id"], now_ms),
                    episode=row["episode_id"],
                    card=row["card_id"],
                    now_ms=now_ms,
                )
                if (
                    recipient != owner.recipient
                    or row["recipient"] != recipient
                    or channel != "feishu"
                    or event_id != compute_snapshot_event_id(snapshot, recipient=recipient)
                    or row["card_version"] != snapshot["card_version"]
                    or SYNTHETIC_WARNING_TOKEN not in text
                    or text != render_signal_alert(snapshot)
                ):
                    raise ContractError("INTEGRITY_FAILURE", "Outbox identity/evidence fail-closed")
                owner.mock.correlation = correlation
                return transport.send_text(
                    channel=channel,
                    recipient=recipient,
                    text=text,
                    event_id=event_id,
                    attempt=attempt,
                )

        self.permit.check()
        self.sender.transport = RecheckedTransport()
        try:
            outcome = self.sender.dispatch_next(
                facade_client=self.client, now_ms=now_ms, simulate_crash_after_send=crash
            )
        finally:
            self.sender.transport = transport
        if outcome and outcome["state"] in {
            "RETRYABLE",
            "PERMANENT",
            "UNKNOWN_DELIVERY",
            "SUPPRESSED",
            "EXPIRED",
        }:
            self.measurements.record("DELIVERY_FAILURE", correlation, code=outcome["state"])
        return outcome

    def send_reply(self, *, callback_id, text, correlation):
        """Same sender fence and transport, with one dispatch per admitted callback."""
        self.permit.check()
        if SYNTHETIC_WARNING_TOKEN not in text:
            raise ContractError("INTEGRITY_FAILURE", "Synthetic reply banner required")
        event_id = correlate("h3-offline-reply", callback_id)
        with self.sender._exclusive_sender_fence():
            self.permit.check()
            self.mock.correlation = correlation
            return self.sender.transport.send_text(
                channel="feishu",
                recipient=self.recipient,
                text=text,
                event_id=event_id,
                attempt=1,
            )
