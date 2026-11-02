"""Portfolio event replay sharing advisory decisions; explicitly modeled economics."""

from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import groupby

import numpy as np
import pandas as pd

from btc_quant_agent.economic.funding import FundingModel

from .advisory import gate, scan
from .config import PlatformConfig
from .core import BacktestRun, Lifecycle, StrategyCandidate, fingerprint, primitive, quantize
from .data import SyntheticProvider, dataset_hash, frame, histories
from .execution_model import entry_fill, exit_price, fee
from .factors import FeaturePipeline
from .portfolio import Exposure


@dataclass
class OpenTrade:
    candidate: StrategyCandidate
    entry_ts: int
    entry_index: int
    entry: float
    reference_entry: float
    original_quantity: float
    quantity: float
    stop: float
    initial_risk: float
    multiplier: float
    entry_cost: float
    entry_slippage: float
    entry_spread: float
    funding: float = 0
    gross: float = 0
    exit_fees: float = 0
    exit_spread: float = 0
    exit_slippage: float = 0
    partial_done: bool = False
    stop_triggered: bool = False
    beta: float | None = None


def manage_episode(position, event, policy):
    """Use exactly the user-supervisor policy; fills/accounting remain separate simulation facts."""
    from .selection.management import manage

    return manage(position, event, policy)


def build_pipeline(events, config):
    groups = histories(events)
    cutoff = max(e.decision_ts for e in events)
    pipeline = FeaturePipeline({s: frame(h, cutoff) for s, h in groups.items()}, config.benchmark)
    indices = {s: {int(ts): i for i, ts in enumerate(df.ts)} for s, df in pipeline.frames.items()}
    return pipeline, indices


def correlations(pipeline, indices, events, exposures):
    result = {}
    for event in events:
        symbol = event.spec.symbol
        ts = event.candle.close_time_ms
        a = pipeline.frames[symbol]
        a = a.loc[a.ts <= ts].tail(31).set_index("ts").close.pct_change(fill_method=None)
        for other in exposures:
            b = pipeline.frames[other.symbol]
            b = b.loc[b.ts <= ts].tail(31).set_index("ts").close.pct_change(fill_method=None)
            joined = pd.concat([a, b], axis=1).dropna()
            if len(joined) >= 20:
                value = joined.iloc[:, 0].corr(joined.iloc[:, 1])
                if np.isfinite(value):
                    result[(symbol, other.symbol)] = float(value)
    return result


def run(config: PlatformConfig, events=None, source_hash: str = "unrecorded") -> dict:
    if any(
        __import__("btc_quant_agent.platform.strategies", fromlist=["REGISTRY"]).REGISTRY[s.id].status
        == "RESEARCH_ONLY"
        for s in config.strategies
    ):
        raise ValueError(
            "Research-only portfolio strategies require the portfolio research command; single-leg replay refused"
        )
    events = events if events is not None else SyntheticProvider().events(config)
    if not events:
        raise ValueError("EMPTY_DATASET")
    if any(e.provenance.exposure != "SYNTHETIC" for e in events):
        raise ValueError("ONLY_SYNTHETIC_AUTHORIZED")
    keys = [(e.decision_ts, e.spec.symbol) for e in events]
    if keys != sorted(set(keys)):
        raise ValueError("EVENT_ORDER_OR_DUPLICATE_INVALID")
    pipeline, all_indices = build_pipeline(events, config)
    pending = {}
    positions = {}
    plans = []
    decisions = []
    trades = []
    fills = []
    equity = []
    ledger = []
    last = {}
    realized = 0.0
    turnover = 0.0
    funding_model = FundingModel()
    warnings = set(
        [
            "Synthetic data only; no market Alpha or economic validation.",
            "OHLC stop sequencing is conservative; stop-market gaps can exceed planned risk.",
            "Quote crossing is a declared synthetic fill assumption, not observed exchange execution.",
            "Entry fraction caps cancel the unfilled remainder; no queue or market-impact calibration.",
            "Open positions are marked at cutoff with separately modeled liquidation costs.",
        ]
    )
    if config.execution.funding == "exclude_with_warning":
        warnings.add("Funding may be incomplete; modeled-net is not full-net.")

    def close_part(position, event, quantity, reason, reference=None):
        nonlocal realized, turnover
        cost = exit_price(event, position.candidate.direction, config, reference)
        if cost is None:
            decisions.append(
                {
                    "ts": event.decision_ts,
                    "symbol": event.spec.symbol,
                    "action": "RECONCILE",
                    "reason": "EXIT_EXECUTABLE_QUOTE_MISSING",
                }
            )
            return False
        actual, ref, spread, slip = cost
        side = 1 if position.candidate.direction == "LONG" else -1
        mult = position.multiplier
        gross = side * (ref - position.reference_entry) * quantity * mult
        exitfee = fee(actual * quantity * mult, config)
        position.gross += gross
        position.exit_fees += exitfee
        position.exit_spread += spread * quantity * mult
        position.exit_slippage += slip * quantity * mult
        position.quantity = max(0, position.quantity - quantity)
        realized += gross - spread * quantity * mult - slip * quantity * mult - exitfee
        turnover += quantity * actual * mult
        ledger.append(
            {
                "ts": event.decision_ts,
                "symbol": event.spec.symbol,
                "kind": reason,
                "quantity": quantity,
                "reference": ref,
                "actual": actual,
                "gross": gross,
                "fees": exitfee,
                "spread": spread * quantity * mult,
                "slippage": slip * quantity * mult,
            }
        )
        if position.quantity < 1e-9:
            net = (
                position.gross
                - position.entry_cost
                - position.exit_fees
                - position.entry_spread
                - position.exit_spread
                - position.entry_slippage
                - position.exit_slippage
                + position.funding
            )
            trades.append(
                {
                    "id": position.candidate.id,
                    "symbol": event.spec.symbol,
                    "strategy": position.candidate.strategy_id,
                    "direction": position.candidate.direction,
                    "regime": position.candidate.regime,
                    "entry_ts": position.entry_ts,
                    "exit_ts": event.decision_ts,
                    "entry": position.entry,
                    "exit": actual,
                    "quantity": position.original_quantity,
                    "gross": position.gross,
                    "fees": position.entry_cost + position.exit_fees,
                    "spread": position.entry_spread + position.exit_spread,
                    "slippage": position.entry_slippage + position.exit_slippage,
                    "funding": position.funding,
                    "modeled_net": net,
                    "r": net / position.initial_risk if position.initial_risk else None,
                    "holding_minutes": (event.decision_ts - position.entry_ts) / 60000,
                    "reason": reason,
                    "event_cluster": position.candidate.decision_ts // (15 * 60000),
                }
            )
        return True

    for ts, batch_iter in groupby(events, key=lambda e: e.decision_ts):
        batch = list(batch_iter)
        indices = {e.spec.symbol: all_indices[e.spec.symbol].get(e.candle.close_time_ms, -1) for e in batch}
        admissible = []
        for event in batch:
            symbol = event.spec.symbol
            if indices[symbol] < 0 or event.reason(config.execution.source_max_age_ms):
                decisions.append(
                    {"ts": ts, "symbol": symbol, "action": "WAIT", "reason": "SOURCE_INADMISSIBLE"}
                )
                continue
            admissible.append(event)
            last[symbol] = event
            pos = positions.get(symbol)
            if pos is None:
                continue
            side = 1 if pos.candidate.direction == "LONG" else -1
            c = event.candle
            d = event.derivatives
            hit = c.low <= pos.stop if side == 1 else c.high >= pos.stop
            if event.spec.market == "PERPETUAL":
                if d is None or d.provenance.reason(ts, config.execution.source_max_age_ms):
                    warnings.add(
                        "A held perpetual position has missing funding evidence; modeled-net incomplete."
                    )
                elif d.funding_settlement and d.funding_rate is not None and d.mark_price is not None:
                    cash = funding_model.calculate_cashflow(
                        side * pos.quantity * pos.multiplier, d.mark_price, d.funding_rate
                    )
                    if hit and cash > 0:
                        cash = 0.0
                        warnings.add(
                            "Stop/funding intrabar sequence ambiguous: potential funding credits withheld, debits retained."
                        )
                    pos.funding += cash
                    realized += cash
                    ledger.append({"ts": ts, "symbol": symbol, "kind": "FUNDING", "cash": cash})
            # Position only exists after the preceding observation; never apply entry-bar extremes.
            reason = None
            reference = None
            if hit or pos.stop_triggered:
                if config.exits.stop_order == "limit":
                    pos.stop_triggered = True
                    limit = pos.stop * (1 - side * config.exits.stop_limit_offset_bps / 10000)
                    q = event.quote
                    can_exit = (
                        q
                        and not q.reason(event.spec, ts)
                        and (float(q.bid) > limit if side == 1 else float(q.ask) < limit)
                    )
                    if not can_exit:
                        decisions.append(
                            {
                                "ts": ts,
                                "symbol": symbol,
                                "action": "RECONCILE",
                                "reason": "STOP_LIMIT_UNFILLED_EXECUTION_UNKNOWN",
                            }
                        )
                        continue
                    reason = "STOP_LIMIT_CROSSED"
                else:
                    reference = min(c.open, pos.stop) if side == 1 else max(c.open, pos.stop)
                    reason = "STOP_GAP" if side * (c.open - pos.stop) < 0 else "STOP"
            elif pos.candidate.target is not None:
                q = event.quote
                if (
                    q
                    and not q.reason(event.spec, ts)
                    and (q.bid > pos.candidate.target if side == 1 else q.ask < pos.candidate.target)
                ):
                    reason = "OBSERVED_MEAN_TARGET"
            if not reason and indices[symbol] - pos.entry_index >= config.exits.max_holding_bars:
                reason = "TIME_INVALIDATION"
            if reason:
                if close_part(pos, event, pos.quantity, reason, reference):
                    positions.pop(symbol)
                continue
            r = side * (c.close - pos.entry) / (abs(pos.entry - float(pos.candidate.stop)))
            if not pos.partial_done and r >= config.exits.partial_at_r:
                try:
                    amount = float(
                        quantize(pos.quantity * config.exits.partial_fraction, event.spec.quantity_step)
                    )
                except ValueError:
                    amount = 0
                if amount > 0 and close_part(pos, event, amount, "PARTIAL_EXIT"):
                    pos.partial_done = True
            atr = pipeline.result(symbol, "ATR", indices[symbol], ts).value
            if atr and pos.candidate.target is None:
                suggested = c.close - side * config.exits.trailing_atr * atr
                # Becomes active on NEXT event. No hindsight use of today's tightened stop.
                if side * (suggested - pos.stop) > 0:
                    pos.stop = float(quantize(suggested, event.spec.tick_size, up=side == -1))
                    decisions.append({"ts": ts, "symbol": symbol, "action": "TIGHTEN_STOP", "stop": pos.stop})
        exposures = [
            Exposure(s, p.candidate.direction, p.quantity * last[s].candle.close * p.multiplier, p.beta)
            for s, p in positions.items()
        ]
        corr = correlations(pipeline, indices, admissible, exposures)
        for event in admissible:
            symbol = event.spec.symbol
            if symbol not in pending or symbol in positions:
                continue
            candidate = pending[symbol]
            beta = pipeline.result(symbol, "BETA", indices[symbol], ts).value
            plan = gate(candidate, event, config, exposures, corr, beta)
            decisions.append(primitive(plan))
            if plan.state in (Lifecycle.CANCELLED, Lifecycle.EXPIRED):
                pending.pop(symbol)
                continue
            pending[symbol] = replace(candidate, state=plan.state)
            fill = entry_fill(plan, event, config)
            if fill is None:
                continue
            fills.append(primitive(fill))
            mid = float((event.quote.bid + event.quote.ask) / 2)
            multiplier = float(event.spec.multiplier)
            qty = float(fill.quantity)
            side = 1 if candidate.direction == "LONG" else -1
            quoteprice = float(event.quote.ask if side == 1 else event.quote.bid)
            spread = abs(quoteprice - mid) * qty * multiplier
            slip = side * (float(fill.price) - quoteprice) * qty * multiplier
            fills[-1]["spread"] = spread
            risk = qty * abs(float(fill.price) - float(candidate.stop)) * multiplier
            positions[symbol] = OpenTrade(
                candidate,
                ts,
                indices[symbol],
                float(fill.price),
                mid,
                qty,
                qty,
                float(candidate.stop),
                risk,
                multiplier,
                fill.fees,
                slip,
                spread,
                beta=beta,
            )
            realized -= fill.fees + slip + spread
            turnover += float(fill.quantity * fill.price) * multiplier
            exposures.append(
                Exposure(symbol, candidate.direction, qty * float(fill.price) * multiplier, beta)
            )
            # Include newly opened symbols in correlation gate for later simultaneous candidates.
            corr = correlations(pipeline, indices, admissible, exposures)
            pending.pop(symbol)
        discovered = scan(pipeline, admissible, indices, config) if admissible else []
        for candidate in discovered:
            if candidate.symbol in positions or candidate.symbol in pending:
                continue
            pending[candidate.symbol] = candidate
            plans.append(primitive(candidate))
        unrealized = 0.0
        exposure = 0.0
        close_costs = 0.0
        for symbol, pos in positions.items():
            event = last[symbol]
            side = 1 if pos.candidate.direction == "LONG" else -1
            unrealized += side * (event.candle.close - pos.reference_entry) * pos.quantity * pos.multiplier
            exposure += pos.quantity * event.candle.close * pos.multiplier
            close_costs += (
                pos.quantity
                * event.candle.close
                * pos.multiplier
                * (
                    max(config.execution.fee_bps, 0)
                    + config.execution.slippage_bps
                    + config.execution.spread_bps / 2
                )
                / 10000
            )
        equity.append(
            {
                "ts": ts,
                "equity": config.risk.equity + realized + unrealized - close_costs,
                "gross_exposure": exposure,
                "open_positions": len(positions),
                "realized_cash_pnl": realized,
                "estimated_cutoff_exit_cost": close_costs,
            }
        )
    open_positions = [
        {
            "symbol": s,
            "quantity": p.quantity,
            "entry": p.entry,
            "stop": p.stop,
            "strategy": p.candidate.strategy_id,
            "status": "OPEN_AT_CUTOFF",
            "funding": p.funding,
        }
        for s, p in positions.items()
    ]
    metrics = performance(config, plans, fills, trades, equity, ledger, turnover, pipeline)
    metrics["pending_at_cutoff"] = len(pending)
    metrics["open_at_cutoff"] = len(positions)
    identity = fingerprint([config.hash, dataset_hash(events), source_hash])
    record = BacktestRun(
        identity,
        config.hash,
        source_hash,
        dataset_hash(events),
        "SYNTHETIC",
        metrics,
        tuple(sorted(warnings)),
    )
    return {
        "run": primitive(record),
        "configuration": config.model_dump(mode="json"),
        "plans": plans,
        "fills": fills,
        "decisions": decisions,
        "trades": trades,
        "equity": equity,
        "cashflows": ledger,
        "open_positions": open_positions,
        "feature_computations": pipeline.computations,
    }


def performance(config, plans, fills, trades, equity, ledger, turnover, pipeline):
    pnl = np.array([t["modeled_net"] for t in trades], dtype=float)
    path = np.array([config.risk.equity] + [p["equity"] for p in equity])
    dd = path / np.maximum.accumulate(path) - 1
    total = float(path[-1] / path[0] - 1)
    exposure = np.array([x["gross_exposure"] for x in equity])
    positive = float(pnl[pnl > 0].sum())
    negative = -float(pnl[pnl < 0].sum())
    attr = {}
    for field in ("direction", "symbol", "regime", "strategy"):
        attr[field] = {
            value: {
                "trades": sum(t[field] == value for t in trades),
                "modeled_net": sum(t["modeled_net"] for t in trades if t[field] == value),
            }
            for value in sorted({t[field] for t in trades})
        }
    clusters = {}
    for t in trades:
        clusters[t["event_cluster"]] = clusters.get(t["event_cluster"], 0) + t["modeled_net"]
    fees = sum(f["fees"] for f in fills) + sum(x.get("fees", 0) for x in ledger)
    funding = sum(x.get("cash", 0) for x in ledger if x["kind"] == "FUNDING")
    benchmark = pipeline.frames[config.benchmark].close
    return {
        "candidate_plans": len(plans),
        "filled_plans": len(fills),
        "unfilled_plans": len(plans) - len(fills),
        "fill_rate": len(fills) / len(plans) if plans else 0,
        "closed_trades": len(trades),
        "closed_gross_pnl": sum(t["gross"] for t in trades),
        "closed_modeled_net_pnl": float(pnl.sum()),
        "total_marked_modeled_net_pnl": float(path[-1] - path[0]),
        "modeled_return": total,
        "fees": fees,
        "funding_cashflow": funding,
        "slippage": sum(f["slippage"] for f in fills) + sum(x.get("slippage", 0) for x in ledger),
        "spread_cost": sum(f.get("spread", 0) for f in fills) + sum(x.get("spread", 0) for x in ledger),
        "closed_slippage": sum(t["slippage"] for t in trades),
        "closed_spread_cost": sum(t["spread"] for t in trades),
        "cutoff_estimated_exit_cost": equity[-1]["estimated_cutoff_exit_cost"],
        "win_rate": float((pnl > 0).mean()) if len(pnl) else None,
        "win_loss_ratio": float((pnl > 0).sum() / (pnl < 0).sum()) if (pnl < 0).any() else None,
        "profit_factor": positive / negative if negative else None,
        "expectancy_per_trade": float(pnl.mean()) if len(pnl) else None,
        "expectancy_per_event_cluster": float(np.mean(list(clusters.values()))) if clusters else None,
        "event_clusters": len(clusters),
        "average_r": float(np.mean([t["r"] for t in trades])) if trades else None,
        "max_drawdown": float(dd.min()),
        "time_exposure_fraction": float((exposure > 0).mean()),
        "mean_gross_exposure_fraction": float(exposure.mean() / config.risk.equity),
        "exposure_adjusted_return": total / float((exposure > 0).mean()) if (exposure > 0).any() else None,
        "turnover_notional": turnover,
        "turnover_equity": turnover / config.risk.equity,
        "holding_minutes_quantiles": np.quantile(
            [t["holding_minutes"] for t in trades], [0, 0.25, 0.5, 0.75, 1]
        ).tolist()
        if trades
        else [],
        "worst_loss_quantiles": np.quantile(pnl, [0, 0.05, 0.25]).tolist() if len(pnl) else [],
        "benchmark_buy_hold_gross_return": float(benchmark.iloc[-1] / benchmark.iloc[0] - 1),
        "benchmark_cost_semantics": "gross unlevered diagnostic, not a net strategy benchmark",
        "annualized_sharpe": None,
        "sortino": None,
        "risk_estimate_warning": "short synthetic sample; annualization withheld",
        "attribution": attr,
    }
