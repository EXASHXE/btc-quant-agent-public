"""Verify H4's current checkout and historical inputs without moving either branch."""

import argparse
import hashlib
import json
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT.parents[1]
DOCS = CODE.parent / "quant-docs-engineering"
H3 = ROOT.parent / "lt-v080-sol62-h3-hermes-quant-field-trial-01"
RUNTIME = Path("/usr/local/lib/hermes-agent")
H3_WHEEL = H3 / "evidence/wheel/quant_hermes_h3-0.8.0a3-py3-none-any.whl"
H3_SHA = "75ce90539b6b6bfbe2fcf91c1ae4a144b9631b839a008160beb4f900e1f8a310"


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def checked(path, expected):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022 or sha(path) != expected:
        raise SystemExit(f"PIN_OR_PERMISSION_MISMATCH {path}")


def git(path, *args):
    return subprocess.check_output(
        ["git", "--no-optional-locks", *args], cwd=path, text=True
    ).strip()


def verify():
    for path, branch, head in (
        (CODE, "v0.8.0", "bd144f2d15836bb84786c91aec571df77351bf5c"),
        (DOCS, "docs/engineering", "a8e9c97cd08f17226ec49ef4c164b727d48a13a6"),
        (RUNTIME, None, "c2fa302e933aafc5f995696709a4179f54206c26"),
    ):
        if (
            git(path, "rev-parse", "HEAD") != head
            or (branch and git(path, "branch", "--show-current") != branch)
            or (path != RUNTIME and git(path, "status", "--porcelain", "--untracked-files=no"))
        ):
            raise SystemExit(f"BASELINE_MISMATCH {path}")
        print(f"PASS repo={path.name} head={head}")
    print(
        "Hermes host checkout tracked differences are bypassed by a local Git-verified source snapshot in QA."
    )
    for line in (ROOT / "tools/upstream-pins.sha256").read_text().splitlines():
        expected, name = line.split("  ", 1)
        full = CODE / name
        checked(full, expected)
        print(f"PASS {expected} {name}")
        if full.name == "SHA256SUMS":
            sealed_inventory(full)
    baseline = CODE / "baseline/PROGRAM_J_BASELINE_MANIFEST_20261118.json"
    rows = json.loads(baseline.read_text())["files"]
    if len(rows) != 323:
        raise SystemExit("LEGACY_INVENTORY_MISMATCH")
    for row in rows:
        path = baseline.parent / "program-j" / row["path"]
        checked(path, row["sha256"])
        if path.stat().st_size != row["bytes"]:
            raise SystemExit(f"LEGACY_SIZE_MISMATCH {path}")
    print("PASS Program J 323/323")
    list(dependencies("hermes-mixed"))
    checked(H3_WHEEL, H3_SHA)


def sealed_inventory(manifest):
    parent = manifest.parent
    rows = [line.split("  ", 1) for line in manifest.read_text().splitlines()]
    files = set()
    for path in parent.rglob("*"):
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or mode & 0o022:
            raise SystemExit(f"UNSAFE_ARCHIVE_PATH {path}")
        if stat.S_ISREG(mode) and path != manifest:
            files.add(path.relative_to(parent).as_posix())
    if len(rows) != len(files) or {name for _, name in rows} != files:
        raise SystemExit(f"SEALED_ARCHIVE_INVENTORY_MISMATCH {parent}")
    for expected, name in rows:
        checked(parent / name, expected)
    print(f"PASS archive={parent.name} entries={len(rows)}")


def dependencies(profile):
    for row in json.loads((H3 / "PINNED_DEPENDENCIES.json").read_text())["wheels"]:
        path = (H3 / row["file"]).resolve()
        if profile.startswith("canary"):
            if row["usage"] == "core" and not path.name.startswith(
                (
                    "quant_personal_public_b1",
                    "quant_personal_decision_b2",
                    "quant_personal_public_bridge_b4",
                    "cryptography",
                )
            ):
                continue
        if row["usage"] == "baseline-only" or (
            row["usage"] == "mixed" and not profile.endswith("-mixed")
        ):
            continue
        checked(path, row["sha256"])
        yield path, row["sha256"]
    if profile.startswith("hermes"):
        checked(H3_WHEEL, H3_SHA)
        yield H3_WHEEL, H3_SHA


def requirements(profile, candidate_wheels):
    for path, expected in dependencies(profile):
        print(f"{path.as_uri()} --hash=sha256:{expected}")
    for wheel in candidate_wheels:
        full = wheel.resolve(strict=True)
        print(f"{full.as_uri()} --hash=sha256:{sha(full)}")


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument(
        "--profile", choices=("canary-clean", "canary-mixed", "hermes-clean", "hermes-mixed")
    )
    cli.add_argument("candidate_wheels", type=Path, nargs="*")
    args = cli.parse_args()
    if args.profile:
        requirements(args.profile, args.candidate_wheels)
    else:
        verify()
