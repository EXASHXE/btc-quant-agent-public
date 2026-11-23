"""Verify the sealed H4 inventory. QA scratch lives below .qa."""

import hashlib
import re
import stat
from pathlib import Path

root = Path(__file__).resolve().parents[1]
actual = set()
for path in root.rglob("*"):
    relative = path.relative_to(root)
    if relative.parts[0] == ".qa" or relative.as_posix() == "SHA256SUMS":
        continue
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode) or mode & 0o022:
        raise SystemExit(f"INVALID_SEAL_MODE {relative}")
    if stat.S_ISREG(mode):
        actual.add(relative.as_posix())

rows = (root / "SHA256SUMS").read_text().splitlines()
recorded = set()
for row in rows:
    if not re.fullmatch(r"[0-9a-f]{64}  [A-Za-z0-9_./-]+", row):
        raise SystemExit("INVALID_SEAL_ROW")
    expected, name = row.split("  ", 1)
    if name in recorded or name not in actual:
        raise SystemExit(f"INVALID_SEAL_PATH {name}")
    recorded.add(name)
    with (root / name).open("rb") as handle:
        if hashlib.file_digest(handle, "sha256").hexdigest() != expected:
            raise SystemExit(f"H4_SEAL_DIGEST_MISMATCH {name}")

if recorded != actual:
    raise SystemExit(f"H4_INVENTORY_MISMATCH {sorted(actual - recorded)}")
print(f"PASS H4 sealed files {len(recorded)}/{len(recorded)}")
