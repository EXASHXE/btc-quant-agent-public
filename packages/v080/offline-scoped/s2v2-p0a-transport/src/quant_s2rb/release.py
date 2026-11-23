"""Pin the reviewed artifact, the installed code, and the production enrollment."""

import io
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from quant_s2v2.protocol import (
    Denied,
    file_bytes,
    hexdigest,
    protected_chain,
    require,
    sha,
    strict_json,
)

from . import CLOSED

_PARENT = Path(__file__).resolve().parent
_CODE_SUFFIXES = {".py", ".json", ".so"}
# A reviewed future source artifact must explicitly provision these immutable roots.
_PRODUCTION_ROOTS = None


@dataclass(frozen=True)
class ProductionRoots:
    configuration: Path
    grant: Path
    wheel: Path
    controller_key: bytes
    policy_sha: str


def production_roots():
    roots = _PRODUCTION_ROOTS
    require(type(roots) is ProductionRoots, CLOSED)
    require(
        all(
            type(path) is type(Path()) and path.is_absolute()
            for path in (roots.configuration, roots.grant, roots.wheel)
        )
        and hexdigest(roots.policy_sha)
        and type(roots.controller_key) is bytes
        and len(roots.controller_key) == 32
        and roots.controller_key.hex() not in _fixture_keys(),
        "PRODUCTION_ROOT_INVALID_OR_FIXTURE",
    )
    return roots


def _fixture_keys():
    raw = file_bytes(_PARENT / "fixture_public_keys.json", protected=True)
    return strict_json(raw)


def _inventory(root):
    protected_chain(root)
    paths = sorted(root.rglob("*"))
    require(
        all(not path.is_symlink() and path.suffix != ".pyc" for path in paths),
        "INSTALLED_BYTECODE_OR_SYMLINK_FORBIDDEN",
    )
    return {
        path.relative_to(root).as_posix(): sha(file_bytes(path, maximum=24_000_000, protected=True))
        for path in paths
        if path.suffix in _CODE_SUFFIXES and path.is_file()
    }


def verify_release(wheel, expected):
    raw = file_bytes(wheel, maximum=2_000_000, protected=True)
    require(sha(raw) == expected, "RELEASE_DIGEST_MISMATCH")
    prefix = "quant_s2rb/"
    try:
        with ZipFile(io.BytesIO(raw)) as archive:
            names = [name for name in archive.namelist() if name.startswith(prefix)]
            require(len(set(names)) == len(names), "RELEASE_INVENTORY_MISMATCH")
            own = {name.removeprefix(prefix): sha(archive.read(name)) for name in names}
    except BadZipFile as exc:
        raise Denied("RELEASE_WHEEL_INVALID") from exc
    require(_inventory(_PARENT) == own, "INSTALLED_RELEASE_MISMATCH")
    pins = strict_json(file_bytes(_PARENT / "dependency_hashes.json", protected=True))
    for package, pin in pins.items():
        spec = find_spec(package)
        require(spec is not None and spec.origin is not None, "DEPENDENCY_UNAVAILABLE")
        path = Path(spec.origin)
        require(path.resolve(strict=True) == path, "DEPENDENCY_PATH_UNSAFE")
        require(_inventory(path.parent) == pin, "DEPENDENCY_BYTES_MISMATCH")
