"""End-to-end demo, telemetry metrics, fail-closed live gate, and preservation verification."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from quant_hermes_feishu_h1.cli import (
    LIVE_CAPABILITY_ERROR,
    LIVE_CAPABILITY_EXIT_CODE,
    run_offline_demo,
)
from quant_hermes_feishu_h1.cli import main as cli_main
from quant_hermes_feishu_h1.contract import SYNTHETIC_WARNING_TOKEN

H1_ROOT = Path(__file__).resolve().parents[1]
WORKSPACES = H1_ROOT.parent
B5_JOURNAL = WORKSPACES / "lt-v080-personal-mvp-live-public-b5-01/evidence/replay-input/journal.sqlite"
B2_DEMO = WORKSPACES / "lt-v080-sol62-personal-mvp-market-decision-b2-01/evidence/demo"


def test_offline_demo_and_metrics_evidence(tmp_path):
    out = tmp_path / "demo_out"
    res = run_offline_demo(
        journal_paths=[
            ("b5_pullback_long", B5_JOURNAL),
            ("b2_pullback_short", B2_DEMO / "pullback-short/decision.sqlite"),
            ("b2_early_long", B2_DEMO / "early-long/decision.sqlite"),
            ("b2_early_short", B2_DEMO / "early-short/decision.sqlite"),
        ],
        output_dir=out,
    )
    assert (out / "summary.json").exists()
    assert (out / "rendered_cards.json").exists()
    assert (out / "conversations.json").exists()
    assert (out / "model_mock_failures.json").exists()
    assert (out / "telemetry_report.json").exists()
    assert (out / "facade_audit.jsonl").exists()

    metrics = res["metrics"]
    assert metrics["evidence_class"] == "SYNTHETIC_QA_ONLY"
    assert metrics["claims"]["real_feishu_delivery_measured"] is False
    assert metrics["claims"]["real_human_response_delay_measured"] is False
    assert metrics["claims"]["live_market_alpha_or_pnl_proven"] is False
    assert metrics["counters"]["alerts_deduplicated"] == 4
    assert metrics["counters"]["explanation_fallbacks"] == 4
    assert metrics["counters"]["inbound_commands_ok"] == 7
    assert metrics["counters"]["inbound_commands_rejected"] == 0
    assert metrics["synthetic_actionability"]["denominator_episodes"] == 4
    assert res["request_reprice_disabled"]["error"]["code"] == "REPRICE_NOT_AUTHORIZED"

    cards_txt = (out / "rendered_cards.json").read_text(encoding="utf-8")
    assert SYNTHETIC_WARNING_TOKEN in cards_txt


def test_live_capability_gates_remain_fail_closed():
    for target in ("feishu-live", "binance-live", "model-oauth"):
        rc = cli_main(["check-live-gate", "--target", target])
        assert rc == LIVE_CAPABILITY_EXIT_CODE

    proc = subprocess.run(
        [sys.executable, "-m", "quant_hermes_feishu_h1", "check-live-gate", "--target", "feishu-live"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == LIVE_CAPABILITY_EXIT_CODE
    assert proc.stdout.strip() == LIVE_CAPABILITY_ERROR


def test_preservation_script_passes():
    preserve_py = H1_ROOT / "tools/preserve.py"
    proc = subprocess.run([sys.executable, str(preserve_py)], capture_output=True, text=True, check=True)
    assert "PASS v0.8.0" in proc.stdout
    assert "PASS docs/engineering" in proc.stdout
    assert "V080_QUANT_AGENT_CONTRACT_V1_20261120.md" in proc.stdout
    assert "lt-v080-gemini-neon-hermes-quant-feishu-h1-01 (57 sealed files)" in proc.stdout
    assert "lt-v080-astra-pi-quant-agent-architecture-p1-01 (7 sealed files)" in proc.stdout
    assert "Program J (323 files)" in proc.stdout
