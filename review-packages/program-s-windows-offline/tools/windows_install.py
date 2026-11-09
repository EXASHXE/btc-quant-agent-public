"""Clean native NTFS venv and offline wheel installation; no service or network change."""

from pathlib import Path
import sys
import os
import subprocess
import json
import tempfile
import hashlib

ROOT = Path(__file__).resolve().parents[1]
root = Path(tempfile.mkdtemp(prefix="Quant_S_PACKAGE_INSTALL_"))
venv = root / "venv"
env = {**os.environ, "PIP_NO_INDEX": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PIP_CONFIG_FILE": os.devnull}
subprocess.run([sys.executable, "-I", "-m", "venv", str(venv)], env=env, check=True)
python = venv / "Scripts/python.exe"
wheel = next((ROOT / "release").glob("quant_windows_handoff-*.whl"))
subprocess.run(
    [str(python), "-I", "-m", "pip", "install", "--no-index", "--no-deps", "--no-cache-dir", str(wheel)],
    env=env,
    check=True,
)
code = 'import win_capture,win_capture.win_clock as w,json,hashlib; from pathlib import Path; p=Path(w.__file__); print(json.dumps({"origin":str(p),"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"sample":w.sample_windows_clocks()}))'
p = subprocess.run([str(python), "-I", "-c", code], env=env, capture_output=True, text=True, check=True)
installed = json.loads(p.stdout)
assert installed["sha256"] == hashlib.sha256((ROOT / "win_capture/win_clock.py").read_bytes()).hexdigest()
cli = subprocess.run(
    [
        str(venv / "Scripts/quant-win-capture.exe"),
        "--allow-live-public-https",
        "--output",
        str(root / "blocked_output"),
    ],
    env=env,
    capture_output=True,
    text=True,
)
assert cli.returncode != 0 and "HASH_BOUND_ACCESS" in cli.stderr and not (root / "blocked_output").exists()
x = {
    "schema": "S_CLEAN_WINDOWS_INSTALL_V1",
    "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
    "venv_path": str(venv),
    "installed": installed,
    "unscoped_live_flag_exit": cli.returncode,
    "unscoped_live_flag_stderr": cli.stderr,
    "exchange_requests": 0,
    "install_index_access": False,
    "entrypoint_default_deny": True,
}
(ROOT / "audit/S_WINDOWS_CLEAN_INSTALL.json").write_text(json.dumps(x, indent=2) + "\n")
print(json.dumps(x))
