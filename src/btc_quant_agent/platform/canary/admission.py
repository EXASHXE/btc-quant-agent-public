"""Per-feed admission around existing bridge decoders; native and local clocks never alias."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..bridge.adapters import PublicPayloadAdapter, venue_symbol
from ..bridge.contracts import InstrumentRecord, Receipt
from ..core import ExecutableQuote, InstrumentSpec, fingerprint, primitive
from ..selection.sources import Bar, MINUTE, Observation, PRICE_FIELDS, UNITS
from .clocks import ClockEstimate, NativeClock, qualify_clock
from .control import CanaryStore
from .policy import Endpoint, Policy
from .transport import Frame


@dataclass(frozen=True)
class Binding:
    record: InstrumentRecord
    native_quantity_unit: str
    unit_evidence: str

    @property
    def spec(self) -> InstrumentSpec:
        return self.record.spec

    @property
    def hash(self):
        return fingerprint([self.spec, self.native_quantity_unit])


@dataclass(frozen=True)
class Decoded:
    feed: str
    symbol: str
    native_event_ms: int | None
    sequence: int | None
    quote: ExecutableQuote | None
    bars: tuple[Bar, ...]
    fields: tuple[Observation, ...]
    clock_report: dict
    reasons: tuple[str, ...]
    payload_sha256: str
    capture_id: str
    exposure: str = "SYNTHETIC"


def bind_instrument(frame: Frame, symbol: str, market="PERPETUAL") -> Binding:
    if frame.exposure != "SYNTHETIC" or frame.error or frame.status != 200:
        raise ValueError("FABRICATED_METADATA_REQUIRED")
    if frame.capture.reason():
        raise ValueError(frame.capture.reason())
    if (
        frame.provider != "binance"
        or frame.market != "USD_M"
        or frame.host != "https://fapi.binance.com"
        or frame.endpoint_id != "binance_usdm_exchange_info"
    ):
        raise ValueError("METADATA_PROVIDER_MARKET_HOST_UNQUALIFIED")
    payload = frame.payload
    native_symbol = venue_symbol(symbol, market, frame.provider)
    if frame.provider == "binance" and "symbols" in payload:
        matches = [x for x in payload["symbols"] if x.get("symbol") == native_symbol]
        if len(matches) != 1:
            raise ValueError("METADATA_SYMBOL_NOT_UNIQUE")
        payload = matches[0]
    receipt = Receipt.make(
        frame.provider,
        "instruments",
        native_symbol,
        frame.capture.complete_wall_ms,
        frame.capture.available_wall_ms,
        payload,
        exposure="SYNTHETIC",
    )
    record = PublicPayloadAdapter(frame.provider, market, 60).instrument(receipt, symbol)
    if not record.active:
        raise ValueError("INSTRUMENT_NOT_TRADING")
    unit = dict(frame.native_units).get("quantity")
    if unit not in {"BASE", "CONTRACTS"}:
        raise ValueError("INSTRUMENT_QUANTITY_UNITS_UNKNOWN")
    return Binding(record, unit, "FABRICATED_EXPLICIT_CONTRACT_UNIT_PROOF:" + frame.payload_sha256)


def _identity(frame: Frame, endpoint: Endpoint, binding: Binding, policy: Policy):
    if frame.exposure != "SYNTHETIC":
        raise ValueError("REAL_PAYLOAD_NOT_AUTHORIZED")
    if frame.endpoint_id not in policy.endpoint_ids:
        raise ValueError("ENDPOINT_NOT_IN_FROZEN_POLICY")
    if (
        frame.provider != endpoint.provider
        or frame.host != endpoint.host
        or frame.market != endpoint.market
        or binding.spec.provider != frame.provider
        or frame.symbol != binding.spec.symbol
        or frame.symbol not in policy.symbols
    ):
        raise ValueError("VENUE_MARKET_SYMBOL_IDENTITY_MISMATCH")
    if (
        not policy.synthetic_start_ms
        <= frame.capture.request_wall_ms
        <= frame.capture.commit_wall_ms
        < policy.end_ms
    ):
        raise ValueError("ACQUISITION_WINDOW_VIOLATION")
    if frame.capture.decision_wall_ms < binding.record.available_ts:
        raise ValueError("INSTRUMENT_METADATA_FROM_FUTURE")
    if frame.capture.decision_wall_ms - binding.record.available_ts > 3_600_000:
        raise ValueError("INSTRUMENT_METADATA_EXPIRED")
    if not binding.record.active or not binding.unit_evidence:
        raise ValueError("INSTRUMENT_OR_UNIT_EVIDENCE_UNKNOWN")
    if frame.capture.reason(policy.wall_drift_ms):
        raise ValueError(frame.capture.reason(policy.wall_drift_ms))


def decode(
    frame: Frame, endpoint: Endpoint, binding: Binding, policy: Policy, estimate: ClockEstimate | None
) -> Decoded:
    """Pure normalization. Replay does not depend on current sequence/recovery state."""
    _identity(frame, endpoint, binding, policy)
    payload = frame.payload
    if isinstance(payload, dict) and "data" in payload and endpoint.transport == "WS":
        payload = payload["data"]
    if isinstance(payload, dict):
        identity = payload.get("s", payload.get("symbol", payload.get("instId")))
        if identity is not None and identity != binding.record.venue_symbol:
            raise ValueError("NATIVE_SYMBOL_MISMATCH")
        if frame.market == "USD_M" and payload.get("st", 1) != 1:
            raise ValueError("COIN_M_STREAM_CANNOT_ALIAS_USD_M")
    units = dict(frame.native_units)
    quote = None
    bars: list[Bar] = []
    fields: list[Observation] = []
    reasons: list[str] = []
    sequence = payload.get("u") if isinstance(payload, dict) else None
    native_value = None
    if endpoint.timestamp_field and isinstance(payload, dict):
        native_value = payload.get(endpoint.timestamp_field)
    is_candle = "klines" in endpoint.id or "candles" in endpoint.id
    rows = payload
    seconds = 60
    if is_candle:
        if isinstance(payload, dict) and "k" in payload:
            k = payload["k"]
            if not k.get("x"):
                raise ValueError("CANDLE_NOT_COMPLETED")
            seconds = {"1m": 60, "5m": 300}.get(k["i"], 0)
            if not seconds:
                raise ValueError("INTERVAL_CHANGE_NOT_AUTHORIZED")
            rows = [[k["t"], k["o"], k["h"], k["l"], k["c"], k["v"], k["T"], k["q"], 0, 0, 0, 0]]
        elif isinstance(payload, dict):
            seconds = payload.get("interval_seconds", 60)
            rows = payload.get("rows")
        if seconds not in (60, 300) or not isinstance(rows, list) or not rows:
            raise ValueError("COMPLETED_CANDLE_ROWS_REQUIRED")
        if endpoint.timestamp_field == "[6]":
            native_value = rows[-1][6]
        sequence = rows[-1][0]
    if native_value is not None:
        if isinstance(native_value, str) and native_value.isdigit():
            native_value = int(native_value)
        if type(native_value) is not int:
            raise ValueError("NATIVE_TIMESTAMP_TYPE_INVALID")
    native = NativeClock(
        endpoint.timestamp_field,
        native_value,
        endpoint.timestamp_semantics,
        endpoint.documentation["reference_url"],
        payload.get("T") if isinstance(payload, dict) and endpoint.timestamp_field == "E" else None,
        payload.get("E") if isinstance(payload, dict) else None,
    )
    clock = qualify_clock(
        native,
        frame.capture,
        estimate,
        endpoint.freshness_ttl_ms,
        max_uncertainty_ms=policy.max_clock_uncertainty_ms,
    )
    if clock["reason"]:
        reasons.append(clock["reason"])
    adapter = PublicPayloadAdapter(frame.provider, binding.spec.market, seconds)
    if "bbo" in endpoint.id:
        if endpoint.id == "binance_usdm_bbo_ws":
            if payload.get("e") != "bookTicker" or payload.get("st") != 1:
                raise ValueError("USD_M_BOOKTICKER_SCHEMA_IDENTITY_REQUIRED")
            if type(sequence) is not int or sequence < 0 or type(payload.get("T")) is not int:
                raise ValueError("NATIVE_UPDATE_OR_TRANSACTION_TIME_MISSING")
            if native_value is not None and payload["T"] > native_value:
                raise ValueError("TRANSACTION_AFTER_EVENT_TIMESTAMP")
        if units.get("quantity") != binding.native_quantity_unit or units.get("price") != "USDT/BASE":
            raise ValueError("QUOTE_UNITS_MISMATCH")
        if binding.native_quantity_unit != "BASE" or binding.spec.multiplier != 1:
            reasons.append("NON_UNIT_LINEAR_CAPACITY_REQUIRES_ADDITIONAL_QUALIFICATION")
        if not reasons:
            if frame.provider == "binance" and endpoint.transport == "WS":
                canonical = {
                    "symbol": payload["s"],
                    "time": native_value,
                    "bidPrice": payload["b"],
                    "bidQty": payload["B"],
                    "askPrice": payload["a"],
                    "askQty": payload["A"],
                }
            else:
                canonical = payload
            receipt = Receipt.make(
                frame.provider,
                "quote",
                binding.record.venue_symbol,
                frame.capture.complete_wall_ms,
                frame.capture.available_wall_ms,
                canonical,
                exposure="SYNTHETIC",
            )
            quote = adapter.quote(receipt, binding.record)
            quote = replace(
                quote, provenance=replace(quote.provenance, source_id="L4:RAW_SHA256:" + frame.payload_sha256)
            )
            why = quote.reason(binding.spec, frame.capture.decision_wall_ms, endpoint.freshness_ttl_ms)
            if why:
                reasons.append(why)
                quote = None
    elif is_candle:
        if units.get("volume") != "BASE" or units.get("quote_volume") != "USDT":
            raise ValueError("CANDLE_UNITS_MISMATCH")
        receipt = Receipt.make(
            frame.provider,
            "candles",
            binding.record.venue_symbol,
            frame.capture.complete_wall_ms,
            frame.capture.available_wall_ms,
            rows,
            exposure="SYNTHETIC",
        )
        for record in adapter.candles(receipt, binding.record):
            c = record.candle
            if not c.closed or c.close_time_ms >= frame.capture.complete_wall_ms:
                raise ValueError("CANDLE_INCOMPLETE_OR_FUTURE")
            if c.open_time_ms < policy.synthetic_start_ms or c.close_time_ms >= policy.end_ms:
                raise ValueError("CANDLE_OUTSIDE_AUTHORIZED_FUTURE_ONLY_WINDOW")
            p = replace(record.provenance, source_id="L4:RAW_SHA256:" + frame.payload_sha256)
            obs = tuple(
                Observation(k, float(getattr(c, k)), c.symbol, seconds * 1000, UNITS[k], p, 2000)
                for k in PRICE_FIELDS
            )
            bars.append(Bar(binding.spec, c.open_time_ms, c.close_time_ms + 1, seconds * 1000, obs))
    elif any(key in endpoint.id for key in ("_oi", "premium", "funding", "turnover")):
        if not reasons:
            channel = (
                "open_interest"
                if endpoint.id.endswith("_oi")
                else "liquidity"
                if endpoint.id.endswith("turnover")
                else "funding"
            )
            receipt = Receipt.make(
                frame.provider,
                channel,
                binding.record.venue_symbol,
                frame.capture.complete_wall_ms,
                frame.capture.available_wall_ms,
                payload,
                exposure="SYNTHETIC",
            )
            if channel == "open_interest" and units.get("open_interest") != "BASE":
                raise ValueError("OI_BASE_UNIT_NOT_ESTABLISHED")
            for o in adapter.fields(receipt, binding.record):
                name = o.name
                unit = {"RATE_PER_SETTLEMENT": "RATE/SETTLEMENT", "USDT_PER_BASE": "QUOTE/BASE"}.get(
                    o.unit, o.unit
                )
                if name in UNITS:
                    fields.append(
                        Observation(name, o.value, binding.spec.symbol, MINUTE, unit, o.provenance, 120_000)
                    )
    return Decoded(
        endpoint.id,
        binding.spec.symbol,
        native_value,
        sequence,
        quote,
        tuple(bars),
        tuple(fields),
        clock,
        tuple(reasons),
        frame.payload_sha256,
        fingerprint(frame),
    )


def admit(
    frame: Frame,
    endpoint: Endpoint,
    binding: Binding,
    policy: Policy,
    estimate: ClockEstimate | None,
    store: CanaryStore,
) -> dict:
    try:
        if frame.error or frame.status != 200:
            raise ValueError(frame.error or "HTTP_" + str(frame.status))
        result = decode(frame, endpoint, binding, policy, estimate)
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        reason = str(exc)
        store.fault(endpoint.id, frame.symbol, reason)
        return {
            "status": "WATCH",
            "reasons": [reason],
            "quote": None,
            "bars": (),
            "fields": (),
            "native_source_qualified": False,
            "action_source_ready": False,
            "exposure": "SYNTHETIC",
        }
    source_key = endpoint.id + (":" + str(result.bars[0].interval_ms) if result.bars else "")
    store.commit_capture(primitive(result))
    for bar in result.bars:
        with store._connect() as db:
            last = db.execute(
                "SELECT MAX(end_ms) FROM canary_bars WHERE provider=? AND symbol=? AND interval_ms=?",
                (bar.spec.provider, bar.spec.symbol, bar.interval_ms),
            ).fetchone()[0]
        if last is not None and bar.start > last:
            store.mark_bar_gap(source_key, frame.symbol, bar.spec.provider, bar.interval_ms, last, bar.start)
        try:
            store.record_bar(bar)
        except ValueError as exc:
            store.fault(source_key, frame.symbol, str(exc))
            return {
                "status": "WATCH",
                "reasons": [str(exc)],
                "action_source_ready": False,
                "native_source_qualified": False,
                "quote": None,
                "bars": (),
                "fields": (),
            }
    if result.reasons or result.native_event_ms is None:
        store.fault(source_key, frame.symbol, "|".join(result.reasons))
        return {
            **primitive(result),
            "status": "WATCH",
            "action_source_ready": False,
            "native_source_qualified": False,
            "decoded": result,
        }
    state, sequence_reason = store.accept(
        source_key,
        frame.symbol,
        epoch=frame.epoch,
        sequence=result.sequence,
        native_ms=result.native_event_ms,
        payload_hash=result.payload_sha256,
        receive_ms=frame.capture.complete_wall_ms,
        instrument_hash=binding.hash,
        recovery_required=policy.recovery_distinct_updates,
    )
    return {
        **primitive(result),
        "status": state["status"],
        "source_state": state,
        "reasons": [sequence_reason] if sequence_reason else list(result.reasons),
        "action_source_ready": state["status"] == "OFFLINE_STABLE" and sequence_reason is None,
        "native_source_qualified": False,
        "decoded": result,
    }
