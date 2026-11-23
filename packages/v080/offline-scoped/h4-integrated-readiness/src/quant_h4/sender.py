"""Protected H2-B composition. H1 alone renders, queues, and claims market alerts."""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from threading import local
from types import SimpleNamespace

from quant_hermes_feishu_h1.contract import SYNTHETIC_WARNING_TOKEN
from quant_hermes_feishu_h1.outbox import DeliveryResult
from quant_hermes_feishu_h1.renderer import render_signal_alert
from quant_hermes_feishu_h2b.activation_gate import H2BRevocationStore
from quant_hermes_feishu_h2b.outbound_sender import (
    H2BMockLarkRecorder,
    HermesSingleSenderService,
    OutboundBinding,
    compute_snapshot_event_id,
    deterministic_feishu_uuid,
)

from .facade import PeerVerifiedFacade
from .fence import Denied, digest
from .provider import FeishuPort

LIMIT_TEXT = 4096


def text_sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ExistingQuota(H2BRevocationStore):
    """Use the accepted quota transaction over an already-enrolled SQLite identity."""

    def __init__(self, pin):
        self.pin = pin
        super().__init__(pin.path)

    def _init_db(self):
        with self._connect() as db:
            for table in ("h2b_grant_usage", "h2b_revocations"):
                if (
                    db.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
                    ).fetchone()
                    is None
                ):
                    raise Denied("QUOTA_SCHEMA_MISMATCH")

    @contextmanager
    def _connect(self, *, write=False):
        self.pin.verify_private()
        db = sqlite3.connect(
            self.pin.path.as_uri() + "?mode=rw", uri=True, isolation_level=None, timeout=1
        )
        db.row_factory = sqlite3.Row
        try:
            self.pin.verify_private()
            if write:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")
            yield db
            if write:
                self.pin.verify_private()
                db.execute("COMMIT")
        finally:
            db.close()


class _GuardedClient:
    """The only im.v1.message.create passed to the accepted H2-B request builder."""

    def __init__(self, sender, provider):
        self.sender, self.provider = sender, provider
        self.im = SimpleNamespace(v1=SimpleNamespace(message=SimpleNamespace(create=self.create)))

    def create(self, request):
        sender = self.sender
        permit = sender.permit
        slot, key, uuid, expected = sender.inflight
        body = request.request_body
        if (
            request.receive_id_type != "chat_id"
            or body.receive_id != permit.claim.chat
            or body.uuid != uuid
            or body.msg_type != "text"
            or json.loads(body.content) != {"text": expected}
        ):
            raise Denied("PROVIDER_REQUEST_BINDING_MISMATCH")
        sender.check()
        permit.state.witness.check(slot, key)
        permit.state.witness.spend(slot + "_wire", key)
        sender.check()
        permit.state.witness.check(slot + "_wire", key)
        if type(self.provider) is FeishuPort:
            return self.provider.send_once(request, slot, key)
        return self.provider.im.v1.message.create(request)


class ProtectedSender:
    """One accepted logical H2-B sender with independent one-shot state."""

    offline_mock_only = True  # The H2-B default gate has no authority over this scoped adapter.

    def __init__(self, permit, *, hermes_home, provider):
        self.permit = permit
        if (
            permit.fixture
            and type(provider) is not H2BMockLarkRecorder
            or not permit.fixture
            and (type(provider) is not FeishuPort or provider.permit is not permit)
        ):
            raise Denied("PROVIDER_PORT_NOT_APPROVED")
        permit.check()
        c = permit.claim
        self.binding = OutboundBinding(
            app_id=c.app,
            tenant_key=c.tenant,
            owner_open_id=c.owner,
            authorized_dm_chat_id=c.chat,
            sender_id=c.sender,
        )
        pins = dict(permit.state.pins)
        state_dir = pins["outbox"].path.parent
        if (
            pins["outbox"].path != state_dir / "h1_outbox.sqlite"
            or pins["delivery"].path != state_dir / "h2b_delivery_ledger.sqlite"
        ):
            raise Denied("NATIVE_SENDER_PATH_MISMATCH")
        self.quota = ExistingQuota(pins["quota"])
        self.check()
        self.service = HermesSingleSenderService(
            state_dir=state_dir,
            binding=self.binding,
            hermes_home=hermes_home,
            max_attempts=1,
            mock_lark_client=_GuardedClient(self, provider),
            offline_mock_only=True,
            lease_ms=1_000,
        )
        self.native = self.service.transport
        self.service.transport = self
        self.inflight = None
        self._dispatch = local()
        self.check()

    @property
    def used_hermes_adapter(self):
        return self.native.used_hermes_adapter

    def check(self):
        self.permit.check()
        c = self.permit.claim
        if self.quota.is_revoked(run_id=c.run_id, app_id=c.app, capability=c.capability):
            raise Denied("CAPABILITY_REVOKED")

    def enqueue(self, snapshot, now_ms):
        self.check()
        c = self.permit.claim
        if (
            c.capability != "outbound"
            or snapshot["source_evidence_class"] != c.evidence_class
            or snapshot["market_status"] != "EXECUTABLE"
            or compute_snapshot_event_id(snapshot, recipient=c.chat) != c.event_id
            or text_sha(render_signal_alert(snapshot)) != c.message_sha256
        ):
            raise Denied("OUTBOX_APPROVAL_BINDING_MISMATCH")
        return self.service.enqueue(snapshot, recipient=c.chat, now_ms=now_ms)

    def dispatch(self, client, now_ms, *, crash=False):
        self.check()
        if self.permit.claim.capability != "outbound":
            raise Denied("WRONG_CAPABILITY")
        self.permit.state.witness.check("outbound")
        pinned_client = PeerVerifiedFacade(client, self.permit)
        pinned_client.probe()
        self._dispatch.active = True
        try:
            return self.service.dispatch_next(
                facade_client=pinned_client, now_ms=now_ms, simulate_crash_after_send=crash
            )
        finally:
            self._dispatch.active = False

    def send_text(self, *, channel, recipient, text, event_id, attempt):
        c = self.permit.claim
        if not getattr(self._dispatch, "active", False):
            return DeliveryResult(classification="PERMANENT", error_code="CORE_RECHECK_REQUIRED")
        if (channel, recipient, event_id, attempt, text_sha(text)) != (
            c.channel,
            c.chat,
            c.event_id,
            1,
            c.message_sha256,
        ):
            return DeliveryResult(
                classification="PERMANENT", error_code="OUTBOX_APPROVAL_BINDING_MISMATCH"
            )
        return self._send("outbound", event_id, text)

    def _reply(self, event, text):
        if self.permit.claim.capability != "inbound":
            raise Denied("WRONG_CAPABILITY")
        if not isinstance(event, str) or len(event) != 64:
            raise Denied("TURN_IDENTITY_INVALID")
        self.permit.state.witness.check("turn", self.permit.key("turn", event))
        with self.service._exclusive_sender_fence():
            return self._send("reply", digest(["H4_REPLY_V1", self.permit.sha, event]), text)

    def _send(self, slot, event, text):
        permit = self.permit
        claim = permit.claim
        self.check()
        if (
            not text
            or len(text.encode("utf-8")) > LIMIT_TEXT
            or (permit.fixture and SYNTHETIC_WARNING_TOKEN not in text)
        ):
            raise Denied("MESSAGE_SIZE_OR_EVIDENCE_INVALID")
        uuid = deterministic_feishu_uuid(event)
        key = permit.key(slot, event, uuid)
        # Independent debit stays spent even if the SQLite transaction raises.
        permit.state.witness.spend(slot, key)
        self.quota.consume_run_quota(
            run_id=claim.run_id + ":" + slot, capability=slot, max_count=1, now_ms=permit.clock()
        )
        self.inflight = slot, key, uuid, text
        try:
            sent = self.native.send_text(
                channel=claim.channel, recipient=claim.chat, text=text, event_id=event, attempt=1
            )
        finally:
            self.inflight = None
        if sent.classification == "RETRYABLE":
            return DeliveryResult(
                classification="PERMANENT", error_code="ONE_SHOT_PROVIDER_REJECTED"
            )
        return sent
