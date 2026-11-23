"""Read-only verified Core journal reader and immutable card presentation helper."""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from quant_personal_decision_b2.journal import APP_ID as B2_APP_ID
from quant_personal_decision_b2.model import CARD as B2_CARD_SCHEMA
from quant_personal_decision_b2.model import EPISODE as B2_EPISODE_SCHEMA
from quant_personal_decision_b2.model import RECEIPT as B2_RECEIPT_SCHEMA
from quant_personal_decision_b2.model import digest as b2_digest

from .models import (
    APPROVED_SYMBOLS,
    DEFAULT_FRESHNESS_TTL_MS,
    PRESENTATION_SCHEMA_VERSION,
    SHA256_HEX_RE,
    CoreJournalError,
    parse_strict_int,
)

HKT = timezone(timedelta(hours=8), "HKT")
MARKET_STATUSES = frozenset(
    {"EXECUTABLE", "WATCH", "INVALID", "NO_SETUP", "SOURCE_BLOCKED", "NOT_EVALUATED"}
)
SYNTHETIC_ORIGINS = frozenset(
    {"fixture", "loopback", "SYNTHETIC_QA_ONLY", "fixture-local", "loopback-qa"}
)
HISTORICAL_ORIGINS = frozenset(
    {"HISTORICAL_REPLAY", "PERSONAL_HISTORICAL_REPLAY", "ARCHIVE_REPLAY"}
)
ALLOWED_RECEIPT_SCHEMAS = frozenset({B2_RECEIPT_SCHEMA, "B5_EVALUATION_RECEIPT_V1"})


def _format_ts(ms: int | None) -> dict[str, Any]:
    if ms is None:
        return {"ms": None, "utc": "unavailable", "hkt": "unavailable"}
    dt_utc = datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat(timespec="seconds")
    dt_hkt = datetime.fromtimestamp(ms / 1000, tz=HKT).isoformat(timespec="seconds")
    return {"ms": ms, "utc": dt_utc, "hkt": dt_hkt}


@dataclass(frozen=True)
class VerifiedCoreJournal:
    """Immutable verified read-only snapshot of an accepted B2/B5 decision journal."""

    journal_path: Path
    db_file_sha256: str
    policy: dict[str, Any]
    episodes: dict[str, dict[str, Any]]
    cards: tuple[dict[str, Any], ...]
    events: tuple[dict[str, Any], ...]
    event_chain_tail_sha256: str | None

    def list_cards(
        self, *, symbol: str | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        rows = [copy.deepcopy(c) for c in self.cards if symbol is None or c.get("symbol") == symbol]
        rows.sort(key=lambda c: (int(c["evaluated_ms"]), str(c["card_id"])), reverse=True)
        if limit is not None:
            return rows[:limit]
        return rows

    def select_card(
        self,
        *,
        card_id: str | None = None,
        episode_id: str | None = None,
        symbol: str | None = None,
    ) -> dict[str, Any]:
        matches = list(self.cards)
        if card_id is not None:
            matches = [c for c in matches if c.get("card_id") == card_id]
        if episode_id is not None:
            matches = [c for c in matches if c.get("episode_id") == episode_id]
        if symbol is not None:
            matches = [c for c in matches if c.get("symbol") == symbol]
        if not matches:
            raise CoreJournalError(
                "CORE_CARD_NOT_FOUND",
                f"card_id={card_id} episode_id={episode_id} symbol={symbol}",
            )
        matches.sort(key=lambda c: (int(c["evaluated_ms"]), str(c["card_id"])))
        return copy.deepcopy(matches[-1])


def classify_source_evidence(card: dict[str, Any]) -> dict[str, Any]:
    """Explicitly classify Core card origin without confusing synthetic, replay, missing, or genuine."""
    status = card.get("market_status")
    receipt = card.get("evaluation_receipt")
    evidence = card.get("evidence")
    source_lane = card.get("source_lane")
    source_origin = receipt.get("source_origin") if isinstance(receipt, dict) else None
    pub_sha = receipt.get("source_publication_sha256") if isinstance(receipt, dict) else None

    if status == "SOURCE_BLOCKED" or receipt is None:
        rejected = card.get("rejected_publication")
        classification = "MISSING_DATA" if status != "NOT_EVALUATED" else "UNAVAILABLE_WARMUP"
        return {
            "evidence_category": classification,
            "is_genuine_qualified": False,
            "card_evidence": evidence,
            "source_lane": source_lane,
            "source_origin": source_origin
            or (rejected.get("source_origin") if isinstance(rejected, dict) else None),
            "source_publication_sha256": pub_sha,
            "source_issue": card.get("source_issue"),
        }

    if not isinstance(receipt, dict):
        raise CoreJournalError("CORE_RECEIPT_INVALID")

    if (
        evidence == "SYNTHETIC_QA_ONLY"
        or source_lane == "SYNTHETIC_QA_ONLY"
        or source_origin in SYNTHETIC_ORIGINS
    ):
        if source_lane not in (None, "SYNTHETIC_QA_ONLY"):
            raise CoreJournalError("INCONSISTENT_SOURCE_EVIDENCE", str(source_lane))
        return {
            "evidence_category": "SYNTHETIC_QA_ONLY",
            "is_genuine_qualified": False,
            "card_evidence": evidence,
            "source_lane": source_lane,
            "source_origin": source_origin,
            "source_publication_sha256": pub_sha,
            "source_issue": None,
        }

    if (
        evidence in HISTORICAL_ORIGINS
        or source_lane in HISTORICAL_ORIGINS
        or source_origin in HISTORICAL_ORIGINS
    ):
        return {
            "evidence_category": "HISTORICAL_REPLAY",
            "is_genuine_qualified": False,
            "card_evidence": evidence,
            "source_lane": source_lane,
            "source_origin": source_origin,
            "source_publication_sha256": pub_sha,
            "source_issue": None,
        }

    if (
        evidence == "PERSONAL_PUBLIC_MARKET_GENUINE"
        and source_lane == "PERSONAL_PUBLIC_MARKET_GENUINE"
        and source_origin == "PERSONAL_PUBLIC_MARKET_GENUINE"
        and isinstance(pub_sha, str)
        and SHA256_HEX_RE.fullmatch(pub_sha)
    ):
        return {
            "evidence_category": "QUALIFIED_GENUINE_SOURCE",
            "is_genuine_qualified": True,
            "card_evidence": evidence,
            "source_lane": source_lane,
            "source_origin": source_origin,
            "source_publication_sha256": pub_sha,
            "source_issue": None,
        }

    raise CoreJournalError(
        "UNQUALIFIED_OR_INCONSISTENT_SOURCE_EVIDENCE",
        f"evidence={evidence} lane={source_lane} origin={source_origin}",
    )


def load_verified_core_journal(journal_path: Path) -> VerifiedCoreJournal:
    """Open accepted B2/B5 SQLite journal read-only and verify digests and event hash chain."""
    if journal_path.is_symlink():
        raise CoreJournalError("CORE_JOURNAL_SYMLINK_FORBIDDEN", str(journal_path))
    resolved = journal_path.resolve()
    if not resolved.is_file():
        raise CoreJournalError("CORE_JOURNAL_MISSING", str(resolved))

    sha_before = hashlib.sha256(resolved.read_bytes()).hexdigest()
    uri = resolved.as_uri() + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=2)
    except sqlite3.Error as exc:
        raise CoreJournalError("CORE_JOURNAL_OPEN_FAILED", str(exc)) from exc
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("PRAGMA foreign_keys=ON")
        app_id = conn.execute("PRAGMA application_id").fetchone()[0]
        user_ver = conn.execute("PRAGMA user_version").fetchone()[0]
        if app_id != B2_APP_ID or user_ver != 1:
            raise CoreJournalError(
                "CORE_JOURNAL_WRONG_SCHEMA", f"app_id={app_id} user_version={user_ver}"
            )
        id_rows = conn.execute("SELECT policy FROM identity").fetchall()
        if len(id_rows) != 1:
            raise CoreJournalError("CORE_IDENTITY_ROW_COUNT_INVALID")
        policy = json.loads(id_rows[0]["policy"])
        if not isinstance(policy, dict):
            raise CoreJournalError("CORE_POLICY_NOT_OBJECT")

        episodes: dict[str, dict[str, Any]] = {}
        for row in conn.execute(
            "SELECT id, symbol, group_id, immutable, payload_sha FROM episodes ORDER BY id"
        ):
            ep = json.loads(row["immutable"])
            if not isinstance(ep, dict) or b2_digest(ep) != row["payload_sha"]:
                raise CoreJournalError("CORE_EPISODE_DIGEST_MISMATCH", str(row["id"]))
            if ep.get("schema") != B2_EPISODE_SCHEMA:
                raise CoreJournalError("CORE_EPISODE_SCHEMA_INVALID", str(row["id"]))
            if (
                ep.get("episode_id") != row["id"]
                or ep.get("symbol") != row["symbol"]
                or ep.get("group_id") != row["group_id"]
            ):
                raise CoreJournalError("CORE_EPISODE_COLUMN_MISMATCH", str(row["id"]))
            episodes[str(row["id"])] = ep

        cards: list[dict[str, Any]] = []
        card_ids: set[str] = set()
        for row in conn.execute(
            "SELECT id, symbol, as_of, episode_id, payload, payload_sha FROM cards ORDER BY as_of ASC, id ASC"
        ):
            card = json.loads(row["payload"])
            if not isinstance(card, dict) or b2_digest(card) != row["payload_sha"]:
                raise CoreJournalError("CORE_CARD_DIGEST_MISMATCH", str(row["id"]))
            if card.get("schema") != B2_CARD_SCHEMA:
                raise CoreJournalError("CORE_CARD_SCHEMA_INVALID", str(row["id"]))
            if (
                card.get("card_id") != row["id"]
                or card.get("symbol") != row["symbol"]
                or card.get("evaluated_ms") != row["as_of"]
            ):
                raise CoreJournalError("CORE_CARD_COLUMN_MISMATCH", str(row["id"]))
            if card["symbol"] not in APPROVED_SYMBOLS:
                raise CoreJournalError("CORE_CARD_UNAPPROVED_SYMBOL", str(card["symbol"]))
            if card.get("market_status") not in MARKET_STATUSES:
                raise CoreJournalError("CORE_CARD_STATUS_INVALID", str(card.get("market_status")))
            receipt = card.get("evaluation_receipt")
            if receipt is not None:
                if (
                    not isinstance(receipt, dict)
                    or receipt.get("schema") not in ALLOWED_RECEIPT_SCHEMAS
                ):
                    raise CoreJournalError("CORE_RECEIPT_SCHEMA_INVALID", str(row["id"]))
            classify_source_evidence(card)
            ep_id = row["episode_id"]
            if ep_id is not None:
                if ep_id not in episodes or card.get("episode") != episodes[ep_id]:
                    raise CoreJournalError("CORE_CARD_EPISODE_MISMATCH", str(row["id"]))
            card_ids.add(str(row["id"]))
            cards.append(card)

        events: list[dict[str, Any]] = []
        prior_sha: str | None = None
        for row in conn.execute("SELECT * FROM events ORDER BY seq ASC"):
            detail = json.loads(row["payload"])
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
                raise CoreJournalError("CORE_EVENT_CHAIN_TAMPERED", f"seq={row['seq']}")
            if row["card_id"] not in card_ids:
                raise CoreJournalError("CORE_EVENT_CARD_UNKNOWN", str(row["card_id"]))
            prior_sha = str(row["sha"])
            events.append({**content, "sequence": row["seq"], "sha256": prior_sha})
    except (sqlite3.Error, json.JSONDecodeError) as exc:
        raise CoreJournalError("CORE_JOURNAL_READ_FAILED", str(exc)) from exc
    finally:
        conn.close()

    sha_after = hashlib.sha256(resolved.read_bytes()).hexdigest()
    if sha_before != sha_after:
        raise CoreJournalError("CORE_JOURNAL_MUTATED_DURING_READ")

    return VerifiedCoreJournal(
        journal_path=resolved,
        db_file_sha256=sha_after,
        policy=policy,
        episodes=episodes,
        cards=tuple(cards),
        events=tuple(events),
        event_chain_tail_sha256=prior_sha,
    )


def build_card_presentation(
    card: dict[str, Any],
    *,
    as_of_ms: int | None = None,
    freshness_ttl_ms: int = DEFAULT_FRESHNESS_TTL_MS,
) -> dict[str, Any]:
    """Build deterministic read-only CLI presentation directly from an immutable Core card."""
    parse_strict_int(freshness_ttl_ms, "freshness_ttl_ms", minimum=1, err_cls=CoreJournalError)
    if as_of_ms is not None:
        parse_strict_int(as_of_ms, "as_of_ms", minimum=1, err_cls=CoreJournalError)

    origin_info = classify_source_evidence(card)
    evaluated_ms = int(card["evaluated_ms"])
    episode = card.get("episode") if isinstance(card.get("episode"), dict) else None
    expires_ms = (
        int(episode["expires_at_ms"])
        if episode and episode.get("expires_at_ms") is not None
        else None
    )
    ref_ms = evaluated_ms if as_of_ms is None else as_of_ms
    is_expired = expires_ms is not None and ref_ms >= expires_ms

    if origin_info["evidence_category"] in ("MISSING_DATA", "UNAVAILABLE_WARMUP"):
        freshness_state = "UNAVAILABLE"
    elif as_of_ms is None:
        freshness_state = "OBSERVED_AT_EVALUATION"
    elif as_of_ms < evaluated_ms:
        freshness_state = "CLOCK_SKEW_UNVERIFIED"
    elif as_of_ms - evaluated_ms > freshness_ttl_ms:
        freshness_state = "STALE"
    else:
        freshness_state = "CURRENT"

    raw_plan = card.get("plan")
    plan_view: dict[str, Any] | None = None
    if isinstance(raw_plan, dict):
        plan_view = {
            "entry_low": str(raw_plan.get("entry_low")),
            "entry_high": str(raw_plan.get("entry_high")),
            "hard_stop": str(raw_plan.get("hard_stop")),
            "unit_stop_loss_usdt": (
                str(raw_plan["unit_stop_loss_usdt"])
                if raw_plan.get("unit_stop_loss_usdt") is not None
                else None
            ),
            "targets": [
                {
                    "label": str(t.get("label")),
                    "status": str(t.get("status")),
                    "price": str(t["price"]) if t.get("price") is not None else None,
                    "net_r": str(t["net_r"]) if t.get("net_r") is not None else None,
                    "reason": t.get("reason"),
                }
                for t in raw_plan.get("targets", ())
            ],
        }

    frame_ends = card.get("frame_end_ms") or {}
    timeframes = {tf: _format_ts(frame_ends.get(tf)) for tf in sorted(frame_ends)}
    return {
        "schema": PRESENTATION_SCHEMA_VERSION,
        "card_id": str(card["card_id"]),
        "symbol": str(card["symbol"]),
        "timeframe_anchor": "1h_setup_15m_trigger_4h_regime",
        "frame_end_times": timeframes,
        "direction": str(episode["direction"]) if episode else "NONE",
        "episode_id": card.get("episode_id"),
        "market_status": str(card["market_status"]),
        "reasons": list(card.get("reasons") or ()),
        "evidence_category": origin_info["evidence_category"],
        "is_genuine_qualified": origin_info["is_genuine_qualified"],
        "source_origin": origin_info["source_origin"],
        "source_publication_sha256": origin_info["source_publication_sha256"],
        "observation_time": _format_ts(evaluated_ms),
        "reference_as_of": _format_ts(as_of_ms),
        "freshness_state": freshness_state,
        "freshness_ttl_ms": freshness_ttl_ms,
        "absolute_expiry": _format_ts(expires_ms),
        "is_expired": is_expired,
        "immutable_core_plan": plan_view,
        "core_frozen_account": {
            "account_context_status": card.get("account_context_status", "UNAVAILABLE"),
            "account_overlay": card.get("account_overlay", "MANUAL_ACCOUNT_CHECK_REQUIRED"),
            "safe_position_size": card.get("safe_position_size", "UNKNOWN"),
            "portfolio_exposure_limits": card.get("portfolio_exposure_limits", "UNKNOWN"),
        },
        "source_issue": origin_info["source_issue"],
        "next_human_action": card.get("next_human_action"),
    }
