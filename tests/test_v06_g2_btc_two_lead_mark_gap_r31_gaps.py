"""Synthetic-only proofs of the frozen R3.1 eight-day source route."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile

import numpy as np
import pytest

from scripts.strategy_research.g2_btc_two_lead_mark_gap_r31 import gaps

DAY = "2021-07-01"
START = gaps.day_plan(DAY)["start_ms"]


def bar(minute: int, *, value: str = "100", close_offset: int = 59999) -> list[str]:
    stamp = START + minute * 60000
    return [str(stamp), value, "101", "99", value, "0", str(stamp + close_offset),
            "0", "0", "0", "0", "0"]


def archive(lines: list[list[str]], *, name: str | None = None) -> tuple[bytes, bytes]:
    plan = gaps.day_plan(DAY)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as opened:
        opened.writestr(name or plan["csv_name"], "\n".join(",".join(line) for line in lines) + "\n")
    raw = buffer.getvalue()
    check = f"{hashlib.sha256(raw).hexdigest()}  {plan['zip_name']}\n".encode()
    return raw, check


def test_scope_guard_all_eight_and_rejects_other_dates() -> None:
    assert len(gaps.ALLOWED_DAYS) == 8
    assert len({gaps.day_plan(day)["start_ms"] for day in gaps.ALLOWED_DAYS}) == 8
    for bad in ("2021-07-02", "2024-01-01", "2026-07-01", "", "2021-07-01/../x"):
        with pytest.raises(ValueError, match="eight frozen"):
            gaps.day_plan(bad)


def test_daily_correct_authentic_partial_and_missing_ranges() -> None:
    raw, check = archive([bar(0), bar(2)])
    rows, receipt = gaps.parse_daily(raw, check, DAY)
    assert rows.shape == (2, 5)
    assert receipt["rows"] == 2
    assert receipt["missing_minutes"] == 1438
    assert gaps.missing_ranges(rows, DAY)[0] == {
        "start_ms": START + 60000, "end_exclusive_ms": START + 120000, "minutes": 1,
    }


def test_daily_checksum_fails() -> None:
    raw, check = archive([bar(0)])
    with pytest.raises(ValueError, match="CHECKSUM"):
        gaps.parse_daily(raw + b"x", check, DAY)


def test_daily_member_fails() -> None:
    raw, check = archive([bar(0)], name="wrong.csv")
    with pytest.raises(ValueError, match="member"):
        gaps.parse_daily(raw, check, DAY)


def test_daily_duplicate_and_reordering_fail() -> None:
    for lines in ([bar(0), bar(0)], [bar(2), bar(1)]):
        raw, check = archive(lines)
        with pytest.raises(ValueError, match="duplicate/out-of-order"):
            gaps.parse_daily(raw, check, DAY)


def test_daily_wrong_close_fails() -> None:
    raw, check = archive([bar(0, close_offset=60000)])
    with pytest.raises(ValueError, match="close-time"):
        gaps.parse_daily(raw, check, DAY)


def test_daily_zero_ohlc_fails() -> None:
    raw, check = archive([bar(0, value="0")])
    with pytest.raises(ValueError, match="OHLC"):
        gaps.parse_daily(raw, check, DAY)


def test_daily_unknown_header_fails() -> None:
    raw, check = archive([["open_time", "x", *["ignore"] * 10], bar(0)])
    with pytest.raises(ValueError, match="header"):
        gaps.parse_daily(raw, check, DAY)


def test_api_exact_requested_minute() -> None:
    rows, receipt = gaps.parse_api(json.dumps([bar(1)]).encode(), DAY, START + 60000, START + 120000)
    assert rows.shape == (1, 5)
    assert receipt["provenance"] == "PROVIDER_API_SECONDARY_NOT_ZIP_AUTHENTICATED"


def test_api_rejects_outside_request_and_day() -> None:
    with pytest.raises(ValueError, match="clock"):
        gaps.parse_api(json.dumps([bar(2)]).encode(), DAY, START + 60000, START + 120000)
    with pytest.raises(ValueError, match="outside frozen"):
        gaps.parse_api(b"[]", DAY, START - 60000, START)


def test_api_rejects_duplicate_and_reordered() -> None:
    for lines in ([bar(1), bar(1)], [bar(2), bar(1)]):
        with pytest.raises(ValueError, match="duplicate/out-of-order"):
            gaps.parse_api(json.dumps(lines).encode(), DAY, START, START + 180000)


def test_api_rejects_bad_json_and_error_object() -> None:
    with pytest.raises(ValueError, match="JSON"):
        gaps.parse_api(b"{", DAY, START, START + 60000)
    with pytest.raises(ValueError, match="shape"):
        gaps.parse_api(b'{"code": -1121}', DAY, START, START + 60000)


def test_api_rejects_infinite_and_outside_day() -> None:
    with pytest.raises(ValueError, match="OHLC"):
        gaps.parse_api(json.dumps([bar(0, value="Infinity")]).encode(), DAY, START, START + 60000)
    with pytest.raises(ValueError, match="outside frozen"):
        gaps.parse_api(b"[]", DAY, START, START + 1441 * 60000)


def test_overlap_agree_and_material_conflict() -> None:
    old = np.array([[float(START), 100, 101, 99, 100]])
    assert gaps.compare_overlap(old, old.copy())["overlap_rows"] == 1
    new = old.copy()
    new[0, 4] = 100.01
    with pytest.raises(ValueError, match="conflicts"):
        gaps.compare_overlap(old, new)


def test_missing_ranges_and_duplicate_guard() -> None:
    rows = np.array([[float(START), 100, 101, 99, 100]])
    assert sum(item["minutes"] for item in gaps.missing_ranges(rows, DAY)) == 1439
    with pytest.raises(ValueError, match="unique"):
        gaps.missing_ranges(np.concatenate([rows, rows]), DAY)


def test_compose_month_does_not_overwrite_existing() -> None:
    old = np.array([[float(START), 100, 101, 99, 100]])
    add = np.array([[float(START + 60000), 100, 101, 99, 100]])
    composed, receipt = gaps.compose_gap_month(old, [add], 2021, 7)
    assert len(composed) == 2 and receipt["added_rows"] == 1
    assert composed[0, 4] == old[0, 4]


def test_compose_rejects_unfrozen_month_minute() -> None:
    old = np.array([[float(START), 100, 101, 99, 100]])
    add = np.array([[float(START + 86400000), 100, 101, 99, 100]])
    with pytest.raises(ValueError, match="outside frozen"):
        gaps.compose_gap_month(old, [add], 2021, 7)


def test_compose_rejects_duplicate_replacement_minute() -> None:
    old = np.array([[float(START), 100, 101, 99, 100]])
    add = np.array([[float(START + 60000), 100, 101, 99, 100]])
    with pytest.raises(ValueError, match="duplicate replacement"):
        gaps.compose_gap_month(old, [add, add], 2021, 7)


def test_daily_precedes_api_for_exact_missing_minute(monkeypatch: pytest.MonkeyPatch) -> None:
    raw_zip, raw_check = archive([bar(i) for i in range(1440) if i != 1])
    visited = []

    def fake_load(url, path, *, allow_download, max_bytes, allowed_host):
        visited.append(url)
        if url.endswith(".zip"):
            return raw_zip, {"status": 200, "sha256": hashlib.sha256(raw_zip).hexdigest()}
        if url.endswith(".CHECKSUM"):
            return raw_check, {"status": 200, "sha256": hashlib.sha256(raw_check).hexdigest()}
        assert "startTime=" + str(START + 60000) in url
        assert "endTime=" + str(START + 119999) in url
        return json.dumps([bar(1)]).encode(), {"status": 200}

    monkeypatch.setattr(gaps, "_load", fake_load)
    rows, receipt = gaps.gather_day(DAY, allow_download=True)
    assert len(rows) == 1440
    assert receipt["unresolved_ranges"] == []
    assert receipt["provenance_counts"] == {
        "PROVIDER_API_SECONDARY_NOT_ZIP_AUTHENTICATED": 1,
        "PROVIDER_DAILY_ZIP_SHA256_AUTHENTICATED": 1439,
    }
    assert len(visited) == 3


def test_daily_404_routes_whole_frozen_day_to_api(monkeypatch: pytest.MonkeyPatch) -> None:
    visited = []

    def fake_load(url, path, *, allow_download, max_bytes, allowed_host):
        visited.append(url)
        if "data.binance.vision" in url:
            return None, {"status": 404}
        assert "startTime=" + str(START) in url
        assert "endTime=" + str(START + gaps.DAY_MS - 1) in url
        return b"[]", {"status": 200}

    monkeypatch.setattr(gaps, "_load", fake_load)
    rows, receipt = gaps.gather_day(DAY, allow_download=True)
    assert len(rows) == 0
    assert sum(r["minutes"] for r in receipt["unresolved_ranges"]) == 1440
    assert len(receipt["api_requests"]) == 1
    assert len(visited) == 3
