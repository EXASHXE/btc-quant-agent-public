import json
from pathlib import Path

import pytest

from btc_quant_agent.platform.cli import main
from btc_quant_agent.platform.bridge.config import BridgeConfig


def test_readiness_is_explicitly_blocked_and_has_activation_requirements(capsys):
    main(["bridge", "readiness", "--config", "configs/bridge/offline.yaml"])
    r = json.loads(capsys.readouterr().out)
    assert r["real_source_activation"] == "BLOCKED" and r["network_calls_performed"] == 0
    assert all(row["authorization_needed"] and row["unverified"] for row in r["matrix"])


def test_cli_end_to_end_replay(config, tmp_path, capsys):
    main(["bridge", "replay", "--config", "configs/bridge/offline.yaml", "--output", str(tmp_path)])
    r = json.loads(capsys.readouterr().out)
    assert r["snapshots"] == 4 and r["real_activation"] == "BLOCKED"
    report = json.loads((Path(r["path"]) / "replay.json").read_text())
    assert report["exposure"] == "SYNTHETIC" and len(report["results"][0]["strategy_evaluations"]) == 9
    assert (Path(r["path"]) / "report.html").exists()


def test_blocked_live_mode_cannot_be_enabled_with_config_or_raw_flags(config, tmp_path, capsys):
    import yaml

    path = tmp_path / "blocked.yaml"
    raw = config.model_dump(mode="json")
    raw["mode"] = "blocked_live"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(SystemExit) as exc:
        main(["bridge", "scan", "--config", str(path), "--output", str(tmp_path / "never_created")])
    assert exc.value.code == 2 and "SEPARATE_ACCESS_AUTHORIZATION" in capsys.readouterr().err
    assert not (tmp_path / "never_created").exists()
    raw["mode"] = "live"
    raw["allow_live"] = True
    with pytest.raises(ValueError):
        BridgeConfig.model_validate(raw)
