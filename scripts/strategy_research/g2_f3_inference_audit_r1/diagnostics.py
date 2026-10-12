"""Pre-registered diagnostic suite for sparse alpha and statistical-validity forensics.

Covers:
- Block support N > 0 and distinct calendar weeks
- 12h vs 18h horizon identity and execution overlap
- Leave-one-event-out (LOEO) jackknife influence and concentration
- Gross-to-fee ratio and cost attribution
- Profit factor sentinels (e.g. 999.0 with zero losses)
- Source timestamp causality and known-at uncertainty classification
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

MINUTE_MS = 60_000
HOUR_MS = 3_600_000
DAY_MS = 86_400_000
WEEK_MS = 7 * DAY_MS


def audit_event_and_block_support(
    trades: list[dict[str, Any]],
    eval_start_ms: int,
    eval_end_ms: int,
    block_days: int = 14,
) -> dict[str, Any]:
    """Audit trade count, block support, and distinct calendar weeks."""
    n_trades = len(trades)
    block_ms = block_days * DAY_MS
    n_blocks = math.ceil((eval_end_ms - eval_start_ms) / block_ms)

    active_blocks: set[int] = set()
    active_weeks: set[int] = set()
    annual_counts: dict[str, int] = {"2021": 0, "2022": 0, "2023": 0}

    for t in trades:
        entry_at = int(t["entry_at"])
        b_idx = int((entry_at - eval_start_ms) // block_ms)
        if 0 <= b_idx < n_blocks:
            active_blocks.add(b_idx)
        w_idx = int((entry_at - eval_start_ms) // WEEK_MS)
        active_weeks.add(w_idx)

        fold = str(t.get("fold", ""))
        for y in ("2021", "2022", "2023"):
            if fold.startswith(y):
                annual_counts[y] += 1

    n_active_blocks = len(active_blocks)
    n_active_weeks = len(active_weeks)
    zero_blocks = n_blocks - n_active_blocks

    return {
        "n_executed_trades": n_trades,
        "n_total_blocks": n_blocks,
        "n_active_blocks": n_active_blocks,
        "n_zero_blocks": zero_blocks,
        "zero_block_fraction": float(zero_blocks / n_blocks) if n_blocks > 0 else 0.0,
        "n_distinct_weeks": n_active_weeks,
        "annual_counts": annual_counts,
        "passes_sample_viability_n30": n_trades >= 30,
        "evaluation_span_days": float((eval_end_ms - eval_start_ms) / DAY_MS),
    }


def audit_horizon_overlap(
    trades_12h: list[dict[str, Any]],
    trades_18h: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare 12h vs 18h executions to detect identical entries and early exit overlaps."""
    map_12h = {t["event_id"].replace("12H", "XX"): t for t in trades_12h}
    map_18h = {t["event_id"].replace("18H", "XX"): t for t in trades_18h}

    common_keys = sorted(set(map_12h.keys()) & set(map_18h.keys()))
    identical_entry_count = 0
    identical_exit_outcome_count = 0
    details: list[dict[str, Any]] = []

    for k in common_keys:
        t12 = map_12h[k]
        t18 = map_18h[k]

        same_entry = (
            int(t12["entry_at"]) == int(t18["entry_at"])
            and int(t12["side"]) == int(t18["side"])
            and abs(float(t12["raw_entry"]) - float(t18["raw_entry"])) < 1e-6
        )
        if same_entry:
            identical_entry_count += 1

        same_outcome = (
            t12["exit_reason"] == t18["exit_reason"]
            and abs(float(t12["net_after_funding_bps"]) - float(t18["net_after_funding_bps"])) < 1e-4
            and abs(float(t12["duration_minutes"]) - float(t18["duration_minutes"])) < 1e-4
        )
        if same_outcome:
            identical_exit_outcome_count += 1

        details.append({
            "key": k,
            "entry_at": t12["entry_at"],
            "side": t12["side"],
            "same_entry": same_entry,
            "exit_reason_12h": t12["exit_reason"],
            "exit_reason_18h": t18["exit_reason"],
            "dur_12h": t12["duration_minutes"],
            "dur_18h": t18["duration_minutes"],
            "net_bps_12h": t12["net_after_funding_bps"],
            "net_bps_18h": t18["net_after_funding_bps"],
            "same_exit_outcome": same_outcome,
        })

    return {
        "n_12h": len(trades_12h),
        "n_18h": len(trades_18h),
        "common_event_keys": len(common_keys),
        "identical_entry_count": identical_entry_count,
        "identical_exit_outcome_count": identical_exit_outcome_count,
        "identical_exit_pct": (identical_exit_outcome_count / len(common_keys) * 100.0) if common_keys else 0.0,
        "details": details,
    }


def compute_leave_one_event_out_influence(
    trades: list[dict[str, Any]],
) -> dict[str, Any]:
    """Jackknife leave-one-out influence analysis across executed trades."""
    n = len(trades)
    if n == 0:
        return {"n": 0, "influences": []}

    net_bps = np.array([float(t["net_after_funding_bps"]) for t in trades], dtype=np.float64)
    net_usdt = np.array([float(t["net_after_funding_usdt"]) for t in trades], dtype=np.float64)

    total_mean_bps = float(np.mean(net_bps))
    total_net_usdt = float(np.sum(net_usdt))

    pos_usdt_total = float(np.sum(net_usdt[net_usdt > 0]))
    neg_usdt_total = float(np.abs(np.sum(net_usdt[net_usdt < 0])))
    total_pf = pos_usdt_total / neg_usdt_total if neg_usdt_total > 0 else (999.0 if pos_usdt_total > 0 else 0.0)

    influences: list[dict[str, Any]] = []

    for i in range(n):
        subset_bps = np.delete(net_bps, i)
        subset_usdt = np.delete(net_usdt, i)

        mean_loo = float(np.mean(subset_bps)) if len(subset_bps) > 0 else 0.0
        sum_usdt_loo = float(np.sum(subset_usdt))

        pos_loo = float(np.sum(subset_usdt[subset_usdt > 0]))
        neg_loo = float(np.abs(np.sum(subset_usdt[subset_usdt < 0])))
        pf_loo = pos_loo / neg_loo if neg_loo > 0 else (999.0 if pos_loo > 0 else 0.0)

        delta_mean_bps = total_mean_bps - mean_loo
        profit_share_pct = (float(net_usdt[i]) / total_net_usdt * 100.0) if total_net_usdt > 0 else 0.0

        influences.append({
            "event_id": trades[i]["event_id"],
            "fold": trades[i].get("fold", ""),
            "trade_index": i + 1,
            "trade_net_bps": float(net_bps[i]),
            "trade_net_usdt": float(net_usdt[i]),
            "profit_share_pct": profit_share_pct,
            "mean_net_bps_loo": mean_loo,
            "delta_mean_bps": delta_mean_bps,
            "net_usdt_loo": sum_usdt_loo,
            "pf_loo": pf_loo,
        })

    # Sort by profit share descending to highlight dominant events
    sorted_by_share = sorted(influences, key=lambda x: x["trade_net_usdt"], reverse=True)
    top_1_event = sorted_by_share[0] if sorted_by_share else None
    top_1_share = top_1_event["profit_share_pct"] if top_1_event else 0.0

    return {
        "n": n,
        "total_mean_net_bps": total_mean_bps,
        "total_net_usdt": total_net_usdt,
        "total_profit_factor": total_pf,
        "top_dominant_event": top_1_event,
        "top_1_profit_share_pct": top_1_share,
        "is_highly_concentrated": top_1_share >= 50.0,
        "influences": influences,
    }


def compute_gross_fee_economics(
    trades: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute exact cash attribution across gross, fees, execution drag, and funding."""
    if not trades:
        return {
            "n": 0,
            "gross_usdt": 0.0,
            "fee_usdt": 0.0,
            "execution_drag_usdt": 0.0,
            "trading_net_usdt": 0.0,
            "funding_usdt": 0.0,
            "net_usdt": 0.0,
            "gross_to_fee_ratio": 0.0,
            "win_count": 0,
            "loss_count": 0,
            "win_rate_pct": 0.0,
        }

    gross = float(sum(float(t["gross_usdt"]) for t in trades))
    fee_entry = float(sum(float(t["fee_entry"]) for t in trades))
    fee_exit = float(sum(float(t["fee_exit"]) for t in trades))
    total_fee = fee_entry + fee_exit
    drag = float(sum(float(t.get("execution_drag_usdt", 0.0)) for t in trades))
    trading_net = float(sum(float(t.get("trading_net_usdt", 0.0)) for t in trades))
    funding = float(sum(float(t.get("funding_usdt", 0.0)) for t in trades))
    net = float(sum(float(t["net_after_funding_usdt"]) for t in trades))

    wins = sum(1 for t in trades if float(t["net_after_funding_usdt"]) > 0)
    losses = sum(1 for t in trades if float(t["net_after_funding_usdt"]) < 0)
    n = len(trades)
    win_rate = (wins / n * 100.0) if n > 0 else 0.0
    gross_to_fee = gross / total_fee if total_fee > 0 else 0.0

    return {
        "n": n,
        "gross_usdt": gross,
        "fee_entry_usdt": fee_entry,
        "fee_exit_usdt": fee_exit,
        "total_fee_usdt": total_fee,
        "execution_drag_usdt": drag,
        "trading_net_usdt": trading_net,
        "funding_usdt": funding,
        "net_usdt": net,
        "gross_to_fee_ratio": gross_to_fee,
        "win_count": wins,
        "loss_count": losses,
        "win_rate_pct": win_rate,
    }


def audit_profit_factor_sentinels(
    annual_metrics: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Analyze profit factor values to distinguish finite statistical evidence from division-by-zero sentinels."""
    audit_results: dict[str, Any] = {}
    for period, metrics in annual_metrics.items():
        pf = float(metrics.get("profit_factor", 0.0))
        n = int(metrics.get("n", 0))
        total_net = float(metrics.get("total_net_usdt", 0.0))

        is_sentinel = abs(pf - 999.0) < 1e-4
        audit_results[period] = {
            "n": n,
            "profit_factor": pf,
            "total_net_usdt": total_net,
            "is_division_by_zero_sentinel": is_sentinel,
            "scientific_interpretation": (
                "ZERO_LOSS_PLACEHOLDER_NOT_FINITE_STATISTICAL_EVIDENCE"
                if is_sentinel
                else ("CALCULATED_FINITE_RATIO" if n > 0 else "ZERO_TRADES")
            ),
        }
    return audit_results


def classify_source_causality_and_known_at() -> dict[str, Any]:
    """Point-in-time classification of data sources and causality assumptions."""
    return {
        "last_1m_close": {
            "role": "TRADEABLE_FILL_PROXY",
            "description": "Last traded transaction price from completed 1m trade kline.",
            "execution_delay_enforced": "1 minute (t_entry = t_decision + 1m)",
            "known_at_soundness": "SOUND_POINT_IN_TIME_PROXY",
        },
        "mark_1m_close": {
            "role": "VALUATION_PROXY_NON_TRADEABLE",
            "description": (
                "Composite Mark price used by exchange for margin and liquidation checks. "
                "Not an executable book or order queue; cannot be directly traded against."
            ),
            "known_at_soundness": "VALUATION_ONLY_NOT_EXECUTABLE",
        },
        "mark_exchange_publication_timestamp": {
            "role": "HISTORICAL_BROADCAST_TIME",
            "description": (
                "Exact historical network dissemination timestamp of the Mark feed is UNKNOWN "
                "in public archived 1m CSV klines. Archive records are retrospective 1m buckets."
            ),
            "known_at_soundness": "RETROSPECTIVE_ARCHIVE_UNKNOWN_INTRAMINUTE_BROADCAST",
        },
        "settled_funding_timestamp": {
            "role": "CASHFLOW_SETTLEMENT_TIME",
            "description": "Settled rate published at 8h intervals; 1m delay enforced before entry.",
            "known_at_soundness": "BOUNDED_POINT_IN_TIME",
        },
        "feature_construction_causality": {
            "uses_future_extrema": False,
            "uses_completed_bars_only": True,
            "intra_hour_warmup_preserved": True,
        },
    }
