"""Verify every sealed file in the optional-risk workroot against SHA256SUMS."""

from __future__ import annotations

import hashlib
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "SHA256SUMS"


def main() -> None:
    if not MANIFEST.is_file() or MANIFEST.is_symlink():
        raise SystemExit("MISSING_SHA256SUMS")
    rows = [
        line.split("  ", 1) for line in MANIFEST.read_text(encoding="utf-8").splitlines() if line
    ]
    actual: set[str] = set()
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT).as_posix()
        if rel == ".qa" or rel.startswith(".qa/") or path == MANIFEST:
            continue
        if "__pycache__" in Path(rel).parts or path.suffix == ".pyc":
            raise SystemExit(f"PYCACHE_FORBIDDEN {rel}")
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_mode & 0o022:
            raise SystemExit(f"UNSAFE_SEALED_PATH {rel}")
        if stat.S_ISREG(info.st_mode):
            actual.add(rel)
    expected_set = {name for _, name in rows}
    if len(rows) != len(actual) or expected_set != actual:
        missing = sorted(expected_set - actual)
        extra = sorted(actual - expected_set)
        raise SystemExit(f"SEAL_INVENTORY_MISMATCH missing={missing} extra={extra}")
    for expected_hash, name in rows:
        with (ROOT / name).open("rb") as fh:
            digest = hashlib.file_digest(fh, "sha256").hexdigest()
        if digest != expected_hash:
            raise SystemExit(f"SEAL_HASH_MISMATCH {name}")
    print(f"PASS seal={MANIFEST.parent.name} entries={len(rows)}")


if __name__ == "__main__":
    main()
