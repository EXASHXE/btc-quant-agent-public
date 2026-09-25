"""Accepted H40 F01 lifecycle evidence-authority contracts and verifiers.

This module is strictly pre-outcome.  It materializes the accepted lifecycle
semantic hash tree, typed authority/receipt schemas, deterministic run and
runtime-roster authority, and synthetic/governance verification mechanics.
It does not evaluate market data, Discovery statistics, walk-forward results,
confirmation outcomes, or execution.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import sqlite3
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import InitVar, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from typing import Any, ClassVar, Protocol, cast, runtime_checkable

from ..research_contract.canonical import canonical_json, canonical_sha256
from .configuration_ledger import DEFAULT_SOURCE_MANIFEST_HASH, DEFAULT_SPLIT_MANIFEST_HASH
from .guards import H40GuardError, H40ReasonCode
from .protocol import H40ProtocolIdentity
from .protocol_authority import (
    EXPECTED_PROTOCOL_AUTHORITY_HASH,
    EXPECTED_SEMANTIC_ROOT_HASH,
    EXPECTED_STRUCTURAL_LEDGER_HASH,
    MaterializedRunAuthority,
    compute_protocol_authority_hash,
    compute_semantic_root_hash,
    current_p1_authority_snapshot,
)
from .source_manifest import (
    H40SourceManifest,
    H40SourceStatus,
    assert_canonical_source_identity,
    extract_verified_source_timestamps,
    validate_source_artifact,
)
from .split_manifest import H40PartitionType, H40SplitManifest

EXPECTED_LIFECYCLE_SEMANTIC_ROOT_HASH = (
    "36cbda530352cffaa475bd835b3b629df47351ca284e09bdf31a8fc884d48b4b"
)
EXPECTED_LIFECYCLE_GOVERNANCE_AUTHORITY_HASH = (
    "bb367f2af726be105bddf42636c97652402014c8a671d43ab81b1964c258e5cf"
)
DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH = (
    "f84c97050c7db813263e5ffda6b1c556af0b7b0e2876bb8616640d2c9d67084b"
)
DISCOVERY_PROVENANCE_CONTRACT_HASH = (
    "31fc3930e44149e6b3af54ddd3b11c630f95cbbd3f152b3d0d5e614690dcf7ae"
)

# Non-negotiable staged authority state: both accepted constants remain None
ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH: str | None = None
ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH: str | None = None

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
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
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
    "authority_rules": [
      "transition_api_constructs_receipt_only_after_recomputing_all_bound_authorities",
      "caller_object_path_boolean_or_label_is_not_authority",
      "upstream_receipt_hash_must_be_null",
      "run_authority_id_must_recompute_under_H40_RUN_AUTHORITY_V1",
      "lifecycle_implementation_authority_hash_must_be_independently_accepted",
      "sealed_registered_roster_hash_and_counts_must_match_materialized_run_authority",
      "execution_disabled_must_be_true",
      "controller_authority_hash_must_equal_current_in_process_ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH",
      "discovery_run_grant_hash_must_recompute_under_H40_DISCOVERY_RUN_GRANT_V1_and_bind_current_controller_run_runtime_source_split_roster_and_execution_disabled",
      "production_discovery_receipt_v2_is_invalid_under_lifecycle_v5",
      "every_production_authoritative_boundary_rechecks_current_in_process_lifecycle_implementation_and_controller_authority_anchors",
      "superseded_long_lived_production_service_authority_fails_closed",
      "hot_authority_republication_requires_new_process_or_service_identity"
    ],
    "authorized_transition": [
      "H40_P1_SCAFFOLDED",
      "H40_DISCOVERY"
    ],
    "implementation_authority_object": {
      "canonical_field_names": [
        "accepted_lifecycle_governance_authority_hash",
        "f01_implementation_acceptance_artifact_path",
        "f01_implementation_acceptance_commit_sha",
        "f01_implementation_commit_sha",
        "required_test_ci_evidence_identity",
        "schema_id"
      ],
      "required_test_ci_evidence_identity_fields": [
        "evidence_manifest_artifact_path",
        "evidence_manifest_sha256",
        "tested_commit_sha"
      ],
      "schema_id": "H40_LIFECYCLE_IMPLEMENTATION_AUTHORITY_V1"
    },
    "receipt_field_contract": {
      "authorized_at_utc": "audit_timestamp_utc",
      "discovery_selection_correction_contract_hash": "constant:f84c97050c7db813263e5ffda6b1c556af0b7b0e2876bb8616640d2c9d67084b",
      "execution_disabled": "constant:true",
      "lifecycle_governance_authority_hash": "accepted_sha256",
      "lifecycle_implementation_authority_hash": "accepted_sha256",
      "materialized_run_authority_hash": "sha256",
      "not_testable_slot_count": "integer_gte_0",
      "protocol_authority_hash": "constant:a83f8fc7a5ca7109fb8cd7fed114d87c3b2c968b5145c11cada203aa5111d1ce",
      "receipt_schema_id": "constant:H40_RECEIPT_DISCOVERY_AUTH_V3",
      "registered_slot_count": "integer_gte_0",
      "run_authority_id": "sha256",
      "sealed_registered_roster_hash": "sha256",
      "semantic_root_hash": "constant:71889a35f227ed734272b712851174a69bf9dbb12ea3f87cd84c26e7c66f6af1",
      "source_manifest_hash": "sha256",
      "split_attestation_hash": "sha256",
      "split_manifest_hash": "sha256",
      "structural_ledger_hash": "constant:483f68502b57972deae071c7bd4587ca3e57ccaa72bd99fb0de07b4f0ab8c85f",
      "total_slot_count": "integer_gt_0",
      "upstream_receipt_hash": "constant:null",
      "controller_authority_hash": "sha256_equal_current_in_process_ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH",
      "discovery_run_grant_hash": "sha256_of_exact_current_H40_DISCOVERY_RUN_GRANT_V1"
    },
    "receipt_hash_rule": "canonical_sha256(exact_receipt_field_contract_keys_only)",
    "receipt_schema_id": "H40_RECEIPT_DISCOVERY_AUTH_V3",
    "schema_id": "H40_LIFECYCLE_CHILD_DISCOVERY_AUTHORIZATION_V1",
    "controller_authority_object": {
      "accepted_hash_constant": "ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH",
      "accepted_hash_pre_authorization_value": null,
      "canonical_field_names": [
        "authorization_scope",
        "controller_acceptance_artifact_path",
        "controller_acceptance_commit_sha",
        "discovery_provenance_contract_hash",
        "discovery_selection_correction_contract_hash",
        "execution_disabled",
        "lifecycle_governance_authority_hash",
        "lifecycle_implementation_authority_hash",
        "lifecycle_semantic_root_hash",
        "permitted_partitions",
        "protocol_authority_hash",
        "schema_id",
        "scientific_semantic_root_hash",
        "structural_ledger_hash",
        "transition_source_state",
        "transition_target_state"
      ],
      "fixed_policy": {
        "authorization_scope": "H40_P3_DISCOVERY_V1",
        "execution_disabled": true,
        "permitted_partitions": [
          "WF1_TRAIN",
          "WF1_CALIBRATION"
        ],
        "transition_source_state": "H40_P1_SCAFFOLDED",
        "transition_target_state": "H40_DISCOVERY"
      },
      "schema_id": "H40_P3_CONTROLLER_AUTHORITY_V1"
    },
    "discovery_run_grant_object": {
      "canonical_field_names": [
        "authorized_at_utc",
        "controller_authority_hash",
        "discovery_provenance_contract_hash",
        "execution_disabled",
        "lifecycle_governance_authority_hash",
        "lifecycle_implementation_authority_hash",
        "materialized_run_authority_hash",
        "permitted_partitions",
        "protocol_authority_hash",
        "run_authority_id",
        "runtime_authority_snapshot_hash",
        "schema_id",
        "scientific_semantic_root_hash",
        "sealed_registered_roster_hash",
        "source_manifest_hash",
        "split_attestation_hash",
        "split_manifest_hash",
        "structural_ledger_hash"
      ],
      "derivation_rule": "derived_from_currently_accepted_controller_authority_plus_exact_verified_run_authority_and_runtime_snapshot_seal",
      "execution_disabled": true,
      "permitted_partitions": [
        "WF1_TRAIN",
        "WF1_CALIBRATION"
      ],
      "schema_id": "H40_DISCOVERY_RUN_GRANT_V1"
    }
  },
  "candidate_lock_receipt_contract": {
    "authorization_receipt_field_contract": {
      "discovery_authorization_receipt_hash": "sha256_equal_upstream_receipt_hash",
      "discovery_result_evidence_hash": "verified_evidence_sha256",
      "discovery_selection_correction_contract_hash": "constant:f84c97050c7db813263e5ffda6b1c556af0b7b0e2876bb8616640d2c9d67084b",
      "locked_at_utc": "audit_timestamp_utc",
      "materialized_run_authority_hash": "sha256_equal_discovery_authorization",
      "receipt_schema_id": "constant:H40_RECEIPT_CANDIDATE_LOCK_V2",
      "run_authority_id": "sha256_equal_discovery_authorization",
      "selected_slot_hash": "sha256_derived_by_verifier",
      "selected_slot_index": "integer_derived_by_verifier",
      "selected_structural_configuration_hash": "sha256_derived_by_verifier",
      "selection_verifier_id": "constant:H40_DISCOVERY_SELECTION_VERIFIER_V1",
      "upstream_receipt_hash": "sha256_of_discovery_authorization_receipt",
      "verified_at_utc": "audit_timestamp_utc"
    },
    "authorized_transition": [
      "H40_DISCOVERY",
      "H40_CANDIDATE_LOCKED"
    ],
    "candidate_result_entry_field_contract": {
      "candidate_result_input_evidence_hash": "sha256_of_complete_canonical_scientific_result_inputs_bound_to_run_authority_candidate_source_split_and_accepted_contracts",
      "complexity": "integer_derived_from_accepted_configuration",
      "family_id": "string_derived_from_accepted_configuration",
      "hard_gate_input_evidence_hashes": "complete_object_sorted_by_accepted_gate_id_to_run_and_candidate_bound_sha256",
      "net_expectancy_input_evidence_hash": "run_and_candidate_bound_sha256",
      "precision_input_evidence_hash": "run_and_candidate_bound_sha256",
      "slot_hash": "sha256",
      "slot_index": "integer_0_through_167",
      "structural_configuration_hash": "sha256"
    },
    "discovery_result_evidence_field_contract": {
      "candidate_result_entries": "array_sorted_by_structural_configuration_hash_ascending",
      "correction_input_evidence_manifest_hash": "sha256_of_complete_run_roster_metric_specific_and_cross_family_inputs",
      "created_at_utc": "audit_timestamp_utc",
      "discovery_authorization_receipt_hash": "sha256",
      "discovery_partition": "constant:WF1_CALIBRATION",
      "discovery_selection_contract_id": "constant:DISCOVERY_SELECTION_V1",
      "discovery_selection_correction_contract_hash": "constant:f84c97050c7db813263e5ffda6b1c556af0b7b0e2876bb8616640d2c9d67084b",
      "evidence_schema_id": "constant:H40_DISCOVERY_RESULT_EVIDENCE_V1",
      "materialized_run_authority_hash": "sha256",
      "run_authority_id": "sha256",
      "sealed_registered_roster_hash": "sha256"
    },
    "evidence_completeness_rule": "candidate_result_entries_must_equal_the_complete_sealed_REGISTERED_roster_with_no_missing_duplicate_or_extra_configuration",
    "forbidden_authority": [
      "caller_supplied_selection_rank",
      "summary_locator_or_hash_without_canonical_result_evidence",
      "global_M_equals_18_FWER",
      "ascending_slot_index_as_final_tie",
      "runner_up_promotion"
    ],
    "receipt_hash_rule": "canonical_sha256(exact_authorization_receipt_field_contract_keys_only)",
    "result_evidence_hash_rule": "canonical_sha256(exact_discovery_result_evidence_fields_with_exact_candidate_result_entry_fields)",
    "schema_id": "H40_LIFECYCLE_CHILD_CANDIDATE_LOCK_V1",
    "selection_authority": {
      "contract_id": "DISCOVERY_SELECTION_V1",
      "content_hash": "f84c97050c7db813263e5ffda6b1c556af0b7b0e2876bb8616640d2c9d67084b",
      "cross_family_rule": "Holm_applies_to_family_representatives",
      "final_selection_order": [
        "pass_every_accepted_hard_gate",
        "highest_adjusted_LCB_net_expectancy",
        "highest_adjusted_LCB_precision",
        "lower_complexity",
        "ascending_canonical_structural_configuration_hash_or_configuration_ID"
      ],
      "metric_correction_rule": "PRECISION_and_NET_EXPECTANCY_within_family_max_statistic_corrections_are_separate",
      "no_runner_up_promotion": true,
      "within_family_universe": "REGISTERED_rows_of_that_family_in_the_sealed_snapshot"
    },
    "verifier_obligations": [
      "load_every_evidence_object_by_content_hash_validate_exact_schema_and_verify_run_candidate_source_split_and_contract_lineage",
      "recompute_candidate_identity_and_membership_against_the_sealed_roster",
      "recompute_all_hard_gates_and_all_correction_and_selection_outputs_under_the_accepted_content_hash",
      "derive_exactly_one_winner_or_emit_no_authorization_receipt",
      "persist_authorization_receipt_only_after_successful_recomputation",
      "reverify_result_evidence_and_selection_on_restore_before_transition_use"
    ]
  },
  "wf_validation_receipt_contract": {
    "authorization_receipt_field_contract": {
      "candidate_lock_receipt_hash": "sha256_equal_upstream_receipt_hash",
      "locked_slot_hash": "sha256_equal_candidate_lock",
      "locked_slot_index": "integer_equal_candidate_lock",
      "locked_structural_configuration_hash": "sha256_equal_candidate_lock",
      "receipt_schema_id": "constant:H40_RECEIPT_WF_VALIDATION_V2",
      "run_authority_id": "sha256_equal_candidate_lock",
      "upstream_receipt_hash": "sha256_of_candidate_lock_receipt",
      "validated_at_utc": "audit_timestamp_utc",
      "validation_verifier_id": "constant:H40_WF_VALIDATION_VERIFIER_V1",
      "verified_at_utc": "audit_timestamp_utc",
      "wf_validation_result_evidence_hash": "verified_evidence_sha256"
    },
    "authorized_transition": [
      "H40_CANDIDATE_LOCKED",
      "H40_WALK_FORWARD_VALIDATED"
    ],
    "fold_result_entry_field_contract": {
      "accepted_gate_input_evidence_hashes": "complete_object_sorted_by_accepted_gate_id_to_run_candidate_split_fold_and_contract_bound_sha256",
      "evaluation_input_evidence_hash": "sha256_of_complete_canonical_inputs_bound_to_run_candidate_split_fold_and_accepted_contracts",
      "fold_identity_hash": "sha256_derived_from_split_authority",
      "fold_id": "string_derived_from_split_authority",
      "partition_id": "string_derived_from_split_authority",
      "split_definition_hash": "sha256_derived_from_split_manifest"
    },
    "forbidden_authority": [
      "caller_supplied_all_wf_gates_passed_boolean",
      "summary_locator_or_hash_without_canonical_fold_evidence",
      "foreign_candidate_evidence",
      "foreign_or_modified_split_evidence"
    ],
    "receipt_hash_rule": "canonical_sha256(exact_authorization_receipt_field_contract_keys_only)",
    "result_evidence_hash_rule": "canonical_sha256(exact_wf_validation_result_evidence_fields_with_exact_fold_result_entry_fields)",
    "schema_id": "H40_LIFECYCLE_CHILD_WF_VALIDATION_V1",
    "verifier_obligations": [
      "load_every_fold_evidence_object_by_content_hash_validate_exact_schema_and_verify_run_candidate_split_fold_and_contract_lineage",
      "derive_the_complete_ordered_fold_set_from_split_manifest_and_split_attestation",
      "reject_missing_duplicate_extra_or_reordered_fold_identity",
      "recompute_candidate_identity_split_identity_every_accepted_validation_gate_and_aggregate_pass_status",
      "emit_authorization_receipt_only_when_every_accepted_gate_passes",
      "emit_termination_not_validation_authority_when_any_gate_fails",
      "reverify_result_evidence_and_all_gate_results_on_restore_before_transition_use"
    ],
    "wf_validation_result_evidence_field_contract": {
      "accepted_validation_contract_hashes": "complete_object_sorted_by_contract_id_to_hash_resolved_from_accepted_P2_semantic_authority_no_subset_or_extra",
      "candidate_lock_receipt_hash": "sha256",
      "created_at_utc": "audit_timestamp_utc",
      "evidence_schema_id": "constant:H40_WF_VALIDATION_RESULT_EVIDENCE_V1",
      "fold_result_entries": "array_in_authoritative_split_order",
      "locked_slot_hash": "sha256",
      "locked_slot_index": "integer_0_through_167",
      "locked_structural_configuration_hash": "sha256",
      "run_authority_id": "sha256",
      "split_attestation_hash": "sha256",
      "split_manifest_hash": "sha256",
      "validation_protocol_id": "constant:H40_PROTOCOL_V1_R3"
    }
  },
  "confirmation_ready_receipt_contract": {
    "authority_rules": [
      "wf_authorization_receipt_must_be_reverified",
      "candidate_run_and_split_lineage_must_match_exactly",
      "receipt_grants_waiting_state_only",
      "receipt_grants_no_confirmation_data_or_outcome_access",
      "f02_status_must_equal_OPEN_SEALED"
    ],
    "authorized_transition": [
      "H40_WALK_FORWARD_VALIDATED",
      "H40_CONFIRMATION_READY"
    ],
    "receipt_field_contract": {
      "confirmation_partition_end_utc": "constant:2026-02-01T00:00:00Z",
      "confirmation_partition_name": "constant:CONFIRMATION_HOLDOUT",
      "confirmation_partition_start_utc": "constant:2025-02-01T00:00:00Z",
      "f02_blocker_status": "constant:OPEN_SEALED",
      "locked_slot_hash": "sha256_equal_wf_authorization",
      "locked_slot_index": "integer_equal_wf_authorization",
      "locked_structural_configuration_hash": "sha256_equal_wf_authorization",
      "prepared_at_utc": "audit_timestamp_utc",
      "receipt_schema_id": "constant:H40_RECEIPT_CONFIRMATION_READY_V2",
      "run_authority_id": "sha256_equal_wf_authorization",
      "split_attestation_hash": "sha256_equal_verified_wf_evidence",
      "split_manifest_hash": "sha256_equal_verified_wf_evidence",
      "upstream_receipt_hash": "sha256_of_wf_validation_authorization_receipt",
      "wf_validation_receipt_hash": "sha256_equal_upstream_receipt_hash"
    },
    "receipt_hash_rule": "canonical_sha256(exact_receipt_field_contract_keys_only)",
    "schema_id": "H40_LIFECYCLE_CHILD_CONFIRMATION_READY_V1"
  },
  "termination_receipt_contract": {
    "accepted_reason_codes": [
      "CONFIG_IDENTITY_CONFLICT",
      "CONFIRMATION_HOLD_LOCKED",
      "CONFIRMATION_NOT_READY",
      "DUPLICATE_TIMESTAMP",
      "EXECUTION_DISABLED",
      "FAMILY_PAIR_RESTRICTED",
      "HORIZON_TRUNCATED",
      "INTERVAL_MISMATCH",
      "LOOKBACK_RESERVED",
      "NOT_TESTABLE",
      "OUTSIDE_PREREGISTERED_SPLIT",
      "PIT_UNAVAILABLE",
      "PRODUCT_MISMATCH",
      "PROTECTED_SURFACE_DENIED",
      "PURGE_BOUNDARY",
      "SEARCH_BUDGET_EXHAUSTED",
      "SOURCE_GAP",
      "SOURCE_HASH_MISMATCH",
      "SOURCE_MISSING",
      "SOURCE_UNVERIFIED",
      "THRESHOLD_UNMET",
      "UNAUTHORIZED_FAMILY"
    ],
    "authority_rules": [
      "termination_receipt_never_authorizes_forward_progress",
      "H40_NO_GO_and_NOT_TESTABLE_are_absorbing",
      "reason_code_must_belong_to_the_accepted_H40ReasonCode_vocabulary",
      "failure_evidence_when_present_must_be_loaded_and_content_hash_verified",
      "source_state_and_upstream_receipt_must_match_current_verified_chain"
    ],
    "receipt_field_contract": {
      "detail_message": "audit_string",
      "failure_evidence_hash": "sha256_or_null",
      "reason_code": "accepted_H40ReasonCode",
      "receipt_schema_id": "constant:H40_RECEIPT_TERMINATION_V2",
      "run_authority_id": "sha256",
      "source_state": "current_lifecycle_state",
      "target_state": "enum:H40_NO_GO_or_NOT_TESTABLE",
      "terminated_at_utc": "audit_timestamp_utc",
      "upstream_receipt_hash": "current_verified_receipt_sha256_or_null"
    },
    "receipt_hash_rule": "canonical_sha256(exact_receipt_field_contract_keys_only)",
    "schema_id": "H40_LIFECYCLE_CHILD_TERMINATION_V1",
    "terminal_states": [
      "H40_NO_GO",
      "NOT_TESTABLE"
    ]
  },
  "transition_matrix_contract": {
    "global_rules": [
      "state_adjacency_is_necessary_never_sufficient",
      "current_executable_HEAD_is_never_required_to_equal_historical_P1_commit",
      "P1_scaffold_transition_verifies_historical_acceptance_artifact_integrity_and_frozen_scientific_identity",
      "executable_authority_for_discovery_is_the_accepted_lifecycle_implementation_authority",
      "all_unlisted_transitions_are_forbidden",
      "terminal_states_are_absorbing",
      "H40_P1_SCAFFOLDED_to_H40_DISCOVERY_requires_current_accepted_controller_authority_and_matching_exact_run_grant",
      "every_production_transition_authorization_rechecks_current_in_process_lifecycle_implementation_and_controller_authority_anchors",
      "superseded_long_lived_production_service_authority_fails_closed",
      "hot_authority_republication_requires_new_process_or_service_identity"
    ],
    "historical_scaffold_lineage": {
      "p1_accepted_code_baseline_commit_sha": "1ddb8eea3259791cf213be03f09557396a03160f",
      "p1_final_acceptance_commit_sha": "1141baec371d53978c5d9751607979fee21464b3",
      "p2_acceptance_record_commit_sha": "52ca0cdb53e5c2dd579ddf4a884d671825f970df",
      "p2_accepted_code_baseline_commit_sha": "ac5e3a1d6c1423f7fe9639e2f5f78095df27d400",
      "p2_final_acceptance_commit_sha": "3208ca92525ed88d31635a6ac9ce9cd4ac6ec725",
      "p2r1_implementation_commit_sha": "81dc2f9bb9a203cb4c72dc6a646aafab1f1985d0",
      "rule": "verify_historical_lineage_and_artifact_integrity_only_never_current_executable_HEAD_equality"
    },
    "rows": [
      {
        "authority": "P1_LINEAGE_VERIFIER_V1",
        "source": "H40_PREREGISTERED",
        "target": "H40_P1_SCAFFOLDED"
      },
      {
        "authority": "H40_RECEIPT_DISCOVERY_AUTH_V3",
        "source": "H40_P1_SCAFFOLDED",
        "target": "H40_DISCOVERY"
      },
      {
        "authority": "H40_RECEIPT_TERMINATION_V2",
        "source": "H40_P1_SCAFFOLDED",
        "target": "H40_NO_GO"
      },
      {
        "authority": "H40_RECEIPT_TERMINATION_V2",
        "source": "H40_P1_SCAFFOLDED",
        "target": "NOT_TESTABLE"
      },
      {
        "authority": "H40_RECEIPT_CANDIDATE_LOCK_V2_AFTER_RESULT_RECOMPUTATION",
        "source": "H40_DISCOVERY",
        "target": "H40_CANDIDATE_LOCKED"
      },
      {
        "authority": "H40_RECEIPT_TERMINATION_V2",
        "source": "H40_DISCOVERY",
        "target": "H40_NO_GO"
      },
      {
        "authority": "H40_RECEIPT_TERMINATION_V2",
        "source": "H40_DISCOVERY",
        "target": "NOT_TESTABLE"
      },
      {
        "authority": "H40_RECEIPT_WF_VALIDATION_V2_AFTER_RESULT_RECOMPUTATION",
        "source": "H40_CANDIDATE_LOCKED",
        "target": "H40_WALK_FORWARD_VALIDATED"
      },
      {
        "authority": "H40_RECEIPT_TERMINATION_V2_NO_RUNNER_UP",
        "source": "H40_CANDIDATE_LOCKED",
        "target": "H40_NO_GO"
      },
      {
        "authority": "H40_RECEIPT_CONFIRMATION_READY_V2",
        "source": "H40_WALK_FORWARD_VALIDATED",
        "target": "H40_CONFIRMATION_READY"
      },
      {
        "authority": "H40_RECEIPT_TERMINATION_V2",
        "source": "H40_WALK_FORWARD_VALIDATED",
        "target": "H40_NO_GO"
      },
      {
        "authority": "PROHIBITED_BY_H40_FSA_F02",
        "source": "H40_CONFIRMATION_READY",
        "target": "H40_CONFIRMATION_EVALUATED_ONCE"
      },
      {
        "authority": "H40_RECEIPT_TERMINATION_V2",
        "source": "H40_CONFIRMATION_READY",
        "target": "H40_NO_GO"
      }
    ],
    "schema_id": "H40_LIFECYCLE_CHILD_TRANSITION_MATRIX_V1",
    "production_discovery_preconditions": {
      "controller_authority_hash_rule": "must_equal_current_in_process_ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH",
      "controller_authority_schema_id": "H40_P3_CONTROLLER_AUTHORITY_V1",
      "discovery_run_grant_hash_rule": "must_recompute_and_match_exact_current_H40_DISCOVERY_RUN_GRANT_V1",
      "discovery_run_grant_schema_id": "H40_DISCOVERY_RUN_GRANT_V1",
      "execution_disabled": "constant:true",
      "legacy_discovery_receipt_policy": "H40_RECEIPT_DISCOVERY_AUTH_V2_INVALID_FOR_PRODUCTION",
      "receipt_schema_id": "H40_RECEIPT_DISCOVERY_AUTH_V3"
    }
  },
  "persistence_replay_contract": {
    "authorization_receipt_issuance": "only_the_accepted_implementation_verifier_may_atomically_construct_and_persist_authorization_after_recomputation_external_caller_receipts_are_inputs_for_reverification_not_trusted_claims",
    "canonical_storage_key": "artifacts/h40/lifecycle/runs/<run_authority_id>",
    "capability_lifetime_rule": "every_production_transition_issue_revalidation_consumption_persistence_and_cold_restore_must_recursively_reverify_root_runtime_snapshot_seal_current_active_source_truth_and_current_in_process_lifecycle_implementation_and_controller_authority_anchors; cached_or_restored_authority_must_apply_the_same_checks; superseded_service_authority_fails_closed",
    "cross_boundary_checks": [
      "run_authority_id_equal_at_every_chain_link",
      "candidate_identity_equal_from_lock_through_confirmation_ready",
      "split_manifest_and_attestation_equal_from_discovery_through_confirmation_ready",
      "upstream_hash_equal_recomputed_predecessor_hash",
      "lifecycle_governance_and_implementation_authorities_equal_accepted_values",
      "controller_authority_hash_equal_current_in_process_ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH",
      "discovery_run_grant_hash_recomputed_and_equal_bound_H40_DISCOVERY_RUN_GRANT_V1",
      "production_persistence_context_is_H40_LIFECYCLE_PERSISTENCE_CONTEXT_V2",
      "production_discovery_lineage_uses_H40_RECEIPT_DISCOVERY_AUTH_V3"
    ],
    "durable_run_head_contract": {
      "concurrency_rule": "head_commit_must_be_a_linearizable_transactional_compare_and_advance_single_winner_stale_or_conflicting_writers_fail_closed",
      "field_contract": {
        "head_predecessor_receipt_hash": "sha256_or_null",
        "head_receipt_hash": "sha256",
        "head_state": "accepted_lifecycle_state_equal_head_receipt_target_state",
        "run_authority_id": "sha256_equal_current_run",
        "schema_id": "constant:H40_DURABLE_RUN_HEAD_V1",
        "terminal": "boolean_derived_from_accepted_terminal_states",
        "transition_sequence": "integer_gte_0_monotonic_by_exactly_one"
      },
      "head_hash_rule": "canonical_sha256(exact_field_contract_keys_only)",
      "ownership_rule": "exactly_one_committed_authoritative_head_per_run_authority_id",
      "restore_rule": "only_receipts_reachable_from_the_current_committed_head_lineage_may_be_restored_as_authority",
      "terminal_rule": "committed_terminal_head_is_absorbing_across_process_restart_and_all_later_consumers",
      "transition_rule": "successor_commit_requires_expected_predecessor_receipt_hash_equal_current_committed_head_receipt_hash_expected_sequence_equal_current_sequence_plus_one_and_current_head_not_terminal"
    },
    "failure_semantics": "any_missing_extra_malformed_hash_mismatch_lineage_mismatch_cross_run_cross_candidate_cross_split_stale_head_conflicting_successor_or_terminal_successor_condition_fails_closed_with_no_committed_state_advance",
    "persistence_rules": [
      "receipt_and_bound_evidence_bytes_are_fully_materialized_and_fsynced_before_final_publication",
      "immutable_receipts_are_content_addressed_and_atomically_published_without_overwriting_different_existing_bytes",
      "unreferenced_fully_published_receipts_are_uncommitted_orphans_and_confer_no_lifecycle_authority",
      "temporary_or_partial_artifacts_never_confer_authority",
      "the_durable_run_head_is_the_only_commit_point_for_run_history",
      "durable_run_head_advance_uses_linearizable_transactional_compare_and_advance_against_expected_predecessor_and_sequence",
      "different_successor_for_the_same_committed_predecessor_is_rejected",
      "identical_transition_retry_is_idempotent_only_after_full_reverification_and_exact_committed_successor_match",
      "restore_recomputes_every_content_hash_every_authoritative_verifier_result_and_root_runtime_source_truth",
      "restore_accepts_only_the_current_committed_head_or_receipts_on_its_unique_ancestor_lineage",
      "directory_filename_and_caller_label_have_no_authority",
      "authorization_receipts_and_bound_result_evidence_are_write_once",
      "production_persistence_requires_H40_LIFECYCLE_PERSISTENCE_CONTEXT_V2_with_controller_authority_hash_and_discovery_run_grant_hash",
      "production_cold_restore_rejects_H40_LIFECYCLE_PERSISTENCE_CONTEXT_V1_and_H40_RECEIPT_DISCOVERY_AUTH_V2",
      "production_persistence_and_restore_revalidate_current_in_process_lifecycle_implementation_and_controller_authority_anchors_and_exact_bound_run_grant",
      "hot_authority_republication_requires_new_process_or_service_identity_before_new_authoritative_operations"
    ],
    "run_authority_field_contract": {
      "discovery_selection_correction_contract_hash": "constant:f84c97050c7db813263e5ffda6b1c556af0b7b0e2876bb8616640d2c9d67084b",
      "lifecycle_governance_authority_hash": "accepted_sha256",
      "lifecycle_implementation_authority_hash": "accepted_sha256",
      "materialized_run_authority_hash": "sha256",
      "protocol_authority_hash": "constant:a83f8fc7a5ca7109fb8cd7fed114d87c3b2c968b5145c11cada203aa5111d1ce",
      "schema_id": "constant:H40_RUN_AUTHORITY_V1",
      "sealed_registered_roster_hash": "sha256",
      "semantic_root_hash": "constant:71889a35f227ed734272b712851174a69bf9dbb12ea3f87cd84c26e7c66f6af1",
      "source_manifest_hash": "sha256",
      "split_attestation_hash": "sha256",
      "split_manifest_hash": "sha256",
      "structural_ledger_hash": "constant:483f68502b57972deae071c7bd4587ca3e57ccaa72bd99fb0de07b4f0ab8c85f"
    },
    "run_authority_rule": "run_authority_id_equals_canonical_sha256_of_exact_run_authority_field_contract_keys_only",
    "run_instance_nonce": "none",
    "schema_id": "H40_LIFECYCLE_CHILD_PERSISTENCE_REPLAY_V2",
    "timestamp_rule": "exact_YYYY-MM-DDTHH:MM:SSZ_calendar_valid_UTC_hash_bound_audit_only_never_authorization_critical_no_clock_tolerance",
    "persistence_context_contract": {
      "context_hash_rule": "canonical_sha256(exact_field_contract_keys_only)",
      "field_contract": {
        "controller_authority_hash": "sha256_equal_current_in_process_ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH",
        "discovery_run_grant_hash": "sha256_equal_bound_H40_DISCOVERY_RUN_GRANT_V1",
        "implementation_authority_hash": "sha256_equal_current_in_process_ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH",
        "predecessor_receipt_hash": "sha256_or_null",
        "run_authority_id": "sha256_equal_current_run",
        "runtime_seal_hash": "sha256_equal_current_runtime_snapshot_seal",
        "schema_id": "constant:H40_LIFECYCLE_PERSISTENCE_CONTEXT_V2",
        "split_authority_hash": "sha256_or_null"
      },
      "legacy_policy": "H40_LIFECYCLE_PERSISTENCE_CONTEXT_V1_INVALID_FOR_PRODUCTION",
      "schema_id": "H40_LIFECYCLE_PERSISTENCE_CONTEXT_V2"
    }
  },
  "runtime_snapshot_seal_contract": {
    "materialized_run_authority_binding": [
      "runtime_authority_snapshot_hash",
      "source_manifest_hash",
      "split_manifest_hash",
      "split_attestation_hash",
      "sealed_registered_roster_hash",
      "registered_slot_count",
      "not_testable_slot_count",
      "total_slot_count"
    ],
    "roster_entry_field_contract": {
      "family_id": "accepted_family_id",
      "slot_hash": "sha256",
      "slot_index": "integer_0_through_167",
      "structural_configuration_hash": "sha256"
    },
    "roster_hash_rule": "canonical_sha256(array_of_exact_roster_entries_sorted_by_structural_configuration_hash_ascending)",
    "runtime_source_split_attestation_contract": {
      "active_source_evidence_entry_field_contract": {
        "file_sha256": "sha256_equal_source_record_receipt_and_cold_validation_receipt",
        "source_id": "accepted_source_id_required_by_at_least_one_sealed_REGISTERED_slot",
        "source_record_hash": "canonical_sha256(exact_runtime_source_record)",
        "source_validation_receipt_hash": "canonical_sha256(exact_cold_validation_receipt)",
        "timestamp_count": "integer_gt_0_equal_source_record_receipt_and_cold_validation_receipt",
        "timestamp_membership_hash": "sha256_equal_source_record_receipt_and_cold_validation_receipt"
      },
      "attestation_field_contract": {
        "accepted_reference_source_manifest_hash": "constant:af7fe2c187dcd503ba27a3f24ba6347cb3c619a63662106e85c6343eda90a74c",
        "accepted_reference_split_manifest_hash": "constant:6e3ed51b4139c7822343752e29b6d8b2e94f9fadf0def38f2101a444b1da62e9",
        "active_required_source_ids": "array_of_unique_source_ids_sorted_ascending_derived_as_union_of_project_required_sources_for_exact_sealed_REGISTERED_roster",
        "active_source_evidence": "array_of_exact_active_source_evidence_entries_sorted_by_source_id",
        "not_testable_slot_count": "integer_derived_from_sealed_runtime_projection",
        "not_testable_source_ids": "array_of_source_ids_sorted_ascending_whose_accepted_runtime_state_is_NOT_TESTABLE",
        "protocol_identity_hash": "constant:6533e880ced04214262f84c21fee98c478ef5c09fa7d0b9f55d650e673a1f971",
        "registered_slot_count": "integer_derived_from_sealed_runtime_projection",
        "runtime_authority_snapshot_hash": "sha256_of_exact_runtime_authority_snapshot_preimage",
        "runtime_authority_snapshot_id": "accepted_nonempty_snapshot_id_bound_into_runtime_authority_snapshot_hash",
        "schema_id": "constant:H40_RUNTIME_SOURCE_SPLIT_ATTESTATION_V1",
        "sealed_registered_roster_hash": "sha256_equal_runtime_seal",
        "source_authority_state_entries": "array_of_exact_source_authority_state_entries_sorted_by_source_id",
        "source_manifest_hash": "sha256_of_exact_runtime_source_manifest",
        "split_manifest_hash": "sha256_of_exact_runtime_scoped_authoritative_split_manifest",
        "structural_ledger_hash": "constant:483f68502b57972deae071c7bd4587ca3e57ccaa72bd99fb0de07b4f0ab8c85f",
        "total_slot_count": "constant:168"
      },
      "attestation_hash_rule": "canonical_sha256(exact_attestation_field_contract_keys_with_exact_nested_entry_fields)",
      "source_authority_state_entry_field_contract": {
        "production_authority_state": "enum:VERIFIED_or_NOT_TESTABLE_equal_accepted_runtime_authority_snapshot",
        "source_id": "accepted_runtime_source_id"
      },
      "verifier_rules": [
        "require_typed_runtime_source_manifest_typed_runtime_split_manifest_and_exact_H40_RUNTIME_SOURCE_SPLIT_ATTESTATION_V1",
        "recompute_source_manifest_split_manifest_attestation_and_runtime_snapshot_hashes_from_exact_canonical_objects",
        "require_source_authority_state_entries_to_equal_the_complete_accepted_runtime_snapshot_preimage_without_inferring_authority_from_local_file_presence",
        "derive_active_required_source_ids_as_the_exact_union_of_project_required_sources_over_the_complete_sealed_REGISTERED_roster",
        "require_every_active_required_source_to_be_VERIFIED_in_the_accepted_runtime_snapshot_and_every_REGISTERED_slot_to_have_no_other_source_dependency",
        "identity_validate_every_runtime_source_record_against_the_accepted_reference_source_manifest_without_promoting_NOT_TESTABLE_sources",
        "cold_validate_only_every_active_required_source_and_bind_its_exact_record_receipt_file_and_timestamp_membership_hashes",
        "require_not_testable_source_ids_to_equal_the_accepted_NOT_TESTABLE_snapshot_entries_and_forbid_active_source_evidence_for_them",
        "verify_the_static_partition_calendar_against_the_accepted_reference_split_manifest_independently_of_source_availability",
        "reconstruct_the_runtime_split_partitions_counts_exclusions_and_timestamp_hashes_from_the_intersection_of_exactly_the_cold_verified_active_required_sources",
        "require_runtime_split_manifest_is_authoritative_true_under_this_attestation_and_never_treat_that_flag_as_sufficient_authority",
        "require_runtime_split_protocol_source_manifest_and_attestation_lineage_to_match_exactly",
        "reject_legacy_BTC_and_ETH_pair_attestation_synthetic_attestation_preregistered_schedule_only_and_hash_self_consistency_without_evidence_truth",
        "bind_the_same_source_manifest_split_manifest_and_runtime_source_split_attestation_hashes_through_Discovery_WF_restore_and_replay"
      ]
    },
    "schema_id": "H40_LIFECYCLE_CHILD_RUNTIME_SNAPSHOT_SEAL_V2",
    "seal_rules": [
      "seal_before_any_discovery_label_return_metric_or_candidate_result_access",
      "REGISTERED_and_NOT_TESTABLE_are_derived_from_the_sealed_materialized_authority",
      "counts_must_sum_to_total_slot_count_and_roster_length_must_equal_registered_slot_count",
      "roster_entries_must_match_the_accepted_168_row_structural_ledger",
      "post_seal_source_state_change_cannot_mutate_or_expand_the_active_roster",
      "a_different_snapshot_or_materialized_authority_produces_a_different_run_authority_id",
      "runtime_source_state_changes_never_change_protocol_semantic_or_structural_ledger_hashes"
    ]
  },
  "f02_boundary_contract": {
    "allowed_scope": "define_H40ConfirmationReadyReceipt_and_verified_lineage_only",
    "confirmation_state": "sealed_waiting_state_only",
    "forbidden_capabilities": [
      "confirmation_nonce",
      "confirmation_unlock_key",
      "one_shot_evaluation_authority",
      "confirmation_outcome_access",
      "confirmation_evaluation_execution"
    ],
    "guard_result": "H40GuardError_with_CONFIRMATION_NOT_READY",
    "prohibited_transition": [
      "H40_CONFIRMATION_READY",
      "H40_CONFIRMATION_EVALUATED_ONCE"
    ],
    "schema_id": "H40_LIFECYCLE_CHILD_F02_BOUNDARY_V1",
    "status": "H40_FSA_F02_OPEN_SEALED"
  }
}
'''

_LIFECYCLE_CONTRACTS: dict[str, Any] = json.loads(_LIFECYCLE_CONTRACTS_JSON)

EXPECTED_LIFECYCLE_CHILD_HASHES: Mapping[str, str] = MappingProxyType({
    "discovery_authorization_receipt_contract": "3dd91827d4a26441bd5218dc299f196841c471eb60f20e03881d2ad56ce36898",
    "candidate_lock_receipt_contract": "96756dfebab636baa1abb33364e307d99d90a61572b813c6a60504283d3d42df",
    "wf_validation_receipt_contract": "bb5698a85daec1a5b9dcd169bde3d575befe8c0a1d73c2e87136cf35afb4001b",
    "confirmation_ready_receipt_contract": "7ab0ae0c8acb17340eccaa2bb737a5300e679b8de7497a539bdc44e93d3109be",
    "termination_receipt_contract": "b45c7021db1c63a447ddb22a1f9cb787ce71a5048c824ce38d40f19f755ecb48",
    "transition_matrix_contract": "bea7b0593251204bbc9138c325f1c9f10ccf7a9b8df60f10bf991377e0ced42d",
    "persistence_replay_contract": "51e4fe6155d388c076dd1788a100265eb17b232300481a3fbcf00150f1432de1",
    "runtime_snapshot_seal_contract": "76a0732742707c78f65da26263076bed7b586ea67d4f5ddd2dac33761e37e612",
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
        "f01r2_amendment_identity": {
            "artifact_path": "reviews/v0.5/V0.5.1_H40_F01R2_SOURCE_SPLIT_RUNTIME_AUTHORITY_COMPATIBILITY_CLOSURE.md",
            "commit_sha": "342953fcb80b1eec905805acb226ddef591861bf",
        },
        "f01r3_amendment_identity": {
            "artifact_path": "reviews/v0.5/V0.5.1_H40_F01R3_SOL_ADJUDICATION_AND_CANONICAL_AMENDMENT.md",
            "commit_sha": "b4a1603671b11f051080f2b178b3a7fa8b089b33",
        },
        "lifecycle_semantic_root_hash": compute_lifecycle_semantic_root_hash(),
        "p2_final_acceptance_identity": {
            "artifact_path": "reviews/v0.5/V0.5.1_H40_P2_FINAL_INDEPENDENT_ACCEPTANCE.md",
            "commit_sha": "3208ca92525ed88d31635a6ac9ce9cd4ac6ec725",
        },
        "p3r0r1_amendment_identity": {
            "artifact_path": "reviews/v0.5/V0.5.1_H40_P3R0R1_LIFECYCLE_EVIDENCE_AUTHORITY_REPAIR.md",
            "commit_sha": "010d1462b33a6f133dd590086baae19cb0a0e0cb",
        },
        "pre_discovery_repair_contract_acceptance_identity": {
            "artifact_path": "reviews/v0.5/V0.5.1_H40_PRE_DISCOVERY_REPAIR_CONTRACT_CONTROLLER_ACCEPTANCE.md",
            "commit_sha": "2229d44c5cc9b88ba515d0b2931d20f05936c7e8",
        },
        "prior_lifecycle_governance_authority_hash": (
            "7e9433aa2ee706dda61871c6ad2b1a1aee4cf7a8f9b6365351942096b5347c84"
        ),
        "protocol_authority_hash": compute_protocol_authority_hash(),
        "schema_id": "H40_LIFECYCLE_GOVERNANCE_AUTHORITY_V5",
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


@dataclass(frozen=True)
class H40SourceAuthorityStateEntry:
    """One complete accepted runtime source-state projection entry."""

    source_id: str
    production_authority_state: str

    _KEYS: ClassVar[frozenset[str]] = frozenset({
        "production_authority_state",
        "source_id",
    })

    def __post_init__(self) -> None:
        _require_text(self.source_id, "source_id")
        if self.production_authority_state not in {"VERIFIED", "NOT_TESTABLE"}:
            raise ValueError("production_authority_state must be VERIFIED or NOT_TESTABLE")

    def to_dict(self) -> dict[str, str]:
        return {
            "production_authority_state": self.production_authority_state,
            "source_id": self.source_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40SourceAuthorityStateEntry:
        _require_exact_keys(data, cls._KEYS, cls.__name__)
        _require_string_fields(data, cls._KEYS, cls.__name__)
        return cls(
            source_id=str(data["source_id"]),
            production_authority_state=str(data["production_authority_state"]),
        )


@dataclass(frozen=True)
class H40ActiveSourceEvidenceEntry:
    """Content-addressed cold evidence for one and only one active source."""

    source_id: str
    source_record_hash: str
    source_validation_receipt_hash: str
    file_sha256: str
    timestamp_membership_hash: str
    timestamp_count: int

    _KEYS: ClassVar[frozenset[str]] = frozenset({
        "file_sha256",
        "source_id",
        "source_record_hash",
        "source_validation_receipt_hash",
        "timestamp_count",
        "timestamp_membership_hash",
    })

    def __post_init__(self) -> None:
        _require_text(self.source_id, "source_id")
        for name in (
            "source_record_hash",
            "source_validation_receipt_hash",
            "file_sha256",
            "timestamp_membership_hash",
        ):
            _require_sha256(getattr(self, name), name)
        if (
            isinstance(self.timestamp_count, bool)
            or not isinstance(self.timestamp_count, int)
            or self.timestamp_count <= 0
        ):
            raise ValueError("timestamp_count must be a positive integer")

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_sha256": self.file_sha256,
            "source_id": self.source_id,
            "source_record_hash": self.source_record_hash,
            "source_validation_receipt_hash": self.source_validation_receipt_hash,
            "timestamp_count": self.timestamp_count,
            "timestamp_membership_hash": self.timestamp_membership_hash,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40ActiveSourceEvidenceEntry:
        _require_exact_keys(data, cls._KEYS, cls.__name__)
        _require_string_fields(data, cls._KEYS - {"timestamp_count"}, cls.__name__)
        count = data["timestamp_count"]
        if isinstance(count, bool) or not isinstance(count, int):
            raise TypeError("timestamp_count must be an integer")
        return cls(
            source_id=str(data["source_id"]),
            source_record_hash=str(data["source_record_hash"]),
            source_validation_receipt_hash=str(data["source_validation_receipt_hash"]),
            file_sha256=str(data["file_sha256"]),
            timestamp_membership_hash=str(data["timestamp_membership_hash"]),
            timestamp_count=count,
        )


@dataclass(frozen=True)
class H40RuntimeSourceSplitAttestation:
    """Canonical F01R2 evidence authority for runtime sources and split."""

    accepted_reference_source_manifest_hash: str
    accepted_reference_split_manifest_hash: str
    protocol_identity_hash: str
    runtime_authority_snapshot_id: str
    runtime_authority_snapshot_hash: str
    source_authority_state_entries: tuple[H40SourceAuthorityStateEntry, ...]
    source_manifest_hash: str
    structural_ledger_hash: str
    sealed_registered_roster_hash: str
    registered_slot_count: int
    not_testable_slot_count: int
    total_slot_count: int
    active_required_source_ids: tuple[str, ...]
    not_testable_source_ids: tuple[str, ...]
    active_source_evidence: tuple[H40ActiveSourceEvidenceEntry, ...]
    split_manifest_hash: str
    schema_id: str = "H40_RUNTIME_SOURCE_SPLIT_ATTESTATION_V1"

    _KEYS: ClassVar[frozenset[str]] = frozenset({
        "accepted_reference_source_manifest_hash",
        "accepted_reference_split_manifest_hash",
        "active_required_source_ids",
        "active_source_evidence",
        "not_testable_slot_count",
        "not_testable_source_ids",
        "protocol_identity_hash",
        "registered_slot_count",
        "runtime_authority_snapshot_hash",
        "runtime_authority_snapshot_id",
        "schema_id",
        "sealed_registered_roster_hash",
        "source_authority_state_entries",
        "source_manifest_hash",
        "split_manifest_hash",
        "structural_ledger_hash",
        "total_slot_count",
    })

    def __post_init__(self) -> None:
        if self.schema_id != "H40_RUNTIME_SOURCE_SPLIT_ATTESTATION_V1":
            raise ValueError("runtime source/split attestation schema mismatch")
        _require_text(self.runtime_authority_snapshot_id, "runtime_authority_snapshot_id")
        for name in (
            "accepted_reference_source_manifest_hash",
            "accepted_reference_split_manifest_hash",
            "protocol_identity_hash",
            "runtime_authority_snapshot_hash",
            "source_manifest_hash",
            "structural_ledger_hash",
            "sealed_registered_roster_hash",
            "split_manifest_hash",
        ):
            _require_sha256(getattr(self, name), name)
        states = tuple(self.source_authority_state_entries)
        evidence = tuple(self.active_source_evidence)
        active_ids = tuple(self.active_required_source_ids)
        not_testable_ids = tuple(self.not_testable_source_ids)
        if not all(isinstance(item, H40SourceAuthorityStateEntry) for item in states):
            raise TypeError("source authority states must use the typed schema")
        if not all(isinstance(item, H40ActiveSourceEvidenceEntry) for item in evidence):
            raise TypeError("active source evidence must use the typed schema")
        if states != tuple(sorted(states, key=lambda item: item.source_id)):
            raise ValueError("source authority state entries must be sorted by source_id")
        if evidence != tuple(sorted(evidence, key=lambda item: item.source_id)):
            raise ValueError("active source evidence must be sorted by source_id")
        if active_ids != tuple(sorted(set(active_ids))) or not active_ids:
            raise ValueError("active_required_source_ids must be non-empty, unique, and sorted")
        if not_testable_ids != tuple(sorted(set(not_testable_ids))):
            raise ValueError("not_testable_source_ids must be unique and sorted")
        state_ids = tuple(item.source_id for item in states)
        evidence_ids = tuple(item.source_id for item in evidence)
        if len(state_ids) != len(set(state_ids)):
            raise ValueError("duplicate source authority state entry")
        if evidence_ids != active_ids:
            raise ValueError("active source evidence must exactly cover active required sources")
        state_map = {item.source_id: item.production_authority_state for item in states}
        if any(state_map.get(source_id) != "VERIFIED" for source_id in active_ids):
            raise ValueError("every active required source must be VERIFIED")
        if tuple(sorted(k for k, value in state_map.items() if value == "NOT_TESTABLE")) != not_testable_ids:
            raise ValueError("not_testable_source_ids must exactly match source authority states")
        if set(active_ids) & set(not_testable_ids):
            raise ValueError("NOT_TESTABLE sources cannot provide active evidence")
        for name in ("registered_slot_count", "not_testable_slot_count", "total_slot_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
        if self.total_slot_count != 168:
            raise ValueError("accepted H40 V1 total_slot_count must equal 168")
        if self.registered_slot_count + self.not_testable_slot_count != self.total_slot_count:
            raise ValueError("runtime attestation slot counts must sum to total")
        object.__setattr__(self, "source_authority_state_entries", states)
        object.__setattr__(self, "active_source_evidence", evidence)
        object.__setattr__(self, "active_required_source_ids", active_ids)
        object.__setattr__(self, "not_testable_source_ids", not_testable_ids)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted_reference_source_manifest_hash": self.accepted_reference_source_manifest_hash,
            "accepted_reference_split_manifest_hash": self.accepted_reference_split_manifest_hash,
            "active_required_source_ids": list(self.active_required_source_ids),
            "active_source_evidence": [item.to_dict() for item in self.active_source_evidence],
            "not_testable_slot_count": self.not_testable_slot_count,
            "not_testable_source_ids": list(self.not_testable_source_ids),
            "protocol_identity_hash": self.protocol_identity_hash,
            "registered_slot_count": self.registered_slot_count,
            "runtime_authority_snapshot_hash": self.runtime_authority_snapshot_hash,
            "runtime_authority_snapshot_id": self.runtime_authority_snapshot_id,
            "schema_id": self.schema_id,
            "sealed_registered_roster_hash": self.sealed_registered_roster_hash,
            "source_authority_state_entries": [item.to_dict() for item in self.source_authority_state_entries],
            "source_manifest_hash": self.source_manifest_hash,
            "split_manifest_hash": self.split_manifest_hash,
            "structural_ledger_hash": self.structural_ledger_hash,
            "total_slot_count": self.total_slot_count,
        }

    @property
    def attestation_hash(self) -> str:
        return canonical_sha256(self.to_dict())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40RuntimeSourceSplitAttestation:
        _require_exact_keys(data, cls._KEYS, cls.__name__)
        for name in ("active_required_source_ids", "not_testable_source_ids"):
            value = data[name]
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise TypeError(f"{name} must be an array of strings")
        states = data["source_authority_state_entries"]
        evidence = data["active_source_evidence"]
        if not isinstance(states, list) or not all(isinstance(item, Mapping) for item in states):
            raise TypeError("source_authority_state_entries must be an array of objects")
        if not isinstance(evidence, list) or not all(isinstance(item, Mapping) for item in evidence):
            raise TypeError("active_source_evidence must be an array of objects")
        kwargs = dict(data)
        kwargs["source_authority_state_entries"] = tuple(
            H40SourceAuthorityStateEntry.from_dict(item) for item in states
        )
        kwargs["active_source_evidence"] = tuple(
            H40ActiveSourceEvidenceEntry.from_dict(item) for item in evidence
        )
        kwargs["active_required_source_ids"] = tuple(data["active_required_source_ids"])
        kwargs["not_testable_source_ids"] = tuple(data["not_testable_source_ids"])
        return cls(**kwargs)


def _slot_family_id(families: Sequence[Any]) -> str:
    return "+".join(str(getattr(item, "value", item)) for item in families)


_PRODUCTION_SEAL_TOKEN = object()
_SYNTHETIC_SEAL_TOKEN = object()


def _accepted_production_roster() -> tuple[
    tuple[H40RuntimeRosterEntry, ...],
    int,
    int,
    str,
]:
    from .search_space import materialize_h40_search_space_production

    ledger = materialize_h40_search_space_production()
    if ledger.structural_ledger_hash != EXPECTED_STRUCTURAL_LEDGER_HASH:
        raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "structural ledger hash mismatch")
    if ledger.slot_count != 168:
        raise H40GuardError(
            H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
            "accepted production search space must contain exactly 168 slots",
        )
    roster = tuple(
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
    snapshot_hash = current_p1_authority_snapshot().runtime_authority_snapshot_hash
    return roster, len(roster), ledger.slot_count - len(roster), snapshot_hash


def _runtime_authority_components() -> tuple[
    tuple[H40RuntimeRosterEntry, ...],
    int,
    int,
    tuple[str, ...],
    tuple[H40SourceAuthorityStateEntry, ...],
    tuple[str, ...],
]:
    from .search_space import (
        derive_required_sources_for_slot,
        materialize_h40_search_space_production,
    )

    ledger = materialize_h40_search_space_production()
    roster, registered_count, not_testable_count, _ = _accepted_production_roster()
    registered_slots = tuple(slot for slot in ledger.slots if slot.status == "REGISTERED")
    active_source_ids = tuple(sorted({
        source_id
        for slot in registered_slots
        for source_id in derive_required_sources_for_slot(slot)
    }))
    snapshot = current_p1_authority_snapshot()
    state_entries_list: list[H40SourceAuthorityStateEntry] = []
    for source_id, state in sorted(snapshot.per_source_states.items()):
        if not isinstance(state, str):
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "runtime authority source state must be a string",
            )
        state_entries_list.append(H40SourceAuthorityStateEntry(
            source_id=source_id,
            production_authority_state=state,
        ))
    state_entries = tuple(state_entries_list)
    state_map = {item.source_id: item.production_authority_state for item in state_entries}
    if any(state_map.get(source_id) != "VERIFIED" for source_id in active_source_ids):
        raise H40GuardError(
            H40ReasonCode.SOURCE_UNVERIFIED,
            "a REGISTERED slot depends on a source not VERIFIED by accepted runtime authority",
        )
    for slot in registered_slots:
        required = derive_required_sources_for_slot(slot)
        if not required or any(source_id not in active_source_ids for source_id in required):
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "REGISTERED slot source projection is incomplete",
            )
    not_testable_source_ids = tuple(
        item.source_id
        for item in state_entries
        if item.production_authority_state == "NOT_TESTABLE"
    )
    return (
        roster,
        registered_count,
        not_testable_count,
        active_source_ids,
        state_entries,
        not_testable_source_ids,
    )


def _assert_runtime_manifest_inventory(
    source_manifest: H40SourceManifest,
    protocol_identity_hash: str,
) -> None:
    reference = H40SourceManifest.build_preregistered_reference(protocol_identity_hash)
    if source_manifest.protocol_identity_hash != protocol_identity_hash:
        raise H40GuardError(
            H40ReasonCode.SOURCE_UNVERIFIED,
            "runtime source manifest protocol identity mismatch",
        )
    reference_ids = tuple(item.source_id for item in reference.sources)
    runtime_ids = tuple(item.source_id for item in source_manifest.sources)
    if runtime_ids != reference_ids or len(runtime_ids) != len(set(runtime_ids)):
        raise H40GuardError(
            H40ReasonCode.SOURCE_UNVERIFIED,
            "runtime source manifest must retain the exact ordered reference inventory",
        )
    for record in source_manifest.sources:
        assert_canonical_source_identity(record, protocol_identity_hash)
    snapshot = current_p1_authority_snapshot()
    for source_id, state in snapshot.per_source_states.items():
        record = source_manifest.get_source(source_id)
        if record.status.value != state:
            raise H40GuardError(
                H40ReasonCode.SOURCE_UNVERIFIED,
                f"runtime source '{source_id}' status does not equal accepted snapshot state",
            )


def materialize_runtime_source_split_authority(
    *,
    source_manifest: H40SourceManifest,
    repo_root: Path | str,
) -> tuple[H40SplitManifest, H40RuntimeSourceSplitAttestation]:
    """Cold-materialize the accepted F01R2 runtime source/split authority."""
    if not isinstance(source_manifest, H40SourceManifest):
        raise TypeError("runtime authority requires H40SourceManifest")
    if not isinstance(repo_root, (Path, str)) or not str(repo_root).strip():
        raise ValueError("runtime authority requires a non-empty repo_root")
    protocol_identity_hash = H40ProtocolIdentity.default().protocol_hash
    _assert_runtime_manifest_inventory(source_manifest, protocol_identity_hash)
    (
        roster,
        registered_count,
        not_testable_count,
        active_source_ids,
        state_entries,
        not_testable_source_ids,
    ) = _runtime_authority_components()
    roster_hash = canonical_sha256([item.to_dict() for item in roster])
    active_evidence: list[H40ActiveSourceEvidenceEntry] = []
    active_timestamps: dict[str, Sequence[str]] = {}
    for source_id in active_source_ids:
        record = source_manifest.get_source(source_id)
        if (
            record.status != H40SourceStatus.VERIFIED
            or record.receipt is None
            or record.receipt.status != H40SourceStatus.VERIFIED
        ):
            raise H40GuardError(
                H40ReasonCode.SOURCE_UNVERIFIED,
                f"active source '{source_id}' requires a typed VERIFIED record and receipt",
            )
        cold_receipt = validate_source_artifact(
            repo_root,
            record,
            expected_product=record.product,
            expected_cadence=record.cadence,
        )
        if cold_receipt.status != H40SourceStatus.VERIFIED:
            raise H40GuardError(
                cold_receipt.reason_code or H40ReasonCode.SOURCE_UNVERIFIED,
                f"active source '{source_id}' failed cold validation",
            )
        if cold_receipt.to_dict() != record.receipt.to_dict():
            raise H40GuardError(
                H40ReasonCode.SOURCE_HASH_MISMATCH,
                f"active source '{source_id}' receipt does not equal cold validation receipt",
            )
        if record.row_count != cold_receipt.timestamp_count:
            raise H40GuardError(
                H40ReasonCode.SOURCE_HASH_MISMATCH,
                f"active source '{source_id}' record row count ({record.row_count}) "
                f"does not equal cold receipt timestamp count ({cold_receipt.timestamp_count})",
            )
        if record.gap_count != cold_receipt.gap_count:
            raise H40GuardError(
                H40ReasonCode.SOURCE_HASH_MISMATCH,
                f"active source '{source_id}' record gap count ({record.gap_count}) "
                f"does not equal cold receipt gap count ({cold_receipt.gap_count})",
            )
        if record.start_utc != cold_receipt.first_timestamp_utc:
            raise H40GuardError(
                H40ReasonCode.SOURCE_HASH_MISMATCH,
                f"active source '{source_id}' record start timestamp UTC ({record.start_utc}) "
                f"does not equal cold receipt first timestamp ({cold_receipt.first_timestamp_utc})",
            )
        if record.end_utc != cold_receipt.last_timestamp_utc:
            raise H40GuardError(
                H40ReasonCode.SOURCE_HASH_MISMATCH,
                f"active source '{source_id}' record end timestamp UTC ({record.end_utc}) "
                f"does not equal cold receipt last timestamp ({cold_receipt.last_timestamp_utc})",
            )
        timestamps = extract_verified_source_timestamps(
            repo_root,
            record,
            expected_product=record.product,
            expected_cadence=record.cadence,
        )
        if timestamps != sorted(set(timestamps)):
            raise H40GuardError(
                H40ReasonCode.INTERVAL_MISMATCH,
                f"active source '{source_id}' timestamps are not unique canonical order",
            )
        membership_hash = hashlib.sha256(",".join(timestamps).encode("utf-8")).hexdigest()
        if (
            len(timestamps) != cold_receipt.timestamp_count
            or membership_hash != cold_receipt.timestamp_membership_hash
        ):
            raise H40GuardError(
                H40ReasonCode.SOURCE_HASH_MISMATCH,
                f"active source '{source_id}' extracted timestamp membership mismatch",
            )
        active_timestamps[source_id] = timestamps
        active_evidence.append(H40ActiveSourceEvidenceEntry(
            source_id=source_id,
            source_record_hash=canonical_sha256(record.to_dict()),
            source_validation_receipt_hash=canonical_sha256(cold_receipt.to_dict()),
            file_sha256=cold_receipt.file_sha256,
            timestamp_membership_hash=cold_receipt.timestamp_membership_hash,
            timestamp_count=cold_receipt.timestamp_count,
        ))
    split_manifest = H40SplitManifest.build_runtime_authoritative(
        protocol_identity_hash=protocol_identity_hash,
        source_manifest_hash=source_manifest.manifest_hash,
        active_source_timestamps=active_timestamps,
    )
    reference_split = H40SplitManifest.build_preregistered_schedule(
        protocol_identity_hash,
        DEFAULT_SOURCE_MANIFEST_HASH,
    )
    split_manifest.assert_static_calendar_matches(reference_split)
    snapshot = current_p1_authority_snapshot()
    attestation = H40RuntimeSourceSplitAttestation(
        accepted_reference_source_manifest_hash=DEFAULT_SOURCE_MANIFEST_HASH,
        accepted_reference_split_manifest_hash=DEFAULT_SPLIT_MANIFEST_HASH,
        protocol_identity_hash=protocol_identity_hash,
        runtime_authority_snapshot_id=snapshot.snapshot_id,
        runtime_authority_snapshot_hash=snapshot.runtime_authority_snapshot_hash,
        source_authority_state_entries=state_entries,
        source_manifest_hash=source_manifest.manifest_hash,
        structural_ledger_hash=EXPECTED_STRUCTURAL_LEDGER_HASH,
        sealed_registered_roster_hash=roster_hash,
        registered_slot_count=registered_count,
        not_testable_slot_count=not_testable_count,
        total_slot_count=168,
        active_required_source_ids=active_source_ids,
        not_testable_source_ids=not_testable_source_ids,
        active_source_evidence=tuple(active_evidence),
        split_manifest_hash=split_manifest.split_hash,
    )
    return split_manifest, attestation


def verify_runtime_source_split_authority(
    *,
    source_manifest: H40SourceManifest,
    split_manifest: H40SplitManifest,
    runtime_attestation: H40RuntimeSourceSplitAttestation,
    repo_root: Path | str,
) -> None:
    """Recompute every F01R2 runtime authority input and require exact equality."""
    if not isinstance(split_manifest, H40SplitManifest):
        raise TypeError("runtime authority requires H40SplitManifest")
    if not isinstance(runtime_attestation, H40RuntimeSourceSplitAttestation):
        raise TypeError("runtime authority requires H40RuntimeSourceSplitAttestation")
    expected_split, expected_attestation = materialize_runtime_source_split_authority(
        source_manifest=source_manifest,
        repo_root=repo_root,
    )
    if split_manifest != expected_split:
        raise H40GuardError(
            H40ReasonCode.SOURCE_HASH_MISMATCH,
            "runtime split does not equal cold-reconstructed active-source split",
        )
    if runtime_attestation != expected_attestation:
        raise H40GuardError(
            H40ReasonCode.SOURCE_HASH_MISMATCH,
            "runtime source/split attestation does not equal recomputed authority",
        )


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
    synthetic_only: bool = field(init=False, compare=False, repr=False)
    _construction_token: InitVar[object | None] = None
    source_manifest_context: InitVar[H40SourceManifest | None] = None
    split_manifest_context: InitVar[H40SplitManifest | None] = None
    runtime_attestation_context: InitVar[H40RuntimeSourceSplitAttestation | None] = None
    repo_root_context: InitVar[Path | str | None] = None
    _source_manifest_context: H40SourceManifest | None = field(
        init=False, compare=False, repr=False
    )
    _split_manifest_context: H40SplitManifest | None = field(
        init=False, compare=False, repr=False
    )
    _runtime_attestation_context: H40RuntimeSourceSplitAttestation | None = field(
        init=False, compare=False, repr=False
    )
    _repo_root_context: Path | None = field(init=False, compare=False, repr=False)

    def __post_init__(
        self,
        _construction_token: object | None,
        source_manifest_context: H40SourceManifest | None,
        split_manifest_context: H40SplitManifest | None,
        runtime_attestation_context: H40RuntimeSourceSplitAttestation | None,
        repo_root_context: Path | str | None,
    ) -> None:
        if _construction_token not in {_PRODUCTION_SEAL_TOKEN, _SYNTHETIC_SEAL_TOKEN}:
            raise TypeError(
                "runtime snapshot seals must be issued by from_verified_authority() "
                "or synthetic_for_tests()"
            )
        object.__setattr__(self, "synthetic_only", _construction_token is _SYNTHETIC_SEAL_TOKEN)
        if _construction_token is _PRODUCTION_SEAL_TOKEN:
            if (
                not isinstance(source_manifest_context, H40SourceManifest)
                or not isinstance(split_manifest_context, H40SplitManifest)
                or not isinstance(runtime_attestation_context, H40RuntimeSourceSplitAttestation)
                or not isinstance(repo_root_context, (Path, str))
                or not str(repo_root_context).strip()
            ):
                raise TypeError("production seal requires complete typed runtime authority context")
            object.__setattr__(self, "_source_manifest_context", source_manifest_context)
            object.__setattr__(self, "_split_manifest_context", split_manifest_context)
            object.__setattr__(self, "_runtime_attestation_context", runtime_attestation_context)
            object.__setattr__(self, "_repo_root_context", Path(repo_root_context))
        else:
            if any(item is not None for item in (
                source_manifest_context,
                split_manifest_context,
                runtime_attestation_context,
                repo_root_context,
            )):
                raise TypeError("synthetic seal cannot carry production authority context")
            object.__setattr__(self, "_source_manifest_context", None)
            object.__setattr__(self, "_split_manifest_context", None)
            object.__setattr__(self, "_runtime_attestation_context", None)
            object.__setattr__(self, "_repo_root_context", None)
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

    @property
    def authority_context_hash(self) -> str:
        return canonical_sha256({
            "authority_kind": "SYNTHETIC_TEST_ONLY" if self.synthetic_only else "PRODUCTION_VERIFIED",
            "schema_id": "H40_RUNTIME_SNAPSHOT_SEAL_CONTEXT_V1",
            **self.to_dict(),
        })

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
        expected, registered_count, not_testable_count, snapshot_hash = (
            _accepted_production_roster()
        )
        if self.runtime_authority_snapshot_hash != snapshot_hash:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "runtime authority snapshot is not the accepted production snapshot",
            )
        if self.roster != expected:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "sealed roster is not the exact complete accepted REGISTERED universe",
            )
        if (
            self.registered_slot_count != registered_count
            or self.not_testable_slot_count != not_testable_count
        ):
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "production roster counts are not the accepted derived counts",
            )
        if not self.synthetic_only:
            if (
                self._source_manifest_context is None
                or self._split_manifest_context is None
                or self._runtime_attestation_context is None
                or self._repo_root_context is None
            ):
                raise H40GuardError(
                    H40ReasonCode.SOURCE_UNVERIFIED,
                    "production seal lost its runtime source/split verification context",
                )
            verify_runtime_source_split_authority(
                source_manifest=self._source_manifest_context,
                split_manifest=self._split_manifest_context,
                runtime_attestation=self._runtime_attestation_context,
                repo_root=self._repo_root_context,
            )
            if (
                self.source_manifest_hash != self._source_manifest_context.manifest_hash
                or self.split_manifest_hash != self._split_manifest_context.split_hash
                or self.split_attestation_hash
                != self._runtime_attestation_context.attestation_hash
            ):
                raise H40GuardError(
                    H40ReasonCode.SOURCE_HASH_MISMATCH,
                    "production seal runtime source/split lineage mismatch",
                )

    @classmethod
    def from_verified_authority(
        cls,
        *,
        source_manifest: H40SourceManifest,
        split_manifest: H40SplitManifest,
        runtime_attestation: H40RuntimeSourceSplitAttestation,
        repo_root: Path | str,
    ) -> H40RuntimeSnapshotSeal:
        if not isinstance(source_manifest, H40SourceManifest):
            raise TypeError("production seal requires H40SourceManifest")
        if not isinstance(split_manifest, H40SplitManifest):
            raise TypeError("production seal requires H40SplitManifest")
        if not isinstance(repo_root, (Path, str)) or str(repo_root).strip() == "":
            raise ValueError("production seal requires a non-empty repo_root")
        if not isinstance(runtime_attestation, H40RuntimeSourceSplitAttestation):
            raise TypeError("production seal requires H40RuntimeSourceSplitAttestation")
        verify_runtime_source_split_authority(
            source_manifest=source_manifest,
            split_manifest=split_manifest,
            runtime_attestation=runtime_attestation,
            repo_root=repo_root,
        )
        registered, registered_count, not_testable_count, snapshot_hash = (
            _accepted_production_roster()
        )
        seal = cls(
            runtime_authority_snapshot_hash=snapshot_hash,
            source_manifest_hash=source_manifest.manifest_hash,
            split_manifest_hash=split_manifest.split_hash,
            split_attestation_hash=runtime_attestation.attestation_hash,
            roster=registered,
            registered_slot_count=registered_count,
            not_testable_slot_count=not_testable_count,
            _construction_token=_PRODUCTION_SEAL_TOKEN,
            source_manifest_context=source_manifest,
            split_manifest_context=split_manifest,
            runtime_attestation_context=runtime_attestation,
            repo_root_context=repo_root,
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
            _construction_token=_SYNTHETIC_SEAL_TOKEN,
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


def _fsync_dir(path: Path, *, fail_closed: bool = False) -> None:
    try:
        fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as err:
        if fail_closed:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"authoritative directory fsync failed for '{path}': {err}",
            ) from err


_TERMINAL_STATES: frozenset[str] = frozenset({"H40_NO_GO", "NOT_TESTABLE"})
_ACCEPTED_LIFECYCLE_STATES: frozenset[str] = frozenset({
    "H40_PREREGISTERED",
    "H40_P1_SCAFFOLDED",
    "H40_DISCOVERY",
    "H40_CANDIDATE_LOCKED",
    "H40_WALK_FORWARD_VALIDATED",
    "H40_CONFIRMATION_READY",
    "H40_CONFIRMATION_EVALUATED_ONCE",
    "H40_NO_GO",
    "NOT_TESTABLE",
})
ACCEPTED_LIFECYCLE_STATES = _ACCEPTED_LIFECYCLE_STATES


@dataclass(frozen=True)
class H40DurableRunHead:
    """Committed durable single run head under H40 F01R3 (ASTRA-B-02/H-01)."""

    head_predecessor_receipt_hash: str | None
    head_receipt_hash: str
    head_state: str
    run_authority_id: str
    terminal: bool
    transition_sequence: int
    schema_id: str = "H40_DURABLE_RUN_HEAD_V1"

    _KEYS: ClassVar[frozenset[str]] = frozenset({
        "head_predecessor_receipt_hash",
        "head_receipt_hash",
        "head_state",
        "run_authority_id",
        "schema_id",
        "terminal",
        "transition_sequence",
    })

    def __post_init__(self) -> None:
        if self.schema_id != "H40_DURABLE_RUN_HEAD_V1":
            raise ValueError("durable run head schema mismatch")
        _require_sha256(self.run_authority_id, "run_authority_id")
        _require_sha256(self.head_receipt_hash, "head_receipt_hash")
        _require_text(self.head_state, "head_state")
        if self.head_predecessor_receipt_hash is not None:
            _require_sha256(self.head_predecessor_receipt_hash, "head_predecessor_receipt_hash")
        if not isinstance(self.transition_sequence, int) or isinstance(self.transition_sequence, bool):
            raise TypeError("transition_sequence must be an integer")
        if self.transition_sequence < 0:
            raise ValueError("transition_sequence must be non-negative")
        if not isinstance(self.terminal, bool):
            raise TypeError("terminal must be a boolean")

    @property
    def head_hash(self) -> str:
        return canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "head_predecessor_receipt_hash": self.head_predecessor_receipt_hash,
            "head_receipt_hash": self.head_receipt_hash,
            "head_state": self.head_state,
            "run_authority_id": self.run_authority_id,
            "schema_id": self.schema_id,
            "terminal": self.terminal,
            "transition_sequence": self.transition_sequence,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40DurableRunHead:
        _require_exact_keys(data, cls._KEYS, cls.__name__)
        pred = data["head_predecessor_receipt_hash"]
        term = data["terminal"]
        if not isinstance(term, bool):
            raise TypeError("terminal must be a boolean")
        seq = data["transition_sequence"]
        if not isinstance(seq, int) or isinstance(seq, bool):
            raise TypeError("transition_sequence must be an integer")
        return cls(
            head_predecessor_receipt_hash=str(pred) if pred is not None else None,
            head_receipt_hash=str(data["head_receipt_hash"]),
            head_state=str(data["head_state"]),
            run_authority_id=str(data["run_authority_id"]),
            schema_id=str(data["schema_id"]),
            terminal=term,
            transition_sequence=seq,
        )


@dataclass(frozen=True)
class H40P3ControllerAuthority:
    schema_id: str = "H40_P3_CONTROLLER_AUTHORITY_V1"
    authorization_scope: str = "H40_P3_DISCOVERY_V1"
    controller_acceptance_artifact_path: str = (
        "reviews/v0.5/V0.5.1_H40_PRE_DISCOVERY_REPAIR_CONTRACT_CONTROLLER_ACCEPTANCE.md"
    )
    controller_acceptance_commit_sha: str = "2229d44c5cc9b88ba515d0b2931d20f05936c7e8"
    protocol_authority_hash: str = EXPECTED_PROTOCOL_AUTHORITY_HASH
    scientific_semantic_root_hash: str = EXPECTED_SEMANTIC_ROOT_HASH
    structural_ledger_hash: str = EXPECTED_STRUCTURAL_LEDGER_HASH
    lifecycle_semantic_root_hash: str = EXPECTED_LIFECYCLE_SEMANTIC_ROOT_HASH
    lifecycle_governance_authority_hash: str = EXPECTED_LIFECYCLE_GOVERNANCE_AUTHORITY_HASH
    lifecycle_implementation_authority_hash: str = ""
    discovery_provenance_contract_hash: str = DISCOVERY_PROVENANCE_CONTRACT_HASH
    discovery_selection_correction_contract_hash: str = (
        DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH
    )
    permitted_partitions: tuple[str, ...] = ("WF1_TRAIN", "WF1_CALIBRATION")
    transition_source_state: str = "H40_P1_SCAFFOLDED"
    transition_target_state: str = "H40_DISCOVERY"
    execution_disabled: bool = True

    _KEYS: ClassVar[frozenset[str]] = frozenset({
        "schema_id",
        "authorization_scope",
        "controller_acceptance_artifact_path",
        "controller_acceptance_commit_sha",
        "protocol_authority_hash",
        "scientific_semantic_root_hash",
        "structural_ledger_hash",
        "lifecycle_semantic_root_hash",
        "lifecycle_governance_authority_hash",
        "lifecycle_implementation_authority_hash",
        "discovery_provenance_contract_hash",
        "discovery_selection_correction_contract_hash",
        "permitted_partitions",
        "transition_source_state",
        "transition_target_state",
        "execution_disabled",
    })

    def __post_init__(self) -> None:
        if self.schema_id != "H40_P3_CONTROLLER_AUTHORITY_V1":
            raise ValueError("controller authority schema mismatch")
        if self.authorization_scope != "H40_P3_DISCOVERY_V1":
            raise ValueError("controller authority authorization_scope mismatch")
        _require_text(
            self.controller_acceptance_artifact_path,
            "controller_acceptance_artifact_path",
        )
        _require_commit(
            self.controller_acceptance_commit_sha,
            "controller_acceptance_commit_sha",
        )
        _require_sha256(self.protocol_authority_hash, "protocol_authority_hash")
        _require_sha256(self.scientific_semantic_root_hash, "scientific_semantic_root_hash")
        _require_sha256(self.structural_ledger_hash, "structural_ledger_hash")
        _require_sha256(self.lifecycle_semantic_root_hash, "lifecycle_semantic_root_hash")
        _require_sha256(self.lifecycle_governance_authority_hash, "lifecycle_governance_authority_hash")
        _require_sha256(self.lifecycle_implementation_authority_hash, "lifecycle_implementation_authority_hash")
        _require_sha256(self.discovery_provenance_contract_hash, "discovery_provenance_contract_hash")
        _require_sha256(self.discovery_selection_correction_contract_hash, "discovery_selection_correction_contract_hash")

        if self.protocol_authority_hash != EXPECTED_PROTOCOL_AUTHORITY_HASH:
            raise ValueError("controller authority protocol_authority_hash mismatch")
        if self.scientific_semantic_root_hash != EXPECTED_SEMANTIC_ROOT_HASH:
            raise ValueError("controller authority scientific_semantic_root_hash mismatch")
        if self.structural_ledger_hash != EXPECTED_STRUCTURAL_LEDGER_HASH:
            raise ValueError("controller authority structural_ledger_hash mismatch")
        if self.lifecycle_semantic_root_hash != EXPECTED_LIFECYCLE_SEMANTIC_ROOT_HASH:
            raise ValueError("controller authority lifecycle_semantic_root_hash mismatch")
        if self.lifecycle_governance_authority_hash != EXPECTED_LIFECYCLE_GOVERNANCE_AUTHORITY_HASH:
            raise ValueError("controller authority lifecycle_governance_authority_hash mismatch")
        if self.discovery_provenance_contract_hash != DISCOVERY_PROVENANCE_CONTRACT_HASH:
            raise ValueError("controller authority discovery_provenance_contract_hash mismatch")
        if self.discovery_selection_correction_contract_hash != DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH:
            raise ValueError("controller authority discovery_selection_correction_contract_hash mismatch")

        partitions = tuple(self.permitted_partitions)
        if partitions != ("WF1_TRAIN", "WF1_CALIBRATION"):
            raise ValueError("controller authority permitted_partitions mismatch")
        object.__setattr__(self, "permitted_partitions", partitions)

        if self.transition_source_state != "H40_P1_SCAFFOLDED":
            raise ValueError("controller authority transition_source_state mismatch")
        if self.transition_target_state != "H40_DISCOVERY":
            raise ValueError("controller authority transition_target_state mismatch")
        if self.execution_disabled is not True or type(self.execution_disabled) is not bool:
            raise ValueError("controller authority execution_disabled must be boolean true")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "authorization_scope": self.authorization_scope,
            "controller_acceptance_artifact_path": self.controller_acceptance_artifact_path,
            "controller_acceptance_commit_sha": self.controller_acceptance_commit_sha,
            "protocol_authority_hash": self.protocol_authority_hash,
            "scientific_semantic_root_hash": self.scientific_semantic_root_hash,
            "structural_ledger_hash": self.structural_ledger_hash,
            "lifecycle_semantic_root_hash": self.lifecycle_semantic_root_hash,
            "lifecycle_governance_authority_hash": self.lifecycle_governance_authority_hash,
            "lifecycle_implementation_authority_hash": self.lifecycle_implementation_authority_hash,
            "discovery_provenance_contract_hash": self.discovery_provenance_contract_hash,
            "discovery_selection_correction_contract_hash": self.discovery_selection_correction_contract_hash,
            "permitted_partitions": list(self.permitted_partitions),
            "transition_source_state": self.transition_source_state,
            "transition_target_state": self.transition_target_state,
            "execution_disabled": self.execution_disabled,
        }

    @property
    def controller_authority_hash(self) -> str:
        return canonical_sha256(self.to_dict())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40P3ControllerAuthority:
        _require_exact_keys(data, cls._KEYS, cls.__name__)
        _require_string_fields(
            data,
            cls._KEYS - {"permitted_partitions", "execution_disabled"},
            cls.__name__,
        )
        if not isinstance(data["permitted_partitions"], (list, tuple)):
            raise TypeError(f"{cls.__name__}.permitted_partitions must be a sequence")
        if not all(isinstance(p, str) for p in data["permitted_partitions"]):
            raise TypeError(f"{cls.__name__}.permitted_partitions items must be strings")
        if not isinstance(data["execution_disabled"], bool):
            raise TypeError(f"{cls.__name__}.execution_disabled must be boolean")
        kwargs = dict(data)
        kwargs["permitted_partitions"] = tuple(data["permitted_partitions"])
        return cls(**kwargs)


def _synthesize_controller_authority(
    implementation_authority: H40LifecycleImplementationAuthority,
    *,
    artifact_path: str = "reviews/v0.5/V0.5.1_H40_PRE_DISCOVERY_REPAIR_CONTRACT_CONTROLLER_ACCEPTANCE.md",
    commit_sha: str = "2229d44c5cc9b88ba515d0b2931d20f05936c7e8",
) -> H40P3ControllerAuthority:
    return H40P3ControllerAuthority(
        schema_id="H40_P3_CONTROLLER_AUTHORITY_V1",
        authorization_scope="H40_P3_DISCOVERY_V1",
        controller_acceptance_artifact_path=artifact_path,
        controller_acceptance_commit_sha=commit_sha,
        protocol_authority_hash=EXPECTED_PROTOCOL_AUTHORITY_HASH,
        scientific_semantic_root_hash=EXPECTED_SEMANTIC_ROOT_HASH,
        structural_ledger_hash=EXPECTED_STRUCTURAL_LEDGER_HASH,
        lifecycle_semantic_root_hash=EXPECTED_LIFECYCLE_SEMANTIC_ROOT_HASH,
        lifecycle_governance_authority_hash=EXPECTED_LIFECYCLE_GOVERNANCE_AUTHORITY_HASH,
        lifecycle_implementation_authority_hash=implementation_authority.lifecycle_implementation_authority_hash,
        discovery_provenance_contract_hash=DISCOVERY_PROVENANCE_CONTRACT_HASH,
        discovery_selection_correction_contract_hash=DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH,
        permitted_partitions=("WF1_TRAIN", "WF1_CALIBRATION"),
        transition_source_state="H40_P1_SCAFFOLDED",
        transition_target_state="H40_DISCOVERY",
        execution_disabled=True,
    )


@dataclass(frozen=True)
class H40DiscoveryRunGrant:
    schema_id: str
    authorized_at_utc: str
    controller_authority_hash: str
    protocol_authority_hash: str
    scientific_semantic_root_hash: str
    structural_ledger_hash: str
    lifecycle_governance_authority_hash: str
    lifecycle_implementation_authority_hash: str
    discovery_provenance_contract_hash: str
    run_authority_id: str
    materialized_run_authority_hash: str
    runtime_authority_snapshot_hash: str
    source_manifest_hash: str
    split_manifest_hash: str
    split_attestation_hash: str
    sealed_registered_roster_hash: str
    permitted_partitions: tuple[str, ...] = ("WF1_TRAIN", "WF1_CALIBRATION")
    execution_disabled: bool = True

    _KEYS: ClassVar[frozenset[str]] = frozenset({
        "schema_id",
        "authorized_at_utc",
        "controller_authority_hash",
        "protocol_authority_hash",
        "scientific_semantic_root_hash",
        "structural_ledger_hash",
        "lifecycle_governance_authority_hash",
        "lifecycle_implementation_authority_hash",
        "discovery_provenance_contract_hash",
        "run_authority_id",
        "materialized_run_authority_hash",
        "runtime_authority_snapshot_hash",
        "source_manifest_hash",
        "split_manifest_hash",
        "split_attestation_hash",
        "sealed_registered_roster_hash",
        "permitted_partitions",
        "execution_disabled",
    })

    def __post_init__(self) -> None:
        if self.schema_id != "H40_DISCOVERY_RUN_GRANT_V1":
            raise ValueError("discovery run grant schema mismatch")
        normalize_audit_timestamp(self.authorized_at_utc)
        for name in (
            "controller_authority_hash",
            "protocol_authority_hash",
            "scientific_semantic_root_hash",
            "structural_ledger_hash",
            "lifecycle_governance_authority_hash",
            "lifecycle_implementation_authority_hash",
            "discovery_provenance_contract_hash",
            "run_authority_id",
            "materialized_run_authority_hash",
            "runtime_authority_snapshot_hash",
            "source_manifest_hash",
            "split_manifest_hash",
            "split_attestation_hash",
            "sealed_registered_roster_hash",
        ):
            _require_sha256(getattr(self, name), name)

        if self.protocol_authority_hash != EXPECTED_PROTOCOL_AUTHORITY_HASH:
            raise ValueError("run grant protocol_authority_hash mismatch")
        if self.scientific_semantic_root_hash != EXPECTED_SEMANTIC_ROOT_HASH:
            raise ValueError("run grant scientific_semantic_root_hash mismatch")
        if self.structural_ledger_hash != EXPECTED_STRUCTURAL_LEDGER_HASH:
            raise ValueError("run grant structural_ledger_hash mismatch")
        if self.lifecycle_governance_authority_hash != EXPECTED_LIFECYCLE_GOVERNANCE_AUTHORITY_HASH:
            raise ValueError("run grant lifecycle_governance_authority_hash mismatch")
        if self.discovery_provenance_contract_hash != DISCOVERY_PROVENANCE_CONTRACT_HASH:
            raise ValueError("run grant discovery_provenance_contract_hash mismatch")

        partitions = tuple(self.permitted_partitions)
        if partitions != ("WF1_TRAIN", "WF1_CALIBRATION"):
            raise ValueError("run grant permitted_partitions mismatch")
        object.__setattr__(self, "permitted_partitions", partitions)

        if self.execution_disabled is not True or type(self.execution_disabled) is not bool:
            raise ValueError("run grant execution_disabled must be boolean true")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "authorized_at_utc": self.authorized_at_utc,
            "controller_authority_hash": self.controller_authority_hash,
            "protocol_authority_hash": self.protocol_authority_hash,
            "scientific_semantic_root_hash": self.scientific_semantic_root_hash,
            "structural_ledger_hash": self.structural_ledger_hash,
            "lifecycle_governance_authority_hash": self.lifecycle_governance_authority_hash,
            "lifecycle_implementation_authority_hash": self.lifecycle_implementation_authority_hash,
            "discovery_provenance_contract_hash": self.discovery_provenance_contract_hash,
            "run_authority_id": self.run_authority_id,
            "materialized_run_authority_hash": self.materialized_run_authority_hash,
            "runtime_authority_snapshot_hash": self.runtime_authority_snapshot_hash,
            "source_manifest_hash": self.source_manifest_hash,
            "split_manifest_hash": self.split_manifest_hash,
            "split_attestation_hash": self.split_attestation_hash,
            "sealed_registered_roster_hash": self.sealed_registered_roster_hash,
            "permitted_partitions": list(self.permitted_partitions),
            "execution_disabled": self.execution_disabled,
        }

    @property
    def discovery_run_grant_hash(self) -> str:
        return canonical_sha256(self.to_dict())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40DiscoveryRunGrant:
        _require_exact_keys(data, cls._KEYS, cls.__name__)
        _require_string_fields(
            data,
            cls._KEYS - {"permitted_partitions", "execution_disabled"},
            cls.__name__,
        )
        if not isinstance(data["permitted_partitions"], (list, tuple)):
            raise TypeError(f"{cls.__name__}.permitted_partitions must be a sequence")
        if not all(isinstance(p, str) for p in data["permitted_partitions"]):
            raise TypeError(f"{cls.__name__}.permitted_partitions items must be strings")
        if not isinstance(data["execution_disabled"], bool):
            raise TypeError(f"{cls.__name__}.execution_disabled must be boolean")
        kwargs = dict(data)
        kwargs["permitted_partitions"] = tuple(data["permitted_partitions"])
        return cls(**kwargs)

    @classmethod
    def from_controller_and_run(
        cls,
        *,
        controller_authority: H40P3ControllerAuthority,
        run_authority: H40RunAuthority,
        seal: H40RuntimeSnapshotSeal,
        authorized_at_utc: str,
    ) -> H40DiscoveryRunGrant:
        if not isinstance(controller_authority, H40P3ControllerAuthority):
            raise TypeError("controller_authority must be H40P3ControllerAuthority")
        if not isinstance(run_authority, H40RunAuthority):
            raise TypeError("run_authority must be H40RunAuthority")
        if not isinstance(seal, H40RuntimeSnapshotSeal):
            raise TypeError("seal must be H40RuntimeSnapshotSeal")

        if (
            controller_authority.lifecycle_implementation_authority_hash
            != run_authority.lifecycle_implementation_authority_hash
        ):
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "controller authority implementation hash mismatch against run authority",
            )
        expected_run = H40RunAuthority.from_seal(
            seal,
            controller_authority.lifecycle_implementation_authority_hash,
        )
        if run_authority != expected_run:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "run authority does not match seal and controller implementation hash",
            )
        if run_authority.source_manifest_hash != seal.source_manifest_hash:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "source manifest hash mismatch between run authority and seal",
            )
        if run_authority.split_manifest_hash != seal.split_manifest_hash:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "split manifest hash mismatch between run authority and seal",
            )
        if run_authority.split_attestation_hash != seal.split_attestation_hash:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "split attestation hash mismatch between run authority and seal",
            )
        if run_authority.sealed_registered_roster_hash != seal.sealed_registered_roster_hash:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "roster hash mismatch between run authority and seal",
            )

        return cls(
            schema_id="H40_DISCOVERY_RUN_GRANT_V1",
            authorized_at_utc=normalize_audit_timestamp(authorized_at_utc),
            controller_authority_hash=controller_authority.controller_authority_hash,
            protocol_authority_hash=controller_authority.protocol_authority_hash,
            scientific_semantic_root_hash=controller_authority.scientific_semantic_root_hash,
            structural_ledger_hash=controller_authority.structural_ledger_hash,
            lifecycle_governance_authority_hash=controller_authority.lifecycle_governance_authority_hash,
            lifecycle_implementation_authority_hash=controller_authority.lifecycle_implementation_authority_hash,
            discovery_provenance_contract_hash=controller_authority.discovery_provenance_contract_hash,
            run_authority_id=run_authority.run_authority_id,
            materialized_run_authority_hash=run_authority.materialized_run_authority_hash,
            runtime_authority_snapshot_hash=seal.runtime_authority_snapshot_hash,
            source_manifest_hash=run_authority.source_manifest_hash,
            split_manifest_hash=run_authority.split_manifest_hash,
            split_attestation_hash=run_authority.split_attestation_hash,
            sealed_registered_roster_hash=run_authority.sealed_registered_roster_hash,
            permitted_partitions=("WF1_TRAIN", "WF1_CALIBRATION"),
            execution_disabled=True,
        )


_SYNTHETIC_CONTROLLER_REGISTRY: dict[str, H40P3ControllerAuthority] = {}
_SYNTHETIC_GRANT_REGISTRY: dict[str, H40DiscoveryRunGrant] = {}


@dataclass(frozen=True)
class H40DiscoveryAuthorizationReceiptV2:
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
    def from_dict(cls, data: Mapping[str, Any]) -> H40DiscoveryAuthorizationReceiptV2:
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


@dataclass(frozen=True)
class H40DiscoveryAuthorizationReceipt:
    authorized_at_utc: str
    controller_authority_hash: str
    discovery_run_grant_hash: str
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
    receipt_schema_id: str = "H40_RECEIPT_DISCOVERY_AUTH_V3"

    _KEYS: ClassVar[frozenset[str]] = frozenset({
        "authorized_at_utc",
        "controller_authority_hash",
        "discovery_run_grant_hash",
        "discovery_selection_correction_contract_hash",
        "execution_disabled",
        "lifecycle_governance_authority_hash",
        "lifecycle_implementation_authority_hash",
        "materialized_run_authority_hash",
        "not_testable_slot_count",
        "protocol_authority_hash",
        "receipt_schema_id",
        "registered_slot_count",
        "run_authority_id",
        "sealed_registered_roster_hash",
        "semantic_root_hash",
        "source_manifest_hash",
        "split_attestation_hash",
        "split_manifest_hash",
        "structural_ledger_hash",
        "total_slot_count",
        "upstream_receipt_hash",
    })

    def __post_init__(self) -> None:
        if self.receipt_schema_id != "H40_RECEIPT_DISCOVERY_AUTH_V3":
            raise ValueError("discovery receipt schema mismatch")
        normalize_audit_timestamp(self.authorized_at_utc)
        if self.execution_disabled is not True or self.upstream_receipt_hash is not None:
            raise ValueError("discovery receipt must bind execution_disabled=true and null upstream")
        for name in self._KEYS - {
            "authorized_at_utc",
            "execution_disabled",
            "not_testable_slot_count",
            "receipt_schema_id",
            "registered_slot_count",
            "total_slot_count",
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
                "execution_disabled",
                "not_testable_slot_count",
                "registered_slot_count",
                "total_slot_count",
                "upstream_receipt_hash",
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
        if "CONFIRMATION" in self.fold_id or not self.fold_id.startswith("WF"):
            raise ValueError(f"invalid fold_id '{self.fold_id}': cannot enter WF universe")
        if "CONFIRMATION" in self.partition_id:
            raise ValueError(f"invalid partition_id '{self.partition_id}': cannot enter WF universe")

    @property
    def fold_identity_hash(self) -> str:
        return canonical_sha256({
            "fold_id": self.fold_id,
            "partition_id": self.partition_id,
            "split_definition_hash": self.split_definition_hash,
        })

    def to_dict(self) -> dict[str, str]:
        return {
            "fold_id": self.fold_id,
            "partition_id": self.partition_id,
            "split_definition_hash": self.split_definition_hash,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40ExpectedWFFold:
        keys = frozenset({"fold_id", "partition_id", "split_definition_hash"})
        _require_exact_keys(data, keys, cls.__name__)
        _require_string_fields(data, keys, cls.__name__)
        return cls(
            fold_id=str(data["fold_id"]),
            partition_id=str(data["partition_id"]),
            split_definition_hash=str(data["split_definition_hash"]),
        )


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
        if len(self.folds) != 4:
            raise ValueError("must contain exactly 4 WF validation folds")
        expected_folds = ("WF1", "WF2", "WF3", "WF4")
        expected_partitions = (
            "WF1_VALIDATION",
            "WF2_VALIDATION",
            "WF3_VALIDATION",
            "WF4_VALIDATION",
        )
        if tuple(fold.fold_id for fold in self.folds) != expected_folds:
            raise ValueError("must be strictly sorted and contain exactly WF1..WF4")
        if tuple(fold.partition_id for fold in self.folds) != expected_partitions:
            raise ValueError("must be strictly sorted and contain exactly WF1_VALIDATION..WF4_VALIDATION")
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
            raise ValueError("accepted_validation_contract_hashes cannot be empty")

    @property
    def fold_names(self) -> tuple[str, ...]:
        return tuple(fold.fold_id for fold in self.folds)

    @property
    def validation_partition_names(self) -> tuple[str, ...]:
        return tuple(fold.partition_id for fold in self.folds)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted_validation_contract_hashes": dict(
                self.accepted_validation_contract_hashes
            ),
            "folds": [fold.to_dict() for fold in self.folds],
            "schema_id": "H40_EXPECTED_SPLIT_AUTHORITY_CONTEXT_V1",
            "split_attestation_hash": self.split_attestation_hash,
            "split_manifest_hash": self.split_manifest_hash,
        }

    @property
    def authority_context_hash(self) -> str:
        return canonical_sha256(self.to_dict())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40ExpectedSplitAuthority:
        keys = frozenset({
            "accepted_validation_contract_hashes",
            "folds",
            "schema_id",
            "split_attestation_hash",
            "split_manifest_hash",
        })
        _require_exact_keys(data, keys, cls.__name__)
        if data["schema_id"] != "H40_EXPECTED_SPLIT_AUTHORITY_CONTEXT_V1":
            raise ValueError("expected split authority context schema mismatch")
        folds = data["folds"]
        contracts = data["accepted_validation_contract_hashes"]
        if not isinstance(folds, list) or not all(isinstance(item, Mapping) for item in folds):
            raise TypeError("folds must be an array of objects")
        if not isinstance(contracts, Mapping):
            raise TypeError("accepted_validation_contract_hashes must be an object")
        return cls(
            split_manifest_hash=str(data["split_manifest_hash"]),
            split_attestation_hash=str(data["split_attestation_hash"]),
            folds=tuple(H40ExpectedWFFold.from_dict(item) for item in folds),
            accepted_validation_contract_hashes={
                str(key): str(value) for key, value in contracts.items()
            },
        )


def derive_expected_wf_authority(
    candidate_authority: VerifiedLifecycleAuthorization | None = None,
    *,
    seal: H40RuntimeSnapshotSeal | None = None,
    split_manifest: H40SplitManifest | None = None,
    accepted_validation_contract_hashes: Mapping[str, str] | None = None,
) -> H40ExpectedSplitAuthority:
    """Deterministically derive the expected production WF authority.

    Under H40 F01R3 (ASTRA-B-01), production expected WF authority must be
    internally derived from the exact seal-bound runtime split manifest.
    The authoritative universe contains exactly four folds: WF1..WF4,
    mapped to WF1_VALIDATION..WF4_VALIDATION.  Confirmation partitions must
    never enter the WF fold universe.
    """
    if candidate_authority is not None:
        if not isinstance(candidate_authority, VerifiedLifecycleAuthorization):
            raise TypeError("candidate_authority must be VerifiedLifecycleAuthorization")
        if candidate_authority.target_state != "H40_CANDIDATE_LOCKED":
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "expected WF authority can only be derived from a locked candidate",
            )
        candidate_seal = candidate_authority.context.get("seal")
        if not isinstance(candidate_seal, H40RuntimeSnapshotSeal):
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "candidate authority lacks bound runtime snapshot seal",
            )
        if seal is not None and seal != candidate_seal:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "supplied seal does not match candidate authority seal",
            )
        seal = candidate_seal
    elif seal is None:
        raise TypeError("either candidate_authority or seal must be provided")

    if not isinstance(seal, H40RuntimeSnapshotSeal):
        raise TypeError("seal must be H40RuntimeSnapshotSeal")

    is_synthetic = seal.synthetic_only or (
        candidate_authority is not None and candidate_authority.synthetic_only
    )

    if not is_synthetic:
        # Production mode
        if split_manifest is not None and split_manifest != seal._split_manifest_context:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "cannot override production seal split manifest",
            )
        resolved_split_manifest = seal._split_manifest_context
        if resolved_split_manifest is None:
            raise H40GuardError(
                H40ReasonCode.SOURCE_UNVERIFIED,
                "production seal missing bound runtime split manifest context",
            )
        if accepted_validation_contract_hashes is not None:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "cannot inject caller validation contracts into production WF derivation",
            )
        # Production P3 statistical validation contracts are not yet materialized
        raise H40GuardError(
            H40ReasonCode.NOT_TESTABLE,
            "accepted P3 validation contracts are not yet materialized in production",
        )
    else:
        # Synthetic test mode
        resolved_split_manifest = (
            split_manifest
            or seal._split_manifest_context
            or (candidate_authority.context.get("split_manifest") if candidate_authority else None)
        )
        contracts = (
            accepted_validation_contract_hashes
            or (
                candidate_authority.context.get("accepted_validation_contract_hashes")
                if candidate_authority
                else None
            )
            or {"WF_GATE_SET_V1": hashlib.sha256(b"wf-gate-set").hexdigest()}
        )

    if resolved_split_manifest is None:
        derived_folds = tuple(
            H40ExpectedWFFold(
                fold_id=f"WF{i}",
                partition_id=f"WF{i}_VALIDATION",
                split_definition_hash=hashlib.sha256(f"fold-{i}".encode()).hexdigest(),
            )
            for i in range(1, 5)
        )
        return H40ExpectedSplitAuthority(
            split_manifest_hash=seal.split_manifest_hash,
            split_attestation_hash=seal.split_attestation_hash,
            folds=derived_folds,
            accepted_validation_contract_hashes=contracts,
        )

    if resolved_split_manifest.split_hash != seal.split_manifest_hash:
        raise H40GuardError(
            H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
            "split manifest hash mismatch against sealed runtime authority",
        )

    # Filter strictly for partition_type == VALIDATION
    wf_partitions = [
        p
        for p in resolved_split_manifest.partitions
        if p.partition_type == H40PartitionType.VALIDATION
    ]

    # Explicitly reject confirmation partitions
    for p in resolved_split_manifest.partitions:
        if (
            p.fold == "CONFIRMATION"
            or "CONFIRMATION" in p.partition_id
            or p.partition_type.value.startswith("CONFIRMATION")
        ) and p in wf_partitions:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "Confirmation partition cannot enter WF fold universe",
            )

    if len(wf_partitions) != 4:
        raise H40GuardError(
            H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
            f"exact WF fold universe must contain 4 validation folds, got {len(wf_partitions)}",
        )

    expected_folds = ("WF1", "WF2", "WF3", "WF4")
    expected_partitions = (
        "WF1_VALIDATION",
        "WF2_VALIDATION",
        "WF3_VALIDATION",
        "WF4_VALIDATION",
    )
    if tuple(p.fold for p in wf_partitions) != expected_folds:
        raise H40GuardError(
            H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
            "exact WF folds must be WF1, WF2, WF3, WF4 in authoritative split order",
        )
    if tuple(p.partition_id for p in wf_partitions) != expected_partitions:
        raise H40GuardError(
            H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
            "exact WF partitions must be WF1_VALIDATION..WF4_VALIDATION in order",
        )

    derived_folds = tuple(
        H40ExpectedWFFold(
            fold_id=p.fold,
            partition_id=p.partition_id,
            split_definition_hash=canonical_sha256(p.to_dict()),
        )
        for p in wf_partitions
    )
    return H40ExpectedSplitAuthority(
        split_manifest_hash=seal.split_manifest_hash,
        split_attestation_hash=seal.split_attestation_hash,
        folds=derived_folds,
        accepted_validation_contract_hashes=contracts,
    )


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
class H40CandidateVerification:
    hard_gates_passed: bool
    adjusted_lcb_net_expectancy: Decimal | None
    adjusted_lcb_precision: Decimal | None
    scientific_unavailable: bool = False


@runtime_checkable
class H40LifecycleEvidenceVerifier(Protocol):
    """Typed seam for a separately accepted lifecycle scientific verifier."""

    @property
    def synthetic_only(self) -> bool: ...

    def verify_discovery_manifest(
        self,
        evidence: H40DiscoveryResultEvidence,
        entries: Sequence[H40CandidateResultEntry],
    ) -> None: ...

    def verify_candidate(
        self,
        entry: H40CandidateResultEntry,
        *,
        run_authority_id: str,
        correction_manifest_hash: str,
    ) -> H40CandidateVerification: ...

    def verify_wf_fold(
        self,
        entry: H40WFFoldResultEntry,
        *,
        evidence: H40WFValidationResultEvidence,
    ) -> bool: ...


class H40SyntheticEvidenceVerifier:
    """Explicitly non-authoritative content verifier for synthetic governance tests.

    Production/default lifecycle authority never constructs this verifier and
    remains unable to authorize Discovery until an independent implementation
    authority is published.
    """

    synthetic_only = True

    def __init__(self, payloads: Mapping[str, Mapping[str, Any]]) -> None:
        copied: dict[str, Mapping[str, Any]] = {}
        for digest, payload in payloads.items():
            _require_sha256(digest, "synthetic evidence digest")
            detached = json.loads(canonical_json(payload))
            if canonical_sha256(detached) != digest:
                raise ValueError("synthetic evidence key does not match canonical content hash")
            copied[digest] = MappingProxyType(detached)
        self._payloads: dict[str, Mapping[str, Any]] = copied
        self._verification_count = 0

    @property
    def verification_count(self) -> int:
        return self._verification_count

    def export_payloads_for_tests(self) -> dict[str, dict[str, Any]]:
        return {
            digest: cast(dict[str, Any], json.loads(canonical_json(payload)))
            for digest, payload in self._payloads.items()
        }

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
        self._verification_count += 1
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
    ) -> H40CandidateVerification:
        self._verification_count += 1
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
        return H40CandidateVerification(
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
        self._verification_count += 1
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
    | H40DiscoveryAuthorizationReceiptV2
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
            H40DiscoveryAuthorizationReceiptV2: ("H40_P1_SCAFFOLDED", "H40_DISCOVERY"),
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
        controller_authority: H40P3ControllerAuthority | None = None,
        accepted_controller_authority_hash: str | None = None,
        discovery_run_grant: H40DiscoveryRunGrant | None = None,
        evidence_verifier: H40LifecycleEvidenceVerifier | None = None,
        synthetic_test_mode: bool = False,
        _construction_token: object = None,
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
        if accepted_controller_authority_hash is not None:
            _require_sha256(
                accepted_controller_authority_hash,
                "accepted_controller_authority_hash",
            )
        if controller_authority is not None:
            computed_ctrl = controller_authority.controller_authority_hash
            if computed_ctrl != accepted_controller_authority_hash:
                raise ValueError("controller authority object/hash mismatch")
        if evidence_verifier is not None and not isinstance(
            evidence_verifier,
            H40LifecycleEvidenceVerifier,
        ):
            raise TypeError("evidence_verifier must implement H40LifecycleEvidenceVerifier")
        if synthetic_test_mode:
            if implementation_authority is None or not isinstance(
                evidence_verifier,
                H40SyntheticEvidenceVerifier,
            ):
                raise ValueError(
                    "synthetic test service requires authority and H40SyntheticEvidenceVerifier"
                )
        elif evidence_verifier is not None and evidence_verifier.synthetic_only:
            raise ValueError("production service cannot use a synthetic/test-only verifier")

        self._implementation_authority = implementation_authority
        self._accepted_implementation_authority_hash = accepted_implementation_authority_hash
        self._controller_authority = controller_authority
        self._accepted_controller_authority_hash = accepted_controller_authority_hash
        self._discovery_run_grant = discovery_run_grant
        self._evidence_verifier = evidence_verifier
        self._synthetic_test_mode = synthetic_test_mode
        self._issuer_id = object()

    @classmethod
    def production(
        cls,
        implementation_authority: H40LifecycleImplementationAuthority | None = None,
        controller_authority: H40P3ControllerAuthority | None = None,
        discovery_run_grant: H40DiscoveryRunGrant | None = None,
        evidence_verifier: H40LifecycleEvidenceVerifier | None = None,
    ) -> H40LifecycleAuthorityService:
        if (
            controller_authority is None
            and ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH is not None
            and ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH in _SYNTHETIC_CONTROLLER_REGISTRY
        ):
            controller_authority = _SYNTHETIC_CONTROLLER_REGISTRY[
                ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH
            ]
        return cls(
            implementation_authority=implementation_authority,
            accepted_implementation_authority_hash=ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH,
            controller_authority=controller_authority,
            accepted_controller_authority_hash=ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH,
            discovery_run_grant=discovery_run_grant,
            evidence_verifier=evidence_verifier,
            synthetic_test_mode=False,
            _construction_token=_VERIFIED_AUTHORITY_TOKEN,
        )

    @property
    def synthetic_test_mode(self) -> bool:
        return self._synthetic_test_mode

    @property
    def implementation_authority(self) -> H40LifecycleImplementationAuthority | None:
        return self._implementation_authority

    @property
    def controller_authority(self) -> H40P3ControllerAuthority | None:
        return self._controller_authority

    @property
    def accepted_implementation_authority_hash(self) -> str | None:
        return self._accepted_implementation_authority_hash

    @property
    def accepted_controller_authority_hash(self) -> str | None:
        return self._accepted_controller_authority_hash

    @property
    def current_implementation_authority_hash(self) -> str | None:
        return self._accepted_implementation_authority_hash

    @property
    def current_controller_authority_hash(self) -> str | None:
        return self._accepted_controller_authority_hash

    def _assert_current_anchors(self, *, require_controller: bool = False) -> None:
        if self._synthetic_test_mode:
            return
        if ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH is None:
            raise H40GuardError(
                H40ReasonCode.NOT_TESTABLE,
                "no independently accepted lifecycle implementation authority exists",
            )
        if (
            self._accepted_implementation_authority_hash
            != ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH
        ):
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "service implementation authority anchor has been superseded",
            )
        if (
            self._implementation_authority is not None
            and self._implementation_authority.lifecycle_implementation_authority_hash
            != ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH
        ):
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "service implementation authority mismatch against accepted constant",
            )
        if require_controller:
            if ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH is None:
                raise H40GuardError(
                    H40ReasonCode.NOT_TESTABLE,
                    "no independently accepted H40 P3 controller authority exists",
                )
            if (
                self._accepted_controller_authority_hash
                != ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH
            ):
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    "service controller authority anchor has been superseded",
                )
            if (
                self._controller_authority is not None
                and self._controller_authority.controller_authority_hash
                != ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH
            ):
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    "service controller authority mismatch against accepted constant",
                )

    @staticmethod
    def _inherited_authority_context(
        prior: VerifiedLifecycleAuthorization,
    ) -> dict[str, Any]:
        return {
            key: prior.context[key]
            for key in (
                "implementation_authority",
                "controller_authority",
                "discovery_run_grant",
                "run_authority",
                "seal",
                "split_authority",
            )
            if key in prior.context
        }

    @classmethod
    def synthetic_for_tests(
        cls,
        implementation_authority: H40LifecycleImplementationAuthority,
        evidence_verifier: H40SyntheticEvidenceVerifier,
        controller_authority: H40P3ControllerAuthority | None = None,
        discovery_run_grant: H40DiscoveryRunGrant | None = None,
    ) -> H40LifecycleAuthorityService:
        if controller_authority is None:
            controller_authority = _synthesize_controller_authority(implementation_authority)
        _SYNTHETIC_CONTROLLER_REGISTRY.setdefault(
            controller_authority.controller_authority_hash, controller_authority
        )
        if discovery_run_grant is not None:
            _SYNTHETIC_GRANT_REGISTRY.setdefault(
                discovery_run_grant.discovery_run_grant_hash, discovery_run_grant
            )
        return cls(
            implementation_authority=implementation_authority,
            accepted_implementation_authority_hash=(
                implementation_authority.lifecycle_implementation_authority_hash
            ),
            controller_authority=controller_authority,
            accepted_controller_authority_hash=(
                controller_authority.controller_authority_hash
            ),
            discovery_run_grant=discovery_run_grant,
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

    def _reverify_root_source_truth(
        self,
        authorization: VerifiedLifecycleAuthorization,
    ) -> None:
        """Capability lifetime Model A: reverify root truth at every production transition use."""
        seal = authorization.context.get("seal")
        if seal is None or getattr(seal, "synthetic_only", False):
            return
        if not isinstance(seal, H40RuntimeSnapshotSeal):
            raise H40GuardError(
                H40ReasonCode.SOURCE_UNVERIFIED,
                "production authorization missing bound production runtime seal",
            )
        seal.verify_against_accepted_ledger()

    def _require_prior(
        self,
        prior: VerifiedLifecycleAuthorization,
        *,
        source_state: str,
        target_state: str,
    ) -> None:
        self._assert_current_anchors(require_controller=True)
        if not isinstance(prior, VerifiedLifecycleAuthorization) or prior._issuer_id is not self._issuer_id:
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "foreign verifier authority")
        if prior.source_state != source_state or prior.target_state != target_state:
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "prior transition authority mismatch")
        if prior.receipt.receipt_sha256 != prior.receipt_hash:
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "prior receipt content mismatch")
        self._reverify_root_source_truth(prior)

    def authorize_discovery(
        self,
        *,
        implementation_authority: H40LifecycleImplementationAuthority,
        run_authority: H40RunAuthority,
        seal: H40RuntimeSnapshotSeal,
        authorized_at_utc: str,
        controller_authority: H40P3ControllerAuthority | None = None,
        discovery_run_grant: H40DiscoveryRunGrant | None = None,
    ) -> VerifiedLifecycleAuthorization:
        normalize_audit_timestamp(authorized_at_utc)
        self._assert_current_anchors(require_controller=True)
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

        active_controller: H40P3ControllerAuthority
        if not self._synthetic_test_mode:
            ctrl = controller_authority or self._controller_authority
            if (
                ctrl is None
                or self._accepted_controller_authority_hash is None
                or ctrl.controller_authority_hash != self._accepted_controller_authority_hash
                or ctrl.lifecycle_implementation_authority_hash
                != implementation_authority.lifecycle_implementation_authority_hash
            ):
                raise H40GuardError(
                    H40ReasonCode.NOT_TESTABLE,
                    "no independently accepted H40 P3 controller authority exists",
                )
            active_controller = ctrl
        else:
            active_controller = (
                controller_authority
                or self._controller_authority
                or _synthesize_controller_authority(implementation_authority)
            )
            _SYNTHETIC_CONTROLLER_REGISTRY.setdefault(
                active_controller.controller_authority_hash, active_controller
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

        expected_grant = H40DiscoveryRunGrant.from_controller_and_run(
            controller_authority=active_controller,
            run_authority=run_authority,
            seal=seal,
            authorized_at_utc=authorized_at_utc,
        )
        active_grant: H40DiscoveryRunGrant
        if discovery_run_grant is not None:
            if discovery_run_grant != expected_grant:
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    "discovery run grant mismatch against active controller and run authority",
                )
            active_grant = discovery_run_grant
        elif self._discovery_run_grant is not None:
            if self._discovery_run_grant != expected_grant:
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    "service discovery run grant mismatch against active controller and run authority",
                )
            active_grant = self._discovery_run_grant
        else:
            active_grant = expected_grant

        if self._synthetic_test_mode:
            _SYNTHETIC_GRANT_REGISTRY.setdefault(
                active_grant.discovery_run_grant_hash, active_grant
            )

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
            controller_authority_hash=active_controller.controller_authority_hash,
            discovery_run_grant_hash=active_grant.discovery_run_grant_hash,
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
            context={
                "implementation_authority": implementation_authority,
                "controller_authority": active_controller,
                "discovery_run_grant": active_grant,
                "run_authority": run_authority,
                "seal": seal,
            },
        )

    def authorize_candidate_lock(
        self,
        *,
        discovery_authority: VerifiedLifecycleAuthorization,
        evidence: H40DiscoveryResultEvidence,
        locked_at_utc: str,
        verified_at_utc: str,
    ) -> VerifiedLifecycleAuthorization:
        self._require_prior(
            discovery_authority,
            source_state="H40_P1_SCAFFOLDED",
            target_state="H40_DISCOVERY",
        )
        if not isinstance(evidence, H40DiscoveryResultEvidence):
            raise TypeError("candidate lock requires H40DiscoveryResultEvidence")
        verifier = self._evidence_verifier
        if verifier is None:
            raise H40GuardError(H40ReasonCode.NOT_TESTABLE, "no accepted scientific evidence verifier")
        if not self._synthetic_test_mode:
            # The Protocol describes behavior, not production implementation authority.
            # Import here so discovery_evidence can continue importing this module.
            from .discovery_evidence import (
                _VERIFIER_METHODS,
                H40ProductionDiscoveryEvidenceVerifier,
            )

            if type(verifier) is not H40ProductionDiscoveryEvidenceVerifier:
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    "unaccepted production Discovery verifier implementation",
                )
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
        if not self._synthetic_test_mode:
            _VERIFIER_METHODS["assert_runtime_integrity"](
                cast(H40ProductionDiscoveryEvidenceVerifier, verifier),
                seal=seal, receipt=discovery_receipt,
            )

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
        if self._synthetic_test_mode:
            verifier.verify_discovery_manifest(evidence, evidence.candidate_result_entries)
        else:
            _VERIFIER_METHODS["verify_discovery_manifest"](
                cast(H40ProductionDiscoveryEvidenceVerifier, verifier),
                evidence, evidence.candidate_result_entries,
            )
        scored: list[tuple[H40CandidateResultEntry, H40CandidateVerification]] = []
        scientific_unavailable = False
        for entry in evidence.candidate_result_entries:
            if self._synthetic_test_mode:
                result = verifier.verify_candidate(
                    entry,
                    run_authority_id=evidence.run_authority_id,
                    correction_manifest_hash=evidence.correction_input_evidence_manifest_hash,
                )
            else:
                result = _VERIFIER_METHODS["verify_candidate"](
                    cast(H40ProductionDiscoveryEvidenceVerifier, verifier), entry,
                    run_authority_id=evidence.run_authority_id,
                    correction_manifest_hash=evidence.correction_input_evidence_manifest_hash,
                )
            scientific_unavailable = scientific_unavailable or result.scientific_unavailable
            if result.hard_gates_passed:
                if (
                    result.adjusted_lcb_net_expectancy is None
                    or result.adjusted_lcb_precision is None
                ):
                    raise H40GuardError(
                        H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                        "passed candidate has undefined scientific lower bound",
                    )
                scored.append((entry, result))
        if not scored:
            reason = H40ReasonCode.NOT_TESTABLE if scientific_unavailable else H40ReasonCode.THRESHOLD_UNMET
            raise H40GuardError(reason, "no candidate passed every accepted hard gate")
        scored.sort(
            key=lambda item: (
                -cast(Decimal, item[1].adjusted_lcb_net_expectancy),
                -cast(Decimal, item[1].adjusted_lcb_precision),
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
                **self._inherited_authority_context(discovery_authority),
                "discovery_authority": discovery_authority,
                "evidence": evidence,
                "selected_entry": selected,
            },
        )

    def authorize_wf_validation(
        self,
        *,
        candidate_authority: VerifiedLifecycleAuthorization,
        evidence: H40WFValidationResultEvidence,
        split_authority: H40ExpectedSplitAuthority | None = None,
        validated_at_utc: str,
        verified_at_utc: str,
    ) -> VerifiedLifecycleAuthorization:
        if not self._synthetic_test_mode and split_authority is not None:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "caller-supplied split authority cannot override production derivation",
            )
        self._require_prior(
            candidate_authority,
            source_state="H40_DISCOVERY",
            target_state="H40_CANDIDATE_LOCKED",
        )
        if not isinstance(evidence, H40WFValidationResultEvidence):
            raise TypeError("WF validation requires H40WFValidationResultEvidence")
        active_split: H40ExpectedSplitAuthority
        if not self._synthetic_test_mode and not candidate_authority.synthetic_only:
            expected_split = derive_expected_wf_authority(candidate_authority)
            active_split = expected_split
        else:
            if split_authority is None:
                active_split = derive_expected_wf_authority(candidate_authority)
            else:
                if not isinstance(split_authority, H40ExpectedSplitAuthority):
                    raise TypeError("WF validation requires H40ExpectedSplitAuthority")
                active_split = split_authority

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
            or evidence.split_manifest_hash != active_split.split_manifest_hash
            or evidence.split_attestation_hash != active_split.split_attestation_hash
            or dict(evidence.accepted_validation_contract_hashes)
            != dict(active_split.accepted_validation_contract_hashes)
        ):
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "WF result lineage mismatch")
        actual_folds = [
            (item.fold_id, item.partition_id, item.split_definition_hash, item.fold_identity_hash)
            for item in evidence.fold_result_entries
        ]
        expected_folds = [
            (item.fold_id, item.partition_id, item.split_definition_hash, item.fold_identity_hash)
            for item in active_split.folds
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
                **self._inherited_authority_context(candidate_authority),
                "candidate_authority": candidate_authority,
                "evidence": evidence,
                "split_authority": active_split,
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
            context={
                **self._inherited_authority_context(wf_authority),
                "wf_authority": wf_authority,
            },
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
        self._reverify_root_source_truth(prior_authority)
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
                **self._inherited_authority_context(prior_authority),
                "failure_evidence": failure_evidence,
                "prior_authority": prior_authority,
            },
        )

    def revalidate_authorization(self, authorization: VerifiedLifecycleAuthorization) -> None:
        """Recompute a previously issued authorization and all bound synthetic evidence."""
        self._assert_current_anchors(require_controller=True)
        if not isinstance(authorization, VerifiedLifecycleAuthorization) or authorization._issuer_id is not self._issuer_id:
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "foreign verifier authority")
        self._reverify_root_source_truth(authorization)
        receipt = authorization.receipt
        reconstructed: VerifiedLifecycleAuthorization
        if isinstance(receipt, (H40DiscoveryAuthorizationReceipt, H40DiscoveryAuthorizationReceiptV2)):
            run_authority = authorization.context.get("run_authority")
            seal = authorization.context.get("seal")
            implementation = self._implementation_authority
            controller = (
                authorization.context.get("controller_authority")
                or self._controller_authority
            )
            grant = (
                authorization.context.get("discovery_run_grant")
                or self._discovery_run_grant
            )
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
                controller_authority=controller,
                discovery_run_grant=grant,
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
            ):
                raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "WF context missing")

            is_production = not self._synthetic_test_mode and not prior.synthetic_only
            if is_production:
                expected_split = derive_expected_wf_authority(prior)
                if split is not None and split != expected_split:
                    raise H40GuardError(
                        H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                        "persisted WF split authority does not match derived production authority",
                    )
                reconstructed = self.authorize_wf_validation(
                    candidate_authority=prior,
                    evidence=evidence,
                    split_authority=None,
                    validated_at_utc=receipt.validated_at_utc,
                    verified_at_utc=receipt.verified_at_utc,
                )
            else:
                if not isinstance(split, H40ExpectedSplitAuthority):
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
    "H40_RECEIPT_DISCOVERY_AUTH_V2": H40DiscoveryAuthorizationReceiptV2.from_dict,
    "H40_RECEIPT_DISCOVERY_AUTH_V3": H40DiscoveryAuthorizationReceipt.from_dict,
    "H40_RECEIPT_CANDIDATE_LOCK_V2": H40CandidateLockReceipt.from_dict,
    "H40_RECEIPT_WF_VALIDATION_V2": H40WFValidationReceipt.from_dict,
    "H40_RECEIPT_CONFIRMATION_READY_V2": H40ConfirmationReadyReceipt.from_dict,
    "H40_RECEIPT_TERMINATION_V2": H40TerminationReceipt.from_dict,
})

_ACCEPTED_TRANSITIONS: frozenset[tuple[str, str]] = frozenset({
    # Genesis / root
    ("H40_P1_SCAFFOLDED", "H40_DISCOVERY"),
    # Forward pipeline
    ("H40_DISCOVERY", "H40_CANDIDATE_LOCKED"),
    ("H40_CANDIDATE_LOCKED", "H40_WALK_FORWARD_VALIDATED"),
    ("H40_WALK_FORWARD_VALIDATED", "H40_CONFIRMATION_READY"),
    # Accepted termination rows
    ("H40_P1_SCAFFOLDED", "H40_NO_GO"),
    ("H40_DISCOVERY", "H40_NO_GO"),
    ("H40_CANDIDATE_LOCKED", "H40_NO_GO"),
    ("H40_WALK_FORWARD_VALIDATED", "H40_NO_GO"),
    ("H40_CONFIRMATION_READY", "H40_NO_GO"),
    ("H40_P1_SCAFFOLDED", "NOT_TESTABLE"),
    ("H40_DISCOVERY", "NOT_TESTABLE"),
})

_RECEIPT_TYPE_TRANSITIONS: Mapping[type[_Receipt], tuple[str, str]] = MappingProxyType({
    H40DiscoveryAuthorizationReceipt: ("H40_P1_SCAFFOLDED", "H40_DISCOVERY"),
    H40DiscoveryAuthorizationReceiptV2: ("H40_P1_SCAFFOLDED", "H40_DISCOVERY"),
    H40CandidateLockReceipt: ("H40_DISCOVERY", "H40_CANDIDATE_LOCKED"),
    H40WFValidationReceipt: ("H40_CANDIDATE_LOCKED", "H40_WALK_FORWARD_VALIDATED"),
    H40ConfirmationReadyReceipt: ("H40_WALK_FORWARD_VALIDATED", "H40_CONFIRMATION_READY"),
})



@dataclass(frozen=True)
class H40LifecyclePersistenceContextV1:
    implementation_authority_hash: str
    run_authority_id: str
    runtime_seal_hash: str
    predecessor_receipt_hash: str | None = None
    split_authority_hash: str | None = None
    schema_id: str = "H40_LIFECYCLE_PERSISTENCE_CONTEXT_V1"

    _KEYS: ClassVar[frozenset[str]] = frozenset({
        "implementation_authority_hash",
        "predecessor_receipt_hash",
        "run_authority_id",
        "runtime_seal_hash",
        "schema_id",
        "split_authority_hash",
    })

    def __post_init__(self) -> None:
        if self.schema_id != "H40_LIFECYCLE_PERSISTENCE_CONTEXT_V1":
            raise ValueError("lifecycle persistence context schema mismatch")
        for name in (
            "implementation_authority_hash",
            "run_authority_id",
            "runtime_seal_hash",
        ):
            _require_sha256(getattr(self, name), name)
        for name in ("predecessor_receipt_hash", "split_authority_hash"):
            value = getattr(self, name)
            if value is not None:
                _require_sha256(value, name)

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self._KEYS}

    @property
    def context_hash(self) -> str:
        return canonical_sha256(self.to_dict())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40LifecyclePersistenceContextV1:
        _require_exact_keys(data, cls._KEYS, cls.__name__)
        _require_string_fields(
            data,
            cls._KEYS - {"predecessor_receipt_hash", "split_authority_hash"},
            cls.__name__,
        )
        for name in ("predecessor_receipt_hash", "split_authority_hash"):
            if data[name] is not None and not isinstance(data[name], str):
                raise TypeError(f"{cls.__name__}.{name} must be a string or null")
        return cls(
            implementation_authority_hash=str(data["implementation_authority_hash"]),
            run_authority_id=str(data["run_authority_id"]),
            runtime_seal_hash=str(data["runtime_seal_hash"]),
            predecessor_receipt_hash=(
                None
                if data["predecessor_receipt_hash"] is None
                else str(data["predecessor_receipt_hash"])
            ),
            split_authority_hash=(
                None
                if data["split_authority_hash"] is None
                else str(data["split_authority_hash"])
            ),
            schema_id=str(data["schema_id"]),
        )


@dataclass(frozen=True)
class H40LifecyclePersistenceContext:
    controller_authority_hash: str
    discovery_run_grant_hash: str
    implementation_authority_hash: str
    run_authority_id: str
    runtime_seal_hash: str
    predecessor_receipt_hash: str | None = None
    split_authority_hash: str | None = None
    schema_id: str = "H40_LIFECYCLE_PERSISTENCE_CONTEXT_V2"

    _KEYS: ClassVar[frozenset[str]] = frozenset({
        "controller_authority_hash",
        "discovery_run_grant_hash",
        "implementation_authority_hash",
        "predecessor_receipt_hash",
        "run_authority_id",
        "runtime_seal_hash",
        "schema_id",
        "split_authority_hash",
    })

    def __post_init__(self) -> None:
        if self.schema_id != "H40_LIFECYCLE_PERSISTENCE_CONTEXT_V2":
            raise ValueError("lifecycle persistence context schema mismatch")
        for name in (
            "controller_authority_hash",
            "discovery_run_grant_hash",
            "implementation_authority_hash",
            "run_authority_id",
            "runtime_seal_hash",
        ):
            _require_sha256(getattr(self, name), name)
        for name in ("predecessor_receipt_hash", "split_authority_hash"):
            value = getattr(self, name)
            if value is not None:
                _require_sha256(value, name)

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self._KEYS}

    @property
    def context_hash(self) -> str:
        return canonical_sha256(self.to_dict())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40LifecyclePersistenceContext:
        _require_exact_keys(data, cls._KEYS, cls.__name__)
        _require_string_fields(
            data,
            cls._KEYS - {"predecessor_receipt_hash", "split_authority_hash"},
            cls.__name__,
        )
        for name in ("predecessor_receipt_hash", "split_authority_hash"):
            if data[name] is not None and not isinstance(data[name], str):
                raise TypeError(f"{cls.__name__}.{name} must be a string or null")
        return cls(
            controller_authority_hash=str(data["controller_authority_hash"]),
            discovery_run_grant_hash=str(data["discovery_run_grant_hash"]),
            implementation_authority_hash=str(data["implementation_authority_hash"]),
            run_authority_id=str(data["run_authority_id"]),
            runtime_seal_hash=str(data["runtime_seal_hash"]),
            predecessor_receipt_hash=(
                None
                if data["predecessor_receipt_hash"] is None
                else str(data["predecessor_receipt_hash"])
            ),
            split_authority_hash=(
                None
                if data["split_authority_hash"] is None
                else str(data["split_authority_hash"])
            ),
            schema_id=str(data["schema_id"]),
        )


@runtime_checkable
class H40LifecycleAuthorityResolver(Protocol):
    """Typed resolver seam backed by accepted immutable authority stores."""

    @property
    def synthetic_only(self) -> bool: ...

    def resolve_implementation_authority(
        self,
        authority_hash: str,
    ) -> H40LifecycleImplementationAuthority: ...

    def resolve_run_authority(self, run_authority_id: str) -> H40RunAuthority: ...

    def resolve_runtime_seal(self, seal_hash: str) -> H40RuntimeSnapshotSeal: ...

    def resolve_split_authority(
        self,
        split_authority_hash: str,
    ) -> H40ExpectedSplitAuthority: ...

    def resolve_controller_authority(
        self,
        controller_authority_hash: str,
    ) -> H40P3ControllerAuthority: ...

    def resolve_discovery_run_grant(
        self,
        grant_hash: str,
    ) -> H40DiscoveryRunGrant: ...


_SYNTHETIC_RESOLVER_TOKEN = object()


class H40SyntheticAuthorityResolver:
    """Immutable in-memory resolver for synthetic/governance tests only."""

    synthetic_only = True

    def __init__(
        self,
        *,
        implementation_authorities: Sequence[H40LifecycleImplementationAuthority],
        run_authorities: Sequence[H40RunAuthority],
        runtime_seals: Sequence[H40RuntimeSnapshotSeal],
        split_authorities: Sequence[H40ExpectedSplitAuthority],
        controller_authorities: Sequence[H40P3ControllerAuthority] = (),
        discovery_run_grants: Sequence[H40DiscoveryRunGrant] = (),
        _construction_token: object,
    ) -> None:
        if _construction_token is not _SYNTHETIC_RESOLVER_TOKEN:
            raise TypeError("use H40SyntheticAuthorityResolver.for_tests()")
        self._implementation_authorities = MappingProxyType({
            item.lifecycle_implementation_authority_hash: item
            for item in implementation_authorities
        })
        self._run_authorities = MappingProxyType({
            item.run_authority_id: item for item in run_authorities
        })
        self._runtime_seals = MappingProxyType({
            item.authority_context_hash: item for item in runtime_seals
        })
        self._split_authorities = MappingProxyType({
            item.authority_context_hash: item for item in split_authorities
        })

        ctrl_map: dict[str, H40P3ControllerAuthority] = {
            item.controller_authority_hash: item for item in controller_authorities
        }
        grant_map: dict[str, H40DiscoveryRunGrant] = {
            item.discovery_run_grant_hash: item for item in discovery_run_grants
        }

        # Auto-synthesize default controller authorities and grants for each implementation + seal/run if not provided
        if not controller_authorities:
            for impl in implementation_authorities:
                synth_ctrl = _synthesize_controller_authority(impl)
                ctrl_map.setdefault(synth_ctrl.controller_authority_hash, synth_ctrl)

        if not discovery_run_grants:
            for impl in implementation_authorities:
                synth_ctrl = _synthesize_controller_authority(impl)
                for seal in runtime_seals:
                    with contextlib.suppress(ValueError, KeyError, H40GuardError, TypeError):
                        expected_run = H40RunAuthority.from_seal(seal, impl.lifecycle_implementation_authority_hash)
                        if expected_run.run_authority_id in self._run_authorities:
                            synth_grant = H40DiscoveryRunGrant.from_controller_and_run(
                                controller_authority=synth_ctrl,
                                run_authority=expected_run,
                                seal=seal,
                                authorized_at_utc="2026-09-23T00:00:00Z",
                            )
                            grant_map.setdefault(synth_grant.discovery_run_grant_hash, synth_grant)

        self._controller_authorities = MappingProxyType(ctrl_map)
        self._discovery_run_grants = MappingProxyType(grant_map)

    @classmethod
    def for_tests(
        cls,
        *,
        implementation_authorities: Sequence[H40LifecycleImplementationAuthority],
        run_authorities: Sequence[H40RunAuthority],
        runtime_seals: Sequence[H40RuntimeSnapshotSeal],
        split_authorities: Sequence[H40ExpectedSplitAuthority] = (),
        controller_authorities: Sequence[H40P3ControllerAuthority] = (),
        discovery_run_grants: Sequence[H40DiscoveryRunGrant] = (),
    ) -> H40SyntheticAuthorityResolver:
        return cls(
            implementation_authorities=implementation_authorities,
            run_authorities=run_authorities,
            runtime_seals=runtime_seals,
            split_authorities=split_authorities,
            controller_authorities=controller_authorities,
            discovery_run_grants=discovery_run_grants,
            _construction_token=_SYNTHETIC_RESOLVER_TOKEN,
        )

    @staticmethod
    def _resolve(values: Mapping[str, Any], identity: str, name: str) -> Any:
        _require_sha256(identity, name)
        resolved = values.get(identity)
        if resolved is None:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"authoritative resolver has no {name} {identity}",
            )
        return resolved

    def resolve_implementation_authority(
        self,
        authority_hash: str,
    ) -> H40LifecycleImplementationAuthority:
        return cast(
            H40LifecycleImplementationAuthority,
            self._resolve(
                self._implementation_authorities,
                authority_hash,
                "implementation authority",
            ),
        )

    def resolve_run_authority(self, run_authority_id: str) -> H40RunAuthority:
        return cast(
            H40RunAuthority,
            self._resolve(self._run_authorities, run_authority_id, "run authority"),
        )

    def resolve_runtime_seal(self, seal_hash: str) -> H40RuntimeSnapshotSeal:
        return cast(
            H40RuntimeSnapshotSeal,
            self._resolve(self._runtime_seals, seal_hash, "runtime seal"),
        )

    def resolve_split_authority(
        self,
        split_authority_hash: str,
    ) -> H40ExpectedSplitAuthority:
        return cast(
            H40ExpectedSplitAuthority,
            self._resolve(
                self._split_authorities,
                split_authority_hash,
                "split authority",
            ),
        )

    def resolve_controller_authority(
        self,
        controller_authority_hash: str,
    ) -> H40P3ControllerAuthority:
        _require_sha256(controller_authority_hash, "controller authority")
        resolved = self._controller_authorities.get(controller_authority_hash)
        if resolved is None:
            resolved = _SYNTHETIC_CONTROLLER_REGISTRY.get(controller_authority_hash)
        if resolved is None:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"authoritative resolver has no controller authority {controller_authority_hash}",
            )
        return resolved

    def resolve_discovery_run_grant(
        self,
        grant_hash: str,
    ) -> H40DiscoveryRunGrant:
        _require_sha256(grant_hash, "discovery run grant")
        resolved = self._discovery_run_grants.get(grant_hash)
        if resolved is None:
            resolved = _SYNTHETIC_GRANT_REGISTRY.get(grant_hash)
        if resolved is None:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"authoritative resolver has no discovery run grant {grant_hash}",
            )
        return resolved


class H40LifecycleArtifactStore:
    """Minimal canonical, write-once lifecycle governance persistence."""

    _KEY_RE = re.compile(r"[0-9]{2}_[a-z0-9_]+\Z", re.ASCII)

    def __init__(self, base_path: str | Path) -> None:
        self._base_path = Path(base_path)

    @property
    def sqlite_path(self) -> Path:
        return self._base_path / "artifacts" / "h40" / "lifecycle" / "lifecycle_heads.sqlite3"

    def _get_sqlite_conn(self) -> sqlite3.Connection:
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.sqlite_path), timeout=60.0, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS h40_lifecycle_run_heads (
                run_authority_id TEXT PRIMARY KEY,
                head_receipt_hash TEXT NOT NULL,
                head_state TEXT NOT NULL,
                head_predecessor_receipt_hash TEXT,
                transition_sequence INTEGER NOT NULL,
                terminal INTEGER NOT NULL,
                head_hash TEXT NOT NULL,
                head_json TEXT NOT NULL
            )
            """
        )
        cursor = conn.execute("PRAGMA table_info(h40_lifecycle_run_heads)")
        columns = {row[1] for row in cursor.fetchall()}
        if "head_hash" not in columns:
            conn.execute("ALTER TABLE h40_lifecycle_run_heads ADD COLUMN head_hash TEXT NOT NULL DEFAULT ''")
        return conn

    def _validate_and_parse_head_row(
        self,
        *,
        row: tuple[Any, ...],
        expected_run_authority_id: str,
    ) -> H40DurableRunHead:
        curr_receipt, curr_state, curr_pred, curr_seq, curr_term, curr_head_hash, curr_json = row
        try:
            head_data = json.loads(curr_json)
            head = H40DurableRunHead.from_dict(head_data)
        except Exception as exc:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"durable head_json parsing failure: {exc}",
            ) from exc

        if head.run_authority_id != expected_run_authority_id:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"durable head run_authority_id '{head.run_authority_id}' does not match expected '{expected_run_authority_id}'",
            )
        if head.head_receipt_hash != curr_receipt:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"durable head receipt_hash '{head.head_receipt_hash}' does not match scalar column '{curr_receipt}'",
            )
        if head.head_state != curr_state:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"durable head state '{head.head_state}' does not match scalar column '{curr_state}'",
            )
        if head.head_predecessor_receipt_hash != curr_pred:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"durable head predecessor '{head.head_predecessor_receipt_hash}' does not match scalar column '{curr_pred}'",
            )
        if head.transition_sequence != curr_seq:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"durable head sequence '{head.transition_sequence}' does not match scalar column '{curr_seq}'",
            )
        if head.terminal != bool(curr_term):
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"durable head terminal '{head.terminal}' does not match scalar column '{bool(curr_term)}'",
            )
        if head.head_state not in _ACCEPTED_LIFECYCLE_STATES:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"durable head state '{head.head_state}' is not in accepted lifecycle vocabulary",
            )
        expected_terminal = head.head_state in _TERMINAL_STATES
        if head.terminal != expected_terminal:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"durable head terminal flag '{head.terminal}' inconsistent with state '{head.head_state}' (expected {expected_terminal})",
            )
        if not curr_head_hash:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "durable head row lacks authoritative head_hash integrity column",
            )
        if curr_head_hash != head.head_hash:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"durable head_hash '{curr_head_hash}' does not match canonical head hash '{head.head_hash}'",
            )
        return head

    def get_committed_run_head(self, run_authority_id: str) -> H40DurableRunHead | None:
        _require_sha256(run_authority_id, "run_authority_id")
        conn = self._get_sqlite_conn()
        try:
            cursor = conn.execute(
                "SELECT head_receipt_hash, head_state, head_predecessor_receipt_hash, "
                "transition_sequence, terminal, head_hash, head_json "
                "FROM h40_lifecycle_run_heads WHERE run_authority_id = ?",
                (run_authority_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return self._validate_and_parse_head_row(
                row=row,
                expected_run_authority_id=run_authority_id,
            )
        finally:
            conn.close()

    def _advance_verified_run_head(
        self,
        *,
        authorization: VerifiedLifecycleAuthorization,
    ) -> H40DurableRunHead:
        return self._commit_run_head(authorization=authorization)

    def _commit_run_head(
        self,
        *,
        authorization: VerifiedLifecycleAuthorization,
    ) -> H40DurableRunHead:
        if not isinstance(authorization, VerifiedLifecycleAuthorization):
            raise TypeError("authorization must be VerifiedLifecycleAuthorization")

        run_authority_id = authorization.run_authority_id
        receipt_hash = authorization.receipt_hash
        target_state = authorization.target_state
        predecessor_receipt_hash = authorization.upstream_receipt_hash
        source_state = authorization.source_state

        _require_sha256(run_authority_id, "run_authority_id")
        _require_sha256(receipt_hash, "receipt_hash")
        _require_text(target_state, "target_state")
        if predecessor_receipt_hash is not None:
            _require_sha256(predecessor_receipt_hash, "predecessor_receipt_hash")

        if target_state not in _ACCEPTED_LIFECYCLE_STATES:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"unrecognized target state '{target_state}'",
            )

        if target_state == "H40_CONFIRMATION_EVALUATED_ONCE":
            raise H40GuardError(
                H40ReasonCode.CONFIRMATION_NOT_READY,
                "F02 confirmation evaluated once is sealed and prohibited",
            )

        receipt_path = self._receipts_dir(run_authority_id) / f"{receipt_hash}.json"
        if not receipt_path.is_file():
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"published receipt '{receipt_hash}.json' does not exist on disk",
            )

        try:
            envelope_raw = json.loads(receipt_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"published receipt '{receipt_hash}.json' envelope failed JSON parsing: {exc}",
            ) from exc

        if not isinstance(envelope_raw, Mapping):
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "lifecycle receipt envelope must be an object",
            )

        _require_exact_keys(
            envelope_raw,
            frozenset({
                "authority_context",
                "bound_evidence",
                "bound_evidence_sha256",
                "receipt",
                "receipt_sha256",
            }),
            "lifecycle receipt envelope",
        )

        if envelope_raw["receipt_sha256"] != receipt_hash:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"envelope receipt_sha256 '{envelope_raw['receipt_sha256']}' does not match '{receipt_hash}'",
            )

        raw_receipt = envelope_raw["receipt"]
        if not isinstance(raw_receipt, Mapping):
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "receipt in envelope must be an object",
            )

        if canonical_sha256(raw_receipt) != receipt_hash:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "envelope receipt canonical hash does not match receipt_sha256",
            )

        schema_id = raw_receipt.get("receipt_schema_id")
        parser = _RECEIPT_PARSERS.get(str(schema_id))
        if parser is None:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"unknown receipt schema_id '{schema_id}'",
            )
        try:
            typed_receipt = parser(raw_receipt)
        except Exception as exc:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"failed to parse typed receipt from envelope: {exc}",
            ) from exc

        if typed_receipt.run_authority_id != run_authority_id:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"receipt run_authority_id '{typed_receipt.run_authority_id}' does not match requested '{run_authority_id}'",
            )

        if isinstance(typed_receipt, H40DiscoveryAuthorizationReceipt):
            receipt_target_state = "H40_DISCOVERY"
            receipt_source_state = "H40_P1_SCAFFOLDED"
        elif isinstance(typed_receipt, H40CandidateLockReceipt):
            receipt_target_state = "H40_CANDIDATE_LOCKED"
            receipt_source_state = "H40_DISCOVERY"
        elif isinstance(typed_receipt, H40WFValidationReceipt):
            receipt_target_state = "H40_WALK_FORWARD_VALIDATED"
            receipt_source_state = "H40_CANDIDATE_LOCKED"
        elif isinstance(typed_receipt, H40ConfirmationReadyReceipt):
            receipt_target_state = "H40_CONFIRMATION_READY"
            receipt_source_state = "H40_WALK_FORWARD_VALIDATED"
        elif isinstance(typed_receipt, H40TerminationReceipt):
            receipt_target_state = typed_receipt.target_state
            receipt_source_state = typed_receipt.source_state
        else:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"unexpected receipt type '{type(typed_receipt).__name__}'",
            )

        if receipt_target_state != target_state:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"receipt target state '{receipt_target_state}' does not match requested target state '{target_state}'",
            )

        if predecessor_receipt_hash is None and target_state != "H40_DISCOVERY":
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"state '{target_state}' cannot be genesis / sequence zero",
            )

        if typed_receipt.upstream_receipt_hash != predecessor_receipt_hash:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"receipt upstream_receipt_hash '{typed_receipt.upstream_receipt_hash}' does not match predecessor '{predecessor_receipt_hash}'",
            )

        if authorization.receipt_hash != receipt_hash:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "authorization receipt_hash mismatch against receipt_hash",
            )
        if authorization.receipt != typed_receipt:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "authorization receipt does not equal published typed receipt",
            )
        if authorization.target_state != target_state:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "authorization target_state mismatch against requested target_state",
            )
        if authorization.upstream_receipt_hash != predecessor_receipt_hash:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "authorization upstream mismatch against requested predecessor",
            )
        if authorization.run_authority_id != run_authority_id:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "authorization run_authority_id mismatch against requested run_authority_id",
            )

        if source_state != receipt_source_state:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"transition source state '{source_state}' does not match receipt source state '{receipt_source_state}'",
            )

        if (source_state, target_state) not in _ACCEPTED_TRANSITIONS:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"transition '{source_state}' -> '{target_state}' is not an accepted lifecycle transition",
            )

        conn = self._get_sqlite_conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                "SELECT head_receipt_hash, head_state, head_predecessor_receipt_hash, "
                "transition_sequence, terminal, head_hash, head_json FROM h40_lifecycle_run_heads "
                "WHERE run_authority_id = ?",
                (run_authority_id,),
            )
            row = cursor.fetchone()
            if row is None:
                if predecessor_receipt_hash is not None:
                    conn.execute("ROLLBACK")
                    raise H40GuardError(
                        H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                        "non-null predecessor cannot commit as sequence zero genesis",
                    )
                if target_state != "H40_DISCOVERY" or source_state != "H40_P1_SCAFFOLDED":
                    conn.execute("ROLLBACK")
                    raise H40GuardError(
                        H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                        f"state '{target_state}' cannot be genesis / sequence zero",
                    )
                sequence = 0
                terminal = target_state in _TERMINAL_STATES
                head = H40DurableRunHead(
                    head_predecessor_receipt_hash=None,
                    head_receipt_hash=receipt_hash,
                    head_state=target_state,
                    run_authority_id=run_authority_id,
                    terminal=terminal,
                    transition_sequence=sequence,
                )
                head_json = canonical_json(head.to_dict())
                head_hash = head.head_hash
                conn.execute(
                    "INSERT INTO h40_lifecycle_run_heads "
                    "(run_authority_id, head_receipt_hash, head_state, "
                    "head_predecessor_receipt_hash, transition_sequence, terminal, head_hash, head_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_authority_id,
                        receipt_hash,
                        target_state,
                        predecessor_receipt_hash,
                        sequence,
                        int(terminal),
                        head_hash,
                        head_json,
                    ),
                )
                conn.execute("COMMIT")
            else:
                current_head = self._validate_and_parse_head_row(
                    row=row,
                    expected_run_authority_id=run_authority_id,
                )
                if current_head.head_receipt_hash == receipt_hash:
                    # Idempotent retry
                    conn.execute("COMMIT")
                    return current_head

                if current_head.terminal:
                    conn.execute("ROLLBACK")
                    raise H40GuardError(
                        H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                        f"run '{run_authority_id}' is in terminal state '{current_head.head_state}'; no forward commits allowed",
                    )

                if predecessor_receipt_hash != current_head.head_receipt_hash:
                    conn.execute("ROLLBACK")
                    raise H40GuardError(
                        H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                        f"predecessor receipt hash mismatch: expected current head '{current_head.head_receipt_hash}', "
                        f"got '{predecessor_receipt_hash}'",
                    )

                if source_state != current_head.head_state:
                    conn.execute("ROLLBACK")
                    raise H40GuardError(
                        H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                        f"transition source state '{source_state}' does not match current durable head state '{current_head.head_state}'",
                    )

                next_seq = current_head.transition_sequence + 1
                terminal = target_state in _TERMINAL_STATES
                head = H40DurableRunHead(
                    head_predecessor_receipt_hash=current_head.head_receipt_hash,
                    head_receipt_hash=receipt_hash,
                    head_state=target_state,
                    run_authority_id=run_authority_id,
                    terminal=terminal,
                    transition_sequence=next_seq,
                )
                head_json = canonical_json(head.to_dict())
                head_hash = head.head_hash
                conn.execute(
                    "UPDATE h40_lifecycle_run_heads SET "
                    "head_receipt_hash = ?, head_state = ?, head_predecessor_receipt_hash = ?, "
                    "transition_sequence = ?, terminal = ?, head_hash = ?, head_json = ? "
                    "WHERE run_authority_id = ?",
                    (
                        receipt_hash,
                        target_state,
                        current_head.head_receipt_hash,
                        next_seq,
                        int(terminal),
                        head_hash,
                        head_json,
                        run_authority_id,
                    ),
                )
                conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except (sqlite3.Error, OSError):
                pass
            raise
        finally:
            conn.close()

        # Mirror head.json
        run_dir = self._run_dir(run_authority_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        head_path = run_dir / "head.json"
        head_tmp = run_dir / f"head.tmp.{os.getpid()}_{uuid.uuid4().hex}"
        head_tmp.write_text(canonical_json(head.to_dict()) + "\n", encoding="utf-8")
        os.replace(head_tmp, head_path)
        _fsync_dir(run_dir)
        return head

    def _run_dir(self, run_authority_id: str) -> Path:
        _require_sha256(run_authority_id, "run_authority_id")
        return self._base_path / "artifacts" / "h40" / "lifecycle" / "runs" / run_authority_id

    def _receipts_dir(self, run_authority_id: str) -> Path:
        return self._run_dir(run_authority_id) / "receipts"

    def _path(self, run_authority_id: str, transition_key: str) -> Path:
        if _SHA256_RE.fullmatch(transition_key):
            return self._receipts_dir(run_authority_id) / f"{transition_key}.json"
        if self._KEY_RE.fullmatch(transition_key) is None:
            raise ValueError("transition_key must match NN_lowercase_name or sha256 hex")
        return self._run_dir(run_authority_id) / f"{transition_key}.json"

    def _find_receipt_path(self, run_authority_id: str, key_or_hash: str) -> Path:
        if _SHA256_RE.fullmatch(key_or_hash):
            p = self._receipts_dir(run_authority_id) / f"{key_or_hash}.json"
            if p.exists():
                return p
        if self._KEY_RE.fullmatch(key_or_hash):
            p = self._run_dir(run_authority_id) / f"{key_or_hash}.json"
            if p.exists():
                return p
        receipts_dir = self._receipts_dir(run_authority_id)
        if receipts_dir.exists():
            for p in sorted(receipts_dir.glob("*.json")):
                if p.stem == key_or_hash:
                    return p
        run_dir = self._run_dir(run_authority_id)
        if run_dir.exists():
            for p in sorted(run_dir.glob("*.json")):
                if self._KEY_RE.fullmatch(p.stem):
                    if p.stem == key_or_hash:
                        return p
                    try:
                        raw = json.loads(p.read_text(encoding="utf-8"))
                        if isinstance(raw, Mapping) and raw.get("receipt_sha256") == key_or_hash:
                            return p
                    except (OSError, UnicodeError, json.JSONDecodeError):
                        pass
        raise H40GuardError(
            H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
            f"cannot find lifecycle artifact for key/hash '{key_or_hash}'",
        )

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

    @staticmethod
    def _persistence_context(
        authorization: VerifiedLifecycleAuthorization,
    ) -> H40LifecyclePersistenceContext:
        implementation = authorization.context.get("implementation_authority")
        run_authority = authorization.context.get("run_authority")
        seal = authorization.context.get("seal")
        split_authority = authorization.context.get("split_authority")
        controller = authorization.context.get("controller_authority")
        grant = authorization.context.get("discovery_run_grant")
        if (
            not isinstance(implementation, H40LifecycleImplementationAuthority)
            or not isinstance(run_authority, H40RunAuthority)
            or not isinstance(seal, H40RuntimeSnapshotSeal)
            or not isinstance(controller, H40P3ControllerAuthority)
            or not isinstance(grant, H40DiscoveryRunGrant)
        ):
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "verified authorization lacks canonical persistence authority context",
            )
        if split_authority is not None and not isinstance(
            split_authority,
            H40ExpectedSplitAuthority,
        ):
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "verified authorization has an invalid split authority context",
            )
        return H40LifecyclePersistenceContext(
            controller_authority_hash=controller.controller_authority_hash,
            discovery_run_grant_hash=grant.discovery_run_grant_hash,
            implementation_authority_hash=(
                implementation.lifecycle_implementation_authority_hash
            ),
            predecessor_receipt_hash=authorization.upstream_receipt_hash,
            run_authority_id=run_authority.run_authority_id,
            runtime_seal_hash=seal.authority_context_hash,
            split_authority_hash=(
                None
                if split_authority is None
                else split_authority.authority_context_hash
            ),
        )

    @classmethod
    def _envelope(cls, authorization: VerifiedLifecycleAuthorization) -> dict[str, Any]:
        evidence = cls._bound_evidence(authorization)
        return {
            "authority_context": cls._persistence_context(authorization).to_dict(),
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
        service: H40LifecycleAuthorityService,
    ) -> Path:
        if not isinstance(authorization, VerifiedLifecycleAuthorization):
            raise TypeError("only verified lifecycle authorization can be persisted")
        if not isinstance(service, H40LifecycleAuthorityService):
            raise TypeError("service must be H40LifecycleAuthorityService")
        service._assert_current_anchors(require_controller=True)
        service.revalidate_authorization(authorization)

        run_authority_id = authorization.run_authority_id
        receipt_hash = authorization.receipt_hash
        receipts_dir = self._receipts_dir(run_authority_id)
        receipts_dir.mkdir(parents=True, exist_ok=True)
        final_receipt_path = receipts_dir / f"{receipt_hash}.json"

        envelope = self._envelope(authorization)
        encoded = (canonical_json(envelope) + "\n").encode("utf-8")

        if final_receipt_path.exists():
            existing = final_receipt_path.read_bytes()
            if existing != encoded:
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    "write-once immutable lifecycle receipt already exists with different bytes",
                )
        else:
            temp_path = receipts_dir / f"receipt.{os.getpid()}_{uuid.uuid4().hex}.tmp"
            descriptor = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
                try:
                    os.link(temp_path, final_receipt_path)
                except FileExistsError:
                    if final_receipt_path.read_bytes() != encoded:
                        raise H40GuardError(
                            H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                            "write-once immutable lifecycle receipt already exists with different bytes",
                        )
                except OSError as err:
                    raise H40GuardError(
                        H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                        f"authoritative immutable receipt link failed: {err}",
                    ) from err
                finally:
                    temp_path.unlink(missing_ok=True)
            except Exception:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass
                raise

        # RG-H01-01: Every path that may advance durable head MUST establish
        # authoritative receipt-directory durability before head commit.
        _fsync_dir(receipts_dir, fail_closed=True)

        legacy_path: Path | None = None
        if transition_key != receipt_hash and self._KEY_RE.fullmatch(transition_key):
            run_dir = self._run_dir(run_authority_id)
            run_dir.mkdir(parents=True, exist_ok=True)
            legacy_path = run_dir / f"{transition_key}.json"
            if legacy_path.exists():
                if legacy_path.read_bytes() != encoded:
                    raise H40GuardError(
                        H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                        "write-once lifecycle legacy artifact already exists with different bytes",
                    )
            else:
                legacy_tmp = run_dir / f"legacy.{os.getpid()}_{uuid.uuid4().hex}.tmp"
                legacy_tmp.write_bytes(encoded)
                os.replace(legacy_tmp, legacy_path)
                _fsync_dir(run_dir, fail_closed=False)

        self._commit_run_head(authorization=authorization)

        return legacy_path if legacy_path is not None else final_receipt_path

    def _restore(
        self,
        run_authority_id: str,
        transition_key: str,
    ) -> tuple[
        _Receipt,
        _ResultEvidence | None,
        H40LifecyclePersistenceContext | H40LifecyclePersistenceContextV1,
    ]:
        path = self._find_receipt_path(run_authority_id, transition_key)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "invalid lifecycle artifact") from exc
        if not isinstance(raw, Mapping):
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "lifecycle envelope must be an object")
        _require_exact_keys(
            raw,
            frozenset({
                "authority_context",
                "bound_evidence",
                "bound_evidence_sha256",
                "receipt",
                "receipt_sha256",
            }),
            "lifecycle envelope",
        )
        raw_context = raw["authority_context"]
        if not isinstance(raw_context, Mapping):
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "lifecycle authority context must be an object",
            )
        schema = raw_context.get("schema_id")
        context: H40LifecyclePersistenceContext | H40LifecyclePersistenceContextV1
        if schema == "H40_LIFECYCLE_PERSISTENCE_CONTEXT_V1":
            context = H40LifecyclePersistenceContextV1.from_dict(raw_context)
        elif schema == "H40_LIFECYCLE_PERSISTENCE_CONTEXT_V2":
            context = H40LifecyclePersistenceContext.from_dict(raw_context)
        else:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"unknown lifecycle persistence context schema '{schema}'",
            )
        if context.run_authority_id != run_authority_id:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "persistence context run authority does not match storage boundary",
            )
        payload = raw["receipt"]
        digest = raw["receipt_sha256"]
        if not isinstance(payload, Mapping) or not isinstance(digest, str):
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "invalid lifecycle envelope fields")
        if canonical_sha256(payload) != digest:
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "lifecycle receipt content hash mismatch")
        schema_id = payload.get("receipt_schema_id")
        parser = _RECEIPT_PARSERS.get(str(schema_id))
        if parser is None:
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "unknown lifecycle receipt schema")
        receipt = parser(payload)
        if receipt.receipt_sha256 != digest or receipt.run_authority_id != run_authority_id:
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "restored receipt authority mismatch")
        if context.predecessor_receipt_hash != receipt.upstream_receipt_hash:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "persistence predecessor context does not match receipt lineage",
            )
        evidence = self._parse_bound_evidence(
            raw["bound_evidence"],
            raw["bound_evidence_sha256"],
            receipt,
        )
        return receipt, evidence, context

    def restore_receipt(self, run_authority_id: str, transition_key: str) -> _Receipt:
        receipt, _, _ = self._restore(run_authority_id, transition_key)
        return receipt

    def _find_transition_key_by_receipt_hash(
        self,
        run_authority_id: str,
        receipt_hash: str,
    ) -> str:
        _require_sha256(receipt_hash, "predecessor receipt hash")
        receipt_path = self._receipts_dir(run_authority_id) / f"{receipt_hash}.json"
        if receipt_path.exists():
            return receipt_hash
        matches: list[str] = []
        run_dir = self._run_dir(run_authority_id)
        if run_dir.exists():
            for path in sorted(run_dir.glob("*.json")):
                if self._KEY_RE.fullmatch(path.stem) is None:
                    continue
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                    raise H40GuardError(
                        H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                        "invalid lifecycle predecessor artifact",
                    ) from exc
                if not isinstance(raw, Mapping):
                    raise H40GuardError(
                        H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                        "lifecycle predecessor envelope must be an object",
                    )
                if raw.get("receipt_sha256") == receipt_hash:
                    payload = raw.get("receipt")
                    if not isinstance(payload, Mapping) or canonical_sha256(payload) != receipt_hash:
                        raise H40GuardError(
                            H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                            "predecessor receipt content hash mismatch",
                        )
                    matches.append(path.stem)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "predecessor receipt must resolve to exactly one persisted artifact",
            )
        raise H40GuardError(
            H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
            f"predecessor receipt '{receipt_hash}' not found",
        )

    @staticmethod
    def _resolve_authority_context(
        context: H40LifecyclePersistenceContext | H40LifecyclePersistenceContextV1,
        resolver: H40LifecycleAuthorityResolver,
    ) -> tuple[
        H40LifecycleImplementationAuthority,
        H40RunAuthority,
        H40RuntimeSnapshotSeal,
        H40ExpectedSplitAuthority | None,
        H40P3ControllerAuthority | None,
        H40DiscoveryRunGrant | None,
    ]:
        implementation = resolver.resolve_implementation_authority(
            context.implementation_authority_hash
        )
        run_authority = resolver.resolve_run_authority(context.run_authority_id)
        seal = resolver.resolve_runtime_seal(context.runtime_seal_hash)
        seal.verify_against_accepted_ledger()
        if (
            implementation.lifecycle_implementation_authority_hash
            != context.implementation_authority_hash
            or run_authority.run_authority_id != context.run_authority_id
            or seal.authority_context_hash != context.runtime_seal_hash
        ):
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "resolved authority object does not match its content address",
            )
        expected_run = H40RunAuthority.from_seal(
            seal,
            implementation.lifecycle_implementation_authority_hash,
        )
        if run_authority != expected_run:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "resolved run authority does not match implementation/runtime seal",
            )
        split_authority = (
            None
            if context.split_authority_hash is None
            else resolver.resolve_split_authority(context.split_authority_hash)
        )
        if split_authority is not None and (
            split_authority.authority_context_hash != context.split_authority_hash
            or split_authority.split_manifest_hash != seal.split_manifest_hash
            or split_authority.split_attestation_hash != seal.split_attestation_hash
        ):
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "resolved split authority does not match runtime seal",
            )

        controller_authority: H40P3ControllerAuthority | None = None
        discovery_run_grant: H40DiscoveryRunGrant | None = None
        if isinstance(context, H40LifecyclePersistenceContext):
            controller_authority = resolver.resolve_controller_authority(
                context.controller_authority_hash
            )
            discovery_run_grant = resolver.resolve_discovery_run_grant(
                context.discovery_run_grant_hash
            )
            if controller_authority.controller_authority_hash != context.controller_authority_hash:
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    "resolved controller authority hash mismatch against context",
                )
            if discovery_run_grant.discovery_run_grant_hash != context.discovery_run_grant_hash:
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    "resolved discovery run grant hash mismatch against context",
                )
            if discovery_run_grant.controller_authority_hash != controller_authority.controller_authority_hash:
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    "resolved discovery run grant controller authority mismatch",
                )
            if discovery_run_grant.run_authority_id != run_authority.run_authority_id:
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    "resolved discovery run grant run_authority_id mismatch",
                )
            if discovery_run_grant.materialized_run_authority_hash != seal.materialized_run_authority_hash:
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    "resolved discovery run grant materialized run authority mismatch",
                )
            expected_grant = H40DiscoveryRunGrant.from_controller_and_run(
                controller_authority=controller_authority,
                run_authority=run_authority,
                seal=seal,
                authorized_at_utc=discovery_run_grant.authorized_at_utc,
            )
            if discovery_run_grant != expected_grant:
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    "resolved discovery run grant does not match exact recomputation",
                )

        return (
            implementation,
            run_authority,
            seal,
            split_authority,
            controller_authority,
            discovery_run_grant,
        )

    def _cold_restore_authorization(
        self,
        run_authority_id: str,
        transition_key: str,
        *,
        service: H40LifecycleAuthorityService,
        resolver: H40LifecycleAuthorityResolver,
        visited_receipts: frozenset[str],
    ) -> VerifiedLifecycleAuthorization:
        receipt, evidence, context = self._restore(run_authority_id, transition_key)
        if receipt.receipt_sha256 in visited_receipts:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "cyclic lifecycle predecessor lineage",
            )
        if not service.synthetic_test_mode:
            service._assert_current_anchors(require_controller=False)
            if isinstance(context, H40LifecyclePersistenceContextV1):
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    "production cold restore rejects H40_LIFECYCLE_PERSISTENCE_CONTEXT_V1",
                )
            if isinstance(receipt, H40DiscoveryAuthorizationReceiptV2):
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    "production cold restore rejects H40_RECEIPT_DISCOVERY_AUTH_V2",
                )
            if isinstance(context, H40LifecyclePersistenceContext):
                if context.implementation_authority_hash != ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH:
                    raise H40GuardError(
                        H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                        "persisted context implementation authority hash does not match current accepted anchor",
                    )
                if isinstance(receipt, H40DiscoveryAuthorizationReceipt):
                    if context.controller_authority_hash != receipt.controller_authority_hash:
                        raise H40GuardError(
                            H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                            "persisted context controller authority hash does not match receipt",
                        )
                    if context.discovery_run_grant_hash != receipt.discovery_run_grant_hash:
                        raise H40GuardError(
                            H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                            "persisted context run grant hash does not match receipt",
                        )
                if (
                    service.current_controller_authority_hash is not None
                    and context.controller_authority_hash != service.current_controller_authority_hash
                ):
                    raise H40GuardError(
                        H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                        "persisted context controller authority hash does not match service anchor",
                    )
        (
            implementation,
            run_authority,
            seal,
            split_authority,
            controller_authority,
            discovery_run_grant,
        ) = self._resolve_authority_context(context, resolver)
        prior: VerifiedLifecycleAuthorization | None = None
        if receipt.upstream_receipt_hash is not None:
            predecessor_key = self._find_transition_key_by_receipt_hash(
                run_authority_id,
                receipt.upstream_receipt_hash,
            )
            prior = self._cold_restore_authorization(
                run_authority_id,
                predecessor_key,
                service=service,
                resolver=resolver,
                visited_receipts=visited_receipts | {receipt.receipt_sha256},
            )
            if prior.receipt_hash != receipt.upstream_receipt_hash:
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    "cold-restored predecessor receipt substitution",
                )

        if isinstance(receipt, (H40DiscoveryAuthorizationReceipt, H40DiscoveryAuthorizationReceiptV2)):
            if prior is not None or evidence is not None:
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    "discovery restore has unexpected predecessor or result evidence",
                )
            if isinstance(receipt, H40DiscoveryAuthorizationReceipt):
                if controller_authority is None or discovery_run_grant is None:
                    raise H40GuardError(
                        H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                        "discovery V3 restore requires controller authority and run grant",
                    )
                if receipt.controller_authority_hash != controller_authority.controller_authority_hash:
                    raise H40GuardError(
                        H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                        "receipt controller authority hash mismatch against resolved controller authority",
                    )
                if receipt.discovery_run_grant_hash != discovery_run_grant.discovery_run_grant_hash:
                    raise H40GuardError(
                        H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                        "receipt discovery run grant hash mismatch against resolved run grant",
                    )
            reconstructed = service.authorize_discovery(
                implementation_authority=implementation,
                run_authority=run_authority,
                seal=seal,
                authorized_at_utc=receipt.authorized_at_utc,
                controller_authority=controller_authority,
                discovery_run_grant=discovery_run_grant,
            )
        elif isinstance(receipt, H40CandidateLockReceipt):
            if prior is None or not isinstance(evidence, H40DiscoveryResultEvidence):
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    "candidate restore lacks predecessor/result evidence",
                )
            reconstructed = service.authorize_candidate_lock(
                discovery_authority=prior,
                evidence=evidence,
                locked_at_utc=receipt.locked_at_utc,
                verified_at_utc=receipt.verified_at_utc,
            )
        elif isinstance(receipt, H40WFValidationReceipt):
            if (
                prior is None
                or not isinstance(evidence, H40WFValidationResultEvidence)
            ):
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    "WF restore lacks predecessor/result evidence",
                )
            is_production = not service.synthetic_test_mode and not prior.synthetic_only
            if is_production:
                expected_split = derive_expected_wf_authority(prior)
                if split_authority is not None and split_authority != expected_split:
                    raise H40GuardError(
                        H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                        "persisted WF split authority does not match derived production authority",
                    )
                reconstructed = service.authorize_wf_validation(
                    candidate_authority=prior,
                    evidence=evidence,
                    split_authority=None,
                    validated_at_utc=receipt.validated_at_utc,
                    verified_at_utc=receipt.verified_at_utc,
                )
            else:
                if split_authority is None:
                    raise H40GuardError(
                        H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                        "WF restore lacks predecessor/result/split authority",
                    )
                reconstructed = service.authorize_wf_validation(
                    candidate_authority=prior,
                    evidence=evidence,
                    split_authority=split_authority,
                    validated_at_utc=receipt.validated_at_utc,
                    verified_at_utc=receipt.verified_at_utc,
                )
        elif isinstance(receipt, H40ConfirmationReadyReceipt):
            if prior is None or evidence is not None:
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    "confirmation-ready restore has invalid context",
                )
            reconstructed = service.authorize_confirmation_ready(
                wf_authority=prior,
                prepared_at_utc=receipt.prepared_at_utc,
            )
        elif isinstance(receipt, H40TerminationReceipt):
            if prior is None:
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    "termination restore lacks predecessor authority",
                )
            reconstructed = service.authorize_termination(
                prior_authority=prior,
                target_state=receipt.target_state,
                reason_code=receipt.reason_code,
                detail_message=receipt.detail_message,
                terminated_at_utc=receipt.terminated_at_utc,
                failure_evidence_hash=receipt.failure_evidence_hash,
                failure_evidence=evidence,
            )
        else:
            raise TypeError("unknown lifecycle receipt type")
        if (
            reconstructed.receipt_hash != receipt.receipt_sha256
            or reconstructed.receipt.to_dict() != receipt.to_dict()
            or reconstructed.run_authority_id != run_authority_id
        ):
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "cold-restored verifier result does not match persisted authorization",
            )
        return reconstructed

    def _get_committed_lineage(
        self,
        run_authority_id: str,
        committed_head: H40DurableRunHead,
    ) -> list[str]:
        _require_sha256(run_authority_id, "run_authority_id")
        if not isinstance(committed_head, H40DurableRunHead):
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "committed_head must be H40DurableRunHead",
            )
        _require_sha256(committed_head.head_receipt_hash, "head_receipt_hash")
        if committed_head.head_predecessor_receipt_hash is not None:
            _require_sha256(
                committed_head.head_predecessor_receipt_hash,
                "head_predecessor_receipt_hash",
            )

        curr_hash: str | None = committed_head.head_receipt_hash
        lineage: list[str] = []
        visited: set[str] = set()
        prev_source_state: str | None = None
        is_head = True

        while curr_hash is not None:
            if curr_hash in visited:
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    "cyclic committed lineage detected in durable store",
                )
            visited.add(curr_hash)
            if _SHA256_RE.fullmatch(curr_hash) is None:
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    f"invalid receipt hash format in lineage: '{curr_hash}'",
                )

            receipt_path = self._receipts_dir(run_authority_id) / f"{curr_hash}.json"
            if not receipt_path.is_file():
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    f"authoritative lineage receipt '{curr_hash}.json' not found in receipts directory",
                )

            try:
                raw_envelope = json.loads(receipt_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    f"failed to read lineage receipt '{curr_hash}'",
                ) from exc

            if not isinstance(raw_envelope, Mapping):
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    f"receipt in lineage '{curr_hash}' envelope must be a mapping",
                )

            _require_exact_keys(
                raw_envelope,
                frozenset({
                    "authority_context",
                    "bound_evidence",
                    "bound_evidence_sha256",
                    "receipt",
                    "receipt_sha256",
                }),
                "lifecycle envelope",
            )

            envelope_digest = raw_envelope.get("receipt_sha256")
            if envelope_digest != curr_hash:
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    f"envelope receipt_sha256 '{envelope_digest}' does not match expected '{curr_hash}'",
                )

            receipt_payload = raw_envelope.get("receipt")
            if not isinstance(receipt_payload, Mapping):
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    f"receipt in lineage '{curr_hash}' has invalid receipt object",
                )

            if canonical_sha256(receipt_payload) != curr_hash:
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    f"receipt in lineage '{curr_hash}' content hash mismatch",
                )

            schema_id = receipt_payload.get("receipt_schema_id")
            parser = _RECEIPT_PARSERS.get(str(schema_id))
            if parser is None:
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    f"unknown receipt schema '{schema_id}' in lineage '{curr_hash}'",
                )

            try:
                typed_receipt = parser(receipt_payload)
            except Exception as exc:
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    f"failed to parse typed receipt in lineage '{curr_hash}': {exc}",
                ) from exc

            if typed_receipt.receipt_sha256 != curr_hash:
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    f"recomputed typed receipt hash in lineage '{curr_hash}' mismatch",
                )

            if typed_receipt.run_authority_id != run_authority_id:
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    f"receipt in lineage '{curr_hash}' run_authority_id mismatch: "
                    f"'{typed_receipt.run_authority_id}' != '{run_authority_id}'",
                )

            # Determine receipt source and target states
            if isinstance(typed_receipt, H40DiscoveryAuthorizationReceipt):
                node_target_state = "H40_DISCOVERY"
                node_source_state = "H40_P1_SCAFFOLDED"
            elif isinstance(typed_receipt, H40CandidateLockReceipt):
                node_target_state = "H40_CANDIDATE_LOCKED"
                node_source_state = "H40_DISCOVERY"
            elif isinstance(typed_receipt, H40WFValidationReceipt):
                node_target_state = "H40_WALK_FORWARD_VALIDATED"
                node_source_state = "H40_CANDIDATE_LOCKED"
            elif isinstance(typed_receipt, H40ConfirmationReadyReceipt):
                node_target_state = "H40_CONFIRMATION_READY"
                node_source_state = "H40_WALK_FORWARD_VALIDATED"
            elif isinstance(typed_receipt, H40TerminationReceipt):
                node_target_state = typed_receipt.target_state
                node_source_state = typed_receipt.source_state
            else:
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    f"unexpected receipt type '{type(typed_receipt).__name__}' in lineage",
                )

            if (node_source_state, node_target_state) not in _ACCEPTED_TRANSITIONS:
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    f"transition '{node_source_state}' -> '{node_target_state}' in lineage is not accepted",
                )

            # Adjacency checks
            if is_head:
                if node_target_state != committed_head.head_state:
                    raise H40GuardError(
                        H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                        f"head receipt target state '{node_target_state}' does not match "
                        f"durable head state '{committed_head.head_state}'",
                    )
                if typed_receipt.upstream_receipt_hash != committed_head.head_predecessor_receipt_hash:
                    raise H40GuardError(
                        H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                        f"head receipt upstream hash '{typed_receipt.upstream_receipt_hash}' does not match "
                        f"durable head predecessor '{committed_head.head_predecessor_receipt_hash}'",
                    )
                is_head = False
            else:
                if node_target_state != prev_source_state:
                    raise H40GuardError(
                        H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                        f"lineage transition adjacency broken: predecessor target state '{node_target_state}' "
                        f"does not match successor source state '{prev_source_state}'",
                    )

            upstream = typed_receipt.upstream_receipt_hash
            if isinstance(typed_receipt, H40DiscoveryAuthorizationReceipt):
                if upstream is not None:
                    raise H40GuardError(
                        H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                        f"discovery genesis receipt '{curr_hash}' must have null upstream hash",
                    )
            else:
                if upstream is None:
                    raise H40GuardError(
                        H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                        f"non-genesis receipt '{curr_hash}' cannot have null upstream hash",
                    )
                if not isinstance(upstream, str) or _SHA256_RE.fullmatch(upstream) is None:
                    raise H40GuardError(
                        H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                        f"upstream receipt hash in lineage '{curr_hash}' is invalid: '{upstream}'",
                    )

            lineage.append(curr_hash)
            prev_source_state = node_source_state
            curr_hash = upstream

        if prev_source_state != "H40_P1_SCAFFOLDED":
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "committed lineage does not terminate at genesis state",
            )

        if committed_head.transition_sequence != len(lineage) - 1:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"committed lineage depth {len(lineage) - 1} does not match "
                f"durable head transition_sequence {committed_head.transition_sequence}",
            )

        return lineage

    def restore_authorization(
        self,
        run_authority_id: str,
        transition_key: str,
        *,
        service: H40LifecycleAuthorityService,
        resolver: H40LifecycleAuthorityResolver,
    ) -> VerifiedLifecycleAuthorization:
        """Cold-restore and reissue authority without a process-local prior object."""
        if not isinstance(resolver, H40LifecycleAuthorityResolver):
            raise TypeError("resolver must implement H40LifecycleAuthorityResolver")
        if resolver.synthetic_only != service.synthetic_test_mode:
            raise H40GuardError(
                H40ReasonCode.NOT_TESTABLE,
                "resolver authority mode does not match lifecycle service mode",
            )
        service._assert_current_anchors(require_controller=False)
        head = self.get_committed_run_head(run_authority_id)
        if head is None:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"no committed durable run head found for run '{run_authority_id}'",
            )
        lineage = self._get_committed_lineage(run_authority_id, head)
        target_path = self._find_receipt_path(run_authority_id, transition_key)
        try:
            raw_target = json.loads(target_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "invalid lifecycle artifact",
            ) from exc
        if not isinstance(raw_target, Mapping):
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "lifecycle envelope must be an object",
            )
        target_hash = raw_target.get("receipt_sha256")
        target_payload = raw_target.get("receipt")
        if (
            not isinstance(target_hash, str)
            or not isinstance(target_payload, Mapping)
            or canonical_sha256(target_payload) != target_hash
            or target_hash not in lineage
        ):
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"target receipt '{target_hash}' is not in committed run head lineage",
            )
        return self._cold_restore_authorization(
            run_authority_id,
            transition_key,
            service=service,
            resolver=resolver,
            visited_receipts=frozenset(),
        )


__all__ = [
    "ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH",
    "ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH",
    "DISCOVERY_PROVENANCE_CONTRACT_HASH",
    "DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH",
    "EXPECTED_LIFECYCLE_CHILD_HASHES",
    "EXPECTED_LIFECYCLE_GOVERNANCE_AUTHORITY_HASH",
    "EXPECTED_LIFECYCLE_SEMANTIC_ROOT_HASH",
    "H40ActiveSourceEvidenceEntry",
    "H40CandidateLockReceipt",
    "H40CandidateResultEntry",
    "H40CandidateVerification",
    "H40ConfirmationReadyReceipt",
    "H40DiscoveryAuthorizationReceipt",
    "H40DiscoveryAuthorizationReceiptV2",
    "H40DiscoveryResultEvidence",
    "H40DiscoveryRunGrant",
    "H40DurableRunHead",
    "H40ExpectedSplitAuthority",
    "H40ExpectedWFFold",
    "H40LifecycleArtifactStore",
    "H40LifecycleAuthorityResolver",
    "H40LifecycleAuthorityService",
    "H40LifecycleEvidenceVerifier",
    "H40LifecycleImplementationAuthority",
    "H40LifecyclePersistenceContext",
    "H40LifecyclePersistenceContextV1",
    "H40P3ControllerAuthority",
    "H40RequiredTestCIEvidenceIdentity",
    "H40RunAuthority",
    "H40RuntimeRosterEntry",
    "H40RuntimeSnapshotSeal",
    "H40RuntimeSourceSplitAttestation",
    "H40SourceAuthorityStateEntry",
    "H40SyntheticAuthorityResolver",
    "H40SyntheticEvidenceVerifier",
    "H40TerminationReceipt",
    "H40WFFoldResultEntry",
    "H40WFValidationReceipt",
    "H40WFValidationResultEvidence",
    "VerifiedLifecycleAuthorization",
    "compute_lifecycle_child_hashes",
    "compute_lifecycle_governance_authority_hash",
    "compute_lifecycle_semantic_root_hash",
    "derive_expected_wf_authority",
    "lifecycle_governance_authority_object",
    "lifecycle_semantic_contracts",
    "lifecycle_semantic_root_preimage",
    "materialize_runtime_source_split_authority",
    "normalize_audit_timestamp",
    "verify_runtime_source_split_authority",
]
