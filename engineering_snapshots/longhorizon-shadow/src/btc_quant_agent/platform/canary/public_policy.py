"""Prospective Owner-attested scope. No constructor or preflight opens a market socket."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shutil
import time
import math
import ctypes
import sys
import threading
import uuid
from importlib.metadata import version, PackageNotFoundError

from ..core import fingerprint
from .policy import ROOT, Policy, SourceGrant
from .clock_domain import ClockEpoch, capture, sample_reason, same_epoch

HEAD = "570659d4e7cf673144bc1ffb9e82a1581c3c038e"
EGRESS_OWNER = "OWNER-V070-L4-EGRESS-GATEWAY-20261030"
DEFAULT_GRANT = ROOT / "configs/canary/scope_session02_preparation_offline_20261030.json"
SOURCE_BINDING = ROOT / "configs/canary/source_binding_session02_preparation_20261030.json"
ENDPOINT_DOCUMENT = ROOT / "configs/canary/public_endpoints_session02_preparation_20261030.json"
REVIEWED_DOCUMENT = ROOT / "configs/canary/public_endpoints_20261030.json"
REVIEW_AUTHORITY = ROOT / "configs/canary/source_grant_20261030.json"
OWNER = "OWNER-V070-L4-WINDOW-20261030"
ATTESTATION_REF = "OWNER-V070-L4-REGION-ATTESTED-20261029"
OUTER_OWNER = "OWNER-V070-L4-3SYM-20261029"
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
START = int(datetime(2026, 10, 30, tzinfo=timezone.utc).timestamp() * 1000)
END = int(datetime(2026, 10, 31, 2, tzinfo=timezone.utc).timestamp() * 1000)
OUTPUT = ROOT / "artifacts/live_public_canary_20261030"
ACCESS_DENIAL = OUTPUT / "source_access_denial.json"
REST = {
    "binance_usdm_exchange_info": "/fapi/v1/exchangeInfo",
    "binance_usdm_server_time": "/fapi/v1/time",
    "binance_usdm_klines_rest": "/fapi/v1/klines",
    "binance_usdm_oi": "/fapi/v1/openInterest",
    "binance_usdm_premium": "/fapi/v1/premiumIndex",
    "binance_usdm_funding_info": "/fapi/v1/fundingInfo",
    "binance_usdm_turnover": "/fapi/v1/ticker/24hr",
}
WS = ("binance_usdm_bbo_ws", "binance_usdm_klines_ws")
IDS = tuple(sorted((*REST, *WS)))
DOC_HOST = "developers.binance.com"
DOC_PATHS = (
    "/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data",
    "/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/public",
    "/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/market",
    "/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Connect",
    "/en/docs/products/derivatives-trading-usds-futures/change-log",
)


class PublicStop(RuntimeError):
    pass


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def persisted_source_denial():
    if ACCESS_DENIAL.is_symlink():
        return "SOURCE_ACCESS_STATE_INVALID"
    if not ACCESS_DENIAL.exists():
        return None
    try:
        value = json.loads(ACCESS_DENIAL.read_text())
        if (value.get("provider"), value.get("market"), value.get("exposure")) != (
            "binance",
            "USD_M",
            "PUBLIC_CANARY",
        ):
            return "SOURCE_ACCESS_STATE_INVALID"
        return "VENUE_ACCESS_DENIED_PERSISTED"
    except (OSError, ValueError, AttributeError):
        return "SOURCE_ACCESS_STATE_INVALID"


def persist_source_denial(value):
    """Keep the first actual denial across restarts; synthetic fixtures never call this."""
    ACCESS_DENIAL.parent.mkdir(parents=True, exist_ok=True)
    import os

    try:
        with ACCESS_DENIAL.open("x") as f:
            json.dump(value, f, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
    except FileExistsError:
        pass
    fd = os.open(ACCESS_DENIAL.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class SystemClock:
    def __init__(self):
        self._clock_lock = threading.RLock()
        self.epoch = ClockEpoch(str(uuid.uuid4()))
        self._sync_checked_mono = -(10**18)
        self.refresh_sync()
        self.anchor_wall, self.anchor_mono = self.pair()

    def refresh_sync(self):
        now = self.mono()
        if now - self._sync_checked_mono < 60000:
            return
        self._sync_checked_mono = now
        evidence = {
            "status": "UNVERIFIED",
            "method": "Linux adjtimex modes=0 read-only",
            "sample_mono_ms": now,
        }
        try:
            if not sys.platform.startswith("linux") or ctypes.sizeof(ctypes.c_long) != 8:
                raise RuntimeError("UNSUPPORTED_HOST_CLOCK_INTERFACE")

            class Leading(ctypes.Structure):
                _fields_ = [
                    ("modes", ctypes.c_uint),
                    ("offset", ctypes.c_long),
                    ("freq", ctypes.c_long),
                    ("maxerror", ctypes.c_long),
                    ("esterror", ctypes.c_long),
                    ("status", ctypes.c_int),
                ]

            buf = ctypes.create_string_buffer(1024)
            result = ctypes.CDLL(None, use_errno=True).adjtimex(ctypes.byref(buf))
            value = Leading.from_buffer(buf)
            uncertainty = math.ceil(max(0, value.maxerror) / 1000) + 1
            evidence.update(
                kernel_status=value.status,
                return_code=result,
                maxerror_us=value.maxerror,
                esterror_us=value.esterror,
                uncertainty_ms=uncertainty,
                system_clock_modified=False,
            )
            evidence["status"] = (
                "SYNC_OBSERVED"
                if result >= 0 and result != 5 and not value.status & 64 and uncertainty <= 1000
                else "UNVERIFIED"
            )
        except (OSError, AttributeError, RuntimeError) as exc:
            evidence["reason"] = str(exc)
        self.sync_evidence = evidence
        self.utc_uncertainty_ms = evidence.get("uncertainty_ms", 1001)

    def wall(self):
        return time.time_ns() // 1_000_000

    def mono(self):
        return time.monotonic_ns() // 1_000_000

    def pair(self):
        sample = self.sample()
        return sample["wall_ms"], sample["mono_after_ms"]

    def sample(self):
        # Bracket the wall read; do not mistake scheduler delay for a wall step.
        # Invalid samples remain recordable during shutdown, but cannot be admitted.
        with self._clock_lock:
            self.refresh_sync()
            before = self.mono()
            wall = self.wall()
            after = self.mono()
            return self.epoch.capture(wall, before, after, self.sync_evidence)

    def sleep(self, seconds):
        if not 0 <= seconds <= 1:
            raise PublicStop("UNBOUNDED_WAIT_FORBIDDEN")
        time.sleep(seconds)


class Window:
    def __init__(self, clock, *, start_ms=START, end_ms=END):
        if type(start_ms) is not int or type(end_ms) is not int or not START <= start_ms < end_ms <= END:
            raise PublicStop("GRANT_WINDOW_BOUNDS_INVALID")
        self.start_ms, self.end_ms = start_ms, end_ms
        self.clock = clock
        self.wall0, self.mono0, self.sample0 = capture(clock)
        self.mono_end = self.mono0 + max(
            0, self.end_ms - self.wall0 - getattr(clock, "utc_uncertainty_ms", 0)
        )
        self.stopped = False
        self.stop_reason = None

    def check(self):
        if hasattr(self.clock, "refresh_sync"):
            self.clock.refresh_sync()
            if self.clock.sync_evidence["status"] != "SYNC_OBSERVED":
                raise PublicStop("CLOCK_SYNC_UNVERIFIED")
        wall, mono, sample = capture(self.clock)
        uncertainty = getattr(self.clock, "utc_uncertainty_ms", 0)
        self.mono_end = min(self.mono_end, mono + max(0, self.end_ms - wall - uncertainty))
        if self.stopped:
            raise PublicStop(self.stop_reason or "GRANT_WINDOW_EXPIRED")
        if wall + uncertainty >= self.end_ms or mono >= self.mono_end:
            self.stopped = True
            self.stop_reason = "GRANT_WINDOW_EXPIRED"
            raise PublicStop(self.stop_reason)
        if wall - uncertainty < self.start_ms:
            raise PublicStop("GRANT_WINDOW_NOT_OPEN")
        if sample is not None and (reason := sample_reason(sample)):
            self.stopped = True
            self.stop_reason = reason
            raise PublicStop(reason)
        if sample is not None and self.sample0 is not None and (reason := same_epoch([self.sample0, sample])):
            self.stopped = True
            self.stop_reason = reason
            raise PublicStop(reason)
        if abs((wall - self.wall0) - (mono - self.mono0)) > 50:
            self.stopped = True
            self.stop_reason = "LOCAL_WALL_CLOCK_JUMP"
            raise PublicStop(self.stop_reason)
        return min((self.end_ms - wall - uncertainty) / 1000, (self.mono_end - mono) / 1000)


@dataclass(frozen=True)
class PublicScope:
    grant: SourceGrant
    raw: dict
    document: dict
    grant_path: Path

    @property
    def hash(self):
        return self.grant.policy_hash

    def validate_route(self, route):
        mode = route.get("egress_mode")
        if mode == "DIRECT":
            return
        approved = self.raw["policy"]["egress"]
        if (
            mode != "CONTROLLED_EGRESS_PROXY"
            or route.get("proxy_host") != approved["proxy_host"]
            or route.get("proxy_port") != approved["proxy_port"]
            or route.get("tunnel_type") not in approved["tunnel_types"]
            or self.raw.get("egress_authority_ref") != EGRESS_OWNER
        ):
            raise PublicStop("EGRESS_ROUTE_GRANT_MISMATCH")

    def verify_document_baseline(self):
        declared = self.raw["policy"].get("document_validation", {})
        if (
            declared.get("mode") != "LOCAL_REVIEWED_BASELINE"
            or declared.get("path") != str(REVIEWED_DOCUMENT.relative_to(ROOT))
            or declared.get("authority_path") != str(REVIEW_AUTHORITY.relative_to(ROOT))
            or sha(REVIEWED_DOCUMENT) != declared.get("sha256")
            or sha(REVIEW_AUTHORITY) != declared.get("authority_sha256")
        ):
            raise PublicStop("REVIEWED_DOCUMENT_BASELINE_MISMATCH")
        original = json.loads(REVIEWED_DOCUMENT.read_text())
        authority = json.loads(REVIEW_AUTHORITY.read_text())
        if (
            fingerprint(original) != authority["source_grant"]["documentation_fingerprint"]
            or not original.get("official_review_complete")
            or original["endpoints"] != self.document["endpoints"]
            or original["unknowns"] != self.document["unknowns"]
        ):
            raise PublicStop("REVIEWED_DOCUMENT_CONTRACT_DRIFT")
        return {
            "status": "DOCUMENT_BASELINE_VERIFIED_OFFLINE",
            "path": declared["path"],
            "sha256": declared["sha256"],
            "authority_sha256": declared["authority_sha256"],
            "canonical_head": HEAD,
            "fact_checks": "LOCAL_CONTENT_AND_REVIEW_BINDING_VERIFIED",
            "observed_feed_quality": False,
            "network_requests": 0,
            "dynamic_contract": "exchangeInfo rules/status/filters/rateLimits; independent native clock/schema gates remain mandatory",
        }

    def validate_request(self, id, params, now):
        if id not in REST or id not in self.grant.endpoint_ids:
            raise PublicStop("ENDPOINT_FORBIDDEN")
        if not START <= now < END:
            raise PublicStop("GRANT_WINDOW_NOT_OPEN" if now < START else "GRANT_WINDOW_EXPIRED")
        if id in ("binance_usdm_oi", "binance_usdm_premium", "binance_usdm_turnover"):
            if set(params) != {"symbol"} or params["symbol"] not in SYMBOLS:
                raise PublicStop("SYMBOL_OR_PARAMETER_SCOPE_VIOLATION")
        elif id == "binance_usdm_klines_rest":
            if set(params) != {"symbol", "interval", "startTime", "endTime", "limit"}:
                raise PublicStop("KLINE_SCOPE_VIOLATION")
            size = {"1m": 60000, "5m": 300000}.get(params["interval"])
            if (
                params["symbol"] not in SYMBOLS
                or size is None
                or type(params["limit"]) is not int
                or not 1 <= params["limit"] <= 99
                or not START <= params["startTime"] <= params["endTime"] < min(now, END)
                or params["startTime"] % size
                or (params["endTime"] + 1) % size
            ):
                raise PublicStop("KLINE_FUTURE_HISTORY_OR_INTERVAL_FORBIDDEN")
        elif params:
            raise PublicStop("UNAPPROVED_PARAMETERS")
        return "https://fapi.binance.com" + REST[id]

    def streams(self, group):
        if group == "public":
            return tuple(s.lower() + "@bookTicker" for s in SYMBOLS)
        if group == "market":
            return tuple(s.lower() + "@kline_" + interval for s in SYMBOLS for interval in ("1m", "5m"))
        raise PublicStop("PRIVATE_OR_UNKNOWN_STREAM_GROUP")

    def ws_url(self, group):
        return "wss://fstream.binance.com/" + group + "/stream?streams=" + "/".join(self.streams(group))

    def endpoint(self, id):
        from .policy import ROOT, load_catalog

        if id not in IDS:
            raise PublicStop("ENDPOINT_FORBIDDEN")
        endpoint = load_catalog(ROOT / "configs/canary/endpoints.json")[id]
        declared = next(e for e in self.document["endpoints"] if e["id"] == id)
        return endpoint.model_copy(
            update={
                "timestamp_semantics": declared["timestamp_semantics"],
                "documented_rate_limits": declared["rate_limits"],
                "websocket": declared.get("websocket", endpoint.websocket),
            }
        )

    def budget_policy(self):
        # Reuse Phase A's budget container only. Its OFFLINE flag is not a network grant.
        return Policy.model_validate(
            {
                "symbols": SYMBOLS,
                "endpoint_ids": IDS,
                "synthetic_start_ms": START,
                "duration_ms": END - START,
                "endpoint_calls_per_minute": self.grant.endpoint_calls_per_minute,
                "max_subscriptions": 9,
                "max_connections": 2,
                "storage": {
                    "raw_retention_hours": 36,
                    "normalized_retention_hours": 168,
                    "raw_quota_bytes": 8 * 1024**3,
                    # This counter container reserves metadata INSIDE the auxiliary cap.
                    # PublicJournal enforces the actual combined auxiliary ceiling.
                    "normalized_quota_bytes": 4 * 1024**3 - 1024**2,
                    "total_disk_quota_bytes": 12 * 1024**3,
                    "symbol_quota_bytes": 4 * 1024**3,
                    "max_chunks": 200000,
                },
            }
        )


def current_source_hashes():
    files = list((ROOT / "src/btc_quant_agent/platform").rglob("*.py"))
    files += [ROOT / "tools/launch_public_canary.py", ROOT / "pyproject.toml"]
    return {str(p.relative_to(ROOT)): sha(p) for p in sorted(files)}


def load_scope(path=DEFAULT_GRANT):
    path = Path(path)
    raw = json.loads(path.read_text())
    grant = SourceGrant.model_validate(raw["source_grant"])
    document_path = ROOT / raw["documentation_file"]
    if document_path.resolve() != ENDPOINT_DOCUMENT:
        raise PublicStop("UNTRUSTED_DOCUMENTATION_PATH")
    document = json.loads(document_path.read_text())
    attest = ROOT / "L4_BC_OWNER_ATTESTATION_20261029.md"
    if (
        grant.grant_id != OWNER
        or grant.authority != "OWNER_EXACT_SOURCE_GRANT"
        or grant.permitted_use_status != "EXPLICITLY_OWNER_CONFIRMED"
        or raw["canonical_head"] != HEAD
        or raw.get("egress_authority_ref") != EGRESS_OWNER
        or document.get("canonical_head") != HEAD
        or raw["owner_attestation_sha256"] != sha(attest)
        or raw["owner_attestation_ref"] != ATTESTATION_REF
        or raw["window_amendment_sha256"] != sha(ROOT / "L4_BC_WINDOW_AMENDMENT_20261029.md")
        or raw["owner_scope_ref"] != OUTER_OWNER
        or not document.get("official_review_complete")
    ):
        raise PublicStop("OWNER_ATTESTATION_BINDING_INVALID")
    if (
        tuple(grant.symbols) != SYMBOLS
        or tuple(sorted(grant.endpoint_ids)) != IDS
        or set(grant.fields) != set(IDS)
        or set(grant.hosts) != {"https://fapi.binance.com", "wss://fstream.binance.com"}
        or grant.provider != "binance"
        or grant.market != "USD_M"
        or grant.region != "NOT_INDEPENDENTLY_OBSERVED"
        or (grant.start_utc_ms, grant.end_utc_ms) != (START, END)
        or Path(grant.output_path).resolve() != OUTPUT
        or grant.ip_weight_per_minute != 60
        or grant.controls_per_second != 2
        or grant.subscriptions != 9
        or grant.connections != 2
        or grant.reconnects_per_hour != 3
        or grant.bytes_total != 12 * 1024**3
        or (grant.raw_retention_hours, grant.normalized_retention_hours) != (36, 168)
    ):
        raise PublicStop("EXACT_OWNER_SCOPE_MISMATCH")
    if (
        raw["storage"]
        != {"raw_bytes": 8 * 1024**3, "auxiliary_bytes": 4 * 1024**3, "reserve_bytes": 2 * 1024**3}
        or fingerprint(raw["policy"]) != grant.policy_hash
        or fingerprint(document) != grant.documentation_fingerprint
        or raw["policy"]["endpoint_caps"] != grant.endpoint_calls_per_minute
    ):
        raise PublicStop("POLICY_DOCUMENT_OR_QUOTA_BINDING_MISMATCH")
    if (ROOT / raw.get("source_binding_file", "")).resolve() != SOURCE_BINDING:
        raise PublicStop("SOURCE_BINDING_PATH_INVALID")
    binding = json.loads(SOURCE_BINDING.read_text())
    if (
        binding["files"] != current_source_hashes()
        or fingerprint(binding["files"]) != raw["policy"].get("source_fingerprint")
        or binding.get("canonical_head") != HEAD
    ):
        raise PublicStop("CURRENT_SOURCE_BINDING_MISMATCH")
    if not (HEAD in grant.approval_source_reference and OWNER in grant.approval_source_reference):
        raise PublicStop("EXTERNAL_APPROVAL_PROVENANCE_MISSING")
    if tuple(sorted(e["id"] for e in document["endpoints"])) != IDS or {
        r["path"] for r in document["runtime_document_checks"]
    } != set(DOC_PATHS):
        raise PublicStop("DOCUMENT_ENDPOINT_OR_PATH_SET_MISMATCH")
    for e in document["endpoints"]:
        if e["id"] not in IDS or tuple(grant.fields[e["id"]]) != tuple(e["fields"]):
            raise PublicStop("FIELD_GRANT_BINDING_MISMATCH")
    scope = PublicScope(grant, raw, document, path)
    scope.verify_document_baseline()
    return scope


def preflight(scope, clock=None, *, native=True):
    clock = clock or SystemClock()
    now = clock.wall()
    usage = shutil.disk_usage(OUTPUT.parent)
    required = 14 * 1024**3
    reasons = []
    if native and scope.raw.get("activation_status") == "OFFLINE_ONLY_PENDING_SECOND_SESSION_AUTH":
        reasons.append("SECOND_NATIVE_SESSION_REQUIRES_DISTINCT_OWNER_AUTHORIZATION")
    denied = persisted_source_denial() if native else None
    if denied:
        reasons.append(denied)
    dependencies = {}
    for name, expected in {"httpx": "0.28.1", "httpcore": "1.0.9", "websockets": "16.1.1"}.items():
        try:
            dependencies[name] = version(name)
        except PackageNotFoundError:
            dependencies[name] = "MISSING"
        if dependencies[name] != expected:
            reasons.append("PUBLIC_DEPENDENCY_VERSION_UNTESTED:" + name)
    if hasattr(clock, "sync_evidence") and clock.sync_evidence["status"] != "SYNC_OBSERVED":
        reasons.append("CLOCK_SYNC_UNVERIFIED")
    if usage.free < required:
        reasons.append("STORAGE_SCOPE_BLOCKED")
    if now >= END:
        reasons.append("GRANT_WINDOW_EXPIRED")
    if scope.raw["policy"].get("known_terms_conflict"):
        reasons.append("TERMS_CONFLICT")
    age = now - int(
        datetime.fromisoformat(scope.document["reviewed_utc"].replace("Z", "+00:00")).timestamp() * 1000
    )
    if age < 0 or age > 7 * 86400000:
        reasons.append("DOCUMENTATION_REVIEW_EXPIRED")
    return {
        "status": "BLOCKED"
        if reasons
        else "READY_FOR_OPERATOR_WINDOW"
        if now < START
        else "TECHNICAL_PREFLIGHT_PASSED",
        "reasons": reasons,
        "window_status": "GRANT_WINDOW_NOT_OPEN"
        if now < START
        else "GRANT_WINDOW_EXPIRED"
        if now >= END
        else "OPEN",
        "owner_documentary_gate": "OWNER_ATTESTED_SATISFIED_FOR_INTERNAL_DISPATCH",
        "host_jurisdiction": "NOT_INDEPENDENTLY_OBSERVED",
        "venue_permission_independently_verified": False,
        "available_disk_bytes": usage.free,
        "required_with_reserve_bytes": required,
        "scope_hash": scope.hash,
        "source_qualified": False,
        "shadow_advisory_qualified": False,
        "economically_validated": False,
        "native_market_calls": 0,
        "dependencies": dependencies,
        "receiver_utc_sync_evidence": getattr(clock, "sync_evidence", {"status": "SYNTHETIC_CLOCK_FIXTURE"}),
        "execution_default_disabled": True,
        "launch_requires_explicit_flag": True,
        "runtime_document_recheck": "Local reviewed-baseline hashes and scope verified; no website availability dependency. Native exchangeInfo rules/schema/rates independently checked.",
        "ip_ceiling_bootstrap": "One approved exchangeInfo request of weight 1; unknown returned limit stops all subsequent requests",
        "background_or_scheduled_task": False,
    }
