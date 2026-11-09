"""Pure-stdlib deterministic OHLCV fixtures and ephemeral loopback TLS server (never external)."""

from __future__ import annotations

import json
import math
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import threading
import time
from typing import Any
from urllib.parse import parse_qs, urlsplit

TRIGGER = 1793923200000  # 2026-11-06 00:00 UTC (matches rc_fixture.TRIGGER)
INTERVALS = {"1H": 3_600_000, "4H": 14_400_000, "1D": 86_400_000}
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")


def find_openssl() -> str:
    found = shutil.which("openssl")
    if found:
        return found
    for candidate in (
        r"C:\Program Files\Git\usr\bin\openssl.exe",
        r"C:\Program Files\OpenSSL-Win64\bin\openssl.exe",
    ):
        if Path(candidate).is_file():
            return candidate
    raise RuntimeError("OPENSSL_EXECUTABLE_NOT_FOUND")


def create_ephemeral_ca_and_leaf(
    directory: Path, *, sni_host: str = "fapi.binance.com"
) -> tuple[Path, Path, Path]:
    """Generate a temporary CA cert + CA-signed leaf cert/key for loopback TLS QA."""
    directory.mkdir(parents=True, exist_ok=True)
    openssl = find_openssl()
    ca_key = directory / "ca.key"
    ca_crt = directory / "ca.crt"
    leaf_key = directory / "leaf.key"
    leaf_csr = directory / "leaf.csr"
    leaf_crt = directory / "leaf.crt"
    ext_cfg = directory / "leaf_ext.cnf"

    subprocess.run(
        [
            openssl,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(ca_key),
            "-out",
            str(ca_crt),
            "-days",
            "2",
            "-subj",
            "/CN=Quant-QA-Loopback-Root-CA",
            "-addext",
            "basicConstraints=critical,CA:TRUE",
            "-addext",
            "keyUsage=critical,keyCertSign,cRLSign",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            openssl,
            "req",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(leaf_key),
            "-out",
            str(leaf_csr),
            "-subj",
            f"/CN={sni_host}",
        ],
        check=True,
        capture_output=True,
    )
    ext_cfg.write_text(
        "basicConstraints=CA:FALSE\n"
        "keyUsage=critical,digitalSignature,keyEncipherment\n"
        "extendedKeyUsage=serverAuth\n"
        f"subjectAltName=DNS:{sni_host},IP:127.0.0.1\n",
        encoding="utf-8",
    )
    subprocess.run(
        [
            openssl,
            "x509",
            "-req",
            "-in",
            str(leaf_csr),
            "-CA",
            str(ca_crt),
            "-CAkey",
            str(ca_key),
            "-CAcreateserial",
            "-out",
            str(leaf_crt),
            "-days",
            "2",
            "-sha256",
            "-extfile",
            str(ext_cfg),
        ],
        check=True,
        capture_output=True,
    )
    return ca_crt, leaf_crt, leaf_key


def build_hourly_series(symbol: str, flat: bool) -> list[dict[str, Any]]:
    """Pure-stdlib equivalent of rc_fixture._hourly for Windows + WSL parity."""
    scale = {"BTCUSDT": 100.0, "ETHUSDT": 10.0, "SOLUSDT": 1.0}[symbol]
    suffix = [
        126,
        128,
        130,
        132,
        134,
        146,
        132,
        130,
        129,
        130,
        131,
        130,
        129,
        129.5,
        130,
        131,
        131.5,
        132,
        131,
        130,
        129.5,
        130,
        130.5,
        132.5,
    ]
    count = 80 * 6
    closes = (
        [120.0] * count
        if flat
        else [
            100 + 26 * i / (count - len(suffix)) + 0.6 * math.sin(i * math.pi / 4)
            for i in range(count - len(suffix))
        ]
        + suffix
    )
    output: list[dict[str, Any]] = []
    previous = closes[0]
    for index, end_price in enumerate(closes):
        for hour in range(4):
            opening = previous + (end_price - previous) * hour / 4
            closing = previous + (end_price - previous) * (hour + 1) / 4
            wick = 0.1 + 0.02 * (index % 3)
            high, low = max(opening, closing) + wick, min(opening, closing) - wick
            if flat:
                high, low = 120.1, 119.9
            if not flat and index == count - 1 and hour == 0:
                low = min(low, 129.6)
            start = TRIGGER - count * INTERVALS["4H"] + (index * 4 + hour) * INTERVALS["1H"]
            output.append(
                {
                    "open_time_ms": start,
                    "close_time_ms": start + INTERVALS["1H"] - 1,
                    "open": opening * scale,
                    "high": high * scale,
                    "low": low * scale,
                    "close": closing * scale,
                    "volume": 1000.0,
                    "quote_volume": 1000.0 * closing * scale,
                }
            )
        previous = end_price
    return output


def build_kline_rows(*, flat: bool = False) -> dict[tuple[str, str], list[list[Any]]]:
    data: dict[tuple[str, str], list[list[Any]]] = {}
    for symbol in SYMBOLS:
        hourly = build_hourly_series(symbol, flat or symbol != "BTCUSDT")
        for interval in ("1D", "4H", "1H"):
            width = INTERVALS[interval] // INTERVALS["1H"]
            rows: list[list[Any]] = []
            for index in range(0, len(hourly), width):
                group = hourly[index : index + width]
                rows.append(
                    [
                        group[0]["open_time_ms"],
                        str(group[0]["open"]),
                        str(max(c["high"] for c in group)),
                        str(min(c["low"] for c in group)),
                        str(group[-1]["close"]),
                        str(sum(c["volume"] for c in group)),
                        group[-1]["close_time_ms"],
                        str(sum(c["quote_volume"] for c in group)),
                        100,
                        "0",
                        "0",
                        "0",
                    ]
                )
            data[(symbol, interval)] = rows
    return data


def default_exchange_info() -> dict[str, Any]:
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
            for s in SYMBOLS
        ],
    }


class LoopbackMockVenue:
    """In-process loopback TLS HTTPS server speaking /fapi/v1/{time,exchangeInfo,klines}."""

    def __init__(
        self,
        cert_dir: Path,
        *,
        sni_host: str = "fapi.binance.com",
        minutes: int = 30,
        flat: bool = False,
        market_fault: str | None = None,
        series_fault: str | None = None,
        wire_fault: str | None = None,
        http_status: int = 200,
        extra_headers: dict[str, str] | None = None,
    ):
        self.ca_crt, self.leaf_crt, self.leaf_key = create_ephemeral_ca_and_leaf(cert_dir, sni_host=sni_host)
        self.minutes = minutes
        self.market_fault = market_fault
        self.series_fault = series_fault
        self.wire_fault = wire_fault
        self.http_status = http_status
        self.extra_headers = dict(extra_headers or {})
        self.calls: list[str] = []
        self.time_calls = 0
        self.data = build_kline_rows(flat=flat)

        series = self.data[("BTCUSDT", "4H")]
        if series_fault == "gap":
            series.pop(-5)
        elif series_fault == "incomplete":
            series[-1][6] += 1
        elif series_fault == "insufficient":
            self.data[("BTCUSDT", "4H")] = series[-20:]

        self.epoch_ns = time.monotonic_ns()
        self.ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.ssl_ctx.load_cert_chain(certfile=str(self.leaf_crt), keyfile=str(self.leaf_key))

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(64)
        self.sock.settimeout(0.2)
        self.port = int(self.sock.getsockname()[1])
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    @property
    def qa(self) -> dict[str, Any]:
        return {
            "host": "127.0.0.1",
            "port": self.port,
            "cafile": str(self.ca_crt),
            "connect_tunnel": getattr(self, "connect_tunnel", False),
        }

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        try:
            if self.qa.get("connect_tunnel"):
                buf = b""
                conn.settimeout(5)
                while b"\r\n\r\n" not in buf:
                    chunk = conn.recv(4096)
                    if not chunk:
                        return
                    buf += chunk
                    if len(buf) > 8192:
                        return
                first = buf.split(b"\r\n", 1)[0]
                if first not in (
                    b"CONNECT fapi.binance.com:443 HTTP/1.0",
                    b"CONNECT fapi.binance.com:443 HTTP/1.1",
                ):
                    return
                self.connect_calls = getattr(self, "connect_calls", 0) + 1
                if getattr(self, "connect_denied", False):
                    conn.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                    conn.close()
                    return
                conn.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            with self.ssl_ctx.wrap_socket(conn, server_side=True) as tls:
                tls.settimeout(5.0)
                buf = b""
                while b"\r\n\r\n" not in buf:
                    chunk = tls.recv(4096)
                    if not chunk:
                        return
                    buf += chunk
                first_line = buf.split(b"\r\n", 1)[0].decode("ascii", errors="replace")
                path = first_line.split(" ")[1]
                self.calls.append(path)
                if self.wire_fault == "hang":
                    self._stop.wait(3.0)
                    return
                body_bytes = self._render_body(path)
                content_type = "text/plain" if self.wire_fault == "non_json" else "application/json"
                headers_lines = [
                    f"HTTP/1.1 {self.http_status} QA",
                    f"Content-Type: {content_type}",
                    f"Content-Length: {len(body_bytes)}",
                    "Connection: close",
                ]
                for hk, hv in self.extra_headers.items():
                    headers_lines.append(f"{hk}: {hv}")
                resp = ("\r\n".join(headers_lines) + "\r\n\r\n").encode("ascii") + body_bytes
                if self.wire_fault == "slow_drip":
                    headers, body = resp.split(b"\r\n\r\n", 1)
                    tls.sendall(headers + b"\r\n\r\n")
                    for byte in body:
                        if self._stop.wait(0.04):
                            break
                        tls.sendall(bytes([byte]))
                else:
                    tls.sendall(resp)
        except OSError:
            pass

    def _render_body(self, path: str) -> bytes:
        if self.wire_fault == "duplicate_key":
            return b'{"serverTime": 1793925000000, "serverTime": 1793925000001}'
        if self.wire_fault == "nan_json":
            return b'{"serverTime": NaN}'
        if self.wire_fault == "trailing_json":
            return b'{"serverTime": 1793925000000} {"extra": 1}'
        if self.wire_fault == "oversize":
            return b" " * 2_097_200

        parsed = urlsplit(path)
        if parsed.path == "/fapi/v1/time":
            self.time_calls += 1
            elapsed_ms = (time.monotonic_ns() - self.epoch_ns) // 1_000_000
            server_ms = TRIGGER + self.minutes * 60_000 + elapsed_ms
            if self.wire_fault == "time_regression" and self.time_calls >= 2:
                server_ms -= 1000
            elif self.wire_fault == "time_wide_bracket" and self.time_calls >= 2:
                server_ms += 6000
            return json.dumps({"serverTime": server_ms}).encode("utf-8")

        if parsed.path == "/fapi/v1/exchangeInfo":
            info = default_exchange_info()
            if self.wire_fault == "bad_exchange_info":
                info["symbols"][0]["contractType"] = "DELIVERY"
            return json.dumps(info).encode("utf-8")

        if parsed.path == "/fapi/v1/klines":
            q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            symbol = q["symbol"]
            if q.get("limit") == "1":
                c = float(self.data[(symbol, "4H")][-1][4])
                if self.market_fault == "chase" and symbol == "BTCUSDT":
                    c += 1000.0
                row = [
                    TRIGGER,
                    str(c),
                    str(c + 0.01),
                    str(c - 0.01),
                    str(c),
                    "10",
                    TRIGGER + INTERVALS["4H"] - 1,
                    "1000",
                    1,
                    "0",
                    "0",
                    "0",
                ]
                if self.market_fault == "pivot" and symbol == "BTCUSDT":
                    row[3] = "0.01"
                elif self.market_fault == "target_hit" and symbol == "BTCUSDT":
                    row[2] = "16000.0"
                elif self.market_fault == "wrong_interval":
                    row[6] = TRIGGER + INTERVALS["1H"] - 1
                elif self.market_fault == "wrong_cycle":
                    row[0] -= INTERVALS["4H"]
                elif self.market_fault == "no_current":
                    return b"[]"
                return json.dumps([row]).encode("utf-8")
            interval = {"1d": "1D", "4h": "4H", "1h": "1H"}[q["interval"]]
            rows = [
                list(r)
                for r in self.data[(symbol, interval)]
                if int(q["startTime"]) <= r[0] <= int(q["endTime"])
            ][: int(q["limit"])]
            return json.dumps(rows).encode("utf-8")
        return b"{}"

    def close(self) -> None:
        self._stop.set()
        try:
            self.sock.close()
        except OSError:
            pass
        self._thread.join(timeout=2.0)
