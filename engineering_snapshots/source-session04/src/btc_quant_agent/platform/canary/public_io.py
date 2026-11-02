"""Finite, exact-URL public transport. Backend construction and preflight are socket-free."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from html.parser import HTMLParser
import html
import json
import os
from queue import Queue, Empty, Full
import socket
import threading
import time
from typing import Any
from urllib.parse import urlsplit
from .clock_domain import capture
from .telemetry import NULL, TimedQueue

from .public_policy import (
    DOC_HOST,
    DOC_PATHS,
    PublicStop,
    SYMBOLS,
    Window,
    REST,
    persisted_source_denial,
    persist_source_denial,
)


def tls_failure(exc):
    import ssl

    for _ in range(8):
        if isinstance(exc, ssl.SSLError):
            return True
        exc = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
        if exc is None:
            break
    return False


def strict_json(text):
    def invalid(value):
        raise ValueError("NONFINITE_JSON_CONSTANT:" + value)

    return json.loads(text, parse_constant=invalid)


@dataclass(frozen=True)
class Wire:
    endpoint_id: str
    symbol: str
    params: dict
    payload_text: str | None
    request_wall: int | None
    request_mono: int | None
    receive_wall: int
    receive_mono: int
    available_wall: int
    available_mono: int
    first_wall: int | None = None
    first_mono: int | None = None
    status: int = 200
    error: str | None = None
    stream: str | None = None
    epoch: int = 0
    exposure: str = "PUBLIC_CANARY"
    rate_headers: dict | None = None
    clock_samples: dict | None = None

    @property
    def payload(self):
        return strict_json(self.payload_text) if self.payload_text is not None else None

    def record(self):
        value = asdict(self)
        if self.clock_samples is None:
            value.pop("clock_samples")  # Preserve V1 raw identities/replay byte contracts.
        return value


class DocText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

    def value(self):
        return " ".join(html.unescape(" ".join(self.parts)).split())


class HttpWsBackend:
    """No keys/auth/cookies/redirects; only explicit, byte-preserving tunnel egress."""

    exposure = "PUBLIC_CANARY"

    def __init__(self):
        self.http = None
        self.guard = lambda: (_ for _ in ()).throw(PublicStop("PUBLIC_NETWORK_DEFAULT_DISABLED"))
        self.direct = None
        self.scope = None
        self.clock = None
        self.tls_context = None
        self.tls_evidence = []
        self.route_info = {"egress_mode": "DIRECT", "target_tls": "STRICT_VERIFICATION_REQUIRED"}

    def bind_scope(self, scope, clock):
        self.scope, self.clock = scope, clock
        scope.validate_route(self.route_info)

    def set_guard(self, guard):
        from .public_network import DirectSockets

        self.guard = guard
        # Explicit opt-in; ambient host-wide proxies never silently alter public routing.
        opt_in = os.environ.get("L4_CONTROLLED_EGRESS") == "1"
        proxy_url = None
        if opt_in:
            proxy_url = (
                os.environ.get("L4_EGRESS_PROXY_URL")
                or os.environ.get("HTTPS_PROXY")
                or os.environ.get("ALL_PROXY")
            )
            if not proxy_url:
                raise PublicStop("EXPLICIT_EGRESS_PROXY_NOT_CONFIGURED")
        self.direct = DirectSockets(guard, proxy_url=proxy_url)
        self.route_info = self.direct.route_info

    def abort(self):
        if self.direct is not None:
            self.direct.abort()

    def _tls(self):
        import httpx
        import ssl

        if self.tls_context is None:
            self.tls_context = httpx.create_ssl_context(verify=True, trust_env=False)
        if not self.tls_context.check_hostname or self.tls_context.verify_mode != ssl.CERT_REQUIRED:
            raise PublicStop("TLS_VERIFICATION_REQUIRED")
        return self.tls_context

    def _record_tls(self, ssl_object, host):
        if ssl_object is None:
            return
        import hashlib

        peer = ssl_object.getpeercert(True)
        if not peer:
            raise PublicStop("TLS_PEER_CERTIFICATE_MISSING")
        row = {
            "target_hostname": host,
            "certificate_sha256": hashlib.sha256(peer).hexdigest(),
            "chain_verification": "CERT_REQUIRED",
            "hostname_verification": True,
            "tls_version": ssl_object.version(),
            "egress_mode": self.route_info["egress_mode"],
        }
        if row not in self.tls_evidence:
            self.tls_evidence.append(row)
            del self.tls_evidence[:-16]

    def _http(self):
        if self.http is None:
            import httpx

            import httpcore

            if self.direct is None:
                raise PublicStop("PUBLIC_NETWORK_DEFAULT_DISABLED")
            context = self._tls()
            transport = httpx.HTTPTransport(verify=context, trust_env=False, retries=0)
            transport._pool.close()
            transport._pool = httpcore.ConnectionPool(
                ssl_context=context,
                network_backend=self.direct,
                max_connections=4,
                max_keepalive_connections=2,
            )
            self.http = httpx.Client(
                transport=transport,
                trust_env=False,
                follow_redirects=False,
                headers={"Accept": "application/json", "User-Agent": "Quant-L4-readonly/1"},
            )
        return self.http

    def get(self, url, params, timeout, clock, limit=4 * 1024**2):
        parsed = urlsplit(url)
        if self.scope is not None and hasattr(self.scope, "allowed_hostnames"):
            if parsed.hostname not in self.scope.allowed_hostnames:
                raise PublicStop("BACKEND_HOST_FORBIDDEN")
        if (
            parsed.scheme != "https"
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.port not in (None, 443)
        ):
            raise PublicStop("BACKEND_URL_FORBIDDEN")
        if parsed.hostname == DOC_HOST and parsed.path in DOC_PATHS:
            if params:
                raise PublicStop("DOCUMENT_PARAMETERS_FORBIDDEN")
        elif (
            parsed.hostname == "fapi.binance.com" and parsed.path in REST.values() and self.scope is not None
        ):
            id = next(k for k, v in REST.items() if v == parsed.path)
            self.scope.validate_request(id, params, clock.wall())
        else:
            raise PublicStop("BACKEND_ENDPOINT_FORBIDDEN")
        self.guard()
        # Both facade and backend enforce exact public URLs; HTTP redirects stay disabled.
        first = None
        data = bytearray()
        self._http().cookies.clear()
        with self._http().stream("GET", url, params=params, timeout=timeout) as response:
            stream = response.extensions.get("network_stream")
            if stream is not None:
                self._record_tls(stream.get_extra_info("ssl_object"), parsed.hostname)
            for block in response.iter_bytes():
                if first is None:
                    first = capture(clock) if hasattr(clock, "sample") else clock.pair()
                data.extend(block)
                if len(data) > limit:
                    raise PublicStop("RESPONSE_SIZE_CAP_EXCEEDED")
            status = response.status_code
            self.last_headers = {
                k.lower(): v
                for k, v in response.headers.items()
                if "weight" in k.lower() or k.lower() == "retry-after"
            }
        return status, bytes(data).decode("utf-8", errors="strict"), first

    def connect(self, url, timeout, on_control):
        if self.scope is None or (
            url != self.scope.ws_url("public") and url != self.scope.ws_url("market")
        ):
            raise PublicStop("BACKEND_WEBSOCKET_SCOPE_FORBIDDEN")
        self.guard()
        from websockets.sync.client import connect, ClientConnection

        outer_guard = self.guard
        if self.direct is None:
            raise PublicStop("PUBLIC_NETWORK_DEFAULT_DISABLED")
        register = self.direct.register

        class ObservedConnection(ClientConnection):
            def __init__(self, sock, protocol, **kwargs):
                register(sock)
                request = protocol.send_request

                def checked_request(value):
                    # Connection/TLS may have consumed the remainder of the window.
                    outer_guard()
                    request(value)

                protocol.send_request = checked_request
                send = protocol.send_frame

                def observed(frame):
                    if int(frame.opcode) in (8, 9, 10):
                        on_control(int(frame.opcode))
                    send(frame)

                protocol.send_frame = observed
                super().__init__(sock, protocol, **kwargs)

        if self.direct is None:
            raise PublicStop("PUBLIC_NETWORK_DEFAULT_DISABLED")
        stream = self.direct.connect_tcp("fstream.binance.com", 443, timeout=timeout)
        self.guard()
        connection = connect(
            url,
            sock=stream._sock,
            ssl=self._tls(),
            server_hostname="fstream.binance.com",
            proxy=None,
            open_timeout=timeout,
            close_timeout=0.5,
            ping_interval=None,
            max_size=65536,
            max_queue=16,
            compression=None,
            create_connection=ObservedConnection,
        )
        self._record_tls(connection.socket, "fstream.binance.com")
        return connection

    def close(self):
        if self.http is not None:
            self.http.close()


class PublicTransport:
    def __init__(self, scope, clock, guard, *, enabled=False, backend=None, telemetry=None):
        self.scope, self.clock, self.guard = scope, clock, guard
        self.telemetry = telemetry or getattr(guard, "telemetry", NULL)
        self.window = scope.make_window(clock) if hasattr(scope, "make_window") else Window(clock)
        self.enabled = enabled
        self.backend = backend if backend is not None else HttpWsBackend()
        if hasattr(self.backend, "set_guard"):
            self.backend.set_guard(self.active)
        if hasattr(self.backend, "bind_scope"):
            self.backend.bind_scope(scope, clock)
        self.queue: Queue[Wire] = TimedQueue(self.telemetry, maxsize=128)
        self.connections = {}
        self.threads = []
        self.watchdog = None
        self.stop_event = threading.Event()
        self.stop_check = lambda: False
        self.error = None
        self.lock = threading.RLock()
        self.epochs = {"public": 0, "market": 0}
        self.metrics: dict[str, Any] = {
            "rest_requests": 0,
            "rest_weight": 0,
            "ws_connections": 0,
            "ws_frames": 0,
            "ws_controls": 0,
            "reconnects": 0,
            "docs_requests": 0,
            "egress_route": getattr(self.backend, "route_info", {"egress_mode": "DIRECT"}),
            "tls_verification": getattr(self.backend, "tls_evidence", []),
        }

    @property
    def exposure(self):
        return self.backend.exposure

    def active(self):
        if not self.enabled:
            raise PublicStop("PUBLIC_NETWORK_DEFAULT_DISABLED")
        denial = persisted_source_denial() if self.exposure == "PUBLIC_CANARY" else None
        if denial:
            raise PublicStop(denial)
        if self.stop_check():
            raise PublicStop("EMERGENCY_STOP")
        if self.error or self.stop_event.is_set():
            raise PublicStop(self.error or "TRANSPORT_CLOSED")
        try:
            remaining = self.window.check()
        except PublicStop as exc:
            self.telemetry.stop("transport.clock_admission", str(exc), self.queue.qsize())
            raise
        if hasattr(self.scope, "require_authority"):
            self.scope.require_authority(self.clock.wall(), native=self.exposure == "PUBLIC_CANARY")
        if hasattr(self.scope, "require_execution_reservation"):
            self.scope.require_execution_reservation()
        if (
            self.exposure == "PUBLIC_CANARY"
            and self.scope.raw.get("activation_status") == "OFFLINE_ONLY_PENDING_SECOND_SESSION_AUTH"
        ):
            raise PublicStop("SECOND_NATIVE_SESSION_REQUIRES_DISTINCT_OWNER_AUTHORIZATION")
        if self.exposure == "PUBLIC_CANARY":
            route = self.metrics["egress_route"]
            if route.get("egress_mode") != "CONTROLLED_EGRESS_PROXY" or route.get("tunnel_type") != "HTTP_CONNECT":
                self.telemetry.stop("transport.egress", "APPROVED_HTTP_CONNECT_EGRESS_REQUIRED", self.queue.qsize())
                raise PublicStop("APPROVED_HTTP_CONNECT_EGRESS_REQUIRED")
        return remaining

    def verify_documents(self):
        """Verify the approved local semantic baseline; never fetch a human website at startup."""
        self.active()
        result = self.scope.verify_document_baseline()
        result["checked_wall_ms"] = self.clock.wall()
        self.metrics["document_validation"] = result
        return [result]

    def _remember_denial(self, endpoint_id, status, received_wall):
        if self.exposure == "PUBLIC_CANARY":
            persist_source_denial(
                {
                    "provider": "binance",
                    "market": "USD_M",
                    "exposure": self.exposure,
                    "endpoint_id": endpoint_id,
                    "http_status": status,
                    "received_wall_ms": received_wall,
                    "reason": "VENUE_ACCESS_DENIED",
                    "scope_hash": self.scope.hash,
                    "egress_route": self.metrics["egress_route"],
                }
            )

    def probe_document_website(self):
        """Explicit legacy diagnostic only; not a startup gate, fallback or WAF bypass."""
        self.active()
        results = []
        for row in self.scope.document["runtime_document_checks"]:
            self.active()
            if row["path"] not in DOC_PATHS:
                raise PublicStop("DOCUMENT_HOST_SCOPE_VIOLATION")
            self.metrics["docs_requests"] += 1
            status, body, _ = self.backend.get(
                "https://" + DOC_HOST + row["path"], {}, min(8, self.active()), self.clock, 8 * 1024**2
            )
            if status != 200:
                raise PublicStop("OFFICIAL_DOCUMENTATION_UNAVAILABLE")
            p = DocText()
            p.feed(body)
            text = p.value()
            if any(token.casefold() not in text.casefold() for token in row["required_tokens"]):
                raise PublicStop("OFFICIAL_DOCUMENTATION_CONTRACT_CHANGED")
            import hashlib

            results.append(
                {
                    "url": "https://" + DOC_HOST + row["path"],
                    "sha256": hashlib.sha256(body.encode()).hexdigest(),
                    "checked_wall_ms": self.clock.wall(),
                    "fact_checks": "PASSED",
                    "observed_feed_quality": False,
                }
            )
        return results

    def request(self, id, params, *, retry=False):
        remaining = self.active()
        url = self.scope.validate_request(id, params, self.clock.wall())
        endpoint = self.scope.endpoint(id)
        with self.lock:
            charge = self.guard.request(endpoint, params, self.clock.mono(), retry=retry)
            self.metrics["rest_requests"] += 1
            self.metrics["rest_weight"] += charge["weight"]
        start = capture(self.clock)
        first = None
        status = 0
        body = None
        error = None
        try:
            status, body, first = self.backend.get(url, params, min(5, remaining), self.clock)
        except PublicStop:
            raise
        except Exception as exc:
            error = (
                "TLS_VERIFICATION_FAILED" if tls_failure(exc)
                else "NETWORK_TIMEOUT" if "timeout" in type(exc).__name__.lower() else "NETWORK_FAILURE"
            )
            if error == "TLS_VERIFICATION_FAILED":
                self.error = error
        received = capture(self.clock)
        try:
            if body is not None:
                strict_json(body)
        except (ValueError, TypeError):
            error = "INVALID_JSON_SCHEMA"
        available = capture(self.clock)
        wire = Wire(
            id,
            params.get("symbol", "*"),
            dict(params),
            body,
            request_wall=start[0],
            request_mono=start[1],
            receive_wall=received[0],
            receive_mono=received[1],
            available_wall=available[0],
            available_mono=available[1],
            first_wall=first[0] if first else None,
            first_mono=first[1] if first else None,
            status=status,
            error=error,
            exposure=self.exposure,
            rate_headers=getattr(self.backend, "last_headers", None),
            clock_samples={
                "request": start[2],
                "receive": received[2],
                "available": available[2],
                "first": first[2] if first and len(first) > 2 else None,
            }
            if received[2] is not None
            else None,
        )
        if status:
            self.metrics.setdefault("rest_responses", 0)
            self.metrics["rest_responses"] += 1
        if wire.rate_headers:
            used = wire.rate_headers.get("x-mbx-used-weight-1m")
            if used is not None:
                try:
                    used_value = int(used)
                    self.metrics["last_observed_venue_ip_weight_1m"] = used_value
                    if used_value >= self.guard.policy.ip_weight_per_minute:
                        self.error = "VENUE_IP_WEIGHT_CAP_REACHED"
                except ValueError:
                    self.error = "VENUE_WEIGHT_HEADER_SCHEMA_CHANGED"
        if status in (403, 451):
            self.error = "VENUE_ACCESS_DENIED"
        elif 300 <= status < 400:
            self.error = "UNAPPROVED_REDIRECT"
        elif body and any(
            s in body.lower()
            for s in ("restricted location", "restricted jurisdiction", "not available in your country")
        ):
            self.error = "VENUE_ACCESS_DENIED"
        elif status in (429, 418):
            try:
                self.guard.response(status, self.clock.mono())
            except ValueError:
                self.error = "RATE_LIMIT_CIRCUIT_OPEN"
        elif error or status >= 500:
            try:
                self.guard.response(408 if error else status, self.clock.mono())
            except ValueError:
                self.error = "RETRY_EXHAUSTED"
        if self.error == "VENUE_ACCESS_DENIED":
            self._remember_denial(id, status, wire.receive_wall)
        return wire

    def open_group(self, group, *, reconnect=False):
        self.active()
        url = self.scope.ws_url(group)
        streams = self.scope.streams(group)
        with self.lock:
            self.guard.connection_open(
                group,
                self.scope.endpoint("binance_usdm_bbo_ws" if group == "public" else "binance_usdm_klines_ws"),
                self.clock.mono(),
            )
            self.guard.subscription_set(
                group,
                self.scope.endpoint("binance_usdm_bbo_ws" if group == "public" else "binance_usdm_klines_ws"),
                streams,
                self.clock.mono(),
            )
            self.metrics.setdefault("ws_connect_attempts", 0)
            self.metrics["ws_connect_attempts"] += 1
            if reconnect:
                self.epochs[group] += 1
                self.metrics["reconnects"] += 1

        def control(opcode):
            if opcode != 8:
                self.active()
                with self.lock:
                    self.guard.websocket_control(
                        self.scope.endpoint("binance_usdm_bbo_ws"), self.clock.mono()
                    )
            self.metrics["ws_controls"] += 1

        connect_wall, connect_mono = self.clock.pair()
        try:
            conn = self.backend.connect(url, min(5, self.active()), control)
        except Exception as exc:
            self.guard.connection_close(group)
            response = getattr(exc, "response", None)
            status = getattr(response, "status_code", 0)
            self.error = (
                "VENUE_ACCESS_DENIED"
                if status in (403, 451)
                else "RATE_LIMIT_CIRCUIT_OPEN"
                if status in (418, 429)
                else "UNAPPROVED_REDIRECT"
                if 300 <= status < 400
                else "TLS_VERIFICATION_FAILED"
                if tls_failure(exc)
                else "WS_CONNECT_FAILURE"
            )
            if self.error == "VENUE_ACCESS_DENIED":
                self._remember_denial(
                    "binance_usdm_bbo_ws" if group == "public" else "binance_usdm_klines_ws",
                    status,
                    self.clock.wall(),
                )
            if status in (418, 429):
                try:
                    self.guard.response(status, self.clock.mono())
                except ValueError:
                    pass
            event = Wire(
                "binance_usdm_bbo_ws" if group == "public" else "binance_usdm_klines_ws",
                "*",
                {},
                json.dumps({"handshake_status": status, "reason": self.error}),
                connect_wall,
                connect_mono,
                self.clock.wall(),
                self.clock.mono(),
                self.clock.wall(),
                self.clock.mono(),
                status=status,
                error=self.error,
                exposure=self.exposure,
            )
            self.queue.put_nowait(event)
            raise PublicStop(self.error) from exc
        self.metrics.setdefault("connection_clock_observations", []).append(
            {
                "group": group,
                "epoch": self.epochs[group],
                "request_wall_ms": connect_wall,
                "request_mono_ms": connect_mono,
                "upgrade_returned_wall_ms": self.clock.wall(),
                "upgrade_returned_mono_ms": self.clock.mono(),
                "first_byte_ms": None,
            }
        )
        self.metrics["ws_connections"] += 1
        self.connections[group] = conn

        def receive():
            try:
                while not self.stop_event.is_set():
                    remaining = self.active()
                    try:
                        with self.telemetry.measure("ws.recv_call"):
                            message = conn.recv(timeout=min(0.25, remaining))
                    except TimeoutError:
                        continue
                    received_perf = time.perf_counter_ns()
                    with self.telemetry.measure("ws.capture"):
                        received = capture(self.clock)
                    self.metrics.setdefault("ws_raw_messages", 0)
                    self.metrics["ws_raw_messages"] += 1
                    if not isinstance(message, str):
                        raise PublicStop("BINARY_FRAME_UNSUPPORTED")
                    parse_started = time.perf_counter_ns()
                    try:
                        payload = strict_json(message)
                        stream = payload.get("stream")
                        if stream not in streams:
                            raise PublicStop("UNAPPROVED_STREAM_FRAME")
                        value = payload.get("data")
                        symbol = stream.split("@")[0].upper()
                        if symbol not in SYMBOLS or not isinstance(value, dict) or value.get("s") != symbol:
                            raise PublicStop("WRONG_SYMBOL_STREAM_BINDING")
                    finally:
                        self.telemetry.observe("ws.parse_validate", time.perf_counter_ns() - parse_started)
                    available = capture(self.clock)
                    lock_started = time.perf_counter_ns()
                    with self.lock:
                        self.telemetry.observe("ws.guard_lock_wait", time.perf_counter_ns() - lock_started)
                        with self.telemetry.measure("ws.guard"):
                            self.guard.data_message(self.clock.mono(), self.queue.qsize())
                        self.metrics["ws_frames"] += 1
                    id = "binance_usdm_bbo_ws" if group == "public" else "binance_usdm_klines_ws"
                    # WS first byte and per-message request clocks are not exposed by this library.
                    # Per-message request and first-byte clocks remain UNKNOWN, not manufactured.
                    wire = Wire(
                        id,
                        symbol,
                        {},
                        message,
                        request_wall=None,
                        request_mono=None,
                        receive_wall=received[0],
                        receive_mono=received[1],
                        available_wall=available[0],
                        available_mono=available[1],
                        stream=stream,
                        epoch=self.epochs[group],
                        exposure=self.exposure,
                        clock_samples={"receive": received[2], "available": available[2]}
                        if received[2] is not None
                        else None,
                    )
                    try:
                        if isinstance(self.queue, TimedQueue):
                            self.queue.put_wire(wire, received_perf)
                        else:
                            self.queue.put_nowait(wire)
                        self.metrics["ws_data_enqueued"] = self.metrics.get("ws_data_enqueued", 0) + 1
                    except Full:
                        raise PublicStop("BACKPRESSURE_BLOCKED") from None
            except Exception as exc:
                if not self.stop_event.is_set():
                    reason = str(exc) if isinstance(exc, (PublicStop, ValueError)) else "WS_DISCONNECT"
                    fault_receive = capture(self.clock)
                    fault_available = capture(self.clock)
                    try:
                        self.queue.put_nowait(
                            Wire(
                                "source_failure",
                                group,
                                {},
                                None,
                                request_wall=None,
                                request_mono=None,
                                receive_wall=fault_receive[0],
                                receive_mono=fault_receive[1],
                                available_wall=fault_available[0],
                                available_mono=fault_available[1],
                                error=reason,
                                exposure=self.exposure,
                                clock_samples={"receive": fault_receive[2], "available": fault_available[2]}
                                if fault_receive[2] is not None
                                else None,
                            )
                        )
                    except Full:
                        self.error = "BACKPRESSURE_BLOCKED"
            finally:
                self.guard.connection_close(group)

        thread = threading.Thread(target=receive, name="l4-" + group, daemon=False)
        self.threads.append(thread)
        thread.start()

    def start_watchdog(self):
        self.active()

        def watch():
            while not self.stop_event.wait(0.05):
                try:
                    self.active()
                except PublicStop as exc:
                    if not self.stop_event.is_set():
                        self.error = str(exc)
                        if hasattr(self.backend, "abort"):
                            self.backend.abort()
                        for c in tuple(self.connections.values()):
                            try:
                                c.socket.shutdown(socket.SHUT_RDWR)
                            except (AttributeError, OSError):
                                pass
                    return

        self.watchdog = threading.Thread(target=watch, name="l4-deadline", daemon=False)
        self.watchdog.start()

    def next(self, timeout=0.2):
        try:
            with self.telemetry.measure("queue.dequeue_call"):
                return self.queue.get(timeout=timeout)
        except Empty:
            return None

    def queue_timing(self, item):
        return self.queue.take_timing(item) if isinstance(self.queue, TimedQueue) else None

    def close_group(self, group):
        c = self.connections.pop(group, None)
        if c is not None:
            # Terminate our own connection immediately; never keep reading beyond the grant.
            try:
                c.socket.shutdown(socket.SHUT_RDWR)
            except (AttributeError, OSError):
                pass
            try:
                c.close()
            except Exception:
                pass
        self.guard.connection_close(group)

    def close(self):
        self.stop_event.set()
        errors = []
        if hasattr(self.backend, "abort"):
            try:
                self.backend.abort()
            except Exception as exc:
                errors.append(str(exc))
        for group in tuple(self.connections):
            try:
                self.close_group(group)
            except Exception as exc:
                errors.append(str(exc))
        for t in self.threads:
            t.join(timeout=2)
            if t.is_alive():
                errors.append("FINITE_RECEIVER_DID_NOT_STOP")
        if self.watchdog is not None:
            self.watchdog.join(timeout=2)
            if self.watchdog.is_alive():
                errors.append("FINITE_WATCHDOG_DID_NOT_STOP")
        try:
            self.backend.close()
        except Exception as exc:
            errors.append(str(exc))
        if errors:
            raise PublicStop("|".join(errors))
