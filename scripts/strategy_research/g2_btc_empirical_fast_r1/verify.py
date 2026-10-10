"""Assert result/ledger causality, event conservation and exact rerun digests."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

from .run import FREEZE
from .sources import EVIDENCE, ROOT, verify_freeze


def main():
    verify_freeze(FREEZE)
    scratch=Path('/tmp/g2-btc-public-empirical-fast-r1')
    a=scratch/'run1/aggregate_results.json';b=scratch/'run2/aggregate_results.json'
    assert a.read_bytes()==b.read_bytes(), 'aggregate/ledger rerun mismatch'
    r=json.loads(a.read_text())
    assert len(r['rows'])==24 and len(r['folds'])==5
    assert all(len(x['folds'])==5 for x in r['rows'])
    trades=[json.loads(line) for line in (scratch/'run1/trade_ledger.jsonl').read_text().splitlines()]
    events=[json.loads(line) for line in (scratch/'run1/decision_event_ledger.jsonl').read_text().splitlines()]
    assert len(trades)==r['total_candidate_cost_trades']
    for t in trades:
        assert t['decision_at']>=t['event_time']+60000
        assert t['entry_at']>=t['decision_at']+60000
        fold=next(f for f in r['folds'] if f['id']==t['fold'])
        assert fold['start_ms']<=t['entry_at']<t['exit_at']<fold['end_ms']
        assert abs(t['net_usdt']-(t['gross_usdt']-t['fee_usdt']-t['execution_drag_usdt']))<1e-7
        assert t['quantity']>0
    for row in r['rows']:
        for fold in row['folds']:
            selected=[e for e in events if e['candidate']==row['candidate'] and
                      e['fold']==fold['fold'] and e['cost_case']==row['cost_case']]
            assert len(selected)==fold['source_signal_events_including_warmup']
            assert len(selected)==sum(v for k,v in fold['waits'].items() if k!='DRAWDOWN_DISABLE')
            assert len({(e['event_id'],e['entry_at']) for e in selected})==len(selected)
            assert sum(e['result']=='FILLED' for e in selected)==fold['trades']
            assert abs(sum(d['daily_pnl_usdt'] for d in fold['daily_account'])-fold['net_usdt'])<1e-7
    for record in r['ledger_manifest']:
        path=scratch/'run1'/record['name']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==record['sha256']
    audit=json.loads((EVIDENCE/'INDEPENDENT_THREE_TRADE_HAND_AUDIT.json').read_text())
    assert audit['pass_count']==3 and all(t['assertions']=='PASS' for t in audit['audited_trades'])
    shutil.copyfile(a,EVIDENCE/'AGGREGATE_RESULTS.json')
    receipt=json.loads((EVIDENCE/'EXECUTION_RECEIPT.json').read_text())
    output=Path('/tmp/g2_empirical_pytest_final.log').read_text()
    match=re.search(r'(\d+) passed in ([\d.]+)s',output)
    assert match and int(match[1])>=12
    receipt['focused_validation'][0].update(passed=int(match[1]),elapsed_seconds=float(match[2]),
        output_sha256=hashlib.sha256(output.encode()).hexdigest())
    paths=sorted(list((ROOT/'scripts/strategy_research/g2_btc_empirical_fast_r1').glob('*.py'))+
                 list((ROOT/'tests').glob('test_v06_g2_btc_empirical_fast_*.py')))
    receipt.update(reproduction_verified='PASS_BYTE_IDENTICAL_AGGREGATE_AND_ALL_LEDGER_HASHES',
        aggregate_sha256=hashlib.sha256(a.read_bytes()).hexdigest(),
        decision_events=len(events),
        trade_ledger_sha256=next(p['sha256'] for p in r['ledger_manifest'] if p['name']=='trade_ledger.jsonl'),
        source_manifest_sha256=r['source_manifest_sha256'],
        machine_cross_checks={'causal_trade_clocks':len(trades),'fate_for_every_generated_event':len(events),
            'account_fold_reconciliation':120,'daily_pnl_reconciliation':120,
            'ledger_hashes_verified':len(r['ledger_manifest']),'all_candidate_fold_and_cost_rows':120},
        code_test_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    (EVIDENCE/'EXECUTION_RECEIPT.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'verification':'PASS','trades':len(trades),'event_fates':len(events),
                      'aggregate_sha256':receipt['aggregate_sha256']}))


if __name__=='__main__':
    main()
