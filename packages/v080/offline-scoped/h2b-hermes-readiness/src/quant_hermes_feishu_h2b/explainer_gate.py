"""Gated AI explanation pipeline using offline scripted providers and mandatory deterministic fallback."""

from __future__ import annotations

import asyncio
import concurrent.futures
import time
from dataclasses import dataclass
from typing import Any

from quant_hermes_feishu_h1.contract import ContractError
from quant_hermes_feishu_h1.explainer import (
    EXPLANATION_SCHEMA_VERSION,
    explain_snapshot,
    validate_explanation_payload,
)
from quant_hermes_feishu_h1.feishu_chat import contains_prompt_injection_or_forbidden_op

from .activation_gate import GateDenialError, reject_consumer_subscription_entitlement
from .constants import LIVE_MODEL_ERROR, V1_MODEL_READONLY_TOOLS
from .readonly_tools import QuantV1ReadonlyToolGateway


def diagnostic_deterministic_fallback(record: dict[str, Any]) -> dict[str, Any]:
    """Deterministic grounded explanation for NO_SETUP / NOT_EVALUATED diagnostic records (no alert)."""
    reasons = record.get("status_reason_codes") or record.get("reasons") or ["UNKNOWN"]
    return {
        "schema_version": EXPLANATION_SCHEMA_VERSION,
        "card_id": record["card_id"],
        "card_version": record["card_version"],
        "market_status": record["market_status"],
        "referenced_reason_codes": list(reasons),
        "summary_zh": (
            f"[{record.get('source_evidence_class', 'UNKNOWN')}] {record['symbol']} "
            f"当前为诊断状态 {record['market_status']}（episode_id=null，不可推送信号），"
            f"原因码={', '.join(reasons)}；账户上下文={record.get('account_context_status', 'UNAVAILABLE')}。"
        ),
        "advisory_only": True,
    }


@dataclass(frozen=True)
class ScriptedModelResponse:
    """Scripted offline response or injected failure mode for QA without real model providers."""

    mode: str = "valid"  # valid | unavailable | timeout | quota | hallucinated | invalid_json | delayed_cancel
    delay_ms: int = 0
    tool_choice: str | None = None
    tool_args: dict[str, Any] | None = None
    explanation_payload: dict[str, Any] | str | None = None
    error_message: str = "Scripted offline model failure"


class ScriptedModelProvider:
    """Offline mock model/explanation provider supporting deterministic fault injection."""

    name = "h2b_offline_scripted_provider"

    def __init__(self, script: ScriptedModelResponse | None = None) -> None:
        self._script = script or ScriptedModelResponse(mode="valid")

    def generate(self, context: dict[str, Any], *, timeout_ms: int) -> str | dict[str, Any]:
        del timeout_ms
        m = self._script.mode
        if m == "unavailable":
            raise ConnectionError("OFFLINE_MODEL_UNAVAILABLE: scripted provider unreachable")
        if m == "timeout":
            time.sleep(max(0.05, self._script.delay_ms / 1000.0))
            raise TimeoutError("MODEL_TIMEOUT")
        if m == "quota":
            raise RuntimeError("429 quota exhausted (scripted)")
        if m == "delayed_cancel":
            raise asyncio.CancelledError("Cancelled or late response")
        if m == "invalid_json":
            return "{not valid json"
        if m == "hallucinated":
            return {
                "schema_version": EXPLANATION_SCHEMA_VERSION,
                "card_id": context["card_id"],
                "card_version": context["card_version"],
                "market_status": "EXECUTABLE" if context["market_status"] != "EXECUTABLE" else context["market_status"],
                "referenced_reason_codes": ["INVENTED_REASON_CODE"],
                "summary_zh": "保证盈利，建议立即市价入场目标 999999。",
                "advisory_only": True,
            }
        if self._script.explanation_payload is not None:
            return self._script.explanation_payload
        reasons = list(context.get("status_reason_codes") or [])
        return {
            "schema_version": EXPLANATION_SCHEMA_VERSION,
            "card_id": context["card_id"],
            "card_version": context["card_version"],
            "market_status": context["market_status"],
            "referenced_reason_codes": reasons,
            "summary_zh": (
                f"[{context['source_evidence_class']}] {context['symbol']} 当前核心状态 "
                f"{context['market_status']}（原因码 {', '.join(reasons)}），账户上下文不可用。"
            ),
            "advisory_only": True,
        }


class GatedAiExplanationPipeline:
    """Optional offline-first explanation & bounded tool selector with fail-closed deterministic fallback."""

    def __init__(
        self,
        *,
        provider: ScriptedModelProvider | None = None,
        offline_mock_only: bool = True,
        model_gate_authorized: bool = False,
        timeout_ms: int = 200,
    ) -> None:
        self.provider = provider
        self.offline_mock_only = offline_mock_only
        self.model_gate_authorized = model_gate_authorized
        self.timeout_ms = timeout_ms

    def authorize_provider_scope(self, provider_claim: str) -> None:
        reject_consumer_subscription_entitlement(provider_claim)
        if not self.offline_mock_only and not self.model_gate_authorized:
            raise GateDenialError(
                LIVE_MODEL_ERROR,
                f"External model provider {provider_claim!r} blocked by H2-B default-deny gate",
            )
        if not isinstance(self.provider, (type(None), ScriptedModelProvider)):
            raise GateDenialError(LIVE_MODEL_ERROR, "Non-scripted external model provider denied in offline mode")

    def interpret_and_query(
        self,
        *,
        user_text: str,
        selected_tool: str,
        selected_args: dict[str, Any] | None,
        gateway: QuantV1ReadonlyToolGateway,
    ) -> dict[str, Any]:
        """Select one of 6 allowlisted tools, validate args & envelope, and fall back safely on errors."""
        inj = contains_prompt_injection_or_forbidden_op(user_text)
        if inj is not None:
            return {
                "ok": False,
                "fallback_used": True,
                "fallback_reason": "PROMPT_INJECTION_BLOCKED",
                "tool": None,
                "envelope": None,
                "summary_zh": f"检测到敏感/注入输入 ({inj})，拒绝调用模型或工具。",
            }

        if selected_tool not in V1_MODEL_READONLY_TOOLS:
            return {
                "ok": False,
                "fallback_used": True,
                "fallback_reason": "MODEL_TOOL_NOT_ALLOWED",
                "tool": selected_tool,
                "envelope": None,
                "summary_zh": f"工具 {selected_tool!r} 不在六项只读 V1 允许清单内，已拦截。",
            }

        try:
            env = gateway.call_model_tool(selected_tool, selected_args)
        except ContractError as exc:
            return {
                "ok": False,
                "fallback_used": True,
                "fallback_reason": f"TOOL_ERROR:{exc.code}",
                "tool": selected_tool,
                "envelope": None,
                "summary_zh": f"只读工具调用拒绝 ({exc.code})，未调用模型解释。",
            }

        if not isinstance(env, dict) or env.get("status") not in {"OK", "ERROR"} or "data" not in env:
            return {
                "ok": False,
                "fallback_used": True,
                "fallback_reason": "MALFORMED_TOOL_RESULT",
                "tool": selected_tool,
                "envelope": None,
                "summary_zh": "工具返回格式异常，已回退为安全拒绝。",
            }
        if env["status"] != "OK":
            err = env.get("error") or {}
            return {
                "ok": False,
                "fallback_used": True,
                "fallback_reason": f"FACADE_ERROR:{err.get('code', 'UNKNOWN')}",
                "tool": selected_tool,
                "envelope": env,
                "summary_zh": f"QUANT 核心返回错误 {err.get('code', 'UNKNOWN')}，保持确定性提示。",
            }

        return {
            "ok": True,
            "fallback_used": False,
            "fallback_reason": None,
            "tool": selected_tool,
            "envelope": env,
            "summary_zh": "只读 V1 工具查询完成。",
        }

    def explain_record(
        self,
        record: dict[str, Any],
        *,
        provider_claim: str = "NONE",
    ) -> dict[str, Any]:
        """Explain an existing Snapshot or NO_SETUP/NOT_EVALUATED diagnostic with guaranteed deterministic fallback."""
        if provider_claim != "NONE":
            try:
                reject_consumer_subscription_entitlement(provider_claim)
            except GateDenialError as exc:
                det = (
                    diagnostic_deterministic_fallback(record)
                    if record.get("episode_id") is None
                    else explain_snapshot(record, provider=None).explanation
                )
                return {
                    "explanation": det,
                    "provenance": {
                        "mode": "DETERMINISTIC_FALLBACK",
                        "fallback_used": True,
                        "fallback_reason": exc.code,
                        "detail": exc.message,
                    },
                }

        if not self.offline_mock_only and not self.model_gate_authorized:
            det = (
                diagnostic_deterministic_fallback(record)
                if record.get("episode_id") is None
                else explain_snapshot(record, provider=None).explanation
            )
            return {
                "explanation": det,
                "provenance": {
                    "mode": "DETERMINISTIC_FALLBACK",
                    "fallback_used": True,
                    "fallback_reason": LIVE_MODEL_ERROR,
                },
            }

        if record.get("episode_id") is None or record.get("diagnostic_only") is True:
            det = diagnostic_deterministic_fallback(record)
            if self.provider is None:
                return {
                    "explanation": det,
                    "provenance": {"mode": "DETERMINISTIC_DIAGNOSTIC", "fallback_used": False, "fallback_reason": None},
                }
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    fut = pool.submit(self.provider.generate, record, timeout_ms=self.timeout_ms)
                    raw = fut.result(timeout=self.timeout_ms / 1000.0)
                validated = validate_explanation_payload(record, raw)
                return {
                    "explanation": validated,
                    "provenance": {"mode": "MOCK_AI_DIAGNOSTIC", "fallback_used": False, "fallback_reason": None},
                }
            except BaseException as exc:  # noqa: BLE001
                return {
                    "explanation": det,
                    "provenance": {
                        "mode": "DETERMINISTIC_FALLBACK",
                        "fallback_used": True,
                        "fallback_reason": type(exc).__name__,
                    },
                }

        if self.provider is None:
            outcome = explain_snapshot(record, provider=None)
            return {"explanation": outcome.explanation, "provenance": outcome.provenance}

        # Enforce hard timeout even for blocking scripted sleep before passing into H1 explain_snapshot
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(self.provider.generate, _minimal_context(record), timeout_ms=self.timeout_ms)
                raw = fut.result(timeout=self.timeout_ms / 1000.0)
            validated = validate_explanation_payload(record, raw)
            return {
                "explanation": validated,
                "provenance": {
                    "mode": "AI_VALIDATED",
                    "provider": self.provider.name,
                    "fallback_used": False,
                    "validation_status": "VALIDATED",
                },
            }
        except concurrent.futures.TimeoutError:
            fb = explain_snapshot(record, provider=None).explanation
            return {
                "explanation": fb,
                "provenance": {
                    "mode": "DETERMINISTIC_FALLBACK",
                    "provider": self.provider.name,
                    "fallback_used": True,
                    "fallback_reason": "MODEL_TIMEOUT",
                },
            }
        except asyncio.CancelledError:
            fb = explain_snapshot(record, provider=None).explanation
            return {
                "explanation": fb,
                "provenance": {
                    "mode": "DETERMINISTIC_FALLBACK",
                    "provider": self.provider.name,
                    "fallback_used": True,
                    "fallback_reason": "CANCELLED_OR_LATE_RESPONSE",
                },
            }
        except BaseException:  # noqa: BLE001
            outcome = explain_snapshot(record, provider=self.provider, timeout_ms=self.timeout_ms)
            return {"explanation": outcome.explanation, "provenance": outcome.provenance}


def _minimal_context(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "episode_id": snapshot["episode_id"],
        "card_id": snapshot["card_id"],
        "card_version": snapshot["card_version"],
        "symbol": snapshot["symbol"],
        "market_status": snapshot["market_status"],
        "status_reason_codes": snapshot["status_reason_codes"],
        "source_evidence_class": snapshot["source_evidence_class"],
    }
