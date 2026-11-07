"""Offline deterministic build and RECORD-verified installed dependency wheelhouse.

Dependency wheels are reconstructed host artifacts, not upstream wheels. Their
provenance and platform tags are recorded. Nothing is fetched from a registry.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import importlib.metadata as metadata
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def deterministic_zip(path, files):
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, raw)


def dependencies():
    queue = ['numpy', 'pandas', 'PyYAML', 'pydantic', 'cryptography', 'pytest']
    found = {}
    while queue:
        name = canonicalize_name(queue.pop())
        if name in found:
            continue
        dist = metadata.distribution(name)
        found[name] = dist
        for raw in dist.requires or []:
            req = Requirement(raw)
            if req.marker is None or req.marker.evaluate({'extra': ''}):
                if not req.specifier.contains(metadata.version(req.name)):
                    raise ValueError('INSTALLED_DEPENDENCY_CONFLICT:' + req.name)
                queue.append(req.name)
    return found


def rewheel(name, dist, directory):
    files = {}
    verified = 0
    for item in dist.files or []:
        relative = item.as_posix()
        if '..' in item.parts or item.suffix == '.pyc' or item.name in {'RECORD', 'INSTALLER', 'REQUESTED', 'direct_url.json'}:
            continue
        raw = dist.locate_file(item).read_bytes()
        if item.hash:
            expected = base64.urlsafe_b64encode(hashlib.new(item.hash.mode, raw).digest()).rstrip(b'=').decode()
            if expected != item.hash.value:
                raise ValueError('DEPENDENCY_RECORD_MISMATCH:' + name + ':' + relative)
            verified += 1
        else:
            raise ValueError('DEPENDENCY_FILE_WITHOUT_RECORD_HASH:' + relative)
        files[relative] = raw
    wheel_name = next(p for p in files if p.endswith('.dist-info/WHEEL'))
    from packaging.tags import sys_tags
    supported = {str(t) for t in sys_tags()}
    tag = next(line[5:] for line in files[wheel_name].decode().splitlines()
               if line.startswith('Tag: ') and line[5:] in supported)
    record_name = wheel_name.rsplit('/', 1)[0] + '/RECORD'
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer, lineterminator='\n')
    for path, raw in sorted(files.items()):
        writer.writerow([path, 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b'=').decode(), len(raw)])
    writer.writerow([record_name, '', ''])
    files[record_name] = buffer.getvalue().encode()
    path = directory / (name.replace('-', '_') + '-' + dist.version + '-' + tag + '.whl')
    deterministic_zip(path, files)
    return {'name': name, 'version': dist.version, 'path': str(path.relative_to(ROOT)),
            'sha256': sha(path.read_bytes()), 'verified_RECORD_files': verified,
            'origin': 'LOCAL_INSTALLED_DISTRIBUTION_RECORD_VERIFIED_RECONSTRUCTION', 'tag': tag}


def cached_wheel(name, version, directory):
    # Existing cached archive only; never a network fetch or use of a changed host binary.
    from packaging.tags import sys_tags
    compatible = {str(t) for t in sys_tags()}
    for path in (Path(os.environ.get('PIP_CACHE_DIR', str(Path.home() / '.cache/pip'))) / 'http-v2').rglob('*.body'):
        with path.open('rb') as stream:
            if stream.read(4) != b'PK\x03\x04':
                continue
        try:
            with zipfile.ZipFile(path) as archive:
                metadata_path = next((n for n in archive.namelist()
                                      if n.endswith('.dist-info/METADATA') and
                                      n.split('/')[0].lower() == (name.replace('-', '_') + '-' + version + '.dist-info').lower()), None)
                if metadata_path is None:
                    continue
                prefix = metadata_path.rsplit('/', 1)[0]
                wheel = archive.read(prefix + '/WHEEL').decode()
                tags = [line[5:] for line in wheel.splitlines() if line.startswith('Tag: ')]
                tag = next((t for t in tags if t in compatible), None)
                if tag is None:
                    continue
                count = 0
                for row in csv.reader(io.StringIO(archive.read(prefix + '/RECORD').decode())):
                    file, bound, size = row
                    if not bound:
                        if file != prefix + '/RECORD':
                            raise ValueError('CACHED_UNSIGNED_FILE')
                        continue
                    algorithm, expected = bound.split('=', 1)
                    raw = archive.read(file)
                    actual = base64.urlsafe_b64encode(hashlib.new(algorithm, raw).digest()).rstrip(b'=').decode()
                    if actual != expected or len(raw) != int(size):
                        raise ValueError('CACHED_RECORD_INVALID')
                    count += 1
                target = directory / (name.replace('-', '_') + '-' + version + '-' + tag + '.whl')
                target.write_bytes(path.read_bytes())
                return {'name': name, 'version': version, 'path': str(target.relative_to(ROOT)),
                        'sha256': sha(target.read_bytes()), 'verified_RECORD_files': count,
                        'origin': 'EXISTING_CACHE_WHEEL_ALL_RECORD_HASHES_VERIFIED', 'tag': tag}
        except zipfile.BadZipFile:
            continue
    raise ValueError('VERIFIED_CACHED_DEPENDENCY_UNAVAILABLE:' + name)


def main():
    release = ROOT / 'release'
    release.mkdir(exist_ok=True)
    wheelhouse = release / 'wheelhouse'
    wheelhouse.mkdir(exist_ok=True)
    receipts, deviations = [], []
    for name, dist in sorted(dependencies().items()):
        # Existing compatible cached versions satisfy the declared package range;
        # host core 2.46.2 has no matching verified archive. Keep host evidence distinct.
        overrides = {'pydantic': '2.13.5', 'pydantic-core': '2.46.5'}
        if name in overrides:
            deviations.append({'dependency': name, 'host_version': dist.version,
                               'release_version': overrides[name],
                               'action': 'Use compatible RECORD-verified cached pair; clean regression required'})
            receipts.append(cached_wheel(name, overrides[name], wheelhouse))
            continue
        try:
            receipt = rewheel(name, dist, wheelhouse)
        except ValueError as exc:
            if not str(exc).startswith('DEPENDENCY_RECORD_MISMATCH:'):
                raise
            deviations.append({'dependency': name, 'failure': str(exc),
                               'host_binary_qualified': False, 'action': 'Use fully verified existing cache wheel'})
            receipt = cached_wheel(name, dist.version, wheelhouse)
        receipts.append(receipt)
    (release / 'dependency_record_deviations.json').write_text(json.dumps(deviations, indent=2) + '\n')
    env = {**os.environ, 'SOURCE_DATE_EPOCH': '1767225600', 'PYTHONDONTWRITEBYTECODE': '1'}
    paths = []
    for iteration in (1, 2):
        output = release / f'build{iteration}'
        output.mkdir(exist_ok=True)
        result = subprocess.run([sys.executable, '-B', '-c',
                                 'import setuptools.build_meta as b; b.build_wheel(' + repr(str(output)) + ')'],
                                cwd=ROOT, env=env, capture_output=True, text=True)
        (release / f'build{iteration}.log').write_text(result.stdout + result.stderr)
        result.check_returncode()
        paths.append(next(output.glob('*.whl')))
    if paths[0].read_bytes() != paths[1].read_bytes():
        raise ValueError('REPRODUCIBLE_WHEEL_MISMATCH')
    target = wheelhouse / paths[0].name
    target.write_bytes(paths[0].read_bytes())
    receipts.append({'name': 'quant-advisory-platform', 'version': '0.7.0',
                     'path': str(target.relative_to(ROOT)), 'sha256': sha(target.read_bytes()),
                     'origin': 'ISOLATED_SOURCE_BUILD_BYTE_IDENTICAL_TWICE'})
    lines = [f"{x['name']}=={x['version']} --hash=sha256:{x['sha256']}" for x in receipts]
    (release / 'requirements-lock.txt').write_text('\n'.join(lines) + '\n')
    (release / 'dependency_provenance.json').write_text(json.dumps(receipts, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'wheel': str(target.relative_to(ROOT)), 'sha256': sha(target.read_bytes()),
                      'repeat_build_identical': True, 'dependency_count': len(receipts)-1}))


if __name__ == '__main__':
    main()
