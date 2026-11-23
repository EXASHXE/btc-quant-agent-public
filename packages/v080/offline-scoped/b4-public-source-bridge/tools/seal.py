"""Seal the final B4 tree in canonical path order."""

import hashlib
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = root / "SHA256SUMS"
entries = []
for path in root.rglob("*"):
    rel = path.relative_to(root)
    if path.is_symlink() or any(part.startswith(".") for part in rel.parts):
        raise SystemExit(f"Unexpected deliverable path {rel}")
    if path.is_dir() or path == manifest:
        continue
    if not path.is_file() or path.resolve() != path or any(char in rel.as_posix() for char in "\\\r\n"):
        raise SystemExit(f"Unexpected deliverable type {rel}")
    entries.append((rel.as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()))
payload = "".join(f"{sha}  {name}\n" for name, sha in sorted(entries))
manifest.write_text(payload, encoding="ascii", newline="\n")
print(f"{len(entries)} files sealed")
