"""Offline execution environment authority and preflight verification for Track B.

Implements:
- EXECUTION_ENVIRONMENT_AUTHORITY_V1 schema
- CURRENT_EXECUTION_POLICY = RESEARCH_DISABLED_V1
- ACCEPTED_EXECUTION_WRITE_AUTHORITY = None
- Offline preflight validation P01 through P16
- Strict environment/account/plan/order compound binding
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from ..config import AppConfig, ExecutionConfig
from .guard import ExecutionBlocked
from .models import ClosePlan, ExecutionMode, ExecutionPlan, OrderReceipt

CURRENT_EXECUTION_POLICY: str = "RESEARCH_DISABLED_V1"
ACCEPTED_EXECUTION_WRITE_AUTHORITY: None = None

CANONICAL_ENVIRONMENT_MAP: dict[ExecutionMode, str] = {
    ExecutionMode.PAPER: "local_paper",
    ExecutionMode.TESTNET: "binance_usdm_testnet",
    ExecutionMode.LIVE: "binance_usdm_live",
}

CANONICAL_CREDENTIAL_NAMESPACE_MAP: dict[ExecutionMode, str] = {
    ExecutionMode.PAPER: "NONE",
    ExecutionMode.TESTNET: "BINANCE_TESTNET",
    ExecutionMode.LIVE: "BINANCE_LIVE",
}

CANONICAL_URL_MAP: dict[str, str] = {
    "binance_usdm_testnet": "https://testnet.binancefuture.com",
    "binance_usdm_live": "https://fapi.binance.com",
    "local_paper": "local://paper",
}

CANONICAL_ACCOUNT_AUTHORITY_MAP: dict[ExecutionMode, str] = {
    ExecutionMode.PAPER: "DEFAULT_PAPER_ACCOUNT",
    ExecutionMode.TESTNET: "BINANCE_TESTNET_DEFAULT",
    ExecutionMode.LIVE: "BINANCE_LIVE_DEFAULT",
}


class ActionClassification(StrEnum):
    ENTRY_SUBMIT = "ENTRY_SUBMIT"
    RECONCILE = "RECONCILE"
    RECONCILE_OPEN_PLANS = "RECONCILE_OPEN_PLANS"
    PREPARE_CLOSE = "PREPARE_CLOSE"
    SUBMIT_CLOSE = "SUBMIT_CLOSE"
    CANCEL_ENTRY = "CANCEL_ENTRY"
    ORDER_QUERY = "ORDER_QUERY"
    POSITION_QUERY = "POSITION_QUERY"
    ACCOUNT_QUERY = "ACCOUNT_QUERY"


def normalize_rest_base_url(url: str) -> str:
    cleaned = url.strip()
    parsed = urllib.parse.urlsplit(cleaned)
    if not parsed.scheme:
        return cleaned.rstrip("/")
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme.lower()}://{netloc}{path}"


@dataclass(frozen=True)
class ExecutionEnvironmentAuthority:
    schema_id: str = "EXECUTION_ENVIRONMENT_AUTHORITY_V1"
    mode: ExecutionMode = ExecutionMode.DISABLED
    exchange_family: str = "BINANCE_USDM"
    environment_id: str = "disabled"
    normalized_rest_base_url: str = ""
    credential_namespace_id: str = "NONE"
    account_authority_id: str = "DEFAULT"
    position_mode_assumption: str = "ONE_WAY"
    margin_mode_assumption: str = "ISOLATED"

    @classmethod
    def from_config(
        cls,
        config: ExecutionConfig | AppConfig,
        *,
        base_url: str | None = None,
        account_authority_id: str | None = None,
    ) -> ExecutionEnvironmentAuthority:
        exec_cfg = config.execution if isinstance(config, AppConfig) else config
        mode = ExecutionMode(exec_cfg.mode)
        if mode == ExecutionMode.DISABLED:
            return cls(
                mode=mode,
                environment_id="disabled",
                normalized_rest_base_url="",
                credential_namespace_id="NONE",
                account_authority_id=account_authority_id or "DISABLED",
                position_mode_assumption=exec_cfg.position_mode,
                margin_mode_assumption=exec_cfg.margin_type,
            )

        env_id = CANONICAL_ENVIRONMENT_MAP[mode]
        cred_ns = CANONICAL_CREDENTIAL_NAMESPACE_MAP[mode]

        if base_url is not None:
            resolved_url = normalize_rest_base_url(base_url)
        elif mode == ExecutionMode.TESTNET:
            resolved_url = normalize_rest_base_url(exec_cfg.testnet_base_url)
        elif mode == ExecutionMode.LIVE:
            data_url = (
                config.data.rest_base_url
                if isinstance(config, AppConfig)
                else "https://fapi.binance.com"
            )
            resolved_url = normalize_rest_base_url(data_url)
        else:
            resolved_url = "local://paper"

        expected_url = normalize_rest_base_url(CANONICAL_URL_MAP[env_id])
        if mode in {ExecutionMode.TESTNET, ExecutionMode.LIVE} and resolved_url != expected_url:
            raise ExecutionBlocked(
                f"endpoint/environment mismatch: '{resolved_url}' is not allowlisted for '{env_id}'"
            )

        resolved_account = (
            account_authority_id
            or getattr(exec_cfg, "account_authority_id", None)
            or CANONICAL_ACCOUNT_AUTHORITY_MAP[mode]
        )

        return cls(
            mode=mode,
            environment_id=env_id,
            normalized_rest_base_url=resolved_url,
            credential_namespace_id=cred_ns,
            account_authority_id=resolved_account,
            position_mode_assumption=exec_cfg.position_mode,
            margin_mode_assumption=exec_cfg.margin_type,
        )


def validate_execution_environment_preflight(
    plan: ExecutionPlan | ClosePlan,
    config: ExecutionConfig | AppConfig,
    *,
    receipt: OrderReceipt | dict[str, Any] | None = None,
    action: ActionClassification | str | None = None,
    now_ms: int | None = None,
    account_authority_id: str | None = None,
    base_url: str | None = None,
) -> ExecutionEnvironmentAuthority:
    """Shared offline execution environment authority preflight (P01-P16)."""
    # P01 & P02: Verify plan type
    if not isinstance(plan, (ExecutionPlan, ClosePlan)):
        raise ExecutionBlocked(f"unrecognized plan type: {type(plan).__name__}")

    # P03 & P04: Recompute plan hash and require exact equality
    if plan.calculated_hash() != plan.plan_hash:
        raise ExecutionBlocked("execution plan hash mismatch")

    # P05: Verify plan kind/status and expiration
    if action != ActionClassification.RECONCILE and now_ms is not None and now_ms > plan.expires_at_ms:
        raise ExecutionBlocked("execution plan expired")

    # P06: Resolve persisted authority fields from plan
    p_mode = plan.mode
    p_env = getattr(plan, "execution_environment_id", "")
    p_ns = getattr(plan, "credential_namespace_id", "")
    p_acct = getattr(plan, "account_authority_id", "")

    # Legacy testnet/live plan without V1 environment authority must fail closed
    if p_mode in {ExecutionMode.TESTNET, ExecutionMode.LIVE} and (not p_env or not p_ns or not p_acct):
        raise ExecutionBlocked("old testnet/live plan without V1 environment authority fails closed")

    # P07: Derive current configured offline environment authority
    curr_auth = ExecutionEnvironmentAuthority.from_config(
        config,
        base_url=base_url,
        account_authority_id=account_authority_id,
    )

    # P08: Require exact persisted/current equality
    if p_mode != curr_auth.mode:
        raise ExecutionBlocked(
            f"plan mode '{p_mode.value}' does not match current execution mode '{curr_auth.mode.value}'"
        )
    if p_env != curr_auth.environment_id:
        raise ExecutionBlocked(
            f"environment mismatch: plan '{p_env}' != configured '{curr_auth.environment_id}'"
        )
    if p_ns != curr_auth.credential_namespace_id:
        raise ExecutionBlocked(
            f"credential namespace mismatch: plan '{p_ns}' != configured '{curr_auth.credential_namespace_id}'"
        )
    if p_acct != curr_auth.account_authority_id:
        raise ExecutionBlocked(
            f"account authority mismatch: plan '{p_acct}' != configured '{curr_auth.account_authority_id}'"
        )

    # P09 & P10: If order receipt is supplied, require receipt plan_hash equality
    if receipt is not None:
        if isinstance(receipt, dict):
            r_plan_hash = receipt.get("plan_hash", "")
            r_env = receipt.get("execution_environment_id", "")
            r_ns = receipt.get("credential_namespace_id", "")
            r_acct = receipt.get("account_authority_id", "")
            r_symbol = receipt.get("symbol", "")
            r_mode_raw = receipt.get("mode", "")
            r_mode = r_mode_raw if isinstance(r_mode_raw, str) else getattr(r_mode_raw, "value", str(r_mode_raw))
        else:
            r_plan_hash = receipt.plan_hash
            r_env = receipt.execution_environment_id
            r_ns = receipt.credential_namespace_id
            r_acct = receipt.account_authority_id
            r_symbol = receipt.symbol
            r_mode = receipt.mode.value if isinstance(receipt.mode, ExecutionMode) else str(receipt.mode)

        if r_plan_hash != plan.plan_hash:
            raise ExecutionBlocked("foreign plan receipt: receipt plan_hash does not match plan")

        # P11: Require receipt environment/account/credential namespace == plan/current authority
        if r_env != curr_auth.environment_id:
            raise ExecutionBlocked(
                f"foreign-environment order receipt: receipt '{r_env}' != current '{curr_auth.environment_id}'"
            )
        if r_ns != curr_auth.credential_namespace_id:
            raise ExecutionBlocked(
                f"receipt credential namespace mismatch: receipt '{r_ns}' != current '{curr_auth.credential_namespace_id}'"
            )
        if r_acct != curr_auth.account_authority_id:
            raise ExecutionBlocked(
                f"receipt account authority mismatch: receipt '{r_acct}' != current '{curr_auth.account_authority_id}'"
            )
        if r_mode != curr_auth.mode.value:
            raise ExecutionBlocked(
                f"receipt mode mismatch: receipt '{r_mode}' != current '{curr_auth.mode.value}'"
            )

        # P12: Require receipt symbol == plan symbol
        if r_symbol and r_symbol != plan.symbol:
            raise ExecutionBlocked(f"wrong symbol on receipt: '{r_symbol}' != '{plan.symbol}'")

    # Assumption checks (ONE_WAY and ISOLATED required)
    if curr_auth.position_mode_assumption != "ONE_WAY":
        raise ExecutionBlocked(
            f"position mode assumption mismatch: '{curr_auth.position_mode_assumption}' != 'ONE_WAY'"
        )
    if curr_auth.margin_mode_assumption != "ISOLATED":
        raise ExecutionBlocked(
            f"margin mode assumption mismatch: '{curr_auth.margin_mode_assumption}' != 'ISOLATED'"
        )

    # P13: Classify requested action
    classified_action = ActionClassification(action) if action else None

    # P14 & P15: Under RESEARCH_DISABLED_V1, all signed exchange capabilities fail closed
    if curr_auth.mode == ExecutionMode.DISABLED:
        raise ExecutionBlocked("execution.mode=disabled")
    if curr_auth.mode != ExecutionMode.PAPER:
        raise ExecutionBlocked(
            f"RESEARCH_DISABLED_V1: signed exchange execution is not authorized "
            f"(policy={CURRENT_EXECUTION_POLICY}, write_authority={ACCEPTED_EXECUTION_WRITE_AUTHORITY}, "
            f"action={classified_action})"
        )

    # P16: Paper mode passed all local verification gates; signed client remains unreachable
    return curr_auth
