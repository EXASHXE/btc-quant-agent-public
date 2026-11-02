"""Field-bound point-in-time histories feeding the existing 69-factor pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

import pandas as pd

from ..core import DataProvenance, FactorResult, InstrumentSpec, Status, fingerprint, primitive
from ..factors import REGISTRY, FeaturePipeline

MINUTE = 60_000
STRUCTURE = 5 * MINUTE
PRICE_FIELDS = ("open", "high", "low", "close", "volume", "quote_volume")
OHLC_FIELDS = ("open", "high", "low", "close")
UNITS = {
    "open": "QUOTE/BASE",
    "high": "QUOTE/BASE",
    "low": "QUOTE/BASE",
    "close": "QUOTE/BASE",
    "volume": "BASE",
    "quote_volume": "QUOTE",
    "open_interest": "BASE",
    "funding_rate": "RATE/SETTLEMENT",
    "spot_close": "QUOTE/BASE",
    "taker_buy": "BASE",
    "taker_sell": "BASE",
    "cvd": "BASE",
    "basis": "RATIO",
    "premium": "RATIO",
    "spread": "BPS",
    "orderbook_imbalance": "RATIO",
    "mark_price": "QUOTE/BASE",
    "funding_interval_ms": "MS",
    "next_funding_ts": "UTC_MS",
    "aggressive_delta": "BASE",
    "bid": "QUOTE/BASE",
    "ask": "QUOTE/BASE",
    "bid_depth": "BASE",
    "ask_depth": "BASE",
}


@dataclass(frozen=True)
class Observation:
    field: str
    value: float
    symbol: str
    interval_ms: int
    unit: str
    provenance: DataProvenance
    max_age_ms: int
    complete: bool = True
    dependencies: tuple[Observation, ...] = ()

    def reason(self, spec: InstrumentSpec, now: int, interval: int) -> str | None:
        if self.provenance.exposure != "SYNTHETIC":
            from ..canary.public_data import admitted_public

            if not admitted_public(self.provenance):
                return "BLOCKED_PENDING_OWNER_AUTH"
        if self.symbol != spec.symbol:
            return "FIELD_SYMBOL_MISMATCH"
        if self.provenance.provider != spec.provider:
            return "FIELD_PROVIDER_MISMATCH"
        if self.interval_ms != interval:
            return "FIELD_INTERVAL_MISMATCH"
        if self.unit != UNITS.get(self.field):
            return "FIELD_UNITS_UNKNOWN_OR_MISMATCH"
        if not self.complete:
            return "OBSERVATION_INCOMPLETE"
        if not isfinite(self.value):
            return "FIELD_NONFINITE"
        cap = 2000 if self.field in PRICE_FIELDS else 120_000
        if self.max_age_ms <= 0:
            return "FIELD_FRESHNESS_POLICY_INVALID"
        return self.provenance.reason(now, min(self.max_age_ms, cap))


@dataclass(frozen=True)
class Bar:
    """Half-open UTC interval [start, end); each value retains its own receipt."""

    spec: InstrumentSpec
    start: int
    end: int
    interval_ms: int
    fields: tuple[Observation, ...]
    closed: bool = True

    @property
    def id(self) -> str:
        return fingerprint([self.spec.provider, self.spec.symbol, self.interval_ms, self.start, self.end])

    def values(self, now: int) -> tuple[dict[str, float], dict[str, str]]:
        values: dict[str, float] = {}
        errors: dict[str, str] = {}
        from ..canary.clock_domain import NativeProvenance, bar_decision, native_before

        native_p = next(
            (o.provenance for o in self.fields if isinstance(o.provenance, NativeProvenance)), None
        )
        native = native_p is not None
        if native and not all(isinstance(o.provenance, NativeProvenance) for o in self.fields):
            return {}, {"bar": "MIXED_CLOCK_DOMAINS"}
        if native:
            try:
                now = bar_decision(self, now)
            except (ValueError, KeyError, TypeError) as exc:
                return {}, {"bar": str(exc)}
        complete = native_before(native_p, self.end, now) if native_p else self.end <= now
        if not self.closed or not complete or self.end - self.start != self.interval_ms:
            return {}, {"bar": "BAR_INCOMPLETE_OR_INTERVAL_INVALID"}
        if len({x.field for x in self.fields}) != len(self.fields):
            return {}, {"bar": "DUPLICATE_FIELD"}
        for obs in self.fields:
            reason = obs.reason(self.spec, now, self.interval_ms)
            if obs.field in PRICE_FIELDS and obs.provenance.exchange_event_ts not in (self.end - 1, self.end):
                reason = "BAR_EVENT_CLOCK_MISMATCH"
            if reason:
                errors[obs.field] = reason
            else:
                values[obs.field] = obs.value
        if all(k in values for k in OHLC_FIELDS):
            if not (
                0
                < values["low"]
                <= min(values["open"], values["close"])
                <= max(values["open"], values["close"])
                <= values["high"]
            ) or any(values[k] < 0 for k in ("volume", "quote_volume") if k in values):
                return {}, {"bar": "INVALID_OHLCV"}
        return values, errors


@dataclass(frozen=True)
class FrozenUniverse:
    members: tuple[str, ...]
    benchmark: str
    cutoff: int
    interval_ms: int = STRUCTURE
    minimum_rank_members: int = 10
    decision_ts: int | None = None

    def __post_init__(self):
        if tuple(sorted(set(self.members))) != self.members or self.benchmark not in self.members:
            raise ValueError("UNIVERSE_MUST_BE_SORTED_UNIQUE_AND_INCLUDE_BENCHMARK")

    @property
    def hash(self) -> str:
        return fingerprint(self)


class SourceHistory:
    """Immutable histories plus field-level lineage, never price-stamped derivative values."""

    def __init__(self, bars: tuple[Bar, ...], universe: FrozenUniverse):
        self.bars, self.universe = bars, universe
        exposures = {o.provenance.exposure for b in bars for o in b.fields}
        if "PUBLIC_CANARY" in exposures and len(exposures) != 1:
            raise ValueError("MIXED_SYNTHETIC_NATIVE_HISTORY_FORBIDDEN")
        self.exposure = next(iter(exposures)) if len(exposures) == 1 else "UNKNOWN"
        self.traces: dict[tuple[str, int, str], Observation] = {}
        self.errors: dict[tuple[str, int], dict[str, str]] = {}
        self.frames: dict[str, pd.DataFrame] = {}
        for symbol in universe.members:
            rows: list[dict[str, Any]] = []
            selected = sorted(
                (
                    b
                    for b in bars
                    if b.spec.symbol == symbol
                    and b.end <= universe.cutoff
                    and b.interval_ms == universe.interval_ms
                ),
                key=lambda b: b.end,
            )
            if len({b.end for b in selected}) != len(selected):
                raise ValueError("DUPLICATE_BAR_IDENTITY")
            expected_provider = selected[0].spec.provider if selected else None
            for bar in selected:
                # Admission at the original row availability, not a fresh final candle's clock.
                row_time = min(
                    universe.decision_ts if universe.decision_ts is not None else universe.cutoff,
                    bar.end + 1000,
                )
                vals, errors = bar.values(row_time)
                if bar.spec.provider != expected_provider:
                    vals, errors = {}, {"bar": "HISTORY_PROVIDER_CHANGED"}
                self.errors[(symbol, bar.end)] = errors
                if not all(k in vals for k in OHLC_FIELDS):
                    continue
                row: dict[str, Any] = {"ts": bar.end, "available_ts": 0, **vals}
                for obs in bar.fields:
                    if obs.field not in vals:
                        continue
                    self.traces[(symbol, bar.end, obs.field)] = obs
                    row[obs.field + "__available_ts"] = obs.provenance.available_ts
                    if obs.field in OHLC_FIELDS:
                        row["available_ts"] = max(row["available_ts"], obs.provenance.available_ts)
                rows.append(row)
            self.frames[symbol] = pd.DataFrame(
                rows, columns=None if rows else ["ts", "available_ts", *PRICE_FIELDS]
            )
        self.pipeline = QualifiedPipeline(self)

    def synchronized(self) -> bool:
        return all(
            not df.empty and int(df.ts.iloc[-1]) == self.universe.cutoff for df in self.frames.values()
        )

    def lineage(self, symbol: str, field: str) -> list[dict]:
        return [primitive(v) for (s, _, f), v in sorted(self.traces.items()) if s == symbol and f == field]


class QualifiedPipeline(FeaturePipeline):
    def __init__(self, history: SourceHistory):
        self.history = history
        super().__init__(history.frames, history.universe.benchmark)

    def series(self, symbol, id, params=None):
        if id.upper() in {"RELATIVE_STRENGTH", "BETA", "CORRELATION", "MOMENTUM_RANK", "MARKET_RISK"}:
            if not self.history.synchronized() or (
                id.upper() == "MOMENTUM_RANK"
                and len(self.history.universe.members) < self.history.universe.minimum_rank_members
            ):
                return pd.Series(float("nan"), index=self.frames[symbol].index)
        return super().series(symbol, id, params)

    def result(self, symbol, id, index, decision_ts, params=None) -> FactorResult:
        id = id.upper()
        h, u = self.history, self.history.universe
        if id in ("RELATIVE_STRENGTH", "BETA", "CORRELATION", "MOMENTUM_RANK", "MARKET_RISK"):
            if not h.synchronized():
                return FactorResult(id, None, Status.INADMISSIBLE, None, "FROZEN_UNIVERSE_MISALIGNED")
        if id == "MOMENTUM_RANK" and len(u.members) < u.minimum_rank_members:
            return FactorResult(id, None, Status.MISSING, None, "RANK_COVERAGE_BELOW_MINIMUM")
        df = self.frames[symbol]
        if 0 <= index < len(df):
            ts = int(df.ts.iloc[index])
            if index and (df.ts.iloc[: index + 1].diff().dropna() != u.interval_ms).any():
                return FactorResult(id, None, Status.INADMISSIBLE, None, "HISTORY_GAP_OR_INTERVAL_CHANGE")
            for field in REGISTRY[id].required_fields:
                if field in {"benchmark", "cross_section"}:
                    continue
                obs = h.traces.get((symbol, ts, field))
                if obs is None:
                    return FactorResult(id, None, Status.MISSING, None, "MISSING_ADMISSIBLE_FIELD:" + field)
                reason = obs.reason(
                    next(b.spec for b in h.bars if b.spec.symbol == symbol),
                    self._field_decision(obs, min(decision_ts, ts + 1000)),
                    u.interval_ms,
                )
                if reason:
                    return FactorResult(id, None, Status.INADMISSIBLE, obs.provenance.available_ts, reason)
        from ..canary.clock_domain import current_decision, NativeProvenance

        if h.traces and any(isinstance(o.provenance, NativeProvenance) for o in h.traces.values()):
            context = current_decision()
            if context is None:
                return FactorResult(id, None, Status.INADMISSIBLE, None, "CLOCK_DECISION_EVIDENCE_MISSING")
            decision_ts = context[0]["wall_ms"]
        return super().result(symbol, id, index, decision_ts, params)

    @staticmethod
    def _field_decision(obs, cutoff):
        from ..canary.clock_domain import NativeProvenance, historical_decision

        if isinstance(obs.provenance, NativeProvenance):
            # A failure remains an inadmissible factor, never a fallback raw clock.
            try:
                return historical_decision(obs.provenance, cutoff)
            except ValueError:
                return -1
        return cutoff


def aggregate_five_minutes(bars: tuple[Bar, ...], decision_ts: int) -> tuple[Bar, ...]:
    """Only five contiguous completed 1m bars; no interval relabeling or invented receipts."""
    from ..canary.clock_domain import NativeProvenance

    if any(isinstance(o.provenance, NativeProvenance) for b in bars for o in b.fields):
        # The legacy composer creates a synthetic receipt. It cannot relabel
        # native evidence: use separately admitted native 5m bars instead.
        raise ValueError("NATIVE_AGGREGATION_PROOF_COMPOSITION_UNSUPPORTED_USE_NATIVE_5M")
    groups: dict[tuple[str, str, int], list[Bar]] = {}
    for bar in bars:
        if bar.interval_ms != MINUTE:
            continue
        groups.setdefault((bar.spec.provider, bar.spec.symbol, bar.start // STRUCTURE), []).append(bar)
    result = []
    for (_, _, bucket), members in sorted(groups.items()):
        members.sort(key=lambda b: b.start)
        start = bucket * STRUCTURE
        if len(members) != 5 or [b.start for b in members] != [start + n * MINUTE for n in range(5)]:
            continue
        vals = [b.values(min(decision_ts, b.end + 1000))[0] for b in members]
        if not all(all(k in v for k in PRICE_FIELDS) for v in vals):
            continue
        values = {
            "open": vals[0]["open"],
            "high": max(v["high"] for v in vals),
            "low": min(v["low"] for v in vals),
            "close": vals[-1]["close"],
            "volume": sum(v["volume"] for v in vals),
            "quote_volume": sum(v["quote_volume"] for v in vals),
        }
        fields = []
        for field, value in values.items():
            deps = [next(o for o in b.fields if o.field == field) for b in members]
            # Preserve all leaf receipts via source_id, with max causal dependency clocks.
            p = DataProvenance(
                members[0].spec.provider,
                fingerprint([o.provenance for o in deps]),
                members[-1].end,
                max(o.provenance.received_ts for o in deps),
                max(o.provenance.available_ts for o in deps),
            )
            fields.append(
                Observation(
                    field,
                    value,
                    members[0].spec.symbol,
                    STRUCTURE,
                    UNITS[field],
                    p,
                    2000,
                    dependencies=tuple(deps),
                )
            )
        result.append(Bar(members[0].spec, start, start + STRUCTURE, STRUCTURE, tuple(fields)))
    return tuple(result)


def from_bridge_snapshot(snapshot, *, field_bindings: dict[str, tuple[str, int]]) -> tuple[Bar, ...]:
    """Reuse normalized public-adapter records with an explicit receipt->symbol/interval binding.

    The old FieldObservation contract has no symbol/interval. A caller must supply its
    receipt binding; enclosing it in a symbol object is insufficient evidence by itself.
    Real-source activation remains blocked, including user-supplied forward payloads.
    """
    if snapshot.exposure != "SYNTHETIC":
        raise ValueError("BLOCKED_PENDING_OWNER_AUTH")
    bars = []
    for item in snapshot.symbols:
        if item.instrument is None or not item.instrument.active:
            continue
        spec = item.instrument.spec
        for record in item.candles:
            c, p = record.candle, record.provenance
            interval = {"1m": MINUTE, "60s": MINUTE, "5m": STRUCTURE, "300s": STRUCTURE}.get(c.interval)
            if interval is None:
                continue
            end = c.close_time_ms + 1
            fields = [
                Observation(k, float(getattr(c, k)), c.symbol, interval, UNITS[k], p, 2000)
                for k in PRICE_FIELDS
            ]
            latest: dict[str, Any] = {}
            for o in item.observations:
                if o.provenance.available_ts <= min(snapshot.decision_ts, end + 1000):
                    old = latest.get(o.name)
                    if old is None or old.provenance.exchange_event_ts < o.provenance.exchange_event_ts:
                        latest[o.name] = o
            for o in latest.values():
                binding = field_bindings.get(o.provenance.source_id)
                if binding is None or o.provenance.available_ts > snapshot.decision_ts:
                    continue
                unit = {"RATE_PER_SETTLEMENT": "RATE/SETTLEMENT", "USDT_PER_BASE": "QUOTE/BASE"}.get(
                    o.unit, o.unit
                )
                fields.append(
                    Observation(o.name, o.value, binding[0], binding[1], unit, o.provenance, 120_000)
                )
            bars.append(Bar(spec, c.open_time_ms, end, interval, tuple(fields), c.closed))
    return tuple(bars)
