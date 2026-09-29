"""Immutable bindings copied from the accepted H41 R1 machine authority.

The packaged JSON is a transport copy.  Each child contract and the ledger are
rehashed at load time so a changed copy cannot silently become authority.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .frozen_bindings import FROZEN_BINDINGS_JSON

EXPECTED_HASHES = {
    "candidate_ledger_hash": "d2ee1551ab4778e8ce34e83e053aba17ebb6be240aed812a4beedb218548b7e0",
    "event_pit_contract_hash": "dee7b3ac334dd62e68a7ee700841e9862505bc5827c3ccd665d52b046040362e",
    "endpoint_contract_hash": "ba467d3c69d0b0f266137536d432beea9523b0ba39ccfc7ffd610eeb72c21314",
    "inference_contract_hash": "6b7c3d5289fd9cc132affb51f85fa292049868b96041b2b749cc11cf8be11136",
    "source_requirements_hash": "04845354af6c22f88a55da74aa4fdf8393277e28447c9d57b84a718e8aecb581",
    "validation_lifecycle_contract_hash": "7619ce3849bf4e7f5e288231cd8c38f78189bc1d61baa4c58c87edeb58c6e864",
    "frozen_h41_semantic_root_hash": "f784ce4cfe7ba4d1d5d30582e59ab4811aa7b1e8aed79b00a5f5e0f200c26917",
    "frozen_protocol_hash": "f784ce4cfe7ba4d1d5d30582e59ab4811aa7b1e8aed79b00a5f5e0f200c26917",
}
EXPECTED_SOURCE_ROOT = "05145d35a5cbd060ce3e9d7932b3757f901e396fa545ca624146dfbfa0cdb8b8"
EXPECTED_RECEIPTS = {
    "BTC": "cf6bd69856e06db4a15310b6533e19d60aa96e67528806f4c3d131196e770320",
    "ETH": "6948eb9bbd13c66a49fd73079b0d426685ed0a3bc5ce061a6402f61d668896a5",
}
EXPECTED_PROJECTIONS = {
    "BTC": "466f9fa2bbb483c11218bbda67e00e0f64df048b771a9a724ee61825715a32f8",
    "ETH": "a6728877c47727d796b0c4f42a43f56956fcf05e308533d250783dccd2ae8912",
}
EXPECTED_ARCHIVE_SETS = {
    "BTC": "38f07fa25a9dcfa3c1ae6ddb2564f913ff914bcd2c1229f709bf8fc862fd2d75",
    "ETH": "a4816c5a5b9e2fdc1a56737350145cd3f6fecdfc385cea97d9dd2bfdc74224c5",
}
EXPECTED_MEMBERSHIP = "ddaf3de876c021275939dce51863ef0ab9dee32d0ee9c4a6a0d7b330a4e4977f"
EXPECTED_SOURCE_EVIDENCE_SHA256 = "04cc098ca873ba985adc75f27d08941eb877afce8db26174a57b020a73da217d"


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


@dataclass(frozen=True, slots=True)
class Candidate:
    candidate_id: str
    decision_condition: str
    family: str
    horizon_hours: int
    lookback_window_hours: int
    modifier_type: str | None
    parent_id: str | None
    slot: int
    target_asset: str


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


_BINDINGS = json.loads(FROZEN_BINDINGS_JSON)
FROZEN_HASHES = MappingProxyType(_BINDINGS["authority_hashes"])
CANDIDATES = tuple(Candidate(**row) for row in _BINDINGS["candidates"])
CANDIDATES_BY_ID = MappingProxyType({row.candidate_id: row for row in CANDIDATES})
SOURCE_BINDING = _freeze(_BINDINGS["source"])


def verify_frozen_bindings() -> None:
    if dict(FROZEN_HASHES) != EXPECTED_HASHES:
        raise ValueError("H41 frozen authority hash mismatch")
    if len(CANDIDATES) != 20 or len(CANDIDATES_BY_ID) != 20:
        raise ValueError("H41 candidate count or identity mismatch")
    if [c.slot for c in CANDIDATES] != list(range(1, 21)):
        raise ValueError("H41 candidate order mismatch")
    if canonical_sha256(_BINDINGS["candidates"]) != EXPECTED_HASHES["candidate_ledger_hash"]:
        raise ValueError("H41 candidate ledger mismatch")
    contracts = _BINDINGS["contracts"]
    for name in (
        "event_pit_contract", "endpoint_contract", "inference_contract",
        "source_requirements", "validation_lifecycle_contract",
    ):
        if canonical_sha256(contracts[name]) != EXPECTED_HASHES[f"{name}_hash"]:
            raise ValueError(f"H41 {name} mismatch")
    children = {key: value for key, value in FROZEN_HASHES.items()
                if key not in {"frozen_h41_semantic_root_hash", "frozen_protocol_hash"}}
    if canonical_sha256(children) != EXPECTED_HASHES["frozen_h41_semantic_root_hash"]:
        raise ValueError("H41 semantic root mismatch")
    if SOURCE_BINDING["joint_root"] != EXPECTED_SOURCE_ROOT:
        raise ValueError("H41 accepted source root mismatch")
    if dict(SOURCE_BINDING["receipt_hashes"]) != EXPECTED_RECEIPTS:
        raise ValueError("H41 accepted source receipts mismatch")
    if dict(SOURCE_BINDING["projection_hashes"]) != EXPECTED_PROJECTIONS:
        raise ValueError("H41 accepted source projections mismatch")
    if SOURCE_BINDING["source_evidence_sha256"] != EXPECTED_SOURCE_EVIDENCE_SHA256:
        raise ValueError("H41 accepted source evidence mismatch")
    if (SOURCE_BINDING["controller_state"] != "CLOSED_16_OF_16_PASS"
            or SOURCE_BINDING["implementation_authorized"] is not True):
        raise ValueError("H41 accepted source controller state mismatch")
    if dict(SOURCE_BINDING["archive_set_hashes"]) != EXPECTED_ARCHIVE_SETS:
        raise ValueError("H41 accepted archive-set identities mismatch")
    if dict(SOURCE_BINDING["membership_hashes"]) != {
        "BTC": EXPECTED_MEMBERSHIP, "ETH": EXPECTED_MEMBERSHIP,
        "joint": EXPECTED_MEMBERSHIP,
    }:
        raise ValueError("H41 accepted timestamp membership mismatch")
    for asset in ("BTC", "ETH"):
        if (canonical_sha256(_BINDINGS["source"]["archive_records"][asset])
                != SOURCE_BINDING["archive_set_hashes"][asset]):
            raise ValueError("H41 accepted archive set mismatch")
    root_payload = {
        "schema_id": "H41_CANONICAL_SOURCE_AUTHORITY_ROOT_V1",
        "btc_receipt_hash": EXPECTED_RECEIPTS["BTC"],
        "eth_receipt_hash": EXPECTED_RECEIPTS["ETH"],
        "btc_canonical_projection_hash": EXPECTED_PROJECTIONS["BTC"],
        "eth_canonical_projection_hash": EXPECTED_PROJECTIONS["ETH"],
        "joint_timestamp_membership_hash": SOURCE_BINDING["membership_hashes"]["joint"],
        "frozen_source_requirements_hash": EXPECTED_HASHES["source_requirements_hash"],
        "frozen_protocol_semantic_root": EXPECTED_HASHES["frozen_h41_semantic_root_hash"],
    }
    if canonical_sha256(root_payload) != EXPECTED_SOURCE_ROOT:
        raise ValueError("H41 joint source root does not bind accepted receipts")


verify_frozen_bindings()
