"""Read-only QUANT Core journal reader, integrity verifier, and V1 SignalSnapshot projector."""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contract import (
    ALLOWED_GENUINE_EVIDENCE,
    ALLOWED_SYNTHETIC_ORIGINS,
    APPROVED_DIRECTIONS,
    APPROVED_FAMILIES,
    APPROVED_SYMBOLS,
    CONTRACT_VERSION,
    EVIDENCE_SYNTHETIC,
    SHA256_HEX_RE,
    SYNTHETIC_BANNER,
    ContractError,
    b2_sha256,
    validate_decimal_strings_only,
    validate_diagnostic_record,
    validate_signal_snapshot,
)

B2_JOURNAL_APP_ID = 0x51423244
B2_JOURNAL_USER_VERSION = 1
REQUIRED_JOURNAL_TABLES = frozenset({"identity", "episodes", "cards", "events"})
REQUIRED_APPEND_TRIGGERS = frozenset({
    "lock_identity_UPDATE",
    "lock_identity_DELETE",
    "lock_episodes_UPDATE",
    "lock_episodes_DELETE",
    "lock_cards_UPDATE",
    "lock_cards_DELETE",
    "lock_events_UPDATE",
    "lock_events_DELETE",
})
FORBIDDEN_PRIVATE_TOKENS = ("b3", "private", "account_db", "user_data", "credential", "secret", "keyring")
FORBIDDEN_PRIVATE_PATH_TOKENS = (
    "lt-v080-personal-mvp-account-aware-b3",
    "b3-01",
    "private_user_data",
    "account_db",
    "keyring",
)
FORBIDDEN_PRIVATE_TABLES = frozenset({
    "accounts",
    "balances",
    "positions",
    "orders",
    "fills",
    "trades",
    "credentials",
    "private_state",
    "account_overlay",
})

DEFAULT_FRESHNESS_TTL_MS = 15 * 60_000
DEFAULT_CLOCK_SKEW_MS = 5_000


@dataclass(frozen=True)
class ApprovedJournalSource:
    """Configuration for one approved read-only market-side B2/B4/B5 SQLite journal."""

    source_id: str
    path: Path
    allow_hypothetical_genuine: bool = False


@dataclass(frozen=True)
class VerifiedCardRecord:
    """Verified immutable card + episode + journal publication event metadata."""

    source_id: str
    card_id: str
    card_version: str
    episode_id: str | None
    symbol: str
    evaluated_at_ms: int
    observed_at_ms: int | None
    pub_seq: int
    pub_sha: str
    source_evidence_class: str
    card: dict[str, Any]
    episode_row: dict[str, Any] | None
    events_for_episode: tuple[dict[str, Any], ...]
    latest_reprice_event: dict[str, Any] | None


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _assert_not_private_path(path: Path) -> None:
    name_lower = path.name.lower()
    for token in FORBIDDEN_PRIVATE_TOKENS:
        if token in name_lower:
            raise ContractError(
                "UNAUTHORIZED",
                f"Refused potential private/B3 database filename token ({token!r})",
            )
    full_lower = path.as_posix().lower()
    for token in FORBIDDEN_PRIVATE_PATH_TOKENS:
        if token in full_lower:
            raise ContractError(
                "UNAUTHORIZED",
                f"Refused potential private/B3 database path token ({token!r})",
            )


def _open_readonly_sqlite(path: Path) -> sqlite3.Connection:
    resolved = path.resolve()
    _assert_not_private_path(resolved)
    if not resolved.exists() or not resolved.is_file():
        raise ContractError("SOURCE_UNAVAILABLE", "Approved journal file does not exist")
    if resolved.is_symlink():
        raise ContractError("INTEGRITY_FAILURE", "Refused symlinked journal path")
    uri = resolved.as_uri() + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=2.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only = ON")
    except sqlite3.Error as exc:
        raise ContractError("SOURCE_UNAVAILABLE", f"Failed to open journal read-only: {exc}") from exc
    return conn


def _verify_journal_schema(conn: sqlite3.Connection) -> None:
    app_id = conn.execute("PRAGMA application_id").fetchone()[0]
    user_version = conn.execute("PRAGMA user_version").fetchone()[0]
    if app_id != B2_JOURNAL_APP_ID or user_version != B2_JOURNAL_USER_VERSION:
        raise ContractError(
            "INTEGRITY_FAILURE",
            f"Unexpected journal header app_id={app_id:#x} user_version={user_version}",
        )
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if not REQUIRED_JOURNAL_TABLES.issubset(tables):
        raise ContractError("INTEGRITY_FAILURE", "Journal missing required B2 append-only tables")
    lower_tables = {t.lower() for t in tables}
    if lower_tables & FORBIDDEN_PRIVATE_TABLES:
        raise ContractError("UNAUTHORIZED", "Forbidden private account table detected in journal")
    triggers = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall()
    }
    if not REQUIRED_APPEND_TRIGGERS.issubset(triggers):
        raise ContractError("INTEGRITY_FAILURE", "Journal missing append-only immutability triggers")
    policies = conn.execute("SELECT policy FROM identity").fetchall()
    if len(policies) != 1:
        raise ContractError("INTEGRITY_FAILURE", "Journal identity policy row missing or duplicated")


def _verify_and_load_events(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    prior_sha: str | None = None
    verified: list[dict[str, Any]] = []
    rows = conn.execute("SELECT * FROM events ORDER BY seq ASC").fetchall()
    for row in rows:
        try:
            detail = json.loads(row["payload"])
        except Exception as exc:
            raise ContractError("INTEGRITY_FAILURE", f"Corrupt event payload JSON at seq={row['seq']}") from exc
        content = {
            "id": row["event_id"],
            "kind": row["kind"],
            "card_id": row["card_id"],
            "episode_id": row["episode_id"],
            "evidence": row["evidence"],
            "prior_sha": row["prior_sha"],
            "detail": detail,
        }
        if row["prior_sha"] != prior_sha or b2_sha256(content) != row["sha"]:
            raise ContractError(
                "INTEGRITY_FAILURE",
                f"Event hash chain broken at seq={row['seq']}",
            )
        prior_sha = row["sha"]
        verified.append({
            "seq": int(row["seq"]),
            "event_id": str(row["event_id"]),
            "card_id": str(row["card_id"]),
            "episode_id": str(row["episode_id"]) if row["episode_id"] is not None else None,
            "kind": str(row["kind"]),
            "evidence": str(row["evidence"]),
            "detail": detail,
            "prior_sha": row["prior_sha"],
            "sha256": prior_sha,
        })
    return verified


def _extract_source_refs(card: dict[str, Any]) -> tuple[str, str | None, str | None, int | None]:
    receipt = card.get("evaluation_receipt")
    rejected = card.get("rejected_publication")
    if isinstance(receipt, dict):
        origin = str(receipt.get("source_origin") or "UNKNOWN")
        pub_sha = receipt.get("source_publication_sha256")
        raw_receipts = receipt.get("raw_receipts")
        if raw_receipts is not None:
            receipt_sha: str | None = b2_sha256(receipt)
        else:
            receipt_sha = receipt.get("receipt_sha256")
        source_as_of = receipt.get("source_published_venue_ms")
        if source_as_of is None:
            source_as_of = receipt.get("bar_cutoff_venue_ms")
        return origin, receipt_sha, pub_sha, int(source_as_of) if type(source_as_of) is int else None
    if isinstance(rejected, dict):
        origin = str(rejected.get("source_origin") or "UNKNOWN")
        pub_sha = rejected.get("source_publication_sha256")
        source_as_of = rejected.get("source_published_venue_ms")
        return origin, None, pub_sha, int(source_as_of) if type(source_as_of) is int else None
    return "UNKNOWN", None, None, None


def _classify_and_verify_evidence(
    card: dict[str, Any],
    *,
    allow_hypothetical_genuine: bool,
) -> str:
    """Strictly classify source evidence; fail closed on missing or forged genuine labels."""
    if card.get("b3_schema") or card.get("account_context_status") != "UNAVAILABLE":
        raise ContractError("UNAUTHORIZED", "Private account payload detected in market card")
    if card.get("account_overlay") != "MANUAL_ACCOUNT_CHECK_REQUIRED":
        raise ContractError("INTEGRITY_FAILURE", "Unexpected account_overlay in market card")
    if card.get("portfolio_exposure_limits") not in ("UNKNOWN", None):
        raise ContractError("UNAUTHORIZED", "Unexpected exposure limit field in market card")

    evidence = card.get("evidence")
    source_lane = card.get("source_lane")
    origin, receipt_sha, pub_sha, _ = _extract_source_refs(card)
    warnings = card.get("warnings") or []

    if not isinstance(evidence, str) or not evidence:
        raise ContractError("INTEGRITY_FAILURE", "Card missing mandatory source evidence label")

    if evidence == EVIDENCE_SYNTHETIC:
        if source_lane is not None and source_lane != EVIDENCE_SYNTHETIC:
            raise ContractError("INTEGRITY_FAILURE", f"Conflicting source_lane {source_lane!r} on synthetic card")
        if origin != "UNKNOWN" and origin not in ALLOWED_SYNTHETIC_ORIGINS:
            raise ContractError("INTEGRITY_FAILURE", f"Unexpected source_origin {origin!r} on synthetic card")
        return EVIDENCE_SYNTHETIC

    if evidence in ALLOWED_GENUINE_EVIDENCE:
        if origin in ALLOWED_SYNTHETIC_ORIGINS or origin == "UNKNOWN":
            raise ContractError(
                "INTEGRITY_FAILURE",
                f"Forged genuine evidence label: origin={origin!r} cannot support {evidence!r}",
            )
        if any(tok in str(warnings) for tok in ("SYNTHETIC_QA_ONLY", "NOT_GENUINE_MARKET")):
            raise ContractError("INTEGRITY_FAILURE", "Forged genuine label with synthetic warnings")
        if not SHA256_HEX_RE.fullmatch(str(receipt_sha or "")) or not SHA256_HEX_RE.fullmatch(str(pub_sha or "")):
            raise ContractError("INTEGRITY_FAILURE", "Genuine evidence missing verified receipt/publication SHA-256")
        if not allow_hypothetical_genuine:
            raise ContractError(
                "SOURCE_BLOCKED",
                "Genuine public market evidence not authorized in offline H1 scope",
            )
        return evidence

    raise ContractError("INTEGRITY_FAILURE", f"Unknown source evidence class: {evidence!r}")


def _compute_freshness(
    *,
    card: dict[str, Any],
    source_as_of_ms: int | None,
    reference_as_of_ms: int,
    freshness_ttl_ms: int,
    allowed_clock_skew_ms: int,
) -> str:
    if source_as_of_ms is None:
        return "UNKNOWN"
    if reference_as_of_ms + allowed_clock_skew_ms < source_as_of_ms:
        return "UNKNOWN"
    issue = card.get("source_issue")
    if isinstance(issue, dict) and "STALE" in str(issue.get("detail", "")).upper():
        return "STALE"
    if reference_as_of_ms - source_as_of_ms > freshness_ttl_ms:
        return "STALE"
    if card.get("market_status") == "SOURCE_BLOCKED" and not card.get("data_ready", False):
        return "STALE"
    return "CURRENT"


def _project_plan(card: dict[str, Any]) -> dict[str, Any] | None:
    plan = card.get("plan")
    if plan is None:
        return None
    if not isinstance(plan, dict):
        raise ContractError("INTEGRITY_FAILURE", "Card plan must be dict or null")
    validate_decimal_strings_only(plan, path="card.plan")
    return json.loads(json.dumps(plan))


def _build_projected_base(
    record: VerifiedCardRecord,
    *,
    reference_as_of_ms: int | None,
    verified_at_ms: int,
    freshness_ttl_ms: int = DEFAULT_FRESHNESS_TTL_MS,
    allowed_clock_skew_ms: int = DEFAULT_CLOCK_SKEW_MS,
) -> dict[str, Any]:
    card = record.card
    episode = card.get("episode") or record.episode_row or {}
    origin, receipt_sha, pub_sha, source_as_of_ms = _extract_source_refs(card)

    symbol = card.get("symbol")
    if symbol not in APPROVED_SYMBOLS:
        raise ContractError("INTEGRITY_FAILURE", f"Unapproved symbol in journal card: {symbol!r}")

    direction = episode.get("direction") if episode else None
    if direction is not None and direction not in APPROVED_DIRECTIONS:
        raise ContractError("INTEGRITY_FAILURE", f"Invalid direction in card: {direction!r}")

    family = episode.get("family") if episode else None
    if family is not None and family not in APPROVED_FAMILIES:
        raise ContractError("INTEGRITY_FAILURE", f"Invalid strategy family in card: {family!r}")

    market_status = card.get("market_status")
    raw_reasons = card.get("reasons") or []
    reason_codes = [str(r) for r in raw_reasons]

    expires_at_ms = episode.get("expires_at_ms") if isinstance(episode, dict) else None
    if expires_at_ms is not None:
        if type(expires_at_ms) is not int or expires_at_ms <= 0:
            raise ContractError("INTEGRITY_FAILURE", f"Invalid expires_at_ms: {expires_at_ms!r}")
        if reference_as_of_ms is None:
            is_expired = False
            expiry_status = "EXPIRY_UNKNOWN"
        else:
            is_expired = reference_as_of_ms >= expires_at_ms
            expiry_status = "EXPIRED" if is_expired else "VALID"
    else:
        is_expired = False
        expiry_status = "EXPIRY_UNKNOWN"

    freshness_state = (
        "UNKNOWN"
        if reference_as_of_ms is None
        else _compute_freshness(
            card=card,
            source_as_of_ms=source_as_of_ms,
            reference_as_of_ms=reference_as_of_ms,
            freshness_ttl_ms=freshness_ttl_ms,
            allowed_clock_skew_ms=allowed_clock_skew_ms,
        )
    )

    reprice_payload = card.get("reprice")
    latest_reprice: dict[str, Any] | None = None
    if isinstance(reprice_payload, dict) or record.latest_reprice_event is not None:
        ev = record.latest_reprice_event
        latest_reprice = {
            "reprice": reprice_payload,
            "reprice_event_id": ev["event_id"] if ev else None,
            "reprice_event_sha256": ev["sha256"] if ev else None,
            "reprice_card_id": ev["card_id"] if ev else record.card_id,
            "reprice_seq": ev["seq"] if ev else None,
        }

    is_synthetic = record.source_evidence_class == EVIDENCE_SYNTHETIC
    source_banner = (
        SYNTHETIC_BANNER
        if is_synthetic
        else f"{record.source_evidence_class} / MARKET_SIDE_ONLY"
    )

    return {
        "episode_id": record.episode_id,
        "card_id": record.card_id,
        "card_version": record.card_version,
        "symbol": symbol,
        "direction": direction or "UNKNOWN",
        "strategy_family": family or "UNKNOWN",
        "market_status": market_status,
        "episode_state": card.get("episode_state"),
        "status_reason_codes": reason_codes,
        "source_evidence_class": record.source_evidence_class,
        "source_origin": origin,
        "source_receipt_sha256": receipt_sha,
        "source_publication_sha256": pub_sha,
        "source_as_of_ms": source_as_of_ms,
        "evaluated_at_ms": record.evaluated_at_ms,
        "observed_at_ms": record.observed_at_ms,
        "absolute_expiry_ms": expires_at_ms,
        "expiry_status": expiry_status,
        "is_expired": is_expired,
        "freshness_state": freshness_state,
        "account_context_status": "UNAVAILABLE",
        "account_overlay": "MANUAL_ACCOUNT_CHECK_REQUIRED",
        "portfolio_exposure_limits": "UNKNOWN",
        "safe_position_size": "UNKNOWN",
        "plan": _project_plan(card),
        "latest_reprice": latest_reprice,
        "reasons": reason_codes,
        "human_action": str(card.get("next_human_action") or ""),
        "verified_at_ms": verified_at_ms,
        "contract_version": CONTRACT_VERSION,
        "source_banner": source_banner,
        "not_a_real_trade_signal": is_synthetic,
        "source_id": record.source_id,
        "frame_end_ms": dict(card.get("frame_end_ms") or {}),
    }


def project_signal_snapshot(
    record: VerifiedCardRecord,
    *,
    reference_as_of_ms: int | None,
    verified_at_ms: int,
    freshness_ttl_ms: int = DEFAULT_FRESHNESS_TTL_MS,
    allowed_clock_skew_ms: int = DEFAULT_CLOCK_SKEW_MS,
) -> dict[str, Any]:
    """Project one episode-bound verified Core card into the exact V1 SignalSnapshot schema."""
    if not record.episode_id:
        raise ContractError(
            "INTEGRITY_FAILURE",
            f"Null-episode card {record.card_id} cannot be projected as an active SignalSnapshot",
        )
    snapshot = _build_projected_base(
        record,
        reference_as_of_ms=reference_as_of_ms,
        verified_at_ms=verified_at_ms,
        freshness_ttl_ms=freshness_ttl_ms,
        allowed_clock_skew_ms=allowed_clock_skew_ms,
    )
    validate_signal_snapshot(snapshot)
    return snapshot


def project_diagnostic_record(
    record: VerifiedCardRecord,
    *,
    reference_as_of_ms: int | None,
    verified_at_ms: int,
    freshness_ttl_ms: int = DEFAULT_FRESHNESS_TTL_MS,
    allowed_clock_skew_ms: int = DEFAULT_CLOCK_SKEW_MS,
) -> dict[str, Any]:
    """Project a null-episode Core card (NO_SETUP / NOT_EVALUATED) as a non-actionable diagnostic record."""
    if record.episode_id is not None:
        raise ContractError(
            "INTEGRITY_FAILURE",
            f"Episode-bound card {record.card_id} cannot be projected as a null-episode diagnostic",
        )
    diag = _build_projected_base(
        record,
        reference_as_of_ms=reference_as_of_ms,
        verified_at_ms=verified_at_ms,
        freshness_ttl_ms=freshness_ttl_ms,
        allowed_clock_skew_ms=allowed_clock_skew_ms,
    )
    diag["diagnostic_only"] = True
    diag["not_eligible_for_alert"] = True
    validate_diagnostic_record(diag)
    return diag


class ApprovedJournalRegistry:
    """Read-only registry over approved market-side B2/B4/B5 SQLite journals."""

    def __init__(
        self,
        sources: list[ApprovedJournalSource],
        *,
        freshness_ttl_ms: int = DEFAULT_FRESHNESS_TTL_MS,
        allowed_clock_skew_ms: int = DEFAULT_CLOCK_SKEW_MS,
        clock_ms_fn: Callable[[], int] | None = None,
    ) -> None:
        if not sources:
            raise ContractError("SOURCE_UNAVAILABLE", "At least one approved journal source is required")
        seen_ids: set[str] = set()
        for src in sources:
            if src.source_id in seen_ids:
                raise ContractError("INVALID_ARGUMENT", f"Duplicate source_id: {src.source_id!r}")
            seen_ids.add(src.source_id)
            _assert_not_private_path(src.path)
        self._sources = list(sources)
        self.freshness_ttl_ms = freshness_ttl_ms
        self.allowed_clock_skew_ms = allowed_clock_skew_ms
        self._clock_ms_fn = clock_ms_fn

    def load_all_verified_cards(self) -> tuple[list[VerifiedCardRecord], int | None]:
        """Re-read and cryptographically verify every approved journal on disk."""
        records: list[VerifiedCardRecord] = []
        max_eval_ms = 0
        seen_card_ids: dict[str, str] = {}

        for src in self._sources:
            conn = _open_readonly_sqlite(src.path)
            try:
                _verify_journal_schema(conn)
                events = _verify_and_load_events(conn)

                episodes_by_id: dict[str, dict[str, Any]] = {}
                for row in conn.execute("SELECT id, immutable, payload_sha FROM episodes").fetchall():
                    try:
                        ep_obj = json.loads(row["immutable"])
                    except Exception as exc:
                        raise ContractError("INTEGRITY_FAILURE", "Corrupt episode JSON") from exc
                    if b2_sha256(ep_obj) != row["payload_sha"]:
                        raise ContractError("INTEGRITY_FAILURE", f"Episode digest mismatch for {row['id']}")
                    episodes_by_id[str(row["id"])] = ep_obj

                pub_by_card: dict[str, dict[str, Any]] = {}
                events_by_episode: dict[str, list[dict[str, Any]]] = {}
                reprice_by_episode: dict[str, dict[str, Any]] = {}
                for ev in events:
                    ep_id = ev["episode_id"]
                    if ep_id is not None:
                        events_by_episode.setdefault(ep_id, []).append(ev)
                    if ev["kind"] == "PUBLICATION":
                        if ev["card_id"] in pub_by_card:
                            raise ContractError("INTEGRITY_FAILURE", f"Duplicate PUBLICATION for card {ev['card_id']}")
                        pub_by_card[ev["card_id"]] = ev
                    if ev["kind"] == "REPRICE" and ep_id is not None:
                        reprice_by_episode[ep_id] = ev

                card_rows = conn.execute(
                    "SELECT id, symbol, as_of, episode_id, payload, payload_sha FROM cards ORDER BY as_of ASC, id ASC"
                ).fetchall()
                for row in card_rows:
                    card_id = str(row["id"])
                    try:
                        card = json.loads(row["payload"])
                    except Exception as exc:
                        raise ContractError("INTEGRITY_FAILURE", f"Corrupt card JSON for {card_id}") from exc
                    if b2_sha256(card) != row["payload_sha"] or card.get("card_id") != card_id:
                        raise ContractError("INTEGRITY_FAILURE", f"Card digest/id mismatch for {card_id}")
                    if card.get("symbol") != row["symbol"] or card.get("evaluated_ms") != row["as_of"]:
                        raise ContractError("INTEGRITY_FAILURE", f"Card column/payload mismatch for {card_id}")

                    ep_id = str(row["episode_id"]) if row["episode_id"] is not None else None
                    if card.get("episode_id") != ep_id:
                        raise ContractError("INTEGRITY_FAILURE", f"Card episode_id mismatch for {card_id}")
                    ep_row = episodes_by_id.get(ep_id) if ep_id is not None else None
                    if ep_id is not None and ep_row is None:
                        raise ContractError("INTEGRITY_FAILURE", f"Missing episode row {ep_id} for card {card_id}")

                    pub_ev = pub_by_card.get(card_id)
                    if pub_ev is None:
                        raise ContractError("INTEGRITY_FAILURE", f"Card {card_id} lacks PUBLICATION journal event")

                    evidence_cls = _classify_and_verify_evidence(
                        card,
                        allow_hypothetical_genuine=src.allow_hypothetical_genuine,
                    )

                    _, _, source_pub_sha, _ = _extract_source_refs(card)
                    src_pub_short = source_pub_sha[:16] if isinstance(source_pub_sha, str) and len(source_pub_sha) >= 16 else "NONE"
                    card_version = f"jseq:{pub_ev['seq']}:{pub_ev['sha256'][:16]}:{src_pub_short}"

                    observed_raw = card.get("journal_recorded_wall_ms") or pub_ev["detail"].get("recorded_wall_ms")
                    observed_at_ms = int(observed_raw) if type(observed_raw) is int else None
                    evaluated_ms = int(row["as_of"])
                    max_eval_ms = max(max_eval_ms, evaluated_ms)

                    if card_id in seen_card_ids and seen_card_ids[card_id] != card_version:
                        raise ContractError(
                            "INTEGRITY_FAILURE",
                            f"Card {card_id} has conflicting versions across journals",
                        )
                    seen_card_ids[card_id] = card_version

                    records.append(
                        VerifiedCardRecord(
                            source_id=src.source_id,
                            card_id=card_id,
                            card_version=card_version,
                            episode_id=ep_id,
                            symbol=str(row["symbol"]),
                            evaluated_at_ms=evaluated_ms,
                            observed_at_ms=observed_at_ms,
                            pub_seq=pub_ev["seq"],
                            pub_sha=pub_ev["sha256"],
                            source_evidence_class=evidence_cls,
                            card=card,
                            episode_row=ep_row,
                            events_for_episode=tuple(events_by_episode.get(ep_id, ())) if ep_id else (),
                            latest_reprice_event=reprice_by_episode.get(ep_id) if ep_id else None,
                        )
                    )
            finally:
                conn.close()

        if self._clock_ms_fn is not None:
            default_as_of_ms: int | None = self._clock_ms_fn()
        else:
            default_as_of_ms = max_eval_ms if records and max_eval_ms > 0 else None
        return records, default_as_of_ms

    def resolve_reference_as_of(self, explicit_as_of_ms: int | None, default_as_of_ms: int | None) -> int | None:
        if explicit_as_of_ms is None:
            return default_as_of_ms
        if type(explicit_as_of_ms) is not int or explicit_as_of_ms <= 0:
            raise ContractError("INVALID_ARGUMENT", "as_of_ms must be a positive integer")
        return explicit_as_of_ms

    def latest_records_by_episode(
        self,
        records: list[VerifiedCardRecord],
    ) -> dict[str, VerifiedCardRecord]:
        latest: dict[str, VerifiedCardRecord] = {}
        for rec in sorted(records, key=lambda r: (r.evaluated_at_ms, r.pub_seq, r.card_id)):
            if not rec.episode_id:
                continue
            latest[rec.episode_id] = rec
        return latest

    def project_record(
        self,
        record: VerifiedCardRecord,
        *,
        reference_as_of_ms: int | None,
        verified_at_ms: int,
    ) -> dict[str, Any]:
        return project_signal_snapshot(
            record,
            reference_as_of_ms=reference_as_of_ms,
            verified_at_ms=verified_at_ms,
            freshness_ttl_ms=self.freshness_ttl_ms,
            allowed_clock_skew_ms=self.allowed_clock_skew_ms,
        )

    def project_diagnostic(
        self,
        record: VerifiedCardRecord,
        *,
        reference_as_of_ms: int | None,
        verified_at_ms: int,
    ) -> dict[str, Any]:
        return project_diagnostic_record(
            record,
            reference_as_of_ms=reference_as_of_ms,
            verified_at_ms=verified_at_ms,
            freshness_ttl_ms=self.freshness_ttl_ms,
            allowed_clock_skew_ms=self.allowed_clock_skew_ms,
        )
