"""Build the sealed wheel, install exact local dependencies and reproduce the demo offline."""

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
PACKAGE = "quant_personal_decision_b2"
ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "PIP_NO_INDEX": "1",
       "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PYTHONDONTWRITEBYTECODE": "1", "SOURCE_DATE_EPOCH": "1767225600"}
B1_PIN = "19d89bd87721733dbe05a1298f157e8ea15258fd1d4b981dd5e11e34b05a544f"
DENY_SOCKET = (
    "import sys; "
    "sys.addaudithook(lambda e,a: (_ for _ in ()).throw(RuntimeError(e)) if e.startswith('socket.') else None); "
)


def execute(*command: str, cwd: Path, env: dict[str, str], expected: int = 0, show: bool = True) -> str:
    print(f"cwd={cwd}\n$ {shlex.join(command)}", flush=True)
    p = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, check=False, timeout=45)
    if show and p.stdout:
        print(p.stdout, end="", flush=True)
    if p.stderr:
        print(p.stderr, end="", flush=True)
    print(f"exit_code={p.returncode} expected={expected}", flush=True)
    assert p.returncode == expected
    return p.stdout


def main() -> None:
    assert {name for _, name in socket.if_nameindex()} == {"lo"}, "Use loopback-only/unconfigured network namespace"
    wheel_dir = EVIDENCE / "wheel"
    wheel_dir.mkdir(exist_ok=False)
    b1, = (EVIDENCE / "dependencies").glob("*.whl")
    assert hashlib.sha256(b1.read_bytes()).hexdigest() == B1_PIN
    with tempfile.TemporaryDirectory(prefix=".b2-build-", dir=ROOT) as tmp:
        temp = Path(tmp)
        env = {**ENV, "TMPDIR": tmp}
        pkg = temp / "package"
        pkg.mkdir()
        shutil.copyfile(ROOT / "pyproject.toml", pkg / "pyproject.toml")
        shutil.copytree(ROOT / "src", pkg / "src", ignore=shutil.ignore_patterns("__pycache__"))
        execute(sys.executable, "-B", "-m", "pip", "wheel", "--no-index", "--no-build-isolation", "--no-deps",
                "--wheel-dir", str(wheel_dir), ".", cwd=pkg, env=env)
        wheel, = wheel_dir.glob("*.whl")
        b2_hash = hashlib.sha256(wheel.read_bytes()).hexdigest()
        with zipfile.ZipFile(wheel) as z:
            inventory = z.namelist()
            assert all(path.split("/")[0].startswith(PACKAGE) for path in inventory)
        requirements = EVIDENCE / "offline_requirements.txt"
        requirements.write_text(f"quant-personal-public-b1==0.8.0b1 --hash=sha256:{B1_PIN}\n"
                                f"quant-personal-decision-b2==0.8.0b2 --hash=sha256:{b2_hash}\n")
        clean = temp / "clean"
        venv.EnvBuilder(with_pip=False).create(clean)
        python = str(clean / "bin/python")
        pip = (sys.executable, "-B", "-m", "pip", "--python", python, "install", "--no-index")
        execute(*pip, "--require-hashes", "--find-links", str(b1.parent), "--find-links", str(wheel_dir),
                "-r", str(requirements), cwd=temp, env=env)
        script = str(ROOT / "tools/audit_install.py")
        cold = json.loads(execute(python, "-B", "-I", script, str(b1), cwd=temp, env=env, show=False))
        assert not cold["legacy_installed"] and cold["isolated"]
        cold.update(wheel_sha256=b2_hash, wheel_inventory=inventory)
        (EVIDENCE / "cold_install.json").write_text(json.dumps(cold, indent=2) + "\n")
        execute(str(clean / "bin/quant-decision-b2"), "demo", "--output", str(EVIDENCE / "demo"), cwd=temp, env=env)
        case = EVIDENCE / "demo/pullback-long"
        journal = case / "decision.sqlite"
        read_args = ["read", "--journal", str(journal), "--json"]
        read_code = DENY_SOCKET + f"from {PACKAGE}.cli import main; raise SystemExit(main({read_args!r}))"
        old = json.loads(execute(python, "-B", "-I", "-c", read_code, cwd=temp, env=env, show=False))
        assert old == json.loads((case / "card_3.json").read_bytes())
        legacy, = (ROOT.parent / "lt-v080-sol62-personal-mvp-layer1-public-01/evidence/wheel").glob("*.whl")
        execute(*pip, "--no-deps", str(legacy), cwd=temp, env=env)
        shadow = temp / "shadow"
        for namespace in (PACKAGE, "quant_personal_public_b1", "btc_quant_agent"):
            trap = shadow / namespace / "__init__.py"
            trap.parent.mkdir(parents=True)
            trap.write_text("raise RuntimeError('shadow module executed')\n")
        hostile = {**env, "PYTHONPATH": str(shadow), "QUANT_LIVE": "1", "ENABLE_TRADE": "1",
                   "BINANCE_API_KEY": "fabricated", "BINANCE_API_SECRET": "fabricated",
                   "HTTPS_PROXY": "http://127.0.0.1:9"}
        mixed = json.loads(execute(python, "-B", "-I", script, str(b1), cwd=shadow, env=hostile, show=False))
        assert mixed["legacy_installed"] and not mixed["legacy_imported"] and mixed["isolated"]
        again = json.loads(execute(python, "-B", "-I", "-c", read_code, cwd=shadow, env=hostile, show=False))
        assert again == old
        denied = json.loads(execute(
            python, "-B", "-I", "-c", DENY_SOCKET + "from quant_personal_public_b1.cli import main; "
            "sys.argv=['quant-public-b1','live']; raise SystemExit(main())", cwd=shadow, env=hostile, expected=2,
        ))
        assert denied["error"] == "LIVE_CAPABILITY_DORMANT"
        mixed.update(live_gate=denied, replay_with_socket_audit_equal=True)
        (EVIDENCE / "mixed_install.json").write_text(json.dumps(mixed, indent=2) + "\n")


if __name__ == "__main__":
    main()
