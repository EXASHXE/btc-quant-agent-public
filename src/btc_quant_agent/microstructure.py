from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import DataConfig
from .data.binance import BinancePublicClient


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

    def __init__(self, root: str | Path, campaign_id: str, start_ms: int) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.campaign_id = campaign_id
        self.start_ms = start_ms

    def _path(self, timestamp_ms: int) -> Path:
        day = datetime.fromtimestamp(timestamp_ms / 1000, UTC).strftime("%Y-%m-%d")
        return self.root / f"microstructure-{day}.sqlite3"

    @contextmanager
    def _connect(self, timestamp_ms: int) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._path(timestamp_ms), timeout=10)
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
            CREATE TABLE IF NOT EXISTS sessions(session_id TEXT PRIMARY KEY,start_ms INTEGER,
              end_ms INTEGER,status TEXT);
            CREATE TABLE IF NOT EXISTS audit_counters(name TEXT PRIMARY KEY,value INTEGER NOT NULL);
            """
        )
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def append_depth(self, event: DepthEvent) -> bool:
        payload = json.dumps(asdict(event), sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(payload.encode()).hexdigest()
        with self._connect(event.receive_time_ms) as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO depth_events VALUES(?,?,?,?,?,?)",
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
            """INSERT INTO audit_counters VALUES(?,1)
            ON CONFLICT(name) DO UPDATE SET value=value+1""",
            (name,),
        )

    def append_trade(self, trade: AggTrade) -> bool:
        digest = hashlib.sha256(json.dumps(asdict(trade), sort_keys=True).encode()).hexdigest()
        with self._connect(trade.receive_time_ms) as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO agg_trades VALUES(?,?,?,?,?,?,?,?,?,?)",
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
                "INSERT OR IGNORE INTO book_samples VALUES(?,?,?,?,?,?,?,?,?)",
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

    def gap(self, timestamp_ms: int, kind: str, detail: str) -> None:
        identity = int(time.time_ns())
        with self._connect(timestamp_ms) as connection:
            connection.execute(
                "INSERT INTO gaps VALUES(?,?,?,?,?)",
                (identity, timestamp_ms, timestamp_ms, kind, detail),
            )
            for interval in self.INTERVALS_MS:
                bucket = timestamp_ms // interval * interval
                connection.execute(
                    """INSERT INTO aggregates(interval_ms,bucket_start_ms,gap_count)
                    VALUES(?,?,1) ON CONFLICT(interval_ms,bucket_start_ms) DO UPDATE SET
                    gap_count=gap_count+1""",
                    (interval, bucket),
                )

    def session_start(self, timestamp_ms: int) -> str:
        session_id = f"{timestamp_ms}-{time.monotonic_ns()}"
        with self._connect(timestamp_ms) as connection:
            connection.execute(
                "INSERT INTO sessions VALUES(?,?,NULL,'CONNECTED')", (session_id, timestamp_ms)
            )
        return session_id

    def session_end(self, timestamp_ms: int, session_id: str) -> None:
        for path in sorted(self.root.glob("microstructure-*.sqlite3")):
            connection = sqlite3.connect(path)
            cursor = connection.execute(
                "UPDATE sessions SET end_ms=?,status='CLOSED' WHERE session_id=?",
                (timestamp_ms, session_id),
            )
            connection.commit()
            connection.close()
            if cursor.rowcount:
                return

    def closed_partition_manifest(self, now_ms: int | None = None) -> dict[str, str]:
        now = now_ms or int(time.time() * 1000)
        current_day = datetime.fromtimestamp(now / 1000, UTC).strftime("%Y-%m-%d")
        manifests: dict[str, str] = {}
        for path in sorted(self.root.glob("microstructure-*.sqlite3")):
            if path.stem.endswith(current_day):
                continue
            connection = sqlite3.connect(path)
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            connection.close()
            manifests[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest_path = self.root / "closed-partitions.sha256.json"
        manifest_path.write_text(
            json.dumps(manifests, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return manifests

    def status(self, now_ms: int | None = None) -> dict[str, Any]:
        now = now_ms or int(time.time() * 1000)
        depth = trades = gaps = book_samples = aggregate_buckets = 0
        gap_affected_buckets = 0
        closed_buckets = complete_buckets = duplicate_count = conflict_count = 0
        connected_ms = 0
        latencies: list[int] = []
        integrity = True
        for path in sorted(self.root.glob("microstructure-*.sqlite3")):
            try:
                connection = sqlite3.connect(path)
                depth += int(connection.execute("SELECT count(*) FROM depth_events").fetchone()[0])
                trades += int(connection.execute("SELECT count(*) FROM agg_trades").fetchone()[0])
                gaps += int(connection.execute("SELECT count(*) FROM gaps").fetchone()[0])
                book_samples += int(
                    connection.execute("SELECT count(*) FROM book_samples").fetchone()[0]
                )
                aggregate_buckets += int(
                    connection.execute("SELECT count(*) FROM aggregates").fetchone()[0]
                )
                gap_affected_buckets += int(
                    connection.execute(
                        "SELECT count(*) FROM aggregates WHERE gap_count > 0"
                    ).fetchone()[0]
                )
                for interval, start, trade_count, sample_count, gap_count in connection.execute(
                    """SELECT interval_ms,bucket_start_ms,trade_count,book_sample_count,gap_count
                    FROM aggregates"""
                ):
                    if int(start) + int(interval) <= now:
                        closed_buckets += 1
                        complete_buckets += int(
                            int(trade_count) > 0 and int(sample_count) > 0 and int(gap_count) == 0
                        )
                for name, value in connection.execute("SELECT name,value FROM audit_counters"):
                    if str(name).startswith("duplicate_"):
                        duplicate_count += int(value)
                    elif str(name).startswith("conflict_"):
                        conflict_count += int(value)
                for start, end in connection.execute("SELECT start_ms,end_ms FROM sessions"):
                    connected_ms += max(0, int(end or now) - int(start))
                integrity = (
                    integrity
                    and connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                )
                latencies += [
                    int(a) - int(b)
                    for a, b in connection.execute(
                        "SELECT receive_time_ms,event_time_ms FROM agg_trades"
                    )
                ]
                connection.close()
            except sqlite3.DatabaseError:
                integrity = False
        ordered = sorted(latencies)

        def pct(value: float) -> int | None:
            return ordered[min(len(ordered) - 1, int(value * len(ordered)))] if ordered else None

        expected_ms = max(0, now - self.start_ms)
        uptime_ratio = min(1.0, connected_ms / expected_ms) if expected_ms else 0.0
        continuity_ratio = book_samples / depth if depth else 0.0
        completeness_ratio = complete_buckets / closed_buckets if closed_buckets else 0.0

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
            "aggregation_intervals_ms": list(self.INTERVALS_MS),
            "gap_count": gaps,
            "resync_count": gaps,
            "connected_seconds": connected_ms / 1000,
            "expected_seconds": expected_ms / 1000,
            "uptime_ratio": uptime_ratio,
            "depth_sequence_continuity_ratio": continuity_ratio,
            "duplicate_count": duplicate_count,
            "conflict_count": conflict_count,
            "latency_ms": {"p50": pct(0.5), "p95": pct(0.95), "p99": pct(0.99)},
            "chunk_integrity": integrity,
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
    session_id = store.session_start(int(time.time() * 1000))

    async def trade_loop() -> None:
        async for socket in websockets.connect(campaign.trade_url, open_timeout=15):
            try:
                async for message in socket:
                    ns, ms = time.monotonic_ns(), int(time.time() * 1000)
                    store.append_trade(AggTrade.parse(json.loads(message)["data"], ms, ns))
            except Exception as exc:  # noqa: BLE001 - disconnects and malformed frames are gaps
                store.gap(int(time.time() * 1000), "TRADE_DISCONNECT", type(exc).__name__)
                await asyncio.sleep(1)

    async def depth_loop() -> None:
        async for socket in websockets.connect(campaign.depth_url, open_timeout=15):
            book, buffered = LocalOrderBook(), []
            previous_best: tuple[float, float, float, float] | None = None
            try:
                async for message in socket:
                    ns, ms = time.monotonic_ns(), int(time.time() * 1000)
                    event = DepthEvent.parse(json.loads(message)["data"], ms, ns)
                    store.append_depth(event)
                    if book.update_id is None:
                        buffered.append(event)
                        snapshot = await asyncio.to_thread(
                            client._get,
                            "/fapi/v1/depth",
                            {"symbol": campaign.symbol, "limit": 1000},
                        )
                        try:
                            book.bootstrap(snapshot, buffered)
                            latest_event = buffered[-1]
                            buffered.clear()
                            previous_best = book.best()
                            store.append_book_sample(latest_event, book.stats(), None)
                        except SequenceGap:
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
            except Exception as exc:  # noqa: BLE001 - any depth failure requires clean resync
                store.gap(int(time.time() * 1000), "DEPTH_GAP_RESYNC", type(exc).__name__)
                await asyncio.sleep(1)

    try:
        await asyncio.gather(depth_loop(), trade_loop())
    finally:
        now_ms = int(time.time() * 1000)
        store.session_end(now_ms, session_id)
        store.closed_partition_manifest(now_ms)
