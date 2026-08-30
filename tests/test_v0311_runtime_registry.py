from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from btc_quant_agent.config import AppConfig, ExecutionConfig, load_config
from btc_quant_agent.data.quality import QualityReport
from btc_quant_agent.domain import (
    Candidate,
    Candle,
    Direction,
    PositionPlan,
    Regime,
    RuntimeStage,
    ScanResult,
    Setup,
    TimeframeFeatures,
)
from btc_quant_agent.engine import EngineMode, QuantEngine
from btc_quant_agent.execution.guard import ExecutionBlocked
from btc_quant_agent.execution.service import ExecutionService
from btc_quant_agent.multifactor import FactorAssessment
from btc_quant_agent.research_registry import RegistryError, ResearchRegistry
from btc_quant_agent.service import QuantService
from btc_quant_agent.storage import Repository


def _features() -> TimeframeFeatures:
    return TimeframeFeatures(
        close=110.0,
        ema_fast=108.0,
        ema_mid=105.0,
        ema_slow=100.0,
        ema_mid_slope=1.0,
        ema_slow_slope=0.5,
        atr=2.0,
        atr_percentile=0.5,
        adx=28.0,
        volume_z=1.0,
        rsi=55.0,
        roc=0.01,
        bb_width_percentile=0.5,
        cvd_slope=1.0,
        cvd_available=True,
        last_swing_high=115.0,
        previous_swing_high=112.0,
        last_swing_low=100.0,
        previous_swing_low=98.0,
        structure="HH_HL",
        bar_open_time_ms=0,
        bar_close_time_ms=899_999,
    )


def _candles() -> tuple[list[Candle], list[Candle], list[Candle]]:
    return (
        [Candle("BTCUSDT", "4h", 0, 14_399_999, 100, 111, 99, 110, 10)],
        [Candle("BTCUSDT", "1h", 0, 3_599_999, 100, 111, 99, 110, 10)],
        [Candle("BTCUSDT", "15m", 0, 899_999, 100, 111, 99, 110, 10)],
    )


def _candidate(setup: Setup) -> Candidate:
    return Candidate(
        Direction.LONG,
        setup,
        109.0,
        110.0,
        100.0,
        125.0,
        80,
        f"structure-{setup.value}",
        ("deterministic setup",),
        ("movement is not direction",),
    )


def _runtime_scan(setup: Setup) -> ScanResult:
    with (
        patch("btc_quant_agent.engine.validate_candles", return_value=QualityReport(True, ())),
        patch("btc_quant_agent.engine.build_features", return_value=_features()),
        patch("btc_quant_agent.engine.classify_regime", return_value=Regime.TREND_UP),
        patch("btc_quant_agent.engine.find_candidate", return_value=_candidate(setup)),
        patch(
            "btc_quant_agent.engine.assess_factors",
            side_effect=AssertionError("rejected direction factors must not run"),
        ),
        patch(
            "btc_quant_agent.engine.build_position_plan",
            side_effect=AssertionError("risk plan must not run"),
        ),
    ):
        return QuantEngine(AppConfig()).scan(*_candles(), None, 900_000)


def _write_registry_variant(tmp_path: Path, update: dict[str, object]) -> Path:
    raw = json.loads(Path("configs/research_registry.json").read_text(encoding="utf-8"))
    raw["components"][0].update(update)
    target = tmp_path / "registry.json"
    target.write_text(json.dumps(raw), encoding="utf-8")
    return target


def test_registry_rejected_component_cannot_be_actionable(tmp_path: Path) -> None:
    path = _write_registry_variant(tmp_path, {"runtime_eligibility": "SHADOW_ONLY"})
    with pytest.raises(RegistryError, match="REJECTED component is actionable"):
        ResearchRegistry.load(path)


def test_registry_supported_movement_is_analysis_only() -> None:
    registry = ResearchRegistry.load()
    for component_id in ("trend_pullback_opportunity", "breakout_retest_opportunity"):
        component = registry.get(component_id)
        assert component.research_status.value == "SUPPORTED_MOVEMENT"
        assert component.runtime_eligibility.value == "ANALYSIS_ONLY"
        assert not component.actionable


def test_registry_live_eligible_requires_validated_forward(tmp_path: Path) -> None:
    path = _write_registry_variant(
        tmp_path,
        {"research_status": "CANDIDATE", "runtime_eligibility": "LIVE_ELIGIBLE"},
    )
    with pytest.raises(RegistryError, match="requires VALIDATED_FORWARD"):
        ResearchRegistry.load(path)


def test_registry_unknown_component_fails_closed() -> None:
    with pytest.raises(RegistryError, match="unknown component fails closed"):
        ResearchRegistry.load().get("not-registered")


def test_registry_evidence_paths_exist() -> None:
    registry = ResearchRegistry.load()
    assert all(
        Path(path).is_file()
        for component in registry.components.values()
        for path in component.evidence_paths
    )


def test_registry_holdout_state_is_sealed() -> None:
    registry = ResearchRegistry.load()
    assert registry.final_holdout == "SEALED"
    assert not any(item.final_holdout_accessed for item in registry.components.values())


@pytest.mark.parametrize("setup", [Setup.TREND_PULLBACK, Setup.BREAKOUT_RETEST])
def test_runtime_legacy_tp_br_do_not_emit_actionable_long_short(setup: Setup) -> None:
    result = _runtime_scan(setup)
    assert result.action == "OPPORTUNITY_ONLY"
    assert result.runtime_stage == RuntimeStage.OPPORTUNITY_ONLY
    assert result.signal is None
    assert result.opportunity is not None
    assert result.opportunity.legacy_side_is_actionable is False


def test_opportunity_contains_no_entry_stop_take_profit_size() -> None:
    payload = _runtime_scan(Setup.TREND_PULLBACK).opportunity
    assert payload is not None
    prohibited = {
        "entry",
        "entry_low",
        "entry_high",
        "stop",
        "stop_loss",
        "take_profit",
        "position_size",
        "recommended_notional",
    }
    assert prohibited.isdisjoint(payload.as_dict())


def test_repeated_opportunity_scan_is_idempotent(tmp_path: Path) -> None:
    opportunity = _runtime_scan(Setup.TREND_PULLBACK).opportunity
    assert opportunity is not None
    repository = Repository(str(tmp_path / "opportunities.db"))
    assert repository.save_opportunity(opportunity)
    assert repository.save_opportunity(replace(opportunity, detected_at_ms=900_001)) is False


def test_runtime_registry_unavailable_fails_closed() -> None:
    with (
        patch("btc_quant_agent.engine.validate_candles", return_value=QualityReport(True, ())),
        patch("btc_quant_agent.engine.build_features", return_value=_features()),
        patch("btc_quant_agent.engine.classify_regime", return_value=Regime.TREND_UP),
        patch(
            "btc_quant_agent.engine.find_candidate",
            return_value=_candidate(Setup.TREND_PULLBACK),
        ),
        patch(
            "btc_quant_agent.engine.load_registry",
            side_effect=RegistryError("registry unavailable"),
        ),
    ):
        result = QuantEngine(AppConfig()).scan(*_candles(), None, 900_000)
    assert result.signal is None
    assert result.reason_code == "RESEARCH_REGISTRY_BLOCKED"
    assert result.registry_snapshot["status"] == "FAIL_CLOSED"


def test_legacy_research_mode_is_explicit_only() -> None:
    transform = lambda candidate, _features: candidate
    with pytest.raises(ValueError, match="explicit LEGACY_RESEARCH_V022"):
        QuantEngine(AppConfig(), research_candidate_transform=transform)
    assert (
        QuantEngine(
            AppConfig(),
            research_candidate_transform=transform,
            mode=EngineMode.LEGACY_RESEARCH_V022,
        ).mode
        == EngineMode.LEGACY_RESEARCH_V022
    )


def test_legacy_research_reproduces_frozen_v022_behavior() -> None:
    assessment = FactorAssessment(80.0, 4, {"trend_structure": 100.0}, ("confirmed",), ())
    plan = PositionPlan(109.5, 99.5, 125.0, 1.55, 1.8, 0.5, 5.0, 0.25, 0.005, 0.002, 0.0)
    with (
        patch("btc_quant_agent.engine.validate_candles", return_value=QualityReport(True, ())),
        patch("btc_quant_agent.engine.build_features", return_value=_features()),
        patch("btc_quant_agent.engine.classify_regime", return_value=Regime.TREND_UP),
        patch(
            "btc_quant_agent.engine.find_candidate",
            return_value=_candidate(Setup.TREND_PULLBACK),
        ),
        patch("btc_quant_agent.engine.assess_factors", return_value=assessment),
        patch("btc_quant_agent.engine.build_position_plan", return_value=plan),
        patch("btc_quant_agent.engine.confirmed_levels", return_value=([], [])),
    ):
        result = QuantEngine(
            load_config("configs/frozen/v0.2.2.toml"),
            mode=EngineMode.LEGACY_RESEARCH_V022,
        ).scan(*_candles(), None, 900_000)
    assert result.action == "LONG"
    assert result.reason_code == "CONFIRMED"
    assert result.signal is not None
    assert result.signal.strategy_version == "0.2.2"


def test_quant_service_always_uses_runtime_gated_mode(tmp_path: Path) -> None:
    repository = Repository(str(tmp_path / "runtime.db"))
    client = MagicMock()
    client.server_time_ms.return_value = 900_000
    client.klines.side_effect = [_candles()[2], _candles()[1], _candles()[0]]
    client.derivatives.return_value = SimpleNamespace(observed_at_ms=900_000)
    engine = MagicMock()
    engine.invalidation_reason.return_value = None
    engine.scan.return_value = ScanResult("WAIT", "OK", "no setup")
    with patch("btc_quant_agent.service.QuantEngine", return_value=engine) as engine_class:
        service = QuantService(AppConfig(), repository, client, MagicMock())
        service.scan(notify=False)
    assert engine_class.call_args.kwargs["mode"] == EngineMode.RUNTIME_GATED


def test_execution_plan_rejects_registry_blocked_legacy_signal(tmp_path: Path) -> None:
    repository = Repository(str(tmp_path / "execution.db"))
    service = ExecutionService(AppConfig(), repository, MagicMock())
    with pytest.raises(ExecutionBlocked, match="RESEARCH_REGISTRY_NOT_ACTIONABLE"):
        service.build_entry_plan("legacy-signal", now_ms=1)


def test_execution_status_reports_no_qualified_direction_engine(tmp_path: Path) -> None:
    repository = Repository(str(tmp_path / "execution.db"))
    status = ExecutionService(
        AppConfig(execution=ExecutionConfig(mode="paper")), repository, MagicMock()
    ).status()
    assert status["qualified_direction_engine_count"] == 0
    assert status["order_submission_enabled"] is False
    assert status["runtime_actionability"] == "OPPORTUNITY_ONLY"


def test_default_execution_and_holdout_safety() -> None:
    config = load_config()
    assert config.execution.mode == "disabled"
    assert config.execution.auto_execute is False
    assert config.execution.allow_live is False
    assert ResearchRegistry.load().final_holdout == "SEALED"
