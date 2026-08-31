from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import time
from collections import Counter
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import AppConfig
from .data.binance import BinancePublicClient
from .domain import RuntimeStage, ScanResult
from .research_registry import ResearchRegistry
from .service import QuantService

CADENCE_MS = 15 * 60_000
DAY_MS = 24 * 60 * 60_000
HORIZONS = (240, 480)
MAX_CONTROLS = 5


class OpportunityForwardConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class OpportunityCampaign:
    campaign_id: str
    campaign_start_ms: int
    start_git_sha: str
    registry_version: str
    strategy_version: str
    feature_version: str
    config_hash: str
    symbol: str
    detector_ids: tuple[str, ...]
    seed: int

    @classmethod
    def load(cls, path: str | Path) -> OpportunityCampaign:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if raw["normal_runtime_mode"] != "RUNTIME_GATED":
            raise ValueError("opportunity campaign requires RUNTIME_GATED")
        if raw["direction_claim"] != "NONE" or raw["immutability"]["execution"] != "DISABLED":
            raise ValueError("opportunity campaign violates direction/execution firewall")
        if tuple(raw["movement_horizons_minutes"]) != HORIZONS:
            raise ValueError("opportunity campaign horizons changed")
        return cls(
            campaign_id=str(raw["campaign_id"]),
            campaign_start_ms=int(raw["campaign_start_ms"]),
            start_git_sha=str(raw["start_git_sha"]),
            registry_version=str(raw["registry_version"]),
            strategy_version=str(raw["strategy_version"]),
            feature_version=str(raw["feature_version"]),
            config_hash=str(raw["config_hash"]),
            symbol=str(raw["symbol"]),
            detector_ids=tuple(str(value) for value in raw["detector_ids"]),
            seed=int(raw["h35"]["seed"]),
        )


@dataclass(frozen=True)
class ForwardObservation:
    observation_id: str
    campaign_id: str
    scheduled_slot_ms: int
    collection_started_at_ms: int
    observed_at_ms: int
    status: str
    market_data_health: str
    decision_close_ms: int | None
    regime: str | None
    atr_15m: float | None
    atr_percentile_decile: int | None
    opportunity_present: bool
    opportunity_id: str | None
    detector_id: str | None
    setup: str | None
    registry_version: str
    git_sha: str
    config_hash: str
    network_data_errors: tuple[str, ...]
    payload_hash: str

    @classmethod
    def create(
        cls,
        *,
        campaign: OpportunityCampaign,
        scheduled_slot_ms: int,
        collection_started_at_ms: int,
        observed_at_ms: int,
        status: str,
        market_data_health: str,
        decision_close_ms: int | None,
        regime: str | None,
        atr_15m: float | None,
        atr_percentile_decile: int | None,
        opportunity_id: str | None,
        detector_id: str | None,
        setup: str | None,
        registry_version: str,
        git_sha: str,
        config_hash: str,
        network_data_errors: Sequence[str] = (),
    ) -> ForwardObservation:
        payload = {
            "campaign_id": campaign.campaign_id,
            "scheduled_slot_ms": scheduled_slot_ms,
            "collection_started_at_ms": collection_started_at_ms,
            "observed_at_ms": observed_at_ms,
            "status": status,
            "market_data_health": market_data_health,
            "decision_close_ms": decision_close_ms,
            "regime": regime,
            "atr_15m": atr_15m,
            "atr_percentile_decile": atr_percentile_decile,
            "opportunity_id": opportunity_id,
            "detector_id": detector_id,
            "setup": setup,
            "registry_version": registry_version,
            "git_sha": git_sha,
            "config_hash": config_hash,
            "network_data_errors": tuple(network_data_errors),
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        identity = hashlib.sha256(
            f"{campaign.campaign_id}:{scheduled_slot_ms}".encode()
        ).hexdigest()[:24]
        return cls(
            observation_id=f"OBS:{identity}",
            campaign_id=campaign.campaign_id,
            scheduled_slot_ms=scheduled_slot_ms,
            collection_started_at_ms=collection_started_at_ms,
            observed_at_ms=observed_at_ms,
            status=status,
            market_data_health=market_data_health,
            decision_close_ms=decision_close_ms,
            regime=regime,
            atr_15m=atr_15m,
            atr_percentile_decile=atr_percentile_decile,
            opportunity_id=opportunity_id,
            opportunity_present=opportunity_id is not None,
            detector_id=detector_id,
            setup=setup,
            registry_version=registry_version,
            git_sha=git_sha,
            config_hash=config_hash,
            network_data_errors=tuple(network_data_errors),
            payload_hash=digest,
        )


class OpportunityForwardStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=10000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS scan_observations (
                    observation_id TEXT PRIMARY KEY,
                    campaign_id TEXT NOT NULL,
                    scheduled_slot_ms INTEGER NOT NULL,
                    collection_started_at_ms INTEGER NOT NULL,
                    observed_at_ms INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    market_data_health TEXT NOT NULL,
                    decision_close_ms INTEGER,
                    regime TEXT,
                    atr_15m REAL,
                    atr_percentile_decile INTEGER,
                    opportunity_present INTEGER NOT NULL,
                    opportunity_id TEXT,
                    detector_id TEXT,
                    setup TEXT,
                    registry_version TEXT NOT NULL,
                    git_sha TEXT NOT NULL,
                    config_hash TEXT NOT NULL,
                    network_data_errors_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    UNIQUE(campaign_id, scheduled_slot_ms)
                );
                CREATE TABLE IF NOT EXISTS outcomes (
                    observation_id TEXT NOT NULL,
                    horizon_minutes INTEGER NOT NULL,
                    reference_time_ms INTEGER NOT NULL,
                    reference_price REAL NOT NULL,
                    future_high REAL NOT NULL,
                    future_low REAL NOT NULL,
                    future_close REAL NOT NULL,
                    future_range_atr REAL NOT NULL,
                    max_up_excursion_atr REAL NOT NULL,
                    max_down_excursion_atr REAL NOT NULL,
                    max_abs_excursion_atr REAL NOT NULL,
                    resolved_at_ms INTEGER NOT NULL,
                    resolution_source TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    PRIMARY KEY(observation_id, horizon_minutes),
                    FOREIGN KEY(observation_id) REFERENCES scan_observations(observation_id)
                );
                CREATE TABLE IF NOT EXISTS integrity_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    occurred_at_ms INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    observation_id TEXT NOT NULL
                );
                """
            )

    def append_observation(self, observation: ForwardObservation) -> bool:
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT payload_hash FROM scan_observations WHERE campaign_id=? "
                "AND scheduled_slot_ms=?",
                (observation.campaign_id, observation.scheduled_slot_ms),
            ).fetchone()
            if existing is not None:
                exact = str(existing["payload_hash"]) == observation.payload_hash
                connection.execute(
                    "INSERT INTO integrity_events(occurred_at_ms,kind,observation_id) VALUES(?,?,?)",
                    (
                        int(time.time() * 1_000),
                        "DUPLICATE" if exact else "CONFLICT",
                        observation.observation_id,
                    ),
                )
                if not exact:
                    raise OpportunityForwardConflict(
                        "scheduled slot is immutable; missed/successful observation cannot be replaced"
                    )
                return False
            connection.execute(
                "INSERT INTO scan_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    observation.observation_id,
                    observation.campaign_id,
                    observation.scheduled_slot_ms,
                    observation.collection_started_at_ms,
                    observation.observed_at_ms,
                    observation.status,
                    observation.market_data_health,
                    observation.decision_close_ms,
                    observation.regime,
                    observation.atr_15m,
                    observation.atr_percentile_decile,
                    int(observation.opportunity_present),
                    observation.opportunity_id,
                    observation.detector_id,
                    observation.setup,
                    observation.registry_version,
                    observation.git_sha,
                    observation.config_hash,
                    json.dumps(observation.network_data_errors),
                    observation.payload_hash,
                ),
            )
        return True

    def append_outcome(self, outcome: dict[str, Any]) -> bool:
        payload = {key: value for key, value in outcome.items() if key != "payload_hash"}
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        values = {**payload, "payload_hash": digest}
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT payload_hash FROM outcomes WHERE observation_id=? AND horizon_minutes=?",
                (values["observation_id"], values["horizon_minutes"]),
            ).fetchone()
            if existing is not None:
                if str(existing["payload_hash"]) != digest:
                    raise OpportunityForwardConflict("resolved outcome conflict; original preserved")
                return False
            connection.execute(
                "INSERT INTO outcomes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                tuple(
                    values[key]
                    for key in (
                        "observation_id",
                        "horizon_minutes",
                        "reference_time_ms",
                        "reference_price",
                        "future_high",
                        "future_low",
                        "future_close",
                        "future_range_atr",
                        "max_up_excursion_atr",
                        "max_down_excursion_atr",
                        "max_abs_excursion_atr",
                        "resolved_at_ms",
                        "resolution_source",
                        "payload_hash",
                    )
                ),
            )
        return True

    def observations(self, campaign_id: str) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM scan_observations WHERE campaign_id=? ORDER BY scheduled_slot_ms",
                (campaign_id,),
            ).fetchall()

    def outcomes(self) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM outcomes ORDER BY observation_id,horizon_minutes"
            ).fetchall()

    def unresolved(self, campaign_id: str, now_ms: int) -> list[tuple[sqlite3.Row, int]]:
        observations = [
            row
            for row in self.observations(campaign_id)
            if row["status"] == "SUCCESSFUL_SCAN" and row["decision_close_ms"] is not None
        ]
        existing = {(str(row["observation_id"]), int(row["horizon_minutes"])) for row in self.outcomes()}
        return [
            (row, horizon)
            for row in observations
            for horizon in HORIZONS
            if (str(row["observation_id"]), horizon) not in existing
            and int(row["decision_close_ms"]) + 1 + horizon * 60_000 <= now_ms
        ]

    def control_matches(self, campaign_id: str, horizon: int) -> list[dict[str, Any]]:
        observations = {str(row["observation_id"]): row for row in self.observations(campaign_id)}
        outcomes = {
            str(row["observation_id"]): row
            for row in self.outcomes()
            if int(row["horizon_minutes"]) == horizon
            and str(row["observation_id"]) in observations
        }
        candidates = [
            row
            for identity, row in observations.items()
            if bool(row["opportunity_present"]) and identity in outcomes
        ]
        controls = [
            row
            for identity, row in observations.items()
            if not bool(row["opportunity_present"]) and identity in outcomes
        ]
        matches: list[dict[str, Any]] = []
        for candidate in candidates:
            timestamp = int(candidate["scheduled_slot_ms"])
            month = datetime.fromtimestamp(timestamp / 1_000, UTC).strftime("%Y-%m")
            eligible = [
                row
                for row in controls
                if row["regime"] == candidate["regime"]
                and row["atr_percentile_decile"] == candidate["atr_percentile_decile"]
                and abs(int(row["scheduled_slot_ms"]) - timestamp) >= DAY_MS
            ]
            chosen = sorted(
                eligible,
                key=lambda row: (
                    datetime.fromtimestamp(
                        int(row["scheduled_slot_ms"]) / 1_000, UTC
                    ).strftime("%Y-%m")
                    != month,
                    abs(int(row["scheduled_slot_ms"]) - timestamp),
                    int(row["scheduled_slot_ms"]),
                ),
            )[:MAX_CONTROLS]
            for rank, control in enumerate(chosen, 1):
                matches.append(
                    {
                        "candidate_observation_id": candidate["observation_id"],
                        "control_observation_id": control["observation_id"],
                        "horizon_minutes": horizon,
                        "rank": rank,
                        "time_separation_hours": abs(
                            int(control["scheduled_slot_ms"]) - timestamp
                        )
                        / 3_600_000,
                        "candidate_future_range_atr": float(
                            outcomes[str(candidate["observation_id"])]["future_range_atr"]
                        ),
                        "control_future_range_atr": float(
                            outcomes[str(control["observation_id"])]["future_range_atr"]
                        ),
                    }
                )
        return matches

    def audit(self, campaign_id: str) -> dict[str, Any]:
        rows = self.observations(campaign_id)
        slots = [int(row["scheduled_slot_ms"]) for row in rows]
        with self._connect() as connection:
            events = connection.execute(
                "SELECT kind,COUNT(*) n FROM integrity_events GROUP BY kind"
            ).fetchall()
            columns = [
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(scan_observations)").fetchall()
            ]
        return {
            "campaign_id": campaign_id,
            "observation_count": len(rows),
            "scheduled_slots_ordered": slots == sorted(slots),
            "duplicate_slot_count": len(slots) - len(set(slots)),
            "integrity_events": {str(row["kind"]): int(row["n"]) for row in events},
            "missed_slots_are_immutable": True,
            "retrospective_feature_backfill_rows": 0,
            "outcome_resolution_is_separate": True,
            "direction_action_columns": [
                name for name in columns if name in {"direction", "signal", "entry", "stop", "size"}
            ],
        }

    def status(
        self,
        campaign: OpportunityCampaign,
        *,
        scheduler: dict[str, Any] | None = None,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        now = now_ms or int(time.time() * 1_000)
        rows = self.observations(campaign.campaign_id)
        outcomes = self.outcomes()
        successful = [row for row in rows if row["status"] == "SUCCESSFUL_SCAN"]
        opportunities = [row for row in successful if bool(row["opportunity_present"])]
        resolved = {
            horizon: {
                str(row["observation_id"])
                for row in outcomes
                if int(row["horizon_minutes"]) == horizon
            }
            for horizon in HORIZONS
        }
        matches = {horizon: self.control_matches(campaign.campaign_id, horizon) for horizon in HORIZONS}
        opportunity_resolved_8h = [
            row for row in opportunities if str(row["observation_id"]) in resolved[480]
        ]
        unique_controls = {
            str(row["control_observation_id"]) for rows_for_horizon in matches.values() for row in rows_for_horizon
        }
        distinct_days = {
            datetime.fromtimestamp(int(row["scheduled_slot_ms"]) / 1_000, UTC).strftime("%Y-%m-%d")
            for row in successful
            if str(row["observation_id"]) in resolved[480]
        }
        age_days = max(0.0, (now - campaign.campaign_start_ms) / 86_400_000)
        evaluable = (
            len(opportunity_resolved_8h) >= 30
            and age_days >= 30
            and len(unique_controls) >= 100
            and len(distinct_days) >= 20
        )
        return {
            "campaign_id": campaign.campaign_id,
            "campaign_start_ms": campaign.campaign_start_ms,
            "campaign_age_days": age_days,
            "scheduler_detected": bool((scheduler or {}).get("detected", False)),
            "scheduler_active": bool((scheduler or {}).get("active", False)),
            "scheduled_slots_recorded": len(rows),
            "successful_scans": len(successful),
            "missed_decision_slots": sum(row["status"] == "MISSED_DECISION_SLOT" for row in rows),
            "opportunity_count": len(opportunities),
            "tp_count": sum(row["detector_id"] == "trend_pullback_opportunity" for row in opportunities),
            "br_count": sum(row["detector_id"] == "breakout_retest_opportunity" for row in opportunities),
            "resolved_4h_opportunity_count": sum(
                str(row["observation_id"]) in resolved[240] for row in opportunities
            ),
            "resolved_8h_opportunity_count": len(opportunity_resolved_8h),
            "unique_eligible_controls": len(unique_controls),
            "matched_pairs": {f"{horizon}m": len(matches[horizon]) for horizon in HORIZONS},
            "control_reuse_distribution": {
                f"{horizon}m": dict(
                    sorted(
                        Counter(
                            Counter(
                                str(row["control_observation_id"])
                                for row in matches[horizon]
                            ).values()
                        ).items()
                    )
                )
                for horizon in HORIZONS
            },
            "h35_state": "EVALUABLE" if evaluable else "FORWARD_CAMPAIGN_ACCUMULATING",
            "h35_gate": {
                "minimum_resolved_opportunities": 30,
                "preferred_resolved_opportunities": 50,
                "minimum_calendar_days": 30,
                "minimum_unique_matched_controls": 100,
                "minimum_distinct_utc_days": 20,
                "distinct_resolved_days": len(distinct_days),
            },
            "direction_claim": "NONE",
            "execution": "DISABLED",
        }


def _git_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def _timer_status(unit: str) -> dict[str, Any]:
    try:
        enabled = subprocess.run(
            ["systemctl", "--user", "is-enabled", unit],
            capture_output=True,
            check=False,
            timeout=5,
        ).returncode == 0
        active = subprocess.run(
            ["systemctl", "--user", "is-active", unit],
            capture_output=True,
            check=False,
            timeout=5,
        ).returncode == 0
        return {"unit": unit, "detected": enabled, "active": active}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"unit": unit, "detected": False, "active": False, "error": str(exc)}


def opportunity_scheduler_status() -> dict[str, Any]:
    return _timer_status("btc-quant-opportunity-forward.timer")


def opportunity_resolver_scheduler_status() -> dict[str, Any]:
    return _timer_status("btc-quant-opportunity-resolve.timer")


def collect_opportunity_once(
    service: QuantService,
    store: OpportunityForwardStore,
    campaign: OpportunityCampaign,
    *,
    now_ms: int | None = None,
) -> ForwardObservation:
    started = now_ms or int(time.time() * 1_000)
    scheduled_slot = (started // CADENCE_MS) * CADENCE_MS
    registry = ResearchRegistry.load()
    if registry.registry_version != campaign.registry_version:
        raise ValueError("campaign registry version mismatch; start a new campaign")
    if service.config.config_hash != campaign.config_hash:
        raise ValueError("campaign config hash mismatch; start a new campaign")
    try:
        result = service.scan(campaign.symbol, notify=False)
        if result.signal is not None or result.runtime_stage not in {
            RuntimeStage.NO_OPPORTUNITY,
            RuntimeStage.OPPORTUNITY_ONLY,
        }:
            raise RuntimeError("opportunity forward scan attempted actionable Direction")
        if result.health != "OK":
            raise RuntimeError(
                f"runtime scan unavailable: {result.reason_code}: {result.reason}"
            )
        observation = observation_from_scan(
            result,
            campaign,
            scheduled_slot_ms=scheduled_slot,
            collection_started_at_ms=started,
            observed_at_ms=int(time.time() * 1_000),
            config=service.config,
            git_sha=_git_sha(),
        )
    except Exception as exc:  # noqa: BLE001 - missed real slot must be durably recorded
        observation = ForwardObservation.create(
            campaign=campaign,
            scheduled_slot_ms=scheduled_slot,
            collection_started_at_ms=started,
            observed_at_ms=int(time.time() * 1_000),
            status="MISSED_DECISION_SLOT",
            market_data_health="UNAVAILABLE",
            decision_close_ms=None,
            regime=None,
            atr_15m=None,
            atr_percentile_decile=None,
            opportunity_id=None,
            detector_id=None,
            setup=None,
            registry_version=campaign.registry_version,
            git_sha=_git_sha(),
            config_hash=service.config.config_hash,
            network_data_errors=(f"{type(exc).__name__}: {exc}",),
        )
    store.append_observation(observation)
    return observation


def observation_from_scan(
    result: ScanResult,
    campaign: OpportunityCampaign,
    *,
    scheduled_slot_ms: int,
    collection_started_at_ms: int,
    observed_at_ms: int,
    config: AppConfig,
    git_sha: str,
) -> ForwardObservation:
    if result.health != "OK":
        raise ValueError(f"unhealthy runtime scan: {result.reason_code}: {result.reason}")
    if result.signal is not None or result.action in {"LONG", "SHORT"}:
        raise ValueError("opportunity campaign cannot accept an actionable signal")
    diagnostics = result.diagnostics
    opportunity = result.opportunity
    detector = opportunity.detector_id if opportunity else None
    if detector is not None and detector not in campaign.detector_ids:
        raise ValueError("unfrozen opportunity detector")
    return ForwardObservation.create(
        campaign=campaign,
        scheduled_slot_ms=scheduled_slot_ms,
        collection_started_at_ms=collection_started_at_ms,
        observed_at_ms=observed_at_ms,
        status="SUCCESSFUL_SCAN",
        market_data_health=result.health,
        decision_close_ms=int(diagnostics["decision_close_ms"]),
        regime=str(diagnostics["regime"]),
        atr_15m=float(diagnostics["atr"]),
        atr_percentile_decile=int(diagnostics["atr_percentile_decile"]),
        opportunity_id=opportunity.opportunity_id if opportunity else None,
        detector_id=detector,
        setup=opportunity.setup.value if opportunity else None,
        registry_version=campaign.registry_version,
        git_sha=git_sha,
        config_hash=config.config_hash,
    )


def movement_outcome(
    observation: sqlite3.Row | dict[str, Any],
    horizon: int,
    candles: Sequence[Any],
    *,
    resolved_at_ms: int,
) -> dict[str, Any]:
    decision_close = int(observation["decision_close_ms"])
    expected_first = decision_close + 1
    if (
        len(candles) != horizon
        or int(candles[0].open_time_ms) != expected_first
        or int(candles[-1].open_time_ms) - int(candles[0].open_time_ms)
        != (horizon - 1) * 60_000
    ):
        raise ValueError("outcome window is incomplete or not the strict next-open window")
    atr = float(observation["atr_15m"])
    if atr <= 0:
        raise ValueError("frozen forward ATR must be positive")
    reference = float(candles[0].open)
    high = max(float(row.high) for row in candles)
    low = min(float(row.low) for row in candles)
    up = max(0.0, high - reference) / atr
    down = max(0.0, reference - low) / atr
    return {
        "observation_id": str(observation["observation_id"]),
        "horizon_minutes": horizon,
        "reference_time_ms": int(candles[0].open_time_ms),
        "reference_price": reference,
        "future_high": high,
        "future_low": low,
        "future_close": float(candles[-1].close),
        "future_range_atr": (high - low) / atr,
        "max_up_excursion_atr": up,
        "max_down_excursion_atr": down,
        "max_abs_excursion_atr": max(up, down),
        "resolved_at_ms": resolved_at_ms,
        "resolution_source": "Binance USD-M public REST 1m deterministic post-event label",
    }


def resolve_opportunity_outcomes(
    client: BinancePublicClient,
    store: OpportunityForwardStore,
    campaign: OpportunityCampaign,
    *,
    now_ms: int | None = None,
) -> dict[str, Any]:
    now = now_ms or int(time.time() * 1_000)
    resolved = failed = 0
    errors: list[str] = []
    for observation, horizon in store.unresolved(campaign.campaign_id, now):
        first_open = int(observation["decision_close_ms"]) + 1
        try:
            candles = client.historical_klines(
                campaign.symbol,
                "1m",
                first_open,
                first_open + horizon * 60_000 - 1,
            )
            store.append_outcome(
                movement_outcome(observation, horizon, candles, resolved_at_ms=now)
            )
            resolved += 1
        except Exception as exc:  # noqa: BLE001 - unresolved label remains retryable
            failed += 1
            errors.append(f"{observation['observation_id']}:{horizon}:{type(exc).__name__}")
    return {"resolved": resolved, "failed": failed, "errors": errors}
