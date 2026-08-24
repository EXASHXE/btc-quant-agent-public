from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.request

from ..domain import Signal


def _signature(timestamp: int, secret: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def build_card(signal: Signal) -> dict[str, object]:
    color = "green" if signal.direction.value == "LONG" else "red"
    p_win = "尚未校准" if signal.p_win is None else f"{signal.p_win:.1%}"
    expected = "尚未校准" if signal.expected_r is None else f"{signal.expected_r:+.2f}R"
    body = (
        f"**状态**：{signal.validation_status}\n"
        f"**Setup**：{signal.setup.value} / {signal.regime.value}\n"
        f"**Entry**：{signal.entry_low:,.2f} – {signal.entry_high:,.2f}\n"
        f"**SL / TP**：{signal.stop_loss:,.2f} / {signal.take_profit:,.2f}\n"
        f"**净 RR**：{signal.rr_net:.2f}\n"
        f"**校准胜率 / Expected R**：{p_win} / {expected}\n"
        f"**建议名义仓位**：{signal.recommended_notional:.2f} USDT\n"
        f"**{signal.display_leverage:g}x 展示保证金**：{signal.margin_at_leverage:.2f} USDT\n"
        f"**估算 Funding**：{signal.estimated_funding_usdt:.4f} USDT\n"
        f"**预计止损损失（含估算摩擦）**：{signal.max_loss_usdt:.2f} USDT"
    )
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "template": color,
                "title": {"tag": "plain_text", "content": f"BTCUSDT {signal.direction.value}"},
            },
            "elements": [
                {"tag": "markdown", "content": body},
                {"tag": "hr"},
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": "仅为研究信号，Agent 不可修改数字，系统无下单权限。",
                        }
                    ],
                },
            ],
        },
    }


def send_signal(webhook_url: str, signal: Signal, secret: str | None = None) -> None:
    payload = build_card(signal)
    if secret:
        timestamp = int(time.time())
        payload["timestamp"] = str(timestamp)
        payload["sign"] = _signature(timestamp, secret)
    request = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        result = json.loads(response.read().decode("utf-8"))
    if result.get("code", result.get("StatusCode", 0)) != 0:
        raise RuntimeError(f"Feishu rejected message: {result}")


def send_invalidation(
    webhook_url: str, signal: Signal, reason: str, secret: str | None = None
) -> None:
    payload: dict[str, object] = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "template": "grey",
                "title": {
                    "tag": "plain_text",
                    "content": f"BTCUSDT {signal.direction.value} 信号已失效",
                },
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": (
                        f"**Signal**：{signal.signal_id}\n"
                        f"**原因代码**：{reason}\n"
                        "该信号不再允许用于新开仓。"
                    ),
                }
            ],
        },
    }
    if secret:
        timestamp = int(time.time())
        payload["timestamp"] = str(timestamp)
        payload["sign"] = _signature(timestamp, secret)
    request = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        result = json.loads(response.read().decode("utf-8"))
    if result.get("code", result.get("StatusCode", 0)) != 0:
        raise RuntimeError(f"Feishu rejected invalidation message: {result}")
