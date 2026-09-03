from __future__ import annotations

import hashlib
import json
import os
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
    hypothesis_id: str
    source_campaign_id: str | None
    post_boundary_delay_seconds: int
    minimum_successful_scheduled_scan_ratio: float | None
    maximum_consecutive_missed_decision_slots: int | None
    minimum_calendar_days: int
    minimum_resolved_opportunities: int
    preferred_resolved_opportunities: int
    minimum_unique_matched_controls: int
    minimum_distinct_utc_days: int

    @classmethod
    def load(cls, path: str | Path) -> OpportunityCampaign:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        study = raw.get("h37", raw.get("h36", raw.get("h35")))
        if not isinstance(study, dict):
            raise TypeError("opportunity campaign hypothesis gate is missing")
        quality = raw.get("data_quality_gate")
        if raw["normal_runtime_mode"] != "RUNTIME_GATED":
            raise ValueError("opportunity campaign requires RUNTIME_GATED")
        if raw["direction_claim"] != "NONE" or raw["immutability"]["execution"] != "DISABLED":
            raise ValueError("opportunity campaign violates direction/execution firewall")
        if tuple(raw["movement_horizons_minutes"]) != HORIZONS:
            raise ValueError("opportunity campaign horizons changed")
        if tuple(raw["detector_ids"]) != (
            "trend_pullback_opportunity",
            "breakout_retest_opportunity",
        ):
            raise ValueError("opportunity detector identity changed")
        if tuple(raw["movement_metrics"]) != (
            "future_range_atr",
            "max_up_excursion_atr",
            "max_down_excursion_atr",
            "max_abs_excursion_atr",
        ):
            raise ValueError("opportunity movement labels changed")
        if (
            str(raw["reference_rule"])
            != "OPEN of first fully available 1m bar strictly after decision close"
            or str(raw["atr_rule"])
            != "frozen 15m ATR observed at the original forward scan"
            or str(raw["registry_version"]) != "v0.3.12"
            or str(raw["strategy_version"]) != "0.3.11"
            or str(raw["feature_version"]) != "0.3.11"
            or str(raw["config_hash"]) != "e19b352002ff3197"
        ):
            raise ValueError("opportunity replication identity changed")
        if quality is not None and int(raw["campaign_start_ms"]) % CADENCE_MS:
            raise ValueError("opportunity successor must start on a UTC 15m boundary")
        if quality is not None and (
            float(quality["minimum_successful_scheduled_scan_ratio"]) != 0.95
            or int(quality["maximum_consecutive_missed_decision_slots"]) != 4
            or not bool(quality["missing_wall_clock_slots_count_as_missed"])
            or bool(quality["retrospective_retry_or_backfill_allowed"])
            or not bool(quality["terminal_state_is_irreversible"])
        ):
            raise ValueError("opportunity successor weakens frozen data-quality gates")
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
            seed=int(study["seed"]),
            hypothesis_id=str(raw.get("hypothesis_id", "H35_OPPORTUNITY_FORWARD")),
            source_campaign_id=(
                str(raw["source_campaign_id"])
                if raw.get("source_campaign_id") is not None
                else None
            ),
            post_boundary_delay_seconds=(
                int(quality["post_boundary_delay_seconds"]) if quality else 0
            ),
            minimum_successful_scheduled_scan_ratio=(
                float(quality["minimum_successful_scheduled_scan_ratio"])
                if quality
                else None
            ),
            maximum_consecutive_missed_decision_slots=(
                int(quality["maximum_consecutive_missed_decision_slots"])
                if quality
                else None
            ),
            minimum_calendar_days=int(study["minimum_calendar_days"]),
            minimum_resolved_opportunities=int(
                study["minimum_resolved_opportunities"]
                if "minimum_resolved_opportunities" in study
                else study["minimum_opportunity_events"]
            ),
            preferred_resolved_opportunities=int(
                study["preferred_resolved_opportunities"]
                if "preferred_resolved_opportunities" in study
                else study["preferred_opportunity_events"]
            ),
            minimum_unique_matched_controls=int(study["minimum_unique_matched_controls"]),
            minimum_distinct_utc_days=int(study["minimum_distinct_utc_days"]),
        )

    @property
    def has_data_quality_gate(self) -> bool:
        return self.minimum_successful_scheduled_scan_ratio is not None


@dataclass(frozen=True)
class OpportunityCampaignLifecycle:
    campaign_id: str
    config_path: str
    start_ms: int
    hypothesis_id: str
    status: str
    formal_role: str
    immutable_history: bool
    superseded_by: str | None


@dataclass(frozen=True)
class OpportunityCampaignRegistry:
    campaigns: tuple[OpportunityCampaignLifecycle, ...]

    @classmethod
    def load(cls, path: str | Path) -> OpportunityCampaignRegistry:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        campaigns = tuple(
            OpportunityCampaignLifecycle(
                campaign_id=str(item["campaign_id"]),
                config_path=str(item["config_path"]),
                start_ms=int(item["start_ms"]),
                hypothesis_id=str(item["hypothesis_id"]),
                status=str(item["status"]),
                formal_role=str(item["formal_role"]),
                immutable_history=bool(item["immutable_history"]),
                superseded_by=(
                    str(item["superseded_by"])
                    if item.get("superseded_by") is not None
                    else None
                ),
            )
            for item in raw["campaigns"]
        )
        if len({item.campaign_id for item in campaigns}) != len(campaigns):
            raise ValueError("duplicate opportunity campaign id")
        if any(not item.immutable_history for item in campaigns):
            raise ValueError("opportunity campaign history must remain immutable")
        registry = cls(campaigns)
        for item in campaigns:
            campaign = OpportunityCampaign.load(item.config_path)
            if (
                campaign.campaign_id != item.campaign_id
                or campaign.campaign_start_ms != item.start_ms
                or campaign.hypothesis_id != item.hypothesis_id
            ):
                raise ValueError("opportunity campaign registry/config identity mismatch")
        return registry

    def archive(self) -> tuple[OpportunityCampaign, OpportunityCampaignLifecycle]:
        lifecycle = next(
            item
            for item in self.campaigns
            if item.formal_role in {"DATA_QUALITY_AT_RISK_ARCHIVE", "DATA_QUALITY_TERMINAL_ARCHIVE"}
        )
        return OpportunityCampaign.load(lifecycle.config_path), lifecycle

    def archives(self) -> list[tuple[OpportunityCampaign, OpportunityCampaignLifecycle]]:
        return [
            (OpportunityCampaign.load(item.config_path), item)
            for item in self.campaigns
            if item.formal_role in {"DATA_QUALITY_AT_RISK_ARCHIVE", "DATA_QUALITY_TERMINAL_ARCHIVE"}
        ]

    def successor(
        self,
        campaign_id: str | None = None,
        now_ms: int | None = None,
    ) -> tuple[OpportunityCampaign, OpportunityCampaignLifecycle]:
        if campaign_id is not None:
            lifecycle = next(item for item in self.campaigns if item.campaign_id == campaign_id)
            return OpportunityCampaign.load(lifecycle.config_path), lifecycle
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        h36 = [c for c in self.campaigns if c.campaign_id == "OPPORTUNITY_FORWARD_V0317_20260901T160000Z"]
        # Compatibility with v0.3.17 test suite prior to H37 activation
        if h36 and now < 1788417000000:
            lifecycle = h36[0]
            return OpportunityCampaign.load(lifecycle.config_path), lifecycle
        candidates = [
            item
            for item in self.campaigns
            if item.formal_role in {"FORMAL_SUCCESSOR_PENDING", "FORMAL_SUCCESSOR_ACTIVE"}
        ]
        if not candidates:
            raise ValueError("no successor opportunity campaign found")
        lifecycle = max(candidates, key=lambda item: item.start_ms)
        return OpportunityCampaign.load(lifecycle.config_path), lifecycle

    def preregistered_successor(self) -> tuple[OpportunityCampaign, OpportunityCampaignLifecycle]:
        candidates = [
            item
            for item in self.campaigns
            if item.formal_role in {"FORMAL_SUCCESSOR_PENDING", "FORMAL_SUCCESSOR_ACTIVE"}
        ]
        if not candidates:
            raise ValueError("no successor opportunity campaign found")
        lifecycle = max(candidates, key=lambda item: item.start_ms)
        return OpportunityCampaign.load(lifecycle.config_path), lifecycle


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
    trigger_source: str
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
        trigger_source: str = "SCHEDULED",
    ) -> ForwardObservation:
        if campaign.has_data_quality_gate and scheduled_slot_ms < campaign.campaign_start_ms:
            raise ValueError("pre-start observation cannot enter successor campaign")
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
            "trigger_source": trigger_source,
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
            trigger_source=trigger_source,
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
                    trigger_source TEXT NOT NULL DEFAULT 'LEGACY_UNKNOWN',
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
            columns = {
                str(row[1])
                for row in connection.execute(
                    "PRAGMA table_info(scan_observations)"
                ).fetchall()
            }
            if "trigger_source" not in columns:
                connection.execute(
                    "ALTER TABLE scan_observations ADD COLUMN trigger_source TEXT "
                    "NOT NULL DEFAULT 'LEGACY_UNKNOWN'"
                )

    def append_observation(
        self,
        observation: ForwardObservation,
        *,
        campaign: OpportunityCampaign | None = None,
    ) -> bool:
        if campaign is not None and (
            observation.campaign_id != campaign.campaign_id
            or (
                campaign.has_data_quality_gate
                and observation.scheduled_slot_ms < campaign.campaign_start_ms
            )
        ):
            raise ValueError("observation violates frozen campaign identity or start")
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
                """INSERT INTO scan_observations(
                observation_id,campaign_id,scheduled_slot_ms,collection_started_at_ms,
                observed_at_ms,status,market_data_health,decision_close_ms,regime,atr_15m,
                atr_percentile_decile,opportunity_present,opportunity_id,detector_id,setup,
                registry_version,git_sha,config_hash,network_data_errors_json,trigger_source,
                payload_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
                    observation.trigger_source,
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
            "scheduled_observation_count": sum(
                str(row["trigger_source"]) == "SCHEDULED" for row in rows
            ),
            "manual_or_legacy_observation_count": sum(
                str(row["trigger_source"]) != "SCHEDULED" for row in rows
            ),
        }

    @staticmethod
    def _miss_root_cause(row: sqlite3.Row) -> str:
        errors = tuple(str(value) for value in json.loads(str(row["network_data_errors_json"])))
        text = " | ".join(errors).lower()
        if "http error 451" in text:
            return "NETWORK_HTTP_451"
        if "ssl" in text or "tls" in text:
            return "NETWORK_TLS"
        if "timed out" in text or "timeout" in text:
            return "NETWORK_TIMEOUT"
        if "connection" in text:
            return "NETWORK_TLS"
        if "keyerror: -1" in text:
            return "MARKET_DATA_INSUFFICIENT"
        if "decision_close_ms" in text:
            return "RUNTIME_CONTRACT"
        if "process" in text or "host" in text:
            return "PROCESS_OR_HOST_GAP"
        if str(row["market_data_health"]) != "OK":
            return "OTHER"
        return "OTHER"

    def missed_slot_audit(self, campaign_id: str) -> dict[str, Any]:
        missed = [
            row
            for row in self.observations(campaign_id)
            if row["status"] == "MISSED_DECISION_SLOT"
        ]
        chronology = [
            {
                "scheduled_slot_ms": int(row["scheduled_slot_ms"]),
                "root_cause": self._miss_root_cause(row),
                "market_data_health": str(row["market_data_health"]),
                "errors": json.loads(str(row["network_data_errors_json"])),
            }
            for row in missed
        ]
        distribution = Counter(item["root_cause"] for item in chronology)
        return {
            "missed_slot_count": len(missed),
            "root_cause_distribution": dict(sorted(distribution.items())),
            "chronology": chronology,
            "classification_deterministic": True,
            "missingness_independent_of_market_state_proven": False,
            "data_quality_state": (
                "H35_DATA_QUALITY_AT_RISK" if missed else "NO_RECORDED_MISSED_SLOTS"
            ),
        }

    @staticmethod
    def _successful_scan(row: sqlite3.Row, *, require_scheduled: bool = True) -> bool:
        return (
            str(row["status"]) == "SUCCESSFUL_SCAN"
            and (not require_scheduled or str(row["trigger_source"]) == "SCHEDULED")
            and str(row["market_data_health"]) == "OK"
            and row["decision_close_ms"] is not None
            and int(row["decision_close_ms"]) < int(row["collection_started_at_ms"])
        )

    def data_quality_metrics(
        self, campaign: OpportunityCampaign, *, now_ms: int
    ) -> dict[str, Any]:
        if not campaign.has_data_quality_gate:
            return {
                "state": "H35_DATA_QUALITY_AT_RISK",
                "formal_role": "DATA_QUALITY_AT_RISK_ARCHIVE",
                "wall_clock_gate_enabled": False,
            }
        cadence_ms = CADENCE_MS
        latest_expected = (
            (now_ms - campaign.post_boundary_delay_seconds * 1_000) // cadence_ms
        ) * cadence_ms
        expected_slots = (
            list(range(campaign.campaign_start_ms, latest_expected + 1, cadence_ms))
            if latest_expected >= campaign.campaign_start_ms
            else []
        )
        rows = self.observations(campaign.campaign_id)
        by_slot = {int(row["scheduled_slot_ms"]): row for row in rows}
        successful_slots = {
            slot for slot, row in by_slot.items() if self._successful_scan(row)
        }
        missing_slots = set(expected_slots) - set(by_slot)
        recorded_missed_slots = {
            slot for slot in expected_slots if slot in by_slot and slot not in successful_slots
        }
        longest = current = 0
        for slot in expected_slots:
            if slot in successful_slots:
                current = 0
            else:
                current += 1
                longest = max(longest, current)
        assert campaign.maximum_consecutive_missed_decision_slots is not None
        terminal = longest > campaign.maximum_consecutive_missed_decision_slots
        ratio = len(successful_slots & set(expected_slots)) / len(expected_slots) if expected_slots else 0.0
        categories = Counter(
            self._miss_root_cause(row)
            for slot, row in by_slot.items()
            if slot in recorded_missed_slots
        )
        if missing_slots:
            categories["PROCESS_OR_HOST_GAP"] += len(missing_slots)
        return {
            "state": (
                "DATA_QUALITY_TERMINAL"
                if terminal
                else "PREREGISTERED_NOT_STARTED"
                if not expected_slots
                else "ACTIVE_ACCUMULATING"
            ),
            "formal_role": "FORMAL_SUCCESSOR",
            "wall_clock_gate_enabled": True,
            "expected_scheduled_slots": len(expected_slots),
            "recorded_scheduled_slots": len(set(by_slot) & set(expected_slots)),
            "successful_scheduled_scans": len(successful_slots & set(expected_slots)),
            "recorded_missed_decision_slots": len(recorded_missed_slots),
            "missing_wall_clock_slots": len(missing_slots),
            "total_missed_slots": len(recorded_missed_slots | missing_slots),
            "successful_scheduled_scan_ratio": ratio,
            "minimum_successful_scheduled_scan_ratio": (
                campaign.minimum_successful_scheduled_scan_ratio
            ),
            "max_consecutive_missed_decision_slots": longest,
            "maximum_allowed_consecutive_missed_decision_slots": (
                campaign.maximum_consecutive_missed_decision_slots
            ),
            "terminal_failure": terminal,
            "terminal_state_is_irreversible": True,
            "miss_root_causes": dict(sorted(categories.items())),
            "manual_or_backfill_counts_for_quality": False,
        }

    def status(
        self,
        campaign: OpportunityCampaign,
        *,
        scheduler: dict[str, Any] | None = None,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        now = now_ms if now_ms is not None else int(time.time() * 1_000)
        rows = self.observations(campaign.campaign_id)
        outcomes = self.outcomes()
        successful = [
            row
            for row in rows
            if self._successful_scan(row, require_scheduled=campaign.has_data_quality_gate)
        ]
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
        quality = self.data_quality_metrics(campaign, now_ms=now)
        evaluable = (
            campaign.has_data_quality_gate
            and not quality["terminal_failure"]
            and quality["successful_scheduled_scan_ratio"]
            >= campaign.minimum_successful_scheduled_scan_ratio
            and len(opportunity_resolved_8h) >= campaign.minimum_resolved_opportunities
            and age_days >= campaign.minimum_calendar_days
            and len(unique_controls) >= campaign.minimum_unique_matched_controls
            and len(distinct_days) >= campaign.minimum_distinct_utc_days
        )
        missed_audit = self.missed_slot_audit(campaign.campaign_id)
        return {
            "campaign_id": campaign.campaign_id,
            "campaign_start_ms": campaign.campaign_start_ms,
            "campaign_age_days": age_days,
            "scheduler_detected": bool((scheduler or {}).get("detected", False)),
            "scheduler_active": bool((scheduler or {}).get("active", False)),
            "scheduled_slots_recorded": len(rows),
            "successful_scans": len(successful),
            "missed_decision_slots": sum(row["status"] == "MISSED_DECISION_SLOT" for row in rows),
            "missed_slot_root_causes": missed_audit["root_cause_distribution"],
            "data_quality_state": quality["state"],
            "data_quality_gate": quality,
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
            "hypothesis_id": campaign.hypothesis_id,
            "hypothesis_state": (
                "DATA_QUALITY_AT_RISK_ARCHIVE"
                if not campaign.has_data_quality_gate
                else "DATA_QUALITY_TERMINAL"
                if quality["terminal_failure"]
                else "EVALUABLE"
                if evaluable
                else "FORWARD_CAMPAIGN_ACCUMULATING"
            ),
            "h35_state": (
                "DATA_QUALITY_AT_RISK_ARCHIVE"
                if not campaign.has_data_quality_gate
                else None
            ),
            "hypothesis_gate": {
                "minimum_resolved_opportunities": campaign.minimum_resolved_opportunities,
                "preferred_resolved_opportunities": campaign.preferred_resolved_opportunities,
                "minimum_calendar_days": campaign.minimum_calendar_days,
                "minimum_unique_matched_controls": campaign.minimum_unique_matched_controls,
                "minimum_distinct_utc_days": campaign.minimum_distinct_utc_days,
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
    started = now_ms if now_ms is not None else int(time.time() * 1_000)
    scheduled_slot = (started // CADENCE_MS) * CADENCE_MS
    if campaign.has_data_quality_gate and scheduled_slot < campaign.campaign_start_ms:
        raise ValueError("successor campaign has not reached its frozen start")
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
            trigger_source=os.environ.get("BTC_QUANT_TRIGGER_SOURCE", "MANUAL"),
        )
    store.append_observation(observation, campaign=campaign)
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
        trigger_source=os.environ.get("BTC_QUANT_TRIGGER_SOURCE", "MANUAL"),
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
