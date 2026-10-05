import json, os, pathlib, signal, subprocess, sys, time
src=pathlib.Path('/tmp/b5-r8-independent-source')
evd=pathlib.Path('/tmp/b5-r8-independent-publication/evidence/v0.5.5/live_v1/B5_R8_INDEPENDENT_EXACT_SHA_REVALIDATION/regression')
commands=[
'python -m compileall -q src tests',
'git diff --check',
'ruff check .',
'mypy src',
'pytest -q tests/test_live_v1_position_outbox_r8.py',
'pytest -q tests/test_live_v1_position_outbox_r7.py',
'pytest -q tests/test_live_v1_*_r6.py',
'pytest -q tests/test_live_v1_*_r5.py',
'pytest -q tests/test_live_v1_*_r4.py tests/test_live_v1_*_r3.py',
'pytest -q tests/test_live_v1_*.py',
'pytest -q tests/test_tactical_*.py',
'pytest -q tests/test_v050_r02_orchestration_guards.py',
'pytest -q',
]
results=[]
env=os.environ.copy(); env['PATH']='/root/miniconda3/bin:'+env.get('PATH',''); env['PYTHONPATH']='/tmp/b5-r8-independent-source/src:/tmp';
for i,cmd in enumerate(commands,1):
    log=evd/f'{i:02d}.log'; stall=evd/f'{i:02d}.stall.txt'
    e=env.copy(); e['B5R8_STALL_FILE']=str(stall)
    if cmd.startswith('pytest '): e['PYTEST_PLUGINS']='b5r8_gatewatch'
    start=time.monotonic(); timed=False
    with open(log,'w') as f:
        p=subprocess.Popen(cmd,shell=True,cwd=src,env=e,stdout=f,stderr=subprocess.STDOUT,start_new_session=True,text=True)
        try: code=p.wait(timeout=120 if cmd.startswith('pytest ') else 600)
        except subprocess.TimeoutExpired:
            timed=True
            os.killpg(p.pid,signal.SIGTERM)
            try: p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid,signal.SIGKILL); p.wait()
            code=124
    elapsed=round(time.monotonic()-start,2)
    data={'index':i,'command':cmd,'exit_code':code,'elapsed_seconds':elapsed,'timed_out':timed,'log':str(log),'stall_file':str(stall) if stall.exists() else None}
    results.append(data)
    print(json.dumps(data),flush=True)
    if timed:
        print('STALLED_GATE '+cmd,flush=True)
        # continue mandatory gate sequence; stalled process group was terminated by this runner
summary={'source':str(src),'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=src,text=True).strip(),'commands':results}
(evd/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
