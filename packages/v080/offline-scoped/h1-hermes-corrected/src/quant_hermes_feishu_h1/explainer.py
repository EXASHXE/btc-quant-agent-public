"""Optional, out-of-band, schema- and fact-validated signal explanation with deterministic fallback."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Protocol

from .contract import CONTRACT_VERSION, ContractError, validate_decimal_strings_only

EXPLANATION_SCHEMA_VERSION = "H1_EXPLANATION_V1"

_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_FORBIDDEN_UPGRADE_PATTERNS = (
    "升级为可执行",
    "视同executable",
    "视同可执行",
    "建议立即市价入场",
    "立即满仓",
    "保证盈利",
    "稳赚",
    "必胜",
    "账户已校验安全",
    "guaranteed profit",
    "promote to executable",
)
_ALLOWED_STRUCTURAL_NUMBERS = frozenset({"1", "2", "3", "4", "5", "10", "15", "24", "30", "45"})

_REASON_EXPLANATIONS_ZH: dict[str, str] = {
    "INDEPENDENT_15M_PENDING": "1H 形态已冻结候选，但尚未完成独立延迟的 15m 收盘确认，当前保持 WATCH 观察。",
    "MARKET_SIDE_ELIGIBLE_SYNTHETIC": "已完成独立 15m 触发及 5m 成本/不追价检查（仅合成测试市场侧通过，账户不可用）。",
    "TP1_AFTER_COST_R_INSUFFICIENT": "复价时按当前买一/卖一盘口及费用滑点重算，TP1 扣费后净 R 低于最小门槛，降回 WATCH。",
    "SYMBOL_INPUT_BLOCKED": "标的行情输入被阻断或存在过期报价（SOURCE_BLOCKED），禁止给出可执行判断。",
    "STRUCTURAL_INVALIDATION": "价格已触及硬止损或结构失效位，Episode 终止为 INVALID。",
    "MISSED_NO_CHASE": "触发前已提前触及目标或超出不追价边界（NO-CHASE），Episode 终止为 INVALID。",
    "TERMINAL_EPISODE": "该 Episode 已进入终态 INVALID，不会再重新激活。",
    "4H_REGIME_PAUSED": "4H 趋势结构进入暂停/区间状态，保持 WATCH 等待方向恢复。",
    "EPISODE_EXPIRED": "已达到绝对过期时间（absolute_expiry_ms），信号失效。",
}


class ExplanationProvider(Protocol):
    """Protocol for an optional out-of-band explanation provider (mocked in H1 offline QA)."""

    name: str

    def generate(self, context: dict[str, Any], *, timeout_ms: int) -> str | dict[str, Any]:
        ...


def build_explanation_context(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Build minimal validated numeric/status context with zero secrets or raw file paths."""
    plan = snapshot.get("plan")
    compact_plan: dict[str, Any] | None = None
    if isinstance(plan, dict):
        compact_plan = {
            "entry_low": plan.get("entry_low"),
            "entry_high": plan.get("entry_high"),
            "hard_stop": plan.get("hard_stop"),
            "no_chase_boundary": plan.get("no_chase_boundary"),
            "targets": [
                {"label": t.get("label"), "price": t.get("price"), "net_r": t.get("net_r"), "status": t.get("status")}
                for t in (plan.get("targets") or [])
            ],
            "first_obstacle_after_cost_r": plan.get("first_obstacle_after_cost_r"),
            "unit_stop_loss_usdt": plan.get("unit_stop_loss_usdt"),
        }
    return {
        "contract_version": CONTRACT_VERSION,
        "episode_id": snapshot["episode_id"],
        "card_id": snapshot["card_id"],
        "card_version": snapshot["card_version"],
        "symbol": snapshot["symbol"],
        "direction": snapshot["direction"],
        "strategy_family": snapshot["strategy_family"],
        "market_status": snapshot["market_status"],
        "status_reason_codes": list(snapshot["status_reason_codes"]),
        "source_evidence_class": snapshot["source_evidence_class"],
        "freshness_state": snapshot["freshness_state"],
        "expiry_status": snapshot["expiry_status"],
        "account_context_status": snapshot["account_context_status"],
        "plan": compact_plan,
    }


def _collect_allowed_numeric_strings(snapshot: dict[str, Any]) -> set[str]:
    allowed = set(_ALLOWED_STRUCTURAL_NUMBERS)
    plan = snapshot.get("plan")
    if isinstance(plan, dict):
        for key in (
            "entry_low",
            "entry_high",
            "hard_stop",
            "no_chase_boundary",
            "unit_stop_loss_usdt",
            "first_obstacle_after_cost_r",
            "spread_usdt",
            "fee_rate_each_side",
            "slippage_bps_each_side",
            "mark",
            "index",
            "bid",
            "ask",
        ):
            val = plan.get(key)
            if isinstance(val, str):
                allowed.add(val)
        for t in plan.get("targets") or []:
            if isinstance(t, dict):
                for tk in ("price", "net_r", "geometric_r"):
                    if isinstance(t.get(tk), str):
                        allowed.add(t[tk])
    return allowed


def deterministic_fallback_explanation(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Generate a strictly grounded model-free explanation directly from Core facts."""
    reasons = snapshot["status_reason_codes"]
    parts = [
        (
            f"[{snapshot['source_evidence_class']}] {snapshot['symbol']} ({snapshot['direction']} / {snapshot['strategy_family']}) "
            f"当前核心状态为 {snapshot['market_status']}。"
        )
    ]
    for code in reasons:
        parts.append(f"{code}: {_REASON_EXPLANATIONS_ZH.get(code, '遵循核心原因码。')}")
    plan = snapshot.get("plan")
    if isinstance(plan, dict) and plan.get("entry_low") and plan.get("hard_stop"):
        parts.append(
            f"核心价格参数: 入场 {plan['entry_low']}-{plan['entry_high']} USDT，硬止损 {plan['hard_stop']} USDT。"
        )
    parts.append(
        f"账户上下文={snapshot['account_context_status']} ({snapshot['account_overlay']})，"
        "需人工校验账户敞口与手续费。"
    )
    return {
        "schema_version": EXPLANATION_SCHEMA_VERSION,
        "card_id": snapshot["card_id"],
        "card_version": snapshot["card_version"],
        "market_status": snapshot["market_status"],
        "referenced_reason_codes": list(reasons),
        "summary_zh": " ".join(parts),
        "advisory_only": True,
    }


def validate_explanation_payload(snapshot: dict[str, Any], raw: str | dict[str, Any]) -> dict[str, Any]:
    """Validate optional LLM explanation strictly against immutable Core snapshot facts."""
    if isinstance(raw, str):
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ContractError("INTEGRITY_FAILURE", f"Explanation JSON parse failed: {exc}") from exc
    elif isinstance(raw, dict):
        payload = raw
    else:
        raise ContractError("INTEGRITY_FAILURE", "Explanation payload must be JSON string or dict")

    if not isinstance(payload, dict):
        raise ContractError("INTEGRITY_FAILURE", "Explanation must be a JSON object")
    validate_decimal_strings_only(payload, path="explanation")

    required = {
        "schema_version",
        "card_id",
        "card_version",
        "market_status",
        "referenced_reason_codes",
        "summary_zh",
        "advisory_only",
    }
    missing = required - set(payload.keys())
    if missing:
        raise ContractError("INTEGRITY_FAILURE", f"Explanation missing keys: {sorted(missing)}")
    if payload["schema_version"] != EXPLANATION_SCHEMA_VERSION:
        raise ContractError("INTEGRITY_FAILURE", "Explanation schema_version mismatch")
    if payload["card_id"] != snapshot["card_id"] or payload["card_version"] != snapshot["card_version"]:
        raise ContractError("INTEGRITY_FAILURE", "Explanation bound to wrong card_id or card_version")
    if payload["market_status"] != snapshot["market_status"]:
        raise ContractError(
            "INTEGRITY_FAILURE",
            f"Explanation attempted status rewrite {payload['market_status']!r} != {snapshot['market_status']!r}",
        )
    if payload["advisory_only"] is not True:
        raise ContractError("INTEGRITY_FAILURE", "Explanation must declare advisory_only=True")

    ref_reasons = payload["referenced_reason_codes"]
    if not isinstance(ref_reasons, list) or not set(ref_reasons).issubset(set(snapshot["status_reason_codes"])):
        raise ContractError("INTEGRITY_FAILURE", "Explanation invented unverified reason codes")

    summary = payload["summary_zh"]
    if type(summary) is not str or not summary.strip() or len(summary) > 800:
        raise ContractError("INTEGRITY_FAILURE", "Invalid explanation summary_zh length")

    lower = summary.lower()
    for pat in _FORBIDDEN_UPGRADE_PATTERNS:
        if pat in lower:
            raise ContractError("INTEGRITY_FAILURE", f"Explanation contains prohibited advisory/upgrade text: {pat!r}")

    if snapshot["market_status"] != "EXECUTABLE" and "executable" in lower:
        allowed_neg = ("非 executable", "不是 executable", "尚未达到 executable", "not executable")
        if not any(tok in lower for tok in allowed_neg):
            raise ContractError("INTEGRITY_FAILURE", "Non-EXECUTABLE card explanation claimed EXECUTABLE")

    allowed_nums = _collect_allowed_numeric_strings(snapshot)
    stripped = re.sub(r"\b(?:TP[123]|1d|4h|1h|15m|5m|\+5m?|\+10m?)\b", " ", summary, flags=re.IGNORECASE)
    for num in _NUMBER_RE.findall(stripped):
        if num not in allowed_nums:
            raise ContractError(
                "INTEGRITY_FAILURE",
                f"Explanation cited ungrounded numeric value {num!r} not present in Core snapshot",
            )
    return payload


@dataclass(frozen=True)
class ExplanationOutcome:
    """Separate explanation + provenance envelope; never merged into SignalSnapshot."""

    explanation: dict[str, Any]
    provenance: dict[str, Any]


def explain_snapshot(
    snapshot: dict[str, Any],
    *,
    provider: ExplanationProvider | None = None,
    timeout_ms: int = 800,
) -> ExplanationOutcome:
    """Produce optional explanation completely outside immediate alert critical path."""
    if provider is None:
        return ExplanationOutcome(
            explanation=deterministic_fallback_explanation(snapshot),
            provenance={
                "mode": "DETERMINISTIC_MODEL_FREE",
                "provider": "none",
                "fallback_used": False,
                "validation_status": "DETERMINISTIC",
                "latency_ms": 0.0,
                "error_code": None,
            },
        )

    context = build_explanation_context(snapshot)
    t0 = time.monotonic_ns()
    try:
        raw = provider.generate(context, timeout_ms=timeout_ms)
        elapsed_ms = (time.monotonic_ns() - t0) / 1_000_000.0
        if elapsed_ms > timeout_ms:
            raise ContractError("TIMEOUT", f"Explanation provider exceeded timeout_ms={timeout_ms}")
        validated = validate_explanation_payload(snapshot, raw)
        return ExplanationOutcome(
            explanation=validated,
            provenance={
                "mode": "MODEL_VALIDATED",
                "provider": provider.name,
                "fallback_used": False,
                "validation_status": "PASSED",
                "latency_ms": round(elapsed_ms, 3),
                "error_code": None,
            },
        )
    except ContractError as exc:
        elapsed_ms = (time.monotonic_ns() - t0) / 1_000_000.0
        return ExplanationOutcome(
            explanation=deterministic_fallback_explanation(snapshot),
            provenance={
                "mode": "DETERMINISTIC_FALLBACK",
                "provider": provider.name,
                "fallback_used": True,
                "validation_status": "REJECTED",
                "latency_ms": round(elapsed_ms, 3),
                "error_code": exc.code,
                "reason": exc.message,
            },
        )
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = (time.monotonic_ns() - t0) / 1_000_000.0
        err_code = "TIMEOUT" if "timeout" in str(exc).lower() else "RATE_LIMITED" if "429" in str(exc) or "quota" in str(exc).lower() else "SOURCE_UNAVAILABLE"
        return ExplanationOutcome(
            explanation=deterministic_fallback_explanation(snapshot),
            provenance={
                "mode": "DETERMINISTIC_FALLBACK",
                "provider": provider.name,
                "fallback_used": True,
                "validation_status": "PROVIDER_ERROR",
                "latency_ms": round(elapsed_ms, 3),
                "error_code": err_code,
                "reason": str(exc)[:200],
            },
        )


class MockValidExplainer:
    name = "mock-valid-explainer"

    def generate(self, context: dict[str, Any], *, timeout_ms: int) -> str:
        del timeout_ms
        reasons = context["status_reason_codes"]
        plan = context.get("plan") or {}
        if plan.get("entry_low") and plan.get("hard_stop"):
            plan_part = f"核心入场区 {plan['entry_low']}-{plan['entry_high']}，硬止损 {plan['hard_stop']}。"
        else:
            plan_part = "暂无完整执行计划。"
        summary = (
            f"[{context['source_evidence_class']}] {context['symbol']} {context['direction']} "
            f"保持核心状态 {context['market_status']}，原因码 {', '.join(reasons)}。{plan_part} "
            f"账户状态 {context['account_context_status']}。"
        )
        return json.dumps({
            "schema_version": EXPLANATION_SCHEMA_VERSION,
            "card_id": context["card_id"],
            "card_version": context["card_version"],
            "market_status": context["market_status"],
            "referenced_reason_codes": reasons,
            "summary_zh": summary,
            "advisory_only": True,
        }, ensure_ascii=False)


class MockHallucinatingExplainer:
    name = "mock-hallucinating-explainer"

    def __init__(self, *, mode: str = "invented_price") -> None:
        self.mode = mode

    def generate(self, context: dict[str, Any], *, timeout_ms: int) -> str:
        del timeout_ms
        if self.mode == "status_upgrade":
            return json.dumps({
                "schema_version": EXPLANATION_SCHEMA_VERSION,
                "card_id": context["card_id"],
                "card_version": context["card_version"],
                "market_status": "EXECUTABLE",
                "referenced_reason_codes": context["status_reason_codes"],
                "summary_zh": "该信号已升级为可执行，建议立即市价入场。",
                "advisory_only": True,
            }, ensure_ascii=False)
        if self.mode == "bad_json":
            return "{not valid json"
        return json.dumps({
            "schema_version": EXPLANATION_SCHEMA_VERSION,
            "card_id": context["card_id"],
            "card_version": context["card_version"],
            "market_status": context["market_status"],
            "referenced_reason_codes": context["status_reason_codes"],
            "summary_zh": "建议在 98765.43 买入，目标 123456.78，稳赚。",
            "advisory_only": True,
        }, ensure_ascii=False)


class MockFailingExplainer:
    name = "mock-failing-explainer"

    def __init__(self, *, mode: str = "quota_exhausted") -> None:
        self.mode = mode

    def generate(self, context: dict[str, Any], *, timeout_ms: int) -> str:
        del context, timeout_ms
        if self.mode == "timeout":
            raise TimeoutError("Mock LLM request timeout")
        if self.mode == "quota_exhausted":
            raise RuntimeError("429 RESOURCE_EXHAUSTED: model quota exhausted")
        raise RuntimeError("503 upstream model provider unavailable")
