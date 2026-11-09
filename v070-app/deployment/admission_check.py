"""Durable, no-socket authority intake for the existing quant-native launcher."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

from btc_quant_agent.platform import native
from btc_quant_agent.platform.native.clock import Clock
from btc_quant_agent.platform.native.contract import (
    Envelope,
    AuditEnvelope,
    Policy,
    authorize,
    require,
    source_hash,
    strict,
)
from btc_quant_agent.platform.qualification.admission import HostEnvelope
from deployment.host_check import compatibility, durable_json, signed_host


def rights_scope(dossier, grant):
    require(dossier.get("schema") == "G_INDEPENDENT_RIGHTS_DOSSIER_V1", "RIGHTS_DOSSIER_SCHEMA")
    require(
        dossier.get("independent_reference") and dossier.get("venue") == grant.venue,
        "INDEPENDENT_RIGHTS_REFERENCE_REQUIRED",
    )
    for field in (
        "venue_eligibility",
        "region_eligibility",
        "public_access",
        "noncommercial_research",
        "prospective_capture",
        "local_cache",
        "retention",
    ):
        require(dossier.get(field) == "INDEPENDENTLY_ESTABLISHED", "RIGHTS_UNVERIFIED:" + field)
    require(
        set(dossier.get("endpoints", [])) == {grant.endpoint, grant.clock_endpoint}, "RIGHTS_ENDPOINT_SCOPE"
    )
    require(set(grant.streams) <= set(dossier.get("streams", [])), "RIGHTS_STREAM_SCOPE")
    require(
        type(dossier.get("retention_seconds_max")) is int
        and 0 < grant.retention_seconds <= dossier["retention_seconds_max"],
        "RIGHTS_RETENTION_SCOPE",
    )
    return {
        "status": "SIGNED_PINNED_DOSSIER_SCOPE_MATCH",
        "historical_backfill": "NOT_AUTHORIZED_BY_THIS_PATH",
    }


def check(args):
    compatibility()
    roots = strict((Path(native.__file__).parent / "authority_roots.json").read_bytes())
    require(roots.get("owner") and roots.get("auditor"), "INDEPENDENT_TRUST_REQUIRED")
    envelope = Envelope.model_validate(strict(args.grant.read_bytes()))
    audit = AuditEnvelope.model_validate(strict(args.audit.read_bytes()))
    policy = Policy.model_validate(strict(args.config.read_bytes()))
    current = Clock().sample()
    grant = authorize(
        envelope,
        audit,
        roots,
        policy,
        source_hash=source_hash(),
        executable_hash=hashlib.sha256(args.wheel.read_bytes()).hexdigest(),
        now_ms=current["wall_ms"],
        exposure="NATIVE_UNQUALIFIED",
    )
    raw = args.rights.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == grant.rights_sha256, "PINNED_RIGHTS_BYTES_MISMATCH")
    rights = rights_scope(strict(raw), grant)
    host = signed_host(
        HostEnvelope.model_validate(strict(args.host_certificate.read_bytes())), grant, args.wheel, current
    )
    output = Path(grant.output)
    require(
        not output.exists() and not any(p.is_symlink() for p in (output, *output.absolute().parents)),
        "UNUSED_TRUSTED_OUTPUT_REQUIRED",
    )
    require(output.parent.is_dir(), "OUTPUT_PARENT_REQUIRED")
    require(
        shutil.disk_usage(output.parent).free > grant.storage_bytes_max + 268435456,
        "STORAGE_RESERVATION_UNCERTAIN",
    )
    if args.registry.exists():
        require(args.registry.is_file() and not args.registry.is_symlink(), "REGISTRY_UNTRUSTED")
        with sqlite3.connect("file:" + str(args.registry.absolute()) + "?mode=ro", uri=True) as db:
            require(
                db.execute(
                    "SELECT count(*) FROM sessions WHERE id=? OR output=?", (grant.session_id, grant.output)
                ).fetchone()[0]
                == 0,
                "SESSION_OR_OUTPUT_CONSUMED",
            )
    return {
        "status": "AUTHORITY_PREFLIGHT_ONLY_RUNTIME_ENFORCEMENT_REQUIRED",
        "rights": rights,
        "clock": host,
        "session_id": grant.session_id,
        "window_ms": [grant.start_ms, grant.end_ms],
        "reservation_created": False,
        "actual_TLS_queue_budget_terminal_checks": "REQUIRED_IN_EXISTING_RUNTIME",
        "clock_freshness": "RECHECK_ON_LAUNCH",
        "single_use_replay": "NO_RETRY",
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("grant", "audit", "config", "wheel", "rights", "host-certificate", "registry", "report"):
        p.add_argument("--" + name, type=Path, required=True)
    args = p.parse_args(argv)
    value: dict = {
        "schema": "G_NO_SOCKET_ADMISSION_V1",
        "status": "BLOCKED_EXTERNAL_AUTHORITY",
        "native_connections": 0,
        "native_requests": 0,
        "capture_started": False,
    }
    try:
        value.update(check(args))
    except (ValueError, OSError, KeyError, sqlite3.Error) as exc:
        value["reason"] = str(exc)
    try:
        durable_json(args.report, value)
    except OSError as exc:
        value.update(status="FAILED_DURABLE_ADMISSION_REPORT", report_error=str(exc))
    print(json.dumps(value, sort_keys=True))
    return 0 if value["status"] == "AUTHORITY_PREFLIGHT_ONLY_RUNTIME_ENFORCEMENT_REQUIRED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
