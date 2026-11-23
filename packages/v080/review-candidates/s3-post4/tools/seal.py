"""Seal the complete shared deliverable inventory into SHA256SUMS in canonical order."""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "SHA256SUMS"
# Exclude disposable .qa/, SHA256SUMS itself, and live AGY CLI stdout/stderr capture files.
EXCLUDED_TOP_LEVEL = frozenset({".qa", "SHA256SUMS", "agy_cli_response.json", "agy_cli_stderr.log"})


def main() -> int:
    entries: list[tuple[str, str]] = []
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        if rel.parts[0] in EXCLUDED_TOP_LEVEL:
            continue
        if path.is_symlink():
            raise SystemExit(f"Unexpected symlink in deliverables: {rel}")
        if any(part.startswith(".") for part in rel.parts):
            raise SystemExit(f"Unexpected hidden path in deliverables: {rel}")
        if any(part == "__pycache__" or part.endswith(".pyc") for part in rel.parts):
            raise SystemExit(f"Unexpected bytecode path in deliverables: {rel}")
        if path.is_dir():
            continue
        if not path.is_file() or path.resolve() != path or any(ch in rel.as_posix() for ch in "\\\r\n"):
            raise SystemExit(f"Unexpected deliverable entry: {rel}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        entries.append((rel.as_posix(), digest))
    payload = "".join(f"{digest}  {name}\n" for name, digest in sorted(entries))
    MANIFEST.write_text(payload, encoding="ascii", newline="\n")
    manifest_sha = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    print(f"SEALED {len(entries)} files; SHA256SUMS sha256={manifest_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
