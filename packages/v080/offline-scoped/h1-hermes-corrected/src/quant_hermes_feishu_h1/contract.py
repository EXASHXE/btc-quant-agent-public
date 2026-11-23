"""Controller-frozen Quant-Agent Contract V1 schemas, canonical hashes, and validators."""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

CONTRACT_ID = "V080_QUANT_AGENT_CONTRACT_V1"
CONTRACT_VERSION = CONTRACT_ID
CONTRACT_DOC_PATH = "docs/architecture/V080_QUANT_AGENT_CONTRACT_V1_20261120.md"
CONTRACT_DOC_SHA256 = "622677b019120ed18d9bfea057589f7bf923f7f15e17adb3ac59831a0bfd8cc2"
H1_TASK_ID = "V080-HERMES-QUANT-FEISHU-INTEGRATION-H1-01"
P0_REMEDIATION_TASK_ID = "V080-HERMES-H1-P0-INTEROP-REMEDIATION-01"
MAX_SAFE_JS_INT = 9007199254740991

V1_READ_ONLY_TOOLS: tuple[str, ...] = (
    "list_active_signals",
    "get_signal_detail",
    "get_market_context",
    "get_latest_reprice",
    "get_signal_history",
    "get_strategy_summary",
)
V1_STATE_TOOLS: tuple[str, ...] = ("request_reprice",)
V1_ALL_TOOLS: tuple[str, ...] = V1_READ_ONLY_TOOLS + V1_STATE_TOOLS

MARKET_STATUSES: frozenset[str] = frozenset({
    "EXECUTABLE",
    "WATCH",
    "INVALID",
    "NO_SETUP",
    "SOURCE_BLOCKED",
    "NOT_EVALUATED",
})

FRESHNESS_STATES: frozenset[str] = frozenset({"CURRENT", "STALE", "UNKNOWN"})

EVIDENCE_UNKNOWN = "UNKNOWN"
EVIDENCE_SYNTHETIC = "SYNTHETIC_QA_ONLY"
EVIDENCE_GENUINE_PERSONAL = "PERSONAL_PUBLIC_MARKET"
EVIDENCE_GENUINE_B5 = "PERSONAL_PUBLIC_MARKET_GENUINE"
ALLOWED_GENUINE_EVIDENCE: frozenset[str] = frozenset({
    EVIDENCE_GENUINE_PERSONAL,
    EVIDENCE_GENUINE_B5,
})
ALLOWED_RESPONSE_EVIDENCE_CLASSES: frozenset[str] = (
    frozenset({EVIDENCE_SYNTHETIC, EVIDENCE_UNKNOWN}) | ALLOWED_GENUINE_EVIDENCE
)
ALLOWED_SYNTHETIC_ORIGINS: frozenset[str] = frozenset({
    "OFFLINE_FIXTURE_V2",
    "LOOPBACK_HTTPS_QA_V2",
    "SYNTHETIC_QA_ONLY",
    "FIXTURE",
    "fixture",
    "loopback",
})

APPROVED_SYMBOLS: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
APPROVED_FAMILIES: tuple[str, ...] = ("TREND_PULLBACK", "EARLY_CONTINUATION")
APPROVED_DIRECTIONS: frozenset[str] = frozenset({"LONG", "SHORT"})

TYPED_ERROR_CODES: frozenset[str] = frozenset({
    "UNAUTHORIZED",
    "UNKNOWN_TOOL",
    "INVALID_ARGUMENT",
    "NOT_FOUND",
    "SOURCE_UNAVAILABLE",
    "SOURCE_BLOCKED",
    "STALE_CARD",
    "EXPIRED",
    "INTEGRITY_FAILURE",
    "REPRICE_NOT_AUTHORIZED",
    "RATE_LIMITED",
    "TIMEOUT",
    "INTERNAL_REDACTED",
})

MAX_LIST_LIMIT = 50
MAX_REQUEST_BYTES = 32_768
MAX_RESPONSE_BYTES = 262_144
DEFAULT_DEADLINE_MS = 2_000
MAX_DEADLINE_MS = 10_000

SYNTHETIC_BANNER = "SYNTHETIC_QA_ONLY / NOT_A_REAL_TRADE_SIGNAL"
HETEROGENEOUS_BANNER = "HETEROGENEOUS_EVIDENCE / MIXED_SOURCES_DO_NOT_NOTIFY_AGGREGATE"
UNKNOWN_EVIDENCE_BANNER = "EVIDENCE_UNKNOWN / NO_VERIFIED_MARKET_SOURCE"
SYNTHETIC_WARNING_TOKEN = "NOT_A_REAL_TRADE_SIGNAL"
PRINTABLE_ASCII_ID_RE = re.compile(r"^[\x21-\x7e]{1,256}$")

DECIMAL_STR_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?$")
SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_SECRET_KV_RE = re.compile(
    r"(?i)\b(app_secret|api_secret|api_key|access_token|auth_token|password|secret|token|signature|sig)\s*[:=]\s*([^\s,;\"']+)"
)
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-+/=]+")
_ABS_PATH_RE = re.compile(r"(?:/[A-Za-z0-9._-]+){2,}")


def _b2_json_default(value: object) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _assert_no_unpaired_surrogates(text: str, *, path: str) -> None:
    for ch in text:
        code = ord(ch)
        if 0xD800 <= code <= 0xDFFF:
            raise ContractError("INVALID_ARGUMENT", f"Unpaired UTF-16 surrogate in {path}")


def validate_canonical_conformance_value(value: Any, *, path: str = "$") -> None:
    """Validate strict Python/TS canonical JSON interoperability rules (P0-C03)."""
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_JS_INT:
            raise ContractError("INVALID_ARGUMENT", f"Unsafe JS integer at {path}: {value}")
        return
    if isinstance(value, float):
        raise ContractError("INVALID_ARGUMENT", f"Float forbidden in canonical JSON profile at {path}: {value!r}")
    if isinstance(value, str):
        _assert_no_unpaired_surrogates(value, path=path)
        return
    if isinstance(value, list):
        for idx, item in enumerate(value):
            validate_canonical_conformance_value(item, path=f"{path}[{idx}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if type(key) is not str:
                raise ContractError("INVALID_ARGUMENT", f"Object key must be str at {path}")
            _assert_no_unpaired_surrogates(key, path=f"{path}.<key>")
            if not key.isascii():
                raise ContractError("INVALID_ARGUMENT", f"Non-ASCII object property name forbidden at {path}: {key!r}")
            validate_canonical_conformance_value(item, path=f"{path}.{key}")
        return
    raise ContractError("INVALID_ARGUMENT", f"Unsupported type for canonical JSON at {path}: {type(value).__name__}")


def canonical_json(obj: Any) -> str:
    """Serialize deterministically matching B2's canonical JSON encoder."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=_b2_json_default,
    )


def canonical_json_strict(obj: Any) -> str:
    """Validate P0-C03 canonical profile rules and emit Python 3.12/Node 24 identical UTF-8 JSON."""
    validate_canonical_conformance_value(obj)
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def b2_canonical_json(obj: Any) -> str:
    """Serialize deterministically using B2's exact ASCII-escaped canonical JSON for SQLite SHA verification."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
        default=_b2_json_default,
    )


def b2_sha256(obj: Any) -> str:
    """Compute SHA-256 hex digest matching ``quant_personal_decision_b2.model.digest``."""
    return hashlib.sha256(b2_canonical_json(obj).encode("utf-8")).hexdigest()


def canonical_sha256(obj: Any) -> str:
    """Compute SHA-256 hex digest over UTF-8 canonical JSON."""
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def canonical_sha256_strict(obj: Any) -> str:
    """Validate strict P0-C03 canonical profile and return UTF-8 SHA-256 hex digest."""
    return hashlib.sha256(canonical_json_strict(obj).encode("utf-8")).hexdigest()


def _validate_event_id_component(value: Any, name: str) -> str:
    if type(value) is not str:
        raise ContractError("INVALID_ARGUMENT", f"{name} must be an opaque str, got {type(value).__name__}")
    _assert_no_unpaired_surrogates(value, path=name)
    if not value or value != value.strip() or not PRINTABLE_ASCII_ID_RE.fullmatch(value):
        raise ContractError("INVALID_ARGUMENT", f"{name} must be non-empty trimmed printable ASCII")
    return value


def compute_outbox_event_id(
    *,
    contract_id: str,
    channel: str,
    recipient: str,
    episode_id: str,
    card_id: str,
    card_version: str,
    market_status: str,
) -> str:
    """Compute V1 section 6 deterministic notification event_id (strict P0-C01/C03 profile)."""
    c_id = _validate_event_id_component(contract_id, "contract_id")
    ch = _validate_event_id_component(channel, "channel")
    rcp = _validate_event_id_component(recipient, "recipient")
    ep = _validate_event_id_component(episode_id, "episode_id")
    cid = _validate_event_id_component(card_id, "card_id")
    ver = _validate_event_id_component(card_version, "card_version")
    st = _validate_event_id_component(market_status, "market_status")
    if c_id != CONTRACT_ID:
        raise ContractError("INVALID_ARGUMENT", f"Unsupported contract_id for event_id: {c_id!r}")
    if ep.startswith("noep:"):
        raise ContractError("INVALID_ARGUMENT", "Synthetic noep: episode_id is forbidden for notification event_id")
    if st not in MARKET_STATUSES:
        raise ContractError("INVALID_ARGUMENT", f"Invalid market_status for event_id: {st!r}")
    payload = [c_id, ch, rcp, ep, cid, ver, st]
    return canonical_sha256_strict(payload)


def redact_error_text(text: object) -> str:
    """Redact credentials, tokens, and internal filesystem paths from error strings."""
    raw = str(text)
    cleaned = _BEARER_RE.sub("Bearer [REDACTED]", raw)
    cleaned = _SECRET_KV_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", cleaned)
    cleaned = _ABS_PATH_RE.sub("[PATH_REDACTED]", cleaned)
    return cleaned[:400]


class ContractError(Exception):
    """Typed error conforming to Contract V1 section 5."""

    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        if code not in TYPED_ERROR_CODES:
            raise ValueError(f"Unsupported Contract V1 error code: {code!r}")
        safe_msg = redact_error_text(message)
        super().__init__(f"{code}: {safe_msg}")
        self.code = code
        self.message = safe_msg
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            out["details"] = self.details
        return out


def validate_decimal_strings_only(value: Any, *, path: str = "plan") -> None:
    """Recursively verify that all numeric plan fields use decimal strings or integers (never float)."""
    if isinstance(value, bool):
        return
    if isinstance(value, float):
        raise ContractError("INTEGRITY_FAILURE", f"Float forbidden in {path}: {value!r}")
    if isinstance(value, dict):
        for k, v in value.items():
            validate_decimal_strings_only(v, path=f"{path}.{k}")
    elif isinstance(value, (list, tuple)):
        for idx, item in enumerate(value):
            validate_decimal_strings_only(item, path=f"{path}[{idx}]")


def is_valid_decimal_str(value: Any) -> bool:
    """Return True if value is a finite non-float Decimal string."""
    if type(value) is not str or not DECIMAL_STR_RE.fullmatch(value):
        return False
    try:
        d = Decimal(value)
    except (InvalidOperation, ValueError):
        return False
    return d.is_finite()


TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "list_active_signals": {
        "name": "list_active_signals",
        "description": (
            "List Core-verified non-expired QUANT signal summaries from the authenticated local facade. "
            "Read-only; preserves exact market_status, source_evidence_class, freshness, and expiry."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_LIST_LIMIT,
                    "description": "Maximum number of signal summaries to return (<= 50).",
                },
                "cursor": {
                    "type": "string",
                    "description": "Opaque bounded pagination cursor returned by a previous call.",
                },
                "as_of_ms": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Optional UTC epoch ms reference timestamp for active/expiry evaluation.",
                },
                "statuses": {
                    "type": "array",
                    "items": {"type": "string", "enum": sorted(MARKET_STATUSES)},
                    "description": "Optional status filter list (e.g., ['EXECUTABLE', 'WATCH']).",
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    },
    "get_signal_detail": {
        "name": "get_signal_detail",
        "description": (
            "Read the exact immutable QUANT SignalSnapshot for an episode_id (and optional card_id), "
            "including Decimal plan fields, reasons, source timestamps, and current freshness/expiry check."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "episode_id": {
                    "type": "string",
                    "description": "Core-assigned immutable episode_id.",
                },
                "card_id": {
                    "type": "string",
                    "description": "Optional immutable card_id within the episode.",
                },
                "as_of_ms": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Optional UTC epoch ms reference timestamp for freshness/expiry check.",
                },
            },
            "required": ["episode_id"],
            "additionalProperties": False,
        },
    },
    "get_market_context": {
        "name": "get_market_context",
        "description": (
            "Read approved public market-side context (quote, depth, mark, funding, OI, 4H regime) for an "
            "approved symbol. Never reads private B3 account data or triggers network fetches."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "enum": list(APPROVED_SYMBOLS),
                    "description": "Approved USD-M symbol (BTCUSDT, ETHUSDT, SOLUSDT).",
                },
                "as_of_ms": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Optional UTC epoch ms reference timestamp.",
                },
            },
            "required": ["symbol"],
            "additionalProperties": False,
        },
    },
    "get_latest_reprice": {
        "name": "get_latest_reprice",
        "description": (
            "Read the latest ALREADY-RECORDED +5/+10 minute immutable reprice card/receipt for an episode_id. "
            "Never triggers new Binance acquisition."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "episode_id": {
                    "type": "string",
                    "description": "Core-assigned immutable episode_id.",
                },
                "as_of_ms": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Optional UTC epoch ms reference timestamp.",
                },
            },
            "required": ["episode_id"],
            "additionalProperties": False,
        },
    },
    "get_signal_history": {
        "name": "get_signal_history",
        "description": (
            "Read bounded immutable QUANT journal history including status transitions and source evidence."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_LIST_LIMIT,
                    "description": "Maximum number of history records to return (<= 50).",
                },
                "cursor": {
                    "type": "string",
                    "description": "Opaque bounded pagination cursor.",
                },
                "start_ms": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Inclusive lower UTC epoch ms bound on evaluated_at_ms.",
                },
                "end_ms": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Inclusive upper UTC epoch ms bound on evaluated_at_ms.",
                },
                "symbol": {
                    "type": "string",
                    "enum": list(APPROVED_SYMBOLS),
                    "description": "Optional symbol filter.",
                },
                "episode_id": {
                    "type": "string",
                    "description": "Optional episode_id filter.",
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    },
    "get_strategy_summary": {
        "name": "get_strategy_summary",
        "description": (
            "Read factual B2 strategy family definitions and recorded synthetic/journal counts. "
            "Never makes profitability or economic edge claims."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "family": {
                    "type": "string",
                    "enum": list(APPROVED_FAMILIES),
                    "description": "Optional strategy family filter.",
                },
                "start_ms": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Optional start UTC epoch ms bound.",
                },
                "end_ms": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Optional end UTC epoch ms bound.",
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    },
    "request_reprice": {
        "name": "request_reprice",
        "description": (
            "Future state-producing reprice request interface. DISABLED_BY_DEFAULT in H1; "
            "always returns REPRICE_NOT_AUTHORIZED without source acquisition or journal writes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "episode_id": {
                    "type": "string",
                    "description": "Core-assigned immutable episode_id.",
                },
                "idempotency_key": {
                    "type": "string",
                    "description": "Caller idempotency key.",
                },
                "desired_delay_minutes": {
                    "type": "integer",
                    "enum": [5, 10],
                    "description": "Requested reprice delay (5 or 10 minutes).",
                },
                "requested_by": {
                    "type": "string",
                    "description": "Authenticated human principal identifier.",
                },
            },
            "required": ["episode_id", "idempotency_key", "desired_delay_minutes", "requested_by"],
            "additionalProperties": False,
        },
    },
}


SIGNAL_SNAPSHOT_REQUIRED_FIELDS: tuple[str, ...] = (
    "episode_id",
    "card_id",
    "card_version",
    "symbol",
    "direction",
    "strategy_family",
    "market_status",
    "status_reason_codes",
    "source_evidence_class",
    "source_origin",
    "source_receipt_sha256",
    "source_publication_sha256",
    "source_as_of_ms",
    "evaluated_at_ms",
    "observed_at_ms",
    "absolute_expiry_ms",
    "expiry_status",
    "freshness_state",
    "account_context_status",
    "account_overlay",
    "portfolio_exposure_limits",
    "safe_position_size",
    "plan",
    "latest_reprice",
    "reasons",
    "human_action",
    "verified_at_ms",
    "contract_version",
    "source_banner",
    "not_a_real_trade_signal",
)


def validate_signal_snapshot(snapshot: dict[str, Any]) -> None:
    """Strictly validate a projected episode-bound V1 SignalSnapshot against Contract V1 section 3."""
    if not isinstance(snapshot, dict):
        raise ContractError("INTEGRITY_FAILURE", "SignalSnapshot must be a JSON object")
    missing = [field for field in SIGNAL_SNAPSHOT_REQUIRED_FIELDS if field not in snapshot]
    if missing:
        raise ContractError("INTEGRITY_FAILURE", f"SignalSnapshot missing required fields: {missing}")
    ep_id = snapshot["episode_id"]
    if type(ep_id) is not str or not ep_id.strip() or ep_id.startswith("noep:"):
        raise ContractError("INTEGRITY_FAILURE", f"SignalSnapshot requires authentic episode_id, got {ep_id!r}")
    if snapshot["contract_version"] != CONTRACT_VERSION:
        raise ContractError("INTEGRITY_FAILURE", f"Invalid contract_version: {snapshot['contract_version']!r}")
    if snapshot["market_status"] not in MARKET_STATUSES:
        raise ContractError("INTEGRITY_FAILURE", f"Invalid market_status: {snapshot['market_status']!r}")
    if snapshot["freshness_state"] not in FRESHNESS_STATES:
        raise ContractError("INTEGRITY_FAILURE", f"Invalid freshness_state: {snapshot['freshness_state']!r}")
    if snapshot["account_context_status"] != "UNAVAILABLE":
        raise ContractError("INTEGRITY_FAILURE", "H1 account_context_status must remain UNAVAILABLE")
    if snapshot["account_overlay"] != "MANUAL_ACCOUNT_CHECK_REQUIRED":
        raise ContractError("INTEGRITY_FAILURE", "H1 account_overlay must remain MANUAL_ACCOUNT_CHECK_REQUIRED")
    if snapshot["portfolio_exposure_limits"] != "UNKNOWN" or snapshot["safe_position_size"] != "UNKNOWN":
        raise ContractError("INTEGRITY_FAILURE", "H1 exposure/sizing fields must remain UNKNOWN")
    if snapshot["source_evidence_class"] == EVIDENCE_UNKNOWN:
        raise ContractError("INTEGRITY_FAILURE", "UNKNOWN is not an admissible SignalSnapshot source_evidence_class")
    if snapshot["source_evidence_class"] == EVIDENCE_SYNTHETIC:
        if snapshot["not_a_real_trade_signal"] is not True:
            raise ContractError("INTEGRITY_FAILURE", "Synthetic snapshot must flag not_a_real_trade_signal=True")
        if SYNTHETIC_WARNING_TOKEN not in str(snapshot["source_banner"]):
            raise ContractError("INTEGRITY_FAILURE", "Synthetic snapshot missing NOT_A_REAL_TRADE_SIGNAL banner")
    elif snapshot["source_evidence_class"] not in ALLOWED_GENUINE_EVIDENCE:
        raise ContractError("INTEGRITY_FAILURE", f"Unknown source_evidence_class: {snapshot['source_evidence_class']!r}")
    if snapshot["plan"] is not None:
        validate_decimal_strings_only(snapshot["plan"], path="snapshot.plan")


def validate_diagnostic_record(diag: dict[str, Any]) -> None:
    """Validate a null-episode Core diagnostic record (P0-C01; never eligible for active signal or alert)."""
    if not isinstance(diag, dict):
        raise ContractError("INTEGRITY_FAILURE", "Diagnostic record must be a JSON object")
    missing = [field for field in SIGNAL_SNAPSHOT_REQUIRED_FIELDS if field not in diag]
    if missing:
        raise ContractError("INTEGRITY_FAILURE", f"Diagnostic record missing required fields: {missing}")
    if diag["episode_id"] is not None:
        raise ContractError("INTEGRITY_FAILURE", f"Diagnostic record must have episode_id=None, got {diag['episode_id']!r}")
    if diag.get("diagnostic_only") is not True or diag.get("not_eligible_for_alert") is not True:
        raise ContractError("INTEGRITY_FAILURE", "Diagnostic record must flag diagnostic_only=True and not_eligible_for_alert=True")
    if diag["contract_version"] != CONTRACT_VERSION:
        raise ContractError("INTEGRITY_FAILURE", f"Invalid contract_version: {diag['contract_version']!r}")
    if diag["market_status"] not in MARKET_STATUSES:
        raise ContractError("INTEGRITY_FAILURE", f"Invalid market_status: {diag['market_status']!r}")
    if diag["freshness_state"] not in FRESHNESS_STATES:
        raise ContractError("INTEGRITY_FAILURE", f"Invalid freshness_state: {diag['freshness_state']!r}")
    if diag["account_context_status"] != "UNAVAILABLE":
        raise ContractError("INTEGRITY_FAILURE", "H1 account_context_status must remain UNAVAILABLE")
    if diag["account_overlay"] != "MANUAL_ACCOUNT_CHECK_REQUIRED":
        raise ContractError("INTEGRITY_FAILURE", "H1 account_overlay must remain MANUAL_ACCOUNT_CHECK_REQUIRED")
    if diag["portfolio_exposure_limits"] != "UNKNOWN" or diag["safe_position_size"] != "UNKNOWN":
        raise ContractError("INTEGRITY_FAILURE", "H1 exposure/sizing fields must remain UNKNOWN")
    if diag["source_evidence_class"] == EVIDENCE_UNKNOWN:
        raise ContractError("INTEGRITY_FAILURE", "UNKNOWN is not an admissible verified source_evidence_class")
    if diag["source_evidence_class"] == EVIDENCE_SYNTHETIC:
        if diag["not_a_real_trade_signal"] is not True:
            raise ContractError("INTEGRITY_FAILURE", "Synthetic diagnostic must flag not_a_real_trade_signal=True")
        if SYNTHETIC_WARNING_TOKEN not in str(diag["source_banner"]):
            raise ContractError("INTEGRITY_FAILURE", "Synthetic diagnostic missing NOT_A_REAL_TRADE_SIGNAL banner")
    elif diag["source_evidence_class"] not in ALLOWED_GENUINE_EVIDENCE:
        raise ContractError("INTEGRITY_FAILURE", f"Unknown source_evidence_class: {diag['source_evidence_class']!r}")


def validate_request_envelope(req: Any) -> dict[str, Any]:
    """Validate incoming V1 transport request envelope."""
    if not isinstance(req, dict):
        raise ContractError("INVALID_ARGUMENT", "Request must be a JSON object")
    required = ("contract_id", "request_id", "tool", "args", "principal_id", "recipient_scope", "deadline_ms")
    for key in required:
        if key not in req:
            raise ContractError("INVALID_ARGUMENT", f"Missing request field: {key}")
    extra = set(req.keys()) - set(required)
    if extra:
        raise ContractError("INVALID_ARGUMENT", f"Unexpected request fields: {sorted(extra)}")
    if req["contract_id"] != CONTRACT_ID:
        raise ContractError("INVALID_ARGUMENT", f"Unsupported contract_id: {req['contract_id']!r}")
    request_id = req["request_id"]
    if type(request_id) is not str or not SAFE_ID_RE.fullmatch(request_id):
        raise ContractError("INVALID_ARGUMENT", "Invalid request_id")
    tool = req["tool"]
    if type(tool) is not str:
        raise ContractError("INVALID_ARGUMENT", "tool must be a string")
    if tool not in V1_ALL_TOOLS:
        raise ContractError("UNKNOWN_TOOL", f"Tool not in V1 allowlist: {tool}")
    if not isinstance(req["args"], dict):
        raise ContractError("INVALID_ARGUMENT", "args must be a JSON object")
    if type(req["principal_id"]) is not str or not req["principal_id"].strip():
        raise ContractError("UNAUTHORIZED", "principal_id must be a non-empty string")
    if not isinstance(req["recipient_scope"], (str, list)):
        raise ContractError("INVALID_ARGUMENT", "recipient_scope must be string or list")
    deadline_ms = req["deadline_ms"]
    if type(deadline_ms) is not int or deadline_ms <= 0 or deadline_ms > MAX_DEADLINE_MS:
        raise ContractError("INVALID_ARGUMENT", f"deadline_ms must be 1..{MAX_DEADLINE_MS}")
    return req


def build_response_envelope(
    *,
    request_id: str,
    generated_at_ms: int,
    status: str,
    server_as_of_ms: int | None,
    source_evidence_class: str,
    data: Any = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construct canonical Contract V1 section 2 response envelope."""
    if status not in {"OK", "ERROR"}:
        raise ValueError(f"Invalid response status: {status!r}")
    if source_evidence_class not in ALLOWED_RESPONSE_EVIDENCE_CLASSES:
        raise ValueError(f"Invalid response source_evidence_class: {source_evidence_class!r}")
    return {
        "contract_id": CONTRACT_ID,
        "request_id": request_id,
        "generated_at_ms": generated_at_ms,
        "status": status,
        "data": data if status == "OK" else None,
        "error": error if status == "ERROR" else None,
        "server_as_of_ms": server_as_of_ms,
        "source_evidence_class": source_evidence_class,
    }
