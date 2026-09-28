from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from .config import MarketWatchConfig, compute_market_watch_config_hash
from .domain import (
    MARKET_WATCH_EVIDENCE_VERSION,
    MARKET_WATCH_POLICY_VERSION,
    RULE_SCORE_SEMANTICS_VERSION,
    TACTICAL_POLICY_VERSION,
    AlertSeverity,
    BreakoutState,
    DerivativesRegime,
    DirectionalDecision,
    GridDecision,
    GridPlan,
    ShadowExecutionPathModel,
    SignalLifecycleState,
    SymbolAssessment,
    TacticalSemanticIdentity,
    extract_setup_key,
    extract_signal_identity,
)
from .evidence import (
    TacticalEvidenceConflictError,
    TacticalEvidenceIdentityError,
    TacticalEvidenceLinkageError,
    TacticalFeatureEvidenceV2,
    canonical_evidence_json,
    deserialize_tactical_feature_evidence,
    validate_tactical_feature_evidence,
    verify_tactical_evidence_identity,
)


def compute_decision_fingerprint(
    assessment: SymbolAssessment,
    config: MarketWatchConfig | None = None,
) -> str:
    """Generate a stable, deterministic fingerprint reflecting meaningful operational state.

    Excludes volatile fields like millisecond timestamps or minor price ticks.
    Uses active config for crowding classification and includes config_hash.
    """
    from .derivatives import is_severe_long_crowding, is_severe_short_crowding

    d = assessment.directional
    g = assessment.grid
    c_hash = compute_market_watch_config_hash(config) if config is not None else assessment.config_hash
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
        "is_severe_long_crowding": is_severe_long_crowding(assessment.snapshot.derivatives, config),
        "is_severe_short_crowding": is_severe_short_crowding(assessment.snapshot.derivatives, config),
        "lifecycle_state": str(assessment.lifecycle_state),
        "breakout_state": str(d.breakout_state),
        "signal_identity": str(assessment.signal_identity),
        "config_hash": str(c_hash),
    }
    raw = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _serialize_semantic_identity(val: Any) -> str | None:
    if val is None:
        return None
    if isinstance(val, str):
        return val
    if hasattr(val, "as_json"):
        return str(val.as_json())
    if hasattr(val, "to_json"):
        return str(val.to_json())
    if hasattr(val, "as_dict"):
        return json.dumps(val.as_dict(), sort_keys=True)
    if hasattr(val, "to_dict"):
        return json.dumps(val.to_dict(), sort_keys=True)
    try:
        return json.dumps(val, default=str, sort_keys=True)
    except Exception:  # noqa: BLE001
        return str(val)


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
                    setup TEXT,
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
                    updated_at_ms INTEGER,
                    breakout_level REAL,
                    breakout_direction TEXT,
                    breakout_bar_end_ms INTEGER,
                    breakout_state TEXT,
                    grid_lower_bound REAL,
                    grid_upper_bound REAL,
                    recent_failed_breakout_ms INTEGER,
                    recent_failed_breakdown_ms INTEGER,
                    created_bar_end_ms INTEGER,
                    armed_bar_end_ms INTEGER,
                    triggered_bar_end_ms INTEGER,
                    age_bars INTEGER DEFAULT 0,
                    last_shadow_recorded_state TEXT,
                    signal_identity TEXT,
                    last_shadow_armed_signal_id TEXT,
                    last_shadow_triggered_signal_id TEXT,
                    setup_key TEXT,
                    setup_instance_started_bar_end_ms INTEGER
                )
                """
            )
            # Migrations for existing DB
            cols_symbol_state = [
                ("setup", "TEXT"),
                ("breakout_level", "REAL"),
                ("breakout_direction", "TEXT"),
                ("breakout_bar_end_ms", "INTEGER"),
                ("breakout_state", "TEXT"),
                ("grid_lower_bound", "REAL"),
                ("grid_upper_bound", "REAL"),
                ("recent_failed_breakout_ms", "INTEGER"),
                ("recent_failed_breakdown_ms", "INTEGER"),
                ("created_bar_end_ms", "INTEGER"),
                ("armed_bar_end_ms", "INTEGER"),
                ("triggered_bar_end_ms", "INTEGER"),
                ("age_bars", "INTEGER DEFAULT 0"),
                ("last_shadow_recorded_state", "TEXT"),
                ("signal_identity", "TEXT"),
                ("last_shadow_armed_signal_id", "TEXT"),
                ("last_shadow_triggered_signal_id", "TEXT"),
                ("setup_key", "TEXT"),
                ("setup_instance_started_bar_end_ms", "INTEGER"),
            ]
            for col_name, col_type in cols_symbol_state:
                try:
                    conn.execute(f"ALTER TABLE market_watch_symbol_state ADD COLUMN {col_name} {col_type}")
                except sqlite3.OperationalError:
                    pass

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS market_watch_assessments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    decision_time_ms INTEGER,
                    symbol TEXT,
                    snapshot_hash TEXT,
                    policy_version TEXT,
                    config_hash TEXT,
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
                    notification_sent INTEGER,
                    signal_identity TEXT,
                    setup_key TEXT,
                    rule_score REAL,
                    rule_score_semantics TEXT,
                    eligible_playbooks_json TEXT,
                    actionable_playbooks_json TEXT,
                    selected_playbook TEXT,
                    selection_method TEXT,
                    reference_universe_status TEXT,
                    missing_reference_members_json TEXT,
                    semantic_identity_json TEXT
                )
                """
            )
            for col_name, col_type in [
                ("policy_version", "TEXT"),
                ("config_hash", "TEXT"),
                ("signal_identity", "TEXT"),
                ("setup_key", "TEXT"),
                ("rule_score", "REAL"),
                ("rule_score_semantics", "TEXT"),
                ("eligible_playbooks_json", "TEXT"),
                ("actionable_playbooks_json", "TEXT"),
                ("selected_playbook", "TEXT"),
                ("selection_method", "TEXT"),
                ("reference_universe_status", "TEXT"),
                ("missing_reference_members_json", "TEXT"),
                ("semantic_identity_json", "TEXT"),
                ("feature_evidence_id", "TEXT"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE market_watch_assessments ADD COLUMN {col_name} {col_type}")
                except sqlite3.OperationalError:
                    pass

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS market_watch_shadow_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_ms INTEGER,
                    symbol TEXT,
                    snapshot_hash TEXT,
                    policy_version TEXT,
                    config_hash TEXT,
                    agent_decision TEXT,
                    agent_setup TEXT,
                    entry_quality TEXT,
                    reason_codes_json TEXT,
                    reference_decision TEXT,
                    reference_notes TEXT,
                    entry_price REAL,
                    stop_loss REAL,
                    tp1 REAL,
                    tp2 REAL,
                    direction TEXT,
                    future_mfe REAL,
                    future_mae REAL,
                    tp1_hit INTEGER DEFAULT 0,
                    tp2_hit INTEGER DEFAULT 0,
                    sl_hit INTEGER DEFAULT 0,
                    time_to_target_ms INTEGER,
                    time_to_stop_ms INTEGER,
                    net_r REAL,
                    regime_after TEXT,
                    resolved INTEGER DEFAULT 0,
                    evaluation_horizon_bars INTEGER DEFAULT 16,
                    evaluation_end_ms INTEGER,
                    observation_type TEXT DEFAULT 'ACTIONABLE_TRIGGERED',
                    signal_identity TEXT,
                    signal_time_ms INTEGER,
                    entry_zone_low REAL,
                    entry_zone_high REAL,
                    entry_window_bars INTEGER DEFAULT 4,
                    entry_window_end_ms INTEGER,
                    fill_status TEXT DEFAULT 'WAITING_FOR_FILL',
                    fill_time_ms INTEGER,
                    fill_price REAL,
                    gross_r REAL,
                    friction_r REAL,
                    path_resolution TEXT,
                    execution_path_model TEXT,
                    setup_key TEXT,
                    evidence_version TEXT,
                    entry_window_start_ms INTEGER,
                    evaluation_start_ms INTEGER,
                    terminal_reason TEXT,
                    exit_time_ms INTEGER,
                    exit_price REAL,
                    coverage_status TEXT,
                    coverage_reason TEXT,
                    semantic_identity_json TEXT,
                    feature_evidence_id TEXT
                )
                """
            )
            for col_name, col_type in [
                ("snapshot_hash", "TEXT"),
                ("policy_version", "TEXT"),
                ("config_hash", "TEXT"),
                ("agent_decision", "TEXT"),
                ("agent_setup", "TEXT"),
                ("entry_quality", "TEXT"),
                ("reason_codes_json", "TEXT"),
                ("reference_decision", "TEXT"),
                ("reference_notes", "TEXT"),
                ("entry_price", "REAL"),
                ("stop_loss", "REAL"),
                ("tp1", "REAL"),
                ("tp2", "REAL"),
                ("direction", "TEXT"),
                ("resolved", "INTEGER DEFAULT 0"),
                ("evaluation_horizon_bars", "INTEGER DEFAULT 16"),
                ("evaluation_end_ms", "INTEGER"),
                ("observation_type", "TEXT DEFAULT 'ACTIONABLE_TRIGGERED'"),
                ("signal_identity", "TEXT"),
                ("signal_time_ms", "INTEGER"),
                ("entry_zone_low", "REAL"),
                ("entry_zone_high", "REAL"),
                ("entry_window_bars", "INTEGER DEFAULT 4"),
                ("entry_window_end_ms", "INTEGER"),
                ("fill_status", "TEXT DEFAULT 'WAITING_FOR_FILL'"),
                ("fill_time_ms", "INTEGER"),
                ("fill_price", "REAL"),
                ("gross_r", "REAL"),
                ("friction_r", "REAL"),
                ("path_resolution", "TEXT"),
                ("execution_path_model", "TEXT"),
                ("setup_key", "TEXT"),
                ("evidence_version", "TEXT"),
                ("entry_window_start_ms", "INTEGER"),
                ("evaluation_start_ms", "INTEGER"),
                ("terminal_reason", "TEXT"),
                ("exit_time_ms", "INTEGER"),
                ("exit_price", "REAL"),
                ("coverage_status", "TEXT"),
                ("coverage_reason", "TEXT"),
                ("semantic_identity_json", "TEXT"),
                ("feature_evidence_id", "TEXT"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE market_watch_shadow_records ADD COLUMN {col_name} {col_type}")
                except sqlite3.OperationalError:
                    pass

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tactical_feature_evidence_v2 (
                    evidence_id TEXT PRIMARY KEY,
                    evidence_schema_version TEXT NOT NULL,
                    decision_time_ms INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    snapshot_hash TEXT NOT NULL,
                    policy_version TEXT NOT NULL,
                    config_hash TEXT NOT NULL,
                    semantic_identity_hash TEXT,
                    signal_identity TEXT,
                    setup_key TEXT,
                    lifecycle_state TEXT,
                    selected_playbook TEXT,
                    final_directional_decision TEXT,
                    rule_score REAL,
                    reference_universe_status TEXT,
                    evidence_json TEXT NOT NULL,
                    persisted_at_ms INTEGER
                )
                """
            )
            # Scan for duplicate natural keys with divergent evidence IDs (Section 38)
            cur_dup = conn.execute(
                """
                SELECT symbol, decision_time_ms, snapshot_hash, policy_version, config_hash, COUNT(DISTINCT evidence_id) AS cnt
                FROM tactical_feature_evidence_v2
                GROUP BY symbol, decision_time_ms, snapshot_hash, policy_version, config_hash
                HAVING cnt > 1
                """
            )
            conflict_row = cur_dup.fetchone()
            if conflict_row is not None:
                raise TacticalEvidenceConflictError(
                    f"B1_R1_EXISTING_EVIDENCE_CONFLICT: Duplicate natural key with divergent evidence IDs found in database: {conflict_row}"
                )

            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_tactical_feat_ev_natural_key
                ON tactical_feature_evidence_v2 (symbol, decision_time_ms, snapshot_hash, policy_version, config_hash)
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
        evidence: TacticalFeatureEvidenceV2 | None = None,
    ) -> None:
        prev = self.get_symbol_state(symbol) or {}
        last_fp = assessment.alert_fingerprint if alert_sent else prev.get("last_alert_fingerprint")
        last_alert_time = now_ms if alert_sent else prev.get("last_alert_time_ms")

        bar_end_ms = assessment.snapshot.tf_15m.closed_bar_end_time_ms
        curr_life = str(assessment.lifecycle_state)
        prev_life = prev.get("lifecycle_state")

        # Breakout state tracking
        d = assessment.directional
        bo_state = str(d.breakout_state) if d.breakout_state != BreakoutState.NONE else prev.get("breakout_state", "NONE")
        bo_level = d.breakout_level if d.breakout_level is not None else prev.get("breakout_level")
        bo_dir = d.breakout_direction or ("LONG" if d.decision == DirectionalDecision.LONG else ("SHORT" if d.decision == DirectionalDecision.SHORT else None)) or prev.get("breakout_direction")
        bo_time = d.breakout_bar_end_ms if d.breakout_bar_end_ms is not None else prev.get("breakout_bar_end_ms")

        # If retested or invalidated or expired, reset breakout state
        if d.breakout_state == BreakoutState.RETEST_CONFIRMED or curr_life in ("INVALIDATED", "EXPIRED"):
            bo_state = "NONE"

        # Failed breakout memory tracking (R1-04)
        failed_bo = prev.get("recent_failed_breakout")
        failed_bo_ms = prev.get("recent_failed_breakout_ms")
        failed_bd = prev.get("recent_failed_breakdown")
        failed_bd_ms = prev.get("recent_failed_breakdown_ms")

        if assessment.directional.setup.value == "FAILED_BREAKOUT":
            failed_bo = assessment.snapshot.tf_1h.recent_swing_high
            failed_bo_ms = bar_end_ms
        if assessment.directional.setup.value == "FAILED_BREAKDOWN":
            failed_bd = assessment.snapshot.tf_1h.recent_swing_low
            failed_bd_ms = bar_end_ms

        curr_setup = str(assessment.directional.setup.value)

        curr_setup_key = assessment.setup_key or extract_setup_key(symbol, assessment.directional, assessment.snapshot)
        prev_setup_key = prev.get("setup_key")
        prev_instance_started = prev.get("setup_instance_started_bar_end_ms")
        is_same_setup = bool(
            prev_setup_key is not None
            and prev_setup_key == curr_setup_key
            and curr_setup != "NO_TRADE"
            and prev_life not in ("INVALIDATED", "EXPIRED", None)
        )
        if is_same_setup:
            instance_started_ms = prev_instance_started or bar_end_ms
        else:
            instance_started_ms = bar_end_ms

        curr_sig_id = assessment.signal_identity or extract_signal_identity(symbol, assessment.directional, assessment.snapshot, instance_started_ms)
        prev_sig_id = prev.get("signal_identity")
        prev_bo_level = prev.get("breakout_level")
        curr_bo_level = d.breakout_level
        bo_level_changed = (
            curr_bo_level is not None
            and prev_bo_level is not None
            and round(curr_bo_level, 2) != round(prev_bo_level, 2)
        )
        prev_bo_dir = prev.get("breakout_direction")
        intended_dir_part = curr_sig_id.split(":")[2] if ":" in curr_sig_id else "NONE"
        dir_changed = (
            prev_bo_dir is not None
            and intended_dir_part not in ("NONE", "")
            and prev_bo_dir != intended_dir_part
        )

        prev_setup = prev.get("setup")
        setup_changed = bool(prev_setup is not None and prev_setup != curr_setup)

        # A new breakout level or changed intended direction or new signal identity resets:
        # created_bar_end_ms, age_bars, and shadow dedupe state.
        is_reset = (
            setup_changed
            or bo_level_changed
            or dir_changed
            or (prev_sig_id is not None and prev_sig_id != curr_sig_id)
            or curr_setup == "NO_TRADE"
            or curr_life in ("INVALIDATED", "EXPIRED")
        )

        if is_reset:
            created_ms = bar_end_ms
            age_bars = 0
            armed_ms = bar_end_ms if curr_life == "ARMED" else None
            triggered_ms = bar_end_ms if curr_life == "TRIGGERED" else None
            prev_armed = prev.get("last_shadow_armed_signal_id")
            prev_trig = prev.get("last_shadow_triggered_signal_id")
            shadow_armed_id = prev_armed if prev_armed == curr_sig_id else None
            shadow_triggered_id = prev_trig if prev_trig == curr_sig_id else None
            last_shadow_state = (
                prev.get("last_shadow_recorded_state")
                if (prev_trig == curr_sig_id or prev_armed == curr_sig_id)
                else None
            )
        else:
            shadow_armed_id = prev.get("last_shadow_armed_signal_id")
            shadow_triggered_id = prev.get("last_shadow_triggered_signal_id")
            last_shadow_state = prev.get("last_shadow_recorded_state")

            signal_identity_matches = (
                prev_sig_id is not None
                and prev_sig_id == curr_sig_id
                and curr_life in ("ARMED", "TRIGGERED", "CANDIDATE")
                and prev_life in ("ARMED", "TRIGGERED", "CANDIDATE")
            )
            if signal_identity_matches and prev.get("created_bar_end_ms"):
                created_ms = prev["created_bar_end_ms"]
                armed_ms = prev.get("armed_bar_end_ms") or (bar_end_ms if curr_life == "ARMED" else None)
                triggered_ms = prev.get("triggered_bar_end_ms") or (bar_end_ms if curr_life == "TRIGGERED" else None)
                if created_ms and bar_end_ms >= created_ms:
                    age_bars = max(0, int((bar_end_ms - created_ms) / (15 * 60 * 1000)))
                else:
                    age_bars = 0
            else:
                created_ms = prev.get("created_bar_end_ms") or bar_end_ms
                age_bars = 0
                armed_ms = prev.get("armed_bar_end_ms") or (bar_end_ms if curr_life == "ARMED" else None)
                triggered_ms = prev.get("triggered_bar_end_ms") or (bar_end_ms if curr_life == "TRIGGERED" else None)

        if evidence is None:
            evidence = getattr(assessment, "feature_evidence", None)

        if evidence is not None:
            validate_tactical_feature_evidence(evidence)
            verify_tactical_evidence_identity(evidence)

        with self._connect() as conn:
            if evidence is not None:
                cur_ev = conn.execute(
                    """
                    SELECT evidence_id FROM tactical_feature_evidence_v2
                    WHERE symbol = ? AND decision_time_ms = ? AND snapshot_hash = ?
                      AND policy_version = ? AND config_hash = ?
                    """,
                    (
                        evidence.symbol,
                        evidence.decision_time_ms,
                        evidence.snapshot_hash,
                        evidence.policy_version,
                        evidence.config_hash,
                    ),
                )
                row_ev = cur_ev.fetchone()
                if row_ev is not None:
                    existing_ev_id = row_ev[0]
                    if existing_ev_id != evidence.evidence_id:
                        raise TacticalEvidenceConflictError(
                            f"Evidence conflict for natural key "
                            f"({evidence.symbol}, {evidence.decision_time_ms}, {evidence.snapshot_hash}, {evidence.policy_version}, {evidence.config_hash}): "
                            f"existing={existing_ev_id}, new={evidence.evidence_id}"
                        )
                else:
                    sem_hash = (
                        evidence.semantic_identity.canonical_hash()
                        if hasattr(evidence.semantic_identity, "canonical_hash")
                        else (
                            evidence.semantic_identity.compute_identity_hash()
                            if hasattr(evidence.semantic_identity, "compute_identity_hash")
                            else None
                        )
                    )
                    final_dir = (
                        evidence.decision_trace.final_directional_decision
                        if hasattr(evidence.decision_trace, "final_directional_decision")
                        else ""
                    )
                    ref_status = (
                        evidence.reference_universe_evidence.status
                        if hasattr(evidence.reference_universe_evidence, "status")
                        else getattr(evidence.reference_universe_evidence, "reference_universe_status", "UNIVERSE_COMPLETE")
                    )
                    try:
                        conn.execute(
                            """
                            INSERT INTO tactical_feature_evidence_v2 (
                                evidence_id, evidence_schema_version, decision_time_ms, symbol,
                                snapshot_hash, policy_version, config_hash, semantic_identity_hash,
                                signal_identity, setup_key, lifecycle_state, selected_playbook,
                                final_directional_decision, rule_score, reference_universe_status,
                                evidence_json, persisted_at_ms
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                evidence.evidence_id,
                                evidence.evidence_schema_version,
                                evidence.decision_time_ms,
                                evidence.symbol,
                                evidence.snapshot_hash,
                                evidence.policy_version,
                                evidence.config_hash,
                                sem_hash,
                                evidence.signal_identity,
                                evidence.setup_key,
                                evidence.lifecycle_state,
                                evidence.selected_playbook,
                                final_dir,
                                evidence.rule_score,
                                ref_status,
                                canonical_evidence_json(evidence),
                                now_ms,
                            ),
                        )
                    except sqlite3.IntegrityError as exc:
                        cur_race = conn.execute(
                            """
                            SELECT evidence_id FROM tactical_feature_evidence_v2
                            WHERE symbol = ? AND decision_time_ms = ? AND snapshot_hash = ?
                              AND policy_version = ? AND config_hash = ?
                            """,
                            (
                                evidence.symbol,
                                evidence.decision_time_ms,
                                evidence.snapshot_hash,
                                evidence.policy_version,
                                evidence.config_hash,
                            ),
                        )
                        race_row = cur_race.fetchone()
                        if race_row is not None and race_row[0] != evidence.evidence_id:
                            raise TacticalEvidenceConflictError(
                                f"Concurrent conflict on natural key: existing={race_row[0]}, new={evidence.evidence_id}"
                            ) from exc

            conn.execute(
                """
                INSERT INTO market_watch_symbol_state (
                    symbol, setup, regime, directional_decision, grid_decision,
                    derivatives_regime, entry_quality, recent_support,
                    recent_resistance, recent_breakout_level,
                    recent_failed_breakout, recent_failed_breakdown,
                    lifecycle_state, last_invalidation_reason, last_rank,
                    last_alert_fingerprint, last_alert_time_ms, updated_at_ms,
                    breakout_level, breakout_direction, breakout_bar_end_ms, breakout_state,
                    grid_lower_bound, grid_upper_bound,
                    recent_failed_breakout_ms, recent_failed_breakdown_ms,
                    created_bar_end_ms, armed_bar_end_ms, triggered_bar_end_ms,
                    age_bars, last_shadow_recorded_state,
                    signal_identity, last_shadow_armed_signal_id, last_shadow_triggered_signal_id,
                    setup_key, setup_instance_started_bar_end_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    setup = excluded.setup,
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
                    updated_at_ms = excluded.updated_at_ms,
                    breakout_level = excluded.breakout_level,
                    breakout_direction = excluded.breakout_direction,
                    breakout_bar_end_ms = excluded.breakout_bar_end_ms,
                    breakout_state = excluded.breakout_state,
                    grid_lower_bound = excluded.grid_lower_bound,
                    grid_upper_bound = excluded.grid_upper_bound,
                    recent_failed_breakout_ms = excluded.recent_failed_breakout_ms,
                    recent_failed_breakdown_ms = excluded.recent_failed_breakdown_ms,
                    created_bar_end_ms = excluded.created_bar_end_ms,
                    armed_bar_end_ms = excluded.armed_bar_end_ms,
                    triggered_bar_end_ms = excluded.triggered_bar_end_ms,
                    age_bars = excluded.age_bars,
                    last_shadow_recorded_state = excluded.last_shadow_recorded_state,
                    signal_identity = excluded.signal_identity,
                    last_shadow_armed_signal_id = excluded.last_shadow_armed_signal_id,
                    last_shadow_triggered_signal_id = excluded.last_shadow_triggered_signal_id,
                    setup_key = excluded.setup_key,
                    setup_instance_started_bar_end_ms = excluded.setup_instance_started_bar_end_ms
                """,
                (
                    symbol,
                    curr_setup,
                    str(assessment.directional.regime),
                    str(assessment.directional.decision),
                    str(assessment.grid.decision),
                    str(assessment.directional.derivatives_regime),
                    str(assessment.directional.entry_quality),
                    round(assessment.snapshot.tf_1h.supports[0], 2) if assessment.snapshot.tf_1h.supports else None,
                    round(assessment.snapshot.tf_1h.resistances[0], 2) if assessment.snapshot.tf_1h.resistances else None,
                    bo_level,
                    failed_bo,
                    failed_bd,
                    curr_life,
                    assessment.veto_reasons[0] if assessment.veto_reasons else None,
                    assessment.rank,
                    last_fp,
                    last_alert_time,
                    now_ms,
                    bo_level,
                    bo_dir,
                    bo_time,
                    bo_state,
                    assessment.grid.lower_bound,
                    assessment.grid.upper_bound,
                    failed_bo_ms,
                    failed_bd_ms,
                    created_ms,
                    armed_ms,
                    triggered_ms,
                    age_bars,
                    last_shadow_state,
                    curr_sig_id,
                    shadow_armed_id,
                    shadow_triggered_id,
                    curr_setup_key,
                    instance_started_ms,
                ),
            )
            # Record auditable assessment
            cur_a = conn.execute(
                """
                SELECT id FROM market_watch_assessments
                WHERE symbol = ? AND decision_time_ms = ? AND snapshot_hash = ?
                  AND policy_version = ? AND config_hash = ?
                LIMIT 1
                """,
                (
                    symbol,
                    assessment.snapshot.decision_time_ms,
                    assessment.snapshot.snapshot_hash,
                    assessment.policy_version,
                    assessment.config_hash,
                ),
            )
            if cur_a.fetchone() is None:
                feat_ev_id = evidence.evidence_id if evidence else getattr(assessment, "feature_evidence_id", None)
                conn.execute(
                    """
                    INSERT INTO market_watch_assessments (
                        decision_time_ms, symbol, snapshot_hash, policy_version, config_hash,
                        regime, setup, directional_decision, grid_decision, entry_quality,
                        derivatives_regime, benchmark_context, opportunity_score,
                        rank, reason_codes_json, risk_codes_json, decision_json,
                        alert_fingerprint, notification_sent, signal_identity, setup_key,
                        rule_score, rule_score_semantics, eligible_playbooks_json,
                        actionable_playbooks_json, selected_playbook, selection_method,
                        reference_universe_status, missing_reference_members_json,
                        semantic_identity_json, feature_evidence_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        assessment.snapshot.decision_time_ms,
                        symbol,
                        assessment.snapshot.snapshot_hash,
                        assessment.policy_version,
                        assessment.config_hash,
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
                        assessment.signal_identity or curr_sig_id,
                        assessment.setup_key or curr_setup_key,
                        getattr(assessment, "rule_score", assessment.opportunity_score),
                        getattr(assessment, "rule_score_semantics", RULE_SCORE_SEMANTICS_VERSION),
                        json.dumps([p.value if hasattr(p, "value") else str(p) for p in getattr(assessment, "eligible_playbooks", ())]),
                        json.dumps([p.value if hasattr(p, "value") else str(p) for p in getattr(assessment, "actionable_playbooks", ())]),
                        (assessment.selected_playbook.value if hasattr(assessment.selected_playbook, "value") else str(assessment.selected_playbook)) if getattr(assessment, "selected_playbook", None) else None,
                        getattr(assessment, "selection_method", "STATIC_PRECEDENCE"),
                        getattr(assessment, "reference_universe_status", "UNIVERSE_COMPLETE"),
                        json.dumps(list(getattr(assessment, "missing_reference_members", ()))),
                        _serialize_semantic_identity(getattr(assessment, "semantic_identity", None)),
                        feat_ev_id,
                    ),
                )
            conn.commit()

    def set_last_shadow_signal_ids(
        self,
        symbol: str,
        *,
        armed_id: str | None = None,
        triggered_id: str | None = None,
    ) -> None:
        with self._connect() as conn:
            if armed_id is not None and triggered_id is not None:
                cursor = conn.execute(
                    "UPDATE market_watch_symbol_state SET last_shadow_armed_signal_id = ?, last_shadow_triggered_signal_id = ? WHERE symbol = ?",
                    (armed_id, triggered_id, symbol.upper()),
                )
                if cursor.rowcount == 0:
                    conn.execute(
                        "INSERT INTO market_watch_symbol_state (symbol, last_shadow_armed_signal_id, last_shadow_triggered_signal_id) VALUES (?, ?, ?) "
                        "ON CONFLICT(symbol) DO UPDATE SET last_shadow_armed_signal_id = excluded.last_shadow_armed_signal_id, last_shadow_triggered_signal_id = excluded.last_shadow_triggered_signal_id",
                        (symbol.upper(), armed_id, triggered_id),
                    )
            elif armed_id is not None:
                cursor = conn.execute(
                    "UPDATE market_watch_symbol_state SET last_shadow_armed_signal_id = ? WHERE symbol = ?",
                    (armed_id, symbol.upper()),
                )
                if cursor.rowcount == 0:
                    conn.execute(
                        "INSERT INTO market_watch_symbol_state (symbol, last_shadow_armed_signal_id) VALUES (?, ?) "
                        "ON CONFLICT(symbol) DO UPDATE SET last_shadow_armed_signal_id = excluded.last_shadow_armed_signal_id",
                        (symbol.upper(), armed_id),
                    )
            elif triggered_id is not None:
                cursor = conn.execute(
                    "UPDATE market_watch_symbol_state SET last_shadow_triggered_signal_id = ? WHERE symbol = ?",
                    (triggered_id, symbol.upper()),
                )
                if cursor.rowcount == 0:
                    conn.execute(
                        "INSERT INTO market_watch_symbol_state (symbol, last_shadow_triggered_signal_id) VALUES (?, ?) "
                        "ON CONFLICT(symbol) DO UPDATE SET last_shadow_triggered_signal_id = excluded.last_shadow_triggered_signal_id",
                        (symbol.upper(), triggered_id),
                    )
            conn.commit()

    def set_last_shadow_recorded_state(self, symbol: str, state_value: str) -> None:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE market_watch_symbol_state SET last_shadow_recorded_state = ? WHERE symbol = ?",
                (state_value, symbol.upper()),
            )
            if cursor.rowcount == 0:
                conn.execute(
                    "INSERT INTO market_watch_symbol_state (symbol, last_shadow_recorded_state) VALUES (?, ?) "
                    "ON CONFLICT(symbol) DO UPDATE SET last_shadow_recorded_state = excluded.last_shadow_recorded_state",
                    (symbol.upper(), state_value),
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
        policy_version: str = "",
        config_hash: str = "",
        entry_price: float = 0.0,
        stop_loss: float = 0.0,
        tp1: float = 0.0,
        tp2: float = 0.0,
        direction: str = "",
        evaluation_horizon_bars: int = 16,
        evaluation_end_ms: int | None = None,
        observation_type: str = "ACTIONABLE_TRIGGERED",
        signal_identity: str = "",
        signal_time_ms: int | None = None,
        entry_zone_low: float = 0.0,
        entry_zone_high: float = 0.0,
        entry_window_bars: int = 4,
        entry_window_end_ms: int | None = None,
        fill_status: str = "WAITING_FOR_FILL",
        fill_time_ms: int | None = None,
        fill_price: float | None = None,
        gross_r: float | None = None,
        friction_r: float | None = None,
        path_resolution: str | None = None,
        execution_path_model: str | None = None,
        setup_key: str = "",
        evidence_version: str = MARKET_WATCH_EVIDENCE_VERSION,
        entry_window_start_ms: int | None = None,
        evaluation_start_ms: int | None = None,
        terminal_reason: str | None = None,
        exit_time_ms: int | None = None,
        exit_price: float | None = None,
        coverage_status: str | None = None,
        coverage_reason: str | None = None,
        semantic_identity: TacticalSemanticIdentity | None = None,
        semantic_identity_json: str | None = None,
        feature_evidence_id: str | None = None,
    ) -> int:
        if semantic_identity is not None and not semantic_identity_json:
            semantic_identity_json = _serialize_semantic_identity(semantic_identity)
        if signal_time_ms is None:
            signal_time_ms = timestamp_ms
        if entry_window_start_ms is None:
            entry_window_start_ms = signal_time_ms
        if entry_window_end_ms is None:
            entry_window_end_ms = signal_time_ms + (entry_window_bars * 15 * 60 * 1000)
        if evaluation_end_ms is None:
            eval_end_ms = signal_time_ms + (evaluation_horizon_bars * 15 * 60 * 1000)
        else:
            eval_end_ms = evaluation_end_ms

        if entry_zone_low <= 0.0 and entry_price > 0.0:
            entry_zone_low = entry_price
        if entry_zone_high <= 0.0 and entry_price > 0.0:
            entry_zone_high = entry_price

        if not signal_identity:
            anchor = entry_price if entry_price > 0 else 0.0
            setup_key = f"{symbol.upper()}:{agent_setup}:{direction}:{anchor}"
            signal_identity = f"{setup_key}:{signal_time_ms}"
        elif not setup_key:
            parts = signal_identity.split(":")
            if len(parts) >= 5:
                setup_key = ":".join(parts[:4])
            else:
                setup_key = signal_identity

        if execution_path_model is None or not str(execution_path_model).strip():
            execution_path_model = ShadowExecutionPathModel.PARTIAL_FIRST_BAR_1M_THEN_15M.value
        if not policy_version:
            policy_version = MARKET_WATCH_POLICY_VERSION
        if not config_hash:
            config_hash = "default"
        if not evidence_version:
            evidence_version = MARKET_WATCH_EVIDENCE_VERSION

        with self._connect() as conn:
            if feature_evidence_id is not None:
                cur_ev = conn.execute(
                    "SELECT 1 FROM tactical_feature_evidence_v2 WHERE evidence_id = ?",
                    (feature_evidence_id,),
                )
                if cur_ev.fetchone() is None:
                    raise TacticalEvidenceLinkageError(
                        f"Shadow record links to non-existent evidence_id: {feature_evidence_id}"
                    )

            # Deduplication guard: exactly one ACTIONABLE_TRIGGERED per signal_identity
            if observation_type == "ACTIONABLE_TRIGGERED" and signal_identity:
                cursor = conn.execute(
                    "SELECT id FROM market_watch_shadow_records WHERE signal_identity = ? AND observation_type = 'ACTIONABLE_TRIGGERED' LIMIT 1",
                    (signal_identity,),
                )
                row = cursor.fetchone()
                if row is not None:
                    return int(row[0])

            cursor = conn.execute(
                """
                INSERT INTO market_watch_shadow_records (
                    timestamp_ms, symbol, snapshot_hash, policy_version, config_hash,
                    agent_decision, agent_setup, entry_quality, reason_codes_json,
                    reference_decision, reference_notes, entry_price, stop_loss,
                    tp1, tp2, direction, resolved, evaluation_horizon_bars, evaluation_end_ms,
                    observation_type, signal_identity, signal_time_ms, entry_zone_low,
                    entry_zone_high, entry_window_bars, entry_window_end_ms, fill_status,
                    fill_time_ms, fill_price, gross_r, friction_r, path_resolution,
                    execution_path_model, setup_key, evidence_version, entry_window_start_ms,
                    evaluation_start_ms, terminal_reason, exit_time_ms, exit_price,
                    coverage_status, coverage_reason, semantic_identity_json, feature_evidence_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp_ms,
                    symbol,
                    snapshot_hash,
                    policy_version,
                    config_hash,
                    agent_decision,
                    agent_setup,
                    entry_quality,
                    json.dumps(reason_codes),
                    reference_decision,
                    reference_notes,
                    entry_price,
                    stop_loss,
                    tp1,
                    tp2,
                    direction,
                    evaluation_horizon_bars,
                    eval_end_ms,
                    observation_type,
                    signal_identity,
                    signal_time_ms,
                    entry_zone_low,
                    entry_zone_high,
                    entry_window_bars,
                    entry_window_end_ms,
                    fill_status,
                    fill_time_ms,
                    fill_price,
                    gross_r,
                    friction_r,
                    path_resolution,
                    execution_path_model,
                    setup_key,
                    evidence_version,
                    entry_window_start_ms,
                    evaluation_start_ms,
                    terminal_reason,
                    exit_time_ms,
                    exit_price,
                    coverage_status,
                    coverage_reason,
                    semantic_identity_json,
                    feature_evidence_id,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid) if cursor.lastrowid is not None else 0

    def update_shadow_fill(
        self,
        shadow_id: int,
        *,
        fill_status: str,
        fill_time_ms: int | None,
        fill_price: float | None,
        evaluation_start_ms: int | None = None,
        evaluation_end_ms: int | None = None,
        path_resolution: str | None = None,
        execution_path_model: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE market_watch_shadow_records SET
                    fill_status = ?,
                    fill_time_ms = ?,
                    fill_price = ?,
                    entry_price = COALESCE(?, entry_price),
                    evaluation_start_ms = COALESCE(?, evaluation_start_ms),
                    evaluation_end_ms = COALESCE(?, evaluation_end_ms),
                    path_resolution = COALESCE(?, path_resolution),
                    execution_path_model = COALESCE(?, execution_path_model)
                WHERE id = ?
                """,
                (
                    fill_status,
                    fill_time_ms,
                    fill_price,
                    fill_price,
                    evaluation_start_ms,
                    evaluation_end_ms,
                    path_resolution,
                    execution_path_model,
                    shadow_id,
                ),
            )
            conn.commit()

    def update_shadow_outcome(
        self,
        shadow_id: int,
        *,
        future_mfe: float | None = None,
        future_mae: float | None = None,
        tp1_hit: bool = False,
        tp2_hit: bool = False,
        sl_hit: bool = False,
        time_to_target_ms: int | None = None,
        time_to_stop_ms: int | None = None,
        net_r: float | None = None,
        regime_after: str = "UNKNOWN",
        gross_r: float | None = None,
        friction_r: float | None = None,
        fill_status: str | None = None,
        fill_time_ms: int | None = None,
        fill_price: float | None = None,
        path_resolution: str | None = None,
        execution_path_model: str | None = None,
        evaluation_start_ms: int | None = None,
        evaluation_end_ms: int | None = None,
        terminal_reason: str | None = None,
        exit_time_ms: int | None = None,
        exit_price: float | None = None,
        coverage_status: str | None = None,
        coverage_reason: str | None = None,
        resolved: int = 1,
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
                    regime_after = ?,
                    resolved = ?,
                    gross_r = COALESCE(?, gross_r),
                    friction_r = COALESCE(?, friction_r),
                    fill_status = COALESCE(?, fill_status),
                    fill_time_ms = COALESCE(?, fill_time_ms),
                    fill_price = COALESCE(?, fill_price),
                    entry_price = COALESCE(?, entry_price),
                    path_resolution = COALESCE(?, path_resolution),
                    execution_path_model = COALESCE(?, execution_path_model),
                    evaluation_start_ms = COALESCE(?, evaluation_start_ms),
                    evaluation_end_ms = COALESCE(?, evaluation_end_ms),
                    terminal_reason = COALESCE(?, terminal_reason),
                    exit_time_ms = COALESCE(?, exit_time_ms),
                    exit_price = COALESCE(?, exit_price),
                    coverage_status = COALESCE(?, coverage_status),
                    coverage_reason = COALESCE(?, coverage_reason)
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
                    resolved,
                    gross_r,
                    friction_r,
                    fill_status,
                    fill_time_ms,
                    fill_price,
                    fill_price,
                    path_resolution,
                    execution_path_model,
                    evaluation_start_ms,
                    evaluation_end_ms,
                    terminal_reason,
                    exit_time_ms,
                    exit_price,
                    coverage_status,
                    coverage_reason,
                    shadow_id,
                ),
            )
            conn.commit()

    def get_pending_shadow_records(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM market_watch_shadow_records WHERE resolved = 0 ORDER BY timestamp_ms ASC"
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_all_shadow_records(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM market_watch_shadow_records ORDER BY timestamp_ms DESC"
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_tactical_shadow_records(
        self,
        *,
        include_legacy: bool = False,
    ) -> list[dict[str, Any]]:
        """Query shadow records, defaulting strictly to current compatible Tactical semantic identity."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            if include_legacy:
                cursor = conn.execute(
                    "SELECT * FROM market_watch_shadow_records ORDER BY timestamp_ms DESC"
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM market_watch_shadow_records WHERE semantic_identity_json IS NOT NULL ORDER BY timestamp_ms DESC"
                )
            records = [dict(row) for row in cursor.fetchall()]
            if not include_legacy:
                return [r for r in records if not is_legacy_tactical_record(r)]
            return records

    def get_tactical_assessments(
        self,
        symbol: str | None = None,
        *,
        include_legacy: bool = False,
    ) -> list[dict[str, Any]]:
        """Query assessments, defaulting strictly to current compatible Tactical semantic identity."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            query = "SELECT * FROM market_watch_assessments"
            clauses: list[str] = []
            params: list[Any] = []
            if symbol:
                clauses.append("symbol = ?")
                params.append(symbol.upper())
            if not include_legacy:
                clauses.append("semantic_identity_json IS NOT NULL")
            if clauses:
                query += " WHERE " + " AND ".join(clauses)
            query += " ORDER BY id DESC"
            cursor = conn.execute(query, tuple(params))
            records = [dict(row) for row in cursor.fetchall()]
            if not include_legacy:
                return [r for r in records if not is_legacy_tactical_record(r)]
            return records

    def get_latest_assessment(self, symbol: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM market_watch_assessments WHERE symbol = ? ORDER BY id DESC LIMIT 1",
                (symbol.upper(),),
            )
            row = cursor.fetchone()
            return dict(row) if row is not None else None

    def get_all_states(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM market_watch_symbol_state ORDER BY last_rank ASC")
            return [dict(row) for row in cursor.fetchall()]

    def get_tactical_feature_evidence(self, evidence_id: str) -> TacticalFeatureEvidenceV2 | None:
        """Fetch immutable TacticalFeatureEvidenceV2 by evidence_id."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT evidence_id, evidence_json FROM tactical_feature_evidence_v2 WHERE evidence_id = ?",
                (evidence_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            ev = deserialize_tactical_feature_evidence(row["evidence_json"], verify_identity=True)
            if row["evidence_id"] != ev.evidence_id:
                raise TacticalEvidenceIdentityError(
                    f"Row evidence_id mismatch: row={row['evidence_id']}, embedded={ev.evidence_id}"
                )
            return ev

    def list_tactical_feature_evidence(
        self,
        symbol: str | None = None,
        start_ms: int | None = None,
        end_ms: int | None = None,
        selected_playbook: str | None = None,
        final_decision: str | None = None,
        limit: int = 100,
    ) -> list[TacticalFeatureEvidenceV2]:
        """Query immutable TacticalFeatureEvidenceV2 records, defaulting to B1 schema."""
        query = ["SELECT evidence_id, evidence_json FROM tactical_feature_evidence_v2 WHERE evidence_schema_version = 'TACTICAL_FEATURE_EVIDENCE_V2'"]
        params: list[Any] = []
        if symbol:
            query.append("AND symbol = ?")
            params.append(symbol.upper())
        if start_ms is not None:
            query.append("AND decision_time_ms >= ?")
            params.append(start_ms)
        if end_ms is not None:
            query.append("AND decision_time_ms <= ?")
            params.append(end_ms)
        if selected_playbook:
            query.append("AND selected_playbook = ?")
            params.append(selected_playbook)
        if final_decision:
            query.append("AND final_directional_decision = ?")
            params.append(final_decision)
        query.append("ORDER BY decision_time_ms DESC LIMIT ?")
        params.append(limit)

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(" ".join(query), tuple(params))
            rows = cursor.fetchall()
            evidences: list[TacticalFeatureEvidenceV2] = []
            for row in rows:
                ev = deserialize_tactical_feature_evidence(row["evidence_json"], verify_identity=True)
                if row["evidence_id"] != ev.evidence_id:
                    raise TacticalEvidenceIdentityError(
                        f"Row evidence_id mismatch: row={row['evidence_id']}, embedded={ev.evidence_id}"
                    )
                evidences.append(ev)
            return evidences


def is_legacy_tactical_record(record: dict[str, Any]) -> bool:
    """Determine whether a record predates TACTICAL_POLICY_R2_B0."""
    sem_id = record.get("semantic_identity_json")
    if not sem_id or not str(sem_id).strip():
        return True
    try:
        data = json.loads(sem_id) if isinstance(sem_id, str) else sem_id
        if data.get("tactical_policy_version") != TACTICAL_POLICY_VERSION:
            return True
    except Exception:  # noqa: BLE001
        return True
    return False


def is_legacy_shadow_record(record: dict[str, Any]) -> bool:
    """Determine whether a shadow record predates modern R2.3 forward evidence semantics."""
    if record.get("is_legacy") or record.get("regime_after") in ("LEGACY", "LEGACY_INELIGIBLE"):
        return True
    if record.get("terminal_reason") == "LEGACY_INELIGIBLE":
        return True
    if record.get("fill_status") in ("LEGACY", "INELIGIBLE"):
        return True

    # P0: Legacy forward evidence must be version-gated (Section 9)
    # A database record is R2.3/V1 eligible ONLY IF evidence_version == MARKET_WATCH_EVIDENCE_VERSION
    if "evidence_version" in record:
        if record.get("evidence_version") != MARKET_WATCH_EVIDENCE_VERSION:
            return True
        if not record.get("setup_key") or not str(record.get("setup_key")).strip():
            return True
        if not record.get("signal_identity") or not str(record.get("signal_identity")).strip():
            return True
        if record.get("observation_type") == "ACTIONABLE_TRIGGERED":
            direction = record.get("direction")
            if not direction or str(direction).upper() not in ("LONG", "SHORT"):
                return True

    return False


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
      * Grid state change, boundary delta >= configured threshold, or LOWER_BOUND_BREACHED
      * Derivatives regime materially changes / crowding risk
    - Grid-only changes MUST generate an alert even when DirectionalDecision == WAIT.
    - LOWER_BOUND_BREACHED should be RISK.
    - Filter by min_alert_severity (default WATCH or ACTION).
    """
    from .grid_policy import should_alert_grid_change

    reasons: list[str] = []
    current_fp = assessment.alert_fingerprint

    # Check grid changes
    prev_grid = None
    if prev_state is not None:
        prev_gd = prev_state.get("grid_decision")
        if prev_gd:
            prev_lb = prev_state.get("grid_lower_bound")
            if prev_lb is None:
                prev_lb = prev_state.get("recent_support")
            prev_ub = prev_state.get("grid_upper_bound")
            if prev_ub is None:
                prev_ub = prev_state.get("recent_resistance")
            prev_grid = GridPlan(
                symbol=assessment.symbol,
                decision=GridDecision(prev_gd),
                lower_bound=prev_lb,
                upper_bound=prev_ub,
            )

    grid_change_alert = should_alert_grid_change(
        current=assessment.grid,
        previous=prev_grid,
        threshold_pct=config.grid.grid_boundary_change_pct,
    )

    if prev_state is not None:
        last_fp = prev_state.get("last_alert_fingerprint")
        if config.notify_only_on_change and last_fp == current_fp and not grid_change_alert:
            return False, AlertSeverity.INFO, ("NO_NOTIFICATION_IDENTICAL_STATE",)

    # Determine severity
    curr_dir = assessment.directional.decision
    curr_life = assessment.lifecycle_state

    prev_dir_str = prev_state.get("directional_decision") if prev_state else None
    prev_life_str = prev_state.get("lifecycle_state") if prev_state else None

    if prev_life_str is not None and prev_life_str != str(curr_life):
        reasons.append(f"LIFECYCLE_{prev_life_str}_TO_{curr_life}")

    severity = AlertSeverity.INFO

    # 1. Actionable Directional Signals
    if curr_life == SignalLifecycleState.TRIGGERED and curr_dir in (DirectionalDecision.LONG, DirectionalDecision.SHORT):
        severity = AlertSeverity.ACTION
        reasons.append(f"DIRECTIONAL_{curr_dir}_TRIGGERED")
    elif curr_life == SignalLifecycleState.INVALIDATED:
        severity = AlertSeverity.RISK
        reasons.append("SIGNAL_INVALIDATED")
    elif curr_life == SignalLifecycleState.ARMED:
        severity = AlertSeverity.WATCH
        reasons.append("SETUP_ARMED")
    elif assessment.directional.setup.value in ("FAILED_BREAKOUT", "FAILED_BREAKDOWN"):
        severity = AlertSeverity.WATCH
        reasons.append(f"SETUP_{assessment.directional.setup.value}")
    elif prev_dir_str is not None and prev_dir_str != str(curr_dir):
        severity = AlertSeverity.WATCH
        reasons.append(f"DIRECTION_CHANGED_{prev_dir_str}_TO_{curr_dir}")

    # 2. Derivatives State Changes & Risk Alerts (R2.1-02)
    from .derivatives import is_severe_long_crowding, is_severe_short_crowding

    curr_d_regime = assessment.directional.derivatives_regime
    prev_d_regime_str = prev_state.get("derivatives_regime") if prev_state else None
    deriv_changed = prev_d_regime_str is not None and prev_d_regime_str != str(curr_d_regime)

    is_severe_long = is_severe_long_crowding(assessment.snapshot.derivatives, config)
    is_severe_short = is_severe_short_crowding(assessment.snapshot.derivatives, config)

    severity_order = {
        AlertSeverity.INFO: 0,
        AlertSeverity.WATCH: 1,
        AlertSeverity.ACTION: 2,
        AlertSeverity.RISK: 3,
    }

    if curr_d_regime in (DerivativesRegime.LONG_LIQUIDATION, DerivativesRegime.DELEVERAGING):
        severity = AlertSeverity.RISK
        shock_code = "LONG_LIQUIDATION_RISK" if curr_d_regime == DerivativesRegime.LONG_LIQUIDATION else "DELEVERAGING_RISK"
        if shock_code not in reasons:
            reasons.append(shock_code)
    elif is_severe_long or is_severe_short or curr_d_regime in (DerivativesRegime.LONG_CROWDING, DerivativesRegime.SHORT_CROWDING):
        if severity_order[AlertSeverity.WATCH] > severity_order[severity]:
            severity = AlertSeverity.WATCH
        if is_severe_long and "SEVERE_LONG_CROWDING" not in reasons:
            reasons.append("SEVERE_LONG_CROWDING")
        elif is_severe_short and "SEVERE_SHORT_CROWDING" not in reasons:
            reasons.append("SEVERE_SHORT_CROWDING")
        elif f"DERIVATIVES_{curr_d_regime}" not in reasons:
            reasons.append(f"DERIVATIVES_{curr_d_regime}")
    elif deriv_changed and curr_d_regime != DerivativesRegime.NEUTRAL:
        if severity_order[AlertSeverity.WATCH] > severity_order[severity]:
            severity = AlertSeverity.WATCH
        change_code = f"DERIVATIVES_REGIME_{prev_d_regime_str}_TO_{curr_d_regime}"
        if change_code not in reasons:
            reasons.append(change_code)

    # 3. Grid-Only / Grid-Change Triggers (R1-03)
    if grid_change_alert:
        grid_sev = AlertSeverity.WATCH
        if assessment.grid.decision == GridDecision.PAUSE and prev_grid is not None and prev_grid.decision != GridDecision.PAUSE:
            grid_sev = AlertSeverity.RISK
            reasons.append("GRID_STATUS_CHANGED")
        if "LOWER_BOUND_BREACHED" in assessment.grid.reason_codes:
            grid_sev = AlertSeverity.RISK
            if "LOWER_BOUND_BREACHED" not in reasons:
                reasons.append("LOWER_BOUND_BREACHED")
        if grid_sev != AlertSeverity.RISK:
            if prev_grid is not None and prev_grid.decision != assessment.grid.decision:
                grid_sev = AlertSeverity.WATCH
                reasons.append(f"GRID_DECISION_CHANGED_{prev_grid.decision}_TO_{assessment.grid.decision}")
            elif prev_grid is None and assessment.grid.decision != GridDecision.PAUSE:
                grid_sev = AlertSeverity.WATCH
                reasons.append(f"GRID_INITIALIZED_{assessment.grid.decision}")
            else:
                grid_sev = AlertSeverity.WATCH
                reasons.append("GRID_BOUNDARIES_SHIFTED")

        severity_order = {
            AlertSeverity.INFO: 0,
            AlertSeverity.WATCH: 1,
            AlertSeverity.ACTION: 2,
            AlertSeverity.RISK: 3,
        }
        if severity_order[grid_sev] > severity_order[severity]:
            severity = grid_sev

    if not reasons:
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
