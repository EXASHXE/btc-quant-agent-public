import json

import pytest
from pydantic import ValidationError

from btc_quant_agent.decision.models import AnalysisResultV1, CasePackageV1


def sample_case(**overrides):
    values = {
        "case_id": "case-1", "created_at_ms": 1000, "observed_at_ms": 1000, "expires_at_ms": 61000,
        "symbol": "BTCUSDT", "trigger": "MARKET_WATCH", "strategy": "TREND_PULLBACK",
        "strategy_version": "TACTICAL_POLICY_R2_B0", "direction": "LONG",
        "evidence_id": "a" * 64, "snapshot_hash": "snapshot-1", "signal_identity": "signal-1",
        "price": 100.0, "entry_low": 99.0, "entry_high": 101.0, "stop_loss": 95.0,
        "take_profit_1": 110.0, "take_profit_2": 120.0, "atr": 2.0,
        "spread_bps": 1.0, "liquidity_usdt": 1000000.0, "data_quality": "OK",
    }
    values.update(overrides)
    return CasePackageV1.build(**values)


def sample_analysis(case, **overrides):
    values = {
        "backend": "responses", "model": "configured-model", "provider_request_id": "request-1",
        "case_id": case.case_id, "case_hash": case.case_hash, "action": "OPEN_LONG", "confidence": 0.9,
        "entry_quality": "GOOD", "thesis_strength": 0.8, "supporting_factors": ("TREND",),
        "risk_factors": (), "invalidation_factors": ("STOP",), "risk_modifier": "STANDARD",
        "requires_secondary_review": False, "requires_manual_review": False,
        "strategy_data_disagreement": False, "narrative": "Review only",
    }
    values.update(overrides)
    return AnalysisResultV1(**values)


def test_case_hash_tamper_and_missing_hash_rejected():
    case = sample_case()
    raw = json.loads(case.canonical_json())
    raw["price"] = 999
    with pytest.raises(ValidationError):
        CasePackageV1.model_validate_json(json.dumps(raw))
    raw.pop("case_hash")
    with pytest.raises(ValidationError):
        CasePackageV1.model_validate_json(json.dumps(raw))
    assert CasePackageV1.model_validate_json(case.canonical_json()) == case
    assert sample_case().case_hash == case.case_hash


def test_case_deep_immutable_and_secrets_excluded():
    case = sample_case()
    with pytest.raises(ValidationError):
        case.price = 999
    with pytest.raises(ValidationError):
        sample_case(api_key="secret")
    assert "api_key" not in case.canonical_json()


@pytest.mark.parametrize("field", ["quantity", "leverage", "notional", "order_type", "price"])
def test_llm_executable_fields_rejected(field):
    case = sample_case()
    with pytest.raises(ValidationError):
        sample_analysis(case, **{field: 2})


def test_live_config_has_no_secret_fields(monkeypatch):
    from dataclasses import asdict

    from btc_quant_agent.config import LiveV1Config
    monkeypatch.setenv("BINANCE_API_KEY", "exchange-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "provider-secret")
    monkeypatch.setenv("FEISHU_APP_SECRET", "app-secret")
    config = LiveV1Config.from_env()
    assert config.responses_model == ""
    assert "secret" not in json.dumps(asdict(config))
    assert "secret" not in sample_case().canonical_json()
