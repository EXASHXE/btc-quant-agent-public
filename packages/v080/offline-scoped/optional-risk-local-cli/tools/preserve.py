"""Verify canonical git baselines, Program J, accepted workroot seals, and pinned wheels."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT.parents[1]
DOCS = CODE.parent / "quant-docs-engineering"


def sha(path: Path) -> str:
    with path.open("rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def check_file(path: Path, expected: str) -> None:
    mode = path.lstat().st_mode
    if not stat.S_ISREG(mode) or mode & 0o022 or sha(path) != expected:
        raise SystemExit(f"UNSAFE_OR_CHANGED_INPUT {path}")


def check_inventory(manifest: Path) -> None:
    root = manifest.parent
    rows: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        digest, name = line.split("  ", 1)
        rel = Path(name)
        if rel.is_absolute() or ".." in rel.parts or name in seen:
            raise SystemExit(f"INVALID_INVENTORY_PATH {manifest} {name}")
        seen.add(name)
        rows.append((digest, root / rel))
    actual: set[str] = set()
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if root == ROOT and rel.parts[0] == ".qa":
            continue
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or mode & 0o022:
            raise SystemExit(f"UNSAFE_ARCHIVE_PATH {path}")
        if stat.S_ISREG(mode) and path != manifest:
            actual.add(rel.as_posix())
    if actual != seen:
        raise SystemExit(f"INVENTORY_MISMATCH {root}")
    for digest, path in rows:
        check_file(path, digest)
    print(f"PASS archive={root.name} entries={len(rows)} sha256={sha(manifest)}")


def emit_wheels(profile: str | None = None, *, extra_wheel: Path | None = None) -> None:
    for line in (ROOT / "tools/wheels.lock").read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        usage, digest, rel = line.split(" ", 2)
        path = (CODE / rel).resolve(strict=True)
        check_file(path, digest)
        if profile is not None:
            include = (usage == "core") or (profile == "full" and usage == "full")
            if include:
                print(f"{path.as_uri()} --hash=sha256:{digest}")
        else:
            print(f"PASS wheel {digest} {path.name}")
    if profile is not None and extra_wheel is not None:
        resolved = extra_wheel.resolve(strict=True)
        print(f"{resolved.as_uri()} --hash=sha256:{sha(resolved)}")


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "--no-optional-locks", "-C", str(repo), *args], text=True
    ).strip()


def verify_all() -> None:
    for repo, branch, head in (
        (CODE, "v0.8.0", "bd144f2d15836bb84786c91aec571df77351bf5c"),
        (DOCS, "docs/engineering", "f7f6852ae7c73c5113c9e4f09a21a7c68adc4ad9"),
    ):
        actual = git(repo, "rev-parse", "HEAD")
        if (
            actual != head
            or git(repo, "branch", "--show-current") != branch
            or git(repo, "status", "--porcelain", "--untracked-files=no")
        ):
            raise SystemExit(f"BASELINE_MISMATCH {repo} {actual}")
        print(f"PASS repo={repo.name} branch={branch} head={head}")

    for line in (ROOT / "tools/upstream-pins.sha256").read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        digest, rel = line.split("  ", 1)
        target = CODE / rel
        check_file(target, digest)
        if target.name == "SHA256SUMS":
            check_inventory(target)
        else:
            print(f"PASS pin={digest} {rel}")

    pj = CODE / "baseline/PROGRAM_J_BASELINE_MANIFEST_20261118.json"
    files = json.loads(pj.read_text(encoding="utf-8"))["files"]
    if len(files) != 323:
        raise SystemExit("PROGRAM_J_COUNT_MISMATCH")
    for row in files:
        p = pj.parent / "program-j" / row["path"]
        check_file(p, row["sha256"])
        if p.stat().st_size != row["bytes"]:
            raise SystemExit(f"PROGRAM_J_SIZE_MISMATCH {p}")
    print("PASS Program J 323/323")
    emit_wheels()


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--wheels", choices=("core", "full"))
    group.add_argument("--seal", action="store_true")
    parser.add_argument("--extra-wheel", type=Path)
    args = parser.parse_args()
    if args.wheels:
        emit_wheels(args.wheels, extra_wheel=args.extra_wheel)
    elif args.seal:
        check_inventory(ROOT / "SHA256SUMS")
    else:
        verify_all()


if __name__ == "__main__":
    main()
