"""One manual local advisory workflow. Never acquires data or accesses accounts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..native.contract import strict
from ..native.runtime import exclusive
from .models import Dataset, POLICY, CONTRACT_HASH
from .source import Source, checked_output
from .product import Product


def checked_input(path):
    path = Path(path)
    parts = [x.lower() for x in path.resolve().parts]
    if any(
        "holdout" in x
        or x.startswith("l4-")
        or (x.startswith("lt-program-") and x != "lt-program-h-exploratory-mvp-01")
        for x in parts
    ):
        raise ValueError("MVP_PROTECTED_OR_ORIGINAL_WORKSPACE_DATA_READ_FORBIDDEN")
    if any(x.is_symlink() for x in (path, *path.absolute().parents)) or path.stat().st_size > 33554432:
        raise ValueError("MVP_DATASET_UNTRUSTED_OR_TOO_LARGE")
    return path


def read_dataset(path):
    return Dataset.model_validate(strict(checked_input(path).read_bytes()))


def strict_main(argv):
    if not argv or argv[0] == "doctor":
        from ..qualification.cli import main as original
        from contextlib import redirect_stdout
        from io import StringIO

        buffer = StringIO()
        with redirect_stdout(buffer):
            code = original(["doctor"])
        value = json.loads(buffer.getvalue())
        value["mode"] = "STRICT_RESEARCH"
        value["acceptance_contract"] = "UNCHANGED_F_NATIVE_RESEARCH_GATES"
        print(json.dumps(value, sort_keys=True))
        return code
    if argv[0] == "native":
        from ..native.cli import main as original
    elif argv[0] == "qualification":
        from ..qualification.cli import main as original
    else:
        raise ValueError("STRICT_RESEARCH_REQUIRES_NATIVE_OR_QUALIFICATION_ENTRYPOINT")
    return original(argv[1:])


def operator_view(value):
    if isinstance(value, dict):
        return {
            k: (
                {"retained_records": len(v), "location": "mvp.sqlite and dashboard/latest.json"}
                if k in ("admitted_prefix", "receipt_ids", "future_receipt_ids")
                else operator_view(v)
            )
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [operator_view(v) for v in value]
    return value


def main(argv=None):
    p = argparse.ArgumentParser(prog="quant mvp", description=__doc__)
    commands = p.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor")
    commands.add_parser("limitations")
    for name in (
        "init",
        "demo",
        "import",
        "review",
        "status",
        "episodes",
        "observe",
        "dashboard",
        "evaluate",
        "reconcile",
        "clock-check",
        "demo-followup",
        "recover",
    ):
        task = commands.add_parser(name)
        task.add_argument("--output", type=Path, required=True)
        if name in ("init", "demo"):
            task.add_argument("--grace-seconds", type=int, default=120)
        if name == "demo":
            task.add_argument(
                "--scenario",
                choices=("positive", "all-no-setup", "clock-reconciled", "clock-blocked"),
                default="positive",
            )
        if name in ("import", "reconcile"):
            task.add_argument("--dataset", type=Path, required=True)
            task.add_argument("--permission", type=Path)
        if name == "review":
            task.add_argument("--symbol", choices=("BTCUSDT", "ETHUSDT", "SOLUSDT", "ALL"), default="ALL")
            task.add_argument("--holding-hours", type=int, default=24)
        if name == "observe":
            task.add_argument("--episode-id", required=True)
        if name == "evaluate":
            task.add_argument("--report-output", type=Path, required=True)
    args = p.parse_args(argv)
    try:
        if args.command in ("doctor", "limitations"):
            value = {
                "mode": "EXPLORATORY_MVP",
                "status": "H_EXPLORATORY_MVP_OFFLINE_READY",
                "current_market_data": "MVP_DATA_NOT_READY",
                "contract_sha256": CONTRACT_HASH,
                "policy": POLICY,
                "strict_research": "UNCHANGED; use quant strict native/qualification",
                "source_qualified": False,
                "shadow_qualified": False,
                "economically_validated": False,
                "native_market_requests": 0,
            }
        elif args.command == "demo":
            from .demo import run

            value = run(args.output, args.scenario, args.grace_seconds * 1000)
        else:
            checked_output(args.output)
            lock = str(args.output.absolute()) + ".mvp.worker.lock"
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with exclusive(lock):
                source = Source(
                    args.output,
                    create=args.command == "init",
                    grace_ms=getattr(args, "grace_seconds", 120) * 1000,
                )
                product = Product(source)
                if args.command == "init":
                    value = {"status": "MVP_DATA_NOT_READY", "mode": "EXPLORATORY_MVP"}
                elif args.command in ("import", "reconcile"):
                    data = read_dataset(args.dataset)
                    permit = strict(checked_input(args.permission).read_bytes()) if args.permission else None
                    value = (
                        source.ingest(data, permit)
                        if args.command == "import"
                        else source.reconcile(data, permit)
                    )
                elif args.command == "review":
                    symbols = ("BTCUSDT", "ETHUSDT", "SOLUSDT") if args.symbol == "ALL" else (args.symbol,)
                    values = [product.review(s, args.holding_hours) for s in symbols]
                    value = {
                        "mode": "EXPLORATORY_MVP",
                        "decisions": [
                            d.model_dump(mode="json") if hasattr(d, "model_dump") else d for d in values
                        ],
                        **product.dashboard(),
                    }
                elif args.command == "observe":
                    value = product.observe(args.episode_id)
                    product.dashboard()
                elif args.command == "demo-followup":
                    from .demo import followup

                    value = followup(source)
                elif args.command == "recover":
                    known = {v["dataset_id"] for v in source.imports()}
                    recovered = [
                        source.ingest(Dataset.model_validate(e["dataset"]), e["permissions"])
                        for key, e in source.datasets().items()
                        if key not in known
                    ]
                    value = {"recovered": recovered, **product.dashboard()}
                elif args.command == "dashboard":
                    value = product.dashboard()
                elif args.command == "evaluate":
                    value = product.evaluate(args.report_output)
                elif args.command == "episodes":
                    value = {
                        "mode": "EXPLORATORY_MVP",
                        "episodes": [
                            product.episode(d.episode_id) for d in product.decisions() if d.episode_id
                        ],
                    }
                elif args.command == "clock-check":
                    value = source.clock(source.sample())
                else:
                    value = product.snapshot()
        print(json.dumps(operator_view(value), sort_keys=True, default=str))
        return 2 if args.command == "review" and value.get("data_status") == "MVP_DATA_NOT_READY" else 0
    except (ValueError, OSError, KeyError, StopIteration) as exc:
        print(
            json.dumps(
                {
                    "mode": "EXPLORATORY_MVP",
                    "status": "MVP_DATA_NOT_READY",
                    "reason": str(exc),
                    "source_qualified": False,
                    "native_market_requests": 0,
                }
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
