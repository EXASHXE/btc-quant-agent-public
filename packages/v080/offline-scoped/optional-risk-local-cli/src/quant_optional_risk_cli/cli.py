"""Local read-only WSL2 Core + optional account-risk CLI (zero Hermes, zero Feishu, zero LLM)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .config import default_disabled_config, load_config_file
from .core_reader import build_card_presentation, load_verified_core_journal
from .models import (
    DEFAULT_FRESHNESS_TTL_MS,
    OptionalRiskError,
    install_offline_network_guard,
)
from .overlay import LatchStore, evaluate_optional_account_overlay
from .parser import load_structured_file

LIVE_GATES = {
    "layer2-private": "LAYER2_PRIVATE_USER_DATA_DISABLED_NOT_AUTHORIZED",
    "layer3-trade": "LAYER3_TRADE_EXECUTION_DISABLED_UNREACHABLE",
    "binance-live": "REAL_BINANCE_API_NOT_AUTHORIZED",
    "feishu-live": "REAL_FEISHU_CHANNEL_NOT_AUTHORIZED",
}


def format_human_card_report(presentation: dict[str, Any], overlay: dict[str, Any]) -> str:
    """Format verified Core card & separated optional account overlay for Owner WSL2 console."""
    plan = presentation.get("immutable_core_plan")
    obs = presentation["observation_time"]
    exp = presentation["absolute_expiry"]
    frozen = presentation["core_frozen_account"]
    lines = [
        f"Symbol: {presentation['symbol']} | Direction: {presentation['direction']} | Market Status: {presentation['market_status']}",
        f"Market Reasons: {', '.join(presentation['reasons']) or 'NONE'}",
        f"Timeframes: {presentation['timeframe_anchor']}",
    ]
    for tf, info in presentation["frame_end_times"].items():
        lines.append(f"  {tf:<3} closed: {info['utc']} (HKT {info['hkt']})")
    lines.extend(
        [
            f"Data Origin Category: {presentation['evidence_category']} (genuine_qualified={presentation['is_genuine_qualified']})",
            f"Source Origin: {presentation['source_origin']} | Publication SHA256: {presentation['source_publication_sha256']}",
            f"Observation Time: UTC {obs['utc']} | HKT {obs['hkt']}",
            f"Freshness: {presentation['freshness_state']} (TTL {presentation['freshness_ttl_ms']}ms)",
            f"Absolute Expiry: UTC {exp['utc']} | HKT {exp['hkt']} (expired={presentation['is_expired']})",
        ]
    )
    if presentation.get("source_issue"):
        lines.append(f"Source Issue: {presentation['source_issue']}")
    if plan is not None:
        lines.append(
            f"Immutable Core Plan: Entry {plan['entry_low']}..{plan['entry_high']} | Hard Stop {plan['hard_stop']}"
        )
        for tgt in plan["targets"]:
            t_txt = (
                f"{tgt['price']} (net R {tgt['net_r']})"
                if tgt["price"]
                else f"UNESTABLISHED ({tgt['reason']})"
            )
            lines.append(f"  {tgt['label']}: {t_txt}")
    else:
        lines.append("Immutable Core Plan: NONE (no entry/stop/TP invented)")

    lines.extend(
        [
            "--- Optional Account Risk Overlay (Strictly Separate from Market Status) ---",
            f"Overlay Mode: {overlay['overlay_mode']} | Policy Status: {overlay['policy_status']}",
            f"Core Market Status Unchanged: {overlay['core_market_status']} (unchanged={overlay['core_market_status_unchanged']})",
            f"Account Overlay Eligibility: {overlay['account_risk_eligibility']}",
            f"Frozen V1 Core Account Fields: status={frozen['account_context_status']} | overlay={frozen['account_overlay']} | safe_size={frozen['safe_position_size']}",
            f"Approved Real Position Size: {overlay['approved_real_position_size']} (real_safe_position_size={overlay['real_safe_position_size']})",
            f"Layer2 PRIVATE_USER_DATA: {overlay['layer2_private_user_data']} | Layer3 TRADE: {overlay['layer3_trade_execution']}",
            f"Overlay Reasons: {', '.join(overlay['reasons'])}",
        ]
    )
    if overlay.get("modeled_metrics"):
        m = overlay["modeled_metrics"]
        lines.append(
            f"Modeled Synthetic Only: E0={m.get('opening_equity')} Et={m.get('current_equity')} "
            f"day_loss={m.get('daily_loss_fraction')} qty={m.get('modeled_candidate_qty')}"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    install_offline_network_guard()
    parser = argparse.ArgumentParser(
        prog="quant-local-cli",
        description="Local offline WSL2 Core reader and optional account-risk config/fixture CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    for cmd_name in ("config-show", "config-validate"):
        p = sub.add_parser(cmd_name)
        p.add_argument("--config", type=Path)
        p.add_argument("--expected-sha256")
        p.add_argument("--expected-version")
        p.add_argument("--allow-synthetic-opt-in", action="store_true")
        p.add_argument("--json", action="store_true")

    cards_p = sub.add_parser("cards")
    cards_p.add_argument("--journal", type=Path, required=True)
    cards_p.add_argument("--symbol")
    cards_p.add_argument("--limit", type=int)
    cards_p.add_argument("--json", action="store_true")

    inspect_p = sub.add_parser("inspect-card")
    inspect_p.add_argument("--journal", type=Path, required=True)
    inspect_p.add_argument("--card")
    inspect_p.add_argument("--episode")
    inspect_p.add_argument("--symbol")
    inspect_p.add_argument("--config", type=Path)
    inspect_p.add_argument("--expected-sha256")
    inspect_p.add_argument("--expected-version")
    inspect_p.add_argument("--allow-synthetic-opt-in", action="store_true")
    inspect_p.add_argument("--synthetic-fixture", type=Path)
    inspect_p.add_argument("--latch-db", type=Path)
    inspect_p.add_argument("--as-of", type=int)
    inspect_p.add_argument("--freshness-ttl-ms", type=int, default=DEFAULT_FRESHNESS_TTL_MS)
    inspect_p.add_argument("--candidate-qty")
    inspect_p.add_argument("--json", action="store_true")

    gate_p = sub.add_parser("check-live-gate")
    gate_p.add_argument("--target", choices=sorted(LIVE_GATES), required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "check-live-gate":
            print(f"BLOCKED_OFFLINE_ONLY {LIVE_GATES[args.target]}", file=sys.stderr)
            return 3

        if args.command in ("config-show", "config-validate"):
            cfg = (
                load_config_file(
                    args.config,
                    expected_sha256=args.expected_sha256,
                    expected_config_version=args.expected_version,
                    allow_enabled_opt_in=args.allow_synthetic_opt_in,
                )
                if args.config is not None
                else default_disabled_config()
            )
            payload = cfg.to_dict()
            if args.json:
                print(json.dumps(payload, indent=2, sort_keys=True))
            else:
                ar = cfg.account_risk
                print(
                    f"Config Version: {cfg.config_version} ({cfg.schema_version})\n"
                    f"Config SHA256: {cfg.config_sha256}\n"
                    f"Source: {cfg.source} | Review Status: {cfg.review_status}\n"
                    f"Optional Account Risk Enabled: {ar.enabled}\n"
                    f"Per-Trade Default/Max: {ar.per_trade_default} / {ar.per_trade_max}\n"
                    f"BTC/ETH Default/Band/Max: {ar.btc_eth_default_leverage}x / {ar.btc_eth_normal_band[0]}-{ar.btc_eth_normal_band[1]}x / {ar.btc_eth_exceptional_max}x\n"
                    f"SOL/Other Default/Max: {ar.sol_other_default_leverage}x / {ar.sol_other_max_leverage}x\n"
                    f"Proposed Daily Stop/Halt: {ar.daily_stop} / {ar.daily_halt}\n"
                    f"Layer2 PRIVATE_USER_DATA: {cfg.layer2_private_user_data} | Layer3 TRADE: {cfg.layer3_trade_execution}"
                )
            return 0

        journal = load_verified_core_journal(args.journal)
        if args.command == "cards":
            cards = journal.list_cards(symbol=args.symbol, limit=args.limit)
            summaries = [
                {
                    "card_id": c["card_id"],
                    "symbol": c["symbol"],
                    "market_status": c["market_status"],
                    "evaluated_ms": c["evaluated_ms"],
                    "evidence": c["evidence"],
                    "episode_id": c.get("episode_id"),
                }
                for c in cards
            ]
            if args.json:
                print(json.dumps(summaries, indent=2, sort_keys=True))
            else:
                for row in summaries:
                    print(
                        f"{row['card_id'][:12]}  {row['symbol']:<8}  {row['market_status']:<14}  "
                        f"{row['evidence']:<18}  ep={row['episode_id']}"
                    )
            return 0

        card = journal.select_card(card_id=args.card, episode_id=args.episode, symbol=args.symbol)
        cfg = (
            load_config_file(
                args.config,
                expected_sha256=args.expected_sha256,
                expected_config_version=args.expected_version,
                allow_enabled_opt_in=args.allow_synthetic_opt_in,
            )
            if args.config is not None
            else default_disabled_config()
        )
        fixture = (
            load_structured_file(args.synthetic_fixture)
            if args.synthetic_fixture is not None
            else None
        )
        latch = LatchStore(args.latch_db) if args.latch_db is not None else None
        presentation = build_card_presentation(
            card, as_of_ms=args.as_of, freshness_ttl_ms=args.freshness_ttl_ms
        )
        overlay = evaluate_optional_account_overlay(
            card,
            cfg,
            synthetic_fixture=fixture,
            latch_store=latch,
            as_of_ms=args.as_of,
            candidate_qty=args.candidate_qty,
        )
        if args.json:
            print(
                json.dumps(
                    {"presentation": presentation, "overlay": overlay}, indent=2, sort_keys=True
                )
            )
        else:
            print(format_human_card_report(presentation, overlay), end="")
        return 0
    except OptionalRiskError as exc:
        print(json.dumps({"error": exc.code, "detail": exc.detail}, sort_keys=True))
        return 2
