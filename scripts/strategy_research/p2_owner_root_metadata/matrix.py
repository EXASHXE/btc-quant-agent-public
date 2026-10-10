"""Matrix generation for Candidate-Month × File-Existence and Source Classes & Permissions."""

from __future__ import annotations

from typing import Any

from .config import (
    CONTROLLER_DISPATCH_SHA,
    PROMPT_PINNED_SHA,
    TASK_ID,
    MonthPartitionObservation,
    AdditionalTargetObservation,
)


def build_candidate_month_matrix(
    month_observations: list[MonthPartitionObservation],
) -> dict[str, Any]:
    """Build candidate-month × file-existence matrix for the 6 approved BTC months."""
    matrix_rows: list[dict[str, Any]] = []
    for obs in month_observations:
        matrix_rows.append(
            {
                "partition_label": obs.label,
                "year": obs.year,
                "month": obs.month,
                "relative_directory": obs.rel_dir,
                "directory_exists": obs.dir_exists,
                "directory_is_symlink": obs.dir_is_symlink,
                "file_name": obs.file_name,
                "file_relative_path": obs.file_rel_path,
                "file_exists": obs.file_exists,
                "file_is_regular": obs.file_is_regular,
                "file_is_symlink": obs.file_is_symlink,
                "file_size_bytes": obs.file_size_bytes,
                "file_mode_octal": obs.file_mode_octal,
                "verification_status": obs.status,
                "notes": obs.notes,
            }
        )

    all_present = len(matrix_rows) == 6 and all(
        row["verification_status"] == "PRESENT_METADATA_ONLY" for row in matrix_rows
    )

    return {
        "schema_version": "P2_CANDIDATE_MONTH_MATRIX_V1",
        "task_id": TASK_ID,
        "controller_dispatch_sha": CONTROLLER_DISPATCH_SHA,
        "prompt_pinned_sha": PROMPT_PINNED_SHA,
        "total_approved_months": 6,
        "all_selected_files_present_metadata_only": all_present,
        "rows": matrix_rows,
    }


def build_source_type_and_permissions_matrix(
    month_matrix: dict[str, Any],
    target_observations: list[AdditionalTargetObservation],
) -> dict[str, Any]:
    """Build source classes and permissions matrix."""
    # Group observations by source class
    source_classes: list[dict[str, Any]] = [
        {
            "class_name": "BTC Perpetual 1m Klines (Selected Non-Protected Partitions)",
            "asset": "BTC",
            "instrument": "Perpetual (USD-M)",
            "frequency": "1m",
            "coverage_scope": "6 selected candidate months (2021-03, 2021-04, 2023-03, 2023-04, 2025-03, 2025-04)",
            "physical_format": "Hive Partitioned Parquet (data.parquet)",
            "existence_status": (
                "LOCATED_METADATA_ONLY"
                if month_matrix.get("all_selected_files_present_metadata_only")
                else "INCOMPLETE"
            ),
            "true_continuous_1m_pit_status": "UNVERIFIED_PENDING_CONTENT_AUDIT",
            "spot_vs_perp_distinction": "Perpetual derivative contract; distinct from spot cash market",
            "license_and_rights": "UNVERIFIED_PENDING_OWNER_GRANT",
            "p2_source_admission_status": "BLOCKED_NOT_ADMITTED",
            "policy_rule": "Metadata presence does NOT constitute empirical source admission; no P3/P4 grant.",
        },
        {
            "class_name": "BTC Perpetual Data Manifest & Funding Events",
            "asset": "BTC",
            "instrument": "Perpetual (USD-M)",
            "frequency": "N/A (Manifest JSON / Event CSV)",
            "coverage_scope": "research/BTCUSDT/data_manifest.json and research/BTCUSDT/funding_events.csv",
            "physical_format": "JSON / CSV",
            "existence_status": "LOCATED_METADATA_ONLY",
            "true_continuous_1m_pit_status": (
                "UNPROVEN: CSV existence is NOT verified funding event clock/right or true known-at timestamp"
            ),
            "spot_vs_perp_distinction": "Perpetual funding event series; not spot",
            "license_and_rights": "UNVERIFIED_PENDING_OWNER_GRANT",
            "p2_source_admission_status": "BLOCKED_NOT_ADMITTED",
            "policy_rule": "Stat-only inspection; files not opened or parsed.",
        },
        {
            "class_name": "BTC Perpetual Raw Source Directories (Mark Price, Funding, Klines)",
            "asset": "BTC",
            "instrument": "Perpetual (USD-M)",
            "frequency": "Directory container only",
            "coverage_scope": "research/BTCUSDT/raw/{mark_price,funding,klines}",
            "physical_format": "Directory hierarchies",
            "existence_status": "PARENT_DIRECTORIES_LOCATED_ONLY",
            "true_continuous_1m_pit_status": (
                "UNPROVEN: raw/mark_price parent directory existence does NOT prove continuous true 1m Mark PIT"
            ),
            "spot_vs_perp_distinction": "Raw perp ingestion landing zone",
            "license_and_rights": "UNVERIFIED_PENDING_OWNER_GRANT",
            "p2_source_admission_status": "EXCLUDED_FROM_LISTING_OR_READ",
            "policy_rule": "Strict prohibition against scandir or descent into raw subdirectories.",
        },
        {
            "class_name": "BTC Spot Separate Dataset",
            "asset": "BTC",
            "instrument": "Spot (Cash)",
            "frequency": "1m (Separate tree)",
            "coverage_scope": "research/BTCUSDT_SPOT/{data_manifest.json,1m}",
            "physical_format": "JSON manifest + 1m directory",
            "existence_status": "LOCATED_METADATA_ONLY",
            "true_continuous_1m_pit_status": "NOT_APPLICABLE_SPOT_ONLY",
            "spot_vs_perp_distinction": (
                "SPOT IS NOT PERPETUAL: Spot cash data cannot substitute for perpetual futures mechanics "
                "or funding rate dynamics"
            ),
            "license_and_rights": "UNVERIFIED_PENDING_OWNER_GRANT",
            "p2_source_admission_status": "BLOCKED_NOT_ADMITTED",
            "policy_rule": "Distinct source class; no automatic interchangeability.",
        },
        {
            "class_name": "Cross-Asset Hourly Auxiliary Data",
            "asset": "ETH / Basket",
            "instrument": "USD-M / Spot / Mixed",
            "frequency": "1h (HOURLY, NOT 1m)",
            "coverage_scope": "research/cross_asset_1h/{ETHUSDT.parquet,basket_manifest.json}",
            "physical_format": "Parquet + JSON manifest",
            "existence_status": "LOCATED_METADATA_ONLY",
            "true_continuous_1m_pit_status": (
                "HOURLY NOT MINUTE: 1h ETH data is NOT evidence of ETH/SOL perp 1m or true continuous Mark"
            ),
            "spot_vs_perp_distinction": "Auxiliary hourly macro features",
            "license_and_rights": "UNVERIFIED_PENDING_OWNER_GRANT",
            "p2_source_admission_status": "BLOCKED_NOT_ADMITTED",
            "policy_rule": "Does NOT satisfy 1m perp execution requirement for multi-asset trading.",
        },
        {
            "class_name": "Legacy Official Derivatives (v0.3.19)",
            "asset": "BTC",
            "instrument": "Derivatives archive",
            "frequency": "Hourly",
            "coverage_scope": "research/v0.3.19_official_derivatives/{hourly_inputs.parquet,raw_data_manifest.json}",
            "physical_format": "Parquet + JSON manifest",
            "existence_status": "LOCATED_METADATA_ONLY",
            "true_continuous_1m_pit_status": "NOT_APPLICABLE_HOURLY_DERIVATIVE_ARCHIVE",
            "spot_vs_perp_distinction": "Older derivative archive; not minute execution series",
            "license_and_rights": "UNVERIFIED_PENDING_OWNER_GRANT",
            "p2_source_admission_status": "BLOCKED_NOT_ADMITTED",
            "policy_rule": "Retained for historical traceability only; no new live trading use.",
        },
        {
            "class_name": "Protected Forward & Validation Holdout Data",
            "asset": "BTC",
            "instrument": "Forward / Held-out partitions",
            "frequency": "All frequencies",
            "coverage_scope": (
                "data/forward/BTCUSDT/**, data/research/h39_validation/**, "
                "data/research/BTCUSDT/1m/year=2026/**, and any BTC market file in [2026-02-01, 2026-08-01)"
            ),
            "physical_format": "PROTECTED_EXCLUDED",
            "existence_status": "STRICT_ZERO_ACCESS_PRESERVED",
            "true_continuous_1m_pit_status": "PROTECTED_HOLD_OUT",
            "spot_vs_perp_distinction": "Protected evaluation domain",
            "license_and_rights": "STRICTLY_SEALED",
            "p2_source_admission_status": "PERMANENTLY_BLOCKED_FROM_P2_INSPECTION",
            "policy_rule": "Zero stat, zero scandir, zero open, zero read bytes.",
        },
    ]

    target_details = [obs.to_dict() for obs in target_observations]

    # Formulate next bounded readiness checks without executing them
    next_bounded_readiness_checks = [
        {
            "check_id": "CHECK_A_KLINE_READ_AND_SHA_GRANT",
            "title": "Owner Grants Future Selected Kline Parquet Read/SHA",
            "description": (
                "Owner provides explicit cryptographic sha256 golden references and bounded read authorization "
                "for the 6 verified non-protected monthly kline parquets (2021-03, 2021-04, 2023-03, 2023-04, "
                "2025-03, 2025-04) to audit column schema and timestamp monotonicity."
            ),
            "status": "PROPOSED_UNEXECUTED",
        },
        {
            "check_id": "CHECK_B_RAW_MARK_1M_SCHEMA_AND_PIT_CONTINUITY",
            "title": "Raw Mark 1m Schema/Timestamp Availability & True Continuous 1m PIT",
            "description": (
                "Rigorous audit of raw/mark_price internal structure to establish whether continuous 1-minute "
                "point-in-time Mark prices exist without gaps or forward leakage across backtest windows."
            ),
            "status": "PROPOSED_UNEXECUTED",
        },
        {
            "check_id": "CHECK_C_FUNDING_TRUE_KNOWN_AT_AND_SETTLEMENT_SOURCES",
            "title": "Funding True Known-At, Settlement/Index, and Price Sources",
            "description": (
                "Verification that funding_events.csv records point-in-time publication timestamps rather than "
                "retrospective settlement timestamps, verifying cash settlement flow causality."
            ),
            "status": "PROPOSED_UNEXECUTED",
        },
        {
            "check_id": "CHECK_D_RIGHTS_FEES_FILTER_AND_PROTECTION_GATES",
            "title": "Rights, Fees, Filter, and Protection Gates",
            "description": (
                "Formal legal/commercial data usage clearance, VIP fee tier schedule verification, and "
                "cryptographic verification that [2026-02-01, 2026-08-01) holdout remains completely uninspected."
            ),
            "status": "PROPOSED_UNEXECUTED",
        },
        {
            "check_id": "CHECK_E_ETH_SOL_MINUTE_DECISION_OR_PROSPECTIVE_BTC_ONLY_ROUTE",
            "title": "ETH/SOL Minute Data Decision or Prospective BTC-Only Diagnostic Route",
            "description": (
                "Address multi-asset diversification vs single-asset concentration. Note: BTC-only positive "
                "screen issue is 100% single asset exposure >60% ceiling; NOT '1/3 assets 33% below >=60% positive "
                "support'. A BTC-only separately authorized diagnostic need not claim 3-asset positive support and "
                "must be a new prospective method if selected."
            ),
            "status": "PROPOSED_UNEXECUTED",
        },
    ]

    return {
        "schema_version": "P2_SELECTED_SOURCE_TYPE_AND_PERMISSIONS_MATRIX_V1",
        "task_id": TASK_ID,
        "controller_dispatch_sha": CONTROLLER_DISPATCH_SHA,
        "prompt_pinned_sha": PROMPT_PINNED_SHA,
        "source_classes": source_classes,
        "additional_targets_observed": target_details,
        "next_bounded_readiness_checks": next_bounded_readiness_checks,
    }
