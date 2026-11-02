"""Local canary policy inspection and fabricated replay; no activation command."""

from pathlib import Path

from .policy import ROOT, load_catalog, load_policy
from .runtime import demo, preflight


def configure(commands):
    sub = commands.add_parser(
        "canary", help="Offline source admission; real transport disabled"
    ).add_subparsers(dest="operation", required=True)
    for name in ("matrix", "preflight", "demo"):
        p = sub.add_parser(name)
        p.add_argument("--config", default=str(ROOT / "configs/canary/offline.yaml"))
        p.add_argument("--catalog", default=str(ROOT / "configs/canary/endpoints.json"))
        p.add_argument("--output", default="artifacts/canary-demo")
        p.add_argument("--data", choices=["synthetic"], default="synthetic")


def execute(args):
    policy, catalog = load_policy(args.config), load_catalog(args.catalog)
    if args.operation == "matrix":
        return {"endpoints": list(catalog.values()), **preflight(policy, catalog, args.output)}
    if args.operation == "preflight":
        return preflight(policy, catalog, args.output)
    r = demo(policy, catalog, Path(args.output))
    return {
        "status": r["status"],
        "json": str(Path(args.output) / "report.json"),
        "html": str(Path(args.output) / "report.html"),
        "finalization": r["finalization"],
        "decoded_completed_5m_bars": r["decoded_completed_5m_bars"],
    }
