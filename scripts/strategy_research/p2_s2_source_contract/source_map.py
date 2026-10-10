"""Machine-readable Data Source Map and Rights Questionnaire Generator.

Maps all 9 data roles and certainty tiers based on immutable physical metadata receipts.
Does NOT inject unread manifest content or assert clearance.
"""

from typing import Any

from scripts.strategy_research.p2_s2_source_contract.constants import (
    CODE_START_SHA,
    CONTROLLER_ADMISSION_DESIGN_SHA,
    CONTROLLER_DISPATCH_SHA,
    CONTROLLER_TERMINATION_SHA,
    IMMUTABLE_OWNER_WSL_DATA_ROOT,
    ORIGINAL_STAT_RECEIPT_SHA,
    RECORDED_METADATA_FILE_SIZES,
    SIX_NONPROTECTED_CANDIDATE_PATHS,
    TASK_ID,
    TERMINATED_LOCATOR_COUNTEREXAMPLE_SHA,
)
from scripts.strategy_research.p2_s2_source_contract.types import (
    EvidenceCertainty,
    InstrumentRole,
)


def build_source_scope_and_authority_matrix() -> dict[str, Any]:
    """Build authoritative machine-readable source matrix."""
    items: list[dict[str, Any]] = []

    # 1. Six Candidate 1m BTC Perp Monthly Partitions
    for path in SIX_NONPROTECTED_CANDIDATE_PATHS:
        size = RECORDED_METADATA_FILE_SIZES.get(path)
        items.append({
            "source_id": f"btc_perp_1m_{path.split('year=')[1].split('/')[0]}_{path.split('month=')[1].split('/')[0]}",
            "relative_path": path,
            "role": InstrumentRole.BTC_PERP_1M_KLINE.value,
            "certainty": [
                EvidenceCertainty.PHYSICAL_METADATA_EXECUTOR_OBSERVED.value,
                EvidenceCertainty.UNVERIFIED_RIGHTS.value,
                EvidenceCertainty.UNKNOWN_FILE_CONTINUITY.value,
            ],
            "receipt_sha": ORIGINAL_STAT_RECEIPT_SHA,
            "size_bytes": size,
            "is_regular_file": True,
            "is_directory": False,
            "expected_future_fields": [
                "event_ts",
                "known_at",
                "available_at",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "quote_volume",
                "count",
                "taker_buy_volume",
                "taker_buy_quote_volume",
            ],
            "clock_definition": "UTC minute open [m, m+60000ms), available_at >= m+60000ms",
            "rights_status": "PROPOSED_UNVERIFIED_PENDING_OWNER_GRANT",
            "continuity_status": "UNKNOWN_PENDING_L3_QA",
            "notes": "Verified regular parquet file via lstat receipt; zero data bytes read",
        })

    # 2. Companion BTC Perp Manifest & Funding Events
    items.append({
        "source_id": "btc_perp_data_manifest",
        "relative_path": "research/BTCUSDT/data_manifest.json",
        "role": "BTC_PERP_MANIFEST_METADATA",
        "certainty": [
            EvidenceCertainty.PHYSICAL_METADATA_EXECUTOR_OBSERVED.value,
            EvidenceCertainty.UNVERIFIED_RIGHTS.value,
        ],
        "receipt_sha": ORIGINAL_STAT_RECEIPT_SHA,
        "size_bytes": RECORDED_METADATA_FILE_SIZES["research/BTCUSDT/data_manifest.json"],
        "is_regular_file": True,
        "is_directory": False,
        "expected_future_fields": ["partitions", "checksums", "provenance"],
        "clock_definition": "Static manifest",
        "rights_status": "PROPOSED_UNVERIFIED_PENDING_OWNER_GRANT",
        "continuity_status": "NOT_APPLICABLE_MANIFEST",
        "notes": "Metadata file observed; contents not parsed or trusted without cryptographic verification",
    })

    items.append({
        "source_id": "btc_perp_funding_events_csv",
        "relative_path": "research/BTCUSDT/funding_events.csv",
        "role": InstrumentRole.BTC_PERP_FUNDING_EVENTS_CSV.value,
        "certainty": [
            EvidenceCertainty.PHYSICAL_METADATA_EXECUTOR_OBSERVED.value,
            EvidenceCertainty.UNVERIFIED_RIGHTS.value,
            EvidenceCertainty.UNKNOWN_FILE_CONTINUITY.value,
        ],
        "receipt_sha": ORIGINAL_STAT_RECEIPT_SHA,
        "size_bytes": RECORDED_METADATA_FILE_SIZES["research/BTCUSDT/funding_events.csv"],
        "is_regular_file": True,
        "is_directory": False,
        "expected_future_fields": [
            "event_ts",
            "known_at",
            "settlement_at",
            "funding_rate",
            "mark_price",
            "realized_cashflow",
        ],
        "clock_definition": "Published prediction vs settled actual rate at 8h/4h UTC boundaries",
        "rights_status": "PROPOSED_UNVERIFIED_PENDING_OWNER_GRANT",
        "continuity_status": "UNPROVEN_CLOCK_CAUSALITY",
        "notes": "CSV presence does NOT prove point-in-time publication timing or signed cashflow causality",
    })

    # 3. Raw Containers
    items.append({
        "source_id": "btc_perp_raw_klines_dir",
        "relative_path": "research/BTCUSDT/raw/klines",
        "role": InstrumentRole.BTC_PERP_RAW_KLINE_CONTAINER.value,
        "certainty": [EvidenceCertainty.PHYSICAL_METADATA_EXECUTOR_OBSERVED.value],
        "receipt_sha": ORIGINAL_STAT_RECEIPT_SHA,
        "size_bytes": 4096,
        "is_regular_file": False,
        "is_directory": True,
        "expected_future_fields": ["monthly_zip_archives"],
        "clock_definition": "Raw ingestion timestamp",
        "rights_status": "PROPOSED_UNVERIFIED_PENDING_OWNER_GRANT",
        "continuity_status": "DIRECTORY_CONTAINER_ONLY",
        "notes": "Directory container observed; descent into raw contents strictly excluded",
    })

    items.append({
        "source_id": "btc_perp_raw_mark_price_dir",
        "relative_path": "research/BTCUSDT/raw/mark_price",
        "role": InstrumentRole.BTC_PERP_RAW_MARK_CONTAINER.value,
        "certainty": [EvidenceCertainty.PHYSICAL_METADATA_EXECUTOR_OBSERVED.value],
        "receipt_sha": ORIGINAL_STAT_RECEIPT_SHA,
        "size_bytes": 4096,
        "is_regular_file": False,
        "is_directory": True,
        "expected_future_fields": ["mark_price_1m_continuous"],
        "clock_definition": "Exchange mark calculation index clock",
        "rights_status": "PROPOSED_UNVERIFIED_PENDING_OWNER_GRANT",
        "continuity_status": "UNPROVEN_TRUE_CONTINUOUS_1M_MARK",
        "notes": "Raw mark price directory existence does NOT prove continuous true 1m PIT Mark prices",
    })

    items.append({
        "source_id": "btc_perp_raw_funding_dir",
        "relative_path": "research/BTCUSDT/raw/funding",
        "role": InstrumentRole.BTC_PERP_RAW_FUNDING_CONTAINER.value,
        "certainty": [EvidenceCertainty.PHYSICAL_METADATA_EXECUTOR_OBSERVED.value],
        "receipt_sha": ORIGINAL_STAT_RECEIPT_SHA,
        "size_bytes": 4096,
        "is_regular_file": False,
        "is_directory": True,
        "expected_future_fields": ["funding_rate_events"],
        "clock_definition": "Exchange funding rate settlement clock",
        "rights_status": "PROPOSED_UNVERIFIED_PENDING_OWNER_GRANT",
        "continuity_status": "DIRECTORY_CONTAINER_ONLY",
        "notes": "Raw funding parent directory observed only",
    })

    # 4. Spot Dataset
    items.append({
        "source_id": "btc_spot_manifest",
        "relative_path": "research/BTCUSDT_SPOT/data_manifest.json",
        "role": InstrumentRole.BTC_SPOT_MANIFEST_AND_DATA.value,
        "certainty": [EvidenceCertainty.PHYSICAL_METADATA_EXECUTOR_OBSERVED.value],
        "receipt_sha": ORIGINAL_STAT_RECEIPT_SHA,
        "size_bytes": RECORDED_METADATA_FILE_SIZES["research/BTCUSDT_SPOT/data_manifest.json"],
        "is_regular_file": True,
        "is_directory": False,
        "expected_future_fields": ["spot_kline_partitions"],
        "clock_definition": "UTC Spot Trade Clock",
        "rights_status": "PROPOSED_UNVERIFIED_PENDING_OWNER_GRANT",
        "continuity_status": "DISTINCT_SPOT_DATASET",
        "notes": "Spot cash market cannot substitute for perpetual derivative mechanics or funding rates",
    })

    # 5. Cross-Asset ETH Hourly
    items.append({
        "source_id": "eth_hourly_auxiliary_parquet",
        "relative_path": "research/cross_asset_1h/ETHUSDT.parquet",
        "role": InstrumentRole.ETH_HOURLY_AUXILIARY.value,
        "certainty": [EvidenceCertainty.PHYSICAL_METADATA_EXECUTOR_OBSERVED.value],
        "receipt_sha": ORIGINAL_STAT_RECEIPT_SHA,
        "size_bytes": RECORDED_METADATA_FILE_SIZES["research/cross_asset_1h/ETHUSDT.parquet"],
        "is_regular_file": True,
        "is_directory": False,
        "expected_future_fields": ["hourly_open", "hourly_close", "hourly_volume"],
        "clock_definition": "1h Macro Clock (NOT 1m)",
        "rights_status": "PROPOSED_UNVERIFIED_PENDING_OWNER_GRANT",
        "continuity_status": "HOURLY_AUXILIARY_ONLY",
        "notes": "Hourly cross-asset data does NOT satisfy 1m multi-asset perpetual execution requirement",
    })

    # 6. Legacy Derivatives (v0.3.19)
    items.append({
        "source_id": "legacy_v0319_derivatives",
        "relative_path": "research/v0.3.19_official_derivatives/hourly_inputs.parquet",
        "role": InstrumentRole.LEGACY_DERIVATIVE_HOURLY.value,
        "certainty": [EvidenceCertainty.PHYSICAL_METADATA_EXECUTOR_OBSERVED.value],
        "receipt_sha": ORIGINAL_STAT_RECEIPT_SHA,
        "size_bytes": RECORDED_METADATA_FILE_SIZES["research/v0.3.19_official_derivatives/hourly_inputs.parquet"],
        "is_regular_file": True,
        "is_directory": False,
        "expected_future_fields": ["v0319_features"],
        "clock_definition": "Historical Hourly",
        "rights_status": "HISTORICAL_ARCHIVE_ONLY",
        "continuity_status": "NOT_APPLICABLE_LEGACY",
        "notes": "Historical archive for traceability only; no new live trading use",
    })

    # 7. Absent / Unproven ETH & SOL Perp 1m
    items.append({
        "source_id": "unproven_eth_sol_perp_1m",
        "relative_path": "research/{ETHUSDT,SOLUSDT}/1m/**",
        "role": InstrumentRole.UNPROVEN_ETH_SOL_PERP_1M.value,
        "certainty": [EvidenceCertainty.UNKNOWN_FILE_CONTINUITY.value],
        "receipt_sha": "NONE",
        "size_bytes": None,
        "is_regular_file": False,
        "is_directory": False,
        "expected_future_fields": ["continuous_1m_perp_trade", "continuous_1m_mark", "funding_rates"],
        "clock_definition": "Unproven",
        "rights_status": "ABSENT_OR_UNPROVEN",
        "continuity_status": "STRICT_FAIL_CLOSED_NO_DATA",
        "notes": "Multi-asset diversification claim requires unproven minute data; single-asset BTC fails <=60% screen",
    })

    # 8. Protected Partitions
    items.append({
        "source_id": "protected_holdout_2026_and_forward",
        "relative_path": "research/BTCUSDT/1m/year=2026/**, data/forward/**, data/research/h39_validation/**",
        "role": InstrumentRole.PROTECTED_HOLDOUT.value,
        "certainty": [EvidenceCertainty.PROTECTED_DO_NOT_TOUCH.value],
        "receipt_sha": "PROTECTED_SEALED",
        "size_bytes": None,
        "is_regular_file": False,
        "is_directory": False,
        "expected_future_fields": ["SEALED"],
        "clock_definition": "[2026-02-01, 2026-08-01) strictly protected holdout",
        "rights_status": "STRICTLY_FORBIDDEN",
        "continuity_status": "PROTECTED_DO_NOT_TOUCH",
        "notes": "Strict fail-closed zero metadata traversal and zero data byte access",
    })

    # Proposed Rights Questionnaire
    rights_questionnaire = [
        {
            "question_id": "Q1_COMMERCIAL_AND_RESEARCH_LICENSE",
            "topic": "Data License and Terms of Service Conformance",
            "question": "What is the specific legal terms-of-service and licensing authorization under which the historical Binance/exchange perpetual futures market data was acquired and may be queried by automated agents?",
            "status": "PROPOSED_PENDING_OWNER_RESPONSE",
        },
        {
            "question_id": "Q2_FEE_SCHEDULE_AND_VIP_TIER",
            "topic": "Historical Execution Fee Schedule",
            "question": "What explicit VIP tier maker/taker fee rates, BUSD/USDT discount schedules, and slippage assumptions are authorized to model historical execution friction accurately?",
            "status": "PROPOSED_PENDING_OWNER_RESPONSE",
        },
        {
            "question_id": "Q3_TRUE_CONTINUOUS_1M_MARK_PROVENANCE",
            "topic": "Mark Price Source and Granularity",
            "question": "Does the raw/mark_price landing zone contain actual uninterrupted 1-minute sampled Mark Price records matching the trade Kline timestamps, or is it composed solely of daily/sparse archives?",
            "status": "PROPOSED_PENDING_OWNER_RESPONSE",
        },
        {
            "question_id": "Q4_FUNDING_KNOWN_AT_AND_SETTLEMENT_CAUSALITY",
            "topic": "Point-in-Time Funding Rate Timing",
            "question": "Does funding_events.csv record the point-in-time timestamp at which funding rates were published by the exchange API (known_at), or does it record only the effective settlement timestamp (settlement_at)?",
            "status": "PROPOSED_PENDING_OWNER_RESPONSE",
        },
        {
            "question_id": "Q5_SCOPE_OF_READER_GRANT_LEVEL",
            "topic": "Explicit Reader Capability Grant",
            "question": "Will the owner grant a future explicit staged capability token permitting L2 (Parquet footer metadata only) or L3 (bounded timestamp audit sample), and what is the maximum allowed byte/row ceiling for that grant?",
            "status": "PROPOSED_PENDING_OWNER_RESPONSE",
        },
    ]

    return {
        "task_id": TASK_ID,
        "controller_dispatch_sha": CONTROLLER_DISPATCH_SHA,
        "code_start_sha": CODE_START_SHA,
        "stat_receipt_sha": ORIGINAL_STAT_RECEIPT_SHA,
        "terminated_locator_counterexample_sha": TERMINATED_LOCATOR_COUNTEREXAMPLE_SHA,
        "controller_termination_sha": CONTROLLER_TERMINATION_SHA,
        "controller_admission_design_sha": CONTROLLER_ADMISSION_DESIGN_SHA,
        "owner_wsl_data_root": IMMUTABLE_OWNER_WSL_DATA_ROOT,
        "source_items_count": len(items),
        "source_items": items,
        "rights_questionnaire": rights_questionnaire,
    }
