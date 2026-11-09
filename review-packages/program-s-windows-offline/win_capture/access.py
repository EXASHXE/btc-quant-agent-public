"""Stdlib operational admission, not a venue licence or Strict signed grant."""

from __future__ import annotations
import hashlib
import os
from pathlib import Path
import sqlite3
from .transport import ALLOWED_HOST, ALLOWED_ROUTES, CaptureError, strict_json

POLICY = {
    "schema": "S_WINDOWS_PUBLIC_CAPTURE_V1",
    "host": ALLOWED_HOST,
    "routes": sorted(ALLOWED_ROUTES),
    "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    "method": "GET",
    "max_requests": 24,
    "max_weight": 40,
    "max_seconds": 120,
    "max_retention_hours": 24,
    "consumer_current": "REFUSE_WITHOUT_INDEPENDENT_CURRENT_ANCHOR",
    "proxy": "EXPLICIT_127.0.0.1_CONNECT_ONLY",
    "strict_utc": False,
    "boot_identity": "NATIVE_GUID_AND_KERNEL_BOOT_EPOCH_NO_FALLBACK",
}


def digest(x):
    import json

    return hashlib.sha256(
        json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


POLICY_HASH = digest(POLICY)
J_HASH = "340c3c2b0f7788203b8fdcab36b74fdd982a4d3d7e276b03a69fe681511707ba"
HOLDOUT = (1769904000000, 1785542400000)


def need(ok, why):
    if not ok:
        raise CaptureError(why)


def safe(path):
    p = Path(path).absolute()
    need(".." not in Path(path).parts, "ACCESS_PATH_TRAVERSAL")
    for q in [p, *p.parents]:
        need(not q.is_symlink(), "ACCESS_SYMLINK")
        if os.name == "nt" and q.exists():
            import ctypes

            flags = ctypes.windll.kernel32.GetFileAttributesW(str(q))
            need(flags != 0xFFFFFFFF and not flags & 0x400, "ACCESS_REPARSE_POINT")
    return p


def load_json(p, limit=1048576):
    p = safe(p)
    need(p.is_file() and p.stat().st_size <= limit, "ACCESS_FILE_MISSING_OR_LARGE")
    return strict_json(p.read_bytes())


def source_hash():
    root = Path(__file__).resolve().parent
    return digest({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.glob("*.py"))})


def load_access(path):
    p = safe(path)
    a = load_json(p, 65536)
    required = {
        "schema_version",
        "status",
        "policy_sha256",
        "region",
        "reviewer_reference",
        "eligibility",
        "advisory_use_and_cache",
        "holdout_exclusions",
        "retention_days",
        "operational_rolling_lookback_only",
        "proxy",
    }
    need(set(a) == required, "J_ACCESS_FIELDS")
    need(
        a["schema_version"] == "J_OPERATIONAL_ACCESS_V1"
        and a["status"] == "VERIFIED"
        and a["policy_sha256"] == J_HASH,
        "J_ACCESS_CONTRACT",
    )
    need(
        a["region"] in ["KR", "South Korea"]
        and type(a["retention_days"]) is int
        and a["retention_days"] == 1
        and a["operational_rolling_lookback_only"] is True
        and bool(a["reviewer_reference"].strip()),
        "ACCESS_SCOPE_OR_RETENTION",
    )
    evidence = {}
    for name in ["eligibility", "advisory_use_and_cache", "holdout_exclusions"]:
        ref = a[name]
        need(set(ref) == {"path", "sha256"}, "EVIDENCE_REF_FIELDS")
        q = safe(p.parent / ref["path"])
        need(q.is_relative_to(p.parent), "EVIDENCE_OUTSIDE_OPERATOR_ROOT")
        raw = q.read_bytes()
        need(len(raw) <= 1048576 and hashlib.sha256(raw).hexdigest() == ref["sha256"], "EVIDENCE_HASH")
        evidence[name] = strict_json(raw)
    e = evidence["eligibility"]
    u = evidence["advisory_use_and_cache"]
    x = evidence["holdout_exclusions"]
    need(
        e.get("operator_physical_country") == "KR"
        and e.get("egress_country") == "KR"
        and e.get("declaration_kind") == "OWNER_DECLARATION_NOT_LEGAL_CERTIFICATION",
        "KR_DECLARATION_REQUIRED",
    )
    need(
        e.get("applicable_restriction_found") is False
        and e.get("review_status") == "VERIFIED_OPERATIONAL_SCOPE"
        and isinstance(e.get("official_references"), list)
        and e["official_references"]
        and bool(e.get("reviewed_at_UTC")),
        "CURRENT_SOURCE_REVIEW_REQUIRED",
    )
    need(
        u.get("purpose") == "PERSONAL_NONCOMMERCIAL_READONLY_ADVISORY"
        and u.get("cache_hours") == 24
        and u.get("retention_permission_reviewed") is True,
        "USE_CACHE_REVIEW_REQUIRED",
    )
    need(
        x.get("metadata_complete") is True and isinstance(x.get("excluded_UTC_ms_ranges"), list),
        "EXCLUSIONS_INCOMPLETE",
    )
    ranges = x["excluded_UTC_ms_ranges"]
    for v in ranges:
        need(
            isinstance(v, list) and len(v) == 2 and all(type(z) is int for z in v) and 0 < v[0] < v[1],
            "EXCLUSION_RANGE",
        )
    need(any(lo <= HOLDOUT[0] and hi >= HOLDOUT[1] for lo, hi in ranges), "FINAL_HOLDOUT_REQUIRED")
    proxy = a["proxy"]
    need(
        isinstance(proxy, dict)
        and set(proxy) == {"host", "port", "permitted_reference"}
        and proxy["host"] == "127.0.0.1"
        and type(proxy["port"]) is int
        and 1 <= proxy["port"] <= 65535
        and bool(proxy["permitted_reference"]),
        "APPROVED_LOCAL_CONNECT_REQUIRED",
    )
    return a, ranges, hashlib.sha256(p.read_bytes()).hexdigest()


class Admission:
    def __init__(self, access_path, authorization_path, output, clock, *, _qa=False):
        self.access, self.exclusions, access_hash = load_access(access_path)
        g = load_json(authorization_path)
        now = clock.sample()
        evidence = load_json(Path(access_path).parent / self.access["eligibility"]["path"])
        need(
            evidence.get("review_boot_id") == now["boot_session_id"]
            and type(evidence.get("review_qpc_ms")) is int
            and 0 <= now["qpc_after_ms"] - evidence["review_qpc_ms"] < 86400000,
            "SOURCE_REVIEW_STALE_OR_WRONG_BOOT",
        )
        if not _qa:
            need(
                "SYNTHETIC" not in str(g.get("owner_reference", "")).upper()
                and "SYNTHETIC" not in self.access["reviewer_reference"].upper(),
                "SYNTHETIC_RECORD_NOT_REAL_AUTHORITY",
            )
        required = {
            "schema",
            "owner_reference",
            "session",
            "source_sha256",
            "policy_sha256",
            "access_sha256",
            "output_path",
            "host",
            "routes",
            "symbols",
            "method",
            "max_requests",
            "max_weight",
            "max_seconds",
            "retention_hours",
            "boot_id",
            "not_before_qpc_ms",
            "not_after_qpc_ms",
            "reservation_db",
            "current_source_review_sha256",
        }
        need(set(g) == required, "OWNER_SCOPE_FIELDS")
        need(
            g["schema"] == "S_ONE_MANUAL_SCAN_AUTH_V1"
            and bool(g["owner_reference"])
            and len(g["session"]) >= 16,
            "OWNER_SCOPE_MISSING",
        )
        need(
            g["source_sha256"] == source_hash()
            and g["policy_sha256"] == POLICY_HASH
            and g["access_sha256"] == access_hash,
            "OWNER_CODE_POLICY_ACCESS_BINDING",
        )
        need(
            g["current_source_review_sha256"] == self.access["eligibility"]["sha256"],
            "OWNER_SOURCE_REVIEW_BINDING",
        )
        for field, value in [
            ("host", ALLOWED_HOST),
            ("routes", sorted(ALLOWED_ROUTES)),
            ("symbols", POLICY["symbols"]),
            ("method", "GET"),
            ("max_requests", 24),
            ("max_weight", 40),
            ("max_seconds", 120),
            ("retention_hours", 24),
        ]:
            need(g[field] == value, "OWNER_EXACT_SCOPE_" + field)
        need(str(safe(output)) == g["output_path"] and not Path(output).exists(), "OWNER_UNUSED_OUTPUT")
        need(
            g["boot_id"] == now["boot_session_id"]
            and type(g["not_before_qpc_ms"]) is int
            and type(g["not_after_qpc_ms"]) is int
            and 0 < g["not_after_qpc_ms"] - g["not_before_qpc_ms"] <= 120000
            and g["not_before_qpc_ms"] <= now["qpc_before_ms"] <= now["qpc_after_ms"] < g["not_after_qpc_ms"],
            "OWNER_BOOT_QPC_WINDOW",
        )
        dbpath = safe(g["reservation_db"])
        need(dbpath.parent.exists(), "RESERVATION_PARENT_MISSING")
        if os.name == "nt":
            from .bundle import verify_ntfs

            verify_ntfs(dbpath.parent)
        db = sqlite3.connect(dbpath, timeout=0)
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA journal_mode=DELETE")
        try:
            db.execute(
                "CREATE TABLE IF NOT EXISTS consumed(session TEXT PRIMARY KEY,output TEXT UNIQUE,grant_sha256 TEXT)"
            )
            with db:
                db.execute("INSERT INTO consumed VALUES(?,?,?)", (g["session"], g["output_path"], digest(g)))
        except sqlite3.IntegrityError as e:
            raise CaptureError("OWNER_SESSION_OR_OUTPUT_ALREADY_CONSUMED") from e
        finally:
            db.close()
        self.grant = g
        self.clock = clock
        self.receipt = {
            "schema": "S_ADMISSION_CONSUMPTION_V1",
            "authority_class": "SYNTHETIC_QA" if _qa else "OWNER_OPERATIONAL_SCOPE_NOT_VENUE_LICENSE",
            "grant_sha256": digest(g),
            "access_sha256": access_hash,
            "source_sha256": source_hash(),
            "policy_sha256": POLICY_HASH,
            "session": g["session"],
            "grant": g,
            "access": self.access,
            "evidence": {
                k: load_json(Path(access_path).parent / self.access[k]["path"])
                for k in ["eligibility", "advisory_use_and_cache", "holdout_exclusions"]
            },
            "reservation_db": str(dbpath),
            "consumed_before_network": True,
            "exchange_legal_approval_claimed": False,
        }

    def check(self, route, params):
        g = self.grant
        n = self.clock.sample()
        need(
            n["boot_session_id"] == g["boot_id"]
            and g["not_before_qpc_ms"] <= n["qpc_before_ms"] <= n["qpc_after_ms"] < g["not_after_qpc_ms"],
            "OWNER_WINDOW_EXPIRED",
        )
        need(route in ALLOWED_ROUTES, "ROUTE_NOT_ALLOWED")
        if route.endswith("klines"):
            need(
                set(params) == {"symbol", "interval", "startTime", "endTime", "limit"}
                and params["symbol"] in POLICY["symbols"]
                and params["interval"] in ["1d", "4h", "1h"],
                "KLINE_SCOPE",
            )
            need(
                type(params["startTime"]) is int
                and type(params["endTime"]) is int
                and params["startTime"] < params["endTime"]
                and not any(
                    params["startTime"] < hi and params["endTime"] + 1 > lo for lo, hi in self.exclusions
                ),
                "REQUEST_EXCLUDED_DATE",
            )
            need(
                type(params["limit"]) is int
                and 0 < params["limit"] <= {"1d": 80, "4h": 100, "1h": 72}[params["interval"]],
                "ROLLING_LIMIT",
            )
        else:
            need(not params, "QUERY_SCOPE")
