"""Positive and negative tests for Layer 2 PRIVATE_USER_DATA client, allowlist, signer, redaction, and normalization."""

from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal
from typing import Any

import pytest

from quant_personal_account_b3.client import (
    CORE_ALLOWLIST,
    ROUTE_ACCOUNT,
    ROUTE_ALL_ALGO_ORDERS,
    ROUTE_ALL_ORDERS,
    ROUTE_INCOME,
    ROUTE_OPEN_ALGO_ORDERS,
    ROUTE_OPEN_ORDERS,
    ROUTE_POSITION_RISK,
    ROUTE_USER_TRADES,
    DeterministicFakeClock,
    DeterministicFakeSigner,
    DisabledLiveHttpTransport,
    DisabledProductionCredentialProvider,
    FakeCredentialProvider,
    OfflineFixtureTransport,
    PrivateUserDataClient,
    SignedPrivateRequest,
    TransportResponse,
)
from quant_personal_account_b3.fixtures import (
    DEFAULT_SYNTHETIC_AS_OF_MS,
    build_synthetic_scenario,
)
from quant_personal_account_b3.models import (
    DAY_MS,
    PRIVATE_CONNECTION_NOT_ACTIVATED,
    REDACTED,
    SEVEN_DAYS_MS,
    PermissionDeniedError,
    PrivateConnectionNotActivatedError,
    PrivateRequestRejectedError,
    RateLimitError,
    ResponseValidationError,
    TimestampSyncError,
    parse_decimal,
    redact_mapping,
    redact_text,
)
from quant_personal_account_b3.normalize import (
    build_endpoint_coverage,
    compute_overall_snapshot_status,
    normalize_account,
    normalize_algo_orders,
    normalize_fills,
    normalize_income,
    normalize_orders,
    normalize_positions,
)


def _make_client(
    routes: dict[str, Any] | None = None,
    *,
    handler: Any = None,
    clock: DeterministicFakeClock | None = None,
) -> tuple[PrivateUserDataClient, OfflineFixtureTransport, FakeCredentialProvider, DeterministicFakeClock]:
    clk = clock or DeterministicFakeClock(wall_ms=1_735_691_520_000, venue_offset_ms=150)
    creds = FakeCredentialProvider(
        key_id="unit-test-key",
        api_key="FAKE_KEY_SECRET_SENTINEL_XYZ",
        secret="FAKE_SIGNING_SECRET_SENTINEL_999",
    )
    signer = DeterministicFakeSigner()
    transport = OfflineFixtureTransport(routes=routes, handler=handler, clock=clk)
    client = PrivateUserDataClient(transport=transport, credentials=creds, signer=signer, clock=clk)
    return client, transport, creds, clk


def test_core_allowlist_contains_exact_eight_get_routes() -> None:
    expected = {
        ROUTE_ACCOUNT,
        ROUTE_POSITION_RISK,
        ROUTE_OPEN_ORDERS,
        ROUTE_OPEN_ALGO_ORDERS,
        ROUTE_USER_TRADES,
        ROUTE_ALL_ORDERS,
        ROUTE_ALL_ALGO_ORDERS,
        ROUTE_INCOME,
    }
    assert set(CORE_ALLOWLIST.keys()) == expected
    assert all(spec.method == "GET" for spec in CORE_ALLOWLIST.values())


def test_deterministic_fake_signed_get_for_all_eight_allowlisted_endpoints() -> None:
    routes: dict[str, Any] = {
        ROUTE_ACCOUNT: {
            "totalWalletBalance": "1000",
            "availableBalance": "900",
            "totalMarginBalance": "1000",
            "totalUnrealizedProfit": "0",
        },
        ROUTE_POSITION_RISK: [],
        ROUTE_OPEN_ORDERS: [],
        ROUTE_OPEN_ALGO_ORDERS: [],
        ROUTE_USER_TRADES: [],
        ROUTE_ALL_ORDERS: [],
        ROUTE_ALL_ALGO_ORDERS: [],
        ROUTE_INCOME: [],
    }
    client, transport, creds, clk = _make_client(routes=routes)
    base_end = clk.venue_time_estimate_ms()

    calls = [
        (ROUTE_ACCOUNT, None),
        (ROUTE_POSITION_RISK, {"symbol": "BTCUSDT"}),
        (ROUTE_OPEN_ORDERS, {"symbol": "BTCUSDT"}),
        (ROUTE_OPEN_ALGO_ORDERS, {"symbol": "BTCUSDT", "algoType": "CONDITIONAL"}),
        (ROUTE_USER_TRADES, {"symbol": "BTCUSDT", "startTime": base_end - SEVEN_DAYS_MS, "endTime": base_end, "limit": 500}),
        (ROUTE_ALL_ORDERS, {"symbol": "BTCUSDT", "startTime": base_end - 6 * DAY_MS, "endTime": base_end, "limit": 500}),
        (ROUTE_ALL_ALGO_ORDERS, {"symbol": "BTCUSDT", "startTime": base_end - 6 * DAY_MS, "endTime": base_end, "page": 1, "limit": 100}),
        (ROUTE_INCOME, {"symbol": "BTCUSDT", "incomeType": "FUNDING_FEE", "limit": 100}),
    ]
    for path, params in calls:
        _, receipt = client.request("GET", path, params)
        assert receipt.endpoint == path
        assert receipt.http_status == 200
        assert len(receipt.raw_sha256) == 64

    assert transport.call_count == 8
    secret_bytes = creds.get_credentials().secret.encode("utf-8")
    for req in transport.observed_requests:
        assert req.method == "GET"
        expected_sig = hmac.new(secret_bytes, req.canonical_unsigned_query.encode("utf-8"), hashlib.sha256).hexdigest()
        assert req.signed_query == f"{req.canonical_unsigned_query}&signature={expected_sig}"
        assert req.headers["X-MBX-APIKEY"] == creds.get_credentials().api_key


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "get", "Get", ""])
def test_non_get_methods_rejected_before_transport_zero_calls(method: str) -> None:
    client, transport, _, _ = _make_client(routes={ROUTE_ACCOUNT: {}})
    with pytest.raises(PrivateRequestRejectedError) as exc_info:
        client.request(method, ROUTE_ACCOUNT)
    assert exc_info.value.code == "METHOD_NOT_ALLOWED"
    assert transport.call_count == 0


@pytest.mark.parametrize(
    "path",
    [
        "/fapi/v1/order",
        "/fapi/v1/batchOrders",
        "/fapi/v1/allOpenOrders",
        "/fapi/v1/leverage",
        "/fapi/v1/marginType",
        "/fapi/v1/positionMargin",
        "/fapi/v1/listenKey",
        "/sapi/v1/capital/withdraw/apply",
        "/sapi/v1/account/apiRestrictions",
        "/fapi/v1/commissionRate",
        "//fapi/v3/account",
        "/fapi/v3/account/",
        "/fapi/v3/../v3/account",
        "/fapi/v3/%61ccount",
        "/fapi/v3/account?symbol=BTCUSDT",
        "/FAPI/v3/account",
        " /fapi/v3/account",
    ],
)
def test_unknown_routes_layer3_and_path_aliases_rejected_before_transport(path: str) -> None:
    client, transport, _, _ = _make_client(routes={ROUTE_ACCOUNT: {}})
    with pytest.raises(PrivateRequestRejectedError) as exc_info:
        client.request("GET", path)
    assert exc_info.value.code == "ENDPOINT_NOT_ALLOWLISTED"
    assert transport.call_count == 0


def test_invalid_unexpected_duplicate_and_window_params_rejected_before_transport() -> None:
    client, transport, _, clk = _make_client(routes={})
    now = clk.venue_time_estimate_ms()

    bad_calls: list[tuple[str, Any, str]] = [
        # Unexpected param
        (ROUTE_ACCOUNT, {"symbol": "BTCUSDT"}, "UNEXPECTED_PARAM"),
        (ROUTE_OPEN_ORDERS, {"side": "BUY"}, "UNEXPECTED_PARAM"),
        # Caller-supplied signature forbidden
        (ROUTE_ACCOUNT, {"signature": "deadbeef"}, "CALLER_SIGNATURE_FORBIDDEN"),
        # Duplicate security-sensitive params via sequence of pairs
        (ROUTE_ACCOUNT, [("recvWindow", 5000), ("recvWindow", 5000)], "DUPLICATE_SECURITY_PARAM"),
        (ROUTE_ACCOUNT, [("timestamp", now), ("timestamp", now)], "DUPLICATE_SECURITY_PARAM"),
        (ROUTE_POSITION_RISK, [("symbol", "BTCUSDT"), ("symbol", "ETHUSDT")], "DUPLICATE_PARAM"),
        # Missing required symbol
        (ROUTE_USER_TRADES, {"limit": 10}, "MISSING_REQUIRED_PARAM"),
        (ROUTE_ALL_ORDERS, {"limit": 10}, "MISSING_REQUIRED_PARAM"),
        (ROUTE_ALL_ALGO_ORDERS, {"limit": 10}, "MISSING_REQUIRED_PARAM"),
        # Malformed symbol / timestamp / recvWindow / limit
        (ROUTE_POSITION_RISK, {"symbol": "btcusdt"}, "INVALID_SYMBOL"),
        (ROUTE_POSITION_RISK, {"symbol": "BTCUSDT&side=BUY"}, "INVALID_SYMBOL"),
        (ROUTE_ACCOUNT, {"timestamp": "1735691520000"}, "INVALID_PARAM_TYPE"),
        (ROUTE_ACCOUNT, {"timestamp": True}, "INVALID_PARAM_TYPE"),
        (ROUTE_ACCOUNT, {"timestamp": 123}, "PARAM_BELOW_MIN"),
        (ROUTE_ACCOUNT, {"recvWindow": 0}, "PARAM_BELOW_MIN"),
        (ROUTE_ACCOUNT, {"recvWindow": 60_001}, "PARAM_ABOVE_MAX"),
        (ROUTE_USER_TRADES, {"symbol": "BTCUSDT", "limit": 1001}, "PARAM_ABOVE_MAX"),
        (ROUTE_ALL_ALGO_ORDERS, {"symbol": "BTCUSDT", "limit": 101}, "PARAM_ABOVE_MAX"),
        # Window constraints: userTrades <= 7d; allOrders & allAlgoOrders strictly < 7d; end >= start
        (ROUTE_USER_TRADES, {"symbol": "BTCUSDT", "startTime": now - SEVEN_DAYS_MS - 1, "endTime": now}, "TIME_WINDOW_EXCEEDS_7_DAYS"),
        (ROUTE_ALL_ORDERS, {"symbol": "BTCUSDT", "startTime": now - SEVEN_DAYS_MS, "endTime": now}, "TIME_WINDOW_MUST_BE_UNDER_7_DAYS"),
        (ROUTE_ALL_ALGO_ORDERS, {"symbol": "BTCUSDT", "startTime": now - SEVEN_DAYS_MS, "endTime": now}, "TIME_WINDOW_MUST_BE_UNDER_7_DAYS"),
        (ROUTE_USER_TRADES, {"symbol": "BTCUSDT", "startTime": now, "endTime": now - 1000}, "INVALID_TIME_WINDOW_ORDER"),
        # fromId conflicts with startTime/endTime on userTrades
        (ROUTE_USER_TRADES, {"symbol": "BTCUSDT", "fromId": 1, "startTime": now - 1000}, "FROM_ID_CONFLICTS_WITH_TIME_WINDOW"),
    ]
    for path, params, expected_code in bad_calls:
        with pytest.raises(PrivateRequestRejectedError) as exc_info:
            client.request("GET", path, params)
        assert exc_info.value.code == expected_code, f"Path {path} params {params}: got {exc_info.value.code}"
    assert transport.call_count == 0


def test_disabled_production_secret_provider_and_live_http_transport_fail_closed() -> None:
    prod_creds = DisabledProductionCredentialProvider()
    live_transport = DisabledLiveHttpTransport()
    fake_creds = FakeCredentialProvider()
    fake_transport = OfflineFixtureTransport()
    signer = DeterministicFakeSigner()
    clock = DeterministicFakeClock()

    with pytest.raises(PrivateConnectionNotActivatedError) as e1:
        prod_creds.get_credentials()
    assert e1.value.code == PRIVATE_CONNECTION_NOT_ACTIVATED

    dummy_req = SignedPrivateRequest(
        method="GET",
        path=ROUTE_ACCOUNT,
        canonical_unsigned_query="recvWindow=5000&timestamp=1735691520000",
        signed_query="recvWindow=5000&timestamp=1735691520000&signature=abc",
        headers={"X-MBX-APIKEY": "fake"},
        redacted_params={},
        weight_cost=5,
        signer_mode="TEST",
    )
    with pytest.raises(PrivateConnectionNotActivatedError) as e2:
        live_transport.send(dummy_req)
    assert e2.value.code == PRIVATE_CONNECTION_NOT_ACTIVATED

    with pytest.raises(PrivateConnectionNotActivatedError):
        PrivateUserDataClient(transport=live_transport, credentials=fake_creds, signer=signer, clock=clock)

    with pytest.raises(PrivateConnectionNotActivatedError):
        PrivateUserDataClient(transport=fake_transport, credentials=prod_creds, signer=signer, clock=clock)


def test_permission_denied_never_retries_and_timestamp_resync_is_bounded_to_one() -> None:
    # 1. Permission denied (401, 403, -2015): strictly 1 call, 0 retries!
    for status, body in (
        (401, {"code": -2015, "msg": "Invalid API-key, IP, or permissions for action"}),
        (403, {"code": -2015, "msg": "Forbidden"}),
        (200, {"code": -2014, "msg": "API-key format invalid"}),
    ):
        resp = TransportResponse(status_code=status, raw_body=json.dumps(body).encode("utf-8"))
        client, transport, _, clk = _make_client(routes={ROUTE_ACCOUNT: resp})
        with pytest.raises(PermissionDeniedError) as exc_info:
            client.get_account()
        assert exc_info.value.code == "PERMISSION_DENIED_FAIL_CLOSED"
        assert transport.call_count == 1
        assert clk.resync_count == 0

    # 2. Timestamp drift (-1021): succeeds on single bounded resync!
    attempts = {"n": 0}

    def drift_then_ok(_req: SignedPrivateRequest) -> TransportResponse:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return TransportResponse(
                status_code=400,
                raw_body=json.dumps({"code": -1021, "msg": "Timestamp for this request is outside of the recvWindow"}).encode(),
            )
        return TransportResponse(
            status_code=200,
            raw_body=json.dumps(
                {
                    "totalWalletBalance": "100",
                    "availableBalance": "100",
                    "totalMarginBalance": "100",
                    "totalUnrealizedProfit": "0",
                }
            ).encode(),
        )

    clk = DeterministicFakeClock(venue_offset_ms=-8000, resync_target_offset_ms=50)
    client, transport, _, _ = _make_client(handler=drift_then_ok, clock=clk)
    data, _ = client.get_account()
    assert data["totalWalletBalance"] == "100"
    assert transport.call_count == 2
    assert clk.resync_count == 1

    # 3. Persistent -1021 fails closed after at most ONE resync (never unbounded!).
    always_1021 = TransportResponse(
        status_code=400,
        raw_body=json.dumps({"code": -1021, "msg": "Timestamp out of sync"}).encode(),
    )
    clk2 = DeterministicFakeClock(venue_offset_ms=-8000, resync_target_offset_ms=-8000)
    client2, transport2, _, _ = _make_client(routes={ROUTE_ACCOUNT: always_1021}, clock=clk2)
    with pytest.raises(TimestampSyncError) as ts_exc:
        client2.get_account()
    assert ts_exc.value.code == "TIMESTAMP_RESYNC_EXHAUSTED"
    assert transport2.call_count == 2
    assert clk2.resync_count == 1

    # 4. Rate limit 429 and IP ban 418 fail closed without retrying.
    for code, expected in ((429, "RATE_LIMITED_429"), (418, "IP_BANNED_418")):
        rl_resp = TransportResponse(status_code=code, raw_body=b'{"code":-1003,"msg":"Too many requests"}', headers={"Retry-After": "15"})
        c_rl, t_rl, _, _ = _make_client(routes={ROUTE_ACCOUNT: rl_resp})
        with pytest.raises(RateLimitError) as rl_exc:
            c_rl.get_account()
        assert rl_exc.value.code == expected
        assert rl_exc.value.retry_after_ms == 15_000
        assert t_rl.call_count == 1


def test_strict_secret_and_private_payload_redaction() -> None:
    def error_echoing_secret(req: SignedPrivateRequest) -> TransportResponse:
        # Simulate an adversarial error message attempting to echo api key, signature, and query!
        leaked_msg = (
            f"Bad request X-MBX-APIKEY={req.headers['X-MBX-APIKEY']} "
            f"query={req.signed_query} secret=FAKE_SIGNING_SECRET_SENTINEL_999"
        )
        return TransportResponse(
            status_code=400,
            raw_body=json.dumps({"code": -1100, "msg": leaked_msg}).encode("utf-8"),
        )

    client, transport, creds, _ = _make_client(handler=error_echoing_secret)
    mat = creds.get_credentials()
    assert mat.api_key not in repr(mat)
    assert mat.secret not in repr(mat)
    assert mat.api_key not in str(mat)
    assert mat.secret not in str(mat)

    with pytest.raises(ResponseValidationError) as exc_info:
        client.get_account()
    err_str = str(exc_info.value)
    assert mat.api_key not in err_str
    assert mat.secret not in err_str
    assert REDACTED in err_str

    # Check redacted transport history and SignedPrivateRequest repr.
    req = transport.observed_requests[0]
    sig = req.signed_query.split("signature=")[1]
    assert mat.api_key not in repr(req)
    assert sig not in repr(req)
    assert sig not in err_str
    hist_json = json.dumps(transport.redacted_history)
    assert mat.api_key not in hist_json
    assert mat.secret not in hist_json
    assert sig not in hist_json

    # Check private balance fields are redacted by redact_mapping.
    sample_log = {
        "endpoint": ROUTE_ACCOUNT,
        "walletBalance": "99999.12",
        "availableBalance": "88888.34",
        "signature": "abcdef123456",
        "nested": {"realizedPnl": "1234.56", "safe": "ok"},
    }
    sanitized = redact_mapping(sample_log)
    assert sanitized["walletBalance"] == REDACTED
    assert sanitized["availableBalance"] == REDACTED
    assert sanitized["signature"] == REDACTED
    assert sanitized["nested"]["realizedPnl"] == REDACTED
    assert sanitized["nested"]["safe"] == "ok"
    assert "abcdef" not in redact_text("timestamp=1735691520000&recvWindow=5000&signature=abcdef")


def test_decimal_strictness_rejects_binary_float_and_non_finite_json() -> None:
    with pytest.raises(ResponseValidationError) as e_float:
        parse_decimal(100.75, "price")
    assert e_float.value.code == "BINARY_FLOAT_PROHIBITED"

    with pytest.raises(ResponseValidationError) as e_bool:
        parse_decimal(True, "price")
    assert e_bool.value.code == "INVALID_DECIMAL_BOOL"

    # NaN in JSON body fails closed at client validation.
    nan_resp = TransportResponse(status_code=200, raw_body=b'{"totalWalletBalance": NaN}')
    client, _, _, _ = _make_client(routes={ROUTE_ACCOUNT: nan_resp})
    with pytest.raises(ResponseValidationError) as e_nan:
        client.get_account()
    assert e_nan.value.code == "NON_FINITE_JSON_CONSTANT"


def test_normalization_preserves_decimal_unknown_fields_and_unknown_enums_and_hedge_modes() -> None:
    acc = normalize_account(
        {
            "totalWalletBalance": "10000.12345678",
            "availableBalance": "9500.00000000",
            "totalMarginBalance": "10025.12345678",
            "totalUnrealizedProfit": "25.00000000",
            "brandNewFutureField": {"nested": True},
        }
    )
    assert acc.wallet_balance == Decimal("10000.12345678")
    assert acc.raw_unknown_fields == {"brandNewFutureField": {"nested": True}}

    positions = normalize_positions(
        [
            {
                "symbol": "BTCUSDT",
                "positionAmt": "0.500",
                "positionSide": "LONG",
                "entryPrice": "100.75",
                "markPrice": "101.00",
                "unRealizedProfit": "0.125",
                "liquidationPrice": "90.00",
                "leverage": "10",
                "marginType": "FUTURE_MARGIN_MODE_X",
                "unknownPosField": "keep",
            },
            {
                "symbol": "BTCUSDT",
                "positionAmt": "-0.250",
                "positionSide": "SHORT",
                "entryPrice": "102.00",
                "markPrice": "101.00",
                "unRealizedProfit": "0.250",
                "liquidationPrice": "112.00",
                "leverage": "10",
                "marginType": "isolated",
            },
        ]
    )
    assert len(positions) == 2
    assert positions[0].position_mode == "HEDGE"
    assert positions[0].effective_direction == "LONG"
    assert positions[0].unknown_enums == {"marginType": "FUTURE_MARGIN_MODE_X"}
    assert positions[0].raw_unknown_fields == {"unknownPosField": "keep"}
    assert positions[1].effective_direction == "SHORT"
    assert positions[1].abs_qty == Decimal("0.250")

    # Empty positionRisk NEVER fabricates zero position rows.
    assert normalize_positions([]) == ()

    orders = normalize_orders(
        [
            {
                "symbol": "BTCUSDT",
                "orderId": 1,
                "clientOrderId": "c1",
                "side": "SELL",
                "positionSide": "BOTH",
                "type": "FUTURE_ORDER_TYPE",
                "status": "NEW",
                "origQty": "1.0",
                "executedQty": "0.25",
                "price": "105.0",
                "stopPrice": "104.5",
                "workingType": "MARK_PRICE",
                "closePosition": False,
                "reduceOnly": True,
                "timeInForce": "GTC",
                "extraOrderTag": "abc",
            }
        ],
        source_endpoint=ROUTE_OPEN_ORDERS,
    )
    assert orders[0].remaining_qty == Decimal("0.75")
    assert orders[0].unknown_enums == {"type": "FUTURE_ORDER_TYPE"}
    assert orders[0].raw_unknown_fields == {"extraOrderTag": "abc"}

    algos = normalize_algo_orders(
        [
            {
                "symbol": "BTCUSDT",
                "algoId": 77,
                "clientAlgoId": "ca77",
                "algoType": "CONDITIONAL",
                "orderType": "TRAILING_STOP_MARKET",
                "algoStatus": "FUTURE_ALGO_STATUS",
                "side": "SELL",
                "positionSide": "BOTH",
                "quantity": "0.5",
                "triggerPrice": "102.0",
                "activatePrice": "102.0",
                "callbackRate": "1.5",
                "workingType": "MARK_PRICE",
                "closePosition": False,
                "reduceOnly": True,
                "createTime": 1_735_691_550_000,
                "updateTime": 1_735_691_560_000,
                "extraAlgoField": 123,
            }
        ],
        source_endpoint=ROUTE_OPEN_ALGO_ORDERS,
    )
    assert algos[0].unknown_enums == {"algoStatus": "FUTURE_ALGO_STATUS"}
    assert algos[0].raw_unknown_fields == {"extraAlgoField": 123}

    fills = normalize_fills(
        [
            {
                "symbol": "BTCUSDT",
                "id": 500,
                "orderId": 1,
                "side": "SELL",
                "positionSide": "BOTH",
                "price": "103.33",
                "qty": "0.500",
                "quoteQty": "51.665",
                "realizedPnl": "1.29",
                "commission": "0.0258325",
                "commissionAsset": "USDT",
                "time": 1_735_691_570_000,
            }
        ]
    )
    assert fills[0].realized_pnl == Decimal("1.29")

    inc = normalize_income(
        [
            {
                "tranId": "T1",
                "symbol": "BTCUSDT",
                "incomeType": "CUSTOM_FUTURE_TYPE",
                "income": "-0.015",
                "asset": "USDT",
                "info": "funding",
                "time": 1_735_691_580_000,
                "extraInc": "ok",
            }
        ]
    )
    assert inc[0].unknown_enums == {"incomeType": "CUSTOM_FUTURE_TYPE"}
    assert inc[0].raw_unknown_fields == {"extraInc": "ok"}


def test_non_atomic_snapshot_coverage_and_overall_status_transitions() -> None:
    bundle = build_synthetic_scenario("one_way_protected", as_of_venue_ms=DEFAULT_SYNTHETIC_AS_OF_MS)
    _, r_acc = bundle.client.get_account()
    _, r_pos = bundle.client.get_position_risk(symbol="BTCUSDT")
    _, r_oo = bundle.client.get_open_orders(symbol="BTCUSDT")
    _, r_oao = bundle.client.get_open_algo_orders(symbol="BTCUSDT")

    # Each endpoint has its own distinct request/receive timing (NON_ATOMIC).
    assert r_acc.receive_monotonic_ms < r_pos.receive_monotonic_ms < r_oo.receive_monotonic_ms < r_oao.receive_monotonic_ms

    as_of = DEFAULT_SYNTHETIC_AS_OF_MS
    cov_ok = {
        ROUTE_ACCOUNT: build_endpoint_coverage(
            endpoint=ROUTE_ACCOUNT, symbol=None, as_of_venue_ms=as_of, receipt=r_acc, record_count=1, freshness_limit_ms=60_000
        ),
        ROUTE_POSITION_RISK: build_endpoint_coverage(
            endpoint=ROUTE_POSITION_RISK, symbol="BTCUSDT", as_of_venue_ms=as_of, receipt=r_pos, record_count=1, freshness_limit_ms=60_000
        ),
        ROUTE_OPEN_ORDERS: build_endpoint_coverage(
            endpoint=ROUTE_OPEN_ORDERS, symbol="BTCUSDT", as_of_venue_ms=as_of, receipt=r_oo, record_count=0, freshness_limit_ms=60_000
        ),
        ROUTE_OPEN_ALGO_ORDERS: build_endpoint_coverage(
            endpoint=ROUTE_OPEN_ALGO_ORDERS, symbol="BTCUSDT", as_of_venue_ms=as_of, receipt=r_oao, record_count=2, freshness_limit_ms=60_000
        ),
    }
    assert compute_overall_snapshot_status(cov_ok) == "SYNTHETIC_CONNECTED"

    # Missing openAlgoOrders => PARTIAL (never complete!).
    cov_partial = dict(cov_ok)
    cov_partial[ROUTE_OPEN_ALGO_ORDERS] = build_endpoint_coverage(
        endpoint=ROUTE_OPEN_ALGO_ORDERS,
        symbol="BTCUSDT",
        as_of_venue_ms=as_of,
        receipt=None,
        record_count=0,
        freshness_limit_ms=60_000,
        error_code="ENDPOINT_ERROR_RESPONSE",
    )
    assert compute_overall_snapshot_status(cov_partial) == "PARTIAL"

    # Stale positionRisk => STALE.
    cov_stale = dict(cov_ok)
    cov_stale[ROUTE_POSITION_RISK] = build_endpoint_coverage(
        endpoint=ROUTE_POSITION_RISK,
        symbol="BTCUSDT",
        as_of_venue_ms=as_of + 120_000,
        receipt=r_pos,
        record_count=1,
        freshness_limit_ms=60_000,
    )
    assert cov_stale[ROUTE_POSITION_RISK].status == "STALE"
    assert compute_overall_snapshot_status(cov_stale) == "STALE"
