"""Append-only durable segment logger, hash-chaining, atomic manifest roll, and torn-write recovery."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .contracts import (
    MarketEventV1,
    canonical_json_bytes,
    compute_sha256,
)

GENESIS_HASH: str = "0" * 64
DEFAULT_MAX_RECORDS_PER_SEGMENT: int = 5_000


class DurabilityError(RuntimeError):
    """Raised when segment integrity or hash chain is broken."""


def compute_entry_hash(
    index: int,
    prev_hash: str,
    payload_sha256: str,
    event_sha256: str,
) -> str:
    """Compute deterministic cryptographic hash of a segment entry."""
    data = f"{index}:{prev_hash}:{payload_sha256}:{event_sha256}".encode()
    return hashlib.sha256(data).hexdigest()


class SegmentWriter:
    """Manages an append-only JSONL segment log with cryptographic hash chain and atomic manifest roll."""

    def __init__(
        self,
        base_dir: str | Path,
        epoch: str,
        feed_id: str = "BTCUSDT_BINANCE_USDT_M_PERP",
        max_records_per_segment: int = DEFAULT_MAX_RECORDS_PER_SEGMENT,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.epoch = epoch
        self.feed_id = feed_id
        self.max_records_per_segment = max_records_per_segment

        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.segment_index: int = 0
        self.current_record_count: int = 0
        self.total_records_written: int = 0

        self.head_hash: str = GENESIS_HASH
        self.first_wall_utc_ms: int | None = None
        self.last_wall_utc_ms: int | None = None
        self.first_index: int | None = None
        self.last_index: int | None = None

        self._file_handle: Any = None
        self._current_segment_path: Path | None = None
        self._current_manifest_path: Path | None = None
        self.manifest_sha256: str = compute_sha256(GENESIS_HASH)

        self._open_new_segment()

    def _open_new_segment(self) -> None:
        """Close current segment if open, and initialize a new segment."""
        if self._file_handle is not None and not self._file_handle.closed:
            self._file_handle.flush()
            os.fsync(self._file_handle.fileno())
            self._file_handle.close()
            self._write_manifest()

        self.segment_index += 1
        self.current_record_count = 0
        self.first_wall_utc_ms = None
        self.last_wall_utc_ms = None
        self.first_index = None
        self.last_index = None

        seg_name = f"segment_{self.epoch}_{self.segment_index:06d}.jsonl"
        man_name = f"manifest_{self.epoch}_{self.segment_index:06d}.json"
        self._current_segment_path = self.base_dir / seg_name
        self._current_manifest_path = self.base_dir / man_name

        self._file_handle = open(self._current_segment_path, "a", encoding="utf-8")  # noqa: SIM115
        self._write_manifest()

    def _write_manifest(self) -> None:
        """Write manifest atomically via .tmp and replace."""
        if self._current_manifest_path is None:
            return

        manifest_data: dict[str, Any] = {
            "epoch": self.epoch,
            "feed_id": self.feed_id,
            "segment_index": self.segment_index,
            "record_count": self.current_record_count,
            "first_index": self.first_index,
            "last_index": self.last_index,
            "first_wall_utc_ms": self.first_wall_utc_ms,
            "last_wall_utc_ms": self.last_wall_utc_ms,
            "head_hash": self.head_hash,
            "segment_filename": self._current_segment_path.name if self._current_segment_path else "",
        }
        manifest_bytes = canonical_json_bytes(manifest_data)
        manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
        manifest_data["manifest_sha256"] = manifest_sha
        self.manifest_sha256 = manifest_sha

        tmp_path = self._current_manifest_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(canonical_json_bytes(manifest_data).decode("utf-8"))
            f.flush()
            os.fsync(f.fileno())

        os.replace(tmp_path, self._current_manifest_path)

    def append_event(self, event: MarketEventV1) -> str:
        """Append an event to the segment log, updating the cryptographic hash chain."""
        if self.current_record_count >= self.max_records_per_segment:
            self._open_new_segment()

        index = self.total_records_written
        prev_h = self.head_hash
        event_sha = event.event_sha256()
        payload_sha = event.payload_sha256

        entry_h = compute_entry_hash(index, prev_h, payload_sha, event_sha)

        entry = {
            "index": index,
            "prev_hash": prev_h,
            "entry_hash": entry_h,
            "payload_sha256": payload_sha,
            "event": event.to_dict(),
        }

        line = canonical_json_bytes(entry).decode("utf-8") + "\n"
        self._file_handle.write(line)
        self._file_handle.flush()

        self.head_hash = entry_h
        self.current_record_count += 1
        self.total_records_written += 1

        if self.first_index is None:
            self.first_index = index
        self.last_index = index

        if self.first_wall_utc_ms is None:
            self.first_wall_utc_ms = event.observed_wall_utc_ms
        self.last_wall_utc_ms = event.observed_wall_utc_ms

        self._write_manifest()
        return entry_h

    def close(self) -> None:
        """Flush and close active segment."""
        if self._file_handle is not None and not self._file_handle.closed:
            self._file_handle.flush()
            os.fsync(self._file_handle.fileno())
            self._file_handle.close()
            self._write_manifest()


class SegmentReader:
    """Reads segment files, verifies hash chains and manifests, and recovers from torn writes."""

    @staticmethod
    def read_manifest(manifest_path: str | Path) -> dict[str, Any]:
        """Read and verify manifest checksum."""
        p = Path(manifest_path)
        if not p.exists():
            raise DurabilityError(f"Manifest not found: {p}")
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)

        expected_sha = data.get("manifest_sha256")
        data_copy = dict(data)
        data_copy.pop("manifest_sha256", None)
        computed_sha = hashlib.sha256(canonical_json_bytes(data_copy)).hexdigest()
        if expected_sha != computed_sha:
            raise DurabilityError(f"Manifest sha mismatch in {p}: expected {expected_sha}, computed {computed_sha}")
        return data

    @staticmethod
    def read_segment(
        segment_path: str | Path,
        expected_prev_hash: str = GENESIS_HASH,
        auto_repair_torn_write: bool = False,
    ) -> tuple[list[MarketEventV1], str]:
        """Read a segment file and verify the cryptographic hash-chain.

        Returns tuple of (events, head_hash).
        If auto_repair_torn_write is True, corrupt trailing lines are quarantined.
        """
        p = Path(segment_path)
        if not p.exists():
            raise DurabilityError(f"Segment file not found: {p}")

        events: list[MarketEventV1] = []
        current_prev_hash = expected_prev_hash

        valid_lines: list[str] = []
        corrupted_lines: list[str] = []

        with open(p, "r", encoding="utf-8") as f:
            for line_no, raw_line in enumerate(f, start=1):
                raw_str = raw_line.strip()
                if not raw_str:
                    continue

                try:
                    entry = json.loads(raw_str)
                    idx = entry["index"]
                    prev_h = entry["prev_hash"]
                    entry_h = entry["entry_hash"]
                    payload_sha = entry["payload_sha256"]
                    event_dict = entry["event"]

                    if prev_h != current_prev_hash:
                        raise DurabilityError(
                            f"Hash chain break at line {line_no}: expected prev {current_prev_hash}, found {prev_h}"
                        )

                    event = MarketEventV1.from_dict(event_dict)
                    expected_entry_h = compute_entry_hash(idx, prev_h, payload_sha, event.event_sha256())
                    if entry_h != expected_entry_h:
                        raise DurabilityError(
                            f"Entry hash corruption at line {line_no}: expected {expected_entry_h}, found {entry_h}"
                        )

                    events.append(event)
                    current_prev_hash = entry_h
                    valid_lines.append(raw_str + "\n")
                except Exception as exc:
                    if auto_repair_torn_write:
                        corrupted_lines.append(raw_line)
                        break
                    raise DurabilityError(f"Segment corruption at line {line_no}: {exc}") from exc

        if corrupted_lines and auto_repair_torn_write:
            # Quarantine and truncate
            quarantine_path = p.with_suffix(".quarantine")
            with open(quarantine_path, "a", encoding="utf-8") as qf:
                qf.writelines(corrupted_lines)

            # Rewrite valid prefix atomically
            tmp_p = p.with_suffix(".repaired.tmp")
            with open(tmp_p, "w", encoding="utf-8") as rf:
                rf.writelines(valid_lines)
                rf.flush()
                os.fsync(rf.fileno())
            os.replace(tmp_p, p)

        return events, current_prev_hash
