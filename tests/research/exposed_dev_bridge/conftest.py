"""Small, private final-manifest fixtures; no production writer imports."""

import copy
import csv
import hashlib
import io
import json
import zipfile

import pytest

from scripts.research.cross_venue import normalized_sources as n


def publish(root, venue, records):
    root.mkdir(parents=True, exist_ok=True)
    for name, key in (("manifest.json", "records"), ("qc.json", "qc_records")):
        (root / name).write_bytes(n.canonical_bytes({
            "manifest_version": "1.0", "venue": venue, key: copy.deepcopy(records)}))
    return root


def archive(root, venue, family, *, period="2026-07", asset="BTC", times=None):
    daily = venue == "okx" or family == "metrics"
    if daily and len(period) == 7:
        period += "-01"
    symbol = (f"{asset}USDT" if venue == "binance" else "ALL_SWAPS" if family == "funding_rates"
              else f"{asset}-USDT" + ("" if family == "spot_candlesticks" else "-SWAP"))
    record = {"venue": venue, "family": family, "symbol": symbol, "period": period,
        "market": "spot" if family in ("spot_klines", "spot_candlesticks") else "futures_um" if venue == "binance" else "swap",
        "interval": "5m" if family == "metrics" else "8h" if family in ("fundingRate", "funding_rates") else "1m",
        "verdict": "PASS", "duplicates": 0, "gaps": 0, "malformed_rows": 0}
    left, _ = n.file_window(record, venue)
    times = times if times is not None else [left, left + (300 if family == "metrics" else 60) * n.US]
    stem = n.expected_filename(record, venue)
    record.update(local_path=f"data/{family}/{stem}.zip", member_filename=stem + ".csv")
    if family in n.BAR_FAMILIES and venue == "binance":
        factor = 1 if family == "spot_klines" else 1000
        rows = [[t // factor, 100, 102, 99, 101, 10, (t + 60 * n.US) // factor - 1,
                 1000, 5, 5, 500, 0] for t in times]
        schema = n.BARS_SCHEMA
    elif family in n.BAR_FAMILIES:
        rows = [[symbol, 100, 102, 99, 101, 10, 1, 1000, t // 1000, 1] for t in times]
        schema = n.OKX_SCHEMA
    elif family == "metrics":
        rows = [[n.iso_us(t)[:19].replace("T", " "), symbol, 1000 + i, 999999, 8, 1.2, 3, 9]
                for i, t in enumerate(times)]
        schema = n.METRICS_SCHEMA
    elif family == "fundingRate":
        rows = [[t // 1000, 8, .0001] for t in times]
        schema = n.FUNDING_SCHEMAS[venue]
    else:
        rows = [[f"{asset}-USDT-SWAP", .0001, t // 1000] for t in times]
        schema = n.FUNDING_SCHEMAS[venue]
    payload = io.StringIO(newline="")
    writer = csv.writer(payload, lineterminator="\n")
    if family != "spot_klines":
        writer.writerow(schema)
    writer.writerows(rows)
    raw = payload.getvalue().encode()
    path = root / record["local_path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    member = zipfile.ZipInfo(record["member_filename"], date_time=(2020, 1, 1, 0, 0, 0))
    member.compress_type = zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(path, "w") as target:
        target.writestr(member, raw)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    record.update(rows=len(rows), start_utc=n.iso_us(min(times)), end_utc=n.iso_us(max(times)),
        compressed_bytes=path.stat().st_size, expanded_bytes=len(raw), local_sha256=digest,
        publisher_checksum_verified=venue == "binance", publisher_checksum=digest if venue == "binance" else None)
    return record


@pytest.fixture
def empty_roots(tmp_path):
    return {("Q3", venue): publish(tmp_path / venue, venue, []) for venue in ("binance", "okx")}


@pytest.fixture
def owner_scope(tmp_path):
    root = tmp_path / "binance"
    record = archive(root, "binance", "metrics")
    publish(root, "binance", [record])
    left, right = n.file_window(record, "binance")
    doc = {"schema": "exposed_dev_bridge.owner-scope.v1", "exposure": "EXPOSED_DEV",
        "authorization": {"role": "Owner", "owner": "Synthetic fixture owner", "reference": "TEST_ONLY",
                          "decision": "AUTHORIZE_EXPOSED_DEV", "issued_at_utc": "2026-01-01T00:00:00Z"},
        "development_ranges": [{"start_utc": "2026-07-01T00:00:00Z", "end_utc": "2026-07-03T00:00:00Z"}],
        "governance": {"protected_dates_complete": True, "holdout_status": "OWNER_CONFIRMED",
            "protected_date_exclusions": [{"kind": "HOLDOUT", "start_utc": "2026-10-01T00:00:00Z",
                                           "end_utc": "2026-11-01T00:00:00Z"}]},
        "sources": [{"quarter": "Q3", "venue": "binance", "root": str(root),
            "manifest_sha256": hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest(),
            "qc_sha256": hashlib.sha256((root / "qc.json").read_bytes()).hexdigest(),
            "files": [{"path": record["local_path"], "sha256": record["local_sha256"],
                "family": record["family"], "market": record["market"], "symbol": record["symbol"],
                "start_utc": n.iso_us(left), "end_utc": n.iso_us(right)}]}]}
    scope = tmp_path / "owner-scope.json"
    scope.write_text(json.dumps(doc))
    return scope, doc, root, record
