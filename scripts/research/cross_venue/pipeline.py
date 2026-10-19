"""Manual Controller feature bridge; no scheduler, outcomes, Alpha or fills.

    python3 -m scripts.research.cross_venue.pipeline demo --output-dir /tmp/new
    python3 -m scripts.research.cross_venue.pipeline inspect-historical \
        --binance-q3 /root/workspace/project/crypto-data/historical/binance-usdm-expansion \
        --okx-q3 /root/workspace/project/crypto-data/historical/okx-swap-expansion \
        --output-dir /tmp/another-new

Optional --binance-q2/--okx-q2 require a stable pair of manifest/QC snapshots.
Stdout is exactly one status line. Exit 0 = DEV_READY, 1 = partial historical
coverage, 2 = blocked; diagnostics.json carries the exact cause. Historical
receiver PIT always remains UNKNOWN and every scheduled origin is NO_ACTION.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import math
import os
import sys
import zipfile
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import LABELS, REPORT_SHA256, TASK, US
from . import normalized_sources as ns

READY = "CROSS_VENUE_DEV_READY"
PARTIAL = "PARTIAL_SOURCE_COVERAGE"
BLOCKED = "BLOCKED_EXACT_CAUSE"
EXIT_CODES = {READY: 0, PARTIAL: 1, BLOCKED: 2}
OUTPUT_FILES = ("source_inventory.json", "lineage_manifest.json", "origins.jsonl",
                "coverage.json", "diagnostics.json")
CHANNELS = {
    "binance_perp": ("binance", "klines"),
    "binance_spot": ("binance", "spot_klines"),
    "okx_swap": ("okx", "candlesticks"),
    "okx_spot": ("okx", "spot_candlesticks"),
    "binance_mark": ("binance", "markPriceKlines"),
}
PRIMARY_CHANNELS = tuple(CHANNELS)[:4]
FEATURE_INPUTS = {
    "lagged_venue_perp_log_price_spread": ("binance_perp", "okx_swap"),
    "lagged_venue_spot_log_price_spread": ("binance_spot", "okx_spot"),
    "binance_spot_perp_log_basis": ("binance_perp", "binance_spot"),
    "okx_spot_perp_log_basis": ("okx_swap", "okx_spot"),
    "binance_mark_last_log_spread": ("binance_mark", "binance_perp"),
}
FUNDING_MAX_AGE_US = 12 * 3600 * US  # Freshness policy, never an inferred settlement interval.


def select_z(stocks: dict[int, ns.Stock], times: list[int], cutoff: int, asset: str) -> dict[str, Any]:
    """Binance stock state at C-10m..C-5m and its exact four-hour predecessor."""
    c = cutoff * US
    result = {"status": "UNAVAILABLE", "reason": "MISSING_Z", "z": None,
              "z_t": None, "z_4h_exact": False, "raw_z_present": False,
              "sample": None, "predecessor": None}
    i = bisect.bisect_right(times, c - 300 * US) - 1
    if i < 0:
        if times:
            result["reason"] = "Z_FUTURE_OR_TOO_RECENT"
        return result
    sample = stocks[times[i]]
    result.update(raw_z_present=True, z_t=sample.t_us // US, sample=sample.as_dict())
    if not c - 600 * US <= sample.t_us <= c - 300 * US:
        result["reason"] = "Z_STALE"
        return result
    if (sample.asset != asset or sample.venue != "binance" or sample.market != "futures_um"
            or sample.interval_s != 300 or sample.t_us % (300 * US)):
        result["reason"] = "Z_FAMILY_OR_INTERVAL_MISMATCH"
        return result
    predecessor = stocks.get(sample.t_us - 14400 * US)
    if predecessor is None:
        result["reason"] = "Z_4H_PREDECESSOR_MISSING"
        return result
    result["predecessor"] = predecessor.as_dict()
    if (predecessor.t_us != sample.t_us - 14400 * US or predecessor.asset != asset
            or predecessor.venue != sample.venue or predecessor.market != sample.market
            or predecessor.interval_s != 300):
        result["reason"] = "Z_4H_PREDECESSOR_INVALID"
        return result
    if not all(ns.finite(v) and v > 0 for v in
               (sample.base_oi, predecessor.base_oi, sample.top_position_ls)):
        result["reason"] = "Z_INVALID_STOCK"
        return result
    z = [math.log(sample.base_oi) - math.log(predecessor.base_oi), math.log(sample.top_position_ls)]
    result.update(status="OBSERVED", reason="READY", z=z, z_4h_exact=True)
    return result


def settled_funding(events: list[ns.Funding], times: list[int], cutoff: int,
                    asset: str, venue: str) -> dict[str, Any]:
    c = cutoff * US
    # Strictly before C, including millisecond event times. A row settled at C
    # or later cannot become a known input merely because it is in this file.
    i = bisect.bisect_left(times, c) - 1
    result = {"status": "UNAVAILABLE", "reason": "FUNDING_MISSING", "sample": None,
              "age_us": None, "receiver_pit": "PIT_UNKNOWN"}
    if i < 0:
        if events:
            result["reason"] = "FUNDING_FUTURE_OR_AT_CUTOFF"
        return result
    sample = events[i]
    if sample.asset != asset or sample.venue != venue:
        result["reason"] = "FUNDING_FAMILY_MISMATCH"
        return result
    age = c - sample.t_us
    if not 0 < age <= FUNDING_MAX_AGE_US:
        result.update(reason="FUNDING_STALE", age_us=age)
        return result
    if not ns.finite(sample.rate):
        result["reason"] = "FUNDING_INVALID_RATE"
        return result
    result.update(status="OBSERVED_SETTLED", reason="READY", sample=sample.as_dict(), age_us=age)
    return result


def origin(asset: str, quarter: str, cutoff: int, latest: dict[str, ns.Bar],
           stocks: dict[int, ns.Stock], stock_times: list[int],
           funding: dict[str, list[ns.Funding]], funding_times: dict[str, list[int]]) -> dict[str, Any]:
    bars, usable = {}, {}
    reasons = []
    for name, (venue, family) in CHANNELS.items():
        bar = latest.get(name)
        reason = "MISSING_BAR" if bar is None else "READY"
        if bar is not None:
            if (bar.asset != asset or bar.venue != venue or bar.family != family
                    or bar.market != ("spot" if "spot" in name else "swap" if venue == "okx" else "futures_um")
                    or bar.symbol != (f"{asset}USDT" if venue == "binance" else f"{asset}-USDT" + ("" if "spot" in name else "-SWAP"))):
                reason = "BAR_FAMILY_MISMATCH"
            elif bar.open_us != (cutoff - 60) * US:
                reason = "BAR_FUTURE" if bar.open_us > (cutoff - 60) * US else "BAR_STALE_OR_GAP"
            elif not bar.open_us < bar.end_us < cutoff * US:
                reason = "BAR_NOT_STRICTLY_CLOSED"
            elif not ns.finite(bar.closing) or bar.closing <= 0:
                reason = "INVALID_BAR_PRICE"
        bars[name] = {"status": "OBSERVED_CLOSED" if reason == "READY" else "UNAVAILABLE",
                      "reason": reason, "sample": bar.as_dict() if bar is not None else None}
        if reason == "READY":
            usable[name] = bar
        else:
            reasons.append(f"{name}:{reason}")
    features, feature_reasons = {}, {}
    for name, (a, b) in FEATURE_INPUTS.items():
        features[name] = (math.log(usable[a].closing) - math.log(usable[b].closing)
                          if a in usable and b in usable else None)
        if features[name] is None:
            feature_reasons[name] = "MISSING_STALE_OR_INVALID_CLOSED_BAR"
    a, b = features["binance_spot_perp_log_basis"], features["okx_spot_perp_log_basis"]
    features["lagged_venue_basis_spread"] = a - b if a is not None and b is not None else None
    if features["lagged_venue_basis_spread"] is None:
        feature_reasons["lagged_venue_basis_spread"] = "MISSING_SPOT_PERP_PAIR"
    features["okx_mark_last_log_spread"] = None
    feature_reasons["okx_mark_last_log_spread"] = "OKX_MARK_SOURCE_NOT_AVAILABLE"
    z = select_z(stocks, stock_times, cutoff, asset)
    settled = {venue: settled_funding(funding.get(venue, []), funding_times.get(venue, []), cutoff, asset, venue)
               for venue in ("binance", "okx")}
    if z["status"] != "OBSERVED":
        reasons.append(z["reason"])
    reasons.extend(f"{v}:{value['reason']}" for v, value in settled.items() if value["reason"] != "READY")
    native_ready = (len(usable) == len(CHANNELS) and z["status"] == "OBSERVED"
                    and all(v["status"] == "OBSERVED_SETTLED" for v in settled.values()))
    return {"quarter": quarter, "asset": asset, "t": cutoff + 60,
            "decision_utc": ns.iso_us((cutoff + 60) * US), "cutoff_utc_s": cutoff,
            "bars": bars, "features": features, "feature_reasons": feature_reasons,
            "binance_z": z, "okx_z": {"status": "UNKNOWN", "z": None,
                                        "reason": "OKX_HISTORICAL_OI_POSITION_UNKNOWN"},
            "settled_funding": settled, "native_feature_ready": native_ready,
            "receiver_pit": "PIT_UNKNOWN", "action": "NO_ACTION",
            "no_action_reasons": sorted(set(reasons + ["PIT_UNKNOWN", "SOURCE_NOT_ADMITTED",
                "COST_UNVALIDATED_REAL_FILL", "NO_ALPHA_ESTABLISHED", "OKX_HISTORICAL_OI_POSITION_UNKNOWN"])),
            "labels": list(LABELS)}


def build_asset_grid(asset: str, quarter: str, streams: dict[str, Iterable[ns.Bar]],
                     stocks: dict[int, ns.Stock], funding: dict[str, list[ns.Funding]],
                     start: int, end: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ns.require(type(start) is int and type(end) is int and start % 3600 == end % 3600 == 0
               and 0 < end - start <= 92 * 86400, "INVALID_HOURLY_GRID")
    ns.require(all(type(t) is int and t == s.t_us for t, s in stocks.items()), "STOCK_INDEX_MISMATCH")
    iterators = {name: iter(streams.get(name, ())) for name in CHANNELS}
    heads = {name: next(stream, None) for name, stream in iterators.items()}
    previous: dict[str, int] = {}
    latest: dict[str, ns.Bar] = {}
    rows = []
    stock_times = sorted(stocks)
    funding_times = {}
    for venue, events in funding.items():
        times = [s.t_us for s in events]
        ns.require(times == sorted(set(times)), "DUPLICATE_OR_UNSORTED_FUNDING_CALENDAR")
        funding_times[venue] = times
    cutoff = start
    aligned = 0
    first = last = None
    segments = []
    segment_start = None
    while any(b is not None for b in heads.values()):
        t = min(b.open_us for b in heads.values() if b is not None)
        while cutoff < end and cutoff * US <= t:
            rows.append(origin(asset, quarter, cutoff, latest, stocks, stock_times, funding, funding_times))
            cutoff += 3600
        group = {name: b for name, b in heads.items() if b is not None and b.open_us == t}
        if all(name in group for name in PRIMARY_CHANNELS) and start * US <= t < end * US:
            aligned += 1
            if first is None:
                first = t
            if last is None or t != last + 60 * US:
                if last is not None:
                    segments.append([segment_start, last + 60 * US])
                segment_start = t
            last = t
        for name, bar in group.items():
            ns.require(name not in previous or t > previous[name], "DUPLICATE_OR_BACKWARD_STREAM_BAR", channel=name)
            previous[name] = t
            latest[name] = bar
            heads[name] = next(iterators[name], None)
    if last is not None:
        segments.append([segment_start, last + 60 * US])
    while cutoff < end:
        rows.append(origin(asset, quarter, cutoff, latest, stocks, stock_times, funding, funding_times))
        cutoff += 3600
    ns.require(len(rows) == (end - start) // 3600
               and all(row["t"] == start + i * 3600 + 60 for i, row in enumerate(rows)), "HOURLY_DENOMINATOR_CHANGED")
    return rows, {"quarter": quarter, "asset": asset, "aligned_minutes_scanned": aligned,
                  "first_aligned_event_utc_us": first, "last_aligned_event_utc_us": last,
                  "observed_segments_utc_us_half_open": segments,
                  "hourly_scheduled_origins": len(rows), "no_action_origins": len(rows),
                  "native_feature_ready_origins": sum(r["native_feature_ready"] for r in rows)}


def _source_asset(source: ns.Source) -> str:
    symbol = source.record["symbol"]
    return "ALL" if symbol == "ALL_SWAPS" else "BTC" if symbol.startswith("BTC") else "ETH" if symbol.startswith("ETH") else "OTHER"


def _bar_stream(sources: list[ns.Source], venue: str, family: str, asset: str,
                quarter: str, budget: ns.Budget) -> Iterator[ns.Bar]:
    selected = [s for s in sources if s.selected and s.snapshot.venue == venue
                and s.snapshot.quarter == quarter and s.record["family"] == family and _source_asset(s) == asset]
    for source in sorted(selected, key=lambda s: s.record["start_utc"]):
        yield from ns.source_bars(source, budget)


def _merge_intervals(intervals: list[list[int]]) -> list[list[int]]:
    result: list[list[int]] = []
    for left, right in sorted(intervals):
        if result and left <= result[-1][1]:
            result[-1][1] = max(result[-1][1], right)
        else:
            result.append([left, right])
    return result


def metadata_intersection(sources: list[ns.Source], quarter: str, asset: str) -> dict[str, Any]:
    start, end = ns.quarter_window(quarter)
    common = [[start * US, end * US]]
    channel_ranges = {}
    for name in PRIMARY_CHANNELS:
        venue, family = CHANNELS[name]
        relevant = [s for s in sources if s.snapshot.quarter == quarter and s.snapshot.venue == venue
                    and _source_asset(s) == asset and s.record["family"] == family and s.record.get("verdict") == "PASS"]
        ranges = _merge_intervals([[ns.utc_us(s.record["start_utc"]), ns.utc_us(s.record["end_utc"]) + 60 * US]
                                  for s in relevant])
        channel_ranges[name] = {"ranges_utc_us_half_open": ranges,
                                "metadata_rows": sum(s.record["rows"] for s in relevant),
                                "metadata_gap_count": sum(s.record["gaps"] for s in relevant)}
        common = _merge_intervals([[max(a, c), min(b, d)] for a, b in common for c, d in ranges
                                   if max(a, c) < min(b, d)])
    return {"candidate_ranges_utc_us_half_open": common,
            "candidate_aligned_minutes": sum((b - a) // (60 * US) for a, b in common),
            "evidence": "METADATA_BOUNDS_REQUIRE_STREAM_CONFIRMATION", "channels": channel_ranges}


@dataclass
class Inspection:
    mode: str
    budget: ns.Budget = field(default_factory=ns.Budget)
    snapshots: list[ns.Snapshot] = field(default_factory=list)
    sources: list[ns.Source] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    intersections: list[dict[str, Any]] = field(default_factory=list)
    calendars: list[dict[str, Any]] = field(default_factory=list)
    synthetic_sources: list[dict[str, Any]] = field(default_factory=list)
    error: ns.BridgeError | None = None

    @property
    def status(self) -> str:
        if self.error is not None:
            return BLOCKED
        if self.mode == "demo":
            return READY
        quarters = {snapshot.quarter for snapshot in self.snapshots}
        if (self.mode != "inspect-historical" or not {("Q3", "binance"), ("Q3", "okx")}
                <= {(snapshot.quarter, snapshot.venue) for snapshot in self.snapshots}
                or not all(snapshot.unchanged for snapshot in self.snapshots)
                or len(self.intersections) != 2 * len(quarters)
                or len(self.rows) != sum(item["hourly_scheduled_origins"] for item in self.intersections)
                or not all(row["action"] == "NO_ACTION" for row in self.rows)):
            return PARTIAL
        if any(source.record.get("verdict") != "PASS"
               or source.scan.get("status") == "SKIPPED_SCAN_BUDGET"
               or (source.selected and source.scan.get("status") != "FULL_STREAM_SCAN")
               or (source.record.get("family") in ns.BAR_FAMILIES
                   and source.record.get("gaps") != 0)
               for source in self.sources):
            return PARTIAL
        if any(item.get("proof") != "FULL_STREAM_SCAN_AGREES_WITH_METADATA"
               or item.get("aligned_minutes_scanned", 0) <= 0
               or item.get("native_feature_ready_origins", 0) <= 0
               for item in self.intersections):
            return PARTIAL
        return READY


def inspect_historical(roots: dict[tuple[str, str], Path], budget: ns.Budget | None = None) -> Inspection:
    state = Inspection("inspect-historical", budget or ns.Budget())
    try:
        ns.require(all(("Q3", v) in roots for v in ("binance", "okx")), "Q3_ROOT_PAIR_REQUIRED")
        ns.require(all(k in ns.ROOT_NAMES for k in roots), "UNSUPPORTED_ROOT_IDENTITY")
        ns.require((("Q2", "binance") in roots) == (("Q2", "okx") in roots), "Q2_ROOT_PAIR_REQUIRED")
        for (quarter, venue), root in sorted(roots.items()):
            snapshot = ns.Snapshot.capture(root, venue, quarter)
            state.snapshots.append(snapshot)
            state.sources.extend(ns.expansion_sources(snapshot, state.budget))
        ns.require(len({s.root for s in state.snapshots}) == len(state.snapshots), "ROOT_ALIAS_OR_DUPLICATE")
        for snapshot in state.snapshots:
            snapshot.verify()
        stocks: dict[tuple[str, str], dict[int, ns.Stock]] = {}
        funding: dict[tuple[str, str, str], list[ns.Funding]] = {}
        for source in state.sources:
            if not source.selected:
                continue
            quarter, family = source.snapshot.quarter, source.record["family"]
            if family == "metrics":
                target = stocks.setdefault((quarter, _source_asset(source)), {})
                for stock in ns.source_stocks(source, state.budget):
                    ns.require(stock.t_us not in target, "DUPLICATE_STOCK_TIMESTAMP")
                    target[stock.t_us] = stock
            elif family in ("fundingRate", "funding_rates"):
                for event in ns.source_funding(source, state.budget):
                    funding.setdefault((quarter, event.asset, event.venue), []).append(event)
        for key, events in sorted(funding.items()):
            events.sort(key=lambda event: event.t_us)
            ns.require(len({e.t_us for e in events}) == len(events), "DUPLICATE_FUNDING_SETTLEMENT")
            state.calendars.append({"quarter": key[0], "asset": key[1], "venue": key[2],
                                    "scope": "EX_POST_SETTLEMENT_INVENTORY_NOT_PRIOR_PUBLICATION",
                                    "settlements": [e.as_dict() for e in events]})
        for quarter in sorted({q for q, _ in roots}):
            start, end = ns.quarter_window(quarter)
            for asset in ("BTC", "ETH"):
                streams = {name: _bar_stream(state.sources, venue, family, asset, quarter, state.budget)
                           for name, (venue, family) in CHANNELS.items()}
                events = {v: funding.get((quarter, asset, v), []) for v in ("binance", "okx")}
                rows, observed = build_asset_grid(asset, quarter, streams, stocks.get((quarter, asset), {}), events, start, end)
                state.rows.extend(rows)
                metadata = metadata_intersection(state.sources, quarter, asset)
                primary = [s for s in state.sources if s.snapshot.quarter == quarter and _source_asset(s) == asset
                           and (s.snapshot.venue, s.record["family"]) in [CHANNELS[n] for n in PRIMARY_CHANNELS]]
                complete = (bool(primary) and all(s.scan["status"] == "FULL_STREAM_SCAN" for s in primary)
                            and observed["observed_segments_utc_us_half_open"] == metadata["candidate_ranges_utc_us_half_open"]
                            and observed["aligned_minutes_scanned"] == metadata["candidate_aligned_minutes"]
                            and len(metadata["candidate_ranges_utc_us_half_open"]) == 1)
                observed.update(metadata=metadata, proof="FULL_STREAM_SCAN_AGREES_WITH_METADATA" if complete
                                else "INCOMPLETE_NO_FULL_COVERAGE_CLAIM",
                                missing_trailing_utc_minutes=(end * US - observed["last_aligned_event_utc_us"] - 60 * US) // (60 * US)
                                if observed["last_aligned_event_utc_us"] is not None else None)
                state.intersections.append(observed)
    except (ns.BridgeError, OSError, ValueError, KeyError, TypeError, csv.Error, zipfile.BadZipFile, UnicodeError) as exc:
        state.error = exc if isinstance(exc, ns.BridgeError) else ns.BridgeError("SOURCE_PARSE_OR_IO_ERROR", error_type=type(exc).__name__)
    finally:
        # The after hashes cover the entire feature scan, including failure paths.
        for snapshot in state.snapshots:
            try:
                snapshot.verify()
            except ns.BridgeError as exc:
                state.error = exc
        if state.error is not None:
            state.rows.clear()
            state.calendars.clear()
            state.intersections.clear()
    return state


def _synthetic_provenance(asset: str, venue: str, family: str, market: str,
                          t_us: int, native: int | str, unit: str, close: int | None = None) -> dict[str, Any]:
    symbol = f"{asset}USDT" if venue == "binance" else f"{asset}-USDT" + ("" if market == "spot" else "-SWAP")
    source_id = f"SYNTHETIC/{venue}/{family}/{symbol}"
    return {"source_id": source_id, "raw_source_sha256": None,
            "synthetic_identity_sha256": hashlib.sha256(source_id.encode("ascii")).hexdigest(),
            "venue": venue, "family": family, "market": market, "contract": symbol,
            "native_sample": native, "native_close": close, "native_time_unit": unit,
            "event_utc_us": t_us, "event_utc": ns.iso_us(t_us),
            "file_calendar_label": "SYNTHETIC", "file_calendar_timezone": "UTC+08:00" if venue == "okx" else "UTC",
            "receiver_pit": "PIT_UNKNOWN", "evidence": "SYNTHETIC_NO_RAW_ARCHIVE"}


def demo() -> Inspection:
    state = Inspection("demo")
    start, end = 1704067200, 1704067200 + 8 * 3600
    for asset in ("BTC", "ETH"):
        level = 40000 if asset == "BTC" else 2000
        def bars(name: str, asset: str = asset, level: int = level) -> Iterator[ns.Bar]:
            venue, family = CHANNELS[name]
            market = "spot" if "spot" in name else "swap" if venue == "okx" else "futures_um"
            for i, t in enumerate(range(start, end, 60)):
                price = level * (1 + 0.000001 * i + (list(CHANNELS).index(name) + 1) * 0.0001)
                unit = "us" if family == "spot_klines" else "ms"
                factor = 1 if unit == "us" else 1000
                native = t * US // factor
                close = None if venue == "okx" else native + 60 * US // factor - 1
                provenance = _synthetic_provenance(asset, venue, family, market, t * US, native, unit, close)
                yield ns.Bar(asset, venue, market, family, provenance["contract"], t * US,
                             t * US + 60 * US - (1 if venue == "okx" or unit == "us" else 1000),
                             price, price * 1.0001, price * 0.9999, price, 10.0, price * 10, provenance)
        stocks = {}
        for i, t in enumerate(range(start, end, 300)):
            native = ns.iso_us(t * US)[:19].replace("T", " ")
            stocks[t * US] = ns.Stock(asset, t * US, 10000.0 + i, 1.2 + i * 0.0001,
                _synthetic_provenance(asset, "binance", "metrics", "futures_um", t * US, native, "UTC_TEXT_SECONDS"))
        funding = {v: [ns.Funding(asset, v, (start - 3600) * US, 0.0001,
                    _synthetic_provenance(asset, v, "fundingRate" if v == "binance" else "funding_rates",
                    "futures_um" if v == "binance" else "swap", (start - 3600) * US,
                    (start - 3600) * 1000, "ms"))] for v in ("binance", "okx")}
        rows, observed = build_asset_grid(asset, "DEMO", {name: bars(name) for name in CHANNELS}, stocks, funding, start, end)
        state.rows.extend(rows)
        observed["proof"] = "SYNTHETIC_ONLY"
        state.intersections.append(observed)
        samples = ([cell["sample"] for cell in rows[-1]["bars"].values()]
                   + [next(iter(stocks.values())).provenance]
                   + [events[0].provenance for events in funding.values()])
        for sample in samples:
            state.synthetic_sources.append({"source_id": sample["source_id"], "raw_source_sha256": None,
                "synthetic_identity_sha256": sample["synthetic_identity_sha256"], "evidence": "SYNTHETIC_NO_RAW_ARCHIVE"})
        state.calendars.extend({"quarter": "DEMO", "asset": asset, "venue": v,
                                "scope": "SYNTHETIC_SETTLEMENT_ONLY", "settlements": [e.as_dict() for e in events]}
                               for v, events in funding.items())
    return state


def coverage_groups(state: Inspection) -> list[dict[str, Any]]:
    groups = []
    requested = {(s.quarter, s.venue) for s in state.snapshots}
    for quarter in ("Q2", "Q3"):
        for asset in ("BTC", "ETH"):
            for venue in ("binance", "okx"):
                relevant = [s for s in state.sources if s.snapshot.quarter == quarter and s.snapshot.venue == venue
                            and _source_asset(s) in (asset, "ALL")]
                blockers = []
                if (quarter, venue) not in requested:
                    blockers.append("QUARTER_ROOT_NOT_REQUESTED_NO_COVERAGE_CLAIM")
                else:
                    expected = ({"klines", "spot_klines", "markPriceKlines", "metrics", "fundingRate"} if venue == "binance"
                                else {"candlesticks", "spot_candlesticks", "funding_rates"})
                    for family in sorted(expected):
                        family_sources = [s for s in relevant if s.record["family"] == family]
                        if not family_sources:
                            blockers.append(f"MISSING_FAMILY:{family}")
                        if any(s.scan["status"] == "SKIPPED_SCAN_BUDGET" for s in family_sources):
                            blockers.append(f"SKIPPED_SCAN_BUDGET:{family}")
                        if any(s.record.get("verdict") != "PASS" for s in family_sources):
                            blockers.append(f"NON_PASS_SOURCE:{family}")
                        if family in ns.BAR_FAMILIES and any(s.record.get("gaps", 0) for s in family_sources):
                            blockers.append(f"BAR_GAPS:{family}")
                    if venue == "okx":
                        blockers.extend(("OKX_HISTORICAL_OI_POSITION_UNKNOWN", "OKX_MARK_SOURCE_NOT_AVAILABLE"))
                        l2 = [s for s in relevant if s.record["family"] == "orderbook"]
                        if quarter == "Q2" and asset == "BTC" and (not l2 or any(s.record.get("verdict") != "PASS" for s in l2)):
                            blockers.append("APRIL_01_BTC_400_LEVEL_L2_MISSING")
                        if l2:
                            blockers.append("L2_NOT_SCANNED_NO_FULL_DAY_OR_FILL_CLAIM")
                    rows = [r for r in state.rows if r["quarter"] == quarter and r["asset"] == asset]
                    if rows and any(not r["native_feature_ready"] for r in rows):
                        blockers.append("MISSING_STALE_OR_WARMUP_ORIGINS_RETAINED")
                groups.append({"quarter": quarter, "asset": asset, "venue": venue,
                               "requested": (quarter, venue) in requested,
                               "record_counts": ns.inventory_counts(relevant), "source_feature_blockers": sorted(set(blockers)),
                               "admission_blockers": ["SOURCE_NOT_ADMITTED", "PIT_UNKNOWN", "COST_UNVALIDATED_REAL_FILL"],
                               "complete_source_pass_claim": False})
    return groups


def reports(state: Inspection) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    inventory = {"task": TASK, "mode": state.mode, "schema": "cross_venue.sources.v1", "labels": list(LABELS),
                 "snapshots": [s.receipt() for s in state.snapshots],
                 "root_counts": [{"quarter": s.quarter, "venue": s.venue,
                                   **ns.inventory_counts([x for x in state.sources if x.snapshot is s])} for s in state.snapshots],
                 "sources": [s.inventory() for s in state.sources] + state.synthetic_sources}
    coverage = {"task": TASK, "labels": list(LABELS), "groups": coverage_groups(state),
                "intersections": state.intersections,
                "hourly_denominators": dict(sorted(Counter(f"{r['quarter']}/{r['asset']}" for r in state.rows).items())),
                "denominator_policy": "EVERY_UTC_HOUR_OF_REQUESTED_QUARTER_PER_ASSET_INCLUDING_WARMUP_AND_MISSING_TAIL",
                "q2_constraint": "Q2_OKX_BTC_APRIL_01_400_LEVEL_L2_MUST_NOT_BE_ASSUMED_PASS",
                "full_source_admission": False}
    diagnostics = {"task": TASK, "mode": state.mode, "status": state.status, "labels": list(LABELS),
                   "exact_cause": state.error.code if state.error else None,
                   "cause_details": state.error.details if state.error else {},
                   "counts": {"origins": len(state.rows), "no_action": sum(r["action"] == "NO_ACTION" for r in state.rows),
                              "native_feature_ready": sum(r["native_feature_ready"] for r in state.rows),
                              "outcomes_evaluated": 0, "alpha_tests": 0, "market_requests": 0,
                              "l2_archives_opened": 0, "real_funds_writes": 0},
                   "budget": state.budget.receipt(), "scan_scope": {
                       "families": sorted(ns.FEATURE_FAMILIES), "bounded_full_stream_archives": sum(s.scan["status"] == "FULL_STREAM_SCAN" for s in state.sources),
                       "sampled_archives": 0, "skipped_budget_archives": sum(s.scan["status"] == "SKIPPED_SCAN_BUDGET" for s in state.sources),
                       "excluded_payloads": ["aggTrades", "trades", "orderbook"],
                       "policy": "FULL_SMALL_CSV_ZIPS_WITHIN_HARD_BUDGET_NO_EXTRACTION_NO_L2_OR_TICK_READS"},
                   "historical_scope": "FEATURES_ONLY_Q3_OVERLAPS_HOLDOUT_NO_OUTCOMES_OR_ALPHA",
                   "receiver_pit": "PIT_UNKNOWN", "fill_evidence": "UNKNOWN_NO_EXECUTABLE_FILL_INFERENCE"}
    lineage = {"task": TASK, "schema": "cross_venue.lineage.v1", "labels": list(LABELS),
               "frozen_report_sha256": REPORT_SHA256,
               "frozen_report_sections": [4, 5, 6],
               "p1_interface_reviewed": ["scripts/research/strategy_eval/clocked_dataset.py", "scripts/research/strategy_eval/pipeline.py"],
               "p1_candidate_a_adapter": "NOT_ENABLED_NO_EVALUATOR_IMPORT_OR_CALL",
               "clock": {"decision": "HH:01_UTC", "cutoff": "HH:00_UTC", "bar": "OPEN_C_MINUS_1M_AND_NATIVE_OR_CONFIRMED_END_STRICTLY_BEFORE_C",
                         "binance_file_calendar": "MONTHLY_UTC_DAILY_METRICS_UTC", "okx_file_calendar": "DAILY_UTC_PLUS_8",
                         "epoch_shift_applied_us": 0, "receiver_pit": "PIT_UNKNOWN"},
               "feature_formulas": {name: {"formula": "log(a.close)-log(b.close)", "a": a, "b": b}
                                    for name, (a, b) in FEATURE_INPUTS.items()},
               "venue_basis_spread_formula": "binance_spot_perp_log_basis-okx_spot_perp_log_basis",
               "units": "USDT_PER_BASE_ASSET_NOT_USD_EXECUTABLE_QUOTES; BASIS_IS_DIMENSIONLESS",
               "z": {"venue": "binance", "age_window_s": [300, 600], "native_interval_s": 300,
                     "predecessor_s": 14400, "fields": ["sum_open_interest", "sum_toptrader_long_short_ratio"],
                     "formula": ["log(base_oi_now)-log(base_oi_exact_4h_prior)", "log(top_position_long_short_ratio)"],
                     "okx": "UNKNOWN_NO_HISTORICAL_OI_POSITION_SUBSTITUTE"},
               "funding": {"selection": "ACTUAL_SETTLEMENT_STRICTLY_BEFORE_CUTOFF", "max_age_us": FUNDING_MAX_AGE_US,
                           "max_age_is": "FRESHNESS_POLICY_NOT_SETTLEMENT_SCHEDULE", "future_rate_features": False,
                           "prior_publication_or_receiver_time": "UNKNOWN", "calendars": state.calendars},
               "source_hash_scope": "ACTUAL_RAW_ZIP_SHA_VERIFIED_FOR_FULLY_SCANNED_PASS_SOURCES_ONLY",
               "missingness": "NULL_FEATURE_AND_NO_ACTION_RETAIN_SCHEDULED_ORIGIN", "outcomes_or_alpha": "NOT_RUN"}
    return inventory, coverage, diagnostics, lineage


def prepare_output(path: Path, inputs: Iterable[Path] = ()) -> Path:
    path = ns.safe_path(path)
    ns.require(path.is_relative_to(Path("/tmp")) and path != Path("/tmp"), "OUTPUT_MUST_BE_UNDER_TMP")
    for root in inputs:
        root = ns.safe_path(root)
        ns.require(not (path.is_relative_to(root) or root.is_relative_to(path)), "OUTPUT_INPUT_ALIAS")
    # Creation is confined to /tmp; all existing ancestors are checked first.
    missing = []
    cursor = path
    while not cursor.exists() and not cursor.is_symlink():
        missing.append(cursor)
        cursor = cursor.parent
    ns.safe_directory(cursor)
    for directory in reversed(missing):
        with ns.directory_fd(directory.parent) as fd:
            os.mkdir(directory.name, mode=0o700, dir_fd=fd)
    ns.safe_directory(path)
    with ns.directory_fd(path) as fd:
        ns.require(not os.listdir(fd), "OUTPUT_DIRECTORY_NOT_EMPTY")
    return path


def write_outputs(state: Inspection, path: Path) -> None:
    inventory, coverage, diagnostics, lineage = reports(state)
    hashes = {}
    with ns.directory_fd(path) as directory:
        def write(name: str, chunks: Iterable[bytes]) -> None:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            digest = hashlib.sha256()
            with os.fdopen(fd, "wb") as stream:
                for block in chunks:
                    stream.write(block)
                    digest.update(block)
            hashes[name] = digest.hexdigest()
        write("source_inventory.json", [ns.canonical_bytes(inventory)])
        write("origins.jsonl", (ns.canonical_bytes(row) for row in state.rows))
        write("coverage.json", [ns.canonical_bytes(coverage)])
        write("diagnostics.json", [ns.canonical_bytes(diagnostics)])
        lineage["artifact_sha256"] = hashes
        write("lineage_manifest.json", [ns.canonical_bytes(lineage)])


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ns.BridgeError("INVALID_ARGUMENTS", message=message)


def main(argv: list[str] | None = None) -> int:
    output = None
    try:
        parser = Parser(description=__doc__)
        commands = parser.add_subparsers(dest="command", required=True)
        demo_parser = commands.add_parser("demo")
        demo_parser.add_argument("--output-dir", type=Path, required=True)
        historical = commands.add_parser("inspect-historical")
        historical.add_argument("--output-dir", type=Path, required=True)
        for quarter in ("q3", "q2"):
            for venue in ("binance", "okx"):
                historical.add_argument(f"--{venue}-{quarter}", type=Path, required=quarter == "q3")
        historical.add_argument("--max-expanded-bytes", type=int, default=384 * 1024**2,
                                help="Lower the hard streaming budget; skipped objects remain explicit.")
        args = parser.parse_args(argv)
        roots = {(q.upper(), v): getattr(args, f"{v}_{q}") for q in ("q2", "q3") for v in ("binance", "okx")
                 if args.command == "inspect-historical" and getattr(args, f"{v}_{q}") is not None}
        output = prepare_output(args.output_dir, roots.values())
        if args.command == "demo":
            state = demo()
        else:
            ns.require(0 <= args.max_expanded_bytes <= 384 * 1024**2, "INVALID_SCAN_BUDGET")
            state = inspect_historical(roots, ns.Budget(expanded_cap=args.max_expanded_bytes))
        write_outputs(state, output)
        print(state.status)
        return EXIT_CODES[state.status]
    except (ns.BridgeError, OSError, ValueError, csv.Error, zipfile.BadZipFile) as exc:
        error = exc if isinstance(exc, ns.BridgeError) else ns.BridgeError("OUTPUT_OR_ARGUMENT_ERROR", error_type=type(exc).__name__)
        if output is not None and not any(output.iterdir()):
            write_outputs(Inspection("blocked", error=error), output)
        print(BLOCKED)
        print(ns.canonical_bytes({"exact_cause": error.code, "details": error.details}).decode("ascii").strip(), file=sys.stderr)
        return EXIT_CODES[BLOCKED]


if __name__ == "__main__":
    raise SystemExit(main())
