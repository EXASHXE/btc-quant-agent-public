from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DataManifest:
    source: str
    retrieved_at_ms: int
    event_start_ms: int | None
    event_end_ms: int | None
    records: int
    field_coverage: dict[str, float]
    checksum_sha256: str
    known_gaps: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(
    dataset_path: str | Path,
    *,
    source: str,
    rows: Sequence[dict[str, Any]],
    timestamp_field: str,
    expected_interval_ms: int | None = None,
) -> DataManifest:
    timestamps = sorted(
        int(row[timestamp_field])
        for row in rows
        if row.get(timestamp_field) not in (None, "")
    )
    fields = sorted({key for row in rows for key in row})
    coverage = {
        field: round(
            sum(row.get(field) not in (None, "") for row in rows) / len(rows)
            if rows
            else 0.0,
            6,
        )
        for field in fields
    }
    gaps: list[str] = []
    if expected_interval_ms and timestamps:
        for previous, current in pairwise(timestamps):
            if current - previous > expected_interval_ms * 2:
                gaps.append(f"{previous}->{current}")
                if len(gaps) == 100:
                    gaps.append("additional gaps omitted")
                    break
    return DataManifest(
        source=source,
        retrieved_at_ms=int(time.time() * 1000),
        event_start_ms=timestamps[0] if timestamps else None,
        event_end_ms=timestamps[-1] if timestamps else None,
        records=len(rows),
        field_coverage=coverage,
        checksum_sha256=sha256_file(dataset_path),
        known_gaps=tuple(gaps),
    )


def write_manifest(path: str | Path, manifest: DataManifest) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(manifest.as_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
