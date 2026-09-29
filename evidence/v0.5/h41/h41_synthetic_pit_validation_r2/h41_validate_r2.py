import json
import math
import subprocess
from pathlib import Path
import numpy as np
from btc_quant_agent.h41.inference import run_frozen_joint_inference, run_joint_bootstrap_studentized

COMMIT='c0059b7bd26beb90096792a5232e5ad58e75580c'
PATH='scripts/v0.5/h41_r2_inference_validation_r1.py'
blob=subprocess.check_output(['git','-C',str(Path(__file__).resolve().parents[4]),'rev-parse',f'{COMMIT}:{PATH}']).decode().strip()
assert blob=='ec8f975a45f7ff6c73beb238e4711aae62bdbb3d',blob
source=subprocess.check_output(['git','-C',str(Path(__file__).resolve().parents[4]),'show',f'{COMMIT}:{PATH}']).decode()
namespace={'__name__':'h41_accepted_r2_reference'}
exec(compile(source,f'<git:{COMMIT}:{PATH}>','exec'),namespace)
reference=namespace['run_joint_bootstrap_studentized']

cases={}
rng=np.random.default_rng(9001)
T=2184
K=20
factor=rng.normal(0,.003,T)
noise=rng.normal(0,.002,(K,T))
for name,prob in [('ordinary',.25),('unequal',np.linspace(.04,.45,K)[:,None]),('sparse_zero',.055),('correlated_bundle',.18)]:
    draw=rng.random((K,T))
    a=(draw<prob).astype(np.float64)
    if name=='sparse_zero':a[0]=0;a[1,:]=0;a[1,::17]=1
    y=(factor[None,:]+noise+.0005) if name=='correlated_bundle' else (noise+.0004)
    if name=='unequal':y[:,0:120]+=.002
    z=a*y
    seed={'ordinary':41,'unequal':42,'sparse_zero':43,'correlated_bundle':44}[name]
    actual=run_frozen_joint_inference(z,a,np.random.default_rng(seed))
    expected=reference(z,a,120,10000,np.random.default_rng(seed))
    for left,right in zip(actual,expected):
        np.testing.assert_array_equal(left,right)
    if name=='sparse_zero':assert np.isneginf(actual[3][0])
    if name=='unequal':
        valid=1
        zcs=np.pad(np.cumsum(z[valid]),(1,0));acs=np.pad(np.cumsum(a[valid]),(1,0))
        zb=zcs[120:]-zcs[:-120];ab=acs[120:]-acs[:-120]
        center=float(zb.sum()/ab.sum()); mu=float(z[valid].sum()/a[valid].sum())
        assert center!=mu
    cases[name]={'exact_mu':True,'exact_se':True,'exact_c95':True,'exact_lcb':True,'seed':seed,'L':120,'B':10000,'supported_coordinates':int((a.sum(axis=1)>=60).sum())}
    if name=='correlated_bundle':
        order=np.arange(K)[::-1]
        perm=run_frozen_joint_inference(z[order],a[order],np.random.default_rng(seed))
        for index in (0,1,3):np.testing.assert_array_equal(actual[index][order],perm[index])
        assert actual[2]==perm[2]
        cases[name]['coordinate_permutation_exact']=True
result={'reference_commit':COMMIT,'reference_blob':blob,'cases':cases,'center_differs_from_mu':True,'all_exact':True}
Path(__file__).with_name('h41_r2_result.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
print(json.dumps(result,sort_keys=True))
