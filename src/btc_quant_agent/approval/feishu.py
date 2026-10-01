"""Feishu Custom App interactive proposal notification."""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx

from btc_quant_agent.decision.models import TradeProposalV1

_BASE = "https://open.feishu.cn/open-apis"
_ACTIONS = ("APPROVE", "REJECT", "MANUAL", "REQUEST_CODEX_REVIEW")


def build_interactive_card(proposal: TradeProposalV1) -> dict[str, Any]:
    proposal.verify()
    fields = (
        f"Authority: {proposal.account_authority}\n"
        f"{proposal.symbol} {proposal.action}\n"
        f"Recommended notional: {proposal.recommended_notional_usdt:.2f} USDT\n"
        f"Margin: {proposal.margin_usdt:.2f} USDT; leverage: {proposal.leverage}x\n"
        f"Entry: {proposal.entry_low:.8f}–{proposal.entry_high:.8f}; stop: {proposal.stop_loss:.8f}\n"
        f"TP1: {proposal.take_profit_1:.8f}; TP2: {proposal.take_profit_2:.8f}\n"
        f"Risk budget: {proposal.risk_budget_usdt:.2f} USDT; "
        f"max loss: {proposal.max_loss_usdt:.2f} USDT\n"
        f"Estimated fees/slippage/funding: {proposal.fee_estimate_usdt:.4f}/"
        f"{proposal.slippage_estimate_usdt:.4f}/{proposal.funding_estimate_usdt:.4f} USDT\n"
        f"Allowed price drift: {proposal.allowed_price_drift_bps:.2f} bps\n"
        f"Expires: {proposal.expires_at_ms} ms Unix\n"
        f"Case hash: {proposal.case_hash}\nProposal hash: {proposal.proposal_hash}\n"
        f"Manual review: {proposal.requires_manual_review}\n"
        f"Blocked: {', '.join(proposal.blocked_reasons) or 'none'}"
    )
    elements: list[dict[str, Any]] = [{"tag": "div", "text": {"tag": "plain_text", "content": fields}}]
    for action in _ACTIONS:
        elements.append({"tag": "action", "actions": [{
            "tag": "button", "text": {"tag": "plain_text", "content": action},
            "type": "primary" if action == "APPROVE" else "default",
            "value": {"action": action, "proposal_hash": proposal.proposal_hash,
                      "case_hash": proposal.case_hash},
        }]})
    return {"config": {"wide_screen_mode": True},
            "header": {"title": {"tag": "plain_text", "content": "Live V1 DRY_RUN proposal"}},
            "elements": elements}


class FeishuAppClient:
    def __init__(self, app_id: str, app_secret: str, receive_id: str,
                 client: httpx.AsyncClient | None = None) -> None:
        if not app_id or not app_secret or not receive_id:
            raise ValueError("Feishu app configuration required")
        self.app_id = app_id
        self.app_secret = app_secret
        self.receive_id = receive_id
        self.client = client

    async def send_proposal(self, proposal: TradeProposalV1) -> str:
        proposal.verify()
        card = build_interactive_card(proposal)
        async def post_json(client: httpx.AsyncClient, url: str, payload: dict[str, object],
                            headers: dict[str, str] | None = None,
                            params: dict[str, str] | None = None) -> dict[str, Any]:
            async with client.stream("POST", url, timeout=10.0, json=payload,
                                     headers=headers, params=params) as response:
                response.raise_for_status()
                chunks = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > 65536:
                        raise ValueError("oversized response")
                    chunks.append(chunk)
                body = json.loads(b"".join(chunks))
                if not isinstance(body, dict):
                    raise TypeError("invalid response")
                return body

        async def send(client: httpx.AsyncClient) -> str:
            try:
                token_body = await post_json(client, f"{_BASE}/auth/v3/tenant_access_token/internal",
                                             {"app_id": self.app_id, "app_secret": self.app_secret})
                if token_body.get("code") != 0 or not isinstance(token_body.get("tenant_access_token"), str):
                    raise ValueError("token unavailable")
                body = await post_json(
                    client,
                    f"{_BASE}/im/v1/messages",
                    {"receive_id": self.receive_id, "msg_type": "interactive",
                     "content": json.dumps(card, ensure_ascii=False),
                     "uuid": str(uuid.UUID(proposal.proposal_hash[:32]))},
                    headers={"Authorization": f"Bearer {token_body['tenant_access_token']}"},
                    params={"receive_id_type": "chat_id"},
                )
                data = body.get("data")
                message_id = data.get("message_id") if isinstance(data, dict) else None
                if body.get("code") != 0 or not isinstance(message_id, str) or not message_id:
                    raise ValueError("message unavailable")
                return message_id
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                raise RuntimeError("Feishu proposal delivery failed") from None

        if self.client is not None:
            return await send(self.client)
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            return await send(client)
