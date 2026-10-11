"""Read-only monthly authority and inherited implementation invariants."""
from __future__ import annotations

from unittest.mock import Mock

import pytest

from scripts.strategy_research.g2_btc_two_lead_mark_gap_r31 import gaps, monthly, run


def test_exact_gap_days_and_old_two_configs():
    assert len(gaps.ALLOWED_DAYS)==8
    assert set(run.inherited.IDS)=={'W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H','W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H'}


def test_old_output_destination_redirected_only_in_memory(tmp_path,monkeypatch):
    old=run.inherited.SCRATCH
    monkeypatch.setattr(run,'SCRATCH',tmp_path)
    routine=Mock(return_value={})
    monkeypatch.setattr(run.inherited,'study',routine)
    result=run.full_study([],{}, {}, 'invented',{})
    assert result['terminal']=='R31_TWO_LEAD_OBSERVED_FUNDING_MARK_COMPLETE_DEVELOPMENT_ONLY'
    assert run.inherited.SCRATCH==old


def test_symlink_monthly_cache_rejected_without_target_access(tmp_path):
    target=tmp_path/'source';target.symlink_to(tmp_path/'forbidden-target')
    with pytest.raises(ValueError,match='within'):
        monthly.guard_file(target,tmp_path)


def test_own_gap_cache_path_guard(tmp_path,monkeypatch):
    monkeypatch.setattr(gaps,'SCRATCH',tmp_path)
    symlink=tmp_path/'2021-07-01';symlink.symlink_to(tmp_path/'do-not-access')
    with pytest.raises(ValueError,match='symlink'):
        gaps._guard_cache_path(symlink/'invented.zip')


def test_redirect_rejected_before_following_new_url():
    request=gaps.urllib.request.Request('https://data.binance.vision/exact')
    with pytest.raises(gaps.urllib.error.HTTPError):
        gaps._NoRedirect().redirect_request(request,None,302,'redirect',{},'https://elsewhere.invalid/2026')
