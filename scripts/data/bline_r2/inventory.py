"""Read-only public-source inventory; excludes Forward and protected research."""
from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from pathlib import Path

from .transport import digest

FAMILIES = {"metrics", "klines", "candles", "candle_volume_only", "spot_klines",
    "markPriceKlines", "markPriceKlines_1m", "indexPriceKlines_1m", "premiumIndexKlines_1m",
    "fundingRate", "funding_rates", "candlesticks", "spot_candlesticks", "orderbook",
    "aggTrades", "perp_aggTrades", "spot_aggTrades", "trades"}


def checksum(path: Path, filename: str) -> str | None:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 8192:
        return None
    match = re.fullmatch(r"([a-fA-F0-9]{64})\s+\*?([^\r\n]+)\s*", path.read_text().strip())
    if match and match[2].strip() == filename:
        return match[1].lower()
    return None


def inspect_existing(catalog: Path) -> list[dict]:
    # This URI names the C0 catalog only, never a Forward database.
    if catalog.name != "catalog.sqlite":
        raise ValueError("C0_CATALOG_ONLY")
    conn = sqlite3.connect(catalog.resolve().as_uri()+"?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        selected = [dict(r) for r in conn.execute("""SELECT * FROM source_files
            WHERE exchange IN ('binance','okx','bybit') AND asset IN ('BTC','ETH','MULTI')
            AND product IN ('USD_M_PERPETUAL','SPOT','OKX_SWAP','BYBIT_LINEAR')""")]
    finally:
        conn.close()
    result = []
    for row in selected:
        if row["family"] not in FAMILIES:
            continue
        path = Path(row["path"])
        if path.is_symlink() or not path.is_file():
            row.update(verification="MISSING_OR_UNSAFE")
            result.append(row)
            continue
        stat = path.stat()
        row.update(signature=[stat.st_size,stat.st_mtime_ns,stat.st_ino],filename=path.name,
                   actual_sha256=None, publisher_sha256=checksum(Path(str(path)+".CHECKSUM"),path.name))
        # Rehash small native archives. Large trade archives remain metadata only;
        # never imply their stored manifest SHA was independently checked here.
        if path.suffix == ".zip" and stat.st_size <= 64*1024**2:
            row["actual_sha256"] = digest(path)
            if row["publisher_sha256"]:
                row["verification"] = ("PUBLISHER_SHA256_VERIFIED" if
                    row["actual_sha256"] == row["publisher_sha256"] else "CHECKSUM_MISMATCH")
            elif row["raw_sha256"]:
                row["verification"] = ("MANIFEST_SHA256_VERIFIED_NO_PUBLISHER_SIDECAR" if
                    row["actual_sha256"] == row["raw_sha256"] else "MANIFEST_MISMATCH")
            else:
                row["verification"] = "LOCAL_SHA256_ONLY"
        else:
            row["verification"] = "METADATA_PIN_ONLY_NOT_REHASHED"
        if row["family"] == "metrics" and row.get("interval") == "UNKNOWN":
            row["interval"] = "5m_EXPECTED_NOT_YET_PHYSICALLY_SCANNED"
        result.append(row)
    groups = defaultdict(list)
    for row in result:
        if row.get("actual_sha256"):
            groups[row["actual_sha256"]].append(row)
    for rows in groups.values():
        canonical = min(rows, key=lambda r:(-int(r.get("priority") or 0),r["path"]))["path"]
        for row in rows:
            row.update(deduplicated_canonical_path=canonical, duplicate_archive_alias=row["path"]!=canonical)
    return result


def monthly_inventory(rows: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        period = row.get("period") or "UNKNOWN"
        month = period[:7] if re.match(r"20\d\d-\d\d",period) else "UNKNOWN"
        groups[(row["exchange"],row["asset"],row["product"],row["family"],row["interval"],month)].append(row)
    result = []
    for key, items in sorted(groups.items()):
        result.append(dict(zip(["venue","asset","product","family","granularity","month"],key)) | {
            "files":len(items),"physical_bytes":sum(r.get("bytes") or 0 for r in items),
            "deduplicated_verified_objects":len({r["actual_sha256"] for r in items if r.get("actual_sha256")}),
            "publisher_verified_files":sum(r.get("verification")=="PUBLISHER_SHA256_VERIFIED" for r in items),
            "metadata_only_files":sum(r.get("verification")=="METADATA_PIN_ONLY_NOT_REHASHED" for r in items)})
    return result
