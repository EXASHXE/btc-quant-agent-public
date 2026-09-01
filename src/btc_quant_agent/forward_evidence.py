from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .data.forward_store import ForwardDerivativeStore, scheduler_status
from .evidence_epoch import EvidenceEpoch, resolve_formal_epoch
from .microstructure import (
    MicrostructureCampaign,
    MicrostructureStore,
    microstructure_service_status,
)
from .opportunity_forward import (
    OpportunityCampaign,
    OpportunityCampaignLifecycle,
    OpportunityCampaignRegistry,
    OpportunityForwardStore,
    opportunity_resolver_scheduler_status,
    opportunity_scheduler_status,
)


def forward_evidence_status(
    *,
    derivatives_store_path: str | Path,
    opportunity_store_path: str | Path,
    epoch_path: str | Path,
    epoch_registry_path: str | Path = "configs/forward/derivatives_evidence_epochs.json",
    campaign_path: str | Path,
    opportunity_campaign_registry_path: str
    | Path = "configs/forward/opportunity_forward_campaigns.json",
    now_ms: int | None = None,
    microstructure_root: str | Path = "data/forward/BTCUSDT/microstructure",
    microstructure_campaign_path: str
    | Path = "configs/forward/v0.3.15_microstructure_capture_campaign.json",
) -> dict[str, Any]:
    now = now_ms if now_ms is not None else int(time.time() * 1_000)
    epoch, lifecycle = resolve_formal_epoch(
        now, registry_path=epoch_registry_path, fallback_epoch_path=epoch_path
    )
    derivatives_store = ForwardDerivativeStore(derivatives_store_path)
    opportunity_store = OpportunityForwardStore(opportunity_store_path)
    archive = derivatives_store.reliability_metrics()
    active = derivatives_store.evidence_epoch_metrics(epoch, now_ms=now)
    active["lifecycle"] = lifecycle.__dict__.copy() if lifecycle is not None else None
    derivative_timer = scheduler_status()
    active["scheduler_enabled"] = bool(derivative_timer.get("detected"))
    active["scheduler_active"] = bool(derivative_timer.get("active"))
    opportunity_registry_file = Path(opportunity_campaign_registry_path)
    archive_lifecycle: OpportunityCampaignLifecycle | None
    successor_lifecycle: OpportunityCampaignLifecycle | None
    if opportunity_registry_file.exists():
        opportunity_registry = OpportunityCampaignRegistry.load(opportunity_registry_file)
        archive_campaign, archive_lifecycle = opportunity_registry.archive()
        successor_campaign, successor_lifecycle = opportunity_registry.successor()
    else:
        archive_campaign = OpportunityCampaign.load(campaign_path)
        successor_campaign = archive_campaign
        archive_lifecycle = successor_lifecycle = None
    opportunity_archive = opportunity_store.status(archive_campaign, now_ms=now)
    opportunity_archive["lifecycle"] = (
        archive_lifecycle.__dict__.copy() if archive_lifecycle is not None else None
    )
    opportunity = opportunity_store.status(
        successor_campaign, scheduler=opportunity_scheduler_status(), now_ms=now
    )
    opportunity["lifecycle"] = (
        successor_lifecycle.__dict__.copy() if successor_lifecycle is not None else None
    )
    resolver = opportunity_resolver_scheduler_status()
    opportunity["resolver_scheduler_enabled"] = bool(resolver.get("detected"))
    opportunity["resolver_scheduler_active"] = bool(resolver.get("active"))
    unresolved = opportunity_store.unresolved(successor_campaign.campaign_id, now)
    opportunity["unresolved_mature_labels"] = len(unresolved)
    opportunity["oldest_unresolved_mature_age_seconds"] = max(
        (
            now
            - (int(row["decision_close_ms"]) + 1 + horizon * 60_000)
        )
        / 1000
        for row, horizon in unresolved
    ) if unresolved else 0.0
    micro_campaign = MicrostructureCampaign.load(microstructure_campaign_path)
    microstructure = MicrostructureStore(
        microstructure_root, micro_campaign.campaign_id, micro_campaign.start_ms
    ).status(now)
    microstructure["service"] = microstructure_service_status()
    old_epoch = EvidenceEpoch.load(
        "configs/forward/v0.3.14_derivatives_evidence_epoch.json"
    )
    old_terminal = derivatives_store.evidence_epoch_metrics(old_epoch, now_ms=now)
    old_terminal["chain_state"] = "TERMINAL_ARCHIVE"
    active["chain_state"] = (
        "TERMINAL" if active["terminal_failure"] else "ACTIVE_ACCUMULATING"
    )
    return {
        "derivatives": {
            "terminal_archive_v0314": old_terminal,
            "successor_v0316": active,
            "active_epoch": active,
            "archive_pre_epoch": {
                "total_attempt_count": archive["total_attempt_count"],
                "manual_attempt_count": archive["manual_attempt_count"],
                "legacy_unknown_attempt_count": archive["legacy_unknown_attempt_count"],
                "failed_attempt_count": archive["failed_attempt_count"],
                "all_rows_preserved": True,
            },
        },
        "opportunity_forward": {
            "archive_h35": opportunity_archive,
            "successor_h36": opportunity,
        },
        "microstructure_forward": microstructure,
        "alpha_interpretation": "NONE",
        "execution": "DISABLED",
        "final_holdout": "SEALED",
    }


def forward_operations_health(report: dict[str, Any]) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    derivatives = report["derivatives"]["successor_v0316"]
    derivative_limit = 4
    if not derivatives.get("scheduler_active"):
        failures.append({"chain": "DERIVATIVES", "reason": "SCHEDULER_INACTIVE"})
    if derivatives.get("terminal_failure"):
        failures.append({"chain": "DERIVATIVES", "reason": "DATA_QUALITY_TERMINAL"})
    elif int(derivatives.get("max_consecutive_bad_or_missing_slots", 0)) >= derivative_limit - 1:
        warnings.append({"chain": "DERIVATIVES", "reason": "GAP_GATE_APPROACHING"})

    opportunity = report["opportunity_forward"]["successor_h36"]
    quality = opportunity["data_quality_gate"]
    if not opportunity.get("scheduler_active"):
        failures.append({"chain": "OPPORTUNITY_H36", "reason": "SCHEDULER_INACTIVE"})
    if quality.get("terminal_failure"):
        failures.append({"chain": "OPPORTUNITY_H36", "reason": "DATA_QUALITY_TERMINAL"})
    elif int(quality.get("max_consecutive_missed_decision_slots", 0)) >= 3:
        warnings.append({"chain": "OPPORTUNITY_H36", "reason": "MISS_GATE_APPROACHING"})
    if float(opportunity.get("oldest_unresolved_mature_age_seconds", 0)) > 7_200:
        failures.append({"chain": "OPPORTUNITY_H36", "reason": "RESOLVER_DELAY"})

    micro = report["microstructure_forward"]
    if not micro["service"].get("active"):
        failures.append({"chain": "MICROSTRUCTURE", "reason": "DAEMON_INACTIVE"})
    heartbeat_age = micro.get("heartbeat_age_seconds")
    if heartbeat_age is None or float(heartbeat_age) > 15:
        failures.append({"chain": "MICROSTRUCTURE", "reason": "STALE_HEARTBEAT"})
    if not micro["partition_integrity"].get("integrity_ok"):
        failures.append({"chain": "MICROSTRUCTURE", "reason": "PARTITION_INTEGRITY"})

    state = "UNHEALTHY" if failures else "DEGRADED" if warnings else "HEALTHY"
    return {
        "state": state,
        "failures": failures,
        "warnings": warnings,
        "direction_claim": "NONE",
        "execution": "DISABLED",
        "final_holdout": "SEALED",
    }
