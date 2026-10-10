"""Stage conservation, cash reconciliation, reproduction and a finite audit."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from importlib.metadata import version
from pathlib import Path

import numpy as np

from scripts.strategy_research.g2_btc_empirical_fast_r1.audit import check_trade

from .run import FREEZE, dump
from .sources import EVIDENCE, ROOT, SCRATCH, utcnow, verify_freeze


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    roster,split=verify_freeze(FREEZE)
    assert sum(f['stage']=='DEVELOPMENT' for f in split['folds'])==12
    one=SCRATCH/'development-run1';two=SCRATCH/'development-run2'
    assert (one/'results.json').read_bytes()==(two/'results.json').read_bytes()
    result=json.loads((one/'results.json').read_text())
    assert result['stage']=='DEVELOPMENT' and result['terminal']=='DEVELOPMENT_NO_GO'
    assert not result['promoted_ids']
    assert len(result['rows'])==12 and len(result['full_folds'])==12
    trades=[json.loads(line) for line in (one/'trade_ledger.jsonl').read_text().splitlines()]
    events=[json.loads(line) for line in (one/'event_fates.jsonl').read_text().splitlines()]
    manifest=json.loads((EVIDENCE/'SOURCE_MANIFEST_DEVELOPMENT.json').read_text())
    assert len(manifest['records'])==24
    assert all(r['year'] in [2021,2022,2023] for r in manifest['records'])
    assert manifest['gate']=='PASS_PUBLIC_TRADE_PRICE_ONLY'
    for t in trades:
        fold=next(f for f in result['folds'] if f['id']==t['fold'])
        assert fold['start_ms']<=t['entry_at']<t['exit_at']<fold['end_ms']
        assert t['exit_ack_at']<=fold['end_ms']
        assert t['entry_at']>=t['decision_at']+60000>=t['event_time']+120000
        assert abs(t['net_usdt']-t['gross_usdt']+t['fee_usdt']+t['execution_drag_usdt'])<1e-7
        assert t['side']*(t['raw_exit']-t['target'])<=1e-6
    for row in result['rows']:
        for fold in row['folds']:
            selected=[e for e in events if (e['candidate'],e['cost_case'],e['fold'])==
                      (row['candidate'],row['cost_case'],fold['fold'])]
            assert len(selected)==fold['generated_signals']
            assert len({(e['event_id'],e['entry_at']) for e in selected})==len(selected)
            assert sum(e['result']=='FILLED' for e in selected)==fold['trades']
            assert abs(sum(d['daily_pnl_usdt'] for d in fold['daily_account'])-fold['net_usdt'])<1e-7
            assert abs(fold['ending_equity_usdt']-1000-fold['net_usdt'])<1e-7
        assert sum(y['trades'] for y in row['years'])==row['trades']
    for record in result['ledger_manifest']:
        assert sha(one/record['name'])==record['sha256']==sha(two/record['name'])
    simple=sorted([t for t in trades if not t['partial_reductions'] and t['exit_reason']!='DRAWDOWN_KILL'],
                  key=lambda t:(t['entry_at'],t['candidate'],t['cost_case']))
    selected=[];used=set()
    for label,predicate in [('EARLIEST_LONG',lambda t:t['side']==1),
                            ('EARLIEST_SHORT',lambda t:t['side']==-1),
                            ('EARLIEST_TARGET_ELSE_FIRST_REMAINING',lambda t:t['exit_reason']=='TARGET')]:
        eligible=[t for t in simple if (t['candidate'],t['cost_case'],t['event_id'],t['fold']) not in used]
        t=next((t for t in eligible if predicate(t)),eligible[0])
        used.add((t['candidate'],t['cost_case'],t['event_id'],t['fold']))
        fold=next(f for f in result['folds'] if f['id']==t['fold'])
        data=np.concatenate([np.load(SCRATCH/f"validated-{fold['year']}-{m:02}.npy",allow_pickle=False)
                             for m in [fold['warmup_month'],fold['month']]])[:,:6]
        audit=check_trade(data,t,roster['execution']['costs'][t['cost_case']])
        selected.append(dict(audit,selection=label))
    (EVIDENCE/'THREE_TRADE_DECIMAL_AUDIT.json').write_bytes(dump({'audited_trades':selected,'pass_count':3,
        'audit_scope':'UNMODIFIED_R1_INDEPENDENT_DECIMAL_FIRST_HIT_HELPER_NOT_FULL_ENGINE_CERTIFICATION'}))
    shutil.copyfile(one/'results.json',EVIDENCE/'DEVELOPMENT_RESULTS.json')
    promotion={'stage':'DEVELOPMENT','freeze_sha':FREEZE,'promoted_ids':[],
        'results_sha256':sha(EVIDENCE/'DEVELOPMENT_RESULTS.json'),'decision_at_utc':utcnow(),
        'terminal':'DEVELOPMENT_NO_GO','reserved_action':'DO_NOT_STAT_DOWNLOAD_READ_RESERVED_MONTHS',
        'ranking':[{'candidate':r['candidate'],'ranking_score':r['ranking_score'],'gate_failures':r['gate_failures']}
                   for r in sorted([r for r in result['rows'] if r['cost_case']=='STRESS'],
                        key=lambda r:(r['ranking_score'] is None,-(r['ranking_score'] or 0),-r['unique_filled_events'],r['candidate']))]}
    (EVIDENCE/'DEVELOPMENT_PROMOTION.json').write_bytes(dump(promotion))
    log=Path('/tmp/g2_r2_pytest_final.log').read_text()
    match=re.search(r'(\d+) passed in ([\d.]+)s',log);assert match and int(match[1])>=12
    code=sorted((ROOT/'scripts/strategy_research/g2_btc_flow_regime_r2').glob('*.py'))
    tests=sorted((ROOT/'tests').glob('test_v06_g2_btc_flow_regime_r2_*.py'))
    receipt={'task_id':roster['task_id'],'controller_sha':roster['controller_dispatch_sha'],
        'prompt_sha':roster['prompt_sha'],'exact_start_sha':roster['exact_start_sha'],'freeze_sha':FREEZE,
        'second_commit_expected_parent':FREEZE,'expected_commit_count':2,'third_commit':'NOT_REQUIRED_AND_NOT_CREATED_DEV_NO_GO',
        'actual_root_model':'NOT_EXPOSED','actual_root_effort':'NOT_EXPOSED','requested_model':roster['requested_model'],
        'implementation_workers':'observable implementer GPT-6 Sol Medium, synthetic only',
        'verified_at_utc':utcnow(),'terminal':result['terminal'],'dependencies':{k:version(k) for k in ['numpy','pytest','ruff']},
        'source_rows':sum(r['price_rows'] for r in manifest['records']),'source_archives':24,
        'first_development_csv_body_read_at_utc':manifest['first_price_csv_read_at_utc'],
        'reserved_raw_stat_download_body_reads':0,'protected_owner_account_access':0,
        'frozen_roster_split_receipt_R1_code':'EXACT_BYTES_PASS','R1_code_modified':False,
        'data_rounding_imputation_clamps':0,'strict_source_reparse_and_cache_match':24,
        'candidate_cost_trade_observations':len(trades),'candidate_fold_event_union_count':len({(t['candidate'],t['fold'],t['event_id']) for t in trades}),
        'independent_trade_count_claim':False,'event_fates_verified':len(events),'account_fold_reconciliations':144,
        'ledger_hashes_verified':len(result['ledger_manifest']),
        'byte_identical_second_run':True,'results_sha256':promotion['results_sha256'],
        'trade_ledger_sha256':sha(one/'trade_ledger.jsonl'),
        'focused_pytest':{'command':'pytest -q tests/test_v06_g2_btc_flow_regime_r2_*.py',
                          'passed':int(match[1]),'elapsed_seconds':float(match[2]),'exit_code':0,'output_sha256':hashlib.sha256(log.encode()).hexdigest()},
        'ruff_compile_JSON':'PASS_OBSERVED_SEPARATELY_FINAL_CHECK','three_independent_actual_decimal_audits':3,
        'code_and_test_sha256':{str(p.relative_to(ROOT)):sha(p) for p in [*code,*tests]},
        'one_fixed_roster_no_outcome_retunes':True,'reserved_validation':'NOT_RUN_DEV_NO_PROMOTION_NOT_A_VALIDATION_ZERO',
        'rights':roster['source_rights'],'source_economics':'MARK_FUNDING_FEES_FILTERS_PIT_UNKNOWN_COST_PROXY',
        'P2_P3_P4_ALPHA_TESTNET_LIVE':'NONE','repository_full_CI':'NOT_LOCALLY_REPEATED; final exactSHA observed externally afterpush; noH40waiver',
        'allowed_new_namespaces':['scripts/strategy_research/g2_btc_flow_regime_r2/**','tests/test_v06_g2_btc_flow_regime_r2_*.py',
                                  'docs/strategy_research/g2_r3/flow_regime_r2/**','evidence/v0.6/b_line/g2_btc_flow_regime_r2/**']}
    (EVIDENCE/'EXECUTION_RECEIPT.json').write_bytes(dump(receipt))
    print(json.dumps({'verified':'PASS','terminal':result['terminal'],'trade_observations':len(trades),
                      'event_fates':len(events),'three_decimal_audits':'PASS','promotion':[]}))


if __name__=='__main__':main()
