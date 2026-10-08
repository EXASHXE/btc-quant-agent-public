"""Nonselective descriptive metrics and frozen development screening."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal, localcontext
from typing import Any

from .perp_replay import Trade, bootstrap
from .perp_source import CONTEXT

D = Decimal


def number(value: Decimal) -> str:
    with localcontext(CONTEXT):
        return format(value.quantize(D("0.000000000001")), "f")


def summary(
    trades: list[Trade], *, stress: bool = False, event_study: bool = False
) -> dict[str, Any]:
    if not trades:
        return {
            "n": 0,
            "mean_net_R": None,
            "median_net_R": None,
            "gross_pnl_usdt": None,
            "net_pnl_usdt": None,
            "costs_usdt": None,
            "realized_drawdown_usdt": None,
        }
    with localcontext(CONTEXT):
        returns = sorted(t.stress_net_R if stress else t.net_R for t in trades)
        n = len(trades)
        total = sum(returns, D(0))
        median = (returns[(n - 1) // 2] + returns[n // 2]) / 2
        costs = {
            k: number(sum((getattr(t, ("stress_" if stress else "") + k) for t in trades), D(0)))
            for k in ("fee", "spread", "slippage", "funding")
        }
        reasons = Counter(t.reason for t in trades)
        holds = sorted(t.holding_hours for t in trades)
        equity = peak = D(1000)
        drawdown = D(0)
        for t in sorted(trades, key=lambda t: (t.exit_ms, t.symbol, t.identity)):
            equity += t.stress_net_pnl if stress else t.net_pnl
            peak = max(peak, equity)
            drawdown = max(drawdown, peak - equity)
        return {
            "n": n,
            "LONG": sum(t.direction == "LONG" for t in trades),
            "SHORT": sum(t.direction == "SHORT" for t in trades),
            "mean_net_R": number(total / n),
            "median_net_R": number(median),
            "mean_gross_R": number(sum((t.gross_R for t in trades), D(0)) / n),
            "gross_pnl_usdt": number(sum((t.gross_pnl for t in trades), D(0))),
            "net_pnl_usdt": number(
                sum((t.stress_net_pnl if stress else t.net_pnl for t in trades), D(0))
            ),
            "costs_usdt": costs,
            "maker_fees_usdt": "0.000000000000",
            "net_hit_rate": number(D(sum(r > 0 for r in returns)) / n),
            "TP1": reasons["TP1"],
            "SL_first": reasons["SL_FIRST"],
            "timeout": reasons["TIMEOUT"],
            "stop_before_target_resolved": number(
                D(reasons["SL_FIRST"]) / (reasons["SL_FIRST"] + reasons["TP1"])
            )
            if reasons["SL_FIRST"] + reasons["TP1"]
            else None,
            "stop_share_all_trades": number(D(reasons["SL_FIRST"]) / n),
            "mean_MFE_R": number(sum((t.mfe_R for t in trades), D(0)) / n),
            "mean_MAE_R": number(sum((t.mae_R for t in trades), D(0)) / n),
            "holding_hours": {
                "p10": number(holds[int((n - 1) * D("0.1"))]),
                "median": number((holds[(n - 1) // 2] + holds[n // 2]) / 2),
                "p90": number(holds[int((n - 1) * D("0.9"))]),
            },
            "tail_5pct_net_R": number(returns[int((n - 1) * D("0.05"))]),
            "realized_drawdown_usdt": None if event_study else number(drawdown),
            "drawdown_basis": "NOT_A_PORTFOLIO"
            if event_study
            else "fixed-notional realized exits only, not intraminute MTM",
            "asset_exposure_days": number(sum((t.holding_hours for t in trades), D(0)) / 24),
            "capital_return_sum": number(
                sum(((t.stress_net_pnl if stress else t.net_pnl) / t.capital for t in trades), D(0))
            ),
            "capital_return_interpretation": "noncompounded trade-level returns, not self-financing portfolio ROI",
        }


def candidate_result(
    identity: str,
    trades: list[Trade],
    decisions: list[dict[str, Any]],
    matched: list[tuple[Trade, Trade]],
    delayed: list[Trade],
    start: int,
    proxy: bool,
) -> dict[str, Any]:
    with localcontext(CONTEXT):
        statuses = Counter(row["status"] for row in decisions)
        signals = Counter(row["requested_action"] for row in decisions)
        stress_ci = bootstrap([(t.entry_ms, t.stress_net_R) for t in trades], start)
        base_ci = bootstrap([(t.entry_ms, t.net_R) for t in trades], start)
        increments = [
            (t.entry_ms, t.stress_net_R - (l.stress_net_R + s.stress_net_R) / 2)
            for t, (l, s) in zip(trades, matched, strict=True)
        ]
        increment_ci = bootstrap(increments, start)
        parts = {
            str(i): {
                "base": summary([t for t in trades if t.partition == i]),
                "higher_cost": summary([t for t in trades if t.partition == i], stress=True),
            }
            for i in (1, 2, 3)
        }
        exposures = {
            symbol: sum((t.holding_hours for t in trades if t.symbol == symbol), D(0))
            for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT")
        }
        total_exposure = sum(exposures.values(), D(0))
        concentration = max(exposures.values()) / total_exposure if total_exposure else D(1)
        support = (
            bool(trades)
            and all(parts[str(i)]["base"]["n"] >= 100 for i in (1, 2, 3))
            and (
                len(trades) >= 20
                and int(str(stress_ci["blocks"])) >= 12
                and concentration <= D("0.60")
            )
        )
        base = summary(trades)
        stress = summary(trades, stress=True)
        positive = bool(trades) and D(base["mean_net_R"]) > 0 and D(stress["mean_net_R"]) > 0
        qualifies = (
            support
            and not proxy
            and positive
            and D(str(stress_ci["lower_bonferroni"])) > 0
            and (
                D(str(increment_ci["lower_bonferroni"])) > 0
                and sum(
                    parts[str(i)]["higher_cost"]["mean_net_R"] is not None
                    and D(parts[str(i)]["higher_cost"]["mean_net_R"]) >= 0
                    for i in (1, 2, 3)
                )
                >= 2
            )
        )
        return {
            "candidate_id": identity,
            "status": "EVALUATED_DEVELOPMENT_ONLY",
            "n_decisions": len(decisions),
            "decision_statuses": dict(sorted(statuses.items())),
            "LONG_SHORT_WAIT_signals": dict(sorted(signals.items())),
            "action_frequency": number(D(len(trades)) / len(decisions)) if decisions else None,
            "fill_ratio": number(D(statuses["FILLED"]) / (statuses["FILLED"] + statuses["NO_FILL"]))
            if statuses["FILLED"] + statuses["NO_FILL"]
            else None,
            "base": base,
            "higher_cost": stress,
            "partitions": parts,
            "symbols": {
                s: summary([t for t in trades if t.symbol == s], stress=True) for s in exposures
            },
            "regimes": {
                r: summary([t for t in trades if t.regime == r], stress=True)
                for r in ("UP", "DOWN", "RANGE")
            },
            "asset_exposure_fraction": {
                s: number(v / total_exposure) if total_exposure else None
                for s, v in exposures.items()
            },
            "base_interval": base_ci,
            "higher_cost_interval": stress_ci,
            "matched_incremental_interval": increment_ci,
            "matched_long": summary([p[0] for p in matched], stress=True, event_study=True),
            "matched_short": summary([p[1] for p in matched], stress=True, event_study=True),
            "matched_control_interpretation": "paired counterfactual event-study episodes; may overlap across episodes, not funded portfolios",
            "liquidity_stress": {
                "filled": sum(t.liquidity_stress_filled for t in trades),
                "unfilled": sum(not t.liquidity_stress_filled for t in trades),
                "metrics": summary([t for t in trades if t.liquidity_stress_filled], stress=True),
            },
            "latency_plus_1m": {"filled": len(delayed), "metrics": summary(delayed, stress=True)},
            "funding_grade": "PROXY_STRESS_ONLY" if proxy else "ACTUAL_RATE_ADVERSE_PRICE_PROXY",
            "sample_support": support,
            "shortlist_eligible": qualifies,
            "ranking_score": stress["mean_net_R"],
            "coverage": "1.000000000000",
            "data_grade": "ARCHIVAL_EVENT_TIME_RECONSTRUCTED",
            "multiple_testing": "eight candidates/two screens, Bonferroni lower quantile0.003125; exploratory, not alpha proof",
        }
