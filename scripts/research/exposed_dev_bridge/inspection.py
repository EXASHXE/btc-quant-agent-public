"""Streaming P2 source/QC integration with the unchanged BTC P1 controls.

Only feature ZIPs marked PASS in both final documents are opened. L2 and trades
remain metadata only. All quarter denominators survive gaps and warmup. Reading
an archive event clock never attests receiver PIT or authorizes an outcome.
"""

from __future__ import annotations

import csv
import os
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterator

from scripts.research.cross_venue import pipeline as p2
from scripts.research.cross_venue import normalized_sources as n
from scripts.research.strategy_eval import DAY, HORIZONS, PLAN, X_NAMES
from scripts.research.strategy_eval import clocked_dataset as p1

from . import LABELS, checked_path


def inspect_proposal(scope_path: Path, output_dir: Path) -> dict[str, Any]:
    """Unsigned proposal evidence only: metadata and compressed SHA, no CSVs.

    This does not call validate_scope, create authority, or decode any archive.
    Metadata may describe other partitions; only explicitly proposed PASS
    feature ZIPs are hashed, never trades or L2 objects.
    """
    import hashlib
    import json
    from .authorization import _absolute, _digest, _digest_scope, _ranges, _inside
    from .synthetic_contract import write_json

    scope_path = _absolute(str(scope_path))
    with n.published_file(scope_path, 1024**2) as stream:
        raw = stream.read()
    doc = json.loads(raw, object_pairs_hook=n._unique, parse_constant=n._bad_constant)
    n.require(type(doc) is dict and doc.get("schema") == "exposed_dev_bridge.owner-scope.v2",
              "PROPOSAL_V2_REQUIRED")
    envelope = _ranges(doc.get("archive_ranges"), hour_aligned=True)
    origins = _ranges(doc.get("origin_ranges"), hour_aligned=True)
    n.require(all(_inside(a, b, envelope) for a, b in origins), "ORIGIN_WINDOW_OUTSIDE_ARCHIVE_ENVELOPE")
    sources = doc.get("sources")
    n.require(type(sources) is list and 0 < len(sources) <= 4, "EXACT_SOURCES_REQUIRED")
    output = p2.prepare_output(checked_path(output_dir), [scope_path] + [_absolute(s["root"]) for s in sources])
    snapshots, ledger, signatures = [], [], {}
    try:
        for plan in sources:
            root = _absolute(plan["root"])
            snap = n.Snapshot.capture(root, plan["venue"], plan["quarter"])
            snapshots.append(snap)
            n.require(snap.before == {"manifest.json": plan["manifest_sha256"], "qc.json": plan["qc_sha256"]},
                      "SCOPE_METADATA_HASH_MISMATCH")
            inventory = n.expansion_sources(snap, n.Budget(expanded_cap=0))
            by_path = {s.record["local_path"]: s for s in inventory}
            n.require(type(plan["files"]) is list and 0 < len(plan["files"]) <= 1000, "EXACT_FILES_REQUIRED")
            for entry in plan["files"]:
                source = by_path.get(entry["path"])
                n.require(source is not None and source.record.get("verdict") == "PASS"
                          and source.qc.get("verdict") == "PASS" and entry["family"] in n.FEATURE_FAMILIES,
                          "SCOPE_FILE_NOT_PASS")
                r = source.record
                n.require(all(entry[k] == r[k] for k in ("family", "market", "symbol"))
                          and entry["sha256"] == r["local_sha256"], "SCOPE_FILE_IDENTITY_OR_HASH_MISMATCH")
                window = n.file_window(r, snap.venue)
                n.require(window == (n.utc_us(entry["start_utc"]), n.utc_us(entry["end_utc"]))
                          and _inside(*window, envelope), "FULL_ARCHIVE_DATE_AUTHORIZATION_REQUIRED")
                path = root / r["local_path"]
                n.require(path not in signatures, "DUPLICATE_SOURCE_IDENTITY")
                signatures[path] = _raw_signature(path)
                actual = _digest(path)
                n.require(actual == entry["sha256"], "SCOPE_RAW_HASH_MISMATCH")
                ledger.append({"path": str(path), "sha256": actual, "venue": snap.venue,
                    "market": r["market"], "symbol": r["symbol"], "family": r["family"],
                    "file_start_utc_us": window[0], "file_end_utc_us_exclusive": window[1],
                    "manifest_rows": r["rows"], "manifest_gaps": r["gaps"],
                    "payload_rows_read": 0, "receiver_pit": "PIT_UNKNOWN"})
        n.require(all(_raw_signature(p) == sig for p, sig in signatures.items()), "INPUT_CHANGED")
        n.require(_digest_scope(scope_path) == hashlib.sha256(raw).hexdigest(), "INPUT_CHANGED")
    finally:
        for snap in snapshots:
            snap.verify()
    result = {"status": "PROPOSAL_METADATA_SHA_ONLY", "access_status": "P3_ACCESS_SCOPE_HOLD",
        "authorization_decision": doc.get("authorization", {}).get("decision"),
        "protected_dates_complete": doc.get("governance", {}).get("protected_dates_complete"),
        "proposal_sha256": hashlib.sha256(raw).hexdigest(), "pass_compressed_archives": len(ledger),
        "archive_ranges_utc_us_half_open": envelope, "origin_ranges_utc_us_half_open": origins,
        "sources": [s.receipt() for s in snapshots], "archive_ledger": ledger,
        "outcome_labels_read": 0, "historical_outcomes_evaluated": 0, "payload_rows_read": 0,
        "ticks_l2_opened": 0, "exit_code": 0, "labels": list(LABELS)}
    sha = write_json(output, "source_hash_date_receipt.json", result)
    write_json(output, "test_receipt.json", {"status": result["status"], "artifact_sha256": {
        "source_hash_date_receipt.json": sha}, "checks": {"all_pinned_sha_match": True,
        "metadata_unchanged": all(s.unchanged for s in snapshots), "no_archive_payload_decoded": True}})
    return result


def p1_bars(source: n.Source, budget: n.Budget) -> Iterator[p1.Bar]:
    """Keep native taker quote (absent from P2 Bar), using P2's secure reader.

    P1's complete numeric/interval validator and feature formulas are reused;
    P2 supplies descriptor confinement, SHA, ZIP/CRC/schema and final-row QC.
    """
    r = source.record
    n.require(source.snapshot.venue == "binance" and r["symbol"] == "BTCUSDT"
              and r["family"] in ("klines", "spot_klines"), "P1_BTC_SOURCE_REQUIRED")
    n.require(budget.reserve(r), "P1_SCAN_BUDGET_EXCEEDED")
    left, right = n.file_window(r, "binance")
    factor = 1 if r["family"] == "spot_klines" else 1000
    first = last = None
    count = gaps = 0
    for cells in n._csv_rows(source, budget, n.BARS_SCHEMA, headerless=factor == 1):
        bar = p1.Bar(int(cells[0]) * factor, int(cells[6]) * factor,
                     *map(float, cells[1:6]), float(cells[7]), float(cells[10]),
                     r["symbol"], r["market"], "binance")
        n.require(p1._bar_valid(bar, x_control=r["family"] == "klines")
                  and int(cells[6]) - int(cells[0]) == 60 * n.US // factor - 1,
                  "P1_BAR_NUMERIC_OR_INTERVAL_INVALID")
        n.require(left <= bar.open_us < right and (last is None or bar.open_us > last),
                  "P1_BAR_WINDOW_OR_ORDER_INVALID")
        if last is not None:
            gaps += (bar.open_us - last) // (60 * n.US) - 1
        first = bar.open_us if first is None else first
        last = bar.open_us
        count += 1
        n.require(count <= r["rows"], "SOURCE_ROW_LIMIT")
        yield bar
    n._finish(source, count, first, last, budget, missing_minutes=gaps,
              native_time_unit="us" if factor == 1 else "ms", epoch_shift_applied_us=0)
    n.require(gaps == r["gaps"], "SOURCE_GAP_COUNT_MISMATCH", source=source.source_id)


def intersection(sources: list[n.Source], start: int, end: int, asset: str) -> dict[str, Any]:
    """Intersect native UTC bounds across quarters, never shift event epochs."""
    common = [[start * n.US, end * n.US]]
    channels = {}
    for name in p2.PRIMARY_CHANNELS:
        venue, family = p2.CHANNELS[name]
        relevant = [s for s in sources if s.snapshot.venue == venue
                    and s.record["family"] == family and p2._source_asset(s) == asset
                    and s.record.get("verdict") == "PASS"]
        ranges = p2._merge_intervals([
            [max(start * n.US, n.utc_us(s.record["start_utc"])),
             min(end * n.US, n.utc_us(s.record["end_utc"]) + 60 * n.US)]
            for s in relevant if n.utc_us(s.record["start_utc"]) < end * n.US
            and n.utc_us(s.record["end_utc"]) >= start * n.US])
        channels[name] = ranges
        common = p2._merge_intervals([[max(a, c), min(b, d)] for a, b in common for c, d in ranges
                                      if max(a, c) < min(b, d)])
    return {"ranges_utc_us_half_open": common, "channels": channels,
            "candidate_aligned_minutes": sum((b - a) // (60 * n.US) for a, b in common),
            "evidence": "MANIFEST_BOUNDS_REQUIRE_STREAM_CONFIRMATION"}


def _bars(sources: list[n.Source], venue: str, family: str, asset: str,
          start: int, end: int, budget: n.Budget) -> Iterator[n.Bar]:
    # Include the previous minute and adjacent-quarter UTC+8 files. Exhaust
    # every selected ZIP for CRC/QC, including its rows outside this grid.
    selected = [s for s in sources if s.selected and s.snapshot.venue == venue
                and s.record["family"] == family and p2._source_asset(s) == asset
                and n.utc_us(s.record["start_utc"]) < end * n.US
                and n.utc_us(s.record["end_utc"]) >= (start - 60) * n.US]
    for source in sorted(selected, key=lambda s: s.record["start_utc"]):
        yield from n.source_bars(source, budget)
        n.require(source.scan["missing_minutes"] == source.record["gaps"],
                  "SOURCE_GAP_COUNT_MISMATCH", source=source.source_id)


def _raw_signature(path: Path) -> tuple[int, ...]:
    with n.published_file(path, 8 * 1024**2) as stream:
        return n._signature(os.fstat(stream.fileno()))


def inspect_sources(roots: dict[tuple[str, str], Path]) -> p2.Inspection:
    # Limits bound decompression/work, not retained memory; bars are streamed.
    state = p2.Inspection("inspect-historical", n.Budget(
        compressed_cap=256 * 1024**2, expanded_cap=768 * 1024**2,
        object_cap=1500, row_cap=8_000_000))
    raw_signatures = {}
    state.raw_inputs_unchanged = True
    try:
        n.require({("Q3", "binance"), ("Q3", "okx")} <= roots.keys(), "Q3_ROOT_PAIR_REQUIRED")
        n.require(set(roots) <= n.ROOT_NAMES.keys(), "UNSUPPORTED_ROOT_IDENTITY")
        n.require((("Q2", "binance") in roots) == (("Q2", "okx") in roots), "Q2_ROOT_PAIR_REQUIRED")
        for (quarter, venue), root in sorted(roots.items()):
            snap = n.Snapshot.capture(checked_path(root), venue, quarter)
            state.snapshots.append(snap)
            state.sources.extend(n.expansion_sources(snap, state.budget))
        identities = [(s.root.stat().st_dev, s.root.stat().st_ino) for s in state.snapshots]
        n.require(len(set(identities)) == len(identities), "ROOT_ALIAS_OR_DUPLICATE")
        n.require(not any(s.scan["status"] == "SKIPPED_SCAN_BUDGET" for s in state.sources),
                  "FEATURE_SCAN_BUDGET_EXCEEDED")
        for source in state.sources:
            if source.selected:
                path = source.snapshot.root / source.record["local_path"]
                raw_signatures[path] = _raw_signature(path)
        stocks: dict[str, dict[int, n.Stock]] = defaultdict(dict)
        funding: dict[tuple[str, str], list[n.Funding]] = defaultdict(list)
        for source in state.sources:
            if not source.selected:
                continue
            if source.record["family"] == "metrics":
                for stock in n.source_stocks(source, state.budget):
                    n.require(stock.t_us not in stocks[stock.asset], "DUPLICATE_STOCK_TIMESTAMP")
                    stocks[stock.asset][stock.t_us] = stock
            elif source.record["family"] in ("fundingRate", "funding_rates"):
                for event in n.source_funding(source, state.budget):
                    funding[event.asset, event.venue].append(event)
        for events in funding.values():
            events.sort(key=lambda e: e.t_us)
            n.require(len({e.t_us for e in events}) == len(events), "DUPLICATE_FUNDING_SETTLEMENT")

        quarters = sorted({q for q, _ in roots})
        start, end = n.quarter_window(quarters[0])[0], n.quarter_window(quarters[-1])[1]
        p1_budget = n.Budget(expanded_cap=256 * 1024**2, object_cap=512, row_cap=1_000_000)
        btc_stocks = {t // n.US: p1.Stock(t // n.US, s.base_oi, s.top_position_ls)
                      for t, s in stocks.get("BTC", {}).items()}

        def btc_bars(family: str) -> Iterator[p1.Bar]:
            for source in sorted(state.sources, key=lambda s: s.record.get("start_utc", "")):
                if (source.selected and source.snapshot.venue == "binance"
                        and source.record["family"] == family and source.record["symbol"] == "BTCUSDT"):
                    yield from p1_bars(source, p1_budget)

        controls = {r["t"]: r for r in p1.feature_grid(
            btc_bars("klines"), btc_bars("spot_klines"), btc_stocks, start, end)}
        state.p1_budget = p1_budget.receipt()
        for quarter in quarters:
            left, right = n.quarter_window(quarter)
            for asset in ("BTC", "ETH"):
                streams = {name: _bars(state.sources, venue, family, asset, left, right, state.budget)
                           for name, (venue, family) in p2.CHANNELS.items()}
                rows, observed = p2.build_asset_grid(asset, quarter, streams, stocks.get(asset, {}),
                    {v: funding.get((asset, v), []) for v in ("binance", "okx")}, left, right)
                for row in rows:
                    row["labels"] = list(LABELS)
                    row["p1"] = (controls[row["t"]] if asset == "BTC" else
                                 {"x": None, "z": None, "reason": "P1_BTC_ONLY_NO_SYMBOL_RELABEL"})
                state.rows.extend(rows)
                meta = intersection(state.sources, left, right, asset)
                observed.update(metadata=meta, quarter_local_metadata=p2.metadata_intersection(state.sources, quarter, asset),
                    proof=("FULL_STREAM_SCAN_AGREES_WITH_METADATA"
                           if observed["observed_segments_utc_us_half_open"] == meta["ranges_utc_us_half_open"]
                           and observed["aligned_minutes_scanned"] == meta["candidate_aligned_minutes"]
                           else "INCOMPLETE_NO_FULL_COVERAGE_CLAIM"))
                state.intersections.append(observed)
        n.require(all(not s.selected or s.scan["status"] == "FULL_STREAM_SCAN" for s in state.sources),
                  "INCOMPLETE_FEATURE_ARCHIVE_SCAN")
    except (n.BridgeError, OSError, ValueError, KeyError, TypeError, csv.Error, zipfile.BadZipFile, UnicodeError) as exc:
        state.error = exc if isinstance(exc, n.BridgeError) else n.BridgeError(
            "SOURCE_PARSE_OR_IO_ERROR", error_type=type(exc).__name__)
    finally:
        # P2 already verifies each open descriptor. Also cover replacement of
        # an earlier ZIP after that stream closed, through the end of the run.
        for path, before in raw_signatures.items():
            try:
                unchanged = _raw_signature(path) == before
            except (OSError, n.BridgeError):
                unchanged = False
            if not unchanged:
                state.raw_inputs_unchanged = False
                state.error = n.BridgeError("INPUT_CHANGED", path=str(path))
        for snapshot in state.snapshots:
            try:
                snapshot.verify()
            except n.BridgeError as exc:
                state.error = exc
        if state.error is not None:
            state.rows.clear()
            state.intersections.clear()
    return state


def source_coverage(state: p2.Inspection) -> dict[str, Any]:
    grouped = defaultdict(list)
    for source in state.sources:
        r = source.record
        grouped[source.snapshot.quarter, source.snapshot.venue, r["family"], r.get("market"), r["symbol"]].append(source)
    for snap in state.snapshots:
        families = ({"klines", "spot_klines", "markPriceKlines", "metrics", "fundingRate"}
                    if snap.venue == "binance" else {"candlesticks", "spot_candlesticks", "funding_rates"})
        for family in sorted(families):
            symbols = (["ALL_SWAPS"] if family == "funding_rates" else
                       [f"{a}USDT" if snap.venue == "binance" else f"{a}-USDT" +
                        ("" if family == "spot_candlesticks" else "-SWAP") for a in ("BTC", "ETH")])
            for symbol in symbols:
                _, market, _ = n.expected_identity(snap.venue, family, symbol)
                grouped[snap.quarter, snap.venue, family, market, symbol]
        if snap.venue == "okx":
            grouped[snap.quarter, "okx", "orderbook", "swap", "BTC-USDT-SWAP"]
    groups, blockers = [], []
    for key, sources in sorted(grouped.items()):
        quarter, venue, family, market, symbol = key
        verdicts = Counter(s.record.get("verdict", "MISSING") for s in sources)
        status = "PASS" if sources and set(verdicts) == {"PASS"} else "PARTIAL" if verdicts["PASS"] else "MISSING"
        groups.append({"quarter": quarter, "venue": venue, "family": family, "market": market, "symbol": symbol,
            "manifest_status": status, "verdict_counts": dict(sorted(verdicts.items())),
            "manifest_rows": sum(s.record.get("rows", 0) or 0 for s in sources),
            "manifest_gaps": sum(s.record.get("gaps", 0) or 0 for s in sources),
            "full_stream_scanned_records": sum(s.scan["status"] == "FULL_STREAM_SCAN" for s in sources),
            "records": len(sources), "not_pass_periods": [s.record["period"] for s in sources if s.record.get("verdict") != "PASS"],
            "read_policy": "BOUNDED_FEATURE_ZIP_ONLY" if family in n.FEATURE_FAMILIES else "METADATA_ONLY_NEVER_OPENED"})
        if status != "PASS":
            blockers.append({"quarter": quarter, "venue": venue, "family": family, "symbol": symbol,
                "code": "FAMILY_SOURCE_NOT_PASS", "blocks_native_features": family in n.FEATURE_FAMILIES,
                "periods": [s.record["period"] for s in sources if s.record.get("verdict") != "PASS"]})
    return {"status": "PARTIAL_SOURCE_COVERAGE" if blockers or state.error else "PASS",
            "families": groups, "family_blockers": blockers, "utc_intersections": state.intersections,
            "receiver_pit": "PIT_UNKNOWN", "source_admission": "SOURCE_NOT_ADMITTED"}


def panel_schema() -> dict[str, Any]:
    return {"schema": "exposed_dev_bridge.feature-panel.v1", "outcomes_present": False,
        "p1_scope": "BTC_BINANCE_FUTURES_UM_ONLY", "p1_x_names": list(X_NAMES),
        "p1_formula_implementation": "scripts.research.strategy_eval.clocked_dataset.controls",
        "p1_z_implementation": "scripts.research.strategy_eval.clocked_dataset.select_z",
        "cross_venue_implementation": "scripts.research.cross_venue.pipeline.origin",
        "origin": "HH:01", "cutoff": "C=HH:00", "bars": "END_STRICTLY_BEFORE_C",
        "p1_control_window": "1441_EXACT_CONSECUTIVE_MINUTES_C-24H-1M_THROUGH_C-1M",
        "z_sample_age_s_inclusive": [300, 600], "z_exact_predecessor_s": 14400,
        "funding_feature": "ACTUAL_SETTLEMENT_STRICTLY_BEFORE_C_NOT_FIRST_KNOWN",
        "okx_file_calendar": "UTC+08:00", "event_epoch_shift_us": 0,
        "lineage": "SOURCE_ID_RAW_SHA256_NATIVE_TIME_UNIT_VENUE_MARKET_SYMBOL",
        "missingness": "NULL_FEATURE_NO_ACTION_FIXED_DENOMINATOR",
        "outcome_missingness": "OMIT_UNRESOLVED_HORIZON_KEY_WITH_OUTCOME_REASONS_NEVER_ZERO_PNL",
        "real_gate": "PREEXISTING_OWNER_V2_PRIVATE_PARTITIONS_AND_OWNER_PINNED_P1_V1_ALLOWLIST",
        "receiver_pit": "PIT_UNKNOWN", "horizons_h_if_separately_authorized": list(HORIZONS),
        "costs": "DELEGATE_UNCHANGED_P1_COSTS_ONLY_IF_SAFE_AND_AUTHORIZED", "labels": list(LABELS)}


def proposals(state: p2.Inspection) -> dict[str, Any]:
    ranges = []
    if state.snapshots and state.error is None:
        quarters = sorted({s.quarter for s in state.snapshots})
        bounds = intersection(state.sources, n.quarter_window(quarters[0])[0],
                              n.quarter_window(quarters[-1])[1], "BTC")
        for a, b in bounds["ranges_utc_us_half_open"]:
            # Reserve whole UTC days for P1 controls and the maximum outcome.
            left = ((a // n.US + DAY + 60 + DAY - 1) // DAY) * DAY
            right = ((b // n.US - max(HORIZONS) * 3600 - 120) // DAY) * DAY
            if left < right:
                ranges.append({"start_utc": n.iso_us(left * n.US), "end_utc_exclusive": n.iso_us(right * n.US)})
    return {"status": "PROPOSED_ONLY_NOT_AUTHORIZED", "asset": "BTC", "ranges": ranges,
            "maximum_p1_outer_training_days": max(PLAN["outer_development_days"]),
            "outer_validation_days": PLAN["outer_validation_days"],
            "holdout_governance": "UNKNOWN_OWNER_MUST_RESOLVE_PROTECTED_DATES",
            "blockers": ["NO_OWNER_EXPOSED_DEV_ALLOWLIST", "GOVERNED_HOLDOUT_DATES_UNRESOLVED"]}
