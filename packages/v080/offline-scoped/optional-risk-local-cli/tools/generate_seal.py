"""Generate SHA256SUMS manifest over the sealed workroot (excluding .qa/ and SHA256SUMS)."""

from __future__ import annotations

import hashlib
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "SHA256SUMS"


def main() -> None:
    entries: list[str] = []
    for path in sorted(ROOT.rglob("*"), key=lambda p: p.relative_to(ROOT).as_posix()):
        rel = path.relative_to(ROOT).as_posix()
        if rel == ".qa" or rel.startswith(".qa/") or rel == "SHA256SUMS":
            continue
        if "__pycache__" in Path(rel).parts or path.suffix == ".pyc":
            raise SystemExit(f"PYCACHE_FORBIDDEN {rel}")
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise SystemExit(f"SYMLINK_FORBIDDEN {rel}")
        if info.st_mode & 0o022:
            raise SystemExit(
                f"WRITABLE_GROUP_OR_WORLD_MODE {rel} {oct(stat.S_IMODE(info.st_mode))}"
            )
        if stat.S_ISREG(info.st_mode):
            with path.open("rb") as fh:
                digest = hashlib.file_digest(fh, "sha256").hexdigest()
            entries.append(f"{digest}  {rel}")
    MANIFEST.write_text("\n".join(entries) + "\n", encoding="utf-8")
    MANIFEST.chmod(0o644)
    print(f"GENERATED {MANIFEST} entries={len(entries)}")


if __name__ == "__main__":
    main()
