"""Independent, durable Day 1 approval journal. No execution authority lives here."""

from __future__ import annotations

import secrets
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path

from btc_quant_agent.decision.models import AnalysisResultV1, CasePackageV1, TradeProposalV1
from btc_quant_agent.live_db import connection


class LiveState(StrEnum):
    CASE_TRIGGERED = "CASE_TRIGGERED"
    LLM_ANALYZING = "LLM_ANALYZING"
    PLAN_READY = "PLAN_READY"
    NOTIFIED = "NOTIFIED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MANUAL = "MANUAL"
    EXPIRED = "EXPIRED"


_EDGES = {
    LiveState.CASE_TRIGGERED: {LiveState.LLM_ANALYZING, LiveState.MANUAL},
    LiveState.LLM_ANALYZING: {LiveState.PLAN_READY, LiveState.MANUAL},
    LiveState.PLAN_READY: {LiveState.NOTIFIED, LiveState.MANUAL},
    LiveState.NOTIFIED: {LiveState.WAITING_APPROVAL, LiveState.MANUAL},
    LiveState.WAITING_APPROVAL: {LiveState.APPROVED, LiveState.REJECTED, LiveState.MANUAL},
    LiveState.MANUAL: {LiveState.PLAN_READY},
}
_TERMINAL = {LiveState.APPROVED, LiveState.REJECTED, LiveState.EXPIRED}
_ACTIONS = {"APPROVE": LiveState.APPROVED, "REJECT": LiveState.REJECTED,
            "MANUAL": LiveState.MANUAL, "REQUEST_CODEX_REVIEW": LiveState.MANUAL}


class LiveStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS live_cases (
                    case_id TEXT PRIMARY KEY, case_hash TEXT NOT NULL UNIQUE,
                    payload TEXT NOT NULL, state TEXT NOT NULL,
                    active_proposal_hash TEXT, created_at_ms INTEGER NOT NULL,
                    source TEXT NOT NULL, evidence_id TEXT NOT NULL,
                    signal_identity TEXT NOT NULL, trigger TEXT NOT NULL,
                    strategy_version TEXT NOT NULL,
                    UNIQUE(source, evidence_id, signal_identity, trigger, strategy_version)
                );
                CREATE TABLE IF NOT EXISTS analysis_results (
                    result_hash TEXT NOT NULL, case_id TEXT NOT NULL,
                    role TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(case_id, role, result_hash),
                    FOREIGN KEY(case_id) REFERENCES live_cases(case_id)
                );
                CREATE INDEX IF NOT EXISTS analysis_case_role ON analysis_results(case_id, role);
                CREATE TABLE IF NOT EXISTS trade_proposals (
                    proposal_hash TEXT PRIMARY KEY, proposal_id TEXT NOT NULL UNIQUE,
                    case_id TEXT NOT NULL, case_hash TEXT NOT NULL, payload TEXT NOT NULL,
                    FOREIGN KEY(case_id) REFERENCES live_cases(case_id)
                );
                CREATE TABLE IF NOT EXISTS approval_records (
                    event_id TEXT PRIMARY KEY, action TEXT NOT NULL, actor TEXT NOT NULL,
                    proposal_hash TEXT NOT NULL, case_hash TEXT NOT NULL,
                    at_ms INTEGER NOT NULL, result_state TEXT NOT NULL,
                    review_processed INTEGER NOT NULL DEFAULT 0,
                    review_claim_until_ms INTEGER NOT NULL DEFAULT 0,
                    review_claim_token TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(proposal_hash) REFERENCES trade_proposals(proposal_hash)
                );
                CREATE TABLE IF NOT EXISTS live_state_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL,
                    from_state TEXT, to_state TEXT NOT NULL, at_ms INTEGER NOT NULL,
                    callback_event_id TEXT UNIQUE,
                    FOREIGN KEY(case_id) REFERENCES live_cases(case_id),
                    FOREIGN KEY(callback_event_id) REFERENCES approval_records(event_id)
                );
            """)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(approval_records)")}
            if "review_processed" not in columns:
                db.execute("ALTER TABLE approval_records ADD COLUMN review_processed INTEGER NOT NULL DEFAULT 0")
            if "review_claim_until_ms" not in columns:
                db.execute("ALTER TABLE approval_records ADD COLUMN review_claim_until_ms INTEGER NOT NULL DEFAULT 0")
            if "review_claim_token" not in columns:
                db.execute("ALTER TABLE approval_records ADD COLUMN review_claim_token TEXT NOT NULL DEFAULT ''")

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        with connection(self.path) as db:
            yield db

    def save_case(self, case: CasePackageV1) -> bool:
        case.verify()
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT case_hash FROM live_cases WHERE case_id=?", (case.case_id,)).fetchone()
            if row:
                if row["case_hash"] != case.case_hash:
                    raise ValueError("case identity collision")
                return False
            try:
                db.execute("INSERT INTO live_cases "
                           "(case_id, case_hash, payload, state, created_at_ms, source, evidence_id, "
                           "signal_identity, trigger, strategy_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (case.case_id, case.case_hash, case.canonical_json(),
                            LiveState.CASE_TRIGGERED, case.created_at_ms, case.source,
                            case.evidence_id, case.signal_identity, case.trigger, case.strategy_version))
            except sqlite3.IntegrityError:
                raise ValueError("case natural identity collision") from None
            db.execute("INSERT INTO live_state_events(case_id, from_state, to_state, at_ms) VALUES (?, NULL, ?, ?)",
                       (case.case_id, LiveState.CASE_TRIGGERED, case.created_at_ms))
            return True

    def get_case(self, case_id: str) -> CasePackageV1:
        with self._connection() as db:
            row = db.execute("SELECT payload FROM live_cases WHERE case_id=?", (case_id,)).fetchone()
            if row is None:
                raise KeyError(case_id)
            return CasePackageV1.model_validate_json(row["payload"])

    def save_analysis(self, result: AnalysisResultV1, role: str = "PRIMARY") -> None:
        if role not in {"PRIMARY", "SECONDARY", "FUSED"}:
            raise ValueError("invalid analysis role")
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM live_cases WHERE case_id=?", (result.case_id,)).fetchone()
            if row is None:
                raise ValueError("unknown case")
            result.verify_case(CasePackageV1.model_validate_json(row["payload"]))
            db.execute("INSERT OR IGNORE INTO analysis_results VALUES (?, ?, ?, ?)",
                       (result.result_hash, result.case_id, role, result.canonical_json()))
            existing = db.execute("SELECT payload FROM analysis_results "
                                  "WHERE case_id=? AND role=? AND result_hash=?",
                                  (result.case_id, role, result.result_hash)).fetchone()
            if existing["payload"] != result.canonical_json():
                raise ValueError("analysis identity collision")

    def get_analysis(self, case_id: str, role: str = "PRIMARY") -> AnalysisResultV1 | None:
        with self._connection() as db:
            row = db.execute("SELECT payload FROM analysis_results WHERE case_id=? AND role=? ORDER BY rowid DESC LIMIT 1",
                             (case_id, role)).fetchone()
            return AnalysisResultV1.model_validate_json(row["payload"]) if row else None

    def save_proposal(self, proposal: TradeProposalV1, *, review_claim_token: str | None = None,
                      now_ms: int | None = None) -> None:
        proposal.verify()
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if review_claim_token is not None:
                if now_ms is None:
                    raise ValueError("review claim time required")
                self._require_review_claim(db, proposal.case_id, review_claim_token, now_ms)
            case = db.execute("SELECT case_hash, state FROM live_cases WHERE case_id=?",
                              (proposal.case_id,)).fetchone()
            if not case or case["case_hash"] != proposal.case_hash:
                raise ValueError("proposal case identity mismatch")
            if LiveState(case["state"]) in _TERMINAL:
                raise ValueError("terminal case")
            if not proposal.analysis_result_hashes:
                raise ValueError("missing analysis hashes")
            for result_hash in proposal.analysis_result_hashes:
                row = db.execute("SELECT 1 FROM analysis_results WHERE case_id=? AND result_hash=?",
                                 (proposal.case_id, result_hash)).fetchone()
                if not row:
                    raise ValueError("unknown analysis hash")
            row = db.execute("SELECT proposal_hash, payload FROM trade_proposals WHERE proposal_id=?",
                             (proposal.proposal_id,)).fetchone()
            if row and (row["proposal_hash"] != proposal.proposal_hash or
                        row["payload"] != proposal.canonical_json()):
                raise ValueError("proposal identity collision")
            if row is None:
                db.execute("INSERT INTO trade_proposals VALUES (?, ?, ?, ?, ?)",
                           (proposal.proposal_hash, proposal.proposal_id, proposal.case_id,
                            proposal.case_hash, proposal.canonical_json()))
            db.execute("UPDATE live_cases SET active_proposal_hash=? WHERE case_id=?",
                       (proposal.proposal_hash, proposal.case_id))

    def get_proposal(self, proposal_hash: str) -> TradeProposalV1:
        with self._connection() as db:
            row = db.execute("SELECT payload FROM trade_proposals WHERE proposal_hash=?",
                             (proposal_hash,)).fetchone()
            if row is None:
                raise KeyError(proposal_hash)
            return TradeProposalV1.model_validate_json(row["payload"])

    def active_proposal(self, case_id: str) -> TradeProposalV1 | None:
        with self._connection() as db:
            row = db.execute("SELECT p.payload FROM live_cases c JOIN trade_proposals p "
                             "ON c.active_proposal_hash=p.proposal_hash WHERE c.case_id=?",
                             (case_id,)).fetchone()
            return TradeProposalV1.model_validate_json(row["payload"]) if row else None

    def state(self, case_id: str) -> LiveState:
        with self._connection() as db:
            row = db.execute("SELECT state FROM live_cases WHERE case_id=?", (case_id,)).fetchone()
            if row is None:
                raise KeyError(case_id)
            return LiveState(row["state"])

    def expire_cases(self, now_ms: int) -> None:
        """Recover abandoned work at its immutable TTL, without reissuing analysis."""
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT c.case_id, c.state, c.payload, p.payload AS proposal_payload "
                "FROM live_cases c LEFT JOIN trade_proposals p "
                "ON p.proposal_hash=c.active_proposal_hash "
                "WHERE c.state NOT IN ('APPROVED','REJECTED','EXPIRED')",
            ).fetchall()
            for row in rows:
                case = CasePackageV1.model_validate_json(row["payload"])
                deadline = case.expires_at_ms
                state = LiveState(row["state"])
                if state == LiveState.WAITING_APPROVAL and row["proposal_payload"]:
                    proposal = TradeProposalV1.model_validate_json(row["proposal_payload"])
                    deadline = min(deadline, proposal.expires_at_ms)
                if now_ms >= deadline:
                    self._transition(db, case.case_id, state, LiveState.EXPIRED, now_ms)
                    db.execute(
                        "UPDATE approval_records SET review_processed=1, review_claim_until_ms=0, "
                        "review_claim_token='' WHERE proposal_hash IN "
                        "(SELECT proposal_hash FROM trade_proposals WHERE case_id=?) "
                        "AND action='REQUEST_CODEX_REVIEW'", (case.case_id,),
                    )

    @staticmethod
    def _transition(db: sqlite3.Connection, case_id: str, old: LiveState, new: LiveState,
                    now_ms: int, callback_event_id: str | None = None) -> None:
        if new not in _EDGES.get(old, set()) and not (new == LiveState.EXPIRED and old not in _TERMINAL):
            raise ValueError("invalid state transition")
        db.execute("UPDATE live_cases SET state=? WHERE case_id=?", (new, case_id))
        db.execute("INSERT INTO live_state_events(case_id, from_state, to_state, at_ms, callback_event_id) "
                   "VALUES (?, ?, ?, ?, ?)", (case_id, old, new, now_ms, callback_event_id))

    @staticmethod
    def _require_review_claim(db: sqlite3.Connection, case_id: str, token: str, now_ms: int) -> None:
        if not token:
            raise ValueError("review claim required")
        row = db.execute("SELECT 1 FROM approval_records a JOIN trade_proposals p "
                         "ON p.proposal_hash=a.proposal_hash WHERE p.case_id=? "
                         "AND a.action='REQUEST_CODEX_REVIEW' AND a.review_processed=0 "
                         "AND a.review_claim_token=? AND a.review_claim_until_ms>? LIMIT 1",
                         (case_id, token, now_ms)).fetchone()
        if row is None:
            raise ValueError("stale review claim")

    def transition(self, case_id: str, state: LiveState | str, now_ms: int, *,
                   review_claim_token: str | None = None) -> None:
        new = LiveState(state)
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if review_claim_token is not None:
                self._require_review_claim(db, case_id, review_claim_token, now_ms)
            row = db.execute("SELECT state FROM live_cases WHERE case_id=?", (case_id,)).fetchone()
            if row is None:
                raise KeyError(case_id)
            self._transition(db, case_id, LiveState(row["state"]), new, now_ms)

    def record_callback(self, event_id: str, action: str, actor: str, proposal_hash: str,
                        case_hash: str, now_ms: int) -> dict[str, str | bool]:
        if not event_id or not actor or action not in _ACTIONS:
            raise ValueError("invalid callback")
        expired = False
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            replay = db.execute("SELECT * FROM approval_records WHERE event_id=?", (event_id,)).fetchone()
            if replay:
                if (replay["action"], replay["actor"], replay["proposal_hash"], replay["case_hash"]) != (
                        action, actor, proposal_hash, case_hash):
                    raise ValueError("callback event collision")
                return {"state": replay["result_state"], "replay": True}
            row = db.execute("SELECT c.case_id, c.case_hash, c.active_proposal_hash, c.state, c.payload AS case_payload, "
                             "p.payload AS proposal_payload FROM trade_proposals p JOIN live_cases c "
                             "ON p.case_id=c.case_id WHERE p.proposal_hash=?", (proposal_hash,)).fetchone()
            if not row or row["case_hash"] != case_hash or row["active_proposal_hash"] != proposal_hash:
                raise ValueError("stale or mismatched callback identity")
            proposal = TradeProposalV1.model_validate_json(row["proposal_payload"])
            case = CasePackageV1.model_validate_json(row["case_payload"])
            old = LiveState(row["state"])
            if now_ms >= min(case.expires_at_ms, proposal.expires_at_ms):
                if old not in _TERMINAL:
                    self._transition(db, case.case_id, old, LiveState.EXPIRED, now_ms)
                expired = True
            elif old != LiveState.WAITING_APPROVAL:
                raise ValueError("callback not awaiting approval")
            elif action == "APPROVE" and (proposal.requires_manual_review or proposal.blocked_reasons
                                          or proposal.recommended_notional_usdt <= 0):
                raise ValueError("proposal cannot be approved")
            else:
                new = _ACTIONS[action]
                db.execute("INSERT INTO approval_records(event_id, action, actor, proposal_hash, case_hash, at_ms, result_state) "
                           "VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (event_id, action, actor, proposal_hash, case_hash, now_ms, new))
                self._transition(db, case.case_id, old, new, now_ms, event_id)
        if expired:
            raise ValueError("proposal expired")
        return {"state": new, "replay": False}

    def queued_codex_reviews(self, now_ms: int | None = None) -> list[str]:
        current_ms = int(time.time() * 1000) if now_ms is None else now_ms
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE approval_records SET review_processed=1, review_claim_until_ms=0, "
                       "review_claim_token='' WHERE event_id IN ("
                       "SELECT a.event_id FROM approval_records a JOIN trade_proposals p "
                       "ON p.proposal_hash=a.proposal_hash JOIN live_cases c ON c.case_id=p.case_id "
                       "WHERE a.action='REQUEST_CODEX_REVIEW' AND a.review_processed=0 "
                       "AND c.active_proposal_hash != a.proposal_hash AND ("
                       "c.state IN ('WAITING_APPROVAL','APPROVED','REJECTED') OR ("
                       "c.state='MANUAL' AND EXISTS (SELECT 1 FROM approval_records newer "
                       "WHERE newer.proposal_hash=c.active_proposal_hash "
                       "AND newer.action='REQUEST_CODEX_REVIEW' AND newer.review_processed=0 "
                       "AND newer.rowid>a.rowid))))")
            interrupted = db.execute(
                "SELECT DISTINCT c.case_id, c.state FROM live_cases c JOIN trade_proposals p "
                "ON p.case_id=c.case_id JOIN approval_records a ON a.proposal_hash=p.proposal_hash "
                "WHERE a.action='REQUEST_CODEX_REVIEW' AND a.review_processed=0 "
                "AND a.review_claim_until_ms<=? AND c.state IN ('PLAN_READY','NOTIFIED') "
                "AND NOT EXISTS (SELECT 1 FROM approval_records busy JOIN trade_proposals bp "
                "ON bp.proposal_hash=busy.proposal_hash WHERE bp.case_id=c.case_id "
                "AND busy.action='REQUEST_CODEX_REVIEW' AND busy.review_processed=0 "
                "AND busy.review_claim_until_ms>?)",
                (current_ms, current_ms),
            ).fetchall()
            for row in interrupted:
                self._transition(db, row["case_id"], LiveState(row["state"]), LiveState.MANUAL, current_ms)
            rows = db.execute("SELECT DISTINCT c.case_id FROM live_cases c JOIN trade_proposals p "
                              "ON p.case_id=c.case_id JOIN approval_records a "
                              "ON a.proposal_hash=p.proposal_hash WHERE c.state='MANUAL' "
                              "AND a.action='REQUEST_CODEX_REVIEW' AND a.review_processed=0 "
                              "AND a.review_claim_until_ms<=? "
                              "AND NOT EXISTS (SELECT 1 FROM approval_records busy "
                              "JOIN trade_proposals bp ON bp.proposal_hash=busy.proposal_hash "
                              "WHERE bp.case_id=c.case_id AND busy.action='REQUEST_CODEX_REVIEW' "
                              "AND busy.review_processed=0 AND busy.review_claim_until_ms>?) "
                              "ORDER BY c.case_id", (current_ms, current_ms)).fetchall()
            return [row["case_id"] for row in rows]

    def claim_codex_review(self, case_id: str, now_ms: int, lease_ms: int) -> str | None:
        if lease_ms <= 0:
            raise ValueError("review lease must be positive")
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM live_cases WHERE case_id=?", (case_id,)).fetchone()
            if row is None or row["state"] != LiveState.MANUAL:
                return None
            busy = db.execute("SELECT 1 FROM approval_records a JOIN trade_proposals p "
                              "ON p.proposal_hash=a.proposal_hash WHERE p.case_id=? "
                              "AND a.action='REQUEST_CODEX_REVIEW' AND a.review_processed=0 "
                              "AND a.review_claim_until_ms>? LIMIT 1", (case_id, now_ms)).fetchone()
            if busy:
                return None
            pending = db.execute("SELECT a.event_id FROM approval_records a JOIN trade_proposals p "
                                 "ON p.proposal_hash=a.proposal_hash WHERE p.case_id=? "
                                 "AND a.action='REQUEST_CODEX_REVIEW' AND a.review_processed=0 "
                                 "AND a.review_claim_until_ms<=? ORDER BY a.at_ms, a.event_id LIMIT 1",
                                 (case_id, now_ms)).fetchone()
            if pending is None:
                return None
            token = secrets.token_hex(16)
            changed = db.execute("UPDATE approval_records SET review_claim_until_ms=?, review_claim_token=? "
                                 "WHERE event_id=? AND review_processed=0 AND review_claim_until_ms<=?",
                                 (now_ms + lease_ms, token, pending["event_id"], now_ms))
            return token if changed.rowcount == 1 else None

    def renew_codex_review(self, case_id: str, token: str, now_ms: int, lease_ms: int) -> bool:
        if not token or lease_ms <= 0:
            raise ValueError("invalid review lease")
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute("UPDATE approval_records SET review_claim_until_ms=? WHERE event_id IN ("
                                 "SELECT a.event_id FROM approval_records a JOIN trade_proposals p "
                                 "ON p.proposal_hash=a.proposal_hash WHERE p.case_id=? "
                                 "AND a.action='REQUEST_CODEX_REVIEW' AND a.review_processed=0 "
                                 "AND a.review_claim_token=? AND a.review_claim_until_ms>?)",
                                 (now_ms + lease_ms, case_id, token, now_ms))
            return changed.rowcount == 1

    def release_codex_review(self, case_id: str, token: str) -> None:
        if not token:
            raise ValueError("review claim required")
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE approval_records SET review_claim_until_ms=0, review_claim_token='' "
                       "WHERE event_id IN ("
                       "SELECT a.event_id FROM approval_records a JOIN trade_proposals p "
                       "ON p.proposal_hash=a.proposal_hash WHERE p.case_id=? "
                       "AND a.action='REQUEST_CODEX_REVIEW' AND a.review_processed=0 "
                       "AND a.review_claim_token=?)", (case_id, token))

    def mark_codex_review_processed(self, case_id: str, token: str) -> None:
        if not token:
            raise ValueError("review claim required")
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE approval_records SET review_processed=1, review_claim_until_ms=0, "
                       "review_claim_token='' WHERE event_id IN ("
                                "SELECT a.event_id FROM approval_records a JOIN trade_proposals p "
                                "ON p.proposal_hash=a.proposal_hash JOIN live_cases c ON c.case_id=p.case_id "
                                "WHERE c.case_id=? "
                                "AND a.action='REQUEST_CODEX_REVIEW' AND a.review_processed=0 "
                                "AND a.review_claim_token=?)", (case_id, token))
