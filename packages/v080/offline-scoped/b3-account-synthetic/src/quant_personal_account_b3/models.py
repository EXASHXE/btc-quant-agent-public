"""Core B3 contracts, exact Decimal parsing, canonical hashing, and strict redaction."""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Context, Decimal, InvalidOperation
from typing import Any

D = Decimal
DECIMAL_CONTEXT = Context(prec=40)
ZERO = D("0")

HOUR_MS = 3_600_000
MINUTE_MS = 60_000
DAY_MS = 86_400_000
SEVEN_DAYS_MS = 7 * DAY_MS
THREE_DAYS_MS = 3 * DAY_MS
NINETY_DAYS_MS = 90 * DAY_MS

VENUE = "BINANCE_USDM_USDT_PERPETUAL"
EVIDENCE_CLASS_SYNTHETIC = "SYNTHETIC_PRIVATE_QA_ONLY"
CONNECTION_MODE_FIXTURE = "FIXTURE_ONLY"
ACCOUNT_REALITY_BANNER = "NOT_A_REAL_ACCOUNT"
SYNTHETIC_BANNER_TEXT = f"{EVIDENCE_CLASS_SYNTHETIC} / {CONNECTION_MODE_FIXTURE} / {ACCOUNT_REALITY_BANNER}"
PRIVATE_CONNECTION_NOT_ACTIVATED = "PRIVATE_CONNECTION_NOT_ACTIVATED"
LAYER3_STATUS = "DISABLED_UNREACHABLE"

SCHEMA_SNAPSHOT = "B3_PRIVATE_SNAPSHOT_V1"
SCHEMA_ENDPOINT_COVERAGE = "B3_ENDPOINT_COVERAGE_V1"
SCHEMA_ACCOUNT = "B3_NORMALIZED_ACCOUNT_V1"
SCHEMA_POSITION = "B3_NORMALIZED_POSITION_V1"
SCHEMA_ORDER = "B3_NORMALIZED_ORDER_V1"
SCHEMA_ALGO_ORDER = "B3_NORMALIZED_ALGO_ORDER_V1"
SCHEMA_FILL = "B3_NORMALIZED_FILL_V1"
SCHEMA_INCOME = "B3_NORMALIZED_INCOME_V1"
SCHEMA_CHECKPOINT = "B3_PAGINATION_CHECKPOINT_V1"
SCHEMA_RECONCILIATION = "B3_ACCOUNTING_RECONCILIATION_V1"
SCHEMA_MATCH = "B3_EPISODE_MATCH_V1"
SCHEMA_OVERLAY = "B3_ACCOUNT_OVERLAY_V1"
SCHEMA_JOURNAL_EVENT = "B3_OVERLAY_EVENT_V1"
SCHEMA_MANUAL_LINK = "B3_OWNER_ENTERED_ASSOCIATION_V1"

MARKET_SETUP_STATUSES = frozenset(
    {"EXECUTABLE", "WATCH", "INVALID", "NO_SETUP", "SOURCE_BLOCKED", "NOT_EVALUATED"}
)
ACCOUNT_CONTEXT_STATUSES = frozenset({"SYNTHETIC_CONNECTED", "UNAVAILABLE", "STALE", "PARTIAL"})
POSITION_RELATIONS = frozenset(
    {"NO_POSITION", "SAME_DIRECTION", "OPPOSITE_DIRECTION", "MULTIPLE", "UNKNOWN"}
)
PROTECTION_STATUSES = frozenset({"PROTECTED", "PARTIAL", "UNPROTECTED", "CONFLICTING", "UNKNOWN"})
SIGNAL_TRADE_MATCH_STATUSES = frozenset({"MATCHED", "PROBABLE_MATCH", "UNMATCHED", "AMBIGUOUS"})
ENDPOINT_STATUSES = frozenset(
    {"OK", "PARTIAL", "STALE", "MISSING", "ERROR", "PERMISSION_DENIED", "RATE_LIMITED", "NOT_FETCHED"}
)

RAW_DECIMAL_RE = re.compile(r"^[+-]?\d{1,30}(?:\.\d{1,30})?(?:[eE][+-]?\d{1,4})?$")
SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,30}$")

REDACTED = "[REDACTED]"

SENSITIVE_KEY_NAMES = frozenset(
    {
        "api_key",
        "apikey",
        "x-mbx-apikey",
        "secret",
        "api_secret",
        "secret_key",
        "signature",
        "signed_query",
        "query_string",
        "recvwindow",
        "timestamp",
        "walletbalance",
        "availablebalance",
        "marginbalance",
        "totalwalletbalance",
        "totalmarginbalance",
        "totalunrealizedprofit",
        "maxwithdrawamount",
        "totalcrosswalletbalance",
        "positionamt",
        "unrealizedprofit",
        "isolatedmargin",
        "isolatedwallet",
        "realizedpnl",
        "commission",
        "income",
        "raw_payload",
        "raw_body",
        "authorization",
    }
)

_SENSITIVE_PATTERNS = (
    re.compile(r"(?i)(signature=)[^&\s\"']+"),
    re.compile(r"(?i)(x-mbx-apikey\s*[:=]\s*)[^\s,;\"']+"),
    re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)[^\s,;\"']+"),
    re.compile(r"(?i)(api[_-]?secret\s*[:=]\s*)[^\s,;\"']+"),
    re.compile(r"(?i)(secret\s*[:=]\s*)[^\s,;\"']+"),
    re.compile(r"(?i)(timestamp=)\d+"),
    re.compile(r"(?i)(recvWindow=)\d+"),
)


def redact_text(text: str, extra_secrets: tuple[str, ...] = ()) -> str:
    """Redact credentials, signatures, signed queries, and registered fake secrets."""
    sanitized = text
    for secret in extra_secrets:
        if secret:
            sanitized = sanitized.replace(secret, REDACTED)
    for pattern in _SENSITIVE_PATTERNS:
        sanitized = pattern.sub(rf"\1{REDACTED}", sanitized)
    return sanitized


def redact_mapping(value: Any, extra_secrets: tuple[str, ...] = ()) -> Any:
    """Recursively redact sensitive keys and string values from logs/diagnostics."""
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for k, v in value.items():
            key_str = str(k)
            if key_str.lower() in SENSITIVE_KEY_NAMES:
                result[key_str] = REDACTED
            else:
                result[key_str] = redact_mapping(v, extra_secrets)
        return result
    if isinstance(value, (list, tuple)):
        return [redact_mapping(item, extra_secrets) for item in value]
    if isinstance(value, str):
        return redact_text(value, extra_secrets)
    return value


class AccountB3Error(ValueError):
    """Typed B3 error that always redacts sensitive material from its message."""

    def __init__(
        self,
        code: str,
        detail: str = "",
        *,
        extra_secrets: tuple[str, ...] = (),
    ) -> None:
        safe_detail = redact_text(detail, extra_secrets)
        super().__init__(f"{code}: {safe_detail}" if safe_detail else code)
        self.code = code
        self.detail = safe_detail

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


class PrivateConnectionNotActivatedError(AccountB3Error):
    """Raised whenever any live transport or real secret-store path is invoked."""

    def __init__(self, detail: str = "Live private connection and real credentials are disabled in B3") -> None:
        super().__init__(PRIVATE_CONNECTION_NOT_ACTIVATED, detail)


class PrivateRequestRejectedError(AccountB3Error):
    """Raised at the final request boundary before transport is ever invoked."""


class PermissionDeniedError(AccountB3Error):
    """Fail-closed permission error (401/403/-2015); never retries or widens scope."""


class TimestampSyncError(AccountB3Error):
    """Timestamp/recvWindow failure (-1021) after bounded resync budget is exhausted."""


class RateLimitError(AccountB3Error):
    """Rate limit (429) or IP ban (418) error."""

    def __init__(self, code: str, detail: str = "", *, retry_after_ms: int | None = None) -> None:
        super().__init__(code, detail)
        self.retry_after_ms = retry_after_ms


class ResponseValidationError(AccountB3Error):
    """Fail-closed payload schema or numeric parsing failure."""


class B2IntegrityError(AccountB3Error):
    """Raised when a read-only B2 journal fails schema, digest, or event-chain verification."""


def check(condition: object, code: str, detail: str = "", *, extra_secrets: tuple[str, ...] = ()) -> None:
    if not condition:
        raise AccountB3Error(code, detail, extra_secrets=extra_secrets)


def parse_decimal(value: object, field: str, *, allow_zero: bool = True, allow_negative: bool = True) -> Decimal:
    """Strictly parse a finite Decimal; rejects binary floats and booleans."""
    if isinstance(value, bool):
        raise ResponseValidationError("INVALID_DECIMAL_BOOL", field)
    if isinstance(value, float):
        raise ResponseValidationError("BINARY_FLOAT_PROHIBITED", field)
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = D(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped or not RAW_DECIMAL_RE.fullmatch(stripped):
            raise ResponseValidationError("INVALID_DECIMAL_STRING", field)
        try:
            result = D(stripped)
        except InvalidOperation as exc:
            raise ResponseValidationError("INVALID_DECIMAL_STRING", field) from exc
    else:
        raise ResponseValidationError("INVALID_DECIMAL_TYPE", field)
    if not result.is_finite():
        raise ResponseValidationError("NON_FINITE_DECIMAL", field)
    if not allow_negative and result < ZERO:
        raise ResponseValidationError("NEGATIVE_DECIMAL_DISALLOWED", field)
    if not allow_zero and result == ZERO:
        raise ResponseValidationError("ZERO_DECIMAL_DISALLOWED", field)
    return result


def parse_optional_decimal(
    value: object,
    field: str,
    *,
    allow_zero: bool = True,
    allow_negative: bool = True,
) -> Decimal | None:
    if value is None or value == "":
        return None
    return parse_decimal(value, field, allow_zero=allow_zero, allow_negative=allow_negative)


def parse_int(value: object, field: str, *, minimum: int | None = None, maximum: int | None = None) -> int:
    """Strictly parse a non-bool integer."""
    if type(value) is not int:
        raise ResponseValidationError("INVALID_INTEGER", field)
    if minimum is not None and value < minimum:
        raise ResponseValidationError("INTEGER_BELOW_MIN", field)
    if maximum is not None and value > maximum:
        raise ResponseValidationError("INTEGER_ABOVE_MAX", field)
    return value


def parse_optional_int(
    value: object,
    field: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int | None:
    if value is None or value == "":
        return None
    return parse_int(value, field, minimum=minimum, maximum=maximum)


def parse_bool(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise ResponseValidationError("INVALID_BOOLEAN", field)
    return value


def parse_symbol(value: object, field: str = "symbol") -> str:
    if not isinstance(value, str) or not SYMBOL_RE.fullmatch(value):
        raise PrivateRequestRejectedError("INVALID_SYMBOL", field)
    return value


def _json_default(value: object) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    raise TypeError(f"Unsupported JSON type: {type(value).__name__}")


def encode(value: object) -> str:
    """Canonical deterministic JSON encoding preserving full Decimal precision."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=_json_default)


def digest(value: object) -> str:
    """SHA-256 hex digest of canonically encoded JSON."""
    return hashlib.sha256(encode(value).encode("utf-8")).hexdigest()


def raw_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decimal_str(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def synthetic_provenance_block() -> dict[str, Any]:
    """Inseparable synthetic fixture banner embedded in every B3 private record/overlay."""
    return {
        "evidence_class": EVIDENCE_CLASS_SYNTHETIC,
        "connection_mode": CONNECTION_MODE_FIXTURE,
        "account_reality_banner": ACCOUNT_REALITY_BANNER,
        "synthetic_banner": SYNTHETIC_BANNER_TEXT,
        "real_account_connected": False,
        "layer3_trade_execution": LAYER3_STATUS,
    }
