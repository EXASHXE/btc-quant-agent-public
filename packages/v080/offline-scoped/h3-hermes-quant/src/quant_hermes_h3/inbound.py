"""Hermes-shaped private DM callbacks, H2-B admission and Core-owned replies."""

import asyncio
import json
import time
from contextlib import closing

from quant_hermes_feishu_h1.contract import SYNTHETIC_WARNING_TOKEN
from quant_hermes_feishu_h1.feishu_chat import FeishuChatService, FeishuInboundEvent
from quant_hermes_feishu_h1.renderer import render_suppressed_notice
from quant_hermes_feishu_h2b.inbound_boundary import (
    H2BInboundBoundary,
    InboundBinding,
    InboundDedupStore,
)
from quant_hermes_feishu_h2b.outbound_sender import OutboundBinding
from quant_personal_live_public_b5.contract import QA

from .agent import LocalSession, explain
from .telemetry import correlate

APP = "cli_h3synthetic01"
TENANT = "tenant_h3_synthetic"
OPEN_ID = "ou_h3synthetic01"
CHAT = "oc_h3synthetic01"
TOKEN = "h3-offline-callback-marker"
BANNER = f"[{QA} / {SYNTHETIC_WARNING_TOKEN}]"


def binding():
    return OutboundBinding(
        app_id=APP, tenant_key=TENANT, owner_open_id=OPEN_ID, authorized_dm_chat_id=CHAT
    )


def mock_callback(
    *,
    number,
    text,
    ts,
    app=APP,
    tenant=TENANT,
    owner=OPEN_ID,
    chat=CHAT,
    token=TOKEN,
    chat_type="p2p",
    message_number=None,
):
    """Construct the accepted Lark SDK object plus Hermes-normalized metadata."""
    from gateway.config import Platform
    from gateway.platforms.base import MessageEvent
    from gateway.session import SessionSource
    from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

    message_id = f"om_h3_{number if message_number is None else message_number}"
    raw = P2ImMessageReceiveV1(
        {
            "schema": "2.0",
            "header": {
                "event_id": f"ev_h3_{number}",
                "event_type": "im.message.receive_v1",
                "create_time": str(ts),
                "token": token,
                "app_id": app,
                "tenant_key": tenant,
            },
            "event": {
                "sender": {
                    "sender_id": {"open_id": owner},
                    "sender_type": "user",
                    "tenant_key": tenant,
                },
                "message": {
                    "message_id": message_id,
                    "chat_id": chat,
                    "chat_type": chat_type,
                    "message_type": "text",
                    "content": json.dumps({"text": text}),
                    "create_time": ts,
                },
            },
        }
    )
    return MessageEvent(
        text=text,
        raw_message=raw,
        message_id=message_id,
        source=SessionSource(
            platform=Platform.FEISHU,
            chat_id=chat,
            user_id=owner,
            chat_type="dm" if chat_type == "p2p" else "group",
        ),
    )


class ObservedClient:
    def __init__(self, client, measurements, turn):
        self.client, self.measurements, self.turn = client, measurements, turn
        self.index = 0
        self.detail = None

    def call_tool(self, name, args=None, **kwargs):
        self.index += 1
        key = correlate(self.turn, "deterministic-tool", self.index)
        self.measurements.record("TOOL_BEGIN", key)
        try:
            result = self.client.call_tool(name, args, **kwargs)
            if name == "get_signal_detail" and result["status"] == "OK":
                self.detail = result["data"]
            return result
        finally:
            self.measurements.record("TOOL_END", key)


class PrivateDm:
    def __init__(self, state, client, permit, delivery, measurements):
        self.client, self.permit, self.delivery, self.measurements = (
            client,
            permit,
            delivery,
            measurements,
        )
        self.boundary = H2BInboundBoundary(
            binding=InboundBinding(
                app_id=APP,
                tenant_key=TENANT,
                allowed_owner_open_ids=frozenset({OPEN_ID}),
                owner_chat_bindings={OPEN_ID: CHAT},
                verification_token=TOKEN,
                rate_limit_max=32,
            ),
            dedup_store=InboundDedupStore(state / "inbound.sqlite"),
        )
        self.services = {}
        self.busy = set()

    def _reject(self, code):
        slot = correlate("h3-rejected", len(self.measurements.rows()))
        self.measurements.record("INBOUND_REJECT", slot, code="REJECTED")
        if code in {"DUPLICATE_EVENT_ID", "DUPLICATE_MESSAGE_ID"}:
            self.measurements.record("DUPLICATE", slot, code="DUPLICATE")
        return {"accepted": False, "error_code": code, "sent": False}

    async def handle(self, event, *, now_ms, as_of_ms, script=None, deadline_s=2.0):
        from gateway.config import Platform
        from gateway.platforms.base import MessageEvent
        from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

        self.permit.check()
        deadline = time.monotonic() + deadline_s
        if (
            type(event) is not MessageEvent
            or type(event.raw_message) is not P2ImMessageReceiveV1
            or event.source is None
            or event.source.platform is not Platform.FEISHU
            or not event.source.user_id
            or not event.source.chat_id
        ):
            return self._reject("UNVERIFIED_MOCK_CALLBACK_ORIGIN")
        message = getattr(getattr(event.raw_message, "event", None), "message", None)
        if message is None or event.message_id != message.message_id:
            return self._reject("HERMES_MESSAGE_ID_MISMATCH")
        ok, verified, reason = self.boundary.verify_raw_feishu_event(
            event.raw_message,
            source=event.source,
            now_ms=now_ms,
        )
        if not ok:
            # Free-form error suffixes must not be persisted or handed to the model.
            return self._reject(reason.split(":", 1)[0])
        key = (verified.app_id, verified.tenant_key, verified.sender_open_id, verified.chat_id)
        if key in self.busy:
            return self._reject("SESSION_CONCURRENCY_BUSY")
        self.busy.add(key)
        turn = correlate("h3-dm", *key, verified.event_id, verified.message_id)
        self.measurements.record("INBOUND_DM", turn, venue_ms=as_of_ms)
        try:
            return await asyncio.wait_for(
                self._reply(verified, key, turn, now_ms, as_of_ms, script, deadline),
                max(0, deadline - time.monotonic()),
            )
        except TimeoutError:
            self.measurements.record("INBOUND_REJECT", turn, code="TIMEOUT")
            return {"accepted": False, "error_code": "TURN_TIMEOUT", "sent": False}
        except asyncio.CancelledError:
            self.measurements.record("INBOUND_REJECT", turn, code="CANCELLED")
            raise
        finally:
            self.busy.remove(key)

    async def _reply(self, verified, key, turn, now_ms, as_of_ms, script, deadline):
        observer = ObservedClient(self.client, self.measurements, turn)
        if key not in self.services:
            self.services[key] = FeishuChatService(
                facade_client=observer,
                allowed_owner_open_ids=frozenset({verified.sender_open_id}),
                owner_chat_bindings={verified.sender_open_id: verified.chat_id},
            )
        chat = self.services[key]
        chat.facade_client = observer
        event = FeishuInboundEvent(
            message_id=verified.message_id,
            chat_id=verified.chat_id,
            chat_type=verified.chat_type,
            sender_open_id=verified.sender_open_id,
            sender_type=verified.sender_type,
            text=verified.clean_text,
            event_ts_ms=verified.event_ts_ms,
        )
        res = chat.handle_inbound(event, now_ms=now_ms, as_of_ms=as_of_ms)
        if not res["accepted"]:
            return self._reject(res["error_code"])
        if res["intent"] == "request_reprice":
            return self._reject("REPRICE_NOT_AUTHORIZED")
        text = res["reply_text"]
        snapshot = (observer.detail or {}).get("snapshot")
        self.measurements.record("FIRST_DM_RESPONSE", turn, code="NO_MODEL")
        explanation, model_status, inventory = None, "NO_MODEL", []
        if script is not None and snapshot is not None:
            with closing(LocalSession(key, self.measurements)) as session:
                inventory = session.inventory()
                explanation, model_status = await explain(
                    session,
                    script,
                    snapshot=snapshot,
                    turn=turn,
                    measurements=self.measurements,
                )
        if snapshot is not None:
            reread = observer.call_tool(
                "get_signal_detail",
                {
                    "episode_id": snapshot["episode_id"],
                    "card_id": snapshot["card_id"],
                    "as_of_ms": as_of_ms,
                },
            )
            if reread["status"] != "OK":
                return self._reject("SOURCE_UNAVAILABLE")
            current = reread["data"]
            latest = current["snapshot"]
            if (
                current["is_superseded"]
                or latest["is_expired"]
                or latest["freshness_state"] != "CURRENT"
                or latest["market_status"] in {"INVALID", "SOURCE_BLOCKED"}
            ):
                text = render_suppressed_notice(
                    latest, suppression_reason="CURRENT_CORE_CARD_UNAVAILABLE"
                )
                explanation = None
            if explanation is not None:
                text += f"\n\n[{model_status} / advisory_only=true]\n{explanation['summary_zh']}"
        if SYNTHETIC_WARNING_TOKEN not in text:
            text = f"{BANNER}\n{text}"
        self.permit.check()
        if time.monotonic() >= deadline:
            raise TimeoutError
        result = self.delivery.send_reply(callback_id=turn, text=text, correlation=turn)
        acknowledged = result.classification == "PROVIDER_ACK"
        if acknowledged:
            self.measurements.record("FINAL_DM_REPLY", turn, code="ACK")
        else:
            self.measurements.record("DELIVERY_FAILURE", turn, code=result.classification)
        return {
            "accepted": True,
            "sent": acknowledged,
            "delivery_state": result.classification,
            "intent": res["intent"],
            "model_status": model_status,
            "tool_inventory": inventory,
            "transcript": text,
            "turn_ref": turn,
            "human_read": "UNOBSERVED",
        }
