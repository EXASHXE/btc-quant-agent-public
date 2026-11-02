"""Offline CLI. No exchange/order/collector command exists in this extension."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from .config import load_config
from .core import InstrumentSpec, UserReportedFill, dec, primitive


def output(value):
    print(json.dumps(primitive(value), indent=2, sort_keys=True, allow_nan=False))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="quant", description="Quant 0.7 synthetic research and read-only advisory"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    from .canary.cli import configure as configure_canary

    configure_canary(commands)
    from .bridge.cli import configure as configure_bridge

    configure_bridge(commands)
    from .selection.cli import configure as configure_selector

    configure_selector(commands)
    for name in ("factors", "strategies"):
        sub = commands.add_parser(name).add_subparsers(dest="operation", required=True)
        sub.add_parser("list")
        sub.add_parser("inspect").add_argument("id")
    configs = commands.add_parser("configs").add_subparsers(dest="operation", required=True)
    configs.add_parser("validate").add_argument("path")
    backtest = commands.add_parser("backtest").add_subparsers(dest="operation", required=True)
    p = backtest.add_parser("run")
    p.add_argument("--config", required=True)
    p.add_argument("--data", choices=["synthetic"], default="synthetic")
    p.add_argument("--output", default="artifacts/runs")
    p = backtest.add_parser("compare")
    p.add_argument("--suite", required=True)
    p.add_argument("--data", choices=["synthetic"], default="synthetic")
    p.add_argument("--output", default="artifacts/comparison")
    research = commands.add_parser("research").add_subparsers(dest="operation", required=True)
    for operation in ("factors", "walk-forward", "search", "portfolio", "attribution"):
        p = research.add_parser(operation)
        p.add_argument("--config", required=True)
        p.add_argument("--data", choices=["synthetic"], default="synthetic")
        p.add_argument("--output", default="artifacts/experiments")
        if operation == "search":
            p.add_argument("--space", required=True)
            p.add_argument("--method", choices=["grid", "random"], default="grid")
            p.add_argument("--max-trials", type=int, default=12)
    p = commands.add_parser("train")
    p.add_argument("--config", required=True)
    p.add_argument("--data", choices=["synthetic"], default="synthetic")
    p.add_argument("--output", default="artifacts/models")
    models = commands.add_parser("models").add_subparsers(dest="operation", required=True)
    p = models.add_parser("list")
    p.add_argument("--path", default="artifacts/models")
    advisory = commands.add_parser("advisory").add_subparsers(dest="operation", required=True)
    p = advisory.add_parser("scan")
    p.add_argument("--config", required=True)
    p.add_argument("--data", choices=["synthetic"], default="synthetic")
    p.add_argument("--bar", type=int, default=-1)
    p.add_argument("--store", default="artifacts/advisory.sqlite")
    p = advisory.add_parser("replay")
    p.add_argument("--scenario", default="all")
    p.add_argument("--output", default="artifacts/demos")
    positions = commands.add_parser("positions").add_subparsers(dest="operation", required=True)
    for operation in ("report-fill", "show", "amend-stop", "manage"):
        p = positions.add_parser(operation)
        p.add_argument("--store", default="artifacts/user_positions.sqlite")
        if operation == "report-fill":
            p.add_argument("--file", required=True)
        else:
            p.add_argument("--id", required=True)
        if operation in ("amend-stop", "manage"):
            p.add_argument("--config", required=True)
        if operation == "amend-stop":
            p.add_argument("--stop", required=True)
            p.add_argument("--expected-version", type=int, required=True)
            p.add_argument("--user-action-ts", type=int, required=True)
        if operation == "manage":
            p.add_argument("--bar", type=int, default=-1)
    p = commands.add_parser("report")
    p.add_argument("run_id")
    p.add_argument("--path", default="artifacts/runs")
    p = commands.add_parser("demo")
    p.add_argument("scenario", nargs="?", default="all")
    p.add_argument("--output", default="artifacts/demos")
    p = commands.add_parser("ui")
    p.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    try:
        execute(args)
    except (ValueError, KeyError, RuntimeError, FileNotFoundError) as exc:
        parser.exit(2, f"quant: {exc}\n")


def execute(args):
    from .reporting import save_run, source_identity, write_json

    if args.command == "canary":
        from .canary.cli import execute as execute_canary

        output(execute_canary(args))
        return

    if args.command == "selector":
        from .selection.cli import execute as execute_selector

        output(execute_selector(args))
        return

    if args.command == "bridge":
        from .bridge.cli import execute as execute_bridge

        output(execute_bridge(args))
    elif args.command in ("factors", "strategies"):
        from .factors import REGISTRY as factors
        from .strategies import REGISTRY as strategies

        registry = factors if args.command == "factors" else strategies
        if args.operation == "list":
            output(list(registry.values()))
        else:
            output(registry[args.id.upper() if args.command == "factors" else args.id])
    elif args.command == "configs":
        config = load_config(args.path)
        output({"valid": True, "config_hash": config.hash})
    elif args.command == "backtest":
        if args.operation == "compare":
            from .reporting import compare

            path = Path(args.suite)
            raw = yaml.safe_load(path.read_text())
            if not isinstance(raw, dict) or set(raw) != {"configs"}:
                raise ValueError("suite must contain configs only")
            output(compare([load_config(path.parent / p) for p in raw["configs"]], args.output))
        else:
            config = load_config(args.config)
            from .strategies import REGISTRY

            if any(REGISTRY[s.id].status == "RESEARCH_ONLY" for s in config.strategies):
                from .portfolio_research import run

                result = run(config)
                write_json(Path(args.output) / (config.hash + ".json"), result)
                output(result["metrics"])
            else:
                from .backtest import run

                result = run(config, source_hash=source_identity())
                path = save_run(result, args.output)
                output({"path": str(path), "run": result["run"]})
    elif args.command == "research":
        from .research import factor_research, register_experiment, search, walk_forward

        config = load_config(args.config)
        if args.operation == "factors":
            result = factor_research(config, source_identity())
        elif args.operation == "walk-forward":
            result = {"folds": walk_forward(config)}
        elif args.operation == "search":
            result = search(
                config,
                yaml.safe_load(Path(args.space).read_text()),
                source_identity(),
                method=args.method,
                max_trials=args.max_trials,
            )
        elif args.operation == "attribution":
            from .research import policy_attribution

            result = policy_attribution(config, source_identity())
        else:
            from .portfolio_research import run

            result = run(config)
        receipt = register_experiment(result, config, args.output, source_identity())
        output(receipt)
    elif args.command == "train":
        from .ml import train

        output(train(load_config(args.config), args.output))
    elif args.command == "models":
        from .ml import ModelRegistry

        output(ModelRegistry(args.path).list())
    elif args.command == "advisory" and args.operation == "scan":
        from .advisory import gate, scan
        from .backtest import build_pipeline
        from .data import SyntheticProvider, histories

        config = load_config(args.config)
        events = SyntheticProvider().events(config)
        pipeline, indices = build_pipeline(events, config)
        batch = [group[args.bar] for group in histories(events).values()]
        candidates = scan(
            pipeline,
            batch,
            {e.spec.symbol: indices[e.spec.symbol][e.candle.close_time_ms] for e in batch},
            config,
        )
        by_symbol = {e.spec.symbol: e for e in batch}
        plans = [gate(c, by_symbol[c.symbol], config) for c in candidates]
        from .position_management import AdvisoryStore

        store = AdvisoryStore(args.store)
        receipts = []
        for plan in plans:
            identity = store.commit_decision(plan, plan.decision_ts, plan.decision_ts)
            event_id = store.prepare(identity, plan.candidate.symbol, plan.decision_ts)
            receipts.append(
                {
                    "decision_id": identity,
                    "event_id": event_id,
                    "notification_status": "PENDING; preview only",
                }
            )
        output(
            {
                "exposure": "SYNTHETIC",
                "candidates": candidates,
                "plans": plans,
                "persistence": receipts,
            }
        )
    elif args.command == "positions":
        from .position_management import AdvisoryStore

        store = AdvisoryStore(args.store)
        if args.operation == "show":
            output(store.position(args.id))
        elif args.operation in ("amend-stop", "manage"):
            from .data import SyntheticProvider, histories
            from .position_management import supervise

            config = load_config(args.config)
            position = store.position(args.id)
            events = SyntheticProvider().events(config)
            group = histories(events)[position.symbol]
            event = group[args.bar] if args.operation == "manage" else group[-1]
            if args.operation == "amend-stop":
                output(
                    store.amend_stop(
                        args.id,
                        dec(args.stop),
                        event.spec,
                        args.user_action_ts,
                        expected_version=args.expected_version,
                    )
                )
            else:
                from .backtest import build_pipeline

                pipeline, indices = build_pipeline(events, config)
                atr = pipeline.result(
                    position.symbol,
                    "ATR",
                    indices[position.symbol][event.candle.close_time_ms],
                    event.decision_ts,
                ).value
                action = supervise(position, event, atr=atr, policy=config.exits)
                identity = store.commit_decision(action, action.decision_ts, action.decision_ts)
                output(
                    {
                        "source": "SYNTHETIC",
                        "action": action,
                        "decision_id": identity,
                        "position_status": position.status,
                    }
                )
        else:
            raw = json.loads(Path(args.file).read_text())
            spec_raw = raw.pop("instrument")
            for k in ("tick_size", "quantity_step", "multiplier", "min_notional"):
                if k in spec_raw:
                    spec_raw[k] = dec(spec_raw[k])
            spec = InstrumentSpec(**spec_raw)
            stop = dec(raw.pop("stop")) if "stop" in raw else None
            for key in ("price", "quantity"):
                raw[key] = dec(raw[key])
            output(store.report(UserReportedFill(**raw), spec, stop=stop))
    elif args.command == "report":
        output(json.loads((Path(args.path) / args.run_id / "run.json").read_text()))
    elif args.command == "ui":
        from .ui import serve

        serve(args.port)
    else:
        from .demos import demonstrate

        output(demonstrate(args.output, args.scenario))
