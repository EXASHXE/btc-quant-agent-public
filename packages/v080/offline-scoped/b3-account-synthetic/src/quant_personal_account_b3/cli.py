"""Local read-only B3 CLI for synthetic private snapshots, reconciliation, overlays, and journal replay.

No live network, real credential access, or Layer 3 order mutation commands exist.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .accounting import compute_accounting_report
from .b2_reader import ReadOnlyB2JournalReader
from .client import DisabledLiveHttpTransport, DisabledProductionCredentialProvider
from .fixtures import DEFAULT_SYNTHETIC_AS_OF_MS, SCENARIO_NAMES
from .models import (
    PRIVATE_CONNECTION_NOT_ACTIVATED,
    SYNTHETIC_BANNER_TEXT,
    AccountB3Error,
    encode,
)
from .service import (
    generate_and_publish_overlay,
    load_synthetic_scenario_into_store,
    run_offline_demo,
)
from .storage import MANUAL_TARGET_TYPES, OverlayJournal, PrivateAccountStore

HKT = timezone(timedelta(hours=8), "HKT")


def _fmt_hkt(ms: int | None) -> str:
    if ms is None:
        return "unavailable"
    return datetime.fromtimestamp(ms / 1000, tz=HKT).isoformat(timespec="seconds")


def render_overlay_text(overlay: dict[str, Any]) -> str:
    lines = [
        f"=== B3 ACCOUNT OVERLAY ({overlay['synthetic_banner']}) ===",
        f"Overlay ID:              {overlay['overlay_id']}",
        f"B2 Card / Episode:       {overlay['b2_card_id']} / {overlay['b2_episode_id']}",
        f"Symbol / B2 As-Of (HKT): {overlay['symbol']} / {_fmt_hkt(overlay['b2_evaluated_ms'])}",
        f"Market Setup Status:     {overlay['market_setup_status']} (B2 evidence: {overlay['b2_market_evidence']})",
        f"Account Context Status:  {overlay['account_context_status']} (real_account_connected={overlay['real_account_connected']})",
        f"Position Relation:       {overlay['position_relation']}",
        f"Protection Status:       {overlay['protection_status']}",
        f"Signal-Trade Match:      {overlay['signal_trade_match']}",
        f"Portfolio Limits / Size: {overlay['portfolio_exposure_limits']} / safe_size={overlay['safe_position_size']}",
        f"Layer 3 Trade Execution: {overlay['layer3_trade_execution']}",
    ]
    if overlay.get("position_context"):
        lines.append("Active Position Legs:")
        for leg in overlay["position_context"]:
            lines.append(
                f"  - {leg['symbol']} {leg['position_side']} ({leg['position_mode']}) {leg['direction']} "
                f"qty={leg['quantity']} entry={leg['entry_price']} mark={leg['mark_price']} "
                f"upnl={leg['unrealized_pnl']} liq={leg['liquidation_price']} "
                f"prot={leg['protection_status']} sl_cov={leg['sl_covered_qty']} uncovered={leg['uncovered_qty']}"
            )
    recon = overlay.get("accounting_reconciliation", {})
    cc = recon.get("reconciliation_cross_check", {})
    r_info = (recon.get("actual_vs_b2_projected") or {}).get("planned_vs_realized_net_r", {})
    lines.append(
        f"Accounting Coverage / Recon: {recon.get('coverage_status')} / {cc.get('status')} | "
        f"Realized Net R: {r_info.get('realized_net_r_status')} ({r_info.get('realized_net_r')})"
    )
    ha = overlay.get("human_actionability", {})
    lines.append("Warnings:")
    for w in ha.get("warnings", []):
        lines.append(f"  ! {w}")
    lines.append("Manual Next Checks:")
    for c in ha.get("manual_next_checks", []):
        lines.append(f"  * {c}")
    return "\n".join(lines) + "\n"


def render_coverage_text(snapshot_dict: dict[str, Any]) -> str:
    lines = [
        f"=== B3 ENDPOINT COVERAGE ({snapshot_dict['synthetic_banner']}) ===",
        f"Snapshot ID:     {snapshot_dict['snapshot_id']} ({snapshot_dict['snapshot_mode']})",
        f"As-Of (HKT):     {_fmt_hkt(snapshot_dict['as_of_venue_ms'])}",
        f"Overall Status:  {snapshot_dict['overall_status']}",
    ]
    for ep, cov in sorted(snapshot_dict.get("endpoint_coverage", {}).items()):
        lines.append(
            f"  {ep:<24} status={cov['status']:<17} age_ms={cov['age_ms']} "
            f"pages={cov['pages_fetched']} complete={cov['page_coverage_complete']} "
            f"rows={cov['record_count']} err={cov['error_code']}"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quant-account-b3", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    load_cmd = sub.add_parser("load-snapshot", help="load a synthetic private fixture snapshot into B3 store")
    load_cmd.add_argument("--scenario", choices=SCENARIO_NAMES, required=True)
    load_cmd.add_argument("--private-db", type=Path, required=True)
    load_cmd.add_argument("--symbol", default="BTCUSDT")
    load_cmd.add_argument("--episode-id")
    load_cmd.add_argument("--as-of", type=int, default=DEFAULT_SYNTHETIC_AS_OF_MS)
    load_cmd.add_argument("--json", action="store_true")

    acct_cmd = sub.add_parser("show-account", help="read normalized synthetic account/positions/orders/fills/income")
    acct_cmd.add_argument("--private-db", type=Path, required=True)
    acct_cmd.add_argument("--snapshot-id")
    acct_cmd.add_argument("--json", action="store_true")

    cov_cmd = sub.add_parser("coverage", help="show per-endpoint NON_ATOMIC coverage and freshness")
    cov_cmd.add_argument("--private-db", type=Path, required=True)
    cov_cmd.add_argument("--snapshot-id")
    cov_cmd.add_argument("--json", action="store_true")

    rec_cmd = sub.add_parser("reconcile", help="show canonical accounting reconciliation and ledger views")
    rec_cmd.add_argument("--private-db", type=Path, required=True)
    rec_cmd.add_argument("--snapshot-id")
    rec_cmd.add_argument("--symbol")
    rec_cmd.add_argument("--b2-journal", type=Path)
    rec_cmd.add_argument("--card-id")
    rec_cmd.add_argument("--json", action="store_true")

    ov_cmd = sub.add_parser("overlay", help="generate & publish B3 overlay for a verified read-only B2 card")
    ov_cmd.add_argument("--b2-journal", type=Path, required=True)
    ov_cmd.add_argument("--overlay-journal", type=Path, required=True)
    ov_cmd.add_argument("--private-db", type=Path)
    ov_cmd.add_argument("--card-id")
    ov_cmd.add_argument("--episode-id")
    ov_cmd.add_argument("--symbol")
    ov_cmd.add_argument("--snapshot-id")
    ov_cmd.add_argument("--json", action="store_true")

    jr_cmd = sub.add_parser("journal-read", help="read a committed B3 overlay from journal without recomputing")
    jr_cmd.add_argument("--overlay-journal", type=Path, required=True)
    jr_cmd.add_argument("--overlay-id")
    jr_cmd.add_argument("--card-id")
    jr_cmd.add_argument("--episode-id")
    jr_cmd.add_argument("--json", action="store_true")

    rep_cmd = sub.add_parser("journal-replay", help="verify and replay all overlays and SHA-linked events")
    rep_cmd.add_argument("--overlay-journal", type=Path, required=True)
    rep_cmd.add_argument("--json", action="store_true")

    ml_cmd = sub.add_parser("manual-link", help="record an immutable OWNER_ENTERED episode-to-order/trade association")
    ml_cmd.add_argument("--private-db", type=Path, required=True)
    ml_cmd.add_argument("--operator-id", required=True)
    ml_cmd.add_argument("--episode-id", required=True)
    ml_cmd.add_argument("--card-id")
    ml_cmd.add_argument("--symbol", required=True)
    ml_cmd.add_argument("--target-type", choices=sorted(MANUAL_TARGET_TYPES), required=True)
    ml_cmd.add_argument("--target-id", required=True)
    ml_cmd.add_argument("--time", type=int, required=True)
    ml_cmd.add_argument("--note", default="")

    demo_cmd = sub.add_parser("demo", help="run complete offline synthetic B3 demo across all scenarios")
    demo_cmd.add_argument("--output", type=Path, required=True)
    demo_cmd.add_argument("--b2-journal", type=Path)

    sub.add_parser("live-connect", help="disabled live private connection gate (always returns PRIVATE_CONNECTION_NOT_ACTIVATED)")

    args = parser.parse_args(argv)
    try:
        if args.command == "live-connect":
            # Explicitly exercise disabled production stubs; always fails closed.
            _ = DisabledLiveHttpTransport()
            DisabledProductionCredentialProvider().get_credentials()
            return 2

        if args.command == "demo":
            summary = run_offline_demo(args.output, existing_b2_journal=args.b2_journal)
            print(encode(summary))
            return 0

        if args.command == "load-snapshot":
            snap = load_synthetic_scenario_into_store(
                scenario=args.scenario,
                private_db=args.private_db,
                symbol=args.symbol,
                episode_id=args.episode_id,
                as_of_venue_ms=args.as_of,
            )
            data = snap.to_dict()
            print(encode(data) if args.json else render_coverage_text(data), end="" if not args.json else "\n")
            return 0

        if args.command == "show-account":
            store = PrivateAccountStore(args.private_db, create=False)
            snap_opt = store.load_snapshot(snapshot_id=args.snapshot_id)
            if snap_opt is None:
                raise AccountB3Error("SNAPSHOT_NOT_FOUND")
            data = snap_opt.to_dict()
            print(encode(data) if args.json else json.dumps(data, indent=2))
            return 0

        if args.command == "coverage":
            store = PrivateAccountStore(args.private_db, create=False)
            snap_opt = store.load_snapshot(snapshot_id=args.snapshot_id)
            if snap_opt is None:
                raise AccountB3Error("SNAPSHOT_NOT_FOUND")
            data = snap_opt.to_dict()
            cov_payload = {
                "synthetic_banner": SYNTHETIC_BANNER_TEXT,
                "snapshot_id": data["snapshot_id"],
                "snapshot_mode": data["snapshot_mode"],
                "as_of_venue_ms": data["as_of_venue_ms"],
                "overall_status": data["overall_status"],
                "endpoint_coverage": data["endpoint_coverage"],
            }
            print(encode(cov_payload) if args.json else render_coverage_text(data), end="" if not args.json else "\n")
            return 0

        if args.command == "reconcile":
            store = PrivateAccountStore(args.private_db, create=False)
            snap_opt = store.load_snapshot(snapshot_id=args.snapshot_id)
            card = None
            if args.b2_journal is not None:
                b2_view = ReadOnlyB2JournalReader(args.b2_journal).load_and_verify()
                card = b2_view.get_card(card_id=args.card_id, symbol=args.symbol)
            report = compute_accounting_report(snap_opt, card=card, symbol_filter=args.symbol)
            data = report.to_dict()
            print(encode(data) if args.json else json.dumps(data, indent=2))
            return 0

        if args.command == "overlay":
            overlay = generate_and_publish_overlay(
                b2_journal_path=args.b2_journal,
                overlay_journal_path=args.overlay_journal,
                private_db_path=args.private_db,
                card_id=args.card_id,
                episode_id=args.episode_id,
                symbol=args.symbol,
                snapshot_id=args.snapshot_id,
            )
            print(encode(overlay) if args.json else render_overlay_text(overlay), end="" if not args.json else "\n")
            return 0

        if args.command == "journal-read":
            journal = OverlayJournal(args.overlay_journal, create=False)
            overlay_opt = journal.read(
                overlay_id=args.overlay_id,
                b2_card_id=args.card_id,
                b2_episode_id=args.episode_id,
            )
            if overlay_opt is None:
                raise AccountB3Error("OVERLAY_NOT_FOUND")
            print(
                encode(overlay_opt) if args.json else render_overlay_text(overlay_opt),
                end="" if not args.json else "\n",
            )
            return 0

        if args.command == "journal-replay":
            journal = OverlayJournal(args.overlay_journal, create=False)
            replay = journal.replay()
            print(encode(replay) if args.json else json.dumps(replay, indent=2))
            return 0

        if args.command == "manual-link":
            store = PrivateAccountStore(args.private_db, create=True)
            assoc = store.record_manual_association(
                operator_id=args.operator_id,
                b2_episode_id=args.episode_id,
                b2_card_id=args.card_id,
                symbol=args.symbol,
                target_type=args.target_type,
                target_id=args.target_id,
                owner_reported_venue_ms=args.time,
                note=args.note,
            )
            print(encode(assoc.to_dict()))
            return 0

        raise AccountB3Error(PRIVATE_CONNECTION_NOT_ACTIVATED, "Unknown command")
    except AccountB3Error as exc:
        print(encode({"error": exc.code, "detail": exc.detail}))
        return 2
    except (sqlite3.Error, OSError) as exc:
        print(encode({"error": "LOCAL_IO_FAILED", "detail": str(exc)}))
        return 2
