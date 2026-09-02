from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from btc_quant_agent.data.binance_archive import _sha256
from btc_quant_agent.data.binance_market_archive import OFFICIAL_SPECS
from btc_quant_agent.data.official_derivatives_features import OfficialHourlyInputs

START = datetime(2021, 1, 1, tzinfo=UTC)
END = datetime(2026, 2, 1, tzinfo=UTC)
HOUR_MS = 3_600_000
SEGMENT_CONNECTIONS = 8


def _months() -> list[str]:
    output: list[str] = []
    year, month = START.year, START.month
    while (year, month) < (END.year, END.month):
        output.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return output


def _target(root: Path, family: str, month: str) -> Path:
    spec = OFFICIAL_SPECS[family]
    return root / "raw" / family / Path(spec.monthly_url(month)).name


def _official_checksum(url: str) -> str:
    result = subprocess.run(
        [
            "curl",
            "--location",
            "--fail",
            "--silent",
            "--show-error",
            "--retry",
            "10",
            "--retry-all-errors",
            "--max-time",
            "300",
            url + ".CHECKSUM",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise ConnectionError(result.stderr.strip())
    expected = result.stdout.split()[0]
    if len(expected) != 64 or any(character not in "0123456789abcdef" for character in expected):
        raise ValueError("malformed official checksum")
    return expected


def _remote_size(url: str) -> int:
    result = subprocess.run(
        [
            "curl",
            "--head",
            "--location",
            "--fail",
            "--silent",
            "--show-error",
            "--retry",
            "10",
            "--retry-all-errors",
            "--max-time",
            "300",
            url,
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise ConnectionError(result.stderr.strip())
    lengths = [
        int(line.split(":", 1)[1].strip())
        for line in result.stdout.splitlines()
        if line.lower().startswith("content-length:")
    ]
    if not lengths or lengths[-1] <= 0:
        raise ValueError("official archive response omitted content length")
    return lengths[-1]


def _download_segment(url: str, path: Path, start: int, end: int) -> None:
    expected_size = end - start + 1
    current_size = path.stat().st_size if path.exists() else 0
    if current_size > expected_size:
        raise ValueError(f"oversized partial segment: {path}")
    if current_size == expected_size:
        return
    with path.open("ab") as output:
        result = subprocess.run(
            [
                "curl",
                "--location",
                "--fail",
                "--silent",
                "--show-error",
                "--retry",
                "10",
                "--retry-all-errors",
                "--connect-timeout",
                "60",
                "--max-time",
                "3600",
                "--range",
                f"{start + current_size}-{end}",
                url,
            ],
            stdout=output,
            stderr=subprocess.PIPE,
            check=False,
        )
    if result.returncode:
        raise ConnectionError(result.stderr.decode().strip())
    if path.stat().st_size != expected_size:
        raise ValueError(f"official server returned an invalid byte range: {path}")


def _download_resumable(url: str, partial: Path) -> None:
    remote_size = _remote_size(url)
    prefix_size = partial.stat().st_size if partial.exists() else 0
    if prefix_size > remote_size:
        raise ValueError("local partial archive is larger than the official object")
    if prefix_size == remote_size:
        return
    remaining = remote_size - prefix_size
    segment_size = max(1, (remaining + SEGMENT_CONNECTIONS - 1) // SEGMENT_CONNECTIONS)
    segments = [
        (start, min(start + segment_size - 1, remote_size - 1))
        for start in range(prefix_size, remote_size, segment_size)
    ]
    paths = [partial.with_name(f"{partial.name}.{start}-{end}.segment") for start, end in segments]
    with ThreadPoolExecutor(max_workers=SEGMENT_CONNECTIONS) as pool:
        futures = [
            pool.submit(_download_segment, url, path, start, end)
            for path, (start, end) in zip(paths, segments, strict=True)
        ]
        for future in as_completed(futures):
            future.result()
    with partial.open("ab") as output:
        for path in paths:
            with path.open("rb") as source:
                while chunk := source.read(8 * 1024 * 1024):
                    output.write(chunk)
    for path in paths:
        path.unlink()
    if partial.stat().st_size != remote_size:
        raise ValueError("segmented official archive assembly size mismatch")


def _download_one(root: Path, family: str, month: str) -> dict[str, Any]:
    spec = OFFICIAL_SPECS[family]
    url = spec.monthly_url(month)
    target = _target(root, family, month)
    try:
        expected = _official_checksum(url)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or _sha256(target) != expected:
            partial = target.with_suffix(target.suffix + ".part")
            _download_resumable(url, partial)
            if _sha256(partial) != expected:
                raise ValueError("official checksum mismatch after resumable transfer")
            partial.replace(target)
        return {
            "family": family,
            "month": month,
            "url": url,
            "path": str(target),
            "status": "VERIFIED",
            "expected_sha256": expected,
            "local_sha256": _sha256(target),
            "bytes": target.stat().st_size,
        }
    except (
        ConnectionError,
        OSError,
        TimeoutError,
        ValueError,
    ) as exc:
        return {
            "family": family,
            "month": month,
            "url": url,
            "path": str(target),
            "status": "MISSING_OR_UNREACHABLE",
            "error": f"{type(exc).__name__}: {exc}",
        }


KLINE_AWK = r"""
BEGIN { OFS=","; cur=""; rows=0; ms=0; us=0; order=0; last=-1 }
$1 ~ /^[0-9]+$/ {
 raw=$1+0; if(raw>=1000000000000000){ts=int(raw/1000);us++}else{ts=raw;ms++}
 if(last>=0 && ts<=last) order++; last=ts; h=int(ts/3600000)*3600000
 if(cur!="" && h!=cur){print cur,count,close; count=0}
 cur=h; count++; close=$5+0; rows++
}
END { if(cur!="") print cur,count,close; print "#STATS",rows,ms,us,order,last }
"""

AGG_AWK = r"""
BEGIN { OFS=","; cur=""; rows=0; ms=0; us=0; order=0; dup=0; lastid=-1; firstts=-1 }
$1 ~ /^[0-9]+$/ {
 id=$1+0; raw=$6+0; if(raw>=1000000000000000){ts=int(raw/1000);us++}else{ts=raw;ms++}
 if(firstts<0) firstts=ts; if(lastid>=0 && id<lastid) order++; if(id==lastid) dup++; lastid=id
 h=int(ts/3600000)*3600000
 if(cur!="" && h!=cur){print cur,count,buy,sell; count=0;buy=0;sell=0}
 cur=h; notional=($2+0)*($3+0); maker=tolower($7); if(maker=="true")sell+=notional;else buy+=notional
 count++;rows++;lastts=ts
}
END { if(cur!="") print cur,count,buy,sell; print "#STATS",rows,ms,us,order,dup,firstts,lastts }
"""


def _aggregate_archive(record: dict[str, Any]) -> tuple[list[list[str]], dict[str, Any]]:
    family = str(record["family"])
    program = AGG_AWK if "aggTrades" in family else KLINE_AWK
    unzip = subprocess.Popen(
        ["unzip", "-p", str(record["path"])], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    assert unzip.stdout is not None
    awk = subprocess.run(
        ["mawk", "-F,", program],
        stdin=unzip.stdout,
        text=True,
        capture_output=True,
        check=False,
    )
    unzip.stdout.close()
    unzip_stderr = unzip.stderr.read().decode() if unzip.stderr else ""
    unzip_code = unzip.wait()
    if unzip_code or awk.returncode:
        raise RuntimeError(
            f"archive aggregation failed: unzip={unzip_code} {unzip_stderr} awk={awk.stderr}"
        )
    rows = list(csv.reader(awk.stdout.splitlines()))
    stats_row = rows.pop()
    if not stats_row or stats_row[0] != "#STATS":
        raise RuntimeError("archive aggregation did not emit stats")
    if "aggTrades" in family:
        keys = (
            "row_count",
            "millisecond_rows",
            "microsecond_rows",
            "order_errors",
            "duplicate_ids",
            "first_timestamp_ms",
            "last_timestamp_ms",
        )
    else:
        keys = (
            "row_count",
            "millisecond_rows",
            "microsecond_rows",
            "order_errors",
            "last_timestamp_ms",
        )
    stats = {key: int(float(value)) for key, value in zip(keys, stats_row[1:], strict=True)}
    return rows, stats


def build(
    root: Path,
    workers: int,
    selected_families: tuple[str, ...] | None = None,
    download_only: bool = False,
) -> dict[str, Any]:
    all_families = (
        "markPriceKlines_1m",
        "indexPriceKlines_1m",
        "premiumIndexKlines_1m",
        "perp_aggTrades",
        "spot_aggTrades",
        "fundingRate",
    )
    families = selected_families or all_families
    requests = [(family, month) for family in families for month in _months()]
    downloads: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_download_one, root, family, month): (family, month)
            for family, month in requests
        }
        for future in as_completed(futures):
            result = future.result()
            downloads.append(result)
            print(result["status"], result["family"], result["month"], flush=True)
    downloads.sort(key=lambda item: (item["family"], item["month"]))
    verified = [item for item in downloads if item["status"] == "VERIFIED"]
    if download_only:
        return {
            "request_count": len(downloads),
            "verified_count": len(verified),
            "incomplete_count": len(downloads) - len(verified),
        }
    aggregates: dict[str, dict[int, tuple[float, ...]]] = {family: {} for family in families}
    for record in verified:
        family = str(record["family"])
        if family == "fundingRate":
            continue
        rows, stats = _aggregate_archive(record)
        record["audit"] = stats
        for row in rows:
            timestamp = int(float(row[0]))
            if family.endswith("Klines_1m"):
                count = int(row[1])
                aggregates[family][timestamp] = (float(row[2]),) if count == 60 else ()
            else:
                aggregates[family][timestamp] = (float(row[2]), float(row[3]))
        print("AGGREGATED", family, record["month"], stats["row_count"], flush=True)
    start_ms = int(START.timestamp() * 1000)
    end_ms = int(END.timestamp() * 1000)
    inputs: list[OfficialHourlyInputs] = []
    for timestamp in range(start_ms, end_ms, HOUR_MS):
        mark = aggregates["markPriceKlines_1m"].get(timestamp, ())
        index = aggregates["indexPriceKlines_1m"].get(timestamp, ())
        premium = aggregates["premiumIndexKlines_1m"].get(timestamp, ())
        perp = aggregates["perp_aggTrades"].get(timestamp, ())
        spot = aggregates["spot_aggTrades"].get(timestamp, ())
        inputs.append(
            OfficialHourlyInputs(
                timestamp,
                premium[0] if premium else None,
                mark[0] if mark else None,
                index[0] if index else None,
                perp[0] if perp else None,
                perp[1] if perp else None,
                spot[0] if spot else None,
                spot[1] if spot else None,
            )
        )
    hourly_path = root / "hourly_inputs.parquet"
    pq.write_table(
        pa.Table.from_pylist([asdict(row) for row in inputs]), hourly_path, compression="zstd"
    )
    manifest = {
        "dataset_id": "V0319_BTCUSDT_OFFICIAL_DERIVATIVES_20210101_20260201",
        "created_at_ms": int(time.time() * 1000),
        "formal_role": "OFFICIAL_HISTORICAL_TIMESTAMPED",
        "start_ms": start_ms,
        "end_ms_exclusive": end_ms,
        "final_holdout_rows": 0,
        "requests": downloads,
        "request_count": len(downloads),
        "verified_count": len(verified),
        "missing_count": len(downloads) - len(verified),
        "hourly_rows": len(inputs),
        "hourly_input_sha256": _sha256(hourly_path),
        "synthetic_events": 0,
        "gap_fill": 0,
    }
    manifest_path = root / "raw_data_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    return {
        "manifest": str(manifest_path),
        "manifest_sha256": digest,
        **{
            key: manifest[key]
            for key in ("request_count", "verified_count", "missing_count", "hourly_rows")
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--families", nargs="*", choices=tuple(OFFICIAL_SPECS))
    parser.add_argument("--download-only", action="store_true")
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    selected = tuple(args.families) if args.families else None
    print(
        json.dumps(build(args.root.resolve(), args.workers, selected, args.download_only), indent=2)
    )


if __name__ == "__main__":
    main()
