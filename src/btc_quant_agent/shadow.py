from __future__ import annotations

from collections.abc import Sequence

from .backtest import resolve_signal
from .config import BacktestConfig
from .domain import Candle, SignalStatus
from .storage import Repository

OUTCOME_STATUS = {
    "WIN": SignalStatus.RESOLVED_WIN,
    "LOSS": SignalStatus.RESOLVED_LOSS,
    "TIMEOUT": SignalStatus.RESOLVED_TIMEOUT,
    "UNFILLED": SignalStatus.EXPIRED,
}


def update_shadow(
    repository: Repository,
    bars: Sequence[Candle],
    now_ms: int,
    backtest_config: BacktestConfig | None = None,
) -> list[dict[str, object]]:
    resolved: list[dict[str, object]] = []
    for signal in repository.active_signals():
        outcome = resolve_signal(signal, bars, as_of_ms=now_ms, backtest_config=backtest_config)
        if outcome.outcome == "PENDING":
            continue
        payload = outcome.as_dict()
        repository.save_shadow(signal.signal_id, payload)
        repository.update_signal_status(signal.signal_id, OUTCOME_STATUS[outcome.outcome])
        resolved.append(payload)
    return resolved
