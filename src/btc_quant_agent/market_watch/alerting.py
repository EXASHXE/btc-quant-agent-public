from __future__ import annotations

import json
import time
import urllib.request
from typing import Any

from ..notify.feishu import _signature
from .domain import AlertSeverity, DirectionalDecision, MarketWatchAlert


def _format_price(val: float | None) -> str:
    if val is None:
        return "N/A"
    if abs(val) >= 100:
        return f"{val:,.2f}"
    if abs(val) >= 1:
        return f"{val:,.4f}".rstrip("0").rstrip(".")
    return f"{val:,.6f}".rstrip("0").rstrip(".")


def build_market_watch_card(alert: MarketWatchAlert) -> dict[str, Any]:
    """Build a rich, interactive Feishu card for MarketWatch operational alerts."""
    d = alert.directional
    g = alert.grid

    # Color template based on severity and direction
    if alert.severity == AlertSeverity.RISK:
        color = "orange"
        emoji = "⚠️"
    elif d.decision == DirectionalDecision.LONG:
        color = "green"
        emoji = "🚨"
    elif d.decision == DirectionalDecision.SHORT:
        color = "red"
        emoji = "🚨"
    else:
        color = "blue"
        emoji = "ℹ️"

    # Evidence bullet points
    evidence_text = "\n".join(f"- {e}" for e in alert.evidence) if alert.evidence else "- 无特殊触发证据"
    # Risks bullet points
    risks_text = "\n".join(f"- {r}" for r in alert.risks) if alert.risks else "- 暂无显著异常风险"

    # Directional section
    lines = [
        f"**Directional**: {d.decision.value} ({d.setup.value})",
        f"**Regime**: {d.regime.value}",
        f"**Entry Quality**: {d.entry_quality.value}",
        f"**Entry Zone**: {_format_price(d.entry_low)} – {_format_price(d.entry_high)}",
        f"**Stop Loss**: {_format_price(d.stop_loss)}",
        f"**TP1 / TP2**: {_format_price(d.take_profit_1)} / {_format_price(d.take_profit_2)}",
        f"**Net RR**: {d.net_rr:.2f} (Gross {d.gross_rr:.2f})",
        f"**Derivatives State**: {d.derivatives_regime.value}",
        f"**Benchmark Context**: {d.benchmark_context.value}",
        f"**Opportunity Score**: {d.opportunity_score:.1f}",
    ]

    # Grid section if active
    if g.lower_bound is not None and g.upper_bound is not None:
        lines.append(
            f"\n**Grid Recommendation** ({g.decision.value}):\n"
            f"Range: {_format_price(g.lower_bound)} – {_format_price(g.upper_bound)} | Grids: {g.grid_count} | ~{g.estimated_grid_pct:.2f}% per step"
        )

    lines.extend([
        f"\n**Evidence**:\n{evidence_text}",
        f"\n**Risks**:\n{risks_text}",
        "\n**Classification**: `EXPERIMENTAL_OPERATIONAL_MARKET_WATCH`",
    ])

    body = "\n".join(lines)

    title = f"{emoji} {alert.symbol} {d.decision.value} [{alert.severity.value}]"

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "template": color,
                "title": {"tag": "plain_text", "content": title},
            },
            "elements": [
                {"tag": "markdown", "content": body},
                {"tag": "hr"},
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": "No automatic order submission. Decision-support only.",
                        }
                    ],
                },
            ],
        },
    }


def send_market_watch_alert(
    webhook_url: str,
    alert: MarketWatchAlert,
    secret: str | None = None,
) -> None:
    """Send MarketWatchAlert via Feishu webhook with HMAC signature support."""
    payload = build_market_watch_card(alert)
    if secret:
        timestamp = int(time.time())
        payload["timestamp"] = str(timestamp)
        payload["sign"] = _signature(timestamp, secret)

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        result = json.loads(response.read().decode("utf-8"))
    if result.get("code", result.get("StatusCode", 0)) != 0:
        raise RuntimeError(f"Feishu rejected MarketWatch alert: {result.get('msg', result)}")


def send_test_market_watch_alert(
    webhook_url: str,
    secret: str | None = None,
) -> None:
    """Send test-only connectivity card to Feishu."""
    payload: dict[str, Any] = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": "🔔 MARKET WATCH FEISHU CONNECTIVITY TEST"},
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": (
                        "**Status**: CONNECTIVITY_OK\n"
                        "**Timestamp**: " + time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()) + "\n"
                        "**Message**: TEST ONLY. Feishu webhook connectivity established successfully.\n"
                        "**Notice**: No market recommendation."
                    ),
                },
                {"tag": "hr"},
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": "Experimental Market Watch Notification System",
                        }
                    ],
                },
            ],
        },
    }

    if secret:
        timestamp = int(time.time())
        payload["timestamp"] = str(timestamp)
        payload["sign"] = _signature(timestamp, secret)

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        result = json.loads(response.read().decode("utf-8"))
    if result.get("code", result.get("StatusCode", 0)) != 0:
        raise RuntimeError(f"Feishu rejected test message: {result.get('msg', result)}")
