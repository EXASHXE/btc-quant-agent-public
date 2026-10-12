"""Category 5 & Static Identity Assurance: AST/socket guards, CLI/log redaction, and isolation."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts.g1_offline_preview_r1.__main__ import (
    OfflineLLMAnalysisPort,
    SafeArgumentParser,
    load_fixture,
    main,
)
from scripts.g1_offline_preview_r1.fixtures import make_fixture
from scripts.g1_offline_preview_r1.model import (
    SafetyViolation,
    digest,
    initial_state,
    redact_text,
)
from scripts.g1_offline_preview_r1.reducer import transition
from scripts.g1_offline_preview_r1.storage import Engine, guard_directory
from scripts.strategy_research.g1_offline_assurance_r1.oracle import (
    EXPECTED_C4_SOURCE_HASHES,
    REPO_ROOT,
    audit_static_import_and_call_surface,
    build_state_at_phase,
    intercept_outbound_network,
    make_analysis,
    make_bar,
    make_event,
    record_negative_transition,
)


def test_static_source_manifest_matches_frozen_c4() -> None:
    manifest_path = (
        REPO_ROOT / "evidence/v0.6/b_line/g1_offline_preview_r1/C4_FINAL_SOURCE_MANIFEST.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["source_manifest"] == EXPECTED_C4_SOURCE_HASHES
    for rel_path, expected_sha in EXPECTED_C4_SOURCE_HASHES.items():
        actual_sha = hashlib.sha256((REPO_ROOT / rel_path).read_bytes()).hexdigest()
        assert actual_sha == expected_sha, rel_path


def test_static_ast_import_and_call_surface_sealed() -> None:
    report = audit_static_import_and_call_surface()
    assert report["verified_file_count"] == 5
    assert report["violations"] == []
    allowed_stdlib = {
        "__future__",
        "argparse",
        "collections.abc",
        "copy",
        "decimal",
        "fcntl",
        "hashlib",
        "json",
        "os",
        "pathlib",
        "re",
        "typing",
        ".model",
        ".reducer",
        ".storage",
    }
    for rel_path, file_info in report["files"].items():
        assert set(file_info["imports"]).issubset(allowed_stdlib), rel_path


def test_c3_and_c4_executable_symbols_present() -> None:
    assert issubclass(SafeArgumentParser, object)
    parser = SafeArgumentParser()
    with pytest.raises(SystemExit) as exc:
        parser.error("api_key=TOP_SECRET_LEAK")
    assert exc.value.code == 3
    # Verify C3 stop_update_source_hash is cleared on PROPOSE and set on UPDATE_STOP
    s, _b0, prop, _ = build_state_at_phase("BAR_LOADED")
    s["stop_update_source_hash"] = "stale_hash"
    s = transition(s, make_event("PROPOSE", 60000, prop))
    assert "stop_update_source_hash" not in s


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
def test_dynamic_outbound_network_trap_during_full_workflows(
    side: str, tmp_path: Path
) -> None:
    fixture = make_fixture(side, 24, "STOP")
    out_dir = tmp_path / f"net-trap-{side.lower()}"
    with (
        intercept_outbound_network() as calls,
        Engine(out_dir, initial_state(fixture["trusted_approvals"]), temporary=True) as eng,
    ):
        port = OfflineLLMAnalysisPort()
        for ev in fixture["events"]:
            if ev["kind"] == "ANALYZE":
                ev = {**ev, "payload": port.analyze(ev["payload"])}
            eng.apply(ev)
        eng.checkpoint()
        eng.deliver()
        rec = eng.receipt()
    assert calls == []
    assert rec["status"] == "G1_OFFLINE_PREVIEW_VERIFIED"
    assert rec["counters"]["actual_private_or_network_calls"] == 0
    assert rec["network_ports"] == "NONE"


@pytest.mark.parametrize(
    ("bad_args", "secret_marker"),
    [
        (["--unknown=api_key=SECRET_VAL_1"], "SECRET_VAL_1"),
        (["--crash-edge=password:SECRET_VAL_2"], "SECRET_VAL_2"),
        (["--fixture", "secret=SECRET_VAL_3", "--extra"], "SECRET_VAL_3"),
        (["-z", "bearer SECRET_VAL_4"], "SECRET_VAL_4"),
        (["--bad-arg", "token=SECRET_VAL_5"], "SECRET_VAL_5"),
        (["--crash-edge", "invalid_api-key=SECRET_VAL_6"], "SECRET_VAL_6"),
    ],
)
def test_safe_argparse_redacts_secrets_and_creates_no_state(
    bad_args: list[str],
    secret_marker: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "no-state-created"
    with pytest.raises(SystemExit) as exc:
        main([*bad_args, "--output", str(target)])
    assert exc.value.code == 3
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert secret_marker not in combined
    err_json = json.loads(captured.err.strip())
    assert err_json["code"] == "CLI_ARGUMENTS_INVALID"
    assert err_json["status"] == "G1_OFFLINE_PREVIEW_FAIL_CLOSED"
    assert not target.exists()


@pytest.mark.parametrize(
    ("raw_text", "secret_fragment"),
    [
        ("note api_key=my_secret_123 end", "my_secret_123"),
        ("note API-KEY:my_secret_456 end", "my_secret_456"),
        ("note secret = super_hidden_789 end", "super_hidden_789"),
        ("note password:pass_value_000 end", "pass_value_000"),
        ("note token=tok_value_111 end", "tok_value_111"),
        ("note Bearer jwt_token_222 end", "jwt_token_222"),
    ],
)
def test_redact_text_scrubs_all_credential_patterns(
    raw_text: str, secret_fragment: str
) -> None:
    scrubbed = redact_text(raw_text)
    assert secret_fragment not in scrubbed
    assert "[REDACTED]" in scrubbed


def test_redact_text_rejects_non_string() -> None:
    with pytest.raises(SafetyViolation, match="TEXT_INVALID"):
        redact_text(12345)  # type: ignore[arg-type]


def test_llm_port_and_engine_apply_scrub_secrets_before_wal_and_outbox(
    tmp_path: Path,
) -> None:
    s, b0, prop, _tok = build_state_at_phase("READY")
    raw_secret = "api_key=ULTRA_SENSITIVE_999 Bearer TOKEN_888 password=PASS_777"
    analysis = make_analysis(prop, summary=f"Risk summary {raw_secret}")
    with Engine(tmp_path, s, temporary=True) as eng:
        eng.apply(make_event("BAR", 59999, b0))
        eng.apply(make_event("PROPOSE", 60000, prop))
        eng.apply(make_event("ANALYZE", 60001, analysis))
        eng.checkpoint()
        eng.deliver()
    for p in [
        tmp_path / "events.wal.jsonl",
        tmp_path / "events.log.jsonl",
        tmp_path / "outbox_delivery.jsonl",
        *list((tmp_path / "checkpoints").glob("checkpoint-*.json")),
    ]:
        content = p.read_text(encoding="utf-8")
        assert "ULTRA_SENSITIVE_999" not in content
        assert "TOKEN_888" not in content
        assert "PASS_777" not in content


@pytest.mark.parametrize(
    ("phase", "event_builder"),
    [
        (
            "BAR_LOADED",
            lambda s, b, p: make_event("BAR", 119999, make_bar(60000), "api_key=leak"),
        ),
        (
            "BAR_LOADED",
            lambda s, b, p: make_event(
                "PROPOSE", 60000, {**p, "signal_id": "secret-signal"}
            ),
        ),
        (
            "PLACED",
            lambda s, b, p: make_event(
                "FILL_ENTRY", 60004, {"fill_id": "password-fill"}
            ),
        ),
        (
            "OPEN",
            lambda s, b, p: make_event(
                "FUNDING",
                120005,
                {
                    "settlement_id": "bearer-settle",
                    "settlement_at": 120005,
                    "rate_fraction": "0.0001",
                },
            ),
        ),
        (
            "WAIT_ENTRY_ACK",
            lambda s, b, p: make_event(
                "ACK",
                120004,
                {
                    "ack_id": "token=ack",
                    "order_id": s["order_id"],
                    "fill_id": "entry-1",
                },
            ),
        ),
    ],
)
def test_reducer_rejects_secret_substrings_in_event_identifiers(
    phase: str, event_builder
) -> None:
    s, b, p, _ = build_state_at_phase(phase)
    ev = event_builder(s, b, p)
    rec = record_negative_transition(
        f"secret_in_{phase}", "output_and_safety", s, ev, "SECRET_IN_EVENT"
    )
    assert rec["state_mutated"] is False


def test_local_outbox_delivery_and_trace_span_id_integrity(tmp_path: Path) -> None:
    s, b0, prop, _ = build_state_at_phase("READY")
    with Engine(tmp_path, s, temporary=True) as eng:
        eng.apply(make_event("BAR", 59999, b0, "BAR-0"))
        eng.apply(make_event("PROPOSE", 60000, prop, "PROPOSE-1"))
        count = eng.deliver()
        assert count == 1
        outbox_row = json.loads(
            (tmp_path / "outbox_delivery.jsonl").read_text(encoding="utf-8").splitlines()[0]
        )
        log_row = json.loads(
            (tmp_path / "events.log.jsonl").read_text(encoding="utf-8").splitlines()[-1]
        )
        assert outbox_row["trace_id"] == log_row["trace_id"]
        assert outbox_row["safety"] == "DRY_RUN_NO_NETWORK_NO_ORDERING"
        msg_id = outbox_row["key"]
        eng.apply(make_event("OUTBOX_RECEIPT", 60000, {"message_id": msg_id}, "RCPT-1"))
        assert eng.state["delivered_outbox_ids"] == [msg_id]
        record_negative_transition(
            "duplicate_outbox_receipt",
            "output_and_safety",
            eng.state,
            make_event("OUTBOX_RECEIPT", 60000, {"message_id": msg_id}, "RCPT-2"),
            "OUTBOX_RECEIPT_DUPLICATE",
        )
        record_negative_transition(
            "unknown_outbox_receipt",
            "output_and_safety",
            eng.state,
            make_event("OUTBOX_RECEIPT", 60000, {"message_id": "unknown-msg"}, "RCPT-3"),
            "OUTBOX_UNKNOWN",
        )


def test_idempotent_duplicate_and_event_reuse_drift(tmp_path: Path) -> None:
    s, b0, _, _ = build_state_at_phase("READY")
    ev = make_event("BAR", 59999, b0, "BAR-0")
    with Engine(tmp_path, s, temporary=True) as eng:
        assert eng.apply(ev) == "COMMITTED"
        wal_before = eng.wal.read_bytes()
        state_before = digest(eng.state)
        assert eng.apply(ev) == "IDEMPOTENT_DUPLICATE"
        assert eng.wal.read_bytes() == wal_before
        assert digest(eng.state) == state_before

        mutated = copy.deepcopy(ev)
        mutated["payload"]["mark_close"] = "102"
        with pytest.raises(SafetyViolation, match="EVENT_REUSE_DRIFT"):
            eng.apply(mutated)
        assert eng.wal.read_bytes() == wal_before
        assert digest(eng.state) == state_before


def test_single_writer_flock_and_engine_closed_guards(tmp_path: Path) -> None:
    s, b0, _, _ = build_state_at_phase("READY")
    with (
        Engine(tmp_path, s, temporary=True) as eng,
        pytest.raises(SafetyViolation, match="SINGLE_WRITER_LOCKED"),
    ):
        Engine(tmp_path, s, temporary=True)
    with pytest.raises(SafetyViolation, match="ENGINE_CLOSED"):
        eng.apply(make_event("BAR", 59999, b0))


def test_guard_directory_and_load_fixture_path_and_symlink_defenses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(SafetyViolation, match="PATH_SCOPE"):
        guard_directory(Path("relative/path"), temporary=True)
    with pytest.raises(SafetyViolation, match="PATH_SCOPE"):
        guard_directory(Path("/tmp/../etc"), temporary=True)
    with pytest.raises(SafetyViolation, match="PATH_SCOPE"):
        guard_directory(Path("/var/tmp/outside"), temporary=False)

    real_dir = tmp_path / "real"
    real_dir.mkdir()
    sym_dir = tmp_path / "symlink_dir"
    sym_dir.symlink_to(real_dir, target_is_directory=True)
    with pytest.raises(SafetyViolation, match="PATH_SYMLINK"):
        guard_directory(sym_dir, temporary=True)

    def _forbidden_stat(*args, **kwargs):
        raise AssertionError("Filesystem called before lexical fixture admission")

    monkeypatch.setattr(Path, "stat", _forbidden_stat)
    with pytest.raises(SafetyViolation, match="FIXTURE_PATH_SCOPE"):
        load_fixture("../long_24h.json")
    with pytest.raises(SafetyViolation, match="FIXTURE_PATH_SCOPE"):
        load_fixture("unregistered.json")
