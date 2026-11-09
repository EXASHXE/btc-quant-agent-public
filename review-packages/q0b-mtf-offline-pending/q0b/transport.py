"""Pure Binance-shaped fixture decoder. It cannot acquire data or qualify live time."""
from .schema import Bar, Batch, INTERVALS, Quote, digest


def number(value):
    if type(value) not in (str, int, float):
        raise ValueError("NUMERIC_WIRE_FIELD_REQUIRED")
    result = float(value)
    # Admission performs full finite/OHLC validation before any strategy reads.
    return result


def decode_fixture(request, payload, *, received_ms, available_ms, exchange_lower_ms):
    """Return typed but unadmitted records plus immutable raw-response provenance.

    A future integration must provide an accepted Strict/O proof externally; this
    synthetic decoder does not mint that proof and has no production activation.
    """
    if not all(type(t) is int for t in (received_ms, available_ms, exchange_lower_ms)):
        raise ValueError("INTEGER_RECEIPT_TIMES_REQUIRED")
    if not exchange_lower_ms <= received_ms <= available_ms:
        raise ValueError("RECEIPT_CAUSALITY")
    if request.method != "GET" or request.params.get("symbol") != request.symbol:
        raise ValueError("REQUEST_IDENTITY_OR_METHOD")
    if request.endpoint == "/fapi/v1/klines":
        if not isinstance(payload, list) or not payload:
            raise ValueError("NONEMPTY_KLINE_ARRAY_REQUIRED")
        if (request.interval not in INTERVALS or len(payload) > request.params["limit"]
                or request.params.get("interval") != request.interval.lower()):
            raise ValueError("WIRE_LIMIT_OR_INTERVAL")
        bars = []
        for row in payload:
            if (not isinstance(row, list) or len(row) != 12 or type(row[0]) is not int
                    or type(row[6]) is not int):
                raise ValueError("BINANCE_12_FIELD_KLINE_REQUIRED")
            end = row[6] + 1
            bars.append(Bar(
                request.symbol, request.interval, row[0], end, row[6],
                *(number(v) for v in row[1:6]), available_ms, received_ms, exchange_lower_ms,
                closed=end <= exchange_lower_ms,
            ))
        value = Batch(request.symbol, request.interval, tuple(bars),
                      request.params["startTime"], request.params["endTime"] + 1)
    elif request.endpoint == "/fapi/v1/ticker/bookTicker":
        fields = {"symbol", "bidPrice", "askPrice", "bidQty", "askQty", "time"}
        if (not isinstance(payload, dict) or set(payload) != fields
                or payload["symbol"] != request.symbol or type(payload["time"]) is not int):
            raise ValueError("QUOTE_WIRE_SCHEMA_OR_IDENTITY")
        value = Quote(request.symbol, *(number(payload[k]) for k in
                                       ("bidPrice", "askPrice", "bidQty", "askQty")),
                      payload["time"], available_ms, received_ms)
    else:
        raise ValueError("ONLY_BAR_AND_QUOTE_FIXTURES_ARE_DECODED")
    return value, {
        "schema": "Q0B_TRANSPORT_RECEIPT_V2", "request_id": request.identity,
        "response_sha256": digest(payload), "received_ms": received_ms,
        "available_ms": available_ms, "exchange_lower_ms": exchange_lower_ms,
        "provenance": "SYNTHETIC_Q0B_V2", "live_time_authority": False,
    }
