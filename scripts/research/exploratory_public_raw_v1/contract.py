"""Immutable registration + independently persisted, externally pinned acceptance.

No acceptance writer, runtime token, CLI trust override, or real-source default exists.
The deployment authority must pin a genuine registry hash and authenticity reference
out of band, after independently checking publisher rights and exact source identities.
"""

import os
from datetime import UTC, datetime
from itertools import pairwise
from types import MappingProxyType

from . import require
from .safeio import (
    absent,
    canonical,
    digest,
    directory,
    file_info,
    hash_value,
    load,
    path,
    read_exact,
)

# Intentionally empty: this implementation is not an admission authority.
# Each deployed pin: {path, sha256, accepted_by, authenticity_reference}.
TRUSTED_REGISTRIES = MappingProxyType({})
SCHEMA = 'exploratory-public-raw.v1'
LABELS = {
    'classification': 'EXPLORATORY_ONLY',
    'holdout': 'UNKNOWN_OR_POSSIBLE_OVERLAP',
    'selection': 'SELECTION_CONTAMINATED_OR_UNKNOWN',
    'pit': 'PIT_UNKNOWN', 'fills': 'COST_UNVALIDATED_REAL_FILL',
    'p3': 'P3_ACCESS_SCOPE_HOLD', 'alpha': 'NO_ALPHA_ESTABLISHED',
    'g2': 'G2_ALPHA_NO_GO', 'g4': 'G4_TESTNET_NO_GO',
    'live': 'LIVE_NO_GO', 'funds': 'REAL_FUNDS_WRITE_NONE',
}
POLICY = {
    'x_log_return_4h_lte': -0.01, 'z_log_oi_24h_gte': 0.015,
    'z_log_oi_4h_gte': -0.005, 'direction': 'SHORT_ONLY',
    'origin_delay_ms': 60000, 'entry_delay_ms': 120000, 'exit_ms': 28800000,
    'concurrent_per_arm': 1, 'entry': 'EXACT_1M_OPEN_NO_DELAYED_FILL',
    'missingness': 'SKIP_NO_FORWARD_FILL', 'funding_boundary': 'ENTRY_LT_EVENT_LE_EXIT',
    'baseline': {'fee_roundtrip_bp': 8, 'slippage_roundtrip_bp': 8},
    'stress': {'fee_roundtrip_bp': 8, 'slippage_roundtrip_bp': 24},
    'cost_basis': 'FIXED_ENTRY_NOTIONAL_AGGREGATE_SENSITIVITY',
    'capital': 'UNIT_ENTRY_NOTIONAL_ADDITIVE_NO_COMPOUNDING',
    'regime': 'EX_ANTE_4H_DROP_LE_MINUS_3PCT_ELSE_ORDINARY',
}
BAR_SCHEMA = ['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time',
              'quote_volume', 'count', 'taker_buy_volume', 'taker_buy_quote_volume', 'ignore']
OI_SCHEMA = ['create_time', 'symbol', 'sum_open_interest', 'sum_open_interest_value',
             'count_toptrader_long_short_ratio', 'sum_toptrader_long_short_ratio',
             'count_long_short_ratio', 'sum_taker_long_short_vol_ratio']
SCHEMAS = {'price_1m': BAR_SCHEMA, 'oi_5m': OI_SCHEMA, 'mark_1m': BAR_SCHEMA,
           'funding': ['calc_time', 'funding_interval_hours', 'last_funding_rate']}
FIELDS = {'price_1m': ['open_time', 'open', 'close_time', 'close'],
          'oi_5m': ['create_time', 'symbol', 'sum_open_interest'],
          'mark_1m': ['open_time', 'open'], 'funding': SCHEMAS['funding']}
OUTPUTS = ['EXPERIMENT_REGISTRATION.json', 'ACCEPTED_SCOPE_RECORD.json', 'SOURCE_MANIFEST.json',
           'SOURCE_QA.json', 'BTC_TRADE_LEDGER.csv', 'BTC_ECONOMICS.json',
           'LOSS_AND_MISSINGNESS.json', 'RUN_RECEIPT.json', 'DECISION.md', 'HASH_MANIFEST.json']


def keys(obj, names):
    require(type(obj) is dict and set(obj) == set(names.split()), 'CONTRACT_FIELDS')


def utc(text):
    require(isinstance(text, str) and len(text) == 20 and text.endswith('Z'), 'EXACT_UTC')
    try:
        dt = datetime.strptime(text, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=UTC)
    except ValueError:
        require(False, 'EXACT_UTC')
    return int(dt.timestamp()) * 1000


def window(w):
    require(type(w) is list and len(w) == 2, 'WINDOW')
    a, b = map(utc, w)
    require(a < b <= utc('2026-10-21T00:00:00Z'), 'DATE_SUPPORT')
    return a, b


def reference(r):
    keys(r, 'publisher_reference document_sha256 applicability acquisition_evidence')
    hash_value(r['document_sha256'])
    require(all(isinstance(r[k], str) and r[k].strip() for k in r), 'RIGHTS_EVIDENCE')


def acceptance(registry_id):
    require(registry_id in TRUSTED_REGISTRIES, 'TRUSTED_SCOPE_NOT_INSTALLED')
    pin = TRUSTED_REGISTRIES[registry_id]
    keys(pin, 'path sha256 accepted_by authenticity_reference')
    require(pin['accepted_by'] and pin['authenticity_reference'], 'AUTHENTICITY_REQUIRED')
    hash_value(pin['sha256'])
    record = load(read_exact(path(pin['path']), pin['sha256'], cap=4 * 1024 * 1024))
    return record, pin


def validate(r, m, a, pin, registration_path, manifest_path):
    """All identities, scope and rights pass before ANY source descriptor is opened."""
    keys(r, 'schema experiment_id registered_at origins support policy use_oi economics '
         'training_selection_history output_dir manifest_sha256 labels complete_net_claim')
    keys(m, 'schema files')
    keys(a, 'schema state accepted_at accepted_by authenticity_reference registration_sha256 '
         'manifest_sha256 registration_path manifest_path output_dir roots rights economics')
    require(r['schema'] == m['schema'] == a['schema'] == SCHEMA, 'SCHEMA')
    require(a['state'] == 'ACCEPTED' and a['accepted_by'] == pin['accepted_by']
            and a['authenticity_reference'] == pin['authenticity_reference'], 'SCOPE_NOT_ACCEPTED')
    require(a['registration_sha256'] == digest(r), 'REGISTRATION_NOT_ACCEPTED')
    require(a['manifest_sha256'] == r['manifest_sha256'] == digest(m), 'MANIFEST_NOT_ACCEPTED')
    require(a['registration_path'] == str(registration_path)
            and a['manifest_path'] == str(manifest_path), 'INPUT_IDENTITY')
    require(canonical(r['labels']) == canonical(LABELS), 'CLAIM_OR_PROMOTION_FORBIDDEN')
    require(canonical(r['policy']) == canonical(POLICY), 'POLICY_CHANGED')
    require(type(r['use_oi']) is bool and type(r['complete_net_claim']) is bool, 'CONTRACT_TYPE')
    require(isinstance(r['experiment_id'], str) and r['experiment_id'].strip()
            and isinstance(r['training_selection_history'], list)
            and len(r['training_selection_history']) > 0, 'SELECTION_HISTORY_REQUIRED')
    require(all(isinstance(v, str) and v.strip() for v in r['training_selection_history']),
            'SELECTION_HISTORY_REQUIRED')
    require(utc(r['registered_at']) < utc(a['accepted_at']), 'ACCEPTANCE_ORDER')
    left, right = window(r['origins'])
    lo, hi = window(r['support'])
    require(left % 3600000 == right % 3600000 == 0 and right-left <= 92*86400000,
            'ORIGIN_SCOPE')
    require(lo <= left-86400000 and hi >= right+POLICY['exit_ms']+120000
            and hi-lo <= 123*86400000, 'DATE_SUPPORT')
    require(a['rights'], 'RIGHTS_EVIDENCE')
    reference(a['rights'])
    require(a['economics'] == r['economics'], 'ECONOMICS_NOT_ACCEPTED')
    require(r['economics'] in ('PARTIAL_EXECUTION_SENSITIVITY', 'VERIFIED_SETTLEMENTS'),
            'ECONOMICS_MODE')
    require(not r['complete_net_claim'] or r['economics'] == 'VERIFIED_SETTLEMENTS',
            'COST_INCOMPLETE_NET_CLAIM')
    out = path(r['output_dir'])
    require(str(out) == a['output_dir'], 'OUTPUT_IDENTITY')
    roots = a['roots']
    require(type(roots) is dict and 0 < len(roots) <= 4, 'TRUSTED_ROOT_REQUIRED')
    root_paths = []
    for v in roots.values():
        keys(v, 'path device inode')
        root_paths.append(path(v['path']))
    for i, p in enumerate(root_paths):
        require(not out.is_relative_to(p) and not p.is_relative_to(out), 'OUTPUT_OVERLAP')
        for other in root_paths[:i]:
            require(not p.is_relative_to(other) and not other.is_relative_to(p), 'ROOT_OVERLAP')
    # Acceptance must be independently persisted outside inputs/output/raw roots.
    registry = path(pin['path'])
    for p in [out, *root_paths, registration_path.parent, manifest_path.parent]:
        require(not registry.is_relative_to(p), 'ACCEPTANCE_NOT_INDEPENDENT')
    require(not registration_path.is_relative_to(out) and not manifest_path.is_relative_to(out),
            'OUTPUT_OVERLAP')
    for name in OUTPUTS:
        absent(out / name)
    for v in roots.values():
        with directory(path(v['path'])) as fd:
            info = os.fstat(fd)
            require(info.st_dev == v['device'] and info.st_ino == v['inode'],
                    'TRUSTED_ROOT_IDENTITY_CHANGED')
            require(info.st_mode & 0o022 == 0, 'UNSAFE_ROOT_PERMISSIONS')
    require(type(m['files']) is list and 0 < len(m['files']) <= 200, 'FILE_LIMIT')
    seen, intervals = set(), {k: [] for k in SCHEMAS}
    for f in m['files']:
        keys(f, 'root path source_id venue symbol product family fields native_schema '
             'coverage sha256 stat publisher_url rights_sha256 availability_delay_ms format clock')
        require(f['root'] in roots, 'ROOT_NOT_ACCEPTED')
        p = path(f['path'])
        require(p.is_relative_to(path(roots[f['root']]['path']))
                and p != path(roots[f['root']]['path']),
                'FILE_OUTSIDE_ROOT')
        require(str(p) not in seen, 'DUPLICATE_SOURCE')
        seen.add(str(p))
        require(f['venue'] == 'binance' and f['symbol'] == 'BTCUSDT'
                and f['product'] == 'USD_M_PERPETUAL', 'SOURCE_IDENTITY')
        family = f['family']
        require(family in SCHEMAS and f['native_schema'] == SCHEMAS[family]
                and f['fields'] == FIELDS[family], 'NATIVE_FIELD_IDENTITY')
        require(f['source_id'] and f['publisher_url'].startswith(
            'https://data.binance.vision/data/futures/um/'), 'PUBLISHER_IDENTITY')
        require(f['rights_sha256'] == a['rights']['document_sha256'], 'RIGHTS_IDENTITY')
        require(type(f['availability_delay_ms']) is int
                and 0 <= f['availability_delay_ms'] <= 60000, 'AVAILABILITY_SEMANTICS')
        require(f['clock'] == 'BINANCE_NATIVE_UTC_EVENT_NOT_RECEIVER', 'CLOCK_NOT_ACCEPTED')
        require(f['format'] in ('csv', 'zip'), 'NATIVE_FORMAT')
        x, y = window(f['coverage'])
        require(lo <= x < y <= hi, 'FILE_SUPPORT_BOUNDARY')
        intervals[family].append((x, y))
        hash_value(f['sha256'])
    require(intervals['price_1m'], 'PRICE_SOURCE_REQUIRED')
    require(bool(intervals['oi_5m']) == r['use_oi'], 'OI_ADMISSION')
    for family, spans in intervals.items():
        spans.sort()
        require(all(x[1] <= y[0] for x, y in pairwise(spans)), 'OVERLAPPING_FILES')
    if r['economics'] == 'VERIFIED_SETTLEMENTS':
        require(intervals['funding'] and intervals['mark_1m'], 'FUNDING_MARK_REQUIRED')
        require(False, 'INDEPENDENT_SETTLEMENT_CLOCK_ADAPTER_NOT_INSTALLED')
    # Native funding calc_time and candle OPEN have no authenticated historical mapping.
    # Partial mode may carry them for QA, but never computes purported funding economics.
    for f in m['files']:
        require(file_info(path(f['path'])) == f['stat'], 'IDENTITY_CHANGED')
    require(sum(f['stat'][2] for f in m['files']) <= 128*1024*1024, 'TOTAL_SOURCE_BYTE_LIMIT')
    return r, m, a
