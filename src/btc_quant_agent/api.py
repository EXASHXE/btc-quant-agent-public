from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import secrets
import sqlite3
import sys
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import __version__
from .config import LiveV1Config, load_config
from .explain import explain_signal
from .service import QuantService

if TYPE_CHECKING:
    from .decision.service import TacticalLiveService
    from .live_runtime import LiveV1Runtime

try:
    from fastapi import Depends, FastAPI, HTTPException
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
except ImportError as exc:  # pragma: no cover - optional dependency guard
    raise RuntimeError("Install the API extra: pip install -e '.[api]'") from exc


_bearer = HTTPBearer(auto_error=False)
_readiness_logger = logging.getLogger("btc_quant_agent.live_v1.readiness")
_HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
_PYTHON_MINOR_RE = re.compile(r"^3\.(1[1-9]|[2-9][0-9])$")

RC1_RELEASE_ID = "B_LINE_INITIAL_USABLE_RELEASE_V1_RC1"
RC1_TASK_ID = "B_LINE_RELEASE_ENGINEERING_R1_REPAIR_IDENTITY_BINDING"
RC1_INITIAL_TASK_ID = "B_LINE_RELEASE_ENGINEERING_R1"
RC1_UNBOUND_SOURCE_SHA = "UNBOUND_PENDING_RC_INTEGRATION"
RC1_WORK_PACKAGE_BASE_SHA = "08e81bec003d645a0a0582db183a1b6916887eff"
RC1_PARENT_SHA = "08e81bec003d645a0a0582db183a1b6916887eff"
RC1_BASELINE_PARENT_SHA = "fde61dafb301d5bd5af3dc7eb81e5618f979036c"
RC1_INITIAL_CONTROLLER_DISPATCH_SHA = "f8e894f2f39adb66340f6bc8cbd803e1b9515b2a"
RC1_CONTROLLER_DISPATCH_SHA = "b5ad376f4fd00d5609c678989eae3156a9e14737"
RC1_STARTUP_CONTRACT = "SERIALIZED_SINGLE_RUNTIME_INITIALIZER"
RC1_STARTUP_MECHANICAL_CERTIFICATION = "PENDING_WP_A"
RC1_CERTIFIED_PYTHON_PENDING = "PENDING_WP_A"
RC1_REQUIRES_PYTHON = ">=3.11"
RC1_CONTAINER_BUILD_PYTHON = "3.12"
RC1_CANONICAL_STARTUP_COMMAND = (
    "uvicorn btc_quant_agent.api:app --host 127.0.0.1 --port 8787 --workers 1"
)
RC1_SUPPORTED_MODES: tuple[str, ...] = ("DRY_RUN", "TESTNET")
RC1_SAFETY_AUTHORITY: dict[str, str] = {
    "real_funds_write_authority": "NONE",
    "live_approval_only": "NOT_AUTHORIZED",
    "autonomous_live": "FORBIDDEN",
}
RC1_FORBIDDEN_CREDENTIAL_ENV_VARS: tuple[str, ...] = (
    "BINANCE_API_KEY",
    "BINANCE_API_SECRET",
    "BINANCE_LIVE_API_KEY",
    "BINANCE_LIVE_API_SECRET",
    "BINANCE_MAINNET_API_KEY",
    "BINANCE_MAINNET_API_SECRET",
    "BINANCE_PRIVATE_KEY",
)
READINESS_REQUIRED_FIELDS: tuple[str, ...] = (
    "service_started",
    "database_ready",
    "migration_ready",
    "market_source_ready",
    "analysis_backend_ready",
    "approval_backend_state",
    "account_stream_state",
    "execution_mode",
    "kill_switch_state",
)
_B3_REQUIRED_TABLES: tuple[str, ...] = (
    "live_cases",
    "analysis_results",
    "trade_proposals",
    "approval_records",
    "live_state_events",
)
_B4_REQUIRED_TABLES: tuple[str, ...] = (
    *_B3_REQUIRED_TABLES,
    "live_account_snapshots",
    "live_account_events",
    "live_trade_intents",
    "live_intent_transitions",
    "live_execution_market_observations",
    "live_pre_execution_authorizations",
    "live_execution_claims",
    "live_execution_orders",
    "live_protection_owners",
    "live_kill_switch_state",
    "live_position_events",
    "live_position_active",
    "live_position_lifecycle",
    "live_position_lifecycle_v2",
    "live_position_observed_sources",
    "live_position_case_dispatches",
)
_B3_MIGRATED_COLUMNS: dict[str, tuple[str, ...]] = {
    "approval_records": (
        "review_processed",
        "review_claim_until_ms",
        "review_claim_token",
    ),
}
_B4_MIGRATED_COLUMNS: dict[str, tuple[str, ...]] = {
    **_B3_MIGRATED_COLUMNS,
    "live_protection_owners": ("confirmed_at_ms",),
    "live_position_events": (
        "environment",
        "credential_namespace",
        "account_id",
        "position_side",
        "position_authority_key",
    ),
    "live_position_case_dispatches": (
        "position_case_id",
        "position_case_hash",
        "position_case_json",
        "case_hash",
        "dispatch_authority_json",
        "dispatch_authority_hash",
        "analysis_admission_hash",
        "analysis_completed",
    ),
}


def _require_api_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),  # noqa: B008
) -> None:
    expected = os.getenv("BTC_QUANT_API_TOKEN", "")
    if not expected:
        raise HTTPException(503, "BTC_QUANT_API_TOKEN is not configured")
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not secrets.compare_digest(credentials.credentials, expected)
    ):
        raise HTTPException(
            401,
            "invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _validate_env_pre_parse() -> None:
    """Fail early with explicit variable names before constructing LiveV1Config."""
    for bool_var in (
        "BTC_QUANT_LIVE_V1_ENABLED",
        "BTC_QUANT_LIVE_V1_RUNTIME_ENABLED",
        "BTC_QUANT_LIVE_V1_TESTNET_EXECUTION_ENABLED",
        "BTC_QUANT_LIVE_CODEX_ENABLED",
    ):
        raw_bool = os.getenv(bool_var)
        if raw_bool is not None and raw_bool.strip().lower() not in {"true", "false"}:
            raise ValueError(f"{bool_var} must be true or false")

    authority_checks = (
        ("REAL_FUNDS_WRITE_AUTHORITY", "NONE"),
        ("LIVE_APPROVAL_ONLY", "NOT_AUTHORIZED"),
        ("AUTONOMOUS_LIVE", "FORBIDDEN"),
    )
    for var_name, expected in authority_checks:
        raw_val = os.getenv(var_name)
        if raw_val is not None and raw_val.strip().upper() != expected:
            raise ValueError(f"{var_name} must be {expected} in RC1")

    primary_mode = os.getenv("BTC_QUANT_LIVE_V1_EXECUTION_MODE")
    legacy_mode = os.getenv("BTC_QUANT_LIVE_EXECUTION_MODE")
    if (
        primary_mode is not None
        and legacy_mode is not None
        and primary_mode.strip().upper() != legacy_mode.strip().upper()
    ):
        raise ValueError(
            "Conflicting BTC_QUANT_LIVE_V1_EXECUTION_MODE and BTC_QUANT_LIVE_EXECUTION_MODE"
        )
    effective_mode_raw = (primary_mode if primary_mode is not None else legacy_mode)
    if effective_mode_raw is not None:
        cleaned_mode = effective_mode_raw.strip().upper()
        if cleaned_mode == "LIVE":
            raise ValueError(
                "BTC_QUANT_LIVE_V1_EXECUTION_MODE=LIVE is unavailable in RC1; "
                "supported modes are DRY_RUN and TESTNET"
            )
        if cleaned_mode not in {"DRY_RUN", "TESTNET", "PAPER", "SHADOW"}:
            raise ValueError(
                "BTC_QUANT_LIVE_V1_EXECUTION_MODE must be DRY_RUN or TESTNET"
            )

    for float_var in (
        "BTC_QUANT_LIVE_V1_REST_RECONCILE_SECONDS",
        "BTC_QUANT_LIVE_ANALYSIS_TIMEOUT",
        "BTC_QUANT_LIVE_V1_POSITION_POLL_SECONDS",
        "BTC_QUANT_LIVE_V1_OUTBOX_POLL_SECONDS",
    ):
        raw_float = os.getenv(float_var)
        if raw_float is not None:
            try:
                parsed_float = float(raw_float)
            except ValueError as exc:
                raise ValueError(f"{float_var} must be a finite number") from exc
            if not math.isfinite(parsed_float) or parsed_float <= 0:
                raise ValueError(f"{float_var} must be a positive finite number")

    raw_ttl = os.getenv("BTC_QUANT_LIVE_CASE_TTL_MS")
    if raw_ttl is not None:
        try:
            parsed_ttl = int(raw_ttl)
        except ValueError as exc:
            raise ValueError("BTC_QUANT_LIVE_CASE_TTL_MS must be a positive integer") from exc
        if parsed_ttl <= 0:
            raise ValueError("BTC_QUANT_LIVE_CASE_TTL_MS must be a positive integer")

    for text_var in (
        "BTC_QUANT_LIVE_V1_DB_PATH",
        "BTC_QUANT_LIVE_V1_SYMBOL",
        "BTC_QUANT_LIVE_V1_ACCOUNT_ID",
    ):
        raw_text = os.getenv(text_var)
        if raw_text is not None and not raw_text.strip():
            raise ValueError(f"{text_var} must not be empty")
    if os.getenv("BTC_QUANT_LIVE_V1_DB_PATH", "").strip() == ":memory:":
        raise ValueError("BTC_QUANT_LIVE_V1_DB_PATH must be a durable filesystem path")

    raw_ws = os.getenv("BTC_QUANT_LIVE_V1_WS_URL")
    if raw_ws is not None and not raw_ws.strip().startswith(("ws://", "wss://")):
        raise ValueError("BTC_QUANT_LIVE_V1_WS_URL must be a ws:// or wss:// URL")

    raw_receive_id_type = os.getenv("FEISHU_RECEIVE_ID_TYPE")
    if raw_receive_id_type is not None and raw_receive_id_type.strip() not in {
        "chat_id",
        "open_id",
        "user_id",
        "email",
    }:
        raise ValueError(
            "FEISHU_RECEIVE_ID_TYPE must be one of: chat_id, open_id, user_id, email"
        )


def _validate_active_live_v1_config(
    live_config: LiveV1Config,
    *,
    runtime_requested: bool,
    injected_runtime: bool,
) -> None:
    """Validate cross-field and credential boundary invariants when Live V1 is active."""
    for forbidden_var in RC1_FORBIDDEN_CREDENTIAL_ENV_VARS:
        if os.getenv(forbidden_var, "").strip():
            raise ValueError(
                f"Forbidden live/mainnet credential variable {forbidden_var} is set; "
                "REAL_FUNDS_WRITE_AUTHORITY is NONE in RC1"
            )

    raw_responses_model = os.getenv("BTC_QUANT_LIVE_RESPONSES_MODEL")
    if raw_responses_model is not None and not raw_responses_model.strip():
        raise ValueError("BTC_QUANT_LIVE_RESPONSES_MODEL must not be whitespace-only")

    policy_json = os.getenv("BTC_QUANT_LIVE_RISK_POLICY_JSON")
    if policy_json is not None:
        if not policy_json.strip():
            raise ValueError("BTC_QUANT_LIVE_RISK_POLICY_JSON must not be empty when set")
        from .decision.risk import RiskPolicyV1

        try:
            RiskPolicyV1.model_validate_json(policy_json)
        except Exception as exc:
            raise ValueError(f"BTC_QUANT_LIVE_RISK_POLICY_JSON is invalid: {exc}") from exc

    feishu_outbound = (
        live_config.feishu_app_id.strip(),
        os.getenv("FEISHU_APP_SECRET", "").strip(),
        live_config.feishu_receive_id.strip(),
    )
    if any(feishu_outbound) and not all(feishu_outbound):
        raise ValueError(
            "Incomplete Feishu outbound configuration: FEISHU_APP_ID, FEISHU_APP_SECRET, "
            "and FEISHU_RECEIVE_ID must all be set together or all left unset"
        )

    receive_id_type = os.getenv("FEISHU_RECEIVE_ID_TYPE")
    if receive_id_type is not None and receive_id_type.strip() not in {
        "chat_id",
        "open_id",
        "user_id",
        "email",
    }:
        raise ValueError(
            "FEISHU_RECEIVE_ID_TYPE must be one of: chat_id, open_id, user_id, email"
        )

    if live_config.execution_mode == "TESTNET":
        fapi_url = os.getenv(
            "BINANCE_TESTNET_FAPI_BASE_URL", "https://testnet.binancefuture.com"
        ).strip()
        if fapi_url.rstrip("/").lower() != "https://testnet.binancefuture.com":
            raise ValueError(
                "BINANCE_TESTNET_FAPI_BASE_URL must be https://testnet.binancefuture.com"
            )
        ws_url = os.getenv(
            "BINANCE_TESTNET_WS_BASE_URL", "wss://stream.binancefuture.com/ws"
        ).strip()
        if not ws_url.startswith(("ws://", "wss://")) or "testnet" not in ws_url.lower() and "binancefuture" not in ws_url.lower():
            raise ValueError(
                "BINANCE_TESTNET_WS_BASE_URL must be a valid Binance Futures Testnet ws(s) URL"
            )
        if runtime_requested and not injected_runtime:
            key = os.getenv("BINANCE_TESTNET_API_KEY", "").strip()
            secret = os.getenv("BINANCE_TESTNET_API_SECRET", "").strip()
            if not key or not secret:
                raise ValueError(
                    "TESTNET mode requires BINANCE_TESTNET_API_KEY and BINANCE_TESTNET_API_SECRET"
                )


def _initialize_live_v1_persistence(db_path: str | Path, *, runtime_mode: bool) -> None:
    """Initialize and migrate durable Live V1 SQLite schema under SERIALIZED_SINGLE_RUNTIME_INITIALIZER."""
    from .approval.store import LiveStore

    LiveStore(db_path)
    if runtime_mode:
        from .account_watch.store import AccountStore
        from .execution.authorization import AuthorizationStore
        from .execution.backend import DryRunExecutionBackend
        from .execution.intents import IntentStore
        from .execution.protection import ProtectionStore
        from .position_supervisor.kill_switch import KillSwitch
        from .position_supervisor.supervisor import PositionSupervisor

        AccountStore(db_path)
        IntentStore(db_path)
        AuthorizationStore(db_path)
        DryRunExecutionBackend(db_path)
        ProtectionStore(db_path)
        KillSwitch(db_path)
        PositionSupervisor(db_path)


def _inspect_live_v1_db_read_only(
    db_path: str | Path | None, *, runtime_mode: bool
) -> dict[str, Any]:
    """Read-only inspection of Live V1 SQLite database and schema migrations without file creation."""
    if not db_path:
        return {
            "database_ready": False,
            "migration_ready": False,
            "kill_switch_state": "UNAVAILABLE",
            "kill_switch_reasons": [],
        }
    path_obj = Path(db_path)
    if not path_obj.is_file():
        return {
            "database_ready": False,
            "migration_ready": False,
            "kill_switch_state": "UNAVAILABLE",
            "kill_switch_reasons": [],
        }
    try:
        uri = f"file:{path_obj.resolve().as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA query_only=ON")
            journal_row = conn.execute("PRAGMA journal_mode").fetchone()
            journal_mode = str(journal_row[0]).lower() if journal_row else ""
            tables = {
                str(row["name"])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            required_tables = _B4_REQUIRED_TABLES if runtime_mode else _B3_REQUIRED_TABLES
            required_columns = _B4_MIGRATED_COLUMNS if runtime_mode else _B3_MIGRATED_COLUMNS
            tables_ok = all(t in tables for t in required_tables)
            columns_ok = True
            if tables_ok:
                for table_name, cols in required_columns.items():
                    present_cols = {
                        str(r["name"])
                        for r in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
                    }
                    if not all(c in present_cols for c in cols):
                        columns_ok = False
                        break
            triggers_ok = True
            if runtime_mode and tables_ok:
                triggers = {
                    str(row["name"])
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='trigger'"
                    ).fetchall()
                }
                for req_trigger in (
                    "trg_live_position_events_immutable_update",
                    "trg_live_position_dispatch_blank_insert",
                    "trg_live_position_analysis_completion_guard",
                ):
                    if req_trigger not in triggers:
                        triggers_ok = False
                        break

            kill_state = "ARMED"
            kill_reasons: list[str] = []
            if "live_kill_switch_state" in tables:
                k_row = conn.execute(
                    "SELECT is_killed, reasons FROM live_kill_switch_state WHERE id=1"
                ).fetchone()
                if k_row is not None and int(k_row["is_killed"]) == 1:
                    kill_state = "TRIPPED"
                    try:
                        parsed_reasons = json.loads(str(k_row["reasons"]))
                        if isinstance(parsed_reasons, list):
                            kill_reasons = [str(item) for item in parsed_reasons]
                    except ValueError:
                        kill_reasons = ["KILL_SWITCH_ACTIVE"]

            db_ready = journal_mode == "wal" and bool(tables)
            migration_ready = db_ready and tables_ok and columns_ok and triggers_ok
            return {
                "database_ready": db_ready,
                "migration_ready": migration_ready,
                "kill_switch_state": kill_state,
                "kill_switch_reasons": kill_reasons,
            }
        finally:
            conn.close()
    except sqlite3.Error:
        return {
            "database_ready": False,
            "migration_ready": False,
            "kill_switch_state": "UNAVAILABLE",
            "kill_switch_reasons": [],
        }


def build_live_v1_readiness(
    live_config: LiveV1Config,
    *,
    b3_mode: bool,
    runtime_mode: bool,
    live_service: TacticalLiveService | None,
    live_runtime: LiveV1Runtime | None,
    lifespan_started: bool = False,
) -> dict[str, Any]:
    """Construct the canonical 9-field machine-readable Live V1 readiness report."""
    if not b3_mode and not runtime_mode:
        return {
            "service_started": False,
            "database_ready": False,
            "migration_ready": False,
            "market_source_ready": False,
            "analysis_backend_ready": False,
            "approval_backend_state": "DISABLED",
            "account_stream_state": "DISABLED",
            "execution_mode": "DISABLED",
            "kill_switch_state": "DISABLED",
            "startup_contract": RC1_STARTUP_CONTRACT,
            "startup_mechanical_certification": RC1_STARTUP_MECHANICAL_CERTIFICATION,
            "runtime_mode": "DISABLED",
            "accepting_risk": False,
            "blocked_reason": "LIVE_V1_DISABLED",
            "safety_authority": dict(RC1_SAFETY_AUTHORITY),
        }

    runtime_status: dict[str, Any] = {}
    if live_runtime is not None and hasattr(live_runtime, "status"):
        try:
            raw_status = live_runtime.status()
            if isinstance(raw_status, dict):
                runtime_status = dict(raw_status)
        except Exception:  # noqa: BLE001
            runtime_status = {}

    db_path = (
        getattr(getattr(live_service, "store", None), "path", None)
        or live_config.sqlite_path
    )
    db_inspection = _inspect_live_v1_db_read_only(db_path, runtime_mode=runtime_mode)

    exec_mode = str(
        runtime_status.get("execution_mode", live_config.execution_mode)
    ).upper()

    if runtime_mode:
        service_started = bool(
            lifespan_started
            or getattr(live_runtime, "_started", False)
            or runtime_status.get("enabled", False)
        )
    else:
        service_started = True

    market_stream = getattr(live_runtime, "market_stream", None)
    if runtime_mode:
        if market_stream is not None:
            market_source_ready = bool(getattr(market_stream, "is_connected", False))
        else:
            market_source_ready = bool(
                service_started
                and (
                    runtime_status.get("accepting_risk", False)
                    or getattr(live_service, "market_watch", None) is not None
                )
            )
    else:
        market_source_ready = getattr(live_service, "market_watch", None) is not None

    primary_backend = getattr(live_service, "primary", None)
    secondary_backend = getattr(live_service, "secondary", None)
    primary_ready = False
    if primary_backend is not None:
        model_attr = getattr(primary_backend, "model", None)
        if isinstance(model_attr, str):
            has_key_or_client = bool(
                getattr(primary_backend, "client", None) is not None
                or os.getenv("OPENAI_API_KEY", "").strip()
            )
            primary_ready = bool(model_attr.strip()) and has_key_or_client
        else:
            primary_ready = True
    secondary_ready = True
    if live_config.codex_enabled:
        sec_model = getattr(secondary_backend, "model", "") if secondary_backend is not None else ""
        secondary_ready = bool(str(sec_model).strip())
    analysis_backend_ready = primary_ready and secondary_ready

    notifier = getattr(live_service, "notifier", None)
    has_verify_token = bool(os.getenv("FEISHU_VERIFICATION_TOKEN", "").strip())
    has_approvers = bool(live_config.feishu_approver_open_ids)
    if notifier is not None and has_verify_token and has_approvers:
        approval_backend_state = "READY"
    elif has_verify_token and has_approvers:
        approval_backend_state = "CALLBACK_READY_NO_OUTBOUND_NOTIFIER"
    elif has_verify_token:
        approval_backend_state = "CALLBACK_TOKEN_ONLY"
    else:
        approval_backend_state = "MANUAL_FALLBACK_ONLY"

    if not runtime_mode:
        account_stream_state = "NOT_APPLICABLE_B3_CONTROL"
    else:
        account_watch = getattr(live_runtime, "account_watch", None)
        stream_connected = bool(
            runtime_status.get(
                "account_stream_connected",
                getattr(account_watch, "is_stream_connected", False),
            )
        )
        if exec_mode == "DRY_RUN":
            account_stream_state = (
                "CONNECTED" if stream_connected else "NOT_REQUIRED_DRY_RUN"
            )
        else:
            account_stream_state = "CONNECTED" if stream_connected else "DISCONNECTED"

    kill_switch_state = str(db_inspection["kill_switch_state"])
    kill_obj = getattr(live_runtime, "kill_switch", None)
    if kill_obj is not None and hasattr(kill_obj, "allows_new_risk"):
        try:
            if not kill_obj.allows_new_risk():
                kill_switch_state = "TRIPPED"
            elif kill_switch_state == "UNAVAILABLE":
                kill_switch_state = "ARMED"
        except Exception:  # noqa: BLE001
            kill_switch_state = "UNAVAILABLE"

    accepting_risk = bool(
        runtime_status.get(
            "accepting_risk",
            getattr(live_runtime, "accepting_risk", False),
        )
    )
    blocked_reason = str(
        runtime_status.get(
            "blocked_reason",
            getattr(
                live_runtime,
                "blocked_reason",
                "" if accepting_risk else ("B3_CONTROL_ONLY" if b3_mode else "RUNTIME_NOT_STARTED"),
            ),
        )
    )

    return {
        "service_started": service_started,
        "database_ready": bool(db_inspection["database_ready"]),
        "migration_ready": bool(db_inspection["migration_ready"]),
        "market_source_ready": market_source_ready,
        "analysis_backend_ready": analysis_backend_ready,
        "approval_backend_state": approval_backend_state,
        "account_stream_state": account_stream_state,
        "execution_mode": exec_mode,
        "kill_switch_state": kill_switch_state,
        "startup_contract": RC1_STARTUP_CONTRACT,
        "startup_mechanical_certification": RC1_STARTUP_MECHANICAL_CERTIFICATION,
        "runtime_mode": "B4_RUNTIME" if runtime_mode else "B3_CONTROL",
        "accepting_risk": accepting_risk,
        "blocked_reason": blocked_reason,
        "database_path": str(db_path),
        "kill_switch_reasons": list(db_inspection["kill_switch_reasons"]),
        "safety_authority": dict(RC1_SAFETY_AUTHORITY),
    }


def create_app(
    live_service: TacticalLiveService | None = None,
    live_runtime: LiveV1Runtime | None = None,
) -> FastAPI:
    _validate_env_pre_parse()
    live_config = LiveV1Config.from_env()
    runtime_requested = live_config.normalized_mode == "B4_RUNTIME"
    runtime_mode = live_runtime is not None or runtime_requested
    b3_mode = (live_service is not None or live_config.normalized_mode == "B3_CONTROL") and not runtime_mode

    if b3_mode or runtime_mode:
        _validate_active_live_v1_config(
            live_config,
            runtime_requested=runtime_requested,
            injected_runtime=live_runtime is not None,
        )

    service = QuantService.create(load_config())
    if (b3_mode or runtime_mode) and (
        service.config.execution.allow_live or service.config.execution.mode == "live"
    ):
        raise ValueError("RC1 forbids execution.allow_live=true and execution.mode='live'")

    live: TacticalLiveService | None = None
    lifespan_state = {"started": False}

    if b3_mode or runtime_mode:
        from .approval.callback import create_callback_app
        from .decision.service import TacticalLiveService
        from .market_watch.service import MarketWatchService

        live = (
            live_service
            or (live_runtime.tactical_service if live_runtime is not None else None)
            or TacticalLiveService.from_config(
                live_config,
                MarketWatchService.create(service.config.market_watch, service.config.data),
            )
        )
        active_db_path = getattr(getattr(live, "store", None), "path", None) or live_config.sqlite_path
        _initialize_live_v1_persistence(active_db_path, runtime_mode=runtime_mode)

        if runtime_requested and live_runtime is None:
            from .live_runtime import LiveV1Runtime

            live_runtime = LiveV1Runtime.create(live_config, live)

    def _current_readiness() -> dict[str, Any]:
        return build_live_v1_readiness(
            live_config,
            b3_mode=b3_mode,
            runtime_mode=runtime_mode,
            live_service=live,
            live_runtime=live_runtime,
            lifespan_started=lifespan_state["started"],
        )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if live_runtime is not None:
            try:
                await live_runtime.start()
                lifespan_state["started"] = True
                readiness_payload = _current_readiness()
                _readiness_logger.info(
                    json.dumps(
                        {
                            "event": "LIVE_V1_STARTUP_READINESS",
                            "release_id": RC1_RELEASE_ID,
                            **readiness_payload,
                        },
                        sort_keys=True,
                    )
                )
            except Exception as exc:
                lifespan_state["started"] = False
                failure_payload = _current_readiness()
                _readiness_logger.error(
                    json.dumps(
                        {
                            "event": "LIVE_V1_STARTUP_READINESS_FAILED",
                            "release_id": RC1_RELEASE_ID,
                            "error": str(exc),
                            **failure_payload,
                        },
                        sort_keys=True,
                    )
                )
                raise
        try:
            yield
        finally:
            lifespan_state["started"] = False
            if live_runtime is not None:
                await live_runtime.stop()
                _readiness_logger.info(
                    json.dumps(
                        {
                            "event": "LIVE_V1_SHUTDOWN_COMPLETE",
                            "release_id": RC1_RELEASE_ID,
                            **_current_readiness(),
                        },
                        sort_keys=True,
                    )
                )

    app = FastAPI(
        title="BTC Quant Signal API",
        version=__version__,
        dependencies=[Depends(_require_api_token)],
        lifespan=lifespan,
    )
    app.state.live_v1_readiness = _current_readiness

    if (b3_mode or runtime_mode) and live is not None:
        from .approval.callback import create_callback_app

        # Mounted app authenticates Feishu callbacks independently of the API bearer.
        app.mount(
            "/live-v1/feishu",
            create_callback_app(
                live.store,
                os.getenv("FEISHU_VERIFICATION_TOKEN", ""),
                signing_secret=os.getenv("FEISHU_ENCRYPT_KEY", ""),
                approver_open_ids=live_config.feishu_approver_open_ids,
                app_id=live_config.feishu_app_id,
            ),
        )

        if b3_mode:
            from .decision.api import create_live_router

            app.include_router(create_live_router(live))

    @app.get("/health")
    def health() -> dict[str, object]:
        report = dict(service.health())
        report["live_v1_readiness"] = _current_readiness()
        return report

    @app.get("/signals/latest")
    def latest() -> dict[str, object]:
        signal = service.repository.latest_signal()
        if signal is None:
            raise HTTPException(404, "signal not found")
        return signal.as_dict()

    @app.get("/signals/{signal_id}")
    def get_signal(signal_id: str) -> dict[str, object]:
        signal = service.repository.get_signal(signal_id)
        if signal is None:
            raise HTTPException(404, "signal not found")
        return signal.as_dict()

    @app.get("/signals/{signal_id}/explanation")
    def explanation(signal_id: str) -> dict[str, object]:
        signal = service.repository.get_signal(signal_id)
        if signal is None:
            raise HTTPException(404, "signal not found")
        return explain_signal(signal)

    @app.get("/performance")
    def performance(days: int = 30) -> dict[str, object]:
        if days < 1 or days > 3650:
            raise HTTPException(422, "days must be between 1 and 3650")
        since_ms = int(time.time() * 1000) - days * 86_400_000
        from .shadow import read_legacy_shadow_performance

        return read_legacy_shadow_performance(service.repository, since_ms)

    @app.get("/execution/status")
    def execution_status() -> dict[str, object]:
        status = dict(service.execution.status())
        if live_runtime is not None:
            status["live_v1_runtime"] = live_runtime.status()
        status["live_v1_readiness"] = _current_readiness()
        return status

    return app


def _validate_git_sha40(
    value: str,
    *,
    field_name: str,
    reject_work_package_base: bool = False,
) -> str:
    """Validate that a git SHA is a 40-character lowercase hexadecimal string."""
    cleaned = value.strip()
    if not _HEX40_RE.fullmatch(cleaned):
        raise ValueError(f"{field_name} must be a 40-character lowercase hexadecimal git SHA")
    if reject_work_package_base and cleaned == RC1_WORK_PACKAGE_BASE_SHA:
        raise ValueError(
            f"{field_name} cannot be the pre-integration WP-D work_package_base_sha "
            f"({RC1_WORK_PACKAGE_BASE_SHA}); supply the final integrated RC1 source SHA"
        )
    return cleaned


def _resolve_wp_a_runtime_certification(
    *,
    rc1_certified_python: list[str] | tuple[str, ...] | str | None,
    startup_mechanical_certification: str | None,
    wp_a_evidence_identity: str | None,
    wp_a_independent_313_certification: bool,
) -> tuple[str | list[str], str, str]:
    """Resolve and validate WP-A runtime certification and Python version bindings."""
    resolved_wp_a_evidence = (
        wp_a_evidence_identity.strip()
        if isinstance(wp_a_evidence_identity, str) and wp_a_evidence_identity.strip()
        else RC1_CERTIFIED_PYTHON_PENDING
    )
    has_accepted_wp_a_evidence = resolved_wp_a_evidence != RC1_CERTIFIED_PYTHON_PENDING

    if (
        rc1_certified_python is None
        or rc1_certified_python == RC1_CERTIFIED_PYTHON_PENDING
    ):
        resolved_certified_python: str | list[str] = RC1_CERTIFIED_PYTHON_PENDING
    else:
        if not has_accepted_wp_a_evidence:
            raise ValueError(
                "rc1_certified_python cannot be bound without accepted wp_a_evidence_identity"
            )
        raw_items: list[str]
        if isinstance(rc1_certified_python, str):
            raw_items = [
                item.strip() for item in rc1_certified_python.split(",") if item.strip()
            ]
        elif isinstance(rc1_certified_python, (list, tuple)):
            raw_items = [str(item).strip() for item in rc1_certified_python if str(item).strip()]
        else:
            raise ValueError("rc1_certified_python must be 'PENDING_WP_A' or a list of versions")
        if not raw_items:
            raise ValueError("rc1_certified_python list must not be empty when bound")
        normalized_versions: list[str] = []
        for ver in raw_items:
            if not _PYTHON_MINOR_RE.fullmatch(ver):
                raise ValueError(
                    f"Invalid Python version '{ver}' in rc1_certified_python; must match 3.11+"
                )
            if ver == "3.13" and not wp_a_independent_313_certification:
                raise ValueError(
                    "Python 3.13 cannot be listed as RC1-certified unless WP-A independently certifies it"
                )
            if ver not in normalized_versions:
                normalized_versions.append(ver)
        resolved_certified_python = normalized_versions

    resolved_startup_cert = (
        startup_mechanical_certification.strip()
        if isinstance(startup_mechanical_certification, str)
        and startup_mechanical_certification.strip()
        else RC1_STARTUP_MECHANICAL_CERTIFICATION
    )
    if resolved_startup_cert not in {RC1_STARTUP_MECHANICAL_CERTIFICATION, "CERTIFIED_BY_WP_A"}:
        raise ValueError(
            "startup_mechanical_certification must be 'PENDING_WP_A' or 'CERTIFIED_BY_WP_A'"
        )
    if resolved_startup_cert == "CERTIFIED_BY_WP_A" and not has_accepted_wp_a_evidence:
        raise ValueError(
            "startup_mechanical_certification='CERTIFIED_BY_WP_A' requires accepted wp_a_evidence_identity"
        )

    return resolved_certified_python, resolved_startup_cert, resolved_wp_a_evidence


def build_rc1_release_manifest(
    *,
    source_sha: str | None = None,
    parent_sha: str | None = None,
    rc1_certified_python: list[str] | tuple[str, ...] | str | None = None,
    startup_mechanical_certification: str | None = None,
    wp_a_evidence_identity: str | None = None,
    wp_a_independent_313_certification: bool = False,
    require_bound_source_sha: bool = False,
) -> dict[str, Any]:
    """Deterministically build the B_LINE_INITIAL_USABLE_RELEASE_V1_RC1 release manifest.

    In the WP-D worktree template (prior to final RC integration), ``source_sha``
    defaults to ``UNBOUND_PENDING_RC_INTEGRATION`` and WP-A runtime certification
    fields remain ``PENDING_WP_A``. At RC integration time, an explicit 40-hex
    integration ``source_sha`` (not the WP-D base SHA ``08e81bec...``) and
    accepted WP-A certification evidence can be bound.
    """
    if require_bound_source_sha and (
        source_sha is None or source_sha.strip() == RC1_UNBOUND_SOURCE_SHA
    ):
        raise ValueError(
            "Final RC1 release manifest requires an explicit 40-hex integration source_sha"
        )

    if source_sha is None or (
        isinstance(source_sha, str) and source_sha.strip() == RC1_UNBOUND_SOURCE_SHA
    ):
        resolved_source_sha = RC1_UNBOUND_SOURCE_SHA
        release_identity_state = "UNBOUND_PENDING_RC_INTEGRATION"
    else:
        resolved_source_sha = _validate_git_sha40(
            source_sha,
            field_name="source_sha",
            reject_work_package_base=True,
        )
        release_identity_state = "BOUND_RC_INTEGRATION"

    if parent_sha is None:
        resolved_parent_sha = RC1_PARENT_SHA
    else:
        resolved_parent_sha = _validate_git_sha40(
            parent_sha,
            field_name="parent_sha",
            reject_work_package_base=False,
        )

    resolved_certified_python, resolved_startup_cert, resolved_wp_a_evidence = (
        _resolve_wp_a_runtime_certification(
            rc1_certified_python=rc1_certified_python,
            startup_mechanical_certification=startup_mechanical_certification,
            wp_a_evidence_identity=wp_a_evidence_identity,
            wp_a_independent_313_certification=wp_a_independent_313_certification,
        )
    )

    schema_identity: dict[str, Any] = {
        "default_live_v1_db_path": "./var/live_v1.db",
        "default_host_db_path": "./var/quant.db",
        "default_market_watch_db_path": "./var/market_watch.db",
        "journal_mode": "wal",
        "synchronous": "FULL",
        "foreign_keys": True,
        "recursive_triggers": True,
        "busy_timeout_ms": 10000,
        "startup_migration_policy": "SERIALIZED_SINGLE_RUNTIME_INITIALIZER_IDEMPOTENT_DDL",
        "b3_tables": list(_B3_REQUIRED_TABLES),
        "b4_tables": list(_B4_REQUIRED_TABLES),
        "migrated_columns": {k: list(v) for k, v in _B4_MIGRATED_COLUMNS.items()},
        "immutable_triggers": [
            "trg_live_position_events_immutable_update",
            "trg_live_position_events_immutable_delete",
            "trg_live_position_dispatches_immutable_authority",
            "trg_live_position_dispatch_blank_insert",
            "trg_live_position_dispatch_admission_immutable",
            "trg_live_position_dispatch_done_requires_completion",
            "trg_live_position_analysis_completion_guard",
            "trg_live_position_dispatches_immutable_delete",
        ],
    }
    return {
        "schema_version": "B_LINE_RC1_RELEASE_MANIFEST_V1",
        "release_id": RC1_RELEASE_ID,
        "work_package": "WP_D",
        "task_id": RC1_TASK_ID,
        "initial_task_id": RC1_INITIAL_TASK_ID,
        "release_identity_state": release_identity_state,
        "source_sha": resolved_source_sha,
        "work_package_base_sha": RC1_WORK_PACKAGE_BASE_SHA,
        "parent_sha": resolved_parent_sha,
        "baseline_parent_sha": RC1_BASELINE_PARENT_SHA,
        "initial_controller_dispatch_sha": RC1_INITIAL_CONTROLLER_DISPATCH_SHA,
        "controller_dispatch_sha": RC1_CONTROLLER_DISPATCH_SHA,
        "startup_contract": RC1_STARTUP_CONTRACT,
        "startup_mechanical_certification": resolved_startup_cert,
        "canonical_startup_command": RC1_CANONICAL_STARTUP_COMMAND,
        "runtime_certification_binding": {
            "release_identity_state": release_identity_state,
            "work_package_base_sha": RC1_WORK_PACKAGE_BASE_SHA,
            "integration_source_sha": resolved_source_sha,
            "startup_contract": RC1_STARTUP_CONTRACT,
            "startup_mechanical_certification": resolved_startup_cert,
            "rc1_certified_python": resolved_certified_python,
            "wp_a_evidence_identity": resolved_wp_a_evidence,
        },
        "component_versions": {
            "package_name": "btc-quant-agent",
            "package_version": __version__,
            "release_line": "v0.5.5-B-LINE-RC1",
            "market_watch_policy_version": "0.5.0-r1",
            "forward_evidence_contract_version": "FORWARD_EVIDENCE_V1",
            "tactical_feature_evidence_version": "TACTICAL_FEATURE_EVIDENCE_V2",
            "directional_shadow_evaluation_version": "DIRECTIONAL_SHADOW_EVALUATION_V2",
            "grid_shadow_evaluation_version": "GRID_SHADOW_EVALUATION_V1",
            "case_package_schema": "CasePackageV1",
            "analysis_result_schema": "AnalysisResultV1",
            "trade_proposal_schema": "TradeProposalV1",
            "trade_intent_schema": "TradeIntentV1",
            "position_observation_schema": "PositionObservationV1",
        },
        "supported_python": {
            "requires_python": RC1_REQUIRES_PYTHON,
            "container_build_python": RC1_CONTAINER_BUILD_PYTHON,
            "rc1_certified_python": resolved_certified_python,
            "rc1_certified_python_source": resolved_wp_a_evidence,
        },
        "execution_modes": {
            "canonical_modes": list(RC1_SUPPORTED_MODES),
            "default_mode": "DRY_RUN",
            "aliases_normalized_to_dry_run": ["PAPER", "SHADOW"],
            "unavailable_modes": ["LIVE"],
            "testnet_requires_explicit_opt_in": True,
        },
        "feature_flags": {
            "BTC_QUANT_LIVE_V1_RUNTIME_ENABLED": {
                "type": "bool",
                "default": False,
                "canonical_rc1_service_value": True,
                "description": "Enable canonical B4_RUNTIME single-initializer operational service",
            },
            "BTC_QUANT_LIVE_V1_ENABLED": {
                "type": "bool",
                "default": False,
                "description": "Legacy B3_CONTROL mode flag (superseded when BTC_QUANT_LIVE_V1_RUNTIME_ENABLED=true)",
            },
            "BTC_QUANT_LIVE_V1_EXECUTION_MODE": {
                "type": "enum",
                "default": "DRY_RUN",
                "allowed": ["DRY_RUN", "TESTNET"],
                "forbidden": ["LIVE"],
            },
            "BTC_QUANT_LIVE_V1_TESTNET_EXECUTION_ENABLED": {
                "type": "bool",
                "default": False,
                "description": "Explicit opt-in required when BTC_QUANT_LIVE_V1_EXECUTION_MODE=TESTNET",
            },
            "BTC_QUANT_LIVE_CODEX_ENABLED": {
                "type": "bool",
                "default": False,
                "description": "Enable secondary Codex CLI review backend",
            },
        },
        "model_config_identifiers": {
            "primary_responses_backend": {
                "backend_id": "responses",
                "model_env_var": "BTC_QUANT_LIVE_RESPONSES_MODEL",
                "default_model_identifier": "gpt-5.4",
                "credential_env_var": "OPENAI_API_KEY",
                "timeout_env_var": "BTC_QUANT_LIVE_ANALYSIS_TIMEOUT",
                "default_timeout_seconds": 60.0,
            },
            "secondary_codex_backend": {
                "backend_id": "codex_exec",
                "enabled_env_var": "BTC_QUANT_LIVE_CODEX_ENABLED",
                "model_env_var": "BTC_QUANT_LIVE_CODEX_MODEL",
                "default_model_identifier": "gpt-5.3-codex-spark",
                "timeout_env_var": "BTC_QUANT_LIVE_ANALYSIS_TIMEOUT",
                "default_timeout_seconds": 60.0,
            },
            "decision_risk_compiler": {
                "compiler_id": "RiskCompilerV1",
                "policy_schema": "RiskPolicyV1",
                "policy_override_env_var": "BTC_QUANT_LIVE_RISK_POLICY_JSON",
                "case_ttl_env_var": "BTC_QUANT_LIVE_CASE_TTL_MS",
                "default_case_ttl_ms": 120000,
            },
            "approval_feishu_identifiers": {
                "app_id_env_var": "FEISHU_APP_ID",
                "app_secret_env_var": "FEISHU_APP_SECRET",
                "receive_id_env_var": "FEISHU_RECEIVE_ID",
                "receive_id_type_env_var": "FEISHU_RECEIVE_ID_TYPE",
                "verification_token_env_var": "FEISHU_VERIFICATION_TOKEN",
                "encrypt_key_env_var": "FEISHU_ENCRYPT_KEY",
                "approver_open_ids_env_var": "FEISHU_APPROVER_OPEN_IDS",
            },
        },
        "schema_identity": schema_identity,
        "database_identity": schema_identity,
        "readiness_field_matrix": list(READINESS_REQUIRED_FIELDS),
        "evidence_identities": {
            "rc1_release_contract": "reviews/v0.5/live_v1/V0.5.5_B_LINE_INITIAL_USABLE_RELEASE_V1_RC1_CONTRACT.md",
            "b3_day1_validation": "evidence/v0.5.5/live_v1/B3_DAY1_VALIDATION.json",
            "b3_day1_public_data_dry_run": "evidence/v0.5.5/live_v1/B3_DAY1_PUBLIC_DATA_DRY_RUN.json",
            "b4_day2_validation": "evidence/v0.5.5/live_v1/B4_DAY2_VALIDATION.json",
            "wp_a_runtime_certification_evidence": resolved_wp_a_evidence,
            "wp_d_evidence": "evidence/v0.5.5/live_v1/RC1/WP_D/EVIDENCE.json",
            "wp_d_release_manifest": "evidence/v0.5.5/live_v1/RC1/WP_D/B_LINE_INITIAL_USABLE_RELEASE_V1_RC1_MANIFEST.json",
            "operational_runbook": "docs/LIVE_V1_RC1_OPERATIONAL_RUNBOOK.md",
            "config_template": ".env.example",
        },
        "known_limitations": [
            "LIVE execution mode is unavailable in RC1; only DRY_RUN and TESTNET are supported.",
            "Real-money write authority is NONE; LIVE_APPROVAL_ONLY is NOT_AUTHORIZED; AUTONOMOUS_LIVE is FORBIDDEN.",
            "Final RC1 release source_sha is an integration-time binding (UNBOUND_PENDING_RC_INTEGRATION in WP-D worktree template; work_package_base_sha 08e81bec003d645a0a0582db183a1b6916887eff is not final release identity).",
            "Startup mechanical certification under SERIALIZED_SINGLE_RUNTIME_INITIALIZER and rc1_certified_python remain PENDING_WP_A until accepted WP-A runtime certification evidence is bound.",
            "Runtime must be started as a single serialized process (--workers 1) under SERIALIZED_SINGLE_RUNTIME_INITIALIZER.",
            "Single configured symbol (default BTCUSDT) and ONE_WAY position mode only; foreign or unconfigured nonzero positions block new risk.",
            "Provider (Responses/Codex), Feishu notification, or Binance stream/REST outages fail closed to MANUAL or block new risk until reconciled.",
            "Release manifest is descriptive engineering identity only and grants zero authority to trade real funds.",
        ],
        "real_money_authority": {
            **RC1_SAFETY_AUTHORITY,
            "live_mode_available": False,
            "manifest_is_descriptive_identity_only": True,
            "grants_trading_authority": False,
        },
    }


def verify_rc1_release_manifest(
    manifest: dict[str, Any],
    *,
    expected_source_sha: str | None = None,
    require_bound: bool = False,
    wp_a_independent_313_certification: bool = False,
) -> tuple[bool, list[str]]:
    """Mechanically verify RC1 release manifest completeness, determinism, and safety invariants."""
    errors: list[str] = []
    required_top_keys = (
        "release_id",
        "release_identity_state",
        "source_sha",
        "work_package_base_sha",
        "parent_sha",
        "startup_contract",
        "startup_mechanical_certification",
        "runtime_certification_binding",
        "component_versions",
        "supported_python",
        "execution_modes",
        "feature_flags",
        "model_config_identifiers",
        "schema_identity",
        "database_identity",
        "evidence_identities",
        "known_limitations",
        "real_money_authority",
    )
    for key in required_top_keys:
        if key not in manifest:
            errors.append(f"missing required key: {key}")

    if manifest.get("release_id") != RC1_RELEASE_ID:
        errors.append(f"release_id mismatch: {manifest.get('release_id')}")
    if manifest.get("startup_contract") != RC1_STARTUP_CONTRACT:
        errors.append(f"startup_contract mismatch: {manifest.get('startup_contract')}")
    if manifest.get("work_package_base_sha") != RC1_WORK_PACKAGE_BASE_SHA:
        errors.append(
            f"work_package_base_sha mismatch: {manifest.get('work_package_base_sha')}"
        )

    raw_source_sha = manifest.get("source_sha")
    if not isinstance(raw_source_sha, str):
        errors.append("source_sha must be a string")
    elif raw_source_sha == RC1_WORK_PACKAGE_BASE_SHA:
        errors.append(
            f"source_sha must not claim pre-integration work_package_base_sha "
            f"({RC1_WORK_PACKAGE_BASE_SHA}) as final RC1 release identity"
        )
    elif raw_source_sha == RC1_UNBOUND_SOURCE_SHA:
        if require_bound or expected_source_sha is not None:
            errors.append(
                "source_sha is UNBOUND_PENDING_RC_INTEGRATION; bound 40-hex integration source_sha required"
            )
        if manifest.get("release_identity_state") != "UNBOUND_PENDING_RC_INTEGRATION":
            errors.append(
                "release_identity_state must be 'UNBOUND_PENDING_RC_INTEGRATION' when source_sha is unbound"
            )
    elif not _HEX40_RE.fullmatch(raw_source_sha):
        errors.append("source_sha must be 'UNBOUND_PENDING_RC_INTEGRATION' or a 40-hex git SHA")
    elif manifest.get("release_identity_state") != "BOUND_RC_INTEGRATION":
        errors.append(
            "release_identity_state must be 'BOUND_RC_INTEGRATION' when source_sha is a bound 40-hex git SHA"
        )

    if expected_source_sha is not None:
        try:
            validated_expected = _validate_git_sha40(
                expected_source_sha,
                field_name="expected_source_sha",
                reject_work_package_base=True,
            )
            if raw_source_sha != validated_expected:
                errors.append(
                    f"source_sha mismatch: expected {validated_expected}, got {raw_source_sha}"
                )
        except ValueError as exc:
            errors.append(str(exc))

    raw_parent_sha = manifest.get("parent_sha")
    if not isinstance(raw_parent_sha, str) or not _HEX40_RE.fullmatch(raw_parent_sha):
        errors.append("parent_sha must be a 40-character lowercase hexadecimal git SHA")

    supported_py = manifest.get("supported_python")
    if not isinstance(supported_py, dict):
        errors.append("supported_python must be a dict")
    else:
        if supported_py.get("requires_python") != RC1_REQUIRES_PYTHON:
            errors.append(f"supported_python.requires_python must be '{RC1_REQUIRES_PYTHON}'")
        if supported_py.get("container_build_python") != RC1_CONTAINER_BUILD_PYTHON:
            errors.append(
                f"supported_python.container_build_python must be '{RC1_CONTAINER_BUILD_PYTHON}'"
            )
        if "supported_versions" in supported_py:
            errors.append(
                "supported_python must not contain uncertified 'supported_versions' list; "
                "use requires_python, container_build_python, and rc1_certified_python"
            )
        cert_py = supported_py.get("rc1_certified_python")
        cert_source = supported_py.get("rc1_certified_python_source")
        if cert_py == RC1_CERTIFIED_PYTHON_PENDING:
            if require_bound:
                errors.append(
                    "supported_python.rc1_certified_python is PENDING_WP_A; bound WP-A certification required"
                )
            if cert_source != RC1_CERTIFIED_PYTHON_PENDING:
                errors.append(
                    "supported_python.rc1_certified_python_source must be 'PENDING_WP_A' when rc1_certified_python is pending"
                )
        elif isinstance(cert_py, list):
            if not cert_py:
                errors.append("supported_python.rc1_certified_python must not be empty when bound")
            if not isinstance(cert_source, str) or cert_source in {"", RC1_CERTIFIED_PYTHON_PENDING}:
                errors.append(
                    "supported_python.rc1_certified_python requires accepted WP-A evidence source"
                )
            if "3.13" in cert_py and not wp_a_independent_313_certification:
                errors.append(
                    "Python 3.13 must not be listed in rc1_certified_python without independent WP-A certification"
                )
        else:
            errors.append(
                "supported_python.rc1_certified_python must be 'PENDING_WP_A' or a list of WP-A certified versions"
            )

    startup_cert = manifest.get("startup_mechanical_certification")
    if startup_cert not in {RC1_STARTUP_MECHANICAL_CERTIFICATION, "CERTIFIED_BY_WP_A"}:
        errors.append(
            "startup_mechanical_certification must be 'PENDING_WP_A' or 'CERTIFIED_BY_WP_A'"
        )
    elif require_bound and startup_cert != "CERTIFIED_BY_WP_A":
        errors.append(
            "startup_mechanical_certification is PENDING_WP_A; CERTIFIED_BY_WP_A required for bound release"
        )

    modes = manifest.get("execution_modes", {})
    if not isinstance(modes, dict) or modes.get("canonical_modes") != ["DRY_RUN", "TESTNET"]:
        errors.append("execution_modes.canonical_modes must be ['DRY_RUN', 'TESTNET']")
    if not isinstance(modes, dict) or "LIVE" not in modes.get("unavailable_modes", []):
        errors.append("execution_modes.unavailable_modes must include 'LIVE'")

    authority = manifest.get("real_money_authority", {})
    if not isinstance(authority, dict):
        errors.append("real_money_authority must be a dict")
    else:
        for k, v in RC1_SAFETY_AUTHORITY.items():
            if authority.get(k) != v:
                errors.append(f"real_money_authority.{k} must be {v}")
        if authority.get("live_mode_available") is not False:
            errors.append("real_money_authority.live_mode_available must be False")
        if authority.get("grants_trading_authority") is not False:
            errors.append("real_money_authority.grants_trading_authority must be False")

    if not errors:
        try:
            expected = build_rc1_release_manifest(
                source_sha=raw_source_sha if isinstance(raw_source_sha, str) else None,
                parent_sha=raw_parent_sha if isinstance(raw_parent_sha, str) else None,
                rc1_certified_python=supported_py.get("rc1_certified_python")
                if isinstance(supported_py, dict)
                else None,
                startup_mechanical_certification=startup_cert
                if isinstance(startup_cert, str)
                else None,
                wp_a_evidence_identity=supported_py.get("rc1_certified_python_source")
                if isinstance(supported_py, dict)
                else None,
                wp_a_independent_313_certification=wp_a_independent_313_certification,
            )
            if manifest != expected:
                errors.append(
                    "manifest payload diverges from deterministic build_rc1_release_manifest()"
                )
        except ValueError as exc:
            errors.append(str(exc))

    return (len(errors) == 0, errors)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for config validation, readiness output, manifest verification, or server start."""
    parser = argparse.ArgumentParser(
        prog="python -m btc_quant_agent.api",
        description="B-Line Live V1 RC1 canonical service initializer and release verifier",
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate environment/configuration and print readiness JSON without starting server",
    )
    parser.add_argument(
        "--print-readiness",
        action="store_true",
        help="Construct application and print machine-readable readiness JSON",
    )
    parser.add_argument(
        "--print-manifest",
        action="store_true",
        help="Print deterministic RC1 release manifest JSON to stdout",
    )
    parser.add_argument(
        "--verify-manifest",
        type=Path,
        help="Mechanically verify a release manifest JSON file against RC1 invariants",
    )
    parser.add_argument(
        "--source-sha",
        default=None,
        help="Integration 40-hex git source SHA to bind when building or verifying the RC1 manifest",
    )
    parser.add_argument(
        "--parent-sha",
        default=None,
        help="Optional 40-hex git parent SHA to bind when building the RC1 manifest",
    )
    parser.add_argument(
        "--rc1-certified-python",
        default=None,
        help="Comma-separated WP-A certified Python minor version(s) (requires --wp-a-evidence)",
    )
    parser.add_argument(
        "--startup-certification",
        default=None,
        help="Startup mechanical certification state: PENDING_WP_A or CERTIFIED_BY_WP_A",
    )
    parser.add_argument(
        "--wp-a-evidence",
        default=None,
        help="Accepted WP-A runtime certification evidence path/identity",
    )
    parser.add_argument(
        "--require-bound",
        action="store_true",
        help="Require manifest source_sha and WP-A runtime certification to be bound",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8787, help="Bind port (default: 8787)")
    args = parser.parse_args(argv)

    if args.print_manifest:
        try:
            manifest = build_rc1_release_manifest(
                source_sha=args.source_sha,
                parent_sha=args.parent_sha,
                rc1_certified_python=args.rc1_certified_python,
                startup_mechanical_certification=args.startup_certification,
                wp_a_evidence_identity=args.wp_a_evidence,
                require_bound_source_sha=args.require_bound,
            )
            print(json.dumps(manifest, indent=2, sort_keys=True))
            return 0
        except ValueError as exc:
            print(
                json.dumps({"valid": False, "errors": [str(exc)]}, indent=2, sort_keys=True),
                file=sys.stderr,
            )
            return 2

    if args.verify_manifest is not None:
        if not args.verify_manifest.is_file():
            print(
                json.dumps(
                    {"valid": False, "errors": [f"file not found: {args.verify_manifest}"]},
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
            return 2
        loaded = json.loads(args.verify_manifest.read_text(encoding="utf-8"))
        ok, errs = verify_rc1_release_manifest(
            loaded,
            expected_source_sha=args.source_sha,
            require_bound=args.require_bound,
        )
        print(json.dumps({"valid": ok, "errors": errs}, indent=2, sort_keys=True))
        return 0 if ok else 2

    if args.check_config or args.print_readiness:
        try:
            application = create_app()
            readiness = application.state.live_v1_readiness()
            print(json.dumps(readiness, indent=2, sort_keys=True))
            return 0
        except Exception as exc:  # noqa: BLE001
            print(
                json.dumps(
                    {"config_valid": False, "error": str(exc)},
                    indent=2,
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
            return 2

    import uvicorn

    uvicorn.run("btc_quant_agent.api:app", host=args.host, port=args.port, workers=1)
    return 0


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
