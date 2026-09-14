"""Orchestration guards: R02 runtime convergence and entry-surface invariants."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest
from helpers import signal as make_signal

from btc_quant_agent import api, cli
from btc_quant_agent.config import AppConfig, StorageConfig
from btc_quant_agent.domain import SignalStatus
from btc_quant_agent.storage import Repository

ROOT = Path(__file__).resolve().parents[1]


def _catalog():
    spec = importlib.util.spec_from_file_location(
        "r02_catalog", ROOT / "tools/catalog_surfaces.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# 1. Formal research routing invariants
@pytest.mark.parametrize("command", ["backtest", "research", "replay"])
def test_formal_commands_route_only_through_formal_facade(command, tmp_path, monkeypatch, capsys):
    forbidden = Mock(side_effect=AssertionError("runtime service constructed"))
    monkeypatch.setattr(cli, "_service", forbidden)
    monkeypatch.setattr("btc_quant_agent.service.QuantService.create", forbidden)

    output = tmp_path / "output"
    exit_code = cli.main(
        [command, "--job", str(tmp_path / "missing_job.json"), "--output", str(output)]
    )
    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["classification"] == "NOT_TESTABLE_FOR_NEW_PROMOTION"
    assert not output.exists()
    forbidden.assert_not_called()


@pytest.mark.parametrize("command", ["backtest", "research", "replay"])
def test_formal_dispatch_occurs_before_runtime_service_construction(
    command, tmp_path, monkeypatch
):
    forbidden = Mock(side_effect=AssertionError("service constructed during formal dispatch"))
    monkeypatch.setattr(cli, "_service", forbidden)
    with pytest.raises(SystemExit):
        cli.main([command])  # missing required --job and --output
    forbidden.assert_not_called()


# 2. Removed CLI surfaces fail at parser/dispatch level
@pytest.mark.parametrize(
    "args",
    [
        ["microstructure-research", "validation-status"],
        ["microstructure-research", "validation-accumulate"],
        ["microstructure-research", "scheduled-accumulate"],
        ["microstructure-research", "verify-integrity"],
        ["microstructure-research", "backup-ledger"],
        ["microstructure-research", "validation-readiness"],
        ["microstructure-research", "freeze-cutoff"],
        ["microstructure-research", "one-shot-unblind"],
        ["microstructure-research", "generate-deliverables"],
        ["collect-derivatives"],
        ["derivatives", "diagnose-network"],
    ],
)
def test_removed_cli_commands_fail_at_parser_level(args, monkeypatch):
    forbidden = Mock(side_effect=AssertionError("unexpected service invocation"))
    monkeypatch.setattr(cli, "_service", forbidden)
    with pytest.raises(SystemExit) as exc:
        cli.main(args)
    assert exc.value.code == 2
    forbidden.assert_not_called()


def test_catalog_confirms_removed_surfaces_are_absent():
    catalog = _catalog()
    entrypoints = catalog.get_cli_entrypoints()
    assert not any("microstructure-research" in ep for ep in entrypoints)
    assert not any("collect-derivatives" in ep for ep in entrypoints)
    assert not any("diagnose-network" in ep for ep in entrypoints)
    assert {"backtest", "research", "replay", "h39 validation-status"} <= set(entrypoints)
    assert len(entrypoints) == 51

    api_routes = catalog.get_api_routes()
    assert len(api_routes) == 6
    for r in api_routes:
        assert r["method"] == "GET"


# 3. Lazy service construction: offline commands never construct QuantService
def test_lazy_service_construction_for_offline_commands(monkeypatch):
    forbidden = Mock(side_effect=AssertionError("QuantService constructed by offline command"))
    monkeypatch.setattr(cli, "_service", forbidden)

    # parser construction and help must not construct service
    parser = cli.build_parser()
    assert parser is not None
    forbidden.assert_not_called()


# 4. API convergence: mutating routes are absent and retained routes are strictly read-only
def test_removed_api_mutating_routes_are_not_registered(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        config = AppConfig(storage=StorageConfig(sqlite_path=str(Path(d) / "test.db")))
        monkeypatch.setattr(api, "load_config", lambda: config)
        monkeypatch.setenv("BTC_QUANT_API_TOKEN", "test-token")
        app = api.create_app()

        registered_routes = [
            (route.path, method)
            for route in app.routes  # type: ignore[attr-defined]
            for method in getattr(route, "methods", set())
            if getattr(route, "path", None)
        ]

        # Only GET methods allowed on API endpoints
        for path, method in registered_routes:
            if path in {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}:
                continue
            assert method in {"GET", "HEAD", "OPTIONS"}, f"Non-read-only method {method} on {path}"

        # Mutating endpoints must be absent
        removed_paths = [
            "/scan",
            "/signals/{signal_id}/decision",
            "/execution/plans/entry/{signal_id}",
            "/execution/plans/{plan_id}/submit",
            "/execution/plans/{plan_id}/reconcile",
            "/execution/close/preview",
            "/execution/close/{plan_id}/submit",
            "/execution/plans/{plan_id}/cancel",
        ]
        registered_paths = {r[0] for r in registered_routes}
        for path in removed_paths:
            assert path not in registered_paths, f"Mutating route {path} still registered"


def test_retained_api_routes_are_non_mutating(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        db_path = str(Path(d) / "test.db")
        config = AppConfig(storage=StorageConfig(sqlite_path=db_path))
        monkeypatch.setattr(api, "load_config", lambda: config)
        monkeypatch.setenv("BTC_QUANT_API_TOKEN", "test-token")
        monkeypatch.setattr(
            "btc_quant_agent.service.QuantService.health",
            lambda self: {"status": "OK", "validation_status": "HERMETIC_TEST"},
        )
        monkeypatch.setattr(
            "btc_quant_agent.storage.Repository.performance",
            lambda self, since_ms=0: {"trades": 0, "since_ms": since_ms},
        )

        app = api.create_app()

        def _get_endpoint(path: str):
            return next(
                route.endpoint
                for route in app.routes  # type: ignore[attr-defined]
                if getattr(route, "path", None) == path and "GET" in getattr(route, "methods", set())
            )

        # GET /health is read-only
        health_fn = _get_endpoint("/health")
        res = health_fn()
        assert res["status"] == "OK"

        # GET /performance is read-only
        perf_fn = _get_endpoint("/performance")
        res = perf_fn(days=7)
        assert res["trades"] == 0

        # GET /execution/status is read-only
        exec_fn = _get_endpoint("/execution/status")
        res = exec_fn()
        assert res["mode"] == "disabled"


# 5. Execution safety defaults and confirmation
def test_execution_safety_defaults_remain_enforced():
    config = AppConfig()
    assert config.execution.mode == "disabled"
    assert not config.execution.auto_execute
    assert not config.execution.allow_live

    # CLI execution commands require --confirm
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["execution", "submit", "plan-1"])  # missing --confirm
    with pytest.raises(SystemExit):
        parser.parse_args(["execution", "submit-close", "plan-1"])  # missing --confirm
    with pytest.raises(SystemExit):
        parser.parse_args(["execution", "cancel", "plan-1"])  # missing --confirm


# 6. R02R: Read-only Signal API behavioral and storage-level immutability guards


def _make_test_signal(signal_id: str, status: SignalStatus = SignalStatus.ACTIVE, expires_at_ms: int = 0):
    sig = make_signal()
    sig.signal_id = signal_id
    sig.fingerprint = f"fp-{signal_id}"
    sig.status = status
    sig.expires_at_ms = expires_at_ms
    return sig


def _get_db_snapshot(db_path: str) -> dict[str, list[dict]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    snapshot = {}
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]
    for table in sorted(tables):
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        snapshot[table] = [dict(r) for r in rows]
    conn.close()
    return snapshot


def _setup_test_app_r02r(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_api_r02r.db")
    config = AppConfig(storage=StorageConfig(sqlite_path=db_path))
    monkeypatch.setattr(api, "load_config", lambda: config)
    monkeypatch.setenv("BTC_QUANT_API_TOKEN", "test-token")
    monkeypatch.setattr(
        "btc_quant_agent.service.QuantService.health",
        lambda self: {"status": "OK", "validation_status": "HERMETIC_TEST"},
    )
    repo = Repository(db_path)
    app = api.create_app()

    def _get_endpoint(path: str):
        return next(
            route.endpoint
            for route in app.routes
            if getattr(route, "path", None) == path and "GET" in getattr(route, "methods", set())
        )

    return app, repo, db_path, _get_endpoint


def test_r02r_t1_latest_signal_is_storage_read_only(tmp_path, monkeypatch):
    _app, repo, db_path, get_endpoint = _setup_test_app_r02r(tmp_path, monkeypatch)
    past_ms = int(time.time() * 1000) - 30_000
    sig = _make_test_signal("sig-expired-1", status=SignalStatus.ACTIVE, expires_at_ms=past_ms)
    assert repo.save_signal(sig, 90)

    snapshot_before = _get_db_snapshot(db_path)

    expire_spy = MagicMock(wraps=repo.expire_signals)
    monkeypatch.setattr(repo, "expire_signals", expire_spy)

    fn = get_endpoint("/signals/latest")
    res = fn()

    assert res["signal_id"] == "sig-expired-1"
    assert res["status"] == SignalStatus.ACTIVE.value

    snapshot_after = _get_db_snapshot(db_path)
    assert snapshot_before == snapshot_after, "Database mutated during GET /signals/latest"

    persisted = repo.get_signal("sig-expired-1")
    assert persisted is not None
    assert persisted.status == SignalStatus.ACTIVE
    assert persisted.expires_at_ms == past_ms
    assert expire_spy.call_count == 0


def test_r02r_t2_specific_signal_is_storage_read_only(tmp_path, monkeypatch):
    _app, repo, db_path, get_endpoint = _setup_test_app_r02r(tmp_path, monkeypatch)
    past_ms = int(time.time() * 1000) - 60_000
    sig = _make_test_signal("sig-expired-2", status=SignalStatus.ACTIVE, expires_at_ms=past_ms)
    assert repo.save_signal(sig, 90)

    snapshot_before = _get_db_snapshot(db_path)

    expire_spy = MagicMock(wraps=repo.expire_signals)
    monkeypatch.setattr(repo, "expire_signals", expire_spy)

    fn = get_endpoint("/signals/{signal_id}")
    res = fn("sig-expired-2")

    assert res["signal_id"] == "sig-expired-2"
    assert res["status"] == SignalStatus.ACTIVE.value

    snapshot_after = _get_db_snapshot(db_path)
    assert snapshot_before == snapshot_after, "Database mutated during GET /signals/{signal_id}"

    persisted = repo.get_signal("sig-expired-2")
    assert persisted is not None
    assert persisted.status == SignalStatus.ACTIVE
    assert expire_spy.call_count == 0


def test_r02r_t3_all_retained_routes_have_no_repository_mutation(tmp_path, monkeypatch):
    _app, repo, db_path, get_endpoint = _setup_test_app_r02r(tmp_path, monkeypatch)
    past_ms = int(time.time() * 1000) - 120_000
    sig = _make_test_signal("sig-t3", status=SignalStatus.ACTIVE, expires_at_ms=past_ms)
    repo.save_signal(sig, 90)

    class StrictReadOnlyConnection:
        def __init__(self, conn):
            self._conn = conn
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            self._conn.close()
        def execute(self, sql, *args, **kwargs):
            norm = sql.strip().upper()
            forbidden = ("INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER ", "CREATE ", "REPLACE ")
            for kw in forbidden:
                assert not norm.startswith(kw), f"Forbidden mutating SQL executed: {sql}"
            return self._conn.execute(sql, *args, **kwargs)

    def safe_connect():
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        return StrictReadOnlyConnection(c)

    monkeypatch.setattr(repo, "_connect", safe_connect)

    snapshot_before = _get_db_snapshot(db_path)

    # 1. /health
    health_res = get_endpoint("/health")()
    assert health_res["status"] == "OK"

    # 2. /signals/latest
    latest_res = get_endpoint("/signals/latest")()
    assert latest_res["signal_id"] == "sig-t3"

    # 3. /signals/{signal_id}
    show_res = get_endpoint("/signals/{signal_id}")("sig-t3")
    assert show_res["signal_id"] == "sig-t3"

    # 4. /signals/{signal_id}/explanation
    expl_res = get_endpoint("/signals/{signal_id}/explanation")("sig-t3")
    assert expl_res["signal_id"] == "sig-t3"

    # 5. /performance
    perf_res = get_endpoint("/performance")(days=7)
    assert "trades" in perf_res

    # 6. /execution/status
    exec_res = get_endpoint("/execution/status")()
    assert exec_res["mode"] == "disabled"

    snapshot_after = _get_db_snapshot(db_path)
    assert snapshot_before == snapshot_after, "State changed across all 6 GET routes"


def test_r02r_t4_explicit_operational_workflows_still_own_expiry(tmp_path, monkeypatch, capsys):
    db_path = str(tmp_path / "op_expiry.db")
    repo = Repository(db_path)
    past_ms = int(time.time() * 1000) - 10_000
    sig = _make_test_signal("sig-op-1", status=SignalStatus.ACTIVE, expires_at_ms=past_ms)
    repo.save_signal(sig, 90)

    # 1. Direct repository call mutates expired signal
    now_ms = int(time.time() * 1000)
    expired_count = repo.expire_signals(now_ms)
    assert expired_count == 1

    persisted_after = repo.get_signal("sig-op-1")
    assert persisted_after is not None
    assert persisted_after.status == SignalStatus.EXPIRED

    # 2. Operational CLI signal workflow explicitly triggers expiry
    sig2 = _make_test_signal("sig-op-2", status=SignalStatus.ACTIVE, expires_at_ms=past_ms)
    repo.save_signal(sig2, 90)
    config = AppConfig(storage=StorageConfig(sqlite_path=db_path))
    monkeypatch.setattr(cli, "load_config", lambda *args, **kwargs: config)
    ret = cli.main(["signal", "latest"])
    assert ret == 0

    persisted_sig2 = repo.get_signal("sig-op-2")
    assert persisted_sig2 is not None
    assert persisted_sig2.status == SignalStatus.EXPIRED
