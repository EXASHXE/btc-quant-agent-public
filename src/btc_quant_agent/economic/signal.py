from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class InformationSignal:
    """Pure informational forecast resulting from statistical research.

    Inviolate Rule: An InformationSignal contains ZERO execution parameters.
    It represents what the quantitative model forecasts, not how to execute a trade.
    """

    signal_id: str
    experiment_id: str
    timestamp_ms: int
    asset: str = "BTCUSDT"
    direction: int = 1  # +1 = upward / positive drift, -1 = downward / negative drift, 0 = neutral
    strength: float = 1.0  # normalized signal magnitude (e.g. z-score, basis points)
    confidence_interval: tuple[float, float] | None = None
    horizon_ms: int = 3_600_000  # expected informational validity window (e.g., 60m)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.signal_id:
            raise ValueError("signal_id cannot be empty")
        if not self.experiment_id:
            raise ValueError("experiment_id cannot be empty")
        if self.timestamp_ms <= 0:
            raise ValueError("timestamp_ms must be positive")
        if self.direction not in (-1, 0, 1):
            raise ValueError(f"direction must be -1, 0, or 1; got {self.direction}")
        if self.horizon_ms <= 0:
            raise ValueError(f"horizon_ms must be positive; got {self.horizon_ms}")

    @property
    def is_actionable(self) -> bool:
        return self.direction != 0 and self.strength != 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InformationSignal:
        ci = data.get("confidence_interval")
        ci_tuple = tuple(ci) if isinstance(ci, (list, tuple)) and len(ci) == 2 else None
        return cls(
            signal_id=str(data["signal_id"]),
            experiment_id=str(data["experiment_id"]),
            timestamp_ms=int(data["timestamp_ms"]),
            asset=str(data.get("asset", "BTCUSDT")),
            direction=int(data.get("direction", 1)),
            strength=float(data.get("strength", 1.0)),
            confidence_interval=ci_tuple,
            horizon_ms=int(data.get("horizon_ms", 3_600_000)),
            metadata=dict(data.get("metadata", {})),
        )
