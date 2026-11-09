from __future__ import annotations

import json
from pathlib import Path

import pytest

from btc_quant_agent.platform.evaluation_adapter import evaluate_export
from btc_quant_agent.platform.program_c_export import build_export, write_export
from btc_quant_agent.platform.rc_operator import recover, run_demo, status
from btc_quant_agent.platform.rc_store import RCStore


@pytest.mark.parametrize("all_no_setup", [False, True])
def test_actual_generated_export_to_c_and_restart(tmp_path, all_no_setup):
    output = tmp_path / "operator"
    first = run_demo(output, all_no_setup=all_no_setup)
    initial_status = status(output)
    original_plan = (output / "initial/latest.json").read_bytes()
    store = RCStore(output / "state.sqlite", readonly=True)
    value = build_export(store)
    path = write_export(output, value)
    result = evaluate_export(path, tmp_path / "evaluation")
    assert result["scientific_decision"] == "INSUFFICIENT_SUPPORT"
    report = (tmp_path / "evaluation/scientific_report.md").read_text()
    if not all_no_setup:
        assert "MISSING_COVERAGE" in report
        assert "TARGET_FIRST" in report
    assert status(output) == initial_status
    second = run_demo(output, all_no_setup=all_no_setup)
    assert first["decision_digests"] == second["decision_digests"]
    assert first["snapshot_sha256"] == second["snapshot_sha256"]
    assert (output / "initial/latest.json").read_bytes() == original_plan
    (output / "latest.html").unlink()
    recover(output)
    assert (output / "latest.html").is_file()


def test_changed_export_cannot_be_evaluated(tmp_path):
    output = tmp_path / "operator"
    run_demo(output)
    store = RCStore(output / "state.sqlite", readonly=True)
    value = build_export(store)
    value["no_setup_decision_count"] += 1
    from btc_quant_agent.platform.core import fingerprint
    value["export_sha256"] = fingerprint({k: v for k, v in value.items() if k != "export_sha256"})
    path = output / "modified.json"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        evaluate_export(path, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


def test_original_verifier_functions_are_verbatim():
    import ast
    root = Path(__file__).resolve().parents[2]
    original = json.loads((root / "audit/original_verifier.json").read_text())
    source = root.parent / original["path"]
    if not source.exists():
        pytest.skip("Original input unavailable in standalone public checkout; extraction hash receipt retained")
    import hashlib
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original["sha256"]
    trees = [ast.parse(p.read_text()) for p in
             (source, root / "src/btc_quant_agent/platform/owner_verifier.py")]
    for name in original["functions"]:
        nodes = [next(n for n in t.body if isinstance(n, ast.FunctionDef) and n.name == name) for t in trees]
        assert ast.dump(nodes[0], include_attributes=False) == ast.dump(nodes[1], include_attributes=False)
