"""Installed-package demonstration using only fabricated loopback REST/TLS bytes."""

from __future__ import annotations
import contextlib
import io
import ipaddress
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import socket
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests/live"), str(ROOT / "tests/native")]


def main_demo():
    from local_swing import SwingVenue
    from btc_quant_agent.platform.live import models, product, source, store, swing_review
    from btc_quant_agent.platform.live.cli import main
    from btc_quant_agent.platform.native.contract import digest

    actual_connect = socket.socket.connect

    def local_only(sock, address):
        if sock.family == socket.AF_UNIX or ipaddress.ip_address(address[0]).is_loopback:
            return actual_connect(sock, address)
        raise AssertionError("L_OFFLINE_DEMO_EXTERNAL_NETWORK_FORBIDDEN")

    actual_sample = models.sample

    def qa_sample():
        s = actual_sample()
        s["wall_ms"] = s["mono_before_ms"] + 1000000000000
        return s

    runtime = Path(tempfile.mkdtemp(prefix="quant-l-synthetic-"))
    artifact = ROOT / "artifacts/SYNTHETIC_OFFLINE_QA"
    assert not artifact.exists(), "DEMO_ARTIFACT_OUTPUT_MUST_BE_UNUSED"
    artifact.mkdir(parents=True)
    results = []
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(socket.socket, "connect", local_only))
        stack.enter_context(patch.object(socket.socket, "connect_ex", local_only))
        for module in (source, store, product, swing_review):
            stack.enter_context(patch.object(module, "sample", qa_sample))
        for name, flat in [("positive_30m", False), ("all_NO_SETUP_30m", True)]:
            v = SwingVenue(runtime / (name + "_tls"), minutes=30, flat=flat)
            try:
                s = store.Store(runtime / name, create=True, exposure=models.QA)
                p = swing_review.product_for(s, swing_review.VERSION, 120)
                snapshot = swing_review.SwingCollector(s, _qa=v.qa).run()
                decisions = [p.review(symbol) for symbol in models.POLICY["symbols"]]
                expected = ["NO_SETUP"] * 3 if flat else ["WATCH", "NO_SETUP", "NO_SETUP"]
                assert [d.market_state for d in decisions] == expected
                before = [d.model_dump(mode="json") for d in decisions]
                for d in decisions:
                    if d.episode_id:
                        p.observe(d.episode_id)
                assert [
                    d.model_dump(mode="json")
                    for d in swing_review.product_for(store.Store(s.directory)).decisions()
                ] == before
                cli = {}
                for command in ["status", "opportunities", "episodes", "dashboard"]:
                    out = io.StringIO()
                    with contextlib.redirect_stdout(out):
                        code = main([command, "--output", str(s.directory)])
                    cli[command] = {"exit_code": code, "result": json.loads(out.getvalue())}
                    assert code == 0
                report = p.evaluate(runtime / (name + "_C"))
                assert report["scientific_decision"] == "INSUFFICIENT_SUPPORT"
                assert report["actual_C_validator_error"] == "SOURCE_CLASS_INVALID"
                target = artifact / name
                shutil.copytree(s.directory, target)
                shutil.copytree(runtime / (name + "_C"), artifact / (name + "_C"))
                (artifact / (name + "_CLI.json")).write_text(json.dumps(cli, indent=2, sort_keys=True) + "\n")
                results.append(
                    {
                        "name": name,
                        "evidence_class": models.QA,
                        "actual_market_requests": 0,
                        "local_fabricated_HTTPS_requests": snapshot["requests"],
                        "local_request_weight": snapshot["request_weight"],
                        "actual_synthetic_review_delay_ms": [
                            d.decision_ms - d.trigger_close_ms for d in decisions
                        ],
                        "source_snapshot_sha256": digest(snapshot),
                        "clock": snapshot["clock"],
                        "states": expected,
                        "frozen_decisions_unchanged_after_observe_restart": True,
                        "C_boundary": report,
                        "artifact_directory": str(target.relative_to(ROOT)),
                    }
                )
            finally:
                v.close()
    receipt = {
        "schema": "L_INSTALLED_SYNTHETIC_DEMONSTRATION_V1",
        "status": "PASS_OFFLINE_ONLY",
        "runtime_directory": str(runtime),
        "installed_application_version": importlib.metadata.version("quant-advisory-platform"),
        "installed_module_origin": str(swing_review.__file__),
        "installed_module_sha256": hashlib.sha256(Path(swing_review.__file__).read_bytes()).hexdigest(),
        "demonstrations": results,
        "actual_market_requests": 0,
        "authentic_market_or_authority_evidence": False,
        "source_qualified": False,
        "shadow_qualified": False,
        "economically_validated": False,
        "account": "ACCOUNT_UNKNOWN/ACCOUNT_VETO",
    }
    (ROOT / "L3_SYNTHETIC_OPERATOR_DEMONSTRATION.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({"status": receipt["status"], "artifacts": str(artifact), "actual_market_requests": 0}))


if __name__ == "__main__":
    main_demo()
