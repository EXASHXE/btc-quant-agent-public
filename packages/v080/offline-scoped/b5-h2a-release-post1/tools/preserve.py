"""Verify immutable baselines, acceptance records and both clean tracked trees."""

import hashlib
import json
import subprocess
from pathlib import Path

workspace = Path(__file__).resolve().parents[1]
code = workspace.parents[1]
docs = code.parent / "quant-docs-engineering"
seals = {
    "lt-v080-personal-mvp-live-public-b5-01":
        "2b4b5e36cc914fda5f748ba71a31f0cae4fdedaecbfbf9980ecbb6bf335edd09",
    "lt-v080-gemini-neon-hermes-quant-feishu-h1-01":
        "577816c61c72591977241b203a4c80b52d0668ea1485bdfb255851b7b50188f2",
    "lt-v080-gemini-neon-hermes-h1-p0-interop-fix-01":
        "90ff56de9175191e771b3de613aedf19267213ee842bec6f87b84817038268d4",
    "lt-v080-astra-pi-quant-agent-architecture-p1-01":
        "0d54ec08f264af77dc9bc80e655236ff03fbc04efd73e678a06f70474ff46acd",
    "lt-v080-personal-mvp-public-source-bridge-b4-01":
        "127fcb635d70096bace47949c69d2bb9c5629460d27b3adf02c457f02c438216",
    "lt-v080-sol62-personal-mvp-public-runtime-foundation-b1-01":
        "73af3d2e273e9d4c6865fe3fe935939c4ae64a7a1475c4bb0ab99ceef319f7a5",
    "lt-v080-sol62-personal-mvp-market-decision-b2-01":
        "8c908905eaa8002e12f53f1d78939b15726658726c20b19abc66c673c6a58368",
    "lt-v080-personal-mvp-account-aware-b3-01":
        "b652ffdc79a0392612c19f02542df3713baf0ab82bd12af5c0eae017c596e54b",
    "lt-v080-sol62-personal-mvp-layer1-public-01":
        "78125e1549de4b8d9e13e1d1c97ec0e5d66cdd9ebcd0c241e069d37ee396d365",
    "lt-v080-astra-full-system-arch-audit-roadmap-01":
        "c946b0ef804c0b19c6dd9b9c1f75a7986493f3ff8d6d1872e1119a0c48b9d85d",
}
receipts = {
    "B5_PHASE_A_OFFLINE_ACCEPTANCE_20261120":
        "1af049c8b5f2be6570d837dd37055a987e3749e9ef0d9c94dfdccfa5ccbd320f",
    "H1_P0_OFFLINE_REFERENCE_SCOPED_ACCEPTANCE_20261120":
        "ed7116fbbb5f3f6ced9434825cd7d318a18c1cf5df2aba3fe752f60dee209e39",
    "P1_PI_ARCHITECTURE_ACCEPTANCE_20261120":
        "c367c8c6188fb6ec51cdc316e4260b2f35486d82781e7eee6c72fcc6e1ba4999",
    "B4_PUBLIC_SOURCE_BRIDGE_OFFLINE_SCOPED_ACCEPTANCE_20261120":
        "095dc79a730b843257947f6d77760a741efb67a6973880c4f9a806ef9ec86b58",
    "B1_PUBLIC_RUNTIME_OFFLINE_SCOPED_ACCEPTANCE_20261118":
        "b42ad44bc91a5fe89e7e2209ba4682ca5232d6611c5340b2b5febfe356a08cbf",
    "B2_MARKET_DECISION_OFFLINE_INTEGRATED_ACCEPTANCE_20261119":
        "7de93eed45541d09a3b65b3e8452033c894ad402a169306bd97e4952929ac48d",
    "B3_ACCOUNT_AWARE_OFFLINE_SCOPED_ACCEPTANCE_20261120":
        "0d3b88ea3bcedeab9f8d18d8118929be4610ecfa433d2bd35cd6fc7f96b8d7a0",
    "R1_LAYER1_PUBLIC_OFFLINE_SCOPED_ACCEPTANCE_20261118":
        "32ddbab7a7244852fb6c5948c057b2063c3d01be420d50eb4046ec8696baeefa",
    "ASTRA_FULL_SYSTEM_ARCH_AUDIT_ACCEPTANCE_20261118":
        "0213dcfc3a12419081404923c9d8112cbb532269f6fc537f2403ced9c4990663",
}


def check(path, expected):
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise SystemExit(f"HASH_MISMATCH {path}")
    return actual


def git(cwd, *args):
    return subprocess.check_output(["git", "--no-optional-locks", *args], cwd=cwd, text=True).strip()


for repo, branch, head in (
    (code, "v0.8.0", "bd144f2d15836bb84786c91aec571df77351bf5c"),
    (docs, "docs/engineering", "cd57a397bd887db703d1354608a8d18a7e03f73d"),
):
    if (git(repo, "branch", "--show-current") != branch or git(repo, "rev-parse", "HEAD") != head
            or git(repo, "status", "--porcelain=v1", "--untracked-files=no")):
        raise SystemExit(f"BASELINE_CONFLICT {repo}")
    print(f"PASS {branch} {head}; tracked tree clean")

for name, expected in seals.items():
    root = code / "workspaces" / name
    manifest = root / "SHA256SUMS"
    check(manifest, expected)
    subprocess.run(["sha256sum", "--quiet", "-c", "SHA256SUMS"], cwd=root, check=True)
    print(f"PASS {expected} {name} ({len(manifest.read_text().splitlines())} sealed files)")

for name, expected in receipts.items():
    check(code / "controller-decisions" / f"V080_CONTROLLER_{name}.json", expected)
    print(f"PASS {expected} {name}")

task = docs / "docs/prompts/v0.8/V080_LIVE_PUBLIC_FIRST_BOUNDED_SCAN_B5_20261120.md"
print("PASS Canonical B5 task", check(task, "209b6a9982d663eabb4aa0aed2368e39de28c6f23a08480655f7ee2ed5b2e5a6"))
manifest = code / "baseline/PROGRAM_J_BASELINE_MANIFEST_20261118.json"
expected = "9796870e41ed19188dcfe003f45b8f0edcb3826e408d3e46966d0626374b635b"
check(manifest, expected)
rows = json.loads(manifest.read_text())["files"]
for row in rows:
    path = code / "baseline/program-j" / row["path"]
    check(path, row["sha256"])
    if path.stat().st_size != row["bytes"]:
        raise SystemExit(f"SIZE_MISMATCH {path}")
print(f"PASS {expected} Program J ({len(rows)} files)")
for path, expected in {
    "governance/V080_PERSONAL_PUBLIC_MARKET_SCOPE_TEMPLATE_20261118.json":
        "3676f630bce8edaf08a15afb45e8cd2b2647b846cd8920b7ec01e5cf65be510d",
    "OWNER_STANDING_M2_AUTHORIZATION_20261024.md":
        "094780240fb440fc550326fbb3797ee60d26cb9e776374fcbc2c0645818830c6",
}.items():
    print(f"PASS {check(code / path, expected)} {path}")
approval = code / "controller-decisions/V080_CONTROLLER_B5_LIVE_PUBLIC_TWO_PHASE_FORWARD_APPROVAL_20261120.json"
print("PASS B5 Phase A scope approval", check(
    approval, "e2bbcb701ae74fb2ba523f7e2b9d1d2e0a45ce10cd2e4cfdcc7c576051afcf6c"))

frozen = docs / "docs/architecture/V080_QUANT_AGENT_CONTRACT_V1_20261120.md"
print("PASS Frozen V1", check(frozen, "622677b019120ed18d9bfea057589f7bf923f7f15e17adb3ac59831a0bfd8cc2"))
