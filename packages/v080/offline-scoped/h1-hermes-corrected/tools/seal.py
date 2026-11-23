"""Seal the final H1 workroot tree in canonical lexicographic path order."""

from __future__ import annotations

import hashlib
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = root / "SHA256SUMS"
entries: list[tuple[str, str]] = []

for path in root.rglob("*"):
    rel = path.relative_to(root)
    if path.is_symlink() or any(
        part.startswith(".") or part == "__pycache__" or part.endswith(".egg-info")
        for part in rel.parts
    ):
        raise SystemExit(f"Unexpected deliverable path {rel}")
    if path.is_dir() or path == manifest:
        continue
    if not path.is_file() or path.resolve() != path or any(ch in rel.as_posix() for ch in "\\\r\n"):
        raise SystemExit(f"Unexpected deliverable type {rel}")
    entries.append((rel.as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()))

payload = "".join(f"{sha}  {name}\n" for name, sha in sorted(entries))
manifest.write_text(payload, encoding="ascii", newline="\n")
print(f"{len(entries)} files sealed")
