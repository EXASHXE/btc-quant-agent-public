"""Offline-only transport -> receipts -> bridge -> L23 features/selector, with no sender."""

from __future__ import annotations

import html
import json
from dataclasses import replace
from pathlib import Path

from ..core import primitive
from ..selection.fixtures import structural_bars
from ..selection.lifecycle import Monitor
from ..selection.selector import Policy as SelectorPolicy, scan
from ..selection.sources import FrozenUniverse, SourceHistory, STRUCTURE
from .admission import admit, bind_instrument, decode
from .clocks import ClockEstimate
from .control import BudgetGuard, CanaryStore, CircuitOpen
from .fixtures import bbo, candle_frame, clock_for, frame_from_record, metadata, raw_record
from .policy import budget_plan, grant_reasons
from .storage import ReceiptStorage, StorageBlocked
from .transport import NetworkDisabled, ScriptedTransport
from .warmup import assess, contract


def normalize_record(record, catalog, policy):
    """A replay record includes the metadata and clock estimate known at receipt time."""
    frame = frame_from_record(record["frame"])
    binding = bind_instrument(frame_from_record(record["instrument_frame"]), frame.symbol)
    estimate = ClockEstimate(**{**record["clock"], "rtt_ms": tuple(record["clock"]["rtt_ms"])})
    try:
        return primitive(decode(frame, catalog[frame.endpoint_id], binding, policy, estimate))
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        return {"exposure": "SYNTHETIC", "rejected": str(exc), "frame_sha256": frame.payload_sha256}


class OfflineSession:
    def __init__(self, root, policy, catalog, transport):
        if type(transport) is not ScriptedTransport:
            raise NetworkDisabled("PHASE_A_ONLY_EXACT_SCRIPTED_TRANSPORT")
        self.root, self.policy, self.catalog, self.transport = Path(root), policy, catalog, transport
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = CanaryStore(self.root / "canary.sqlite")
        self.guard = BudgetGuard(self.store, policy)
        self.storage = ReceiptStorage(self.root, self.store, policy.storage)
        self.storage.recover_orphans()
        if self.storage.audit()["errors"]:
            raise StorageBlocked("PRE_ADMISSION_INTEGRITY_FAILURE")

    def step(self, endpoint_id, symbol, now_ms, instrument_frame, *, retry=False, pending=0):
        try:
            return self._step(endpoint_id, symbol, now_ms, instrument_frame, retry=retry, pending=pending)
        except (CircuitOpen, StorageBlocked):
            self.transport.close()
            self.store.set_value("session_stop", {"reason": "CIRCUIT_OR_STORAGE_BLOCKED", "utc_ms": now_ms})
            raise

    def _step(self, endpoint_id, symbol, now_ms, instrument_frame, *, retry=False, pending=0):
        if now_ms >= self.policy.end_ms:
            self.finish(now_ms)
            raise NetworkDisabled("CANARY_UTC_END_REACHED")
        endpoint = self.catalog[endpoint_id]
        mono = now_ms - 1_700_000_000_000  # Declared synthetic epoch, not a measured market clock.
        if endpoint.transport == "REST":
            self.guard.request(endpoint, {"symbol": symbol, "limit": 99}, mono, retry=retry)
        else:
            if "public" not in self.store.get_value("connections", {}):
                self.guard.connection_open("public", endpoint, mono)
                self.guard.subscription_set(
                    "public", endpoint, tuple(s.lower() + "@bookTicker" for s in self.policy.symbols), mono
                )
            self.guard.data_message(mono, pending)
        frame = self.transport.receive(endpoint, symbol, now_ms)
        if frame.capture.request_wall_ms < now_ms or frame.capture.request_wall_ms >= self.policy.end_ms:
            raise ValueError("SCRIPTED_RECEIVE_CLOCK_BINDING_INVALID")
        estimate = clock_for(frame.capture)
        record = {
            "exposure": "SYNTHETIC",
            "frame": raw_record(frame),
            "instrument_frame": raw_record(instrument_frame),
            "clock": primitive(estimate),
        }
        start, end = frame.capture.request_wall_ms, frame.capture.commit_wall_ms
        raw_sha = self.storage.write("RAW", symbol, (record,), start, end)
        normalized = normalize_record(record, self.catalog, self.policy)
        self.storage.write("NORMALIZED", symbol, (normalized,), start, end, raw_sha=raw_sha)
        # Receipts are durable before any selector state or local outbox is touched.
        try:
            self.guard.response(
                408 if frame.error == "TIMEOUT" else frame.status,
                frame.capture.complete_mono_ms,
                venue_code=str(frame.payload.get("code")) if isinstance(frame.payload, dict) else None,
            )
        except CircuitOpen:
            self.store.fault(endpoint_id, symbol, "RATE_LIMIT_CIRCUIT_OPEN")
            self.transport.close()
            raise
        if frame.error == "DISCONNECT":
            self.store.reconnect(endpoint_id, symbol, frame.capture.complete_wall_ms)
        self.storage.reserve_admission_capacity(normalized)
        result = admit(
            frame, endpoint, bind_instrument(instrument_frame, symbol), self.policy, estimate, self.store
        )
        self.store.set_value(
            "last_receipt",
            {
                "raw_sha256": raw_sha,
                "endpoint": endpoint_id,
                "symbol": symbol,
                "received_ms": frame.capture.complete_wall_ms,
            },
        )
        return result

    def finish(self, now_ms):
        self.transport.close()
        for connection_id in self.store.get_value("connections", {}):
            self.guard.connection_close(connection_id)
        replay = self.storage.replay_crosscheck(lambda r: normalize_record(r, self.catalog, self.policy))
        result = {
            "status": "OFFLINE_READY_PENDING_AUTH",
            "stopped_utc_ms": now_ms,
            "transport_closed": self.transport.closed,
            "replay": replay,
            "source_transport_network_calls": 0,
            "source_qualified": False,
            "shadow_advisory_qualified": False,
            "economically_validated": False,
        }
        self.store.set_value("finalization", result)
        return result


def monitor_from_admitted(bar, previous_bar, quote_result, now, *, regime="UNKNOWN", beta=None, beta_ts=None):
    """No synthetic funding or quote substitutes. L23 enforces the remaining hard gates."""
    decoded = quote_result.get("decoded")
    quote = decoded.quote if decoded and quote_result.get("action_source_ready") else None
    return Monitor(
        bar,
        now,
        quote,
        "OFFLINE_EXECUTABLE_TOP_OF_BOOK",
        previous_bar=previous_bar,
        healthy=True,
        regime=regime,
        beta=beta,
        beta_available_ts=beta_ts,
    )


def preflight(policy, catalog, output):
    return {
        "status": "OFFLINE_READY_PENDING_AUTH",
        "grant_reasons": grant_reasons(None, policy, catalog, policy.synthetic_start_ms, Path(output)),
        "policy_hash": policy.hash,
        "budget": budget_plan(policy, catalog),
        "warmup": contract(),
        "source_transport_network_calls": 0,
        "background_task_created": False,
        "real_transport_implemented": False,
        "B_C_status": "BLOCKED_PENDING_OWNER_AUTH",
        "proposal_2026_11_01": "UNAPPROVED_NOT_SCHEDULED",
        "source_qualified": False,
        "shadow_advisory_qualified": False,
        "economically_validated": False,
    }


def demo(policy, catalog, output):
    """66 contiguous 5m bars per pilot symbol from fabricated native REST schemas."""
    root = Path(output)
    if root.exists() and any(root.iterdir()):
        raise ValueError("OUTPUT_EXISTS: choose an empty isolated output; receipts are immutable")
    candles = catalog["binance_usdm_klines_rest"]
    quote_endpoint = catalog["binance_usdm_bbo_ws"]
    meta_endpoint = catalog["binance_usdm_exchange_info"]
    # Reuse the existing L23 fabricated mechanisms, but decode every price from native-shaped receipts.
    bars = sorted(
        structural_bars(count=66, symbols=tuple(sorted(policy.symbols))), key=lambda b: (b.end, b.spec.symbol)
    )
    frames, meta_frames = [], []
    metadata_by_hour = {}
    for bar in bars:
        hour = (bar.end - policy.synthetic_start_ms) // 3_600_000
        key = (bar.spec.symbol, hour)
        if key not in metadata_by_hour:
            t = max(policy.synthetic_start_ms + 100, bar.start + 100)
            metadata_by_hour[key] = metadata(meta_endpoint, bar.spec.symbol, t)[0]
        mf = metadata_by_hour[key]
        f = candle_frame(candles, bind_instrument(mf, bar.spec.symbol), bar.start, interval=STRUCTURE)
        values, _ = bar.values(bar.end + 1000)
        body = f.payload
        row = body["rows"][0]
        row[1:6] = [str(values[k]) for k in ("open", "high", "low", "close", "volume")]
        row[7] = str(values["quote_volume"])
        frames.append(replace(f, payload_json=json.dumps(body, sort_keys=True)))
        meta_frames.append(mf)
    last = bars[-1].end
    for i in range(2):
        for symbol in policy.symbols:
            frames.append(bbo(quote_endpoint, symbol, last + 2000 + i * 1000, sequence=i + 1))
            meta_frames.append(metadata(meta_endpoint, symbol, last + 1000)[0])
    session = OfflineSession(root, policy, catalog, ScriptedTransport(tuple(frames), policy))
    decoded_bars, quotes = [], {}
    for f, mf in zip(frames, meta_frames):
        result = session.step(f.endpoint_id, f.symbol, f.capture.request_wall_ms, mf)
        if result.get("decoded"):
            decoded_bars.extend(result["decoded"].bars)
        if "bbo" in f.endpoint_id:
            quotes[f.symbol] = {
                "status": result["status"],
                "action_source_ready": result["action_source_ready"],
                "native_source_qualified": False,
            }
    selector_policy = SelectorPolicy.model_validate({"symbols": tuple(sorted(policy.symbols))})

    def history(cutoff):
        return SourceHistory(
            tuple(decoded_bars),
            FrozenUniverse(
                tuple(sorted(policy.symbols)), policy.benchmark, cutoff, decision_ts=cutoff + 1000
            ),
        )

    scan(history(last - STRUCTURE), session.store, selector_policy)
    h = history(last)
    selected = scan(h, session.store, selector_policy)
    report = {
        **preflight(policy, catalog, root),
        "exposure": "SYNTHETIC",
        "workflow": "scripted native REST/WS -> immutable receipts -> existing bridge -> L23 factors -> V1 selector",
        "decoded_completed_5m_bars": len(decoded_bars),
        "readiness": assess(h),
        "quotes": quotes,
        "selector": selected,
        "funding": "UNKNOWN native premiumIndex time / cadence; ACTION blocked",
        "local_external_sends": 0,
        "finalization": session.finish(policy.end_ms),
    }
    (root / "report.json").write_text(json.dumps(primitive(report), sort_keys=True, indent=2) + "\n")
    (root / "report.html").write_text(
        "<!doctype html><html lang='en'><meta charset='utf-8'>"
        "<title>L4 offline source canary</title><h1>Fabricated inputs only</h1>"
        "<p>OFFLINE_READY_PENDING_AUTH. No observed feed, execution or profitability validation.</p><pre>"
        + html.escape(json.dumps(primitive(report), sort_keys=True, indent=2))
        + "</pre></html>"
    )
    return report
