"""Coverage, vintage and immutable-input receipts. No strategy outcomes."""
from __future__ import annotations

import bisect
import csv
import json
import math
import shutil
import sqlite3
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq

from . import LABELS, TASK
from .quality import epoch_us
from .transport import digest, immutable_json, json_bytes, now

US = 1_000_000
DAY = 86400*US
H40_LEFT = int(datetime(2025,2,1,tzinfo=UTC).timestamp())*US
H40_RIGHT = int(datetime(2026,2,1,tzinfo=UTC).timestamp())*US
H39 = int(datetime(2026,9,1,tzinfo=UTC).timestamp())*US
FIELDS = ['base_open_interest','open_interest_notional','top_account_long_short_ratio',
          'top_position_long_short_ratio','global_account_long_short_ratio','taker_long_short_volume_ratio']


def positive(value):
    return value is not None and math.isfinite(value) and value > 0


def state_at_origin(states: dict, times: list[int], conflicts: set[int], origin: int,
                    *, content_delay_us=300*US, joint=True) -> bool:
    """HH01 fixed origins; stock content has a conservative five-minute upper guard."""
    if origin % (3600*US) != 60*US:
        raise ValueError('FIXED_HH01_ORIGIN_REQUIRED')
    cutoff = origin-60*US
    idx = bisect.bisect_right(times,cutoff-300*US-content_delay_us)-1
    if idx < 0:
        return False
    t = times[idx]
    pred = t-4*3600*US
    # For an uncertain content clock [label,label+delay], BOTH ends must
    # satisfy the frozen 5–10m age window. Delay=5m therefore requires C-10m
    # exactly, rather than rescuing a potentially 15-minute-old observation.
    if (not cutoff-600*US <= t <= cutoff-300*US-content_delay_us
            or t % (300*US) or t in conflicts or pred in conflicts or pred not in states
            or not positive(states[t][0]) or not positive(states[pred][0])):
        return False
    return not joint or positive(states[t][3])


def protected_feature_window(origin):
    cutoff = origin-60*US
    left = cutoff-86400*US-120*US
    return max(left,H40_LEFT) < min(cutoff,H40_RIGHT) or cutoff >= H39


def metric_states(records):
    states = defaultdict(dict)
    conflicts = defaultdict(set)
    file_stats = []
    for record in records:
        if record.get('family') != 'metrics' or not record.get('normalized_metrics_path'):
            continue
        if record['status'] not in ('DOWNLOADED_VERIFIED','REUSED_VERIFIED'):
            continue
        key = (record['venue'],record['symbol'],record['product'])
        table = pq.ParquetFile(record['normalized_metrics_path']).read(columns=['native_label_us',*FIELDS]).to_pydict()
        for values in zip(table['native_label_us'],*(table[f] for f in FIELDS)):
            t, v = values[0], tuple(values[1:])
            if t in states[key] and states[key][t] != v:
                conflicts[key].add(t)
            else:
                states[key][t] = v
        qc = record['qc']
        distinct = len(set(table['native_label_us']))
        pattern = ('START_LABEL_PATTERN' if distinct==288 and qc['first_offset_seconds']==0 and qc['last_offset_seconds']==86100 else
                   'END_LABEL_PATTERN' if distinct==288 and qc['first_offset_seconds']==300 and qc['last_offset_seconds']==86400 else 'PARTIAL_OR_AMBIGUOUS_PATTERN')
        file_stats.append({'venue':key[0],'symbol':key[1],'period':record['period'],
            'sha256':record['sha256'],'status':record['status'],'archive_path':record['path'],
            'rows':qc['rows'],'unique_labels':distinct,'duplicate_labels':qc['duplicate_native_labels'],
            'first_offset_seconds':qc['first_offset_seconds'],'last_offset_seconds':qc['last_offset_seconds'],
            'observed_unique_label_pattern':pattern,'downloaded_at_utc':record.get('downloaded_at_utc'),
            'last_modified_http':record.get('last_modified'),'etag':record.get('etag'),
            'existing_other_vintages':record.get('existing_other_vintages',[])})
    return states,conflicts,file_stats


def native_coverage(states,conflicts):
    groups = defaultdict(Counter)
    for (venue,symbol,product),mapping in states.items():
        hours = defaultdict(Counter)
        for t,values in mapping.items():
            key = (venue,symbol,product,datetime.fromtimestamp(t//US,UTC).strftime('%Y-%m'))
            g = groups[key]
            g['native_unique_labels'] += 1
            if t in conflicts[(venue,symbol,product)]:
                g['conflicting_native_labels'] += 1
                continue
            if t % (300*US):
                g['off_grid_labels'] += 1
                continue
            if positive(values[0]):
                g['valid_native_oi_samples'] += 1
                hours[key][t//(3600*US)] += 1
                if positive(values[3]):
                    g['valid_oi_and_position_samples'] += 1
            elif positive(values[3]):
                g['position_without_oi_samples'] += 1
        for key,counts in hours.items():
            groups[key]['observed_oi_clock_hours'] = len(counts)
            groups[key]['complete_12_sample_hours'] = sum(c==12 for c in counts.values())
    monthly = []
    for (venue,symbol,product,month),c in sorted(groups.items()):
        monthly.append({'venue':venue,'contract':symbol,'product':product,'month':month,
                        'oi_unit':'native_underlying_quantity_not_notional','granularity':'5m',
                        **dict(c),'nominal_5m_equivalent_hours':c['valid_native_oi_samples']/12,
                        'receiver_verified_hours':0,'PIT':'UNKNOWN'})
    annual = defaultdict(Counter)
    for m in monthly:
        key = (m['venue'],m['contract'],m['product'],m['month'][:4])
        annual[key].update({k:m.get(k,0) for k in ['native_unique_labels','valid_native_oi_samples',
            'valid_oi_and_position_samples','observed_oi_clock_hours','complete_12_sample_hours','conflicting_native_labels']})
    yearly = [{'venue':k[0],'contract':k[1],'product':k[2],'year':k[3],**dict(c),
               'nominal_5m_equivalent_hours':c['valid_native_oi_samples']/12,
               'receiver_verified_hours':0} for k,c in sorted(annual.items())]
    for venue,product,contracts,blocker in [
        ('bybit','LINEAR_USDT_PERPETUAL',['BTCUSDT','ETHUSDT'],'RIGHTS_UNRESOLVED_FOR_BULK_OI_ARCHIVE_RETENTION; network unreachable'),
        ('okx','USDT_SWAP',['BTC-USDT-SWAP','ETH-USDT-SWAP'],'No native OI archive source admitted in this task; funding/trades/L2 remain separate')]:
        for contract in contracts:
            for year in range(2021,2027):
                yearly.append({'venue':venue,'contract':contract,'product':product,'year':str(year),
                    'valid_native_oi_samples':0,'nominal_5m_equivalent_hours':0,'observed_oi_clock_hours':0,
                    'complete_12_sample_hours':0,'receiver_verified_hours':0,'blocker':blocker})
    return monthly,yearly


def compare_r1(root,states,conflicts):
    r1 = root.parent/'lakehouse/research-bline-r1'
    baseline = json.loads((r1/'completion-final/COMPLETION_RECEIPT.json').read_text())
    mapping = states.get(('binance','BTCUSDT','USD_M_PERPETUAL'),{})
    excluded = conflicts.get(('binance','BTCUSDT','USD_M_PERPETUAL'),set())
    times = sorted(mapping)
    counts = Counter()
    years = defaultdict(Counter)
    paired_origins = []
    with (r1/'features-release/feature_panel.jsonl').open() as stream:
        for line in stream:
            row = json.loads(line)
            if row.get('asset') != 'BTC' or row.get('venue') != 'binance':
                continue
            t = row['t']*US
            counts['r1_existing_feature_origins'] += 1
            if not row['x_complete'] or protected_feature_window(t):
                continue
            c = years[datetime.fromtimestamp(row['t'],UTC).strftime('%Y')]
            c['X_available'] += 1
            label_based = state_at_origin(mapping,times,excluded,t,content_delay_us=0)
            conservative = state_at_origin(mapping,times,excluded,t)
            oi_only = state_at_origin(mapping,times,excluded,t,joint=False)
            c.update(joint_label_based=label_based,joint_conservative=conservative,
                     oi_only_conservative=oi_only,r1_joint=row['z_status']=='OBSERVED')
            prior = row['z_status']=='OBSERVED'
            c.update(gained_joint_origins=conservative and not prior,
                     lost_prior_joint_origins=prior and not conservative,
                     common_joint_origins=prior and conservative)
            if conservative:
                paired_origins.append({'origin_utc_us':t,'X_available_from_frozen_R1':True,
                    'Z_native_venue':'binance','Z_native_contract':'BTCUSDT',
                    'Z_content_upper_guard':'native_label+5m','receiver_pit':'PIT_UNKNOWN',
                    'incremental_vs_R1':not prior,
                    'outcome_evaluation_authorized':False})
    for c in years.values():
        counts.update(c)
    return {'R1_frozen_counts':baseline['BTC_binance'],'R2_matched_existing_X':dict(counts),
        'incremental_joint_conservative_vs_r1':counts['joint_conservative']-counts['r1_joint'],
        'by_year':{k:dict(v) for k,v in years.items()},'scope':'DESCRIPTIVE_EVENT_TIME_FEATURE_ELIGIBILITY_ONLY',
        'R1_unchanged':True,'receiver_verified_origins':0,'authorized_real_outcome_origins':0,
        'no_new_strategy_parameters':True,'paired_origins':paired_origins}


def report(root):
    began = time.monotonic()
    conn = sqlite3.connect((root/'catalog.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
    records = [json.loads(r[0]) for r in conn.execute('SELECT record_json FROM archives ORDER BY venue,family,symbol,period')]
    conn.close()
    existing = json.loads((root/'existing_inventory.json').read_text())
    rights = json.loads((root/'rights_assessment.json').read_text()) if (root/'rights_assessment.json').exists() else {}
    access = json.loads((root/'source_access_checks.json').read_text()) if (root/'source_access_checks.json').exists() else []
    status = Counter(r['status'] for r in records)
    good = [r for r in records if r['status'] in ('DOWNLOADED_VERIFIED','REUSED_VERIFIED','DOWNLOADED_LOCAL_SHA_ONLY')]
    # Final integrity gate rehashes all selected objects, including reused ones.
    for r in good:
        if digest(Path(r['path'])) != r['sha256']:
            raise ValueError('FINAL_ARCHIVE_SHA_CHANGED:'+r['path'])
    normalized_paths = sorted({r['normalized_metrics_path'] for r in good if r.get('normalized_metrics_path')})
    normalized_manifest = [{'path':p,'bytes':Path(p).stat().st_size,'sha256':digest(Path(p))}
                           for p in normalized_paths]
    states,conflicts,vintages = metric_states(good)
    monthly,yearly = native_coverage(states,conflicts)
    comparison = compare_r1(root,states,conflicts)
    snapshot = json.loads((root/'preservation_before.json').read_text())
    repo = Path(__file__).resolve().parents[3]
    changed = [p for p,h in snapshot['owner_files'].items() if not (repo/p).is_file() or digest(repo/p)!=h]
    changed += [p for p,h in snapshot['r1_files'].items() if not Path(p).is_file() or digest(Path(p))!=h]
    original_changed = []
    for r in existing:
        if r.get('signature'):
            p = Path(r['path']);s=p.stat()
            if [s.st_size,s.st_mtime_ns,s.st_ino] != r['signature']:
                original_changed.append(str(p))
    if changed or original_changed:
        raise ValueError('ORIGINAL_INPUT_MUTATED')
    if digest(root.parent/'lakehouse/catalog.sqlite') != json.loads((root/'ROOT_RECEIPT.json').read_text())['existing_catalog_sha256']:
        raise ValueError('ORIGINAL_C0_CATALOG_CHANGED')
    out = root/'reports'/datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')
    out.mkdir(parents=True)
    by_sha = defaultdict(list)
    for r in good:
        by_sha[r['sha256']].append(r)
    sha_manifest = [{'sha256':h,'bytes':items[0]['bytes'],'canonical_path':min(r['path'] for r in items),
                     'source_urls':sorted(r['url'] for r in items),
                     'publisher_verified':all(r.get('publisher_sha256')==h for r in items),
                     'aliases':sorted({r['path'] for r in items})} for h,items in sorted(by_sha.items())]
    object_index = {r['path'] for r in good}
    orphan_files = [p for p in (root/'objects').rglob('*') if p.is_file() and str(p) not in object_index]
    group = defaultdict(Counter)
    for r in records:
        k = (r['venue'],r['asset'],r['product'],r['family'],r['interval'],r['period'][:7])
        group[k].update({r['status']:1,'known_archive_bytes':r.get('bytes') or 0})
    coverage = [dict(zip(['venue','asset','product','family','granularity','month'],k)) | dict(c)
                for k,c in sorted(group.items())]
    combined = defaultdict(lambda:{'existing_files':0,'R2_selected_files':0,'SHA256_objects':set(),
        'metadata_only_files':0,'publisher_verified_files':0})
    for r in existing:
        period = r.get('period') or 'UNKNOWN'
        key = (r['exchange'],r['asset'],r['product'],r['family'],r['interval'],period[:7])
        cell = combined[key]
        cell['existing_files'] += 1
        if r.get('actual_sha256'):
            cell['SHA256_objects'].add(r['actual_sha256'])
        else:
            cell['metadata_only_files'] += 1
        cell['publisher_verified_files'] += r.get('verification')=='PUBLISHER_SHA256_VERIFIED'
    for r in good:
        key = (r['venue'],r['asset'],r['product'],r['family'],r['interval'],r['period'][:7])
        cell = combined[key]
        cell['R2_selected_files'] += 1
        cell['SHA256_objects'].add(r['sha256'])
        cell['publisher_verified_files'] += r.get('publisher_sha256')==r['sha256']
    combined_rows = []
    for key,cell in sorted(combined.items()):
        combined_rows.append(dict(zip(['venue','asset','product','family','granularity','month'],key)) |
            {**cell,'SHA256_objects':len(cell['SHA256_objects']),
             'coverage_semantics':'Archive/representation availability; OI sample-hours separately physically measured'})
    clock = {'contract_version':'BLINE_R2_NATIVE_ARCHIVE_CLOCK_V1','origin':'UTC HH:01; cutoff HH:00',
        'metrics':{'native':'Preserve create_time verbatim; expected UTC 5m grid; no epoch shift',
            'conservative_content_upper':'native content bounds [label,label+5m]; label>=C-10m AND upper<=C-5m; exact native 4h predecessor',
            'reported_change':'https://github.com/binance/binance-public-data/issues/491',
            'change_status':'Community report, no maintainer confirmation assumed. Recompute actual per-file label patterns and preserve HTTP vintage.',
            'duplicates':'Exact same contents may be deduplicated; different contents at same label are excluded from asof eligibility',
            'missing':'OI and top-position availability separate; never impute missing ratios or notional-derived OI'},
        'spot':'Binance spot native timestamps us since 2025-01-01, ms earlier; UM ms retained',
        'funding':'Native settlement event clock, not accrual start; never forward funding labels',
        'okx':'Archive calendar UTC+8; native UTC epoch unshifted; BTC-USDT-SWAP and funding/trade/L2 never Binance OI',
        'bybit':'Independent linear BTCUSDT/ETHUSDT only. No inverse alias, no substitution for Binance. openInterest vs singleOpenInterest retained separately if future authority is established.',
        'vintage':'HTTP Last-Modified/ETag are archive versions, not exchange publication or receiver timestamps',
        'PIT':'UNKNOWN; source rights do not authorize protected outcomes','real_returns_computed':0}
    bytes_report = {'downloaded_verified_archive_bytes':sum(r['bytes'] for r in good if r['status'].startswith('DOWNLOADED')),
        'reused_original_archive_bytes':sum(r['bytes'] for r in good if r['status']=='REUSED_VERIFIED'),
        'unavailable_known_bytes':0,'unavailable_unknown_size_objects':sum(n for s,n in status.items() if 'UNAVAILABLE' in s),
        'rights_blocked_payload_bytes_downloaded':0,'rights_blocked_size_bytes':None,
        'rights_blocked_family':'Bybit bulk native OI archive retention authority unresolved; no size estimate invented',
        'access_blocked_payload_bytes_downloaded':0,
        'access_blocked_families':[r['family'] for r in access if r['status']!='ACCESS_VERIFIED'],
        'source_blocked_size_bytes':None,'orphan_or_partial_object_bytes':sum(p.stat().st_size for p in orphan_files),
        'note':'404/rights/network failures do not reveal remote payload size; null means unknown, not zero bytes of unavailable history.'}
    preservation = {'Owner_files_SHA_unchanged':len(snapshot['owner_files']),
        'R1_files_SHA_unchanged':len(snapshot['r1_files']),'original_source_signatures_unchanged':len(existing)-sum(not r.get('signature') for r in existing),
        'original_C0_catalog_SHA_unchanged':True,'changed':[], 'forward_databases_opened':0,
        'real_outcomes_evaluated':0,'orders':0,'services_changed':0,'git_commit_push_reset':False}
    for name,value in [('verified_archive_inventory.json',good),('archive_status_inventory.json',records),
        ('sha_manifest.json',sha_manifest),('monthly_coverage_matrix.json',coverage),
        ('normalized_metrics_sha_manifest.json',normalized_manifest),
        ('combined_existing_and_R2_monthly_coverage.json',combined_rows),
        ('native_oi_monthly.json',monthly),('native_oi_hours_by_year.json',yearly),
        ('source_vintage_and_period_checks.json',vintages),('source_timestamp_contract.json',clock),
        ('bytes_by_status.json',bytes_report),('preservation_receipt.json',preservation)]:
        immutable_json(out/name,value)
    immutable_json(out/'source_rights_and_access_blockers.json',{
        'rights_assessment':rights,'official_archive_access_checks':access,
        'bybit_oi_conclusion':'Bulk archive-retention authority not established, not a claim that all personal API use is forbidden; no alternative venue OI is relabeled as Binance.',
        'scope':'Only blocked families held; successful Binance families continued.'})
    transition = [v for v in vintages if '2026-06-24' <= v['period'] <= '2026-06-26']
    immutable_json(out/'metrics_clock_diagnostics.json',{
        'transition_file_checks':transition,
        'interpretation':'Observed label ranges alone cannot confirm or disprove the reported economic-content shift. No blind date-dependent timestamp correction or receiver PIT claim.',
        'per_contract_conflicting_labels':{'/'.join(k):len(v) for k,v in conflicts.items()},
        'within_archive_duplicate_labels':sum(v['duplicate_labels'] for v in vintages),
        'duplicate_rule':'Only equal native rows collapse. Different native tuples at one label are excluded from eligibility.',
        'late_publication':'A 2021 observation in an archive last-modified in 2026 does not prove a 2021 receiver observation.'})
    period_checks = []
    for r in good:
        q = r.get('qc',{})
        if 'first_native_us' not in q:
            continue
        period = r['period']
        start = epoch_us(period+('-01' if len(period)==7 else '')+'T00:00:00Z')
        if len(period)==7:
            y,m = map(int,period.split('-'))
            end = epoch_us(f'{y+m//12}-{m%12+1:02}-01T00:00:00Z')
        else:
            end = start+DAY
        if r['venue']=='okx':
            start -= 8*3600*US;end -= 8*3600*US
        inclusive_end = r['family']=='metrics'
        within = start <= q['first_native_us'] and (q['last_native_us']<=end if inclusive_end else q['last_native_us']<end)
        period_checks.append({'venue':r['venue'],'contract':r['symbol'],'family':r['family'],
            'period_label':period,'expected_start_us':start,'expected_end_us':end,
            'end_inclusive_for_possible_end_labeled_metrics':inclusive_end,
            'observed_first_us':q['first_native_us'],'observed_last_us':q['last_native_us'],
            'native_unit':q['native_timestamp_unit'],'within_nominal_native_window':within,
            'sha256':r['sha256']})
    immutable_json(out/'all_archive_period_boundary_checks.json',period_checks)
    paired = comparison.pop('paired_origins')
    with (out/'btc_incremental_eligible_origins.jsonl').open('xb') as stream:
        for row in paired:
            stream.write(json_bytes(row))
    immutable_json(out/'comparison_with_BLINE_R1.json',comparison)
    for name,values in [('monthly_coverage_matrix.csv',coverage),('combined_existing_and_R2_monthly_coverage.csv',combined_rows),('native_oi_hours_by_year.csv',yearly)]:
        fields = sorted({k for row in values for k in row})
        with (out/name).open('x',newline='') as stream:
            writer = csv.DictWriter(stream,fields)
            writer.writeheader();writer.writerows(values)
    catalog = sqlite3.connect(out/'deduplicated_catalog.sqlite')
    catalog.execute('CREATE TABLE objects(sha256 TEXT PRIMARY KEY,canonical_path TEXT,bytes INTEGER,verification TEXT)')
    catalog.execute('''CREATE TABLE sources(id TEXT PRIMARY KEY,venue TEXT,contract TEXT,product TEXT,
        family TEXT,period TEXT,granularity TEXT,status TEXT,sha256 TEXT,path TEXT,metadata_json TEXT)''')
    for r in existing:
        h = r.get('actual_sha256')
        if h:
            catalog.execute('INSERT OR IGNORE INTO objects VALUES (?,?,?,?)',
                (h,r.get('deduplicated_canonical_path',r['path']),r['bytes'],r['verification']))
        catalog.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?,?,?,?,?)',
            ('existing:'+r['source_id'],r['exchange'],r['symbol'],r['product'],r['family'],r['period'],
             r['interval'],r['verification'],h,r['path'],json_bytes(r).decode()))
    for r in records:
        h = r.get('sha256')
        if h:
            catalog.execute('INSERT OR IGNORE INTO objects VALUES (?,?,?,?)',
                (h,r['path'],r['bytes'],r['status']))
        catalog.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?,?,?,?,?)',
            ('R2:'+r['url'],r['venue'],r['symbol'],r['product'],r['family'],r['period'],
             r['interval'],r['status'],h,r.get('path'),json_bytes(r).decode()))
    catalog.execute('CREATE INDEX source_month_identity ON sources(venue,contract,product,family,period)')
    catalog.commit();catalog.close()
    with (out/'RECEIPT.md').open('x') as stream:
        stream.write('# BLINE R2 archive expansion\n\n'
            f'Root: `{root}`\n\n'
            f'Archive status: `{dict(status)}`\n\n'
            f'New verified archive bytes: {bytes_report["downloaded_verified_archive_bytes"]:,}. '
            f'Reused original bytes: {bytes_report["reused_original_archive_bytes"]:,}.\n\n'
            '| Binance USD-M native OI | Contract | Nominal 5m-equivalent hours | Complete hours |\n'
            '|---|---|---:|---:|\n')
        for r in yearly:
            if r['venue']=='binance':
                stream.write(f'| {r["year"]} | {r["contract"]} | {r["nominal_5m_equivalent_hours"]:.2f} | {r["complete_12_sample_hours"]} |\n')
        stream.write('\nIncremental BTC joint OI/position origins versus frozen R1: '
            f'{comparison["incremental_joint_conservative_vs_r1"]:,}. '
            'This measures archive feature readiness only; receiver PIT remains unknown. '
            'No real outcome evaluation is authorized or executed.\n\n'
            'Bybit bulk native OI retention authority is unresolved. OKX funding/trade/L2 '
            'archive access failed ordinary official-host checks. Blocked remote sizes are unknown; '
            'zero downloaded bytes does not mean zero historical data.\n\n'
            'Run from the quant repository root:\n\n```bash\n'
            f'python3 -m scripts.data.bline_r2.pipeline report --root {root}\n'
            f'python3 -m scripts.data.bline_r2.pipeline acquire --root {root} --tier core --direct --workers 4\n'
            'PYTHONPATH=src:. python3 -m pytest -q tests/data/bline_r2 tests/data/test_data_acquisition.py tests/data/catalog/test_forward_clock_c3.py\n```\n')
    allocated = sum(getattr(p.stat(),'st_blocks',(p.stat().st_size+511)//512)*512 for p in root.rglob('*') if p.is_file())
    logical = sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
    disk = shutil.disk_usage(root)
    checks = {'selected_archives_SHA_verified':len(good),'unique_verified_objects':len(by_sha),
        'allocated_bytes_under_256GB':allocated < 256_000_000_000,
        'free_bytes_above_400GiB':disk.free >= 400*1024**3,
        'real_outcomes_read_zero':True,'R1_preserved':True,'source_clock_not_promoted_to_PIT':True}
    result = {'task':TASK,'status':'BLINE_R2_ARCHIVE_EXPANSION_COMPLETE_WITH_SOURCE_LIMITS',
        'root':str(root),'report_dir':str(out),'completed_at_utc':now(),'labels':LABELS,
        'status_counts':dict(status),'bytes':bytes_report,'disk':{'logical_bytes':logical,'allocated_bytes':allocated,
            'remaining_free_bytes':disk.free,'floor_bytes':400*1024**3,'cap_bytes':256_000_000_000,
            'extracted_to_disk_bytes':0,'temporary_expansion_reserved_bytes':2*1024**3},
        'comparison':comparison,'checks':checks,'preservation':preservation,
        'elapsed_report_s':round(time.monotonic()-began,3),
        'input_manifest_sha256':{str(p.relative_to(root)):digest(p) for p in
            [root/n for n in ['ROOT_RECEIPT.json','rights_assessment.json','existing_inventory.json',
             'preservation_before.json','source_access_checks.json','benefit_review_after_pilot.json',
             'evidence/validation_receipt.json','evidence/focused_validation.xml']] if p.is_file()},
        'artifact_sha256':{str(p.relative_to(out)):digest(p) for p in sorted(out.iterdir()) if p.is_file()},
        'implementation_sha256':{str(p.relative_to(repo)):digest(p) for p in sorted(Path(__file__).parent.glob('*.py'))}}
    immutable_json(out/'COMPLETION_RECEIPT.json',result)
    # The root pointer is append-only; report directories remain reproducible snapshots.
    immutable_json(root/'runs'/('report_'+out.name+'.json'),{'report':str(out),'receipt_sha256':digest(out/'COMPLETION_RECEIPT.json')})
    return {k:result[k] for k in ['task','status','root','report_dir','status_counts','bytes','disk','comparison','checks']}
