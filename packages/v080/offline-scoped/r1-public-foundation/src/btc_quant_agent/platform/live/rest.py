"""Three allowlisted GETs using standard HTTPS and a finite per-request worker."""

from __future__ import annotations

import base64
import hashlib
import http.client
import ipaddress
import json
import ssl
import subprocess
import sys
from urllib.parse import urlencode

from .models import Access, POLICY, Blocked, ensure, sample


def wire_request(spec):
    route, params = spec["route"], spec["params"]
    ensure(route in POLICY["routes"], "LIVE_ROUTE_NOT_ALLOWLISTED")
    ensure(
        (route.endswith("klines") and set(params) == {"symbol", "interval", "startTime", "endTime", "limit"})
        or (not route.endswith("klines") and not params),
        "LIVE_QUERY_NOT_ALLOWLISTED",
    )
    if route.endswith("klines"):
        interval = {"1d": "1D", "4h": "4H", "1h": "1H"}.get(params["interval"])
        ensure(
            interval is not None
            and params["symbol"] in POLICY["symbols"]
            and 0 < params["limit"] <= POLICY["bars"][interval],
            "LIVE_SCOPE_NOT_ALLOWLISTED",
        )
    qa = spec.get("qa")
    if qa:
        ensure(ipaddress.ip_address(qa["host"]).is_loopback and qa["cafile"], "LIVE_QA_LOOPBACK_ONLY")
        # Isolated fabricated CA only. No production roots or direct fallback.
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(qa["cafile"])
        proxy = {"host": qa["host"], "port": qa["port"]}
    else:
        access, exclusions = Access.load(spec["access_file"])
        if route.endswith("klines"):
            ensure(
                not any(
                    params["startTime"] < hi and params["endTime"] + 1 > lo
                    for lo, hi in exclusions["excluded_UTC_ms_ranges"]
                ),
                "LIVE_HOLDOUT_DATE_OVERLAP_FORBIDDEN",
            )
        proxy = access.proxy
        context = ssl.create_default_context()
    ensure(
        context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED, "LIVE_TLS_VERIFICATION_REQUIRED"
    )
    host = POLICY["host"]
    conn = http.client.HTTPSConnection(
        proxy["host"] if proxy else host,
        proxy["port"] if proxy else 443,
        timeout=spec["timeout"],
        context=context,
    )
    if proxy:
        conn.set_tunnel(host, 443)

    def capture_sample():
        value = sample()
        if qa:
            # Explicit isolated simulation only; PUBLIC captures actual wall time.
            value["wall_ms"] = value["mono_before_ms"] + 1000000000000
        return value

    before = capture_sample()
    try:
        conn.connect()
        sock = conn.sock
        ensure(sock is not None, "LIVE_TLS_SOCKET_MISSING")
        certificate = sock.getpeercert(binary_form=True)
        ensure(certificate is not None, "LIVE_TLS_CERTIFICATE_MISSING")
        assert certificate is not None
        tls = {
            "host": host,
            "sni": host,
            "hostname_verified": True,
            "chain": "CERT_REQUIRED",
            "version": sock.version(),
            "certificate_sha256": hashlib.sha256(certificate).hexdigest(),
            "transport_class": "FABRICATED_LOOPBACK_TLS_QA" if qa else "PUBLIC_HTTPS_UNSIGNED_DATA",
        }
        query = route + ("?" + urlencode(params) if params else "")
        conn.request(
            "GET", query, headers={"Accept": "application/json", "User-Agent": "Quant-J-manual-readonly/1"}
        )
        response = conn.getresponse()
        raw = response.read(POLICY["response_bytes_max"] + 1)
        after = capture_sample()
        complete = len(raw) <= POLICY["response_bytes_max"]
        raw = raw[: POLICY["response_bytes_max"]]
        return {
            "url": "https://" + host + query,
            "route": route,
            "params": params,
            "status": response.status,
            "response_complete": complete,
            "wall_clock_class": "FABRICATED_QA_MONOTONIC_OFFSET" if qa else "ACTUAL_LOCAL_WALL",
            "tls": tls,
            "request_sample": before,
            "receive_sample": after,
            "body_sha256": hashlib.sha256(raw).hexdigest(),
            "headers": {
                k.lower(): v
                for k, v in response.getheaders()
                if k.lower() in ("date", "content-type", "retry-after", "x-mbx-used-weight-1m")
            },
            "body_base64": base64.b64encode(raw).decode(),
        }
    finally:
        conn.close()


class Transport:
    def __init__(self, access_file, qa=None):
        self.access_file = str(access_file) if access_file else None
        self.qa = qa

    def request(self, route, params, timeout):
        spec = {
            "access_file": self.access_file,
            "qa": self.qa,
            "route": route,
            "params": params,
            "timeout": timeout,
        }
        try:
            result = subprocess.run(
                [sys.executable, "-B", "-m", __name__],
                input=json.dumps(spec),
                capture_output=True,
                text=True,
                timeout=timeout + 0.2,
            )
        except subprocess.TimeoutExpired as e:
            # subprocess.run kills and waits: no DNS/socket receiver is abandoned.
            raise Blocked("LIVE_REQUEST_DEADLINE_NO_RETRY") from e
        ensure(result.returncode == 0, "LIVE_TLS_PROXY_OR_NETWORK_FAILURE_NO_RETRY:" + result.stderr[-200:])
        return json.loads(result.stdout)


if __name__ == "__main__":
    try:
        print(json.dumps(wire_request(json.load(sys.stdin)), sort_keys=True))
    except Exception as error:
        print(type(error).__name__ + ":" + str(error), file=sys.stderr)
        raise SystemExit(2)
