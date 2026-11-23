"""Finite, authenticated ingress from a reviewed local provider-session bridge."""

import asyncio
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from quant_hermes_feishu_h1.contract import SYNTHETIC_WARNING_TOKEN
from quant_hermes_feishu_h1.feishu_chat import FeishuChatService, FeishuInboundEvent
from quant_hermes_feishu_h2b.inbound_boundary import (
    H2BInboundBoundary,
    InboundBinding,
    InboundDedupStore,
)

from .fence import Denied, digest
from .facade import PeerVerifiedFacade

REVIEWED_INGRESS = None
MAX_FRAME = 8192


@dataclass(frozen=True)
class Frame:
    body: bytes
    mac: str


def authenticate(secret, run_id, body):
    return hmac.digest(
        secret, b"H4_WS_BRIDGE_V1\0" + run_id.encode("ascii") + b"\0" + body, "sha256"
    ).hex()


class FiniteInbound:
    """One authenticated Owner event and one deterministic reply on the same sender."""

    def __init__(self, sender, client, *, bridge_secret, events=None):
        self.sender, self.secret, self.events = sender, bridge_secret, events
        permit = sender.permit
        claim = permit.claim
        if claim.capability != "inbound":
            raise Denied("WRONG_CAPABILITY")
        if not permit.fixture and REVIEWED_INGRESS is None:
            raise Denied("LIVE_INGRESS_NOT_ACTIVATED")
        if type(bridge_secret) is not bytes or len(bridge_secret) < 32:
            raise Denied("CALLBACK_KEY_INVALID")
        if hashlib.sha256(bridge_secret).hexdigest() != claim.callback_key_sha256:
            raise Denied("CALLBACK_KEY_INVALID")
        sender.check()
        self.boundary = H2BInboundBoundary(
            binding=InboundBinding(
                app_id=claim.app,
                tenant_key=claim.tenant,
                allowed_owner_open_ids=frozenset({claim.owner}),
                owner_chat_bindings={claim.owner: claim.chat},
            ),
            dedup_store=InboundDedupStore(dict(permit.state.pins)["dedup"].path),
        )
        pinned_client = PeerVerifiedFacade(client, permit)
        pinned_client.probe()
        self.chat = FeishuChatService(
            facade_client=pinned_client,
            allowed_owner_open_ids=frozenset({claim.owner}),
            owner_chat_bindings={claim.owner: claim.chat},
        )

    def handle(self, frame, *, as_of_ms, deadline):
        permit = self.sender.permit
        claim = permit.claim
        self.sender.check()
        if (
            type(frame) is not Frame
            or type(frame.body) is not bytes
            or type(frame.mac) is not str
            or len(frame.body) > MAX_FRAME
            or not hmac.compare_digest(
                frame.mac, authenticate(self.secret, claim.run_id, frame.body)
            )
        ):
            raise Denied("UNAUTHENTICATED_CALLBACK")
        try:
            payload = json.loads(frame.body)
        except (UnicodeError, ValueError) as exc:
            raise Denied("MALFORMED_CALLBACK") from exc
        if type(payload) is not dict:
            raise Denied("MALFORMED_CALLBACK")
        self._deadline(deadline)
        permit.state.witness.check("turn")
        ok, verified, reason = self.boundary.verify_raw_feishu_event(payload, now_ms=permit.clock())
        if not ok:
            raise Denied(str(reason).split(":", 1)[0])
        if verified.clean_text != "当前机会":
            raise Denied("INBOUND_COMMAND_OUTSIDE_SCOPE")
        event_key = digest(
            [
                claim.app,
                claim.tenant,
                claim.owner,
                claim.chat,
                verified.event_id,
                verified.message_id,
            ]
        )
        permit.state.witness.spend("turn", permit.key("turn", event_key))
        if self.events is not None:
            self.events.record("INBOUND_DM", event_key)
            self.events.record("TOOL_BEGIN", event_key)
        try:
            checked_event = FeishuInboundEvent(
                message_id=verified.message_id,
                chat_id=verified.chat_id,
                chat_type=verified.chat_type,
                sender_open_id=verified.sender_open_id,
                sender_type=verified.sender_type,
                text=verified.clean_text,
                event_ts_ms=verified.event_ts_ms,
            )
            answer = self.chat.handle_inbound(
                checked_event, now_ms=permit.clock(), as_of_ms=as_of_ms
            )
        finally:
            if self.events is not None:
                self.events.record("TOOL_END", event_key)
        self._deadline(deadline)
        if not answer.get("accepted"):
            raise Denied("CORE_REPLY_UNAVAILABLE")
        text = answer["reply_text"]
        if permit.fixture and SYNTHETIC_WARNING_TOKEN not in text:
            text = f"[SYNTHETIC_QA_ONLY / {SYNTHETIC_WARNING_TOKEN}]\n{text}"
        if self.events is not None:
            self.events.record("FIRST_DM_RESPONSE", event_key, code="NO_MODEL")
        outcome = self.sender._reply(event_key, text)
        if self.events is not None:
            self.events.record(
                "FINAL_DM_REPLY",
                event_key,
                code="ACK"
                if outcome.classification == "PROVIDER_ACK"
                else "UNKNOWN_DELIVERY"
                if outcome.classification == "UNKNOWN_DELIVERY"
                else "REJECTED",
            )
        return {"status": outcome.classification, "model": "NONE", "human_read": "UNOBSERVED"}

    @staticmethod
    def _deadline(deadline):
        if time.monotonic() >= deadline:
            raise Denied("TURN_TIMEOUT")

    async def run(self, session, *, as_of_ms, timeout_s=2.0):
        """Read one externally verified frame and always close the finite session."""
        if not self.sender.permit.fixture and type(session) is not REVIEWED_INGRESS:
            raise Denied("LIVE_INGRESS_NOT_ACTIVATED")
        if not 0 < timeout_s <= 2:
            raise Denied("SESSION_WINDOW_INVALID")
        deadline = time.monotonic() + timeout_s
        try:
            frame = await asyncio.wait_for(session.receive(), timeout_s)
            return self.handle(frame, as_of_ms=as_of_ms, deadline=deadline)
        except TimeoutError as exc:
            raise Denied("TURN_TIMEOUT") from exc
        finally:
            try:
                await asyncio.wait_for(session.disconnect(), 0.25)
            except TimeoutError as exc:
                raise Denied("TEARDOWN_TIMEOUT") from exc
