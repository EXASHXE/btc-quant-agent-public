"""All payloads generated under /tmp. No inherited market or protected fixtures."""

import builtins
import copy
import csv
import hashlib
import io
import json
import os
import socket
import subprocess
import tempfile
import zipfile
from pathlib import Path

import pytest

from scripts.research.exploratory_public_raw_v1 import GateError, contract
from scripts.research.exploratory_public_raw_v1.__main__ import main
from scripts.research.exploratory_public_raw_v1.evaluate import payoff
from scripts.research.exploratory_public_raw_v1.native import (
    HOUR,
    MINUTE,
    feature_masks,
    parse,
    read_sources,
)
from scripts.research.exploratory_public_raw_v1.runner import execute
from scripts.research.exploratory_public_raw_v1.safeio import (
    canonical,
    digest,
    file_info,
    load,
    path,
)


@pytest.fixture
def bundle(monkeypatch):
    with tempfile.TemporaryDirectory(prefix='eprv1-', dir='/tmp') as name:
        base = Path(name)
        for n in ('inputs', 'acceptance', 'raw', 'output'):
            (base/n).mkdir()
        start = contract.utc('2021-04-01T00:00:00Z')
        cutoff = start+24*HOUR
        manifest = {'schema': contract.SCHEMA, 'files': []}
        rights = {'publisher_reference': 'ARTIFICIAL_TEST_ONLY',
                  'document_sha256': 'a'*64, 'applicability': 'GENERATED_TEST_ONLY',
                  'acquisition_evidence': 'TEST_GENERATOR_NO_REAL_AUTHORITY'}
        for family in ('price_1m', 'oi_5m'):
            output = io.StringIO(newline='')
            writer = csv.writer(output, lineterminator='\n')
            writer.writerow(contract.SCHEMAS[family])
            step = MINUTE if family == 'price_1m' else 5*MINUTE
            for t in range(start, start+48*HOUR, step):
                if family == 'price_1m':
                    open_price = 90 if t == cutoff+2*MINUTE+8*HOUR else 100
                    close = 100 if t < cutoff-MINUTE else 98
                    writer.writerow([t, open_price, 101, 89, close, 1, t+MINUTE-1,
                                     100, 1, 1, 100, 0])
                else:
                    from datetime import UTC, datetime
                    stamp = datetime.fromtimestamp(t/1000, UTC).strftime('%Y-%m-%d %H:%M:%S')
                    writer.writerow([stamp, 'BTCUSDT', 100 if t < cutoff-4*HOUR else 102, 10000, '', '', '', ''])
            payload = output.getvalue().encode()
            p = base/'raw'/f'{family}.csv'
            p.write_bytes(payload)
            manifest['files'].append({
                'root': 'test-native', 'path': str(p), 'source_id': f'TEST_ONLY_{family}',
                'venue': 'binance', 'symbol': 'BTCUSDT', 'product': 'USD_M_PERPETUAL',
                'family': family, 'fields': contract.FIELDS[family],
                'native_schema': contract.SCHEMAS[family],
                'coverage': ['2021-04-01T00:00:00Z', '2021-04-03T00:00:00Z'],
                'sha256': hashlib.sha256(payload).hexdigest(), 'stat': file_info(p),
                'publisher_url': 'https://data.binance.vision/data/futures/um/TEST_ONLY',
                'rights_sha256': rights['document_sha256'], 'availability_delay_ms': 0,
                'format': 'csv', 'clock': 'BINANCE_NATIVE_UTC_EVENT_NOT_RECEIVER'})
        registration = {
            'schema': contract.SCHEMA, 'experiment_id': 'FAKE_PUBLIC_RAW_TEST_ONLY',
            'registered_at': '2026-10-21T00:00:00Z',
            'origins': ['2021-04-02T00:00:00Z', '2021-04-02T12:00:00Z'],
            'support': ['2021-04-01T00:00:00Z', '2021-04-03T00:00:00Z'],
            'policy': copy.deepcopy(contract.POLICY), 'use_oi': True,
            'economics': 'PARTIAL_EXECUTION_SENSITIVITY',
            'training_selection_history': ['GENERATED_TEST_ONLY; no fitted model'],
            'output_dir': str(base/'output'), 'manifest_sha256': digest(manifest),
            'labels': dict(contract.LABELS), 'complete_net_claim': False}
        rp, mp, ap = base/'inputs'/'registration.json', base/'inputs'/'manifest.json', \
            base/'acceptance'/'scope.json'
        accepted = {
            'schema': contract.SCHEMA, 'state': 'ACCEPTED',
            'accepted_at': '2026-10-21T00:01:00Z', 'accepted_by': 'TEST_ONLY_EXTERNAL_PIN',
            'authenticity_reference': 'GENERATED_FIXTURE_NOT_REAL_AUTHORITY',
            'registration_sha256': digest(registration), 'manifest_sha256': digest(manifest),
            'registration_path': str(rp), 'manifest_path': str(mp),
            'output_dir': registration['output_dir'], 'roots': {'test-native': {
                'path': str(base/'raw'), 'device': (base/'raw').stat().st_dev,
                'inode': (base/'raw').stat().st_ino}},
            'rights': rights, 'economics': registration['economics']}
        b = {'r': registration, 'm': manifest, 'a': accepted, 'rp': rp, 'mp': mp,
             'ap': ap, 'base': base, 'monkeypatch': monkeypatch, 'opened': []}
        repin(b)
        # Audit Python and descriptor payload access; directories are traversed safely.
        original_low, original_io, original_builtin = os.open, io.open, builtins.open

        def audit(value):
            if not isinstance(value, int):
                p = Path(value)
                assert p.is_relative_to(base), f'Nonfixture payload open attempted: {p}'
                b['opened'].append(str(p))

        def low(value, flags, mode=0o777, *, dir_fd=None):
            p = Path(value)
            if not flags & os.O_DIRECTORY:
                if not p.is_absolute():
                    p = Path(os.readlink(f'/proc/self/fd/{dir_fd}'))/p
                audit(p)
            return original_low(value, flags, mode, dir_fd=dir_fd)

        def wrap(fn):
            def high(value, *args, **kwargs):
                audit(value)
                return fn(value, *args, **kwargs)
            return high

        monkeypatch.setattr(os, 'open', low)
        monkeypatch.setattr(io, 'open', wrap(original_io))
        monkeypatch.setattr(builtins, 'open', wrap(original_builtin))

        def forbidden(*args, **kwargs):
            raise AssertionError('No network, credentials, account or subprocess interfaces')

        monkeypatch.setattr(socket, 'socket', forbidden)
        monkeypatch.setattr(subprocess, 'Popen', forbidden)
        yield b


def repin(b):
    """Simulate a separately installed external authority, only for this temp fixture."""
    r, m, a = b['r'], b['m'], b['a']
    r['manifest_sha256'] = digest(m)
    a.update(registration_sha256=digest(r), manifest_sha256=digest(m))
    b['rp'].write_bytes(canonical(r))
    b['mp'].write_bytes(canonical(m))
    b['ap'].write_bytes(canonical(a))
    pin = {'path': str(b['ap']), 'sha256': hashlib.sha256(b['ap'].read_bytes()).hexdigest(),
           'accepted_by': a['accepted_by'], 'authenticity_reference': a['authenticity_reference']}
    b['monkeypatch'].setattr(contract, 'TRUSTED_REGISTRIES', {'TEST_ONLY': pin})


def run(b):
    return execute(b['rp'], b['mp'], 'TEST_ONLY')


def assert_no_source_open(b):
    assert not any(Path(p).is_relative_to(b['base']/'raw') for p in b['opened'])


# Negative gates are exercised before any positive evaluation.
@pytest.mark.parametrize('component', ['Quant-agent', 'H39', 'H40', 'H41', 'Forward', 'Final',
                                      'OOS', 'A-line', '.aws', '.git', 'protected', 'credentials'])
def test_protected_roots_never_visited(bundle, component):
    b = bundle
    b['m']['files'][0]['path'] = str(b['base']/component/'missing.csv')
    repin(b)
    b['opened'].clear()
    with pytest.raises(GateError, match='PROTECTED_PATH'):
        run(b)
    assert_no_source_open(b)


@pytest.mark.parametrize('change', ['traversal', 'path', 'symbol', 'product', 'venue', 'field',
                                    'schema', 'rights', 'scope', 'support', 'clock', 'output',
                                    'credential', 'endpoint', 'holdout', 'P3', 'Alpha',
                                    'TESTNET', 'LIVE', 'net', 'settlement', 'missing_funding'])
def test_metadata_gates_before_source_open(bundle, change):
    b, expected = bundle, None
    f, r, a = b['m']['files'][0], b['r'], b['a']
    if change == 'traversal':
        f['path'] = str(b['base'])+'/raw/../raw/price_1m.csv'
    elif change == 'path':
        f['path'] = str(b['base']/'elsewhere.csv')
    elif change in ('symbol', 'product', 'venue'):
        f[change] = 'UNADMITTED'
    elif change == 'field':
        f['fields'] = ['outcome_label']
    elif change == 'schema':
        f['native_schema'] = ['open_time', 'private_outcome']
    elif change == 'rights':
        a['rights'] = {}
        expected = 'RIGHTS_EVIDENCE'
    elif change == 'scope':
        a['state'] = 'REVOKED'
    elif change == 'support':
        r['support'][0] = '2021-04-02T00:00:00Z'
    elif change == 'clock':
        f['availability_delay_ms'] = -1
    elif change == 'output':
        r['output_dir'] = a['output_dir'] = str(b['base']/'raw')
    elif change in ('credential', 'endpoint'):
        r[change] = 'NOT_INVOKED'
    elif change == 'holdout':
        r['labels']['holdout'] = 'CLEAN'
    elif change in ('P3', 'Alpha', 'TESTNET', 'LIVE'):
        r['labels'][change] = 'PROMOTED'
    elif change == 'net':
        r['complete_net_claim'] = True
        expected = 'COST_INCOMPLETE_NET_CLAIM'
    elif change in ('settlement', 'missing_funding'):
        r['economics'] = a['economics'] = 'VERIFIED_SETTLEMENTS'
        expected = 'FUNDING_MARK_REQUIRED'
    repin(b)
    b['opened'].clear()
    with pytest.raises(GateError, match=expected):
        run(b)
    assert_no_source_open(b)


def test_no_deployed_authority_or_cli_override(bundle, monkeypatch, capsys):
    monkeypatch.setattr(contract, 'TRUSTED_REGISTRIES', {})
    bundle['opened'].clear()
    assert main(['--registration', str(bundle['rp']), '--manifest', str(bundle['mp']),
                 '--accepted-registry-id', 'TEST_ONLY']) == 2
    assert 'TRUSTED_SCOPE_NOT_INSTALLED' in capsys.readouterr().out
    assert bundle['opened'] == []
    with pytest.raises(SystemExit):
        main(['--enabled', '--synthetic'])


@pytest.mark.parametrize('target', ['registration', 'manifest', 'acceptance'])
def test_mutated_or_self_approved_inputs(bundle, target):
    b = bundle
    p = {'registration': b['rp'], 'manifest': b['mp'], 'acceptance': b['ap']}[target]
    d = json.loads(p.read_bytes())
    d['self_approved'] = True
    p.write_bytes(canonical(d))
    b['opened'].clear()
    with pytest.raises(GateError):
        run(b)
    assert_no_source_open(b)


@pytest.mark.parametrize('change', ['file_symlink', 'parent_symlink', 'hardlink', 'missing',
                                    'mutated', 'unsafe_mode', 'wrong_sha', 'wrong_inode'])
def test_source_identity_link_and_sha(bundle, change):
    b = bundle
    f = b['m']['files'][0]
    p = Path(f['path'])
    if change == 'file_symlink':
        p.unlink()
        p.symlink_to(b['base']/'unvisited')
    elif change == 'parent_symlink':
        raw = b['base']/'raw'
        raw.rename(b['base']/'elsewhere')
        raw.symlink_to(b['base']/'elsewhere', target_is_directory=True)
    elif change == 'hardlink':
        os.link(p, b['base']/'extra_link')
    elif change == 'missing':
        p.unlink()
    elif change == 'mutated':
        with p.open('ab') as stream:
            stream.write(b'\n')
    elif change == 'unsafe_mode':
        p.chmod(0o666)
    elif change == 'wrong_sha':
        f['sha256'] = '0'*64
        repin(b)
    elif change == 'wrong_inode':
        f['stat'][1] += 1
        repin(b)
    b['opened'].clear()
    with pytest.raises(GateError):
        run(b)
    if change != 'wrong_sha':
        assert_no_source_open(b)
    assert not list((b['base']/'output').iterdir())


def test_independent_scope_location(bundle):
    b = bundle
    ap = b['rp'].parent/'scope.json'
    ap.write_bytes(b['ap'].read_bytes())
    contract.TRUSTED_REGISTRIES['TEST_ONLY']['path'] = str(ap)
    b['opened'].clear()
    with pytest.raises(GateError, match='ACCEPTANCE_NOT_INDEPENDENT'):
        run(b)
    assert_no_source_open(b)


def test_output_collision_before_raw(bundle):
    (bundle['base']/'output'/'DECISION.md').write_text('existing')
    bundle['opened'].clear()
    with pytest.raises(GateError, match='OUTPUT_COLLISION'):
        run(bundle)
    assert_no_source_open(bundle)


@pytest.mark.parametrize('change', ['outside', 'duplicate', 'clock', 'symbol', 'schema'])
def test_payload_semantic_failure_has_no_outcomes(bundle, change):
    b = bundle
    f = b['m']['files'][1 if change == 'symbol' else 0]
    rows = list(csv.reader(io.StringIO(Path(f['path']).read_text())))
    if change == 'outside':
        rows[1][0] = str(int(rows[1][0])-MINUTE)
    elif change == 'duplicate':
        rows.insert(2, rows[1])
    elif change == 'clock':
        rows[1][6] = str(int(rows[1][0])+MINUTE)
    elif change == 'symbol':
        rows[1][1] = 'ETHUSDT'
    else:
        rows[0][0] = 'private_outcome'
    stream = io.StringIO()
    csv.writer(stream).writerows(rows)
    payload = stream.getvalue().encode()
    Path(f['path']).write_bytes(payload)
    f.update(sha256=hashlib.sha256(payload).hexdigest(), stat=file_info(Path(f['path'])))
    repin(b)
    with pytest.raises(GateError):
        run(b)
    assert not list((b['base']/'output').iterdir())


def test_causal_feature_masks_ignore_future_outcomes_and_late_availability(bundle):
    b = bundle
    tables, _ = read_sources(b['m'])
    masks = feature_masks(b['r'], tables)
    cutoff = contract.utc(b['r']['origins'][0])
    assert masks[0]['x'] is True
    tables['price_1m'][cutoff+2*MINUTE]['open'] = 1e9
    tables['price_1m'][cutoff+8*HOUR+2*MINUTE]['open'] = 0.01
    assert masks == feature_masks(b['r'], tables)
    tables['price_1m'][cutoff-MINUTE]['available'] = cutoff+2*MINUTE
    assert feature_masks(b['r'], tables)[0]['x_valid'] is False
    # Receiver PIT remains UNKNOWN even when event-time availability passes.


@pytest.mark.parametrize('name', ['../evil.csv', '/evil.csv', 'nested/data.csv'])
def test_unsafe_zip_member(bundle, name):
    f = dict(bundle['m']['files'][0], format='zip')
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as z:
        z.writestr(name, 'x')
    with pytest.raises(GateError, match='UNSAFE_ZIP_MEMBER'):
        parse(f, stream.getvalue())


def test_positive_native_zip_and_known_short_payoff(bundle):
    f = dict(bundle['m']['files'][0], format='zip')
    stream = io.BytesIO()
    payload = Path(f['path']).read_bytes()
    with zipfile.ZipFile(stream, 'w') as z:
        z.writestr('BTCUSDT-1m-TEST.csv', payload)
    assert len(parse(f, stream.getvalue())) == 48*60
    baseline = payoff(100, 90, contract.POLICY['baseline'])
    stress = payoff(100, 90, contract.POLICY['stress'])
    assert baseline['gross_return'] == pytest.approx(0.1)
    assert baseline['fee_return'] == pytest.approx(0.0008)
    assert baseline['slippage_return'] == pytest.approx(0.0008)
    assert baseline['partial_cost_adjusted_return'] == pytest.approx(0.0984)
    assert stress['partial_cost_adjusted_return'] == pytest.approx(0.0968)
    assert payoff(100, 110, contract.POLICY['baseline'])['gross_return'] == pytest.approx(-0.1)


def test_positive_partial_run_reproducible_and_funding_never_zero(bundle):
    b = bundle
    receipt = run(b)
    output = b['base']/'output'
    ledger = list(csv.DictReader(io.StringIO((output/'BTC_TRADE_LEDGER.csv').read_text())))
    x = [r for r in ledger if r['arm'] == 'X_full']
    assert len(x) == 1
    assert float(x[0]['gross_return']) == pytest.approx(0.1)
    assert float(x[0]['partial_cost_adjusted_return']) == pytest.approx(0.0984)
    assert int(x[0]['exit_ms'])-int(x[0]['entry_ms']) == 8*HOUR
    assert all(r['modeled_net_return'] == r['funding_return'] == '' for r in ledger)
    assert receipt['complete_modeled_net_pnl'] is False
    qa = load((output/'SOURCE_QA.json').read_bytes())
    assert digest(qa['feature_masks']) == receipt['feature_masks_sha256']
    assert all(not m['z'] or m['common_valid'] for m in qa['feature_masks'])
    hashes = load((output/'HASH_MANIFEST.json').read_bytes())
    assert len(hashes) == 9
    for name, expected in hashes.items():
        p = output/name
        assert hashlib.sha256(p.read_bytes()).hexdigest() == expected
        assert p.stat().st_mode & 0o777 == 0o400
    # Re-run into a fresh directory with the same frozen market inputs/masks.
    previous = (output/'BTC_TRADE_LEDGER.csv').read_bytes()
    out2 = b['base']/'output2'
    out2.mkdir()
    b['r']['output_dir'] = b['a']['output_dir'] = str(out2)
    repin(b)
    assert run(b)['feature_masks_sha256'] == receipt['feature_masks_sha256']
    assert (out2/'BTC_TRADE_LEDGER.csv').read_bytes() == previous


def test_x_full_and_matched_masks_missing_oi_without_outcome_filter(bundle):
    b = bundle
    tables, _ = read_sources(b['m'])
    cutoff = contract.utc(b['r']['origins'][0])
    del tables['oi_5m'][cutoff]
    masks = feature_masks(b['r'], tables)
    assert masks[0]['x_valid'] is True and masks[0]['common_valid'] is False
    assert masks[0]['x'] is True and masks[0]['z'] is False


def test_duplicate_json_and_nonfinite_rejected():
    for payload in (b'{"a":1,"a":2}', b'{"a":NaN}'):
        with pytest.raises(GateError):
            load(payload)


def test_path_rejects_relative_windows_and_endpoint():
    for p in ('../raw.csv', 'C:\\market\\data.csv', 'https://example.invalid/raw.csv'):
        with pytest.raises(GateError):
            path(p)


@pytest.mark.parametrize('change', ['entry', 'exit', 'holding'])
def test_missing_execution_bars_skip_with_reason(bundle, change):
    from scripts.research.exploratory_public_raw_v1.evaluate import evaluate
    b = bundle
    tables, _ = read_sources(b['m'])
    masks = feature_masks(b['r'], tables)
    cutoff = contract.utc(b['r']['origins'][0])
    offset = {'entry': 2*MINUTE, 'exit': 8*HOUR+2*MINUTE, 'holding': 30*MINUTE}[change]
    del tables['price_1m'][cutoff+offset]
    ledger, summaries, reasons = evaluate(b['r'], tables, masks)
    assert len({row['entry_ms'] for row in ledger if row['arm'] == 'X_full'}) <= 1
    code = 'MISSING_HOLDING_BAR' if change == 'holding' else 'MISSING_EXACT_ENTRY_OR_EXIT'
    assert any(r['arm'] == 'X_full' and r['reason'] == code for r in reasons)
    assert summaries['X_full']['gross']['trades'] == len(
        [r for r in ledger if r['arm'] == 'X_full'])


def test_oi_filter_is_matched_subset_and_single_position(bundle):
    from scripts.research.exploratory_public_raw_v1.evaluate import evaluate
    b = bundle
    tables, _ = read_sources(b['m'])
    masks = feature_masks(b['r'], tables)
    assert masks[0]['common_valid'] and masks[0]['x'] and masks[0]['z']
    assert all(not (r['x'] and r['z']) or r['x'] for r in masks)
    ledger, _, reasons = evaluate(b['r'], tables, masks)
    for arm in ('X_full', 'X_common', 'XZ_common'):
        trades = [r for r in ledger if r['arm'] == arm]
        assert len(trades) == 1
    assert any(r['reason'] == 'CONCURRENT_POSITION' for r in reasons)


def test_x_only_does_not_require_unadmitted_oi(bundle):
    b = bundle
    b['r']['use_oi'] = False
    b['m']['files'] = [b['m']['files'][0]]
    repin(b)
    run(b)
    result = load((b['base']/'output'/'BTC_ECONOMICS.json').read_bytes())
    assert set(result['arms']) == {'X_full'}


@pytest.mark.parametrize('kind', ['source', 'scope', 'registration'])
def test_mutation_during_evaluation_blocks_publication(bundle, monkeypatch, kind):
    from scripts.research.exploratory_public_raw_v1 import runner
    b = bundle
    original = runner.evaluate

    def mutate(*args):
        result = original(*args)
        if kind == 'source':
            with Path(b['m']['files'][0]['path']).open('ab') as stream:
                stream.write(b'\n')
        else:
            p = b['ap'] if kind == 'scope' else b['rp']
            p.write_bytes(b'{"state":"REVOKED"}')
        return result

    monkeypatch.setattr(runner, 'evaluate', mutate)
    with pytest.raises(GateError):
        run(b)
    assert not list((b['base']/'output').iterdir())


def test_complete_inventory_cannot_invent_settlement_mapping(bundle):
    b = bundle
    for family in ('funding', 'mark_1m'):
        f = copy.deepcopy(b['m']['files'][0])
        p = b['base']/'raw'/f'{family}.csv'
        p.write_text('TEST_ONLY_UNREAD\n')
        f.update(path=str(p), family=family, fields=contract.FIELDS[family],
                 native_schema=contract.SCHEMAS[family], stat=file_info(p),
                 sha256=hashlib.sha256(p.read_bytes()).hexdigest())
        b['m']['files'].append(f)
    b['r']['economics'] = b['a']['economics'] = 'VERIFIED_SETTLEMENTS'
    b['r']['complete_net_claim'] = True
    repin(b)
    b['opened'].clear()
    with pytest.raises(GateError, match='INDEPENDENT_SETTLEMENT_CLOCK_ADAPTER_NOT_INSTALLED'):
        run(b)
    assert_no_source_open(b)


def test_native_funding_offsets_are_not_snapped(bundle):
    f = dict(bundle['m']['files'][0], family='funding',
             native_schema=contract.SCHEMAS['funding'])
    t = contract.utc('2021-04-01T00:00:00Z')+25
    payload = f'calc_time,funding_interval_hours,last_funding_rate\n{t},8,0.001\n'.encode()
    rows = parse(f, payload)
    assert rows[0]['t'] == t
    assert 'economic_settlement' not in rows[0]


@pytest.mark.parametrize('kind', ['root_inode', 'root_permissions', 'file_boundary', 'date_cap',
                                  'native_clock', 'non_utc', 'manifest_path'])
def test_additional_scope_boundaries_before_payload(bundle, kind):
    b = bundle
    if kind == 'root_inode':
        b['a']['roots']['test-native']['inode'] += 1
    elif kind == 'root_permissions':
        (b['base']/'raw').chmod(0o777)
    elif kind == 'file_boundary':
        b['m']['files'][0]['coverage'][0] = '2021-03-31T00:00:00Z'
    elif kind == 'date_cap':
        b['r']['support'][1] = '2026-10-22T00:00:00Z'
    elif kind == 'native_clock':
        b['m']['files'][0]['clock'] = 'RECEIVER_PIT_PROVEN'
    elif kind == 'non_utc':
        b['r']['origins'][0] = '2021-04-02T00:00:00+08:00'
    else:
        b['a']['manifest_path'] = str(b['rp'])
    repin(b)
    b['opened'].clear()
    with pytest.raises(GateError):
        run(b)
    assert_no_source_open(b)
