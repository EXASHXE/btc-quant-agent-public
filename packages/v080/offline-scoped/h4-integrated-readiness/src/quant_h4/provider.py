"""Single-message compatible provider port. No token exchange or live construction in H4."""

import hashlib
import http.client
import json
import ssl
from pathlib import Path
from types import SimpleNamespace

from .approval import Permit
from .fence import Denied

REVIEWED_PROVIDER = None


class FeishuPort:
    """Accept a pre-issued scoped tenant token only after separate deployment authorization."""

    def __init__(self, permit, *, token, ca_path, ca_sha256):
        if REVIEWED_PROVIDER is None or type(permit) is not Permit or permit.fixture:
            raise Denied("REAL_PROVIDER_NOT_ACTIVATED")
        permit.check()
        if REVIEWED_PROVIDER != (permit.claim.app, permit.claim.tenant, ca_sha256):
            raise Denied("PROVIDER_PROFILE_MISMATCH")
        if not isinstance(token, str) or not token or any(c.isspace() for c in token):
            raise Denied("INVALID_BOUND_TOKEN")
        pem = Path(ca_path).read_bytes()
        if hashlib.sha256(pem).hexdigest() != ca_sha256:
            raise Denied("PROVIDER_CA_MISMATCH")
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.context.load_verify_locations(cadata=pem.decode("ascii"))
        self.token = token
        self.permit = permit

    def send_once(self, request, slot, key):
        self.permit.check()
        # Final edge refuses replacement, revocation and any repeat via the SDK port.
        self.permit.state.witness.check(slot + "_wire", key)
        self.permit.state.witness.spend(slot + "_provider", key)
        self.permit.check()
        body = request.request_body
        if (
            request.receive_id_type != "chat_id"
            or body.receive_id != self.permit.claim.chat
            or body.msg_type != "text"
            or not body.uuid
        ):
            raise Denied("PROVIDER_RECIPIENT_OR_BODY_MISMATCH")
        payload = json.dumps(
            {
                "receive_id": body.receive_id,
                "msg_type": "text",
                "content": body.content,
                "uuid": body.uuid,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        conn = http.client.HTTPSConnection("open.feishu.cn", 443, context=self.context, timeout=2)
        try:
            conn.request(
                "POST",
                "/open-apis/im/v1/messages?receive_id_type=chat_id",
                payload,
                {
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
            )
            response = conn.getresponse()
            raw = response.read(65_537)
            if len(raw) > 65_536:
                raise OSError("AMBIGUOUS_PROVIDER_BODY_LIMIT")
            if response.status >= 500:
                raise OSError("AMBIGUOUS_PROVIDER_HTTP_STATUS")
            if response.status != 200:
                return SimpleNamespace(
                    success=lambda: False, code=response.status, msg="HTTP_REJECTED"
                )
            try:
                data = json.loads(raw)
                if type(data) is not dict or type(data.get("code")) is not int:
                    raise ValueError
                details = data.get("data")
                message = details.get("message_id") if type(details) is dict else None
                if data["code"] == 0 and (type(message) is not str or not message):
                    raise ValueError
            except (ValueError, UnicodeError):
                raise OSError("AMBIGUOUS_PROVIDER_ACK") from None
            return SimpleNamespace(
                success=lambda: data.get("code") == 0,
                code=data.get("code"),
                data=SimpleNamespace(message_id=message),
                msg="PROVIDER_RESULT",
            )
        finally:
            conn.close()
