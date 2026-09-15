"""v0.5.0 R05A AG-04 regression tests: GET /health read-only store inspection.

Permanent regression suite for the AG-04 bounded repair (commit 81978ff), which
rerouted ``QuantService.health`` onto the read-only ``ForwardDerivativeStore
.read_status`` inspection entrypoint so a health check no longer instantiates
the writer-mode ``ForwardDerivativeStore`` (which previously created the
operational store directory, the SQLite database, WAL sidecars and the full
schema on every probe).

The acceptance tests exercise the real health implementation: the app is built
through ``api.create_app`` with a temporary runtime repository, the ``/health``
handler is resolved through the FastAPI routing table and invoked directly, and
only external dependencies (scheduler metadata, Binance connectivity) are
mocked. Because app construction may initialize the normal runtime repository,
storage snapshots are taken after app construction and before the GET and are
compared afterwards: the invariant applies to effects caused by the request.
The production health path inspects the cwd-relative ``data/forward/BTCUSDT/
derivatives.sqlite3`` store, so every test runs inside a temporary working
directory (``tempfile.mkdtemp`` outside the repository) that also carries a
copy of the repository ``configs`` tree for the epoch/registry loaders.

Test map:
- T1: missing parent directory — health degrades explicitly; nothing created.
- T2: existing parent without DB — directory membership unchanged; no SQLite
  or sidecar file appears.
- T3: populated valid store — DB bytes, schema, and row content are
  byte-preserved by the real GET.
- T4: incomplete/unsupported schema — fail-closed degradation with a stable
  error classification; no migration; no sidecar files.
- T5: main runtime repository — no signal/decision/event/execution rows are
  created or mutated by the GET.
- T6: defense-in-depth — INSERT/UPDATE/DELETE/DDL are denied on the read-only
  inspection connection (``PRAGMA query_only``); bytes unchanged.
- T7: control — explicit writer construction still initializes the schema and
  accepts writes (the repair did not globally disable the store).
- T8 (R05AR): crash-leftover WAL without SHM — health fails closed with the
  ``FORWARD_STORE_WAL_RECOVERY_REQUIRED`` classification; no ``-shm`` is
  materialized; DB/WAL bytes and directory membership are unchanged.
- T9 (R05AR): pre-existing WAL + SHM — conservative degrade (production never
  opens a store carrying a non-empty WAL); no new files; existing sidecars,
  DB bytes, and rows untouched.
- T10 (R05AR): negative guards — across the missing, checkpointed, and
  crash-leftover WAL states the real health path never invokes writer
  initialization, schema DDL helpers, or a writer-mode constructor
  (supplemental spies; the storage proofs of T1-T4/T8/T9 stay primary).
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

from helpers import signal
from test_forward_derivatives import _record

from btc_quant_agent import api
from btc_quant_agent.config import AppConfig, StorageConfig
from btc_quant_agent.data.forward_store import ForwardDerivativeStore
from btc_quant_agent.storage import Repository

FORWARD_STORE_RELATIVE = Path("data/forward/BTCUSDT/derivatives.sqlite3")
SCHEDULER_PROBE: dict[str, Any] = {"unit": "probe", "detected": False, "active": False}
RUNTIME_TABLES = (
    "signals",
    "user_decisions",
    "shadow_trades",
    "runtime_events",
    "opportunities",
    "execution_plans",
    "execution_orders",
)


class R05AHealthReadOnlyInspectionTests(unittest.TestCase):
    """AG-04 acceptance: GET /health must inspect the forward store read-only."""

    def setUp(self) -> None:
        self._previous_cwd = Path.cwd()
        self._temp = Path(tempfile.mkdtemp(prefix="r05a-ag04-"))
        os.chdir(self._temp)
        shutil.copytree(Path(__file__).resolve().parents[1] / "configs", self._temp / "configs")

    def tearDown(self) -> None:
        os.chdir(self._previous_cwd)
        shutil.rmtree(self._temp, ignore_errors=True)

    # -- helpers ---------------------------------------------------------

    def _create_app(self) -> Callable[[], dict[str, Any]]:
        config = AppConfig(storage=StorageConfig(sqlite_path=str(self._temp / "runtime.db")))
        with patch("btc_quant_agent.api.load_config", return_value=config):
            app = api.create_app()
        return next(
            route.endpoint
            for route in app.routes
            if getattr(route, "path", None) == "/health"
            and "GET" in getattr(route, "methods", set())
        )

    def _invoke_health(self, health_fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        with (
            patch(
                "btc_quant_agent.data.forward_store.scheduler_status",
                return_value=SCHEDULER_PROBE,
            ),
            patch(
                "btc_quant_agent.data.binance.BinancePublicClient.connectivity",
                return_value=True,
            ),
        ):
            return health_fn()

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _sqlite_sidecars(self, store_path: Path) -> list[str]:
        return sorted(
            sidecar.name
            for sidecar in store_path.parent.glob(store_path.name + "-*")
            if sidecar.name.endswith(("-wal", "-shm"))
        )

    def _sidecar_hashes(self, store_path: Path) -> dict[str, str]:
        return {
            name: self._sha256(store_path.parent / name)
            for name in self._sqlite_sidecars(store_path)
        }

    def _forward_tree_files(self) -> list[str]:
        forward_root = self._temp / "data" / "forward"
        if not forward_root.is_dir():
            return []
        return sorted(
            path.relative_to(self._temp).as_posix()
            for path in forward_root.rglob("*")
            if path.is_file()
        )

    def _snapshot_forward_state(self) -> dict[str, Any]:
        """Schema, pragma, and row state read through the production read-only path."""
        store = ForwardDerivativeStore.open_read_only(self._temp / FORWARD_STORE_RELATIVE)
        with store._connect() as connection:
            tables = tuple(
                str(row["name"])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ).fetchall()
            )
            columns = {
                table: tuple(
                    str(row["name"])
                    for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
                )
                for table in tables
            }
            user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            rows = [
                tuple(row)
                for row in connection.execute(
                    "SELECT symbol, collection_id, mark_price, payload_hash "
                    "FROM derivative_snapshots ORDER BY observed_at_ms"
                ).fetchall()
            ]
        return {"tables": tables, "columns": columns, "user_version": user_version, "rows": rows}

    def _snapshot_runtime_state(self) -> dict[str, Any]:
        """Tables, per-table row counts, and bytes of the main runtime repository."""
        db_path = self._temp / "runtime.db"
        connection = sqlite3.connect(str(db_path))
        try:
            tables = tuple(
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ).fetchall()
            )
            counts = {
                table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in RUNTIME_TABLES
            }
        finally:
            connection.close()
        return {"tables": tables, "counts": counts, "sha256": self._sha256(db_path)}

    def _populate_forward_store(self) -> None:
        """Populate the store through the writer workflow, before any snapshot."""
        store_path = self._temp / FORWARD_STORE_RELATIVE
        writer = ForwardDerivativeStore(store_path)
        self.assertTrue(writer.append(_record()))
        self.assertEqual(writer.count(), 1)
        # The writer's contextmanager connections are closed per operation, so
        # the WAL was checkpointed and the sidecars removed on the last close.
        self.assertEqual(self._sqlite_sidecars(store_path), [])

    def _capture_and_restore_wal_image(self, *, preserve_shm: bool) -> tuple[Path, Path, Path]:
        """Reproduce the crash/recovery filesystem state on a populated store.

        Commits one extra row through a raw connection so a genuine non-empty
        WAL image (real WAL-mode committed frames, not a fake empty file)
        exists while the connection is open, captures it together with the
        matching ``-shm``, closes the connection (which checkpoints and
        removes the sidecars), then restores the WAL image — and the SHM when
        ``preserve_shm`` — so no SQLite connection is left open. Returns
        ``(store, wal, shm)`` paths.
        """
        store_path = self._temp / FORWARD_STORE_RELATIVE
        wal_path = store_path.parent / (store_path.name + "-wal")
        shm_path = store_path.parent / (store_path.name + "-shm")
        connection = sqlite3.connect(str(store_path))
        try:
            connection.execute("PRAGMA busy_timeout=10000")
            connection.execute(
                "INSERT INTO derivative_snapshots (symbol, collection_id, "
                "collection_started_at_ms, observed_at_ms, collector_version, "
                "field_availability_json, endpoint_errors_json, payload_hash) "
                "VALUES ('BTCUSDT', 'run-wal-crash', 1, 1, '0.3.14', '{}', '{}', 'wal')"
            )
            connection.commit()
            wal_image = wal_path.read_bytes()
            shm_image = shm_path.read_bytes() if shm_path.exists() else None
        finally:
            connection.close()
        # The last close checkpointed the WAL and removed both sidecars.
        self.assertFalse(wal_path.exists())
        self.assertFalse(shm_path.exists())
        # Restore the genuine WAL image: DB exists, non-empty -wal, and the
        # -shm absent (crash-leftover state) or restored (live-WAL state).
        wal_path.write_bytes(wal_image)
        if preserve_shm:
            self.assertIsNotNone(shm_image)
            shm_path.write_bytes(shm_image)
            self.assertTrue(shm_path.exists())
        else:
            self.assertFalse(shm_path.exists())
        self.assertGreater(wal_path.stat().st_size, 0)
        return store_path, wal_path, shm_path

    def _assert_missing_store_degradation(self, forward: dict[str, Any]) -> None:
        """The explicit degraded response designed for a missing store."""
        self.assertEqual(Path(forward["store_path"]), FORWARD_STORE_RELATIVE)
        self.assertIs(forward["store_exists"], False)
        self.assertEqual(forward["health"], "DEGRADED")
        self.assertEqual(forward["sample_count"], 0)
        self.assertEqual(forward["collection_status"], "NOT_COLLECTING")
        self.assertIs(forward["scheduler_detected"], False)
        self.assertIs(forward["scheduler_active"], False)
        self.assertIsNone(forward["latest_collection_run"])
        self.assertNotIn("error", forward)

    # -- A04-T1 ----------------------------------------------------------

    def test_a04_t1_missing_parent_directory_stays_absent_and_degrades(self) -> None:
        """Missing store parent: health degrades as designed and creates nothing."""
        # Setup: no data/forward tree at all; app construction; filesystem snapshot.
        self.assertFalse((self._temp / "data").exists())
        health_fn = self._create_app()
        before_files = self._forward_tree_files()
        # Invoke the real /health endpoint.
        report = self._invoke_health(health_fn)
        # Result is usable/degraded as designed for a missing store.
        self._assert_missing_store_degradation(report["forward_derivatives"])
        # The request created no directory, database, or sidecar files.
        self.assertFalse((self._temp / "data").exists())
        self.assertFalse((self._temp / FORWARD_STORE_RELATIVE).exists())
        self.assertEqual(self._forward_tree_files(), before_files)
        self.assertEqual(self._sqlite_sidecars(self._temp / FORWARD_STORE_RELATIVE), [])

    # -- A04-T2 ----------------------------------------------------------

    def test_a04_t2_existing_parent_without_db_leaves_directory_unchanged(self) -> None:
        """Existing parent, missing DB: directory membership unchanged, no files."""
        # Setup: create only the store directory; snapshot its (empty) membership.
        btcusdt_dir = (self._temp / FORWARD_STORE_RELATIVE).parent
        btcusdt_dir.mkdir(parents=True)
        health_fn = self._create_app()
        before_files = self._forward_tree_files()
        before_membership = sorted(path.name for path in btcusdt_dir.iterdir())
        self.assertEqual(before_membership, [])
        # Invoke the real /health endpoint.
        report = self._invoke_health(health_fn)
        self._assert_missing_store_degradation(report["forward_derivatives"])
        # Directory membership is unchanged; no SQLite or sidecar file appears.
        self.assertEqual(sorted(path.name for path in btcusdt_dir.iterdir()), before_membership)
        self.assertFalse((self._temp / FORWARD_STORE_RELATIVE).is_file())
        self.assertEqual(self._forward_tree_files(), before_files)

    # -- A04-T3 ----------------------------------------------------------

    def test_a04_t3_populated_store_is_byte_preserved_by_real_health(self) -> None:
        """Populated valid DB: the GET preserves bytes, schema, and row content."""
        # Setup: populate the store through the writer workflow before any snapshot.
        store_path = self._temp / FORWARD_STORE_RELATIVE
        self._populate_forward_store()
        health_fn = self._create_app()
        # Snapshot: directory file names, DB/sidecar bytes, schema, and rows.
        before_files = self._forward_tree_files()
        before_db_sha256 = self._sha256(store_path)
        before_sidecars = self._sidecar_hashes(store_path)
        before_state = self._snapshot_forward_state()
        # Invoke the real /health endpoint.
        report = self._invoke_health(health_fn)
        forward = report["forward_derivatives"]
        # The read-only inspection actually read the store (no fail-closed error).
        self.assertIs(forward["store_exists"], True)
        self.assertEqual(forward["health"], "DEGRADED")  # scheduler probe inactive
        self.assertEqual(forward["sample_count"], 1)
        self.assertEqual(forward["collection_status"], "SCHEDULER_NOT_ACTIVE")
        self.assertEqual(forward["latest_collection_run"]["run_id"], "run-1")
        self.assertEqual(forward["latest_collection_run"]["status"], "COMPLETE")
        self.assertNotIn("error", forward)
        self.assertIs(report["binance_public_data"], True)
        # No new files, and all captured bytes/data/schema are unchanged.
        self.assertEqual(self._forward_tree_files(), before_files)
        self.assertEqual(self._sha256(store_path), before_db_sha256)
        self.assertEqual(self._sidecar_hashes(store_path), before_sidecars)
        self.assertEqual(self._snapshot_forward_state(), before_state)

    # -- A04-T4 ----------------------------------------------------------

    def test_a04_t4_incomplete_schema_fails_closed_without_migration(self) -> None:
        """Incomplete schema: health fails closed, DB untouched, no migration."""
        # Setup: an incomplete SQLite file created WITHOUT the writer initializer.
        store_path = self._temp / FORWARD_STORE_RELATIVE
        store_path.parent.mkdir(parents=True)
        connection = sqlite3.connect(str(store_path))
        try:
            connection.execute("CREATE TABLE other(x)")
            connection.commit()
        finally:
            connection.close()
        health_fn = self._create_app()
        before_files = self._forward_tree_files()
        before_db_sha256 = self._sha256(store_path)
        # Invoke the real /health endpoint.
        report = self._invoke_health(health_fn)
        forward = report["forward_derivatives"]
        # Health degrades/fails closed with a stable error classification.
        self.assertIs(forward["store_exists"], True)
        self.assertEqual(forward["health"], "DEGRADED")
        self.assertEqual(forward["sample_count"], 0)
        self.assertEqual(forward["collection_status"], "NOT_COLLECTING")
        self.assertIn("error", forward)
        self.assertIsInstance(forward["error"], str)
        self.assertTrue(forward["error"])
        # Bytes unchanged, table/column set unchanged, no migration, no sidecars.
        self.assertEqual(self._sha256(store_path), before_db_sha256)
        connection = sqlite3.connect(str(store_path))
        try:
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            columns = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(other)").fetchall()
            }
        finally:
            connection.close()
        self.assertEqual(tables, {"other"})
        self.assertNotIn("derivative_snapshots", tables)
        self.assertNotIn("collection_runs", tables)
        self.assertEqual(columns, {"x"})
        self.assertEqual(self._forward_tree_files(), before_files)

    # -- A04-T5 ----------------------------------------------------------

    def test_a04_t5_main_runtime_repository_unchanged_during_health(self) -> None:
        """The GET creates or mutates no main-runtime signal/decision/event rows."""
        # Setup: app construction initializes the normal runtime repository.
        repo = Repository(str(self._temp / "runtime.db"))
        seeded = signal()
        self.assertTrue(repo.save_signal(seeded, 90))
        health_fn = self._create_app()
        # Snapshot after app construction and before the GET.
        before = self._snapshot_runtime_state()
        self.assertEqual(before["counts"]["signals"], 1)
        # Invoke the real /health endpoint.
        report = self._invoke_health(health_fn)
        self.assertIn("forward_derivatives", report)
        after = self._snapshot_runtime_state()
        # No repository event/signal/decision/execution rows created or mutated.
        self.assertEqual(after["tables"], before["tables"])
        self.assertEqual(after["counts"], before["counts"])
        self.assertEqual(after["sha256"], before["sha256"])
        persisted = repo.get_signal(seeded.signal_id)
        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.status, seeded.status)

    # -- A04-T6 ----------------------------------------------------------

    def test_a04_t6_read_only_inspection_path_denies_writes(self) -> None:
        """Defense-in-depth: writes are denied on the read-only inspection path."""
        # Setup: a populated store, then the production read-only inspection instance.
        store_path = self._temp / FORWARD_STORE_RELATIVE
        self._populate_forward_store()
        store = ForwardDerivativeStore.open_read_only(store_path)
        before_db_sha256 = self._sha256(store_path)
        with store._connect() as connection:
            # Read-only pragma state on the sidecar-free inspection connection.
            self.assertEqual(connection.execute("PRAGMA query_only").fetchone()[0], 1)
            self.assertEqual(connection.execute("PRAGMA busy_timeout").fetchone()[0], 10_000)
            # INSERT/UPDATE/DELETE/DDL are denied with a readonly-database error.
            with self.assertRaises(sqlite3.OperationalError) as insert:
                connection.execute(
                    "INSERT INTO derivative_snapshots (symbol, collection_id, "
                    "collection_started_at_ms, observed_at_ms, collector_version, "
                    "field_availability_json, endpoint_errors_json, payload_hash) "
                    "VALUES ('BTCUSDT', 'attack', 1, 1, '0.0.0', '{}', '{}', 'hash')"
                )
            with self.assertRaises(sqlite3.OperationalError) as update:
                connection.execute("UPDATE derivative_snapshots SET mark_price = -1")
            with self.assertRaises(sqlite3.OperationalError) as delete:
                connection.execute("DELETE FROM derivative_snapshots")
            with self.assertRaises(sqlite3.OperationalError) as ddl:
                connection.execute("CREATE TABLE injected(x)")
        for raised in (insert, update, delete, ddl):
            self.assertIn("readonly", str(raised.exception))
        # A missing store path also fails closed on the inspection instance
        # instead of creating or opening anything.
        missing = ForwardDerivativeStore.open_read_only(store_path.parent / "absent.sqlite3")
        with self.assertRaises(FileNotFoundError):
            missing.count()
        # The denied writes left the database bytes untouched, with no sidecars.
        self.assertEqual(self._sha256(store_path), before_db_sha256)
        self.assertEqual(self._sqlite_sidecars(store_path), [])

    # -- A04-T7 ----------------------------------------------------------

    def test_a04_t7_writer_construction_still_initializes_and_accepts_writes(self) -> None:
        """Control: the writer path still initializes schema and accepts writes."""
        # Explicit writer construction in a normal test context.
        writer_path = self._temp / "writer-store" / "derivatives.sqlite3"
        writer = ForwardDerivativeStore(writer_path)
        record = _record(collection_id="run-ag04-t7")
        self.assertEqual(record.trigger_source, "MANUAL")
        # The writer still creates the expected schema and accepts the write.
        self.assertTrue(writer.append(record))
        self.assertEqual(writer.count(), 1)
        self.assertTrue(writer_path.parent.is_dir())
        connection = sqlite3.connect(str(writer_path))
        try:
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        finally:
            connection.close()
        self.assertIn("derivative_snapshots", tables)
        self.assertIn("collection_runs", tables)

    # -- A04-T8 (R05AR) ---------------------------------------------------

    def test_a04_t8_crash_leftover_wal_without_shm_fails_closed(self) -> None:
        """Crash-leftover WAL without SHM: fail closed before SQLite recovers.

        The restored state is DB + non-empty -wal + absent -shm, built from
        genuine WAL-mode committed content. The real GET must degrade with the
        stable classification BEFORE any SQLite open, leaving the -shm absent
        and every captured byte and directory member unchanged.
        """
        self._populate_forward_store()
        store_path, wal_path, shm_path = self._capture_and_restore_wal_image(
            preserve_shm=False
        )
        health_fn = self._create_app()
        before_files = self._forward_tree_files()
        before_db_sha256 = self._sha256(store_path)
        before_wal_sha256 = self._sha256(wal_path)
        # Invoke the real /health endpoint.
        report = self._invoke_health(health_fn)
        forward = report["forward_derivatives"]
        # Deterministic fail-closed degradation with the stable classification.
        self.assertIs(forward["store_exists"], True)
        self.assertEqual(forward["health"], "DEGRADED")
        self.assertEqual(forward["sample_count"], 0)
        self.assertEqual(forward["collection_status"], "NOT_COLLECTING")
        self.assertIn("FORWARD_STORE_WAL_RECOVERY_REQUIRED", forward["error"])
        # No -shm was created; WAL, DB, and directory membership are unchanged.
        self.assertFalse(shm_path.exists())
        self.assertEqual(self._sha256(store_path), before_db_sha256)
        self.assertEqual(self._sha256(wal_path), before_wal_sha256)
        self.assertEqual(self._forward_tree_files(), before_files)
        self.assertEqual(self._sqlite_sidecars(store_path), [wal_path.name])

    # -- A04-T9 (R05AR) ---------------------------------------------------

    def test_a04_t9_preexisting_wal_and_shm_degrade_without_new_files(self) -> None:
        """WAL + SHM pre-existing: conservative degrade, nothing new, rows intact.

        Production refuses to open any store carrying a non-empty WAL, so both
        sidecars are preserved untouched — no new filesystem member, no schema
        or application write, and no reader bookkeeping on the SHM (byte
        equality is provable precisely because SQLite is never opened).
        """
        self._populate_forward_store()
        store_path, wal_path, shm_path = self._capture_and_restore_wal_image(
            preserve_shm=True
        )
        health_fn = self._create_app()
        before_files = self._forward_tree_files()
        before_db_sha256 = self._sha256(store_path)
        before_wal_sha256 = self._sha256(wal_path)
        before_shm_sha256 = self._sha256(shm_path)
        # Invoke the real /health endpoint.
        report = self._invoke_health(health_fn)
        forward = report["forward_derivatives"]
        # Deterministic fail-closed degradation with the stable classification.
        self.assertIs(forward["store_exists"], True)
        self.assertEqual(forward["health"], "DEGRADED")
        self.assertEqual(forward["sample_count"], 0)
        self.assertIn("FORWARD_STORE_WAL_RECOVERY_REQUIRED", forward["error"])
        # Existing sidecars preserved byte-for-byte; no new files; rows intact.
        self.assertEqual(self._sha256(store_path), before_db_sha256)
        self.assertEqual(self._sha256(wal_path), before_wal_sha256)
        self.assertEqual(self._sha256(shm_path), before_shm_sha256)
        self.assertEqual(self._forward_tree_files(), before_files)
        self.assertEqual(
            self._sqlite_sidecars(store_path), sorted([wal_path.name, shm_path.name])
        )

    # -- A04-T10 (R05AR) --------------------------------------------------

    def test_a04_t10_health_never_invokes_writer_init_ddl_or_writer_constructor(
        self,
    ) -> None:
        """Negative guards: the health path never initializes, migrates, or writes.

        Supplemental to the storage proofs of T1-T4/T8/T9 (which stay primary):
        across the missing, checkpointed, and crash-leftover WAL states, the
        real /health path never invokes ``_initialize``/``prepare_schema``/
        ``finish_schema`` (the only DDL carriers of CREATE/ALTER TABLE) or a
        writer-mode ``ForwardDerivativeStore`` constructor. The spies fail the
        test if the health path ever touches them.
        """
        health_fn = self._create_app()
        failure = AssertionError(
            "health invoked writer initialization, schema DDL, or a "
            "writer-mode forward store constructor"
        )
        with (
            patch.object(ForwardDerivativeStore, "__init__", side_effect=failure),
            patch.object(ForwardDerivativeStore, "_initialize", side_effect=failure),
            patch(
                "btc_quant_agent.data.forward_store.prepare_schema",
                side_effect=failure,
            ),
            patch(
                "btc_quant_agent.data.forward_store.finish_schema",
                side_effect=failure,
            ),
        ):
            # 1. Missing store: degrade without creating/initializing anything.
            missing = self._invoke_health(health_fn)
            self._assert_missing_store_degradation(missing["forward_derivatives"])
            self.assertFalse((self._temp / FORWARD_STORE_RELATIVE).exists())
        # Build the checkpointed state through the writer workflow (spies
        # inactive: this construction is writer-owned).
        self._populate_forward_store()
        with (
            patch.object(ForwardDerivativeStore, "__init__", side_effect=failure),
            patch.object(ForwardDerivativeStore, "_initialize", side_effect=failure),
            patch(
                "btc_quant_agent.data.forward_store.prepare_schema",
                side_effect=failure,
            ),
            patch(
                "btc_quant_agent.data.forward_store.finish_schema",
                side_effect=failure,
            ),
        ):
            # 2. Checkpointed store: read through status(), never writer init.
            checkpointed = self._invoke_health(health_fn)
            self.assertEqual(checkpointed["forward_derivatives"]["sample_count"], 1)
            self.assertNotIn("error", checkpointed["forward_derivatives"])
        # Then reproduce the crash-leftover WAL state (writer-owned build).
        store_path, wal_path, _shm_path = self._capture_and_restore_wal_image(
            preserve_shm=False
        )
        with (
            patch.object(ForwardDerivativeStore, "__init__", side_effect=failure),
            patch.object(ForwardDerivativeStore, "_initialize", side_effect=failure),
            patch(
                "btc_quant_agent.data.forward_store.prepare_schema",
                side_effect=failure,
            ),
            patch(
                "btc_quant_agent.data.forward_store.finish_schema",
                side_effect=failure,
            ),
        ):
            # 3. Crash-leftover WAL: fail closed, never writer init.
            wal_state = self._invoke_health(health_fn)
            self.assertIn(
                "FORWARD_STORE_WAL_RECOVERY_REQUIRED",
                wal_state["forward_derivatives"]["error"],
            )
        # The spy-gated invocations created no -shm and left the WAL untouched.
        self.assertFalse((store_path.parent / (store_path.name + "-shm")).exists())
        self.assertTrue(wal_path.exists())


if __name__ == "__main__":
    unittest.main()
