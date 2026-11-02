"""Durable local Kill Switch for Live V1."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from ..live_db import connection
from .models import KillObservationV1, SupervisorPolicyV1


class KillSwitch:
    def __init__(self, path: str | Path, policy: SupervisorPolicyV1 | None = None) -> None:
        self.path = Path(path)
        self.policy = policy or SupervisorPolicyV1()
        with connection(self.path) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS live_kill_switch_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    is_killed INTEGER NOT NULL DEFAULT 0,
                    reasons TEXT NOT NULL DEFAULT '[]',
                    tripped_at_ms INTEGER NOT NULL DEFAULT 0
                );
                INSERT OR IGNORE INTO live_kill_switch_state (id, is_killed, reasons, tripped_at_ms)
                VALUES (1, 0, '[]', 0);
            """)

    def evaluate(self, state: KillObservationV1, now_ms: int) -> list[str]:
        reasons: list[str] = []

        if state.daily_loss_usdt >= self.policy.daily_loss_cap_usdt:
            reasons.append("DAILY_LOSS_CAP")

        if state.drawdown_pct >= self.policy.drawdown_cap_pct:
            reasons.append("DRAWDOWN_CAP")

        if (not state.reconciled) and (now_ms - state.last_reconciled_at_ms >= self.policy.unreconciled_timeout_ms):
            reasons.append("ACCOUNT_UNRECONCILED")

        if state.order_conflicts >= self.policy.order_conflicts_max:
            reasons.append("ORDER_STATE_CONFLICT")

        if state.environment == "TESTNET" and (
            state.credential_namespace != "TESTNET"
            or state.rest_url.rstrip("/") != "https://testnet.binancefuture.com"
        ):
            reasons.append("WRONG_ENVIRONMENT")

        if (
            state.protective_missing_since_ms is not None
            and (now_ms - state.protective_missing_since_ms) >= self.policy.protective_missing_grace_ms
        ):
            reasons.append("PROTECTIVE_ORDER_MISSING")

        if reasons:
            self._latch(reasons, now_ms)

        return reasons

    def _latch(self, reasons: Sequence[str], now_ms: int) -> None:
        with connection(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT is_killed, reasons FROM live_kill_switch_state WHERE id=1"
            ).fetchone()
            current_reasons = set(json.loads(row["reasons"])) if row else set()
            combined = sorted(current_reasons.union(reasons))
            db.execute(
                "UPDATE live_kill_switch_state SET is_killed=1, reasons=?, tripped_at_ms=? WHERE id=1",
                (json.dumps(combined), now_ms),
            )

    def allows_new_risk(self) -> bool:
        with connection(self.path) as db:
            row = db.execute(
                "SELECT is_killed FROM live_kill_switch_state WHERE id=1"
            ).fetchone()
            if row and row["is_killed"] == 1:
                return False
        return True

    def allows_risk_reducing(self, environment: str) -> bool:
        # Real-money LIVE writes are forbidden under all circumstances
        return environment.upper() != "LIVE"
