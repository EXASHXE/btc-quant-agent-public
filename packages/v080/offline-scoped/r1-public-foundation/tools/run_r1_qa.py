"""Materialize the preserved regression inputs and run pytest in a loopback-only namespace."""

import argparse
import hashlib
import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R1_PACKAGE = Path("src/btc_quant_agent/platform/personal_mvp")


def materialize(parent: Path) -> Path:
    workspace = parent / "r1"
    workspace.mkdir()
    manifest = json.loads((ROOT / "evidence/PROGRAM_J_INPUT_MANIFEST.json").read_bytes())
    for item in manifest["files"]:
        path = Path(item["path"])
        destination = workspace / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, destination)
    shutil.copytree(ROOT / R1_PACKAGE, workspace / R1_PACKAGE, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "tests/personal_market", workspace / "tests/personal_market",
                    ignore=shutil.ignore_patterns("__pycache__"))
    inputs = ROOT / "evidence/qa_inputs"
    pins = json.loads((inputs / "inputs.json").read_text())
    for entry in pins:
        src = inputs / entry["vendored"]
        if hashlib.sha256(src.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError(f"QA input integrity failure: {src.name}")
        out = parent / entry["materialized"]
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, out)
    return workspace


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", choices=["targeted", "full"])
    args = parser.parse_args()
    # This runner must never be launched in the default host network namespace.
    if {name for _, name in socket.if_nameindex()} != {"lo"}:
        parser.error("run inside a network namespace with loopback as its sole interface")
    with tempfile.TemporaryDirectory(prefix=".r1-qa-", dir=ROOT) as temporary:
        workspace = materialize(Path(temporary))
        output = ROOT / f"evidence/pytest_{args.suite}.xml"
        selection = "tests/personal_market" if args.suite == "targeted" else "tests"
        argv = [
            sys.executable, "-B", "tools/offline_pytest.py", selection, "-q",
            "-o", "pythonpath=src tests tools tests/native .", "-p", "no:cacheprovider",
            f"--basetemp={workspace / 'test-tmp'}", f"--junitxml={output}",
        ]
        print("$ " + shlex.join(argv), flush=True)
        env = {key: val for key, val in os.environ.items() if key in {"PATH", "LANG", "LC_ALL"}}
        env.update(PYTHONDONTWRITEBYTECODE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONPATH="src")
        result = subprocess.run(argv, cwd=workspace, env=env, check=False)
        print(f"exit_code={result.returncode}", flush=True)
        return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
