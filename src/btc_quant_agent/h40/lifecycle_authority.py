"""Accepted H40 F01 lifecycle evidence-authority contracts and verifiers.

This module is strictly pre-outcome.  It materializes the accepted lifecycle
semantic hash tree, typed authority/receipt schemas, deterministic run and
runtime-roster authority, and synthetic/governance verification mechanics.
It does not evaluate market data, Discovery statistics, walk-forward results,
confirmation outcomes, or execution.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from typing import Any, ClassVar, cast

from ..research_contract.canonical import canonical_json, canonical_sha256
from .guards import H40GuardError, H40ReasonCode
from .protocol_authority import (
    EXPECTED_PROTOCOL_AUTHORITY_HASH,
    EXPECTED_SEMANTIC_ROOT_HASH,
    EXPECTED_STRUCTURAL_LEDGER_HASH,
    MaterializedRunAuthority,
    compute_protocol_authority_hash,
    compute_semantic_root_hash,
    current_p1_authority_snapshot,
)

EXPECTED_LIFECYCLE_SEMANTIC_ROOT_HASH = (
    "d8c24b878b18426666ce46390e7363a0a2a5d7d3eb4d7636cc5cb2ecfaf4e9f5"
)
EXPECTED_LIFECYCLE_GOVERNANCE_AUTHORITY_HASH = (
    "ee619e16bb665ba377baa2a50f92ea1c36ee207282e3f7757b54a0a1adf7b828"
)
DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH = (
    "f84c97050c7db813263e5ffda6b1c556af0b7b0e2876bb8616640d2c9d67084b"
)

# No implementation authority is accepted during F01 implementation.  A later
# independently accepted publication must materialize this boundary.
ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH: str | None = None

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
_TIMESTAMP_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z", re.ASCII)


def _require_sha256(value: str, name: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be an exact lowercase SHA-256 hex digest")
    return value


def _require_commit(value: str, name: str) -> str:
    if not isinstance(value, str) or _COMMIT_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be an exact lowercase 40-hex commit SHA")
    return value


def _require_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_exact_keys(data: Mapping[str, Any], expected: frozenset[str], name: str) -> None:
    actual = frozenset(data)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(f"{name} schema mismatch; missing={missing}, extra={extra}")


def _require_string_fields(
    data: Mapping[str, Any],
    fields: frozenset[str] | set[str],
    name: str,
) -> None:
    for field_name in fields:
        if not isinstance(data[field_name], str):
            raise TypeError(f"{name}.{field_name} must be a string")


def normalize_audit_timestamp(value: str) -> str:
    """Validate the sole accepted audit timestamp spelling.

    Timestamps are content-bound audit metadata only.  This function performs
    no comparison with the wall clock and confers no transition authority.
    """
    if not isinstance(value, str) or len(value) != 20 or _TIMESTAMP_RE.fullmatch(value) is None:
        raise ValueError("timestamp must use exact YYYY-MM-DDTHH:MM:SSZ form")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ValueError("timestamp must be a calendar-valid UTC second without leap second") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise ValueError("timestamp is not canonically normalized")
    return value


# The following JSON is the exact nine-child accepted P3R0R1 semantic preimage.
# Expected digests below are test oracles only; every computation hashes content.
_LIFECYCLE_CONTRACTS_JSON = r'''
{
  "discovery_authorization_receipt_contract": {
    "authority_rules": ["transition_api_constructs_receipt_only_after_recomputing_all_bound_authorities","caller_object_path_boolean_or_label_is_not_authority","upstream_receipt_hash_must_be_null","run_authority_id_must_recompute_under_H40_RUN_AUTHORITY_V1","lifecycle_implementation_authority_hash_must_be_independently_accepted","sealed_registered_roster_hash_and_counts_must_match_materialized_run_authority","execution_disabled_must_be_true"],
    "authorized_transition": ["H40_P1_SCAFFOLDED","H40_DISCOVERY"],
    "implementation_authority_object": {"canonical_field_names":["accepted_lifecycle_governance_authority_hash","f01_implementation_acceptance_artifact_path","f01_implementation_acceptance_commit_sha","f01_implementation_commit_sha","required_test_ci_evidence_identity","schema_id"],"required_test_ci_evidence_identity_fields":["evidence_manifest_artifact_path","evidence_manifest_sha256","tested_commit_sha"],"schema_id":"H40_LIFECYCLE_IMPLEMENTATION_AUTHORITY_V1"},
    "receipt_field_contract": {"authorized_at_utc":"audit_timestamp_utc","discovery_selection_correction_contract_hash":"constant:f84c97050c7db813263e5ffda6b1c556af0b7b0e2876bb8616640d2c9d67084b","execution_disabled":"constant:true","lifecycle_governance_authority_hash":"accepted_sha256","lifecycle_implementation_authority_hash":"accepted_sha256","materialized_run_authority_hash":"sha256","not_testable_slot_count":"integer_gte_0","protocol_authority_hash":"constant:a83f8fc7a5ca7109fb8cd7fed114d87c3b2c968b5145c11cada203aa5111d1ce","receipt_schema_id":"constant:H40_RECEIPT_DISCOVERY_AUTH_V2","registered_slot_count":"integer_gte_0","run_authority_id":"sha256","sealed_registered_roster_hash":"sha256","semantic_root_hash":"constant:71889a35f227ed734272b712851174a69bf9dbb12ea3f87cd84c26e7c66f6af1","source_manifest_hash":"sha256","split_attestation_hash":"sha256","split_manifest_hash":"sha256","structural_ledger_hash":"constant:483f68502b57972deae071c7bd4587ca3e57ccaa72bd99fb0de07b4f0ab8c85f","total_slot_count":"integer_gt_0","upstream_receipt_hash":"constant:null"},
    "receipt_hash_rule":"canonical_sha256(exact_receipt_field_contract_keys_only)","receipt_schema_id":"H40_RECEIPT_DISCOVERY_AUTH_V2","schema_id":"H40_LIFECYCLE_CHILD_DISCOVERY_AUTHORIZATION_V1"
  },
  "candidate_lock_receipt_contract": {
    "authorization_receipt_field_contract":{"discovery_authorization_receipt_hash":"sha256_equal_upstream_receipt_hash","discovery_result_evidence_hash":"verified_evidence_sha256","discovery_selection_correction_contract_hash":"constant:f84c97050c7db813263e5ffda6b1c556af0b7b0e2876bb8616640d2c9d67084b","locked_at_utc":"audit_timestamp_utc","materialized_run_authority_hash":"sha256_equal_discovery_authorization","receipt_schema_id":"constant:H40_RECEIPT_CANDIDATE_LOCK_V2","run_authority_id":"sha256_equal_discovery_authorization","selected_slot_hash":"sha256_derived_by_verifier","selected_slot_index":"integer_derived_by_verifier","selected_structural_configuration_hash":"sha256_derived_by_verifier","selection_verifier_id":"constant:H40_DISCOVERY_SELECTION_VERIFIER_V1","upstream_receipt_hash":"sha256_of_discovery_authorization_receipt","verified_at_utc":"audit_timestamp_utc"},
    "authorized_transition":["H40_DISCOVERY","H40_CANDIDATE_LOCKED"],
    "candidate_result_entry_field_contract":{"candidate_result_input_evidence_hash":"sha256_of_complete_canonical_scientific_result_inputs_bound_to_run_authority_candidate_source_split_and_accepted_contracts","complexity":"integer_derived_from_accepted_configuration","family_id":"string_derived_from_accepted_configuration","hard_gate_input_evidence_hashes":"complete_object_sorted_by_accepted_gate_id_to_run_and_candidate_bound_sha256","net_expectancy_input_evidence_hash":"run_and_candidate_bound_sha256","precision_input_evidence_hash":"run_and_candidate_bound_sha256","slot_hash":"sha256","slot_index":"integer_0_through_167","structural_configuration_hash":"sha256"},
    "discovery_result_evidence_field_contract":{"candidate_result_entries":"array_sorted_by_structural_configuration_hash_ascending","correction_input_evidence_manifest_hash":"sha256_of_complete_run_roster_metric_specific_and_cross_family_inputs","created_at_utc":"audit_timestamp_utc","discovery_authorization_receipt_hash":"sha256","discovery_partition":"constant:WF1_CALIBRATION","discovery_selection_contract_id":"constant:DISCOVERY_SELECTION_V1","discovery_selection_correction_contract_hash":"constant:f84c97050c7db813263e5ffda6b1c556af0b7b0e2876bb8616640d2c9d67084b","evidence_schema_id":"constant:H40_DISCOVERY_RESULT_EVIDENCE_V1","materialized_run_authority_hash":"sha256","run_authority_id":"sha256","sealed_registered_roster_hash":"sha256"},
    "evidence_completeness_rule":"candidate_result_entries_must_equal_the_complete_sealed_REGISTERED_roster_with_no_missing_duplicate_or_extra_configuration",
    "forbidden_authority":["caller_supplied_selection_rank","summary_locator_or_hash_without_canonical_result_evidence","global_M_equals_18_FWER","ascending_slot_index_as_final_tie","runner_up_promotion"],
    "receipt_hash_rule":"canonical_sha256(exact_authorization_receipt_field_contract_keys_only)","result_evidence_hash_rule":"canonical_sha256(exact_discovery_result_evidence_fields_with_exact_candidate_result_entry_fields)","schema_id":"H40_LIFECYCLE_CHILD_CANDIDATE_LOCK_V1",
    "selection_authority":{"contract_id":"DISCOVERY_SELECTION_V1","content_hash":"f84c97050c7db813263e5ffda6b1c556af0b7b0e2876bb8616640d2c9d67084b","cross_family_rule":"Holm_applies_to_family_representatives","final_selection_order":["pass_every_accepted_hard_gate","highest_adjusted_LCB_net_expectancy","highest_adjusted_LCB_precision","lower_complexity","ascending_canonical_structural_configuration_hash_or_configuration_ID"],"metric_correction_rule":"PRECISION_and_NET_EXPECTANCY_within_family_max_statistic_corrections_are_separate","no_runner_up_promotion":true,"within_family_universe":"REGISTERED_rows_of_that_family_in_the_sealed_snapshot"},
    "verifier_obligations":["load_every_evidence_object_by_content_hash_validate_exact_schema_and_verify_run_candidate_source_split_and_contract_lineage","recompute_candidate_identity_and_membership_against_the_sealed_roster","recompute_all_hard_gates_and_all_correction_and_selection_outputs_under_the_accepted_content_hash","derive_exactly_one_winner_or_emit_no_authorization_receipt","persist_authorization_receipt_only_after_successful_recomputation","reverify_result_evidence_and_selection_on_restore_before_transition_use"]
  },
  "wf_validation_receipt_contract": {
    "authorization_receipt_field_contract":{"candidate_lock_receipt_hash":"sha256_equal_upstream_receipt_hash","locked_slot_hash":"sha256_equal_candidate_lock","locked_slot_index":"integer_equal_candidate_lock","locked_structural_configuration_hash":"sha256_equal_candidate_lock","receipt_schema_id":"constant:H40_RECEIPT_WF_VALIDATION_V2","run_authority_id":"sha256_equal_candidate_lock","upstream_receipt_hash":"sha256_of_candidate_lock_receipt","validated_at_utc":"audit_timestamp_utc","validation_verifier_id":"constant:H40_WF_VALIDATION_VERIFIER_V1","verified_at_utc":"audit_timestamp_utc","wf_validation_result_evidence_hash":"verified_evidence_sha256"},
    "authorized_transition":["H40_CANDIDATE_LOCKED","H40_WALK_FORWARD_VALIDATED"],
    "fold_result_entry_field_contract":{"accepted_gate_input_evidence_hashes":"complete_object_sorted_by_accepted_gate_id_to_run_candidate_split_fold_and_contract_bound_sha256","evaluation_input_evidence_hash":"sha256_of_complete_canonical_inputs_bound_to_run_candidate_split_fold_and_accepted_contracts","fold_identity_hash":"sha256_derived_from_split_authority","fold_id":"string_derived_from_split_authority","partition_id":"string_derived_from_split_authority","split_definition_hash":"sha256_derived_from_split_manifest"},
    "forbidden_authority":["caller_supplied_all_wf_gates_passed_boolean","summary_locator_or_hash_without_canonical_fold_evidence","foreign_candidate_evidence","foreign_or_modified_split_evidence"],
    "receipt_hash_rule":"canonical_sha256(exact_authorization_receipt_field_contract_keys_only)","result_evidence_hash_rule":"canonical_sha256(exact_wf_validation_result_evidence_fields_with_exact_fold_result_entry_fields)","schema_id":"H40_LIFECYCLE_CHILD_WF_VALIDATION_V1",
    "verifier_obligations":["load_every_fold_evidence_object_by_content_hash_validate_exact_schema_and_verify_run_candidate_split_fold_and_contract_lineage","derive_the_complete_ordered_fold_set_from_split_manifest_and_split_attestation","reject_missing_duplicate_extra_or_reordered_fold_identity","recompute_candidate_identity_split_identity_every_accepted_validation_gate_and_aggregate_pass_status","emit_authorization_receipt_only_when_every_accepted_gate_passes","emit_termination_not_validation_authority_when_any_gate_fails","reverify_result_evidence_and_all_gate_results_on_restore_before_transition_use"],
    "wf_validation_result_evidence_field_contract":{"accepted_validation_contract_hashes":"complete_object_sorted_by_contract_id_to_hash_resolved_from_accepted_P2_semantic_authority_no_subset_or_extra","candidate_lock_receipt_hash":"sha256","created_at_utc":"audit_timestamp_utc","evidence_schema_id":"constant:H40_WF_VALIDATION_RESULT_EVIDENCE_V1","fold_result_entries":"array_in_authoritative_split_order","locked_slot_hash":"sha256","locked_slot_index":"integer_0_through_167","locked_structural_configuration_hash":"sha256","run_authority_id":"sha256","split_attestation_hash":"sha256","split_manifest_hash":"sha256","validation_protocol_id":"constant:H40_PROTOCOL_V1_R3"}
  },
  "confirmation_ready_receipt_contract":{"authority_rules":["wf_authorization_receipt_must_be_reverified","candidate_run_and_split_lineage_must_match_exactly","receipt_grants_waiting_state_only","receipt_grants_no_confirmation_data_or_outcome_access","f02_status_must_equal_OPEN_SEALED"],"authorized_transition":["H40_WALK_FORWARD_VALIDATED","H40_CONFIRMATION_READY"],"receipt_field_contract":{"confirmation_partition_end_utc":"constant:2026-02-01T00:00:00Z","confirmation_partition_name":"constant:CONFIRMATION_HOLDOUT","confirmation_partition_start_utc":"constant:2025-02-01T00:00:00Z","f02_blocker_status":"constant:OPEN_SEALED","locked_slot_hash":"sha256_equal_wf_authorization","locked_slot_index":"integer_equal_wf_authorization","locked_structural_configuration_hash":"sha256_equal_wf_authorization","prepared_at_utc":"audit_timestamp_utc","receipt_schema_id":"constant:H40_RECEIPT_CONFIRMATION_READY_V2","run_authority_id":"sha256_equal_wf_authorization","split_attestation_hash":"sha256_equal_verified_wf_evidence","split_manifest_hash":"sha256_equal_verified_wf_evidence","upstream_receipt_hash":"sha256_of_wf_validation_authorization_receipt","wf_validation_receipt_hash":"sha256_equal_upstream_receipt_hash"},"receipt_hash_rule":"canonical_sha256(exact_receipt_field_contract_keys_only)","schema_id":"H40_LIFECYCLE_CHILD_CONFIRMATION_READY_V1"},
  "termination_receipt_contract":{"accepted_reason_codes":["CONFIG_IDENTITY_CONFLICT","CONFIRMATION_HOLD_LOCKED","CONFIRMATION_NOT_READY","DUPLICATE_TIMESTAMP","EXECUTION_DISABLED","FAMILY_PAIR_RESTRICTED","HORIZON_TRUNCATED","INTERVAL_MISMATCH","LOOKBACK_RESERVED","NOT_TESTABLE","OUTSIDE_PREREGISTERED_SPLIT","PIT_UNAVAILABLE","PRODUCT_MISMATCH","PROTECTED_SURFACE_DENIED","PURGE_BOUNDARY","SEARCH_BUDGET_EXHAUSTED","SOURCE_GAP","SOURCE_HASH_MISMATCH","SOURCE_MISSING","SOURCE_UNVERIFIED","THRESHOLD_UNMET","UNAUTHORIZED_FAMILY"],"authority_rules":["termination_receipt_never_authorizes_forward_progress","H40_NO_GO_and_NOT_TESTABLE_are_absorbing","reason_code_must_belong_to_the_accepted_H40ReasonCode_vocabulary","failure_evidence_when_present_must_be_loaded_and_content_hash_verified","source_state_and_upstream_receipt_must_match_current_verified_chain"],"receipt_field_contract":{"detail_message":"audit_string","failure_evidence_hash":"sha256_or_null","reason_code":"accepted_H40ReasonCode","receipt_schema_id":"constant:H40_RECEIPT_TERMINATION_V2","run_authority_id":"sha256","source_state":"current_lifecycle_state","target_state":"enum:H40_NO_GO_or_NOT_TESTABLE","terminated_at_utc":"audit_timestamp_utc","upstream_receipt_hash":"current_verified_receipt_sha256_or_null"},"receipt_hash_rule":"canonical_sha256(exact_receipt_field_contract_keys_only)","schema_id":"H40_LIFECYCLE_CHILD_TERMINATION_V1","terminal_states":["H40_NO_GO","NOT_TESTABLE"]},
  "transition_matrix_contract":{"global_rules":["state_adjacency_is_necessary_never_sufficient","current_executable_HEAD_is_never_required_to_equal_historical_P1_commit","P1_scaffold_transition_verifies_historical_acceptance_artifact_integrity_and_frozen_scientific_identity","executable_authority_for_discovery_is_the_accepted_lifecycle_implementation_authority","all_unlisted_transitions_are_forbidden","terminal_states_are_absorbing"],"historical_scaffold_lineage":{"p1_accepted_code_baseline_commit_sha":"3fc89541ed0965fc0e2972af310e34ae1b838168","p1_final_acceptance_commit_sha":"95ab819d5300312b4d493b9585b4b369621504b6","p2_acceptance_record_commit_sha":"8c4e486752feadf8810ba853f27eaad5cb0b88a9","p2_accepted_code_baseline_commit_sha":"cfefdbabfeef8ab004e43bbda24038e4d5e3fca0","p2_final_acceptance_commit_sha":"5f1618ed73a91c954c1443f62f77152682b33ef4","p2r1_implementation_commit_sha":"255148c49754b70365816106d97dc21fcd1955ce","rule":"verify_historical_lineage_and_artifact_integrity_only_never_current_executable_HEAD_equality"},"rows":[{"authority":"P1_LINEAGE_VERIFIER_V1","source":"H40_PREREGISTERED","target":"H40_P1_SCAFFOLDED"},{"authority":"H40_RECEIPT_DISCOVERY_AUTH_V2","source":"H40_P1_SCAFFOLDED","target":"H40_DISCOVERY"},{"authority":"H40_RECEIPT_TERMINATION_V2","source":"H40_P1_SCAFFOLDED","target":"H40_NO_GO"},{"authority":"H40_RECEIPT_TERMINATION_V2","source":"H40_P1_SCAFFOLDED","target":"NOT_TESTABLE"},{"authority":"H40_RECEIPT_CANDIDATE_LOCK_V2_AFTER_RESULT_RECOMPUTATION","source":"H40_DISCOVERY","target":"H40_CANDIDATE_LOCKED"},{"authority":"H40_RECEIPT_TERMINATION_V2","source":"H40_DISCOVERY","target":"H40_NO_GO"},{"authority":"H40_RECEIPT_TERMINATION_V2","source":"H40_DISCOVERY","target":"NOT_TESTABLE"},{"authority":"H40_RECEIPT_WF_VALIDATION_V2_AFTER_RESULT_RECOMPUTATION","source":"H40_CANDIDATE_LOCKED","target":"H40_WALK_FORWARD_VALIDATED"},{"authority":"H40_RECEIPT_TERMINATION_V2_NO_RUNNER_UP","source":"H40_CANDIDATE_LOCKED","target":"H40_NO_GO"},{"authority":"H40_RECEIPT_CONFIRMATION_READY_V2","source":"H40_WALK_FORWARD_VALIDATED","target":"H40_CONFIRMATION_READY"},{"authority":"H40_RECEIPT_TERMINATION_V2","source":"H40_WALK_FORWARD_VALIDATED","target":"H40_NO_GO"},{"authority":"PROHIBITED_BY_H40_FSA_F02","source":"H40_CONFIRMATION_READY","target":"H40_CONFIRMATION_EVALUATED_ONCE"},{"authority":"H40_RECEIPT_TERMINATION_V2","source":"H40_CONFIRMATION_READY","target":"H40_NO_GO"}],"schema_id":"H40_LIFECYCLE_CHILD_TRANSITION_MATRIX_V1"},
  "persistence_replay_contract":{"authorization_receipt_issuance":"only_the_accepted_implementation_verifier_may_atomically_construct_and_persist_authorization_after_recomputation_external_caller_receipts_are_inputs_for_reverification_not_trusted_claims","canonical_storage_key":"artifacts/h40/lifecycle/runs/<run_authority_id>","cross_boundary_checks":["run_authority_id_equal_at_every_chain_link","candidate_identity_equal_from_lock_through_confirmation_ready","split_manifest_and_attestation_equal_from_discovery_through_confirmation_ready","upstream_hash_equal_recomputed_predecessor_hash","lifecycle_governance_and_implementation_authorities_equal_accepted_values"],"failure_semantics":"any_missing_extra_malformed_hash_mismatch_lineage_mismatch_cross_run_cross_candidate_or_cross_split_condition_fails_closed_with_no_state_advance","persistence_rules":["write_canonical_JSON_with_atomic_create_if_absent","different_bytes_at_existing_transition_key_are_rejected","identical_bytes_are_idempotent_only_after_full_reverification","restore_recomputes_every_content_hash_and_every_authoritative_verifier_result","directory_filename_and_caller_label_have_no_authority","authorization_receipts_and_bound_result_evidence_are_write_once"],"run_authority_field_contract":{"discovery_selection_correction_contract_hash":"constant:f84c97050c7db813263e5ffda6b1c556af0b7b0e2876bb8616640d2c9d67084b","lifecycle_governance_authority_hash":"accepted_sha256","lifecycle_implementation_authority_hash":"accepted_sha256","materialized_run_authority_hash":"sha256","protocol_authority_hash":"constant:a83f8fc7a5ca7109fb8cd7fed114d87c3b2c968b5145c11cada203aa5111d1ce","schema_id":"constant:H40_RUN_AUTHORITY_V1","sealed_registered_roster_hash":"sha256","semantic_root_hash":"constant:71889a35f227ed734272b712851174a69bf9dbb12ea3f87cd84c26e7c66f6af1","source_manifest_hash":"sha256","split_attestation_hash":"sha256","split_manifest_hash":"sha256","structural_ledger_hash":"constant:483f68502b57972deae071c7bd4587ca3e57ccaa72bd99fb0de07b4f0ab8c85f"},"run_authority_rule":"run_authority_id_equals_canonical_sha256_of_exact_run_authority_field_contract_keys_only","run_instance_nonce":"none","schema_id":"H40_LIFECYCLE_CHILD_PERSISTENCE_REPLAY_V1","timestamp_rule":"exact_YYYY-MM-DDTHH:MM:SSZ_calendar_valid_UTC_hash_bound_audit_only_never_authorization_critical_no_clock_tolerance"},
  "runtime_snapshot_seal_contract":{"materialized_run_authority_binding":["runtime_authority_snapshot_hash","source_manifest_hash","split_manifest_hash","split_attestation_hash","sealed_registered_roster_hash","registered_slot_count","not_testable_slot_count","total_slot_count"],"roster_entry_field_contract":{"family_id":"accepted_family_id","slot_hash":"sha256","slot_index":"integer_0_through_167","structural_configuration_hash":"sha256"},"roster_hash_rule":"canonical_sha256(array_of_exact_roster_entries_sorted_by_structural_configuration_hash_ascending)","schema_id":"H40_LIFECYCLE_CHILD_RUNTIME_SNAPSHOT_SEAL_V1","seal_rules":["seal_before_any_discovery_label_return_metric_or_candidate_result_access","REGISTERED_and_NOT_TESTABLE_are_derived_from_the_sealed_materialized_authority","counts_must_sum_to_total_slot_count_and_roster_length_must_equal_registered_slot_count","roster_entries_must_match_the_accepted_168_row_structural_ledger","post_seal_source_state_change_cannot_mutate_or_expand_the_active_roster","a_different_snapshot_or_materialized_authority_produces_a_different_run_authority_id","runtime_source_state_changes_never_change_protocol_semantic_or_structural_ledger_hashes"]},
  "f02_boundary_contract":{"allowed_scope":"define_H40ConfirmationReadyReceipt_and_verified_lineage_only","confirmation_state":"sealed_waiting_state_only","forbidden_capabilities":["confirmation_nonce","confirmation_unlock_key","one_shot_evaluation_authority","confirmation_outcome_access","confirmation_evaluation_execution"],"guard_result":"H40GuardError_with_CONFIRMATION_NOT_READY","prohibited_transition":["H40_CONFIRMATION_READY","H40_CONFIRMATION_EVALUATED_ONCE"],"schema_id":"H40_LIFECYCLE_CHILD_F02_BOUNDARY_V1","status":"H40_FSA_F02_OPEN_SEALED"}
}
'''

_LIFECYCLE_CONTRACTS: dict[str, Any] = json.loads(_LIFECYCLE_CONTRACTS_JSON)

EXPECTED_LIFECYCLE_CHILD_HASHES: Mapping[str, str] = MappingProxyType({
    "discovery_authorization_receipt_contract": "8889aaec90e6b25efa9f269ccd38af13be32c665a72248342d01dc145c860b65",
    "candidate_lock_receipt_contract": "96756dfebab636baa1abb33364e307d99d90a61572b813c6a60504283d3d42df",
    "wf_validation_receipt_contract": "bb5698a85daec1a5b9dcd169bde3d575befe8c0a1d73c2e87136cf35afb4001b",
    "confirmation_ready_receipt_contract": "7ab0ae0c8acb17340eccaa2bb737a5300e679b8de7497a539bdc44e93d3109be",
    "termination_receipt_contract": "b45c7021db1c63a447ddb22a1f9cb787ce71a5048c824ce38d40f19f755ecb48",
    "transition_matrix_contract": "58c8eefe64afd130c6244e40e3bc9ce3a6ef25f418bc7be18dced5defa56e1d3",
    "persistence_replay_contract": "ae6582d64d3f0bdb9b7c8773ce758d011670ea7b7bbf433585806345aa239c26",
    "runtime_snapshot_seal_contract": "0c44b6f306d7d562338bdaf901543e09ccd4ea8cf1d4fbb79fb4edbff7bc2f35",
    "f02_boundary_contract": "5678d8bd6b83bb69e1a1ad2cf78af8ddbaece625a5a34b7018b0a5e6368756f4",
})


def lifecycle_semantic_contracts() -> dict[str, Any]:
    """Return a detached copy of the nine accepted canonical child objects."""
    return cast(dict[str, Any], json.loads(json.dumps(_LIFECYCLE_CONTRACTS, ensure_ascii=False)))


def compute_lifecycle_child_hashes(
    contracts: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    objects = lifecycle_semantic_contracts() if contracts is None else dict(contracts)
    if frozenset(objects) != frozenset(EXPECTED_LIFECYCLE_CHILD_HASHES):
        raise ValueError("lifecycle child contract name set mismatch")
    return {name: canonical_sha256(objects[name]) for name in objects}


def lifecycle_semantic_root_preimage(
    contracts: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    hashes = compute_lifecycle_child_hashes(contracts)
    root = {f"{name}_hash": digest for name, digest in hashes.items()}
    root["schema_id"] = "H40_LIFECYCLE_SEMANTIC_ROOT_V1"
    return root


def compute_lifecycle_semantic_root_hash(
    contracts: Mapping[str, Any] | None = None,
) -> str:
    return canonical_sha256(lifecycle_semantic_root_preimage(contracts))


def lifecycle_governance_authority_object() -> dict[str, Any]:
    return {
        "lifecycle_semantic_root_hash": compute_lifecycle_semantic_root_hash(),
        "p2_final_acceptance_identity": {
            "artifact_path": "reviews/v0.5/V0.5.1_H40_P2_FINAL_INDEPENDENT_ACCEPTANCE.md",
            "commit_sha": "5f1618ed73a91c954c1443f62f77152682b33ef4",
        },
        "p3r0r1_amendment_artifact_path": "reviews/v0.5/V0.5.1_H40_P3R0R1_LIFECYCLE_EVIDENCE_AUTHORITY_REPAIR.md",
        "p3r0r1_amendment_commit_sha": "89b014389b371ae1256d9b31ded86f10dd3b4783",
        "protocol_authority_hash": compute_protocol_authority_hash(),
        "schema_id": "H40_LIFECYCLE_GOVERNANCE_AUTHORITY_V2",
        "semantic_root_hash": compute_semantic_root_hash(),
        "structural_ledger_hash": EXPECTED_STRUCTURAL_LEDGER_HASH,
    }


def compute_lifecycle_governance_authority_hash() -> str:
    return canonical_sha256(lifecycle_governance_authority_object())


@dataclass(frozen=True)
class H40RequiredTestCIEvidenceIdentity:
    evidence_manifest_artifact_path: str
    evidence_manifest_sha256: str
    tested_commit_sha: str

    _KEYS: ClassVar[frozenset[str]] = frozenset({
        "evidence_manifest_artifact_path",
        "evidence_manifest_sha256",
        "tested_commit_sha",
    })

    def __post_init__(self) -> None:
        _require_text(self.evidence_manifest_artifact_path, "evidence_manifest_artifact_path")
        _require_sha256(self.evidence_manifest_sha256, "evidence_manifest_sha256")
        _require_commit(self.tested_commit_sha, "tested_commit_sha")

    def to_dict(self) -> dict[str, str]:
        return {
            "evidence_manifest_artifact_path": self.evidence_manifest_artifact_path,
            "evidence_manifest_sha256": self.evidence_manifest_sha256,
            "tested_commit_sha": self.tested_commit_sha,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40RequiredTestCIEvidenceIdentity:
        _require_exact_keys(data, cls._KEYS, cls.__name__)
        _require_string_fields(data, cls._KEYS, cls.__name__)
        return cls(
            evidence_manifest_artifact_path=str(data["evidence_manifest_artifact_path"]),
            evidence_manifest_sha256=str(data["evidence_manifest_sha256"]),
            tested_commit_sha=str(data["tested_commit_sha"]),
        )


@dataclass(frozen=True)
class H40LifecycleImplementationAuthority:
    accepted_lifecycle_governance_authority_hash: str
    f01_implementation_acceptance_artifact_path: str
    f01_implementation_acceptance_commit_sha: str
    f01_implementation_commit_sha: str
    required_test_ci_evidence_identity: H40RequiredTestCIEvidenceIdentity
    schema_id: str = "H40_LIFECYCLE_IMPLEMENTATION_AUTHORITY_V1"

    _KEYS: ClassVar[frozenset[str]] = frozenset({
        "accepted_lifecycle_governance_authority_hash",
        "f01_implementation_acceptance_artifact_path",
        "f01_implementation_acceptance_commit_sha",
        "f01_implementation_commit_sha",
        "required_test_ci_evidence_identity",
        "schema_id",
    })

    def __post_init__(self) -> None:
        if self.schema_id != "H40_LIFECYCLE_IMPLEMENTATION_AUTHORITY_V1":
            raise ValueError("implementation authority schema mismatch")
        if not isinstance(self.required_test_ci_evidence_identity, H40RequiredTestCIEvidenceIdentity):
            raise TypeError("required_test_ci_evidence_identity must use the typed schema")
        if self.accepted_lifecycle_governance_authority_hash != compute_lifecycle_governance_authority_hash():
            raise ValueError("implementation authority governance hash is not accepted")
        _require_text(
            self.f01_implementation_acceptance_artifact_path,
            "f01_implementation_acceptance_artifact_path",
        )
        _require_commit(
            self.f01_implementation_acceptance_commit_sha,
            "f01_implementation_acceptance_commit_sha",
        )
        _require_commit(self.f01_implementation_commit_sha, "f01_implementation_commit_sha")
        if self.required_test_ci_evidence_identity.tested_commit_sha != self.f01_implementation_commit_sha:
            raise ValueError("test/CI evidence tested_commit_sha must equal implementation commit")

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted_lifecycle_governance_authority_hash": self.accepted_lifecycle_governance_authority_hash,
            "f01_implementation_acceptance_artifact_path": self.f01_implementation_acceptance_artifact_path,
            "f01_implementation_acceptance_commit_sha": self.f01_implementation_acceptance_commit_sha,
            "f01_implementation_commit_sha": self.f01_implementation_commit_sha,
            "required_test_ci_evidence_identity": self.required_test_ci_evidence_identity.to_dict(),
            "schema_id": self.schema_id,
        }

    @property
    def lifecycle_implementation_authority_hash(self) -> str:
        return canonical_sha256(self.to_dict())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40LifecycleImplementationAuthority:
        _require_exact_keys(data, cls._KEYS, cls.__name__)
        _require_string_fields(
            data,
            cls._KEYS - {"required_test_ci_evidence_identity"},
            cls.__name__,
        )
        nested = data["required_test_ci_evidence_identity"]
        if not isinstance(nested, Mapping):
            raise TypeError("required_test_ci_evidence_identity must be an object")
        return cls(
            accepted_lifecycle_governance_authority_hash=str(
                data["accepted_lifecycle_governance_authority_hash"]
            ),
            f01_implementation_acceptance_artifact_path=str(
                data["f01_implementation_acceptance_artifact_path"]
            ),
            f01_implementation_acceptance_commit_sha=str(
                data["f01_implementation_acceptance_commit_sha"]
            ),
            f01_implementation_commit_sha=str(data["f01_implementation_commit_sha"]),
            required_test_ci_evidence_identity=H40RequiredTestCIEvidenceIdentity.from_dict(nested),
            schema_id=str(data["schema_id"]),
        )


@dataclass(frozen=True, order=True)
class H40RuntimeRosterEntry:
    structural_configuration_hash: str
    family_id: str = field(compare=False)
    slot_hash: str = field(compare=False)
    slot_index: int = field(compare=False)

    _KEYS: ClassVar[frozenset[str]] = frozenset({
        "family_id", "slot_hash", "slot_index", "structural_configuration_hash"
    })

    def __post_init__(self) -> None:
        _require_sha256(self.structural_configuration_hash, "structural_configuration_hash")
        _require_text(self.family_id, "family_id")
        _require_sha256(self.slot_hash, "slot_hash")
        if isinstance(self.slot_index, bool) or not isinstance(self.slot_index, int) or not 0 <= self.slot_index < 168:
            raise ValueError("slot_index must be an integer in 0..167")

    def to_dict(self) -> dict[str, Any]:
        return {
            "family_id": self.family_id,
            "slot_hash": self.slot_hash,
            "slot_index": self.slot_index,
            "structural_configuration_hash": self.structural_configuration_hash,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40RuntimeRosterEntry:
        _require_exact_keys(data, cls._KEYS, cls.__name__)
        _require_string_fields(data, cls._KEYS - {"slot_index"}, cls.__name__)
        slot_index = data["slot_index"]
        if isinstance(slot_index, bool) or not isinstance(slot_index, int):
            raise TypeError("slot_index must be an integer")
        return cls(
            family_id=str(data["family_id"]),
            slot_hash=str(data["slot_hash"]),
            slot_index=slot_index,
            structural_configuration_hash=str(data["structural_configuration_hash"]),
        )


def _slot_family_id(families: Sequence[Any]) -> str:
    return "+".join(str(getattr(item, "value", item)) for item in families)


@dataclass(frozen=True)
class H40RuntimeSnapshotSeal:
    runtime_authority_snapshot_hash: str
    source_manifest_hash: str
    split_manifest_hash: str
    split_attestation_hash: str
    roster: tuple[H40RuntimeRosterEntry, ...]
    registered_slot_count: int
    not_testable_slot_count: int
    total_slot_count: int = 168
    synthetic_only: bool = field(default=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        roster = tuple(self.roster)
        if not all(isinstance(item, H40RuntimeRosterEntry) for item in roster):
            raise TypeError("roster entries must use H40RuntimeRosterEntry")
        object.__setattr__(self, "roster", roster)
        for name in (
            "runtime_authority_snapshot_hash",
            "source_manifest_hash",
            "split_manifest_hash",
            "split_attestation_hash",
        ):
            _require_sha256(getattr(self, name), name)
        for name in ("registered_slot_count", "not_testable_slot_count", "total_slot_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
        if self.total_slot_count != 168:
            raise ValueError("accepted H40 V1 total_slot_count must equal 168")
        if self.registered_slot_count < 0 or self.not_testable_slot_count < 0:
            raise ValueError("slot counts must be non-negative")
        if self.registered_slot_count + self.not_testable_slot_count != self.total_slot_count:
            raise ValueError("registered + not_testable must equal total")
        if len(self.roster) != self.registered_slot_count:
            raise ValueError("roster length must equal registered_slot_count")
        ordered = tuple(sorted(self.roster, key=lambda item: item.structural_configuration_hash))
        if self.roster != ordered:
            raise ValueError("roster must be ordered by structural_configuration_hash")
        indices = [item.slot_index for item in self.roster]
        configs = [item.structural_configuration_hash for item in self.roster]
        if len(indices) != len(set(indices)) or len(configs) != len(set(configs)):
            raise ValueError("duplicate roster slot/config identity")

    @property
    def sealed_registered_roster_hash(self) -> str:
        return canonical_sha256([entry.to_dict() for entry in self.roster])

    @property
    def materialized_run_authority_hash(self) -> str:
        return MaterializedRunAuthority(
            structural_ledger_hash=EXPECTED_STRUCTURAL_LEDGER_HASH,
            runtime_authority_snapshot_hash=self.runtime_authority_snapshot_hash,
        ).materialized_run_authority_hash

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_authority_snapshot_hash": self.runtime_authority_snapshot_hash,
            "source_manifest_hash": self.source_manifest_hash,
            "split_manifest_hash": self.split_manifest_hash,
            "split_attestation_hash": self.split_attestation_hash,
            "sealed_registered_roster_hash": self.sealed_registered_roster_hash,
            "registered_slot_count": self.registered_slot_count,
            "not_testable_slot_count": self.not_testable_slot_count,
            "total_slot_count": self.total_slot_count,
        }

    def verify_against_accepted_ledger(self) -> None:
        from .search_space import materialize_h40_search_space_production

        ledger = materialize_h40_search_space_production()
        if ledger.structural_ledger_hash != EXPECTED_STRUCTURAL_LEDGER_HASH:
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "structural ledger hash mismatch")
        by_index = {slot.slot_index: slot for slot in ledger.slots}
        for entry in self.roster:
            slot = by_index.get(entry.slot_index)
            if (
                slot is None
                or slot.status != "REGISTERED"
                or slot.slot_hash != entry.slot_hash
                or slot.structural_configuration_hash != entry.structural_configuration_hash
                or _slot_family_id(slot.family_combination) != entry.family_id
            ):
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    f"roster entry {entry.slot_index} does not match accepted REGISTERED slot",
                )

    @classmethod
    def from_current_production_authority(
        cls,
        *,
        source_manifest_hash: str,
        split_manifest_hash: str,
        split_attestation_hash: str,
    ) -> H40RuntimeSnapshotSeal:
        from .search_space import materialize_h40_search_space_production

        ledger = materialize_h40_search_space_production()
        snapshot = current_p1_authority_snapshot()
        registered = tuple(
            sorted(
                (
                    H40RuntimeRosterEntry(
                        family_id=_slot_family_id(slot.family_combination),
                        slot_hash=slot.slot_hash,
                        slot_index=slot.slot_index,
                        structural_configuration_hash=slot.structural_configuration_hash,
                    )
                    for slot in ledger.slots
                    if slot.status == "REGISTERED"
                ),
                key=lambda item: item.structural_configuration_hash,
            )
        )
        seal = cls(
            runtime_authority_snapshot_hash=snapshot.runtime_authority_snapshot_hash,
            source_manifest_hash=source_manifest_hash,
            split_manifest_hash=split_manifest_hash,
            split_attestation_hash=split_attestation_hash,
            roster=registered,
            registered_slot_count=len(registered),
            not_testable_slot_count=ledger.slot_count - len(registered),
        )
        seal.verify_against_accepted_ledger()
        return seal

    @classmethod
    def synthetic_for_tests(
        cls,
        *,
        runtime_authority_snapshot_hash: str,
        source_manifest_hash: str,
        split_manifest_hash: str,
        split_attestation_hash: str,
        roster: Sequence[H40RuntimeRosterEntry],
        not_testable_slot_count: int,
    ) -> H40RuntimeSnapshotSeal:
        ordered = tuple(sorted(roster, key=lambda item: item.structural_configuration_hash))
        return cls(
            runtime_authority_snapshot_hash=runtime_authority_snapshot_hash,
            source_manifest_hash=source_manifest_hash,
            split_manifest_hash=split_manifest_hash,
            split_attestation_hash=split_attestation_hash,
            roster=ordered,
            registered_slot_count=len(ordered),
            not_testable_slot_count=not_testable_slot_count,
            synthetic_only=True,
        )


@dataclass(frozen=True)
class H40RunAuthority:
    discovery_selection_correction_contract_hash: str
    lifecycle_governance_authority_hash: str
    lifecycle_implementation_authority_hash: str
    materialized_run_authority_hash: str
    protocol_authority_hash: str
    sealed_registered_roster_hash: str
    semantic_root_hash: str
    source_manifest_hash: str
    split_attestation_hash: str
    split_manifest_hash: str
    structural_ledger_hash: str
    schema_id: str = "H40_RUN_AUTHORITY_V1"

    _KEYS: ClassVar[frozenset[str]] = frozenset({
        "discovery_selection_correction_contract_hash",
        "lifecycle_governance_authority_hash",
        "lifecycle_implementation_authority_hash",
        "materialized_run_authority_hash",
        "protocol_authority_hash",
        "sealed_registered_roster_hash",
        "semantic_root_hash",
        "source_manifest_hash",
        "split_attestation_hash",
        "split_manifest_hash",
        "structural_ledger_hash",
        "schema_id",
    })

    def __post_init__(self) -> None:
        if self.schema_id != "H40_RUN_AUTHORITY_V1":
            raise ValueError("run authority schema mismatch")
        for name in self._KEYS - {"schema_id"}:
            _require_sha256(getattr(self, name), name)

    def to_dict(self) -> dict[str, str]:
        return {name: str(getattr(self, name)) for name in self._KEYS}

    @property
    def run_authority_id(self) -> str:
        return canonical_sha256(self.to_dict())

    @classmethod
    def from_seal(
        cls,
        seal: H40RuntimeSnapshotSeal,
        lifecycle_implementation_authority_hash: str,
    ) -> H40RunAuthority:
        return cls(
            discovery_selection_correction_contract_hash=DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH,
            lifecycle_governance_authority_hash=compute_lifecycle_governance_authority_hash(),
            lifecycle_implementation_authority_hash=lifecycle_implementation_authority_hash,
            materialized_run_authority_hash=seal.materialized_run_authority_hash,
            protocol_authority_hash=compute_protocol_authority_hash(),
            sealed_registered_roster_hash=seal.sealed_registered_roster_hash,
            semantic_root_hash=compute_semantic_root_hash(),
            source_manifest_hash=seal.source_manifest_hash,
            split_attestation_hash=seal.split_attestation_hash,
            split_manifest_hash=seal.split_manifest_hash,
            structural_ledger_hash=EXPECTED_STRUCTURAL_LEDGER_HASH,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40RunAuthority:
        _require_exact_keys(data, cls._KEYS, cls.__name__)
        _require_string_fields(data, cls._KEYS, cls.__name__)
        return cls(**{name: str(data[name]) for name in cls._KEYS})


@dataclass(frozen=True)
class H40DiscoveryAuthorizationReceipt:
    authorized_at_utc: str
    discovery_selection_correction_contract_hash: str
    execution_disabled: bool
    lifecycle_governance_authority_hash: str
    lifecycle_implementation_authority_hash: str
    materialized_run_authority_hash: str
    not_testable_slot_count: int
    protocol_authority_hash: str
    registered_slot_count: int
    run_authority_id: str
    sealed_registered_roster_hash: str
    semantic_root_hash: str
    source_manifest_hash: str
    split_attestation_hash: str
    split_manifest_hash: str
    structural_ledger_hash: str
    total_slot_count: int
    upstream_receipt_hash: None = None
    receipt_schema_id: str = "H40_RECEIPT_DISCOVERY_AUTH_V2"

    _KEYS: ClassVar[frozenset[str]] = frozenset({
        "authorized_at_utc", "discovery_selection_correction_contract_hash",
        "execution_disabled", "lifecycle_governance_authority_hash",
        "lifecycle_implementation_authority_hash", "materialized_run_authority_hash",
        "not_testable_slot_count", "protocol_authority_hash", "receipt_schema_id",
        "registered_slot_count", "run_authority_id", "sealed_registered_roster_hash",
        "semantic_root_hash", "source_manifest_hash", "split_attestation_hash",
        "split_manifest_hash", "structural_ledger_hash", "total_slot_count",
        "upstream_receipt_hash",
    })

    def __post_init__(self) -> None:
        if self.receipt_schema_id != "H40_RECEIPT_DISCOVERY_AUTH_V2":
            raise ValueError("discovery receipt schema mismatch")
        normalize_audit_timestamp(self.authorized_at_utc)
        if self.execution_disabled is not True or self.upstream_receipt_hash is not None:
            raise ValueError("discovery receipt must bind execution_disabled=true and null upstream")
        for name in self._KEYS - {
            "authorized_at_utc", "execution_disabled", "not_testable_slot_count",
            "receipt_schema_id", "registered_slot_count", "total_slot_count",
            "upstream_receipt_hash",
        }:
            _require_sha256(getattr(self, name), name)
        for name in ("registered_slot_count", "not_testable_slot_count", "total_slot_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
        if self.registered_slot_count < 0 or self.not_testable_slot_count < 0:
            raise ValueError("discovery slot counts must be non-negative")
        if self.total_slot_count != 168:
            raise ValueError("accepted H40 V1 total_slot_count must equal 168")
        if self.registered_slot_count + self.not_testable_slot_count != self.total_slot_count:
            raise ValueError("discovery receipt slot counts must sum to total")

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self._KEYS}

    @property
    def receipt_sha256(self) -> str:
        return canonical_sha256(self.to_dict())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40DiscoveryAuthorizationReceipt:
        _require_exact_keys(data, cls._KEYS, cls.__name__)
        _require_string_fields(
            data,
            cls._KEYS - {
                "execution_disabled", "not_testable_slot_count", "registered_slot_count",
                "total_slot_count", "upstream_receipt_hash",
            },
            cls.__name__,
        )
        for name in ("not_testable_slot_count", "registered_slot_count", "total_slot_count"):
            if isinstance(data[name], bool) or not isinstance(data[name], int):
                raise TypeError(f"{name} must be an integer")
        if not isinstance(data["execution_disabled"], bool):
            raise TypeError("execution_disabled must be boolean")
        if data["upstream_receipt_hash"] is not None:
            raise ValueError("discovery upstream_receipt_hash must be null")
        kwargs = dict(data)
        return cls(**kwargs)


def _freeze_hash_map(values: Mapping[str, str], name: str) -> Mapping[str, str]:
    copied: dict[str, str] = {}
    for key, value in values.items():
        _require_text(key, f"{name} key")
        copied[key] = _require_sha256(value, f"{name}[{key}]")
    return MappingProxyType(dict(sorted(copied.items())))


@dataclass(frozen=True)
class H40CandidateResultEntry:
    candidate_result_input_evidence_hash: str
    complexity: int
    family_id: str
    hard_gate_input_evidence_hashes: Mapping[str, str]
    net_expectancy_input_evidence_hash: str
    precision_input_evidence_hash: str
    slot_hash: str
    slot_index: int
    structural_configuration_hash: str

    _KEYS: ClassVar[frozenset[str]] = frozenset({
        "candidate_result_input_evidence_hash", "complexity", "family_id",
        "hard_gate_input_evidence_hashes", "net_expectancy_input_evidence_hash",
        "precision_input_evidence_hash", "slot_hash", "slot_index",
        "structural_configuration_hash",
    })

    def __post_init__(self) -> None:
        for name in (
            "candidate_result_input_evidence_hash", "net_expectancy_input_evidence_hash",
            "precision_input_evidence_hash", "slot_hash", "structural_configuration_hash",
        ):
            _require_sha256(getattr(self, name), name)
        _require_text(self.family_id, "family_id")
        if isinstance(self.complexity, bool) or self.complexity not in (1, 2):
            raise ValueError("complexity must be accepted family depth 1 or 2")
        if isinstance(self.slot_index, bool) or not isinstance(self.slot_index, int) or not 0 <= self.slot_index < 168:
            raise ValueError("slot_index must be in 0..167")
        object.__setattr__(
            self,
            "hard_gate_input_evidence_hashes",
            _freeze_hash_map(self.hard_gate_input_evidence_hashes, "hard_gate_input_evidence_hashes"),
        )
        if not self.hard_gate_input_evidence_hashes:
            raise ValueError("hard gate evidence map cannot be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_result_input_evidence_hash": self.candidate_result_input_evidence_hash,
            "complexity": self.complexity,
            "family_id": self.family_id,
            "hard_gate_input_evidence_hashes": dict(self.hard_gate_input_evidence_hashes),
            "net_expectancy_input_evidence_hash": self.net_expectancy_input_evidence_hash,
            "precision_input_evidence_hash": self.precision_input_evidence_hash,
            "slot_hash": self.slot_hash,
            "slot_index": self.slot_index,
            "structural_configuration_hash": self.structural_configuration_hash,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40CandidateResultEntry:
        _require_exact_keys(data, cls._KEYS, cls.__name__)
        _require_string_fields(
            data,
            cls._KEYS - {"complexity", "hard_gate_input_evidence_hashes", "slot_index"},
            cls.__name__,
        )
        gates = data["hard_gate_input_evidence_hashes"]
        if not isinstance(gates, Mapping):
            raise TypeError("hard_gate_input_evidence_hashes must be an object")
        complexity = data["complexity"]
        slot_index = data["slot_index"]
        if isinstance(complexity, bool) or not isinstance(complexity, int):
            raise TypeError("complexity must be an integer")
        if isinstance(slot_index, bool) or not isinstance(slot_index, int):
            raise TypeError("slot_index must be an integer")
        return cls(
            candidate_result_input_evidence_hash=str(data["candidate_result_input_evidence_hash"]),
            complexity=complexity,
            family_id=str(data["family_id"]),
            hard_gate_input_evidence_hashes={str(k): str(v) for k, v in gates.items()},
            net_expectancy_input_evidence_hash=str(data["net_expectancy_input_evidence_hash"]),
            precision_input_evidence_hash=str(data["precision_input_evidence_hash"]),
            slot_hash=str(data["slot_hash"]),
            slot_index=slot_index,
            structural_configuration_hash=str(data["structural_configuration_hash"]),
        )


@dataclass(frozen=True)
class H40DiscoveryResultEvidence:
    candidate_result_entries: tuple[H40CandidateResultEntry, ...]
    correction_input_evidence_manifest_hash: str
    created_at_utc: str
    discovery_authorization_receipt_hash: str
    materialized_run_authority_hash: str
    run_authority_id: str
    sealed_registered_roster_hash: str
    discovery_partition: str = "WF1_CALIBRATION"
    discovery_selection_contract_id: str = "DISCOVERY_SELECTION_V1"
    discovery_selection_correction_contract_hash: str = DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH
    evidence_schema_id: str = "H40_DISCOVERY_RESULT_EVIDENCE_V1"

    _KEYS: ClassVar[frozenset[str]] = frozenset({
        "candidate_result_entries", "correction_input_evidence_manifest_hash",
        "created_at_utc", "discovery_authorization_receipt_hash", "discovery_partition",
        "discovery_selection_contract_id", "discovery_selection_correction_contract_hash",
        "evidence_schema_id", "materialized_run_authority_hash", "run_authority_id",
        "sealed_registered_roster_hash",
    })

    def __post_init__(self) -> None:
        entries = tuple(self.candidate_result_entries)
        if not all(isinstance(item, H40CandidateResultEntry) for item in entries):
            raise TypeError("candidate entries must use H40CandidateResultEntry")
        object.__setattr__(self, "candidate_result_entries", entries)
        if self.evidence_schema_id != "H40_DISCOVERY_RESULT_EVIDENCE_V1":
            raise ValueError("discovery evidence schema mismatch")
        if self.discovery_partition != "WF1_CALIBRATION":
            raise ValueError("discovery partition must be WF1_CALIBRATION")
        if self.discovery_selection_contract_id != "DISCOVERY_SELECTION_V1":
            raise ValueError("discovery selection contract ID mismatch")
        if self.discovery_selection_correction_contract_hash != DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH:
            raise ValueError("discovery selection content hash mismatch")
        normalize_audit_timestamp(self.created_at_utc)
        for name in (
            "correction_input_evidence_manifest_hash", "discovery_authorization_receipt_hash",
            "materialized_run_authority_hash", "run_authority_id", "sealed_registered_roster_hash",
        ):
            _require_sha256(getattr(self, name), name)
        ordered = tuple(sorted(self.candidate_result_entries, key=lambda item: item.structural_configuration_hash))
        if self.candidate_result_entries != ordered:
            raise ValueError("candidate entries must be ordered by structural_configuration_hash")

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_result_entries": [entry.to_dict() for entry in self.candidate_result_entries],
            "correction_input_evidence_manifest_hash": self.correction_input_evidence_manifest_hash,
            "created_at_utc": self.created_at_utc,
            "discovery_authorization_receipt_hash": self.discovery_authorization_receipt_hash,
            "discovery_partition": self.discovery_partition,
            "discovery_selection_contract_id": self.discovery_selection_contract_id,
            "discovery_selection_correction_contract_hash": self.discovery_selection_correction_contract_hash,
            "evidence_schema_id": self.evidence_schema_id,
            "materialized_run_authority_hash": self.materialized_run_authority_hash,
            "run_authority_id": self.run_authority_id,
            "sealed_registered_roster_hash": self.sealed_registered_roster_hash,
        }

    @property
    def evidence_sha256(self) -> str:
        return canonical_sha256(self.to_dict())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40DiscoveryResultEvidence:
        _require_exact_keys(data, cls._KEYS, cls.__name__)
        _require_string_fields(data, cls._KEYS - {"candidate_result_entries"}, cls.__name__)
        entries = data["candidate_result_entries"]
        if not isinstance(entries, list) or not all(isinstance(item, Mapping) for item in entries):
            raise TypeError("candidate_result_entries must be an array of objects")
        return cls(
            candidate_result_entries=tuple(H40CandidateResultEntry.from_dict(item) for item in entries),
            correction_input_evidence_manifest_hash=str(data["correction_input_evidence_manifest_hash"]),
            created_at_utc=str(data["created_at_utc"]),
            discovery_authorization_receipt_hash=str(data["discovery_authorization_receipt_hash"]),
            discovery_partition=str(data["discovery_partition"]),
            discovery_selection_contract_id=str(data["discovery_selection_contract_id"]),
            discovery_selection_correction_contract_hash=str(data["discovery_selection_correction_contract_hash"]),
            evidence_schema_id=str(data["evidence_schema_id"]),
            materialized_run_authority_hash=str(data["materialized_run_authority_hash"]),
            run_authority_id=str(data["run_authority_id"]),
            sealed_registered_roster_hash=str(data["sealed_registered_roster_hash"]),
        )


@dataclass(frozen=True)
class H40CandidateLockReceipt:
    discovery_authorization_receipt_hash: str
    discovery_result_evidence_hash: str
    locked_at_utc: str
    materialized_run_authority_hash: str
    run_authority_id: str
    selected_slot_hash: str
    selected_slot_index: int
    selected_structural_configuration_hash: str
    upstream_receipt_hash: str
    verified_at_utc: str
    discovery_selection_correction_contract_hash: str = DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH
    receipt_schema_id: str = "H40_RECEIPT_CANDIDATE_LOCK_V2"
    selection_verifier_id: str = "H40_DISCOVERY_SELECTION_VERIFIER_V1"

    _KEYS: ClassVar[frozenset[str]] = frozenset({
        "discovery_authorization_receipt_hash", "discovery_result_evidence_hash",
        "discovery_selection_correction_contract_hash", "locked_at_utc",
        "materialized_run_authority_hash", "receipt_schema_id", "run_authority_id",
        "selected_slot_hash", "selected_slot_index", "selected_structural_configuration_hash",
        "selection_verifier_id", "upstream_receipt_hash", "verified_at_utc",
    })

    def __post_init__(self) -> None:
        if self.receipt_schema_id != "H40_RECEIPT_CANDIDATE_LOCK_V2":
            raise ValueError("candidate lock receipt schema mismatch")
        if self.selection_verifier_id != "H40_DISCOVERY_SELECTION_VERIFIER_V1":
            raise ValueError("candidate selection verifier mismatch")
        if self.discovery_selection_correction_contract_hash != DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH:
            raise ValueError("candidate selection content hash mismatch")
        normalize_audit_timestamp(self.locked_at_utc)
        normalize_audit_timestamp(self.verified_at_utc)
        for name in self._KEYS - {
            "locked_at_utc", "receipt_schema_id", "selected_slot_index",
            "selection_verifier_id", "verified_at_utc",
        }:
            _require_sha256(getattr(self, name), name)
        if self.discovery_authorization_receipt_hash != self.upstream_receipt_hash:
            raise ValueError("candidate discovery/upstream receipt hashes differ")
        if (
            isinstance(self.selected_slot_index, bool)
            or not isinstance(self.selected_slot_index, int)
            or not 0 <= self.selected_slot_index < 168
        ):
            raise ValueError("selected_slot_index must be in 0..167")

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self._KEYS}

    @property
    def receipt_sha256(self) -> str:
        return canonical_sha256(self.to_dict())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40CandidateLockReceipt:
        _require_exact_keys(data, cls._KEYS, cls.__name__)
        _require_string_fields(data, cls._KEYS - {"selected_slot_index"}, cls.__name__)
        if isinstance(data["selected_slot_index"], bool) or not isinstance(data["selected_slot_index"], int):
            raise TypeError("selected_slot_index must be an integer")
        return cls(**dict(data))


@dataclass(frozen=True)
class H40WFFoldResultEntry:
    accepted_gate_input_evidence_hashes: Mapping[str, str]
    evaluation_input_evidence_hash: str
    fold_identity_hash: str
    fold_id: str
    partition_id: str
    split_definition_hash: str

    _KEYS: ClassVar[frozenset[str]] = frozenset({
        "accepted_gate_input_evidence_hashes", "evaluation_input_evidence_hash",
        "fold_identity_hash", "fold_id", "partition_id", "split_definition_hash",
    })

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "accepted_gate_input_evidence_hashes",
            _freeze_hash_map(
                self.accepted_gate_input_evidence_hashes,
                "accepted_gate_input_evidence_hashes",
            ),
        )
        if not self.accepted_gate_input_evidence_hashes:
            raise ValueError("accepted gate evidence map cannot be empty")
        for name in ("evaluation_input_evidence_hash", "fold_identity_hash", "split_definition_hash"):
            _require_sha256(getattr(self, name), name)
        _require_text(self.fold_id, "fold_id")
        _require_text(self.partition_id, "partition_id")

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted_gate_input_evidence_hashes": dict(self.accepted_gate_input_evidence_hashes),
            "evaluation_input_evidence_hash": self.evaluation_input_evidence_hash,
            "fold_identity_hash": self.fold_identity_hash,
            "fold_id": self.fold_id,
            "partition_id": self.partition_id,
            "split_definition_hash": self.split_definition_hash,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40WFFoldResultEntry:
        _require_exact_keys(data, cls._KEYS, cls.__name__)
        _require_string_fields(
            data,
            cls._KEYS - {"accepted_gate_input_evidence_hashes"},
            cls.__name__,
        )
        gates = data["accepted_gate_input_evidence_hashes"]
        if not isinstance(gates, Mapping):
            raise TypeError("accepted_gate_input_evidence_hashes must be an object")
        return cls(
            accepted_gate_input_evidence_hashes={str(k): str(v) for k, v in gates.items()},
            evaluation_input_evidence_hash=str(data["evaluation_input_evidence_hash"]),
            fold_identity_hash=str(data["fold_identity_hash"]),
            fold_id=str(data["fold_id"]),
            partition_id=str(data["partition_id"]),
            split_definition_hash=str(data["split_definition_hash"]),
        )


@dataclass(frozen=True)
class H40ExpectedWFFold:
    fold_id: str
    partition_id: str
    split_definition_hash: str

    def __post_init__(self) -> None:
        _require_text(self.fold_id, "fold_id")
        _require_text(self.partition_id, "partition_id")
        _require_sha256(self.split_definition_hash, "split_definition_hash")

    @property
    def fold_identity_hash(self) -> str:
        return canonical_sha256({
            "fold_id": self.fold_id,
            "partition_id": self.partition_id,
            "split_definition_hash": self.split_definition_hash,
        })


@dataclass(frozen=True)
class H40ExpectedSplitAuthority:
    split_manifest_hash: str
    split_attestation_hash: str
    folds: tuple[H40ExpectedWFFold, ...]
    accepted_validation_contract_hashes: Mapping[str, str]

    def __post_init__(self) -> None:
        folds = tuple(self.folds)
        if not all(isinstance(item, H40ExpectedWFFold) for item in folds):
            raise TypeError("folds must use H40ExpectedWFFold")
        object.__setattr__(self, "folds", folds)
        _require_sha256(self.split_manifest_hash, "split_manifest_hash")
        _require_sha256(self.split_attestation_hash, "split_attestation_hash")
        if not self.folds:
            raise ValueError("authoritative WF fold set cannot be empty")
        identities = [fold.fold_identity_hash for fold in self.folds]
        if len(identities) != len(set(identities)):
            raise ValueError("authoritative WF fold identities must be unique")
        object.__setattr__(
            self,
            "accepted_validation_contract_hashes",
            _freeze_hash_map(
                self.accepted_validation_contract_hashes,
                "accepted_validation_contract_hashes",
            ),
        )
        if not self.accepted_validation_contract_hashes:
            raise ValueError("accepted validation contract set cannot be empty")


@dataclass(frozen=True)
class H40WFValidationResultEvidence:
    accepted_validation_contract_hashes: Mapping[str, str]
    candidate_lock_receipt_hash: str
    created_at_utc: str
    fold_result_entries: tuple[H40WFFoldResultEntry, ...]
    locked_slot_hash: str
    locked_slot_index: int
    locked_structural_configuration_hash: str
    run_authority_id: str
    split_attestation_hash: str
    split_manifest_hash: str
    evidence_schema_id: str = "H40_WF_VALIDATION_RESULT_EVIDENCE_V1"
    validation_protocol_id: str = "H40_PROTOCOL_V1_R3"

    _KEYS: ClassVar[frozenset[str]] = frozenset({
        "accepted_validation_contract_hashes", "candidate_lock_receipt_hash",
        "created_at_utc", "evidence_schema_id", "fold_result_entries",
        "locked_slot_hash", "locked_slot_index", "locked_structural_configuration_hash",
        "run_authority_id", "split_attestation_hash", "split_manifest_hash",
        "validation_protocol_id",
    })

    def __post_init__(self) -> None:
        folds = tuple(self.fold_result_entries)
        if not all(isinstance(item, H40WFFoldResultEntry) for item in folds):
            raise TypeError("fold results must use H40WFFoldResultEntry")
        object.__setattr__(self, "fold_result_entries", folds)
        if self.evidence_schema_id != "H40_WF_VALIDATION_RESULT_EVIDENCE_V1":
            raise ValueError("WF result evidence schema mismatch")
        if self.validation_protocol_id != "H40_PROTOCOL_V1_R3":
            raise ValueError("WF validation protocol mismatch")
        normalize_audit_timestamp(self.created_at_utc)
        for name in (
            "candidate_lock_receipt_hash", "locked_slot_hash",
            "locked_structural_configuration_hash", "run_authority_id",
            "split_attestation_hash", "split_manifest_hash",
        ):
            _require_sha256(getattr(self, name), name)
        if (
            isinstance(self.locked_slot_index, bool)
            or not isinstance(self.locked_slot_index, int)
            or not 0 <= self.locked_slot_index < 168
        ):
            raise ValueError("locked_slot_index must be in 0..167")
        object.__setattr__(
            self,
            "accepted_validation_contract_hashes",
            _freeze_hash_map(
                self.accepted_validation_contract_hashes,
                "accepted_validation_contract_hashes",
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted_validation_contract_hashes": dict(self.accepted_validation_contract_hashes),
            "candidate_lock_receipt_hash": self.candidate_lock_receipt_hash,
            "created_at_utc": self.created_at_utc,
            "evidence_schema_id": self.evidence_schema_id,
            "fold_result_entries": [entry.to_dict() for entry in self.fold_result_entries],
            "locked_slot_hash": self.locked_slot_hash,
            "locked_slot_index": self.locked_slot_index,
            "locked_structural_configuration_hash": self.locked_structural_configuration_hash,
            "run_authority_id": self.run_authority_id,
            "split_attestation_hash": self.split_attestation_hash,
            "split_manifest_hash": self.split_manifest_hash,
            "validation_protocol_id": self.validation_protocol_id,
        }

    @property
    def evidence_sha256(self) -> str:
        return canonical_sha256(self.to_dict())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40WFValidationResultEvidence:
        _require_exact_keys(data, cls._KEYS, cls.__name__)
        _require_string_fields(
            data,
            cls._KEYS - {
                "accepted_validation_contract_hashes", "fold_result_entries", "locked_slot_index",
            },
            cls.__name__,
        )
        contracts = data["accepted_validation_contract_hashes"]
        folds = data["fold_result_entries"]
        if not isinstance(contracts, Mapping):
            raise TypeError("accepted_validation_contract_hashes must be an object")
        if not isinstance(folds, list) or not all(isinstance(item, Mapping) for item in folds):
            raise TypeError("fold_result_entries must be an array of objects")
        slot_index = data["locked_slot_index"]
        if isinstance(slot_index, bool) or not isinstance(slot_index, int):
            raise TypeError("locked_slot_index must be an integer")
        return cls(
            accepted_validation_contract_hashes={str(k): str(v) for k, v in contracts.items()},
            candidate_lock_receipt_hash=str(data["candidate_lock_receipt_hash"]),
            created_at_utc=str(data["created_at_utc"]),
            evidence_schema_id=str(data["evidence_schema_id"]),
            fold_result_entries=tuple(H40WFFoldResultEntry.from_dict(item) for item in folds),
            locked_slot_hash=str(data["locked_slot_hash"]),
            locked_slot_index=slot_index,
            locked_structural_configuration_hash=str(data["locked_structural_configuration_hash"]),
            run_authority_id=str(data["run_authority_id"]),
            split_attestation_hash=str(data["split_attestation_hash"]),
            split_manifest_hash=str(data["split_manifest_hash"]),
            validation_protocol_id=str(data["validation_protocol_id"]),
        )


@dataclass(frozen=True)
class H40WFValidationReceipt:
    candidate_lock_receipt_hash: str
    locked_slot_hash: str
    locked_slot_index: int
    locked_structural_configuration_hash: str
    run_authority_id: str
    upstream_receipt_hash: str
    validated_at_utc: str
    verified_at_utc: str
    wf_validation_result_evidence_hash: str
    receipt_schema_id: str = "H40_RECEIPT_WF_VALIDATION_V2"
    validation_verifier_id: str = "H40_WF_VALIDATION_VERIFIER_V1"

    _KEYS: ClassVar[frozenset[str]] = frozenset({
        "candidate_lock_receipt_hash", "locked_slot_hash", "locked_slot_index",
        "locked_structural_configuration_hash", "receipt_schema_id", "run_authority_id",
        "upstream_receipt_hash", "validated_at_utc", "validation_verifier_id",
        "verified_at_utc", "wf_validation_result_evidence_hash",
    })

    def __post_init__(self) -> None:
        if self.receipt_schema_id != "H40_RECEIPT_WF_VALIDATION_V2":
            raise ValueError("WF receipt schema mismatch")
        if self.validation_verifier_id != "H40_WF_VALIDATION_VERIFIER_V1":
            raise ValueError("WF verifier identity mismatch")
        normalize_audit_timestamp(self.validated_at_utc)
        normalize_audit_timestamp(self.verified_at_utc)
        for name in self._KEYS - {
            "locked_slot_index", "receipt_schema_id", "validated_at_utc",
            "validation_verifier_id", "verified_at_utc",
        }:
            _require_sha256(getattr(self, name), name)
        if self.candidate_lock_receipt_hash != self.upstream_receipt_hash:
            raise ValueError("WF candidate/upstream receipt hashes differ")
        if (
            isinstance(self.locked_slot_index, bool)
            or not isinstance(self.locked_slot_index, int)
            or not 0 <= self.locked_slot_index < 168
        ):
            raise ValueError("locked_slot_index must be in 0..167")

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self._KEYS}

    @property
    def receipt_sha256(self) -> str:
        return canonical_sha256(self.to_dict())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40WFValidationReceipt:
        _require_exact_keys(data, cls._KEYS, cls.__name__)
        _require_string_fields(data, cls._KEYS - {"locked_slot_index"}, cls.__name__)
        if isinstance(data["locked_slot_index"], bool) or not isinstance(data["locked_slot_index"], int):
            raise TypeError("locked_slot_index must be an integer")
        return cls(**dict(data))


@dataclass(frozen=True)
class H40ConfirmationReadyReceipt:
    locked_slot_hash: str
    locked_slot_index: int
    locked_structural_configuration_hash: str
    prepared_at_utc: str
    run_authority_id: str
    split_attestation_hash: str
    split_manifest_hash: str
    upstream_receipt_hash: str
    wf_validation_receipt_hash: str
    confirmation_partition_end_utc: str = "2026-02-01T00:00:00Z"
    confirmation_partition_name: str = "CONFIRMATION_HOLDOUT"
    confirmation_partition_start_utc: str = "2025-02-01T00:00:00Z"
    f02_blocker_status: str = "OPEN_SEALED"
    receipt_schema_id: str = "H40_RECEIPT_CONFIRMATION_READY_V2"

    _KEYS: ClassVar[frozenset[str]] = frozenset({
        "confirmation_partition_end_utc", "confirmation_partition_name",
        "confirmation_partition_start_utc", "f02_blocker_status", "locked_slot_hash",
        "locked_slot_index", "locked_structural_configuration_hash", "prepared_at_utc",
        "receipt_schema_id", "run_authority_id", "split_attestation_hash",
        "split_manifest_hash", "upstream_receipt_hash", "wf_validation_receipt_hash",
    })

    def __post_init__(self) -> None:
        constants = (
            (self.confirmation_partition_name, "CONFIRMATION_HOLDOUT"),
            (self.confirmation_partition_start_utc, "2025-02-01T00:00:00Z"),
            (self.confirmation_partition_end_utc, "2026-02-01T00:00:00Z"),
            (self.f02_blocker_status, "OPEN_SEALED"),
            (self.receipt_schema_id, "H40_RECEIPT_CONFIRMATION_READY_V2"),
        )
        if any(actual != expected for actual, expected in constants):
            raise ValueError("confirmation-ready constant mismatch")
        normalize_audit_timestamp(self.prepared_at_utc)
        for name in (
            "locked_slot_hash", "locked_structural_configuration_hash", "run_authority_id",
            "split_attestation_hash", "split_manifest_hash", "upstream_receipt_hash",
            "wf_validation_receipt_hash",
        ):
            _require_sha256(getattr(self, name), name)
        if self.upstream_receipt_hash != self.wf_validation_receipt_hash:
            raise ValueError("confirmation WF/upstream receipt hashes differ")
        if (
            isinstance(self.locked_slot_index, bool)
            or not isinstance(self.locked_slot_index, int)
            or not 0 <= self.locked_slot_index < 168
        ):
            raise ValueError("locked_slot_index must be in 0..167")

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self._KEYS}

    @property
    def receipt_sha256(self) -> str:
        return canonical_sha256(self.to_dict())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40ConfirmationReadyReceipt:
        _require_exact_keys(data, cls._KEYS, cls.__name__)
        _require_string_fields(data, cls._KEYS - {"locked_slot_index"}, cls.__name__)
        if isinstance(data["locked_slot_index"], bool) or not isinstance(data["locked_slot_index"], int):
            raise TypeError("locked_slot_index must be an integer")
        return cls(**dict(data))


@dataclass(frozen=True)
class H40TerminationReceipt:
    detail_message: str
    failure_evidence_hash: str | None
    reason_code: H40ReasonCode
    run_authority_id: str
    source_state: str
    target_state: str
    terminated_at_utc: str
    upstream_receipt_hash: str | None
    receipt_schema_id: str = "H40_RECEIPT_TERMINATION_V2"

    _KEYS: ClassVar[frozenset[str]] = frozenset({
        "detail_message", "failure_evidence_hash", "reason_code", "receipt_schema_id",
        "run_authority_id", "source_state", "target_state", "terminated_at_utc",
        "upstream_receipt_hash",
    })
    _TARGETS: ClassVar[frozenset[str]] = frozenset({"H40_NO_GO", "NOT_TESTABLE"})

    def __post_init__(self) -> None:
        if self.receipt_schema_id != "H40_RECEIPT_TERMINATION_V2":
            raise ValueError("termination receipt schema mismatch")
        if not isinstance(self.reason_code, H40ReasonCode):
            raise TypeError("reason_code must use existing H40ReasonCode")
        _require_text(self.detail_message, "detail_message")
        _require_sha256(self.run_authority_id, "run_authority_id")
        _require_text(self.source_state, "source_state")
        if self.target_state not in self._TARGETS:
            raise ValueError("termination target must be H40_NO_GO or NOT_TESTABLE")
        normalize_audit_timestamp(self.terminated_at_utc)
        if self.failure_evidence_hash is not None:
            _require_sha256(self.failure_evidence_hash, "failure_evidence_hash")
        if self.upstream_receipt_hash is not None:
            _require_sha256(self.upstream_receipt_hash, "upstream_receipt_hash")

    def to_dict(self) -> dict[str, Any]:
        return {
            "detail_message": self.detail_message,
            "failure_evidence_hash": self.failure_evidence_hash,
            "reason_code": self.reason_code.value,
            "receipt_schema_id": self.receipt_schema_id,
            "run_authority_id": self.run_authority_id,
            "source_state": self.source_state,
            "target_state": self.target_state,
            "terminated_at_utc": self.terminated_at_utc,
            "upstream_receipt_hash": self.upstream_receipt_hash,
        }

    @property
    def receipt_sha256(self) -> str:
        return canonical_sha256(self.to_dict())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40TerminationReceipt:
        _require_exact_keys(data, cls._KEYS, cls.__name__)
        _require_string_fields(
            data,
            cls._KEYS - {"failure_evidence_hash", "upstream_receipt_hash"},
            cls.__name__,
        )
        for nullable_hash in ("failure_evidence_hash", "upstream_receipt_hash"):
            if data[nullable_hash] is not None and not isinstance(data[nullable_hash], str):
                raise TypeError(f"{cls.__name__}.{nullable_hash} must be a string or null")
        return cls(
            detail_message=str(data["detail_message"]),
            failure_evidence_hash=(
                None if data["failure_evidence_hash"] is None else str(data["failure_evidence_hash"])
            ),
            reason_code=H40ReasonCode(str(data["reason_code"])),
            receipt_schema_id=str(data["receipt_schema_id"]),
            run_authority_id=str(data["run_authority_id"]),
            source_state=str(data["source_state"]),
            target_state=str(data["target_state"]),
            terminated_at_utc=str(data["terminated_at_utc"]),
            upstream_receipt_hash=(
                None if data["upstream_receipt_hash"] is None else str(data["upstream_receipt_hash"])
            ),
        )


@dataclass(frozen=True)
class _CandidateScore:
    hard_gates_passed: bool
    adjusted_lcb_net_expectancy: Decimal
    adjusted_lcb_precision: Decimal


class H40SyntheticEvidenceVerifier:
    """Explicitly non-authoritative content verifier for synthetic governance tests.

    Production/default lifecycle authority never constructs this verifier and
    remains unable to authorize Discovery until an independent implementation
    authority is published.
    """

    def __init__(self, payloads: Mapping[str, Mapping[str, Any]]) -> None:
        copied: dict[str, Mapping[str, Any]] = {}
        for digest, payload in payloads.items():
            _require_sha256(digest, "synthetic evidence digest")
            detached = json.loads(canonical_json(payload))
            if canonical_sha256(detached) != digest:
                raise ValueError("synthetic evidence key does not match canonical content hash")
            copied[digest] = MappingProxyType(detached)
        self._payloads: dict[str, Mapping[str, Any]] = copied

    def add_payload_for_tests(self, payload: Mapping[str, Any]) -> str:
        """Add immutable synthetic evidence; never available to production authority."""
        detached = json.loads(canonical_json(payload))
        digest = canonical_sha256(detached)
        existing = self._payloads.get(digest)
        frozen = MappingProxyType(detached)
        if existing is not None and canonical_json(existing) != canonical_json(frozen):
            raise ValueError("synthetic content-hash collision")
        self._payloads[digest] = frozen
        return digest

    def _load(self, digest: str) -> Mapping[str, Any]:
        payload = self._payloads.get(digest)
        if payload is None or canonical_sha256(payload) != digest:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"missing or altered content-addressed synthetic evidence {digest}",
            )
        return payload

    @staticmethod
    def _decimal(value: Any, name: str) -> Decimal:
        if not isinstance(value, str):
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, f"{name} must be a decimal string")
        try:
            result = Decimal(value)
        except InvalidOperation as exc:
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, f"invalid {name}") from exc
        if not result.is_finite():
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, f"non-finite {name}")
        return result

    def verify_discovery_manifest(
        self,
        evidence: H40DiscoveryResultEvidence,
        entries: Sequence[H40CandidateResultEntry],
    ) -> None:
        payload = self._load(evidence.correction_input_evidence_manifest_hash)
        expected = frozenset({
            "candidate_structural_configuration_hashes", "discovery_selection_correction_contract_hash",
            "roster_hash", "run_authority_id", "schema_id",
        })
        _require_exact_keys(payload, expected, "synthetic correction manifest")
        if payload["schema_id"] != "H40_SYNTHETIC_CORRECTION_MANIFEST_V1":
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "correction manifest schema mismatch")
        expected_configurations = [entry.structural_configuration_hash for entry in entries]
        if (
            payload["candidate_structural_configuration_hashes"] != expected_configurations
            or payload["run_authority_id"] != evidence.run_authority_id
            or payload["roster_hash"] != evidence.sealed_registered_roster_hash
            or payload["discovery_selection_correction_contract_hash"]
            != DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH
        ):
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "correction manifest binding mismatch")

    def verify_candidate(
        self,
        entry: H40CandidateResultEntry,
        *,
        run_authority_id: str,
        correction_manifest_hash: str,
    ) -> _CandidateScore:
        gate_results: list[bool] = []
        for gate_id, digest in entry.hard_gate_input_evidence_hashes.items():
            payload = self._load(digest)
            expected = frozenset({
                "gate_id", "passed", "run_authority_id", "schema_id",
                "structural_configuration_hash",
            })
            _require_exact_keys(payload, expected, "synthetic candidate gate evidence")
            if (
                payload["schema_id"] != "H40_SYNTHETIC_CANDIDATE_GATE_EVIDENCE_V1"
                or payload["gate_id"] != gate_id
                or payload["run_authority_id"] != run_authority_id
                or payload["structural_configuration_hash"] != entry.structural_configuration_hash
                or not isinstance(payload["passed"], bool)
            ):
                raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "candidate gate binding mismatch")
            gate_results.append(bool(payload["passed"]))

        metrics: dict[str, Decimal] = {}
        for metric_id, digest in (
            ("NET_EXPECTANCY", entry.net_expectancy_input_evidence_hash),
            ("PRECISION", entry.precision_input_evidence_hash),
        ):
            payload = self._load(digest)
            expected = frozenset({
                "adjusted_lcb", "correction_manifest_hash", "metric_id", "run_authority_id",
                "schema_id", "structural_configuration_hash",
            })
            _require_exact_keys(payload, expected, "synthetic candidate metric evidence")
            if (
                payload["schema_id"] != "H40_SYNTHETIC_CANDIDATE_METRIC_EVIDENCE_V1"
                or payload["metric_id"] != metric_id
                or payload["run_authority_id"] != run_authority_id
                or payload["structural_configuration_hash"] != entry.structural_configuration_hash
                or payload["correction_manifest_hash"] != correction_manifest_hash
            ):
                raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "candidate metric binding mismatch")
            metrics[metric_id] = self._decimal(payload["adjusted_lcb"], "adjusted_lcb")

        result = self._load(entry.candidate_result_input_evidence_hash)
        expected_result = frozenset({
            "hard_gate_input_evidence_hashes",
            "net_expectancy_input_evidence_hash", "precision_input_evidence_hash",
            "run_authority_id", "schema_id", "slot_hash", "slot_index",
            "structural_configuration_hash",
        })
        _require_exact_keys(result, expected_result, "synthetic candidate result input")
        if (
            result["schema_id"] != "H40_SYNTHETIC_CANDIDATE_RESULT_INPUT_V1"
            or result["run_authority_id"] != run_authority_id
            or result["slot_hash"] != entry.slot_hash
            or result["slot_index"] != entry.slot_index
            or result["structural_configuration_hash"] != entry.structural_configuration_hash
            or result["hard_gate_input_evidence_hashes"] != dict(entry.hard_gate_input_evidence_hashes)
            or result["net_expectancy_input_evidence_hash"] != entry.net_expectancy_input_evidence_hash
            or result["precision_input_evidence_hash"] != entry.precision_input_evidence_hash
        ):
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "candidate result input binding mismatch")
        return _CandidateScore(
            hard_gates_passed=all(gate_results),
            adjusted_lcb_net_expectancy=metrics["NET_EXPECTANCY"],
            adjusted_lcb_precision=metrics["PRECISION"],
        )

    def verify_wf_fold(
        self,
        entry: H40WFFoldResultEntry,
        *,
        evidence: H40WFValidationResultEvidence,
    ) -> bool:
        gate_results: list[bool] = []
        for gate_id, digest in entry.accepted_gate_input_evidence_hashes.items():
            payload = self._load(digest)
            expected = frozenset({
                "fold_identity_hash", "gate_id", "locked_structural_configuration_hash",
                "passed", "run_authority_id", "schema_id", "split_attestation_hash",
                "split_manifest_hash",
            })
            _require_exact_keys(payload, expected, "synthetic WF gate evidence")
            if (
                payload["schema_id"] != "H40_SYNTHETIC_WF_GATE_EVIDENCE_V1"
                or payload["gate_id"] != gate_id
                or payload["run_authority_id"] != evidence.run_authority_id
                or payload["locked_structural_configuration_hash"]
                != evidence.locked_structural_configuration_hash
                or payload["split_manifest_hash"] != evidence.split_manifest_hash
                or payload["split_attestation_hash"] != evidence.split_attestation_hash
                or payload["fold_identity_hash"] != entry.fold_identity_hash
                or not isinstance(payload["passed"], bool)
            ):
                raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "WF gate binding mismatch")
            gate_results.append(bool(payload["passed"]))
        evaluation = self._load(entry.evaluation_input_evidence_hash)
        expected_eval = frozenset({
            "accepted_gate_input_evidence_hashes", "fold_identity_hash",
            "locked_structural_configuration_hash", "run_authority_id", "schema_id",
            "split_attestation_hash", "split_manifest_hash",
        })
        _require_exact_keys(evaluation, expected_eval, "synthetic WF evaluation input")
        if (
            evaluation["schema_id"] != "H40_SYNTHETIC_WF_EVALUATION_INPUT_V1"
            or evaluation["accepted_gate_input_evidence_hashes"]
            != dict(entry.accepted_gate_input_evidence_hashes)
            or evaluation["fold_identity_hash"] != entry.fold_identity_hash
            or evaluation["run_authority_id"] != evidence.run_authority_id
            or evaluation["locked_structural_configuration_hash"]
            != evidence.locked_structural_configuration_hash
            or evaluation["split_manifest_hash"] != evidence.split_manifest_hash
            or evaluation["split_attestation_hash"] != evidence.split_attestation_hash
        ):
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "WF evaluation binding mismatch")
        return all(gate_results)


_Receipt = (
    H40DiscoveryAuthorizationReceipt
    | H40CandidateLockReceipt
    | H40WFValidationReceipt
    | H40ConfirmationReadyReceipt
    | H40TerminationReceipt
)
_ResultEvidence = H40DiscoveryResultEvidence | H40WFValidationResultEvidence
_VERIFIED_AUTHORITY_TOKEN = object()


class VerifiedLifecycleAuthorization:
    """Opaque, process-local result of deterministic authority verification."""

    _context: Mapping[str, Any]
    _issuer_id: object
    _receipt: _Receipt
    _receipt_hash: str
    _run_authority_id: str
    _sealed: bool
    _source_state: str
    _synthetic_only: bool
    _target_state: str
    _token: object
    _upstream_receipt_hash: str | None

    __slots__ = (
        "_context", "_issuer_id", "_receipt", "_receipt_hash", "_run_authority_id",
        "_sealed", "_source_state", "_synthetic_only", "_target_state", "_token",
        "_upstream_receipt_hash",
    )

    def __init__(
        self,
        *,
        receipt: _Receipt,
        source_state: str,
        target_state: str,
        run_authority_id: str,
        upstream_receipt_hash: str | None,
        context: Mapping[str, Any],
        issuer_id: object,
        synthetic_only: bool,
        token: object,
    ) -> None:
        if token is not _VERIFIED_AUTHORITY_TOKEN:
            raise TypeError("verified lifecycle authorization cannot be caller-constructed")
        object.__setattr__(self, "_receipt", receipt)
        object.__setattr__(self, "_receipt_hash", receipt.receipt_sha256)
        object.__setattr__(self, "_source_state", source_state)
        object.__setattr__(self, "_target_state", target_state)
        object.__setattr__(self, "_run_authority_id", run_authority_id)
        object.__setattr__(self, "_upstream_receipt_hash", upstream_receipt_hash)
        object.__setattr__(self, "_context", MappingProxyType(dict(context)))
        object.__setattr__(self, "_issuer_id", issuer_id)
        object.__setattr__(self, "_synthetic_only", synthetic_only)
        object.__setattr__(self, "_token", token)
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("verified lifecycle authorization is immutable")
        object.__setattr__(self, name, value)

    @property
    def receipt(self) -> _Receipt:
        return self._receipt

    @property
    def receipt_hash(self) -> str:
        return self._receipt_hash

    @property
    def source_state(self) -> str:
        return self._source_state

    @property
    def target_state(self) -> str:
        return self._target_state

    @property
    def run_authority_id(self) -> str:
        return self._run_authority_id

    @property
    def upstream_receipt_hash(self) -> str | None:
        return self._upstream_receipt_hash

    @property
    def synthetic_only(self) -> bool:
        return self._synthetic_only

    @property
    def context(self) -> Mapping[str, Any]:
        return self._context

    def assert_valid(
        self,
        *,
        source_state: str,
        target_state: str,
        expected_run_authority_id: str | None,
        expected_upstream_receipt_hash: str | None,
    ) -> None:
        if self._token is not _VERIFIED_AUTHORITY_TOKEN:
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "unverified authority token")
        if self._receipt.receipt_sha256 != self._receipt_hash:
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "receipt mutated after verification")
        if self._receipt.run_authority_id != self._run_authority_id:
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "receipt run authority mismatch")
        receipt_transition = {
            H40DiscoveryAuthorizationReceipt: ("H40_P1_SCAFFOLDED", "H40_DISCOVERY"),
            H40CandidateLockReceipt: ("H40_DISCOVERY", "H40_CANDIDATE_LOCKED"),
            H40WFValidationReceipt: ("H40_CANDIDATE_LOCKED", "H40_WALK_FORWARD_VALIDATED"),
            H40ConfirmationReadyReceipt: (
                "H40_WALK_FORWARD_VALIDATED",
                "H40_CONFIRMATION_READY",
            ),
        }.get(type(self._receipt))
        if isinstance(self._receipt, H40TerminationReceipt):
            receipt_transition = (self._receipt.source_state, self._receipt.target_state)
        if receipt_transition != (self._source_state, self._target_state):
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "receipt transition mismatch")
        if self._receipt.upstream_receipt_hash != self._upstream_receipt_hash:
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "receipt upstream mismatch")
        if self._source_state != source_state or self._target_state != target_state:
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "transition authority state mismatch")
        if expected_run_authority_id is not None and self._run_authority_id != expected_run_authority_id:
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "cross-run transition replay")
        if self._upstream_receipt_hash != expected_upstream_receipt_hash:
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "upstream receipt substitution")


class H40LifecycleAuthorityService:
    """Construct verified transition authority only after deterministic checks."""

    def __init__(
        self,
        *,
        implementation_authority: H40LifecycleImplementationAuthority | None,
        accepted_implementation_authority_hash: str | None,
        evidence_verifier: H40SyntheticEvidenceVerifier | None,
        synthetic_test_mode: bool,
        _construction_token: object,
    ) -> None:
        if _construction_token is not _VERIFIED_AUTHORITY_TOKEN:
            raise TypeError("use production() or synthetic_for_tests()")
        if accepted_implementation_authority_hash is not None:
            _require_sha256(
                accepted_implementation_authority_hash,
                "accepted_implementation_authority_hash",
            )
        if implementation_authority is not None:
            computed = implementation_authority.lifecycle_implementation_authority_hash
            if computed != accepted_implementation_authority_hash:
                raise ValueError("implementation authority object/hash mismatch")
        if synthetic_test_mode:
            if implementation_authority is None or evidence_verifier is None:
                raise ValueError("synthetic test service requires authority and evidence verifier")
        elif evidence_verifier is not None:
            raise ValueError("production service cannot use synthetic evidence verifier")
        self._implementation_authority = implementation_authority
        self._accepted_implementation_authority_hash = accepted_implementation_authority_hash
        self._evidence_verifier = evidence_verifier
        self._synthetic_test_mode = synthetic_test_mode
        self._issuer_id = object()

    @classmethod
    def production(
        cls,
        implementation_authority: H40LifecycleImplementationAuthority | None = None,
    ) -> H40LifecycleAuthorityService:
        return cls(
            implementation_authority=implementation_authority,
            accepted_implementation_authority_hash=ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH,
            evidence_verifier=None,
            synthetic_test_mode=False,
            _construction_token=_VERIFIED_AUTHORITY_TOKEN,
        )

    @classmethod
    def synthetic_for_tests(
        cls,
        implementation_authority: H40LifecycleImplementationAuthority,
        evidence_verifier: H40SyntheticEvidenceVerifier,
    ) -> H40LifecycleAuthorityService:
        return cls(
            implementation_authority=implementation_authority,
            accepted_implementation_authority_hash=(
                implementation_authority.lifecycle_implementation_authority_hash
            ),
            evidence_verifier=evidence_verifier,
            synthetic_test_mode=True,
            _construction_token=_VERIFIED_AUTHORITY_TOKEN,
        )

    def _wrap(
        self,
        receipt: _Receipt,
        *,
        source_state: str,
        target_state: str,
        upstream_receipt_hash: str | None,
        context: Mapping[str, Any],
    ) -> VerifiedLifecycleAuthorization:
        return VerifiedLifecycleAuthorization(
            receipt=receipt,
            source_state=source_state,
            target_state=target_state,
            run_authority_id=receipt.run_authority_id,
            upstream_receipt_hash=upstream_receipt_hash,
            context=context,
            issuer_id=self._issuer_id,
            synthetic_only=self._synthetic_test_mode,
            token=_VERIFIED_AUTHORITY_TOKEN,
        )

    def _require_prior(
        self,
        prior: VerifiedLifecycleAuthorization,
        *,
        source_state: str,
        target_state: str,
    ) -> None:
        if not isinstance(prior, VerifiedLifecycleAuthorization) or prior._issuer_id is not self._issuer_id:
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "foreign verifier authority")
        if prior.source_state != source_state or prior.target_state != target_state:
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "prior transition authority mismatch")
        if prior.receipt.receipt_sha256 != prior.receipt_hash:
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "prior receipt content mismatch")

    def authorize_discovery(
        self,
        *,
        implementation_authority: H40LifecycleImplementationAuthority,
        run_authority: H40RunAuthority,
        seal: H40RuntimeSnapshotSeal,
        authorized_at_utc: str,
    ) -> VerifiedLifecycleAuthorization:
        normalize_audit_timestamp(authorized_at_utc)
        if (
            self._implementation_authority is None
            or self._accepted_implementation_authority_hash is None
            or implementation_authority != self._implementation_authority
            or implementation_authority.lifecycle_implementation_authority_hash
            != self._accepted_implementation_authority_hash
        ):
            raise H40GuardError(
                H40ReasonCode.NOT_TESTABLE,
                "no independently accepted lifecycle implementation authority exists",
            )
        if not self._synthetic_test_mode and seal.synthetic_only:
            raise H40GuardError(H40ReasonCode.NOT_TESTABLE, "synthetic runtime seal is non-authoritative")
        if not seal.synthetic_only:
            seal.verify_against_accepted_ledger()
        expected_run = H40RunAuthority.from_seal(
            seal,
            implementation_authority.lifecycle_implementation_authority_hash,
        )
        if run_authority != expected_run:
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "run authority preimage mismatch")
        if (
            compute_lifecycle_semantic_root_hash() != EXPECTED_LIFECYCLE_SEMANTIC_ROOT_HASH
            or compute_lifecycle_governance_authority_hash()
            != EXPECTED_LIFECYCLE_GOVERNANCE_AUTHORITY_HASH
            or compute_protocol_authority_hash() != EXPECTED_PROTOCOL_AUTHORITY_HASH
            or compute_semantic_root_hash() != EXPECTED_SEMANTIC_ROOT_HASH
        ):
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "accepted authority identity mismatch")
        receipt = H40DiscoveryAuthorizationReceipt(
            authorized_at_utc=authorized_at_utc,
            discovery_selection_correction_contract_hash=(
                DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH
            ),
            execution_disabled=True,
            lifecycle_governance_authority_hash=compute_lifecycle_governance_authority_hash(),
            lifecycle_implementation_authority_hash=(
                implementation_authority.lifecycle_implementation_authority_hash
            ),
            materialized_run_authority_hash=seal.materialized_run_authority_hash,
            not_testable_slot_count=seal.not_testable_slot_count,
            protocol_authority_hash=compute_protocol_authority_hash(),
            registered_slot_count=seal.registered_slot_count,
            run_authority_id=run_authority.run_authority_id,
            sealed_registered_roster_hash=seal.sealed_registered_roster_hash,
            semantic_root_hash=compute_semantic_root_hash(),
            source_manifest_hash=seal.source_manifest_hash,
            split_attestation_hash=seal.split_attestation_hash,
            split_manifest_hash=seal.split_manifest_hash,
            structural_ledger_hash=EXPECTED_STRUCTURAL_LEDGER_HASH,
            total_slot_count=seal.total_slot_count,
        )
        return self._wrap(
            receipt,
            source_state="H40_P1_SCAFFOLDED",
            target_state="H40_DISCOVERY",
            upstream_receipt_hash=None,
            context={"run_authority": run_authority, "seal": seal},
        )

    def authorize_candidate_lock(
        self,
        *,
        discovery_authority: VerifiedLifecycleAuthorization,
        evidence: H40DiscoveryResultEvidence,
        locked_at_utc: str,
        verified_at_utc: str,
    ) -> VerifiedLifecycleAuthorization:
        if not isinstance(evidence, H40DiscoveryResultEvidence):
            raise TypeError("candidate lock requires H40DiscoveryResultEvidence")
        self._require_prior(
            discovery_authority,
            source_state="H40_P1_SCAFFOLDED",
            target_state="H40_DISCOVERY",
        )
        verifier = self._evidence_verifier
        if verifier is None:
            raise H40GuardError(H40ReasonCode.NOT_TESTABLE, "no accepted scientific evidence verifier")
        seal = discovery_authority.context.get("seal")
        if not isinstance(seal, H40RuntimeSnapshotSeal):
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "missing verified runtime seal")
        discovery_receipt = discovery_authority.receipt
        if not isinstance(discovery_receipt, H40DiscoveryAuthorizationReceipt):
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "discovery receipt type mismatch")
        if (
            evidence.discovery_authorization_receipt_hash != discovery_authority.receipt_hash
            or evidence.run_authority_id != discovery_authority.run_authority_id
            or evidence.materialized_run_authority_hash != seal.materialized_run_authority_hash
            or evidence.sealed_registered_roster_hash != seal.sealed_registered_roster_hash
        ):
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "discovery result lineage mismatch")

        expected_roster = [
            (
                item.slot_index,
                item.slot_hash,
                item.structural_configuration_hash,
                item.family_id,
                len(item.family_id.split("+")),
            )
            for item in seal.roster
        ]
        actual_entries = [
            (
                item.slot_index,
                item.slot_hash,
                item.structural_configuration_hash,
                item.family_id,
                item.complexity,
            )
            for item in evidence.candidate_result_entries
        ]
        if actual_entries != sorted(expected_roster, key=lambda item: item[2]):
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "candidate evidence is not the complete sealed REGISTERED roster",
            )
        verifier.verify_discovery_manifest(evidence, evidence.candidate_result_entries)
        scored: list[tuple[H40CandidateResultEntry, _CandidateScore]] = []
        for entry in evidence.candidate_result_entries:
            result = verifier.verify_candidate(
                entry,
                run_authority_id=evidence.run_authority_id,
                correction_manifest_hash=evidence.correction_input_evidence_manifest_hash,
            )
            if result.hard_gates_passed:
                scored.append((entry, result))
        if not scored:
            raise H40GuardError(H40ReasonCode.THRESHOLD_UNMET, "no candidate passed every accepted hard gate")
        scored.sort(
            key=lambda item: (
                -item[1].adjusted_lcb_net_expectancy,
                -item[1].adjusted_lcb_precision,
                item[0].complexity,
                item[0].structural_configuration_hash,
            )
        )
        selected = scored[0][0]
        receipt = H40CandidateLockReceipt(
            discovery_authorization_receipt_hash=discovery_authority.receipt_hash,
            discovery_result_evidence_hash=evidence.evidence_sha256,
            locked_at_utc=locked_at_utc,
            materialized_run_authority_hash=seal.materialized_run_authority_hash,
            run_authority_id=evidence.run_authority_id,
            selected_slot_hash=selected.slot_hash,
            selected_slot_index=selected.slot_index,
            selected_structural_configuration_hash=selected.structural_configuration_hash,
            upstream_receipt_hash=discovery_authority.receipt_hash,
            verified_at_utc=verified_at_utc,
        )
        return self._wrap(
            receipt,
            source_state="H40_DISCOVERY",
            target_state="H40_CANDIDATE_LOCKED",
            upstream_receipt_hash=discovery_authority.receipt_hash,
            context={
                "discovery_authority": discovery_authority,
                "evidence": evidence,
                "seal": seal,
                "selected_entry": selected,
            },
        )

    def authorize_wf_validation(
        self,
        *,
        candidate_authority: VerifiedLifecycleAuthorization,
        evidence: H40WFValidationResultEvidence,
        split_authority: H40ExpectedSplitAuthority,
        validated_at_utc: str,
        verified_at_utc: str,
    ) -> VerifiedLifecycleAuthorization:
        if not isinstance(evidence, H40WFValidationResultEvidence):
            raise TypeError("WF validation requires H40WFValidationResultEvidence")
        if not isinstance(split_authority, H40ExpectedSplitAuthority):
            raise TypeError("WF validation requires H40ExpectedSplitAuthority")
        self._require_prior(
            candidate_authority,
            source_state="H40_DISCOVERY",
            target_state="H40_CANDIDATE_LOCKED",
        )
        verifier = self._evidence_verifier
        if verifier is None:
            raise H40GuardError(H40ReasonCode.NOT_TESTABLE, "no accepted WF evidence verifier")
        receipt = candidate_authority.receipt
        if not isinstance(receipt, H40CandidateLockReceipt):
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "candidate receipt type mismatch")
        if (
            evidence.candidate_lock_receipt_hash != candidate_authority.receipt_hash
            or evidence.run_authority_id != candidate_authority.run_authority_id
            or evidence.locked_slot_hash != receipt.selected_slot_hash
            or evidence.locked_slot_index != receipt.selected_slot_index
            or evidence.locked_structural_configuration_hash
            != receipt.selected_structural_configuration_hash
            or evidence.split_manifest_hash != split_authority.split_manifest_hash
            or evidence.split_attestation_hash != split_authority.split_attestation_hash
            or dict(evidence.accepted_validation_contract_hashes)
            != dict(split_authority.accepted_validation_contract_hashes)
        ):
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "WF result lineage mismatch")
        actual_folds = [
            (item.fold_id, item.partition_id, item.split_definition_hash, item.fold_identity_hash)
            for item in evidence.fold_result_entries
        ]
        expected_folds = [
            (item.fold_id, item.partition_id, item.split_definition_hash, item.fold_identity_hash)
            for item in split_authority.folds
        ]
        if actual_folds != expected_folds:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "WF fold set is missing, duplicate, extra, or reordered",
            )
        fold_results = [
            verifier.verify_wf_fold(item, evidence=evidence)
            for item in evidence.fold_result_entries
        ]
        all_passed = all(fold_results)
        if not all_passed:
            return self.authorize_termination(
                prior_authority=candidate_authority,
                target_state="H40_NO_GO",
                reason_code=H40ReasonCode.THRESHOLD_UNMET,
                detail_message="locked candidate failed an accepted WF gate; no runner-up promotion",
                terminated_at_utc=verified_at_utc,
                failure_evidence_hash=evidence.evidence_sha256,
                failure_evidence=evidence,
            )
        wf_receipt = H40WFValidationReceipt(
            candidate_lock_receipt_hash=candidate_authority.receipt_hash,
            locked_slot_hash=receipt.selected_slot_hash,
            locked_slot_index=receipt.selected_slot_index,
            locked_structural_configuration_hash=receipt.selected_structural_configuration_hash,
            run_authority_id=evidence.run_authority_id,
            upstream_receipt_hash=candidate_authority.receipt_hash,
            validated_at_utc=validated_at_utc,
            verified_at_utc=verified_at_utc,
            wf_validation_result_evidence_hash=evidence.evidence_sha256,
        )
        return self._wrap(
            wf_receipt,
            source_state="H40_CANDIDATE_LOCKED",
            target_state="H40_WALK_FORWARD_VALIDATED",
            upstream_receipt_hash=candidate_authority.receipt_hash,
            context={
                "candidate_authority": candidate_authority,
                "evidence": evidence,
                "split_authority": split_authority,
            },
        )

    def authorize_confirmation_ready(
        self,
        *,
        wf_authority: VerifiedLifecycleAuthorization,
        prepared_at_utc: str,
    ) -> VerifiedLifecycleAuthorization:
        self._require_prior(
            wf_authority,
            source_state="H40_CANDIDATE_LOCKED",
            target_state="H40_WALK_FORWARD_VALIDATED",
        )
        wf_receipt = wf_authority.receipt
        evidence = wf_authority.context.get("evidence")
        if not isinstance(wf_receipt, H40WFValidationReceipt) or not isinstance(
            evidence, H40WFValidationResultEvidence
        ):
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "WF authority context mismatch")
        confirmation_receipt = H40ConfirmationReadyReceipt(
            locked_slot_hash=wf_receipt.locked_slot_hash,
            locked_slot_index=wf_receipt.locked_slot_index,
            locked_structural_configuration_hash=wf_receipt.locked_structural_configuration_hash,
            prepared_at_utc=prepared_at_utc,
            run_authority_id=wf_receipt.run_authority_id,
            split_attestation_hash=evidence.split_attestation_hash,
            split_manifest_hash=evidence.split_manifest_hash,
            upstream_receipt_hash=wf_authority.receipt_hash,
            wf_validation_receipt_hash=wf_authority.receipt_hash,
        )
        return self._wrap(
            confirmation_receipt,
            source_state="H40_WALK_FORWARD_VALIDATED",
            target_state="H40_CONFIRMATION_READY",
            upstream_receipt_hash=wf_authority.receipt_hash,
            context={"wf_authority": wf_authority},
        )

    def authorize_termination(
        self,
        *,
        prior_authority: VerifiedLifecycleAuthorization,
        target_state: str,
        reason_code: H40ReasonCode,
        detail_message: str,
        terminated_at_utc: str,
        failure_evidence_hash: str | None = None,
        failure_evidence: _ResultEvidence | None = None,
    ) -> VerifiedLifecycleAuthorization:
        if not isinstance(prior_authority, VerifiedLifecycleAuthorization) or prior_authority._issuer_id is not self._issuer_id:
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "foreign termination lineage")
        if (failure_evidence_hash is None) != (failure_evidence is None):
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "failure evidence hash and typed evidence must be supplied together",
            )
        if failure_evidence is not None:
            if failure_evidence.evidence_sha256 != failure_evidence_hash:
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    "failure evidence content hash mismatch",
                )
            if failure_evidence.run_authority_id != prior_authority.run_authority_id:
                raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "failure evidence cross-run replay")
            verifier = self._evidence_verifier
            if verifier is None:
                raise H40GuardError(H40ReasonCode.NOT_TESTABLE, "no accepted failure evidence verifier")
            if isinstance(failure_evidence, H40WFValidationResultEvidence):
                if failure_evidence.candidate_lock_receipt_hash != prior_authority.receipt_hash:
                    raise H40GuardError(
                        H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                        "failure evidence candidate lineage mismatch",
                    )
                for fold in failure_evidence.fold_result_entries:
                    verifier.verify_wf_fold(fold, evidence=failure_evidence)
            else:
                if failure_evidence.discovery_authorization_receipt_hash != prior_authority.receipt_hash:
                    raise H40GuardError(
                        H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                        "failure evidence discovery lineage mismatch",
                    )
                verifier.verify_discovery_manifest(
                    failure_evidence,
                    failure_evidence.candidate_result_entries,
                )
                for entry in failure_evidence.candidate_result_entries:
                    verifier.verify_candidate(
                        entry,
                        run_authority_id=failure_evidence.run_authority_id,
                        correction_manifest_hash=(
                            failure_evidence.correction_input_evidence_manifest_hash
                        ),
                    )
        receipt = H40TerminationReceipt(
            detail_message=detail_message,
            failure_evidence_hash=failure_evidence_hash,
            reason_code=reason_code,
            run_authority_id=prior_authority.run_authority_id,
            source_state=prior_authority.target_state,
            target_state=target_state,
            terminated_at_utc=terminated_at_utc,
            upstream_receipt_hash=prior_authority.receipt_hash,
        )
        return self._wrap(
            receipt,
            source_state=prior_authority.target_state,
            target_state=target_state,
            upstream_receipt_hash=prior_authority.receipt_hash,
            context={
                "failure_evidence": failure_evidence,
                "prior_authority": prior_authority,
            },
        )

    def revalidate_authorization(self, authorization: VerifiedLifecycleAuthorization) -> None:
        """Recompute a previously issued authorization and all bound synthetic evidence."""
        if not isinstance(authorization, VerifiedLifecycleAuthorization) or authorization._issuer_id is not self._issuer_id:
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "foreign verifier authority")
        receipt = authorization.receipt
        reconstructed: VerifiedLifecycleAuthorization
        if isinstance(receipt, H40DiscoveryAuthorizationReceipt):
            run_authority = authorization.context.get("run_authority")
            seal = authorization.context.get("seal")
            implementation = self._implementation_authority
            if (
                not isinstance(run_authority, H40RunAuthority)
                or not isinstance(seal, H40RuntimeSnapshotSeal)
                or implementation is None
            ):
                raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "discovery context missing")
            reconstructed = self.authorize_discovery(
                implementation_authority=implementation,
                run_authority=run_authority,
                seal=seal,
                authorized_at_utc=receipt.authorized_at_utc,
            )
        elif isinstance(receipt, H40CandidateLockReceipt):
            prior = authorization.context.get("discovery_authority")
            evidence = authorization.context.get("evidence")
            if not isinstance(prior, VerifiedLifecycleAuthorization) or not isinstance(
                evidence, H40DiscoveryResultEvidence
            ):
                raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "candidate context missing")
            reconstructed = self.authorize_candidate_lock(
                discovery_authority=prior,
                evidence=evidence,
                locked_at_utc=receipt.locked_at_utc,
                verified_at_utc=receipt.verified_at_utc,
            )
        elif isinstance(receipt, H40WFValidationReceipt):
            prior = authorization.context.get("candidate_authority")
            evidence = authorization.context.get("evidence")
            split = authorization.context.get("split_authority")
            if (
                not isinstance(prior, VerifiedLifecycleAuthorization)
                or not isinstance(evidence, H40WFValidationResultEvidence)
                or not isinstance(split, H40ExpectedSplitAuthority)
            ):
                raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "WF context missing")
            reconstructed = self.authorize_wf_validation(
                candidate_authority=prior,
                evidence=evidence,
                split_authority=split,
                validated_at_utc=receipt.validated_at_utc,
                verified_at_utc=receipt.verified_at_utc,
            )
        elif isinstance(receipt, H40ConfirmationReadyReceipt):
            prior = authorization.context.get("wf_authority")
            if not isinstance(prior, VerifiedLifecycleAuthorization):
                raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "confirmation context missing")
            reconstructed = self.authorize_confirmation_ready(
                wf_authority=prior,
                prepared_at_utc=receipt.prepared_at_utc,
            )
        elif isinstance(receipt, H40TerminationReceipt):
            prior = authorization.context.get("prior_authority")
            failure_evidence = authorization.context.get("failure_evidence")
            if not isinstance(prior, VerifiedLifecycleAuthorization):
                raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "termination context missing")
            if failure_evidence is not None and not isinstance(
                failure_evidence,
                (H40DiscoveryResultEvidence, H40WFValidationResultEvidence),
            ):
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    "termination failure evidence context mismatch",
                )
            reconstructed = self.authorize_termination(
                prior_authority=prior,
                target_state=receipt.target_state,
                reason_code=receipt.reason_code,
                detail_message=receipt.detail_message,
                terminated_at_utc=receipt.terminated_at_utc,
                failure_evidence_hash=receipt.failure_evidence_hash,
                failure_evidence=failure_evidence,
            )
        else:
            raise TypeError("unknown lifecycle receipt type")
        if (
            reconstructed.receipt_hash != authorization.receipt_hash
            or reconstructed.source_state != authorization.source_state
            or reconstructed.target_state != authorization.target_state
            or reconstructed.upstream_receipt_hash != authorization.upstream_receipt_hash
        ):
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "authorization replay mismatch")


_RECEIPT_PARSERS: Mapping[str, Callable[[Mapping[str, Any]], _Receipt]] = MappingProxyType({
    "H40_RECEIPT_DISCOVERY_AUTH_V2": H40DiscoveryAuthorizationReceipt.from_dict,
    "H40_RECEIPT_CANDIDATE_LOCK_V2": H40CandidateLockReceipt.from_dict,
    "H40_RECEIPT_WF_VALIDATION_V2": H40WFValidationReceipt.from_dict,
    "H40_RECEIPT_CONFIRMATION_READY_V2": H40ConfirmationReadyReceipt.from_dict,
    "H40_RECEIPT_TERMINATION_V2": H40TerminationReceipt.from_dict,
})


class H40LifecycleArtifactStore:
    """Minimal canonical, write-once lifecycle governance persistence."""

    _KEY_RE = re.compile(r"[0-9]{2}_[a-z0-9_]+\Z", re.ASCII)

    def __init__(self, base_path: str | Path) -> None:
        self._base_path = Path(base_path)

    def _run_dir(self, run_authority_id: str) -> Path:
        _require_sha256(run_authority_id, "run_authority_id")
        return self._base_path / "artifacts" / "h40" / "lifecycle" / "runs" / run_authority_id

    def _path(self, run_authority_id: str, transition_key: str) -> Path:
        if self._KEY_RE.fullmatch(transition_key) is None:
            raise ValueError("transition_key must match NN_lowercase_name")
        return self._run_dir(run_authority_id) / f"{transition_key}.json"

    @staticmethod
    def _bound_evidence(
        authorization: VerifiedLifecycleAuthorization,
    ) -> _ResultEvidence | None:
        evidence = authorization.context.get("evidence")
        if isinstance(evidence, (H40DiscoveryResultEvidence, H40WFValidationResultEvidence)):
            return evidence
        failure_evidence = authorization.context.get("failure_evidence")
        if isinstance(
            failure_evidence,
            (H40DiscoveryResultEvidence, H40WFValidationResultEvidence),
        ):
            return failure_evidence
        return None

    @classmethod
    def _envelope(cls, authorization: VerifiedLifecycleAuthorization) -> dict[str, Any]:
        evidence = cls._bound_evidence(authorization)
        return {
            "bound_evidence": None if evidence is None else evidence.to_dict(),
            "bound_evidence_sha256": None if evidence is None else evidence.evidence_sha256,
            "receipt": authorization.receipt.to_dict(),
            "receipt_sha256": authorization.receipt_hash,
        }

    @staticmethod
    def _parse_bound_evidence(
        payload: object,
        digest: object,
        receipt: _Receipt,
    ) -> _ResultEvidence | None:
        if payload is None or digest is None:
            if payload is not None or digest is not None:
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    "bound evidence payload/hash nullability mismatch",
                )
            if isinstance(receipt, (H40CandidateLockReceipt, H40WFValidationReceipt)) or (
                isinstance(receipt, H40TerminationReceipt)
                and receipt.failure_evidence_hash is not None
            ):
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    "receipt is missing its bound result evidence",
                )
            return None
        if not isinstance(payload, Mapping) or not isinstance(digest, str):
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "invalid bound evidence envelope fields",
            )
        if canonical_sha256(payload) != digest:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "bound evidence content hash mismatch",
            )
        schema = payload.get("evidence_schema_id")
        if schema == "H40_DISCOVERY_RESULT_EVIDENCE_V1":
            evidence: _ResultEvidence = H40DiscoveryResultEvidence.from_dict(payload)
        elif schema == "H40_WF_VALIDATION_RESULT_EVIDENCE_V1":
            evidence = H40WFValidationResultEvidence.from_dict(payload)
        else:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "unknown bound result evidence schema",
            )
        expected_digest: str | None
        if isinstance(receipt, H40CandidateLockReceipt):
            expected_digest = receipt.discovery_result_evidence_hash
        elif isinstance(receipt, H40WFValidationReceipt):
            expected_digest = receipt.wf_validation_result_evidence_hash
        elif isinstance(receipt, H40TerminationReceipt):
            expected_digest = receipt.failure_evidence_hash
        else:
            expected_digest = None
        if evidence.evidence_sha256 != digest or digest != expected_digest:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "bound evidence/receipt authority mismatch",
            )
        return evidence

    def persist_authorization(
        self,
        transition_key: str,
        authorization: VerifiedLifecycleAuthorization,
        *,
        revalidate: Callable[[VerifiedLifecycleAuthorization], None],
    ) -> Path:
        if not isinstance(authorization, VerifiedLifecycleAuthorization):
            raise TypeError("only verified lifecycle authorization can be persisted")
        revalidate(authorization)
        path = self._path(authorization.run_authority_id, transition_key)
        encoded = (canonical_json(self._envelope(authorization)) + "\n").encode("utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            existing = path.read_bytes()
            if existing != encoded:
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    "write-once lifecycle artifact already exists with different bytes",
                )
            restored = self.restore_receipt(authorization.run_authority_id, transition_key)
            if restored.receipt_sha256 != authorization.receipt_hash:
                raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "idempotent receipt mismatch")
            revalidate(authorization)
            return path
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        return path

    def _restore(
        self,
        run_authority_id: str,
        transition_key: str,
    ) -> tuple[_Receipt, _ResultEvidence | None]:
        path = self._path(run_authority_id, transition_key)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "invalid lifecycle artifact") from exc
        if not isinstance(raw, Mapping):
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "lifecycle envelope must be an object")
        _require_exact_keys(
            raw,
            frozenset({
                "bound_evidence",
                "bound_evidence_sha256",
                "receipt",
                "receipt_sha256",
            }),
            "lifecycle envelope",
        )
        payload = raw["receipt"]
        digest = raw["receipt_sha256"]
        if not isinstance(payload, Mapping) or not isinstance(digest, str):
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "invalid lifecycle envelope fields")
        if canonical_sha256(payload) != digest:
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "lifecycle receipt content hash mismatch")
        schema = payload.get("receipt_schema_id")
        parser = _RECEIPT_PARSERS.get(str(schema))
        if parser is None:
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "unknown lifecycle receipt schema")
        receipt = parser(payload)
        if receipt.receipt_sha256 != digest or receipt.run_authority_id != run_authority_id:
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "restored receipt authority mismatch")
        evidence = self._parse_bound_evidence(
            raw["bound_evidence"],
            raw["bound_evidence_sha256"],
            receipt,
        )
        return receipt, evidence

    def restore_receipt(self, run_authority_id: str, transition_key: str) -> _Receipt:
        receipt, _ = self._restore(run_authority_id, transition_key)
        return receipt

    def restore_authorization(
        self,
        run_authority_id: str,
        transition_key: str,
        *,
        expected_authorization: VerifiedLifecycleAuthorization,
        service: H40LifecycleAuthorityService,
    ) -> VerifiedLifecycleAuthorization:
        receipt, evidence = self._restore(run_authority_id, transition_key)
        if receipt.to_dict() != expected_authorization.receipt.to_dict():
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "restored receipt substitution")
        expected_evidence = self._bound_evidence(expected_authorization)
        if (
            (evidence is None) != (expected_evidence is None)
            or evidence is not None
            and expected_evidence is not None
            and evidence.to_dict() != expected_evidence.to_dict()
        ):
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "restored evidence substitution")
        service.revalidate_authorization(expected_authorization)
        return expected_authorization


__all__ = [
    "ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH",
    "DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH",
    "EXPECTED_LIFECYCLE_CHILD_HASHES",
    "EXPECTED_LIFECYCLE_GOVERNANCE_AUTHORITY_HASH",
    "EXPECTED_LIFECYCLE_SEMANTIC_ROOT_HASH",
    "H40CandidateLockReceipt",
    "H40CandidateResultEntry",
    "H40ConfirmationReadyReceipt",
    "H40DiscoveryAuthorizationReceipt",
    "H40DiscoveryResultEvidence",
    "H40ExpectedSplitAuthority",
    "H40ExpectedWFFold",
    "H40LifecycleArtifactStore",
    "H40LifecycleAuthorityService",
    "H40LifecycleImplementationAuthority",
    "H40RequiredTestCIEvidenceIdentity",
    "H40RunAuthority",
    "H40RuntimeRosterEntry",
    "H40RuntimeSnapshotSeal",
    "H40SyntheticEvidenceVerifier",
    "H40TerminationReceipt",
    "H40WFFoldResultEntry",
    "H40WFValidationReceipt",
    "H40WFValidationResultEvidence",
    "VerifiedLifecycleAuthorization",
    "compute_lifecycle_child_hashes",
    "compute_lifecycle_governance_authority_hash",
    "compute_lifecycle_semantic_root_hash",
    "lifecycle_governance_authority_object",
    "lifecycle_semantic_contracts",
    "lifecycle_semantic_root_preimage",
    "normalize_audit_timestamp",
]
