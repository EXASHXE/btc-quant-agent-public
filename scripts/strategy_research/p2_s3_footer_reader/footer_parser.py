"""In-memory Parquet trailer and Thrift FileMetaData parser for P2 S3A.

Operates strictly on raw ``bytes`` already read into RAM via ``os.pread``.
Passing a filesystem path, ``PathLike``, integer file descriptor, or file stream
is rejected fail-closed with ``ParserInputViolationError``.

All embedded column statistics (``min``, ``max``, ``null_count``,
``distinct_count``) and custom ``key_value_metadata`` payloads are stripped
before returning ``SanitizedParquetFooterMetadata``.
"""

from __future__ import annotations

import struct
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from scripts.strategy_research.p2_s3_footer_reader.constants import (
    HEADER_STATUS_NOT_VERIFIED,
    MAX_FOOTER_READ_BYTES,
    MIN_VALID_PARQUET_FILE_SIZE_BYTES,
    PARQUET_HEADER_MAGIC_SIZE_BYTES,
    PARQUET_MAGIC_BYTES,
    PARQUET_TRAILER_SIZE_BYTES,
)
from scripts.strategy_research.p2_s3_footer_reader.errors import (
    CorruptedParquetFooterError,
    InvalidParquetFooterExtentError,
    InvalidParquetFooterLengthError,
    InvalidParquetMagicError,
    ParserInputViolationError,
    ShortReadOrTruncatedFileError,
)
from scripts.strategy_research.p2_s3_footer_reader.types import (
    ColumnSchemaSummary,
    SanitizedParquetFooterMetadata,
)


def _assert_strict_bytes_input(value: Any, *, arg_name: str) -> bytes:
    """Reject str, PathLike, int FD, bytearray, memoryview, or stream objects."""
    if type(value) is not bytes:
        raise ParserInputViolationError(
            f"Argument {arg_name!r} must be exact type 'bytes' in RAM, got "
            f"{type(value).__name__!r}. Passing paths, FDs, or streams is forbidden."
        )
    return value


def validate_parquet_trailer_and_extent(
    trailer_bytes: Any,
    *,
    file_size_bytes: int,
    max_footer_bytes: int = MAX_FOOTER_READ_BYTES,
) -> int:
    """Validate the 8-byte Parquet trailer and return the verified footer_len.

    Enforces:
    1. ``file_size_bytes >= MIN_VALID_PARQUET_FILE_SIZE_BYTES`` (13 bytes).
    2. ``len(trailer_bytes) == 8`` and ``type(trailer_bytes) is bytes``.
    3. Last 4 bytes of trailer equal ``b"PAR1"``.
    4. Little-endian signed 32-bit ``footer_len`` satisfies ``1 <= footer_len <= max_footer_bytes``.
    5. ``footer_len + 8 <= file_size_bytes - 4`` (leaving >= 4 bytes for the file header).
    """
    raw_trailer = _assert_strict_bytes_input(trailer_bytes, arg_name="trailer_bytes")
    if file_size_bytes < MIN_VALID_PARQUET_FILE_SIZE_BYTES:
        raise ShortReadOrTruncatedFileError(
            f"File size {file_size_bytes} bytes is smaller than minimum valid "
            f"Parquet size ({MIN_VALID_PARQUET_FILE_SIZE_BYTES} bytes)."
        )
    if len(raw_trailer) != PARQUET_TRAILER_SIZE_BYTES:
        raise ShortReadOrTruncatedFileError(
            f"Parquet trailer must be exactly {PARQUET_TRAILER_SIZE_BYTES} bytes, "
            f"got {len(raw_trailer)} bytes."
        )

    footer_len, magic = struct.unpack("<i4s", raw_trailer)
    if magic != PARQUET_MAGIC_BYTES:
        raise InvalidParquetMagicError(
            f"Invalid Parquet trailer magic {magic!r}; expected {PARQUET_MAGIC_BYTES!r}."
        )
    if footer_len <= 0:
        raise InvalidParquetFooterLengthError(
            f"Invalid non-positive Parquet footer length: {footer_len}."
        )
    if footer_len > max_footer_bytes or footer_len > MAX_FOOTER_READ_BYTES:
        raise InvalidParquetFooterLengthError(
            f"Parquet footer length {footer_len} exceeds hard budget "
            f"min({max_footer_bytes}, {MAX_FOOTER_READ_BYTES})."
        )
    if footer_len + PARQUET_TRAILER_SIZE_BYTES > (
        file_size_bytes - PARQUET_HEADER_MAGIC_SIZE_BYTES
    ):
        raise InvalidParquetFooterExtentError(
            f"Parquet footer_len ({footer_len}) + trailer (8) overlaps 4-byte header "
            f"for file_size_bytes={file_size_bytes}."
        )
    return int(footer_len)


def parse_in_memory_parquet_footer(
    footer_bytes: Any,
    trailer_bytes: Any,
    *,
    file_size_bytes: int,
    max_footer_bytes: int = MAX_FOOTER_READ_BYTES,
) -> SanitizedParquetFooterMetadata:
    """Parse Parquet FileMetaData strictly from in-memory footer + trailer bytes.

    Constructs an in-memory ``pyarrow.BufferReader`` over ``b"PAR1" + footer + trailer``
    so that ``pyarrow.parquet.read_metadata`` never touches the filesystem or any OS FD,
    and never sees any row-group data pages.
    """
    raw_footer = _assert_strict_bytes_input(footer_bytes, arg_name="footer_bytes")
    raw_trailer = _assert_strict_bytes_input(trailer_bytes, arg_name="trailer_bytes")

    expected_footer_len = validate_parquet_trailer_and_extent(
        raw_trailer,
        file_size_bytes=file_size_bytes,
        max_footer_bytes=max_footer_bytes,
    )
    if len(raw_footer) != expected_footer_len:
        raise ShortReadOrTruncatedFileError(
            f"Footer byte buffer length ({len(raw_footer)}) does not match trailer "
            f"declared footer_len ({expected_footer_len})."
        )

    synthetic_ram_envelope = PARQUET_MAGIC_BYTES + raw_footer + raw_trailer
    buf_reader = pa.BufferReader(synthetic_ram_envelope)
    try:
        file_meta = pq.read_metadata(buf_reader)
    except (pa.ArrowInvalid, pa.ArrowException, OSError, RuntimeError, ValueError) as exc:
        raise CorruptedParquetFooterError(
            f"Failed to decode Parquet Thrift FileMetaData from in-memory footer: {exc}"
        ) from exc

    schema = file_meta.schema
    num_cols = int(file_meta.num_columns)
    num_row_groups = int(file_meta.num_row_groups)
    declared_num_rows = int(file_meta.num_rows)

    any_stats_detected = False
    columns_out: list[ColumnSchemaSummary] = []

    for col_idx in range(num_cols):
        col_schema = schema.column(col_idx)
        codecs: list[str] = []
        encodings_seen: list[str] = []
        col_had_stats = False

        for rg_idx in range(num_row_groups):
            col_chunk = file_meta.row_group(rg_idx).column(col_idx)
            codec_str = str(col_chunk.compression)
            if codec_str not in codecs:
                codecs.append(codec_str)
            for enc in col_chunk.encodings:
                enc_str = str(enc)
                if enc_str not in encodings_seen:
                    encodings_seen.append(enc_str)
            if bool(col_chunk.is_stats_set) or col_chunk.statistics is not None:
                col_had_stats = True
                any_stats_detected = True

        logical_type_str = (
            str(col_schema.logical_type)
            if col_schema.logical_type is not None
            else "NONE"
        )
        converted_type_str = (
            str(col_schema.converted_type)
            if col_schema.converted_type is not None
            else "NONE"
        )

        columns_out.append(
            ColumnSchemaSummary(
                column_index=col_idx,
                name=str(col_schema.name),
                path_in_schema=str(col_schema.path),
                physical_type=str(col_schema.physical_type),
                logical_type=logical_type_str,
                converted_type=converted_type_str,
                max_definition_level=int(col_schema.max_definition_level),
                max_repetition_level=int(col_schema.max_repetition_level),
                compression_codecs=tuple(codecs),
                encodings=tuple(encodings_seen),
                had_embedded_statistics=col_had_stats,
                statistics_suppressed=True,
            )
        )

    kv_meta = file_meta.metadata
    kv_detected = bool(kv_meta is not None and len(kv_meta) > 0)

    return SanitizedParquetFooterMetadata(
        format_version=str(file_meta.format_version),
        created_by=str(file_meta.created_by) if file_meta.created_by else None,
        num_columns=num_cols,
        num_row_groups=num_row_groups,
        declared_num_rows=declared_num_rows,
        footer_length_bytes=expected_footer_len,
        trailer_length_bytes=PARQUET_TRAILER_SIZE_BYTES,
        header_verification_status=HEADER_STATUS_NOT_VERIFIED,
        embedded_statistics_detected=any_stats_detected,
        embedded_statistics_suppressed=True,
        key_value_metadata_detected=kv_detected,
        key_value_metadata_suppressed=True,
        row_data_pages_read=0,
        columns=tuple(columns_out),
    )


__all__ = [
    "parse_in_memory_parquet_footer",
    "validate_parquet_trailer_and_extent",
]
