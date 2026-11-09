"""One Owner-authorized foreground trial; stop only timesyncd, rollback on failure."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from analyze import analyze
from btc_quant_agent.platform.live.operational_clock import control_check

children=[]
state={'Owner_authorization':'Explicit Owner user message approving one stop,600s+120s Windows-QPC measurements,672 regressions,conditional start rollback; successful trial may remain stopped; no disable/mask or other configuration/network actions','changed':False,'rollback':'NOT_NEEDED','status':'STARTING','Binance_requests':0,'account_order_trade_requests':0}

def save():
    (ROOT/'audit/P2_TRIAL_STATE.json').write_text(json.dumps(state,indent=2,sort_keys=True)+'\n')

def unit():
    p=subprocess.run(['systemctl','show','systemd-timesyncd.service','--property=ActiveState,SubState,UnitFileState,MainPID'],capture_output=True,text=True,timeout=10,check=True)
    return dict(line.split('=',1) for line in p.stdout.splitlines() if '=' in line)

def config():
    values={}
    for name in ['/etc/wsl.conf','/etc/systemd/timesyncd.conf','/proc/cmdline','/sys/devices/system/clocksource/clocksource0/current_clocksource','/sys/module/hv_utils/parameters/timesync_implicit','/proc/sys/kernel/random/boot_id']:
        values[name]=hashlib.sha256(Path(name).read_bytes()).hexdigest()
    for folder in ['/etc/systemd/timesyncd.conf.d','/run/systemd/timesyncd.conf.d','/usr/lib/systemd/timesyncd.conf.d']:
        for p in Path(folder).glob('*.conf'):values[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    return values

def terminate():
    for p in children:
        if p.poll() is None:
            os.killpg(p.pid,signal.SIGTERM)
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=5)

def interrupted(signum,frame):raise RuntimeError('OWNER_TRIAL_INTERRUPTED_SIGNAL_'+str(signum))
for sig in [signal.SIGTERM,signal.SIGINT,signal.SIGHUP]:signal.signal(sig,interrupted)

def start(command,log,cwd=ROOT):
    stream=(ROOT/'audit'/log).open('w')
    p=subprocess.Popen(command,cwd=cwd,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
    stream.close();children.append(p);return p

def check_counter(s,boot):
    return {'boot_id':boot,'mono_before_ms':s['mono_before_ns']//1000000,'mono_after_ms':s['mono_after_ns']//1000000,'wall_ms':s['realtime_ns']//1000000,'raw_ms':s['raw_ns']//1000000,'boottime_ms':s['boottime_ns']//1000000,'control_end_ms':s['mono_after_ns']//1000000}

try:
    state['before']=unit();state['config_before']=config();save()
    assert state['before']['ActiveState']=='active' and state['before']['UnitFileState']=='enabled','PRECONDITION_CHANGED'
    # Mark attempted before invocation so an interrupted stop always triggers rollback.
    state['changed']=True;state['stop_attempted']=True;save()
    stopped=subprocess.run(['sudo','-n','systemctl','stop','systemd-timesyncd.service'],capture_output=True,text=True,timeout=20)
    state['stop_receipt']={'exit':stopped.returncode,'stdout':stopped.stdout,'stderr':stopped.stderr};save();stopped.check_returncode()
    state['after_stop']=unit();assert state['after_stop']['ActiveState']=='inactive' and state['after_stop']['UnitFileState']=='enabled'
    assert config()==state['config_before'],'UNEXPECTED_CONFIGURATION_CHANGE'
    state['status']='MEASURING_AND_OFFLINE_REGRESSIONS';save()
    regression=start([sys.executable,'-B','tools/run_o_tests.py'],'P2_REGRESSION_RUNNER.log',ROOT/'regression_input')
    for seconds,name in [(600,'P_POSTCHANGE_600S'),(120,'P_POSTCHANGE_SESSION_120S')]:
        child=start([sys.executable,'-B','tools/windows_elapsed.py','--seconds',str(seconds),'--hz','5','--phase','POST_CHANGE','--name',name],name+'.log')
        path=ROOT/'audit'/(name+'.jsonl');position=0;anchor=prior=None
        deadline=time.monotonic()+seconds*1.5+30
        while child.poll() is None:
            if regression.poll() not in (None,0):raise RuntimeError('OFFLINE_REGRESSION_FAILED')
            if time.monotonic()>deadline:raise RuntimeError('FINITE_MEASUREMENT_DEADLINE')
            if path.exists():
                with path.open() as f:
                    f.seek(position)
                    while True:
                        startpos=f.tell();line=f.readline()
                        if not line or not line.endswith('\n'):f.seek(startpos);break
                        row=json.loads(line)
                        for side in ['before','after']:
                            stamp=check_counter(row[side],row['boot_id'])
                            if prior is not None:
                                control_check(prior,stamp);control_check(anchor,stamp)
                                delta=(stamp['wall_ms']-stamp['mono_before_ms'])-(prior['wall_ms']-prior['mono_before_ms'])
                                assert abs(delta)<=50+5+5,'POSTCHANGE_WALL_STEP'
                            if anchor is None:anchor=stamp
                            prior=stamp
                    position=f.tell()
            time.sleep(.5)
        assert child.returncode==0,'MEASUREMENT_WORKER_FAILED'
        result=analyze([json.loads(x) for x in path.read_text().splitlines()])
        meta=json.loads(path.with_suffix('.json').read_text());assert meta['post_change'] and meta['Windows_elapsed_seconds']>=seconds and meta['worker_closed']
        assert result['control_clock_criteria_pass'] and not result['Linux_wall_steps'],'POSTCHANGE_CLOCK_FAILED'
        result['capture_phase']='POST_CHANGE';result['requested_Windows_elapsed_seconds']=seconds
        path.with_suffix('.analysis.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
        state[name]={'samples':result['paired_reference_samples'],'control_criteria_pass':True,'Windows_elapsed_seconds':meta['Windows_elapsed_seconds']};save()
    regression.wait(timeout=900);assert regression.returncode==0,'OFFLINE_REGRESSION_FAILED'
    state['after']=unit();state['config_after']=config();assert state['config_after']==state['config_before']
    assert state['after']['ActiveState']=='inactive' and state['after']['UnitFileState']=='enabled'
    state.update(status='MEASURED_WINDOWS_AND_REGRESSIONS_PASS_PENDING_CONTROLLER',rollback='NOT_TRIGGERED_OWNER_ALLOWS_TEMPORARY_STOPPED',HOST_CLOCK_QUALIFIED='NOT_SELF_DECLARED',Windows_UTC_qualified=False);save()
except BaseException as e:
    state.update(status='FAILED_OR_INTERRUPTED',error=str(e));terminate()
    if state['changed']:
        try:
            p=subprocess.run(['sudo','-n','systemctl','start','systemd-timesyncd.service'],capture_output=True,text=True,timeout=20)
            state['rollback_receipt']={'exit':p.returncode,'stdout':p.stdout,'stderr':p.stderr};state['after_rollback']=unit()
            state['rollback']='PASS_ACTIVE_ENABLED' if p.returncode==0 and state['after_rollback']['ActiveState']=='active' and state['after_rollback']['UnitFileState']=='enabled' else 'FAILED_OWNER_ACTION_REQUIRED'
        except BaseException as err:state['rollback']='FAILED_OWNER_ACTION_REQUIRED';state['rollback_error']=str(err)
    save();raise
finally:
    terminate();save()
print(json.dumps(state))
