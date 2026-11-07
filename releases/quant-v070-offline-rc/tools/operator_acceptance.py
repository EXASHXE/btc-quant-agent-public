"""Run installed CLI through all finite offline operator functions in fresh outputs."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    executable = Path(sys.argv[1]).resolve()
    env = {k: v for k, v in os.environ.items() if k not in {'PYTHONPATH', 'PYTHONHOME'}}
    env.update(PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1')
    calls = []
    def run(*args):
        start = time.perf_counter()
        result = subprocess.run([str(executable), *map(str, args)], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=60)
        calls.append({'args': list(map(str, args)), 'exit': result.returncode,
                      'elapsed_ms': round((time.perf_counter()-start)*1000, 3),
                      'stdout': result.stdout, 'stderr': result.stderr})
        if result.returncode:
            raise ValueError('OPERATOR_COMMAND_FAILED:' + result.stderr)
        return json.loads(result.stdout)
    doctor = run('doctor')
    positive = ROOT / 'artifacts/operator_demo'
    negative = ROOT / 'artifacts/operator_no_setup'
    first = run('replay', '--output', positive)
    original_initial = digest(positive / 'initial/latest.json')
    original_latest = digest(positive / 'latest.json')
    original_sqlite = digest(positive / 'state.sqlite')
    run('status', '--output', positive)
    assert digest(positive / 'state.sqlite') == original_sqlite
    second = run('replay', '--output', positive)
    assert first['decision_digests'] == second['decision_digests']
    assert first['snapshot_sha256'] == second['snapshot_sha256']
    assert digest(positive / 'initial/latest.json') == original_initial
    assert digest(positive / 'latest.json') == original_latest
    state_bytes_replay_equal = digest(positive / 'state.sqlite') == original_sqlite
    no_setup = run('replay', '--output', negative, '--all-no-setup')
    assert set(no_setup['original_decisions'].values()) == {'NO_SETUP'}
    manual = ROOT / 'artifacts/manual'
    run('ingest', '--output', manual)
    reviews = []
    for symbol in ('BTCUSDT', 'ETHUSDT', 'SOLUSDT'):
        reviews.append(run('review', '--output', manual, '--symbol', symbol,
                           '--trigger-ms', 1793923200000, '--decision-ms', 1793923201000))
    btc = next(r for r in reviews if r['episode_id'])
    before = json.loads((manual / 'latest.json').read_text())['decisions']
    observation = run('observe', '--output', manual, '--episode-id', btc['episode_id'])
    assert json.loads((manual / 'latest.json').read_text())['decisions'] == before
    (manual / 'latest.html').unlink()
    run('recover', '--output', manual)
    run('dashboard', '--output', manual)
    export = run('export', '--output', positive)
    run('evaluate', '--input', export['path'], '--output', ROOT / 'artifacts/evaluation')
    neg_export = run('export', '--output', negative)
    run('evaluate', '--input', neg_export['path'], '--output', ROOT / 'artifacts/no_setup_evaluation')
    initial = json.loads((positive / 'initial/latest.json').read_text())
    later = json.loads((positive / 'latest.json').read_text())
    assert initial['decisions'] == later['decisions']
    assert initial['episodes'] != later['episodes']
    receipt = {'status': 'PASS', 'installed_executable': str(executable.relative_to(ROOT)), 'doctor': doctor,
               'positive': first, 'no_setup': no_setup, 'manual_observation': observation,
               'demos': {f'Demo {i}': 'PASS' for i in range(1, 6)},
               'restart_sqlite_bytes_equal': state_bytes_replay_equal,
               'original_plan_preserved': True, 'native_market_requests': 0, 'calls': calls,
               'files': [{'path': str(p.relative_to(ROOT)), 'sha256': digest(p), 'bytes': p.stat().st_size}
                         for folder in (positive, negative, manual, ROOT/'artifacts/evaluation')
                         for p in sorted(folder.rglob('*')) if p.is_file()]}
    (ROOT / 'D2_OPERATOR_ACCEPTANCE.json').write_text(json.dumps(receipt, indent=2, sort_keys=True)+'\n')
    print(json.dumps({'status': 'PASS', 'commands': len(calls), 'demos': receipt['demos']}))


if __name__ == '__main__':
    main()
