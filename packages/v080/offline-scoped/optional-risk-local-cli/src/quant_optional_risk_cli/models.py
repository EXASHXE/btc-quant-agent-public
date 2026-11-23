"""Core error types, strict Decimal/type parsers, redaction, and offline socket guard."""

from __future__ import annotations

import hashlib
import json
import re
import socket
import threading
from decimal import Context, Decimal, InvalidOperation
from typing import Any

D = Decimal
DECIMAL_CTX = Context(prec=40)
ZERO = D("0")

CONFIG_SCHEMA_VERSION = "OPTIONAL_ACCOUNT_RISK_CONFIG_V1"
SUPPORTED_CONFIG_VERSIONS = frozenset({"1.0.0"})
POLICY_REFERENCE = "V080-OWNER-PERSONAL-WSL2-KR-OPTIONAL-RISK-20261122"
PRESENTATION_SCHEMA_VERSION = "QUANT_LOCAL_CLI_PRESENTATION_V1"

APPROVED_SYMBOLS = frozenset({"BTCUSDT", "ETHUSDT", "SOLUSDT"})
MAJOR_SYMBOLS = frozenset({"BTCUSDT", "ETHUSDT"})
SOL_OTHER_SYMBOLS = frozenset({"SOLUSDT"})
DEFAULT_FRESHNESS_TTL_MS = 120_000

STRICT_DECIMAL_STR_RE = re.compile(r"^[+-]?\d{1,24}(?:\.\d{1,12})?$")
SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")

REDACTED = "[REDACTED]"
_BINANCE_HEADER = "x-mbx-" + "apikey"
FORBIDDEN_SECRET_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        _BINANCE_HEADER,
        "api_secret",
        "secret",
        "secret_key",
        "private_key",
        "ed25519_private_key",
        "bearer_token",
        "tenant_access_token",
        "app_secret",
        "authorization",
        "signature",
        "signed_query",
        "live_credentials",
        "binance_credentials",
        "feishu_credentials",
    }
)
_REDACT_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)[^\s,;\"']+"),
    re.compile(r"(?i)(api[_-]?secret\s*[:=]\s*)[^\s,;\"']+"),
    re.compile(r"(?i)(" + _BINANCE_HEADER + r"\s*[:=]\s*)[^\s,;\"']+"),
    re.compile(r"(?i)(signature=)[^&\s\"']+"),
    re.compile(r"BEGIN\s+[A-Z0-9 ]*PRIVATE KEY"),
)
_GUARD_LOCK = threading.Lock()
_GUARD_INSTALLED = False


def redact_text(text: str) -> str:
    """Scrub secret or credential patterns from diagnostic strings."""
    cleaned = text
    for pat in _REDACT_PATTERNS:
        cleaned = pat.sub(REDACTED, cleaned)
    return cleaned


class OptionalRiskError(ValueError):
    """Base typed fail-closed error for optional risk config and local CLI."""

    def __init__(self, code: str, detail: str = "") -> None:
        safe = redact_text(detail)
        super().__init__(f"{code}: {safe}" if safe else code)
        self.code = code
        self.detail = safe

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


class OptionalRiskConfigError(OptionalRiskError):
    """Raised when configuration syntax, schema, digest, or bounds fail validation."""


class OptionalRiskBoundaryError(OptionalRiskError):
    """Raised when synthetic fixture integrity or persistent latch invariants are violated."""


class CoreJournalError(OptionalRiskError):
    """Raised when read-only B2/B5 SQLite journal verification fails."""


class LiveCapabilityBlockedError(OptionalRiskError):
    """Raised when any disabled Layer 2 / Layer 3 / live-API / network action is attempted."""


def _json_default(value: Any) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    raise TypeError(type(value).__name__)


def canonical_encode(value: Any) -> str:
    """Deterministically serialize structured objects without NaN or binary floats."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=_json_default,
    )


def canonical_sha256(value: Any) -> str:
    """Compute SHA-256 hex digest of canonical JSON representation."""
    return hashlib.sha256(canonical_encode(value).encode("utf-8")).hexdigest()


def parse_strict_bool(
    value: Any, field: str, *, err_cls: type[OptionalRiskError] = OptionalRiskConfigError
) -> bool:
    """Accept exact Python bool only."""
    if type(value) is not bool:
        raise err_cls("INVALID_BOOLEAN", f"{field}: expected bool")
    return value


def parse_strict_int(
    value: Any,
    field: str,
    *,
    minimum: int = 0,
    err_cls: type[OptionalRiskError] = OptionalRiskConfigError,
) -> int:
    """Accept exact Python int (never bool) within bounds."""
    if type(value) is not int or value < minimum or value >= 2**63:
        raise err_cls("INVALID_INTEGER", field)
    return value


def parse_strict_decimal_string(
    value: Any,
    field: str,
    *,
    positive: bool = False,
    non_negative: bool = False,
    err_cls: type[OptionalRiskError] = OptionalRiskConfigError,
) -> Decimal:
    """Parse strictly formatted decimal string; reject bool, float, int, %, sci notation, NaN/Inf."""
    if isinstance(value, bool):
        raise err_cls("BOOLEAN_IN_NUMERIC_FIELD", field)
    if isinstance(value, float):
        raise err_cls("BINARY_FLOAT_FORBIDDEN", field)
    if not isinstance(value, str):
        raise err_cls("DECIMAL_STRING_REQUIRED", f"{field}: got {type(value).__name__}")
    if "%" in value or re.search(r"\d[eE]", value):
        raise err_cls("PERCENT_OR_EXPONENT_FORBIDDEN", field)
    if value != value.strip() or not value or not STRICT_DECIMAL_STR_RE.fullmatch(value):
        raise err_cls("MALFORMED_DECIMAL_STRING", field)
    try:
        parsed = D(value)
    except InvalidOperation as exc:
        raise err_cls("MALFORMED_DECIMAL_STRING", field) from exc
    if not parsed.is_finite():
        raise err_cls("NON_FINITE_DECIMAL", field)
    if positive and parsed <= ZERO:
        raise err_cls("NON_POSITIVE_DECIMAL_FORBIDDEN", field)
    if non_negative and parsed < ZERO:
        raise err_cls("NEGATIVE_DECIMAL_FORBIDDEN", field)
    return parsed


def scan_forbidden_live_or_secret_fields(obj: Any, *, path: str = "$") -> None:
    """Fail closed if any config or synthetic fixture includes secrets or live credentials."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            key_s = str(k)
            if key_s.lower() in FORBIDDEN_SECRET_KEYS:
                raise OptionalRiskBoundaryError(
                    "FORBIDDEN_SECRET_OR_LIVE_CREDENTIAL_INPUT",
                    f"prohibited key at {path}.{key_s}",
                )
            scan_forbidden_live_or_secret_fields(v, path=f"{path}.{key_s}")
    elif isinstance(obj, (list, tuple)):
        for idx, item in enumerate(obj):
            scan_forbidden_live_or_secret_fields(item, path=f"{path}[{idx}]")
    elif isinstance(obj, str):
        low = obj.lower()
        if "begin " in low and "private key" in low:
            raise OptionalRiskBoundaryError("FORBIDDEN_SECRET_OR_LIVE_CREDENTIAL_INPUT", path)
        if _BINANCE_HEADER in low or obj.startswith("t-"):
            raise OptionalRiskBoundaryError("FORBIDDEN_SECRET_OR_LIVE_CREDENTIAL_INPUT", path)


def install_offline_network_guard() -> None:
    """Disable outbound INET/INET6 network calls inside the offline CLI process."""
    global _GUARD_INSTALLED
    with _GUARD_LOCK:
        if _GUARD_INSTALLED:
            return

        orig_connect = socket.socket.connect
        orig_connect_ex = socket.socket.connect_ex

        def _guarded_connect(self: socket.socket, address: Any) -> Any:
            if getattr(self, "family", None) != socket.AF_UNIX:
                raise LiveCapabilityBlockedError(
                    "OFFLINE_NETWORK_DISABLED",
                    f"blocked socket family={getattr(self, 'family', 'UNKNOWN')}",
                )
            return orig_connect(self, address)

        def _guarded_connect_ex(self: socket.socket, address: Any) -> int:
            if getattr(self, "family", None) != socket.AF_UNIX:
                raise LiveCapabilityBlockedError(
                    "OFFLINE_NETWORK_DISABLED",
                    f"blocked socket family={getattr(self, 'family', 'UNKNOWN')}",
                )
            return orig_connect_ex(self, address)

        def _blocked_create_connection(*_args: Any, **_kwargs: Any) -> Any:
            raise LiveCapabilityBlockedError(
                "OFFLINE_NETWORK_DISABLED",
                "create_connection forbidden in offline local CLI",
            )

        socket.socket.connect = _guarded_connect  # type: ignore[method-assign]
        socket.socket.connect_ex = _guarded_connect_ex  # type: ignore[method-assign]
        socket.create_connection = _blocked_create_connection  # type: ignore[assignment]
        _GUARD_INSTALLED = True
