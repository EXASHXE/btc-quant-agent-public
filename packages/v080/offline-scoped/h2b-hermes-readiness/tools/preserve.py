"""Verify all accepted upstream baselines, contracts, H1, H2-A, P1, Hermes v0.16.0, and clean git trees."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
CODE = WORKSPACE.parents[1]
DOCS = CODE.parent / "quant-docs-engineering"
HERMES = Path("/usr/local/lib/hermes-agent")
REAL_HERMES_HOME = Path("/root/.hermes")

SEALS = {
    "lt-v080-gemini-neon-hermes-quant-feishu-h1-01": (
        "577816c61c72591977241b203a4c80b52d0668ea1485bdfb255851b7b50188f2",
        57,
    ),
    "lt-v080-gemini-neon-hermes-h1-p0-interop-fix-01": (
        "90ff56de9175191e771b3de613aedf19267213ee842bec6f87b84817038268d4",
        71,
    ),
    "lt-v080-sol62-h2a-b5-phaseb-activation-01": (
        "b6be8e070fbd55d2a15c5443ab49eabe1bda62dc5f6396ab1d6a4996d8085a16",
        69,
    ),
    "lt-v080-astra-pi-quant-agent-architecture-p1-01": (
        "0d54ec08f264af77dc9bc80e655236ff03fbc04efd73e678a06f70474ff46acd",
        7,
    ),
    "lt-v080-personal-mvp-live-public-b5-01": (
        "2b4b5e36cc914fda5f748ba71a31f0cae4fdedaecbfbf9980ecbb6bf335edd09",
        58,
    ),
    "lt-v080-personal-mvp-public-source-bridge-b4-01": (
        "127fcb635d70096bace47949c69d2bb9c5629460d27b3adf02c457f02c438216",
        50,
    ),
    "lt-v080-personal-mvp-account-aware-b3-01": (
        "b652ffdc79a0392612c19f02542df3713baf0ab82bd12af5c0eae017c596e54b",
        183,
    ),
    "lt-v080-sol62-personal-mvp-market-decision-b2-01": (
        "8c908905eaa8002e12f53f1d78939b15726658726c20b19abc66c673c6a58368",
        93,
    ),
    "lt-v080-sol62-personal-mvp-public-runtime-foundation-b1-01": (
        "73af3d2e273e9d4c6865fe3fe935939c4ae64a7a1475c4bb0ab99ceef319f7a5",
        56,
    ),
    "lt-v080-sol62-personal-mvp-layer1-public-01": (
        "78125e1549de4b8d9e13e1d1c97ec0e5d66cdd9ebcd0c241e069d37ee396d365",
        367,
    ),
    "lt-v080-astra-full-system-arch-audit-roadmap-01": (
        "c946b0ef804c0b19c6dd9b9c1f75a7986493f3ff8d6d1872e1119a0c48b9d85d",
        5,
    ),
}

RECEIPTS = {
    "V080_CONTROLLER_H2B_HERMES_FEISHU_OFFLINE_ENGINEERING_DISPATCH_20261120.json":
        "738588a5207bf35d22705e69b7df571c27069caa90bbb5163e6849898ab8af43",
    "V080_CONTROLLER_H1_P0_OFFLINE_REFERENCE_SCOPED_ACCEPTANCE_20261120.json":
        "ed7116fbbb5f3f6ced9434825cd7d318a18c1cf5df2aba3fe752f60dee209e39",
    "V080_CONTROLLER_H2A_B5_PHASEB_OFFLINE_SCOPED_ACCEPTANCE_20261120.json":
        "bf4c582f1b6b1d4083c87c26e2d99a2248390340f2aa14aa19266930ccc5e2a5",
    "V080_CONTROLLER_H1_INDEPENDENT_P0_HOLD_20261120.json":
        "3293b8d04468ab408a21ba7b284621f32023b81a3f0accf08b655473679093fe",
    "V080_CONTROLLER_P1_PI_ARCHITECTURE_ACCEPTANCE_20261120.json":
        "c367c8c6188fb6ec51cdc316e4260b2f35486d82781e7eee6c72fcc6e1ba4999",
}


def check_sha(path: Path, expected: str) -> str:
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise SystemExit(f"HASH_MISMATCH {path}: actual={actual} expected={expected}")
    return actual


def git(cwd: Path, *args: str) -> str:
    return subprocess.check_output(["git", "--no-optional-locks", *args], cwd=cwd, text=True).strip()


def main() -> None:
    for repo, branch, head in (
        (CODE, "v0.8.0", "bd144f2d15836bb84786c91aec571df77351bf5c"),
        (DOCS, "docs/engineering", "cd57a397bd887db703d1354608a8d18a7e03f73d"),
    ):
        cur_branch = git(repo, "branch", "--show-current")
        cur_head = git(repo, "rev-parse", "HEAD")
        dirty = git(repo, "status", "--porcelain=v1", "--untracked-files=no")
        if cur_branch != branch or cur_head != head or dirty:
            raise SystemExit(f"BASELINE_CONFLICT {repo}: branch={cur_branch} head={cur_head} dirty={dirty!r}")
        print(f"PASS {branch} {head}; tracked tree clean")

    hermes_head = git(HERMES, "rev-parse", "HEAD")
    hermes_dirty = git(HERMES, "status", "--porcelain=v1", "--untracked-files=no")
    if hermes_head != "c2fa302e933aafc5f995696709a4179f54206c26" or hermes_dirty:
        raise SystemExit(f"HERMES_CONFLICT head={hermes_head} dirty={hermes_dirty!r}")
    print(f"PASS hermes-agent {hermes_head}; tracked tree clean")

    for plugin_name in ("quant-v080-readonly", "quant-v080-h2b-readonly"):
        if (REAL_HERMES_HOME / "plugins" / plugin_name).exists():
            raise SystemExit(f"HERMES_PROFILE_CONTAMINATION: {plugin_name} in /root/.hermes/plugins")
    print("PASS /root/.hermes untouched by quant plugins")

    for rel, expected in (
        ("docs/architecture/V080_QUANT_AGENT_CONTRACT_V1_20261120.md", "622677b019120ed18d9bfea057589f7bf923f7f15e17adb3ac59831a0bfd8cc2"),
        ("docs/architecture/V080_QUANT_AGENT_V1_P0_CONTROLLER_DISPOSITIONS_20261120.md", "87fbab75cd2f4ef3581c02fb68aa1e9109fc7118fe1a3827fae1876ff159421b"),
        ("docs/architecture/V080_QUANT_AGENT_V1_P0_CROSS_LANGUAGE_GOLDENS_20261120.json", "5263e68a1f8c56353873d4f8f7c4342fad175bba416139e366733c819026d713"),
    ):
        print(f"PASS {check_sha(DOCS / rel, expected)} {rel}")

    h1_corr_wheel = (
        CODE
        / "workspaces/lt-v080-gemini-neon-hermes-h1-p0-interop-fix-01"
        / "evidence/wheel/quant_hermes_feishu_h1-0.8.0.post1-py3-none-any.whl"
    )
    print(
        "PASS accepted H1 0.8.0.post1 wheel",
        check_sha(h1_corr_wheel, "f8f43e21ea5c9e3155aecea1e0b66313e65c3bf20b3c56e1a8821eb9270e3e2e"),
    )
    h1_ref_manifest = (
        CODE
        / "workspaces/lt-v080-gemini-neon-hermes-h1-p0-interop-fix-01"
        / "reference-export/REFERENCE_EXPORT_MANIFEST.json"
    )
    print(
        "PASS H1 reference-export manifest",
        check_sha(h1_ref_manifest, "892e1a4ff908376f1e4b6351dd5aef922fc9a5448b0ae12396426cb49c581bea"),
    )

    for name, (expected, expected_count) in SEALS.items():
        root = CODE / "workspaces" / name
        manifest = root / "SHA256SUMS"
        check_sha(manifest, expected)
        lines = manifest.read_text().splitlines()
        if len(lines) != expected_count:
            raise SystemExit(f"COUNT_MISMATCH {name}: {len(lines)} != {expected_count}")
        subprocess.run(["sha256sum", "--quiet", "-c", "SHA256SUMS"], cwd=root, check=True)
        print(f"PASS {expected} {name} ({len(lines)} sealed files)")

    for fname, expected in RECEIPTS.items():
        check_sha(CODE / "controller-decisions" / fname, expected)
        print(f"PASS {expected} {fname}")

    manifest = CODE / "baseline/PROGRAM_J_BASELINE_MANIFEST_20261118.json"
    expected_pj = "9796870e41ed19188dcfe003f45b8f0edcb3826e408d3e46966d0626374b635b"
    check_sha(manifest, expected_pj)
    rows = json.loads(manifest.read_text())["files"]
    for row in rows:
        path = CODE / "baseline/program-j" / row["path"]
        check_sha(path, row["sha256"])
        if path.stat().st_size != row["bytes"]:
            raise SystemExit(f"SIZE_MISMATCH {path}")
    print(f"PASS {expected_pj} Program J ({len(rows)} files)")


if __name__ == "__main__":
    main()
