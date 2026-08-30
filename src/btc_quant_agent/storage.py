from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .domain import OpportunityEvidence, Signal, SignalStatus, UserDecision


class Repository:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS signals (
                    signal_id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL,
                    expires_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_signals_created ON signals(created_at_ms DESC);
                CREATE INDEX IF NOT EXISTS idx_signals_fingerprint ON signals(fingerprint, created_at_ms DESC);
                CREATE TABLE IF NOT EXISTS user_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    actual_entry REAL,
                    decided_at_ms INTEGER NOT NULL,
                    FOREIGN KEY(signal_id) REFERENCES signals(signal_id)
                );
                CREATE TABLE IF NOT EXISTS shadow_trades (
                    signal_id TEXT PRIMARY KEY,
                    outcome TEXT NOT NULL,
                    entry_price REAL,
                    exit_price REAL,
                    r_multiple REAL,
                    entered_at_ms INTEGER,
                    exited_at_ms INTEGER,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(signal_id) REFERENCES signals(signal_id)
                );
                CREATE TABLE IF NOT EXISTS runtime_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS opportunities (
                    opportunity_id TEXT PRIMARY KEY,
                    detector_id TEXT NOT NULL,
                    detected_at_ms INTEGER NOT NULL,
                    expires_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_opportunities_detected
                ON opportunities(detected_at_ms DESC);
                CREATE TABLE IF NOT EXISTS execution_plans (
                    plan_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL,
                    expires_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS execution_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    exchange_order_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(plan_id) REFERENCES execution_plans(plan_id)
                );
                CREATE INDEX IF NOT EXISTS idx_execution_orders_plan
                ON execution_orders(plan_id, role, created_at_ms DESC);
                """
            )

    def save_signal(self, signal: Signal, cooldown_minutes: int) -> bool:
        cutoff = signal.created_at_ms - cooldown_minutes * 60_000
        with self._connect() as connection:
            duplicate = connection.execute(
                "SELECT 1 FROM signals WHERE fingerprint = ? AND created_at_ms >= ? LIMIT 1",
                (signal.fingerprint, cutoff),
            ).fetchone()
            if duplicate:
                return False
            connection.execute(
                "INSERT INTO signals VALUES (?, ?, ?, ?, ?, ?)",
                (
                    signal.signal_id,
                    signal.fingerprint,
                    signal.status.value,
                    signal.created_at_ms,
                    signal.expires_at_ms,
                    json.dumps(signal.as_dict(), ensure_ascii=False, sort_keys=True),
                ),
            )
        return True

    def save_opportunity(self, opportunity: OpportunityEvidence) -> bool:
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT payload_json FROM opportunities WHERE opportunity_id = ?",
                (opportunity.opportunity_id,),
            ).fetchone()
            payload = json.dumps(opportunity.as_dict(), ensure_ascii=False, sort_keys=True)
            if existing:
                stored_payload = json.loads(str(existing["payload_json"]))
                incoming_payload = json.loads(payload)
                stored_payload.pop("detected_at_ms", None)
                incoming_payload.pop("detected_at_ms", None)
                if stored_payload != incoming_payload:
                    raise ValueError("conflicting immutable opportunity")
                return False
            connection.execute(
                "INSERT INTO opportunities VALUES (?, ?, ?, ?, ?)",
                (
                    opportunity.opportunity_id,
                    opportunity.detector_id,
                    opportunity.detected_at_ms,
                    opportunity.expires_at_ms,
                    payload,
                ),
            )
        return True

    def get_signal(self, signal_id: str) -> Signal | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM signals WHERE signal_id = ?", (signal_id,)
            ).fetchone()
        return Signal.from_dict(json.loads(row["payload_json"])) if row else None

    def latest_signal(self) -> Signal | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM signals ORDER BY created_at_ms DESC LIMIT 1"
            ).fetchone()
        return Signal.from_dict(json.loads(row["payload_json"])) if row else None

    def active_signals(self) -> list[Signal]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM signals WHERE status = ? ORDER BY created_at_ms",
                (SignalStatus.ACTIVE.value,),
            ).fetchall()
        return [Signal.from_dict(json.loads(row["payload_json"])) for row in rows]

    def update_signal_status(self, signal_id: str, status: SignalStatus) -> None:
        signal = self.get_signal(signal_id)
        if signal is None:
            raise KeyError(f"unknown signal: {signal_id}")
        signal.status = status
        with self._connect() as connection:
            connection.execute(
                "UPDATE signals SET status = ?, payload_json = ? WHERE signal_id = ?",
                (
                    status.value,
                    json.dumps(signal.as_dict(), ensure_ascii=False, sort_keys=True),
                    signal_id,
                ),
            )

    def invalidate_signal(self, signal_id: str, reason: str) -> None:
        signal = self.get_signal(signal_id)
        if signal is None:
            raise KeyError(f"unknown signal: {signal_id}")
        signal.status = SignalStatus.INVALIDATED
        signal.invalidation_reason = reason
        self._write_signal(signal)

    def mark_signal_notified(self, signal_id: str, notified_at_ms: int) -> None:
        signal = self.get_signal(signal_id)
        if signal is None:
            raise KeyError(f"unknown signal: {signal_id}")
        signal.notified_at_ms = notified_at_ms
        self._write_signal(signal)

    def _write_signal(self, signal: Signal) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE signals SET status = ?, payload_json = ? WHERE signal_id = ?",
                (
                    signal.status.value,
                    json.dumps(signal.as_dict(), ensure_ascii=False, sort_keys=True),
                    signal.signal_id,
                ),
            )

    def mark_decision(
        self,
        signal_id: str,
        decision: UserDecision,
        actual_entry: float | None = None,
        decided_at_ms: int | None = None,
    ) -> None:
        if self.get_signal(signal_id) is None:
            raise KeyError(f"unknown signal: {signal_id}")
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO user_decisions(signal_id, decision, actual_entry, decided_at_ms) "
                "VALUES (?, ?, ?, ?)",
                (signal_id, decision.value, actual_entry, decided_at_ms or int(time.time() * 1000)),
            )

    def expire_signals(self, now_ms: int) -> int:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT signal_id, payload_json FROM signals WHERE status = ? AND expires_at_ms < ?",
                (SignalStatus.ACTIVE.value, now_ms),
            ).fetchall()
            for row in rows:
                signal = Signal.from_dict(json.loads(row["payload_json"]))
                signal.status = SignalStatus.EXPIRED
                connection.execute(
                    "UPDATE signals SET status = ?, payload_json = ? WHERE signal_id = ?",
                    (
                        signal.status.value,
                        json.dumps(signal.as_dict(), ensure_ascii=False, sort_keys=True),
                        signal.signal_id,
                    ),
                )
        return len(rows)

    def save_shadow(self, signal_id: str, outcome: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO shadow_trades VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    signal_id,
                    outcome["outcome"],
                    outcome.get("entry_price"),
                    outcome.get("exit_price"),
                    outcome.get("r_multiple"),
                    outcome.get("entered_at_ms"),
                    outcome.get("exited_at_ms"),
                    json.dumps(outcome, ensure_ascii=False, sort_keys=True),
                ),
            )

    def performance(self, since_ms: int = 0) -> dict[str, Any]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT outcome, r_multiple FROM shadow_trades WHERE exited_at_ms >= ?",
                (since_ms,),
            ).fetchall()
        resolved = [row for row in rows if row["r_multiple"] is not None]
        wins = sum(1 for row in resolved if row["outcome"] == "WIN")
        total_r = sum(float(row["r_multiple"]) for row in resolved)
        return {
            "trades": len(resolved),
            "wins": wins,
            "losses": sum(1 for row in resolved if row["outcome"] == "LOSS"),
            "win_rate": wins / len(resolved) if resolved else None,
            "total_r": total_r,
            "expectancy_r": total_r / len(resolved) if resolved else None,
        }

    def record_event(self, event_type: str, payload: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO runtime_events(event_type, created_at_ms, payload_json) VALUES (?, ?, ?)",
                (event_type, int(time.time() * 1000), json.dumps(payload, ensure_ascii=False)),
            )

    def save_execution_plan(self, kind: str, payload: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO execution_plans VALUES (?, ?, ?, ?, ?, ?)",
                (
                    payload["plan_id"],
                    kind,
                    "PREPARED",
                    payload["created_at_ms"],
                    payload["expires_at_ms"],
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                ),
            )

    def get_execution_plan(self, plan_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT kind, status, payload_json FROM execution_plans WHERE plan_id = ?",
                (plan_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "kind": row["kind"],
            "status": row["status"],
            "payload": json.loads(row["payload_json"]),
        }

    def update_execution_plan_status(self, plan_id: str, status: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE execution_plans SET status = ? WHERE plan_id = ?", (status, plan_id)
            )

    def save_execution_order(self, payload: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO execution_orders(plan_id, role, exchange_order_id, status, "
                "created_at_ms, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    payload["plan_id"],
                    payload["role"],
                    payload["order_id"],
                    payload["status"],
                    int(time.time() * 1000),
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                ),
            )

    def latest_execution_order(self, plan_id: str, role: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT exchange_order_id, status, payload_json FROM execution_orders "
                "WHERE plan_id = ? AND role = ? ORDER BY created_at_ms DESC, id DESC LIMIT 1",
                (plan_id, role),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload_json"])
        return {
            "order_id": row["exchange_order_id"],
            "status": row["status"],
            "payload": payload,
        }

    def daily_realized_loss_usdt(self, now_ms: int) -> float:
        day_start = now_ms - now_ms % 86_400_000
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM runtime_events WHERE event_type = ? AND created_at_ms >= ?",
                ("realized_pnl", day_start),
            ).fetchall()
        realized = [
            float(json.loads(row["payload_json"]).get("realized_pnl_usdt", 0.0)) for row in rows
        ]
        return abs(sum(value for value in realized if value < 0))

    def open_entry_plan_ids(self) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT plan_id FROM execution_plans WHERE kind = 'ENTRY' "
                "AND status IN ('SUBMITTED', 'PARTIALLY_FILLED') ORDER BY created_at_ms"
            ).fetchall()
        return [str(row["plan_id"]) for row in rows]
