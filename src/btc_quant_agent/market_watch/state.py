from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from .config import MarketWatchConfig
from .domain import (
    AlertSeverity,
    DerivativesRegime,
    DirectionalDecision,
    SignalLifecycleState,
    SymbolAssessment,
)


def compute_decision_fingerprint(assessment: SymbolAssessment) -> str:
    """Generate a stable, deterministic fingerprint reflecting meaningful operational state.

    Excludes volatile fields like millisecond timestamps or minor price ticks.
    """
    d = assessment.directional
    g = assessment.grid
    payload = {
        "symbol": assessment.symbol,
        "direction": str(d.decision),
        "setup": str(d.setup),
        "regime": str(d.regime),
        "entry_quality": str(d.entry_quality),
        "stop_loss": round(d.stop_loss, 2),
        "take_profit_1": round(d.take_profit_1, 2),
        "grid_decision": str(g.decision),
        "grid_lower": round(g.lower_bound, 2) if g.lower_bound is not None else None,
        "grid_upper": round(g.upper_bound, 2) if g.upper_bound is not None else None,
        "derivatives_regime": str(d.derivatives_regime),
        "lifecycle_state": str(assessment.lifecycle_state),
    }
    raw = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class MarketWatchStateStore:
    """Persistent SQLite store for stateful memory, audit trail, and shadow tracking."""

    def __init__(self, db_path: str | Path = "./var/market_watch.db") -> None:
        self.db_path = str(db_path)
        self._ensure_dir()
        self._init_db()

    def _ensure_dir(self) -> None:
        parent = Path(self.db_path).parent
        parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=30.0)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS market_watch_symbol_state (
                    symbol TEXT PRIMARY KEY,
                    regime TEXT,
                    directional_decision TEXT,
                    grid_decision TEXT,
                    derivatives_regime TEXT,
                    entry_quality TEXT,
                    recent_support REAL,
                    recent_resistance REAL,
                    recent_breakout_level REAL,
                    recent_failed_breakout REAL,
                    recent_failed_breakdown REAL,
                    lifecycle_state TEXT,
                    last_invalidation_reason TEXT,
                    last_rank INTEGER,
                    last_alert_fingerprint TEXT,
                    last_alert_time_ms INTEGER,
                    updated_at_ms INTEGER
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS market_watch_assessments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    decision_time_ms INTEGER,
                    symbol TEXT,
                    snapshot_hash TEXT,
                    regime TEXT,
                    setup TEXT,
                    directional_decision TEXT,
                    grid_decision TEXT,
                    entry_quality TEXT,
                    derivatives_regime TEXT,
                    benchmark_context TEXT,
                    opportunity_score REAL,
                    rank INTEGER,
                    reason_codes_json TEXT,
                    risk_codes_json TEXT,
                    decision_json TEXT,
                    alert_fingerprint TEXT,
                    notification_sent INTEGER
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS market_watch_shadow_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_ms INTEGER,
                    symbol TEXT,
                    snapshot_hash TEXT,
                    agent_decision TEXT,
                    agent_setup TEXT,
                    entry_quality TEXT,
                    reason_codes_json TEXT,
                    reference_decision TEXT,
                    reference_notes TEXT,
                    future_mfe REAL,
                    future_mae REAL,
                    tp1_hit INTEGER,
                    tp2_hit INTEGER,
                    sl_hit INTEGER,
                    time_to_target_ms INTEGER,
                    time_to_stop_ms INTEGER,
                    net_r REAL,
                    regime_after TEXT
                )
                """
            )
            conn.commit()

    def get_symbol_state(self, symbol: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM market_watch_symbol_state WHERE symbol = ?",
                (symbol,),
            )
            row = cursor.fetchone()
            return dict(row) if row is not None else None

    def save_symbol_state(
        self,
        symbol: str,
        assessment: SymbolAssessment,
        now_ms: int,
        alert_sent: bool = False,
    ) -> None:
        prev = self.get_symbol_state(symbol) or {}
        last_fp = assessment.alert_fingerprint if alert_sent else prev.get("last_alert_fingerprint")
        last_alert_time = now_ms if alert_sent else prev.get("last_alert_time_ms")

        # Track failed breakout/breakdown levels
        failed_bo = prev.get("recent_failed_breakout")
        failed_bd = prev.get("recent_failed_breakdown")
        if assessment.directional.setup.value == "FAILED_BREAKOUT":
            failed_bo = assessment.snapshot.tf_1h.recent_swing_high
        if assessment.directional.setup.value == "FAILED_BREAKDOWN":
            failed_bd = assessment.snapshot.tf_1h.recent_swing_low

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO market_watch_symbol_state (
                    symbol, regime, directional_decision, grid_decision,
                    derivatives_regime, entry_quality, recent_support,
                    recent_resistance, recent_breakout_level,
                    recent_failed_breakout, recent_failed_breakdown,
                    lifecycle_state, last_invalidation_reason, last_rank,
                    last_alert_fingerprint, last_alert_time_ms, updated_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    regime = excluded.regime,
                    directional_decision = excluded.directional_decision,
                    grid_decision = excluded.grid_decision,
                    derivatives_regime = excluded.derivatives_regime,
                    entry_quality = excluded.entry_quality,
                    recent_support = excluded.recent_support,
                    recent_resistance = excluded.recent_resistance,
                    recent_breakout_level = excluded.recent_breakout_level,
                    recent_failed_breakout = excluded.recent_failed_breakout,
                    recent_failed_breakdown = excluded.recent_failed_breakdown,
                    lifecycle_state = excluded.lifecycle_state,
                    last_invalidation_reason = excluded.last_invalidation_reason,
                    last_rank = excluded.last_rank,
                    last_alert_fingerprint = excluded.last_alert_fingerprint,
                    last_alert_time_ms = excluded.last_alert_time_ms,
                    updated_at_ms = excluded.updated_at_ms
                """,
                (
                    symbol,
                    str(assessment.directional.regime),
                    str(assessment.directional.decision),
                    str(assessment.grid.decision),
                    str(assessment.directional.derivatives_regime),
                    str(assessment.directional.entry_quality),
                    assessment.snapshot.tf_1h.recent_swing_low,
                    assessment.snapshot.tf_1h.recent_swing_high,
                    None,
                    failed_bo,
                    failed_bd,
                    str(assessment.lifecycle_state),
                    None,
                    assessment.rank,
                    last_fp,
                    last_alert_time,
                    now_ms,
                ),
            )
            # Record auditable assessment
            conn.execute(
                """
                INSERT INTO market_watch_assessments (
                    decision_time_ms, symbol, snapshot_hash, regime, setup,
                    directional_decision, grid_decision, entry_quality,
                    derivatives_regime, benchmark_context, opportunity_score,
                    rank, reason_codes_json, risk_codes_json, decision_json,
                    alert_fingerprint, notification_sent
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    assessment.snapshot.decision_time_ms,
                    symbol,
                    assessment.snapshot.snapshot_hash,
                    str(assessment.directional.regime),
                    str(assessment.directional.setup),
                    str(assessment.directional.decision),
                    str(assessment.grid.decision),
                    str(assessment.directional.entry_quality),
                    str(assessment.directional.derivatives_regime),
                    str(assessment.directional.benchmark_context),
                    assessment.opportunity_score,
                    assessment.rank,
                    json.dumps(assessment.directional.reason_codes),
                    json.dumps(assessment.directional.risk_codes),
                    json.dumps(assessment.as_dict()),
                    assessment.alert_fingerprint,
                    1 if alert_sent else 0,
                ),
            )
            conn.commit()

    def record_shadow_observation(
        self,
        *,
        timestamp_ms: int,
        symbol: str,
        snapshot_hash: str,
        agent_decision: str,
        agent_setup: str,
        entry_quality: str,
        reason_codes: list[str],
        reference_decision: str | None = None,
        reference_notes: str | None = None,
    ) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO market_watch_shadow_records (
                    timestamp_ms, symbol, snapshot_hash, agent_decision,
                    agent_setup, entry_quality, reason_codes_json,
                    reference_decision, reference_notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp_ms,
                    symbol,
                    snapshot_hash,
                    agent_decision,
                    agent_setup,
                    entry_quality,
                    json.dumps(reason_codes),
                    reference_decision,
                    reference_notes,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid) if cursor.lastrowid is not None else 0

    def update_shadow_outcome(
        self,
        shadow_id: int,
        *,
        future_mfe: float,
        future_mae: float,
        tp1_hit: bool,
        tp2_hit: bool,
        sl_hit: bool,
        time_to_target_ms: int | None,
        time_to_stop_ms: int | None,
        net_r: float,
        regime_after: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE market_watch_shadow_records SET
                    future_mfe = ?,
                    future_mae = ?,
                    tp1_hit = ?,
                    tp2_hit = ?,
                    sl_hit = ?,
                    time_to_target_ms = ?,
                    time_to_stop_ms = ?,
                    net_r = ?,
                    regime_after = ?
                WHERE id = ?
                """,
                (
                    future_mfe,
                    future_mae,
                    1 if tp1_hit else 0,
                    1 if tp2_hit else 0,
                    1 if sl_hit else 0,
                    time_to_target_ms,
                    time_to_stop_ms,
                    net_r,
                    regime_after,
                    shadow_id,
                ),
            )
            conn.commit()

    def get_all_states(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM market_watch_symbol_state ORDER BY last_rank ASC")
            return [dict(row) for row in cursor.fetchall()]


def evaluate_alert_emission(
    assessment: SymbolAssessment,
    prev_state: dict[str, Any] | None,
    config: MarketWatchConfig,
) -> tuple[bool, AlertSeverity, tuple[str, ...]]:
    """Determine whether an alert should be emitted.

    Rules:
    - State-change driven: repeated identical state produces NO_NOTIFICATION.
    - Meaningful transitions:
      * WAIT -> LONG, WAIT -> SHORT, LONG -> WAIT, SHORT -> WAIT
      * CANDIDATE -> ARMED, ARMED -> TRIGGERED, TRIGGERED -> INVALIDATED
      * Grid state change or bounds delta >= 2%
      * Derivatives regime materially changes / crowding risk
    - Filter by min_alert_severity (default WATCH or ACTION).
    """
    reasons: list[str] = []
    current_fp = assessment.alert_fingerprint

    if prev_state is not None:
        last_fp = prev_state.get("last_alert_fingerprint")
        if config.notify_only_on_change and last_fp == current_fp:
            return False, AlertSeverity.INFO, ("NO_NOTIFICATION_IDENTICAL_STATE",)

    # Determine severity
    curr_dir = assessment.directional.decision
    curr_life = assessment.lifecycle_state

    prev_dir_str = prev_state.get("directional_decision") if prev_state else None
    prev_life_str = prev_state.get("lifecycle_state") if prev_state else None

    if prev_life_str is not None and prev_life_str != str(curr_life):
        reasons.append(f"LIFECYCLE_{prev_life_str}_TO_{curr_life}")

    severity = AlertSeverity.INFO

    # ACTION: actionable LONG/SHORT
    if curr_life == SignalLifecycleState.TRIGGERED and curr_dir in (DirectionalDecision.LONG, DirectionalDecision.SHORT):
        severity = AlertSeverity.ACTION
        reasons.append(f"DIRECTIONAL_{curr_dir}_TRIGGERED")
    # RISK: active signal invalidated or deleveraging/crowding shock
    elif curr_life == SignalLifecycleState.INVALIDATED:
        severity = AlertSeverity.RISK
        reasons.append("SIGNAL_INVALIDATED")
    elif assessment.directional.derivatives_regime in (
        DerivativesRegime.LONG_LIQUIDATION,
        DerivativesRegime.DELEVERAGING,
    ):
        severity = AlertSeverity.RISK
        reasons.append("DELEVERAGING_RISK")
    # WATCH: setup armed or failed breakout detected
    elif curr_life == SignalLifecycleState.ARMED:
        severity = AlertSeverity.WATCH
        reasons.append("SETUP_ARMED")
    elif assessment.directional.setup.value in ("FAILED_BREAKOUT", "FAILED_BREAKDOWN"):
        severity = AlertSeverity.WATCH
        reasons.append(f"SETUP_{assessment.directional.setup.value}")
    elif prev_dir_str is not None and prev_dir_str != str(curr_dir):
        severity = AlertSeverity.WATCH
        reasons.append(f"DIRECTION_CHANGED_{prev_dir_str}_TO_{curr_dir}")
    else:
        severity = AlertSeverity.INFO
        reasons.append("REGIME_OR_RANK_UPDATE")

    # Severity hierarchy check against config.min_alert_severity
    severity_order = {
        AlertSeverity.INFO: 0,
        AlertSeverity.WATCH: 1,
        AlertSeverity.ACTION: 2,
        AlertSeverity.RISK: 3,
    }
    min_sev_enum = AlertSeverity(config.min_alert_severity)
    if severity_order[severity] < severity_order[min_sev_enum]:
        return False, severity, ("SEVERITY_BELOW_MINIMUM",)

    return True, severity, tuple(reasons)
