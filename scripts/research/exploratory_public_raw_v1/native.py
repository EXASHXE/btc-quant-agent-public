"""Bounded Binance native CSV/ZIP parser, no extraction or network code."""

import csv
import io
import math
import zipfile
from datetime import UTC, datetime
from itertools import chain

from . import GateError, require
from .contract import window
from .safeio import path, read_exact

MINUTE = 60000
HOUR = 60 * MINUTE
EXPANDED_CAP = 128 * 1024 * 1024
ROW_CAP = 200000


def number(v, positive=False):
    try:
        x = float(v)
    except (TypeError, ValueError) as exc:
        raise GateError('INVALID_NATIVE_NUMBER') from exc
    require(math.isfinite(x) and (not positive or x > 0), 'INVALID_NATIVE_NUMBER')
    return x


def millis(text):
    require(isinstance(text, str) and text.isdecimal(), 'NATIVE_INTEGER_MS_REQUIRED')
    return int(text)


def oi_time(text):
    try:
        dt = datetime.strptime(text, '%Y-%m-%d %H:%M:%S').replace(tzinfo=UTC)
    except (TypeError, ValueError) as exc:
        raise GateError('NATIVE_OI_UTC_CLOCK') from exc
    return int(dt.timestamp()) * 1000


def parse(f, payload):
    if f['format'] == 'zip':
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                infos = archive.infolist()
                require(len(infos) == 1, 'ZIP_MEMBER_COUNT')
                member = infos[0]
                require(not member.is_dir() and '/' not in member.filename
                        and '\\' not in member.filename and '..' not in member.filename
                        and member.filename.endswith('.csv') and member.flag_bits & 1 == 0,
                        'UNSAFE_ZIP_MEMBER')
                require(0 < member.file_size <= EXPANDED_CAP, 'ZIP_EXPANSION_LIMIT')
                with archive.open(member) as stream:
                    payload = stream.read(EXPANDED_CAP + 1)
                require(len(payload) == member.file_size, 'ZIP_EXPANSION_LIMIT')
        except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
            raise GateError('INVALID_ZIP') from exc
    require(len(payload) <= EXPANDED_CAP, 'CSV_SIZE_LIMIT')
    try:
        rows = csv.reader(io.StringIO(payload.decode('utf-8-sig')), strict=True)
        first = next(rows)
        header = first == f['native_schema']
        if not header:
            # Headerless native candles are valid; other families require native headers.
            require(f['family'] in ('price_1m', 'mark_1m') and first[0].isdecimal(),
                    'NATIVE_SCHEMA_MISMATCH')
        rows = rows if header else chain([first], rows)
        lo, hi = window(f['coverage'])
        result, previous = [], None
        for count, row in enumerate(rows, 1):
            require(count <= ROW_CAP and len(row) == len(f['native_schema']), 'NATIVE_SCHEMA')
            family = f['family']
            if family in ('price_1m', 'mark_1m'):
                t = millis(row[0])
                require(t % MINUTE == 0 and millis(row[6]) == t+MINUTE-1, 'NATIVE_BAR_CLOCK')
                values = [number(v, positive=True) for v in row[1:5]]
                require(values[2] <= min(values[0], values[3])
                        and values[1] >= max(values[0], values[3]), 'NATIVE_OHLC')
                event = {'t': t, 'open': values[0], 'close': values[3],
                         'available': t+MINUTE+f['availability_delay_ms']}
            elif family == 'oi_5m':
                t = oi_time(row[0])
                require(t % (5*MINUTE) == 0 and row[1] == 'BTCUSDT', 'NATIVE_OI_IDENTITY_CLOCK')
                event = {'t': t, 'oi': number(row[2], True) if row[2] else None,
                         'available': t+f['availability_delay_ms']}
            else:
                t = millis(row[0])
                require(number(row[1], True) <= 24, 'NATIVE_FUNDING_INTERVAL')
                event = {'t': t, 'rate': number(row[2]), 'interval_hours': number(row[1], True)}
            require(lo <= t < hi, 'PAYLOAD_OUTSIDE_FILE_COVERAGE')
            require(previous is None or t > previous, 'DUPLICATE_OR_UNSORTED_NATIVE_TIME')
            previous = t
            result.append(event)
        require(result, 'EMPTY_SOURCE')
        return result
    except (UnicodeError, csv.Error, StopIteration, IndexError) as exc:
        raise GateError('INVALID_NATIVE_CSV') from exc


def read_sources(manifest):
    tables = {k: {} for k in ('price_1m', 'oi_5m', 'funding', 'mark_1m')}
    qa, count = [], 0
    for f in manifest['files']:
        payload = read_exact(path(f['path']), f['sha256'], f['stat'])
        rows = parse(f, payload)
        count += len(rows)
        require(count <= 400000, 'TOTAL_NATIVE_ROW_LIMIT')
        table = tables[f['family']]
        for row in rows:
            require(row['t'] not in table, 'DUPLICATE_NATIVE_TIME')
            table[row['t']] = row
        qa.append({'path': f['path'], 'sha256': f['sha256'], 'rows': len(rows),
                   'first_event_ms': rows[0]['t'], 'last_event_ms': rows[-1]['t'],
                   'pit': 'PIT_UNKNOWN', 'receiver_first_known': None})
    return tables, qa


def feature_masks(registration, tables):
    """Freeze every hourly mask using features only, before consulting entry/exit prices."""
    bars, oi = tables['price_1m'], tables['oi_5m']
    left, right = window(registration['origins'])
    masks = []
    for cutoff in range(left, right, HOUR):
        origin = cutoff+MINUTE
        p = [bars.get(cutoff-MINUTE), bars.get(cutoff-4*HOUR-MINUTE)]
        x_valid = all(v is not None and v['available'] <= origin for v in p)
        ret = math.log(p[0]['close']/p[1]['close']) if x_valid else None
        zrows = [oi.get(cutoff-h*HOUR) for h in (0, 4, 24)]
        z_valid = registration['use_oi'] and all(
            v is not None and v['oi'] is not None and v['available'] <= origin for v in zrows)
        z = bool(z_valid and math.log(zrows[0]['oi']/zrows[2]['oi']) >= 0.015
                 and math.log(zrows[0]['oi']/zrows[1]['oi']) >= -0.005)
        masks.append({'cutoff': cutoff, 'origin': origin, 'x_valid': x_valid,
                      'common_valid': bool(x_valid and z_valid),
                      'x': bool(x_valid and ret <= -0.01), 'z': z,
                      'return_4h': ret,
                      'regime': 'LARGE_DROP' if ret is not None and ret <= -0.03 else 'ORDINARY'})
    return masks
