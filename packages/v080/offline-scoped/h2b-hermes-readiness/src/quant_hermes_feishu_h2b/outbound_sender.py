"""Deterministic single-sender Feishu outbound boundary wrapping accepted H1 outbox & Hermes v0.16.0."""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import re
import sqlite3
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from quant_hermes_feishu_h1.contract import (
    CONTRACT_ID,
    ContractError,
    canonical_json,
    compute_outbox_event_id,
)
from quant_hermes_feishu_h1.feishu_outbound import (
    MockLarkClient,
    classify_hermes_send_result,
    isolated_hermes_feishu_env,
)
from quant_hermes_feishu_h1.outbox import DeliveryResult, DeterministicOutbox

from .activation_gate import GateDenialError, H2BActivationGate
from .constants import (
    FEISHU_APP_ID_RE,
    FEISHU_TARGET_RE,
    FEISHU_TENANT_KEY_RE,
    LIVE_FEISHU_ERROR,
)

_SECRET_SCRUB_RE = re.compile(r"(cli_[A-Za-z0-9_-]{6,}|Bearer\s+[A-Za-z0-9._-]+|t-[A-Za-z0-9_-]{6,})")


class ConcurrentSenderError(RuntimeError):
    """Raised when a second logical sender attempts to dispatch while another sender holds the fence."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = "CONCURRENT_SENDER_FENCED"
        self.message = message


def _redact_secret(text: str | None) -> str | None:
    if text is None:
        return None
    return _SECRET_SCRUB_RE.sub("[REDACTED]", str(text))[:400]


def deterministic_feishu_uuid(event_id: str) -> str:
    """Derive a <=50-char deterministic Feishu im/v1/messages `uuid` from H1 canonical `event_id`."""
    clean = event_id.strip()
    if len(clean) < 16:
        raise ValueError(f"Invalid H1 event_id for deterministic Feishu uuid: {event_id!r}")
    return f"qh2b-{clean[:36]}"


def _infer_receive_id_type(recipient: str) -> str:
    if recipient.startswith("ou_"):
        return "open_id"
    if recipient.startswith(("oc_", "chat_")):
        return "chat_id"
    if recipient.startswith("on_"):
        return "union_id"
    raise ContractError("INVALID_ARGUMENT", f"Unsupported Feishu recipient format: {recipient!r}")


@dataclass(frozen=True)
class OutboundBinding:
    """Immutable app/tenant/recipient/sender binding for the sole production Feishu sender."""

    app_id: str
    tenant_key: str
    owner_open_id: str
    authorized_dm_chat_id: str
    sender_id: str = "hermes-h2b-sole-sender"
    principal_id: str = "hermes_quant_plugin"
    recipient_scope: str = "outbox_worker"

    def __post_init__(self) -> None:
        if not FEISHU_APP_ID_RE.fullmatch(self.app_id):
            raise ValueError(f"Invalid app_id format: {self.app_id!r}")
        if not FEISHU_TENANT_KEY_RE.fullmatch(self.tenant_key):
            raise ValueError(f"Invalid tenant_key format: {self.tenant_key!r}")
        if not FEISHU_TARGET_RE.fullmatch(self.owner_open_id) or not self.owner_open_id.startswith("ou_"):
            raise ValueError(f"owner_open_id must be a valid open_id ('ou_...'): {self.owner_open_id!r}")
        if not FEISHU_TARGET_RE.fullmatch(self.authorized_dm_chat_id) or not self.authorized_dm_chat_id.startswith(
            "oc_"
        ):
            raise ValueError(f"authorized_dm_chat_id must be a valid p2p chat_id ('oc_...'): {self.authorized_dm_chat_id!r}")
        if not self.sender_id.strip():
            raise ValueError("sender_id must be non-empty")

    @property
    def allowed_recipients(self) -> frozenset[str]:
        return frozenset({self.owner_open_id, self.authorized_dm_chat_id})


class H2BMockLarkRecorder:
    """In-memory mock replacement for lark_oapi.Client capturing uuid + receive_id_type + payload."""

    def __init__(self, responses: list[Any] | None = None) -> None:
        self._responses = list(responses or [])
        self.requests: list[dict[str, Any]] = []
        self._counter = 0
        outer = self

        class _MessageAPI:
            def create(self, request: Any) -> Any:
                return outer._handle("create", request)

            def reply(self, request: Any) -> Any:
                return outer._handle("reply", request)

        self.im = SimpleNamespace(v1=SimpleNamespace(message=_MessageAPI()))

    def _handle(self, op: str, request: Any) -> Any:
        self._counter += 1
        body = getattr(request, "request_body", None)
        self.requests.append({
            "seq": self._counter,
            "op": op,
            "receive_id": getattr(body, "receive_id", None),
            "receive_id_type": getattr(request, "receive_id_type", None),
            "msg_type": getattr(body, "msg_type", None),
            "content": getattr(body, "content", None),
            "uuid": getattr(body, "uuid", None),
        })
        if self._responses:
            nxt = self._responses.pop(0)
            if isinstance(nxt, BaseException):
                raise nxt
            return nxt
        return SimpleNamespace(
            success=lambda: True,
            code=0,
            msg="ok",
            data=SimpleNamespace(message_id=f"om_h2b_mock_{self._counter:06d}"),
        )


_LEDGER_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS h2b_delivery_ledger (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        ts_ms INTEGER NOT NULL,
        sender_id TEXT NOT NULL,
        app_id TEXT NOT NULL,
        tenant_key TEXT NOT NULL,
        event_id TEXT NOT NULL,
        episode_id TEXT,
        card_id TEXT,
        card_version TEXT,
        recipient TEXT NOT NULL,
        feishu_uuid TEXT,
        action TEXT NOT NULL,
        outbox_state TEXT,
        provider_message_id TEXT,
        duplicate_risk INTEGER NOT NULL DEFAULT 0,
        user_read_receipt_proven INTEGER NOT NULL DEFAULT 0,
        error_code TEXT,
        detail_json TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_h2b_ledger_event ON h2b_delivery_ledger(event_id, seq)",
)


class DeliveryLedger:
    """Append-only persistent SQLite ledger for sender claims, rechecks, sends, and reconciliations."""

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
            for stmt in _LEDGER_SCHEMA:
                db.execute(stmt)
            for op in ("UPDATE", "DELETE"):
                db.execute(
                    f"CREATE TRIGGER IF NOT EXISTS lock_h2b_ledger_{op} "
                    f"BEFORE {op} ON h2b_delivery_ledger "
                    "BEGIN SELECT RAISE(ABORT, 'H2B_DELIVERY_LEDGER_APPEND_ONLY'); END"
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

    def record(
        self,
        *,
        ts_ms: int,
        sender_id: str,
        app_id: str,
        tenant_key: str,
        event_id: str,
        recipient: str,
        action: str,
        outbox_state: str | None = None,
        episode_id: str | None = None,
        card_id: str | None = None,
        card_version: str | None = None,
        feishu_uuid: str | None = None,
        provider_message_id: str | None = None,
        duplicate_risk: bool = False,
        error_code: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        safe_detail = canonical_json(detail or {})
        safe_detail = _redact_secret(safe_detail) or "{}"
        with self._lock, self._connect(write=True) as db:
            db.execute(
                """INSERT INTO h2b_delivery_ledger(
                    ts_ms, sender_id, app_id, tenant_key, event_id, episode_id, card_id,
                    card_version, recipient, feishu_uuid, action, outbox_state,
                    provider_message_id, duplicate_risk, user_read_receipt_proven,
                    error_code, detail_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
                (
                    ts_ms,
                    sender_id,
                    app_id,
                    tenant_key,
                    event_id,
                    episode_id,
                    card_id,
                    card_version,
                    recipient,
                    feishu_uuid,
                    action,
                    outbox_state,
                    provider_message_id,
                    1 if duplicate_risk else 0,
                    error_code,
                    safe_detail,
                ),
            )

    def entries_for_event(self, event_id: str) -> list[dict[str, Any]]:
        with self._lock, self._connect(write=False) as db:
            rows = db.execute(
                "SELECT * FROM h2b_delivery_ledger WHERE event_id = ? ORDER BY seq ASC",
                (event_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def all_entries(self) -> list[dict[str, Any]]:
        with self._lock, self._connect(write=False) as db:
            rows = db.execute("SELECT * FROM h2b_delivery_ledger ORDER BY seq ASC").fetchall()
            return [dict(r) for r in rows]


class HermesFeishuSingleAttemptTransport:
    """Single-attempt Feishu sender using Hermes v0.16.0 request builders + deterministic UUID.

    Avoids ``FeishuAdapter.send``'s internal 3-retry random-UUID loop and markdown->post
    mutation so every H1 outbox attempt maps 1:1 with deterministic dedup and explicit retry accounting.
    """

    def __init__(
        self,
        *,
        binding: OutboundBinding,
        hermes_home: Path,
        outbox_db_path: Path,
        activation_gate: H2BActivationGate | None = None,
        mock_lark_client: H2BMockLarkRecorder | MockLarkClient | None = None,
        offline_mock_only: bool = True,
        app_secret: str = "offline_mock_secret_do_not_use",
    ) -> None:
        self.binding = binding
        self.hermes_home = Path(hermes_home).resolve()
        self.outbox_db_path = Path(outbox_db_path).resolve()
        self.activation_gate = activation_gate or H2BActivationGate()
        self.mock_lark_client = mock_lark_client
        self.offline_mock_only = offline_mock_only
        self._app_secret = app_secret
        self.used_hermes_adapter = False

    def send_text(
        self,
        *,
        channel: str,
        recipient: str,
        text: str,
        event_id: str,
        attempt: int,
    ) -> DeliveryResult:
        del attempt
        if channel != "feishu":
            return DeliveryResult(
                classification="PERMANENT",
                error_code="UNSUPPORTED_CHANNEL",
                error_detail=f"Unsupported channel {channel!r}",
            )
        if not FEISHU_TARGET_RE.fullmatch(recipient) or recipient not in self.binding.allowed_recipients:
            return DeliveryResult(
                classification="PERMANENT",
                error_code="UNAUTHORIZED_OR_INVALID_RECIPIENT",
                error_detail=f"Recipient {recipient!r} rejected by H2-B binding allowlist",
            )

        if not self.offline_mock_only:
            try:
                self.activation_gate.authorize_capability(
                    "FEISHU_OUTBOUND_DM_ONCE",
                    app_id=self.binding.app_id,
                    tenant_key=self.binding.tenant_key,
                    recipient_open_id=self.binding.owner_open_id,
                    chat_id=self.binding.authorized_dm_chat_id,
                    sender_id=self.binding.sender_id,
                    outbox_path=self.outbox_db_path,
                    consume_quota=True,
                )
            except GateDenialError as exc:
                return DeliveryResult(
                    classification="PERMANENT",
                    error_code=exc.code,
                    error_detail=exc.message,
                )
        elif self.mock_lark_client is None:
            return DeliveryResult(
                classification="PERMANENT",
                error_code=LIVE_FEISHU_ERROR,
                error_detail="Offline mode requires an explicit mock_lark_client; live SDK disabled",
            )

        dedup_uuid = deterministic_feishu_uuid(event_id)
        receive_id_type = _infer_receive_id_type(recipient)
        payload = json.dumps({"text": text}, ensure_ascii=False)

        try:
            response = self._dispatch_single_create(
                recipient=recipient,
                receive_id_type=receive_id_type,
                payload=payload,
                dedup_uuid=dedup_uuid,
            )
        except Exception as exc:  # noqa: BLE001
            err_msg = _redact_secret(str(exc)) or "transport_error"
            lower = err_msg.lower()
            if any(tok in lower for tok in ("timeout", "timed out", "connection reset", "broken pipe", "eof")):
                return DeliveryResult(
                    classification="UNKNOWN_DELIVERY",
                    error_code="TRANSPORT_AMBIGUOUS",
                    error_detail=err_msg,
                )
            if any(tok in lower for tok in ("429", "99991400", "500", "502", "503", "504")):
                return DeliveryResult(
                    classification="RETRYABLE",
                    error_code="TRANSIENT_HTTP_EXCEPTION",
                    error_detail=err_msg,
                    http_status=429 if ("429" in lower or "99991400" in lower) else 503,
                )
            return DeliveryResult(
                classification="UNKNOWN_DELIVERY",
                error_code="AMBIGUOUS_SEND_EXCEPTION",
                error_detail=err_msg,
            )

        return self._classify_sdk_response(response)

    def _dispatch_single_create(
        self,
        *,
        recipient: str,
        receive_id_type: str,
        payload: str,
        dedup_uuid: str,
    ) -> Any:
        try:
            from gateway.config import PlatformConfig
            from gateway.platforms.feishu import FeishuAdapter

            hermes_available = True
        except ImportError:
            hermes_available = False

        if hermes_available:
            self.used_hermes_adapter = True
            with isolated_hermes_feishu_env(
                self.hermes_home,
                app_id=self.binding.app_id,
                app_secret=self._app_secret,
                allowed_users=(self.binding.owner_open_id,),
            ):
                pconfig = PlatformConfig(
                    enabled=True,
                    extra={
                        "app_id": self.binding.app_id,
                        "app_secret": self._app_secret,
                        "domain": "feishu",
                        "connection_mode": "websocket",
                    },
                )
                adapter = FeishuAdapter(pconfig)
                client = self.mock_lark_client
                if client is None:
                    raise RuntimeError("Live lark client disabled without reviewed trust root")
                body = adapter._build_create_message_body(
                    receive_id=recipient,
                    msg_type="text",
                    content=payload,
                    uuid_value=dedup_uuid,
                )
                req = adapter._build_create_message_request(receive_id_type, body)
                return client.im.v1.message.create(req)

        if self.mock_lark_client is None:
            raise RuntimeError("Mock lark client missing")
        body = SimpleNamespace(
            receive_id=recipient,
            msg_type="text",
            content=payload,
            uuid=dedup_uuid,
        )
        req = SimpleNamespace(receive_id_type=receive_id_type, request_body=body)
        return self.mock_lark_client.im.v1.message.create(req)

    @staticmethod
    def _classify_sdk_response(response: Any) -> DeliveryResult:
        ok = bool(response and getattr(response, "success", lambda: False)())
        now_ms = time.time_ns() // 1_000_000
        if ok:
            data = getattr(response, "data", None)
            msg_id = getattr(data, "message_id", None) if data else None
            return DeliveryResult(
                classification="PROVIDER_ACK",
                provider_message_id=msg_id,
                provider_ack_at_ms=now_ms,
                http_status=200,
            )
        code = getattr(response, "code", None)
        msg = _redact_secret(str(getattr(response, "msg", "Feishu API error")))
        formatted = f"[{code}] {msg}"
        if code in {99991400, 429, 500, 502, 503, 504}:
            return DeliveryResult(
                classification="RETRYABLE",
                error_code="TRANSIENT_PROVIDER_ERROR",
                error_detail=formatted,
                http_status=429 if code in {99991400, 429} else int(code),
            )
        return classify_hermes_send_result({"success": False, "error": formatted})


class HermesSingleSenderService:
    """One fenced logical Feishu sender reusing H1 DeterministicOutbox + DeliveryLedger + H2-B gate."""

    def __init__(
        self,
        *,
        state_dir: Path,
        binding: OutboundBinding,
        hermes_home: Path,
        activation_gate: H2BActivationGate | None = None,
        mock_lark_client: H2BMockLarkRecorder | MockLarkClient | None = None,
        offline_mock_only: bool = True,
        lease_ms: int = 10_000,
        max_attempts: int = 3,
        base_backoff_ms: int = 1_000,
        max_backoff_ms: int = 30_000,
        clock_ms_fn: Callable[[], int] | None = None,
        claim_token_fn: Callable[[], str] | None = None,
    ) -> None:
        self.state_dir = Path(state_dir).resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.state_dir, 0o700)
        except OSError:
            pass
        self.binding = binding
        self.outbox_db_path = self.state_dir / "h1_outbox.sqlite"
        self.ledger = DeliveryLedger(self.state_dir / "h2b_delivery_ledger.sqlite")
        self.lock_path = self.state_dir / "sender.lock"
        self._clock_ms_fn = clock_ms_fn or (lambda: time.time_ns() // 1_000_000)
        self.outbox = DeterministicOutbox(
            self.outbox_db_path,
            allowed_recipients=binding.allowed_recipients,
            max_attempts=max_attempts,
            base_backoff_ms=base_backoff_ms,
            max_backoff_ms=max_backoff_ms,
            lease_ms=lease_ms,
            clock_ms_fn=self._clock_ms_fn,
            claim_token_fn=claim_token_fn,
        )
        self.transport = HermesFeishuSingleAttemptTransport(
            binding=binding,
            hermes_home=hermes_home,
            outbox_db_path=self.outbox_db_path,
            activation_gate=activation_gate,
            mock_lark_client=mock_lark_client,
            offline_mock_only=offline_mock_only,
        )

    @contextmanager
    def _exclusive_sender_fence(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self.lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ConcurrentSenderError(
                    f"Another logical sender already holds lock {self.lock_path}",
                ) from exc
            os.ftruncate(fd, 0)
            os.write(fd, f"{os.getpid()}:{self.binding.sender_id}\n".encode("ascii"))
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def enqueue(
        self,
        snapshot: dict[str, Any],
        *,
        recipient: str | None = None,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        """Enqueue a verified SignalSnapshot using H1 deterministic event identity."""
        target = recipient or self.binding.authorized_dm_chat_id
        ts = now_ms if now_ms is not None else self._clock_ms_fn()
        res = self.outbox.enqueue_snapshot(snapshot, channel="feishu", recipient=target, now_ms=ts)
        eid = res["event_id"]
        self.ledger.record(
            ts_ms=ts,
            sender_id=self.binding.sender_id,
            app_id=self.binding.app_id,
            tenant_key=self.binding.tenant_key,
            event_id=eid,
            episode_id=snapshot.get("episode_id"),
            card_id=snapshot.get("card_id"),
            card_version=snapshot.get("card_version"),
            recipient=target,
            feishu_uuid=deterministic_feishu_uuid(eid),
            action="ENQUEUE_DEDUP" if res.get("deduplicated") else "ENQUEUE",
            outbox_state=res["state"],
            detail={"deduplicated": bool(res.get("deduplicated"))},
        )
        return res

    def dispatch_next(
        self,
        *,
        facade_client: Any,
        now_ms: int | None = None,
        simulate_crash_after_send: bool = False,
    ) -> dict[str, Any] | None:
        """Acquire exclusive sender fence, claim one due item, recheck Core, and send once."""
        ts = now_ms if now_ms is not None else self._clock_ms_fn()
        with self._exclusive_sender_fence():
            # Enforce optional gate verification hook BEFORE claiming if caller wants live gate checked.
            if not self.transport.offline_mock_only and self.transport.activation_gate is not None:
                self.transport.activation_gate.authorize_capability(
                    "FEISHU_OUTBOUND_DM_ONCE",
                    app_id=self.binding.app_id,
                    tenant_key=self.binding.tenant_key,
                    recipient_open_id=self.binding.owner_open_id,
                    chat_id=self.binding.authorized_dm_chat_id,
                    sender_id=self.binding.sender_id,
                    outbox_path=self.outbox_db_path,
                    now_ms=ts,
                    consume_quota=False,
                )

            claimed = self.outbox.claim_next(worker_id=self.binding.sender_id, now_ms=ts)
            if claimed is None:
                return None

            eid = str(claimed["event_id"])
            fuuid = deterministic_feishu_uuid(eid)
            self.ledger.record(
                ts_ms=ts,
                sender_id=self.binding.sender_id,
                app_id=self.binding.app_id,
                tenant_key=self.binding.tenant_key,
                event_id=eid,
                episode_id=claimed.get("episode_id"),
                card_id=claimed.get("card_id"),
                card_version=claimed.get("card_version"),
                recipient=str(claimed["recipient"]),
                feishu_uuid=fuuid,
                action="CLAIM",
                outbox_state="ATTEMPTED",
                detail={"attempt_count": claimed["attempt_count"]},
            )
            outcome = self.outbox.process_claimed(
                claimed,
                facade_client=facade_client,
                transport=self.transport,
                worker_id=self.binding.sender_id,
                now_ms=ts,
                simulate_crash_after_send=simulate_crash_after_send,
            )
            state = str(outcome.get("state", "ATTEMPTED"))
            self.ledger.record(
                ts_ms=ts,
                sender_id=self.binding.sender_id,
                app_id=self.binding.app_id,
                tenant_key=self.binding.tenant_key,
                event_id=eid,
                episode_id=claimed.get("episode_id"),
                card_id=claimed.get("card_id"),
                card_version=claimed.get("card_version"),
                recipient=str(claimed["recipient"]),
                feishu_uuid=fuuid,
                action="SIMULATED_CRASH" if simulate_crash_after_send else f"OUTCOME_{state}",
                outbox_state=state,
                provider_message_id=outcome.get("provider_message_id"),
                duplicate_risk=state == "UNKNOWN_DELIVERY",
                error_code=outcome.get("last_error_code"),
                detail={
                    "suppression_reason": outcome.get("suppression_reason"),
                    "used_hermes_adapter": self.transport.used_hermes_adapter,
                    "user_read_receipt_proven": False,
                },
            )
            return outcome

    def reclaim_unknown_deliveries(self, *, now_ms: int | None = None) -> list[str]:
        ts = now_ms if now_ms is not None else self._clock_ms_fn()
        reclaimed = self.outbox.reclaim_expired_leases(now_ms=ts)
        for eid in reclaimed:
            row = self.outbox.get_event(eid) or {}
            self.ledger.record(
                ts_ms=ts,
                sender_id=self.binding.sender_id,
                app_id=self.binding.app_id,
                tenant_key=self.binding.tenant_key,
                event_id=eid,
                episode_id=row.get("episode_id"),
                card_id=row.get("card_id"),
                card_version=row.get("card_version"),
                recipient=str(row.get("recipient") or self.binding.authorized_dm_chat_id),
                feishu_uuid=deterministic_feishu_uuid(eid),
                action="LEASE_RECLAIM_UNKNOWN_DELIVERY",
                outbox_state="UNKNOWN_DELIVERY",
                duplicate_risk=True,
                error_code="WORKER_LEASE_EXPIRED",
                detail={"reconciliation_required": True},
            )
        return reclaimed

    def reconcile_unknown(
        self,
        *,
        event_id: str,
        provider_message_id: str | None,
        delivered: bool,
        reconciled_at_ms: int | None = None,
        actor: str = "operator.reconcile",
    ) -> dict[str, Any]:
        """Explicitly reconcile UNKNOWN_DELIVERY after manual/provider inspection; never blindly re-sent."""
        ts = reconciled_at_ms if reconciled_at_ms is not None else self._clock_ms_fn()
        if delivered:
            if not provider_message_id:
                raise ContractError("INVALID_ARGUMENT", "provider_message_id required when confirming delivery")
            updated = self.outbox.reconcile_delayed_ack(
                event_id=event_id,
                provider_message_id=provider_message_id,
                ack_at_ms=ts,
                actor=actor,
            )
            action = "RECONCILE_PROVIDER_ACK"
        else:
            row = self.outbox.get_event(event_id)
            if row is None or row["state"] != "UNKNOWN_DELIVERY":
                raise ContractError("INVALID_ARGUMENT", f"Event {event_id} is not in UNKNOWN_DELIVERY")
            updated = row
            action = "RECONCILE_UNCONFIRMED_NO_AUTO_RESEND"
        self.ledger.record(
            ts_ms=ts,
            sender_id=self.binding.sender_id,
            app_id=self.binding.app_id,
            tenant_key=self.binding.tenant_key,
            event_id=event_id,
            episode_id=updated.get("episode_id"),
            card_id=updated.get("card_id"),
            card_version=updated.get("card_version"),
            recipient=str(updated.get("recipient") or self.binding.authorized_dm_chat_id),
            feishu_uuid=deterministic_feishu_uuid(event_id),
            action=action,
            outbox_state=str(updated.get("state")),
            provider_message_id=provider_message_id,
            duplicate_risk=bool(updated.get("duplicate_risk")),
            detail={"actor": actor, "user_read_receipt_proven": False},
        )
        return updated


def compute_snapshot_event_id(snapshot: dict[str, Any], *, recipient: str) -> str:
    """Thin wrapper over H1 compute_outbox_event_id preserving identical P0-C03 canonical identity."""
    return compute_outbox_event_id(
        contract_id=CONTRACT_ID,
        channel="feishu",
        recipient=recipient,
        episode_id=snapshot.get("episode_id"),
        card_id=snapshot.get("card_id"),
        card_version=snapshot.get("card_version"),
        market_status=snapshot.get("market_status"),
    )


def verify_hermes_standalone_send_compat(
    *,
    hermes_home: Path,
    binding: OutboundBinding,
    text: str,
    mock_client: H2BMockLarkRecorder | None = None,
) -> dict[str, Any]:
    """Exercise actual Hermes v0.16.0 ``tools.send_message_tool._send_feishu`` offline with mocked Lark SDK."""
    from gateway.config import PlatformConfig
    from gateway.platforms.feishu import FeishuAdapter
    from tools.send_message_tool import _send_feishu

    recorder = mock_client or H2BMockLarkRecorder()
    with isolated_hermes_feishu_env(
        hermes_home,
        app_id=binding.app_id,
        allowed_users=(binding.owner_open_id,),
    ):
        pconfig = PlatformConfig(
            enabled=True,
            extra={
                "app_id": binding.app_id,
                "app_secret": "offline_mock_secret_do_not_use",
                "domain": "feishu",
                "connection_mode": "websocket",
            },
        )
        with patch.object(FeishuAdapter, "_build_lark_client", return_value=recorder):
            res = asyncio.run(_send_feishu(pconfig, binding.authorized_dm_chat_id, text))
    return {"hermes_result": res, "lark_requests": recorder.requests}
