"""Synthetic Parquet fixture builders for ephemeral temporary-directory testing.

All fixtures use purely invented toy integers/floats and are written only inside
``tempfile.TemporaryDirectory()`` trees during tests.
"""

from __future__ import annotations

import os
import struct
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from scripts.strategy_research.p2_s3_footer_reader.constants import (
    PARQUET_MAGIC_BYTES,
    S3_SINGLE_PILOT_COMPONENTS,
)


def build_synthetic_parquet_bytes(
    *,
    num_rows: int = 8,
    write_statistics: bool = True,
    custom_kv_metadata: dict[bytes, bytes] | None = None,
    compression: str = "SNAPPY",
) -> bytes:
    """Build an in-memory synthetic Parquet byte buffer with invented toy values."""
    base_ts = 1_614_556_800_000  # 2021-03-01T00:00:00Z in ms (synthetic sequence)
    table = pa.table(
        {
            "open_time_ms": pa.array(
                [base_ts + i * 60_000 for i in range(num_rows)],
                type=pa.int64(),
            ),
            "open": pa.array([100.0 + float(i) for i in range(num_rows)], type=pa.float64()),
            "high": pa.array([101.0 + float(i) for i in range(num_rows)], type=pa.float64()),
            "low": pa.array([99.0 + float(i) for i in range(num_rows)], type=pa.float64()),
            "close": pa.array([100.5 + float(i) for i in range(num_rows)], type=pa.float64()),
            "volume": pa.array([10.0 * float(i + 1) for i in range(num_rows)], type=pa.float64()),
        }
    )
    if custom_kv_metadata:
        existing = table.schema.metadata or {}
        merged = {**existing, **custom_kv_metadata}
        table = table.replace_schema_metadata(merged)

    sink = pa.BufferOutputStream()
    pq.write_table(
        table,
        sink,
        compression=compression,
        write_statistics=write_statistics,
    )
    return sink.getvalue().to_pybytes()


def materialize_synthetic_pilot_tree(
    temp_root: str | Path,
    *,
    parquet_bytes: bytes | None = None,
) -> Path:
    """Create ``research/BTCUSDT/1m/year=2021/month=03/data.parquet`` under temp_root."""
    root_path = Path(temp_root)
    rel_dir = root_path.joinpath(*S3_SINGLE_PILOT_COMPONENTS[:-1])
    os.makedirs(rel_dir, exist_ok=True)
    leaf_path = rel_dir / S3_SINGLE_PILOT_COMPONENTS[-1]
    payload = (
        parquet_bytes
        if parquet_bytes is not None
        else build_synthetic_parquet_bytes(
            num_rows=8,
            write_statistics=True,
            custom_kv_metadata={b"synthetic_secret_min_price": b"99.0"},
        )
    )
    leaf_path.write_bytes(payload)
    return leaf_path


def craft_custom_trailer_parquet_bytes(
    *,
    body_and_footer_bytes: bytes,
    declared_footer_len: int,
    trailer_magic: bytes = PARQUET_MAGIC_BYTES,
) -> bytes:
    """Craft a synthetic file buffer with an explicit trailer length and magic."""
    trailer = struct.pack("<i4s", declared_footer_len, trailer_magic)
    return PARQUET_MAGIC_BYTES + body_and_footer_bytes + trailer


__all__ = [
    "build_synthetic_parquet_bytes",
    "craft_custom_trailer_parquet_bytes",
    "materialize_synthetic_pilot_tree",
]
