import pytest
from pydantic import ValidationError
from btc_quant_agent.platform.canary.control import BudgetGuard, CircuitOpen
from btc_quant_agent.platform.canary.fixtures import bbo
from btc_quant_agent.platform.canary.policy import SourceGrant, grant_reasons, weight
from btc_quant_agent.platform.canary.runtime import preflight
from btc_quant_agent.platform.canary.transport import (
    DisabledPublicTransport,
    NetworkDisabled,
    ScriptedTransport,
)
from btc_quant_agent.platform.core import fingerprint


def fabricated_grant(policy, catalog, output):
    selected = [catalog[i] for i in policy.endpoint_ids]
    return SourceGrant(
        grant_id="FABRICATED",
        authority="FABRICATED_TEST_GRANT",
        provider="binance",
        region=selected[0].region,
        market="USD_M",
        hosts=tuple(sorted({e.host for e in selected})),
        endpoint_ids=policy.endpoint_ids,
        fields={e.id: tuple(e.native_fields_units) for e in selected},
        symbols=policy.symbols,
        start_utc_ms=policy.synthetic_start_ms,
        end_utc_ms=policy.end_ms,
        ip_weight_per_minute=policy.ip_weight_per_minute,
        endpoint_calls_per_minute={
            e.id: policy.endpoint_calls_per_minute[e.id] for e in selected if e.transport == "REST"
        },
        controls_per_second=policy.controls_per_second,
        subscriptions=policy.max_subscriptions,
        connections=policy.max_connections,
        reconnects_per_hour=policy.max_reconnects_per_hour,
        bytes_total=policy.storage.total_disk_quota_bytes,
        raw_retention_hours=36,
        normalized_retention_hours=168,
        output_path=str(output),
        permitted_use_status="FABRICATED_TEST_ONLY",
        policy_hash=policy.hash,
        documentation_fingerprint=fingerprint(selected),
        approval_source_reference="FABRICATED_TEST_ASSERTION",
    )


@pytest.mark.parametrize(
    "limit,expected", [(1, 1), (99, 1), (100, 2), (499, 2), (500, 5), (1000, 5), (1500, 10)]
)
def test_kline_weights(limit, expected, catalog):
    assert weight(catalog["binance_usdm_klines_rest"], {"limit": limit}) == expected


@pytest.mark.parametrize(
    "id,single,all_",
    [("binance_usdm_bbo_rest", 2, 5), ("binance_usdm_premium", 1, 10), ("binance_usdm_turnover", 1, 40)],
)
def test_symbol_weight_formulas(id, single, all_, catalog):
    assert weight(catalog[id], {"symbol": "BTCUSDT"}) == single
    assert weight(catalog[id], {}) == all_


@pytest.mark.parametrize(
    "change",
    [
        dict(symbols=("BTCUSDT",)),
        dict(end_utc_ms=1),
        dict(fields={}),
        dict(hosts=()),
        dict(ip_weight_per_minute=1000),
        dict(raw_retention_hours=24),
        dict(output_path="/tmp/other"),
        dict(policy_hash="bad"),
        dict(documentation_fingerprint="bad"),
        dict(endpoint_calls_per_minute={}),
        dict(authority="OWNER_EXACT_SOURCE_GRANT"),
    ],
)
def test_exact_grant_mismatch(change, policy, catalog, tmp_path):
    grant = fabricated_grant(policy, catalog, tmp_path).model_copy(update=change)
    assert grant_reasons(grant, policy, catalog, policy.synthetic_start_ms, tmp_path, fabricated_test=True)


def test_complete_fabricated_grant_still_cannot_connect(policy, catalog, tmp_path):
    g = fabricated_grant(policy, catalog, tmp_path)
    assert not grant_reasons(g, policy, catalog, policy.synthetic_start_ms, tmp_path, fabricated_test=True)
    with pytest.raises(NetworkDisabled, match="PHASE_A_NETWORK_DISABLED"):
        DisabledPublicTransport(g).receive(
            catalog["binance_usdm_bbo_ws"], "BTCUSDT", policy.synthetic_start_ms
        )
    assert "GRANT_NOT_ACTIVE_OR_EXPIRED" in grant_reasons(
        g, policy, catalog, policy.end_ms, tmp_path, fabricated_test=True
    )


def test_preflight_grant_absent_terminates_without_creation(policy, catalog, tmp_path):
    output = tmp_path / "never-created"
    p = preflight(policy, catalog, output)
    assert p["status"] == "OFFLINE_READY_PENDING_AUTH" and p["grant_reasons"] == (
        "OWNER_SOURCE_GRANT_ABSENT",
    )
    assert not output.exists() and not p["background_task_created"]
    assert not p["budget"]["raw_quota_sufficient_for_estimate"]
    assert p["budget"]["projected_with_reserve"] <= policy.ip_weight_per_minute


@pytest.mark.parametrize(
    "change", [{"network_enabled": True}, {"mode": "LIVE"}, {"retry_weight_reserve_per_minute": 60}]
)
def test_policy_cannot_activate(change, policy):
    with pytest.raises(ValidationError):
        type(policy).model_validate({**policy.model_dump(), **change})


def test_scripted_end_closes_and_rejects_real(policy, catalog):
    e = catalog["binance_usdm_bbo_ws"]
    f = bbo(e, "BTCUSDT", policy.synthetic_start_ms + 1000)
    with pytest.raises(ValueError, match="FABRICATED"):
        ScriptedTransport((type(f)(**{**f.__dict__, "exposure": "FORWARD"}),), policy)
    s = ScriptedTransport((f,), policy)
    with pytest.raises(NetworkDisabled, match="END_REACHED"):
        s.receive(e, "BTCUSDT", policy.end_ms)
    assert s.closed and s.receive_calls == 0


@pytest.mark.parametrize("status,code", [(429, None), (418, None), (200, "50011"), (200, "50061")])
def test_throttles_open_persistent_circuit(status, code, policy, store):
    guard = BudgetGuard(store, policy)
    with pytest.raises(CircuitOpen, match="RATE_LIMIT"):
        guard.response(status, 1000, venue_code=code)
    with pytest.raises(CircuitOpen):
        BudgetGuard(type(store)(store.db_path), policy).precheck(1000000)


def test_atomic_rest_budget_prevents_excess_and_retry_storm(policy, store, catalog):
    guard = BudgetGuard(
        store, policy.model_copy(update={"ip_weight_per_minute": 4, "retry_weight_reserve_per_minute": 1})
    )
    e = catalog["binance_usdm_oi"]
    for i in range(3):
        guard.request(e, {"symbol": "BTCUSDT"}, 1000 + i)
    with pytest.raises(CircuitOpen, match="HARD_BUDGET"):
        guard.request(e, {}, 1004)
    with store._connect() as db:
        assert db.execute("SELECT SUM(amount) FROM canary_budget WHERE scope='IP:binance'").fetchone()[0] == 3


def test_backoff_is_bounded_and_restart_safe(policy, store):
    g = BudgetGuard(store, policy)
    assert g.response(408, 1000)["retry_not_before_mono"] == 2000
    with pytest.raises(CircuitOpen, match="BACKOFF"):
        g.precheck(1999)
    g.precheck(2000)
    for t in (3000, 10000):
        g.response(503, t)
    with pytest.raises(CircuitOpen, match="RETRY_EXHAUSTED"):
        g.response(503, 20000)


@pytest.mark.parametrize(
    "kind",
    [
        "control",
        "data",
        "pending",
        "connections",
        "subscriptions",
        "reconnect",
        "unknown_weight",
        "unknown_cap",
        "heartbeat",
    ],
)
def test_ws_pressure_unknown_and_liveness_fail_closed(kind, policy, catalog, store):
    g = BudgetGuard(store, policy)
    e = catalog["binance_usdm_bbo_ws"]
    with pytest.raises((CircuitOpen, ValueError)):
        if kind == "control":
            for i in range(3):
                g.websocket_control(e, 1000 + i)
        elif kind == "data":
            for i in range(201):
                g.data_message(1000, 0)
        elif kind == "pending":
            g.data_message(1000, 128)
        elif kind == "connections":
            for i in range(3):
                g.connection_open(str(i), e, 1000 + i * 2000)
        elif kind == "subscriptions":
            g.websocket_control(e, 1000, subscriptions=129)
        elif kind == "reconnect":
            for i in range(4):
                g.websocket_control(e, 1000 + i * 2000, reconnect=True)
        elif kind == "unknown_weight":
            g.request(e.model_copy(update={"transport": "REST", "weight_formula": "UNKNOWN"}), {}, 1000)
        elif kind == "unknown_cap":
            g.request(catalog["okx_swap_oi"], {}, 1000)
        elif kind == "heartbeat":
            g.connection_open("c", e, 1000)
            g.heartbeat("c", 602000, last_ping_mono=2000, last_pong_mono=1000, endpoint=e)


def test_connection_close_releases_subscriptions(policy, catalog, store):
    g = BudgetGuard(store, policy)
    e = catalog["binance_usdm_bbo_ws"]
    g.connection_open("c", e, 1000)
    g.subscription_set("c", e, ("btcusdt@bookTicker",), 1001)
    g.connection_close("c")
    assert not store.get_value("connections") and not store.get_value("subscriptions")


def test_local_endpoint_hard_cap_separate_from_ip(policy, catalog, store):
    g = BudgetGuard(store, policy.model_copy(update={"endpoint_calls_per_minute": {"binance_usdm_oi": 1}}))
    e = catalog["binance_usdm_oi"]
    g.request(e, {}, 1000)
    with pytest.raises(CircuitOpen, match="LOCAL_ENDPOINT"):
        g.request(e, {}, 1001)


def test_registry_rejects_private_or_wrong_market_alias(catalog):
    e = catalog["binance_usdm_exchange_info"]
    for change in (
        {"endpoint": "/fapi/v1/order"},
        {"host": "https://dapi.binance.com"},
        {"endpoint": "/api/v3/exchangeInfo"},
    ):
        with pytest.raises(ValidationError):
            type(e).model_validate({**e.model_dump(), **change})
