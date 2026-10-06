"""Deterministic Position Supervisor for Live V1."""

from __future__ import annotations

import json
import secrets
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..account_watch.models import AccountSnapshotV1
from ..decision.models import CasePackageV1, canonical_json, content_hash
from ..live_db import connection, serialized_initializer
from .models import (
    PositionEventV1,
    PositionObservationV1,
    SupervisorPolicyV1,
    position_authority_key,
)


@dataclass(frozen=True)
class _AnalysisAdmission:
    authority_json: str
    authority_hash: str
    admission_hash: str
    case_json: str
    event_json: str
    provider_completed: bool


def _dispatch_authority(
    event: PositionEventV1, case: CasePackageV1, lease_token: str,
) -> dict[str, Any]:
    return {
        "schema_version": "POSITION_DISPATCH_AUTHORITY_V1",
        **{name: getattr(event, name) for name in (
            "event_id", "event_hash", "symbol", "environment", "credential_namespace",
            "account_id", "position_side", "position_authority_key",
        )},
        "position_case_id": case.case_id,
        "position_case_hash": case.case_hash,
        "lease_token": lease_token,
    }


def _admission_hash(authority_hash: str) -> str:
    return content_hash({
        "schema_version": "POSITION_ANALYSIS_ADMISSION_V1",
        "dispatch_authority_hash": authority_hash,
    })


def _unbound_legacy_lifecycle(
    db: sqlite3.Connection, environment: str, credential_namespace: str,
    account_id: str, symbol: str, position_side: str,
) -> bool:
    if environment != "DRY_RUN" or credential_namespace != "NONE":
        return False
    row = db.execute(
        "SELECT 1 FROM live_position_lifecycle old "
        "WHERE old.account_id=? AND old.symbol=? AND old.position_side=? "
        "AND NOT EXISTS (SELECT 1 FROM live_position_lifecycle_v2 scoped "
        "WHERE scoped.environment=? AND scoped.credential_namespace=? "
        "AND scoped.account_id=old.account_id AND scoped.symbol=old.symbol "
        "AND scoped.position_side=old.position_side) LIMIT 1",
        (account_id, symbol, position_side, environment, credential_namespace),
    ).fetchone()
    return row is not None


def position_case_from_event(
    base: CasePackageV1, event: PositionEventV1, now_ms: int | None = None
) -> CasePackageV1:
    ttl = max(60_000, base.expires_at_ms - base.created_at_ms)
    event_time = event.observed_at_ms
    return CasePackageV1.build(
        case_id=f"pos-{event.event_id}",
        created_at_ms=event_time,
        observed_at_ms=event_time,
        expires_at_ms=event_time + ttl,
        symbol=base.symbol,
        trigger=event.trigger,
        strategy=base.strategy,
        strategy_version=base.strategy_version,
        direction=base.direction,
        evidence_id=base.evidence_id,
        snapshot_hash=base.snapshot_hash,
        signal_identity=base.signal_identity,
        source="POSITION_SUPERVISOR",
        base_case_hash=base.case_hash,
        position_event_hash=event.event_hash,
        price=base.price,
        entry_low=base.entry_low,
        entry_high=base.entry_high,
        stop_loss=base.stop_loss,
        take_profit_1=base.take_profit_1,
        take_profit_2=base.take_profit_2,
        atr=base.atr,
        data_quality=base.data_quality,
        spread_bps=base.spread_bps,
        liquidity_usdt=base.liquidity_usdt,
    )


REQUIRED_R8_GUARDS: tuple[str, ...] = (
    "trg_live_position_events_immutable_update",
    "trg_live_position_events_immutable_delete",
    "trg_live_position_dispatches_immutable_authority",
    "trg_live_position_dispatch_blank_insert",
    "trg_live_position_dispatch_admission_immutable",
    "trg_live_position_analysis_completion_guard",
    "trg_live_position_dispatch_done_requires_completion",
    "trg_live_position_dispatches_immutable_delete",
)


class PositionSupervisor:
    def __init__(
        self,
        path: str | Path,
        analysis_service: Any = None,
        fresh_market_case: Callable[[str], CasePackageV1] | None = None,
        policy: SupervisorPolicyV1 | None = None,
        lease_clock_ms: Callable[[], int] | None = None,
    ) -> None:
        self.path = Path(path)
        self.analysis_service = analysis_service
        self.fresh_market_case = fresh_market_case
        self.policy = policy or SupervisorPolicyV1()
        self.lease_clock_ms = lease_clock_ms

        with serialized_initializer(self.path):
            self._init_schema()
            self.assert_guards_installed()

    def assert_guards_installed(self) -> None:
        with connection(self.path) as db:
            triggers = {
                r[0] for r in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger'"
                ).fetchall()
            }
        missing = [g for g in REQUIRED_R8_GUARDS if g not in triggers]
        if missing:
            raise RuntimeError(f"R8_GUARDS_MISSING: {missing}")

    def _init_schema(self) -> None:
        with connection(self.path) as db:
            cols = [
                col["name"]
                for col in db.execute("PRAGMA table_info(live_position_case_dispatches)").fetchall()
            ]
            if cols:
                if "position_case_id" not in cols:
                    db.execute(
                        "ALTER TABLE live_position_case_dispatches ADD COLUMN position_case_id TEXT NOT NULL DEFAULT ''"
                    )
                if "position_case_hash" not in cols:
                    db.execute(
                        "ALTER TABLE live_position_case_dispatches ADD COLUMN position_case_hash TEXT NOT NULL DEFAULT ''"
                    )
                if "position_case_json" not in cols:
                    db.execute(
                        "ALTER TABLE live_position_case_dispatches ADD COLUMN position_case_json TEXT NOT NULL DEFAULT ''"
                    )
                if "case_hash" not in cols:
                    db.execute(
                        "ALTER TABLE live_position_case_dispatches ADD COLUMN case_hash TEXT NOT NULL DEFAULT ''"
                    )
                db.execute(
                    "UPDATE live_position_case_dispatches SET position_case_hash = case_hash "
                    "WHERE position_case_hash = '' AND case_hash != ''"
                    + (" AND analysis_admission_hash = ''"
                       if "analysis_admission_hash" in cols else "")
                )

            db.executescript("""
                CREATE TABLE IF NOT EXISTS live_position_events (
                    event_id TEXT PRIMARY KEY,
                    event_hash TEXT NOT NULL UNIQUE,
                    trigger TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    source_hash TEXT NOT NULL,
                    observed_at_ms INTEGER NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_live_position_events_lookup
                    ON live_position_events(symbol, trigger, observed_at_ms DESC);
                CREATE INDEX IF NOT EXISTS idx_live_position_events_source
                    ON live_position_events(source_hash);
                CREATE TABLE IF NOT EXISTS live_position_active (
                    symbol TEXT PRIMARY KEY,
                    is_open INTEGER NOT NULL DEFAULT 0,
                    last_opened_at_ms INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS live_position_lifecycle (
                    account_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    position_side TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    is_open INTEGER NOT NULL,
                    last_transition TEXT NOT NULL,
                    last_transition_at_ms INTEGER NOT NULL,
                    observed_at_ms INTEGER NOT NULL,
                    source_hash TEXT NOT NULL,
                    PRIMARY KEY (account_id, symbol, position_side)
                );
                CREATE TABLE IF NOT EXISTS live_position_lifecycle_v2 (
                    environment TEXT NOT NULL,
                    credential_namespace TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    position_side TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    is_open INTEGER NOT NULL,
                    last_transition TEXT NOT NULL,
                    last_transition_at_ms INTEGER NOT NULL,
                    observed_at_ms INTEGER NOT NULL,
                    source_hash TEXT NOT NULL,
                    PRIMARY KEY (environment, credential_namespace, account_id, symbol, position_side)
                );
                CREATE TABLE IF NOT EXISTS live_position_observed_sources (
                    source_hash TEXT PRIMARY KEY
                );
                CREATE TABLE IF NOT EXISTS live_position_case_dispatches (
                    event_id TEXT PRIMARY KEY,
                    event_hash TEXT NOT NULL UNIQUE,
                    position_case_id TEXT NOT NULL DEFAULT '',
                    position_case_hash TEXT NOT NULL DEFAULT '',
                    position_case_json TEXT NOT NULL DEFAULT '',
                    case_hash TEXT NOT NULL DEFAULT '',
                    dispatch_authority_json TEXT NOT NULL DEFAULT '',
                    dispatch_authority_hash TEXT NOT NULL DEFAULT '',
                    analysis_admission_hash TEXT NOT NULL DEFAULT '',
                    analysis_completed INTEGER NOT NULL DEFAULT 0 CHECK(analysis_completed IN (0, 1)),
                    symbol TEXT NOT NULL,
                    state TEXT NOT NULL,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    lease_token TEXT,
                    lease_expires_at_ms INTEGER NOT NULL DEFAULT 0,
                    created_at_ms INTEGER NOT NULL,
                    updated_at_ms INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_dispatches_state
                    ON live_position_case_dispatches(state, lease_expires_at_ms);
            """)
            # Serialize inspection and additive migrations across concurrent starters.
            db.execute("BEGIN IMMEDIATE")
            dispatch_columns = {
                col["name"] for col in db.execute("PRAGMA table_info(live_position_case_dispatches)").fetchall()
            }
            for name, definition in (
                ("dispatch_authority_json", "TEXT NOT NULL DEFAULT ''"),
                ("dispatch_authority_hash", "TEXT NOT NULL DEFAULT ''"),
                ("analysis_admission_hash", "TEXT NOT NULL DEFAULT ''"),
                ("analysis_completed", "INTEGER NOT NULL DEFAULT 0 CHECK(analysis_completed IN (0, 1))"),
            ):
                if name not in dispatch_columns:
                    db.execute(f"ALTER TABLE live_position_case_dispatches ADD COLUMN {name} {definition}")

            # Existing unscoped event rows remain legacy authority and cannot
            # suppress events from any current account/environment.
            event_columns = {
                col["name"] for col in db.execute("PRAGMA table_info(live_position_events)").fetchall()
            }
            for name in ("environment", "credential_namespace", "account_id",
                         "position_side", "position_authority_key"):
                if name not in event_columns:
                    db.execute(f"ALTER TABLE live_position_events ADD COLUMN {name} TEXT")
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_live_position_events_authority "
                "ON live_position_events(position_authority_key, trigger, observed_at_ms DESC)"
            )
            db.commit()

            db.executescript("""
                CREATE TRIGGER IF NOT EXISTS trg_live_position_events_immutable_update
                BEFORE UPDATE ON live_position_events
                FOR EACH ROW
                BEGIN
                    SELECT RAISE(ABORT, 'POSITION_EVENT_IMMUTABLE_UPDATE_BLOCKED')
                    WHERE OLD.event_id != NEW.event_id
                       OR OLD.event_hash != NEW.event_hash
                       OR OLD.symbol != NEW.symbol
                       OR OLD.trigger != NEW.trigger
                       OR OLD.source_hash != NEW.source_hash
                       OR OLD.observed_at_ms != NEW.observed_at_ms
                       OR OLD.payload != NEW.payload
                       OR OLD.environment IS NOT NEW.environment
                       OR OLD.credential_namespace IS NOT NEW.credential_namespace
                       OR OLD.account_id IS NOT NEW.account_id
                       OR OLD.position_side IS NOT NEW.position_side
                       OR OLD.position_authority_key IS NOT NEW.position_authority_key;
                END;

                CREATE TRIGGER IF NOT EXISTS trg_live_position_events_immutable_delete
                BEFORE DELETE ON live_position_events
                FOR EACH ROW
                BEGIN
                    SELECT RAISE(ABORT, 'POSITION_EVENT_IMMUTABLE_DELETE_BLOCKED');
                END;

                CREATE TRIGGER IF NOT EXISTS trg_live_position_dispatches_immutable_authority
                BEFORE UPDATE ON live_position_case_dispatches
                FOR EACH ROW
                BEGIN
                    SELECT RAISE(ABORT, 'DISPATCH_AUTHORITY_IMMUTABLE')
                    WHERE OLD.event_id != NEW.event_id
                       OR OLD.event_hash != NEW.event_hash
                       OR OLD.symbol != NEW.symbol;
                END;

                CREATE TRIGGER IF NOT EXISTS trg_live_position_dispatch_blank_insert
                BEFORE INSERT ON live_position_case_dispatches
                FOR EACH ROW
                BEGIN
                    SELECT RAISE(ABORT, 'DISPATCH_INSERT_REQUIRES_BLANK_PENDING')
                    WHERE NEW.state != 'PENDING'
                       OR NEW.analysis_completed != 0
                       OR NEW.dispatch_authority_json != ''
                       OR NEW.dispatch_authority_hash != ''
                       OR NEW.analysis_admission_hash != ''
                       OR NEW.position_case_id != ''
                       OR NEW.position_case_hash != ''
                       OR NEW.position_case_json != ''
                       OR NEW.case_hash != ''
                       OR NEW.retry_count != 0
                       OR NEW.lease_token IS NOT NULL
                       OR NEW.lease_expires_at_ms != 0;
                END;

                CREATE TRIGGER IF NOT EXISTS trg_live_position_dispatch_admission_immutable
                BEFORE UPDATE ON live_position_case_dispatches
                FOR EACH ROW
                BEGIN
                    SELECT RAISE(ABORT, 'DISPATCH_ADMISSION_IMMUTABLE')
                    WHERE (OLD.analysis_admission_hash != '' OR OLD.dispatch_authority_hash != '')
                      AND (OLD.dispatch_authority_json IS NOT NEW.dispatch_authority_json
                        OR OLD.dispatch_authority_hash IS NOT NEW.dispatch_authority_hash
                        OR OLD.analysis_admission_hash IS NOT NEW.analysis_admission_hash
                        OR OLD.position_case_id IS NOT NEW.position_case_id
                        OR OLD.position_case_hash IS NOT NEW.position_case_hash
                        OR OLD.position_case_json IS NOT NEW.position_case_json
                        OR OLD.case_hash IS NOT NEW.case_hash);
                    SELECT RAISE(ABORT, 'ANALYSIS_COMPLETION_IMMUTABLE')
                    WHERE OLD.analysis_completed = 1 AND NEW.analysis_completed IS NOT 1;
                END;

                CREATE TRIGGER IF NOT EXISTS trg_live_position_dispatch_done_requires_completion
                BEFORE UPDATE ON live_position_case_dispatches
                FOR EACH ROW
                BEGIN
                    SELECT RAISE(ABORT, 'DONE_REQUIRES_ANALYSIS_COMPLETION')
                    WHERE OLD.state != 'DONE' AND NEW.state = 'DONE'
                      AND NEW.analysis_completed != 1;
                END;

                CREATE TRIGGER IF NOT EXISTS trg_live_position_analysis_completion_guard
                BEFORE UPDATE OF analysis_completed ON live_position_case_dispatches
                FOR EACH ROW WHEN OLD.analysis_completed = 0 AND NEW.analysis_completed = 1
                BEGIN
                    SELECT RAISE(ABORT, 'ANALYSIS_COMPLETION_REQUIRES_TERMINAL_AUTHORITY')
                    WHERE OLD.state != 'DISPATCHING' OR NEW.state != 'DONE'
                       OR NEW.lease_token IS NOT NULL OR NEW.lease_expires_at_ms != 0
                       OR position_analysis_completion_authorized(
                            OLD.analysis_admission_hash, OLD.dispatch_authority_hash,
                            OLD.lease_token, OLD.case_hash) != 1;
                END;

                CREATE TRIGGER IF NOT EXISTS trg_live_position_dispatches_immutable_delete
                BEFORE DELETE ON live_position_case_dispatches
                FOR EACH ROW
                BEGIN
                    SELECT RAISE(ABORT, 'DISPATCH_DELETE_BLOCKED');
                END;
            """)

    def evaluate(
        self, obs: PositionObservationV1, now_ms: int
    ) -> tuple[PositionEventV1, ...]:
        obs.verify()
        authority_key = position_authority_key(
            obs.environment, obs.credential_namespace, obs.account_id,
            obs.symbol, obs.position_side,
        )
        with connection(self.path) as db:
            db.execute("BEGIN IMMEDIATE")

            # 1. Exact source deduplication
            existing = db.execute(
                "SELECT 1 FROM live_position_observed_sources WHERE source_hash=? LIMIT 1",
                (obs.observation_hash,),
            ).fetchone()
            if existing is not None:
                return ()

            active_row = db.execute(
                "SELECT quantity, is_open, last_transition, last_transition_at_ms, observed_at_ms "
                "FROM live_position_lifecycle_v2 WHERE environment=? AND credential_namespace=? "
                "AND account_id=? AND symbol=? AND position_side=?",
                (obs.environment, obs.credential_namespace, obs.account_id,
                 obs.symbol, obs.position_side),
            ).fetchone()
            if active_row is None and _unbound_legacy_lifecycle(
                db, obs.environment, obs.credential_namespace, obs.account_id,
                obs.symbol, obs.position_side,
            ):
                raise ValueError("LEGACY_POSITION_LIFECYCLE_AUTHORITY_UNBOUND")
            if active_row is not None and obs.observed_at_ms < active_row["observed_at_ms"]:
                raise ValueError("POSITION_OBSERVATION_OUT_OF_ORDER")
            legacy_row = None
            if active_row is None and obs.environment == "DRY_RUN" and obs.credential_namespace == "NONE":
                legacy_row = db.execute(
                    "SELECT is_open, last_opened_at_ms FROM live_position_active WHERE symbol=?",
                    (obs.symbol,),
                ).fetchone()
            if legacy_row is not None:
                table = db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='live_account_snapshots'"
                ).fetchone()
                if table is None:
                    raise ValueError("LEGACY_POSITION_ACCOUNT_BINDING_REQUIRED")
                accounts = db.execute(
                    "SELECT DISTINCT account_id FROM live_account_snapshots"
                ).fetchall()
                latest = db.execute(
                    "SELECT snapshot_hash, payload FROM live_account_snapshots "
                    "WHERE account_id=? ORDER BY observed_at_ms DESC, rowid DESC LIMIT 1",
                    (obs.account_id,),
                ).fetchone()
                if len(accounts) != 1 or latest is None:
                    raise ValueError("LEGACY_POSITION_ACCOUNT_BINDING_REQUIRED")
                try:
                    snapshot = AccountSnapshotV1.model_validate_json(latest["payload"])
                except Exception as exc:
                    raise ValueError("LEGACY_POSITION_ACCOUNT_BINDING_REQUIRED") from exc
                if (snapshot.environment != "DRY_RUN"
                        or snapshot.credential_namespace != "NONE"
                        or snapshot.account_id != obs.account_id
                        or snapshot.snapshot_hash != latest["snapshot_hash"]
                        or snapshot.snapshot_hash != obs.account_snapshot_hash
                        or legacy_row["is_open"] not in (0, 1)):
                    raise ValueError("LEGACY_POSITION_ACCOUNT_BINDING_REQUIRED")
                db.execute("DELETE FROM live_position_active WHERE symbol=?", (obs.symbol,))

            previous = float(active_row["quantity"]) if active_row is not None else 0.0
            was_open = (bool(active_row["is_open"]) if active_row is not None
                        else bool(legacy_row["is_open"]) if legacy_row is not None else False)
            transitions: list[str] = []
            if was_open and obs.quantity == 0:
                transitions.append("POSITION_CLOSED")
            elif not was_open and obs.quantity != 0:
                transitions.append("POSITION_OPENED")
            elif active_row is not None and previous * obs.quantity < 0:
                transitions.extend(("POSITION_CLOSED", "POSITION_OPENED"))
            last_transition = (transitions[-1] if transitions else
                               active_row["last_transition"] if active_row is not None else
                               "POSITION_OPENED" if was_open else "")
            last_transition_at = (now_ms if transitions else
                                  active_row["last_transition_at_ms"] if active_row is not None else
                                  legacy_row["last_opened_at_ms"] if was_open and legacy_row is not None else 0)
            db.execute(
                "INSERT INTO live_position_lifecycle_v2 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(environment, credential_namespace, account_id, symbol, position_side) "
                "DO UPDATE SET "
                "quantity=excluded.quantity, is_open=excluded.is_open, "
                "last_transition=excluded.last_transition, "
                "last_transition_at_ms=excluded.last_transition_at_ms, "
                "observed_at_ms=excluded.observed_at_ms, source_hash=excluded.source_hash",
                (obs.environment, obs.credential_namespace, obs.account_id,
                 obs.symbol, obs.position_side, obs.quantity,
                 int(obs.quantity != 0), last_transition, last_transition_at,
                 obs.observed_at_ms, obs.observation_hash),
            )
            db.execute("INSERT INTO live_position_observed_sources VALUES (?)", (obs.observation_hash,))

            events: list[PositionEventV1] = []

            # 2. Check each trigger predicate
            triggers_to_check: list[str] = []

            triggers_to_check.extend(transitions)

            if (
                obs.order_status == "PARTIALLY_FILLED"
                and (now_ms - obs.order_observed_at_ms) >= self.policy.stale_partial_fill_ms
            ):
                triggers_to_check.append("PARTIAL_FILL_STALE")

            if obs.stop_price > 0 and obs.entry_price > 0:
                dist_stop = abs(obs.mark_price - obs.stop_price) / obs.entry_price
                if dist_stop <= self.policy.stop_near_pct:
                    triggers_to_check.append("STOP_NEAR")

            if obs.take_profit_price > 0 and obs.entry_price > 0:
                dist_tp = abs(obs.take_profit_price - obs.mark_price) / obs.entry_price
                if dist_tp <= self.policy.tp_near_pct:
                    triggers_to_check.append("TP_NEAR")

            if obs.tactical_regime is not None and (
                (obs.quantity > 0 and obs.tactical_regime == "BEARISH")
                or (obs.quantity < 0 and obs.tactical_regime == "BULLISH")
            ):
                triggers_to_check.append("REGIME_REVERSAL")

            if obs.oi_change_pct is not None and abs(obs.oi_change_pct) >= self.policy.oi_shock_pct:
                triggers_to_check.append("OI_SHOCK")

            if obs.funding_rate is not None and abs(obs.funding_rate) >= self.policy.funding_shock_rate:
                triggers_to_check.append("FUNDING_SHOCK")

            if obs.volatility_percentile is not None and obs.volatility_percentile >= self.policy.volatility_spike_percentile:
                triggers_to_check.append("VOLATILITY_SPIKE")

            if obs.spread_bps is not None and obs.spread_bps >= self.policy.liquidity_deterioration_bps:
                triggers_to_check.append("LIQUIDITY_DETERIORATION")

            if obs.grid_boundary_breached:
                triggers_to_check.append("GRID_BOUNDARY_BREACH")

            if (
                obs.add_opportunity
                and obs.evidence_id is not None
                and obs.signal_identity is not None
                and obs.evidence_id not in obs.prior_evidence_ids
                and obs.signal_identity not in obs.prior_signal_identities
            ):
                triggers_to_check.append("ADD_OPPORTUNITY")

            for trigger in triggers_to_check:
                # Cooldown check
                recent = db.execute(
                    "SELECT observed_at_ms FROM live_position_events "
                    "WHERE position_authority_key=? AND trigger=? AND (? - observed_at_ms) < ? "
                    "ORDER BY observed_at_ms DESC LIMIT 1",
                    (authority_key, trigger, now_ms, self.policy.cooldown_ms),
                ).fetchone()
                if recent is not None and trigger not in {"POSITION_OPENED", "POSITION_CLOSED"}:
                    continue

                event = PositionEventV1.build(
                    event_id=f"pe-{secrets.token_hex(12)}",
                    trigger=trigger,
                    symbol=obs.symbol,
                    source_hash=obs.observation_hash,
                    environment=obs.environment,
                    credential_namespace=obs.credential_namespace,
                    account_id=obs.account_id,
                    position_side=obs.position_side,
                    position_authority_key=authority_key,
                    observed_at_ms=now_ms,
                    details={"mark_price": obs.mark_price,
                             "quantity": 0.0 if trigger == "POSITION_CLOSED" else obs.quantity},
                )
                db.execute(
                    "INSERT INTO live_position_events (event_id, event_hash, trigger, symbol, "
                    "source_hash, observed_at_ms, payload, environment, credential_namespace, "
                    "account_id, position_side, position_authority_key) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        event.event_id,
                        event.event_hash,
                        event.trigger,
                        event.symbol,
                        event.source_hash,
                        event.observed_at_ms,
                        event.canonical_json(),
                        event.environment,
                        event.credential_namespace,
                        event.account_id,
                        event.position_side,
                        event.position_authority_key,
                    ),
                )
                db.execute(
                    """
                    INSERT OR IGNORE INTO live_position_case_dispatches (
                        event_id, event_hash, position_case_id, position_case_hash,
                        position_case_json, case_hash, symbol, state,
                        retry_count, lease_token, lease_expires_at_ms,
                        created_at_ms, updated_at_ms
                    ) VALUES (?, ?, '', '', '', '', ?, 'PENDING', 0, NULL, 0, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.event_hash,
                        event.symbol,
                        now_ms,
                        now_ms,
                    ),
                )
                events.append(event)


            return tuple(events)

    def current_quantity(
        self, account_id: str, symbol: str, environment: str,
        credential_namespace: str, position_side: str = "BOTH",
    ) -> float:
        if position_side != "BOTH":
            raise ValueError("unsupported position side")
        with connection(self.path) as db:
            row = db.execute(
                "SELECT quantity FROM live_position_lifecycle_v2 "
                "WHERE environment=? AND credential_namespace=? AND account_id=? "
                "AND symbol=? AND position_side=?",
                (environment, credential_namespace, account_id, symbol, position_side),
            ).fetchone()
        return float(row["quantity"]) if row is not None else 0.0

    def has_unbound_legacy_lifecycle(
        self, environment: str, credential_namespace: str, account_id: str,
        symbol: str, position_side: str = "BOTH",
    ) -> bool:
        with connection(self.path) as db:
            return _unbound_legacy_lifecycle(
                db, environment, credential_namespace, account_id, symbol, position_side,
            )

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> PositionEventV1:
        event = PositionEventV1.model_validate_json(row["payload"])
        event.verify()
        for name in (
            "event_id", "event_hash", "symbol", "trigger", "source_hash", "observed_at_ms",
            "environment", "credential_namespace", "account_id", "position_side",
            "position_authority_key",
        ):
            if getattr(event, name) != row[name]:
                raise ValueError("position event storage authority mismatch")
        return event

    def get_event(self, event_id: str) -> PositionEventV1 | None:
        with connection(self.path) as db:
            row = db.execute(
                "SELECT * FROM live_position_events WHERE event_id=?", (event_id,),
            ).fetchone()
            return None if row is None else self._event_from_row(row)

    def get_dispatch(self, event_id: str) -> dict[str, Any] | None:
        with connection(self.path) as db:
            row = db.execute(
                "SELECT * FROM live_position_case_dispatches WHERE event_id=?",
                (event_id,),
            ).fetchone()
            if row is None:
                return None
            return dict(row)

    def _verify_durable_authority(
        self,
        event_id: str,
        *,
        lease_token: str | None = None,
        expected_event_hash: str | None = None,
        expected_symbol: str | None = None,
        pos_case: CasePackageV1 | None = None,
        check_lease_now: int | None = None,
        _db: sqlite3.Connection | None = None,
    ) -> tuple[PositionEventV1, dict[str, Any]]:
        def read_rows(db: sqlite3.Connection) -> tuple[sqlite3.Row, sqlite3.Row]:
            event_row = db.execute(
                "SELECT * FROM live_position_events WHERE event_id=?", (event_id,),
            ).fetchone()
            dispatch_row = db.execute(
                "SELECT * FROM live_position_case_dispatches WHERE event_id=?", (event_id,),
            ).fetchone()
            if event_row is None or dispatch_row is None:
                raise ValueError("position event or dispatch missing")
            return event_row, dispatch_row

        if _db is None:
            with connection(self.path) as db:
                db.execute("BEGIN")
                event_row, dispatch_row = read_rows(db)
        else:
            event_row, dispatch_row = read_rows(_db)
        event = self._event_from_row(event_row)

        if expected_event_hash is not None and event.event_hash != expected_event_hash:
            raise ValueError("position event hash mismatch")
        if expected_symbol is not None and event.symbol != expected_symbol:
            raise ValueError("position event symbol mismatch")

        if (event.event_id != dispatch_row["event_id"]
                or event.event_hash != dispatch_row["event_hash"]
                or event.symbol != dispatch_row["symbol"]):
            raise ValueError("event and dispatch identity mismatch")

        if (event.environment is not None
                and event.credential_namespace is not None
                and event.account_id is not None
                and event.position_side is not None):
            expected_auth_key = position_authority_key(
                event.environment, event.credential_namespace, event.account_id,
                event.symbol, event.position_side,
            )
            if event.position_authority_key != expected_auth_key:
                raise ValueError("position authority key mismatch")
        elif event.position_authority_key is not None:
            raise ValueError("position authority key mismatch")

        dispatch_keys = dispatch_row.keys() if hasattr(dispatch_row, "keys") else tuple(dispatch_row)
        for field in ("environment", "credential_namespace", "account_id",
                      "position_side", "position_authority_key"):
            if field in dispatch_keys:
                dispatch_val = dispatch_row[field]
                if dispatch_val is None or dispatch_val != getattr(event, field):
                    raise ValueError(f"dispatch authority mismatch for {field}")

        if lease_token is not None:
            if dispatch_row["lease_token"] != lease_token:
                raise KeyError("lease token mismatch")
            if dispatch_row["state"] != "DISPATCHING":
                raise KeyError("dispatch state not DISPATCHING")
            if check_lease_now is not None and dispatch_row["lease_expires_at_ms"] <= check_lease_now:
                raise KeyError("lease expired")

        if pos_case is not None:
            pos_case.verify()
            if pos_case.position_event_hash != event.event_hash:
                raise ValueError("case event_hash linkage mismatch")
            if pos_case.case_id != f"pos-{event.event_id}":
                raise ValueError("case_id linkage mismatch")
            if pos_case.symbol != event.symbol:
                raise ValueError("case symbol mismatch")
            if dispatch_row["position_case_hash"] and pos_case.case_hash != dispatch_row["position_case_hash"]:
                raise ValueError("frozen case hash mismatch")
            if dispatch_row["position_case_json"] and pos_case.canonical_json() != dispatch_row["position_case_json"]:
                raise ValueError("frozen case json mismatch")

        return event, dict(dispatch_row)

    @staticmethod
    def _verify_admission(
        dispatch: dict[str, Any], event: PositionEventV1, case: CasePackageV1,
    ) -> tuple[str, str, str]:
        capsule = json.loads(dispatch["dispatch_authority_json"])
        if not isinstance(capsule, dict) or not isinstance(capsule.get("lease_token"), str):
            raise TypeError("invalid dispatch capsule")
        if not capsule["lease_token"]:
            raise ValueError("missing admitting lease")
        expected = _dispatch_authority(event, case, capsule["lease_token"])
        authority_json = canonical_json(expected)
        authority_hash = content_hash(expected)
        admission_hash = _admission_hash(authority_hash)
        if (dispatch["dispatch_authority_json"] != authority_json
                or dispatch["dispatch_authority_hash"] != authority_hash
                or dispatch["analysis_admission_hash"] != admission_hash):
            raise ValueError("analysis admission authority mismatch")
        return authority_json, authority_hash, admission_hash

    def _mint_analysis_admission(
        self, event_id: str, lease_token: str, expected_event_hash: str,
        expected_symbol: str, pos_case: CasePackageV1, now_ms: int, lease_ms: int,
    ) -> _AnalysisAdmission:
        lock_started = time.monotonic()
        with connection(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            now_ms += int((time.monotonic() - lock_started) * 1000)
            event, dispatch = self._verify_durable_authority(
                event_id, lease_token=lease_token, expected_event_hash=expected_event_hash,
                expected_symbol=expected_symbol, pos_case=pos_case, check_lease_now=now_ms,
                _db=db,
            )
            if (dispatch["position_case_id"] != pos_case.case_id
                    or dispatch["position_case_hash"] != pos_case.case_hash
                    or dispatch["position_case_json"] != pos_case.canonical_json()
                    or dispatch["case_hash"] != pos_case.case_hash):
                raise ValueError("incomplete frozen case authority")
            if dispatch["analysis_admission_hash"]:
                authority_json, authority_hash, admission_hash = self._verify_admission(
                    dispatch, event, pos_case,
                )
                if dispatch["analysis_completed"] != 1:
                    raise ValueError("uncertain admitted analysis requires manual recovery")
                provider_completed = True
            else:
                if (dispatch["dispatch_authority_json"] or dispatch["dispatch_authority_hash"]
                        or dispatch["analysis_completed"] != 0):
                    raise ValueError("partial analysis admission")
                authority = _dispatch_authority(event, pos_case, lease_token)
                authority_json = canonical_json(authority)
                authority_hash = content_hash(authority)
                admission_hash = _admission_hash(authority_hash)
                minted = db.execute(
                    """
                    UPDATE live_position_case_dispatches
                    SET dispatch_authority_json=?, dispatch_authority_hash=?,
                        analysis_admission_hash=?,
                        lease_expires_at_ms=?, updated_at_ms=?
                    WHERE event_id=? AND state='DISPATCHING' AND lease_token=?
                      AND lease_expires_at_ms>? AND analysis_admission_hash=''
                      AND dispatch_authority_hash='' AND dispatch_authority_json=''
                      AND position_case_id=? AND position_case_hash=? AND position_case_json=?
                      AND case_hash=?
                    """,
                    (authority_json, authority_hash, admission_hash,
                     now_ms + lease_ms, now_ms, event_id, lease_token, now_ms,
                     pos_case.case_id, pos_case.case_hash, pos_case.canonical_json(),
                     pos_case.case_hash),
                )
                if minted.rowcount != 1:
                    raise KeyError("analysis admission lease lost")
                provider_completed = False
            return _AnalysisAdmission(
                authority_json, authority_hash, admission_hash, pos_case.canonical_json(),
                event.canonical_json(), provider_completed,
            )

    def _complete_analysis(
        self, admission: _AnalysisAdmission, lease_token: str, now_ms: int,
    ) -> PositionEventV1:
        lock_started = time.monotonic()
        admitted_event = PositionEventV1.model_validate_json(admission.event_json)
        admitted_case = CasePackageV1.model_validate_json(admission.case_json)
        with connection(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            now_ms += int((time.monotonic() - lock_started) * 1000)
            event, dispatch = self._verify_durable_authority(
                admitted_event.event_id, lease_token=lease_token,
                expected_event_hash=admitted_event.event_hash, expected_symbol=admitted_event.symbol,
                pos_case=admitted_case, check_lease_now=now_ms, _db=db,
            )
            current = self._verify_admission(dispatch, event, admitted_case)
            if (current != (admission.authority_json, admission.authority_hash,
                            admission.admission_hash)
                    or event.canonical_json() != admission.event_json
                    or dispatch["case_hash"] != admitted_case.case_hash):
                raise ValueError("admitted analysis authority changed")
            # Only this validated connection can authorize the completion marker.
            # The capability disappears when the terminal transaction closes.
            db.create_function(
                "position_analysis_completion_authorized", 4,
                lambda receipt, authority, owner, case_hash: int(
                    (receipt, authority, owner, case_hash) == (
                        admission.admission_hash, admission.authority_hash,
                        lease_token, admitted_case.case_hash,
                    )
                ),
            )
            done = db.execute(
                """
                UPDATE live_position_case_dispatches
                SET state='DONE', analysis_completed=1, lease_token=NULL,
                    lease_expires_at_ms=0, updated_at_ms=?
                WHERE event_id=? AND state='DISPATCHING' AND lease_token=?
                  AND lease_expires_at_ms>? AND position_case_id=? AND position_case_hash=?
                  AND case_hash=? AND position_case_json=? AND dispatch_authority_json=?
                  AND dispatch_authority_hash=? AND analysis_admission_hash=?
                """,
                (now_ms, event.event_id, lease_token, now_ms, admitted_case.case_id,
                 admitted_case.case_hash, admitted_case.case_hash, admission.case_json,
                 admission.authority_json,
                 admission.authority_hash, admission.admission_hash),
            )
            if done.rowcount != 1:
                raise KeyError("analysis completion lease lost")
            return event

    async def drain_pending_dispatches(
        self, now_ms: int, lease_ms: int = 30_000, max_retries: int = 3
    ) -> tuple[PositionEventV1, ...]:
        """Drain unfinished position case dispatches using atomic leasing.

        Transitions rows through PENDING -> DISPATCHING -> DONE.
        Excessive retries or unrecoverable errors transition to FAILED_CLOSED.
        Returns the tuple of PositionEventV1 instances that were successfully dispatched.
        """
        if self.analysis_service is None or self.fresh_market_case is None:
            return ()

        dispatched_events: list[PositionEventV1] = []
        started = time.monotonic()

        def lease_now_ms() -> int:
            if self.lease_clock_ms is not None:
                return self.lease_clock_ms()
            return now_ms + int((time.monotonic() - started) * 1000)

        while True:
            lease_token = secrets.token_hex(16)
            claimed_row: sqlite3.Row | None = None
            claim_now = lease_now_ms()

            with connection(self.path) as db:
                db.execute("BEGIN IMMEDIATE")
                candidate = db.execute(
                    """
                    SELECT *
                    FROM live_position_case_dispatches
                    WHERE state = 'PENDING'
                       OR (state = 'DISPATCHING' AND lease_expires_at_ms <= ?)
                    ORDER BY created_at_ms ASC
                    LIMIT 1
                    """,
                    (claim_now,),
                ).fetchone()

                if candidate is None:
                    break

                event_id = candidate["event_id"]
                retry_count = int(candidate["retry_count"])

                if (candidate["analysis_admission_hash"] and candidate["analysis_completed"] != 1
                        or retry_count >= max_retries):
                    db.execute(
                        """
                        UPDATE live_position_case_dispatches
                        SET state = 'FAILED_CLOSED', lease_token = NULL, updated_at_ms = ?
                        WHERE event_id = ?
                        """,
                        (claim_now, event_id),
                    )
                    continue

                cursor = db.execute(
                    """
                    UPDATE live_position_case_dispatches
                    SET state = 'DISPATCHING',
                        lease_token = ?,
                        lease_expires_at_ms = ?,
                        retry_count = retry_count + 1,
                        updated_at_ms = ?
                    WHERE event_id = ?
                      AND (state = 'PENDING' OR (state = 'DISPATCHING' AND lease_expires_at_ms <= ?))
                    """,
                    (lease_token, claim_now + lease_ms, claim_now, event_id, claim_now),
                )
                if cursor.rowcount == 1:
                    claimed_row = candidate

            if claimed_row is None:
                continue

            event_id = claimed_row["event_id"]
            claim_event_hash = claimed_row["event_hash"]
            claim_symbol = claimed_row["symbol"]

            # Checkpoint 1: after claim
            try:
                event, current_dispatch = self._verify_durable_authority(
                    event_id, lease_token=lease_token,
                    expected_event_hash=claim_event_hash,
                    expected_symbol=claim_symbol,
                )
            except KeyError:
                break
            except Exception:  # noqa: BLE001
                with connection(self.path) as db:
                    db.execute(
                        """
                        UPDATE live_position_case_dispatches
                        SET state = 'FAILED_CLOSED', lease_token = NULL, updated_at_ms = ?
                        WHERE event_id = ? AND lease_token = ?
                        """,
                        (now_ms, event_id, lease_token),
                    )
                continue

            stored_case_json = current_dispatch["position_case_json"]
            stored_case_id = current_dispatch["position_case_id"]

            pos_case: CasePackageV1
            if stored_case_json:
                # 3.2 Retry rule: exact stored case must be used; fresh_market_case is NOT called.
                try:
                    pos_case = CasePackageV1.model_validate_json(stored_case_json)
                    pos_case.verify()
                    if any(current_dispatch[field] and pos_case.case_hash != current_dispatch[field]
                           for field in ("position_case_hash", "case_hash")):
                        raise ValueError("stored case hash mismatch")
                    if stored_case_id and pos_case.case_id != stored_case_id:
                        raise ValueError(f"stored case id mismatch: {pos_case.case_id} != {stored_case_id}")
                    if pos_case.position_event_hash != event.event_hash:
                        raise ValueError(f"event hash linkage mismatch: {pos_case.position_event_hash} != {event.event_hash}")
                    if pos_case.case_id != f"pos-{event.event_id}":
                        raise ValueError(f"case_id linkage mismatch: {pos_case.case_id} != pos-{event.event_id}")
                    if pos_case.symbol != event.symbol:
                        raise ValueError("position case symbol mismatch")
                except Exception:  # noqa: BLE001
                    # Tampered or corrupted stored case -> mark FAILED_CLOSED without calling analysis
                    with connection(self.path) as db:
                        db.execute(
                            """
                            UPDATE live_position_case_dispatches
                            SET state = 'FAILED_CLOSED', lease_token = NULL, updated_at_ms = ?
                            WHERE event_id = ? AND lease_token = ?
                            """,
                            (now_ms, event_id, lease_token),
                        )
                    continue
            else:
                # Checkpoint 2: immediately before first external fresh-market call
                try:
                    event, current_dispatch = self._verify_durable_authority(
                        event_id, lease_token=lease_token,
                        expected_event_hash=claim_event_hash,
                        expected_symbol=claim_symbol,
                    )
                except KeyError:
                    break
                except Exception:  # noqa: BLE001
                    with connection(self.path) as db:
                        db.execute(
                            """
                            UPDATE live_position_case_dispatches
                            SET state = 'FAILED_CLOSED', lease_token = NULL, updated_at_ms = ?
                            WHERE event_id = ? AND lease_token = ?
                            """,
                            (now_ms, event_id, lease_token),
                        )
                    continue

                # 3.3 First materialization: obtain base case once and freeze PositionCase before calling analysis
                try:
                    base_case = self.fresh_market_case(event.symbol)
                    base_case.verify()
                    if base_case.symbol != event.symbol:
                        raise ValueError("FRESH_MARKET_CASE_SYMBOL_MISMATCH")
                    pos_case = position_case_from_event(base_case, event, now_ms=now_ms)
                    pos_case.verify()
                except Exception as exc:  # noqa: BLE001
                    with connection(self.path) as db:
                        db.execute(
                            """
                            UPDATE live_position_case_dispatches
                            SET state = CASE WHEN ? OR retry_count >= ? THEN 'FAILED_CLOSED' ELSE 'PENDING' END,
                                lease_token = NULL,
                                lease_expires_at_ms = 0,
                                updated_at_ms = ?
                            WHERE event_id = ? AND lease_token = ?
                            """,
                            (str(exc) == "FRESH_MARKET_CASE_SYMBOL_MISMATCH",
                             max_retries, now_ms, event_id, lease_token),
                        )
                    continue

                # Checkpoint 3: after fresh-market materialization and before freezing
                try:
                    event, current_dispatch = self._verify_durable_authority(
                        event_id, lease_token=lease_token,
                        expected_event_hash=claim_event_hash,
                        expected_symbol=claim_symbol,
                        pos_case=pos_case,
                    )
                except KeyError:
                    break
                except Exception:  # noqa: BLE001
                    with connection(self.path) as db:
                        db.execute(
                            """
                            UPDATE live_position_case_dispatches
                            SET state = 'FAILED_CLOSED', lease_token = NULL, updated_at_ms = ?
                            WHERE event_id = ? AND lease_token = ?
                            """,
                            (now_ms, event_id, lease_token),
                        )
                    continue

                # Commit durable freeze to SQLite before external side effect
                freeze_now = lease_now_ms()
                with connection(self.path) as db:
                    frozen = db.execute(
                        """
                        UPDATE live_position_case_dispatches
                        SET position_case_id = ?,
                            position_case_hash = ?,
                            position_case_json = ?,
                            case_hash = ?,
                            updated_at_ms = ?
                        WHERE event_id = ? AND event_hash = ? AND symbol = ?
                          AND state = 'DISPATCHING'
                          AND lease_token = ? AND lease_expires_at_ms > ?
                          AND position_case_json = ''
                        """,
                        (
                            pos_case.case_id,
                            pos_case.case_hash,
                            pos_case.canonical_json(),
                            pos_case.case_hash,
                            freeze_now,
                            event_id,
                            claim_event_hash,
                            claim_symbol,
                            lease_token,
                            freeze_now,
                        ),
                    )
                if frozen.rowcount != 1:
                    break

            # Mint the immutable one-shot receipt under the same write transaction
            # that verifies event, frozen case and current dispatch ownership.
            analysis_now = lease_now_ms()
            try:
                admission = self._mint_analysis_admission(
                    event_id, lease_token, claim_event_hash, claim_symbol,
                    pos_case, analysis_now, lease_ms,
                )
            except KeyError:
                break
            except Exception:  # noqa: BLE001 - corrupt/uncertain authority fails closed.
                with connection(self.path) as db:
                    db.execute(
                        "UPDATE live_position_case_dispatches "
                        "SET state='FAILED_CLOSED', lease_token=NULL, updated_at_ms=? "
                        "WHERE event_id=? AND state='DISPATCHING' AND lease_token=?",
                        (now_ms, event_id, lease_token),
                    )
                continue

            try:
                if not admission.provider_completed:
                    # Archival changes cannot replace the immutable admitted case.
                    admitted_case = CasePackageV1.model_validate_json(admission.case_json)
                    await self.analysis_service.analyze_case(admitted_case)
                done_now = lease_now_ms()
                event = self._complete_analysis(admission, lease_token, done_now)
                dispatched_events.append(event)
            except KeyError:
                break
            except Exception:  # noqa: BLE001 - admitted completion is uncertain: never replay.
                with connection(self.path) as db:
                    db.execute(
                        "UPDATE live_position_case_dispatches "
                        "SET state='FAILED_CLOSED', lease_token=NULL, lease_expires_at_ms=0, "
                        "updated_at_ms=? WHERE event_id=? AND state='DISPATCHING' AND lease_token=?",
                        (now_ms, event_id, lease_token),
                    )

        return tuple(dispatched_events)

    async def process(
        self, obs: PositionObservationV1, now_ms: int
    ) -> tuple[PositionEventV1, ...]:
        events = self.evaluate(obs, now_ms)
        await self.drain_pending_dispatches(now_ms)
        return events
