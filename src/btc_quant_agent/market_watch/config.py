from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field, fields
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence


def _require_positive_int(value: Any, name: str) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _require_real(value: Any, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    if not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite")


def _require_nonnegative_real(value: Any, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    if not math.isfinite(float(value)) or value < 0:
        raise ValueError(f"{name} must be finite and nonnegative")


def canonicalize_symbols(symbols: Sequence[str]) -> tuple[str, ...]:
    """Uppercase, strip, deduplicate, and preserve stable order."""
    seen: set[str] = set()
    result: list[str] = []
    for s in symbols:
        sym = str(s).strip().upper()
        if sym and sym not in seen:
            seen.add(sym)
            result.append(sym)
    return tuple(result)


DEFAULT_RELATIVE_STRENGTH_UNIVERSE: tuple[str, ...] = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "LINKUSDT",
    "SUIUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "BNBUSDT",
)


@dataclass(frozen=True)
class MarketWatchRankingConfig:
    weight_trend_quality: float = 0.20
    weight_structure_quality: float = 0.15
    weight_entry_quality: float = 0.20
    weight_derivatives_confirmation: float = 0.15
    weight_participation_quality: float = 0.10
    weight_relative_strength: float = 0.10
    weight_net_rr: float = 0.10
    penalty_crowding: float = 15.0
    penalty_overextension: float = 20.0
    penalty_benchmark_risk: float = 25.0
    penalty_low_liquidity: float = 15.0
    penalty_timeframe_conflict: float = 20.0
    rs_weight_1h: float = 0.20
    rs_weight_4h: float = 0.50
    rs_weight_12h: float = 0.30
    rs_weight_btc: float = 0.40
    rs_weight_eth: float = 0.30
    rs_weight_median: float = 0.30

    def __post_init__(self) -> None:
        for f in fields(self):
            _require_nonnegative_real(getattr(self, f.name), f"ranking.{f.name}")

    @property
    def rs_weight_15m(self) -> float:
        """Deprecated legacy alias for rs_weight_1h."""
        return self.rs_weight_1h


@dataclass(frozen=True)
class MarketWatchThresholdsConfig:
    ema_fast: int = 20
    ema_mid: int = 50
    ema_slow: int = 200
    atr_period: int = 14
    adx_period: int = 14
    adx_trend_min: float = 20.0
    slope_lookback: int = 5
    pivot_left: int = 2
    pivot_right: int = 2
    high_vol_atr_percentile: float = 0.85
    vol_compression_bb_pct: float = 0.25
    vol_compression_min_bars: int = 3
    vol_expansion_atr_mult: float = 1.25
    overextension_ema20_atr: float = 2.2
    extreme_overextension_ema20_atr: float = 3.2
    overextension_ema50_atr: float = 3.8
    pullback_ema_tolerance_atr: float = 0.5
    breakout_atr_threshold: float = 0.12
    retest_atr_tolerance: float = 0.35
    failed_level_ttl_ms: int = 24 * 3600 * 1000
    failed_level_breakout_mult: float = 1.5
    failed_level_min_volume_z: float = 0.8
    max_retest_bars: int = 12
    max_signal_age_bars: int = 8
    entry_window_bars: int = 4
    min_volume_z: float = -0.5
    funding_crowding_abs: float = 0.0003
    funding_extreme_abs: float = 0.0008
    global_long_crowding_ratio: float = 2.2
    global_short_crowding_ratio: float = 0.55
    top_trader_crowding_ratio: float = 2.0
    max_spread_bps: float = 8.0
    min_quote_volume_24h: float = 5_000_000.0

    def __post_init__(self) -> None:
        int_fields = (
            "ema_fast",
            "ema_mid",
            "ema_slow",
            "atr_period",
            "adx_period",
            "slope_lookback",
            "pivot_left",
            "pivot_right",
            "failed_level_ttl_ms",
            "max_retest_bars",
            "vol_compression_min_bars",
            "max_signal_age_bars",
            "entry_window_bars",
        )
        for name in int_fields:
            _require_positive_int(getattr(self, name), f"thresholds.{name}")
        _require_real(self.min_volume_z, "thresholds.min_volume_z")
        for f in fields(self):
            if f.name not in int_fields and f.name != "min_volume_z":
                _require_nonnegative_real(getattr(self, f.name), f"thresholds.{f.name}")


@dataclass(frozen=True)
class MarketWatchGridConfig:
    grid_boundary_change_pct: float = 2.0
    default_grid_count: int = 10
    min_grid_profit_pct: float = 0.25
    atr_buffer_mult: float = 1.0
    max_trend_adx: float = 25.0

    def __post_init__(self) -> None:
        _require_positive_int(self.default_grid_count, "grid.default_grid_count")
        for name in ("grid_boundary_change_pct", "min_grid_profit_pct", "atr_buffer_mult", "max_trend_adx"):
            _require_nonnegative_real(getattr(self, name), f"grid.{name}")


@dataclass(frozen=True)
class MarketWatchConfig:
    enabled: bool = False
    symbols: tuple[str, ...] = DEFAULT_RELATIVE_STRENGTH_UNIVERSE
    benchmark_symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT")
    relative_strength_universe: tuple[str, ...] = DEFAULT_RELATIVE_STRENGTH_UNIVERSE
    scan_interval_minutes: int = 15
    fast_watch_interval_minutes: int = 5
    notify_only_on_change: bool = True
    max_alert_symbols: int = 3
    min_net_rr: float = 1.5
    high_quality_net_rr: float = 2.0
    min_action_entry_quality: str = "GOOD"
    min_alert_severity: str = "WATCH"
    feishu_enabled: bool = False
    sqlite_path: str = "./var/market_watch.db"
    taker_fee_rate: float = 0.0005
    maker_fee_rate: float = 0.0002
    slippage_bps_per_side: float = 2.0
    funding_stress_rate: float = 0.0005
    ranking: MarketWatchRankingConfig = field(default_factory=MarketWatchRankingConfig)
    thresholds: MarketWatchThresholdsConfig = field(default_factory=MarketWatchThresholdsConfig)
    grid: MarketWatchGridConfig = field(default_factory=MarketWatchGridConfig)

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise TypeError("market_watch.enabled must be a boolean")
        object.__setattr__(self, "symbols", canonicalize_symbols(self.symbols))
        object.__setattr__(self, "benchmark_symbols", canonicalize_symbols(self.benchmark_symbols))
        object.__setattr__(self, "relative_strength_universe", canonicalize_symbols(self.relative_strength_universe))
        if not self.symbols:
            raise ValueError("market_watch.symbols cannot be empty")
        if not self.relative_strength_universe:
            raise ValueError("market_watch.relative_strength_universe cannot be empty")
        for name in ("scan_interval_minutes", "fast_watch_interval_minutes", "max_alert_symbols"):
            _require_positive_int(getattr(self, name), f"market_watch.{name}")
        for name in ("min_net_rr", "high_quality_net_rr", "taker_fee_rate", "maker_fee_rate", "slippage_bps_per_side", "funding_stress_rate"):
            _require_nonnegative_real(getattr(self, name), f"market_watch.{name}")
        if self.min_action_entry_quality not in {"EXCELLENT", "GOOD", "MARGINAL", "POOR"}:
            raise ValueError("market_watch.min_action_entry_quality invalid")
        if self.min_alert_severity not in {"INFO", "WATCH", "ACTION", "RISK"}:
            raise ValueError("market_watch.min_alert_severity invalid")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def config_hash(self) -> str:
        return compute_market_watch_config_hash(self)


def compute_required_closed_bars(config: MarketWatchConfig) -> int:
    """Centralize required closed-bar history with deterministic engineering warmup margin."""
    existing_feature_required = 160  # level_lookback
    return max(existing_feature_required, config.thresholds.ema_slow + 50)


def compute_required_fetch_bars(config: MarketWatchConfig) -> int:
    """Request enough candles to tolerate a currently forming bar."""
    return compute_required_closed_bars(config) + 1


def build_market_watch_config(raw: dict[str, Any] | None) -> MarketWatchConfig:
    if not raw:
        return MarketWatchConfig()
    values = dict(raw)
    if "symbols" in values and isinstance(values["symbols"], (list, tuple)):
        values["symbols"] = tuple(values["symbols"])
    if "benchmark_symbols" in values and isinstance(values["benchmark_symbols"], (list, tuple)):
        values["benchmark_symbols"] = tuple(values["benchmark_symbols"])
    if "relative_strength_universe" in values and isinstance(values["relative_strength_universe"], (list, tuple)):
        values["relative_strength_universe"] = tuple(values["relative_strength_universe"])
    if "ranking" in values and isinstance(values["ranking"], dict):
        rk = dict(values["ranking"])
        # Support legacy configuration migration:
        # rs_weight_15m -> rs_weight_1h, rs_weight_1h -> rs_weight_4h, rs_weight_4h -> rs_weight_12h
        if "rs_weight_15m" in rk and "rs_weight_12h" not in rk:
            old_15m = rk.pop("rs_weight_15m")
            old_1h = rk.get("rs_weight_1h", 0.50)
            old_4h = rk.get("rs_weight_4h", 0.30)
            rk["rs_weight_1h"] = old_15m
            rk["rs_weight_4h"] = old_1h
            rk["rs_weight_12h"] = old_4h
        values["ranking"] = MarketWatchRankingConfig(**rk)
    if "thresholds" in values and isinstance(values["thresholds"], dict):
        values["thresholds"] = MarketWatchThresholdsConfig(**values["thresholds"])
    if "grid" in values and isinstance(values["grid"], dict):
        values["grid"] = MarketWatchGridConfig(**values["grid"])
    return MarketWatchConfig(**values)


def compute_market_watch_config_hash(config: MarketWatchConfig) -> str:
    """Compute deterministic audit hash for MarketWatch configuration.

    Isolated from global research config_hash. Changes when thresholds or parameters change.
    """
    payload = {
        "symbols": list(config.symbols),
        "benchmark_symbols": list(config.benchmark_symbols),
        "relative_strength_universe": list(config.relative_strength_universe),
        "scan_interval_minutes": config.scan_interval_minutes,
        "min_net_rr": config.min_net_rr,
        "high_quality_net_rr": config.high_quality_net_rr,
        "min_action_entry_quality": config.min_action_entry_quality,
        "min_alert_severity": config.min_alert_severity,
        "taker_fee_rate": config.taker_fee_rate,
        "maker_fee_rate": config.maker_fee_rate,
        "slippage_bps_per_side": config.slippage_bps_per_side,
        "funding_stress_rate": config.funding_stress_rate,
        "ranking": asdict(config.ranking),
        "thresholds": asdict(config.thresholds),
        "grid": asdict(config.grid),
    }
    raw = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
