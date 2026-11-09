"""Public-safe exact allowlist packet; never publishes or includes N market payloads."""

from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
from package_live import packet

ROOT = Path(__file__).resolve().parents[1]


def main():
    base = json.loads((ROOT / "contracts/O_FROZEN_L_CODE.json").read_text())["files"]
    names = {r["path"] for r in base}
    names.update(
        [
            "src/btc_quant_agent/platform/live/operational_clock.py",
            "src/btc_quant_agent/platform/live/operational_clock.json",
            "tests/live/test_operational_clock.py",
            "tests/live/test_o_retention.py",
            "tests/live/test_o_host_counterexample.py",
            "contracts/O_FROZEN_L_CODE.json",
            "contracts/O_HOST_CLOCK_COUNTEREXAMPLE.json",
            "README_O_OPERATOR.md",
            "O5_HOST_REMEDIATION_AND_FUTURE_PREFLIGHT.md",
            "O5_N_RETENTION_PURGE_CHECKLIST.md",
        ]
    )
    names.update(
        "tools/" + n + ".py"
        for n in [
            "build_o",
            "run_o_tests",
            "demonstrate_o",
            "o_retention",
            "clock_o_telemetry",
            "preserve_o",
            "report_o",
            "package_o",
        ]
    )
    rows = []
    files = {}
    for name in sorted(names):
        p = ROOT / name
        assert p.is_file() and not p.is_symlink(), name
        raw = p.read_bytes()
        assert not re.search(
            rb"-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----\r?\n[A-Za-z0-9+/=]{32,}", raw
        ), name
        rows.append({"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
        files[name] = raw
    manifest = ROOT / "audit/code_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "O_EXACT_CODE_ALLOWLIST_V1",
                "files": rows,
                "excluded": "N market payloads/keys/grants/host audit/Session03/protected research/FINAL_HOLDOUT",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    files["audit/code_manifest.json"] = manifest.read_bytes()
    source = packet(ROOT / "release/O_public_source_review.zip", files)
    distributions = set()
    for name in ["dependency_provenance.json", "toolchain_provenance.json"]:
        p = ROOT / "release" / name
        files["release/" + name] = p.read_bytes()
        for row in json.loads(p.read_bytes()):
            p = ROOT / row["path"]
            raw = p.read_bytes()
            assert hashlib.sha256(raw).hexdigest() == row["sha256"]
            files[row["path"]] = raw
            distributions.add(row["path"])
    for name in ["requirements-lock.txt", "toolchain-lock.txt", "dependency_record_deviations.json"]:
        files["release/" + name] = (ROOT / "release" / name).read_bytes()
    offline = packet(ROOT / "release/O_offline_release.zip", files)
    receipt = {
        "status": "LOCAL_REVIEW_PACKET_ONLY_CONTROLLER_ACCEPTANCE_PENDING",
        "source_packet": source,
        "offline_packet": offline,
        "verified_distributions": len(distributions),
        "code_files": len(rows),
        "repeat_byte_identical": True,
        "market_data_or_authentic_keys_or_grants_included": False,
        "publication_merge_deployment": False,
    }
    (ROOT / "O_RELEASE_REVIEW_PACKET.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
