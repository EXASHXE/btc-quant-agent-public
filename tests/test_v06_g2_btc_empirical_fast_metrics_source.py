"""Synthetic source corruption and finite inferential gate witnesses."""
import hashlib
import io
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.strategy_research.g2_btc_empirical_fast_r1 import metrics, sources


def toy_archive(name='BTCUSDT-1m-2021-04.csv',row='1617235200000,100,101,99,100,1,1617235259999,100,1,1,100,0\n'):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as z:
        z.writestr(name,row)
    return stream.getvalue()


def test_checksum_exact_filename_and_body():
    raw=toy_archive(); name='BTCUSDT-1m-2021-04.zip'; h=hashlib.sha256(raw).hexdigest()
    assert sources.validate_zip_checksum(raw,h+'  '+name,name)==h
    for wrong in [h+' other.zip','0'*64+' '+name,h]:
        with pytest.raises(ValueError):
            sources.validate_zip_checksum(raw,wrong,name)


@pytest.mark.parametrize('name,row,error',[
    ('../../elsewhere.csv','x','member'),
    ('BTCUSDT-1m-2021-04.csv','1,2\n','field count'),
    ('BTCUSDT-1m-2021-04.csv','1617235200000,100,99,101,100,1,1617235259999,100,1,1,100,0\n','OHLC'),
    ('BTCUSDT-1m-2021-04.csv','1617235200000,100,101,99,100,1,1617235260000,100,1,1,100,0\n','clock'),
    ('BTCUSDT-1m-2021-04.csv','1617235200000,100,101,99,nan,1,1617235259999,100,1,1,100,0\n','nonfinite'),
    ('BTCUSDT-1m-2021-04.csv','1617235200000,100,101,99,100,1,1617235259999,100,1,1,100,0\n','row count'),
])
def test_source_fails_closed(name,row,error):
    with pytest.raises(ValueError,match=error):
        sources.parse_month(toy_archive(name,row),2021,4)


def test_protected_year_rejected_before_zip_body():
    with pytest.raises(ValueError,match='outside'):
        sources.parse_month(b'not zip',2026,4)


def test_future_network_source_rejected_before_call(tmp_path):
    with pytest.raises(ValueError,match='unexpected network'):
        sources.fetch('https://example.invalid/2026.zip',tmp_path/'no-read')


def test_funding_boundary_clocks_and_unknown_hourly():
    hour=3600000
    assert metrics.possible_settlements(8*hour,12*hour,8)==[8*hour]
    assert metrics.possible_settlements(8*hour,12*hour,1)==[h*hour for h in range(8,13)]
    assert metrics.possible_settlements(8*hour+16000,9*hour-16000,8)==[]


def test_zero_trade_is_undefined_not_no_edge():
    f=[{'id':'x','start_ms':0,'end_ms':28*metrics.DAY}]
    cfg={'seed':17012025,'bootstrap_resamples':10000}
    r=metrics.blocked_ci([],f,cfg)
    assert r['equal_era_net_bps'] is None and r['adjusted_net_LCB_bps'] is None
    assert r['status']=='INSUFFICIENT_SUPPORT_ZERO_TRADE_ERA'


def test_shared_calendar_bootstrap_is_deterministic_and_equal_era():
    cfg={'seed':17012025,'bootstrap_resamples':10000,'ci_interval':[.025,.975],
         'one_sided_lower_quantile':.05/24,'comparisons':24}
    folds=[{'id':str(i),'start_ms':0,'end_ms':28*metrics.DAY} for i in range(3)]
    trades=[{'fold':str(i),'entry_at':j*metrics.DAY,'net_bps':10*(i+1),
             'incremental_vs_balanced_bps':5} for i in range(3) for j in range(28)]
    a=metrics.blocked_ci(trades,folds,cfg)
    assert a==metrics.blocked_ci(trades,folds,cfg)
    assert a['equal_era_net_bps']==20 and a['adjusted_net_LCB_bps']==pytest.approx(20)
    assert a['adjusted_incremental_LCB_bps']==pytest.approx(5)


def test_drawdown_includes_starting_cash():
    assert metrics.drawdown([1000,900,950])==pytest.approx(10)
