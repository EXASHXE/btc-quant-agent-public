"""Materialize only the sealed J code allowlist and verified offline wheels."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from build_release import deterministic_zip
from deployment.bundle import safe_name, wheel_record

ROOT = Path(__file__).resolve().parents[1]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def packet(path, files):
    entries = []
    for name, raw in sorted(files.items()):
        safe_name(name)
        if name.endswith(".whl"):
            wheel_record(raw)
        entries.append({"path": name, "bytes": len(raw), "sha256": digest(raw)})
    manifest = {
        "schema": "J_EXACT_PUBLIC_PACKET_V1",
        "evidence_class": "CODE_AND_OFFLINE_DEPENDENCIES_ONLY",
        "files": entries,
    }
    payload = {
        **files,
        "bundle_manifest.json": (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
    }
    deterministic_zip(path, payload)
    repeated = path.with_suffix(".repeat.zip")
    deterministic_zip(repeated, payload)
    assert path.read_bytes() == repeated.read_bytes(), "J_PACKET_REPRODUCIBILITY_FAILURE"
    repeated.unlink()
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": digest(path.read_bytes()),
        "bytes": path.stat().st_size,
        "files": len(entries),
        "repeat_identical": True,
    }


def main():
    manifest_path = ROOT / "audit/code_manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    files = {}
    for row in manifest["files"]:
        name = row["path"]
        safe_name(name)
        p = ROOT / name
        assert not p.is_symlink(), "J_PUBLIC_SYMLINK_FORBIDDEN"
        raw = p.read_bytes()
        assert digest(raw) == row["sha256"], "J_CODE_ALLOWLIST_CHANGED:" + name
        # Accepted scanners contain header literals; reject actual PEM payloads.
        assert not re.search(
            rb"-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----\r?\n[A-Za-z0-9+/=]{32,}", raw
        ), "J_PRIVATE_KEY_FORBIDDEN"
        files[name] = raw
    files["audit/code_manifest.json"] = manifest_path.read_bytes()
    source = packet(ROOT / "release/J_public_source_review.zip", files)
    wheel_paths = set()
    for name in ("dependency_provenance.json", "toolchain_provenance.json"):
        p = ROOT / "release" / name
        files["release/" + name] = p.read_bytes()
        for row in json.loads(p.read_bytes()):
            target = row["path"]
            safe_name(target)
            raw = (ROOT / target).read_bytes()
            assert digest(raw) == row["sha256"], "J_DEPENDENCY_HASH_CHANGED"
            files[target] = raw
            wheel_paths.add(target)
    for name in ("requirements-lock.txt", "toolchain-lock.txt", "dependency_record_deviations.json"):
        files["release/" + name] = (ROOT / "release" / name).read_bytes()
    offline = packet(ROOT / "release/J_offline_release.zip", files)
    receipt = {
        "status": "PUBLIC_SAFE_REVIEW_PACKET_READY",
        "publication": "LOCAL_PACKET_ONLY_NO_PR_PUSH_MERGE_OR_DEPLOYMENT",
        "source_packet": source,
        "offline_packet": offline,
        "verified_distributions": len(wheel_paths),
        "compatibility": "TESTED_LINUX_X86_64_CPYTHON_3_13_ONLY",
        "genuine_data_or_authority_included": False,
        "strict_source_qualified": False,
    }
    (ROOT / "J7_PUBLIC_RELEASE_PACKET.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
