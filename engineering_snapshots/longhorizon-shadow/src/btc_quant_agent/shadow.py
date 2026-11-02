from __future__ import annotations

import warnings
from collections.abc import Sequence

from .backtest import resolve_signal
from .config import BacktestConfig
from .domain import Candle, SignalStatus
from .formal_research import FormalResearchJobSpec, run_formal_job
from .storage import Repository

OUTCOME_STATUS = {
    "WIN": SignalStatus.RESOLVED_WIN,
    "LOSS": SignalStatus.RESOLVED_LOSS,
    "TIMEOUT": SignalStatus.RESOLVED_TIMEOUT,
    "UNFILLED": SignalStatus.EXPIRED,
}


def read_legacy_shadow_performance(
    repository: Repository, since_ms: int = 0,
) -> dict[str, object]:
    """Read historical R metrics without converting or promoting stored rows."""
    return {
        **repository.performance(since_ms),
        "classification": "LEGACY_DIAGNOSTIC_ONLY", "can_promote": False,
    }


def update_legacy_shadow(
    repository: Repository,
    bars: Sequence[Candle],
    now_ms: int,
    backtest_config: BacktestConfig | None = None,
) -> list[dict[str, object]]:
    """Compatibility-only resolver; old R rows are never current formal evidence."""
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


def update_shadow(
    repository: Repository,
    bars: Sequence[Candle],
    now_ms: int,
    backtest_config: BacktestConfig | None = None,
) -> list[dict[str, object]]:
    """Deprecated legacy-signature shim, retained for historical callers only."""
    warnings.warn(
        "shadow.update_shadow(repository, bars, now) is LEGACY_DIAGNOSTIC_ONLY; "
        "use update_formal_shadow with an explicit protocol/evidence job for current economics",
        DeprecationWarning, stacklevel=2,
    )
    return [
        {**row, "classification": "LEGACY_DIAGNOSTIC_ONLY", "can_promote": False}
        for row in update_legacy_shadow(repository, bars, now_ms, backtest_config)
    ]


def update_formal_shadow(
    spec: FormalResearchJobSpec, *, output_directory: str | None = None,
) -> list[dict[str, object]]:
    """Observation-supported formal replay, separate from old runtime shadow rows."""
    if output_directory is None:
        raise ValueError("formal shadow requires an explicit new artifact directory")
    from pathlib import Path

    result = run_formal_job(
        spec, output_directory=Path(output_directory) / "formal-shadow-v1",
    )
    return [{**result.status(), "consumer": "FORMAL_SHADOW_V1"}]
