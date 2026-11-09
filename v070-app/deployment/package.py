"""Build public code and portable offline packets; never transfers or deploys them."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_release import deterministic_zip  # noqa:E402
from deployment.bundle import materialize, wheel_record  # noqa:E402


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    original = json.loads((ROOT / "deployment/accepted_application_manifest.json").read_text())
    files = {}
    for row in original["files"]:
        raw = (ROOT / row["path"]).read_bytes()
        if sha(raw) != row["sha256"]:
            raise ValueError("ACCEPTED_F_APPLICATION_MUTATION:" + row["path"])
        files[row["path"]] = raw
    for group in ("deployment", "tests/host"):
        for path in (ROOT / group).rglob("*"):
            if path.is_file() and path.suffix in {".py", ".json"}:
                files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    files["README_G_OPERATOR.md"] = (ROOT / "README_G_OPERATOR.md").read_bytes()
    for name, raw in files.items():
        if any(
            line in {b"-----BEGIN PRIVATE KEY-----", b"-----BEGIN OPENSSH PRIVATE KEY-----"}
            for line in raw.splitlines()
        ):
            raise ValueError("SECRET_IN_PUBLIC_PACKET:" + name)
        if (ROOT / name).is_symlink():
            raise ValueError("SYMLINK_IN_PUBLIC_PACKET:" + name)
    rows = [{"path": n, "sha256": sha(raw), "bytes": len(raw)} for n, raw in sorted(files.items())]
    code = {
        "schema": "G_EXACT_CODE_ALLOWLIST_V1",
        "file_count": len(rows),
        "files": rows,
        "unchanged_accepted_F_files": len(original["files"]),
        "application_modifications": 0,
        "exclusions": [
            "private keys/signatures/live grants",
            "captured observations, research/holdout, raw host metadata",
            "venvs, caches, datasets and dependency binaries",
        ],
    }
    (ROOT / "audit/code_manifest.json").write_text(json.dumps(code, indent=2, sort_keys=True) + "\n")
    files["audit/code_manifest.json"] = (ROOT / "audit/code_manifest.json").read_bytes()
    release = ROOT / "release"
    for suffix in ("", "-repeat"):
        deterministic_zip(release / f"G_code{suffix}.zip", files)
    assert (release / "G_code.zip").read_bytes() == (release / "G_code-repeat.zip").read_bytes()
    for name in (
        "requirements-lock.txt",
        "dependency_provenance.json",
        "dependency_record_deviations.json",
        "toolchain-lock.txt",
        "toolchain_provenance.json",
    ):
        files["release/" + name] = (release / name).read_bytes()
    provenance = json.loads((release / "toolchain_provenance.json").read_text())
    for row in provenance:
        path = ROOT / row["path"]
        raw = path.read_bytes()
        if sha(raw) != row["sha256"]:
            raise ValueError("DEPENDENCY_ARTIFACT_CHANGED:" + row["name"])
        wheel_record(raw)
        files[row["path"]] = raw
    manifest = {
        "schema": "G_PORTABLE_BUNDLE_V1",
        "files": [{"path": n, "sha256": sha(raw), "bytes": len(raw)} for n, raw in sorted(files.items())],
        "trust": "Checksums freeze artifacts; they do not authorize native access or qualify a host.",
    }
    files["bundle_manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    for suffix in ("", "-repeat"):
        deterministic_zip(release / f"G_portable{suffix}.zip", files)
    portable = release / "G_portable.zip"
    assert portable.read_bytes() == (release / "G_portable-repeat.zip").read_bytes()
    (release / "G_portable.zip.sha256").write_text(sha(portable.read_bytes()) + "  G_portable.zip\n")
    result = materialize(portable, release / "G_portable_materialized")
    report = {
        "status": "PORTABLE_PACKET_READY_HOST_NOT_YET_QUALIFIED",
        "platform_contract": "deployment/platform_contract.json",
        "prerequisite": "Separately approved Linux x86_64/glibc>=2.39 host with CPython3.13.13 already supplied; interpreter itself is not bundled or provisioned.",
        "portable_bundle": "release/G_portable.zip",
        "portable_sha256": sha(portable.read_bytes()),
        "portable_bytes": portable.stat().st_size,
        "repeat_bytes_identical": True,
        "materialized": "release/G_portable_materialized",
        "verification": result,
        "dependency_distributions": len(provenance),
        "source_code_files": len(rows),
        "F_wheel_unchanged_sha256": json.loads((ROOT / "deployment/accepted_release.json").read_text())[
            "wheel_sha256"
        ],
        "alternative_host_tested": False,
        "transfer_or_provisioning": False,
        "native_requests": 0,
    }
    (ROOT / "G2_PORTABLE_RELEASE_BUNDLE.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    publication = {
        "status": "PUBLIC_SAFE_CODE_PACKET_PREPARED_LOCAL_ONLY",
        "packet": "release/G_code.zip",
        "sha256": sha((release / "G_code.zip").read_bytes()),
        "code_manifest_sha256": sha((ROOT / "audit/code_manifest.json").read_bytes()),
        "canonical_docs": "docs/engineering",
        "remote_PR_or_branch_changed": False,
        "merge_force_push_deployment": False,
        "private_signing_keys_or_live_grants": False,
    }
    (ROOT / "G7_PUBLICATION_PACKET.json").write_text(json.dumps(publication, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
