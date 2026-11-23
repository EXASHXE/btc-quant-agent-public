from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from helpers import QAClock, LocalVenue, authority, key, sign
from test_runtime import message
from btc_quant_agent.platform.native.contract import (
    Envelope,
    AuditBody,
    AuditEnvelope,
    authorize,
    digest,
    source_hash,
)
from btc_quant_agent.platform.native.journal import Journal
from btc_quant_agent.platform.native.runtime import capture
from btc_quant_agent.platform.native.transport import Transport
from btc_quant_agent.platform.native.audit import challenge
from btc_quant_agent.platform.qualification.admission import HostBody, HostEnvelope, verify_host
from btc_quant_agent.platform.qualification.evidence import Plan, PlanEnvelope, Ledger, SCHEMA_HASH
from btc_quant_agent.platform.qualification.source import Qualification, clock_proof
from btc_quant_agent.platform.rc_fixture import TRIGGER, DECISION, fixture

from btc_quant_agent.platform.qualification.evidence import (
    TimedAuditBody as CaptureAuditBody,
    TimedAuditEnvelope as CaptureAuditEnvelope,
)


@pytest.fixture
def context(tmp_path, request):
    clock = QAClock(TRIGGER + 110)
    venue = LocalVenue(tmp_path / "tls", clock, [message()])
    owner, ok = key("SYNTHETIC_OWNER")
    auditor, ak = key("SYNTHETIC_AUDITOR")
    roots = {"owner": ok, "auditor": ak, "rights_sha256": "b" * 64}
    p = venue.policy
    g, *_ = authority(p, tmp_path / "capture", clock.wall, **getattr(request, "param", {}))
    env = sign(g, "SYNTHETIC_OWNER", owner, Envelope)
    adm = sign(
        AuditBody(
            grant_sha256=digest(g.model_dump(mode="json")),
            rights_sha256="b" * 64,
            independent_reference="SYNTHETIC_ONLY",
        ),
        "SYNTHETIC_AUDITOR",
        auditor,
        AuditEnvelope,
    )
    authorize(
        env,
        adm,
        roots,
        p,
        source_hash=source_hash(),
        executable_hash="a" * 64,
        now_ms=clock.wall,
        exposure="SYNTHETIC_NETWORK",
    )
    j = Journal(tmp_path / "native.sqlite")
    try:
        capture(g, p, j, clock, Transport(p, g, j, clock, qa_ca=venue.cert, qa_proxy=True))
    finally:
        venue.close()
    ledger = Ledger(tmp_path / "qual.sqlite")
    start = TRIGGER - 60 * 86400000
    plan = Plan(
        evidence_class="SYNTHETIC_NETWORK_QA",
        source_sha256=g.source_sha256,
        executable_sha256=g.executable_sha256,
        config_sha256=g.config_sha256,
        rights_sha256="b" * 64,
        created_ms=start - 1000,
        start_ms=start,
        availability_start_ms=TRIGGER - 7 * 86400000,
        end_ms=TRIGGER,
        required_symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        auditor_key_id=g.auditor_key_id,
    )

    def register(target, chosen=plan):
        target.register(
            sign(chosen, "SYNTHETIC_OWNER", owner, PlanEnvelope),
            sign(chosen, "SYNTHETIC_AUDITOR", auditor, PlanEnvelope),
            roots,
            qa=True,
            observed_ms=start - 500,
        )

    register(ledger)
    samples = [p[k] for p in clock.estimate["probes"] for k in ("request", "receive")]
    h = HostBody(
        evidence_class="SYNTHETIC_NETWORK_QA",
        boot_id="QA_BOOT",
        valid_start_ms=g.start_ms,
        valid_end_ms=g.end_ms,
        source_sha256=g.source_sha256,
        config_sha256=g.config_sha256,
        executable_sha256=g.executable_sha256,
        raw_diagnostics={
            "samples": [
                {
                    "wall_ns": s["wall_ms"] * 1000000,
                    "mono_before_ns": s["mono_before_ms"] * 1000000,
                    "mono_after_ns": s["mono_after_ms"] * 1000000,
                }
                for s in samples
            ]
        },
        native_clock_probes=[
            {
                "source": p.clock_endpoint,
                "original_target_tls_verified": True,
                "request_mono_ms": x["request"]["mono_before_ms"],
                "receive_mono_ms": x["receive"]["mono_after_ms"],
                "receive_wall_ms": x["receive"]["wall_ms"],
                "server_ms": x["server_ms"],
            }
            for x in clock.estimate["probes"]
        ],
        independent_reference="FABRICATED_LOCAL_ONLY",
    )
    host = sign(h, "SYNTHETIC_AUDITOR", auditor, HostEnvelope)
    ledger.attach_host(j, g.session_id, host, roots, qa=True)
    cap = sign(
        CaptureAuditBody(
            **challenge(j, g.session_id),
            independently_verified_reference="SYNTHETIC_ONLY",
            audited_ms=clock.wall,
            host_admission_sha256=digest(host.model_dump(mode="json")),
        ),
        "SYNTHETIC_AUDITOR",
        auditor,
        CaptureAuditEnvelope,
    )
    ledger.attach_audit(j, cap, roots, qa=True)

    q = Qualification(
        j, ledger, qa_roots=roots, qa_schema_roots={"accepted_product_schema_sha256": SCHEMA_HASH}
    )
    return SimpleNamespace(
        q=q,
        j=j,
        ledger=ledger,
        roots=roots,
        g=g,
        plan=plan,
        cap=cap,
        host=host,
        register=register,
        owner=owner,
        auditor=auditor,
        path=tmp_path,
    )


def test_actual_local_transport_qualified_but_missing_warmup_blocked(context):
    r = context.q.assess(DECISION)
    assert r["status"] == "SOURCE_BLOCKED" and len(r["stages"]) == 4
    assert "INSUFFICIENT_COMPLETED_HISTORY" in r["reason"]
    assert r["source_qualified"] is False


@pytest.mark.parametrize("missing", ["CAPTURE_AUDIT", "HOST_ADMISSION", "PLAN"])
def test_missing_independent_stage_evidence(context, missing):
    replacement = Ledger(context.path / ("missing_" + missing + ".sqlite"))
    for kind in ("PLAN", "CAPTURE_AUDIT", "HOST_ADMISSION"):
        if kind != missing:
            for row in context.ledger.values(kind):
                replacement.append(kind, row)
    q = Qualification(
        context.j,
        replacement,
        qa_roots=context.roots,
        qa_schema_roots={"accepted_product_schema_sha256": SCHEMA_HASH},
    )
    result = q.assess(DECISION)
    assert result["status"] == "SOURCE_BLOCKED" and "MISSING" in result["reason"]


@pytest.mark.parametrize("role", ["owner", "auditor"])
def test_untrusted_authority_cannot_advance(context, role):
    context.q.roots = {**context.roots, role: {}}
    result = context.q.assess(DECISION)
    assert result["status"] == "SOURCE_BLOCKED" and "TRUST" in result["reason"]


def test_signed_wrong_source_fingerprint_rejected(context):
    replacement = Ledger(context.path / "wrong_source.sqlite")
    context.register(replacement, context.plan.model_copy(update={"source_sha256": "c" * 64}))
    for kind in ("CAPTURE_AUDIT", "HOST_ADMISSION"):
        for r in context.ledger.values(kind):
            replacement.append(kind, r)
    q = Qualification(
        context.j,
        replacement,
        qa_roots=context.roots,
        qa_schema_roots={"accepted_product_schema_sha256": SCHEMA_HASH},
    )
    assert "BUILD_BINDING" in q.assess(DECISION)["reason"] or "FINAL_SOURCE" in q.assess(DECISION)["reason"]


@pytest.mark.parametrize(
    "fault", ["step", "stale", "uncertainty", "native_probe", "source", "config", "signature"]
)
def test_host_signature_and_clock_negative_cases(context, fault):
    h = context.host.grant
    changes = {}
    if fault == "step":
        raw = copy.deepcopy(h.raw_diagnostics)
        raw["samples"][-1]["wall_ns"] += 1695000000
        changes["raw_diagnostics"] = raw
    if fault == "stale":
        changes["valid_end_ms"] = TRIGGER
    if fault == "uncertainty":
        probes = copy.deepcopy(h.native_clock_probes)
        probes[0]["receive_mono_ms"] += 1000
        changes["native_clock_probes"] = probes
    if fault == "native_probe":
        changes["native_clock_probes"] = []
    if fault == "source":
        changes["source_sha256"] = "f" * 64
    if fault == "config":
        changes["config_sha256"] = "f" * 64
    env = sign(h.model_copy(update=changes), "SYNTHETIC_AUDITOR", context.auditor, HostEnvelope)
    if fault == "signature":
        env = env.model_copy(update={"signature_base64": "eA=="})
    with pytest.raises(ValueError):
        verify_host(env, context.roots, context.g, DECISION, qa=True)


def test_clock_regression_after_valid_network_capture_rejected(context):
    value = copy.deepcopy(context.j.records(context.g.session_id)[0])
    value["clock_proof"]["probes"][1]["server_ms"] = value["clock_proof"]["probes"][0]["server_ms"] - 1
    import json

    probe = value["clock_proof"]["probes"][1]
    probe["wire_record"]["body"] = json.dumps({"serverTime": probe["server_ms"]})
    probe["wire_sha256"] = digest(probe["wire_record"])
    with pytest.raises(ValueError, match="REGRESSION"):
        clock_proof(value, context.g.model_dump(mode="json"))


def test_qa_records_never_become_genuine_source(context):
    q = Qualification(context.j, context.ledger)
    result = q.assess(DECISION)
    assert result["status"] == "SOURCE_BLOCKED" and result["source_qualified"] is False


def test_native_account_and_positive_schema_gate():
    import json
    from btc_quant_agent.platform.rc_strategy import decide_s1
    from btc_quant_agent.platform.qualification.product import Decision, PRODUCT
    from btc_quant_agent.platform.core import fingerprint

    rows = fixture()
    d = decide_s1(symbol="BTCUSDT", trigger_ms=TRIGGER, decision_ms=DECISION, receipts=rows)
    fields = {
        k: v
        for k, v in d.model_dump(mode="json").items()
        if k
        not in {"schema_version", "product_version", "contract_sha256", "source_type", "confidence", "gaps"}
    }
    fields.update(
        schema_version="F_NATIVE_PRODUCT_V1",
        product_version=PRODUCT,
        exposure="GENUINE_NATIVE",
        source_qualified=False,
        qualification_sha256="a" * 64,
        episode_id=fingerprint([PRODUCT, d.strategy_version, d.symbol, d.trigger_close_ms, d.prefix_sha256]),
    )
    with pytest.raises(ValueError, match="UNQUALIFIED_NATIVE_POSITIVE"):
        Decision.model_validate_json(json.dumps(fields))
    fields.update(exposure="SYNTHETIC_NETWORK_QA", account="ACCOUNT_APPROVED")
    with pytest.raises(ValueError):
        Decision.model_validate_json(json.dumps(fields))


def test_live_review_requires_same_certified_epoch(context):
    from btc_quant_agent.platform.qualification.admission import verify_review_epoch

    b = context.host.grant
    anchor = b.raw_diagnostics["samples"][-1]
    sample = {
        "wall_ms": anchor["wall_ns"] // 1000000,
        "mono_before_ms": anchor["mono_before_ns"] // 1000000,
        "mono_after_ms": anchor["mono_after_ns"] // 1000000,
    }
    verify_review_epoch(context.host, sample, sample["wall_ms"])
    sample["wall_ms"] += 1695
    with pytest.raises(ValueError, match="EPOCH_CHANGED"):
        verify_review_epoch(context.host, sample, sample["wall_ms"])


def test_refresh_cadence_is_stricter_than_probe_hard_ttl(context):
    value = copy.deepcopy(context.j.records(context.g.session_id)[0])
    value["receive_sample"]["wall_ms"] += 120001
    value["receive_sample"]["mono_before_ms"] += 120001
    value["receive_sample"]["mono_after_ms"] += 120001
    value["record"]["received_ms"] += 120001
    with pytest.raises(ValueError, match="REFRESH_CONTRACT"):
        clock_proof(value, context.g.model_dump(mode="json"))


def test_native_clock_raw_wire_is_retained_and_verified(context):
    value = copy.deepcopy(context.j.records(context.g.session_id)[0])
    assert value["clock_proof"]["probes"][0]["wire_record"]["body"]
    value["clock_proof"]["probes"][0]["wire_record"]["body"] = '{"serverTime":1}'
    with pytest.raises(ValueError, match="RAW_WIRE"):
        clock_proof(value, context.g.model_dump(mode="json"))


def test_future_auditor_receipt_cannot_authorize_earlier_review(context):
    target = Ledger(context.path / "future_audit.sqlite")
    for kind in ("PLAN", "HOST_ADMISSION"):
        for row in context.ledger.values(kind):
            target.append(kind, row)
    future = sign(
        context.cap.grant.model_copy(update={"audited_ms": DECISION + 1}),
        "SYNTHETIC_AUDITOR",
        context.auditor,
        CaptureAuditEnvelope,
    )
    target.attach_audit(context.j, future, context.roots, qa=True)
    result = Qualification(
        context.j,
        target,
        qa_roots=context.roots,
        qa_schema_roots={"accepted_product_schema_sha256": SCHEMA_HASH},
    ).assess(DECISION)
    assert result["reason"] == "CAPTURE_AUDIT_NOT_AVAILABLE_AT_REVIEW"
    assert result["stages"] == ["NATIVE_RAW_CAPTURED"]


@pytest.mark.parametrize("context", [{"messages_max": 2}], indirect=True)
def test_closed_session_with_valid_bar_and_budget_stop_is_unqualified(context):
    # Actual loopback capture admitted and durably wrote its first completed bar.
    # Ping + candle consume two messages; the close frame exceeds that budget. CLOSED only
    # certifies socket/journal closure; it must not hide that safety stop.
    assert len(context.j.records(context.g.session_id)) == 1
    with context.j.db() as db:
        assert db.execute("SELECT status FROM sessions").fetchone()[0] == "CLOSED"
    result = context.q.assess(DECISION)
    assert result["status"] == "SOURCE_BLOCKED"
    assert result["reason"] == "UNRESOLVED_NATIVE_TERMINAL_SAFETY_STOP"
    assert result["stages"] == ["NATIVE_RAW_CAPTURED"]
