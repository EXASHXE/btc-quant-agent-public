"""Read-only, exact-manifest R3 reuse; partial Mark clocks are preserved."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from contextlib import contextmanager
from itertools import pairwise
from pathlib import Path

import numpy as np

from scripts.strategy_research.g2_btc_two_lead_funding_mark_r3 import sources as r3

from .gaps import ALLOWED_DAYS, SCRATCH, day_plan

ROOT = Path(__file__).resolve().parents[3]
OLD_PUBLIC = Path('/tmp/btc-two-lead-funding-mark-r3')
OLD_EP = ROOT/'evidence/v0.6/b_line/g2_btc_two_lead_funding_mark_r3'


@contextmanager
def own_fetch_destination():
    previous=r3.SCRATCH
    r3.SCRATCH=SCRATCH
    try:
        yield
    finally:
        r3.SCRATCH=previous


def guard_file(path, base):
    if path.parent != base or base.is_symlink() or path.is_symlink():
        raise ValueError('Public cache must resolve within exact approved R3 or R31 scratch')
    return path


def _bytes(year,month,kind):
    plan=r3.source_plan(year,month,kind)
    old_manifest=json.loads((OLD_EP/'R3_SOURCE_ADMISSION_RESULTS.json').read_text())
    good=next((s for s in old_manifest['successful_sources'] if (s['year'],s['month'],s['kind'])==(year,month,kind)),None)
    bad=next((s for s in old_manifest['blockers'] if (s['year'],s['month'],s['kind'])==(year,month,kind)),None)
    reference=good or (bad['diagnostic']['archive_authentication'] if bad is not None else None)
    if reference is None:raise ValueError('No signed R3 source identity for requested month')
    cache_zip=guard_file(OLD_PUBLIC/(kind+'-'+plan['zip_name']),OLD_PUBLIC)
    cache_check=guard_file(OLD_PUBLIC/(kind+'-'+plan['zip_name']+'.CHECKSUM'),OLD_PUBLIC)
    transport={};origin='READ_ONLY_APPROVED_R3_PUBLIC_CACHE'
    if cache_zip.exists() and cache_check.exists():
        raw_zip,raw_check=cache_zip.read_bytes(),cache_check.read_bytes()
    else:
        origin='REDOWNLOADED_EXACT_R3_MONTHLY_SOURCE'
        raw=[]
        for label,url in (('zip',plan['zip_url']),('checksum',plan['checksum_url'])):
            path=guard_file(SCRATCH/(kind+'-'+plan['zip_name']+('' if label=='zip' else '.CHECKSUM')),SCRATCH)
            if not path.exists():
                SCRATCH.mkdir(exist_ok=True,mode=0o700)
                with own_fetch_destination():
                    response=r3._fetch(url,path,max_bytes=r3.MAX_ZIP_BYTES if label=='zip' else 4096,allowed_prefix=r3.VISION)
                transport[label]=response
                if response['status']!='FETCHED':raise ValueError('Required monthly source unavailable: '+str(response))
            raw.append(path.read_bytes())
        raw_zip,raw_check=raw
    for name,value in (('zip_sha256',raw_zip),('checksum_sha256',raw_check)):
        if hashlib.sha256(value).hexdigest()!=reference[name]:
            raise ValueError('R3 source bytes changed: '+kind+' '+str(year)+'-'+str(month)+' '+name)
    body,proof=r3._archive_csv(raw_zip,raw_check,plan)
    if proof['csv_sha256']!=reference['csv_sha256']:raise ValueError('R3 member bytes changed')
    return raw_zip,raw_check,body,{**proof,'year':year,'month':month,'kind':kind,'origin':origin,'transport':transport,'source_url':plan['zip_url']}


def parse_sparse_month_mark(body: bytes, year: int, month: int) -> np.ndarray:
    start,end=r3.month_bounds(year,month);rows=[];previous=start-60000
    for line,fields in enumerate(csv.reader(io.StringIO(body.decode('utf-8-sig'))),1):
        if line==1 and fields[0]=='open_time':
            header=('open_time','open','high','low','close','ignore','close_time','ignore','ignore','ignore','ignore','ignore')
            if tuple(fields) not in r3.KLINE_HEADERS and tuple(fields)!=header:raise ValueError('Unknown Mark header')
            continue
        if len(fields)!=12:raise ValueError('Monthly Mark must be12 fields')
        stamp=r3._millis(fields[0],'open_time',line);close=r3._millis(fields[6],'close_time',line)
        if not start<=stamp<end or stamp%60000 or close!=stamp+59999 or stamp<=previous:
            raise ValueError('Monthly Mark present clocks invalid/duplicate/unsorted')
        o,h,lo,c=[r3._decimal(fields[i],'MarkOHLC',line) for i in range(1,5)]
        if not 0<lo<=min(o,c)<=max(o,c)<=h:raise ValueError('Monthly Mark present OHLC invalid')
        rows.append((float(stamp),float(o),float(h),float(lo),float(c)));previous=stamp
    result=np.asarray(rows,dtype=np.float64).reshape((-1,5))
    if not np.all(np.isfinite(result)):raise ValueError('Nonfinite monthly Mark')
    expected=set(range(start,end,60000));present=set(map(int,result[:,0]));missing=expected-present
    frozen={stamp for day in ALLOWED_DAYS if day.startswith(f'{year}-{month:02d}-')
            for stamp in range(day_plan(day)['start_ms'],day_plan(day)['end_ms'],60000)}
    if missing!=frozen:raise ValueError('Monthly Mark gap set differs from exact frozen8days')
    return result


def load_all():
    arrays={'last':{},'mark':{}};funding={};sources=[]
    for y in range(2021,2024):
        for m in range(1,13):
            for kind in ('last','mark','funding'):
                raw,check,body,receipt=_bytes(y,m,kind)
                if kind=='last':
                    data,validation=r3.validate_kline_archive_bytes(raw,check,y,m,kind=kind);arrays[kind][y,m]=data
                elif kind=='mark':
                    data=parse_sparse_month_mark(body,y,m);validation={'rows':len(data),'present_rows_sha256':hashlib.sha256(data.astype('<f8').tobytes()).hexdigest()};arrays[kind][y,m]=data
                else:
                    data,validation=r3.validate_funding_archive_bytes(raw,check,y,m);validation['continuity']=r3.verify_funding_continuity(data,y,m);funding[y,m]=data
                sources.append({**receipt,**validation,'kind':kind,'year':y,'month':m})
        print(f'MONTHLY REUSE {y} complete',flush=True)
    events=[e for key in sorted(funding) for e in funding[key]]
    assert len(events)==3285 and len({e['settlement_at'] for e in events})==3285
    for a,b in pairwise(events):
        assert abs((b['settlement_at']-a['settlement_at'])/3600000-float(b['interval_hours']))<=60/3600
    assert sum(len(v) for v in arrays['last'].values())==1576800
    assert sum(len(v) for v in arrays['mark'].values())==1565280
    return arrays,funding,{'successful_sources':sources,'R3_monthly_signed_bytes_preserved':True,'original_mark_rows':1565280,'original_missing_minutes':11520,'funding_events':3285}
