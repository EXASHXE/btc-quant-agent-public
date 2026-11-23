"""Provisioning inputs compiled into a separately reviewed activation build."""

from dataclasses import dataclass
from pathlib import Path

from .enrollment import Enrollment
from .contract import DISABLED, bounded_int, sha_text
from quant_personal_public_b1.policy import require


@dataclass(frozen=True)
class TrustRoots:
    owner_ed25519: bytes
    controller_ed25519: bytes
    state_path: Path
    egress_id: str
    local_uid: int
    ca_bundle_sha256: str
    enrollment: Enrollment | None = None

    def validate(self):
        require(type(self.owner_ed25519) is bytes and type(self.controller_ed25519) is bytes
                and len(self.owner_ed25519) == len(self.controller_ed25519) == 32
                and self.owner_ed25519 != self.controller_ed25519 and self.state_path.is_absolute()
                and sha_text(self.egress_id) and bounded_int(self.local_uid, 0, 2**32 - 1)
                and sha_text(self.ca_bundle_sha256), "TRUST_ROOT_INVALID")


# Phase A cannot make a real request or admit an alleged genuine archive.
# Provisioning is an audited source/release change, never a runtime config option.
_PROVISIONED: TrustRoots | None = None


def production_roots() -> TrustRoots:
    require(type(_PROVISIONED) is TrustRoots, DISABLED)
    _PROVISIONED.validate()
    require(type(_PROVISIONED.enrollment) is Enrollment
            and _PROVISIONED.enrollment.path != _PROVISIONED.state_path,
            "PROTECTED_ENROLLMENT_REQUIRED")
    _PROVISIONED.enrollment.validate()
    return _PROVISIONED
