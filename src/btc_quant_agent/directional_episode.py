from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EpisodeAccumulator:
    """Causally collapse consecutive identical 1h trend states into episodes."""

    rows: list[dict[str, Any]] = field(default_factory=list)
    previous_regime: str | None = None
    active_index: int | None = None
    last_1h_close_ms: int | None = None

    def add(self, snapshot: dict[str, Any]) -> None:
        close_ms = int(snapshot["feature_1h_close_ms"])
        if close_ms == self.last_1h_close_ms:
            return
        regime = str(snapshot["regime"])
        if regime in {"TREND_UP", "TREND_DOWN"}:
            if regime != self.previous_regime:
                row = dict(snapshot)
                row["end_close_ms"] = close_ms
                row["duration_bars"] = 1
                row["duration_hours"] = 1
                self.rows.append(row)
                self.active_index = len(self.rows) - 1
            elif self.active_index is not None:
                row = self.rows[self.active_index]
                row["end_close_ms"] = close_ms
                row["duration_bars"] = int(row["duration_bars"]) + 1
                row["duration_hours"] = int(row["duration_bars"])
        else:
            self.active_index = None
        self.previous_regime = regime
        self.last_1h_close_ms = close_ms
