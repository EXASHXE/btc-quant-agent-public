"""Verify sealed code/reports, optionally original read-only inputs. No writes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--original-inputs', action='store_true')
    args = parser.parse_args()
    failures, count = [], 0
    for kind in ('code', 'report'):
        path = ROOT/'audit'/f'{kind}_manifest.json'
        if not path.exists() and kind == 'report':
            continue  # Public code packet has a code manifest only.
        for row in json.loads(path.read_text())['files']:
            target=ROOT/row['path']
            count += 1
            if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != row['sha256']:
                failures.append(row['path'])
    if args.original_inputs:
        for row in json.loads((ROOT/'D0_BASELINE_AND_PRESERVATION.json').read_text())['inputs']:
            target=ROOT.parent/row['path']
            count += 1
            if (not target.is_file() or target.stat().st_mtime_ns != row['mtime_ns']
                    or hashlib.sha256(target.read_bytes()).hexdigest() != row['sha256']):
                failures.append(row['path'])
    print(json.dumps({'status':'PASS' if not failures else 'FAIL', 'verified':count,'failures':failures}))
    return int(bool(failures))


if __name__=='__main__':
    raise SystemExit(main())
