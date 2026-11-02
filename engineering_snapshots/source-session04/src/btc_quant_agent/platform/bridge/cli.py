"""Bounded offline bridge commands and source-readiness report."""

from __future__ import annotations

import json
from pathlib import Path

from ..core import UserReportedFill, dec, fingerprint
from ..reporting import document, table, write_json
from .config import load
from .contracts import PublicSource
from .fixtures import SCENARIOS, OfflineFixtureProvider
from .runtime import BridgeStore, ReadOnlyScanner


def configure(commands):
    group = commands.add_parser("bridge", help="Offline public-provider bridge; real activation blocked")
    sub = group.add_subparsers(dest="bridge_operation", required=True)
    for operation in ("scan", "replay", "readiness", "report-fill"):
        p = sub.add_parser(operation)
        p.add_argument("--config", required=True)
        p.add_argument("--output", default="artifacts/bridge")
        p.add_argument("--store", default=None)
        if operation in ("scan", "replay"):
            p.add_argument("--fixture", choices=SCENARIOS, default="normal")
        if operation == "scan":
            p.add_argument("--bar", type=int, default=50)
        if operation == "replay":
            p.add_argument("--bars", type=int, nargs="+", default=[50, 51, 55, 57])
        if operation == "report-fill":
            p.add_argument("--plan-id", required=True)
            p.add_argument("--report", required=True)


def readiness(config):
    return {
        "mode": config.mode,
        "provider": config.provider,
        "real_source_activation": "BLOCKED",
        "network_calls_performed": 0,
        "orders_or_accounts": "ABSENT",
        "matrix": [
            {
                "component": "USDT instrument metadata",
                "implemented": "Binance and OKX fixture decoders; active status, precision, linear multiplier",
                "unverified": "Live schema, minimum notional/margin tiers, funding schedule and symbol entitlement",
                "authorization_needed": "Explicit provider, public metadata endpoints, universe and read-only access scope",
            },
            {
                "component": "Completed candles and volume",
                "implemented": "Existing Candle/decoder reused; response-receive and availability retained",
                "unverified": "Authorized forward continuity, gaps, interval boundaries and data retention",
                "authorization_needed": "Explicit public candle fields, intervals, acquisition period and retained evidence location",
            },
            {
                "component": "Executable bid/ask and size",
                "implemented": "Independent quote, event/receive clocks, tick/spread/age checks; no candle quote inference",
                "unverified": "Real source event timestamp and quote-size semantics; timestamp-less REST quotes fail closed",
                "authorization_needed": "Explicit public quote transport/endpoint, source-time authority, rate limits and freshness pilot",
            },
            {
                "component": "Funding and OI",
                "implemented": "Separate field clocks, OI base normalization, unknown/failed/stale fields stay missing",
                "unverified": "Native funding cadence, dynamic changes, settlement evidence, OI units and live failure recovery",
                "authorization_needed": "Explicit funding/OI public endpoints, units, sampling interval and retention; no account endpoints",
            },
            {
                "component": "Spot/perpetual comparison",
                "implemented": "Separate spot receipts, aligned completed windows and skew/availability checks",
                "unverified": "Authorized independent spot source and cross-market clock synchronization",
                "authorization_needed": "Explicit spot/perpetual symbol mapping and both public sources",
            },
            {
                "component": "Advisory/positions/notifications",
                "implemented": "69 factors, 21 directional strategies, bound admission, risk sizing, durable preview, user-confirmed ledger",
                "unverified": "Real-feed operational latency, outages and authorized notification delivery; no live readiness claim",
                "authorization_needed": "Separate source-admission pilot and any later notification/deployment scope; orders remain outside scope",
            },
        ],
        "limitations": [
            "Offline fixture success is not observed market connectivity or profitability.",
            "No configuration, raw payload flag or environment variable activates a real source.",
        ],
    }


def execute(args):
    config = load(args.config)
    if args.bridge_operation == "readiness":
        return readiness(config)
    if config.mode != "offline_fixture":
        PublicSource(config.provider).snapshot(0)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    store = BridgeStore(args.store or output / (config.hash + ".sqlite"))
    if args.bridge_operation == "report-fill":
        raw = json.loads(Path(args.report).read_text())
        for name in ("price", "quantity"):
            raw[name] = dec(raw[name])
        return store.report_plan_fill(args.plan_id, UserReportedFill(**raw))
    provider = OfflineFixtureProvider(config, args.fixture)
    scanner = ReadOnlyScanner(config, store)
    bars = [args.bar] if args.bridge_operation == "scan" else args.bars
    if bars != sorted(set(bars)):
        raise ValueError("replay bars must be strictly increasing")
    results = [scanner.scan(provider.snapshot(bar)) for bar in bars]
    id = fingerprint([config.hash, args.fixture, bars, scanner.source_hash])
    path = output / id
    path.mkdir(parents=True, exist_ok=True)
    report = {
        "run_id": id,
        "config_hash": config.hash,
        "source_hash": scanner.source_hash,
        "fixture": args.fixture,
        "exposure": "SYNTHETIC",
        "results": results,
        "readiness": readiness(config),
    }
    write_json(path / "replay.json", report)
    rows = []
    for r in results:
        for record in r["records"]:
            rows.append(
                {
                    "decision_ts": r["decision_ts"],
                    "symbol": record["symbol"],
                    "kind": record["kind"],
                    "state": record.get("state", "USER_POSITION"),
                    "action": record["action"],
                    "veto_reasons": record.get("veto_reasons", []),
                }
            )
    (path / "report.html").write_text(
        document("Offline provider-to-advisory replay", table(rows)), encoding="utf-8"
    )
    return {
        "run_id": id,
        "exposure": "SYNTHETIC",
        "path": str(path),
        "snapshots": len(results),
        "states": rows,
        "real_activation": "BLOCKED",
    }
