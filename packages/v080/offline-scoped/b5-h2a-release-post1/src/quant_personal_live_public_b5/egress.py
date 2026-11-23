"""Bound IPv4 direct egress and strict official-authority HTTP/TLS exchange."""

from __future__ import annotations

import http.client
import ipaddress
import secrets
import socket
import ssl
import struct
import time
from dataclasses import dataclass
from pathlib import Path

from quant_personal_public_b1.policy import SourceBlocked, require
from quant_personal_public_b1.store import sha
from quant_personal_public_b1.wire import (
    BoundedRead, Reply, ResponseSocket, WireFailure, WireLimits, audit_headers, entity, remaining,
)

from quant_personal_public_bridge_b4.session import POLICY

from .contract import HOST, PORT, PRODUCTION_CA, RouteRequest, bounded_int
from .trust import production_roots

DNS_LIMIT = 4096
WIRE = WireLimits()
QNAME = b"".join(bytes((len(label),)) + label.encode("ascii") for label in HOST.split(".")) + b"\x00"
QUESTION = QNAME + struct.pack("!HH", 1, 1)


def route_fingerprint(proc_ipv4_routes: str) -> str:
    """Fingerprint the stable fields of Linux's visible IPv4 main routing table."""
    lines = proc_ipv4_routes.splitlines()
    require(bool(lines) and lines[0].split()[:4] == ["Iface","Destination","Gateway","Flags"],
            "EGRESS_ROUTE_TABLE_INVALID")
    stable = []
    for line in lines[1:]:
        columns = line.split()
        require(len(columns) == 11, "EGRESS_ROUTE_TABLE_INVALID")
        stable.append(" ".join(columns[:4] + columns[6:]))
    require(bool(stable), "EGRESS_ROUTE_TABLE_EMPTY")
    return sha(("\n".join(sorted(stable))+"\n").encode("ascii"))


def check_local_route(route):
    try:
        inode = Path("/proc/self/ns/net").stat().st_ino
        names = {name for _, name in socket.if_nameindex()}
    except OSError as exc:
        raise SourceBlocked("EGRESS_ROUTE_UNAVAILABLE") from exc
    require(inode == route.netns_inode and route.interface in names, "EGRESS_ROUTE_MISMATCH")
    require(hasattr(socket, "SO_BINDTODEVICE"), "EGRESS_DEVICE_BIND_UNAVAILABLE")
    try:
        seen = route_fingerprint(Path("/proc/net/route").read_text(encoding="ascii"))
    except OSError as exc:
        raise SourceBlocked("EGRESS_ROUTE_UNAVAILABLE") from exc
    require(seen == route.route_table_sha256, "EGRESS_ROUTE_TABLE_CHANGED")


def _bound_socket(route):
    conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
    try:
        # Apply to BOTH the DNS and HTTPS sockets. A host-local routing change
        # that makes the requested interface unusable is a stop.
        conn.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, route.interface.encode("ascii") + b"\x00")
        conn.bind((route.source_address, 0))
    except OSError as exc:
        conn.close()
        raise SourceBlocked("EGRESS_DEVICE_BIND_FAILED") from exc
    return conn


def _peer_matches(conn, expected, port, source):
    require(conn.getpeername()[:2] == (expected, port) and conn.getsockname()[0] == source,
            "CONNECTED_PEER_OR_EGRESS_MISMATCH")


def _read_exact(conn, count, deadline):
    result = bytearray()
    while len(result) < count:
        conn.settimeout(remaining(deadline))
        chunk = conn.recv(count-len(result))
        require(bool(chunk), "DNS_REPLY_TRUNCATED")
        result.extend(chunk)
    return bytes(result)


def _name(packet, position):
    labels = []
    visited = set()
    end = None
    while True:
        require(0 <= position < len(packet) and position not in visited and len(visited) <= 128,
                "DNS_NAME_INVALID")
        visited.add(position)
        count = packet[position]
        position += 1
        if count == 0:
            return b".".join(labels).lower(), end if end is not None else position
        if count & 0xC0 == 0xC0:
            require(position < len(packet), "DNS_NAME_INVALID")
            pointer = ((count & 0x3F) << 8) | packet[position]
            require(pointer < position-1, "DNS_NAME_INVALID")
            end = position+1 if end is None else end
            position = pointer
        else:
            require(count <= 63 and position+count <= len(packet) and len(labels) <= 32, "DNS_NAME_INVALID")
            labels.append(packet[position:position+count])
            position += count


def _dns_answers(packet, query_id):
    require(12 <= len(packet) <= DNS_LIMIT, "DNS_REPLY_INVALID")
    ident, flags, questions, answers, _, _ = struct.unpack_from("!6H", packet)
    require(ident == query_id and flags & 0xFA0F == 0x8000 and questions == 1 and 1 <= answers <= 64,
            "DNS_REPLY_INVALID")
    question, pos = _name(packet, 12)
    origin = HOST.encode("ascii")
    require(question == origin and packet[pos:pos+4] == struct.pack("!HH", 1, 1), "DNS_QUESTION_MISMATCH")
    pos += 4
    aliases = {}
    addresses = {}
    for _ in range(answers):
        name, pos = _name(packet, pos)
        require(pos+10 <= len(packet), "DNS_REPLY_TRUNCATED")
        typ, cls, _, size = struct.unpack_from("!HHIH", packet, pos)
        pos += 10
        require(pos+size <= len(packet) and cls == 1, "DNS_REPLY_INVALID")
        if typ == 5:
            alias, end = _name(packet, pos)
            require(end == pos+size and name not in aliases and bool(alias), "DNS_ALIAS_INVALID")
            aliases[name] = alias
        elif typ == 1:
            require(size == 4, "DNS_ADDRESS_INVALID")
            addresses.setdefault(name, set()).add(str(ipaddress.IPv4Address(packet[pos:pos+4])))
        pos += size
    name = origin
    visited = set()
    while name in aliases:
        require(name not in visited and name not in addresses, "DNS_ALIAS_INVALID")
        visited.add(name)
        name = aliases[name]
    require(bool(addresses.get(name)), "DNS_NO_BOUND_ADDRESS")
    return tuple(sorted(addresses[name]))


def _select_peer(answers, approved, pinned=None):
    require(bool(answers) and set(answers) <= set(approved), "DNS_PEER_OUTSIDE_APPROVAL")
    if pinned is not None:
        require(pinned in answers, "DNS_BINDING_CHANGED")
        return pinned
    return sorted(answers)[0]


def _resolve(route, deadline):
    query_id = secrets.randbelow(65536)
    query = struct.pack("!6H", query_id, 0x0100, 1, 0, 0, 0) + QUESTION
    try:
        with _bound_socket(route) as conn:
            conn.settimeout(remaining(deadline))
            conn.connect((route.resolver_address, 53))
            _peer_matches(conn, route.resolver_address, 53, route.source_address)
            conn.settimeout(remaining(deadline))
            conn.sendall(struct.pack("!H", len(query)) + query)
            count = struct.unpack("!H", _read_exact(conn, 2, deadline))[0]
            require(12 <= count <= DNS_LIMIT, "DNS_REPLY_TOO_LARGE_OR_SHORT")
            return _dns_answers(_read_exact(conn, count, deadline), query_id)
    except OSError as exc:
        raise SourceBlocked("DNS_EGRESS_FAILED") from exc


def _tls_context(pem: bytes):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.hostname_checks_common_name = False
    context.load_verify_locations(cadata=pem.decode("ascii"))
    return context


def _exchange(conn, request: RouteRequest, context, deadline, proof, before_write):
    """Read one HTTP response on a caller-owned, already connected socket."""
    require(type(request) is RouteRequest, "INVALID_B5_REQUEST")
    _, request_bytes = request.validate()
    require(context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
            and context.minimum_version >= ssl.TLSVersion.TLSv1_2, "TLS_VERIFY_REQUIRED")
    try:
        conn.settimeout(min(WIRE.connect_ms/1000, remaining(deadline)))
        with context.wrap_socket(conn, server_hostname=HOST) as tls:
            cert = tls.getpeercert(binary_form=True)
            require(bool(cert) and tls.version() in {"TLSv1.2", "TLSv1.3"}, "TLS_PROOF_MISSING")
            tls_proof = {**proof, "sni": HOST, "certificate_sha256": sha(cert), "protocol": tls.version(),
                         "verification": "CERT_REQUIRED_AND_HOSTNAME"}
            before_write()
            # Reconstruct only the exact validated unsigned query.
            require(request.validate()[1] == request_bytes, "REQUEST_CHANGED_AT_DISPATCH")
            tls.settimeout(min(WIRE.idle_ms/1000, remaining(deadline)))
            tls.sendall(request_bytes)
            raw = BoundedRead(tls, deadline, WIRE)
            response = http.client.HTTPResponse(ResponseSocket(raw), method="GET")
            status, headers = None, {}
            try:
                response.begin()
                status = response.status
                headers = audit_headers(response.getheaders())
                if 300 <= status < 400 or status == 418:
                    return Reply(status, headers, b"", raw.seen, complete=False, tls=tls_proof)
                body, encoded = entity(response, WIRE.max_decoded_bytes, deadline)
                return Reply(status, headers, body, raw.seen, encoded, tls=tls_proof)
            except (SourceBlocked, OSError, http.client.HTTPException) as exc:
                if status is None:
                    raise
                reason = exc.code if isinstance(exc, SourceBlocked) else "HTTP_BODY_INCOMPLETE"
                return Reply(status, headers, b"", raw.seen, complete=False, issue=reason, tls=tls_proof)
            finally:
                response.close()
    except ssl.SSLError as exc:
        raise WireFailure("TLS_VERIFICATION_FAILED") from exc
    except (TimeoutError, ConnectionResetError, ConnectionAbortedError) as exc:
        raise WireFailure("TRANSIENT_WIRE_FAILURE", retryable=True) from exc
    except (OSError, http.client.HTTPException) as exc:
        raise WireFailure("HTTP_TRANSPORT_FAILED") from exc


@dataclass(frozen=True)
class PhysicalProof:
    reservation: int
    wire_sha: str
    response: Reply


class PhysicalTransport:
    """The sole real transport. There is no selectable host, CA, resolver hook or QA mode."""

    def __init__(self, active):
        from .ledger import Active

        roots = production_roots()
        require(type(active) is Active, "PRODUCTION_RUN_REQUIRED")
        active.assert_production(roots)
        self.active = active
        self.pinned = None
        self.answers: tuple[str, ...] = ()
        self.resolved_scan = None
        pem = Path(PRODUCTION_CA).read_bytes()
        require(sha(pem) == roots.ca_bundle_sha256, "SYSTEM_CA_BUNDLE_CHANGED")
        self.context = _tls_context(pem)
        self.ca_sha = roots.ca_bundle_sha256

    def send(self, request, timeout_ms, reservation):
        active = self.active
        from .ledger import Active

        roots = production_roots()
        require(type(active) is Active, "PRODUCTION_RUN_REQUIRED")
        active.assert_production(roots)
        require(type(request) is RouteRequest, "INVALID_B5_REQUEST")
        require(bounded_int(timeout_ms,1,POLICY.request_timeout_ms), "PHYSICAL_REQUEST_TIMEOUT_INVALID")
        _, wire = request.validate()
        pending = active.assert_pending(reservation, request)
        route = active.approval.scope.route
        check_local_route(route)
        deadline = time.monotonic() + timeout_ms/1000
        connect_limit = min(deadline, time.monotonic()+WIRE.connect_ms/1000)
        if self.resolved_scan != pending["scan_id"]:
            answers = _resolve(route, connect_limit)
            self.pinned = _select_peer(answers, route.peers, self.pinned)
            self.answers = answers
            self.resolved_scan = pending["scan_id"]
        active.assert_pending(reservation, request)
        check_local_route(route)
        try:
            with _bound_socket(route) as conn:
                conn.settimeout(remaining(connect_limit))
                conn.connect((self.pinned, PORT))
                _peer_matches(conn, self.pinned, PORT, route.source_address)
                proof = {"peer": self.pinned, "resolved_ipv4": ",".join(self.answers),
                         "egress_id": route.egress_id, "source_ipv4": route.source_address,
                         "netns_inode": str(route.netns_inode), "interface": route.interface,
                         "resolver_ipv4": route.resolver_address,
                         "route_table_sha256": route.route_table_sha256, "ca_sha256": self.ca_sha,
                         "authority": request.host + ":443"}
                def before_write():
                    check_local_route(route)
                    active.assert_pending(reservation, request)

                reply = _exchange(conn, request, self.context, deadline, proof, before_write)
        except (TimeoutError, ConnectionResetError, ConnectionAbortedError) as exc:
            raise WireFailure("TRANSIENT_CONNECT_FAILURE", retryable=True) from exc
        except OSError as exc:
            raise WireFailure("CONNECT_FAILED") from exc
        return PhysicalProof(reservation, sha(wire), reply)
