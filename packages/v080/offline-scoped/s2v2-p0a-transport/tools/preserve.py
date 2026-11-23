"""Verify immutable inputs without invoking historical build or checkout scripts."""

import argparse
import hashlib
import json
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT.parents[1]
DOCS = CODE.parent / "quant-docs-engineering"


def sha(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def check(path, digest):
    mode = path.lstat().st_mode
    if not stat.S_ISREG(mode) or mode & 0o022 or sha(path) != digest:
        raise SystemExit(f"UNSAFE_OR_CHANGED_INPUT {path}")


def inventory(manifest):
    root = manifest.parent
    rows = []
    names = set()
    for line in manifest.read_text().splitlines():
        digest, name = line.split("  ", 1)
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or name in names:
            raise SystemExit(f"INVALID_INVENTORY_PATH {manifest} {name}")
        names.add(name)
        rows.append((digest, root / relative))
    paths = set()
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if relative.parts[0] == ".qa" and root in (
            ROOT,
            ROOT.parent / "lt-v080-sol62-personal-wsl2-s2v2-offline-01",
        ):
            continue
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or mode & 0o022:
            raise SystemExit(f"UNSAFE_ARCHIVE_PATH {path}")
        if stat.S_ISREG(mode) and path != manifest:
            paths.add(relative.as_posix())
    if paths != names:
        raise SystemExit(f"INVENTORY_MISMATCH {root}")
    for digest, path in rows:
        check(path, digest)
    print(f"PASS {root.name} {len(rows)}/{len(rows)} {sha(manifest)}")


def wheels(profile=None):
    for line in (ROOT / "tools/wheels.lock").read_text().splitlines():
        usage, digest, name = line.split(" ", 2)
        path = (CODE / name).resolve(strict=True)
        check(path, digest)
        if profile is not None and usage in ("common", profile):
            print(f"{path.as_uri()} --hash=sha256:{digest}")
        elif profile is None:
            print(f"PASS wheel {digest} {path.name}")


def git(path, *args):
    return subprocess.check_output(
        ["git", "--no-optional-locks", "-C", str(path), *args], text=True
    ).strip()


def verify():
    for path, branch, head in (
        (CODE, "v0.8.0", "bd144f2d15836bb84786c91aec571df77351bf5c"),
        (DOCS, "docs/engineering", "f7f6852ae7c73c5113c9e4f09a21a7c68adc4ad9"),
    ):
        actual = git(path, "rev-parse", "HEAD")
        if (
            actual != head
            or git(path, "branch", "--show-current") != branch
            or git(path, "status", "--porcelain", "--untracked-files=no")
        ):
            raise SystemExit(f"BASELINE_MISMATCH {path} {actual}")
        print(f"PASS {branch} {head}")
    for line in (ROOT / "tools/upstream-pins.sha256").read_text().splitlines():
        digest, name = line.split("  ", 1)
        path = CODE / name
        check(path, digest)
        if path.name == "SHA256SUMS":
            inventory(path)
        else:
            print(f"PASS {digest} {name}")
    manifest = CODE / "baseline/PROGRAM_J_BASELINE_MANIFEST_20261118.json"
    data = json.loads(manifest.read_text())["files"]
    if len(data) != 323:
        raise SystemExit("PROGRAM_J_INVENTORY_MISMATCH")
    for row in data:
        path = manifest.parent / "program-j" / row["path"]
        check(path, row["sha256"])
        if path.stat().st_size != row["bytes"]:
            raise SystemExit(f"PROGRAM_J_SIZE_MISMATCH {path}")
    print("PASS Program J 323/323")
    wheels()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--wheels", choices=("staged", "canary"))
    group.add_argument("--seal", action="store_true")
    args = parser.parse_args()
    if args.wheels:
        wheels(args.wheels)
    elif args.seal:
        inventory(ROOT / "SHA256SUMS")
    else:
        verify()
