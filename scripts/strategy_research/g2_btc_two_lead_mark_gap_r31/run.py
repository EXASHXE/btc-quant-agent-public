"""Gap-only provider repair then full or measured partial two-lead economics."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np

from scripts.strategy_research.g2_btc_two_lead_funding_mark_r3 import run as inherited
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.reanalysis_r2_run import (
    canonical,
    verify_identity,
)

from .gaps import ALLOWED_DAYS, SCRATCH, compose_gap_month, gather_day
from .monthly import load_all
from .partial import partial_study

ROOT=Path(__file__).resolve().parents[3]
START='057c47a4bfd248131f4fd94d12d3deef73c65e1f'
EP=ROOT/'evidence/v0.6/b_line/g2_btc_two_lead_mark_gap_r31'
GRADE='EX_POST_EXPOSED_DEV_ONLY;MONTHLY_VERIFIED_PLUS_GAP_ONLY_VERIFIED_DAILY_OR_API'


def dump(path,value):
    Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def verify_code(sha):
    parent=subprocess.check_output(['git','rev-parse',sha+'^'],text=True,cwd=ROOT).strip()
    if parent!=START:raise ValueError('R31 freeze must directly parent exactstart')
    for prefix,revision in (('scripts/strategy_research/g2_btc_two_lead_mark_gap_r31',sha),
                            ('scripts/strategy_research/g2_btc_two_lead_funding_mark_r3',START),
                            ('scripts/strategy_research/g2_gemini_goal_trend_flow_r1',START)):
        paths=subprocess.check_output(['git','ls-tree','-r','--name-only',revision,'--',prefix],text=True,cwd=ROOT).splitlines()
        for path in paths:
            if (ROOT/path).read_bytes()!=subprocess.check_output(['git','show',revision+':'+path],cwd=ROOT):
                raise ValueError('Frozen inherited/new implementationbytes differ '+path)
    configs,_=verify_identity()
    selected=[c for c in configs if c['id'] in inherited.IDS]
    assert len(selected)==2
    return selected


def full_study(configs,arrays,funding,sha,source):
    # Redirect only the old routine's output destination in memory, never its
    # algorithms/source bytes, old files, or old public scratch.
    previous=inherited.SCRATCH
    inherited.SCRATCH=SCRATCH
    try:
        result=inherited.study(configs,arrays,funding,sha,source)
    finally:
        inherited.SCRATCH=previous
    result['terminal']='R31_TWO_LEAD_OBSERVED_FUNDING_MARK_COMPLETE_DEVELOPMENT_ONLY'
    result['scientific_grade']=GRADE
    result['Mark_MTM_STATUS']='COMPLETE_COMPOSITE_RETROSPECTIVE_NOT_HISTORICAL_KNOWN_AT'
    return result


def run(code_sha):
    configs=verify_code(code_sha)
    if SCRATCH.is_symlink():raise ValueError('Own output scratch symlink')
    SCRATCH.mkdir(exist_ok=True,mode=0o700)
    if (SCRATCH/'R31_ECONOMIC_RESULTS.json').exists():raise ValueError('Bounded R31run alreadycompleted')
    arrays,funding,source=load_all()
    days={};fatal=[];receipts=[]
    for day in ALLOWED_DAYS:
        try:
            rows,receipt=gather_day(day,allow_download=True)
            days[day]=rows;receipts.append(receipt)
            print('GAP',day,len(rows),'unresolved',sum(x['minutes'] for x in receipt['unresolved_ranges']),flush=True)
        except (ValueError,TypeError,OSError) as exc:
            fatal.append({'day':day,'exception':type(exc).__name__,'reason':str(exc)})
            days[day]=np.empty((0,5));receipts.append({'day':day,'fatal_source_conflict':str(exc),'rows':0})
            print('GAP',day,'INTEGRITY FAIL',str(exc),flush=True)
        dump(SCRATCH/'R31_GAP_SOURCE_RECEIPTS.json',{'scientific_grade':GRADE,'days':receipts,'fatal':fatal})
    composites=[]
    for (y,m),monthly in arrays['mark'].items():
        additions=[days[d] for d in ALLOWED_DAYS if d.startswith(f'{y}-{m:02d}-')]
        combined,proof=compose_gap_month(monthly,additions,y,m)
        # Exact preserved values are checked directly, not just clock totals.
        old_rows={int(row[0]):row for row in monthly}
        assert all(np.array_equal(row,old_rows[int(row[0])]) for row in combined if int(row[0]) in old_rows)
        arrays['mark'][y,m]=combined;composites.append({'year':y,'month':m,**proof,'original_monthly_rows_preserved':True})
    source.update({'scientific_grade':GRADE,'gap_source_receipts':receipts,'composites':composites,
        'composite_rows':sum(len(a) for a in arrays['mark'].values()),
        'composite_added_rows':sum(p['added_rows'] for p in composites),
        'full_dense':all(p['dense'] for p in composites),'historical_known_at':'UNPROVEN',
        'gap_no_direct_monthly_overlap':'Expected;all8days absent;provenanceexplicitlylowerwithoutsameclockoverlap'})
    source['source_manifest_sha256']=hashlib.sha256(canonical(source)).hexdigest()
    dump(SCRATCH/'R31_COMPOSITE_SOURCE_MANIFEST.json',source)
    if source['full_dense'] and not fatal:
        assert source['composite_rows']==1576800 and source['composite_added_rows']==11520
        result=full_study(configs,arrays,funding,code_sha,source)
    else:
        result=partial_study(configs,arrays,funding,SCRATCH,source)
        result['scientific_grade']=GRADE
        result['fatal_source_conflicts']=fatal
        if fatal:result['terminal']='R31_FAIL_CLOSED_SOURCE_OR_ACCOUNTING'
    result['frozen_code_sha']=code_sha;result['source_manifest_sha256']=source['source_manifest_sha256']
    result['unresolved_mark_minutes']=1576800-source['composite_rows'];result['automatic_promotions']=[]
    dump(SCRATCH/'R31_ECONOMIC_RESULTS.json',result)
    print('TERMINAL',result['terminal'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--code-sha',required=True)
    args=parser.parse_args()
    try:
        run(args.code_sha)
    except (ValueError,TypeError,AssertionError,OSError) as exc:
        SCRATCH.mkdir(exist_ok=True)
        dump(SCRATCH/'R31_ACCOUNTING_OR_SOURCE_FAILURE.json',{'terminal':'R31_FAIL_CLOSED_SOURCE_OR_ACCOUNTING',
            'frozen_code_sha':args.code_sha,'exception':type(exc).__name__,'reason':str(exc)})
        raise
