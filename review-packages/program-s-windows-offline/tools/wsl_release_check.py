# ruff: noqa: E402
# Establish the source/accepted Quant import roots before importing the consumer.
"""Actual NTFS via DrvFS, final history artifacts and tests. No exchange network."""

from pathlib import Path
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parent / "lt-program-o-clock-remediation-01/src")]
from wsl_handoff.importer import process_bundle_to_handoff

m = json.loads((ROOT / "audit/S_NATIVE_NTFS_RECEIPT.json").read_text())
w = m["bundle_path"]
native = "/mnt/" + w[0].lower() + w[2:].replace("\\", "/")
env = {
    **os.environ,
    "QUANT_WIN_NATIVE_QA_BUNDLE": native,
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONPATH": str(ROOT) + ":" + str(ROOT.parent / "lt-program-o-clock-remediation-01/src"),
}
with (ROOT / "audit/S_WSL_RELEASE_FINAL.log").open("w") as log:
    p = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "-q",
            "tests/test_wsl_handoff_e2e.py",
            "tests/test_s_consumer.py",
            "-p",
            "no:cacheprovider",
            "--junitxml=audit/S_WSL_RELEASE_FINAL.xml",
        ],
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
p.check_returncode()
output = ROOT / ("artifacts/SYNTHETIC_NTFS_HISTORY_AUDIT_" + m["bundle_sha256"][:12])
result = process_bundle_to_handoff(Path(native), output)
(ROOT / "audit/S_OPERATOR_ARTIFACT_RECEIPT.json").write_text(
    json.dumps(
        {
            "source": "ACTUAL_WINDOWS_NTFS_LOOPBACK_TLS_SYNTHETIC",
            "native_path": w,
            "DrvFS_path": native,
            "bundle_sha256": m["bundle_sha256"],
            "output": str(output.relative_to(ROOT)),
            "mode": result["mode"],
            "current_actionability": result["current_actionability"],
            "historical_states": {s: d["market_state"] for s, d in result["decisions"].items()},
            "C": result["program_c_boundary"],
            "market_requests": 0,
        },
        indent=2,
    )
    + "\n"
)
