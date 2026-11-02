import json
import subprocess
import sys
from pathlib import Path

import pytest

from btc_quant_agent.platform.cli import main
from btc_quant_agent.platform.demos import demonstrate
from btc_quant_agent.platform.ui import page


@pytest.mark.parametrize(
    "args",
    [
        ["factors", "list"],
        ["factors", "inspect", "RSI"],
        ["strategies", "list"],
        ["strategies", "inspect", "trend_pullback"],
        ["configs", "validate", "configs/trend_breakout.yaml"],
        ["models", "list"],
    ],
)
def test_cli_inspection_has_json_contract(args, capsys):
    main(args)
    assert json.loads(capsys.readouterr().out) is not None


def test_restart_identity_in_separate_processes(tmp_path):
    script = """import sys,json
from btc_quant_agent.platform.position_management import AdvisoryStore
s=AdvisoryStore(sys.argv[1]);i=s.commit_decision({"fixture":"restart","action":"WATCH"},100,100)
e=s.prepare(i,"BTCUSDT",100);calls=[]
status=s.dispatch(e,lambda payload:calls.append(payload),101,notify=sys.argv[2]=="send")
print(json.dumps({"event":e,"status":status,"calls":len(calls)}))
"""
    args = [sys.executable, "-c", script, str(tmp_path / "store.sqlite")]
    results = [
        json.loads(subprocess.check_output(args + [mode], text=True)) for mode in ("preview", "send", "send")
    ]
    assert len({r["event"] for r in results}) == 1
    assert [r["calls"] for r in results] == [0, 1, 0]


def test_complete_nine_demonstrations(tmp_path):
    result = demonstrate(tmp_path)
    assert result["scenarios_completed"] == list(map(str, range(1, 10)))
    artifact = json.loads(Path(result["artifact"]).read_text())
    assert len(artifact["8"]["rows"]) == 3
    assert artifact["9"]["stop_gap"]["execution_status"] == "EXECUTION_UNKNOWN"
    assert artifact["6"]["family"] == "logistic" and artifact["7"]["family"] == "transformer"


def test_dashboard_has_strategy_factor_risk_and_report_controls():
    markup = page()
    for name in ("strategies", "factors", "weights", "risk", "slip", "lookback", "models"):
        assert f'id="{name}"' in markup
    assert "SYNTHETIC" in markup and "X-Quant-Local" in markup
