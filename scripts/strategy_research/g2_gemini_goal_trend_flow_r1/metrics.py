"""Statistical metrics, block bootstrap, and strict promotion gate evaluation."""
from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

import numpy as np

CALENDAR_START_MS = int(datetime(2021, 2, 1, tzinfo=UTC).timestamp() * 1000)
CALENDAR_END_MS = int(datetime(2024, 1, 1, tzinfo=UTC).timestamp() * 1000)
FAMILY_SIZE = 48
FAMILYWISE_ALPHA = 0.05 / FAMILY_SIZE


def _profit_factor(pnl: np.ndarray) -> float | None:
    gains = float(np.sum(pnl[pnl > 0]))
    losses = float(-np.sum(pnl[pnl < 0]))
    return gains / losses if losses > 0 else None


def compute_drawdown(equity_curve: list[float]) -> float:
    """Compute maximum drawdown percentage from an equity curve."""
    if equity_curve is None or len(equity_curve) < 2:
        return 0.0
    arr = np.array(equity_curve, dtype=np.float64)
    if not np.all(np.isfinite(arr)):
        raise ValueError("Non-finite equity observation")
    peaks = np.maximum.accumulate(arr)
    dd = (peaks - arr) / np.maximum(peaks, 1e-6)
    return float(np.max(dd) * 100.0)


def calculate_candidate_metrics(
    trades: list[dict], cost_name: str, *, minute_equity_curve: list[float] | None = None,
    fold_metrics: list[dict] | None = None,
) -> dict:
    """Calculate descriptive performance metrics for a candidate."""
    n = len(trades)
    if minute_equity_curve is None and fold_metrics is not None and all(
        "minute_equity_curve" in fold for fold in fold_metrics
    ):
        segments = []
        for fold in fold_metrics:
            curve = np.asarray(fold["minute_equity_curve"], dtype=np.float64)
            if curve.ndim != 2 or curve.shape[1] != 2 or not np.all(np.isfinite(curve)):
                raise ValueError("Minute equity must contain causal [UTC close clock, equity] pairs")
            if len(curve) and np.any(np.diff(curve[:, 0]) <= 0):
                raise ValueError("Minute equity clocks must increase")
            segments.append(curve)
        joined = np.concatenate(segments) if segments else np.empty((0, 2))
        if len(joined) and np.any(np.diff(joined[:, 0]) <= 0):
            raise ValueError("Overlapping fold minute equity clocks")
        minute_equity_curve = [1000.0, *joined[:, 1].tolist()]
    mtm_dd = compute_drawdown(minute_equity_curve) if minute_equity_curve is not None else None
    if n == 0:
        return {
            "cost_model": cost_name,
            "trade_count": 0,
            "win_rate_pct": None,
            "profit_factor": None,
            "net_profit_factor": None,
            "gross_profit_factor": None,
            "mean_gross_bps": None,
            "median_gross_bps": None,
            "mean_net_bps": None,
            "median_net_bps": None,
            "equal_year_net_bps": None,
            "worst_year_net_bps": None,
            "years_covered": 0,
            "months_covered": 0,
            "max_mtm_drawdown_pct": mtm_dd,
            "max_trade_close_drawdown_pct": None,
            "mean_paired_increment_bps": None,
            "mean_duration_minutes": None,
            "exit_reasons": {},
            "yearly_breakdown": {},
        }

    gross_bps = np.array([t["gross_bps"] for t in trades], dtype=np.float64)
    net_bps = np.array([t["net_bps"] for t in trades], dtype=np.float64)
    net_usdts = np.array([t["net_usdt"] for t in trades], dtype=np.float64)
    gross_usdts = np.array([t["gross_usdt"] for t in trades], dtype=np.float64)

    wins = net_usdts > 0
    win_rate = float(np.mean(wins) * 100.0)

    net_pf = _profit_factor(net_usdts)
    gross_pf = _profit_factor(gross_usdts)

    # Equity curve
    curve = [1000.0]
    eq = 1000.0
    for u in net_usdts:
        eq += u
        curve.append(eq)
    max_trade_close_dd = compute_drawdown(curve)

    # Breakdown by calendar year and month
    by_year = defaultdict(list)
    by_month = set()
    exit_reasons = defaultdict(int)
    durations = []

    for t in trades:
        entry_at = t["entry_at"]
        dt = datetime.fromtimestamp(int(entry_at) / 1000, tz=UTC)
        y = dt.year
        m = dt.month
        by_year[y].append(t["net_bps"])
        by_month.add((y, m))
        exit_reasons[t["exit_reason"]] += 1
        durations.append(t["duration_minutes"])

    yearly_breakdown = {}
    yearly_means = []
    for y in sorted(by_year.keys()):
        bps_list = by_year[y]
        m_net = float(np.mean(bps_list))
        yearly_means.append(m_net)
        yearly_breakdown[y] = {
            "n_trades": len(bps_list),
            "mean_net_bps": m_net,
        }

    equal_year_net = float(np.mean(yearly_means))
    worst_year_net = float(np.min(yearly_means))
    paired_increment = None
    if all(t.get("control_net_bps") is not None for t in trades):
        controls = np.asarray([t["control_net_bps"] for t in trades], dtype=np.float64)
        if np.all(np.isfinite(controls)):
            paired_increment = float(np.mean(net_bps - controls))

    return {
        "cost_model": cost_name,
        "trade_count": n,
        "win_rate_pct": win_rate,
        "profit_factor": net_pf,
        "net_profit_factor": net_pf,
        "gross_profit_factor": gross_pf,
        "mean_gross_bps": float(np.mean(gross_bps)),
        "median_gross_bps": float(np.median(gross_bps)),
        "mean_net_bps": float(np.mean(net_bps)),
        "median_net_bps": float(np.median(net_bps)),
        "equal_year_net_bps": equal_year_net,
        "worst_year_net_bps": worst_year_net,
        "years_covered": len(by_year),
        "months_covered": len(by_month),
        "max_mtm_drawdown_pct": mtm_dd,
        "max_trade_close_drawdown_pct": max_trade_close_dd,
        "mean_paired_increment_bps": paired_increment,
        "mean_duration_minutes": float(np.mean(durations)) if durations else 0.0,
        "exit_reasons": dict(exit_reasons),
        "yearly_breakdown": yearly_breakdown,
    }


def block_bootstrap(
    trades: list[dict], block_days: int = 7, n_iter: int = 10000, seed: int = 42
) -> dict:
    """Identical fixed UTC calendar draws, including empty blocks, for all trials."""
    if block_days not in (7, 14) or n_iter <= 0:
        raise ValueError("Only fixed 7d/14d blocks and positive iterations are valid")
    block_ms = block_days * 86400 * 1000
    n_blocks = (CALENDAR_END_MS - CALENDAR_START_MS + block_ms - 1) // block_ms
    counts = np.zeros(n_blocks, dtype=np.int64)
    sums = np.zeros(n_blocks, dtype=np.float64)
    for t in trades:
        at = int(t["entry_at"])
        if not CALENDAR_START_MS <= at < CALENDAR_END_MS:
            raise ValueError("Trade outside fixed development calendar")
        value = float(t["net_bps"])
        if not np.isfinite(value):
            raise ValueError("Non-finite net bps")
        idx = (at - CALENDAR_START_MS) // block_ms
        counts[idx] += 1
        sums[idx] += value
    nonempty = int(np.count_nonzero(counts))
    result = {
        "block_days": block_days,
        "calendar_start_utc": "2021-02-01T00:00:00Z",
        "calendar_end_exclusive_utc": "2024-01-01T00:00:00Z",
        "block_count": int(n_blocks),
        "nonempty_block_count": nonempty,
        "empty_block_count": int(n_blocks - nonempty),
        "family_size": FAMILY_SIZE,
        "familywise_alpha": FAMILYWISE_ALPHA,
        "n_iter": n_iter,
        "seed": seed,
        "mean": None,
        "median": None,
        "ci_95_lower": None,
        "ci_95_upper": None,
        "lcb_95": None,
        "familywise_lcb_48": None,
        "zero_trade_resamples": n_iter,
    }
    if not trades:
        return result
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, n_blocks, size=(n_iter, n_blocks))
    drawn_counts = np.sum(counts[indices], axis=1)
    valid = drawn_counts > 0
    result["zero_trade_resamples"] = int(np.count_nonzero(~valid))
    if np.any(valid):
        means = np.sum(sums[indices[valid]], axis=1) / drawn_counts[valid]
        result["mean"] = float(np.mean(means))
        result["median"] = float(np.median(means))
    if nonempty < 2 or not np.all(valid):
        return result
    result["ci_95_lower"] = float(np.quantile(means, 0.025))
    result["ci_95_upper"] = float(np.quantile(means, 0.975))
    result["lcb_95"] = float(np.quantile(means, 0.05))
    result["familywise_lcb_48"] = float(np.quantile(means, FAMILYWISE_ALPHA))
    return result


def evaluate_promotion_gate(
    stress_metrics: dict, bootstrap_7d: dict, bootstrap_14d: dict | None = None
) -> dict:
    """Require absolute net economics, paired control and both adjusted bounds."""
    def positive(value: float | None) -> bool:
        return value is not None and np.isfinite(value) and value > 0

    def at_least(value: float | None, threshold: float) -> bool:
        return value is not None and np.isfinite(value) and value >= threshold

    def bound_valid(result: dict | None) -> bool:
        return bool(
            result is not None
            and result.get("nonempty_block_count", 0) >= 2
            and result.get("zero_trade_resamples", 1) == 0
            and result.get("family_size") == FAMILY_SIZE
            and result.get("familywise_alpha") == FAMILYWISE_ALPHA
            and positive(result.get("familywise_lcb_48"))
        )

    dd = stress_metrics.get("max_mtm_drawdown_pct")
    gates = {
        "G1_sample_size_ge_100": at_least(stress_metrics.get("trade_count"), 100),
        "G2_temporal_breadth": (
            at_least(stress_metrics.get("years_covered"), 2)
            and at_least(stress_metrics.get("months_covered"), 6)
        ),
        "G3_absolute_mean_net_gt_0": positive(stress_metrics.get("mean_net_bps")),
        "G4_equal_year_net_gt_0": positive(stress_metrics.get("equal_year_net_bps")),
        "G5_net_profit_factor_ge_115": at_least(stress_metrics.get("net_profit_factor"), 1.15),
        "G6_worst_year_net_ge_neg10": at_least(stress_metrics.get("worst_year_net_bps"), -10),
        "G7_true_minute_mtm_drawdown_le_12pct": (
            dd is not None and np.isfinite(dd) and dd <= 12
        ),
        "G8_paired_control_increment_gt_0": positive(
            stress_metrics.get("mean_paired_increment_bps")
        ),
        "G9_familywise_7d_lcb_gt_0": bound_valid(bootstrap_7d),
        "G10_familywise_14d_lcb_gt_0": bound_valid(bootstrap_14d),
    }
    all_passed = all(gates.values())
    return {
        "gates": {key: {"passed": value} for key, value in gates.items()},
        "all_passed": all_passed,
        "verdict": (
            "PROMOTABLE_DEV_HYPOTHESIS_PENDING_CONTROLLER_HOLDOUT"
            if all_passed else "FALSIFIED_DEV_CANDIDATE"
        ),
    }
