"""Artificial temporary files only. Every test audits all Python/POSIX payload opens.

No legacy fixtures, research, outcomes, market sources or protected data are used.
"""

from __future__ import annotations

import builtins
import io
import json
import os
import stat
import sys
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from scripts.research.exploratory_retrospective_v1 import GateError
from scripts.research.exploratory_retrospective_v1.__main__ import main
from scripts.research.exploratory_retrospective_v1.contract import (
    ARTIFICIAL_BYTES,
    LABELS,
    digest,
    enforce_labels,
    validate,
)
from scripts.research.exploratory_retrospective_v1.runner import (
    check_fixture,
    execute,
    publish_fixture,
)
from scripts.research.exploratory_retrospective_v1.safeio import publish_new, safe_path, signature
from scripts.research.exploratory_retrospective_v1.synthetic import artificial_fixture


@pytest.fixture
def bundle():
    # Avoid deriving paths from test names (which intentionally contain denied tokens).
    with TemporaryDirectory(prefix="erv1-", dir="/tmp") as directory:
        yield artificial_fixture(Path(directory))


@pytest.fixture(autouse=True)
def payload_audit(bundle, monkeypatch):
    """Permit reads only beneath this newly generated artificial fixture directory.

    Count forbidden attempts before opening, not a self-reported runner counter.
    Both low-level descriptor access and high-level Python open are instrumented.
    """
    base = Path(bundle[3].output_root).parent
    opened = []
    forbidden = []
    originals = (os.open, builtins.open, io.open)

    def check(path):
        path = Path(path)
        try:
            safe_path(str(path))
        except GateError as exc:
            forbidden.append(str(path))
            raise AssertionError(f"Protected payload open: {path}") from exc
        if not path.is_relative_to(base):
            forbidden.append(str(path))
            raise AssertionError(f"Non-artificial payload open: {path}")
        opened.append(str(path))

    def low_open(path, flags, mode=0o777, *, dir_fd=None):
        full = Path(path)
        if not full.is_absolute():
            parent = Path(os.readlink(f"/proc/self/fd/{dir_fd}")) if dir_fd else Path.cwd()
            full = parent / full
        # Directories carry no payload; their safe descriptor traversal is expected.
        if not flags & os.O_DIRECTORY and not flags & (os.O_WRONLY | os.O_RDWR):
            check(full)
        return originals[0](path, flags, mode, dir_fd=dir_fd)

    def wrap(original):
        def high_open(path, mode="r", *args, **kwargs):
            if not isinstance(path, int) and ("r" in mode or "+" in mode):
                check(Path(path).absolute())
            return original(path, mode, *args, **kwargs)
        return high_open

    monkeypatch.setattr(os, "open", low_open)
    monkeypatch.setattr(builtins, "open", wrap(originals[1]))
    monkeypatch.setattr(io, "open", wrap(originals[2]))
    yield opened
    assert forbidden == [], "Protected payload reads and real outcome-label reads must both be zero"


def repin(bundle):
    """Test-only simulated external catalog, used to reach deeper negative gates."""
    r, s, m, t = bundle
    r["manifest_sha256"] = digest(m)
    s["manifest_sha256"] = digest(m)
    s["registration_sha256"] = digest(r)
    return replace(t, registrations=((r["experiment_id"], r["version"], digest(r)),),
                   acceptances=((digest(s), "2000-01-01T00:01:00Z"),))


def check(bundle, trust=None):
    r, s, m, t = bundle
    return check_fixture(r, s, m, t if trust is None else trust, enabled=True)


def test_positive_artificial_structure_has_no_authority(bundle, payload_audit):
    result = publish_fixture(check(bundle))
    assert result["labels"] == LABELS
    assert result["real_source_authority"] is False
    assert result["outcomes_computed"] is False
    assert len(payload_audit) == 2  # initial check and pre-publication recheck, artificial only
    output = Path(bundle[1]["output_path"])
    assert json.loads(output.read_bytes()) == result
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert "private_partition_exclusions" not in bundle[0]


def test_default_disabled_and_execute_unconditionally_blocked(bundle, payload_audit):
    with pytest.raises(GateError, match="MODE_DISABLED_BY_DEFAULT"):
        check_fixture(*bundle)
    with pytest.raises(GateError, match="REAL_EXECUTION_DISABLED"):
        execute(enabled=True, purpose="RESEARCH")
    assert payload_audit == []


@pytest.mark.parametrize("action", ["missing", "changed", "duplicate", "new_version"])
def test_immutable_unique_registration_before_reads(bundle, payload_audit, action):
    r, _s, _m, t = bundle
    if action == "missing":
        t = replace(t, registrations=())
    elif action == "changed":
        r["parameters"]["expected"] = 8
    elif action == "duplicate":
        t = replace(t, registrations=t.registrations * 2)
    else:
        r["version"] = "2"
    with pytest.raises(GateError, match="REGISTRATION"):
        check(bundle, t)
    assert payload_audit == []


@pytest.mark.parametrize("action", ["missing", "stale_hash", "duplicate", "predates", "same_time"])
def test_separate_hash_bound_acceptance(bundle, payload_audit, action):
    t = bundle[3]
    if action == "missing":
        t = replace(t, acceptances=())
    elif action == "stale_hash":
        t = replace(t, acceptances=(("0" * 64, t.acceptances[0][1]),))
    elif action == "duplicate":
        t = replace(t, acceptances=t.acceptances * 2)
    else:
        time = "1999-12-31T23:59:59Z" if action == "predates" else bundle[0]["registered_at"]
        t = replace(t, acceptances=((digest(bundle[1]), time),))
    with pytest.raises(GateError, match="ACCEPTANCE"):
        check(bundle, t)
    assert payload_audit == []


@pytest.mark.parametrize("component", [
    "protected", "outcome_panel.parquet", "private_labels.csv", "returns.csv", "A-line",
    "Final", "Forward", "OOS", "H39", "H40", "H41", ".aws", ".ssh", ".codex",
    "credentials.json", "protected_archive", "historical", "final_holdout.sqlite",
])
def test_protected_paths_and_existing_panels_rejected_before_open(bundle, payload_audit, component):
    row = bundle[2]["sources"][0]
    denied = Path(row["root"]) / component
    # Artificial sentinel, including fake panel/label names; never read it.
    with os.fdopen(os.open(denied, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
        stream.write(b"ARTIFICIAL_DENIED_SENTINEL")
    row["path"] = str(denied)
    bundle[1]["input_paths"] = [str(denied)]
    with pytest.raises(GateError, match="PROTECTED_PATH"):
        check(bundle, repin(bundle))
    assert payload_audit == []


@pytest.mark.parametrize("action", ["file_link", "ancestor_link", "traversal", "hardlink", "fifo"])
def test_unsafe_paths_never_read_targets(bundle, payload_audit, action):
    row = bundle[2]["sources"][0]
    source = Path(row["path"])
    if action == "file_link":
        target = source.with_name("target.json")
        source.rename(target)
        source.symlink_to(target)
    elif action == "ancestor_link":
        parent = source.parent
        target = parent.with_name("relocated")
        parent.rename(target)
        parent.symlink_to(target, target_is_directory=True)
    elif action == "traversal":
        row["path"] = str(source.parent / ".." / "inputs" / source.name)
        bundle[1]["input_paths"] = [row["path"]]
    elif action == "hardlink":
        os.link(source, source.with_name("alias.json"))
    else:
        source.unlink()
        os.mkfifo(source)
    with pytest.raises(GateError, match="UNSAFE|TRAVERSAL"):
        check(bundle, repin(bundle))
    assert payload_audit == []


@pytest.mark.parametrize("level", ["registration", "manifest", "file"])
@pytest.mark.parametrize("value", [None, "", "0" * 64])
def test_missing_and_mismatched_hashes(bundle, payload_audit, level, value):
    _r, s, m, t = bundle
    if level == "file":
        m["sources"][0]["sha256"] = value
        t = repin(bundle)
    else:
        s[f"{level}_sha256"] = value
        t = replace(t, acceptances=((digest(s), "2000-01-01T00:01:00Z"),))
    with pytest.raises(GateError, match="HASH|ARTIFICIAL"):
        check(bundle, t)
    assert payload_audit == []


@pytest.mark.parametrize("field", ["source", "venue", "product", "symbol", "fields", "rights"])
def test_source_identity_rights_and_mapping(bundle, payload_audit, field):
    bundle[2]["sources"][0]["identity"][field] = "UNAPPROVED"
    with pytest.raises(GateError, match="UNAPPROVED_SOURCE_IDENTITY"):
        check(bundle, repin(bundle))
    assert payload_audit == []


@pytest.mark.parametrize("claim", ["HOLDOUT_CLEAN", "OOS", "FORWARD_ONLY", "UNTOUCHED", "INDEPENDENT"])
def test_unknown_holdout_cannot_be_upgraded(bundle, payload_audit, claim):
    bundle[0]["labels"]["holdout_relationship"] = claim
    with pytest.raises(GateError, match="UNSUPPORTED_CLAIM"):
        check(bundle, repin(bundle))
    assert payload_audit == []


@pytest.mark.parametrize("target", ["FORMAL_P3", "CONFIRMATORY_VALIDATION", "Alpha", "TESTNET",
                                    "LIVE", "FUNDS"])
def test_no_promotion_or_panel_materialization(bundle, payload_audit, target):
    bundle[0]["labels"]["promotion"] = target
    with pytest.raises(GateError, match="PROMOTION"):
        check(bundle, repin(bundle))
    assert payload_audit == []


@pytest.mark.parametrize("field,value", [
    ("pit_status", "PIT_VERIFIED"), ("cost_status", "COST_COMPLETE"), ("complete_net_pnl", True),
    ("classification", "CONFIRMATORY"), ("selection_status", "UNCONTAMINATED"),
    ("source_status", "SOURCE_ADMITTED"), ("real_execution_enabled", True),
])
def test_unknown_pit_incomplete_cost_and_result_claims(bundle, payload_audit, field, value):
    bundle[0]["labels"][field] = value
    with pytest.raises(GateError, match="UNSUPPORTED_CLAIM"):
        check(bundle, repin(bundle))
    assert payload_audit == []


@pytest.mark.parametrize("action", ["unclassified", "outside_root", "outside_allowlist", "duplicate"])
def test_exact_roots_manifests_and_allowlists(bundle, payload_audit, action):
    row = bundle[2]["sources"][0]
    if action == "unclassified":
        row["classification"] = "UNKNOWN"
    elif action == "outside_root":
        row["root"] = str(Path(row["root"]).parent)
    elif action == "outside_allowlist":
        bundle[1]["input_paths"] = []
    else:
        bundle[2]["sources"].append(dict(row))
    with pytest.raises(GateError, match="CLASSIFICATION|ROOT|ALLOWLIST|DUPLICATE"):
        check(bundle, repin(bundle))
    assert payload_audit == []


@pytest.mark.parametrize("action", ["existing_file", "existing_dir", "dangling_link", "overlap"])
def test_existing_output_and_overlap(bundle, payload_audit, action):
    output = Path(bundle[1]["output_path"])
    t = bundle[3]
    if action == "existing_file":
        output.write_bytes(b"artificial existing receipt")
    elif action == "existing_dir":
        output.mkdir()
    elif action == "dangling_link":
        output.symlink_to(output.with_name("missing.json"))
    else:
        t = replace(t, output_root=t.input_roots[0])
    with pytest.raises(GateError, match="OUTPUT_EXISTS|INPUT_OUTPUT_OVERLAP"):
        check(bundle, t)
    assert payload_audit == []


@pytest.mark.parametrize("action", ["change_bytes", "replace_same_bytes", "add_hardlink"])
def test_mutation_after_acceptance_before_publication(bundle, action):
    checked = check(bundle)
    source = Path(bundle[2]["sources"][0]["path"])
    if action == "change_bytes":
        source.write_bytes(ARTIFICIAL_BYTES.replace(b"7", b"8"))
    elif action == "replace_same_bytes":
        replacement = source.with_name("replacement.json")
        replacement.write_bytes(ARTIFICIAL_BYTES)
        replacement.replace(source)
    else:
        os.link(source, source.with_name("copy.json"))
    with pytest.raises(GateError, match="HASH_MISMATCH|SOURCE_MUTATED|UNSAFE_FILE"):
        publish_fixture(checked)
    assert not Path(bundle[1]["output_path"]).exists()


def test_metadata_snapshot_and_exclusive_publication(bundle):
    checked = check(bundle)
    bundle[0]["labels"]["promotion"] = "LIVE"
    assert publish_fixture(checked)["labels"] == LABELS
    with pytest.raises(GateError, match="OUTPUT_EXISTS"):
        publish_fixture(checked)
    with pytest.raises(GateError, match="OUTPUT_EXISTS"):
        publish_new(Path(bundle[1]["output_path"]), b"ARTIFICIAL")


def test_identical_replacement_after_acceptance_before_initial_check(bundle, payload_audit):
    source = Path(bundle[2]["sources"][0]["path"])
    replacement = source.with_name("replacement.json")
    replacement.write_bytes(ARTIFICIAL_BYTES)
    replacement.replace(source)
    with pytest.raises(GateError, match="SOURCE_MUTATED_AFTER_ACCEPTANCE"):
        check(bundle)
    assert payload_audit == []


def test_wrong_bytes_with_accepted_stat_still_fail_hash_check(bundle):
    source = Path(bundle[2]["sources"][0]["path"])
    source.write_bytes(ARTIFICIAL_BYTES.replace(b"7", b"8"))
    bundle[2]["sources"][0]["file_signature"] = list(signature(source.stat()))
    with pytest.raises(GateError, match="FILE_HASH_MISMATCH"):
        check(bundle, repin(bundle))


@pytest.mark.parametrize("action", ["non_utc", "empty", "outside", "horizon", "missing_cost",
                                    "missing_feature", "extra_field", "missing_hypothesis"])
def test_bounded_contract_and_required_definitions(bundle, payload_audit, action):
    r = bundle[0]
    if action == "non_utc":
        r["windows"]["entry"][0] = "2000-01-01T01:00:00+08:00"
    elif action == "empty":
        r["windows"]["source"][1] = r["windows"]["source"][0]
    elif action == "outside":
        r["windows"]["source"][1] = "2000-01-01T02:00:00Z"
    elif action == "horizon":
        r["outcome_horizon_seconds"] = 7200
    elif action == "missing_cost":
        del r["cost_assumptions"]["funding"]
    elif action == "missing_feature":
        r["features"] = {}
    elif action == "extra_field":
        r["materialize_existing_panel"] = True
    else:
        r["hypothesis"] = ""
    with pytest.raises(ValueError):
        check(bundle, repin(bundle))
    assert payload_audit == []


def test_result_label_enforcer_rejects_unknown_claim():
    with pytest.raises(GateError, match="UNSUPPORTED_CLAIM"):
        enforce_labels({**LABELS, "net_profit": 100})


def test_cli_disabled_and_no_caller_paths(monkeypatch):
    for args in ([], ["--input", "/arbitrary/source"], ["--enable-real"]):
        monkeypatch.setattr(sys, "argv", ["erv1", *args])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 2


def test_scope_metadata_validation_does_not_open_payloads(bundle, payload_audit):
    validate(*bundle)
    assert payload_audit == []
