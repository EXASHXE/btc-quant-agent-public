"""Read-only admission inspection and manually initiated qualified native product review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..native.contract import strict, source_hash
from ..native.journal import Journal
from ..native.runtime import exclusive
from .evidence import Ledger, PlanEnvelope, SCHEMA_HASH
from .source import Qualification
from .product import Product


def main(argv=None):
    parser = argparse.ArgumentParser(prog="quant-qualification")
    tasks = parser.add_subparsers(dest="command", required=True)
    tasks.add_parser("doctor")
    for name in (
        "register-plan",
        "attach-audit",
        "attach-host",
        "assess",
        "review",
        "observe",
        "dashboard",
        "export",
    ):
        p = tasks.add_parser(name)
        p.add_argument("--registry", type=Path, required=True)
        p.add_argument("--ledger", type=Path, required=True)
        if name == "register-plan":
            p.add_argument("--owner", type=Path, required=True)
            p.add_argument("--auditor", type=Path, required=True)
        if name in ("attach-audit", "attach-host"):
            p.add_argument("--signature", type=Path, required=True)
        if name == "attach-host":
            p.add_argument("--session", required=True)
        if name in ("assess", "review", "observe"):
            p.add_argument("--asof-ms", type=int, required=True)
        if name in ("review", "observe", "dashboard", "export"):
            p.add_argument("--shadow", type=Path, required=True)
        if name == "review":
            p.add_argument("--symbol", choices=("BTCUSDT", "ETHUSDT", "SOLUSDT"), required=True)
            p.add_argument("--trigger-ms", type=int, required=True)
        if name == "observe":
            p.add_argument("--episode", required=True)
        if name in ("dashboard", "export"):
            p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        roots = strict((Path(__file__).parents[1] / "native/authority_roots.json").read_bytes())
        schema = strict((Path(__file__).parent / "roots.json").read_bytes())
        if args.command == "doctor":
            result = {
                "status": "BLOCKED_EXTERNAL_AUTHORITY",
                "host_clock": "HOST_CLOCK_UNQUALIFIED",
                "Owner_keys": len(roots["owner"]),
                "auditor_keys": len(roots["auditor"]),
                "schema_sha256": SCHEMA_HASH,
                "schema_accepted": schema["accepted_product_schema_sha256"] == SCHEMA_HASH,
                "source_sha256": source_hash(),
                "source_qualified": False,
                "shadow_qualified": False,
                "account": "ACCOUNT_UNKNOWN/ACCOUNT_VETO",
                "economic_validation": False,
                "native_requests": 0,
            }
        else:
            if not args.registry.is_file():
                raise ValueError("NATIVE_REGISTRY_REQUIRED")
            with exclusive(str(args.registry) + ".worker.lock"):
                journal = Journal(args.registry)
                ledger = Ledger(args.ledger)
                qualification = Qualification(journal, ledger)
                if args.command == "register-plan":
                    result = {
                        "hash": ledger.register(
                            PlanEnvelope.model_validate(strict(args.owner.read_bytes())),
                            PlanEnvelope.model_validate(strict(args.auditor.read_bytes())),
                            roots,
                        )
                    }
                elif args.command == "attach-audit":
                    from .evidence import TimedAuditEnvelope

                    result = {
                        "hash": ledger.attach_audit(
                            journal,
                            TimedAuditEnvelope.model_validate(strict(args.signature.read_bytes())),
                            roots,
                        )
                    }
                elif args.command == "attach-host":
                    from .admission import HostEnvelope

                    result = {
                        "hash": ledger.attach_host(
                            journal,
                            args.session,
                            HostEnvelope.model_validate(strict(args.signature.read_bytes())),
                            roots,
                        )
                    }
                elif args.command == "assess":
                    result = {k: v for k, v in qualification.assess(args.asof_ms).items() if k != "records"}
                else:
                    product = Product(qualification, args.shadow)
                    if args.command == "review":
                        result = product.review(args.symbol, args.trigger_ms, args.asof_ms).model_dump(
                            mode="json"
                        )
                    elif args.command == "observe":
                        result = product.observe(args.episode, args.asof_ms).model_dump(mode="json")
                    elif args.command == "dashboard":
                        result = product.dashboard(args.output)
                    else:
                        product.export_c(args.output)
                        result = {"output": str(args.output), "scientific_decision": "INSUFFICIENT_SUPPORT"}
        print(json.dumps(result, sort_keys=True, default=str))
        return 0
    except (ValueError, OSError, KeyError) as exc:
        print(json.dumps({"status": "SOURCE_BLOCKED", "reason": str(exc), "native_requests": 0}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
