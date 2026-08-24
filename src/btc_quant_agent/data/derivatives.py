from __future__ import annotations

import csv
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import asdict, fields, replace
from pathlib import Path
from typing import Any

from ..config import DataConfig
from ..domain import DerivativesSnapshot

DERIVATIVE_FIELDS = [field.name for field in fields(DerivativesSnapshot)]


def _available(timestamp_ms: int | None, decision_time_ms: int, max_age_seconds: int) -> bool:
    if timestamp_ms is None or timestamp_ms > decision_time_ms:
        return False
    return decision_time_ms - timestamp_ms <= max_age_seconds * 1000


def sanitize_derivatives(
    snapshot: DerivativesSnapshot | None,
    decision_time_ms: int,
    config: DataConfig,
    *,
    include_order_book: bool = True,
) -> tuple[DerivativesSnapshot | None, tuple[str, ...]]:
    """Remove stale/future fields before any feature scoring or risk calculation."""
    if snapshot is None or snapshot.observed_at_ms > decision_time_ms:
        return None, ("snapshot",)

    stale: list[str] = []
    updates: dict[str, Any] = {}

    groups = (
        (
            "open_interest",
            snapshot.open_interest_time_ms,
            config.oi_stale_seconds,
            ("open_interest", "open_interest_change_pct"),
        ),
        (
            "funding",
            snapshot.funding_time_ms,
            config.funding_stale_seconds,
            ("funding_rate",),
        ),
        (
            "taker",
            snapshot.taker_time_ms,
            config.derivatives_stale_seconds,
            ("taker_buy_sell_ratio",),
        ),
        (
            "basis",
            snapshot.basis_time_ms,
            config.derivatives_stale_seconds,
            ("basis_rate",),
        ),
        (
            "long_short",
            snapshot.long_short_time_ms,
            config.derivatives_stale_seconds,
            ("long_short_account_ratio",),
        ),
    )
    for name, timestamp_ms, max_age, names in groups:
        if not _available(timestamp_ms, decision_time_ms, max_age):
            stale.append(name)
            updates.update({field_name: None for field_name in names})

    aggregate_available = _available(
        snapshot.observed_at_ms, decision_time_ms, config.derivatives_stale_seconds
    )
    if not aggregate_available:
        stale.append("snapshot")
        updates.update(
            {
                "mark_price": None,
                "index_price": None,
                "premium_bps": None,
            }
        )

    order_book_available = include_order_book and _available(
        snapshot.order_book_time_ms, decision_time_ms, config.derivatives_stale_seconds
    )
    if not order_book_available:
        if include_order_book:
            stale.append("order_book")
        updates.update({"order_book_imbalance": None, "spread_bps": None})

    return replace(snapshot, **updates), tuple(dict.fromkeys(stale))


class HistoricalDerivativeStore:
    """Immutable backward as-of store for historical derivatives snapshots."""

    def __init__(self, snapshots: Sequence[DerivativesSnapshot]):
        self._snapshots = tuple(sorted(snapshots, key=lambda item: item.observed_at_ms))
        if len({item.observed_at_ms for item in self._snapshots}) != len(self._snapshots):
            raise ValueError("duplicate derivative observed_at_ms")
        self._timestamps = tuple(item.observed_at_ms for item in self._snapshots)

    def snapshot_at(
        self,
        decision_time_ms: int,
        config: DataConfig,
        *,
        include_order_book: bool = False,
    ) -> DerivativesSnapshot | None:
        index = bisect_right(self._timestamps, decision_time_ms) - 1
        selected = self._snapshots[index] if index >= 0 else None
        sanitized, _ = sanitize_derivatives(
            selected, decision_time_ms, config, include_order_book=include_order_book
        )
        return sanitized

    @classmethod
    def from_csv(cls, path: str | Path) -> HistoricalDerivativeStore:
        with Path(path).open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        return cls.from_rows(rows)

    @classmethod
    def from_rows(cls, rows: Sequence[dict[str, Any]]) -> HistoricalDerivativeStore:
        snapshots: list[DerivativesSnapshot] = []
        integer_fields = {
            "observed_at_ms",
            "funding_time_ms",
            "open_interest_time_ms",
            "taker_time_ms",
            "basis_time_ms",
            "long_short_time_ms",
            "order_book_time_ms",
        }
        for row in rows:
            values: dict[str, Any] = {}
            for name in DERIVATIVE_FIELDS:
                raw = row.get(name)
                if raw in (None, ""):
                    values[name] = None
                elif name in integer_fields:
                    values[name] = int(str(raw))
                else:
                    values[name] = float(str(raw))
            if values["observed_at_ms"] is None:
                raise ValueError("observed_at_ms is required")
            snapshots.append(DerivativesSnapshot(**values))
        return cls(snapshots)

    def as_rows(self) -> list[dict[str, Any]]:
        return [asdict(snapshot) for snapshot in self._snapshots]

    def as_snapshots(self) -> tuple[DerivativesSnapshot, ...]:
        return self._snapshots


def write_historical_derivatives_csv(
    path: str | Path, snapshots: Sequence[DerivativesSnapshot]
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DERIVATIVE_FIELDS)
        writer.writeheader()
        for snapshot in snapshots:
            writer.writerow(asdict(snapshot))
