"""LT-A append-only store extension; L23 immutable anchors and monotone CAS lifecycle."""
from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .core import fingerprint
from .rc_models import BShadowState, RCDecision
from .rc_source import Receipt, canonical
from .rc_strategy import decide_s1
from .swing import decide
from .swing_store import DecisionStore

TERMINAL = frozenset({"NO_CHASE", "MISSED_ENTRY", "INVALIDATED", "EXPIRED", "CANCELED", "NO_FILL", "TIME_STOP"})
ALLOWED = {"WATCH": {"WATCH", "ARMED", *TERMINAL}, "ARMED": {"ARMED", *TERMINAL}}
B_SHADOW_STATES = frozenset(BShadowState.model_fields["status"].annotation.__args__)
B_SHADOW_TERMINAL = frozenset({"CANCELED", "INVALIDATED", "EXPIRED", "NO_CHASE",
                               "MISSED_ENTRY", "NO_FILL", "TIME_STOP"})


class InjectedCrash(RuntimeError):
    pass


def fault(requested, boundary):
    if requested == "kill_" + boundary:
        os._exit(73)  # Used only by the bounded subprocess crash test.
    if requested == boundary:
        raise InjectedCrash(boundary)


class RCStore(DecisionStore):
    def __init__(self, path, *, readonly=False):
        self.readonly = readonly
        self.path = Path(path)
        if any(p.is_symlink() for p in (self.path, *self.path.parents)):
            raise ValueError("UNTRUSTED_STORE_PATH")
        if readonly:
            if not self.path.is_file():
                raise ValueError("READ_ONLY_STORE_MISSING")
            return
        super().__init__(path)
        with self.connect() as db:
            db.executescript("""
              CREATE TABLE IF NOT EXISTS rc_receipts(
                sequence INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL, symbol TEXT NOT NULL,
                interval TEXT NOT NULL, open_ms INTEGER NOT NULL, revision INTEGER NOT NULL,
                available_ms INTEGER NOT NULL, digest TEXT NOT NULL, value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS rc_decisions(
                sequence INTEGER PRIMARY KEY, symbol TEXT NOT NULL, trigger_ms INTEGER NOT NULL,
                decision_ms INTEGER NOT NULL, digest TEXT NOT NULL, value TEXT NOT NULL,
                UNIQUE(symbol,trigger_ms));
              CREATE TABLE IF NOT EXISTS rc_watermarks(
                symbol TEXT NOT NULL, trigger_ms INTEGER NOT NULL, prefix_digest TEXT NOT NULL,
                decision_digest TEXT NOT NULL, PRIMARY KEY(symbol,trigger_ms));
              CREATE TABLE IF NOT EXISTS rc_episodes(
                id TEXT PRIMARY KEY, digest TEXT NOT NULL, anchors TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS rc_transitions(
                id TEXT NOT NULL, revision INTEGER NOT NULL, now_ms INTEGER NOT NULL,
                digest TEXT NOT NULL, previous_digest TEXT NOT NULL, value TEXT NOT NULL,
                PRIMARY KEY(id,revision));
              CREATE TABLE IF NOT EXISTS rc_observations(
                id TEXT PRIMARY KEY, episode_id TEXT NOT NULL, digest TEXT NOT NULL, value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS rc_stops(
                sequence INTEGER PRIMARY KEY, reason TEXT UNIQUE NOT NULL);
              CREATE TABLE IF NOT EXISTS b_shadow_states(
                state_id TEXT NOT NULL, revision INTEGER NOT NULL, digest TEXT NOT NULL,
                previous_digest TEXT NOT NULL, value TEXT NOT NULL,
                PRIMARY KEY(state_id,revision));
              CREATE TABLE IF NOT EXISTS b_schema_migrations(
                version TEXT PRIMARY KEY);
            """)
            self._migrate_b_shadow_states(db)

    def _migrate_b_shadow_states(self, db):
        migration = "V070_B_SHADOW_STATE_V1_FROM_RC_V1"
        if not db.execute("SELECT 1 FROM b_schema_migrations WHERE version=?", (migration,)).fetchone():
            rows = db.execute("SELECT value FROM rc_decisions ORDER BY sequence").fetchall()
            for (encoded,) in rows:
                decision = RCDecision.model_validate_json(encoded)
                identity = decision.episode_id or fingerprint(["V070_B_SHADOW_STATE_V1",
                                                                decision.symbol, decision.trigger_close_ms])
                if db.execute("SELECT 1 FROM b_shadow_states WHERE state_id=?", (identity,)).fetchone():
                    continue
                status, at_ms = decision.market_state, decision.decision_ms
                reason = "MIGRATED_FROM_IMMUTABLE_RC_V1_DECISION"
                if decision.episode_id:
                    episode = self.episode(decision.episode_id)
                    if episode["anchors"]["decision"] != decision.model_dump(mode="json"):
                        raise ValueError("B_MIGRATION_EPISODE_DECISION_BINDING_INVALID")
                    status = episode["state"]["status"]
                    at_ms = episode["updated_ms"]
                    reason += ";LATEST_V1_LIFECYCLE=" + status
                if status not in B_SHADOW_STATES:
                    status = "UNKNOWN"
                self._append_b_state(db, decision, status, at_ms, reason, "SYNTHETIC")
            db.execute("INSERT INTO b_schema_migrations VALUES (?)", (migration,))

        # Repair the earlier B migration's terminal-state projection append-only.
        correction = "V070_B_SHADOW_STATE_V1_RECONCILE_LATEST_RC_LIFECYCLE"
        if not db.execute("SELECT 1 FROM b_schema_migrations WHERE version=?", (correction,)).fetchone():
            for (encoded,) in db.execute("SELECT value FROM rc_decisions ORDER BY sequence").fetchall():
                decision = RCDecision.model_validate_json(encoded)
                if not decision.episode_id:
                    continue
                episode = self.episode(decision.episode_id)
                if episode["anchors"]["decision"] != decision.model_dump(mode="json"):
                    raise ValueError("B_MIGRATION_EPISODE_DECISION_BINDING_INVALID")
                b_row = db.execute("SELECT value FROM b_shadow_states WHERE state_id=? ORDER BY revision DESC LIMIT 1",
                                   (decision.episode_id,)).fetchone()
                if b_row is None:
                    raise ValueError("B_MIGRATION_STATE_MISSING")
                b_status = json.loads(b_row[0])["status"]
                v1_status = episode["state"]["status"]
                if v1_status in TERMINAL and b_status != v1_status:
                    self._append_b_state(db, decision, v1_status, episode["updated_ms"],
                                         "MIGRATED_LATEST_V1_TERMINAL_CORRECTION", "SYNTHETIC")
            db.execute("INSERT INTO b_schema_migrations VALUES (?)", (correction,))

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            db.execute("PRAGMA query_only=ON")
            yield db
        finally:
            db.close()

    @contextmanager
    def connect(self):
        if self.readonly:
            raise ValueError("READ_ONLY_STORE_MUTATION_FORBIDDEN")
        with super().connect() as db:
            db.execute("PRAGMA busy_timeout=1000")
            page_size = db.execute("PRAGMA page_size").fetchone()[0]
            maximum_pages = 67108864 // page_size
            actual_limit = db.execute(f"PRAGMA max_page_count={maximum_pages}").fetchone()[0]
            if actual_limit > maximum_pages:
                raise ValueError("DATABASE_ALREADY_EXCEEDS_FROZEN_STORAGE_BUDGET")
            yield db

    def stop(self, reason):
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO rc_stops(reason) VALUES (?)", (reason,))
        self.reconcile()

    def _append_b_state(self, db, decision, status, at_ms, reason, source_status=None):
        digest = fingerprint(decision.model_dump(mode="json"))
        identity = decision.episode_id or fingerprint(["V070_B_SHADOW_STATE_V1",
                                                        decision.symbol, decision.trigger_close_ms])
        row = db.execute("SELECT revision,digest FROM b_shadow_states WHERE state_id=? ORDER BY revision DESC LIMIT 1",
                         (identity,)).fetchone()
        revision, previous = (0, "") if row is None else (row[0] + 1, row[1])
        if row is not None:
            old_value = json.loads(db.execute(
                "SELECT value FROM b_shadow_states WHERE state_id=? AND revision=?",
                (identity, row[0])).fetchone()[0])
            old_status = old_value["status"]
            if at_ms < old_value["at_ms"]:
                raise ValueError("B_SHADOW_STATE_TIME_REGRESSION")
            allowed = ({old_status} if old_status in B_SHADOW_TERMINAL else
                       {old_status, "SOURCE_BLOCKED", "UNKNOWN", *B_SHADOW_TERMINAL})
            if old_status in {"WATCH", "ARMED"}:
                allowed.add("ARMED")
                allowed.add("WATCH")
            if status not in allowed:
                raise ValueError("B_SHADOW_STATE_TRANSITION_INVALID")
        envelope = BShadowState(state_id=identity, episode_id=decision.episode_id,
                                decision_digest=digest, revision=revision, status=status,
                                source_status=source_status or decision.exposure,
                                reason=reason, at_ms=at_ms).model_dump(mode="json")
        value = canonical(envelope)
        state_digest = fingerprint(envelope)
        db.execute("INSERT INTO b_shadow_states VALUES (?,?,?,?,?)",
                   (identity, revision, state_digest, previous, value))
        return state_digest

    def b_states(self, state_id=None):
        with self.read() as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='b_shadow_states'").fetchone():
                if self.decisions():
                    raise ValueError("B_SHADOW_STATE_MIGRATION_REQUIRED")
                return []
            if state_id is None:
                rows = db.execute("SELECT state_id,revision,digest,previous_digest,value FROM b_shadow_states ORDER BY state_id,revision").fetchall()
            else:
                rows = db.execute("SELECT state_id,revision,digest,previous_digest,value FROM b_shadow_states WHERE state_id=? ORDER BY revision",
                                  (state_id,)).fetchall()
        result, last, last_revision, prior_values = [], {}, {}, {}
        decisions = self.decisions()
        indexed = {d.episode_id or fingerprint(["V070_B_SHADOW_STATE_V1", d.symbol, d.trigger_close_ms]): d
                   for d in decisions}
        for identity, revision, digest, previous, encoded in rows:
            value = BShadowState.model_validate_json(encoded).model_dump(mode="json")
            prior = last.get(identity, "")
            decision = indexed.get(identity)
            if (revision != last_revision.get(identity, -1) + 1
                    or previous != prior or fingerprint(value) != digest
                    or value["state_id"] != identity or value["revision"] != revision
                    or decision is None
                    or value["decision_digest"] != fingerprint(decision.model_dump(mode="json"))
                    or value["episode_id"] != decision.episode_id
                    or value["source_status"] != decision.exposure
                    or value["at_ms"] < decision.decision_ms):
                raise ValueError("B_SHADOW_STATE_CHAIN_INVALID")
            prior_value = prior_values.get(identity)
            if prior_value:
                old_status = prior_value["status"]
                allowed = ({old_status} if old_status in B_SHADOW_TERMINAL else
                           {old_status, "SOURCE_BLOCKED", "UNKNOWN", *B_SHADOW_TERMINAL})
                if old_status in {"WATCH", "ARMED"}:
                    allowed.update({"WATCH", "ARMED"})
                if value["status"] not in allowed or value["at_ms"] < prior_value["at_ms"]:
                    raise ValueError("B_SHADOW_STATE_TRANSITION_OR_CLOCK_INVALID")
            elif value["reason"].startswith("MIGRATED_FROM_IMMUTABLE_RC_V1_DECISION"):
                if ";LATEST_V1_LIFECYCLE=" in value["reason"]:
                    expected_status = value["reason"].split(";LATEST_V1_LIFECYCLE=", 1)[1]
                else:
                    expected_status = decision.market_state
                if value["status"] != (expected_status if expected_status in B_SHADOW_STATES else "UNKNOWN"):
                    raise ValueError("B_SHADOW_STATE_MIGRATION_STATUS_MISMATCH")
            elif value["status"] != (decision.market_state if decision.market_state in B_SHADOW_STATES else "UNKNOWN"):
                raise ValueError("B_SHADOW_STATE_INITIAL_STATUS_MISMATCH")
            last[identity] = digest
            last_revision[identity] = revision
            prior_values[identity] = value
            result.append(value | {"state_digest": digest, "previous_digest": previous})
        if state_id is None and set(indexed) - set(last):
            raise ValueError("B_SHADOW_STATE_DECISION_MISSING")
        if state_id is None:
            for identity, decision in indexed.items():
                if not decision.episode_id:
                    continue
                episode = self.episode(decision.episode_id)
                b_status = prior_values[identity]["status"]
                v1_status = episode["state"]["status"]
                if v1_status in TERMINAL and b_status != v1_status:
                    raise ValueError("B_SHADOW_STATE_V1_TERMINAL_MISMATCH")
        return result

    def note_source_blocked(self, symbol, trigger_ms, *, at_ms, reason="SOURCE_BLOCKED"):
        return self.note_b_state(symbol, trigger_ms, "SOURCE_BLOCKED", at_ms=at_ms, reason=reason)

    def note_b_state(self, symbol, trigger_ms, status, *, at_ms, reason):
        if status not in B_SHADOW_STATES:
            raise ValueError("B_SHADOW_STATE_INVALID")
        decision = next((d for d in self.decisions()
                         if d.symbol == symbol and d.trigger_close_ms == trigger_ms), None)
        if decision is None:
            raise ValueError("B_SHADOW_STATE_REQUIRES_PERSISTED_DECISION")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            return self._append_b_state(db, decision, status, at_ms, reason)

    def stopped(self):
        with self.read() as db:
            return tuple(r[0] for r in db.execute("SELECT reason FROM rc_stops ORDER BY sequence"))

    def admit(self, receipts, *, crash=None):
        if len(receipts) > 4096:
            self.stop("BACKFILL_BATCH_LIMIT_EXCEEDED")
            raise ValueError("BACKFILL_BATCH_LIMIT_EXCEEDED")
        if self.stopped():
            raise ValueError("STICKY_SOURCE_STOP")
        # Conservative reservation includes SQLite index/page overhead. No pruning for space.
        required = sum(len(r.model_dump_json().encode()) + 4096 for r in receipts)
        if self.path.stat().st_size + required > 67108864:
            self.stop("STORAGE_BUDGET_EXCEEDED")
            raise ValueError("STORAGE_BUDGET_EXCEEDED")
        admitted = 0
        try:
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                for item in receipts:
                    r = Receipt.model_validate_json(item.model_dump_json())
                    digest, b = fingerprint(r.model_dump(mode="json")), r.bar
                    existing = db.execute("SELECT digest FROM rc_receipts WHERE id=?", (r.identity,)).fetchone()
                    if existing:
                        if existing[0] != digest:
                            raise ValueError("IMMUTABLE_RECEIPT_CONFLICT")
                        continue
                    key = (b.candle.symbol, b.candle.interval)
                    latest = db.execute("SELECT MAX(open_ms) FROM rc_receipts WHERE symbol=? AND interval=?",
                                        key).fetchone()[0]
                    if b.revision:
                        prior = db.execute("SELECT MAX(revision) FROM rc_receipts WHERE symbol=? AND interval=? AND open_ms=?",
                                           (*key, b.candle.open_time_ms)).fetchone()[0]
                        if prior is None or b.revision != prior + 1:
                            raise ValueError("REVISION_SEQUENCE_INVALID")
                    elif latest is not None and b.candle.open_time_ms <= latest:
                        raise ValueError("OUT_OF_ORDER_SOURCE_ADMISSION")
                    db.execute("INSERT INTO rc_receipts(id,symbol,interval,open_ms,revision,available_ms,digest,value) VALUES (?,?,?,?,?,?,?,?)",
                               (r.identity, *key, b.candle.open_time_ms, b.revision, b.available_ms,
                                digest, canonical(r.model_dump(mode="json"))))
                    admitted += 1
                fault(crash, "before_receipt_commit")
            fault(crash, "after_receipt_commit")
        except (ValueError, sqlite3.Error) as exc:
            self.stop("SOURCE_INTEGRITY_OR_STORAGE_STOP:" + type(exc).__name__)
            raise
        self.reconcile()
        return admitted

    def reconcile(self, *, now_ms=None):
        """Complete source/lifecycle reconciliation after receipt durability or restart."""
        from .rc_observe import advance_episode

        decisions = self.decisions()
        if now_ms is None:
            now_ms = max([d.decision_ms for d in decisions]
                         + [r.bar.durable_ms for r in self.receipts()] + [1])
        for d in decisions:
            if not d.episode_id:
                continue
            e = self.episode(d.episode_id)
            if e["state"]["status"] not in TERMINAL and now_ms >= e["updated_ms"]:
                advance_episode(self, d.episode_id, now_ms=now_ms)

    def receipts(self):
        with self.read() as db:
            rows = db.execute("SELECT id,digest,value FROM rc_receipts ORDER BY sequence").fetchall()
        result = []
        for identity, digest, encoded in rows:
            r = Receipt.model_validate_json(encoded)
            if digest != fingerprint(r.model_dump(mode="json")) or identity != r.identity:
                raise ValueError("PERSISTED_RECEIPT_DIGEST_MISMATCH")
            result.append(r)
        return tuple(result)

    def compile(self, symbol, trigger_ms, decision_ms, *, holding_hours=24):
        return decide_s1(symbol=symbol, trigger_ms=trigger_ms, decision_ms=decision_ms,
                         receipts=self.receipts(), source_blocked=bool(self.stopped()),
                         holding_hours=holding_hours)

    def commit(self, decision, *, crash=None):
        d = RCDecision.model_validate_json(decision.model_dump_json())
        value, digest = canonical(d.model_dump(mode="json")), fingerprint(d.model_dump(mode="json"))
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT digest,value FROM rc_decisions WHERE symbol=? AND trigger_ms=?",
                             (d.symbol, d.trigger_close_ms)).fetchone()
            if old:
                if old != (digest, value):
                    raise ValueError("IMMUTABLE_DECISION_CONFLICT")
                return digest  # Never touch episode status or observations during replay.
            latest = db.execute("SELECT MAX(trigger_ms),MAX(decision_ms) FROM rc_decisions WHERE symbol=?",
                                (d.symbol,)).fetchone()
            if latest[0] is not None and (d.trigger_close_ms <= latest[0] or d.decision_ms < latest[1]):
                raise ValueError("STALE_OR_REGRESSING_RC_DECISION")
            # Compile from durable receipts, including sticky source stop, inside the writer transaction.
            expected = self.compile(d.symbol, d.trigger_close_ms, d.decision_ms,
                                    holding_hours=d.diagnostics["holding_hours"])
            if expected != d:
                raise ValueError("DECISION_NOT_BOUND_TO_DURABLE_CAUSAL_SOURCE")
            db.execute("INSERT INTO rc_decisions(symbol,trigger_ms,decision_ms,digest,value) VALUES (?,?,?,?,?)",
                       (d.symbol, d.trigger_close_ms, d.decision_ms, digest, value))
            db.execute("INSERT INTO rc_watermarks VALUES (?,?,?,?)",
                       (d.symbol, d.trigger_close_ms, d.prefix_sha256, digest))
            # Original LT-A envelope stays an honest non-actionable negative. RC V1 carries the S1 plan.
            bars = [r.bar for r in self.receipts() if r.identity in set(d.receipt_ids)]
            legacy = decide(symbol=d.symbol, trigger_close_ms=d.trigger_close_ms, decision_ms=d.decision_ms,
                            bars=bars, source_blocked=bool(self.stopped()))
            self.append_in_transaction(db, legacy)
            if d.episode_id:
                anchors = {"id": d.episode_id, "decision_digest": digest,
                           "decision": d.model_dump(mode="json")}
                db.execute("INSERT INTO rc_episodes VALUES (?,?,?)",
                           (d.episode_id, fingerprint(anchors), canonical(anchors)))
                state = {"status": d.market_state, "reason": "INITIAL_SYNTHETIC_MARKET_CANDIDATE",
                         "account": d.account, "actual_fill": False}
                event = {"state": state, "now_ms": d.decision_ms, "revision": 0}
                db.execute("INSERT INTO rc_transitions VALUES (?,?,?,?,?,?)",
                           (d.episode_id, 0, d.decision_ms, fingerprint(event), "", canonical(event)))
            b_status = d.market_state if d.market_state in B_SHADOW_STATES else "UNKNOWN"
            self._append_b_state(db, d, b_status, d.decision_ms,
                                 ";".join(d.reasons), "SYNTHETIC")
            fault(crash, "before_decision_commit")
        fault(crash, "after_decision_commit")
        return digest

    def decisions(self):
        with self.read() as db:
            rows = db.execute("SELECT digest,value FROM rc_decisions ORDER BY sequence").fetchall()
            watermarks = {(r[0], r[1]): r[2:] for r in db.execute("SELECT * FROM rc_watermarks")}
        result = []
        for digest, value in rows:
            d = RCDecision.model_validate_json(value)
            if fingerprint(d.model_dump(mode="json")) != digest:
                raise ValueError("PERSISTED_RC_DECISION_DIGEST_MISMATCH")
            if watermarks.get((d.symbol, d.trigger_close_ms)) != (d.prefix_sha256, digest):
                raise ValueError("DECISION_WATERMARK_BINDING_MISMATCH")
            result.append(d)
        return tuple(result)

    def episode(self, identity, *, asof_ms=None):
        with self.read() as db:
            row = db.execute("SELECT digest,anchors FROM rc_episodes WHERE id=?", (identity,)).fetchone()
            events = db.execute("SELECT revision,now_ms,digest,previous_digest,value FROM rc_transitions WHERE id=? AND now_ms<=? ORDER BY revision",
                                (identity, asof_ms if asof_ms is not None else 9223372036854775807)).fetchall()
        if row is None:
            raise KeyError(identity)
        anchors = json.loads(row[1])
        if fingerprint(anchors) != row[0] or anchors["id"] != identity or not events:
            raise ValueError("EPISODE_ANCHOR_DIGEST_MISMATCH")
        previous, old_status, last_time = "", None, 0
        for index, (revision, now, digest, prior, encoded) in enumerate(events):
            event = json.loads(encoded)
            status = event["state"]["status"]
            if (revision != index or prior != previous or fingerprint(event) != digest or now < last_time
                    or event["now_ms"] != now or event["revision"] != revision
                    or (old_status is not None and status not in ALLOWED.get(old_status, {old_status}))):
                raise ValueError("EPISODE_TRANSITION_CHAIN_INVALID")
            previous, old_status, last_time = digest, status, now
        return {"anchors": anchors, "state": event["state"], "revision": revision,
                "updated_ms": now, "transition_digest": previous}

    def transition(self, identity, expected_revision, status, now_ms, reason):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = self.episode(identity)
            if old["revision"] != expected_revision:
                raise ValueError("EPISODE_REVISION_CONFLICT")
            if type(now_ms) is not int or now_ms < old["updated_ms"]:
                raise ValueError("EPISODE_TIME_REGRESSION")
            prior = old["state"]["status"]
            if prior in TERMINAL:
                if status != prior:
                    raise ValueError("TERMINAL_EPISODE_IMMUTABLE")
                return old
            if status not in ALLOWED[prior]:
                raise ValueError("EPISODE_TRANSITION_INVALID")
            if status == prior:
                return old
            event = {"state": {**old["state"], "status": status, "reason": reason},
                     "now_ms": now_ms, "revision": expected_revision + 1}
            db.execute("INSERT INTO rc_transitions VALUES (?,?,?,?,?,?)",
                       (identity, expected_revision + 1, now_ms, fingerprint(event),
                        old["transition_digest"], canonical(event)))
            anchors = json.loads(db.execute("SELECT anchors FROM rc_episodes WHERE id=?", (identity,)).fetchone()[0])
            decision = RCDecision.model_validate_json(canonical(anchors["decision"]))
            b_status = status if status in B_SHADOW_STATES else "UNKNOWN"
            self._append_b_state(db, decision, b_status, now_ms, reason, "SYNTHETIC")
        return self.episode(identity)

    def observations(self):
        with self.read() as db:
            rows = db.execute("SELECT digest,value FROM rc_observations ORDER BY id").fetchall()
        result = []
        for digest, value in rows:
            item = json.loads(value)
            if fingerprint(item) != digest:
                raise ValueError("OBSERVATION_DIGEST_MISMATCH")
            result.append(item)
        return result

    def record_observation(self, value):
        from .rc_observe import Observation, observe

        item = Observation.model_validate_json(canonical(value)).model_dump(mode="json")
        episode = self.episode(item["episode_id"])
        decision = RCDecision.model_validate_json(canonical(episode["anchors"]["decision"]))
        expected = observe(decision, self.receipts(), asof_ms=item["asof_ms"],
                           right_censored=item["right_censored"]).model_dump(mode="json")
        if expected != item:
            raise ValueError("OBSERVATION_NOT_BOUND_TO_DURABLE_SYNTHETIC_PATH")
        digest = fingerprint(item)
        with self.connect() as db:
            inserted = db.execute("INSERT OR IGNORE INTO rc_observations VALUES (?,?,?,?)",
                                  (digest, item["episode_id"], digest, canonical(item))).rowcount
            if inserted and item["outcome"] == "AMBIGUOUS_OHLC_ORDER_UNKNOWN":
                self._append_b_state(db, decision, "UNKNOWN", item["asof_ms"], item["outcome"],
                                     "SYNTHETIC")
        return digest

    def verify(self):
        receipts, decisions = self.receipts(), self.decisions()
        self.b_states()
        ids = {r.identity for r in receipts}
        for d in decisions:
            if not set(d.receipt_ids) <= ids:
                raise ValueError("DECISION_RECEIPT_BINDING_MISSING")
            if d.episode_id:
                e = self.episode(d.episode_id)
                if e["anchors"]["decision"] != d.model_dump(mode="json"):
                    raise ValueError("EPISODE_DECISION_BINDING_MISMATCH")
        return {"receipts": len(receipts), "decisions": len(decisions),
                "episodes": sum(d.episode_id is not None for d in decisions),
                "observations": len(self.observations()), "stops": list(self.stopped())}
