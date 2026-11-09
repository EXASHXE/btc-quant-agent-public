"""Manual finite public REST scans; no account connectivity or automatic polling."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import uuid

from ..mvp.cli import operator_view
from ..native.runtime import exclusive
from .models import Access, POLICY, POLICY_HASH, PUBLIC, ensure, path_guard
from .source import Collector
from .store import Store


def doctor(access=None):
    try:
        ensure(access is not None, "LIVE_ACCESS_REGION_AND_HOLDOUT_METADATA_REQUIRED")
        config, _ = Access.load(access)
        status, reason = "OPERATIONAL_ACCESS_RECORD_VERIFIED_NOT_NETWORK_TESTED", None
        region = config.region
    except (ValueError, KeyError, OSError) as error:
        status, reason, region = "LIVE_SOURCE_UNAVAILABLE", str(error), "UNKNOWN"
    return {
        "evidence_class": PUBLIC,
        "status": status,
        "reason": reason,
        "region": region,
        "policy_sha256": POLICY_HASH,
        "policy": POLICY,
        "strict_owner_auditor_or_native_clock_required_for_J": False,
        "independent_applicable_access_and_usage_eligibility_required": True,
        "LIVE_ADAPTER_IMPLEMENTED": True,
        "LIVE_MARKET_ACCESS_VERIFIED": False,
        "SOURCE_QUALIFIED": False,
        "ECONOMICALLY_VALIDATED": False,
        "account": "ACCOUNT_UNKNOWN/ACCOUNT_VETO",
        "requests_made_by_doctor": 0,
        "environment_proxy_variables": "IGNORED_EXPLICIT_APPROVED_PROXY_ONLY",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(prog="quant live", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("doctor")
    d.add_argument("--access", type=Path)
    d.add_argument(
        "--review-policy",
        choices=("J_OPERATIONAL_POLICY_V1", "J_SWING_MANUAL_REVIEW_V2", "O_EXPLORATORY_VENUE_CLOCK_V1"),
    )
    for name in (
        "scan",
        "observe",
        "status",
        "opportunities",
        "episodes",
        "dashboard",
        "evaluate",
        "recover",
    ):
        p = sub.add_parser(name)
        p.add_argument("--output", type=Path, default=Path("artifacts/live"))
        if name in ("scan", "observe"):
            p.add_argument("--access", type=Path)
            p.add_argument("--grace-seconds", type=int, default=120)
            p.add_argument("--fresh-seconds", type=int, default=120)
            p.add_argument("--holding-hours", type=int, default=24)
            p.add_argument(
                "--review-policy",
                choices=(
                    "J_OPERATIONAL_POLICY_V1",
                    "J_SWING_MANUAL_REVIEW_V2",
                    "O_EXPLORATORY_VENUE_CLOCK_V1",
                ),
            )
            p.add_argument("--review-window-minutes", type=int)
        if name == "evaluate":
            p.add_argument("--report-output", type=Path)
    args = parser.parse_args(argv)
    exit_code = 0
    try:
        if args.command == "doctor":
            result = doctor(args.access)
            if args.review_policy == "O_EXPLORATORY_VENUE_CLOCK_V1":
                from .operational_clock import CONTRACT, HASH

                result.update(operational_time_policy=CONTRACT, operational_time_policy_sha256=HASH)
            if args.review_policy == "J_SWING_MANUAL_REVIEW_V2":
                from .swing_review import V2, V2_HASH

                result.update(manual_review_policy=V2, manual_review_policy_sha256=V2_HASH)
        else:
            output = path_guard(args.output)
            # Operational legal/access evidence is distinct from Strict cryptographic grants.
            if args.command in ("scan", "observe"):
                ensure(args.access is not None, "LIVE_ACCESS_REGION_AND_HOLDOUT_METADATA_REQUIRED")
                Access.load(args.access)
            output.parent.mkdir(parents=True, exist_ok=True)
            with exclusive(str(output) + ".live.worker.lock"):
                if args.command == "scan" and not output.exists():
                    store = Store(output, create=True, exposure=PUBLIC)
                else:
                    store = Store(output)
                from .swing_review import SwingCollector, SwingObservationCollector, SwingProduct

                from .operational_clock import (
                    OperationalCollector,
                    OperationalObserver,
                    OperationalProduct,
                    product_for as operational_product_for,
                )

                product = operational_product_for(
                    store, getattr(args, "review_policy", None), getattr(args, "review_window_minutes", None)
                )
                if args.command in ("scan", "observe"):
                    if args.command == "observe":
                        ensure(
                            any(d.episode_id for d in product.decisions()),
                            "LIVE_NO_FROZEN_EPISODE_TO_OBSERVE",
                        )
                    collector = SwingCollector if isinstance(product, SwingProduct) else Collector
                    if isinstance(product, SwingProduct) and args.command == "observe":
                        collector = SwingObservationCollector
                    if isinstance(product, OperationalProduct):
                        collector = OperationalObserver if args.command == "observe" else OperationalCollector
                    snap = collector(
                        store,
                        args.access,
                        grace_ms=args.grace_seconds * 1000,
                        max_age_ms=args.fresh_seconds * 1000,
                    ).run()
                    if args.command == "scan":
                        values = [product.review(s, args.holding_hours) for s in POLICY["symbols"]]
                        states = [
                            d.market_state if hasattr(d, "market_state") else d["status"] for d in values
                        ]
                        admitted = all(
                            hasattr(d, "market_state") and d.market_state in ("ARMED", "WATCH", "NO_SETUP")
                            for d in values
                        )
                        result = {
                            "status": "LIVE_MANUAL_REVIEW_VERIFIED"
                            if admitted
                            else "LIVE_WARMUP_COMPLETE_REVIEW_BLOCKED",
                            "states": dict(zip(POLICY["symbols"], states)),
                            "decisions": [
                                d.model_dump(mode="json") if hasattr(d, "model_dump") else d for d in values
                            ],
                        }
                        exit_code = 0 if admitted else 2
                    else:
                        values = [product.observe(d.episode_id) for d in product.decisions() if d.episode_id]
                        result = {"status": "LIVE_MANUAL_OBSERVATIONS_APPENDED", "observations": values}
                    result.update(
                        evidence_class=snap["exposure"],
                        requests=snap["requests"],
                        request_weight=snap["request_weight"],
                        source_bounds=snap["source_bounds"],
                        clock=snap["clock"],
                        **product.dashboard(),
                    )
                elif args.command == "dashboard":
                    result = product.dashboard()
                elif args.command == "recover":
                    result = {"abandoned_sessions": store.recover(), **product.dashboard()}
                elif args.command == "evaluate":
                    report = args.report_output or output / ("evaluation-" + uuid.uuid4().hex)
                    result = product.evaluate(report)
                elif args.command == "episodes":
                    result = {
                        "episodes": [
                            product.episode(d.episode_id) for d in product.decisions() if d.episode_id
                        ]
                    }
                elif args.command == "opportunities":
                    result = {
                        "decisions": [d.model_dump(mode="json") for d in product.decisions()],
                        "current_source_status": {
                            k: v for k, v in product.source.assess().items() if k != "records"
                        },
                    }
                else:
                    result = product.snapshot()
        result.update(
            strict_source_qualified=False,
            strict_shadow_qualified=False,
            economically_validated=False,
            account="ACCOUNT_UNKNOWN/ACCOUNT_VETO",
            S2="RESEARCH_ONLY_DISABLED",
            S3="RESEARCH_ONLY_DISABLED",
        )
        print(json.dumps(operator_view(result), sort_keys=True, default=str))
        return exit_code
    except (ValueError, OSError, KeyError, StopIteration) as error:
        print(
            json.dumps(
                {
                    "status": getattr(error, "status", "LIVE_SOURCE_UNAVAILABLE"),
                    "reason": str(error),
                    "new_candidates": "SOURCE_BLOCKED",
                    "no_synthetic_fallback": True,
                    "source_qualified": False,
                    "account": "ACCOUNT_UNKNOWN/ACCOUNT_VETO",
                },
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
