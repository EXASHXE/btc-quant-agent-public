"""Command Line Interface for Binance USDⓈ-M public forward recorder."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from decimal import Decimal
from pathlib import Path

from .connector import BinancePublicFeedClient, NetworkGateError
from .contracts import (
    ALLOWED_PRODUCT,
    ALLOWED_SYMBOL,
    ContractValidationError,
    MarketEventV1,
    compute_sha256,
)
from .durability import RawSegmentWriter, SegmentWriter
from .fixture import DeterministicExchangeFixture
from .health import HealthSupervisor
from .order_book import OrderBookIntegrityEngine
from .proxy_route import ProxyRouteConfig
from .replay import ReplayEngine
from .time_authority import TimeAuthority


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Public forward recorder for Binance USDⓈ-M BTCUSDT (account-free, order-free)."
    )
    parser.add_argument(
        "--mode",
        choices=["fixture", "replay", "live-public"],
        default="fixture",
        help="Execution mode (default: fixture).",
    )
    parser.add_argument(
        "--network",
        choices=["disabled", "allow-public", "public-direct", "public-clash-explicit"],
        default="disabled",
        help="Network access gate (default: disabled). Live connection requires opt-in mode.",
    )
    parser.add_argument(
        "--proxy-kind",
        choices=["http", "socks5h"],
        default="http",
        help="Proxy protocol kind (default: http).",
    )
    parser.add_argument(
        "--proxy-host",
        default=None,
        help="Proxy hostname or IP for public-clash-explicit.",
    )
    parser.add_argument(
        "--proxy-port",
        type=int,
        default=None,
        help="Proxy port for public-clash-explicit.",
    )
    parser.add_argument(
        "--symbol",
        default=ALLOWED_SYMBOL,
        help="Market symbol (strictly BTCUSDT uppercase).",
    )
    parser.add_argument(
        "--duration-seconds",
        type=int,
        default=10,
        help="Maximum runtime duration in seconds for live-public or high-velocity run.",
    )
    parser.add_argument(
        "--records-count",
        type=int,
        default=50,
        help="Number of synthetic frames to generate in fixture mode.",
    )
    parser.add_argument(
        "--output-dir",
        default="/tmp/btc-forward_public_feed_r1/run_data",
        help="Directory to write append-only segments and manifests.",
    )
    parser.add_argument(
        "--replay-dir",
        default=None,
        help="Directory containing segment files to replay.",
    )
    parser.add_argument(
        "--replay-source",
        choices=["auto", "normalized", "raw"],
        default="auto",
        help="Source log to replay: auto (default), normalized, or raw.",
    )
    parser.add_argument(
        "--epoch",
        default=None,
        help="Specific connection epoch to record or replay.",
    )
    return parser


def run_fixture_mode(args: argparse.Namespace) -> int:
    """Run hermetic deterministic exchange fixture generation with segregated raw and normalized logs."""
    out_dir = Path(args.output_dir)
    epoch = args.epoch or f"fixture-epoch-{args.records_count}"
    raw_writer = RawSegmentWriter(base_dir=out_dir, epoch=epoch)
    writer = SegmentWriter(base_dir=out_dir, epoch=epoch)
    fix = DeterministicExchangeFixture(symbol=args.symbol)
    ta = TimeAuthority(connection_epoch=epoch)
    book_engine = OrderBookIntegrityEngine(symbol=args.symbol)
    health = HealthSupervisor(symbol=args.symbol, time_authority=ta)

    # 1. Depth snapshot
    snap_frame = fix.generate_depth_snapshot_frame(levels=20)
    snap_ingress = ta.capture_ingress()
    _seh, snap_raw_sha = raw_writer.append_raw_frame(
        json.dumps(snap_frame), snap_ingress.observed_wall_utc_ms, snap_ingress.observed_monotonic_ns
    )
    book_receipt = book_engine.apply_snapshot(snap_frame, snap_ingress.observed_wall_utc_ms)
    health.record_channel_event("depth_snapshot", snap_ingress.observed_wall_utc_ms, snap_frame, "VERIFIED")
    health.record_book_status(book_receipt.quality, book_receipt.continuous, book_receipt.reason_codes)

    snap_event = MarketEventV1(
        schema_version="market-event-v1",
        symbol=args.symbol,
        product=ALLOWED_PRODUCT,
        channel="depth_snapshot",
        provider_event_ms=snap_frame["E"],
        provider_transaction_ms=snap_frame["T"],
        observed_wall_utc_ms=snap_ingress.observed_wall_utc_ms,
        observed_monotonic_ns=snap_ingress.observed_monotonic_ns,
        available_at_ms=snap_ingress.available_at_ms,
        source_stream_id=f"{args.symbol.lower()}@depth_snapshot",
        connection_epoch=epoch,
        source_sequence=snap_frame["lastUpdateId"],
        payload_sha256=compute_sha256(snap_frame),
        payload=snap_frame,
        quality=book_receipt.quality,
        reason_codes=book_receipt.reason_codes,
        raw_source_manifest_sha256=snap_raw_sha,
        book=book_receipt,
    )
    writer.append_event(snap_event)

    # 2. Official Settled Funding (Realized, not estimated)
    fund_frame = fix.generate_settled_funding_frame()
    fund_ingress = ta.capture_ingress()
    _feh, fund_raw_sha = raw_writer.append_raw_frame(
        json.dumps(fund_frame), fund_ingress.observed_wall_utc_ms, fund_ingress.observed_monotonic_ns
    )
    health.record_channel_event("funding_settled", fund_ingress.observed_wall_utc_ms, fund_frame, "VERIFIED")
    fund_event = MarketEventV1(
        schema_version="market-event-v1",
        symbol=args.symbol,
        product=ALLOWED_PRODUCT,
        channel="funding_settled",
        provider_event_ms=fund_frame["fundingTime"],
        provider_transaction_ms=None,
        observed_wall_utc_ms=fund_ingress.observed_wall_utc_ms,
        observed_monotonic_ns=fund_ingress.observed_monotonic_ns,
        available_at_ms=fund_ingress.available_at_ms,
        source_stream_id=f"{args.symbol.lower()}@fundingRate",
        connection_epoch=epoch,
        source_sequence=None,
        payload_sha256=compute_sha256(fund_frame),
        payload=fund_frame,
        quality="VERIFIED",
        reason_codes=["OK"],
        raw_source_manifest_sha256=fund_raw_sha,
        book=None,
    )
    writer.append_event(fund_event)

    # 3. Sequential stream frames
    for i in range(args.records_count):
        fix.current_time_ms += 100
        mod = i % 4
        if mod == 0:
            frame = fix.generate_depth_delta_frame(span=2)
            channel = "depth_delta"
            ing = ta.capture_ingress()
            b_rec = book_engine.apply_delta(frame, ing.observed_wall_utc_ms)
            health.record_channel_event(channel, ing.observed_wall_utc_ms, frame, b_rec.quality)
            health.record_book_status(b_rec.quality, b_rec.continuous, b_rec.reason_codes)
            q = b_rec.quality
            r = b_rec.reason_codes
            seq = frame["u"]
            stream_id = f"{args.symbol.lower()}@depth@100ms"
        elif mod == 1:
            frame = fix.generate_agg_trade_frame(price_offset=Decimal("0.50"), quantity=Decimal("0.1"))
            channel = "agg_trade"
            ing = ta.capture_ingress()
            health.record_channel_event(channel, ing.observed_wall_utc_ms, frame, "VERIFIED")
            q = "VERIFIED"
            r = ["OK"]
            seq = frame["a"]
            b_rec = None
            stream_id = f"{args.symbol.lower()}@aggTrade"
        elif mod == 2:
            frame = fix.generate_mark_price_frame()
            channel = "mark_price"
            ing = ta.capture_ingress()
            health.record_channel_event(channel, ing.observed_wall_utc_ms, frame, "VERIFIED")
            q = "VERIFIED"
            r = ["OK"]
            seq = None
            b_rec = None
            stream_id = f"{args.symbol.lower()}@markPrice"
        else:
            frame = fix.generate_kline_frame(interval="1m", closed=(i == args.records_count - 1))
            channel = "last_kline_1m"
            ing = ta.capture_ingress()
            health.record_channel_event(channel, ing.observed_wall_utc_ms, frame, "VERIFIED")
            q = "VERIFIED"
            r = ["OK"]
            seq = frame["k"]["L"]
            b_rec = None
            stream_id = f"{args.symbol.lower()}@kline_1m"

        _eh, frame_raw_sha = raw_writer.append_raw_frame(
            json.dumps(frame), ing.observed_wall_utc_ms, ing.observed_monotonic_ns
        )

        ev = MarketEventV1(
            schema_version="market-event-v1",
            symbol=args.symbol,
            product=ALLOWED_PRODUCT,
            channel=channel,
            provider_event_ms=frame["E"],
            provider_transaction_ms=frame.get("T"),
            observed_wall_utc_ms=ing.observed_wall_utc_ms,
            observed_monotonic_ns=ing.observed_monotonic_ns,
            available_at_ms=ing.available_at_ms,
            source_stream_id=stream_id,
            connection_epoch=epoch,
            source_sequence=seq,
            payload_sha256=compute_sha256(frame),
            payload=frame,
            quality=q,
            reason_codes=r,
            raw_source_manifest_sha256=frame_raw_sha,
            book=b_rec,
        )
        writer.append_event(ev)

    # 4. Health event
    h_ev = health.create_health_event(
        current_wall_ms=ta.last_observed_wall_ms or 1728720000000,
        raw_manifest_sha256=raw_writer.manifest_sha256,
    )
    writer.append_event(h_ev)

    raw_writer.close()
    writer.close()

    summary = {
        "status": "FIXTURE_RECORDED_SUCCESS",
        "output_dir": str(out_dir),
        "total_records": writer.total_records_written,
        "head_hash": writer.head_hash,
        "raw_manifest_sha256": raw_writer.manifest_sha256,
        "manifest_sha256": writer.manifest_sha256,
    }
    print(json.dumps(summary, indent=2))
    return 0


def run_replay_mode(args: argparse.Namespace) -> int:
    """Run replay verification over saved immutable segment logs."""
    replay_dir = args.replay_dir or args.output_dir
    engine = ReplayEngine(data_dir=replay_dir, epoch=args.epoch)
    _events, witness = engine.replay_all(source=getattr(args, "replay_source", "auto"))
    print(json.dumps(witness.to_dict(), indent=2))
    return 0 if witness.depth_continuous else 1


def run_live_public_mode(args: argparse.Namespace) -> int:
    """Run bounded public-only live market stream recorder."""
    if args.network == "disabled":
        print(
            "ERROR: --mode live-public requires explicit opt-in flag '--network allow-public', 'public-direct', or 'public-clash-explicit'.",
            file=sys.stderr,
        )
        return 2

    if args.network == "public-clash-explicit":
        proxy_cfg = ProxyRouteConfig(
            mode="public-clash-explicit",
            kind=args.proxy_kind,
            host=args.proxy_host,
            port=args.proxy_port,
        )
    else:
        proxy_cfg = ProxyRouteConfig(mode="public-direct")

    client = BinancePublicFeedClient(
        symbol=args.symbol,
        network_mode=args.network,
        proxy_config=proxy_cfg,
    )
    out_dir = Path(args.output_dir)
    epoch = f"live-epoch-{args.symbol.lower()}"
    raw_writer = RawSegmentWriter(base_dir=out_dir, epoch=epoch)
    writer = SegmentWriter(base_dir=out_dir, epoch=epoch)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        stats = loop.run_until_complete(
            client.run_bounded_public_stream(
                duration_seconds=args.duration_seconds,
                raw_writer=raw_writer,
                event_writer=writer,
            )
        )
        print(json.dumps(stats, indent=2))
        return 0
    finally:
        raw_writer.close()
        writer.close()
        loop.close()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.symbol != ALLOWED_SYMBOL:
        print(f"ERROR: Forbidden symbol '{args.symbol}'. Must be '{ALLOWED_SYMBOL}'.", file=sys.stderr)
        return 1

    try:
        if args.mode == "fixture":
            return run_fixture_mode(args)
        elif args.mode == "replay":
            return run_replay_mode(args)
        elif args.mode == "live-public":
            return run_live_public_mode(args)
    except (ContractValidationError, NetworkGateError) as exc:
        print(f"CONTRACT ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"UNHANDLED ERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
