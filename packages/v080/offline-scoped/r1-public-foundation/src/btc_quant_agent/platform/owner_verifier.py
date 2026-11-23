"""Verbatim original canonical Ed25519 verification functions; no acquisition code."""
from __future__ import annotations
import base64
import json
from typing import Any

GrantBody = Any
GrantEnvelope = Any

class PublicStop(ValueError):
    pass

def signed_bytes(body: GrantBody) -> bytes:
    return json.dumps(
        body.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()


def verify_signature(envelope: GrantEnvelope, keys: dict):
    entry = keys.get(envelope.key_id)
    if not entry:
        raise PublicStop("SESSION02_OWNER_AUTHORIZATION_NOT_PROVISIONED")
    if (
        set(entry) != {"public_key_base64", "verified_owner_reference"}
        or not entry["verified_owner_reference"]
    ):
        raise PublicStop("SESSION02_OWNER_KEY_ATTESTATION_MISSING")
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
    except ImportError as exc:
        raise PublicStop("SESSION02_SIGNATURE_VERIFIER_UNAVAILABLE") from exc
    try:
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(entry["public_key_base64"], validate=True))
        key.verify(base64.b64decode(envelope.signature_base64, validate=True), signed_bytes(envelope.grant))
    except (ValueError, TypeError, InvalidSignature) as exc:
        raise PublicStop("SESSION02_OWNER_SIGNATURE_INVALID") from exc


