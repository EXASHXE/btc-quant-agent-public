import hashlib
import json
import tempfile
import zipfile
from decimal import Decimal
from pathlib import Path
from btc_quant_agent.h41.science import HOUR_MS
from btc_quant_agent.h41.source import EconomicBar, SynchronizedSource, load_synthetic_archive, projection_sha256

START = 1_609_459_200_000

def row(t, *, high='102', low='99', volume='1', close_t=None):
    return f'{t},100,{high},{low},100,{volume},{t+HOUR_MS-1 if close_t is None else close_t},100,5,0.5,50,0'

def archive(root, rows, symbol='BTCUSDT', month='2021-01'):
    name=f'{symbol}-1h-{month}'
    path=root/f'{name}.zip'
    with zipfile.ZipFile(path,'w') as z:
        z.writestr(f'{name}.csv','\n'.join(rows)+'\n')
    return path, hashlib.sha256(path.read_bytes()).hexdigest()

def rejects(label, root, rows, **kwargs):
    path,digest=archive(root,rows,**kwargs)
    try:load_synthetic_archive(path,kwargs.get('symbol','BTCUSDT'),kwargs.get('month','2021-01'),digest)
    except (ValueError, zipfile.BadZipFile) as e:return type(e).__name__
    raise AssertionError(label+' accepted')

results={}
with tempfile.TemporaryDirectory() as td:
    root=Path(td)
    path,digest=archive(root,[row(START),row(START+HOUR_MS)])
    parsed=load_synthetic_archive(path,'BTCUSDT','2021-01',digest)
    assert parsed.archive_sha256==digest and parsed.projection_sha256==projection_sha256((parsed,))
    assert len(parsed.bars[0].projection())==14
    results['same_buffer_and_projection_replay']=True
    results['duplicate']=rejects('duplicate',root,[row(START),row(START)])
    results['gap']=rejects('gap',root,[row(START),row(START+2*HOUR_MS)])
    results['out_of_order']=rejects('out of order',root,[row(START+HOUR_MS),row(START)])
    results['unaligned']=rejects('unaligned',root,[row(START+1)])
    results['wrong_close_time']=rejects('close time',root,[row(START,close_t=0)])
    results['invalid_ohlc']=rejects('OHLC',root,[row(START,high='98')])
    results['invalid_volume']=rejects('volume',root,[row(START,volume='-1')])
    path,digest=archive(root,[row(START)])
    try:load_synthetic_archive(path,'ETHUSDT','2021-01',digest)
    except ValueError:results['wrong_symbol']='ValueError'
    else:raise AssertionError('wrong symbol accepted')
    results['wrong_month']=rejects('month',root,[row(START)],month='2021-02')
    try:load_synthetic_archive(path,'BTCUSDT','2021-01','0'*64)
    except ValueError:results['wrong_checksum']='ValueError'
    else:raise AssertionError('wrong checksum accepted')
    path.write_bytes(b'bad zip')
    try:load_synthetic_archive(path,'BTCUSDT','2021-01',hashlib.sha256(path.read_bytes()).hexdigest())
    except zipfile.BadZipFile:results['corrupt_zip']='BadZipFile'
    else:raise AssertionError('corrupt ZIP accepted')
    path,digest=archive(root,[row(START)])
    path.write_bytes(path.read_bytes()+b'mutation')
    try:load_synthetic_archive(path,'BTCUSDT','2021-01',digest)
    except ValueError:results['source_mutation']='ValueError'
    else:raise AssertionError('mutated source accepted')
    def economic(symbol,t):
        return EconomicBar(symbol,t,t+HOUR_MS-1,Decimal(100),Decimal(102),Decimal(99),Decimal(100),Decimal(1),Decimal(100),5,Decimal('.5'),Decimal(50))
    try:SynchronizedSource((economic('BTCUSDT',START),),(economic('ETHUSDT',START+HOUR_MS),))
    except ValueError:results['btc_eth_desync']='ValueError'
    else:raise AssertionError('desync accepted')
output={'synthetic_only':True,'cases':results,'all_fail_closed':True}
Path(__file__).with_name('h41_source_adversarial_result.json').write_text(json.dumps(output,sort_keys=True,indent=2)+'\n')
print(json.dumps(output,sort_keys=True))
