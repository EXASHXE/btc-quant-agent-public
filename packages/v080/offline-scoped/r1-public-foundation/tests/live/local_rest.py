"""Fabricated REST behind a real loopback CONNECT/TLS server, never Binance."""

import json
import ssl
import time
from urllib.parse import urlsplit, parse_qs

from helpers import LocalVenue
from btc_quant_agent.platform.rc_fixture import _hourly, TRIGGER
from btc_quant_agent.platform.swing import INTERVALS


def exchange_info():
    return {
        "rateLimits": [
            {"rateLimitType": "REQUEST_WEIGHT", "interval": "MINUTE", "intervalNum": 1, "limit": 2400}
        ],
        "symbols": [
            {
                "symbol": s,
                "pair": s,
                "contractType": "PERPETUAL",
                "quoteAsset": "USDT",
                "marginAsset": "USDT",
                "baseAsset": s[:-4],
                "status": "TRADING",
            }
            for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT")
        ],
    }


class RestVenue(LocalVenue):
    def __init__(self, directory, *, flat=False, **kwargs):
        self.epoch = time.monotonic()
        self.calls = []
        self.status = 200
        self.fault = None
        self.data = {}
        for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
            hourly = _hourly(symbol, flat or symbol != "BTCUSDT")
            for interval in ("1D", "4H", "1H"):
                width = INTERVALS[interval] // INTERVALS["1H"]
                rows = []
                for index in range(0, len(hourly), width):
                    group = hourly[index : index + width]
                    rows.append(
                        [
                            group[0].open_time_ms,
                            str(group[0].open),
                            str(max(c.high for c in group)),
                            str(min(c.low for c in group)),
                            str(group[-1].close),
                            str(sum(c.volume for c in group)),
                            group[-1].close_time_ms,
                            str(sum(c.quote_volume for c in group)),
                            100,
                            "0",
                            "0",
                            "0",
                        ]
                    )
                self.data[(symbol, interval)] = rows
        super().__init__(directory, None, [], **kwargs)

    @property
    def qa(self):
        return {"host": "127.0.0.1", "port": self.proxy.getsockname()[1], "cafile": str(self.cert)}

    def body(self, path):
        url = urlsplit(path)
        if url.path == "/fapi/v1/time":
            return {"serverTime": TRIGGER + 125000 + int((time.monotonic() - self.epoch) * 1000)}
        if url.path == "/fapi/v1/exchangeInfo":
            return exchange_info()
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        interval = {"1d": "1D", "4h": "4H", "1h": "1H"}[query["interval"]]
        rows = [
            list(r)
            for r in self.data[(query["symbol"], interval)]
            if int(query["startTime"]) <= r[0] <= int(query["endTime"])
        ][: int(query["limit"])]
        if self.fault == "revision":
            rows[-1][5] = str(float(rows[-1][5]) + 1)
        return rows

    def handle_target(self, sock):
        try:
            with self.context.wrap_socket(sock, server_side=True) as tls:
                tls.settimeout(5)
                request = self.head(tls)
                path = request.split(b" ")[1].decode()
                self.calls.append(path)
                if self.fault == "hang":
                    self.done.wait(5)
                raw = json.dumps(self.body(path)).encode()
                if self.fault == "oversize":
                    raw = b" " * 2097200
                tls.sendall(
                    (
                        f"HTTP/1.1 {self.status} QA\r\nContent-Type: application/json\r\n"
                        f"Content-Length: {len(raw)}\r\nConnection: close\r\n\r\n"
                    ).encode()
                    + raw
                )
        except (OSError, EOFError, ssl.SSLError) as e:
            self.errors.append(type(e).__name__)


def candle_row(opening, size):
    return [opening, "100", "110", "90", "105", "10", opening + size - 1, "1000", 10, "0", "0", "0"]
