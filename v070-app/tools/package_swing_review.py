"""Exact public-safe L code and cached-dependency packets; no publication action."""

from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re

from package_live import packet

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = ROOT / "audit/code_manifest.json"
    files = {}
    for row in json.loads(manifest.read_text())["files"]:
        raw = (ROOT / row["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row["sha256"], row["path"]
        assert not re.search(
            rb"-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----\r?\n[A-Za-z0-9+/=]{32,}", raw
        )
        files[row["path"]] = raw
    files["audit/code_manifest.json"] = manifest.read_bytes()
    source = packet(ROOT / "release/L_public_source_review.zip", files)
    distributions = set()
    for name in ["dependency_provenance.json", "toolchain_provenance.json"]:
        path = ROOT / "release" / name
        files["release/" + name] = path.read_bytes()
        for row in json.loads(path.read_bytes()):
            raw = (ROOT / row["path"]).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == row["sha256"], row["path"]
            files[row["path"]] = raw
            distributions.add(row["path"])
    for name in ["requirements-lock.txt", "toolchain-lock.txt", "dependency_record_deviations.json"]:
        files["release/" + name] = (ROOT / "release" / name).read_bytes()
    offline = packet(ROOT / "release/L_offline_release.zip", files)
    receipt = {
        "status": "PUBLIC_SAFE_LOCAL_REVIEW_PACKET_READY_NOT_PUBLISHED",
        "source_packet": source,
        "offline_packet": offline,
        "distributions_verified": len(distributions),
        "private_keys_live_grants_or_real_payloads_included": False,
        "merge_deploy_or_publication_performed": False,
        "genuine_market_requests": 0,
    }
    (ROOT / "L5_PUBLIC_RELEASE_PACKET.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
