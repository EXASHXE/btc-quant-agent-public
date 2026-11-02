"""Plaintext Feishu v2 callback endpoint with token and optional request signature."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Callable, Iterable
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from .store import LiveStore


def create_callback_app(
    store: LiveStore, verification_token: str, signing_secret: str = "",
    approver_open_ids: Iterable[str] = (), app_id: str = "",
    clock_ms: Callable[[], int] | None = None,
) -> FastAPI:
    app = FastAPI()
    approvers = frozenset(approver_open_ids)
    now = clock_ms or (lambda: int(time.time() * 1000))

    @app.post("/callback")
    async def callback(request: Request) -> dict[str, Any]:
        chunks: list[bytes] = []
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > 65536:
                raise HTTPException(413, "callback too large")
            chunks.append(chunk)
        raw = b"".join(chunks)
        if signing_secret:
            timestamp = request.headers.get("x-lark-request-timestamp", "")
            nonce = request.headers.get("x-lark-request-nonce", "")
            signature = request.headers.get("x-lark-signature", "")
            if not timestamp or not nonce or not signature or not timestamp.isdigit():
                raise HTTPException(401, "invalid callback signature")
            if abs(now() // 1000 - int(timestamp)) > 300:
                raise HTTPException(401, "stale callback signature")
            expected = hashlib.sha256(timestamp.encode() + nonce.encode() +
                                      signing_secret.encode() + raw).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise HTTPException(401, "invalid callback signature")
        try:
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise TypeError()
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
            raise HTTPException(400, "invalid callback body") from None
        if "encrypt" in body:
            raise HTTPException(400, "encrypted callbacks unsupported")
        challenge = body.get("type") == "url_verification"
        header_raw = body.get("header")
        header: dict[str, Any] = header_raw if isinstance(header_raw, dict) else {}
        token = body.get("token") if challenge else header.get("token")
        if not verification_token or not isinstance(token, str) or not hmac.compare_digest(token, verification_token):
            raise HTTPException(401, "invalid verification token")
        if challenge:
            if not isinstance(body.get("challenge"), str):
                raise HTTPException(400, "invalid challenge")
            return {"challenge": body["challenge"]}
        if (body.get("schema") != "2.0" or header.get("event_type") != "card.action.trigger"
                or not isinstance(header.get("event_id"), str)):
            raise HTTPException(400, "invalid callback envelope")
        if app_id and header.get("app_id") != app_id:
            raise HTTPException(403, "callback app denied")
        event = body.get("event")
        if not isinstance(event, dict):
            raise HTTPException(400, "invalid callback event")
        operator = event.get("operator")
        action = event.get("action")
        actor = operator.get("open_id") if isinstance(operator, dict) else None
        value = action.get("value") if isinstance(action, dict) else None
        if not isinstance(actor, str) or actor not in approvers:
            raise HTTPException(403, "callback actor denied")
        if not isinstance(value, dict) or set(value) != {"action", "proposal_hash", "case_hash"}:
            raise HTTPException(400, "invalid callback action")
        if not all(isinstance(value[key], str) for key in value):
            raise HTTPException(400, "invalid callback action")
        try:
            result = store.record_callback(header["event_id"], value["action"], actor,
                                           value["proposal_hash"], value["case_hash"], now())
        except (ValueError, KeyError):
            raise HTTPException(400, "callback rejected") from None
        return {"toast": {"type": "success", "content": result["state"]}, **result}

    return app
