"""Seal a code-only publication packet and deterministic clean materialization."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import os
import sys

from build_release import deterministic_zip

ROOT = Path(__file__).resolve().parents[1]


def main():
    files = []
    for group in ("src", "tests", "tools", "contracts", "configs", "fixtures", "inputs"):
        files.extend(
            p
            for p in (ROOT / group).rglob("*")
            if p.is_file()
            and p.suffix in {".py", ".json", ".jsonl", ".yaml"}
            and "__pycache__" not in p.parts
            and ".egg-info" not in p.as_posix()
        )
    files.extend(
        ROOT / name
        for name in (
            "pyproject.toml",
            "frozen_protocol.json",
            "README_OPERATOR.md",
            "README_NATIVE_OPERATOR.md",
            "README_F_OPERATOR.md",
            ".gitignore",
            "audit/original_verifier.json",
        )
    )
    rows = []
    content = {}
    for p in sorted(set(files)):
        raw = p.read_bytes()
        if p.is_symlink() or any(
            line in {b"-----BEGIN PRIVATE KEY-----", b"-----BEGIN OPENSSH PRIVATE KEY-----"}
            for line in raw.splitlines()
        ):
            raise ValueError("PUBLIC_SECRET_OR_SYMLINK_REJECTED:" + str(p))
        name = str(p.relative_to(ROOT))
        content[name] = raw
        rows.append({"path": name, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
    manifest = {
        "schema": "F_EXACT_CODE_ALLOWLIST_V1",
        "file_count": len(rows),
        "files": rows,
        "exclusions": [
            "Native and generated QA capture evidence",
            "Owner/auditor keys/signatures/private grants; shipped authority JSON is an EMPTY default-deny stub",
            "Protected research and holdout",
            "Dependencies and virtual environments",
            "Caches, bytecode and tests temporary outputs",
        ],
        "content_root_sha256": hashlib.sha256(
            json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }
    path = ROOT / "audit/code_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    content["audit/code_manifest.json"] = path.read_bytes()
    release = ROOT / "release"
    for name in (
        "quant-v070-native-qualification-code.zip",
        "quant-v070-native-qualification-code-repeat.zip",
    ):
        deterministic_zip(release / name, content)
    assert (release / "quant-v070-native-qualification-code.zip").read_bytes() == (
        release / "quant-v070-native-qualification-code-repeat.zip"
    ).read_bytes()
    materialized = release / "public_qualification_source"
    materialized.mkdir(exist_ok=False)
    for name, raw in content.items():
        target = materialized / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    out = release / "materialized_qualification_build"
    out.mkdir(exist_ok=False)
    command = "import setuptools.build_meta as b;b.build_wheel(" + repr(str(out)) + ")"
    result = subprocess.run(
        [sys.executable, "-B", "-c", command],
        cwd=materialized,
        env={**os.environ, "SOURCE_DATE_EPOCH": "1767225600", "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
    )
    (ROOT / "audit/materialized_build.log").write_text(result.stdout + result.stderr)
    result.check_returncode()
    wheel = next(out.glob("*.whl"))
    built = release / "wheelhouse" / wheel.name
    assert wheel.read_bytes() == built.read_bytes()
    packet = {
        "status": "PUBLIC_SAFE_CODE_PACKET_READY_NOT_PUBLISHED",
        "destination_prefix": "releases/quant-v070-native-qualification-rc",
        "source_packet": "release/quant-v070-native-qualification-code.zip",
        "source_packet_sha256": hashlib.sha256(
            (release / "quant-v070-native-qualification-code.zip").read_bytes()
        ).hexdigest(),
        "code_manifest_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "exact_allowlist": rows,
        "public_files": len(content),
        "remote_branch_or_PR_created": False,
        "PR12_modified": False,
        "force_push": False,
        "merged": False,
        "deployment": False,
        "canonical_planning_authority": "docs/engineering",
        "build_materialization": "release/public_qualification_source",
        "repeat_source_packet_identical": True,
        "materialized_wheel_identical": True,
    }
    (ROOT / "F7_PUBLICATION_PACKET.json").write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n")
    receipt = {
        "status": "PASS_LOCAL_REPRODUCIBLE",
        "wheel": str(built.relative_to(ROOT)),
        "wheel_sha256": hashlib.sha256(built.read_bytes()).hexdigest(),
        "SOURCE_DATE_EPOCH": 1767225600,
        "repeat_build_byte_identical": True,
        "clean_materialization_byte_identical": True,
        "offline_install": "audit/clean_install.log",
        "pip_check": "audit/clean_pip_check.log",
        "dependency_lock_sha256": hashlib.sha256(
            (release / "requirements-lock.txt").read_bytes()
        ).hexdigest(),
        "dependency_provenance": "release/dependency_provenance.json",
        "publication": "F7_PUBLICATION_PACKET.json",
        "scope": "Linux x86_64/Python3.13 local dependency wheels; native Windows not run",
    }
    (ROOT / "F7_REPRODUCIBLE_RELEASE.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "status": packet["status"],
                "code_files": len(rows),
                "public_files": len(content),
                "code_manifest_sha256": packet["code_manifest_sha256"],
                "wheel_sha256": receipt["wheel_sha256"],
            }
        )
    )


if __name__ == "__main__":
    main()
