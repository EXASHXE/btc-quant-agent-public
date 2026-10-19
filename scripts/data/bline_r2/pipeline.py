"""Isolated archive CLI: init, acquire, report. No historical return evaluation."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sqlite3
import subprocess
import time
import zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from tools.data.binance_usdm import ORIGIN
from tools.data.common import generate_date_range, generate_month_range
from tools.data.okx_swap import get_okx_tasks

from . import LABELS, TASK
from .inventory import inspect_existing, monthly_inventory
from .quality import scan_archive
from .transport import (
    CAP_BYTES,
    EXPANSION_RESERVE,
    FREE_FLOOR,
    SourceBlocked,
    Transport,
    digest,
    immutable_json,
    json_bytes,
    now,
)

DATA_ROOT = Path("/root/workspace/project/crypto-data")
DEFAULT_ROOT = DATA_ROOT/"bline-r2-20261019"
RIGHTS_COMMIT = "d571690eb66760763b0bd6e27e8cd35603c7e244"
RIGHTS_SNAPSHOT_CONTENT_PINS = {
    'TERMS_AND_CONDITIONS.md':'f7e5a44d91807ecaaaf85e99733475c63aa6ab7cd62d9dc8c8cd6c9927006ef2',
    'README.md':'f0cb8aa80d272ff26174397de3cec4c1a5844c551db7c9c77e8b62a039fdf10f',
}


def checked_root(path: Path) -> Path:
    path = path.absolute()
    if path.parent != DATA_ROOT or not path.name.startswith("bline-r2-"):
        raise ValueError("NEW_ISOLATED_BLINE_R2_ROOT_ONLY")
    if ".." in path.parts or any(p.is_symlink() for p in [path,*path.parents]):
        raise ValueError("SYMLINK_OR_TRAVERSAL_REFUSED")
    return path


def database(root):
    conn = sqlite3.connect(root/"catalog.sqlite")
    conn.execute("""CREATE TABLE IF NOT EXISTS archives(url TEXT PRIMARY KEY, venue TEXT,
        asset TEXT, product TEXT, family TEXT, symbol TEXT, period TEXT, interval TEXT,
        status TEXT, path TEXT, sha256 TEXT, bytes INTEGER, record_json TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS archive_versions(url TEXT,sha256 TEXT,
        record_json TEXT,PRIMARY KEY(url,sha256))""")
    return conn


def initialize(root: Path, *, evidence_dir: Path | None = None,
               preservation_snapshot: Path | None = None):
    evidence_dir = evidence_dir or DEFAULT_ROOT/'evidence'
    for name in ('TERMS_AND_CONDITIONS.md','README.md'):
        source = evidence_dir/('binance_'+name)
        if not source.is_file():
            raise ValueError('AUDITED_SOURCE_EVIDENCE_DIRECTORY_REQUIRED')
        if hashlib.sha256(source.read_bytes().rstrip(b'\n')).hexdigest() != RIGHTS_SNAPSHOT_CONTENT_PINS[name]:
            raise ValueError('REVIEWED_OFFICIAL_SOURCE_SNAPSHOT_MISMATCH')
    root.mkdir()
    for name in ("objects","evidence","normalized_metrics","runs"):
        (root/name).mkdir()
    if preservation_snapshot is not None:
        shutil.copyfile(preservation_snapshot,root/'preservation_before.json')
    else:
        repo = Path(__file__).resolve().parents[3]
        status = subprocess.check_output(['git','-C',str(repo),'status','--porcelain=v1','-uall'],text=True)
        paths = [repo/line[3:] for line in status.splitlines()]
        r1 = DATA_ROOT/'lakehouse/research-bline-r1'
        immutable_json(root/'preservation_before.json',{
            'owner_files':{str(p.relative_to(repo)):digest(p) for p in paths if p.is_file()},
            'r1_files':{str(p):digest(p) for p in r1.rglob('*') if p.is_file()}})
    for name in ("TERMS_AND_CONDITIONS.md","README.md"):
        source = evidence_dir/('binance_'+name)
        shutil.copyfile(source,root/'evidence'/('binance_'+name))
    terms_sha = digest(root/'evidence/binance_TERMS_AND_CONDITIONS.md')
    rights = {
        "checked_at_utc":now(),"purpose":"Personal noncommercial, non-production historical research only",
        "binance": {"state":"PERSONAL_ARCHIVE_RESEARCH_ALLOWED", "families":["metrics","klines",
            "spot_klines","markPriceKlines","indexPriceKlines","premiumIndexKlines","fundingRate"],
            "url":f"https://github.com/binance/binance-public-data/blob/{RIGHTS_COMMIT}/TERMS_AND_CONDITIONS.md",
            "terms_commit":RIGHTS_COMMIT,"terms_sha256":terms_sha,
            "basis":"Vision Dataset Terms 3.1,4.1 allow personal non-production research; no commercial/live use or redistribution",
            "download_origin":"https://data.binance.vision","product":"USD-M BTCUSDT/ETHUSDT perpetual; Spot kept separate",
            "posted_static_rate_limit":"No numeric archive-specific limit found; local 4 inflight / 8 request starts per second, Retry-After enforced"},
        "okx": {"state":"PERSONAL_ARCHIVE_RESEARCH_ALLOWED","families":["funding_rates","trades","orderbook"],
            "url":"https://www.okx.com/help/historicaldata-terms-and-conditions",
            "basis":"2023-10-26 historical data terms 2 explicitly include personal strategy development; no redistribution",
            "evidence_kind":"OFFICIAL_WEB_REVIEW; no claim of raw HTML hash",
            "download_origin":"https://static.okx.com/cdn","product":"BTC-USDT-SWAP/ETH-USDT-SWAP; never Binance OI",
            "calendar":"UTC+8 nominal archive days; preserve native UTC epoch, never shift epochs"},
        "bybit": {"state":"RIGHTS_UNRESOLVED_FOR_BULK_OI_ARCHIVE_RETENTION","families":["open_interest"],
            "url":"https://www.bybit.com/common-static/compliance/legal/BYBIT/df1923006718fbba8ba70d7d762b9866.pdf",
            "basis":"API agreement 5.1 licenses API use but excludes IP in returned content; public historical CSV guide lists orderbook/kline/trades/funding, not OI. No clear OI bulk archive retention grant located.",
            "historical_csv_guide":"https://www.bybit.com/en/learn/bybit-guide/how-to-create-a-bybit-api-key",
            "native_oi_docs":"https://bybit-exchange.github.io/docs/v5/market/open-interest",
            "product":"linear BTCUSDT, USDT quote/settlement; OI unit BTC. Inverse BTCUSD excluded.",
            "vintage":"2026-06-11 single-sided display change; V5 openInterest both-sides and singleOpenInterest separate. No divide-by-two inference.",
            "network_probe":"api.bybit.com and public.bybit.com direct access: Network is unreachable; no alternative region/host bypass attempted",
            "archive_payload_downloaded_bytes":0}}
    immutable_json(root/'rights_assessment.json',rights)
    print('Inventory: rehashing small public archives, preserving large archives as metadata only',flush=True)
    sources = inspect_existing(DATA_ROOT/'lakehouse/catalog.sqlite')
    immutable_json(root/'existing_inventory.json',sources)
    immutable_json(root/'existing_monthly_coverage.json',monthly_inventory(sources))
    immutable_json(root/'ROOT_RECEIPT.json',{"task":TASK,"created_at_utc":now(),"labels":LABELS,
        "data_root":str(root),"initial_disk":shutil.disk_usage(root)._asdict(),
        "additional_storage_cap_bytes":CAP_BYTES,"minimum_free_bytes":FREE_FLOOR,
        "temporary_expansion_reserve_bytes":EXPANSION_RESERVE,"extraction":"STREAMED_NO_DISK_EXTRACTION",
        "existing_catalog_path":str(DATA_ROOT/'lakehouse/catalog.sqlite'),
        "existing_catalog_sha256":digest(DATA_ROOT/'lakehouse/catalog.sqlite'),
        "rights_assessment_sha256":digest(root/'rights_assessment.json'),"existing_sources":len(sources)})
    database(root).close()
    return {"task":TASK,"status":"INITIALIZED","existing_sources":len(sources),"root":str(root)}


def binance_task(family, symbol, period):
    metrics = family == "metrics"
    spot = family == "spot_klines"
    native_family = "klines" if spot else family
    cadence = "daily" if metrics else "monthly"
    folder = "spot" if spot else "futures/um"
    interval_path = "" if metrics or family == "fundingRate" else "/1m"
    filename = (f"{symbol}-metrics-{period}.zip" if metrics else
                f"{symbol}-fundingRate-{period}.zip" if family == "fundingRate" else
                f"{symbol}-1m-{period}.zip")
    return {"venue":"binance","asset":symbol.removesuffix('USDT'),"product":"SPOT" if spot else "USD_M_PERPETUAL",
            "family":family,"symbol":symbol,"period":period,"interval":"5m" if metrics else "EVENT" if family=="fundingRate" else "1m",
            "url":f"{ORIGIN}/data/{folder}/{cadence}/{native_family}/{symbol}{interval_path}/{filename}",
            "filename":filename,"publisher_checksum_required":True}


def tasks(tier, start, end):
    if not start < end <= datetime.now(UTC).date().isoformat():
        raise ValueError("HISTORICAL_BOUNDS_REQUIRED")
    result = []
    days = generate_date_range(start,end,end_inclusive=False)
    months = [m for m in generate_month_range(start,end) if m < datetime.now(UTC).strftime('%Y-%m')]
    symbols = ("BTCUSDT","ETHUSDT")
    if tier in ("pilot","oi","core"):
        pilot_days = {f'{y}-01-01' for y in range(2021,2027)} | {"2021-12-01","2026-06-24","2026-06-25","2026-06-26","2026-08-31"}
        chosen = [d for d in days if tier != "pilot" or d in pilot_days]
        for symbol in symbols:
            result.extend(binance_task("metrics",symbol,d) for d in chosen)
    if tier in ("pilot","monthly","core"):
        chosen = [m for m in months if tier != "pilot" or m in {"2021-01","2026-02","2026-09"}]
        for symbol in symbols:
            for family in ("fundingRate","indexPriceKlines","premiumIndexKlines","markPriceKlines","klines","spot_klines"):
                result.extend(binance_task(family,symbol,m) for m in chosen)
    if tier == "okx":
        # Funding is small and high information. Trade/L2 samples stay separate
        # features and the per-object cap prevents bulk multi-GB L2 downloads.
        native = get_okx_tasks(start_date=max(start,"2022-03-01"),end_date=end,
                               sample_days=["2023-03-01"])
        for t in native:
            if t['family'] not in ('funding_rates','trades','orderbook'):
                continue
            result.append({**t,"product":"OKX_SWAP","asset":"MULTI" if t['family']=='funding_rates' else t['symbol'].split('-')[0],
                "filename":t['url'].split('?')[0].rsplit('/',1)[1],"publisher_checksum_required":False})
    return result


def acquire(root, tier, start, end, *, direct=False, workers=4):
    if not 1 <= workers <= 4:
        raise ValueError("BOUNDED_CONCURRENCY_1_TO_4")
    policy = json.loads((root/'rights_assessment.json').read_text())
    receipt = json.loads((root/'ROOT_RECEIPT.json').read_text())
    if digest(root/'rights_assessment.json') != receipt['rights_assessment_sha256']:
        raise ValueError("RIGHTS_ASSESSMENT_CHANGED")
    existing = json.loads((root/'existing_inventory.json').read_text())
    conn = database(root)
    already = {url:json.loads(record) for url,record in conn.execute('SELECT url,record_json FROM archives')}
    names = {}
    for r in existing:
        if r.get('actual_sha256'):
            names.setdefault(r['filename'],[]).append(r)
    transport = Transport(root,direct=direct)
    planned = tasks(tier,start,end)
    started = time.monotonic()
    def one(task):
        record = {**task,'checked_at_utc':now(),'receiver_pit':'PIT_UNKNOWN','real_outcome_labels_read':0}
        family = task['venue']+'/'+task['family']
        authorization = policy.get(task['venue'],{})
        if (authorization.get('state') != 'PERSONAL_ARCHIVE_RESEARCH_ALLOWED'
                or task['family'] not in authorization.get('families',[])):
            return {**record,'status':'RIGHTS_BLOCKED','bytes':None}
        prior = already.get(task['url'])
        if (prior and prior.get('status') in ('DOWNLOADED_VERIFIED','REUSED_VERIFIED','DOWNLOADED_LOCAL_SHA_ONLY')
                and Path(prior['path']).is_file() and digest(Path(prior['path'])) == prior['sha256']):
            return prior
        try:
            expected = None
            if task['publisher_checksum_required']:
                raw,headers = transport.metadata(task['url']+'.CHECKSUM',family)
                if raw is None:
                    return {**record,'status':'PUBLISHER_CHECKSUM_UNAVAILABLE','bytes':None,'http_status':404}
                import re
                match = re.fullmatch(rb'([a-fA-F0-9]{64})\s+\*?([^\r\n]+)\s*',raw.strip())
                if not match or match[2].decode().strip() != task['filename']:
                    raise ValueError('PUBLISHER_CHECKSUM_IDENTITY_INVALID')
                expected = match[1].decode().lower()
                sidecar = root/'evidence/checksums'/expected/(task['filename']+'.CHECKSUM')
                sidecar.parent.mkdir(parents=True,exist_ok=True)
                if not sidecar.exists():
                    with sidecar.open('xb') as f:
                        f.write(raw)
                record.update(publisher_sha256=expected,publisher_checksum_path=str(sidecar),
                    checksum_response_headers=headers)
            equivalent = [r for r in names.get(task['filename'],[]) if r['actual_sha256']==expected
                          and r['exchange']==task['venue'] and r['product']==task['product']]
            # Different native families use identical kline filenames. A SHA
            # equality is required in addition to filename/product identity.
            if equivalent:
                source = min(equivalent,key=lambda r:r['path'])
                path = Path(source['path'])
                if digest(path) != expected:
                    raise ValueError('EXISTING_ARCHIVE_MUTATED')
                metadata = {'sha256':expected,'bytes':path.stat().st_size,'reused':True}
            else:
                path = root/'objects'/family/task['symbol']/(expected or hashlib.sha256(task['url'].encode()).hexdigest())/task['filename']
                metadata = transport.archive(task['url'],family,path,expected)
                if metadata is None:
                    return {**record,'status':'ARCHIVE_UNAVAILABLE','bytes':None,'http_status':404}
            normalized = root/'normalized_metrics'/task['symbol']/(metadata['sha256']+'.parquet') if task['family']=='metrics' else None
            if task['filename'].endswith('.zip'):
                qc = scan_archive(path,task,metadata['sha256'],normalized)
            else:
                qc = {'status':'ARCHIVE_STORED_NOT_EXPANDED','receiver_pit':'PIT_UNKNOWN'}
            record.update(metadata,path=str(path),status='REUSED_VERIFIED' if metadata['reused'] else
                'DOWNLOADED_VERIFIED' if expected else 'DOWNLOADED_LOCAL_SHA_ONLY',qc=qc,
                normalized_metrics_path=str(normalized) if normalized else None,
                existing_other_vintages=[{'path':r['path'],'sha256':r['actual_sha256']}
                    for r in names.get(task['filename'],[]) if r['actual_sha256']!=expected and
                    r['exchange']==task['venue'] and r['product']==task['product'] and r['family'].startswith(task['family'])])
            return record
        except SourceBlocked as exc:
            return {**record,'status':'SOURCE_BLOCKED','blocker':str(exc),'bytes':None}
        except (OSError,ValueError,RuntimeError,csv.Error,zipfile.BadZipFile) as exc:
            return {**record,'status':'FAILED_PENDING_RESUME','blocker':type(exc).__name__+':'+str(exc)[:300],'bytes':None}
    counts = Counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i,record in enumerate(pool.map(one,planned),1):
            counts[record['status']] += 1
            values = [record.get(k) for k in ['url','venue','asset','product','family','symbol','period','interval','status','path','sha256','bytes']]
            conn.execute('INSERT OR REPLACE INTO archives VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',values+[json_bytes(record).decode()])
            if record.get('sha256'):
                conn.execute('INSERT OR IGNORE INTO archive_versions VALUES (?,?,?)',
                             (record['url'],record['sha256'],json_bytes(record).decode()))
            conn.commit()
            if i % 100 == 0 or i == len(planned):
                print(json.dumps({'completed':i,'planned':len(planned),'status_counts':dict(counts),
                    'download_network_bytes':transport.network_bytes,'elapsed_s':round(time.monotonic()-started,1)}),flush=True)
    conn.close()
    result = {'task':TASK,'tier':tier,'start':start,'end':end,'status_counts':dict(counts),
        'planned':len(planned),'requests':transport.requests,'network_bytes':transport.network_bytes,
        'elapsed_s':round(time.monotonic()-started,3),'family_blocks':transport.blocked,
        'disk':shutil.disk_usage(root)._asdict(),'real_outcome_labels_read':0,'labels':LABELS}
    immutable_json(root/'runs'/(datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')+'_'+tier+'.json'),result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['init','acquire','report'])
    parser.add_argument('--root',type=Path,default=DEFAULT_ROOT)
    parser.add_argument('--tier',choices=['pilot','oi','monthly','core','okx'],default='pilot')
    parser.add_argument('--start',default='2021-01-01')
    parser.add_argument('--end',default='2026-10-19')
    parser.add_argument('--direct',action='store_true',help='Ordinary direct HTTPS; never an alternate proxy or provider-block bypass')
    parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--evidence-dir',type=Path,help='Previously reviewed official Binance terms/README snapshots; recheck rights before reuse')
    parser.add_argument('--preservation-snapshot',type=Path,help='Optional pre-execution snapshot; otherwise captured now')
    args = parser.parse_args(argv)
    root = checked_root(args.root)
    if args.action == 'init':
        result = initialize(root,evidence_dir=args.evidence_dir,preservation_snapshot=args.preservation_snapshot)
    elif args.action == 'acquire':
        result = acquire(root,args.tier,args.start,args.end,direct=args.direct,workers=args.workers)
    else:
        from .report import report
        result = report(root)
    print(json.dumps(result,ensure_ascii=False,sort_keys=True),flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
