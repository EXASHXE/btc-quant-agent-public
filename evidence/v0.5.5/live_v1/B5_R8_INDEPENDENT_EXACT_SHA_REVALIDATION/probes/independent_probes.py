"""Independent B5 R8 probes authored from requirements and production interfaces.

Run from the exact target checkout with PYTHONPATH=<checkout>/src. No committed
test helper is imported. All data/provider inputs are synthetic and local.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import sqlite3
import sys
import tempfile
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from btc_quant_agent import live_db
from btc_quant_agent.approval.store import LiveStore
from btc_quant_agent.decision.models import AnalysisResultV1, CasePackageV1
from btc_quant_agent.decision.risk import RiskCompilerV1, RiskPolicyV1
from btc_quant_agent.decision.service import TacticalLiveService
from btc_quant_agent.position_supervisor import supervisor as sm
from btc_quant_agent.position_supervisor.models import PositionObservationV1

SRC = Path.cwd() / "src"
OUT = Path(__file__).parent
NOW = 1_790_000_000_000
TABLE = "live_position_case_dispatches"
results = []


def stable(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def digest(value):
    return hashlib.sha256(stable(value).encode()).hexdigest()


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def probe(name, fn):
    try:
        with tempfile.TemporaryDirectory(prefix="b5-r8-probe-") as tmp:
            detail = fn(Path(tmp))
        results.append({"name": name, "status": "PASS", "detail": detail})
    except BaseException as exc:
        results.append({"name": name, "status": "FAIL", "error": repr(exc),
                        "traceback": traceback.format_exc()})
    print(name, results[-1]["status"], flush=True)


def base_case():
    return CasePackageV1.build(
        case_id="independent-synthetic-base", created_at_ms=NOW,
        observed_at_ms=NOW, expires_at_ms=NOW + 180_000, symbol="BTCUSDT",
        trigger="INDEPENDENT_PROBE", strategy="SYNTHETIC", strategy_version="probe-v1",
        direction="LONG", evidence_id="a" * 64, snapshot_hash="synthetic-only",
        signal_identity="independent-local", price=60_000.0, entry_low=59_990.0,
        entry_high=60_010.0, stop_loss=55_000.0, take_profit_1=66_000.0,
        take_profit_2=70_000.0, atr=700.0, data_quality="OK", spread_bps=1.0,
        liquidity_usdt=1_000_000.0,
    )


def observation():
    return PositionObservationV1.build(
        account_snapshot_hash="synthetic-account", market_source_hash="synthetic-market",
        environment="DRY_RUN", credential_namespace="NONE", account_id="probe-account",
        symbol="BTCUSDT", observed_at_ms=NOW, quantity=0.01, previous_quantity=0.0,
        entry_price=60_000.0, mark_price=60_000.0, unrealized_pnl_usdt=0.0,
        realized_pnl_usdt=0.0, margin_usdt=10.0, stop_price=55_000.0,
        take_profit_price=70_000.0, order_status="FILLED", order_filled_quantity=0.01,
        order_observed_at_ms=NOW,
    )


class Cut(BaseException):
    """Synthetic crash boundary, outside normal application exception recovery."""


class Backend:
    def __init__(self):
        self.inputs = []

    async def analyze(self, case, mode):
        self.inputs.append({"case_json": case.canonical_json(), "mode": mode.value})
        return AnalysisResultV1.fail_closed(case, "synthetic", "local-only", "PROBE_NO_ACTION")


class Recorder:
    def __init__(self, behavior="ok"):
        self.inputs = []
        self.behavior = behavior

    async def analyze_case(self, case):
        self.inputs.append(case.canonical_json())
        if self.behavior == "error":
            raise RuntimeError("SYNTHETIC_PROVIDER_ERROR")


class Harness(sm.PositionSupervisor):
    def __init__(self, *args, cut=None, rollback=False, **kwargs):
        self.cut = cut
        self.rollback_terminal = rollback
        self.receipt = None
        self.preterminal = None
        self.saw_uncommitted_done = False
        super().__init__(*args, **kwargs)

    def _mint_analysis_admission(self, *args, **kwargs):
        if self.cut == "frozen":
            raise Cut("AFTER_PRODUCTION_FREEZE_BEFORE_ADMISSION")
        self.receipt = super()._mint_analysis_admission(*args, **kwargs)
        if self.cut == "admitted":
            raise Cut("AFTER_PRODUCTION_ADMISSION_BEFORE_PROVIDER")
        return self.receipt

    def _complete_analysis(self, admission, token, now):
        event_id = json.loads(admission.event_json)["event_id"]
        self.preterminal = self.get_dispatch(event_id)
        if self.cut == "provider_returned":
            raise Cut("AFTER_PROVIDER_BEFORE_TERMINAL")
        if not self.rollback_terminal:
            return super()._complete_analysis(admission, token, now)

        @contextmanager
        def injected_commit_failure(path, busy_timeout_ms=10000):
            with live_db.connection(path, busy_timeout_ms) as db:
                yield db
                marker = db.execute(f"SELECT state,analysis_completed FROM {TABLE} WHERE event_id=?",
                                    (event_id,)).fetchone()
                self.saw_uncommitted_done = tuple(marker) == ("DONE", 1)
                raise sqlite3.OperationalError("SYNTHETIC_FAILURE_BEFORE_TERMINAL_COMMIT")

        with patch.object(sm, "connection", injected_commit_failure):
            return super()._complete_analysis(admission, token, now)


def setup(tmp, phase="completed", real_service=False, rollback=False, behavior="ok"):
    path = tmp / "synthetic.sqlite"
    provider = Backend() if real_service else Recorder(behavior)
    service = (TacticalLiveService(LiveStore(path), provider, RiskCompilerV1(RiskPolicyV1()),
                                  clock_ms=lambda: NOW + 5)
               if real_service else provider)
    fresh_calls = []

    def fresh(symbol):
        fresh_calls.append(symbol)
        return base_case()

    supervisor = Harness(path, service, fresh, lease_clock_ms=lambda: NOW + 5,
                         cut=phase if phase != "completed" else None, rollback=rollback)
    events = supervisor.evaluate(observation(), NOW)
    check(len(events) == 1, "synthetic observation must emit exactly one open event")
    event = events[0]
    if phase != "pending":
        try:
            drained = asyncio.run(supervisor.drain_pending_dispatches(NOW + 5))
        except Cut:
            drained = ()
    else:
        supervisor.cut = None
        drained = ()
    row = supervisor.get_dispatch(event.event_id)
    if phase == "frozen":
        check(row["position_case_json"] and not row["analysis_admission_hash"], "freeze checkpoint")
    elif phase in ("admitted", "provider_returned"):
        check(row["analysis_admission_hash"] and row["analysis_completed"] == 0, "admit checkpoint")
    elif phase == "completed" and not rollback and behavior == "ok":
        check(len(drained) == 1 and row["state"] == "DONE" and row["analysis_completed"] == 1,
              "positive production terminal path")
    return supervisor, event, provider, service, fresh_calls


def rejected(supervisor, event_id, sql, values=()):
    before = supervisor.get_dispatch(event_id)
    failure = None
    with live_db.connection(supervisor.path) as db:
        check(db.execute("PRAGMA recursive_triggers").fetchone()[0] == 1, "normal project pragma")
        try:
            db.execute(sql, values)
        except sqlite3.DatabaseError as exc:
            failure = str(exc)
        check(failure is not None, "authority write unexpectedly accepted: " + sql)
        inside = dict(db.execute(f"SELECT * FROM {TABLE} WHERE event_id=?", (event_id,)).fetchone())
        check(inside == before, "rejected statement changed row before connection exit")
    after = supervisor.get_dispatch(event_id)
    check(after == before, "rejected write changed original row after connection commit")
    return {"sql": sql, "error": failure, "unchanged_row_hash": digest(before)}


def insert_sql(row, form="INSERT", tail=""):
    columns = list(row)
    return (f"{form} INTO {TABLE} ({','.join(columns)}) VALUES "
            f"({','.join('?' for _ in columns)}){tail}", tuple(row.values()))


def blank(identifier="fresh-independent"):
    return dict(event_id=identifier, event_hash=identifier + "-hash", symbol="BTCUSDT",
                state="PENDING", created_at_ms=NOW, updated_at_ms=NOW)


def v1_pragmas(tmp, timeout):
    records = []
    for _ in range(3):
        with live_db.connection(tmp / "db.sqlite", timeout) as db:
            values = {key: db.execute(f"PRAGMA {key}").fetchone()[0] for key in
                      ("recursive_triggers", "journal_mode", "synchronous", "foreign_keys", "busy_timeout")}
            check(values == dict(recursive_triggers=1, journal_mode="wal", synchronous=2,
                                 foreign_keys=1, busy_timeout=timeout), "shared connection settings")
            records.append(values)
    return records


def v1_failure(tmp, mode):
    original = sqlite3.connect
    observed = {"yielded": False, "rollback": False, "closed": False}

    class Fault(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            if sql == "PRAGMA recursive_triggers=ON":
                if mode == "enable_error":
                    raise sqlite3.OperationalError("synthetic unsupported pragma")
                if mode == "readback_zero":
                    return super().execute("PRAGMA recursive_triggers=OFF")
            if sql == "PRAGMA recursive_triggers":
                if mode == "read_error":
                    raise sqlite3.OperationalError("synthetic unreadable pragma")
                if mode == "read_missing":
                    return super().execute("SELECT 1 WHERE 0")
            return super().execute(sql, *args, **kwargs)

        def rollback(self):
            observed["rollback"] = True
            return super().rollback()

        def close(self):
            observed["closed"] = True
            return super().close()

    def connect(*args, **kwargs):
        return original(*args, **kwargs, factory=Fault)

    try:
        with patch.object(live_db.sqlite3, "connect", connect):
            with live_db.connection(tmp / "db.sqlite"):
                observed["yielded"] = True
    except (RuntimeError, sqlite3.Error, TypeError) as exc:
        observed["error"] = str(exc)
    check(not observed["yielded"] and observed["rollback"] and observed["closed"], "must fail closed")
    return observed


def v2(tmp, mutation, form="INSERT"):
    supervisor = sm.PositionSupervisor(tmp / "db.sqlite")
    row = blank()
    row.update(mutation)
    sql, values = insert_sql(row, form)
    try:
        with live_db.connection(supervisor.path) as db:
            db.execute(sql, values)
    except sqlite3.DatabaseError as exc:
        failure = str(exc)
    else:
        check(not mutation, "nonblank initial authority insert unexpectedly accepted")
        failure = None
    stored = supervisor.get_dispatch(row["event_id"])
    check((stored is None) == bool(mutation), "rejected initial insert must leave no row")
    return {"mutation": mutation, "sql": sql, "error": failure, "stored": stored}


def v3(tmp, phase, form, payload, collision):
    supervisor, event, *_ = setup(tmp, phase)
    old = supervisor.get_dispatch(event.event_id)
    row = blank(event.event_id if collision == "primary" else "different-id-same-event-hash")
    row["event_hash"] = old["event_hash"]
    if payload == "fabricated_terminal":
        row.update(old)
        if collision == "unique":
            row["event_id"] = "different-id-same-event-hash"
        row.update(state="DONE", analysis_completed=1, lease_token=None, lease_expires_at_ms=0)
    sql, values = insert_sql(row, form)
    detail = rejected(supervisor, event.event_id, sql, values)
    if collision == "unique":
        check(supervisor.get_dispatch("different-id-same-event-hash") is None, "replacement id leaked")
    detail.update(phase=phase, form=form, payload=payload, collision=collision)
    return detail


def v4(tmp, operation):
    supervisor, event, *_ = setup(tmp, "admitted")
    if operation == "upsert_authority":
        sql, values = insert_sql(blank(event.event_id), tail=
            " ON CONFLICT(event_id) DO UPDATE SET dispatch_authority_json='{}'")
    elif operation == "upsert_completion":
        sql, values = insert_sql(blank(event.event_id), tail=
            " ON CONFLICT(event_id) DO UPDATE SET state='DONE',analysis_completed=1,"
            "lease_token=NULL,lease_expires_at_ms=0")
    elif operation == "completion":
        sql = f"UPDATE {TABLE} SET state='DONE',analysis_completed=1,lease_token=NULL,lease_expires_at_ms=0 WHERE event_id=?"
        values = (event.event_id,)
    elif operation == "marker_only":
        sql = f"UPDATE {TABLE} SET analysis_completed=1 WHERE event_id=?"
        values = (event.event_id,)
    elif operation == "done_only":
        sql = f"UPDATE {TABLE} SET state='DONE' WHERE event_id=?"
        values = (event.event_id,)
    elif operation == "delete":
        sql = f"DELETE FROM {TABLE} WHERE event_id=?"
        values = (event.event_id,)
    else:
        field = operation.removeprefix("authority_")
        sql = f"UPDATE {TABLE} SET {field}='changed' WHERE event_id=?"
        values = (event.event_id,)
    return rejected(supervisor, event.event_id, sql, values)


def v5_positive(tmp):
    supervisor, event, backend, service, fresh_calls = setup(tmp, real_service=True)
    row = supervisor.get_dispatch(event.event_id)
    before = supervisor.preterminal
    check(before["state"] == "DISPATCHING" and before["analysis_completed"] == 0
          and before["analysis_admission_hash"], "marker only on terminal transition")
    check(len(backend.inputs) == 1 and len(fresh_calls) == 1, "exactly one provider invocation")
    check(service.exchange_write_count == 0, "no exchange writes")
    capsule = json.loads(row["dispatch_authority_json"])
    expected = dict(schema_version="POSITION_DISPATCH_AUTHORITY_V1",
                    **{field: getattr(event, field) for field in
                       ("event_id", "event_hash", "symbol", "environment", "credential_namespace",
                        "account_id", "position_side", "position_authority_key")},
                    position_case_id=row["position_case_id"], position_case_hash=row["position_case_hash"],
                    lease_token=before["lease_token"])
    check(capsule == expected and stable(expected) == row["dispatch_authority_json"], "canonical capsule")
    check(digest(expected) == row["dispatch_authority_hash"], "independent capsule digest")
    check(digest(dict(schema_version="POSITION_ANALYSIS_ADMISSION_V1",
                      dispatch_authority_hash=digest(expected))) == row["analysis_admission_hash"], "receipt binding")
    check(backend.inputs[0]["case_json"] == row["position_case_json"] == supervisor.receipt.case_json,
          "exact admitted bytes reached genuine service/provider boundary")
    check(service.store.get_case(row["position_case_id"]).canonical_json() == row["position_case_json"],
          "archive agrees with provider input")
    for clock in (NOW + 10, NOW + 100_000):
        restarted = sm.PositionSupervisor(supervisor.path, service,
                        lambda _: (_ for _ in ()).throw(AssertionError("fresh must not replay")),
                        lease_clock_ms=lambda: clock)
        check(asyncio.run(restarted.drain_pending_dispatches(clock)) == (), "DONE must not replay")
        check(restarted.get_dispatch(event.event_id) == row, "restart changed completed row")
    check(len(backend.inputs) == 1, "restart replayed provider")
    return dict(row=row, before_terminal=before, provider_inputs=backend.inputs,
                admission=dataclasses.asdict(supervisor.receipt), exchange_write_count=0)


def v5_rollback(tmp):
    supervisor, event, provider, service, _ = setup(tmp, rollback=True)
    row = supervisor.get_dispatch(event.event_id)
    check(supervisor.saw_uncommitted_done, "terminal update must precede injected commit failure")
    check(row["analysis_completed"] == 0 and row["state"] != "DONE", "terminal rollback leaked marker")
    check(len(provider.inputs) == 1 and row["state"] == "FAILED_CLOSED", "uncertain terminal fails closed")
    restarted = sm.PositionSupervisor(supervisor.path, service, lambda _: base_case(),
                                     lease_clock_ms=lambda: NOW + 100_000)
    check(asyncio.run(restarted.drain_pending_dispatches(NOW + 100_000)) == (), "rollback replay")
    check(len(provider.inputs) == 1, "rollback recovery called provider twice")
    return dict(row=row, before_terminal=supervisor.preterminal, saw_uncommitted_done=True,
                provider_calls=len(provider.inputs))


def v5_restart(tmp, phase):
    supervisor, event, provider, service, _ = setup(tmp, phase)
    original = supervisor.get_dispatch(event.event_id)
    restarted = sm.PositionSupervisor(supervisor.path, service,
                  lambda _: (_ for _ in ()).throw(AssertionError("frozen case must be reused")),
                  lease_clock_ms=lambda: NOW + 100_000)
    drained = asyncio.run(restarted.drain_pending_dispatches(NOW + 100_000))
    after = restarted.get_dispatch(event.event_id)
    if phase == "frozen":
        check(len(drained) == 1 and after["state"] == "DONE" and len(provider.inputs) == 1,
              "frozen unadmitted recovery")
        check(provider.inputs[0] == original["position_case_json"], "frozen bytes changed")
    else:
        check(not drained and after["state"] == "FAILED_CLOSED" and after["analysis_completed"] == 0,
              "uncertain admitted recovery")
        check(len(provider.inputs) == (1 if phase == "provider_returned" else 0), "uncertain provider replay")
    check(after["position_case_json"] == original["position_case_json"], "recovery replaced frozen authority")
    return dict(before=original, after=after, provider_calls=len(provider.inputs))


def v6_terminal_binding(tmp, field):
    supervisor, event, _, _, _ = setup(tmp, "admitted")
    before = supervisor.get_dispatch(event.event_id)
    receipt = supervisor.receipt
    token = before["lease_token"]
    if field == "lease":
        token += "-wrong"
    elif field in ("authority_hash", "admission_hash"):
        receipt = dataclasses.replace(receipt, **{field: "0" * 64})
    elif field == "authority_json":
        receipt = dataclasses.replace(receipt, authority_json="{}")
    elif field == "event_json":
        data = event.model_dump(exclude={"event_hash"})
        data["source_hash"] = "different-synthetic-source"
        other = type(event).build(**data)
        receipt = dataclasses.replace(receipt, event_json=other.canonical_json())
    elif field == "case_json":
        case = CasePackageV1.model_validate_json(receipt.case_json)
        data = case.model_dump(exclude={"case_hash"})
        data["snapshot_hash"] = "different-synthetic-snapshot"
        receipt = dataclasses.replace(receipt, case_json=CasePackageV1.build(**data).canonical_json())
    try:
        supervisor._complete_analysis(receipt, token, NOW + 5)
    except (ValueError, KeyError) as exc:
        failure = str(exc)
    else:
        raise AssertionError("terminal accepted mismatched " + field)
    check(supervisor.get_dispatch(event.event_id) == before, "bad terminal mutated authority")
    return dict(changed_field=field, error=failure, unchanged_row_hash=digest(before))


LEGACY_SCHEMA = f"""
CREATE TABLE {TABLE} (
event_id TEXT PRIMARY KEY, event_hash TEXT NOT NULL UNIQUE,
position_case_id TEXT NOT NULL DEFAULT '',position_case_hash TEXT NOT NULL DEFAULT '',
position_case_json TEXT NOT NULL DEFAULT '',case_hash TEXT NOT NULL DEFAULT '',
symbol TEXT NOT NULL,state TEXT NOT NULL,retry_count INTEGER NOT NULL DEFAULT 0,
lease_token TEXT,lease_expires_at_ms INTEGER NOT NULL DEFAULT 0,
created_at_ms INTEGER NOT NULL,updated_at_ms INTEGER NOT NULL);
CREATE TABLE live_position_events (
event_id TEXT PRIMARY KEY,event_hash TEXT NOT NULL UNIQUE,trigger TEXT NOT NULL,
symbol TEXT NOT NULL,source_hash TEXT NOT NULL,observed_at_ms INTEGER NOT NULL,
payload TEXT NOT NULL,environment TEXT,credential_namespace TEXT,account_id TEXT,
position_side TEXT,position_authority_key TEXT);
"""


def legacy_image(path, event, case, state):
    row = blank(event.event_id)
    row.update(event_hash=event.event_hash, position_case_id=case.case_id,
               position_case_hash=case.case_hash, position_case_json=case.canonical_json(),
               case_hash=case.case_hash, state=state)
    with sqlite3.connect(path) as db:
        db.executescript(LEGACY_SCHEMA)
        sql, values = insert_sql(row)
        db.execute(sql, values)
        fields = ("event_id", "event_hash", "trigger", "symbol", "source_hash", "observed_at_ms",
                  "environment", "credential_namespace", "account_id", "position_side", "position_authority_key")
        db.execute(f"INSERT INTO live_position_events ({','.join(fields)},payload) VALUES ({','.join('?' for _ in range(len(fields)+1))})",
                   tuple(getattr(event, f) for f in fields) + (event.canonical_json(),))
        before = dict(zip([d[0] for d in db.execute(f"SELECT * FROM {TABLE}").description],
                          db.execute(f"SELECT * FROM {TABLE}").fetchone()))
    return before


def v7_legacy(tmp, state):
    source, event, *_ = setup(tmp / "source", "pending")
    case = sm.position_case_from_event(base_case(), event)
    path = tmp / "historical.sqlite"
    before = legacy_image(path, event, case, state)
    provider = Recorder()
    current = sm.PositionSupervisor(path, provider,
                  lambda _: (_ for _ in ()).throw(AssertionError("historical case must remain frozen")),
                  lease_clock_ms=lambda: NOW + 5)
    migrated = current.get_dispatch(event.event_id)
    check({k: migrated[k] for k in before} == before, "migration changed legacy row")
    check(migrated["analysis_completed"] == 0 and not migrated["analysis_admission_hash"], "legacy marker fabricated")
    drained = asyncio.run(current.drain_pending_dispatches(NOW + 5))
    after = current.get_dispatch(event.event_id)
    if state == "DONE":
        check(not drained and not provider.inputs and after == migrated, "historical DONE replay/change")
    else:
        check(len(drained) == 1 and after["state"] == "DONE" and after["analysis_completed"] == 1,
              "historical frozen PENDING completion")
        check(provider.inputs == [case.canonical_json()], "historical exact case mismatch")
    return dict(before=before, migrated=migrated, after=after, provider_calls=len(provider.inputs))


def v7_concurrent(tmp, initial):
    path = tmp / "concurrent.sqlite"
    if initial == "current":
        sm.PositionSupervisor(path)
    elif initial == "legacy":
        with sqlite3.connect(path) as db:
            db.executescript(LEGACY_SCHEMA)
    barrier = Barrier(6)

    def construct(index):
        barrier.wait(timeout=15)
        sm.PositionSupervisor(path)
        with live_db.connection(path, 2700 + index) as db:
            values = {key: db.execute(f"PRAGMA {key}").fetchone()[0] for key in
                      ("recursive_triggers", "journal_mode", "synchronous", "foreign_keys", "busy_timeout")}
            columns = [r["name"] for r in db.execute(f"PRAGMA table_info({TABLE})")]
            triggers = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name")]
        check(values == dict(recursive_triggers=1, journal_mode="wal", synchronous=2,
                             foreign_keys=1, busy_timeout=2700 + index), "concurrent settings")
        check(len(columns) == len(set(columns)) and "analysis_completed" in columns, "concurrent schema")
        check("trg_live_position_dispatch_blank_insert" in triggers
              and "trg_live_position_dispatches_immutable_delete" in triggers
              and "trg_live_position_dispatch_done_requires_completion" in triggers, "concurrent guards")
        return dict(index=index, settings=values, columns=columns, triggers=triggers)

    with ThreadPoolExecutor(max_workers=6) as pool:
        observations = list(pool.map(construct, range(6)))
    return dict(initial=initial, observations=observations)


def imports(tmp):
    files = {name: str(Path(module.__file__).resolve()) for name, module in sys.modules.items()
             if name.startswith("btc_quant_agent") and getattr(module, "__file__", None)}
    check(files and all(Path(file).is_relative_to(SRC.resolve()) for file in files.values()), "foreign project runtime import")
    return files


probe("IDENTITY_runtime_imports", imports)
for timeout in (10000, 1739, 1):
    probe(f"V1_settings_{timeout}", lambda tmp, timeout=timeout: v1_pragmas(tmp, timeout))
for mode in ("enable_error", "readback_zero", "read_error", "read_missing"):
    probe("V1_fail_closed_" + mode, lambda tmp, mode=mode: v1_failure(tmp, mode))
probe("V2_blank_pending", lambda tmp: v2(tmp, {}))
for field, value in dict(state="DONE", analysis_completed=1, dispatch_authority_json="{}",
                        dispatch_authority_hash="b" * 64, analysis_admission_hash="c" * 64,
                        position_case_id="forged", position_case_hash="d" * 64,
                        position_case_json="{}", case_hash="e" * 64,
                        retry_count=1, lease_token="forged-lease", lease_expires_at_ms=NOW + 1000).items():
    probe("V2_reject_" + field, lambda tmp, field=field, value=value: v2(tmp, {field: value}))
for form in ("INSERT OR REPLACE", "REPLACE"):
    probe("V2_new_terminal_" + form, lambda tmp, form=form: v2(tmp, {"state": "DONE", "analysis_completed": 1}, form))
for phase in ("frozen", "admitted", "completed"):
    for form in ("INSERT OR REPLACE", "REPLACE"):
        for payload in ("blank", "fabricated_terminal"):
            for collision in ("primary", "unique"):
                name = "V3_" + "_".join((phase, form, payload, collision))
                probe(name, lambda tmp, phase=phase, form=form, payload=payload, collision=collision:
                      v3(tmp, phase, form, payload, collision))
for operation in ("upsert_authority", "upsert_completion", "completion", "marker_only", "done_only", "delete",
                  "authority_event_hash", "authority_symbol", "authority_dispatch_authority_json",
                  "authority_dispatch_authority_hash", "authority_analysis_admission_hash",
                  "authority_position_case_id", "authority_position_case_hash",
                  "authority_position_case_json", "authority_case_hash"):
    probe("V4_" + operation, lambda tmp, operation=operation: v4(tmp, operation))
probe("V5_V6_positive_atomic_terminal_canonical_admission_exact_provider", v5_positive)
probe("V5_terminal_commit_rollback", v5_rollback)
for phase in ("frozen", "admitted", "provider_returned"):
    probe("V5_V6_restart_" + phase, lambda tmp, phase=phase: v5_restart(tmp, phase))
for field in ("lease", "authority_json", "authority_hash", "admission_hash", "event_json", "case_json"):
    probe("V6_terminal_binding_" + field, lambda tmp, field=field: v6_terminal_binding(tmp, field))
for state in ("DONE", "PENDING"):
    probe("V7_historical_" + state, lambda tmp, state=state: v7_legacy(tmp, state))
for initial in ("current", "legacy", "cold"):
    probe("V7_concurrent_" + initial, lambda tmp, initial=initial: v7_concurrent(tmp, initial))
probe("IDENTITY_runtime_imports_final", imports)
summary = dict(authorship="Fresh independent coordinating validator; no committed test/helper imports",
               source_checkout=str(SRC.parent.resolve()), python=sys.version,
               sqlite=sqlite3.sqlite_version, count=len(results),
               passed=sum(r["status"] == "PASS" for r in results),
               failed=sum(r["status"] == "FAIL" for r in results), results=results,
               safety=dict(LIVE_WRITE_AUTHORITY="NONE", REAL_FUNDS_WRITE_COUNT=0,
                           LIVE_APPROVAL_ONLY="NOT_AUTHORIZED", AUTONOMOUS_LIVE="FORBIDDEN",
                           PUBLIC_REST_MUTATION_SURFACES=0))
(OUT / "results.json").write_text(json.dumps(summary, indent=2) + "\n")
print(stable({k: v for k, v in summary.items() if k not in ("results",)}), flush=True)
sys.exit(bool(summary["failed"]))
