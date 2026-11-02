"""Verify the fixed preservation scope without reading market or protected payloads."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
before = json.loads((ROOT / "artifacts/engineering/preservation_before.json").read_text())
base = Path(before["baseline"])
differences = []
for group in ("source_hashes", "receipt_hashes"):
    for relative, expected in before[group].items():
        path = base / relative
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "MISSING"
        if actual != expected:
            differences.append({"group": group, "path": str(path), "before": expected, "after": actual})
for name, expected in before["R_M_Q"].items():
    path = Path(expected["path"])

    def git(*args):
        return subprocess.check_output(["git", "-C", str(path), *args], text=True,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"}).strip()

    actual = {"path": str(path), "head": git("rev-parse", "HEAD"), "status": git("status", "--porcelain=v1"),
        "index_sha256": hashlib.sha256(Path(git("rev-parse", "--path-format=absolute", "--git-path", "index")).read_bytes()).hexdigest(),
        "dirty_source_hashes": {f: hashlib.sha256((path / f).read_bytes()).hexdigest()
                                for f in expected["dirty_source_hashes"]}}
    if actual != expected:
        differences.append({"group": name, "before": expected, "after": actual})
result = {"unchanged": not differences, "differences": differences, "scope": before["scope"],
          "baseline_source_files": len(before["source_hashes"]),
          "baseline_receipt_files": len(before["receipt_hashes"]),
          "old_session02_key_and_code_unchanged": not differences,
          "R_M_Q": before["R_M_Q"]}
(ROOT / "artifacts/engineering/preservation_after.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({"unchanged": result["unchanged"], "differences": len(differences),
                  "baseline_source_files": result["baseline_source_files"],
                  "baseline_receipt_files": result["baseline_receipt_files"]}))
raise SystemExit(0 if result["unchanged"] else 1)
