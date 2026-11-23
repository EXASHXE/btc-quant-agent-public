"""Build, install, audit and demo the B1 artifact using local tooling only."""

from __future__ import annotations

import hashlib
import json
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import venv
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence"
PACKAGE = "quant_personal_public_b1"
ENV = {
    "PATH": "/usr/bin:/bin",
    "LANG": "C.UTF-8",
    "PIP_NO_INDEX": "1",
    "PIP_DISABLE_PIP_VERSION_CHECK": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
    "SOURCE_DATE_EPOCH": "1767225600",
}


def run(*args: str, cwd: Path, env: dict[str, str] = ENV, expected: int = 0, echo_stdout: bool = True) -> str:
    print(f"cwd={cwd}\n$ {shlex.join(args)}", flush=True)
    result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, check=False)
    if result.stdout and echo_stdout:
        print(result.stdout, end="", flush=True)
    if result.stderr:
        print(result.stderr, end="", flush=True)
    print(f"exit_code={result.returncode} expected={expected}", flush=True)
    assert result.returncode == expected
    return result.stdout


def main() -> None:
    assert {name for _, name in socket.if_nameindex()} == {"lo"}, "build must use an isolated network namespace"
    wheel_dir = EVIDENCE / "wheel"
    wheel_dir.mkdir(exist_ok=False)
    with tempfile.TemporaryDirectory(prefix=".b1-build-", dir=ROOT) as tm:
        stage = Path(tm)
        package_root = stage / "package"
        package_root.mkdir()
        shutil.copyfile(ROOT / "pyproject.toml", package_root / "pyproject.toml")
        shutil.copytree(ROOT / "src", package_root / "src", ignore=shutil.ignore_patterns("__pycache__"))
        env = {**ENV, "TMPDIR": tm}
        run(sys.executable, "-B", "-m", "pip", "wheel", "--no-index", "--no-build-isolation", "--no-deps",
            "--wheel-dir", str(wheel_dir), ".", cwd=package_root, env=env)
        wheel, = wheel_dir.glob("*.whl")
        wheel_sha = hashlib.sha256(wheel.read_bytes()).hexdigest()
        with zipfile.ZipFile(wheel) as z:
            inventory = z.namelist()
            assert all(name.split("/")[0].startswith((PACKAGE + "-", PACKAGE)) for name in inventory)
            assert not any("btc_quant_agent" in name for name in inventory)
        venv_path = stage / "clean"
        venv.EnvBuilder(with_pip=False).create(venv_path)
        executable = str(venv_path / "bin/python")
        pip = (sys.executable, "-B", "-m", "pip", "--python", executable, "install", "--no-index", "--no-deps")
        run(*pip, str(wheel), cwd=stage, env=env)
        audit = str(ROOT / "tools/audit_installed.py")
        clean = json.loads(run(executable, "-B", "-I", audit, cwd=stage, env=env))
        assert clean["isolated_interpreter"] and not clean["legacy_package_available"]
        clean.update(wheel_sha256=wheel_sha, wheel_inventory=inventory)
        (EVIDENCE / "cold_install_inventory.json").write_text(json.dumps(clean, indent=2) + "\n")

        # Only the B1 wheel is installed at this point. Exercise its normal console entry point and full demo.
        run(str(venv_path / "bin/quant-public-b1"), "demo", "--output", str(EVIDENCE / "demo"), cwd=stage, env=env)
        store_path = EVIDENCE / "demo/fixture.sqlite"
        read = run(executable, "-B", "-I", "-m", PACKAGE, "read", "--db", str(store_path), "--origin", "fixture",
                   "--scan", "2", cwd=stage, env=env, echo_stdout=False)
        assert json.loads(read)["strategy_status"] == "NOT_EVALUATED"

        legacy, = (ROOT.parent / "lt-v080-sol62-personal-mvp-layer1-public-01/evidence/wheel").glob("*.whl")
        run(*pip, str(legacy), cwd=stage, env=env)
        shadow = stage / "shadow"
        for namespace in ("btc_quant_agent", PACKAGE):
            trap = shadow / namespace / "__init__.py"
            trap.parent.mkdir(parents=True)
            trap.write_text("raise RuntimeError('shadow package must never run')\n")
        adversarial = {
            **env, "PYTHONPATH": str(shadow), "QUANT_MODE": "legacy-execution", "QUANT_LIVE": "1",
            "ENABLE_EXECUTION": "1", "BINANCE_API_KEY": "synthetic", "BINANCE_API_SECRET": "synthetic",
            "HTTPS_PROXY": "http://127.0.0.1:9",
        }
        mixed = json.loads(run(executable, "-B", "-I", audit, cwd=shadow, env=adversarial))
        assert mixed["legacy_package_available"] and not mixed["legacy_package_loaded"]
        denied = run(executable, "-B", "-I", "-m", PACKAGE, "live", cwd=shadow, env=adversarial, expected=2)
        assert json.loads(denied)["error"] == "LIVE_CAPABILITY_DORMANT"
        mixed["live_mode_result"] = json.loads(denied)
        (EVIDENCE / "mixed_install_inventory.json").write_text(json.dumps(mixed, indent=2) + "\n")


if __name__ == "__main__":
    main()
