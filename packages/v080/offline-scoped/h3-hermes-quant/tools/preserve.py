"""Verify Controller inputs, accepted seals, and the installed Hermes baseline."""

import hashlib
import json
import stat
import subprocess
import sys
from pathlib import Path

workspace = Path(__file__).resolve().parents[1]
workspaces = workspace.parent
code = workspaces.parent
docs = code.parent / "quant-docs-engineering"
hermes = Path("/usr/local/lib/hermes-agent")
h2a = workspaces / "lt-v080-sol62-h2a-b5-phaseb-activation-01"
h2b = workspaces / "lt-v080-neon-h2b-hermes-feishu-readiness-01"
h1 = workspaces / "lt-v080-gemini-neon-hermes-h1-p0-interop-fix-01"


def sha(path):
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()


def checked(path, expected):
    if path.is_symlink() or not path.is_file() or sha(path) != expected:
        raise SystemExit(f"HASH_MISMATCH {path}")


def git(cwd, *args):
    return subprocess.check_output(
        ["git", "--no-optional-locks", *args], cwd=cwd, text=True
    ).strip()


def ensure_permissions(root):
    for path in (root, *root.rglob("*")):
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or mode & 0o022:
            raise SystemExit(f"PERMISSION_MISMATCH {path}")


def verify():
    for repo, branch, head in (
        (code, "v0.8.0", "bd144f2d15836bb84786c91aec571df77351bf5c"),
        (docs, "docs/engineering", "cd57a397bd887db703d1354608a8d18a7e03f73d"),
        (hermes, None, "c2fa302e933aafc5f995696709a4179f54206c26"),
    ):
        if (
            git(repo, "rev-parse", "HEAD") != head
            or (branch and git(repo, "branch", "--show-current") != branch)
            or git(repo, "status", "--porcelain", "--untracked-files=no")
        ):
            raise SystemExit(f"BASELINE_MISMATCH {repo}")
        print(f"PASS repository {repo.name} {head}")
    receipts = {
        "H3_HERMES_QUANT_OFFLINE_INTEGRATION_DISPATCH_20261121": "11d71e288ef89d263e33e134b8ac3079cca1ea7e5c249877fac50092e55d63fc",
        "H2A_B5_PHASEB_OFFLINE_SCOPED_ACCEPTANCE_20261120": "bf4c582f1b6b1d4083c87c26e2d99a2248390340f2aa14aa19266930ccc5e2a5",
        "H2B_HERMES_FEISHU_OFFLINE_SCOPED_ACCEPTANCE_20261121": "377a8ba393c168da7b5c8b8b688bae7c8559a9a57be9dae746d326b6a0c5d2b8",
    }
    for name, expected in receipts.items():
        path = code / "controller-decisions" / f"V080_CONTROLLER_{name}.json"
        checked(path, expected)
        ensure_permissions(path)
        print(f"PASS receipt {expected} {name}")
    for root, sha256, count in (
        (h2a, "b6be8e070fbd55d2a15c5443ab49eabe1bda62dc5f6396ab1d6a4996d8085a16", 69),
        (h2b, "a5ee93c45f734511315a66343e0b9fab26608d6de4553b0045586c215d82c542", 58),
        (h1, "90ff56de9175191e771b3de613aedf19267213ee842bec6f87b84817038268d4", 71),
    ):
        ensure_permissions(root)
        manifest = root / "SHA256SUMS"
        checked(manifest, sha256)
        rows = manifest.read_text().splitlines()
        names = [row[66:] for row in rows]
        actual = {
            str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and p != manifest
        }
        if len(names) != count or len(set(names)) != count or set(names) != actual:
            raise SystemExit(f"INVALID_MANIFEST_INVENTORY {root}")
        subprocess.run(
            ["sha256sum", "--check", "--quiet", "--strict", "SHA256SUMS"], cwd=root, check=True
        )
        print(f"PASS {root.name} {count}/{count} {sha256}")
    upstream = h2a / "tools/preserve.py"
    subprocess.run([sys.executable, "-B", str(upstream)], check=True)
    pin = json.loads((h2b / "PINNED_DEPENDENCIES.json").read_text())
    for name, expected in pin["pinned_documents"].items():
        parent = (
            code / "controller-decisions"
            if name.startswith("V080_CONTROLLER_")
            else docs / "docs/architecture"
        )
        checked(parent / name, expected)
        print(f"PASS pinned norm {expected} {name}")
    checked(
        h1 / "reference-export/REFERENCE_EXPORT_MANIFEST.json",
        "892e1a4ff908376f1e4b6351dd5aef922fc9a5448b0ae12396426cb49c581bea",
    )
    print("PASS H1 reference export manifest")
    for row in wheels():
        checked((workspace / row["file"]).resolve(), row["sha256"])
        print(f"PASS wheel {row['sha256']} {Path(row['file']).name}")


def wheels():
    return json.loads((workspace / "PINNED_DEPENDENCIES.json").read_text())["wheels"]


if __name__ == "__main__":
    if sys.argv[1:] in (["--requirements"], ["--requirements", "--mixed"]):
        for row in wheels():
            if row["usage"] == "baseline-only":
                continue
            if row["usage"] == "mixed" and "--mixed" not in sys.argv:
                continue
            path = (workspace / row["file"]).resolve()
            checked(path, row["sha256"])
            print(f"{path.as_uri()} --hash=sha256:{row['sha256']}")
    else:
        verify()
