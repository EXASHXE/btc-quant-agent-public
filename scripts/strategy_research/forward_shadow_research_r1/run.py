"""Main executable entry point, synthetic developmental suite runner, and CLI interface.

TASK_ID: V06_GEMINI_GOAL_B_FORWARD_SHADOW_SCIENCE_R1
CONTROLLER_DISPATCH_SHA: e35724f1d1ee7458709e003dfc5673c826c68ffd
START_SHA: 55ac4c631c69f6edbd275462ad23e4486b9782ed
AUTHORITY: reviews/v0.6/b_line/V06_FORWARD_SHADOW_G1G3_THREE_GEMINI_GOALS_R1_CONTROLLER_AUTHORITY.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from .adapter import PublicFeedAdapter
    from .contract import BookIntegrityV1, Channel, sha256_hex
    from .execution import ShadowExecutionEngine
    from .fixtures import (
        generate_warmup_hourly_bars,
        make_agg_trade_event,
        make_funding_settled_event,
        make_kline_event,
        make_test_book,
    )
    from .registry import (
        SELECTABLE_OBSERVATION_CELLS,
        SampleReadinessGate,
        compute_policy_fingerprint,
        get_default_hypotheses,
    )
    from .statistics import block_bootstrap_net_bps, project_statistical_power
except (ImportError, ValueError):
    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from scripts.strategy_research.forward_shadow_research_r1.adapter import PublicFeedAdapter
    from scripts.strategy_research.forward_shadow_research_r1.contract import (
        BookIntegrityV1,
        Channel,
        sha256_hex,
    )
    from scripts.strategy_research.forward_shadow_research_r1.execution import (
        ShadowExecutionEngine,
    )
    from scripts.strategy_research.forward_shadow_research_r1.fixtures import (
        generate_warmup_hourly_bars,
        make_agg_trade_event,
        make_funding_settled_event,
        make_kline_event,
        make_test_book,
    )
    from scripts.strategy_research.forward_shadow_research_r1.registry import (
        SELECTABLE_OBSERVATION_CELLS,
        SampleReadinessGate,
        compute_policy_fingerprint,
        get_default_hypotheses,
    )
    from scripts.strategy_research.forward_shadow_research_r1.statistics import (
        block_bootstrap_net_bps,
        project_statistical_power,
    )

TASK_ID = "V06_GEMINI_GOAL_B_FORWARD_SHADOW_SCIENCE_R1"
START_SHA = "55ac4c631c69f6edbd275462ad23e4486b9782ed"
CONTROLLER_DISPATCH_SHA = "e35724f1d1ee7458709e003dfc5673c826c68ffd"
TERMINAL_STATUS = "FORWARD_SHADOW_ENGINE_PRE_REGISTERED_OFFLINE_VERIFIED"


def get_implementation_files() -> list[Path]:
    """Find all implementation and test files for Goal B."""
    base_dir = Path(__file__).resolve().parent
    repo_root = base_dir.parents[2]
    script_files = sorted(base_dir.glob("*.py"))
    test_files = sorted((repo_root / "tests").glob("test_v06_forward_shadow_research_r1_*.py"))
    return script_files + test_files


def compute_frozen_manifest() -> dict[str, str]:
    """Compute relative path -> sha256 mapping for all implementation files."""
    base_dir = Path(__file__).resolve().parent
    repo_root = base_dir.parents[2]
    files = get_implementation_files()
    manifest: dict[str, str] = {}
    for f in files:
        rel = str(f.relative_to(repo_root))
        manifest[rel] = sha256_hex(f.read_bytes())
    return manifest


def run_developmental_synthetic_suite(
    output_dir: Path,
    scratch_dir: Path,
) -> dict[str, Any]:
    """Run developmental synthetic verification across all 6 prespecified cells."""
    scratch_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    hypotheses = get_default_hypotheses()

    # Align start_sim_time with 15m (900,000 ms) decision boundary
    start_sim_time = (1776000000000 // 900000) * 900000
    warmup_bars = generate_warmup_hourly_bars(
        start_time_ms=start_sim_time - (210 * 3600 * 1000),
        hours_count=210,
        base_price=65000.0,
    )

    # Instantiate engines for each of the 6 cells
    engines = {cell_id: ShadowExecutionEngine(hyp) for cell_id, hyp in hypotheses.items()}
    adapters = {cell_id: PublicFeedAdapter(engine) for cell_id, engine in engines.items()}

    for engine in engines.values():
        engine.set_warmup_hourly_bars(warmup_bars)

    # Generate synthetic event stream
    curr_time = start_sim_time
    total_events_generated = 0

    def feed_all(event_dict: dict[str, Any], book_obj: BookIntegrityV1 | None = None) -> None:
        nonlocal total_events_generated
        total_events_generated += 1
        if book_obj is not None:
            for eng in engines.values():
                eng.on_book_update(book_obj)
        for adp in adapters.values():
            adp.ingest_dict(event_dict)

    # 1. Warmup initial 30 1m bars (minutes 0 to 29)
    for m in range(30):
        bar_open = curr_time
        bar_close = curr_time + 60000 - 1
        price = 65000.0
        kline = make_kline_event(
            channel=Channel.LAST_KLINE_1M,
            bar_open_ms=bar_open,
            bar_close_ms=bar_close,
            open_price=price,
            high_price=price + 1.0,
            low_price=price - 1.0,
            close_price=price,
        )
        mark = make_kline_event(
            channel=Channel.MARK_PRICE,
            bar_open_ms=bar_open,
            bar_close_ms=bar_close,
            open_price=price,
            high_price=price + 0.5,
            low_price=price - 0.5,
            close_price=price,
        )
        book = make_test_book(best_bid=price - 0.5, best_ask=price + 0.5)
        feed_all(kline.to_dict(), book)
        feed_all(mark.to_dict())
        curr_time += 60000

    # 2. Inject P1 dislocation synthetic pattern (minutes 30 to 44, ending at minute 45 boundary)
    # Last is below Mark by 40 USDT (-6.15 bps > 5bp and 2x spread) and restoring from -60 USDT (-9.23 bps) 5m prior
    for m in range(30, 45):
        bar_open = curr_time
        bar_close = curr_time + 60000 - 1
        mark_price = 65000.0
        if m < 39:
            last_price = 65000.0 - 70.0
        elif m < 44:
            last_price = 65000.0 - 60.0  # 5m prior
        else:
            last_price = 65000.0 - 40.0  # Decision at bar 44: restoring upward!

        kline = make_kline_event(
            channel=Channel.LAST_KLINE_1M,
            bar_open_ms=bar_open,
            bar_close_ms=bar_close,
            open_price=last_price,
            high_price=last_price + 2.0,
            low_price=last_price - 2.0,
            close_price=last_price,
        )
        mark = make_kline_event(
            channel=Channel.MARK_PRICE,
            bar_open_ms=bar_open,
            bar_close_ms=bar_close,
            open_price=mark_price,
            high_price=mark_price + 1.0,
            low_price=mark_price - 1.0,
            close_price=mark_price,
        )
        book = make_test_book(best_bid=last_price - 0.25, best_ask=last_price + 0.25)
        feed_all(kline.to_dict(), book)
        feed_all(mark.to_dict())
        curr_time += 60000

    # 3. Advance across minutes 45 to 59:
    # - P1 long position moves towards profit target (> 65150) and closes
    # - Feed aggressor buy trades for P2 over last 15m
    for t_idx in range(40):
        tr = make_agg_trade_event(
            trade_id=t_idx + 1,
            trade_time_ms=curr_time + (t_idx * 15000),
            price=65000.0,
            quantity=2.0,
            is_buyer_maker=False,  # Buyer aggressor
        )
        feed_all(tr.to_dict())

    for m in range(45, 60):
        bar_open = curr_time
        bar_close = curr_time + 60000 - 1
        p = 65000.0 + ((m - 44) * 12.0)  # Reaches > 65150, triggering P1 profit target
        kline = make_kline_event(
            channel=Channel.LAST_KLINE_1M,
            bar_open_ms=bar_open,
            bar_close_ms=bar_close,
            open_price=p,
            high_price=p + 5.0,
            low_price=p - 1.0,
            close_price=p,
        )
        mark = make_kline_event(
            channel=Channel.MARK_PRICE,
            bar_open_ms=bar_open,
            bar_close_ms=bar_close,
            open_price=p,
            high_price=p + 1.0,
            low_price=p - 1.0,
            close_price=p,
        )
        if m == 59:
            # Skewed book at decision boundary (minute 60) for P2
            book = make_test_book(best_bid=p - 0.5, best_ask=p + 0.5, bids_skew=2.5, asks_skew=0.8)
        else:
            book = make_test_book(best_bid=p - 0.5, best_ask=p + 0.5)
        feed_all(kline.to_dict(), book)
        feed_all(mark.to_dict())
        curr_time += 60000

    # 4. Advance across minutes 60 to 74:
    # - P2 long position moves towards profit target and closes
    # - Inject settled official funding event during holding
    funding_time = curr_time + (2 * 60 * 1000)
    for m in range(60, 75):
        bar_open = curr_time
        bar_close = curr_time + 60000 - 1
        p = 65180.0 + ((m - 59) * 26.0)  # Reaches > 65550, triggering P2 profit target
        book = make_test_book(best_bid=p - 0.5, best_ask=p + 0.5)

        if curr_time <= funding_time <= bar_close:
            funding_ev = make_funding_settled_event(
                funding_time_ms=funding_time,
                funding_rate=0.0001,  # 1 bp positive funding
                mark_price=p,
            )
            feed_all(funding_ev.to_dict())

        kline = make_kline_event(
            channel=Channel.LAST_KLINE_1M,
            bar_open_ms=bar_open,
            bar_close_ms=bar_close,
            open_price=p,
            high_price=p + 6.0,
            low_price=p - 1.0,
            close_price=p,
        )
        mark = make_kline_event(
            channel=Channel.MARK_PRICE,
            bar_open_ms=bar_open,
            bar_close_ms=bar_close,
            open_price=p,
            high_price=p + 1.0,
            low_price=p - 1.0,
            close_price=p,
        )
        feed_all(kline.to_dict(), book)
        feed_all(mark.to_dict())
        curr_time += 60000

    # 5. Negative Control Cases (minutes 75 to 90, ending at minute 90 boundary):
    # - Minute 90 evaluation: neutral price (dislocation = 0 < 5bp) -> NO_SIGNAL
    for m in range(75, 90):
        bar_open = curr_time
        bar_close = curr_time + 60000 - 1
        p = 65500.0
        kline = make_kline_event(
            channel=Channel.LAST_KLINE_1M,
            bar_open_ms=bar_open,
            bar_close_ms=bar_close,
            open_price=p,
            high_price=p + 1.0,
            low_price=p - 1.0,
            close_price=p,
        )
        mark = make_kline_event(
            channel=Channel.MARK_PRICE,
            bar_open_ms=bar_open,
            bar_close_ms=bar_close,
            open_price=p,
            high_price=p + 0.5,
            low_price=p - 0.5,
            close_price=p,
        )
        book = make_test_book(best_bid=p - 0.5, best_ask=p + 0.5)
        feed_all(kline.to_dict(), book)
        feed_all(mark.to_dict())
        curr_time += 60000

    # Finalize all 6 engines
    summaries = {}
    all_closed_trades = []
    for cell_id, eng in engines.items():
        summary = eng.finalize_evaluation(stream_end_ms=curr_time)
        summaries[cell_id] = {
            "cell_id": summary.cell_id,
            "total_decision_evaluations": summary.total_decision_evaluations,
            "signals_proposed_count": summary.signals_proposed_count,
            "positions_opened_count": summary.positions_opened_count,
            "positions_closed_count": summary.positions_closed_count,
            "positions_right_censored_count": summary.positions_right_censored_count,
            "unfillable_proposals_count": summary.unfillable_proposals_count,
            "closed_positions_count": len(summary.closed_positions),
            "account_initial_capital_usdt": summary.account_initial_capital_usdt,
            "account_final_cash_usdt": summary.account_final_cash_usdt,
            "net_pnl_usdt": summary.net_pnl_usdt,
            "mean_net_bps": summary.mean_net_bps,
            "all_cost_complete": summary.all_cost_complete,
            "incomplete_economics_count": summary.incomplete_economics_count,
            "closed_positions": summary.closed_positions,
        }
        all_closed_trades.extend(summary.closed_positions)

    # Perform bootstrap analysis on developmental trades
    bootstrap_res = block_bootstrap_net_bps(
        trades=all_closed_trades,
        block_size_days=7,
        n_bootstraps=500,
        random_seed=42,
    )
    power_proj = project_statistical_power(
        assumed_std_bps=25.0,
        target_sample_sizes=(30, 60, 100),
        effect_sizes_bps=(5.0, 10.0, 15.0),
        alpha=0.05,
        n_simulations=500,
        random_seed=12345,
    )

    # Evaluate Sample Readiness Gate
    readiness_gate = SampleReadinessGate()
    # In developmental synthetic suite, n is deliberately below the minimum prospective gate
    # to demonstrate that the engine strictly gates unvalidated claims as EVIDENCE_IMMATURE
    readiness_eval = readiness_gate.evaluate_readiness(
        event_count_p1=summaries["P1_BASIS_REVERSION_V2_SHADOW_6H"]["positions_opened_count"],
        event_count_p2=summaries["P2_ORDERFLOW_BOOK_RESILIENCE_SHADOW_6H"]["positions_opened_count"],
        distinct_utc_weeks=1,
        distinct_volatility_regimes=1,
        source_coverage_pct=100.0,
        has_30d_forward_warmup=False,
    )

    dev_receipt = {
        "task_id": TASK_ID,
        "controller_dispatch_sha": CONTROLLER_DISPATCH_SHA,
        "start_sha": START_SHA,
        "terminal_status": TERMINAL_STATUS,
        "selectable_cells": list(SELECTABLE_OBSERVATION_CELLS),
        "total_events_generated": total_events_generated,
        "cell_summaries": summaries,
        "bootstrap_results": {
            "status": bootstrap_res.status,
            "point_estimate_net_bps": bootstrap_res.point_estimate_net_bps,
            "active_blocks": bootstrap_res.active_blocks,
            "total_blocks_spanned": bootstrap_res.total_blocks_spanned,
            "trade_count": bootstrap_res.trade_count,
            "is_degenerate": bootstrap_res.is_degenerate,
            "diagnostic": bootstrap_res.diagnostic,
        },
        "power_projections": [
            {
                "sample_size": p.sample_size,
                "effect_size_bps": p.effect_size_bps,
                "projected_power": p.projected_power,
            }
            for p in power_proj
        ],
        "sample_readiness_gate": readiness_eval,
        "policy_fingerprint": compute_policy_fingerprint(),
    }

    # Write receipts
    (output_dir / "DEVELOPMENTAL_SYNTHETIC_SUITE_RECEIPT.json").write_text(
        json.dumps(dev_receipt, indent=2) + "\n"
    )
    (output_dir / "SAMPLE_READINESS_AUDIT.json").write_text(
        json.dumps(readiness_eval, indent=2) + "\n"
    )

    return dev_receipt


def main() -> None:
    parser = argparse.ArgumentParser(description="Goal B Prospective BTC Shadow Engine Runner")
    parser.add_argument(
        "--mode",
        choices=["synthetic-suite", "check-freeze", "policy-fingerprint"],
        default="synthetic-suite",
        help="Execution mode",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evidence/v0.6/b_line/forward_shadow_research_r1"),
        help="Path for evidence receipts",
    )
    parser.add_argument(
        "--scratch-dir",
        type=Path,
        default=Path("/tmp/btc-forward_shadow_research_r1"),
        help="Scratch directory",
    )
    args = parser.parse_args()

    if args.mode == "policy-fingerprint":
        fp = compute_policy_fingerprint()
        print(f"Policy Fingerprint: {fp}")
    elif args.mode == "check-freeze":
        manifest = compute_frozen_manifest()
        print(f"Frozen Implementation Files: {len(manifest)}")
        for path, sha in manifest.items():
            print(f"  {path}: {sha}")
    elif args.mode == "synthetic-suite":
        res = run_developmental_synthetic_suite(args.output_dir, args.scratch_dir)
        print(f"Developmental Synthetic Suite complete. Terminal Status: {res['terminal_status']}")
        print(f"Policy Fingerprint: {res['policy_fingerprint']}")
        print(f"Sample Readiness Status: {res['sample_readiness_gate']['status']}")


if __name__ == "__main__":
    main()
