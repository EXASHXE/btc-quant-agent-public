"""Bounded manifest/Parquet-footer inventory; never opens Forward database rows."""

from __future__ import annotations

import calendar
import hashlib
import json
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def month_window(period: str) -> tuple[str, str]:
    year, month = map(int, period.split("-"))
    a = datetime(year, month, 1, tzinfo=UTC)
    b = datetime(year + month // 12, month % 12 + 1, 1, tzinfo=UTC)
    return a.isoformat(), b.isoformat()


def iso_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, UTC).isoformat()


def record(path: Path, **fields: Any) -> dict[str, Any]:
    st = path.lstat() if path.exists() else None
    return {"source_id": hashlib.sha256(str(path).encode()).hexdigest()[:24],
            "path": str(path), "bytes": st.st_size if st and path.is_file() else None,
            "mtime_ns": st.st_mtime_ns if st else None, "exists": bool(st and path.is_file()),
            "raw_sha256": None, "manifest_sha256": None, "rows": None,
            "gaps": None, "duplicates": None, "start_utc": None, "end_utc_exclusive": None,
            "receiver_pit": "UNKNOWN", "study_scope": "HISTORICAL_OFFLINE_METADATA_ONLY",
            "qa_level": "UNKNOWN", "priority": 0, "calendar_timezone": "UTC",
            "schema_fields": [], **fields}


def _parquet_footer(path: Path) -> tuple[int, list[str], str | None, str | None]:
    pf = pq.ParquetFile(path)
    schema = pf.schema_arrow.names
    col = "open_time_ms" if "open_time_ms" in schema else None
    if col and pf.metadata.num_row_groups:
        mins, maxs = [], []
        for i in range(pf.metadata.num_row_groups):
            rg = pf.metadata.row_group(i)
            column = rg.column(schema.index(col))
            stats = column.statistics
            if stats and stats.has_min_max:
                mins.append(int(stats.min)); maxs.append(int(stats.max))
        if mins:
            step = 3600000 if "1h" in str(path) else 60000
            return pf.metadata.num_rows, schema, iso_ms(min(mins)), iso_ms(max(maxs) + step)
    return pf.metadata.num_rows, schema, None, None


def original_research(root: Path) -> list[dict[str, Any]]:
    result = []
    for directory, product in (("BTCUSDT", "USD_M_PERPETUAL"), ("BTCUSDT_SPOT", "SPOT")):
        base = root / directory
        manifest = base / "data_manifest.json"
        if not manifest.is_file():
            continue
        data = json.loads(manifest.read_bytes())
        manifest_sha = digest(manifest)
        for rel, pinned in sorted(data.get("partition_checksums", {}).items()):
            path = base / rel
            if not path.is_file() or path.is_symlink():
                result.append(record(path, exchange="binance", symbol="BTCUSDT", asset="BTC",
                    product=product, family="candles", interval="1m", period="-".join(re.findall(r"(?:year|month)=(\d+)", rel)),
                    qa_level="MISSING_OR_UNSAFE", manifest_sha256=manifest_sha, raw_sha256=pinned, priority=90))
                continue
            rows, fields, start, end = _parquet_footer(path)
            year, month = re.findall(r"(?:year|month)=(\d+)", rel)
            period = f"{year}-{month}"
            if start is None:
                start, end = month_window(period)
            expected = calendar.monthrange(int(year), int(month))[1] * 1440
            result.append(record(path, exchange="binance", symbol="BTCUSDT", asset="BTC",
                product=product, family="candles" if "open" in fields else "candle_volume_only",
                interval="1m", period=period, start_utc=start, end_utc_exclusive=end,
                rows=rows, gaps=max(expected - rows, 0), duplicates=0 if data.get("duplicate_count") == 0 else None,
                raw_sha256=pinned, manifest_sha256=manifest_sha,
                qa_level="MANIFEST_PINNED_FOOTER_READ_RAW_NOT_REHASHED", priority=90,
                schema_fields=fields))
    derivatives = root / "v0.3.19_official_derivatives"
    manifest = derivatives / "raw_data_manifest.json"
    if manifest.is_file():
        doc = json.loads(manifest.read_bytes()); msha = digest(manifest)
        for item in doc.get("requests", []):
            path = Path(item["path"])
            family = item.get("family", "UNKNOWN")
            start, end = month_window(item["month"])
            result.append(record(path, exchange="binance", symbol="BTCUSDT", asset="BTC",
                product="SPOT" if family.startswith("spot_") else "USD_M_PERPETUAL",
                family=family, interval="1m" if "Klines" in family else "EVENT",
                period=item["month"], start_utc=start, end_utc_exclusive=end,
                raw_sha256=item.get("local_sha256"), manifest_sha256=msha,
                qa_level="MANIFEST_VERIFIED_RAW_NOT_REHASHED" if item.get("status") == "VERIFIED" else item.get("status", "UNKNOWN"),
                priority=70, study_scope="DERIVATIVES_RAW_NO_OUTCOME_LABEL_READ"))
        hourly = derivatives / "hourly_inputs.parquet"
        if hourly.is_file():
            rows, fields, _, _ = _parquet_footer(hourly)
            result.append(record(hourly, exchange="binance", symbol="BTCUSDT", asset="BTC",
                product="USD_M_PERPETUAL", family="derived_hourly_inputs", interval="1h",
                period="2021-01..2026-01", rows=rows, schema_fields=fields,
                raw_sha256=doc.get("hourly_input_sha256"), manifest_sha256=msha,
                qa_level="DERIVED_RESEARCH_NOT_EXCHANGE_NATIVE", priority=10,
                study_scope="DERIVED_RESEARCH_METADATA_ONLY"))
    basket = root / "cross_asset_1h"
    manifest = basket / "basket_manifest.json"
    if manifest.is_file():
        data = json.loads(manifest.read_bytes()); msha = digest(manifest)
        for symbol, info in sorted(data.get("symbols", {}).items()):
            path = basket / f"{symbol}.parquet"
            if path.is_file():
                rows, fields, start, end = _parquet_footer(path)
                result.append(record(path, exchange="binance", symbol=symbol, asset=symbol.removesuffix("USDT"),
                    product="USD_M_PERPETUAL", family="candles", interval="1h",
                    period="2021-01..2026-01", rows=rows, gaps=info.get("missing_count"),
                    duplicates=info.get("duplicates"), start_utc=start, end_utc_exclusive=end,
                    raw_sha256=info.get("parquet_sha256"), manifest_sha256=msha,
                    qa_level="MANIFEST_PINNED_FOOTER_READ_RAW_NOT_REHASHED", priority=85,
                    schema_fields=fields))
            for archive in sorted((basket / "raw" / symbol).glob("*.zip")):
                match = re.search(r"(20\d\d-\d\d)\.zip$", archive.name)
                if match:
                    start, end = month_window(match.group(1))
                    result.append(record(archive, exchange="binance", symbol=symbol,
                        asset=symbol.removesuffix("USDT"), product="USD_M_PERPETUAL",
                        family="candles", interval="1h", period=match.group(1),
                        start_utc=start, end_utc_exclusive=end, manifest_sha256=msha,
                        qa_level="ARCHIVE_METADATA_ONLY", priority=65))
    # Derived funding is visible as metadata only, never treated as native settlement records.
    derived = root / "BTCUSDT" / "funding_events.csv"
    if derived.is_file():
        result.append(record(derived, exchange="binance", symbol="BTCUSDT", asset="BTC",
            product="USD_M_PERPETUAL", family="derived_funding_events", interval="EVENT",
            period="UNKNOWN", qa_level="DERIVED_RESEARCH_NOT_EXCHANGE_NATIVE", priority=5,
            study_scope="DERIVED_RESEARCH_METADATA_ONLY"))
    return result


def expansion(root: Path, name: str) -> list[dict[str, Any]]:
    manifest, qc = root / "manifest.json", root / "qc.json"
    if not manifest.is_file() or not qc.is_file():
        return []
    data, checks = json.loads(manifest.read_bytes()), json.loads(qc.read_bytes())
    msha, qsha = digest(manifest), digest(qc)
    qa = {r["local_path"]: r for r in checks.get("qc_records", [])}
    venue = "okx" if name.startswith("okx") else "binance"
    result = []
    for item in data.get("records", []):
        rel = item.get("local_path")
        if not isinstance(rel, str) or rel.startswith("/") or ".." in Path(rel).parts:
            continue
        path = root / rel
        qc_row = qa.get(rel, {})
        family = item.get("family", "UNKNOWN")
        symbol = item.get("symbol", "UNKNOWN")
        asset = "BTC" if symbol.startswith("BTC") else "ETH" if symbol.startswith("ETH") else "MULTI"
        product = ("SPOT" if "spot" in family.lower() else "OKX_SWAP" if venue == "okx"
                   else "USD_M_PERPETUAL")
        start = qc_row.get("start_utc") or item.get("start_utc")
        end = qc_row.get("end_utc") or item.get("end_utc")
        interval = item.get("interval", "EVENT")
        if end and interval in ("1m", "5m", "1h"):
            try:
                end = (datetime.fromisoformat(end.replace("Z", "+00:00")) +
                       timedelta(seconds={"1m": 60, "5m": 300, "1h": 3600}[interval])).isoformat()
            except ValueError:
                end = None
        result.append(record(path, exchange=venue, symbol=symbol, asset=asset, product=product,
            family=family, interval=interval, period=item.get("period", "UNKNOWN"),
            calendar_timezone="Asia/Shanghai" if venue == "okx" else "UTC",
            start_utc=start, end_utc_exclusive=end, rows=qc_row.get("rows", item.get("rows")),
            gaps=qc_row.get("gaps"), duplicates=qc_row.get("duplicates"),
            raw_sha256=item.get("local_sha256"), manifest_sha256=msha, qc_sha256=qsha,
            qa_level="PASS_MANIFEST_QC_PINNED_RAW_NOT_REHASHED" if item.get("verdict") == qc_row.get("verdict") == "PASS" and path.is_file() else
                     "OBJECT_NOT_FOUND_OR_NONPASS", priority=100 if venue == "okx" or name.endswith("2026q2") or name.endswith("expansion") else 30,
            study_scope="HISTORICAL_OFFLINE_SOURCE_NOT_ADMITTED"))
    return result


def pilots(root: Path) -> list[dict[str, Any]]:
    result = []
    for name in ("r10-binance-vision", "r11-binance-core-pilot"):
        base = root / name
        if not base.is_dir():
            continue
        for path in sorted(base.glob("data/**/*.zip")):
            namepart = path.name
            period = next(iter(re.findall(r"20\d\d-\d\d(?:-\d\d)?", namepart)), "UNKNOWN")
            family = path.parent.name
            symbol = "BTCUSDT" if "BTC" in namepart else "ETHUSDT" if "ETH" in namepart else "UNKNOWN"
            result.append(record(path, exchange="binance", symbol=symbol,
                asset=symbol.removesuffix("USDT"), product="USD_M_PERPETUAL",
                family=family, interval="UNKNOWN", period=period,
                qa_level="PILOT_METADATA_DUPLICATE_CANDIDATE", priority=20,
                study_scope="HISTORICAL_OFFLINE_SOURCE_NOT_ADMITTED"))
    return result


def forward_metadata(root: Path) -> list[dict[str, Any]]:
    result = []
    if not root.is_dir():
        return result
    paths = list(root.iterdir()) + list((root / "microstructure").iterdir()) if (root / "microstructure").is_dir() else list(root.iterdir())
    today = datetime.now(UTC).date().isoformat()
    for path in sorted(paths):
        if not path.is_file() or path.is_symlink():
            continue
        match = re.search(r"(20\d\d-\d\d-\d\d)", path.name)
        period = match.group(1) if match else "UNKNOWN"
        wal = path.with_name(path.name + "-wal")
        wal_bytes = wal.stat().st_size if path.suffix == ".sqlite3" and wal.is_file() else None
        state = ("ACTIVE_WRITER_CANDIDATE" if (period != "UNKNOWN" and period >= today) or (wal_bytes or 0) > 0 else
                 "PAST_DATED_CLOSED_UNVERIFIED" if period != "UNKNOWN" else "UNPARTITIONED_ACTIVE_UNKNOWN")
        result.append(record(path, exchange="binance", symbol="BTCUSDT", asset="BTC",
            product="FORWARD_PROTECTED", family="microstructure_db_metadata" if path.suffix.startswith(".sqlite")
            else "forward_file_metadata", interval="UNKNOWN", period=period,
            qa_level="STAT_ONLY_NO_DB_ATTACH_OR_ROW_READ", priority=-1,
            study_scope="FORWARD_PROTECTED_METADATA_ONLY", forward_state=state,
            attached_wal_bytes=wal_bytes))
    return result


def protected_research_metadata(root: Path) -> list[dict[str, Any]]:
    """Stat only: never open H39 ledgers or older potentially reserved samples."""
    result = []
    for name in ("h39_validation", "v0.3.18_official_samples"):
        base = root / name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            match = re.search(r"(20\d\d-\d\d(?:-\d\d)?)", path.name)
            result.append(record(path, exchange="binance", symbol="BTCUSDT", asset="BTC",
                product="PROTECTED_RESEARCH", family="protected_metadata",
                interval="UNKNOWN", period=match.group(1) if match else "UNKNOWN",
                qa_level="STAT_ONLY_PROTECTED_NO_ROW_READ", priority=-1,
                study_scope="PROTECTED_RESEARCH_METADATA_ONLY"))
    return result


def inventory(original: Path, historical: Path, forward: Path) -> list[dict[str, Any]]:
    rows = original_research(original)
    rows.extend(protected_research_metadata(original))
    for name in ("binance-usdm-2026q2", "binance-usdm-expansion", "okx-swap-2026q2", "okx-swap-expansion"):
        rows.extend(expansion(historical / name, name))
    rows.extend(pilots(historical))
    rows.extend(forward_metadata(forward))
    return sorted(rows, key=lambda r: r["path"])


def coverage(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for row in rows:
        key = tuple(str(row.get(k, "UNKNOWN")) for k in
                    ("exchange", "asset", "product", "family", "interval")) + (row["period"][:7],)
        groups.setdefault(key, []).append(row)
    result = []
    for key, group in sorted(groups.items()):
        selected = [r for r in group if r["priority"] == max(x["priority"] for x in group)]
        starts = [r["start_utc"] for r in group if r["start_utc"]]
        ends = [r["end_utc_exclusive"] for r in group if r["end_utc_exclusive"]]
        result.append(dict(zip(("exchange", "asset", "product", "family", "interval", "calendar_month"), key)) |
            {"source_files": len(group), "preferred_source_ids": [r["source_id"] for r in selected],
             "physical_rows_sum": sum(r["rows"] for r in group if isinstance(r["rows"], int)),
             "reported_gaps_sum": sum(r["gaps"] for r in group if isinstance(r["gaps"], int)),
             "utc_start_min": min(starts) if starts else None, "utc_end_max_exclusive": max(ends) if ends else None,
             "qa_levels": sorted(set(r["qa_level"] for r in group)),
             "overlap_or_duplicate_candidate": len({r["priority"] for r in group}) > 1})
    return result


def issues(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        if row["qa_level"] == "OBJECT_NOT_FOUND_OR_NONPASS" or not row["exists"]:
            result.append({"source_id": row["source_id"], "kind": "NONPASS_OR_MISSING", "path": row["path"]})
        if isinstance(row["gaps"], int) and row["gaps"] > 0:
            result.append({"source_id": row["source_id"], "kind": "REPORTED_GAPS", "count": row["gaps"], "path": row["path"]})
        if row["family"] == "candle_volume_only":
            result.append({"source_id": row["source_id"], "kind": "PRICE_COLUMNS_ABSENT", "path": row["path"]})
    return result
