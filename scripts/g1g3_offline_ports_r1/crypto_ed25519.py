"""Pure Python 3.12 stdlib RFC 8032 Ed25519 verifier and synthetic test keyring.

No external dependencies, no live secrets, and no environment credential reads.
The verifier holds only pinned 32-byte Ed25519 public keys. Ephemeral synthetic
test seeds are used strictly by offline test/CLI fixture signers.
"""

from __future__ import annotations

import hashlib
from typing import Any

from scripts.g1_offline_preview_r1.model import SafetyViolation, canonical

# RFC 8032 Ed25519 curve constants
_P = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_D = (-121665 * pow(121666, _P - 2, _P)) % _P
_I = pow(2, (_P - 1) // 4, _P)

_BY = (4 * pow(5, _P - 2, _P)) % _P
_BX = 15112221349535400772501151409588531511454012693041857206046113283949847762202
_BASE_EXT = (_BX, _BY, 1, (_BX * _BY) % _P)
_NEUTRAL_EXT = (0, 1, 1, 0)

SIGNING_DOMAIN_PREFIX = b"G1G3_OFFLINE_OPERATOR_DECISION_V1:"


def _point_add(
    p1: tuple[int, int, int, int], p2: tuple[int, int, int, int]
) -> tuple[int, int, int, int]:
    x1, y1, z1, t1 = p1
    x2, y2, z2, t2 = p2
    a = ((y1 - x1) * (y2 - x2)) % _P
    b = ((y1 + x1) * (y2 + x2)) % _P
    c = (2 * _D * t1 * t2) % _P
    d = (2 * z1 * z2) % _P
    e = (b - a) % _P
    f = (d - c) % _P
    g = (d + c) % _P
    h = (b + a) % _P
    return (e * f) % _P, (g * h) % _P, (f * g) % _P, (e * h) % _P


def _scalar_mult(scalar: int, point: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    result = _NEUTRAL_EXT
    addend = point
    k = scalar
    while k > 0:
        if k & 1:
            result = _point_add(result, addend)
        addend = _point_add(addend, addend)
        k >>= 1
    return result


def _encode_point(point: tuple[int, int, int, int]) -> bytes:
    x, y, z, _ = point
    zi = pow(z, _P - 2, _P)
    xp = (x * zi) % _P
    yp = (y * zi) % _P
    raw = bytearray(yp.to_bytes(32, "little"))
    raw[31] |= (xp & 1) << 7
    return bytes(raw)


def _decode_point(encoded: bytes) -> tuple[int, int, int, int]:
    if len(encoded) != 32:
        raise SafetyViolation("APPROVAL_SIGNATURE_INVALID")
    y = int.from_bytes(encoded, "little") & ((1 << 255) - 1)
    if y >= _P:
        raise SafetyViolation("APPROVAL_SIGNATURE_INVALID")
    x_sign = (encoded[31] >> 7) & 1
    y2 = (y * y) % _P
    u = (y2 - 1) % _P
    v = (_D * y2 + 1) % _P
    x2 = (u * pow(v, _P - 2, _P)) % _P
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = (x * _I) % _P
    if (x * x - x2) % _P != 0:
        raise SafetyViolation("APPROVAL_SIGNATURE_INVALID")
    if x == 0 and x_sign == 1:
        raise SafetyViolation("APPROVAL_SIGNATURE_INVALID")
    if (x & 1) != x_sign:
        x = _P - x
    return x, y, 1, (x * y) % _P


def ed25519_public_key_from_seed(seed_bytes: bytes) -> bytes:
    """Derive 32-byte RFC 8032 Ed25519 public key from 32-byte synthetic seed."""
    if len(seed_bytes) != 32:
        raise ValueError("Ed25519 seed must be 32 bytes")
    h = hashlib.sha512(seed_bytes).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return _encode_point(_scalar_mult(a, _BASE_EXT))


def ed25519_sign(seed_bytes: bytes, message: bytes) -> bytes:
    """Produce 64-byte deterministic RFC 8032 Ed25519 signature."""
    if len(seed_bytes) != 32:
        raise ValueError("Ed25519 seed must be 32 bytes")
    h = hashlib.sha512(seed_bytes).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    prefix = h[32:]
    pub = _encode_point(_scalar_mult(a, _BASE_EXT))
    r = int.from_bytes(hashlib.sha512(prefix + message).digest(), "little") % _L
    r_enc = _encode_point(_scalar_mult(r, _BASE_EXT))
    k = int.from_bytes(hashlib.sha512(r_enc + pub + message).digest(), "little") % _L
    s = (r + k * a) % _L
    return r_enc + s.to_bytes(32, "little")


def ed25519_verify(public_key_bytes: bytes, message: bytes, signature_bytes: bytes) -> bool:
    """Verify 64-byte RFC 8032 Ed25519 signature against 32-byte public key."""
    if len(public_key_bytes) != 32 or len(signature_bytes) != 64:
        return False
    r_enc = signature_bytes[:32]
    s = int.from_bytes(signature_bytes[32:], "little")
    if s >= _L:
        return False
    try:
        a_pt = _decode_point(public_key_bytes)
        r_pt = _decode_point(r_enc)
    except SafetyViolation:
        return False
    k = int.from_bytes(hashlib.sha512(r_enc + public_key_bytes + message).digest(), "little") % _L
    lhs = _encode_point(_scalar_mult(s, _BASE_EXT))
    rhs = _encode_point(_point_add(r_pt, _scalar_mult(k, a_pt)))
    return lhs == rhs


def canonical_signing_bytes(signing_body: dict[str, Any]) -> bytes:
    """Domain-separated canonical UTF-8 bytes for operator decision signing."""
    return SIGNING_DOMAIN_PREFIX + canonical(signing_body).encode("utf-8")


# Ephemeral synthetic test seeds (NEVER live credentials; scoped to offline preview tests)
SYNTHETIC_TEST_OPERATOR_SEEDS: dict[str, bytes] = {
    "ed25519-offline-op-alpha-v1": hashlib.sha256(
        b"SYNTHETIC_TEST_ONLY_SEED_OPERATOR_ALPHA_V1"
    ).digest(),
    "ed25519-offline-op-beta-v1": hashlib.sha256(
        b"SYNTHETIC_TEST_ONLY_SEED_OPERATOR_BETA_V1"
    ).digest(),
    "ed25519-offline-op-revoked-v1": hashlib.sha256(
        b"SYNTHETIC_TEST_ONLY_SEED_OPERATOR_REVOKED_V1"
    ).digest(),
}

# Pinned public-key keyring used by AuthenticatedHumanPort (contains NO secret seeds)
PINNED_OPERATOR_KEYRING: dict[str, dict[str, str]] = {
    "ed25519-offline-op-alpha-v1": {
        "key_id": "ed25519-offline-op-alpha-v1",
        "operator_id": "op-alpha",
        "algorithm": "ED25519_RFC8032_V1",
        "public_key_hex": ed25519_public_key_from_seed(
            SYNTHETIC_TEST_OPERATOR_SEEDS["ed25519-offline-op-alpha-v1"]
        ).hex(),
        "environment": "OFFLINE_PREVIEW",
        "status": "ACTIVE",
        "key_scope": "SYNTHETIC_OFFLINE_TEST_FIXTURE_ONLY",
    },
    "ed25519-offline-op-beta-v1": {
        "key_id": "ed25519-offline-op-beta-v1",
        "operator_id": "op-beta",
        "algorithm": "ED25519_RFC8032_V1",
        "public_key_hex": ed25519_public_key_from_seed(
            SYNTHETIC_TEST_OPERATOR_SEEDS["ed25519-offline-op-beta-v1"]
        ).hex(),
        "environment": "OFFLINE_PREVIEW",
        "status": "ACTIVE",
        "key_scope": "SYNTHETIC_OFFLINE_TEST_FIXTURE_ONLY",
    },
    "ed25519-offline-op-revoked-v1": {
        "key_id": "ed25519-offline-op-revoked-v1",
        "operator_id": "op-revoked",
        "algorithm": "ED25519_RFC8032_V1",
        "public_key_hex": ed25519_public_key_from_seed(
            SYNTHETIC_TEST_OPERATOR_SEEDS["ed25519-offline-op-revoked-v1"]
        ).hex(),
        "environment": "OFFLINE_PREVIEW",
        "status": "REVOKED",
        "key_scope": "SYNTHETIC_OFFLINE_TEST_FIXTURE_ONLY",
    },
}
