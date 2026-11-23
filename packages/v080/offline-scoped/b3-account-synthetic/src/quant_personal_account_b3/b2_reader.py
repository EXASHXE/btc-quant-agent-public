"""Strictly read-only B2 SQLite journal reader with full digest and event-chain verification."""

from __future__ import annotations

import copy
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quant_personal_decision_b2.journal import APP_ID as B2_APP_ID
from quant_personal_decision_b2.model import CARD as B2_CARD_SCHEMA
from quant_personal_decision_b2.model import EPISODE as B2_EPISODE_SCHEMA
from quant_personal_decision_b2.model import RECEIPT as B2_RECEIPT_SCHEMA
from quant_personal_decision_b2.model import SYNTHETIC as B2_SYNTHETIC_EVIDENCE
from quant_personal_decision_b2.model import digest as b2_digest

from .models import MARKET_SETUP_STATUSES, B2IntegrityError, raw_sha256


@dataclass(frozen=True)
class B2CardRecord:
    """Verified immutable read-only view of a committed B2 MarketCard."""

    card_id: str
    symbol: str
    as_of_ms: int
    episode_id: str | None
    market_status: str
    evidence: str
    payload_sha256: str
    card_payload: dict[str, Any]
    episode_payload: dict[str, Any] | None

    @property
    def plan(self) -> dict[str, Any] | None:
        raw = self.card_payload.get("plan")
        return copy.deepcopy(raw) if isinstance(raw, dict) else None

    @property
    def evaluation_receipt(self) -> dict[str, Any] | None:
        raw = self.card_payload.get("evaluation_receipt")
        return copy.deepcopy(raw) if isinstance(raw, dict) else None

    def immutable_card_copy(self) -> dict[str, Any]:
        return copy.deepcopy(self.card_payload)


@dataclass(frozen=True)
class B2JournalVerifiedView:
    """Complete verified read-only snapshot of an immutable B2 journal database."""

    journal_path: Path
    db_file_sha256: str
    policy: dict[str, Any]
    episodes: dict[str, dict[str, Any]]
    cards: tuple[B2CardRecord, ...]
    events: tuple[dict[str, Any], ...]
    event_chain_tail_sha256: str | None

    def get_card(
        self,
        *,
        card_id: str | None = None,
        episode_id: str | None = None,
        symbol: str | None = None,
    ) -> B2CardRecord:
        candidates = list(self.cards)
        if card_id is not None:
            candidates = [c for c in candidates if c.card_id == card_id]
        if episode_id is not None:
            candidates = [c for c in candidates if c.episode_id == episode_id]
        if symbol is not None:
            candidates = [c for c in candidates if c.symbol == symbol]
        if not candidates:
            raise B2IntegrityError("B2_CARD_NOT_FOUND", f"card_id={card_id} episode_id={episode_id} symbol={symbol}")
        candidates.sort(key=lambda c: (c.as_of_ms, c.card_id))
        return candidates[-1]


class ReadOnlyB2JournalReader:
    """Reads and cryptographically verifies an accepted B2 SQLite journal without ever writing to it."""

    def __init__(self, journal_path: Path) -> None:
        self.path = journal_path.resolve()
        if not self.path.exists() or not self.path.is_file():
            raise B2IntegrityError("B2_JOURNAL_MISSING", str(self.path))

    def _connect_readonly(self) -> sqlite3.Connection:
        # Strict read-only SQLite URI + query_only pragma: any write/migration/UPDATE/DELETE fails closed.
        uri = self.path.as_uri() + "?mode=ro"
        try:
            conn = sqlite3.connect(uri, uri=True, timeout=2)
        except sqlite3.Error as exc:
            raise B2IntegrityError("B2_JOURNAL_OPEN_FAILED", str(exc)) from exc
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def load_and_verify(self) -> B2JournalVerifiedView:
        """Open B2 read-only, verify schema/digests/hash-chain, and return immutable records."""
        file_hash_before = raw_sha256(self.path.read_bytes())
        conn = self._connect_readonly()
        try:
            app_id = conn.execute("PRAGMA application_id").fetchone()[0]
            user_ver = conn.execute("PRAGMA user_version").fetchone()[0]
            if app_id != B2_APP_ID or user_ver != 1:
                raise B2IntegrityError("B2_JOURNAL_WRONG_SCHEMA", f"app_id={app_id} user_version={user_ver}")

            id_rows = conn.execute("SELECT policy FROM identity").fetchall()
            if len(id_rows) != 1:
                raise B2IntegrityError("B2_IDENTITY_INVALID", f"count={len(id_rows)}")
            try:
                policy = json.loads(id_rows[0]["policy"])
            except json.JSONDecodeError as exc:
                raise B2IntegrityError("B2_POLICY_JSON_INVALID", str(exc)) from exc
            if not isinstance(policy, dict):
                raise B2IntegrityError("B2_POLICY_NOT_OBJECT")

            # Verify every episode digest.
            episodes: dict[str, dict[str, Any]] = {}
            for row in conn.execute("SELECT id, symbol, group_id, immutable, payload_sha FROM episodes ORDER BY id"):
                try:
                    ep = json.loads(row["immutable"])
                except json.JSONDecodeError as exc:
                    raise B2IntegrityError("B2_EPISODE_JSON_INVALID", row["id"]) from exc
                if not isinstance(ep, dict):
                    raise B2IntegrityError("B2_EPISODE_NOT_OBJECT", row["id"])
                if b2_digest(ep) != row["payload_sha"]:
                    raise B2IntegrityError("B2_EPISODE_DIGEST_MISMATCH", row["id"])
                if ep.get("schema") != B2_EPISODE_SCHEMA:
                    raise B2IntegrityError("B2_EPISODE_SCHEMA_INVALID", row["id"])
                if ep.get("episode_id") != row["id"] or ep.get("symbol") != row["symbol"] or ep.get("group_id") != row["group_id"]:
                    raise B2IntegrityError("B2_EPISODE_COLUMN_MISMATCH", row["id"])
                episodes[row["id"]] = ep

            # Verify every card digest and link consistency.
            cards: list[B2CardRecord] = []
            card_ids: set[str] = set()
            for row in conn.execute(
                "SELECT id, symbol, as_of, episode_id, structural_state, payload, payload_sha FROM cards ORDER BY as_of ASC, id ASC"
            ):
                try:
                    card = json.loads(row["payload"])
                except json.JSONDecodeError as exc:
                    raise B2IntegrityError("B2_CARD_JSON_INVALID", row["id"]) from exc
                if not isinstance(card, dict):
                    raise B2IntegrityError("B2_CARD_NOT_OBJECT", row["id"])
                if b2_digest(card) != row["payload_sha"]:
                    raise B2IntegrityError("B2_CARD_DIGEST_MISMATCH", row["id"])
                if card.get("schema") != B2_CARD_SCHEMA:
                    raise B2IntegrityError("B2_CARD_SCHEMA_INVALID", row["id"])
                if card.get("card_id") != row["id"] or card.get("symbol") != row["symbol"] or card.get("evaluated_ms") != row["as_of"]:
                    raise B2IntegrityError("B2_CARD_COLUMN_MISMATCH", row["id"])
                status = card.get("market_status")
                if not isinstance(status, str) or status not in MARKET_SETUP_STATUSES:
                    raise B2IntegrityError("B2_CARD_STATUS_INVALID", str(status))
                evidence = card.get("evidence")
                if evidence != B2_SYNTHETIC_EVIDENCE:
                    raise B2IntegrityError("B2_CARD_EVIDENCE_UNEXPECTED", str(evidence))
                receipt = card.get("evaluation_receipt")
                if receipt is not None and (not isinstance(receipt, dict) or receipt.get("schema") != B2_RECEIPT_SCHEMA):
                    raise B2IntegrityError("B2_RECEIPT_SCHEMA_INVALID", row["id"])

                ep_id = row["episode_id"]
                ep_payload: dict[str, Any] | None = None
                if ep_id is not None:
                    if ep_id not in episodes:
                        raise B2IntegrityError("B2_CARD_EPISODE_MISSING", ep_id)
                    ep_payload = episodes[ep_id]
                    if card.get("episode") != ep_payload:
                        raise B2IntegrityError("B2_CARD_EPISODE_MISMATCH", row["id"])

                card_ids.add(row["id"])
                cards.append(
                    B2CardRecord(
                        card_id=row["id"],
                        symbol=row["symbol"],
                        as_of_ms=row["as_of"],
                        episode_id=ep_id,
                        market_status=status,
                        evidence=evidence,
                        payload_sha256=row["payload_sha"],
                        card_payload=copy.deepcopy(card),
                        episode_payload=copy.deepcopy(ep_payload) if ep_payload is not None else None,
                    )
                )

            # Verify the complete B2 append-only event hash chain.
            events: list[dict[str, Any]] = []
            prior_sha: str | None = None
            for row in conn.execute("SELECT * FROM events ORDER BY seq ASC"):
                try:
                    detail = json.loads(row["payload"])
                except json.JSONDecodeError as exc:
                    raise B2IntegrityError("B2_EVENT_JSON_INVALID", str(row["seq"])) from exc
                content = {
                    "id": row["event_id"],
                    "kind": row["kind"],
                    "card_id": row["card_id"],
                    "episode_id": row["episode_id"],
                    "evidence": row["evidence"],
                    "detail": detail,
                    "prior_sha": row["prior_sha"],
                }
                if row["prior_sha"] != prior_sha or b2_digest(content) != row["sha"]:
                    raise B2IntegrityError("B2_EVENT_CHAIN_TAMPERED", f"seq={row['seq']}")
                if row["card_id"] not in card_ids:
                    raise B2IntegrityError("B2_EVENT_CARD_UNKNOWN", row["card_id"])
                prior_sha = row["sha"]
                events.append({**content, "sequence": row["seq"], "sha256": prior_sha})
        except sqlite3.Error as exc:
            raise B2IntegrityError("B2_SQLITE_READ_ERROR", str(exc)) from exc
        finally:
            conn.close()

        file_hash_after = raw_sha256(self.path.read_bytes())
        if file_hash_before != file_hash_after:
            raise B2IntegrityError("B2_FILE_MUTATED_DURING_READ")

        return B2JournalVerifiedView(
            journal_path=self.path,
            db_file_sha256=file_hash_after,
            policy=policy,
            episodes=episodes,
            cards=tuple(cards),
            events=tuple(events),
            event_chain_tail_sha256=prior_sha,
        )
