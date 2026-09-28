"""Isolated operational multi-asset market watch and trading policy subsystem."""

from typing import TYPE_CHECKING, Any

from .config import MarketWatchConfig
from .domain import (
    AlertSeverity,
    BenchmarkContext,
    ConfidenceBand,
    DerivativesMetrics,
    DerivativesRegime,
    DirectionalDecision,
    DirectionalPlan,
    EntryQuality,
    ExhaustionMetrics,
    ExhaustionState,
    GridDecision,
    GridPlan,
    MarketSnapshot,
    MarketWatchAlert,
    PlaybookType,
    PriceMetrics,
    RelativePerformance,
    ScanHealth,
    SignalLifecycleState,
    SymbolAssessment,
    TimeframeSnapshot,
)

if TYPE_CHECKING:
    from .scanner import MarketWatchScanner
    from .service import MarketWatchService


def __getattr__(name: str) -> Any:
    if name == "MarketWatchScanner":
        from .scanner import MarketWatchScanner
        return MarketWatchScanner
    if name == "MarketWatchService":
        from .service import MarketWatchService
        return MarketWatchService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "AlertSeverity",
    "BenchmarkContext",
    "ConfidenceBand",
    "DerivativesMetrics",
    "DerivativesRegime",
    "DirectionalDecision",
    "DirectionalPlan",
    "EntryQuality",
    "ExhaustionMetrics",
    "ExhaustionState",
    "GridDecision",
    "GridPlan",
    "MarketSnapshot",
    "MarketWatchAlert",
    "MarketWatchConfig",
    "MarketWatchScanner",
    "MarketWatchService",
    "PlaybookType",
    "PriceMetrics",
    "RelativePerformance",
    "ScanHealth",
    "SignalLifecycleState",
    "SymbolAssessment",
    "TimeframeSnapshot",
]
