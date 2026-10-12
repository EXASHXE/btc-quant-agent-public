"""FeishuOutboxPort: Informational-only card formatter, local durable WAL, and loopback delivery.

Translates approved/rejected/pending/execution-state events into redacted informational
cards with deterministic SHA receipts and deduplication IDs.
Enforces:
- Local JSONL/WAL outbox by default; loopback HTTP only when allow_loopback=True.
- Bounded retry with exponential backoff on 429/500/503/timeout; immediate fail on 400/401.
- Zero portfolio/cash mutation, zero duplicate human approval, and zero delay of mandatory STOP.
- Strict credential/secret redaction and private-key/seed blocking.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from scripts.g1_offline_preview_r1.model import (
    SafetyViolation,
    canonical,
    digest,
    exact,
    redact_text,
    timestamp,
)
from scripts.g1_offline_preview_r1.storage import strict_json

from .crypto_ed25519 import SYNTHETIC_TEST_OPERATOR_SEEDS
from .loopback_servers import LoopbackHTTPConnection
from .no_order_port import NoOrderPort, guard_scratch_dir

VALID_CARD_CATEGORIES = {
    "APPROVAL_NEEDED",
    "APPROVED_INFO",
    "REJECTED_INFO",
    "PENDING_INFO",
    "EXECUTION_STATE",
    "NO_ACTION",
}

CARD_SCHEMA_KEYS = {
    "schema_version",
    "deduplication_id",
    "card_category",
    "event_kind",
    "phase",
    "at",
    "trace_id",
    "span_id",
    "source_hash",
    "signal_id",
    "informational_only",
    "execution_authority",
    "safety_status",
    "summary_text",
    "payload_sha256",
}

FORBIDDEN_RAW_SECRET_TOKENS = (
    "-----begin private key-----",
    "-----begin openssh private key-----",
    "sk-live-",
    "feishu_app_secret",
    "binance_api_secret",
)


def _ensure_no_leaked_secrets(text: str) -> None:
    lowered = text.lower()
    if any(tok in lowered for tok in FORBIDDEN_RAW_SECRET_TOKENS):
        raise SafetyViolation("FEISHU_SECRET_CONTENT_BLOCKED")
    for seed in SYNTHETIC_TEST_OPERATOR_SEEDS.values():
        if seed.hex().lower() in lowered:
            raise SafetyViolation("FEISHU_SECRET_CONTENT_BLOCKED")
    if any(w in lowered for w in ("api_key=", "secret=", "password=", "token=", "bearer ")):
        raise SafetyViolation("FEISHU_SECRET_CONTENT_BLOCKED")


class FeishuOutboxPort:
    """Durable informational outbox port with local WAL and optional loopback HTTP transport."""

    def __init__(
        self,
        storage_dir: str | Path,
        *,
        endpoint_url: str | None = None,
        allow_loopback: bool = False,
        allowed_endpoints: set[tuple[str, int]] | None = None,
        max_attempts: int = 3,
        base_backoff_ms: int = 10,
        timeout_ms: int = 150,
        no_order_port: NoOrderPort | None = None,
        temporary: bool = False,
    ) -> None:
        if not (1 <= max_attempts <= 5):
            raise SafetyViolation("FEISHU_CONFIG_INVALID")
        if not (0 <= base_backoff_ms <= 1000):
            raise SafetyViolation("FEISHU_CONFIG_INVALID")
        if not (1 <= timeout_ms <= 5000):
            raise SafetyViolation("FEISHU_CONFIG_INVALID")

        self.root = guard_scratch_dir(storage_dir, temporary=temporary)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.wal_path = self.root / "feishu_outbox.wal.jsonl"
        if self.wal_path.is_symlink():
            raise SafetyViolation("PATH_SYMLINK")
        self.endpoint_url = endpoint_url
        self.allow_loopback = allow_loopback
        self.allowed_endpoints = set(allowed_endpoints or set())
        self.max_attempts = max_attempts
        self.base_backoff_ms = base_backoff_ms
        self.timeout_ms = timeout_ms
        self.no_order_port = no_order_port or NoOrderPort()
        self.receipts_by_dedup_id: dict[str, dict[str, Any]] = {}
        self.duplicate_Ignored_count: int = 0
        self.backoff_history_ms: list[int] = []
        self.chain: str = digest({"wal": "FEISHU_OUTBOX_WAL_V1"})
        self.seq: int = 0
        self._recover_wal()

    def _recover_wal(self) -> None:
        if not self.wal_path.exists():
            fd = os.open(self.wal_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                header = (
                    canonical({"format": "FEISHU_OUTBOX_WAL_V1", "genesis_chain": self.chain})
                    + "\n"
                ).encode("utf-8")
                os.write(fd, header)
                os.fsync(fd)
            finally:
                os.close(fd)
            return

        raw = self.wal_path.read_bytes()
        if not raw.endswith(b"\n"):
            raise SafetyViolation("FEISHU_WAL_TRUNCATED")
        lines = raw.decode("utf-8").splitlines()
        if not lines or strict_json(lines[0]) != {
            "format": "FEISHU_OUTBOX_WAL_V1",
            "genesis_chain": self.chain,
        }:
            raise SafetyViolation("FEISHU_WAL_GENESIS_MISMATCH")
        for line in lines[1:]:
            rec = strict_json(line)
            exact(
                rec,
                {"seq", "previous", "entry", "entry_hash", "record_hash"},
                "FEISHU_WAL_SCHEMA",
            )
            body = {k: v for k, v in rec.items() if k != "record_hash"}
            if (
                rec["seq"] != self.seq + 1
                or rec["previous"] != self.chain
                or digest(body) != rec["record_hash"]
            ):
                raise SafetyViolation("FEISHU_WAL_CHAIN_CORRUPT")
            entry = rec["entry"]
            if digest(entry) != rec["entry_hash"]:
                raise SafetyViolation("FEISHU_WAL_ENTRY_HASH_MISMATCH")
            if entry.get("delivered") is True:
                self.receipts_by_dedup_id[entry["deduplication_id"]] = entry
            self.seq = rec["seq"]
            self.chain = rec["record_hash"]

    def build_card(
        self,
        *,
        deduplication_id: str,
        card_category: str,
        event_kind: str,
        phase: str,
        at: int,
        trace_id: str,
        source_hash: str | None,
        signal_id: str | None,
        summary_text: str,
        reject_raw_secrets: bool = False,
    ) -> dict[str, Any]:
        """Format and validate a redacted FeishuInformationalCardV1."""
        if not isinstance(deduplication_id, str) or not deduplication_id:
            raise SafetyViolation("FEISHU_DEDUP_ID_INVALID")
        if card_category not in VALID_CARD_CATEGORIES:
            raise SafetyViolation("FEISHU_CARD_CATEGORY_INVALID")
        if not isinstance(event_kind, str) or not event_kind:
            raise SafetyViolation("FEISHU_EVENT_KIND_INVALID")
        if not isinstance(phase, str) or not phase:
            raise SafetyViolation("FEISHU_PHASE_INVALID")
        timestamp(at)
        if not isinstance(trace_id, str) or not trace_id:
            raise SafetyViolation("FEISHU_TRACE_ID_INVALID")
        if not isinstance(summary_text, str) or not summary_text:
            raise SafetyViolation("FEISHU_SUMMARY_INVALID")

        if reject_raw_secrets:
            _ensure_no_leaked_secrets(summary_text)
        redacted_summary = redact_text(summary_text)
        _ensure_no_leaked_secrets(redacted_summary)

        span_id = digest([deduplication_id, "feishu_card_span"])[:16]
        body_without_sha = {
            "schema_version": "feishu-outbox-card-v1",
            "deduplication_id": deduplication_id,
            "card_category": card_category,
            "event_kind": event_kind,
            "phase": phase,
            "at": at,
            "trace_id": trace_id,
            "span_id": span_id,
            "source_hash": source_hash,
            "signal_id": signal_id,
            "informational_only": True,
            "execution_authority": "NONE",
            "safety_status": "DRY_RUN_NO_NETWORK_NO_ORDERING",
            "summary_text": redacted_summary,
        }
        card = {
            **body_without_sha,
            "payload_sha256": digest(body_without_sha),
        }
        exact(card, CARD_SCHEMA_KEYS, "FEISHU_CARD_SCHEMA_INVALID")
        return card

    def build_card_from_g1_outbox_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """Translate a read-only G1 state['outbox'] row into a FeishuInformationalCardV1."""
        ev_kind = str(row["event_kind"])
        if row["kind"] == "NO_ACTION":
            cat = "NO_ACTION"
        elif row["kind"] == "APPROVAL_NEEDED":
            cat = "APPROVAL_NEEDED"
        elif ev_kind == "APPROVE":
            cat = "APPROVED_INFO"
        elif ev_kind in ("PROPOSE", "ANALYZE"):
            cat = "PENDING_INFO"
        else:
            cat = "EXECUTION_STATE"
        summary = (
            f"[{cat}] event={ev_kind} phase={row['phase']} signal={row.get('signal_id')} "
            f"cash={row['cash']} qty={row['remaining_qty']} (INFORMATIONAL_ONLY)"
        )
        return self.build_card(
            deduplication_id=row["key"],
            card_category=cat,
            event_kind=ev_kind,
            phase=row["phase"],
            at=row["at"],
            trace_id=row["trace_id"],
            source_hash=row.get("source_hash"),
            signal_id=row.get("signal_id"),
            summary_text=summary,
        )

    def _append_wal(self, entry: dict[str, Any], *, hook: Any | None = None) -> None:
        if hook:
            hook("before_feishu_wal_append", entry)
        body = {
            "seq": self.seq + 1,
            "previous": self.chain,
            "entry": entry,
            "entry_hash": digest(entry),
        }
        record = {**body, "record_hash": digest(body)}
        raw = (canonical(record) + "\n").encode("utf-8")
        fd = os.open(self.wal_path, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
        try:
            offset = 0
            while offset < len(raw):
                offset += os.write(fd, raw[offset:])
            os.fsync(fd)
        finally:
            os.close(fd)
        self.seq = record["seq"]
        self.chain = record["record_hash"]
        if hook:
            hook("after_feishu_wal_fsync", entry)

    def deliver_card(
        self,
        card: dict[str, Any],
        *,
        hook: Any | None = None,
    ) -> dict[str, Any]:
        """Deliver one FeishuInformationalCardV1 idempotently (local WAL + optional loopback HTTP)."""
        exact(card, CARD_SCHEMA_KEYS, "FEISHU_CARD_SCHEMA_INVALID")
        _ensure_no_leaked_secrets(card["summary_text"])
        body_without_sha = {k: v for k, v in card.items() if k != "payload_sha256"}
        if digest(body_without_sha) != card["payload_sha256"]:
            raise SafetyViolation("FEISHU_CARD_HASH_MISMATCH")

        dedup_id = card["deduplication_id"]
        if dedup_id in self.receipts_by_dedup_id:
            existing = self.receipts_by_dedup_id[dedup_id]
            if existing["payload_sha256"] != card["payload_sha256"]:
                raise SafetyViolation("FEISHU_DEDUP_PAYLOAD_DRIFT")
            self.duplicate_Ignored_count += 1
            return {
                **existing,
                "dedup_status": "IDEMPOTENT_DUPLICATE",
            }

        # Local-only mode when endpoint_url is None
        if self.endpoint_url is None:
            receipt = {
                "schema_version": "feishu-delivery-receipt-v1",
                "delivered": True,
                "transport": "LOCAL_JSONL_WAL_ONLY",
                "deduplication_id": dedup_id,
                "payload_sha256": card["payload_sha256"],
                "receipt_sha256": digest(
                    [dedup_id, card["payload_sha256"], "LOCAL_WAL_RECEIPT_V1"]
                ),
                "http_status": 200,
                "attempts": 1,
                "dedup_status": "FIRST_DELIVERY",
                "trace_id": card["trace_id"],
                "span_id": card["span_id"],
            }
            self._append_wal(receipt, hook=hook)
            self.receipts_by_dedup_id[dedup_id] = receipt
            return receipt

        # Loopback HTTP transport mode
        host, port, path = self.no_order_port.validate_endpoint_url(
            self.endpoint_url,
            allow_loopback=self.allow_loopback,
            allowed_endpoints=self.allowed_endpoints,
        )
        req_bytes = canonical(card).encode("utf-8")
        last_code = "FEISHU_RETRY_CAP_EXHAUSTED"
        last_status = 0
        attempts_made = 0

        for attempt in range(1, self.max_attempts + 1):
            if attempt > 1:
                backoff_ms = self.base_backoff_ms * (2 ** (attempt - 2))
                self.backoff_history_ms.append(backoff_ms)
                if backoff_ms > 0:
                    time.sleep(backoff_ms / 1000.0)
            attempts_made = attempt
            conn = LoopbackHTTPConnection(host, port, timeout=self.timeout_ms / 1000.0)
            try:
                conn.request(
                    "POST",
                    path,
                    body=req_bytes,
                    headers={"Content-Type": "application/json; charset=utf-8"},
                )
                resp = conn.getresponse()
                last_status = resp.status
                raw_resp = resp.read(4096)
                if last_status == 200:
                    parsed = strict_json(raw_resp.decode("utf-8"))
                    receipt = {
                        "schema_version": "feishu-delivery-receipt-v1",
                        "delivered": True,
                        "transport": "LOOPBACK_HTTP_FAKE_FEISHU",
                        "deduplication_id": dedup_id,
                        "payload_sha256": card["payload_sha256"],
                        "receipt_sha256": parsed["receipt_sha256"],
                        "http_status": 200,
                        "attempts": attempts_made,
                        "dedup_status": parsed.get("server_dedup_status", "FIRST_DELIVERY"),
                        "trace_id": card["trace_id"],
                        "span_id": card["span_id"],
                    }
                    self._append_wal(receipt, hook=hook)
                    self.receipts_by_dedup_id[dedup_id] = receipt
                    return receipt
                if last_status in (400, 401, 403, 409):
                    last_code = f"FEISHU_HTTP_{last_status}"
                    break
                if last_status in (429, 500, 502, 503, 504):
                    last_code = f"FEISHU_RETRY_CAP_EXHAUSTED_HTTP_{last_status}"
                    continue
                last_code = f"FEISHU_HTTP_{last_status}"
                break
            except TimeoutError:
                last_code = "FEISHU_TIMEOUT_EXHAUSTED"
                continue
            except OSError:
                last_code = "FEISHU_TRANSPORT_ERROR"
                continue
            finally:
                conn.close()

        failure_entry = {
            "schema_version": "feishu-delivery-receipt-v1",
            "delivered": False,
            "transport": "LOOPBACK_HTTP_FAKE_FEISHU",
            "deduplication_id": dedup_id,
            "payload_sha256": card["payload_sha256"],
            "receipt_sha256": digest([dedup_id, last_code, attempts_made]),
            "http_status": last_status,
            "attempts": attempts_made,
            "failure_code": last_code,
            "trace_id": card["trace_id"],
            "span_id": card["span_id"],
        }
        self._append_wal(failure_entry, hook=hook)
        raise SafetyViolation(last_code)

    def deliver_state_outbox(
        self,
        state: dict[str, Any],
        *,
        hook: Any | None = None,
    ) -> list[dict[str, Any]]:
        """Deliver all rows in state['outbox'] without mutating state or delaying required exits."""
        if state.get("required_exit") is not None:
            raise SafetyViolation("REQUIRED_EXIT_PRECEDES_OUTBOX_DELIVERY")
        snapshot_before = digest(state)
        receipts: list[dict[str, Any]] = []
        for row in state.get("outbox", []):
            card = self.build_card_from_g1_outbox_row(row)
            rec = self.deliver_card(card, hook=hook)
            receipts.append(rec)
        if digest(state) != snapshot_before:
            raise SafetyViolation("FEISHU_OUTBOX_MUTATED_STATE")
        return receipts
