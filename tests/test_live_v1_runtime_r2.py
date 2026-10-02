from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from test_live_v1_decision_models import sample_case

from btc_quant_agent import api
from btc_quant_agent.approval.store import LiveStore
from btc_quant_agent.config import AppConfig, LiveV1Config, StorageConfig
from btc_quant_agent.decision.risk import RiskCompilerV1, RiskPolicyV1
from btc_quant_agent.decision.service import TacticalLiveService
from btc_quant_agent.execution.guard import ExecutionBlocked
from btc_quant_agent.live_runtime import LiveV1Runtime


def _runtime(*, mode: str = "DRY_RUN", pending: tuple[str, ...] = ()) -> LiveV1Runtime:
    async def wait_forever(*_args):
        await asyncio.Future()

    market = SimpleNamespace(run_stream=wait_forever, stop=Mock(), is_connected=True,
                             latest_observation=Mock(return_value=None))
    account = SimpleNamespace(
        environment=mode, is_stream_connected=mode == "TESTNET",
        reconcile_rest=Mock(), reconcile_rest_async=AsyncMock(), mark_stream_disconnected=Mock(),
        run_user_stream=wait_forever, close_user_stream=AsyncMock(), stop=Mock(),
        latest_snapshot=Mock(return_value=SimpleNamespace(
            reconciled=True, quality="OK", positions=(), orders=(), snapshot_hash="account")),
    )
    execution = SimpleNamespace(reconcile_intent=AsyncMock(), execute_approved_intent=AsyncMock())
    supervisor = SimpleNamespace(drain_pending_dispatches=AsyncMock())
    kill = SimpleNamespace(allows_new_risk=Mock(return_value=True))
    runtime = LiveV1Runtime(
        config=LiveV1Config(runtime_enabled=True, execution_mode=mode,
                            testnet_execution_enabled=mode == "TESTNET"),
        tactical_service=SimpleNamespace(), market_stream=market, account_watch=account,
        intent_store=SimpleNamespace(unfinished_intent_ids=Mock(return_value=pending)),
        execution_service=execution, supervisor=supervisor, kill_switch=kill,
    )
    return runtime


def _run(coro):
    asyncio.run(coro)


def test_runtime_recovers_before_accepting_risk_and_owns_tasks(monkeypatch):
    async def inline_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr("btc_quant_agent.live_runtime.asyncio.to_thread", inline_thread)
    async def run():
        runtime = _runtime(pending=("pending-1",))
        await runtime.start()
        assert runtime.accepting_risk
        runtime.execution_service.reconcile_intent.assert_awaited_once_with("pending-1")
        runtime.supervisor.drain_pending_dispatches.assert_awaited()
        assert len(runtime.tasks) == 4  # market, REST, outbox, position
        await asyncio.wait_for(runtime.stop(), 2)
        assert not runtime.accepting_risk
        assert all(task.done() for task in runtime.tasks)
        runtime.account_watch.mark_stream_disconnected.assert_called()
    _run(run())


def test_testnet_adds_owned_user_stream_and_blocks_until_connected(monkeypatch):
    async def inline_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr("btc_quant_agent.live_runtime.asyncio.to_thread", inline_thread)
    async def run():
        runtime = _runtime(mode="TESTNET")
        runtime.account_watch.is_stream_connected = False
        await runtime.start()
        assert len(runtime.tasks) == 5
        with pytest.raises(ExecutionBlocked):
            await runtime.execute_intent("intent-1")
        runtime.execution_service.execute_approved_intent.assert_not_awaited()
        await asyncio.wait_for(runtime.stop(), 2)
        runtime.account_watch.close_user_stream.assert_awaited()
    _run(run())


def test_live_and_missing_testnet_opt_in_are_rejected():
    with pytest.raises(ValueError):
        LiveV1Config(runtime_enabled=True, execution_mode="LIVE")
    with pytest.raises(ValueError):
        LiveV1Config(runtime_enabled=True, execution_mode="TESTNET")
    assert LiveV1Config(execution_mode="PAPER").execution_mode == "DRY_RUN"
    assert LiveV1Config(execution_mode="SHADOW").execution_mode == "DRY_RUN"
    with pytest.raises(ValueError):
        LiveV1Config(execution_mode="AUTONOMOUS")


def test_testnet_factory_requires_testnet_credentials(tmp_path, monkeypatch):
    monkeypatch.delenv("BINANCE_TESTNET_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_TESTNET_API_SECRET", raising=False)
    service = TacticalLiveService(LiveStore(tmp_path / "live.db"), None,
                                  RiskCompilerV1(RiskPolicyV1()))
    config = LiveV1Config(runtime_enabled=True, execution_mode="TESTNET",
                          testnet_execution_enabled=True, sqlite_path=str(tmp_path / "live.db"))
    with pytest.raises(Exception, match="BINANCE_TESTNET"):
        LiveV1Runtime.create(config, service)


def test_reconciliation_failure_blocks_startup_and_cleans_up(monkeypatch):
    async def inline_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr("btc_quant_agent.live_runtime.asyncio.to_thread", inline_thread)
    runtime = _runtime()
    runtime.account_watch.reconcile_rest_async.side_effect = RuntimeError("local REST unavailable")

    async def run():
        with pytest.raises(RuntimeError, match="local REST unavailable"):
            await runtime.start()
        assert not runtime.accepting_risk
        assert not runtime.tasks
        runtime.account_watch.mark_stream_disconnected.assert_called()

    _run(run())


def test_position_poll_uses_account_quantity_and_previous_quantity():
    runtime = _runtime(pending=("intent-1",))
    position = SimpleNamespace(symbol="BTCUSDT", quantity=0.25, entry_price=100.0,
                               unrealized_pnl_usdt=1.0, leverage=2)
    snapshot = SimpleNamespace(snapshot_hash="account-hash", reconciled=True, quality="OK",
                               positions=(position,), orders=())
    runtime.account_watch.latest_snapshot.return_value = snapshot
    runtime.market_stream.latest_observation = Mock(return_value=SimpleNamespace(
        symbol="BTCUSDT", observation_hash="market-hash", mark_price=101.0, spread_bps=1.0))
    runtime.intent_store.get_intent = Mock(return_value=SimpleNamespace(
        intent_id="intent-1", symbol="BTCUSDT", stop_loss=95.0,
        take_profit_1=110.0, client_order_id="client-1",
        environment="DRY_RUN", account_authority="DEFAULT_ACCOUNT"))
    runtime.supervisor.process = AsyncMock(return_value=())

    async def run():
        await runtime.poll_positions(1_700_000_000_000)
        first = runtime.supervisor.process.await_args.args[0]
        assert first.quantity == 0.25
        assert first.previous_quantity == 0
        position.quantity = 0.1
        await runtime.poll_positions(1_700_000_005_000)
        second = runtime.supervisor.process.await_args.args[0]
        assert second.quantity == 0.1
        assert second.previous_quantity == 0.25
        assert runtime.execution_service.reconcile_intent.await_count == 2

    _run(run())


def test_foreign_account_position_never_uses_btc_market_observation():
    runtime = _runtime()
    foreign = SimpleNamespace(symbol="ETHUSDT", quantity=1.0, entry_price=50.0,
                              unrealized_pnl_usdt=0.0, leverage=1)
    runtime.account_watch.latest_snapshot.return_value = SimpleNamespace(
        snapshot_hash="account", reconciled=True, quality="OK", positions=(foreign,), orders=())
    runtime.market_stream.latest_observation.return_value = SimpleNamespace(
        symbol="BTCUSDT", observation_hash="btc-market", mark_price=100.0, spread_bps=1.0)
    runtime.supervisor.process = AsyncMock()

    async def run():
        await runtime.poll_positions(1_700_000_000_000)
        runtime.supervisor.process.assert_not_awaited()
        assert runtime.blocked_reason == "UNCONFIGURED_POSITION_SYMBOL"

    _run(run())


def test_cached_tactical_case_is_verified_and_bad_entry_is_blocked(tmp_path, monkeypatch):
    async def inline_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr("btc_quant_agent.live_runtime.asyncio.to_thread", inline_thread)
    monkeypatch.setattr("btc_quant_agent.decision.case.case_from_assessment",
                        lambda assessment, *, ttl_ms: assessment)
    now = 1_700_000_000_000
    monkeypatch.setattr("btc_quant_agent.live_runtime.time.time", lambda: now / 1000)
    case = sample_case(created_at_ms=now, observed_at_ms=now, expires_at_ms=now + 60_000,
                       entry_quality="GOOD")
    watch = SimpleNamespace(scan=Mock(return_value=[case]))
    service = TacticalLiveService(LiveStore(tmp_path / "live.db"), None,
                                  RiskCompilerV1(RiskPolicyV1()), market_watch=watch)
    runtime = LiveV1Runtime.create(LiveV1Config(runtime_enabled=True,
                                  sqlite_path=str(tmp_path / "live.db")), service)

    async def run():
        await runtime._refresh_case("BTCUSDT")
        assert runtime.execution_service.validator.tactical_case_provider("BTCUSDT", now) == case
        assert runtime.execution_service.validator.tactical_validity_provider("BTCUSDT", now)
        bad = sample_case(created_at_ms=now, observed_at_ms=now, expires_at_ms=now + 60_000,
                          entry_quality="POOR")
        runtime._case_cache["BTCUSDT"] = bad
        with pytest.raises(ValueError, match="FRESH_MARKET_CASE_UNAVAILABLE"):
            runtime.execution_service.validator.tactical_case_provider("BTCUSDT", now)

    _run(run())


def test_shutdown_waits_for_inflight_position_reconciliation():
    runtime = _runtime()
    runtime.market_stream.latest_observation.return_value = None
    entered = asyncio.Event()
    release = asyncio.Event()

    async def reconcile(_intent_id):
        entered.set()
        await release.wait()

    runtime.execution_service.reconcile_intent.side_effect = reconcile

    async def run():
        await runtime.start()
        runtime.intent_store.unfinished_intent_ids.return_value = ("pending-1",)
        await entered.wait()
        stopping = asyncio.create_task(runtime.stop())
        await asyncio.sleep(0)
        assert not stopping.done()
        release.set()
        await stopping
        assert all(task.done() for task in runtime.tasks)

    _run(run())


def test_api_lifespan_starts_and_stops_only_injected_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "load_config", lambda: AppConfig(
        storage=StorageConfig(sqlite_path=str(tmp_path / "api.db"))))
    service = TacticalLiveService(LiveStore(tmp_path / "live.db"), None,
                                  RiskCompilerV1(RiskPolicyV1()))
    runtime = SimpleNamespace(tactical_service=service, start=AsyncMock(), stop=AsyncMock(),
                              status=Mock(return_value={"enabled": True}),
                              execute_intent=AsyncMock(return_value={"status": "FILLED"}))
    app = api.create_app(live_runtime=runtime)

    def _all_routes(application):
        routes = []
        for route in application.routes:
            path = getattr(route, "path", None)
            methods = getattr(route, "methods", None)
            if path and methods:
                for method in methods:
                    routes.append((path, method))
            if hasattr(route, "original_router"):
                for sub in route.original_router.routes:
                    sub_path = getattr(sub, "path", None)
                    sub_methods = getattr(sub, "methods", None)
                    if sub_path and sub_methods:
                        for method in sub_methods:
                            routes.append((sub_path, method))
        return routes

    # 1. Verify all routes on app (including any nested routers) are strictly read-only GET/HEAD/OPTIONS
    registered_routes = _all_routes(app)
    for path, method in registered_routes:
        if path in {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}:
            continue
        assert method in {"GET", "HEAD", "OPTIONS"}, f"Non-read-only method {method} on {path}"

    # 2. No runtime execution route exists anywhere in app
    assert not any(getattr(route, "path", "").startswith("/live-v1/runtime/") for route in app.routes)
    assert not any(p in {"/live-v1/scan", "/live-v1/reviews"} for p, _ in registered_routes)

    # 3. Lifespan correctly starts and stops injected runtime
    async def run():
        async with app.router.lifespan_context(app):
            runtime.start.assert_awaited_once()
        runtime.stop.assert_awaited_once()

    _run(run())

    # 4. Default create_app() has no runtime routes
    default = api.create_app()
    assert not any(getattr(route, "path", "").startswith("/live-v1/runtime/") for route in default.routes)

    # 5. /execution/status returns live_v1_runtime status when runtime is injected
    exec_status_route = next(route for route in app.routes if getattr(route, "path", "") == "/execution/status")
    status = exec_status_route.endpoint()
    assert status.get("live_v1_runtime") == {"enabled": True}

    # 6. LiveV1Runtime.execute_intent(intent_id) remains callable directly in Python
    async def run_direct():
        res = await runtime.execute_intent("intent-1")
        assert res == {"status": "FILLED"}
        runtime.execute_intent.assert_awaited_once_with("intent-1")

    _run(run_direct())


def test_b4_runtime_host_api_governance_matrix(tmp_path, monkeypatch):
    import httpx

    monkeypatch.setenv("FEISHU_VERIFICATION_TOKEN", "test-token")
    monkeypatch.setenv("FEISHU_APPROVER_OPEN_IDS", "approver-1")
    monkeypatch.setattr(api, "load_config", lambda: AppConfig(
        storage=StorageConfig(sqlite_path=str(tmp_path / "api.db"))))
    service = TacticalLiveService(LiveStore(tmp_path / "live.db"), None,
                                  RiskCompilerV1(RiskPolicyV1()))
    runtime = SimpleNamespace(tactical_service=service, start=AsyncMock(), stop=AsyncMock(),
                              status=Mock(return_value={"enabled": True, "mode": "B4_RUNTIME"}),
                              execute_intent=AsyncMock(return_value={"status": "FILLED"}))

    def _all_routes(application):
        routes = []
        for r in application.routes:
            p = getattr(r, "path", None)
            m = getattr(r, "methods", None)
            if p and m:
                for method in m:
                    routes.append((p, method))
            if hasattr(r, "original_router"):
                for sub in r.original_router.routes:
                    sp = getattr(sub, "path", None)
                    sm = getattr(sub, "methods", None)
                    if sp and sm:
                        for method in sm:
                            routes.append((sp, method))
        return routes

    # R2.1.1-A01 & A02: Injected runtime mode -> host routes are strictly read-only; no scan/reviews/execute
    app_injected = api.create_app(live_runtime=runtime)
    routes_injected = _all_routes(app_injected)
    for path, method in routes_injected:
        if path in {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}:
            continue
        assert method in {"GET", "HEAD", "OPTIONS"}, f"Non-read-only method {method} on {path}"
    assert not any(p in {"/live-v1/scan", "/live-v1/reviews"} for p, _ in routes_injected)
    assert not any(p.startswith("/live-v1/runtime/") for p, _ in routes_injected)

    # R2.1.1-A03: BTC_QUANT_LIVE_V1_RUNTIME_ENABLED=true -> same read-only host invariant
    monkeypatch.setenv("BTC_QUANT_LIVE_V1_RUNTIME_ENABLED", "true")
    monkeypatch.delenv("BTC_QUANT_LIVE_V1_ENABLED", raising=False)
    app_env = api.create_app()
    routes_env = _all_routes(app_env)
    for path, method in routes_env:
        if path in {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}:
            continue
        assert method in {"GET", "HEAD", "OPTIONS"}, f"Non-read-only method {method} on {path}"
    assert not any(p in {"/live-v1/scan", "/live-v1/reviews"} for p, _ in routes_env)
    assert not any(p.startswith("/live-v1/runtime/") for p, _ in routes_env)

    # R2.1.1-A04: Both legacy B3 enabled + runtime enabled -> runtime mode takes precedence and remains host-read-only
    monkeypatch.setenv("BTC_QUANT_LIVE_V1_ENABLED", "true")
    monkeypatch.setenv("BTC_QUANT_LIVE_V1_RUNTIME_ENABLED", "true")
    app_both = api.create_app()
    routes_both = _all_routes(app_both)
    for path, method in routes_both:
        if path in {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}:
            continue
        assert method in {"GET", "HEAD", "OPTIONS"}, f"Non-read-only method {method} on {path}"
    assert not any(p in {"/live-v1/scan", "/live-v1/reviews"} for p, _ in routes_both)
    assert not any(p.startswith("/live-v1/runtime/") for p, _ in routes_both)

    # R2.1.1-A05: Legacy B3 control-plane mode without B4 runtime -> existing B3 router behavior preserved
    monkeypatch.delenv("BTC_QUANT_LIVE_V1_RUNTIME_ENABLED", raising=False)
    monkeypatch.setenv("BTC_QUANT_LIVE_V1_ENABLED", "true")
    app_b3 = api.create_app(live_service=service)
    routes_b3 = _all_routes(app_b3)
    assert any(p == "/live-v1/scan" and m == "POST" for p, m in routes_b3)
    assert any(p == "/live-v1/reviews" and m == "POST" for p, m in routes_b3)
    assert any(p == "/live-v1/cases/{case_id}" and m == "GET" for p, m in routes_b3)

    # R2.1.1-A06: Lifespan in runtime mode starts and stops LiveV1Runtime
    async def run_lifespan():
        async with app_injected.router.lifespan_context(app_injected):
            runtime.start.assert_awaited_once()
        runtime.stop.assert_awaited_once()

    _run(run_lifespan())

    # R2.1.1-A07: /execution/status remains GET/read-only and surfaces runtime status
    exec_status_route = next(r for r in app_injected.routes if getattr(r, "path", "") == "/execution/status")
    status_payload = exec_status_route.endpoint()
    assert status_payload.get("live_v1_runtime") == {"enabled": True, "mode": "B4_RUNTIME"}

    # R2.1.1-A08: Direct Python call LiveV1Runtime.execute_intent(intent_id) remains functional
    async def run_direct():
        res = await runtime.execute_intent("intent-governance-1")
        assert res == {"status": "FILLED"}
        runtime.execute_intent.assert_awaited_once_with("intent-governance-1")

    _run(run_direct())

    # R2.1.1-A09: Feishu callback cannot carry executable order fields and cannot directly call execution backend
    async def test_feishu_callback_execution_isolation():
        monkeypatch.setenv("FEISHU_VERIFICATION_TOKEN", "test-token")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app_injected),
                                     base_url="http://test") as client:
            malicious_payload = {
                "schema": "2.0",
                "header": {"event_type": "card.action.trigger", "event_id": "evt-1", "token": "test-token"},
                "event": {
                    "operator": {"open_id": "approver-1"},
                    "action": {
                        "value": {
                            "action": "APPROVE",
                            "proposal_hash": "h1",
                            "case_hash": "c1",
                            "quantity": "1.5",
                            "leverage": 10,
                        }
                    }
                }
            }
            resp = await client.post("/live-v1/feishu/callback", json=malicious_payload)
            assert resp.status_code == 400

    _run(test_feishu_callback_execution_isolation())
