"""Run disjoint inherited suites under their unchanged output-path contracts."""

from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", choices=["all", "product", "c", "mvp", "rc"], default="all")
    args = parser.parse_args()
    domains = ["product", "c", "mvp", "rc"] if args.domain == "all" else [args.domain]
    receipts = []
    for domain in domains:
        report = ROOT / "audit" / ("O_" + domain + "_domain_tests.xml")
        cwd = ROOT
        selection = [
            str(ROOT / "tests"),
            "--ignore=" + str(ROOT / "tests/evaluator"),
            "--ignore=" + str(ROOT / "tests/mvp"),
            "--ignore=" + str(ROOT / "tests/rc/test_d_integration.py"),
        ]
        extra = []
        if domain == "c":
            selection = [str(ROOT / "tests/evaluator")]
            extra = ["--basetemp=" + str(ROOT / "audit/O_C_test_work")]
        if domain in ("mvp", "rc"):
            cwd = Path(tempfile.mkdtemp(prefix="quant-o-mvp-test-"))
            selection = [str(ROOT / ("tests/mvp" if domain == "mvp" else "tests/rc/test_d_integration.py"))]
            extra = ["--basetemp=" + str(cwd / "tests")]
        env = {
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": os.pathsep.join(
                str(ROOT / p) for p in [".", "src", "tests", "tools", "tests/native"]
            ),
        }
        command = [
            sys.executable,
            "-B",
            str(ROOT / "tools/offline_pytest.py"),
            "-q",
            *selection,
            "-p",
            "no:cacheprovider",
            "--junitxml=" + str(report),
            *extra,
        ]
        with (ROOT / "audit" / ("O_" + domain + "_domain_tests.log")).open("w") as log:
            result = subprocess.run(
                command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=1800
            )
        receipt = {
            "domain": domain,
            "exit_code": result.returncode,
            "cwd": str(cwd),
            "report": str(report.relative_to(ROOT)),
            "network": "LOOPBACK_ONLY_OFFLINE_GUARD",
        }
        receipts.append(receipt)
        print(json.dumps(receipt), flush=True)
    return int(any(r["exit_code"] for r in receipts))


if __name__ == "__main__":
    raise SystemExit(main())
