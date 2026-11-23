"""Family A tests: packaging, dependencies, H1 reuse, offline CLI checks, and Hermes interface verification."""

from __future__ import annotations

import json
import subprocess
import sys
from importlib.metadata import entry_points, version
from pathlib import Path

from quant_hermes_feishu_h1 import outbox as h1_outbox
from quant_hermes_feishu_h1 import renderer as h1_renderer

from quant_hermes_feishu_h2b import (
    ACCEPTED_H1_VERSION,
    H2B_VERSION,
    QUANT_H2B_TOOLSET,
    V1_MODEL_READONLY_TOOLS,
)
from quant_hermes_feishu_h2b.activation_gate import PRODUCTION_TRUST_ROOT
from quant_hermes_feishu_h2b.cli import verify_hermes_interfaces
from quant_hermes_feishu_h2b.outbound_sender import HermesSingleSenderService

H2B_ROOT = Path(__file__).resolve().parents[1]


def test_a1_package_version_entrypoint_and_pinned_manifest():
    assert H2B_VERSION == "0.8.0b2"
    assert ACCEPTED_H1_VERSION == "0.8.0.post1"
    assert version("quant-hermes-feishu-h1") == "0.8.0.post1"
    assert QUANT_H2B_TOOLSET == "quant_v080_h2b_readonly"
    assert len(V1_MODEL_READONLY_TOOLS) == 6
    assert "request_reprice" not in V1_MODEL_READONLY_TOOLS

    manifest = json.loads((H2B_ROOT / "PINNED_DEPENDENCIES.json").read_text(encoding="utf-8"))
    assert manifest["release"]["package"] == "quant-hermes-feishu-h2b"
    assert manifest["release"]["version"] == "0.8.0b2"
    assert manifest["hermes_runtime"]["version"] == "0.16.0"
    assert manifest["hermes_runtime"]["commit"] == "c2fa302e933aafc5f995696709a4179f54206c26"

    eps = entry_points().select(group="hermes_agent.plugins")
    matching = [e for e in eps if e.name == "quant-v080-h2b-readonly"]
    if matching:
        assert matching[0].value == "quant_hermes_feishu_h2b.hermes_plugin"


def test_a2_reuses_h1_components_without_forking_and_default_deny_inactive():
    # HermesSingleSenderService wraps H1 DeterministicOutbox directly (never a forked second outbox).
    assert HermesSingleSenderService.__init__.__globals__["DeterministicOutbox"] is h1_outbox.DeterministicOutbox
    assert HermesSingleSenderService.__init__.__globals__["compute_outbox_event_id"] is not None
    assert h1_outbox.render_signal_alert is h1_renderer.render_signal_alert

    # Default production trust root is strictly inactive (default-deny).
    assert PRODUCTION_TRUST_ROOT.live_enabled is False
    assert PRODUCTION_TRUST_ROOT.allowed_capabilities == frozenset()
    assert PRODUCTION_TRUST_ROOT.app_id is None
    assert PRODUCTION_TRUST_ROOT.tenant_key is None
    assert PRODUCTION_TRUST_ROOT.owner_open_id is None

    # Offline review templates must also remain explicitly NOT_AUTHORIZED.
    tpl = json.loads((H2B_ROOT / "H2B_ACTIVATION_TEMPLATE.json").read_text(encoding="utf-8"))
    prop = json.loads((H2B_ROOT / "H2B_PROPOSED_OWNER_SCOPE.json").read_text(encoding="utf-8"))
    assert tpl["status"] == "NOT_AUTHORIZED"
    assert tpl["live_enabled"] is False
    assert prop["status"] == "NOT_AUTHORIZED"


def test_a3_hermes_interface_verification_command_matches_local_repo():
    info = verify_hermes_interfaces()
    assert info["hermes_version"] == "0.16.0"
    assert info["hermes_commit"] == "c2fa302e933aafc5f995696709a4179f54206c26"
    assert info["h2b_readonly_tools"] == list(V1_MODEL_READONLY_TOOLS)

    proc = subprocess.run(
        [sys.executable, "-m", "quant_hermes_feishu_h2b", "verify-hermes-interface"],
        capture_output=True,
        text=True,
        check=True,
    )
    parsed = json.loads(proc.stdout)
    assert parsed["hermes_commit"] == "c2fa302e933aafc5f995696709a4179f54206c26"
