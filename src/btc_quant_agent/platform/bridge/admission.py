"""Separate observation quality, liquid-universe eligibility and entry authority."""

from __future__ import annotations

from dataclasses import dataclass

from ..core import DerivativeSnapshot, MarketEvent, SourceAdmission, fingerprint
from ..data import frame
from ..factors import FeaturePipeline
from .config import BridgeConfig
from .contracts import FieldObservation, NormalizedSnapshot, NormalizedSymbol


@dataclass
class AdmittedSnapshot:
    snapshot: NormalizedSnapshot
    pipeline: FeaturePipeline
    events: dict[str, MarketEvent]
    indices: dict[str, int]
    admission: dict[str, SourceAdmission]
    diagnostics: dict[str, list[str]]


def latest_fields(
    symbol: NormalizedSymbol, cutoff: int, decision_ts: int, max_age: int, candle_ts: int, spot_skew: int
) -> dict[str, FieldObservation]:
    result: dict[str, FieldObservation] = {}
    for observation in symbol.observations:
        p = observation.provenance
        if observation.name == "quote_volume_24h":
            continue
        if p.reason(decision_ts, 10**15) or p.exchange_event_ts > cutoff:
            continue
        if cutoff - p.exchange_event_ts > max_age:
            continue
        if observation.name == "spot_close" and abs(p.exchange_event_ts - candle_ts) > spot_skew:
            continue
        old = result.get(observation.name)
        if old is None or (p.exchange_event_ts, p.available_ts) > (
            old.provenance.exchange_event_ts,
            old.provenance.available_ts,
        ):
            result[observation.name] = observation
    return result


def compile_snapshot(snapshot: NormalizedSnapshot, config: BridgeConfig) -> AdmittedSnapshot:
    now = snapshot.decision_ts
    if type(now) is not int or now <= 0:
        raise ValueError("DECISION_CLOCK_INVALID")
    frames = {}
    events = {}
    diagnostics = {}
    indices = {}
    admissions = {}
    for symbol in snapshot.symbols:
        reasons = []
        record = symbol.instrument
        if record is None:
            diagnostics[symbol.symbol] = ["INSTRUMENT_METADATA_UNKNOWN", *symbol.issues]
            continue
        if record.available_ts > now or now - record.received_ts > config.universe.metadata_max_age_ms:
            diagnostics[symbol.symbol] = ["INSTRUMENT_METADATA_UNAVAILABLE_OR_STALE"]
            continue
        if not record.active:
            reasons.append("INSTRUMENT_NOT_TRADING")
        if record.spec.quote_currency != config.universe.quote_currency:
            reasons.append("QUOTE_CURRENCY_UNSUPPORTED")
        liquidity = [
            x
            for x in symbol.observations
            if x.name == "quote_volume_24h"
            and not x.provenance.reason(now, config.universe.liquidity_max_age_ms)
        ]
        if not liquidity:
            reasons.append("LIQUIDITY_OBSERVATION_UNKNOWN_OR_STALE")
        elif (
            max(liquidity, key=lambda x: (x.provenance.exchange_event_ts, x.provenance.available_ts)).value
            < config.universe.min_quote_volume_24h
        ):
            reasons.append("BELOW_LIQUID_UNIVERSE_THRESHOLD")
        usable = [
            c
            for c in symbol.candles
            if not c.provenance.reason(now, 10**15)
            and c.candle.available_at_ms is not None
            and c.candle.available_at_ms <= now
        ]
        if not usable:
            diagnostics[symbol.symbol] = ["CANDLES_UNAVAILABLE", *reasons, *symbol.issues]
            continue
        history = []
        for index, c in enumerate(usable):
            last = index == len(usable) - 1
            cutoff = now if last else c.candle.close_time_ms
            fields = latest_fields(
                symbol,
                cutoff,
                now,
                config.admission.derivatives_max_age_ms,
                c.candle.close_time_ms,
                config.admission.spot_max_skew_ms,
            )
            values = {name: ob.value for name, ob in fields.items()}
            derivative = (
                DerivativeSnapshot(
                    c.provenance,
                    open_interest=values.get("open_interest"),
                    funding_rate=values.get("funding_rate"),
                    basis=values.get("basis"),
                    premium=values.get("premium"),
                    spot_close=values.get("spot_close"),
                    mark_price=values.get("mark_price"),
                    field_provenance=tuple((name, ob.provenance) for name, ob in sorted(fields.items())),
                )
                if values
                else None
            )
            history.append(
                MarketEvent(
                    record.spec, c.candle, c.provenance, now, symbol.quote if last else None, derivative
                )
            )
        event = history[-1]
        frames[symbol.symbol] = frame(history, now)
        if frames[symbol.symbol].empty:
            diagnostics[symbol.symbol] = ["CANDLES_INADMISSIBLE", *reasons]
            continue
        events[symbol.symbol] = event
        indices[symbol.symbol] = len(frames[symbol.symbol]) - 1
        if snapshot.exposure != "SYNTHETIC" or snapshot.fixture_id is None:
            reasons.append("REAL_SOURCE_ACTIVATION_REQUIRES_SEPARATE_ACCESS_AUTHORIZATION")
        if event.reason(config.platform.execution.source_max_age_ms):
            reasons.append("ANALYTICAL_SOURCE_INADMISSIBLE_OR_STALE")
        if event.derivatives is None or event.derivatives.field_reason(
            "funding_rate", now, config.admission.derivatives_max_age_ms
        ):
            if event.spec.market == "PERPETUAL" and config.platform.execution.funding == "required":
                reasons.append("FUNDING_MISSING_OR_STALE")
        if config.admission.require_open_interest_for_entry and (
            event.derivatives is None
            or event.derivatives.field_reason("open_interest", now, config.admission.derivatives_max_age_ms)
        ):
            reasons.append("OPEN_INTEREST_MISSING_OR_STALE")
        # A malformed candle response may hide a newer bar; never act on a silently truncated history.
        if any(issue.startswith("candles:") for issue in symbol.issues):
            reasons.append("CANDLE_RESPONSE_DEGRADED")
        admissions[symbol.symbol] = SourceAdmission(
            fingerprint(event), config.platform.hash, now, tuple(sorted(set(reasons)))
        )
        diagnostics[symbol.symbol] = sorted(set([*reasons, *symbol.issues]))
    if config.platform.benchmark not in frames:
        for symbol_id in admissions:
            prior = admissions[symbol_id]
            admissions[symbol_id] = SourceAdmission(
                prior.event_hash,
                prior.config_hash,
                now,
                tuple(sorted(set([*prior.reasons, "BENCHMARK_SOURCE_MISSING"]))),
            )
    elif events:
        benchmark_ts = events[config.platform.benchmark].candle.close_time_ms
        for symbol_id, event in events.items():
            if event.candle.close_time_ms != benchmark_ts:
                prior = admissions[symbol_id]
                admissions[symbol_id] = SourceAdmission(
                    prior.event_hash,
                    prior.config_hash,
                    now,
                    tuple(sorted(set([*prior.reasons, "BENCHMARK_BAR_MISMATCH"]))),
                )
    return AdmittedSnapshot(
        snapshot, FeaturePipeline(frames, config.platform.benchmark), events, indices, admissions, diagnostics
    )
