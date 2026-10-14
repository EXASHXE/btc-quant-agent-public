"""Trade-level and calendar-cluster development summaries; never minute-IID."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import numpy as np

from .engine import Cost


def describe(trades):
    n = len(trades)
    names = (
        "gross_bps",
        "net_bps",
        "net_R",
        "gross_usdt",
        "fee_usdt",
        "execution_drag_usdt",
        "net_usdt",
    )
    result = {
        "completed_trades": n,
        **{
            "mean_" + k: float(np.mean([float(t[k]) for t in trades])) if n else None for k in names
        },
    }
    gains = sum(max(0, float(t["net_usdt"])) for t in trades)
    losses = -sum(min(0, float(t["net_usdt"])) for t in trades)
    result.update(
        profit_factor=gains / losses if losses > 0 else None,
        profit_factor_state="FINITE"
        if losses > 0
        else "POSITIVE_NO_LOSSES"
        if gains > 0
        else "UNDEFINED",
        sum_net_usdt_over_separate_books=sum(float(t["net_usdt"]) for t in trades),
        win_fraction=sum(float(t["net_usdt"]) > 0 for t in trades) / n if n else None,
        worst_5pct_mean_net_bps=float(
            np.mean(sorted(float(t["net_bps"]) for t in trades)[: max(1, math.ceil(0.05 * n))])
        )
        if n
        else None,
        collision_minutes=sum(t["collision_minutes"] for t in trades),
        partial_TP1_trade_fraction=sum(
            t["policy"] != "X0" and any(x["reason"] == "TP1" for x in t["legs"]) for t in trades
        )
        / n
        if n
        else None,
        reasons={
            r: sum(t["exit_reason"] == r for t in trades)
            for r in sorted({t["exit_reason"] for t in trades})
        },
        cap_triggers={
            str(h): sum(t["exit_reason"] == "TIME_CAP" and t["cap_hours"] == h for t in trades)
            for h in (8, 18, 24)
        },
    )
    durations = [t["hold_minutes"] for t in trades]
    result["hold_minutes"] = {
        k: float(np.quantile(durations, q)) if n else None
        for k, q in [("min", 0), ("median", 0.5), ("p75", 0.75), ("max", 1)]
    }
    result["exited_before_hours_fraction"] = {
        str(h): sum(d < h * 60 for d in durations) / n if n else None for h in (4, 12, 18, 24)
    }
    if n:
        spreads = []
        slips = []
        ticks = []
        fees = []
        extra = []
        for t in trades:
            notional = float(t["entry_notional"])
            c = t["cost"]
            spread = notional * float(c["spread_bps"]) / 10000 + sum(
                float(x["spread_drag"]) for x in t["legs"]
            )
            slip = notional * float(c["slip_bps"]) / 10000 + sum(
                float(x["slippage_drag"]) for x in t["legs"]
            )
            spreads.append(spread / notional * 10000)
            slips.append(slip / notional * 10000)
            ticks.append((float(t["execution_drag_usdt"]) - spread - slip) / notional * 10000)
            fees.append(float(t["fee_usdt"]) / notional * 10000)
            extra_cost = Cost(c["fee_bps"], c["spread_bps"] + 2, c["slip_bps"] + 3)
            extra_loss = 0
            for leg in t["legs"]:
                adjusted = extra_cost.effective(leg["raw_price"], t["side"], False)
                extra_loss += (
                    t["side"] * (leg["effective_price"] - adjusted) * leg["quantity"]
                    + extra_cost.fee(adjusted, leg["quantity"])
                    - leg["fee"]
                )
            extra.append(float(extra_loss) / notional * 10000)
        result.update(
            mean_fee_bps=float(np.mean(fees)),
            mean_spread_drag_bps=float(np.mean(spreads)),
            mean_slippage_drag_bps=float(np.mean(slips)),
            mean_tick_drag_bps=float(np.mean(ticks)),
            extra_exit_2bp_spread_3bp_slip_fixed_leg_sensitivity_mean_net_bps=result["mean_net_bps"]
            - float(np.mean(extra)),
        )
    else:
        result.update(
            {
                k: None
                for k in (
                    "mean_fee_bps",
                    "mean_spread_drag_bps",
                    "mean_slippage_drag_bps",
                    "mean_tick_drag_bps",
                    "extra_exit_2bp_spread_3bp_slip_fixed_leg_sensitivity_mean_net_bps",
                )
            }
        )
    return result


def block_uncertainty(records, folds, key="net_bps", monthly=False):
    """Shared deterministic within-year calendar draws, including empty blocks."""
    years = sorted({f["year"] for f in folds})
    means = []
    draws = []
    represented = []
    rng = np.random.default_rng(27182026)
    B = 10000
    for year in years:
        cluster_set = set()
        for f in [f for f in folds if f["year"] == year]:
            d = datetime.fromtimestamp(f["start_ms"] / 1000, UTC)
            while d.timestamp() * 1000 < f["end_ms"]:
                cluster_set.add(
                    (d.year, d.month)
                    if monthly
                    else (d - timedelta(days=d.weekday())).date().isoformat()
                )
                d += timedelta(days=1)
        clusters = sorted(cluster_set)
        mapping = {x: i for i, x in enumerate(clusters)}
        sums = np.zeros(len(clusters))
        counts = np.zeros(len(clusters))
        for t in records:
            if t["year"] != year:
                continue
            d = datetime.fromtimestamp(t["entry_at"] / 1000, UTC)
            cluster = (
                (d.year, d.month)
                if monthly
                else (d - timedelta(days=d.weekday())).date().isoformat()
            )
            sums[mapping[cluster]] += float(t[key])
            counts[mapping[cluster]] += 1
        indexes = rng.integers(0, len(clusters), (B, len(clusters)))
        if counts.sum() == 0:
            continue
        represented.append(year)
        means.append(sums.sum() / counts.sum())
        totals = sums[indexes].sum(axis=1)
        den = counts[indexes].sum(axis=1)
        values = np.full(B, np.nan)
        np.divide(totals, den, out=values, where=den > 0)
        draws.append(values)
    if not draws:
        return {
            "observed": None,
            "ci95": [None, None],
            "p_one_sided": 1.0,
            "Bonferroni27_p": 1.0,
            "undefined_resamples": 10000,
            "represented_years": [],
            "blocks": "MONTH" if monthly else "WEEK",
        }
    observed = float(np.mean(means))
    a = np.mean(np.stack(draws), axis=0)
    valid = np.isfinite(a)
    missing = int(np.sum(~valid))
    fraction = missing / B
    values = a[valid]
    lower = (
        None
        if fraction >= 0.025 or not len(values)
        else float(np.quantile(values, (0.025 - fraction) / (1 - fraction)))
    )
    upper = float(np.quantile(values, 0.975)) if len(values) else None
    p = (1 + missing + int(np.sum(values - observed >= observed))) / (B + 1)
    return {
        "observed": observed,
        "ci95": [lower, upper],
        "p_one_sided": p,
        "Bonferroni27_p": min(1, 27 * p),
        "undefined_resamples": missing,
        "represented_years": represented,
        "bootstrap_draws": B,
        "seed": 27182026,
        "blocks": "MONTH" if monthly else "WEEK",
        "zero_trade_blocks_included": True,
        "undefined_null_draws_counted_adversarially": True,
    }


def gate(summary, paired, definition):
    fail = []
    if summary["completed_trades"] < 50:
        fail.append("SUPPORT_LT50")
    if summary["active_months"] < 6:
        fail.append("MONTHS_LT6")
    represented = [y for y in summary["years"] if y["completed_trades"]]
    if len(represented) < 2:
        fail.append("YEARS_LT2")
    if summary["equal_year_mean_net_bps"] is None or summary["equal_year_mean_net_bps"] <= 0:
        fail.append("NONPOSITIVE_EQUAL_YEAR_NET")
    if sum(y["mean_net_bps"] is not None and y["mean_net_bps"] >= 0 for y in summary["years"]) < 2:
        fail.append("NONNEGATIVE_YEARS_LT2")
    pf = summary["profit_factor"]
    if not (summary["profit_factor_state"] == "POSITIVE_NO_LOSSES" or pf is not None and pf > 1):
        fail.append("PF_NOT_GT1")
    if summary["max_closed_dense_MTM_DD_pct"] > 15:
        fail.append("DD_GT15PCT")
    if summary["weekly_uncertainty"]["Bonferroni27_p"] > 0.05:
        fail.append("NET_BONFERRONI_NOT_SIGNIFICANT")
    if definition["exit"] == "X0":
        fail.append("BASELINE_COMPARATOR_NOT_NEW_PROMOTION")
    elif paired is None or paired["matched_entries"] == 0:
        fail.append("NO_PAIRED_SUPPORT")
    else:
        if paired["mean_delta_bps"] <= 0:
            fail.append("PAIRED_DELTA_NOT_POSITIVE")
        if paired["tail5_candidate_bps"] < paired["tail5_X0_bps"] - 10:
            fail.append("PAIRED_TAIL_DEGRADATION_GT10BP")
        if paired["weekly_uncertainty"]["Bonferroni27_p"] > 0.05:
            fail.append("PAIRED_BONFERRONI_NOT_SIGNIFICANT")
    return fail
