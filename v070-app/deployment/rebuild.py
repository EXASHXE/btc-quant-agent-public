"""Rebuild the unchanged accepted F wheel using the bundled offline toolchain."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import subprocess
import sys

from deployment.host_check import compatibility
from deployment.bundle import verify


def main(root, output):
    root, output = Path(root).absolute(), Path(output).absolute()
    compatibility()
    verify(root)
    if output.exists():
        raise ValueError("UNUSED_BUILD_OUTPUT_REQUIRED")
    provenance = json.loads((root / "release/toolchain_provenance.json").read_text())
    for row in provenance:
        if metadata.version(row["name"]) != row["version"]:
            raise ValueError("INSTALLED_TOOLCHAIN_VERSION_MISMATCH:" + row["name"])
    output.mkdir()
    expected = json.loads((root / "deployment/accepted_release.json").read_text())["wheel_sha256"]
    hashes = []
    for repeat in (1, 2):
        target = output / str(repeat)
        target.mkdir()
        script = "import setuptools.build_meta as b; b.build_wheel(" + repr(str(target)) + ")"
        result = subprocess.run(
            [sys.executable, "-B", "-c", script],
            cwd=root,
            env={**os.environ, "SOURCE_DATE_EPOCH": "1767225600", "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True,
            text=True,
            timeout=90,
        )
        (output / f"build{repeat}.log").write_text(result.stdout + result.stderr)
        result.check_returncode()
        wheel = next(target.glob("*.whl"))
        value = hashlib.sha256(wheel.read_bytes()).hexdigest()
        hashes.append(value)
        if value != expected:
            raise ValueError("ACCEPTED_F_REBUILD_MISMATCH")
    receipt = {
        "status": "PASS_BYTE_IDENTICAL_ACCEPTED_F_WHEEL",
        "wheel_sha256": expected,
        "repeat_builds": hashes,
        "native_requests": 0,
        "host_qualified": False,
    }
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        print(json.dumps(main(args.root, args.output)))
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "FAILED_CLEAN_REBUILD", "reason": str(exc)}))
        raise SystemExit(2)
