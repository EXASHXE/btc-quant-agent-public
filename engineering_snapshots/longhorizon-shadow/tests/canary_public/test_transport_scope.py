import json
import subprocess
import os
import sys
import pytest

from btc_quant_agent.platform.canary.control import CanaryStore, BudgetGuard
from btc_quant_agent.platform.canary.public_policy import (
    START,
    END,
    OUTPUT,
    PublicStop,
    load_scope,
    preflight,
)
from btc_quant_agent.platform.canary.public_io import PublicTransport
from btc_quant_agent.platform.canary.public_policy import Window
from .fixtures import Clock, Backend


def transport(scope, tmp_path, clock=None, backend=None, enabled=True):
    clock = clock or Clock()
    backend = backend or Backend(scope, clock)
    return PublicTransport(
        scope,
        clock,
        BudgetGuard(CanaryStore(tmp_path / "state.sqlite"), scope.budget_policy()),
        enabled=enabled,
        backend=backend,
    )


def test_owner_attestation_is_not_host_legal_certification(scope):
    assert scope.grant.permitted_use_status == "EXPLICITLY_OWNER_CONFIRMED"
    assert scope.grant.region == "NOT_INDEPENDENTLY_OBSERVED"
    assert "20261030" in scope.grant.grant_id and scope.grant.start_utc_ms == START
    p = preflight(scope, Clock(START - 1))
    assert p["window_status"] == "GRANT_WINDOW_NOT_OPEN" and p["owner_documentary_gate"].startswith(
        "OWNER_ATTESTED"
    )
    assert not p["venue_permission_independently_verified"]


@pytest.mark.parametrize(
    "when,enabled,reason",
    [
        (START - 1, True, "NOT_OPEN"),
        (END, True, "EXPIRED"),
        (END + 2 * 86400000, True, "EXPIRED"),
        (START + 1, False, "DEFAULT_DISABLED"),
    ],
)
def test_zero_backend_calls_outside_window_or_default_disabled(when, enabled, reason, scope, tmp_path):
    clock = Clock(when)
    b = Backend(scope, clock)
    t = transport(scope, tmp_path, clock, b, enabled)
    with pytest.raises(PublicStop, match=reason):
        t.request("binance_usdm_server_time", {})
    assert not b.calls and not b.connections


@pytest.mark.parametrize(
    "id,params",
    [
        ("binance_usdm_bbo_rest", {}),
        ("private", {}),
        ("binance_usdm_oi", {"symbol": "ADAUSDT"}),
        ("binance_usdm_oi", {"symbol": "BTCUSDT", "apiKey": "bad"}),
        ("binance_usdm_funding_info", {"signature": "bad"}),
        (
            "binance_usdm_klines_rest",
            {
                "symbol": "BTCUSDT",
                "interval": "1m",
                "startTime": START - 60000,
                "endTime": START - 1,
                "limit": 1,
            },
        ),
    ],
)
def test_no_private_or_expanded_endpoint_or_history(id, params, scope, tmp_path):
    t = transport(scope, tmp_path)
    with pytest.raises(PublicStop):
        t.request(id, params)
    assert not t.backend.calls


@pytest.mark.parametrize("group", ["private", "spot", "all", "public/../private"])
def test_no_extra_ws_group(group, scope, tmp_path):
    t = transport(scope, tmp_path)
    with pytest.raises(PublicStop):
        t.open_group(group)
    assert not t.backend.connections


def test_emergency_stop_prevents_next_request(scope, tmp_path):
    t = transport(scope, tmp_path)
    t.stop_check = lambda: True
    with pytest.raises(PublicStop, match="EMERGENCY"):
        t.request("binance_usdm_server_time", {})
    assert not t.backend.calls


@pytest.mark.parametrize(
    "status,reason",
    [
        (403, "VENUE_ACCESS_DENIED"),
        (451, "VENUE_ACCESS_DENIED"),
        (429, "RATE_LIMIT"),
        (418, "RATE_LIMIT"),
        (302, "REDIRECT"),
    ],
)
def test_venue_denial_rate_and_redirect_stops_without_retry(status, reason, scope, tmp_path):
    clock = Clock()
    b = Backend(scope, clock, {"time": (status, {"msg": "blocked"})})
    t = transport(scope, tmp_path, clock, b)
    result = t.request("binance_usdm_server_time", {})
    assert result.status == status and reason in t.error
    with pytest.raises(PublicStop):
        t.request("binance_usdm_server_time", {})
    assert len(b.calls) == 1


def test_ordinary_timeout_is_not_terms_denial(scope, tmp_path):
    clock = Clock()
    b = Backend(scope, clock, {"time": TimeoutError()})
    t = transport(scope, tmp_path, clock, b)
    w = t.request("binance_usdm_server_time", {})
    assert w.error == "NETWORK_TIMEOUT" and t.error is None
    assert t.guard.store.get_value("next_allowed_mono") > clock.mono()


def test_closed_future_only_rest_repair_binding(scope):
    now = START + 180100
    url = scope.validate_request(
        "binance_usdm_klines_rest",
        {"symbol": "BTCUSDT", "interval": "1m", "startTime": START, "endTime": START + 119999, "limit": 2},
        now,
    )
    assert url == "https://fapi.binance.com/fapi/v1/klines"


def test_future_and_revoked_grants_rejected(scope, tmp_path):
    value = json.loads(scope.grant_path.read_text())
    value["source_grant"]["start_utc_ms"] = 1793491200000
    p = tmp_path / "forged.json"
    p.write_text(json.dumps(value))
    with pytest.raises(PublicStop, match="SCOPE"):
        load_scope(p)


def test_document_checks_are_not_feed_quality(scope, tmp_path):
    t = transport(scope, tmp_path)
    r = t.probe_document_website()
    assert len(r) == 5 and all(not x["observed_feed_quality"] for x in r)
    assert all("developers.binance.com" in url for url, _ in t.backend.calls)


def test_operator_launcher_before_window_exits_without_run(scope):
    # Current real clock is outside the approved future window in this engineering invocation.
    from btc_quant_agent.platform.canary.public_policy import SystemClock

    if START <= SystemClock().wall() < END:
        # Use default-deny, which is still valid if tests are repeated during the pilot.
        flag = []
        expected = "DEFAULT_DISABLED"
    else:
        flag = ["--enable-public-network"]
        expected = "WINDOW"
    p = subprocess.run(
        [sys.executable, "tools/launch_public_canary.py", "run", *flag],
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": "src"},
        timeout=10,
    )
    assert p.returncode == 2 and expected in p.stdout
    assert not (OUTPUT / "run/started.json").exists()


def test_global_venue_weight_header_stops_before_more_calls(scope, tmp_path):
    clock = Clock()
    b = Backend(scope, clock)
    b.last_headers = {"x-mbx-used-weight-1m": "60"}
    t = transport(scope, tmp_path, clock, b)
    w = t.request("binance_usdm_server_time", {})
    assert w.rate_headers == b.last_headers and t.error == "VENUE_IP_WEIGHT_CAP_REACHED"
    with pytest.raises(PublicStop):
        t.request("binance_usdm_server_time", {})
    assert len(b.calls) == 1


def test_ws_403_is_venue_denial_not_generic_reconnect(scope, tmp_path):
    class Denied(Exception):
        response = type("Response", (), {"status_code": 403})()

    clock = Clock()
    b = Backend(scope, clock)

    def fail(*a, **k):
        raise Denied()

    b.connect = fail
    t = transport(scope, tmp_path, clock, b)
    with pytest.raises(PublicStop, match="VENUE_ACCESS_DENIED"):
        t.open_group("public")
    failure = t.next(0)
    assert failure.status == 403 and failure.error == "VENUE_ACCESS_DENIED"
    assert not t.guard.store.get_value("connections")


def test_runtime_documents_change_stops_before_market_request(scope, tmp_path):
    clock = Clock()
    b = Backend(scope, clock)
    b.get = lambda *a, **kw: (200, "<html>changed</html>", clock.pair())
    t = transport(scope, tmp_path, clock, b)
    with pytest.raises(PublicStop, match="CONTRACT_CHANGED"):
        t.probe_document_website()
    assert t.metrics["rest_requests"] == 0


@pytest.mark.parametrize(
    "url",
    [
        "https://fapi.binance.com/fapi/v1/account",
        "https://fapi.binance.com/fapi/v1/order",
        "https://api.binance.com/api/v3/ticker/price",
        "https://fapi.binance.com/fapi/v1/time?apiKey=bad",
        "https://user:pw@fapi.binance.com/fapi/v1/time",
    ],
)
def test_real_http_backend_itself_rejects_private_or_changed_route(url, scope):
    from btc_quant_agent.platform.canary.public_io import HttpWsBackend

    clock = Clock()
    b = HttpWsBackend()
    b.bind_scope(scope, clock)
    b.set_guard(Window(clock).check)
    with pytest.raises(PublicStop):
        b.get(url, {}, 1, clock)
    assert b.http is None


def test_real_http_codec_with_in_memory_response_is_not_native_connection(scope):
    import httpx
    from btc_quant_agent.platform.canary.public_io import HttpWsBackend

    clock = Clock()
    b = HttpWsBackend()
    b.bind_scope(scope, clock)
    b.set_guard(Window(clock).check)
    observed = []

    def respond(request):
        observed.append(request)
        return httpx.Response(200, json={"serverTime": START + 1000}, headers={"X-MBX-USED-WEIGHT-1M": "1"})

    b.http = httpx.Client(transport=httpx.MockTransport(respond), trust_env=False, follow_redirects=False)
    status, text, first = b.get("https://fapi.binance.com/fapi/v1/time", {}, 1, clock)
    assert status == 200 and json.loads(text)["serverTime"] == START + 1000
    assert not observed[0].headers.get("authorization") and not observed[0].headers.get("cookie")
    assert b.last_headers["x-mbx-used-weight-1m"] == "1"
    b.close()
