"""One bound DNS lookup and one no-retry HTTP/TLS exchange per reserved request."""

import http.client
import re
import secrets
import socket
import ssl
import struct
import time
from contextlib import contextmanager

from quant_personal_public_b1.policy import SourceBlocked
from quant_personal_public_b1.wire import (
    BoundedRead,
    Reply,
    ResponseSocket,
    WireLimits,
    entity,
    remaining,
)
from quant_s2v2.protocol import GETS, Denied, require, sha

from ._inherited import DNS_LIMIT, dns_answers
from .policy import Egress

LIMITS = WireLimits(connect_ms=1000, idle_ms=700)
ATTEMPT_SECONDS = 2.5
_HEADER = "x-mbx-used-weight-1m"


def client_context(pem):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.hostname_checks_common_name = False
    context.options |= ssl.OP_NO_RENEGOTIATION | ssl.OP_NO_TICKET
    try:
        context.load_verify_locations(cadata=pem.decode("ascii"))
    except (ssl.SSLError, UnicodeError) as exc:
        raise Denied("CA_BUNDLE_INVALID") from exc
    return context


def _read_exact(stream, size, deadline):
    result = bytearray()
    while len(result) < size:
        stream.settimeout(min(LIMITS.idle_ms / 1000, remaining(deadline)))
        part = stream.recv(size - len(result))
        require(bool(part), "DNS_REPLY_TRUNCATED")
        result.extend(part)
    return bytes(result)


@contextmanager
def _dial(policy, dns, deadline, recheck):
    require(type(policy) is Egress, "REVIEWED_EGRESS_REQUIRED")
    recheck()
    policy.check_targets()
    address, port = (policy.resolver, policy.resolver_port) if dns else (policy.peer, policy.port)
    require(hasattr(socket, "SO_BINDTODEVICE"), "EGRESS_DEVICE_BIND_UNAVAILABLE")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP) as stream:
        stream.setsockopt(
            socket.SOL_SOCKET, socket.SO_BINDTODEVICE, policy.interface.encode("ascii") + b"\x00"
        )
        stream.bind((policy.source, 0))
        stream.settimeout(min(LIMITS.connect_ms / 1000, remaining(deadline)))
        stream.connect((address, port))
        require(
            stream.getpeername()[:2] == (address, port)
            and stream.getsockname()[0] == policy.source,
            "CONNECTED_PEER_OR_SOURCE_MISMATCH",
        )
        yield stream


def _one_resolution(policy, deadline, recheck):
    query_id = secrets.randbelow(65536)
    qname = b"".join(bytes((len(s),)) + s.encode("ascii") for s in policy.hostname.split("."))
    query = struct.pack("!6H", query_id, 0x0100, 1, 0, 0, 0) + qname + b"\x00\x00\x01\x00\x01"
    with _dial(policy, True, deadline, recheck) as stream:
        recheck()
        stream.settimeout(min(LIMITS.idle_ms / 1000, remaining(deadline)))
        stream.sendall(struct.pack("!H", len(query)) + query)
        size = struct.unpack("!H", _read_exact(stream, 2, deadline))[0]
        require(12 <= size <= DNS_LIMIT, "DNS_REPLY_SIZE_INVALID")
        answers = dns_answers(_read_exact(stream, size, deadline), query_id, policy.hostname)
    require(answers == (policy.peer,), "DNS_PEER_NOT_EXACTLY_APPROVED")


def _headers(response):
    headers = {}
    for name in (_HEADER, "content-type", "retry-after"):
        values = response.headers.get_all(name, [])
        if name == _HEADER and response.status == 200:
            require(
                len(values) == 1 and re.fullmatch(r"[0-9]{1,7}", values[0]),
                "WEIGHT_COUNTER_INVALID",
            )
        if len(values) == 1:
            headers[name] = values[0]
    return headers


class Wire:
    """No caller-controlled HTTP method, headers, SNI, authority, or retry path."""

    def __init__(self, policy, pem, recheck):
        require(type(policy) is Egress, "REVIEWED_EGRESS_REQUIRED")
        policy.check_targets()
        self.policy = policy
        self.context = client_context(pem)
        self.recheck = recheck
        self.expected = 0

    def exchange(self, request, window_seconds):
        index = self.expected
        require(index < len(GETS) and request == GETS[index], "REQUEST_OUTSIDE_S2_ORDER")
        # Mark the attempt before DNS or TLS, even when send/response remains ambiguous.
        self.expected += 1
        policy = self.policy
        deadline = time.monotonic() + min(ATTEMPT_SECONDS, window_seconds)
        try:
            if index == 0:
                _one_resolution(policy, deadline, self.recheck)
            with _dial(policy, False, deadline, self.recheck) as stream:
                stream.settimeout(min(LIMITS.connect_ms / 1000, remaining(deadline)))
                with self.context.wrap_socket(stream, server_hostname=policy.hostname) as tls:
                    fingerprint = tls.getpeercert(binary_form=True)
                    require(
                        fingerprint and tls.version() in {"TLSv1.2", "TLSv1.3"},
                        "TLS_PROOF_MISSING",
                    )
                    proof = {
                        "evidence": policy.evidence,
                        "hostname": policy.hostname,
                        "sni": policy.hostname,
                        "cert_sha256": sha(fingerprint),
                        "protocol": tls.version(),
                    }
                    self.recheck()
                    tls.settimeout(min(LIMITS.idle_ms / 1000, remaining(deadline)))
                    wire_request = (
                        f"GET {GETS[index]['path']} HTTP/1.1\r\n"
                        f"Host: {policy.hostname}\r\n"
                        "Accept: application/json\r\nAccept-Encoding: gzip\r\nConnection: close\r\n\r\n"
                    )
                    tls.sendall(wire_request.encode("ascii"))
                    raw = BoundedRead(tls, deadline, LIMITS)
                    response = http.client.HTTPResponse(ResponseSocket(raw), method="GET")
                    try:
                        response.begin()
                        headers = _headers(response)
                        if response.status != 200:
                            return Reply(response.status, headers, b"", raw.seen, tls=proof)
                        require(
                            response.chunked or response.length is not None, "HTTP_FRAMING_REQUIRED"
                        )
                        body, encoded = entity(response, LIMITS.max_decoded_bytes, deadline)
                        return Reply(200, headers, body, raw.seen, encoded_body=encoded, tls=proof)
                    finally:
                        response.close()
        except ssl.SSLError as exc:
            raise Denied("TLS_VERIFICATION_OR_HANDSHAKE_FAILED") from exc
        except TimeoutError as exc:
            raise Denied("TRANSPORT_DEADLINE") from exc
        except SourceBlocked as exc:
            raise Denied(exc.code) from exc
        except (OSError, http.client.HTTPException) as exc:
            raise Denied("WIRE_AMBIGUOUS_OR_INCOMPLETE") from exc
