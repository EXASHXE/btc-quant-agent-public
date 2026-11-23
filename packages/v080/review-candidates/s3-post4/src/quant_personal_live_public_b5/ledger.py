"""Separate B5 SQLite ledger, exact one-shot claim and reservation transaction."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
import stat
from pathlib import Path

from quant_personal_public_b1.budget import Budget, FAMILY_RULES, FIVE_MIN
from quant_personal_public_b1.clock import VenueTime, check_elapsed
from quant_personal_public_b1.policy import SourceBlocked, require
from quant_personal_public_b1.store import SCHEMA as BUDGET_STORAGE, Store, encode, sha
from quant_personal_public_b1.wire import json_body
from quant_personal_public_bridge_b4 import normalize as norm
from quant_personal_public_bridge_b4.admission import chronology, ms
from quant_personal_public_bridge_b4.session import POLICY
from quant_personal_public_bridge_b4.source import Ledger as B4Ledger

from .enrollment import require_enrolled
from .stages import CANARY_ROUTES, STAGE_CONTRACT, market_requests
from .contract import (
    CONTRACT, FUNDING, GENUINE, GENUINE_PUBLICATION, GENUINE_RECEIPT, QA, QA_PUBLICATION,
    QA_RECEIPT, QA_WARNINGS, ROLLING_MS, SYMBOL_ORDER, RouteRequest, digest,
)

APP_ID = 0x51423550
DB_VERSION = 2
STORAGE_SCHEMA = (
    """CREATE TABLE b5_control (
        singleton INTEGER PRIMARY KEY CHECK(singleton=1), lane TEXT NOT NULL, lineage TEXT NOT NULL,
        signed_sha TEXT NOT NULL, scope_sha TEXT NOT NULL, release_sha TEXT NOT NULL, run_id TEXT NOT NULL,
        approval TEXT, scope TEXT, state TEXT NOT NULL, claimed TEXT, reason TEXT
    )""",
    "CREATE TABLE b5_phases (phase TEXT PRIMARY KEY, scan_id INTEGER UNIQUE NOT NULL REFERENCES scans(id))",
    """CREATE TABLE h2a_canary (
        scan_id INTEGER PRIMARY KEY REFERENCES scans(id),
        payload TEXT NOT NULL, sha256 TEXT NOT NULL
    )""",
    "CREATE TABLE b4_sends (attempt INTEGER PRIMARY KEY REFERENCES attempts(id), stamp TEXT NOT NULL)",
    "CREATE TABLE b5_receipts (attempt INTEGER PRIMARY KEY REFERENCES attempts(id), payload TEXT NOT NULL, sha256 TEXT NOT NULL)",
    """CREATE TABLE b4_visibility (
        scan_id INTEGER PRIMARY KEY REFERENCES publications(scan_id),
        stamp TEXT NOT NULL, upper_ms INTEGER
    )""",
)


class B5Store(Store):
    """The B1 transaction/storage helpers are reused with a distinct application ID."""

    def __init__(self, path, lane, egress, *, create=False):
        if lane == GENUINE:
            from .trust import production_roots

            roots = production_roots()
            require(path == roots.state_path and egress == roots.egress_id, "UNQUALIFIED_PHYSICAL_ORIGIN")
        else:
            require(lane == QA, "UNQUALIFIED_QA_LEDGER")
        self.path, self.origin, self.egress = path.resolve(), lane, egress
        if create:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.close(fd)
            with self.connect(write=True) as db:
                for statement in (*BUDGET_STORAGE, *STORAGE_SCHEMA):
                    db.execute(statement)
                db.execute(f"PRAGMA application_id={APP_ID}")
                db.execute(f"PRAGMA user_version={DB_VERSION}")
                db.execute("INSERT INTO identity VALUES (?,?)", (lane, egress))
                for table in ("identity", "bars", "publications", "b4_sends", "b4_visibility", "b5_phases", "b5_receipts", "h2a_canary"):
                    for op in ("DELETE", "UPDATE"):
                        db.execute(f"CREATE TRIGGER lock_{table}_{op} BEFORE {op} ON {table} "
                                   "BEGIN SELECT RAISE(ABORT,'B5_APPEND_ONLY'); END")
                db.execute("""CREATE TRIGGER lock_settled_receipt BEFORE UPDATE OF
                              scan_id,logical_request,retry,route,weight,family,egress,request,reserved,response,raw,encoded
                              ON attempts WHEN old.response IS NOT NULL
                              BEGIN SELECT RAISE(ABORT,'B5_APPEND_ONLY'); END""")
                db.execute("""CREATE TRIGGER lock_attempt_delete BEFORE DELETE ON attempts
                              BEGIN SELECT RAISE(ABORT,'B5_APPEND_ONLY'); END""")
        else:
            with self.connect() as db:
                self.verify(db)

    def verify(self, db):
        require(db.execute("PRAGMA application_id").fetchone()[0] == APP_ID
                and db.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION, "B5_LEDGER_SCHEMA")
        rows = db.execute("SELECT origin,egress FROM identity").fetchall()
        require(len(rows) == 1 and tuple(rows[0]) == (self.origin, self.egress), "B5_LEDGER_IDENTITY")


def secure_storage(path, uid, *, creating=False):
    require(path.is_absolute() and path.resolve() == path and uid == os.geteuid(), "STORAGE_IDENTITY_MISMATCH")
    folder = path.parent.stat()
    require(stat.S_ISDIR(folder.st_mode) and folder.st_uid == uid and not (folder.st_mode & 0o077),
            "LOCAL_STORAGE_DIRECTORY_NOT_PRIVATE")
    if not creating or path.exists():
        info = path.stat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid == uid and not (info.st_mode & 0o077) and info.st_nlink == 1,
                "LOCAL_STORAGE_FILE_NOT_PRIVATE")


class Ledger:
    # B4's causal SQL is used over private B5 tables with the same shapes; no B4
    # store or origin constructors are used.
    sent = B4Ledger.sent
    record_visibility = B4Ledger.record_visibility
    tail = B4Ledger.tail
    prior_observations = B4Ledger.prior_observations

    def __init__(self, store: B5Store):
        self.store = store
        self.origin = store.origin
        self.schema = GENUINE_PUBLICATION if self.origin == GENUINE else QA_PUBLICATION
        self.warnings = [] if self.origin == GENUINE else QA_WARNINGS
        with store.connect() as db:
            row = self.control(db)
            require(row["lane"] == self.origin, "B5_LEDGER_IDENTITY")
            self.lineage = row["lineage"]
            self.run_id = row["run_id"]
            self.signed_sha = row["signed_sha"]

    @staticmethod
    def control(db):
        row = db.execute("SELECT * FROM b5_control WHERE singleton=1").fetchone()
        require(row is not None, "ACTIVATION_NOT_REGISTERED")
        return row

    @classmethod
    def _create(cls, path, origin, approval, *, envelope=None, raw_scope=None):
        if origin == GENUINE:
            from .approval import verify_envelope
            from .trust import production_roots

            roots = production_roots()
            require(path == roots.state_path and approval == verify_envelope(
                envelope, raw_scope, roots, approval.release, 0, historical=True), "ACTIVATION_NOT_REGISTERED_FOR_SCOPE")
        store = B5Store(path, origin, approval.scope.route.egress_id, create=True)
        lineage = digest([origin, store.egress, approval.signed_sha256, approval.run_id])
        with store.connect(write=True) as db:
            db.execute("""INSERT INTO b5_control VALUES (1,?,?,?,?,?,?,?,?,'AVAILABLE',NULL,NULL)""",
                       (origin, lineage, approval.signed_sha256, approval.scope.sha256, approval.release, approval.run_id,
                        encode(envelope) if envelope is not None else None,
                        encode(raw_scope) if raw_scope is not None else None))
        return cls(store)

    @classmethod
    def qa(cls, path, approval):
        return cls._create(path, QA, approval)

    @classmethod
    def open_qa(cls, path):
        # Read-only probe. The exact B5 application and origin checks follow.
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            row = db.execute("SELECT origin,egress FROM identity").fetchone()
        require(row is not None and row[0] == QA, "UNQUALIFIED_QA_LEDGER")
        return cls(B5Store(path, QA, row[1]))

    def binding(self, row, approval):
        require(row["run_id"] == approval.run_id and row["scope_sha"] == approval.scope.sha256
                and row["release_sha"] == approval.release and row["signed_sha"] == approval.signed_sha256,
                "ACTIVATION_NOT_REGISTERED_FOR_SCOPE")

    def verify_registration(self, db, approval, roots):
        from .approval import verify_envelope
        from .trust import production_roots

        require(type(self) is Ledger and type(self.store) is B5Store and roots is production_roots()
                and self.origin == GENUINE and self.store.path == roots.state_path,
                "UNQUALIFIED_PHYSICAL_ORIGIN")
        require(approval.scope.stage_plan is not None, "H2A_STAGED_SCOPE_REQUIRED")
        require_enrolled(roots.enrollment, roots.local_uid, approval, roots.state_path)
        files = {row[1]: row[2] for row in db.execute("PRAGMA database_list")}
        require(files.get("main") == str(roots.state_path), "SOURCE_LEDGER_PATH_MISMATCH")
        self.store.verify(db)
        row = self.control(db)
        self.binding(row, approval)
        stored = verify_envelope(json.loads(row["approval"]), json.loads(row["scope"]), roots,
                                 approval.release, 0, historical=True)
        require(stored == approval, "ACTIVATION_REGISTRY_SIGNATURE_MISMATCH")
        return row

    def publication(self, scan=None, as_of_ms=None, *, db=None):
        if db is None:
            with self.store.connect() as conn:
                return self.publication(scan, as_of_ms, db=conn)
        sql = """SELECT p.*,s.staged,v.stamp AS visible_stamp,v.upper_ms AS visible_upper
                 FROM publications p JOIN scans s ON s.id=p.scan_id JOIN b4_visibility v ON v.scan_id=p.scan_id
                 WHERE 1=1"""
        args = []
        if scan is not None:
            sql += " AND p.scan_id=?"
            args.append(scan)
        if as_of_ms is not None:
            sql += " AND v.upper_ms<=?"
            args.append(as_of_ms)
        row = db.execute(sql+" ORDER BY p.scan_id DESC LIMIT 1", args).fetchone()
        if row is None:
            return None
        data = json.loads(row["payload"])
        staged = row["staged"]
        require(row["sha256"] == sha(row["payload"].encode()) and staged is not None
                and data["stage_sha256"] == sha(staged.encode()) and data["stage"] == json.loads(staged),
                "PUBLICATION_DIGEST_MISMATCH")
        require(data["origin"] == self.origin and data["schema"] == self.schema and data["warnings"] == self.warnings
                and data["contract"] == CONTRACT and data["lineage"] == self.lineage
                and data["run_id"] == self.run_id and data["signed_sha256"] == self.signed_sha
                and data["scan_id"] == row["scan_id"], "UNQUALIFIED_B5_PUBLICATION")
        phase = db.execute("SELECT phase FROM b5_phases WHERE scan_id=?", (row["scan_id"],)).fetchone()
        require(phase is not None and phase[0] == data["phase"], "PUBLICATION_PHASE_MISMATCH")
        started = row["visible_venue_upper_ms"]
        visible = row["visible_upper"]
        stamp = json.loads(row["visible_stamp"])
        require(data["visible_venue_upper_ms"] == started
                and data["publication_started"]["wall_ms"] == row["published_wall_ms"]
                and (started is None) == (visible is None)
                and (started is None or visible >= started), "PUBLICATION_VISIBILITY_MISMATCH")
        return {**data, "published": stamp, "visible_venue_upper_ms": visible}, digest([row["sha256"], stamp, visible])

    def _record_receipt(self, reservation, proof, physical=None):
        if self.origin == GENUINE:
            from .egress import PhysicalProof
            from .trust import production_roots

            production_roots()
            require(type(physical) is PhysicalProof and physical.reservation == reservation
                    and proof["schema"] == GENUINE_RECEIPT and proof["wire_sha256"] == physical.wire_sha
                    and proof["tls"] is not None and proof["tls"] == physical.response.tls,
                    "UNQUALIFIED_PHYSICAL_PROOF")
        else:
            require(physical is None and proof["schema"] == QA_RECEIPT, "UNQUALIFIED_QA_RECEIPT")
        require(proof["origin"] == self.origin, "RECEIPT_LANE_MISMATCH")
        with self.store.connect(write=True) as db:
            db.execute("INSERT INTO b5_receipts VALUES (?,?,?)", (reservation, encode(proof), digest(proof)))


class Active:
    """Process-owned capability tied to a durable one-shot consumption."""

    def __init__(self, ledger, approval, clock, identity, *, roots=None):
        self.ledger, self.approval, self.clock, self.identity = ledger, approval, clock, identity
        self.roots = roots
        self.budget = Budget(ledger.store, bootstrap=approval.scope.rolling.weight)

    def assert_production(self, roots):
        require(type(self) is Active and self.approval.scope.stage_plan is not None
                and self.roots is roots and self.ledger.origin == GENUINE
                and self.ledger.store.path == roots.state_path
                and self.ledger.store.egress == roots.egress_id, "PRODUCTION_RUN_REQUIRED")

    def _availability(self, db, row, point):
        self.ledger.binding(row, self.approval)
        self._check_live_enrollment()
        self.approval.valid_at(point.wall_ms)
        require(row["state"] == "AVAILABLE", "ACTIVATION_CONSUMED_OR_REVOKED")
        epoch = db.execute("SELECT * FROM budget_epoch WHERE singleton=1").fetchone()
        if epoch:
            require(not epoch["stop"], epoch["stop"] or "GLOBAL_STOP")
            if epoch["cooldown_until"]:
                require(epoch["boot"] == self.identity.boot and point.mono_ms >= epoch["cooldown_until"],
                        "RETRY_AFTER_ACTIVE")
        require(db.execute("SELECT 1 FROM attempts WHERE response IS NULL LIMIT 1").fetchone() is None,
                "DISPATCH_OUTCOME_UNKNOWN")

    def check_available(self):
        with self.ledger.store.connect() as db:
            self._availability(db, self.ledger.control(db), self.clock.sample())

    def claim(self):
        sample = self.clock.sample()
        stamp = self.identity.stamp(sample)
        with self.ledger.store.connect(write=True) as db:
            row = self.ledger.control(db)
            self._availability(db, row, sample)
            db.execute("UPDATE b5_control SET state='CONSUMED',claimed=? WHERE singleton=1", (encode(stamp.data()),))
        scope = self.approval.scope
        self.budget.configure({("REQUEST_WEIGHT", ROLLING_MS): scope.rolling.weight,
                               ("RAW_REQUESTS", ROLLING_MS): scope.rolling.count})

    def _owned(self, db, point):
        row = self.ledger.control(db)
        self.ledger.binding(row, self.approval)
        self._check_live_enrollment()
        self.approval.valid_at(point.wall_ms)
        require(row["state"] == "CONSUMED", row["reason"] or "ACTIVATION_NOT_RUNNING")
        stamp = json.loads(row["claimed"])
        require((stamp["boot"], stamp["session"]) == (self.identity.boot, self.identity.session),
                "ACTIVATION_PROCESS_OWNERSHIP")
        check_elapsed(ms(stamp), point, POLICY)

    def begin_phase(self, phase):
        scope = self.approval.scope
        require(phase in scope.phase_limits, "SCAN_PHASE_NOT_AUTHORIZED")
        sample = self.clock.sample()
        with self.ledger.store.connect(write=True) as db:
            self._owned(db, sample)
            require(db.execute("SELECT 1 FROM b5_phases WHERE phase=?", (phase,)).fetchone() is None,
                    "SCAN_PHASE_ALREADY_CONSUMED")
            if self.ledger.origin == GENUINE and phase != "bootstrap":
                base = db.execute("""SELECT v.stamp FROM b4_visibility v JOIN b5_phases p ON v.scan_id=p.scan_id
                                   WHERE p.phase='bootstrap' AND v.upper_ms IS NOT NULL""").fetchone()
                require(base is not None, "BOOTSTRAP_REQUIRED")
                base_point = ms(json.loads(base["stamp"]))
                delay = int(phase.split("_")[1]) * 60_000
                require(delay <= sample.mono_ms-base_point.mono_ms <= delay+30_000, "REFRESH_WINDOW_MISMATCH")
                if phase == "refresh_10":
                    require(db.execute("SELECT 1 FROM b5_phases WHERE phase='refresh_5'").fetchone() is not None,
                            "PRIOR_REFRESH_REQUIRED")
            scan = db.execute("INSERT INTO scans(starting) VALUES (?)", (encode(self.identity.stamp(sample).data()),))
            db.execute("INSERT INTO b5_phases VALUES (?,?)", (phase, scan.lastrowid))
            return scan.lastrowid, sample

    def _budget_stop(self, db, epoch):
        if epoch["stop"]:
            return epoch["stop"]
        if epoch["last_mono"] < epoch["cooldown_until"]:
            return "RETRY_AFTER_ACTIVE"
        if db.execute("SELECT 1 FROM attempts WHERE response IS NULL LIMIT 1").fetchone():
            return "DISPATCH_OUTCOME_UNKNOWN"
        return None

    def _validate_request(self, request):
        require(type(request) is RouteRequest and (request.route != FUNDING
                or request.funding_debit == self.approval.scope.funding_debit), "REQUEST_OUTSIDE_APPROVED_DEBIT")
        return request.validate()[0]

    def _check_live_enrollment(self):
        if self.ledger.origin == GENUINE:
            from .trust import production_roots

            roots = production_roots()
            require(self.roots is roots and self.approval.scope.stage_plan is not None,
                    "H2A_STAGED_SCOPE_REQUIRED")
            require_enrolled(roots.enrollment, roots.local_uid, self.approval, roots.state_path)

    def pass_canary(self, scan, first_id, meta_id, clock_evidence):
        """Persist the canary milestone before any market endpoint is admitted."""
        plan = self.approval.scope.stage_plan
        require(plan is not None, "H2A_STAGED_SCOPE_REQUIRED")
        with self.ledger.store.connect(write=True) as db:
            self._owned(db, self.clock.sample())
            rows = db.execute("""SELECT a.id,a.route,a.raw,a.response,a.retry,a.request,s.stamp,r.sha256,r.payload
                                 FROM attempts a JOIN b4_sends s ON s.attempt=a.id
                                 JOIN b5_receipts r ON r.attempt=a.id
                                 WHERE a.scan_id=? ORDER BY a.id""", (scan,)).fetchall()
            require(len(rows) == 2 and tuple(row["route"] for row in rows) == CANARY_ROUTES
                    and tuple(row["id"] for row in rows) == (first_id,meta_id)
                    and all(row["retry"] == 0 for row in rows), "CANARY_RECEIPTS_REQUIRED")
            stamps = []
            bodies = []
            for row in rows:
                response = json.loads(row["response"])
                proof = json.loads(row["payload"])
                require(response["status"] == 200 and response["error"] is None and row["raw"] is not None
                        and sha(row["raw"]) == response["body_sha256"] == proof["raw_sha256"]
                        and digest(proof) == row["sha256"]
                        and proof["origin"] == self.ledger.origin and proof["signed_sha256"] == self.ledger.signed_sha
                        and proof["attempt"] == row["id"] and proof["scan_id"] == scan
                        and json.loads(row["request"]) == RouteRequest(row["route"],{}).data(),
                        "CANARY_RECEIPT_UNQUALIFIED")
                start, received = json.loads(row["stamp"]), response["receipt"]
                chronology(start, received)
                stamps.extend((start,received))
                bodies.append(json_body(row["raw"]))
            chronology(*stamps)
            server_ms = norm.n.integer(norm.n.obj(bodies[0]).get("serverTime"), "serverTime", minimum=1)
            point = VenueTime.bracket(ms(stamps[0]),ms(stamps[1]),server_ms,POLICY)
            require(point.evidence() == clock_evidence and abs(server_ms-ms(stamps[1]).wall_ms) <= 300_000,
                    "CANARY_CLOCK_UNQUALIFIED")
            norm.n.exchange_info(bodies[1], SYMBOL_ORDER)
            summary = {"schema": STAGE_CONTRACT, "time_receipt":first_id, "metadata_receipt":meta_id,
                       "receipt_sha256": [row["sha256"] for row in rows],
                       "cutoff_venue_ms":point.lower_ms, "market_authorized":plan.market_allowed,
                       "scope_sha256":self.approval.scope.sha256}
            db.execute("INSERT INTO h2a_canary VALUES (?,?,?)", (scan,encode(summary),digest(summary)))
            return summary

    def _check_stage(self, db, phase, scan, logical, retry, request, *, reserved_id=0):
        plan = self.approval.scope.stage_plan
        if plan is None:
            return
        require(phase == "bootstrap", "TIMED_REFRESH_DISABLED")
        marker = db.execute("SELECT payload,sha256 FROM h2a_canary WHERE scan_id=?", (scan,)).fetchone()
        if marker is None:
            sent = db.execute("SELECT COUNT(*) FROM attempts WHERE scan_id=? AND id!=?",
                              (scan,reserved_id)).fetchone()[0]
            require(sent < len(CANARY_ROUTES) and retry == 0 and logical == sent+1
                    and request.route == CANARY_ROUTES[sent] and not request.params, "CANARY_REQUEST_SEQUENCE")
            return
        require(plan.market_allowed, "STAGE2_NOT_AUTHORIZED")
        require(plan.market_retry_limit != 0 or retry == 0, "STAGE2_RETRY_POLICY_DENIED")
        proof = json.loads(marker["payload"])
        require(marker["sha256"] == digest(proof) and proof["schema"] == STAGE_CONTRACT
                and proof["market_authorized"] is True and proof["scope_sha256"] == self.approval.scope.sha256,
                "CANARY_PROOF_MISMATCH")
        def key(route, data):
            return (route, encode(data))

        order = {key(r.route,r.data()): position for position,r in enumerate(market_requests(proof["cutoff_venue_ms"]))}
        target = key(request.route,request.data())
        require(target in order, "STAGE2_REQUEST_OUTSIDE_PLAN")
        rows = db.execute("""SELECT logical_request,retry,response,route,request,weight FROM attempts
                             WHERE scan_id=? AND id>? AND id!=? ORDER BY id""",
                          (scan,proof["metadata_receipt"],reserved_id)).fetchall()
        require(len(rows)+1 <= plan.market_count and sum(row["weight"] for row in rows)+request.validate()[0]
                <= plan.market_weight, "STAGE2_BUDGET_EXHAUSTED")
        previous = rows[-1] if rows else None
        if retry == 0:
            require(previous is None or order.get((previous["route"],previous["request"]),len(order)) < order[target],
                    "STAGE2_REQUEST_ORDER_OR_DUPLICATE")
        else:
            require(retry == 1 and previous is not None and previous["retry"] == 0
                    and previous["logical_request"] == logical and (previous["route"],previous["request"]) == target
                    and previous["response"] is not None, "STAGE2_RETRY_NOT_BOUND")
            response = json.loads(previous["response"])
            require(response["status"] in {408,500,502,503,504} or (response["status"] is None and
                    response["error"] in {"TRANSIENT_WIRE_FAILURE","TRANSIENT_CONNECT_FAILURE"}),
                    "STAGE2_RETRY_NOT_TRANSIENT")

    def reserve(self, phase, scan, logical, retry, request, sample):
        debit = self._validate_request(request)
        scope = self.approval.scope
        stamp = self.identity.stamp(sample)
        pending = None
        with self.ledger.store.connect(write=True) as db:
            self._owned(db, sample)
            selected = db.execute("SELECT phase FROM b5_phases WHERE scan_id=?", (scan,)).fetchone()
            require(selected is not None and selected["phase"] == phase, "SCAN_PHASE_NOT_AUTHORIZED")
            self._check_stage(db, phase, scan, logical, retry, request)
            epoch = self.budget.epoch(db, stamp)
            blocked = self._budget_stop(db, epoch)
            if not blocked:
                for sql, args, cap in (
                    ("SELECT COUNT(*),COALESCE(SUM(weight),0) FROM attempts", (), scope.total),
                    ("SELECT COUNT(*),COALESCE(SUM(weight),0) FROM attempts WHERE scan_id=?",
                     (scan,), scope.phase_limits[phase]),
                ):
                    count, weight = db.execute(sql, args).fetchone()
                    require(count+1 <= cap.count and weight+debit <= cap.weight, "ONE_SHOT_BUDGET_EXHAUSTED")
                family, cap = FAMILY_RULES.get(request.route, ("GENERAL", 0))
                rules = {(kind, window): ceiling for kind, window, ceiling in db.execute("SELECT * FROM rules")}
                if cap:
                    rules[family, FIVE_MIN] = cap
                # Maintain headroom in every trusted venue weight window.
                rules = {(kind, window): (ceiling - scope.headroom_weight if kind == "REQUEST_WEIGHT" else ceiling)
                         for (kind, window), ceiling in rules.items()}
                blocked = self.budget.check_windows(db, stamp.monotonic_ms, rules, debit)
                if not blocked:
                    row = db.execute("""INSERT INTO attempts(scan_id,logical_request,retry,route,weight,family,egress,
                                     request,reserved,accounted_mono) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                                     (scan, logical, retry, request.route, debit, family, self.ledger.store.egress,
                                      encode(request.data()), encode(stamp.data()), stamp.monotonic_ms))
                    pending = row.lastrowid
        if blocked:
            raise SourceBlocked(blocked)
        return pending

    def assert_pending(self, ident, request):
        with self.ledger.store.connect() as db:
            self._owned(db, self.clock.sample())
            row = db.execute("""SELECT a.*,p.phase FROM attempts a JOIN b4_sends s ON s.attempt=a.id
                                JOIN b5_phases p ON p.scan_id=a.scan_id WHERE a.id=? AND a.response IS NULL""", (ident,)).fetchone()
            debit = self._validate_request(request)
            require(row is not None and row["route"] == request.route and row["weight"] == debit
                    and row["request"] == encode(request.data()) and row["egress"] == self.ledger.store.egress,
                    "UNRESERVED_PHYSICAL_REQUEST")
            self._check_stage(db,row["phase"],row["scan_id"],row["logical_request"],row["retry"],
                              request,reserved_id=ident)
            epoch = db.execute("SELECT * FROM budget_epoch WHERE singleton=1").fetchone()
            require(epoch is not None and not epoch["stop"] and epoch["boot"] == self.identity.boot
                    and epoch["cooldown_until"] <= self.clock.sample().mono_ms, "GLOBAL_STOP")
            return row

    def close(self, *, reason=None):
        with self.ledger.store.connect(write=True) as db:
            row = self.ledger.control(db)
            self.ledger.binding(row, self.approval)
            if row["state"] == "CONSUMED" and json.loads(row["claimed"])["session"] == self.identity.session:
                db.execute("UPDATE b5_control SET state=?,reason=? WHERE singleton=1",
                           ("HALTED" if reason else "COMPLETE", reason))

    def revoke(self):
        with self.ledger.store.connect(write=True) as db:
            self.ledger.binding(self.ledger.control(db), self.approval)
            db.execute("""UPDATE b5_control SET state='REVOKED',reason='ACTIVATION_REVOKED'
                          WHERE singleton=1 AND state IN ('AVAILABLE','CONSUMED')""")
            return self.ledger.control(db)["state"]
