"""RC1 WP-A Operational Readiness Test Suite.

Proves:
- >=25 fresh serialized cold starts (30 runs x 6 concurrent contenders = 180 attempts)
- >=25 serial restart/reopen cycles (30 cycles on the same DB)
- Predecessor-schema migrations
- All R8 guards installed after every successful init
- Failed initializer never yields a usable runtime object
- Initializer lock timeout fails closed
"""

from __future__ import annotations

import sqlite3
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from btc_quant_agent.config import LiveV1Config
from btc_quant_agent.execution.guard import ExecutionBlocked
from btc_quant_agent.live_db import connection, serialized_initializer
from btc_quant_agent.live_runtime import LiveV1Runtime
from btc_quant_agent.position_supervisor.supervisor import (
    REQUIRED_R8_GUARDS,
    PositionSupervisor,
)


def _assert_guards_present(path: Path | str) -> None:
    with connection(path) as db:
        triggers = {
            r[0]
            for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            ).fetchall()
        }
    for guard in REQUIRED_R8_GUARDS:
        assert guard in triggers, f"Missing R8 guard: {guard}"


def test_fresh_serialized_cold_starts_30x() -> None:
    """Prove >=25 fresh serialized cold starts with concurrent contenders."""
    num_runs = 30
    num_workers = 6

    for run_idx in range(num_runs):
        with tempfile.TemporaryDirectory(prefix=f"rc1-wp-a-cold-{run_idx}-") as tmp:
            db_path = Path(tmp) / "cold.sqlite"
            barrier = threading.Barrier(num_workers)

            def make_contender(b: threading.Barrier, p: Path):
                def contender(idx: int) -> dict[str, object]:
                    b.wait(timeout=10)
                    try:
                        supervisor = PositionSupervisor(p)
                        supervisor.assert_guards_installed()
                        return {"idx": idx, "status": "PASS"}
                    except Exception as exc:  # noqa: BLE001
                        return {"idx": idx, "status": "FAIL", "error": str(exc)}
                return contender

            with ThreadPoolExecutor(max_workers=num_workers) as pool:
                outcomes = list(pool.map(make_contender(barrier, db_path), range(num_workers)))

            failed = [o for o in outcomes if o["status"] == "FAIL"]
            assert not failed, f"Cold-start run {run_idx} had failures: {failed}"
            _assert_guards_present(db_path)


def test_serial_restart_reopen_cycles_30x() -> None:
    """Prove >=25 serial restart/reopen cycles on the same database path."""
    num_cycles = 30
    with tempfile.TemporaryDirectory(prefix="rc1-wp-a-reopen-") as tmp:
        db_path = Path(tmp) / "lifecycle.sqlite"

        for cycle_idx in range(num_cycles):
            supervisor = PositionSupervisor(db_path)
            supervisor.assert_guards_installed()
            _assert_guards_present(db_path)
            # Verify data persistence across cycles
            with connection(db_path) as db:
                count = db.execute("SELECT COUNT(*) FROM live_position_events").fetchone()[0]
                assert count == cycle_idx
                db.execute(
                    "INSERT INTO live_position_events (event_id, event_hash, trigger, symbol, "
                    "source_hash, observed_at_ms, payload, environment, credential_namespace, "
                    "account_id, position_side, position_authority_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"evt-{cycle_idx}",
                        f"hash-{cycle_idx}",
                        "PERIODIC",
                        "BTCUSDT",
                        f"src-{cycle_idx}",
                        1700000000000 + cycle_idx,
                        "{}",
                        "DRY_RUN",
                        "NONE",
                        "test-account",
                        "BOTH",
                        "DRY_RUN:NONE:test-account:BTCUSDT:BOTH",
                    ),
                )


def test_predecessor_schema_migration_legacy_dispatches() -> None:
    """Prove migration of predecessor schema with legacy dispatches and events."""
    with tempfile.TemporaryDirectory(prefix="rc1-wp-a-mig-") as tmp:
        db_path = Path(tmp) / "predecessor.sqlite"

        # Create predecessor schema lacking current R7/R8 columns
        with connection(db_path) as db:
            db.executescript("""
                CREATE TABLE live_position_case_dispatches (
                    event_id TEXT PRIMARY KEY,
                    event_hash TEXT NOT NULL UNIQUE,
                    case_hash TEXT NOT NULL DEFAULT '',
                    symbol TEXT NOT NULL,
                    state TEXT NOT NULL,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    lease_token TEXT,
                    lease_expires_at_ms INTEGER NOT NULL DEFAULT 0,
                    created_at_ms INTEGER NOT NULL,
                    updated_at_ms INTEGER NOT NULL
                );
                CREATE TABLE live_position_events (
                    event_id TEXT PRIMARY KEY,
                    event_hash TEXT NOT NULL UNIQUE,
                    trigger TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    source_hash TEXT NOT NULL,
                    observed_at_ms INTEGER NOT NULL,
                    payload TEXT NOT NULL
                );
                INSERT INTO live_position_case_dispatches (
                    event_id, event_hash, case_hash, symbol, state, created_at_ms, updated_at_ms
                ) VALUES (
                    'legacy-evt-1', 'legacy-hash-1', 'legacy-case-hash-1', 'BTCUSDT', 'PENDING', 1000, 1000
                );
                INSERT INTO live_position_events (
                    event_id, event_hash, trigger, symbol, source_hash, observed_at_ms, payload
                ) VALUES (
                    'legacy-evt-1', 'legacy-hash-1', 'OPEN', 'BTCUSDT', 'src-1', 1000, '{}'
                );
            """)

        # Execute PositionSupervisor initializer
        supervisor = PositionSupervisor(db_path)
        supervisor.assert_guards_installed()
        _assert_guards_present(db_path)

        # Verify predecessor rows were upgraded
        with connection(db_path) as db:
            row = db.execute(
                "SELECT position_case_hash, case_hash, analysis_completed, dispatch_authority_json "
                "FROM live_position_case_dispatches WHERE event_id = 'legacy-evt-1'"
            ).fetchone()
            assert row is not None
            assert row["position_case_hash"] == "legacy-case-hash-1"
            assert row["case_hash"] == "legacy-case-hash-1"
            assert row["analysis_completed"] == 0
            assert row["dispatch_authority_json"] == ""

            evt_cols = [
                r["name"] for r in db.execute("PRAGMA table_info(live_position_events)").fetchall()
            ]
            for col in ("environment", "credential_namespace", "account_id", "position_side", "position_authority_key"):
                assert col in evt_cols


def test_all_r8_guards_enforce_safety_semantics() -> None:
    """Prove that installed R8 guards mechanically reject illegal mutations."""
    with tempfile.TemporaryDirectory(prefix="rc1-wp-a-guards-") as tmp:
        db_path = Path(tmp) / "guards.sqlite"
        supervisor = PositionSupervisor(db_path)
        supervisor.assert_guards_installed()

        with connection(db_path) as db:
            # 1. Blank PENDING required on INSERT
            with pytest.raises(sqlite3.IntegrityError, match="DISPATCH_INSERT_REQUIRES_BLANK_PENDING"):
                db.execute(
                    "INSERT INTO live_position_case_dispatches (event_id, event_hash, symbol, state, created_at_ms, updated_at_ms) "
                    "VALUES ('e1', 'h1', 'BTCUSDT', 'DONE', 1000, 1000)"
                )

            # Insert valid blank PENDING
            db.execute(
                "INSERT INTO live_position_case_dispatches (event_id, event_hash, symbol, state, created_at_ms, updated_at_ms) "
                "VALUES ('e1', 'h1', 'BTCUSDT', 'PENDING', 1000, 1000)"
            )

            # 2. Deletion blocked
            with pytest.raises(sqlite3.IntegrityError, match="DISPATCH_DELETE_BLOCKED"):
                db.execute("DELETE FROM live_position_case_dispatches WHERE event_id = 'e1'")

            # 3. State DONE requires analysis_completed = 1
            with pytest.raises(sqlite3.IntegrityError, match="DONE_REQUIRES_ANALYSIS_COMPLETION"):
                db.execute("UPDATE live_position_case_dispatches SET state = 'DONE' WHERE event_id = 'e1'")

            # 4. Events immutable delete
            db.execute(
                "INSERT INTO live_position_events (event_id, event_hash, trigger, symbol, source_hash, observed_at_ms, payload) "
                "VALUES ('e1', 'h1', 'OPEN', 'BTCUSDT', 'src', 1000, '{}')"
            )
            with pytest.raises(sqlite3.IntegrityError, match="POSITION_EVENT_IMMUTABLE_DELETE_BLOCKED"):
                db.execute("DELETE FROM live_position_events WHERE event_id = 'e1'")

            # 5. Events immutable update
            with pytest.raises(sqlite3.IntegrityError, match="POSITION_EVENT_IMMUTABLE_UPDATE_BLOCKED"):
                db.execute("UPDATE live_position_events SET symbol = 'ETHUSDT' WHERE event_id = 'e1'")


def test_failed_initializer_never_yields_usable_runtime() -> None:
    """Prove that a failed initializer fails closed and never returns a usable runtime."""
    with tempfile.TemporaryDirectory(prefix="rc1-wp-a-fail-") as tmp:
        db_path = Path(tmp) / "corrupt.sqlite"

        # Write a non-database file to simulate initialization failure
        db_path.write_text("NOT_A_VALID_SQLITE_FILE")

        # Initializer must fail closed
        with pytest.raises((sqlite3.DatabaseError, RuntimeError)):
            PositionSupervisor(db_path)

        tactical_service = SimpleNamespace(market_watch=Mock(), store=Mock(), compiler=Mock())
        config = LiveV1Config(runtime_enabled=True, sqlite_path=str(db_path))

        with pytest.raises((sqlite3.DatabaseError, RuntimeError)):
            LiveV1Runtime.create(config, tactical_service)


def test_uninitialized_runtime_cannot_start() -> None:
    """Prove that an uninitialized runtime cannot enter started state."""
    import asyncio
    runtime = SimpleNamespace(
        _started=False,
        _initialized=False,
        supervisor=SimpleNamespace(assert_guards_installed=Mock()),
    )
    with pytest.raises(ExecutionBlocked, match="DATABASE_INITIALIZATION_REQUIRED"):
        asyncio.run(LiveV1Runtime.start(runtime))  # type: ignore[arg-type]


def test_missing_guards_runtime_cannot_start() -> None:
    """Prove that a runtime with missing guards cannot enter started state."""
    import asyncio
    def missing_guards() -> None:
        raise RuntimeError("R8_GUARDS_MISSING: ['trg_live_position_dispatch_blank_insert']")

    runtime = SimpleNamespace(
        _started=False,
        _initialized=True,
        supervisor=SimpleNamespace(assert_guards_installed=missing_guards),
    )
    with pytest.raises(RuntimeError, match="R8_GUARDS_MISSING"):
        asyncio.run(LiveV1Runtime.start(runtime))  # type: ignore[arg-type]


def test_initializer_lock_timeout_fails_closed() -> None:
    """Prove that a contender unable to acquire the initializer lock fails closed."""
    with tempfile.TemporaryDirectory(prefix="rc1-wp-a-lock-") as tmp:
        db_path = Path(tmp) / "locked.sqlite"

        # Hold the initializer lock externally
        with serialized_initializer(db_path, timeout_seconds=5.0):
            # Attempt to initialize with short timeout from another thread
            barrier = threading.Barrier(2)
            error: list[Exception] = []

            def competing() -> None:
                barrier.wait()
                try:
                    with serialized_initializer(db_path, timeout_seconds=0.1):
                        PositionSupervisor(db_path)
                except TimeoutError as exc:
                    error.append(exc)

            t = threading.Thread(target=competing)
            t.start()
            barrier.wait()
            t.join()

            assert len(error) == 1
            assert isinstance(error[0], TimeoutError)
            assert "INITIALIZER" in str(error[0])
