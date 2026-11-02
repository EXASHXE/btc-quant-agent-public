"""Offline compatibility and forged-authority rejection; never opens transport."""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

from btc_quant_agent.platform.canary import clock_eligibility as q
from btc_quant_agent.platform.canary import longhorizon as lh
from btc_quant_agent.platform.canary.public_policy import PublicStop
from btc_quant_agent.platform.core import fingerprint


def demonstrate(output, session03_offline_receipt=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    # Fixed invented clocks, not a replacement or rolling Owner window.
    now = 1793462400000
    template = json.loads((lh.ROOT / "LONGHORIZON_SOURCE_GRANT_PROPOSAL.json").read_text())["unsigned_contract_template"]
    template.update(authorization_reference="OWNER-V070-L4-LONGHORIZON-FABRICATED_DEMO",
                    issued_utc_ms=now - 1000, start_utc_ms=now, end_utc_ms=now + 48 * 3600000,
                    source_sha256_fingerprint=fingerprint(lh.source_hashes()),
                    clock_qualification_receipt_sha256="0" * 64)
    target = lh.GrantBody.model_validate_json(json.dumps(template))
    family = "SESSION03_CLOCK_V2_V2"
    spec = q.FAMILIES[family]
    q.family_contract(family, *spec[:2])
    attestation = {"version": "L4_CLOCK_QUALIFICATION_BUNDLE_V1", "family": family,
        "source_session_id": spec[0], "grant_version": spec[1],
        "acquisition_origin": "NATIVE_PUBLIC_CANARY_CAPTURE", "exposure": "PUBLIC_CANARY",
        "clock_contract": "L4_CLOCK_DOMAIN_V2", "scope_hash": "0" * 64,
        "owner_grant_sha256": "0" * 64, "original_receipt_sha256": "0" * 64,
        "receipt_seal_sha256": "0" * 64, "source_config_sha256": "0" * 64,
        "source_sha256_fingerprint": "0" * 64, "target_binding_sha256": q.target_binding(target),
        "capture_end_utc_ms": now - 100, "issued_utc_ms": now - 50, "expires_utc_ms": now + 1000,
        "artifacts": {f"ABSENT_FAKE_{i}.json": "0" * 64 for i in range(8)}}
    fake = {"attestation": attestation, "capture_key_id": "FABRICATED_NOT_TRUSTED",
            "signature_algorithm": "Ed25519", "signature_base64": "UNSIGNED"}
    path = output / "FABRICATED_REJECTED_BUNDLE.json"
    path.write_text(json.dumps(fake, indent=2, sort_keys=True) + "\n")
    target = target.model_copy(update={"clock_qualification_receipt_sha256": q.digest(path.read_bytes())})
    try:
        q.verify_bundle(path, target, now)
    except q.QualificationError as exc:
        rejection = exc.reason.value
    else:
        raise AssertionError("FORGED_QUALIFICATION_WAS_ACCEPTED")
    envelope = lh.GrantEnvelope(grant=target, key_id="FABRICATED_NOT_AUTHORITY",
                               signature_algorithm="Ed25519", signature_base64="UNSIGNED")
    scope = lh.make_scope(envelope, fabricated=True, clock_receipt=path)

    class Clock:
        def wall(self):
            return now

    try:
        scope.preflight(Clock(), native=True)
    except PublicStop as exc:
        native_rejection = str(exc)
    else:
        raise AssertionError("FABRICATED_NATIVE_PREFLIGHT_WAS_ACCEPTED")
    result = {"version": "L4_CLOCK_ELIGIBILITY_OFFLINE_DEMONSTRATION_V1",
        "session_version_compatibility": {k: list(v) for k, v in q.FAMILIES.items()},
        "new_session03_v2_structure_compatible": True,
        "fabricated_bundle_rejection": rejection, "native_preflight_rejection": native_rejection,
        "authenticated_native_qualification_demonstrated": False, "native_transport_constructed": False,
        "native_market_calls": 0, "keys_installed": False, "grant_signed": False,
        "source_qualified": False, "shadow_advisory_qualified": False, "economically_validated": False}
    if session03_offline_receipt:
        from btc_quant_agent.platform.canary.public_data import normalize

        root = Path(session03_offline_receipt)
        report = json.loads((root / "report.json").read_text())
        assert report["exposure"] == "SYNTHETIC" and report["native_market_requests"] == 0
        assert report["flex_window_contract"]["version"] == spec[1]
        chunks = {}
        checked = 0
        for row in report["replay"]["manifest"]:
            p = root / row["kind"] / (row["sha256"] + ".json.gz")
            assert q.digest(p.read_bytes()) == row["sha256"]
            chunk = json.loads(gzip.decompress(p.read_bytes()))
            assert chunk["exposure"] == "SYNTHETIC"
            chunks[row["sha256"]] = chunk
            if row["kind"] == "normalized":
                expected = [normalize(r) for r in chunks[row["raw_sha"]]["records"]]
                assert expected == chunk["records"]
                checked += 1
        assert checked > 0
        result["new_synthetic_session03_receipt_replayed_in_longhorizon_pairs"] = checked
        result["synthetic_evidence_relabelled"] = False
        synthetic = target.model_copy(update={"clock_qualification_receipt_sha256": q.digest((root / "report.json").read_bytes())})
        try:
            q.verify_bundle(root / "report.json", synthetic, now)
        except q.QualificationError as exc:
            result["synthetic_receipt_native_qualification_rejection"] = exc.reason.value
        else:
            raise AssertionError("SYNTHETIC_RECEIPT_WAS_ACCEPTED_AS_NATIVE")
    (output / "demonstration.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--session03-offline-receipt")
    args = parser.parse_args()
    print(json.dumps(demonstrate(args.output, args.session03_offline_receipt), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
