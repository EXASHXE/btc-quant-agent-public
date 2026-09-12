"""Declared column projections and monotonic compatibility for active SQLite stores."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable

SCHEMA_VERSION = 1
COLUMNS = {
    "derivative_snapshots": ("symbol", "collection_id", "collection_started_at_ms", "observed_at_ms", "collector_version", "mark_price", "index_price", "premium_bps", "funding_rate", "funding_time_ms", "open_interest", "open_interest_time_ms", "open_interest_change_pct", "taker_buy_sell_ratio", "taker_time_ms", "basis_rate", "basis_time_ms", "long_short_account_ratio", "long_short_time_ms", "order_book_imbalance", "spread_bps", "order_book_time_ms", "field_availability_json", "endpoint_errors_json", "payload_hash"),
    "collection_runs": ("run_id", "started_at_ms", "finished_at_ms", "status", "attempted_fields", "successful_fields", "error_summary", "trigger_source", "scheduled_slot_ms", "endpoint_telemetry_json", "evidence_epoch_id"),
    "scan_observations": ("observation_id", "campaign_id", "scheduled_slot_ms", "collection_started_at_ms", "observed_at_ms", "status", "market_data_health", "decision_close_ms", "regime", "atr_15m", "atr_percentile_decile", "opportunity_present", "opportunity_id", "detector_id", "setup", "registry_version", "git_sha", "config_hash", "network_data_errors_json", "trigger_source", "payload_hash"),
    "outcomes": ("observation_id", "horizon_minutes", "reference_time_ms", "reference_price", "future_high", "future_low", "future_close", "future_range_atr", "max_up_excursion_atr", "max_down_excursion_atr", "max_abs_excursion_atr", "resolved_at_ms", "resolution_source", "payload_hash"),
    "integrity_events": ("event_id", "occurred_at_ms", "kind", "observation_id"),
    "depth_events": ("event_time_ms", "final_update_id", "receive_time_ms", "receive_monotonic_ns", "payload_json", "payload_hash"),
    "agg_trades": ("aggregate_trade_id", "event_time_ms", "transaction_time_ms", "receive_time_ms", "receive_monotonic_ns", "price", "quantity", "buyer_is_maker", "aggressive_side", "payload_hash"),
    "gaps": ("id", "start_ms", "end_ms", "kind", "detail"),
    "book_samples": ("event_time_ms", "final_update_id", "receive_time_ms", "spread_bps", "top1_imbalance", "top5_imbalance", "top20_imbalance", "microprice", "ofi"),
    "aggregates": ("interval_ms", "bucket_start_ms", "trade_count", "buy_quantity", "sell_quantity", "buy_notional", "sell_notional", "book_sample_count", "spread_bps_sum", "top1_imbalance_sum", "top5_imbalance_sum", "top20_imbalance_sum", "ofi_sum", "gap_count"),
    "sessions": ("session_id", "stream", "start_ms", "end_ms", "status", "instance_id", "last_heartbeat_ms"),
    "audit_counters": ("name", "value"),
    "process_instances": ("instance_id", "start_ms", "last_heartbeat_ms", "end_ms", "status"),
    "coverage_segments": ("id", "instance_id", "stream", "start_ms", "end_ms", "sequence_valid", "status"),
    "clock_measurements": ("measured_at_ms", "request_send_ms", "response_receive_ms", "server_time_ms", "offset_ms", "rtt_ms", "quality"),
    "signals": ("signal_id", "fingerprint", "status", "created_at_ms", "expires_at_ms", "payload_json"),
    "opportunities": ("opportunity_id", "detector_id", "detected_at_ms", "expires_at_ms", "payload_json"),
    "shadow_trades": ("signal_id", "outcome", "entry_price", "exit_price", "r_multiple", "entered_at_ms", "exited_at_ms", "payload_json"),
    "runtime_events": ("id", "event_type", "created_at_ms", "payload_json"),
    "user_decisions": ("id", "signal_id", "decision", "actual_entry", "decided_at_ms"),
    "execution_plans": ("plan_id", "kind", "status", "created_at_ms", "expires_at_ms", "payload_json"),
    "execution_orders": ("id", "plan_id", "role", "exchange_order_id", "status", "created_at_ms", "payload_json"),
    "h39_source_partitions": ("partition_name", "partition_path", "partition_sha256", "file_size_bytes", "min_time_ms", "max_time_ms", "finalized", "first_seen_utc", "last_verified_utc"),
    "h39_blind_validation_ledger": ("decision_close_ms", "slot_utc", "m1_trade_imbalance_5m", "m2_trade_imbalance_15m", "m3_ofi_5m", "m4_top5_depth_imbalance_5m", "m5_top20_depth_imbalance_5m", "m6_microprice_deviation_1m", "m7_pressure_agreement", "m8_pressure_divergence", "trailing_return_15m", "trailing_return_60m", "trailing_atr_ratio_15m", "trailing_atr_15m", "decision_close_price", "eligible", "rejection_reason", "book_sample_count_15m", "trade_count_15m", "feature_window_start_ms", "feature_window_end_ms", "reference_time_ms", "target_60m_ms", "target_240m_ms", "source_partitions", "source_partition_hashes", "protocol_hash", "clarification_hash", "input_contract_version", "code_version_sha", "ingested_at_utc"),
    "h39_one_shot_executions": ("execution_key", "freeze_manifest_sha256", "freeze_commit_sha", "unblind_cutoff_ms", "protocol_hash", "clarification_hash", "started_at_utc", "completed_at_utc", "state", "result_manifest_sha256", "executing_git_sha"),
}
FORWARD_TABLES = ("derivative_snapshots", "collection_runs")
OPPORTUNITY_TABLES = ("scan_observations", "outcomes", "integrity_events")
MICROSTRUCTURE_TABLES = ("depth_events", "agg_trades", "gaps", "book_samples", "aggregates", "sessions", "audit_counters", "process_instances", "coverage_segments", "clock_measurements")
REPOSITORY_TABLES = ("signals", "opportunities", "user_decisions", "shadow_trades", "runtime_events", "execution_plans", "execution_orders")


class SQLiteSchemaError(ValueError):
    pass


def projection(table: str) -> str:
    return ",".join(COLUMNS[table])


def schema_version(connection: sqlite3.Connection) -> int:
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version not in (0, SCHEMA_VERSION):
        raise SQLiteSchemaError(f"unsupported SQLite schema version {version}: NOT_TESTABLE")
    return version


def require_columns(connection: sqlite3.Connection, tables: Iterable[str], *, legacy_optional: Iterable[str] = ()) -> None:
    optional = set(legacy_optional) if schema_version(connection) == 0 else set()
    for table in tables:
        actual = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
        missing = set(COLUMNS[table]) - optional - actual
        if missing:
            raise SQLiteSchemaError(f"SQLite schema {table} missing {sorted(missing)}: NOT_TESTABLE")


def prepare_schema(connection: sqlite3.Connection, tables: Iterable[str], *, legacy_optional: Iterable[str] = ()) -> None:
    version = schema_version(connection)
    # Legacy 0 is an explicit adapter: absent tables may be created, but an
    # existing table must have every core column. Version 1 never self-heals.
    present = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    require_columns(connection, tables if version == SCHEMA_VERSION else (table for table in tables if table in present), legacy_optional=legacy_optional)


def finish_schema(connection: sqlite3.Connection, tables: Iterable[str]) -> None:
    require_columns(connection, tables)
    connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
