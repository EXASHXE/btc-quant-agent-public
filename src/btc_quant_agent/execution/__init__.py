"""Explicitly gated order-execution adapters."""

from .environment import (
    ACCEPTED_EXECUTION_WRITE_AUTHORITY,
    CURRENT_EXECUTION_POLICY,
    ActionClassification,
    ExecutionEnvironmentAuthority,
    validate_execution_environment_preflight,
)
from .guard import ExecutionBlocked, ExecutionGuard
from .models import ClosePlan, ExecutionMode, ExecutionPlan, OrderReceipt

__all__ = [
    "ACCEPTED_EXECUTION_WRITE_AUTHORITY",
    "CURRENT_EXECUTION_POLICY",
    "ActionClassification",
    "ClosePlan",
    "ExecutionBlocked",
    "ExecutionEnvironmentAuthority",
    "ExecutionGuard",
    "ExecutionMode",
    "ExecutionPlan",
    "OrderReceipt",
    "validate_execution_environment_preflight",
]
