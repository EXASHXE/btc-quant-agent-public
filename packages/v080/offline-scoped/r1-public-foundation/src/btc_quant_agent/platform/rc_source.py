"""Synthetic-only source boundary with immutable raw/normalized receipt binding."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from queue import Full, Queue
from typing import Literal

from pydantic import Field, model_validator

from ..domain import Candle
from .core import fingerprint
from .swing import ClosedBar, Contract, INTERVALS, SwingPolicy

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def raw_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("RAW_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


class Receipt(Contract):
    schema_version: Literal["PROGRAM_A_SYNTHETIC_RECEIPT_V1"] = "PROGRAM_A_SYNTHETIC_RECEIPT_V1"
    venue: Literal["SYNTHETIC_SIMULATOR"] = "SYNTHETIC_SIMULATOR"
    bar: ClosedBar
    raw: str
    raw_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    normalized_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @property
    def identity(self) -> str:
        c, b = self.bar.candle, self.bar
        return fingerprint([b.source_id, self.venue, c.symbol, c.interval, c.open_time_ms, b.revision])

    @model_validator(mode="after")
    def binding(self):
        if self.raw_sha256 != raw_hash(self.raw) or self.normalized_sha256 != fingerprint(
            self.bar.model_dump(mode="json")
        ):
            raise ValueError("SOURCE_HASH_BINDING_MISMATCH")
        if decode(self.raw) != self.bar:
            raise ValueError("RAW_NORMALIZED_CONTENT_MISMATCH")
        return self


def decode(raw: str) -> ClosedBar:
    value = json.loads(raw, object_pairs_hook=strict_object,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("RAW_NONFINITE")))
    expected = {"schema", "venue", "source_id", "candle", "source_event_ms", "received_ms",
                "available_ms", "durable_ms", "revision"}
    if (not isinstance(value, dict) or set(value) != expected
            or value["schema"] != "SYNTHETIC_CLOSED_BAR_V1"
            or value["venue"] != "SYNTHETIC_SIMULATOR"
            or value["source_id"] != "PROGRAM_A_SYNTHETIC_V1"):
        raise ValueError("SYNTHETIC_SOURCE_SCHEMA_OR_AUTHORITY_REQUIRED")
    candle = Candle(**value["candle"])
    if candle.symbol not in SYMBOLS:
        raise ValueError("SYMBOL_OUT_OF_SCOPE")
    bar = ClosedBar(candle=candle, **{k: value[k] for k in (
        "source_id", "source_event_ms", "received_ms", "available_ms", "durable_ms", "revision")})
    if reason := bar.reason(bar.durable_ms, SwingPolicy()):
        if reason != "AVAILABILITY_SLA_MISSED" or not bar.revision:
            raise ValueError(reason)
    return bar


def normalize(raw: str) -> Receipt:
    bar = decode(raw)
    return Receipt(bar=bar, raw=raw, raw_sha256=raw_hash(raw),
                   normalized_sha256=fingerprint(bar.model_dump(mode="json")))


def asof(receipts: Sequence[Receipt], symbol: str, trigger_ms: int, decision_ms: int):
    """Keep causal admission order, deduplicate exact receipts, veto visible revisions/gaps."""
    seen, rows, errors, periods = {}, [], [], {}
    for receipt in receipts:
        b = receipt.bar
        if b.candle.symbol != symbol or b.end_ms > trigger_ms or b.durable_ms > decision_ms:
            continue
        receipt = Receipt.model_validate_json(receipt.model_dump_json())
        if receipt.identity in seen:
            if seen[receipt.identity] != receipt.raw_sha256:
                errors.append("IMMUTABLE_RECEIPT_CONFLICT")
            continue
        seen[receipt.identity] = receipt.raw_sha256
        key = (b.candle.interval, b.candle.open_time_ms)
        if key in periods:
            errors.append("VISIBLE_REVISION_UNRESOLVED")
        periods[key] = b.revision
        if b.revision:
            errors.append("VISIBLE_REVISION_REQUIRES_CANCEL_AND_REQUALIFICATION")
        rows.append(receipt)
    for interval in INTERVALS:
        members = [r.bar for r in rows if r.bar.candle.interval == interval]
        ends = [b.end_ms for b in members]
        if ends and any(b - a != INTERVALS[interval] for a, b in zip(ends, ends[1:])):
            errors.append("GAP_OR_OUT_OF_ORDER:" + interval)
        if interval == "1H" and ends:
            if len(ends) < 2 or ends[-1] != trigger_ms:
                errors.append("OPTIONAL_CONFIRMATION_PREFIX_INCOMPLETE")
    return rows, tuple(dict.fromkeys(errors))


def admit_stream(store, receipts, *, burst=128):
    """Finite synchronous simulator inbox, bounded at the retained queue128 hard stop."""
    inbox = Queue(maxsize=128)
    admitted = 0
    batch = []
    for receipt in receipts:
        try:
            inbox.put_nowait(receipt)
        except Full as exc:
            store.stop("QUEUE128_EXHAUSTED_STICKY")
            raise ValueError("QUEUE128_EXHAUSTED_STICKY") from exc
        if inbox.qsize() >= burst:
            while not inbox.empty():
                batch.append(inbox.get_nowait())
            admitted += store.admit(batch)
            batch.clear()
    while not inbox.empty():
        batch.append(inbox.get_nowait())
    if batch:
        admitted += store.admit(batch)
    return admitted
