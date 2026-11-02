"""Research-only multi-leg/weight accounting; never routed as a single-leg entry plan."""

from __future__ import annotations

import numpy as np

from btc_quant_agent.economic.funding import FundingModel

from .config import PlatformConfig
from .core import quantize
from .data import SyntheticProvider, dataset_hash, histories
from .execution_model import fee


def target_weights(id: str, prices: np.ndarray, *, target_vol: float = 0.01) -> np.ndarray:
    returns = np.diff(np.log(prices), axis=0)
    n = prices.shape[1]
    if id in ("volatility_target", "rebalance"):
        vol = returns.std(axis=0, ddof=1)
        raw = np.divide(1, vol, out=np.zeros(n), where=vol > 1e-9)
        weights = raw / raw.sum() if raw.sum() else raw
        portfolio_vol = float(np.std(returns @ weights, ddof=1))
        return weights * min(1, target_vol / portfolio_vol) if portfolio_vol else weights
    if id == "relative_strength_rotation":
        momentum = prices[-1] / prices[0] - 1
        chosen = np.argsort(-momentum)[: max(1, n // 2)]
        weights = np.zeros(n)
        weights[chosen] = 1 / len(chosen)
        return weights
    raise ValueError("UNSUPPORTED_ALLOCATION")


def run(config: PlatformConfig) -> dict:
    if len(config.strategies) != 1:
        raise ValueError("research-only portfolios run separately from directional strategies")
    id = config.strategies[0].id
    events = SyntheticProvider().events(config)
    groups = histories(events)
    symbols = list(config.universe)
    carry = id == "funding_carry"
    if carry:
        if config.market != "PERPETUAL":
            raise ValueError("FUNDING_CARRY_REQUIRES_PERPETUAL_AND_SPOT")
        # Generate a distinct spot source; no spot executable quote inferred from a perp candle.
        spot = SyntheticProvider().events(config.model_copy(update={"market": "SPOT"}))
        spot_groups = histories(spot)
        symbols = [config.universe[0] + ":SPOT", config.universe[0] + ":PERP"]
        groups = {symbols[0]: spot_groups[config.universe[0]], symbols[1]: groups[config.universe[0]]}
    if len(symbols) < 2 and id in ("pair_trading", "cointegration_spread"):
        raise ValueError("PAIR_REQUIRES_TWO_INSTRUMENTS")
    if id in ("pair_trading", "cointegration_spread"):
        symbols = symbols[:2]
        groups = {s: groups[s] for s in symbols}
    matrix = np.array([[groups[s][i].candle.close for s in symbols] for i in range(config.bars)])
    qty = np.zeros(len(symbols))
    cash = config.risk.equity
    ledger = []
    path = []
    funding_total = 0.0
    fees = 0.0
    slippage = 0.0
    spread = 0.0
    fm = FundingModel()
    hedge = None
    center = None
    scale = None
    stationarity = None
    if id in ("pair_trading", "cointegration_spread"):
        training = matrix[:60]
        design = np.column_stack([np.ones(60), training[:, 1]])
        intercept, hedge = np.linalg.lstsq(design, training[:, 0], rcond=None)[0]
        residual = training[:, 0] - (intercept + hedge * training[:, 1])
        center = float(residual.mean())
        scale = float(residual.std(ddof=1))
        # This diagnostic is not a cointegration acceptance test. Refuse an unsupported claim.
        if id == "cointegration_spread":
            try:
                from statsmodels.tsa.stattools import coint
            except ImportError as exc:
                raise RuntimeError("cointegration_spread BLOCKED: optional statsmodels unavailable") from exc
            stat, pvalue, _ = coint(training[:, 0], training[:, 1])
            stationarity = {"training_only_pvalue": float(pvalue), "statistic": float(stat)}
            if pvalue >= 0.05:
                raise ValueError("TRAINING_COINTEGRATION_NOT_ESTABLISHED; no spread trade")
    grid_anchor = None
    for i in range(60, config.bars):
        current = [groups[s][i] for s in symbols]
        if any(e.quote is None or e.quote.reason(e.spec, e.decision_ts) for e in current):
            path.append(
                {
                    "ts": current[0].decision_ts,
                    "equity": cash + float(qty @ matrix[i]),
                    "status": "MISSING_QUOTES",
                }
            )
            continue
        funding = 0.0
        for j, e in enumerate(current):
            d = e.derivatives
            if e.spec.market == "PERPETUAL" and d and d.funding_settlement and qty[j] != 0:
                if d.funding_rate is None or d.mark_price is None:
                    raise ValueError("MULTILEG_FUNDING_UNKNOWN")
                funding += fm.calculate_cashflow(qty[j], d.mark_price, d.funding_rate)
        cash += funding
        funding_total += funding
        equity = cash + float(qty @ matrix[i])
        weights = None
        if carry and i == 60:
            weights = np.array([0.45, -0.45])
        elif id in ("pair_trading", "cointegration_spread") and i % 5 == 0:
            spread_value = matrix[i - 1, 0] - (intercept + hedge * matrix[i - 1, 1])
            z = (spread_value - center) / scale if scale else 0
            sign = -np.sign(z) if abs(z) > 1 else 0
            # Leg dollars proportional to observed hedge quantity, with explicit gross capital cap.
            raw = np.array([sign, -sign * hedge * matrix[i - 1, 1] / matrix[i - 1, 0]])
            weights = raw / (np.abs(raw).sum() or 1) * 0.8
        elif id in ("volatility_target", "rebalance", "relative_strength_rotation") and i % 20 == 0:
            weights = target_weights(id, matrix[max(0, i - 40) : i]) * 0.8
        elif id == "grid":
            history = matrix[i - 40 : i, 0]
            # Only activate a stationary-looking range and use prior observed range boundaries.
            if np.std(history) > 0 and abs(history[-1] - history[0]) < 2 * np.std(history):
                if grid_anchor is None:
                    grid_anchor = (float(np.quantile(history, 0.25)), float(np.quantile(history, 0.75)))
                bid, ask = float(current[0].quote.bid), float(current[0].quote.ask)
                desired = 0.3 if ask < grid_anchor[0] else 0 if bid > grid_anchor[1] else None
                if desired is not None:
                    weights = np.zeros(len(symbols))
                    weights[0] = desired
            elif qty[0] != 0:
                weights = np.zeros(len(symbols))
                grid_anchor = None
        if weights is not None:
            if config.market != "PERPETUAL" and (weights < 0).any():
                raise ValueError("SHORT_BORROW_NOT_MODELED")
            gross = float(np.abs(weights).sum())
            occupancy = float(
                np.maximum(weights, 0).sum() + np.abs(np.minimum(weights, 0)).sum() / config.risk.leverage
            )
            if gross > config.risk.max_gross or occupancy > 1:
                raise ValueError("MULTILEG_CAPITAL_LIMIT")
            target = weights * max(0, equity) / matrix[i]
            for j, e in enumerate(current):
                delta = target[j] - qty[j]
                if abs(delta) < float(e.spec.quantity_step):
                    continue
                amount = float(quantize(abs(delta), e.spec.quantity_step)) * (1 if delta > 0 else -1)
                price = float(e.quote.ask if amount > 0 else e.quote.bid)
                reference = float((e.quote.bid + e.quote.ask) / 2)
                actual = float(
                    quantize(
                        price * (1 + np.sign(amount) * config.execution.slippage_bps / 10000),
                        e.spec.tick_size,
                        up=amount > 0,
                    )
                )
                f = fee(amount * actual, config)
                cash -= amount * actual + f
                qty[j] += amount
                fees += f
                slippage += abs(amount) * abs(actual - price)
                spread += abs(amount) * abs(price - reference)
                ledger.append(
                    {
                        "ts": e.decision_ts,
                        "leg": symbols[j],
                        "quantity_delta": amount,
                        "actual": actual,
                        "fees": f,
                        "funding": funding,
                        "status": "SIMULATED_RESEARCH_ONLY",
                    }
                )
        liquidation_cost = sum(
            abs(qty[j])
            * matrix[i, j]
            * (
                max(config.execution.fee_bps, 0)
                + config.execution.slippage_bps
                + config.execution.spread_bps / 2
            )
            / 10000
            for j in range(len(symbols))
        )
        path.append(
            {
                "ts": current[0].decision_ts,
                "equity": cash + float(qty @ matrix[i]) - liquidation_cost,
                "gross_notional": float(np.abs(qty * matrix[i]).sum()),
                "leg_quantities": qty.tolist(),
            }
        )
    eq = np.array([config.risk.equity] + [x["equity"] for x in path])
    return {
        "strategy": id,
        "status": "RESEARCH_ONLY",
        "exposure": "SYNTHETIC",
        "config_hash": config.hash,
        "dataset_hash": dataset_hash(events),
        "leg_sources": [
            {"symbol": s, "provider": "synthetic", "market": groups[s][0].spec.market} for s in symbols
        ],
        "metrics": {
            "modeled_return": float(eq[-1] / eq[0] - 1),
            "modeled_net_pnl": float(eq[-1] - eq[0]),
            "max_drawdown": float((eq / np.maximum.accumulate(eq) - 1).min()),
            "fees": fees,
            "funding_cashflow": funding_total,
            "slippage": slippage,
            "spread_cost": spread,
            "leg_fills": len(ledger),
            "closed_trades": None,
        },
        "ledger": ledger,
        "equity": path,
        "open_legs_at_cutoff": dict(zip(symbols, qty.tolist())),
        "stationarity": stationarity,
        "limitations": [
            "Research-only weights/legs, not a single-leg advisory signal.",
            "No borrow, cross-exchange transfer, legging latency, or tiered liquidation model.",
            "Cointegration test is training-only and does not establish stable out-of-sample economics.",
            "Funding fixture settlement schedule is synthetic, not an exchange calendar.",
        ],
    }
