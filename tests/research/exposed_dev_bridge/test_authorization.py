import copy
import json
import os
import time

import pytest

from scripts.research.cross_venue import normalized_sources as n
from scripts.research.exposed_dev_bridge import authorization as a
from scripts.research.exposed_dev_bridge import pipeline as cli


def save(scope, doc):
    scope.write_bytes(n.canonical_bytes(doc))


def test_valid_synthetic_scope_is_only_scope_authorization_and_history_hold(owner_scope, tmp_path):
    scope, _, _, _ = owner_scope
    gate = a.validate_scope(scope)
    assert gate["gate_status"] == "AUTHORIZED_SCOPE_ONLY"
    assert len(gate["verified_files"]) == 1 and all(s["unchanged"] for s in gate["sources"])
    result = cli.materialize(scope, tmp_path / "out")
    assert result["status"] == "AUTHORIZATION_DENIED" and result["exit_code"] == 2
    assert result["blockers"] == ["OWNER_SCOPE_V2_REQUIRED"]
    assert result["historical_outcomes_evaluated"] == result["outcome_labels_read"] == 0
    assert not result["evaluation_delegated"]
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == sorted(cli.OUTPUT_FILES)


def test_long_synthetic_scope_still_holds_unattested_outcome_coverage(owner_scope, tmp_path):
    scope, doc, _, _ = owner_scope
    doc["development_ranges"][0]["end_utc"] = "2026-10-01T00:00:00Z"
    save(scope, doc)
    result = cli.materialize(scope, tmp_path / "out")
    assert result["status"] == "AUTHORIZATION_DENIED" and result["exit_code"] == 2
    assert result["blockers"] == ["OWNER_SCOPE_V2_REQUIRED"]
    assert result["outcome_labels_read"] == 0


def test_materialize_output_cannot_be_nested_in_authorized_source(owner_scope):
    scope, _, root, _ = owner_scope
    output = root / "new-output"
    with pytest.raises(n.BridgeError, match="OUTPUT_INPUT_ALIAS"):
        cli.materialize(scope, output)
    assert not output.exists()


@pytest.mark.parametrize("change,reason", [
    (lambda d: d.update(exposure="HISTORICAL"), "EXPOSED_DEV_NOT_AUTHORIZED"),
    (lambda d: d.pop("authorization"), "EXPLICIT_OWNER_AUTHORIZATION_REQUIRED"),
    (lambda d: d["authorization"].update(role="Controller"), "EXPLICIT_OWNER_AUTHORIZATION_REQUIRED"),
    (lambda d: d["authorization"].update(decision="INSPECT"), "EXPLICIT_OWNER_AUTHORIZATION_REQUIRED"),
    (lambda d: d["authorization"].update(owner=""), "EXPLICIT_OWNER_AUTHORIZATION_REQUIRED"),
    (lambda d: d["authorization"].update(issued_at_utc="2099-01-01T00:00:00Z"), "OWNER_AUTHORIZATION_IN_FUTURE"),
    (lambda d: d["governance"].update(protected_dates_complete=False), "GOVERNED_HOLDOUT_DATES_UNRESOLVED"),
    (lambda d: d["governance"].update(holdout_status="UNKNOWN"), "GOVERNED_HOLDOUT_DATES_UNRESOLVED"),
    (lambda d: d["governance"].update(protected_date_exclusions=[]), "SCOPE_DATE_RANGES_REQUIRED"),
    (lambda d: d["sources"][0].update(files=[]), "EXACT_FILES_REQUIRED"),
    (lambda d: d["sources"][0].update(root="//tmp/alias"), "SCOPE_PATH_NOT_CANONICAL"),
    (lambda d: d["sources"][0]["files"][0].update(path="../labels.json"), "SCOPE_FILE_PATH_INVALID"),
    (lambda d: d["sources"][0]["files"][0].update(path="/tmp/labels.json"), "SCOPE_FILE_PATH_INVALID"),
    (lambda d: d["sources"][0]["files"][0].update(path="data//metrics/file.zip"), "SCOPE_FILE_PATH_INVALID"),
    (lambda d: d["sources"][0]["files"][0].update(family="orderbook"), "SCOPE_NON_FEATURE_FILE_FORBIDDEN"),
    (lambda d: d["sources"][0]["files"][0].update(market="spot"), "SCOPE_SOURCE_IDENTITY_MISMATCH"),
    (lambda d: d["sources"][0]["files"][0].update(sha256="x" * 64), "SCOPE_HASH_INVALID"),
    (lambda d: d["sources"][0]["files"][0].update(end_utc="2026-07-04T00:00:00Z"), "FILE_DATE_OUTSIDE_AUTHORIZED_DEVELOPMENT"),
])
def test_denied_before_any_archive_hash_or_outcome_read(owner_scope, monkeypatch, change, reason):
    scope, doc, _, _ = owner_scope
    change(doc)
    save(scope, doc)
    def forbidden(*args, **kwargs):
        pytest.fail("Denied scope reached a raw archive")
    monkeypatch.setattr(a, "_digest", forbidden)
    with pytest.raises(n.BridgeError, match=reason):
        a.validate_scope(scope)


def test_protected_date_exclusion_rejects_development_overlap_before_any_file(owner_scope, monkeypatch):
    scope, doc, _, _ = owner_scope
    doc["governance"]["protected_date_exclusions"][0].update(
        start_utc="2026-07-02T00:00:00Z", end_utc="2026-07-03T00:00:00Z")
    save(scope, doc)
    monkeypatch.setattr(n.Snapshot, "capture", lambda *a: pytest.fail("Protected scope opened metadata"))
    with pytest.raises(n.BridgeError, match="PROTECTED_DATE_OVERLAP"):
        a.validate_scope(scope)


def test_partial_archive_dates_are_not_permission_to_exhaust_protected_rows(owner_scope):
    scope, doc, _, _ = owner_scope
    doc["sources"][0]["files"][0]["end_utc"] = "2026-07-01T01:00:00Z"
    save(scope, doc)
    with pytest.raises(n.BridgeError, match="FULL_ARCHIVE_DATE_AUTHORIZATION_REQUIRED"):
        a.validate_scope(scope)


@pytest.mark.parametrize("field", ["manifest_sha256", "qc_sha256"])
def test_exact_metadata_hash_required(owner_scope, field):
    scope, doc, _, _ = owner_scope
    doc["sources"][0][field] = "0" * 64
    save(scope, doc)
    with pytest.raises(n.BridgeError, match="SCOPE_METADATA_HASH_MISMATCH"):
        a.validate_scope(scope)


def test_raw_changed_hash_rejected(owner_scope):
    scope, _, root, record = owner_scope
    path = root / record["local_path"]
    raw = bytearray(path.read_bytes())
    raw[len(raw) // 2] ^= 1
    path.write_bytes(raw)
    with pytest.raises(n.BridgeError, match="SCOPE_RAW_HASH_MISMATCH"):
        a.validate_scope(scope)


def test_raw_changed_between_gate_hashes_is_input_changed(owner_scope, monkeypatch):
    scope, _, root, record = owner_scope
    original = a._digest
    calls = 0
    def change(path):
        nonlocal calls
        calls += 1
        digest = original(path)
        if calls == 1:
            raw = bytearray(path.read_bytes())
            raw[len(raw) // 2] ^= 1
            path.write_bytes(raw)
        return digest
    monkeypatch.setattr(a, "_digest", change)
    with pytest.raises(n.BridgeError, match="INPUT_CHANGED"):
        a.validate_scope(scope)
    assert (root / record["local_path"]).is_file()


def test_raw_removed_between_gate_hashes_is_input_changed(owner_scope, monkeypatch):
    scope, _, _, _ = owner_scope
    original = a._digest
    def remove_after_hash(path):
        result = original(path)
        path.unlink()
        return result
    monkeypatch.setattr(a, "_digest", remove_after_hash)
    with pytest.raises(n.BridgeError, match="INPUT_CHANGED"):
        a.validate_scope(scope)


@pytest.mark.parametrize("kind", ["root_symlink", "file_symlink", "file_hardlink", "duplicate_root", "protected_path"])
def test_path_confinement_no_aliases(owner_scope, tmp_path, kind):
    scope, doc, root, record = owner_scope
    source = doc["sources"][0]
    if kind == "root_symlink":
        alias = tmp_path / "alias"
        alias.symlink_to(root, target_is_directory=True)
        source["root"] = str(alias)
        reason = "UNSAFE_OR_MISSING_DIRECTORY"
    elif kind in ("file_symlink", "file_hardlink"):
        path = root / record["local_path"]
        other = tmp_path / "other.zip"
        path.rename(other)
        if kind == "file_symlink":
            path.symlink_to(other)
            reason = "UNSAFE_OR_MISSING_FILE"
        else:
            os.link(other, path)
            reason = "UNSAFE_FILE_TYPE_OR_HARDLINK"
    elif kind == "duplicate_root":
        doc["sources"].append(copy.deepcopy(source))
        reason = "ROOT_ALIAS_OR_DUPLICATE"
    else:
        source["root"] = str(tmp_path / "holdout")
        reason = "PROTECTED_PATH"
    save(scope, doc)
    with pytest.raises(n.BridgeError, match=reason):
        a.validate_scope(scope)


def test_nonpass_archive_is_never_opened(owner_scope, monkeypatch):
    scope, doc, root, record = owner_scope
    from .conftest import publish
    record["verdict"] = "OBJECT_NOT_FOUND"
    publish(root, "binance", [record])
    import hashlib
    for filename, key in (("manifest.json", "manifest_sha256"), ("qc.json", "qc_sha256")):
        doc["sources"][0][key] = hashlib.sha256((root / filename).read_bytes()).hexdigest()
    save(scope, doc)
    monkeypatch.setattr(a, "_digest", lambda *a: pytest.fail("NON_PASS archive opened"))
    with pytest.raises(n.BridgeError, match="SCOPE_FILE_NOT_PASS"):
        a.validate_scope(scope)


def test_no_allowlist_missing_file_and_exposure_label_alone_deny(tmp_path):
    missing = tmp_path / "absent.json"
    assert cli.main(["materialize", "--scope", str(missing), "--output-dir", str(tmp_path / "one")]) == 2
    missing.write_text('{"exposure":"EXPOSED_DEV","outcomes":"MUST_NOT_BE_READ"}')
    result = cli.materialize(missing, tmp_path / "two")
    assert result["status"] == "AUTHORIZATION_DENIED" and result["outcome_labels_read"] == 0
    gate = json.loads((tmp_path / "two/authorization_gate.json").read_text())
    assert gate["reason"] == "EXPOSED_DEV_NOT_AUTHORIZED"


def test_scope_must_preexist_and_no_duplicate_json_keys(owner_scope):
    scope, _, _, _ = owner_scope
    with pytest.raises(n.BridgeError, match="SCOPE_NOT_PREEXISTING"):
        a.validate_scope(scope, started_ns=time.time_ns() - 60_000_000_000)
    scope.write_text('{"exposure":"EXPOSED_DEV","exposure":"EXPOSED_DEV"}')
    with pytest.raises(n.BridgeError, match="DUPLICATE_JSON_KEY"):
        a.validate_scope(scope)


@pytest.mark.parametrize("kind", ["root", "symlink", "nonempty"])
def test_output_confinement(empty_roots, tmp_path, kind):
    if kind == "root":
        output = empty_roots["Q3", "binance"] / "new"
        reason = "OUTPUT_INPUT_ALIAS"
    elif kind == "symlink":
        output = tmp_path / "output-link"
        target = tmp_path / "target"
        target.mkdir()
        output.symlink_to(target, target_is_directory=True)
        reason = "UNSAFE_OR_MISSING_DIRECTORY"
    else:
        output = tmp_path / "occupied"
        output.mkdir()
        (output / "keep").write_text("preserve")
        reason = "OUTPUT_DIRECTORY_NOT_EMPTY"
    with pytest.raises(n.BridgeError, match=reason):
        cli.inspect(empty_roots, output)
