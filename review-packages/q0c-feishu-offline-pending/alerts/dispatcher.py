"""Durable single-consumer SQLite outbox; strictly in-memory mock transport."""

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import sqlite3
import time

from .card import make_card
from .contract import PRIORITY, TERMINAL, admit, validate_shape
from .mock import AmbiguousDelivery, MockFeishuTransport, NotDelivered, Response

STATES = ("QUEUED", "ATTEMPTED", "PROVIDER_ACCEPTED", "FAILED", "UNKNOWN_DELIVERY")
ALLOWED = {"QUEUED": {"ATTEMPTED", "FAILED"},
           "FAILED": {"ATTEMPTED", "FAILED"},
           "ATTEMPTED": {"PROVIDER_ACCEPTED", "FAILED", "UNKNOWN_DELIVERY"},
           "PROVIDER_ACCEPTED": set(), "UNKNOWN_DELIVERY": set()}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


@dataclass(frozen=True)
class Policy:
    max_attempts: int = 3
    retry_base_seconds: float = 5
    cooldown_seconds: float = 30
    rate_window_seconds: float = 60
    rate_cap: int = 3
    degraded_cooldown_seconds: float = 300
    max_signal_age: float = 120
    max_source_age: float = 60
    max_quote_age: float = 30
    clock_jump_tolerance: float = 5

    def __post_init__(self):
        for name, value in asdict(self).items():
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError("invalid policy: " + name)
        if type(self.max_attempts) is not int or not 1 <= self.max_attempts <= 10:
            raise ValueError("max_attempts must be 1..10")
        if type(self.rate_cap) is not int or self.rate_cap < 1 or self.rate_window_seconds <= 0:
            raise ValueError("invalid rate policy")


class ClockFault(RuntimeError):
    pass


class Dispatcher:
    """One active dispatcher per DB. Close it before restart/rehydration.

    No background thread, scheduler, webhook URL, network client or live send path.
    A failed/unknown network-like outcome never becomes a human acknowledgement.
    """

    def __init__(self, database, transport, *, clock=time, policy=None, secret=None):
        if type(transport) is not MockFeishuTransport:
            raise ValueError("only exact offline MockFeishuTransport is allowed")
        self.transport, self.clock, self.secret = transport, clock, secret
        self.policy = policy or Policy()
        self.db = sqlite3.connect(database, timeout=5, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS outbox (
                id TEXT PRIMARY KEY, payload TEXT NOT NULL, payload_hash TEXT NOT NULL,
                strategy TEXT NOT NULL, episode TEXT NOT NULL, kind TEXT NOT NULL,
                channel TEXT NOT NULL, version TEXT NOT NULL, priority INTEGER NOT NULL,
                state TEXT NOT NULL CHECK(state IN
                    ('QUEUED','ATTEMPTED','PROVIDER_ACCEPTED','FAILED','UNKNOWN_DELIVERY')),
                attempts INTEGER NOT NULL DEFAULT 0, retryable INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL, eligible_at REAL NOT NULL, expires_at REAL NOT NULL,
                next_attempt_at REAL NOT NULL, accepted_at REAL, last_error TEXT, proof TEXT);
            CREATE TABLE IF NOT EXISTS audit (
                seq INTEGER PRIMARY KEY, outbox_id TEXT NOT NULL REFERENCES outbox(id),
                at REAL NOT NULL, state TEXT NOT NULL, reason TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS audit_state_time ON audit(state, at);
            CREATE INDEX IF NOT EXISTS outbox_due ON outbox(state, next_attempt_at, priority);
            CREATE TABLE IF NOT EXISTS terminal (
                strategy TEXT NOT NULL, episode TEXT NOT NULL, channel TEXT NOT NULL,
                PRIMARY KEY(strategy,episode,channel));
            CREATE TABLE IF NOT EXISTS feedback (
                outbox_id TEXT PRIMARY KEY REFERENCES outbox(id), outcome TEXT NOT NULL,
                received_at REAL NOT NULL, origin TEXT NOT NULL CHECK(origin='SYNTHETIC_TEST'));
            CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit
                BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
            CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit
                BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
        """)
        self._last_wall = self._last_mono = None
        try:
            with self._transaction():
                saved = self._meta("policy")
                if saved is not None and saved != canonical(asdict(self.policy)):
                    raise ValueError("database policy mismatch; do not loosen limits on restart")
                version = self._meta("schema_version")
                if version is not None and version != "1":
                    raise ValueError("unsupported outbox schema")
                self._put_meta("schema_version", "1")
                self._put_meta("policy", canonical(asdict(self.policy)))
            now = self._tick()
            with self._transaction():
                for row in self.db.execute("SELECT id FROM outbox WHERE state='ATTEMPTED'").fetchall():
                    self._transition(row["id"], "UNKNOWN_DELIVERY", now, "restart_inflight_ambiguous")
        except BaseException:
            self.db.close()
            raise

    @contextmanager
    def _transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def _meta(self, key):
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return None if row is None else row[0]

    def _put_meta(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, str(value)))

    def _tick(self):
        wall, mono = self.clock.time(), self.clock.monotonic()
        if not math.isfinite(wall) or not math.isfinite(mono):
            raise ClockFault("nonfinite clock")
        with self._transaction():
            fault = self._meta("clock_fault")
            high = float(self._meta("wall_highwater") or wall)
            if wall < high - self.policy.clock_jump_tolerance:
                fault = "wall_clock_rollback"
            if self._last_wall is not None:
                elapsed = mono - self._last_mono
                if elapsed < 0 or abs((wall - self._last_wall) - elapsed) > self.policy.clock_jump_tolerance:
                    fault = "wall_monotonic_discontinuity"
            if fault:
                self._put_meta("clock_fault", fault)
            self._put_meta("wall_highwater", max(wall, high))
        self._last_wall, self._last_mono = wall, mono
        if fault:
            raise ClockFault("clock quarantined; operator reconciliation required")
        return wall

    def _transition(self, key, state, now, reason, **fields):
        current = self.db.execute("SELECT state FROM outbox WHERE id=?", (key,)).fetchone()[0]
        if state not in ALLOWED[current]:
            raise RuntimeError("illegal outbox transition")
        fields.update(state=state, last_error=reason, retryable=fields.get("retryable", 0))
        self.db.execute("UPDATE outbox SET " + ",".join(name + "=?" for name in fields) + " WHERE id=?",
                        (*fields.values(), key))
        self.db.execute("INSERT INTO audit(outbox_id,at,state,reason) VALUES (?,?,?,?)",
                        (key, now, state, reason))

    def enqueue(self, event):
        now = self._tick()
        validate_shape(event)
        payload = canonical(event)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        identity = [event[k] for k in ("strategy", "episode_id", "event_type", "transition_id", "channel", "contract_version")]
        key = hashlib.sha256(canonical(identity).encode()).hexdigest()
        with self._transaction():
            existing = self.db.execute("SELECT payload_hash FROM outbox WHERE id=?", (key,)).fetchone()
            if existing:
                if existing[0] != digest:
                    raise ValueError("idempotency_payload_conflict")
                return key  # duplicates remain duplicates even after expiry/restart
            admit(event, now, self.policy)
            candidate = (event["strategy"], event["episode_id"], event["channel"])
            if event["event_type"] not in TERMINAL and self.db.execute(
                    "SELECT 1 FROM terminal WHERE strategy=? AND episode=? AND channel=?", candidate).fetchone():
                raise ValueError("episode_already_terminal")
            self.db.execute("""INSERT INTO outbox
                (id,payload,payload_hash,strategy,episode,kind,channel,version,priority,state,
                 created_at,eligible_at,expires_at,next_attempt_at)
                VALUES (?,?,?,?,?,?,?,?,?,'QUEUED',?,?,?,?)""",
                (key, payload, digest, *candidate[:2], event["event_type"], candidate[2],
                 event["contract_version"], PRIORITY[event["event_type"]], now,
                 event["eligible_at"], event["expires_at"], now))
            self.db.execute("INSERT INTO audit(outbox_id,at,state,reason) VALUES (?,?,?,?)",
                            (key, now, "QUEUED", "durable_admission"))
            if event["event_type"] in TERMINAL:
                self.db.execute("INSERT OR IGNORE INTO terminal VALUES (?,?,?)", candidate)
                pending = self.db.execute("""SELECT id FROM outbox WHERE strategy=? AND episode=? AND channel=?
                    AND kind IN ('ENTRY_READY','SETUP_READY','WATCH')
                    AND (state='QUEUED' OR (state='FAILED' AND retryable=1))""", candidate).fetchall()
                for row in pending:
                    self._transition(row[0], "FAILED", now, "superseded_by_terminal_transition")
        return key

    def _rate_due(self, row, now):
        times = [r[0] for r in self.db.execute("""SELECT a.at FROM audit a JOIN outbox o ON o.id=a.outbox_id
            WHERE a.state='ATTEMPTED' AND o.channel=? AND a.at>? ORDER BY a.at DESC""",
            (row["channel"], now - max(self.policy.rate_window_seconds, self.policy.cooldown_seconds)))]
        due = now
        if times:
            due = max(due, times[0] + self.policy.cooldown_seconds)
        window = [t for t in times if t > now - self.policy.rate_window_seconds]
        if len(window) >= self.policy.rate_cap:
            due = max(due, window[self.policy.rate_cap - 1] + self.policy.rate_window_seconds)
        if row["kind"] == "SYSTEM_DEGRADED":
            last = self.db.execute("""SELECT MAX(a.at) FROM audit a JOIN outbox o ON o.id=a.outbox_id
                WHERE a.state='ATTEMPTED' AND o.channel=? AND o.kind='SYSTEM_DEGRADED'""",
                (row["channel"],)).fetchone()[0]
            if last is not None:
                due = max(due, last + self.policy.degraded_cooldown_seconds)
        return due

    def dispatch_one(self):
        """At most one attempt. Return its id, or None. Caller controls invocation."""
        now = self._tick()
        chosen = None
        with self._transaction():
            rows = self.db.execute("""SELECT * FROM outbox WHERE state='QUEUED'
                OR (state='FAILED' AND retryable=1)
                ORDER BY priority,eligible_at,id""").fetchall()
            for row in rows:
                if row["attempts"] >= self.policy.max_attempts or now >= row["expires_at"]:
                    self._transition(row["id"], "FAILED", now, "attempt_limit_or_expiry")
                    continue
                try:
                    event = json.loads(row["payload"])
                    admit(event, now, self.policy)
                except ValueError:
                    self._transition(row["id"], "FAILED", now, "dispatch_admission_expired_or_vetoed")
                    continue
                if now < max(row["next_attempt_at"], self._rate_due(row, now)):
                    continue
                try:
                    card = make_card(event, now, self.secret)
                except Exception:
                    self._transition(row["id"], "FAILED", now, "secret_or_card_validation_failed")
                    continue
                # A protected getter can be slow; use the actual attempt time,
                # not the time before card construction, for TTL and rate accounting.
                now = self.clock.time()
                try:
                    admit(event, now, self.policy)
                except ValueError:
                    self._transition(row["id"], "FAILED", now, "pre_submission_admission_failed")
                    continue
                attempts = row["attempts"] + 1
                self._transition(row["id"], "ATTEMPTED", now, "append_before_mock_send", attempts=attempts)
                chosen = (row, card, attempts)
                break
        if chosen is None:
            return None
        row, card, attempts = chosen  # ATTEMPTED is committed before any submission
        try:
            submit_at = self._tick()
            admit(json.loads(row["payload"]), submit_at, self.policy)
        except (ClockFault, ValueError) as error:
            with self._transaction():
                self._transition(row["id"], "FAILED", self.clock.time(), "pre_submission_gate_failed")
            if isinstance(error, ClockFault):
                raise
            return row["id"]
        proof, retryable, accepted_at = None, False, None
        try:
            response = self.transport.send(card)
            if type(response) is not Response or type(response.status) is not int:
                raise AmbiguousDelivery
            body = response.body
            code = body.get("code") if type(body) is dict else None
            if response.status == 200 and type(code) is int and code == 0:
                body_digest = hashlib.sha256(canonical(body).encode()).hexdigest()
                state, reason = "PROVIDER_ACCEPTED", "mock_provider_code_zero"
                accepted_at = self.clock.time()
                proof = canonical({"origin": "MOCK_PROVIDER", "http_status": 200, "provider_code": 0,
                                   "response_sha256": body_digest,
                                   "observed_at": accepted_at, "human_read": False})
            elif type(code) is int and code != 0 and response.status == 200:
                state, reason = "FAILED", "provider_rejected"
                retryable = response.proven_not_delivered is True
            elif response.proven_not_delivered is True:
                state, reason, retryable = "FAILED", "mock_proven_not_delivered", True
            else:
                state, reason = "UNKNOWN_DELIVERY", "ambiguous_provider_response"
        except NotDelivered:
            state, reason, retryable = "FAILED", "mock_proven_no_submission", True
        except Exception:
            state, reason = "UNKNOWN_DELIVERY", "ambiguous_submission_or_timeout"
            proof, accepted_at = None, None
        # Quarantine the clock BEFORE publishing the result. Retain independent
        # provider evidence, but never timestamp it as a trusted latency sample.
        clock_fault = None
        try:
            finished = self._tick()
        except ClockFault as fault:
            clock_fault = fault
            finished = self.clock.time()
            accepted_at = None
            if proof is not None:
                evidence = json.loads(proof)
                evidence["observation_clock_trusted"] = False
                proof = canonical(evidence)
        next_at = finished + self.policy.retry_base_seconds * (2 ** (attempts - 1))
        retryable = (retryable and clock_fault is None and attempts < self.policy.max_attempts
                     and next_at < row["expires_at"])
        with self._transaction():
            self._transition(row["id"], state, finished, reason, retryable=int(retryable),
                             next_attempt_at=next_at, proof=proof, accepted_at=accepted_at)
        if clock_fault is not None:
            raise clock_fault
        return row["id"]

    def get(self, key):
        row = self.db.execute("SELECT * FROM outbox WHERE id=?", (key,)).fetchone()
        return None if row is None else dict(row)

    def record_feedback(self, key, outcome):
        """Explicit synthetic operator feedback; never inferred from provider acceptance."""
        if outcome not in {"ACKNOWLEDGED", "MISSED", "TOO_LATE", "ACTIONABLE", "NOT_ACTIONABLE"}:
            raise ValueError("invalid feedback outcome")
        now = self._tick()
        with self._transaction():
            row = self.get(key)
            if row is None or row["state"] != "PROVIDER_ACCEPTED":
                raise ValueError("feedback requires provider-accepted event")
            existing = self.db.execute("SELECT outcome FROM feedback WHERE outbox_id=?", (key,)).fetchone()
            if existing:
                if existing[0] != outcome:
                    raise ValueError("feedback conflict")
                return
            self.db.execute("INSERT INTO feedback VALUES (?,?,?,'SYNTHETIC_TEST')", (key, outcome, now))

    def metrics(self):
        counts = {s: 0 for s in STATES}
        counts.update(dict(self.db.execute("SELECT state,COUNT(*) FROM outbox GROUP BY state")))
        attempted = self.db.execute("SELECT COUNT(*) FROM outbox WHERE attempts>0").fetchone()[0]
        feedback = self.db.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
        return {"origin": "SYNTHETIC_TEST_ONLY", "states": counts, "admitted_distinct": sum(counts.values()),
                "attempted_distinct_denominator": attempted,
                "provider_accepted_numerator": counts["PROVIDER_ACCEPTED"],
                "feedback_numerator": feedback, "feedback_denominator": counts["PROVIDER_ACCEPTED"],
                "human_read_inferred": False,
                "attempts_including_retries": self.db.execute("SELECT COALESCE(SUM(attempts),0) FROM outbox").fetchone()[0]}

    def synthetic_latency(self):
        if self._meta("clock_fault"):
            return {"origin": "SYNTHETIC_TEST_ONLY", "future_slo_seconds": 120, "samples": 0,
                    "p95_seconds": None, "reason": "clock_quarantined", "live_claim": False}
        values = sorted(r[0] for r in self.db.execute("""SELECT accepted_at-eligible_at FROM outbox
            WHERE state='PROVIDER_ACCEPTED' AND kind='ENTRY_READY' AND accepted_at>=eligible_at"""))
        return {"origin": "SYNTHETIC_TEST_ONLY", "future_slo_seconds": 120, "samples": len(values),
                "p95_seconds": values[math.ceil(.95 * len(values)) - 1] if values else None,
                "denominator": "provider-accepted ENTRY_READY only; failures/unknowns reported separately",
                "live_claim": False}

    def close(self):
        self.db.close()
