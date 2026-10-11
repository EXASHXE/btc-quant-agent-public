"""Invented UTC minutes only; never read or fetch a historical market body."""

from __future__ import annotations

import calendar
import hashlib
import io
import zipfile
from functools import lru_cache

import pytest

from scripts.strategy_research.g2_gemini_goal_trend_flow_r1 import reanalysis_r2_sources as source

YEAR, MONTH = 2021, 2
ZIP_NAME = "BTCUSDT-1m-2021-02.zip"
CSV_NAME = "BTCUSDT-1m-2021-02.csv"
START = calendar.timegm((YEAR, MONTH, 1, 0, 0, 0)) * 1000
ROW = "{open_ms},100,101,99,100,1,{close_ms},100,1,0.5,50,0\n"


def package(csv_body: bytes, member: str = CSV_NAME) -> tuple[bytes, bytes]:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, csv_body)
    raw = buf.getvalue()
    return raw, f"{hashlib.sha256(raw).hexdigest()}  {ZIP_NAME}\n".encode()


@lru_cache(maxsize=1)
def good_body() -> bytes:
    lines = [",".join(source.FIELDS) + "\n"]
    for i in range(28 * 1440):
        current = START + i * 60_000
        lines.append(ROW.format(open_ms=current, close_ms=current + 59_999))
    return "".join(lines).encode()


@lru_cache(maxsize=1)
def good_package() -> tuple[bytes, bytes]:
    return package(good_body())


def changed_line(index: int, field: int, value: str) -> bytes:
    rows = good_body().decode().splitlines()
    fields = rows[index + 1].split(",")
    fields[field] = value
    rows[index + 1] = ",".join(fields)
    return ("\n".join(rows) + "\n").encode()


def test_complete_february_has_exact_ms_bounds_and_base_taker_volume() -> None:
    values, receipt = source.validate_archive_bytes(*good_package(), YEAR, MONTH)
    assert values.shape == (28 * 1440, 7)
    assert values[0, 0] == START
    assert values[-1, 0] == START + (28 * 1440 - 1) * 60_000
    assert values[0, 6] == 0.5
    assert receipt["last_close_ms"] == START + 28 * 1440 * 60_000 - 1
    assert receipt["zip_sha256"] == hashlib.sha256(good_package()[0]).hexdigest()
    assert receipt["status"] == "VERIFIED_COMPLETE_PUBLIC_TRADE_PRICE_MONTH"


def test_protected_year_fails_before_any_scratch_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(source, "DATA_DIR", object())
    with pytest.raises(ValueError, match="outside authorized"):
        source.load_validated_month(2024, 1, allow_download=True)


@pytest.mark.parametrize("month", [0, 13])
def test_invalid_month_fails_before_zip_parse(month: int) -> None:
    with pytest.raises(ValueError, match="outside authorized"):
        source.validate_archive_bytes(*good_package(), YEAR, month)


def test_provider_checksum_mismatch_fails() -> None:
    raw, checksum = good_package()
    with pytest.raises(ValueError, match="SHA-256"):
        source.validate_archive_bytes(raw, checksum.replace(b"a", b"b", 1), YEAR, MONTH)


def test_provider_checksum_filename_mismatch_fails() -> None:
    raw, check = good_package()
    with pytest.raises(ValueError, match="filename"):
        source.validate_archive_bytes(raw, check.replace(ZIP_NAME.encode(), b"wrong.zip"), YEAR, MONTH)


def test_unexpected_zip_member_fails() -> None:
    raw, check = package(good_body(), "BTCUSDT-1m-2021-03.csv")
    with pytest.raises(ValueError, match="exactly"):
        source.validate_archive_bytes(raw, check, YEAR, MONTH)


def test_reordered_header_fails() -> None:
    header, sep, rest = good_body().partition(b"\n")
    columns = header.decode().split(",")
    columns[5], columns[9] = columns[9], columns[5]
    with pytest.raises(ValueError, match="header"):
        source.validate_archive_bytes(*package(",".join(columns).encode() + sep + rest), YEAR, MONTH)


def test_one_missing_minute_fails() -> None:
    lines = good_body().splitlines(keepends=True)
    del lines[1441]
    with pytest.raises(ValueError, match="gap"):
        source.validate_archive_bytes(*package(b"".join(lines)), YEAR, MONTH)


def test_duplicate_minute_fails() -> None:
    lines = good_body().splitlines(keepends=True)
    lines[1441] = lines[1440]
    with pytest.raises(ValueError, match="duplicate"):
        source.validate_archive_bytes(*package(b"".join(lines)), YEAR, MONTH)


def test_close_clock_one_ms_late_fails() -> None:
    body = changed_line(10, 6, str(START + 10 * 60_000 + 60_000))
    with pytest.raises(ValueError, match="close clock"):
        source.validate_archive_bytes(*package(body), YEAR, MONTH)


def test_decimal_taker_buy_must_not_exceed_total_by_tiny_amount() -> None:
    body = changed_line(10, 9, "1.000000005")
    with pytest.raises(ValueError, match="signed-flow base"):
        source.validate_archive_bytes(*package(body), YEAR, MONTH)


def test_crossed_high_low_fails() -> None:
    body = changed_line(10, 2, "98")
    with pytest.raises(ValueError, match="OHLC"):
        source.validate_archive_bytes(*package(body), YEAR, MONTH)


def test_nonfinite_numeric_field_fails() -> None:
    body = changed_line(10, 7, "NaN")
    with pytest.raises(ValueError, match="nonfinite"):
        source.validate_archive_bytes(*package(body), YEAR, MONTH)


def test_absent_month_never_trusts_old_npy(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(source, "DATA_DIR", tmp_path)
    monkeypatch.setattr(source, "SCRATCH_ROOT", tmp_path)
    (tmp_path / "validated-2021-02.npy").write_bytes(b"stale and unverified")
    with pytest.raises(FileNotFoundError, match="missing authorized source file"):
        source.load_validated_month(YEAR, MONTH)
