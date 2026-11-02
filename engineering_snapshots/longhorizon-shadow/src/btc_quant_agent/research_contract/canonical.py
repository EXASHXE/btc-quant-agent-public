from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping
from enum import Enum
from types import MappingProxyType
from typing import Any, TypeAlias

JsonScalar: TypeAlias = str | int | float | bool | None
FrozenJson: TypeAlias = JsonScalar | tuple[Any, ...] | Mapping[str, Any]


class FrozenDict(Mapping[str, FrozenJson]):
    """A copied, recursively immutable JSON mapping."""

    __slots__ = ("__data",)

    def __init__(self, values: Mapping[str, Any] | None = None) -> None:
        source = values or {}
        if any(not isinstance(key, str) for key in source):
            raise TypeError("canonical JSON object keys must be strings")
        copied = {key: freeze_json(value) for key, value in source.items()}
        self.__data: Mapping[str, FrozenJson] = MappingProxyType(copied)

    def __getitem__(self, key: str) -> FrozenJson:
        return self.__data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.__data)

    def __len__(self) -> int:
        return len(self.__data)

    def __repr__(self) -> str:
        return f"FrozenDict({dict(self.__data)!r})"


def freeze_json(value: Any) -> FrozenJson:
    """Copy JSON-like data into immutable values, normalizing enums to strings."""
    if isinstance(value, Enum):
        return freeze_json(value.value)
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("canonical JSON object keys must be strings")
        return FrozenDict(value)
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(item) for item in value)
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


def thaw_json(value: FrozenJson | Mapping[str, Any] | list[Any]) -> Any:
    """Return ordinary dict/list JSON data without exposing immutable internals."""
    if isinstance(value, Mapping):
        return {str(key): thaw_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [thaw_json(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    """RFC-8259-compatible JSON with stable ordering and no insignificant whitespace."""
    return json.dumps(
        thaw_json(freeze_json(value)),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
