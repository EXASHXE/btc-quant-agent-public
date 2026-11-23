"""Verify immutable baselines, upstream seals, pinned patch, receipts, and build requirements."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

WORKROOT = Path(__file__).resolve().parents[1]
REPO = WORKROOT.parents[1]
DOCS = REPO.parent / "quant-docs-engineering"
QUANT070 = REPO.parent / "quant-0.7.0"

CODE_BRANCH = "v0.8.0"
CODE_HEAD = "bd144f2d15836bb84786c91aec571df77351bf5c"
DOCS_BRANCH = "docs/engineering"
DOCS_HEAD = "a089c9e4b37f0e2cddd3592aa60a0cc61aa89784"

TASK_CARD_SHA256 = "55a2ead2c772e43ca5c726664743927561ec01ea83e4b5fabbd6b54eb6d02ea4"

UPSTREAM_SEALS = {
    "lt-v080-sol62-h2a-b5-phaseb-activation-01":
        ("b6be8e070fbd55d2a15c5443ab49eabe1bda62dc5f6396ab1d6a4996d8085a16", 69),
    "lt-v080-sol62-s3-market-offline-readiness-01":
        ("cd19490333992fd972849eb54a098bea01667f95d0fb7595ea61ea60533c99fb", 31),
    "lt-v080-astra-s3-minimum-data-admission-01":
        ("fd67aa64c72bc9acb4d61aae81fb727298fc65d8fe2d65dd540848f25db6d9e5", 9),
    "lt-v080-sol62-wsl2-local-runtime-readiness-01":
        ("56bd017ecf0aa2fcf41b60ed6d0d8f17509b1a9070e566a4501122c51afbc44d", 50),
    "lt-v080-personal-mvp-live-public-b5-01":
        ("2b4b5e36cc914fda5f748ba71a31f0cae4fdedaecbfbf9980ecbb6bf335edd09", None),
    "lt-v080-personal-mvp-public-source-bridge-b4-01":
        ("127fcb635d70096bace47949c69d2bb9c5629460d27b3adf02c457f02c438216", None),
    "lt-v080-sol62-personal-mvp-market-decision-b2-01":
        ("8c908905eaa8002e12f53f1d78939b15726658726c20b19abc66c673c6a58368", None),
    "lt-v080-sol62-personal-mvp-public-runtime-foundation-b1-01":
        ("73af3d2e273e9d4c6865fe3fe935939c4ae64a7a1475c4bb0ab99ceef319f7a5", None),
    "lt-v080-personal-mvp-account-aware-b3-01":
        ("b652ffdc79a0392612c19f02542df3713baf0ab82bd12af5c0eae017c596e54b", None),
    "lt-v080-sol62-personal-mvp-layer1-public-01":
        ("78125e1549de4b8d9e13e1d1c97ec0e5d66cdd9ebcd0c241e069d37ee396d365", None),
}

CONTROLLER_RECEIPTS = {
    "controller-decisions/V080_CONTROLLER_NEON_S3_ZERO_RETRY_OFFLINE_ENGINEERING_DISPATCH_20261123.json":
        "14d4d1bbbea5595648d28111fcc4e18f11dc3d61562ad925a0fb95863c9eef9d",
    "controller-decisions/V080_CONTROLLER_H2A_B5_PHASEB_OFFLINE_SCOPED_ACCEPTANCE_20261120.json":
        "bf4c582f1b6b1d4083c87c26e2d99a2248390340f2aa14aa19266930ccc5e2a5",
    "controller-decisions/V080_CONTROLLER_S3_ADMISSION_RESEARCH_SCOPED_ACCEPTANCE_20261122.json":
        "41538880277d065953deeda4dd02247d36be9f002629ba1f3ad846adb7560f4e",
    "controller-decisions/V080_CONTROLLER_P0A_S2V2_TRANSPORT_OFFLINE_SCOPED_ACCEPTANCE_20261123.json":
        "fcf4b56fabfd70fada06b8217d5fd788ba9d5151d1cf4cddf6237cd21142db9e",
    "controller-decisions/V080_CONTROLLER_P0B_KR_WSL2_EVIDENCE_OFFLINE_SCOPED_ACCEPTANCE_20261123.json":
        "816058e895b475ef3b1915423d91b572e257f126f6ca00cde55f64c083298ac6",
    "controller-decisions/V080_CONTROLLER_P0_DUAL_QA_CONSOLIDATED_ACCEPTANCE_AND_QUEUE_20261123.json":
        "caf4dfcdbb0d408c56e0c84b9974b7ed0dbacc4a47ddf6749092a3080b106be1",
}

PATCH_PATH = REPO / "workspaces/lt-v080-sol62-wsl2-local-runtime-readiness-01/proposals/H2A_SIGNED_ZERO_RETRY_V2.patch"
PATCH_SHA256 = "c4ec40dea271b61124099db3addbeb61cfd9dd62f85012f00f9f88feafab3fca"

WHEELS = {
    "b1": (
        REPO / "workspaces/lt-v080-sol62-personal-mvp-public-runtime-foundation-b1-01/evidence/wheel/quant_personal_public_b1-0.8.0b1-py3-none-any.whl",
        "19d89bd87721733dbe05a1298f157e8ea15258fd1d4b981dd5e11e34b05a544f",
    ),
    "b2": (
        REPO / "workspaces/lt-v080-sol62-personal-mvp-market-decision-b2-01/evidence/wheel/quant_personal_decision_b2-0.8.0b2-py3-none-any.whl",
        "29cce34ff2b751ef9a9d305d3b7591281a6028c0057e360c9eb666b0840fed64",
    ),
    "b3": (
        REPO / "workspaces/lt-v080-personal-mvp-account-aware-b3-01/evidence/wheel/quant_personal_account_b3-0.8.0b3-py3-none-any.whl",
        "ed11906d6b23b74ef90984a44a7c6cadfff68543bee7f9715226af366f769c5f",
    ),
    "b4": (
        REPO / "workspaces/lt-v080-personal-mvp-public-source-bridge-b4-01/evidence/wheel/quant_personal_public_bridge_b4-0.8.0b4-py3-none-any.whl",
        "c30332d0028b14f2c7ee89ef941be3e9d51f1ff500231bb9cbcaae95a63c7710",
    ),
    "b5": (
        REPO / "workspaces/lt-v080-personal-mvp-live-public-b5-01/evidence/wheel/quant_personal_live_public_b5-0.8.0b5-py3-none-any.whl",
        "eb6076a3a98f3fa82512a2b748d8cbf44333ca9f56dec265b163c6f6857ddab3",
    ),
    "h2a": (
        REPO / "workspaces/lt-v080-sol62-h2a-b5-phaseb-activation-01/evidence/wheel/quant_personal_live_public_b5-0.8.0b5.post1-py3-none-any.whl",
        "35e8968a5af9c17ee4dcbed3fe3f8f442368af302f1e35f93e394664c8902fbd",
    ),
    "r1": (
        REPO / "workspaces/lt-v080-sol62-personal-mvp-layer1-public-01/evidence/wheel/quant_advisory_platform-0.8.0-py3-none-any.whl",
        "7f7877fe4b0efc5c1456ea02d91a91f78cbd99f2ee3ad8dd6853e87ea86f6fcc",
    ),
    "cryptography": (
        QUANT070 / "lt-program-j-realtime-advisory-01/release/wheelhouse/cryptography-45.0.7-cp311-abi3-manylinux_2_34_x86_64.whl",
        "b6a0e535baec27b528cb07a119f321ac024592388c5681a5ced167ae98e9fff3",
    ),
}

FROZEN_V1_PATH = DOCS / "docs/architecture/V080_QUANT_AGENT_CONTRACT_V1_20261120.md"
FROZEN_V1_SHA256 = "622677b019120ed18d9bfea057589f7bf923f7f15e17adb3ac59831a0bfd8cc2"
PROGRAM_J_MANIFEST = REPO / "baseline/PROGRAM_J_BASELINE_MANIFEST_20261118.json"
PROGRAM_J_MANIFEST_SHA256 = "9796870e41ed19188dcfe003f45b8f0edcb3826e408d3e46966d0626374b635b"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_sha(path: Path, expected: str) -> str:
    actual = sha256_file(path)
    if actual != expected:
        raise SystemExit(f"HASH_MISMATCH {path}: expected {expected}, got {actual}")
    return actual


def git(cwd: Path, *args: str) -> str:
    return subprocess.check_output(["git", "--no-optional-locks", *args], cwd=cwd, text=True).strip()


def emit_requirements(profile: str, candidate_wheel: Path | None) -> None:
    if profile == "clean":
        if candidate_wheel is None:
            raise SystemExit("candidate wheel required for clean profile")
        items = [(candidate_wheel, sha256_file(candidate_wheel)), WHEELS["b1"], WHEELS["b2"], WHEELS["b4"]]
    elif profile == "clean-verifier":
        if candidate_wheel is None:
            raise SystemExit("candidate wheel required for clean-verifier profile")
        items = [
            (candidate_wheel, sha256_file(candidate_wheel)),
            WHEELS["b1"], WHEELS["b2"], WHEELS["b4"], WHEELS["cryptography"],
        ]
    elif profile == "mixed":
        if candidate_wheel is None:
            raise SystemExit("candidate wheel required for mixed profile")
        items = [
            (candidate_wheel, sha256_file(candidate_wheel)),
            WHEELS["b1"], WHEELS["b2"], WHEELS["b4"], WHEELS["b3"], WHEELS["r1"], WHEELS["cryptography"],
        ]
    elif profile == "legacy-h2a":
        items = [WHEELS["h2a"], WHEELS["b1"], WHEELS["b2"], WHEELS["b4"], WHEELS["cryptography"]]
    elif profile == "legacy-b5":
        items = [WHEELS["b5"], WHEELS["b1"], WHEELS["b2"], WHEELS["b4"], WHEELS["cryptography"]]
    else:
        raise SystemExit(f"Unknown requirements profile: {profile}")
    for path, digest in items:
        resolved = path.resolve()
        if profile in ("legacy-h2a", "legacy-b5") or path != candidate_wheel:
            check_sha(resolved, digest)
        print(f"{resolved.as_uri()} --hash=sha256:{digest}")


def verify_workroot_seal() -> None:
    manifest = WORKROOT / "SHA256SUMS"
    if not manifest.is_file():
        raise SystemExit("MISSING_WORKROOT_SHA256SUMS")
    subprocess.run(["sha256sum", "--quiet", "-c", "SHA256SUMS"], cwd=WORKROOT, check=True)
    count = len(manifest.read_text(encoding="ascii").splitlines())
    print(f"PASS workroot SHA256SUMS ({count} files)")


def verify_all() -> None:
    for repo, branch, head in (
        (REPO, CODE_BRANCH, CODE_HEAD),
        (DOCS, DOCS_BRANCH, DOCS_HEAD),
    ):
        actual_branch = git(repo, "branch", "--show-current")
        actual_head = git(repo, "rev-parse", "HEAD")
        dirty = git(repo, "status", "--porcelain=v1", "--untracked-files=no")
        if actual_branch != branch or actual_head != head or dirty:
            raise SystemExit(f"BASELINE_CONFLICT {repo}: branch={actual_branch} head={actual_head} dirty={bool(dirty)}")
        print(f"PASS git {branch}@{head} tracked-clean")

    check_sha(WORKROOT / "CONTROLLER_OFFLINE_TASK.md", TASK_CARD_SHA256)
    check_sha(WORKROOT / "OWNER_CONTROLLER_TASK.md", TASK_CARD_SHA256)
    print(f"PASS task card {TASK_CARD_SHA256}")

    check_sha(PATCH_PATH, PATCH_SHA256)
    print(f"PASS three-file patch {PATCH_SHA256}")

    for name, (expected, expected_count) in UPSTREAM_SEALS.items():
        root = REPO / "workspaces" / name
        manifest = root / "SHA256SUMS"
        check_sha(manifest, expected)
        subprocess.run(["sha256sum", "--quiet", "-c", "SHA256SUMS"], cwd=root, check=True)
        count = len(manifest.read_text(encoding="ascii").splitlines())
        if expected_count is not None and count != expected_count:
            raise SystemExit(f"SEAL_COUNT_MISMATCH {name}: expected {expected_count}, got {count}")
        print(f"PASS seal {name} ({count} files) {expected}")

    for rel, expected in CONTROLLER_RECEIPTS.items():
        check_sha(REPO / rel, expected)
        print(f"PASS receipt {rel} {expected}")

    for label, (path, expected) in WHEELS.items():
        check_sha(path, expected)
        print(f"PASS wheel {label} {path.name} {expected}")

    check_sha(FROZEN_V1_PATH, FROZEN_V1_SHA256)
    print(f"PASS frozen V1 contract {FROZEN_V1_SHA256}")

    check_sha(PROGRAM_J_MANIFEST, PROGRAM_J_MANIFEST_SHA256)
    rows = json.loads(PROGRAM_J_MANIFEST.read_text(encoding="utf-8"))["files"]
    for row in rows:
        target = REPO / "baseline/program-j" / row["path"]
        check_sha(target, row["sha256"])
        if target.stat().st_size != row["bytes"]:
            raise SystemExit(f"PROGRAM_J_SIZE_MISMATCH {target}")
    print(f"PASS Program J baseline ({len(rows)} files) {PROGRAM_J_MANIFEST_SHA256}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", choices=("clean", "clean-verifier", "mixed", "legacy-h2a", "legacy-b5"))
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--seal", action="store_true")
    args = parser.parse_args(argv)
    if args.requirements:
        emit_requirements(args.requirements, args.wheel)
        return 0
    if args.seal:
        verify_workroot_seal()
        return 0
    verify_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
