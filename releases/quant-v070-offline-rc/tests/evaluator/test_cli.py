from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from program_c.cli import main
from program_c.integrity import WORKSPACE, canonical, digest
from program_c.protocol import FLAGS


def test_frozen_b_cli_and_report(tmp_path):
    output = tmp_path / "evaluation"
    assert main(["evaluate", "--input", str(WORKSPACE / "inputs/B_episode_export.original.json"),
                 "--output", str(output)]) == 0
    summary = json.loads((output / "summary.json").read_bytes())
    assert summary["scientific_decision"] == "INSUFFICIENT_SUPPORT"
    assert summary["denominators"]["NO_SETUP_decisions"] == 2
    assert summary["unknown_path_fraction"] == 1
    text = (output / "scientific_report.md").read_text()
    assert "3.783014" in text and "3.318973" in text
    assert "EX_ANTE_GEOMETRY_NOT_OBSERVED_RETURN" in text
    assert "MISSING_COVERAGE" in text
    for key, value in FLAGS.items():
        assert json.loads((output / "status.json").read_bytes())[key] == value


def test_no_silent_overwrite(tmp_path):
    output = tmp_path / "already"
    output.mkdir()
    (output / "sentinel").write_text("keep")
    assert main(["plan", "--protocol", str(WORKSPACE / "frozen_protocol.json"), "--output", str(output)]) == 2
    assert list(output.iterdir()) == [output / "sentinel"]
    assert (output / "sentinel").read_text() == "keep"


def test_restart_replays_byte_identical(tmp_path):
    outputs = [tmp_path / "run1", tmp_path / "run2"]
    env = dict(os.environ, PYTHONPATH=str(WORKSPACE / "src"), PYTHONDONTWRITEBYTECODE="1")
    for output in outputs:
        result = subprocess.run([sys.executable, "-B", "-m", "program_c", "evaluate", "--input",
                                 str(WORKSPACE / "fixtures/winning_unambiguous.json"), "--output", str(output)],
                                env=env, cwd=WORKSPACE, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
    assert sorted(p.name for p in outputs[0].iterdir()) == sorted(p.name for p in outputs[1].iterdir())
    for path in outputs[0].iterdir():
        assert path.read_bytes() == (outputs[1] / path.name).read_bytes(), path.name


@pytest.mark.parametrize("command,argument,input_path", [
    ("validate", "--input", "inputs/B_episode_export.original.json"),
    ("scenarios", "--fixtures", "fixtures/suite.json"),
    ("plan", "--protocol", "frozen_protocol.json"),
])
def test_commands_are_runnable(tmp_path, command, argument, input_path):
    assert main([command, argument, str(WORKSPACE / input_path), "--output", str(tmp_path / command)]) == 0


def test_failure_has_machine_reason(tmp_path):
    output = tmp_path / "rejected"
    assert main(["evaluate", "--input", str(WORKSPACE / "fixtures/future_leaking_receipt.json"),
                 "--output", str(output)]) == 2
    failure = json.loads((output / "failure.json").read_bytes())
    assert failure["reason"] == "FUTURE_RECEIPT_AFTER_ASOF"
    assert not (output / "scenario_ledger.json").exists()


def test_untrusted_protocol_rejected(tmp_path, protocol):
    protocol["trusted_native_admission_roots"] = ["f"*64]
    protocol["protocol_sha256"] = digest({k:v for k,v in protocol.items() if k != "protocol_sha256"})
    path = tmp_path / "changed.json"
    path.write_bytes(canonical(protocol))
    assert main(["plan", "--protocol", str(path), "--output", str(tmp_path / "plan")]) == 2


def test_output_cannot_escape_workspace(tmp_path):
    assert main(["plan", "--protocol", str(WORKSPACE / "frozen_protocol.json"), "--output", "/tmp/program_c_escape"]) == 2
    assert not Path("/tmp/program_c_escape").exists()


def test_symlink_input_rejected_before_open(tmp_path):
    link = tmp_path / "input.json"
    link.symlink_to(WORKSPACE / "inputs/B_episode_export.original.json")
    assert main(["evaluate", "--input", str(link), "--output", str(tmp_path / "blocked")]) == 2


def test_evaluator_has_no_network_or_process_interfaces():
    forbidden = {"socket", "requests", "urllib", "http", "httpx", "aiohttp", "subprocess", "ccxt"}
    for path in (WORKSPACE / "src/program_c").glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not {n.name.split(".")[0] for n in node.names} & forbidden
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden
