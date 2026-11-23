"""Versioned, explicit dual approval for the proposed S4 runtime."""

import hashlib
import os
import re
import socket
import time
from dataclasses import asdict, dataclass
from importlib.util import find_spec
from pathlib import Path
from zipfile import ZipFile

from .fence import Denied, FilePin, Witness, canonical, digest

PRODUCTION_ROOTS = None
PRODUCTION_DEPENDENCIES = None
ROLES = ("owner", "controller")
NATIVE = "H4_FEISHU_SCOPE_V1"
SHA = re.compile(r"[0-9a-f]{64}")
QA_ROOTS = frozenset(
    bytes.fromhex(key)
    for key in (
        "c86d01ad8b2fb694b22ff60e3c9d9e7ed90db5604772b74450d40913b9a9cbaf",
        "e2fe2a39b7326642827d6d82d497622cd6c297fe78270eaa436b01f086b6f3cb",
    )
)


def ns_guard():
    if os.readlink("/proc/self/ns/net") == os.readlink("/proc/1/ns/net") or {
        name for _, name in socket.if_nameindex()
    } != {"lo"}:
        raise Denied("OFFLINE_NAMESPACE_REQUIRED")


@dataclass(frozen=True)
class Claim:
    task: str
    capability: str
    run_id: str
    release_sha256: str
    state_sha256: str
    runtime_uid: int
    authority: str
    app: str
    tenant: str
    owner: str
    chat: str
    sender: str
    channel: str
    not_before_ms: int
    expires_ms: int
    event_id: str | None
    message_sha256: str | None
    evidence_class: str
    message_limit: int
    accepted_turns: int
    reply_limit: int
    auth_bootstrap_limit: int
    facade_path: str
    facade_uid: int
    callback_key_sha256: str | None = None


@dataclass(frozen=True)
class State:
    witness: Witness
    pins: tuple[tuple[str, FilePin], ...]

    def check(self):
        self.witness.require_separation(tuple(pin.path for _, pin in self.pins))
        names = [name for name, _ in self.pins]
        if len(names) != len(set(names)) or set(names) != {"outbox", "delivery", "quota", "dedup"}:
            raise Denied("STATE_INVENTORY_MISMATCH")
        if len({(pin.device, pin.inode) for _, pin in self.pins}) != len(names):
            raise Denied("STATE_PIN_ALIAS")
        for _, pin in self.pins:
            pin.verify_private()

    def identity(self):
        def encode(pin):
            return [str(pin.path), pin.device, pin.inode, pin.uid]

        return digest(
            [
                encode(self.witness.pin),
                self.witness.header_sha256,
                [[name, encode(pin)] for name, pin in self.pins],
            ]
        )


def verify_release(wheel, expected):
    if hashlib.sha256(wheel.read_bytes()).hexdigest() != expected:
        raise Denied("RELEASE_DIGEST_MISMATCH")
    installed = Path(__file__).resolve().parent
    with ZipFile(wheel) as archive:
        names = [name for name in archive.namelist() if name.startswith("quant_h4/")]
        if len(set(names)) != len(names):
            raise Denied("WHEEL_INVENTORY_MISMATCH")
        expected_files = {name.split("/", 1)[1]: archive.read(name) for name in names}
    actual = {p.relative_to(installed).as_posix(): p.read_bytes() for p in installed.rglob("*.py")}
    if actual != expected_files:
        raise Denied("INSTALLED_RELEASE_MISMATCH")


def verify_production_dependencies():
    expected = {"quant_hermes_feishu_h1", "quant_hermes_feishu_h2b", "quant_hermes_h3"}
    if type(PRODUCTION_DEPENDENCIES) is not dict or set(PRODUCTION_DEPENDENCIES) != expected:
        raise Denied("LIVE_DEPENDENCY_REVIEW_REQUIRED")
    for name, pin in PRODUCTION_DEPENDENCIES.items():
        location = find_spec(name)
        if location is None or location.origin is None:
            raise Denied("LIVE_DEPENDENCY_MISSING")
        package = Path(location.origin).resolve().parent
        files = {
            path.relative_to(package).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in package.rglob("*.py")
        }
        if files != pin:
            raise Denied("LIVE_DEPENDENCY_BYTES_MISMATCH")


class Permit:
    """One already reviewed claim. Runtime checks live expiry, identity and stop state."""

    def __init__(self, claim, state, wheel, signatures, *, fixture_keys=None, clock=None):
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        if type(claim) is not Claim or type(state) is not State:
            raise Denied("SCOPE_INVALID")
        fixture = fixture_keys is not None
        if fixture:
            ns_guard()
            if not state.witness.fixture_only or claim.evidence_class != "SYNTHETIC_QA_ONLY":
                raise Denied("FIXTURE_EVIDENCE_REQUIRED")
            keys = fixture_keys
        else:
            if PRODUCTION_ROOTS is None or state.witness.fixture_only or claim.runtime_uid <= 0:
                raise Denied("LIVE_FEISHU_NOT_ACTIVATED")
            verify_production_dependencies()
            if claim.evidence_class not in {
                "PERSONAL_PUBLIC_MARKET",
                "PERSONAL_PUBLIC_MARKET_GENUINE",
            }:
                raise Denied("LIVE_EVIDENCE_CLASS_INVALID")
            keys = PRODUCTION_ROOTS
            if any(key in QA_ROOTS for key in keys):
                raise Denied("FIXTURE_APPROVAL_ROOT_FORBIDDEN")
        if (
            type(signatures) is not dict
            or set(signatures) != set(ROLES)
            or len(keys) != 2
            or keys[0] == keys[1]
        ):
            raise Denied("DUAL_APPROVAL_REQUIRED")
        if (
            claim.task != NATIVE
            or claim.authority != "https://open.feishu.cn"
            or claim.channel != "feishu"
            or not all(SHA.fullmatch(x) for x in (claim.release_sha256, claim.state_sha256))
            or not re.fullmatch(r"[0-9a-f]{32}", claim.run_id)
            or not claim.app.startswith("cli_")
            or not claim.owner.startswith("ou_")
            or not claim.chat.startswith("oc_")
            or not claim.tenant
            or not claim.sender
            or any(
                type(n) is not int
                for n in (
                    claim.runtime_uid,
                    claim.not_before_ms,
                    claim.expires_ms,
                    claim.message_limit,
                    claim.accepted_turns,
                    claim.reply_limit,
                    claim.auth_bootstrap_limit,
                )
            )
            or not 0 < claim.expires_ms - claim.not_before_ms <= 120_000
            or claim.auth_bootstrap_limit != 0
            or not Path(claim.facade_path).is_absolute()
            or type(claim.facade_uid) is not int
            or claim.facade_uid < 0
            or (not fixture and claim.facade_uid in (0, claim.runtime_uid))
        ):
            raise Denied("SCOPE_INVALID")
        if claim.capability == "outbound":
            if (
                (claim.message_limit, claim.accepted_turns, claim.reply_limit) != (1, 0, 0)
                or not claim.event_id
                or not SHA.fullmatch(claim.event_id)
                or not claim.message_sha256
                or not SHA.fullmatch(claim.message_sha256)
                or claim.callback_key_sha256 is not None
            ):
                raise Denied("OUTBOUND_SCOPE_INVALID")
        elif claim.capability == "inbound":
            if (
                (claim.message_limit, claim.accepted_turns, claim.reply_limit) != (0, 1, 1)
                or claim.event_id is not None
                or claim.message_sha256 is not None
                or not claim.callback_key_sha256
                or not SHA.fullmatch(claim.callback_key_sha256)
            ):
                raise Denied("INBOUND_SCOPE_INVALID")
        else:
            raise Denied("CAPABILITY_UNKNOWN")
        body = canonical(asdict(claim))
        try:
            for role, key in zip(ROLES, keys, strict=True):
                Ed25519PublicKey.from_public_bytes(key).verify(
                    bytes.fromhex(signatures[role]),
                    f"{NATIVE}/{role}\n".encode("ascii") + body,
                )
        except (TypeError, ValueError, InvalidSignature) as exc:
            raise Denied("APPROVAL_SIGNATURE_INVALID") from exc
        verify_release(wheel, claim.release_sha256)
        self.claim, self.state, self.fixture = claim, state, fixture
        self.sha = hashlib.sha256(body).hexdigest()
        self.clock = clock if fixture and clock else lambda: time.time_ns() // 1_000_000
        self.check()

    def check(self):
        if self.fixture:
            ns_guard()
        claim = self.claim
        if claim.runtime_uid != os.geteuid():
            raise Denied("RUNTIME_UID_MISMATCH")
        if not claim.not_before_ms <= self.clock() < claim.expires_ms:
            raise Denied("APPROVAL_EXPIRED_OR_EARLY")
        if any(pin.uid != claim.runtime_uid for _, pin in self.state.pins):
            raise Denied("STATE_RUNTIME_UID_MISMATCH")
        self.state.check()
        if self.state.identity() != claim.state_sha256:
            raise Denied("SIGNED_STORAGE_SCOPE_MISMATCH")
        self.state.witness.check("health")

    def key(self, slot, event, uuid=""):
        return digest([self.sha, slot, event, uuid])

    def revoke(self):
        # Revocation remains local after deadline. Never recover from a suspect pin.
        if self.claim.runtime_uid != os.geteuid():
            raise Denied("RUNTIME_UID_MISMATCH")
        self.state.witness.spend("revoked", self.sha, idempotent=True)
