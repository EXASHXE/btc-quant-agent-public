"""Strict, versioned YAML. Unsupported economics fail explicitly."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .core import fingerprint


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class FactorConfig(ConfigModel):
    id: str
    params: dict[str, Any] = Field(default_factory=dict)
    weight: float = 1.0
    normalization: Literal["raw", "rank", "zscore"] = "rank"
    gate_min: float | None = None
    gate_max: float | None = None
    regimes: list[str] = Field(default_factory=list)
    regime_weights: dict[str, float] = Field(default_factory=dict)


class StrategyConfig(ConfigModel):
    id: str
    params: dict[str, Any] = Field(default_factory=dict)
    regimes: list[str] = Field(default_factory=list)
    priority: int = 0
    group: str = "directional"


class RiskConfig(ConfigModel):
    equity: float = Field(default=10000, gt=0)
    per_trade: float = Field(default=0.005, gt=0, le=0.05)
    leverage: float = Field(default=1, ge=1, le=20)
    max_gross: float = Field(default=1.5, gt=0)
    max_symbol: float = Field(default=0.35, gt=0, le=1)
    max_positions: int = Field(default=4, ge=1)
    max_correlated: int = Field(default=2, ge=1)
    correlation_threshold: float = Field(default=0.85, ge=0, le=1)
    max_beta_exposure: float = Field(default=1.5, gt=0)
    liquidation_buffer: float = Field(default=0.03, ge=0, lt=1)
    max_funding_drag: float = Field(default=0.01, ge=0)


class ExecutionConfig(ConfigModel):
    fee_bps: float = Field(default=4, ge=-10, le=100)
    slippage_bps: float = Field(default=2, ge=0, le=1000)
    spread_bps: float = Field(default=2, ge=0, le=1000)
    max_spread_bps: float = Field(default=25, gt=0)
    delay_minutes: int = Field(default=1, ge=0, le=60)
    quote_max_age_ms: int = Field(default=5000, gt=0)
    source_max_age_ms: int = Field(default=90000, gt=0)
    entry_mode: Literal["market", "limit"] = "market"
    fill_fraction: float = Field(default=1, gt=0, le=1)
    volume_participation: float = Field(default=0.01, gt=0, le=1)
    funding: Literal["required", "exclude_with_warning"] = "required"


class EntryConfig(ConfigModel):
    expiry_minutes: int = Field(default=10, ge=1)
    region_bps: float = Field(default=50, gt=0)
    min_score: float = Field(default=-100, ge=-1000, le=1000)
    confirmation_bars: int = Field(default=1, ge=0, le=10)
    factor_condition: Literal["all", "any"] = "all"
    aggregation: Literal["priority", "vote"] = "priority"


class ExitConfig(ConfigModel):
    stop_lookback: int = Field(default=12, ge=3, le=200)
    stop_buffer_ticks: int = Field(default=1, ge=0)
    trailing_atr: float = Field(default=2, gt=0)
    partial_at_r: float = Field(default=1.5, gt=0)
    partial_fraction: float = Field(default=0.5, gt=0, lt=1)
    max_holding_bars: int = Field(default=80, ge=1)
    policy: Literal["strategy", "trailing", "mean"] = "strategy"
    stop_order: Literal["market", "limit"] = "market"
    stop_limit_offset_bps: float = Field(default=10, ge=0)


class MLConfig(ConfigModel):
    family: str = "logistic"
    features: list[str] = Field(default_factory=lambda: ["ROC", "RSI", "ATR", "RELATIVE_VOLUME"])
    target: str = "direction"
    horizon: int = Field(default=5, ge=1, le=50)
    context: int = Field(default=12, ge=2, le=200)
    epochs: int = Field(default=1, ge=1, le=100)
    hidden: int = Field(default=16, ge=4)
    seed: int = 7
    embargo: int = Field(default=2, ge=0)
    artifact: str | None = None
    device: Literal["cpu", "auto"] = "cpu"


class PlatformConfig(ConfigModel):
    schema_version: Literal["0.7.0"] = "0.7.0"
    name: str = "synthetic"
    market: Literal["PERPETUAL", "SPOT", "EQUITY", "ETF"] = "PERPETUAL"
    universe: list[str] = Field(default_factory=lambda: ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    interval_seconds: Literal[60, 300, 900] = 60
    benchmark: str = "BTCUSDT"
    dataset: Literal["synthetic"] = "synthetic"
    scenario: Literal["mixed", "trend", "range", "shock"] = "mixed"
    bars: int = Field(default=240, ge=80, le=20000)
    seed: int = 7
    strategies: list[StrategyConfig] = Field(default_factory=lambda: [StrategyConfig(id="trend_breakout")])
    factors: list[FactorConfig] = Field(default_factory=list)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    entry: EntryConfig = Field(default_factory=EntryConfig)
    exits: ExitConfig = Field(default_factory=ExitConfig)
    ml: MLConfig = Field(default_factory=MLConfig)

    @model_validator(mode="after")
    def combinations(self) -> PlatformConfig:
        if not self.universe or len(set(self.universe)) != len(self.universe):
            raise ValueError("universe must contain unique symbols")
        if self.benchmark not in self.universe:
            raise ValueError("benchmark must be included in the synthetic universe")
        if not self.strategies or len({s.id for s in self.strategies}) != len(self.strategies):
            raise ValueError("select at least one strategy; strategy IDs must be unique")
        if len({f.id.upper() for f in self.factors}) != len(self.factors):
            raise ValueError("factor IDs must be unique; use parameters on the selected factor")
        regimes = {"TREND_UP", "TREND_DOWN", "RANGE", "HIGH_VOLATILITY", "DELEVERAGING_SHOCK", "UNKNOWN"}
        if any(set(s.regimes) - regimes for s in self.strategies):
            raise ValueError("unsupported strategy regime")
        if any((set(f.regimes) | set(f.regime_weights)) - regimes for f in self.factors):
            raise ValueError("unsupported factor regime")
        if self.entry.expiry_minutes * 60 < self.interval_seconds * self.entry.confirmation_bars:
            raise ValueError("entry expires before the configured confirmation can complete")
        if self.market != "PERPETUAL" and self.risk.leverage != 1:
            raise ValueError("this baseline supports leverage only for linear perpetuals")
        return self

    @property
    def hash(self) -> str:
        return fingerprint(self.model_dump(mode="json"))


def load_config(path: str | Path) -> PlatformConfig:
    with Path(path).open(encoding="utf-8") as stream:
        raw = yaml.safe_load(stream)
    if not isinstance(raw, dict):
        raise ValueError("configuration must be a YAML mapping")
    config = PlatformConfig.model_validate(raw)
    from .factors import REGISTRY as factors, validate_params
    from .strategies import REGISTRY as strategies

    for factor in config.factors:
        if factor.id.upper() not in factors:
            raise ValueError(f"unknown factor: {factor.id}")
        validate_params(factor.id.upper(), factor.params)
        if config.market not in factors[factor.id.upper()].supported_markets:
            raise ValueError(f"{factor.id} does not support {config.market}")
    for strategy in config.strategies:
        if strategy.id not in strategies:
            raise ValueError(f"unknown strategy: {strategy.id}")
        definition = strategies[strategy.id]
        unknown = set(strategy.params) - set(definition.parameters)
        if unknown:
            raise ValueError(f"{strategy.id}: unsupported parameters {sorted(unknown)}")
        for name, value in strategy.params.items():
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{strategy.id}.{name}: expected positive number")
            if name in ("period", "fast", "slow", "lookback") and (type(value) is not int or value < 2):
                raise ValueError(f"{strategy.id}.{name}: expected integer >= 2")
        if (
            "fast" in definition.parameters
            and "slow" in definition.parameters
            and strategy.params.get("fast", 10) >= strategy.params.get("slow", 30)
        ):
            raise ValueError("strategy fast must be less than slow")
        if config.market not in definition.supported_markets:
            raise ValueError(f"{strategy.id} does not support {config.market}")
    return config
