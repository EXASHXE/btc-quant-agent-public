"""Focused clock, provenance, publication, missingness and confinement contracts."""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import math
import os
import zipfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.research.cross_venue import LABELS, US
from scripts.research.cross_venue import normalized_sources as n
from scripts.research.cross_venue import pipeline as p

START = n.quarter_window("Q3")[0]


def test_historical_ready_requires_complete_stream_evidence_and_retained_no_action():
    state = p.Inspection("inspect-historical")
    state.snapshots = [SimpleNamespace(quarter="Q3", venue=venue, unchanged=True)
                       for venue in ("binance", "okx")]
    state.sources = [SimpleNamespace(record={"verdict": "PASS", "family": "klines", "gaps": 0},
                                     scan={"status": "FULL_STREAM_SCAN"}, selected=True)]
    state.intersections = [{"hourly_scheduled_origins": 1,
                            "proof": "FULL_STREAM_SCAN_AGREES_WITH_METADATA",
                            "aligned_minutes_scanned": 132000, "native_feature_ready_origins": 1}
                           for _ in ("BTC", "ETH")]
    state.rows = [{"action": "NO_ACTION"}, {"action": "NO_ACTION"}]
    assert state.status == p.READY
    state.sources[0].scan["status"] = "SKIPPED_SCAN_BUDGET"
    assert state.status == p.PARTIAL
    state.sources[0].scan["status"] = "FULL_STREAM_SCAN"
    state.intersections[0]["proof"] = "INCOMPLETE_NO_FULL_COVERAGE_CLAIM"
    assert state.status == p.PARTIAL


def publish(root, venue, records):
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_bytes(n.canonical_bytes({
        "manifest_version": "1.0", "venue": venue, "records": records}))
    (root / "qc.json").write_bytes(n.canonical_bytes({
        "manifest_version": "1.0", "venue": venue, "qc_records": copy.deepcopy(records)}))
    return root


def archive(root, venue, family, *, asset="BTC", times=None, period=None, schema=None, rows=None):
    """Publish tiny private fixtures only, never touching the historical roots."""
    daily = venue == "okx" or family == "metrics"
    period = period or ("2026-07-01" if daily else "2026-07")
    symbol = (f"{asset}USDT" if venue == "binance" else "ALL_SWAPS" if family == "funding_rates"
              else f"{asset}-USDT" + ("" if family == "spot_candlesticks" else "-SWAP"))
    market = "spot" if family in ("spot_klines", "spot_candlesticks") else "futures_um" if venue == "binance" else "swap"
    interval = "5m" if family == "metrics" else "8h" if family in ("fundingRate", "funding_rates") else "1m"
    record = {"family": family, "venue": venue, "symbol": symbol, "period": period, "market": market,
              "interval": interval, "verdict": "PASS", "duplicates": 0, "gaps": 0, "malformed_rows": 0}
    left, _ = n.file_window(record, venue)
    times = times if times is not None else [left, left + 60 * US]
    stem = n.expected_filename(record, venue)
    record.update(local_path=f"data/{family}/{stem}.zip", member_filename=stem + ".csv")
    if rows is None:
        if family in n.BAR_FAMILIES and venue == "binance":
            factor = 1 if family == "spot_klines" else 1000
            rows = [[str(t // factor), "100", "101", "99", "100.5", "10", str((t + 60 * US) // factor - 1),
                     "1000", "5", "5", "500", "0"] for t in times]
            schema = schema or n.BARS_SCHEMA
        elif family in n.BAR_FAMILIES:
            rows = [[symbol, "100", "101", "99", "100.5", "10", "1", "1000", str(t // 1000), "1"] for t in times]
            schema = schema or n.OKX_SCHEMA
        elif family == "metrics":
            rows = [[n.iso_us(t)[:19].replace("T", " "), symbol, "1000", "999999", "8", "1.2", "3", "9"] for t in times]
            schema = schema or n.METRICS_SCHEMA
        elif family == "fundingRate":
            rows = [[str(t // 1000), "8", "0.0001"] for t in times]
            schema = schema or n.FUNDING_SCHEMAS[venue]
        else:
            rows = [[f"{asset}-USDT-SWAP", "0.0001", str(t // 1000)] for t in times]
            schema = schema or n.FUNDING_SCHEMAS[venue]
    text = io.StringIO(newline="")
    writer = csv.writer(text, lineterminator="\n")
    if family != "spot_klines":
        writer.writerow(schema)
    writer.writerows(rows)
    payload = text.getvalue().encode()
    path = root / record["local_path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    member = zipfile.ZipInfo(record["member_filename"], date_time=(2020, 1, 1, 0, 0, 0))
    member.compress_type = zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(member, payload)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    record.update(rows=len(rows), start_utc=n.iso_us(min(times)), end_utc=n.iso_us(max(times)),
                  compressed_bytes=path.stat().st_size, expanded_bytes=len(payload), local_sha256=sha,
                  publisher_checksum_verified=venue == "binance", publisher_checksum=sha if venue == "binance" else None)
    return record


def load(root, venue, records, quarter="Q3", budget=None):
    publish(root, venue, records)
    snapshot = n.Snapshot.capture(root, venue, quarter)
    budget = budget or n.Budget()
    return snapshot, budget, n.expansion_sources(snapshot, budget)


def bar(name, t, asset="BTC", price=100.0):
    venue, family = p.CHANNELS[name]
    market = "spot" if "spot" in name else "swap" if venue == "okx" else "futures_um"
    unit = "us" if family == "spot_klines" else "ms"
    factor = 1 if unit == "us" else 1000
    native = t * US // factor
    close = None if venue == "okx" else native + 60 * US // factor - 1
    provenance = p._synthetic_provenance(asset, venue, family, market, t * US, native, unit, close)
    return n.Bar(asset, venue, market, family, provenance["contract"], t * US, (t + 60) * US - 1,
                 price, price * 1.01, price * .99, price, 10, 1000, provenance)


def stock(t, oi=1000.0, ratio=1.2, asset="BTC"):
    return n.Stock(asset, t * US, oi, ratio, p._synthetic_provenance(
        asset, "binance", "metrics", "futures_um", t * US, str(t), "UTC_TEXT_SECONDS"))


def funding(t_us, venue="binance", rate=.0001, asset="BTC"):
    return n.Funding(asset, venue, t_us, rate, p._synthetic_provenance(
        asset, venue, "fundingRate" if venue == "binance" else "funding_rates",
        "futures_um" if venue == "binance" else "swap", t_us, t_us // 1000, "ms"))


def ready_origin(c=START + 8 * 3600, latest=None):
    samples = [stock(c - 300), stock(c - 300 - 14400, oi=900)]
    stocks = {s.t_us: s for s in samples}
    fs = {v: [funding((c - 3600) * US, v)] for v in ("binance", "okx")}
    return p.origin("BTC", "Q3", c, latest or {name: bar(name, c - 60) for name in p.CHANNELS},
                    stocks, sorted(stocks), fs, {v: [e.t_us for e in events] for v, events in fs.items()})


def test_okx_utc_plus_eight_native_boundary_and_contract_units(tmp_path):
    root = tmp_path / "okx"
    left = (START - 8 * 3600) * US
    record = archive(root, "okx", "candlesticks", times=[left, left + 86400 * US - 60 * US])
    snapshot, budget, sources = load(root, "okx", [record])
    bars = list(n.source_bars(sources[0], budget))
    snapshot.verify()
    assert bars[0].open_us == left
    assert bars[0].provenance["event_utc"] == "2026-06-30T16:00:00.000000Z"
    assert bars[-1].provenance["event_utc"] == "2026-07-01T15:59:00.000000Z"
    assert bars[0].provenance["file_calendar_label"] == "2026-07-01"
    sample = bars[0].as_dict()
    assert sample["native_close"] is None and sample["native_time_unit"] == "ms"
    assert sample["native_volume_unit"] == "CONTRACTS" and sample["price_unit"] == "USDT_PER_BTC"
    assert sample["raw_source_sha256"] == record["local_sha256"]
    assert sources[0].scan["missing_minutes"] == 1438
    outside = archive(tmp_path / "outside", "okx", "candlesticks", times=[left + 86400 * US])
    with pytest.raises(n.BridgeError, match="METADATA_FILE_WINDOW_MISMATCH"):
        load(tmp_path / "outside", "okx", [outside])


@pytest.mark.parametrize("family,unit", [("klines", "ms"), ("spot_klines", "us"), ("markPriceKlines", "ms")])
def test_binance_native_units_and_strict_closed_bar(tmp_path, family, unit):
    root = tmp_path / family
    record = archive(root, "binance", family)
    _, budget, sources = load(root, "binance", [record])
    bars = list(n.source_bars(sources[0], budget))
    assert bars[0].open_us == START * US
    assert bars[0].end_us < (START + 60) * US
    assert bars[0].provenance["native_time_unit"] == unit
    assert bars[0].provenance["native_close"] == (START + 60) * (US if unit == "us" else 1000) - 1
    assert bars[0].as_dict()["price_role"] == ("MARK_VALUATION" if family == "markPriceKlines" else "LAST_TRADE_BAR")


@pytest.mark.parametrize("mutation,reason", [("close", "BAR_NOT_STRICTLY_CLOSED"), ("future", "BAR_FUTURE"), ("stale", "BAR_STALE_OR_GAP"), ("family", "BAR_FAMILY_MISMATCH")])
def test_price_features_reject_unclosed_future_stale_or_wrong_family(mutation, reason):
    c = START + 8 * 3600
    latest = {name: bar(name, c - 60) for name in p.CHANNELS}
    original = latest["binance_perp"]
    latest["binance_perp"] = (replace(original, end_us=c * US) if mutation == "close" else
                               bar("binance_perp", c) if mutation == "future" else
                               bar("binance_perp", c - 120) if mutation == "stale" else
                               replace(original, market="spot"))
    row = ready_origin(c, latest)
    assert row["bars"]["binance_perp"]["reason"] == reason
    assert row["features"]["lagged_venue_perp_log_price_spread"] is None
    assert row["action"] == "NO_ACTION" and not row["native_feature_ready"]


def test_spreads_share_exact_closed_minute_and_do_not_imply_fills():
    c = START + 8 * 3600
    prices = dict(zip(p.CHANNELS, [102, 101, 100, 99, 103]))
    row = ready_origin(c, {name: bar(name, c - 60, price=price) for name, price in prices.items()})
    f = row["features"]
    assert f["lagged_venue_perp_log_price_spread"] == pytest.approx(math.log(102 / 100))
    assert f["lagged_venue_basis_spread"] == pytest.approx(math.log(102 / 101) - math.log(100 / 99))
    assert f["binance_mark_last_log_spread"] == pytest.approx(math.log(103 / 102))
    assert all(cell["sample"]["executable_fill"] == "UNKNOWN" for cell in row["bars"].values())


@pytest.mark.parametrize("age,prior,reason", [(0, False, "Z_FUTURE_OR_TOO_RECENT"), (900, True, "Z_STALE"), (300, False, "Z_4H_PREDECESSOR_MISSING"), (600, True, "READY")])
def test_z_lag_future_stale_and_exact_predecessor(age, prior, reason):
    c = START + 8 * 3600
    sample = stock(c - age)
    values = {sample.t_us: sample}
    if prior:
        old = stock(c - age - 14400, oi=900)
        values[old.t_us] = old
    z = p.select_z(values, sorted(values), c, "BTC")
    assert z["reason"] == reason
    assert (z["z"] is not None) == (reason == "READY")


def test_z_no_nearest_predecessor_substitute_or_future_mutation():
    c = START + 8 * 3600
    sample, wrong = stock(c - 300), stock(c - 300 - 14400 - 300)
    values = {s.t_us: s for s in (sample, wrong)}
    assert p.select_z(values, sorted(values), c, "BTC")["reason"] == "Z_4H_PREDECESSOR_MISSING"
    old = stock(c - 300 - 14400, oi=900)
    values[old.t_us] = old
    baseline = p.select_z(values, sorted(values), c, "BTC")
    future = stock(c + 3600, oi=1e12)
    values[future.t_us] = future
    assert p.select_z(values, sorted(values), c, "BTC") == baseline
    assert baseline["z"][0] == pytest.approx(math.log(1000 / 900))
    values[sample.t_us] = replace(sample, asset="ETH")
    assert p.select_z(values, sorted(values), c, "BTC")["reason"] == "Z_FAMILY_OR_INTERVAL_MISMATCH"


@pytest.mark.parametrize("field,value,reason", [("interval_s", 60, "Z_FAMILY_OR_INTERVAL_MISMATCH"), ("base_oi", None, "Z_INVALID_STOCK"), ("base_oi", 0, "Z_INVALID_STOCK"), ("top_position_ls", None, "Z_INVALID_STOCK")])
def test_z_missing_invalid_native_stock_stays_unavailable(field, value, reason):
    c = START + 8 * 3600
    sample = replace(stock(c - 300), **{field: value})
    old = stock(c - 300 - 14400)
    values = {s.t_us: s for s in (sample, old)}
    assert p.select_z(values, sorted(values), c, "BTC")["reason"] == reason


def test_stock_reader_preserves_base_stock_and_bounded_native_event_sort(tmp_path):
    root = tmp_path / "stocks"
    record = archive(root, "binance", "metrics", times=[(START + 300) * US, START * US])
    _, budget, sources = load(root, "binance", [record])
    stocks = list(n.source_stocks(sources[0], budget))
    assert [s.t_us for s in stocks] == [START * US, (START + 300) * US]
    assert stocks[0].base_oi == 1000 and stocks[0].top_position_ls == 1.2
    assert sources[0].scan["native_backward_transitions"] == 1
    assert stocks[0].as_dict()["base_oi_unit"] == "BTC"
    assert stocks[0].provenance["receiver_pit"] == "PIT_UNKNOWN"


def test_unknown_okx_oi_and_receiver_pit_force_no_action_even_with_features():
    row = ready_origin()
    assert row["native_feature_ready"]
    assert row["okx_z"] == {"status": "UNKNOWN", "z": None, "reason": "OKX_HISTORICAL_OI_POSITION_UNKNOWN"}
    assert row["receiver_pit"] == "PIT_UNKNOWN" and row["action"] == "NO_ACTION"
    assert set(LABELS) <= set(row["labels"])
    assert "PIT_UNKNOWN" in row["no_action_reasons"]


def test_funding_actual_millisecond_calendar_rejects_future_at_cutoff_and_stale():
    c = START + 8 * 3600
    at = funding(c * US)
    after = funding(c * US + 2000, rate=.9)
    assert p.settled_funding([at, after], [at.t_us, after.t_us], c, "BTC", "binance")["reason"] == "FUNDING_FUTURE_OR_AT_CUTOFF"
    old = funding((c - 8 * 3600) * US + 2000)
    base = p.settled_funding([old], [old.t_us], c, "BTC", "binance")
    assert base["age_us"] == 8 * 3600 * US - 2000
    assert p.settled_funding([old, at, after], [old.t_us, at.t_us, after.t_us], c, "BTC", "binance") == base
    stale = funding(c * US - p.FUNDING_MAX_AGE_US - 1)
    assert p.settled_funding([stale], [stale.t_us], c, "BTC", "binance")["reason"] == "FUNDING_STALE"
    assert p.settled_funding([], [], c, "BTC", "okx")["reason"] == "FUNDING_MISSING"


def test_funding_reader_uses_native_events_without_inventing_eight_hour_grid(tmp_path):
    root = tmp_path / "funding"
    events = [START * US, (START + 3600) * US + 2000, (START + 3 * 3600) * US]
    record = archive(root, "binance", "fundingRate", times=events)
    _, budget, sources = load(root, "binance", [record])
    parsed = list(n.source_funding(sources[0], budget))
    assert [e.t_us for e in parsed] == events
    assert parsed[1].provenance["native_sample"] == (START + 3600) * 1000 + 2
    chosen = p.settled_funding(parsed, events, START + 2 * 3600, "BTC", "binance")
    assert chosen["sample"]["event_utc_us"] == events[1]


def test_okx_aggregate_physical_end_is_not_the_actual_instrument_calendar_end(tmp_path):
    root = tmp_path / "aggregate"
    left = (START - 8 * 3600) * US
    times = [left, left + 16 * 3600 * US, left + 23 * 3600 * US, left, left + 20 * 3600 * US]
    rows = [[symbol, ".0001", str(t // 1000)] for symbol, t in zip(
        ["BTC-USDT-SWAP", "BTC-USDT-SWAP", "OTHER-USDT-SWAP", "ETH-USDT-SWAP", "ZRX-USDT-SWAP"], times)]
    record = archive(root, "okx", "funding_rates", times=times, rows=rows, schema=n.FUNDING_SCHEMAS["okx"])
    record["end_utc"] = n.iso_us(times[-1])  # Actual expansion producer's physical-row convention.
    _, budget, sources = load(root, "okx", [record])
    events = list(n.source_funding(sources[0], budget))
    assert [(e.asset, e.t_us) for e in events] == [("BTC", times[0]), ("BTC", times[1]), ("ETH", times[3])]
    scan = sources[0].scan
    assert scan["last_event_utc_us"] == times[-1] and scan["observed_max_event_utc_us"] == times[2]
    assert events[0].as_dict()["contract"] == "BTC-USDT-SWAP"
    assert events[0].as_dict()["container_contract"] == "ALL_SWAPS"
    assert record["end_utc"] == n.iso_us(times[-1])


def test_null_funding_is_unavailable_without_poisoning_other_instruments(tmp_path):
    root = tmp_path / "null_rates"
    left = (START - 8 * 3600) * US
    times = [left, left + 8 * 3600 * US, left + 12 * 3600 * US]
    rows = [["BTC-USDT-SWAP", ".0001", str(times[0] // 1000)],
            ["BTC-USDT-SWAP", "None", str(times[1] // 1000)],
            ["IP-USDT-SWAP", "None", str(times[2] // 1000)]]
    record = archive(root, "okx", "funding_rates", times=times, rows=rows, schema=n.FUNDING_SCHEMAS["okx"])
    _, budget, sources = load(root, "okx", [record])
    events = list(n.source_funding(sources[0], budget))
    assert len(events) == 2 and events[1].rate is None
    assert sources[0].scan["invalid_rate_rows"] == 2 and sources[0].scan["retained_invalid_rate_rows"] == 1
    selected = p.settled_funding(events, [e.t_us for e in events], START + 3600, "BTC", "okx")
    assert selected["reason"] == "FUNDING_INVALID_RATE" and selected["sample"] is None


def test_april_l2_missing_is_separate_btc_q2_blocker_and_never_opened(tmp_path):
    missing = {"local_path": "data/orderbook/BTC-USDT-SWAP-L2orderbook-400lv-2026-04-01.tar.gz",
               "family": "orderbook", "symbol": "BTC-USDT-SWAP", "period": "2026-04-01", "market": "swap",
               "venue": "okx", "verdict": "OBJECT_NOT_FOUND", "interval": "tick_l2_400lv"}
    snapshot, budget, sources = load(tmp_path / "q2", "okx", [missing], quarter="Q2")
    state = p.Inspection("inspect-historical", budget, [snapshot], sources)
    groups = p.reports(state)[1]["groups"]
    btc = next(g for g in groups if (g["quarter"], g["asset"], g["venue"]) == ("Q2", "BTC", "okx"))
    eth = next(g for g in groups if (g["quarter"], g["asset"], g["venue"]) == ("Q2", "ETH", "okx"))
    assert "APRIL_01_BTC_400_LEVEL_L2_MISSING" in btc["source_feature_blockers"]
    assert "APRIL_01_BTC_400_LEVEL_L2_MISSING" not in eth["source_feature_blockers"]
    assert not btc["complete_source_pass_claim"] and btc["record_counts"]["published_pass_records"] == 0
    assert sources[0].actual_sha256 is None and not sources[0].selected
    assert budget.compressed_read == budget.expanded_read == 0


def test_l2_prefix_pass_never_becomes_full_day_or_normalized_candles(tmp_path):
    record = {"local_path": "data/orderbook/large.tar.gz", "family": "orderbook", "symbol": "BTC-USDT-SWAP",
              "period": "2026-07-01", "market": "swap", "venue": "okx", "verdict": "PASS", "records_sampled": 2000}
    _, budget, sources = load(tmp_path / "prefix", "okx", [record])
    assert not sources[0].selected
    assert sources[0].scan["producer_qc_scope"] == "PREFIX_ONLY_NOT_FULL_L2_CONTINUITY"
    assert budget.compressed_read == 0


def test_q2_pass_with_mark_gap_is_reported_as_partial_features(tmp_path):
    root = tmp_path / "q2_marks"
    april = n.quarter_window("Q2")[0] * US
    record = archive(root, "binance", "markPriceKlines", period="2026-04",
                     times=[april, april + 60 * US, april + 3 * 60 * US])
    record["gaps"] = 1
    snapshot, budget, sources = load(root, "binance", [record], quarter="Q2")
    assert len(list(n.source_bars(sources[0], budget))) == 3
    assert sources[0].scan["missing_minutes"] == 1 and record["verdict"] == "PASS"
    groups = p.coverage_groups(p.Inspection("inspect-historical", budget, [snapshot], sources))
    group = next(g for g in groups if (g["quarter"], g["asset"], g["venue"]) == ("Q2", "BTC", "binance"))
    assert "BAR_GAPS:markPriceKlines" in group["source_feature_blockers"]
    assert group["record_counts"]["published_pass_records"] == 1
    assert not group["complete_source_pass_claim"]


@pytest.mark.parametrize("mutation,code", [("market", "SOURCE_FAMILY_IDENTITY_MISMATCH"), ("path", "SOURCE_PATH_FAMILY_MISMATCH"), ("interval", "SOURCE_FAMILY_IDENTITY_MISMATCH"), ("schema", "CSV_FAMILY_SCHEMA_MISMATCH")])
def test_family_market_interval_and_schema_dispatch(tmp_path, mutation, code):
    root = tmp_path / "identity"
    record = archive(root, "binance", "klines", schema=n.METRICS_SCHEMA if mutation == "schema" else None)
    if mutation == "market":
        record["market"] = "spot"
    if mutation == "path":
        record["local_path"] = record["local_path"].replace("klines", "spot_klines")
    if mutation == "interval":
        record["interval"] = "5m"
    with pytest.raises(n.BridgeError, match=code):
        _, budget, sources = load(root, "binance", [record])
        list(n.source_bars(sources[0], budget))


@pytest.mark.parametrize("kind,code", [("bars", "DUPLICATE_OR_BACKWARD_BAR"), ("stocks", "DUPLICATE_STOCK_TIMESTAMP"), ("funding", "DUPLICATE_FUNDING_SETTLEMENT")])
def test_duplicate_raw_events_are_not_silently_deduplicated(tmp_path, kind, code):
    root = tmp_path / "duplicates"
    family = {"bars": "klines", "stocks": "metrics", "funding": "fundingRate"}[kind]
    record = archive(root, "binance", family, times=[START * US, START * US])
    _, budget, sources = load(root, "binance", [record])
    reader = {"bars": n.source_bars, "stocks": n.source_stocks, "funding": n.source_funding}[kind]
    with pytest.raises(n.BridgeError, match=code):
        list(reader(sources[0], budget))


def test_duplicate_manifest_identities_and_json_keys_are_blocked(tmp_path):
    root = tmp_path / "dup_manifest"
    record = archive(root, "binance", "klines")
    with pytest.raises(n.BridgeError, match="DUPLICATE_SOURCE_IDENTITY"):
        load(root, "binance", [record, record])
    (root / "manifest.json").write_text('{"manifest_version":"1.0","manifest_version":"1.0"}')
    with pytest.raises(n.BridgeError, match="DUPLICATE_JSON_KEY"):
        n.Snapshot.capture(root, "binance", "Q3")


@pytest.mark.parametrize("verdict", ["PARTIAL_PASS", "FAIL", "OBJECT_NOT_FOUND"])
def test_non_pass_records_are_metadata_only_and_missing_files_are_not_opened(tmp_path, verdict):
    record = {"local_path": "data/klines/BTCUSDT-1m-2026-07.zip", "family": "klines", "symbol": "BTCUSDT",
              "period": "2026-07", "verdict": verdict}
    _, budget, sources = load(tmp_path / "nonpass", "binance", [record])
    assert not sources[0].selected and sources[0].scan["status"] == "NOT_PASS_NOT_OPENED"
    assert sources[0].actual_sha256 is None and budget.compressed_read == 0


def test_manifest_and_qc_must_both_publish_same_pass(tmp_path):
    root = tmp_path / "two_docs"
    record = archive(root, "binance", "klines")
    publish(root, "binance", [record])
    qc = json.loads((root / "qc.json").read_bytes())
    qc["qc_records"][0]["verdict"] = "FAIL"
    (root / "qc.json").write_bytes(n.canonical_bytes(qc))
    snapshot = n.Snapshot.capture(root, "binance", "Q3")
    with pytest.raises(n.BridgeError, match="MANIFEST_QC_MISMATCH"):
        n.expansion_sources(snapshot, n.Budget())


@pytest.mark.parametrize("document", ["manifest.json", "qc.json"])
def test_moving_snapshot_sha_blocks_and_discards_all_feature_rows(tmp_path, monkeypatch, document):
    b, o = tmp_path / "binance", tmp_path / "okx"
    publish(b, "binance", [archive(b, "binance", "klines")])
    publish(o, "okx", [])
    original = n.source_bars
    moved = False
    def mutate(source, budget):
        nonlocal moved
        yield from original(source, budget)
        if not moved:
            target = b / document
            target.write_bytes(target.read_bytes() + b"\n")
            moved = True
    monkeypatch.setattr(n, "source_bars", mutate)
    state = p.inspect_historical({("Q3", "binance"): b, ("Q3", "okx"): o})
    assert state.status == p.BLOCKED and state.error.code == "INPUT_CHANGED"
    assert not state.rows and not state.calendars and not state.intersections
    receipt = state.snapshots[0].receipt()
    assert receipt["sha256_before"][document] != receipt["sha256_after"][document]
    assert not receipt["unchanged"]


def test_no_action_denominator_retains_warmup_gaps_and_unavailable_tail():
    start, end = START, START + 8 * 3600
    def stream(name):
        for t in range(start, start + 3 * 3600, 60):
            if not (name == "okx_swap" and t == start + 2 * 3600 - 60):
                yield bar(name, t)
    rows, observed = p.build_asset_grid("BTC", "Q3", {name: stream(name) for name in p.CHANNELS}, {}, {}, start, end)
    assert [r["t"] for r in rows] == list(range(start + 60, end, 3600))
    assert observed["aligned_minutes_scanned"] == 179
    assert len(rows) == 8 and all(r["action"] == "NO_ACTION" for r in rows)
    assert rows[2]["features"]["lagged_venue_perp_log_price_spread"] is None
    assert rows[-1]["bars"]["okx_swap"]["reason"] == "BAR_STALE_OR_GAP"


def test_duplicates_across_stream_segments_cannot_expand_the_intersection():
    streams = {name: [bar(name, START), bar(name, START)] for name in p.CHANNELS}
    with pytest.raises(n.BridgeError, match="DUPLICATE_OR_BACKWARD_STREAM_BAR"):
        p.build_asset_grid("BTC", "Q3", streams, {}, {}, START, START + 3600)


def test_budget_skip_is_explicit_and_never_reported_as_complete_scan(tmp_path):
    b, o = tmp_path / "b", tmp_path / "o"
    publish(b, "binance", [archive(b, "binance", "klines")])
    publish(o, "okx", [archive(o, "okx", "candlesticks")])
    state = p.inspect_historical({("Q3", "binance"): b, ("Q3", "okx"): o}, n.Budget(expanded_cap=0))
    assert state.status == p.PARTIAL and len(state.rows) == 2 * 92 * 24
    assert all(s.scan["status"] == "SKIPPED_SCAN_BUDGET" and s.actual_sha256 is None for s in state.sources)
    assert all(c["proof"] == "INCOMPLETE_NO_FULL_COVERAGE_CLAIM" for c in state.intersections)
    assert p.reports(state)[2]["scan_scope"]["skipped_budget_archives"] == 2
    assert state.budget.compressed_read == state.budget.expanded_read == 0


@pytest.mark.parametrize("part", ["holdout", "holdout_alias", "protected-store", "HiStOrY", "oos.data", ".git", "staging", "download.part"])
def test_sensitive_alias_components_are_rejected(tmp_path, part):
    with pytest.raises(n.BridgeError, match="PROTECTED_PATH|UNPUBLISHED_PATH"):
        p.prepare_output(tmp_path / part / "new")


def test_symlink_ancestors_and_output_input_alias_are_rejected(tmp_path):
    actual = tmp_path / "actual"
    actual.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(actual, target_is_directory=True)
    with pytest.raises(n.BridgeError, match="UNSAFE_OR_MISSING_DIRECTORY"):
        p.prepare_output(alias / "new")
    with pytest.raises(n.BridgeError, match="UNSAFE_OR_MISSING_DIRECTORY"):
        n.Snapshot.capture(alias, "binance", "Q3")
    with pytest.raises(n.BridgeError, match="OUTPUT_INPUT_ALIAS"):
        p.prepare_output(actual / "new", [actual])
    with pytest.raises(n.BridgeError, match="OUTPUT_MUST_BE_UNDER_TMP"):
        p.prepare_output(Path("/root/workspace/project/quant-0.6.5/new-output"))
    with pytest.raises(n.BridgeError, match="UNSAFE_TRAVERSAL_PATH"):
        p.prepare_output(tmp_path / ".." / "new")


@pytest.mark.parametrize("kind", ["symlink", "hardlink"])
def test_archive_aliases_cannot_reach_other_data(tmp_path, kind):
    root = tmp_path / "input"
    record = archive(root, "binance", "klines")
    _, budget, sources = load(root, "binance", [record])
    path = root / record["local_path"]
    target = tmp_path / "target.zip"
    path.rename(target)
    if kind == "symlink":
        path.symlink_to(target)
    else:
        os.link(target, path)
    with pytest.raises(n.BridgeError, match="UNSAFE_OR_MISSING_FILE|UNSAFE_FILE_TYPE_OR_HARDLINK"):
        list(n.source_bars(sources[0], budget))


def test_unsafe_nonempty_output_preserves_owner_bytes_and_strict_stdout(tmp_path, capsys):
    output = tmp_path / "output"
    output.mkdir()
    owner = output / "owner.txt"
    owner.write_bytes(b"Owner bytes\n")
    assert p.main(["demo", "--output-dir", str(output)]) == 2
    captured = capsys.readouterr()
    assert captured.out == "BLOCKED_EXACT_CAUSE\n"
    assert json.loads(captured.err)["exact_cause"] == "OUTPUT_DIRECTORY_NOT_EMPTY"
    assert owner.read_bytes() == b"Owner bytes\n" and list(output.iterdir()) == [owner]


def test_blocked_cli_keeps_exact_cause_and_writes_reviewable_failure_outputs(tmp_path, capsys):
    b, o = tmp_path / "b", tmp_path / "o"
    record = archive(b, "binance", "klines")
    record["market"] = "spot"
    publish(b, "binance", [record])
    publish(o, "okx", [])
    output = tmp_path / "blocked_result"
    assert p.main(["inspect-historical", "--binance-q3", str(b), "--okx-q3", str(o), "--output-dir", str(output)]) == 2
    assert capsys.readouterr().out == "BLOCKED_EXACT_CAUSE\n"
    assert {path.name for path in output.iterdir()} == set(p.OUTPUT_FILES)
    diagnostics = json.loads((output / "diagnostics.json").read_bytes())
    assert diagnostics["exact_cause"] == "SOURCE_FAMILY_IDENTITY_MISMATCH"
    assert (output / "origins.jsonl").read_bytes() == b""


def test_demo_cli_deterministic_scientific_bytes_and_artifact_hashes(tmp_path, capsys):
    outputs = [tmp_path / "one", tmp_path / "two"]
    for output in outputs:
        assert p.main(["demo", "--output-dir", str(output)]) == 0
        assert capsys.readouterr().out == "CROSS_VENUE_DEV_READY\n"
    assert {f.name for f in outputs[0].iterdir()} == set(p.OUTPUT_FILES)
    for name in p.OUTPUT_FILES:
        assert (outputs[0] / name).read_bytes() == (outputs[1] / name).read_bytes()
    lineage = json.loads((outputs[0] / "lineage_manifest.json").read_bytes())
    for name, expected in lineage["artifact_sha256"].items():
        assert hashlib.sha256((outputs[0] / name).read_bytes()).hexdigest() == expected
    diagnostics = json.loads((outputs[0] / "diagnostics.json").read_bytes())
    assert diagnostics["counts"]["origins"] == diagnostics["counts"]["no_action"] == 16
    assert diagnostics["counts"]["native_feature_ready"] == 6
    assert diagnostics["counts"]["outcomes_evaluated"] == diagnostics["counts"]["alpha_tests"] == 0
    assert set(LABELS) <= set(diagnostics["labels"])
    inventory = json.loads((outputs[0] / "source_inventory.json").read_bytes())
    identities = {s["source_id"] for s in inventory["sources"]}
    assert len(identities) == 16
    with (outputs[0] / "origins.jsonl").open() as stream:
        row = list(map(json.loads, stream))[-1]
    assert all(cell["sample"]["source_id"] in identities for cell in row["bars"].values())
    assert row["binance_z"]["sample"]["source_id"] in identities
    assert all(cell["sample"]["source_id"] in identities for cell in row["settled_funding"].values())


def test_historical_scientific_bytes_are_independent_of_output_directory(tmp_path):
    b, o = publish(tmp_path / "b", "binance", []), publish(tmp_path / "o", "okx", [])
    roots = {("Q3", "binance"): b, ("Q3", "okx"): o}
    for name in ("one", "two"):
        state = p.inspect_historical(roots)
        assert state.status == p.PARTIAL
        p.write_outputs(state, p.prepare_output(tmp_path / name, roots.values()))
    for name in p.OUTPUT_FILES:
        assert (tmp_path / "one" / name).read_bytes() == (tmp_path / "two" / name).read_bytes()


def test_raw_source_sha_mismatch_blocks_instead_of_using_qc_claim(tmp_path):
    root = tmp_path / "hash"
    record = archive(root, "binance", "klines")
    record["local_sha256"] = record["publisher_checksum"] = "0" * 64
    _, budget, sources = load(root, "binance", [record])
    with pytest.raises(n.BridgeError, match="RAW_SOURCE_SHA_MISMATCH"):
        list(n.source_bars(sources[0], budget))


def test_expansion_schema_is_not_relabelled_as_p0_v2(tmp_path):
    root = publish(tmp_path / "version", "binance", [])
    doc = json.loads((root / "manifest.json").read_bytes())
    doc["manifest_version"] = 2
    (root / "manifest.json").write_bytes(n.canonical_bytes(doc))
    snapshot = n.Snapshot.capture(root, "binance", "Q3")
    with pytest.raises(n.BridgeError, match="EXPANSION_SCHEMA_VERSION_INVALID"):
        n.expansion_sources(snapshot, n.Budget())
