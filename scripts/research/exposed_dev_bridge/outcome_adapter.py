"""Authorization-gated, synthetic-tested source-to-P1 outcome panel adapter.

Converts verified native 1m price bars, 5m metrics stocks, mark price klines,
and 8h funding rate settlements into a strategy_eval.normalized.v1 compatible
hourly grid with strict causal cutoff, fixed 10 X controls, Z state, and
multi-horizon Outcome objects with right-boundary embargo enforcement.

Real callers live in archive_adapter behind both authorization gates. This
module's generators and demo use synthetic data exclusively.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from scripts.research.cross_venue import normalized_sources as n
from scripts.research.strategy_eval import DAY, HORIZONS, LABELS, SEED
from scripts.research.strategy_eval import clocked_dataset as p1_data
from scripts.research.strategy_eval.costs import (
    BASELINE,
    US,
    CostAssumptions,
    Outcome,
    Settlement,
    economics,
    finite,
    policy_action,
)

TASK = "V065-P3-R3-REAL-SOURCE-ADAPTER-INTEGRATION-R1"
H39_CUTOFF_US = n.utc_us("2026-09-01T00:00:00.000000Z")
# Gap fixtures only. Real reads use observed native absence, not assumed dates.
JUNE_2026_MARK_GAP_START_US = n.utc_us("2026-06-29T00:00:00.000000Z")
JUNE_2026_MARK_GAP_END_US = n.utc_us("2026-06-30T00:00:00.000000Z")


@dataclass(frozen=True, slots=True)
class SimpleBar:
    t: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float
    taker_buy_volume: float
    taker_buy_quote_volume: float


@dataclass(frozen=True, slots=True)
class SimpleStock:
    t: int
    base_oi: float
    top_position_ls: float


# ---------------------------------------------------------------------------
# 1. Timing & Horizon Maturity (Right-Boundary Embargo Isolation)
# ---------------------------------------------------------------------------

def is_origin_mature(origin_t: int, horizon_h: int, embargo_utc_us: int = H39_CUTOFF_US) -> bool:
    """A price row at the half-open protected boundary cannot be read."""
    n.require(type(origin_t) is int and origin_t % 3600 == 60
              and type(horizon_h) is int and horizon_h in HORIZONS,
              "OUTCOME_CLOCK_INVALID")
    entry_t = origin_t + 60
    exit_t = entry_t + horizon_h * 3600
    return exit_t * US < embargo_utc_us


def horizon_max_origin(horizon_h: int, embargo_utc_us: int = H39_CUTOFF_US) -> int:
    """Return the latest HH:01 timestamp that matures strictly before embargo."""
    latest_sec = (embargo_utc_us - 1) // US - 120 - horizon_h * 3600
    return (latest_sec // 3600) * 3600 + 60


def validate_horizon_limits(origins: list[int], embargo_utc_us: int = H39_CUTOFF_US) -> dict[int, dict[str, Any]]:
    """Enforce per-horizon origin limits as executable rules rather than narrative comments."""
    limits = {}
    for h in HORIZONS:
        max_origin = horizon_max_origin(h, embargo_utc_us)
        eligible = [t for t in origins if is_origin_mature(t, h, embargo_utc_us)]
        exceeded = [t for t in origins if not is_origin_mature(t, h, embargo_utc_us)]
        limits[h] = {
            "horizon_hours": h,
            "max_eligible_origin_utc": n.iso_us(max_origin * US),
            "max_eligible_origin_t": max_origin,
            "eligible_origin_count": len(eligible),
            "embargo_blocked_count": len(exceeded),
            "first_blocked_origin": n.iso_us(min(exceeded) * US) if exceeded else None,
        }
    return limits


# ---------------------------------------------------------------------------
# 2. Data Availability & Gap Handling
# ---------------------------------------------------------------------------

def is_mark_price_available(t_us: int, known_gaps: list[tuple[int, int]] | None = None) -> bool:
    """Detect Binance mark price gaps (such as June 29, 2026 1440-minute gap)."""
    gaps = known_gaps if known_gaps is not None else []
    return not any(start <= t_us < end for start, end in gaps)


def filter_btc_funding_events(all_swap_events: list[dict[str, Any]],
                              symbol: str = "BTC-USDT-SWAP") -> list[dict[str, Any]]:
    """Distinguish OKX aggregated ALL_SWAPS archive gaps from target BTC-USDT-SWAP.

    An archive-level gap in altcoin swaps does NOT imply missing BTC settlements.
    Only instrument-specific missing settlements invalidate BTC coverage.
    """
    return [e for e in all_swap_events if e.get("instrument_name", e.get("symbol")) == symbol
            and e.get("symbol", symbol) == symbol]


def resolve_funding_settlements(
    entry_t: int,
    exit_t: int,
    funding_rates: dict[int, float],
    mark_prices: dict[int, float],
    funding_coverage_us: tuple[int, int],
    known_mark_gaps: list[tuple[int, int]] | None = None,
) -> tuple[tuple[Settlement, ...] | None, tuple[int, ...], str]:
    """Resolve standard 8h funding settlements between entry and exit (entry < settlement <= exit)."""
    # 8-hour settlements occur at 00:00, 08:00, 16:00 UTC (every 28800 seconds)
    first_slot = (entry_t // 28800 + 1) * 28800
    expected_times = [t for t in range(first_slot, exit_t + 1, 28800) if entry_t < t <= exit_t]
    expected_us = tuple(t * US for t in expected_times)

    if (len(funding_coverage_us) != 2
            or not funding_coverage_us[0] <= entry_t * US < exit_t * US <= funding_coverage_us[1]):
        return None, expected_us, "UNRESOLVED_FUNDING_COVERAGE"

    if not expected_times:
        return (), (), "RESOLVED"

    settlements = []
    for t in expected_times:
        t_us = t * US
        if not is_mark_price_available(t_us, known_mark_gaps):
            return None, expected_us, "UNRESOLVED_FUNDING_RATE_OR_MARK"
        rate = funding_rates.get(t)
        mark = mark_prices.get(t)
        if rate is None or not finite(rate):
            return None, expected_us, "UNRESOLVED_FUNDING_SETTLEMENT"
        if mark is None or not finite(mark) or mark <= 0:
            return None, expected_us, "UNRESOLVED_FUNDING_RATE_OR_MARK"
        settlements.append(Settlement(t_us=t_us, rate=float(rate), mark=float(mark)))

    return tuple(settlements), expected_us, "RESOLVED"


# ---------------------------------------------------------------------------
# 3. Outcome Construction for an Hourly Origin
# ---------------------------------------------------------------------------

def build_origin_outcome(
    origin_t: int,
    horizon_h: int,
    perp_1m_bars: dict[int, SimpleBar],
    mark_prices: dict[int, float],
    funding_rates: dict[int, float],
    funding_coverage_us: tuple[int, int],
    embargo_utc_us: int = H39_CUTOFF_US,
    known_mark_gaps: list[tuple[int, int]] | None = None,
) -> tuple[Outcome | None, str]:
    """Construct an immutable Outcome object adhering to P1 research contract."""
    # Maturation guard against embargo boundary
    if not is_origin_mature(origin_t, horizon_h, embargo_utc_us):
        return None, "OUTCOME_MATURITY_BLOCKED_BY_EMBARGO"

    entry_t = origin_t + 60  # HH:02
    exit_t = entry_t + horizon_h * 3600  # (HH + H):02

    entry_bar = perp_1m_bars.get(entry_t)
    if isinstance(entry_bar, p1_data.Bar) and (entry_bar.t != entry_t or entry_bar.market != "futures_um"
            or entry_bar.symbol != "BTCUSDT" or entry_bar.venue != "binance"
            or not p1_data._bar_valid(entry_bar)):
        return None, "OUTCOME_PRICE_SOURCE_INVALID"
    entry_price = (entry_bar.opening if isinstance(entry_bar, p1_data.Bar) else
                   entry_bar.open if entry_bar is not None else None)
    if not finite(entry_price) or entry_price <= 0:
        return None, "UNRESOLVED_ENTRY_PRICE"

    exit_bar = perp_1m_bars.get(exit_t)
    if isinstance(exit_bar, p1_data.Bar) and (exit_bar.t != exit_t or exit_bar.market != "futures_um"
            or exit_bar.symbol != "BTCUSDT" or exit_bar.venue != "binance"
            or not p1_data._bar_valid(exit_bar)):
        return None, "OUTCOME_PRICE_SOURCE_INVALID"
    exit_price = (exit_bar.opening if isinstance(exit_bar, p1_data.Bar) else
                  exit_bar.open if exit_bar is not None else None)
    if not finite(exit_price) or exit_price <= 0:
        return None, "UNRESOLVED_EXIT_PRICE"

    settlements, expected_us, reason = resolve_funding_settlements(
        entry_t, exit_t, funding_rates, mark_prices, funding_coverage_us, known_mark_gaps
    )
    if settlements is None:
        return None, reason

    outcome = Outcome(
        entry_t=entry_t,
        exit_t=exit_t,
        entry_price=float(entry_price),
        exit_price=float(exit_price),
        settlements=settlements,
        expected_settlements_us=expected_us,
        funding_coverage_us=funding_coverage_us,
    )
    return outcome, "RESOLVED"


# ---------------------------------------------------------------------------
# 4. Feature Construction: 10 Fixed X Controls & Z Overhang State
# ---------------------------------------------------------------------------

def extract_x_controls(
    perp_1m_bars: dict[int, SimpleBar],
    spot_1m_bars: dict[int, SimpleBar] | None,
    cutoff_t: int,
) -> tuple[list[float] | None, bool, int | None, str]:
    """Delegate all formulas and missingness checks to frozen P1 controls."""
    def window(bars, market):
        result = []
        for t in range(cutoff_t - DAY - 60, cutoff_t, 60):
            bar = (bars or {}).get(t)
            if bar is not None:
                result.append(as_p1_bar(bar, market))
        return result

    futures, spot = window(perp_1m_bars, "futures_um"), window(spot_1m_bars, "spot")
    x, reason = p1_data.controls(futures, spot, cutoff_t)
    return x, x is not None, futures[-1].close_us if futures else None, reason


def as_p1_bar(bar: SimpleBar | p1_data.Bar, market: str) -> p1_data.Bar:
    if isinstance(bar, p1_data.Bar):
        return bar
    return p1_data.Bar(bar.t * US, (bar.t + 60) * US - 1,
                       bar.open, bar.high, bar.low, bar.close, bar.volume,
                       bar.quote_volume, bar.taker_buy_quote_volume, market=market)


def extract_z_state(
    metrics_5m: dict[int, SimpleStock],
    cutoff_t: int,
) -> dict[str, Any]:
    """Keep P1's native interval, identity, age and exact predecessor rules."""
    stocks = {t: s if isinstance(s, p1_data.Stock) else
              p1_data.Stock(s.t, s.base_oi, s.top_position_ls) for t, s in metrics_5m.items()}
    n.require(all(t == s.t for t, s in stocks.items()), "Z_TIMESTAMP_INVALID")
    return p1_data.select_z(stocks, sorted(stocks), cutoff_t)


# ---------------------------------------------------------------------------
# 5. Panel Grid & Row Assembly
# ---------------------------------------------------------------------------

def build_panel_row(
    origin_t: int,
    perp_1m_bars: dict[int, SimpleBar],
    spot_1m_bars: dict[int, SimpleBar] | None,
    mark_prices: dict[int, float],
    metrics_5m: dict[int, SimpleStock],
    funding_rates: dict[int, float],
    funding_coverage_us: tuple[int, int],
    embargo_utc_us: int = H39_CUTOFF_US,
    known_mark_gaps: list[tuple[int, int]] | None = None,
) -> dict[str, Any]:
    """Assemble single hourly HH:01 row matching strategy_eval.normalized.v1."""
    cutoff_t = origin_t - 60  # C = HH:00

    x_vals, x_ok, x_end_us, x_reason = extract_x_controls(perp_1m_bars, spot_1m_bars, cutoff_t)
    z_dict = extract_z_state(metrics_5m, cutoff_t)

    outcomes, reasons = {}, {}
    for h in HORIZONS:
        outc, outc_reason = build_origin_outcome(
            origin_t, h, perp_1m_bars, mark_prices, funding_rates,
            funding_coverage_us, embargo_utc_us, known_mark_gaps
        )
        reasons[str(h)] = outc_reason
        if outc is not None:
            outcomes[str(h)] = outc.to_dict()

    # Check P1 readiness
    z_ok = z_dict["z_status"] == "OBSERVED" and z_dict["z_4h_exact"] is True
    native_feature_ready = x_ok and z_ok

    row = {
        "t": origin_t,
        "asset": "BTC",
        "action": "NO_ACTION",
        "x": x_vals,
        "x_complete": x_ok,
        "x_reason": x_reason,
        "x_end_us": x_end_us,
        "z": z_dict["z"],
        "z_status": z_dict["z_status"],
        "z_reason": z_dict["z_reason"],
        "z_t": z_dict["z_t"],
        "z_4h_exact": z_dict["z_4h_exact"],
        "raw_z_present": z_dict["raw_z_present"],
        "native_feature_ready": native_feature_ready,
        "outcomes": outcomes,
        "outcome_reasons": reasons,
        "labels": list(LABELS),
    }
    return row


# ---------------------------------------------------------------------------
# 6. Delegation to P1 Economics (Zero-Duplication Interface)
# ---------------------------------------------------------------------------

def evaluate_panel_economics(
    panel_rows: list[dict[str, Any]],
    horizon_h: int = 8,
    prediction: float = 0.0050,  # 50 bps synthetic directional signal
    assumptions: CostAssumptions = BASELINE,
) -> dict[str, Any]:
    """Demonstrate direct delegation to frozen P1 after-cost economics engine."""
    results = []
    action = policy_action(prediction, horizon_h, assumptions)

    for row in panel_rows:
        raw_outc = row.get("outcomes", {}).get(str(horizon_h))
        outcome_obj = (raw_outc if isinstance(raw_outc, Outcome) else
                       Outcome.from_dict(raw_outc) if raw_outc is not None else None)
        requested = action if p1_data.ready(row)[1] else 0
        econ = economics(outcome_obj, requested, horizon_h, assumptions)
        if requested and outcome_obj is None:
            econ["reason"] = row.get("outcome_reasons", {}).get(str(horizon_h), "MISSING_OUTCOME")
        results.append(econ)

    resolved = [r for r in results if r["status"] == "RESOLVED"]
    return {
        "horizon_hours": horizon_h,
        "policy_action": action,
        "cost_scenario": assumptions.name,
        "total_origins": len(panel_rows),
        "resolved_trades": len(resolved),
        "no_action_origins": sum(r["status"] == "NO_ACTION" for r in results),
        "unresolved_origins": sum(r["status"] == "UTILITY_UNRESOLVED" for r in results),
        "mean_net_return": float(np.mean([r["net_return"] for r in resolved])) if resolved else None,
        "mean_gross_return": float(np.mean([r["gross_return"] for r in resolved])) if resolved else None,
        "mean_funding_debit": float(np.mean([r["funding_debit"] for r in resolved])) if resolved else None,
        "mean_total_cost": float(np.mean([r["total_cost"] for r in resolved])) if resolved else None,
        "sleeve_pnl_sum": (None if any(r["status"] == "UTILITY_UNRESOLVED" for r in results)
                           else float(sum(r["sleeve_pnl"] for r in results))),
    }


# ---------------------------------------------------------------------------
# 7. Synthetic Dataset Generator & Demo Pipeline
# ---------------------------------------------------------------------------

def generate_synthetic_fixture_data(
    start_t: int,
    n_hours: int,
    seed: int = SEED,
    inject_mark_gap: bool = False,
    inject_altcoin_okx_gap: bool = True,
) -> dict[str, Any]:
    """Generate deterministic synthetic multi-venue price, stock, and funding streams."""
    rng = np.random.default_rng(seed)
    n_mins = n_hours * 60 + 1441 + 24 * 60 + 120  # Lookback + horizon exit buffer
    t_base = start_t - 1441 * 60
    t_base_metrics = (start_t - 1441 * 60) // 300 * 300

    # Synthetic price random walk
    increments = rng.normal(0, 0.00012, n_mins)
    prices = 40000.0 * np.exp(np.cumsum(increments))
    spot_prices = prices * (1.0 + rng.normal(0, 0.00005, n_mins))

    perp_1m_bars = {}
    spot_1m_bars = {}
    for i in range(n_mins):
        t = int(t_base + i * 60)
        p = float(prices[i])
        vol = float(15.0 + rng.uniform(0, 5))
        tb_vol = float(vol * rng.uniform(0.4, 0.6))
        perp_1m_bars[t] = SimpleBar(
            t=t, open=p, high=float(p * 1.0005), low=float(p * 0.9995), close=p,
            volume=vol, quote_volume=float(vol * p),
            taker_buy_volume=tb_vol, taker_buy_quote_volume=float(tb_vol * p)
        )
        sp = float(spot_prices[i])
        spot_1m_bars[t] = SimpleBar(
            t=t, open=sp, high=float(sp * 1.0005), low=float(sp * 0.9995), close=sp,
            volume=vol, quote_volume=float(vol * sp),
            taker_buy_volume=tb_vol, taker_buy_quote_volume=float(tb_vol * sp)
        )

    # Mark prices (sampled 1m)
    mark_prices = {}
    for i in range(n_mins):
        t = int(t_base + i * 60)
        mark_prices[t] = float(prices[i] * (1.0 + rng.normal(0, 0.00002)))

    # 5m Metrics Stocks aligned to 300s
    metrics_5m = {}
    t_end_metrics = t_base + n_mins * 60 + 3600
    for t in range(t_base_metrics, t_end_metrics, 300):
        metrics_5m[t] = SimpleStock(
            t=t,
            base_oi=float(120000.0 + rng.uniform(-100, 100)),
            top_position_ls=float(1.25 + rng.uniform(-0.02, 0.02)),
        )

    # 8h Funding Settlements (every 28800s)
    funding_rates = {}
    first_fund = (t_base // 28800) * 28800
    last_fund = ((t_base + n_mins * 60) // 28800 + 1) * 28800
    for t in range(first_fund, last_fund + 1, 28800):
        funding_rates[t] = float(0.00010 + rng.normal(0, 0.00002))

    known_mark_gaps = []
    if inject_mark_gap:
        # Inject 1440m synthetic mark gap on day 3
        gap_start = start_t + 48 * 3600
        gap_end = gap_start + 24 * 3600
        known_mark_gaps.append((gap_start * US, gap_end * US))
        for t in range(gap_start, gap_end, 60):
            mark_prices.pop(t, None)

    return {
        "start_t": start_t,
        "n_hours": n_hours,
        "perp_1m_bars": perp_1m_bars,
        "spot_1m_bars": spot_1m_bars,
        "mark_prices": mark_prices,
        "metrics_5m": metrics_5m,
        "funding_rates": funding_rates,
        "funding_coverage_us": (t_base * US, (t_base + n_mins * 60) * US),
        "known_mark_gaps": known_mark_gaps,
        "altcoin_gap_injected": inject_altcoin_okx_gap,
    }


def run_synthetic_outcome_bridge(
    output_dir: Path,
    n_hours: int = 120,
    seed: int = SEED,
    embargo_offset_h: int = 24,
) -> dict[str, Any]:
    """Compatibility entry point for the separate TEST-ONLY contract demo."""
    from .synthetic_contract import run_demo
    return run_demo(output_dir, n_hours=n_hours, seed=seed, embargo_offset_h=embargo_offset_h)
