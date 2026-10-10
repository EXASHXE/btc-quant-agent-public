"""Only the ten frozen official BTC USD-M archive URLs; stdlib ZIP/CSV reader."""
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
from pathlib import Path

import numpy as np

BASE = 'https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/'
ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / 'evidence/v0.6/b_line/g2_btc_empirical_fast_r1'
REGISTRY = EVIDENCE / 'FROZEN_STRATEGY_REGISTRY.json'
FIELDS = ['open_time','open','high','low','close','volume','close_time','quote_volume',
          'count','taker_buy_volume','taker_buy_quote_volume','ignore']


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def ms(text: str) -> int:
    return int(datetime.fromisoformat(text).timestamp()*1000)


def verify_freeze(freeze: str) -> dict:
    if len(freeze) != 40 or any(c not in '0123456789abcdef' for c in freeze):
        raise ValueError('exact40hex freeze required')
    relative = str(REGISTRY.relative_to(ROOT))
    raw = subprocess.check_output(['git','show',f'{freeze}:{relative}'],cwd=ROOT)
    if raw != REGISTRY.read_bytes():
        raise ValueError('frozen roster changed')
    signature_path=EVIDENCE/'OUTCOME_BLIND_FREEZE_SIGNATURE.json'
    signed_raw=subprocess.check_output(['git','show',f'{freeze}:{signature_path.relative_to(ROOT)}'],cwd=ROOT)
    if signed_raw!=signature_path.read_bytes():
        raise ValueError('signed ledger changed')
    ledger=json.loads(signed_raw)
    if ledger['signed_payload']['registry_sha256']!=hashlib.sha256(raw).hexdigest():
        raise ValueError('signed registry digest mismatch')
    registry=json.loads(raw)
    if len(registry['source_plan'])!=10 or len(registry['candidates'])!=12:
        raise ValueError('fixed finite experiment altered')
    return registry


def validate_zip_checksum(raw: bytes, checksum: str, name: str) -> str:
    words=checksum.strip().split()
    actual=hashlib.sha256(raw).hexdigest()
    if len(words)!=2 or words[0].lower()!=actual or words[1].lstrip('*')!=name:
        raise ValueError('official ZIP checksum/name mismatch')
    return actual


def parse_month(raw: bytes, year: int, month: int) -> tuple[np.ndarray, dict]:
    if year not in range(2021,2026) or month not in (3,4):
        raise ValueError('month outside fixed public grant')
    name=f'BTCUSDT-1m-{year}-{month:02}.csv'
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if archive.namelist()!=[name]:
            raise ValueError('unexpected ZIP member set')
        info=archive.getinfo(name)
        if info.file_size>30_000_000:
            raise ValueError('CSV uncompressed budget exceeded')
        body=archive.read(name)
    rows=csv.reader(io.StringIO(body.decode('utf-8-sig')))
    values=[];header=None;close_times=[];zero_volume=0
    for lineno,row in enumerate(rows,1):
        if len(row)!=12:
            raise ValueError(f'CSV field count at line{lineno}')
        if lineno==1 and not row[0].isdigit():
            header=row
            if row[0]!='open_time':
                raise ValueError('unrecognized header')
            continue
        timestamp=int(row[0]); close=int(row[6]);nums=[float(v) for v in row]
        if not all(math.isfinite(v) for v in nums):
            raise ValueError('nonfinite source number')
        o,h,l,c,v=nums[1:6]
        if not (0<l<=min(o,c)<=max(o,c)<=h and v>=0 and close==timestamp+59999):
            raise ValueError(f'invalidOHLC/volume/clock line{lineno}')
        if nums[7]<0 or nums[8]<0 or int(nums[8])!=nums[8] or nums[9]<0 or nums[10]<0:
            raise ValueError('negative/nonintegral volume/trades fields')
        zero_volume+=int(v==0);values.append([timestamp,o,h,l,c,v]);close_times.append(close)
    array=np.asarray(values,dtype=np.float64)
    expected=calendar.monthrange(year,month)[1]*1440
    start=ms(f'{year}-{month:02}-01T00:00:00Z');end=start+expected*60000
    if array.shape!=(expected,6):
        raise ValueError(f'month row count {array.shape}, expected{expected}')
    times=array[:,0].astype(np.int64);diff=np.diff(times)
    duplicate=int(np.sum(diff==0));gaps=int(np.sum(diff>60000));out_of_order=int(np.sum(diff<=0))
    if duplicate or gaps or out_of_order or not np.array_equal(times,np.arange(start,end,60000)):
        raise ValueError('noncomplete,duplicate,gapped or outoforder month')
    return array,{'csv_member':name,'csv_sha256':hashlib.sha256(body).hexdigest(),
                  'csv_bytes':len(body),'physical_lines':len(body.splitlines()),'price_rows':len(values),
                  'header':header,'field_layout':FIELDS,'unit':'milliseconds USD-M verified by UTC calendar',
                  'min_open_utc':datetime.fromtimestamp(start/1000,UTC).isoformat(),
                  'max_open_utc':datetime.fromtimestamp(int(times[-1])/1000,UTC).isoformat(),
                  'max_close_ms':close_times[-1],'end_exclusive_ms':end,'duplicates':duplicate,
                  'gaps':gaps,'out_of_order':out_of_order,'zero_volume_minutes':zero_volume,
                  'publisher_corrections':'snapshot observed now, not historical as-of publication evidence'}


def fetch(url: str, target: Path) -> dict:
    if not url.startswith(BASE):
        raise ValueError('unexpected network source')
    headers=target.with_suffix(target.suffix+'.headers')
    completed=subprocess.run(['curl','--silent','--show-error','--location','--max-redirs','2',
        '--proto','=https','--connect-timeout','20','--max-time','120','--retry','2',
        '--dump-header',str(headers),'--output',str(target),
        '--write-out','%{http_code}\n%{url_effective}\n%{http_version}',url],capture_output=True,text=True,check=False)
    lines=completed.stdout.splitlines();status=int(lines[0]) if lines and lines[0].isdigit() else 0
    returned=lines[1] if len(lines)>1 else ''
    result={'requested_url':url,'returned_url':returned,'http_status':status,
            'http_version':lines[2] if len(lines)>2 else None,'curl_exit':completed.returncode,
            'download_utc':utcnow(),'response_headers':headers.read_text(errors='replace') if headers.exists() else '',
            'error':completed.stderr[:1000] if completed.returncode else None}
    if returned and not returned.startswith(BASE):
        raise ValueError('redirect outside authorized official archive prefix')
    return result


def download(scratch: Path, freeze: str) -> dict:
    registry=verify_freeze(freeze)
    if not str(scratch.resolve()).startswith('/tmp/g2-btc-public-empirical-fast-r1'):
        raise ValueError('only task-owned external scratch supported')
    scratch.mkdir(mode=0o700,exist_ok=True)
    manifest={'schema':'PUBLIC_BTC_SOURCE_MANIFEST_V1','freeze_sha':freeze,'started_at_utc':utcnow(),
              'first_price_csv_read_at_utc':None,'records':[],'rights':registry['rights'],
              'price_grade':'EXPLORATORY_COST_PROXY_ONLY','mark_source':'NOT_ACQUIRED_UNKNOWN',
              'funding_source':'NOT_ACQUIRED_UNKNOWN','owner_or_protected_body_reads':0}
    for plan in registry['source_plan']:
        y,m=plan['year'],plan['month'];expected=f'{BASE}BTCUSDT-1m-{y}-{m:02}.zip'
        if plan['url']!=expected or plan['checksum_url']!=expected+'.CHECKSUM' or y not in range(2021,2026) or m not in (3,4):
            raise ValueError('source plan drift')
        file=scratch/f'BTCUSDT-1m-{y}-{m:02}.zip';check=Path(str(file)+'.CHECKSUM')
        record={'year':y,'month':m,'zip':fetch(plan['url'],file),'checksum':fetch(plan['checksum_url'],check)}
        if record['zip']['http_status']!=200 or record['checksum']['http_status']!=200 or record['zip']['curl_exit'] or record['checksum']['curl_exit']:
            record['status']='HTTP_SOURCE_MISSING';manifest['records'].append(record)
        else:
            try:
                raw=file.read_bytes();record['zip_sha256']=validate_zip_checksum(raw,check.read_text(),file.name)
                record['checksum_sha256']=hashlib.sha256(check.read_bytes()).hexdigest()
                if manifest['first_price_csv_read_at_utc'] is None:
                    manifest['first_price_csv_read_at_utc']=utcnow()
                array,meta=parse_month(raw,y,m);record.update(meta);record['status']='VERIFIED_COMPLETE_PUBLIC_MONTH'
                np.save(scratch/f'validated-{y}-{m:02}.npy',array,allow_pickle=False)
            except (ValueError,zipfile.BadZipFile,UnicodeError) as exc:
                record['status']='SOURCE_INTEGRITY_FAIL';record['error']=str(exc)
            manifest['records'].append(record)
        (EVIDENCE/'SOURCE_TIME_VERSION_MANIFEST.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
        print(json.dumps({'year':y,'month':m,'status':record['status'],'rows':record.get('price_rows'),
                          'http':record['zip']['http_status']}),flush=True)
    manifest['finished_at_utc']=utcnow()
    failures=[r for r in manifest['records'] if r['status']!='VERIFIED_COMPLETE_PUBLIC_MONTH']
    full=[y for y in range(2021,2026) if all(any(r['year']==y and r['month']==m and r['status']=='VERIFIED_COMPLETE_PUBLIC_MONTH' for r in manifest['records']) for m in (3,4))]
    manifest['complete_era_years']=full
    manifest['gate']='PASS_PUBLIC_TRADE_PRICE_ONLY' if len(failures)<=2 and len(full)>=3 and not any(r['status']=='SOURCE_INTEGRITY_FAIL' for r in failures) else 'BLOCKED_PUBLIC_DATA_COVERAGE_OR_INTEGRITY'
    (EVIDENCE/'SOURCE_TIME_VERSION_MANIFEST.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    return manifest


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scratch',type=Path,required=True);parser.add_argument('--freeze',required=True)
    args=parser.parse_args();result=download(args.scratch,args.freeze)
    if result['gate'].startswith('BLOCKED'):
        raise SystemExit(2)


if __name__=='__main__':
    main()
