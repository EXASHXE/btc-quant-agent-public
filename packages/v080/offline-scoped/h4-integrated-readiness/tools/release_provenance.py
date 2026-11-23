"""Emit an offline review SBOM from preserved manifests and local candidate wheels."""

import json
import subprocess
import sys
from email import message_from_bytes
from importlib import metadata
from zipfile import ZipFile

from preserve import H3, ROOT, RUNTIME, dependencies, sha


def entry(path, checksum):
    return {"filename": path.name, "sha256": checksum}


candidate = []
for path in sorted((ROOT / "evidence/wheel").glob("*.whl")):
    with ZipFile(path) as archive:
        (name,) = (name for name in archive.namelist() if name.endswith(".dist-info/METADATA"))
        meta = message_from_bytes(archive.read(name))
        candidate.append(
            {
                **entry(path, sha(path)),
                "name": meta["Name"],
                "version": meta["Version"],
                "requires_dist": meta.get_all("Requires-Dist", []),
            }
        )
report = {
    "schema": "H4_RELEASE_SBOM_V1",
    "candidates": candidate,
    "profiles": {
        profile: [entry(path, checksum) for path, checksum in dependencies(profile)]
        for profile in ("hermes-clean", "hermes-mixed", "canary-clean", "canary-mixed")
    },
    "upstream_manifest": {
        "path": "tools/upstream-pins.sha256",
        "sha256": sha(ROOT / "tools/upstream-pins.sha256"),
    },
    "source_delta": {
        "path": "evidence/source-delta.patch",
        "sha256": sha(ROOT / "evidence/source-delta.patch"),
    },
    "runtime": {
        "commit": "c2fa302e933aafc5f995696709a4179f54206c26",
        "root": str(RUNTIME),
        "dependency_inventory": "HERMES_RUNTIME_LOCK.json",
        "dependency_inventory_sha256": sha(H3 / "HERMES_RUNTIME_LOCK.json"),
    },
    "build": {
        "epoch": 1795219200,
        "python": sys.version.split()[0],
        "toolchains": {name: metadata.version(name) for name in ("pip", "setuptools", "wheel")},
        "node": subprocess.check_output(["node", "--version"], text=True).strip(),
    },
}
print(json.dumps(report, indent=2) + "\n", end="")
