"""Offline safety, resumption, native clocks and source identity regressions."""
from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import zipfile
from collections import namedtuple
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path
from urllib.error import HTTPError

import pyarrow.parquet as pq
import pytest

from scripts.data.bline_r2 import inventory, pipeline, quality, report, transport
from tools.data.qc import BINANCE_METRICS_SCHEMA


def archive(path, day='2026-06-24', *, end_labels=False, duplicate=False, missing_ratio=False,
            symbol='BTCUSDT', bad_member=False):
    start = datetime.fromisoformat(day).replace(tzinfo=UTC)
    rows = [','.join(BINANCE_METRICS_SCHEMA)]
    for i in range(288):
        t = start+timedelta(minutes=(i+int(end_labels))*5)
        row = f'{t:%Y-%m-%d %H:%M:%S},{symbol},100,100000,2,{"" if missing_ratio else "1.5"},2,1'
        rows.append(row)
        if duplicate:
            rows.append(row)
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('../escape.csv' if bad_member else 'metrics.csv','\n'.join(rows)+'\n')
    return {'family':'metrics','venue':'binance','symbol':'BTCUSDT','period':day}


@pytest.mark.parametrize('end_labels,expected',[(True,'END_LABEL_PATTERN'),(False,'START_LABEL_PATTERN')])
def test_metric_day_label_patterns_and_no_blind_shift(tmp_path,end_labels,expected):
    path = tmp_path/'metrics.zip'
    task = archive(path,end_labels=end_labels)
    normalized = tmp_path/'normalized.parquet'
    qc = quality.scan_archive(path,task,transport.digest(path),normalized)
    assert qc['observed_label_pattern'] == expected
    rows = pq.read_table(normalized).to_pylist()
    assert rows[0]['content_upper_us_conservative']-rows[0]['native_label_us'] == 300_000_000
    assert rows[0]['native_create_time'].endswith('00:05:00' if end_labels else '00:00:00')
    assert qc['receiver_first_known_at'] is None and qc['price_or_return_labels_computed'] == 0


def test_duplicate_rows_kept_and_missing_ratio_not_imputed(tmp_path):
    path = tmp_path/'duplicate.zip'
    task = archive(path,duplicate=True,missing_ratio=True)
    qc = quality.scan_archive(path,task,transport.digest(path),tmp_path/'n.parquet')
    assert qc['rows']==576 and qc['duplicate_native_labels']==288
    assert qc['observed_label_pattern']=='START_LABEL_PATTERN'
    assert qc['missing_base_oi_rows']==0 and qc['missing_top_position_ratio_rows']==576
    assert all(r['top_position_long_short_ratio'] is None for r in pq.read_table(tmp_path/'n.parquet').to_pylist())


@pytest.mark.parametrize('kind',['wrong_symbol','traversal'])
def test_wrong_contract_and_unsafe_members_fail_closed(tmp_path,kind):
    path = tmp_path/'bad.zip'
    task = archive(path,symbol='BTCUSD' if kind=='wrong_symbol' else 'BTCUSDT',bad_member=kind=='traversal')
    with pytest.raises(ValueError,match='IDENTITY|UNSAFE'):
        quality.scan_archive(path,task,transport.digest(path))


def test_fixed_origin_exact_predecessor_and_5m_content_guard():
    origin = quality.epoch_us('2024-01-02T12:01:00Z')
    cutoff = origin-60*report.US
    latest = cutoff-300*report.US
    earlier = cutoff-600*report.US
    states = {t:(100.,1000.,2.,1.5,2.,1.) for t in [latest,latest-14400*report.US,earlier,earlier-14400*report.US]}
    assert report.state_at_origin(states,sorted(states),set(),origin)
    del states[earlier-14400*report.US]
    assert not report.state_at_origin(states,sorted(states),set(),origin)
    assert report.state_at_origin(states,sorted(states),set(),origin,content_delay_us=0)


def test_conflicting_latest_label_cannot_fall_back_to_rescue():
    origin = quality.epoch_us('2024-01-02T12:01:00Z')
    t = origin-60*report.US-600*report.US
    states = {s:(100.,1000.,2.,1.5,2.,1.) for s in [t,t-300*report.US,t-14400*report.US,t-14700*report.US]}
    assert not report.state_at_origin(states,sorted(states),{t},origin)


def test_uncertain_content_clock_does_not_rescue_a_stale_15m_label():
    origin = quality.epoch_us('2024-01-02T12:01:00Z')
    t = origin-60*report.US-900*report.US
    states = {s:(100.,1000.,2.,1.5,2.,1.) for s in [t,t-14400*report.US]}
    assert not report.state_at_origin(states,sorted(states),set(),origin)


def test_native_oi_usable_when_top_position_missing_but_joint_is_not():
    origin = quality.epoch_us('2024-01-02T12:01:00Z')
    t = origin-60*report.US-600*report.US
    states = {s:(100.,1000.,2.,None,2.,1.) for s in [t,t-14400*report.US]}
    assert report.state_at_origin(states,sorted(states),set(),origin,joint=False)
    assert not report.state_at_origin(states,sorted(states),set(),origin)


@pytest.mark.parametrize('origin',['2025-02-01T01:01:00Z','2026-02-01T12:01:00Z','2026-09-01T00:01:00Z'])
def test_known_exclusions_and_h40_warmup(origin):
    assert report.protected_feature_window(quality.epoch_us(origin))


def test_after_h40_warmup_can_be_descriptive_but_not_authorized():
    assert not report.protected_feature_window(quality.epoch_us('2026-02-03T00:01:00Z'))


class Response:
    def __init__(self,body,status=200,headers=None):
        self.body = io.BytesIO(body)
        self.status = status
        self.headers = {'Content-Length':str(len(body)),**(headers or {})}
    def __enter__(self):
        return self
    def __exit__(self,*args):
        self.body.close()
    def read(self,n):
        return self.body.read(n)


def test_download_resume_checks_range_and_final_sha(tmp_path,monkeypatch):
    payload = b'public historical archive'
    expected = hashlib.sha256(payload).hexdigest()
    dest = tmp_path/'file.zip'
    part = tmp_path/'file.zip.part'
    part.write_bytes(payload[:7])
    url = 'https://data.binance.vision/data/file.zip'
    (tmp_path/'file.zip.part.json').write_text(json.dumps({'url':url,'expected_sha256':expected,'etag':'"version"'}))
    client = transport.Transport(tmp_path)
    seen = []
    def open_response(u,family,headers):
        seen.append(headers)
        return Response(payload[7:],206,{'Content-Range':f'bytes 7-{len(payload)-1}/{len(payload)}'})
    monkeypatch.setattr(client,'_open',open_response)
    r = client.archive(url,'binance/metrics',dest,expected)
    assert seen == [{'Range':'bytes=7-','If-Range':'"version"'}]
    assert dest.read_bytes()==payload and r['resumed_from_bytes']==7 and not part.exists()


def test_server_ignores_range_restarts_safely(tmp_path,monkeypatch):
    payload = b'complete archive'
    expected = hashlib.sha256(payload).hexdigest()
    url = 'https://data.binance.vision/data/file.zip'
    (tmp_path/'file.zip.part').write_bytes(b'old partial')
    (tmp_path/'file.zip.part.json').write_text(json.dumps({'url':url,'expected_sha256':expected}))
    client = transport.Transport(tmp_path)
    monkeypatch.setattr(client,'_open',lambda *a:Response(payload))
    client.archive(url,'binance/metrics',tmp_path/'file.zip',expected)
    assert (tmp_path/'file.zip').read_bytes()==payload


def test_wrong_resume_range_and_checksum_never_promoted(tmp_path,monkeypatch):
    client = transport.Transport(tmp_path)
    monkeypatch.setattr(client,'_open',lambda *a:Response(b'bad'))
    with pytest.raises(ValueError,match='SHA256_MISMATCH'):
        client.archive('https://data.binance.vision/data/file.zip','binance/metrics',tmp_path/'file.zip','a'*64)
    assert not (tmp_path/'file.zip').exists()


def test_provider_denial_blocks_only_that_family(tmp_path,monkeypatch):
    client = transport.Transport(tmp_path)
    def denied(*args):
        raise HTTPError('https://data.binance.vision/data/x',451,'denied',{},None)
    monkeypatch.setattr(client,'_open',denied)
    with pytest.raises(transport.SourceBlocked,match='451'):
        client.metadata('https://data.binance.vision/data/x','binance/metrics')
    assert 'binance/metrics' in client.blocked and 'okx/funding_rates' not in client.blocked


def test_http_date_retry_after_is_honored_as_hold_without_early_retry(tmp_path,monkeypatch):
    client = transport.Transport(tmp_path)
    date = format_datetime(datetime.now(UTC)+timedelta(minutes=5),usegmt=True)
    def limited(*args):
        raise HTTPError('https://data.binance.vision/data/x',429,'limited',{'Retry-After':date},None)
    monkeypatch.setattr(client,'_open',limited)
    with pytest.raises(transport.SourceBlocked,match='RATE_LIMIT_HOLD'):
        client.metadata('https://data.binance.vision/data/x','binance/metrics')
    assert transport.retry_after_seconds('15')==15


def test_disk_floor_accounts_for_extraction_reserve(tmp_path):
    Disk = namedtuple('Disk','total used free')
    free = transport.FREE_FLOOR+transport.EXPANSION_RESERVE-1
    client = transport.Transport(tmp_path,disk_usage=lambda p:Disk(10**13,0,free))
    with pytest.raises(transport.SourceBlocked,match='400_GIB'):
        client.check_storage()


@pytest.mark.parametrize('url',['https://evil.example/data/x','http://data.binance.vision/data/x','https://data.binance.vision/api/account'])
def test_no_account_origin_or_protocol_fallback(tmp_path,url):
    with pytest.raises(ValueError,match='ORIGIN|PATH'):
        transport.Transport(tmp_path)._open(url,'binance/metrics')


def test_checksum_filename_bound_and_root_cannot_be_original(tmp_path):
    p = tmp_path/'file.zip.CHECKSUM'
    p.write_text('a'*64+'  other.zip\n')
    assert inventory.checksum(p,'file.zip') is None
    with pytest.raises(ValueError,match='ISOLATED'):
        pipeline.checked_root(Path('/root/workspace/project/crypto-data/historical'))


def test_bybit_rights_block_happens_before_fetch(tmp_path,monkeypatch):
    policy = {'bybit':{'state':'RIGHTS_UNRESOLVED_FOR_BULK_OI_ARCHIVE_RETENTION'}}
    (tmp_path/'rights_assessment.json').write_text(json.dumps(policy))
    (tmp_path/'ROOT_RECEIPT.json').write_text(json.dumps({'rights_assessment_sha256':transport.digest(tmp_path/'rights_assessment.json')}))
    (tmp_path/'existing_inventory.json').write_text('[]')
    task = {'venue':'bybit','asset':'BTC','product':'LINEAR_USDT_PERPETUAL','family':'open_interest',
            'symbol':'BTCUSDT','period':'2021-01-01','interval':'5m','url':'https://api.bybit.com/v5/market/open-interest'}
    monkeypatch.setattr(pipeline,'tasks',lambda *a:[task])
    monkeypatch.setattr(transport.Transport,'_open',lambda *a,**k:pytest.fail('must not fetch'))
    result = pipeline.acquire(tmp_path,'oi','2021-01-01','2021-01-02')
    assert result['status_counts']=={'RIGHTS_BLOCKED':1} and result['requests']==0


def test_repeated_objects_are_catalog_aliases_not_duplicate_coverage(tmp_path):
    path = tmp_path/'source.zip'
    path.write_bytes(b'fixture')
    sidecar = tmp_path/'source.zip.CHECKSUM'
    sidecar.write_text(transport.digest(path)+'  source.zip\n')
    db = tmp_path/'catalog.sqlite'
    c = sqlite3.connect(db)
    c.execute('''CREATE TABLE source_files(source_id TEXT,path TEXT,exchange TEXT,asset TEXT,symbol TEXT,
        product TEXT,family TEXT,interval TEXT,period TEXT,priority INTEGER,bytes INTEGER,raw_sha256 TEXT)''')
    for i in range(2):
        c.execute('INSERT INTO source_files VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (str(i),str(path),'binance','BTC','BTCUSDT','USD_M_PERPETUAL','metrics','5m','2024-01-01',i,path.stat().st_size,None))
    c.commit();c.close()
    rows = inventory.inspect_existing(db)
    assert len({r['actual_sha256'] for r in rows})==1
    assert all(r['verification']=='PUBLISHER_SHA256_VERIFIED' for r in rows)


def test_full_report_is_feature_only_deduplicated_and_preserves_r1(tmp_path):
    root = tmp_path/'bline-r2-fixture'
    root.mkdir()
    (root/'objects').mkdir()
    (root/'runs').mkdir()
    r1 = tmp_path/'lakehouse/research-bline-r1'
    (r1/'completion-final').mkdir(parents=True)
    (r1/'features-release').mkdir()
    c0 = tmp_path/'lakehouse/catalog.sqlite'
    c0.write_bytes(b'C0 TEST METADATA ONLY')
    (root/'ROOT_RECEIPT.json').write_text(json.dumps({'existing_catalog_sha256':transport.digest(c0)}))
    (root/'existing_inventory.json').write_text('[]')
    (root/'preservation_before.json').write_text(json.dumps({'owner_files':{},'r1_files':{}}))
    (r1/'completion-final/COMPLETION_RECEIPT.json').write_text(json.dumps({'BTC_binance':{'OI_eligible':0,'X_eligible':1}}))
    row = {'asset':'BTC','venue':'binance','t':quality.epoch_us('2024-01-01T12:01:00Z')//report.US,
           'x_complete':True,'z_status':'UNAVAILABLE'}
    r1panel = r1/'features-release/feature_panel.jsonl'
    r1panel.write_text(json.dumps(row)+'\n')
    original = transport.digest(r1panel)
    path = root/'objects/fixture.zip'
    task = archive(path,day='2024-01-01')
    normalized = root/'fixture.parquet'
    qc = quality.scan_archive(path,task,transport.digest(path),normalized)
    record = {**task,'asset':'BTC','product':'USD_M_PERPETUAL','interval':'5m','url':'https://data.binance.vision/data/fixture.zip',
        'status':'DOWNLOADED_VERIFIED','path':str(path),'sha256':transport.digest(path),'bytes':path.stat().st_size,
        'qc':qc,'normalized_metrics_path':str(normalized),'publisher_sha256':transport.digest(path)}
    conn = pipeline.database(root)
    keys = ['url','venue','asset','product','family','symbol','period','interval','status','path','sha256','bytes']
    conn.execute('INSERT INTO archives VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                 [record[k] for k in keys]+[json.dumps(record)])
    conn.commit();conn.close()
    result = report.report(root)
    assert result['comparison']['incremental_joint_conservative_vs_r1']==1
    assert result['comparison']['authorized_real_outcome_origins']==0
    assert result['checks']['selected_archives_SHA_verified']==1
    assert transport.digest(r1panel)==original
    output = Path(result['report_dir'])
    conn = sqlite3.connect(output/'deduplicated_catalog.sqlite')
    assert conn.execute('SELECT count(*) FROM objects').fetchone()[0]==1
    conn.close()
    receipt = json.loads((output/'COMPLETION_RECEIPT.json').read_text())
    assert all(transport.digest(output/p)==h for p,h in receipt['artifact_sha256'].items())


def test_unreviewed_rights_snapshot_cannot_initialize_another_root(tmp_path):
    evidence = tmp_path/'fake-evidence'
    evidence.mkdir()
    for name in ['TERMS_AND_CONDITIONS.md','README.md']:
        (evidence/('binance_'+name)).write_text('unreviewed replacement')
    output = tmp_path/'new-root'
    with pytest.raises(ValueError,match='SNAPSHOT_MISMATCH'):
        pipeline.initialize(output,evidence_dir=evidence)
    assert not output.exists()
