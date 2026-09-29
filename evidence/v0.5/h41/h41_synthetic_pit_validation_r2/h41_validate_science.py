import dataclasses
import hashlib
import io
import json
import math
import subprocess
import tempfile
import zipfile
from decimal import Decimal
from pathlib import Path
import numpy as np
from btc_quant_agent.h41.authority import CANDIDATES, EXPECTED_SOURCE_ROOT
from btc_quant_agent.h41.science import HOUR_MS, PARTITIONS, CompletedBar, CompletedPairView, Event, EventBatch, build_event_batch, candidate_side, train_q80, _linear_q80
from btc_quant_agent.h41.outcomes import materialize_outcomes
from btc_quant_agent.h41.selection import CandidateInference, rank_positive_lcb
from btc_quant_agent.h41.source import load_synthetic_archive, projection_sha256, canonical_number
from btc_quant_agent.h41.testability import H41State, make_testability_receipt

base=PARTITIONS['WF1_TRAIN'][0]
t=base+100*HOUR_MS

def view(decision,btc=None,eth=None,n=74):
    btc=btc or [100.] * n; eth=eth or [100.] * n
    def bars(vals):return tuple(CompletedBar(decision-(i+1)*HOUR_MS,vals[i]+1,vals[i]-1,vals[i]) for i in range(n))
    return CompletedPairView(decision,bars(btc),bars(eth))

checks={}
assert {f.name for f in dataclasses.fields(CompletedBar)}=={'open_time_ms','high','low','close'}
checks['pit_completed_bar_field_isolation']=True
for cand in CANDIDATES[:4]:
    vals=[100.]*74; vals[0]=110.
    v=view(t,btc=vals if cand.target_asset=='BTCUSDT' else None,eth=vals if cand.target_asset=='ETHUSDT' else None)
    assert candidate_side(cand,v,{cand.candidate_id:math.log(1.1)})==1
    vals[0]=90.
    v=view(t,btc=vals if cand.target_asset=='BTCUSDT' else None,eth=vals if cand.target_asset=='ETHUSDT' else None)
    assert candidate_side(cand,v,{cand.candidate_id:abs(math.log(.9))})==-1
    vals[0]=100.
    v=view(t,btc=vals if cand.target_asset=='BTCUSDT' else None,eth=vals if cand.target_asset=='ETHUSDT' else None)
    assert candidate_side(cand,v,{cand.candidate_id:0.})==0
scores=[abs(math.log((100+i%23)/100)) for i in range(500)]
assert _linear_q80(scores)==float(np.quantile(scores,.8,method='linear'))
try:_linear_q80(scores[:499]);raise AssertionError('500 floor absent')
except ValueError:pass
checks['D1_four_variants_q80_sign_equality_floor']=True
for cand in CANDIDATES[4:8]:
    vals=[100.]*74
    for close,expected in [(103.,1),(97.,-1),(101.,0),(99.,0)]:
        vals[0]=close
        v=view(t,btc=vals if cand.target_asset=='BTCUSDT' else None,eth=vals if cand.target_asset=='ETHUSDT' else None)
        assert candidate_side(cand,v,{})==expected
checks['D2_four_variants_both_sides_equality']=True
for cand in CANDIDATES[8:12]:
    vals=[100.]*74
    for prior,current,expected in [(103.,100.,-1),(97.,100.,1),(101.,100.,0),(103.,101.,0),(97.,99.,0)]:
        vals[1]=prior;vals[0]=current
        v=view(t,btc=vals if cand.target_asset=='BTCUSDT' else None,eth=vals if cand.target_asset=='ETHUSDT' else None)
        assert candidate_side(cand,v,{})==expected
checks['D3_four_variants_prior_break_inside_equality']=True
for idx in (12,14,16,18):
    confirm,diverge=CANDIDATES[idx:idx+2]
    parent=CANDIDATES[[0,2,4,6][(idx-12)//2]]
    vals=[100.]*74;vals[0]=103.
    other=[100.]*74
    q80={parent.candidate_id:0.} if parent.family=='D1_TREND' else {}
    for other_close,expected in [(105.,(1,0)),(95.,(0,1)),(100.,(0,0))]:
        other[0]=other_close
        v=view(t,btc=vals if confirm.target_asset=='BTCUSDT' else other,eth=other if confirm.target_asset=='BTCUSDT' else vals)
        assert (candidate_side(confirm,v,q80),candidate_side(diverge,v,q80))==expected
checks['D4_eight_variants_RET4_sign_parent_inheritance']=True
hours={k:(b-a)//HOUR_MS for k,(a,b) in PARTITIONS.items()}
assert hours=={'WF1_TRAIN':16032,'WF1_PURGE_1':24,'WF1_CALIBRATION':2184,'WF1_PURGE_2':24,'WF1_VALIDATION':2112,'SOURCE_RESERVE':24}
for h in (4,8,24):
    cand=next(c for c in CANDIDATES if c.horizon_hours==h)
    end=PARTITIONS['WF1_TRAIN'][1]
    for delta,valid in ((h+1,True),(h,True),(h-1,False)):
        event=Event(end-delta*HOUR_MS,1,h)
        try: EventBatch(cand.candidate_id,'WF1_TRAIN',(event,));got=True
        except ValueError:got=False
        assert got==valid
for partition in ('WF1_PURGE_1','WF1_PURGE_2','WF1_VALIDATION','SOURCE_RESERVE'):
    try:candidate_side(CANDIDATES[4],view(PARTITIONS[partition][0]),{});raise AssertionError('protected scientific read allowed')
    except ValueError:pass
checks['partitions_right_boundary_protected_science']=True

def batch(n,d):
    times=sorted(base+(i%d)*24*HOUR_MS+(i//d)*HOUR_MS for i in range(n))
    return EventBatch(CANDIDATES[0].candidate_id,'WF1_TRAIN',tuple(Event(x,1,4) for x in times))
assert make_testability_receipt(batch(59,30)).state==H41State.BASIC_SUPPORT_UNAVAILABLE
assert make_testability_receipt(batch(60,29)).state==H41State.BASIC_SUPPORT_UNAVAILABLE
receipt=make_testability_receipt(batch(60,30))
assert receipt.state==H41State.TESTABLE_EXPLORATORY
assert not any(x in {f.name.lower() for f in dataclasses.fields(receipt)} for x in ('price','open','return','mu','lcb','ranking','pnl'))
checks['testability_N_D_floors_redaction']=True
class Marks:
    def __init__(self,entry,exit):self.entry=Decimal(entry);self.exit=Decimal(exit)
    def open_at(self,symbol,time):return self.entry if time==t else self.exit
one=EventBatch(CANDIDATES[0].candidate_id,'WF1_TRAIN',(Event(t,1,4),))
y=materialize_outcomes(one,Marks('101','102'))[0]
assert y.primary_net==float(Decimal(102)/Decimal(101)-1)-.0012
assert y.stress_net_diagnostic==float(Decimal(102)/Decimal(101)-1)-.0024
checks['endpoint_open_ratio_12bp_24bp']=True
ids=[c.candidate_id for c in CANDIDATES]
rows=[CandidateInference(ids[0],.01,100,.3,30),CandidateInference(ids[1],.02,60,.1,30)]
rows += [CandidateInference(cid,float('-inf'),0,0.,0) for cid in ids[2:]]
assert [x.candidate_id for x in rank_positive_lcb(rows)]==[ids[1],ids[0]]
checks['ranking_LCB_over_mu_support']=True
with tempfile.TemporaryDirectory() as td:
    root=Path(td);symbol='BTCUSDT';month='2021-01';name=f'{symbol}-1h-{month}'
    csv='\n'.join(f'{base+i*HOUR_MS},100.00,102,99,100,1,{base+(i+1)*HOUR_MS-1},100,5,0.5,50,0' for i in range(2))+'\n'
    path=root/f'{name}.zip'
    with zipfile.ZipFile(path,'w') as z:z.writestr(f'{name}.csv',csv)
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    parsed=load_synthetic_archive(path,symbol,month,digest)
    audit_source=subprocess.check_output(['git','-C',str(Path(__file__).resolve().parents[4]),'show','807b545d7bda0801e51648e1c5bc7bfc42f121d4:scripts/v0.5/h41_source_authority_closure.py']).decode()
    ns={'__name__':'accepted_source_audit'};exec(compile(audit_source,'<accepted_source_audit>','exec'),ns)
    accepted=ns['audit_archive'](path,symbol,month,digest)
    assert parsed.projection_sha256==accepted['projection_hash']==projection_sha256((parsed,))
    assert parsed.timestamp_membership_sha256==accepted['timestamp_membership_hash']
    assert len(parsed.bars[0].projection())==14 and canonical_number(Decimal('100.00'))=='100'
    for wrong in ('0'*64,):
        try:load_synthetic_archive(path,symbol,month,wrong);raise AssertionError('checksum accepted')
        except ValueError:pass
    path.write_bytes(b'bad zip')
    try:load_synthetic_archive(path,symbol,month,digest);raise AssertionError('mutation accepted')
    except ValueError:pass
checks['source_projection_independent_audit_same_buffer']=True
# Material authority gaps, using synthetic data only.
cal_start,cal_end=PARTITIONS['WF1_CALIBRATION']
candidate=CANDIDATES[0]

def views():
    for i in range(2184):
        decision=cal_start+i*HOUR_MS
        vals=[100+0.01*(i-j) for j in range(5)]
        yield view(decision,btc=vals,eth=[100.]*5,n=5)
low=build_event_batch(candidate,views(),{candidate.candidate_id:0.},'WF1_CALIBRATION')
high=build_event_batch(candidate,views(),{candidate.candidate_id:1.},'WF1_CALIBRATION')
assert len(low.events)>0 and len(high.events)==0
forged=make_testability_receipt(batch(60,30))
assert forged.source_authority_root!=EXPECTED_SOURCE_ROOT
assert forged.authority_kind=="SYNTHETIC_NON_AUTHORITATIVE"
altered=materialize_outcomes(one,Marks('101','110'))[0]
assert altered.primary_net!=y.primary_net
adversarial={'caller_q80_changes_event_count_same_completed_views':[len(low.events),len(high.events)],'synthetic_batch_source_root':forged.source_authority_root,'caller_marks_change_outcome_same_event':True}
result={'checks':checks,'independent_check_count':len(checks),'all_independent_checks_passed':all(checks.values()),'adversarial_authority_substitution':adversarial,'material_defect_confirmed':False}
Path(__file__).with_name('h41_science_result.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
print(json.dumps(result,sort_keys=True))
