"""Descriptor-relative, exact-path I/O. Never discover or resolve protected trees."""

import hashlib
import json
import os
import re
import stat
from contextlib import contextmanager
from pathlib import Path

from . import GateError, require

DENIED = {
    '.git', '.aws', '.agents', '.codex', 'quant-agent', 'quant-agent-sanitized',
    'protected', 'forward', 'final', 'oos', 'a-line', 'a_line', 'h39', 'h40', 'h41',
    'holdout', 'accounts', 'credentials', 'private',
}


def canonical(obj):
    return (json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def digest(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def path(value):
    require(isinstance(value, str) and value.startswith('/') and not value.startswith('//')
            and '\\' not in value, 'PATH')
    p = Path(value)
    require('..' not in p.parts and str(p) == value and '://' not in value, 'TRAVERSAL')
    for part in p.parts:
        lower = part.casefold()
        require(not any(lower == d or lower.startswith(d + sep)
                        for d in DENIED for sep in ('-', '_', '.')), 'PROTECTED_PATH')
    return p


@contextmanager
def directory(p):
    p = path(str(p))
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in p.parts[1:]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    except OSError as exc:
        raise GateError('UNSAFE_OR_MISSING_PATH') from exc
    finally:
        os.close(fd)


def signature(s):
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def file_info(p):
    p = path(str(p))
    with directory(p.parent) as fd:
        try:
            s = os.stat(p.name, dir_fd=fd, follow_symlinks=False)
        except OSError as exc:
            raise GateError('UNSAFE_OR_MISSING_FILE') from exc
        require(stat.S_ISREG(s.st_mode) and s.st_nlink == 1, 'UNSAFE_FILE_OR_LINK')
        require(s.st_mode & 0o022 == 0, 'WRITABLE_BY_OTHER_PRINCIPALS')
        return signature(s)


def read_exact(p, sha=None, accepted=None, cap=64 * 1024 * 1024):
    """Hash and parse the same immutable bytes; reject links before payload opens."""
    p = path(str(p))
    before = file_info(p)
    require(0 < before[2] <= cap, 'SIZE_LIMIT')
    require(accepted is None or before == accepted, 'IDENTITY_CHANGED')
    with directory(p.parent) as parent:
        try:
            fd = os.open(p.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            with os.fdopen(fd, 'rb') as stream:
                require(signature(os.fstat(stream.fileno())) == before, 'IDENTITY_CHANGED')
                payload = stream.read(cap + 1)
                require(signature(os.fstat(stream.fileno())) == before, 'MUTATED_SOURCE')
        except OSError as exc:
            raise GateError('UNSAFE_OR_MISSING_FILE') from exc
    require(file_info(p) == before and len(payload) == before[2], 'MUTATED_SOURCE')
    if sha is not None:
        require(hashlib.sha256(payload).hexdigest() == sha, 'SHA_MISMATCH')
    return payload


def hash_value(value):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value), 'SHA_REQUIRED')


def load(payload):
    def unique(pairs):
        d = {}
        for k, v in pairs:
            require(k not in d, 'DUPLICATE_JSON_KEY')
            d[k] = v
        return d

    def invalid(_):
        raise GateError('NONFINITE_JSON')

    try:
        return json.loads(payload, object_pairs_hook=unique, parse_constant=invalid)
    except (ValueError, UnicodeError) as exc:
        raise GateError('INVALID_JSON') from exc


def absent(p):
    p = path(str(p))
    with directory(p.parent) as fd:
        try:
            os.stat(p.name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        raise GateError('OUTPUT_COLLISION')


def publish(p, payload):
    p = path(str(p))
    with directory(p.parent) as parent:
        try:
            fd = os.open(p.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o400, dir_fd=parent)
        except OSError as exc:
            raise GateError('OUTPUT_COLLISION') from exc
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
