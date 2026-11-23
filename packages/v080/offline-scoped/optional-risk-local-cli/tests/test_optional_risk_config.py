"""Tests for versioned optional account-risk YAML/JSON configuration and negative validation."""

from __future__ import annotations

import copy
import json
import os
from decimal import Decimal
from pathlib import Path

import pytest

from quant_optional_risk_cli.config import (
    default_disabled_config,
    load_config_file,
    validate_config_mapping,
)
from quant_optional_risk_cli.models import (
    CONFIG_SCHEMA_VERSION,
    POLICY_REFERENCE,
    OptionalRiskBoundaryError,
    OptionalRiskConfigError,
    canonical_encode,
)
from quant_optional_risk_cli.parser import parse_strict_yaml_mapping

WORKROOT = Path(os.environ["OPT_RISK_WORKROOT"])
DEFAULT_YAML = WORKROOT / "configs/default_disabled_account_risk.yaml"
OPT_IN_YAML = WORKROOT / "configs/synthetic_opt_in_fixture_example.yaml"
SCHEMA_JSON = WORKROOT / "OPTIONAL_ACCOUNT_RISK_SCHEMA.json"


def _base_raw(*, enabled: bool = False, source: str | None = None) -> dict[str, object]:
    src = source or (
        "SYNTHETIC_OPT_IN_QA_FIXTURE_ONLY" if enabled else "OWNER_LOCAL_DISABLED_DEFAULT"
    )
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "config_version": "1.0.0",
        "policy_reference": POLICY_REFERENCE,
        "review_status": "PROPOSED_NOT_PRODUCTION_POLICY",
        "source": src,
        "layer2_private_user_data": "DISABLED",
        "layer3_trade_execution": "DISABLED",
        "account_risk": {
            "enabled": enabled,
            "per_trade_default": "0.02",
            "per_trade_max": "0.03",
            "selected_per_trade_risk": "0.02",
            "explicit_above_default_risk_selected": False,
            "btc_eth_default_leverage": "10",
            "btc_eth_normal_band": ["10", "15"],
            "btc_eth_exceptional_max": "20",
            "sol_other_default_leverage": "10",
            "sol_other_max_leverage": "15",
            "selected_leverage_by_symbol": {
                "BTCUSDT": "10",
                "ETHUSDT": "10",
                "SOLUSDT": "10",
            },
            "explicit_exceptional_leverage_selected": False,
            "daily_stop": "0.06",
            "daily_halt": "0.08",
        },
        "provisional_rules": {
            "day_boundary": {"convention": "00:00_UTC_TO_NEXT_00:00_UTC", "status": "PROPOSED"},
            "cashflow_adjustment": {"formula": "max(0,(E0-(Et-F))/E0)", "status": "PROPOSED"},
            "portfolio_exposure_aggregation": {
                "rule": "OPEN_POSITIONS_INCREMENTAL_DOWNSIDE_PLUS_CANDIDATE_UNDER_6PCT_HEADROOM",
                "status": "PROPOSED",
            },
        },
    }


def test_default_disabled_config_and_yaml_parity() -> None:
    builtin = default_disabled_config()
    loaded = load_config_file(DEFAULT_YAML)
    schema = json.loads(SCHEMA_JSON.read_text(encoding="utf-8"))

    assert builtin.account_risk.enabled is False
    assert builtin.layer2_private_user_data == "DISABLED"
    assert builtin.layer3_trade_execution == "DISABLED"
    assert builtin.review_status == "PROPOSED_NOT_PRODUCTION_POLICY"
    assert builtin.config_sha256 == loaded.config_sha256
    assert canonical_encode(builtin.canonical_payload()) == canonical_encode(
        loaded.canonical_payload()
    )
    assert loaded.account_risk.per_trade_default == Decimal("0.02")
    assert loaded.account_risk.per_trade_max == Decimal("0.03")
    assert loaded.account_risk.btc_eth_default_leverage == Decimal("10")
    assert loaded.account_risk.btc_eth_normal_band == (Decimal("10"), Decimal("15"))
    assert loaded.account_risk.btc_eth_exceptional_max == Decimal("20")
    assert loaded.account_risk.sol_other_default_leverage == Decimal("10")
    assert loaded.account_risk.sol_other_max_leverage == Decimal("15")
    assert loaded.account_risk.daily_stop == Decimal("0.06")
    assert loaded.account_risk.daily_halt == Decimal("0.08")
    assert schema["properties"]["layer2_private_user_data"]["const"] == "DISABLED"
    assert schema["properties"]["layer3_trade_execution"]["const"] == "DISABLED"


def test_manual_opt_in_vs_no_auto_enable_after_restart() -> None:
    with pytest.raises(OptionalRiskConfigError, match="AUTO_ENABLE_AFTER_RESTART_FORBIDDEN"):
        load_config_file(OPT_IN_YAML)

    opted_in = load_config_file(OPT_IN_YAML, allow_enabled_opt_in=True)
    assert opted_in.account_risk.enabled is True
    assert opted_in.source == "SYNTHETIC_OPT_IN_QA_FIXTURE_ONLY"

    raw_non_synthetic = _base_raw(enabled=True, source="OWNER_LOCAL_DISABLED_DEFAULT")
    with pytest.raises(OptionalRiskConfigError, match="ENABLED_CONFIG_REQUIRES_SYNTHETIC_SOURCE"):
        validate_config_mapping(raw_non_synthetic, allow_enabled_opt_in=True)


def test_reject_bool_float_percentage_negative_and_malformed_numbers() -> None:
    bad_values: list[tuple[object, str]] = [
        (True, "BOOLEAN_IN_NUMERIC_FIELD"),
        (False, "BOOLEAN_IN_NUMERIC_FIELD"),
        (0.02, "BINARY_FLOAT_FORBIDDEN"),
        ("2%", "PERCENT_OR_EXPONENT_FORBIDDEN"),
        ("2e-2", "PERCENT_OR_EXPONENT_FORBIDDEN"),
        ("-0.02", "NON_POSITIVE_DECIMAL_FORBIDDEN"),
        ("0", "NON_POSITIVE_DECIMAL_FORBIDDEN"),
        (" 0.02", "MALFORMED_DECIMAL_STRING"),
        ("not-a-number", "MALFORMED_DECIMAL_STRING"),
        ("1..2", "MALFORMED_DECIMAL_STRING"),
    ]
    for bad, code in bad_values:
        raw = _base_raw()
        ar = raw["account_risk"]
        assert isinstance(ar, dict)
        ar["per_trade_default"] = bad
        with pytest.raises(OptionalRiskConfigError, match=code):
            validate_config_mapping(raw)

    for yaml_bad, code in (
        ("enabled: false\nper_trade_default: 0.02\n", "BINARY_FLOAT_FORBIDDEN"),
        ("\taccount_risk: {}\n", "YAML_TABS_FORBIDDEN"),
        ('a: &anchor "1"\nb: *anchor\n', "UNSUPPORTED_YAML_CONSTRUCT"),
        ('a: "1"\na: "2"\n', "DUPLICATE_CONFIG_KEY"),
    ):
        with pytest.raises(OptionalRiskConfigError, match=code):
            parse_strict_yaml_mapping(yaml_bad)


def test_per_trade_risk_and_leverage_bounds_and_symbol_universe() -> None:
    raw_3pct_implicit = _base_raw()
    raw_3pct_implicit["account_risk"]["selected_per_trade_risk"] = "0.03"  # type: ignore[index]
    with pytest.raises(
        OptionalRiskConfigError, match="ABOVE_DEFAULT_RISK_REQUIRES_EXPLICIT_SELECTION"
    ):
        validate_config_mapping(raw_3pct_implicit)

    raw_3pct_explicit = copy.deepcopy(raw_3pct_implicit)
    raw_3pct_explicit["account_risk"]["explicit_above_default_risk_selected"] = True  # type: ignore[index]
    cfg_3pct = validate_config_mapping(raw_3pct_explicit)
    assert cfg_3pct.account_risk.selected_per_trade_risk == Decimal("0.03")

    raw_over_3pct = _base_raw()
    raw_over_3pct["account_risk"]["selected_per_trade_risk"] = "0.0301"  # type: ignore[index]
    raw_over_3pct["account_risk"]["explicit_above_default_risk_selected"] = True  # type: ignore[index]
    with pytest.raises(OptionalRiskConfigError, match="SELECTED_RISK_EXCEEDS_CAP"):
        validate_config_mapping(raw_over_3pct)

    raw_btc_18_no_flag = _base_raw()
    raw_btc_18_no_flag["account_risk"]["selected_leverage_by_symbol"]["BTCUSDT"] = "18"  # type: ignore[index]
    with pytest.raises(
        OptionalRiskConfigError, match="EXCEPTIONAL_LEVERAGE_REQUIRES_EXPLICIT_SELECTION"
    ):
        validate_config_mapping(raw_btc_18_no_flag)

    raw_btc_20_ok = copy.deepcopy(raw_btc_18_no_flag)
    raw_btc_20_ok["account_risk"]["selected_leverage_by_symbol"]["BTCUSDT"] = "20"  # type: ignore[index]
    raw_btc_20_ok["account_risk"]["explicit_exceptional_leverage_selected"] = True  # type: ignore[index]
    cfg_20 = validate_config_mapping(raw_btc_20_ok)
    assert cfg_20.account_risk.leverage_for("BTCUSDT") == Decimal("20")

    raw_btc_21 = copy.deepcopy(raw_btc_20_ok)
    raw_btc_21["account_risk"]["selected_leverage_by_symbol"]["BTCUSDT"] = "21"  # type: ignore[index]
    with pytest.raises(OptionalRiskConfigError, match="LEVERAGE_EXCEEDS_CEILING"):
        validate_config_mapping(raw_btc_21)

    raw_sol_16 = _base_raw()
    raw_sol_16["account_risk"]["selected_leverage_by_symbol"]["SOLUSDT"] = "16"  # type: ignore[index]
    with pytest.raises(OptionalRiskConfigError, match="LEVERAGE_EXCEEDS_CEILING"):
        validate_config_mapping(raw_sol_16)

    raw_doge = _base_raw()
    raw_doge["account_risk"]["selected_leverage_by_symbol"]["DOGEUSDT"] = "5"  # type: ignore[index]
    with pytest.raises(OptionalRiskConfigError, match="UNAPPROVED_SYMBOL_UNIVERSE_EXPANSION"):
        validate_config_mapping(raw_doge)


def test_stale_version_changed_digest_inconsistent_thresholds_and_forbidden_keys(
    tmp_path: Path,
) -> None:
    raw = _base_raw()
    with pytest.raises(OptionalRiskConfigError, match="STALE_OR_UNSUPPORTED_CONFIG_VERSION"):
        validate_config_mapping({**raw, "config_version": "0.9.0"})
    with pytest.raises(OptionalRiskConfigError, match="CONFIG_VERSION_MISMATCH"):
        validate_config_mapping(raw, expected_config_version="2.0.0")
    with pytest.raises(OptionalRiskConfigError, match="CONFIG_DIGEST_MISMATCH"):
        validate_config_mapping(raw, expected_sha256="0" * 64)

    bad_daily = _base_raw()
    bad_daily["account_risk"]["daily_stop"] = "0.06"  # type: ignore[index]
    bad_daily["account_risk"]["daily_halt"] = "0.06"  # type: ignore[index]
    with pytest.raises(OptionalRiskConfigError, match="INCONSISTENT_DAILY_LOSS_THRESHOLDS"):
        validate_config_mapping(bad_daily)

    bad_prov = _base_raw()
    bad_prov["provisional_rules"]["day_boundary"]["status"] = "ACTIVE_PRODUCTION"  # type: ignore[index]
    with pytest.raises(
        OptionalRiskConfigError, match="UNSUPPORTED_RISK_DAY_OR_PORTFOLIO_ACTIVATION"
    ):
        validate_config_mapping(bad_prov)

    bad_layer2 = {**_base_raw(), "layer2_private_user_data": "ENABLED"}
    with pytest.raises(
        OptionalRiskConfigError, match="LAYER2_PRIVATE_USER_DATA_MUST_REMAIN_DISABLED"
    ):
        validate_config_mapping(bad_layer2)

    secret_cfg = {**_base_raw(), "api_key": "dummy"}
    with pytest.raises(
        OptionalRiskBoundaryError, match="FORBIDDEN_SECRET_OR_LIVE_CREDENTIAL_INPUT"
    ):
        validate_config_mapping(secret_cfg)

    link_path = tmp_path / "link.yaml"
    link_path.symlink_to(DEFAULT_YAML)
    with pytest.raises(OptionalRiskConfigError, match="SYMLINK_CONFIG_FORBIDDEN"):
        load_config_file(link_path)

    bad_json = tmp_path / "bad.json"
    bad_json.write_text('{"schema_version": "X", "per_trade_default": 0.02}', encoding="utf-8")
    with pytest.raises(OptionalRiskConfigError, match="BINARY_FLOAT_FORBIDDEN"):
        load_config_file(bad_json)
