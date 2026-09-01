from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .data.forward_store import ForwardDerivativeStore, scheduler_status
from .evidence_epoch import resolve_formal_epoch
from .microstructure import MicrostructureCampaign, MicrostructureStore
from .opportunity_forward import (
    OpportunityCampaign,
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
    now_ms: int | None = None,
    microstructure_root: str | Path = "data/forward/BTCUSDT/microstructure",
    microstructure_campaign_path: str
    | Path = "configs/forward/v0.3.15_microstructure_capture_campaign.json",
) -> dict[str, Any]:
    now = now_ms if now_ms is not None else int(time.time() * 1_000)
    epoch, lifecycle = resolve_formal_epoch(
        now, registry_path=epoch_registry_path, fallback_epoch_path=epoch_path
    )
    campaign = OpportunityCampaign.load(campaign_path)
    derivatives_store = ForwardDerivativeStore(derivatives_store_path)
    opportunity_store = OpportunityForwardStore(opportunity_store_path)
    archive = derivatives_store.reliability_metrics()
    active = derivatives_store.evidence_epoch_metrics(epoch, now_ms=now)
    active["lifecycle"] = lifecycle.__dict__.copy() if lifecycle is not None else None
    derivative_timer = scheduler_status()
    active["scheduler_enabled"] = bool(derivative_timer.get("detected"))
    active["scheduler_active"] = bool(derivative_timer.get("active"))
    opportunity = opportunity_store.status(
        campaign, scheduler=opportunity_scheduler_status(), now_ms=now
    )
    resolver = opportunity_resolver_scheduler_status()
    opportunity["resolver_scheduler_enabled"] = bool(resolver.get("detected"))
    opportunity["resolver_scheduler_active"] = bool(resolver.get("active"))
    opportunity["unresolved_mature_labels"] = len(
        opportunity_store.unresolved(campaign.campaign_id, now)
    )
    micro_campaign = MicrostructureCampaign.load(microstructure_campaign_path)
    microstructure = MicrostructureStore(
        microstructure_root, micro_campaign.campaign_id, micro_campaign.start_ms
    ).status(now)
    return {
        "derivatives": {
            "active_epoch": active,
            "archive_pre_epoch": {
                "total_attempt_count": archive["total_attempt_count"],
                "manual_attempt_count": archive["manual_attempt_count"],
                "legacy_unknown_attempt_count": archive["legacy_unknown_attempt_count"],
                "failed_attempt_count": archive["failed_attempt_count"],
                "all_rows_preserved": True,
            },
        },
        "opportunity_forward": opportunity,
        "microstructure_forward": microstructure,
        "alpha_interpretation": "NONE",
        "execution": "DISABLED",
        "final_holdout": "SEALED",
    }
