from __future__ import annotations

import asyncio
import bisect
import hashlib
import json
import sqlite3
import subprocess
import threading
import time
import uuid
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from typing import Any, TypeVar

from .config import DataConfig
from .data.binance import BinancePublicClient
from .publication import (
    PublicationConflict,
    PublicationUncertain,
    file_digest,
    publication_lock,
    publish_bytes,
)
from .sqlite_schema import MICROSTRUCTURE_TABLES, finish_schema, prepare_schema, projection

_T = TypeVar("_T")


def _owned_mutation(method: Callable[..., _T]) -> Callable[..., _T]:
    @wraps(method)
    def owned(self: MicrostructureStore, *args: Any, **kwargs: Any) -> _T:
        with publication_lock(self.finalized_manifest_path):
            if file_digest(self.finalized_manifest_path) != self._manifest_digest:
                raise PublicationConflict("stale microstructure manifest owner")
            # Validate every mutable partition before any cross-partition write
            # or checkpoint. Sealed partitions are never migrated by a writer.
            for path in self.root.glob("microstructure-*.sqlite3"):
                if self._is_finalized(path):
                    continue
                try:
                    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
                except sqlite3.OperationalError:
                    # Heartbeats are advisory and historically skip locked DBs;
                    # unavailable is not a schema success or a committed write.
                    if method.__name__ != "heartbeat":
                        raise
                    continue
                try:
                    prepare_schema(connection, MICROSTRUCTURE_TABLES,
                                   legacy_optional=("sessions.instance_id", "sessions.last_heartbeat_ms"))
                finally:
                    connection.close()
            try:
                return method(self, *args, **kwargs)
            except PublicationUncertain:
                self._manifest_digest = file_digest(self.finalized_manifest_path)
                raise
    return owned


def microstructure_service_status() -> dict[str, Any]:
    unit = "btc-quant-microstructure-forward.service"
    try:
        active = subprocess.run(
            ["systemctl", "--user", "is-active", unit],
            capture_output=True,
            check=False,
            timeout=5,
        ).returncode == 0
        return {"unit": unit, "detected": True, "active": active}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"unit": unit, "detected": False, "active": False, "error": str(exc)}


class SequenceGap(RuntimeError):
    pass


@dataclass(frozen=True)
class MicrostructureCampaign:
    campaign_id: str
    symbol: str
    start_ms: int
    depth_url: str
    trade_url: str

    @classmethod
    def load(cls, path: str | Path) -> MicrostructureCampaign:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if (
            raw["direction_claim"] != "NONE"
            or raw["alpha_claim"] != "NONE"
            or raw["runtime_integration"] != "DISABLED"
            or raw["execution_integration"] != "DISABLED"
            or raw["final_holdout_access"]
            or raw["retrospective_evidence_backfill"]
        ):
            raise ValueError("microstructure safety firewall violated")
        return cls(
            str(raw["campaign_id"]),
            str(raw["symbol"]),
            int(raw["capture_start_ms"]),
            str(raw["source_streams"]["diff_depth"]),
            str(raw["source_streams"]["aggregate_trade"]),
        )


@dataclass(frozen=True)
class MicrostructureReliabilityProtocol:
    protocol_id: str
    heartbeat_interval_ms: int
    lease_timeout_ms: int
    minimum_trade_coverage: float
    minimum_depth_coverage: float
    minimum_depth_valid_coverage: float
    clock_interval_ms: int
    maximum_clock_rtt_ms: int
    finalization_grace_ms: int

    @classmethod
    def load(cls, path: str | Path) -> MicrostructureReliabilityProtocol:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        coverage = raw["coverage"]
        clock = raw["clock"]
        finalization = raw["partition_finalization"]
        protocol = cls(
            protocol_id=str(raw["protocol_id"]),
            heartbeat_interval_ms=int(raw["heartbeat_interval_seconds"]) * 1_000,
            lease_timeout_ms=int(raw["lease_timeout_seconds"]) * 1_000,
            minimum_trade_coverage=float(coverage["minimum_trade_stream_coverage_ratio"]),
            minimum_depth_coverage=float(coverage["minimum_depth_stream_coverage_ratio"]),
            minimum_depth_valid_coverage=float(
                coverage["minimum_depth_sequence_valid_ratio"]
            ),
            clock_interval_ms=int(clock["measurement_interval_seconds"]) * 1_000,
            maximum_clock_rtt_ms=int(clock["maximum_acceptable_rtt_ms"]),
            finalization_grace_ms=int(finalization["grace_after_utc_midnight_seconds"])
            * 1_000,
        )
        if (
            protocol.heartbeat_interval_ms <= 0
            or protocol.lease_timeout_ms < 2 * protocol.heartbeat_interval_ms
            or not 0 < protocol.minimum_trade_coverage <= 1
            or not 0 < protocol.minimum_depth_coverage <= 1
            or not 0 < protocol.minimum_depth_valid_coverage <= 1
            or raw["direction_claim"] != "NONE"
            or raw["alpha_claim"] != "NONE"
            or raw["execution"] != "DISABLED"
            or raw["final_holdout_access"]
        ):
            raise ValueError("microstructure reliability protocol violates frozen gates")
        return protocol


@dataclass(frozen=True)
class DepthEvent:
    event_time_ms: int
    transaction_time_ms: int | None
    first_update_id: int
    final_update_id: int
    previous_final_update_id: int
    bids: tuple[tuple[float, float], ...]
    asks: tuple[tuple[float, float], ...]
    receive_time_ms: int
    receive_monotonic_ns: int

    @classmethod
    def parse(cls, raw: dict[str, Any], receive_ms: int, monotonic_ns: int) -> DepthEvent:
        return cls(
            int(raw["E"]),
            int(raw["T"]) if raw.get("T") is not None else None,
            int(raw["U"]),
            int(raw["u"]),
            int(raw["pu"]),
            tuple((float(p), float(q)) for p, q in raw["b"]),
            tuple((float(p), float(q)) for p, q in raw["a"]),
            receive_ms,
            monotonic_ns,
        )


@dataclass(frozen=True)
class AggTrade:
    event_time_ms: int
    aggregate_trade_id: int
    price: float
    quantity: float
    buyer_is_maker: bool
    aggressive_side: str
    transaction_time_ms: int | None
    receive_time_ms: int
    receive_monotonic_ns: int

    @classmethod
    def parse(cls, raw: dict[str, Any], receive_ms: int, monotonic_ns: int) -> AggTrade:
        buyer_is_maker = bool(raw["m"])
        return cls(
            int(raw["E"]),
            int(raw["a"]),
            float(raw["p"]),
            float(raw["q"]),
            buyer_is_maker,
            "SELL" if buyer_is_maker else "BUY",
            int(raw["T"]) if raw.get("T") is not None else None,
            receive_ms,
            monotonic_ns,
        )


class LocalOrderBook:
    def __init__(self) -> None:
        self.bids: dict[float, float] = {}
        self.asks: dict[float, float] = {}
        self.update_id: int | None = None

    def reset(self) -> None:
        self.bids.clear()
        self.asks.clear()
        self.update_id = None

    def bootstrap(self, snapshot: dict[str, Any], buffered: Iterable[DepthEvent]) -> int:
        last = int(snapshot["lastUpdateId"])
        events = [event for event in buffered if event.final_update_id >= last]
        if not events or not (events[0].first_update_id <= last <= events[0].final_update_id):
            raise SequenceGap("no diff event bridges REST snapshot")
        self.bids = {float(p): float(q) for p, q in snapshot["bids"] if float(q)}
        self.asks = {float(p): float(q) for p, q in snapshot["asks"] if float(q)}
        self.update_id = last
        self._apply_levels(events[0])
        applied = 1
        for event in events[1:]:
            applied += int(self.apply(event))
        return applied

    def _apply_levels(self, event: DepthEvent) -> None:
        for book, updates in ((self.bids, event.bids), (self.asks, event.asks)):
            for price, quantity in updates:
                if quantity == 0:
                    book.pop(price, None)
                else:
                    book[price] = quantity
        self.update_id = event.final_update_id

    def apply(self, event: DepthEvent) -> bool:
        if self.update_id is None:
            raise SequenceGap("book not bootstrapped")
        if event.final_update_id <= self.update_id:
            return False
        if event.previous_final_update_id != self.update_id:
            self.reset()
            raise SequenceGap("pu continuity failure")
        self._apply_levels(event)
        return True

    def stats(self) -> dict[str, float | None]:
        if not self.bids or not self.asks:
            return {
                "spread_bps": None,
                "top1_imbalance": None,
                "top5_imbalance": None,
                "top20_imbalance": None,
                "microprice": None,
            }
        bid, ask = max(self.bids), min(self.asks)
        bq, aq = self.bids[bid], self.asks[ask]
        total, mid = bq + aq, (bid + ask) / 2
        bid_prices = sorted(self.bids, reverse=True)
        ask_prices = sorted(self.asks)

        def imbalance(levels: int) -> float | None:
            bid_quantity = sum(self.bids[price] for price in bid_prices[:levels])
            ask_quantity = sum(self.asks[price] for price in ask_prices[:levels])
            quantity = bid_quantity + ask_quantity
            return (bid_quantity - ask_quantity) / quantity if quantity else None

        return {
            "spread_bps": (ask - bid) / mid * 10_000,
            "top1_imbalance": imbalance(1),
            "top5_imbalance": imbalance(5),
            "top20_imbalance": imbalance(20),
            "microprice": (ask * bq + bid * aq) / total if total else None,
        }

    def best(self) -> tuple[float, float, float, float] | None:
        if not self.bids or not self.asks:
            return None
        bid, ask = max(self.bids), min(self.asks)
        return bid, self.bids[bid], ask, self.asks[ask]


def event_ofi(
    previous: tuple[float, float, float, float], current: tuple[float, float, float, float]
) -> float:
    """Best-level event OFI: bid-side contribution minus ask-side contribution."""
    pb, qb, pa, qa = previous
    cb, cqb, ca, cqa = current
    bid = (cqb if cb >= pb else 0.0) - (qb if cb <= pb else 0.0)
    ask = (qa if ca >= pa else 0.0) - (cqa if ca <= pa else 0.0)
    return bid + ask


def _streaming_sha256(path: Path | str, chunk_size: int = 2 * 1024 * 1024) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


MAX_PARTITION_STATS_CACHE_BYTES = 128 * 1024 * 1024  # 128 MiB
STATS_CACHE_SCHEMA_VERSION = "3.0.0"


class MicrostructureStore:
    INTERVALS_MS = (1_000, 60_000, 900_000)
    MAX_PARTITION_STATS_CACHE_BYTES = MAX_PARTITION_STATS_CACHE_BYTES
    STATS_CACHE_SCHEMA_VERSION = STATS_CACHE_SCHEMA_VERSION

    def __init__(
        self,
        root: str | Path,
        campaign_id: str,
        start_ms: int,
        protocol_path: str
        | Path = "configs/forward/v0.3.16_microstructure_reliability_protocol.json",
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.campaign_id = campaign_id
        self.start_ms = start_ms
        self.protocol = MicrostructureReliabilityProtocol.load(protocol_path)
        self._finalized_cache: dict[str, dict[str, Any]] = {}
        self._manifest_digest = file_digest(self.finalized_manifest_path)

    @property
    def finalized_manifest_path(self) -> Path:
        return self.root / "finalized-partitions.v0316.sha256.json"

    @property
    def _stats_cache_path(self) -> Path:
        return self.root / ".partition_stats_cache.json"

    @staticmethod
    def _partition_day_bounds(path: Path) -> tuple[int, int]:
        try:
            day_str = path.stem.removeprefix("microstructure-")
            day_dt = datetime.strptime(day_str, "%Y-%m-%d").replace(tzinfo=UTC)
            day_start_ms = int(day_dt.timestamp() * 1000)
            day_end_ms = day_start_ms + 86_400_000
            return day_start_ms, day_end_ms
        except ValueError:
            return 0, 0

    def _load_stats_cache(self) -> dict[str, dict[str, Any]]:
        if not self._stats_cache_path.exists():
            return {}
        try:
            st = self._stats_cache_path.stat()
            if st.st_size > self.MAX_PARTITION_STATS_CACHE_BYTES:
                try:
                    self._stats_cache_path.unlink(missing_ok=True)
                except OSError:
                    pass
                return {}
            data = json.loads(self._stats_cache_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("schema_version") != self.STATS_CACHE_SCHEMA_VERSION:
                return {}
            partitions = data.get("partitions")
            if not isinstance(partitions, dict):
                return {}
            valid: dict[str, dict[str, Any]] = {}
            for name, entry in partitions.items():
                if (
                    isinstance(name, str)
                    and isinstance(entry, dict)
                    and isinstance(entry.get("mtime_ns"), int)
                    and isinstance(entry.get("size"), int)
                ):
                    has_stats = isinstance(entry.get("stats"), dict) and self._is_valid_partition_stats(entry["stats"])
                    has_att = isinstance(entry.get("attestation"), dict)
                    if has_stats or has_att:
                        record: dict[str, Any] = {
                            "mtime_ns": int(entry["mtime_ns"]),
                            "size": int(entry["size"]),
                        }
                        if has_stats:
                            record["stats"] = dict(entry["stats"])
                        if has_att:
                            record["attestation"] = dict(entry["attestation"])
                        valid[name] = record
            return valid
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _save_stats_cache(self, partitions: dict[str, dict[str, Any]]) -> None:
        current_names = {p.name for p in self.root.glob("microstructure-*.sqlite3")}
        pruned = {
            name: entry
            for name, entry in partitions.items()
            if name in current_names and isinstance(entry, dict) and ("stats" in entry or "attestation" in entry)
        }
        payload = {
            "schema_version": self.STATS_CACHE_SCHEMA_VERSION,
            "partitions": dict(sorted(pruned.items())),
        }
        try:
            publish_bytes(
                self._stats_cache_path,
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"),
            )
        except (OSError, PublicationConflict):
            pass

    @staticmethod
    def _is_valid_partition_stats(stats: Any) -> bool:
        if not isinstance(stats, dict):
            return False
        required_int_fields = (
            "depth",
            "trades",
            "book_samples",
            "aggregate_buckets",
            "duplicate_count",
            "conflict_count",
            "orphan_count",
            "gap_count",
        )
        for field in required_int_fields:
            val = stats.get(field)
            if not isinstance(val, int) or isinstance(val, bool):
                return False
        if not isinstance(stats.get("gap_type_counts"), dict):
            return False
        if not isinstance(stats.get("gap_merged_intervals"), list):
            return False
        if not isinstance(stats.get("spill_gaps"), list):
            return False
        if not isinstance(stats.get("latencies"), list):
            return False
        if not isinstance(stats.get("segments"), dict):
            return False
        if not isinstance(stats.get("depth_valid_segments"), list):
            return False
        if not isinstance(stats.get("integrity"), bool):
            return False
        hb = stats.get("latest_heartbeat_ms")
        if hb is not None and (not isinstance(hb, int) or isinstance(hb, bool)):
            return False
        latest_clock = stats.get("latest_clock")
        if latest_clock is not None:
            if not (isinstance(latest_clock, (list, tuple)) and len(latest_clock) == 4):
                return False
        elif "clocks" in stats and not isinstance(stats.get("clocks"), list):
            return False
        min_start = stats.get("gap_min_start_ms")
        if min_start is not None and (not isinstance(min_start, int) or isinstance(min_start, bool)):
            return False
        max_end = stats.get("gap_max_end_ms")
        if max_end is not None and (not isinstance(max_end, int) or isinstance(max_end, bool)):
            return False
        summary = stats.get("bucket_summary")
        return not (summary is not None and not isinstance(summary, dict))

    def _manifest(self) -> dict[str, dict[str, Any]]:
        if not self.finalized_manifest_path.exists():
            return {}
        raw = json.loads(self.finalized_manifest_path.read_text(encoding="utf-8"))
        if (not isinstance(raw, dict) or raw.get("schema_version") != "1.0.0"
                or raw.get("protocol_id") != self.protocol.protocol_id
                or not isinstance(raw.get("partitions"), dict)):
            raise ValueError("unsupported/corrupt finalized manifest")
        for name, metadata in raw["partitions"].items():
            if (Path(name).name != name or not isinstance(metadata, dict)
                    or metadata.get("immutable") is not True
                    or not isinstance(metadata.get("sha256"), str)
                    or len(metadata["sha256"]) != 64):
                raise ValueError("invalid finalized partition metadata")
        return {str(key): dict(value) for key, value in raw["partitions"].items()}

    def _is_finalized(self, path: Path) -> bool:
        return path.name in self._manifest()

    def _path(self, timestamp_ms: int) -> Path:
        day = datetime.fromtimestamp(timestamp_ms / 1000, UTC).strftime("%Y-%m-%d")
        return self.root / f"microstructure-{day}.sqlite3"

    @contextmanager
    def _connect(self, timestamp_ms: int) -> Iterator[sqlite3.Connection]:
        with publication_lock(self.finalized_manifest_path):
            if file_digest(self.finalized_manifest_path) != self._manifest_digest:
                raise PublicationConflict("stale microstructure manifest owner")
            with self._connect_owned(timestamp_ms) as connection:
                yield connection

    @contextmanager
    def _connect_owned(self, timestamp_ms: int) -> Iterator[sqlite3.Connection]:
        path = self._path(timestamp_ms)
        if self._is_finalized(path):
            raise RuntimeError(f"finalized partition is immutable: {path.name}")
        connection = sqlite3.connect(path, timeout=10)
        try:
            prepare_schema(connection, MICROSTRUCTURE_TABLES, legacy_optional=("sessions.instance_id", "sessions.last_heartbeat_ms"))
        except BaseException:
            connection.close()
            raise
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS depth_events(event_time_ms INTEGER,final_update_id INTEGER,
              receive_time_ms INTEGER,receive_monotonic_ns INTEGER,payload_json TEXT,payload_hash TEXT,
              PRIMARY KEY(event_time_ms,final_update_id));
            CREATE TABLE IF NOT EXISTS agg_trades(aggregate_trade_id INTEGER PRIMARY KEY,
              event_time_ms INTEGER,transaction_time_ms INTEGER,receive_time_ms INTEGER,
              receive_monotonic_ns INTEGER,price REAL,quantity REAL,buyer_is_maker INTEGER,
              aggressive_side TEXT,payload_hash TEXT);
            CREATE TABLE IF NOT EXISTS gaps(id INTEGER PRIMARY KEY,start_ms INTEGER,end_ms INTEGER,
              kind TEXT,detail TEXT);
            CREATE TABLE IF NOT EXISTS book_samples(event_time_ms INTEGER,final_update_id INTEGER,
              receive_time_ms INTEGER,spread_bps REAL,top1_imbalance REAL,top5_imbalance REAL,
              top20_imbalance REAL,microprice REAL,ofi REAL,
              PRIMARY KEY(event_time_ms,final_update_id));
            CREATE TABLE IF NOT EXISTS aggregates(interval_ms INTEGER,bucket_start_ms INTEGER,
              trade_count INTEGER DEFAULT 0,buy_quantity REAL DEFAULT 0,
              sell_quantity REAL DEFAULT 0,buy_notional REAL DEFAULT 0,
              sell_notional REAL DEFAULT 0,book_sample_count INTEGER DEFAULT 0,
              spread_bps_sum REAL DEFAULT 0,top1_imbalance_sum REAL DEFAULT 0,
              top5_imbalance_sum REAL DEFAULT 0,top20_imbalance_sum REAL DEFAULT 0,
              ofi_sum REAL DEFAULT 0,gap_count INTEGER DEFAULT 0,
              PRIMARY KEY(interval_ms,bucket_start_ms));
            CREATE TABLE IF NOT EXISTS sessions(session_id TEXT PRIMARY KEY,stream TEXT,
              start_ms INTEGER,end_ms INTEGER,status TEXT);
            CREATE TABLE IF NOT EXISTS audit_counters(name TEXT PRIMARY KEY,value INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS process_instances(instance_id TEXT PRIMARY KEY,
              start_ms INTEGER,last_heartbeat_ms INTEGER,end_ms INTEGER,status TEXT);
            CREATE TABLE IF NOT EXISTS coverage_segments(id INTEGER PRIMARY KEY AUTOINCREMENT,
              instance_id TEXT,stream TEXT,start_ms INTEGER,end_ms INTEGER,
              sequence_valid INTEGER,status TEXT);
            CREATE TABLE IF NOT EXISTS clock_measurements(measured_at_ms INTEGER PRIMARY KEY,
              request_send_ms INTEGER,response_receive_ms INTEGER,server_time_ms INTEGER,
              offset_ms REAL,rtt_ms INTEGER,quality TEXT);
            """
        )
        session_columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(sessions)").fetchall()
        }
        if "instance_id" not in session_columns:
            connection.execute("ALTER TABLE sessions ADD COLUMN instance_id TEXT")
        if "last_heartbeat_ms" not in session_columns:
            connection.execute("ALTER TABLE sessions ADD COLUMN last_heartbeat_ms INTEGER")
        try:
            finish_schema(connection, MICROSTRUCTURE_TABLES)
            yield connection
            connection.commit()
        finally:
            connection.close()

    def append_depth(self, event: DepthEvent) -> bool:
        payload = json.dumps(asdict(event), sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(payload.encode()).hexdigest()
        with self._connect(event.receive_time_ms) as connection:
            cursor = connection.execute(
                f"INSERT OR IGNORE INTO depth_events ({projection('depth_events')}) VALUES(?,?,?,?,?,?)",
                (
                    event.event_time_ms,
                    event.final_update_id,
                    event.receive_time_ms,
                    event.receive_monotonic_ns,
                    payload,
                    digest,
                ),
            )
            if cursor.rowcount == 0:
                existing = connection.execute(
                    "SELECT payload_hash FROM depth_events WHERE event_time_ms=? AND final_update_id=?",
                    (event.event_time_ms, event.final_update_id),
                ).fetchone()
                self._increment(
                    connection,
                    "duplicate_depth" if existing and existing[0] == digest else "conflict_depth",
                )
        return cursor.rowcount == 1

    @staticmethod
    def _increment(connection: sqlite3.Connection, name: str) -> None:
        connection.execute(
            """INSERT INTO audit_counters(name,value) VALUES(?,1)
            ON CONFLICT(name) DO UPDATE SET value=value+1""",
            (name,),
        )

    def append_trade(self, trade: AggTrade) -> bool:
        digest = hashlib.sha256(json.dumps(asdict(trade), sort_keys=True).encode()).hexdigest()
        with self._connect(trade.receive_time_ms) as connection:
            cursor = connection.execute(
                f"INSERT OR IGNORE INTO agg_trades ({projection('agg_trades')}) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    trade.aggregate_trade_id,
                    trade.event_time_ms,
                    trade.transaction_time_ms,
                    trade.receive_time_ms,
                    trade.receive_monotonic_ns,
                    trade.price,
                    trade.quantity,
                    int(trade.buyer_is_maker),
                    trade.aggressive_side,
                    digest,
                ),
            )
            if cursor.rowcount == 0:
                existing = connection.execute(
                    "SELECT payload_hash FROM agg_trades WHERE aggregate_trade_id=?",
                    (trade.aggregate_trade_id,),
                ).fetchone()
                self._increment(
                    connection,
                    "duplicate_trade" if existing and existing[0] == digest else "conflict_trade",
                )
            if cursor.rowcount == 1:
                for interval in self.INTERVALS_MS:
                    bucket = trade.event_time_ms // interval * interval
                    buy = trade.quantity if trade.aggressive_side == "BUY" else 0.0
                    sell = trade.quantity if trade.aggressive_side == "SELL" else 0.0
                    connection.execute(
                        """INSERT INTO aggregates(interval_ms,bucket_start_ms,trade_count,
                        buy_quantity,sell_quantity,buy_notional,sell_notional)
                        VALUES(?,?,1,?,?,?,?) ON CONFLICT(interval_ms,bucket_start_ms) DO UPDATE SET
                        trade_count=trade_count+1,buy_quantity=buy_quantity+excluded.buy_quantity,
                        sell_quantity=sell_quantity+excluded.sell_quantity,
                        buy_notional=buy_notional+excluded.buy_notional,
                        sell_notional=sell_notional+excluded.sell_notional""",
                        (interval, bucket, buy, sell, buy * trade.price, sell * trade.price),
                    )
        return cursor.rowcount == 1

    def append_book_sample(
        self,
        event: DepthEvent,
        stats: dict[str, float | None],
        ofi: float | None,
    ) -> bool:
        with self._connect(event.receive_time_ms) as connection:
            cursor = connection.execute(
                f"INSERT OR IGNORE INTO book_samples ({projection('book_samples')}) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    event.event_time_ms,
                    event.final_update_id,
                    event.receive_time_ms,
                    stats["spread_bps"],
                    stats["top1_imbalance"],
                    stats["top5_imbalance"],
                    stats["top20_imbalance"],
                    stats["microprice"],
                    ofi,
                ),
            )
            if cursor.rowcount == 0:
                self._increment(connection, "duplicate_book_sample")
            if cursor.rowcount == 1:
                for interval in self.INTERVALS_MS:
                    bucket = event.event_time_ms // interval * interval
                    connection.execute(
                        """INSERT INTO aggregates(interval_ms,bucket_start_ms,book_sample_count,
                        spread_bps_sum,top1_imbalance_sum,top5_imbalance_sum,
                        top20_imbalance_sum,ofi_sum) VALUES(?,?,1,?,?,?,?,?)
                        ON CONFLICT(interval_ms,bucket_start_ms) DO UPDATE SET
                        book_sample_count=book_sample_count+1,
                        spread_bps_sum=spread_bps_sum+excluded.spread_bps_sum,
                        top1_imbalance_sum=top1_imbalance_sum+excluded.top1_imbalance_sum,
                        top5_imbalance_sum=top5_imbalance_sum+excluded.top5_imbalance_sum,
                        top20_imbalance_sum=top20_imbalance_sum+excluded.top20_imbalance_sum,
                        ofi_sum=ofi_sum+excluded.ofi_sum""",
                        (
                            interval,
                            bucket,
                            stats["spread_bps"] or 0.0,
                            stats["top1_imbalance"] or 0.0,
                            stats["top5_imbalance"] or 0.0,
                            stats["top20_imbalance"] or 0.0,
                            ofi or 0.0,
                        ),
                    )
        return cursor.rowcount == 1

    def gap(
        self, timestamp_ms: int, kind: str, detail: str, *, end_ms: int | None = None
    ) -> None:
        identity = int(time.time_ns())
        gap_end = max(timestamp_ms, end_ms if end_ms is not None else timestamp_ms)
        with self._connect(timestamp_ms) as connection:
            connection.execute(
                f"INSERT INTO gaps ({projection('gaps')}) VALUES(?,?,?,?,?)",
                (identity, timestamp_ms, gap_end, kind, detail),
            )
            for interval in self.INTERVALS_MS:
                first = timestamp_ms // interval * interval
                last = gap_end // interval * interval
                for bucket in range(first, last + 1, interval):
                    connection.execute(
                        """INSERT INTO aggregates(interval_ms,bucket_start_ms,gap_count)
                        VALUES(?,?,1) ON CONFLICT(interval_ms,bucket_start_ms) DO UPDATE SET
                        gap_count=gap_count+1""",
                        (interval, bucket),
                    )

    @_owned_mutation
    def recover_orphan_instances(
        self, now_ms: int, *, exclude_instance_id: str | None = None
    ) -> int:
        cutoff = now_ms - self.protocol.lease_timeout_ms
        recovered: list[tuple[int, str]] = []
        for path in sorted(self.root.glob("microstructure-*.sqlite3")):
            if self._is_finalized(path):
                continue
            connection = sqlite3.connect(path)
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if "process_instances" not in tables:
                connection.close()
                continue
            rows = connection.execute(
                """SELECT instance_id,last_heartbeat_ms FROM process_instances
                WHERE status='ACTIVE' AND last_heartbeat_ms < ?
                AND (? IS NULL OR instance_id != ?)""",
                (cutoff, exclude_instance_id, exclude_instance_id),
            ).fetchall()
            for instance_id, last_heartbeat in rows:
                lease_end = int(last_heartbeat) + self.protocol.lease_timeout_ms
                connection.execute(
                    """UPDATE process_instances SET end_ms=?,status='ORPHANED'
                    WHERE instance_id=?""",
                    (lease_end, instance_id),
                )
                connection.execute(
                    """UPDATE sessions SET end_ms=?,status='ORPHANED'
                    WHERE instance_id=? AND end_ms IS NULL""",
                    (lease_end, instance_id),
                )
                connection.execute(
                    """UPDATE coverage_segments SET end_ms=?,status='ORPHANED'
                    WHERE instance_id=? AND status='OPEN'""",
                    (lease_end, instance_id),
                )
                recovered.append((lease_end, str(instance_id)))
            connection.commit()
            connection.close()
        for lease_end, instance_id in recovered:
            self.gap(
                lease_end,
                "PROCESS_OR_HOST_GAP",
                f"orphaned_instance={instance_id};lease_expired",
                end_ms=now_ms,
            )
        return len(recovered)

    @_owned_mutation
    def instance_start(self, timestamp_ms: int, instance_id: str | None = None) -> str:
        self.recover_orphan_instances(timestamp_ms)
        identity = instance_id or uuid.uuid4().hex
        with self._connect(timestamp_ms) as connection:
            connection.execute(
                f"INSERT INTO process_instances ({projection('process_instances')}) VALUES(?,?,?,NULL,'ACTIVE')",
                (identity, timestamp_ms, timestamp_ms),
            )
        return identity

    def session_start(self, timestamp_ms: int, stream: str, instance_id: str) -> str:
        session_id = f"{stream}-{timestamp_ms}-{time.monotonic_ns()}"
        with self._connect(timestamp_ms) as connection:
            connection.execute(
                """INSERT INTO sessions(session_id,stream,start_ms,end_ms,status,
                instance_id,last_heartbeat_ms) VALUES(?,?,?,NULL,'CONNECTED',?,?)""",
                (session_id, stream, timestamp_ms, instance_id, timestamp_ms),
            )
            connection.execute(
                """INSERT INTO coverage_segments(instance_id,stream,start_ms,end_ms,
                sequence_valid,status) VALUES(?,?,?,?,?,'OPEN')""",
                (instance_id, stream, timestamp_ms, timestamp_ms, int(stream == "trade")),
            )
        return session_id

    @_owned_mutation
    def heartbeat(self, timestamp_ms: int, instance_id: str) -> None:
        # A fast supervisor restart can occur before the previous lease expires.
        # Recheck on every heartbeat so that such an orphan is closed once the
        # frozen timeout elapses instead of remaining open until another restart.
        try:
            self.recover_orphan_instances(
                timestamp_ms, exclude_instance_id=instance_id
            )
        except sqlite3.OperationalError:
            pass
        for path in sorted(self.root.glob("microstructure-*.sqlite3")):
            if self._is_finalized(path):
                continue
            try:
                connection = sqlite3.connect(path, timeout=30.0)
                tables = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                if "process_instances" in tables:
                    connection.execute(
                        """UPDATE process_instances SET last_heartbeat_ms=?
                        WHERE instance_id=? AND status='ACTIVE'""",
                        (timestamp_ms, instance_id),
                    )
                    connection.execute(
                        """UPDATE sessions SET last_heartbeat_ms=?
                        WHERE instance_id=? AND end_ms IS NULL""",
                        (timestamp_ms, instance_id),
                    )
                    connection.execute(
                        """UPDATE coverage_segments SET end_ms=?
                        WHERE instance_id=? AND status='OPEN'""",
                        (timestamp_ms, instance_id),
                    )
                    connection.commit()
                connection.close()
            except sqlite3.OperationalError:
                continue

    @_owned_mutation
    def depth_sequence_state(self, timestamp_ms: int, instance_id: str, valid: bool) -> None:
        for path in sorted(self.root.glob("microstructure-*.sqlite3")):
            if self._is_finalized(path):
                continue
            connection = sqlite3.connect(path)
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if "coverage_segments" in tables:
                connection.execute(
                    """UPDATE coverage_segments SET end_ms=?,status='CLOSED'
                    WHERE instance_id=? AND stream='depth' AND status='OPEN'""",
                    (timestamp_ms, instance_id),
                )
                connection.commit()
            connection.close()
        with self._connect(timestamp_ms) as connection:
            connection.execute(
                """INSERT INTO coverage_segments(instance_id,stream,start_ms,end_ms,
                sequence_valid,status) VALUES(?,'depth',?,?,?,'OPEN')""",
                (instance_id, timestamp_ms, timestamp_ms, int(valid)),
            )

    @_owned_mutation
    def session_end(self, timestamp_ms: int, session_id: str) -> None:
        for path in sorted(self.root.glob("microstructure-*.sqlite3")):
            if self._is_finalized(path):
                continue
            connection = sqlite3.connect(path)
            columns = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(sessions)").fetchall()
            }
            if "instance_id" not in columns:
                connection.close()
                continue
            row = connection.execute(
                "SELECT instance_id,stream FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            cursor = connection.execute(
                "UPDATE sessions SET end_ms=?,status='CLOSED' WHERE session_id=?",
                (timestamp_ms, session_id),
            )
            if row:
                connection.execute(
                    """UPDATE coverage_segments SET end_ms=?,status='CLOSED'
                    WHERE instance_id=? AND stream=? AND status='OPEN'""",
                    (timestamp_ms, row[0], row[1]),
                )
            connection.commit()
            connection.close()
            if cursor.rowcount:
                return

    @_owned_mutation
    def instance_end(self, timestamp_ms: int, instance_id: str) -> None:
        self.heartbeat(timestamp_ms, instance_id)
        for path in sorted(self.root.glob("microstructure-*.sqlite3")):
            if self._is_finalized(path):
                continue
            connection = sqlite3.connect(path)
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if "process_instances" in tables:
                connection.execute(
                    """UPDATE process_instances SET end_ms=?,status='CLOSED'
                    WHERE instance_id=? AND status='ACTIVE'""",
                    (timestamp_ms, instance_id),
                )
                connection.execute(
                    """UPDATE sessions SET end_ms=?,status='CLOSED'
                    WHERE instance_id=? AND end_ms IS NULL""",
                    (timestamp_ms, instance_id),
                )
                connection.execute(
                    """UPDATE coverage_segments SET end_ms=?,status='CLOSED'
                    WHERE instance_id=? AND status='OPEN'""",
                    (timestamp_ms, instance_id),
                )
                connection.commit()
            connection.close()

    def append_clock_measurement(
        self,
        *,
        request_send_ms: int,
        response_receive_ms: int,
        server_time_ms: int,
    ) -> None:
        rtt = response_receive_ms - request_send_ms
        midpoint = (request_send_ms + response_receive_ms) / 2
        offset = server_time_ms - midpoint
        quality = "OK" if rtt <= self.protocol.maximum_clock_rtt_ms else "DEGRADED_RTT"
        with self._connect(response_receive_ms) as connection:
            connection.execute(
                f"INSERT OR REPLACE INTO clock_measurements ({projection('clock_measurements')}) VALUES(?,?,?,?,?,?,?)",
                (
                    response_receive_ms,
                    request_send_ms,
                    response_receive_ms,
                    server_time_ms,
                    offset,
                    rtt,
                    quality,
                ),
            )

    def partition_integrity_audit(
        self,
        force_full: bool = False,
        stats_cache: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        manifest = self._manifest()
        drift: list[str] = []
        missing: list[str] = []
        reused = 0
        recomputed = 0
        cache = self._load_stats_cache() if stats_cache is None else stats_cache
        cache_dirty = False
        for name, metadata in manifest.items():
            path = self.root / name
            if not path.exists():
                missing.append(name)
                continue
            st = path.stat()
            entry = cache.get(name)
            attestation = entry.get("attestation") if isinstance(entry, dict) else None
            is_valid_attestation = (
                not force_full
                and isinstance(attestation, dict)
                and attestation.get("st_dev") == st.st_dev
                and attestation.get("st_ino") == st.st_ino
                and attestation.get("st_size") == st.st_size
                and attestation.get("st_mtime_ns") == st.st_mtime_ns
                and attestation.get("st_ctime_ns") == st.st_ctime_ns
                and attestation.get("manifest_sha256") == metadata["sha256"]
                and attestation.get("verified") is True
            )
            if is_valid_attestation:
                reused += 1
            else:
                digest = _streaming_sha256(path)
                recomputed += 1
                if digest != metadata["sha256"]:
                    drift.append(name)
                else:
                    new_attestation = {
                        "st_dev": st.st_dev,
                        "st_ino": st.st_ino,
                        "st_size": st.st_size,
                        "st_mtime_ns": st.st_mtime_ns,
                        "st_ctime_ns": st.st_ctime_ns,
                        "manifest_sha256": metadata["sha256"],
                        "verified": True,
                    }
                    if isinstance(entry, dict):
                        entry["attestation"] = new_attestation
                    else:
                        cache[name] = {
                            "mtime_ns": st.st_mtime_ns,
                            "size": st.st_size,
                            "attestation": new_attestation,
                        }
                    cache_dirty = True
        if cache_dirty and stats_cache is None:
            self._save_stats_cache(cache)
        return {
            "manifest_path": str(self.finalized_manifest_path),
            "finalized_partition_count": len(manifest),
            "checksum_drift": drift,
            "missing_partitions": missing,
            "integrity_ok": not drift and not missing,
            "attestation_reused": reused,
            "attestation_recomputed": recomputed,
        }

    @_owned_mutation
    def finalize_partitions(self, now_ms: int | None = None) -> dict[str, dict[str, Any]]:
        now = now_ms or int(time.time() * 1000)
        manifest = self._manifest()
        audit = self.partition_integrity_audit()
        if not audit["integrity_ok"]:
            return manifest
        changed = False
        for path in sorted(self.root.glob("microstructure-*.sqlite3")):
            if path.name in manifest:
                continue
            day = datetime.strptime(path.stem.removeprefix("microstructure-"), "%Y-%m-%d").replace(
                tzinfo=UTC
            )
            eligible_at = int(day.timestamp() * 1_000) + 86_400_000 + self.protocol.finalization_grace_ms
            if now < eligible_at:
                continue
            connection = sqlite3.connect(path)
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if "sessions" in tables:
                open_count = int(
                    connection.execute(
                        "SELECT count(*) FROM sessions WHERE end_ms IS NULL"
                    ).fetchone()[0]
                )
                if open_count:
                    connection.close()
                    continue
            checkpoint = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if checkpoint is None or checkpoint[0] != 0:
                connection.close()
                raise RuntimeError("partition WAL checkpoint busy; finalization refused")
            quick_check = connection.execute("PRAGMA quick_check").fetchone()
            if quick_check is None or quick_check[0] != "ok":
                connection.close()
                raise RuntimeError(f"partition quick_check failed: {quick_check}")
            connection.close()
            manifest[path.name] = {
                "sha256": _streaming_sha256(path),
                "finalized_at_ms": now,
                "eligible_at_ms": eligible_at,
                "immutable": True,
            }
            changed = True
        if changed:
            payload = {
                "schema_version": "1.0.0",
                "protocol_id": self.protocol.protocol_id,
                "partitions": dict(sorted(manifest.items())),
            }
            publish_bytes(self.finalized_manifest_path,
                          (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"),
                          expected_sha256=self._manifest_digest)
            self._manifest_digest = file_digest(self.finalized_manifest_path)
        return manifest

    def closed_partition_manifest(self, now_ms: int | None = None) -> dict[str, str]:
        """Compatibility view; v0.3.16 manifests never overwrite an existing digest."""
        return {
            name: str(metadata["sha256"])
            for name, metadata in self.finalize_partitions(now_ms).items()
        }

    @staticmethod
    def _covered_ms(
        segments: Iterable[tuple[int, int]], start_ms: int, end_ms: int
    ) -> int:
        clipped = sorted(
            (max(start_ms, start), min(end_ms, end))
            for start, end in segments
            if end > start_ms and start < end_ms
        )
        covered = 0
        cursor_start: int | None = None
        cursor_end: int | None = None
        for start, end in clipped:
            if end <= start:
                continue
            if cursor_start is None:
                cursor_start, cursor_end = start, end
            elif cursor_end is not None and start <= cursor_end:
                cursor_end = max(cursor_end, end)
            else:
                assert cursor_end is not None
                covered += cursor_end - cursor_start
                cursor_start, cursor_end = start, end
        if cursor_start is not None and cursor_end is not None:
            covered += cursor_end - cursor_start
        return covered

    def status(
        self, now_ms: int | None = None, deep_integrity: bool = False
    ) -> dict[str, Any]:
        now = now_ms or int(time.time() * 1000)
        depth = trades = book_samples = aggregate_buckets = 0
        duplicate_count = conflict_count = orphan_count = 0
        latencies: list[int] = []
        segments: dict[str, list[tuple[int, int]]] = {"depth": [], "trade": []}
        depth_valid_segments: list[tuple[int, int]] = []
        latest_clocks: list[tuple[int, float, int, str]] = []
        latest_heartbeat_ms: int | None = None
        integrity = True
        gap_count = 0
        gap_type_counts: Counter[str] = Counter()
        partition_records: list[dict[str, Any]] = []
        finalized_cache_hits = 0
        finalized_cache_misses = 0

        manifest = self._manifest()
        finalized_names = set(manifest.keys())

        stats_cache = self._load_stats_cache()
        current_files = sorted(self.root.glob("microstructure-*.sqlite3"))
        current_names = {p.name for p in current_files}
        cache_dirty = bool(set(stats_cache.keys()) - current_names)

        active_quick_checks_executed = 0

        for path in current_files:
            st = path.stat()
            is_finalized = path.name in finalized_names
            day_start_ms, day_end_ms = self._partition_day_bounds(path)
            cached_entry = stats_cache.get(path.name)
            is_hit = False
            cache_eligible = (
                (not is_finalized and not deep_integrity)
                or (
                    is_finalized
                    and isinstance(cached_entry, dict)
                    and isinstance(cached_entry.get("stats"), dict)
                    and cached_entry["stats"].get("integrity") is True
                )
            )
            if (
                isinstance(cached_entry, dict)
                and cached_entry.get("mtime_ns") == st.st_mtime_ns
                and cached_entry.get("size") == st.st_size
                and self._is_valid_partition_stats(cached_entry.get("stats"))
                and cache_eligible
            ):
                try:
                    cached = cached_entry["stats"]
                    cached_depth = int(cached["depth"])
                    cached_trades = int(cached["trades"])
                    cached_book_samples = int(cached["book_samples"])
                    cached_aggregate_buckets = int(cached["aggregate_buckets"])
                    cached_duplicate_count = int(cached["duplicate_count"])
                    cached_conflict_count = int(cached["conflict_count"])
                    cached_segments: dict[str, list[tuple[int, int]]] = {
                        str(k): [(int(start), min(now, int(end))) for start, end in segs]
                        for k, segs in cached["segments"].items()
                    }
                    cached_valid_segments = [
                        (int(start), min(now, int(end))) for start, end in cached["depth_valid_segments"]
                    ]
                    cached_orphan_count = int(cached["orphan_count"])
                    cached_latest_hb = (
                        int(cached["latest_heartbeat_ms"]) if cached["latest_heartbeat_ms"] is not None else None
                    )
                    cached_latencies = [int(lat) for lat in cached["latencies"]]
                    cached_clock_tuple: tuple[int, float, int, str] | None = None
                    if cached_clock := cached.get("latest_clock"):
                        cached_clock_tuple = (
                            int(cached_clock[0]),
                            float(cached_clock[1]),
                            int(cached_clock[2]),
                            str(cached_clock[3]),
                        )
                    elif cached_clocks := cached.get("clocks"):
                        valid_c = [
                            (int(c[0]), float(c[1]), int(c[2]), str(c[3]))
                            for c in cached_clocks
                        ]
                        if valid_c:
                            cached_clock_tuple = max(valid_c, key=lambda value: value[0])
                    cached_integrity = bool(cached["integrity"])

                    p_gap_count = int(cached["gap_count"])
                    p_gap_type_counts = {str(k): int(v) for k, v in cached["gap_type_counts"].items()}
                    p_gap_merged = [(int(s), int(e)) for s, e in cached["gap_merged_intervals"]]
                    p_gap_min_start = int(cached["gap_min_start_ms"]) if cached.get("gap_min_start_ms") is not None else None
                    p_gap_max_end = int(cached["gap_max_end_ms"]) if cached.get("gap_max_end_ms") is not None else None
                    p_spill_gaps = [(int(s), int(e)) for s, e in cached.get("spill_gaps", [])]
                    p_bucket_summary = dict(cached["bucket_summary"]) if isinstance(cached.get("bucket_summary"), dict) else None

                    depth += cached_depth
                    trades += cached_trades
                    book_samples += cached_book_samples
                    aggregate_buckets += cached_aggregate_buckets
                    duplicate_count += cached_duplicate_count
                    conflict_count += cached_conflict_count
                    gap_count += p_gap_count
                    for k, v in p_gap_type_counts.items():
                        gap_type_counts[k] += v

                    for stream_name, segs in cached_segments.items():
                        if stream_name not in segments:
                            segments[stream_name] = []
                        segments[stream_name].extend(segs)
                    depth_valid_segments.extend(cached_valid_segments)
                    orphan_count += cached_orphan_count
                    if cached_latest_hb is not None:
                        latest_heartbeat_ms = max(latest_heartbeat_ms or cached_latest_hb, cached_latest_hb)
                    if cached_clock_tuple is not None:
                        latest_clocks.append(cached_clock_tuple)
                    integrity = integrity and cached_integrity
                    latencies += cached_latencies

                    partition_records.append({
                        "path": path,
                        "is_finalized": is_finalized,
                        "day_start_ms": day_start_ms,
                        "day_end_ms": day_end_ms,
                        "gap_count": p_gap_count,
                        "gap_type_counts": p_gap_type_counts,
                        "gap_merged_intervals": p_gap_merged,
                        "gap_min_start_ms": p_gap_min_start,
                        "gap_max_end_ms": p_gap_max_end,
                        "spill_gaps": p_spill_gaps,
                        "bucket_summary": p_bucket_summary,
                        "active_gaps": None,
                    })

                    if is_finalized:
                        finalized_cache_hits += 1
                    is_hit = True
                except (TypeError, IndexError, ValueError, KeyError):
                    is_hit = False

            if is_hit:
                continue

            if is_finalized:
                finalized_cache_misses += 1

            try:
                connection = sqlite3.connect(path, timeout=30.0)
                tables = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                cur_depth = int(connection.execute("SELECT count(*) FROM depth_events").fetchone()[0]) if "depth_events" in tables else 0
                cur_trades = int(connection.execute("SELECT count(*) FROM agg_trades").fetchone()[0]) if "agg_trades" in tables else 0
                cur_book_samples = int(connection.execute("SELECT count(*) FROM book_samples").fetchone()[0]) if "book_samples" in tables else 0
                cur_aggregate_buckets = int(connection.execute("SELECT count(*) FROM aggregates").fetchone()[0]) if "aggregates" in tables else 0

                cur_duplicate_count = 0
                cur_conflict_count = 0
                if "audit_counters" in tables:
                    for name, value in connection.execute("SELECT name,value FROM audit_counters"):
                        if str(name).startswith("duplicate_"):
                            cur_duplicate_count += int(value)
                        elif str(name).startswith("conflict_"):
                            cur_conflict_count += int(value)

                cur_segments: dict[str, list[tuple[int, int]]] = {"depth": [], "trade": []}
                cur_depth_valid_segments: list[tuple[int, int]] = []
                if "coverage_segments" in tables:
                    for stream, start, end, valid in connection.execute(
                        "SELECT stream,start_ms,end_ms,sequence_valid FROM coverage_segments"
                    ):
                        segment = (int(start), int(end))
                        cur_segments[str(stream)].append(segment)
                        if stream == "depth" and bool(valid):
                            cur_depth_valid_segments.append(segment)

                cur_orphan_count = 0
                cur_latest_heartbeat_ms: int | None = None
                if "process_instances" in tables:
                    cur_orphan_count = int(
                        connection.execute(
                            "SELECT count(*) FROM process_instances WHERE status='ORPHANED'"
                        ).fetchone()[0]
                    )
                    heartbeat_row = connection.execute(
                        "SELECT MAX(last_heartbeat_ms) FROM process_instances"
                    ).fetchone()
                    if heartbeat_row and heartbeat_row[0] is not None:
                        cur_latest_heartbeat_ms = int(heartbeat_row[0])

                cur_latest_clock: tuple[int, float, int, str] | None = None
                if "clock_measurements" in tables:
                    clock_row = connection.execute(
                        """SELECT measured_at_ms,offset_ms,rtt_ms,quality
                        FROM clock_measurements
                        ORDER BY measured_at_ms DESC
                        LIMIT 1"""
                    ).fetchone()
                    if clock_row is not None:
                        cur_latest_clock = (
                            int(clock_row[0]),
                            float(clock_row[1]),
                            int(clock_row[2]),
                            str(clock_row[3]),
                        )

                if deep_integrity:
                    cur_integrity = connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
                    if not is_finalized:
                        active_quick_checks_executed += 1
                else:
                    cur_integrity = True

                cur_latencies = []
                if "agg_trades" in tables:
                    cur_latencies = [
                        int(a) - int(b)
                        for a, b in connection.execute(
                            "SELECT receive_time_ms,event_time_ms FROM agg_trades ORDER BY aggregate_trade_id DESC LIMIT 5000"
                        )
                    ]

                cur_gap_count = 0
                cur_gap_type_counts: dict[str, int] = {}
                cur_merged_gaps: list[list[int]] = []
                cur_gap_min_start_ms: int | None = None
                cur_gap_max_end_ms: int | None = None
                cur_spill_gaps: list[list[int]] = []
                active_gaps: list[tuple[int, int]] | None = [] if not is_finalized else None

                if "gaps" in tables:
                    cursor = connection.execute(
                        "SELECT start_ms, end_ms, kind FROM gaps ORDER BY start_ms, end_ms"
                    )
                    for start_ms_raw, end_ms_raw, kind_raw in cursor:
                        s = int(start_ms_raw)
                        e = int(end_ms_raw)
                        k = str(kind_raw)
                        cur_gap_count += 1
                        cur_gap_type_counts[k] = cur_gap_type_counts.get(k, 0) + 1
                        if cur_gap_min_start_ms is None or s < cur_gap_min_start_ms:
                            cur_gap_min_start_ms = s
                        if cur_gap_max_end_ms is None or e > cur_gap_max_end_ms:
                            cur_gap_max_end_ms = e
                        if e >= day_end_ms:
                            cur_spill_gaps.append([s, e])
                        if active_gaps is not None:
                            active_gaps.append((s, e))
                        if e <= s:
                            continue
                        if not cur_merged_gaps:
                            cur_merged_gaps.append([s, e])
                        elif s <= cur_merged_gaps[-1][1]:
                            cur_merged_gaps[-1][1] = max(cur_merged_gaps[-1][1], e)
                        else:
                            cur_merged_gaps.append([s, e])

                connection.close()

                existing_attestation = None
                if isinstance(cached_entry, dict) and isinstance(cached_entry.get("attestation"), dict):
                    existing_attestation = cached_entry["attestation"]

                stats_entry: dict[str, Any] = {
                    "mtime_ns": st.st_mtime_ns,
                    "size": st.st_size,
                    "stats": {
                        "depth": cur_depth,
                        "trades": cur_trades,
                        "book_samples": cur_book_samples,
                        "aggregate_buckets": cur_aggregate_buckets,
                        "duplicate_count": cur_duplicate_count,
                        "conflict_count": cur_conflict_count,
                        "segments": cur_segments,
                        "depth_valid_segments": cur_depth_valid_segments,
                        "orphan_count": cur_orphan_count,
                        "latest_heartbeat_ms": cur_latest_heartbeat_ms,
                        "latest_clock": list(cur_latest_clock) if cur_latest_clock is not None else None,
                        "integrity": cur_integrity,
                        "latencies": cur_latencies,
                        "gap_count": cur_gap_count,
                        "gap_type_counts": cur_gap_type_counts,
                        "gap_merged_intervals": cur_merged_gaps,
                        "gap_min_start_ms": cur_gap_min_start_ms,
                        "gap_max_end_ms": cur_gap_max_end_ms,
                        "spill_gaps": cur_spill_gaps,
                        "bucket_summary": None,
                    },
                }
                if existing_attestation is not None:
                    stats_entry["attestation"] = existing_attestation

                stats_cache[path.name] = stats_entry
                cache_dirty = True

                depth += cur_depth
                trades += cur_trades
                book_samples += cur_book_samples
                aggregate_buckets += cur_aggregate_buckets
                duplicate_count += cur_duplicate_count
                conflict_count += cur_conflict_count
                gap_count += cur_gap_count
                for k, v in cur_gap_type_counts.items():
                    gap_type_counts[k] += v

                for stream_name, segs in cur_segments.items():
                    if stream_name not in segments:
                        segments[stream_name] = []
                    segments[stream_name].extend((start, min(now, end)) for start, end in segs)
                depth_valid_segments.extend((start, min(now, end)) for start, end in cur_depth_valid_segments)
                orphan_count += cur_orphan_count
                if cur_latest_heartbeat_ms is not None:
                    latest_heartbeat_ms = max(latest_heartbeat_ms or cur_latest_heartbeat_ms, cur_latest_heartbeat_ms)
                if cur_latest_clock is not None:
                    latest_clocks.append(cur_latest_clock)
                integrity = integrity and cur_integrity
                latencies += cur_latencies

                partition_records.append({
                    "path": path,
                    "is_finalized": is_finalized,
                    "day_start_ms": day_start_ms,
                    "day_end_ms": day_end_ms,
                    "gap_count": cur_gap_count,
                    "gap_type_counts": cur_gap_type_counts,
                    "gap_merged_intervals": [(s, e) for s, e in cur_merged_gaps],
                    "gap_min_start_ms": cur_gap_min_start_ms,
                    "gap_max_end_ms": cur_gap_max_end_ms,
                    "spill_gaps": [(s, e) for s, e in cur_spill_gaps],
                    "bucket_summary": None,
                    "active_gaps": active_gaps,
                })
            except sqlite3.DatabaseError:
                integrity = False

        ordered = sorted(latencies)

        def pct(value: float) -> int | None:
            return ordered[min(len(ordered) - 1, int(value * len(ordered)))] if ordered else None

        evaluation_start = min(
            (start for stream_segments in segments.values() for start, _ in stream_segments),
            default=now,
        )
        expected_ms = max(0, now - evaluation_start)
        connected_ms_by_stream = {
            stream: self._covered_ms(values, evaluation_start, now)
            for stream, values in segments.items()
        }
        connected_ms = min(connected_ms_by_stream.values()) if connected_ms_by_stream else 0
        uptime_ratio = min(1.0, connected_ms / expected_ms) if expected_ms else 0.0
        depth_valid_ms = self._covered_ms(depth_valid_segments, evaluation_start, now)
        depth_connected_ms = connected_ms_by_stream.get("depth", 0)
        continuity_ratio = depth_valid_ms / depth_connected_ms if depth_connected_ms else 0.0

        def _merge_intervals(segs: list[tuple[int, int]]) -> list[tuple[int, int]]:
            if not segs:
                return []
            ordered_segs = sorted(segs)
            merged: list[list[int]] = []
            for s, e in ordered_segs:
                if e <= s:
                    continue
                if not merged:
                    merged.append([s, e])
                elif s <= merged[-1][1]:
                    merged[-1][1] = max(merged[-1][1], e)
                else:
                    merged.append([s, e])
            return [(s, e) for s, e in merged]

        def _fast_covered(
            merged: list[tuple[int, int]], start_ms: int, end_ms: int, hint_idx: int = 0
        ) -> tuple[int, int]:
            if not merged or end_ms <= start_ms:
                return 0, hint_idx
            idx = bisect.bisect_right(merged, (start_ms, 10**18), lo=hint_idx) - 1
            idx = max(idx, 0)
            covered = 0
            for s, e in merged[idx:]:
                if s >= end_ms:
                    break
                overlap_s = max(start_ms, s)
                overlap_e = min(end_ms, e)
                if overlap_e > overlap_s:
                    covered += overlap_e - overlap_s
            return covered, idx

        def _fast_has_gap(
            merged_gaps: list[tuple[int, int]], start_ms: int, end_ms: int, hint_idx: int = 0
        ) -> tuple[bool, int]:
            if not merged_gaps or end_ms <= start_ms:
                return False, hint_idx
            idx = bisect.bisect_right(merged_gaps, (start_ms, 10**18), lo=hint_idx) - 1
            idx = max(idx, 0)
            for s, e in merged_gaps[idx:]:
                if s >= end_ms:
                    break
                if s < end_ms and e >= start_ms:
                    return True, idx
            return False, idx

        merged_trade = _merge_intervals(segments.get("trade", []))
        merged_depth = _merge_intervals(segments.get("depth", []))
        merged_valid = _merge_intervals(depth_valid_segments)
        all_partition_gaps: list[tuple[int, int]] = []
        for p_rec in partition_records:
            all_partition_gaps.extend(p_rec["gap_merged_intervals"])
        merged_gaps = _merge_intervals(all_partition_gaps)

        closed_buckets = complete_buckets = gap_affected_buckets = 0
        completeness_by_interval: dict[str, dict[str, int | float]] = {
            str(interval): {"closed": 0, "complete": 0, "ratio": 0.0}
            for interval in self.INTERVALS_MS
        }
        bucket_history_cache_hits = 0
        bucket_active_candidates_evaluated = 0

        for p_rec in partition_records:
            p_is_finalized = p_rec["is_finalized"]
            p_day_start = p_rec["day_start_ms"]
            p_day_end = p_rec["day_end_ms"]
            p_path = p_rec["path"]
            p_summary = p_rec["bucket_summary"]

            if p_is_finalized:
                summary_valid = (
                    isinstance(p_summary, dict)
                    and (
                        p_summary.get("evaluation_start_ms") == evaluation_start
                        or (
                            isinstance(p_summary.get("evaluation_start_ms"), int)
                            and p_summary["evaluation_start_ms"] <= p_day_start
                            and evaluation_start <= p_day_start
                        )
                    )
                    and isinstance(p_summary.get("intervals"), dict)
                    and all(
                        str(interval) in p_summary["intervals"]
                        and isinstance(p_summary["intervals"][str(interval)].get("closed"), int)
                        and isinstance(p_summary["intervals"][str(interval)].get("complete"), int)
                        and isinstance(p_summary["intervals"][str(interval)].get("gap_affected"), int)
                        for interval in self.INTERVALS_MS
                    )
                )
                if summary_valid:
                    assert p_summary is not None
                    for interval in self.INTERVALS_MS:
                        i_data = p_summary["intervals"][str(interval)]
                        c = int(i_data["closed"])
                        comp = int(i_data["complete"])
                        g = int(i_data["gap_affected"])
                        completeness_by_interval[str(interval)]["closed"] = int(completeness_by_interval[str(interval)]["closed"]) + c
                        completeness_by_interval[str(interval)]["complete"] = int(completeness_by_interval[str(interval)]["complete"]) + comp
                        closed_buckets += c
                        complete_buckets += comp
                        gap_affected_buckets += g
                        bucket_history_cache_hits += 1
                else:
                    new_intervals: dict[str, dict[str, int]] = {}
                    for interval in self.INTERVALS_MS:
                        first = max(p_day_start, evaluation_start // interval * interval)
                        p_closed = p_complete = p_gap = 0
                        trade_hint = depth_hint = valid_hint = gap_hint = 0
                        if first < p_day_end:
                            for start in range(first, p_day_end, interval):
                                end = start + interval
                                p_closed += 1
                                gap_overlap, gap_hint = _fast_has_gap(merged_gaps, start, end, gap_hint)
                                if gap_overlap:
                                    p_gap += 1
                                cov_t, trade_hint = _fast_covered(merged_trade, start, end, trade_hint)
                                cov_d, depth_hint = _fast_covered(merged_depth, start, end, depth_hint)
                                cov_v, valid_hint = _fast_covered(merged_valid, start, end, valid_hint)
                                trade_ratio = cov_t / interval
                                depth_ratio = cov_d / interval
                                valid_ratio = cov_v / interval
                                if (
                                    trade_ratio >= self.protocol.minimum_trade_coverage
                                    and depth_ratio >= self.protocol.minimum_depth_coverage
                                    and valid_ratio >= self.protocol.minimum_depth_valid_coverage
                                    and not gap_overlap
                                ):
                                    p_complete += 1
                        new_intervals[str(interval)] = {
                            "closed": p_closed,
                            "complete": p_complete,
                            "gap_affected": p_gap,
                        }
                        completeness_by_interval[str(interval)]["closed"] = int(completeness_by_interval[str(interval)]["closed"]) + p_closed
                        completeness_by_interval[str(interval)]["complete"] = int(completeness_by_interval[str(interval)]["complete"]) + p_complete
                        closed_buckets += p_closed
                        complete_buckets += p_complete
                        gap_affected_buckets += p_gap
                    new_summary = {
                        "evaluation_start_ms": evaluation_start,
                        "intervals": new_intervals,
                    }
                    if p_path.name in stats_cache and isinstance(stats_cache[p_path.name].get("stats"), dict):
                        stats_cache[p_path.name]["stats"]["bucket_summary"] = new_summary
                        cache_dirty = True
            else:
                for interval in self.INTERVALS_MS:
                    first = max(p_day_start, evaluation_start // interval * interval)
                    partition_end = min(p_day_end, now)
                    latest_closed = partition_end // interval * interval - interval
                    trade_hint = depth_hint = valid_hint = gap_hint = 0
                    if first <= latest_closed:
                        for start in range(first, latest_closed + 1, interval):
                            bucket_active_candidates_evaluated += 1
                            end = start + interval
                            completeness_by_interval[str(interval)]["closed"] = int(completeness_by_interval[str(interval)]["closed"]) + 1
                            closed_buckets += 1
                            gap_overlap, gap_hint = _fast_has_gap(merged_gaps, start, end, gap_hint)
                            if gap_overlap:
                                gap_affected_buckets += 1
                            cov_t, trade_hint = _fast_covered(merged_trade, start, end, trade_hint)
                            cov_d, depth_hint = _fast_covered(merged_depth, start, end, depth_hint)
                            cov_v, valid_hint = _fast_covered(merged_valid, start, end, valid_hint)
                            trade_ratio = cov_t / interval
                            depth_ratio = cov_d / interval
                            valid_ratio = cov_v / interval
                            if (
                                trade_ratio >= self.protocol.minimum_trade_coverage
                                and depth_ratio >= self.protocol.minimum_depth_coverage
                                and valid_ratio >= self.protocol.minimum_depth_valid_coverage
                                and not gap_overlap
                            ):
                                completeness_by_interval[str(interval)]["complete"] = int(completeness_by_interval[str(interval)]["complete"]) + 1
                                complete_buckets += 1

        for interval in self.INTERVALS_MS:
            c = int(completeness_by_interval[str(interval)]["closed"])
            comp = int(completeness_by_interval[str(interval)]["complete"])
            completeness_by_interval[str(interval)]["ratio"] = comp / c if c else 0.0
        completeness_ratio = complete_buckets / closed_buckets if closed_buckets else 0.0

        partition_audit = self.partition_integrity_audit(force_full=deep_integrity, stats_cache=stats_cache)
        if cache_dirty:
            self._save_stats_cache(stats_cache)

        rolling_reliability: dict[str, dict[str, Any]] = {}
        for label, window_ms in (("24h", 86_400_000), ("7d", 7 * 86_400_000)):
            window_start = max(evaluation_start, now - window_ms)
            window_expected = max(0, now - window_start)
            trade_covered = self._covered_ms(segments.get("trade", []), window_start, now)
            depth_covered = self._covered_ms(segments.get("depth", []), window_start, now)
            valid_covered = self._covered_ms(depth_valid_segments, window_start, now)

            window_gap_count = 0
            for p_rec in partition_records:
                p_day_start = p_rec["day_start_ms"]
                p_day_end = p_rec["day_end_ms"]
                p_path = p_rec["path"]
                p_is_finalized = p_rec["is_finalized"]

                if not p_is_finalized:
                    active_gaps = p_rec.get("active_gaps")
                    if active_gaps is not None:
                        window_gap_count += sum(1 for s, e in active_gaps if s < now and e >= window_start)
                    else:
                        with sqlite3.connect(f"file:{p_path.resolve().as_posix()}?mode=ro", uri=True) as conn:
                            window_gap_count += int(conn.execute(
                                "SELECT count(*) FROM gaps WHERE start_ms < ? AND end_ms >= ?",
                                (now, window_start),
                            ).fetchone()[0])
                else:
                    if p_day_start >= window_start and p_day_end <= now:
                        window_gap_count += p_rec["gap_count"]
                    elif p_day_end <= window_start:
                        spill = p_rec.get("spill_gaps", [])
                        window_gap_count += sum(1 for s, e in spill if s < now and e >= window_start)
                    elif p_day_start <= window_start < p_day_end or p_day_start < now < p_day_end:
                        g_min = p_rec.get("gap_min_start_ms")
                        g_max = p_rec.get("gap_max_end_ms")
                        if p_rec["gap_count"] == 0 or (g_max is not None and g_max < window_start):
                            pass
                        elif g_min is not None and g_min >= window_start and p_day_end <= now:
                            window_gap_count += p_rec["gap_count"]
                        else:
                            with sqlite3.connect(f"file:{p_path.resolve().as_posix()}?mode=ro", uri=True) as conn:
                                window_gap_count += int(conn.execute(
                                    "SELECT count(*) FROM gaps WHERE start_ms < ? AND end_ms >= ?",
                                    (now, window_start),
                                ).fetchone()[0])

            rolling_reliability[label] = {
                "window_start_ms": window_start,
                "observed_seconds": window_expected / 1000,
                "trade_coverage_ratio": (
                    trade_covered / window_expected if window_expected else 0.0
                ),
                "depth_coverage_ratio": (
                    depth_covered / window_expected if window_expected else 0.0
                ),
                "sequence_valid_coverage_ratio": (
                    valid_covered / window_expected if window_expected else 0.0
                ),
                "gap_count": window_gap_count,
            }

        resync_types = {
            "DEPTH_SEQUENCE_GAP",
            "DEPTH_BOOTSTRAP_FAILURE",
            "DEPTH_RECONNECT",
            "REST_BOOTSTRAP_FAILURE",
            "DEPTH_GAP_RESYNC",
        }
        resync_count = sum(count for kind, count in gap_type_counts.items() if kind in resync_types)

        latest_clock = max(latest_clocks, default=None, key=lambda value: value[0])
        offset = latest_clock[1] if latest_clock is not None else None
        adjusted = sorted(value + offset for value in latencies) if offset is not None else []

        def adjusted_pct(value: float) -> float | None:
            return adjusted[min(len(adjusted) - 1, int(value * len(adjusted)))] if adjusted else None

        status_performance = {
            "stats_cache_schema": self.STATS_CACHE_SCHEMA_VERSION,
            "finalized_partition_cache_hits": finalized_cache_hits,
            "finalized_partition_cache_misses": finalized_cache_misses,
            "finalized_hash_reused": partition_audit.get("attestation_reused", 0),
            "finalized_hash_recomputed": partition_audit.get("attestation_recomputed", 0),
            "active_quick_check_executed": active_quick_checks_executed > 0,
            "bucket_history_cache_hits": bucket_history_cache_hits,
            "bucket_active_candidates_evaluated": bucket_active_candidates_evaluated,
            "raw_gap_rows_materialized": 0,
            "active_partition_integrity_mode": (
                "DEEP_QUICK_CHECK" if active_quick_checks_executed > 0 else "LIGHTWEIGHT_STATUS_READS"
            ),
        }

        return {
            "campaign_id": self.campaign_id,
            "campaign_age_seconds": max(0.0, (now - self.start_ms) / 1000),
            "depth_events": depth,
            "agg_trade_events": trades,
            "book_samples": book_samples,
            "aggregate_buckets": aggregate_buckets,
            "gap_affected_buckets": gap_affected_buckets,
            "closed_aggregate_buckets": closed_buckets,
            "complete_aggregate_buckets": complete_buckets,
            "aggregate_completeness_ratio": completeness_ratio,
            "aggregate_completeness_by_interval_ms": completeness_by_interval,
            "completeness_semantics": "COVERAGE_LIVENESS_SEQUENCE_VALIDITY_NO_GAP",
            "aggregation_intervals_ms": list(self.INTERVALS_MS),
            "gap_count": gap_count,
            "gap_type_counts": dict(sorted(gap_type_counts.items())),
            "resync_count": resync_count,
            "connected_seconds": connected_ms / 1000,
            "connected_seconds_by_stream": {
                key: value / 1000 for key, value in connected_ms_by_stream.items()
            },
            "coverage_evaluation_start_ms": evaluation_start,
            "expected_seconds": expected_ms / 1000,
            "legacy_coverage_unverified_seconds": max(
                0.0, (evaluation_start - self.start_ms) / 1000
            ),
            "uptime_ratio": uptime_ratio,
            "depth_sequence_continuity_ratio": continuity_ratio,
            "depth_sequence_valid_seconds": depth_valid_ms / 1000,
            "orphan_instance_count": orphan_count,
            "latest_heartbeat_ms": latest_heartbeat_ms,
            "heartbeat_age_seconds": (
                (now - latest_heartbeat_ms) / 1000
                if latest_heartbeat_ms is not None
                else None
            ),
            "rolling_reliability": rolling_reliability,
            "duplicate_count": duplicate_count,
            "conflict_count": conflict_count,
            "latency_ms": {
                "p50": pct(0.5),
                "p95": pct(0.95),
                "p99": pct(0.99),
                "raw_signed_receive_minus_exchange": {
                    "p50": pct(0.5),
                    "p95": pct(0.95),
                    "p99": pct(0.99),
                },
                "clock_adjusted_diagnostic": {
                    "p50": adjusted_pct(0.5),
                    "p95": adjusted_pct(0.95),
                    "p99": adjusted_pct(0.99),
                },
            },
            "clock": {
                "measured_at_ms": latest_clock[0] if latest_clock else None,
                "server_minus_local_midpoint_ms": offset,
                "measurement_rtt_ms": latest_clock[2] if latest_clock else None,
                "quality": latest_clock[3] if latest_clock else "NO_MEASUREMENT",
                "raw_timestamps_modified": False,
            },
            "partition_integrity": partition_audit,
            "chunk_integrity": integrity and bool(partition_audit["integrity_ok"]),
            "data_role": "FUTURE_RESEARCH_DATA",
            "state": "COLLECTING" if depth or trades else "INITIALIZING",
            "direction_claim": "NONE",
            "alpha_claim": "NONE",
            "status_performance": status_performance,
        }


async def run_daemon(campaign: MicrostructureCampaign, root: str | Path) -> None:
    import websockets

    store = MicrostructureStore(root, campaign.campaign_id, campaign.start_ms)
    client = BinancePublicClient(DataConfig())
    wait_seconds = max(0.0, (campaign.start_ms - int(time.time() * 1000)) / 1000)
    if wait_seconds:
        await asyncio.sleep(wait_seconds)
    instance_id = store.instance_start(int(time.time() * 1000))

    heartbeat_stop = threading.Event()

    def heartbeat_worker() -> None:
        while not heartbeat_stop.is_set():
            try:
                store.heartbeat(int(time.time() * 1000), instance_id)
            except Exception:  # noqa: BLE001,S110 - protect heartbeat worker against transient locks
                pass
            heartbeat_stop.wait(store.protocol.heartbeat_interval_ms / 1000)

    heartbeat_thread = threading.Thread(
        target=heartbeat_worker,
        name="microstructure-heartbeat",
        daemon=True,
    )
    heartbeat_thread.start()

    async def supervisor_loop() -> None:
        nonlocal heartbeat_thread
        while True:
            if not heartbeat_thread.is_alive() and not heartbeat_stop.is_set():
                heartbeat_thread = threading.Thread(
                    target=heartbeat_worker,
                    name="microstructure-heartbeat",
                    daemon=True,
                )
                heartbeat_thread.start()
            await asyncio.sleep(2.0)

    async def clock_loop() -> None:
        while True:
            request_send_ms = int(time.time() * 1000)
            try:
                response = await asyncio.to_thread(client._get, "/fapi/v1/time")
                response_receive_ms = int(time.time() * 1000)
                store.append_clock_measurement(
                    request_send_ms=request_send_ms,
                    response_receive_ms=response_receive_ms,
                    server_time_ms=int(response["serverTime"]),
                )
            except Exception:  # noqa: BLE001,S110 - stream coverage remains independent
                pass
            await asyncio.sleep(store.protocol.clock_interval_ms / 1000)

    async def trade_loop() -> None:
        async for socket in websockets.connect(campaign.trade_url, open_timeout=15):
            session_id = store.session_start(int(time.time() * 1000), "trade", instance_id)
            try:
                async for message in socket:
                    ns, ms = time.monotonic_ns(), int(time.time() * 1000)
                    store.append_trade(AggTrade.parse(json.loads(message)["data"], ms, ns))
                    await asyncio.sleep(0)
            except Exception as exc:  # noqa: BLE001 - disconnects and malformed frames are gaps
                store.gap(int(time.time() * 1000), "TRADE_DISCONNECT", type(exc).__name__)
                await asyncio.sleep(1)
            finally:
                store.session_end(int(time.time() * 1000), session_id)

    async def depth_loop() -> None:
        async for socket in websockets.connect(campaign.depth_url, open_timeout=15):
            session_id = store.session_start(int(time.time() * 1000), "depth", instance_id)
            book, buffered = LocalOrderBook(), []
            previous_best: tuple[float, float, float, float] | None = None
            snapshot_task: asyncio.Task[dict[str, Any]] | None = None
            try:
                async for message in socket:
                    ns, ms = time.monotonic_ns(), int(time.time() * 1000)
                    event = DepthEvent.parse(json.loads(message)["data"], ms, ns)
                    store.append_depth(event)
                    if book.update_id is None:
                        buffered.append(event)
                        if snapshot_task is None:
                            snapshot_task = asyncio.create_task(
                                asyncio.to_thread(
                                    client._get,
                                    "/fapi/v1/depth",
                                    {"symbol": campaign.symbol, "limit": 1000},
                                )
                            )
                        if not snapshot_task.done():
                            continue
                        try:
                            snapshot = snapshot_task.result()
                        except Exception as exc:  # noqa: BLE001 - preserve REST bootstrap fault
                            store.gap(
                                ms,
                                "REST_BOOTSTRAP_FAILURE",
                                f"{type(exc).__name__}: {exc}",
                            )
                            snapshot_task = None
                            continue
                        try:
                            book.bootstrap(snapshot, buffered)
                            latest_event = buffered[-1]
                            buffered.clear()
                            snapshot_task = None
                            previous_best = book.best()
                            store.append_book_sample(latest_event, book.stats(), None)
                            store.depth_sequence_state(ms, instance_id, True)
                        except SequenceGap as exc:
                            store.gap(ms, "DEPTH_BOOTSTRAP_FAILURE", str(exc))
                            snapshot_task = None
                            continue
                    else:
                        book.apply(event)
                        current_best = book.best()
                        ofi = (
                            event_ofi(previous_best, current_best)
                            if previous_best is not None and current_best is not None
                            else None
                        )
                        store.append_book_sample(event, book.stats(), ofi)
                        previous_best = current_best
                    await asyncio.sleep(0)
            except SequenceGap as exc:
                failed_at = int(time.time() * 1000)
                store.depth_sequence_state(failed_at, instance_id, False)
                store.gap(failed_at, "DEPTH_SEQUENCE_GAP", str(exc))
                await asyncio.sleep(1)
            except Exception as exc:  # noqa: BLE001 - any depth failure requires clean resync
                failed_at = int(time.time() * 1000)
                store.depth_sequence_state(failed_at, instance_id, False)
                store.gap(failed_at, "DEPTH_RECONNECT", type(exc).__name__)
                await asyncio.sleep(1)
            finally:
                if snapshot_task is not None and not snapshot_task.done():
                    snapshot_task.cancel()
                store.session_end(int(time.time() * 1000), session_id)

    try:
        await asyncio.gather(depth_loop(), trade_loop(), clock_loop(), supervisor_loop())
    finally:
        heartbeat_stop.set()
        heartbeat_thread.join(timeout=store.protocol.heartbeat_interval_ms / 1000 + 1)
        now_ms = int(time.time() * 1000)
        store.instance_end(now_ms, instance_id)
        store.finalize_partitions(now_ms)
