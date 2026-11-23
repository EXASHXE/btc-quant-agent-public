"""Path B offline Feishu private DM chat router, allowlist guard, injection defense, and Gateway adapter hook."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from .contract import ContractError
from .explainer import ExplanationProvider, explain_snapshot
from .facade import QuantFacadeClient
from .renderer import (
    render_active_signals_list,
    render_history_list,
    render_reprice_result,
    render_signal_alert,
    render_strategy_summary,
    render_suppressed_notice,
)

_EPISODE_HEX_RE = re.compile(r"\b([0-9a-f]{8,64})\b")
_SYMBOL_RE = re.compile(r"\b(BTCUSDT|ETHUSDT|SOLUSDT)\b", re.IGNORECASE)
_FAMILY_RE = re.compile(r"\b(TREND_PULLBACK|EARLY_CONTINUATION)\b", re.IGNORECASE)

_INJECTION_PATTERNS = (
    "忽略之前",
    "忽略上述",
    "ignore previous",
    "ignore all prior",
    "system prompt",
    "升级为 executable",
    "改成 executable",
    "改写为可执行",
    "帮我下单",
    "市价买入",
    "市价卖出",
    "select ",
    "drop table",
    "union select",
    "terminal",
    "bash",
    "cat ~/.hermes",
    "/root/",
    ".env",
    "private_user_data",
    "app_secret",
    "api_secret",
)


@dataclass(frozen=True)
class FeishuInboundEvent:
    """Normalized Feishu inbound message/callback event for offline gateway simulation."""

    message_id: str
    chat_id: str
    chat_type: str  # "p2p" | "group" | ...
    sender_open_id: str
    sender_type: str  # "user" | "bot" | "app"
    text: str
    event_ts_ms: int
    sender_union_id: str | None = None
    bot_open_id: str = "ou_quant_bot_self"
    is_callback: bool = False
    callback_token: str | None = None
    raw_quote_text: str | None = None


@dataclass
class ChatSessionState:
    """Isolated per-(owner, chat) session memory; never shared across chats or users."""

    last_episode_id: str | None = None
    last_symbol: str | None = None
    turn_count: int = 0


def strip_quoted_spoof_segments(text: str) -> str:
    """Strip markdown quote lines and Feishu forward/quote blocks so quoted fake commands never execute."""
    kept: list[str] = []
    for raw_line in text.splitlines():
        s = raw_line.strip()
        if s.startswith((">", "「引用", "回复:", "回复：")):
            continue
        if s.startswith(("[引用", "--- 引用")):
            continue
        kept.append(raw_line)
    return "\n".join(kept).strip()


def contains_prompt_injection_or_forbidden_op(text: str) -> str | None:
    """Detect prompt injection, SQL injection, path traversal, or unauthorized trade/secret requests."""
    lower = text.lower()
    for pat in _INJECTION_PATTERNS:
        if pat in lower:
            return pat
    # Avoid false positives on valid 8..64-hex episode_id/card_id digests containing 'b3' (e.g. 'eb3e')
    scrubbed_hex = re.sub(r"\b[0-9a-f]{8,64}\b", " ", lower)
    if "b3" in scrubbed_hex:
        return "b3"
    return None


def parse_strict_chinese_command(
    clean_text: str,
    *,
    session: ChatSessionState,
) -> tuple[str, dict[str, Any]]:
    """Parse exact Chinese commands or strict allowlisted natural-language phrases into tool intents."""
    t = clean_text.strip()
    if not t:
        raise ContractError("INVALID_ARGUMENT", "Empty command after quote filtering")

    # 1. Explicit reprice mutation request -> always routes to disabled request_reprice
    if any(k in t for k in ("request_reprice", "执行复价", "立即复价", "强制复价", "触发复价")):
        ep = _extract_episode_token(t) or session.last_episode_id or "0" * 64
        return "request_reprice", {
            "episode_id": ep,
            "idempotency_key": f"chat-{int(time.time_ns() // 1_000_000)}",
            "desired_delay_minutes": 5,
        }

    # 2. 当前机会
    if t == "当前机会" or t.startswith("当前机会 ") or any(p in t for p in ("有什么机会", "现在有哪些信号", "查看当前机会")):
        return "list_active_signals", {"limit": 20}

    # 3. 策略说明
    if t.startswith("策略说明") or any(p in t for p in ("策略逻辑", "策略介绍", "怎么判断setup")):
        fam_m = _FAMILY_RE.search(t)
        args: dict[str, Any] = {}
        if fam_m:
            args["family"] = fam_m.group(1).upper()
        return "get_strategy_summary", args

    # 4. 最近信号
    if t.startswith("最近信号") or any(p in t for p in ("信号历史", "最近有哪些信号", "历史记录")):
        sym_m = _SYMBOL_RE.search(t)
        args = {"limit": 10}
        if sym_m:
            args["symbol"] = sym_m.group(1).upper()
        return "get_signal_history", args

    # 5. 复价 (read-only latest recorded +5/+10 reprice)
    if t.startswith("复价") or "复价结果" in t or "最新复价" in t:
        ep = _extract_episode_token(t)
        sym_m = _SYMBOL_RE.search(t)
        return "get_latest_reprice", {
            "episode_id": ep,
            "symbol": sym_m.group(1).upper() if sym_m else None,
        }

    # 6. 为什么 WATCH / 为什么 <status|episode|symbol>
    if t.startswith("为什么") or "为什么还在观察" in t or "解释一下" in t:
        ep = _extract_episode_token(t)
        sym_m = _SYMBOL_RE.search(t)
        target_status = None
        for st in ("WATCH", "EXECUTABLE", "INVALID", "SOURCE_BLOCKED", "NO_SETUP"):
            if st in t.upper():
                target_status = st
                break
        return "explain_signal", {
            "episode_id": ep,
            "symbol": sym_m.group(1).upper() if sym_m else None,
            "target_status": target_status,
        }

    # 7. 查看 BTCUSDT / 查看 episode
    if t.startswith("查看") or _SYMBOL_RE.search(t):
        ep = _extract_episode_token(t)
        sym_m = _SYMBOL_RE.search(t)
        if ep or sym_m:
            return "get_signal_detail", {
                "episode_id": ep,
                "symbol": sym_m.group(1).upper() if sym_m else None,
            }
        raise ContractError("INVALID_ARGUMENT", "未识别查询目标；请使用 `查看 BTCUSDT` 或 `查看 <episode_id>`")

    raise ContractError(
        "INVALID_ARGUMENT",
        "未识别指令。支持指令: 当前机会 / 查看 BTCUSDT / 查看 <episode_id> / 为什么 WATCH / 复价 / 最近信号 / 策略说明",
    )


def _extract_episode_token(text: str) -> str | None:
    m = _EPISODE_HEX_RE.search(text)
    if m:
        return m.group(1).lower()
    return None


@dataclass
class FeishuChatService:
    """Offline private DM Feishu conversational handler backed ONLY by QuantFacadeClient."""

    facade_client: QuantFacadeClient
    allowed_owner_open_ids: frozenset[str]
    owner_chat_bindings: dict[str, str]  # sender_open_id -> authorized p2p chat_id
    bot_open_id: str = "ou_quant_bot_self"
    expected_callback_token: str | None = "offline_cb_token"
    max_callback_age_ms: int = 300_000
    explanation_provider: ExplanationProvider | None = None
    sessions: dict[tuple[str, str], ChatSessionState] = field(default_factory=dict)
    seen_message_ids: set[str] = field(default_factory=set)
    audit_events: list[dict[str, Any]] = field(default_factory=list)

    def handle_inbound(
        self,
        event: FeishuInboundEvent,
        *,
        now_ms: int | None = None,
        as_of_ms: int | None = None,
    ) -> dict[str, Any]:
        """Authenticate, isolate, route, recheck Core status, and render reply."""
        cur_ms = now_ms if now_ms is not None else (time.time_ns() // 1_000_000)

        # 1. Duplicate message check
        if not event.message_id or event.message_id in self.seen_message_ids:
            return self._reject(event, "DUPLICATE_OR_MISSING_MESSAGE_ID", "重复或无效消息ID，已忽略。", cur_ms)
        self.seen_message_ids.add(event.message_id)

        # 2. Bot-self / bot echo check
        if event.sender_type in {"bot", "app"} or event.sender_open_id == self.bot_open_id:
            return self._reject(event, "BOT_SELF_EVENT_REJECTED", "拒绝处理机器人自身或第三方机器人事件。", cur_ms)

        # 3. Private DM only
        if event.chat_type != "p2p":
            return self._reject(event, "UNAUTHORIZED_GROUP_CHAT", "拒绝群聊请求：当前仅授权 Owner 私聊 (p2p DM)。", cur_ms)

        # 4. Owner allowlist + explicit chat identity binding (prevents forged chat_id / cross-chat spoof)
        if event.sender_open_id not in self.allowed_owner_open_ids:
            return self._reject(event, "UNAUTHORIZED_USER", "未授权用户：仅允许 Owner 列表访问。", cur_ms)
        bound_chat = self.owner_chat_bindings.get(event.sender_open_id)
        if bound_chat is None or event.chat_id != bound_chat:
            return self._reject(event, "CHAT_IDENTITY_MISMATCH", "会话 chat_id 与授权私聊绑定不一致。", cur_ms)

        # 5. Stale callback / token check
        if event.is_callback:
            if self.expected_callback_token and event.callback_token != self.expected_callback_token:
                return self._reject(event, "INVALID_CALLBACK_TOKEN", "回调校验令牌无效。", cur_ms)
            if cur_ms - event.event_ts_ms > self.max_callback_age_ms:
                return self._reject(event, "STALE_CALLBACK_IGNORED", "回调已过期，请重新查询最新状态。", cur_ms)

        # 6. Strip quoted lines & block prompt injection / forbidden commands
        clean_text = strip_quoted_spoof_segments(event.text)
        inj = contains_prompt_injection_or_forbidden_op(clean_text)
        if inj is not None:
            return self._reject(
                event,
                "PROMPT_INJECTION_OR_FORBIDDEN_INPUT",
                f"输入包含受禁操作或越权指令特征 ({inj})，已拒绝。仅支持只读 QUANT V1 查询。",
                cur_ms,
            )

        session_key = (event.sender_open_id, event.chat_id)
        session = self.sessions.setdefault(session_key, ChatSessionState())
        session.turn_count += 1

        try:
            intent, args = parse_strict_chinese_command(clean_text, session=session)
        except ContractError as exc:
            return self._reject(event, exc.code, exc.message, cur_ms)

        return self._execute_intent(
            event=event,
            session=session,
            intent=intent,
            args=args,
            now_ms=cur_ms,
            as_of_ms=as_of_ms,
        )

    def _reject(self, event: FeishuInboundEvent, code: str, reply_text: str, ts_ms: int) -> dict[str, Any]:
        rec = {
            "accepted": False,
            "error_code": code,
            "message_id": event.message_id,
            "chat_id": event.chat_id,
            "sender_open_id": event.sender_open_id,
            "reply_text": f"[拒绝 / {code}] {reply_text}",
            "ts_ms": ts_ms,
        }
        self.audit_events.append({k: v for k, v in rec.items() if k != "reply_text"})
        return rec

    def _resolve_episode_id(
        self,
        *,
        episode_token: str | None,
        symbol: str | None,
        target_status: str | None,
        session: ChatSessionState,
        as_of_ms: int | None,
    ) -> str:
        if episode_token and len(episode_token) == 64:
            return episode_token

        hist_args: dict[str, Any] = {"limit": 50}
        if symbol:
            hist_args["symbol"] = symbol
        elif session.last_symbol and not episode_token and not target_status:
            hist_args["symbol"] = session.last_symbol
        if as_of_ms is not None:
            hist_args["end_ms"] = as_of_ms

        hist_resp = self.facade_client.call_tool("get_signal_history", hist_args)
        if hist_resp.get("status") != "OK":
            err = hist_resp.get("error") or {}
            raise ContractError(err.get("code", "SOURCE_UNAVAILABLE"), err.get("message", "History lookup failed"))

        items = hist_resp["data"]["history"]
        if episode_token:
            matches = sorted({
                item["episode_id"]
                for item in items
                if item.get("episode_id") and str(item["episode_id"]).startswith(episode_token)
            })
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                raise ContractError("INVALID_ARGUMENT", f"episode 前缀 {episode_token} 匹配多条记录，请提供完整 episode_id")
            raise ContractError("NOT_FOUND", f"未找到 episode {episode_token}")

        if target_status:
            for item in items:
                if item.get("market_status") == target_status and item.get("episode_id"):
                    return str(item["episode_id"])

        if session.last_episode_id and not symbol:
            return session.last_episode_id

        for item in items:
            if item.get("episode_id"):
                return str(item["episode_id"])
        raise ContractError("NOT_FOUND", "当前没有匹配的信号 Episode")

    def _execute_intent(
        self,
        *,
        event: FeishuInboundEvent,
        session: ChatSessionState,
        intent: str,
        args: dict[str, Any],
        now_ms: int,
        as_of_ms: int | None,
    ) -> dict[str, Any]:
        t0 = time.monotonic_ns()
        tool_latency_ms = 0.0
        model_latency_ms = 0.0
        recheck_latency_ms = 0.0
        explanation_provenance: dict[str, Any] | None = None
        explanation_payload: dict[str, Any] | None = None

        try:
            if intent == "request_reprice":
                t_tool = time.monotonic_ns()
                resp = self.facade_client.call_tool(
                    "request_reprice",
                    {
                        "episode_id": args["episode_id"],
                        "idempotency_key": args["idempotency_key"],
                        "desired_delay_minutes": args["desired_delay_minutes"],
                        "requested_by": event.sender_open_id,
                    },
                )
                tool_latency_ms = (time.monotonic_ns() - t_tool) / 1_000_000.0
                err = resp.get("error") or {}
                code = str(err.get("code") or "REPRICE_NOT_AUTHORIZED")
                reply = f"[只读拒绝 / {code}] {err.get('message', 'request_reprice 在 H1 中默认禁用，未发起行情请求。')}"
                return self._finish_ok(
                    event, intent, reply, now_ms,
                    tool_ms=tool_latency_ms, model_ms=0.0, recheck_ms=0.0,
                    total_ms=(time.monotonic_ns() - t0) / 1_000_000.0,
                    error_code=code,
                )

            if intent == "list_active_signals":
                call_args = dict(args)
                if as_of_ms is not None:
                    call_args["as_of_ms"] = as_of_ms
                t_tool = time.monotonic_ns()
                resp = self.facade_client.call_tool("list_active_signals", call_args)
                tool_latency_ms = (time.monotonic_ns() - t_tool) / 1_000_000.0
                if resp.get("status") != "OK":
                    raise _resp_error(resp)
                signals = resp["data"].get("signals") or []
                if signals:
                    session.last_episode_id = signals[0].get("episode_id")
                    session.last_symbol = signals[0].get("symbol")
                reply = render_active_signals_list(resp["data"])
                return self._finish_ok(
                    event, intent, reply, now_ms,
                    tool_ms=tool_latency_ms, model_ms=0.0, recheck_ms=0.0,
                    total_ms=(time.monotonic_ns() - t0) / 1_000_000.0,
                )

            if intent == "get_strategy_summary":
                t_tool = time.monotonic_ns()
                resp = self.facade_client.call_tool("get_strategy_summary", args)
                tool_latency_ms = (time.monotonic_ns() - t_tool) / 1_000_000.0
                if resp.get("status") != "OK":
                    raise _resp_error(resp)
                reply = render_strategy_summary(resp["data"])
                return self._finish_ok(
                    event, intent, reply, now_ms,
                    tool_ms=tool_latency_ms, model_ms=0.0, recheck_ms=0.0,
                    total_ms=(time.monotonic_ns() - t0) / 1_000_000.0,
                )

            if intent == "get_signal_history":
                call_args = dict(args)
                if as_of_ms is not None:
                    call_args["end_ms"] = as_of_ms
                t_tool = time.monotonic_ns()
                resp = self.facade_client.call_tool("get_signal_history", call_args)
                tool_latency_ms = (time.monotonic_ns() - t_tool) / 1_000_000.0
                if resp.get("status") != "OK":
                    raise _resp_error(resp)
                hist = resp["data"].get("history") or []
                if hist:
                    session.last_episode_id = hist[0].get("episode_id")
                    session.last_symbol = hist[0].get("symbol")
                reply = render_history_list(resp["data"])
                return self._finish_ok(
                    event, intent, reply, now_ms,
                    tool_ms=tool_latency_ms, model_ms=0.0, recheck_ms=0.0,
                    total_ms=(time.monotonic_ns() - t0) / 1_000_000.0,
                )

            if intent == "get_latest_reprice":
                t_tool = time.monotonic_ns()
                ep_id = self._resolve_episode_id(
                    episode_token=args.get("episode_id"),
                    symbol=args.get("symbol"),
                    target_status=None,
                    session=session,
                    as_of_ms=as_of_ms,
                )
                call_args: dict[str, Any] = {"episode_id": ep_id}
                if as_of_ms is not None:
                    call_args["as_of_ms"] = as_of_ms
                resp = self.facade_client.call_tool("get_latest_reprice", call_args)
                tool_latency_ms = (time.monotonic_ns() - t_tool) / 1_000_000.0
                if resp.get("status") != "OK":
                    raise _resp_error(resp)
                session.last_episode_id = ep_id
                snap = resp["data"].get("snapshot")
                if snap:
                    session.last_symbol = snap.get("symbol")
                reply = render_reprice_result(resp["data"])
                return self._finish_ok(
                    event, intent, reply, now_ms,
                    tool_ms=tool_latency_ms, model_ms=0.0, recheck_ms=0.0,
                    total_ms=(time.monotonic_ns() - t0) / 1_000_000.0,
                )

            if intent in {"get_signal_detail", "explain_signal"}:
                t_tool = time.monotonic_ns()
                ep_id = self._resolve_episode_id(
                    episode_token=args.get("episode_id"),
                    symbol=args.get("symbol"),
                    target_status=args.get("target_status"),
                    session=session,
                    as_of_ms=as_of_ms,
                )
                detail_args: dict[str, Any] = {"episode_id": ep_id}
                if as_of_ms is not None:
                    detail_args["as_of_ms"] = as_of_ms
                resp = self.facade_client.call_tool("get_signal_detail", detail_args)
                tool_latency_ms = (time.monotonic_ns() - t_tool) / 1_000_000.0
                if resp.get("status") != "OK":
                    raise _resp_error(resp)
                snap = resp["data"]["snapshot"]
                session.last_episode_id = ep_id
                session.last_symbol = snap["symbol"]

                if intent == "explain_signal":
                    outcome = explain_snapshot(snap, provider=self.explanation_provider)
                    explanation_payload = outcome.explanation
                    explanation_provenance = outcome.provenance
                    model_latency_ms = float(outcome.provenance.get("latency_ms", 0.0))

                # Mandatory immediate-before-reply status & expiry recheck (Contract V1 §5)
                t_recheck = time.monotonic_ns()
                recheck = self.facade_client.call_tool("get_signal_detail", detail_args)
                recheck_latency_ms = (time.monotonic_ns() - t_recheck) / 1_000_000.0
                if recheck.get("status") != "OK":
                    raise _resp_error(recheck)
                latest_snap = recheck["data"]["snapshot"]

                if latest_snap["is_expired"] or latest_snap["market_status"] in {"INVALID", "SOURCE_BLOCKED"}:
                    sup_reason = "EXPIRED" if latest_snap["is_expired"] else latest_snap["market_status"]
                    reply = render_suppressed_notice(latest_snap, suppression_reason=sup_reason)
                else:
                    reply = render_signal_alert(latest_snap)

                if explanation_payload is not None and explanation_provenance is not None:
                    reply = (
                        f"{reply}\n\n"
                        f"[附加说明 / {explanation_provenance['mode']} / advisory_only=true]\n"
                        f"{explanation_payload['summary_zh']}"
                    )

                return self._finish_ok(
                    event, intent, reply, now_ms,
                    tool_ms=tool_latency_ms,
                    model_ms=model_latency_ms,
                    recheck_ms=recheck_latency_ms,
                    total_ms=(time.monotonic_ns() - t0) / 1_000_000.0,
                    explanation=explanation_payload,
                    explanation_provenance=explanation_provenance,
                )

            raise ContractError("UNKNOWN_TOOL", f"Unsupported chat intent: {intent}")
        except ContractError as exc:
            return self._reject(event, exc.code, exc.message, now_ms)

    def _finish_ok(
        self,
        event: FeishuInboundEvent,
        intent: str,
        reply_text: str,
        ts_ms: int,
        *,
        tool_ms: float,
        model_ms: float,
        recheck_ms: float,
        total_ms: float,
        error_code: str | None = None,
        explanation: dict[str, Any] | None = None,
        explanation_provenance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        rec: dict[str, Any] = {
            "accepted": True,
            "intent": intent,
            "error_code": error_code,
            "message_id": event.message_id,
            "chat_id": event.chat_id,
            "sender_open_id": event.sender_open_id,
            "reply_text": reply_text,
            "tool_latency_ms": round(tool_ms, 3),
            "model_latency_ms": round(model_ms, 3),
            "recheck_latency_ms": round(recheck_ms, 3),
            "total_latency_ms": round(total_ms, 3),
            "explanation": explanation,
            "explanation_provenance": explanation_provenance,
            "ts_ms": ts_ms,
        }
        self.audit_events.append({
            "accepted": True,
            "intent": intent,
            "error_code": error_code,
            "message_id": event.message_id,
            "chat_id": event.chat_id,
            "sender_open_id": event.sender_open_id,
            "tool_latency_ms": rec["tool_latency_ms"],
            "model_latency_ms": rec["model_latency_ms"],
            "recheck_latency_ms": rec["recheck_latency_ms"],
            "total_latency_ms": rec["total_latency_ms"],
            "ts_ms": ts_ms,
        })
        return rec


def _resp_error(resp: dict[str, Any]) -> ContractError:
    err = resp.get("error") or {}
    return ContractError(
        str(err.get("code") or "INTERNAL_REDACTED"),
        str(err.get("message") or "Facade returned error"),
    )
