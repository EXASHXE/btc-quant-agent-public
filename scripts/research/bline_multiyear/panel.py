"""Bounded monthly C1/C2 feature adapter; never constructs historical outcomes."""
from __future__ import annotations

import bisect
import calendar
import json
import math
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds

from scripts.data.catalog.flow_query import FlowQueryEngine
from scripts.data.catalog.forward_clock import ClockRecord, evaluate_asof
from scripts.data.catalog.query import CanonicalQueryEngine
from scripts.research.strategy_eval import clocked_dataset as p1

from .contracts import H40, X_NAMES, canonical, excluded, sha, signals

US = 1_000_000
PERP = "USD_M_PERPETUAL"


def stamp(value: datetime) -> int:
    return int(value.timestamp() * US)


def signature(path: Path) -> list[int]:
    s = path.stat()
    return [s.st_size, s.st_mtime_ns, s.st_ino]


class Channel:
    def __init__(self, rows: list[dict], fields: tuple[str, ...], *, event=False):
        key = "event_ts_utc" if event else "interval_start_utc"
        rows = sorted(rows, key=lambda r: r[key])
        self.rows = rows
        self.t = np.array([stamp(r[key]) for r in rows], dtype=np.int64)
        if len(self.t) > 1 and np.any(np.diff(self.t) <= 0):
            raise ValueError("DUPLICATE_OR_UNSORTED_CANONICAL_TIME")
        self.end = np.array([stamp(r["interval_end_utc"]) for r in rows], dtype=np.int64)
        self.values = {f: np.array([np.nan if r.get(f) is None else r[f] for r in rows],
                                   dtype=float) for f in fields}

    def window(self, cutoff: int, count: int, *, flow=False):
        # Exclusive C1 ends: last price bar ends C-1m; flow may end at C.
        last = cutoff * US - (60 if flow else 120) * US
        expected = np.arange(last - (count - 1) * 60 * US, last + 1, 60 * US)
        i = int(np.searchsorted(self.t, expected[0]))
        j = i + count
        if (j > len(self.t) or not np.array_equal(self.t[i:j], expected)
                or np.any(self.end[i:j] != expected + 60 * US)
                or (self.end[j - 1] > cutoff * US if flow else
                    self.end[j - 1] >= cutoff * US)
                or any(r.get("interval") != "1m" for r in self.rows[i:j])
                or any(not np.isfinite(v[i:j]).all() for v in self.values.values())):
            return None
        return slice(i, j)

    def sources(self, sl: slice) -> list[str]:
        return sorted({r["source_id"] for r in self.rows[sl]})


def price_controls(channel: Channel, cutoff: int) -> tuple[list | None, slice | None]:
    sl = channel.window(cutoff, 1441)
    if sl is None:
        return None, None
    v = {k: a[sl] for k, a in channel.values.items()}
    close, high, low = v["close"], v["high"], v["low"]
    base, quote = v["base_volume"], v["quote_volume"]
    if (np.any(close <= 0) or np.any(low <= 0) or np.any(low > close)
            or np.any(high < close) or np.any(high < low)
            or np.any(base < 0) or np.any(quote < 0)):
        return None, None
    bh, bd, qh = base[-60:].sum(), base[-1440:].sum(), quote[-60:].sum()
    rh, rd = high[-60:].max() - low[-60:].min(), high[-1440:].max() - low[-1440:].min()
    if min(bh, bd, qh, rh, rd) <= 0:
        return None, None
    logs = np.log(close)
    returns = np.diff(logs)
    x = [float(logs[-1] - logs[-1-h*60]) for h in (1, 4, 24)]
    x += [float(np.sqrt(np.sum(returns[-60:]**2))), float(np.sqrt(np.sum(returns**2))),
          math.log1p(qh), math.log(bh/(bd/24)),
          float((close[-1]-low[-60:].min())/rh-.5),
          float((close[-1]-low[-1440:].min())/rd-.5), math.log1p(bd)]
    return x, sl


def clock(row: dict, kind: str, stream: str) -> ClockRecord:
    """Native text OI clock retained in panel; C3 checks its parsed UTC event."""
    unit = row.get("source_time_unit")
    native = int(row["source_native_ts"]) if unit in ("s", "ms", "us") else None
    return ClockRecord(
        row["exchange"], row["native_symbol"], row["product_type"], stream, kind,
        row["event_ts_utc"], native, unit if native is not None else None,
        row["source_id"], row["raw_sha256"],
        source_native_clock_role="EVENT_TS" if kind in ("oi", "funding") else "INTERVAL_OPEN",
        interval_open=None if kind in ("oi", "funding") else row["interval_start_utc"],
        interval_close=None if kind in ("oi", "funding") else row["interval_end_utc"],
    )


def clock_check(records: list[ClockRecord], cutoff: int, kind: str, stream: str,
                mode="DESCRIPTIVE_EVENT_TIME", flow_minutes=1) -> dict:
    r = records[0]
    return evaluate_asof(records, origin=datetime.fromtimestamp(cutoff+60, UTC),
                         exchange=r.exchange, instrument=r.instrument, product=r.product,
                         stream=stream, kind=kind, mode=mode, flow_minutes=flow_minutes)


def build_rows(start: int, end: int, channels: dict[str, Channel]) -> list[dict]:
    empty = Channel([], ())
    perp = channels.get("perp", empty)
    stocks_ch = channels.get("oi", empty)
    stocks = {int(t//US): p1.Stock(int(t//US), float(stocks_ch.values["base_open_interest"][i]),
                                  float(stocks_ch.values["top_position_long_short_ratio"][i]))
              for i, t in enumerate(stocks_ch.t)}
    stock_rows = {int(t//US): r for t, r in zip(stocks_ch.t, stocks_ch.rows)}
    times = sorted(stocks)
    funding = channels.get("funding", empty)
    rows = []
    for cutoff in range(start, end, 3600):
        x, sl = price_controls(perp, cutoff)
        row = {"schema": "bline-r1.features.v1", "t": cutoff+60, "cutoff": cutoff,
               "entry_t": cutoff+120, "x": x, "x_complete": x is not None,
               "x_end_us": int(perp.end[sl.stop-1]) if sl else None,
               "x_reason": "READY" if x else "INCOMPLETE_24H_MINUTE_X",
               "receiver_pit": "PIT_UNKNOWN", "action": "NO_ACTION",
               "source_ids": {}, "derivatives": None, "signed_flow": {}}
        if sl:
            row["source_ids"]["X"] = perp.sources(sl)
            rec = clock(perp.rows[sl.stop-1], "bar", "perp")
            row["clock"] = clock_check([rec], cutoff, "bar", "perp")
            row["receiver_gate"] = clock_check([rec], cutoff, "bar", "perp",
                                                mode="RECEIVER_PIT_REQUIRED")["action"]
        z = p1.select_z(stocks, times, cutoff)
        row.update(z)
        if z["z_status"] == "OBSERVED":
            selected = [stock_rows[z["z_t"]], stock_rows[z["z_t"]-14400]]
            row["oi_clock"] = clock_check([clock(r, "oi", "oi") for r in selected], cutoff, "oi", "oi")
            row["oi_native_samples"] = [{k: r[k] for k in ("source_native_ts", "source_time_unit")}
                                         for r in selected]
            row["source_ids"]["OI"] = sorted({r["source_id"] for r in selected})
        slices = {k: channels.get(k, empty).window(cutoff, 300)
                  for k in ("perp", "spot", "mark", "index", "premium")}
        fi = bisect.bisect_left(funding.t, cutoff*US)-1
        if (all(s is not None for s in slices.values()) and fi >= 0
                and 0 < cutoff*US-funding.t[fi] <= 9*3600*US):
            values = {k: channels[k].values["close"][s] for k, s in slices.items()}
            rate = float(funding.values["funding_rate"][fi])
            if (all(np.all(values[k] > 0) for k in ("perp", "spot", "mark", "index"))
                    and math.isfinite(rate)):
                premium = np.log(values["mark"] / values["index"])
                basis = np.log(values["perp"] / values["spot"])
                # Also require observed premium-index contraction, not just mark construction.
                native_premium = values["premium"]
                row["derivatives"] = {
                    "premium_prior4h": float(premium[:-60].mean()),
                    "basis_prior4h": float(basis[:-60].mean()),
                    "premium_change": float(premium[-60:].mean()-premium[:-60].mean()),
                    "basis_change": float(basis[-60:].mean()-basis[:-60].mean()),
                    "native_premium_1h": float(native_premium[-60:].mean()),
                    "funding_rate": rate, "funding_event_us": int(funding.t[fi])}
                for k, s in slices.items():
                    row["source_ids"][k] = channels[k].sources(s)
                row["source_ids"]["funding"] = [funding.rows[fi]["source_id"]]
                row["funding_clock"] = clock_check([clock(funding.rows[fi], "funding", "funding")],
                                                      cutoff, "funding", "funding")
        for market in ("perp", "spot"):
            ch = channels.get("flow_"+market, empty)
            row["signed_flow"][market] = None
            s = ch.window(cutoff, 60, flow=True)
            if s:
                q = ch.values["volume_quote"][s].sum()
                if q > 0:
                    row["signed_flow"][market] = float(ch.values["signed_flow_quote"][s].sum()/q)
                    row["source_ids"]["flow_"+market] = ch.sources(s)
                    row.setdefault("flow_clock", {})[market] = clock_check(
                        [clock(r, "flow", "flow") for r in ch.rows[s]], cutoff, "flow", "flow",
                        flow_minutes=60)
        rows.append(row)
    return rows


class Lake:
    """Use C1/C2 query engines and verify physical materialization receipts."""
    def __init__(self, root: Path):
        self.root = root
        self.c1 = CanonicalQueryEngine(root/"c1/canonical_v1")
        self.c2 = FlowQueryEngine(root/"c2", root/"c1/canonical_v1")
        self.receipts = list(json.loads((root/"c1/source_receipts.json").read_text()).values())
        self.receipts += [json.loads(p.read_text()) for p in sorted((root/"c2/checkpoints").glob("*.json"))]
        self.verified = {}
        self.raw_before = {}
        for r in self.receipts:
            p = Path(r["source_path"])
            self.raw_before[str(p)] = signature(p)
        self.metadata_before = {str(p): sha(p) for p in [root/"c1/source_receipts.json",
                                root/"c1/conflict_resolution.json", *sorted((root/"c2/checkpoints").glob("*.json"))]}

    def load(self, table, venue, asset, product, left, right, fields) -> Channel:
        flow = table == "trade_flow_1m"
        base = (self.root/"c2/minute_flow" if flow else self.root/"c1/canonical_v1"/f"table={table}")
        if not (base/f"exchange={venue}"/f"asset={asset}"/f"product={product}").exists():
            return Channel([], fields)
        common = ["event_ts_utc", "interval_start_utc", "interval_end_utc", "interval",
                  "source_native_ts", "source_time_unit", "source_id", "raw_sha256",
                  "exchange", "native_symbol", "product_type"]
        # Arrow otherwise attempts an optional timezone-module import for every
        # individual UTC scalar in to_pylist(). Project integer microseconds
        # through the EXISTING C1/C2 scanners; reconstruct exact stdlib UTC below.
        time_fields = {"event_ts_utc", "interval_start_utc", "interval_end_utc"}
        projection = {key: pc.field(key).cast(pa.int64()) if key in time_fields else pc.field(key)
                      for key in common+list(fields)}
        if table == "funding_settlements":
            # C1's general query filters interval_start (the accrual start).
            # Funding availability is the native settlement EVENT, so that
            # filter can pull the next month's settlement across a protected
            # boundary. Use the same canonical scanner with an event filter.
            partition = base/f"exchange={venue}"/f"asset={asset}"/f"product={product}"
            dataset = ds.dataset(str(partition), format="parquet", partitioning="hive")
            utc_type = pa.timestamp("us", tz="UTC")
            event_filter = ((pc.field("event_ts_utc") >= pa.scalar(stamp(left), utc_type)) &
                            (pc.field("event_ts_utc") < pa.scalar(stamp(right), utc_type)))
            records = dataset.scanner(columns=projection, filter=event_filter).to_table().to_pylist()
        elif flow:
            records = self.c2.query_flow_range(venue, asset, product, left, right, projection)
        else:
            records = self.c1.query_range(table, venue, asset, product, left, right, projection)
        for row in records:
            for key in time_fields:
                seconds, fraction = divmod(row[key], US)
                row[key] = datetime.fromtimestamp(seconds, UTC)+timedelta(microseconds=fraction)
        pins = {(r["source_id"], r["source_sha256"]): r for r in self.receipts
                if r.get("status") == "SUCCESS" and r.get("table") == table
                and (r["exchange"], r["asset"], r["product"]) == (venue, asset, product)}
        for identity in {(r["source_id"], r["raw_sha256"]) for r in records}:
            if identity not in pins:
                raise ValueError("UNRECEIPTED_CANONICAL_IDENTITY")
            r = pins[identity]
            path = Path(r["partition_path"])
            if str(path) not in self.verified:
                if not path.is_relative_to(self.root) or path.is_symlink():
                    raise ValueError("UNSAFE_CANONICAL_PATH")
                actual = sha(path)
                if actual != r["partition_sha256"]:
                    raise ValueError("CANONICAL_HASH_CHANGED")
                self.verified[str(path)] = {"partition_sha256": actual, "source_id": r["source_id"],
                    "source_sha256": r["source_sha256"], "raw_path": r["source_path"],
                    "signature": signature(path)}
        return Channel(records, fields, event=table == "funding_settlements")

    def month(self, venue, asset, start: datetime, end: datetime):
        left = start-timedelta(days=1, minutes=2)
        # An unprotected origin must not reopen H40 through its warmup.
        # Preserve the scheduled origins and mark incomplete X/Z as unavailable.
        boundary = datetime.fromtimestamp(H40[1], UTC)
        if left < boundary <= start:
            left = boundary
        product = PERP if venue == "binance" else "OKX_SWAP"
        bars = ("close", "high", "low", "base_volume", "quote_volume")
        specs = {"perp": ("bars", product, bars), "spot": ("bars", "SPOT", ("close",)),
                 "mark": ("mark_prices", product, ("close",)),
                 "index": ("index_prices", product, ("close",)),
                 "premium": ("premium_index", product, ("close",)),
                 "funding": ("funding_settlements", product, ("funding_rate",)),
                 "oi": ("position_state", product, ("base_open_interest", "top_position_long_short_ratio")),
                 "flow_perp": ("trade_flow_1m", product, ("volume_quote", "signed_flow_quote")),
                 "flow_spot": ("trade_flow_1m", "SPOT", ("volume_quote", "signed_flow_quote"))}
        channels = {key: self.load(table, venue, asset, prod, left, end, fields)
                    for key, (table, prod, fields) in specs.items()}
        return build_rows(int(start.timestamp()), int(end.timestamp()), channels)

    def verify_unchanged(self) -> dict:
        raw_changed = [p for p, s in self.raw_before.items() if signature(Path(p)) != s]
        changed = [p for p, h in self.metadata_before.items() if sha(Path(p)) != h]
        changed += [p for p, r in self.verified.items() if sha(Path(p)) != r["partition_sha256"]]
        if raw_changed or changed:
            raise ValueError("SOURCE_CHANGED")
        return {"raw_sources_stat_unchanged": len(self.raw_before),
                "raw_hash_verification": "C1/C2 receipt SHA lineage; raw payloads not reopened",
                "canonical_partitions_rehashed": len(self.verified),
                "metadata_rehashed": len(self.metadata_before), "changed": []}


def coverage(lake: Lake, output: Path, start: datetime, end: datetime) -> dict:
    matrix, examples, counts = [], [], Counter()
    source_groups = sorted({(r["exchange"], r["asset"]) for r in lake.receipts})
    with (output/"feature_panel.jsonl").open("xb") as stream:
        month = start
        while month < end:
            days = calendar.monthrange(month.year, month.month)[1]
            stop = min(month+timedelta(days=days), end)
            for venue, asset in source_groups:
                available = [r for r in lake.receipts if (r["exchange"], r["asset"]) == (venue, asset)
                             and r.get("period", r.get("month", ""))[:7] == month.strftime("%Y-%m")]
                # No payload/feature construction on known protected months. Metadata retained.
                protected = excluded(int(month.timestamp()), int(stop.timestamp()))
                rows = [] if protected or not available else lake.month(venue, asset, month, stop)
                n = int((stop-month).total_seconds()/3600)
                cell = {"venue": venue, "asset": asset, "month": month.strftime("%Y-%m"),
                        "scheduled_origins": n, "feature_only_origins": len(rows),
                        "feature_status": "KNOWN_PROTECTED_METADATA_ONLY" if protected else "FEATURE_ONLY",
                        "native_partitions": len(available), "native_rows": sum(r.get("row_count", r.get("minute_rows", 0)) for r in available),
                        "flow_native_rows": sum(r.get("minute_rows", 0) for r in available),
                        "X_eligible": sum(r["x_complete"] for r in rows),
                        "funding_premium_eligible": sum(r["x_complete"] and r["derivatives"] is not None for r in rows),
                        "OI_eligible": sum(p1.ready(r)[1] for r in rows),
                        "flow_paired_eligible": sum(all(v is not None for v in r["signed_flow"].values()) for r in rows),
                        "receiver_pit": "PIT_UNKNOWN", "live_actionable": 0,
                        "historical_outcomes_evaluated": 0}
                for candidate in ("FUNDING_PREMIUM_RELEASE", "OI_DELEVERAGING_CONTINUATION"):
                    for row in rows:
                        row.update(venue=venue, asset=asset, data_kind="HISTORICAL_FEATURE_ONLY")
                    policies = [signals(r, candidate) for r in rows]
                    cell[candidate] = {"paired_eligible": sum(p[2] for p in policies),
                                       "X_signal": sum(bool(p[0]) for p in policies),
                                       "XZ_signal": sum(bool(p[1]) for p in policies),
                                       "scheduled_no_signal": n-sum(bool(p[1]) for p in policies)}
                cell["X_gap_or_unavailable"] = n-cell["X_eligible"]
                cell["NO_ACTION"] = n
                matrix.append(cell)
                for row in rows:
                    row.update(venue=venue, asset=asset, x_names=X_NAMES)
                    stream.write(canonical(row))
                if rows:
                    for predicate in (lambda r: r["x_complete"], lambda r: r["derivatives"] is not None,
                                      lambda r: r["z_status"] == "OBSERVED",
                                      lambda r: r["signed_flow"].get("perp") is not None):
                        example = next((r for r in rows if predicate(r)), None)
                        if example:
                            examples.append(example)
                counts.update(scheduled=n, feature_origins=len(rows), X_eligible=cell["X_eligible"])
            month = stop
    integrity = lake.verify_unchanged()
    return {"matrix": matrix, "examples": examples, "counts": dict(counts),
            "integrity": integrity, "lineage": lake.verified,
            "real_outcome_labels_read": 0}
