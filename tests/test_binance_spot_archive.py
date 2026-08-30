from __future__ import annotations

from btc_quant_agent.data.binance_spot_archive import (
    normalize_archive_timestamp,
    parse_spot_flow_rows,
)


def _row(open_time: int, close_time: int, volume: str = "10", taker: str = "6") -> list[str]:
    return [
        str(open_time),
        "1",
        "1",
        "1",
        "1",
        volume,
        str(close_time),
        "10",
        "2",
        taker,
        "6",
        "0",
    ]


def test_normalize_archive_timestamp_accepts_milliseconds() -> None:
    assert normalize_archive_timestamp(1_735_689_600_000) == (1_735_689_600_000, "milliseconds")


def test_normalize_archive_timestamp_converts_microseconds() -> None:
    assert normalize_archive_timestamp(1_735_689_600_000_000) == (
        1_735_689_600_000,
        "microseconds",
    )


def test_parse_spot_rows_normalizes_both_timestamps() -> None:
    rows, audit = parse_spot_flow_rows(
        [_row(1_735_689_600_000_000, 1_735_689_659_999_000)]
    )
    assert rows[0]["open_time_ms"] == 1_735_689_600_000
    assert rows[0]["close_time_ms"] == 1_735_689_659_999
    assert audit["timestamp_value_units"] == {"microseconds": 2}


def test_parse_spot_rows_audits_volume_and_order() -> None:
    rows, audit = parse_spot_flow_rows(
        [_row(120_000, 179_999, "10", "11"), _row(60_000, 119_999, "0", "0")]
    )
    assert len(rows) == 2
    assert audit["invalid_volume"] == 1
    assert audit["zero_volume"] == 1
    assert audit["out_of_order"] == 1
