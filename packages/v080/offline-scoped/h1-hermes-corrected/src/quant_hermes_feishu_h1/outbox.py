"""Durable, transaction-safe, idempotent notification outbox with pre-send Core revalidation."""

from __future__ import annotations

import os
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .contract import (
    CONTRACT_ID,
    EVIDENCE_SYNTHETIC,
    EVIDENCE_UNKNOWN,
    SYNTHETIC_WARNING_TOKEN,
    ContractError,
    canonical_json,
    compute_outbox_event_id,
)
from .facade import QuantFacadeClient
from .renderer import render_signal_alert, render_suppressed_notice

OUTBOX_STATES = frozenset({
    "CREATED",
    "READY",
    "ATTEMPTED",
    "PROVIDER_ACK",
    "RETRYABLE",
    "PERMANENT",
    "UNKNOWN_DELIVERY",
    "SUPPRESSED",
    "EXPIRED",
})

TERMINAL_OR_HELD_STATES = frozenset({
    "PROVIDER_ACK",
    "PERMANENT",
    "UNKNOWN_DELIVERY",
    "SUPPRESSED",
    "EXPIRED",
})

_OUTBOX_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS outbox_events (
        event_id TEXT PRIMARY KEY,
        contract_id TEXT NOT NULL,
        channel TEXT NOT NULL,
        recipient TEXT NOT NULL,
        episode_id TEXT NOT NULL,
        card_id TEXT NOT NULL,
        card_version TEXT NOT NULL,
        market_status TEXT NOT NULL,
        source_evidence_class TEXT NOT NULL,
        absolute_expiry_ms INTEGER,
        state TEXT NOT NULL,
        attempt_count INTEGER NOT NULL DEFAULT 0,
        max_attempts INTEGER NOT NULL DEFAULT 3,
        next_retry_at_ms INTEGER,
        claim_token TEXT,
        claimed_by TEXT,
        lease_expires_at_ms INTEGER,
        provider_message_id TEXT,
        provider_ack_at_ms INTEGER,
        duplicate_risk INTEGER NOT NULL DEFAULT 0,
        reconciliation_required INTEGER NOT NULL DEFAULT 0,
        user_read_receipt_proven INTEGER NOT NULL DEFAULT 0,
        last_error_code TEXT,
        last_error_detail TEXT,
        suppression_reason TEXT,
        rendered_payload_sha256 TEXT,
        created_at_ms INTEGER NOT NULL,
        updated_at_ms INTEGER NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_outbox_state_retry ON outbox_events(state, next_retry_at_ms, created_at_ms)",
    """CREATE TABLE IF NOT EXISTS outbox_transitions (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL REFERENCES outbox_events(event_id),
        from_state TEXT,
        to_state TEXT NOT NULL,
        actor TEXT NOT NULL,
        ts_ms INTEGER NOT NULL,
        detail TEXT NOT NULL
    )""",
)


@dataclass(frozen=True)
class DeliveryResult:
    """Classified outcome from a Feishu outbound transport adapter."""

    classification: str  # PROVIDER_ACK | RETRYABLE | PERMANENT | UNKNOWN_DELIVERY
    provider_message_id: str | None = None
    provider_ack_at_ms: int | None = None
    error_code: str | None = None
    error_detail: str | None = None
    http_status: int | None = None


class OutboundTransport(Protocol):
    """Protocol implemented by mock/Hermes Feishu outbound adapters."""

    def send_text(
        self,
        *,
        channel: str,
        recipient: str,
        text: str,
        event_id: str,
        attempt: int,
    ) -> DeliveryResult:
        ...


class DeterministicOutbox:
    """SQLite-backed durable outbox enforcing V1 deterministic identity and pre-send rechecks."""

    def __init__(
        self,
        db_path: Path,
        *,
        allowed_recipients: frozenset[str],
        max_attempts: int = 3,
        base_backoff_ms: int = 1_000,
        max_backoff_ms: int = 30_000,
        lease_ms: int = 10_000,
        clock_ms_fn: Callable[[], int] | None = None,
        claim_token_fn: Callable[[], str] | None = None,
    ) -> None:
        self.db_path = Path(db_path).resolve()
        self.allowed_recipients = allowed_recipients
        self.max_attempts = max_attempts
        self.base_backoff_ms = base_backoff_ms
        self.max_backoff_ms = max_backoff_ms
        self.lease_ms = lease_ms
        self._clock_ms_fn = clock_ms_fn or (lambda: time.time_ns() // 1_000_000)
        self._claim_token_fn = claim_token_fn or (lambda: uuid.uuid4().hex)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.db_path.parent, 0o700)
        except OSError:
            pass
        with self._connect(write=True) as db:
            for stmt in _OUTBOX_SCHEMA:
                db.execute(stmt)
            for op in ("UPDATE", "DELETE"):
                db.execute(
                    f"CREATE TRIGGER IF NOT EXISTS lock_transitions_{op} "
                    f"BEFORE {op} ON outbox_transitions "
                    "BEGIN SELECT RAISE(ABORT, 'H1_OUTBOX_APPEND_ONLY'); END"
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
            conn.execute("PRAGMA foreign_keys = ON")
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

    @staticmethod
    def _record_transition(
        db: sqlite3.Connection,
        *,
        event_id: str,
        from_state: str | None,
        to_state: str,
        actor: str,
        ts_ms: int,
        detail: dict[str, Any],
    ) -> None:
        if to_state not in OUTBOX_STATES:
            raise ValueError(f"Invalid outbox state: {to_state!r}")
        db.execute(
            "INSERT INTO outbox_transitions(event_id, from_state, to_state, actor, ts_ms, detail) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (event_id, from_state, to_state, actor, ts_ms, canonical_json(detail)),
        )

    def enqueue_snapshot(
        self,
        snapshot: dict[str, Any],
        *,
        channel: str = "feishu",
        recipient: str,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        """Idempotently create CREATED -> READY (or EXPIRED/UNAUTHORIZED) outbox entry."""
        if recipient not in self.allowed_recipients:
            raise ContractError("UNAUTHORIZED", f"Recipient {recipient!r} not in outbox allowlist")
        if snapshot.get("diagnostic_only") is True or snapshot.get("not_eligible_for_alert") is True:
            raise ContractError("INVALID_ARGUMENT", "Diagnostic/non-alert card cannot be enqueued into outbox")
        ep_id = snapshot.get("episode_id")
        if type(ep_id) is not str or not ep_id.strip() or ep_id.startswith("noep:"):
            raise ContractError("INVALID_ARGUMENT", "Outbox requires an authentic non-null episode_id")
        if snapshot.get("market_status") in {"NO_SETUP", "NOT_EVALUATED"}:
            raise ContractError("INVALID_ARGUMENT", f"Diagnostic status {snapshot.get('market_status')!r} cannot be enqueued")
        ev_class = snapshot.get("source_evidence_class")
        if not isinstance(ev_class, str) or not ev_class or ev_class == EVIDENCE_UNKNOWN:
            raise ContractError("INVALID_ARGUMENT", "Outbox requires verified non-UNKNOWN source_evidence_class")

        ts = now_ms if now_ms is not None else self._clock_ms_fn()
        event_id = compute_outbox_event_id(
            contract_id=CONTRACT_ID,
            channel=channel,
            recipient=recipient,
            episode_id=str(snapshot["episode_id"]),
            card_id=str(snapshot["card_id"]),
            card_version=str(snapshot["card_version"]),
            market_status=str(snapshot["market_status"]),
        )
        abs_exp = snapshot.get("absolute_expiry_ms")
        already_expired = snapshot.get("is_expired") or (abs_exp is not None and ts >= abs_exp)

        with self._lock, self._connect(write=True) as db:
            existing = db.execute("SELECT * FROM outbox_events WHERE event_id = ?", (event_id,)).fetchone()
            if existing is not None:
                return {"event_id": event_id, "deduplicated": True, "state": existing["state"]}

            db.execute(
                """INSERT INTO outbox_events(
                    event_id, contract_id, channel, recipient, episode_id, card_id, card_version,
                    market_status, source_evidence_class, absolute_expiry_ms, state, attempt_count,
                    max_attempts, created_at_ms, updated_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'CREATED', 0, ?, ?, ?)""",
                (
                    event_id,
                    CONTRACT_ID,
                    channel,
                    recipient,
                    str(snapshot["episode_id"]),
                    str(snapshot["card_id"]),
                    str(snapshot["card_version"]),
                    str(snapshot["market_status"]),
                    str(snapshot["source_evidence_class"]),
                    abs_exp,
                    self.max_attempts,
                    ts,
                    ts,
                ),
            )
            self._record_transition(
                db,
                event_id=event_id,
                from_state=None,
                to_state="CREATED",
                actor="outbox.enqueue",
                ts_ms=ts,
                detail={"symbol": snapshot["symbol"], "market_status": snapshot["market_status"]},
            )

            next_state = "EXPIRED" if already_expired else "READY"
            suppression = "EXPIRED_BEFORE_ENQUEUE" if already_expired else None
            db.execute(
                "UPDATE outbox_events SET state = ?, suppression_reason = ?, updated_at_ms = ? WHERE event_id = ?",
                (next_state, suppression, ts, event_id),
            )
            self._record_transition(
                db,
                event_id=event_id,
                from_state="CREATED",
                to_state=next_state,
                actor="outbox.enqueue",
                ts_ms=ts,
                detail={"reason": suppression or "ELIGIBLE"},
            )
            return {"event_id": event_id, "deduplicated": False, "state": next_state}

    def reclaim_expired_leases(self, *, now_ms: int | None = None) -> list[str]:
        """Transition crashed ATTEMPTED leases to UNKNOWN_DELIVERY with explicit duplicate_risk."""
        ts = now_ms if now_ms is not None else self._clock_ms_fn()
        reclaimed: list[str] = []
        with self._lock, self._connect(write=True) as db:
            rows = db.execute(
                "SELECT event_id FROM outbox_events WHERE state = 'ATTEMPTED' AND lease_expires_at_ms <= ?",
                (ts,),
            ).fetchall()
            for row in rows:
                eid = str(row["event_id"])
                db.execute(
                    """UPDATE outbox_events
                       SET state = 'UNKNOWN_DELIVERY',
                           duplicate_risk = 1,
                           reconciliation_required = 1,
                           claim_token = NULL,
                           lease_expires_at_ms = NULL,
                           last_error_code = 'WORKER_LEASE_EXPIRED',
                           last_error_detail = 'Worker crashed or timed out during ATTEMPTED state; duplicate delivery possible',
                           updated_at_ms = ?
                       WHERE event_id = ? AND state = 'ATTEMPTED'""",
                    (ts, eid),
                )
                self._record_transition(
                    db,
                    event_id=eid,
                    from_state="ATTEMPTED",
                    to_state="UNKNOWN_DELIVERY",
                    actor="outbox.reclaim",
                    ts_ms=ts,
                    detail={"duplicate_risk": True, "reconciliation_required": True},
                )
                reclaimed.append(eid)
        return reclaimed

    def claim_next(self, *, worker_id: str, now_ms: int | None = None) -> dict[str, Any] | None:
        """Atomically claim one READY or due RETRYABLE event for delivery."""
        ts = now_ms if now_ms is not None else self._clock_ms_fn()
        claim_token = self._claim_token_fn()
        lease_exp = ts + self.lease_ms

        with self._lock, self._connect(write=True) as db:
            row = db.execute(
                """SELECT * FROM outbox_events
                   WHERE state = 'READY'
                      OR (state = 'RETRYABLE' AND (next_retry_at_ms IS NULL OR next_retry_at_ms <= ?))
                   ORDER BY created_at_ms ASC, event_id ASC
                   LIMIT 1""",
                (ts,),
            ).fetchone()
            if row is None:
                return None

            eid = str(row["event_id"])
            prev_state = str(row["state"])
            abs_exp = row["absolute_expiry_ms"]
            if abs_exp is not None and ts >= int(abs_exp):
                db.execute(
                    """UPDATE outbox_events
                       SET state = 'EXPIRED', suppression_reason = 'EXPIRED_BEFORE_CLAIM', updated_at_ms = ?
                       WHERE event_id = ?""",
                    (ts, eid),
                )
                self._record_transition(
                    db,
                    event_id=eid,
                    from_state=prev_state,
                    to_state="EXPIRED",
                    actor=worker_id,
                    ts_ms=ts,
                    detail={"absolute_expiry_ms": abs_exp},
                )
                return None

            new_attempts = int(row["attempt_count"]) + 1
            cur = db.execute(
                """UPDATE outbox_events
                   SET state = 'ATTEMPTED',
                       attempt_count = ?,
                       claim_token = ?,
                       claimed_by = ?,
                       lease_expires_at_ms = ?,
                       updated_at_ms = ?
                   WHERE event_id = ? AND state = ?""",
                (new_attempts, claim_token, worker_id, lease_exp, ts, eid, prev_state),
            )
            if cur.rowcount != 1:
                return None

            self._record_transition(
                db,
                event_id=eid,
                from_state=prev_state,
                to_state="ATTEMPTED",
                actor=worker_id,
                ts_ms=ts,
                detail={"attempt": new_attempts, "claim_token": claim_token},
            )
            updated = db.execute("SELECT * FROM outbox_events WHERE event_id = ?", (eid,)).fetchone()
            return dict(updated) if updated else None

    def process_claimed(
        self,
        claimed_row: dict[str, Any],
        *,
        facade_client: QuantFacadeClient,
        transport: OutboundTransport,
        worker_id: str,
        now_ms: int | None = None,
        simulate_crash_after_send: bool = False,
    ) -> dict[str, Any]:
        """Revalidate Core card via facade, render model-free text, send, and persist transition."""
        ts = now_ms if now_ms is not None else self._clock_ms_fn()
        eid = str(claimed_row["event_id"])
        claim_token = str(claimed_row["claim_token"])

        if claimed_row["recipient"] not in self.allowed_recipients:
            return self._transition_claimed(
                eid,
                claim_token=claim_token,
                to_state="PERMANENT",
                actor=worker_id,
                ts_ms=ts,
                error_code="UNAUTHORIZED",
                error_detail="Recipient removed from allowlist before send",
            )

        recheck_resp = facade_client.call_tool(
            "get_signal_detail",
            {
                "episode_id": claimed_row["episode_id"],
                "card_id": claimed_row["card_id"],
                "as_of_ms": ts,
            },
            recipient_scope="outbox_worker",
        )
        if recheck_resp.get("status") != "OK":
            err = recheck_resp.get("error") or {}
            return self._transition_claimed(
                eid,
                claim_token=claim_token,
                to_state="SUPPRESSED",
                actor=worker_id,
                ts_ms=ts,
                suppression_reason=f"RECHECK_ERROR:{err.get('code', 'UNKNOWN')}",
                error_code=str(err.get("code") or "SOURCE_UNAVAILABLE"),
                error_detail=str(err.get("message") or "Facade recheck failed"),
            )

        data = recheck_resp["data"]
        snap = data["snapshot"]
        suppression_reason = self._check_send_eligibility(claimed_row, data, snap, ts)
        if suppression_reason is not None:
            to_state = "EXPIRED" if suppression_reason.startswith("EXPIRED") else "SUPPRESSED"
            notice = render_suppressed_notice(snap, suppression_reason=suppression_reason)
            return self._transition_claimed(
                eid,
                claim_token=claim_token,
                to_state=to_state,
                actor=worker_id,
                ts_ms=ts,
                suppression_reason=suppression_reason,
                rendered_text=notice,
            )

        rendered_text = render_signal_alert(snap)
        if snap["source_evidence_class"] == EVIDENCE_SYNTHETIC and SYNTHETIC_WARNING_TOKEN not in rendered_text:
            raise ContractError("INTEGRITY_FAILURE", "Synthetic rendered card missing NOT_A_REAL_TRADE_SIGNAL")

        delivery = transport.send_text(
            channel=str(claimed_row["channel"]),
            recipient=str(claimed_row["recipient"]),
            text=rendered_text,
            event_id=eid,
            attempt=int(claimed_row["attempt_count"]),
        )

        if simulate_crash_after_send:
            return {
                "event_id": eid,
                "state": "ATTEMPTED",
                "simulated_crash": True,
                "rendered_text": rendered_text,
                "provider_result_lost_before_commit": delivery.provider_message_id,
            }

        if now_ms is not None:
            ack_ts = ts
        else:
            ack_ts = delivery.provider_ack_at_ms or self._clock_ms_fn()
        if delivery.classification == "PROVIDER_ACK":
            return self._transition_claimed(
                eid,
                claim_token=claim_token,
                to_state="PROVIDER_ACK",
                actor=worker_id,
                ts_ms=ack_ts,
                provider_message_id=delivery.provider_message_id,
                provider_ack_at_ms=ack_ts,
                rendered_text=rendered_text,
            )

        if delivery.classification == "UNKNOWN_DELIVERY":
            return self._transition_claimed(
                eid,
                claim_token=claim_token,
                to_state="UNKNOWN_DELIVERY",
                actor=worker_id,
                ts_ms=ack_ts,
                duplicate_risk=True,
                reconciliation_required=True,
                error_code=delivery.error_code or "UNKNOWN_DELIVERY",
                error_detail=delivery.error_detail or "Ambiguous transport outcome; duplicate risk",
                rendered_text=rendered_text,
            )

        if delivery.classification == "RETRYABLE":
            attempts = int(claimed_row["attempt_count"])
            max_att = int(claimed_row["max_attempts"])
            if attempts >= max_att:
                return self._transition_claimed(
                    eid,
                    claim_token=claim_token,
                    to_state="PERMANENT",
                    actor=worker_id,
                    ts_ms=ack_ts,
                    error_code="RETRY_BUDGET_EXHAUSTED",
                    error_detail=delivery.error_detail or "Max retry attempts reached",
                    rendered_text=rendered_text,
                )
            delay = min(self.base_backoff_ms * (2 ** max(attempts - 1, 0)), self.max_backoff_ms)
            next_retry = ack_ts + delay
            abs_exp = snap.get("absolute_expiry_ms")
            if abs_exp is not None and next_retry >= int(abs_exp):
                return self._transition_claimed(
                    eid,
                    claim_token=claim_token,
                    to_state="EXPIRED",
                    actor=worker_id,
                    ts_ms=ack_ts,
                    suppression_reason="EXPIRES_BEFORE_NEXT_RETRY",
                    error_code=delivery.error_code,
                    error_detail=delivery.error_detail,
                    rendered_text=rendered_text,
                )
            return self._transition_claimed(
                eid,
                claim_token=claim_token,
                to_state="RETRYABLE",
                actor=worker_id,
                ts_ms=ack_ts,
                next_retry_at_ms=next_retry,
                error_code=delivery.error_code or "RETRYABLE_ERROR",
                error_detail=delivery.error_detail or "Transient transport failure",
                rendered_text=rendered_text,
            )

        return self._transition_claimed(
            eid,
            claim_token=claim_token,
            to_state="PERMANENT",
            actor=worker_id,
            ts_ms=ack_ts,
            error_code=delivery.error_code or "PERMANENT_ERROR",
            error_detail=delivery.error_detail or "Permanent transport failure",
            rendered_text=rendered_text,
        )

    @staticmethod
    def _check_send_eligibility(
        row: dict[str, Any],
        detail_data: dict[str, Any],
        snap: dict[str, Any],
        now_ms: int,
    ) -> str | None:
        if snap.get("is_expired") or (
            snap.get("absolute_expiry_ms") is not None and now_ms >= int(snap["absolute_expiry_ms"])
        ):
            return "EXPIRED_BEFORE_SEND"
        if detail_data.get("is_superseded") or detail_data.get("latest_card_version") != row["card_version"]:
            return f"SUPERSEDED_BY:{detail_data.get('latest_card_version')}"
        if snap.get("source_evidence_class") != row["source_evidence_class"]:
            return "SOURCE_EVIDENCE_CHANGED"
        if snap.get("market_status") in {"INVALID", "SOURCE_BLOCKED", "NO_SETUP", "NOT_EVALUATED"}:
            return f"NON_AFFIRMATIVE_STATUS:{snap.get('market_status')}"
        if snap.get("market_status") != row["market_status"]:
            return f"STATUS_CHANGED:{snap.get('market_status')}"
        if snap.get("freshness_state") != "CURRENT":
            return f"FRESHNESS_NOT_CURRENT:{snap.get('freshness_state')}"
        return None

    def _transition_claimed(
        self,
        event_id: str,
        *,
        claim_token: str,
        to_state: str,
        actor: str,
        ts_ms: int,
        provider_message_id: str | None = None,
        provider_ack_at_ms: int | None = None,
        next_retry_at_ms: int | None = None,
        duplicate_risk: bool = False,
        reconciliation_required: bool = False,
        error_code: str | None = None,
        error_detail: str | None = None,
        suppression_reason: str | None = None,
        rendered_text: str | None = None,
    ) -> dict[str, Any]:
        import hashlib

        rendered_sha = hashlib.sha256(rendered_text.encode("utf-8")).hexdigest() if rendered_text else None
        with self._lock, self._connect(write=True) as db:
            cur = db.execute(
                """UPDATE outbox_events
                   SET state = ?,
                       claim_token = NULL,
                       lease_expires_at_ms = NULL,
                       next_retry_at_ms = ?,
                       provider_message_id = COALESCE(?, provider_message_id),
                       provider_ack_at_ms = COALESCE(?, provider_ack_at_ms),
                       duplicate_risk = CASE WHEN ? THEN 1 ELSE duplicate_risk END,
                       reconciliation_required = CASE WHEN ? THEN 1 ELSE reconciliation_required END,
                       last_error_code = ?,
                       last_error_detail = ?,
                       suppression_reason = COALESCE(?, suppression_reason),
                       rendered_payload_sha256 = COALESCE(?, rendered_payload_sha256),
                       updated_at_ms = ?
                   WHERE event_id = ? AND state = 'ATTEMPTED' AND claim_token = ?""",
                (
                    to_state,
                    next_retry_at_ms,
                    provider_message_id,
                    provider_ack_at_ms,
                    1 if duplicate_risk else 0,
                    1 if reconciliation_required else 0,
                    error_code,
                    error_detail,
                    suppression_reason,
                    rendered_sha,
                    ts_ms,
                    event_id,
                    claim_token,
                ),
            )
            if cur.rowcount != 1:
                raise ContractError("INTEGRITY_FAILURE", f"Lost claim lease for event {event_id}")
            self._record_transition(
                db,
                event_id=event_id,
                from_state="ATTEMPTED",
                to_state=to_state,
                actor=actor,
                ts_ms=ts_ms,
                detail={
                    "provider_message_id": provider_message_id,
                    "error_code": error_code,
                    "suppression_reason": suppression_reason,
                    "duplicate_risk": duplicate_risk,
                    "user_read_receipt_proven": False,
                },
            )
            row = db.execute("SELECT * FROM outbox_events WHERE event_id = ?", (event_id,)).fetchone()
            out = dict(row) if row else {"event_id": event_id, "state": to_state}
            if rendered_text is not None:
                out["rendered_text"] = rendered_text
            return out

    def reconcile_delayed_ack(
        self,
        *,
        event_id: str,
        provider_message_id: str,
        ack_at_ms: int | None = None,
        actor: str = "outbox.reconcile",
    ) -> dict[str, Any]:
        """Reconcile a delayed provider message_id onto UNKNOWN_DELIVERY or ATTEMPTED."""
        ts = ack_at_ms if ack_at_ms is not None else self._clock_ms_fn()
        with self._lock, self._connect(write=True) as db:
            row = db.execute("SELECT * FROM outbox_events WHERE event_id = ?", (event_id,)).fetchone()
            if row is None:
                raise ContractError("NOT_FOUND", f"Unknown outbox event_id: {event_id}")
            prev_state = str(row["state"])
            if prev_state not in {"UNKNOWN_DELIVERY", "ATTEMPTED", "PROVIDER_ACK"}:
                raise ContractError("INVALID_ARGUMENT", f"Cannot reconcile event in state {prev_state}")
            db.execute(
                """UPDATE outbox_events
                   SET state = 'PROVIDER_ACK',
                       provider_message_id = ?,
                       provider_ack_at_ms = ?,
                       reconciliation_required = 0,
                       claim_token = NULL,
                       lease_expires_at_ms = NULL,
                       updated_at_ms = ?
                   WHERE event_id = ?""",
                (provider_message_id, ts, ts, event_id),
            )
            self._record_transition(
                db,
                event_id=event_id,
                from_state=prev_state,
                to_state="PROVIDER_ACK",
                actor=actor,
                ts_ms=ts,
                detail={
                    "provider_message_id": provider_message_id,
                    "duplicate_risk": bool(row["duplicate_risk"]),
                    "user_read_receipt_proven": False,
                },
            )
            updated = db.execute("SELECT * FROM outbox_events WHERE event_id = ?", (event_id,)).fetchone()
            return dict(updated)

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        with self._connect(write=False) as db:
            row = db.execute("SELECT * FROM outbox_events WHERE event_id = ?", (event_id,)).fetchone()
            return dict(row) if row else None

    def get_transitions(self, event_id: str) -> list[dict[str, Any]]:
        with self._connect(write=False) as db:
            rows = db.execute(
                "SELECT * FROM outbox_transitions WHERE event_id = ? ORDER BY seq ASC",
                (event_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def summary_counts(self) -> dict[str, int]:
        with self._connect(write=False) as db:
            rows = db.execute("SELECT state, COUNT(*) AS cnt FROM outbox_events GROUP BY state").fetchall()
            return {str(r["state"]): int(r["cnt"]) for r in rows}
