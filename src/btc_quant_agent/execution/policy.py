"""Execution capability policy for Live V1.

Frozen authority boundaries:
SHADOW:      ALLOWED
DRY_RUN:     ALLOWED
PAPER:       ALLOWED
TESTNET:     ALLOWED after deterministic validation
LIVE:        BLOCKED (permanently, no bypass)
AUTONOMOUS:  BLOCKED
"""

from __future__ import annotations

from enum import StrEnum

from .guard import ExecutionBlocked

LIVE_WRITE_AUTHORITY: None = None


class CapabilityMode(StrEnum):
    SHADOW = "SHADOW"
    DRY_RUN = "DRY_RUN"
    PAPER = "PAPER"
    TESTNET = "TESTNET"
    LIVE = "LIVE"
    AUTONOMOUS = "AUTONOMOUS"


class ExecutionCapabilityPolicyV1:
    POLICY_NAME: str = "EXECUTION_CAPABILITY_POLICY_V1"
    LIVE_WRITE_AUTHORITY: None = None

    ALLOWED_CAPABILITIES: frozenset[str] = frozenset({"SHADOW", "DRY_RUN", "PAPER", "TESTNET"})
    BLOCKED_CAPABILITIES: frozenset[str] = frozenset({"LIVE", "AUTONOMOUS"})

    @classmethod
    def is_allowed(cls, mode: str) -> bool:
        normalized = mode.upper()
        if normalized in cls.BLOCKED_CAPABILITIES:
            return False
        return normalized in cls.ALLOWED_CAPABILITIES

    @classmethod
    def check_capability(
        cls,
        mode: str,
        action: str = "ORDER_SUBMIT",
        *,
        env_id: str = "",
        cred_ns: str = "",
        rest_url: str = "",
    ) -> None:
        normalized = mode.upper()

        if normalized in cls.BLOCKED_CAPABILITIES or normalized == "LIVE":
            raise ExecutionBlocked(
                f"LIVE execution is permanently blocked: LIVE_WRITE_AUTHORITY is NONE "
                f"(policy={cls.POLICY_NAME}, action={action})"
            )

        if normalized == "TESTNET":
            # Testnet and Live credential and endpoint isolation
            if env_id and env_id != "binance_usdm_testnet":
                raise ExecutionBlocked(f"environment mismatch for TESTNET: '{env_id}'")
            if cred_ns and cred_ns != "BINANCE_TESTNET":
                raise ExecutionBlocked(f"credential namespace mismatch for TESTNET: '{cred_ns}'")
            if rest_url:
                cleaned_url = rest_url.rstrip("/").lower()
                if cleaned_url != "https://testnet.binancefuture.com":
                    raise ExecutionBlocked(
                        f"endpoint/environment mismatch: '{rest_url}' is not allowlisted for TESTNET"
                    )
            return

        if normalized in {"PAPER", "DRY_RUN", "SHADOW"}:
            if cred_ns and cred_ns != "NONE":
                raise ExecutionBlocked(f"offline mode must have NONE credential namespace, got '{cred_ns}'")
            return

        raise ExecutionBlocked(f"unknown or unhandled execution capability: '{mode}'")
