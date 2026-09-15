"""R04 guards for legacy-diagnostic labeling and authority separation."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from btc_quant_agent import cli
from btc_quant_agent.config import AppConfig
from btc_quant_agent.mechanism_research import write_v032_artifacts
from btc_quant_agent.research import (
    mark_legacy_diagnostic,
    research_summary,
    write_research_artifacts,
)
from btc_quant_agent.research_contract.registry import ResearchContractRegistry
from btc_quant_agent.research_registry import ResearchRegistry


ROOT = Path(__file__).resolve().parents[1]
MARKER = {
    "classification": "LEGACY_DIAGNOSTIC_ONLY",
    "promotion_eligibility": "NOT_TESTABLE_FOR_NEW_PROMOTION",
    "can_promote": False,
}


class _FakeTable:
    @staticmethod
    def from_pylist(_rows):
        return object()


class _FakeParquet:
    @staticmethod
    def write_table(_table, path):
        Path(path).write_bytes(b"diagnostic-test-parquet")


def _fake_optional_module(name: str):
    if name == "pyarrow":
        return SimpleNamespace(Table=_FakeTable)
    if name == "pyarrow.parquet":
        return _FakeParquet
    raise ImportError(name)


def _assert_marker(payload: dict[str, object]) -> None:
    assert {key: payload[key] for key in MARKER} == MARKER


def test_legacy_research_results_and_persisted_report_are_non_promoting(
    tmp_path: Path, monkeypatch,
) -> None:
    _assert_marker(research_summary([]))
    assert mark_legacy_diagnostic({"classification": "forged", "can_promote": True}) == MARKER

    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"checksum_sha256":"fixture"}', encoding="utf-8")
    suite = {
        "baseline": {"overall": {"trades": 0, "expectancy_r": None,
                                    "profit_factor": None, "max_drawdown_r": 0.0}},
        "outcomes": [],
        "decisions": [],
    }
    monkeypatch.setattr("btc_quant_agent.research.importlib.import_module", _fake_optional_module)
    output = tmp_path / "research"
    write_research_artifacts(
        output, suite, AppConfig(), data_manifest_path=manifest, seed=1,
    )
    _assert_marker(json.loads((output / "research_report.json").read_text()))
    markdown = (output / "research_report.md").read_text()
    assert "LEGACY_DIAGNOSTIC_ONLY" in markdown
    assert "NOT_TESTABLE_FOR_NEW_PROMOTION" in markdown


def test_legacy_mechanism_json_artifacts_are_all_non_promoting(
    tmp_path: Path, monkeypatch,
) -> None:
    result = {
        "control_summary": {},
        "rr_component_summary": {},
        "required_target_distance": {},
        "funding_stress_diagnostic": {},
        "stop_buffer_diagnostic": {},
        "e1_tp_target_results": {},
        "e1_barrier_diagnostic": {},
        "e2_score_dedup_results": {"distribution": {}},
        "e3_participation_dedup_results": {},
        "mechanism_comparison": {},
        "rr_rows": [],
        "e1_rows": [],
        "e1_trade_rows": [],
    }
    protocol = tmp_path / "protocol.json"
    protocol.write_text("{}", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"checksum_sha256":"fixture"}', encoding="utf-8")
    monkeypatch.setattr(
        "btc_quant_agent.mechanism_research.importlib.import_module", _fake_optional_module,
    )
    output = write_v032_artifacts(
        tmp_path / "mechanism", result, AppConfig(), protocol, manifest,
    )
    for path in output.glob("*.json"):
        if path.name in {"protocol.json", "data_manifest.json"}:
            continue
        _assert_marker(json.loads(path.read_text()))


def test_operational_registry_has_no_formal_decision_bridge(monkeypatch, capsys) -> None:
    forbidden = Mock(side_effect=AssertionError("formal registry invoked"))
    monkeypatch.setattr(ResearchContractRegistry, "record_economic_qualification", forbidden)
    registry = ResearchRegistry.load(ROOT / "configs/research_registry.json")
    registry.validate(ROOT)
    registry.status()
    registry.get("active_direction_engine")
    monkeypatch.setattr(cli.ResearchRegistry, "load", lambda _path: registry)
    assert cli.main(["research-registry", "status"]) == 0
    capsys.readouterr()
    forbidden.assert_not_called()

    spec = importlib.util.spec_from_file_location("catalog", ROOT / "tools/catalog_surfaces.py")
    assert spec is not None and spec.loader is not None
    catalog = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(catalog)
    imports = catalog.find_imports_in_file(ROOT / "src/btc_quant_agent/research_registry.py")
    assert not any(name.startswith("btc_quant_agent.research_contract") for name in imports)

