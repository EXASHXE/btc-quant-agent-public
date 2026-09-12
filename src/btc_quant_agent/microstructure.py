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


class MicrostructureStore:
    INTERVALS_MS = (1_000, 60_000, 900_000)

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

    def _load_stats_cache(self) -> dict[str, dict[str, Any]]:
        if not self._stats_cache_path.exists():
            return {}
        try:
            data = json.loads(self._stats_cache_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): dict(v) for k, v in data.items() if isinstance(v, dict)}
            return {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_stats_cache(self, cache: dict[str, dict[str, Any]]) -> None:
        try:
            publish_bytes(self._stats_cache_path, json.dumps(cache).encode("utf-8"))
        except (OSError, PublicationConflict):
            pass

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

    def partition_integrity_audit(self) -> dict[str, Any]:
        manifest = self._manifest()
        drift: list[str] = []
        missing: list[str] = []
        for name, metadata in manifest.items():
            path = self.root / name
            if not path.exists():
                missing.append(name)
            elif hashlib.sha256(path.read_bytes()).hexdigest() != metadata["sha256"]:
                drift.append(name)
        return {
            "manifest_path": str(self.finalized_manifest_path),
            "finalized_partition_count": len(manifest),
            "checksum_drift": drift,
            "missing_partitions": missing,
            "integrity_ok": not drift and not missing,
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
            connection.close()
            manifest[path.name] = {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
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

    def status(self, now_ms: int | None = None) -> dict[str, Any]:
        now = now_ms or int(time.time() * 1000)
        depth = trades = book_samples = aggregate_buckets = 0
        duplicate_count = conflict_count = orphan_count = 0
        latencies: list[int] = []
        segments: dict[str, list[tuple[int, int]]] = {"depth": [], "trade": []}
        depth_valid_segments: list[tuple[int, int]] = []
        gap_rows: list[tuple[int, int, str]] = []
        clocks: list[tuple[int, float, int, str]] = []
        latest_heartbeat_ms: int | None = None
        integrity = True
        stats_cache = self._load_stats_cache()
        cache_dirty = False
        for path in sorted(self.root.glob("microstructure-*.sqlite3")):
            st = path.stat()
            cache_key = f"{path.name}:{st.st_mtime_ns}:{st.st_size}"
            if cache_key in stats_cache:
                cached = stats_cache[cache_key]
                depth += cached["depth"]
                trades += cached["trades"]
                gap_rows += [tuple(g) for g in cached["gap_rows"]]
                book_samples += cached["book_samples"]
                aggregate_buckets += cached["aggregate_buckets"]
                duplicate_count += cached["duplicate_count"]
                conflict_count += cached["conflict_count"]
                for stream_name, segs in cached["segments"].items():
                    segments[stream_name].extend((int(start), min(now, int(end))) for start, end in segs)
                depth_valid_segments.extend((int(start), min(now, int(end))) for start, end in cached["depth_valid_segments"])
                orphan_count += cached["orphan_count"]
                if cached["latest_heartbeat_ms"] is not None:
                    latest_heartbeat_ms = max(latest_heartbeat_ms or cached["latest_heartbeat_ms"], cached["latest_heartbeat_ms"])
                clocks += [tuple(c) for c in cached["clocks"]]
                integrity = integrity and cached["integrity"]
                latencies += cached["latencies"]
                continue

            try:
                connection = sqlite3.connect(path, timeout=30.0)
                tables = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                cur_depth = int(connection.execute("SELECT count(*) FROM depth_events").fetchone()[0])
                cur_trades = int(connection.execute("SELECT count(*) FROM agg_trades").fetchone()[0])
                cur_gap_rows = [
                    (int(start), int(end), str(kind))
                    for start, end, kind in connection.execute(
                        "SELECT start_ms,end_ms,kind FROM gaps"
                    )
                ]
                cur_book_samples = int(
                    connection.execute("SELECT count(*) FROM book_samples").fetchone()[0]
                )
                cur_aggregate_buckets = int(
                    connection.execute("SELECT count(*) FROM aggregates").fetchone()[0]
                )
                cur_duplicate_count = 0
                cur_conflict_count = 0
                for name, value in connection.execute("SELECT name,value FROM audit_counters"):
                    if str(name).startswith("duplicate_"):
                        cur_duplicate_count += int(value)
                    elif str(name).startswith("conflict_"):
                        cur_conflict_count += int(value)
                cur_segments: dict[str, list[tuple[int, int]]] = {"depth": [], "trade": []}
                cur_depth_valid_segments: list[tuple[int, int]] = []
                if "coverage_segments" in tables:
                    for stream, start, end, valid in connection.execute(
                        """SELECT stream,start_ms,end_ms,sequence_valid
                        FROM coverage_segments"""
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
                cur_clocks: list[tuple[int, float, int, str]] = []
                if "clock_measurements" in tables:
                    cur_clocks = [
                        (int(measured), float(offset), int(rtt), str(quality))
                        for measured, offset, rtt, quality in connection.execute(
                            """SELECT measured_at_ms,offset_ms,rtt_ms,quality
                            FROM clock_measurements"""
                        )
                    ]
                cur_integrity = connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
                cur_latencies = [
                    int(a) - int(b)
                    for a, b in connection.execute(
                        "SELECT receive_time_ms,event_time_ms FROM agg_trades ORDER BY aggregate_trade_id DESC LIMIT 5000"
                    )
                ]
                connection.close()

                stats_cache[cache_key] = {
                    "depth": cur_depth,
                    "trades": cur_trades,
                    "gap_rows": cur_gap_rows,
                    "book_samples": cur_book_samples,
                    "aggregate_buckets": cur_aggregate_buckets,
                    "duplicate_count": cur_duplicate_count,
                    "conflict_count": cur_conflict_count,
                    "segments": cur_segments,
                    "depth_valid_segments": cur_depth_valid_segments,
                    "orphan_count": cur_orphan_count,
                    "latest_heartbeat_ms": cur_latest_heartbeat_ms,
                    "clocks": cur_clocks,
                    "integrity": cur_integrity,
                    "latencies": cur_latencies,
                }
                cache_dirty = True

                depth += cur_depth
                trades += cur_trades
                gap_rows += cur_gap_rows
                book_samples += cur_book_samples
                aggregate_buckets += cur_aggregate_buckets
                duplicate_count += cur_duplicate_count
                conflict_count += cur_conflict_count
                for stream_name, segs in cur_segments.items():
                    segments[stream_name].extend((start, min(now, end)) for start, end in segs)
                depth_valid_segments.extend((start, min(now, end)) for start, end in cur_depth_valid_segments)
                orphan_count += cur_orphan_count
                if cur_latest_heartbeat_ms is not None:
                    latest_heartbeat_ms = max(latest_heartbeat_ms or cur_latest_heartbeat_ms, cur_latest_heartbeat_ms)
                clocks += cur_clocks
                integrity = integrity and cur_integrity
                latencies += cur_latencies
            except sqlite3.DatabaseError:
                integrity = False
        if cache_dirty:
            self._save_stats_cache(stats_cache)
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
        connected_ms = min(connected_ms_by_stream.values())
        uptime_ratio = min(1.0, connected_ms / expected_ms) if expected_ms else 0.0
        depth_valid_ms = self._covered_ms(depth_valid_segments, evaluation_start, now)
        depth_connected_ms = connected_ms_by_stream["depth"]
        continuity_ratio = depth_valid_ms / depth_connected_ms if depth_connected_ms else 0.0

        bucket_candidates: set[tuple[int, int]] = set()
        if evaluation_start < now:
            for interval in self.INTERVALS_MS:
                first = evaluation_start // interval * interval
                latest_closed = now // interval * interval - interval
                bucket_candidates.update(
                    (interval, start)
                    for start in range(first, latest_closed + 1, interval)
                )
        closed_buckets = complete_buckets = gap_affected_buckets = 0
        completeness_by_interval: dict[str, dict[str, int | float]] = {}
        def _merge_intervals(segs: list[tuple[int, int]]) -> list[tuple[int, int]]:
            if not segs:
                return []
            ordered = sorted(segs)
            merged: list[list[int]] = []
            for s, e in ordered:
                if e <= s:
                    continue
                if not merged:
                    merged.append([s, e])
                elif s <= merged[-1][1]:
                    merged[-1][1] = max(merged[-1][1], e)
                else:
                    merged.append([s, e])
            return [(s, e) for s, e in merged]

        def _fast_covered(merged: list[tuple[int, int]], start_ms: int, end_ms: int) -> int:
            if not merged or end_ms <= start_ms:
                return 0
            idx = bisect.bisect_right(merged, (start_ms, 10**18)) - 1
            idx = max(idx, 0)
            covered = 0
            for s, e in merged[idx:]:
                if s >= end_ms:
                    break
                overlap_s = max(start_ms, s)
                overlap_e = min(end_ms, e)
                if overlap_e > overlap_s:
                    covered += overlap_e - overlap_s
            return covered

        def _fast_has_gap(merged_gaps: list[tuple[int, int]], start_ms: int, end_ms: int) -> bool:
            if not merged_gaps or end_ms <= start_ms:
                return False
            idx = bisect.bisect_right(merged_gaps, (start_ms, 10**18)) - 1
            idx = max(idx, 0)
            for s, e in merged_gaps[idx:]:
                if s >= end_ms:
                    break
                if s < end_ms and e >= start_ms:
                    return True
            return False

        merged_trade = _merge_intervals(segments["trade"])
        merged_depth = _merge_intervals(segments["depth"])
        merged_valid = _merge_intervals(depth_valid_segments)
        merged_gaps = _merge_intervals([(g[0], g[1]) for g in gap_rows])

        for interval in self.INTERVALS_MS:
            interval_candidates = sorted(
                start for candidate_interval, start in bucket_candidates if candidate_interval == interval
            )
            interval_complete = interval_gap = 0
            for start in interval_candidates:
                end = start + interval
                trade_ratio = _fast_covered(merged_trade, start, end) / interval
                depth_ratio = _fast_covered(merged_depth, start, end) / interval
                valid_ratio = _fast_covered(merged_valid, start, end) / interval
                gap_overlap = _fast_has_gap(merged_gaps, start, end)
                interval_gap += int(gap_overlap)
                interval_complete += int(
                    trade_ratio >= self.protocol.minimum_trade_coverage
                    and depth_ratio >= self.protocol.minimum_depth_coverage
                    and valid_ratio >= self.protocol.minimum_depth_valid_coverage
                    and not gap_overlap
                )
            closed_buckets += len(interval_candidates)
            complete_buckets += interval_complete
            gap_affected_buckets += interval_gap
            completeness_by_interval[str(interval)] = {
                "closed": len(interval_candidates),
                "complete": interval_complete,
                "ratio": interval_complete / len(interval_candidates)
                if interval_candidates
                else 0.0,
            }
        completeness_ratio = complete_buckets / closed_buckets if closed_buckets else 0.0
        gap_types = Counter(kind for _, _, kind in gap_rows)
        resync_types = {
            "DEPTH_SEQUENCE_GAP",
            "DEPTH_BOOTSTRAP_FAILURE",
            "DEPTH_RECONNECT",
            "REST_BOOTSTRAP_FAILURE",
            "DEPTH_GAP_RESYNC",
        }
        resync_count = sum(count for kind, count in gap_types.items() if kind in resync_types)
        latest_clock = max(clocks, default=None, key=lambda value: value[0])
        offset = latest_clock[1] if latest_clock is not None else None
        adjusted = sorted(value + offset for value in latencies) if offset is not None else []

        def adjusted_pct(value: float) -> float | None:
            return adjusted[min(len(adjusted) - 1, int(value * len(adjusted)))] if adjusted else None

        partition_audit = self.partition_integrity_audit()

        rolling_reliability: dict[str, dict[str, Any]] = {}
        for label, window_ms in (("24h", 86_400_000), ("7d", 7 * 86_400_000)):
            window_start = max(evaluation_start, now - window_ms)
            window_expected = max(0, now - window_start)
            trade_covered = self._covered_ms(segments["trade"], window_start, now)
            depth_covered = self._covered_ms(segments["depth"], window_start, now)
            valid_covered = self._covered_ms(depth_valid_segments, window_start, now)
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
                "gap_count": sum(
                    gap_start < now and gap_end >= window_start
                    for gap_start, gap_end, _ in gap_rows
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
            "gap_count": len(gap_rows),
            "gap_type_counts": dict(sorted(gap_types.items())),
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
