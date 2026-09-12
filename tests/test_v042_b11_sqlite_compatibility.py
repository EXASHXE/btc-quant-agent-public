from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from test_forward_derivatives import _record
from test_v042_b10_writer_finalization import store, trade

from btc_quant_agent.data.forward_store import ForwardDerivativeStore, ForwardStoreConflict
from btc_quant_agent.microstructure_research import H39BlindLedger, MicrostructureResearchLoader
from btc_quant_agent.sqlite_schema import COLUMNS, SQLiteSchemaError, projection


def test_reordered_physical_columns_and_extra_column_safe_read_write(tmp_path):
    path = tmp_path / "forward.sqlite3"
    owner = ForwardDerivativeStore(path)
    owner.append(_record())
    with sqlite3.connect(path) as conn:
        columns = conn.execute("PRAGMA table_info(derivative_snapshots)").fetchall()
        conn.execute("ALTER TABLE derivative_snapshots RENAME TO old_snapshots")
        declarations = [f"{row[1]} {row[2]}" for row in reversed(columns)]
        conn.execute("CREATE TABLE derivative_snapshots (" + ",".join(declarations)
                     + ",future_unknown TEXT,PRIMARY KEY(symbol,observed_at_ms))")
        names = projection("derivative_snapshots")
        conn.execute(f"INSERT INTO derivative_snapshots ({names}) SELECT {names} FROM old_snapshots")
        conn.execute("DROP TABLE old_snapshots")
    reopened = ForwardDerivativeStore(path)
    assert reopened.append(_record(1_800_000, "run-2"))
    rows = reopened._rows()
    assert tuple(rows[0].keys()) == COLUMNS["derivative_snapshots"]
    assert rows[0]["mark_price"] == 100.5
    assert rows[1]["observed_at_ms"] == 1_800_000
    assert rows[1]["funding_rate"] == 0.0001


@pytest.mark.parametrize("marker,column", [(1, "mark_price"), (0, "mark_price"), (1, "evidence_epoch_id")])
def test_missing_core_or_partial_marker_migration_rejected(tmp_path, marker, column):
    path = tmp_path / "partial.sqlite3"
    ForwardDerivativeStore(path)
    table = "collection_runs" if column == "evidence_epoch_id" else "derivative_snapshots"
    with sqlite3.connect(path) as conn:
        conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
        conn.execute(f"PRAGMA user_version={marker}")
    with pytest.raises(SQLiteSchemaError, match="NOT_TESTABLE"):
        ForwardDerivativeStore(path)
    with sqlite3.connect(path) as conn:
        assert column not in {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def test_explicit_legacy_adapter_preserves_rows_and_neutral_defaults(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    owner = ForwardDerivativeStore(path)
    owner.append(_record())
    optional = ("trigger_source", "scheduled_slot_ms", "endpoint_telemetry_json", "evidence_epoch_id")
    with sqlite3.connect(path) as conn:
        for column in optional:
            conn.execute(f"ALTER TABLE collection_runs DROP COLUMN {column}")
        conn.execute("PRAGMA user_version=0")
    reopened = ForwardDerivativeStore(path)
    assert reopened.count() == 1
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
        row = conn.execute("SELECT trigger_source,scheduled_slot_ms,endpoint_telemetry_json,evidence_epoch_id FROM collection_runs").fetchone()
        assert row == ("LEGACY_UNKNOWN", None, "{}", None)


@pytest.mark.parametrize("marker", [-1, 2, 99])
def test_unsupported_schema_version_rejected_without_relabeling(tmp_path, marker):
    path = tmp_path / "unsupported.sqlite3"
    ForwardDerivativeStore(path)
    with sqlite3.connect(path) as conn:
        conn.execute(f"PRAGMA user_version={marker}")
    with pytest.raises(SQLiteSchemaError, match="unsupported"):
        ForwardDerivativeStore(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == marker


def test_blind_ledger_legacy_adapter_does_not_promote_outcomes(tmp_path):
    path = tmp_path / "blind.sqlite3"
    H39BlindLedger(path)
    with sqlite3.connect(path) as conn:
        conn.execute("ALTER TABLE h39_blind_validation_ledger DROP COLUMN input_contract_version")
        conn.execute("PRAGMA user_version=0")
    H39BlindLedger(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM h39_blind_validation_ledger").fetchone()[0] == 0


def test_cross_partition_projection_survives_reordered_source(tmp_path):
    paths = []
    for number in (1, 2):
        root = tmp_path / str(number)
        owner = store(root)
        owner.append_trade(trade(number))
        paths.append(root / "microstructure-1970-01-01.sqlite3")
    with sqlite3.connect(paths[1]) as conn:
        columns = conn.execute("PRAGMA table_info(agg_trades)").fetchall()
        conn.execute("ALTER TABLE agg_trades RENAME TO old_trades")
        conn.execute("CREATE TABLE agg_trades (" + ",".join(f"{row[1]} {row[2]}" for row in reversed(columns)) + ",unknown TEXT)")
        names = projection("agg_trades")
        conn.execute(f"INSERT INTO agg_trades ({names}) SELECT {names} FROM old_trades")
        conn.execute("DROP TABLE old_trades")
    loader = MicrostructureResearchLoader(paths[0], [paths[1]])
    with loader.connect_readonly() as conn:
        rows = conn.execute(f"SELECT {projection('agg_trades')} FROM agg_trades ORDER BY aggregate_trade_id").fetchall()
        assert [row["aggregate_trade_id"] for row in rows] == [1, 2]
        assert [row["price"] for row in rows] == [100.0, 100.0]
        assert rows[1]["aggressive_side"] == "BUY"


@pytest.mark.parametrize("table,column,marker", [("agg_trades", "price", 1), ("coverage_segments", "instance_id", 0), ("process_instances", "last_heartbeat_ms", 0)])
def test_cross_partition_mutator_rejects_missing_schema_before_write(tmp_path, table, column, marker):
    owner = store(tmp_path)
    owner.append_trade(trade())
    path = tmp_path / "microstructure-1970-01-01.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
        conn.execute(f"PRAGMA user_version={marker}")
    with pytest.raises(SQLiteSchemaError, match="NOT_TESTABLE"):
        owner.heartbeat(200, "synthetic")
    assert not owner.finalized_manifest_path.exists()


@pytest.mark.parametrize("attack", ["changed_rows", "missing_csv", "corrupt_manifest"])
def test_committed_export_not_overwritten_on_retry_drift(tmp_path, attack):
    owner = ForwardDerivativeStore(tmp_path / "forward.sqlite3")
    owner.append(_record())
    csv = tmp_path / "snapshot.csv"
    manifest = tmp_path / "manifest.json"
    first = owner.export(csv, manifest)
    prior_csv = csv.read_bytes()
    prior_manifest = manifest.read_bytes()
    assert owner.export(csv, manifest) == first
    assert manifest.read_bytes() == prior_manifest
    if attack == "changed_rows":
        owner.append(_record(1_800_000, "run-2"))
    elif attack == "missing_csv":
        csv.unlink()
    else:
        manifest.write_bytes(b'{"truncated":')
        prior_manifest = manifest.read_bytes()
    with pytest.raises(ForwardStoreConflict):
        owner.export(csv, manifest)
    assert manifest.read_bytes() == prior_manifest
    if attack != "missing_csv":
        assert csv.read_bytes() == prior_csv
    else:
        assert not csv.exists()


def test_export_owners_with_different_manifests_cannot_replace_same_csv(tmp_path):
    owners = [ForwardDerivativeStore(tmp_path / f"store-{number}.sqlite3") for number in (1, 2)]
    owners[0].append(_record())
    owners[1].append(_record(1_800_000, "run-2"))
    barrier = Barrier(2)

    def export(number):
        barrier.wait(timeout=2)
        try:
            owners[number].export(tmp_path / "shared.csv", tmp_path / f"manifest-{number}.json")
            return "committed"
        except ForwardStoreConflict:
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(export, [0, 1])) == ["committed", "stale"]
    assert len(list(tmp_path.glob("manifest-*.json"))) == 1


def test_export_rejects_same_target_for_csv_and_manifest(tmp_path):
    owner = ForwardDerivativeStore(tmp_path / "forward.sqlite3")
    with pytest.raises(ForwardStoreConflict, match="distinct"):
        owner.export(tmp_path / "ambiguous", tmp_path / "ambiguous")
    assert not (tmp_path / "ambiguous").exists()
