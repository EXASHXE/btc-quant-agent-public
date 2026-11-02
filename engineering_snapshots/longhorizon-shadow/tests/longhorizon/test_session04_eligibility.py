"""OFFLINE_SYNTHETIC compatibility/negative fixtures; no trust provisioning."""

import copy
import json

import pytest

from btc_quant_agent.platform.canary import clock_eligibility as q
from btc_quant_agent.platform.canary.session04_acceptance import evaluate
from .fixtures import START
from .test_clock_eligibility import fake_bundle


def candidate(tmp_path, **updates):
    target, bundle = fake_bundle(tmp_path)
    bundle["attestation"].update(version="L4_CLOCK_QUALIFICATION_BUNDLE_V2",
        family="SESSION04_RUNTIME_V1", source_session_id="L4-NATIVE-RUNTIME-V1-SESSION04",
        grant_version="L4_RUNTIME_SESSION04_GRANT_V1", predeclared_acceptance_sha256="4" * 64)
    bundle["attestation"].update(updates)
    p = tmp_path / "OFFLINE_SYNTHETIC_NOT_CAPTURE_AUTHORITY.json"
    p.write_text(json.dumps(bundle))
    target = target.model_copy(update={"clock_qualification_receipt_sha256": q.digest(p.read_bytes())})
    return p, target


def test_session04_requires_new_bundle_and_independent_empty_trust(tmp_path):
    assert json.loads(q.TRUST_V2.read_text()) == {"version": "L4_CLOCK_QUALIFICATION_TRUST_V2", "owner_keys": {}, "capture_keys": {}}
    p, target = candidate(tmp_path)
    with pytest.raises(q.QualificationError, match="INDEPENDENT_CAPTURE_TRUST_MISSING"):
        q.verify_bundle(p, target, START)
    with pytest.raises(q.QualificationError, match="SESSION_VERSION_NOT_ALLOWED"):
        q.family_contract("SESSION04_RUNTIME_V1", *q.FAMILIES_V2["SESSION04_RUNTIME_V1"][:2])
    assert q.family_contract("SESSION04_RUNTIME_V1", *q.FAMILIES_V2["SESSION04_RUNTIME_V1"][:2],
                            bundle_version="L4_CLOCK_QUALIFICATION_BUNDLE_V2")[2] == 28800000


@pytest.mark.parametrize("field,value,reason", [
    ("source_session_id", "L4-NATIVE-CLOCK-V2-FLEX-SESSION03", "SESSION_VERSION_NOT_ALLOWED"),
    ("grant_version", "L4_FLEX_SESSION03_GRANT_V2", "SESSION_VERSION_NOT_ALLOWED"),
    ("version", "L4_CLOCK_QUALIFICATION_BUNDLE_V1", "FORMAT_INVALID"),
    ("acquisition_origin", "SYNTHETIC", "NATIVE_ACQUISITION_ORIGIN_REQUIRED"),
    ("exposure", "SYNTHETIC", "NATIVE_ACQUISITION_ORIGIN_REQUIRED"),
    ("expires_utc_ms", START, "EXPIRED_OR_STALE"),
    ("issued_utc_ms", START + 1, "EXPIRED_OR_STALE"),
    ("target_binding_sha256", "1" * 64, "TARGET_SESSION_BINDING_MISMATCH"),
    ("predeclared_acceptance_sha256", "NOT_A_DIGEST", "FORMAT_INVALID"),
])
def test_cross_version_origin_hash_target_and_stale_candidate_fail_closed(tmp_path, field, value, reason):
    p, target = candidate(tmp_path, **{field: value})
    with pytest.raises(q.QualificationError, match="CQUAL_" + reason):
        q.verify_bundle(p, target, START)


def test_explicit_session04_replay_binding_never_confers_native_authority():
    c = {"version": "L4_RUNTIME_SESSION04_GRANT_V1", "session_id": "L4-NATIVE-RUNTIME-V1-SESSION04",
         "launch_start_ms": START, "launch_end_ms": START + 30000,
         "acquisition_start_ms": START, "acquisition_end_ms": START + 30000,
         "scope_hash": "1" * 64, "authorization_digest": "2" * 64, "source_fingerprint": "3" * 64}
    record = {"flex_window_contract": c, "scope_hash": c["scope_hash"], "scope_window_ms": [START, START + 30000],
              "clock_contract_version": "L4_CLOCK_DOMAIN_V2"}
    q.validate_flex_window(record)
    for field, bad in (("session_id", "Session03"), ("acquisition_end_ms", START + 180001),
                       ("authorization_digest", "x")):
        mutated = copy.deepcopy(record)
        mutated["flex_window_contract"][field] = bad
        with pytest.raises(q.QualificationError):
            q.validate_flex_window(mutated)
    assert evaluate({"session_id": c["session_id"], "source_qualified": True})["passed"] is False


@pytest.mark.parametrize("failure", ["BACKPRESSURE_PENDING_EXCEEDED", "RATE_LIMIT_CIRCUIT_OPEN", "CLOCK_EPOCH_INVALID", "CRASH", "PARTIAL"])
def test_failed_source_or_connected_ws_never_qualifies_long(failure):
    report = {"session_id": "L4-NATIVE-RUNTIME-V1-SESSION04", "exposure": "PUBLIC_CANARY",
              "stop_reason": failure, "status": "SOURCE_QUALIFIED", "source_qualified": True,
              "transport_metrics": {"ws_connections": 1}}
    result = evaluate(report)
    assert result["passed"] is False and "UNCLEAN_STOP" in result["reasons"]
    assert result["source_qualified"] is False and result["long_acquisition_authorized"] is False
