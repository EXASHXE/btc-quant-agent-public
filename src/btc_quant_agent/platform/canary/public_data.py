"""Causal native normalization using the existing bridge; no synthetic relabeling."""

from __future__ import annotations

from dataclasses import replace
from math import isfinite

from ..bridge.adapters import PublicPayloadAdapter
from ..bridge.contracts import Receipt
from ..core import DataProvenance, ExecutableQuote, InstrumentSpec, dec, fingerprint, primitive
from ..selection.sources import Bar, Observation, PRICE_FIELDS, UNITS
from .clocks import ClockEstimate
from .public_io import Wire
from .public_policy import START, END, SYMBOLS, IDS
from . import clock_domain as domain


def admitted_public(p):
    # This is lineage validation, not a network authorization mechanism. Only the
    # grant-bound runtime may mark input admitted after source/clock/identity checks.
    pieces = p.source_id.split(":")
    return (
        p.exposure == "PUBLIC_CANARY"
        and p.admissible
        and isinstance(p, domain.NativeProvenance)
        and p.clock_evidence is not None
        and len(pieces) == 3
        and pieces[0] == "L4_PUBLIC"
        and all(len(x) == 64 and all(c in "0123456789abcdef" for c in x) for x in pieces[1:])
    )


def instrument(payload, symbol, wire):
    matches = [x for x in payload.get("symbols", []) if x.get("symbol") == symbol]
    if len(matches) != 1:
        raise ValueError("INSTRUMENT_SYMBOL_NOT_UNIQUE")
    body = matches[0]
    if body.get("contractType") != "PERPETUAL" or body.get("marginAsset") != "USDT":
        raise ValueError("CONTRACT_TYPE_CHANGED")
    # Native exchangeInfo does not establish funding cadence or account margin tiers.
    body = {k: v for k, v in body.items() if k != "fundingIntervalHours"}
    r = Receipt.make(
        "binance", "instruments", symbol, wire.receive_wall, wire.available_wall, body, exposure=wire.exposure
    )
    result = PublicPayloadAdapter("binance", "PERPETUAL", 60).instrument(r, symbol)
    if not result.active:
        raise ValueError("INSTRUMENT_NOT_TRADING")
    return result


def clock_report(w, native, semantics, estimate, now, now_mono, ttl, record=None):
    if record and record.get("clock_contract_version") == domain.VERSION:
        samples = w.clock_samples or {}
        report = domain.qualify(
            estimate,
            native,
            samples.get("receive"),
            record.get("normalization_sample", samples.get("available")),
            record.get("decision_sample"),
            record["scope_hash"],
            w.exposure,
            ttl,
            semantics,
        )
        report["local"] = {
            "message_complete_to_available_ms": w.available_mono - w.receive_mono,
            "available_to_decision_ms": now_mono - w.available_mono,
            "request_to_complete_ms": w.receive_mono - w.request_mono if w.request_mono is not None else None,
            "request_to_first_ms": w.first_mono - w.request_mono
            if w.first_mono is not None and w.request_mono is not None
            else None,
            "measurement": "measured_local_elapsed",
        }
        report["clock_epoch_id"] = (samples.get("receive") or {}).get("epoch_id")
        report["first_receive_wall_ms"] = w.first_wall
        report["ws_first_byte_note"] = "UNKNOWN; library exposes complete message only" if w.stream else None
        return report
    reason = None
    bounds = None
    age = None
    if native is None or type(native) is not int or native <= 0 or semantics == "UNKNOWN":
        reason = "NATIVE_TIMESTAMP_OR_SEMANTICS_UNKNOWN"
    elif not w.receive_wall <= w.available_wall <= now or not w.receive_mono <= w.available_mono <= now_mono:
        reason = "LOCAL_CLOCK_ORDER_INVALID"
    elif estimate is None:
        reason = "CLOCK_UNCERTAINTY_UNKNOWN"
    else:
        e = ClockEstimate(**{**estimate, "rtt_ms": tuple(estimate["rtt_ms"])})
        if (
            e.exposure != w.exposure
            or not e.rtt_ms
            or not all(isfinite(x) for x in (e.offset_low_ms, e.offset_high_ms))
            or e.offset_high_ms < e.offset_low_ms
            or e.available_wall_ms > now
            or e.available_mono_ms > now_mono
            or not 0 <= now_mono - e.available_mono_ms <= e.max_probe_age_ms
        ):
            reason = "CLOCK_ESTIMATE_INVALID_STALE_OR_FUTURE"
        elif e.uncertainty_ms > 100:
            reason = "CLOCK_UNCERTAINTY_EXCEEDS_LEASE"
        else:
            bounds = e.interval(native, w.receive_wall)
            age = e.interval(native, now)
            if min(bounds) < 0 or min(age) < 0:
                reason = "SOURCE_TIME_POTENTIALLY_FUTURE"
            elif max(age) > ttl:
                reason = "SOURCE_AGE_UPPER_BOUND_EXCEEDED"
            elif native > w.receive_wall:
                reason = "L23_NATIVE_CLOCK_ORDER_UNSUPPORTED"
    elapsed = {
        "message_complete_to_available_ms": w.available_mono - w.receive_mono,
        "available_to_decision_ms": now_mono - w.available_mono,
        "measurement": "measured_local_elapsed",
    }
    if w.stream is None:
        elapsed["request_to_complete_ms"] = w.receive_mono - w.request_mono
        elapsed["request_to_first_ms"] = w.first_mono - w.request_mono if w.first_mono is not None else None
    return {
        "native_event_or_snapshot_ms": native,
        "semantics": semantics,
        "event_to_receive_estimate_bounds_ms": bounds,
        "event_age_estimate_bounds_ms": age,
        "local": elapsed,
        "first_receive_wall_ms": w.first_wall,
        "ws_first_byte_note": "UNKNOWN; library exposes complete message only" if w.stream else None,
        "one_way_latency_proven": False,
        "source_clock_qualified": reason is None,
        "reason": reason,
    }


def normalize(record):
    if record.get("clock_contract_version") == domain.VERSION and record.get("decision_sample"):
        with domain.decision_clock(record["decision_sample"], record["scope_hash"]):
            return _normalize(record)
    return _normalize(record)


def _normalize(record):
    w = Wire(**record["wire"])
    w = replace(
        w,
        available_wall=max(w.available_wall, record.get("normalization_available_wall_ms", w.available_wall)),
        available_mono=max(w.available_mono, record.get("normalization_available_mono_ms", w.available_mono)),
    )
    payload = None
    now, mono = record["decision_wall_ms"], record["decision_mono_ms"]
    result = {
        "exposure": w.exposure,
        "received_wall_ms": w.receive_wall,
        "symbol": w.symbol,
        "endpoint_id": w.endpoint_id,
        "wire_id": fingerprint(record["wire"]),
        "decision_wall_ms": now,
        "status": "MISSING",
        "reasons": [],
        "bars": [],
        "quote": None,
        "fields": [],
    }
    try:
        start, end = record.get("scope_window_ms", (START, END))
        long_duration = record.get("source_contract_version") == "L4_LONGHORIZON_V1"
        if "flex_window_contract" in record:
            from .clock_eligibility import validate_flex_window

            validate_flex_window(record)
        elif (type(start) is not int or type(end) is not int
            or not (0 < end - start <= 48 * 3600000 if long_duration else START <= start < end <= END)):
            raise ValueError("SOURCE_GRANTED_WINDOW_INVALID")
        v2 = record.get("clock_contract_version") == domain.VERSION
        if w.clock_samples is not None or v2:
            if not v2:
                raise ValueError("CLOCK_CONTRACT_VERSION_MISSING")
            samples = w.clock_samples or {}
            receive, original_available = samples.get("receive", {}), samples.get("available", {})
            available = record.get("normalization_sample", original_available)
            decision = record.get("decision_sample")
            if reason := domain.same_epoch([receive, original_available, available, decision]):
                raise ValueError(reason)
            if (
                receive["wall_ms"] != w.receive_wall
                or receive["mono_after_ms"] != w.receive_mono
                or original_available["wall_ms"] != record["wire"]["available_wall"]
                or original_available["mono_after_ms"] != record["wire"]["available_mono"]
                or available["wall_ms"] != w.available_wall
                or available["mono_after_ms"] != w.available_mono
                or decision["wall_ms"] != now
                or decision["mono_after_ms"] != mono
                or receive["mono_after_ms"] > original_available["mono_before_ms"]
                or original_available["mono_after_ms"] > available["mono_before_ms"]
                or available["mono_after_ms"] > decision["mono_before_ms"]
            ):
                raise ValueError("CLOCK_SAMPLE_WIRE_BINDING_MISMATCH")
        if not start <= w.receive_wall < end:
            raise ValueError("SOURCE_RECEIVE_OUTSIDE_GRANTED_WINDOW")
        if w.error or w.status != 200:
            raise ValueError(w.error or "HTTP_" + str(w.status))
        if w.endpoint_id not in IDS and w.endpoint_id != "source_failure":
            raise ValueError("ENDPOINT_FORBIDDEN")
        payload = w.payload
        if w.endpoint_id == "binance_usdm_exchange_info":
            result["instruments"] = {s: primitive(instrument(payload, s, w)) for s in SYMBOLS}
            result["status"] = "METADATA_OBSERVED"
            return result
        if w.endpoint_id == "binance_usdm_server_time":
            if type(payload.get("serverTime")) is not int:
                raise ValueError("SERVER_TIME_MISSING")
            result["status"] = "SERVER_CLOCK_SAMPLE"
            result["serverTime"] = payload["serverTime"]
            return result
        if w.endpoint_id == "binance_usdm_funding_info":
            if not isinstance(payload, list):
                raise ValueError("FUNDING_INFO_SCHEMA")
            result["cadence_hours"] = {
                d["symbol"]: int(d["fundingIntervalHours"])
                for d in payload
                if d.get("symbol") in SYMBOLS
                and type(d.get("fundingIntervalHours")) is int
                and d["fundingIntervalHours"] > 0
            }
            result["status"] = "CONTEXT_ONLY"
            result["reasons"] = [
                "STATIC_METADATA_HAS_NO_INVENTED_NATIVE_EVENT_CLOCK",
                "ABSENCE_DOES_NOT_ESTABLISH_8H_CADENCE",
            ]
            return result
        if w.endpoint_id == "source_failure":
            raise ValueError(w.error or "SOURCE_OUTAGE")
        if w.symbol not in SYMBOLS:
            raise ValueError("SYMBOL_SCOPE_VIOLATION")
        metadata = record.get("metadata")
        if not metadata:
            raise ValueError("INSTRUMENT_METADATA_MISSING")
        mw = Wire(**metadata["wire"])
        if mw.exposure != w.exposure:
            raise ValueError("MIXED_NATIVE_SYNTHETIC_METADATA")
        mw = replace(
            mw,
            available_wall=metadata.get("normalization_available_wall_ms", mw.available_wall),
            available_mono=metadata.get("normalization_available_mono_ms", mw.available_mono),
        )
        spec = instrument(mw.payload, w.symbol, mw).spec
        if v2:
            metadata_samples = mw.clock_samples or {}
            if reason := domain.same_epoch([metadata_samples.get("receive"), receive]):
                raise ValueError(reason)
            metadata_age = mono - mw.available_mono
        else:
            metadata_age = now - mw.available_wall
        if not 0 <= metadata_age <= 3600000:
            raise ValueError("INSTRUMENT_METADATA_EXPIRED_OR_FUTURE")
        data = payload.get("data") if w.stream else payload
        if isinstance(data, dict):
            if data.get("s", data.get("symbol", w.symbol)) != w.symbol:
                raise ValueError("WRONG_SYMBOL_NATIVE_PAYLOAD")
            if data.get("st", 1) != 1:
                raise ValueError("COIN_M_CANNOT_ALIAS_USD_M")
        result["instrument_spec"] = primitive(spec)
        receipt_id = "L4_PUBLIC:" + record["scope_hash"] + ":" + result["wire_id"]
        ep = w.endpoint_id
        native = data.get("E", data.get("time", data.get("closeTime"))) if isinstance(data, dict) else None
        semantics = (
            "EVENT_TIME"
            if w.stream
            else "TRANSACTION_TIME"
            if ep.endswith("_oi")
            else "UNKNOWN"
            if ep.endswith("_premium")
            else "ROLLING_WINDOW_CLOSE"
            if ep.endswith("_turnover")
            else "CANDLE_CLOSE"
        )
        is_bar = "klines" in ep
        rows = []
        seconds = 60
        if is_bar:
            if w.stream:
                k = data["k"]
                if data.get("e") != "kline" or k.get("s", w.symbol) != w.symbol:
                    raise ValueError("KLINE_IDENTITY_MISMATCH")
                if not k.get("x"):
                    result.update(status="INCOMPLETE_BAR_IGNORED", reasons=["CANDLE_NOT_COMPLETED"])
                    return result
                seconds = {"1m": 60, "5m": 300}.get(k["i"], 0)
                if not seconds:
                    raise ValueError("INTERVAL_CHANGE_NOT_AUTHORIZED")
                rows = [
                    [
                        k["t"],
                        k["o"],
                        k["h"],
                        k["l"],
                        k["c"],
                        k["v"],
                        k["T"],
                        k["q"],
                        k.get("n", 0),
                        k.get("V", 0),
                        k.get("Q", 0),
                        0,
                    ]
                ]
            else:
                seconds = {"1m": 60, "5m": 300}.get(str(w.params.get("interval")), 0)
                rows = data
                if not seconds or not isinstance(rows, list) or not rows:
                    raise ValueError("KLINE_ROWS_MISSING")
                native = rows[-1][6]
        ttl = 5000 if "bbo" in ep else 2000 if is_bar else 120000
        if long_duration and ep == "binance_usdm_klines_rest":
            p = w.params
            size = seconds * 1000
            if (not 1 <= len(rows) <= p.get("limit", 0) <= 99
                or not start <= p["startTime"] <= p["endTime"] < end
                or p["startTime"] % size or (p["endTime"] + 1) % size
                or p["endTime"] - p["startTime"] + 1 > 99 * size
                or any(not p["startTime"] <= r[0] < r[6] <= p["endTime"]
                       or r[0] % size or r[6] + 1 != r[0] + size for r in rows)
                or any(b[0] - a[0] != size for a, b in zip(rows, rows[1:]))):
                raise ValueError("BOUNDED_REPAIR_ROWS_OUTSIDE_REQUEST")
            # Old completed bars are archival facts available at this receipt.
            # This allowance never applies to quotes or ordinary WS observations.
            ttl = 100 * size + 5000
        report = clock_report(w, native, semantics, record.get("clock"), now, mono, ttl, record)
        result["clock"] = report
        if report["reason"]:
            result["reasons"].append(report["reason"])
        admitted = report["source_clock_qualified"]
        adapter = PublicPayloadAdapter("binance", "PERPETUAL", seconds)

        def provenance(p):
            if v2:
                if isinstance(p, domain.NativeProvenance):
                    return p
                field_native = p.exchange_event_ts
                field_semantics = "CANDLE_CLOSE" if is_bar else semantics
                qualified = clock_report(
                    w, field_native, field_semantics, record.get("clock"), now, mono, ttl, record
                )
                return domain.provenance(
                    p,
                    record=record,
                    native=field_native,
                    semantics=field_semantics,
                    admitted=admitted and qualified["source_clock_qualified"],
                    source_window=(start, end),
                )
            return replace(p, source_id=receipt_id, admissible=admitted)

        def native_provenance(event):
            if type(event) is not int or event <= 0:
                raise ValueError("EXCHANGE_EVENT_TIME_UNKNOWN")
            base = DataProvenance(
                "binance", receipt_id, event, w.receive_wall, w.available_wall, w.exposure, False
            )
            return provenance(base)

        if "bbo" in ep:
            if (
                data.get("e") != "bookTicker"
                or data.get("st") != 1
                or type(data.get("u")) is not int
                or type(data.get("T")) is not int
            ):
                raise ValueError("BOOKTICKER_NATIVE_SCHEMA_CHANGED")
            if native is None or data["T"] > native:
                raise ValueError("TRANSACTION_AFTER_EVENT")
            r = Receipt.make(
                "binance",
                "quote",
                w.symbol,
                w.receive_wall,
                w.available_wall,
                {
                    "symbol": w.symbol,
                    "time": native,
                    "bidPrice": data["b"],
                    "bidQty": data["B"],
                    "askPrice": data["a"],
                    "askQty": data["A"],
                },
                exposure=w.exposure,
            )
            q = adapter.quote(
                r,
                type("Binding", (), {"spec": spec, "venue_symbol": w.symbol})(),
                provenance_factory=native_provenance if v2 else None,
            )
            q = replace(q, provenance=provenance(q.provenance))
            reason = q.reason(spec, now, 5000)
            if reason:
                result["reasons"].append(reason)
            result["native_sizes"] = {
                "bid": str(dec(data["B"])),
                "ask": str(dec(data["A"])),
                "unit": "NATIVE_LINEAR_QUANTITY; ACTION unit entitlement unverified",
            }
            result["native_transaction_ms"] = data["T"]
            result["sequence"] = data["u"]
            if not result["reasons"]:
                # Quote prices are admitted. Size/margin/funding qualifications are independent hard gates.
                if w.exposure == "PUBLIC_CANARY":
                    q = replace(q, bid_quantity=None, ask_quantity=None)
                result["quote"] = primitive(q)
        elif is_bar:
            if v2 and not admitted:
                raise ValueError(report["reason"])
            r = Receipt.make(
                "binance", "candles", w.symbol, w.receive_wall, w.available_wall, rows, exposure=w.exposure
            )
            # The explicit cutoff is in the native domain and used only after the
            # clock envelope proves completion. Original receiver walls stay raw.
            cutoff = max(row[6] for row in rows) + 1 if v2 else None
            for c in adapter.candles(
                r,
                type("Binding", (), {"spec": spec, "venue_symbol": w.symbol})(),
                completion_cutoff_ms=cutoff,
                provenance_factory=native_provenance if v2 else None,
            ):
                bar = c.candle
                field_provenance = provenance(c.provenance)
                completion_valid = (
                    (
                        field_provenance.reason(now, ttl) is None
                        and domain.native_bounds(field_provenance, bar.close_time_ms + 1)[1]
                        <= receive["mono_before_ms"]
                    )
                    if v2
                    else bar.close_time_ms < w.receive_wall
                )
                if (
                    not start <= bar.open_time_ms < bar.close_time_ms < end
                    or not completion_valid
                    or bar.open_time_ms % (seconds * 1000)
                ):
                    raise ValueError("BAR_WINDOW_BOUNDARY_OR_COMPLETION_INVALID")
                if not all(isfinite(float(getattr(bar, f))) for f in PRICE_FIELDS):
                    raise ValueError("NATIVE_FIELD_NONFINITE")
                unit_ok = (bar.volume == 0 and bar.quote_volume == 0) or (
                    bar.volume > 0
                    and bar.low - float(spec.tick_size)
                    <= bar.quote_volume / bar.volume
                    <= bar.high + float(spec.tick_size)
                )
                result["volume_unit_qualification"] = (
                    "LINEAR_PRICE_VOLUME_RECONCILED" if unit_ok else "UNVERIFIED"
                )
                if not unit_ok:
                    result["reasons"].append("OPTIONAL_VOLUME_UNIT_RECONCILIATION_FAILED")
                obs = tuple(
                    Observation(
                        f,
                        float(getattr(bar, f)),
                        w.symbol,
                        seconds * 1000,
                        UNITS[f],
                        field_provenance,
                        2000,
                    )
                    for f in PRICE_FIELDS
                    if unit_ok or f in ("open", "high", "low", "close")
                )
                result["bars"].append(
                    primitive(Bar(spec, bar.open_time_ms, bar.close_time_ms + 1, seconds * 1000, obs))
                )
        else:
            result["context_values"] = data
            if ep.endswith("_oi"):
                dec(data["openInterest"])
                result["reasons"].append("NATIVE_OI_UNIT_NOT_PROMOTED_TO_BASE_WITHOUT_QUALIFICATION")
            if ep.endswith("_premium"):
                result["reasons"].append("FUNDING_CLOCK_AND_CADENCE_NOT_COMPLETE_FOR_ACTION")
        result["status"] = "ADMITTED_OBSERVATION" if not result["reasons"] else "WATCH_CONTEXT_ONLY"
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        result["status"] = "INADMISSIBLE"
        result["reasons"].append(str(exc))
        result["quote"] = None
        result["bars"] = []
    return result


def bar_from_record(value):
    v = dict(value)
    v["spec"] = InstrumentSpec(**v["spec"])
    v["fields"] = tuple(
        Observation(**{**o, "provenance": domain.from_record(o["provenance"]), "dependencies": ()})
        for o in v["fields"]
    )
    return Bar(**v)


def quote_from_record(value):
    return (
        ExecutableQuote(**{**value, "provenance": domain.from_record(value["provenance"])}) if value else None
    )
