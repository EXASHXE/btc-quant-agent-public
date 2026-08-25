from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from .backtest import BacktestEngine, bootstrap, metrics, monte_carlo
from .config import load_config
from .data.binance import BinancePublicClient
from .data.binance_archive import build_official_dataset
from .data.collector import collect_derivative_snapshot
from .data.csvio import read_candles, write_candles
from .data.derivatives import HistoricalDerivativeStore
from .data.funding import read_funding_events_csv
from .data.manifest import build_manifest, write_manifest
from .engine import QuantEngine
from .explain import explain_signal
from .research import replay_decisions, run_full_suite, write_research_artifacts
from .service import QuantService


def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _service(config_path: str | None) -> QuantService:
    return QuantService.create(load_config(config_path))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quantctl")
    parser.add_argument("--config", help="TOML configuration path")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="scan current market")
    scan.add_argument("symbol", nargs="?", default="BTCUSDT")
    scan.add_argument("--no-notify", action="store_true")

    signal = sub.add_parser("signal", help="read immutable signals")
    signal_sub = signal.add_subparsers(dest="signal_command", required=True)
    signal_sub.add_parser("latest")
    show = signal_sub.add_parser("show")
    show.add_argument("signal_id")

    explain = sub.add_parser("explain", help="explain a signal from stored fields")
    explain.add_argument("signal_id")

    decision = sub.add_parser("decision", help="record a manual user decision")
    decision.add_argument("signal_id")
    decision.add_argument("decision", choices=["accept", "ignore"])
    decision.add_argument("--entry", type=float)

    performance = sub.add_parser("performance", help="shadow performance")
    performance.add_argument("--days", type=int, default=30)

    sub.add_parser("health", help="health and execution-capability check")

    execution = sub.add_parser("execution", help="gated order interface (disabled by default)")
    execution_sub = execution.add_subparsers(dest="execution_command", required=True)
    execution_sub.add_parser("status")
    entry_plan = execution_sub.add_parser("plan-entry")
    entry_plan.add_argument("signal_id")
    submit = execution_sub.add_parser("submit")
    submit.add_argument("plan_id")
    submit.add_argument("--confirm", required=True)
    reconcile = execution_sub.add_parser("reconcile")
    reconcile.add_argument("plan_id")
    close_preview = execution_sub.add_parser("plan-close")
    close_preview.add_argument("--symbol", default="BTCUSDT")
    close_submit = execution_sub.add_parser("submit-close")
    close_submit.add_argument("plan_id")
    close_submit.add_argument("--confirm", required=True)
    cancel = execution_sub.add_parser("cancel")
    cancel.add_argument("plan_id")
    cancel.add_argument("--confirm", required=True)

    download = sub.add_parser("download", help="download public historical candles to CSV")
    download.add_argument("path")
    download.add_argument("--start-ms", type=int, required=True)
    download.add_argument("--end-ms", type=int, required=True)
    download.add_argument("--interval", choices=["1m", "5m", "15m", "1h", "4h"], default="1m")

    backtest = sub.add_parser("backtest", help="replay a canonical 1m CSV")
    backtest.add_argument("path")
    backtest.add_argument(
        "--derivatives", help="historical derivatives CSV for backward as-of replay"
    )
    backtest.add_argument("--monte-carlo", type=int, default=2000)
    backtest.add_argument("--funding-events", help="point-in-time funding settlement CSV")

    collector = sub.add_parser(
        "collect-derivatives", help="append a point-in-time public derivatives snapshot"
    )
    collector.add_argument("--path", default="./data/BTCUSDT-derivatives.csv")
    collector.add_argument("--manifest")
    collector.add_argument("--samples", type=int, default=1)
    collector.add_argument("--interval-seconds", type=int, default=900)
    collector.add_argument("--include-order-book", action="store_true")

    replay = sub.add_parser("replay", help="emit every causal 15m decision and rejection")
    replay.add_argument("path")
    replay.add_argument("--derivatives")
    replay.add_argument("--start-ms", type=int)
    replay.add_argument("--end-ms", type=int)

    research = sub.add_parser("research", help="run the frozen validation suite")
    research.add_argument("path")
    research.add_argument("--data-manifest", required=True)
    research.add_argument("--derivatives")
    research.add_argument("--funding-events")
    research.add_argument("--output")
    research.add_argument("--seed", type=int, default=7)

    dataset = sub.add_parser("build-official-dataset", help="build verified Binance monthly data")
    dataset.add_argument("--root", default="./data/research/BTCUSDT")
    dataset.add_argument("--start", default="2021-01-01")
    dataset.add_argument("--end-exclusive", default="2026-08-01")

    daemon = sub.add_parser("daemon", help="poll at closed 15m boundaries")
    daemon.add_argument("--once", action="store_true")
    daemon.add_argument("--poll-seconds", type=int, default=30)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    service = _service(args.config)
    if args.command == "scan":
        _print(service.scan(args.symbol, not args.no_notify).as_dict())
        return 0
    if args.command == "signal":
        service.repository.expire_signals(int(time.time() * 1000))
        signal = (
            service.repository.latest_signal()
            if args.signal_command == "latest"
            else service.repository.get_signal(args.signal_id)
        )
        _print(signal.as_dict() if signal else {"error": "signal not found"})
        return 0 if signal else 2
    if args.command == "explain":
        signal = service.repository.get_signal(args.signal_id)
        if signal is None:
            _print({"error": "signal not found"})
            return 2
        _print(explain_signal(signal))
        return 0
    if args.command == "decision":
        try:
            service.mark_decision(args.signal_id, args.decision, args.entry)
        except KeyError as exc:
            _print({"error": str(exc)})
            return 2
        _print({"status": "recorded", "signal_id": args.signal_id})
        return 0
    if args.command == "performance":
        since = int(time.time() * 1000) - args.days * 86_400_000
        _print(service.repository.performance(since))
        return 0
    if args.command == "health":
        _print(service.health())
        return 0
    if args.command == "execution":
        try:
            if args.execution_command == "status":
                payload = service.execution.status()
            elif args.execution_command == "plan-entry":
                payload = service.execution.build_entry_plan(args.signal_id).as_dict()
            elif args.execution_command == "submit":
                payload = service.execution.submit_entry(args.plan_id, args.confirm).as_dict()
            elif args.execution_command == "reconcile":
                payload = service.execution.reconcile(args.plan_id)
            elif args.execution_command == "plan-close":
                payload = service.execution.prepare_close(args.symbol).as_dict()
            elif args.execution_command == "submit-close":
                payload = service.execution.submit_close(args.plan_id, args.confirm).as_dict()
            else:
                payload = service.execution.cancel_entry(args.plan_id, args.confirm)
        except (KeyError, RuntimeError, ValueError) as exc:
            _print({"error": str(exc)})
            return 2
        _print(payload)
        return 0
    if args.command == "download":
        client = BinancePublicClient(service.config.data)
        bars = client.historical_klines("BTCUSDT", args.interval, args.start_ms, args.end_ms)
        write_candles(args.path, bars)
        manifest = build_manifest(
            args.path,
            source="Binance USD-M public REST klines",
            rows=[asdict(bar) for bar in bars],
            timestamp_field="open_time_ms",
            expected_interval_ms={
                "1m": 60_000,
                "5m": 300_000,
                "15m": 900_000,
                "1h": 3_600_000,
                "4h": 14_400_000,
            }[args.interval],
        )
        manifest_path = f"{args.path}.manifest.json"
        write_manifest(manifest_path, manifest)
        _print(
            {
                "status": "written",
                "path": args.path,
                "candles": len(bars),
                "data_manifest": manifest_path,
            }
        )
        return 0
    if args.command == "collect-derivatives":
        if args.samples < 1 or args.interval_seconds < 1:
            _print({"error": "samples and interval-seconds must be positive"})
            return 2
        client = BinancePublicClient(service.config.data)
        collected_manifest = None
        for index in range(args.samples):
            collected_manifest = collect_derivative_snapshot(
                client,
                args.path,
                include_order_book=args.include_order_book,
                manifest_path=args.manifest,
            )
            if index + 1 < args.samples:
                time.sleep(args.interval_seconds)
        assert collected_manifest is not None
        _print({"status": "collected", "manifest": collected_manifest.as_dict()})
        return 0
    if args.command == "build-official-dataset":
        start = datetime.fromisoformat(args.start).replace(tzinfo=UTC)
        end = datetime.fromisoformat(args.end_exclusive).replace(tzinfo=UTC)
        _print(build_official_dataset(args.root, start, end))
        return 0
    if args.command == "replay":
        bars = read_candles(args.path)
        if args.start_ms is not None:
            bars = [bar for bar in bars if bar.open_time_ms >= args.start_ms]
        if args.end_ms is not None:
            bars = [bar for bar in bars if bar.close_time_ms <= args.end_ms]
        derivative_store = (
            HistoricalDerivativeStore.from_csv(args.derivatives) if args.derivatives else None
        )
        _print(
            replay_decisions(
                bars,
                QuantEngine(service.config),
                derivative_store,
            )
        )
        return 0
    if args.command == "research":
        bars = read_candles(args.path)
        if not bars or any(bar.interval != "1m" for bar in bars):
            _print({"error": "research requires a non-empty canonical 1m CSV"})
            return 2
        derivative_store = (
            HistoricalDerivativeStore.from_csv(args.derivatives) if args.derivatives else None
        )
        funding_events = read_funding_events_csv(args.funding_events) if args.funding_events else []
        suite = run_full_suite(
            bars,
            service.config,
            derivative_store,
            funding_events,
            seed=args.seed,
        )
        output = args.output or (
            "artifacts/research/" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        )
        try:
            write_research_artifacts(
                output,
                suite,
                service.config,
                data_manifest_path=args.data_manifest,
                seed=args.seed,
            )
        except RuntimeError as exc:
            _print({"error": str(exc)})
            return 2
        _print({"status": "written", "output": output})
        return 0
    if args.command == "backtest":
        bars = read_candles(args.path)
        if not bars or any(bar.interval != "1m" for bar in bars):
            _print({"error": "backtest requires a non-empty canonical 1m CSV"})
            return 2
        try:
            derivative_store = (
                HistoricalDerivativeStore.from_csv(args.derivatives) if args.derivatives else None
            )
            funding_events = (
                read_funding_events_csv(args.funding_events) if args.funding_events else []
            )
            outcomes = BacktestEngine(
                QuantEngine(service.config), derivative_store, funding_events
            ).run(bars)
        except ValueError as exc:
            _print({"error": str(exc)})
            return 2
        _print(
            {
                "validation_status": service.config.runtime.validation_status,
                "metrics": metrics(outcomes),
                "monte_carlo": monte_carlo(outcomes, args.monte_carlo),
                "bootstrap": bootstrap(outcomes, args.monte_carlo),
                "block_bootstrap": bootstrap(
                    outcomes, args.monte_carlo, block_size=max(1, round(len(outcomes) ** 0.5))
                ),
                "outcomes": [item.as_dict() for item in outcomes],
            }
        )
        return 0
    if args.command == "daemon":
        while True:
            try:
                shadow = service.update_shadow()
                execution = service.execution.reconcile_open_plans()
                _print(
                    {
                        "shadow_resolved": shadow,
                        "execution_reconciled": execution,
                        "scan": service.scan().as_dict(),
                    }
                )
            except Exception as exc:  # noqa: BLE001 - daemon must remain alive and report faults
                _print({"status": "DEGRADED", "error": str(exc)})
            if args.once:
                return 0
            time.sleep(max(args.poll_seconds, 5))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
