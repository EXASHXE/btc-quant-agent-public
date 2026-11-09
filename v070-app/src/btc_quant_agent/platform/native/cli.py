"""Finite native launcher; missing genuine authority exits before any network."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .contract import source_hash, strict
from .journal import Journal
from .runtime import exclusive, run_native


def main(argv=None):
    parser = argparse.ArgumentParser(prog="quant-native", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor")
    cap = commands.add_parser("capture")
    cap.add_argument("--host-admission",type=Path)
    for name in ("grant", "audit", "config", "wheel", "registry"):
        cap.add_argument("--" + name, type=Path, required=True)
    for name in ("inspect", "recover", "audit-challenge", "verify-audit"):
        task = commands.add_parser(name)
        task.add_argument("--registry", type=Path, required=True)
        if name != "recover":
            task.add_argument("--session", required=True)
        if name == "verify-audit":
            task.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            roots = strict((Path(__file__).parent / "authority_roots.json").read_bytes())
            value = {
                "status": "NATIVE_BLOCKED_AUTHORITY"
                if not roots["owner"] or not roots["auditor"]
                else "EXTERNAL_GRANT_REQUIRED",
                "source_sha256": source_hash(),
                "owner_keys": len(roots["owner"]),
                "auditor_keys": len(roots["auditor"]),
                "native_market_requests": 0,
                "source_qualified": False,
                "shadow_qualified": False,
                "account": "ACCOUNT_UNKNOWN/ACCOUNT_VETO",
                "economically_validated": False,
            }
        elif args.command == "capture":
            value = run_native(args.grant, args.audit, args.config, args.wheel, args.registry, args.host_admission)
        else:
            if not args.registry.is_file():
                raise ValueError("REGISTRY_MISSING")
            with exclusive(str(args.registry) + ".worker.lock"):
                journal = Journal(args.registry)
                if args.command in ("audit-challenge", "verify-audit"):
                    from .audit import challenge, verify_capture_audit, CaptureAuditEnvelope

                    if args.command == "audit-challenge":
                        value = challenge(journal, args.session)
                    else:
                        roots = strict((Path(__file__).parent / "authority_roots.json").read_bytes())
                        envelope = CaptureAuditEnvelope.model_validate(strict(args.audit.read_bytes()))
                        value = verify_capture_audit(journal, args.session, envelope, roots)
                    print(json.dumps(value, sort_keys=True))
                    return 0
                value = (
                    journal.recover()
                    if args.command == "recover"
                    else {
                        "integrity": journal.verify(),
                        "usage": journal.usage(args.session),
                        "completed": len(journal.records(args.session)),
                    }
                )
        print(json.dumps(value, sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError) as exc:
        print(
            json.dumps(
                {
                    "status": "FAIL_CLOSED_NATIVE_NOT_STARTED_OR_STOPPED",
                    "reason": str(exc),
                    "qualification": "NOT_GRANTED",
                },
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
