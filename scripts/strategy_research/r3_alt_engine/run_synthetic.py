"""Hermetic runner for synthetic alternative engine simulation without external network or loaders."""

import argparse
import sys
from decimal import Decimal
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parent.parent.parent.parent / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from btc_quant_agent.strategy_research.r3_alt_engine.frozen_primitives import (
    CANDIDATE_IDS,
    quantize12dp,
)
from btc_quant_agent.strategy_research.r3_alt_engine.model import (
    Bar1m,
    CostScenario,
    MarkBar1m,
    ReplayConfig,
    SymbolFilters,
)
from btc_quant_agent.strategy_research.r3_alt_engine.replay import (
    ReplayEngine,
    SyntheticDataset,
)


def build_synthetic_dataset(n_hours: int = 245, trend: str = "win") -> SyntheticDataset:
    start_ms = 1699999200000
    symbol = "BTCUSDT"
    bars: list[Bar1m] = []
    marks: list[MarkBar1m] = []

    price = Decimal("50000.0")
    for h in range(n_hours):
        h_open = start_ms + h * 3_600_000
        for m in range(60):
            m_open = h_open + m * 60_000
            step = Decimal("2.0") if h < 240 else (Decimal("15.0") if trend == "win" else Decimal("-15.0"))
            o = price
            h_p = price + Decimal("5.0")
            l_p = price - Decimal("5.0")
            c = price + step
            price = c

            b = Bar1m(
                timestamp_ms=m_open,
                open=quantize12dp(o),
                high=quantize12dp(h_p),
                low=quantize12dp(l_p),
                close=quantize12dp(c),
                volume=Decimal("1.0"),
                symbol=symbol,
            )
            mb = MarkBar1m(
                timestamp_ms=m_open,
                open=quantize12dp(o),
                high=quantize12dp(h_p),
                low=quantize12dp(l_p),
                close=quantize12dp(c),
                symbol=symbol,
                available_at_ms=m_open + 120_000,
            )
            bars.append(b)
            marks.append(mb)

    filters = SymbolFilters(
        symbol=symbol,
        tick_size=Decimal("0.1"),
        step_size=Decimal("0.001"),
        min_notional=Decimal("5.0"),
    )
    return SyntheticDataset(
        source_name=f"HERMETIC_SYNTHETIC_{trend.upper()}",
        bars_1m={symbol: bars},
        mark_bars_1m={symbol: marks},
        symbol_filters={symbol: filters},
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Hermetic Synthetic Replay Runner")
    parser.add_argument("--scenario", choices=["BASE", "STRESS"], default="BASE")
    parser.add_argument("--candidate", choices=list(CANDIDATE_IDS), default="STRUCTURAL_CONTINUATION_LONG_04H")
    parser.add_argument("--trend", choices=["win", "loss"], default="win")
    args = parser.parse_args()

    scenario = CostScenario[args.scenario]
    ds = build_synthetic_dataset(n_hours=245, trend=args.trend)
    engine = ReplayEngine()
    cfg = ReplayConfig(
        candidates=(args.candidate,),
        cost_scenario=scenario,
        initial_cash=Decimal("1000.000000000000"),
        symbols=("BTCUSDT",),
    )

    report = engine.run_simulation(ds, cfg)
    print("=== Synthetic Simulation Complete ===")
    print(f"Source: {report.source}")
    print(f"Candidate: {args.candidate}")
    print(f"Scenario: {args.scenario}")
    print(f"Event Sequence Hash: {report.event_sequence_hash}")
    print(f"Terminal All Zero Liabilities: {report.terminal_all_zero}")
    for cid, outcomes in report.candidate_outcomes.items():
        print(f"Candidate {cid}: status={outcomes.get('status')}, trades={outcomes.get('trades')}, net_pnl={outcomes.get('net_pnl')}")
    for inv_id, count in sorted(report.invariants_checked_counts.items()):
        print(f"Invariant {inv_id}: checked {count} times")


if __name__ == "__main__":
    main()
