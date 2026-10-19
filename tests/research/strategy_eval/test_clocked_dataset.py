import csv
import hashlib
import io
import json
import math
import zipfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts.research.strategy_eval import DAY
from scripts.research.strategy_eval import clocked_dataset as d
from scripts.research.strategy_eval.costs import US


def window(cutoff=2 * DAY):
    futures, spot = [], []
    for i in range(1441):
        t = (cutoff - DAY - 60 + i * 60) * US
        opening = 100 + i * 0.01
        bar = d.Bar(t, t + 60 * US - 1000, opening, opening + 1, opening - 1,
                    opening + 0.005, 10, 1000, 600)
        futures.append(bar)
        spot.append(replace(bar, market="spot", closing=bar.closing / 1.001))
    return futures, spot


def stocks(cutoff=2 * DAY, age=300):
    t = cutoff - age
    return {t: d.Stock(t, 110, 2), t - 14400: d.Stock(t - 14400, 100, 1)}


def test_ten_controls_use_closed_complete_aligned_native_windows():
    f, s = window()
    x, reason = d.controls(f, s, 2 * DAY)
    assert reason == "READY" and len(x) == 10
    assert x[0] == pytest.approx(math.log(f[-1].closing / f[-61].closing))
    assert x[2] == pytest.approx(math.log(f[-1].closing / f[0].closing))
    assert x[5] == pytest.approx(math.log1p(60000))
    assert x[6] == pytest.approx(0)
    assert x[7] == pytest.approx(0.2)
    assert x[9] == pytest.approx(math.log(1.001))


@pytest.mark.parametrize("change,reason", [
    ("boundary", "X_BAR_NOT_STRICTLY_CLOSED"),
    ("gap", "MISSING_X_1M_WINDOW"),
    ("spot_gap", "MISSING_X_1M_WINDOW"),
    ("wrong_market", "X_SOURCE_IDENTITY_INVALID"),
    ("wrong_symbol", "X_SOURCE_IDENTITY_INVALID"),
    ("interval", "X_INVALID_BAR_OR_NATIVE_INTERVAL"),
    ("nan", "X_INVALID_BAR_OR_NATIVE_INTERVAL"),
    ("zero_volume", "X_ZERO_DENOMINATOR"),
    ("zero_range", "X_ZERO_DENOMINATOR"),
])
def test_bad_X_is_unavailable_without_imputation(change, reason):
    f, s = window()
    if change == "boundary":
        f[-1] = replace(f[-1], close_us=2 * DAY * US)
    elif change == "gap":
        del f[100]
    elif change == "spot_gap":
        del s[100]
    elif change == "wrong_market":
        f[-1] = replace(f[-1], market="spot")
    elif change == "wrong_symbol":
        s[-1] = replace(s[-1], symbol="ETHUSDT")
    elif change == "interval":
        f[-1] = replace(f[-1], interval_verified=False)
    elif change == "nan":
        f[-1] = replace(f[-1], closing=float("nan"))
    elif change == "zero_volume":
        f = [replace(b, volume=0) for b in f]
    elif change == "zero_range":
        f = [replace(b, opening=100, closing=100, high=100, low=100) for b in f]
    x, actual = d.controls(f, s, 2 * DAY)
    assert x is None and actual == reason


@pytest.mark.parametrize("age", [300, 600])
def test_native_Z_inclusive_guard_and_exact_4h_base_OI(age):
    z = stocks(age=age)
    result = d.select_z(z, sorted(z), 2 * DAY)
    assert result["z_reason"] == "READY"
    assert result["z"] == pytest.approx([math.log(1.1), math.log(2)])
    assert result["z_4h_exact"]


@pytest.mark.parametrize("change,reason", [
    ("missing", "MISSING_Z"), ("future", "Z_FUTURE_OR_TOO_RECENT"),
    ("same_cutoff", "Z_FUTURE_OR_TOO_RECENT"), ("stale", "Z_STALE"),
    ("missing_predecessor", "Z_4H_PREDECESSOR_MISSING"),
    ("wrong_predecessor", "Z_4H_PREDECESSOR_INVALID"),
    ("wrong_interval", "Z_NATIVE_INTERVAL_INVALID"),
    ("off_grid", "Z_NATIVE_INTERVAL_INVALID"),
    ("wrong_market", "Z_SOURCE_IDENTITY_INVALID"),
    ("nonfinite", "Z_INVALID_STOCK"), ("zero_ratio", "Z_INVALID_STOCK"),
])
def test_stable_Z_no_action_reasons(change, reason):
    cutoff = 2 * DAY
    z = stocks()
    t = cutoff - 300
    if change == "missing":
        z = {}
    elif change in ("future", "same_cutoff"):
        new = cutoff - 299 if change == "future" else cutoff
        z = {new: replace(z[t], t=new)}
    elif change == "stale":
        z = stocks(age=900)
    elif change == "missing_predecessor":
        z.pop(t - 14400)
    elif change == "wrong_predecessor":
        z[t - 14400] = replace(z[t - 14400], t=t - 14400 + 300)
    elif change == "wrong_interval":
        z[t] = replace(z[t], interval_s=60)
    elif change == "off_grid":
        z = stocks(age=350)
    elif change == "wrong_market":
        z[t] = replace(z[t], market="spot")
    elif change == "nonfinite":
        z[t] = replace(z[t], base_oi=float("nan"))
    elif change == "zero_ratio":
        z[t] = replace(z[t], top_position_ls=0)
    result = d.select_z(z, sorted(z), cutoff)
    assert result["z"] is None and result["z_reason"] == reason


def test_origin_denominator_and_future_bar_mutation_invariance():
    cutoff = 2 * DAY
    f, s = window(cutoff)
    future = replace(f[-1], open_us=cutoff * US, close_us=(cutoff + 60) * US - 1000,
                     closing=1e12, high=1e12)
    a = d.feature_grid(f + [future], s, stocks(cutoff), cutoff, cutoff + DAY)
    b = d.feature_grid(f + [replace(future, closing=2e12, high=2e12)], s,
                       stocks(cutoff), cutoff, cutoff + DAY)
    assert len(a) == 24 and a[0]["t"] == cutoff + 60
    assert a[0] == b[0]
    assert d.ready(a[0]) == (True, True)
    assert not d.ready(a[-1])[0]


def test_nonfixed_clocks_and_malformed_ready_Z():
    f, s = window()
    row = d.feature_grid(f, s, stocks(), 2 * DAY, 3 * DAY)[0]
    for bad in (None, {}, [1], [1, float("inf")], "12"):
        assert d.ready({**row, "z": bad}) == (True, False)
    assert d.ready({**row, "z_t": row["t"]}) == (True, False)
    assert d.ready({**row, "x_end_us": row["cutoff"] * US}) == (False, False)
    with pytest.raises(ValueError, match="NON_FIXED_CLOCK"):
        d.ready({**row, "t": row["t"] + 1})


def emit_source(root, venue, family, period, rows, schema, *, header=True):
    symbol, market, interval = d.FAMILY_IDENTITIES[venue][family]
    rel = f"data/{family}/{symbol}-{family}-{period}.zip"
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    member = path.stem + ".csv"
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    if header:
        writer.writerow(schema)
    writer.writerows(rows)
    raw = buffer.getvalue().encode()
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(member, raw)
    if family == "metrics":
        bounds = [int(datetime.strptime(rows[i][0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC).timestamp()) for i in (0, -1)]
    else:
        index = 8 if venue == "okx" else 0
        unit = 1_000_000 if family == "spot_klines" else 1000
        bounds = [rows[i][index] // unit for i in (0, -1)]
    return {
        "venue": venue, "family": family, "symbol": symbol, "market": market, "interval": interval,
        "period": period, "local_path": rel, "local_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "member_filename": member, "rows": len(rows), "expanded_bytes": len(raw),
        "compressed_bytes": path.stat().st_size, "verdict": "PASS", "gaps": 0,
        "duplicates": 0, "malformed_rows": 0, "publisher_checksum_verified": venue == "binance",
        "start_utc": datetime.fromtimestamp(bounds[0], UTC).isoformat(),
        "end_utc": datetime.fromtimestamp(bounds[-1], UTC).isoformat(),
    }


def fixture_roots(tmp_path):
    roots = [tmp_path / "binance", tmp_path / "okx"]
    for root, venue in zip(roots, ("binance", "okx")):
        root.mkdir()
        records = []
        for family in d.FAMILY_IDENTITIES[venue]:
            if family == "metrics":
                for day in range(2):
                    left = d.JULY_START + day * DAY
                    rows = [[datetime.fromtimestamp(left + i * 300, UTC).strftime("%Y-%m-%d %H:%M:%S"),
                             "BTCUSDT", 100 + i, 100000, 1.2, 1.5, 1.1, 1.3] for i in range(288)]
                    records.append(emit_source(root, venue, family, f"2026-07-0{day + 1}", rows, d.METRICS_SCHEMA))
                continue
            count = 2880 if venue == "binance" else 1440
            left = d.JULY_START - (8 * 3600 if venue == "okx" else 0)
            rows = []
            for i in range(count):
                price = 100 + i / 10000
                if venue == "binance":
                    unit = 1_000_000 if family == "spot_klines" else 1000
                    t = (left + i * 60) * unit
                    rows.append([t, price, price + 1, price - 1, price + 0.001, 10,
                                 t + 60 * unit - 1, 1000, 5, 6, 600, 0])
                else:
                    rows.append([d.FAMILY_IDENTITIES[venue][family][0], price, price + 1,
                                 price - 1, price + 0.001, 10, 1, 1000, (left + i * 60) * 1000, 1])
            records.append(emit_source(root, venue, family, "2026-07" if venue == "binance" else "2026-07-01",
                                       rows, d.BARS_SCHEMA if venue == "binance" else d.OKX_SCHEMA,
                                       header=family != "spot_klines"))
        doc = {"manifest_version": "1.0", "venue": venue, "records": records}
        (root / "manifest.json").write_text(json.dumps(doc))
        (root / "qc.json").write_text(json.dumps({"manifest_version": "1.0", "venue": venue, "qc_records": records}))
    return roots


def test_bounded_expansion_dispatch_microseconds_epoch_and_no_full_L2(tmp_path):
    b, o = fixture_roots(tmp_path)
    rows, inventory = d.inspect_panel(b, o)
    assert len(rows) == 31 * 24
    assert inventory["outcomes_evaluated"] == inventory["ticks_l2_opened"] == 0
    assert all("outcomes" not in row for row in rows)
    assert any(d.ready(row)[1] for row in rows)
    spot = next(s for s in inventory["sources"] if s["original_record"]["family"] == "spot_klines")
    assert spot["native_timestamp_unit"] == "us"
    assert spot["first_native_timestamp"] == d.JULY_START * US
    okx = inventory["okx_coverage"]["candlesticks"]
    assert okx["first_utc_s"] == d.JULY_START - 8 * 3600
    assert okx["leading_minutes_outside_utc_july"] == 480
    assert okx["epoch_shift_applied_s"] == 0
    assert inventory["budget"]["expanded_bytes"] < inventory["budget"]["expanded_cap"]
    assert all(s["normalization_status"] == "COMPLETE_BOUNDED_FEATURE_QC" for s in inventory["sources"])


@pytest.mark.parametrize("mutation,reason", [
    ("int_v2", "EXPANSION_SCHEMA_VERSION_INVALID"),
    ("market", "SOURCE_MARKET_OR_INTERVAL_MISMATCH"),
    ("symbol", "REQUIRED_BTC_FEATURE_SERIES_MISSING"),
    ("qc", "MANIFEST_QC_MISMATCH"),
    ("digest", "SOURCE_DIGEST_MISMATCH"),
    ("traversal", "UNSAFE_OBJECT_PATH"),
    ("bad_native_qc", "SOURCE_QC_NOT_COMPLETE_PASS"),
])
def test_bad_expansion_identity_qc_or_schema_rejected(tmp_path, mutation, reason):
    b, _ = fixture_roots(tmp_path)
    manifest = json.loads((b / "manifest.json").read_text())
    record = manifest["records"][0]
    if mutation == "int_v2":
        manifest["manifest_version"] = 2
    elif mutation == "market":
        record["market"] = "spot"
    elif mutation == "symbol":
        record["symbol"] = "ETHUSDT"
    elif mutation == "qc":
        record["rows"] += 1
    elif mutation == "digest":
        record["local_sha256"] = "0" * 64
    elif mutation == "traversal":
        old = record["local_path"]
        record["local_path"] = "../unsafe.zip"
        qc = json.loads((b / "qc.json").read_text())
        next(r for r in qc["qc_records"] if r["local_path"] == old)["local_path"] = record["local_path"]
        (b / "qc.json").write_text(json.dumps(qc))
    elif mutation == "bad_native_qc":
        record["malformed_rows"] = 1
    (b / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match=reason):
        d.expansion_sources(b, "binance", d.Budget())


def test_L2_prefix_is_excluded_even_when_manifest_calls_it_a_full_day(tmp_path):
    _, root = fixture_roots(tmp_path)
    doc = json.loads((root / "manifest.json").read_text())
    doc["records"].append({"venue": "okx", "family": "orderbook", "symbol": "BTC-USDT-SWAP",
                            "market": "swap", "interval": "tick_l2_400lv", "period": "2026-07-01",
                            "local_path": "data/orderbook/DO_NOT_OPEN.zip", "verdict": "PASS",
                            "records_sampled": 2000, "claimed_full_day": True})
    (root / "manifest.json").write_text(json.dumps(doc))
    sources, meta = d.expansion_sources(root, "okx", d.Budget())
    assert all(s.record["family"] != "orderbook" for s in sources)
    assert meta["ticks_l2_opened"] == 0
    assert meta["excluded_family_counts"]["orderbook"] == 1


def test_unordered_native_daily_stocks_are_bounded_sorted_without_PIT_claim(tmp_path):
    root, _ = fixture_roots(tmp_path)
    sources, _ = d.expansion_sources(root, "binance", d.Budget())
    source = next(s for s in sources if s.record["family"] == "metrics")
    path = root / source.record["local_path"]
    with zipfile.ZipFile(path) as archive:
        lines = archive.read(source.record["member_filename"]).splitlines(keepends=True)
    # Native record hashes/order evidence are retained by the adapter; normalized
    # event-time order follows the same explicit dispatch as existing expansion QC.
    changed = lines[0] + b"".join(lines[1:][::-1])
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(source.record["member_filename"], changed)
    normalized = list(d.source_stocks(source, d.Budget()))
    assert len(normalized) == 288
    assert [s.t for s in normalized] == sorted(s.t for s in normalized)
    assert source.native_backward_transitions == 287
    assert source.archive_first_native_timestamp.endswith("23:55:00")
    assert source.inventory()["stock_order_policy"] == "BOUNDED_DAILY_EVENT_TIME_SORT_NOT_RECEIVER_ORDER"
    assert "PIT_UNKNOWN" in source.inventory()["labels"]


def test_wrong_csv_schema_and_unbounded_zip_rejected(tmp_path):
    b, _ = fixture_roots(tmp_path)
    sources, _ = d.expansion_sources(b, "binance", d.Budget())
    source = next(s for s in sources if s.record["family"] == "metrics")
    path = b / source.record["local_path"]
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(source.record["member_filename"], b"wrong,header\n1,2\n")
    source.record["expanded_bytes"] = len(b"wrong,header\n1,2\n")
    with pytest.raises(ValueError, match="CSV_SCHEMA_MISMATCH"):
        list(d.source_stocks(source, d.Budget()))
    source.record["expanded_bytes"] = 100 * 1024**2
    with pytest.raises(ValueError, match="ZIP_EXPANSION_LIMIT"):
        list(d.source_stocks(source, d.Budget()))


def test_output_and_source_aliases_nonempty_hardlinks_and_protected_paths(tmp_path):
    nonempty = tmp_path / "occupied"
    nonempty.mkdir()
    marker = nonempty / "owner.txt"
    marker.write_text("owner dirty bytes")
    with pytest.raises(ValueError, match="OUTPUT_DIRECTORY_NOT_EMPTY"):
        d.prepare_output(nonempty)
    assert marker.read_text() == "owner dirty bytes"
    alias = tmp_path / "alias"
    alias.symlink_to(nonempty, target_is_directory=True)
    with pytest.raises(ValueError, match="SYMLINK"):
        d.prepare_output(alias / "new")
    with pytest.raises(ValueError, match="PROTECTED_OR_TRAVERSAL_PATH"):
        d.safe_directory(tmp_path / "protected" / "missing")
    with pytest.raises(ValueError, match="PROTECTED_OR_TRAVERSAL_PATH"):
        d.safe_directory(tmp_path / ".." / "missing")
    linked = tmp_path / "linked"
    linked.hardlink_to(marker)
    with pytest.raises(ValueError, match="UNSAFE_OBJECT_TYPE"):
        d.safe_file(tmp_path, "linked", 100)


def test_budget_and_duplicate_json_fail_closed(tmp_path):
    budget = d.Budget(compressed_cap=2, expanded_cap=2)
    with pytest.raises(ValueError, match="BUDGET"):
        budget.compressed_object(3)
    with pytest.raises(ValueError, match="BUDGET"):
        budget.expanded_bytes(3)
    path = tmp_path / "duplicate.json"
    path.write_text('{"exposure":"PROTECTED","exposure":"EXPOSED_DEV"}')
    with pytest.raises(ValueError, match="DUPLICATE_JSON_KEY"):
        d.read_json(path)
