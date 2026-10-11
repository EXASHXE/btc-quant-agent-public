import csv
import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

base=Path('/tmp/btc-two-lead-mark-gap-r31');old=Path('/tmp/btc-two-lead-funding-mark-r3');ep=Path('evidence/v0.6/b_line/g2_btc_two_lead_mark_gap_r31')
s=json.loads((base/'R31_COMPOSITE_SOURCE_MANIFEST.json').read_text());r=json.loads((base/'R31_ECONOMIC_RESULTS.json').read_text())
selected={};groups=set();boundary_n=0
for cid,c in r['candidates'].items():
 p=c['costs']['STRESS']['attribution_ledger'];raw=Path(p['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==p['sha256']
 for line in raw.splitlines():
  t=json.loads(line)['trade'];year=datetime.fromtimestamp(t['entry_at']/1000,UTC).year;group=(cid,t['side'],year)
  boundary=any(Decimal(v)!=Decimal(t['funding_cash_usdt']) for v in t['timing_boundary_sensitivity'].values())
  if boundary:boundary_n+=1
  if (t['funding_settlements'] and group not in groups) or boundary:
   selected[cid,t['event_id']]=t;groups.add(group)
# Independent source decoding; no inherited economics or adapter calls.
def member(path,sha):
 assert not path.is_symlink();raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==sha
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  assert len(z.namelist())==1
  return z.read(z.namelist()[0]).decode()
rates={}
for ref in s['successful_sources']:
 if ref['kind']!='funding':continue
 name=f"BTCUSDT-fundingRate-{ref['year']}-{ref['month']:02d}.zip"
 rows=csv.DictReader(io.StringIO(member(old/('funding-'+name),ref['zip_sha256'])))
 for row in rows:
  stamp=int(row['calc_time']);assert stamp not in rates;rates[stamp]=Decimal(row['last_funding_rate'])
assert len(rates)==3285
shifts=((0,0),(-60000,-60000),(60000,60000),(-60000,60000),(60000,-60000))
needed=set()
for t in selected.values():
 for a,z in shifts:
  needed.update(((ts-59999)//60000)*60000 for ts in rates if t['entry_at']+a<=ts<t['exit_at']+z)
marks={}
for ref in s['successful_sources']:
 if ref['kind']!='mark':continue
 y,m=ref['year'],ref['month'];targets={ts for ts in needed if datetime.fromtimestamp(ts/1000,UTC).year==y and datetime.fromtimestamp(ts/1000,UTC).month==m}
 if not targets:continue
 text=member(old/(f'mark-BTCUSDT-1m-{y}-{m:02d}.zip'),ref['zip_sha256'])
 for row in csv.reader(io.StringIO(text)):
  if row[0]=='open_time':continue
  ts=int(row[0])
  if ts in targets:assert ts not in marks;marks[ts]=(Decimal(row[4]),int(row[6]),'MONTHLY_AUTHORITY')
for dr in s['gap_source_receipts']:
 d=dr['day'];ds=int(datetime.strptime(d,'%Y-%m-%d').replace(tzinfo=UTC).timestamp()*1000)
 if not any(ds<=ts<ds+86400000 and ts not in marks for ts in needed):continue
 text=member(base/d/(f'BTCUSDT-1m-{d}.zip'),dr['daily_parse']['zip_sha256'])
 for row in csv.reader(io.StringIO(text)):
  if row[0]=='open_time':continue
  ts=int(row[0])
  if ts in needed:assert ts not in marks;marks[ts]=(Decimal(row[4]),int(row[6]),'DAILY_AUTHENTICATED_REPAIR')
assert needed<=set(marks)
episodes=[]
for (cid,eid),t in selected.items():
 cases=[]
 for a,z in shifts:
  cash=Decimal(0);events=[]
  for ts,rate in sorted(rates.items()):
   if not t['entry_at']+a<=ts<t['exit_at']+z:continue
   at=((ts-59999)//60000)*60000;price,close,source=marks[at]
   assert close<=ts and ts-close<60000
   bill=-Decimal(t['side'])*Decimal(str(t['quantity']))*price*rate;cash+=bill
   events.append({'settlement_at':ts,'rate_fraction':str(rate),'quantity':str(t['quantity']),'Mark_completed_close_at':close,'Mark_close':str(price),'Mark_source':source,'signed_cash_usdt':str(bill)})
  expected=t['funding_cash_usdt'] if (a,z)==(0,0) else t['timing_boundary_sensitivity'][f'{a},{z}']
  assert abs(cash-Decimal(expected))<=Decimal('1e-24')
  cases.append({'shift_entry_ms':a,'shift_exit_ms':z,'settlements':events,'independent_cash_usdt':str(cash),'frozen_ledger_cash_usdt':expected,'assertions':'PASS'})
 episodes.append({'candidate':cid,'event_id':eid,'side':t['side'],'year':datetime.fromtimestamp(t['entry_at']/1000,UTC).year,'entry_at':t['entry_at'],'exit_at':t['exit_at'],'actual_boundary_sensitive':any(c['independent_cash_usdt']!=cases[0]['independent_cash_usdt'] for c in cases[1:]),'cases':cases})
assert len(episodes)>=5 and {e['side'] for e in episodes}=={-1,1} and {e['year'] for e in episodes}=={2021,2022,2023}
assert any(e['candidate'].startswith('W2') and e['actual_boundary_sensitive'] for e in episodes)
result={'method':'Independent stdlib CSV/ZIP and Decimal source reconstruction; -side*quantity*completedMark*actualRate; [entry+shift,exit+shift); no production economics imports','source_manifest_sha256':s['source_manifest_sha256'],'episodes':episodes,'episode_count':len(episodes),'checked_shift_cases':len(episodes)*5,'all_frozen_boundary_sensitive_trades':boundary_n,'audited_boundary_sensitive_trades':sum(e['actual_boundary_sensitive'] for e in episodes),'rate_event_count':len(rates),'historical_settlement_mark_basis':'LATEST_COMPLETED_1M_MARK_CLOSE_APPROXIMATION_NOT_EXACT_EXCHANGE_SETTLEMENT_MARK','status':'PASS'}
(ep/'R31_INDEPENDENT_REAL_DECIMAL_BOUNDARY_AUDIT.json').write_text(json.dumps(result,indent=2)+'\n')
print({k:result[k] for k in ['episode_count','checked_shift_cases','all_frozen_boundary_sensitive_trades','audited_boundary_sensitive_trades','status']})
