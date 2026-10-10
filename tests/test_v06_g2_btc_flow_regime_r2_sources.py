"""Synthetic monthly source and reservation-gate witnesses; no market files."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.strategy_research.g2_btc_flow_regime_r2 import sources


@pytest.fixture(autouse=True)
def one_day_calendar(monkeypatch):
    monkeypatch.setattr(sources.calendar, 'monthrange', lambda year, month: (0, 1))


def synthetic_rows(year=2021, month=1):
    start = int(datetime(year, month, 1, tzinfo=UTC).timestamp() * 1000)
    return [[str(start + i * 60_000), '100', '101', '99', '100', '2',
             str(start + i * 60_000 + 59_999), '200', '3', '1', '100', '0']
            for i in range(1440)]


def zip_rows(rows=None, *, year=2021, month=1, name=None, header=None):
    rows = synthetic_rows(year, month) if rows is None else rows
    name = name or f'BTCUSDT-1m-{year}-{month:02}.csv'
    text = '\n'.join([','.join(x) for x in ([header] if header else []) + rows]) + '\n'
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as archive:
        archive.writestr(name, text)
    return out.getvalue()


def test_dense_month_no_header_preserves_taker_base_column():
    arr, meta = sources.parse_month(zip_rows(), 2021, 1)
    assert arr.shape == (1440, 7)
    assert (arr[:, 6] == 1).all()
    assert meta['price_rows'] == 1440 and meta['header'] is None
    assert meta['duplicates'] == meta['gaps'] == 0


def test_documented_header_aliases_are_accepted_without_reorder():
    header = [aliases[-1] for aliases in sources.HEADER_ALIASES]
    _, meta = sources.parse_month(zip_rows(header=header), 2021, 1)
    assert meta['header'] == header and meta['physical_lines'] == 1441


def test_reordered_header_fails_closed():
    header = list(sources.FIELDS)
    header[5], header[9] = header[9], header[5]
    with pytest.raises(ValueError, match='header'):
        sources.parse_month(zip_rows(header=header), 2021, 1)


def test_taker_base_larger_than_total_volume_fails():
    rows = synthetic_rows(); rows[17][9] = '2.00000002'
    with pytest.raises(ValueError, match='taker volume'):
        sources.parse_month(zip_rows(rows), 2021, 1)


def test_tiny_taker_excess_is_rejected_without_clamping():
    rows = synthetic_rows(); rows[17][9] = '2.000000005'
    with pytest.raises(ValueError, match='taker volume'):
        sources.parse_month(zip_rows(rows), 2021, 1)


def test_zero_volume_taker_contradiction_fails():
    rows = synthetic_rows(); rows[17][5] = '0'; rows[17][9] = '0.000000001'
    with pytest.raises(ValueError, match='zero-volume'):
        sources.parse_month(zip_rows(rows), 2021, 1)


def test_duplicate_timestamp_fails_before_row_count():
    rows = synthetic_rows(); rows[17][0] = rows[16][0]; rows[17][6] = rows[16][6]
    with pytest.raises(ValueError, match='gapped, duplicate'):
        sources.parse_month(zip_rows(rows), 2021, 1)


def test_missing_minute_fails_exact_calendar():
    rows = synthetic_rows(); rows.pop(17)
    with pytest.raises(ValueError, match='gapped, duplicate'):
        sources.parse_month(zip_rows(rows), 2021, 1)


def test_close_timestamp_must_be_last_millisecond():
    rows = synthetic_rows(); rows[17][6] = str(int(rows[17][6]) + 1)
    with pytest.raises(ValueError, match='close clock'):
        sources.parse_month(zip_rows(rows), 2021, 1)


def test_nonfinite_and_bad_count_fail():
    rows = synthetic_rows(); rows[0][3] = 'nan'
    with pytest.raises(ValueError, match='nonfinite'):
        sources.parse_month(zip_rows(rows), 2021, 1)
    rows = synthetic_rows(); rows[0][8] = '1.5'
    with pytest.raises(ValueError, match='quote/count/taker'):
        sources.parse_month(zip_rows(rows), 2021, 1)


def test_zip_member_exact_and_year_grant():
    with pytest.raises(ValueError, match='member'):
        sources.parse_month(zip_rows(name='../BTCUSDT-1m-2021-01.csv'), 2021, 1)
    with pytest.raises(ValueError, match='outside frozen'):
        sources.parse_month(b'not even a ZIP', 2026, 1)


def test_checksum_exact_zip_identity():
    raw = zip_rows(); name = 'BTCUSDT-1m-2021-01.zip'
    checksum = hashlib.sha256(raw).hexdigest()
    assert sources.validate_zip_checksum(raw, f'{checksum}  {name}', name) == checksum
    with pytest.raises(ValueError, match='checksum'):
        sources.validate_zip_checksum(raw, f'{checksum}  another.zip', name)


def test_validation_denied_before_any_scratch_or_reserved_fetch(monkeypatch):
    monkeypatch.setattr(sources, 'verify_freeze', lambda sha: ({}, {}))
    monkeypatch.setattr(sources, 'verify_promotion',
                        lambda *args: (_ for _ in ()).throw(ValueError('promotion not pushed')))
    monkeypatch.setattr(sources.Path, 'mkdir',
                        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('scratch touched')))
    monkeypatch.setattr(sources, 'fetch',
                        lambda *args: (_ for _ in ()).throw(AssertionError('network touched')))
    with pytest.raises(ValueError, match='promotion not pushed'):
        sources.download('VALIDATION', sources.SCRATCH, '0' * 40, '1' * 40)


def test_validation_requires_promotion_sha_before_source_inspection(monkeypatch):
    monkeypatch.setattr(sources, 'verify_freeze', lambda sha: ({}, {}))
    with pytest.raises(ValueError, match='pushed promotion SHA'):
        sources.download('VALIDATION', sources.SCRATCH, '0' * 40)


def test_promotion_results_digest_checked_before_remote_and_reserved_access(monkeypatch, tmp_path):
    monkeypatch.setattr(sources, 'EVIDENCE', tmp_path)
    freeze = '0' * 40; promotion = '1' * 40
    record = {'stage': 'DEVELOPMENT', 'freeze_sha': freeze,
              'promoted_ids': ['CANDIDATE_A'], 'results_sha256': 'f' * 64}
    promotion_body = (json.dumps(record) + '\n').encode()
    (tmp_path / sources.PROMOTION_FILE).write_bytes(promotion_body)
    (tmp_path / sources.DEVELOPMENT_RESULTS_FILE).write_bytes(b'actual results')
    monkeypatch.setattr(sources, 'git_bytes',
                        lambda sha, path: (promotion_body if path.name == sources.PROMOTION_FILE
                                           else b'actual results'))
    monkeypatch.setattr(sources, 'verify_remote_head',
                        lambda sha: (_ for _ in ()).throw(AssertionError('remote checked too soon')))
    with pytest.raises(ValueError, match='results mismatch'):
        sources.verify_promotion(promotion, freeze, {'candidates': [{'id': 'CANDIDATE_A'}]})


def test_unapproved_stage_or_scratch_rejected():
    with pytest.raises(ValueError, match='stage'):
        sources.download('RESERVED', sources.SCRATCH, '0' * 40)
    with pytest.raises(ValueError, match='scratch'):
        sources.download('DEVELOPMENT', Path('/tmp/other'), '0' * 40)
