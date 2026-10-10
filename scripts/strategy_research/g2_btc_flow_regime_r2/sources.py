"""Frozen two-stage Binance Vision BTC USD-M minute source admission.

Only explicitly listed public monthly ZIPs are fetched. A validation request is
rejected before inspecting its scratch directory or contacting the source unless
the development promotion is already the verified remote branch tip.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import io
import json
import math
import subprocess
import zipfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import numpy as np

from scripts.strategy_research.g2_btc_empirical_fast_r1.sources import (
    BASE,
    FIELDS,
    validate_zip_checksum,
)

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / 'evidence/v0.6/b_line/g2_btc_flow_regime_r2'
SCRATCH = Path('/tmp/g2-btc-flow-regime-r2')
BRANCH = 'feature/v06-bline-g2-btc-flow-regime-discovery-r2'
FROZEN_FILES = ('FROZEN_R2_ROSTER.json', 'FROZEN_R2_SOURCE_SPLIT.json',
                'OUTCOME_BLIND_R2_FREEZE_RECEIPT.json')
PROMOTION_FILE = 'DEVELOPMENT_PROMOTION.json'
DEVELOPMENT_RESULTS_FILE = 'DEVELOPMENT_RESULTS.json'
VALID_MONTHS = frozenset((1, 2, 5, 6, 8, 9, 11, 12))
TRANSIENT_HTTP = frozenset((408, 429, 500, 502, 503, 504))
HEADER_ALIASES = (
    ('open_time',), ('open',), ('high',), ('low',), ('close',), ('volume',),
    ('close_time',), ('quote_volume', 'quote_asset_volume'),
    ('count', 'number_of_trades'),
    ('taker_buy_volume', 'taker_buy_base_asset_volume'),
    ('taker_buy_quote_volume', 'taker_buy_quote_asset_volume'), ('ignore',),
)


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def digest(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def exact_sha(value: str) -> str:
    if len(value) != 40 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('exact lowercase 40-hex SHA required')
    return value


def git_bytes(sha: str, path: Path) -> bytes:
    return subprocess.check_output(
        ['git', 'show', f'{exact_sha(sha)}:{path.relative_to(ROOT)}'], cwd=ROOT,
    )


def verify_remote_head(sha: str) -> None:
    refs = subprocess.check_output(
        ['git', 'ls-remote', '--heads', 'origin', BRANCH], cwd=ROOT, text=True,
    ).splitlines()
    if refs != [f'{exact_sha(sha)}\trefs/heads/{BRANCH}']:
        raise ValueError('remote branch does not point to required pushed SHA')


def verify_freeze(freeze_sha: str) -> tuple[dict, dict]:
    """Check immutable files and parent; no market path is opened here."""
    exact_sha(freeze_sha)
    raw = {name: git_bytes(freeze_sha, EVIDENCE / name) for name in FROZEN_FILES}
    if any(raw[name] != (EVIDENCE / name).read_bytes() for name in FROZEN_FILES):
        raise ValueError('freeze files differ from freeze commit')
    roster = json.loads(raw[FROZEN_FILES[0]])
    split = json.loads(raw[FROZEN_FILES[1]])
    receipt = json.loads(raw[FROZEN_FILES[2]])
    if (digest(raw[FROZEN_FILES[0]]) != receipt['roster_sha256']
            or digest(raw[FROZEN_FILES[1]]) != receipt['source_split_sha256']
            or roster['source_split_sha256'] != receipt['source_split_sha256']):
        raise ValueError('freeze file digest mismatch')
    parent = subprocess.check_output(['git', 'rev-parse', f'{freeze_sha}^'],
                                     cwd=ROOT, text=True).strip()
    if parent != receipt['exact_parent'] or roster['exact_start_sha'] != parent:
        raise ValueError('freeze parent mismatch')
    if len(split['source_plan']) != 40 or len(split['folds']) != 20:
        raise ValueError('frozen source split shape mismatch')
    if split['column_spec']['accepted_header_aliases'] != [list(a) for a in HEADER_ALIASES]:
        raise ValueError('frozen header aliases drift')
    for relative, frozen_digest in roster['R1_code_sha256'].items():
        if digest((ROOT / relative).read_bytes()) != frozen_digest:
            raise ValueError(f'frozen R1 dependency drift: {relative}')
    return roster, split


def verify_promotion(promotion_sha: str, freeze_sha: str, roster: dict) -> dict:
    """Return admitted IDs; any failure occurs before reserved scratch access."""
    exact_sha(promotion_sha)
    promotion_path = EVIDENCE / PROMOTION_FILE
    raw = git_bytes(promotion_sha, promotion_path)
    if raw != promotion_path.read_bytes():
        raise ValueError('promotion file differs from pushed commit')
    record = json.loads(raw)
    ids = record.get('promoted_ids')
    candidate_ids = {candidate['id'] for candidate in roster['candidates']}
    if (record.get('stage') != 'DEVELOPMENT' or record.get('freeze_sha') != freeze_sha
            or not isinstance(ids, list) or not 1 <= len(ids) <= 2
            or len(set(ids)) != len(ids) or not set(ids) <= candidate_ids
            or not isinstance(record.get('results_sha256'), str)
            or len(record['results_sha256']) != 64
            or any(c not in '0123456789abcdef' for c in record['results_sha256'])):
        raise ValueError('invalid frozen development promotion')
    results_path = EVIDENCE / DEVELOPMENT_RESULTS_FILE
    results = git_bytes(promotion_sha, results_path)
    if results != results_path.read_bytes() or digest(results) != record['results_sha256']:
        raise ValueError('development results mismatch promotion digest')
    parent = subprocess.check_output(['git', 'rev-parse', f'{promotion_sha}^'],
                                     cwd=ROOT, text=True).strip()
    if parent != freeze_sha:
        raise ValueError('promotion must directly follow freeze commit')
    verify_remote_head(promotion_sha)
    return record


def parse_month(raw: bytes, year: int, month: int) -> tuple[np.ndarray, dict]:
    """Parse one authorized full UTC month to [ms,O,H,L,C,V,B]."""
    if year not in range(2021, 2026) or month not in VALID_MONTHS:
        raise ValueError('month outside frozen R2 public grant')
    name = f'BTCUSDT-1m-{year}-{month:02}.csv'
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if archive.namelist() != [name]:
            raise ValueError('unexpected ZIP member set')
        info = archive.getinfo(name)
        if info.file_size > 30_000_000:
            raise ValueError('CSV uncompressed budget exceeded')
        body = archive.read(name)
    rows = csv.reader(io.StringIO(body.decode('utf-8-sig')))
    expected = calendar.monthrange(year, month)[1] * 1440
    start = int(datetime(year, month, 1, tzinfo=UTC).timestamp() * 1000)
    values: list[list[float]] = []
    header: list[str] | None = None
    zero_volume = 0
    for lineno, row in enumerate(rows, 1):
        if len(row) != 12:
            raise ValueError(f'CSV field count at line {lineno}')
        if lineno == 1 and not row[0].isdigit():
            header = row
            if not all(actual in aliases for actual, aliases in zip(header, HEADER_ALIASES, strict=True)):
                raise ValueError('unrecognized or reordered USD-M header')
            continue
        if len(values) >= expected:
            raise ValueError('month row count exceeds calendar')
        try:
            timestamp = int(row[0]); close_time = int(row[6])
            nums = [float(value) for value in row]
        except ValueError as exc:
            raise ValueError(f'invalid numeric source field at line {lineno}') from exc
        if not all(math.isfinite(value) for value in nums):
            raise ValueError(f'nonfinite source number at line {lineno}')
        o, h, l, c, volume = nums[1:6]
        quote, count, taker, taker_quote = nums[7:11]
        if not (0 < l <= min(o, c) <= max(o, c) <= h and volume >= 0):
            raise ValueError(f'invalid OHLC or volume at line {lineno}')
        if close_time != timestamp + 59_999:
            raise ValueError(f'invalid close clock at line {lineno}')
        if volume == 0 and taker != 0:
            raise ValueError(f'zero-volume taker contradiction at line {lineno}')
        if not (quote >= 0 and count >= 0 and count.is_integer()
                and taker_quote >= 0 and 0 <= taker <= volume
                and Decimal(row[9]) <= Decimal(row[5])):
            raise ValueError(f'invalid quote/count/taker volume at line {lineno}')
        if timestamp != start + len(values) * 60_000:
            raise ValueError(f'gapped, duplicate, or out-of-order minute at line {lineno}')
        zero_volume += volume == 0
        values.append([timestamp, o, h, l, c, volume, taker])
    if len(values) != expected:
        raise ValueError(f'month row count {len(values)}, expected {expected}')
    array = np.asarray(values, dtype=np.float64)
    return array, {
        'csv_member': name, 'csv_sha256': digest(body), 'csv_bytes': len(body),
        'physical_lines': len(values) + (header is not None), 'price_rows': len(values),
        'header': header, 'field_layout': FIELDS,
        'feature_array': ['open_time_ms', 'open', 'high', 'low', 'close',
                          'volume_BTC', 'taker_buy_volume_BTC'],
        'unit': 'UTC milliseconds; BTC base volume; USDT quote volume',
        'min_open_ms': start, 'max_open_ms': start + (expected - 1) * 60_000,
        'end_exclusive_ms': start + expected * 60_000,
        'duplicates': 0, 'gaps': 0, 'out_of_order': 0,
        'zero_volume_minutes': zero_volume,
        'taker_volume_was_clamped': False,
        'publisher_corrections': 'current archive snapshot; no historical known-at proof',
    }


def fetch(url: str, target: Path) -> dict:
    """At most three transient attempts, with every attempt's HTTP evidence."""
    if not url.startswith(BASE):
        raise ValueError('unexpected network source')
    attempts = []
    for index in range(1, 4):
        headers = Path(str(target) + f'.attempt{index}.headers')
        temporary = Path(str(target) + f'.attempt{index}')
        result = subprocess.run(
            ['curl', '--silent', '--show-error', '--location', '--max-redirs', '2',
             '--proto', '=https', '--proto-redir', '=https',
             '--connect-timeout', '20', '--max-time', '120',
             '--dump-header', str(headers), '--output', str(temporary),
             '--write-out', '%{http_code}\n%{url_effective}\n%{http_version}', url],
            capture_output=True, text=True, check=False,
        )
        lines = result.stdout.splitlines()
        status = int(lines[0]) if lines and lines[0].isdigit() else 0
        returned = lines[1] if len(lines) > 1 else ''
        if returned and returned != url:
            raise ValueError('redirect outside exact authorized archive URL')
        attempt = {
            'index': index, 'requested_url': url, 'returned_url': returned,
            'http_status': status, 'http_version': lines[2] if len(lines) > 2 else None,
            'curl_exit': result.returncode, 'utc': utcnow(),
            'headers_sha256': digest(headers.read_bytes()) if headers.exists() else None,
            'download_sha256': digest(temporary.read_bytes()) if temporary.exists() else None,
            'stderr': result.stderr[:500] if result.returncode else None,
        }
        attempts.append(attempt)
        if status == 200 and result.returncode == 0:
            temporary.replace(target)
            break
        temporary.unlink(missing_ok=True)
        if status not in TRANSIENT_HTTP and result.returncode == 0:
            break
    return {'attempts': attempts, 'http_status': attempts[-1]['http_status'],
            'curl_exit': attempts[-1]['curl_exit'],
            'requested_url': url, 'returned_url': attempts[-1]['returned_url']}


def download(stage: str, scratch: Path, freeze_sha: str,
             promotion_sha: str | None = None) -> dict:
    """Admit one stage; reserved access gate executes before scratch.stat/mkdir."""
    if stage not in {'DEVELOPMENT', 'VALIDATION'}:
        raise ValueError('unknown source stage')
    if scratch != SCRATCH:
        raise ValueError('only exact task-owned /tmp scratch supported')
    roster, split = verify_freeze(freeze_sha)
    if stage == 'VALIDATION':
        if promotion_sha is None:
            raise ValueError('pushed promotion SHA required before validation source access')
        verify_promotion(promotion_sha, freeze_sha, roster)
    else:
        if promotion_sha is not None:
            raise ValueError('development must not use promotion SHA')
        verify_remote_head(freeze_sha)
    plan = [entry for entry in split['source_plan'] if entry['stage'] == stage]
    expected_count = 24 if stage == 'DEVELOPMENT' else 16
    if len(plan) != expected_count:
        raise ValueError('source-stage plan shape mismatch')
    for entry in plan:
        year, month = entry['year'], entry['month']
        expected = f'{BASE}BTCUSDT-1m-{year}-{month:02}.zip'
        if (year not in range(2021, 2026) or month not in VALID_MONTHS
                or entry['url'] != expected or entry['checksum_url'] != expected + '.CHECKSUM'):
            raise ValueError('source-stage URL/month drift')
        if (stage == 'DEVELOPMENT') != (year <= 2023):
            raise ValueError('source-stage year drift')
    scratch.mkdir(mode=0o700, parents=True, exist_ok=True)
    manifest_path = EVIDENCE / f'SOURCE_MANIFEST_{stage}.json'
    manifest = {
        'schema': 'PUBLIC_BTC_R2_SOURCE_MANIFEST_V1', 'stage': stage,
        'freeze_sha': freeze_sha, 'promotion_sha': promotion_sha,
        'started_at_utc': utcnow(), 'first_price_csv_read_at_utc': None,
        'source_snapshot_grade': split['source_snapshot_grade'],
        'rights': roster['source_rights'], 'records': [],
        'owner_protected_or_account_reads': 0,
    }
    for entry in plan:
        year, month = entry['year'], entry['month']
        filename = f'BTCUSDT-1m-{year}-{month:02}.zip'
        archive = scratch / filename
        check = scratch / f'{filename}.CHECKSUM'
        record = {
            'year': year, 'month': month, 'fold': entry['fold'],
            'role': entry['role'], 'zip': fetch(entry['url'], archive),
            'checksum': fetch(entry['checksum_url'], check),
        }
        if (record['zip']['http_status'] != 200 or record['checksum']['http_status'] != 200
                or record['zip']['curl_exit'] or record['checksum']['curl_exit']):
            record['status'] = 'HTTP_SOURCE_MISSING'
        else:
            try:
                raw = archive.read_bytes()
                record['zip_sha256'] = validate_zip_checksum(raw, check.read_text(), filename)
                record['checksum_sha256'] = digest(check.read_bytes())
                if manifest['first_price_csv_read_at_utc'] is None:
                    manifest['first_price_csv_read_at_utc'] = utcnow()
                array, meta = parse_month(raw, year, month)
                record.update(meta)
                cache = scratch / f'validated-{year}-{month:02}.npy'
                np.save(cache, array, allow_pickle=False)
                record['validated_npy_sha256'] = digest(cache.read_bytes())
                record['status'] = 'VERIFIED_COMPLETE_PUBLIC_MONTH'
            except (ValueError, UnicodeError, OSError, zipfile.BadZipFile) as exc:
                record['status'] = 'SOURCE_INTEGRITY_FAIL'
                record['error'] = str(exc)
        manifest['records'].append(record)
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
        print(json.dumps({'stage': stage, 'year': year, 'month': month,
                          'status': record['status'], 'rows': record.get('price_rows')}), flush=True)
        if record['status'] == 'SOURCE_INTEGRITY_FAIL':
            break
    manifest['finished_at_utc'] = utcnow()
    admitted = {(r['year'], r['month']) for r in manifest['records']
                if r['status'] == 'VERIFIED_COMPLETE_PUBLIC_MONTH'}
    full = [fold['id'] for fold in split['folds'] if fold['stage'] == stage
            and (fold['year'], fold['warmup_month']) in admitted
            and (fold['year'], fold['month']) in admitted]
    years = sorted({int(fold[:4]) for fold in full})
    floor = (split['development_minimum_full_folds'] if stage == 'DEVELOPMENT'
             else split['validation_minimum_full_folds'])
    required_years = (split['development_required_years'] if stage == 'DEVELOPMENT'
                      else split['validation_required_years'])
    integrity_failed = any(r['status'] == 'SOURCE_INTEGRITY_FAIL' for r in manifest['records'])
    manifest.update({'complete_folds': full, 'complete_years': years,
                     'missing_months': [(r['year'], r['month']) for r in manifest['records']
                                        if r['status'] == 'HTTP_SOURCE_MISSING'],
                     'gate': ('PASS_PUBLIC_TRADE_PRICE_ONLY' if not integrity_failed
                              and len(manifest['records']) == expected_count
                              and len(full) >= floor and years == required_years
                              else 'BLOCKED_PUBLIC_DATA_COVERAGE_OR_INTEGRITY')})
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=('DEVELOPMENT', 'VALIDATION'), required=True)
    parser.add_argument('--scratch', type=Path, default=SCRATCH)
    parser.add_argument('--freeze', required=True)
    parser.add_argument('--promotion')
    args = parser.parse_args()
    outcome = download(args.stage, args.scratch, args.freeze, args.promotion)
    if outcome['gate'].startswith('BLOCKED'):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
