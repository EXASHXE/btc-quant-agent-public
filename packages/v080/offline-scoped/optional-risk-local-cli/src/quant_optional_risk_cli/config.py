"""Strict versioned configuration contract and defaults for optional account risk."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from .models import (
    APPROVED_SYMBOLS,
    CONFIG_SCHEMA_VERSION,
    DECIMAL_CTX,
    MAJOR_SYMBOLS,
    POLICY_REFERENCE,
    SHA256_HEX_RE,
    SOL_OTHER_SYMBOLS,
    SUPPORTED_CONFIG_VERSIONS,
    D,
    OptionalRiskConfigError,
    canonical_sha256,
    parse_strict_bool,
    parse_strict_decimal_string,
    scan_forbidden_live_or_secret_fields,
)
from .parser import load_structured_file

ALLOWED_TOP_KEYS = frozenset(
    {
        "schema_version",
        "config_version",
        "policy_reference",
        "review_status",
        "source",
        "expected_config_sha256",
        "layer2_private_user_data",
        "layer3_trade_execution",
        "account_risk",
        "provisional_rules",
    }
)
REQUIRED_TOP_KEYS = frozenset(
    {
        "schema_version",
        "config_version",
        "policy_reference",
        "review_status",
        "source",
        "layer2_private_user_data",
        "layer3_trade_execution",
        "account_risk",
        "provisional_rules",
    }
)
ALLOWED_RISK_KEYS = frozenset(
    {
        "enabled",
        "per_trade_default",
        "per_trade_max",
        "selected_per_trade_risk",
        "explicit_above_default_risk_selected",
        "btc_eth_default_leverage",
        "btc_eth_normal_band",
        "btc_eth_exceptional_max",
        "sol_other_default_leverage",
        "sol_other_max_leverage",
        "selected_leverage_by_symbol",
        "explicit_exceptional_leverage_selected",
        "daily_stop",
        "daily_halt",
    }
)
REQUIRED_RISK_KEYS = frozenset(
    {
        "enabled",
        "per_trade_default",
        "per_trade_max",
        "btc_eth_default_leverage",
        "btc_eth_exceptional_max",
        "sol_other_default_leverage",
        "sol_other_max_leverage",
        "daily_stop",
        "daily_halt",
    }
)
ALLOWED_REVIEW_STATUSES = frozenset({"PROPOSED_NOT_PRODUCTION_POLICY", "OWNER_LOCAL_OFFLINE_DRAFT"})
ALLOWED_CONFIG_SOURCES = frozenset(
    {"OWNER_LOCAL_DISABLED_DEFAULT", "SYNTHETIC_OPT_IN_QA_FIXTURE_ONLY"}
)

MAX_PER_TRADE_DEFAULT = D("0.02")
MAX_PER_TRADE_ABSOLUTE = D("0.03")
MIN_LEVERAGE = D("1")
MAX_BTC_ETH_NORMAL_HIGH = D("15")
MAX_BTC_ETH_EXCEPTIONAL = D("20")
MAX_SOL_OTHER = D("15")
MAX_DAILY_STOP = D("0.06")
MAX_DAILY_HALT = D("0.08")

DEFAULT_PROVISIONAL = {
    "day_boundary": {"convention": "00:00_UTC_TO_NEXT_00:00_UTC", "status": "PROPOSED"},
    "cashflow_adjustment": {"formula": "max(0,(E0-(Et-F))/E0)", "status": "PROPOSED"},
    "portfolio_exposure_aggregation": {
        "rule": "OPEN_POSITIONS_INCREMENTAL_DOWNSIDE_PLUS_CANDIDATE_UNDER_6PCT_HEADROOM",
        "status": "PROPOSED",
    },
}


def _dstr(value: Decimal) -> str:
    return format(value, "f")


@dataclass(frozen=True)
class ProvisionalPolicyMarkers:
    """Explicit PROPOSED markers for unapproved day-boundary, flow, and portfolio rules."""

    day_boundary_convention: str
    day_boundary_status: str
    cashflow_formula: str
    cashflow_status: str
    portfolio_rule: str
    portfolio_status: str

    def to_dict(self) -> dict[str, dict[str, str]]:
        return {
            "day_boundary": {
                "convention": self.day_boundary_convention,
                "status": self.day_boundary_status,
            },
            "cashflow_adjustment": {
                "formula": self.cashflow_formula,
                "status": self.cashflow_status,
            },
            "portfolio_exposure_aggregation": {
                "rule": self.portfolio_rule,
                "status": self.portfolio_status,
            },
        }


@dataclass(frozen=True)
class AccountRiskParameters:
    """Validated optional account-risk parameter values using exact Decimal math."""

    enabled: bool
    per_trade_default: Decimal
    per_trade_max: Decimal
    selected_per_trade_risk: Decimal
    explicit_above_default_risk_selected: bool
    btc_eth_default_leverage: Decimal
    btc_eth_normal_band: tuple[Decimal, Decimal]
    btc_eth_exceptional_max: Decimal
    sol_other_default_leverage: Decimal
    sol_other_max_leverage: Decimal
    selected_leverage_by_symbol: dict[str, Decimal]
    explicit_exceptional_leverage_selected: bool
    daily_stop: Decimal
    daily_halt: Decimal

    def leverage_for(self, symbol: str) -> Decimal:
        if symbol not in APPROVED_SYMBOLS:
            raise OptionalRiskConfigError("UNAPPROVED_SYMBOL", symbol)
        return self.selected_leverage_by_symbol[symbol]

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "per_trade_default": _dstr(self.per_trade_default),
            "per_trade_max": _dstr(self.per_trade_max),
            "selected_per_trade_risk": _dstr(self.selected_per_trade_risk),
            "explicit_above_default_risk_selected": self.explicit_above_default_risk_selected,
            "btc_eth_default_leverage": _dstr(self.btc_eth_default_leverage),
            "btc_eth_normal_band": [_dstr(x) for x in self.btc_eth_normal_band],
            "btc_eth_exceptional_max": _dstr(self.btc_eth_exceptional_max),
            "sol_other_default_leverage": _dstr(self.sol_other_default_leverage),
            "sol_other_max_leverage": _dstr(self.sol_other_max_leverage),
            "selected_leverage_by_symbol": {
                sym: _dstr(self.selected_leverage_by_symbol[sym])
                for sym in sorted(self.selected_leverage_by_symbol)
            },
            "explicit_exceptional_leverage_selected": self.explicit_exceptional_leverage_selected,
            "daily_stop": _dstr(self.daily_stop),
            "daily_halt": _dstr(self.daily_halt),
        }


@dataclass(frozen=True)
class OptionalAccountRiskConfig:
    """Complete versioned configuration object with canonical SHA-256 identity."""

    schema_version: str
    config_version: str
    policy_reference: str
    review_status: str
    source: str
    layer2_private_user_data: str
    layer3_trade_execution: str
    account_risk: AccountRiskParameters
    provisional_rules: ProvisionalPolicyMarkers
    config_sha256: str
    config_path: str | None = None

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "config_version": self.config_version,
            "policy_reference": self.policy_reference,
            "review_status": self.review_status,
            "source": self.source,
            "layer2_private_user_data": self.layer2_private_user_data,
            "layer3_trade_execution": self.layer3_trade_execution,
            "account_risk": self.account_risk.to_dict(),
            "provisional_rules": self.provisional_rules.to_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        data = self.canonical_payload()
        data["config_sha256"] = self.config_sha256
        data["config_path"] = self.config_path
        return data


def _build_config(
    *,
    schema_version: str,
    config_version: str,
    policy_reference: str,
    review_status: str,
    source: str,
    account_risk: AccountRiskParameters,
    provisional_rules: ProvisionalPolicyMarkers,
    config_path: str | None = None,
) -> OptionalAccountRiskConfig:
    payload = {
        "schema_version": schema_version,
        "config_version": config_version,
        "policy_reference": policy_reference,
        "review_status": review_status,
        "source": source,
        "layer2_private_user_data": "DISABLED",
        "layer3_trade_execution": "DISABLED",
        "account_risk": account_risk.to_dict(),
        "provisional_rules": provisional_rules.to_dict(),
    }
    digest = canonical_sha256(payload)
    return OptionalAccountRiskConfig(
        schema_version=schema_version,
        config_version=config_version,
        policy_reference=policy_reference,
        review_status=review_status,
        source=source,
        layer2_private_user_data="DISABLED",
        layer3_trade_execution="DISABLED",
        account_risk=account_risk,
        provisional_rules=provisional_rules,
        config_sha256=digest,
        config_path=config_path,
    )


def default_disabled_config() -> OptionalAccountRiskConfig:
    """Return canonical default-disabled config matching Owner KR policy decision."""
    risk = AccountRiskParameters(
        enabled=False,
        per_trade_default=D("0.02"),
        per_trade_max=D("0.03"),
        selected_per_trade_risk=D("0.02"),
        explicit_above_default_risk_selected=False,
        btc_eth_default_leverage=D("10"),
        btc_eth_normal_band=(D("10"), D("15")),
        btc_eth_exceptional_max=D("20"),
        sol_other_default_leverage=D("10"),
        sol_other_max_leverage=D("15"),
        selected_leverage_by_symbol={
            "BTCUSDT": D("10"),
            "ETHUSDT": D("10"),
            "SOLUSDT": D("10"),
        },
        explicit_exceptional_leverage_selected=False,
        daily_stop=D("0.06"),
        daily_halt=D("0.08"),
    )
    provisional = ProvisionalPolicyMarkers(
        day_boundary_convention="00:00_UTC_TO_NEXT_00:00_UTC",
        day_boundary_status="PROPOSED",
        cashflow_formula="max(0,(E0-(Et-F))/E0)",
        cashflow_status="PROPOSED",
        portfolio_rule="OPEN_POSITIONS_INCREMENTAL_DOWNSIDE_PLUS_CANDIDATE_UNDER_6PCT_HEADROOM",
        portfolio_status="PROPOSED",
    )
    return _build_config(
        schema_version=CONFIG_SCHEMA_VERSION,
        config_version="1.0.0",
        policy_reference=POLICY_REFERENCE,
        review_status="PROPOSED_NOT_PRODUCTION_POLICY",
        source="OWNER_LOCAL_DISABLED_DEFAULT",
        account_risk=risk,
        provisional_rules=provisional,
        config_path="BUILTIN_DISABLED_DEFAULT",
    )


def _validate_provisional_rules(raw: Any) -> ProvisionalPolicyMarkers:
    if not isinstance(raw, dict):
        raise OptionalRiskConfigError("INVALID_PROVISIONAL_RULES_OBJECT")
    expected_keys = set(DEFAULT_PROVISIONAL)
    if set(raw.keys()) != expected_keys:
        raise OptionalRiskConfigError("PROVISIONAL_RULES_KEY_MISMATCH")
    for section, expected in DEFAULT_PROVISIONAL.items():
        val = raw[section]
        if not isinstance(val, dict) or set(val.keys()) != set(expected.keys()):
            raise OptionalRiskConfigError("PROVISIONAL_RULE_INVALID", section)
        if val["status"] != "PROPOSED":
            raise OptionalRiskConfigError(
                "UNSUPPORTED_RISK_DAY_OR_PORTFOLIO_ACTIVATION",
                f"{section}.status must remain PROPOSED",
            )
        if val != expected:
            raise OptionalRiskConfigError("PROVISIONAL_RULE_MODIFIED", section)
    return ProvisionalPolicyMarkers(
        day_boundary_convention=DEFAULT_PROVISIONAL["day_boundary"]["convention"],
        day_boundary_status="PROPOSED",
        cashflow_formula=DEFAULT_PROVISIONAL["cashflow_adjustment"]["formula"],
        cashflow_status="PROPOSED",
        portfolio_rule=DEFAULT_PROVISIONAL["portfolio_exposure_aggregation"]["rule"],
        portfolio_status="PROPOSED",
    )


def validate_config_mapping(
    raw: dict[str, Any],
    *,
    expected_sha256: str | None = None,
    expected_config_version: str | None = None,
    allow_enabled_opt_in: bool = False,
    config_path: str | None = None,
) -> OptionalAccountRiskConfig:
    """Strictly validate an optional account-risk config mapping with zero permissive fallback."""
    if not isinstance(raw, dict):
        raise OptionalRiskConfigError("CONFIG_MUST_BE_MAPPING")
    scan_forbidden_live_or_secret_fields(raw)

    unknown = sorted(set(raw.keys()) - ALLOWED_TOP_KEYS)
    if unknown:
        raise OptionalRiskConfigError("UNKNOWN_CONFIG_KEY", ",".join(unknown))
    missing = sorted(REQUIRED_TOP_KEYS - set(raw.keys()))
    if missing:
        raise OptionalRiskConfigError("MISSING_REQUIRED_CONFIG_KEY", ",".join(missing))

    schema_version = raw["schema_version"]
    if schema_version != CONFIG_SCHEMA_VERSION:
        raise OptionalRiskConfigError("STALE_OR_UNSUPPORTED_SCHEMA_VERSION", str(schema_version))

    config_version = raw["config_version"]
    if config_version not in SUPPORTED_CONFIG_VERSIONS:
        raise OptionalRiskConfigError("STALE_OR_UNSUPPORTED_CONFIG_VERSION", str(config_version))
    if expected_config_version is not None and config_version != expected_config_version:
        raise OptionalRiskConfigError(
            "CONFIG_VERSION_MISMATCH",
            f"expected={expected_config_version} actual={config_version}",
        )

    policy_ref = raw["policy_reference"]
    if policy_ref != POLICY_REFERENCE:
        raise OptionalRiskConfigError("POLICY_REFERENCE_MISMATCH", str(policy_ref))

    review_status = raw["review_status"]
    if not isinstance(review_status, str) or review_status not in ALLOWED_REVIEW_STATUSES:
        raise OptionalRiskConfigError("UNAPPROVED_PRODUCTION_POLICY_CLAIM", str(review_status))

    source = raw["source"]
    if not isinstance(source, str) or source not in ALLOWED_CONFIG_SOURCES:
        raise OptionalRiskConfigError("UNQUALIFIED_CONFIG_SOURCE", str(source))

    if raw["layer2_private_user_data"] != "DISABLED":
        raise OptionalRiskConfigError("LAYER2_PRIVATE_USER_DATA_MUST_REMAIN_DISABLED")
    if raw["layer3_trade_execution"] != "DISABLED":
        raise OptionalRiskConfigError("LAYER3_TRADE_EXECUTION_MUST_REMAIN_DISABLED")

    ar = raw["account_risk"]
    if not isinstance(ar, dict):
        raise OptionalRiskConfigError("INVALID_ACCOUNT_RISK_OBJECT")
    ar_unknown = sorted(set(ar.keys()) - ALLOWED_RISK_KEYS)
    if ar_unknown:
        raise OptionalRiskConfigError("UNKNOWN_ACCOUNT_RISK_KEY", ",".join(ar_unknown))
    ar_missing = sorted(REQUIRED_RISK_KEYS - set(ar.keys()))
    if ar_missing:
        raise OptionalRiskConfigError("MISSING_ACCOUNT_RISK_KEY", ",".join(ar_missing))

    enabled = parse_strict_bool(ar["enabled"], "account_risk.enabled")
    if enabled and not allow_enabled_opt_in:
        raise OptionalRiskConfigError(
            "AUTO_ENABLE_AFTER_RESTART_FORBIDDEN",
            "account_risk.enabled=true requires explicit per-invocation opt-in with synthetic fixtures",
        )
    if enabled and source != "SYNTHETIC_OPT_IN_QA_FIXTURE_ONLY":
        raise OptionalRiskConfigError(
            "ENABLED_CONFIG_REQUIRES_SYNTHETIC_SOURCE",
            f"source={source}",
        )

    per_trade_default = parse_strict_decimal_string(
        ar["per_trade_default"], "account_risk.per_trade_default", positive=True
    )
    per_trade_max = parse_strict_decimal_string(
        ar["per_trade_max"], "account_risk.per_trade_max", positive=True
    )
    selected_risk = (
        parse_strict_decimal_string(
            ar["selected_per_trade_risk"], "account_risk.selected_per_trade_risk", positive=True
        )
        if "selected_per_trade_risk" in ar
        else per_trade_default
    )
    above_default_flag = (
        parse_strict_bool(
            ar["explicit_above_default_risk_selected"],
            "account_risk.explicit_above_default_risk_selected",
        )
        if "explicit_above_default_risk_selected" in ar
        else False
    )

    if per_trade_default > MAX_PER_TRADE_DEFAULT:
        raise OptionalRiskConfigError("PER_TRADE_DEFAULT_EXCEEDS_0_02")
    if per_trade_max < per_trade_default:
        raise OptionalRiskConfigError("INCONSISTENT_PER_TRADE_RISK_RANGE")
    if per_trade_max > MAX_PER_TRADE_ABSOLUTE:
        raise OptionalRiskConfigError("PER_TRADE_MAX_EXCEEDS_0_03")
    if selected_risk > per_trade_max:
        raise OptionalRiskConfigError("SELECTED_RISK_EXCEEDS_CAP")
    if selected_risk > per_trade_default and not above_default_flag:
        raise OptionalRiskConfigError("ABOVE_DEFAULT_RISK_REQUIRES_EXPLICIT_SELECTION")
    if above_default_flag and selected_risk <= per_trade_default:
        raise OptionalRiskConfigError("SPURIOUS_ABOVE_DEFAULT_RISK_FLAG")

    btc_default = parse_strict_decimal_string(
        ar["btc_eth_default_leverage"], "account_risk.btc_eth_default_leverage", positive=True
    )
    btc_max = parse_strict_decimal_string(
        ar["btc_eth_exceptional_max"], "account_risk.btc_eth_exceptional_max", positive=True
    )
    if "btc_eth_normal_band" in ar:
        raw_band = ar["btc_eth_normal_band"]
        if not isinstance(raw_band, list) or len(raw_band) != 2:
            raise OptionalRiskConfigError("INVALID_BTC_ETH_NORMAL_BAND")
        band_lo = parse_strict_decimal_string(
            raw_band[0], "account_risk.btc_eth_normal_band[0]", positive=True
        )
        band_hi = parse_strict_decimal_string(
            raw_band[1], "account_risk.btc_eth_normal_band[1]", positive=True
        )
    else:
        band_lo, band_hi = D("10"), D("15")

    if btc_default < MIN_LEVERAGE or band_lo < MIN_LEVERAGE:
        raise OptionalRiskConfigError("LEVERAGE_BELOW_ONE")
    if not (band_lo <= btc_default <= band_hi <= MAX_BTC_ETH_NORMAL_HIGH):
        raise OptionalRiskConfigError("INVALID_BTC_ETH_NORMAL_BAND_BOUNDS")
    if btc_max < band_hi or btc_max > MAX_BTC_ETH_EXCEPTIONAL:
        raise OptionalRiskConfigError("BTC_ETH_EXCEPTIONAL_LEVERAGE_OUT_OF_RANGE")

    sol_default = parse_strict_decimal_string(
        ar["sol_other_default_leverage"], "account_risk.sol_other_default_leverage", positive=True
    )
    sol_max = parse_strict_decimal_string(
        ar["sol_other_max_leverage"], "account_risk.sol_other_max_leverage", positive=True
    )
    if sol_default < MIN_LEVERAGE or sol_max < sol_default or sol_max > MAX_SOL_OTHER:
        raise OptionalRiskConfigError("SOL_OTHER_LEVERAGE_OUT_OF_RANGE")

    exc_lev_flag = (
        parse_strict_bool(
            ar["explicit_exceptional_leverage_selected"],
            "account_risk.explicit_exceptional_leverage_selected",
        )
        if "explicit_exceptional_leverage_selected" in ar
        else False
    )

    selected_lev: dict[str, Decimal] = {
        "BTCUSDT": btc_default,
        "ETHUSDT": btc_default,
        "SOLUSDT": sol_default,
    }
    if "selected_leverage_by_symbol" in ar:
        raw_sel = ar["selected_leverage_by_symbol"]
        if not isinstance(raw_sel, dict):
            raise OptionalRiskConfigError("INVALID_SELECTED_LEVERAGE_BY_SYMBOL")
        for sym, val in raw_sel.items():
            if not isinstance(sym, str) or sym not in APPROVED_SYMBOLS:
                raise OptionalRiskConfigError("UNAPPROVED_SYMBOL_UNIVERSE_EXPANSION", str(sym))
            lev = parse_strict_decimal_string(
                val, f"account_risk.selected_leverage_by_symbol.{sym}", positive=True
            )
            if lev < MIN_LEVERAGE:
                raise OptionalRiskConfigError("LEVERAGE_BELOW_ONE", sym)
            if sym in MAJOR_SYMBOLS:
                if lev > btc_max:
                    raise OptionalRiskConfigError("LEVERAGE_EXCEEDS_CEILING", sym)
                if lev > band_hi and not exc_lev_flag:
                    raise OptionalRiskConfigError(
                        "EXCEPTIONAL_LEVERAGE_REQUIRES_EXPLICIT_SELECTION", sym
                    )
            elif sym in SOL_OTHER_SYMBOLS and lev > sol_max:
                raise OptionalRiskConfigError("LEVERAGE_EXCEEDS_CEILING", sym)
            selected_lev[sym] = lev

    if exc_lev_flag and all(selected_lev[s] <= band_hi for s in MAJOR_SYMBOLS):
        raise OptionalRiskConfigError("SPURIOUS_EXCEPTIONAL_LEVERAGE_FLAG")

    daily_stop = parse_strict_decimal_string(
        ar["daily_stop"], "account_risk.daily_stop", positive=True
    )
    daily_halt = parse_strict_decimal_string(
        ar["daily_halt"], "account_risk.daily_halt", positive=True
    )
    if daily_stop > MAX_DAILY_STOP:
        raise OptionalRiskConfigError("DAILY_STOP_EXCEEDS_0_06")
    if daily_halt > MAX_DAILY_HALT:
        raise OptionalRiskConfigError("DAILY_HALT_EXCEEDS_0_08")
    if daily_stop >= daily_halt:
        raise OptionalRiskConfigError("INCONSISTENT_DAILY_LOSS_THRESHOLDS")

    provisional = _validate_provisional_rules(raw["provisional_rules"])

    with_ctx = DECIMAL_CTX  # keep Decimal context clean
    _ = with_ctx
    params = AccountRiskParameters(
        enabled=enabled,
        per_trade_default=per_trade_default,
        per_trade_max=per_trade_max,
        selected_per_trade_risk=selected_risk,
        explicit_above_default_risk_selected=above_default_flag,
        btc_eth_default_leverage=btc_default,
        btc_eth_normal_band=(band_lo, band_hi),
        btc_eth_exceptional_max=btc_max,
        sol_other_default_leverage=sol_default,
        sol_other_max_leverage=sol_max,
        selected_leverage_by_symbol=selected_lev,
        explicit_exceptional_leverage_selected=exc_lev_flag,
        daily_stop=daily_stop,
        daily_halt=daily_halt,
    )
    cfg = _build_config(
        schema_version=schema_version,
        config_version=config_version,
        policy_reference=policy_ref,
        review_status=review_status,
        source=source,
        account_risk=params,
        provisional_rules=provisional,
        config_path=config_path,
    )

    embedded_sha = raw.get("expected_config_sha256")
    if embedded_sha is not None:
        if not isinstance(embedded_sha, str) or not SHA256_HEX_RE.fullmatch(embedded_sha):
            raise OptionalRiskConfigError("INVALID_EXPECTED_CONFIG_SHA256")
        if embedded_sha != cfg.config_sha256:
            raise OptionalRiskConfigError(
                "CONFIG_DIGEST_MISMATCH",
                f"embedded={embedded_sha} actual={cfg.config_sha256}",
            )
    if expected_sha256 is not None:
        if expected_sha256 != cfg.config_sha256:
            raise OptionalRiskConfigError(
                "CONFIG_DIGEST_MISMATCH",
                f"expected={expected_sha256} actual={cfg.config_sha256}",
            )
    return cfg


def load_config_file(
    path: Path,
    *,
    expected_sha256: str | None = None,
    expected_config_version: str | None = None,
    allow_enabled_opt_in: bool = False,
) -> OptionalAccountRiskConfig:
    """Load and strictly validate a YAML or JSON optional account-risk config file."""
    raw = load_structured_file(path)
    return validate_config_mapping(
        raw,
        expected_sha256=expected_sha256,
        expected_config_version=expected_config_version,
        allow_enabled_opt_in=allow_enabled_opt_in,
        config_path=str(path.resolve()),
    )
