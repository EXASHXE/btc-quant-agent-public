"""Deterministic Position Supervisor for Live V1."""

from __future__ import annotations

import json
import secrets
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..decision.models import CasePackageV1
from ..live_db import connection
from .models import PositionEventV1, PositionObservationV1, SupervisorPolicyV1


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


class PositionSupervisor:
    def __init__(
        self,
        path: str | Path,
        analysis_service: Any = None,
        fresh_market_case: Callable[[str], CasePackageV1] | None = None,
        policy: SupervisorPolicyV1 | None = None,
    ) -> None:
        self.path = Path(path)
        self.analysis_service = analysis_service
        self.fresh_market_case = fresh_market_case
        self.policy = policy or SupervisorPolicyV1()

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
                CREATE TABLE IF NOT EXISTS live_position_case_dispatches (
                    event_id TEXT PRIMARY KEY,
                    event_hash TEXT NOT NULL UNIQUE,
                    position_case_id TEXT NOT NULL DEFAULT '',
                    position_case_hash TEXT NOT NULL DEFAULT '',
                    position_case_json TEXT NOT NULL DEFAULT '',
                    case_hash TEXT NOT NULL DEFAULT '',
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

    def evaluate(
        self, obs: PositionObservationV1, now_ms: int
    ) -> tuple[PositionEventV1, ...]:
        with connection(self.path) as db:
            db.execute("BEGIN IMMEDIATE")

            # 1. Exact source deduplication
            existing = db.execute(
                "SELECT 1 FROM live_position_events WHERE source_hash=? LIMIT 1",
                (obs.observation_hash,),
            ).fetchone()
            if existing is not None:
                return ()

            active_row = db.execute(
                "SELECT is_open FROM live_position_active WHERE symbol=?",
                (obs.symbol,),
            ).fetchone()
            is_currently_open = bool(active_row and active_row["is_open"])

            # Handle position closing update
            if obs.quantity == 0.0 and is_currently_open:
                db.execute(
                    "UPDATE live_position_active SET is_open=0 WHERE symbol=?",
                    (obs.symbol,),
                )
                is_currently_open = False

            events: list[PositionEventV1] = []

            # 2. Check each trigger predicate
            triggers_to_check: list[str] = []

            if obs.previous_quantity == 0.0 and obs.quantity != 0.0 and not is_currently_open:
                triggers_to_check.append("POSITION_OPENED")

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
                    "WHERE symbol=? AND trigger=? AND (? - observed_at_ms) < ? "
                    "ORDER BY observed_at_ms DESC LIMIT 1",
                    (obs.symbol, trigger, now_ms, self.policy.cooldown_ms),
                ).fetchone()
                if recent is not None:
                    continue

                event = PositionEventV1.build(
                    event_id=f"pe-{secrets.token_hex(12)}",
                    trigger=trigger,
                    symbol=obs.symbol,
                    source_hash=obs.observation_hash,
                    observed_at_ms=now_ms,
                    details={"mark_price": obs.mark_price, "quantity": obs.quantity},
                )
                db.execute(
                    "INSERT INTO live_position_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        event.event_id,
                        event.event_hash,
                        event.trigger,
                        event.symbol,
                        event.source_hash,
                        event.observed_at_ms,
                        event.canonical_json(),
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

                if trigger == "POSITION_OPENED":
                    db.execute(
                        "INSERT INTO live_position_active (symbol, is_open, last_opened_at_ms) "
                        "VALUES (?, 1, ?) "
                        "ON CONFLICT(symbol) DO UPDATE SET is_open=1, last_opened_at_ms=?",
                        (obs.symbol, now_ms, now_ms),
                    )

            return tuple(events)

    def get_event(self, event_id: str) -> PositionEventV1 | None:
        with connection(self.path) as db:
            row = db.execute(
                "SELECT payload FROM live_position_events WHERE event_id=?",
                (event_id,),
            ).fetchone()
            if row is None:
                return None
            return PositionEventV1.model_validate(json.loads(row["payload"]))

    def get_dispatch(self, event_id: str) -> dict[str, Any] | None:
        with connection(self.path) as db:
            row = db.execute(
                "SELECT * FROM live_position_case_dispatches WHERE event_id=?",
                (event_id,),
            ).fetchone()
            if row is None:
                return None
            return dict(row)

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

        while True:
            lease_token = secrets.token_hex(16)
            claimed_row: sqlite3.Row | None = None

            with connection(self.path) as db:
                db.execute("BEGIN IMMEDIATE")
                candidate = db.execute(
                    """
                    SELECT event_id, event_hash, symbol, retry_count,
                           position_case_id, position_case_hash, position_case_json, case_hash
                    FROM live_position_case_dispatches
                    WHERE state = 'PENDING'
                       OR (state = 'DISPATCHING' AND lease_expires_at_ms <= ?)
                    ORDER BY created_at_ms ASC
                    LIMIT 1
                    """,
                    (now_ms,),
                ).fetchone()

                if candidate is None:
                    break

                event_id = candidate["event_id"]
                retry_count = int(candidate["retry_count"])

                if retry_count >= max_retries:
                    db.execute(
                        """
                        UPDATE live_position_case_dispatches
                        SET state = 'FAILED_CLOSED', lease_token = NULL, updated_at_ms = ?
                        WHERE event_id = ?
                        """,
                        (now_ms, event_id),
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
                    (lease_token, now_ms + lease_ms, now_ms, event_id, now_ms),
                )
                if cursor.rowcount == 1:
                    claimed_row = candidate

            if claimed_row is None:
                continue

            event_id = claimed_row["event_id"]
            event = self.get_event(event_id)
            if event is None:
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

            try:
                event.verify()
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

            if event.event_hash != claimed_row["event_hash"]:
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

            stored_case_json = claimed_row["position_case_json"]
            stored_case_hash = claimed_row["position_case_hash"] or claimed_row["case_hash"]
            stored_case_id = claimed_row["position_case_id"]

            pos_case: CasePackageV1
            if stored_case_json:
                # 3.2 Retry rule: exact stored case must be used; fresh_market_case is NOT called.
                try:
                    pos_case = CasePackageV1.model_validate_json(stored_case_json)
                    pos_case.verify()
                    if stored_case_hash and pos_case.case_hash != stored_case_hash:
                        raise ValueError(f"stored case hash mismatch: {pos_case.case_hash} != {stored_case_hash}")
                    if stored_case_id and pos_case.case_id != stored_case_id:
                        raise ValueError(f"stored case id mismatch: {pos_case.case_id} != {stored_case_id}")
                    if pos_case.position_event_hash != event.event_hash:
                        raise ValueError(f"event hash linkage mismatch: {pos_case.position_event_hash} != {event.event_hash}")
                    if pos_case.case_id != f"pos-{event.event_id}":
                        raise ValueError(f"case_id linkage mismatch: {pos_case.case_id} != pos-{event.event_id}")
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
                # 3.3 First materialization: obtain base case once and freeze PositionCase before calling analysis
                try:
                    base_case = self.fresh_market_case(claimed_row["symbol"])
                    base_case.verify()
                    pos_case = position_case_from_event(base_case, event, now_ms=now_ms)
                    pos_case.verify()
                except Exception:  # noqa: BLE001
                    with connection(self.path) as db:
                        db.execute(
                            """
                            UPDATE live_position_case_dispatches
                            SET state = CASE WHEN retry_count >= ? THEN 'FAILED_CLOSED' ELSE 'PENDING' END,
                                lease_token = NULL,
                                lease_expires_at_ms = 0,
                                updated_at_ms = ?
                            WHERE event_id = ? AND lease_token = ?
                            """,
                            (max_retries, now_ms, event_id, lease_token),
                        )
                    continue

                # Commit durable freeze to SQLite before external side effect
                with connection(self.path) as db:
                    db.execute(
                        """
                        UPDATE live_position_case_dispatches
                        SET position_case_id = ?,
                            position_case_hash = ?,
                            position_case_json = ?,
                            case_hash = ?,
                            updated_at_ms = ?
                        WHERE event_id = ? AND lease_token = ?
                        """,
                        (
                            pos_case.case_id,
                            pos_case.case_hash,
                            pos_case.canonical_json(),
                            pos_case.case_hash,
                            now_ms,
                            event_id,
                            lease_token,
                        ),
                    )

            try:
                await self.analysis_service.analyze_case(pos_case)

                with connection(self.path) as db:
                    db.execute(
                        """
                        UPDATE live_position_case_dispatches
                        SET state = 'DONE',
                            case_hash = ?,
                            position_case_hash = ?,
                            lease_token = NULL,
                            lease_expires_at_ms = 0,
                            updated_at_ms = ?
                        WHERE event_id = ? AND lease_token = ?
                        """,
                        (pos_case.case_hash, pos_case.case_hash, now_ms, event_id, lease_token),
                    )
                dispatched_events.append(event)
            except Exception:  # noqa: BLE001
                with connection(self.path) as db:
                    db.execute(
                        """
                        UPDATE live_position_case_dispatches
                        SET state = CASE WHEN retry_count >= ? THEN 'FAILED_CLOSED' ELSE 'PENDING' END,
                            lease_token = NULL,
                            lease_expires_at_ms = 0,
                            updated_at_ms = ?
                        WHERE event_id = ? AND lease_token = ?
                        """,
                        (max_retries, now_ms, event_id, lease_token),
                    )

        return tuple(dispatched_events)

    async def process(
        self, obs: PositionObservationV1, now_ms: int
    ) -> tuple[PositionEventV1, ...]:
        events = self.evaluate(obs, now_ms)
        await self.drain_pending_dispatches(now_ms)
        return events
