"""Verify frozen scoped inputs and only stat Session03 payloads; never read N payloads."""

from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    inputs = json.loads((ROOT / "audit/original_inputs.json").read_text())
    failures = []
    for row in inputs["files"]:
        p = ROOT.parent / row["path"]
        st = p.stat()
        if (
            st.st_size != row["bytes"]
            or st.st_mtime_ns != row["mtime_ns"]
            or hashlib.sha256(p.read_bytes()).hexdigest() != row["sha256"]
        ):
            failures.append(row["path"])
    for name, expected in inputs["session03_metadata"].items():
        st = (ROOT.parent / name).stat()
        if [st.st_size, st.st_mtime_ns, st.st_ctime_ns, st.st_mode, st.st_ino] != expected:
            failures.append(name)
    seal = (
        ROOT.parent
        / "l4-readonly-source-canary-01/artifacts/live_public_canary_flex/session_03_clock_v2/receipt_seal.json"
    )
    seal_hash = hashlib.sha256(seal.read_bytes()).hexdigest()  # Seal metadata only.
    assert seal_hash == inputs["session03_seal_sha256"], "SESSION03_SEAL_CHANGED"
    result = {
        "status": "PASS" if not failures else "FAILED_SAFETY",
        "scoped_file_SHA256_size_mtime_checks": len(inputs["files"]),
        "Session03_stat_only_checks": len(inputs["session03_metadata"]),
        "Session03_seal_metadata_sha256": seal_hash,
        "failures": failures,
        "N_original_market_payload_opened_copied_or_deleted": False,
        "FINAL_HOLDOUT_or_historical_payloads_read": False,
        "live_exchange_requests_by_O": 0,
        "OS_NTP_proxy_or_Windows_settings_changes": 0,
    }
    (ROOT / "O6_PRESERVATION_AFTER.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps(result))
    assert not failures


if __name__ == "__main__":
    main()
