"""Invented, explicit human-approved offline fixture; never a market data loader."""
from __future__ import annotations

from .model import digest


def bar(index,side='LONG',*,exit_kind='STOP'):
    sign=1 if side=='LONG' else -1
    value=30000
    if index==360:value=30000+sign*305
    elif index>360:value=30000+sign*200
    if exit_kind=='STOP' and index>=720:value=30000-sign*100
    return {'source':'SYNTHETIC_V1','open_time':index*60000,'close_time':index*60000+59999,
        'available_at':index*60000+59999,'last_open':str(value),'last_high':str(value+5),
        'last_low':str(value-5),'last_close':str(value),'mark_close':str(value+sign*7)}


def make_fixture(side='LONG',horizon=24,exit_kind='STOP'):
    if side not in ('LONG','SHORT') or horizon not in (12,18,24) or exit_kind not in ('STOP','TIME_CAP','CLOSE'):
        raise ValueError('Only registered synthetic fixture variants')
    first=bar(0,side,exit_kind=exit_kind);sign=1 if side=='LONG' else -1
    proposal={'schema_version':1,'signal_id':'synthetic-'+side.lower(),'source_hash':digest(first),
        'source_close_at':59999,'decision_at':60000,'side':side,'quantity':'0.01','stop':str(30000-sign*300),
        'tp1':str(30000+sign*300),'tp2':str(30000+sign*600),'horizon_hours':horizon,
        'exit_identity':'OFFLINE_TP1_BE_TIME_CAP_V1','expires_at':180000,'version':1}
    token={'token_id':'synthetic-explicit-human-'+side.lower(),'signal_id':proposal['signal_id'],
        'proposal_hash':digest(proposal),'proposal_version':1,'quantity':'0.01','issued_at':60002,
        'expires_at':160000,'approved':True,'issuer':'TRUSTED_HUMAN_FIXTURE'}
    order=digest([digest(proposal),'SIMULATED_ENTRY'])
    actions=[]
    def action(kind,at,payload=None,id=None):
        actions.append({'id':id or kind+'-'+str(at),'kind':kind,'at':at,'payload':payload or {}})
    action('PROPOSE',60000,proposal)
    action('ANALYZE',60001,{'schema_version':1,'signal_id':proposal['signal_id'],'proposal_hash':digest(proposal),
        'source_hash':digest(first),'as_of':60000,'summary':'Offline mocked descriptive risk analysis; no trading authority','risk':'DESCRIPTIVE_ONLY'})
    action('APPROVE',60002,{'token_id':token['token_id']})
    action('PLACE',60003)
    action('FILL_ENTRY',60004,{'fill_id':'entry1'})
    action('ACK',120004,{'ack_id':'ack-entry','order_id':order,'fill_id':'entry1'})
    action('TP1',360*60000+59999,{'fill_id':'partial1'})
    action('FUNDING',360*60000+60001,{'settlement_id':'funding-before-partial-ACK','settlement_at':360*60000+60001,'rate_fraction':'0.0001'})
    action('ACK',361*60000+59999,{'ack_id':'ack-partial','order_id':order,'fill_id':'partial1'})
    action('UPDATE_STOP',362*60000+59999)
    action('FUNDING',480*60000,{'settlement_id':'funding-positive','settlement_at':480*60000,'rate_fraction':'0.0001'})
    action('FUNDING',600*60000,{'settlement_id':'funding-negative','settlement_at':600*60000,'rate_fraction':'-0.0002'})
    close_index=720 if exit_kind in ('STOP','CLOSE') else horizon*60+1
    close_at=close_index*60000+59999
    action(exit_kind,close_at,{'fill_id':'final1'})
    action('ACK',close_at+60000,{'ack_id':'ack-final','order_id':order,'fill_id':'final1'})
    bars=max(1441,close_index+3)
    events=[{'id':'BAR-'+str(i),'kind':'BAR','at':i*60000+59999,'payload':bar(i,side,exit_kind=exit_kind)} for i in range(bars)]
    events.extend(actions)
    # BAR at close precedes actions using the newly completed receipt.
    events.sort(key=lambda e:(e['at'],0 if e['kind']=='BAR' else 1))
    return {'schema_version':1,'fixture_name':'synthetic-'+side.lower()+'-'+str(horizon)+'h-'+exit_kind,
        'synthetic_only':True,'scenario_hours':24,'ACK_tail_minutes':max(0,bars-1441),
        'trusted_approvals':[token],'events':events}
