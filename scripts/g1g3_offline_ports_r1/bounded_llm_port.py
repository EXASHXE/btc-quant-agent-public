"""BoundedLLMPort: Schema-bounded, injection-hardened, fail-closed loopback LLM analysis port.

Enforces request/response schemas, token/byte/depth caps, socket timeouts, retry budget,
duplicate context detection, prompt-injection neutralization, and owner-independent traces.
On any transport, timeout, schema, or model-hash failure, fails closed to
NO_ACTION_OR_MANUAL_REVIEW and never authorizes approval or orders.
"""

from __future__ import annotations

import copy
import time
from typing import Any

from scripts.g1_offline_preview_r1.model import (
    SafetyViolation,
    canonical,
    digest,
    exact,
    redact_text,
    timestamp,
)
from scripts.g1_offline_preview_r1.storage import strict_json

from .loopback_servers import LoopbackHTTPConnection
from .no_order_port import NoOrderPort

PINNED_MODEL_ID = "offline-loopback-analyzer-v1"
MAX_ALLOWED_TOKENS = 256
MAX_ALLOWED_REQUEST_BYTES = 8192
MAX_ALLOWED_RESPONSE_BYTES = 4096
MAX_ALLOWED_JSON_DEPTH = 6
MAX_ALLOWED_TIMEOUT_MS = 5000
MAX_ALLOWED_ATTEMPTS = 3

PROMPT_INJECTION_PATTERNS = (
    "ignore previous instructions",
    "ignore all previous",
    "disregard instructions",
    "approve_order",
    "execute_order",
    "submit_order",
    "place_order",
    "bypass_human",
    "auto_approve",
    "system_override",
    "tool_call",
)

REQUEST_SCHEMA_KEYS = {
    "schema_version",
    "request_id",
    "model_id",
    "signal_id",
    "proposal_hash",
    "source_hash",
    "as_of",
    "max_tokens",
    "max_response_bytes",
    "timeout_ms",
    "redacted_context",
}

RESPONSE_ENVELOPE_KEYS = {
    "schema_version",
    "model_id",
    "request_sha256",
    "token_usage",
    "analysis",
}

ANALYSIS_OBJECT_KEYS = {
    "schema_version",
    "signal_id",
    "proposal_hash",
    "source_hash",
    "as_of",
    "summary",
    "risk",
}


def _json_depth(value: Any, current: int = 0) -> int:
    if isinstance(value, dict):
        if not value:
            return current + 1
        return max(_json_depth(v, current + 1) for v in value.values())
    if isinstance(value, list):
        if not value:
            return current + 1
        return max(_json_depth(v, current + 1) for v in value)
    return current


def _has_prompt_injection(text: str) -> bool:
    lowered = text.lower()
    return any(pat in lowered for pat in PROMPT_INJECTION_PATTERNS)


class BoundedLLMPort:
    """Bounded, fail-closed LLM analysis port operating strictly offline or via loopback fake."""

    def __init__(
        self,
        *,
        endpoint_url: str | None = None,
        allow_loopback: bool = False,
        allowed_endpoints: set[tuple[str, int]] | None = None,
        expected_model_id: str = PINNED_MODEL_ID,
        max_tokens: int = 128,
        max_request_bytes: int = 4096,
        max_response_bytes: int = 2048,
        max_json_depth: int = MAX_ALLOWED_JSON_DEPTH,
        timeout_ms: int = 150,
        max_attempts: int = 2,
        retry_budget_ms: int = 500,
        no_order_port: NoOrderPort | None = None,
    ) -> None:
        if not (1 <= max_tokens <= MAX_ALLOWED_TOKENS):
            raise SafetyViolation("LLM_CONFIG_BOUNDS_INVALID")
        if not (1 <= max_request_bytes <= MAX_ALLOWED_REQUEST_BYTES):
            raise SafetyViolation("LLM_CONFIG_BOUNDS_INVALID")
        if not (1 <= max_response_bytes <= MAX_ALLOWED_RESPONSE_BYTES):
            raise SafetyViolation("LLM_CONFIG_BOUNDS_INVALID")
        if not (1 <= max_json_depth <= MAX_ALLOWED_JSON_DEPTH):
            raise SafetyViolation("LLM_CONFIG_BOUNDS_INVALID")
        if not (1 <= timeout_ms <= MAX_ALLOWED_TIMEOUT_MS):
            raise SafetyViolation("LLM_CONFIG_BOUNDS_INVALID")
        if not (1 <= max_attempts <= MAX_ALLOWED_ATTEMPTS):
            raise SafetyViolation("LLM_CONFIG_BOUNDS_INVALID")
        if not (1 <= retry_budget_ms <= 10000):
            raise SafetyViolation("LLM_CONFIG_BOUNDS_INVALID")

        self.endpoint_url = endpoint_url
        self.allow_loopback = allow_loopback
        self.allowed_endpoints = set(allowed_endpoints or set())
        self.expected_model_id = expected_model_id
        self.max_tokens = max_tokens
        self.max_request_bytes = max_request_bytes
        self.max_response_bytes = max_response_bytes
        self.max_json_depth = max_json_depth
        self.timeout_ms = timeout_ms
        self.max_attempts = max_attempts
        self.retry_budget_ms = retry_budget_ms
        self.no_order_port = no_order_port or NoOrderPort()
        self.seen_contexts: set[tuple[str, str, str]] = set()
        self.traces: list[dict[str, Any]] = []

    def build_request(
        self,
        *,
        signal_id: str,
        proposal_hash: str,
        source_hash: str,
        as_of: int,
        context_text: str = "Synthetic market/signal context",
    ) -> dict[str, Any]:
        """Construct and validate a redacted, SHA-bound LLMAnalysisRequestV1."""
        if not isinstance(signal_id, str) or not signal_id:
            raise SafetyViolation("LLM_REQUEST_SCHEMA_INVALID")
        if not isinstance(proposal_hash, str) or not proposal_hash:
            raise SafetyViolation("LLM_REQUEST_SCHEMA_INVALID")
        if not isinstance(source_hash, str) or not source_hash:
            raise SafetyViolation("LLM_REQUEST_SCHEMA_INVALID")
        timestamp(as_of)
        if not isinstance(context_text, str):
            raise SafetyViolation("LLM_REQUEST_SCHEMA_INVALID")
        redacted = redact_text(context_text)
        req_id = digest(
            [
                signal_id,
                proposal_hash,
                source_hash,
                as_of,
                self.expected_model_id,
                redacted,
            ]
        )
        req = {
            "schema_version": 1,
            "request_id": req_id,
            "model_id": self.expected_model_id,
            "signal_id": signal_id,
            "proposal_hash": proposal_hash,
            "source_hash": source_hash,
            "as_of": as_of,
            "max_tokens": self.max_tokens,
            "max_response_bytes": self.max_response_bytes,
            "timeout_ms": self.timeout_ms,
            "redacted_context": redacted,
        }
        exact(req, REQUEST_SCHEMA_KEYS, "LLM_REQUEST_SCHEMA_INVALID")
        raw_bytes = canonical(req).encode("utf-8")
        if len(raw_bytes) > self.max_request_bytes:
            raise SafetyViolation("LLM_REQUEST_TOO_LARGE")
        return req

    def _fail_closed(
        self,
        *,
        code: str,
        req: dict[str, Any] | None,
        request_sha256: str,
        response_sha256: str | None,
        attempts: int,
        elapsed_ms: int,
    ) -> dict[str, Any]:
        trace_id = digest([request_sha256, "bounded_llm_trace"])[:24]
        span_id = digest([request_sha256, code, attempts])[:16]
        record = {
            "status": "NO_ACTION_OR_MANUAL_REVIEW",
            "approved": False,
            "order_authorized": False,
            "failure_code": code,
            "model_id": self.expected_model_id,
            "request_id": req.get("request_id") if isinstance(req, dict) else None,
            "request_sha256": request_sha256,
            "response_sha256": response_sha256,
            "attempts": attempts,
            "elapsed_ms": elapsed_ms,
            "trace_id": trace_id,
            "span_id": span_id,
            "analysis": None,
        }
        self.traces.append(copy.deepcopy(record))
        return record

    def analyze(
        self,
        *,
        signal_id: str,
        proposal_hash: str,
        source_hash: str,
        as_of: int,
        context_text: str = "Synthetic market/signal context",
        offline_mock_response: dict[str, Any] | str | None = None,
    ) -> dict[str, Any]:
        """Run bounded LLM analysis (via loopback HTTP or offline mock), failing closed on any fault."""
        start_ns = time.monotonic_ns()
        try:
            req = self.build_request(
                signal_id=signal_id,
                proposal_hash=proposal_hash,
                source_hash=source_hash,
                as_of=as_of,
                context_text=context_text,
            )
        except SafetyViolation as exc:
            return self._fail_closed(
                code=exc.code,
                req=None,
                request_sha256=digest(str(signal_id)),
                response_sha256=None,
                attempts=0,
                elapsed_ms=0,
            )

        req_sha = digest(req)
        ctx_key = (signal_id, proposal_hash, source_hash)
        if ctx_key in self.seen_contexts:
            return self._fail_closed(
                code="LLM_DUPLICATE_CONTEXT",
                req=req,
                request_sha256=req_sha,
                response_sha256=None,
                attempts=0,
                elapsed_ms=0,
            )

        # Prompt-injection guard on input market/news text
        if _has_prompt_injection(context_text):
            return self._fail_closed(
                code="LLM_PROMPT_INJECTION_BLOCKED",
                req=req,
                request_sha256=req_sha,
                response_sha256=None,
                attempts=0,
                elapsed_ms=0,
            )

        self.seen_contexts.add(ctx_key)

        if offline_mock_response is not None and self.endpoint_url is None:
            raw_str = (
                offline_mock_response
                if isinstance(offline_mock_response, str)
                else canonical(offline_mock_response)
            )
            return self._validate_raw_response(
                raw_str.encode("utf-8"),
                req=req,
                req_sha=req_sha,
                attempts=1,
                start_ns=start_ns,
            )

        # Validate loopback endpoint before any socket activity
        try:
            if self.endpoint_url is None:
                raise SafetyViolation("LLM_ENDPOINT_MISSING")
            host, port, path = self.no_order_port.validate_endpoint_url(
                self.endpoint_url,
                allow_loopback=self.allow_loopback,
                allowed_endpoints=self.allowed_endpoints,
            )
        except SafetyViolation as exc:
            return self._fail_closed(
                code=exc.code,
                req=req,
                request_sha256=req_sha,
                response_sha256=None,
                attempts=0,
                elapsed_ms=int((time.monotonic_ns() - start_ns) // 1_000_000),
            )

        req_body = canonical(req).encode("utf-8")
        last_failure_code = "LLM_UNKNOWN_FAILURE"
        last_resp_sha: str | None = None
        attempts_made = 0

        for attempt in range(1, self.max_attempts + 1):
            elapsed_ms = int((time.monotonic_ns() - start_ns) // 1_000_000)
            if attempt > 1 and elapsed_ms >= self.retry_budget_ms:
                last_failure_code = "LLM_RETRY_BUDGET_EXHAUSTED"
                break
            attempts_made = attempt
            conn = LoopbackHTTPConnection(host, port, timeout=self.timeout_ms / 1000.0)
            try:
                conn.request(
                    "POST",
                    path,
                    body=req_body,
                    headers={"Content-Type": "application/json; charset=utf-8"},
                )
                resp = conn.getresponse()
                status = resp.status
                raw_resp = resp.read(self.max_response_bytes + 1)
                last_resp_sha = digest(raw_resp.decode("utf-8", errors="replace"))
                if len(raw_resp) > self.max_response_bytes:
                    return self._fail_closed(
                        code="LLM_RESPONSE_TOO_LARGE",
                        req=req,
                        request_sha256=req_sha,
                        response_sha256=last_resp_sha,
                        attempts=attempts_made,
                        elapsed_ms=int((time.monotonic_ns() - start_ns) // 1_000_000),
                    )
                if status in (408, 429, 500, 502, 503, 504):
                    last_failure_code = f"LLM_HTTP_{status}_EXHAUSTED"
                    continue
                if status != 200:
                    return self._fail_closed(
                        code=f"LLM_HTTP_{status}",
                        req=req,
                        request_sha256=req_sha,
                        response_sha256=last_resp_sha,
                        attempts=attempts_made,
                        elapsed_ms=int((time.monotonic_ns() - start_ns) // 1_000_000),
                    )
                return self._validate_raw_response(
                    raw_resp,
                    req=req,
                    req_sha=req_sha,
                    attempts=attempts_made,
                    start_ns=start_ns,
                )
            except TimeoutError:
                last_failure_code = "LLM_TIMEOUT"
                continue
            except SafetyViolation as exc:
                return self._fail_closed(
                    code=exc.code,
                    req=req,
                    request_sha256=req_sha,
                    response_sha256=last_resp_sha,
                    attempts=attempts_made,
                    elapsed_ms=int((time.monotonic_ns() - start_ns) // 1_000_000),
                )
            except OSError:
                last_failure_code = "LLM_TRANSPORT_ERROR"
                continue
            finally:
                conn.close()

        return self._fail_closed(
            code=last_failure_code,
            req=req,
            request_sha256=req_sha,
            response_sha256=last_resp_sha,
            attempts=attempts_made,
            elapsed_ms=int((time.monotonic_ns() - start_ns) // 1_000_000),
        )

    def _validate_raw_response(
        self,
        raw_bytes: bytes,
        *,
        req: dict[str, Any],
        req_sha: str,
        attempts: int,
        start_ns: int,
    ) -> dict[str, Any]:
        elapsed_ms = int((time.monotonic_ns() - start_ns) // 1_000_000)
        resp_sha = digest(raw_bytes.decode("utf-8", errors="replace"))
        if len(raw_bytes) > self.max_response_bytes:
            return self._fail_closed(
                code="LLM_RESPONSE_TOO_LARGE",
                req=req,
                request_sha256=req_sha,
                response_sha256=resp_sha,
                attempts=attempts,
                elapsed_ms=elapsed_ms,
            )
        try:
            parsed = strict_json(raw_bytes.decode("utf-8"))
        except (SafetyViolation, UnicodeError) as exc:
            code = exc.code if isinstance(exc, SafetyViolation) else "JSON_MALFORMED"
            return self._fail_closed(
                code=f"LLM_{code}",
                req=req,
                request_sha256=req_sha,
                response_sha256=resp_sha,
                attempts=attempts,
                elapsed_ms=elapsed_ms,
            )

        if _json_depth(parsed) > self.max_json_depth:
            return self._fail_closed(
                code="LLM_JSON_DEPTH_EXCEEDED",
                req=req,
                request_sha256=req_sha,
                response_sha256=resp_sha,
                attempts=attempts,
                elapsed_ms=elapsed_ms,
            )

        if not isinstance(parsed, dict):
            return self._fail_closed(
                code="LLM_SCHEMA_DRIFT",
                req=req,
                request_sha256=req_sha,
                response_sha256=resp_sha,
                attempts=attempts,
                elapsed_ms=elapsed_ms,
            )

        if "tool_calls" in parsed:
            return self._fail_closed(
                code="LLM_PROMPT_INJECTION_BLOCKED",
                req=req,
                request_sha256=req_sha,
                response_sha256=resp_sha,
                attempts=attempts,
                elapsed_ms=elapsed_ms,
            )

        try:
            exact(parsed, RESPONSE_ENVELOPE_KEYS, "LLM_SCHEMA_DRIFT")
        except SafetyViolation:
            return self._fail_closed(
                code="LLM_SCHEMA_DRIFT",
                req=req,
                request_sha256=req_sha,
                response_sha256=resp_sha,
                attempts=attempts,
                elapsed_ms=elapsed_ms,
            )

        if type(parsed["schema_version"]) is not int or parsed["schema_version"] != 1:
            return self._fail_closed(
                code="LLM_SCHEMA_DRIFT",
                req=req,
                request_sha256=req_sha,
                response_sha256=resp_sha,
                attempts=attempts,
                elapsed_ms=elapsed_ms,
            )

        if parsed["model_id"] != self.expected_model_id:
            return self._fail_closed(
                code="LLM_MODEL_HASH_MISMATCH",
                req=req,
                request_sha256=req_sha,
                response_sha256=resp_sha,
                attempts=attempts,
                elapsed_ms=elapsed_ms,
            )

        if parsed["request_sha256"] != req_sha:
            return self._fail_closed(
                code="LLM_REQUEST_HASH_MISMATCH",
                req=req,
                request_sha256=req_sha,
                response_sha256=resp_sha,
                attempts=attempts,
                elapsed_ms=elapsed_ms,
            )

        usage = parsed["token_usage"]
        if not isinstance(usage, dict) or set(usage) != {
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
        }:
            return self._fail_closed(
                code="LLM_TOKEN_USAGE_SCHEMA",
                req=req,
                request_sha256=req_sha,
                response_sha256=resp_sha,
                attempts=attempts,
                elapsed_ms=elapsed_ms,
            )
        comp_tokens = usage["completion_tokens"]
        tot_tokens = usage["total_tokens"]
        if (
            type(comp_tokens) is not int
            or type(tot_tokens) is not int
            or comp_tokens < 1
            or comp_tokens > self.max_tokens
            or tot_tokens > self.max_tokens * 2
        ):
            return self._fail_closed(
                code="LLM_TOKEN_CAP_EXCEEDED",
                req=req,
                request_sha256=req_sha,
                response_sha256=resp_sha,
                attempts=attempts,
                elapsed_ms=elapsed_ms,
            )

        analysis = parsed["analysis"]
        try:
            exact(analysis, ANALYSIS_OBJECT_KEYS, "LLM_SCHEMA_DRIFT")
        except SafetyViolation:
            if isinstance(analysis, dict) and any(
                k in analysis for k in ("place_order", "approve", "tool_calls", "order")
            ):
                return self._fail_closed(
                    code="LLM_PROMPT_INJECTION_BLOCKED",
                    req=req,
                    request_sha256=req_sha,
                    response_sha256=resp_sha,
                    attempts=attempts,
                    elapsed_ms=elapsed_ms,
                )
            return self._fail_closed(
                code="LLM_SCHEMA_DRIFT",
                req=req,
                request_sha256=req_sha,
                response_sha256=resp_sha,
                attempts=attempts,
                elapsed_ms=elapsed_ms,
            )

        if (
            type(analysis["schema_version"]) is not int
            or analysis["schema_version"] != 1
            or analysis["signal_id"] != req["signal_id"]
            or analysis["proposal_hash"] != req["proposal_hash"]
            or analysis["source_hash"] != req["source_hash"]
            or analysis["as_of"] != req["as_of"]
        ):
            return self._fail_closed(
                code="LLM_OUTPUT_DRIFT",
                req=req,
                request_sha256=req_sha,
                response_sha256=resp_sha,
                attempts=attempts,
                elapsed_ms=elapsed_ms,
            )

        if analysis["risk"] != "DESCRIPTIVE_ONLY":
            return self._fail_closed(
                code="LLM_PROMPT_INJECTION_BLOCKED",
                req=req,
                request_sha256=req_sha,
                response_sha256=resp_sha,
                attempts=attempts,
                elapsed_ms=elapsed_ms,
            )

        summary = analysis["summary"]
        if not isinstance(summary, str) or not (1 <= len(summary) <= 256):
            return self._fail_closed(
                code="LLM_SCHEMA_DRIFT",
                req=req,
                request_sha256=req_sha,
                response_sha256=resp_sha,
                attempts=attempts,
                elapsed_ms=elapsed_ms,
            )
        if _has_prompt_injection(summary):
            return self._fail_closed(
                code="LLM_PROMPT_INJECTION_BLOCKED",
                req=req,
                request_sha256=req_sha,
                response_sha256=resp_sha,
                attempts=attempts,
                elapsed_ms=elapsed_ms,
            )

        clean_analysis = copy.deepcopy(analysis)
        clean_analysis["summary"] = redact_text(summary)

        trace_id = digest([req_sha, "bounded_llm_trace"])[:24]
        span_id = digest([req_sha, resp_sha, attempts])[:16]
        result = {
            "status": "DESCRIPTIVE_ANALYSIS_VERIFIED",
            "approved": False,
            "order_authorized": False,
            "failure_code": None,
            "model_id": self.expected_model_id,
            "request_id": req["request_id"],
            "request_sha256": req_sha,
            "response_sha256": resp_sha,
            "attempts": attempts,
            "elapsed_ms": elapsed_ms,
            "trace_id": trace_id,
            "span_id": span_id,
            "analysis": clean_analysis,
        }
        self.traces.append(copy.deepcopy(result))
        return result
