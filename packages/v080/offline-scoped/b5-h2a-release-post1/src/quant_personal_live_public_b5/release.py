"""Bind an approval to the supplied review wheel and the exact installed implementation."""

from io import BytesIO
from importlib.util import find_spec
import json
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from quant_personal_public_b1.policy import SourceBlocked, require
from quant_personal_public_b1.store import sha

PACKAGE = "quant_personal_live_public_b5"
LOCK = Path(__file__).with_name("dependency_lock.json")


def _installed(name, entries, *, own=False):
    spec = find_spec(name)
    require(spec is not None and spec.origin is not None, "INSTALLED_RELEASE_MISSING")
    root = Path(spec.origin).resolve().parent
    actual = {
        p.relative_to(root).as_posix(): sha(p.read_bytes())
        for p in root.rglob("*.py")
        if p.is_file()
    }
    if own:
        actual[LOCK.name] = sha(LOCK.read_bytes())
    require(actual == entries, "INSTALLED_RELEASE_MISMATCH", name)


def verify_release(wheel: Path, expected_sha: str) -> None:
    try:
        with wheel.open("rb") as handle:
            raw = handle.read(5_000_001)
            require(0 < len(raw) <= 5_000_000 and sha(raw) == expected_sha, "RELEASE_WHEEL_DIGEST_MISMATCH")
            with ZipFile(BytesIO(raw)) as archive:
                names = archive.namelist()
                require(len(names) == len(set(names)) and all(
                    n.startswith(PACKAGE + "/") or n.split("/")[0].endswith(".dist-info") for n in names
                ), "RELEASE_WHEEL_LAYOUT_INVALID")
                files = {n.split("/", 1)[1]: sha(archive.read(n)) for n in names if n.startswith(PACKAGE+"/")}
        _installed(PACKAGE, files, own=True)
        for name, pin in json.loads(LOCK.read_text()).items():
            _installed(name, pin["modules"])
    except (OSError, BadZipFile) as exc:
        raise SourceBlocked("RELEASE_WHEEL_UNVERIFIABLE") from exc
