"""Fake qualification must fail the real native gate. No fake trust is installed."""

import copy
import base64
import json

import pytest

from btc_quant_agent.platform.canary import clock_eligibility as q
from btc_quant_agent.platform.canary import longhorizon as lh
from btc_quant_agent.platform.canary.public_policy import PublicStop
from .fixtures import START, body, scope


def fake_bundle(tmp_path):
    target = lh.GrantBody.model_validate_json(json.dumps(body()))
    spec = q.FAMILIES["SESSION03_CLOCK_V2_V2"]
    fake = {"attestation": {"version": "L4_CLOCK_QUALIFICATION_BUNDLE_V1",
        "family": "SESSION03_CLOCK_V2_V2", "source_session_id": spec[0], "grant_version": spec[1],
        "acquisition_origin": "NATIVE_PUBLIC_CANARY_CAPTURE", "exposure": "PUBLIC_CANARY",
        "clock_contract": "L4_CLOCK_DOMAIN_V2", "scope_hash": "0" * 64,
        "owner_grant_sha256": "0" * 64, "original_receipt_sha256": "0" * 64,
        "receipt_seal_sha256": "0" * 64, "source_config_sha256": "0" * 64,
        "source_sha256_fingerprint": "0" * 64, "target_binding_sha256": q.target_binding(target),
        "capture_end_utc_ms": START - 100, "issued_utc_ms": START - 50, "expires_utc_ms": START + 1000,
        "artifacts": {f"FAKE_{i}.json": "0" * 64 for i in range(8)}},
        "capture_key_id": "FABRICATED_NOT_AUTHORIZED", "signature_algorithm": "Ed25519",
        "signature_base64": "UNSIGNED"}
    return target, fake


@pytest.mark.parametrize("family", list(q.FAMILIES))
def test_known_family_compatibility_never_authorizes_fake_native_preflight(tmp_path, family):
    target, fake = fake_bundle(tmp_path)
    sid, version, limit = q.family_contract(family, *q.FAMILIES[family][:2])
    fake["attestation"].update(family=family, source_session_id=sid, grant_version=version)
    assert limit <= 8 * 3600000
    p = tmp_path / "fake.json"
    p.write_text(json.dumps(fake))
    target = target.model_copy(update={"clock_qualification_receipt_sha256": q.digest(p.read_bytes())})
    with pytest.raises(q.QualificationError, match="CQUAL_INDEPENDENT_CAPTURE_TRUST_MISSING"):
        q.verify_bundle(p, target, START)
    s = scope()
    with pytest.raises(PublicStop, match="FABRICATED_AUTHORITY_CANNOT_ACTIVATE_NATIVE"):
        s.preflight(type("Clock", (), {"wall": lambda self: START})(), native=True)


@pytest.mark.parametrize("field,value,reason", [
    ("family", "UNKNOWN_SESSION", "SESSION_VERSION_NOT_ALLOWED"),
    ("source_session_id", "L4-NATIVE-CLOCK-V2-SESSION02-20261030", "SESSION_VERSION_NOT_ALLOWED"),
    ("grant_version", "L4_FLEX_SESSION03_GRANT_V1", "SESSION_VERSION_NOT_ALLOWED"),
    ("acquisition_origin", "SYNTHETIC", "NATIVE_ACQUISITION_ORIGIN_REQUIRED"),
    ("exposure", "SYNTHETIC", "NATIVE_ACQUISITION_ORIGIN_REQUIRED"),
    ("target_binding_sha256", "1" * 64, "TARGET_SESSION_BINDING_MISMATCH"),
    ("expires_utc_ms", START, "EXPIRED_OR_STALE"),
    ("expires_utc_ms", START + 300001, "EXPIRED_OR_STALE"),
    ("issued_utc_ms", START + 1, "EXPIRED_OR_STALE"),
    ("capture_end_utc_ms", START + 1, "EXPIRED_OR_STALE"),
    ("native_clock_qualified", True, "FORMAT_INVALID"),
    ("clock_contract", "CLOCK_V1", "FORMAT_INVALID"),
])
def test_forged_mutated_replayed_cross_session_or_stale_receipts_rejected(tmp_path, field, value, reason):
    target, fake = fake_bundle(tmp_path)
    fake["attestation"][field] = value
    p = tmp_path / "fake.json"
    p.write_text(json.dumps(fake))
    target = target.model_copy(update={"clock_qualification_receipt_sha256": q.digest(p.read_bytes())})
    with pytest.raises(q.QualificationError, match="CQUAL_" + reason):
        q.verify_bundle(p, target, START)


@pytest.mark.parametrize("mutation", ["receipt", "signer", "signature"])
def test_any_native_looking_fake_remains_untrusted(tmp_path, mutation):
    target, fake = fake_bundle(tmp_path)
    # Public-looking JSON and invented SHA values are never evidence of origin.
    if mutation == "signature":
        fake["signature_base64"] = "A" * 88
    elif mutation == "signer":
        fake["capture_key_id"] = "OLD_SESSION02_SIGNER"
    else:
        fake["attestation"]["artifacts"]["FAKE_0.json"] = "1" * 64
    p = tmp_path / "fake.json"
    p.write_text(json.dumps(fake))
    target = target.model_copy(update={"clock_qualification_receipt_sha256": q.digest(p.read_bytes())})
    with pytest.raises(q.QualificationError, match="INDEPENDENT_CAPTURE_TRUST_MISSING"):
        q.verify_bundle(p, target, START)


def test_old_boolean_receipt_is_rejected_and_not_relabelled(tmp_path):
    target, _ = fake_bundle(tmp_path)
    old = {"session_id": "L4-NATIVE-CLOCK-V2-SESSION02-20261030", "exposure": "PUBLIC_CANARY",
           "native_clock_qualified": True, "clock_fault": None, "independent_probes": 2,
           "distinct_qualified_quotes": 1, "source_sha256_fingerprint": "1" * 64,
           "sealed_receipt_sha256": "2" * 64}
    p = tmp_path / "old.json"
    p.write_text(json.dumps(old))
    before = p.read_bytes()
    target = target.model_copy(update={"clock_qualification_receipt_sha256": q.digest(before)})
    with pytest.raises(q.QualificationError, match="NATIVE_ACQUISITION_ORIGIN_REQUIRED"):
        q.verify_bundle(p, target, START)
    assert p.read_bytes() == before


def test_mutated_file_hash_and_symlink_fail_before_receipt_trust(tmp_path):
    target, fake = fake_bundle(tmp_path)
    p = tmp_path / "fake.json"
    p.write_text(json.dumps(fake))
    with pytest.raises(q.QualificationError, match="ARTIFACT_MISMATCH"):
        q.verify_bundle(p, target, START)
    link = tmp_path / "link.json"
    link.symlink_to(p)
    with pytest.raises(q.QualificationError, match="ARTIFACT_MISMATCH"):
        q.verify_bundle(link, target, START)


def test_duplicate_json_fields_fail_closed():
    with pytest.raises(q.QualificationError, match="FORMAT_INVALID"):
        q.json_value('{"origin":1,"origin":2}')


def test_fabricated_signed_long_grant_cannot_launder_fake_qualification(tmp_path, monkeypatch):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    from canary_public.test_session02 import Clock

    target, fake = fake_bundle(tmp_path)
    target = target.model_copy(update={"egress_route": lh.APPROVED_ROUTE})
    fake["attestation"]["target_binding_sha256"] = q.target_binding(target)
    path = tmp_path / "FABRICATED_REJECTED.json"
    path.write_text(json.dumps(fake))
    target = target.model_copy(update={"clock_qualification_receipt_sha256": q.digest(path.read_bytes())})
    private = Ed25519PrivateKey.generate()
    keys = tmp_path / "TEST_ONLY_LONG_KEYS.json"
    keys.write_text(json.dumps({"version": "L4_LONGHORIZON_OWNER_KEYS_V1", "keys": {"FAKE_TEST": {
        "verified_owner_reference": target.authorization_reference,
        "public_key_base64": base64.b64encode(private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()}}}))
    monkeypatch.setattr(lh, "TRUST", keys)
    envelope = lh.GrantEnvelope(grant=target, key_id="FAKE_TEST", signature_algorithm="Ed25519",
        signature_base64=base64.b64encode(private.sign(lh.signed_bytes(target))).decode())
    s = lh.make_scope(envelope, clock_receipt=path)
    before = q.TRUST.read_bytes()
    result = s.preflight(Clock(START + 10), native=True)
    assert "CQUAL_INDEPENDENT_CAPTURE_TRUST_MISSING" in result["reasons"]
    assert s.native_preflight_digest is None and not lh.OUTPUT.exists()
    assert q.TRUST.read_bytes() == before


@pytest.mark.parametrize("version,limit", [("L4_FLEX_SESSION03_GRANT_V1", 21600000),
                                           ("L4_FLEX_SESSION03_GRANT_V2", 28800000)])
def test_new_session_window_format_compatible_but_fabricated_authority_rejected(tmp_path, version, limit):
    start = START
    c = {"version": version, "session_id": "L4-NATIVE-CLOCK-V2-FLEX-SESSION03",
         "scope_hash": "0" * 64, "authorization_digest": "1" * 64, "source_fingerprint": "2" * 64,
         "launch_start_ms": start, "launch_end_ms": start + limit,
         "acquisition_start_ms": start + limit - 30000, "acquisition_end_ms": start + limit}
    record = {"flex_window_contract": c, "scope_hash": "0" * 64,
              "scope_window_ms": [c["acquisition_start_ms"], c["acquisition_end_ms"]],
              "clock_contract_version": "L4_CLOCK_DOMAIN_V2"}
    q.validate_flex_window(record)
    mutated = copy.deepcopy(record)
    mutated["flex_window_contract"]["launch_end_ms"] += 1
    with pytest.raises(q.QualificationError):
        q.validate_flex_window(mutated)
    with pytest.raises(q.QualificationError, match="BUNDLE_MISSING"):
        q.verify_bundle(None, lh.GrantBody.model_validate_json(json.dumps(body())), START)


@pytest.mark.parametrize("fault", ["missing", "duplicate", "overlap", "uncertain", "mixed_epoch", "wall_jump"])
def test_native_probe_faults_have_typed_rejection_and_cannot_qualify_fake(tmp_path, fault):
    from canary_public.test_session02 import Clock

    c = Clock(START)
    probes = []
    for i in range(2):
        request = c.sample()
        c.advance(250 if fault == "uncertain" else 20)
        received = c.sample()
        c.advance(1)
        available = c.sample()
        probes.append({"request": request, "receive": received, "available": available,
            "server_ms": received["wall_ms"] - 10, "scope_hash": "0" * 64,
            "wire_id": str(i) * 64, "exposure": "PUBLIC_CANARY"})
        c.advance(11)
    if fault == "missing":
        probes.pop()
    elif fault == "duplicate":
        probes[1]["wire_id"] = probes[0]["wire_id"]
    elif fault == "overlap":
        probes[1]["request"] = probes[0]["request"]
    elif fault == "mixed_epoch":
        probes[1]["available"]["epoch_id"] = "OTHER_EPOCH"
    elif fault == "wall_jump":
        probes[1]["available"]["wall_ms"] += 51
    with pytest.raises(q.QualificationError, match="CQUAL_INDEPENDENT_NATIVE_PROBES_INVALID"):
        q.native_probe_estimate(probes, "0" * 64)
    with pytest.raises(PublicStop, match="FABRICATED_AUTHORITY"):
        scope().preflight(c, native=True)
