"""Deletion guards: engineering surface changes must not create new authority."""

import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from btc_quant_agent import cli
from btc_quant_agent.config import AppConfig

ROOT = Path(__file__).resolve().parents[1]
REMOVED_RESEARCH = (
    "breakout_edge", "causal_entry", "cross_asset_breadth", "directional_architecture",
    "funding_crowding", "funding_stability", "funnel", "geometry", "range_mean_reversion",
    "spot_perp_flow",
)


def _catalog():
    spec = importlib.util.spec_from_file_location("r01_catalog", ROOT / "tools/catalog_surfaces.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("command", ["legacy-backtest", "legacy-research", "legacy-replay"])
def test_removed_commands_fail_before_operational_state(command, monkeypatch):
    forbidden = Mock(side_effect=AssertionError("operational state constructed"))
    monkeypatch.setattr(cli, "_service", forbidden)
    with pytest.raises(SystemExit) as exc:
        cli.main([command, "/nonexistent/old.csv"])
    assert exc.value.code == 2
    forbidden.assert_not_called()


@pytest.mark.parametrize("command", ["backtest", "research", "replay"])
def test_formal_load_failure_cannot_fall_back(command, tmp_path, monkeypatch, capsys):
    forbidden = Mock(side_effect=AssertionError("legacy/runtime fallback"))
    monkeypatch.setattr(cli, "_service", forbidden)
    monkeypatch.setattr("btc_quant_agent.backtest.BacktestEngine.run", forbidden)
    output = tmp_path / "output"
    assert cli.main([command, "--job", str(tmp_path / "missing.json"),
                     "--output", str(output)]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["classification"] == "NOT_TESTABLE_FOR_NEW_PROMOTION"
    assert not output.exists()
    forbidden.assert_not_called()


def test_removed_modules_are_absent_from_package_and_active_imports():
    removed = {f"btc_quant_agent.{name}_research" for name in REMOVED_RESEARCH}
    removed.add("btc_quant_agent.symbolic_alpha")
    for name in removed:
        assert importlib.util.find_spec(name) is None
    catalog = _catalog()
    for directory in (ROOT / "src", ROOT / "tools", ROOT / "skill-template/scripts"):
        for source in directory.rglob("*.py"):
            for imported in catalog.find_imports_in_file(source):
                assert not any(imported == name or imported.startswith(name + ".")
                               for name in removed), (source, imported)
    assert not hasattr(cli, "BacktestEngine")
    assert not hasattr(cli, "run_full_suite")


def test_catalog_reports_actual_paths_and_parser_without_service(monkeypatch):
    forbidden = Mock(side_effect=AssertionError("runtime service called"))
    monkeypatch.setattr(cli, "_service", forbidden)
    catalog = _catalog().generate_catalog()
    assert catalog["dangling_internal_imports"] == []
    assert catalog["classification_buckets"] == [
        "KEEP_CURRENT", "DELETE_R01", "DEFER_PROTECTED", "DEFER_UNCERTAIN",
    ]
    assert {"backtest", "research", "replay"} <= set(catalog["cli_entrypoints"])
    assert not any(leaf.startswith("legacy-") for leaf in catalog["cli_entrypoints"])
    for item in catalog["surface_inventory"]:
        assert (ROOT / item["path"]).is_file()
    assert not (ROOT / "prompts").exists()
    assert not (ROOT / "reviews").exists()
    forbidden.assert_not_called()


def test_catalog_default_stdout_never_recreates_reviews(monkeypatch, capsys):
    module = _catalog()
    monkeypatch.setattr("sys.argv", ["catalog_surfaces.py"])
    module.main()
    assert json.loads(capsys.readouterr().out)["schema_version"] == "2.0.0"
    assert not (ROOT / "reviews").exists()


def test_catalog_refuses_agent_documents_on_code_branch(monkeypatch):
    module = _catalog()
    monkeypatch.setattr("sys.argv", ["catalog_surfaces.py", "--output",
                                   str(ROOT / "reviews/forbidden.json")])
    with pytest.raises(SystemExit) as exc:
        module.main()
    assert exc.value.code == 2
    assert not (ROOT / "reviews").exists()


def test_frozen_forward_configuration_references_exist():
    for registry in (ROOT / "configs/forward").glob("*.json"):
        def walk(value, registry=registry):
            if isinstance(value, dict):
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
            elif isinstance(value, str) and value.startswith("configs/"):
                assert (ROOT / value).is_file(), (registry, value)
        walk(json.loads(registry.read_text()))


def test_execution_and_retained_holdout_guard_defaults_are_unchanged():
    config = AppConfig()
    assert config.execution.mode == "disabled"
    assert not config.execution.auto_execute
    assert not config.execution.allow_live
    assert (ROOT / "configs/research/v0.3.2_mechanism_protocol.json").is_file()
    assert (ROOT / "configs/research/v0.3.22_microstructure_h39_protocol.json").is_file()


def test_runtime_registry_evidence_and_rejected_family_gates_survive_deletion():
    from btc_quant_agent.research_registry import ResearchRegistry

    registry = ResearchRegistry.load(ROOT / "configs/research_registry.json")
    registry.validate()
    payload = json.loads((ROOT / "configs/research_registry.json").read_text())
    assert payload["final_holdout"] == "SEALED"
    assert payload["runtime_maximum_stage"] == "OPPORTUNITY_ONLY"
    paths = {path for component in payload["components"] for path in component["evidence_paths"]}
    assert len(paths) == 9
    assert all((ROOT / path).is_file() for path in paths)
    assert set(_catalog().generate_catalog()["protected_evidence_paths"]) == paths
