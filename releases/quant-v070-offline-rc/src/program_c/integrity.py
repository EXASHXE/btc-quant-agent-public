"""Canonical JSON, strict parsing, and confined local file operations."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

WORKSPACE = Path.cwd().resolve()
RESOURCE_ROOT = Path(__file__).resolve().parent
B_ROOT = WORKSPACE.parent / "lt-program-b-qualified-shadow-01"
B_EXPORT = "active_project/artifacts/operator_demo/latest-program-c-episode-export.json"
PINS = {
    "CONTROLLER_0C_PROGRAM_B_SCOPED_ACCEPTANCE.json": "af40b8e1731e928cc4974aa1b8ffec0973e4c19310e1ce772f1d220871a69fad",
    "B8_PROGRAM_C_FROZEN_HANDOFF.json": "36175308d4292c2fcc49ad6affc4ce618dcbb0cd7da942c3242ec56a494a09b6",
    "active_project/contracts/program_c_evaluation_v1.json": "f30380f0bb0ce2c96b495500d66f4a702ccb6f075090ba03ecaa8188b6b982ad",
    "active_project/contracts/b_program_c_episode_export_v1.json": "bae6f31848af7d22e6dcdafe3ad9a31a37e32eace75018ae16bac02c8e0690fe",
    B_EXPORT: "c80f5095e7d3237f7a80c1b33a157a0ee2790f887e63430b9936b612a86b657f",
    "audit/code_manifest.json": "fc84f269e4932dab53c91129c6716a70e8106986ba5bee30886986aaea180262",
    "audit/report_manifest.json": "2f138f7a07d5e43288dba6b993e4dfdd14872e60203d632e50afe67e36156f32",
    "audit/controller/input_baseline.json": "caa4eb38f0d546037fda859a5963f8a443ce369b7fd2da904ea259712a860ad4",
}
B_SELF_HASH = "74578af0ccc410cda2e89a4f92cde7479b5d2feb62d9dbdee136f5fa83890975"
B_ROW_HASH = "e989bd30e6e6e5ce168e6fd6bed36e2ffe0530aa4f0738d657921027c6f2882d"


class ContractError(ValueError):
    """A stable, machine-readable fail-closed reason."""


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ContractError(reason)


def canonical(value: Any) -> bytes:
    # Matches B content_hash for JSON-native values, including ensure_ascii=True.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def digest(value: Any) -> str:
    return sha(canonical(value))


def without(value: dict, key: str) -> dict:
    return {k: v for k, v in value.items() if k != key}


def is_digest(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def number(value: Any, minimum: float = 0, positive: bool = False) -> bool:
    return (type(value) in (int, float) and math.isfinite(value)
            and (value > minimum if positive else value >= minimum))


def milliseconds(value: Any) -> bool:
    return type(value) is int and value > 0


def _pairs(items: list) -> dict:
    result: dict = {}
    for key, value in items:
        require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def parse(raw: bytes) -> dict:
    def invalid_constant(_: str) -> None:
        raise ContractError("NONFINITE_JSON_NUMBER")

    try:
        obj = json.loads(raw, object_pairs_hook=_pairs, parse_constant=invalid_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError("INVALID_JSON") from exc
    require(isinstance(obj, dict), "JSON_OBJECT_REQUIRED")
    return obj


def no_symlinks(path: Path) -> None:
    require(not any(p.is_symlink() for p in [path, *path.parents]), "SYMLINK_FORBIDDEN")


def read_input(path: Path) -> bytes:
    no_symlinks(path.absolute())
    resolved = path.resolve()
    require(resolved.is_relative_to(WORKSPACE) or resolved == B_ROOT / B_EXPORT,
            "INPUT_OUTSIDE_PERMITTED_SCOPE")
    require(path.is_file() and path.stat().st_size <= 30_000_000, "INPUT_FILE_OR_SIZE_INVALID")
    return path.read_bytes()


def fresh_directory(path: Path) -> Path:
    no_symlinks(path.absolute())
    resolved = path.resolve()
    require(resolved != WORKSPACE and resolved.is_relative_to(WORKSPACE), "OUTPUT_OUTSIDE_C_WORKSPACE")
    require(not any(x in {"active_project", "dashboard", ".git", ".agents", ".aws", ".codex"}
                    for x in resolved.relative_to(WORKSPACE).parts), "PROTECTED_OUTPUT_PATH")
    require(not path.exists(), "OUTPUT_ALREADY_EXISTS")
    path.mkdir(parents=True, exist_ok=False)
    return path


def write_json(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
