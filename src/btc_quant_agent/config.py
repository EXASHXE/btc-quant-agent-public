from __future__ import annotations

import hashlib
import json
import math
import os
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any


def _require_positive_int(value: Any, name: str) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _require_nonnegative_real(value: Any, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    if not math.isfinite(float(value)) or value < 0:
        raise ValueError(f"{name} must be finite and nonnegative")


@dataclass(frozen=True)
class RuntimeConfig:
    symbol: str = "BTCUSDT"
    strategy_version: str = "0.3.11"
    feature_version: str = "0.3.11"
    validation_status: str = "EXPERIMENTAL"
    decision_interval: str = "15m"
    ttl_minutes: int = 45
    cooldown_minutes: int = 90
    max_data_age_seconds: int = 120

    def __post_init__(self) -> None:
        if self.validation_status not in {
            "EXPERIMENTAL",
            "LOW_SAMPLE_CONFIDENCE",
            "VALIDATED_OOS",
            "VALIDATED_FORWARD",
        }:
            raise ValueError("unsupported validation_status")
        if self.decision_interval != "15m":
            raise ValueError("v0.2.2 supports a 15m decision interval only")
        for name in ("ttl_minutes", "cooldown_minutes", "max_data_age_seconds"):
            _require_positive_int(getattr(self, name), f"runtime.{name}")


@dataclass(frozen=True)
class StrategyConfig:
    ema_fast: int = 7
    ema_mid: int = 25
    ema_slow: int = 99
    atr_period: int = 14
    adx_period: int = 14
    adx_trend_min: float = 20.0
    slope_lookback: int = 5
    pivot_left: int = 2
    pivot_right: int = 2
    pullback_atr_tolerance: float = 0.35
    breakout_atr_min: float = 0.12
    retest_atr_tolerance: float = 0.30
    volume_z_min: float = -0.25
    rr_min: float = 1.8
    stop_atr_buffer: float = 0.25
    high_vol_atr_percentile: float = 0.9
    max_signal_age_bars: int = 3
    extreme_bar_atr: float = 2.5
    level_lookback_bars: int = 160
    rsi_period: int = 14
    roc_period: int = 12
    bb_period: int = 20
    cvd_window: int = 20
    factor_score_min: float = 72.0
    min_positive_factor_groups: int = 4
    rsi_long_min: float = 45.0
    rsi_long_max: float = 72.0
    rsi_short_min: float = 28.0
    rsi_short_max: float = 55.0
    funding_extreme_abs: float = 0.001
    max_spread_bps: float = 5.0
    max_abs_basis_rate: float = 0.003
    enable_momentum_group: bool = True
    enable_participation_group: bool = True
    enable_derivatives_group: bool = True
    enable_volatility_liquidity_group: bool = True
    enable_volatility_liquidity_score: bool = True
    enable_order_book_factor: bool = False

    def __post_init__(self) -> None:
        for item in fields(self):
            value = getattr(self, item.name)
            if item.name.startswith("enable_"):
                if type(value) is not bool:
                    raise TypeError(f"strategy.{item.name} must be a boolean")
            elif isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"strategy.{item.name} must be numeric")
            elif not math.isfinite(float(value)):
                raise ValueError(f"strategy.{item.name} must be finite")


@dataclass(frozen=True)
class RiskConfig:
    account_equity_usdt: float = 100.0
    risk_per_trade: float = 0.005
    max_notional_usdt: float = 100.0
    min_notional_usdt: float = 5.0
    display_leverage: float = 20.0
    taker_fee_rate: float = 0.0005
    slippage_bps_per_side: float = 2.0
    funding_rate_estimate: float = 0.0
    funding_stress_rate: float = 0.0005
    max_expected_funding_events: int = 2

    def __post_init__(self) -> None:
        for item in fields(self):
            value = getattr(self, item.name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"risk.{item.name} must be numeric")
            if not math.isfinite(float(value)):
                raise ValueError(f"risk.{item.name} must be finite")
        if self.account_equity_usdt <= 0 or not 0 < self.risk_per_trade <= 0.05:
            raise ValueError("risk equity must be positive and risk_per_trade must be in (0, 0.05]")
        if not 0 < self.min_notional_usdt <= self.max_notional_usdt:
            raise ValueError("risk notional bounds are invalid")
        if self.display_leverage <= 0:
            raise ValueError("display leverage must be positive")
        if min(self.taker_fee_rate, self.slippage_bps_per_side, self.funding_stress_rate) < 0:
            raise ValueError("fees and slippage cannot be negative")
        if self.max_expected_funding_events < 0:
            raise ValueError("max_expected_funding_events cannot be negative")


@dataclass(frozen=True)
class DataConfig:
    rest_base_url: str = "https://fapi.binance.com"
    request_timeout_seconds: float = 10.0
    history_limit_15m: int = 500
    history_limit_1h: int = 500
    history_limit_4h: int = 500
    oi_stale_seconds: int = 900
    funding_stale_seconds: int = 900
    derivatives_stale_seconds: int = 900
    max_clock_skew_ms: int = 5_000

    def __post_init__(self) -> None:
        if not isinstance(self.rest_base_url, str) or not self.rest_base_url.startswith(
            ("http://", "https://")
        ):
            raise ValueError("data.rest_base_url must be an HTTP(S) URL")
        _require_nonnegative_real(self.request_timeout_seconds, "data.request_timeout_seconds")
        if self.request_timeout_seconds <= 0:
            raise ValueError("data.request_timeout_seconds must be positive")
        for name in (
            "history_limit_15m",
            "history_limit_1h",
            "history_limit_4h",
            "oi_stale_seconds",
            "funding_stale_seconds",
            "derivatives_stale_seconds",
            "max_clock_skew_ms",
        ):
            _require_positive_int(getattr(self, name), f"data.{name}")


@dataclass(frozen=True)
class BacktestConfig:
    trend_pullback_holding_minutes: int = 720
    breakout_retest_holding_minutes: int = 480

    def __post_init__(self) -> None:
        _require_positive_int(
            self.trend_pullback_holding_minutes,
            "backtest.trend_pullback_holding_minutes",
        )
        _require_positive_int(
            self.breakout_retest_holding_minutes,
            "backtest.breakout_retest_holding_minutes",
        )


@dataclass(frozen=True)
class ExecutionConfig:
    mode: str = "disabled"
    auto_execute: bool = False
    allow_live: bool = False
    max_leverage: int = 5
    max_notional_usdt: float = 100.0
    max_daily_loss_usdt: float = 2.0
    max_open_positions: int = 1
    plan_ttl_seconds: int = 120
    recv_window_ms: int = 5000
    position_mode: str = "ONE_WAY"
    margin_type: str = "ISOLATED"
    entry_order_type: str = "LIMIT"
    require_protective_orders: bool = True
    testnet_base_url: str = "https://testnet.binancefuture.com"

    def __post_init__(self) -> None:
        for name in ("auto_execute", "allow_live", "require_protective_orders"):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"execution.{name} must be a boolean")
        if self.mode not in {"disabled", "paper", "testnet", "live"}:
            raise ValueError("execution.mode must be disabled, paper, testnet, or live")
        if self.position_mode != "ONE_WAY":
            raise ValueError("phase two execution supports ONE_WAY position mode only")
        if type(self.max_leverage) is not int or not 1 <= self.max_leverage <= 20:
            raise ValueError("execution.max_leverage must be between 1 and 20")
        if self.entry_order_type.upper() not in {"LIMIT", "MARKET"}:
            raise ValueError("execution.entry_order_type must be LIMIT or MARKET")
        for name in ("max_notional_usdt", "max_daily_loss_usdt"):
            _require_nonnegative_real(getattr(self, name), f"execution.{name}")
        if self.max_notional_usdt <= 0 or self.max_daily_loss_usdt <= 0:
            raise ValueError("execution notional and daily loss limits must be positive")
        for name in ("max_open_positions", "plan_ttl_seconds", "recv_window_ms"):
            _require_positive_int(getattr(self, name), f"execution.{name}")
        if self.plan_ttl_seconds < 15:
            raise ValueError("execution position limit and plan TTL are invalid")


@dataclass(frozen=True)
class StorageConfig:
    sqlite_path: str = "./var/quant.db"

    def __post_init__(self) -> None:
        if not isinstance(self.sqlite_path, str) or not self.sqlite_path.strip():
            raise ValueError("storage.sqlite_path must be nonempty text")


@dataclass(frozen=True)
class NotifyConfig:
    feishu_enabled: bool = False

    def __post_init__(self) -> None:
        if type(self.feishu_enabled) is not bool:
            raise TypeError("notify.feishu_enabled must be a boolean")


@dataclass(frozen=True)
class AppConfig:
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    data: DataConfig = field(default_factory=DataConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    notify: NotifyConfig = field(default_factory=NotifyConfig)

    @property
    def config_hash(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _build(section: type[Any], raw: dict[str, Any] | None) -> Any:
    values = raw or {}
    if not isinstance(values, dict):
        raise TypeError(f"{section.__name__} configuration must be a table")
    allowed = {item.name for item in fields(section)}
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise ValueError(
            f"unknown {section.__name__} configuration keys: {','.join(unknown)}"
        )
    return section(**values)


def load_config(path: str | Path | None = None) -> AppConfig:
    """Load config with precedence: explicit path, BTC_QUANT_CONFIG, repository default."""
    env_candidate = os.getenv("BTC_QUANT_CONFIG")
    candidate_value = path if path is not None else env_candidate or "configs/default.toml"
    candidate = Path(candidate_value)
    if not candidate.is_file():
        source = "explicit" if path is not None else "BTC_QUANT_CONFIG" if env_candidate else "default"
        raise FileNotFoundError(f"{source} configuration file is unavailable: {candidate}")
    with candidate.open("rb") as handle:
        raw = tomllib.load(handle)
    allowed_sections = {
        "runtime",
        "strategy",
        "risk",
        "data",
        "backtest",
        "execution",
        "storage",
        "notify",
    }
    unknown_sections = sorted(set(raw) - allowed_sections)
    if unknown_sections:
        raise ValueError(f"unknown top-level configuration sections: {','.join(unknown_sections)}")
    config = AppConfig(
        runtime=_build(RuntimeConfig, raw.get("runtime")),
        strategy=_build(StrategyConfig, raw.get("strategy")),
        risk=_build(RiskConfig, raw.get("risk")),
        data=_build(DataConfig, raw.get("data")),
        backtest=_build(BacktestConfig, raw.get("backtest")),
        execution=_build(ExecutionConfig, raw.get("execution")),
        storage=_build(StorageConfig, raw.get("storage")),
        notify=_build(NotifyConfig, raw.get("notify")),
    )
    db_override = os.getenv("BTC_QUANT_DB_PATH")
    if not db_override:
        return config
    return AppConfig(
        runtime=config.runtime,
        strategy=config.strategy,
        risk=config.risk,
        data=config.data,
        backtest=config.backtest,
        execution=config.execution,
        storage=StorageConfig(sqlite_path=db_override),
        notify=config.notify,
    )
