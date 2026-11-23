"""Local market cards and replay. The runtime has no order or network command."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from .adapter import ORIGINS, MarketSnapshotAdapter
from .engine import Engine, market_card
from .fixtures import AFTER_TRIGGER, EARLY, INITIAL, PULLBACK, FabricatedMarket
from .journal import MANUAL_ACTIONS, Journal
from .model import DEFAULT_POLICY, MINUTE, DecisionError, encode

HKT = timezone(timedelta(hours=8), "HKT")


def local_time(ms: int | None) -> str:
    if ms is None:
        return "unavailable"
    return datetime.fromtimestamp(ms / 1000, tz=HKT).isoformat(timespec="seconds")


def display_ratio(value: object) -> str:
    return "unknown" if value is None else f"{Decimal(str(value)):.3f}"


def render(card: dict[str, Any]) -> str:
    episode = card.get("episode") or {}
    plan = card.get("plan") or {}
    source = card.get("evaluation_receipt") or {}
    title = f"{card['symbol']}  {card['market_status']}  {card['evidence']}"
    lines = [title, f"Evaluation HKT {local_time(card['evaluated_ms'])}",
             f"Account {card['account_context_status']} / {card['account_overlay']}",
             f"Reasons {', '.join(card['reasons'])}"]
    if card.get("journal_recorded_wall_ms"):
        lines.append(f"Journal record HKT {local_time(card['journal_recorded_wall_ms'])}")
    if source:
        lines.append(f"Source {source['source_origin']} / publication {source['source_publication_sha256'][:16]}")
        for frame in ("1d", "4h", "1h", "15m", "5m"):
            end = card["frame_end_ms"].get(frame)
            lines.append(f"  {frame:<3} last completed {local_time(end)}")
    if episode:
        lines.extend([f"Episode {episode['episode_id']}  {episode['direction']} {episode['family']} rank {episode['rank']}",
                      f"  1h signal K {local_time(episode['signal_k']['end_ms'])}",
                      f"  Confirmation {episode['confirmation_line']} + directional buffer {episode['confirmation_buffer']} USDT",
                      f"  Independent 15m earliest opening {local_time(episode['earliest_trigger_open_ms'])}",
                      f"  Confirmed 15m {local_time((card.get('trigger') or {}).get('end_ms'))}",
                      f"  Absolute expiry {local_time(episode['expires_at_ms'])}"])
    if card.get("reprice"):
        row = card["reprice"]
        lines.append(f"Reprice +{row['requested_delay_minutes']}m, lateness {row['lateness_ms']}ms")
    if plan:
        lines.append(f"  Entry {plan['entry_low']}–{plan['entry_high']} USDT  Hard SL {plan['hard_stop']} USDT")
        for row in plan.get("targets", ()):
            text = f"{row.get('price')} USDT / net R {display_ratio(row.get('net_r'))}" if row["price"] else f"UNESTABLISHED ({row['reason']})"
            lines.append(f"  {row['label']} {text}")
        for frame in ("4h", "1d", "first"):
            obstacle = plan.get("obstacles", {}).get(frame)
            level, confirmed = (obstacle["price"], local_time(obstacle["confirmed_ms"])) if obstacle else ("unknown", "unavailable")
            lines.append(f"  {frame} obstacle {level} / confirmed {confirmed}")
        if "unit_stop_loss_usdt" in plan:
            lines.extend([f"  Entry fill assumption {plan['entry_fill']} USDT",
                          f"  Stressed stop fill {plan['expected_stop_stress_fill']} USDT",
                          f"  Stop loss {plan['unit_stop_loss_usdt']} USDT per base unit",
                          f"  Liquidity reference {plan['reference_rounded_base']} base units, {plan['reference_nominal_usdt']} USDT",
                          f"  Stop-risk reference cost {plan['reference_stop_loss_usdt']} USDT",
                          f"  Spread {plan['spread_usdt']} USDT; modeled funding crossings {plan['funding']['modeled_crossings']}",
                          f"  First obstacle after-cost R {display_ratio(plan['first_obstacle_after_cost_r'])}",
                          f"  Mark/index basis {plan['mark_index_basis_bps']} bps; OI change {plan['oi_period_change_fraction']}",
                          "  Conditional paths (no estimated probabilities)"])
            for path in plan["conditional_paths"]:
                lines.append(f"    {path['name']} {display_ratio(path['net_r'])} R")
    for name in ("quote", "depth", "oi", "oi_history", "mark", "funding"):
        row = card.get("card_context", {}).get(name)
        if row:
            lines.append(f"  {name:<10} receipt #{row['receipt_id']} / upper age {row['age_upper_ms']}ms")
    if card.get("source_issue"):
        lines.append(f"Source detail {card['source_issue']['detail']}")
    if card.get("next_human_action"):
        lines.append(card["next_human_action"])
    return "\n".join(lines) + "\n"


def demo(output: Path) -> dict[str, Any]:
    output.mkdir(exist_ok=False)
    examples = []
    cases = (
        ("pullback-long", PULLBACK, "LONG", "inside", "spread"),
        ("pullback-short", PULLBACK, "SHORT", "invalid", "inside"),
        ("early-long", EARLY, "LONG", "stale", "inside"),
        ("early-short", EARLY, "SHORT", "inside", "target_hit"),
    )
    for title, family, direction, plus5, plus10 in cases:
        case = output / title
        case.mkdir()
        feed = FabricatedMarket(case / "b1_fixture.sqlite", family, direction)
        feed.scan(INITIAL)
        db = case / "decision.sqlite"
        journal = Journal(db, create=True, policy=DEFAULT_POLICY)
        engine = Engine(MarketSnapshotAdapter(feed.path, "fixture"), journal)
        cards = [engine.evaluate("BTCUSDT")]
        feed.scan(AFTER_TRIGGER)
        active = engine.evaluate("BTCUSDT")
        if active["market_status"] != "EXECUTABLE":
            raise DecisionError("DEMO_TRIGGER_CASE_FAILED", title)
        cards.append(active)
        for plus, variant in ((5, plus5), (10, plus10)):
            sampled = feed.scan(AFTER_TRIGGER + plus * MINUTE + 1000, variant)
            cards.append(engine.evaluate("BTCUSDT", scan=sampled["scan_id"],
                                         as_of_ms=sampled["decision_as_of_venue_ms"],
                                         reprice_minutes=plus, episode_id=active["episode_id"]))
        manual = journal.manual(card_id=cards[2]["card_id"], operator_id="demo-operator-note", action="SKIP",
                                time_ms=cards[2]["evaluated_ms"] + 1000, note="Fabricated operator review.")
        replay = Journal(db)
        matches = all(item == replay.read(card_id=item["card_id"]) for item in cards)
        if not matches:
            raise DecisionError("DEMO_REPLAY_MISMATCH", title)
        for index, card in enumerate(cards):
            (case / f"card_{index}.json").write_text(json.dumps(card, indent=2) + "\n", encoding="utf-8")
            (case / f"card_{index}.txt").write_text(render(card), encoding="utf-8")
        (case / "events.json").write_text(json.dumps(replay.events(), indent=2) + "\n", encoding="utf-8")
        examples.append({"case": title, "family": family, "direction": direction, "episode_id": active["episode_id"],
                         "states": [item["market_status"] for item in cards],
                         "reprice_reasons": [item["reasons"] for item in cards[2:]],
                         "manual_evidence": manual["evidence"], "replay_equal": matches})
    summary = {"evidence": "SYNTHETIC_QA_ONLY", "examples": examples, "account": "UNAVAILABLE"}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def add_input(cmd: argparse.ArgumentParser) -> None:
    cmd.add_argument("--public-db", type=Path, required=True)
    cmd.add_argument("--origin", choices=ORIGINS, required=True)
    cmd.add_argument("--symbol", required=True)
    cmd.add_argument("--scan", type=int)
    cmd.add_argument("--as-of", type=int, help="venue epoch ms")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quant-decision-b2", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    demo_cmd = commands.add_parser("demo", help="generate synthetic cards and journal")
    demo_cmd.add_argument("--output", type=Path, required=True)
    for name in ("inspect", "evaluate", "reprice"):
        cmd = commands.add_parser(name)
        add_input(cmd)
        if name != "inspect":
            cmd.add_argument("--journal", type=Path, required=True)
        if name == "reprice":
            cmd.add_argument("--episode", required=True)
            cmd.add_argument("--plus", type=int, choices=(5, 10), required=True)
        cmd.add_argument("--json", action="store_true")
    read = commands.add_parser("read")
    read.add_argument("--journal", type=Path, required=True)
    read.add_argument("--card")
    read.add_argument("--episode")
    read.add_argument("--as-of", type=int)
    read.add_argument("--json", action="store_true")
    events = commands.add_parser("events")
    events.add_argument("--journal", type=Path, required=True)
    note = commands.add_parser("manual")
    note.add_argument("--journal", type=Path, required=True)
    note.add_argument("--card", required=True)
    note.add_argument("--operator-id", required=True)
    note.add_argument("--action", choices=sorted(MANUAL_ACTIONS), required=True)
    note.add_argument("--time", type=int, required=True)
    note.add_argument("--note", default="")
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            print(encode(demo(args.output)))
            return 0
        if args.command in ("read", "events", "manual"):
            journal = Journal(args.journal)
            if args.command == "events":
                print(encode(journal.events()))
                return 0
            if args.command == "manual":
                print(encode(journal.manual(card_id=args.card, operator_id=args.operator_id, action=args.action,
                                            time_ms=args.time, note=args.note)))
                return 0
            result = journal.read(card_id=args.card, episode_id=args.episode, as_of_ms=args.as_of)
            if result is None:
                raise DecisionError("CARD_UNKNOWN")
        else:
            adapter = MarketSnapshotAdapter(args.public_db, args.origin)
            if args.command == "inspect":
                result = market_card(adapter.read(args.symbol, scan=args.scan, as_of_ms=args.as_of))
            else:
                engine = Engine(adapter, Journal(args.journal, create=True, policy=DEFAULT_POLICY))
                result = engine.evaluate(args.symbol, scan=args.scan, as_of_ms=args.as_of,
                                         reprice_minutes=getattr(args, "plus", None), episode_id=getattr(args, "episode", None))
        if args.json:
            print(encode(result))
        else:
            print(render(result), end="")
        return 0
    except DecisionError as exc:
        print(encode({"error": exc.code, "detail": exc.detail}))
        return 2
    except (sqlite3.Error, OSError) as exc:
        print(encode({"error": "LOCAL_IO_FAILED", "detail": str(exc)}))
        return 2
