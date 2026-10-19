"""Two-phase contract tests use only tiny synthetic PASS ZIP archives."""

import hashlib
import json

import pytest

from scripts.research.cross_venue import normalized_sources as n
from scripts.research.exposed_dev_bridge import archive_adapter as adapter
from scripts.research.exposed_dev_bridge import authorization as auth
from scripts.research.exposed_dev_bridge import pipeline as cli
from scripts.research.exposed_dev_bridge.synthetic_fullfold import run_fullfold
from scripts.research.strategy_eval import pipeline as p1

from .test_archive_adapter import zip_scope


def derived(fixture):
    scope, doc, _, output, _, _ = fixture
    doc["authorization"]["outcome_panel_materialization"] = "AUTHORIZE_EXPOSED_DEV_PANEL_MATERIALIZATION"
    doc["p1_binding"] = {"mode": "DERIVED_P1_INTEGRITY_V1",
        "panel_path": str(output / "normalized_panel.json"),
        "allowlist_path": str(output / "p1_integrity_allowlist.json"),
        "start_utc_s": doc["p1_binding"]["start_utc_s"],
        "end_utc_s": doc["p1_binding"]["end_utc_s"]}
    scope.write_bytes(n.canonical_bytes(doc))
    return scope, doc, output


def test_two_phase_materializes_then_binds_actual_panel_bytes(zip_scope):
    scope, _, output = derived(zip_scope)
    result = cli.materialize(scope, output)
    assert result["exit_code"] == 0 and result["status"] == "AUTHORIZED_PANEL_PARSED"
    panel, allowlist = output / "normalized_panel.json", output / "p1_integrity_allowlist.json"
    doc = json.loads(allowlist.read_bytes())
    assert doc["binding_kind"] == "DERIVED_INTEGRITY_NOT_OWNER_AUTHORIZATION"
    assert doc["owner_scope_sha256"] == hashlib.sha256(scope.read_bytes()).hexdigest()
    assert doc["panels"][0]["sha256"] == hashlib.sha256(panel.read_bytes()).hexdigest()
    rows, _, _ = p1.authorized_panel(panel, allowlist)
    assert len(rows) == 72 and result["outcome_labels_read"] > 0
    assert all(r["action"] == "NO_ACTION" for r in rows)
    assert "24" not in rows[-1]["outcomes"]  # Exit beyond the authorized right edge stays missing.
    assert all(v == 72 for v in result["horizon_denominators"].values())
    panel.write_bytes(panel.read_bytes() + b" ")
    with pytest.raises(ValueError, match="EXPOSED_DEV_NOT_AUTHORIZED"):
        p1.authorized_panel(panel, allowlist)


@pytest.mark.parametrize("change,reason", [
    ("unsigned", "EXPLICIT_OWNER_AUTHORIZATION_REQUIRED"),
    ("permission", "OWNER_PANEL_MATERIALIZATION_PERMISSION_REQUIRED"),
    ("private_unknown", "PRIVATE_PROTECTED_PARTITIONS_UNCONFIRMED"),
    ("attestation_missing", "PRIVATE_PROTECTED_PARTITIONS_UNCONFIRMED"),
    ("wrong_market", "SCOPE_SOURCE_IDENTITY_MISMATCH"),
    ("bad_hash", "SCOPE_FILE_IDENTITY_OR_HASH_MISMATCH"),
    ("h39", "PROTECTED_DATE_OVERLAP"),
    ("binding_hash", "DERIVED_HASH_MUST_NOT_BE_PREAUTHORIZED"),
    ("wrong_contract", "P1_ALLOWLIST_REQUIRED"),
    ("exit_boundary", "P1_INTERVAL_OUTSIDE_OWNER_ORIGINS"),
])
def test_phase_zero_denials_read_no_outcome_rows(zip_scope, monkeypatch, change, reason):
    scope, doc, output = derived(zip_scope)
    if change == "unsigned":
        doc["authorization"]["decision"] = "UNSIGNED_PROPOSAL_HOLD"
    elif change == "permission":
        doc["authorization"].pop("outcome_panel_materialization")
    elif change == "private_unknown":
        doc["governance"]["private_partition_attestations"]["A_LINE"]["status"] = "UNKNOWN"
    elif change == "attestation_missing":
        doc["governance"]["private_partition_attestations"].pop("OOS")
    elif change == "wrong_market":
        doc["sources"][0]["files"][0]["market"] = "spot"
    elif change == "bad_hash":
        doc["sources"][0]["files"][0]["sha256"] = "f" * 64
    elif change == "h39":
        doc["archive_ranges"][0]["end_utc"] = "2026-10-01T00:00:00Z"
    elif change == "binding_hash":
        doc["p1_binding"]["panel_sha256"] = "0" * 64
    elif change == "wrong_contract":
        doc["p1_binding"]["mode"] = "UNKNOWN_PROTOCOL"
    elif change == "exit_boundary":
        doc["p1_binding"]["end_utc_s"] += 86400
    scope.write_bytes(n.canonical_bytes(doc))
    monkeypatch.setattr(adapter, "panel_rows", lambda *a: pytest.fail("Outcome source opened"))
    result = cli.materialize(scope, output)
    assert result["exit_code"] == 2 and result["blockers"] == [reason]
    assert result["outcome_labels_read"] == 0
    assert not (output / "normalized_panel.json").exists()
    assert not (output / "p1_integrity_allowlist.json").exists()


def test_interrupted_stage_never_publishes_panel_or_allowlist(zip_scope, monkeypatch):
    scope, _, output = derived(zip_scope)
    def broken(*args):
        yield {"t": 1}
        raise n.BridgeError("INTERRUPTED_STAGING")
    monkeypatch.setattr(adapter, "panel_rows", broken)
    result = cli.materialize(scope, output)
    assert result["exit_code"] == 2 and result["blockers"] == ["INTERRUPTED_STAGING"]
    assert not any(output.glob("*panel.json"))
    assert not (output / ".normalized_panel.json.stage").exists()
    assert not (output / "p1_integrity_allowlist.json").exists()


def test_post_stage_tamper_quarantines_both_outputs(zip_scope, monkeypatch):
    scope, _, output = derived(zip_scope)
    original = adapter._verify_inputs
    calls = 0
    def tamper(permit, ledger):
        nonlocal calls
        calls += 1
        original(permit, ledger)
        if calls == 2:
            panel = output / "normalized_panel.json"
            panel.write_bytes(panel.read_bytes() + b" ")
    monkeypatch.setattr(adapter, "_verify_inputs", tamper)
    result = cli.materialize(scope, output)
    assert result["exit_code"] == 2 and result["blockers"] == ["POST_STAGE_TAMPER_DETECTED"]
    assert not (output / "normalized_panel.json").exists()
    assert not (output / "p1_integrity_allowlist.json").exists()


@pytest.fixture(scope="module")
def fullfold(tmp_path_factory):
    output = tmp_path_factory.mktemp("p4-fullfold") / "run"
    return output, run_fullfold(output)


def test_fullfold_actual_p1_three_outer_folds_and_sparse_labels(fullfold):
    output, summary = fullfold
    assert summary["origin_count"] == 2016
    assert summary["executed_outer_folds"] == 3
    assert summary["cell_count"] == 48
    assert summary["evaluation_status"] == "EVALUATED_OFFLINE"
    assert [f["development_end_day"] for f in summary["folds"]] == [42, 56, 70]
    assert all(f["scheduled_validation"] == 336 and f["model_count"] == 8 for f in summary["folds"])
    assert all(f["training_max_label_end_utc_s"] < f["validation_start_utc_s"] - 3600
               for f in summary["folds"])
    assert all(v == 2016 for v in summary["origin_horizon_denominators"].values())
    assert all(v > 0 for v in summary["sparse_missing_outcomes"].values())
    assert summary["real_outcome_labels_read"] == 0
    rows, _, _ = p1.authorized_panel(output / "normalized_panel.json",
                                    output / "p1_synthetic_integrity_allowlist.json")
    assert len(rows) == 2016 and any(not r["outcomes"] for r in rows[-24:])
