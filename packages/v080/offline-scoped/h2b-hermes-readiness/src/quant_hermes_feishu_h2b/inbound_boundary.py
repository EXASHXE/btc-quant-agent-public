"""Fail-closed Feishu inbound private-DM identity, dedup persistence, session isolation, and gateway hook."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import sqlite3
import threading
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quant_hermes_feishu_h1.feishu_chat import (
    FeishuChatService,
    FeishuInboundEvent,
    contains_prompt_injection_or_forbidden_op,
    strip_quoted_spoof_segments,
)

from .constants import FEISHU_APP_ID_RE, FEISHU_TARGET_RE, FEISHU_TENANT_KEY_RE

_FORWARD_CLAIM_TOKENS = (
    "转发自",
    "合并转发",
    "代为转发",
    "forwarded from",
    "on behalf of ou_",
    "假装我是",
    "冒充",
)


@dataclass(frozen=True)
class InboundBinding:
    """Authoritative local identity/security policy for Feishu private DM intake."""

    app_id: str
    tenant_key: str
    allowed_owner_open_ids: frozenset[str]
    owner_chat_bindings: dict[str, str]
    bot_open_id: str = "ou_quant_bot_self"
    connection_mode: str = "websocket"
    max_event_age_ms: int = 300_000
    max_future_skew_ms: int = 60_000
    max_message_bytes: int = 1_024
    rate_limit_max: int = 10
    rate_limit_window_ms: int = 60_000
    allow_webhook_mode: bool = False
    verification_token: str = ""
    encrypt_key: str = ""

    def __post_init__(self) -> None:
        if not FEISHU_APP_ID_RE.fullmatch(self.app_id):
            raise ValueError(f"Invalid app_id: {self.app_id!r}")
        if not FEISHU_TENANT_KEY_RE.fullmatch(self.tenant_key):
            raise ValueError(f"Invalid tenant_key: {self.tenant_key!r}")
        if not self.allowed_owner_open_ids:
            raise ValueError("allowed_owner_open_ids must be non-empty")
        seen_chats: set[str] = set()
        for uid, cid in self.owner_chat_bindings.items():
            if not FEISHU_TARGET_RE.fullmatch(uid) or not uid.startswith("ou_"):
                raise ValueError(f"Invalid bound open_id: {uid!r}")
            if not FEISHU_TARGET_RE.fullmatch(cid) or not cid.startswith("oc_"):
                raise ValueError(f"Invalid bound chat_id: {cid!r}")
            if cid in seen_chats:
                raise ValueError(f"Duplicate chat_id binding violates 1:1 private DM isolation: {cid!r}")
            seen_chats.add(cid)


@dataclass(frozen=True)
class VerifiedInboundEnvelope:
    """Normalized private-DM input whose identity fields come strictly from Feishu event metadata."""

    app_id: str
    tenant_key: str
    event_id: str
    message_id: str
    chat_id: str
    chat_type: str
    sender_open_id: str
    sender_union_id: str | None
    sender_type: str
    event_ts_ms: int
    raw_text: str
    clean_text: str


class InboundDedupStore:
    """Persistent SQLite deduplication and 1:1 chat_id provenance guard surviving restarts."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path).resolve()
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.db_path.parent, 0o700)
        except OSError:
            pass
        with self._connect(write=True) as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS h2b_seen_events (
                    key_type TEXT NOT NULL,
                    key_value TEXT NOT NULL,
                    seen_at_ms INTEGER NOT NULL,
                    PRIMARY KEY (key_type, key_value)
                )"""
            )
            db.execute(
                """CREATE TABLE IF NOT EXISTS h2b_chat_provenance (
                    chat_id TEXT PRIMARY KEY,
                    app_id TEXT NOT NULL,
                    tenant_key TEXT NOT NULL,
                    owner_open_id TEXT NOT NULL,
                    first_seen_ms INTEGER NOT NULL
                )"""
            )
        try:
            os.chmod(self.db_path, 0o600)
        except OSError:
            pass

    @contextmanager
    def _connect(self, *, write: bool = False):
        conn = sqlite3.connect(str(self.db_path), timeout=5.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            if write:
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("PRAGMA synchronous = FULL")
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            if write:
                conn.execute("COMMIT")
        except BaseException:
            if write and conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def check_and_record(
        self,
        *,
        event_id: str,
        message_id: str,
        chat_id: str,
        app_id: str,
        tenant_key: str,
        owner_open_id: str,
        ts_ms: int,
    ) -> str | None:
        """Atomically verify non-duplicate event_id/message_id and non-reused chat_id provenance."""
        with self._lock, self._connect(write=True) as db:
            row_ev = db.execute(
                "SELECT 1 FROM h2b_seen_events WHERE key_type = 'event_id' AND key_value = ?",
                (event_id,),
            ).fetchone()
            if row_ev is not None:
                return "DUPLICATE_EVENT_ID"
            row_msg = db.execute(
                "SELECT 1 FROM h2b_seen_events WHERE key_type = 'message_id' AND key_value = ?",
                (message_id,),
            ).fetchone()
            if row_msg is not None:
                return "DUPLICATE_MESSAGE_ID"
            prov = db.execute(
                "SELECT app_id, tenant_key, owner_open_id FROM h2b_chat_provenance WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
            if prov is not None:
                if (
                    prov["app_id"] != app_id
                    or prov["tenant_key"] != tenant_key
                    or prov["owner_open_id"] != owner_open_id
                ):
                    return "CONVERSATION_ID_REUSED_OR_REBOUND"
            else:
                db.execute(
                    "INSERT INTO h2b_chat_provenance(chat_id, app_id, tenant_key, owner_open_id, first_seen_ms) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (chat_id, app_id, tenant_key, owner_open_id, ts_ms),
                )
            db.execute(
                "INSERT INTO h2b_seen_events(key_type, key_value, seen_at_ms) VALUES ('event_id', ?, ?)",
                (event_id, ts_ms),
            )
            db.execute(
                "INSERT INTO h2b_seen_events(key_type, key_value, seen_at_ms) VALUES ('message_id', ?, ?)",
                (message_id, ts_ms),
            )
        return None


def _get_field(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _parse_ts_ms(val: Any) -> int | None:
    if val is None or isinstance(val, bool):
        return None
    try:
        num = int(str(val).strip())
    except (ValueError, TypeError):
        return None
    if num <= 0:
        return None
    if num < 10_000_000_000:
        return num * 1000
    return num


def _verify_feishu_webhook_hmac(*, encrypt_key: str, headers: dict[str, Any], body_bytes: bytes) -> bool:
    ts = str(headers.get("x-lark-request-timestamp") or headers.get("X-Lark-Request-Timestamp") or "")
    nonce = str(headers.get("x-lark-request-nonce") or headers.get("X-Lark-Request-Nonce") or "")
    sig = str(headers.get("x-lark-signature") or headers.get("X-Lark-Signature") or "")
    if not ts or not nonce or not sig or not encrypt_key:
        return False
    raw = (ts + nonce + encrypt_key).encode("utf-8") + body_bytes
    expected = hashlib.sha256(raw).hexdigest()
    return hmac.compare_digest(expected, sig)


class H2BInboundBoundary:
    """Enforces Feishu app/tenant/sender/chat/replay/rate/payload invariants on inbound DM traffic."""

    def __init__(self, *, binding: InboundBinding, dedup_store: InboundDedupStore) -> None:
        self.binding = binding
        self.dedup_store = dedup_store
        self._rate_lock = threading.Lock()
        self._recent_timestamps: dict[str, deque[int]] = {}

    def verify_raw_feishu_event(
        self,
        raw_event: Any,
        *,
        source: Any = None,
        now_ms: int | None = None,
        webhook_headers: dict[str, Any] | None = None,
        webhook_body: bytes | None = None,
    ) -> tuple[bool, VerifiedInboundEnvelope | None, str | None]:
        """Validate a raw Feishu P2ImMessageReceiveV1/dict event strictly from metadata (never text body)."""
        if raw_event is None:
            return False, None, "MISSING_RAW_FEISHU_EVENT"

        if self.binding.connection_mode == "webhook":
            if not self.binding.allow_webhook_mode:
                return False, None, "WEBHOOK_MODE_DISABLED"
            if webhook_headers is None or webhook_body is None:
                return False, None, "MISSING_WEBHOOK_SIGNATURE_MATERIAL"
            if not _verify_feishu_webhook_hmac(
                encrypt_key=self.binding.encrypt_key,
                headers=webhook_headers,
                body_bytes=webhook_body,
            ):
                return False, None, "INVALID_WEBHOOK_SIGNATURE"

        schema = _get_field(raw_event, "schema")
        if schema not in (None, "2.0"):
            return False, None, f"UNSUPPORTED_EVENT_SCHEMA:{schema}"

        header = _get_field(raw_event, "header")
        event = _get_field(raw_event, "event")
        if header is None or event is None:
            return False, None, "UNAUTHENTICATED_EVENT_HEADER_OR_PAYLOAD"

        app_id = str(_get_field(header, "app_id", "") or "").strip()
        if not app_id or app_id != self.binding.app_id:
            return False, None, "APP_ID_MISMATCH"

        tenant_key = str(_get_field(header, "tenant_key", "") or "").strip()
        if not tenant_key or tenant_key != self.binding.tenant_key:
            return False, None, "TENANT_KEY_MISMATCH"

        if self.binding.verification_token:
            hdr_tok = str(_get_field(header, "token", "") or "")
            if not hmac.compare_digest(hdr_tok, self.binding.verification_token):
                return False, None, "INVALID_VERIFICATION_TOKEN"

        event_type = str(_get_field(header, "event_type", "") or "").strip()
        if event_type != "im.message.receive_v1":
            return False, None, f"UNEXPECTED_EVENT_TYPE:{event_type or 'empty'}"

        event_id = str(_get_field(header, "event_id", "") or "").strip()
        if not event_id:
            return False, None, "MISSING_EVENT_ID"

        sender = _get_field(event, "sender")
        message = _get_field(event, "message")
        if sender is None or message is None:
            return False, None, "MISSING_SENDER_OR_MESSAGE"

        sender_tenant = str(_get_field(sender, "tenant_key", "") or "").strip()
        if sender_tenant and sender_tenant != self.binding.tenant_key:
            return False, None, "SENDER_TENANT_MISMATCH"

        sender_type = str(_get_field(sender, "sender_type", "") or "").strip().lower()
        sender_id_obj = _get_field(sender, "sender_id")
        sender_open_id = str(_get_field(sender_id_obj, "open_id", "") or "").strip()
        sender_union_id_raw = _get_field(sender_id_obj, "union_id")
        sender_union_id = str(sender_union_id_raw).strip() if sender_union_id_raw else None

        if sender_type != "user" or sender_open_id == self.binding.bot_open_id:
            return False, None, "BOT_SELF_OR_APP_EVENT_REJECTED"

        if not sender_open_id or sender_open_id not in self.binding.allowed_owner_open_ids:
            return False, None, "UNAUTHORIZED_OWNER_OPEN_ID"

        # If Hermes normalized a PlatformSource, cross-check claimed source identity against raw event metadata.
        if source is not None:
            src_user = str(_get_field(source, "user_id", "") or "").strip()
            src_chat = str(_get_field(source, "chat_id", "") or "").strip()
            src_type = str(_get_field(source, "chat_type", "") or "").strip().lower()
            if src_user and src_user != sender_open_id:
                return False, None, "FORGED_SOURCE_USER_MISMATCH"
            if src_type and src_type not in {"dm", "p2p", "private"}:
                return False, None, "UNAUTHORIZED_GROUP_OR_NON_DM"
        else:
            src_chat = ""

        chat_type = str(_get_field(message, "chat_type", "") or "").strip().lower()
        if chat_type != "p2p":
            return False, None, f"UNAUTHORIZED_CHAT_TYPE:{chat_type or 'empty'}"

        chat_id = str(_get_field(message, "chat_id", "") or "").strip()
        if not chat_id or (src_chat and src_chat != chat_id):
            return False, None, "CHAT_IDENTITY_MISMATCH"

        expected_chat = self.binding.owner_chat_bindings.get(sender_open_id)
        if not expected_chat or chat_id != expected_chat:
            return False, None, "CHAT_IDENTITY_MISMATCH"

        message_id = str(_get_field(message, "message_id", "") or "").strip()
        if not message_id:
            return False, None, "MISSING_MESSAGE_ID"

        event_ts_ms = _parse_ts_ms(_get_field(message, "create_time")) or _parse_ts_ms(
            _get_field(header, "create_time")
        )
        if event_ts_ms is None:
            return False, None, "INVALID_OR_MISSING_TIMESTAMP"

        ts_now = now_ms if now_ms is not None else time.time_ns() // 1_000_000
        if ts_now - event_ts_ms > self.binding.max_event_age_ms:
            return False, None, "STALE_EVENT_REJECTED"
        if event_ts_ms - ts_now > self.binding.max_future_skew_ms:
            return False, None, "FUTURE_SKEW_EVENT_REJECTED"

        # Rate limit before reading content
        if not self._allow_rate(sender_open_id, ts_now):
            return False, None, "INBOUND_RATE_LIMITED"

        msg_type = str(_get_field(message, "message_type", "") or "").strip().lower()
        if msg_type != "text":
            return False, None, f"UNSUPPORTED_MESSAGE_TYPE:{msg_type or 'empty'}"

        raw_content = _get_field(message, "content", "")
        if not isinstance(raw_content, str):
            return False, None, "MALFORMED_MESSAGE_CONTENT"
        if len(raw_content.encode("utf-8")) > self.binding.max_message_bytes * 2:
            return False, None, "MESSAGE_SIZE_LIMIT_EXCEEDED"
        try:
            content_obj = json.loads(raw_content)
        except json.JSONDecodeError:
            return False, None, "MALFORMED_MESSAGE_CONTENT"
        if not isinstance(content_obj, dict) or not isinstance(content_obj.get("text"), str):
            return False, None, "MALFORMED_MESSAGE_CONTENT"

        raw_text = content_obj["text"]
        if len(raw_text.encode("utf-8")) > self.binding.max_message_bytes:
            return False, None, "MESSAGE_SIZE_LIMIT_EXCEEDED"

        lower_raw = raw_text.lower()
        if any(tok in lower_raw for tok in _FORWARD_CLAIM_TOKENS):
            return False, None, "FORWARDED_IDENTITY_CLAIM_REJECTED"

        clean_text = strip_quoted_spoof_segments(raw_text)
        if not clean_text:
            return False, None, "QUOTED_OR_EMPTY_COMMAND_REJECTED"

        inj = contains_prompt_injection_or_forbidden_op(clean_text)
        if inj is not None:
            return False, None, f"PROMPT_INJECTION_OR_FORBIDDEN_INPUT:{inj}"

        dup_err = self.dedup_store.check_and_record(
            event_id=event_id,
            message_id=message_id,
            chat_id=chat_id,
            app_id=app_id,
            tenant_key=tenant_key,
            owner_open_id=sender_open_id,
            ts_ms=ts_now,
        )
        if dup_err is not None:
            return False, None, dup_err

        return (
            True,
            VerifiedInboundEnvelope(
                app_id=app_id,
                tenant_key=tenant_key,
                event_id=event_id,
                message_id=message_id,
                chat_id=chat_id,
                chat_type=chat_type,
                sender_open_id=sender_open_id,
                sender_union_id=sender_union_id,
                sender_type=sender_type,
                event_ts_ms=event_ts_ms,
                raw_text=raw_text,
                clean_text=clean_text,
            ),
            None,
        )

    def _allow_rate(self, sender_open_id: str, now_ms: int) -> bool:
        with self._rate_lock:
            dq = self._recent_timestamps.setdefault(sender_open_id, deque())
            cutoff = now_ms - self.binding.rate_limit_window_ms
            while dq and dq[0] <= cutoff:
                dq.popleft()
            if len(dq) >= self.binding.rate_limit_max:
                return False
            dq.append(now_ms)
            return True

    def check_hermes_message_event(self, event: Any, *, now_ms: int | None = None) -> dict[str, Any]:
        """Hermes v0.16.0 ``pre_gateway_dispatch`` decision returning allow or skip(reason)."""
        if event is None:
            return {"action": "skip", "reason": "MISSING_EVENT"}
        raw_msg = _get_field(event, "raw_message")
        source = _get_field(event, "source")
        ok, env, reason = self.verify_raw_feishu_event(raw_msg, source=source, now_ms=now_ms)
        if not ok or env is None:
            return {"action": "skip", "reason": reason or "UNVERIFIED_FEISHU_EVENT"}
        return {"action": "allow", "envelope": env}


@dataclass
class _SessionSlot:
    chat_service: FeishuChatService
    semaphore: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(1))
    active_count: int = 0
    turn_count: int = 0


class PrivateDmSessionManager:
    """Strictly isolates sessions per (app_id, tenant_key, owner_open_id, chat_id) with bounded concurrency."""

    def __init__(
        self,
        *,
        boundary: H2BInboundBoundary,
        facade_client: Any,
        explanation_provider: Any = None,
        max_inflight_per_session: int = 1,
    ) -> None:
        self.boundary = boundary
        self.facade_client = facade_client
        self.explanation_provider = explanation_provider
        self.max_inflight_per_session = max_inflight_per_session
        self._sessions: dict[tuple[str, str, str, str], _SessionSlot] = {}
        self._lock = threading.Lock()

    def _get_slot(self, env: VerifiedInboundEnvelope) -> _SessionSlot:
        key = (env.app_id, env.tenant_key, env.sender_open_id, env.chat_id)
        with self._lock:
            slot = self._sessions.get(key)
            if slot is None:
                chat_svc = FeishuChatService(
                    facade_client=self.facade_client,
                    allowed_owner_open_ids=frozenset({env.sender_open_id}),
                    owner_chat_bindings={env.sender_open_id: env.chat_id},
                    bot_open_id=self.boundary.binding.bot_open_id,
                    explanation_provider=self.explanation_provider,
                )
                slot = _SessionSlot(
                    chat_service=chat_svc,
                    semaphore=asyncio.Semaphore(self.max_inflight_per_session),
                )
                self._sessions[key] = slot
            return slot

    def session_keys(self) -> list[tuple[str, str, str, str]]:
        with self._lock:
            return list(self._sessions.keys())

    def handle_raw_event_sync(
        self,
        raw_event: Any,
        *,
        source: Any = None,
        now_ms: int | None = None,
        as_of_ms: int | None = None,
    ) -> dict[str, Any]:
        ok, env, reason = self.boundary.verify_raw_feishu_event(raw_event, source=source, now_ms=now_ms)
        if not ok or env is None:
            return {
                "accepted": False,
                "error_code": reason,
                "reply_text": f"[拒绝] 未通过 Feishu 私聊边界校验 ({reason})。",
            }
        slot = self._get_slot(env)
        h1_ev = FeishuInboundEvent(
            message_id=env.message_id,
            chat_id=env.chat_id,
            chat_type=env.chat_type,
            sender_open_id=env.sender_open_id,
            sender_type=env.sender_type,
            text=env.clean_text,
            event_ts_ms=env.event_ts_ms,
            sender_union_id=env.sender_union_id,
            bot_open_id=self.boundary.binding.bot_open_id,
        )
        res = slot.chat_service.handle_inbound(h1_ev, now_ms=now_ms, as_of_ms=as_of_ms)
        slot.turn_count += 1
        res["session_key"] = f"{env.app_id}:{env.tenant_key}:{env.sender_open_id}:{env.chat_id}"
        res["event_id"] = env.event_id
        return res

    async def handle_raw_event_async(
        self,
        raw_event: Any,
        *,
        source: Any = None,
        now_ms: int | None = None,
        as_of_ms: int | None = None,
        simulated_delay_s: float = 0.0,
    ) -> dict[str, Any]:
        ok, env, reason = self.boundary.verify_raw_feishu_event(raw_event, source=source, now_ms=now_ms)
        if not ok or env is None:
            return {
                "accepted": False,
                "error_code": reason,
                "reply_text": f"[拒绝] 未通过 Feishu 私聊边界校验 ({reason})。",
            }
        slot = self._get_slot(env)
        if slot.semaphore.locked():
            return {
                "accepted": False,
                "error_code": "SESSION_CONCURRENCY_BUSY",
                "reply_text": "[拒绝] 当前私聊会话正在处理上一条请求，请稍后再试。",
            }
        async with slot.semaphore:
            if simulated_delay_s > 0:
                await asyncio.sleep(simulated_delay_s)
            h1_ev = FeishuInboundEvent(
                message_id=env.message_id,
                chat_id=env.chat_id,
                chat_type=env.chat_type,
                sender_open_id=env.sender_open_id,
                sender_type=env.sender_type,
                text=env.clean_text,
                event_ts_ms=env.event_ts_ms,
                sender_union_id=env.sender_union_id,
                bot_open_id=self.boundary.binding.bot_open_id,
            )
            res = slot.chat_service.handle_inbound(h1_ev, now_ms=now_ms, as_of_ms=as_of_ms)
            slot.turn_count += 1
            res["session_key"] = f"{env.app_id}:{env.tenant_key}:{env.sender_open_id}:{env.chat_id}"
            res["event_id"] = env.event_id
            return res
