"""Bounded bridge configuration; no credentials, arbitrary data path or allow-live flag."""

from __future__ import annotations

from pathlib import Path
from math import isfinite
from typing import Literal

import yaml
from pydantic import Field, model_validator

from ..config import ConfigModel, PlatformConfig
from ..core import fingerprint


class UniversePolicy(ConfigModel):
    quote_currency: Literal["USDT"] = "USDT"
    min_quote_volume_24h: float = Field(default=10_000_000, ge=0)
    liquidity_max_age_ms: int = Field(default=120000, gt=0)
    metadata_max_age_ms: int = Field(default=86400000, gt=0)


class AdmissionPolicy(ConfigModel):
    derivatives_max_age_ms: int = Field(default=120000, gt=0)
    spot_max_skew_ms: int = Field(default=1000, ge=0)
    require_open_interest_for_entry: bool = False
    # Funding is required by the existing execution policy, not silently waived here.


class BridgeConfig(ConfigModel):
    schema_version: Literal["V070-MARKET-BRIDGE-1"] = "V070-MARKET-BRIDGE-1"
    provider: Literal["binance", "okx"] = "binance"
    mode: Literal["offline_fixture", "blocked_live"] = "offline_fixture"
    universe: UniversePolicy = Field(default_factory=UniversePolicy)
    admission: AdmissionPolicy = Field(default_factory=AdmissionPolicy)
    platform: PlatformConfig = Field(default_factory=PlatformConfig)

    @model_validator(mode="after")
    def supported(self) -> BridgeConfig:
        if self.platform.market not in ("SPOT", "PERPETUAL"):
            raise ValueError("bridge supports USDT spot and linear perpetual contracts only")
        from ..factors import REGISTRY, validate_params
        from ..strategies import REGISTRY as strategies

        for f in self.platform.factors:
            if f.id.upper() not in REGISTRY:
                raise ValueError(f"unknown factor: {f.id}")
            validate_params(f.id.upper(), f.params)
            if self.platform.market not in REGISTRY[f.id.upper()].supported_markets:
                raise ValueError(f"factor market unsupported: {f.id}")
        for s in self.platform.strategies:
            if s.id not in strategies:
                raise ValueError(f"unknown strategy: {s.id}")
            definition = strategies[s.id]
            if definition.status == "RESEARCH_ONLY":
                raise ValueError("multi-leg research is not directional advisory")
            if self.platform.market not in definition.supported_markets:
                raise ValueError("strategy market unsupported")
            if set(s.params) - set(definition.parameters):
                raise ValueError(f"unknown strategy parameters: {s.id}")
            for k, v in s.params.items():
                if isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) or v <= 0:
                    raise ValueError(f"invalid strategy parameter {k}")
                if k in ("period", "fast", "slow", "lookback") and (type(v) is not int or v < 2):
                    raise ValueError(f"invalid integer parameter {k}")
            if (
                "fast" in definition.parameters
                and "slow" in definition.parameters
                and s.params.get("fast", 10) >= s.params.get("slow", 30)
            ):
                raise ValueError("strategy fast must be less than slow")
        return self

    @property
    def hash(self) -> str:
        return fingerprint(self.model_dump(mode="json"))


def load(path: str | Path) -> BridgeConfig:
    return BridgeConfig.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))
