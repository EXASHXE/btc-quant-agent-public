"""Synthetic source admission tests; no network and no historical source files."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pytest

from scripts.strategy_research.g2_btc_two_lead_funding_mark_r3 import sources as s


def archive(raw_csv: bytes, year: int = 2021, month: int = 1, kind: str = "funding") -> tuple[bytes, bytes]:
    plan = s.source_plan(year, month, kind)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as writer:
        writer.writestr(plan["csv_name"], raw_csv)
    raw_zip = output.getvalue()
    check = f"{hashlib.sha256(raw_zip).hexdigest()}  {plan['zip_name']}\n".encode()
    return raw_zip, check


def funding_csv(rows: list[tuple[int, int, str]]) -> bytes:
    return ("calc_time,funding_interval_hours,last_funding_rate\n" +
            "".join(f"{stamp},{hours},{rate}\n" for stamp, hours, rate in rows)).encode()


@pytest.fixture(scope="module")
def january_klines() -> bytes:
    start, end = s.month_bounds(2021, 1)
    out = io.StringIO()
    for stamp in range(start, end, 60_000):
        out.write(f"{stamp},100,102,99,101,1,{stamp+59999},100,1,0.5,50,0\n")
    return out.getvalue().encode()


def test_month_guard_precedes_url_and_path_even_for_other_types() -> None:
    for y, m in ((2020, 12), (2024, 1), (2026, 1), (2023, 13), (2021, 0)):
        with pytest.raises(ValueError, match="source scope"):
            s.source_plan(y, m, "mark")
        with pytest.raises(ValueError, match="source scope"):
            s.load_month(y, m, "mark", allow_download=True)


def test_distinct_exact_source_identity_and_no_mark_api_route() -> None:
    assert "/monthly/klines/BTCUSDT/1m/" in s.source_plan(2021, 1, "last")["zip_url"]
    assert "/monthly/markPriceKlines/BTCUSDT/1m/" in s.source_plan(2021, 1, "mark")["zip_url"]
    assert "/monthly/fundingRate/BTCUSDT/" in s.source_plan(2021, 1, "funding")["zip_url"]


def test_mark_complete_minute_and_ohlc(january_klines: bytes) -> None:
    array, receipt = s.validate_kline_archive_bytes(*archive(january_klines, kind="mark"), 2021, 1, kind="mark")
    assert array.shape == (44_640, 5)
    assert receipt["source_identity"] == "BINANCE_USDM_MARK_PRICE"
    assert receipt["last_close_ms"] == s.month_bounds(2021, 1)[1] - 1


def test_last_complete_minute_and_flow(january_klines: bytes) -> None:
    array, receipt = s.validate_kline_archive_bytes(*archive(january_klines, kind="last"), 2021, 1, kind="last")
    assert array.shape == (44_640, 7)
    assert array[0, 6] == 0.5
    assert receipt["source_identity"] == "BINANCE_USDM_LAST_TRADE"


@pytest.mark.parametrize("change,match", [
    (lambda lines: lines.pop(), "incomplete"),
    (lambda lines: lines.__setitem__(1, lines[0]), "duplicate/gap"),
    (lambda lines: lines.__setitem__(0, lines[0].replace(",100,102,99,101,", ",100,98,99,101,")), "invalid mark OHLC"),
    (lambda lines: lines.__setitem__(0, lines[0].replace("1609459259999", "1609459259998")), "duplicate/gap"),
])
def test_mark_hostile_clock_and_price(january_klines: bytes, change, match: str) -> None:
    lines = january_klines.decode().splitlines()
    change(lines)
    with pytest.raises(ValueError, match=match):
        s.validate_kline_archive_bytes(*archive(("\n".join(lines) + "\n").encode(), kind="mark"), 2021, 1, kind="mark")


def test_checksum_and_member_identity_fail(january_klines: bytes) -> None:
    raw_zip, check = archive(january_klines, kind="mark")
    with pytest.raises(ValueError, match="provider SHA-256"):
        s.validate_kline_archive_bytes(raw_zip, check.replace(b"a", b"b"), 2021, 1, kind="mark")
    with pytest.raises(ValueError, match="ZIP basename mismatch"):
        s.validate_kline_archive_bytes(*archive(b"x", kind="funding"), 2021, 1, kind="mark")


def test_funding_archive_signed_fraction_and_observed_interval() -> None:
    start, _ = s.month_bounds(2021, 1)
    rows = [(start + 8 * 3_600_000, 8, "0.0001"), (start + 16 * 3_600_000, 8, "-0.0002")]
    events, receipt = s.validate_funding_archive_bytes(*archive(funding_csv(rows)), 2021, 1)
    assert [event["rate"] for event in events] == ["0.0001", "-0.0002"]
    assert [event["interval_hours"] for event in events] == ["8", "8"]
    assert receipt["publication_at_historical"].startswith("UNKNOWN")


@pytest.mark.parametrize("rows,match", [
    ([(1609455600000, 8, "0.0001")], "outside admitted month"),
    ([(1609455600000, 8, "1.5")], "fractional unit"),
])
def test_funding_outside_month(rows, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        s.validate_funding_archive_bytes(*archive(funding_csv(rows)), 2021, 1)


def test_funding_duplicate_and_rate_unit_rejected() -> None:
    start, _ = s.month_bounds(2021, 1)
    stamp = start + 8 * 3_600_000
    for rows, match in (([(stamp, 8, "0.001"), (stamp, 8, "0.002")], "duplicate"),
                        ([(stamp, 8, "1.5")], "fractional unit"),
                        ([(stamp, 0, "0.001")], "invalid observed")):
        with pytest.raises(ValueError, match=match):
            s.validate_funding_archive_bytes(*archive(funding_csv(rows)), 2021, 1)


def test_funding_cadence_gap_is_not_silent_zero() -> None:
    start, _ = s.month_bounds(2021, 1)
    events = [s._funding_event(start + 8 * 3_600_000, "0.001", "8", 1),
              s._funding_event(start + 24 * 3_600_000, "0.001", "8", 2)]
    with pytest.raises(ValueError, match="contradicts"):
        s.verify_funding_continuity(events, 2021, 1)


def test_funding_boundary_coverage_is_required() -> None:
    start, _ = s.month_bounds(2021, 1)
    events = [s._funding_event(start + 16 * 3_600_000, "0.001", "8", 1)]
    with pytest.raises(ValueError, match="early-month"):
        s.verify_funding_continuity(events, 2021, 1)


def test_api_page_strict_schema_signed_and_final_page() -> None:
    start, end = s.month_bounds(2021, 1)
    raw = json.dumps([{"symbol": "BTCUSDT", "fundingTime": start + 8 * 3_600_000,
                       "fundingRate": "-0.0003", "markPrice": "30000"}]).encode()
    events, receipt = s.parse_funding_api_pages([(start, end - 1, raw)], 2021, 1)
    assert events[0]["rate"] == "-0.0003"
    assert events[0]["interval_hours"] is None
    assert receipt["pages"][0]["raw_sha256"] == hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError, match="interval"):
        s.verify_funding_continuity(events, 2021, 1)


def test_api_rejects_empty_wrong_symbol_and_cursor() -> None:
    start, end = s.month_bounds(2021, 1)
    with pytest.raises(ValueError, match="empty"):
        s.parse_funding_api_pages([(start, end - 1, b"[]")], 2021, 1)
    wrong = b'[{"symbol":"ETHUSDT","fundingTime":1609488000000,"fundingRate":"0.001","markPrice":"100"}]'
    with pytest.raises(ValueError, match="foreign"):
        s.parse_funding_api_pages([(start, end - 1, wrong)], 2021, 1)
    with pytest.raises(ValueError, match="cursor"):
        s.parse_funding_api_pages([(start + 1, end - 1, wrong)], 2021, 1)
