"""Deterministic S3 Plan A/B/C gate, funding-weight policy checks, and 3-file patch diff audit."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path

from quant_personal_live_public_b5.approval import Scope, verify_envelope
from quant_personal_live_public_b5.contract import (
    AUTHORITY,
    BASE_MAX_REQUESTS,
    BASE_MAX_WEIGHT,
    CONTRACT,
    FUNDING,
    INTERVALS,
    ROUTES,
    SYMBOL_ORDER,
    TASK,
    PublicRequest,
    bounded_int,
    digest,
    sha_text,
)
from quant_personal_live_public_b5.offline import PROSPECTIVE_CUTOFF_MS
from quant_personal_live_public_b5.stages import (
    CANARY_ROUTES,
    SCOPE_V2,
    STAGE_CONTRACT,
    TIMEOUT_PROFILE,
    ZERO_RETRY_PROFILE,
    market_floor,
    market_requests,
)
from quant_personal_public_b1.policy import SourceBlocked, require
from quant_personal_public_bridge_b4.routes import OI_HISTORY, QUOTE

WORKROOT = Path(__file__).resolve().parents[1]
REPO = WORKROOT.parents[1]
H2A_ROOT = REPO / "workspaces/lt-v080-sol62-h2a-b5-phaseb-activation-01"
S3_MATRIX_PATH = REPO / "workspaces/lt-v080-sol62-s3-market-offline-readiness-01/S3_REQUEST_BUDGET_MATRIX.json"
PATCH_PATH = REPO / "workspaces/lt-v080-sol62-wsl2-local-runtime-readiness-01/proposals/H2A_SIGNED_ZERO_RETRY_V2.patch"

ALLOWED_PATCHED_SRC_FILES = frozenset({"collection.py", "ledger.py", "stages.py"})
CANDIDATE_VERSION = "0.8.0b5.post4"
CANDIDATE_PACKAGE = "quant-personal-live-public-b5"

FORBIDDEN_DEBIT_SUBSTITUTES = {
    "funding_family_cap_500_per_5min": "500/5min/IP is a shared family request-count cap, NOT a numeric general REQUEST_WEIGHT debit.",
    "fundingInfo_general_ip_weight_0": "/fapi/v1/fundingInfo general IP weight 0 does NOT transfer to /fapi/v1/fundingRate.",
    "premiumIndex_weight_1": "/fapi/v1/premiumIndex per-symbol weight 1 does NOT transfer to /fapi/v1/fundingRate.",
    "header_delta_inference": "Observed short-window X-MBX-USED-WEIGHT deltas cannot establish authoritative vendor debit.",
    "fixture_assumption_1": "Offline fixture synthetic debit 1 is QA-only and establishes zero vendor authority.",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def audit_source_diff() -> tuple[dict, str]:
    """Verify isolated src/ differs from H2-A ONLY in the exact 3 patched files and hunks."""
    h2a_pkg = H2A_ROOT / "src/quant_personal_live_public_b5"
    cand_pkg = WORKROOT / "src/quant_personal_live_public_b5"
    h2a_files = sorted(p.relative_to(h2a_pkg).as_posix() for p in h2a_pkg.rglob("*") if p.is_file())
    cand_files = sorted(p.relative_to(cand_pkg).as_posix() for p in cand_pkg.rglob("*") if p.is_file())
    require(h2a_files == cand_files, "SOURCE_FILE_INVENTORY_MISMATCH")

    changed = []
    unchanged = []
    diff_chunks = []
    file_hashes = {}
    for rel in cand_files:
        orig_bytes = (h2a_pkg / rel).read_bytes()
        cand_bytes = (cand_pkg / rel).read_bytes()
        file_hashes[rel] = {
            "h2a_post1_sha256": sha256_bytes(orig_bytes),
            "candidate_post4_sha256": sha256_bytes(cand_bytes),
            "changed": orig_bytes != cand_bytes,
        }
        if orig_bytes != cand_bytes:
            changed.append(rel)
            lines = list(
                difflib.unified_diff(
                    orig_bytes.decode("utf-8").splitlines(keepends=True),
                    cand_bytes.decode("utf-8").splitlines(keepends=True),
                    fromfile=f"a/src/quant_personal_live_public_b5/{rel}",
                    tofile=f"b/src/quant_personal_live_public_b5/{rel}",
                )
            )
            diff_chunks.append("".join(lines))
        else:
            unchanged.append(rel)

    require(set(changed) == ALLOWED_PATCHED_SRC_FILES, "CONTRACT_FORK_BEYOND_THREE_FILES", str(changed))
    generated_patch = "".join(diff_chunks)
    pinned_patch = PATCH_PATH.read_text(encoding="utf-8")
    require(generated_patch == pinned_patch, "SOURCE_DIFF_DOES_NOT_MATCH_PINNED_PATCH")

    audit = {
        "schema": "S3_SOURCE_DIFF_AUDIT_V1",
        "h2a_source_lineage": "workspaces/lt-v080-sol62-h2a-b5-phaseb-activation-01",
        "pinned_patch_path": "workspaces/lt-v080-sol62-wsl2-local-runtime-readiness-01/proposals/H2A_SIGNED_ZERO_RETRY_V2.patch",
        "pinned_patch_sha256": sha256_bytes(PATCH_PATH.read_bytes()),
        "generated_diff_sha256": sha256_bytes(generated_patch.encode("utf-8")),
        "byte_exact_match_with_pinned_patch": True,
        "changed_src_files": changed,
        "unchanged_src_file_count": len(unchanged),
        "total_src_file_count": len(cand_files),
        "src_file_hashes": file_hashes,
    }
    return audit, generated_patch


def validate_s3_v2_candidate_scope(raw_scope: dict, roots, *, envelope: dict | None = None, release: str | None = None, wall_ms: int | None = None) -> Scope:
    """Strict release-bound S3 Plan A scope validator enforcing mandatory ZERO_RETRY_PROFILE.

    This gate is stricter than legacy V1 regression parsing: any S3 Plan A scope MUST
    carry H2A_OWNER_PUBLIC_SCOPE_V2, market != None, timeout_profile == ZERO_RETRY_PROFILE,
    and a valid documented integer funding debit with official evidence SHA256.
    """
    require(type(raw_scope) is dict and raw_scope.get("schema") == SCOPE_V2, "S3_V2_SCOPE_SCHEMA_REQUIRED")
    plan_raw = raw_scope.get("activation_plan")
    require(type(plan_raw) is dict, "S3_ACTIVATION_PLAN_REQUIRED")
    require(plan_raw.get("market") is not None, "S2_ONLY_GRANT_CANNOT_ENABLE_S3")
    profile = plan_raw.get("timeout_profile")
    require(profile is not None and profile != "", "S3_TIMEOUT_PROFILE_MISSING")
    require(profile != TIMEOUT_PROFILE, "S3_LEGACY_V1_PROFILE_DENIED")
    require(profile == ZERO_RETRY_PROFILE, "S3_ZERO_RETRY_PROFILE_REQUIRED")
    funding = raw_scope.get("funding")
    require(type(funding) is dict, "FUNDING_WEIGHT_UNRESOLVED")
    debit = funding.get("documented_numeric_ip_weight")
    evidence_sha = funding.get("official_evidence_sha256")
    require(bounded_int(debit, 0, BASE_MAX_WEIGHT) and sha_text(evidence_sha), "FUNDING_WEIGHT_UNRESOLVED")
    # Necessary arithmetic ceiling under candidate 64-weight cap: 39 + 3*d <= 64 => d <= 8
    count, known, funding_calls = market_floor()
    combined_weight = 2 + known + funding_calls * debit
    require(combined_weight <= BASE_MAX_WEIGHT, "PLAN_A_WEIGHT_EXCEEDS_CANDIDATE_CAP")
    if envelope is not None:
        require(release is not None and wall_ms is not None, "APPROVAL_CONTEXT_REQUIRED")
        approval = verify_envelope(envelope, raw_scope, roots, release, wall_ms)
        scope = approval.scope
    else:
        scope = Scope.parse(raw_scope, roots)
    require(scope.stage_plan is not None and scope.stage_plan.market_allowed
            and scope.stage_plan.market_retry_limit == 0, "S3_ZERO_RETRY_ENFORCEMENT_REQUIRED")
    return scope


def evaluate_plan_a_funding_gate(
    d,
    official_evidence_sha256=None,
    *,
    external_official_verified: bool = False,
    substitute_source: str | None = None,
) -> dict:
    """Evaluate Plan A (39 GET, 39 + 3*d weight) funding-weight gate. Never invents d."""
    if substitute_source is not None:
        return {
            "plan": "A_FULL",
            "decision": "DENIED_FORBIDDEN_DEBIT_SUBSTITUTE",
            "reason": FORBIDDEN_DEBIT_SUBSTITUTES.get(substitute_source, "UNAUTHORITATIVE_DEBIT_SUBSTITUTE"),
            "live_qualification_allowed": False,
            "signable_combined_weight": None,
        }
    if type(d) is not int or d < 0:
        return {
            "plan": "A_FULL",
            "decision": "FUNDING_WEIGHT_UNRESOLVED",
            "reason": "Historical /fapi/v1/fundingRate general-IP numeric debit d is unknown/null/invalid.",
            "live_qualification_allowed": False,
            "signable_combined_weight": None,
        }
    combined_weight = 39 + 3 * d
    market_weight = 37 + 3 * d
    if combined_weight > BASE_MAX_WEIGHT:
        return {
            "plan": "A_FULL",
            "decision": "PLAN_A_WEIGHT_EXCEEDS_CANDIDATE_CAP",
            "reason": f"39 + 3*{d} = {combined_weight} exceeds candidate 64-weight ceiling (necessary arithmetic bound d <= 8).",
            "arithmetic_fits_64_cap": False,
            "computed_combined_weight": combined_weight,
            "computed_market_weight": market_weight,
            "live_qualification_allowed": False,
            "signable_combined_weight": None,
        }
    if not sha_text(official_evidence_sha256) or not external_official_verified:
        return {
            "plan": "A_FULL",
            "decision": "FUNDING_WEIGHT_UNRESOLVED_MISSING_OFFICIAL_EVIDENCE",
            "reason": "Arithmetic check 39 + 3*d <= 64 is necessary only; missing verified official Binance endpoint numeric debit evidence.",
            "arithmetic_fits_64_cap": True,
            "computed_combined_weight": combined_weight,
            "computed_market_weight": market_weight,
            "live_qualification_allowed": False,
            "signable_combined_weight": None,
        }
    return {
        "plan": "A_FULL",
        "decision": "SYNTHETIC_GATE_INPUT_COMPLETE_NOT_LIVE_AUTHORIZED",
        "arithmetic_fits_64_cap": True,
        "computed_combined_weight": combined_weight,
        "computed_market_weight": market_weight,
        "live_qualification_allowed": False,
        "signable_combined_weight": None,
        "note": "Offline candidate has no production trust roots and no Owner+Controller live grant.",
    }


def evaluate_plan_b_diagnostic(cutoff_ms: int = PROSPECTIVE_CUTOFF_MS) -> dict:
    """Compute Plan B (36 combined GET, 39 known weight) diagnostic-only boundary."""
    canary = [PublicRequest(path, {}) for path in CANARY_ROUTES]
    full_market = list(market_requests(cutoff_ms))
    full_all = canary + full_market
    omitted_slots = [idx for idx, req in enumerate(full_all, 1) if req.route == FUNDING]
    plan_b_all = [req for req in full_all if req.route != FUNDING]
    plan_b_market = [req for req in full_market if req.route != FUNDING]
    combined_weight = sum(req.validate()[0] for req in plan_b_all)
    market_weight = sum(req.validate()[0] for req in plan_b_market)
    funding_family_calls = sum(1 for req in plan_b_all if req.route == FUNDING)
    oi_history_family_calls = sum(1 for req in plan_b_all if req.route == OI_HISTORY)
    return {
        "plan": "B_DIAGNOSTIC_ONLY",
        "status": "DIAGNOSTIC_ONLY_UNAPPROVED_FOR_LIVE",
        "combined_requests": len(plan_b_all),
        "combined_known_general_ip_weight": combined_weight,
        "market_stage_requests": len(plan_b_market),
        "market_stage_known_general_ip_weight": market_weight,
        "omitted_plan_a_slots": omitted_slots,
        "omitted_route": FUNDING,
        "omission_reason": "FUNDING_HISTORY_DEFERRED",
        "funding_family_requests_5min": funding_family_calls,
        "oi_history_family_requests_5min": oi_history_family_calls,
        "strategy_status": "NOT_EVALUATED",
        "market_cards": 0,
        "funding_cost": None,
        "net_r": None,
        "decision_grade": False,
        "can_pass_b2_b4_full_market_qualification": False,
        "can_publish_market_card": False,
        "can_send_actionable_notice": False,
    }


def build_plan_gate_document(candidate_wheel_sha256: str | None = None) -> dict:
    s3_matrix = json.loads(S3_MATRIX_PATH.read_text(encoding="utf-8"))
    count, known, funding_calls = market_floor()
    assert (count, known, funding_calls) == (37, 37, 3)

    plan_a_matrix = s3_matrix["plans"]["A_FULL"]
    plan_b_matrix = s3_matrix["plans"]["B_DIAGNOSTIC_ONLY"]
    s2_matrix = s3_matrix["plans"]["S2_CANARY_ONLY"]

    assert plan_a_matrix["combined"] == {
        "requests": 39,
        "known_general_ip_weight": 39,
        "unknown_general_ip_debits": 3,
        "nominal_general_ip_weight": None,
    }
    assert plan_b_matrix["combined"] == {
        "requests": 36,
        "known_general_ip_weight": 39,
        "unknown_general_ip_debits": 0,
        "nominal_general_ip_weight": 39,
    }
    assert s2_matrix["combined"] == {
        "requests": 2,
        "known_general_ip_weight": 2,
        "unknown_general_ip_debits": 0,
        "nominal_general_ip_weight": 2,
    }

    return {
        "schema": "S3_PLAN_A_B_C_AND_FUNDING_WEIGHT_GATE_V1",
        "task_id": "V080-NEON-S3-RELEASE-BOUND-ZERO-RETRY-OFFLINE-20261123",
        "classification": "OFFLINE_RELEASE_BOUND_CANDIDATE_NOT_AUTHORIZED",
        "live_authorization": "NOT_AUTHORIZED",
        "production_trust_roots_provisioned": False,
        "candidate_release": {
            "package": CANDIDATE_PACKAGE,
            "version": CANDIDATE_VERSION,
            "wheel_filename": f"quant_personal_live_public_b5-{CANDIDATE_VERSION}-py3-none-any.whl",
            "wheel_sha256": candidate_wheel_sha256,
            "expected_scope_schema": SCOPE_V2,
            "expected_stage_contract": STAGE_CONTRACT,
            "mandatory_s3_timeout_profile": ZERO_RETRY_PROFILE,
            "legacy_v1_timeout_profile": TIMEOUT_PROFILE,
            "authority": AUTHORITY,
            "endpoint_contract": CONTRACT,
            "task_binding": TASK,
            "symbols": list(SYMBOL_ORDER),
            "frames": list(INTERVALS.keys()),
            "routes": list(ROUTES),
            "release_one_shot_ceiling": {
                "requests": BASE_MAX_REQUESTS,
                "weight": BASE_MAX_WEIGHT,
            },
        },
        "s2_s3_separation": {
            "s2_canary_only_requests": 2,
            "s2_canary_only_weight": 2,
            "s2_only_grant_can_enable_s3": False,
            "s2_v2_owner_foreground_ceremony_authorizes_s3": False,
            "s3_requires_distinct_fresh_owner_and_controller_dual_approval": True,
            "s3_requires_same_run_canary_milestone": True,
            "canary_routes_order": list(CANARY_ROUTES),
        },
        "funding_weight_gate": {
            "endpoint": FUNDING,
            "method": "GET",
            "parameter_shape": {"symbol": "SINGLE_SYMBOL", "window_ms": 259_200_000, "limit": 256, "end_inclusive": True},
            "per_request_general_ip_debit_d": None,
            "status": "FUNDING_WEIGHT_UNRESOLVED",
            "plan_a_combined_weight_formula": "39 + 3 * d",
            "plan_a_market_stage_weight_formula": "37 + 3 * d",
            "candidate_64_cap_necessary_arithmetic_bound": {
                "expression": "39 + 3 * d <= 64  <=>  d <= 8 (for non-negative integer d)",
                "max_integer_d_fitting_64_cap": 8,
                "weight_at_d_8": 63,
                "weight_at_d_9": 66,
                "is_necessary_arithmetic_bound_only": True,
                "establishes_vendor_data": False,
            },
            "forbidden_substitutes": FORBIDDEN_DEBIT_SUBSTITUTES,
            "evidence_required_to_close": (
                "Official Binance-published USD-M endpoint specification or attributable written Binance API "
                "clarification quantifying per-request general REQUEST_WEIGHT for GET /fapi/v1/fundingRate "
                "(single symbol, 72h window, limit 256), archived with exact text, date, reference and SHA-256 "
                "and independently verified by Controller 0-C."
            ),
        },
        "plans": {
            "A_FULL": {
                "scope": "A_FULL",
                "authorization": "NOT_AUTHORIZED",
                "gate_status": "FUNDING_WEIGHT_UNRESOLVED",
                "mandatory_profile_for_future_s3": ZERO_RETRY_PROFILE,
                "retries_permitted": 0,
                "canary_stage": {"requests": 2, "known_general_ip_weight": 2},
                "market_stage": {
                    "requests": 37,
                    "known_general_ip_weight": 37,
                    "unknown_general_ip_debits": 3,
                    "weight_expression": "37 + 3 * d",
                    "signable_weight": None,
                },
                "combined": {
                    "requests": 39,
                    "known_general_ip_weight": 39,
                    "unknown_general_ip_debits": 3,
                    "weight_expression": "39 + 3 * d",
                    "signable_weight": None,
                },
                "five_minute_family_usage": {"funding": 3, "oi_history": 3},
                "quote_header_exception": {
                    "route": QUOTE,
                    "policy": "BOOK_TICKER_WEIGHT_HEADER_UNRELIABLE",
                    "local_reservation_still_charged": True,
                },
                "decision_grade_in_offline_candidate": False,
                "live_eligible": False,
            },
            "B_DIAGNOSTIC_ONLY": evaluate_plan_b_diagnostic(PROSPECTIVE_CUTOFF_MS),
            "C_RESEARCH_ONLY": {
                "plan": "C_RESEARCH_ONLY",
                "status": "COST_UNVERIFIED_RESEARCH_ONLY",
                "authorization": "NOT_AUTHORIZED",
                "live_eligible": False,
                "alternative_cost_model_enabled": False,
                "can_publish_market_card": False,
                "can_modify_frozen_v1_enum": False,
                "requires": (
                    "Independently accepted versioned source/cost contract, authoritative settlement event-count, "
                    "rate-bound and notional proof (or certified zero-crossing proof), synthetic admission acceptance, "
                    "and separate Owner+Controller policy approval."
                ),
            },
        },
        "upstream_references": {
            "s3_request_budget_matrix": {
                "path": "workspaces/lt-v080-sol62-s3-market-offline-readiness-01/S3_REQUEST_BUDGET_MATRIX.json",
                "sha256": sha256_bytes(S3_MATRIX_PATH.read_bytes()),
            },
            "pinned_three_file_patch": {
                "path": "workspaces/lt-v080-sol62-wsl2-local-runtime-readiness-01/proposals/H2A_SIGNED_ZERO_RETRY_V2.patch",
                "sha256": sha256_bytes(PATCH_PATH.read_bytes()),
            },
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-diff", action="store_true")
    parser.add_argument("--write-patch", type=Path)
    parser.add_argument("--emit-gate", action="store_true")
    parser.add_argument("--wheel-sha256")
    args = parser.parse_args(argv)

    if args.audit_diff:
        audit, patch_text = audit_source_diff()
        if args.write_patch is not None:
            args.write_patch.write_text(patch_text, encoding="utf-8", newline="\n")
        print(json.dumps(audit, indent=2, sort_keys=True))
        return 0
    if args.emit_gate:
        doc = build_plan_gate_document(candidate_wheel_sha256=args.wheel_sha256)
        print(json.dumps(doc, indent=2, sort_keys=True))
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
