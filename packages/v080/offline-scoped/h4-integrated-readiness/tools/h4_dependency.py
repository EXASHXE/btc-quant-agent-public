"""Render or verify post3's dependency record from the independently built H4 wheel."""

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "b5/src/quant_personal_live_public_b5/dependency_lock.json"


def render(wheel):
    data = json.loads(LOCK.read_text())
    with ZipFile(wheel) as archive:
        modules = {
            name.split("/", 1)[1]: hashlib.sha256(archive.read(name)).hexdigest()
            for name in archive.namelist()
            if name.startswith("quant_h4/")
        }
    data["quant_h4"] = {
        "modules": modules,
        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
    }
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("wheel", type=Path)
    cli.add_argument("--update", action="store_true")
    arguments = cli.parse_args()
    desired = render(arguments.wheel)
    if arguments.update:
        LOCK.write_text(desired)
    elif LOCK.read_text() != desired:
        raise SystemExit("H4_DEPENDENCY_LOCK_MISMATCH")
    else:
        print("PASS post3 H4 dependency wheel and module hashes")
