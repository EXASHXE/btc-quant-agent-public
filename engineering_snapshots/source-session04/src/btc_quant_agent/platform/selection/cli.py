"""Offline-only selector CLI integrated into quant."""

from pathlib import Path
import json

from ..core import InstrumentSpec, UserReportedFill, dec, primitive
from ..position_management import supervise
from .fixtures import market_event, monitor
from .lifecycle import record_user_fill
from .management import ExitPolicy
from .evaluation import evaluate
from .fixtures import BASE, history, structural_bars
from .selector import load_policy, scan
from .sources import STRUCTURE
from .store import SelectorStore


def configure(commands):
    selector = commands.add_parser(
        "selector", help="Offline deterministic V1 selector and episode evaluation"
    )
    sub = selector.add_subparsers(dest="operation", required=True)
    for name in ("scan", "evaluate", "validate"):
        p = sub.add_parser(name)
        p.add_argument("--config", default="configs/selector/v1.yaml")
        p.add_argument("--data", choices=["synthetic"], default="synthetic")
        p.add_argument("--output", default="artifacts/selector")
    p = sub.add_parser("report-fill", help="Bind an explicit user report to an isolated episode; no order")
    p.add_argument("--store", required=True)
    p.add_argument("--episode", required=True)
    p.add_argument("--file", required=True)
    p = sub.add_parser(
        "position-replay", help="Synthetic observations against a user-reported ledger position"
    )
    p.add_argument("--store", required=True)
    p.add_argument("--episode", required=True)
    p.add_argument("--position", required=True)
    p.add_argument("--minute", type=int, default=4)
    p.add_argument("--scenario", choices=["normal", "gap"], default="normal")


def execute(args):
    if args.operation in {"report-fill", "position-replay"}:
        store = SelectorStore(args.store)
        anchors = store.episode(args.episode)["anchors"]
        if args.operation == "report-fill":
            raw = json.loads(Path(args.file).read_text())
            for key in ("price", "quantity"):
                raw[key] = dec(raw[key])
            position, evidence = record_user_fill(
                store, args.episode, UserReportedFill(**raw), InstrumentSpec(**anchors["contract"])
            )
            return {
                "position": primitive(position),
                "report_evidence": evidence,
                "source_context": "ISOLATED_OFFLINE_LEDGER; no account confirmation",
            }
        m = monitor(anchors, args.minute, mode=args.scenario)
        position = store.position(args.position)
        return {
            "source_context": "SYNTHETIC_OBSERVATIONS",
            "position_source": position.source,
            "recommendation": primitive(
                supervise(
                    position,
                    market_event(m),
                    episode_policy=ExitPolicy(
                        atr=anchors["atr"], target=dec(anchors["target"]) if anchors["target"] else None
                    ),
                )
            ),
            "actual_position_status": store.position(args.position).status,
        }
    policy = load_policy(args.config)
    if args.operation == "validate":
        return {
            "status": "VALID",
            "policy_hash": policy.hash,
            "source_activation": "BLOCKED_PENDING_OWNER_AUTH",
        }
    output = Path(args.output)
    if args.operation == "evaluate":
        if (output / "episodes.json").exists() or (output / "scan.sqlite").exists():
            raise ValueError(
                "EVALUATION_OUTPUT_EXISTS: choose a new output directory; evidence is never overwritten"
            )
        report = evaluate(policy, output)
        return {
            "source": report["source"],
            "funnel": report["funnel"],
            "config_hash": policy.hash,
            "json": str(output / "episodes.json"),
            "html": str(output / "episodes.html"),
        }
    output.mkdir(parents=True, exist_ok=True)
    store = SelectorStore(output / "scan.sqlite")
    bars = structural_bars(symbols=tuple(sorted(policy.symbols)))
    if all(store.regime(s)["cutoff"] < BASE + 304 * STRUCTURE for s in policy.symbols):
        scan(history(bars, BASE + 304 * STRUCTURE, policy), store, policy)
    result = scan(history(bars, BASE + 305 * STRUCTURE, policy), store, policy)
    return primitive(result)
