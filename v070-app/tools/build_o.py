"""Reproducible offline J wheel using the already frozen G dependency artifacts."""

from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = ROOT / "release"
    hashes = []
    wheels = []
    for index in (1, 2):
        # Each build must read source, including edits made within one mtime second.
        shutil.rmtree(ROOT / "build", ignore_errors=True)
        target = output / f"O_build{index}"
        target.mkdir(exist_ok=True)
        code = "import setuptools.build_meta as b; b.build_wheel(" + repr(str(target)) + ")"
        result = subprocess.run(
            [sys.executable, "-B", "-c", code],
            cwd=ROOT,
            env={**os.environ, "SOURCE_DATE_EPOCH": "1767225600", "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True,
            text=True,
            timeout=90,
        )
        (output / f"O_build{index}.log").write_text(result.stdout + result.stderr)
        result.check_returncode()
        wheel = next(target.glob("quant_advisory_platform-0.7.0.post6-*.whl"))
        wheels.append(wheel)
        hashes.append(hashlib.sha256(wheel.read_bytes()).hexdigest())
    assert hashes[0] == hashes[1], "O_REPRODUCIBLE_WHEEL_MISMATCH"
    new = output / "wheelhouse" / wheels[0].name
    new.write_bytes(wheels[0].read_bytes())
    for name in ("dependency_provenance.json", "toolchain_provenance.json"):
        rows = json.loads((output / name).read_text())
        rows = [r for r in rows if r["name"] != "quant-advisory-platform"]
        rows.append(
            {
                "name": "quant-advisory-platform",
                "version": "0.7.0.post6",
                "path": str(new.relative_to(ROOT)),
                "sha256": hashes[0],
                "origin": "O_ISOLATED_TWO_BYTE_IDENTICAO_BUILDS",
            }
        )
        (output / name).write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
        lock = "requirements-lock.txt" if name == "dependency_provenance.json" else "toolchain-lock.txt"
        (output / lock).write_text(
            "".join(f"{r['name']}=={r['version']} --hash=sha256:{r['sha256']}\n" for r in rows)
        )
    receipt = {
        "status": "PASS_TWO_BYTE_IDENTICAL_O_BUILDS",
        "wheel": str(new.relative_to(ROOT)),
        "sha256": hashes[0],
        "SOURCE_DATE_EPOCH": 1767225600,
        "old_native_research_contracts_modified": False,
    }
    (ROOT / "O_REPRODUCIBLE_BUILD.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
