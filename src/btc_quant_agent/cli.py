from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .backtest import BacktestEngine, bootstrap, metrics, monte_carlo
from .config import AppConfig, load_config
from .data.binance import BinancePublicClient
from .data.binance_archive import audit_official_timeframes, build_official_dataset
from .data.collector import collect_derivative_snapshot
from .data.csvio import read_candles, write_candles
from .data.derivatives import HistoricalDerivativeStore
from .data.forward_store import (
    ForwardDerivativeStore,
    collect_once,
    next_collection_time_ms,
    scheduler_status,
)
from .data.funding import read_funding_events_csv
from .data.manifest import build_manifest, write_manifest
from .data.network_diagnostic import diagnose_binance_network
from .engine import EngineMode, QuantEngine
from .explain import explain_signal
from .forward_evidence import forward_evidence_status, forward_operations_health
from .microstructure import MicrostructureCampaign, MicrostructureStore, run_daemon
from .opportunity_forward import (
    OpportunityCampaign,
    OpportunityForwardStore,
    collect_opportunity_once,
    opportunity_scheduler_status,
    resolve_opportunity_outcomes,
)
from .research import replay_decisions, run_full_suite, write_research_artifacts
from .research_registry import RegistryError, ResearchRegistry
from .service import QuantService


def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _service(config_path: str | None) -> QuantService:
    return QuantService.create(load_config(config_path))


def _historical_config(config_path: str | None) -> AppConfig:
    return load_config(config_path or "configs/frozen/v0.2.2.toml")


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

    derivatives = sub.add_parser("derivatives", help="append-safe forward PIT derivatives")
    derivatives_sub = derivatives.add_subparsers(dest="derivatives_command", required=True)
    for name in ("collect-once", "run", "status", "audit", "export", "diagnose-network"):
        command = derivatives_sub.add_parser(name)
        command.add_argument("--store", default="./data/forward/BTCUSDT/derivatives.sqlite3")
        if name in {"collect-once", "run"}:
            command.add_argument("--symbol", default="BTCUSDT")
            command.add_argument("--include-order-book", action="store_true")
            command.add_argument("--require-active-epoch", action="store_true", default=False)
            command.add_argument(
                "--epoch-registry",
                default="configs/forward/derivatives_evidence_epochs.json",
            )
        if name == "run":
            command.add_argument("--max-samples", type=int)
        if name == "export":
            command.add_argument("--csv")
            command.add_argument("--manifest")

    opportunity = sub.add_parser(
        "opportunity-forward", help="directionless forward opportunity movement campaign"
    )
    opportunity_sub = opportunity.add_subparsers(dest="opportunity_command", required=True)
    for name in ("collect-once", "status", "audit", "resolve", "report"):
        command = opportunity_sub.add_parser(name)
        command.add_argument(
            "--store", default="./data/forward/BTCUSDT/opportunity_shadow.sqlite3"
        )
        command.add_argument(
            "--campaign",
            default=None,
        )
        command.add_argument(
            "--registry",
            default="configs/forward/opportunity_forward_campaigns.json",
        )
        command.add_argument(
            "--require-active-campaign",
            action="store_true",
            default=False,
        )

    forward_evidence = sub.add_parser(
        "forward-evidence", help="unified non-alpha forward evidence watchdog"
    )
    forward_evidence_sub = forward_evidence.add_subparsers(
        dest="forward_evidence_command", required=True
    )
    for name in ("status", "audit", "health", "doctor"):
        command = forward_evidence_sub.add_parser(name)
        command.add_argument(
            "--derivatives-store",
            default="./data/forward/BTCUSDT/derivatives.sqlite3",
        )
        command.add_argument(
            "--opportunity-store",
            default="./data/forward/BTCUSDT/opportunity_shadow.sqlite3",
        )
        command.add_argument(
            "--epoch",
            default="configs/forward/v0.3.14_derivatives_evidence_epoch.json",
        )
        command.add_argument(
            "--epoch-registry",
            default="configs/forward/derivatives_evidence_epochs.json",
        )
        command.add_argument(
            "--campaign",
            default="configs/forward/v0.3.13_opportunity_shadow_campaign.json",
        )
        command.add_argument(
            "--opportunity-registry",
            default="configs/forward/opportunity_forward_campaigns.json",
        )
        command.add_argument(
            "--microstructure-root",
            default="data/forward/BTCUSDT/microstructure",
        )
        command.add_argument(
            "--microstructure-campaign",
            default="configs/forward/v0.3.15_microstructure_capture_campaign.json",
        )

    recover_cmd = forward_evidence_sub.add_parser(
        "recover-services", help="safely restart and recover forward services"
    )
    recover_cmd.add_argument(
        "--dry-run",
        action="store_true",
        help="print planned recovery actions without executing them",
    )

    microstructure = sub.add_parser(
        "microstructure-forward", help="data-only PIT depth and aggregate-trade capture"
    )
    micro_sub = microstructure.add_subparsers(dest="microstructure_command", required=True)
    for name in ("run", "status", "audit"):
        command = micro_sub.add_parser(name)
        command.add_argument("--root", default="data/forward/BTCUSDT/microstructure")
        command.add_argument(
            "--campaign",
            default="configs/forward/v0.3.15_microstructure_capture_campaign.json",
        )

    micro_research = sub.add_parser(
        "microstructure-research", help="H39 causal microstructure alpha research and diagnostics"
    )
    micro_res_sub = micro_research.add_subparsers(
        dest="microstructure_research_command", required=True
    )
    # H39 blind validation interface
    h39_parser = sub.add_parser(
        "h39", help="H39 blind validation accumulation and operational status"
    )
    h39_sub = h39_parser.add_subparsers(dest="h39_command", required=True)

    for p_sub in (h39_sub, micro_res_sub):
        h39_accum = p_sub.add_parser(
            "validation-accumulate", help="accumulate validation evidence into blind ledger"
        )
        h39_accum.add_argument(
            "--microstructure-root", default="data/forward/BTCUSDT/microstructure"
        )
        h39_accum.add_argument(
            "--opportunity-store", default="data/forward/BTCUSDT/opportunity_shadow.sqlite3"
        )
        h39_accum.add_argument(
            "--ledger-path", default="data/research/h39_validation/h39_blind_ledger.sqlite3"
        )
        h39_accum.add_argument(
            "--only-finalized", action="store_true", default=False, help="only ingest finalized partitions (prior to today UTC)"
        )

        h39_sched = p_sub.add_parser(
            "scheduled-accumulate", help="execute scheduled accumulation with disk check, integrity check, and backup"
        )
        h39_sched.add_argument(
            "--microstructure-root", default="data/forward/BTCUSDT/microstructure"
        )
        h39_sched.add_argument(
            "--opportunity-store", default="data/forward/BTCUSDT/opportunity_shadow.sqlite3"
        )
        h39_sched.add_argument(
            "--ledger-path", default="data/research/h39_validation/h39_blind_ledger.sqlite3"
        )
        h39_sched.add_argument(
            "--backup-dir", default="data/research/h39_validation/backups"
        )
        h39_sched.add_argument(
            "--min-free-gb", type=float, default=5.0
        )
        h39_sched.add_argument(
            "--only-finalized", action="store_true", default=True, help="only ingest finalized partitions"
        )
        h39_sched.add_argument(
            "--include-active", action="store_true", default=False, help="include today's active partition as well"
        )

        h39_integ = p_sub.add_parser(
            "verify-integrity", help="verify SQLite integrity and source partition hashes"
        )
        h39_integ.add_argument(
            "--ledger-path", default="data/research/h39_validation/h39_blind_ledger.sqlite3"
        )

        h39_bak = p_sub.add_parser(
            "backup-ledger", help="create consistent SQLite online backup and manifest"
        )
        h39_bak.add_argument(
            "--ledger-path", default="data/research/h39_validation/h39_blind_ledger.sqlite3"
        )
        h39_bak.add_argument(
            "--backup-dir", default="data/research/h39_validation/backups"
        )

        h39_status = p_sub.add_parser(
            "validation-status", help="show blind validation accumulation status and metrics"
        )
        h39_status.add_argument(
            "--ledger-path", default="data/research/h39_validation/h39_blind_ledger.sqlite3"
        )
        h39_status.add_argument("--as-of-ms", type=int, default=None)

        h39_ready = p_sub.add_parser(
            "validation-readiness", help="check readiness for one-shot unblind"
        )
        h39_ready.add_argument(
            "--ledger-path", default="data/research/h39_validation/h39_blind_ledger.sqlite3"
        )
        h39_ready.add_argument("--as-of-ms", type=int, default=None)

        h39_deliv = p_sub.add_parser(
            "generate-deliverables", help="generate v0.3.24 deliverables"
        )
        h39_deliv.add_argument("--output-dir", default="deliverables/v0.3.24")
        h39_deliv.add_argument(
            "--microstructure-root", default="data/forward/BTCUSDT/microstructure"
        )
        h39_deliv.add_argument(
            "--opportunity-store", default="data/forward/BTCUSDT/opportunity_shadow.sqlite3"
        )
        h39_deliv.add_argument(
            "--ledger-path", default="data/research/h39_validation/h39_blind_ledger.sqlite3"
        )
        h39_deliv.add_argument(
            "--backup-dir", default="data/research/h39_validation/backups"
        )

    registry = sub.add_parser("research-registry", help="inspect research eligibility")
    registry.add_argument(
        "--registry", default="configs/research_registry.json", help="registry JSON path"
    )
    registry_sub = registry.add_subparsers(dest="registry_command", required=True)
    registry_sub.add_parser("validate")
    registry_sub.add_parser("status")
    registry_show = registry_sub.add_parser("show")
    registry_show.add_argument("component_id")

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

    timeframe_audit = sub.add_parser(
        "audit-official-timeframes", help="validate local resampling against official archives"
    )
    timeframe_audit.add_argument("--root", default="./data/research/BTCUSDT")
    timeframe_audit.add_argument(
        "--months", nargs="+", default=["2021-01", "2022-06", "2024-03", "2026-01", "2026-07"]
    )

    daemon = sub.add_parser("daemon", help="poll at closed 15m boundaries")
    daemon.add_argument("--once", action="store_true")
    daemon.add_argument("--poll-seconds", type=int, default=30)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "research-registry":
        try:
            registry = ResearchRegistry.load(args.registry)
            if args.registry_command == "validate":
                _print(
                    {
                        "status": "VALID",
                        "schema_version": registry.schema_version,
                        "registry_version": registry.registry_version,
                        "component_count": len(registry.components),
                    }
                )
            elif args.registry_command == "status":
                _print(registry.status())
            else:
                component = registry.get(args.component_id)
                payload = asdict(component)
                payload["research_status"] = component.research_status.value
                payload["runtime_eligibility"] = component.runtime_eligibility.value
                _print(payload)
        except RegistryError as exc:
            _print({"status": "INVALID", "error": str(exc)})
            return 2
        return 0

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
    if args.command == "derivatives":
        if args.derivatives_command == "diagnose-network":
            report = diagnose_binance_network(
                base_url=service.config.data.rest_base_url,
                timeout=service.config.data.request_timeout_seconds,
            )
            _print(report)
            return 0 if report["overall_status"] == "OK" else 2
        store = ForwardDerivativeStore(args.store)
        if args.derivatives_command == "collect-once":
            if getattr(args, "require_active_epoch", False):
                from .evidence_epoch import resolve_active_derivatives_epoch

                active = resolve_active_derivatives_epoch(registry_path=args.epoch_registry)
                if active is None:
                    _print(
                        {
                            "status": "REFUSED_NO_ACTIVE_EPOCH",
                            "error": "No eligible active derivatives epoch found in registry. Scheduled collection refused on terminal/inactive epochs.",
                            "epoch_registry": args.epoch_registry,
                        }
                    )
                    return 0
                epoch, lifecycle = active
                now_ms = int(time.time() * 1000)
                if (
                    lifecycle.formal_eligibility_role == "FORMAL_SUCCESSOR_PENDING"
                    and now_ms < epoch.epoch_start_ms
                ):
                    _print(
                        {
                            "status": "REFUSED_PREREGISTERED_PENDING",
                            "error": "Successor epoch has not reached its frozen start boundary.",
                            "epoch_id": epoch.epoch_id,
                            "epoch_start_ms": epoch.epoch_start_ms,
                            "starts_in_seconds": round((epoch.epoch_start_ms - now_ms) / 1000, 1),
                        }
                    )
                    return 0
            record = collect_once(
                BinancePublicClient(service.config.data),
                store,
                symbol=args.symbol,
                include_order_book=args.include_order_book,
            )
            successful = any(record.field_availability.values())
            collection_status = (
                "COLLECTED"
                if not record.endpoint_errors
                else "PARTIAL" if successful else "FAILED"
            )
            _print(
                {
                    "status": collection_status,
                    "symbol": record.symbol,
                    "observed_at_ms": record.observed_at_ms,
                    "payload_hash": record.payload_hash,
                    "field_availability": record.field_availability,
                    "endpoint_errors": record.endpoint_errors,
                    "store": str(store.path),
                }
            )
            return 0 if successful else 2
        if args.derivatives_command == "run":
            if getattr(args, "require_active_epoch", False):
                from .evidence_epoch import resolve_active_derivatives_epoch

                active = resolve_active_derivatives_epoch(registry_path=args.epoch_registry)
                if active is None:
                    _print(
                        {
                            "status": "REFUSED_NO_ACTIVE_EPOCH",
                            "error": "No eligible active derivatives epoch found in registry. Runner refused on terminal/inactive epochs.",
                            "epoch_registry": args.epoch_registry,
                        }
                    )
                    return 0
            if args.max_samples is not None and args.max_samples < 1:
                _print({"error": "max-samples must be positive"})
                return 2
            client = BinancePublicClient(service.config.data)
            collected = 0
            while args.max_samples is None or collected < args.max_samples:
                now_ms = int(time.time() * 1000)
                target_ms = next_collection_time_ms(now_ms)
                time.sleep(max(0.0, (target_ms - now_ms) / 1000))
                record = collect_once(
                    client,
                    store,
                    symbol=args.symbol,
                    include_order_book=args.include_order_book,
                )
                collected += 1
                _print(
                    {
                        "status": "COLLECTED",
                        "sample": collected,
                        "observed_at_ms": record.observed_at_ms,
                        "endpoint_errors": record.endpoint_errors,
                    }
                )
            return 0
        if args.derivatives_command == "status":
            _print(store.status(scheduler=scheduler_status()))
            return 0
        if args.derivatives_command == "audit":
            report = store.audit()
            _print(report)
            return (
                0
                if not (
                    report["conflict_count"]
                    or report["source_timestamp_after_observed_at"]
                    or report["impossible_value_timestamps"]
                )
                else 2
            )
        export_csv = args.csv or str(Path(args.store).with_name("derivatives.csv"))
        export_manifest = args.manifest or f"{export_csv}.manifest.json"
        _print(store.export(export_csv, export_manifest))
        return 0
    if args.command == "opportunity-forward":
        from .opportunity_forward import (
            OpportunityCampaign,
            OpportunityCampaignRegistry,
            resolve_active_opportunity_campaign,
        )

        campaign: OpportunityCampaign | None = None
        if args.campaign:
            campaign = OpportunityCampaign.load(args.campaign)
        else:
            resolved = resolve_active_opportunity_campaign(args.registry)
            if resolved is not None:
                campaign = resolved[0]
            elif (
                getattr(args, "require_active_campaign", False)
                or args.opportunity_command in {"collect-once", "resolve"}
            ):
                _print(
                    {
                        "status": "REFUSED_NO_ACTIVE_CAMPAIGN",
                        "error": "No eligible active opportunity campaign found in registry. Scheduled action refused on terminal/inactive campaigns.",
                        "registry": args.registry,
                    }
                )
                return 0
            else:
                reg = OpportunityCampaignRegistry.load(args.registry)
                campaign = reg.archive()[0]
        assert campaign is not None
        opportunity_store = OpportunityForwardStore(args.store)
        if args.opportunity_command == "collect-once":
            now_ms = int(time.time() * 1000)
            slot_ms = (now_ms // 900_000) * 900_000
            if campaign.has_data_quality_gate and slot_ms < campaign.campaign_start_ms:
                _print(
                    {
                        "status": "REFUSED_PREREGISTERED_PENDING",
                        "error": "Successor campaign has not reached its frozen start boundary.",
                        "campaign_id": campaign.campaign_id,
                        "campaign_start_ms": campaign.campaign_start_ms,
                        "starts_in_seconds": round((campaign.campaign_start_ms - now_ms) / 1000, 1),
                    }
                )
                return 0
            observation = collect_opportunity_once(service, opportunity_store, campaign)
            _print(asdict(observation))
            return 0 if observation.status == "SUCCESSFUL_SCAN" else 2
        if args.opportunity_command == "audit":
            report = opportunity_store.audit(campaign.campaign_id)
            _print(report)
            return 0 if not report["direction_action_columns"] else 2
        if args.opportunity_command == "resolve":
            now_ms = int(time.time() * 1000)
            if campaign.has_data_quality_gate and now_ms < campaign.campaign_start_ms:
                _print(
                    {
                        "status": "REFUSED_PREREGISTERED_PENDING",
                        "error": "Successor campaign has not reached its frozen start boundary.",
                        "campaign_id": campaign.campaign_id,
                    }
                )
                return 0
            _print(
                resolve_opportunity_outcomes(
                    BinancePublicClient(service.config.data), opportunity_store, campaign
                )
            )
            return 0
        report = opportunity_store.status(
            campaign, scheduler=opportunity_scheduler_status()
        )
        if args.opportunity_command == "report":
            report = {
                **report,
                "audit": opportunity_store.audit(campaign.campaign_id),
            }
        _print(report)
        return 0
    if args.command == "forward-evidence":
        if args.forward_evidence_command == "doctor":
            from .forward_diagnostics import forward_doctor
            doc = forward_doctor()
            _print(doc)
            return (
                0
                if doc.get(
                    "is_healthy",
                    doc.get("status") in {"HEALTHY", "HEALTHY_ACCUMULATING", "PREREGISTERED_NOT_STARTED"},
                )
                else 2
            )
        if args.forward_evidence_command == "recover-services":
            from .forward_diagnostics import recover_services
            res = recover_services(dry_run=getattr(args, "dry_run", False))
            _print(res)
            return 0
        report = forward_evidence_status(
            derivatives_store_path=args.derivatives_store,
            opportunity_store_path=args.opportunity_store,
            epoch_path=args.epoch,
            epoch_registry_path=args.epoch_registry,
            campaign_path=args.campaign,
            opportunity_campaign_registry_path=args.opportunity_registry,
            microstructure_root=args.microstructure_root,
            microstructure_campaign_path=args.microstructure_campaign,
        )
        if args.forward_evidence_command == "audit":
            report["audit"] = {
                "backfill_occurred": False,
                "manual_improves_eligibility": False,
                "legacy_improves_eligibility": False,
                "outcomes_mutate_observations": False,
            }
        if args.forward_evidence_command == "health":
            health = forward_operations_health(report)
            _print(health)
            return 0 if health["state"] == "HEALTHY" else 2
        _print(report)
        return 0
    if args.command == "microstructure-forward":
        micro_campaign = MicrostructureCampaign.load(args.campaign)
        micro_store = MicrostructureStore(
            args.root, micro_campaign.campaign_id, micro_campaign.start_ms
        )
        if args.microstructure_command == "run":
            import asyncio

            try:
                asyncio.run(run_daemon(micro_campaign, args.root))
            except KeyboardInterrupt:
                return 0
            return 0
        report = micro_store.status()
        if args.microstructure_command == "audit":
            report["audit"] = {
                "retrospective_backfill": False,
                "runtime_integration": "DISABLED",
                "execution_integration": "DISABLED",
                "final_holdout_access": False,
            }
        _print(report)
        return 0
    if args.command in ("h39", "microstructure-research"):
        cmd = getattr(args, "h39_command", None) or getattr(
            args, "microstructure_research_command", None
        )
        from .microstructure_research import (
            H39BlindLedger,
            H39ResearchEngine,
            generate_all_v0322_deliverables,
            generate_all_v0323_deliverables,
            generate_all_v0324_deliverables,
        )

        if cmd == "validation-accumulate":
            engine = H39ResearchEngine(
                microstructure_root=args.microstructure_root,
                opportunity_store_path=args.opportunity_store,
            )
            res = engine.accumulate_blind_validation(
                output_ledger_path=args.ledger_path,
                only_finalized=getattr(args, "only_finalized", False),
            )
            _print(res)
            return 0
        if cmd == "scheduled-accumulate":
            engine = H39ResearchEngine(
                microstructure_root=args.microstructure_root,
                opportunity_store_path=args.opportunity_store,
            )
            only_fin = (
                not getattr(args, "include_active", False)
                if getattr(args, "include_active", False)
                else getattr(args, "only_finalized", True)
            )
            res = engine.run_scheduled_accumulation(
                output_ledger_path=args.ledger_path,
                backup_dir=args.backup_dir,
                min_free_gb=args.min_free_gb,
                only_finalized=only_fin,
            )
            _print(res)
            return 0
        if cmd == "verify-integrity":
            ledger = H39BlindLedger(args.ledger_path)
            res = ledger.verify_integrity()
            _print(res)
            return 0 if res.get("status") == "OK" else 1
        if cmd == "backup-ledger":
            ledger = H39BlindLedger(args.ledger_path)
            bak_path = ledger.backup_ledger(args.backup_dir)
            _print({"status": "SUCCESS", "backup_path": str(bak_path)})
            return 0
        if cmd == "validation-status":
            engine = H39ResearchEngine()
            res = engine.get_blind_validation_status(
                ledger_path=args.ledger_path, as_of_ms=args.as_of_ms
            )
            _print(res)
            return 0
        if cmd == "validation-readiness":
            engine = H39ResearchEngine()
            res = engine.check_unblind_readiness(
                ledger_path=args.ledger_path, as_of_ms=args.as_of_ms
            )
            _print(res)
            return 0 if res.get("ready_for_unblind") else 1
        if cmd == "generate-deliverables":
            if "v0.3.23" in args.output_dir:
                res = generate_all_v0323_deliverables(
                    output_dir=args.output_dir,
                    microstructure_root=args.microstructure_root,
                    opportunity_store_path=args.opportunity_store,
                    ledger_path=args.ledger_path,
                )
            else:
                res = generate_all_v0324_deliverables(
                    output_dir=args.output_dir,
                    microstructure_root=args.microstructure_root,
                    opportunity_store_path=args.opportunity_store,
                    ledger_path=args.ledger_path,
                    backup_dir=getattr(args, "backup_dir", "data/research/h39_validation/backups"),
                )
            _print({"status": "SUCCESS", "deliverables": res})
            return 0
        if cmd == "run-h39":
            res = generate_all_v0322_deliverables(
                output_dir=args.output_dir,
                microstructure_root=args.microstructure_root,
                opportunity_store_path=args.opportunity_store,
            )
            _print({"status": "SUCCESS", "deliverables": res})
            return 0
        return 1
    if args.command == "build-official-dataset":
        if hasattr(os, "nice"):
            try:
                os.nice(10)
            except OSError:
                pass
        start = datetime.fromisoformat(args.start).replace(tzinfo=UTC)
        end = datetime.fromisoformat(args.end_exclusive).replace(tzinfo=UTC)
        _print(build_official_dataset(args.root, start, end))
        return 0
    if args.command == "audit-official-timeframes":
        months = [(int(value[:4]), int(value[5:7])) for value in args.months]
        report = audit_official_timeframes(args.root, months)
        _print(report)
        return 0 if report["price_time_passed"] else 2
    if args.command == "replay":
        historical_config = _historical_config(args.config)
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
                QuantEngine(historical_config, mode=EngineMode.LEGACY_RESEARCH_V022),
                derivative_store,
            )
        )
        return 0
    if args.command == "research":
        historical_config = _historical_config(args.config)
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
            historical_config,
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
                historical_config,
                data_manifest_path=args.data_manifest,
                seed=args.seed,
            )
        except RuntimeError as exc:
            _print({"error": str(exc)})
            return 2
        _print({"status": "written", "output": output})
        return 0
    if args.command == "backtest":
        historical_config = _historical_config(args.config)
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
                QuantEngine(historical_config, mode=EngineMode.LEGACY_RESEARCH_V022),
                derivative_store,
                funding_events,
            ).run(bars)
        except ValueError as exc:
            _print({"error": str(exc)})
            return 2
        _print(
            {
                "validation_status": historical_config.runtime.validation_status,
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
