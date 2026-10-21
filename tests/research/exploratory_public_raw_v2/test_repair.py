"""Generated /tmp evidence only; no synthetic authority ships in the deployment."""

import copy
import hashlib
import io
import os
import socket
import subprocess
import tempfile
import zipfile
from pathlib import Path

import pytest

from scripts.research.exploratory_public_raw_v1 import GateError, contract
from scripts.research.exploratory_public_raw_v1.native import HOUR, MINUTE, parse
from scripts.research.exploratory_public_raw_v1.safeio import canonical, digest, file_info
from scripts.research.exploratory_public_raw_v2 import proof, runner, trust
from scripts.research.exploratory_public_raw_v2.__main__ import main


@pytest.fixture
def generated(monkeypatch, request):
    """Inject fake Controller metadata only in this temp test, never an installed anchor."""
    with tempfile.TemporaryDirectory(prefix='eprv2-', dir='/tmp') as name:
        base = Path(name)
        for d in ('experiment', 'authority', 'raw', 'documents'):
            (base/d).mkdir()
        exp, docs = base/'experiment', base/'documents'
        (exp/'output').mkdir()

        def ref(p, payload):
            if not isinstance(payload, bytes):
                payload = canonical(payload)
            p.write_bytes(payload)
            return {'path': str(p), 'sha256': hashlib.sha256(payload).hexdigest(),
                    'stat': file_info(p)}

        terms = ref(docs/'terms.md', b'ARTIFICIAL_TEST_ONLY_NO_REAL_AUTHORITY\n')
        assessment = ref(docs/'assessment.json', {'binance': {
            'terms_sha256': 'e'*64, 'terms_commit': 'GENERATED_COMMIT',
            'state': 'PERSONAL_ARCHIVE_RESEARCH_ALLOWED'}})
        pub_receipt = ref(docs/'receipt.json', {'documents': [{
            'file': 'terms.md', 'sha256': terms['sha256'], 'url': 'GENERATED_TERMS_URL',
            'bytes': terms['stat'][2], 'status': 200}]})
        rights = {'assessment': assessment, 'publisher_terms': terms,
                  'publisher_receipt': pub_receipt, 'r2_recorded_terms_sha256': 'e'*64,
                  'mapping': 'GENERATED_MAPPING_DIFFERENT_DIGESTS', 'scope': proof.RIGHTS_SCOPE}
        intake = {
            'candidate_origin_utc': proof.ORIGINS,
            'proposed_whole_source_window_utc': proof.SUPPORT,
            'acquisition_rights_evidence': {
                'rights_assessment_path': assessment['path'],
                'rights_assessment_sha256': assessment['sha256'],
                'publisher_document_receipt_path': pub_receipt['path'],
                'publisher_document_receipt_sha256': pub_receipt['sha256'],
                'publisher_snapshot_sha256': terms['sha256'],
                'publisher_snapshot_url': 'GENERATED_TERMS_URL',
                'publisher_terms_commit': 'GENERATED_COMMIT',
                'licence_mapping': rights['mapping']}, 'selected_exact_files': [],
        }
        identity = {'source_hashes_all_match': True, 'source_files': []}
        clock = {'complete': True, 'checks': []}
        manifest = {'schema': contract.SCHEMA, 'files': []}
        evidence = []
        for i, month in enumerate(('2021-03', '2021-04', '2021-05', '2021-06')):
            lo, hi = map(contract.utc, proof.MONTH_BOUNDARIES[i:i+2])
            # Deliberately sparse native source for the full-coverage negative test.
            stream = io.BytesIO()
            cutoff = contract.utc('2021-04-02T00:00:00Z')
            text = io.StringIO()
            for t in range(lo, hi if getattr(request, 'param', False) else lo+MINUTE, MINUTE):
                open_price = 90 if t == cutoff+8*HOUR+2*MINUTE else 100
                close_price = 98 if t >= cutoff-MINUTE else 100
                text.write(f'{t},{open_price},101,89,{close_price},1,'
                           f'{t+MINUTE-1},100,1,1,100,0\n')
            with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr(f'BTCUSDT-1m-{month}.csv',
                           text.getvalue())
            source = ref(base/'raw'/f'BTCUSDT-1m-{month}.zip', stream.getvalue())
            checksum = ref(docs/f'{month}.CHECKSUM',
                           f"{source['sha256']}  {Path(source['path']).name}\n".encode())
            url = ('https://data.binance.vision/data/futures/um/monthly/klines/'
                   f'BTCUSDT/1m/BTCUSDT-1m-{month}.zip')
            acquired, checked = '2026-10-19T05:46:59+00:00', '2026-10-19T05:46:57+00:00'
            record = {'path': source['path'], 'sha256': source['sha256'],
                      'publisher_sha256': source['sha256'], 'status': 'DOWNLOADED_VERIFIED',
                      'venue': 'binance', 'product': 'USD_M_PERPETUAL', 'symbol': 'BTCUSDT',
                      'family': 'klines', 'interval': '1m', 'period': month,
                      'publisher_checksum_required': True, 'url': url,
                      'bytes': source['stat'][2], 'publisher_checksum_path': checksum['path'],
                      'downloaded_at_utc': acquired, 'checked_at_utc': checked}
            evidence.append({'path': source['path'], 'catalog_record': record,
                             'publisher_checksum': checksum})
            intake['selected_exact_files'].append({
                'path': source['path'], 'reported_sha256': source['sha256'],
                'publisher_sha256_at_acquisition': source['sha256'], 'publisher_url': url,
                'acquired_at_utc': acquired, 'checked_at_utc': checked})
            identity['source_files'].append({
                **source, 'bytes': source['stat'][2], 'publisher_url': url,
                'acquired_at_utc': acquired, 'row_format': 'HEADERLESS',
                'zip_member': Path(source['path']).stem+'.csv'})
            clock['checks'].append({
                'source_sha256': source['sha256'], 'month': month, 'gap_minutes': 0,
                'full_month_utc_coverage': True, 'first_open_ms': lo,
                'last_open_ms': hi-MINUTE, 'rows': (hi-lo)//MINUTE,
                'native_clock': 'INCLUSIVE_CLOSE_OPEN_PLUS_59999'})
            manifest['files'].append({
                **source, 'root': 'generated', 'source_id': 'GENERATED_ONLY_'+month,
                'venue': 'binance', 'symbol': 'BTCUSDT', 'product': 'USD_M_PERPETUAL',
                'family': 'price_1m', 'fields': contract.FIELDS['price_1m'],
                'native_schema': contract.SCHEMAS['price_1m'],
                'coverage': proof.MONTH_BOUNDARIES[i:i+2], 'publisher_url': url,
                'rights_sha256': terms['sha256'], 'availability_delay_ms': 60000,
                'format': 'zip', 'clock': 'BINANCE_NATIVE_UTC_EVENT_NOT_RECEIVER'})
        refs = {'intake': ref(docs/'intake.json', intake)}
        identity['input_intake_sha256'] = refs['intake']['sha256']
        refs['identity'] = ref(docs/'identity.json', identity)
        clock['input_source_proof_sha256'] = refs['identity']['sha256']
        refs['clock'] = ref(docs/'clock.json', clock)
        monkeypatch.setattr(proof, 'CONTROLLER_HASHES', {k: v['sha256'] for k, v in refs.items()})
        p = {'schema': 'exact-public-source-proof.v2', 'controller_receipts': refs,
             'rights': rights, 'files': evidence,
             'catalog': {'path': str(docs/'bline-r2-20261019/catalog.sqlite'), 'table': 'archives'}}
        mp = ref(exp/'manifest.json', manifest)
        r = {'schema': contract.SCHEMA, 'experiment_id': 'GENERATED_TEST_ONLY',
             'registered_at': '2026-10-21T00:00:00Z', 'origins': proof.ORIGINS,
             'support': proof.SUPPORT, 'policy': copy.deepcopy(contract.POLICY),
             'use_oi': False, 'economics': 'PARTIAL_EXECUTION_SENSITIVITY',
             'training_selection_history': ['GENERATED_NO_REAL_AUTHORITY'],
             'output_dir': str(exp/'output'), 'manifest_sha256': mp['sha256'],
             'labels': dict(contract.LABELS), 'complete_net_claim': False}
        rp = ref(exp/'registration.json', r)
        raw = (base/'raw').stat()
        a = {'schema': contract.SCHEMA, 'state': 'ACCEPTED',
             'accepted_at': '2026-10-21T00:01:00Z', 'accepted_by': 'GENERATED_TEST_ONLY',
             'authenticity_reference': 'GENERATED_NOT_A_REAL_CONTROLLER',
             'registration_sha256': rp['sha256'], 'manifest_sha256': mp['sha256'],
             'registration_path': rp['path'], 'manifest_path': mp['path'],
             'output_dir': r['output_dir'], 'roots': {'generated': {
                 'path': str(base/'raw'), 'device': raw.st_dev, 'inode': raw.st_ino}},
             'rights': {'document_sha256': terms['sha256'],
                        'publisher_reference': 'GENERATED_TERMS_URL',
                        'applicability': proof.RIGHTS_SCOPE, 'acquisition_evidence': rights['mapping']},
             'economics': r['economics']}
        b = {'base': base, 'r': r, 'm': manifest, 'a': a, 'proof': p,
             'ref': ref, 'rp': rp['path'], 'mp': mp['path']}

        def forbidden(*args, **kwargs):
            raise AssertionError('No network or subprocess in synthetic admission tests')
        monkeypatch.setattr(socket, 'socket', forbidden)
        monkeypatch.setattr(subprocess, 'Popen', forbidden)
        yield b


def install_test_anchor(b, monkeypatch):
    """Only generated /tmp files. There is no production installation interface."""
    ref, base = b['ref'], b['base']
    pr = ref(base/'experiment'/'proof.json', b['proof'])
    scope = ref(base/'authority'/'scope.json', b['a'])
    provenance = ref(base/'authority'/'provenance.json', {
        'schema': 'controller-public-raw-provenance.v2', 'issuing_role': 'Controller B',
        'state': 'ACCEPTED', 'accepted_by': b['a']['accepted_by'],
        'authenticity_reference': b['a']['authenticity_reference'],
        'scope_sha256': scope['sha256'], 'source_proof_sha256': pr['sha256']})
    deployment = ref(base/'authority'/'deployment.json', {
        'schema': 'controller-public-raw-deployment.v2',
        'experiment_root': str(base/'experiment'),
        'scope_path': scope['path'], 'scope_sha256': scope['sha256'],
        'source_proof_path': pr['path'], 'source_proof_sha256': pr['sha256'],
        'provenance_path': provenance['path'], 'provenance_sha256': provenance['sha256']})
    anchor = {'path': deployment['path'], 'sha256': deployment['sha256'],
              'accepted_by': b['a']['accepted_by'],
              'authenticity_reference': b['a']['authenticity_reference']}
    monkeypatch.setattr(trust, 'DEPLOYMENT_ANCHORS', {'GENERATED_ONLY': anchor})
    return anchor


def test_default_authority_cannot_be_supplied_by_v1_fixture_or_cli(monkeypatch, capsys):
    monkeypatch.setattr(contract, 'TRUSTED_REGISTRIES', {'FAKE': {'path': '/tmp/fake'}})
    monkeypatch.setenv('ACCEPTED_REGISTRY', '/tmp/fake')

    def unread(*args, **kwargs):
        raise AssertionError('Uninstalled deployment must not open any file')
    monkeypatch.setattr(os, 'open', unread)
    assert not trust.DEPLOYMENT_ANCHORS
    assert main(['--registration', '/tmp/fake', '--manifest', '/tmp/fake',
                 '--accepted-registry-id', 'FAKE']) == 2
    assert 'CONTROLLER_DEPLOYMENT_NOT_INSTALLED' in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(['--synthetic', '--pin-sha256', '0'*64])


def test_generated_proof_preserves_two_different_terms_digests(generated):
    b = generated
    proof.validate_proof(b['r'], b['m'], b['a'], b['proof'])
    assert b['proof']['rights']['r2_recorded_terms_sha256'] != \
        b['proof']['rights']['publisher_terms']['sha256']


@pytest.mark.parametrize('change', ['protected', 'symbol', 'publisher_hash', 'missing_sidecar',
    'sidecar_bytes', 'sidecar_hash', 'rights_bytes', 'rights_identifier', 'controller_bytes',
    'clock', 'coverage', 'chronology', 'oi', 'net', 'cost', 'availability'])
def test_exact_source_proof_negatives(generated, change):
    b = generated
    f, p = b['m']['files'][0], b['proof']
    expected = None
    if change == 'protected':
        p['rights']['publisher_terms']['path'] = '/tmp/Quant-agent/never-open'
        expected = 'PROTECTED_PATH'
    elif change == 'symbol':
        p['files'][0]['catalog_record']['symbol'] = 'ETHUSDT'
    elif change == 'publisher_hash':
        p['files'][0]['catalog_record']['publisher_sha256'] = '0'*64
    elif change == 'missing_sidecar':
        Path(p['files'][0]['publisher_checksum']['path']).unlink()
    elif change in ('sidecar_bytes', 'rights_bytes', 'controller_bytes'):
        target = {'sidecar_bytes': p['files'][0]['publisher_checksum'],
                  'rights_bytes': p['rights']['publisher_terms'],
                  'controller_bytes': p['controller_receipts']['clock']}[change]
        Path(target['path']).write_bytes(b'ALTERED')
    elif change == 'sidecar_hash':
        target = p['files'][0]['publisher_checksum']
        p['files'][0]['publisher_checksum'] = b['ref'](
            Path(target['path']), f"{'0'*64}  {Path(f['path']).name}\n".encode())
    elif change == 'rights_identifier':
        p['rights']['r2_recorded_terms_sha256'] = p['rights']['publisher_terms']['sha256']
    elif change == 'clock':
        f['clock'] = 'RECEIVER_PIT'  # V1 security check, unchanged.
    elif change == 'coverage':
        f['coverage'] = ['2021-03-01T00:00:00Z', '2021-03-02T00:00:00Z']
    elif change == 'chronology':
        p['files'][0]['catalog_record']['downloaded_at_utc'] = '2027-01-01T00:00:00+00:00'
    elif change == 'oi':
        b['r']['use_oi'] = True
    elif change == 'net':
        b['r']['complete_net_claim'] = True
    elif change == 'cost':
        b['r']['economics'] = 'VERIFIED_SETTLEMENTS'
    else:
        f['availability_delay_ms'] = 0
    with pytest.raises(GateError, match=expected):
        if change == 'clock':
            # V1 validate rejects clock semantics before it visits source metadata.
            b['r']['manifest_sha256'] = b['a']['manifest_sha256'] = digest(b['m'])
            b['a']['registration_sha256'] = digest(b['r'])
            contract.validate(b['r'], b['m'], b['a'],
                              {'path': str(b['base']/'authority/scope.json'),
                               'accepted_by': b['a']['accepted_by'],
                               'authenticity_reference': b['a']['authenticity_reference']},
                              Path(b['rp']), Path(b['mp']))
        else:
            proof.validate_proof(b['r'], b['m'], b['a'], p)


@pytest.mark.parametrize('target', ['deployment', 'scope', 'provenance', 'proof'])
def test_externally_pinned_bytes_cannot_be_mutated(generated, monkeypatch, target):
    b = generated
    install_test_anchor(b, monkeypatch)
    paths = {'proof': b['base']/'experiment/proof.json',
             **{k: b['base']/f'authority/{k}.json' for k in ('deployment', 'scope', 'provenance')}}
    paths[target].write_bytes(b'{"state":"ACCEPTED","self_approved":true}\n')
    with pytest.raises(GateError, match='SHA_MISMATCH'):
        trust.resolve('GENERATED_ONLY')


def test_unaccepted_scope_even_with_test_anchor(generated, monkeypatch):
    generated['a']['state'] = 'NOT_ACCEPTED'
    install_test_anchor(generated, monkeypatch)
    with pytest.raises(GateError, match='PROVENANCE_BINDING'):
        trust.resolve('GENERATED_ONLY')


def test_registry_cannot_live_inside_experiment(generated, monkeypatch):
    b = generated
    anchor = install_test_anchor(b, monkeypatch)
    target = b['base']/'experiment/deployment.json'
    target.write_bytes(Path(anchor['path']).read_bytes())
    anchor['path'] = str(target)
    with pytest.raises(GateError, match='ACCEPTANCE_NOT_INDEPENDENT'):
        trust.resolve('GENERATED_ONLY')


def test_false_provenance_cannot_be_repaired_by_rehashing_only(generated, monkeypatch):
    b = generated
    anchor = install_test_anchor(b, monkeypatch)
    from scripts.research.exploratory_public_raw_v1.safeio import load
    dp = Path(anchor['path'])
    d = load(dp.read_bytes())
    pp = Path(d['provenance_path'])
    p = load(pp.read_bytes())
    p['issuing_role'] = 'Experiment author'
    pp.write_bytes(canonical(p))
    d['provenance_sha256'] = digest(p)
    dp.write_bytes(canonical(d))
    anchor['sha256'] = digest(d)
    with pytest.raises(GateError, match='INDEPENDENT_CONTROLLER_PROVENANCE_REQUIRED'):
        trust.resolve('GENERATED_ONLY')


def test_full_clock_gate_prevents_evaluation_of_sparse_archive(generated, monkeypatch):
    b = generated
    install_test_anchor(b, monkeypatch)

    def forbidden(*args):
        raise AssertionError('No outcomes before full native coverage')
    monkeypatch.setattr(runner, 'evaluate', forbidden)
    with pytest.raises(GateError, match='FULL_NATIVE_MINUTE_COVERAGE_REQUIRED'):
        runner.execute(b['rp'], b['mp'], 'GENERATED_ONLY')
    assert not list((b['base']/'experiment/output').iterdir())


@pytest.mark.parametrize('generated', [True], indirect=True)
def test_generated_full_clock_run_has_exact_delays_and_null_net(generated, monkeypatch):
    import csv

    from scripts.research.exploratory_public_raw_v1.safeio import load
    b = generated
    install_test_anchor(b, monkeypatch)
    result = runner.execute(b['rp'], b['mp'], 'GENERATED_ONLY')
    output = b['base']/'experiment/output'
    with (output/'BTC_TRADE_LEDGER.csv').open() as source:
        rows = list(csv.DictReader(source))
    assert len(rows) == 1 and rows[0]['arm'] == 'X_full'
    row = rows[0]
    assert int(row['entry_ms'])-int(row['origin_ms']) == MINUTE
    assert int(row['exit_ms'])-int(row['entry_ms']) == 8*HOUR
    assert float(row['gross_return']) == pytest.approx(0.1)
    assert float(row['partial_cost_adjusted_return']) == pytest.approx(0.0984)
    assert float(row['stress_partial_return']) == pytest.approx(0.0968)
    assert row['modeled_net_return'] == row['funding_return'] == ''
    assert result['complete_modeled_net_pnl'] is False
    economics = load((output/'BTC_ECONOMICS.json').read_bytes())
    assert economics['arms']['X_full']['year_trade_shares'] == {'2021': 1}
    for name, sha in load((output/'HASH_MANIFEST.json').read_bytes()).items():
        assert hashlib.sha256((output/name).read_bytes()).hexdigest() == sha


def test_output_collision_before_raw_payloads(generated, monkeypatch):
    b = generated
    install_test_anchor(b, monkeypatch)
    (b['base']/'experiment/output/DECISION.md').write_text('preserve me')
    monkeypatch.setattr(runner, 'read_sources', lambda *args: pytest.fail('Raw source opened'))
    with pytest.raises(GateError, match='OUTPUT_COLLISION'):
        runner.execute(b['rp'], b['mp'], 'GENERATED_ONLY')


def test_native_clock_and_zip_identity_negatives(generated):
    f = generated['m']['files'][0]
    lo = contract.utc(f['coverage'][0])
    for member, close in (('../evil.csv', lo+MINUTE-1), ('data.csv', lo+MINUTE)):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as z:
            z.writestr(member, f'{lo},100,101,99,100,1,{close},100,1,1,100,0\n')
        with pytest.raises(GateError):
            parse(f, stream.getvalue())


def test_descriptive_effective_clusters_do_not_claim_independence():
    metrics = {'X_full': {'iso_week_counts': {'W1': 2, 'W2': 2}, 'years': {'2021': 4}}}
    runner.concentration(metrics)
    assert metrics['X_full']['effective_week_clusters'] == 2
    assert metrics['X_full']['year_trade_shares'] == {'2021': 1}
    assert metrics['X_full']['effective_clusters_are_not_independent_sample_size'] is True
