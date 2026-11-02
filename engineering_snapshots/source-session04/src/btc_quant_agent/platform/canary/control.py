"""Durable local budgets and per-source integrity, on the existing L23 SQLite store."""

from __future__ import annotations

import json
import time

from ..core import fingerprint, primitive
from ..selection.store import SelectorStore
from .policy import Endpoint, Policy, weight
from .telemetry import NULL, TimedConnection


class CanaryStore(SelectorStore):
    def __init__(self, path, clock_ms=None, *, telemetry=None):
        self.telemetry = telemetry or NULL
        super().__init__(path, clock_ms=clock_ms)
        with self._connect() as db:
            db.executescript("""
              CREATE TABLE IF NOT EXISTS canary_values(key TEXT PRIMARY KEY, value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS canary_budget(id INTEGER PRIMARY KEY, scope TEXT NOT NULL,
                mono_ms INTEGER NOT NULL, amount INTEGER NOT NULL);
              CREATE INDEX IF NOT EXISTS canary_budget_scope ON canary_budget(scope,mono_ms);
              CREATE TABLE IF NOT EXISTS canary_sources(feed TEXT NOT NULL, symbol TEXT NOT NULL,
                value TEXT NOT NULL, PRIMARY KEY(feed,symbol));
              CREATE TABLE IF NOT EXISTS canary_bars(provider TEXT NOT NULL,symbol TEXT NOT NULL,
                interval_ms INTEGER NOT NULL,start_ms INTEGER NOT NULL,end_ms INTEGER NOT NULL,
                value TEXT NOT NULL,PRIMARY KEY(provider,symbol,interval_ms,start_ms));
              CREATE TABLE IF NOT EXISTS canary_captures(id TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)

    def _connect(self):
        if not self.telemetry.enabled:
            return super()._connect()
        started = time.perf_counter_ns()
        connection = super()._connect()
        self.telemetry.observe("sqlite.connect", time.perf_counter_ns() - started)
        self.telemetry.count("sqlite_connections")
        return TimedConnection(connection, self.telemetry) if self.telemetry.enabled else connection

    def get_value(self, key, default=None):
        with self._connect() as db:
            row = db.execute("SELECT value FROM canary_values WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_value(self, key, value):
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO canary_values VALUES (?,?)",
                (key, json.dumps(primitive(value), sort_keys=True)),
            )

    def invalidate_clock_epoch(self, sample, scope_hash):
        """Atomic readiness cancellation with raw stepped time and revision ordering.

        Normal transition wall-order assertions are unchanged. This dedicated
        fault record is ordered by epoch/monotonic sample and SQLite revision;
        it never substitutes the prior wall time for the newly observed wall.
        Actual execution/position records and capacity reservations are untouched.
        """
        from .clock_domain import sample_reason

        reason = sample_reason(sample)
        if reason is None:
            raise ValueError("CLOCK_EPOCH_STILL_QUALIFIED")
        fault = {
            "reason": reason,
            "sample": sample,
            "scope_hash": scope_hash,
            "actual_orders_cancelled": False,
            "positions_closed": False,
        }
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM canary_values WHERE key='clock_epoch_invalidation'").fetchone():
                return
            for symbol, _, encoded in db.execute(
                "SELECT symbol,cutoff,evidence FROM selector_states"
            ).fetchall():
                state = json.loads(encoded)
                state.update(
                    state="UNKNOWN",
                    pending="UNKNOWN",
                    count=0,
                    failures=0,
                    reason="CLOCK_EPOCH_INVALID",
                    clock_fault=fault,
                )
                db.execute(
                    "UPDATE selector_states SET evidence=? WHERE symbol=?",
                    (json.dumps(state, sort_keys=True), symbol),
                )
            for id, encoded_a, encoded_s, revision in db.execute(
                "SELECT id,anchors,state,revision FROM selector_episodes"
            ).fetchall():
                a, state = json.loads(encoded_a), json.loads(encoded_s)
                if a.get("clock_epoch_id") != sample.get("epoch_id") or state["status"] in (
                    "CANCELLED",
                    "EXPIRED",
                ):
                    continue
                state.update(
                    status="CANCELLED",
                    reasons=["CLOCK_EPOCH_INVALID", reason],
                    clock_fault=fault,
                    execution_reconciliation_required=state.get("execution") != "NOT_REPORTED",
                )
                revision += 1
                db.execute(
                    "UPDATE selector_episodes SET state=?,revision=?,updated_ts=? WHERE id=?",
                    (json.dumps(state, sort_keys=True), revision, sample["wall_ms"], id),
                )
                db.execute(
                    "INSERT INTO selector_transitions VALUES (?,?,?)",
                    (
                        id,
                        revision,
                        json.dumps(
                            {
                                "decision_ts": sample["wall_ms"],
                                "clock_sample": sample,
                                "ordering": "EPOCH_MONOTONIC_AND_REVISION",
                                "state": state,
                            },
                            sort_keys=True,
                        ),
                    ),
                )
            db.execute(
                "INSERT INTO canary_values VALUES (?,?)",
                ("clock_epoch_invalidation", json.dumps(fault, sort_keys=True)),
            )

    def source(self, feed, symbol):
        with self._connect() as db:
            row = db.execute(
                "SELECT value FROM canary_sources WHERE feed=? AND symbol=?", (feed, symbol)
            ).fetchone()
        return (
            json.loads(row[0])
            if row
            else {
                "status": "NEW",
                "epoch": 0,
                "last_sequence": None,
                "last_event_ms": None,
                "last_payload_hash": None,
                "last_receive_ms": None,
                "distinct_recovery": 0,
                "gap": False,
                "reason": "NO_OBSERVATION",
                "instrument_hash": None,
            }
        )

    def fault(self, feed, symbol, reason):
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT value FROM canary_sources WHERE feed=? AND symbol=?", (feed, symbol)
            ).fetchone()
            state = json.loads(row[0]) if row else self.source(feed, symbol)
            state.update(status="DEGRADED", distinct_recovery=0, reason=reason)
            db.execute(
                "INSERT OR REPLACE INTO canary_sources VALUES (?,?,?)",
                (feed, symbol, json.dumps(state, sort_keys=True)),
            )
        return state

    def reconnect(self, feed, symbol, now_ms):
        state = self.source(feed, symbol)
        state.update(
            epoch=state["epoch"] + 1,
            status="RECOVERING",
            last_sequence=None,
            distinct_recovery=0,
            gap=True,
            reason="RECONNECT_GAP_REQUIRES_EVIDENCE",
            fragment_start_ms=now_ms,
            recovery_native_times=[],
        )
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO canary_sources VALUES (?,?,?)",
                (feed, symbol, json.dumps(state, sort_keys=True)),
            )
        return state

    def accept(
        self,
        feed,
        symbol,
        *,
        epoch,
        sequence,
        native_ms,
        payload_hash,
        receive_ms,
        instrument_hash,
        recovery_required=2,
    ):
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT value FROM canary_sources WHERE feed=? AND symbol=?", (feed, symbol)
            ).fetchone()
            state = json.loads(row[0]) if row else self.source(feed, symbol)
            if epoch != state["epoch"]:
                return state, "SOURCE_EPOCH_MISMATCH"
            if state["instrument_hash"] not in (None, instrument_hash):
                state.update(
                    status="DEGRADED", distinct_recovery=0, reason="CONTRACT_CHANGE_REVALIDATION_REQUIRED"
                )
                db.execute(
                    "INSERT OR REPLACE INTO canary_sources VALUES (?,?,?)",
                    (feed, symbol, json.dumps(state, sort_keys=True)),
                )
                return state, state["reason"]
            prior = state["last_sequence"]
            last_ts = state["last_event_ms"]
            if (sequence is not None and sequence == prior) or (sequence is None and native_ms == last_ts):
                if payload_hash == state["last_payload_hash"]:
                    return state, "DUPLICATE_DISCARDED"
                state.update(status="DEGRADED", distinct_recovery=0, reason="SOURCE_EQUIVOCATION")
                db.execute(
                    "INSERT OR REPLACE INTO canary_sources VALUES (?,?,?)",
                    (feed, symbol, json.dumps(state, sort_keys=True)),
                )
                return state, "SOURCE_EQUIVOCATION"
            if (sequence is not None and prior is not None and sequence < prior) or (
                last_ts is not None and native_ms < last_ts
            ):
                return state, "OUT_OF_ORDER_DISCARDED"
            if state["last_receive_ms"] is not None and receive_ms < state["last_receive_ms"]:
                return state, "RECEIVE_TIME_REGRESSION"
            # BookTicker IDs are monotone, not necessarily contiguous depth sequence numbers.
            count = state["distinct_recovery"] + 1
            gap = state["gap"]
            observed = list(state.get("recovery_native_times", []))
            if native_ms not in observed:
                observed.append(native_ms)
            state.update(
                last_sequence=sequence,
                last_event_ms=native_ms,
                last_payload_hash=payload_hash,
                last_receive_ms=receive_ms,
                instrument_hash=instrument_hash,
                distinct_recovery=count,
                gap=gap,
                recovery_native_times=observed[-recovery_required:],
                status="OFFLINE_STABLE" if count >= recovery_required and not gap else "RECOVERING",
                reason=None if count >= recovery_required and not gap else "RECOVERY_CONFIRMATION_PENDING",
            )
            db.execute(
                "INSERT OR REPLACE INTO canary_sources VALUES (?,?,?)",
                (feed, symbol, json.dumps(state, sort_keys=True)),
            )
        return state, None

    def recover_quote_fragment(self, feed, symbol, required=2):
        state = self.source(feed, symbol)
        times = state.get("recovery_native_times", [])
        if (
            not state.get("gap")
            or state.get("gap_range")
            or len(times) < required
            or min(times) < state.get("fragment_start_ms", 10**18)
        ):
            raise ValueError("POST_GAP_DISTINCT_QUOTE_EVIDENCE_INSUFFICIENT")
        state.update(
            gap=False,
            status="OFFLINE_STABLE",
            reason="NEW_FRAGMENT_ONLY_NOT_GAP_RECONSTRUCTION",
            earlier_fragment_continuity=False,
        )
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO canary_sources VALUES (?,?,?)",
                (feed, symbol, json.dumps(state, sort_keys=True)),
            )
        return state

    def mark_bar_gap(self, feed, symbol, provider, interval_ms, start_ms, end_ms):
        state = self.source(feed, symbol)
        prior = state.get("gap_range")
        if prior:
            if prior[:2] != [provider, interval_ms]:
                raise ValueError("GAP_IDENTITY_CHANGE")
            start_ms, end_ms = min(start_ms, prior[2]), max(end_ms, prior[3])
        state.update(
            gap=True,
            status="RECOVERING",
            distinct_recovery=0,
            gap_range=[provider, interval_ms, start_ms, end_ms],
            reason="CLOSED_BAR_GAP",
        )
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO canary_sources VALUES (?,?,?)",
                (feed, symbol, json.dumps(state, sort_keys=True)),
            )

    def repair_bar_gap(self, feed, symbol):
        state = self.source(feed, symbol)
        if not state.get("gap_range"):
            raise ValueError("NO_DECLARED_BAR_GAP")
        provider, interval, start, end = state["gap_range"]
        with self._connect() as db:
            rows = db.execute(
                "SELECT start_ms,end_ms FROM canary_bars WHERE provider=? AND symbol=? AND interval_ms=? AND start_ms>=? AND end_ms<=? ORDER BY start_ms",
                (provider, symbol, interval, start, end),
            ).fetchall()
        if (
            not rows
            or rows[0][0] != start
            or rows[-1][1] != end
            or any(b[0] != a[1] for a, b in zip(rows, rows[1:]))
        ):
            raise ValueError("ACTUAL_CLOSED_BAR_REPAIR_EVIDENCE_MISSING")
        state.update(
            gap=False,
            gap_range=None,
            status="RECOVERING",
            distinct_recovery=0,
            reason="REPAIR_RECEIVED_LATER_NOT_RETROACTIVE_L23_READINESS",
        )
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO canary_sources VALUES (?,?,?)",
                (feed, symbol, json.dumps(state, sort_keys=True)),
            )
        return state

    def revalidate_contract(self, feed, symbol, instrument_hash, evidence_id, now_ms):
        evidence = self.get_value("instrument:" + evidence_id) if evidence_id else None
        if (
            not evidence
            or evidence.get("instrument_hash") != instrument_hash
            or evidence.get("symbol") != symbol
            or evidence.get("provider") != feed.split("_")[0]
            or not 0 <= now_ms - evidence.get("available_ms", -(10**15)) <= 3_600_000
        ):
            raise ValueError("FRESH_INSTRUMENT_EVIDENCE_REQUIRED")
        state = self.source(feed, symbol)
        state.update(
            instrument_hash=instrument_hash,
            distinct_recovery=0,
            status="RECOVERING",
            reason="CONTRACT_RECONFIRMATION_PENDING",
            last_sequence=None,
            last_event_ms=None,
        )
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO canary_sources VALUES (?,?,?)",
                (feed, symbol, json.dumps(state, sort_keys=True)),
            )

    def commit_capture(self, value):
        identity = fingerprint(value)
        with self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO canary_captures VALUES (?,?)",
                (identity, json.dumps(primitive(value), sort_keys=True, allow_nan=False)),
            )
        return identity

    def record_bar(self, bar):
        encoded = json.dumps(primitive(bar), sort_keys=True, allow_nan=False)
        key = (bar.spec.provider, bar.spec.symbol, bar.interval_ms, bar.start)
        with self._connect() as db:
            old = db.execute(
                "SELECT value FROM canary_bars WHERE provider=? AND symbol=? AND interval_ms=? AND start_ms=?",
                key,
            ).fetchone()
            if old:
                previous = json.loads(old[0])
                current = json.loads(encoded)

                def values(v):
                    return [
                        v["spec"],
                        v["start"],
                        v["end"],
                        v["interval_ms"],
                        [
                            (o["field"], o["value"], o["symbol"], o["interval_ms"], o["unit"])
                            for o in v["fields"]
                        ],
                    ]

                if values(previous) != values(current):
                    raise ValueError("IMMUTABLE_CLOSED_BAR_CONFLICT")
                return  # Keep the FIRST actual availability. A later receipt cannot backdate it.
            db.execute("INSERT OR IGNORE INTO canary_bars VALUES (?,?,?,?,?,?)", (*key, bar.end, encoded))


class CircuitOpen(ValueError):
    pass


class BudgetGuard:
    def __init__(self, store: CanaryStore, policy: Policy, *, telemetry=None):
        self.store, self.policy = store, policy
        self.telemetry = telemetry or getattr(store, "telemetry", NULL)

    def charge(self, scopes: tuple[tuple[str, int, int, int], ...], mono_ms: int):
        with self.telemetry.measure("budget.charge"):
            return self._charge(scopes, mono_ms)

    def _charge(self, scopes, mono_ms):
        """All rolling-window claims are atomic across processes. Scope/window/cap/amount."""
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM canary_values WHERE key='circuit'").fetchone():
                raise CircuitOpen("PERSISTED_CIRCUIT_OPEN")
            row = db.execute("SELECT value FROM canary_values WHERE key='budget_clock'").fetchone()
            if row and mono_ms < json.loads(row[0]):
                raise CircuitOpen("BUDGET_MONOTONIC_CLOCK_REGRESSION")
            for scope, window, cap, amount in scopes:
                if cap <= 0 or amount < 0:
                    raise CircuitOpen("BUDGET_UNKNOWN_OR_INVALID")
                used = db.execute(
                    "SELECT COALESCE(SUM(amount),0) FROM canary_budget WHERE scope=? AND mono_ms>?",
                    (scope, mono_ms - window),
                ).fetchone()[0]
                if used + amount > cap:
                    self.telemetry.stop("budget.rolling_window", "HARD_BUDGET_BREACH:" + scope)
                    db.execute(
                        "INSERT OR REPLACE INTO canary_values VALUES (?,?)",
                        ("circuit", json.dumps({"reason": "HARD_BUDGET_BREACH", "scope": scope})),
                    )
                    # Commit the circuit before reporting the failure; no request is emitted.
                    db.commit()
                    raise CircuitOpen("HARD_BUDGET_BREACH:" + scope)
            db.executemany(
                "INSERT INTO canary_budget(scope,mono_ms,amount) VALUES (?,?,?)",
                [(scope, mono_ms, amount) for scope, _, _, amount in scopes],
            )
            db.execute(
                "INSERT OR REPLACE INTO canary_values VALUES ('budget_clock',?)", (json.dumps(mono_ms),)
            )
            db.execute("DELETE FROM canary_budget WHERE mono_ms<?", (mono_ms - 3_600_000,))

    def precheck(self, mono_ms):
        with self.telemetry.measure("budget.precheck"):
            circuit = self.store.get_value("circuit")
            if circuit:
                raise CircuitOpen(circuit["reason"])
            if mono_ms < self.store.get_value("next_allowed_mono", 0):
                raise CircuitOpen("BOUNDED_BACKOFF_ACTIVE")

    def request(self, endpoint: Endpoint, params: dict, mono_ms: int, *, retry=False):
        self.precheck(mono_ms)
        if endpoint.transport != "REST":
            raise ValueError("REST_REQUEST_EXPECTED")
        amount = weight(endpoint, params)
        scopes = [("IP:" + endpoint.provider, 60_000, self.policy.ip_weight_per_minute, amount)]
        primary_cap = self.policy.ip_weight_per_minute - self.policy.retry_weight_reserve_per_minute
        scopes.append(
            (
                "RETRY" if retry else "PRIMARY",
                60_000,
                self.policy.retry_weight_reserve_per_minute if retry else primary_cap,
                amount,
            )
        )
        rate = endpoint.documented_rate_limits
        # Documentation caps are exercised only with fabricated requests. Unknown cap blocks use.
        cap, seconds = rate.get("requests"), rate.get("window_seconds")
        if cap is None or seconds is None:
            raise CircuitOpen("ENDPOINT_RATE_CEILING_UNKNOWN")
        scopes.append(("ENDPOINT:" + endpoint.id, int(seconds * 1000), cap, 1))
        own_cap = self.policy.endpoint_calls_per_minute.get(endpoint.id)
        if own_cap is None:
            raise CircuitOpen("ENDPOINT_LOCAL_HARD_CAP_UNKNOWN")
        scopes.append(("LOCAL_ENDPOINT:" + endpoint.id, 60_000, own_cap, 1))
        if endpoint.id.endswith("funding_info"):
            scopes.append(("BINANCE_SHARED_FUNDING_5M", 300_000, 500, 1))
        self.charge(tuple(scopes), mono_ms)
        return {"endpoint": endpoint.id, "weight": amount, "retry": retry, "exposure": "SYNTHETIC"}

    def websocket_control(self, endpoint: Endpoint, mono_ms: int, *, subscriptions=0, reconnect=False):
        self.precheck(mono_ms)
        if subscriptions > self.policy.max_subscriptions:
            self.store.set_value("circuit", {"reason": "SUBSCRIPTION_CAP_EXCEEDED"})
            raise CircuitOpen("SUBSCRIPTION_CAP_EXCEEDED")
        cap = endpoint.websocket.get("incoming_controls_per_second")
        if cap is None:
            raise CircuitOpen("WS_CONTROL_CAP_UNKNOWN")
        scopes = [("WS_CONTROL:" + endpoint.provider, 1000, min(cap, self.policy.controls_per_second), 1)]
        if endpoint.provider == "okx":
            scopes.append(("OKX_SUBSCRIPTIONS_HOUR", 3_600_000, 480, 1))
        if reconnect:
            scopes.append(("WS_RECONNECT_HOUR", 3_600_000, self.policy.max_reconnects_per_hour, 1))
        self.charge(tuple(scopes), mono_ms)

    def data_message(self, mono_ms: int, pending: int):
        self.telemetry.pending(pending)
        self.precheck(mono_ms)
        if pending >= self.policy.max_pending_records:
            self.telemetry.stop("budget.pending_precheck", "BACKPRESSURE_BLOCKED", pending)
            self.store.set_value("circuit", {"reason": "BACKPRESSURE_BLOCKED"})
            raise CircuitOpen("BACKPRESSURE_BLOCKED")
        self.charge((("WS_DATA", 1000, self.policy.max_messages_per_second, 1),), mono_ms)
        self.telemetry.count("budget_ws_charged")

    def connection_open(self, connection_id: str, endpoint: Endpoint, mono_ms: int):
        self.precheck(mono_ms)
        self.websocket_control(endpoint, mono_ms, reconnect=True)
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT value FROM canary_values WHERE key='connections'").fetchone()
            connections = json.loads(row[0]) if row else {}
            if connection_id not in connections and len(connections) >= self.policy.max_connections:
                raise CircuitOpen("CONNECTION_CAP_EXCEEDED")
            connections[connection_id] = {"opened_mono": mono_ms, "endpoint": endpoint.id}
            db.execute(
                "INSERT OR REPLACE INTO canary_values VALUES ('connections',?)", (json.dumps(connections),)
            )

    def connection_close(self, connection_id):
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT value FROM canary_values WHERE key='connections'").fetchone()
            connections = json.loads(row[0]) if row else {}
            connections.pop(connection_id, None)
            row = db.execute("SELECT value FROM canary_values WHERE key='subscriptions'").fetchone()
            subscriptions = json.loads(row[0]) if row else {}
            subscriptions.pop(connection_id, None)
            db.execute(
                "INSERT OR REPLACE INTO canary_values VALUES ('subscriptions',?)",
                (json.dumps(subscriptions),),
            )
            db.execute(
                "INSERT OR REPLACE INTO canary_values VALUES ('connections',?)", (json.dumps(connections),)
            )

    def subscription_set(self, connection_id, endpoint: Endpoint, streams: tuple[str, ...], mono_ms):
        self.websocket_control(endpoint, mono_ms, subscriptions=len(streams))
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT value FROM canary_values WHERE key='subscriptions'").fetchone()
            subscribed = json.loads(row[0]) if row else {}
            subscribed[connection_id] = sorted(set(streams))
            if sum(len(v) for v in subscribed.values()) > self.policy.max_subscriptions:
                raise CircuitOpen("AGGREGATE_SUBSCRIPTION_CAP_EXCEEDED")
            db.execute(
                "INSERT OR REPLACE INTO canary_values VALUES ('subscriptions',?)", (json.dumps(subscribed),)
            )

    def response(self, status: int, mono_ms: int, *, venue_code: str | None = None, retry_after_ms=0):
        if status in {429, 418} or venue_code in {"50011", "50061"}:
            self.store.set_value(
                "circuit",
                {
                    "reason": "RATE_LIMIT_CIRCUIT_OPEN",
                    "http_status": status,
                    "venue_code": venue_code,
                    "no_automatic_retry": True,
                },
            )
            raise CircuitOpen("RATE_LIMIT_CIRCUIT_OPEN")
        if status in {408, 500, 502, 503, 504}:
            attempt = self.store.get_value("retry_attempt", 0) + 1
            if attempt > self.policy.max_retries or retry_after_ms > self.policy.max_backoff_ms:
                self.store.set_value("circuit", {"reason": "RETRY_EXHAUSTED_OR_UNBOUNDED_BACKOFF"})
                raise CircuitOpen("RETRY_EXHAUSTED_OR_UNBOUNDED_BACKOFF")
            backoff = min(self.policy.max_backoff_ms, max(1000 * 2 ** (attempt - 1), retry_after_ms))
            self.store.set_value("retry_attempt", attempt)
            self.store.set_value("next_allowed_mono", mono_ms + backoff)
            return {"retry_not_before_mono": mono_ms + backoff, "attempt": attempt}
        return {"retry": False}

    def heartbeat(self, connection_id, now_mono, *, last_ping_mono, last_pong_mono, endpoint):
        """Synthetic liveness only; a pong never repairs a market-data hole."""
        connection = self.store.get_value("connections", {}).get(connection_id)
        if not connection:
            raise CircuitOpen("CONNECTION_NOT_OPEN")
        lifetime = endpoint.websocket.get("connection_lifetime_seconds", 86400) * 1000
        timeout = endpoint.websocket.get("pong_timeout_seconds", 600) * 1000
        if now_mono - connection["opened_mono"] >= lifetime or (
            last_ping_mono > last_pong_mono and now_mono - last_ping_mono >= timeout
        ):
            self.connection_close(connection_id)
            raise CircuitOpen("CONNECTION_LIFETIME_OR_HEARTBEAT_EXPIRED")
        return {"liveness": "FABRICATED_HEARTBEAT_ONLY", "gap_repaired": False}
