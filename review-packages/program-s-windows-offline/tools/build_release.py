"""Two fresh offline build processes, fixed epoch; do not reuse setuptools commands."""

from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import shutil

ROOT = Path(__file__).resolve().parents[1]
hashes = []
for i in [1, 2]:
    shutil.rmtree(ROOT / "build", ignore_errors=True)
    target = ROOT / "release" / ("build" + str(i))
    target.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            "import setuptools.build_meta as b; b.build_wheel(" + repr(str(target)) + ")",
        ],
        cwd=ROOT,
        env={**os.environ, "SOURCE_DATE_EPOCH": "1767225600", "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        check=True,
    )
    (ROOT / "audit" / ("S_BUILD" + str(i) + ".log")).write_text(p.stdout + p.stderr)
    wheel = next(target.glob("*.whl"))
    hashes.append(hashlib.sha256(wheel.read_bytes()).hexdigest())
assert hashes[0] == hashes[1]
shutil.copyfile(wheel, ROOT / "release" / wheel.name)
(ROOT / "S_REPRODUCIBLE_BUILD.json").write_text(
    json.dumps(
        {
            "wheel": "release/" + wheel.name,
            "sha256": hashes[0],
            "two_byte_identical_builds": True,
            "SOURCE_DATE_EPOCH": 1767225600,
            "new_dependencies": 0,
            "scope": "Windows stdlib capture; WSL audit requires accepted Quant O environment",
        },
        indent=2,
    )
    + "\n"
)
print(hashes[0])
