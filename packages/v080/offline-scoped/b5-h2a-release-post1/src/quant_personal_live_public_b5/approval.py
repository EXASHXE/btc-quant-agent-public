"""Strict signed-scope verification. Neither role can issue an approval alone."""

from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from quant_personal_public_b1.policy import SourceBlocked, require
from quant_personal_public_b1.store import encode

from .contract import (
    APPROVAL_SCHEMA, AUTHORITY, BASE_MAX_REQUESTS, BASE_MAX_WEIGHT, CONTRACT,
    INTERVALS, ROUTES, SCOPE_SCHEMA, SYMBOL_ORDER, TASK, bounded_int, digest, sha_text,
)
from .stages import SCOPE_V2, StagePlan
from .trust import TrustRoots

MAX_APPROVAL_MS = 24 * 3_600_000


def fields(raw, expected, code):
    require(type(raw) is dict and raw.keys() == set(expected.split()), code)


def safe_path(raw):
    require(type(raw) is str and 1 <= len(raw) <= 4096 and raw.startswith("/")
            and "//" not in raw and not any(ch in raw for ch in "\x00\r\n"), "LOCAL_PATH_INVALID")
    path = Path(raw)
    require(path == Path(path.as_posix()) and path.as_posix() == raw and ".." not in path.parts
            and path != Path("/"), "LOCAL_PATH_INVALID")
    return path


def ipv4(raw, *, public=False):
    require(type(raw) is str and len(raw) <= 15, "ROUTE_ADDRESS_INVALID")
    try:
        address = ipaddress.IPv4Address(raw)
    except ipaddress.AddressValueError as exc:
        raise SourceBlocked("ROUTE_ADDRESS_INVALID") from exc
    require(not (address.is_loopback or address.is_multicast or address.is_unspecified or address.is_link_local
                 or address.is_reserved) and (not public or address.is_global), "ROUTE_ADDRESS_INVALID")
    return str(address)


@dataclass(frozen=True)
class RouteScope:
    region: str
    egress_id: str
    netns_inode: int
    interface: str
    source_address: str
    resolver_address: str
    peers: tuple[str, ...]
    route_table_sha256: str

    @classmethod
    def parse(cls, raw):
        fields(raw, "region egress_id netns_inode interface source_ipv4 resolver_ipv4 approved_ipv4 route_table_sha256 direct_only",
               "ROUTE_SCOPE_INVALID")
        require(type(raw["region"]) is str and re.fullmatch(r"[A-Z]{2}", raw["region"])
                and sha_text(raw["egress_id"]) and sha_text(raw["route_table_sha256"])
                and bounded_int(raw["netns_inode"], 1, 2**63-1)
                and type(raw["interface"]) is str and re.fullmatch(r"[A-Za-z0-9_.-]{1,15}", raw["interface"])
                and raw["interface"] != "lo" and raw["direct_only"] is True
                and type(raw["approved_ipv4"]) is list and 1 <= len(raw["approved_ipv4"]) <= 16,
                "ROUTE_SCOPE_INVALID")
        peers = tuple(ipv4(peer, public=True) for peer in raw["approved_ipv4"])
        require(list(sorted(set(peers))) == list(peers), "ROUTE_PEER_LIST_NON_CANONICAL")
        return cls(raw["region"], raw["egress_id"], raw["netns_inode"], raw["interface"],
                   ipv4(raw["source_ipv4"]), ipv4(raw["resolver_ipv4"]), peers, raw["route_table_sha256"])


@dataclass(frozen=True)
class Limit:
    count: int
    weight: int

    @classmethod
    def parse(cls, raw, cap_count, cap_weight):
        fields(raw, "count weight", "LIMIT_INVALID")
        require(bounded_int(raw["count"], 1, cap_count) and bounded_int(raw["weight"], 1, cap_weight),
                "LIMIT_INVALID")
        return cls(raw["count"], raw["weight"])


@dataclass(frozen=True)
class Scope:
    sha256: str
    route: RouteScope
    ledger: Path
    journal: Path
    retention_days: int
    phase_limits: MappingProxyType
    rolling: Limit
    total: Limit
    headroom_weight: int
    funding_debit: int | None
    stage_plan: StagePlan | None = None

    @classmethod
    def parse(cls, raw, roots):
        staged = type(raw) is dict and raw.get("schema") == SCOPE_V2
        expected = ("schema task endpoint_contract host methods routes symbols frames network storage "
                    "budget funding live_permitted")
        fields(raw, expected + (" activation_plan" if staged else ""), "SCOPE_FIELDS_INVALID")
        require(raw["schema"] in (SCOPE_SCHEMA, SCOPE_V2) and raw["task"] == TASK and raw["endpoint_contract"] == CONTRACT
                and raw["live_permitted"] is True and raw["host"] == AUTHORITY and raw["methods"] == ["GET"]
                and raw["routes"] == list(ROUTES) and raw["symbols"] == list(SYMBOL_ORDER)
                and raw["frames"] == list(INTERVALS), "SCOPE_EXCEEDS_PUBLIC_CONTRACT")
        route = RouteScope.parse(raw["network"])
        require(route.egress_id == roots.egress_id, "EGRESS_IDENTITY_MISMATCH")
        storage = raw["storage"]
        fields(storage, "ledger journal retention_days owner_local_only", "STORAGE_SCOPE_INVALID")
        ledger, journal = safe_path(storage["ledger"]), safe_path(storage["journal"])
        require(ledger == roots.state_path and journal != ledger and journal.parent == ledger.parent
                and storage["owner_local_only"] is True and bounded_int(storage["retention_days"], 1, 3650),
                "STORAGE_SCOPE_INVALID")
        funding = raw["funding"]
        fields(funding, "documented_numeric_ip_weight official_evidence_sha256", "FUNDING_WEIGHT_UNRESOLVED")
        funding_debit = funding["documented_numeric_ip_weight"]
        funding_sha = funding["official_evidence_sha256"]
        canary_only = staged and type(raw["activation_plan"]) is dict and raw["activation_plan"].get("market") is None
        if canary_only:
            require(funding_debit is None and funding_sha is None, "CANARY_FUNDING_MUST_REMAIN_UNUSED")
        else:
            require(bounded_int(funding_debit, 0, BASE_MAX_WEIGHT) and sha_text(funding_sha),
                    "FUNDING_WEIGHT_UNRESOLVED")
        stage_plan = StagePlan.parse(raw["activation_plan"], funding_debit) if staged else None
        budget = raw["budget"]
        fields(budget, "bootstrap refresh_5 refresh_10 total rolling_60s headroom_weight",
               "BUDGET_SCOPE_INVALID")
        phases = {name: Limit.parse(budget[name], BASE_MAX_REQUESTS, BASE_MAX_WEIGHT)
                  for name in ("bootstrap", "refresh_5", "refresh_10") if budget[name] is not None}
        require("bootstrap" in phases and phases["bootstrap"].count >= 2 and phases["bootstrap"].weight >= 2
                and not ("refresh_10" in phases and "refresh_5" not in phases), "BUDGET_PHASE_INVALID")
        total = Limit.parse(budget["total"], 3*BASE_MAX_REQUESTS, 3*BASE_MAX_WEIGHT)
        rolling = Limit.parse(budget["rolling_60s"], 96, 120)
        headroom = budget["headroom_weight"]
        require(bounded_int(headroom, 1, rolling.weight-1)
                and total.count <= sum(p.count for p in phases.values())
                and total.weight <= sum(p.weight for p in phases.values()), "BUDGET_SCOPE_INVALID")
        if stage_plan is not None:
            require(set(phases) == {"bootstrap"}, "TIMED_REFRESH_DISABLED")
            require((total.count, total.weight) == stage_plan.plan_totals()
                    and phases["bootstrap"] == total, "STAGE_TOTAL_BUDGET_MISMATCH")
            require(rolling.count >= 2 and rolling.weight-headroom >= 2, "CANARY_ROLLING_BUDGET_INSUFFICIENT")
        return cls(digest(raw), route, ledger, journal, storage["retention_days"],
                   MappingProxyType(phases), rolling, total, headroom, funding_debit, stage_plan)


@dataclass(frozen=True)
class Approval:
    run_id: str
    release: str
    scope: Scope
    not_before_ms: int
    expires_ms: int
    signed_sha256: str

    def valid_at(self, wall_ms):
        require(self.not_before_ms <= wall_ms < self.expires_ms, "ACTIVATION_EXPIRED_OR_EARLY")


def _signed(role, claims):
    return ("QUANT-B5-V1/" + role + "\n" + encode(claims)).encode("ascii")


def _verify(key, role, claims, signature):
    require(type(signature) is str and re.fullmatch(r"[0-9a-f]{128}", signature), "ACTIVATION_SIGNATURE_INVALID")
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:
        raise SourceBlocked("ACTIVATION_VERIFIER_UNAVAILABLE") from exc
    try:
        Ed25519PublicKey.from_public_bytes(key).verify(bytes.fromhex(signature), _signed(role, claims))
    except (InvalidSignature, ValueError) as exc:
        raise SourceBlocked("ACTIVATION_SIGNATURE_INVALID") from exc


def verify_envelope(raw, raw_scope, roots: TrustRoots, release, wall_ms, *, historical=False):
    roots.validate()
    fields(raw, "schema claims owner_signature controller_signature", "ACTIVATION_FIELDS_INVALID")
    require(raw["schema"] == APPROVAL_SCHEMA, "ACTIVATION_FIELDS_INVALID")
    claims = raw["claims"]
    fields(claims, "task scope_sha256 release_sha256 egress_id run_id not_before_ms expires_ms",
           "ACTIVATION_CLAIMS_INVALID")
    require(claims["task"] == TASK and type(claims["run_id"]) is str
            and re.fullmatch(r"[0-9a-f]{32}", claims["run_id"]) and sha_text(release)
            and claims["release_sha256"] == release and claims["egress_id"] == roots.egress_id
            and claims["scope_sha256"] == digest(raw_scope), "ACTIVATION_BINDING_MISMATCH")
    begin, end = claims["not_before_ms"], claims["expires_ms"]
    require(bounded_int(begin, 1, 2**63-1) and bounded_int(end, begin+1, min(begin+MAX_APPROVAL_MS, 2**63-1)),
            "ACTIVATION_EXPIRY_INVALID")
    _verify(roots.owner_ed25519, "owner", claims, raw["owner_signature"])
    _verify(roots.controller_ed25519, "controller", claims, raw["controller_signature"])
    scope = Scope.parse(raw_scope, roots)
    approval = Approval(claims["run_id"], release, scope, begin, end, digest(raw))
    if not historical:
        approval.valid_at(wall_ms)
    return approval


def load_local_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "DUPLICATE_APPROVAL_FIELD")
            result[key] = value
        return result

    with path.open("rb") as handle:
        data = handle.read(65537)
    require(len(data) <= 65536, "ACTIVATION_FILE_TOO_LARGE")
    try:
        return json.loads(data, object_pairs_hook=unique,
                          parse_constant=lambda _x: require(False, "ACTIVATION_JSON_INVALID"))
    except (ValueError, RecursionError) as exc:
        raise SourceBlocked("ACTIVATION_JSON_INVALID") from exc
