"""Root-owned, signed-scope-bound direct IPv4 egress facts."""

import ipaddress
import os
import re
import socket
from dataclasses import dataclass
from pathlib import Path

from quant_s2v2.protocol import (
    Denied,
    fields,
    file_bytes,
    fixture_namespace,
    hexdigest,
    integer,
    require,
    sha,
    strict_json,
)

from . import FIXTURE_EVIDENCE, FIXTURE_HOST, HOST, LIVE_EVIDENCE
from ._inherited import route_fingerprint
from .release import production_roots

_PROXY_ENV = {"http_proxy", "https_proxy", "all_proxy", "no_proxy", "sslkeylogfile"}


def no_proxy():
    require(not {name.lower() for name in os.environ} & _PROXY_ENV, "PROXY_OR_KEYLOG_FORBIDDEN")


def loopback_namespace():
    fixture_namespace()


def _address(text):
    try:
        require(type(text) is str, "IPV4_LITERAL_REQUIRED")
        address = ipaddress.IPv4Address(text)
        require(
            str(address) == text and not address.is_unspecified and not address.is_multicast,
            "IPV4_LITERAL_REQUIRED",
        )
        return address
    except ipaddress.AddressValueError as exc:
        raise Denied("IPV4_LITERAL_REQUIRED") from exc


@dataclass(frozen=True)
class Egress:
    path: Path
    expected_sha: str
    evidence: str
    hostname: str
    port: int
    resolver: str
    resolver_port: int
    peer: str
    source: str
    interface: str
    netns_inode: int
    route_table_sha: str
    not_before_ms: int
    expires_ms: int

    @classmethod
    def read(cls, config, evidence):
        data = file_bytes(config.route_path, protected=True)
        require(sha(data) == config.route_sha, "EGRESS_POLICY_DIGEST_MISMATCH")
        raw = strict_json(data)
        fields(
            raw,
            "schema evidence hostname port resolver resolver_port peer source interface "
            "netns_inode route_table_sha not_before_ms expires_ms country product "
            "owner_attested product_verified independent_direct no_bypass shared_known "
            "product_evidence_sha windows_egress_evidence_sha shared_method_sha",
            "EGRESS_POLICY_FIELDS_INVALID",
        )
        require(
            raw["schema"] == "S2V2_DIRECT_EGRESS_V1"
            and (raw["evidence"], raw["country"], raw["product"])
            == (evidence, "KR", "USD_M_USDT_PERPETUAL")
            and all(
                raw[key] is True
                for key in (
                    "owner_attested",
                    "product_verified",
                    "independent_direct",
                    "no_bypass",
                    "shared_known",
                )
            )
            and all(
                hexdigest(raw[key])
                for key in (
                    "route_table_sha",
                    "product_evidence_sha",
                    "windows_egress_evidence_sha",
                    "shared_method_sha",
                )
            ),
            "EGRESS_EVIDENCE_UNKNOWN_OR_CONTRADICTORY",
        )
        require(
            type(raw["interface"]) is str
            and re.fullmatch(r"[a-zA-Z0-9_.-]{1,15}", raw["interface"])
            and integer(raw["netns_inode"], 1, 2**64 - 1)
            and all(integer(raw[key], 1, 2**63 - 1) for key in ("not_before_ms", "expires_ms"))
            and 0 < raw["expires_ms"] - raw["not_before_ms"] <= 86_400_000,
            "EGRESS_POLICY_RANGE_INVALID",
        )
        value = cls(
            config.route_path,
            config.route_sha,
            evidence,
            **{
                name: raw[name]
                for name in (
                    "hostname",
                    "port",
                    "resolver",
                    "resolver_port",
                    "peer",
                    "source",
                    "interface",
                    "netns_inode",
                    "route_table_sha",
                    "not_before_ms",
                    "expires_ms",
                )
            },
        )
        value.check_targets()
        return value

    def check_targets(self):
        resolver, peer, source = map(_address, (self.resolver, self.peer, self.source))
        if self.evidence == FIXTURE_EVIDENCE:
            loopback_namespace()
            require(
                self.hostname == FIXTURE_HOST
                and self.interface == "lo"
                and resolver == peer == source == ipaddress.IPv4Address("127.0.0.1")
                and integer(self.resolver_port, 1024, 65535)
                and integer(self.port, 1024, 65535)
                and self.resolver_port != self.port,
                "FIXTURE_TARGET_FORBIDDEN",
            )
        else:
            roots = production_roots()
            require(
                self.evidence == LIVE_EVIDENCE
                and self.expected_sha == roots.policy_sha
                and (self.hostname, self.port, self.resolver_port) == (HOST, 443, 53)
                and self.interface != "lo"
                and peer.is_global
                and all(
                    not addr.is_loopback and not addr.is_link_local and not addr.is_reserved
                    for addr in (resolver, peer, source)
                ),
                "PRODUCTION_EGRESS_BINDING_INVALID",
            )

    def check(self, now):
        self.check_targets()
        no_proxy()
        require(self.not_before_ms <= now < self.expires_ms, "EGRESS_OBSERVATION_EXPIRED")
        require(
            sha(file_bytes(self.path, protected=True)) == self.expected_sha, "EGRESS_POLICY_CHANGED"
        )
        try:
            namespace = Path("/proc/self/ns/net").stat().st_ino
            known = {name for _, name in socket.if_nameindex()}
            table = Path("/proc/net/route").read_text(encoding="ascii")
        except OSError as exc:
            raise Denied("EGRESS_ROUTE_UNAVAILABLE") from exc
        current = (
            sha(table.encode("ascii"))
            if self.evidence == FIXTURE_EVIDENCE
            else route_fingerprint(table)
        )
        require(
            self.interface in known
            and namespace == self.netns_inode
            and current == self.route_table_sha,
            "EGRESS_ROUTE_CHANGED",
        )
