"""Closed-allowlist offline deployment bundle verification and safe materialization."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
import zipfile


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def safe_name(name):
    p = PurePosixPath(name)
    if not name or p.is_absolute() or ".." in p.parts or "\\" in name or ":" in name or p.as_posix() != name:
        raise ValueError("UNSAFE_BUNDLE_PATH:" + name)


def wheel_record(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        if len(set(names)) != len(names):
            raise ValueError("DUPLICATE_WHEEL_ENTRY")
        for name in names:
            safe_name(name.rstrip("/"))
        records = [n for n in names if n.endswith(".dist-info/RECORD") and len(PurePosixPath(n).parts) == 2]
        if len(records) != 1:
            raise ValueError("WHEEL_RECORD_MISSING")
        files = {n for n in names if not n.endswith("/")}
        rows = list(csv.reader(io.StringIO(archive.read(records[0]).decode())))
        if {r[0] for r in rows} != files or len(rows) != len(files):
            raise ValueError("WHEEL_RECORD_COVERAGE")
        for name, bound, size in rows:
            if name == records[0] and not bound and not size:
                continue
            algorithm, encoded = bound.split("=", 1)
            if algorithm != "sha256":
                raise ValueError("UNSUPPORTED_WHEEL_RECORD_HASH")
            content = archive.read(name)
            actual = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode()
            if actual != encoded or len(content) != int(size):
                raise ValueError("WHEEL_RECORD_HASH_MISMATCH")


def verify(root):
    root = Path(root)
    manifest = json.loads((root / "bundle_manifest.json").read_text())
    expected = set()
    for row in manifest["files"]:
        name = row["path"]
        safe_name(name)
        if name in expected:
            raise ValueError("DUPLICATE_BUNDLE_MANIFEST_ENTRY")
        expected.add(name)
        p = root / name
        if any(x.is_symlink() for x in (p, *p.absolute().parents)) or not p.is_file():
            raise ValueError("BUNDLE_FILE_UNTRUSTED:" + name)
        raw = p.read_bytes()
        if sha(raw) != row["sha256"] or len(raw) != row["bytes"]:
            raise ValueError("BUNDLE_HASH_MISMATCH:" + name)
        if name.endswith(".whl"):
            wheel_record(raw)
    for group in (
        "src",
        "tests",
        "tools",
        "deployment",
        "contracts",
        "configs",
        "fixtures",
        "inputs",
        "release/wheelhouse",
    ):
        for path in (root / group).rglob("*"):
            if (
                not path.is_file()
                or "__pycache__" in path.parts
                or any(p.endswith(".egg-info") for p in path.parts)
            ):
                continue
            if (
                path.suffix in {".py", ".json", ".jsonl", ".yaml", ".toml", ".pth", ".so", ".whl"}
                and path.relative_to(root).as_posix() not in expected
            ):
                raise ValueError("UNLISTED_BUNDLE_CODE_OR_ARTIFACT:" + str(path.relative_to(root)))
    return {
        "status": "PASS_EXACT_FROZEN_FILES",
        "files": len(expected),
        "host_qualified": False,
        "native_requests": 0,
    }


def materialize(packet, output):
    output = Path(output)
    if output.exists() or any(p.is_symlink() for p in (output, *output.absolute().parents)):
        raise ValueError("UNUSED_TRUSTED_MATERIALIZATION_REQUIRED")
    with zipfile.ZipFile(packet) as archive:
        names = archive.namelist()
        if len(set(names)) != len(names) or "bundle_manifest.json" not in names:
            raise ValueError("INVALID_BUNDLE_INDEX")
        manifest = json.loads(archive.read("bundle_manifest.json"))
        expected = {r["path"] for r in manifest["files"]} | {"bundle_manifest.json"}
        if set(names) != expected or len(names) != len(manifest["files"]) + 1:
            raise ValueError("BUNDLE_ALLOWLIST_MISMATCH")
        if sum(i.file_size for i in archive.infolist()) > 1073741824:
            raise ValueError("BUNDLE_SIZE_LIMIT")
        for name in names:
            safe_name(name)
            if stat.S_ISLNK(archive.getinfo(name).external_attr >> 16):
                raise ValueError("BUNDLE_SYMLINK")
        # Verify all bytes before writing any application payload.
        for row in manifest["files"]:
            raw = archive.read(row["path"])
            if sha(raw) != row["sha256"] or len(raw) != row["bytes"]:
                raise ValueError("BUNDLE_HASH_MISMATCH:" + row["path"])
            if row["path"].endswith(".whl"):
                wheel_record(raw)
        output.mkdir()
        for name in names:
            path = output / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(archive.read(name))
            path.chmod(0o644)
    return verify(output)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    v = sub.add_parser("verify")
    v.add_argument("root", type=Path)
    m = sub.add_parser("materialize")
    m.add_argument("packet", type=Path)
    m.add_argument("output", type=Path)
    args = p.parse_args()
    try:
        print(
            json.dumps(
                verify(args.root) if args.command == "verify" else materialize(args.packet, args.output)
            )
        )
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as exc:
        print(json.dumps({"status": "FAILED_BUNDLE_VERIFICATION", "reason": str(exc)}))
        raise SystemExit(2)
