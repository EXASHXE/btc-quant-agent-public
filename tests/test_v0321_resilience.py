from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from btc_quant_agent.evidence_epoch import (
    EvidenceEpochRegistry,
    resolve_active_derivatives_epoch,
)
from btc_quant_agent.forward_diagnostics import (
    check_collector_resolver_parity,
    forward_doctor,
)
from btc_quant_agent.opportunity_forward import (
    OpportunityCampaignRegistry,
    resolve_active_opportunity_campaign,
)


def test_derivatives_terminal_epoch_cannot_resolve_as_active(tmp_path: Path) -> None:
    config_file = tmp_path / "epoch.json"
    config_file.write_text(
        json.dumps({
            "schema_version": "1.0.0",
            "epoch_id": "TEST_TERMINAL_EPOCH",
            "symbol": "BTCUSDT",
            "created_from_git_sha": "abc1234",
            "epoch_start_utc": "2026-09-03T00:00:00Z",
            "epoch_start_ms": 1788393600000,
            "epoch_start_rule": "Fixed",
            "cadence_minutes": 15,
            "post_boundary_delay_seconds": 20,
            "required_fields": ["funding_rate"],
            "minimum_days": 30,
            "minimum_fully_available_snapshots": 2500,
            "minimum_required_field_availability": 0.95,
            "maximum_consecutive_failed_or_missing_scheduled_slots": 4,
            "manual_runs_count_for_eligibility": False,
            "legacy_runs_count_for_eligibility": False,
            "backfill_allowed": False,
            "final_holdout_access": False,
        })
    )
    registry_file = tmp_path / "derivatives_evidence_epochs.json"
    registry_file.write_text(
        json.dumps({
            "schema_version": "1.0.0",
            "epochs": [
                {
                    "epoch_id": "TEST_TERMINAL_EPOCH",
                    "config_path": str(config_file),
                    "start_ms": 1788393600000,
                    "status": "FAILED_GAP_GATE_TERMINAL",
                    "terminal_reason": "gap gate breached",
                    "terminal_at_ms": 1788395400000,
                    "superseded_by": None,
                    "formal_eligibility_role": "FORMAL_TERMINAL",
                    "immutable_history": True,
                }
            ],
        })
    )

    reg = EvidenceEpochRegistry.load(registry_file)
    assert reg.active_epoch() is None
    assert reg.active_lifecycle() is None
    assert resolve_active_derivatives_epoch(registry_path=registry_file) is None


def test_opportunity_terminal_campaign_cannot_resolve_as_active(tmp_path: Path) -> None:
    config_file = tmp_path / "opp.json"
    config_file.write_text(
        json.dumps({
            "schema_version": "1.0.0",
            "campaign_id": "TEST_TERMINAL_OPP",
            "campaign_start_utc": "2026-09-03T00:00:00Z",
            "campaign_start_ms": 1788393600000,
            "start_rule": "Fixed",
            "start_git_sha": "abc1234",
            "hypothesis_id": "H38_TEST",
            "registry_version": "v0.3.12",
            "strategy_version": "0.3.11",
            "feature_version": "0.3.11",
            "config_hash": "e19b352002ff3197",
            "symbol": "BTCUSDT",
            "normal_runtime_mode": "RUNTIME_GATED",
            "detector_ids": ["trend_pullback_opportunity", "breakout_retest_opportunity"],
            "direction_claim": "NONE",
            "movement_horizons_minutes": [240, 480],
            "movement_metrics": [
                "future_range_atr",
                "max_up_excursion_atr",
                "max_down_excursion_atr",
                "max_abs_excursion_atr",
            ],
            "reference_rule": "OPEN of first fully available 1m bar strictly after decision close",
            "atr_rule": "frozen 15m ATR observed at the original forward scan",
            "control_matching_rules": {
                "candidate_population": "successful",
                "control_population": "successful",
            },
            "data_quality_gate": {
                "post_boundary_delay_seconds": 50,
                "minimum_successful_scheduled_scan_ratio": 0.95,
                "maximum_consecutive_missed_decision_slots": 4,
                "successful_scan_definition": ["RUNTIME_GATED scan completed"],
                "missing_wall_clock_slots_count_as_missed": True,
                "retrospective_retry_or_backfill_allowed": False,
                "terminal_state_is_irreversible": True,
                "miss_categories": ["NETWORK_HTTP_451"],
            },
            "h38": {
                "hypothesis": "test",
                "primary_metric": "future_range_atr",
                "primary_horizons_minutes": [240, 480],
                "minimum_resolved_opportunities": 30,
                "preferred_resolved_opportunities": 50,
                "minimum_calendar_days": 30,
                "minimum_unique_matched_controls": 100,
                "minimum_distinct_utc_days": 20,
                "seed": 43,
            },
            "immutability": {
                "campaign_start_movable": False,
                "execution": "DISABLED",
            },
        })
    )
    registry_file = tmp_path / "opportunity_forward_campaigns.json"
    registry_file.write_text(
        json.dumps({
            "schema_version": "1.0.0",
            "campaigns": [
                {
                    "campaign_id": "TEST_TERMINAL_OPP",
                    "config_path": str(config_file),
                    "start_ms": 1788393600000,
                    "hypothesis_id": "H38_TEST",
                    "status": "DATA_QUALITY_TERMINAL_ARCHIVE",
                    "formal_role": "DATA_QUALITY_TERMINAL_ARCHIVE",
                    "terminal_reason": "consecutive missed slots exceeded",
                    "terminal_at_ms": 1788395400000,
                    "superseded_by": None,
                    "immutable_history": True,
                }
            ],
        })
    )

    reg = OpportunityCampaignRegistry.load(registry_file)
    assert reg.active_campaign() is None
    assert reg.active_lifecycle() is None
    assert resolve_active_opportunity_campaign(registry_path=registry_file) is None


def test_collector_resolver_parity_checker() -> None:
    # 1. Parity OK: both use --registry
    aligned_units = {
        "btc-quant-opportunity-forward.service": {
            "exec_start": "/bin/quantctl opportunity-forward collect-once --registry configs/opp.json"
        },
        "btc-quant-opportunity-resolve.service": {
            "exec_start": "/bin/quantctl opportunity-forward resolve --registry configs/opp.json"
        },
    }
    result = check_collector_resolver_parity(aligned_units)
    assert result["parity_ok"] is True

    # 2. Parity Failure: collector uses v0.3.20, resolver uses v0.3.17
    mismatched_units = {
        "btc-quant-opportunity-forward.service": {
            "exec_start": "/bin/quantctl opportunity-forward collect-once --campaign configs/v0.3.20.json"
        },
        "btc-quant-opportunity-resolve.service": {
            "exec_start": "/bin/quantctl opportunity-forward resolve --campaign configs/v0.3.17.json"
        },
    }
    result_mismatch = check_collector_resolver_parity(mismatched_units)
    assert result_mismatch["parity_ok"] is False
    assert "Collector targets" in result_mismatch["detail"]


def test_forward_doctor_network_http_451_fails_closed() -> None:
    from urllib.error import HTTPError

    mock_opener = MagicMock()
    mock_opener.side_effect = HTTPError(
        url="https://fapi.binance.com/fapi/v1/time",
        code=451,
        msg="Unavailable For Legal Reasons",
        hdrs=None,
        fp=MagicMock(read=lambda: b"Service unavailable from restricted location"),
    )

    doc = forward_doctor(url_opener=mock_opener)
    assert doc["status"] == "NETWORK_INELIGIBLE"
    assert doc["is_healthy"] is False
    assert any("451" in issue for issue in doc["issues"])


def test_forward_doctor_preregistered_successor_recognized() -> None:
    doc = forward_doctor()
    assert doc["status"] == "PREREGISTERED_NOT_STARTED"
    assert doc["is_healthy"] is True
    assert doc["parity"]["parity_ok"] is True
    assert doc["campaigns"]["has_active_derivatives"] is True
    assert doc["campaigns"]["has_active_opportunity"] is True
    assert doc["chains"]["storage"]["writable"] is True
