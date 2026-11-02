"""Verify only recorded source/doc bytes and Git metadata; no market-payload reads."""

from pathlib import Path
import hashlib
import json
import os
import subprocess

ROOT = Path(__file__).resolve().parents[1]
before = json.loads((ROOT / "artifacts/preservation_before.json").read_text())
after = {}
for name, record in before.items():
    path = Path(record["path"])
    if "source_hashes" in record:
        after[name] = {
            "path": str(path),
            "source_hashes": {
                f: hashlib.sha256((path / f).read_bytes()).hexdigest() for f in record["source_hashes"]
            },
        }
        continue

    def git(*args):
        return subprocess.check_output(
            ["git", "-C", str(path), *args], text=True, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
        ).strip()

    after[name] = {
        "path": str(path),
        "head": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current"),
        "status": git("status", "--porcelain=v1"),
        "index_sha256": hashlib.sha256(
            Path(git("rev-parse", "--path-format=absolute", "--git-path", "index")).read_bytes()
        ).hexdigest(),
        "owner_source_hashes": {
            f: hashlib.sha256((path / f).read_bytes()).hexdigest() for f in record["owner_source_hashes"]
        },
    }
result = {
    "unchanged": after == before,
    "repositories": after,
    "scope": "Baseline source/config/tests/tools/delivery docs; original R/M/Q HEAD, branch, status, index and recorded Owner source bytes. No protected payload or registry-content access.",
}
(ROOT / "artifacts/preservation_after.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({"unchanged": result["unchanged"], "checked": list(after)}))
if not result["unchanged"]:
    raise SystemExit(1)
