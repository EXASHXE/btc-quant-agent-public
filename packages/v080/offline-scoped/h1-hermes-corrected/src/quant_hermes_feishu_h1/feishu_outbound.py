"""Path A Feishu outbound delivery: pure mock adapter + Hermes v0.16.0 _send_feishu adapter."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from .outbox import DeliveryResult

_FEISHU_CONFIG_DIR_PERMS = 0o700


@dataclass
class ScriptedOutcome:
    classification: str  # PROVIDER_ACK | RETRYABLE | PERMANENT | UNKNOWN_DELIVERY
    message_id: str | None = None
    http_status: int | None = None
    error_code: str | None = None
    error_detail: str | None = None
    ack_delay_ms: int = 1


class MockFeishuTransport:
    """Offline mock Feishu transport supporting scripted 429/5xx/403/timeout/delayed-ack scenarios."""

    def __init__(self, scripted: list[ScriptedOutcome] | None = None) -> None:
        self._scripted = list(scripted or [])
        self.sent_records: list[dict[str, Any]] = []
        self._seq = 0

    def send_text(
        self,
        *,
        channel: str,
        recipient: str,
        text: str,
        event_id: str,
        attempt: int,
    ) -> DeliveryResult:
        self._seq += 1
        outcome = (
            self._scripted.pop(0)
            if self._scripted
            else ScriptedOutcome(
                classification="PROVIDER_ACK",
                message_id=f"om_mock_{self._seq:06d}",
                http_status=200,
            )
        )
        now_ms = time.time_ns() // 1_000_000
        self.sent_records.append({
            "seq": self._seq,
            "channel": channel,
            "recipient": recipient,
            "event_id": event_id,
            "attempt": attempt,
            "text": text,
            "classification": outcome.classification,
            "message_id": outcome.message_id,
            "http_status": outcome.http_status,
            "ts_ms": now_ms,
        })
        return DeliveryResult(
            classification=outcome.classification,
            provider_message_id=outcome.message_id,
            provider_ack_at_ms=now_ms + outcome.ack_delay_ms if outcome.classification == "PROVIDER_ACK" else None,
            error_code=outcome.error_code,
            error_detail=outcome.error_detail,
            http_status=outcome.http_status,
        )


def classify_hermes_send_result(result: dict[str, Any]) -> DeliveryResult:
    """Classify the dict returned by Hermes ``tools.send_message_tool._send_feishu``."""
    now_ms = time.time_ns() // 1_000_000
    if result.get("success"):
        return DeliveryResult(
            classification="PROVIDER_ACK",
            provider_message_id=result.get("message_id"),
            provider_ack_at_ms=now_ms,
            http_status=200,
        )

    err = str(result.get("error") or "unknown error")
    lower = err.lower()
    if any(tok in lower for tok in ("timeout", "timed out", "connection reset", "broken pipe")):
        return DeliveryResult(
            classification="UNKNOWN_DELIVERY",
            error_code="TRANSPORT_AMBIGUOUS",
            error_detail=err,
        )
    if any(tok in lower for tok in ("429", "rate limit", "too many requests", "500", "502", "503", "504", "99991400")):
        return DeliveryResult(
            classification="RETRYABLE",
            error_code="TRANSIENT_PROVIDER_ERROR",
            error_detail=err,
            http_status=429 if "429" in lower or "99991400" in lower else 503,
        )
    return DeliveryResult(
        classification="PERMANENT",
        error_code="PERMANENT_PROVIDER_ERROR",
        error_detail=err,
        http_status=400,
    )


@dataclass
class MockLarkResponse:
    ok: bool
    code: int = 0
    msg: str = "ok"
    message_id: str | None = None

    def success(self) -> bool:
        return self.ok

    @property
    def data(self) -> Any:
        return SimpleNamespace(message_id=self.message_id) if self.message_id else None


class MockLarkClient:
    """In-memory replacement for ``lark_oapi.Client`` used by Hermes ``FeishuAdapter._build_lark_client``."""

    def __init__(self, responses: list[MockLarkResponse | Exception] | None = None) -> None:
        self._responses = list(responses or [])
        self.requests: list[dict[str, Any]] = []
        self._counter = 0

        outer = self

        class _MessageAPI:
            def create(self, request: Any) -> MockLarkResponse:
                return outer._handle_call("create", request)

            def reply(self, request: Any) -> MockLarkResponse:
                return outer._handle_call("reply", request)

        self.im = SimpleNamespace(v1=SimpleNamespace(message=_MessageAPI()))

    def _handle_call(self, op: str, request: Any) -> MockLarkResponse:
        self._counter += 1
        body = getattr(request, "request_body", None)
        self.requests.append({
            "seq": self._counter,
            "op": op,
            "receive_id": getattr(body, "receive_id", None),
            "receive_id_type": getattr(request, "receive_id_type", None),
            "msg_type": getattr(body, "msg_type", None),
            "content": getattr(body, "content", None),
        })
        if self._responses:
            nxt = self._responses.pop(0)
            if isinstance(nxt, Exception):
                raise nxt
            return nxt
        return MockLarkResponse(ok=True, code=0, msg="ok", message_id=f"om_hermes_mock_{self._counter:06d}")


@contextmanager
def isolated_hermes_feishu_env(
    hermes_home: Path,
    *,
    app_id: str = "cli_offline_mock_app",
    app_secret: str = "offline_mock_secret_do_not_use",
    allowed_users: tuple[str, ...] = ("ou_owner001",),
):
    """Configure an isolated scratch HERMES_HOME with fake Feishu config and scrubbed real keys."""
    hermes_home = Path(hermes_home).resolve()
    hermes_home.mkdir(parents=True, exist_ok=True)
    os.chmod(hermes_home, _FEISHU_CONFIG_DIR_PERMS)
    (hermes_home / "plugins").mkdir(exist_ok=True)
    cfg = hermes_home / "config.yaml"
    if not cfg.exists():
        cfg.write_text("plugins:\n  enabled: []\n", encoding="utf-8")

    scrub_prefixes = ("FEISHU_", "LARK_", "HERMES_", "OPENAI_", "GEMINI_", "ANTHROPIC_", "BINANCE_")
    saved = dict(os.environ)
    try:
        for key in list(os.environ.keys()):
            if key.startswith(scrub_prefixes):
                os.environ.pop(key, None)
        os.environ["HERMES_HOME"] = str(hermes_home)
        os.environ["FEISHU_APP_ID"] = app_id
        os.environ["FEISHU_APP_SECRET"] = app_secret
        os.environ["FEISHU_DOMAIN"] = "feishu"
        os.environ["FEISHU_CONNECTION_MODE"] = "websocket"
        os.environ["FEISHU_ALLOWED_USERS"] = ",".join(allowed_users)
        yield hermes_home
    finally:
        os.environ.clear()
        os.environ.update(saved)


class HermesSendFeishuTransport:
    """Path A transport exercising installed Hermes ``tools.send_message_tool._send_feishu`` offline."""

    def __init__(
        self,
        *,
        hermes_home: Path,
        mock_lark_client: MockLarkClient | None = None,
        app_id: str = "cli_offline_mock_app",
        app_secret: str = "offline_mock_secret_do_not_use",
    ) -> None:
        self.hermes_home = Path(hermes_home)
        self.mock_client = mock_lark_client or MockLarkClient()
        self.app_id = app_id
        self.app_secret = app_secret
        self.raw_results: list[dict[str, Any]] = []

    def send_text(
        self,
        *,
        channel: str,
        recipient: str,
        text: str,
        event_id: str,
        attempt: int,
    ) -> DeliveryResult:
        del event_id, attempt
        if channel != "feishu":
            return DeliveryResult(
                classification="PERMANENT",
                error_code="UNSUPPORTED_CHANNEL",
                error_detail=f"Unsupported channel {channel!r}",
            )
        if not re.fullmatch(r"(?:oc|ou|on|chat|open)_[-A-Za-z0-9]+", recipient):
            return DeliveryResult(
                classification="PERMANENT",
                error_code="INVALID_FEISHU_RECIPIENT",
                error_detail=f"Invalid Feishu recipient id {recipient!r}",
            )

        from gateway.config import PlatformConfig
        from gateway.platforms.feishu import FeishuAdapter
        from tools.send_message_tool import _send_feishu

        with isolated_hermes_feishu_env(
            self.hermes_home,
            app_id=self.app_id,
            app_secret=self.app_secret,
            allowed_users=(recipient,),
        ):
            pconfig = PlatformConfig(
                enabled=True,
                extra={
                    "app_id": self.app_id,
                    "app_secret": self.app_secret,
                    "domain": "feishu",
                    "connection_mode": "websocket",
                },
            )
            with patch.object(FeishuAdapter, "_build_lark_client", return_value=self.mock_client):
                res = asyncio.run(_send_feishu(pconfig, recipient, text))
        self.raw_results.append(res)
        return classify_hermes_send_result(res)


def invoke_hermes_send_message_tool_feishu(
    *,
    hermes_home: Path,
    recipient: str,
    message: str,
    mock_client: MockLarkClient | None = None,
) -> dict[str, Any]:
    """Exercise ``tools.send_message_tool.send_message_tool(action='send')`` against mocked Feishu SDK."""
    from gateway.platforms.feishu import FeishuAdapter
    from tools.send_message_tool import send_message_tool

    client = mock_client or MockLarkClient()
    with (
        isolated_hermes_feishu_env(hermes_home, allowed_users=(recipient,)),
        patch.object(FeishuAdapter, "_build_lark_client", return_value=client),
    ):
        raw = send_message_tool({
            "action": "send",
            "target": f"feishu:{recipient}",
            "message": message,
        })
    return {"tool_result": json.loads(raw), "lark_requests": client.requests}
