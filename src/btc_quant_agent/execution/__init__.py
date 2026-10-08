"""Explicitly gated order-execution adapters."""

from .backend import DryRunExecutionBackend, ExecutionReport, TestnetExecutionBackend
from .environment import (
    ACCEPTED_EXECUTION_WRITE_AUTHORITY,
    CURRENT_EXECUTION_POLICY,
    ActionClassification,
    ExecutionEnvironmentAuthority,
    validate_execution_environment_preflight,
)
from .executor import LiveExecutionService
from .guard import ExecutionBlocked, ExecutionGuard
from .intents import IntentStore, TradeIntentV1, build_trade_intent
from .models import ClosePlan, ExecutionMode, ExecutionPlan, OrderReceipt
from .policy import LIVE_WRITE_AUTHORITY, CapabilityMode, ExecutionCapabilityPolicyV1
from .validator import PreExecutionValidator, ValidationResult

__all__ = [
    "ACCEPTED_EXECUTION_WRITE_AUTHORITY",
    "CURRENT_EXECUTION_POLICY",
    "LIVE_WRITE_AUTHORITY",
    "ActionClassification",
    "CapabilityMode",
    "ClosePlan",
    "DryRunExecutionBackend",
    "ExecutionBlocked",
    "ExecutionCapabilityPolicyV1",
    "ExecutionEnvironmentAuthority",
    "ExecutionGuard",
    "ExecutionMode",
    "ExecutionPlan",
    "ExecutionReport",
    "IntentStore",
    "LiveExecutionService",
    "OrderReceipt",
    "PreExecutionValidator",
    "TestnetExecutionBackend",
    "TradeIntentV1",
    "ValidationResult",
    "build_trade_intent",
    "validate_execution_environment_preflight",
]
