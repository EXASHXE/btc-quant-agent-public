"""Independent Decimal arithmetic and first-hit walkthrough for three real trades.

No replay helpers are called. This checks fixed protection episodes, not a
second research engine or additional policy search.
"""
from __future__ import annotations

import json
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from pathlib import Path

import numpy as np

from .sources import EVIDENCE


def d(value) -> Decimal:
    return Decimal(str(value))


def rounded(price: Decimal, up: bool) -> Decimal:
    tick = Decimal('.1')
    return (price/tick).to_integral_value(rounding=ROUND_CEILING if up else ROUND_FLOOR)*tick


def check_trade(data, trade: dict, costs: dict) -> dict:
    assert not trade['partial_reductions'] and trade['exit_reason'] != 'DRAWDOWN_KILL'
    assert trade['decision_at'] >= trade['event_time']+60000
    assert trade['entry_at'] >= trade['decision_at']+60000
    i = int(np.searchsorted(data[:,0],trade['entry_at']))
    assert int(data[i,0]) == trade['entry_at']
    assert int(data[i-2,0])+120000 <= trade['entry_at']
    side = trade['side']; qty = d(trade['quantity'])
    entry = d(data[i,1]); assert entry == d(trade['raw_entry'])
    drag = (d(costs['spread_bps'])+d(costs['slippage_bps']))/10000
    effective_entry = rounded(entry*(1+side*drag),side > 0)
    stop = d(trade['stop']); risk = side*(effective_entry-stop)
    target = rounded(effective_entry+side*2*risk,side < 0)
    assert abs(target-d(trade['target'])) < d('.000001')
    deadline = trade['entry_at']+trade['hold_hours']*3600000
    witness = None
    for j in range(i,len(data)):
        at = int(data[j,0]); op,hi,lo = (d(v) for v in data[j,1:4])
        if side*(op-stop) <= 0:
            raw, reason, exit_at = op,'STOP_GAP',at
        elif at >= deadline:
            raw = min(op,target) if side > 0 else max(op,target)
            reason,exit_at = 'TIME_CAP',at
        elif side*(op-target) >= 0:
            raw,reason,exit_at = target,'TARGET_GAP_CAPPED',at
        elif (lo<=stop if side>0 else hi>=stop):
            raw,reason,exit_at = stop,'STOP',at+59999
        elif (hi>=target if side>0 else lo<=target):
            raw,reason,exit_at = target,'TARGET',at+59999
        else:
            continue
        collision = (lo<=stop and hi>=target) if side > 0 else (hi>=stop and lo<=target)
        witness={'utc_minute_open_ms':at,'stop_target_same_bar':collision}
        break
    assert witness is not None
    assert reason == trade['exit_reason'] and exit_at == trade['exit_at']
    assert abs(raw-d(trade['raw_exit'])) < d('.000001')
    effective_exit = rounded(raw*(1-side*drag),side < 0)
    fee_rate = d(costs['fee_bps'])/10000
    entry_fee = effective_entry*qty*fee_rate; exit_fee=effective_exit*qty*fee_rate
    net = side*(effective_exit-effective_entry)*qty-entry_fee-exit_fee
    for key,value in [('effective_entry',effective_entry),('effective_exit',effective_exit),
                      ('entry_fee_usdt',entry_fee),('exit_fee_usdt',exit_fee),('net_usdt',net)]:
        assert abs(value-d(trade[key])) < d('.000001'), key
    return {'candidate':trade['candidate'],'fold':trade['fold'],'cost_case':trade['cost_case'],
        'event_id':trade['event_id'],'side':side,'event_time':trade['event_time'],
        'decision_at':trade['decision_at'],'entry_at':trade['entry_at'],'exit_at':exit_at,
        'exit_reason':reason,'exit_ack_at':trade['exit_ack_at'],'source_entry_open':str(entry),
        'raw_exit':str(raw),'stop':str(stop),'target':str(target),
        'quantity':str(qty),'effective_entry':str(effective_entry),'effective_exit':str(effective_exit),
        'decimal_entry_fee':str(entry_fee),'decimal_exit_fee':str(exit_fee),'decimal_net_usdt':str(net),
        'net_bps':trade['net_bps'],'exit_witness':witness,'assertions':'PASS',
        'scope':'INDEPENDENT_FIRST_HIT_AND_DECIMAL_EPISODE_AUDIT_NOT_WHOLE_BOOK_CERTIFICATION'}


def main():
    scratch=Path('/tmp/g2-btc-public-empirical-fast-r1')
    trades=[json.loads(line) for line in (scratch/'run1/trade_ledger.jsonl').read_text().splitlines()]
    roster=json.loads((EVIDENCE/'FROZEN_STRATEGY_REGISTRY.json').read_text())
    simple=sorted([t for t in trades if not t['partial_reductions'] and t['exit_reason']!='DRAWDOWN_KILL'],
                  key=lambda t:(t['entry_at'],t['candidate'],t['cost_case']))
    selected=[]; used=set()
    criteria=[('EARLIEST_LONG',lambda t:t['side']==1),('EARLIEST_SHORT',lambda t:t['side']==-1),
              ('EARLIEST_GAP_STOP_ELSE_FIRST_REMAINING',lambda t:t['exit_reason']=='STOP_GAP')]
    for name,predicate in criteria:
        eligible=[t for t in simple if (t['candidate'],t['cost_case'],t['event_id'],t['fold']) not in used]
        t=next((t for t in eligible if predicate(t)),eligible[0])
        used.add((t['candidate'],t['cost_case'],t['event_id'],t['fold']))
        y=int(t['fold']);data=np.concatenate([np.load(scratch/f'validated-{y}-{m:02}.npy',allow_pickle=False) for m in [3,4]])
        audit=check_trade(data,t,roster['costs'][t['cost_case']]);audit['selection']=name;selected.append(audit)
    assert len(selected)==3
    (EVIDENCE/'INDEPENDENT_THREE_TRADE_HAND_AUDIT.json').write_text(json.dumps({
        'method':'INDEPENDENT_DECIMAL_AND_MINUTE_WALKTHROUGH_NO_REPLAY_HELPER_CALLS',
        'selection':'EARLIEST_LONG_EARLIEST_SHORT_EARLIEST_GAP_STOP_ELSE_FIRST_REMAINING_SIMPLE_EPISODE',
        'audited_trades':selected,'pass_count':3},indent=2,sort_keys=True)+'\n')
    print('three independent trade audits PASS')


if __name__=='__main__':
    main()
