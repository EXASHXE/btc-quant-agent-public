"""Bounded identity and future rate/schema falsifiers before real access."""
from __future__ import annotations

import json
from decimal import Decimal

import pytest

from scripts.strategy_research.g2_btc_two_lead_funding_mark_r3.run import IDS
from scripts.strategy_research.g2_btc_two_lead_funding_mark_r3.sources import (
    month_bounds,
    parse_funding_api_pages,
    verify_funding_continuity,
)
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.reanalysis_r2_run import verify_identity


def test_exact_two_original_configs_and_no_new_signal():
    candidates,_=verify_identity()
    fixed=[c for c in candidates if c['id'] in IDS]
    assert len(fixed)==2
    assert all(c['horizon_hours']==12 for c in fixed)
    assert fixed[0]['stop_atr_multiplier']==2
    assert fixed[1]['stop_atr_multiplier']==1.8


def test_api_public_schema_optional_regular_and_source_mark():
    start,end=month_bounds(2021,2)
    raw=json.dumps([{'symbol':'BTCUSDT','fundingTime':start,'fundingRate':'-0.0001','markPrice':'100','rateType':'Regular'}]).encode()
    events,_=parse_funding_api_pages([(start,end-1,raw)],2021,2)
    assert Decimal(events[0]['rate'])==-Decimal('0.0001')
    assert events[0]['mark_price_source_proven']


def test_special_funding_type_is_not_silently_regular():
    start,end=month_bounds(2021,2)
    raw=json.dumps([{'symbol':'BTCUSDT','fundingTime':start,'fundingRate':'0.0001','markPrice':'100','rateType':'Special'}]).encode()
    with pytest.raises(ValueError,match='schema'):
        parse_funding_api_pages([(start,end-1,raw)],2021,2)


def test_observed_settlement_millisecond_jitter_not_missing_cadence():
    start,end=month_bounds(2021,2)
    events=[{'settlement_at':t+5,'rate':'0.0001','interval_hours':'8'} for t in range(start,end,8*3600000)]
    assert verify_funding_continuity(events,2021,2)['coverage']=='PROVEN_BY_OBSERVED_INTERVALS'


def test_api_no_event_day_unknown_even_with_full_transport():
    start,_=month_bounds(2021,2)
    events=[{'settlement_at':start,'rate':'0.0001','interval_hours':None,'api_exhausted_bounded_query':True}]
    with pytest.raises(ValueError,match='UNKNOWN'):
        verify_funding_continuity(events,2021,2)


def test_api_exhausted_query_daily_support_no_assumed_8h():
    start,end=month_bounds(2021,2)
    events=[{'settlement_at':t,'rate':'-0.0001','interval_hours':None,'api_exhausted_bounded_query':True}
            for t in range(start,end,86400000)]
    assert 'NO_ASSUMED_CADENCE' in verify_funding_continuity(events,2021,2)['method']


def test_download_sidecar_symlink_rejected_before_curl(tmp_path,monkeypatch):
    from scripts.strategy_research.g2_btc_two_lead_funding_mark_r3 import sources
    monkeypatch.setattr(sources,'SCRATCH',tmp_path)
    destination=tmp_path/'invented.zip'
    (tmp_path/'invented.zip.partial').symlink_to(tmp_path/'do-not-open')
    monkeypatch.setattr(sources.subprocess,'run',lambda *a,**kw:pytest.fail('must reject beforecurl'))
    with pytest.raises(ValueError,match='sidecar'):
        sources._fetch(sources.VISION+'invented.zip',destination,max_bytes=4096,allowed_prefix=sources.VISION)


def test_funding_adjusted_net_R_and_side_risk_summary():
    import numpy as np

    from scripts.strategy_research.g2_btc_two_lead_funding_mark_r3.run import metrics
    stamp=1612137600000
    trade={'side':1,'entry_at':stamp+60000,'exit_at':stamp+120000,'quantity':1.,'entry_notional':100.,
        'effective_entry':100.,'stop':90.,'net_usdt':5.,'net_bps':500.,'gross_usdt':10.,'gross_bps':1000.,
        'funding_cash_usdt':'-1','funding_settlements':[{'signed_cash_usdt':'-1'}],
        'duration_minutes':1.,'exit_reason':'TIME_CAP'}
    curve=np.array([[stamp+59999,1000.],[stamp+119999,990.],[stamp+179999,1004.]])
    result=metrics([trade],curve,'BASE')
    assert result['mean_net_R']==pytest.approx(.4)
    assert result['side']['LONG']['mean_net_bps']==pytest.approx(400)
    assert result['side']['SHORT']['n']==0
