#!/usr/bin/env python3
"""
OKX Historical Data Portal One-File Pilot QC and Acquisition Harness (R11-E2)

Author: Local Codex/Gemini Execution Agent
Contract: V06_R11_E2_OKX_HISTORICAL_PORTAL_ONE_FILE_PILOT_R1
Scope: BTC-USDT-SWAP, 2024-01-15 UTC (+8h portal phase shift noted).
"""

import argparse
import csv
import hashlib
import io
import json
import os
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import zlib
from datetime import UTC, datetime
from pathlib import Path

# --- Constants and Ceilings ---
PRIMARY_INSTRUMENT = "BTC-USDT-SWAP"
INSTRUMENT_FAMILY = "BTC-USDT"
TARGET_DATE = "2024-01-15"
TARGET_MONTH = "2024-01"

# Official Portal Endpoint for Download Link Generation
PORTAL_DOWNLOAD_LINK_API = "https://www.okx.com/priapi/v5/broker/public/trade-data/download-link"
PORTAL_INSTRUMENTS_API = "https://www.okx.com/priapi/v5/broker/public/trade-data/instruments"

# Direct Official CDN Static Archive URLs (as emitted by the Portal API)
OFFICIAL_URLS = {
    "trades": "https://static.okx.com/cdn/okex/traderecords/trades/daily/20240115/BTC-USDT-SWAP-trades-2024-01-15.zip?v=1001",
    "candlesticks": "https://static.okx.com/cdn/okex/traderecords/candlesticks/daily/20240115/BTC-USDT-SWAP-candlesticks-2024-01-15.zip?v=1001",
    "funding_daily": "https://static.okx.com/cdn/okex/traderecords/swaprates/daily/20240115/allswap-fundingrates-2024-01-15.zip?v=1001",
    "funding_monthly": "https://static.okx.com/cdn/okex/traderecords/swaprates/monthly/202401/BTC-USDT-SWAP-fundingrates-2024-01.zip?v=1001",
    "l2_orderbook_400lv": "https://static.okx.com/cdn/okx/match/orderbook/L2/400lv/daily/20240115/BTC-USDT-SWAP-L2orderbook-400lv-2024-01-15.tar.gz"
}

# Verified SHA-256 Checksums of Downloaded Archives
VERIFIED_SHA256 = {
    "trades": "1cb1e8c76a04122d3f2b3d4833c9dc4e684d9a44ce51176e10eafb08aee5e822",
    "candlesticks": "90406dd200d8f3c15c58beac74b57745315967eb5de0a999bb4a935b6d48e9e1",
    "funding_daily": "1ee9c4e60fa028478dec703dab1015c287b2802824521dccc5ae7dbdc84c62f1",
    "funding_monthly": "0b435b9ee300183860c5fd2b471b3eb072142c7200769ab8d6eb37da7616c88d"
}

# Operational Safety Budgets
MAX_COMPRESSED_BYTES = 550 * 1024 * 1024  # 550 MiB ceiling
MAX_EXPANDED_BYTES = 600 * 1024 * 1024    # 600 MiB ceiling
REQUEST_TIMEOUT_SECONDS = 30
MAX_REQUEST_ATTEMPTS = 5

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


class SafetyError(RuntimeError):
    """Raised when a security, bounds, or data integrity invariant is violated."""


def require(condition: bool, code: str):
    if not condition:
        raise SafetyError(code)


class BudgetTracker:
    def __init__(self, compressed_cap=MAX_COMPRESSED_BYTES, expanded_cap=MAX_EXPANDED_BYTES):
        self.compressed_cap = compressed_cap
        self.expanded_cap = expanded_cap
        self.compressed_consumed = 0
        self.expanded_consumed = 0
        self.requests_count = 0

    def consume_compressed(self, n_bytes: int):
        self.compressed_consumed += n_bytes
        require(self.compressed_consumed <= self.compressed_cap, "COMPRESSED_BYTE_CAP_EXCEEDED")

    def consume_expanded(self, n_bytes: int):
        self.expanded_consumed += n_bytes
        require(self.expanded_consumed <= self.expanded_cap, "EXPANDED_BYTE_CAP_EXCEEDED")


def verify_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def qc_trades_rows(reader):
    """
    Validates OKX Trades CSV rows.
    Schema: instrument_name, trade_id, side, price, size, created_time
    """
    header = next(reader)
    expected_header = ["instrument_name", "trade_id", "side", "price", "size", "created_time"]
    require(header == expected_header, f"TRADES_HEADER_MISMATCH: {header}")

    row_count = 0
    min_ts = float("inf")
    max_ts = float("-inf")
    min_id = float("inf")
    max_id = float("-inf")
    prev_id = None
    prev_ts = None
    total_size = 0.0

    for row in reader:
        require(len(row) == 6, f"TRADES_ROW_LENGTH_ERROR: {len(row)}")
        inst, tid_s, side, price_s, sz_s, ts_s = row
        require(inst == PRIMARY_INSTRUMENT, f"UNEXPECTED_INSTRUMENT: {inst}")
        require(side in ("buy", "sell"), f"INVALID_SIDE: {side}")

        tid = int(tid_s)
        price = float(price_s)
        sz = float(sz_s)
        ts = int(ts_s)

        require(price > 0.0, "INVALID_PRICE")
        require(sz > 0.0, "INVALID_SIZE")

        if prev_id is not None:
            require(tid > prev_id, f"TRADE_ID_NOT_STRICTLY_INCREASING: {tid} <= {prev_id}")
        if prev_ts is not None:
            require(ts >= prev_ts, f"TIMESTAMP_DECREASING: {ts} < {prev_ts}")

        row_count += 1
        total_size += sz
        min_ts = min(min_ts, ts)
        max_ts = max(max_ts, ts)
        min_id = min(min_id, tid)
        max_id = max(max_id, tid)

        prev_id = tid
        prev_ts = ts

    return {
        "family": "trades",
        "row_count": row_count,
        "min_trade_id": min_id,
        "max_trade_id": max_id,
        "min_timestamp": min_ts,
        "max_timestamp": max_ts,
        "min_utc": datetime.fromtimestamp(min_ts / 1000.0, tz=UTC).isoformat(),
        "max_utc": datetime.fromtimestamp(max_ts / 1000.0, tz=UTC).isoformat(),
        "total_volume_contracts": total_size,
        "schema": expected_header,
        "trade_id_duplicates": 0,
        "monotonic_trade_id": True,
        "monotonic_timestamp": True
    }


def qc_candlesticks_rows(reader):
    """
    Validates OKX Candlesticks CSV rows.
    Schema: instrument_name, open, high, low, close, vol, vol_ccy, vol_quote, open_time, confirm
    """
    header = next(reader)
    expected_header = ["instrument_name", "open", "high", "low", "close", "vol", "vol_ccy", "vol_quote", "open_time", "confirm"]
    require(header == expected_header, f"CANDLES_HEADER_MISMATCH: {header}")

    row_count = 0
    min_ts = float("inf")
    max_ts = float("-inf")
    prev_ts = None
    total_vol = 0.0
    total_vol_ccy = 0.0
    total_vol_quote = 0.0

    for row in reader:
        require(len(row) == 10, f"CANDLES_ROW_LENGTH_ERROR: {len(row)}")
        inst, o_s, h_s, l_s, c_s, vol_s, vccy_s, vquote_s, ts_s, _conf = row
        require(inst == PRIMARY_INSTRUMENT, f"UNEXPECTED_INSTRUMENT: {inst}")

        o = float(o_s)
        h = float(h_s)
        l = float(l_s)
        c = float(c_s)
        vol = float(vol_s)
        vccy = float(vccy_s)
        vquote = float(vquote_s)
        ts = int(ts_s)

        require(h >= l and h >= o and h >= c and l <= o and l <= c, "OHLC_EXTREMA_VIOLATION")
        if vol > 0.0:
            ratio = vccy / vol
            require(abs(ratio - 0.01) < 1e-6, f"CONTRACT_MULTIPLIER_RATIO_VIOLATION: {ratio}")

        if prev_ts is not None:
            delta = ts - prev_ts
            require(delta == 60000, f"UNEXPECTED_KLINE_INTERVAL: {delta} != 60000ms")

        row_count += 1
        total_vol += vol
        total_vol_ccy += vccy
        total_vol_quote += vquote
        min_ts = min(min_ts, ts)
        max_ts = max(max_ts, ts)
        prev_ts = ts

    return {
        "family": "candlesticks",
        "row_count": row_count,
        "interval_ms": 60000,
        "min_timestamp": min_ts,
        "max_timestamp": max_ts,
        "min_utc": datetime.fromtimestamp(min_ts / 1000.0, tz=UTC).isoformat(),
        "max_utc": datetime.fromtimestamp(max_ts / 1000.0, tz=UTC).isoformat(),
        "total_volume_contracts": total_vol,
        "total_volume_btc": total_vol_ccy,
        "total_volume_quote_usdt": total_vol_quote,
        "observed_contract_multiplier": total_vol_ccy / total_vol if total_vol > 0 else 0.0,
        "schema": expected_header,
        "missing_bars": 1440 - row_count
    }


def qc_funding_rows(reader, filter_instrument=PRIMARY_INSTRUMENT):
    """
    Validates OKX Funding Rate CSV rows.
    Schema: instrument_name, funding_rate, funding_time
    """
    header = next(reader)
    expected_header = ["instrument_name", "funding_rate", "funding_time"]
    require(header == expected_header, f"FUNDING_HEADER_MISMATCH: {header}")

    rows = []
    prev_ts = None
    for row in reader:
        require(len(row) == 3, f"FUNDING_ROW_LENGTH_ERROR: {len(row)}")
        inst, rate_s, ts_s = row
        if filter_instrument and inst != filter_instrument:
            continue
        rate = float(rate_s)
        ts = int(ts_s)
        require(abs(rate) < 0.05, f"EXCESSIVE_FUNDING_RATE: {rate}")
        if prev_ts is not None:
            delta = ts - prev_ts
            require(delta == 28800000, f"UNEXPECTED_FUNDING_INTERVAL: {delta} != 28800000ms")
        rows.append({
            "funding_rate": rate,
            "funding_time": ts,
            "funding_time_utc": datetime.fromtimestamp(ts / 1000.0, tz=UTC).isoformat()
        })
        prev_ts = ts

    return {
        "family": "funding",
        "instrument": filter_instrument,
        "settlement_count": len(rows),
        "settlements": rows
    }


def qc_l2_stream_slice(stream_bytes: bytes):
    """
    Validates a decompressed slice of OKX L2 Order Book match stream.
    Archive contains 512-byte tar header followed by JSONL orderbook lines.
    """
    require(len(stream_bytes) > 512, "L2_STREAM_TOO_SHORT")
    tar_name = stream_bytes[:100].decode("ascii", errors="ignore").strip("\x00")
    require(tar_name.startswith(PRIMARY_INSTRUMENT) and "L2orderbook" in tar_name, f"L2_TAR_NAME_MISMATCH: {tar_name}")

    payload = stream_bytes[512:]
    lines = payload.split(b"\n")
    require(len(lines) >= 2, "INSUFFICIENT_L2_LINES")

    # Line 0 must be full snapshot
    snapshot_obj = json.loads(lines[0].decode("utf-8"))
    require(snapshot_obj.get("instId") == PRIMARY_INSTRUMENT, "L2_SNAPSHOT_INST_MISMATCH")
    require(snapshot_obj.get("action") == "snapshot", "L2_FIRST_LINE_NOT_SNAPSHOT")
    require(len(snapshot_obj.get("asks", [])) == 400, "L2_SNAPSHOT_ASKS_NOT_400")
    require(len(snapshot_obj.get("bids", [])) == 400, "L2_SNAPSHOT_BIDS_NOT_400")

    # Following lines are incremental updates
    updates_inspected = 0
    prev_ts = int(snapshot_obj.get("ts"))
    for l in lines[1:50]:
        if not l.strip():
            continue
        upd = json.loads(l.decode("utf-8"))
        require(upd.get("action") == "update", "L2_UPDATE_ACTION_MISMATCH")
        ts = int(upd.get("ts"))
        require(ts >= prev_ts, "L2_UPDATE_TIMESTAMP_REGRESSION")
        # Check ask/bid 3-tuple format [price, size, order_count]
        for a in upd.get("asks", []):
            require(len(a) == 3, "L2_ASK_TUPLE_LENGTH_ERROR")
        for b in upd.get("bids", []):
            require(len(b) == 3, "L2_BID_TUPLE_LENGTH_ERROR")
        updates_inspected += 1
        prev_ts = ts

    return {
        "family": "l2_orderbook",
        "archive_member_name": tar_name,
        "snapshot_verified": True,
        "snapshot_depth_bids": len(snapshot_obj.get("bids")),
        "snapshot_depth_asks": len(snapshot_obj.get("asks")),
        "snapshot_ts": snapshot_obj.get("ts"),
        "snapshot_utc": datetime.fromtimestamp(int(snapshot_obj.get("ts")) / 1000.0, tz=UTC).isoformat(),
        "incremental_updates_verified": updates_inspected,
        "update_cadence": "10ms_event_stream",
        "tuple_format": ["price", "size_contracts", "order_count"]
    }


def safe_workspace(workspace: Path):
    require(workspace.is_absolute(), "ABSOLUTE_WORKSPACE_REQUIRED")
    for p in (workspace, *workspace.parents):
        require(not p.is_symlink(), "WORKSPACE_SYMLINK_PROHIBITED")
    for subdir in ("data", "reports", "tmp"):
        d = workspace / subdir
        d.mkdir(parents=True, exist_ok=True)
        require(d.is_dir() and not d.is_symlink() and os.access(d, os.W_OK), "SUBDIR_INACCESSIBLE")
    free_bytes = shutil.disk_usage(workspace).free
    require(free_bytes >= 2 * 1024**3, "DISK_BUDGET_INSUFFICIENT")


def download_file(url: str, dest_path: Path, budget: BudgetTracker, chunk_size=65536):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp, dest_path.open("wb") as out:
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            budget.consume_compressed(len(chunk))
            out.write(chunk)


def run_pipeline(workspace: Path, acquire: bool = False):
    safe_workspace(workspace)
    budget = BudgetTracker()
    data_dir = workspace / "data"
    reports_dir = workspace / "reports"
    receipt_file = reports_dir / "okx_portal_pilot_receipt.json"

    records = {}

    # 1. Acquire / Verify Trades
    trades_path = data_dir / "BTC-USDT-SWAP-trades-2024-01-15.zip"
    if acquire and not trades_path.exists():
        download_file(OFFICIAL_URLS["trades"], trades_path, budget)
    require(trades_path.exists(), "TRADES_FILE_MISSING")
    trades_hash = verify_file_sha256(trades_path)
    require(trades_hash == VERIFIED_SHA256["trades"], "TRADES_SHA256_MISMATCH")
    with zipfile.ZipFile(trades_path) as z:
        member = z.infolist()[0]
        budget.consume_expanded(member.file_size)
        with z.open(member) as f, io.TextIOWrapper(f, encoding="utf-8") as text_io:
            trades_qc = qc_trades_rows(csv.reader(text_io))
    trades_qc["sha256"] = trades_hash
    trades_qc["compressed_bytes"] = trades_path.stat().st_size
    trades_qc["expanded_bytes"] = member.file_size
    records["trades"] = trades_qc

    # 2. Acquire / Verify Candlesticks
    candles_path = data_dir / "BTC-USDT-SWAP-candlesticks-2024-01-15.zip"
    if acquire and not candles_path.exists():
        download_file(OFFICIAL_URLS["candlesticks"], candles_path, budget)
    require(candles_path.exists(), "CANDLES_FILE_MISSING")
    candles_hash = verify_file_sha256(candles_path)
    require(candles_hash == VERIFIED_SHA256["candlesticks"], "CANDLES_SHA256_MISMATCH")
    with zipfile.ZipFile(candles_path) as z:
        member = z.infolist()[0]
        budget.consume_expanded(member.file_size)
        with z.open(member) as f, io.TextIOWrapper(f, encoding="utf-8") as text_io:
            candles_qc = qc_candlesticks_rows(csv.reader(text_io))
    candles_qc["sha256"] = candles_hash
    candles_qc["compressed_bytes"] = candles_path.stat().st_size
    candles_qc["expanded_bytes"] = member.file_size
    records["candlesticks"] = candles_qc

    # Volume Reconciliation between Trades and Candlesticks
    vol_diff = abs(trades_qc["total_volume_contracts"] - candles_qc["total_volume_contracts"])
    require(vol_diff == 0.0, f"VOLUME_RECONCILIATION_MISMATCH: {vol_diff}")
    records["volume_reconciliation"] = {
        "trade_sum_contracts": trades_qc["total_volume_contracts"],
        "kline_sum_contracts": candles_qc["total_volume_contracts"],
        "match": True,
        "verified_contract_multiplier": 0.01
    }

    # 3. Acquire / Verify Funding
    funding_daily_path = data_dir / "allswap-fundingrates-2024-01-15.zip"
    if acquire and not funding_daily_path.exists():
        download_file(OFFICIAL_URLS["funding_daily"], funding_daily_path, budget)
    require(funding_daily_path.exists(), "FUNDING_DAILY_FILE_MISSING")
    funding_daily_hash = verify_file_sha256(funding_daily_path)
    require(funding_daily_hash == VERIFIED_SHA256["funding_daily"], "FUNDING_DAILY_SHA256_MISMATCH")
    with zipfile.ZipFile(funding_daily_path) as z:
        member = z.infolist()[0]
        budget.consume_expanded(member.file_size)
        with z.open(member) as f, io.TextIOWrapper(f, encoding="utf-8") as text_io:
            funding_qc = qc_funding_rows(csv.reader(text_io))
    funding_qc["sha256"] = funding_daily_hash
    funding_qc["compressed_bytes"] = funding_daily_path.stat().st_size
    funding_qc["expanded_bytes"] = member.file_size
    records["funding_daily"] = funding_qc

    # 4. Stream and Verify L2 Order Book Slice (Bounded Stream)
    req = urllib.request.Request(OFFICIAL_URLS["l2_orderbook_400lv"], headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
        l2_chunk = resp.read(2 * 1024 * 1024)
        budget.consume_compressed(len(l2_chunk))
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    l2_decompressed = d.decompress(l2_chunk)
    budget.consume_expanded(len(l2_decompressed))
    l2_qc = qc_l2_stream_slice(l2_decompressed)
    records["l2_orderbook"] = l2_qc

    # 5. Open Interest Status Audit
    records["open_interest_audit"] = {
        "status": "OI_PORTAL_UNAVAILABLE / OI_HISTORICAL_UNRESOLVED",
        "advertised_on_portal": False,
        "available_via_portal_api": False,
        "generic_api_download_permitted": False,
        "legal_rights_status": "UNRESOLVED_PENDING_EXPLICIT_SOURCE_GRANT"
    }

    terminal = "R11_E2_OKX_PORTAL_PILOT_ACCEPTED_WITH_LIMITS"
    receipt = {
        "terminal": terminal,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "primary_instrument": PRIMARY_INSTRUMENT,
        "date_analyzed": TARGET_DATE,
        "records": records,
        "compressed_bytes_consumed": budget.compressed_consumed,
        "expanded_bytes_consumed": budget.expanded_consumed
    }

    with receipt_file.open("w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2)

    print(json.dumps({
        "terminal": terminal,
        "trades_rows": trades_qc["row_count"],
        "candles_rows": candles_qc["row_count"],
        "funding_settlements": funding_qc["settlement_count"],
        "l2_snapshot_verified": l2_qc["snapshot_verified"],
        "compressed_bytes": budget.compressed_consumed,
        "expanded_bytes": budget.expanded_consumed
    }, indent=2))

    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("acquire", "verify"))
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    return run_pipeline(args.workspace, acquire=(args.mode == "acquire"))


if __name__ == "__main__":
    sys.exit(main())
