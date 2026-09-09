from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from ..domain import Candle
from .fee_model import FeeModel
from .metrics import SimulationSummary
from .policy import TradePolicy
from .signal import InformationSignal
from .simulator import EconomicSimulationEngine


@dataclass(frozen=True)
class BenchmarkResult:
    """Benchmark performance metrics for evaluating alpha vs. beta."""

    benchmark_name: str
    initial_cash: float
    final_equity: float
    net_pnl_usdt: float
    net_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float | None
    equity_curve: list[tuple[int, float]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_name": self.benchmark_name,
            "initial_cash": self.initial_cash,
            "final_equity": self.final_equity,
            "net_pnl_usdt": self.net_pnl_usdt,
            "net_return_pct": self.net_return_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "sharpe_ratio": self.sharpe_ratio,
        }


class BenchmarkEngine:
    """Computes comparative benchmarks ensuring strategies are judged against genuine alternatives."""

    def __init__(self, fee_model: FeeModel | None = None) -> None:
        self.fee_model = fee_model or FeeModel()

    def simulate_cash_benchmark(
        self,
        initial_cash: float,
        timestamps: Sequence[int],
    ) -> BenchmarkResult:
        """Benchmark A: Cash / No Trade (Capital Preservation)."""
        curve = [(ts, initial_cash) for ts in timestamps]
        return BenchmarkResult(
            benchmark_name="BENCHMARK_A_CASH_NO_TRADE",
            initial_cash=initial_cash,
            final_equity=initial_cash,
            net_pnl_usdt=0.0,
            net_return_pct=0.0,
            max_drawdown_pct=0.0,
            sharpe_ratio=None,
            equity_curve=curve,
        )

    def simulate_passive_btc(
        self,
        initial_cash: float,
        candles: Sequence[Candle],
    ) -> BenchmarkResult:
        """Benchmark B: Passive BTC Buy-and-Hold Exposure."""
        if not candles:
            return self.simulate_cash_benchmark(initial_cash, [])

        first_bar = candles[0]
        entry_price = first_bar.open
        # Initial buy with fee deduction
        entry_fee_rate = self.fee_model.taker_fee_rate
        cash_for_btc = initial_cash / (1.0 + entry_fee_rate)
        btc_quantity = cash_for_btc / entry_price

        peak_equity = initial_cash
        max_dd_pct = 0.0
        curve: list[tuple[int, float]] = []

        for bar in candles:
            eq = btc_quantity * bar.close
            curve.append((bar.close_time_ms, eq))
            peak_equity = max(peak_equity, eq)
            dd = (peak_equity - eq) / peak_equity if peak_equity > 0 else 0.0
            max_dd_pct = max(max_dd_pct, dd)

        # Liquidate on last candle
        last_price = candles[-1].close
        exit_fee = (btc_quantity * last_price) * self.fee_model.taker_fee_rate
        final_equity = (btc_quantity * last_price) - exit_fee
        net_pnl = final_equity - initial_cash
        net_return = net_pnl / initial_cash if initial_cash > 0 else 0.0

        # The legacy API has no declared return-cadence contract.  Do not
        # fabricate an annualized Sharpe from arbitrary candle timestamps.
        sharpe = None
        if curve:
            curve[-1] = (curve[-1][0], final_equity)

        return BenchmarkResult(
            benchmark_name="BENCHMARK_B_PASSIVE_BTC",
            initial_cash=initial_cash,
            final_equity=final_equity,
            net_pnl_usdt=net_pnl,
            net_return_pct=net_return,
            max_drawdown_pct=max_dd_pct,
            sharpe_ratio=sharpe,
            equity_curve=curve,
        )

    def simulate_random_entry(
        self,
        initial_cash: float,
        candles: Sequence[Candle],
        policy: TradePolicy,
        trade_frequency_pct: float = 0.05,  # 5% chance of entry per candle
        num_trials: int = 5,
        seed: int = 42,
    ) -> BenchmarkResult:
        """Benchmark C: Randomized Entry Baseline (Isolates timing alpha from luck/drift)."""
        if not candles:
            return self.simulate_cash_benchmark(initial_cash, [])

        rng = random.Random(seed)
        net_pnls: list[float] = []
        max_dds: list[float] = []
        sharpes: list[float] = []
        last_curve: list[tuple[int, float]] = []

        for trial in range(num_trials):
            random_signals: list[InformationSignal] = []
            for bar in candles:
                if rng.random() < trade_frequency_pct:
                    direction = 1 if rng.random() > 0.5 else -1
                    sig = InformationSignal(
                        signal_id=f"rand_{trial}_{bar.open_time_ms}",
                        experiment_id="BENCHMARK_C_RANDOM",
                        timestamp_ms=bar.open_time_ms,
                        direction=direction,
                        strength=1.0,
                    )
                    random_signals.append(sig)

            sim = EconomicSimulationEngine(
                policy=policy,
                fee_model=self.fee_model,
                initial_cash=initial_cash,
            )
            summary = sim.simulate(candles=candles, signals=random_signals)
            net_pnls.append(summary.net_pnl_usdt)
            max_dds.append(summary.max_drawdown_pct)
            if summary.sharpe_ratio is not None:
                sharpes.append(summary.sharpe_ratio)
            last_curve = list(summary.equity_curve)

        mean_pnl = sum(net_pnls) / len(net_pnls) if net_pnls else 0.0
        mean_dd = sum(max_dds) / len(max_dds) if max_dds else 0.0
        mean_sharpe = sum(sharpes) / len(sharpes) if sharpes else 0.0
        final_eq = initial_cash + mean_pnl
        net_ret = mean_pnl / initial_cash if initial_cash > 0 else 0.0

        return BenchmarkResult(
            benchmark_name="BENCHMARK_C_RANDOM_ENTRY",
            initial_cash=initial_cash,
            final_equity=final_eq,
            net_pnl_usdt=mean_pnl,
            net_return_pct=net_ret,
            max_drawdown_pct=mean_dd,
            sharpe_ratio=mean_sharpe,
            equity_curve=last_curve,
        )

    def evaluate_economic_qualification(
        self,
        strategy_summary: SimulationSummary,
        candles: Sequence[Candle],
        policy: TradePolicy,
    ) -> dict[str, Any]:
        """Diagnostic comparisons only, pending P2-P6 correctness repairs.

        Caller-supplied summaries are not qualification evidence. No performance
        outcome can enable formal qualification through this legacy interface.
        """
        cash_bench = self.simulate_cash_benchmark(
            initial_cash=strategy_summary.initial_cash,
            timestamps=[c.close_time_ms for c in candles],
        )
        btc_bench = self.simulate_passive_btc(
            initial_cash=strategy_summary.initial_cash,
            candles=candles,
        )
        random_bench = self.simulate_random_entry(
            initial_cash=strategy_summary.initial_cash,
            candles=candles,
            policy=policy,
        )

        beat_cash = strategy_summary.net_pnl_usdt > cash_bench.net_pnl_usdt
        beat_random = strategy_summary.net_pnl_usdt > random_bench.net_pnl_usdt
        beat_btc = strategy_summary.net_pnl_usdt > btc_bench.net_pnl_usdt

        return {
            "strategy": strategy_summary.to_dict(),
            "benchmarks": {
                "cash": cash_bench.to_dict(),
                "passive_btc": btc_bench.to_dict(),
                "random_entry": random_bench.to_dict(),
            },
            "comparisons": {
                "excess_return_vs_cash_pct": strategy_summary.net_return_pct - cash_bench.net_return_pct,
                "excess_return_vs_btc_pct": strategy_summary.net_return_pct - btc_bench.net_return_pct,
                "excess_return_vs_random_pct": strategy_summary.net_return_pct - random_bench.net_return_pct,
                "beats_cash": beat_cash,
                "beats_random": beat_random,
                "beats_passive_btc": beat_btc,
            },
            "economic_qualification_passed": False,
            "qualification_evaluated": False,
            "diagnostic_only": True,
            "verdict": "NOT_TESTABLE",
            "reason": "FORMAL_QUALIFICATION_DISABLED_PENDING_P2_P6_REPAIRS",
        }
