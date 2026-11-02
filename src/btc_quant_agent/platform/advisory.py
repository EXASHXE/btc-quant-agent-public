"""Common discovery/ranking/entry kernel used by replay and advisory scans."""

from __future__ import annotations

from dataclasses import replace

import pandas as pd

from .config import PlatformConfig
from .core import EntryPlan, Lifecycle, MarketEvent, SourceAdmission, StrategyCandidate, dec, lifecycle_path
from .factors import FeaturePipeline, normalize
from .portfolio import Exposure, size
from .strategies import evaluate, resolve


def scan(
    pipeline: FeaturePipeline,
    events: list[MarketEvent],
    indices: dict[str, int],
    config: PlatformConfig,
    *,
    resolve_conflicts: bool = True,
) -> list[StrategyCandidate]:
    candidates = []
    for event in events:
        for strategy in config.strategies:
            candidate = evaluate(pipeline, event, indices[event.spec.symbol], strategy, config)
            if candidate:
                candidates.append(candidate)
    scored = []
    factor_values = {}
    for factor in config.factors:
        raw = pd.Series(
            {
                e.spec.symbol: pipeline.result(
                    e.spec.symbol, factor.id, indices[e.spec.symbol], e.decision_ts, factor.params
                ).value
                for e in events
            },
            dtype=float,
        )
        factor_values[factor.id] = normalize(raw, factor.normalization)
    for candidate in candidates:
        score, total = 0.0, 0.0
        gates = []
        veto = []
        for factor in config.factors:
            if factor.regimes and candidate.regime not in factor.regimes:
                continue
            value = factor_values[factor.id].get(candidate.symbol)
            if pd.isna(value):
                veto.append("FACTOR_MISSING:" + factor.id)
                if factor.gate_min is not None or factor.gate_max is not None:
                    gates.append(False)
                continue
            weight = factor.regime_weights.get(candidate.regime, factor.weight)
            score += float(value) * weight
            total += abs(weight)
            if factor.gate_min is not None or factor.gate_max is not None:
                gates.append(
                    (factor.gate_min is None or value >= factor.gate_min)
                    and (factor.gate_max is None or value <= factor.gate_max)
                )
        if gates and not (all(gates) if config.entry.factor_condition == "all" else any(gates)):
            veto.append("CONFIRMATORY_FACTOR_GATE")
        scored.append(
            replace(candidate, opportunity_score=score / total if total else 0, veto_reasons=tuple(veto))
        )
    selected = resolve(scored, config) if resolve_conflicts else scored
    return sorted(selected, key=lambda c: (-c.opportunity_score, c.symbol, c.strategy_id))


def gate(
    candidate: StrategyCandidate,
    event: MarketEvent,
    config: PlatformConfig,
    exposures: list[Exposure] | None = None,
    correlations: dict | None = None,
    beta: float | None = None,
    source_admission: SourceAdmission | None = None,
) -> EntryPlan:
    veto = list(candidate.veto_reasons)
    now = event.decision_ts
    q = event.quote
    elapsed = now - candidate.decision_ts
    if candidate.state in (Lifecycle.EXPIRED, Lifecycle.CANCELLED):
        veto.append("PLAN_TERMINAL")
    if candidate.symbol != event.spec.symbol:
        veto.append("SYMBOL_MISMATCH")
    if candidate.provenance.reason(candidate.decision_ts, config.execution.source_max_age_ms):
        veto.append("SETUP_SOURCE_INADMISSIBLE")
    if now >= candidate.expires_ts:
        veto.append("PLAN_EXPIRED")
    if elapsed < config.execution.delay_minutes * 60000:
        veto.append("MANUAL_DELAY_PENDING")
    if elapsed < config.entry.confirmation_bars * config.interval_seconds * 1000:
        veto.append("CONFIRMATION_PENDING")
    if event.reason(config.execution.source_max_age_ms):
        veto.append("SOURCE_STALE_OR_INADMISSIBLE")
    candle = event.candle
    if not candle.closed or candle.close_time_ms > now:
        veto.append("CANDLE_NOT_COMPLETE")
    if candle.available_at_ms is None or candle.available_at_ms > now:
        veto.append("CANDLE_AVAILABILITY_UNKNOWN_OR_FUTURE")
    if source_admission is not None:
        veto.extend(source_admission.vetoes(event, config.hash))
    elif event.spec.provider != "synthetic" or event.provenance.exposure != "SYNTHETIC":
        veto.append("REAL_MARKET_SOURCE_NOT_AUTHORIZED")
    if q is None:
        veto.append("EXECUTABLE_QUOTE_MISSING")
    else:
        reason = q.reason(event.spec, now, config.execution.quote_max_age_ms)
        if reason:
            veto.append(reason)
        spread = float(20000 * (q.ask - q.bid) / (q.ask + q.bid)) if q.bid + q.ask > 0 else float("inf")
        if spread > config.execution.max_spread_bps:
            veto.append("SPREAD_LIMIT")
    long = candidate.direction == "LONG"
    if q is not None:
        available = q.ask_quantity if long else q.bid_quantity
        if available is None:
            veto.append("EXECUTABLE_LIQUIDITY_UNKNOWN")
        elif available <= 0:
            veto.append("EXECUTABLE_LIQUIDITY_EMPTY")
    if (long and event.candle.low <= float(candidate.stop)) or (
        not long and event.candle.high >= float(candidate.stop)
    ):
        veto.append("STRUCTURE_INVALIDATED")
    import json

    original_close = json.loads(candidate.evidence_json)["close"]
    if config.entry.confirmation_bars and (
        (long and event.candle.close <= original_close) or (not long and event.candle.close >= original_close)
    ):
        veto.append("PRICE_CONFIRMATION_PENDING")
    entry = (
        (q.ask if long else q.bid)
        if q and not q.reason(event.spec, now, config.execution.quote_max_age_ms)
        else None
    )
    if entry is not None:
        # Include modeled latency slippage in the actual acceptable price check.
        entry = entry * (1 + dec(config.execution.slippage_bps / 10000) * (1 if long else -1))
        from .core import quantize

        try:
            entry = quantize(entry, event.spec.tick_size, up=long)
        except ValueError:
            veto.append("ENTRY_PRECISION_UNEXECUTABLE")
            entry = None
    if entry is not None:
        if not candidate.entry_low <= entry <= candidate.entry_high:
            veto.append("ENTRY_REGION_LOST")
        if long and entry > candidate.max_entry_price:
            veto.append("MAX_ENTRY_PRICE")
        if not long and entry < candidate.max_entry_price:
            veto.append("MIN_ENTRY_PRICE")
        if candidate.target is not None and (
            (long and entry >= candidate.target) or (not long and entry <= candidate.target)
        ):
            veto.append("OPPORTUNITY_CONSUMED")
    if candidate.opportunity_score < config.entry.min_score:
        veto.append("OPPORTUNITY_RANK_THRESHOLD")
    risk = None
    if not veto and entry is not None:
        derivative = event.derivatives
        funding = None
        if (
            derivative
            and derivative.provenance.provider == event.spec.provider
            and not derivative.field_reason("funding_rate", now, config.execution.source_max_age_ms)
        ):
            funding = derivative.funding_rate
        risk, reasons = size(
            candidate, event.spec, float(entry), config, exposures or [], correlations, funding, beta
        )
        veto.extend(reasons)
    terminal = {
        "STRUCTURE_INVALIDATED",
        "ENTRY_REGION_LOST",
        "OPPORTUNITY_CONSUMED",
        "MAX_ENTRY_PRICE",
        "MIN_ENTRY_PRICE",
    }
    state = (
        Lifecycle.EXPIRED
        if "PLAN_EXPIRED" in veto
        else Lifecycle.CANCELLED
        if terminal.intersection(veto)
        else Lifecycle.ARMED
        if veto
        else Lifecycle.ENTRY_ELIGIBLE
    )
    if candidate.state in (Lifecycle.EXPIRED, Lifecycle.CANCELLED):
        state = candidate.state
    elif candidate.state == Lifecycle.ENTRY_ELIGIBLE and state == Lifecycle.ARMED:
        state = Lifecycle.CANCELLED
        veto.append("ELIGIBILITY_REVOKED")
    action = (
        "CANCEL"
        if state in (Lifecycle.EXPIRED, Lifecycle.CANCELLED)
        else "WAIT"
        if veto
        else "ENTRY_ELIGIBLE"
    )
    return EntryPlan(
        candidate,
        state,
        action,
        risk,
        entry,
        tuple(sorted(set(veto))),
        now,
        config.hash,
        lifecycle_path(candidate.state, state),
    )
