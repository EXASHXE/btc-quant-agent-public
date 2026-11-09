"""Exact public code allowlist, deterministic packet, no repository mutation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from build_release import deterministic_zip

ROOT=Path(__file__).resolve().parents[1]


def main():
    files=[]
    for group in ('src','tests','contracts','fixtures','configs','inputs'):
        files += [p for p in (ROOT/group).rglob('*') if p.is_file() and p.suffix in {'.py','.json','.jsonl','.yaml'}
                  and '__pycache__' not in p.parts and '.egg-info' not in p.as_posix()]
    files += [ROOT/p for p in ('pyproject.toml','frozen_protocol.json','README_OPERATOR.md','.gitignore',
                               'audit/original_verifier.json')]
    tools=('offline_pytest.py','rc.py','rc_benchmark.py','swing_benchmark.py','make_fixtures.py',
           'build_release.py','operator_acceptance.py','verify_release.py','package_candidate.py')
    files += [ROOT/'tools'/name for name in tools]
    files=sorted(set(files))
    rows=[]
    for p in files:
        raw=p.read_bytes()
        if p.is_symlink() or any(line in {b'-----BEGIN PRIVATE KEY-----', b'-----BEGIN OPENSSH PRIVATE KEY-----'} for line in raw.splitlines()):
            raise ValueError('PUBLIC_SECRET_OR_SYMLINK_REJECTED:'+str(p))
        rows.append({'path':str(p.relative_to(ROOT)), 'sha256':hashlib.sha256(raw).hexdigest(), 'bytes':len(raw)})
    manifest={'schema':'D_EXACT_PUBLIC_CODE_MANIFEST_V1','files':rows,'file_count':len(rows),
              'content_root_sha256':hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
              'exclusions':['Original workspaces, protected research and holdout','Owner/auditor trust, signatures and private grants',
                            'Native raw evidence','Runtime reports, SQLite, HTML and large generated datasets',
                            'Dependency binaries, virtualenvs, caches and build output'],
              'fixtures':'Finite explicitly synthetic offline QA fixtures only'}
    (ROOT/'audit/code_manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    packet={str(p.relative_to(ROOT)):p.read_bytes() for p in files}
    packet['audit/code_manifest.json']=(ROOT/'audit/code_manifest.json').read_bytes()
    output=ROOT/'release'
    deterministic_zip(output/'quant-v070-code-candidate.zip',packet)
    deterministic_zip(output/'quant-v070-code-candidate-repeat.zip',packet)
    assert (output/'quant-v070-code-candidate.zip').read_bytes()==(output/'quant-v070-code-candidate-repeat.zip').read_bytes()
    materialized=output/'public_source'
    if materialized.exists():
        raise ValueError('PUBLIC_MATERIALIZATION_ALREADY_EXISTS')
    materialized.mkdir()
    for name,raw in packet.items():
        dest=materialized/name
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(raw)
    # Detached patch set is reviewable without the local original A/B/C inputs.
    status={'status':'CODE_PACKET_READY','public_prefix':'releases/quant-v070-offline-rc',
            'public_source_files':len(packet),'source_root_sha256':manifest['content_root_sha256'],
            'code_manifest_sha256':hashlib.sha256((ROOT/'audit/code_manifest.json').read_bytes()).hexdigest(),
            'packet':'release/quant-v070-code-candidate.zip',
            'packet_sha256':hashlib.sha256((output/'quant-v070-code-candidate.zip').read_bytes()).hexdigest(),
            'repeat_packet_byte_identical':True, 'materialization':'release/public_source',
            'allowlist':rows,'private_or_native_payloads':0}
    (ROOT/'D4_CODE_RELEASE_MANIFEST.json').write_text(json.dumps(status,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:v for k,v in status.items() if k!='allowlist'}))


if __name__=='__main__':
    main()
